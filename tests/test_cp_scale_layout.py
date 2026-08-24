"""CP-SCALE authoritative offline compilation and layout metrics."""

from __future__ import annotations

import ipaddress
from itertools import combinations

from src.packet_tracer_mcp.application.use_cases.compile_enterprise import (
    compile_enterprise_topology,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.compilation import LayoutProfile
from src.packet_tracer_mcp.domain.enterprise.models.hardware import HardwarePlanStatus
from src.packet_tracer_mcp.domain.enterprise.scenarios.cp_scale import (
    cp_scale_scale_fixture_intent,
)
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import (
    EnterpriseDesigner,
)
from src.packet_tracer_mcp.domain.enterprise.services.hardware_planner import (
    HardwarePlanner,
)
from src.packet_tracer_mcp.domain.enterprise.services.layout_metrics import (
    LayoutMetricsEvaluator,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_topology import (
    PacketTracerTopologyCatalogAdapter,
)


_LAYOUT = LayoutProfile(canvas_width=16_000, canvas_height=8_000)


def _compile():
    designed = EnterpriseDesigner().design(cp_scale_scale_fixture_intent())
    assert designed.validation.is_valid and designed.plan is not None
    catalog = EnterpriseCapabilityAdapter()
    switch = next(
        item for item in catalog.hardware_candidates("switch")
        if item.model == "2960-24TT"
    )
    switch = switch.model_copy(update={
        "capabilities": switch.capabilities.model_copy(update={
            "supports_poe": CapabilityStatus.SUPPORTED,
            "poe_ports": 24,
            "layer3": CapabilityStatus.SUPPORTED,
        }),
    })
    router = next(
        item for item in catalog.hardware_candidates("router")
        if item.model == "2911"
    )
    hardware = HardwarePlanner().plan(designed.plan, [switch], [router])
    physical = PacketTracerTopologyCatalogAdapter()
    compiled = compile_enterprise_topology(
        designed.plan,
        hardware,
        physical.compilation_profile(),
        physical.cable_for,
        _LAYOUT,
    )
    return designed.plan, hardware, compiled


def _rectangles_overlap(left, right):
    return not (
        left.x + left.width <= right.x
        or right.x + right.width <= left.x
        or left.y + left.height <= right.y
        or right.y + right.height <= left.y
    )


def test_metrics_fail_closed_on_overlap_duplicate_bounds_and_missing_link_endpoint():
    topology = TopologyPlan(
        name="invalid-layout",
        devices=[
            DevicePlan(id="a", name="A", model="PC-PT", category="pc", x=5, y=5),
            DevicePlan(id="b", name="B", model="PC-PT", category="pc", x=5, y=5),
        ],
        links=[LinkPlan(
            device_a="A", device_a_id="a", port_a="FastEthernet0",
            device_b="MISSING", device_b_id="missing", port_b="FastEthernet0",
        )],
    )

    metrics = LayoutMetricsEvaluator().evaluate(
        topology, LayoutProfile(canvas_width=100, canvas_height=100),
    )

    assert not metrics.is_valid
    assert metrics.rectangle_overlaps == 1
    assert metrics.duplicate_coordinates == 1
    assert metrics.out_of_bounds_devices == 2
    assert metrics.valid_link_endpoint_percent == 50.0


def test_full_scale_compiles_279_workloads_plus_infrastructure_inside_canvas():
    enterprise, hardware, compiled = _compile()

    assert hardware.status is HardwarePlanStatus.VALID
    assert compiled.is_valid and compiled.plan is not None
    assert compiled.summary.workload_endpoints == 279
    assert compiled.summary.access_points == 17
    assert compiled.summary.endpoints == 296
    assert compiled.summary.devices > 300
    assert compiled.layout_metrics.is_valid
    assert compiled.layout_metrics.rectangle_overlaps == 0
    assert compiled.layout_metrics.duplicate_coordinates == 0
    assert compiled.layout_metrics.out_of_bounds_devices == 0
    assert compiled.layout_metrics.valid_link_endpoint_percent == 100.0
    assert compiled.layout_metrics.site_ownership_violations == 0
    assert compiled.layout_metrics.cluster_ownership_violations == 0
    assert compiled.layout_metrics.endpoint_group_compactness_violations == 0
    assert compiled.layout_metrics.edge_crossings >= 0
    assert compiled.layout_metrics.average_link_length > 0
    assert compiled.layout_metrics.maximum_link_length > 0
    assert compiled.layout_metrics.maximum_group_dispersion > 0

    site_regions = [item for item in compiled.layout_regions if item.kind == "site"]
    assert len(site_regions) == 3
    assert not any(
        _rectangles_overlap(left, right)
        for left, right in combinations(site_regions, 2)
    )
    assert all(
        0 <= item.x and 0 <= item.y
        and item.x + item.width <= _LAYOUT.canvas_width
        and item.y + item.height <= _LAYOUT.canvas_height
        for item in site_regions
    )

    allocations = [
        ipaddress.ip_network(f"{item.network}/{item.prefix}")
        for item in enterprise.addressing.allocations
    ]
    transits = [
        ipaddress.ip_network(f"{item.network}/{item.prefix}")
        for item in enterprise.addressing.transit_allocations
    ]
    assert len(transits) == 3 and all(item.prefixlen == 30 for item in transits)
    assert not any(left.overlaps(right) for left, right in combinations([*allocations, *transits], 2))
    assert all(
        item.usable_hosts >= item.required_hosts
        for item in enterprise.addressing.allocations
    )
    assert len(compiled.plan.modules) == 3
    assert len([item for item in compiled.plan.links if item.cable == "serial"]) == 3


def test_ten_full_rebuilds_keep_all_e4_hashes_stable():
    results = [_compile()[2] for _ in range(10)]

    assert all(item.is_valid for item in results)
    assert len({item.physical_topology_hash for item in results}) == 1
    assert len({item.layout_hash for item in results}) == 1
    assert len({item.artifact_hash for item in results}) == 1
    assert len({item.semantic_hash for item in results}) == 1
