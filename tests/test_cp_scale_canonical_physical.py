"""Canonical CP-SCALE physical design compiles exactly as documented."""

from __future__ import annotations

from collections import Counter

from src.packet_tracer_mcp.application.use_cases.compile_enterprise import (
    compile_enterprise_topology,
)
from src.packet_tracer_mcp.domain.enterprise.models.hardware import HardwarePlanStatus
from src.packet_tracer_mcp.domain.enterprise.scenarios.cp_scale import cp_scale_intent
from src.packet_tracer_mcp.domain.enterprise.scenarios.cp_scale_physical import (
    cp_scale_physical_design,
)
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import (
    EnterpriseDesigner,
)
from src.packet_tracer_mcp.domain.enterprise.services.reference_hardware_planner import (
    ReferenceHardwarePlanner,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_topology import (
    PacketTracerTopologyCatalogAdapter,
)
from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
)


def _compile():
    designed = EnterpriseDesigner().design(cp_scale_intent())
    assert designed.validation.is_valid and designed.plan is not None
    catalog = EnterpriseCapabilityAdapter()
    candidates = [
        *catalog.hardware_candidates("router", MEASURED_BACKEND_VERSION),
        *catalog.hardware_candidates("switch", MEASURED_BACKEND_VERSION),
    ]
    hardware = ReferenceHardwarePlanner().plan(
        designed.plan, cp_scale_physical_design(), candidates,
    )
    physical = PacketTracerTopologyCatalogAdapter()
    compiled = compile_enterprise_topology(
        designed.plan,
        hardware,
        physical.compilation_profile(),
        physical.cable_for,
    )
    return designed.plan, hardware, compiled


def test_canonical_hardware_uses_the_exact_18_network_devices_and_modules():
    _, hardware, _ = _compile()

    assert hardware.status is HardwarePlanStatus.VALID
    devices = [item for site in hardware.site_hardware for item in site.devices]
    assert len(devices) == 18
    assert Counter(item.selected_model for item in devices) == {
        "2811": 3,
        "2960-24TT": 10,
        "3650-24PS": 3,
        "3560-24PS": 2,
    }
    assert {item.semantic_name for item in devices} == {
        "Router0", "Router3", "Router4", "Switch10",
        "Switch0", "Switch1", "Switch3", "Switch4", "Switch5",
        "Switch6", "Switch7", "Switch8", "Switch9",
        "MLS3", "MLS4", "MLS5", "MLS6", "MLS7",
    }
    routers = [item for item in devices if item.selected_model == "2811"]
    assert all(
        [(module.module, module.slot, module.provided_ports) for module in item.module_plan]
        == [("NM-4A/S", "1", ["Serial1/0", "Serial1/1", "Serial1/2", "Serial1/3"])]
        for item in routers
    )


def test_canonical_topology_is_exactly_314_devices_and_219_links():
    _, _, compiled = _compile()

    assert compiled.is_valid, [item.model_dump(mode="json") for item in compiled.issues]
    assert compiled.plan is not None
    assert compiled.summary.devices == 314
    assert compiled.summary.network_devices == 18
    assert compiled.summary.endpoints == 296
    assert compiled.summary.workload_endpoints == 279
    assert compiled.summary.access_points == 17
    assert compiled.summary.links == 219
    assert compiled.summary.infrastructure_links == 18
    assert compiled.summary.endpoint_access_links == 199
    assert compiled.summary.phone_passthrough_links == 2
    assert "Thing" not in {item.model for item in compiled.plan.devices}
    assert Counter(item.model for item in compiled.plan.devices) == {
        "2811": 3,
        "2960-24TT": 10,
        "3650-24PS": 3,
        "3560-24PS": 2,
        "PC-PT": 104,
        "Laptop-PT": 3,
        "7960": 69,
        "Printer-PT": 8,
        "AccessPoint-PT": 17,
        "Webcam": 26,
        "Smoke Detector": 42,
        "Motion Detector": 22,
        "Humiture Monitor": 2,
        "Temperature Monitor": 3,
    }


def test_every_physical_port_is_unique_and_wireless_devices_have_no_links():
    _, _, compiled = _compile()
    assert compiled.plan is not None
    used: set[tuple[str, str]] = set()
    for link in compiled.plan.links:
        for endpoint in (
            (link.device_a_id, link.port_a),
            (link.device_b_id, link.port_b),
        ):
            assert endpoint not in used
            used.add(endpoint)

    wireless = {item.id for item in compiled.plan.devices if item.wireless}
    assert len(wireless) == 95
    assert not any(
        link.device_a_id in wireless or link.device_b_id in wireless
        for link in compiled.plan.links
    )


def test_exact_infrastructure_ports_match_the_typed_reference_design():
    _, _, compiled = _compile()
    assert compiled.plan is not None
    design = cp_scale_physical_design()
    names = {
        item.id: item.semantic_name
        for site in design.sites
        for item in site.devices
    }
    expected = {
        frozenset((
            (names[item.source_device], item.source_port),
            (names[item.target_device], item.target_port),
        ))
        for site in design.sites
        for item in site.links
    }
    observed = {
        frozenset(((item.device_a, item.port_a), (item.device_b, item.port_b)))
        for item in compiled.plan.links
        if item.link_role not in {"endpoint_access", "server_access", "phone_passthrough"}
    }
    assert observed == expected


def test_only_documented_ambiguities_are_marked_as_implementation_allocations():
    design = cp_scale_physical_design()
    allocated = [
        item
        for site in design.sites
        for item in site.endpoint_bindings
        if item.provenance == "implementation_allocation"
    ]

    assert len(allocated) == 18
    assert all(
        item.device_port in {
            "FastEthernet0/22", "FastEthernet0/23",
            "GigabitEthernet0/1", "GigabitEthernet0/2",
        }
        for item in allocated
    )
