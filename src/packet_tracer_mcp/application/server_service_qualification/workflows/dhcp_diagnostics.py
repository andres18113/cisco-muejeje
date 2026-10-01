"""D-DHCP: the causal server-only DHCP sequence, one bounded step at a time."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ....domain.enterprise.models.configuration import (
    ConfigurationPlan,
    SetEndpointStaticAddress,
)
from ....domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationRuntimeContext,
)
from ....domain.enterprise.models.service_plan import (
    ConfigureServerDhcpPool,
    ServicePlan,
)
from ....domain.enterprise.models.service_qualification import (
    Q3_PC1,
    Q3_PC2,
    Q3_POOL,
    Q3_SERVER,
    DiagnosticPrecondition,
    MeasurementConclusion,
)
from ....domain.enterprise.models.service_runtime import ServiceApplicationResult
from ....domain.enterprise.services.qualification_product_evidence import (
    e5_foundation_cause,
    readback_not_observed_cause,
    service_result_cause,
)
from ....domain.enterprise.services.service_diagnostic_profiles import (
    d_dhcp_enable_only_plan,
    d_dhcp_pool_only_plan,
    d_dhcp_static_only_plan,
)
from ....domain.enterprise.services.service_qualification_evidence import (
    DIAGNOSTIC_SCOPE,
    Assessment,
    DefaultPoolSnapshot,
    assess_baseline_drift,
    assess_dhcp_baseline_admission,
    assess_native_default_cumulative,
    assess_native_default_interval,
)
from ...use_cases.apply_configuration import ConfigurationApplicator
from ...use_cases.apply_services import ServiceApplicator
from ...use_cases.foundational_evidence import derive_service_foundational_statuses
from ..contracts import Q3ProductContract
from ..dhcp_observations import (
    D_DHCP_DEFAULT_PURPOSE,
    native_default_facts,
    q3_client_rows,
    q3_default_observed,
    q3_default_purpose,
    q3_default_read,
)
from ..execution import Execution
from ..fixtures import await_readiness, diagnostic_start, fixture_endpoints
from ..operation_budget import counted_seq
from ..product_support import (
    DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE,
    exact_inventory_runtimes,
    product_runtime_context,
)


def run_d_dhcp(execution: Execution) -> None:
    """Run the causal server-only DHCP sequence, one bounded step at a time.

    Disabled baseline, the server's static addressing alone, the intended pool
    while the process is still disabled, the enable, the terminal reading. No
    client is activated, no lease is acquired, no default-pool setter is
    dispatched, and every adjacent pair of native readings is what the record
    attributes an interval to.
    """
    state = _DDhcpState()
    # Registered before the first fixture exists. Whatever the sequence below
    # does -- complete, stop, raise, or lose its record -- finalization takes
    # this reading over this exact state object, before it deletes anything.
    execution.register_terminal(
        ("M-DDHCP-4",), "D_DHCP_FINAL", lambda: _d_dhcp_final(execution, state)
    )
    if not diagnostic_start(execution):
        return
    contract = execution.product_contract
    if contract is None:  # pragma: no cover - admission composes it
        execution.stop("d_dhcp_product_contract_absent")
        return
    configuration_runtime, service_runtime = exact_inventory_runtimes(
        execution, contract
    )
    static_plan = d_dhcp_static_only_plan(
        contract.configuration_plan, device_name=Q3_SERVER
    )
    executed_ids = frozenset(item.id for item in static_plan.actions)
    context = product_runtime_context(contract)
    execution.record.limitations.extend(
        [
            "d_dhcp_private_candidate_capabilities:no_public_catalog_mutation",
            "d_dhcp_projection:server_static_address_only",
        ]
    )

    ids = ("M-DDHCP-0",)
    if execution.selected("D0-baseline") and execution.begin(ids, "D_DHCP_BASELINE"):
        with execution.procedure(ids):
            _d_dhcp_baseline(execution, state)
        execution.finish("D_DHCP_BASELINE")

    ids = ("M-DDHCP-1",)
    if execution.selected("D1-static") and execution.begin(ids, "D_DHCP_E5"):
        with execution.procedure(ids):
            _d_dhcp_static(
                execution, state, configuration_runtime, contract, static_plan, context
            )
        execution.finish("D_DHCP_E5")

    ids = ("M-DDHCP-2",)
    if execution.selected("D2-pool") and execution.begin(ids, "D_DHCP_POOL"):
        with execution.procedure(ids):
            _d_dhcp_pool(
                execution, state, service_runtime, contract, executed_ids, context
            )
        execution.finish("D_DHCP_POOL")

    ids = ("M-DDHCP-3",)
    if execution.selected("D3-enable") and execution.begin(ids, "D_DHCP_ENABLE"):
        with execution.procedure(ids):
            _d_dhcp_enable(
                execution, state, service_runtime, contract, executed_ids, context
            )
        execution.finish("D_DHCP_ENABLE")


def _d_dhcp_final(execution: Execution, state: _DDhcpState) -> None:
    """Read the native default inventory one last time, before any cleanup.

    It is a cumulative baseline-to-final summary of the interventions this run
    actually dispatched, not an adjacent interval: the sequence may have
    stopped anywhere, and what the operator needs is what the whole run left
    behind. No baseline is invented from it and no earlier snapshot is
    rewritten by it.
    """
    ids = ("M-DDHCP-4",)
    if not execution.selected("D4-final"):
        return
    if not execution.begin_terminal(ids, "D_DHCP_FINAL"):
        return
    with execution.procedure(ids):
        final = q3_default_read(
            execution, "d4_before_cleanup", prefix=D_DHCP_DEFAULT_PURPOSE
        )
        execution.conclude(
            "M-DDHCP-4",
            assess_native_default_cumulative(
                label="d4_cumulative",
                baseline=state.baseline,
                final=final,
                interventions=tuple(state.interventions),
                declared_native_calls=tuple(state.declared_native_calls),
            ),
        )
    execution.finish("D_DHCP_FINAL")


@dataclass
class _DDhcpState:
    """What one D-DHCP run has established, carried between its procedures."""

    baseline: DefaultPoolSnapshot | None = None
    control: DefaultPoolSnapshot | None = None
    after_static: DefaultPoolSnapshot | None = None
    after_pool: DefaultPoolSnapshot | None = None
    foundations: dict[str, ActionExecutionStatus] = field(default_factory=dict)
    last_intervention: str = "none:setup_only"
    native_calls: tuple[str, ...] = ()
    fields_written: tuple[str, ...] = ()
    rewrites: list[str] = field(default_factory=list)
    #: Every intervention this run actually dispatched, in order. The final
    #: reading spans all of them, so it is a cumulative summary and naming
    #: only the last one would attribute the whole span to one call.
    interventions: list[str] = field(default_factory=list)
    #: The generated call footprint each intervention declares. It is what
    #: the generator would emit, never a count of observed executions.
    declared_native_calls: list[str] = field(default_factory=list)

    def intervened(self, intervention: str, native_calls: Sequence[str]) -> None:
        """Record one dispatched intervention and its declared call footprint."""
        self.last_intervention = intervention
        self.interventions.append(intervention)
        self.declared_native_calls.extend(
            f"{intervention}:{item}" for item in native_calls
        )


def _d_dhcp_baseline(execution: Execution, state: _DDhcpState) -> None:
    """Establish a coherent disabled baseline and the drift control beside it."""
    clients = ((Q3_PC1, "FastEthernet0"), (Q3_PC2, "FastEthernet0"))
    # One dispatch serves both the typed admission rule and the run's first
    # native reading, exactly as Q3 does: the baseline costs one operation.
    start = len(execution.ledger.entries)
    with execution.ledger.purpose_of(
        q3_default_purpose("d0_baseline", D_DHCP_DEFAULT_PURPOSE)
    ):
        reading = execution.probes.read_dhcp_server_baseline(Q3_SERVER, "FastEthernet0")
    admission = assess_dhcp_baseline_admission(
        reading,
        server=Q3_SERVER,
        interface="FastEthernet0",
        intended_pool=Q3_POOL,
        observed_build=execution.record.environment.observed_build,
        qualified_build=execution.run.boundaries.q3_required_build,
        observed_channel=execution.channel,
        qualified_channels=execution.definition.allowed_channels,
    )
    state.baseline = q3_default_observed(
        execution,
        "d0_baseline",
        reading,
        operation_seq=counted_seq(execution.ledger, start),
        prefix=D_DHCP_DEFAULT_PURPOSE,
    )
    client_rows = q3_client_rows(execution.probes.read_dhcp_clients(clients))
    endpoints = fixture_endpoints(execution)
    gate = await_readiness(
        execution,
        endpoints,
        lambda timeout: execution.probes.read_port_readiness(endpoints, timeout),
        purpose="readiness:d_dhcp_fixture_links",
    )
    drift: Assessment | None = None
    if execution.selected("D0-control"):
        state.control = q3_default_read(
            execution, "d0_control", prefix=D_DHCP_DEFAULT_PURPOSE
        )
        drift = assess_baseline_drift(state.baseline, state.control)
    activated = [row for row in (client_rows or ()) if row.get("mode") is True]
    facts: dict[str, Any] = {
        "native_default": native_default_facts(execution),
        "clients": client_rows if client_rows is not None else [],
        "clients_readable": client_rows is not None,
        "readiness": gate.facts(),
        "baseline_admission": {
            "admitted": admission.admitted,
            "kind": admission.kind,
            "causes": list(admission.causes),
        },
    }
    causes: list[str] = []
    limitations = [
        DIAGNOSTIC_SCOPE,
        "client_dhcp_flags_are_never_written_by_this_stage",
    ]
    if drift is not None:
        facts.update(drift.facts)
        causes.extend(drift.causes)
        limitations.extend(drift.limitations)
    if not admission.admitted:
        causes.extend(["initial_dhcp_server_state_not_admissible", *admission.causes])
    if state.baseline is not None and not state.baseline.observed:
        causes.append(f"native_default_unobserved:{state.baseline.cause}")
    if client_rows is None:
        causes.append("client_rows_not_readable")
    if activated:
        causes.append("client_dhcp_mode_already_on")
    if not gate.ready:
        causes.append(f"readiness_not_established:{gate.reason}")
    conclusion = (
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
        if not causes
        else (
            MeasurementConclusion.CONTRADICTED
            if drift is not None
            and drift.conclusion is MeasurementConclusion.CONTRADICTED
            else MeasurementConclusion.INCONCLUSIVE
        )
    )
    execution.conclude(
        "M-DDHCP-0",
        Assessment(conclusion, facts=facts, causes=causes, limitations=limitations),
    )
    if causes:
        execution.stop(f"d_dhcp_baseline_not_established:{causes[0]}")
        return
    # A coherent retained inventory and a verified-off process are two
    # separate operational facts, and the admission rule asks for them by
    # name rather than reading this measurement's conclusion.
    execution.establish(
        DiagnosticPrecondition.INVENTORY_COHERENT,
        DiagnosticPrecondition.PROCESS_DISABLED_VERIFIED,
    )


def _d_dhcp_static(
    execution: Execution,
    state: _DDhcpState,
    configuration_runtime,
    contract: Q3ProductContract,
    static_plan: ConfigurationPlan,
    context: ConfigurationRuntimeContext,
) -> None:
    """Apply the server's static addressing alone and read the default again.

    The applied action is one `configurePcIp` call that writes the address,
    the netmask, the gateway and the DNS server together. That whole call is
    the intervention this interval is attributed to; no narrower cause is
    available from it and none is claimed.
    """
    if not execution.run.transition("experiment:D_DHCP_E5:started"):
        execution.stop("persistence:d_dhcp_e5_not_announced")
        return
    with execution.ledger.effect_of("d-dhcp:product:e5_server_address"):
        configuration = ConfigurationApplicator(configuration_runtime).apply(
            static_plan,
            actual_source_topology_hash=contract.manifest.physical_topology_hash,
            capabilities=contract.device_capabilities,
            runtime_context=context,
            deployment_manifest=contract.manifest,
        )
    foundation_plan = contract.service_plan.model_copy(
        update={
            "source_configuration_id": static_plan.id,
            "source_configuration_hash": static_plan.semantic_hash,
        },
        deep=True,
    )
    state.foundations = derive_service_foundational_statuses(
        foundation_plan, configuration
    )
    cause = e5_foundation_cause(
        configuration, state.foundations, {item.id for item in static_plan.actions}
    )
    action = next(iter(static_plan.actions), None)
    state.native_calls = ("configurePcIp",)
    state.fields_written = (
        ("ipv4", "netmask", "gateway", "dns_server")
        if isinstance(action, SetEndpointStaticAddress)
        else ()
    )
    state.intervened("e5:server_static_address:configurePcIp", state.native_calls)
    state.after_static = q3_default_read(
        execution, "d1_after_server_address", prefix=D_DHCP_DEFAULT_PURPOSE
    )
    assessment = assess_native_default_interval(
        label="d1_interval",
        before=state.control or state.baseline or state.after_static,
        after=state.after_static,
        intervention=state.last_intervention,
        native_calls=state.native_calls,
        fields_written=state.fields_written,
    )
    assessment.facts["e5"] = {
        "plan_id": static_plan.id,
        "actions": [item.id for item in static_plan.actions],
        "reported": [item.action_id for item in configuration.action_results],
        "action_results": [
            item.model_dump(mode="json") for item in configuration.action_results
        ],
        "foundation_cause": cause,
        "gateway": getattr(action, "gateway", ""),
        "dns_server": getattr(action, "dns_server", "") or "",
    }
    if cause:
        assessment.causes.append(cause)
        assessment = Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=assessment.facts,
            causes=assessment.causes,
            limitations=assessment.limitations,
            outcome_unknown=assessment.outcome_unknown,
        )
    execution.conclude("M-DDHCP-1", assessment)
    if cause:
        execution.stop(cause)
        return
    # The E5 row applied and its address read-back succeeded. Whether the
    # native default moved across the interval is the finding this stage
    # exists to report, and it is not a reason D2 cannot be attempted.
    execution.establish(DiagnosticPrecondition.SERVER_ADDRESSING)


def _d_dhcp_service_stage(
    execution: Execution,
    state: _DDhcpState,
    service_runtime,
    contract: Q3ProductContract,
    plan: ServicePlan,
    rewrites,
    context: ConfigurationRuntimeContext,
    *,
    purpose: str,
    intervention: str,
    native_calls: Sequence[str] = (),
) -> tuple[ServiceApplicationResult | None, str]:
    """Apply one projected E6 stage through the real product applicator."""
    state.rewrites.extend(item.as_text() for item in rewrites)
    with execution.ledger.effect_of(purpose):
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
    cause = service_result_cause(
        result,
        {item.id for item in plan.actions},
        expected_verification_ids={item.id for item in plan.verification_expectations},
    ) or readback_not_observed_cause(result)
    state.intervened(intervention, native_calls)
    return result, cause


def _d_dhcp_pool(
    execution: Execution,
    state: _DDhcpState,
    service_runtime,
    contract: Q3ProductContract,
    executed_ids: frozenset[str],
    context: ConfigurationRuntimeContext,
) -> None:
    """Write the intended pool with the process still disabled, and verify it."""
    plan, rewrites = d_dhcp_pool_only_plan(
        contract.service_plan, executed_configuration_action_ids=executed_ids
    )
    pool_action = next(
        (item for item in plan.actions if isinstance(item, ConfigureServerDhcpPool)),
        None,
    )
    pool_native_calls = (
        (
            "addPool",
            *(("addExcludedAddress",) if pool_action.excluded_ranges else ()),
            "setNetworkMask",
            "setDefaultRouter",
            *(("setDnsServerIp",) if pool_action.dns_server else ()),
            "setStartIp",
            "setEndIp",
            "setMaxUsers",
        )
        if pool_action is not None
        else ()
    )
    result, cause = _d_dhcp_service_stage(
        execution,
        state,
        service_runtime,
        contract,
        plan,
        rewrites,
        context,
        purpose="d-dhcp:product:e6_pool_disabled",
        intervention="e6:configure_server_dhcp_pool:process_disabled",
        native_calls=pool_native_calls,
    )
    state.after_pool = q3_default_read(
        execution, "d2_after_pool", prefix=D_DHCP_DEFAULT_PURPOSE
    )
    assessment = assess_native_default_interval(
        label="d2_interval",
        before=state.after_static or state.baseline or state.after_pool,
        after=state.after_pool,
        intervention=state.last_intervention,
        native_calls=pool_native_calls,
        fields_written=(
            "pool_name",
            "excluded_ranges",
            "network",
            "netmask",
            "gateway",
            "dns_server",
            "lease_start",
            "lease_end",
            "max_users",
        ),
    )
    row = next(iter(result.verification_results), None) if result else None
    assessment.facts["e6_pool"] = {
        "plan_id": plan.id,
        "rewrites": list(state.rewrites),
        "expected_enabled": False,
        "action_results": (
            [item.model_dump(mode="json") for item in result.action_results]
            if result is not None
            else []
        ),
        "verification": row.model_dump(mode="json") if row is not None else None,
        "cause": cause,
    }
    if cause:
        assessment.causes.append(cause)
        assessment = Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=assessment.facts,
            causes=assessment.causes,
            limitations=assessment.limitations,
        )
    execution.conclude("M-DDHCP-2", assessment)
    if cause:
        execution.stop(cause)
        return
    # The stored pool verified against `enabled=False` plus its exact fields,
    # which is the state D3's activation depends on.
    execution.establish(DiagnosticPrecondition.POOL_CONFIGURED)


def _d_dhcp_enable(
    execution: Execution,
    state: _DDhcpState,
    service_runtime,
    contract: Q3ProductContract,
    executed_ids: frozenset[str],
    context: ConfigurationRuntimeContext,
) -> None:
    """Enable the process after verified pool setup and read back the transition."""
    plan, rewrites = d_dhcp_enable_only_plan(
        contract.service_plan, executed_configuration_action_ids=executed_ids
    )
    result, cause = _d_dhcp_service_stage(
        execution,
        state,
        service_runtime,
        contract,
        plan,
        rewrites,
        context,
        purpose="d-dhcp:product:e6_enable",
        intervention="e6:enable_server_dhcp",
        native_calls=("setEnable",),
    )
    after = q3_default_read(execution, "d3_after_enable", prefix=D_DHCP_DEFAULT_PURPOSE)
    assessment = assess_native_default_interval(
        label="d3_interval",
        before=state.after_pool or state.baseline or after,
        after=after,
        intervention=state.last_intervention,
        native_calls=("setEnable",),
    )
    row = next(iter(result.verification_results), None) if result else None
    assessment.facts["e6_enable"] = {
        "plan_id": plan.id,
        "rewrites": [item.as_text() for item in rewrites],
        "expected_enabled": True,
        "action_results": (
            [item.model_dump(mode="json") for item in result.action_results]
            if result is not None
            else []
        ),
        "verification": row.model_dump(mode="json") if row is not None else None,
        "cause": cause,
    }
    if cause:
        assessment.causes.append(cause)
        assessment = Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=assessment.facts,
            causes=assessment.causes,
            limitations=assessment.limitations,
        )
    execution.conclude("M-DDHCP-3", assessment)
    if cause:
        execution.stop(cause)
        return
    execution.establish(DiagnosticPrecondition.PROCESS_ENABLED_VERIFIED)
