"""E8 offline: semantic policies compile into deterministic enforcement."""

from __future__ import annotations

from copy import deepcopy

from src.packet_tracer_mcp.application.use_cases.compile_security import (
    compile_enterprise_security,
)
from src.packet_tracer_mcp.domain.enterprise.services.security_compiler import (
    SecurityCompiler,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigurationPlan,
    ConfigureAccessPort,
    ConfigureDhcpPool,
    ConfigureSubinterface,
    CreateVlan,
    SetEndpointStaticAddress,
)
from src.packet_tracer_mcp.domain.enterprise.models.security_plan import (
    AddSecurityAclRule,
    AttachSecurityAcl,
    ConfigureDhcpSnooping,
    ConfigureEndpointPortSecurity,
    ConfigureSecurityNat,
    DeviceHardeningIntent,
    DhcpInspectionPolicyIntent,
    DynamicNatPoolIntent,
    NatMode,
    NatPolicyIntent,
    PortSecurityPolicyIntent,
    SecurityCapabilityDimension,
    SecurityCapabilityProfile,
    SecurityCapabilityStatus,
    SecurityDecision,
    SecurityIntent,
    SecurityPolicyIntent,
    SecurityProbeKind,
    SecurityVerificationKind,
    StaticNatMappingIntent,
)
from src.packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceDefinition,
    ServicePlan,
    ServiceType,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan


def _fixture():
    devices = [
        DevicePlan(id="r1", name="HQ-R1", model="2911", category="router",
                   enterprise_role="edge_router", site_id="hq"),
        DevicePlan(id="sw1", name="HQ-SW1", model="2960-24TT", category="switch",
                   enterprise_role="access_switch", site_id="hq"),
        DevicePlan(id="sales-pc", name="SALES-PC", model="PC-PT", category="pc",
                   enterprise_role="pc", site_id="hq"),
        DevicePlan(id="guest-pc", name="GUEST-PC", model="PC-PT", category="pc",
                   enterprise_role="pc", site_id="hq"),
        DevicePlan(id="web", name="WEB-SRV", model="Server-PT", category="server",
                   enterprise_role="server", site_id="hq"),
        DevicePlan(id="internet", name="INTERNET-SRV", model="Server-PT", category="server",
                   enterprise_role="server", site_id="wan"),
    ]
    links = [
        LinkPlan(id="uplink", device_a="HQ-R1", device_a_id="r1",
                 port_a="GigabitEthernet0/0", device_b="HQ-SW1", device_b_id="sw1",
                 port_b="GigabitEthernet0/1", link_role="uplink"),
        LinkPlan(id="sales-link", device_a="HQ-SW1", device_a_id="sw1",
                 port_a="FastEthernet0/1", device_b="SALES-PC", device_b_id="sales-pc",
                 port_b="FastEthernet0", link_role="endpoint_access"),
        LinkPlan(id="guest-link", device_a="HQ-SW1", device_a_id="sw1",
                 port_a="FastEthernet0/2", device_b="GUEST-PC", device_b_id="guest-pc",
                 port_b="FastEthernet0", link_role="endpoint_access"),
        LinkPlan(id="web-link", device_a="HQ-SW1", device_a_id="sw1",
                 port_a="FastEthernet0/3", device_b="WEB-SRV", device_b_id="web",
                 port_b="FastEthernet0", link_role="endpoint_access"),
        LinkPlan(id="wan-link", device_a="HQ-R1", device_a_id="r1",
                 port_a="GigabitEthernet0/1", device_b="INTERNET-SRV",
                 device_b_id="internet", port_b="FastEthernet0", link_role="wan"),
    ]
    topology = TopologyPlan(
        id="e4-security", semantic_hash="e4-security-hash",
        devices=devices, links=links,
    )
    actions = [
        CreateVlan(id="cfg/vlan/sales", phase=ConfigurationPhase.L2_DEFINITIONS,
                   device_id="sw1", device_name="HQ-SW1", site_id="hq", vlan_id=10,
                   name="SALES", segment_id="sales"),
        CreateVlan(id="cfg/vlan/guest", phase=ConfigurationPhase.L2_DEFINITIONS,
                   device_id="sw1", device_name="HQ-SW1", site_id="hq", vlan_id=20,
                   name="GUEST", segment_id="guest"),
        CreateVlan(id="cfg/vlan/servers", phase=ConfigurationPhase.L2_DEFINITIONS,
                   device_id="sw1", device_name="HQ-SW1", site_id="hq", vlan_id=50,
                   name="SERVERS", segment_id="servers"),
        ConfigureSubinterface(id="cfg/l3/sales", phase=ConfigurationPhase.L3_INTERFACES,
                   device_id="r1", device_name="HQ-R1", site_id="hq",
                   parent_interface="GigabitEthernet0/0", vlan_id=10,
                   ipv4="10.0.10.1", prefix=24, netmask="255.255.255.0",
                   segment_id="sales"),
        ConfigureSubinterface(id="cfg/l3/guest", phase=ConfigurationPhase.L3_INTERFACES,
                   device_id="r1", device_name="HQ-R1", site_id="hq",
                   parent_interface="GigabitEthernet0/0", vlan_id=20,
                   ipv4="10.0.20.1", prefix=24, netmask="255.255.255.0",
                   segment_id="guest"),
        ConfigureSubinterface(id="cfg/l3/servers", phase=ConfigurationPhase.L3_INTERFACES,
                   device_id="r1", device_name="HQ-R1", site_id="hq",
                   parent_interface="GigabitEthernet0/0", vlan_id=50,
                   ipv4="10.0.50.1", prefix=24, netmask="255.255.255.0",
                   segment_id="servers"),
        ConfigureSubinterface(id="cfg/l3/wan", phase=ConfigurationPhase.L3_INTERFACES,
                   device_id="r1", device_name="HQ-R1", site_id="wan",
                   parent_interface="GigabitEthernet0/1", vlan_id=900,
                   ipv4="198.51.100.1", prefix=24, netmask="255.255.255.0",
                   segment_id="wan"),
        ConfigureAccessPort(id="cfg/access/sales", phase=ConfigurationPhase.L2_INTERFACES,
                   device_id="sw1", device_name="HQ-SW1", site_id="hq",
                   interface="FastEthernet0/1", data_vlan_id=10,
                   endpoint_ids=["sales-pc"]),
        ConfigureAccessPort(id="cfg/access/guest", phase=ConfigurationPhase.L2_INTERFACES,
                   device_id="sw1", device_name="HQ-SW1", site_id="hq",
                   interface="FastEthernet0/2", data_vlan_id=20,
                   endpoint_ids=["guest-pc"]),
        ConfigureAccessPort(id="cfg/access/web", phase=ConfigurationPhase.L2_INTERFACES,
                   device_id="sw1", device_name="HQ-SW1", site_id="hq",
                   interface="FastEthernet0/3", data_vlan_id=50,
                   endpoint_ids=["web"]),
        SetEndpointStaticAddress(id="cfg/ip/sales", phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
                   device_id="sales-pc", device_name="SALES-PC", site_id="hq",
                   interface="FastEthernet0", ipv4="10.0.10.10",
                   netmask="255.255.255.0", gateway="10.0.10.1", segment_id="sales"),
        SetEndpointStaticAddress(id="cfg/ip/guest", phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
                   device_id="guest-pc", device_name="GUEST-PC", site_id="hq",
                   interface="FastEthernet0", ipv4="10.0.20.10",
                   netmask="255.255.255.0", gateway="10.0.20.1", segment_id="guest"),
        SetEndpointStaticAddress(id="cfg/ip/web", phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
                   device_id="web", device_name="WEB-SRV", site_id="hq",
                   interface="FastEthernet0", ipv4="10.0.50.10",
                   netmask="255.255.255.0", gateway="10.0.50.1", segment_id="servers"),
        SetEndpointStaticAddress(id="cfg/ip/internet", phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
                   device_id="internet", device_name="INTERNET-SRV", site_id="wan",
                   interface="FastEthernet0", ipv4="198.51.100.10",
                   netmask="255.255.255.0", gateway="198.51.100.1", segment_id="wan"),
        ConfigureDhcpPool(id="cfg/dhcp/sales", phase=ConfigurationPhase.SERVICES,
                   device_id="r1", device_name="HQ-R1", site_id="hq",
                   pool_name="SALES", segment_id="sales", network="10.0.10.0",
                   prefix=24, netmask="255.255.255.0", gateway="10.0.10.1",
                   lease_start="10.0.10.20", lease_end="10.0.10.200"),
    ]
    configuration = ConfigurationPlan(
        id="e5-security", source_topology_id=topology.id,
        source_topology_hash=topology.semantic_hash,
        semantic_hash="e5-security-hash", actions=actions,
    )
    service = ServiceDefinition(
        id="service/http", name="intranet", service_type=ServiceType.HTTP,
        site_id="hq", host_device_id="web", host_device_name="WEB-SRV",
        host_model="Server-PT", address="10.0.50.10", segment_id="servers",
        client_device_ids=["sales-pc", "guest-pc"], protocol="tcp", ports=[80],
    )
    services = ServicePlan(
        id="e6-security", source_topology_id=topology.id,
        source_topology_hash=topology.semantic_hash,
        source_configuration_id=configuration.id,
        source_configuration_hash=configuration.semantic_hash,
        semantic_hash="e6-security-hash", services=[service],
    )
    intent = SecurityIntent(
        id="security-intent",
        policies=[
            SecurityPolicyIntent(id="allow-sales-http", source_segment_id="sales",
                                 destination_service_id="service/http",
                                 decision=SecurityDecision.ALLOW, priority=10),
            SecurityPolicyIntent(id="deny-guest-http", source_segment_id="guest",
                                 destination_service_id="service/http",
                                 decision=SecurityDecision.DENY, priority=10),
        ],
        nat_policies=[NatPolicyIntent(
            id="pat-hq", router_device_id="r1", mode=NatMode.PAT,
            inside_segment_ids=["sales", "guest", "servers"],
            outside_segment_id="wan", probe_destination_device_id="internet",
        )],
        port_security=[PortSecurityPolicyIntent(
            id="secure-sales", endpoint_ids=["sales-pc"], max_macs=1,
        )],
        dhcp_inspection=[DhcpInspectionPolicyIntent(
            id="inspect-hq", site_id="hq", segment_ids=["sales"],
            enable_snooping=True, enable_dai=True,
        )],
        hardening=[DeviceHardeningIntent(
            id="harden-network", device_ids=["r1", "sw1"],
            banner_motd="Authorized access only",
        )],
    )
    capabilities = {
        "2911": SecurityCapabilityProfile.supported("2911"),
        "2960-24TT": SecurityCapabilityProfile.supported("2960-24TT"),
    }
    return topology, configuration, services, intent, capabilities


def _compile():
    topology, configuration, services, intent, capabilities = _fixture()
    return compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )


def test_security_plan_is_deterministic_10_of_10_and_input_order_independent():
    topology, configuration, services, intent, capabilities = _fixture()
    hashes = {
        compile_enterprise_security(
            deepcopy(intent), deepcopy(topology), deepcopy(configuration),
            service_plan=deepcopy(services), capabilities=deepcopy(capabilities),
        ).semantic_hash
        for _ in range(10)
    }
    topology.devices.reverse()
    topology.links.reverse()
    configuration.actions.reverse()
    intent.policies.reverse()
    reordered = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )

    assert len(hashes) == 1
    assert reordered.semantic_hash == next(iter(hashes))


def test_acl_placement_is_near_source_and_direction_reverses_with_policy():
    result = _compile()
    attachments = [item for item in result.plan.actions if isinstance(item, AttachSecurityAcl)]

    assert {(item.interface, item.direction) for item in attachments} == {
        ("GigabitEthernet0/0.10", "in"),
        ("GigabitEthernet0/0.20", "in"),
    }

    topology, configuration, services, intent, capabilities = _fixture()
    intent.policies = [SecurityPolicyIntent(
        id="reverse", source_segment_id="servers", destination_segment_id="sales",
        protocol="icmp", decision=SecurityDecision.DENY,
    )]
    reversed_result = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )
    attachment = next(
        item for item in reversed_result.plan.actions if isinstance(item, AttachSecurityAcl)
    )
    assert attachment.interface == "GigabitEthernet0/0.50"
    assert attachment.direction == "in"


def test_redundant_source_l3_boundaries_are_all_enforced():
    topology, configuration, services, intent, capabilities = _fixture()
    topology.devices.append(DevicePlan(
        id="r2", name="HQ-R2", model="2911", category="router",
        enterprise_role="edge_router", site_id="hq",
    ))
    configuration.actions.append(ConfigureSubinterface(
        id="cfg/l3/sales-r2", phase=ConfigurationPhase.L3_INTERFACES,
        device_id="r2", device_name="HQ-R2", site_id="hq",
        parent_interface="GigabitEthernet0/0", vlan_id=10,
        ipv4="10.0.10.2", prefix=24, netmask="255.255.255.0",
        segment_id="sales",
    ))
    intent.policies = [SecurityPolicyIntent(
        id="redundant-sales", source_segment_id="sales",
        destination_service_id="service/http", decision=SecurityDecision.DENY,
    )]

    result = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )
    attachments = [
        item for item in result.plan.actions if isinstance(item, AttachSecurityAcl)
    ]

    assert {(item.device_name, item.interface) for item in attachments} == {
        ("HQ-R1", "GigabitEthernet0/0.10"),
        ("HQ-R2", "GigabitEthernet0/0.10"),
    }


def test_service_policy_reuses_e6_address_protocol_and_port():
    result = _compile()
    rule = next(
        item for item in result.plan.actions
        if isinstance(item, AddSecurityAclRule) and item.policy_id == "allow-sales-http"
    )

    assert rule.source_cidr == "10.0.10.0/24"
    assert rule.destination_cidr == "10.0.50.10/32"
    assert rule.protocol == "tcp"
    assert rule.destination_ports == [80]
    assert result.plan.source_service_hash == "e6-security-hash"


def test_service_and_transport_policies_never_substitute_icmp_for_missing_behavior():
    topology, configuration, services, intent, capabilities = _fixture()
    services.services[0].service_type = ServiceType.NTP
    services.services[0].protocol = "udp"
    services.services[0].ports = [123]
    intent.policies = [SecurityPolicyIntent(
        id="allow-ntp", source_segment_id="sales",
        destination_service_id="service/http", decision=SecurityDecision.ALLOW,
    )]
    ntp = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )
    ntp_probe = next(
        item for item in ntp.plan.verification_expectations
        if item.kind is SecurityVerificationKind.TRAFFIC_POLICY
    )

    intent.policies = [SecurityPolicyIntent(
        id="raw-tcp", source_segment_id="sales",
        destination_segment_id="servers", protocol="tcp",
        destination_ports=[22], decision=SecurityDecision.ALLOW,
    )]
    raw_tcp = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )
    tcp_probe = next(
        item for item in raw_tcp.plan.verification_expectations
        if item.kind is SecurityVerificationKind.TRAFFIC_POLICY
    )

    assert ntp_probe.probe_kind is SecurityProbeKind.NTP_SYNC
    assert tcp_probe.probe_kind is SecurityProbeKind.UNOBSERVABLE


def test_deny_policy_compiles_positive_baseline_negative_and_cleanup_expectations():
    result = _compile()
    expectation = next(
        item for item in result.plan.verification_expectations
        if item.policy_id == "deny-guest-http"
        and item.kind is SecurityVerificationKind.TRAFFIC_POLICY
    )

    assert expectation.expected_decision is SecurityDecision.DENY
    assert expectation.baseline_required
    assert expectation.cleanup_recovery_required
    assert expectation.source_device_id == "guest-pc"
    assert expectation.destination_device_id == "web"


def test_conflicting_exact_policy_is_a_compile_error():
    topology, configuration, services, intent, capabilities = _fixture()
    intent.policies.append(SecurityPolicyIntent(
        id="contradiction", source_segment_id="guest",
        destination_service_id="service/http", decision=SecurityDecision.ALLOW,
        priority=10,
    ))
    result = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )

    assert not result.is_valid
    assert any(item.code.value == "SECURITY_POLICY_CONFLICT" for item in result.issues)


def test_exact_conflict_is_not_hidden_by_a_different_priority():
    topology, configuration, services, intent, capabilities = _fixture()
    intent.policies.append(SecurityPolicyIntent(
        id="later-contradiction", source_segment_id="guest",
        destination_service_id="service/http", decision=SecurityDecision.ALLOW,
        priority=900,
    ))

    result = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )

    assert not result.is_valid
    assert any(item.code.value == "SECURITY_POLICY_CONFLICT" for item in result.issues)


def test_missing_service_or_stale_hash_stops_compile():
    topology, configuration, services, intent, capabilities = _fixture()
    missing = compile_enterprise_security(
        intent, topology, configuration, capabilities=capabilities,
    )
    assert not missing.is_valid
    assert any(item.code.value == "SECURITY_SERVICE_MISSING" for item in missing.issues)

    services.source_configuration_hash = "stale"
    stale = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )
    assert not stale.is_valid
    assert any(item.code.value == "SECURITY_SOURCE_MISMATCH" for item in stale.issues)


def test_nat_port_security_and_inspection_reuse_e4_e5_identities():
    result = _compile()
    nat = next(item for item in result.plan.actions if isinstance(item, ConfigureSecurityNat))
    port = next(
        item for item in result.plan.actions
        if isinstance(item, ConfigureEndpointPortSecurity)
    )
    snooping = next(
        item for item in result.plan.actions if isinstance(item, ConfigureDhcpSnooping)
    )

    assert nat.inside_interfaces == [
        "GigabitEthernet0/0.10", "GigabitEthernet0/0.20",
        "GigabitEthernet0/0.50",
    ]
    assert nat.outside_interface == "GigabitEthernet0/1.900"
    assert nat.inside_networks == ["10.0.10.0/24", "10.0.20.0/24", "10.0.50.0/24"]
    assert 1 <= nat.translation_acl_number <= 99
    assert (port.switch_device_id, port.interface) == ("sw1", "FastEthernet0/1")
    assert snooping.vlan_ids == [10]
    assert snooping.trusted_interfaces == ["GigabitEthernet0/1"]


def test_unknown_capability_warns_and_unsupported_required_feature_blocks():
    topology, configuration, services, intent, capabilities = _fixture()
    capabilities["2960-24TT"].dimensions[
        SecurityCapabilityDimension.DHCP_SNOOPING_CONFIG
    ] = SecurityCapabilityStatus.UNKNOWN
    unknown = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )
    assert unknown.is_valid
    assert any(item.code.value == "SECURITY_CAPABILITY_UNKNOWN" for item in unknown.issues)

    capabilities["2911"].dimensions[
        SecurityCapabilityDimension.ACL_CONFIG
    ] = SecurityCapabilityStatus.UNSUPPORTED
    unsupported = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )
    assert not unsupported.is_valid
    assert any(item.code.value == "SECURITY_CAPABILITY_UNSUPPORTED" for item in unsupported.issues)


def test_partial_readback_warns_without_blocking_configuration_compile():
    topology, configuration, services, intent, capabilities = _fixture()
    capabilities["2960-24TT"].dimensions[
        SecurityCapabilityDimension.DAI_READBACK
    ] = SecurityCapabilityStatus.PARTIAL

    result = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )

    assert result.is_valid
    assert any(
        item.code.value == "SECURITY_CAPABILITY_PARTIAL"
        and item.details.get("capability") == "dai_readback"
        for item in result.issues
    )


def test_actions_form_closed_dag_and_summary_stays_compact():
    result = _compile()
    positions = {item.id: index for index, item in enumerate(result.plan.actions)}

    assert result.is_valid
    assert all(
        positions[dependency] < positions[item.id]
        for item in result.plan.actions for dependency in item.depends_on
    )
    summary = result.compact_summary()
    assert "actions" not in summary
    assert "verification_expectations" not in summary
    assert summary["policy_count"] == 2


def test_domain_security_compiler_never_contains_phone_ui_or_raw_ios_actions():
    result = _compile()
    serialized = result.plan.model_dump_json()

    assert "screen coordinate" not in serialized
    assert "phone click" not in serialized
    assert "access-list " not in serialized
    assert "ip nat inside" not in serialized


def test_unsafe_protocol_ports_and_banner_are_rejected_before_backend_rendering():
    topology, configuration, services, intent, capabilities = _fixture()
    intent.policies[0].protocol = "tcp\nend"
    intent.policies[0].destination_service_id = ""
    intent.policies[0].destination_segment_id = "servers"
    intent.policies[0].destination_ports = [70000]
    intent.hardening[0].banner_motd = "safe#\nend"

    result = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )

    assert not result.is_valid
    assert sum(
        item.code.value == "SECURITY_INTENT_INVALID" for item in result.issues
    ) >= 3


def test_non_transport_policy_cannot_carry_port_constraints():
    topology, configuration, services, intent, capabilities = _fixture()
    intent.policies = [SecurityPolicyIntent(
        id="bad-icmp-port", source_segment_id="sales",
        destination_segment_id="servers", protocol="icmp",
        destination_ports=[80], decision=SecurityDecision.DENY,
    )]

    result = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )

    assert not result.is_valid
    assert any(
        item.code.value == "SECURITY_INTENT_INVALID" for item in result.issues
    )


def test_static_or_dynamic_nat_requires_explicit_mapping_semantics():
    topology, configuration, services, intent, capabilities = _fixture()
    intent.nat_policies[0].mode = NatMode.STATIC

    result = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )

    assert not result.is_valid
    assert any(item.code.value == "SECURITY_NAT_INVALID" for item in result.issues)

    intent.nat_policies[0].mode = NatMode.DYNAMIC
    dynamic = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )
    assert not dynamic.is_valid
    assert any(item.code.value == "SECURITY_NAT_INVALID" for item in dynamic.issues)


def test_static_and_dynamic_nat_compile_from_typed_mapping_and_pool_semantics():
    topology, configuration, services, intent, capabilities = _fixture()
    intent.nat_policies = [
        NatPolicyIntent(
            id="static-web", router_device_id="r1", mode=NatMode.STATIC,
            inside_segment_ids=["servers"], outside_segment_id="wan",
            probe_destination_device_id="internet",
            static_mappings=[StaticNatMappingIntent(
                inside_endpoint_id="web",
                outside_global_address="198.51.100.20",
            )],
        ),
        NatPolicyIntent(
            id="dynamic-sales", router_device_id="r1", mode=NatMode.DYNAMIC,
            inside_segment_ids=["sales"], outside_segment_id="wan",
            probe_destination_device_id="internet",
            dynamic_pool=DynamicNatPoolIntent(
                start_address="198.51.100.21",
                end_address="198.51.100.30",
                prefix=24,
            ),
        ),
    ]

    result = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )
    actions = [
        item for item in result.plan.actions
        if isinstance(item, ConfigureSecurityNat)
    ]
    static = next(item for item in actions if item.mode is NatMode.STATIC)
    dynamic = next(item for item in actions if item.mode is NatMode.DYNAMIC)

    assert result.is_valid
    assert static.translation_acl_number == 0
    assert static.static_mappings[0].inside_local_address == "10.0.50.10"
    assert static.static_mappings[0].outside_global_address == "198.51.100.20"
    assert dynamic.dynamic_pool is not None
    assert dynamic.dynamic_pool.netmask == "255.255.255.0"
    assert 1 <= dynamic.translation_acl_number <= 99


def test_nat_standard_acl_collisions_are_resolved_deterministically():
    topology, configuration, services, intent, capabilities = _fixture()
    intent.nat_policies = [
        NatPolicyIntent(
            id=policy_id, router_device_id="r1", mode=NatMode.PAT,
            inside_segment_ids=["sales"], outside_segment_id="wan",
            probe_destination_device_id="internet",
        )
        for policy_id in ("nat-0", "nat-7")  # same initial SHA-derived slot
    ]

    result = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )
    numbers = [
        item.translation_acl_number for item in result.plan.actions
        if isinstance(item, ConfigureSecurityNat)
    ]

    assert len(numbers) == 2
    assert len(set(numbers)) == 2
    assert all(1 <= item <= 99 for item in numbers)


def test_implicit_deny_is_explicit_plan_semantics_not_a_synthetic_ace():
    topology, configuration, services, intent, capabilities = _fixture()
    intent.default_decision = SecurityDecision.DENY

    result = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    )
    defaults = [
        item for item in result.plan.actions
        if isinstance(item, AddSecurityAclRule) and item.default_rule
    ]

    assert result.plan.default_decision is SecurityDecision.DENY
    assert defaults == []


def test_extended_acl_allocator_never_leaves_valid_ios_numbered_ranges():
    assert SecurityCompiler._extended_acl_number(0) == 100
    assert SecurityCompiler._extended_acl_number(99) == 199
    assert SecurityCompiler._extended_acl_number(100) == 2000
    assert SecurityCompiler._extended_acl_number(799) == 2699
    assert SecurityCompiler._extended_acl_number(800) is None
