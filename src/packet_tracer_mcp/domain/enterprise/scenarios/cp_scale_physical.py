"""Canonical CP-SCALE physical design translated from the governed references."""

from __future__ import annotations

from ..models.hardware import (
    AccessBlockPlan,
    EndpointPortBinding,
    HardwareLinkRequirement,
    HierarchyMode,
    LinkRole,
    ModuleInstallation,
    PhysicalDesignDevice,
    PhysicalDesignSpec,
    PhysicalSiteDesign,
    PortClass,
    ResiliencyLevel,
)
from ..models.control_plane import (
    ControlPlaneIntent,
    DynamicRoutingIntent,
    DynamicRoutingProtocol,
    StpIntent,
    StpMode,
)
from ..models.link_performance import LinkMedia
from ..models.voice_plan import ExtensionRange, VoiceIntent
from ..models.roles import DeviceRole
from ..models.topology import NetworkLayer, TopologyPattern
from ...models.plans import TopologyPlan


LARGE = "large-branch"
MULTILAYER = "multilayer-branch"
SMALL = "small-branch"

Z1 = "large-branch/campus/floor-1/zone-a"
Z2 = "large-branch/campus/floor-2/zone-b"
ZC = "large-branch/campus/floor-3/zone-c"
ZD = "large-branch/campus/floor-3/zone-d"
M3 = "multilayer-branch/multilayer-campus/access/mls3"
M4 = "multilayer-branch/multilayer-campus/access/mls4"
M5 = "multilayer-branch/multilayer-campus/access/mls5"
M6 = "multilayer-branch/multilayer-campus/access/mls6"
SB = "small-branch/branch/access/branch-zone"

R4 = "r-edge-large-branch-01"
SW10 = "sw-dist-large-branch-01"
SW4 = "sw-acc-large-branch-zone-a-01"
SW5 = "sw-acc-large-branch-zone-a-02"
SW6 = "sw-acc-large-branch-zone-b-01"
SW7 = "sw-acc-large-branch-zone-b-02"
SW8 = "sw-acc-large-branch-zone-c-01"
SW9 = "sw-acc-large-branch-zone-c-02"
SW0 = "sw-acc-large-branch-zone-d-01"
SW1 = "sw-acc-large-branch-zone-d-02"

R0 = "r-edge-multilayer-branch-01"
MLS7 = "sw-dist-multilayer-branch-01"
MLS3 = "sw-acc-multilayer-branch-mls3-01"
MLS4 = "sw-acc-multilayer-branch-mls4-01"
MLS5 = "sw-acc-multilayer-branch-mls5-01"
MLS6 = "sw-acc-multilayer-branch-mls6-01"

R3 = "r-edge-small-branch-01"
SW3 = "sw-acc-small-branch-branch-zone-01"


_NM_4A_S = ModuleInstallation(
    module="NM-4A/S",
    slot="1",
    provided_ports=["Serial1/0", "Serial1/1", "Serial1/2", "Serial1/3"],
    provided_port_classes=[PortClass.SERIAL, PortClass.WAN],
)


def _device(
    device_id: str,
    site_id: str,
    name: str,
    role: DeviceRole,
    layer: NetworkLayer,
    model: str,
    *,
    zone: str = "",
    additional_roles: tuple[DeviceRole, ...] = (),
    modules: tuple[ModuleInstallation, ...] = (),
) -> PhysicalDesignDevice:
    return PhysicalDesignDevice(
        id=device_id,
        site_id=site_id,
        semantic_name=name,
        role=role,
        additional_roles=list(additional_roles),
        network_layer=layer,
        model=model,
        modules=list(modules),
        parent_group=zone,
    )


def _link(
    source: str,
    source_port: str,
    target: str,
    target_port: str,
    role: LinkRole,
    *,
    serial: bool = False,
) -> HardwareLinkRequirement:
    return HardwareLinkRequirement(
        source_device=source,
        source_port=source_port,
        target_device=target,
        target_port=target_port,
        link_role=role,
        required_port_class=(PortClass.SERIAL if serial else PortClass.UPLINK_CAPABLE),
        media=(LinkMedia.SERIAL if serial else LinkMedia.ETHERNET),
    )


def _endpoint_id(zone: str, role: DeviceRole, index: int) -> str:
    return f"endpoint/{zone}/{role.value}/{index:03d}"


def _binding(
    switch: str,
    port: str,
    zone: str,
    role: DeviceRole,
    index: int,
    endpoint_port: str,
    *,
    provenance: str = "canonical_reference",
) -> EndpointPortBinding:
    return EndpointPortBinding(
        endpoint_id=_endpoint_id(zone, role, index),
        device_id=switch,
        device_port=port,
        endpoint_port=endpoint_port,
        provenance=provenance,
    )


def _range(
    switch: str,
    port_prefix: str,
    first_port: int,
    zone: str,
    role: DeviceRole,
    first_endpoint: int,
    count: int,
    endpoint_port: str,
) -> list[EndpointPortBinding]:
    return [
        _binding(
            switch,
            f"{port_prefix}{first_port + offset}",
            zone,
            role,
            first_endpoint + offset,
            endpoint_port,
        )
        for offset in range(count)
    ]


def _block(
    site: str,
    zone: str,
    switches: list[str],
    direct_ports: int,
    poe_ports: int,
) -> AccessBlockPlan:
    return AccessBlockPlan(
        site_id=site,
        zone_id=zone,
        block_id=f"canonical/{zone}",
        switches=switches,
        required_access_ports=direct_ports,
        required_poe_ports=poe_ports,
        required_uplinks=len(switches),
    )


def _large_bindings() -> list[EndpointPortBinding]:
    """Powered endpoints on powered access ports; uplinks on the uplink ports.

    Every access point here used to sit on `GigabitEthernet0/1-0/2` while the
    switch spent FastEthernet access ports on its infrastructure uplinks. That
    is backwards in both directions, and PoE is where it stopped being merely
    untidy: the powered-port evidence for these builds covers the 24 access
    ports, so an AP on an uplink is a powered attachment nothing can power.
    """
    return [
        *_range(SW4, "FastEthernet0/", 1, Z1, DeviceRole.USER_PC, 1, 22, "FastEthernet0"),
        _binding(SW4, "FastEthernet0/23", Z1, DeviceRole.ACCESS_POINT, 1, "Port 0"),
        _binding(SW4, "FastEthernet0/24", Z1, DeviceRole.USER_PC, 23, "FastEthernet0"),
        *_range(SW5, "FastEthernet0/", 1, Z1, DeviceRole.IP_PHONE, 1, 21, "Switch"),
        _binding(SW5, "FastEthernet0/22", Z1, DeviceRole.ACCESS_POINT, 2, "Port 0", provenance="implementation_allocation"),
        _binding(SW5, "FastEthernet0/23", Z1, DeviceRole.ACCESS_POINT, 3, "Port 0", provenance="implementation_allocation"),
        _binding(SW5, "FastEthernet0/24", Z1, DeviceRole.PRINTER, 1, "FastEthernet0", provenance="implementation_allocation"),
        _binding(SW5, "GigabitEthernet0/2", Z1, DeviceRole.PRINTER, 2, "FastEthernet0", provenance="implementation_allocation"),

        *_range(SW6, "FastEthernet0/", 1, Z2, DeviceRole.USER_PC, 1, 20, "FastEthernet0"),
        _binding(SW6, "FastEthernet0/21", Z2, DeviceRole.ACCESS_POINT, 1, "Port 0"),
        *_range(SW7, "FastEthernet0/", 1, Z2, DeviceRole.IP_PHONE, 1, 14, "Switch"),
        _binding(SW7, "FastEthernet0/15", Z2, DeviceRole.ACCESS_POINT, 2, "Port 0", provenance="implementation_allocation"),
        _binding(SW7, "FastEthernet0/16", Z2, DeviceRole.ACCESS_POINT, 3, "Port 0", provenance="implementation_allocation"),
        _binding(SW7, "FastEthernet0/22", Z2, DeviceRole.PRINTER, 1, "FastEthernet0", provenance="implementation_allocation"),
        _binding(SW7, "FastEthernet0/23", Z2, DeviceRole.PRINTER, 2, "FastEthernet0", provenance="implementation_allocation"),

        *_range(SW8, "FastEthernet0/", 1, ZC, DeviceRole.USER_PC, 1, 22, "FastEthernet0"),
        _binding(SW8, "FastEthernet0/23", ZC, DeviceRole.ACCESS_POINT, 1, "Port 0"),
        _binding(SW8, "FastEthernet0/24", ZC, DeviceRole.USER_PC, 23, "FastEthernet0"),
        *_range(SW9, "FastEthernet0/", 1, ZC, DeviceRole.IP_PHONE, 1, 3, "Switch"),
        _binding(SW9, "FastEthernet0/4", ZC, DeviceRole.ACCESS_POINT, 2, "Port 0", provenance="implementation_allocation"),
        _binding(SW9, "FastEthernet0/5", ZC, DeviceRole.ACCESS_POINT, 3, "Port 0", provenance="implementation_allocation"),
        _binding(SW9, "FastEthernet0/22", ZC, DeviceRole.PRINTER, 1, "FastEthernet0", provenance="implementation_allocation"),
        _binding(SW9, "FastEthernet0/23", ZC, DeviceRole.PRINTER, 2, "FastEthernet0", provenance="implementation_allocation"),

        *_range(SW0, "FastEthernet0/", 1, ZD, DeviceRole.USER_PC, 1, 20, "FastEthernet0"),
        _binding(SW0, "FastEthernet0/21", ZD, DeviceRole.ACCESS_POINT, 1, "Port 0"),
        *_range(SW1, "FastEthernet0/", 1, ZD, DeviceRole.IP_PHONE, 1, 13, "Switch"),
        _binding(SW1, "FastEthernet0/14", ZD, DeviceRole.ACCESS_POINT, 2, "Port 0", provenance="implementation_allocation"),
        _binding(SW1, "FastEthernet0/15", ZD, DeviceRole.ACCESS_POINT, 3, "Port 0", provenance="implementation_allocation"),
        _binding(SW1, "FastEthernet0/22", ZD, DeviceRole.PRINTER, 1, "FastEthernet0", provenance="implementation_allocation"),
        _binding(SW1, "FastEthernet0/23", ZD, DeviceRole.PRINTER, 2, "FastEthernet0", provenance="implementation_allocation"),
    ]


def _multilayer_bindings() -> list[EndpointPortBinding]:
    return [
        _binding(MLS3, "GigabitEthernet1/0/2", M3, DeviceRole.IP_PHONE, 1, "Switch"),
        _binding(MLS3, "GigabitEthernet1/0/3", M3, DeviceRole.IP_PHONE, 2, "Switch"),
        _binding(MLS3, "GigabitEthernet1/0/4", M3, DeviceRole.ACCESS_POINT, 1, "Port 0"),
        _binding(MLS4, "GigabitEthernet1/0/2", M4, DeviceRole.IP_PHONE, 1, "Switch"),
        _binding(MLS4, "GigabitEthernet1/0/3", M4, DeviceRole.ACCESS_POINT, 1, "Port 0"),
        *_range(MLS5, "FastEthernet0/", 1, M5, DeviceRole.IP_PHONE, 1, 8, "Switch"),
        *_range(MLS6, "FastEthernet0/", 1, M6, DeviceRole.USER_PC, 1, 10, "FastEthernet0"),
        *_range(MLS6, "FastEthernet0/", 11, M6, DeviceRole.LAPTOP, 1, 2, "FastEthernet0"),
        _binding(MLS6, "FastEthernet0/13", M6, DeviceRole.ACCESS_POINT, 1, "Port 0"),
    ]


def _small_bindings() -> list[EndpointPortBinding]:
    return [
        *_range(SW3, "FastEthernet0/", 1, SB, DeviceRole.USER_PC, 1, 6, "FastEthernet0"),
        *_range(SW3, "FastEthernet0/", 7, SB, DeviceRole.IP_PHONE, 1, 7, "Switch"),
        _binding(SW3, "FastEthernet0/14", SB, DeviceRole.LAPTOP, 1, "FastEthernet0"),
        _binding(SW3, "FastEthernet0/15", SB, DeviceRole.ACCESS_POINT, 1, "Port 0", provenance="implementation_allocation"),
        _binding(SW3, "FastEthernet0/16", SB, DeviceRole.ACCESS_POINT, 2, "Port 0", provenance="implementation_allocation"),
    ]


def cp_scale_physical_design() -> PhysicalDesignSpec:
    """Return a fresh typed copy of the complete 314-device/219-link target."""

    large = PhysicalSiteDesign(
        site_id=LARGE,
        topology_pattern=TopologyPattern.HIERARCHICAL,
        hierarchy_mode=HierarchyMode.THREE_TIER,
        network_layers=[NetworkLayer.ACCESS, NetworkLayer.DISTRIBUTION, NetworkLayer.EDGE, NetworkLayer.WAN],
        devices=[
            _device(R4, LARGE, "Router4", DeviceRole.EDGE_ROUTER, NetworkLayer.EDGE, "2811", additional_roles=(DeviceRole.WAN_ROUTER,), modules=(_NM_4A_S,)),
            _device(SW10, LARGE, "Switch10", DeviceRole.DISTRIBUTION_SWITCH, NetworkLayer.DISTRIBUTION, "2960-24TT"),
            _device(SW4, LARGE, "Switch4", DeviceRole.ACCESS_SWITCH, NetworkLayer.ACCESS, "3560-24PS", zone=Z1),
            _device(SW5, LARGE, "Switch5", DeviceRole.ACCESS_SWITCH, NetworkLayer.ACCESS, "3560-24PS", zone=Z1),
            _device(SW6, LARGE, "Switch6", DeviceRole.ACCESS_SWITCH, NetworkLayer.ACCESS, "3560-24PS", zone=Z2),
            _device(SW7, LARGE, "Switch7", DeviceRole.ACCESS_SWITCH, NetworkLayer.ACCESS, "3560-24PS", zone=Z2),
            _device(SW8, LARGE, "Switch8", DeviceRole.ACCESS_SWITCH, NetworkLayer.ACCESS, "3560-24PS", zone=ZC),
            _device(SW9, LARGE, "Switch9", DeviceRole.ACCESS_SWITCH, NetworkLayer.ACCESS, "3560-24PS", zone=ZC),
            _device(SW0, LARGE, "Switch0", DeviceRole.ACCESS_SWITCH, NetworkLayer.ACCESS, "3560-24PS", zone=ZD),
            _device(SW1, LARGE, "Switch1", DeviceRole.ACCESS_SWITCH, NetworkLayer.ACCESS, "3560-24PS", zone=ZD),
        ],
        links=[
            _link(R4, "Serial1/1", R3, "Serial1/1", LinkRole.WAN_LINK, serial=True),
            _link(R4, "Serial1/0", R0, "Serial1/0", LinkRole.WAN_LINK, serial=True),
            _link(R4, "FastEthernet0/0", SW10, "GigabitEthernet0/1", LinkRole.EDGE_LINK),
            _link(SW10, "FastEthernet0/1", SW4, "GigabitEthernet0/1", LinkRole.DISTRIBUTION_LINK),
            _link(SW10, "FastEthernet0/2", SW6, "GigabitEthernet0/1", LinkRole.DISTRIBUTION_LINK),
            _link(SW10, "FastEthernet0/3", SW8, "GigabitEthernet0/1", LinkRole.DISTRIBUTION_LINK),
            _link(SW10, "FastEthernet0/4", SW0, "GigabitEthernet0/1", LinkRole.DISTRIBUTION_LINK),
            _link(SW4, "GigabitEthernet0/2", SW5, "GigabitEthernet0/1", LinkRole.ACCESS_LINK),
            _link(SW6, "GigabitEthernet0/2", SW7, "GigabitEthernet0/1", LinkRole.ACCESS_LINK),
            _link(SW8, "GigabitEthernet0/2", SW9, "GigabitEthernet0/1", LinkRole.ACCESS_LINK),
            _link(SW0, "GigabitEthernet0/2", SW1, "GigabitEthernet0/1", LinkRole.ACCESS_LINK),
        ],
        access_blocks=[
            _block(LARGE, Z1, [SW4, SW5], 49, 24),
            _block(LARGE, Z2, [SW6, SW7], 39, 17),
            _block(LARGE, ZC, [SW8, SW9], 31, 6),
            _block(LARGE, ZD, [SW0, SW1], 38, 16),
        ],
        endpoint_bindings=_large_bindings(),
        resiliency=ResiliencyLevel.BASIC,
    )

    multilayer = PhysicalSiteDesign(
        site_id=MULTILAYER,
        topology_pattern=TopologyPattern.HIERARCHICAL,
        hierarchy_mode=HierarchyMode.THREE_TIER,
        network_layers=[NetworkLayer.ACCESS, NetworkLayer.DISTRIBUTION, NetworkLayer.EDGE, NetworkLayer.WAN],
        devices=[
            _device(R0, MULTILAYER, "Router0", DeviceRole.EDGE_ROUTER, NetworkLayer.EDGE, "2811", additional_roles=(DeviceRole.WAN_ROUTER,), modules=(_NM_4A_S,)),
            _device(MLS7, MULTILAYER, "MLS7", DeviceRole.DISTRIBUTION_SWITCH, NetworkLayer.DISTRIBUTION, "3650-24PS"),
            _device(MLS3, MULTILAYER, "MLS3", DeviceRole.ACCESS_SWITCH, NetworkLayer.ACCESS, "3650-24PS", zone=M3),
            _device(MLS4, MULTILAYER, "MLS4", DeviceRole.ACCESS_SWITCH, NetworkLayer.ACCESS, "3650-24PS", zone=M4),
            _device(MLS5, MULTILAYER, "MLS5", DeviceRole.ACCESS_SWITCH, NetworkLayer.ACCESS, "3560-24PS", zone=M5),
            _device(MLS6, MULTILAYER, "MLS6", DeviceRole.ACCESS_SWITCH, NetworkLayer.ACCESS, "3560-24PS", zone=M6),
        ],
        links=[
            _link(R3, "Serial1/0", R0, "Serial1/1", LinkRole.WAN_LINK, serial=True),
            _link(R0, "FastEthernet0/0", MLS7, "GigabitEthernet1/0/5", LinkRole.EDGE_LINK),
            _link(MLS7, "GigabitEthernet1/0/1", MLS3, "GigabitEthernet1/0/1", LinkRole.DISTRIBUTION_LINK),
            _link(MLS7, "GigabitEthernet1/0/2", MLS6, "GigabitEthernet0/1", LinkRole.DISTRIBUTION_LINK),
            _link(MLS7, "GigabitEthernet1/0/3", MLS5, "GigabitEthernet0/1", LinkRole.DISTRIBUTION_LINK),
            _link(MLS7, "GigabitEthernet1/0/4", MLS4, "GigabitEthernet1/0/1", LinkRole.DISTRIBUTION_LINK),
        ],
        access_blocks=[
            _block(MULTILAYER, M3, [MLS3], 3, 3),
            _block(MULTILAYER, M4, [MLS4], 2, 2),
            _block(MULTILAYER, M5, [MLS5], 8, 8),
            _block(MULTILAYER, M6, [MLS6], 13, 1),
        ],
        endpoint_bindings=_multilayer_bindings(),
        resiliency=ResiliencyLevel.BASIC,
    )

    small = PhysicalSiteDesign(
        site_id=SMALL,
        topology_pattern=TopologyPattern.EXTENDED_STAR,
        hierarchy_mode=HierarchyMode.FLAT,
        network_layers=[NetworkLayer.ACCESS, NetworkLayer.EDGE, NetworkLayer.WAN],
        devices=[
            _device(R3, SMALL, "Router3", DeviceRole.EDGE_ROUTER, NetworkLayer.EDGE, "2811", additional_roles=(DeviceRole.WAN_ROUTER,), modules=(_NM_4A_S,)),
            _device(SW3, SMALL, "Switch3", DeviceRole.ACCESS_SWITCH, NetworkLayer.ACCESS, "3560-24PS", zone=SB, additional_roles=(DeviceRole.DISTRIBUTION_SWITCH,)),
        ],
        links=[
            _link(R3, "FastEthernet0/0", SW3, "GigabitEthernet0/1", LinkRole.EDGE_LINK),
        ],
        access_blocks=[_block(SMALL, SB, [SW3], 16, 9)],
        endpoint_bindings=_small_bindings(),
        resiliency=ResiliencyLevel.NONE,
    )

    return PhysicalDesignSpec(
        id="cp-scale-canonical-physical-v1",
        sites=[large, multilayer, small],
        provenance=(
            "docs/reference/cp-scale/diseno_logico_IMP.md;"
            "docs/reference/cp-scale/topologia_completa_IMP.md;"
            "implementation allocations explicitly marked on bindings"
        ),
    )


def cp_scale_canonical_control_plane_intent(
    topology: TopologyPlan,
) -> ControlPlaneIntent:
    """Bind the documented CP-SCALE control policy to one compiled E4 plan.

    Rapid-PVST is deliberately not selected: exact-build Stage-A accepted the
    mutation but yielded no parser-backed instance.  PVST is the strongest
    mode whose protocol and numeric priorities have a typed read-back path.
    """

    expected_router_pairs = {
        frozenset((R4, R0)),
        frozenset((R4, R3)),
        frozenset((R3, R0)),
    }
    serial_links = [
        item for item in topology.links
        if item.cable == "serial"
        and frozenset((item.device_a_id, item.device_b_id)) in expected_router_pairs
    ]
    observed_pairs = {
        frozenset((item.device_a_id, item.device_b_id)) for item in serial_links
    }
    if observed_pairs != expected_router_pairs or len(serial_links) != 3:
        raise ValueError(
            "The canonical CP-SCALE control plane requires the exact three-router "
            "serial triangle."
        )

    vlan_ids = [10, 20, 30]

    def domain(
        site_id: str,
        primary: str,
        secondary: str = "",
    ) -> StpIntent:
        return StpIntent(
            id=f"stp/{site_id}/canonical-pvst",
            site_id=site_id,
            mode=StpMode.PVST,
            vlan_ids=vlan_ids,
            root_primary_by_vlan={vlan: primary for vlan in vlan_ids},
            root_secondary_by_vlan=(
                {vlan: secondary for vlan in vlan_ids} if secondary else {}
            ),
            portfast_access_ports=True,
            bpduguard_access_ports=True,
        )

    return ControlPlaneIntent(
        id="control-plane/cp-scale-canonical",
        stp_domains=[
            domain(LARGE, SW8, SW10),
            domain(MULTILAYER, MLS3, MLS7),
            domain(SMALL, SW3),
        ],
        routing=DynamicRoutingIntent(
            id="routing/cp-scale-canonical/ripv2",
            protocol=DynamicRoutingProtocol.RIPV2,
            device_ids=[R4, R0, R3],
            transit_link_ids=sorted(item.id for item in serial_links),
        ),
    )


#: Documented CME placement: each branch's edge router is its call control, at
#: the voice-VLAN gateway on port 2000. `diseno_logico_IMP.md` section 5.
_CANONICAL_CALL_CONTROL = {
    LARGE: R4,
    MULTILAYER: R0,
    SMALL: R3,
}
#: Configured CME capacities from `diseno_logico_IMP.md` section 5. They are
#: service limits, not counts inferred from whichever stage is currently built.
_CANONICAL_CALL_CONTROL_CAPACITY = {
    R4: 42,
    R0: 12,
    R3: 7,
}
#: Extension ranges are per branch and never overlap, so an extension alone
#: identifies the branch that owns it.
_CANONICAL_EXTENSION_RANGES = {
    LARGE: ExtensionRange(start=3001, end=3999),
    MULTILAYER: ExtensionRange(start=4001, end=4999),
    SMALL: ExtensionRange(start=5001, end=5999),
}


def cp_scale_canonical_voice_intent(topology: TopologyPlan) -> VoiceIntent:
    """Bind CME to whichever branches this projection actually contains.

    A stage that has not reached a branch yet has neither its phones nor its
    router, and naming a call control that is not deployed would fail E7's
    host resolution rather than simply not applying to that stage.

    Intersite calling stays off: the voice renderer refuses to emit it because
    it is not verified on this backend, and asking for it would compile a plan
    whose actions could only ever be skipped.
    """
    present = {item.id for item in topology.devices}
    hosts = {
        site_id: device_id
        for site_id, device_id in sorted(_CANONICAL_CALL_CONTROL.items())
        if device_id in present
    }
    return VoiceIntent(
        id="voice/cp-scale-canonical",
        call_control_device_ids=hosts,
        call_control_capacities={
            device_id: _CANONICAL_CALL_CONTROL_CAPACITY[device_id]
            for device_id in hosts.values()
        },
        extension_ranges={
            site_id: value
            for site_id, value in sorted(_CANONICAL_EXTENSION_RANGES.items())
            if site_id in hosts
        },
        intersite_calling=False,
    )
