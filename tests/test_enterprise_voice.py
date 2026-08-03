"""E7 offline: voice plans, extensions, bindings and call expectations."""

from __future__ import annotations

from copy import deepcopy

from src.packet_tracer_mcp.application.use_cases.compile_voice import (
    compile_enterprise_voice,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigurationPlan,
    ConfigureAccessPort,
    ConfigureSubinterface,
    CreateVlan,
    SetEndpointDhcp,
)
from src.packet_tracer_mcp.domain.enterprise.models.enterprise_plan import EnterprisePlan, SitePlan
from src.packet_tracer_mcp.domain.enterprise.models.intent import SiteType
from src.packet_tracer_mcp.domain.enterprise.models.service_plan import ServicePlan
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import (
    CallExpectationResult,
    ExtensionRange,
    VoiceActionType,
    VoiceCapabilityDimension,
    VoiceCapabilityProfile,
    VoiceCapabilityStatus,
    VoiceIntent,
    VoicePolicy,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan


def _endpoint(phone_id: str, index: int, site_id: str = "hq") -> DevicePlan:
    return DevicePlan(
        id=phone_id,
        name=f"{site_id.upper()}-PHONE-{index:02d}",
        model="7960",
        category="phone",
        enterprise_role="ip_phone",
        site_id=site_id,
        floor_id="f2" if index % 2 else "f1",
        zone_id="users",
        metadata={"pair_id": f"pair-{site_id}-{index:02d}"},
    )


def _fixture(phone_count: int = 2):
    enterprise = EnterprisePlan(
        id="enterprise-e7",
        name="E7",
        sites=[SitePlan(name="HQ", site_id="hq", type=SiteType.HQ)],
    )
    phones = [_endpoint(f"phone-{index}", index) for index in range(1, phone_count + 1)]
    devices = [
        DevicePlan(
            id="r1", name="HQ-R1", model="2911", category="router",
            enterprise_role="edge_router", site_id="hq",
        ),
        DevicePlan(
            id="sw1", name="HQ-ACCESS-01", model="2960-24TT", category="switch",
            enterprise_role="access_switch", site_id="hq",
        ),
        *phones,
    ]
    links = []
    actions = [
        CreateVlan(
            id="cfg/vlan/hq/20", phase=ConfigurationPhase.L2_DEFINITIONS,
            device_id="sw1", device_name="HQ-ACCESS-01", site_id="hq",
            vlan_id=20, name="VOICE", segment_id="hq-voice",
            required_capability="vlan",
        ),
        ConfigureSubinterface(
            id="cfg/l3/r1/voice", phase=ConfigurationPhase.L3_INTERFACES,
            device_id="r1", device_name="HQ-R1", site_id="hq",
            parent_interface="GigabitEthernet0/0", vlan_id=20,
            ipv4="198.18.170.1", prefix=24, netmask="255.255.255.0",
            segment_id="hq-voice", required_capability="layer3",
        ),
    ]
    for index, phone in enumerate(phones, 1):
        actions.extend([
            ConfigureAccessPort(
                id=f"cfg/access/sw1/{index}", phase=ConfigurationPhase.L2_INTERFACES,
                device_id="sw1", device_name="HQ-ACCESS-01", site_id="hq",
                interface=f"FastEthernet0/{index}", data_vlan_id=10, voice_vlan_id=20,
                endpoint_ids=[phone.id], required_capability="voice_vlan",
            ),
            SetEndpointDhcp(
                id=f"cfg/dhcp/{phone.id}", phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
                device_id=phone.id, device_name=phone.name, site_id="hq",
                interface="Switch", segment_id="hq-voice", network="198.18.170.0",
                prefix=24, netmask="255.255.255.0", gateway="198.18.170.1",
                required_capability="endpoint_dhcp",
            ),
        ])
        links.append(LinkPlan(
            id=f"access-{phone.id}", device_a="HQ-ACCESS-01", device_a_id="sw1",
            port_a=f"FastEthernet0/{index}", device_b=phone.name,
            device_b_id=phone.id, port_b="Switch", link_role="endpoint_access",
        ))
    topology = TopologyPlan(
        id="topology-e7", semantic_hash="e4-hash", devices=devices, links=links,
    )
    configuration = ConfigurationPlan(
        id="configuration-e7", source_topology_id=topology.id,
        source_topology_hash=topology.semantic_hash, semantic_hash="e5-hash",
        actions=actions,
    )
    intent = VoiceIntent(
        id="voice-intent-e7",
        call_control_device_ids={"hq": "r1"},
        extension_ranges={"hq": ExtensionRange(start=3101, end=3199)},
    )
    capabilities = {
        "2911": VoiceCapabilityProfile(
            model="2911",
            dimensions={
                VoiceCapabilityDimension.CALL_CONTROL_CONFIG: VoiceCapabilityStatus.SUPPORTED,
                VoiceCapabilityDimension.PHONE_EXTENSION_CONFIG: VoiceCapabilityStatus.SUPPORTED,
            },
            evidence_source="PT 9.0.1 local IpcAPI reference",
        )
    }
    return enterprise, topology, configuration, intent, capabilities


def _compile(phone_count: int = 2):
    enterprise, topology, configuration, intent, capabilities = _fixture(phone_count)
    return compile_enterprise_voice(
        intent, enterprise, topology, configuration, capabilities=capabilities,
    )


def test_voice_plan_is_deterministic_10_of_10_and_input_order_independent():
    enterprise, topology, configuration, intent, capabilities = _fixture(30)
    hashes = {
        compile_enterprise_voice(
            deepcopy(intent), deepcopy(enterprise), deepcopy(topology),
            deepcopy(configuration), capabilities=deepcopy(capabilities),
        ).semantic_hash
        for _ in range(10)
    }
    reordered_topology = deepcopy(topology)
    reordered_topology.devices.reverse()
    reordered_topology.links.reverse()
    reordered_configuration = deepcopy(configuration)
    reordered_configuration.actions.reverse()
    reordered = compile_enterprise_voice(
        intent, enterprise, reordered_topology, reordered_configuration,
        capabilities=capabilities,
    )

    assert len(hashes) == 1
    assert reordered.semantic_hash == next(iter(hashes))


def test_voice_plan_binds_e4_e5_and_only_binds_e6_when_consumed():
    result = _compile()

    assert result.is_valid
    assert result.plan.source_topology_hash == "e4-hash"
    assert result.plan.source_configuration_hash == "e5-hash"
    assert result.plan.source_service_hash == ""

    enterprise, topology, configuration, intent, capabilities = _fixture()
    intent.service_dependency_ids = ["service/hq/tftp"]
    service_plan = ServicePlan(
        id="services-e6", source_topology_id=topology.id,
        source_topology_hash=topology.semantic_hash,
        source_configuration_id=configuration.id,
        source_configuration_hash=configuration.semantic_hash,
        semantic_hash="e6-hash",
    )
    consumed = compile_enterprise_voice(
        intent, enterprise, topology, configuration, service_plan=service_plan,
        capabilities=capabilities,
    )

    assert not consumed.is_valid
    assert consumed.plan is None


def test_extensions_are_stable_numeric_and_queries_are_focused():
    result = _compile(30)
    plan = result.plan

    assert result.is_valid
    assert len(plan.phone_assignments) == 30
    assert [item.extension for item in plan.phone_assignments[:3]] == ["3101", "3102", "3103"]
    assert len({item.extension for item in plan.phone_assignments}) == 30
    assert plan.assignment_for_phone("phone-1").extension == "3101"
    assert plan.assignment_for_extension("3102").phone_id == "phone-2"
    assert len(plan.actions_of_type(VoiceActionType.CREATE_EXTENSION)) == 30


def test_explicit_extensions_precede_allocator_and_collision_is_rejected():
    enterprise, topology, configuration, intent, capabilities = _fixture()
    intent.explicit_extensions = {"phone-1": "3199", "phone-2": "3199"}
    result = compile_enterprise_voice(
        intent, enterprise, topology, configuration, capabilities=capabilities,
    )

    assert not result.is_valid
    assert any(item.code.value == "EXTENSION_COLLISION" for item in result.issues)


def test_invalid_extension_and_exhausted_range_are_structured_errors():
    enterprise, topology, configuration, intent, capabilities = _fixture(2)
    intent.explicit_extensions = {"phone-1": "31x1"}
    invalid = compile_enterprise_voice(
        intent, enterprise, topology, configuration, capabilities=capabilities,
    )
    assert not invalid.is_valid
    assert any(item.code.value == "EXTENSION_INVALID" for item in invalid.issues)

    intent.explicit_extensions = {}
    intent.extension_ranges = {"hq": ExtensionRange(start=3101, end=3101)}
    exhausted = compile_enterprise_voice(
        intent, enterprise, topology, configuration, capabilities=capabilities,
    )
    assert not exhausted.is_valid
    assert any(item.code.value == "EXTENSION_RANGE_EXHAUSTED" for item in exhausted.issues)


def test_phone_binding_reuses_e4_identity_e5_voice_vlan_and_addressing():
    result = _compile()
    assignment = result.plan.assignment_for_phone("phone-1")

    assert assignment.physical_device_name == "HQ-PHONE-01"
    assert assignment.voice_vlan_id == 20
    assert assignment.voice_segment_id == "hq-voice"
    assert assignment.access_configuration_action_id == "cfg/access/sw1/1"
    assert assignment.addressing_configuration_action_id == "cfg/dhcp/phone-1"
    assert assignment.call_control_id == "call-control/hq/r1"


def test_missing_call_control_voice_vlan_or_phone_addressing_blocks_compile():
    enterprise, topology, configuration, intent, capabilities = _fixture()
    intent.call_control_device_ids = {"hq": "missing"}
    missing_host = compile_enterprise_voice(
        intent, enterprise, topology, configuration, capabilities=capabilities,
    )
    assert any(item.code.value == "CALL_CONTROL_HOST_MISSING" for item in missing_host.issues)

    intent.call_control_device_ids = {"hq": "r1"}
    configuration.actions = [
        item for item in configuration.actions
        if not isinstance(item, ConfigureAccessPort)
    ]
    missing_vlan = compile_enterprise_voice(
        intent, enterprise, topology, configuration, capabilities=capabilities,
    )
    assert any(item.code.value == "FOUNDATIONAL_VOICE_VLAN_MISSING" for item in missing_vlan.issues)

    enterprise, topology, configuration, intent, capabilities = _fixture()
    configuration.actions = [
        item for item in configuration.actions
        if not (isinstance(item, SetEndpointDhcp) and item.device_id == "phone-1")
    ]
    missing_address = compile_enterprise_voice(
        intent, enterprise, topology, configuration, capabilities=capabilities,
    )
    assert any(item.code.value == "PHONE_ADDRESSING_MISSING" for item in missing_address.issues)


def test_call_control_address_is_reused_from_e5_and_not_invented():
    result = _compile()
    call_control = result.plan.call_controls[0]

    assert call_control.host_device_id == "r1"
    assert call_control.source_address == "198.18.170.1"
    assert call_control.source_configuration_action_id == "cfg/l3/r1/voice"


def test_local_calls_both_directions_and_fresh_negative_control_are_compiled():
    result = _compile()
    expectations = result.plan.call_expectations

    assert [(item.source_phone_id, item.dialed_extension, item.expected_result) for item in expectations] == [
        ("phone-1", "3102", CallExpectationResult.ESTABLISHED),
        ("phone-1", "3200", CallExpectationResult.NOT_CONNECTED),
        ("phone-2", "3101", CallExpectationResult.ESTABLISHED),
    ]
    assert len({item.id for item in expectations}) == 3


def test_voice_actions_form_a_closed_dag_and_do_not_recompile_switch_ports():
    result = _compile()
    plan = result.plan

    assert result.is_valid
    assert {item.action_type for item in plan.actions} <= set(VoiceActionType)
    assert all("access" not in item.action_type.value for item in plan.actions)
    positions = {item.id: index for index, item in enumerate(plan.actions)}
    assert all(
        positions[dependency] < positions[item.id]
        for item in plan.actions for dependency in item.depends_on
    )


def test_compact_summary_omits_full_actions_and_extensions():
    result = _compile(30)
    summary = result.compact_summary()

    assert result.is_valid
    assert summary["phone_count"] == 30
    assert summary["extension_count"] == 30
    assert "actions" not in summary
    assert "phone_assignments" not in summary


def test_capability_unknown_is_warning_and_unsupported_call_control_is_error():
    enterprise, topology, configuration, intent, _ = _fixture()
    unknown = compile_enterprise_voice(intent, enterprise, topology, configuration)
    assert unknown.is_valid
    assert any(item.code.value == "VOICE_CAPABILITY_UNKNOWN" for item in unknown.issues)

    unsupported = compile_enterprise_voice(
        intent, enterprise, topology, configuration,
        capabilities={"2911": VoiceCapabilityProfile(
            model="2911",
            dimensions={
                VoiceCapabilityDimension.CALL_CONTROL_CONFIG:
                    VoiceCapabilityStatus.UNSUPPORTED,
            },
        )},
    )
    assert not unsupported.is_valid
    assert any(item.code.value == "VOICE_CAPABILITY_UNSUPPORTED" for item in unsupported.issues)


def test_multisite_extensions_are_namespaced_and_intersite_rules_compile_offline():
    enterprise, topology, configuration, intent, capabilities = _fixture(2)
    enterprise.sites.append(SitePlan(name="Branch", site_id="branch", type=SiteType.BRANCH))
    topology.devices.extend([
        DevicePlan(id="r2", name="BR-R1", model="2911", category="router",
                   enterprise_role="edge_router", site_id="branch"),
        DevicePlan(id="sw2", name="BR-SW1", model="2960-24TT", category="switch",
                   enterprise_role="access_switch", site_id="branch"),
        _endpoint("branch-phone-1", 1, "branch"),
    ])
    configuration.actions.extend([
        ConfigureSubinterface(
            id="cfg/l3/r2/voice", phase=ConfigurationPhase.L3_INTERFACES,
            device_id="r2", device_name="BR-R1", site_id="branch",
            parent_interface="GigabitEthernet0/0", vlan_id=120,
            ipv4="198.18.171.1", prefix=24, netmask="255.255.255.0",
            segment_id="branch-voice", required_capability="layer3",
        ),
        ConfigureAccessPort(
            id="cfg/access/sw2/1", phase=ConfigurationPhase.L2_INTERFACES,
            device_id="sw2", device_name="BR-SW1", site_id="branch",
            interface="FastEthernet0/1", data_vlan_id=110, voice_vlan_id=120,
            endpoint_ids=["branch-phone-1"], required_capability="voice_vlan",
        ),
        SetEndpointDhcp(
            id="cfg/dhcp/branch-phone-1", phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
            device_id="branch-phone-1", device_name="BRANCH-PHONE-01", site_id="branch",
            interface="Switch", segment_id="branch-voice", network="198.18.171.0",
            prefix=24, netmask="255.255.255.0", gateway="198.18.171.1",
            required_capability="endpoint_dhcp",
        ),
    ])
    intent.call_control_device_ids["branch"] = "r2"
    intent.extension_ranges["branch"] = ExtensionRange(start=4101, end=4199)
    intent.intersite_calling = True
    result = compile_enterprise_voice(
        intent, enterprise, topology, configuration, capabilities=capabilities,
    )

    assert result.is_valid
    assert {item.extension for item in result.plan.phone_assignments} == {"3101", "3102", "4101"}
    assert len([item for item in result.plan.dial_rules if not item.local]) == 2


def test_service_hash_is_bound_when_real_dependency_exists():
    enterprise, topology, configuration, intent, capabilities = _fixture()
    intent.service_dependency_ids = ["service/hq/tftp"]
    service_plan = ServicePlan(
        id="services-e6", source_topology_id=topology.id,
        source_topology_hash=topology.semantic_hash,
        source_configuration_id=configuration.id,
        source_configuration_hash=configuration.semantic_hash,
        semantic_hash="e6-hash",
        services=[],
    )
    missing = compile_enterprise_voice(
        intent, enterprise, topology, configuration, service_plan=service_plan,
        capabilities=capabilities,
    )
    assert not missing.is_valid

    # The compiler accepts only an actually declared service dependency.
    from src.packet_tracer_mcp.domain.enterprise.models.service_plan import (
        ServiceDefinition,
        ServiceType,
    )
    service_plan.services = [ServiceDefinition(
        id="service/hq/tftp", name="voice-bootstrap", service_type=ServiceType.TFTP,
        site_id="hq", host_device_id="srv1", host_device_name="HQ-TFTP",
        host_model="Server-PT", address="198.18.170.10", segment_id="hq-voice",
        protocol="udp", ports=[69],
    )]
    bound = compile_enterprise_voice(
        intent, enterprise, topology, configuration, service_plan=service_plan,
        capabilities=capabilities,
    )

    assert bound.is_valid
    assert bound.plan.source_service_hash == "e6-hash"
    assert bound.plan.service_dependency_ids == ["service/hq/tftp"]
