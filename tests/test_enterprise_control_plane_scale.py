from __future__ import annotations

from collections import Counter
from copy import deepcopy
from time import perf_counter

from packet_tracer_mcp.application.use_cases.compile_control_plane import (
    compile_enterprise_control_plane,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigureAccessPort,
    ConfigureRoutedInterface,
    ConfigureTrunk,
    ConfigurationPhase,
    ConfigurationPlan,
    CreateVlan,
    SetEndpointStaticAddress,
)
from packet_tracer_mcp.domain.enterprise.models.control_plane import (
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
from packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan


def _device(
    device_id: str,
    name: str,
    category: str,
    site_id: str,
    *,
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
    left: DevicePlan,
    left_port: str,
    right: DevicePlan,
    right_port: str,
    *,
    role: str,
    redundancy_group: str = "",
) -> LinkPlan:
    return LinkPlan(
        id=link_id,
        device_a=left.name,
        device_a_id=left.id,
        port_a=left_port,
        device_b=right.name,
        device_b_id=right.id,
        port_b=right_port,
        cable="cross",
        link_role=role,
        redundancy_group=redundancy_group,
    )


def _site_identity(index: int) -> tuple[str, str]:
    fixed = (("hq", "HQ"), ("branch-a", "BRANCH-A"), ("branch-b", "BRANCH-B"))
    return fixed[index] if index < len(fixed) else (f"branch-{index}", f"BRANCH-{index}")


def _scale_fixture(site_count: int = 3):
    devices: list[DevicePlan] = []
    links: list[LinkPlan] = []
    configuration_actions = []
    stp_domains: list[StpIntent] = []
    etherchannels: list[EtherChannelIntent] = []
    hsrp_groups: list[FirstHopRedundancyIntent] = []
    routing_domains: list[DynamicRoutingIntent] = []
    failure_scenarios: list[LinkFailureScenarioIntent] = []

    for index in range(site_count):
        site_id, label = _site_identity(index)
        sw1 = _device(
            f"{site_id}-sw1", f"{label}-SW1", "switch", site_id,
            layer="distribution",
        )
        sw2 = _device(
            f"{site_id}-sw2", f"{label}-SW2", "switch", site_id,
            layer="distribution",
        )
        r1 = _device(f"{site_id}-r1", f"{label}-R1", "router", site_id, layer="edge")
        r2 = _device(f"{site_id}-r2", f"{label}-R2", "router", site_id, layer="edge")
        pc_source = _device(
            f"{site_id}-pc-source", f"{label}-PC-SOURCE", "pc", site_id,
            model="PC-PT",
        )
        pc_destination = _device(
            f"{site_id}-pc-destination", f"{label}-PC-DESTINATION", "pc", site_id,
            model="PC-PT",
        )
        devices.extend((sw1, sw2, r1, r2, pc_source, pc_destination))

        bundle_a = _link(
            f"{site_id}-bundle-a", sw1, "GigabitEthernet0/1",
            sw2, "GigabitEthernet0/1", role="distribution_uplink",
            redundancy_group=f"{site_id}-bundle",
        )
        bundle_b = _link(
            f"{site_id}-bundle-b", sw1, "GigabitEthernet0/2",
            sw2, "GigabitEthernet0/2", role="distribution_uplink",
            redundancy_group=f"{site_id}-bundle",
        )
        transit = _link(
            f"{site_id}-transit", r1, "GigabitEthernet0/0",
            r2, "GigabitEthernet0/0", role="routing_transit",
            redundancy_group=f"{site_id}-routing",
        )
        links.extend((bundle_a, bundle_b, transit))

        data_segment = f"{site_id}-data"
        voice_segment = f"{site_id}-voice"
        r1_lan = f"{site_id}-r1-lan"
        r2_lan = f"{site_id}-r2-lan"
        transit_segment = f"{site_id}-transit"
        for switch in (sw1, sw2):
            configuration_actions.extend((
                CreateVlan(
                    id=f"cfg/vlan/{switch.id}/10",
                    phase=ConfigurationPhase.L2_DEFINITIONS,
                    device_id=switch.id,
                    device_name=switch.name,
                    site_id=site_id,
                    vlan_id=10,
                    segment_id=data_segment,
                ),
                CreateVlan(
                    id=f"cfg/vlan/{switch.id}/20",
                    phase=ConfigurationPhase.L2_DEFINITIONS,
                    device_id=switch.id,
                    device_name=switch.name,
                    site_id=site_id,
                    vlan_id=20,
                    segment_id=voice_segment,
                ),
            ))
        for link in (bundle_a, bundle_b):
            for switch, interface, peer in (
                (sw1, link.port_a, sw2),
                (sw2, link.port_b, sw1),
            ):
                configuration_actions.append(ConfigureTrunk(
                    id=f"cfg/trunk/{switch.id}/{link.id}",
                    phase=ConfigurationPhase.L2_INTERFACES,
                    device_id=switch.id,
                    device_name=switch.name,
                    site_id=site_id,
                    interface=interface,
                    allowed_vlans=[10, 20],
                    peer_device_id=peer.id,
                    source_link_id=link.id,
                ))
        configuration_actions.append(ConfigureAccessPort(
            id=f"cfg/access/{sw1.id}/fa01",
            phase=ConfigurationPhase.L2_INTERFACES,
            device_id=sw1.id,
            device_name=sw1.name,
            site_id=site_id,
            interface="FastEthernet0/1",
            data_vlan_id=10,
            endpoint_ids=[pc_source.id],
        ))

        subnet = f"10.{index}"
        l3_values = (
            (r1, "GigabitEthernet0/0", f"{subnet}.0.1", 30, transit_segment),
            (r2, "GigabitEthernet0/0", f"{subnet}.0.2", 30, transit_segment),
            (r1, "GigabitEthernet0/1", f"{subnet}.10.2", 24, data_segment),
            (r2, "GigabitEthernet0/1", f"{subnet}.10.3", 24, data_segment),
            (r1, "GigabitEthernet0/2", f"{subnet}.101.1", 24, r1_lan),
            (r2, "GigabitEthernet0/2", f"{subnet}.102.1", 24, r2_lan),
        )
        for router, interface, ipv4, prefix, segment_id in l3_values:
            configuration_actions.append(ConfigureRoutedInterface(
                id=f"cfg/l3/{router.id}/{segment_id}",
                phase=ConfigurationPhase.L3_INTERFACES,
                device_id=router.id,
                device_name=router.name,
                site_id=site_id,
                interface=interface,
                ipv4=ipv4,
                prefix=prefix,
                netmask="255.255.255.252" if prefix == 30 else "255.255.255.0",
                segment_id=segment_id,
                required_capability="layer3",
            ))
        configuration_actions.extend((
            SetEndpointStaticAddress(
                id=f"cfg/endpoint/{pc_source.id}",
                phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
                device_id=pc_source.id,
                device_name=pc_source.name,
                site_id=site_id,
                interface="FastEthernet0",
                ipv4=f"{subnet}.10.10",
                netmask="255.255.255.0",
                gateway=f"{subnet}.10.1",
                segment_id=data_segment,
            ),
            SetEndpointStaticAddress(
                id=f"cfg/endpoint/{pc_destination.id}",
                phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
                device_id=pc_destination.id,
                device_name=pc_destination.name,
                site_id=site_id,
                interface="FastEthernet0",
                ipv4=f"{subnet}.102.10",
                netmask="255.255.255.0",
                gateway=f"{subnet}.102.1",
                segment_id=r2_lan,
            ),
        ))

        stp_domains.append(StpIntent(
            id=f"stp/{site_id}",
            site_id=site_id,
            mode=StpMode.RAPID_PVST,
            vlan_ids=[10, 20],
            root_primary_by_vlan={10: sw1.id, 20: sw2.id},
            root_secondary_by_vlan={10: sw2.id, 20: sw1.id},
        ))
        etherchannels.append(EtherChannelIntent(
            id=f"etherchannel/{site_id}",
            member_link_ids=[bundle_a.id, bundle_b.id],
            protocol=EtherChannelProtocol.LACP,
        ))
        hsrp_groups.append(FirstHopRedundancyIntent(
            id=f"hsrp/{data_segment}",
            segment_id=data_segment,
            device_ids=[r1.id, r2.id],
        ))
        routing_domains.append(DynamicRoutingIntent(
            id=f"routing/{site_id}",
            site_id=site_id,
            protocol=DynamicRoutingProtocol.OSPFV2,
            device_ids=[r1.id, r2.id],
            transit_link_ids=[transit.id],
            process_id=1,
            area_by_segment={data_segment: 10},
        ))
        failure_scenarios.append(LinkFailureScenarioIntent(
            id=f"failure/{bundle_a.id}",
            link_id=bundle_a.id,
            probe_source_device_id=pc_source.id,
            probe_destination_device_id=pc_destination.id,
            expected_surviving_link_ids=[bundle_b.id],
        ))

    topology = TopologyPlan(
        id=f"e4-control-plane-scale-{site_count}",
        semantic_hash=f"e4-control-plane-scale-hash-{site_count}",
        devices=devices,
        links=links,
    )
    configuration = ConfigurationPlan(
        id=f"e5-control-plane-scale-{site_count}",
        source_topology_id=topology.id,
        source_topology_hash=topology.semantic_hash,
        semantic_hash=f"e5-control-plane-scale-hash-{site_count}",
        actions=configuration_actions,
    )
    intent = ControlPlaneIntent(
        id=f"e9-control-plane-scale-{site_count}",
        stp_domains=stp_domains,
        etherchannels=etherchannels,
        first_hop_redundancy=hsrp_groups,
        routing_domains=routing_domains,
        failure_scenarios=failure_scenarios,
    )
    capabilities = {
        "2960-24TT": ControlPlaneCapabilityProfile.supported("2960-24TT"),
        "2911": ControlPlaneCapabilityProfile.supported("2911"),
    }
    return intent, topology, configuration, capabilities


def _compile(site_count: int = 3):
    intent, topology, configuration, capabilities = _scale_fixture(site_count)
    return compile_enterprise_control_plane(
        intent, topology, configuration, capabilities=capabilities,
    )


def test_three_site_control_plane_compiles_with_compact_counts():
    result = _compile()

    assert result.is_valid, result.issues
    assert result.summary.action_count == 27
    assert result.summary.actions_by_type == {
        "configure_etherchannel": 6,
        "configure_hsrp": 6,
        "configure_ospfv2": 6,
        "configure_stp": 6,
        "configure_stp_edge_port": 3,
    }
    assert result.summary.dependencies == 9
    assert result.summary.verification_count == 69
    assert result.summary.failure_scenario_count == 3
    assert result.summary.errors == 0
    kinds = Counter(
        item.kind for item in result.plan.verification_expectations
    )
    assert kinds[ControlPlaneVerificationKind.ROUTING_NEIGHBOR] == 6
    assert kinds[ControlPlaneVerificationKind.ROUTE_PRESENT] == 6
    assert {
        item.site_id for item in result.plan.actions
        if item.site_id
    } == {"hq", "branch-a", "branch-b"}
    assert {
        item.link_id for item in result.plan.failure_scenarios
    } == {"hq-bundle-a", "branch-a-bundle-a", "branch-b-bundle-a"}
    assert all(
        item.expected_surviving_link_ids == [item.link_id.removesuffix("-a") + "-b"]
        for item in result.plan.failure_scenarios
    )
    assert {
        item.probe_destination_ipv4 for item in result.plan.failure_scenarios
    } == {"10.0.102.10", "10.1.102.10", "10.2.102.10"}


def test_three_site_control_plane_is_deterministic_under_reordering():
    intent, topology, configuration, capabilities = _scale_fixture()
    baseline = compile_enterprise_control_plane(
        deepcopy(intent), deepcopy(topology), deepcopy(configuration),
        capabilities=deepcopy(capabilities),
    )
    reordered_intent = deepcopy(intent)
    reordered_intent.stp_domains.reverse()
    reordered_intent.etherchannels.reverse()
    reordered_intent.first_hop_redundancy.reverse()
    reordered_intent.routing_domains.reverse()
    reordered_intent.failure_scenarios.reverse()
    for policy in reordered_intent.etherchannels:
        policy.member_link_ids.reverse()
    for policy in reordered_intent.first_hop_redundancy:
        policy.device_ids.reverse()
    for policy in reordered_intent.routing_domains:
        policy.device_ids.reverse()
        policy.transit_link_ids.reverse()
    for policy in reordered_intent.failure_scenarios:
        policy.expected_surviving_link_ids.reverse()
    reordered_topology = deepcopy(topology)
    reordered_topology.devices.reverse()
    reordered_topology.links.reverse()
    reordered_configuration = deepcopy(configuration)
    reordered_configuration.actions.reverse()

    reordered = compile_enterprise_control_plane(
        reordered_intent,
        reordered_topology,
        reordered_configuration,
        capabilities=deepcopy(capabilities),
    )

    assert baseline.is_valid, baseline.issues
    assert reordered.is_valid, reordered.issues
    assert reordered.semantic_hash == baseline.semantic_hash
    assert reordered.plan.model_dump(mode="json") == baseline.plan.model_dump(mode="json")


def test_larger_synthetic_control_plane_stays_compact_and_interactive():
    site_count = 18
    started = perf_counter()

    result = _compile(site_count)

    elapsed = perf_counter() - started
    assert result.is_valid, result.issues
    assert result.summary.action_count == 9 * site_count
    assert result.summary.dependencies == 3 * site_count
    assert result.summary.failure_scenario_count == site_count
    assert result.summary.verification_count == 23 * site_count
    assert len(result.semantic_hash) == 64
    assert elapsed < 5.0
