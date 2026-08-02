"""Plan físico E3: hardware, módulos, puertos y enlaces sin detalles de Packet Tracer."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .capabilities import DeviceCandidateStatus, DeviceCapabilities, DeviceRequirement
from .roles import DeviceRole
from .topology import NetworkLayer, TopologyPattern


class PortClass(str, Enum):
    ACCESS_CAPABLE = "access_capable"
    UPLINK_CAPABLE = "uplink_capable"
    WAN = "wan"
    SERIAL = "serial"
    CONSOLE = "console"
    MANAGEMENT = "management"
    MODULE_PROVIDED = "module_provided"


class NormalizedPortSpeed(str, Enum):
    SPEED_10M = "10m"
    SPEED_100M = "100m"
    SPEED_1G = "1g"
    SPEED_10G = "10g"
    UNKNOWN = "unknown"


class PortDescriptor(BaseModel):
    name: str
    classes: list[PortClass] = Field(default_factory=list)
    speed: NormalizedPortSpeed = NormalizedPortSpeed.UNKNOWN
    poe: bool | None = None
    source: str = "catalog"
    slot: str = ""
    module: str | None = None


class ModuleInstallation(BaseModel):
    module: str
    provided_ports: list[str] = Field(default_factory=list)
    slot: str | None = None


class EndpointGroupSlice(BaseModel):
    group_id: str
    roles: list[DeviceRole]
    start_index: int
    count: int
    requires_poe: bool = False


class PortAssignmentRange(BaseModel):
    device_id: str
    source_group: str
    roles: list[DeviceRole]
    start_index: int
    count: int
    first_port: str
    last_port: str
    requires_poe: bool = False


class LinkRole(str, Enum):
    ACCESS_LINK = "access_link"
    UPLINK = "uplink"
    DISTRIBUTION_LINK = "distribution_link"
    CORE_LINK = "core_link"
    EDGE_LINK = "edge_link"
    WAN_LINK = "wan_link"
    REDUNDANT_LINK = "redundant_link"


class HardwareLinkRequirement(BaseModel):
    source_device: str
    target_device: str
    link_role: LinkRole
    source_port: str | None = None
    target_port: str | None = None
    redundancy_group: str | None = None
    required_port_class: PortClass = PortClass.UPLINK_CAPABLE


class ResiliencyLevel(str, Enum):
    NONE = "none"
    BASIC = "basic"
    HIGH = "high"


class HierarchyMode(str, Enum):
    FLAT = "flat"
    COLLAPSED_CORE = "collapsed_core"
    THREE_TIER = "three_tier"


class HardwarePlanStatus(str, Enum):
    VALID = "valid"
    PARTIALLY_RESOLVED = "partially_resolved"
    UNRESOLVED = "unresolved"


class CatalogCoverageReport(BaseModel):
    known_in_enterprise: list[str] = Field(default_factory=list)
    known_in_base_catalog: list[str] = Field(default_factory=list)
    unclassified: list[str] = Field(default_factory=list)
    aliases: dict[str, str] = Field(default_factory=dict)
    capability_gaps: dict[str, list[str]] = Field(default_factory=dict)


class PlannedNetworkDevice(BaseModel):
    id: str
    site_id: str
    role: DeviceRole
    network_layer: NetworkLayer
    selection_status: DeviceCandidateStatus
    selected_model: str | None = None
    provisional_model: str | None = None
    candidate_models: list[str] = Field(default_factory=list)
    required_capabilities: DeviceRequirement | None = None
    port_capacity: int = 0
    poe_capacity: int | None = None
    port_descriptors: list[PortDescriptor] = Field(default_factory=list)
    module_plan: list[ModuleInstallation] = Field(default_factory=list)
    parent_group: str = ""
    redundancy_group: str | None = None
    warnings: list[str] = Field(default_factory=list)


class HardwareCandidate(BaseModel):
    """Entrada física para el planificador puro, normalmente construida por el adapter."""

    model: str
    capabilities: DeviceCapabilities
    ports: list[PortDescriptor] = Field(default_factory=list)


class AccessBlockPlan(BaseModel):
    site_id: str
    zone_id: str
    block_id: str
    switches: list[str] = Field(default_factory=list)
    endpoint_slices: list[EndpointGroupSlice] = Field(default_factory=list)
    port_assignments: list[PortAssignmentRange] = Field(default_factory=list)
    required_access_ports: int
    required_poe_ports: int
    required_uplinks: int
    warnings: list[str] = Field(default_factory=list)


class SiteHardwarePlan(BaseModel):
    site_id: str
    topology_pattern: TopologyPattern
    hierarchy_mode: HierarchyMode
    network_layers: list[NetworkLayer] = Field(default_factory=list)
    devices: list[PlannedNetworkDevice] = Field(default_factory=list)
    links: list[HardwareLinkRequirement] = Field(default_factory=list)
    access_blocks: list[AccessBlockPlan] = Field(default_factory=list)
    resiliency: ResiliencyLevel = ResiliencyLevel.BASIC
    warnings: list[str] = Field(default_factory=list)


class HardwarePlan(BaseModel):
    status: HardwarePlanStatus
    site_hardware: list[SiteHardwarePlan] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unsupported_requirements: list[str] = Field(default_factory=list)

    def compact_summary(self) -> dict[str, int | str]:
        devices = [device for site in self.site_hardware for device in site.devices]
        links = [link for site in self.site_hardware for link in site.links]
        return {
            "sites": len(self.site_hardware),
            "network_devices": len(devices),
            "access_switches": sum(device.role is DeviceRole.ACCESS_SWITCH for device in devices),
            "distribution_switches": sum(device.role is DeviceRole.DISTRIBUTION_SWITCH for device in devices),
            "core_switches": sum(device.role is DeviceRole.CORE_SWITCH for device in devices),
            "routers": sum(device.role in {DeviceRole.EDGE_ROUTER, DeviceRole.WAN_ROUTER} for device in devices),
            "module_count": sum(len(device.module_plan) for device in devices),
            "planned_access_ports": sum(block.required_access_ports for site in self.site_hardware for block in site.access_blocks),
            "planned_poe_ports": sum(block.required_poe_ports for site in self.site_hardware for block in site.access_blocks),
            "uplink_count": sum(link.link_role is LinkRole.UPLINK for link in links),
            "redundant_links": sum(link.redundancy_group is not None for link in links),
            "warnings": len(self.warnings) + sum(len(site.warnings) for site in self.site_hardware),
        }
