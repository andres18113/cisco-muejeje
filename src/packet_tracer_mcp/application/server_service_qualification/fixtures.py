"""Owned fixture setup, collision handling and bounded readiness.

Fixtures are created through the production physical runtime, a name
collision is never adopted, and the readiness gate is a precondition with
its own read and time bounds rather than a retry budget.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from ...domain.enterprise.models.configuration import (
    ConfigurationPhase,
    SetEndpointStaticAddress,
)
from ...domain.enterprise.models.execution import MutationDisposition, PostconditionFact
from ...domain.enterprise.models.physical_deployment import PhysicalWorkspaceObservation
from ...domain.enterprise.models.service_plan import (
    EnableHttpService,
    EnableHttpsService,
    ServicePhase,
    ServiceType,
)
from ...domain.enterprise.models.service_qualification import (
    Q1_SERVER,
    READINESS_DEADLINE_SECONDS,
    READINESS_MAX_READS,
    DiagnosticPrecondition,
    MeasurementStatus,
)
from ...domain.enterprise.services.service_qualification_evidence import (
    ProbeReading,
    assess_port_readiness,
)
from .contracts import bounded
from .execution import NOT_SELECTED, Execution
from .operation_budget import LedgerPhase, OperationRefused


def setup_fixtures(execution: Execution) -> bool:
    """Create the stage fixtures through the production physical runtime."""
    if execution.stopped:
        return False
    # Setup is the first effect of the run and it happens before any
    # measurement announces itself, so the receiver is decided here too and
    # not only at each dispatch inside the loops below.
    if not execution.live_authority("fixtures:setup"):
        return False
    if not execution.run.transition("fixtures:started"):
        execution.stop("persistence:record_not_advanced")
        return False
    ledger = execution.ledger
    ledger.enter(LedgerPhase.SETUP)
    record = execution.record
    try:
        for plan in execution.devices:
            fixture = next(item for item in record.fixtures if item.name == plan.name)
            with ledger.effect_of(f"create:{plan.name}"):
                result = execution.physical.ensure_device(plan)
            fixture.creation = result.disposition.value
            fixture.detail = bounded(result.message)
            if result.disposition is MutationDisposition.NO_OP:
                # An existing object with this name is a collision, never
                # permission to adopt or remove it.
                execution.stop(f"fixture_collision:{plan.name}")
                return False
            execution.removal_candidates.append(plan)
            fixture.owned = result.disposition is MutationDisposition.CHANGED
            if result.disposition is MutationDisposition.UNKNOWN:
                execution.stop(f"outcome_unknown:create:{plan.name}")
                return False
            if result.disposition is not MutationDisposition.CHANGED:
                execution.stop(f"fixture_not_created:{plan.name}")
                return False
        for index, link in enumerate(execution.links, start=1):
            with ledger.effect_of(f"create:link:{index}"):
                result = execution.physical.ensure_link(link)
            if result.disposition is MutationDisposition.UNKNOWN:
                execution.stop(f"outcome_unknown:link:{index}")
                return False
            if result.disposition is not MutationDisposition.CHANGED:
                execution.stop(f"link_not_created:{index}:{result.message}")
                return False
        with ledger.purpose_of("read:fixture_identity"):
            observed = execution.physical.observe_workspace()
    except OperationRefused as exc:
        execution.stop(f"operation_refused:{exc.reason}")
        return False
    identity_error = _fixture_identity_error(execution, observed)
    if identity_error:
        execution.stop(identity_error)
        return False
    if not execution.run.transition("fixtures:ready"):
        execution.stop("persistence:record_not_advanced")
        return False
    execution.fixtures_ready = True
    # The identity read above proved the exact fixture names and models under
    # the bound session, which is what "correct subject" means operationally.
    execution.establish(DiagnosticPrecondition.SUBJECT_SESSION)
    return True


def _fixture_identity_error(
    execution: Execution, observed: PhysicalWorkspaceObservation
) -> str:
    if not observed.observed:
        return "fixture_identity_unobserved:" + observed.message
    expected = {plan.name: plan.model for plan in execution.devices}
    semantic = observed.semantic_devices
    names = [item.name for item in semantic]
    foreign = sorted(set(names) - set(expected))
    if foreign:
        return "foreign_device_observed:" + ",".join(foreign)
    for name, model in expected.items():
        matches = [item for item in semantic if item.name == name]
        if len(matches) != 1 or matches[0].model != model:
            return f"fixture_identity_mismatch:{name}"
    return ""


def endpoint_action_id(execution: Execution, name: str) -> str:
    """Return the exact E5 action id this stage dispatches for one fixture.

    The id names the stage, so a D-WEB forwarding selection can bind to the
    action the run actually applied rather than to a Q1 id it never wrote.
    """
    return f"{execution.definition.stage.value.lower()}-e5-{name}"


def configure_web_fixture(execution: Execution) -> bool:
    """Address the endpoints through E5 and enable HTTP/HTTPS through E6.

    Shared by Q1 and by D-WEB, which measures the same fixture and needs the
    same two effects before it can ask anything about them. The action and
    service ids carry the stage's own name, so nothing in either record claims
    to be the other's row.
    """
    ledger = execution.ledger
    scope = execution.definition.stage.value.lower()
    fixtures = {item.name: item for item in execution.definition.fixtures}
    endpoints = [
        SetEndpointStaticAddress(
            id=endpoint_action_id(execution, name),
            phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
            device_id=name,
            device_name=name,
            site_id=scope,
            interface="FastEthernet0",
            ipv4=fixture.ipv4,
            netmask=fixture.netmask,
            gateway="",
            dns_server=fixture.dns_server or None,
            segment_id=scope,
        )
        for name, fixture in fixtures.items()
        if fixture.ipv4
    ]
    server = fixtures[Q1_SERVER]
    common = {
        "phase": ServicePhase.ENABLE,
        "host_device_id": server.name,
        "host_device_name": server.name,
        "host_model": server.model,
        "site_id": scope,
        "required_capability": f"qualification:{execution.definition.stage.value}",
    }
    services = [
        EnableHttpService(
            id=f"{scope}-e6-http",
            service_id=f"{scope}-http",
            service_type=ServiceType.HTTP,
            **common,
        ),
        EnableHttpsService(
            id=f"{scope}-e6-https",
            service_id=f"{scope}-https",
            service_type=ServiceType.HTTPS,
            **common,
        ),
    ]
    try:
        with ledger.effect_of("apply:e5_endpoints"):
            e5 = execution.run.boundaries.configuration_runtime(
                execution.bound
            ).apply_actions(endpoints)
    except OperationRefused as exc:
        execution.stop(f"operation_refused:{exc.reason}")
        return False
    # E5 is classified before the E6 batch is built. The enables used to be
    # dispatched first and the flag read afterwards, so a refusal could not
    # prevent the effects it was refusing.
    e5_error = _incomplete_batch(
        [item.id for item in endpoints], [item.action_id for item in e5]
    )
    execution.e5_accepted = (
        bool(endpoints) and not e5_error and all(item.applied for item in e5)
    )
    execution.record.limitations.append(
        "e5_endpoint_dispatch:"
        + ("accepted" if execution.e5_accepted else e5_error or "unknown")
    )
    if not execution.e5_accepted:
        execution.stop(f"outcome_unknown:e5_endpoints{e5_error and ':' + e5_error}")
        return False
    try:
        with ledger.effect_of("apply:e6_enable_http_https"):
            e6 = execution.run.boundaries.service_runtime(
                execution.bound
            ).apply_actions(services)
    except OperationRefused as exc:
        execution.stop(f"operation_refused:{exc.reason}")
        return False
    e6_error = _incomplete_batch(
        [item.id for item in services], [item.action_id for item in e6]
    )
    enabled = not e6_error and all(
        item.applied and item.postcondition is PostconditionFact.SATISFIED
        for item in e6
    )
    if not enabled:
        execution.stop(f"fixture_services_not_enabled{e6_error and ':' + e6_error}")
        return False
    return execution.run.transition("fixtures:configured")


@dataclass(frozen=True)
class Readiness:
    """What the bounded readiness gate observed before a network attempt."""

    ready: bool
    reads: int
    elapsed_seconds: float
    reason: str
    first: dict[str, Any] = field(default_factory=dict)
    last: dict[str, Any] = field(default_factory=dict)

    def facts(self) -> dict[str, Any]:
        """Return the record shape: the bounds, the reason and both samples."""
        return {
            "ready": self.ready,
            "reads": self.reads,
            "max_reads": READINESS_MAX_READS,
            "deadline_seconds": READINESS_DEADLINE_SECONDS,
            "elapsed_seconds": self.elapsed_seconds,
            "reason": self.reason,
            "first": self.first,
            "last": self.last,
        }


def await_readiness(
    execution: Execution,
    endpoints: Sequence[tuple[str, str]],
    read: Callable[[float], ProbeReading],
    *,
    purpose: str,
) -> Readiness:
    """Read the exact fixture endpoints until one complete sample is ready.

    The gate is a precondition, not a retry budget: at most
    `READINESS_MAX_READS` aggregate reads inside a
    `READINESS_DEADLINE_SECONDS` monotonic window, itself capped by whatever
    the stage still has outside its finalization reserve, and the first
    complete ready sample ends it. Between two reads it waits only while it is
    still allowed to read again, so nothing sleeps unconditionally and nothing
    spins. A gate that never becomes ready is a readiness result: no client is
    created and no acquisition is requested from it.
    """
    ledger = execution.ledger
    started = ledger.elapsed()
    deadline = started + READINESS_DEADLINE_SECONDS
    first: dict[str, Any] = {}
    last: dict[str, Any] = {}
    reads = 0
    reason = "readiness_not_attempted"
    while reads < READINESS_MAX_READS:
        if execution.stopped:
            reason = f"stopped:{execution.record.primary_failure}"
            break
        if not ledger.can_afford(1):
            reason = "readiness_budget_exhausted"
            break
        if ledger.elapsed() >= deadline:
            reason = "readiness_deadline_reached"
            break
        local_remaining = max(0.0, deadline - ledger.elapsed())
        _operations, stage_remaining = ledger.allowance()
        timeout = min(local_remaining, max(0.0, stage_remaining))
        if timeout <= 0:
            reason = "readiness_budget_exhausted"
            break
        with ledger.purpose_of(purpose):
            sample = assess_port_readiness(read(timeout), endpoints)
        reads += 1
        last = dict(sample.facts)
        if reads == 1:
            first = dict(sample.facts)
        if ledger.elapsed() > deadline:
            reason = "readiness_deadline_reached_after_read"
            break
        if sample.ready:
            reason = ""
            break
        reason = sample.cause
        remaining = deadline - ledger.elapsed()
        if reads < READINESS_MAX_READS and remaining > 0:
            ledger.wait(
                min(execution.run.boundaries.settle_seconds, remaining),
                execution.run.boundaries.sleep,
            )
    return Readiness(
        not reason and reads > 0,
        reads,
        round(ledger.elapsed() - started, 3),
        reason,
        first,
        last,
    )


def _incomplete_batch(requested: Sequence[str], reported: Sequence[str]) -> str:
    """Name why a runtime batch cannot be read as complete, or return `""`.

    A short result set is an unknown outcome, not a success for the rows that
    did come back: `all()` over two rows says nothing about a third action
    nobody reported on.
    """
    if len(reported) != len(requested) or sorted(reported) != sorted(requested):
        return f"incomplete_result_set:{len(reported)}_of_{len(requested)}"
    return ""


def fixture_endpoints(execution: Execution) -> tuple[tuple[str, str], ...]:
    """Return both ends of every fixture link, in declaration order."""
    return tuple(
        endpoint
        for link in execution.definition.links
        for endpoint in ((link.device_a, link.port_a), (link.device_b, link.port_b))
    )


def diagnostic_start(execution: Execution) -> bool:
    """Admit one diagnostic stage and omit what its authority did not select.

    An unselected measurement is OMITTED with its reason, not silently left
    NOT_RUN: the record has to say that the authority scoped it out rather
    than that the run failed to reach it. The stage still needs the whole
    selected path to afford itself before the first fixture is created.
    """
    definition = execution.definition
    selected_experiments = set(
        definition.experiments_of_steps(execution.authorized_steps)
        if definition.steps
        else [item.id for item in definition.experiments]
    )
    for item in execution.record.measurements:
        # A measurement the stage already omits keeps its own reason: the
        # authority did not scope it out, the profile never runs it.
        if (
            item.experiment_id not in selected_experiments
            and item.status is not MeasurementStatus.OMITTED
        ):
            item.status = MeasurementStatus.OMITTED
            item.reason = NOT_SELECTED
    planned = sum(
        definition.experiment(item).planned_operations for item in selected_experiments
    )
    required = [
        item.id
        for item in definition.experiments
        if item.required and item.id in selected_experiments
    ]
    if not execution.ledger.can_afford(definition.fixture_operations + planned):
        execution.not_run(required, f"budget_insufficient_for:{definition.stage.value}")
        execution.stop(f"budget:{definition.stage.value}")
        return False
    if not setup_fixtures(execution):
        execution.not_run(required, "fixture_setup_failed")
        return False
    return True
