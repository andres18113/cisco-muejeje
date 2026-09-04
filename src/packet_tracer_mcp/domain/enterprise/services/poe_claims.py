"""PoE delivery claim boundaries shared by discovery and evidence reuse."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from ..models.capabilities import CapabilityStatus, EvidenceSource
from ..models.discovery import RuntimePortDescriptor


POE_ACCESS_PORT_COUNT = "poe_access_port_count"
POE_CONTROL_SUPPORTED_PORTS = "poe_control_supported_ports"
POE_DELIVERY_TESTED_PORTS = "poe_delivery_tested_ports"
POE_DELIVERY_ACTIVE_PORTS = "poe_delivery_active_ports"

_POE_DELIVERY_EVIDENCE_SOURCES = frozenset({
    EvidenceSource.STATIC_OVERRIDE,
    EvidenceSource.PACKET_TRACER_RUNTIME,
    EvidenceSource.CONTROLLED_PROBE,
    EvidenceSource.MANUAL_VERIFICATION,
})


@dataclass(frozen=True)
class PoEDeliveryAssessment:
    """What one simultaneous access-port observation can actually authorize."""

    access_port_count: int
    control_supported_ports: int
    delivery_tested_ports: int
    delivery_active_ports: int

    @property
    def status(self) -> CapabilityStatus:
        if self.delivery_active_ports:
            return CapabilityStatus.SUPPORTED
        if (
            self.access_port_count
            and self.delivery_tested_ports == self.access_port_count
        ):
            return CapabilityStatus.UNSUPPORTED
        return CapabilityStatus.UNKNOWN

    @property
    def observed_value(self) -> int | None:
        if self.status is CapabilityStatus.SUPPORTED:
            return self.delivery_active_ports
        return None

    @property
    def dimensions(self) -> dict[str, str]:
        return {
            POE_ACCESS_PORT_COUNT: str(self.access_port_count),
            POE_CONTROL_SUPPORTED_PORTS: str(self.control_supported_ports),
            POE_DELIVERY_TESTED_PORTS: str(self.delivery_tested_ports),
            POE_DELIVERY_ACTIVE_PORTS: str(self.delivery_active_ports),
        }


def assess_poe_delivery(
    access_ports: Iterable[RuntimePortDescriptor],
) -> PoEDeliveryAssessment:
    """Separate controllable power state from observed endpoint delivery."""

    ports = tuple(access_ports)
    return PoEDeliveryAssessment(
        access_port_count=len(ports),
        control_supported_ports=sum(
            port.poe_status is CapabilityStatus.SUPPORTED for port in ports
        ),
        delivery_tested_ports=sum(
            port.power_delivery_active is not None for port in ports
        ),
        delivery_active_ports=sum(
            port.power_delivery_active is True for port in ports
        ),
    )


class PoEClaim(Protocol):
    capability: str
    status: CapabilityStatus
    verified: bool
    observed_value: int | None
    dimensions: Mapping[str, str]


def poe_claim_has_delivery_basis(result: PoEClaim) -> bool:
    """Accept strong reusable PoE claims only with coherent delivery counts."""

    if result.capability != "supports_poe":
        return True
    if result.status is CapabilityStatus.UNKNOWN:
        return True
    if not result.verified:
        return False
    if _claim_source(result) not in _POE_DELIVERY_EVIDENCE_SOURCES:
        return False

    dimensions = result.dimensions
    access = _non_negative_int(dimensions, POE_ACCESS_PORT_COUNT)
    tested = _non_negative_int(dimensions, POE_DELIVERY_TESTED_PORTS)
    active = _non_negative_int(dimensions, POE_DELIVERY_ACTIVE_PORTS)
    if access is None or tested is None or active is None:
        return False
    if active > tested or tested > access:
        return False
    if result.status is CapabilityStatus.SUPPORTED:
        return active > 0 and result.observed_value == active
    return access > 0 and tested == access and active == 0


def _claim_source(result: PoEClaim) -> EvidenceSource | None:
    source = getattr(result, "source", None)
    if source is None:
        source = getattr(result, "evidence_source", None)
    return source if isinstance(source, EvidenceSource) else None


def _non_negative_int(dimensions: Mapping[str, str], key: str) -> int | None:
    raw = dimensions.get(key)
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 and str(value) == raw else None
