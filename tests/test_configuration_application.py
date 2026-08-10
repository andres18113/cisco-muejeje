"""E5 application: preflight, capability gates y separación apply/verify."""

from __future__ import annotations

from collections import defaultdict

from src.packet_tracer_mcp.application.use_cases.apply_configuration import (
    ConfigurationApplicator,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    DeviceCapabilities,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
    RuntimeVerification,
)
from src.packet_tracer_mcp.domain.models.plans import TopologyPlan

from test_enterprise_configuration import _fixture
from src.packet_tracer_mcp.application.use_cases.compile_configuration import (
    compile_enterprise_configuration,
)


class FakeConfigurationRuntime:
    def __init__(self, topology: TopologyPlan) -> None:
        self.targets = [
            RuntimeConfigurationTarget(
                device_name=device.name,
                model=device.model,
                interfaces=sorted({
                    port
                    for link in topology.links
                    for endpoint_id, port in (
                        (link.device_a_id, link.port_a), (link.device_b_id, link.port_b),
                    )
                    if endpoint_id == device.id
                } | ({"Vlan1"} if device.enterprise_role == "ip_phone" else set())),
            )
            for device in topology.devices
        ]
        self.apply_calls: list[list[str]] = []
        self.verify_calls: list[list[str]] = []
        self.fail_action_types: set[ConfigurationActionType] = set()
        self.verification_status = ActionExecutionStatus.VERIFIED

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        return self.targets

    def apply_actions(self, actions):
        self.apply_calls.append([action.id for action in actions])
        return [
            RuntimeActionMutation(
                action_id=action.id,
                applied=action.action_type not in self.fail_action_types,
                message=(
                    "forced failure"
                    if action.action_type in self.fail_action_types else "applied"
                ),
            )
            for action in actions
        ]

    def verify(self, expectations):
        self.verify_calls.append([expectation.id for expectation in expectations])
        return [
            RuntimeVerification(
                expectation_id=expectation.id,
                status=self.verification_status,
                evidence_method="fake_readback",
                fresh_evidence=True,
                fields={
                    field: FieldVerificationStatus.VERIFIED
                    for field in expectation.expected
                },
            )
            for expectation in expectations
        ]


def _compiled():
    enterprise, topology, policy = _fixture()
    compiled = compile_enterprise_configuration(enterprise, topology, policy)
    assert compiled.is_valid
    return topology, compiled.plan


def _supported_capabilities() -> dict[str, DeviceCapabilities]:
    return {
        "2911": DeviceCapabilities(
            model="2911", category="router", layer3=CapabilityStatus.SUPPORTED,
            supports_dhcp_server=CapabilityStatus.SUPPORTED,
        ),
        "2960-24TT": DeviceCapabilities(
            model="2960-24TT", category="switch",
            supports_vlan=CapabilityStatus.SUPPORTED,
            supports_trunk=CapabilityStatus.SUPPORTED,
        ),
    }


def test_source_topology_hash_mismatch_stops_before_any_mutation():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash="different-e4-hash",
        capabilities=_supported_capabilities(),
    )

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.SOURCE_TOPOLOGY_MISMATCH
    assert not runtime.apply_calls


def test_dependency_cycle_stops_preflight_before_inventory_or_mutation():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    first, second = plan.actions[:2]
    first.depends_on = [second.id]
    second.depends_on = [first.id]

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.DEPENDENCY_BLOCKED
    assert not runtime.apply_calls


def test_missing_capability_snapshot_is_unknown_and_not_blindly_applied():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
    )
    network_actions = [
        item for item in result.action_results
        if next(action for action in plan.actions if action.id == item.action_id)
        .required_capability.startswith("supports_")
    ]

    assert network_actions
    assert all(item.status is ActionExecutionStatus.SKIPPED for item in network_actions)
    assert all(
        item.failure_code is ConfigurationFailureCode.CAPABILITY_UNKNOWN
        for item in network_actions
    )


def test_runtime_model_mismatch_stops_preflight_without_partial_application():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    target = next(item for item in runtime.targets if item.device_name == "__MCP_E5_ACCESS")
    target.model = "NOT-A-2960"

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
    assert not runtime.apply_calls


def test_actions_are_submitted_by_phase_and_not_one_bridge_call_per_line():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert result.status is ConfigurationApplicationStatus.VERIFIED
    assert len(runtime.apply_calls) == len({action.phase for action in plan.actions})
    assert any(len(call) > 1 for call in runtime.apply_calls)
    assert all(item.status is ActionExecutionStatus.APPLIED for item in result.action_results)


def test_application_result_records_generic_runtime_reproducibility_context():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    context = ConfigurationRuntimeContext(
        backend="packet_tracer",
        backend_version="9.0.1.0858",
        capability_snapshot_hash="snapshot-hash",
    )

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
        runtime_context=context,
    )

    assert result.runtime_context == context
    assert result.compact_summary()["runtime_context"] == context.model_dump(mode="json")


def test_failed_vlan_blocks_dependent_access_and_trunk_actions():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    runtime.fail_action_types = {ConfigurationActionType.CREATE_VLAN}

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )
    by_id = {item.action_id: item for item in result.action_results}
    access_and_trunks = [
        action for action in plan.actions
        if action.action_type in {
            ConfigurationActionType.CONFIGURE_ACCESS_PORT,
            ConfigurationActionType.CONFIGURE_TRUNK,
        }
    ]

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert all(
        by_id[action.id].status is ActionExecutionStatus.DEPENDENCY_BLOCKED
        for action in access_and_trunks
    )
    attempted = {action_id for call in runtime.apply_calls for action_id in call}
    assert not attempted.intersection(action.id for action in access_and_trunks)


def test_unknown_svi_is_skipped_without_becoming_unsupported_or_blocking_l2():
    enterprise, topology, policy = _fixture()
    policy.gateway_device_ids = {"hq": "sw-dist"}
    policy.dhcp_server_device_ids = {"hq": "sw-dist"}
    plan = compile_enterprise_configuration(enterprise, topology, policy).plan
    runtime = FakeConfigurationRuntime(topology)
    capabilities = _supported_capabilities()
    capabilities["2960-24TT"].supports_svi = CapabilityStatus.UNKNOWN
    capabilities["2960-24TT"].supports_dhcp_server = CapabilityStatus.UNKNOWN

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=capabilities,
    )
    by_id = {item.action_id: item for item in result.action_results}
    svi_actions = plan.actions_of_type(ConfigurationActionType.CONFIGURE_SVI)
    vlan_actions = plan.actions_of_type(ConfigurationActionType.CREATE_VLAN)

    assert result.status is ConfigurationApplicationStatus.PARTIAL
    assert all(by_id[action.id].status is ActionExecutionStatus.SKIPPED for action in svi_actions)
    assert all(
        by_id[action.id].failure_code is ConfigurationFailureCode.CAPABILITY_UNKNOWN
        for action in svi_actions
    )
    assert all(by_id[action.id].status is ActionExecutionStatus.APPLIED for action in vlan_actions)


def test_explicitly_unsupported_required_action_is_not_attempted():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    capabilities = _supported_capabilities()
    capabilities["2911"].supports_dhcp_server = CapabilityStatus.UNSUPPORTED

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=capabilities,
    )
    pool = plan.actions_of_type(ConfigurationActionType.CONFIGURE_DHCP_POOL)[0]
    pool_result = next(item for item in result.action_results if item.action_id == pool.id)
    attempted = {action_id for call in runtime.apply_calls for action_id in call}

    assert pool_result.status is ActionExecutionStatus.SKIPPED
    assert pool_result.failure_code is ConfigurationFailureCode.CAPABILITY_UNSUPPORTED
    assert pool.id not in attempted


def test_applied_is_not_promoted_to_verified_when_readback_is_partial():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    runtime.verification_status = ActionExecutionStatus.PARTIAL

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert result.status is ConfigurationApplicationStatus.PARTIAL
    assert all(item.status is ActionExecutionStatus.APPLIED for item in result.action_results)
    assert all(item.status is ActionExecutionStatus.PARTIAL for item in result.verification_results)


def test_fully_unobservable_readback_is_an_observability_limit_not_a_failure():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    runtime.verification_status = ActionExecutionStatus.UNOBSERVABLE

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert result.status is ConfigurationApplicationStatus.PARTIAL
    assert result.failure_code is ConfigurationFailureCode.OBSERVABILITY_LIMITATION
    assert all(
        item.status is ActionExecutionStatus.UNOBSERVABLE
        for item in result.verification_results
    )


def test_dhcp_verification_preserves_field_level_observability():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)

    def verify(expectations):
        runtime.verify_calls.append([item.id for item in expectations])
        return [
            RuntimeVerification(
                expectation_id=item.id,
                status=(
                    ActionExecutionStatus.PARTIAL
                    if item.kind.value == "endpoint_addressing"
                    and item.expected.get("mode") == "dhcp"
                    else ActionExecutionStatus.VERIFIED
                ),
                evidence_method="structured_endpoint_getters",
                fresh_evidence=True,
                fields=(
                    {
                        "ipv4": FieldVerificationStatus.VERIFIED,
                        "netmask": FieldVerificationStatus.VERIFIED,
                        "gateway": FieldVerificationStatus.UNOBSERVABLE,
                        "dns": FieldVerificationStatus.UNOBSERVABLE,
                    }
                    if item.kind.value == "endpoint_addressing"
                    and item.expected.get("mode") == "dhcp"
                    else {field: FieldVerificationStatus.VERIFIED for field in item.expected}
                ),
            )
            for item in expectations
        ]

    runtime.verify = verify
    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )
    dhcp = next(
        item for item in result.verification_results
        if item.fields.get("gateway") is FieldVerificationStatus.UNOBSERVABLE
    )

    assert result.status is ConfigurationApplicationStatus.PARTIAL
    assert dhcp.fields["ipv4"] is FieldVerificationStatus.VERIFIED
    assert dhcp.fields["netmask"] is FieldVerificationStatus.VERIFIED
    assert dhcp.fields["gateway"] is FieldVerificationStatus.UNOBSERVABLE
    assert dhcp.fields["dns"] is FieldVerificationStatus.UNOBSERVABLE
