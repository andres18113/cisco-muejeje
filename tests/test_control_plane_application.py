"""Aplicación E9 offline: gates, DAG, evidencia y escenarios con runtime fake."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from src.packet_tracer_mcp.application.use_cases.apply_control_plane import (
    ControlPlaneApplicator,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConvergenceReport,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureEtherChannel,
    ConfigureSpanningTree,
    ControlPlaneCapabilityDimension,
    ControlPlaneCapabilityProfile,
    ControlPlaneFoundationRequirement,
    ControlPlanePhase,
    ControlPlanePlan,
    ControlPlaneVerificationExpectation,
    ControlPlaneVerificationKind,
    EtherChannelProtocol,
    LinkFailureScenario,
    StpMode,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane_runtime import (
    ControlPlaneExecutionStage,
    FailureScenarioTransition,
    FailureTransitionPhase,
    RuntimeControlPlaneVerification,
    RuntimeFailureScenarioResult,
)


class FakeControlPlaneRuntime:
    def __init__(self) -> None:
        self.inventory_calls = 0
        self.applied_batches: list[list[str]] = []
        self.verified_batches: list[list[str]] = []
        self.scenarios: list[str] = []
        self.failed_action_ids: set[str] = set()
        self.omit_verification_ids: set[str] = set()
        self.scenario_result: RuntimeFailureScenarioResult | None = None

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        self.inventory_calls += 1
        return [
            RuntimeConfigurationTarget(
                device_name="SW1", model="2960", interfaces=["FastEthernet0/1"],
            ),
            RuntimeConfigurationTarget(
                device_name="SW2", model="2960", interfaces=["FastEthernet0/2"],
            ),
        ]

    def apply_actions(
        self, actions: Sequence[ConfigureSpanningTree],
    ) -> list[RuntimeActionMutation]:
        self.applied_batches.append([item.id for item in actions])
        return [
            RuntimeActionMutation(
                action_id=item.id,
                applied=item.id not in self.failed_action_ids,
                failure_code=(
                    ConfigurationFailureCode.NONE
                    if item.id not in self.failed_action_ids
                    else ConfigurationFailureCode.APPLICATION_FAILED
                ),
                batch_id=f"batch/{len(self.applied_batches)}",
            )
            for item in actions
        ]

    def verify(
        self, expectations: Sequence[ControlPlaneVerificationExpectation],
    ) -> list[RuntimeControlPlaneVerification]:
        self.verified_batches.append([item.id for item in expectations])
        results = []
        for item in expectations:
            if item.id in self.omit_verification_ids:
                continue
            stage = (
                ControlPlaneExecutionStage.BEHAVIOR
                if item.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
                else ControlPlaneExecutionStage.OBSERVED
            )
            results.append(RuntimeControlPlaneVerification(
                expectation_id=item.id,
                stage=stage,
                status=ActionExecutionStatus.VERIFIED,
                evidence_method="fake_fresh_observation",
                fresh_evidence=True,
            ))
        return results

    def execute_failure_scenario(
        self,
        scenario: LinkFailureScenario,
        failure_expectation: ControlPlaneVerificationExpectation,
        recovery_expectation: ControlPlaneVerificationExpectation,
    ) -> RuntimeFailureScenarioResult:
        self.scenarios.append(scenario.id)
        if self.scenario_result is not None:
            return self.scenario_result
        return _successful_runtime_scenario(scenario, failure_expectation, recovery_expectation)


def _action(
    action_id: str,
    device_id: str,
    device_name: str,
    *,
    depends_on: list[str] | None = None,
) -> ConfigureSpanningTree:
    return ConfigureSpanningTree(
        id=action_id,
        phase=ControlPlanePhase.L2_FOUNDATION,
        device_id=device_id,
        device_name=device_name,
        model="2960",
        site_id="hq",
        depends_on=depends_on or [],
        required_capability=ControlPlaneCapabilityDimension.STP_RAPID_PVST_CONFIG,
        mode=StpMode.RAPID_PVST,
        vlan_ids=[10],
    )


def _expectation(
    expectation_id: str,
    kind: ControlPlaneVerificationKind,
    action_id: str,
    device_id: str,
    capability: ControlPlaneCapabilityDimension,
    *,
    depends_on: list[str] | None = None,
) -> ControlPlaneVerificationExpectation:
    return ControlPlaneVerificationExpectation(
        id=expectation_id,
        kind=kind,
        action_id=action_id,
        device_id=device_id,
        required_capability=capability,
        expected={"destination_ipv4": "10.0.0.2", "reachable": True},
        depends_on=depends_on or [action_id],
    )


def _plan() -> ControlPlanePlan:
    first = _action("cp/a", "sw1", "SW1")
    second = _action("cp/b", "sw2", "SW2", depends_on=[first.id])
    observed = _expectation(
        "verify/state", ControlPlaneVerificationKind.STP_STATE, first.id, "sw1",
        ControlPlaneCapabilityDimension.STP_STATE,
    )
    behavior = _expectation(
        "verify/reach", ControlPlaneVerificationKind.END_TO_END_REACHABILITY,
        second.id, "sw2", ControlPlaneCapabilityDimension.ROUTING_BEHAVIOR,
    )
    failure = _expectation(
        "verify/failure", ControlPlaneVerificationKind.LINK_FAILURE_CONVERGENCE,
        second.id, "sw1", ControlPlaneCapabilityDimension.STP_FAILOVER,
    )
    recovery = _expectation(
        "verify/recovery", ControlPlaneVerificationKind.RESTORE_RECOVERY,
        second.id, "sw1", ControlPlaneCapabilityDimension.STP_FAILOVER,
        depends_on=[failure.id],
    )
    return ControlPlanePlan(
        id="cp-plan",
        semantic_hash="cp-hash",
        source_topology_id="topology",
        source_topology_hash="topology-hash",
        source_configuration_id="configuration",
        source_configuration_hash="configuration-hash",
        source_security_id="security",
        source_security_hash="security-hash",
        actions=[first, second],
        foundational_requirements=[
            ControlPlaneFoundationRequirement(
                id="foundation/vlan/cfg-vlan", kind="vlan", source_id="cfg-vlan",
            ),
            ControlPlaneFoundationRequirement(
                id="foundation/security/sec-action", kind="security",
                source_id="sec-action", source_hash="security-hash",
            ),
        ],
        verification_expectations=[observed, behavior, failure, recovery],
        failure_scenarios=[LinkFailureScenario(
            id="scenario/link-1",
            link_id="link-1",
            device_a_id="sw1",
            device_b_id="sw2",
            target_device_id="sw1",
            target_device_name="SW1",
            target_interface="FastEthernet0/1",
            peer_device_id="sw2",
            peer_device_name="SW2",
            peer_interface="FastEthernet0/2",
            cable="copper_cross",
            probe_source_device_id="sw1",
            probe_source_device_name="SW1",
            probe_destination_device_id="sw2",
            probe_destination_device_name="SW2",
            probe_destination_ipv4="10.0.0.2",
            restore_required=True,
            verification_expectation_ids=[failure.id, recovery.id],
        )],
    )


def _successful_runtime_scenario(scenario, failure, recovery):
    return RuntimeFailureScenarioResult(
        scenario_id=scenario.id,
        before=RuntimeControlPlaneVerification(
            expectation_id=failure.id,
            stage=ControlPlaneExecutionStage.BEHAVIOR,
            status=ActionExecutionStatus.VERIFIED,
            fresh_evidence=True,
        ),
        injection=RuntimeActionMutation(action_id=scenario.id, applied=True),
        during=RuntimeControlPlaneVerification(
            expectation_id=failure.id,
            stage=ControlPlaneExecutionStage.FAILOVER,
            status=ActionExecutionStatus.VERIFIED,
            fresh_evidence=True,
            convergence=ConvergenceReport(
                attempts=2, elapsed_ms=250,
                final_status=ActionExecutionStatus.VERIFIED,
            ),
        ),
        restore_attempted=True,
        restore=RuntimeActionMutation(action_id=scenario.id, applied=True),
        after=RuntimeControlPlaneVerification(
            expectation_id=recovery.id,
            stage=ControlPlaneExecutionStage.RESTORE,
            status=ActionExecutionStatus.VERIFIED,
            fresh_evidence=True,
        ),
        transitions=[
            FailureScenarioTransition(
                sequence=index,
                phase=phase,
                elapsed_ms=index * 10,
                status=ActionExecutionStatus.VERIFIED,
            )
            for index, phase in enumerate((
                FailureTransitionPhase.BASELINE_OBSERVED,
                FailureTransitionPhase.FAULT_INJECTED,
                FailureTransitionPhase.FAILOVER_OBSERVED,
                FailureTransitionPhase.RESTORE_DISPATCHED,
                FailureTransitionPhase.RECOVERY_OBSERVED,
            ))
        ],
    )


def _apply(runtime, plan=None, **overrides):
    arguments = {
        "actual_source_topology_hash": "topology-hash",
        "actual_source_configuration_hash": "configuration-hash",
        "actual_source_security_hash": "security-hash",
        "foundational_statuses": {
            "cfg-vlan": ActionExecutionStatus.VERIFIED,
            "sec-action": ActionExecutionStatus.VERIFIED,
        },
        "foundational_hashes": {"sec-action": "security-hash"},
        "capabilities": {"2960": ControlPlaneCapabilityProfile.supported("2960")},
    }
    arguments.update(overrides)
    return ControlPlaneApplicator(runtime).apply(plan or _plan(), **arguments)


def test_applies_dag_and_keeps_observed_behavior_and_failover_separate():
    runtime = FakeControlPlaneRuntime()

    result = _apply(runtime)

    assert result.status is ConfigurationApplicationStatus.VERIFIED
    assert result.configured_status is ActionExecutionStatus.COMPILED
    assert result.applied_status is ActionExecutionStatus.APPLIED
    assert result.observed_status is ActionExecutionStatus.VERIFIED
    assert result.behavior_status is ActionExecutionStatus.VERIFIED
    assert result.failover_status is ActionExecutionStatus.VERIFIED
    assert runtime.applied_batches == [["cp/a"], ["cp/b"]]
    assert runtime.verified_batches == [["verify/state"], ["verify/reach"]]
    assert runtime.scenarios == ["scenario/link-1"]
    assert result.scenario_results[0].restore_attempted
    assert result.scenario_results[0].restore_status is ActionExecutionStatus.APPLIED
    assert [
        item.elapsed_ms for item in result.scenario_results[0].transitions
    ] == [0, 10, 20, 30, 40]


def test_non_monotonic_failure_transitions_are_rejected_as_runtime_evidence():
    runtime = FakeControlPlaneRuntime()
    plan = _plan()
    scenario = plan.failure_scenarios[0]
    expectations = {item.id: item for item in plan.verification_expectations}
    failure = expectations[scenario.verification_expectation_ids[0]]
    recovery = expectations[scenario.verification_expectation_ids[1]]
    result = _successful_runtime_scenario(scenario, failure, recovery)
    result.transitions[1].elapsed_ms = 100
    result.transitions[2].elapsed_ms = 50
    runtime.scenario_result = result

    applied = _apply(runtime, plan=plan)

    assert applied.scenario_results[0].status is ActionExecutionStatus.FAILED
    assert (
        applied.scenario_results[0].failure_code
        is ConfigurationFailureCode.SESSION_FAILED
    )
    assert "transitions" in applied.scenario_results[0].message


@pytest.mark.parametrize(
    ("override", "value", "failure_code"),
    (
        ("actual_source_topology_hash", "stale", ConfigurationFailureCode.SOURCE_TOPOLOGY_MISMATCH),
        ("actual_source_configuration_hash", "stale", ConfigurationFailureCode.SOURCE_CONFIGURATION_MISMATCH),
        ("actual_source_security_hash", "stale", ConfigurationFailureCode.SOURCE_CONFIGURATION_MISMATCH),
    ),
)
def test_source_hash_mismatch_fails_before_runtime(override, value, failure_code):
    runtime = FakeControlPlaneRuntime()

    result = _apply(runtime, **{override: value})

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is failure_code
    assert runtime.inventory_calls == 0


@pytest.mark.parametrize(
    "overrides",
    (
        {"foundational_statuses": {"cfg-vlan": ActionExecutionStatus.APPLIED}},
        {"foundational_hashes": {"sec-action": "stale"}},
    ),
)
def test_foundation_status_and_hash_gates_fail_before_runtime(overrides):
    runtime = FakeControlPlaneRuntime()

    result = _apply(runtime, **overrides)

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.FOUNDATIONAL_CONFIGURATION_MISSING
    assert runtime.inventory_calls == 0


def test_actions_out_of_deterministic_dependency_order_fail_before_runtime():
    runtime = FakeControlPlaneRuntime()
    plan = _plan()
    plan.actions = list(reversed(plan.actions))

    result = _apply(runtime, plan)

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.DEPENDENCY_BLOCKED
    assert runtime.inventory_calls == 0


def test_capability_skip_blocks_dependent_action_without_calling_it():
    runtime = FakeControlPlaneRuntime()
    profile = ControlPlaneCapabilityProfile(model="2960")

    result = _apply(runtime, capabilities={"2960": profile})

    assert runtime.applied_batches == []
    assert [item.status for item in result.action_results] == [
        ActionExecutionStatus.SKIPPED,
        ActionExecutionStatus.SKIPPED,
    ]
    assert all(
        item.failure_code is ConfigurationFailureCode.CAPABILITY_UNKNOWN
        for item in result.action_results
    )
    assert result.status is ConfigurationApplicationStatus.PARTIAL


def test_preflight_validates_every_etherchannel_member_interface():
    runtime = FakeControlPlaneRuntime()
    plan = _plan()
    plan.actions = [ConfigureEtherChannel(
        id="cp/ec",
        phase=ControlPlanePhase.L2_RESILIENCY,
        device_id="sw1",
        device_name="SW1",
        model="2960",
        site_id="hq",
        required_capability=
            ControlPlaneCapabilityDimension.ETHERCHANNEL_LACP_CONFIG,
        etherchannel_id="ec/one",
        peer_device_id="sw2",
        protocol=EtherChannelProtocol.LACP,
        channel_group=1,
        port_channel_interface="Port-channel1",
        member_interfaces=["FastEthernet0/1", "FastEthernet0/2"],
    )]
    plan.verification_expectations = []
    plan.failure_scenarios = []

    result = _apply(runtime, plan)

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.INTERFACE_NOT_FOUND
    assert "FastEthernet0/2" in result.preflight_errors[0]
    assert runtime.applied_batches == []


def test_failed_action_blocks_its_dependency_and_scenario():
    runtime = FakeControlPlaneRuntime()
    runtime.failed_action_ids.add("cp/a")

    result = _apply(runtime)

    assert [item.status for item in result.action_results] == [
        ActionExecutionStatus.FAILED,
        ActionExecutionStatus.DEPENDENCY_BLOCKED,
    ]
    assert runtime.scenarios == []
    assert result.scenario_results[0].status is ActionExecutionStatus.DEPENDENCY_BLOCKED
    assert result.status is ConfigurationApplicationStatus.FAILED


def test_unbound_failover_expectation_is_reported_as_unobservable():
    runtime = FakeControlPlaneRuntime()
    plan = _plan()
    unbound = _expectation(
        "verify/unbound-failover",
        ControlPlaneVerificationKind.LINK_FAILURE_CONVERGENCE,
        "cp/b",
        "sw2",
        ControlPlaneCapabilityDimension.STP_FAILOVER,
    )
    plan.verification_expectations.append(unbound)

    result = _apply(runtime, plan)

    assert [item.expectation_id for item in result.failover_results] == [unbound.id]
    assert result.failover_results[0].status is ActionExecutionStatus.UNOBSERVABLE
    assert result.failover_status is ActionExecutionStatus.UNOBSERVABLE
    assert result.status is ConfigurationApplicationStatus.PARTIAL


def test_scenario_without_mandatory_restore_is_never_executed():
    runtime = FakeControlPlaneRuntime()
    plan = _plan()
    plan.failure_scenarios[0].restore_required = False

    result = _apply(runtime, plan)

    assert runtime.scenarios == []
    assert result.scenario_results[0].status is ActionExecutionStatus.FAILED
    assert result.scenario_results[0].failure_code is ConfigurationFailureCode.CLEANUP_FAILED
    assert result.status is ConfigurationApplicationStatus.FAILED


def test_missing_verification_result_is_unknown_and_application_is_partial():
    runtime = FakeControlPlaneRuntime()
    runtime.omit_verification_ids.add("verify/state")

    result = _apply(runtime)

    assert result.observed_results[0].status is ActionExecutionStatus.UNKNOWN
    assert result.observed_status is ActionExecutionStatus.UNKNOWN
    assert result.status is ConfigurationApplicationStatus.PARTIAL


def test_typed_scenario_render_failure_is_an_application_failure():
    runtime = FakeControlPlaneRuntime()
    plan = _plan()
    runtime.scenario_result = RuntimeFailureScenarioResult(
        scenario_id=plan.failure_scenarios[0].id,
        injection=RuntimeActionMutation(
            action_id="scenario/link-1:shutdown",
            applied=False,
            failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
            message="typed render failed",
        ),
    )

    result = _apply(runtime, plan)

    assert result.scenario_results[0].failure_code is ConfigurationFailureCode.APPLICATION_FAILED
    assert result.status is ConfigurationApplicationStatus.FAILED


def test_scenario_rejects_mismatched_before_during_after_contract():
    runtime = FakeControlPlaneRuntime()
    plan = _plan()
    failure, recovery = plan.verification_expectations[-2:]
    runtime.scenario_result = _successful_runtime_scenario(
        plan.failure_scenarios[0], failure, recovery,
    )
    runtime.scenario_result.after.expectation_id = failure.id

    result = _apply(runtime, plan)

    scenario = result.scenario_results[0]
    assert scenario.status is ActionExecutionStatus.FAILED
    assert scenario.failure_code is ConfigurationFailureCode.SESSION_FAILED
    assert scenario.baseline_status is ActionExecutionStatus.VERIFIED
    assert scenario.injection_status is ActionExecutionStatus.APPLIED
    assert scenario.failover_status is ActionExecutionStatus.VERIFIED
    assert scenario.restore_status is ActionExecutionStatus.APPLIED
    assert scenario.recovery_status is ActionExecutionStatus.VERIFIED
    assert "after" in scenario.message


def test_scenario_gates_recovery_capability_before_runtime_execution():
    runtime = FakeControlPlaneRuntime()
    plan = _plan()
    recovery = plan.verification_expectations[-1]
    recovery.required_capability = ControlPlaneCapabilityDimension.ROUTING_FAILOVER
    profile = ControlPlaneCapabilityProfile.supported("2960")
    del profile.dimensions[ControlPlaneCapabilityDimension.ROUTING_FAILOVER]

    result = _apply(runtime, plan, capabilities={"2960": profile})

    assert runtime.scenarios == []
    assert result.scenario_results[0].status is ActionExecutionStatus.UNOBSERVABLE
    assert result.scenario_results[0].failure_code is ConfigurationFailureCode.CAPABILITY_UNKNOWN


def test_applied_fault_without_restore_attempt_is_a_cleanup_failure():
    runtime = FakeControlPlaneRuntime()
    plan = _plan()
    failure, recovery = plan.verification_expectations[-2:]
    runtime.scenario_result = RuntimeFailureScenarioResult(
        scenario_id=plan.failure_scenarios[0].id,
        before=RuntimeControlPlaneVerification(
            expectation_id=failure.id,
            stage=ControlPlaneExecutionStage.BEHAVIOR,
            status=ActionExecutionStatus.VERIFIED,
        ),
        injection=RuntimeActionMutation(action_id=plan.failure_scenarios[0].id, applied=True),
        during=RuntimeControlPlaneVerification(
            expectation_id=failure.id,
            stage=ControlPlaneExecutionStage.FAILOVER,
            status=ActionExecutionStatus.VERIFIED,
        ),
        restore_attempted=False,
        after=RuntimeControlPlaneVerification(
            expectation_id=recovery.id,
            stage=ControlPlaneExecutionStage.RESTORE,
            status=ActionExecutionStatus.SKIPPED,
        ),
    )

    result = _apply(runtime, plan)

    scenario = result.scenario_results[0]
    assert scenario.status is ActionExecutionStatus.FAILED
    assert scenario.failure_code is ConfigurationFailureCode.CLEANUP_FAILED
    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.CLEANUP_FAILED


def test_cleanup_failure_takes_precedence_over_invalid_scenario_evidence():
    runtime = FakeControlPlaneRuntime()
    plan = _plan()
    failure, recovery = plan.verification_expectations[-2:]
    runtime.scenario_result = RuntimeFailureScenarioResult(
        scenario_id=plan.failure_scenarios[0].id,
        before=RuntimeControlPlaneVerification(
            expectation_id=failure.id,
            stage=ControlPlaneExecutionStage.BEHAVIOR,
            status=ActionExecutionStatus.VERIFIED,
        ),
        injection=RuntimeActionMutation(
            action_id=plan.failure_scenarios[0].id,
            applied=True,
        ),
        during=RuntimeControlPlaneVerification(
            expectation_id=failure.id,
            stage=ControlPlaneExecutionStage.FAILOVER,
            status=ActionExecutionStatus.VERIFIED,
        ),
        restore_attempted=False,
        after=RuntimeControlPlaneVerification(
            expectation_id=failure.id,
            stage=ControlPlaneExecutionStage.RESTORE,
            status=ActionExecutionStatus.SKIPPED,
        ),
    )

    result = _apply(runtime, plan)

    scenario = result.scenario_results[0]
    assert scenario.failure_code is ConfigurationFailureCode.CLEANUP_FAILED
    assert scenario.injection_status is ActionExecutionStatus.APPLIED
    assert scenario.restore_status is ActionExecutionStatus.SKIPPED
