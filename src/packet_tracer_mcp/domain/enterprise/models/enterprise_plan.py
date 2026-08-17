"""Plan Enterprise lógico; no contiene CLI ni detalles de Packet Tracer."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .addressing import AddressingPlan
from .capabilities import DeviceRequirement, DeviceSelectionResult
from .capacity import AccessCapacityRequirement
from .hierarchy import BuildingPlan, ZonePlan
from .intent import SiteType
from .requirements import EndpointRequirement, ServiceRequirement, WanLinkRequirement
from .segments import NetworkSegment
from .topology import TopologyDesign
from .link_performance import TrafficFlowIntent


class SitePlan(BaseModel):
    name: str
    site_id: str
    type: SiteType
    segments: list[NetworkSegment] = Field(default_factory=list)
    endpoint_requirements: list[EndpointRequirement] = Field(default_factory=list)
    device_requirements: list[DeviceRequirement] = Field(default_factory=list)
    selected_devices: list[DeviceSelectionResult] = Field(default_factory=list)
    services: list[ServiceRequirement] = Field(default_factory=list)
    uplinks: list[WanLinkRequirement] = Field(default_factory=list)
    growth_percent: float = 0.0
    buildings: list[BuildingPlan] = Field(default_factory=list)
    default_zone: ZonePlan | None = None
    topology: TopologyDesign | None = None
    address_block: str | None = None
    pair_pc_with_ip_phone: bool = True
    capacity_requirements: list[AccessCapacityRequirement] = Field(default_factory=list)


class EnterprisePlan(BaseModel):
    """Diseño lógico completo, listo para que E2 lo concrete a TopologyPlan."""

    id: str
    name: str
    sites: list[SitePlan] = Field(default_factory=list)
    address_space: str | None = None
    internet_required: bool = False
    services: list[ServiceRequirement] = Field(default_factory=list)
    security_policies: list[str] = Field(default_factory=list)
    acceptance_requirements: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    addressing: AddressingPlan | None = None
    traffic_flows: list[TrafficFlowIntent] = Field(default_factory=list)

    def compact_summary(self) -> dict[str, int | str]:
        """Resumen calculado bajo demanda para futuras respuestas MCP de bajo consumo."""
        capacity = [item for site in self.sites for item in site.capacity_requirements]
        return {
            "enterprise": self.name,
            "sites": len(self.sites),
            "logical_endpoints": sum(
                segment.host_requirement for site in self.sites for segment in site.segments
            ),
            "segments": sum(len(site.segments) for site in self.sites),
            "required_access_ports": sum(item.required_access_ports for item in capacity),
            "required_poe_ports": sum(item.required_poe_ports for item in capacity),
        }
