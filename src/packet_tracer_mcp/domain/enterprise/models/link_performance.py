"""Semántica backend-neutral de capacidad y modo de enlace.

Separa tres niveles que hasta ahora se confundían en un solo número:

    REQUESTED   lo que pidió el intent o la política
    EFFECTIVE   lo que el planner decidió y el compiler va a aplicar
    OBSERVED    lo que el runtime negoció y volvió a leer

La observación nunca reescribe la petición ni el plan. Y separa dos hechos que
comparten unidades pero no significado: el reloj físico del extremo DCE de un
serial, y el ancho de banda lógico que IOS usa para métricas de routing.

No hay strings IOS ni nombres de modelo de Packet Tracer en este módulo.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .compilation import ConcreteLinkRole


class LinkMedia(str, Enum):
    SERIAL = "serial"
    ETHERNET = "ethernet"
    UNKNOWN = "unknown"


class CapacitySource(str, Enum):
    """De dónde salió la capacidad elegida, en orden de precedencia.

    Un valor sin fuente es un default silencioso, y un default silencioso no
    puede explicarse ni auditarse.
    """

    EXPLICIT_USER = "explicit_user"
    LINK_POLICY = "link_policy"
    SERVICE_REQUIREMENT = "service_requirement"
    TOPOLOGY_ROLE_POLICY = "topology_role_policy"
    MEDIA_DEFAULT_POLICY = "media_default_policy"
    ENTERPRISE_FALLBACK = "enterprise_fallback"
    UNRESOLVED = "unresolved"


_SOURCE_PRECEDENCE: tuple[CapacitySource, ...] = (
    CapacitySource.EXPLICIT_USER,
    CapacitySource.LINK_POLICY,
    CapacitySource.SERVICE_REQUIREMENT,
    CapacitySource.TOPOLOGY_ROLE_POLICY,
    CapacitySource.MEDIA_DEFAULT_POLICY,
    CapacitySource.ENTERPRISE_FALLBACK,
)


def capacity_source_rank(source: CapacitySource) -> int:
    """Menor es más fuerte; una fuente no reconocida nunca gana."""
    try:
        return _SOURCE_PRECEDENCE.index(source)
    except ValueError:
        return len(_SOURCE_PRECEDENCE)


class LinkSpeedMode(str, Enum):
    AUTO = "auto"
    SPEED_10M = "10m"
    SPEED_100M = "100m"
    SPEED_1G = "1g"


class DuplexMode(str, Enum):
    AUTO = "auto"
    FULL = "full"
    HALF = "half"


class SerialEndpointRole(str, Enum):
    """Qué extremo entrega el reloj. Nunca se deduce del hostname."""

    DCE = "dce"
    DTE = "dte"
    UNKNOWN = "unknown"


class LinkPerformanceIssueCode(str, Enum):
    LINK_CAPACITY_INSUFFICIENT = "link_capacity_insufficient"
    DUPLEX_MISMATCH = "duplex_mismatch"
    SPEED_MISMATCH = "speed_mismatch"
    SPEED_NOT_SUPPORTED = "speed_not_supported"
    DCE_ENDPOINT_UNRESOLVED = "dce_endpoint_unresolved"
    MEDIA_UNKNOWN = "media_unknown"


class LinkPerformanceIssue(BaseModel):
    code: LinkPerformanceIssueCode
    link_id: str = ""
    message: str = ""


class TrafficContribution(BaseModel):
    """Un flujo que efectivamente atraviesa este enlace.

    El alcance importa: sumar todos los endpoints de un sitio a un enlace que
    no transportan es tan erróneo como ignorar los que sí.
    """

    source_id: str
    per_unit_bps: int = 0
    units: int = 1
    concurrency: float = 1.0

    @property
    def demand_bps(self) -> int:
        if self.per_unit_bps <= 0 or self.units <= 0:
            return 0
        concurrency = max(0.0, min(1.0, self.concurrency))
        return int(self.per_unit_bps * self.units * concurrency)


class HeadroomPolicy(BaseModel):
    """Reserva de ingeniería de tráfico, distinta de la reserva de crecimiento.

    El 25% es política de este proyecto, no una constante de Cisco: se declara
    aquí para poder cambiarla en un sitio y explicarla en el resultado.
    """

    engineering_headroom_percent: float = 25.0

    def engineered_bps(self, demand_bps: int) -> int:
        if demand_bps <= 0:
            return 0
        factor = 1.0 + max(0.0, self.engineering_headroom_percent) / 100.0
        return int(-(-demand_bps * factor // 1))


# Tasas serial que este proyecto considera seleccionables por política. 64k y
# 128k siguen siendo configuraciones explícitas válidas; simplemente no son el
# fallback de una WAN empresarial sin información de tráfico.
SUPPORTED_SERIAL_RATES_BPS: tuple[int, ...] = (
    64_000, 128_000, 256_000, 512_000,
    1_000_000, 2_000_000, 4_000_000, 8_000_000,
)
ENTERPRISE_SERIAL_FALLBACK_BPS = 2_000_000

_ETHERNET_CAPACITY_BPS: dict[LinkSpeedMode, int] = {
    LinkSpeedMode.SPEED_10M: 10_000_000,
    LinkSpeedMode.SPEED_100M: 100_000_000,
    LinkSpeedMode.SPEED_1G: 1_000_000_000,
}


def ethernet_capacity_bps(speed: LinkSpeedMode) -> int:
    return _ETHERNET_CAPACITY_BPS.get(speed, 0)


class LinkPerformanceIntent(BaseModel):
    """Lo que se pidió, sin resolver todavía nada."""

    link_id: str
    media: LinkMedia = LinkMedia.UNKNOWN
    role: ConcreteLinkRole | None = None
    requested_capacity_bps: int | None = None
    minimum_capacity_bps: int | None = None
    requested_speed: LinkSpeedMode = LinkSpeedMode.AUTO
    requested_duplex: DuplexMode = DuplexMode.AUTO
    traffic: list[TrafficContribution] = Field(default_factory=list)
    failure_survival_bps: int | None = None
    sync_routing_bandwidth_to_effective_capacity: bool = False
    peer_supported_speeds: list[LinkSpeedMode] = Field(default_factory=list)
    peer_duplex: DuplexMode | None = None
    dce_endpoint_device_id: str = ""
    dte_endpoint_device_id: str = ""


class LinkPerformanceDecision(BaseModel):
    """Resultado explicable: qué se eligió, por qué, y qué queda sin resolver."""

    link_id: str
    media: LinkMedia = LinkMedia.UNKNOWN
    role: ConcreteLinkRole | None = None

    requested_capacity_bps: int | None = None
    calculated_demand_bps: int = 0
    engineered_demand_bps: int = 0
    headroom_percent: float = 0.0
    supported_capacities_bps: list[int] = Field(default_factory=list)
    effective_capacity_bps: int | None = None
    capacity_source: CapacitySource = CapacitySource.UNRESOLVED
    selection_reason: str = ""

    effective_speed: LinkSpeedMode = LinkSpeedMode.AUTO
    effective_duplex: DuplexMode = DuplexMode.AUTO

    # Reloj físico del DCE frente a ancho de banda lógico de routing: uno no
    # sustituye al otro y por eso viajan en campos distintos.
    serial_clock_rate_bps: int | None = None
    routing_bandwidth_kbps: int | None = None
    dce_endpoint_device_id: str = ""
    dte_endpoint_device_id: str = ""

    issues: list[LinkPerformanceIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def applicable(self) -> bool:
        return not self.issues

    def explain(self) -> dict[str, object]:
        """Resumen compacto derivable; no una segunda API pública."""
        return {
            "link_id": self.link_id,
            "role": self.role.value if self.role else "",
            "media": self.media.value,
            "requested_capacity_bps": self.requested_capacity_bps,
            "calculated_demand_bps": self.calculated_demand_bps,
            "headroom_percent": self.headroom_percent,
            "engineered_demand_bps": self.engineered_demand_bps,
            "supported_capacities_bps": list(self.supported_capacities_bps),
            "selected_capacity_bps": self.effective_capacity_bps,
            "capacity_source": self.capacity_source.value,
            "reason": self.selection_reason,
            "speed": self.effective_speed.value,
            "duplex": self.effective_duplex.value,
            "routing_bandwidth_kbps": self.routing_bandwidth_kbps,
            "serial_clock_rate_bps": self.serial_clock_rate_bps,
            "dce": self.dce_endpoint_device_id,
            "dte": self.dte_endpoint_device_id,
            "issues": [item.code.value for item in self.issues],
            "warnings": list(self.warnings),
        }


class ObservedLinkPerformance(BaseModel):
    """Lo que el runtime negoció. No reescribe intent ni plan."""

    link_id: str
    observed_speed: LinkSpeedMode | None = None
    observed_duplex: DuplexMode | None = None
    observed_bandwidth_kbps: int | None = None
    observed: bool = False
