"""Capacidades de hardware con estados de evidencia explícitos."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .evidence import CapabilityReadiness
from .roles import DeviceRole


class CapabilityStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class EvidenceSource(str, Enum):
    CATALOG = "catalog"
    STATIC_OVERRIDE = "static_override"
    PACKET_TRACER_RUNTIME = "packet_tracer_runtime"
    CONTROLLED_PROBE = "controlled_probe"
    MANUAL_VERIFICATION = "manual_verification"
    INFERRED = "inferred"


class CapabilityEvidence(BaseModel):
    """Evidencia versionable para una capacidad; la prioridad es determinista."""

    capability: str
    status: CapabilityStatus
    source: EvidenceSource
    source_detail: str = ""
    packet_tracer_version: str | None = None
    confidence: str = ""
    verified: bool = False
    observed_value: int | None = None
    notes: str = ""


class DeviceCapabilities(BaseModel):
    """Hechos conocidos de un modelo físico y capacidades que aún requieren evidencia."""

    model: str
    category: str
    aliases: list[str] = Field(default_factory=list)
    port_count: int = 0
    ethernet_ports: int = 0
    fastethernet_ports: int = 0
    gigabit_ports: int = 0
    ten_gigabit_ports: int = 0
    serial_ports: int = 0
    supports_modules: CapabilityStatus = CapabilityStatus.UNKNOWN
    compatible_modules: list[str] = Field(default_factory=list)
    layer2: CapabilityStatus = CapabilityStatus.UNKNOWN
    layer3: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_vlan: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_trunk: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_svi: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_routing: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_static_routes: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_rip: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_eigrp: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_ospf: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_bgp: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_stp: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_acl: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_nat: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_dhcp_server: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_voice: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_cme: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_poe: CapabilityStatus = CapabilityStatus.UNKNOWN
    poe_ports: int | None = None
    supports_ipv6: CapabilityStatus = CapabilityStatus.UNKNOWN
    supports_wireless: CapabilityStatus = CapabilityStatus.UNKNOWN
    source: str = "catalog"
    packet_tracer_version: str | None = None
    verified: bool = False
    evidence: list[CapabilityEvidence] = Field(default_factory=list)
    capability_readiness: dict[str, CapabilityReadiness] = Field(default_factory=dict)

    @property
    def access_port_count(self) -> int:
        """Puertos ethernet físicos utilizables conocidos por el catálogo."""
        return self.ethernet_ports + self.fastethernet_ports + self.gigabit_ports + self.ten_gigabit_ports

    @property
    def uplink_port_count(self) -> int:
        """Uplinks de alta velocidad contables sin inferir soporte lógico."""
        return self.gigabit_ports + self.ten_gigabit_ports


class DeviceRequirement(BaseModel):
    """Restricciones mínimas para seleccionar un modelo para un rol lógico."""

    role: DeviceRole
    category: str | None = None
    min_access_ports: int = 0
    min_uplinks: int = 0
    poe_ports: int = 0
    requires_layer3: bool = False
    requires_modules: bool = False
    preferred_model: str | None = None


class DeviceSelectionStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"


class DeviceCandidateStatus(str, Enum):
    COMPATIBLE = "compatible"
    NEEDS_VERIFICATION = "needs_verification"
    INCOMPATIBLE = "incompatible"


class DeviceCandidate(BaseModel):
    model: str
    status: DeviceCandidateStatus
    missing_evidence: list[str] = Field(default_factory=list)
    rejected_reasons: list[str] = Field(default_factory=list)


class DeviceSelectionResult(BaseModel):
    """Resultado compacto, estable y explicable del selector."""

    status: DeviceSelectionStatus
    selected_model: str | None = None
    alternatives: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    candidates: list[DeviceCandidate] = Field(default_factory=list)
