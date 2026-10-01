"""Native pool probes, stability and serving on the governed Q3 fixture.

Each stage extends the previous one: the start probe, the repeated start and
capacity, the compiled gateway, DNS and exclusions, the E5 reapplication
stability check, and the autonomous serving of one client.
"""

from __future__ import annotations

from typing import Any

from ....domain.enterprise.models.execution import DispatchFact
from ....domain.enterprise.models.service_plan import ConfigureServerDhcpPool
from ....domain.enterprise.models.service_qualification import (
    Q3_NATIVE_START_AFTER,
    Q3_NATIVE_START_BEFORE,
    Q3_NATIVE_START_EVIDENCE_SHA256,
    Q3_OBSERVED_NATIVE_DEFAULT_POOL,
    Q3_PC1,
    Q3_PC2,
    Q3_POOL,
    Q3_SERVER,
    MeasurementConclusion,
    QualificationStage,
)
from ....domain.enterprise.services.dhcp_lease_evidence import (
    ROW_EXACT,
    ROW_MAC_ELSEWHERE,
    ROW_WRONG_MAC,
    client_readings,
    is_dotted_mac,
    row_status,
    scans_by_pool,
    unobserved_scans,
)
from ....domain.enterprise.services.qualification_product_evidence import (
    e5_foundation_cause,
)
from ....domain.enterprise.services.service_diagnostic_profiles import (
    d_dhcp_static_only_plan,
    q3_fastloop_client_mode_plan,
)
from ....domain.enterprise.services.service_qualification_evidence import (
    Assessment,
    DefaultPoolSnapshot,
    assess_native_policy_address_probe,
    assess_native_policy_exclusion_probe,
    assess_native_pool_max_probe,
    assess_native_pool_repeated_start_probe,
    assess_native_pool_start_probe,
    native_policy_enabled_admitted,
    native_policy_exclusion_inventory_complete,
    native_policy_probe_baseline_admitted,
    native_policy_snapshot_complete,
    native_policy_terminal_inventory_complete,
    native_pool_probe_baseline_admitted,
)
from ...use_cases.apply_configuration import ConfigurationApplicator
from ...use_cases.foundational_evidence import derive_service_foundational_statuses
from ..contracts import Q3ProductContract
from ..dhcp_observations import (
    DhcpObservationState,
    dhcp_acquisition_clients,
    native_default_snapshot,
    q3_default_read,
)
from ..execution import Execution
from ..fixtures import await_readiness, diagnostic_start, fixture_endpoints
from ..product_support import (
    exact_inventory_runtimes,
    product_runtime_context,
    projection_foundations,
)

_Q3_NATIVE_POLICY_STAGES = frozenset(
    {
        QualificationStage.Q3_NATIVE_POLICY,
        QualificationStage.Q3_NATIVE_STABILITY,
        QualificationStage.Q3_NATIVE_SERVE,
    }
)


def _register_q3_native_terminal(execution: Execution) -> None:
    """Keep one final physical read after a stop or normal probe completion."""

    def final_read() -> None:
        ids = ("M-NATIVE-FINAL",)
        if not execution.begin_terminal(ids, "Q3_NATIVE_FINAL"):
            return
        with execution.procedure(ids):
            final = q3_default_read(
                execution,
                "native_before_cleanup",
                prefix="q3-native",
                policy=execution.definition.stage in _Q3_NATIVE_POLICY_STAGES,
            )
            complete = (
                native_policy_terminal_inventory_complete(
                    final, server=Q3_SERVER, interface="FastEthernet0"
                )
                if execution.definition.stage is QualificationStage.Q3_NATIVE_SERVE
                else native_policy_snapshot_complete(
                    final, server=Q3_SERVER, interface="FastEthernet0"
                )
                if execution.definition.stage in _Q3_NATIVE_POLICY_STAGES
                else final.observed
            )
            execution.conclude(
                "M-NATIVE-FINAL",
                Assessment(
                    MeasurementConclusion.SUPPORTED_IN_SAMPLE
                    if complete
                    else MeasurementConclusion.INCONCLUSIVE,
                    facts={
                        "observed": final.observed,
                        "complete": complete,
                        "pools": [dict(item) for item in final.pools],
                        "exclusions": final.raw.get("exclusions"),
                        "excluded_count": final.raw.get("excluded_count"),
                    },
                    causes=(
                        []
                        if complete
                        else [
                            final.cause
                            if not final.observed
                            else "native_policy_final_inventory_incomplete"
                        ]
                    ),
                ),
            )
        execution.finish("Q3_NATIVE_FINAL")

    execution.register_terminal(("M-NATIVE-FINAL",), "Q3_NATIVE_FINAL", final_read)


def _prepare_q3_native_server(
    execution: Execution,
) -> tuple[Q3ProductContract, DefaultPoolSnapshot, ConfigureServerDhcpPool] | None:
    """Apply the product's server address and admit only its reviewed move."""
    contract = execution.product_contract
    if contract is None:
        execution.stop("q3_native_product_contract_absent")
        return None
    pool_actions = [
        item
        for item in contract.service_plan.actions
        if isinstance(item, ConfigureServerDhcpPool)
    ]
    if (
        len(pool_actions) != 1
        or pool_actions[0].pool_name != Q3_POOL
        or pool_actions[0].host_device_id != "endpoint/q3/default/server/001"
        or pool_actions[0].host_device_name != Q3_SERVER
        or pool_actions[0].interface != "FastEthernet0"
        or pool_actions[0].segment_id != "q3-data"
    ):
        execution.stop("q3_native_requested_pool_ambiguous")
        return None
    state = DhcpObservationState()
    policy_mode = execution.definition.stage in _Q3_NATIVE_POLICY_STAGES
    if not native_default_snapshot(
        execution, state, "before_e5", "", policy=policy_mode
    ):
        execution.stop("q3_native_baseline_not_admitted")
        return None
    baseline_admitted = (
        native_policy_probe_baseline_admitted(
            state.snapshots[-1],
            server=Q3_SERVER,
            interface="FastEthernet0",
            expected_row=Q3_OBSERVED_NATIVE_DEFAULT_POOL,
            expected_exclusions=(),
        )
        if policy_mode
        else native_pool_probe_baseline_admitted(
            state.snapshots[-1],
            server=Q3_SERVER,
            interface="FastEthernet0",
            expected_row=Q3_OBSERVED_NATIVE_DEFAULT_POOL,
        )
    )
    if not baseline_admitted:
        execution.stop("q3_native_baseline_not_admitted")
        return None
    static_plan = d_dhcp_static_only_plan(
        contract.configuration_plan, device_name=Q3_SERVER
    )
    if len(static_plan.actions) != 1:
        execution.stop("q3_native_static_action_ambiguous")
        return None
    configuration_runtime, _ = exact_inventory_runtimes(execution, contract)
    if not execution.run.transition("experiment:Q3_NATIVE_E5:started"):
        execution.stop("persistence:q3_native_e5_not_announced")
        return None
    with execution.ledger.effect_of("q3-native:product:e5_server_address"):
        configuration = ConfigurationApplicator(configuration_runtime).apply(
            static_plan,
            actual_source_topology_hash=contract.manifest.physical_topology_hash,
            capabilities=contract.device_capabilities,
            runtime_context=product_runtime_context(contract),
            deployment_manifest=contract.manifest,
        )
    foundation_plan = contract.service_plan.model_copy(
        update={
            "source_configuration_id": static_plan.id,
            "source_configuration_hash": static_plan.semantic_hash,
        },
        deep=True,
    )
    foundations = derive_service_foundational_statuses(foundation_plan, configuration)
    cause = e5_foundation_cause(configuration, foundations, {static_plan.actions[0].id})
    if cause:
        execution.stop(cause)
        return None
    if not native_default_snapshot(
        execution,
        state,
        "after_server_address",
        execution.run.boundaries.reviewed_native_default_intervention,
        policy=policy_mode,
    ):
        execution.stop("q3_native_server_address_transition_not_admitted")
        return None
    after_address_admitted = (
        native_policy_probe_baseline_admitted(
            state.snapshots[-1],
            server=Q3_SERVER,
            interface="FastEthernet0",
            expected_row=Q3_NATIVE_START_BEFORE,
            expected_exclusions=(),
        )
        if policy_mode
        else native_pool_probe_baseline_admitted(
            state.snapshots[-1],
            server=Q3_SERVER,
            interface="FastEthernet0",
            expected_row=Q3_NATIVE_START_BEFORE,
        )
    )
    if not after_address_admitted:
        execution.stop("q3_native_process_not_disabled_after_e5")
        return None
    return contract, state.snapshots[-1], pool_actions[0]


def run_q3_native_probe(execution: Execution) -> None:
    """Bracket one documented native setter inside the governed Q3 fixture."""
    _register_q3_native_terminal(execution)
    if not diagnostic_start(execution):
        return
    ids = ("M-NATIVE-START",)
    if not execution.selected("NATIVE-start") or not execution.begin(
        ids, "Q3_NATIVE_START"
    ):
        return
    with execution.procedure(ids):
        prepared = _prepare_q3_native_server(execution)
        if prepared is None:
            return
        _, before, pool_action = prepared
        requested_start = pool_action.lease_start
        if not execution.run.transition("experiment:Q3_NATIVE_SETTER:started"):
            execution.stop("persistence:q3_native_setter_not_announced")
            return
        with execution.ledger.effect_of("q3-native:serverPool:setStartIp"):
            with execution.ledger.purpose_of("q3-native:serverPool:setStartIp"):
                probe = execution.probes.probe_native_pool_start(
                    Q3_SERVER, "FastEthernet0", requested_start
                )
        after = q3_default_read(execution, "after_native_start", prefix="q3-native")
        execution.conclude(
            "M-NATIVE-START",
            assess_native_pool_start_probe(
                before=before,
                probe=probe,
                after=after,
                server=Q3_SERVER,
                interface="FastEthernet0",
                requested_start=requested_start,
            ),
        )
    execution.finish("Q3_NATIVE_START")


def run_q3_native_size(
    execution: Execution,
) -> tuple[ConfigureServerDhcpPool, DefaultPoolSnapshot] | None:
    """Measure capacity after a separately proved repeat of episode 1's move."""
    _register_q3_native_terminal(execution)
    if not diagnostic_start(execution):
        return
    start_ids = ("M-NATIVE-REPEAT-START",)
    if not execution.selected("NATIVE-size") or not execution.begin(
        start_ids, "Q3_NATIVE_REPEAT_START"
    ):
        return
    with execution.procedure(start_ids):
        prepared = _prepare_q3_native_server(execution)
        if prepared is None:
            return
        _, before, pool_action = prepared
        if pool_action.lease_start != Q3_NATIVE_START_AFTER["start"]:
            execution.stop("q3_native_size_intent_differs_from_episode1")
            return
        if not execution.run.transition("experiment:Q3_NATIVE_REPEAT_SETTER:started"):
            execution.stop("persistence:q3_native_repeat_setter_not_announced")
            return
        with execution.ledger.effect_of("q3-native-size:serverPool:setStartIp"):
            with execution.ledger.purpose_of("q3-native-size:serverPool:setStartIp"):
                start_probe = execution.probes.probe_native_pool_start(
                    Q3_SERVER, "FastEthernet0", pool_action.lease_start
                )
        after_start = q3_default_read(
            execution,
            "after_native_repeat_start",
            prefix="q3-native-size",
            policy=execution.definition.stage in _Q3_NATIVE_POLICY_STAGES,
        )
        execution.conclude(
            "M-NATIVE-REPEAT-START",
            assess_native_pool_repeated_start_probe(
                before=before,
                probe=start_probe,
                after=after_start,
                server=Q3_SERVER,
                interface="FastEthernet0",
                expected_before=Q3_NATIVE_START_BEFORE,
                expected_after=Q3_NATIVE_START_AFTER,
                evidence_sha256=Q3_NATIVE_START_EVIDENCE_SHA256,
            ),
        )
    execution.finish("Q3_NATIVE_REPEAT_START")
    max_ids = ("M-NATIVE-MAX",)
    repeat = execution.measurement("M-NATIVE-REPEAT-START").conclusion
    if repeat is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
        execution.not_run(max_ids, f"repeat_start_not_supported:{repeat.value}")
        execution.stop(f"q3_native_size_repeat_start_not_supported:{repeat.value}")
        return
    if not execution.begin(max_ids, "Q3_NATIVE_MAX"):
        return
    with execution.procedure(max_ids):
        if pool_action.max_users != 1:
            execution.stop("q3_native_size_capacity_differs_from_intent")
            return
        if not execution.run.transition("experiment:Q3_NATIVE_MAX_SETTER:started"):
            execution.stop("persistence:q3_native_max_setter_not_announced")
            return
        with execution.ledger.effect_of("q3-native-size:serverPool:setMaxUsers"):
            with execution.ledger.purpose_of("q3-native-size:serverPool:setMaxUsers"):
                max_probe = execution.probes.probe_native_pool_max(
                    Q3_SERVER, "FastEthernet0", pool_action.max_users
                )
        after_max = q3_default_read(
            execution,
            "after_native_max",
            prefix="q3-native-size",
            policy=execution.definition.stage in _Q3_NATIVE_POLICY_STAGES,
        )
        execution.conclude(
            "M-NATIVE-MAX",
            assess_native_pool_max_probe(
                before=after_start,
                probe=max_probe,
                after=after_max,
                server=Q3_SERVER,
                interface="FastEthernet0",
                expected_before=Q3_NATIVE_START_AFTER,
                requested_max=pool_action.max_users,
            ),
        )
    execution.finish("Q3_NATIVE_MAX")
    if (
        execution.measurement("M-NATIVE-MAX").conclusion
        is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    ):
        return pool_action, after_max
    return None


def run_q3_native_policy(
    execution: Execution,
) -> tuple[ConfigureServerDhcpPool, DefaultPoolSnapshot] | None:
    """Probe compiled gateway, DNS and exclusions on one disabled native pool."""
    sized = run_q3_native_size(execution)
    if sized is None:
        if not execution.stopped:
            execution.stop("q3_native_policy_size_not_supported")
        return
    if not execution.selected("NATIVE-policy"):
        return
    pool_action, after_max = sized
    size_row = {
        **dict(Q3_NATIVE_START_AFTER),
        "end": pool_action.lease_end,
        "max": pool_action.max_users,
    }
    if (
        pool_action.max_users != 1
        or pool_action.lease_start != size_row["start"]
        or pool_action.lease_end != size_row["end"]
    ):
        execution.stop("q3_native_policy_intent_differs_from_size_measurement")
        return
    if not native_pool_probe_baseline_admitted(
        after_max,
        server=Q3_SERVER,
        interface="FastEthernet0",
        expected_row=size_row,
    ):
        execution.stop("q3_native_policy_size_readback_not_admitted")
        return
    before_gateway = q3_default_read(
        execution, "before_native_gateway", prefix="q3-native-policy", policy=True
    )
    if not native_policy_probe_baseline_admitted(
        before_gateway,
        server=Q3_SERVER,
        interface="FastEthernet0",
        expected_row=size_row,
        expected_exclusions=(),
    ):
        execution.stop("q3_native_policy_baseline_not_admitted")
        return
    gateway_row = {**size_row, "gateway": pool_action.gateway}
    ids = ("M-NATIVE-GATEWAY",)
    if not execution.begin(ids, "Q3_NATIVE_GATEWAY"):
        return
    with execution.procedure(ids):
        if not execution.run.transition("experiment:Q3_NATIVE_GATEWAY_SETTER:started"):
            execution.stop("persistence:q3_native_gateway_not_announced")
            return
        with execution.ledger.effect_of("q3-native-policy:serverPool:setDefaultRouter"):
            with execution.ledger.purpose_of(
                "q3-native-policy:serverPool:setDefaultRouter"
            ):
                gateway_probe = execution.probes.probe_native_pool_gateway(
                    Q3_SERVER, "FastEthernet0", pool_action.gateway
                )
        after_gateway = q3_default_read(
            execution, "after_native_gateway", prefix="q3-native-policy", policy=True
        )
        gateway_result = assess_native_policy_address_probe(
            before=before_gateway,
            probe=gateway_probe,
            after=after_gateway,
            server=Q3_SERVER,
            interface="FastEthernet0",
            field="gateway",
            expected_before=size_row,
            expected_after=gateway_row,
            expected_exclusions=(),
        )
        execution.conclude("M-NATIVE-GATEWAY", gateway_result)
    execution.finish("Q3_NATIVE_GATEWAY")
    if gateway_result.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
        execution.stop("q3_native_policy_gateway_not_supported")
        return

    dns_row = {**gateway_row, "dns": pool_action.dns_server}
    ids = ("M-NATIVE-DNS",)
    if not execution.begin(ids, "Q3_NATIVE_DNS"):
        return
    with execution.procedure(ids):
        if not execution.run.transition("experiment:Q3_NATIVE_DNS_SETTER:started"):
            execution.stop("persistence:q3_native_dns_not_announced")
            return
        with execution.ledger.effect_of("q3-native-policy:serverPool:setDnsServerIp"):
            with execution.ledger.purpose_of(
                "q3-native-policy:serverPool:setDnsServerIp"
            ):
                dns_probe = execution.probes.probe_native_pool_dns(
                    Q3_SERVER, "FastEthernet0", pool_action.dns_server
                )
        after_dns = q3_default_read(
            execution, "after_native_dns", prefix="q3-native-policy", policy=True
        )
        dns_result = assess_native_policy_address_probe(
            before=after_gateway,
            probe=dns_probe,
            after=after_dns,
            server=Q3_SERVER,
            interface="FastEthernet0",
            field="dns",
            expected_before=gateway_row,
            expected_after=dns_row,
            expected_exclusions=(),
        )
        execution.conclude("M-NATIVE-DNS", dns_result)
    execution.finish("Q3_NATIVE_DNS")
    if dns_result.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
        execution.stop("q3_native_policy_dns_not_supported")
        return

    ranges = [item.model_dump(mode="json") for item in pool_action.excluded_ranges]
    if (
        len(ranges) != 2
        or ranges[0] != {"start": pool_action.gateway, "end": pool_action.gateway}
        or ranges[1] != {"start": pool_action.dns_server, "end": pool_action.dns_server}
    ):
        execution.stop("q3_native_policy_exclusions_differ_from_intent")
        return
    ids = ("M-NATIVE-EXCLUSIONS",)
    if not execution.begin(ids, "Q3_NATIVE_EXCLUSIONS"):
        return
    before_exclusion = after_dns
    completed: list[Assessment] = []
    with execution.procedure(ids):
        for index, wanted in enumerate(ranges, start=1):
            if not execution.run.transition(
                f"experiment:Q3_NATIVE_EXCLUSION_{index}:started"
            ):
                execution.stop("persistence:q3_native_exclusion_not_announced")
                return
            purpose = f"q3-native-policy:exclude:{index}"
            with execution.ledger.effect_of(purpose):
                with execution.ledger.purpose_of(purpose):
                    exclusion_probe = execution.probes.probe_native_exclusion(
                        Q3_SERVER,
                        "FastEthernet0",
                        wanted["start"],
                        wanted["end"],
                        expected_prior=ranges[: index - 1],
                    )
            after_exclusion = q3_default_read(
                execution,
                f"after_native_exclusion_{index}",
                prefix="q3-native-policy",
                policy=True,
            )
            assessment = assess_native_policy_exclusion_probe(
                before=before_exclusion,
                probe=exclusion_probe,
                after=after_exclusion,
                server=Q3_SERVER,
                interface="FastEthernet0",
                expected_row=dns_row,
                expected_before=ranges[: index - 1],
                added=wanted,
            )
            completed.append(assessment)
            if assessment.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
                execution.conclude("M-NATIVE-EXCLUSIONS", assessment)
                execution.stop(f"q3_native_policy_exclusion_{index}_not_supported")
                break
            before_exclusion = after_exclusion
        else:
            execution.conclude(
                "M-NATIVE-EXCLUSIONS",
                Assessment(
                    MeasurementConclusion.SUPPORTED_IN_SAMPLE,
                    facts={
                        **completed[-1].facts,
                        "steps": [item.facts for item in completed],
                        "compiled_exclusions": ranges,
                    },
                    limitations=[
                        "stored_policy_is_not_serving_or_reapplication_evidence"
                    ],
                ),
            )
    execution.finish("Q3_NATIVE_EXCLUSIONS")
    if (
        execution.measurement("M-NATIVE-EXCLUSIONS").conclusion
        is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    ):
        return pool_action, before_exclusion
    return None


def run_q3_native_stability(
    execution: Execution,
) -> tuple[ConfigureServerDhcpPool, DefaultPoolSnapshot] | None:
    """Reapply E5 and compare the complete disabled native policy."""
    prepared = run_q3_native_policy(execution)
    if prepared is None:
        if not execution.stopped:
            execution.stop("q3_native_stability_policy_not_supported")
        return
    if not execution.selected("NATIVE-stability"):
        return
    pool_action, before = prepared
    expected_row = {
        **dict(Q3_NATIVE_START_AFTER),
        "end": pool_action.lease_end,
        "max": pool_action.max_users,
        "gateway": pool_action.gateway,
        "dns": pool_action.dns_server,
    }
    exclusions = [item.model_dump(mode="json") for item in pool_action.excluded_ranges]
    if not native_policy_probe_baseline_admitted(
        before,
        server=Q3_SERVER,
        interface="FastEthernet0",
        expected_row=expected_row,
        expected_exclusions=exclusions,
    ):
        execution.stop("q3_native_stability_precondition_unobserved")
        return
    contract = execution.product_contract
    if contract is None:
        execution.stop("q3_native_stability_product_contract_absent")
        return
    static_plan = d_dhcp_static_only_plan(
        contract.configuration_plan, device_name=Q3_SERVER
    )
    if len(static_plan.actions) != 1:
        execution.stop("q3_native_stability_static_action_ambiguous")
        return
    ids = ("M-NATIVE-STABILITY",)
    if not execution.begin(ids, "Q3_NATIVE_STABILITY"):
        return
    with execution.procedure(ids):
        if not execution.run.transition("experiment:Q3_NATIVE_STABILITY_E5:started"):
            execution.stop("persistence:q3_native_stability_e5_not_announced")
            return
        configuration_runtime, _ = exact_inventory_runtimes(execution, contract)
        e5_start = len(execution.ledger.entries)
        with execution.ledger.effect_of(
            "q3-native-stability:product:e5_server_address"
        ):
            result = ConfigurationApplicator(configuration_runtime).apply(
                static_plan,
                actual_source_topology_hash=contract.manifest.physical_topology_hash,
                capabilities=contract.device_capabilities,
                runtime_context=product_runtime_context(contract),
                deployment_manifest=contract.manifest,
            )
        e5_operations = execution.ledger.entries[e5_start:]
        unknown_dispatches = [
            item.seq
            for item in e5_operations
            if item.dispatch == DispatchFact.ACCEPTANCE_UNKNOWN.value
        ]
        foundations = projection_foundations(contract, static_plan, result)
        cause = e5_foundation_cause(result, foundations, {static_plan.actions[0].id})
        if unknown_dispatches:
            cause = "outcome_unknown:q3_native_stability_e5_dispatch"
        after = q3_default_read(
            execution,
            "after_native_e5_reapplication",
            prefix="q3-native-stability",
            policy=True,
        )
        after_exact = native_policy_probe_baseline_admitted(
            after,
            server=Q3_SERVER,
            interface="FastEthernet0",
            expected_row=expected_row,
            expected_exclusions=exclusions,
        )
        facts = {
            "before": dict(before.raw),
            "after": dict(after.raw),
            "product_action_results": [
                item.model_dump(mode="json") for item in result.action_results
            ],
            "product_verification_results": [
                item.model_dump(mode="json") for item in result.verification_results
            ],
            "e5_operations": [item.model_dump(mode="json") for item in e5_operations],
            "unknown_dispatch_seqs": unknown_dispatches,
        }
        conclusion = (
            MeasurementConclusion.INCONCLUSIVE
            if cause
            or not after.observed
            or not native_policy_exclusion_inventory_complete(after)
            else MeasurementConclusion.SUPPORTED_IN_SAMPLE
            if after_exact
            else MeasurementConclusion.CONTRADICTED
        )
        assessment = Assessment(
            conclusion,
            facts=facts,
            causes=(
                [cause]
                if cause
                else [f"native_policy_after_unobserved:{after.cause}"]
                if not after.observed
                else ["native_policy_after_exclusions_incomplete"]
                if not native_policy_exclusion_inventory_complete(after)
                else []
                if after_exact
                else ["native_policy_changed_or_incomplete_after_e5_reapplication"]
            ),
            limitations=[
                "e5_fire_and_forget_does_not_prove_setter_success",
                "unchanged_state_does_not_prove_native_setter_idempotence",
                "restart_reload_not_measured",
            ],
            outcome_unknown=cause.startswith("outcome_unknown"),
        )
        execution.conclude("M-NATIVE-STABILITY", assessment)
    execution.finish("Q3_NATIVE_STABILITY")
    if assessment.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
        execution.stop("q3_native_stability_not_supported")
        return None
    return pool_action, after


def run_q3_native_serve(execution: Execution) -> None:
    """Test one autonomous client against the exact enabled physical pool."""
    stable = run_q3_native_stability(execution)
    if stable is None:
        if not execution.stopped:
            execution.stop("q3_native_serve_stability_not_supported")
        return
    if not execution.selected("NATIVE-serve"):
        return
    pool_action, before_enable = stable
    row = {
        **dict(Q3_NATIVE_START_AFTER),
        "end": pool_action.lease_end,
        "max": pool_action.max_users,
        "gateway": pool_action.gateway,
        "dns": pool_action.dns_server,
    }
    exclusions = [item.model_dump(mode="json") for item in pool_action.excluded_ranges]
    if not native_policy_probe_baseline_admitted(
        before_enable,
        server=Q3_SERVER,
        interface="FastEthernet0",
        expected_row=row,
        expected_exclusions=exclusions,
    ):
        execution.stop("q3_native_serve_disabled_policy_not_admitted")
        return
    contract = execution.product_contract
    if contract is None:
        execution.stop("q3_native_serve_product_contract_absent")
        return
    clients = [
        item
        for item in dhcp_acquisition_clients(contract)
        if item.name in {Q3_PC1, Q3_PC2} and item.interface == "FastEthernet0"
    ]
    if len(clients) != 2 or {item.name for item in clients} != {Q3_PC1, Q3_PC2}:
        execution.stop("q3_native_serve_client_binding_ambiguous")
        return
    by_name = {item.name: item for item in clients}
    client = by_name[Q3_PC1]
    inactive_client = by_name[Q3_PC2]
    client_pairs = (
        (client.name, client.interface),
        (inactive_client.name, inactive_client.interface),
    )
    ids = ("M-NATIVE-ENABLE",)
    if not execution.begin(ids, "Q3_NATIVE_ENABLE"):
        return
    with execution.procedure(ids):
        with execution.ledger.purpose_of("q3-native-serve:clients:before_enable"):
            prior_clients_read = execution.probes.read_dhcp_clients(client_pairs)
        prior_clients = client_readings(
            prior_clients_read.payload if prior_clients_read.observed else {},
            (client.name, inactive_client.name),
        )
        clients_clear = all(
            item.observed
            and item.mode is False
            and item.ipv4 in {"", "0.0.0.0"}
            and item.netmask in {"", "0.0.0.0"}
            and is_dotted_mac(item.mac)
            for item in prior_clients.values()
        )
        if not clients_clear:
            execution.conclude(
                "M-NATIVE-ENABLE",
                Assessment(
                    MeasurementConclusion.INCONCLUSIVE,
                    facts={
                        "prior_clients": {
                            name: item.__dict__ for name, item in prior_clients.items()
                        }
                    },
                    causes=["native_enable_clients_not_inactive"],
                ),
            )
            execution.stop("q3_native_serve_clients_not_inactive")
            return
        if not execution.run.transition("experiment:Q3_NATIVE_ENABLE:started"):
            execution.stop("persistence:q3_native_enable_not_announced")
            return
        with execution.ledger.effect_of("q3-native-serve:serverPool:setEnable"):
            with execution.ledger.purpose_of("q3-native-serve:serverPool:setEnable"):
                probe = execution.probes.probe_native_server_enable(
                    Q3_SERVER, "FastEthernet0", row, exclusions, client_pairs
                )
        enabled = q3_default_read(
            execution, "after_native_enable", prefix="q3-native-serve", policy=True
        )
        payload = probe.payload if probe.observed else {}
        policy_ok = native_policy_enabled_admitted(
            enabled,
            server=Q3_SERVER,
            interface="FastEthernet0",
            expected_row=row,
            expected_exclusions=exclusions,
        )
        enabled_ok = (
            probe.observed
            and payload.get("device") == Q3_SERVER
            and payload.get("interface") == "FastEthernet0"
            and payload.get("found") is True
            and payload.get("policy_match") is True
            and payload.get("clients_clear") is True
            and payload.get("attempted") is True
            and payload.get("call_error") == ""
            and payload.get("pre_enabled") is False
            and payload.get("post_enabled") is True
            and policy_ok
        )
        assessment = Assessment(
            MeasurementConclusion.SUPPORTED_IN_SAMPLE
            if enabled_ok
            else MeasurementConclusion.INCONCLUSIVE
            if not probe.observed or not enabled.observed or payload.get("call_error")
            else MeasurementConclusion.CONTRADICTED,
            facts={
                "before": dict(before_enable.raw),
                "prior_clients": {
                    name: item.__dict__ for name, item in prior_clients.items()
                },
                "probe": dict(payload),
                "after": dict(enabled.raw),
                "policy_exact": policy_ok,
            },
            causes=[] if enabled_ok else ["native_enable_unobserved_or_policy_changed"],
            outcome_unknown=not probe.observed
            or (payload.get("attempted") is True and bool(payload.get("call_error"))),
            limitations=["enable_does_not_establish_client_serving"],
        )
        execution.conclude("M-NATIVE-ENABLE", assessment)
    execution.finish("Q3_NATIVE_ENABLE")
    if assessment.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
        execution.stop("q3_native_serve_enable_not_supported")
        return

    ids = ("M-NATIVE-MODE",)
    if not execution.begin(ids, "Q3_NATIVE_MODE"):
        return
    with execution.procedure(ids):
        endpoints = fixture_endpoints(execution)
        readiness = await_readiness(
            execution,
            endpoints,
            lambda timeout: execution.probes.read_port_readiness(endpoints, timeout),
            purpose="readiness:q3_native_client_mode",
        )
        if not readiness.ready:
            execution.conclude(
                "M-NATIVE-MODE",
                Assessment(
                    MeasurementConclusion.INCONCLUSIVE,
                    facts={"readiness": readiness.facts()},
                    causes=[f"native_client_forwarding_unobserved:{readiness.reason}"],
                ),
            )
            execution.stop("q3_native_client_forwarding_unobserved")
            return
        with execution.ledger.purpose_of("q3-native-serve:client:before_mode"):
            prior_read = execution.probes.read_dhcp_clients(client_pairs)
        before_mode_clients = client_readings(
            prior_read.payload if prior_read.observed else {},
            (client.name, inactive_client.name),
        )
        prior = before_mode_clients[client.name]
        prior_inactive = before_mode_clients[inactive_client.name]
        before_mode_policy = q3_default_read(
            execution,
            "before_native_client_mode",
            prefix="q3-native-serve",
            policy=True,
        )
        if (
            not prior.observed
            or prior.mode is not False
            or prior.ipv4 not in {"", "0.0.0.0"}
            or prior.netmask not in {"", "0.0.0.0"}
            or not is_dotted_mac(prior.mac)
            or not prior_inactive.observed
            or prior_inactive.mode is not False
            or prior_inactive.ipv4 not in {"", "0.0.0.0"}
            or prior_inactive.netmask not in {"", "0.0.0.0"}
            or prior_inactive.mac != prior_clients[inactive_client.name].mac
            or prior.mac != prior_clients[client.name].mac
            or not native_policy_enabled_admitted(
                before_mode_policy,
                server=Q3_SERVER,
                interface="FastEthernet0",
                expected_row=row,
                expected_exclusions=exclusions,
            )
        ):
            execution.stop("q3_native_serve_client_mode_precondition_unobserved")
            return
        plan = q3_fastloop_client_mode_plan(
            contract.configuration_plan, device_names=(client.name,)
        )
        if (
            len(plan.actions) != 1
            or plan.actions[0].device_id != client.device_id
            or plan.actions[0].device_name != client.name
            or plan.actions[0].interface != client.interface
        ):
            execution.stop("q3_native_serve_client_mode_action_ambiguous")
            return
        if not execution.run.transition("experiment:Q3_NATIVE_MODE_PROBE:started"):
            execution.stop("persistence:q3_native_mode_not_announced")
            return
        with execution.ledger.effect_of("q3-native-serve:compiled-client-mode"):
            with execution.ledger.purpose_of("q3-native-serve:compiled-client-mode"):
                mode_probe = execution.probes.probe_native_client_mode(
                    Q3_SERVER,
                    "FastEthernet0",
                    client.name,
                    client.interface,
                    row,
                    exclusions,
                    ((inactive_client.name, inactive_client.interface),),
                )
        probe_payload = mode_probe.payload if mode_probe.observed else {}
        probe_exact = (
            mode_probe.observed
            and probe_payload.get("server") == Q3_SERVER
            and probe_payload.get("server_interface") == "FastEthernet0"
            and probe_payload.get("client") == client.name
            and probe_payload.get("client_interface") == client.interface
            and probe_payload.get("policy_match") is True
            and probe_payload.get("inactive_clients_clear") is True
            and probe_payload.get("client_found") is True
            and probe_payload.get("attempted") is True
            and probe_payload.get("call_error") == ""
            and probe_payload.get("pre_mode") is False
            and probe_payload.get("post_mode") is True
        )
        with execution.ledger.purpose_of("q3-native-serve:client:after_mode"):
            after_read = execution.probes.read_dhcp_clients(client_pairs)
        after_clients = client_readings(
            after_read.payload if after_read.observed else {},
            (client.name, inactive_client.name),
        )
        after_client = after_clients[client.name]
        after_inactive = after_clients[inactive_client.name]
        after_mode_policy = q3_default_read(
            execution, "after_native_client_mode", prefix="q3-native-serve", policy=True
        )
        mode_ok = (
            probe_exact
            and after_client.observed
            and after_client.mode is True
            and after_client.mac == prior.mac
            and after_inactive.observed
            and after_inactive.mode is False
            and after_inactive.ipv4 in {"", "0.0.0.0"}
            and after_inactive.netmask in {"", "0.0.0.0"}
            and after_inactive.mac == prior_inactive.mac
            and native_policy_enabled_admitted(
                after_mode_policy,
                server=Q3_SERVER,
                interface="FastEthernet0",
                expected_row=row,
                expected_exclusions=exclusions,
            )
        )
        mode_policy_contradicted = (
            after_mode_policy.observed
            and native_policy_exclusion_inventory_complete(after_mode_policy)
            and not native_policy_enabled_admitted(
                after_mode_policy,
                server=Q3_SERVER,
                interface="FastEthernet0",
                expected_row=row,
                expected_exclusions=exclusions,
            )
        )
        inactive_client_contradicted = after_inactive.observed and (
            after_inactive.mode is not False
            or after_inactive.ipv4 not in {"", "0.0.0.0"}
            or after_inactive.netmask not in {"", "0.0.0.0"}
            or after_inactive.mac != prior_inactive.mac
        )
        mode_assessment = Assessment(
            MeasurementConclusion.SUPPORTED_IN_SAMPLE
            if mode_ok
            else MeasurementConclusion.CONTRADICTED
            if (mode_policy_contradicted or inactive_client_contradicted)
            and mode_probe.observed
            else MeasurementConclusion.INCONCLUSIVE,
            facts={
                "before_client": prior.__dict__,
                "after_client": after_client.__dict__,
                "before_inactive_client": prior_inactive.__dict__,
                "after_inactive_client": after_inactive.__dict__,
                "before_policy": dict(before_mode_policy.raw),
                "after_policy": dict(after_mode_policy.raw),
                "compiled_action_id": plan.actions[0].id,
                "probe": dict(probe_payload),
                "readiness": readiness.facts(),
            },
            causes=[]
            if mode_ok
            else [
                f"mode_probe_unobserved:{mode_probe.cause}"
                if not mode_probe.observed
                else "client_mode_guard_or_policy_not_established"
            ],
            outcome_unknown=not mode_probe.observed
            or (
                probe_payload.get("attempted") is True
                and bool(probe_payload.get("call_error"))
            ),
        )
        execution.conclude("M-NATIVE-MODE", mode_assessment)
    execution.finish("Q3_NATIVE_MODE")
    if mode_assessment.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
        execution.stop("q3_native_serve_mode_not_supported")
        return

    ids = ("M-NATIVE-SERVE",)
    if not execution.begin(ids, "Q3_NATIVE_SERVE"):
        return
    samples: list[dict[str, Any]] = []
    consecutive = 0
    conclusion = MeasurementConclusion.NEGATIVE_OBSERVED
    with execution.procedure(ids):
        for index in range(13):
            if not execution.ledger.can_afford(3):
                conclusion = MeasurementConclusion.INCONCLUSIVE
                break
            if index:
                execution.ledger.wait(10.0, execution.run.boundaries.sleep)
                if not execution.ledger.can_afford(3):
                    conclusion = MeasurementConclusion.INCONCLUSIVE
                    break
            with execution.ledger.purpose_of(f"q3-native-serve:client:{index}"):
                client_read = execution.probes.read_dhcp_clients(client_pairs)
            current_clients = client_readings(
                client_read.payload if client_read.observed else {},
                (client.name, inactive_client.name),
            )
            current = current_clients[client.name]
            inactive_now = current_clients[inactive_client.name]
            inactive_ok = (
                inactive_now.observed
                and inactive_now.mode is False
                and inactive_now.ipv4 in {"", "0.0.0.0"}
                and inactive_now.netmask in {"", "0.0.0.0"}
                and inactive_now.mac == prior_inactive.mac
            )
            with execution.ledger.purpose_of(f"q3-native-serve:lease_scan:{index}"):
                scan_read = execution.probes.read_dhcp_lease_calibration(
                    Q3_SERVER,
                    "FastEthernet0",
                    (("serverPool", 4), (Q3_POOL, 2)),
                )
            scan_payload = scan_read.payload if scan_read.observed else {}
            subject_ok = (
                scan_read.observed
                and scan_payload.get("device") == Q3_SERVER
                and scan_payload.get("interface") == "FastEthernet0"
                and scan_payload.get("found") is True
                and scan_payload.get("process_found") is True
                and not scan_payload.get("error")
            )
            scans = (
                scans_by_pool(scan_payload, ("serverPool", Q3_POOL))
                if subject_ok
                else unobserved_scans(("serverPool", Q3_POOL), "subject_unobserved")
            )
            native = scans["serverPool"]
            named = scans[Q3_POOL]
            policy_now = q3_default_read(
                execution,
                f"native_serving_{index}",
                prefix="q3-native-serve",
                policy=True,
            )
            policy_exact = native_policy_enabled_admitted(
                policy_now,
                server=Q3_SERVER,
                interface="FastEthernet0",
                expected_row=row,
                expected_exclusions=exclusions,
            )
            exact_rows = [
                item
                for item in native.rows_with_ip(current.ipv4)
                if item.mac == current.mac and item.port == client.interface
            ]
            row_state = row_status(native, current, None)
            wrong_port = any(
                item.mac == current.mac and item.port != client.interface
                for item in native.rows_with_ip(current.ipv4)
            )
            ready = (
                current.observed
                and current.mode is True
                and current.ipv4 == pool_action.lease_start
                and current.netmask == pool_action.netmask
                and current.mac == prior.mac
                and native.observed
                and native.capacity == 1
                and row_state == ROW_EXACT
                and len(exact_rows) == 1
                and len(native.rows) == 1
                and named.observed
                and named.cause == "pool_absent"
                and policy_exact
                and inactive_ok
            )
            samples.append(
                {
                    "index": index,
                    "client": current.__dict__,
                    "inactive_client": inactive_now.__dict__,
                    "inactive_ok": inactive_ok,
                    "native": native.as_facts(),
                    "named": named.as_facts(),
                    "policy": dict(policy_now.raw),
                    "policy_observed": policy_now.observed,
                    "policy_exclusions_complete": native_policy_exclusion_inventory_complete(
                        policy_now
                    ),
                    "policy_exact": policy_exact,
                    "row_status": row_state,
                    "wrong_port": wrong_port,
                    "ready": ready,
                }
            )
            consecutive = consecutive + 1 if ready else 0
            if consecutive >= 2:
                conclusion = MeasurementConclusion.SUPPORTED_IN_SAMPLE
                break
            if named.observed and named.cause != "pool_absent":
                conclusion = MeasurementConclusion.CONTRADICTED
                break
            if (
                policy_now.observed
                and native_policy_exclusion_inventory_complete(policy_now)
                and not policy_exact
            ):
                conclusion = MeasurementConclusion.CONTRADICTED
                break
            if current.observed and (
                current.mode is not True or current.mac != prior.mac
            ):
                conclusion = MeasurementConclusion.CONTRADICTED
                break
            if inactive_now.observed and not inactive_ok:
                conclusion = MeasurementConclusion.CONTRADICTED
                break
            if row_state in {ROW_WRONG_MAC, ROW_MAC_ELSEWHERE} or wrong_port:
                conclusion = MeasurementConclusion.CONTRADICTED
                break
            if (
                native.observed
                and native.capacity is not None
                and len(native.rows) > native.capacity
            ):
                conclusion = MeasurementConclusion.CONTRADICTED
                break
            if (
                current.observed
                and current.mode is True
                and current.ipv4
                not in (
                    "",
                    "0.0.0.0",
                    pool_action.lease_start,
                )
            ):
                conclusion = MeasurementConclusion.CONTRADICTED
                break
            if (
                current.observed
                and current.mode is True
                and current.ipv4 == pool_action.lease_start
                and current.netmask != pool_action.netmask
            ):
                conclusion = MeasurementConclusion.CONTRADICTED
                break
        else:
            in_policy_unattributed = any(
                item["client"]["observed"]
                and item["client"]["mode"] is True
                and item["client"]["ipv4"] == pool_action.lease_start
                and item["client"]["netmask"] == pool_action.netmask
                and not item["ready"]
                for item in samples
            )
            if (
                in_policy_unattributed
                or not samples
                or any(
                    not item["client"]["observed"]
                    or not item["native"]["observed"]
                    or not item["named"]["observed"]
                    or not item["policy_observed"]
                    or not item["policy_exclusions_complete"]
                    or not item["inactive_client"]["observed"]
                    for item in samples
                )
            ):
                conclusion = MeasurementConclusion.INCONCLUSIVE
        execution.conclude(
            "M-NATIVE-SERVE",
            Assessment(
                conclusion,
                facts={"samples": samples, "consecutive_matches": consecutive},
                causes=[]
                if conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
                else ["native_client_lease_not_attributed_in_window"],
                limitations=[
                    "autonomous_state_not_explicit_dhcpRun_causality",
                    "positive_row_does_not_establish_table_end",
                ],
            ),
        )
    execution.finish("Q3_NATIVE_SERVE")
    if conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
        execution.stop("q3_native_serve_not_supported")
