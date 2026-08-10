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
    TRAFFIC_CALCULATION = "traffic_calculation"
    TOPOLOGY_ROLE_POLICY = "topology_role_policy"
    MEDIA_DEFAULT_POLICY = "media_default_policy"
    ENTERPRISE_FALLBACK = "enterprise_fallback"
    UNRESOLVED = "unresolved"


_SOURCE_PRECEDENCE: tuple[CapacitySource, ...] = (
    CapacitySource.EXPLICIT_USER,
    CapacitySource.LINK_POLICY,
    CapacitySource.SERVICE_REQUIREMENT,
    CapacitySource.TRAFFIC_CALCULATION,
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


class CapacityRequestMode(str, Enum):
    """Distingue "exactamente 3 Mbps" de "al menos 3 Mbps".

    Un minimo puede subir a la siguiente tasa soportada; una peticion exacta
    que el medio no soporta tiene que fallar, no aproximarse en silencio.
    """

    EXACT = "exact"
    MINIMUM = "minimum"


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
    EXACT_CAPACITY_UNSUPPORTED = "exact_capacity_unsupported"
    DUPLEX_MISMATCH = "duplex_mismatch"
    SPEED_MISMATCH = "speed_mismatch"
    SPEED_NOT_SUPPORTED = "speed_not_supported"
    DUPLEX_NOT_SUPPORTED = "duplex_not_supported"
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


# Tasas serial seleccionables por política. 64k y 128k siguen siendo
# configuraciones explícitas válidas; simplemente no son el fallback de una WAN
# empresarial sin información de tráfico.
#
# El techo sale de una reproducción controlada, no de una tabla Cisco asumida:
# sobre PT 9.0.1.0858, un 2911 con HWIC-2T aceptó y volvió a leer 64k, 128k,
# 2M y 4M, mientras 8M y 3M dejaron la interfaz en su valor anterior. Un
# backend que soporte más lo declara por `supported_serial_rates_bps`.
SUPPORTED_SERIAL_RATES_BPS: tuple[int, ...] = (
    64_000, 128_000, 256_000, 512_000,
    1_000_000, 2_000_000, 4_000_000,
)
ENTERPRISE_SERIAL_FALLBACK_BPS = 2_000_000

# Aritmética de unidades, no una afirmación sobre el backend: "100m" son
# 100 Mbps por definición del nombre. Que un puerto concreto acepte esa
# velocidad es una pregunta distinta, y la responde EthernetLinkModeCapability.
_ETHERNET_CAPACITY_BPS: dict[LinkSpeedMode, int] = {
    LinkSpeedMode.SPEED_10M: 10_000_000,
    LinkSpeedMode.SPEED_100M: 100_000_000,
    LinkSpeedMode.SPEED_1G: 1_000_000_000,
}


def ethernet_capacity_bps(speed: LinkSpeedMode) -> int:
    return _ETHERNET_CAPACITY_BPS.get(speed, 0)


class EncapsulationSource(str, Enum):
    """Nadie eligio PPP ni HDLC: se conservo lo que trae la plataforma."""

    PLATFORM_DEFAULT = "platform_default"
    EXPLICIT_POLICY = "explicit_policy"


class SerialClockCapability(BaseModel):
    """Tasas observadas sobre un backend/modelo/interfaz concretos.

    No es una tabla Cisco universal. `highest_verified_tested_rate_bps` es la
    mayor tasa que se aplico y volvio a leerse, no un maximo absoluto: sin una
    enumeracion completa del backend, lo que no se probo queda sin probar.
    """

    backend_version: str = ""
    device_model: str = ""
    interface_kind: str = ""
    verified_rates_bps: tuple[int, ...] = ()
    rejected_rates_bps: tuple[int, ...] = ()
    enumeration_complete: bool = False
    source: str = "controlled_probe"

    @property
    def highest_verified_tested_rate_bps(self) -> int | None:
        return max(self.verified_rates_bps) if self.verified_rates_bps else None


#: Perfil medido en E9.5 Stage 3A2. Es evidencia con procedencia, no una
#: constante del dominio: otro backend declara la suya.
PT_2911_HWIC2T_SERIAL_CLOCK = SerialClockCapability(
    backend_version="9.0.1.0858",
    device_model="2911",
    interface_kind="HWIC-2T Serial",
    verified_rates_bps=(64_000, 128_000, 2_000_000, 4_000_000),
    rejected_rates_bps=(3_000_000, 8_000_000),
    enumeration_complete=False,
)


class ModeEvidence(str, Enum):
    """Cuánto se sabe de un modo de enlace, sin colapsar los grados.

    Aceptar no es aplicar: el CLI puede tragarse ``speed 1000`` en un puerto ya
    negociado a 100 Mbps sin que nada cambie. Y no haber probado un valor no lo
    vuelve no soportado.
    """

    OBSERVED = "observed"      # se aplicó y el efecto se volvió a leer
    ACCEPTED = "accepted"      # el CLI no lo rechazó; el efecto no se observó
    REJECTED = "rejected"      # el CLI lo rechazó
    UNTESTED = "untested"      # nunca se midió


class EthernetLinkModeCapability(BaseModel):
    """Modos observados sobre un backend/modelo/tipo de puerto concretos.

    Mismo criterio que `SerialClockCapability`: no es una tabla Cisco, es lo
    que este backend hizo. `nominal_capacity_bps` es lo que el puerto declara
    por sí solo; lo que el enlace consigue depende también del otro extremo.
    """

    backend_version: str = ""
    device_model: str = ""
    port_kind: str = ""
    nominal_capacity_bps: int = 0
    observed_speeds: tuple[LinkSpeedMode, ...] = ()
    accepted_speeds: tuple[LinkSpeedMode, ...] = ()
    rejected_speeds: tuple[LinkSpeedMode, ...] = ()
    observed_duplex: tuple[DuplexMode, ...] = ()
    accepted_duplex: tuple[DuplexMode, ...] = ()
    rejected_duplex: tuple[DuplexMode, ...] = ()
    enumeration_complete: bool = False
    source: str = "controlled_probe"
    notes: str = ""

    def speed_evidence(self, speed: LinkSpeedMode) -> ModeEvidence:
        if speed in self.rejected_speeds:
            return ModeEvidence.REJECTED
        if speed in self.observed_speeds:
            return ModeEvidence.OBSERVED
        if speed in self.accepted_speeds:
            return ModeEvidence.ACCEPTED
        return ModeEvidence.UNTESTED

    def duplex_evidence(self, duplex: DuplexMode) -> ModeEvidence:
        if duplex in self.rejected_duplex:
            return ModeEvidence.REJECTED
        if duplex in self.observed_duplex:
            return ModeEvidence.OBSERVED
        if duplex in self.accepted_duplex:
            return ModeEvidence.ACCEPTED
        return ModeEvidence.UNTESTED


#: Perfiles medidos en E9.5 Stage 3A3 sobre PT 9.0.1.0858. Lo que no aparece
#: no está soportado ni sin soportar: está sin probar.
PT_2911_GIGABIT_LINK_MODE = EthernetLinkModeCapability(
    backend_version="9.0.1.0858",
    device_model="2911",
    port_kind="GigabitEthernet",
    nominal_capacity_bps=1_000_000_000,
    accepted_speeds=(
        LinkSpeedMode.AUTO, LinkSpeedMode.SPEED_10M,
        LinkSpeedMode.SPEED_100M, LinkSpeedMode.SPEED_1G,
    ),
    observed_duplex=(DuplexMode.FULL,),
    accepted_duplex=(DuplexMode.AUTO,),
    rejected_duplex=(DuplexMode.HALF,),
    enumeration_complete=False,
    notes=(
        "`duplex half` se rechaza mientras la negociación de velocidad incluya "
        "1 Gbps: \"%Duplex cannot be set to half when speed autonegotiation "
        "subset contains 1Gbps\". El rechazo es condicional, no absoluto."
    ),
)

PT_3560_FASTETHERNET_LINK_MODE = EthernetLinkModeCapability(
    backend_version="9.0.1.0858",
    device_model="3560-24PS",
    port_kind="FastEthernet",
    nominal_capacity_bps=100_000_000,
    accepted_speeds=(
        LinkSpeedMode.AUTO, LinkSpeedMode.SPEED_10M, LinkSpeedMode.SPEED_100M,
    ),
    rejected_speeds=(LinkSpeedMode.SPEED_1G,),
    observed_duplex=(DuplexMode.HALF, DuplexMode.FULL),
    accepted_duplex=(DuplexMode.AUTO,),
    enumeration_complete=False,
    notes="`speed 1000` responde \"% Invalid input\": el puerto no la ofrece.",
)

PT_3560_GIGABIT_LINK_MODE = EthernetLinkModeCapability(
    backend_version="9.0.1.0858",
    device_model="3560-24PS",
    port_kind="GigabitEthernet",
    nominal_capacity_bps=1_000_000_000,
    observed_speeds=(LinkSpeedMode.SPEED_10M, LinkSpeedMode.SPEED_1G),
    accepted_speeds=(LinkSpeedMode.AUTO, LinkSpeedMode.SPEED_100M),
    rejected_duplex=(DuplexMode.AUTO, DuplexMode.FULL, DuplexMode.HALF),
    enumeration_complete=False,
    notes=(
        "El uplink no acepta ninguna forma de `duplex`: las tres responden "
        "\"% Invalid input\". Medido con el puerto sin enlazar, donde el efecto "
        "de `speed` se observo en el bandwidth de routing que espeja el nominal "
        "mientras la autonegociacion sigue activa -- no en una tasa negociada, "
        "que sin cable no existe."
    ),
)

_LINK_MODE_CAPABILITIES: tuple[EthernetLinkModeCapability, ...] = (
    PT_2911_GIGABIT_LINK_MODE,
    PT_3560_FASTETHERNET_LINK_MODE,
    PT_3560_GIGABIT_LINK_MODE,
)


def port_kind_of(interface: str) -> str:
    """`GigabitEthernet0/1` -> `GigabitEthernet`. Sin número no hay tipo."""
    name = (interface or "").strip()
    head = name.split("/", 1)[0]
    return head.rstrip("0123456789 ")


def link_mode_capability_for(
    device_model: str, interface: str, *, backend_version: str = "",
) -> EthernetLinkModeCapability | None:
    """Perfil medido para este modelo y tipo de puerto, o None si no se midió.

    Devolver None es la respuesta correcta cuando no hay evidencia: no existe
    un perfil por defecto que "más o menos" valga para cualquier plataforma.
    """
    model = (device_model or "").strip().casefold()
    kind = port_kind_of(interface).casefold()
    for candidate in _LINK_MODE_CAPABILITIES:
        if candidate.device_model.casefold() != model:
            continue
        if candidate.port_kind.casefold() != kind:
            continue
        if backend_version and candidate.backend_version != backend_version:
            continue
        return candidate
    return None


class LinkPerformanceIntent(BaseModel):
    """Lo que se pidió, sin resolver todavía nada."""

    link_id: str
    media: LinkMedia = LinkMedia.UNKNOWN
    role: ConcreteLinkRole | None = None
    requested_capacity_bps: int | None = None
    requested_capacity_mode: CapacityRequestMode = CapacityRequestMode.MINIMUM
    minimum_capacity_bps: int | None = None
    requested_speed: LinkSpeedMode = LinkSpeedMode.AUTO
    requested_duplex: DuplexMode = DuplexMode.AUTO
    traffic: list[TrafficContribution] = Field(default_factory=list)
    failure_survival_bps: int | None = None
    sync_routing_bandwidth_to_effective_capacity: bool = False
    peer_supported_speeds: list[LinkSpeedMode] = Field(default_factory=list)
    peer_duplex: DuplexMode | None = None

    # Un enlace corre al menor de sus dos extremos: un Gig contra un Fa da
    # 100 Mbps, y eso no se deduce del extremo que se está configurando.
    local_port_capability: EthernetLinkModeCapability | None = None
    peer_port_capability: EthernetLinkModeCapability | None = None

    dce_endpoint_device_id: str = ""
    dte_endpoint_device_id: str = ""


class LinkPerformanceDecision(BaseModel):
    """Resultado explicable: qué se eligió, por qué, y qué queda sin resolver."""

    link_id: str
    media: LinkMedia = LinkMedia.UNKNOWN
    role: ConcreteLinkRole | None = None

    # Que politica produjo la decision. Un cambio de politica que altere el
    # comportamiento cambia esta identidad y, con ella, la del plan.
    policy_id: str = ""
    policy_version: str = ""

    requested_capacity_bps: int | None = None
    requested_capacity_mode: CapacityRequestMode = CapacityRequestMode.MINIMUM
    calculated_demand_bps: int = 0
    engineered_demand_bps: int = 0
    headroom_percent: float = 0.0
    supported_capacities_bps: list[int] = Field(default_factory=list)
    effective_capacity_bps: int | None = None
    capacity_source: CapacitySource = CapacitySource.UNRESOLVED
    selection_reason: str = ""

    effective_speed: LinkSpeedMode = LinkSpeedMode.AUTO
    effective_duplex: DuplexMode = DuplexMode.AUTO

    # Techo del enlace, no del puerto: el menor de los dos extremos cuando
    # ambos se conocen. None significa que falta un extremo, no que no haya
    # techo.
    link_ceiling_bps: int | None = None

    # Reloj físico del DCE frente a ancho de banda lógico de routing: uno no
    # sustituye al otro y por eso viajan en campos distintos.
    serial_clock_rate_bps: int | None = None
    routing_bandwidth_kbps: int | None = None
    dce_endpoint_device_id: str = ""
    dte_endpoint_device_id: str = ""
    encapsulation_source: EncapsulationSource = EncapsulationSource.PLATFORM_DEFAULT

    issues: list[LinkPerformanceIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def applicable(self) -> bool:
        return not self.issues

    def explain(self) -> dict[str, object]:
        """Resumen compacto derivable; no una segunda API pública."""
        return {
            "link_id": self.link_id,
            "policy": f"{self.policy_id}@{self.policy_version}",
            "role": self.role.value if self.role else "",
            "media": self.media.value,
            "requested_capacity_bps": self.requested_capacity_bps,
            "calculated_demand_bps": self.calculated_demand_bps,
            "headroom_percent": self.headroom_percent,
            "engineered_demand_bps": self.engineered_demand_bps,
            "supported_capacities_bps": list(self.supported_capacities_bps),
            "link_ceiling_bps": self.link_ceiling_bps,
            "selected_capacity_bps": self.effective_capacity_bps,
            "capacity_source": self.capacity_source.value,
            "reason": self.selection_reason,
            "speed": self.effective_speed.value,
            "duplex": self.effective_duplex.value,
            "routing_bandwidth_kbps": self.routing_bandwidth_kbps,
            "serial_clock_rate_bps": self.serial_clock_rate_bps,
            "encapsulation_source": self.encapsulation_source.value,
            "dce": self.dce_endpoint_device_id,
            "dte": self.dte_endpoint_device_id,
            "issues": [item.code.value for item in self.issues],
            "warnings": list(self.warnings),
        }


class ObservedLinkPerformance(BaseModel):
    """Lo que el runtime negoció. No reescribe intent ni plan.

    Velocidad física y `bandwidth` de routing viajan en campos distintos porque
    son independientes, igual que el reloj y el `bandwidth` de una serial.
    Medido en PT 9.0.1.0858: con `bandwidth 5000` sobre un enlace negociado a
    100 Mbps, `show interfaces` informa "BW 5000 Kbit" y "Full Duplex, 100Mbps"
    a la vez. Mientras nadie fije `bandwidth`, la metadata sigue a la tasa
    negociada -- y por eso leerla no prueba cuál es esa tasa.
    """

    link_id: str
    observed_speed: LinkSpeedMode | None = None
    observed_duplex: DuplexMode | None = None
    observed_bandwidth_kbps: int | None = None
    routing_bandwidth_autonegotiated: bool | None = None
    observed: bool = False
