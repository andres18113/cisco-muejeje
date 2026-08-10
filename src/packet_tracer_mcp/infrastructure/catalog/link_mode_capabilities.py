"""Perfiles de modo de enlace medidos sobre Packet Tracer.

Este conocimiento es del backend, no del dominio: nombres de modelo, version de
Packet Tracer y combinaciones concretas de `speed`/`duplex` viven aqui, igual
que el catalogo de cables o de dispositivos. El dominio recibe
`EthernetLinkModeCapability` ya resuelto y no sabe que existe Packet Tracer.

Todo lo de abajo se midio en slices desechables sobre PT 9.0.1.0858 durante
E9.5 Stage 3A3 y 3A3-B. Lo que no aparece esta sin medir, que no es lo mismo
que no soportado.

Dos resultados condicionan como se lee esta tabla:

* `speed` sobre un puerto Gigabit ENLAZADO se acepta sin ningun efecto
  observable -- ni en el bandwidth de routing ni tras rebotar el enlace. Sobre
  el mismo puerto SIN enlazar el efecto si se observa. Por eso las
  observaciones llevan contexto.
* el rechazo de `duplex half` en un Gigabit cita el subset de autonegociacion,
  y se reprodujo tambien despues de fijar `speed 100`. Se guarda como rechazo
  en contexto LINKED, no como prohibicion universal.
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

_STAGE = "e95-stage-3a3b"


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
) -> EvidenceRecord:
    return EvidenceRecord(
        id=f"{_STAGE}/{identifier}",
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
    observations=(
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
    observations=(
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
    observations=(
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

_PROFILES: tuple[EthernetLinkModeCapability, ...] = (
    PT_2911_GIGABIT_LINK_MODE,
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
