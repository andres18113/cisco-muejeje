"""Stage 3A4: product planning can express a serial WAN without Packet Tracer."""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.compile_enterprise import (
    compile_enterprise_topology,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    DeviceCapabilities,
)
from src.packet_tracer_mcp.domain.enterprise.models.hardware import (
    HardwareCandidate,
    HardwarePlanStatus,
    ModuleInstallation,
    PortClass,
    PortDescriptor,
)
from src.packet_tracer_mcp.domain.enterprise.models.intent import (
    EnterpriseIntent,
    SiteIntent,
    SiteType,
)
from src.packet_tracer_mcp.domain.enterprise.models.link_performance import LinkMedia
from src.packet_tracer_mcp.domain.enterprise.models.requirements import WanLinkRequirement
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import (
    EnterpriseDesigner,
)
from src.packet_tracer_mcp.domain.enterprise.services.hardware_planner import (
    HardwarePlanner,
    ModulePlanner,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_topology import (
    PacketTracerTopologyCatalogAdapter,
)


def _intent(
    media: LinkMedia,
    *,
    duplicate: bool = False,
    reverse_sites: bool = False,
) -> EnterpriseIntent:
    north_links = [WanLinkRequirement(target_site_id="south", media=media)]
    south_links: list[WanLinkRequirement] = []
    if duplicate:
        north_links.append(WanLinkRequirement(target_site_id="south", media=media))
        south_links.append(WanLinkRequirement(target_site_id="north", media=media))
    sites = [
        SiteIntent(name="North", type=SiteType.HQ, uplinks=north_links),
        SiteIntent(name="South", type=SiteType.BRANCH, uplinks=south_links),
    ]
    if reverse_sites:
        sites.reverse()
    return EnterpriseIntent(name="Generic WAN", sites=sites)


def _design(intent: EnterpriseIntent):
    result = EnterpriseDesigner().design(intent)
    assert result.validation.is_valid
    assert result.plan is not None
    return result.plan


def _router_candidate() -> HardwareCandidate:
    return next(
        candidate
        for candidate in EnterpriseCapabilityAdapter().hardware_candidates("router")
        if candidate.model == "2911"
    )


def _compile(media: LinkMedia, *, duplicate: bool = False, reverse_sites: bool = False):
    enterprise = _design(
        _intent(media, duplicate=duplicate, reverse_sites=reverse_sites),
    )
    hardware = HardwarePlanner().plan(enterprise, [], [_router_candidate()])
    catalog = PacketTracerTopologyCatalogAdapter()
    compiled = compile_enterprise_topology(
        enterprise,
        hardware,
        catalog.compilation_profile(),
        catalog.cable_for,
    )
    return enterprise, hardware, compiled


def test_serial_wan_reaches_module_planner_and_compiles_a_typed_serial_link(monkeypatch):
    calls: list[tuple[str, int]] = []
    original = ModulePlanner.plan_serial

    def traced(self, candidate, required_serial_ports, options, available_slots=None):
        calls.append((candidate.model, required_serial_ports))
        return original(self, candidate, required_serial_ports, options, available_slots)

    monkeypatch.setattr(ModulePlanner, "plan_serial", traced)
    enterprise, hardware, compiled = _compile(LinkMedia.SERIAL)

    assert calls == [("2911", 1), ("2911", 1)]
    assert hardware.status is HardwarePlanStatus.VALID
    wan_devices = [
        device
        for site in hardware.site_hardware
        for device in site.devices
        if device.role is DeviceRole.WAN_ROUTER
    ]
    assert len(wan_devices) == 2
    assert all(len(device.module_plan) == 1 for device in wan_devices)
    assert all(
        any(
            PortClass.MODULE_PROVIDED in port.classes
            and PortClass.SERIAL in port.classes
            for port in device.port_descriptors
        )
        for device in wan_devices
    )

    hardware_links = [link for site in hardware.site_hardware for link in site.links]
    assert len(hardware_links) == 1
    assert hardware_links[0].media is LinkMedia.SERIAL
    assert hardware_links[0].required_port_class is PortClass.SERIAL
    assert compiled.is_valid and compiled.plan is not None
    assert len(compiled.plan.modules) == 2
    serial_links = [link for link in compiled.plan.links if link.cable == LinkMedia.SERIAL.value]
    assert len(serial_links) == 1
    assert serial_links[0].link_role == "wan_link"

    intent_payload = enterprise.model_dump_json()
    assert "2911" not in intent_payload
    assert "HWIC-2T" not in intent_payload
    assert "Serial0/0/0" not in intent_payload


def test_router_to_router_ethernet_wan_remains_ethernet_and_needs_no_module():
    _, hardware, compiled = _compile(LinkMedia.ETHERNET)

    links = [link for site in hardware.site_hardware for link in site.links]
    assert len(links) == 1
    assert links[0].media is LinkMedia.ETHERNET
    assert links[0].required_port_class is PortClass.UPLINK_CAPABLE
    assert all(not device.module_plan for site in hardware.site_hardware for device in site.devices)
    assert compiled.is_valid and compiled.plan is not None
    assert compiled.plan.modules == []
    assert len(compiled.plan.links) == 1
    assert compiled.plan.links[0].cable == "cross"


def test_reordered_reciprocal_serial_requirements_are_deduplicated_deterministically():
    _, first_hardware, first = _compile(LinkMedia.SERIAL, duplicate=True)
    _, second_hardware, second = _compile(
        LinkMedia.SERIAL,
        duplicate=True,
        reverse_sites=True,
    )

    first_links = [link for site in first_hardware.site_hardware for link in site.links]
    first_modules = [
        module
        for site in first_hardware.site_hardware
        for device in site.devices
        for module in device.module_plan
    ]
    assert len(first_links) == 1
    assert len(first_modules) == 2
    assert first_hardware.model_dump(mode="json") == second_hardware.model_dump(mode="json")
    assert first.is_valid and first.plan is not None
    assert second.is_valid and second.plan is not None
    assert first.semantic_hash == second.semantic_hash
    assert first.plan.model_dump(mode="json") == second.plan.model_dump(mode="json")


@pytest.mark.parametrize("supports_modules, include_option", [
    (CapabilityStatus.UNKNOWN, True),
    (CapabilityStatus.SUPPORTED, False),
])
def test_missing_or_unknown_serial_module_capability_fails_closed(
    supports_modules: CapabilityStatus,
    include_option: bool,
):
    option = ModuleInstallation(
        module="Generic-Serial-Module",
        slot="slot-a",
        provided_ports=["module-port-a", "module-port-b"],
        provided_port_classes=[PortClass.SERIAL, PortClass.WAN],
    )
    candidate = HardwareCandidate(
        model="Generic-Router",
        capabilities=DeviceCapabilities(
            model="Generic-Router",
            category="router",
            gigabit_ports=2,
            port_count=2,
            supports_modules=supports_modules,
            compatible_modules=[option.module],
        ),
        ports=[
            PortDescriptor(name="ethernet-a", classes=[PortClass.UPLINK_CAPABLE]),
            PortDescriptor(name="ethernet-b", classes=[PortClass.UPLINK_CAPABLE]),
        ],
        module_options=[option] if include_option else [],
        available_module_slots=["slot-a"],
    )

    hardware = HardwarePlanner().plan(
        _design(_intent(LinkMedia.SERIAL)),
        [],
        [candidate],
    )

    assert hardware.status is HardwarePlanStatus.UNRESOLVED
    assert hardware.unsupported_requirements
    assert not [link for site in hardware.site_hardware for link in site.links]
    assert not [
        device
        for site in hardware.site_hardware
        for device in site.devices
        if device.role is DeviceRole.WAN_ROUTER
    ]
