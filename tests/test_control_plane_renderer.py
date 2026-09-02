"""Renderer IOS cerrado de E9: payloads tipados, inversos y sin JavaScript."""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.compile_control_plane import (
    compile_enterprise_control_plane,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureEigrpIpv4,
    ConfigureEtherChannel,
    ConfigureHsrp,
    ConfigureOspfv2,
    ConfigureSpanningTree,
    ConfigureStpEdgePort,
    ControlPlaneCapabilityDimension,
    ControlPlanePhase,
    EtherChannelProtocol,
    LinkFailureScenario,
    RoutingNetwork,
    StpMode,
)
from src.packet_tracer_mcp.infrastructure.generator.control_plane_renderer import (
    PacketTracerControlPlaneFaultRenderer,
    PacketTracerControlPlaneRenderer,
)
from test_enterprise_control_plane import _fixture as e9_fixture


def _common(**updates):
    values = {
        "id": "cp-action-1",
        "phase": ControlPlanePhase.L2_RESILIENCY,
        "device_id": "sw-1",
        "device_name": "SW1",
        "model": "2960-24TT",
        "site_id": "hq",
        "required_capability": ControlPlaneCapabilityDimension.STP_RAPID_PVST_CONFIG,
    }
    values.update(updates)
    return values


def _network(*, area=0):
    return RoutingNetwork(
        network="10.0.0.0",
        wildcard="0.0.0.255",
        segment_id="transit-1",
        interface="GigabitEthernet0/0",
        source_configuration_action_id="cfg-r1-g0-0",
        area=area,
    )


@pytest.mark.parametrize(
    ("mode", "mst_instances"),
    [
        (StpMode.PVST, {}),
        (StpMode.RAPID_PVST, {}),
        (StpMode.MST, {1: [10], 2: [20]}),
    ],
)
def test_e9_fixture_compiles_and_renders_every_action_once(mode, mst_instances):
    intent, topology, configuration, capabilities = e9_fixture()
    intent.stp_domains[0].mode = mode
    intent.stp_domains[0].mst_instances = mst_instances

    result = compile_enterprise_control_plane(
        intent,
        topology,
        configuration,
        capabilities=capabilities,
    )

    assert result.is_valid, result.issues
    rendered = [
        PacketTracerControlPlaneRenderer().render_action(action)
        for action in result.plan.actions
    ]
    assert len(rendered) == len(result.plan.actions)

    for action, mutation in zip(result.plan.actions, rendered, strict=True):
        assert mutation.action_id == action.id
        assert mutation.device_name == action.device_name
        if not isinstance(action, ConfigureSpanningTree):
            continue
        for vlan in action.root_primary_vlans:
            priority = action.priorities[vlan]
            if mode is StpMode.MST:
                instance = next(
                    key for key, vlans in action.mst_instances.items() if vlan in vlans
                )
                assert f"spanning-tree mst {instance} root primary" not in mutation.ios_payload
                command = f"spanning-tree mst {instance} priority {priority}"
            else:
                assert f"spanning-tree vlan {vlan} root primary" not in mutation.ios_payload
                command = f"spanning-tree vlan {vlan} priority {priority}"
            assert mutation.ios_payload.count(command) == 1
        for vlan in action.root_secondary_vlans:
            priority = action.priorities[vlan]
            if mode is StpMode.MST:
                instance = next(
                    key for key, vlans in action.mst_instances.items() if vlan in vlans
                )
                assert f"spanning-tree mst {instance} root secondary" not in mutation.ios_payload
                command = f"spanning-tree mst {instance} priority {priority}"
            else:
                assert f"spanning-tree vlan {vlan} root secondary" not in mutation.ios_payload
                command = f"spanning-tree vlan {vlan} priority {priority}"
            assert mutation.ios_payload.count(command) == 1


def test_pvst_renderer_reuses_existing_semantics_and_builds_cleanup():
    action = ConfigureSpanningTree(
        **_common(),
        mode=StpMode.RAPID_PVST,
        vlan_ids=[10, 20, 30],
        root_primary_vlans=[10],
        root_secondary_vlans=[20],
        # Las prioridades deterministas del compiler reemplazan los macros
        # dinámicos de root en el borde IOS.
        priorities={10: 24576, 20: 28672, 30: 32768},
    )

    rendered = PacketTracerControlPlaneRenderer().render_action(action)

    assert "spanning-tree mode rapid-pvst" in rendered.ios_payload
    assert "spanning-tree vlan 10 root primary" not in rendered.ios_payload
    assert "spanning-tree vlan 20 root secondary" not in rendered.ios_payload
    assert "spanning-tree vlan 10 priority 24576" in rendered.ios_payload
    assert "spanning-tree vlan 20 priority 28672" in rendered.ios_payload
    assert "spanning-tree vlan 30 priority 32768" in rendered.ios_payload
    assert "no spanning-tree vlan 10 priority" in rendered.cleanup_payload
    assert rendered.cleanup_payload.endswith("spanning-tree mode pvst\nend\nwrite memory")


def test_mst_renderer_maps_vlans_to_instances_and_removes_them_on_cleanup():
    action = ConfigureSpanningTree(
        **_common(
            required_capability=ControlPlaneCapabilityDimension.STP_MST_CONFIG,
        ),
        mode=StpMode.MST,
        vlan_ids=[10, 20],
        root_primary_vlans=[10],
        priorities={20: 24576},
        mst_instances={1: [10], 2: [20]},
    )

    rendered = PacketTracerControlPlaneRenderer().render_action(action)

    assert "spanning-tree mst configuration" in rendered.ios_payload
    assert " instance 1 vlan 10" in rendered.ios_payload
    assert "spanning-tree mst 1 root primary" in rendered.ios_payload
    assert "spanning-tree mst 2 priority 24576" in rendered.ios_payload
    assert " no instance 1" in rendered.cleanup_payload
    assert "spanning-tree mode pvst" in rendered.cleanup_payload


@pytest.mark.parametrize("mode", [StpMode.PVST, StpMode.RAPID_PVST, StpMode.MST])
def test_stp_renderer_rejects_explicit_priority_that_contradicts_root_role(mode):
    if mode is StpMode.MST:
        capability = ControlPlaneCapabilityDimension.STP_MST_CONFIG
    elif mode is StpMode.PVST:
        capability = ControlPlaneCapabilityDimension.STP_PVST_CONFIG
    else:
        capability = ControlPlaneCapabilityDimension.STP_RAPID_PVST_CONFIG
    action = ConfigureSpanningTree(
        **_common(required_capability=capability),
        mode=mode,
        vlan_ids=[10],
        root_primary_vlans=[10],
        priorities={10: 28672},
        mst_instances={1: [10]} if mode is StpMode.MST else {},
    )

    with pytest.raises(ValueError, match="primary-root priority"):
        PacketTracerControlPlaneRenderer().render_action(action)


def test_stp_edge_port_has_an_exact_inverse():
    action = ConfigureStpEdgePort(
        **_common(
            phase=ControlPlanePhase.L2_FOUNDATION,
            required_capability=ControlPlaneCapabilityDimension.STP_EDGE_CONFIG,
        ),
        interface="FastEthernet0/1",
        source_access_action_id="access-fa0-1",
    )

    rendered = PacketTracerControlPlaneRenderer().render_action(action)

    assert " spanning-tree portfast" in rendered.ios_payload
    assert " spanning-tree bpduguard enable" in rendered.ios_payload
    assert " no spanning-tree portfast" in rendered.cleanup_payload
    assert " no spanning-tree bpduguard enable" in rendered.cleanup_payload


def test_stp_edge_port_rejects_the_global_pvst_capability():
    action = ConfigureStpEdgePort(
        **_common(
            phase=ControlPlanePhase.L2_FOUNDATION,
            required_capability=ControlPlaneCapabilityDimension.STP_PVST_CONFIG,
        ),
        interface="FastEthernet0/1",
        source_access_action_id="access-fa0-1",
    )

    with pytest.raises(ValueError, match="stp_edge_config"):
        PacketTracerControlPlaneRenderer().render_action(action)


@pytest.mark.parametrize(
    ("protocol", "mode", "capability"),
    [
        (
            EtherChannelProtocol.LACP, "active",
            ControlPlaneCapabilityDimension.ETHERCHANNEL_LACP_CONFIG,
        ),
        (
            EtherChannelProtocol.PAGP, "desirable",
            ControlPlaneCapabilityDimension.ETHERCHANNEL_PAGP_CONFIG,
        ),
        (
            EtherChannelProtocol.STATIC, "on",
            ControlPlaneCapabilityDimension.ETHERCHANNEL_STATIC_CONFIG,
        ),
    ],
)
def test_etherchannel_is_rendered_only_from_typed_members(protocol, mode, capability):
    action = ConfigureEtherChannel(
        **_common(
            required_capability=capability,
        ),
        etherchannel_id="ec-1",
        peer_device_id="sw-2",
        protocol=protocol,
        channel_group=1,
        port_channel_interface="Port-channel1",
        member_interfaces=["FastEthernet0/1", "FastEthernet0/2"],
        allowed_vlans=[10, 20],
        native_vlan_id=10,
        source_link_ids=["link-1", "link-2"],
        source_trunk_action_ids=["trunk-1"],
    )

    rendered = PacketTracerControlPlaneRenderer().render_action(action)

    assert rendered.ios_payload.count(f"channel-group 1 mode {mode}") == 2
    assert "interface Port-channel1" in rendered.ios_payload
    assert "switchport trunk allowed vlan 10,20" in rendered.ios_payload
    assert rendered.cleanup_payload.count("no channel-group 1") == 2
    assert "no interface Port-channel1" in rendered.cleanup_payload


def test_hsrp_validates_addresses_and_removes_the_compiled_group():
    action = ConfigureHsrp(
        **_common(
            phase=ControlPlanePhase.L3_RESILIENCY,
            device_id="r1",
            device_name="R1",
            model="2911",
            required_capability=ControlPlaneCapabilityDimension.HSRP_CONFIG,
        ),
        redundancy_id="hsrp-users",
        interface="GigabitEthernet0/0",
        segment_id="users",
        group_number=10,
        virtual_ipv4="10.0.10.1",
        physical_ipv4="10.0.10.2",
        priority=110,
        preempt=True,
        source_configuration_action_id="cfg-r1-users",
    )

    rendered = PacketTracerControlPlaneRenderer().render_action(action)

    assert "standby 10 ip 10.0.10.1" in rendered.ios_payload
    assert "standby 10 priority 110" in rendered.ios_payload
    assert "standby 10 preempt" in rendered.ios_payload
    assert "no standby 10" in rendered.cleanup_payload


def test_ospf_and_eigrp_reuse_existing_network_command_semantics():
    ospf = ConfigureOspfv2(
        **_common(
            phase=ControlPlanePhase.DYNAMIC_ROUTING,
            device_id="r1",
            device_name="R1",
            model="2911",
            required_capability=ControlPlaneCapabilityDimension.OSPFV2_CONFIG,
        ),
        process_id=7,
        router_id="1.1.1.1",
        networks=[_network()],
        passive_interfaces=["GigabitEthernet0/1"],
    )
    eigrp_network = _network(area=None)
    eigrp = ConfigureEigrpIpv4(
        **_common(
            id="cp-action-2",
            phase=ControlPlanePhase.DYNAMIC_ROUTING,
            device_id="r1",
            device_name="R1",
            model="2911",
            required_capability=ControlPlaneCapabilityDimension.EIGRP_IPV4_CONFIG,
        ),
        as_number=100,
        router_id="1.1.1.1",
        networks=[eigrp_network],
        passive_interfaces=["GigabitEthernet0/1"],
    )

    ospf_rendered = PacketTracerControlPlaneRenderer().render_action(ospf)
    eigrp_rendered = PacketTracerControlPlaneRenderer().render_action(eigrp)

    assert "router ospf 7" in ospf_rendered.ios_payload
    assert "network 10.0.0.0 0.0.0.255 area 0" in ospf_rendered.ios_payload
    assert "passive-interface GigabitEthernet0/1" in ospf_rendered.ios_payload
    assert "no router ospf 7" in ospf_rendered.cleanup_payload
    assert "router eigrp 100" in eigrp_rendered.ios_payload
    assert "eigrp router-id 1.1.1.1" in eigrp_rendered.ios_payload
    assert "network 10.0.0.0 0.0.0.255" in eigrp_rendered.ios_payload
    assert "no auto-summary" in eigrp_rendered.ios_payload
    assert "no router eigrp 100" in eigrp_rendered.cleanup_payload


@pytest.mark.parametrize(
    "action",
    [
        ConfigureHsrp(
            **_common(
                device_name="R1\nend",
                phase=ControlPlanePhase.L3_RESILIENCY,
                required_capability=ControlPlaneCapabilityDimension.HSRP_CONFIG,
            ),
            redundancy_id="hsrp-1", interface="GigabitEthernet0/0",
            segment_id="users", group_number=1, virtual_ipv4="10.0.0.1",
            physical_ipv4="10.0.0.2", source_configuration_action_id="cfg-1",
        ),
        ConfigureEtherChannel(
            **_common(
                required_capability=ControlPlaneCapabilityDimension.ETHERCHANNEL_LACP_CONFIG,
            ),
            etherchannel_id="ec-1", peer_device_id="sw-2",
            protocol=EtherChannelProtocol.LACP, channel_group=1,
            port_channel_interface="Port-channel2",
            member_interfaces=["FastEthernet0/1", "FastEthernet0/2"],
        ),
        ConfigureEtherChannel(
            **_common(
                required_capability=ControlPlaneCapabilityDimension.ETHERCHANNEL_LACP_CONFIG,
            ),
            etherchannel_id="ec-1", peer_device_id="sw-2",
            protocol=EtherChannelProtocol.LACP, channel_group=1,
            port_channel_interface="Port-channel1",
            member_interfaces=["FastEthernet0/1\nshutdown", "FastEthernet0/2"],
        ),
        ConfigureStpEdgePort(
            **_common(
                device_name="SW1 ",
                phase=ControlPlanePhase.L2_FOUNDATION,
                required_capability=ControlPlaneCapabilityDimension.STP_EDGE_CONFIG,
            ),
            interface="FastEthernet0/1",
            source_access_action_id="access-fa0-1",
        ),
        ConfigureOspfv2(
            **_common(
                phase=ControlPlanePhase.DYNAMIC_ROUTING,
                device_id="r1", device_name="R1", model="2911",
                required_capability=ControlPlaneCapabilityDimension.OSPFV2_CONFIG,
            ),
            process_id=1, router_id="not-an-ip", networks=[_network()],
        ),
    ],
)
def test_renderer_rejects_hostile_or_inconsistent_compiled_actions(action):
    with pytest.raises(ValueError):
        PacketTracerControlPlaneRenderer().render_action(action)


def test_all_regular_mutations_are_ios_only_and_have_persistent_cleanup():
    action = ConfigureStpEdgePort(
        **_common(
            phase=ControlPlanePhase.L2_FOUNDATION,
            required_capability=ControlPlaneCapabilityDimension.STP_EDGE_CONFIG,
        ),
        interface="FastEthernet0/1",
        source_access_action_id="access-fa0-1",
    )

    rendered = PacketTracerControlPlaneRenderer().render_action(action)

    combined = rendered.ios_payload + rendered.cleanup_payload
    assert "ipc." not in combined
    assert "configureIosDevice" not in combined
    assert rendered.ios_payload.endswith("end\nwrite memory")
    assert rendered.cleanup_payload.endswith("end\nwrite memory")


def test_fault_renderer_uses_only_the_compiled_target_and_never_persists_it():
    scenario = LinkFailureScenario(
        id="failure-1",
        link_id="link-1",
        device_a_id="r1",
        device_b_id="r2",
        target_device_id="r1",
        target_device_name="R1",
        target_interface="GigabitEthernet0/0",
        peer_device_id="r2",
        peer_device_name="R2",
        peer_interface="GigabitEthernet0/0",
        cable="cross",
        probe_source_device_id="pc-1",
        probe_source_device_name="PC1",
        probe_destination_device_id="pc-2",
        probe_destination_device_name="PC2",
        probe_destination_ipv4="10.0.20.10",
        expected_surviving_link_ids=["link-2"],
        restore_required=True,
        verification_expectation_ids=["verify-failover", "verify-restore"],
    )

    rendered = PacketTracerControlPlaneFaultRenderer().render_scenario(scenario)

    assert rendered.device_name == "R1"
    assert rendered.interface == "GigabitEthernet0/0"
    assert rendered.ios_payload == (
        "enable\nconfigure terminal\ninterface GigabitEthernet0/0\n"
        " shutdown\n exit\nend"
    )
    assert rendered.cleanup_payload == (
        "enable\nconfigure terminal\ninterface GigabitEthernet0/0\n"
        " no shutdown\n exit\nend"
    )
    assert "write memory" not in rendered.ios_payload
    assert "write memory" not in rendered.cleanup_payload


def test_fault_renderer_rejects_a_scenario_without_mandatory_restore():
    scenario = LinkFailureScenario(
        id="failure-1", link_id="link-1", device_a_id="r1", device_b_id="r2",
        target_device_id="r1", target_device_name="R1",
        target_interface="GigabitEthernet0/0", peer_device_id="r2",
        peer_device_name="R2", peer_interface="GigabitEthernet0/0", cable="cross",
        probe_source_device_id="pc-1", probe_destination_device_id="pc-2",
        probe_source_device_name="PC1", probe_destination_device_name="PC2",
        probe_destination_ipv4="10.0.20.10",
        restore_required=False,
    )

    with pytest.raises(ValueError, match="requires an inverse restore"):
        PacketTracerControlPlaneFaultRenderer().render_scenario(scenario)


def test_fault_renderer_rejects_a_noncanonical_probe_destination():
    scenario = LinkFailureScenario(
        id="failure-1", link_id="link-1", device_a_id="r1", device_b_id="r2",
        target_device_id="r1", target_device_name="R1",
        target_interface="GigabitEthernet0/0", peer_device_id="r2",
        peer_device_name="R2", peer_interface="GigabitEthernet0/0", cable="cross",
        probe_source_device_id="pc-1", probe_source_device_name="PC1",
        probe_destination_device_id="pc-2", probe_destination_device_name="PC2",
        probe_destination_ipv4="10.0.0.1; reload", restore_required=True,
    )

    with pytest.raises(ValueError, match="probe destination IPv4"):
        PacketTracerControlPlaneFaultRenderer().render_scenario(scenario)


def test_fault_renderer_rejects_a_trimmed_instead_of_exact_target_interface():
    scenario = LinkFailureScenario(
        id="failure-1", link_id="link-1", device_a_id="r1", device_b_id="r2",
        target_device_id="r1", target_device_name="R1",
        target_interface=" GigabitEthernet0/0", peer_device_id="r2",
        peer_device_name="R2", peer_interface="GigabitEthernet0/0", cable="cross",
        probe_source_device_id="pc-1", probe_source_device_name="PC1",
        probe_destination_device_id="pc-2", probe_destination_device_name="PC2",
        probe_destination_ipv4="10.0.20.10", restore_required=True,
    )

    with pytest.raises(ValueError, match="exact IOS interface"):
        PacketTracerControlPlaneFaultRenderer().render_scenario(scenario)
