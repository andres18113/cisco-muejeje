"""Local admission, boundary resolution, channel lifecycle and dispatch.

One invocation is admitted locally, its campaign claim is held, its product
contract is resolved, one transport is opened for the authorized channel,
the build and workspace are read before any effect, the stage's workflow runs
through an explicit handler, and finalization always follows an effect.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ...domain.enterprise.models.physical_deployment import PhysicalWorkspaceObservation
from ...domain.enterprise.models.service_qualification import (
    EFFECT_GATE_LIMIT,
    LOCAL_OBSERVATION_TIMEOUT_SECONDS,
    Q3_FL_STAGES,
    Q3_NATIVE_STAGES,
    SP1_ROUTED_STAGES,
    SP2_STAGES,
    DiagnosticLifecycleObservation,
    ExecutionMode,
    MeasurementStatus,
    QualificationOutcome,
    QualificationRecord,
    QualificationRefusal,
    QualificationRequest,
    QualificationStage,
    RefusalKind,
    RefusalSubject,
    RepositoryIdentity,
    StageDefinition,
    TransportIdentity,
    refusal,
    repository_refusals,
    request_refusals,
    stage_definition,
)
from ...domain.models.plans import DevicePlan, LinkPlan
from ..ports.service_qualification import OpenedTransport
from ..ports.service_run_record import RunRecordPersistenceError
from ..use_cases.deploy_enterprise_topology import (
    PhysicalTopologyRuntime,
    disposable_workspace_error,
)
from .campaign_authority import CampaignHold, diagnostic_admission
from .contracts import (
    IsolationObservation,
    Q3ProductContract,
    QualificationBoundaries,
    QualificationCancelled,
    QualificationResult,
    bounded,
    refused_result,
)
from .execution import NOT_SELECTED, Execution
from .finalization import finalize, observe_terminal, release_campaign_claim
from .ledgered_transport import LedgeredTransport
from .operation_budget import OperationLedger
from .record_lifecycle import Run, initial_record
from .workflows.dhcp_diagnostics import run_d_dhcp
from .workflows.engine import run_q0
from .workflows.fastloop import run_q3_fastloop
from .workflows.https_page import run_q1
from .workflows.native_pool import (
    run_q3_native_policy,
    run_q3_native_probe,
    run_q3_native_serve,
    run_q3_native_size,
    run_q3_native_stability,
)
from .workflows.native_product import run_q3_native_product
from .workflows.original_dhcp import run_q3
from .workflows.sp1_routed_product import run_sp1_routed_product
from .workflows.sp2_mixed_product import run_sp2_mixed_product
from .workflows.sp2_remote_relay import run_sp2_remote_relay
from .workflows.web_diagnostics import run_d_web


@dataclass(frozen=True)
class _LocalAdmission:
    """What local admission resolved and observed before any channel exists."""

    definition: StageDefinition
    devices: tuple[DevicePlan, ...]
    links: tuple[LinkPlan, ...]
    isolation: IsolationObservation
    repository: RepositoryIdentity


def run_qualification(
    request: QualificationRequest,
    boundaries: QualificationBoundaries,
    *,
    experimental_capabilities: frozenset[str],
) -> QualificationResult:
    """Run one authorized qualification stage, or refuse it before any effect.

    `experimental_capabilities` is the runner-only scope of unqualified
    behaviors the probes may exercise. An experiment that needs a capability
    outside it does not run. Nothing else in the repository reads this scope.
    """
    admitted = _local_admission(request, boundaries)
    if isinstance(admitted, QualificationResult):
        return admitted
    definition = admitted.definition
    diagnostic_lifecycle: DiagnosticLifecycleObservation | None = None
    hold = CampaignHold(boundaries.campaign_coordinator)
    try:
        if definition.profile_id:
            refusals, diagnostic_lifecycle = diagnostic_admission(
                definition, request.authorization, boundaries, hold
            )
            if refusals:
                return refused_result(refusals, claim_release=hold.finalize())
        return _with_campaign_claim(
            request,
            boundaries,
            definition,
            admitted.devices,
            admitted.links,
            admitted.isolation,
            admitted.repository,
            experimental_capabilities,
            diagnostic_lifecycle=diagnostic_lifecycle,
            hold=hold,
        )
    except KeyboardInterrupt as exc:
        raise QualificationCancelled(exc, hold.finalize()) from exc
    finally:
        # Every ordinary path finalizes the hold before returning its result.
        # This remains the idempotent safety net for an unexpected exception.
        hold.finalize()


def _local_admission(
    request: QualificationRequest, boundaries: QualificationBoundaries
) -> _LocalAdmission | QualificationResult:
    """Decide everything that needs no channel, in order, refusing at the first.

    The request rule, the stage's fixture plans, the typed execution mode,
    process isolation, the repository identity and the campaign authority,
    which waives exactly the upstream-publication rule for the attempt it
    names. A refusal here has touched nothing.
    """
    refusals = request_refusals(request)
    if refusals:
        return refused_result(refusals)
    definition = stage_definition(request.stage)
    if definition is None:  # pragma: no cover - excluded by request_refusals
        return refused_result([refusal(RefusalKind.MALFORMED, RefusalSubject.STAGE)])
    try:
        devices, links = boundaries.fixture_plans(definition)
    except (KeyError, ValueError) as exc:
        return refused_result(
            [refusal(RefusalKind.MALFORMED, RefusalSubject.FIXTURE, bounded(exc))]
        )
    if tuple(plan.name for plan in devices) != definition.fixture_names:
        return refused_result(
            [
                refusal(
                    RefusalKind.MISMATCH,
                    RefusalSubject.FIXTURE,
                    "Resolved fixture plans are not the stage fixtures.",
                )
            ]
        )

    if type(boundaries.execution_mode) is not ExecutionMode:
        return refused_result(
            [
                refusal(
                    RefusalKind.MALFORMED,
                    RefusalSubject.EXECUTION,
                    "Execution mode must be a typed boundary value.",
                )
            ]
        )
    isolation = _isolation(boundaries)
    if not isolation.isolated:
        kind = (
            RefusalKind.UNOBSERVABLE
            if isolation.state == "INDETERMINATE"
            else RefusalKind.NOT_PERMITTED
        )
        return refused_result(
            [
                refusal(
                    kind,
                    RefusalSubject.PROCESS_ISOLATION,
                    f"{isolation.state}: {isolation.detail}",
                )
            ]
        )
    repository = _repository(boundaries)
    authorization = request.authorization
    refusals = repository_refusals(
        repository,
        request.expected_head,
        authorization.tree if authorization is not None else "",
    )
    authority = boundaries.campaign_source_authority
    if (
        boundaries.execution_mode is ExecutionMode.LIVE
        and definition.stage
        in (
            *Q3_FL_STAGES,
            *Q3_NATIVE_STAGES,
            *SP1_ROUTED_STAGES,
            *SP2_STAGES,
        )
        and authority is None
    ):
        return refused_result(
            [
                refusal(
                    RefusalKind.MISSING,
                    RefusalSubject.AUTHORIZATION,
                    "This experimental stage requires its campaign authority.",
                )
            ]
        )
    if authority is not None:
        if not authority.permits(request, repository):
            return refused_result(
                [
                    refusal(
                        RefusalKind.MISMATCH,
                        RefusalSubject.AUTHORIZATION,
                        "The campaign authority does not name this attempt, "
                        "authorization, HEAD and tree.",
                    )
                ]
            )
        # Exactly one rule is waived, and only for the attempt it names.
        refusals = tuple(
            item
            for item in refusals
            if item.subject is not RefusalSubject.REPOSITORY_UPSTREAM
        )
    if refusals:
        return refused_result(refusals)
    return _LocalAdmission(definition, devices, links, isolation, repository)


def _with_campaign_claim(
    request: QualificationRequest,
    boundaries: QualificationBoundaries,
    definition: StageDefinition,
    devices: tuple[DevicePlan, ...],
    links: tuple[LinkPlan, ...],
    isolation: IsolationObservation,
    repository: RepositoryIdentity,
    experimental_capabilities: frozenset[str],
    *,
    diagnostic_lifecycle: DiagnosticLifecycleObservation | None,
    hold: CampaignHold,
) -> QualificationResult:
    """Run the admitted part of one invocation while its campaign claim is held."""
    moment = boundaries.now()
    run_id = boundaries.new_run_id(moment)
    product_contract = _product_contract(request, boundaries, definition, run_id)
    if isinstance(product_contract, QualificationRefusal):
        return refused_result([product_contract], claim_release=hold.finalize())
    record = initial_record(
        request,
        definition,
        boundaries,
        isolation,
        repository,
        experimental_capabilities,
        moment=moment,
        run_id=run_id,
        diagnostic_lifecycle=diagnostic_lifecycle,
    )
    record.links = [
        {
            "device_a": item.device_a,
            "port_a": item.port_a,
            "device_b": item.device_b,
            "port_b": item.port_b,
        }
        for item in links
    ]
    try:
        record_path = boundaries.record_store.begin(record)
    except RunRecordPersistenceError as exc:
        return refused_result(
            [refusal(RefusalKind.NOT_PERMITTED, RefusalSubject.RECORD, bounded(exc))],
            claim_release=hold.finalize(),
        )
    run = Run(record, boundaries, record_path, diagnostic_lifecycle, hold)
    return _on_the_channel(
        run,
        request,
        definition,
        devices,
        links,
        experimental_capabilities,
        product_contract,
        hold,
    )


def _product_contract(
    request: QualificationRequest,
    boundaries: QualificationBoundaries,
    definition: StageDefinition,
    run_id: str,
) -> Q3ProductContract | QualificationRefusal | None:
    """Compose the stage's product contract, or name why it cannot be composed.

    Only the reviewed exact build composes a product contract, and a
    composition that raises is a malformed fixture. A stage that needs no
    product contract resolves to None. The stage families are tried in the
    order that makes the more specific stage win over its family set.
    """
    stage = definition.stage
    build = request.packet_tracer_build
    required = boundaries.q3_required_build
    exact = bool(required) and build == required
    if stage in SP1_ROUTED_STAGES:
        sp1 = boundaries.sp1_product_contract
        if not exact or sp1 is None:
            return _build_refusal("SP-1 has no reviewed exact-build contract.")
        return _composed(
            "sp1_product_contract",
            lambda: sp1(build, run_id, definition.selected_clients),
        )
    if stage is QualificationStage.Q3_NATIVE_PRODUCT:
        native = boundaries.native_product_contract
        if (
            not exact
            or native is None
            or (
                definition.profile_version == "4"
                and boundaries.execution_mode is ExecutionMode.LIVE
                and boundaries.native_public_product_entry is None
            )
        ):
            return _build_refusal(
                "Native product has no reviewed exact-build contract."
            )
        return _composed("native_product_contract", lambda: native(build, run_id))
    if stage is QualificationStage.SP2_REMOTE_RELAY:
        relay = boundaries.sp2_remote_relay_contract
        if not exact or relay is None:
            return _build_refusal("SP-2 remote relay has no exact-build contract.")
        return _composed("sp2_remote_relay_contract", lambda: relay(build, run_id))
    if stage in (
        QualificationStage.SP2_MIXED_PRODUCT,
        QualificationStage.SP2_CAPACITY_PRODUCT,
    ):
        mixed = (
            boundaries.sp2_capacity_product_contract
            if stage is QualificationStage.SP2_CAPACITY_PRODUCT
            else boundaries.sp2_mixed_product_contract
        )
        if not exact or mixed is None:
            return _build_refusal("SP-2 mixed product has no exact-build contract.")
        return _composed("sp2_mixed_product_contract", lambda: mixed(build, run_id))
    if stage in (*Q3_FL_STAGES, *Q3_NATIVE_STAGES, *SP2_STAGES):
        dhcp = boundaries.dhcp_product_contract
        if not exact or dhcp is None:
            return _build_refusal(
                "Q3-FL has no reviewed product contract for this build."
            )
        return _composed(
            "dhcp_product_contract",
            lambda: dhcp(build, run_id, definition.dhcp_pool_capacity),
        )
    if stage in (QualificationStage.Q3, QualificationStage.D_DHCP):
        if not required:
            return _build_refusal("The Q3 Packet Tracer build policy is not composed.")
        if build != required:
            return _build_refusal(
                "Q3 is not implemented for the requested Packet Tracer build."
            )
        q3 = boundaries.q3_product_contract
        if q3 is None:
            return refusal(
                RefusalKind.NOT_PERMITTED,
                RefusalSubject.FIXTURE,
                "The executable Q3 product contract is not composed.",
            )
        return _composed("q3_product_contract", lambda: q3(build, run_id))
    return None


def _build_refusal(detail: str) -> QualificationRefusal:
    """Refuse a stage whose exact-build product composition is unavailable."""
    return refusal(RefusalKind.NOT_PERMITTED, RefusalSubject.BUILD, detail)


def _composed(
    label: str, compose: Callable[[], Q3ProductContract]
) -> Q3ProductContract | QualificationRefusal:
    """Compose one product contract; a composition that raises is malformed."""
    try:
        return compose()
    except Exception as exc:
        return refusal(
            RefusalKind.MALFORMED,
            RefusalSubject.FIXTURE,
            f"{label}:{type(exc).__name__}:{bounded(exc)}",
        )


def _on_the_channel(
    run: Run,
    request: QualificationRequest,
    definition: StageDefinition,
    devices: tuple[DevicePlan, ...],
    links: tuple[LinkPlan, ...],
    experimental_capabilities: frozenset[str],
    product_contract: Q3ProductContract | None,
    hold: CampaignHold,
) -> QualificationResult:
    """Open the one authorized channel, run the admitted invocation, close it."""
    record = run.record
    boundaries = run.boundaries
    opened: OpenedTransport | None = None
    try:
        try:
            opened = boundaries.open_transport(request.channel)
        except Exception as exc:
            opened = OpenedTransport(
                request.channel, None, False, f"open_failed:{type(exc).__name__}"
            )
        record.transport = TransportIdentity(
            channel=opened.channel, fixed_at=boundaries.now(), liveness=opened.detail
        )
        if not opened.live or opened.transport is None:
            return run.refuse_after_contact(
                refusal(
                    RefusalKind.UNOBSERVABLE,
                    RefusalSubject.TRANSPORT,
                    opened.detail or "The authorized channel is not live.",
                )
            )
        ledger = OperationLedger(
            max_operations=definition.budget.max_operations,
            max_seconds=definition.budget.max_seconds,
            clock=boundaries.clock,
        )
        run.ledger = ledger
        bound = LedgeredTransport(
            ledger, opened.transport, boundaries.sleep, boundaries.clock
        )
        return _admitted(
            run,
            request,
            definition,
            devices,
            links,
            bound,
            experimental_capabilities,
            product_contract,
            hold=hold,
        )
    finally:
        if opened is not None and opened.transport is not None:
            try:
                boundaries.close_transport(opened)
            except Exception as exc:
                record.secondary_failures.append(
                    f"transport_close:{type(exc).__name__}"
                )


def _isolation(boundaries: QualificationBoundaries) -> IsolationObservation:
    try:
        return boundaries.isolation()
    except Exception as exc:
        return IsolationObservation(False, "INDETERMINATE", type(exc).__name__)


def _repository(boundaries: QualificationBoundaries) -> RepositoryIdentity:
    try:
        return boundaries.repository()
    except Exception as exc:
        return RepositoryIdentity(error=f"repository_read_failed:{type(exc).__name__}")


def _admitted(
    run: Run,
    request: QualificationRequest,
    definition: StageDefinition,
    devices: tuple[DevicePlan, ...],
    links: tuple[LinkPlan, ...],
    bound: LedgeredTransport,
    capabilities: frozenset[str],
    product_contract: Q3ProductContract | None = None,
    *,
    hold: CampaignHold | None = None,
) -> QualificationResult:
    """Read the build and workspace, run the stage's workflow, then finalize."""
    admitted = _read_admission(run, request, definition, bound)
    if isinstance(admitted, QualificationResult):
        return admitted
    physical, baseline = admitted
    execution = _start_execution(
        run,
        request,
        definition,
        devices,
        links,
        bound,
        physical,
        baseline,
        capabilities,
        product_contract,
        hold,
    )
    cancelled = _run_to_finalization(execution)
    record = run.record
    run.complete(
        QualificationOutcome.COMPLETED
        if _completed(record)
        else QualificationOutcome.STOPPED
    )
    if cancelled is not None:
        raise cancelled
    return QualificationResult(
        outcome=record.outcome,
        record=record,
        record_path=run.record_path,
        claim_release=execution.hold.release_fact,
    )


def _read_admission(
    run: Run,
    request: QualificationRequest,
    definition: StageDefinition,
    bound: LedgeredTransport,
) -> tuple[PhysicalTopologyRuntime, PhysicalWorkspaceObservation] | QualificationResult:
    """Read the executable build and the workspace before any effect.

    Returns the physical runtime and the workspace baseline once both are
    admitted, the reserve is set and the write-ahead record has advanced, or
    the refusal result that contact produced without any effect.
    """
    record = run.record
    ledger = run.ledger
    assert ledger is not None
    boundaries = run.boundaries
    try:
        with ledger.purpose_of("read:executable_build"):
            build = boundaries.build_reader(bound.send_and_wait).read()
    except Exception as exc:
        return run.refuse_after_contact(
            refusal(
                RefusalKind.UNOBSERVABLE,
                RefusalSubject.EXECUTABLE_BUILD,
                f"build_read_failed:{type(exc).__name__}",
            )
        )
    record.environment.observed_build = build.version
    record.environment.build_reader_id = build.reader_id
    record.environment.build_reader_sha256 = build.reader_sha256
    record.environment.build_observation = build.excerpt
    record.environment.build_reason = build.reason
    record.admission_reads.append(f"build:{build.version or build.reason}")
    if not build.available:
        return run.refuse_after_contact(
            refusal(
                RefusalKind.UNOBSERVABLE, RefusalSubject.EXECUTABLE_BUILD, build.reason
            )
        )
    if build.version != request.packet_tracer_build:
        return run.refuse_after_contact(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.EXECUTABLE_BUILD,
                f"Observed {build.version!r}; authorized {request.packet_tracer_build!r}.",
            )
        )
    physical = boundaries.physical_runtime(bound.send_and_wait)
    try:
        with ledger.purpose_of("read:workspace_baseline"):
            baseline = physical.observe_workspace()
    except Exception as exc:
        return run.refuse_after_contact(
            refusal(
                RefusalKind.UNOBSERVABLE,
                RefusalSubject.WORKSPACE,
                f"workspace_read_failed:{type(exc).__name__}",
            )
        )
    record.workspace_baseline = baseline.compact_summary()
    record.admission_reads.append(
        "workspace:"
        + (
            f"semantic={len(baseline.semantic_devices)},links={len(baseline.links)},"
            f"engine_managed={len(baseline.backend_managed_devices)}"
            if baseline.observed
            else "unobserved"
        )
    )
    workspace_error = disposable_workspace_error(baseline)
    if workspace_error:
        return run.refuse_after_contact(
            refusal(
                (
                    RefusalKind.UNOBSERVABLE
                    if not baseline.observed
                    else RefusalKind.NOT_PERMITTED
                ),
                RefusalSubject.WORKSPACE,
                workspace_error,
            )
        )
    if baseline.backend_managed_devices:
        record.limitations.append(
            "engine_managed_objects_in_baseline:"
            + ",".join(item.name for item in baseline.backend_managed_devices)
        )
    ledger.reserve(definition.reserve_operations, definition.budget.reserve_seconds)
    if not run.transition("admitted"):
        # Nothing was effected yet, so this remains a refusal.
        return run.refuse_after_contact(
            refusal(
                RefusalKind.NOT_PERMITTED,
                RefusalSubject.RECORD,
                "The write-ahead record could not advance before the first effect.",
            )
        )
    return physical, baseline


def _start_execution(
    run: Run,
    request: QualificationRequest,
    definition: StageDefinition,
    devices: tuple[DevicePlan, ...],
    links: tuple[LinkPlan, ...],
    bound: LedgeredTransport,
    physical: PhysicalTopologyRuntime,
    baseline: PhysicalWorkspaceObservation,
    capabilities: frozenset[str],
    product_contract: Q3ProductContract | None,
    hold: CampaignHold | None,
) -> Execution:
    """Build the invocation's one mutable context over its admitted ledger."""
    record = run.record
    boundaries = run.boundaries
    bound.observation_context = {
        "backend": "packet_tracer",
        "source_sha": record.source.executed_sha,
        "source_tree": record.source.executed_tree,
        "clean": record.source.clean,
        "build": record.environment.observed_build,
        "channel": request.channel,
    }
    nonce = boundaries.new_nonce()
    hold = hold if hold is not None else CampaignHold()
    execution = Execution(
        run=run,
        nonce=nonce,
        definition=definition,
        devices=devices,
        links=links,
        bound=bound,
        physical=physical,
        baseline=baseline,
        channel=request.channel,
        capabilities=capabilities,
        probes=boundaries.probes(bound, record.run_id, nonce),
        product_contract=product_contract,
        claim=hold.claim,
        hold=hold,
        authorized_steps=(
            tuple(request.authorization.step_ids)
            if definition.steps and request.authorization is not None
            else ()
        ),
    )
    # Constructing the execution bound this ledger's effect guard, so from
    # here on no dispatch inside an effect scope reaches the channel without
    # that decision.
    if definition.profile_id:
        record.limitations.append(EFFECT_GATE_LIMIT)
        record.limitations.append(
            f"local_process_observation_bounded_seconds:{LOCAL_OBSERVATION_TIMEOUT_SECONDS}"
        )
    return execution


def _run_to_finalization(execution: Execution) -> BaseException | None:
    """Run the stage's workflow, then always take its terminal reading and finalize.

    Returns the cancellation to re-raise once the record is complete, or None.
    """
    record = execution.record
    cancelled: BaseException | None = None
    try:
        STAGE_HANDLERS[execution.definition.stage](execution)
    except KeyboardInterrupt as exc:
        execution.cancelled = True
        execution.stop("cancelled")
        cancelled = exc
    except Exception as exc:
        execution.interrupt_in_flight(f"exception:{type(exc).__name__}")
        execution.stop(f"exception:{type(exc).__name__}:{bounded(exc)}")
    finally:
        # The terminal read-only observation belongs to finalization, not to
        # the sequence that may have raised out of the middle of itself. Every
        # exit that reaches cleanup reaches this first, so the last reading is
        # always taken before the first deletion.
        terminal_cancellation = observe_terminal(execution)
        if terminal_cancellation is not None and cancelled is None:
            cancelled = terminal_cancellation
        try:
            finalize(execution)
        except Exception as exc:
            # A finalization defect is secondary: the record still completes
            # with the primary outcome and whatever finalization established.
            record.secondary_failures.append(
                f"finalization:exception:{type(exc).__name__}"
            )
        # The campaign claim is held through finalization and released before
        # the record is completed, so a lock that stayed held is a fact this
        # record carries rather than one that happens after it.
        release_campaign_claim(execution)
    return cancelled


def _completed(record: QualificationRecord) -> bool:
    """Return whether a finalized record completes its stage."""
    return (
        not record.primary_failure
        and record.restoration_proven
        and not record.coordination_residue
        and all(
            item.status is MeasurementStatus.RAN
            for item in record.measurements
            # A measurement the authority deliberately left out of its step
            # selection is not a measurement this run failed to make. Every
            # other omission still keeps the stage from completing.
            if item.required and item.reason != NOT_SELECTED
        )
    )


#: The workflow each executable stage runs, one explicit handler per stage.
#: A declarative stage is refused by request admission before any record
#: exists, so it has no handler.
STAGE_HANDLERS: Mapping[QualificationStage, Callable[[Execution], object]] = (
    MappingProxyType(
        {
            QualificationStage.Q0: run_q0,
            QualificationStage.Q1: run_q1,
            QualificationStage.Q3: run_q3,
            QualificationStage.D_WEB: run_d_web,
            QualificationStage.D_DHCP: run_d_dhcp,
            QualificationStage.Q3_FL_C1: run_q3_fastloop,
            QualificationStage.Q3_FL_C2: run_q3_fastloop,
            QualificationStage.SP2_NATIVE_POOL: run_q3_fastloop,
            QualificationStage.Q3_NATIVE_PROBE: run_q3_native_probe,
            QualificationStage.Q3_NATIVE_SIZE: run_q3_native_size,
            QualificationStage.Q3_NATIVE_POLICY: run_q3_native_policy,
            QualificationStage.Q3_NATIVE_STABILITY: run_q3_native_stability,
            QualificationStage.Q3_NATIVE_SERVE: run_q3_native_serve,
            QualificationStage.Q3_NATIVE_PRODUCT: run_q3_native_product,
            QualificationStage.SP1_ROUTED_W1: run_sp1_routed_product,
            QualificationStage.SP1_ROUTED_W2: run_sp1_routed_product,
            QualificationStage.SP2_REMOTE_RELAY: run_sp2_remote_relay,
            QualificationStage.SP2_MIXED_PRODUCT: run_sp2_mixed_product,
            QualificationStage.SP2_CAPACITY_PRODUCT: run_sp2_mixed_product,
        }
    )
)
