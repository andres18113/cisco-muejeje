from src.packet_tracer_mcp.application.use_cases.apply_configuration import ConfigurationApplicator
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import ConfigurationActionType
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    EnvironmentFingerprint,
    build_deployment_manifest,
)
from src.packet_tracer_mcp.domain.enterprise.models.execution import MutationDisposition
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import RuntimeActionMutation
from test_configuration_application import (
    FakeConfigurationRuntime,
    _compiled,
    _supported_capabilities,
)


def _runtime_context(manifest, *, capability_snapshot_hash: str = ""):
    return ConfigurationRuntimeContext(
        environment_fingerprint=manifest.environment_fingerprint,
        capability_snapshot_hash=capability_snapshot_hash,
    )


class _NameRecordingRuntime(FakeConfigurationRuntime):
    def __init__(self, topology):
        super().__init__(topology)
        self.attempted_targets: list[tuple[str, str]] = []

    def apply_actions(self, actions):
        self.attempted_targets.extend(
            (action.device_id, action.device_name) for action in actions
        )
        return super().apply_actions(actions)


class _IdempotentRuntime(FakeConfigurationRuntime):
    def __init__(self, topology):
        super().__init__(topology)
        self.seen: set[str] = set()

    def apply_actions(self, actions):
        self.apply_calls.append([action.id for action in actions])
        results = []
        for action in actions:
            repeated = action.id in self.seen
            self.seen.add(action.id)
            results.append(RuntimeActionMutation(
                action_id=action.id,
                applied=True,
                operation=action.operation,
                disposition=(
                    MutationDisposition.NO_OP
                    if repeated else MutationDisposition.CHANGED
                ),
            ))
        return results


def test_manifest_retargets_runtime_copies_by_semantic_id_after_display_rename():
    topology, plan = _compiled()
    renamed = topology.model_copy(deep=True)
    action_device_ids = {action.device_id for action in plan.actions}
    target = next(item for item in renamed.devices if item.id in action_device_ids)
    original_name = target.name
    target.name = f"{original_name}-RENAMED"
    assert renamed.physical_identity_hash == plan.source_topology_hash

    runtime = _NameRecordingRuntime(renamed)
    manifest = build_deployment_manifest(
        renamed,
        runtime.inventory(),
        fingerprint=EnvironmentFingerprint(backend_version="9.0.1.0858"),
    )

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
        deployment_manifest=manifest,
        runtime_context=_runtime_context(
            manifest, capability_snapshot_hash="capability/snapshot/sha256",
        ),
    )

    assert result.deployment_id == manifest.deployment_id
    assert result.status.value in {"verified", "partial"}
    attempted = [identifier for batch in runtime.apply_calls for identifier in batch]
    assert attempted
    target_names = [
        name for device_id, name in runtime.attempted_targets
        if device_id == target.id
    ]
    assert target_names
    assert set(target_names) == {target.name}
    assert any(item.status is ActionExecutionStatus.APPLIED for item in result.action_results)
    assert result.evidence_records
    assert all(
        item.environment_fingerprint == manifest.environment_fingerprint.semantic_hash
        for item in result.evidence_records
    )
    assert all(
        item.capability_snapshot_hash == "capability/snapshot/sha256"
        for item in result.evidence_records
    )
    assert all(
        item.environment_fingerprint != item.capability_snapshot_hash
        for item in result.evidence_records
    )


def test_manifest_hash_mismatch_blocks_before_inventory_mutation():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    manifest = build_deployment_manifest(
        topology,
        runtime.inventory(),
        fingerprint=EnvironmentFingerprint(),
    ).model_copy(update={"physical_topology_hash": "wrong"})

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
        deployment_manifest=manifest,
        runtime_context=_runtime_context(manifest),
    )

    assert result.status.value == "failed"
    assert result.dirty_state.value == "clean"
    assert not runtime.apply_calls


def test_modern_e5_plan_requires_manifest_before_runtime_inventory():
    class InventoryCountingRuntime(FakeConfigurationRuntime):
        def __init__(self, topology):
            super().__init__(topology)
            self.inventory_calls = 0

        def inventory(self):
            self.inventory_calls += 1
            return super().inventory()

    topology, plan = _compiled()
    plan = plan.model_copy(update={
        "source_topology_hash_schema": "physical-topology-v2",
    })
    assert plan.source_topology_hash_schema == "physical-topology-v2"
    runtime = InventoryCountingRuntime(topology)

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert result.failure_code is ConfigurationFailureCode.DEPLOYMENT_MANIFEST_REQUIRED
    assert runtime.inventory_calls == 0
    assert runtime.apply_calls == []


def test_e5_rejects_manifest_environment_mismatch_before_runtime_inventory():
    class InventoryCountingRuntime(FakeConfigurationRuntime):
        def __init__(self, topology):
            super().__init__(topology)
            self.inventory_calls = 0

        def inventory(self):
            self.inventory_calls += 1
            return super().inventory()

    topology, plan = _compiled()
    runtime = InventoryCountingRuntime(topology)
    manifest_environment = EnvironmentFingerprint(
        backend_version="9.0.1.0858",
        extension_version="e95",
    )
    manifest = build_deployment_manifest(
        topology,
        runtime.inventory(),
        fingerprint=manifest_environment,
    )
    runtime.inventory_calls = 0

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
        deployment_manifest=manifest,
        runtime_context=ConfigurationRuntimeContext(
            environment_fingerprint=manifest_environment.model_copy(
                update={"extension_version": "different"},
            ),
        ),
    )

    assert result.failure_code is ConfigurationFailureCode.ENVIRONMENT_FINGERPRINT_MISMATCH
    assert runtime.inventory_calls == 0
    assert runtime.apply_calls == []


def test_unsatisfied_e5_verification_prerequisite_is_reported_as_blocked():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    runtime.fail_action_types = {ConfigurationActionType.CREATE_VLAN}

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert len(result.verification_results) == len(plan.verification_expectations)
    assert any(
        item.status is ActionExecutionStatus.DEPENDENCY_BLOCKED
        for item in result.verification_results
    )


def test_second_deterministic_apply_converges_as_noop_without_duplicates():
    topology, plan = _compiled()
    runtime = _IdempotentRuntime(topology)
    applicator = ConfigurationApplicator(runtime)

    first = applicator.apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )
    second = applicator.apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert first.status.value == "verified"
    assert second.status.value == "verified"
    assert all(
        item.status is ActionExecutionStatus.NO_OP
        for item in second.action_results
    )
    assert runtime.seen == {action.id for action in plan.actions}
