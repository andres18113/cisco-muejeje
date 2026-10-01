"""Q3: exact product setup of the DHCP fixture and bounded native measurements."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ....domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    RuntimeActionMutation,
)
from ....domain.enterprise.models.execution import (
    DispatchFact,
    PostconditionFact,
    ResultFact,
)
from ....domain.enterprise.models.service_plan import (
    AcquireDhcpLease,
    ConfigureServerDhcpPool,
    EnableServerDhcp,
)
from ....domain.enterprise.models.service_qualification import (
    Q3_LEASE_IPV4,
    Q3_PC1,
    Q3_PC2,
    Q3_POOL,
    Q3_SERVER,
    MeasurementConclusion,
    ReleaseRecord,
)
from ....domain.enterprise.models.service_runtime import (
    ObservationFact,
    RuntimeServiceVerification,
    ServiceApplicationResult,
)
from ....domain.enterprise.services.qualification_product_evidence import (
    e5_foundation_cause,
    service_result_cause,
)
from ....domain.enterprise.services.service_qualification_evidence import (
    BASELINE_OBSERVED_NATIVE_DEFAULT,
    Assessment,
    BaselineAdmission,
    ProbeReading,
    assess_dhcp_baseline_admission,
)
from ...use_cases.apply_configuration import ConfigurationApplicator
from ...use_cases.apply_services import ServiceApplicator
from ...use_cases.foundational_evidence import derive_service_foundational_statuses
from ..contracts import Q3ProductContract, bounded
from ..dhcp_observations import (
    native_default_facts,
    q3_client_rows,
    q3_default_observed,
    q3_default_purpose,
    q3_default_read,
)
from ..execution import Execution
from ..fixtures import Readiness, await_readiness, fixture_endpoints, setup_fixtures
from ..operation_budget import counted_seq
from ..product_support import (
    DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE,
    ExactInventoryConfigurationRuntime,
    ExactInventoryServiceRuntime,
    product_runtime_context,
    q3_endpoint_plan,
    q3_server_plan,
)


def _q3_client_assessments(
    before: ProbeReading | None, after: ProbeReading | None
) -> tuple[Assessment, Assessment]:
    """Judge native MAC and DHCP-mode readers without assigning semantics."""
    before_rows = q3_client_rows(before)
    after_rows = q3_client_rows(after)
    facts = {
        "before": before_rows or [],
        "after": after_rows or [],
    }
    if before_rows is None or after_rows is None:
        causes = [
            value
            for value in (
                bounded(before.cause)
                if before is not None and not before.observed
                else "",
                bounded(after.cause)
                if after is not None and not after.observed
                else "",
                "dhcp_client_rows_malformed"
                if before_rows is None or after_rows is None
                else "",
            )
            if value
        ]
        inconclusive = Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=causes,
            limitations=["exact_client_reader_sample_not_completed"],
        )
        return inconclusive, inconclusive
    mac_ok = all(
        row["found"]
        and row["port_found"]
        and not row["error"]
        and bool(row["mac"])
        and len(row["mac"]) <= 64
        for row in [*before_rows, *after_rows]
    )
    mode_ok = all(
        row["found"]
        and row["port_found"]
        and not row["error"]
        and row["mode_type"] == "boolean"
        and isinstance(row["mode"], bool)
        for row in [*before_rows, *after_rows]
    )
    mac = Assessment(
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
        if mac_ok
        else MeasurementConclusion.CONTRADICTED,
        facts=facts,
        causes=[] if mac_ok else ["native_mac_reader_invalid"],
        limitations=[
            "native_mac_representation_sample_only",
            "no_equivalence_inferred",
        ],
    )
    mode = Assessment(
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
        if mode_ok
        else MeasurementConclusion.CONTRADICTED,
        facts=facts,
        causes=[] if mode_ok else ["native_dhcp_mode_not_boolean"],
        limitations=["native_mode_reader_sample_only"],
    )
    return mac, mode


def _q3_setup_assessment(
    baseline: ProbeReading,
    admission: BaselineAdmission,
    configuration: ConfigurationApplicationResult | None,
    foundations: Mapping[str, ActionExecutionStatus],
    server_mutations: Sequence[RuntimeActionMutation],
    server_readback: RuntimeServiceVerification | None,
    contract: Q3ProductContract,
    native_default: Mapping[str, Any],
    readiness: Mapping[str, Any],
    setup_cause: str,
) -> Assessment:
    """Judge the product configuration path without promoting native support."""
    mutation_facts = [
        {
            "action_id": item.action_id,
            "dispatch": item.dispatch.value,
            "result": item.result.value,
            "postcondition": item.postcondition.value,
            "attempted": item.attempted,
        }
        for item in server_mutations
    ]
    facts = {
        "initial_server": dict(baseline.payload) if baseline.observed else {},
        "baseline_admission": {
            "admitted": admission.admitted,
            "kind": admission.kind,
            "causes": list(admission.causes),
        },
        "native_default": dict(native_default),
        "readiness": dict(readiness),
        "configuration_plan": configuration.config_plan_id if configuration else "",
        "configuration_hash": (
            configuration.config_semantic_hash if configuration else ""
        ),
        "service_plan": contract.service_plan.id,
        "service_hash": contract.service_plan.semantic_hash,
        "foundation_statuses": {
            key: value.value for key, value in sorted(foundations.items())
        },
        "setup_cause": setup_cause,
        "server_mutations": mutation_facts,
        "server_readback": (
            {
                "status": server_readback.status.value,
                "observation": server_readback.observation.value,
                "cause": server_readback.cause,
            }
            if server_readback is not None
            else {}
        ),
    }
    expected_actions = {
        item.id
        for item in contract.service_plan.actions
        if isinstance(item, EnableServerDhcp | ConfigureServerDhcpPool)
    }
    complete_mutations = {
        item.action_id for item in server_mutations
    } == expected_actions and all(
        item.dispatch is DispatchFact.ACCEPTED
        and item.result is ResultFact.CORRELATED
        and item.postcondition is PostconditionFact.SATISFIED
        for item in server_mutations
    )
    foundations_ready = bool(foundations) and all(
        item is ActionExecutionStatus.VERIFIED for item in foundations.values()
    )
    readback_ready = (
        server_readback is not None
        and server_readback.status is ActionExecutionStatus.VERIFIED
        and server_readback.observation is ObservationFact.OBSERVED
    )
    unknown_effect = setup_cause.startswith("outcome_unknown:") or any(
        item.dispatch is DispatchFact.ACCEPTANCE_UNKNOWN
        or item.result is ResultFact.NOT_OBSERVED
        for item in server_mutations
    )
    limitations = [
        "stored_configuration_sample_only",
        "serving_behavior_not_inferred",
        f"initial_pool_inventory:{admission.kind}",
    ]
    if admission.kind == BASELINE_OBSERVED_NATIVE_DEFAULT:
        # What the run can state is what it did, not what Packet Tracer did:
        # no explicit setter of this run targeted the native default. Whether
        # its values moved is a separate observation, and the readings above
        # are where a reviewer finds the answer.
        limitations.append("no_explicit_setter_targeted_the_native_default")
        limitations.append("process_enable_is_process_wide_not_pool_scoped")
    if not setup_cause and complete_mutations and foundations_ready and readback_ready:
        return Assessment(
            MeasurementConclusion.SUPPORTED_IN_SAMPLE,
            facts=facts,
            limitations=limitations,
        )
    contradicted = (
        setup_cause.startswith("contradiction:")
        or (
            server_readback is not None
            and server_readback.observation is ObservationFact.CONTRADICTED
        )
        or any(
            item.postcondition is PostconditionFact.UNSATISFIED
            for item in server_mutations
        )
    )
    return Assessment(
        MeasurementConclusion.CONTRADICTED
        if contradicted
        else MeasurementConclusion.INCONCLUSIVE,
        facts=facts,
        causes=[
            value
            for value in (setup_cause, "q3_product_configuration_not_established")
            if value
        ],
        limitations=[*limitations, "no_serving_claim"],
        outcome_unknown=unknown_effect,
    )


def _q3_table_assessment(
    empty: ProbeReading | None, full: ProbeReading | None
) -> Assessment:
    facts = {
        "empty": dict(empty.payload) if empty is not None and empty.observed else {},
        "capacity_one": (
            dict(full.payload) if full is not None and full.observed else {}
        ),
    }
    if empty is None or full is None or not empty.observed or not full.observed:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["bounded_lease_table_sample_unobserved"],
            limitations=["no_absence_or_completion_claim"],
        )
    empty_rows = empty.payload.get("rows")
    full_rows = full.payload.get("rows")
    coherent = (
        empty.payload.get("pool_name") == Q3_POOL
        and full.payload.get("pool_name") == Q3_POOL
        and isinstance(empty_rows, list)
        and isinstance(full_rows, list)
        and len(empty_rows) == 0
        and any(
            isinstance(row, dict) and row.get("ipAddress") == Q3_LEASE_IPV4
            for row in full_rows
        )
    )
    return Assessment(
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
        if coherent
        else MeasurementConclusion.INCONCLUSIVE,
        facts=facts,
        causes=[] if coherent else ["empty_or_capacity_one_sample_not_discriminating"],
        limitations=[
            "bounded_sample:empty_and_capacity_one",
            "termination_behavior_not_generalized",
            "no_pool_exhaustion_claim",
        ],
    )


def _q3_timing_assessment(
    before_one: ProbeReading | None,
    before_two: ProbeReading | None,
    after_one: ProbeReading | None,
    after_two: ProbeReading | None,
    service_result: ServiceApplicationResult | None,
    guard: RuntimeActionMutation | None,
    guard_not_run: str,
    readiness: Mapping[str, Any],
    native_default: Mapping[str, Any],
) -> Assessment:
    readings = (before_one, before_two, after_one, after_two)
    rows = [q3_client_rows(item) for item in readings]
    facts = {
        "before_1": rows[0] or [],
        "before_2": rows[1] or [],
        "after_1": rows[2] or [],
        "after_2": rows[3] or [],
        "readiness": dict(readiness),
        "native_default": dict(native_default),
        "guard_not_run": guard_not_run,
        "service_status": service_result.status.value if service_result else "absent",
        "service_actions": (
            [
                {
                    "action_id": item.action_id,
                    "status": item.status.value,
                    "dispatch": item.dispatch.value,
                    "result": item.result.value,
                    "postcondition": item.postcondition.value,
                    "attempted": item.attempted,
                    "cause": item.cause,
                }
                for item in service_result.action_results
            ]
            if service_result is not None
            else []
        ),
        "guard": (
            {
                "attempted": guard.attempted,
                "cause": guard.cause,
                "dispatch": guard.dispatch.value,
            }
            if guard is not None
            else {}
        ),
    }
    guard_refused = (
        guard is not None
        and guard.attempted is not True
        and guard.cause == "own_claim_replayed"
    )
    product_contradictions = (
        [
            item.expectation_id
            for item in service_result.verification_results
            if item.observation is ObservationFact.CONTRADICTED
        ]
        if service_result is not None
        else []
    )
    facts["product_contradictions"] = product_contradictions
    product_outcome_unknown = bool(
        service_result
        and (
            guard_not_run.startswith("outcome_unknown:")
            or any(
                item.dispatch is DispatchFact.ACCEPTANCE_UNKNOWN
                or item.result is ResultFact.NOT_OBSERVED
                or (
                    item.received_mutation is not None
                    and bool(item.received_mutation.call_error)
                )
                for item in service_result.action_results
                if item.attempted is True
            )
        )
    )
    facts["product_outcome_unknown"] = product_outcome_unknown
    if product_contradictions:
        return Assessment(
            MeasurementConclusion.CONTRADICTED,
            facts=facts,
            causes=["product_dhcp_readback_contradicted"],
            limitations=["contradiction_preserved_from_real_product_runtime"],
        )
    if product_outcome_unknown:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["product_dhcp_effect_outcome_unknown"],
            limitations=["no_guard_or_later_mutation_authorized"],
            outcome_unknown=True,
        )
    if guard_not_run:
        # No acquisition was requested at all, so there is nothing to time and
        # nothing to replay. This states what the fixture allowed, never that
        # DHCP acquisition failed.
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=[f"acquisition_not_requested:{guard_not_run}"],
            limitations=[
                "no_client_activated",
                "readiness_result_is_not_an_acquisition_verdict",
            ],
        )
    if not guard_refused:
        return Assessment(
            MeasurementConclusion.CONTRADICTED,
            facts=facts,
            causes=["same_action_guard_control_dispatched_or_unreadable"],
            outcome_unknown=guard is None or guard.attempted is None,
        )
    if any(item is None for item in rows):
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["lease_time_window_unobserved"],
            limitations=["lease_time_semantics_unqualified"],
        )
    return Assessment(
        MeasurementConclusion.INCONCLUSIVE,
        facts=facts,
        causes=["automatic_renewal_not_discriminated_in_fixed_window"],
        limitations=[
            "lease_time_semantics_unqualified",
            "no_clock_or_lease_manipulation",
            "same_action_guard_refused_without_redispatch",
        ],
    )


def run_q3(execution: Execution) -> None:
    """Run the exact Q3 setup, product path and bounded native measurements."""
    required = [item.id for item in execution.definition.experiments if item.required]
    if not execution.ledger.can_afford(
        execution.definition.fixture_operations
        + execution.definition.required_experiment_operations
    ):
        execution.not_run(required, "budget_insufficient_for:Q3")
        execution.stop("budget:Q3")
        return
    if not setup_fixtures(execution):
        execution.not_run(required, "fixture_setup_failed")
        return
    contract = execution.product_contract
    if contract is None:
        execution.not_run(required, "q3_product_contract_absent")
        execution.stop("q3_product_contract_absent")
        return
    configuration_runtime = ExactInventoryConfigurationRuntime(
        execution.run.boundaries.configuration_runtime(execution.bound),
        contract.inventory,
    )
    service_runtime = ExactInventoryServiceRuntime(
        execution.run.boundaries.service_runtime(execution.bound),
        contract.inventory,
    )
    endpoint_plan = q3_endpoint_plan(contract)
    execution.record.limitations.extend(
        [
            "q3_private_candidate_capabilities:no_public_catalog_mutation",
            "q3_endpoint_projection:physical_fixture_dependencies_owned_by_runner",
        ]
    )
    foundation_plan = contract.service_plan.model_copy(
        update={
            "source_configuration_id": endpoint_plan.id,
            "source_configuration_hash": endpoint_plan.semantic_hash,
        },
        deep=True,
    )
    context = product_runtime_context(contract)
    clients = ((Q3_PC1, "FastEthernet0"), (Q3_PC2, "FastEthernet0"))
    gate = Readiness(False, 0, 0.0, "readiness_not_attempted")
    server_application: ServiceApplicationResult | None = None

    setup_ids = ("M-DHCP-1", "M-DHCP-4", "M-DHCP-5")
    if not execution.begin(setup_ids, "Q3_SETUP"):
        return
    foundations: dict[str, ActionExecutionStatus] = {}
    with execution.procedure(setup_ids):
        # One read serves both the typed baseline admission and the run's first
        # default reading, so the first snapshot costs the stage nothing extra.
        baseline_start = len(execution.ledger.entries)
        with execution.ledger.purpose_of(q3_default_purpose("before_e5")):
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
        q3_default_observed(
            execution,
            "before_e5",
            baseline,
            operation_seq=counted_seq(execution.ledger, baseline_start),
        )
        clients_before = execution.probes.read_dhcp_clients(clients)
        if not admission.admitted:
            mac, mode = _q3_client_assessments(clients_before, clients_before)
            execution.conclude(
                "M-DHCP-1",
                Assessment(
                    MeasurementConclusion.INCONCLUSIVE,
                    facts={
                        "initial_server": (
                            dict(baseline.payload) if baseline.observed else {}
                        ),
                        "baseline_admission": {
                            "admitted": False,
                            "kind": admission.kind,
                            "causes": list(admission.causes),
                        },
                        "native_default": native_default_facts(execution),
                    },
                    causes=[
                        "initial_dhcp_server_state_not_admissible",
                        *admission.causes,
                    ],
                    limitations=[
                        "no_setter_dispatched",
                        "observed_state_preserved_untouched",
                    ],
                ),
            )
            execution.conclude("M-DHCP-4", mac)
            execution.conclude("M-DHCP-5", mode)
            execution.stop("q3_initial_server_state_not_admissible")
        else:
            configuration = None
            server_mutations: list[RuntimeActionMutation] = []
            server_readback: RuntimeServiceVerification | None = None
            setup_cause = ""
            endpoints = fixture_endpoints(execution)
            gate = await_readiness(
                execution,
                endpoints,
                lambda timeout: execution.probes.read_port_readiness(
                    endpoints, timeout
                ),
                purpose="readiness:q3_fixture_links",
            )
            if not gate.ready:
                setup_cause = f"readiness_not_established:{gate.reason}"
            if gate.ready and not execution.run.transition(
                "experiment:Q3_SETUP:e5_started"
            ):
                execution.stop("persistence:q3_e5_not_announced")
            if gate.ready and not execution.stopped:
                with execution.ledger.effect_of("q3:product:e5_endpoints"):
                    configuration = ConfigurationApplicator(
                        configuration_runtime
                    ).apply(
                        endpoint_plan,
                        actual_source_topology_hash=(
                            contract.manifest.physical_topology_hash
                        ),
                        capabilities=contract.device_capabilities,
                        runtime_context=context,
                        deployment_manifest=contract.manifest,
                    )
                foundations = derive_service_foundational_statuses(
                    foundation_plan, configuration
                )
                # The E5 result and the foundations it produced decide whether
                # any E6 server mutation is admissible. They used to be judged
                # only after the mutation had already been dispatched.
                setup_cause = e5_foundation_cause(
                    configuration,
                    foundations,
                    {item.id for item in endpoint_plan.actions},
                )
                if setup_cause:
                    execution.stop(setup_cause)
            if (
                gate.ready
                and not execution.stopped
                and not execution.run.transition("experiment:Q3_SETUP:e6_started")
            ):
                execution.stop("persistence:q3_e6_not_announced")
            if gate.ready and not execution.stopped:
                server_plan = q3_server_plan(contract.service_plan)
                with execution.ledger.effect_of("q3:product:e6_server"):
                    server_application = ServiceApplicator(service_runtime).apply(
                        server_plan,
                        actual_source_topology_hash=(
                            contract.manifest.physical_topology_hash
                        ),
                        actual_source_configuration_hash=(
                            contract.service_plan.source_configuration_hash
                        ),
                        foundational_statuses=foundations,
                        capabilities=contract.service_capabilities,
                        runtime_context=context,
                        deployment_manifest=contract.manifest,
                        operational_readiness=(
                            DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE
                        ),
                    )
                setup_cause = service_result_cause(
                    server_application,
                    {item.id for item in server_plan.actions},
                    expected_verification_ids={
                        item.id for item in server_plan.verification_expectations
                    },
                )
                server_mutations = [
                    row.received_mutation
                    for row in server_application.action_results
                    if row.received_mutation is not None
                ]
                server_readback = next(
                    iter(server_application.verification_results), None
                )
                if setup_cause:
                    execution.stop(setup_cause)
            after_snapshot = q3_default_read(execution, "after_setup")
            if not after_snapshot.observed:
                setup_cause = setup_cause or (
                    "q3_native_default_unobserved:" + after_snapshot.cause
                )
                execution.stop(setup_cause)
            elif execution.default_pool_differences:
                setup_cause = setup_cause or (
                    "q3_native_default_changed:" + execution.default_pool_differences[0]
                )
                execution.stop(setup_cause)
            clients_after = clients_before
            if configuration is not None and execution.ledger.can_afford(1):
                clients_after = execution.probes.read_dhcp_clients(clients)
            mac, mode = _q3_client_assessments(clients_before, clients_after)
            execution.conclude(
                "M-DHCP-1",
                _q3_setup_assessment(
                    baseline,
                    admission,
                    configuration,
                    foundations,
                    server_mutations,
                    server_readback,
                    contract,
                    native_default_facts(execution),
                    gate.facts(),
                    setup_cause,
                ),
            )
            execution.conclude("M-DHCP-4", mac)
            execution.conclude("M-DHCP-5", mode)
    execution.finish("Q3_SETUP")
    if execution.stopped:
        q3_default_read(execution, "before_cleanup")
        return

    # M-DHCP-3 is OMITTED in this profile: no observer is registered, so the
    # procedure is the lease table and the lease-time window only.
    measurement_ids = ("M-DHCP-2", "M-DHCP-6")
    if not execution.begin(measurement_ids, "Q3_DHCP"):
        return
    with execution.procedure(measurement_ids):
        claim = execution.probes.write_bag_sentinel()
        if claim.observed and claim.payload.get("run_bag_preexisting"):
            execution.bag_collision = True
        elif (
            claim.observed
            and claim.payload.get("written")
            and claim.payload.get("owned")
        ):
            execution.bag_touched = True
            execution.bag_unreleased.add("sentinel")
        else:
            execution.stop("q3_run_bag_not_owned")
        before_one = before_two = empty_table = None
        service_result = None
        guard = None
        guard_not_run = "" if gate.ready else f"readiness_not_established:{gate.reason}"
        after_one = after_two = full_table = None
        if not execution.stopped:
            before_one = execution.probes.read_dhcp_clients(clients)
            execution.settle()
            before_two = execution.probes.read_dhcp_clients(clients)
            empty_table = execution.probes.read_dhcp_table(
                Q3_SERVER, "FastEthernet0", Q3_POOL
            )
        if not execution.stopped and gate.ready:
            nonces = {
                reference: f"{execution.nonce}:{index}"
                for index, reference in enumerate(
                    contract.service_plan.operation_nonce_refs(), start=1
                )
            }
            bound_plan = contract.service_plan.with_operation_nonces(nonces)
            first_acquisition = next(
                item
                for item in bound_plan.actions
                if isinstance(item, AcquireDhcpLease)
                and item.host_device_name == Q3_PC1
            )
            if not execution.run.transition("experiment:Q3_DHCP:product_started"):
                execution.stop("persistence:q3_product_not_announced")
            if not execution.stopped:
                with execution.ledger.effect_of("q3:product:service_apply"):
                    service_result = ServiceApplicator(service_runtime).apply(
                        bound_plan,
                        actual_source_topology_hash=(
                            contract.manifest.physical_topology_hash
                        ),
                        actual_source_configuration_hash=(
                            contract.service_plan.source_configuration_hash
                        ),
                        foundational_statuses=foundations,
                        capabilities=contract.service_capabilities,
                        runtime_context=context,
                        deployment_manifest=contract.manifest,
                        operational_readiness=(
                            DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE
                        ),
                        retained_action_results=(
                            server_application.action_results
                            if server_application is not None
                            else ()
                        ),
                    )
                verification_by_id = {
                    item.expectation_id: item
                    for item in service_result.verification_results
                }
                recovered_action_ids = {
                    expectation.action_id
                    for expectation in bound_plan.verification_expectations
                    if (
                        (row := verification_by_id.get(expectation.id)) is not None
                        and row.status is ActionExecutionStatus.VERIFIED
                        and row.fresh_evidence
                        and row.observation is ObservationFact.OBSERVED
                    )
                }
                guard_not_run = service_result_cause(
                    service_result,
                    {item.id for item in bound_plan.actions},
                    expected_verification_ids={
                        item.id for item in bound_plan.verification_expectations
                    },
                    recovered_action_ids=recovered_action_ids,
                )
                if guard_not_run:
                    execution.stop(guard_not_run)
                else:
                    with execution.ledger.effect_of("q3:guard:acquisition_replay"):
                        [guard] = service_runtime.apply_actions([first_acquisition])
                after_one = execution.probes.read_dhcp_clients(clients)
                execution.settle()
                after_two = execution.probes.read_dhcp_clients(clients)
                full_table = execution.probes.read_dhcp_table(
                    Q3_SERVER, "FastEthernet0", Q3_POOL
                )
        q3_default_read(execution, "before_cleanup")
        if service_result is not None:
            for action in contract.service_plan.actions:
                if isinstance(action, AcquireDhcpLease):
                    execution.record.releases.append(
                        ReleaseRecord(
                            resource=f"claim:{action.host_device_name}:FastEthernet0",
                            kind="claim",
                            outcome="retained_until_process_retirement",
                            detail="product claims are never reset or deleted",
                        )
                    )
                    execution.record.engine_residue.append(
                        f"claim:{action.host_device_name}:retained"
                    )
        if service_result is None and not gate.ready and not execution.stopped:
            # Nothing was dispatched, so neither measurement was interrupted:
            # both record what the unready fixture allowed them to observe.
            execution.conclude(
                "M-DHCP-2", _q3_table_assessment(empty_table, full_table)
            )
            execution.conclude(
                "M-DHCP-6",
                _q3_timing_assessment(
                    before_one,
                    before_two,
                    after_one,
                    after_two,
                    None,
                    None,
                    guard_not_run,
                    gate.facts(),
                    native_default_facts(execution),
                ),
            )
        elif service_result is None:
            execution.interrupt_in_flight(
                execution.record.primary_failure or "q3_product_application_not_run"
            )
        else:
            execution.conclude(
                "M-DHCP-2", _q3_table_assessment(empty_table, full_table)
            )
            execution.conclude(
                "M-DHCP-6",
                _q3_timing_assessment(
                    before_one,
                    before_two,
                    after_one,
                    after_two,
                    service_result,
                    guard,
                    guard_not_run,
                    gate.facts(),
                    native_default_facts(execution),
                ),
            )
    execution.finish("Q3_DHCP")
