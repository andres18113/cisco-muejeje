"""The bounded operational-readiness gate in front of HTTP client requests.

One question, asked once per switch/VLAN group, immediately before the first
request that depends on it: do the exact access ports of that path forward user
frames right now. The observation is the one the configuration runtime already
performs and the decision is the one the domain already makes; this module only
places them, bounds them and remembers the answer for the rest of the
invocation.

Three properties are deliberate.

Lazy, not staged. Readiness is observed when the first dependent expectation
becomes admissible, not at an earlier stage, because a sample taken before E6
applied would be answering about a different moment. A run whose HTTP
expectations are all blocked upstream therefore observes nothing at all.

Grouped, not per client. Four clients on one switch and VLAN cost one query.
The memo lives for exactly one invocation: a result from an earlier run is
never reused, because identity and state may have changed in between.

Fail-closed in every direction. A missing observer, an exhausted budget, an
observer that raised, a path the plan could not place and every refusing
dimension of the sample all produce the same kind of answer -- a named refusal
-- and none of them lets a request through. There is no argument, flag or
setting that turns the gate off.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Protocol

from ...domain.enterprise.models.forwarding import AccessForwardingObservation
from ...domain.enterprise.services.access_forwarding import (
    access_forwarding_admission,
    access_forwarding_facts,
)
from ...domain.enterprise.services.service_access_readiness import (
    CAUSE_ANSWER_DOES_NOT_MATCH_REQUEST,
    CAUSE_BUDGET_EXHAUSTED,
    CAUSE_OBSERVATION_FAILED,
    CAUSE_OBSERVER_UNAVAILABLE,
    AccessReadinessGroupResult,
    AccessReadinessPlan,
    AccessReadinessRequirement,
    ReadinessDependentResult,
    observed_group_result,
    unobserved_group_result,
    unplaced_group_result,
)

#: Total wait and group ceilings for one invocation. The gate carries each
#: remaining allowance into the runtime and rechecks it after every read.
READINESS_TOTAL_BUDGET_SECONDS = 120.0
READINESS_MAX_GROUPS = 4
READINESS_GROUP_DEADLINE_SECONDS = 30.0
READINESS_GROUP_MAX_SAMPLES = 31
READINESS_GROUP_INTERVAL_SECONDS = 1.0
READINESS_SAMPLE_CALLS = 6


class ReadinessNotRequired:
    """An explicit declaration that this caller needs no readiness gate.

    It exists so that "no gate" can never be the shape a call happens to have.
    The diagnostic qualification stages take their own forwarding evidence,
    record it in their immutable results and are budgeted for exactly the
    operations they declare; running the product gate inside them would add
    unbudgeted queries and a second, differently scoped forwarding claim. Those
    callers say so here, with a reason, and any new caller has to decide rather
    than inherit a default.
    """

    def __init__(self, reason: str) -> None:
        """Record why this caller performs no gated readiness observation."""
        if not reason:
            raise ValueError("a readiness exemption must state its reason")
        self.reason = reason


class ReadinessGateConsumed(RuntimeError):
    """A readiness gate was offered to a second application."""


class AccessForwardingObserver(Protocol):
    """The port one bounded switch/VLAN forwarding observation needs."""

    def observe_access_forwarding(
        self,
        device_name: str,
        vlan_id: int,
        interfaces: Sequence[str],
        *,
        remaining_seconds: float,
        max_samples: int,
        deadline_seconds: float,
        interval_seconds: float,
        sample_calls: int,
    ) -> AccessForwardingObservation:
        """Observe one exact group with the caller's remaining time and policy."""


class ServiceAccessReadinessGate:
    """Decide, once per group, whether its dependent requests may run."""

    def __init__(
        self,
        plan: AccessReadinessPlan,
        observer: AccessForwardingObserver | None,
        *,
        clock: Callable[[], float],
        device_names: Mapping[str, str] | None = None,
        total_budget_seconds: float = READINESS_TOTAL_BUDGET_SECONDS,
        max_groups: int = READINESS_MAX_GROUPS,
    ) -> None:
        """Bind the gate to one derived plan without observing anything yet."""
        self._plan = plan
        self._observer = observer
        self._clock = clock
        self._device_names = dict(device_names or {})
        self._total_budget_seconds = float(total_budget_seconds)
        self._max_groups = int(max_groups)
        self._started: float | None = None
        self._observed_groups = 0
        self._results: dict[tuple[str, int], AccessReadinessGroupResult] = {}
        self._by_expectation: dict[str, ReadinessDependentResult] = {}
        self._requirements = {item.key: item for item in plan.requirements}
        self._unplaced_recorded = False
        self._consumed = False
        self.observations: list[tuple[str, int, tuple[str, ...]]] = []

    def begin_invocation(self) -> None:
        """Claim this gate for one application, and refuse a second.

        The memo exists so one grouped query serves every client of a group
        inside ONE application. Across applications it would be a stale
        verdict about a moment whose identity and state may have changed, so a
        second claim is refused loudly instead of answered from the cache.
        """
        if self._consumed:
            raise ReadinessGateConsumed(
                "a readiness gate serves one application; build a fresh one"
            )
        self._consumed = True

    def decide(self, expectation_id: str) -> ReadinessDependentResult | None:
        """Return the readiness verdict for one expectation, observing if needed.

        Returns `None` when the expectation is not gated at all, which is the
        only way a caller proceeds without a verdict.
        """
        if expectation_id in self._by_expectation:
            return self._by_expectation[expectation_id]
        key = self._plan.group_by_expectation.get(expectation_id)
        if key is None:
            unplaced = [
                item
                for item in self._plan.unplaced
                if item.expectation_id == expectation_id
            ]
            if not unplaced:
                return None
            self._record(unplaced_group_result(self._plan.unplaced))
            self._unplaced_recorded = True
            return self._by_expectation.get(expectation_id)
        requirement = self._requirements.get(key)
        if requirement is None:
            return None
        if key not in self._results:
            self._record(self._observe(requirement))
        return self._by_expectation.get(expectation_id)

    def rows(self) -> list[dict[str, object]]:
        """Return the public readiness rows, including groups never reached.

        A group whose dependents were all blocked upstream is reported as
        never observed rather than omitted, so the report says what the run did
        not ask as clearly as what it did.
        """
        recorded = list(self._results.values())
        for requirement in self._plan.requirements:
            if requirement.key not in self._results:
                recorded.append(
                    unobserved_group_result(
                        requirement, cause="dependent_never_became_admissible"
                    )
                )
        if self._plan.unplaced and not self._unplaced_recorded:
            recorded.append(unplaced_group_result(self._plan.unplaced))
        return [item.as_row() for item in recorded]

    def _record(self, result: AccessReadinessGroupResult) -> None:
        """Keep one group verdict and index its dependents."""
        self._results[(result.switch_device_id, result.vlan_id)] = result
        for dependent in result.dependents:
            self._by_expectation[dependent.expectation_id] = dependent

    def _observe(
        self, requirement: AccessReadinessRequirement
    ) -> AccessReadinessGroupResult:
        """Take one bounded observation episode, or name why it took none."""
        if self._observer is None:
            return unobserved_group_result(
                requirement, cause=CAUSE_OBSERVER_UNAVAILABLE
            )
        if self._started is None:
            self._started = self._clock()
        if self._observed_groups >= self._max_groups:
            return unobserved_group_result(
                requirement,
                cause=f"{CAUSE_BUDGET_EXHAUSTED}:groups={self._max_groups}",
            )
        group_started = self._clock()
        remaining = self._total_budget_seconds - (group_started - self._started)
        if remaining <= 0:
            return unobserved_group_result(
                requirement,
                cause=(
                    f"{CAUSE_BUDGET_EXHAUSTED}:seconds={self._total_budget_seconds:g}"
                ),
            )
        switch_name = self._device_names.get(
            requirement.switch_device_id, requirement.switch_device_name
        )
        self._observed_groups += 1
        self.observations.append(
            (switch_name, requirement.vlan_id, requirement.interfaces)
        )
        try:
            observation = self._observer.observe_access_forwarding(
                switch_name,
                requirement.vlan_id,
                list(requirement.interfaces),
                remaining_seconds=remaining,
                max_samples=READINESS_GROUP_MAX_SAMPLES,
                deadline_seconds=READINESS_GROUP_DEADLINE_SECONDS,
                interval_seconds=READINESS_GROUP_INTERVAL_SECONDS,
                sample_calls=READINESS_SAMPLE_CALLS,
            )
        except Exception as exc:
            # An observer that raised observed nothing. That is the absence of
            # a sample, not a negative one, and it authorizes nothing either.
            return unobserved_group_result(
                requirement,
                cause=f"{CAUSE_OBSERVATION_FAILED}:{type(exc).__name__}",
            )
        if self._clock() - group_started >= min(
            remaining, READINESS_GROUP_DEADLINE_SECONDS
        ):
            # The rows remain available, but the product deadline is a closed
            # permission boundary even if an observer returned a late FWD.
            observation = replace(observation, deadline_reached=True)
        mismatch = _envelope_mismatch(observation, switch_name, requirement)
        if mismatch:
            # A sample was taken, but not of this group. Treating it as a
            # refusal would say something about these ports; it says nothing.
            return unobserved_group_result(
                requirement,
                cause=f"{CAUSE_ANSWER_DOES_NOT_MATCH_REQUEST}:{mismatch}",
            )
        admission = access_forwarding_admission(observation)
        return observed_group_result(
            requirement,
            admitted=admission.admitted,
            dimension=admission.dimension,
            causes=admission.causes,
            sample=access_forwarding_facts(observation, admission),
            forwarding_interfaces=admission.forwarding_interfaces,
        )


def _envelope_mismatch(
    observation: AccessForwardingObservation,
    switch_name: str,
    requirement: AccessReadinessRequirement,
) -> str:
    """Name how one observation fails to answer the question it was asked.

    The admission rule checks that a sample is internally consistent -- that the
    device it reports is the device it names. It cannot check that the sample is
    about the SWITCH AND VLAN THIS GROUP ASKED ABOUT, because it never sees the
    request. That binding is made here, so a self-consistent answer about
    another switch, another VLAN or a narrower interface set can never be read
    as permission for these ports.
    """
    if observation.switch_name != switch_name:
        return f"switch:{observation.switch_name or 'unnamed'}"
    if observation.vlan_id != requirement.vlan_id:
        return f"vlan:{observation.vlan_id}"
    missing = tuple(
        item
        for item in requirement.interfaces
        if item not in set(observation.requested_interfaces)
    )
    if missing:
        return "interfaces:" + ",".join(missing)
    return ""
