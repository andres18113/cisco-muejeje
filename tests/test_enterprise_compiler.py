"""E4 offline: expansión, cableado, layout y determinismo Enterprise."""

from __future__ import annotations

from time import perf_counter

import pytest

from src.packet_tracer_mcp.application.use_cases.compile_enterprise import compile_enterprise_topology
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    DeviceCapabilities,
)
from src.packet_tracer_mcp.domain.enterprise.models.compilation import (
    CompilationIssueCode,
    ConcreteLinkRole,
    LayoutProfile,
)
from src.packet_tracer_mcp.domain.enterprise.models.hardware import (
    HardwareCandidate,
    HardwarePlanStatus,
    HierarchyMode,
    NormalizedPortSpeed,
    PortClass,
    PortDescriptor,
)
from src.packet_tracer_mcp.domain.enterprise.models.hierarchy import (
    BuildingIntent,
    EndpointGroup,
    FloorIntent,
    ZoneIntent,
)
from src.packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent, SiteIntent, SiteType
from src.packet_tracer_mcp.domain.enterprise.models.requirements import EndpointRequirement
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import EnterpriseDesigner
from src.packet_tracer_mcp.domain.enterprise.services.hardware_planner import HardwarePlanner
from src.packet_tracer_mcp.domain.enterprise.services.layout_planner import LayoutPlanner
from src.packet_tracer_mcp.domain.enterprise.services.naming import DeterministicNamingService
from src.packet_tracer_mcp.domain.enterprise.services.physical_ports import (
    is_logical_interface,
    natural_interface_key,
    physical_ports,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_topology import (
    PacketTracerTopologyCatalogAdapter,
)


def _requirement(
    role: DeviceRole,
    count: int,
    *,
    poe: bool = False,
    wired: bool = True,
    wireless: bool = False,
) -> EndpointRequirement:
    return EndpointRequirement(
        role=role,
        count=count,
        requires_poe=poe,
        wired=wired,
        wireless=wireless,
    )


def _candidate(
    *,
    access: int = 24,
    uplinks: int = 2,
    poe: CapabilityStatus = CapabilityStatus.SUPPORTED,
    layer3: CapabilityStatus = CapabilityStatus.SUPPORTED,
) -> HardwareCandidate:
    ports = [
        PortDescriptor(
            name=f"FastEthernet0/{index}",
            classes=[PortClass.ACCESS_CAPABLE],
            speed=NormalizedPortSpeed.SPEED_100M,
        )
        for index in range(1, access + 1)
    ] + [
        PortDescriptor(
            name=f"GigabitEthernet0/{index}",
            classes=[PortClass.UPLINK_CAPABLE],
            speed=NormalizedPortSpeed.SPEED_1G,
        )
        for index in range(1, uplinks + 1)
    ]
    return HardwareCandidate(
        model="2960-24TT",
        capabilities=DeviceCapabilities(
            model="2960-24TT",
            category="switch",
            fastethernet_ports=access,
            gigabit_ports=uplinks,
            port_count=access + uplinks,
            supports_poe=poe,
            poe_ports=24 if poe is CapabilityStatus.SUPPORTED else None,
            layer3=layer3,
        ),
        ports=ports,
    )


def _reference_intent(*, growth: float = 0.30) -> EnterpriseIntent:
    requirements = [
        _requirement(DeviceRole.USER_PC, 30),
        _requirement(DeviceRole.IP_PHONE, 30, poe=True),
        _requirement(DeviceRole.IP_CAMERA, 8, poe=True),
        _requirement(DeviceRole.PRINTER, 4),
        _requirement(DeviceRole.ACCESS_POINT, 3, poe=True),
    ]
    return EnterpriseIntent(
        name="Artefacta",
        default_growth_percent=growth,
        sites=[SiteIntent(
            name="Matriz",
            type=SiteType.HQ,
            buildings=[BuildingIntent(name="A", floors=[FloorIntent(
                name="1",
                zones=[ZoneIntent(
                    name="Ventas",
                    endpoint_groups=[EndpointGroup(name="Ventas", requirements=requirements)],
                )],
            )])],
        )],
    )


def _design(intent: EnterpriseIntent):
    designed = EnterpriseDesigner().design(intent)
    assert designed.validation.is_valid, designed.validation.error_messages()
    assert designed.plan is not None
    return designed.plan


def _compile(intent: EnterpriseIntent, *, candidate: HardwareCandidate | None = None):
    enterprise = _design(intent)
    hardware = HardwarePlanner().plan(enterprise, [candidate or _candidate()])
    catalog = PacketTracerTopologyCatalogAdapter()
    result = compile_enterprise_topology(
        enterprise,
        hardware,
        catalog.compilation_profile(),
        catalog.cable_for,
    )
    return enterprise, hardware, result


def _reference():
    enterprise, hardware, result = _compile(_reference_intent())
    assert result.is_valid, [issue.model_dump(mode="json") for issue in result.issues]
    assert result.plan is not None
    return enterprise, hardware, result


def _legacy_non_wan_identity_reference():
    """Preserva la entrada exacta del hash v2 anterior al gate de estado E4."""
    enterprise = _design(_reference_intent())
    partial = HardwarePlanner().plan(enterprise, [_candidate(
        poe=CapabilityStatus.UNKNOWN,
        layer3=CapabilityStatus.UNKNOWN,
    )])
    assert partial.status is HardwarePlanStatus.PARTIALLY_RESOLVED
    catalog = PacketTracerTopologyCatalogAdapter()
    rejected = compile_enterprise_topology(
        enterprise, partial, catalog.compilation_profile(), catalog.cable_for,
    )
    assert rejected.plan is None
    # El pin pertenece a la identidad del artefacto histórico, no autoriza a
    # producción a compilar el HardwarePlan parcial que lo originó.
    identity_input = partial.model_copy(update={"status": HardwarePlanStatus.VALID})
    result = compile_enterprise_topology(
        enterprise, identity_input, catalog.compilation_profile(), catalog.cable_for,
    )
    assert result.is_valid and result.plan is not None
    return result


def test_natural_interface_order_and_logical_interface_exclusion():
    ports = ["Fa0/10", "Fa0/2", "Fa0/1", "Fa0/24", "Fa0/9"]

    assert sorted(ports, key=natural_interface_key) == ["Fa0/1", "Fa0/2", "Fa0/9", "Fa0/10", "Fa0/24"]
    assert all(is_logical_interface(name) for name in ["Vlan1", "Loopback0", "Tunnel1", "Port-channel2", "BVI1"])
    assert not is_logical_interface("GigabitEthernet0/1")
    assert [port.name for port in physical_ports([
        PortDescriptor(name="Vlan1", physical=False, classes=[PortClass.ACCESS_CAPABLE]),
        PortDescriptor(name="FastEthernet0/2", classes=[PortClass.ACCESS_CAPABLE]),
    ])] == ["FastEthernet0/2"]


def test_reference_expands_actual_endpoints_without_growth_phantoms():
    enterprise, hardware, result = _reference()

    assert enterprise.compact_summary()["required_access_ports"] == 59
    assert hardware.compact_summary()["planned_poe_ports"] == 54
    assert result.summary.endpoints == 75
    assert result.summary.endpoints_by_role == {
        "access_point": 3,
        "ip_camera": 8,
        "ip_phone": 30,
        "printer": 4,
        "user_pc": 30,
    }
    assert all(device.metadata.get("growth_reserve") == "false" for device in result.plan.devices if not device.network_layer)


def test_reference_phone_passthrough_uses_one_switch_port_per_pair():
    _, _, result = _reference()
    plan = result.plan

    assert result.summary.endpoint_access_links == 45
    assert result.summary.phone_passthrough_links == 30
    passthrough = [link for link in plan.links if link.link_role == ConcreteLinkRole.PHONE_PASSTHROUGH.value]
    assert all(link.port_a == "PC" and link.port_b == "FastEthernet0" for link in passthrough)
    phone_access = [
        link for link in plan.links
        if link.link_role == ConcreteLinkRole.ENDPOINT_ACCESS.value
        and plan.device_by_name(link.device_b).enterprise_role == DeviceRole.IP_PHONE.value
    ]
    assert len(phone_access) == 30
    assert all(link.port_b == "Switch" for link in phone_access)


def test_packet_tracer_901_phone_profile_uses_runtime_physical_port_names():
    profile = PacketTracerTopologyCatalogAdapter().compilation_profile()
    phone = profile.model_by_name("7960")

    assert phone is not None
    assert phone.physical_ports == ["Switch", "PC"]
    assert phone.network_port == "Switch"
    assert phone.passthrough_port == "PC"


def test_reference_preserves_hardware_redundancy_and_exact_link_counts():
    _, _, result = _reference()

    assert result.summary.network_devices == 6
    assert result.summary.infrastructure_links == 8
    assert result.summary.links == 83
    redundant = [link for link in result.plan.links if link.redundancy_group]
    assert len(redundant) == 6
    assert len({link.redundancy_group for link in redundant}) == 3


def test_uplinks_are_reserved_before_access_ports_and_ports_never_collide():
    _, _, result = _reference()
    used: set[tuple[str, str]] = set()

    for link in result.plan.links:
        for endpoint in ((link.device_a_id, link.port_a), (link.device_b_id, link.port_b)):
            assert endpoint not in used
            used.add(endpoint)
            assert not is_logical_interface(endpoint[1])
    access_uplinks = [
        link for link in result.plan.links
        if link.link_role == ConcreteLinkRole.ACCESS_UPLINK.value
        and link.device_a_id.startswith("sw-acc-")
    ]
    assert all(link.port_a.startswith("GigabitEthernet") for link in access_uplinks)


def test_compile_is_identical_ten_times_including_hash_ports_and_coordinates():
    enterprise = _design(_reference_intent())
    hardware = HardwarePlanner().plan(enterprise, [_candidate()])
    catalog = PacketTracerTopologyCatalogAdapter()

    results = [
        compile_enterprise_topology(enterprise, hardware, catalog.compilation_profile(), catalog.cable_for)
        for _ in range(10)
    ]

    assert all(result.is_valid for result in results)
    assert len({result.semantic_hash for result in results}) == 1
    serialized = [result.plan.model_dump(mode="json") for result in results]
    assert all(item == serialized[0] for item in serialized)


def test_semantically_unordered_inputs_do_not_change_compilation():
    enterprise = _design(_reference_intent())
    hardware = HardwarePlanner().plan(enterprise, [_candidate()])
    catalog = PacketTracerTopologyCatalogAdapter()
    original = compile_enterprise_topology(enterprise, hardware, catalog.compilation_profile(), catalog.cable_for)

    shuffled_enterprise = enterprise.model_copy(deep=True)
    shuffled_enterprise.sites.reverse()
    zone = shuffled_enterprise.sites[0].buildings[0].floors[0].zones[0]
    zone.endpoint_groups[0].requirements.reverse()
    shuffled_hardware = hardware.model_copy(deep=True)
    shuffled_hardware.site_hardware.reverse()
    shuffled_hardware.site_hardware[0].devices.reverse()
    shuffled_hardware.site_hardware[0].links.reverse()
    shuffled_hardware.site_hardware[0].access_blocks.reverse()
    shuffled_hardware.site_hardware[0].access_blocks[0].port_assignments.reverse()
    reordered = compile_enterprise_topology(
        shuffled_enterprise, shuffled_hardware, catalog.compilation_profile(), catalog.cable_for,
    )

    assert reordered.is_valid
    assert reordered.semantic_hash == original.semantic_hash
    assert reordered.plan.model_dump(mode="json") == original.plan.model_dump(mode="json")


def test_multi_site_input_order_is_semantically_irrelevant():
    intent = EnterpriseIntent(
        name="Order",
        default_growth_percent=0,
        sites=[
            SiteIntent(
                name="HQ", type=SiteType.HQ,
                endpoints=[_requirement(DeviceRole.USER_PC, 2)],
            ),
            SiteIntent(
                name="Branch", type=SiteType.BRANCH,
                endpoints=[_requirement(DeviceRole.PRINTER, 1)],
            ),
        ],
    )
    enterprise = _design(intent)
    hardware = HardwarePlanner().plan(enterprise, [_candidate()])
    catalog = PacketTracerTopologyCatalogAdapter()
    first = compile_enterprise_topology(
        enterprise, hardware, catalog.compilation_profile(), catalog.cable_for,
    )
    reordered_enterprise = enterprise.model_copy(deep=True)
    reordered_enterprise.sites.reverse()
    reordered_hardware = hardware.model_copy(deep=True)
    reordered_hardware.site_hardware.reverse()
    second = compile_enterprise_topology(
        reordered_enterprise, reordered_hardware,
        catalog.compilation_profile(), catalog.cable_for,
    )

    assert first.is_valid and second.is_valid
    assert first.semantic_hash == second.semantic_hash
    assert first.plan.model_dump(mode="json") == second.plan.model_dump(mode="json")


def test_unresolved_network_or_endpoint_model_fails_without_partial_plan():
    enterprise = _design(_reference_intent(growth=0))
    hardware = HardwarePlanner().plan(enterprise, [_candidate(poe=CapabilityStatus.SUPPORTED)])
    hardware.site_hardware[0].devices[0].selected_model = None
    hardware.site_hardware[0].devices[0].provisional_model = None
    catalog = PacketTracerTopologyCatalogAdapter()

    unresolved_network = compile_enterprise_topology(
        enterprise, hardware, catalog.compilation_profile(), catalog.cable_for,
    )
    profile = catalog.compilation_profile()
    del profile.endpoint_role_models[DeviceRole.PRINTER]
    unresolved_endpoint = compile_enterprise_topology(
        enterprise, HardwarePlanner().plan(enterprise, [_candidate()]), profile, catalog.cable_for,
    )

    assert unresolved_network.plan is None
    assert unresolved_endpoint.plan is None
    assert CompilationIssueCode.MODEL_SELECTION_UNRESOLVED in {issue.code for issue in unresolved_network.issues}
    assert CompilationIssueCode.ENDPOINT_MODEL_UNRESOLVED in {issue.code for issue in unresolved_endpoint.issues}


def test_physical_port_exhaustion_is_a_hard_error_and_drops_no_endpoint_silently():
    enterprise = _design(_reference_intent())
    hardware = HardwarePlanner().plan(enterprise, [_candidate()])
    access = next(device for device in hardware.site_hardware[0].devices if device.role is DeviceRole.ACCESS_SWITCH)
    access.port_descriptors = [
        port for port in access.port_descriptors if PortClass.UPLINK_CAPABLE in port.classes
    ]
    catalog = PacketTracerTopologyCatalogAdapter()

    result = compile_enterprise_topology(enterprise, hardware, catalog.compilation_profile(), catalog.cable_for)

    assert result.plan is None
    assert result.summary.endpoints == 75
    assert CompilationIssueCode.INSUFFICIENT_PHYSICAL_PORT_CAPACITY in {issue.code for issue in result.issues}


def test_logical_explicit_uplink_is_rejected_as_a_hard_invariant():
    enterprise = _design(_reference_intent())
    hardware = HardwarePlanner().plan(enterprise, [_candidate()])
    hardware.site_hardware[0].links[0].source_port = "Vlan1"
    catalog = PacketTracerTopologyCatalogAdapter()

    result = compile_enterprise_topology(enterprise, hardware, catalog.compilation_profile(), catalog.cable_for)

    assert result.plan is None
    assert CompilationIssueCode.LOGICAL_PORT_SELECTED in {issue.code for issue in result.issues}


def test_duplicate_hardware_id_fails_loudly():
    enterprise = _design(_reference_intent())
    hardware = HardwarePlanner().plan(enterprise, [_candidate()])
    hardware.site_hardware[0].devices.append(hardware.site_hardware[0].devices[0].model_copy(deep=True))
    catalog = PacketTracerTopologyCatalogAdapter()

    result = compile_enterprise_topology(enterprise, hardware, catalog.compilation_profile(), catalog.cable_for)

    assert result.plan is None
    assert CompilationIssueCode.DUPLICATE_DEVICE_ID in {issue.code for issue in result.issues}


@pytest.mark.parametrize(
    ("pc_count", "expected_mode"),
    [(5, HierarchyMode.FLAT), (30, HierarchyMode.COLLAPSED_CORE), (60, HierarchyMode.THREE_TIER)],
)
def test_existing_flat_collapsed_and_three_tier_hardware_modes_compile(
    pc_count: int, expected_mode: HierarchyMode,
):
    intent = EnterpriseIntent(
        name=f"Mode-{pc_count}",
        default_growth_percent=0,
        sites=[SiteIntent(
            name="HQ",
            type=SiteType.HQ,
            endpoints=[_requirement(DeviceRole.USER_PC, pc_count)],
        )],
    )

    _, hardware, result = _compile(intent)

    assert hardware.site_hardware[0].hierarchy_mode is expected_mode
    assert result.is_valid
    assert result.summary.endpoints == pc_count


def test_multi_building_floor_zone_and_site_regions_are_preserved_without_overlap():
    intent = EnterpriseIntent(
        name="Regional",
        default_growth_percent=0,
        sites=[
            SiteIntent(
                name="HQ",
                type=SiteType.HQ,
                buildings=[
                    BuildingIntent(name="North", floors=[FloorIntent(name="1", zones=[ZoneIntent(
                        name="Sales", endpoint_groups=[EndpointGroup(
                            name="sales", requirements=[_requirement(DeviceRole.USER_PC, 2)],
                        )],
                    )])]),
                    BuildingIntent(name="South", floors=[FloorIntent(name="2", zones=[ZoneIntent(
                        name="Ops", endpoint_groups=[EndpointGroup(
                            name="ops", requirements=[_requirement(DeviceRole.PRINTER, 2)],
                        )],
                    )])]),
                ],
            ),
            SiteIntent(
                name="Branch",
                type=SiteType.BRANCH,
                endpoints=[_requirement(DeviceRole.USER_PC, 2)],
            ),
        ],
    )

    _, _, result = _compile(intent)

    assert result.is_valid
    assert {region.kind for region in result.layout_regions} >= {"site", "building", "floor", "zone"}
    sites = sorted((region for region in result.layout_regions if region.kind == "site"), key=lambda item: item.x)
    assert len(sites) == 2
    assert sites[0].x + sites[0].width < sites[1].x
    assert all(device.site_id and device.zone_id for device in result.plan.devices if not device.network_layer)
    assert all(device.building_id and device.floor_id for device in result.plan.devices if device.site_id == "hq" and not device.network_layer)


def test_layout_is_deterministic_unique_and_changes_only_with_explicit_profile():
    enterprise = _design(_reference_intent())
    hardware = HardwarePlanner().plan(enterprise, [_candidate()])
    catalog = PacketTracerTopologyCatalogAdapter()
    first = compile_enterprise_topology(enterprise, hardware, catalog.compilation_profile(), catalog.cable_for)
    second = compile_enterprise_topology(enterprise, hardware, catalog.compilation_profile(), catalog.cable_for)
    wider = compile_enterprise_topology(
        enterprise,
        hardware,
        catalog.compilation_profile(),
        catalog.cable_for,
        LayoutProfile(horizontal_spacing=180),
    )

    coordinates = [(device.x, device.y) for device in first.plan.devices]
    assert len(coordinates) == len(set(coordinates))
    assert [(device.id, device.x, device.y) for device in first.plan.devices] == [
        (device.id, device.x, device.y) for device in second.plan.devices
    ]
    assert first.semantic_hash == second.semantic_hash
    assert wider.semantic_hash != first.semantic_hash


@pytest.mark.parametrize("count", [1, 2, 3, 4])
def test_site_infrastructure_rows_are_centered_for_even_and_odd_counts(count: int):
    devices = [
        DevicePlan(
            id=f"core-{index:02d}",
            name=f"CORE-{index:02d}",
            model="2911",
            category="router",
            site_id="hq",
            network_layer="core",
        )
        for index in range(1, count + 1)
    ]

    LayoutPlanner._place_site_infrastructure(
        devices,
        site_x=100,
        site_width=1000,
        profile=LayoutProfile(horizontal_spacing=100),
        links=[],
    )

    coordinates = sorted(device.x for device in devices)
    assert coordinates[0] + coordinates[-1] == 1200


def test_site_infrastructure_compresses_dense_rows_inside_padded_site_bounds():
    devices = [
        DevicePlan(
            id=f"distribution-{index:02d}",
            name=f"DIST-{index:02d}",
            model="3560-24PS",
            category="switch",
            site_id="hq",
            network_layer="distribution",
        )
        for index in range(1, 13)
    ]

    LayoutPlanner._place_site_infrastructure(
        devices,
        site_x=100,
        site_width=1000,
        profile=LayoutProfile(horizontal_spacing=100),
        links=[],
    )

    coordinates = sorted(device.x for device in devices)
    assert coordinates[0] == 200
    assert coordinates[-1] == 1000
    assert coordinates[0] + coordinates[-1] == 1200


def test_site_infrastructure_orders_each_lower_layer_by_upstream_connections():
    devices = [
        DevicePlan(
            id="core-a",
            name="CORE-A",
            model="2911",
            category="router",
            site_id="hq",
            network_layer="core",
        ),
        DevicePlan(
            id="core-b",
            name="CORE-B",
            model="2911",
            category="router",
            site_id="hq",
            network_layer="core",
        ),
        DevicePlan(
            id="distribution-a",
            name="DIST-RIGHT",
            model="3560-24PS",
            category="switch",
            site_id="hq",
            network_layer="distribution",
        ),
        DevicePlan(
            id="distribution-z",
            name="DIST-LEFT",
            model="3560-24PS",
            category="switch",
            site_id="hq",
            network_layer="distribution",
        ),
    ]
    links = [
        LinkPlan(
            id="left",
            device_a="CORE-A",
            device_a_id="core-a",
            port_a="GigabitEthernet0/0",
            device_b="DIST-LEFT",
            device_b_id="distribution-z",
            port_b="GigabitEthernet0/1",
        ),
        LinkPlan(
            id="right",
            device_a="CORE-B",
            device_a_id="core-b",
            port_a="GigabitEthernet0/0",
            device_b="DIST-RIGHT",
            device_b_id="distribution-a",
            port_b="GigabitEthernet0/1",
        ),
    ]

    laid_out, _ = LayoutPlanner().plan(
        TopologyPlan(name="connection-aware", devices=devices, links=links),
        LayoutProfile(horizontal_spacing=100),
    )
    by_id = {device.id: device for device in laid_out.devices}

    assert by_id["distribution-z"].x < by_id["distribution-a"].x
    assert by_id["distribution-z"].x == by_id["core-a"].x
    assert by_id["distribution-a"].x == by_id["core-b"].x


def test_catalog_cable_policy_is_used_and_e5_configuration_remains_empty():
    _, _, result = _reference()
    plan = result.plan
    infrastructure = [link for link in plan.links if link.link_role == ConcreteLinkRole.CORE_LINK.value]
    passthrough = [link for link in plan.links if link.link_role == ConcreteLinkRole.PHONE_PASSTHROUGH.value]

    assert infrastructure and all(link.cable == "cross" for link in infrastructure)
    assert passthrough and all(link.cable == "straight" for link in passthrough)
    assert not plan.vlans and not plan.trunks and not plan.dhcp_pools
    assert not plan.static_routes and not plan.ospf_configs and not plan.eigrp_configs


def test_resolved_reference_keeps_only_non_blocking_e4_runtime_warnings():
    _, hardware, result = _reference()
    codes = {issue.code for issue in result.issues}

    assert hardware.status is HardwarePlanStatus.VALID
    assert result.is_valid
    assert CompilationIssueCode.POE_CAPABILITY_UNKNOWN not in codes
    assert CompilationIssueCode.ENDPOINT_MODEL_GENERIC in codes
    assert CompilationIssueCode.LAYOUT_COORDINATE_READBACK_PARTIAL in codes
    assert sum(issue.code is CompilationIssueCode.ENDPOINT_MODEL_GENERIC for issue in result.issues) == 1


def test_compact_summary_omits_full_plan_and_semantic_hash_is_stable():
    _, _, result = _reference()
    compact = result.compact_summary()
    legacy = _legacy_non_wan_identity_reference()

    assert "plan" not in compact
    assert compact["semantic_hash"] == result.semantic_hash
    assert legacy.semantic_hash == "9a02ed7c9f2b6c8f4e334b3f17688207f44b7c213682f570febc305541e26870"
    assert result.plan is not None and result.plan.hash_schema_version == "2"
    assert legacy.plan is not None and legacy.plan.hash_schema_version == "2"
    assert compact["devices"] == 81
    assert compact["links"] == 83


def test_large_synthetic_compilation_stays_interactive():
    intent = EnterpriseIntent(
        name="Scale",
        default_growth_percent=0,
        sites=[SiteIntent(
            name="HQ",
            type=SiteType.HQ,
            endpoints=[
                _requirement(DeviceRole.USER_PC, 120),
                _requirement(DeviceRole.PRINTER, 8),
            ],
        )],
    )
    started = perf_counter()
    _, _, result = _compile(intent)
    elapsed = perf_counter() - started

    assert result.is_valid
    assert result.summary.endpoints == 128
    assert result.summary.devices > 130
    assert elapsed < 5.0


def test_naming_truncation_keeps_readable_unique_deterministic_suffixes():
    naming = DeterministicNamingService(max_length=32)
    first = naming.endpoint_name(
        "extremely-long-site", "extremely-long-building", "extremely-long-floor",
        "extremely-long-zone-a", DeviceRole.USER_PC, 1,
    )
    second = naming.endpoint_name(
        "extremely-long-site", "extremely-long-building", "extremely-long-floor",
        "extremely-long-zone-b", DeviceRole.USER_PC, 1,
    )

    assert len(first) == len(second) == 32
    assert first != second
    assert first == naming.endpoint_name(
        "extremely-long-site", "extremely-long-building", "extremely-long-floor",
        "extremely-long-zone-a", DeviceRole.USER_PC, 1,
    )


def test_explicit_deployment_namespace_is_part_of_deterministic_compilation():
    enterprise = _design(EnterpriseIntent(
        name="Smoke",
        default_growth_percent=0,
        sites=[SiteIntent(
            name="Lab", type=SiteType.BRANCH,
            endpoints=[_requirement(DeviceRole.USER_PC, 1)],
        )],
    ))
    hardware = HardwarePlanner().plan(enterprise, [_candidate()])
    catalog = PacketTracerTopologyCatalogAdapter()
    profile = catalog.compilation_profile()
    profile.device_name_prefix = "__MCP_E4_TEST_"

    first = compile_enterprise_topology(enterprise, hardware, profile, catalog.cable_for)
    second = compile_enterprise_topology(enterprise, hardware, profile, catalog.cable_for)

    assert first.is_valid
    assert all(device.name.startswith("__MCP_E4_TEST_") for device in first.plan.devices)
    assert first.semantic_hash == second.semantic_hash
