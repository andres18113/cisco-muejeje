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
from .evidence import CapabilityReadiness, EvidenceRecord, ReadinessStatus


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

    # Distinto de NOT_SUPPORTED: nadie demostró que falle, pero tampoco que
    # funcione. Bloquea la mutación productiva sin declarar nada falso.
    LINK_MODE_NOT_VERIFIED = "link_mode_not_verified"

    # El plan cabía en el techo planificado; lo que el runtime negoció, no.
    LINK_CAPACITY_BELOW_REQUIREMENT = "link_capacity_below_requirement"
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
# El techo sale de una reproducción controlada, no de una tabla Cisco asumida.
# Qué backend la produjo y con qué hardware es dato del catálogo, no de aquí:
# el perfil medido vive junto a los demás perfiles de infraestructura. Un
# backend que soporte más lo declara por `supported_serial_rates_bps`, que es
# parámetro del planner precisamente para no fijar aquí ninguno.
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


class LinkModeContext(str, Enum):
    """Estado en que se midió una combinación. Un rechazo puede depender de él.

    Medido: `duplex half` sobre un Gigabit se rechaza "when speed
    autonegotiation subset contains 1Gbps". El propio backend condiciona su
    negativa, así que guardarla sin el contexto la convierte en una prohibición
    universal que nadie demostró.
    """

    LINKED = "linked"
    UNLINKED = "unlinked"
    UNSPECIFIED = "unspecified"


class LinkModeOutcome(str, Enum):
    """Grados de lo que se midió. Cada salto exige más que el anterior.

    Aceptar no es aplicar, y aplicar no es observar el modo resultante: el CLI
    acepta `speed 100` en un puerto Gigabit enlazado sin que nada cambie, ni
    siquiera tras rebotar el enlace.
    """

    NOT_MEASURED = "not_measured"
    COMMAND_REJECTED = "command_rejected"
    COMMAND_ACCEPTED = "command_accepted"
    CONFIG_APPLIED = "config_applied"
    MODE_EFFECT_OBSERVED = "mode_effect_observed"
    MODE_BEHAVIOR_VERIFIED = "mode_behavior_verified"


class BandwidthProvenance(str, Enum):
    """De dónde viene el `bandwidth` leído, que decide si sirve de evidencia.

    Medido: sobre un 2911, `bandwidth 5000` deja el BW en 5000 con la
    autonegociación desactivada mientras el enlace sigue físicamente a 1 Gbps.
    Leer esa cifra como capacidad daría 5 Mbps para un enlace de 1 Gbps.

    `PLATFORM_TRACKED` exige dos cosas a la vez: que la plataforma siga
    derivando el valor, y que el perfil medido de ese backend haya demostrado
    que lo deriva de la negociación. Una sola de las dos no basta.
    """

    PLATFORM_TRACKED = "platform_tracked"
    EXPLICITLY_CONFIGURED = "explicitly_configured"
    UNKNOWN = "unknown"


class NominalCapacitySource(str, Enum):
    """De dónde sale la capacidad nominal. No todas valen lo mismo.

    `PORT_CLASS` es la clase del puerto según su nombre: un techo teórico, no
    una medición. Nunca puede derivarse de un getter de bandwidth, que es
    metadata de routing.
    """

    CATALOG_DECLARATION = "catalog_declaration"
    PORT_CLASS = "port_class"
    CONTROLLED_RUNTIME_OBSERVATION = "controlled_runtime_observation"
    UNKNOWN = "unknown"


class LinkModeObservation(BaseModel):
    """Una combinación medida, con su contexto y su registro de evidencia.

    La provenance no se duplica aquí: vive en el `EvidenceRecord`, que ya es el
    vocabulario compartido de E9.5.
    """

    speed: LinkSpeedMode
    duplex: DuplexMode
    context: LinkModeContext = LinkModeContext.UNSPECIFIED
    outcome: LinkModeOutcome = LinkModeOutcome.NOT_MEASURED
    evidence: EvidenceRecord | None = None
    prerequisite: str = ""

    def matches(
        self, speed: LinkSpeedMode, duplex: DuplexMode, context: LinkModeContext,
    ) -> bool:
        if self.speed is not speed or self.duplex is not duplex:
            return False
        if self.context is LinkModeContext.UNSPECIFIED:
            return True
        return context in (self.context, LinkModeContext.UNSPECIFIED)


def _readiness(
    compile_status: ReadinessStatus,
    apply_status: ReadinessStatus,
    verify_status: ReadinessStatus,
    capability: str,
    reason: str,
) -> CapabilityReadiness:
    return CapabilityReadiness(
        capability=capability,
        compile=compile_status,
        apply=apply_status,
        verify=verify_status,
        reasons={"apply": [reason], "verify": [reason]},
    )


class EthernetLinkModeCapability(BaseModel):
    """Qué hizo un backend concreto con un tipo de puerto concreto.

    Genérico a propósito: los valores los rellena un adaptador de
    infraestructura. Este módulo no sabe qué backends existen.

    `nominal_capacity_bps` es un techo teórico y lleva su procedencia al lado
    precisamente porque no es una medición del enlace.
    """

    backend_version: str = ""
    device_model: str = ""
    port_kind: str = ""
    nominal_capacity_bps: int = 0
    nominal_capacity_source: NominalCapacitySource = NominalCapacitySource.UNKNOWN
    observations: tuple[LinkModeObservation, ...] = ()

    # Sólo cierto donde se comprobó que el bandwidth de routing sigue a la tasa
    # negociada mientras nadie lo fije. Sin esa comprobación, leer el BW de un
    # modelo distinto sería extrapolar desde otra plataforma.
    bandwidth_tracks_negotiated_capacity: bool = False

    enumeration_complete: bool = False
    notes: str = ""

    def autonegotiation_observed(
        self, context: LinkModeContext = LinkModeContext.LINKED,
    ) -> bool:
        """¿Se vio a este puerto alcanzar su nominal negociando?"""
        return self.outcome_for(
            LinkSpeedMode.AUTO, DuplexMode.AUTO, context,
        ) in (
            LinkModeOutcome.MODE_EFFECT_OBSERVED,
            LinkModeOutcome.MODE_BEHAVIOR_VERIFIED,
        )

    def speed_is_forceable(
        self, speed: LinkSpeedMode, context: LinkModeContext = LinkModeContext.LINKED,
    ) -> bool:
        """Forzar una velocidad es otra cosa que negociarla.

        Medido en tres plataformas: el CLI acepta `speed` sobre un puerto
        enlazado y la capacidad no se mueve, ni siquiera tras rebotar el
        enlace. Aceptar no es forzar, y por eso esto exige efecto observado.
        """
        if speed is LinkSpeedMode.AUTO:
            return False
        return any(
            item.speed is speed
            and item.duplex is DuplexMode.AUTO
            and item.outcome in (
                LinkModeOutcome.MODE_EFFECT_OBSERVED,
                LinkModeOutcome.MODE_BEHAVIOR_VERIFIED,
            )
            and item.context in (context, LinkModeContext.UNSPECIFIED)
            for item in self.observations
        )

    def observation_for(
        self,
        speed: LinkSpeedMode,
        duplex: DuplexMode,
        context: LinkModeContext = LinkModeContext.UNSPECIFIED,
    ) -> LinkModeObservation | None:
        """La medición más específica que cubra esta combinación y contexto."""
        exact = [
            item for item in self.observations
            if item.matches(speed, duplex, context)
            and item.context is not LinkModeContext.UNSPECIFIED
        ]
        if exact:
            return exact[0]
        for item in self.observations:
            if item.matches(speed, duplex, context):
                return item
        return None

    def outcome_for(
        self,
        speed: LinkSpeedMode,
        duplex: DuplexMode,
        context: LinkModeContext = LinkModeContext.UNSPECIFIED,
    ) -> LinkModeOutcome:
        observation = self.observation_for(speed, duplex, context)
        return observation.outcome if observation else LinkModeOutcome.NOT_MEASURED

    def readiness_for(
        self,
        speed: LinkSpeedMode,
        duplex: DuplexMode,
        context: LinkModeContext = LinkModeContext.UNSPECIFIED,
    ) -> CapabilityReadiness:
        """Traduce la medición a los tres ejes que E9.5 ya usa.

        La distinción que importa está en `apply`: sin medición, compilar la
        intención es legítimo pero mutar el runtime no lo es. `UNKNOWN` no es
        `UNSUPPORTED`, y tampoco es permiso.
        """
        capability = f"ethernet_link_mode/{speed.value}/{duplex.value}"
        outcome = self.outcome_for(speed, duplex, context)
        if outcome is LinkModeOutcome.COMMAND_REJECTED:
            return _readiness(
                ReadinessStatus.UNSUPPORTED, ReadinessStatus.UNSUPPORTED,
                ReadinessStatus.UNSUPPORTED, capability,
                "The backend rejected this combination in the measured context.",
            )
        if outcome in (
            LinkModeOutcome.MODE_EFFECT_OBSERVED,
            LinkModeOutcome.MODE_BEHAVIOR_VERIFIED,
        ):
            return _readiness(
                ReadinessStatus.READY, ReadinessStatus.READY, ReadinessStatus.READY,
                capability, "The mode was applied and its effect was read back.",
            )
        if outcome is LinkModeOutcome.CONFIG_APPLIED:
            return _readiness(
                ReadinessStatus.READY, ReadinessStatus.READY, ReadinessStatus.PARTIAL,
                capability,
                "The configuration took effect; the operational mode was not verified.",
            )
        if outcome is LinkModeOutcome.COMMAND_ACCEPTED:
            return _readiness(
                ReadinessStatus.READY, ReadinessStatus.PARTIAL, ReadinessStatus.UNKNOWN,
                capability,
                "The command was accepted with no observed effect: acceptance is "
                "not proof that the mode can be forced.",
            )
        return _readiness(
            ReadinessStatus.READY, ReadinessStatus.UNKNOWN, ReadinessStatus.UNKNOWN,
            capability,
            "This combination was never measured on this backend.",
        )


def port_kind_of(interface: str) -> str:
    """`GigabitEthernet0/1` -> `GigabitEthernet`. Sin número no hay tipo."""
    name = (interface or "").strip()
    head = name.split("/", 1)[0]
    return head.rstrip("0123456789 ")


def nominal_link_ceiling_bps(
    local: EthernetLinkModeCapability | None,
    peer: EthernetLinkModeCapability | None,
) -> int | None:
    """Techo teórico: el menor de los dos nominales. No es un techo verificado.

    Con un solo extremo conocido no hay techo, porque media evidencia no
    autoriza a afirmar la capacidad de un enlace.
    """
    nominals = [
        capability.nominal_capacity_bps
        for capability in (local, peer)
        if capability is not None and capability.nominal_capacity_bps > 0
    ]
    return min(nominals) if len(nominals) >= 2 else None


def auto_negotiable_ceiling_bps(
    local: EthernetLinkModeCapability | None,
    peer: EthernetLinkModeCapability | None,
    *,
    context: LinkModeContext = LinkModeContext.LINKED,
) -> int | None:
    """Capacidad que el enlace alcanza NEGOCIANDO, no forzando.

    Son cosas distintas y divergen: sobre un enlace Gigabit contra Gigabit la
    negociación llega a 1 Gbps mientras forzar `speed 100` no mueve nada. Usar
    una por la otra sobreafirma en un sentido y subestima en el otro.

    Exige haber visto negociar a los DOS extremos; entonces el techo es el
    menor de sus nominales, que es lo que se observó en cada combinación
    medida. Sin esa evidencia el resultado es None: desconocido, no cero.
    """
    if local is None or peer is None:
        return None
    if not (local.autonegotiation_observed(context) and peer.autonegotiation_observed(context)):
        return None
    nominals = [
        side.nominal_capacity_bps for side in (local, peer)
        if side.nominal_capacity_bps > 0
    ]
    return min(nominals) if len(nominals) == 2 else None


def forceable_speed_ceiling_bps(
    local: EthernetLinkModeCapability | None,
    peer: EthernetLinkModeCapability | None,
    *,
    speed_capacity: "dict[LinkSpeedMode, int]",
    context: LinkModeContext = LinkModeContext.LINKED,
) -> int | None:
    """La mayor velocidad que AMBOS extremos demostraron poder FORZAR.

    Distinta de la negociable: aquí no cuenta que el CLI aceptara el comando,
    sino que el efecto se volviera a leer. Devuelve None cuando ningún extremo
    demostró forzar ninguna, que es el caso en todo lo medido hasta ahora.
    """
    if local is None or peer is None:
        return None
    realizable = [
        capacity
        for speed, capacity in speed_capacity.items()
        if all(side.speed_is_forceable(speed, context) for side in (local, peer))
    ]
    return max(realizable) if realizable else None


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
    link_context: LinkModeContext = LinkModeContext.LINKED

    # Una exploración controlada puede pedir lo que no está medido; la
    # operación productiva no. Son dos rutas y no deben confundirse.
    allow_unverified_mode_exploration: bool = False

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

    # Si la velocidad se fija de verdad o simplemente coincide con la que el
    # enlace negocia. Sólo lo primero justifica emitir un comando `speed`.
    speed_forced: bool = False

    # Tres techos que no son el mismo. El nominal es teórico; el negociable es
    # lo que la autonegociación alcanza con evidencia en ambos extremos; el
    # forzable es lo que ambos demostraron poder fijar a mano. Divergen: un
    # enlace Gigabit negocia 1 Gbps y no deja forzar ninguna velocidad.
    nominal_link_ceiling_bps: int | None = None
    auto_negotiable_ceiling_bps: int | None = None
    forceable_speed_ceiling_bps: int | None = None

    # Readiness del modo pedido sobre este enlace, en los tres ejes de E9.5.
    mode_readiness: CapabilityReadiness | None = None

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
            "nominal_link_ceiling_bps": self.nominal_link_ceiling_bps,
            "auto_negotiable_ceiling_bps": self.auto_negotiable_ceiling_bps,
            "forceable_speed_ceiling_bps": self.forceable_speed_ceiling_bps,
            "mode_apply_readiness": (
                self.mode_readiness.apply.value if self.mode_readiness else ""
            ),
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
    """Lo que el runtime hizo. No reescribe intent ni plan.

    Tres canales que no valen lo mismo y por eso no comparten campo:

    * `reported_speed` es lo que el texto del CLI imprime. Es el más débil:
      medido, un enlace Gigabit contra Gigabit informa "100Mbps" mientras su
      bandwidth de routing dice 1 Gbps, y un puerto sin cable informa una
      velocidad igualmente.
    * `routing_bandwidth_kbps` es metadata de routing. Con
      `bandwidth_autonegotiated` activo espeja la tasa negociada, y ahí es la
      mejor evidencia disponible de la capacidad efectiva -- indirecta, no
      directa. En cuanto alguien fija `bandwidth`, deja de espejarla.
    * `duplex_autonegotiated` y `full_duplex` salen del objeto de puerto y sí
      distinguen un modo forzado de uno negociado.
    """

    link_id: str
    reported_speed: LinkSpeedMode | None = None
    reported_duplex: DuplexMode | None = None
    routing_bandwidth_kbps: int | None = None
    bandwidth_autonegotiated: bool | None = None
    bandwidth_provenance: BandwidthProvenance = BandwidthProvenance.UNKNOWN
    duplex_autonegotiated: bool | None = None
    full_duplex: bool | None = None
    line_protocol_up: bool | None = None
    observed: bool = False

    @property
    def effective_capacity_bps(self) -> int | None:
        """Capacidad inferida, sólo con la procedencia que la sostiene.

        Tres condiciones, y ninguna sobra: la plataforma tiene que seguir
        derivando el valor (`PLATFORM_TRACKED`, que ya incluye el aval del
        perfil medido), el enlace tiene que estar arriba, y tiene que haber
        una cifra. Con la procedencia desconocida no se infiere nada.
        """
        if not self.observed:
            return None
        if self.bandwidth_provenance is not BandwidthProvenance.PLATFORM_TRACKED:
            return None
        if not self.routing_bandwidth_kbps or not self.line_protocol_up:
            return None
        return self.routing_bandwidth_kbps * 1000

    @classmethod
    def from_runtime(
        cls,
        link_id: str,
        *,
        capability: EthernetLinkModeCapability | None,
        routing_bandwidth_kbps: int | None,
        bandwidth_autonegotiated: bool | None,
        duplex_autonegotiated: bool | None = None,
        full_duplex: bool | None = None,
        line_protocol_up: bool | None = None,
        reported_speed: LinkSpeedMode | None = None,
        reported_duplex: DuplexMode | None = None,
    ) -> "ObservedLinkPerformance":
        """Resuelve la procedencia una sola vez, donde se conoce el perfil.

        Sin perfil medido para este modelo y puerto, la procedencia es
        `UNKNOWN` aunque la plataforma diga que autonegocia: que otro backend
        derive el bandwidth de la negociación no dice nada de este.
        """
        if bandwidth_autonegotiated is None:
            provenance = BandwidthProvenance.UNKNOWN
        elif not bandwidth_autonegotiated:
            provenance = BandwidthProvenance.EXPLICITLY_CONFIGURED
        elif capability is not None and capability.bandwidth_tracks_negotiated_capacity:
            provenance = BandwidthProvenance.PLATFORM_TRACKED
        else:
            provenance = BandwidthProvenance.UNKNOWN
        return cls(
            link_id=link_id,
            reported_speed=reported_speed,
            reported_duplex=reported_duplex,
            routing_bandwidth_kbps=routing_bandwidth_kbps,
            bandwidth_autonegotiated=bandwidth_autonegotiated,
            bandwidth_provenance=provenance,
            duplex_autonegotiated=duplex_autonegotiated,
            full_duplex=full_duplex,
            line_protocol_up=line_protocol_up,
            observed=True,
        )

    def meets(self, minimum_capacity_bps: int | None) -> bool | None:
        """None cuando no hay evidencia suficiente: desconocido no es fallo."""
        if not minimum_capacity_bps:
            return None
        effective = self.effective_capacity_bps
        return None if effective is None else effective >= minimum_capacity_bps
