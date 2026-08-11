from __future__ import annotations

from copy import deepcopy

from src.packet_tracer_mcp.application.use_cases.compile_control_plane import (
    compile_enterprise_control_plane,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigureAccessPort,
    ConfigureRoutedInterface,
    ConfigureTrunk,
    ConfigurationIssueCode,
    ConfigurationPhase,
    ConfigurationPlan,
    CreateVlan,
    SetEndpointStaticAddress,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureEigrpIpv4,
    ConfigureEtherChannel,
    ConfigureHsrp,
    ConfigureOspfv2,
    ConfigureSpanningTree,
    ConfigureStpEdgePort,
    ControlPlaneCapabilityDimension,
    ControlPlaneCapabilityProfile,
    ControlPlaneIntent,
    ControlPlaneVerificationKind,
    DynamicRoutingIntent,
    DynamicRoutingProtocol,
    EtherChannelIntent,
    EtherChannelProtocol,
    FirstHopRedundancyIntent,
    LinkFailureScenarioIntent,
    StpIntent,
    StpMode,
)
from src.packet_tracer_mcp.domain.enterprise.models.security_plan import (
    ApplyDeviceHardening,
    SecurityCapabilityDimension,
    SecurityCapabilityStatus,
    SecurityPhase,
    SecurityPlan,
)
from src.packet_tracer_mcp.domain.enterprise.models.failure_domain import (
    FailureDomain,
    FailureDomainProvenance,
    FailureDomainType,
    IndependenceStatus,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan


def _device(
    device_id: str,
    name: str,
    category: str,
    site_id: str,
    layer: str = "",
    model: str | None = None,
) -> DevicePlan:
    return DevicePlan(
        id=device_id,
        name=name,
        model=model or ("2960-24TT" if category == "switch" else "2911"),
        category=category,
        site_id=site_id,
        network_layer=layer,
    )


def _link(
    link_id: str,
    a: DevicePlan,
    port_a: str,
    b: DevicePlan,
    port_b: str,
    *,
    role: str,
    redundancy: str = "",
) -> LinkPlan:
    return LinkPlan(
        id=link_id,
        device_a=a.name,
        device_a_id=a.id,
        port_a=port_a,
        device_b=b.name,
        device_b_id=b.id,
        port_b=port_b,
        cable="cross",
        link_role=role,
        redundancy_group=redundancy,
    )


def _fixture():
    sw1 = _device("sw1", "HQ-SW1", "switch", "hq", "distribution")
    sw2 = _device("sw2", "HQ-SW2", "switch", "hq", "distribution")
    r1 = _device("r1", "HQ-R1", "router", "hq", "edge")
    r2 = _device("r2", "HQ-R2", "router", "hq", "edge")
    b1 = _device("b1", "BR-R1", "router", "branch", "edge")
    b2 = _device("b2", "BR-R2", "router", "branch", "edge")
    pc1 = _device("pc1", "HQ-PC1", "pc", "hq", model="PC-PT")
    pc2 = _device("pc2", "HQ-PC2", "pc", "hq", model="PC-PT")
    links = [
        _link(
            "sw-member-a", sw1, "GigabitEthernet0/1",
            sw2, "GigabitEthernet0/1", role="distribution_uplink",
            redundancy="sw-bundle",
        ),
        _link(
            "sw-member-b", sw1, "GigabitEthernet0/2",
            sw2, "GigabitEthernet0/2", role="distribution_uplink",
            redundancy="sw-bundle",
        ),
        _link(
            "hq-transit", r1, "GigabitEthernet0/0",
            r2, "GigabitEthernet0/0", role="core_link",
            redundancy="hq-routing",
        ),
        _link(
            "branch-transit", b1, "GigabitEthernet0/0",
            b2, "GigabitEthernet0/0", role="core_link",
            redundancy="branch-routing",
        ),
    ]
    topology = TopologyPlan(
        id="e4-control-plane",
        semantic_hash="e4-control-plane-hash",
        devices=[sw1, sw2, r1, r2, b1, b2, pc1, pc2],
        links=links,
    )

    actions = []
    for switch in (sw1, sw2):
        actions.extend([
            CreateVlan(
                id=f"cfg/vlan/{switch.id}/10",
                phase=ConfigurationPhase.L2_DEFINITIONS,
                device_id=switch.id,
                device_name=switch.name,
                site_id="hq",
                vlan_id=10,
                segment_id="hq-data",
            ),
            CreateVlan(
                id=f"cfg/vlan/{switch.id}/20",
                phase=ConfigurationPhase.L2_DEFINITIONS,
                device_id=switch.id,
                device_name=switch.name,
                site_id="hq",
                vlan_id=20,
                segment_id="hq-voice",
            ),
        ])
    for link in links[:2]:
        for device, interface in (
            (sw1, link.port_a), (sw2, link.port_b),
        ):
            actions.append(ConfigureTrunk(
                id=f"cfg/trunk/{device.id}/{link.id}",
                phase=ConfigurationPhase.L2_INTERFACES,
                device_id=device.id,
                device_name=device.name,
                site_id="hq",
                interface=interface,
                allowed_vlans=[10, 20],
                source_link_id=link.id,
                peer_device_id=sw2.id if device.id == sw1.id else sw1.id,
            ))
    actions.append(ConfigureAccessPort(
        id="cfg/access/sw1/fa01",
        phase=ConfigurationPhase.L2_INTERFACES,
        device_id="sw1",
        device_name=sw1.name,
        site_id="hq",
        interface="FastEthernet0/1",
        data_vlan_id=10,
        endpoint_ids=["pc1"],
    ))

    l3_values = [
        (r1, "GigabitEthernet0/0", "10.255.0.1", 30, "hq-transit"),
        (r2, "GigabitEthernet0/0", "10.255.0.2", 30, "hq-transit"),
        (r1, "GigabitEthernet0/1", "10.0.10.2", 24, "hq-data"),
        (r2, "GigabitEthernet0/1", "10.0.10.3", 24, "hq-data"),
        (r1, "GigabitEthernet0/2", "10.0.101.1", 24, "hq-r1-lan"),
        (r2, "GigabitEthernet0/2", "10.0.102.1", 24, "hq-r2-lan"),
        (b1, "GigabitEthernet0/0", "10.255.1.1", 30, "branch-transit"),
        (b2, "GigabitEthernet0/0", "10.255.1.2", 30, "branch-transit"),
        (b1, "GigabitEthernet0/1", "10.1.10.2", 24, "branch-data"),
        (b2, "GigabitEthernet0/1", "10.1.10.3", 24, "branch-data"),
    ]
    for device, interface, address, prefix, segment in l3_values:
        actions.append(ConfigureRoutedInterface(
            id=f"cfg/l3/{device.id}/{segment}",
            phase=ConfigurationPhase.L3_INTERFACES,
            device_id=device.id,
            device_name=device.name,
            site_id=device.site_id,
            interface=interface,
            ipv4=address,
            prefix=prefix,
            netmask="255.255.255.252" if prefix == 30 else "255.255.255.0",
            segment_id=segment,
            required_capability="layer3",
        ))
    actions.append(SetEndpointStaticAddress(
        id="cfg/endpoint/pc1",
        phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
        device_id="pc1",
        device_name=pc1.name,
        site_id="hq",
        interface="FastEthernet0",
        ipv4="10.0.10.10",
        netmask="255.255.255.0",
        gateway="10.0.10.1",
        segment_id="hq-data",
    ))
    actions.append(SetEndpointStaticAddress(
        id="cfg/endpoint/pc2",
        phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
        device_id="pc2",
        device_name=pc2.name,
        site_id="hq",
        interface="FastEthernet0",
        ipv4="10.0.102.10",
        netmask="255.255.255.0",
        gateway="10.0.102.1",
        segment_id="hq-r2-lan",
    ))
    configuration = ConfigurationPlan(
        id="e5-control-plane",
        source_topology_id=topology.id,
        source_topology_hash=topology.semantic_hash,
        semantic_hash="e5-control-plane-hash",
        actions=actions,
    )

    intent = ControlPlaneIntent(
        id="e9-reference",
        stp_domains=[StpIntent(
            id="stp/hq",
            site_id="hq",
            mode=StpMode.RAPID_PVST,
            vlan_ids=[10, 20],
            root_primary_by_vlan={10: "sw1", 20: "sw2"},
            root_secondary_by_vlan={10: "sw2", 20: "sw1"},
        )],
        etherchannels=[EtherChannelIntent(
            id="ec/hq",
            member_link_ids=["sw-member-a", "sw-member-b"],
            protocol=EtherChannelProtocol.LACP,
        )],
        first_hop_redundancy=[FirstHopRedundancyIntent(
            id="hsrp/hq-data",
            segment_id="hq-data",
            device_ids=["r1", "r2"],
        )],
        routing_domains=[
            DynamicRoutingIntent(
                id="routing/hq",
                site_id="hq",
                protocol=DynamicRoutingProtocol.OSPFV2,
                device_ids=["r1", "r2"],
                transit_link_ids=["hq-transit"],
                area_by_segment={"hq-data": 10},
            ),
            DynamicRoutingIntent(
                id="routing/branch",
                site_id="branch",
                protocol=DynamicRoutingProtocol.EIGRP,
                device_ids=["b1", "b2"],
                transit_link_ids=["branch-transit"],
                eigrp_as_number=200,
            ),
        ],
        failure_scenarios=[LinkFailureScenarioIntent(
            id="failure/sw-member-a",
            link_id="sw-member-a",
            probe_source_device_id="pc1",
            probe_destination_device_id="pc2",
            expected_surviving_link_ids=["sw-member-b"],
        )],
    )
    capabilities = {
        "2960-24TT": ControlPlaneCapabilityProfile.supported("2960-24TT"),
        "2911": ControlPlaneCapabilityProfile.supported("2911"),
    }
    return intent, topology, configuration, capabilities


def _compile():
    intent, topology, configuration, capabilities = _fixture()
    return compile_enterprise_control_plane(
        intent, topology, configuration, capabilities=capabilities,
    )


def test_reference_compiles_closed_plan_and_binds_only_consumed_hashes():
    result = _compile()

    assert result.is_valid, result.issues
    assert result.plan.source_topology_hash == "e4-control-plane-hash"
    assert result.plan.source_configuration_hash == "e5-control-plane-hash"
    assert result.plan.source_security_hash == ""
    assert len(result.semantic_hash) == 64
    assert any(isinstance(item, ConfigureSpanningTree) for item in result.plan.actions)
    assert any(isinstance(item, ConfigureStpEdgePort) for item in result.plan.actions)
    assert any(isinstance(item, ConfigureEtherChannel) for item in result.plan.actions)
    assert any(isinstance(item, ConfigureHsrp) for item in result.plan.actions)
    assert len([item for item in result.plan.actions if isinstance(item, ConfigureOspfv2)]) == 2
    assert len([item for item in result.plan.actions if isinstance(item, ConfigureEigrpIpv4)]) == 2
    serialized = result.plan.model_dump_json().casefold()
    assert "raw_ios" not in serialized
    assert "javascript" not in serialized
    assert "actions" not in result.compact_summary()


def test_plan_is_deterministic_10_of_10_and_input_order_independent():
    intent, topology, configuration, capabilities = _fixture()
    results = [
        compile_enterprise_control_plane(
            deepcopy(intent), deepcopy(topology), deepcopy(configuration),
            capabilities=deepcopy(capabilities),
        )
        for _ in range(10)
    ]
    reordered_intent = deepcopy(intent)
    reordered_intent.stp_domains.reverse()
    reordered_intent.routing_domains.reverse()
    reordered_intent.etherchannels[0].member_link_ids.reverse()
    reordered_topology = deepcopy(topology)
    reordered_topology.devices.reverse()
    reordered_topology.links.reverse()
    reordered_configuration = deepcopy(configuration)
    reordered_configuration.actions.reverse()
    reordered = compile_enterprise_control_plane(
        reordered_intent,
        reordered_topology,
        reordered_configuration,
        capabilities=capabilities,
    )

    assert all(item.is_valid for item in results)
    assert len({item.semantic_hash for item in results}) == 1
    assert reordered.semantic_hash == results[0].semantic_hash
    assert reordered.plan.model_dump(mode="json") == results[0].plan.model_dump(mode="json")


def test_exact_e4_e5_foundations_portfast_safety_and_stable_allocations():
    plan = _compile().plan
    channel = next(item for item in plan.actions if isinstance(item, ConfigureEtherChannel))
    edge = next(item for item in plan.actions if isinstance(item, ConfigureStpEdgePort))
    hsrp = [item for item in plan.actions if isinstance(item, ConfigureHsrp)]
    sources = {item.source_id for item in plan.foundational_requirements}

    assert channel.channel_group == 1
    assert channel.member_interfaces == ["GigabitEthernet0/1", "GigabitEthernet0/2"]
    assert channel.source_link_ids == ["sw-member-a", "sw-member-b"]
    assert edge.interface == "FastEthernet0/1" and edge.portfast and edge.bpduguard
    assert all(item.group_number == 0 for item in hsrp)
    assert {item.virtual_ipv4 for item in hsrp} == {"10.0.10.1"}
    assert {item.physical_ipv4 for item in hsrp} == {"10.0.10.2", "10.0.10.3"}
    assert {
        "sw-member-a", "sw-member-b", "cfg/access/sw1/fa01",
        "cfg/l3/r1/hq-data", "cfg/l3/r2/hq-data",
    } <= sources


def test_actions_form_closed_shared_dag_and_expectations_cover_acceptance():
    plan = _compile().plan
    positions = {item.id: index for index, item in enumerate(plan.actions)}

    assert all(
        dependency in positions and positions[dependency] < positions[item.id]
        for item in plan.actions for dependency in item.depends_on
    )
    kinds = {item.kind.value for item in plan.verification_expectations}
    assert {
        "stp_state", "etherchannel_state", "hsrp_state", "routing_process",
        "routing_neighbor", "route_present", "end_to_end_reachability",
        "link_failure_convergence", "restore_recovery",
    } <= kinds
    assert {
        ControlPlaneCapabilityDimension.STP_STATE,
        ControlPlaneCapabilityDimension.ETHERCHANNEL_BEHAVIOR,
        ControlPlaneCapabilityDimension.HSRP_BEHAVIOR,
        ControlPlaneCapabilityDimension.ROUTING_NEIGHBOR_STATE,
        ControlPlaneCapabilityDimension.ETHERCHANNEL_FAILOVER,
    } <= {item.required_capability for item in plan.verification_expectations}
    assert all(
        item.expected.get("adjacent") is True
        for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTING_NEIGHBOR
    )


def test_failure_scenario_keeps_exact_e4_fault_and_restore_identity():
    scenario = _compile().plan.failure_scenarios[0]

    assert scenario.restore_required
    assert scenario.target_device_id == "sw1"
    assert scenario.target_device_name == "HQ-SW1"
    assert scenario.target_interface == "GigabitEthernet0/1"
    assert scenario.peer_device_id == "sw2"
    assert scenario.peer_device_name == "HQ-SW2"
    assert scenario.peer_interface == "GigabitEthernet0/1"
    assert scenario.cable == "cross"
    assert scenario.expected_surviving_link_ids == ["sw-member-b"]
    assert scenario.failure_domain_result.status is IndependenceStatus.INDEPENDENT
    assert _compile().plan.failure_domain_catalog.semantic_hash


def test_failure_scenario_rejects_a_declared_shared_risk_path():
    intent, topology, configuration, capabilities = _fixture()
    shared_conduit = FailureDomain(
        id="srg/shared-conduit",
        domain_type=FailureDomainType.SHARED_RISK,
        provenance=FailureDomainProvenance.EXPLICIT,
        link_ids=["sw-member-a", "sw-member-b"],
        evidence_reference="site-survey",
    )

    result = compile_enterprise_control_plane(
        intent,
        topology,
        configuration,
        capabilities=capabilities,
        failure_domains=[shared_conduit],
    )

    assert not result.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_FAILURE_DOMAIN_NOT_INDEPENDENT in {
        item.code for item in result.issues
    }


def test_required_provider_independence_without_evidence_stays_unknown():
    intent, topology, configuration, capabilities = _fixture()
    intent.failure_scenarios[0].required_independence_domains = [
        FailureDomainType.UPLINK_PROVIDER,
    ]

    result = compile_enterprise_control_plane(
        intent, topology, configuration, capabilities=capabilities,
    )

    assert result.is_valid
    scenario = result.plan.failure_scenarios[0]
    assert scenario.failure_domain_result.status is IndependenceStatus.UNKNOWN
    assert ConfigurationIssueCode.CONTROL_PLANE_FAILURE_DOMAIN_UNKNOWN in {
        item.code for item in result.issues
    }


def test_missing_transit_trunk_and_vip_collision_are_structured_errors():
    intent, topology, configuration, capabilities = _fixture()
    intent.routing_domains[0].transit_link_ids = []
    missing_transit = compile_enterprise_control_plane(
        intent, topology, configuration, capabilities=capabilities,
    )
    assert not missing_transit.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_TRANSIT_L3_MISSING in {
        item.code for item in missing_transit.issues
    }

    intent, topology, configuration, capabilities = _fixture()
    configuration.actions = [
        item for item in configuration.actions
        if getattr(item, "id", "") != "cfg/trunk/sw1/sw-member-a"
    ]
    missing_trunk = compile_enterprise_control_plane(
        intent, topology, configuration, capabilities=capabilities,
    )
    assert not missing_trunk.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_ETHERCHANNEL_TRUNK_MISSING in {
        item.code for item in missing_trunk.issues
    }

    intent, topology, configuration, capabilities = _fixture()
    intent.first_hop_redundancy[0].virtual_ipv4 = "10.0.10.2"
    collision = compile_enterprise_control_plane(
        intent, topology, configuration, capabilities=capabilities,
    )
    assert not collision.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_HSRP_VIP_COLLISION in {
        item.code for item in collision.issues
    }


def test_portfast_never_targets_an_e5_trunk_and_restore_is_mandatory():
    intent, topology, configuration, capabilities = _fixture()
    access = next(item for item in configuration.actions if isinstance(item, ConfigureAccessPort))
    access.interface = "GigabitEthernet0/1"
    conflict = compile_enterprise_control_plane(
        intent, topology, configuration, capabilities=capabilities,
    )
    assert not conflict.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_PORTFAST_TRUNK_CONFLICT in {
        item.code for item in conflict.issues
    }

    intent, topology, configuration, capabilities = _fixture()
    intent.failure_scenarios[0].restore_required = False
    no_restore = compile_enterprise_control_plane(
        intent, topology, configuration, capabilities=capabilities,
    )
    assert not no_restore.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_FAILURE_RESTORE_REQUIRED in {
        item.code for item in no_restore.issues
    }


def test_mst_and_all_required_configuration_features_are_capability_gated():
    intent, topology, configuration, capabilities = _fixture()
    intent.stp_domains[0].mode = StpMode.MST
    intent.stp_domains[0].mst_instances = {1: [10], 2: [20]}
    capabilities["2960-24TT"].dimensions[
        ControlPlaneCapabilityDimension.STP_MST_CONFIG
    ] = SecurityCapabilityStatus.UNKNOWN
    unknown = compile_enterprise_control_plane(
        intent, topology, configuration, capabilities=capabilities,
    )
    assert unknown.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_CAPABILITY_UNKNOWN in {
        item.code for item in unknown.issues
    }

    capabilities["2960-24TT"].dimensions[
        ControlPlaneCapabilityDimension.STP_MST_CONFIG
    ] = SecurityCapabilityStatus.UNSUPPORTED
    unsupported = compile_enterprise_control_plane(
        intent, topology, configuration, capabilities=capabilities,
    )
    assert not unsupported.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_CAPABILITY_UNSUPPORTED in {
        item.code for item in unsupported.issues
    }


def test_source_hash_mismatch_and_input_objects_are_not_mutated():
    intent, topology, configuration, capabilities = _fixture()
    original_intent = deepcopy(intent)
    original_topology = deepcopy(topology)
    original_configuration = deepcopy(configuration)
    configuration.source_topology_hash = "stale"
    result = compile_enterprise_control_plane(
        intent, topology, configuration, capabilities=capabilities,
    )

    assert not result.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_SOURCE_MISMATCH in {
        item.code for item in result.issues
    }
    assert intent == original_intent
    assert topology == original_topology
    original_configuration.source_topology_hash = "stale"
    assert configuration == original_configuration


def test_e8_hash_is_required_and_bound_only_for_consumed_security_policies():
    intent, topology, configuration, capabilities = _fixture()
    security = SecurityPlan(
        id="e8-security",
        source_topology_id=topology.id,
        source_topology_hash=topology.semantic_hash,
        source_configuration_id=configuration.id,
        source_configuration_hash=configuration.semantic_hash,
        semantic_hash="e8-security-hash",
        actions=[ApplyDeviceHardening(
            id="sec/harden/sw1",
            phase=SecurityPhase.HARDENING,
            device_id="sw1",
            device_name="HQ-SW1",
            model="2960-24TT",
            site_id="hq",
            required_capability=SecurityCapabilityDimension.HARDENING_CONFIG,
            policy_id="hardening/hq",
            banner_motd="Authorized use only",
            service_password_encryption=True,
        )],
    )

    ignored = compile_enterprise_control_plane(
        intent, topology, configuration,
        security_plan=security, capabilities=capabilities,
    )
    assert ignored.is_valid
    assert ignored.plan.source_security_hash == ""

    intent.security_policy_ids = ["hardening/hq"]
    missing = compile_enterprise_control_plane(
        intent, topology, configuration, capabilities=capabilities,
    )
    assert not missing.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_SECURITY_MISSING in {
        item.code for item in missing.issues
    }

    consumed = compile_enterprise_control_plane(
        intent, topology, configuration,
        security_plan=security, capabilities=capabilities,
    )
    assert consumed.is_valid
    assert consumed.plan.source_security_id == "e8-security"
    assert consumed.plan.source_security_hash == "e8-security-hash"
    assert "sec/harden/sw1" in {
        item.source_id for item in consumed.plan.foundational_requirements
    }


def test_multiple_stp_domains_are_site_scoped_and_do_not_overlap():
    intent, topology, configuration, capabilities = _fixture()
    branch_switch = _device(
        "branch-sw", "BR-SW", "switch", "branch", "access",
    )
    topology.devices.append(branch_switch)
    configuration.actions.append(CreateVlan(
        id="cfg/vlan/branch-sw/110",
        phase=ConfigurationPhase.L2_DEFINITIONS,
        device_id=branch_switch.id,
        device_name=branch_switch.name,
        site_id="branch",
        vlan_id=110,
        segment_id="branch-data",
    ))
    intent.stp_domains.append(StpIntent(
        id="stp/branch",
        site_id="branch",
        mode=StpMode.PVST,
        vlan_ids=[110],
        root_primary_by_vlan={110: "branch-sw"},
    ))

    result = compile_enterprise_control_plane(
        intent, topology, configuration, capabilities=capabilities,
    )

    assert result.is_valid, result.issues
    stp_actions = [
        item for item in result.plan.actions if isinstance(item, ConfigureSpanningTree)
    ]
    assert {(item.device_id, item.mode) for item in stp_actions} == {
        ("sw1", StpMode.RAPID_PVST),
        ("sw2", StpMode.RAPID_PVST),
        ("branch-sw", StpMode.PVST),
    }


def test_stp_rejects_portfast_on_physical_switch_link_even_if_e5_calls_it_access():
    intent, topology, configuration, capabilities = _fixture()
    intent.etherchannels = []
    configuration.actions = [
        item for item in configuration.actions
        if getattr(item, "id", "") != "cfg/trunk/sw1/sw-member-a"
    ]
    configuration.actions.append(ConfigureAccessPort(
        id="cfg/access/incorrect-switch-link",
        phase=ConfigurationPhase.L2_INTERFACES,
        device_id="sw1",
        device_name="HQ-SW1",
        site_id="hq",
        interface="GigabitEthernet0/1",
        data_vlan_id=10,
    ))

    result = compile_enterprise_control_plane(
        intent, topology, configuration, capabilities=capabilities,
    )

    assert not result.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_PORTFAST_TRUNK_CONFLICT in {
        item.code for item in result.issues
    }


def test_stp_failover_expectation_requires_a_real_alternate_e4_l2_path():
    redundant = _compile()
    assert redundant.is_valid
    assert any(
        item.required_capability is ControlPlaneCapabilityDimension.STP_FAILOVER
        and item.source_link_id in {"sw-member-a", "sw-member-b"}
        for item in redundant.plan.verification_expectations
    )

    intent, topology, configuration, capabilities = _fixture()
    intent.etherchannels = []
    intent.failure_scenarios[0].expected_surviving_link_ids = []
    topology.links = [
        item for item in topology.links if item.id != "sw-member-b"
    ]
    configuration.actions = [
        item for item in configuration.actions
        if getattr(item, "source_link_id", "") != "sw-member-b"
    ]
    nonredundant = compile_enterprise_control_plane(
        intent, topology, configuration, capabilities=capabilities,
    )

    assert nonredundant.is_valid, nonredundant.issues
    assert not any(
        item.required_capability is ControlPlaneCapabilityDimension.STP_FAILOVER
        for item in nonredundant.plan.verification_expectations
    )
