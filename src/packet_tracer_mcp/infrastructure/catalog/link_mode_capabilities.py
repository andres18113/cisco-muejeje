"""Perfiles de modo de enlace medidos sobre Packet Tracer.

Este conocimiento es del backend, no del dominio: nombres de modelo, version de
Packet Tracer y combinaciones concretas de `speed`/`duplex` viven aqui, igual
que el catalogo de cables o de dispositivos. El dominio recibe
`EthernetLinkModeCapability` ya resuelto y no sabe que existe Packet Tracer.

Todo lo de abajo se midio en slices desechables sobre PT 9.0.1.0858 durante
E9.5 Stage 3A3, 3A3-B y 3A3-C. Lo que no aparece esta sin medir, que no es lo
mismo que no soportado.

Cuatro resultados condicionan como se lee esta tabla:

* `speed` sobre un puerto ENLAZADO se acepta sin ningun efecto observable, ni
  tras rebotar el enlace. Se reprodujo en 2911 Gig<->Gig, 2960 Gig<->Gig y
  2960 Fa<->Fa con `speed 10`, que era el unico caso con contrafactual. Sobre
  un puerto SIN enlazar el efecto si se observa; por eso las observaciones
  llevan contexto.
* negociar y forzar no dan la misma capacidad. Un enlace Gigabit negocia
  1 Gbps y no deja fijar ninguna velocidad. Confundirlos hacia que pedir
  100 Mbps sobre un enlace de 1 Gbps se diera por satisfecho.
* el rechazo de `duplex half` en un Gigabit cita el subset de autonegociacion,
  y se reprodujo despues de fijar `speed 100` y en tres plataformas. Se guarda
  como rechazo en contexto LINKED, no como prohibicion universal.
* `bandwidth_tracks_negotiated_capacity` solo se marca donde se comprobo la
  correlacion. En un router, `bandwidth 5000` deja el valor en 5000 con la
  autonegociacion desactivada mientras el enlace sigue a 1 Gbps; en un
  switchport de 2960 el comando ni existe.
"""

from __future__ import annotations

from ...domain.enterprise.models.evidence import (
    EvidenceFreshness,
    EvidenceRecord,
    EvidenceStrength,
    ObservationStatus,
    SupportStatus,
    VerificationMethod,
    VerificationStatus,
)
from ...domain.enterprise.models.link_performance import (
    DuplexMode,
    EthernetLinkModeCapability,
    LinkModeContext,
    LinkModeObservation,
    LinkModeOutcome,
    LinkSpeedMode,
    NominalCapacitySource,
    SerialClockCapability,
    port_kind_of,
)

#: Medido en E9.5 Stage 3A2. Vivia en el dominio por descuido: es conocimiento
#: de un backend concreto, igual que los perfiles Ethernet de abajo.
PT_2911_HWIC2T_SERIAL_CLOCK = SerialClockCapability(
    backend_version="9.0.1.0858",
    device_model="2911",
    interface_kind="HWIC-2T Serial",
    verified_rates_bps=(64_000, 128_000, 2_000_000, 4_000_000),
    rejected_rates_bps=(3_000_000, 8_000_000),
    enumeration_complete=False,
)

PACKET_TRACER_BACKEND = "packet_tracer"
MEASURED_BACKEND_VERSION = "9.0.1.0858"

_STAGE_3A3B = "e95-stage-3a3b"
_STAGE_3A3C = "e95-stage-3a3c"


def _evidence(
    identifier: str,
    subject: str,
    claim: str,
    *,
    method: VerificationMethod,
    support: SupportStatus,
    observation: ObservationStatus,
    verification: VerificationStatus,
    observed_value: object = None,
    limitations: tuple[str, ...] = (),
    stage: str = _STAGE_3A3B,
) -> EvidenceRecord:
    return EvidenceRecord(
        id=f"{stage}/{identifier}",
        subject=subject,
        claim=claim,
        method=method,
        strength=(
            EvidenceStrength.CLAIM_DIRECT
            if method is not VerificationMethod.NONE
            else EvidenceStrength.NONE
        ),
        source="controlled_probe",
        freshness=EvidenceFreshness.FRESH,
        backend=PACKET_TRACER_BACKEND,
        backend_version=MEASURED_BACKEND_VERSION,
        observed_value=observed_value,
        support_status=support,
        observation_status=observation,
        verification_status=verification,
        limitations=list(limitations),
    )


def _rejected(identifier, subject, speed, duplex, context, message) -> LinkModeObservation:
    return LinkModeObservation(
        speed=speed, duplex=duplex, context=context,
        outcome=LinkModeOutcome.COMMAND_REJECTED,
        prerequisite=message,
        evidence=_evidence(
            identifier, subject,
            f"{subject} rejects duplex {duplex.value} at speed {speed.value}",
            method=VerificationMethod.OPERATIONAL_CLI,
            support=SupportStatus.UNSUPPORTED,
            observation=ObservationStatus.OBSERVED,
            verification=VerificationStatus.VERIFIED,
            observed_value=message,
        ),
    )


def _accepted_without_effect(identifier, subject, speed, duplex, context) -> LinkModeObservation:
    return LinkModeObservation(
        speed=speed, duplex=duplex, context=context,
        outcome=LinkModeOutcome.COMMAND_ACCEPTED,
        evidence=_evidence(
            identifier, subject,
            f"{subject} accepts speed {speed.value} without an observable effect",
            method=VerificationMethod.OPERATIONAL_CLI,
            support=SupportStatus.UNKNOWN,
            observation=ObservationStatus.OBSERVED,
            verification=VerificationStatus.UNVERIFIED,
            observed_value="command accepted; routing bandwidth unchanged",
            limitations=(
                "The command was accepted and produced no observable change, "
                "including after bouncing the link. Acceptance alone does not "
                "show the mode can be forced.",
            ),
        ),
    )


def _observed(identifier, subject, speed, duplex, context, observed_value) -> LinkModeObservation:
    return LinkModeObservation(
        speed=speed, duplex=duplex, context=context,
        outcome=LinkModeOutcome.MODE_EFFECT_OBSERVED,
        evidence=_evidence(
            identifier, subject,
            f"{subject} applies speed {speed.value} duplex {duplex.value}",
            method=VerificationMethod.STRUCTURED_API,
            support=SupportStatus.SUPPORTED,
            observation=ObservationStatus.OBSERVED,
            verification=VerificationStatus.VERIFIED,
            observed_value=observed_value,
        ),
    )


def _autonegotiated(identifier, subject, observed_value) -> LinkModeObservation:
    """La negociacion alcanzo el nominal, leido por API estructurada."""
    return LinkModeObservation(
        speed=LinkSpeedMode.AUTO, duplex=DuplexMode.AUTO,
        context=LinkModeContext.LINKED,
        outcome=LinkModeOutcome.MODE_EFFECT_OBSERVED,
        evidence=_evidence(
            identifier, subject,
            f"{subject} reaches its nominal capacity through autonegotiation",
            method=VerificationMethod.STRUCTURED_API,
            support=SupportStatus.SUPPORTED,
            observation=ObservationStatus.OBSERVED,
            verification=VerificationStatus.VERIFIED,
            observed_value=observed_value,
            limitations=(
                "The negotiated rate is read from the routing bandwidth while "
                "the platform still derives it. It is indirect evidence: no "
                "trusted getter reports the operational speed itself.",
            ),
        ),
    )


_R2911_GIG = "2911 GigabitEthernet"
_SW3560_FA = "3560-24PS FastEthernet"
_SW3560_GIG = "3560-24PS GigabitEthernet"

#: Router 2911, puertos GigabitEthernet integrados.
PT_2911_GIGABIT_LINK_MODE = EthernetLinkModeCapability(
    backend_version=MEASURED_BACKEND_VERSION,
    device_model="2911",
    port_kind="GigabitEthernet",
    nominal_capacity_bps=1_000_000_000,
    nominal_capacity_source=NominalCapacitySource.PORT_CLASS,
    bandwidth_tracks_negotiated_capacity=True,
    observations=(
        _autonegotiated(
            "2911-gig-auto", _R2911_GIG,
            "Gig<->Gig: routing bandwidth 1000000 kbps; contra un Fa baja a "
            "100000 kbps. `bandwidth 5000` lo deja en 5000 con la "
            "autonegociacion desactivada, y `no bandwidth` lo restituye.",
        ),
        _observed(
            "2911-gig-100-full", _R2911_GIG,
            LinkSpeedMode.SPEED_100M, DuplexMode.FULL, LinkModeContext.LINKED,
            "isDuplexAutoNegotiate false, isFullDuplex true, link up",
        ),
        _rejected(
            "2911-gig-100-half", _R2911_GIG,
            LinkSpeedMode.SPEED_100M, DuplexMode.HALF, LinkModeContext.LINKED,
            "%Duplex cannot be set to half when speed autonegotiation subset "
            "contains 1Gbps -- reproducido tambien despues de `speed 100`",
        ),
        _rejected(
            "2911-gig-auto-half", _R2911_GIG,
            LinkSpeedMode.AUTO, DuplexMode.HALF, LinkModeContext.LINKED,
            "%Duplex cannot be set to half when speed autonegotiation subset "
            "contains 1Gbps",
        ),
        _accepted_without_effect(
            "2911-gig-speed-100-linked", _R2911_GIG,
            LinkSpeedMode.SPEED_100M, DuplexMode.AUTO, LinkModeContext.LINKED,
        ),
    ),
    enumeration_complete=False,
    notes=(
        "`speed 100` enlazado: aceptado, sin efecto en el bandwidth de routing "
        "ni despues de rebotar el enlace. `duplex full` si aplica y se relee."
    ),
)

#: Switch 3560-24PS, puertos FastEthernet de acceso.
PT_3560_FASTETHERNET_LINK_MODE = EthernetLinkModeCapability(
    backend_version=MEASURED_BACKEND_VERSION,
    device_model="3560-24PS",
    port_kind="FastEthernet",
    nominal_capacity_bps=100_000_000,
    nominal_capacity_source=NominalCapacitySource.PORT_CLASS,
    bandwidth_tracks_negotiated_capacity=True,
    observations=(
        _autonegotiated(
            "3560-fa-auto", _SW3560_FA,
            "contra un Gigabit: routing bandwidth 100000 kbps en ambos extremos",
        ),
        _observed(
            "3560-fa-100-full", _SW3560_FA,
            LinkSpeedMode.SPEED_100M, DuplexMode.FULL, LinkModeContext.LINKED,
            "isDuplexAutoNegotiate false, isFullDuplex true, routing bandwidth 100000 kbps",
        ),
        _observed(
            "3560-fa-100-half", _SW3560_FA,
            LinkSpeedMode.SPEED_100M, DuplexMode.HALF, LinkModeContext.LINKED,
            "isFullDuplex false",
        ),
        _rejected(
            "3560-fa-1g", _SW3560_FA,
            LinkSpeedMode.SPEED_1G, DuplexMode.AUTO, LinkModeContext.UNSPECIFIED,
            "% Invalid input detected at '^' marker",
        ),
        _rejected(
            "3560-fa-1g-full", _SW3560_FA,
            LinkSpeedMode.SPEED_1G, DuplexMode.FULL, LinkModeContext.UNSPECIFIED,
            "% Invalid input detected at '^' marker",
        ),
    ),
    enumeration_complete=False,
    notes="`speed 1000` responde \"% Invalid input\": el puerto no la ofrece.",
)

#: Switch 3560-24PS, uplinks GigabitEthernet.
PT_3560_GIGABIT_LINK_MODE = EthernetLinkModeCapability(
    backend_version=MEASURED_BACKEND_VERSION,
    device_model="3560-24PS",
    port_kind="GigabitEthernet",
    nominal_capacity_bps=1_000_000_000,
    nominal_capacity_source=NominalCapacitySource.PORT_CLASS,
    bandwidth_tracks_negotiated_capacity=True,
    observations=(
        _autonegotiated(
            "3560-gig-auto", _SW3560_GIG,
            "Gig<->Gig contra un 2911: routing bandwidth 1000000 kbps",
        ),
        _rejected(
            "3560-gig-100-full", _SW3560_GIG,
            LinkSpeedMode.SPEED_100M, DuplexMode.FULL, LinkModeContext.LINKED,
            "% Invalid input detected at '^' marker",
        ),
        _rejected(
            "3560-gig-100-half", _SW3560_GIG,
            LinkSpeedMode.SPEED_100M, DuplexMode.HALF, LinkModeContext.LINKED,
            "% Invalid input detected at '^' marker",
        ),
        _rejected(
            "3560-gig-auto-half", _SW3560_GIG,
            LinkSpeedMode.AUTO, DuplexMode.HALF, LinkModeContext.LINKED,
            "% Invalid input detected at '^' marker",
        ),
        _observed(
            "3560-gig-1g-unlinked", _SW3560_GIG,
            LinkSpeedMode.SPEED_1G, DuplexMode.AUTO, LinkModeContext.UNLINKED,
            "routing bandwidth 1000000 kbps mientras la autonegociacion sigue activa",
        ),
        _observed(
            "3560-gig-10m-unlinked", _SW3560_GIG,
            LinkSpeedMode.SPEED_10M, DuplexMode.AUTO, LinkModeContext.UNLINKED,
            "routing bandwidth 10000 kbps",
        ),
        _accepted_without_effect(
            "3560-gig-speed-100-linked", _SW3560_GIG,
            LinkSpeedMode.SPEED_100M, DuplexMode.AUTO, LinkModeContext.LINKED,
        ),
    ),
    enumeration_complete=False,
    notes=(
        "El uplink rechaza `duplex` en cualquiera de sus tres formas, enlazado "
        "y sin enlazar. `speed` solo mostro efecto sin enlace."
    ),
)

_SW2960_FA = "2960-24TT FastEthernet"
_SW2960_GIG = "2960-24TT GigabitEthernet"


#: Switch 2960-24TT. Es el unico modelo de conmutacion que aparece en el
#: EnterprisePlan de referencia, con puertos FastEthernet de acceso y dos
#: uplinks GigabitEthernet.
PT_2960_FASTETHERNET_LINK_MODE = EthernetLinkModeCapability(
    backend_version=MEASURED_BACKEND_VERSION,
    device_model="2960-24TT",
    port_kind="FastEthernet",
    nominal_capacity_bps=100_000_000,
    nominal_capacity_source=NominalCapacitySource.PORT_CLASS,
    bandwidth_tracks_negotiated_capacity=True,
    observations=(
        _autonegotiated(
            "2960-fa-auto", _SW2960_FA,
            "Fa<->Fa: routing bandwidth 100000 kbps, autonegotiated, link up",
        ),
        _observed(
            "2960-fa-duplex-full", _SW2960_FA,
            LinkSpeedMode.AUTO, DuplexMode.FULL, LinkModeContext.LINKED,
            "isDuplexAutoNegotiate paso de true a false, isFullDuplex true",
        ),
        _accepted_without_effect(
            "2960-fa-speed-10-linked", _SW2960_FA,
            LinkSpeedMode.SPEED_10M, DuplexMode.AUTO, LinkModeContext.LINKED,
        ),
        _rejected(
            "2960-fa-1g", _SW2960_FA,
            LinkSpeedMode.SPEED_1G, DuplexMode.AUTO, LinkModeContext.UNSPECIFIED,
            "% Invalid input detected at '^' marker",
        ),
    ),
    enumeration_complete=False,
    notes=(
        "`speed 10` sobre Fa<->Fa se acepta en ambos extremos y la capacidad "
        "sigue en 100 Mbps: era el unico caso con contrafactual y tampoco "
        "mostro forzado."
    ),
)

PT_2960_GIGABIT_LINK_MODE = EthernetLinkModeCapability(
    backend_version=MEASURED_BACKEND_VERSION,
    device_model="2960-24TT",
    port_kind="GigabitEthernet",
    nominal_capacity_bps=1_000_000_000,
    nominal_capacity_source=NominalCapacitySource.PORT_CLASS,
    bandwidth_tracks_negotiated_capacity=True,
    observations=(
        _autonegotiated(
            "2960-gig-auto", _SW2960_GIG,
            "Gig<->Gig: routing bandwidth 1000000 kbps; contra un Fa baja a "
            "100000 kbps, de modo que el valor sigue al extremo lento",
        ),
        _observed(
            "2960-gig-duplex-full", _SW2960_GIG,
            LinkSpeedMode.AUTO, DuplexMode.FULL, LinkModeContext.LINKED,
            "isDuplexAutoNegotiate paso de true a false",
        ),
        _rejected(
            "2960-gig-duplex-half", _SW2960_GIG,
            LinkSpeedMode.AUTO, DuplexMode.HALF, LinkModeContext.LINKED,
            "%Duplex cannot be set to half when speed autonegotiation subset "
            "contains 1Gbps",
        ),
        _rejected(
            "2960-gig-100-half", _SW2960_GIG,
            LinkSpeedMode.SPEED_100M, DuplexMode.HALF, LinkModeContext.LINKED,
            "%Duplex cannot be set to half when speed autonegotiation subset "
            "contains 1Gbps",
        ),
        _accepted_without_effect(
            "2960-gig-speed-100-linked", _SW2960_GIG,
            LinkSpeedMode.SPEED_100M, DuplexMode.AUTO, LinkModeContext.LINKED,
        ),
    ),
    enumeration_complete=False,
    notes=(
        "Con AUTO el enlace llega a 1 Gbps; `speed 100` aceptado en ambos "
        "extremos lo deja igual, tambien tras rebotar el enlace. Negociar y "
        "forzar no son la misma capacidad."
    ),
)

_PROFILES: tuple[EthernetLinkModeCapability, ...] = (
    PT_2911_GIGABIT_LINK_MODE,
    PT_2960_FASTETHERNET_LINK_MODE,
    PT_2960_GIGABIT_LINK_MODE,
    PT_3560_FASTETHERNET_LINK_MODE,
    PT_3560_GIGABIT_LINK_MODE,
)


def link_mode_capability_for(
    device_model: str, interface: str, *, backend_version: str = "",
) -> EthernetLinkModeCapability | None:
    """Perfil medido para este modelo y tipo de puerto, o None si no se midio.

    Devolver None es la respuesta correcta cuando no hay evidencia: no existe
    un perfil por defecto que "mas o menos" valga para cualquier plataforma, y
    un modelo sin medir no hereda el de otro que se le parezca.
    """
    model = (device_model or "").strip().casefold()
    kind = port_kind_of(interface).casefold()
    for candidate in _PROFILES:
        if candidate.device_model.casefold() != model:
            continue
        if candidate.port_kind.casefold() != kind:
            continue
        if backend_version and candidate.backend_version != backend_version:
            continue
        return candidate
    return None
