"""E3 offline: evidencia, selección física, puertos, módulos y redundancia."""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityEvidence,
    CapabilityStatus,
    DeviceCandidateStatus,
    DeviceCapabilities,
    EvidenceSource,
)
from src.packet_tracer_mcp.domain.enterprise.models.hardware import (
    HardwareCandidate,
    HardwarePlanStatus,
    ModuleInstallation,
    NormalizedPortSpeed,
    PortClass,
    PortDescriptor,
    ResiliencyLevel,
)
from src.packet_tracer_mcp.domain.enterprise.models.hierarchy import BuildingIntent, EndpointGroup, FloorIntent, ZoneIntent
from src.packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent, SiteIntent, SiteType
from src.packet_tracer_mcp.domain.enterprise.models.requirements import EndpointRequirement
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.services.capability_resolver import CapabilityResolver
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import EnterpriseDesigner
from src.packet_tracer_mcp.domain.enterprise.services.hardware_planner import (
    HardwarePlanner,
    HardwarePlanningPolicy,
    ModulePlanner,
    SwitchCountPlanner,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import EnterpriseCapabilityAdapter


def _ports(access: int = 24, uplinks: int = 2) -> list[PortDescriptor]:
    return [
        PortDescriptor(name=f"FastEthernet0/{index}", classes=[PortClass.ACCESS_CAPABLE], speed=NormalizedPortSpeed.SPEED_100M)
        for index in range(1, access + 1)
    ] + [
        PortDescriptor(name=f"GigabitEthernet0/{index}", classes=[PortClass.UPLINK_CAPABLE], speed=NormalizedPortSpeed.SPEED_1G)
        for index in range(1, uplinks + 1)
    ]


def _candidate(
    model: str = "Verified-24",
    *, poe: CapabilityStatus = CapabilityStatus.SUPPORTED,
    poe_ports: int | None = 24,
    layer3: CapabilityStatus = CapabilityStatus.SUPPORTED,
    access: int = 24,
    uplinks: int = 2,
) -> HardwareCandidate:
    return HardwareCandidate(
        model=model,
        capabilities=DeviceCapabilities(
            model=model, category="switch", fastethernet_ports=access,
            gigabit_ports=uplinks, port_count=access + uplinks,
            supports_poe=poe, poe_ports=poe_ports, layer3=layer3,
        ),
        ports=_ports(access, uplinks),
    )


def _enterprise() -> EnterpriseIntent:
    requirements = [
        EndpointRequirement(role=DeviceRole.USER_PC, count=30),
        EndpointRequirement(role=DeviceRole.IP_PHONE, count=30, requires_poe=True),
        EndpointRequirement(role=DeviceRole.IP_CAMERA, count=8, requires_poe=True),
        EndpointRequirement(role=DeviceRole.PRINTER, count=4),
        EndpointRequirement(role=DeviceRole.ACCESS_POINT, count=3, requires_poe=True),
    ]
    return EnterpriseIntent(
        name="Artefacta", default_growth_percent=0.30,
        sites=[SiteIntent(
            name="Matriz", type=SiteType.HQ,
            buildings=[BuildingIntent(name="A", floors=[FloorIntent(name="1", zones=[ZoneIntent(
                name="Ventas", endpoint_groups=[EndpointGroup(name="Ventas", requirements=requirements)]
            )])])],
        )],
    )


def _plan():
    result = EnterpriseDesigner().design(_enterprise())
    assert result.plan is not None and result.validation.is_valid
    return result.plan


def test_capability_evidence_priority_keeps_unknown_and_runtime_wins_inference():
    resolver = CapabilityResolver()
    evidence = [
        CapabilityEvidence(capability="supports_poe", status=CapabilityStatus.UNSUPPORTED, source=EvidenceSource.INFERRED),
        CapabilityEvidence(
            capability="supports_poe",
            status=CapabilityStatus.SUPPORTED,
            source=EvidenceSource.PACKET_TRACER_RUNTIME,
            verified=True,
            observed_value=1,
            dimensions={
                "poe_access_port_count": "1",
                "poe_delivery_tested_ports": "1",
                "poe_delivery_active_ports": "1",
            },
        ),
    ]

    assert resolver.resolve_evidence("supports_poe", evidence) is CapabilityStatus.SUPPORTED
    assert resolver.resolve_evidence("layer3", evidence) is CapabilityStatus.UNKNOWN
    updated = resolver.with_evidence(
        _candidate().capabilities,
        [CapabilityEvidence(
            capability="supports_static_routes", status=CapabilityStatus.SUPPORTED,
            source=EvidenceSource.MANUAL_VERIFICATION, verified=True,
        )],
    )
    assert updated.supports_static_routes is CapabilityStatus.SUPPORTED


def test_poe_evidence_without_delivery_dimensions_is_capped_at_resolver():
    resolver = CapabilityResolver()
    evidence = CapabilityEvidence(
        capability="supports_poe",
        status=CapabilityStatus.SUPPORTED,
        source=EvidenceSource.PACKET_TRACER_RUNTIME,
        verified=True,
        observed_value=24,
    )

    winner = resolver.winning_evidence("supports_poe", [evidence])
    resolved = resolver.with_evidence(_candidate().capabilities, [evidence])

    assert winner is not None and winner.status is CapabilityStatus.UNKNOWN
    assert winner.observed_value is None
    assert resolved.supports_poe is CapabilityStatus.UNKNOWN
    assert resolved.poe_ports is None


def test_unverified_delivery_dimensions_cannot_authorize_at_resolver():
    resolver = CapabilityResolver()
    evidence = CapabilityEvidence(
        capability="supports_poe",
        status=CapabilityStatus.SUPPORTED,
        source=EvidenceSource.PACKET_TRACER_RUNTIME,
        verified=False,
        observed_value=24,
        dimensions={
            "poe_access_port_count": "24",
            "poe_delivery_tested_ports": "24",
            "poe_delivery_active_ports": "24",
        },
    )

    resolved = resolver.with_evidence(_candidate().capabilities, [evidence])

    assert resolved.supports_poe is CapabilityStatus.UNKNOWN
    assert resolved.poe_ports is None


def test_descriptive_sources_cannot_authorize_poe_delivery():
    resolver = CapabilityResolver()
    for source in (EvidenceSource.INFERRED, EvidenceSource.CATALOG):
        evidence = CapabilityEvidence(
            capability="supports_poe",
            status=CapabilityStatus.SUPPORTED,
            source=source,
            verified=True,
            observed_value=24,
            dimensions={
                "poe_access_port_count": "24",
                "poe_delivery_tested_ports": "24",
                "poe_delivery_active_ports": "24",
            },
        )

        resolved = resolver.with_evidence(_candidate().capabilities, [evidence])

        assert resolved.supports_poe is CapabilityStatus.UNKNOWN
        assert resolved.poe_ports is None


def test_switch_count_reserves_dedicated_uplinks_without_reducing_access_capacity():
    choice = SwitchCountPlanner().choose(59, 54, 2, [_candidate()])

    assert choice is not None
    assert choice.count == 3
    assert choice.status is DeviceCandidateStatus.COMPATIBLE


def test_unknown_poe_produces_provisional_candidate_not_a_final_selection():
    choice = SwitchCountPlanner().choose(59, 54, 2, [_candidate(poe=CapabilityStatus.UNKNOWN, poe_ports=None)])

    assert choice is not None
    assert choice.status is DeviceCandidateStatus.NEEDS_VERIFICATION


def test_hardware_planner_builds_three_tier_access_slices_and_redundant_uplinks():
    hardware = HardwarePlanner().plan(_plan(), [_candidate()], policy=HardwarePlanningPolicy(resiliency=ResiliencyLevel.BASIC))
    site = hardware.site_hardware[0]
    block = site.access_blocks[0]

    assert hardware.status is HardwarePlanStatus.VALID
    assert len(block.switches) == 3
    assert sum(item.count for item in block.port_assignments if DeviceRole.IP_PHONE in item.roles) == 30
    assert sum(item.count for item in block.port_assignments) == 45
    used_ports = [(item.device_id, port) for item in block.port_assignments for port in (item.first_port, item.last_port)]
    assert len(used_ports) == len(set(used_ports))
    assert len([device for device in site.devices if device.role is DeviceRole.DISTRIBUTION_SWITCH]) == 2
    assert len([device for device in site.devices if device.role is DeviceRole.CORE_SWITCH]) == 1
    assert len(site.links) == 8
    assert all(link.redundancy_group for link in site.links[:6])
    poe_by_device = {
        device.id: sum(
            assignment.count for assignment in block.port_assignments
            if assignment.device_id == device.id and assignment.requires_poe
        )
        for device in site.devices if device.role is DeviceRole.ACCESS_SWITCH
    }
    assert all(used <= 24 for used in poe_by_device.values())


def test_hardware_plan_is_partial_when_catalog_has_only_unknown_poe():
    hardware = HardwarePlanner().plan(_plan(), [_candidate(poe=CapabilityStatus.UNKNOWN, poe_ports=None)])

    assert hardware.status is HardwarePlanStatus.PARTIALLY_RESOLVED
    access = [device for device in hardware.site_hardware[0].devices if device.role is DeviceRole.ACCESS_SWITCH]
    assert all(device.selected_model is None and device.provisional_model == "Verified-24" for device in access)


def test_unknown_layer3_evidence_keeps_higher_layers_provisional():
    hardware = HardwarePlanner().plan(_plan(), [_candidate(layer3=CapabilityStatus.UNKNOWN)])

    assert hardware.status is HardwarePlanStatus.PARTIALLY_RESOLVED
    higher = [device for device in hardware.site_hardware[0].devices if device.role is not DeviceRole.ACCESS_SWITCH]
    assert higher and all(device.selection_status is DeviceCandidateStatus.NEEDS_VERIFICATION for device in higher)


def test_module_planner_uses_only_compatible_catalog_options_and_rejects_empty_without_them():
    modular = _candidate("Router-PT-Empty", access=0, uplinks=0)
    modular = modular.model_copy(update={
        "capabilities": modular.capabilities.model_copy(update={
            "category": "router", "supports_modules": CapabilityStatus.SUPPORTED,
            "compatible_modules": ["PT-NM-2S"],
        })
    })
    option = ModuleInstallation(module="PT-NM-2S", provided_ports=["Serial0/0", "Serial0/1"])

    assert ModulePlanner().plan_serial(modular, 2, [option]) == [option]
    assert ModulePlanner().plan_serial(modular, 2, [option], available_slots=0) is None
    assert ModulePlanner().plan_serial(modular, 2, [ModuleInstallation(module="Wrong", provided_ports=["Serial0/0", "Serial0/1"])]) is None


def test_hardware_plan_is_unresolved_without_any_physical_candidate():
    hardware = HardwarePlanner().plan(_plan(), [])

    assert hardware.status is HardwarePlanStatus.UNRESOLVED
    assert hardware.unsupported_requirements


def test_port_assignments_are_deterministic_and_keep_group_ranges_compact():
    planner = HardwarePlanner()
    first = planner.plan(_plan(), [_candidate()])
    second = planner.plan(_plan(), [_candidate()])

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    slices = first.site_hardware[0].access_blocks[0].endpoint_slices
    assert slices[0].count == 30
    assert len(slices) < 10


def test_catalog_coverage_reports_observed_models_without_auto_adding_them():
    report = EnterpriseCapabilityAdapter().coverage_report(["PT8200", "IR8340", "2911", "IE-3400"])

    assert "2911" in report.known_in_base_catalog
    assert report.unclassified == ["IE-3400", "IR8340", "PT8200"]
    assert "2911" in report.capability_gaps


def test_hardware_compact_summary_does_not_expand_endpoints():
    summary = HardwarePlanner().plan(_plan(), [_candidate()]).compact_summary()

    assert summary["access_switches"] == 3
    assert summary["planned_access_ports"] == 59
    assert summary["planned_poe_ports"] == 54
