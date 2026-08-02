"""E2 offline: jerarquía, VLSM/IPAM y capacidad agregada."""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.enterprise_plan import EnterprisePlan, SitePlan
from src.packet_tracer_mcp.domain.enterprise.models.hierarchy import (
    BuildingIntent,
    EndpointGroup,
    FloorIntent,
    ZoneIntent,
)
from src.packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent, SiteIntent, SiteType
from src.packet_tracer_mcp.domain.enterprise.models.requirements import EndpointRequirement
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.models.segments import NetworkSegment, SegmentRole
from src.packet_tracer_mcp.domain.enterprise.models.topology import NetworkLayer, TopologyPattern
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import EnterpriseDesigner
from src.packet_tracer_mcp.domain.enterprise.services.ipam_planner import (
    IPAMPlanner,
    subnet_requirement_for,
)


def _requirement(role: DeviceRole, count: int, *, poe: bool = False, wired: bool = True,
                 wireless: bool = False) -> EndpointRequirement:
    return EndpointRequirement(role=role, count=count, requires_poe=poe, wired=wired, wireless=wireless)


def _large_hq(*, pair: bool | None = None, address_space: str | None = "10.0.0.0/8") -> EnterpriseIntent:
    return EnterpriseIntent(
        name="Artefacta",
        address_space=address_space,
        default_growth_percent=0.30,
        sites=[SiteIntent(
            name="Matriz-Quito",
            type=SiteType.HQ,
            pair_pc_with_ip_phone=pair,
            buildings=[BuildingIntent(
                name="Administrativo",
                floors=[FloorIntent(
                    name="Piso-1",
                    zones=[ZoneIntent(
                        name="Ventas",
                        endpoint_groups=[EndpointGroup(
                            name="Ventas-P1",
                            requirements=[
                                _requirement(DeviceRole.USER_PC, 30),
                                _requirement(DeviceRole.IP_PHONE, 30, poe=True),
                                _requirement(DeviceRole.IP_CAMERA, 8, poe=True),
                                _requirement(DeviceRole.PRINTER, 4),
                                _requirement(DeviceRole.ACCESS_POINT, 3, poe=True),
                            ],
                        )],
                    )],
                )],
            )],
        )],
    )


def _design(intent: EnterpriseIntent) -> EnterprisePlan:
    result = EnterpriseDesigner().design(intent)
    assert result.validation.is_valid, result.validation.error_messages()
    assert result.plan is not None
    return result.plan


def test_hierarchy_and_hybrid_topology_are_planned_without_coordinates():
    site = _design(_large_hq(address_space=None)).sites[0]

    assert site.buildings[0].floors[0].zones[0].zone_id == "matriz-quito/administrativo/piso-1/ventas"
    assert site.topology is not None
    assert site.topology.pattern is TopologyPattern.HYBRID
    assert site.topology.layer_patterns[NetworkLayer.ACCESS] is TopologyPattern.STAR
    assert NetworkLayer.CORE in site.topology.network_layers


def test_legacy_site_endpoints_create_an_internal_default_zone():
    site = _design(EnterpriseIntent(
        name="Legacy",
        sites=[SiteIntent(name="Sucursal", type=SiteType.BRANCH, endpoints=[_requirement(DeviceRole.USER_PC, 2)])],
    )).sites[0]

    assert site.default_zone is not None
    assert site.default_zone.name == "SITE_DEFAULT_ZONE"
    assert site.default_zone.endpoint_groups[0].requirements[0].count == 2


@pytest.mark.parametrize(
    ("raw_hosts", "growth", "required", "prefix"),
    [
        (1, 0, 2, 30),
        (2, 0, 3, 29),
        (30, 0.30, 40, 26),
        (62, 0, 63, 25),
        (63, 0, 64, 25),
        (126, 0, 127, 24),
        (127, 0, 128, 24),
    ],
)
def test_subnet_requirements_include_growth_once_and_gateway(
    raw_hosts: int, growth: float, required: int, prefix: int
):
    requirement = subnet_requirement_for("segment", raw_hosts, growth)

    assert requirement.required_usable_hosts == required
    assert requirement.prefix == prefix


def test_site_footprint_uses_consumed_subnet_blocks_not_just_usable_hosts():
    plan = _design(EnterpriseIntent(
        name="Footprint",
        address_space="10.0.0.0/16",
        default_growth_percent=0,
        sites=[SiteIntent(
            name="Quito",
            type=SiteType.HQ,
            endpoints=[
                _requirement(DeviceRole.USER_PC, 30),
                _requirement(DeviceRole.PRINTER, 14),
            ],
        )],
    ))

    assert plan.addressing is not None
    assert plan.addressing.site_blocks[0].prefix == 25  # /26 + /27 = 96 addresses -> /25
    assert [item.prefix for item in plan.addressing.allocations] == [26, 27]


def test_vlsm_returns_first_usable_gateway_and_complete_subnet_metadata():
    plan = _design(_large_hq())
    assert plan.addressing is not None
    data = next(item for item in plan.addressing.allocations if item.segment_id.endswith("-data"))

    assert data.network == "10.0.0.0"
    assert data.prefix == 26
    assert data.netmask == "255.255.255.192"
    assert data.gateway == data.first_usable == "10.0.0.1"
    assert data.last_usable == "10.0.0.62"
    assert data.broadcast == "10.0.0.63"


def test_ipam_is_deterministic_and_allocates_summarizable_site_blocks():
    first = _design(_large_hq())
    second = _design(_large_hq())

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.addressing is not None
    assert first.addressing.site_blocks[0].network == "10.0.0.0"
    assert first.addressing.site_blocks[0].prefix == 24


def test_automatic_site_blocks_are_non_overlapping_and_largest_first():
    plan = _design(EnterpriseIntent(
        name="Multi-site",
        address_space="10.0.0.0/16",
        default_growth_percent=0,
        sites=[
            SiteIntent(name="Small", type=SiteType.BRANCH, endpoints=[_requirement(DeviceRole.USER_PC, 2)]),
            SiteIntent(name="Large", type=SiteType.HQ, endpoints=[_requirement(DeviceRole.USER_PC, 60)]),
        ],
    ))

    assert plan.addressing is not None
    blocks = {block.site_id: block for block in plan.addressing.site_blocks}
    assert blocks["large"].prefix < blocks["small"].prefix
    assert blocks["large"].network == "10.0.0.0"
    assert blocks["small"].network != blocks["large"].network


def test_explicit_site_block_is_retained_and_too_small_block_is_rejected():
    valid = _design(EnterpriseIntent(
        name="Explicit",
        address_space="10.0.0.0/16",
        default_growth_percent=0,
        sites=[SiteIntent(name="Quito", type=SiteType.BRANCH, address_block="10.0.20.0/24", endpoints=[_requirement(DeviceRole.USER_PC, 30)])],
    ))
    assert valid.addressing is not None
    assert valid.addressing.site_blocks[0].network == "10.0.20.0"
    assert valid.addressing.site_blocks[0].explicit

    result = EnterpriseDesigner().design(EnterpriseIntent(
        name="Too small",
        address_space="10.0.0.0/16",
        default_growth_percent=0,
        sites=[SiteIntent(name="Quito", type=SiteType.BRANCH, address_block="10.0.20.0/27", endpoints=[_requirement(DeviceRole.USER_PC, 30)])],
    ))
    assert not result.validation.is_valid
    assert result.validation.errors[-1].code.value == "SITE_ADDRESS_SPACE_TOO_SMALL"


def test_overlapping_explicit_site_blocks_are_rejected():
    result = EnterpriseDesigner().design(EnterpriseIntent(
        name="Overlap",
        address_space="10.0.0.0/16",
        sites=[
            SiteIntent(name="A", type=SiteType.BRANCH, address_block="10.0.0.0/24"),
            SiteIntent(name="B", type=SiteType.BRANCH, address_block="10.0.0.128/25"),
        ],
    ))

    assert not result.validation.is_valid
    assert any(error.code.value == "SITE_ADDRESS_SPACE_OVERLAP" for error in result.validation.errors)


def test_site_block_outside_enterprise_and_invalid_address_space_are_rejected():
    outside = EnterpriseDesigner().design(EnterpriseIntent(
        name="Outside",
        address_space="10.0.0.0/16",
        sites=[SiteIntent(name="Quito", type=SiteType.BRANCH, address_block="10.1.0.0/24")],
    ))
    invalid = EnterpriseDesigner().design(EnterpriseIntent(
        name="Invalid",
        address_space="not-a-network",
        sites=[SiteIntent(name="Quito", type=SiteType.BRANCH)],
    ))

    assert any(error.code.value == "SITE_ADDRESS_SPACE_OUTSIDE_ENTERPRISE" for error in outside.validation.errors)
    assert any(error.code.value == "ENTERPRISE_ADDRESS_SPACE_INVALID" for error in invalid.validation.errors)


def test_segment_growth_override_has_precedence_over_site_growth():
    plan = EnterprisePlan(
        id="ent_growth",
        name="Growth",
        address_space="10.0.0.0/24",
        sites=[SitePlan(
            name="Quito",
            site_id="quito",
            type=SiteType.HQ,
            growth_percent=0.50,
            segments=[NetworkSegment(
                name="quito-data", site="quito", role=SegmentRole.DATA,
                host_requirement=30, growth_percent=0.30,
            )],
        )],
    )

    result = IPAMPlanner().plan(plan)
    assert result.validation.is_valid
    assert result.plan is not None
    allocation = result.plan.allocations[0]
    assert allocation.required_hosts == 40
    assert allocation.growth_percent == 0.30


def test_capacity_models_pc_phone_passthrough_and_poe_growth():
    plan = _design(_large_hq(address_space=None))
    capacity = plan.sites[0].capacity_requirements[0]

    assert capacity.raw_wired_endpoints == 75
    assert capacity.pc_phone_pairs == 30
    assert capacity.base_access_ports == 45
    assert capacity.base_poe_ports == 41
    assert capacity.required_access_ports == 59
    assert capacity.required_poe_ports == 54
    assert capacity.required_uplink_ports == 2
    assert plan.compact_summary() == {
        "enterprise": "Artefacta",
        "sites": 1,
        "logical_endpoints": 75,
        "segments": 5,
        "required_access_ports": 59,
        "required_poe_ports": 54,
    }


def test_capacity_pairing_can_be_disabled():
    capacity = _design(_large_hq(pair=False, address_space=None)).sites[0].capacity_requirements[0]

    assert capacity.pc_phone_pairs == 0
    assert capacity.base_access_ports == 75


@pytest.mark.parametrize(
    ("pcs", "phones", "expected_pairs", "expected_access"),
    [
        (5, 3, 3, 5),
        (3, 5, 3, 5),
        (4, 0, 0, 4),
    ],
)
def test_capacity_pairing_handles_unbalanced_and_absent_phones(
    pcs: int, phones: int, expected_pairs: int, expected_access: int
):
    requirements = [_requirement(DeviceRole.USER_PC, pcs)]
    if phones:
        requirements.append(_requirement(DeviceRole.IP_PHONE, phones))
    plan = _design(EnterpriseIntent(
        name="Pairing",
        default_growth_percent=0,
        sites=[SiteIntent(
            name="Branch",
            type=SiteType.BRANCH,
            buildings=[BuildingIntent(name="B", floors=[FloorIntent(name="1", zones=[ZoneIntent(
                name="Z", endpoint_groups=[EndpointGroup(name="G", requirements=requirements)]
            )])])],
        )],
    ))

    capacity = plan.sites[0].capacity_requirements[0]
    assert capacity.pc_phone_pairs == expected_pairs
    assert capacity.base_access_ports == expected_access
    assert capacity.base_poe_ports == 0


def test_wireless_clients_do_not_consume_direct_access_ports_but_access_points_do():
    plan = _design(EnterpriseIntent(
        name="Wireless",
        default_growth_percent=0,
        sites=[SiteIntent(
            name="Bodega",
            type=SiteType.WAREHOUSE,
            buildings=[BuildingIntent(name="B", floors=[FloorIntent(name="1", zones=[ZoneIntent(
                name="WiFi",
                endpoint_groups=[EndpointGroup(name="clients", requirements=[
                    _requirement(DeviceRole.LAPTOP, 20, wired=False, wireless=True),
                    _requirement(DeviceRole.ACCESS_POINT, 2, poe=True),
                ])],
            )])])],
        )],
    ))

    capacity = plan.sites[0].capacity_requirements[0]
    assert capacity.raw_wired_endpoints == 2
    assert capacity.base_access_ports == 2
    assert capacity.base_poe_ports == 2
    assert {segment.role for segment in plan.sites[0].segments} == {SegmentRole.MANAGEMENT, SegmentRole.WIRELESS_CORPORATE}


def test_empty_site_is_plannable_without_endpoint_expansion():
    plan = _design(EnterpriseIntent(
        name="Empty",
        address_space="10.0.0.0/24",
        sites=[SiteIntent(name="Warehouse", type=SiteType.WAREHOUSE)],
    ))

    assert plan.sites[0].capacity_requirements == []
    assert plan.addressing is not None
    assert plan.addressing.site_blocks == []


def test_duplicate_hierarchy_names_are_rejected():
    result = EnterpriseDesigner().design(EnterpriseIntent(
        name="Duplicate",
        sites=[SiteIntent(
            name="Quito",
            type=SiteType.HQ,
            buildings=[
                BuildingIntent(name="A"),
                BuildingIntent(name="a"),
            ],
        )],
    ))

    assert not result.validation.is_valid
    assert any(error.code.value == "ENTERPRISE_DUPLICATE_HIERARCHY_ID" for error in result.validation.errors)
