"""Q3-FL and SP-2 native pool: the versioned DHCP qualification profile."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ....domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationRuntimeContext,
    decide_mutation,
)
from ....domain.enterprise.models.execution import DispatchFact, ResultFact
from ....domain.enterprise.models.service_plan import (
    AcquireDhcpLease,
    ConfigureServerDhcpPool,
    EnableServerDhcp,
)
from ....domain.enterprise.models.service_qualification import (
    Q3_FL_BACKGROUND_INTERVAL_SECONDS,
    Q3_FL_FIXTURE_ACCESS_VLAN,
    Q3_FL_NATIVE_DEFAULT_POLICY,
    Q3_FL_RENEWAL_HORIZON_READS,
    Q3_FL_RENEWAL_INTERVAL_SECONDS,
    Q3_FL_SETTLE_INTERVAL_SECONDS,
    Q3_FL_SETTLE_READS,
    Q3_FL_TIMED_INTERVAL_SECONDS,
    Q3_POOL,
    Q3_SERVER,
    REQUESTED_RENEWAL_CONTRACT_ABSENT,
    DiagnosticPrecondition,
    MeasurementConclusion,
    MeasurementStatus,
    QualificationStage,
    ReleaseRecord,
)
from ....domain.enterprise.models.service_runtime import ServiceApplicationResult
from ....domain.enterprise.services.dhcp_lease_evidence import (
    NO_BACKGROUND_PROOF,
    NOT_DORA,
    SERVED_INTENDED,
    SERVED_NATIVE,
    SERVED_NONE,
    AddressRange,
    CalibrationState,
    ClientAttribution,
    ClientReading,
    LeaseScan,
    assess_capacity_one_negative,
    assess_lease_calibration,
    attribute_client,
    is_dotted_mac,
    normalized_mac,
)
from ....domain.enterprise.services.dhcp_native_default_lifecycle import (
    INTERVAL_REFUSED,
    UNEXPLAINED_DRIFT,
    NativeDefaultReading,
    assess_intended_pool_coexistence,
)
from ....domain.enterprise.services.qualification_product_evidence import (
    e5_foundation_cause,
    readback_not_observed_cause,
    service_result_cause,
)
from ....domain.enterprise.services.service_access_readiness import (
    DHCP_ACQUISITION_KINDS,
    derive_access_readiness_plan,
)
from ....domain.enterprise.services.service_diagnostic_profiles import (
    d_dhcp_enable_only_plan,
    d_dhcp_pool_only_plan,
    d_dhcp_static_only_plan,
    q3_fastloop_client_mode_plan,
    q3_fastloop_fixture_placements,
    q3_fastloop_service_plan,
)
from ....domain.enterprise.services.service_qualification_evidence import (
    Assessment,
    assess_dhcp_baseline_admission,
)
from ....domain.enterprise.services.sp2_pool_diagnostic import (
    assess_sp2_pool_identity,
    cap_sp2_pool_identity,
    sp2_client_progression,
)
from ...use_cases.apply_configuration import ConfigurationApplicator
from ...use_cases.apply_services import ServiceApplicator
from ...use_cases.service_access_readiness_gate import ServiceAccessReadinessGate
from ..contracts import Q3ProductContract, bounded
from ..dhcp_observations import (
    Q3_FL_DEFAULT_PURPOSE,
    DhcpAcquisitionClient,
    DhcpObservationState,
    dhcp_acquisition_clients,
    native_default_facts,
    native_default_snapshot,
    q3_default_observed,
    q3_default_purpose,
    read_acquisition_clients,
    read_client_binding,
    scan_dhcp_pools,
)
from ..execution import Execution
from ..fixtures import diagnostic_start
from ..operation_budget import counted_seq
from ..product_support import (
    DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE,
    application_rows,
    exact_inventory_runtimes,
    product_runtime_context,
    projection_foundations,
)

_Q3FL_CLIENT_MODE = "e5:client_dhcp_mode:configurePcIp_dhcp_flag"
_Q3FL_SERVER_SETUP = "e6:configure_pool_and_enable"
_Q3FL_TERMINAL = "acquisitions_repeat_and_timing"
_Q3FL_DHCP_IDS = (
    "M-DHCP-2",
    "M-DHCP-6",
    "M-DHCP-6-CAP",
    "M-DHCP-6-REPEAT",
    "M-DHCP-6-TIME",
)


@dataclass
class _Q3FlState(DhcpObservationState):
    """What one Q3-FL run has established, carried between its procedures."""

    foundations: dict[str, ActionExecutionStatus] = field(default_factory=dict)
    admitted: tuple[str, ...] = ()
    mode_verified: tuple[str, ...] = ()
    gate_rows: list[dict[str, object]] = field(default_factory=list)
    rewrites: list[str] = field(default_factory=list)
    server_application: ServiceApplicationResult | None = None
    server_facts: dict[str, Any] = field(default_factory=dict)
    acquisitions: dict[str, dict[str, Any]] = field(default_factory=dict)
    repeat: dict[str, Any] = field(default_factory=dict)
    timing_labels: list[str] = field(default_factory=list)


def _q3fl_policy_cause(state: _Q3FlState) -> str:
    """Return the first interval the policy refused, or ""."""
    if state.sequence is None or state.sequence.permits_continuation:
        return ""
    return "q3fl_native_default_policy:" + state.sequence.causes[0]


def _q3fl_sequence_facts(state: _Q3FlState) -> dict[str, Any]:
    """Return every interval the policy decided, with its assessment."""
    sequence = state.sequence
    if sequence is None:
        return {"policy": Q3_FL_NATIVE_DEFAULT_POLICY, "intervals": []}
    return {
        "policy": sequence.policy,
        "permits_continuation": sequence.permits_continuation,
        "causes": list(sequence.causes),
        "limitations": list(sequence.limitations),
        "authorizes_allocation": sequence.authorizes_allocation,
        "intervals": [
            {
                "before": item.before_label,
                "after": item.after_label,
                "intervention": item.intervention,
                "classification": item.assessment.classification,
                "changed_fields": list(item.assessment.changed_fields),
                "assessment_causes": list(item.assessment.causes),
                "matched_evidence": item.assessment.matched_evidence,
                "decision": item.decision,
                "cause": item.cause,
            }
            for item in sequence.intervals
        ],
    }


def _q3fl_request(result: ServiceApplicationResult, action_id: str) -> str:
    """Classify one acquisition's dispatch from its own canonical row.

    This is the Q3-FL decision predicate the brief records. The product keeps
    a void `dhcpRun` unsettled for product dependents until a read-back
    verifies it, and nothing here changes that. What this profile needs is
    narrower: whether the claim script's single evaluation is known. A row
    that reproduces its canonical decision, was accepted and correlated,
    reported `attempted=true` and carried no call error is a known dispatch.
    `attempted=false` is a known non-dispatch with its skip reason. A
    preflight refusal dispatched nothing. Anything else is an unknown outcome,
    which stops every later effect and is never retried.
    """
    row = next(
        (item for item in result.action_results if item.action_id == action_id), None
    )
    if row is None:
        if result.preflight_errors and not result.action_results:
            return "not_dispatched:preflight:" + bounded(result.preflight_errors[0])
        return "outcome_unknown:acquisition_row_absent"
    snapshot = row.received_mutation
    if snapshot is None or snapshot.action_id != action_id:
        return "outcome_unknown:acquisition_snapshot_absent"
    decision = decide_mutation(snapshot)
    if not (
        row.status is decision.status
        and row.failure_code is decision.failure_code
        and row.disposition is decision.disposition
        and row.dispatch is snapshot.dispatch
        and row.result is snapshot.result
        and row.attempted is snapshot.attempted
        and row.cause == decision.cause
    ):
        return "outcome_unknown:acquisition_row_incoherent"
    if snapshot.attempted is False and not snapshot.call_error:
        return "not_dispatched:" + bounded(row.cause or snapshot.cause or "skipped")
    if (
        row.dispatch is not DispatchFact.ACCEPTED
        or row.result is not ResultFact.CORRELATED
        or snapshot.attempted is not True
        or bool(snapshot.call_error)
    ):
        return "outcome_unknown:acquisition_dispatch"
    return "dispatched"


def run_q3_fastloop(execution: Execution) -> None:
    """Run the versioned Q3-FL profile: server, forwarding, clients, tables.

    The E5 bootstrap is split by subject so the native-default transition falls
    inside its one reviewed context, and client DHCP mode is activated while
    the server's process is still disabled so a background discover finds no
    server. Every later reading is a stability check under the versioned
    policy. Acquisitions follow an admitted forwarding decision, one typed
    request per client under its claim, each bracketed by readings and scans.
    """
    state = _Q3FlState()
    execution.register_terminal(
        ("M-DHCP-1-FINAL",), "Q3FL_FINAL", lambda: _q3fl_final(execution, state)
    )
    if not diagnostic_start(execution):
        return
    contract = execution.product_contract
    if contract is None:  # pragma: no cover - admission composes it
        execution.stop("q3fl_product_contract_absent")
        return
    state.clients = dhcp_acquisition_clients(contract)
    if not state.clients or any(
        not item.lease_expectation_id for item in state.clients
    ):
        execution.stop("q3fl_contract_has_no_attributable_client")
        return
    configuration_runtime, service_runtime = exact_inventory_runtimes(
        execution, contract
    )
    context = product_runtime_context(contract)
    execution.record.limitations.extend(
        [
            "q3fl_private_candidate_capabilities:no_public_catalog_mutation",
            "q3fl_physical_fixture_owned_by_runner:no_switch_action_applied",
            f"q3fl_native_default_policy:{Q3_FL_NATIVE_DEFAULT_POLICY}",
            "q3fl_dhcp_lease_never_promoted_to_verified:r_evt_05_fallback_active",
        ]
    )
    ids = tuple(
        item
        for item in ("M-DHCP-1", "M-DHCP-4", "M-DHCP-5")
        if any(row.experiment_id == item for row in execution.record.measurements)
    )
    if execution.selected("Q3FL-core") and execution.begin(ids, "Q3FL_SERVER"):
        with execution.procedure(ids):
            _q3fl_server(
                execution,
                state,
                contract,
                configuration_runtime,
                service_runtime,
                context,
            )
        execution.finish("Q3FL_SERVER")
    ids = tuple(
        item
        for item in (
            *_Q3FL_DHCP_IDS,
            *(
                ("M-SP2-POOL-IDENTITY",)
                if execution.definition.stage is QualificationStage.SP2_NATIVE_POOL
                else ()
            ),
        )
        if any(row.experiment_id == item for row in execution.record.measurements)
        and execution.measurement(item).status is MeasurementStatus.NOT_RUN
    )
    if ids and execution.selected("Q3FL-core") and execution.begin(ids, "Q3FL_DHCP"):
        with execution.procedure(ids):
            _q3fl_dhcp(
                execution,
                state,
                contract,
                configuration_runtime,
                service_runtime,
                context,
                ids,
            )
        execution.finish("Q3FL_DHCP")


def _q3fl_server(
    execution: Execution,
    state: _Q3FlState,
    contract: Q3ProductContract,
    configuration_runtime,
    service_runtime,
    context: ConfigurationRuntimeContext,
) -> None:
    """Baseline, the server's address, forwarding, client mode, then the pool."""
    ledger = execution.ledger
    start = len(ledger.entries)
    with ledger.purpose_of(q3_default_purpose("before_e5", Q3_FL_DEFAULT_PURPOSE)):
        baseline = execution.probes.read_dhcp_server_baseline(
            Q3_SERVER, "FastEthernet0"
        )
    admission = assess_dhcp_baseline_admission(
        baseline,
        server=Q3_SERVER,
        interface="FastEthernet0",
        intended_pool=Q3_POOL,
        observed_build=execution.record.environment.observed_build,
        qualified_build=execution.run.boundaries.q3_required_build,
        observed_channel=execution.channel,
        qualified_channels=execution.definition.allowed_channels,
    )
    first = q3_default_observed(
        execution,
        "before_e5",
        baseline,
        operation_seq=counted_seq(ledger, start),
        prefix=Q3_FL_DEFAULT_PURPOSE,
    )
    state.readings.append(
        NativeDefaultReading(
            label="before_e5",
            observed=first.observed,
            rows=tuple(dict(item) for item in first.pools),
            cause=first.cause,
        )
    )
    state.native_pools = tuple(str(item["name"]) for item in first.pools)
    before = read_acquisition_clients(execution, state, "baseline")
    scan_dhcp_pools(execution, state, "baseline")
    causes: list[str] = []
    if not admission.admitted:
        causes.extend(["initial_dhcp_server_state_not_admissible", *admission.causes])
    if (
        execution.definition.stage is QualificationStage.SP2_NATIVE_POOL
        and state.native_pools != ("serverPool",)
    ):
        causes.append("sp2_native_default_baseline_not_exact")
    for name, reading in before.items():
        if not reading.observed:
            causes.append(f"client_not_readable:{name}:{reading.cause}")
        elif reading.mode is not False:
            causes.append(f"client_dhcp_mode_not_off:{name}")
    state.server_facts["baseline_admission"] = {
        "admitted": admission.admitted,
        "kind": admission.kind,
        "causes": list(admission.causes),
    }
    cause = ""
    if causes:
        cause = "q3fl_baseline_not_established:" + causes[0]
        state.server_facts["baseline_causes"] = causes
    else:
        execution.establish(
            DiagnosticPrecondition.INVENTORY_COHERENT,
            DiagnosticPrecondition.PROCESS_DISABLED_VERIFIED,
        )
        cause = _q3fl_server_address(
            execution, state, contract, configuration_runtime, context
        )
        if (
            not cause
            and execution.definition.stage is QualificationStage.SP2_NATIVE_POOL
        ):
            scan_dhcp_pools(execution, state, "after_server_address")
    if not cause:
        _q3fl_forwarding(execution, state, contract)
        if execution.definition.stage is QualificationStage.SP2_NATIVE_POOL and (
            not state.clients or state.clients[0].name not in state.admitted
        ):
            cause = "sp2_first_client_forwarding_not_admitted"
        if (
            state.admitted
            and execution.definition.stage is not QualificationStage.SP2_NATIVE_POOL
        ):
            cause = _q3fl_client_mode(
                execution, state, contract, configuration_runtime, context
            )
    if not cause:
        if execution.definition.stage is QualificationStage.SP2_NATIVE_POOL:
            cause = _sp2_pool_first_setup(
                execution, state, contract, service_runtime, context
            )
        else:
            cause = _q3fl_server_setup(
                execution, state, contract, service_runtime, context
            )
    if cause:
        execution.stop(cause)
    _q3fl_conclude_server(execution, state, cause)


def _q3fl_server_address(
    execution: Execution,
    state: _Q3FlState,
    contract: Q3ProductContract,
    configuration_runtime,
    context: ConfigurationRuntimeContext,
) -> str:
    """Apply the server's static address alone, inside the reviewed context."""
    static_plan = d_dhcp_static_only_plan(
        contract.configuration_plan, device_name=Q3_SERVER
    )
    if not execution.run.transition("experiment:Q3FL_SERVER:e5_server_address"):
        return "persistence:q3fl_e5_server_address_not_announced"
    with execution.ledger.effect_of("q3-fl:product:e5_server_address"):
        result = ConfigurationApplicator(configuration_runtime).apply(
            static_plan,
            actual_source_topology_hash=contract.manifest.physical_topology_hash,
            capabilities=contract.device_capabilities,
            runtime_context=context,
            deployment_manifest=contract.manifest,
        )
    foundations = projection_foundations(contract, static_plan, result)
    state.foundations.update(foundations)
    state.server_facts["e5_server_address"] = {
        "plan_id": static_plan.id,
        "action_results": [
            item.model_dump(mode="json") for item in result.action_results
        ],
        "verification_results": [
            item.model_dump(mode="json") for item in result.verification_results
        ],
    }
    cause = e5_foundation_cause(
        result, foundations, {item.id for item in static_plan.actions}
    )
    reviewed = execution.run.boundaries.reviewed_native_default_intervention
    permitted = native_default_snapshot(
        execution, state, "after_server_address", reviewed
    )
    if cause:
        return cause
    if not permitted:
        return _q3fl_policy_cause(state)
    execution.establish(DiagnosticPrecondition.SERVER_ADDRESSING)
    return ""


def _q3fl_forwarding(
    execution: Execution, state: _Q3FlState, contract: Q3ProductContract
) -> None:
    """Decide every client's forwarding through the product gate, before activity."""
    actions, rewrites = q3_fastloop_fixture_placements(
        contract.configuration_plan, vlan_id=Q3_FL_FIXTURE_ACCESS_VLAN
    )
    state.rewrites.extend(item.as_text() for item in rewrites)
    wanted = {item.lease_expectation_id for item in state.clients}
    plan = derive_access_readiness_plan(
        configuration_actions=actions,
        verification_expectations=[
            item
            for item in contract.service_plan.verification_expectations
            if item.id in wanted
        ],
        request_kinds=DHCP_ACQUISITION_KINDS,
    )
    gate = ServiceAccessReadinessGate(
        plan,
        execution.run.boundaries.configuration_runtime(execution.bound),
        clock=execution.bound.clock,
    )
    gate.begin_invocation()
    admitted: list[str] = []
    verdicts: dict[str, dict[str, object]] = {}
    with execution.ledger.purpose_of("q3-fl:forwarding"):
        for client in state.clients:
            verdict = gate.decide(client.lease_expectation_id)
            verdicts[client.name] = (
                verdict.as_row() if verdict is not None else {"admitted": False}
            )
            if verdict is not None and verdict.admitted:
                admitted.append(client.name)
    state.gate_rows = gate.rows()
    state.admitted = tuple(admitted)
    state.server_facts["forwarding"] = {
        "verdicts": verdicts,
        "groups": state.gate_rows,
        "unplaced": [item.expectation_id for item in plan.unplaced],
    }
    if admitted:
        execution.establish(DiagnosticPrecondition.FORWARDING_OBSERVED)


def _q3fl_client_mode(
    execution: Execution,
    state: _Q3FlState,
    contract: Q3ProductContract,
    configuration_runtime,
    context: ConfigurationRuntimeContext,
    *,
    device_names: Sequence[str] | None = None,
    label: str = "after_client_mode",
) -> str:
    """Activate only the named admitted clients and read their resulting mode."""
    names = tuple(device_names) if device_names is not None else state.admitted
    if not names or any(name not in state.admitted for name in names):
        return "q3fl_client_mode_selection_not_admitted"
    plan = q3_fastloop_client_mode_plan(contract.configuration_plan, device_names=names)
    if not execution.run.transition("experiment:Q3FL_SERVER:e5_client_mode"):
        return "persistence:q3fl_e5_client_mode_not_announced"
    with execution.ledger.effect_of("q3-fl:product:e5_client_mode"):
        result = ConfigurationApplicator(configuration_runtime).apply(
            plan,
            actual_source_topology_hash=contract.manifest.physical_topology_hash,
            capabilities=contract.device_capabilities,
            runtime_context=context,
            deployment_manifest=contract.manifest,
        )
    foundations = projection_foundations(contract, plan, result)
    state.foundations.update(foundations)
    mode_effect = {
        "plan_id": plan.id,
        "clients": list(names),
        "action_results": [
            item.model_dump(mode="json") for item in result.action_results
        ],
        "verification_results": [
            item.model_dump(mode="json") for item in result.verification_results
        ],
    }
    state.server_facts["e5_client_mode"] = mode_effect
    if execution.definition.stage is QualificationStage.SP2_NATIVE_POOL:
        state.server_facts.setdefault("sp2_mode_effects", []).append(mode_effect)
    cause = e5_foundation_cause(result, foundations, {item.id for item in plan.actions})
    after = read_acquisition_clients(execution, state, label)
    permitted = native_default_snapshot(execution, state, label, _Q3FL_CLIENT_MODE)
    scan_dhcp_pools(execution, state, label)
    state.mode_verified = tuple(
        name
        for name in names
        if after.get(name) is not None
        and after[name].observed
        and after[name].mode is True
    )
    if cause:
        return cause
    if not permitted:
        return _q3fl_policy_cause(state)
    if state.mode_verified:
        execution.establish(DiagnosticPrecondition.CLIENT_DHCP_MODE)
    return ""


def _q3fl_server_setup(
    execution: Execution,
    state: _Q3FlState,
    contract: Q3ProductContract,
    service_runtime,
    context: ConfigurationRuntimeContext,
) -> str:
    """Write the intended pool and enable the process, once, then read."""
    plan, rewrites = q3_fastloop_service_plan(contract.service_plan)
    state.rewrites.extend(item.as_text() for item in rewrites)
    if not execution.run.transition("experiment:Q3FL_SERVER:e6_server"):
        return "persistence:q3fl_e6_server_not_announced"
    with execution.ledger.effect_of("q3-fl:product:e6_server"):
        result = ServiceApplicator(service_runtime).apply(
            plan,
            actual_source_topology_hash=contract.manifest.physical_topology_hash,
            actual_source_configuration_hash=(
                contract.service_plan.source_configuration_hash
            ),
            foundational_statuses=state.foundations,
            capabilities=contract.service_capabilities,
            runtime_context=context,
            deployment_manifest=contract.manifest,
            operational_readiness=DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE,
        )
    state.server_application = result
    state.server_facts["e6_server"] = {"plan_id": plan.id, **application_rows(result)}
    cause = service_result_cause(
        result,
        {item.id for item in plan.actions},
        expected_verification_ids={item.id for item in plan.verification_expectations},
    ) or readback_not_observed_cause(result)
    permitted = native_default_snapshot(
        execution, state, "after_server_setup", _Q3FL_SERVER_SETUP
    )
    scan_dhcp_pools(execution, state, "empty_after_enable")
    if cause:
        return cause
    if not permitted:
        return _q3fl_policy_cause(state)
    execution.establish(
        DiagnosticPrecondition.POOL_CONFIGURED,
        DiagnosticPrecondition.PROCESS_ENABLED_VERIFIED,
        DiagnosticPrecondition.NATIVE_DEFAULT_PERMITS,
    )
    return ""


def _sp2_pool_first_setup(
    execution: Execution,
    state: _Q3FlState,
    contract: Q3ProductContract,
    service_runtime,
    context: ConfigurationRuntimeContext,
) -> str:
    """Verify a named pool while disabled, then enable, with PCs still off."""
    if not native_default_snapshot(
        execution, state, "before_pool_setup", "sp2:forwarding_readiness"
    ):
        return _q3fl_policy_cause(state)
    scan_dhcp_pools(execution, state, "before_pool_setup")
    prior = state.snapshots[-1] if state.snapshots else None
    if (
        prior is None
        or not prior.observed
        or prior.raw.get("enabled_type") != "boolean"
        or prior.raw.get("enabled") is not False
    ):
        return "sp2_process_not_proven_disabled_before_pool"
    executed = frozenset(state.foundations)
    stages = (
        ("pool", d_dhcp_pool_only_plan, False),
        ("enable", d_dhcp_enable_only_plan, True),
    )
    results: dict[str, Any] = {}
    for name, projection, expected_enabled in stages:
        plan, rewrites = projection(
            contract.service_plan, executed_configuration_action_ids=executed
        )
        expected_type = ConfigureServerDhcpPool if name == "pool" else EnableServerDhcp
        if (
            len(plan.actions) != 1
            or not isinstance(plan.actions[0], expected_type)
            or len(plan.verification_expectations) != 1
        ):
            return f"sp2_{name}_projection_not_exact"
        state.rewrites.extend(item.as_text() for item in rewrites)
        if not execution.run.transition(f"experiment:SP2_SERVER:e6_{name}"):
            return f"persistence:sp2_e6_{name}_not_announced"
        with execution.ledger.effect_of(f"sp2:product:e6_{name}"):
            result = ServiceApplicator(service_runtime).apply(
                plan,
                actual_source_topology_hash=contract.manifest.physical_topology_hash,
                actual_source_configuration_hash=(
                    contract.service_plan.source_configuration_hash
                ),
                foundational_statuses=state.foundations,
                capabilities=contract.service_capabilities,
                runtime_context=context,
                deployment_manifest=contract.manifest,
                operational_readiness=DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE,
            )
        results[name] = {"plan_id": plan.id, **application_rows(result)}
        cause = service_result_cause(
            result,
            {item.id for item in plan.actions},
            expected_verification_ids={
                item.id for item in plan.verification_expectations
            },
        ) or readback_not_observed_cause(result)
        permitted = native_default_snapshot(
            execution, state, f"after_{name}_setup", f"sp2:e6_{name}"
        )
        snapshot = state.snapshots[-1]
        scan_dhcp_pools(execution, state, f"after_{name}_setup")
        if cause:
            state.server_facts["e6_server"] = results
            return cause
        if not permitted:
            state.server_facts["e6_server"] = results
            return _q3fl_policy_cause(state)
        if (
            not snapshot.observed
            or snapshot.raw.get("enabled_type") != "boolean"
            or snapshot.raw.get("enabled") is not expected_enabled
            or not snapshot.intended_present
        ):
            state.server_facts["e6_server"] = results
            return f"sp2_{name}_physical_readback_unverified"
        if name == "pool":
            execution.establish(DiagnosticPrecondition.POOL_CONFIGURED)
        else:
            state.server_application = result
    state.server_facts["e6_server"] = results
    execution.establish(
        DiagnosticPrecondition.PROCESS_ENABLED_VERIFIED,
        DiagnosticPrecondition.NATIVE_DEFAULT_PERMITS,
    )
    return ""


def _q3fl_conclude_server(execution: Execution, state: _Q3FlState, cause: str) -> None:
    """Conclude M-DHCP-1, M-DHCP-4 and M-DHCP-5 from what the run observed."""
    sequence = _q3fl_sequence_facts(state)
    drift = state.sequence is not None and any(
        item.decision == INTERVAL_REFUSED
        and item.assessment.classification == UNEXPLAINED_DRIFT
        for item in state.sequence.intervals
    )
    server_facts = {
        **state.server_facts,
        "native_default": native_default_facts(execution),
        "native_default_sequence": sequence,
        "projection_rewrites": list(state.rewrites),
        "coexistence": _q3fl_coexistence(execution),
        "scans": [
            {
                "label": label,
                "pools": {name: scan.as_facts() for name, scan in scans.items()},
            }
            for label, scans in state.scans
        ],
    }
    established = {
        DiagnosticPrecondition.SERVER_ADDRESSING,
        DiagnosticPrecondition.POOL_CONFIGURED,
        DiagnosticPrecondition.PROCESS_ENABLED_VERIFIED,
        DiagnosticPrecondition.NATIVE_DEFAULT_PERMITS,
    } <= execution.established
    if drift:
        conclusion = MeasurementConclusion.CONTRADICTED
    elif established and not cause:
        conclusion = MeasurementConclusion.SUPPORTED_IN_SAMPLE
    else:
        conclusion = MeasurementConclusion.INCONCLUSIVE
    measured = {item.experiment_id for item in execution.record.measurements}
    if "M-DHCP-1" in measured:
        execution.conclude(
            "M-DHCP-1",
            Assessment(
                conclusion,
                facts=server_facts,
                causes=[cause] if cause else [],
                limitations=[
                    "no_explicit_setter_targeted_the_native_default",
                    "enabling_the_process_is_process_wide",
                    "stored_pool_configuration_is_not_service",
                ],
            ),
        )
    readings = _q3fl_reading_series(state)
    if "M-DHCP-4" in measured:
        execution.conclude("M-DHCP-4", _q3fl_mac_assessment(state, readings))
    if "M-DHCP-5" in measured:
        execution.conclude("M-DHCP-5", _q3fl_mode_assessment(state, readings))


def _q3fl_coexistence(execution: Execution) -> dict[str, Any]:
    """State how the intended pool sits beside the native default, as fact."""
    entries = execution.record.native_default_pool
    last = entries[-1] if entries else None
    if last is None or not last.observed:
        return {"stated": False, "cause": "no_observed_reading"}
    raw_rows = last.raw.get("pools") if isinstance(last.raw, Mapping) else None
    intended = next(
        (
            row
            for row in (raw_rows if isinstance(raw_rows, list) else [])
            if isinstance(row, Mapping) and row.get("name") == Q3_POOL
        ),
        None,
    )
    native = next(iter(last.pools), None)
    if intended is None or native is None:
        return {"stated": False, "cause": "intended_or_native_row_absent"}
    coexistence = assess_intended_pool_coexistence(native=native, intended=intended)
    return {
        "stated": True,
        "reading": last.label,
        "native_pool": coexistence.native_pool_name,
        "intended_pool": coexistence.intended_pool_name,
        "shares_subnet": coexistence.shares_subnet,
        "ranges_overlap": coexistence.ranges_overlap,
        "overlapping_addresses": list(coexistence.overlapping_addresses),
        "causes": list(coexistence.causes),
        "limitations": list(coexistence.limitations),
    }


def _q3fl_mac_assessment(
    state: _Q3FlState, readings: list[dict[str, Any]]
) -> Assessment:
    """Judge the MAC reader: typed text, stable across every reading taken."""
    macs: dict[str, set[str]] = {}
    unread: list[str] = []
    for _label, values in state.client_reads:
        for name, item in values.items():
            if item.observed:
                macs.setdefault(name, set()).add(item.mac)
            else:
                unread.append(name)
    causes = []
    for client in state.clients:
        seen = macs.get(client.name, set())
        if not seen:
            causes.append(f"mac_never_read:{client.name}")
        elif len(seen) > 1:
            causes.append(f"mac_changed_between_readings:{client.name}")
        elif not all(is_dotted_mac(item) for item in seen):
            causes.append(f"mac_text_not_dotted_hex:{client.name}")
    return Assessment(
        MeasurementConclusion.INCONCLUSIVE
        if causes
        else MeasurementConclusion.SUPPORTED_IN_SAMPLE,
        facts={"readings": readings},
        causes=causes,
        limitations=[
            "native_mac_representation_sample_only",
            "no_equivalence_inferred",
        ],
    )


def _q3fl_mode_assessment(
    state: _Q3FlState, readings: list[dict[str, Any]]
) -> Assessment:
    """Judge the mode reader: off before, on after activation, boolean always."""
    baseline = state.reading("baseline")
    after = state.reading("after_client_mode")
    causes: list[str] = []
    for client in state.clients:
        first = baseline.get(client.name)
        if first is None or not first.observed:
            causes.append(f"baseline_mode_unread:{client.name}")
        elif first.mode is not False:
            causes.append(f"baseline_mode_not_off:{client.name}")
        if client.name not in state.admitted:
            causes.append(f"forwarding_not_admitted:{client.name}")
            continue
        second = after.get(client.name)
        if second is None or not second.observed:
            causes.append(f"activated_mode_unread:{client.name}")
        elif second.mode is not True:
            causes.append(f"activated_mode_not_on:{client.name}")
    return Assessment(
        MeasurementConclusion.INCONCLUSIVE
        if causes
        else MeasurementConclusion.SUPPORTED_IN_SAMPLE,
        facts={
            "readings": readings,
            "forwarding": state.server_facts.get("forwarding", {}),
            "admitted": list(state.admitted),
            "mode_verified": list(state.mode_verified),
        },
        causes=causes,
        limitations=[
            "native_mode_reader_sample_only",
            "mode_activation_is_potentially_effectful",
            "readiness_is_a_property_of_the_measured_ports_at_that_moment",
        ],
    )


def _q3fl_dhcp(
    execution: Execution,
    state: _Q3FlState,
    contract: Q3ProductContract,
    configuration_runtime,
    service_runtime,
    context: ConfigurationRuntimeContext,
    ids: tuple[str, ...],
) -> None:
    """Acquire per admitted client, repeat once, time, then conclude the tables."""
    if execution.definition.stage is QualificationStage.SP2_NATIVE_POOL:
        _sp2_native_dhcp(
            execution, state, contract, configuration_runtime, context, ids
        )
        return
    ledger = execution.ledger
    sleep = execution.run.boundaries.sleep
    read_acquisition_clients(execution, state, "background_1")
    ledger.wait(Q3_FL_BACKGROUND_INTERVAL_SECONDS, sleep)
    read_acquisition_clients(execution, state, "background_2")
    nonces = {
        reference: f"{execution.nonce}:{index}"
        for index, reference in enumerate(
            contract.service_plan.operation_nonce_refs(), start=1
        )
    }
    bound_plan = contract.service_plan.with_operation_nonces(nonces)
    acquisitions = {
        item.host_device_id: item
        for item in bound_plan.actions
        if isinstance(item, AcquireDhcpLease)
    }
    retained = (
        state.server_application.action_results
        if state.server_application is not None
        else ()
    )
    for client in state.clients:
        if client.name not in state.mode_verified:
            state.acquisitions[client.name] = {
                "request": "not_dispatched:mode_or_forwarding_not_established",
            }
            continue
        if execution.stopped:
            state.acquisitions[client.name] = {
                "request": "not_dispatched:stopped:" + execution.record.primary_failure,
            }
            continue
        before_label = f"before:{client.name}"
        before = read_acquisition_clients(execution, state, before_label)
        prior_label = state.scans[-1][0] if state.scans else ""
        plan, rewrites = q3_fastloop_service_plan(
            bound_plan, client_device_id=client.device_id
        )
        state.rewrites.extend(item.as_text() for item in rewrites)
        if not execution.run.transition(f"experiment:Q3FL_DHCP:acquire:{client.name}"):
            execution.stop("persistence:q3fl_acquisition_not_announced")
            break
        with ledger.effect_of(f"q3-fl:product:acquire:{client.name}"):
            result = ServiceApplicator(service_runtime).apply(
                plan,
                actual_source_topology_hash=contract.manifest.physical_topology_hash,
                actual_source_configuration_hash=(
                    contract.service_plan.source_configuration_hash
                ),
                foundational_statuses=state.foundations,
                capabilities=contract.service_capabilities,
                runtime_context=context,
                deployment_manifest=contract.manifest,
                operational_readiness=DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE,
                retained_action_results=retained,
            )
        request = _q3fl_request(result, client.acquisition_id)
        entry: dict[str, Any] = {
            "request": request,
            "plan_id": plan.id,
            "before_label": before_label,
            "prior_scan_label": prior_label,
            "product": application_rows(result),
        }
        state.acquisitions[client.name] = entry
        if request.startswith("outcome_unknown"):
            # Never retried. Reads may still say what happened, but no later
            # effect of this run is admitted after an unknown outcome.
            execution.stop(f"outcome_unknown:q3fl_acquisition:{client.name}:{request}")
        before_reading = before.get(client.name)
        settle_labels: list[str] = []
        for index in range(1, Q3_FL_SETTLE_READS + 1):
            ledger.wait(Q3_FL_SETTLE_INTERVAL_SECONDS, sleep)
            label = f"settle:{client.name}:{index}"
            settle_labels.append(label)
            current = read_acquisition_clients(execution, state, label).get(client.name)
            if (
                current is not None
                and current.observed
                and before_reading is not None
                and before_reading.observed
                and current.ipv4 != before_reading.ipv4
            ):
                break
        entry["settle_labels"] = settle_labels
        entry["after_label"] = settle_labels[-1] if settle_labels else before_label
        entry["scan_label"] = f"after:{client.name}"
        scan_dhcp_pools(execution, state, entry["scan_label"])
        if (
            not state.repeat
            and request == "dispatched"
            and not execution.stopped
            and execution.measurement("M-DHCP-6-REPEAT").status
            is MeasurementStatus.NOT_RUN
            and "M-DHCP-6-REPEAT" in ids
        ):
            _q3fl_repeat(
                execution,
                state,
                client,
                acquisitions[client.device_id],
                service_runtime,
            )
    for client in state.clients:
        acquired = state.acquisitions.get(client.name, {})
        if acquired.get("request") == "dispatched":
            execution.record.releases.append(
                ReleaseRecord(
                    resource=f"claim:{client.name}:{client.interface}",
                    kind="claim",
                    outcome="retained_until_process_retirement",
                    detail="product claims are never reset or deleted",
                )
            )
            execution.record.engine_residue.append(f"claim:{client.name}:retained")
    if "M-DHCP-6-TIME" in ids and not execution.stopped:
        _q3fl_timing(execution, state)
    _q3fl_conclude_dhcp(execution, state, ids)


def _sp2_first_probe_read(scan: LeaseScan) -> bool:
    """Observe an index-only error for the explicitly bounded first probe.

    The owned diagnostic separately proves every client unbound. Index
    errors may motivate that one investigation, but grant neither absence,
    calibration, serving nor a second client's activation. Field failures
    and malformed observations do not qualify for this exception.
    """
    return scan.clean or (
        scan.cause in {"", "backend_scan_refused"}
        and bool(scan.entries)
        and all(
            type(item.get("index")) is int
            and item["index"] == index
            and item.get("return_kind") == "throw"
            and isinstance(item.get("error"), str)
            and bool(item["error"])
            and item.get("row") is None
            for index, item in enumerate(scan.entries)
        )
    )


def _sp2_native_dhcp(
    execution: Execution,
    state: _Q3FlState,
    contract: Q3ProductContract,
    configuration_runtime,
    context: ConfigurationRuntimeContext,
    ids: tuple[str, ...],
) -> None:
    """Sample one bound client twice before deciding whether to activate PC2."""
    pool = next(
        (
            action
            for action in contract.service_plan.actions
            if isinstance(action, ConfigureServerDhcpPool)
        ),
        None,
    )
    if pool is None or len(state.clients) != 2:
        execution.stop("sp2_pool_or_client_selection_not_exact")
        _q3fl_conclude_dhcp(execution, state, ids)
        return
    samples: list[dict[str, Any]] = []
    progression: dict[str, Any] = {}
    preclient_scans: list[dict[str, Any]] = []
    first_preclient_complete = False
    first_last_sample: (
        tuple[ClientReading, Mapping[str, object], LeaseScan, LeaseScan] | None
    ) = None
    for ordinal, client in enumerate(state.clients):
        if client.name not in state.admitted or execution.stopped:
            progression[client.name] = {
                "admitted": False,
                "causes": ["forwarding_or_stop"],
            }
            break
        unbound = read_acquisition_clients(
            execution, state, f"before_client_mode:{client.name}"
        )
        names = (
            tuple(item.name for item in state.clients)
            if ordinal == 0
            else (client.name,)
        )
        if any(
            (item := unbound.get(name)) is None
            or not item.observed
            or item.mode is not False
            or item.ipv4 not in ("", "0.0.0.0")
            for name in names
        ):
            reason = (
                "sp2_clients_not_unbound_after_enable"
                if ordinal == 0
                else "sp2_second_client_not_unbound"
            )
            execution.stop(reason)
            progression[client.name] = {"admitted": False, "causes": [reason]}
            break
        preclient = scan_dhcp_pools(
            execution, state, f"before_client_mode:{client.name}"
        )
        preclient_scans.append(
            {
                "client": client.name,
                "pools": {name: scan.as_facts() for name, scan in preclient.items()},
            }
        )
        named_before = preclient.get(Q3_POOL)
        default_before = preclient.get("serverPool")
        if (
            named_before is None
            or default_before is None
            or not (
                _sp2_first_probe_read(named_before)
                if ordinal == 0
                else named_before.observed
            )
            or not (
                _sp2_first_probe_read(default_before)
                if ordinal == 0
                else default_before.observed
            )
        ):
            reason = "sp2_preclient_pool_scan_unobserved"
        elif ordinal == 0 and (named_before.rows or default_before.rows):
            reason = "sp2_preclient_lease_rows_present"
        elif ordinal > 0 and (not named_before.clean or not default_before.clean):
            reason = "sp2_second_client_preclient_scan_incomplete"
        elif ordinal > 0 and any(
            normalized_mac(row.mac) == normalized_mac(unbound[client.name].mac)
            for scan in (named_before, default_before)
            for row in scan.rows
        ):
            reason = "sp2_second_client_preexisting_lease"
        else:
            reason = ""
        if reason:
            execution.stop(reason)
            progression[client.name] = {"admitted": False, "causes": [reason]}
            break
        if ordinal == 0:
            first_preclient_complete = named_before.clean and default_before.clean
        if ordinal > 0 and first_last_sample is not None:
            first_name = state.clients[0].name
            recheck_binding = read_client_binding(
                execution, first_name, f"before_second_client:{first_name}"
            )
            first_now = unbound.get(
                first_name, ClientReading(first_name, False, cause="unread")
            )
            still_attributed, recheck_causes = sp2_client_progression(
                (first_last_sample[0], first_now),
                (first_last_sample[1], recheck_binding),
                (first_last_sample[2], named_before),
                (first_last_sample[3], default_before),
                named_range=AddressRange(pool.lease_start, pool.lease_end),
                expected_mask=pool.netmask,
                expected_gateway=pool.gateway,
                expected_dns=pool.dns_server,
            )
            preclient_scans[-1]["first_client_recheck"] = {
                "client": first_name,
                "reading": first_now.__dict__,
                "binding": dict(recheck_binding),
                "admitted": still_attributed,
                "causes": list(recheck_causes),
            }
            if not still_attributed:
                reason = "sp2_first_client_attribution_drifted"
                execution.stop(reason)
                progression[first_name] = {
                    "admitted": False,
                    "causes": [reason, *recheck_causes],
                }
                progression[client.name] = {
                    "admitted": False,
                    "causes": [reason],
                }
                break
        cause = _q3fl_client_mode(
            execution,
            state,
            contract,
            configuration_runtime,
            context,
            device_names=(client.name,),
            label=f"after_client_mode:{client.name}",
        )
        if cause:
            execution.stop(cause)
            progression[client.name] = {"admitted": False, "causes": [cause]}
            break
        observed: list[ClientReading] = []
        bindings: list[Mapping[str, object]] = []
        named_scans: list[LeaseScan] = []
        native_scans: list[LeaseScan] = []
        for index in (1, 2):
            waited = execution.ledger.wait(
                Q3_FL_SETTLE_INTERVAL_SECONDS, execution.run.boundaries.sleep
            )
            if waited < Q3_FL_SETTLE_INTERVAL_SECONDS:
                execution.stop("sp2_sample_interval_not_available")
                break
            label = f"sample:{client.name}:{index}"
            reading = read_acquisition_clients(execution, state, label).get(
                client.name, ClientReading(client.name, False, cause="unread")
            )
            binding = read_client_binding(execution, client.name, label)
            scans = scan_dhcp_pools(execution, state, label)
            named = scans.get(Q3_POOL, LeaseScan(Q3_POOL, False, "scan_absent"))
            native = scans.get(
                "serverPool", LeaseScan("serverPool", False, "scan_absent")
            )
            observed.append(reading)
            bindings.append(binding)
            named_scans.append(named)
            native_scans.append(native)
            samples.append(
                {
                    "label": label,
                    "client": reading.__dict__,
                    "binding": dict(binding),
                    "named_scan": named.as_facts(),
                    "native_scan": native.as_facts(),
                }
            )
        if execution.stopped:
            progression[client.name] = {
                "admitted": False,
                "causes": [execution.record.primary_failure],
            }
            break
        permitted, causes = sp2_client_progression(
            observed,
            bindings,
            named_scans,
            native_scans,
            named_range=AddressRange(pool.lease_start, pool.lease_end),
            expected_mask=pool.netmask,
            expected_gateway=pool.gateway,
            expected_dns=pool.dns_server,
            preclient_complete=first_preclient_complete,
        )
        progression[client.name] = {"admitted": permitted, "causes": list(causes)}
        if not permitted:
            break
        if ordinal == 0:
            first_last_sample = (
                observed[-1],
                bindings[-1],
                named_scans[-1],
                native_scans[-1],
            )
    state.server_facts["sp2_samples"] = samples
    state.server_facts["sp2_progression"] = progression
    state.server_facts["sp2_preclient_scans"] = preclient_scans
    _q3fl_conclude_dhcp(execution, state, ids)


def _q3fl_repeat(
    execution: Execution,
    state: _Q3FlState,
    client: DhcpAcquisitionClient,
    action: AcquireDhcpLease,
    service_runtime,
) -> None:
    """Replay the identical acquisition once; the claim must send no dhcpRun."""
    with execution.ledger.effect_of("q3-fl:guard:acquisition_replay"):
        [guard] = service_runtime.apply_actions([action])
    post = read_acquisition_clients(execution, state, f"after_repeat:{client.name}")
    state.repeat = {
        "client": client.name,
        "action_id": action.id,
        "attempted": guard.attempted,
        "cause": guard.cause,
        "call_error": bool(guard.call_error),
        "dispatch": guard.dispatch.value,
        "result": guard.result.value,
        "after_label": f"after_repeat:{client.name}",
        "after": {
            "observed": post[client.name].observed,
            "ipv4": post[client.name].ipv4,
            "lease_time": post[client.name].lease_time,
        }
        if client.name in post
        else {},
    }
    # The runtime reports an own-claim replay as `attempted=None`: this
    # evaluation cannot speak for the earlier one. Its branch report is the
    # evidence that THIS evaluation reached no dhcpRun, because the claim
    # script calls it only on the no-claim path.
    refused = (
        guard.attempted is not True
        and guard.cause == "own_claim_replayed"
        and not guard.call_error
        and guard.dispatch is DispatchFact.ACCEPTED
        and guard.result is ResultFact.CORRELATED
    )
    if not refused:
        execution.stop("contradiction:q3fl_same_action_repeat_not_refused")


def _q3fl_timing(execution: Execution, state: _Q3FlState) -> None:
    """Two timed readings with no request, then the declared renewal horizon."""
    ledger = execution.ledger
    sleep = execution.run.boundaries.sleep
    read_acquisition_clients(execution, state, "timed_1")
    state.timing_labels.append("timed_1")
    ledger.wait(Q3_FL_TIMED_INTERVAL_SECONDS, sleep)
    read_acquisition_clients(execution, state, "timed_2")
    state.timing_labels.append("timed_2")
    for index in range(1, Q3_FL_RENEWAL_HORIZON_READS + 1):
        ledger.wait(Q3_FL_RENEWAL_INTERVAL_SECONDS, sleep)
        label = f"horizon_{index}"
        read_acquisition_clients(execution, state, label)
        state.timing_labels.append(label)
    scan_dhcp_pools(execution, state, "timing_end")


def _q3fl_scan_named(state: _Q3FlState, label: str) -> dict[str, LeaseScan]:
    return next((value for name, value in state.scans if name == label), {})


def _q3fl_conclude_dhcp(
    execution: Execution, state: _Q3FlState, ids: tuple[str, ...]
) -> None:
    """Conclude the table, acquisition, capacity, repeat and timing measurements."""
    capacity = execution.definition.dhcp_pool_capacity
    macs = [
        item.mac
        for _label, values in state.client_reads
        for item in values.values()
        if item.observed and item.mac
    ]
    labels_with_intended = [
        label
        for label, scans in state.scans
        if Q3_POOL in scans and scans[Q3_POOL].termination != "pool_absent"
    ]
    intended_calibration = assess_lease_calibration(
        [
            CalibrationState(label, _q3fl_scan_named(state, label)[Q3_POOL])
            for label in labels_with_intended
        ],
        pool=Q3_POOL,
        capacity=capacity,
        fixture_macs=macs,
    )
    native_calibrations = {
        name: assess_lease_calibration(
            [
                CalibrationState(label, scans[name])
                for label, scans in state.scans
                if name in scans
            ],
            pool=name,
            capacity=next(
                (
                    scans[name].capacity
                    for _label, scans in state.scans
                    if name in scans and scans[name].capacity is not None
                ),
                None,
            ),
            fixture_macs=macs,
        )
        for name in state.native_pools
    }
    if "M-DHCP-2" in ids:
        execution.conclude(
            "M-DHCP-2",
            Assessment(
                intended_calibration.conclusion,
                facts={
                    "intended": intended_calibration.as_facts(),
                    "native": {
                        name: item.as_facts()
                        for name, item in native_calibrations.items()
                    },
                    "scans": [
                        {
                            "label": label,
                            "pools": {
                                name: scan.as_facts() for name, scan in scans.items()
                            },
                        }
                        for label, scans in state.scans
                    ],
                },
                causes=list(intended_calibration.causes),
                limitations=list(intended_calibration.limitations),
            ),
        )
    intended_range, native_range, netmask = _q3fl_ranges(execution, state)
    native_name = state.native_pools[0] if state.native_pools else ""
    attributions: dict[str, ClientAttribution] = {}
    for client in state.clients:
        entry = state.acquisitions.get(client.name, {})
        if "after_label" not in entry:
            continue
        before = state.reading(entry["before_label"]).get(
            client.name, ClientReading(client.name, False, cause="unread")
        )
        after = state.reading(entry["after_label"]).get(
            client.name, ClientReading(client.name, False, cause="unread")
        )
        prior = _q3fl_scan_named(state, entry["prior_scan_label"])
        post = _q3fl_scan_named(state, entry["scan_label"])
        missing = LeaseScan(Q3_POOL, False, "scan_absent")
        attributions[client.name] = attribute_client(
            client.name,
            request=entry["request"],
            before=before,
            after=after,
            prior_intended=prior.get(Q3_POOL, missing),
            prior_native=prior.get(
                native_name, LeaseScan(native_name, False, "scan_absent")
            ),
            intended=post.get(Q3_POOL, missing),
            native=post.get(native_name, LeaseScan(native_name, False, "scan_absent")),
            intended_range=intended_range,
            native_range=native_range,
            netmask=netmask,
            intended_calibration=intended_calibration,
            native_calibration=native_calibrations.get(native_name),
        )
    if "M-DHCP-6" in ids:
        execution.conclude(
            "M-DHCP-6", _q3fl_acquisition_assessment(state, attributions)
        )
    if "M-SP2-POOL-IDENTITY" in ids:
        latest = state.latest_scans()
        recent_clients = state.client_reads[-1][1] if state.client_reads else {}
        native_pool = "serverPool"
        assessment = assess_sp2_pool_identity(
            tuple(client.name for client in state.clients),
            recent_clients,
            latest.get(Q3_POOL, LeaseScan(Q3_POOL, False, "scan_absent")),
            latest.get(native_pool, LeaseScan(native_pool, False, "scan_absent")),
            named_pool=Q3_POOL,
            native_pool=native_pool,
            native_calibration=native_calibrations.get(native_pool),
            named_range=intended_range,
            expected_netmask=netmask,
            other_pools=tuple(
                name for name in state.native_pools if name != native_pool
            ),
        )
        if execution.definition.stage is QualificationStage.SP2_NATIVE_POOL:
            assessment.facts["samples"] = state.server_facts.get("sp2_samples", [])
            progression = state.server_facts.get("sp2_progression", {})
            assessment.facts["progression"] = progression
            assessment.facts["mode_effects"] = state.server_facts.get(
                "sp2_mode_effects", []
            )
            assessment.facts["preclient_scans"] = state.server_facts.get(
                "sp2_preclient_scans", []
            )
            preclient_sets = [
                scans
                for label, scans in state.scans
                if label.startswith("before_client_mode:")
            ]
            preclient_complete = len(preclient_sets) == len(state.clients) and all(
                scan.clean for scans in preclient_sets for scan in scans.values()
            )
            assessment = cap_sp2_pool_identity(
                assessment,
                progression,
                tuple(client.name for client in state.clients),
                preclient_complete=preclient_complete,
            )
        execution.conclude(
            "M-SP2-POOL-IDENTITY",
            assessment,
        )
    # A measurement whose procedure was never reached did not run: it is
    # NOT_RUN with the reason, never a RAN row that says nothing happened.
    stopped = execution.record.primary_failure or "not_reached"
    if "M-DHCP-6-CAP" in ids:
        if len(attributions) < 2:
            execution.not_run(
                ["M-DHCP-6-CAP"], f"capacity_negative_not_reached:{stopped}"
            )
        else:
            execution.conclude(
                "M-DHCP-6-CAP",
                _q3fl_capacity_assessment(state, attributions, capacity),
            )
    if "M-DHCP-6-REPEAT" in ids:
        if not state.repeat:
            execution.not_run(["M-DHCP-6-REPEAT"], f"repeat_not_reached:{stopped}")
        else:
            execution.conclude("M-DHCP-6-REPEAT", _q3fl_repeat_assessment(state))
    if "M-DHCP-6-TIME" in ids:
        if not state.timing_labels:
            execution.not_run(["M-DHCP-6-TIME"], f"timing_not_reached:{stopped}")
        else:
            execution.conclude("M-DHCP-6-TIME", _q3fl_timing_assessment(state))


def _q3fl_ranges(
    execution: Execution, state: _Q3FlState
) -> tuple[AddressRange, AddressRange | None, str]:
    """Return the compiled intended window and the observed native range."""
    contract = execution.product_contract
    pool = next(
        (
            item
            for item in (contract.service_plan.actions if contract is not None else [])
            if isinstance(item, ConfigureServerDhcpPool)
        ),
        None,
    )
    intended = (
        AddressRange(pool.lease_start, pool.lease_end)
        if pool is not None
        else AddressRange("0.0.0.0", "0.0.0.0")
    )
    netmask = pool.netmask if pool is not None else ""
    latest = next(
        (item for item in reversed(state.readings) if item.observed and item.rows), None
    )
    native = (
        AddressRange(str(latest.rows[0]["start"]), str(latest.rows[0]["end"]))
        if latest is not None
        else None
    )
    return intended, native, netmask


def _q3fl_reading_series(state: _Q3FlState) -> list[dict[str, Any]]:
    """Return every labelled client reading the run took, in order."""
    return [
        {
            "label": label,
            "clients": {
                name: {
                    "observed": item.observed,
                    "mode": item.mode,
                    "mac": item.mac,
                    "ipv4": item.ipv4,
                    "netmask": item.netmask,
                    "lease_time": item.lease_time,
                    "cause": item.cause,
                }
                for name, item in values.items()
            },
        }
        for label, values in state.client_reads
    ]


def _q3fl_acquisition_assessment(
    state: _Q3FlState, attributions: Mapping[str, ClientAttribution]
) -> Assessment:
    """Keep every client's claims separate; conclude only from all of them."""
    facts = {
        # Every reading, background and settle included: when an address
        # first appeared is itself evidence about autonomous acquisition.
        "client_readings": _q3fl_reading_series(state),
        "clients": {
            name: {**state.acquisitions.get(name, {}), "attribution": item.as_facts()}
            for name, item in attributions.items()
        },
        "not_requested": {
            name: entry
            for name, entry in state.acquisitions.items()
            if name not in attributions
        },
    }
    contradictions = [
        f"{name}:{item}"
        for name, value in attributions.items()
        for item in value.contradictions
    ]
    unknown = [
        name
        for name, entry in state.acquisitions.items()
        if str(entry.get("request", "")).startswith("outcome_unknown")
    ]
    requested = [
        name for name, value in attributions.items() if value.request == "dispatched"
    ]
    causes: list[str] = []
    if contradictions:
        return Assessment(
            MeasurementConclusion.CONTRADICTED,
            facts=facts,
            causes=contradictions,
            limitations=[NO_BACKGROUND_PROOF, NOT_DORA],
        )
    if unknown:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=[f"acquisition_outcome_unknown:{name}" for name in unknown],
            limitations=["no_later_effect_after_an_unknown_outcome"],
            outcome_unknown=True,
        )
    if not requested:
        causes.append("no_acquisition_dispatched")
    for name in requested:
        value = attributions[name]
        if value.served_by not in (SERVED_INTENDED, SERVED_NATIVE, SERVED_NONE):
            causes.append(f"serving_pool_not_attributed:{name}:{value.served_by}")
    return Assessment(
        MeasurementConclusion.INCONCLUSIVE
        if causes
        else MeasurementConclusion.SUPPORTED_IN_SAMPLE,
        facts=facts,
        causes=causes,
        limitations=[
            NO_BACKGROUND_PROOF,
            NOT_DORA,
            "dhcp_lease_read_back_is_never_promoted_to_verified",
            "an_in_range_address_alone_identifies_no_serving_pool",
        ],
    )


def _q3fl_capacity_assessment(
    state: _Q3FlState,
    attributions: Mapping[str, ClientAttribution],
    capacity: int,
) -> Assessment:
    """Decide the capacity-one negative from the first two clients, in order."""
    ordered = [
        attributions[item.name] for item in state.clients if item.name in attributions
    ]
    if len(ordered) < 2:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts={"clients": [item.as_facts() for item in ordered]},
            causes=["two_acquisitions_not_observed"],
        )
    final_scans = _q3fl_scan_named(
        state, state.acquisitions[ordered[1].client].get("scan_label", "")
    )
    result = assess_capacity_one_negative(
        first=ordered[0],
        second=ordered[1],
        intended=final_scans.get(Q3_POOL, LeaseScan(Q3_POOL, False, "scan_absent")),
        capacity=capacity,
    )
    return Assessment(
        result.conclusion,
        facts={**dict(result.facts), "result": result.result},
        causes=list(result.causes),
        limitations=[
            "a_timeout_without_an_address_is_not_pool_exhaustion",
            "native_default_service_is_not_intended_pool_success",
            "the_native_default_was_never_modified_to_rescue_the_control",
        ],
    )


def _q3fl_repeat_assessment(state: _Q3FlState) -> Assessment:
    """Judge the identical replay: its own claim reported, nothing sent."""
    repeat = state.repeat
    if not repeat:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts={},
            causes=["repeat_not_run:no_known_dispatch_to_replay"],
        )
    refused = (
        repeat.get("attempted") is not True
        and repeat.get("cause") == "own_claim_replayed"
        and not repeat.get("call_error")
        and repeat.get("dispatch") == DispatchFact.ACCEPTED.value
        and repeat.get("result") == ResultFact.CORRELATED.value
    )
    return Assessment(
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
        if refused
        else MeasurementConclusion.CONTRADICTED,
        facts=dict(repeat),
        causes=[] if refused else ["same_action_repeat_dispatched_or_unreadable"],
        limitations=[
            "evidence_is_the_claim_scripts_own_branch_report",
            "requested_renewal_is_a_different_operation_and_is_not_measured",
        ],
    )


def _q3fl_timing_assessment(state: _Q3FlState) -> Assessment:
    """Keep every raw lease-time reading; a changed string is not a renewal."""
    series: dict[str, list[dict[str, Any]]] = {}
    for label in ["timed_1", "timed_2", *state.timing_labels[2:]]:
        for name, item in state.reading(label).items():
            series.setdefault(name, []).append(
                {
                    "label": label,
                    "observed": item.observed,
                    "ipv4": item.ipv4,
                    "lease_time": item.lease_time,
                }
            )
    unread = [
        f"{name}:{row['label']}"
        for name, rows in series.items()
        for row in rows
        if not row["observed"]
    ]
    changed = [
        name
        for name, rows in series.items()
        if len({row["lease_time"] for row in rows if row["observed"]}) > 1
    ]
    causes = [f"timed_reading_unobserved:{item}" for item in unread] or [
        (
            "lease_time_string_changed_renewal_unproven"
            if changed
            else "automatic_renewal_not_observed_within_declared_horizon"
        )
    ]
    return Assessment(
        MeasurementConclusion.INCONCLUSIVE,
        facts={
            "series": series,
            "timed_interval_seconds": Q3_FL_TIMED_INTERVAL_SECONDS,
            "horizon_seconds": Q3_FL_RENEWAL_HORIZON_READS
            * Q3_FL_RENEWAL_INTERVAL_SECONDS,
            "changed_lease_strings": changed,
            "requested_renewal": REQUESTED_RENEWAL_CONTRACT_ABSENT,
        },
        causes=causes,
        limitations=[
            "no_clock_or_lease_manipulation",
            "no_explicit_request_is_not_proof_of_absent_background_traffic",
            "a_lease_string_change_is_not_renewal",
        ],
    )


def _q3fl_final(execution: Execution, state: _Q3FlState) -> None:
    """Read the native default and both tables once more, before cleanup."""
    ids = ("M-DHCP-1-FINAL",)
    if not execution.selected("Q3FL-final"):
        return
    if not execution.begin_terminal(ids, "Q3FL_FINAL"):
        return
    with execution.procedure(ids):
        permitted = native_default_snapshot(
            execution, state, "before_cleanup", _Q3FL_TERMINAL
        )
        scans = scan_dhcp_pools(execution, state, "before_cleanup")
        last = state.readings[-1] if state.readings else None
        observed = last is not None and last.observed and last.label == "before_cleanup"
        terminal = (
            state.sequence.intervals[-1]
            if state.sequence and state.sequence.intervals
            else None
        )
        drift = (
            terminal is not None
            and terminal.decision == INTERVAL_REFUSED
            and terminal.assessment.classification == UNEXPLAINED_DRIFT
        )
        if drift:
            conclusion = MeasurementConclusion.CONTRADICTED
        elif observed and permitted:
            conclusion = MeasurementConclusion.SUPPORTED_IN_SAMPLE
        else:
            conclusion = MeasurementConclusion.INCONCLUSIVE
        execution.conclude(
            "M-DHCP-1-FINAL",
            Assessment(
                conclusion,
                facts={
                    "native_default": native_default_facts(execution),
                    "native_default_sequence": _q3fl_sequence_facts(state),
                    "scans": {name: scan.as_facts() for name, scan in scans.items()},
                },
                causes=[]
                if conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
                else [_q3fl_policy_cause(state) or "final_reading_not_observed"],
                limitations=["terminal_reading_is_taken_whatever_the_sequence_did"],
            ),
        )
    execution.finish("Q3FL_FINAL")
