"""E9.5 manifest identity, idempotency, and dirty-state coverage for E8/E9."""

from __future__ import annotations

from collections.abc import Sequence

from src.packet_tracer_mcp.application.use_cases.apply_control_plane import (
    ControlPlaneApplicator,
)
from src.packet_tracer_mcp.application.use_cases.apply_security import SecurityApplicator
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationFailureCode,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ControlPlaneAction,
    ControlPlaneVerificationExpectation,
    LinkFailureScenario,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane_runtime import (
    ControlPlaneExecutionStage,
    RuntimeControlPlaneVerification,
    RuntimeFailureScenarioResult,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    DeploymentBinding,
    DeploymentManifest,
)
from src.packet_tracer_mcp.domain.enterprise.models.execution import (
    CompensationStatus,
    DirtyState,
    MutationDisposition,
)
from src.packet_tracer_mcp.domain.enterprise.models.security_plan import (
    SecurityAction,
    SecurityVerificationExpectation,
)
from src.packet_tracer_mcp.domain.enterprise.models.verification import (
    PrerequisiteKind,
    VerificationPrerequisite,
)
from tests.test_control_plane_application import (
    FakeControlPlaneRuntime,
    _apply as _apply_control_plane,
    _plan as _control_plane_plan,
    _successful_runtime_scenario,
)
from tests.test_enterprise_security import _compile as _compile_security
from tests.test_security_application import (
    FakeSecurityRuntime,
    _capabilities as _security_capabilities,
    _foundations as _security_foundations,
)


class _RenamedSecurityRuntime(FakeSecurityRuntime):
    def __init__(self, targets: list[RuntimeConfigurationTarget]) -> None:
        super().__init__()
        self.targets = targets
        self.applied_names: list[str] = []
        self.behavior_names: list[tuple[str, str]] = []
        self.cleanup_names: list[str] = []

    def inventory(self):
        self.calls.append(("inventory", []))
        return self.targets

    def apply_actions(self, actions: Sequence[SecurityAction]):
        self.applied_names.extend(item.device_name for item in actions)
        return super().apply_actions(actions)

    def verify_behavior(self, expectations, stage):
        self.behavior_names.extend(
            (item.source_device_name, item.destination_device_name)
            for item in expectations
        )
        return super().verify_behavior(expectations, stage)

    def cleanup_actions(self, actions: Sequence[SecurityAction]):
        self.cleanup_names.extend(item.device_name for item in actions)
        return super().cleanup_actions(actions)


class _RenamedControlPlaneRuntime(FakeControlPlaneRuntime):
    def __init__(self, targets: list[RuntimeConfigurationTarget]) -> None:
        super().__init__()
        self.targets = targets
        self.applied_names: list[str] = []
        self.verified_source_names: list[str] = []
        self.scenario_names: list[tuple[str, str, str, str]] = []

    def inventory(self):
        self.inventory_calls += 1
        return self.targets

    def apply_actions(self, actions: Sequence[ControlPlaneAction]):
        self.applied_names.extend(item.device_name for item in actions)
        return super().apply_actions(actions)

    def verify(self, expectations: Sequence[ControlPlaneVerificationExpectation]):
        self.verified_source_names.extend(
            str(item.expected.get("source_device_name") or "")
            for item in expectations
        )
        return super().verify(expectations)

    def execute_failure_scenario(
        self,
        scenario: LinkFailureScenario,
        failure_expectation: ControlPlaneVerificationExpectation,
        recovery_expectation: ControlPlaneVerificationExpectation,
    ):
        self.scenario_names.append((
            scenario.target_device_name,
            scenario.peer_device_name,
            scenario.probe_source_device_name,
            scenario.probe_destination_device_name,
        ))
        return super().execute_failure_scenario(
            scenario, failure_expectation, recovery_expectation,
        )


def _security_manifest(plan):
    names = {
        "r1": ("HQ-R1-LIVE", "2911"),
        "sw1": ("HQ-SW1-LIVE", "2960-24TT"),
        "guest-pc": ("GUEST-PC-LIVE", "PC-PT"),
        "sales-pc": ("SALES-PC-LIVE", "PC-PT"),
        "web": ("WEB-SRV-LIVE", "Server-PT"),
        "internet": ("INTERNET-SRV-LIVE", "Server-PT"),
    }
    interfaces = {
        "r1": ["GigabitEthernet0/0", "GigabitEthernet0/1"],
        "sw1": ["FastEthernet0/1", "GigabitEthernet0/1"],
    }
    targets = [
        RuntimeConfigurationTarget(
            device_name=name,
            model=model,
            interfaces=interfaces.get(identifier, []),
            runtime_identifier=f"runtime/{identifier}",
        )
        for identifier, (name, model) in names.items()
    ]
    manifest = DeploymentManifest(
        deployment_id="deployment/security-renamed",
        physical_topology_hash=plan.source_topology_hash,
        bindings=[
            DeploymentBinding(
                semantic_device_id=identifier,
                deployed_name=name,
                model=model,
                runtime_identifier=f"runtime/{identifier}",
            )
            for identifier, (name, model) in names.items()
        ],
    )
    return manifest, targets, names


def _control_plane_manifest(plan):
    names = {"sw1": "SW1-LIVE", "sw2": "SW2-LIVE"}
    interfaces = {
        "sw1": ["FastEthernet0/1"],
        "sw2": ["FastEthernet0/2"],
    }
    targets = [
        RuntimeConfigurationTarget(
            device_name=name,
            model="2960",
            interfaces=interfaces[identifier],
            runtime_identifier=f"runtime/{identifier}",
        )
        for identifier, name in names.items()
    ]
    manifest = DeploymentManifest(
        deployment_id="deployment/control-plane-renamed",
        physical_topology_hash=plan.source_topology_hash,
        bindings=[
            DeploymentBinding(
                semantic_device_id=identifier,
                deployed_name=name,
                model="2960",
                runtime_identifier=f"runtime/{identifier}",
            )
            for identifier, name in names.items()
        ],
    )
    return manifest, targets, names


def test_security_manifest_retargets_actions_behavior_and_cleanup_by_semantic_id():
    plan = _compile_security().plan
    manifest, targets, names = _security_manifest(plan)
    runtime = _RenamedSecurityRuntime(targets)

    result = SecurityApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        actual_source_service_hash=plan.source_service_hash,
        foundational_statuses=_security_foundations(plan),
        capabilities=_security_capabilities(),
        cleanup_control=True,
        deployment_manifest=manifest,
    )

    assert result.deployment_id == manifest.deployment_id
    assert set(runtime.applied_names) == {names["r1"][0], names["sw1"][0]}
    assert set(runtime.cleanup_names) == {names["r1"][0], names["sw1"][0]}
    assert (names["guest-pc"][0], names["web"][0]) in runtime.behavior_names
    assert result.execution_journal is not None
    assert result.execution_journal.cleanup_status is CompensationStatus.SUCCEEDED
    assert result.dirty_state is DirtyState.CLEAN


def test_security_manifest_hash_mismatch_blocks_before_inventory_or_mutation():
    plan = _compile_security().plan
    manifest, targets, _names = _security_manifest(plan)
    runtime = _RenamedSecurityRuntime(targets)
    manifest = manifest.model_copy(update={"physical_topology_hash": "wrong"})

    result = SecurityApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        actual_source_service_hash=plan.source_service_hash,
        foundational_statuses=_security_foundations(plan),
        capabilities=_security_capabilities(),
        deployment_manifest=manifest,
    )

    assert result.failure_code is ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
    assert runtime.calls == []
    assert result.dirty_state is DirtyState.CLEAN


def test_security_manifest_never_falls_back_to_a_planned_display_name():
    plan = _compile_security().plan
    manifest, targets, _names = _security_manifest(plan)
    manifest = manifest.model_copy(update={
        "bindings": [
            item for item in manifest.bindings
            if item.semantic_device_id != "web"
        ],
    })
    targets.append(RuntimeConfigurationTarget(
        device_name="WEB-SRV", model="Server-PT",
    ))
    runtime = _RenamedSecurityRuntime(targets)

    result = SecurityApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        actual_source_service_hash=plan.source_service_hash,
        foundational_statuses=_security_foundations(plan),
        capabilities=_security_capabilities(),
        deployment_manifest=manifest,
    )

    assert result.failure_code is ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
    assert [kind for kind, _ids in runtime.calls] == ["inventory"]
    assert runtime.applied_names == []


def test_control_plane_manifest_retargets_actions_observation_and_scenario():
    plan = _control_plane_plan()
    manifest, targets, names = _control_plane_manifest(plan)
    runtime = _RenamedControlPlaneRuntime(targets)

    result = _apply_control_plane(
        runtime,
        plan,
        deployment_manifest=manifest,
    )

    assert result.deployment_id == manifest.deployment_id
    assert set(runtime.applied_names) == set(names.values())
    assert set(runtime.verified_source_names) == set(names.values())
    assert runtime.scenario_names == [(
        names["sw1"], names["sw2"], names["sw1"], names["sw2"],
    )]
    assert result.execution_journal is not None
    assert result.execution_journal.cleanup_status is CompensationStatus.SUCCEEDED
    assert result.dirty_state is DirtyState.CLEAN


def test_control_plane_manifest_hash_mismatch_blocks_before_inventory_or_mutation():
    plan = _control_plane_plan()
    manifest, targets, _names = _control_plane_manifest(plan)
    runtime = _RenamedControlPlaneRuntime(targets)
    manifest = manifest.model_copy(update={"physical_topology_hash": "wrong"})

    result = _apply_control_plane(runtime, plan, deployment_manifest=manifest)

    assert result.failure_code is ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
    assert runtime.inventory_calls == 0
    assert runtime.applied_batches == []
    assert result.dirty_state is DirtyState.CLEAN


def test_control_plane_manifest_never_falls_back_to_a_planned_display_name():
    plan = _control_plane_plan()
    manifest, targets, _names = _control_plane_manifest(plan)
    manifest = manifest.model_copy(update={
        "bindings": [
            item for item in manifest.bindings
            if item.semantic_device_id != "sw2"
        ],
    })
    targets.append(RuntimeConfigurationTarget(
        device_name="SW2", model="2960", interfaces=["FastEthernet0/2"],
    ))
    runtime = _RenamedControlPlaneRuntime(targets)

    result = _apply_control_plane(runtime, plan, deployment_manifest=manifest)

    assert result.failure_code is ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
    assert runtime.inventory_calls == 1
    assert runtime.applied_batches == []


def test_security_dependencies_accept_no_op_and_reasserted_results():
    class IdempotentRuntime(FakeSecurityRuntime):
        def apply_actions(self, actions):
            self.calls.append(("apply", [item.id for item in actions]))
            return [RuntimeActionMutation(
                action_id=item.id,
                applied=True,
                disposition=(
                    MutationDisposition.NO_OP
                    if index % 2 == 0 else MutationDisposition.REASSERTED
                ),
            ) for index, item in enumerate(actions)]

    runtime = IdempotentRuntime()
    plan = _compile_security().plan
    result = SecurityApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        actual_source_service_hash=plan.source_service_hash,
        foundational_statuses=_security_foundations(plan),
        capabilities=_security_capabilities(),
    )

    assert not any(
        item.status is ActionExecutionStatus.DEPENDENCY_BLOCKED
        for item in result.action_results
    )
    assert {item.status for item in result.action_results} <= {
        ActionExecutionStatus.NO_OP,
        ActionExecutionStatus.REASSERTED,
    }


def test_control_plane_dependencies_accept_no_op_and_reasserted_results():
    class IdempotentRuntime(FakeControlPlaneRuntime):
        def apply_actions(self, actions):
            self.applied_batches.append([item.id for item in actions])
            return [RuntimeActionMutation(
                action_id=item.id,
                applied=True,
                disposition=(
                    MutationDisposition.NO_OP
                    if item.id == "cp/a" else MutationDisposition.REASSERTED
                ),
            ) for item in actions]

    runtime = IdempotentRuntime()
    result = _apply_control_plane(runtime)

    assert runtime.applied_batches == [["cp/a"], ["cp/b"]]
    assert [item.status for item in result.action_results] == [
        ActionExecutionStatus.NO_OP,
        ActionExecutionStatus.REASSERTED,
    ]
    assert result.status.value == "verified"


def test_security_failed_cleanup_is_dirty_and_never_reported_as_rollback():
    class CleanupFailureRuntime(FakeSecurityRuntime):
        def cleanup_actions(self, actions):
            self.calls.append(("cleanup", [item.id for item in actions]))
            return [RuntimeActionMutation(
                action_id=item.id,
                applied=False,
                disposition=MutationDisposition.FAILED,
                failure_code=ConfigurationFailureCode.SECURITY_CLEANUP_FAILED,
            ) for item in actions]

    runtime = CleanupFailureRuntime()
    plan = _compile_security().plan
    result = SecurityApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        actual_source_service_hash=plan.source_service_hash,
        foundational_statuses=_security_foundations(plan),
        capabilities=_security_capabilities(),
        cleanup_control=True,
    )

    assert result.execution_journal is not None
    assert result.execution_journal.cleanup_status is CompensationStatus.FAILED
    assert result.dirty_state is DirtyState.DIRTY_UNRECOVERABLE


def test_security_cleanup_acceptance_without_recovery_proof_is_unknown():
    runtime = FakeSecurityRuntime()
    runtime.cleanup_status = ActionExecutionStatus.FAILED
    plan = _compile_security().plan

    result = SecurityApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        actual_source_service_hash=plan.source_service_hash,
        foundational_statuses=_security_foundations(plan),
        capabilities=_security_capabilities(),
        cleanup_control=True,
    )

    assert result.execution_journal is not None
    assert result.execution_journal.cleanup_status is CompensationStatus.UNKNOWN
    assert result.dirty_state is DirtyState.UNKNOWN


def test_control_plane_applied_fault_without_restore_marks_deployment_dirty():
    runtime = FakeControlPlaneRuntime()
    plan = _control_plane_plan()
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
            expectation_id=recovery.id,
            stage=ControlPlaneExecutionStage.RESTORE,
            status=ActionExecutionStatus.SKIPPED,
        ),
    )

    result = _apply_control_plane(runtime, plan)

    assert result.execution_journal is not None
    assert result.execution_journal.cleanup_status is CompensationStatus.FAILED
    assert result.dirty_state is DirtyState.DIRTY_UNRECOVERABLE


def test_control_plane_restore_acceptance_without_recovery_proof_is_unknown():
    runtime = FakeControlPlaneRuntime()
    plan = _control_plane_plan()
    failure, recovery = plan.verification_expectations[-2:]
    runtime.scenario_result = _successful_runtime_scenario(
        plan.failure_scenarios[0], failure, recovery,
    )
    runtime.scenario_result.after.status = ActionExecutionStatus.UNKNOWN

    result = _apply_control_plane(runtime, plan)

    assert result.execution_journal is not None
    assert result.execution_journal.cleanup_status is CompensationStatus.UNKNOWN
    assert result.dirty_state is DirtyState.UNKNOWN


def test_security_emits_one_typed_evidence_record_for_every_executed_stage():
    runtime = FakeSecurityRuntime()
    plan = _compile_security().plan

    result = SecurityApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        actual_source_service_hash=plan.source_service_hash,
        foundational_statuses=_security_foundations(plan),
        capabilities=_security_capabilities(),
        cleanup_control=True,
    )

    stage_fields = {
        "baseline": "baseline_status",
        "direct_state": "direct_status",
        "enforcement_behavior": "enforcement_status",
        "cleanup_recovery": "cleanup_status",
    }
    expected_ids = {
        f"evidence/security/{verification.expectation_id}/{stage}"
        for verification in result.verification_results
        for stage, field in stage_fields.items()
        if getattr(verification, field) is not ActionExecutionStatus.SKIPPED
    }
    actual_ids = [item.id for item in result.evidence_records]

    assert set(actual_ids) == expected_ids
    assert len(actual_ids) == len(set(actual_ids))
    assert all(item.subject and item.claim for item in result.evidence_records)
    assert all(item.backend == result.runtime_context.backend for item in result.evidence_records)


def test_security_typed_resource_prerequisite_blocks_runtime_observation():
    runtime = FakeSecurityRuntime()
    plan = _compile_security().plan
    direct = next(
        item for item in plan.verification_expectations
        if item.probe_kind.value == "direct_readback"
    )
    expectations = [
        item.model_copy(update={
            "verification_prerequisites": [VerificationPrerequisite(
                kind=PrerequisiteKind.RESOURCE_READY,
                reference_id="runtime/security-readback",
            )],
        }) if item.id == direct.id else item
        for item in plan.verification_expectations
    ]
    plan = plan.model_copy(update={"verification_expectations": expectations})

    result = SecurityApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        actual_source_service_hash=plan.source_service_hash,
        foundational_statuses=_security_foundations(plan),
        capabilities=_security_capabilities(),
    )

    direct_result = next(
        item for item in result.verification_results
        if item.expectation_id == direct.id
    )
    observed_ids = {
        identifier
        for kind, identifiers in runtime.calls if kind == "observe"
        for identifier in identifiers
    }
    evidence = next(
        item for item in result.evidence_records
        if item.id == f"evidence/security/{direct.id}/direct_state"
    )

    assert direct_result.direct_status is ActionExecutionStatus.DEPENDENCY_BLOCKED
    assert direct.id not in observed_ids
    assert evidence.source == "verification_prerequisite_gate"
    assert "resource_ready:runtime/security-readback" in evidence.limitations[0]


def test_control_plane_emits_typed_evidence_for_state_behavior_and_scenario():
    result = _apply_control_plane(FakeControlPlaneRuntime())

    expected_ids = {
        "evidence/control-plane/verify/state/observed",
        "evidence/control-plane/verify/reach/behavior",
        "evidence/control-plane/verify/failure/behavior",
        "evidence/control-plane/verify/failure/failover",
        "evidence/control-plane/verify/recovery/restore",
        "evidence/control-plane/scenario/scenario/link-1",
    }
    actual_ids = [item.id for item in result.evidence_records]

    assert set(actual_ids) == expected_ids
    assert len(actual_ids) == len(set(actual_ids))
    assert all(item.subject and item.claim for item in result.evidence_records)
    composed = next(
        item for item in result.evidence_records
        if item.id == "evidence/control-plane/scenario/scenario/link-1"
    )
    assert composed.observed_value["restore_attempted"] is True


def test_control_plane_typed_verification_prerequisite_blocks_downstream_probe():
    runtime = FakeControlPlaneRuntime()
    runtime.omit_verification_ids.add("verify/state")
    plan = _control_plane_plan()
    expectations = [
        item.model_copy(update={
            "verification_prerequisites": [VerificationPrerequisite(
                kind=PrerequisiteKind.VERIFICATION_VERIFIED,
                reference_id="verify/state",
            )],
        }) if item.id == "verify/reach" else item
        for item in plan.verification_expectations
    ]
    plan = plan.model_copy(update={"verification_expectations": expectations})

    result = _apply_control_plane(runtime, plan)

    behavior = next(
        item for item in result.behavior_results
        if item.expectation_id == "verify/reach"
    )
    evidence = next(
        item for item in result.evidence_records
        if item.id == "evidence/control-plane/verify/reach/behavior"
    )

    assert behavior.status is ActionExecutionStatus.DEPENDENCY_BLOCKED
    assert runtime.verified_batches == [["verify/state"]]
    assert evidence.source == "verification_prerequisite_gate"
    assert "verification_verified:verify/state" in evidence.limitations[0]


def test_control_plane_recovery_requires_verified_failover_evidence():
    runtime = FakeControlPlaneRuntime()
    plan = _control_plane_plan()
    failure, recovery = plan.verification_expectations[-2:]
    plan.verification_expectations[-1] = recovery.model_copy(update={
        "verification_prerequisites": [
            VerificationPrerequisite(
                kind=PrerequisiteKind.ACTION_APPLIED,
                reference_id=recovery.action_id,
            ),
            # Transitional compiler output used ACTION_APPLIED for an ID that
            # is actually a verification dependency. The applicator normalizes
            # that legacy shape before evaluating the scenario sequence.
            VerificationPrerequisite(
                kind=PrerequisiteKind.ACTION_APPLIED,
                reference_id=failure.id,
            ),
        ],
    })
    runtime.scenario_result = _successful_runtime_scenario(
        plan.failure_scenarios[0], failure, recovery,
    )
    runtime.scenario_result.during.status = ActionExecutionStatus.FAILED

    result = _apply_control_plane(runtime, plan)

    scenario = result.scenario_results[0]
    recovery_evidence = next(
        item for item in result.evidence_records
        if item.id == "evidence/control-plane/verify/recovery/restore"
    )

    assert scenario.failover_status is ActionExecutionStatus.FAILED
    assert scenario.recovery_status is ActionExecutionStatus.DEPENDENCY_BLOCKED
    assert scenario.after is not None
    assert scenario.after.evidence_method == "verification_prerequisite_gate"
    assert recovery_evidence.source == "verification_prerequisite_gate"
    assert "verification_verified:verify/failure" in recovery_evidence.limitations[0]
