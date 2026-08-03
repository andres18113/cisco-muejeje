"""E5 offline: configuración tipada, dependencias y renderizado confiable."""

from __future__ import annotations

from time import perf_counter

import pytest

from src.packet_tracer_mcp.application.use_cases.compile_configuration import (
    compile_enterprise_configuration,
)
from src.packet_tracer_mcp.domain.enterprise.models.addressing import (
    AddressSpace,
    AddressingPlan,
    SubnetAllocation,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    DeviceCapabilities,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
    ConfigurationIssueCode,
    ConfigurationPhase,
    ConfigurationPolicy,
    ConfigureAccessPort,
    ConfigureDhcpPool,
    CreateVlan,
    SetEndpointStaticAddress,
)
from src.packet_tracer_mcp.domain.enterprise.models.enterprise_plan import EnterprisePlan, SitePlan
from src.packet_tracer_mcp.domain.enterprise.models.intent import SiteType
from src.packet_tracer_mcp.domain.enterprise.models.segments import NetworkSegment, SegmentRole
from src.packet_tracer_mcp.domain.enterprise.services.configuration_dependencies import (
    ConfigurationDependencyError,
    order_configuration_actions,
)
from src.packet_tracer_mcp.domain.enterprise.services.configuration_validator import (
    validate_configuration_actions,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan
from src.packet_tracer_mcp.infrastructure.generator.configuration_renderer import (
    PacketTracerIosRenderer,
)


def _allocation(segment: str, network: str, gateway: str) -> SubnetAllocation:
    return SubnetAllocation(
        segment_id=segment,
        network=network,
        prefix=24,
        netmask="255.255.255.0",
        gateway=gateway,
        first_usable=gateway,
        last_usable=network.rsplit(".", 1)[0] + ".254",
        broadcast=network.rsplit(".", 1)[0] + ".255",
        usable_hosts=254,
        required_hosts=4,
        growth_percent=0,
    )


def _fixture() -> tuple[EnterprisePlan, TopologyPlan, ConfigurationPolicy]:
    enterprise = EnterprisePlan(
        id="ent_e5",
        name="E5",
        address_space="198.18.0.0/15",
        sites=[SitePlan(
            name="HQ",
            site_id="hq",
            type=SiteType.HQ,
            segments=[
                NetworkSegment(
                    name="hq-data",
                    role=SegmentRole.DATA,
                    site="hq",
                    host_requirement=1,
                    dhcp=True,
                    vlan_id=10,
                ),
                NetworkSegment(
                    name="hq-voice",
                    role=SegmentRole.VOICE,
                    site="hq",
                    host_requirement=1,
                    vlan_id=20,
                ),
            ],
        )],
        addressing=AddressingPlan(
            address_space=AddressSpace(network="198.18.0.0/15"),
            allocations=[
                _allocation("hq-data", "198.18.150.0", "198.18.150.1"),
                _allocation("hq-voice", "198.18.151.0", "198.18.151.1"),
            ],
        ),
    )
    devices = [
        DevicePlan(
            id="r1", name="__MCP_E5_R1", model="2911", category="router",
            enterprise_role="edge_router", site_id="hq", network_layer="edge",
        ),
        DevicePlan(
            id="sw-dist", name="__MCP_E5_DIST", model="2960-24TT", category="switch",
            enterprise_role="distribution_switch", site_id="hq", network_layer="distribution",
        ),
        DevicePlan(
            id="sw-access", name="__MCP_E5_ACCESS", model="2960-24TT", category="switch",
            enterprise_role="access_switch", site_id="hq", network_layer="access",
        ),
        DevicePlan(
            id="phone-1", name="__MCP_E5_PHONE", model="7960", category="phone",
            enterprise_role="ip_phone", site_id="hq",
            metadata={"pair_id": "pair-1", "addressing_preference": "static"},
        ),
        DevicePlan(
            id="pc-1", name="__MCP_E5_PC", model="PC-PT", category="pc",
            enterprise_role="user_pc", site_id="hq",
            metadata={"pair_id": "pair-1", "addressing_preference": "dhcp"},
        ),
    ]
    links = [
        LinkPlan(
            id="router-dist", device_a="__MCP_E5_R1", device_a_id="r1",
            port_a="GigabitEthernet0/0", device_b="__MCP_E5_DIST", device_b_id="sw-dist",
            port_b="GigabitEthernet0/2", link_role="edge_link",
        ),
        LinkPlan(
            id="dist-access", device_a="__MCP_E5_DIST", device_a_id="sw-dist",
            port_a="GigabitEthernet0/1", device_b="__MCP_E5_ACCESS", device_b_id="sw-access",
            port_b="GigabitEthernet0/1", link_role="access_uplink",
        ),
        LinkPlan(
            id="access-phone", device_a="__MCP_E5_ACCESS", device_a_id="sw-access",
            port_a="FastEthernet0/1", device_b="__MCP_E5_PHONE", device_b_id="phone-1",
            port_b="Port 1", link_role="endpoint_access",
        ),
        LinkPlan(
            id="phone-pc", device_a="__MCP_E5_PHONE", device_a_id="phone-1",
            port_a="Port 2", device_b="__MCP_E5_PC", device_b_id="pc-1",
            port_b="FastEthernet0", link_role="phone_passthrough",
        ),
    ]
    topology = TopologyPlan(
        id="topology-e5",
        name="E5 physical",
        semantic_hash="e4-source-hash",
        devices=devices,
        links=links,
    )
    policy = ConfigurationPolicy(
        gateway_device_ids={"hq": "r1"},
        dhcp_server_device_ids={"hq": "r1"},
        dns_server="198.18.150.53",
    )
    return enterprise, topology, policy


def _compile():
    enterprise, topology, policy = _fixture()
    return compile_enterprise_configuration(enterprise, topology, policy)


def test_configuration_compiler_binds_source_hash_and_emits_typed_actions():
    result = _compile()

    assert result.is_valid
    assert result.plan is not None
    assert result.plan.source_topology_hash == "e4-source-hash"
    assert result.plan.semantic_hash
    action_types = {action.action_type for action in result.plan.actions}
    assert action_types >= {
        ConfigurationActionType.CREATE_VLAN,
        ConfigurationActionType.CONFIGURE_ACCESS_PORT,
        ConfigurationActionType.CONFIGURE_TRUNK,
        ConfigurationActionType.CONFIGURE_SUBINTERFACE,
        ConfigurationActionType.CONFIGURE_DHCP_POOL,
        ConfigurationActionType.SET_ENDPOINT_STATIC,
        ConfigurationActionType.SET_ENDPOINT_DHCP,
    }


def test_configuration_compilation_is_identical_ten_times():
    results = [_compile() for _ in range(10)]
    plans = [result.plan.model_dump(mode="json") for result in results]

    assert all(result.is_valid for result in results)
    assert all(plan == plans[0] for plan in plans)
    assert len({result.semantic_hash for result in results}) == 1


def test_configuration_compilation_ignores_semantically_irrelevant_input_order():
    enterprise, topology, policy = _fixture()
    first = compile_enterprise_configuration(enterprise, topology, policy)
    reordered_enterprise = enterprise.model_copy(deep=True)
    reordered_enterprise.sites.reverse()
    reordered_enterprise.sites[0].segments.reverse()
    reordered_enterprise.addressing.allocations.reverse()
    reordered_topology = topology.model_copy(deep=True)
    reordered_topology.devices.reverse()
    reordered_topology.links.reverse()
    second = compile_enterprise_configuration(reordered_enterprise, reordered_topology, policy)

    assert first.plan.model_dump(mode="json") == second.plan.model_dump(mode="json")
    assert first.semantic_hash == second.semantic_hash


def test_access_port_uses_e4_interface_and_compiles_phone_data_voice_pair_once():
    plan = _compile().plan
    access = [
        action for action in plan.actions
        if action.action_type is ConfigurationActionType.CONFIGURE_ACCESS_PORT
    ]

    assert len(access) == 1
    assert access[0].device_id == "sw-access"
    assert access[0].interface == "FastEthernet0/1"
    assert access[0].data_vlan_id == 10
    assert access[0].voice_vlan_id == 20


def test_trunks_use_exact_e4_ports_and_minimal_stably_sorted_vlan_sets():
    plan = _compile().plan
    trunks = [
        action for action in plan.actions
        if action.action_type is ConfigurationActionType.CONFIGURE_TRUNK
    ]

    assert {(action.device_id, action.interface) for action in trunks} == {
        ("sw-dist", "GigabitEthernet0/1"),
        ("sw-access", "GigabitEthernet0/1"),
        ("sw-dist", "GigabitEthernet0/2"),
    }
    assert all(action.allowed_vlans == [10, 20] for action in trunks)
    assert all(action.native_vlan_id is None for action in trunks)


def test_single_segment_router_uses_exact_e4_routed_port_and_switch_access_side():
    enterprise, topology, policy = _fixture()
    enterprise.sites[0].segments = [enterprise.sites[0].segments[0]]
    enterprise.addressing.allocations = [enterprise.addressing.allocations[0]]
    topology.devices = [device for device in topology.devices if device.id != "phone-1"]
    topology.links = [link for link in topology.links if link.id not in {"phone-pc"}]
    endpoint_link = next(link for link in topology.links if link.id == "access-phone")
    endpoint_link.device_b = "__MCP_E5_PC"
    endpoint_link.device_b_id = "pc-1"
    endpoint_link.port_b = "FastEthernet0"

    result = compile_enterprise_configuration(enterprise, topology, policy)
    routed = result.plan.actions_of_type(ConfigurationActionType.CONFIGURE_ROUTED_INTERFACE)
    gateway_access = [
        action for action in result.plan.actions_of_type(
            ConfigurationActionType.CONFIGURE_ACCESS_PORT
        )
        if action.device_id == "sw-dist"
    ]

    assert result.is_valid
    assert len(routed) == 1
    assert routed[0].device_id == "r1"
    assert routed[0].interface == "GigabitEthernet0/0"
    assert routed[0].ipv4 == "198.18.150.1"
    assert len(gateway_access) == 1
    assert gateway_access[0].interface == "GigabitEthernet0/2"
    assert gateway_access[0].data_vlan_id == 10


def test_svi_compiles_but_unknown_runtime_capability_remains_a_warning():
    enterprise, topology, policy = _fixture()
    policy.gateway_device_ids = {"hq": "sw-dist"}
    policy.dhcp_server_device_ids = {"hq": "sw-dist"}
    capabilities = {
        "2960-24TT": DeviceCapabilities(
            model="2960-24TT",
            category="switch",
            supports_vlan=CapabilityStatus.SUPPORTED,
            supports_trunk=CapabilityStatus.SUPPORTED,
            supports_svi=CapabilityStatus.UNKNOWN,
            supports_dhcp_server=CapabilityStatus.UNKNOWN,
        ),
    }

    result = compile_enterprise_configuration(enterprise, topology, policy, capabilities)

    assert result.is_valid
    assert len(result.plan.actions_of_type(ConfigurationActionType.CONFIGURE_SVI)) == 2
    assert ConfigurationIssueCode.CAPABILITY_UNVERIFIED in {
        issue.code for issue in result.issues
    }


def test_actions_are_topologically_sorted_and_dependencies_precede_consumers():
    plan = _compile().plan
    positions = {action.id: index for index, action in enumerate(plan.actions)}

    assert all(
        positions[dependency] < positions[action.id]
        for action in plan.actions
        for dependency in action.depends_on
    )
    access = next(
        action for action in plan.actions
        if action.action_type is ConfigurationActionType.CONFIGURE_ACCESS_PORT
    )
    assert len(access.depends_on) == 2


def test_dependency_cycle_is_a_compile_error_not_an_infinite_loop():
    first = CreateVlan(
        id="vlan-a", phase=ConfigurationPhase.L2_DEFINITIONS,
        device_id="sw", device_name="SW", site_id="hq", vlan_id=10,
        depends_on=["vlan-b"],
    )
    second = CreateVlan(
        id="vlan-b", phase=ConfigurationPhase.L2_DEFINITIONS,
        device_id="sw", device_name="SW", site_id="hq", vlan_id=20,
        depends_on=["vlan-a"],
    )

    with pytest.raises(ConfigurationDependencyError):
        order_configuration_actions([first, second])


@pytest.mark.parametrize("vlan_id", [0, 1002, 1003, 1004, 1005, 4095])
def test_invalid_or_reserved_vlan_ids_fail_compilation(vlan_id: int):
    enterprise, topology, policy = _fixture()
    enterprise.sites[0].segments[0].vlan_id = vlan_id

    result = compile_enterprise_configuration(enterprise, topology, policy)

    assert not result.is_valid
    assert result.plan is None
    assert ConfigurationIssueCode.VLAN_INVALID_ID in {issue.code for issue in result.issues}


def test_conflicting_segment_vlan_ids_are_not_silently_renumbered():
    enterprise, topology, policy = _fixture()
    enterprise.sites[0].segments[1].vlan_id = 10

    result = compile_enterprise_configuration(enterprise, topology, policy)

    assert not result.is_valid
    assert ConfigurationIssueCode.VLAN_ID_CONFLICT in {issue.code for issue in result.issues}


def test_access_and_trunk_cannot_target_the_same_physical_interface():
    enterprise, topology, policy = _fixture()
    endpoint_link = next(link for link in topology.links if link.id == "access-phone")
    endpoint_link.port_a = "GigabitEthernet0/1"

    result = compile_enterprise_configuration(enterprise, topology, policy)

    assert not result.is_valid
    assert ConfigurationIssueCode.ACCESS_TRUNK_CONFLICT in {issue.code for issue in result.issues}


def test_dhcp_pool_excludes_gateway_and_static_assignments_and_client_depends_on_pool():
    plan = _compile().plan
    pool = next(
        action for action in plan.actions
        if action.action_type is ConfigurationActionType.CONFIGURE_DHCP_POOL
    )
    client = next(
        action for action in plan.actions
        if action.action_type is ConfigurationActionType.SET_ENDPOINT_DHCP
    )

    assert pool.gateway == "198.18.150.1"
    assert pool.excluded_ranges[0].start == "198.18.150.1"
    assert pool.lease_start == "198.18.150.2"
    assert pool.lease_end == "198.18.150.254"
    assert pool.id in client.depends_on


def test_phone_addressing_targets_logical_vlan1_not_a_cable_port():
    plan = _compile().plan
    phone = next(
        action for action in plan.actions
        if action.action_type is ConfigurationActionType.SET_ENDPOINT_STATIC
        and action.device_id == "phone-1"
    )
    pc = next(
        action for action in plan.actions
        if action.action_type is ConfigurationActionType.SET_ENDPOINT_DHCP
        and action.device_id == "pc-1"
    )

    assert phone.interface == "Vlan1"
    assert pc.interface == "FastEthernet0"


def test_validator_detects_duplicate_static_ip_and_unexcluded_dhcp_overlap():
    actions = [
        SetEndpointStaticAddress(
            id="static-a", phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
            device_id="pc-a", device_name="PC-A", site_id="hq",
            interface="FastEthernet0", ipv4="198.18.10.10", netmask="255.255.255.0",
            gateway="198.18.10.1", segment_id="hq-data",
        ),
        SetEndpointStaticAddress(
            id="static-b", phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
            device_id="pc-b", device_name="PC-B", site_id="hq",
            interface="FastEthernet0", ipv4="198.18.10.10", netmask="255.255.255.0",
            gateway="198.18.10.1", segment_id="hq-data",
        ),
        ConfigureDhcpPool(
            id="pool", phase=ConfigurationPhase.SERVICES,
            device_id="r1", device_name="R1", site_id="hq", pool_name="HQ_DATA",
            segment_id="hq-data", network="198.18.10.0", prefix=24,
            netmask="255.255.255.0", gateway="198.18.10.1",
            lease_start="198.18.10.2", lease_end="198.18.10.254",
        ),
    ]

    issues = validate_configuration_actions(actions)
    codes = {issue.code for issue in issues}

    assert ConfigurationIssueCode.DUPLICATE_IPV4 in codes
    assert ConfigurationIssueCode.DHCP_STATIC_COLLISION in codes


def test_trusted_renderer_batches_typed_actions_and_sanitizes_vlan_names():
    plan = _compile().plan
    switch_actions = plan.actions_for_device("sw-access")

    payloads = PacketTracerIosRenderer().render_device_batches(
        device_name="__MCP_E5_ACCESS",
        model="2960-24TT",
        actions=switch_actions,
    )
    rendered = "\n".join(batch.ios_payload for batch in payloads)

    assert len(payloads) == 2
    assert "vlan 10" in rendered
    assert "switchport access vlan 10" in rendered
    assert "switchport voice vlan 20" in rendered
    assert "switchport trunk allowed vlan 10,20" in rendered
    assert all("configureIosDevice" in batch.js_call for batch in payloads)
    assert all("\n" not in batch.js_call for batch in payloads)

    hostile = CreateVlan(
        id="hostile", phase=ConfigurationPhase.L2_DEFINITIONS,
        device_id="sw", device_name="SW", site_id="hq", vlan_id=30,
        name="USERS\nend\nreload",
    )
    safe = PacketTracerIosRenderer().render_device_batches("SW", "2960-24TT", [hostile])
    assert "\nend\nreload" not in safe[0].ios_payload


def test_renderer_rejects_an_interface_that_could_inject_ios_commands():
    hostile = ConfigureAccessPort(
        id="bad-port", phase=ConfigurationPhase.L2_INTERFACES,
        device_id="sw", device_name="SW", site_id="hq",
        interface="FastEthernet0/1\nshutdown", data_vlan_id=10,
    )

    with pytest.raises(ValueError):
        PacketTracerIosRenderer().render_device_batches("SW", "2960-24TT", [hostile])


def test_compact_summary_omits_actions_and_compilation_stays_interactive():
    started = perf_counter()
    result = _compile()
    elapsed = perf_counter() - started
    summary = result.compact_summary()

    assert "actions" not in summary
    assert summary["source_topology_hash"] == "e4-source-hash"
    assert summary["action_count"] == len(result.plan.actions)
    assert elapsed < 1.0


def test_configuration_compilation_stays_interactive_for_137_device_topology():
    segment = NetworkSegment(
        name="large-data",
        role=SegmentRole.DATA,
        site="large",
        host_requirement=131,
        dhcp=False,
        vlan_id=910,
    )
    allocation = _allocation("large-data", "198.18.160.0", "198.18.160.1")
    allocation.required_hosts = 131
    enterprise = EnterprisePlan(
        id="ent-large-137",
        name="Large 137",
        address_space="198.18.0.0/15",
        sites=[SitePlan(
            name="Large",
            site_id="large",
            type=SiteType.HQ,
            segments=[segment],
        )],
        addressing=AddressingPlan(
            address_space=AddressSpace(network="198.18.0.0/15"),
            allocations=[allocation],
        ),
    )
    switches = [
        DevicePlan(
            id=f"sw-{index:02d}",
            name=f"LARGE-SW-{index:02d}",
            model="2960-24TT",
            category="switch",
            enterprise_role="access_switch",
            site_id="large",
            network_layer="access",
        )
        for index in range(1, 7)
    ]
    endpoints = [
        DevicePlan(
            id=f"pc-{index:03d}",
            name=f"LARGE-PC-{index:03d}",
            model="PC-PT",
            category="pc",
            enterprise_role="user_pc",
            site_id="large",
            metadata={"addressing_preference": "static"},
        )
        for index in range(1, 132)
    ]
    links = []
    switch_port_counts = [0] * len(switches)
    for index, endpoint in enumerate(endpoints):
        switch_index = index % len(switches)
        switch_port_counts[switch_index] += 1
        switch = switches[switch_index]
        links.append(LinkPlan(
            id=f"access-{endpoint.id}",
            device_a=switch.name,
            device_a_id=switch.id,
            port_a=f"FastEthernet0/{switch_port_counts[switch_index]}",
            device_b=endpoint.name,
            device_b_id=endpoint.id,
            port_b="FastEthernet0",
            link_role="endpoint_access",
        ))
    for index, (left, right) in enumerate(zip(switches, switches[1:]), start=1):
        links.append(LinkPlan(
            id=f"uplink-{index:02d}",
            device_a=left.name,
            device_a_id=left.id,
            port_a="GigabitEthernet0/2",
            device_b=right.name,
            device_b_id=right.id,
            port_b="GigabitEthernet0/1",
            link_role="access_uplink",
        ))
    topology = TopologyPlan(
        id="topology-large-137",
        name="Large 137 physical",
        semantic_hash="large-e4-hash",
        devices=[*switches, *endpoints],
        links=links,
    )

    started = perf_counter()
    result = compile_enterprise_configuration(
        enterprise, topology, ConfigurationPolicy(),
    )
    elapsed = perf_counter() - started

    assert result.is_valid
    assert result.plan is not None
    assert len(topology.devices) == 137
    assert len(result.plan.devices) == 137
    assert len(result.plan.actions_of_type(ConfigurationActionType.CREATE_VLAN)) == 6
    assert len(result.plan.actions_of_type(ConfigurationActionType.CONFIGURE_ACCESS_PORT)) == 131
    assert len(result.plan.actions_of_type(ConfigurationActionType.CONFIGURE_TRUNK)) == 10
    assert len(result.plan.actions_of_type(ConfigurationActionType.SET_ENDPOINT_STATIC)) == 131
    assert elapsed < 2.0
