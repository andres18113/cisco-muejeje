"""Stage 3A4: product planning can express a serial WAN without Packet Tracer."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.packet_tracer_mcp.application.use_cases.compile_enterprise import (
    compile_enterprise_topology,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    DeviceCapabilities,
)
from src.packet_tracer_mcp.domain.enterprise.models.enterprise_plan import SitePlan
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


def _candidate_with_module_status(
    supports_modules: CapabilityStatus,
    *,
    include_option: bool = True,
) -> HardwareCandidate:
    option = ModuleInstallation(
        module="Generic-Serial-Module",
        slot="slot-a",
        provided_ports=["module-port-a", "module-port-b"],
        provided_port_classes=[PortClass.SERIAL, PortClass.WAN],
    )
    return HardwareCandidate(
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


@pytest.mark.parametrize(
    ("supports_modules", "warning", "is_unsupported"),
    [
        (
            CapabilityStatus.UNKNOWN,
            "WAN: north queda sin resolver: Generic-Router tiene "
            "supports_modules=UNKNOWN; falta evidencia para instalar 1 puerto(s) serial.",
            False,
        ),
        (
            CapabilityStatus.UNSUPPORTED,
            "No existe candidato WAN soportado para north: Generic-Router tiene "
            "supports_modules=UNSUPPORTED y se requiere(n) 1 puerto(s) serial.",
            True,
        ),
    ],
)
def test_unknown_and_unsupported_module_capabilities_remain_distinct(
    supports_modules: CapabilityStatus,
    warning: str,
    is_unsupported: bool,
):
    hardware = HardwarePlanner().plan(
        _design(_intent(LinkMedia.SERIAL)),
        [],
        [_candidate_with_module_status(supports_modules)],
    )

    assert hardware.status is HardwarePlanStatus.UNRESOLVED
    assert hardware.warnings == [
        warning,
        warning.replace("north", "south"),
    ]
    assert hardware.unsupported_requirements == (
        hardware.warnings if is_unsupported else []
    )
    assert not [link for site in hardware.site_hardware for link in site.links]
    wan_devices = [
        device
        for site in hardware.site_hardware
        for device in site.devices
        if device.role is DeviceRole.WAN_ROUTER
    ]
    assert wan_devices == []
    assert not [
        module
        for site in hardware.site_hardware
        for device in site.devices
        for module in device.module_plan
    ]


def test_supported_modules_without_a_compatible_option_remain_unsupported():
    hardware = HardwarePlanner().plan(
        _design(_intent(LinkMedia.SERIAL)),
        [],
        [_candidate_with_module_status(CapabilityStatus.SUPPORTED, include_option=False)],
    )

    assert hardware.status is HardwarePlanStatus.UNRESOLVED
    assert hardware.unsupported_requirements == hardware.warnings
    assert all("módulo serial compatible" in warning for warning in hardware.warnings)


def _conflicting_intent(*, reverse_sites: bool = False) -> EnterpriseIntent:
    sites = [
        SiteIntent(
            name="A",
            type=SiteType.HQ,
            uplinks=[WanLinkRequirement(target_site_id="b", media=LinkMedia.SERIAL)],
        ),
        SiteIntent(
            name="B",
            type=SiteType.BRANCH,
            uplinks=[WanLinkRequirement(target_site_id="a", media=LinkMedia.ETHERNET)],
        ),
    ]
    if reverse_sites:
        sites.reverse()
    return EnterpriseIntent(name="Conflict", sites=sites)


def test_reciprocal_media_conflict_is_a_deterministic_structured_invalid_plan():
    first = EnterpriseDesigner().design(_conflicting_intent())
    reordered = EnterpriseDesigner().design(_conflicting_intent(reverse_sites=True))

    assert first.plan is None
    assert reordered.plan is None
    assert first.validation.to_dict() == reordered.validation.to_dict()
    assert [error.code.value for error in first.validation.errors] == [
        "ENTERPRISE_WAN_MEDIA_CONFLICT",
    ]
    assert first.validation.errors[0].device == "a<->b"
    assert "ethernet, serial" in first.validation.errors[0].message


@pytest.mark.parametrize(
    ("uplink", "error_code"),
    [
        (
            WanLinkRequirement(target_site_id="a", media=LinkMedia.SERIAL),
            "ENTERPRISE_WAN_SELF_LINK",
        ),
        (
            WanLinkRequirement(target_site_id="missing", media=LinkMedia.SERIAL),
            "ENTERPRISE_WAN_SITE_NOT_FOUND",
        ),
    ],
)
def test_invalid_wan_peer_fails_closed_before_a_plan_exists(
    uplink: WanLinkRequirement,
    error_code: str,
):
    result = EnterpriseDesigner().design(EnterpriseIntent(
        name="Invalid peer",
        sites=[SiteIntent(name="A", type=SiteType.HQ, uplinks=[uplink])],
    ))

    assert result.plan is None
    assert not result.validation.is_valid
    assert [error.code.value for error in result.validation.errors] == [error_code]


def test_unknown_wan_media_fails_closed_before_a_plan_exists():
    result = EnterpriseDesigner().design(EnterpriseIntent(
        name="Unknown media",
        sites=[
            SiteIntent(
                name="A",
                type=SiteType.HQ,
                uplinks=[WanLinkRequirement(
                    target_site_id="b",
                    media=LinkMedia.UNKNOWN,
                )],
            ),
            SiteIntent(name="B", type=SiteType.BRANCH),
        ],
    ))

    assert result.plan is None
    assert [error.code.value for error in result.validation.errors] == [
        "ENTERPRISE_WAN_MEDIA_UNKNOWN",
    ]


def test_uplink_public_schema_is_typed_and_legacy_site_plan_strings_fail_closed():
    intent_uplinks = SiteIntent.model_json_schema()["properties"]["uplinks"]
    plan_uplinks = SitePlan.model_json_schema()["properties"]["uplinks"]

    assert intent_uplinks["items"]["$ref"].endswith("/WanLinkRequirement")
    assert plan_uplinks["items"]["$ref"].endswith("/WanLinkRequirement")
    with pytest.raises(ValidationError):
        SitePlan.model_validate({
            "name": "A",
            "site_id": "a",
            "type": "hq",
            "uplinks": ["b"],
        })
    assert SitePlan(name="A", site_id="a", type=SiteType.HQ).model_dump()["uplinks"] == []


def test_two_serial_links_per_router_use_one_catalogued_two_port_module(monkeypatch):
    serial_demands: list[tuple[str, int]] = []
    original = ModulePlanner.plan_serial

    def traced(self, candidate, required_serial_ports, options, available_slots=None):
        serial_demands.append((candidate.model, required_serial_ports))
        return original(self, candidate, required_serial_ports, options, available_slots)

    monkeypatch.setattr(ModulePlanner, "plan_serial", traced)
    enterprise = _design(EnterpriseIntent(
        name="Serial triangle",
        sites=[
            SiteIntent(
                name="A",
                type=SiteType.HQ,
                uplinks=[
                    WanLinkRequirement(target_site_id="b", media=LinkMedia.SERIAL),
                    WanLinkRequirement(target_site_id="c", media=LinkMedia.SERIAL),
                ],
            ),
            SiteIntent(
                name="B",
                type=SiteType.BRANCH,
                uplinks=[WanLinkRequirement(target_site_id="c", media=LinkMedia.SERIAL)],
            ),
            SiteIntent(name="C", type=SiteType.BRANCH),
        ],
    ))
    hardware = HardwarePlanner().plan(enterprise, [], [_router_candidate()])
    catalog = PacketTracerTopologyCatalogAdapter()
    compiled = compile_enterprise_topology(
        enterprise,
        hardware,
        catalog.compilation_profile(),
        catalog.cable_for,
    )

    routers = [
        device
        for site in hardware.site_hardware
        for device in site.devices
        if device.role is DeviceRole.WAN_ROUTER
    ]
    links = [link for site in hardware.site_hardware for link in site.links]
    assert hardware.status is HardwarePlanStatus.VALID
    assert serial_demands == [("2911", 2), ("2911", 2), ("2911", 2)]
    assert len(routers) == 3
    assert all(len(router.module_plan) == 1 for router in routers)
    assert all(router.module_plan[0].module == "HWIC-2T" for router in routers)
    assert all(len(router.module_plan[0].provided_ports) == 2 for router in routers)
    assert len(links) == 3
    assert compiled.is_valid and compiled.plan is not None
    assert len(compiled.plan.modules) == 3
    serial_links = [link for link in compiled.plan.links if link.cable == "serial"]
    assert len(serial_links) == 3
    ports_by_router: dict[str, set[str]] = {}
    for link in serial_links:
        ports_by_router.setdefault(link.device_a_id, set()).add(link.port_a)
        ports_by_router.setdefault(link.device_b_id, set()).add(link.port_b)
    assert {router.id: len(ports_by_router[router.id]) for router in routers} == {
        router.id: 2 for router in routers
    }


def test_edge_and_wan_router_roles_are_distinct_pending_role_reconciliation():
    intent = _intent(LinkMedia.SERIAL).model_copy(update={"internet_required": True})
    hardware = HardwarePlanner().plan(_design(intent), [], [_router_candidate()])

    for site in hardware.site_hardware:
        routers = [
            device
            for device in site.devices
            if device.role in {DeviceRole.EDGE_ROUTER, DeviceRole.WAN_ROUTER}
        ]
        assert [device.role for device in routers] == [
            DeviceRole.EDGE_ROUTER,
            DeviceRole.WAN_ROUTER,
        ]
        assert [device.selected_model for device in routers] == ["2911", "2911"]
