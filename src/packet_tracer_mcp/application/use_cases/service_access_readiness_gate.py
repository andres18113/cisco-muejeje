"""The bounded operational-readiness gate in front of HTTP client requests.

One question, asked once per group, immediately before the first request that
depends on it: do the exact access ports of that path forward user frames
right now, and, for a path between two access switches, do forwarding trunks
join them in the path's VLAN. The observations are the ones the configuration
runtime already performs with registered readers, and the decisions are the
ones the domain already makes; this module only places them, bounds them and
remembers the answers for the rest of the invocation.

Four properties are deliberate.

Lazy, not staged. Readiness is observed when the first dependent expectation
becomes admissible, not at an earlier stage, because a sample taken before E6
applied would be answering about a different moment. A run whose HTTP
expectations are all blocked upstream therefore observes nothing at all.

Grouped, not per client. Four clients on one switch and VLAN cost one query,
and a thousand clients behind forty access switches cost forty access groups
and one continuity group per component. The memo lives for exactly one
invocation and is keyed by the group's complete identity and its dependency
revision: a relevant configuration change advances the revision and the next
dependent observes again. A result from an earlier run is never reused.

Dependency-local. A dependent names every group its path needs and is
admitted only when all of them admit it. A group that refuses blocks exactly
its dependents; every other dependent is decided by its own groups. When a
group refused only because some of its interfaces (or some of its pairs) never
forwarded while the last authoritative sample showed the others forwarding,
the gate asks once more, with a fresh bounded episode, about exactly that
forwarding subset. It is a different question with its own identity; it can
admit only the dependents it fully covers, and it never rescues the rest.

Fail-closed in every direction. A missing observer, an exhausted budget, an
observer that raised, a path the plan could not place and every refusing
dimension of a sample all produce the same kind of answer -- a named refusal
-- and none of them lets a request through. There is no argument, flag or
setting that turns the gate off.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Protocol

from ...domain.enterprise.models.forwarding import AccessForwardingObservation
from ...domain.enterprise.services.access_forwarding import (
    CAUSE_GROUP_DEADLINE_REACHED,
    access_forwarding_admission,
    access_forwarding_facts,
    forwarding_subset,
)
from ...domain.enterprise.services.service_access_readiness import (
    CAUSE_ANSWER_DOES_NOT_MATCH_REQUEST,
    CAUSE_BUDGET_EXHAUSTED,
    CAUSE_OBSERVATION_FAILED,
    CAUSE_OBSERVER_UNAVAILABLE,
    AccessReadinessGroupResult,
    AccessReadinessPlan,
    AccessReadinessRequirement,
    ContinuityGroupResult,
    ContinuityRequirement,
    GroupKey,
    ReadinessDependentResult,
    observed_continuity_result,
    observed_group_result,
    unobserved_continuity_result,
    unobserved_group_result,
    unplaced_group_result,
)
from ...domain.enterprise.services.trunk_continuity import (
    CONTINUITY_DEADLINE,
    TrunkContinuityObservation,
    TrunkContinuityRound,
    continuity_facts,
    joined_pairs,
    round_joins,
    trunk_continuity_verdicts,
)

#: Total wait and group ceilings of the legacy profile. The gate carries each
#: remaining allowance into the runtime and rechecks it after every read. A
#: plan with more groups derives its own ceilings from its group count; a
#: plan that fits these keeps exactly these.
READINESS_TOTAL_BUDGET_SECONDS = 120.0
READINESS_MAX_GROUPS = 4
READINESS_GROUP_DEADLINE_SECONDS = 30.0
READINESS_GROUP_MAX_SAMPLES = 31
READINESS_GROUP_INTERVAL_SECONDS = 1.0
READINESS_SAMPLE_CALLS = 6
#: One continuity episode: rounds over every switch of its component.
CONTINUITY_GROUP_DEADLINE_SECONDS = 30.0
CONTINUITY_MAX_ROUNDS = 31
CONTINUITY_INTERVAL_SECONDS = 1.0


#: Episodes one group may take: its own, and at most one narrowed episode.
EPISODES_PER_GROUP = 2


def readiness_limits(plan: AccessReadinessPlan) -> tuple[int, float]:
    """Derive the episode ceiling and total wait one plan may use.

    Every group may take its own full window and one narrowed window, so the
    ceiling is twice the group count and the total is that many windows,
    never less than the legacy values. A plan that fits the legacy ceilings
    gets exactly the legacy ceilings.
    """
    groups = plan.group_count
    return (
        max(READINESS_MAX_GROUPS, EPISODES_PER_GROUP * groups),
        max(
            READINESS_TOTAL_BUDGET_SECONDS,
            EPISODES_PER_GROUP
            * (
                len(plan.requirements) * READINESS_GROUP_DEADLINE_SECONDS
                + len(plan.continuity) * CONTINUITY_GROUP_DEADLINE_SECONDS
            ),
        ),
    )


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


class TrunkContinuityObserver(Protocol):
    """The port one bounded trunk continuity observation needs."""

    def observe_trunk_continuity(
        self,
        switches: Sequence[tuple[str, Sequence[str]]],
        vlan_id: int,
        *,
        settled: Callable[[TrunkContinuityRound], bool],
        remaining_seconds: float,
        max_rounds: int,
        deadline_seconds: float,
        interval_seconds: float,
        sample_calls: int,
    ) -> TrunkContinuityObservation:
        """Read every listed switch per round until `settled` or the window ends."""


class _NarrowedResult:
    """A refused group and the fresh episode about its forwarding subset.

    Each dependent the narrowed episode covered takes that episode's verdict;
    every other dependent keeps the refusal of the first episode. Both
    observations are reported, the narrowed one marked as such.
    """

    def __init__(self, first, second) -> None:
        self.first = first
        self.second = second
        self._narrowed = {item.expectation_id for item in second.dependents}
        narrowed = {item.expectation_id: item for item in second.dependents}
        self.dependents = tuple(
            narrowed.get(item.expectation_id, item) for item in first.dependents
        )

    def source(self, expectation_id: str):
        """Return the observation whose verdict one dependent takes."""
        return self.second if expectation_id in self._narrowed else self.first


_ObservedResult = AccessReadinessGroupResult | ContinuityGroupResult
_GroupResult = _ObservedResult | _NarrowedResult


class ServiceAccessReadinessGate:
    """Decide, once per group, whether its dependent requests may run."""

    def __init__(
        self,
        plan: AccessReadinessPlan,
        observer: AccessForwardingObserver | None,
        *,
        clock: Callable[[], float],
        device_names: Mapping[str, str] | None = None,
        total_budget_seconds: float | None = None,
        max_groups: int | None = None,
        continuity_observer: TrunkContinuityObserver | None = None,
    ) -> None:
        """Bind the gate to one derived plan without observing anything yet."""
        derived_groups, derived_seconds = readiness_limits(plan)
        self._plan = plan
        self._observer = observer
        self._continuity_observer = continuity_observer
        self._clock = clock
        self._device_names = dict(device_names or {})
        self._total_budget_seconds = float(
            derived_seconds if total_budget_seconds is None else total_budget_seconds
        )
        self._max_groups = int(derived_groups if max_groups is None else max_groups)
        self._started: float | None = None
        self._observed_groups = 0
        self._results: dict[GroupKey, _GroupResult] = {}
        self._superseded: list[_GroupResult] = []
        self._revisions: dict[GroupKey, int] = {}
        #: Observer calls per group identity; the n-th is episode `ordinal` n.
        self._episodes: dict[GroupKey, int] = {}
        #: Per observation, keyed by the identity of the result object the
        #: gate keeps for the rest of the invocation, the expectations it
        #: decided and the group revision each decision was taken at.
        self._decided: dict[int, dict[str, int]] = {}
        self._verdicts: dict[str, ReadinessDependentResult] = {}
        self._requirements = {item.key: item for item in plan.requirements}
        self._continuity = {item.key: item for item in plan.continuity}
        self._unplaced_recorded = False
        self._consumed = False
        self.observations: list[tuple[str, int, tuple[str, ...]]] = []

    @property
    def limits(self) -> tuple[int, float]:
        """Return the group ceiling and total wait this gate enforces."""
        return self._max_groups, self._total_budget_seconds

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
        if expectation_id in self._verdicts:
            return self._verdicts[expectation_id]
        keys = self._plan.groups_by_expectation.get(expectation_id)
        if not keys:
            unplaced = [
                item
                for item in self._plan.unplaced
                if item.expectation_id == expectation_id
            ]
            if not unplaced:
                return None
            if not self._unplaced_recorded:
                self._unplaced_recorded = True
                for dependent in unplaced_group_result(self._plan.unplaced).dependents:
                    self._verdicts[dependent.expectation_id] = dependent
            return self._verdicts.get(expectation_id)
        verdicts: list[tuple[GroupKey, ReadinessDependentResult]] = []
        for key in keys:
            result = self._group(key)
            if result is None:
                return None
            verdict = _verdict_of(result, expectation_id)
            if verdict is None:
                return None
            # The record names the one observation this decision used and the
            # revision it was taken at, so evidence can bind the permission
            # to that episode and nothing earlier or later.
            source = (
                result.source(expectation_id)
                if isinstance(result, _NarrowedResult)
                else result
            )
            self._decided.setdefault(id(source), {})[expectation_id] = self.revision(
                key
            )
            verdicts.append((key, verdict))
            if not verdict.admitted:
                # The first refusing group decides; groups after it are not
                # observed for this dependent, because nothing they say can
                # admit it. They stay available to other dependents.
                break
        combined = _combined(verdicts, self._label)
        self._verdicts[expectation_id] = combined
        return combined

    def invalidate_devices(self, device_ids: Iterable[str]) -> None:
        """Advance the revision of every group a changed device belongs to.

        The superseded result stays in the report; the next dependent of the
        group observes again, and a verdict already used is not rewritten.
        """
        changed = set(device_ids)
        if not changed:
            return
        for key, result in list(self._results.items()):
            if not changed & self._devices(key):
                continue
            self._superseded.append(result)
            del self._results[key]
            self._revisions[key] = self._revisions.get(key, 0) + 1
            for expectation_id, keys in self._plan.groups_by_expectation.items():
                if key in keys:
                    self._verdicts.pop(expectation_id, None)

    def revision(self, key: GroupKey) -> int:
        """Return how many times one group's memo was invalidated."""
        return self._revisions.get(key, 0)

    def rows(self) -> list[dict[str, object]]:
        """Return the public readiness rows, including groups never reached.

        A group whose dependents were all blocked upstream is reported as
        never observed rather than omitted, so the report says what the run did
        not ask as clearly as what it did. Superseded observations are kept
        ahead of the ones that replaced them.
        """
        recorded: list[_GroupResult] = [*self._superseded, *self._results.values()]
        for requirement in self._plan.requirements:
            if requirement.key not in self._results:
                recorded.append(
                    unobserved_group_result(
                        requirement, cause="dependent_never_became_admissible"
                    )
                )
        for continuity in self._plan.continuity:
            if continuity.key not in self._results:
                recorded.append(
                    unobserved_continuity_result(
                        continuity, cause="dependent_never_became_admissible"
                    )
                )
        if self._plan.unplaced:
            recorded.append(unplaced_group_result(self._plan.unplaced))
        rows: list[dict[str, object]] = []
        for item in recorded:
            if isinstance(item, _NarrowedResult):
                rows.append(self._rendered(item.first))
                second = self._rendered(item.second)
                second["narrowed_from_group"] = True
                rows.append(second)
            else:
                rows.append(self._rendered(item))
        return rows

    def _rendered(self, result: _ObservedResult) -> dict[str, object]:
        """Render one observation, marking the dependents it decided."""
        row = result.as_row()
        decided = self._decided.get(id(result))
        if decided:
            for dependent in row["dependents"]:
                revision = decided.get(dependent["expectation_id"])
                if revision is not None:
                    dependent["decision"] = {"revision": revision}
        return row

    # -- internals ------------------------------------------------------------

    def _label(self, key: GroupKey) -> str:
        if key in self._continuity:
            return f"trunk_continuity:{key[1]}"
        requirement = self._requirements.get(key)
        name = (
            self._device_names.get(
                requirement.switch_device_id, requirement.switch_device_name
            )
            if requirement is not None
            else ""
        )
        return f"access:{name}:{key[1]}"

    def _devices(self, key: GroupKey) -> set[str]:
        if key in self._continuity:
            return set(self._continuity[key].component.switch_device_ids)
        requirement = self._requirements.get(key)
        if requirement is None:
            return set()
        devices = {requirement.switch_device_id}
        for dependent in requirement.dependents:
            devices.update(
                item
                for item in (dependent.client_device_id, dependent.host_device_id)
                if item
            )
        return devices

    def _group(self, key: GroupKey) -> _GroupResult | None:
        if key in self._results:
            return self._results[key]
        if key in self._requirements:
            result: _GroupResult = self._access_group(self._requirements[key])
        elif key in self._continuity:
            result = self._continuity_group(self._continuity[key])
        else:
            return None
        self._results[key] = result
        return result

    def _access_group(self, requirement: AccessReadinessRequirement) -> _GroupResult:
        """Observe one access group, and narrow once if its subset forwarded."""
        first, observation = self._observe(requirement)
        if first.admitted or observation is None:
            return first
        subset = set(forwarding_subset(observation))
        covered = tuple(
            item
            for item in requirement.dependents
            if item.interfaces
            and not item.unresolved_endpoint_ids
            and set(item.interfaces) <= subset
        )
        if not covered or len(subset) >= len(requirement.interfaces):
            return first
        narrowed = replace(
            requirement,
            interfaces=tuple(item for item in requirement.interfaces if item in subset),
            dependents=covered,
        )
        second, _ = self._observe(narrowed, narrowed=True)
        return _NarrowedResult(first, second)

    def _continuity_group(self, requirement: ContinuityRequirement) -> _GroupResult:
        """Observe one component, and narrow once to the pairs it joined."""
        first, observation = self._observe_continuity(requirement)
        if first.status == "admitted" or observation is None:
            return first
        pairs = sorted(
            {
                (item.client_switch_id, item.host_switch_id)
                for item in requirement.dependents
            }
        )
        names = self._switch_names(requirement)
        joined = set(joined_pairs(requirement.component, names, observation, pairs))
        covered = tuple(
            item
            for item in requirement.dependents
            if (item.client_switch_id, item.host_switch_id) in joined
        )
        if not covered or len(joined) >= len(pairs):
            return first
        second, _ = self._observe_continuity(
            replace(requirement, dependents=covered), narrowed=True
        )
        return _NarrowedResult(first, second)

    def _switch_names(self, requirement: ContinuityRequirement) -> dict[str, str]:
        component = requirement.component
        return {
            switch_id: self._device_names.get(switch_id, name)
            for switch_id, name in zip(
                component.switch_device_ids, component.switch_device_names, strict=True
            )
        }

    def _episode(self, key: GroupKey, *, narrowed: bool) -> dict[str, object]:
        """Return the identity of one observer call about to be made for a group.

        The acceptance composition labels that call's dispatches with the same
        per-group ordinal, so a record row names the ledger positions it came
        from.
        """
        self._episodes[key] = self._episodes.get(key, 0) + 1
        return {
            "ordinal": self._episodes[key],
            "revision": self.revision(key),
            "narrowed": narrowed,
        }

    def _admit_group(self) -> tuple[float, str]:
        """Return the remaining total budget, or the reason no group may start."""
        if self._started is None:
            self._started = self._clock()
        if self._observed_groups >= self._max_groups:
            return 0.0, f"{CAUSE_BUDGET_EXHAUSTED}:groups={self._max_groups}"
        remaining = self._total_budget_seconds - (self._clock() - self._started)
        if remaining <= 0:
            return 0.0, (
                f"{CAUSE_BUDGET_EXHAUSTED}:seconds={self._total_budget_seconds:g}"
            )
        return remaining, ""

    def _observe(
        self, requirement: AccessReadinessRequirement, *, narrowed: bool = False
    ) -> tuple[AccessReadinessGroupResult, AccessForwardingObservation | None]:
        """Take one bounded observation episode, or name why it took none."""
        if self._observer is None:
            return (
                unobserved_group_result(requirement, cause=CAUSE_OBSERVER_UNAVAILABLE),
                None,
            )
        remaining, refused = self._admit_group()
        if refused:
            return unobserved_group_result(requirement, cause=refused), None
        group_started = self._clock()
        switch_name = self._device_names.get(
            requirement.switch_device_id, requirement.switch_device_name
        )
        self._observed_groups += 1
        self.observations.append(
            (switch_name, requirement.vlan_id, requirement.interfaces)
        )
        episode = self._episode(requirement.key, narrowed=narrowed)
        result, observation = self._observed(
            requirement, switch_name, remaining, group_started
        )
        return replace(result, episode=episode), observation

    def _observed(
        self,
        requirement: AccessReadinessRequirement,
        switch_name: str,
        remaining: float,
        group_started: float,
    ) -> tuple[AccessReadinessGroupResult, AccessForwardingObservation | None]:
        """Call the observer once and judge what it returned."""
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
            return (
                unobserved_group_result(
                    requirement,
                    cause=f"{CAUSE_OBSERVATION_FAILED}:{type(exc).__name__}",
                ),
                None,
            )
        if self._clock() - group_started >= min(
            remaining, READINESS_GROUP_DEADLINE_SECONDS
        ):
            # The rows remain available, but the product deadline is a closed
            # permission boundary even if an observer returned a late FWD.
            # This is the PARENT bound closing, which is not a claim that the
            # sample was late: a cause the observer already named is more
            # specific than this one, so it is kept.
            observation = replace(
                observation,
                deadline_reached=True,
                deadline_cause=(
                    observation.deadline_cause or CAUSE_GROUP_DEADLINE_REACHED
                ),
            )
        mismatch = _envelope_mismatch(observation, switch_name, requirement)
        if mismatch:
            # A sample was taken, but not of this group. Treating it as a
            # refusal would say something about these ports; it says nothing.
            return (
                unobserved_group_result(
                    requirement,
                    cause=f"{CAUSE_ANSWER_DOES_NOT_MATCH_REQUEST}:{mismatch}",
                ),
                None,
            )
        admission = access_forwarding_admission(observation)
        return (
            observed_group_result(
                requirement,
                admitted=admission.admitted,
                dimension=admission.dimension,
                causes=admission.causes,
                sample=access_forwarding_facts(observation, admission),
                forwarding_interfaces=admission.forwarding_interfaces,
            ),
            observation,
        )

    def _observe_continuity(
        self, requirement: ContinuityRequirement, *, narrowed: bool = False
    ) -> tuple[ContinuityGroupResult, TrunkContinuityObservation | None]:
        """Take one bounded continuity episode over one component."""
        if self._continuity_observer is None:
            return (
                unobserved_continuity_result(
                    requirement, cause=CAUSE_OBSERVER_UNAVAILABLE
                ),
                None,
            )
        remaining, refused = self._admit_group()
        if refused:
            return unobserved_continuity_result(requirement, cause=refused), None
        component = requirement.component
        names = self._switch_names(requirement)
        by_switch = component.interfaces_by_switch()
        switches = [
            (names[switch_id], by_switch.get(switch_id, ()))
            for switch_id in component.switch_device_ids
        ]
        pairs = sorted(
            {
                (item.client_switch_id, item.host_switch_id)
                for item in requirement.dependents
            }
        )
        group_started = self._clock()
        self._observed_groups += 1
        self.observations.append(
            (
                "trunk_continuity",
                component.vlan_id,
                tuple(name for name, _ in switches),
            )
        )
        episode = self._episode(requirement.key, narrowed=narrowed)
        result, observation = self._observed_continuity(
            requirement, names, switches, pairs, remaining, group_started
        )
        return replace(result, episode=episode), observation

    def _observed_continuity(
        self,
        requirement: ContinuityRequirement,
        names: Mapping[str, str],
        switches: Sequence[tuple[str, Sequence[str]]],
        pairs: Sequence[tuple[str, str]],
        remaining: float,
        group_started: float,
    ) -> tuple[ContinuityGroupResult, TrunkContinuityObservation | None]:
        """Call the continuity observer once and judge what it returned."""
        component = requirement.component
        try:
            observation = self._continuity_observer.observe_trunk_continuity(
                switches,
                component.vlan_id,
                settled=lambda round_: round_joins(component, names, round_, pairs),
                remaining_seconds=remaining,
                max_rounds=CONTINUITY_MAX_ROUNDS,
                deadline_seconds=CONTINUITY_GROUP_DEADLINE_SECONDS,
                interval_seconds=CONTINUITY_INTERVAL_SECONDS,
                sample_calls=READINESS_SAMPLE_CALLS,
            )
        except Exception as exc:
            return (
                unobserved_continuity_result(
                    requirement,
                    cause=f"{CAUSE_OBSERVATION_FAILED}:{type(exc).__name__}",
                ),
                None,
            )
        requested = tuple(name for name, _ in switches)
        if (
            observation.vlan_id != component.vlan_id
            or observation.switch_names != requested
        ):
            return (
                unobserved_continuity_result(
                    requirement,
                    cause=f"{CAUSE_ANSWER_DOES_NOT_MATCH_REQUEST}:continuity",
                ),
                None,
            )
        late = self._clock() - group_started >= min(
            remaining, CONTINUITY_GROUP_DEADLINE_SECONDS
        ) and not (observation.rounds and _joined_before_window(observation))
        verdicts = {
            (item.client_switch_id, item.host_switch_id): (
                (False, CONTINUITY_DEADLINE, CAUSE_GROUP_DEADLINE_REACHED)
                if late
                else (item.admitted, item.dimension, item.cause)
            )
            for item in trunk_continuity_verdicts(component, names, observation, pairs)
        }
        return (
            observed_continuity_result(
                requirement,
                verdicts=verdicts,
                sample=continuity_facts(component, names, observation),
            ),
            observation,
        )


def _joined_before_window(observation: TrunkContinuityObservation) -> bool:
    """Whether the deciding round ended inside the observer's own window."""
    deciding = observation.rounds[-1]
    return deciding.complete and not any(
        item.after_deadline for item in deciding.readings
    )


def _verdict_of(
    result: _GroupResult, expectation_id: str
) -> ReadinessDependentResult | None:
    """Return one dependent's verdict from one group, as an access verdict."""
    for dependent in result.dependents:
        if dependent.expectation_id != expectation_id:
            continue
        if isinstance(dependent, ReadinessDependentResult):
            return dependent
        return ReadinessDependentResult(
            expectation_id=dependent.expectation_id,
            service_id=dependent.service_id,
            kind=dependent.kind,
            client_device_id=dependent.client_device_id,
            host_device_id=dependent.host_device_id,
            interfaces=(),
            admitted=dependent.admitted,
            cause=dependent.cause,
        )
    return None


def _combined(
    verdicts: Sequence[tuple[GroupKey, ReadinessDependentResult]],
    label: Callable[[GroupKey], str],
) -> ReadinessDependentResult:
    """Combine one dependent's group verdicts; one group is itself unchanged."""
    if len(verdicts) == 1:
        return verdicts[0][1]
    first = verdicts[0][1]
    refused = next(((key, item) for key, item in verdicts if not item.admitted), None)
    return ReadinessDependentResult(
        expectation_id=first.expectation_id,
        service_id=first.service_id,
        kind=first.kind,
        client_device_id=first.client_device_id,
        host_device_id=first.host_device_id,
        interfaces=tuple(
            dict.fromkeys(
                interface for _, item in verdicts for interface in item.interfaces
            )
        ),
        admitted=refused is None,
        cause="" if refused is None else f"{label(refused[0])}:{refused[1].cause}",
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
