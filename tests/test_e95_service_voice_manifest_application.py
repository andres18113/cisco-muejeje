"""E9.5 manifest identity and execution semantics for E6/E7 applicators."""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.apply_services import ServiceApplicator
from src.packet_tracer_mcp.application.use_cases.apply_voice import VoiceApplicator
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    EnvironmentFingerprint,
    build_deployment_manifest,
)
from src.packet_tracer_mcp.domain.enterprise.models.execution import MutationDisposition
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import BindPhoneToExtension

from test_enterprise_services import _fixture as _service_fixture
from test_enterprise_voice import _compile as _compile_voice
from test_enterprise_voice import _fixture as _voice_fixture
from test_service_application import FakeServiceRuntime, _foundation as _service_foundation
from test_voice_runtime import FakeVoiceRuntime, _profile

from src.packet_tracer_mcp.application.use_cases.compile_services import (
    compile_enterprise_services,
)


class _RecordingServiceRuntime(FakeServiceRuntime):
    def __init__(self, topology):
        super().__init__()
        self._topology = topology
        self.action_targets: list[tuple[str, str]] = []
        self.verification_targets: list[tuple[str, str, str]] = []
        self.inventory_calls = 0

    def inventory(self):
        self.inventory_calls += 1
        return [
            RuntimeConfigurationTarget(device_name=item.name, model=item.model)
            for item in self._topology.devices
        ]

    def apply_actions(self, actions):
        self.action_targets.extend(
            (item.host_device_id, item.host_device_name) for item in actions
        )
        return super().apply_actions(actions)

    def verify(self, expectation):
        self.verification_targets.append((
            expectation.host_device_id,
            expectation.host_device_name,
            expectation.client_device_name,
        ))
        return super().verify(expectation)


class _RecordingVoiceRuntime(FakeVoiceRuntime):
    def __init__(self, topology):
        super().__init__()
        self._topology = topology
        self.action_targets: list[object] = []
        self.inventory_calls = 0

    def inventory(self):
        self.inventory_calls += 1
        return [
            RuntimeConfigurationTarget(device_name=item.name, model=item.model)
            for item in self._topology.devices
        ]

    def apply_actions(self, actions):
        self.action_targets.extend(actions)
        return super().apply_actions(actions)


def _voice_foundation(plan):
    return {
        item.source_id: ActionExecutionStatus.VERIFIED
        for item in plan.foundational_requirements
    }


def _runtime_context(manifest):
    return ConfigurationRuntimeContext(
        environment_fingerprint=manifest.environment_fingerprint,
    )


def test_service_manifest_retargets_runtime_copies_without_mutating_plan():
    enterprise, topology, configuration, capabilities = _service_fixture()
    plan = compile_enterprise_services(
        enterprise, topology, configuration, capabilities=capabilities,
    ).plan
    original_action_names = {
        item.id: item.host_device_name for item in plan.actions
    }
    renamed = topology.model_copy(deep=True)
    for device in renamed.devices:
        device.name = f"LIVE-{device.name}"
    deployed_names = {item.id: item.name for item in renamed.devices}
    runtime = _RecordingServiceRuntime(renamed)
    manifest = build_deployment_manifest(
        renamed,
        runtime.inventory(),
        fingerprint=EnvironmentFingerprint(backend_version="9.0.1.0858"),
        deployment_id="deployment/e6-renamed",
    )

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_service_foundation(plan),
        capabilities=capabilities,
        deployment_manifest=manifest,
        runtime_context=_runtime_context(manifest),
    )

    assert result.deployment_id == manifest.deployment_id
    assert result.execution_journal is not None
    assert result.evidence_records
    assert result.execution_journal.deployment_id == manifest.deployment_id
    assert runtime.action_targets
    assert all(name == deployed_names[identifier] for identifier, name in runtime.action_targets)
    assert runtime.verification_targets
    for host_id, host_name, client_name in runtime.verification_targets:
        assert host_name == deployed_names[host_id]
        if client_name:
            assert client_name in deployed_names.values()
    assert {item.id: item.host_device_name for item in plan.actions} == original_action_names


def test_voice_manifest_retargets_call_control_and_phone_runtime_copies():
    _, topology, _, _, _ = _voice_fixture()
    plan = _compile_voice().plan
    original_action_names = {
        item.id: item.host_device_name for item in plan.actions
    }
    renamed = topology.model_copy(deep=True)
    for device in renamed.devices:
        device.name = f"LIVE-{device.name}"
    deployed_names = {item.id: item.name for item in renamed.devices}
    runtime = _RecordingVoiceRuntime(renamed)
    manifest = build_deployment_manifest(
        renamed,
        runtime.inventory(),
        fingerprint=EnvironmentFingerprint(backend_version="9.0.1.0858"),
        deployment_id="deployment/e7-renamed",
    )

    result = VoiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_voice_foundation(plan),
        capabilities=_profile(),
        deployment_manifest=manifest,
        runtime_context=_runtime_context(manifest),
    )

    assert result.deployment_id == manifest.deployment_id
    assert result.execution_journal is not None
    assert result.evidence_records
    assert runtime.action_targets
    assert all(
        item.host_device_name == deployed_names[item.host_device_id]
        for item in runtime.action_targets
    )
    bindings = [
        item for item in runtime.action_targets
        if isinstance(item, BindPhoneToExtension)
    ]
    assert bindings
    assert all(
        item.physical_device_name == deployed_names[item.phone_id]
        for item in bindings
    )
    assert {item.id: item.host_device_name for item in plan.actions} == original_action_names


def test_service_manifest_hash_mismatch_is_clean_and_precedes_inventory():
    enterprise, topology, configuration, capabilities = _service_fixture()
    plan = compile_enterprise_services(
        enterprise, topology, configuration, capabilities=capabilities,
    ).plan
    runtime = _RecordingServiceRuntime(topology)
    manifest = build_deployment_manifest(
        topology, runtime.inventory(), fingerprint=EnvironmentFingerprint(),
    ).model_copy(update={"physical_topology_hash": "wrong"})
    runtime.inventory_calls = 0

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_service_foundation(plan),
        capabilities=capabilities,
        deployment_manifest=manifest,
        runtime_context=_runtime_context(manifest),
    )

    assert result.failure_code is ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
    assert result.dirty_state.value == "clean"
    assert runtime.inventory_calls == 0
    assert runtime.apply_calls == []


def test_voice_manifest_hash_mismatch_is_clean_and_precedes_inventory():
    _, topology, _, _, _ = _voice_fixture()
    plan = _compile_voice().plan
    runtime = _RecordingVoiceRuntime(topology)
    manifest = build_deployment_manifest(
        topology, runtime.inventory(), fingerprint=EnvironmentFingerprint(),
    ).model_copy(update={"physical_topology_hash": "wrong"})
    runtime.inventory_calls = 0

    result = VoiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_voice_foundation(plan),
        capabilities=_profile(),
        deployment_manifest=manifest,
        runtime_context=_runtime_context(manifest),
    )

    assert result.failure_code is ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
    assert result.dirty_state.value == "clean"
    assert runtime.inventory_calls == 0
    assert runtime.applied == []


def test_modern_e6_plan_requires_manifest_before_runtime_inventory():
    enterprise, topology, configuration, capabilities = _service_fixture()
    plan = compile_enterprise_services(
        enterprise, topology, configuration, capabilities=capabilities,
    ).plan
    plan = plan.model_copy(update={
        "source_topology_hash_schema": "physical-topology-v2",
    })
    assert plan.source_topology_hash_schema == "physical-topology-v2"
    runtime = _RecordingServiceRuntime(topology)

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_service_foundation(plan),
        capabilities=capabilities,
    )

    assert result.failure_code is ConfigurationFailureCode.DEPLOYMENT_MANIFEST_REQUIRED
    assert runtime.inventory_calls == 0
    assert runtime.apply_calls == []


def test_e7_manifest_environment_mismatch_precedes_runtime_inventory():
    _, topology, _, _, _ = _voice_fixture()
    plan = _compile_voice().plan
    runtime = _RecordingVoiceRuntime(topology)
    manifest_environment = EnvironmentFingerprint(
        backend_version="9.0.1.0858",
        bridge_transport="file",
    )
    manifest = build_deployment_manifest(
        topology,
        runtime.inventory(),
        fingerprint=manifest_environment,
    )
    runtime.inventory_calls = 0

    result = VoiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_voice_foundation(plan),
        capabilities=_profile(),
        deployment_manifest=manifest,
        runtime_context=ConfigurationRuntimeContext(
            environment_fingerprint=manifest_environment.model_copy(
                update={"bridge_transport": "http"},
            ),
        ),
    )

    assert result.failure_code is ConfigurationFailureCode.ENVIRONMENT_FINGERPRINT_MISMATCH
    assert runtime.inventory_calls == 0
    assert runtime.applied == []


def test_service_manifest_missing_binding_never_falls_back_to_plan_name():
    enterprise, topology, configuration, capabilities = _service_fixture()
    plan = compile_enterprise_services(
        enterprise, topology, configuration, capabilities=capabilities,
    ).plan
    runtime = _RecordingServiceRuntime(topology)
    manifest = build_deployment_manifest(
        topology, runtime.inventory(), fingerprint=EnvironmentFingerprint(),
    )
    missing_id = plan.foundational_requirements[0].device_id
    manifest.bindings = [
        item for item in manifest.bindings
        if item.semantic_device_id != missing_id
    ]

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_service_foundation(plan),
        capabilities=capabilities,
        deployment_manifest=manifest,
        runtime_context=_runtime_context(manifest),
    )

    assert result.failure_code is ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
    assert runtime.apply_calls == []


def test_voice_manifest_missing_binding_never_falls_back_to_plan_name():
    _, topology, _, _, _ = _voice_fixture()
    plan = _compile_voice().plan
    runtime = _RecordingVoiceRuntime(topology)
    manifest = build_deployment_manifest(
        topology, runtime.inventory(), fingerprint=EnvironmentFingerprint(),
    )
    missing_id = plan.phone_assignments[0].phone_id
    manifest.bindings = [
        item for item in manifest.bindings
        if item.semantic_device_id != missing_id
    ]

    result = VoiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_voice_foundation(plan),
        capabilities=_profile(),
        deployment_manifest=manifest,
        runtime_context=_runtime_context(manifest),
    )

    assert result.failure_code is ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
    assert runtime.applied == []


def test_service_no_op_actions_satisfy_dependencies_and_reach_verification():
    class NoOpRuntime(FakeServiceRuntime):
        def apply_actions(self, actions):
            self.apply_calls.append([item.id for item in actions])
            return [
                RuntimeActionMutation(
                    action_id=item.id,
                    applied=True,
                    disposition=MutationDisposition.NO_OP,
                )
                for item in actions
            ]

    enterprise, topology, configuration, capabilities = _service_fixture()
    plan = compile_enterprise_services(
        enterprise, topology, configuration, capabilities=capabilities,
    ).plan
    runtime = NoOpRuntime()

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_service_foundation(plan),
        capabilities=capabilities,
    )

    assert result.status is ConfigurationApplicationStatus.VERIFIED
    assert all(item.status is ActionExecutionStatus.NO_OP for item in result.action_results)
    assert runtime.verify_calls
    assert result.execution_journal is not None
    assert all(
        item.disposition is MutationDisposition.NO_OP
        for item in result.execution_journal.entries
    )


def test_voice_reasserted_actions_satisfy_dependencies_and_registration():
    class ReassertingRuntime(FakeVoiceRuntime):
        def apply_actions(self, actions):
            self.applied.extend(item.id for item in actions)
            return [
                RuntimeActionMutation(
                    action_id=item.id,
                    applied=True,
                    disposition=MutationDisposition.REASSERTED,
                )
                for item in actions
            ]

    plan = _compile_voice().plan
    runtime = ReassertingRuntime()

    result = VoiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_voice_foundation(plan),
        capabilities=_profile(),
    )

    assert result.application_status is ActionExecutionStatus.APPLIED
    assert all(
        item.status is ActionExecutionStatus.REASSERTED
        for item in result.action_results
    )
    assert all(
        item.status is ActionExecutionStatus.VERIFIED
        for item in result.registrations
    )
    assert result.execution_journal is not None
    assert all(
        item.disposition is MutationDisposition.REASSERTED
        for item in result.execution_journal.entries
    )
