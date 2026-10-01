"""Local admission, boundary resolution, channel lifecycle and dispatch.

One invocation is admitted locally, its campaign claim is held, its product
contract is resolved, one transport is opened for the authorized channel,
the build and workspace are read before any effect, the stage's workflow runs
through an explicit handler, and finalization always follows an effect.
"""

from __future__ import annotations

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
from ..use_cases.deploy_enterprise_topology import disposable_workspace_error
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
    diagnostic_lifecycle: DiagnosticLifecycleObservation | None = None
    hold = CampaignHold(boundaries.campaign_coordinator)
    try:
        if definition.profile_id:
            refusals, diagnostic_lifecycle = diagnostic_admission(
                definition, authorization, boundaries, hold
            )
            if refusals:
                return refused_result(refusals, claim_release=hold.finalize())
        return _with_campaign_claim(
            request,
            boundaries,
            definition,
            devices,
            links,
            isolation,
            repository,
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
    product_contract: Q3ProductContract | None = None
    if definition.stage in SP1_ROUTED_STAGES:
        if (
            not boundaries.q3_required_build
            or request.packet_tracer_build != boundaries.q3_required_build
            or boundaries.sp1_product_contract is None
        ):
            return refused_result(
                [
                    refusal(
                        RefusalKind.NOT_PERMITTED,
                        RefusalSubject.BUILD,
                        "SP-1 has no reviewed exact-build contract.",
                    )
                ],
                claim_release=hold.finalize(),
            )
        try:
            product_contract = boundaries.sp1_product_contract(
                request.packet_tracer_build, run_id, definition.selected_clients
            )
        except Exception as exc:
            return refused_result(
                [
                    refusal(
                        RefusalKind.MALFORMED,
                        RefusalSubject.FIXTURE,
                        f"sp1_product_contract:{type(exc).__name__}:{bounded(exc)}",
                    )
                ],
                claim_release=hold.finalize(),
            )
    elif definition.stage is QualificationStage.Q3_NATIVE_PRODUCT:
        if (
            not boundaries.q3_required_build
            or request.packet_tracer_build != boundaries.q3_required_build
            or boundaries.native_product_contract is None
            or (
                definition.profile_version == "4"
                and boundaries.execution_mode is ExecutionMode.LIVE
                and boundaries.native_public_product_entry is None
            )
        ):
            return refused_result(
                [
                    refusal(
                        RefusalKind.NOT_PERMITTED,
                        RefusalSubject.BUILD,
                        "Native product has no reviewed exact-build contract.",
                    )
                ],
                claim_release=hold.finalize(),
            )
        try:
            product_contract = boundaries.native_product_contract(
                request.packet_tracer_build, run_id
            )
        except Exception as exc:
            return refused_result(
                [
                    refusal(
                        RefusalKind.MALFORMED,
                        RefusalSubject.FIXTURE,
                        f"native_product_contract:{type(exc).__name__}:{bounded(exc)}",
                    )
                ],
                claim_release=hold.finalize(),
            )
    elif definition.stage is QualificationStage.SP2_REMOTE_RELAY:
        if (
            not boundaries.q3_required_build
            or request.packet_tracer_build != boundaries.q3_required_build
            or boundaries.sp2_remote_relay_contract is None
        ):
            return refused_result(
                [
                    refusal(
                        RefusalKind.NOT_PERMITTED,
                        RefusalSubject.BUILD,
                        "SP-2 remote relay has no exact-build contract.",
                    )
                ],
                claim_release=hold.finalize(),
            )
        try:
            product_contract = boundaries.sp2_remote_relay_contract(
                request.packet_tracer_build, run_id
            )
        except Exception as exc:
            return refused_result(
                [
                    refusal(
                        RefusalKind.MALFORMED,
                        RefusalSubject.FIXTURE,
                        f"sp2_remote_relay_contract:{type(exc).__name__}:{bounded(exc)}",
                    )
                ],
                claim_release=hold.finalize(),
            )
    elif definition.stage in (
        QualificationStage.SP2_MIXED_PRODUCT,
        QualificationStage.SP2_CAPACITY_PRODUCT,
    ):
        factory = (
            boundaries.sp2_capacity_product_contract
            if definition.stage is QualificationStage.SP2_CAPACITY_PRODUCT
            else boundaries.sp2_mixed_product_contract
        )
        if (
            not boundaries.q3_required_build
            or request.packet_tracer_build != boundaries.q3_required_build
            or factory is None
        ):
            return refused_result(
                [
                    refusal(
                        RefusalKind.NOT_PERMITTED,
                        RefusalSubject.BUILD,
                        "SP-2 mixed product has no exact-build contract.",
                    )
                ],
                claim_release=hold.finalize(),
            )
        try:
            product_contract = factory(request.packet_tracer_build, run_id)
        except Exception as exc:
            return refused_result(
                [
                    refusal(
                        RefusalKind.MALFORMED,
                        RefusalSubject.FIXTURE,
                        f"sp2_mixed_product_contract:{type(exc).__name__}:{bounded(exc)}",
                    )
                ],
                claim_release=hold.finalize(),
            )
    elif definition.stage in (*Q3_FL_STAGES, *Q3_NATIVE_STAGES, *SP2_STAGES):
        if (
            not boundaries.q3_required_build
            or request.packet_tracer_build != boundaries.q3_required_build
            or boundaries.dhcp_product_contract is None
        ):
            return refused_result(
                [
                    refusal(
                        RefusalKind.NOT_PERMITTED,
                        RefusalSubject.BUILD,
                        "Q3-FL has no reviewed product contract for this build.",
                    )
                ],
                claim_release=hold.finalize(),
            )
        try:
            product_contract = boundaries.dhcp_product_contract(
                request.packet_tracer_build, run_id, definition.dhcp_pool_capacity
            )
        except Exception as exc:
            return refused_result(
                [
                    refusal(
                        RefusalKind.MALFORMED,
                        RefusalSubject.FIXTURE,
                        f"dhcp_product_contract:{type(exc).__name__}:{bounded(exc)}",
                    )
                ],
                claim_release=hold.finalize(),
            )
    elif definition.stage in (QualificationStage.Q3, QualificationStage.D_DHCP):
        if not boundaries.q3_required_build:
            return refused_result(
                [
                    refusal(
                        RefusalKind.NOT_PERMITTED,
                        RefusalSubject.BUILD,
                        "The Q3 Packet Tracer build policy is not composed.",
                    )
                ],
                claim_release=hold.finalize(),
            )
        if request.packet_tracer_build != boundaries.q3_required_build:
            return refused_result(
                [
                    refusal(
                        RefusalKind.NOT_PERMITTED,
                        RefusalSubject.BUILD,
                        "Q3 is not implemented for the requested Packet Tracer build.",
                    )
                ],
                claim_release=hold.finalize(),
            )
        if boundaries.q3_product_contract is None:
            return refused_result(
                [
                    refusal(
                        RefusalKind.NOT_PERMITTED,
                        RefusalSubject.FIXTURE,
                        "The executable Q3 product contract is not composed.",
                    )
                ],
                claim_release=hold.finalize(),
            )
        try:
            product_contract = boundaries.q3_product_contract(
                request.packet_tracer_build, run_id
            )
        except Exception as exc:
            return refused_result(
                [
                    refusal(
                        RefusalKind.MALFORMED,
                        RefusalSubject.FIXTURE,
                        f"q3_product_contract:{type(exc).__name__}:{bounded(exc)}",
                    )
                ],
                claim_release=hold.finalize(),
            )

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
    cancelled: BaseException | None = None
    try:
        if definition.stage is QualificationStage.Q0:
            run_q0(execution)
        elif definition.stage is QualificationStage.Q1:
            run_q1(execution)
        elif definition.stage is QualificationStage.D_DHCP:
            run_d_dhcp(execution)
        elif definition.stage is QualificationStage.D_WEB:
            run_d_web(execution)
        elif definition.stage is QualificationStage.SP2_REMOTE_RELAY:
            run_sp2_remote_relay(execution)
        elif definition.stage in (
            QualificationStage.SP2_MIXED_PRODUCT,
            QualificationStage.SP2_CAPACITY_PRODUCT,
        ):
            run_sp2_mixed_product(execution)
        elif definition.stage in (*Q3_FL_STAGES, *SP2_STAGES):
            run_q3_fastloop(execution)
        elif definition.stage is QualificationStage.Q3_NATIVE_PROBE:
            run_q3_native_probe(execution)
        elif definition.stage is QualificationStage.Q3_NATIVE_SIZE:
            run_q3_native_size(execution)
        elif definition.stage is QualificationStage.Q3_NATIVE_POLICY:
            run_q3_native_policy(execution)
        elif definition.stage is QualificationStage.Q3_NATIVE_STABILITY:
            run_q3_native_stability(execution)
        elif definition.stage is QualificationStage.Q3_NATIVE_SERVE:
            run_q3_native_serve(execution)
        elif definition.stage is QualificationStage.Q3_NATIVE_PRODUCT:
            run_q3_native_product(execution)
        elif definition.stage in SP1_ROUTED_STAGES:
            run_sp1_routed_product(execution)
        else:
            run_q3(execution)
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
    completed = (
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
    run.complete(
        QualificationOutcome.COMPLETED if completed else QualificationOutcome.STOPPED
    )
    if cancelled is not None:
        raise cancelled
    return QualificationResult(
        outcome=record.outcome,
        record=record,
        record_path=run.record_path,
        claim_release=execution.hold.release_fact,
    )
