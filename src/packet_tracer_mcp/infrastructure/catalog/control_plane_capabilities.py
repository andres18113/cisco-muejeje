"""Baseline E9 de control plane medido para Packet Tracer 9.0.1.0858.

Sólo entra aquí evidencia viva ATRIBUIDA A UN MODELO concreto. La matriz de
`docs/architecture/enterprise-control-plane.md` registra resultados vivos de
STP, EtherChannel, HSRP, OSPF y EIGRP, pero **no dice sobre qué modelo** se
obtuvo cada uno. Un perfil se indexa por modelo, así que atribuir esos
resultados a un modelo concreto sería inventar procedencia: quedan UNKNOWN
hasta que exista una medición atribuida.

Toda dimensión se declara de forma explícita, incluidas las UNKNOWN, para que
añadir una dimensión nueva al enum obligue a clasificarla en vez de heredar un
estado por omisión.
"""

from __future__ import annotations

from ...domain.enterprise.models.control_plane import (
    ControlPlaneCapabilityDimension as Dimension,
    ControlPlaneCapabilityProfile,
)
from ...domain.enterprise.models.security_plan import SecurityCapabilityStatus as Status


_RIPV2_LIVE_QUALIFICATION = (
    "R2-0 and R2-B controlled Packet Tracer live qualifications on disposable "
    "2911 routers; configuration and routing-process state from R2-0, learned "
    "route state from R2-B phase 4; "
    "see docs/architecture/ripv2-runtime-qualification.md"
)

_NO_MODEL_ATTRIBUTED_EVIDENCE = (
    "The E9 live baseline in docs/architecture/enterprise-control-plane.md "
    "records no per-model attribution, so no dimension is claimed for this model"
)


# Evidencia probada, por modelo. Lo que no aparece aquí NO se afirma.
#
# 2911 / RIPV2_CONFIG:
#   R2-0 aplicó en vivo el conjunto exacto de operaciones RIPv2 sobre un 2911
#   disposable en PT 9.0.1.0858 y lo releyó con `show ip protocols`. Es
#   evidencia de configuración, atribuida a modelo y a build.
#
# 2911 / ROUTING_PROCESS_STATE:
#   La misma lectura demuestra que ESTE build expone el estado de un proceso de
#   enrutamiento en ESTE modelo. La dimensión describe el canal de observación,
#   no el protocolo: no convierte a OSPF ni a EIGRP en observables, porque el
#   runtime los lee con consultas distintas y sigue exigiendo su propio parseo
#   fresco antes de promover cualquier afirmación.
_PROVEN_BY_MODEL: dict[str, tuple[str, dict[Dimension, Status]]] = {
    "2911": (
        _RIPV2_LIVE_QUALIFICATION,
        {
            Dimension.RIPV2_CONFIG: Status.SUPPORTED,
            Dimension.ROUTING_PROCESS_STATE: Status.SUPPORTED,
            # R2-B fase 4 leyo en vivo `show ip route rip` en este modelo y
            # build, y el parser de produccion extrajo la ruta aprendida
            # (`R 150.1.1.0/27 ... Serial0/0/0`).
            #
            # Igual que ROUTING_PROCESS_STATE, la dimension describe el CANAL
            # de observacion del dispositivo, no un protocolo. Marcarla
            # SUPPORTED tambien habilita las expectativas de ruta de OSPF sobre
            # este modelo, que hasta ahora se saltaban por capacidad. Eso es
            # deliberado y no fabrica evidencia: `_observe_ospf_route` sigue
            # exigiendo su propia consulta y su propio parseo fresco, y
            # devuelve UNOBSERVABLE cuando no hay filas que leer.
            Dimension.ROUTING_ROUTE_STATE: Status.SUPPORTED,
        },
    ),
    "2960-24TT": (_NO_MODEL_ATTRIBUTED_EVIDENCE, {}),
}


def packet_tracer_control_plane_capabilities(
    packet_tracer_version: str = "9.0.1.0858",
) -> dict[str, ControlPlaneCapabilityProfile]:
    """Perfiles de control plane derivados sólo de evidencia viva atribuida.

    Un modelo ausente de este catálogo no obtiene perfil, y el gate lo resuelve
    como UNKNOWN. La ausencia de evidencia nunca se convierte en SUPPORTED ni
    en UNSUPPORTED.
    """
    return {
        model: ControlPlaneCapabilityProfile(
            model=model,
            packet_tracer_version=packet_tracer_version,
            evidence_source=evidence_source,
            dimensions={
                **{dimension: Status.UNKNOWN for dimension in Dimension},
                **proven,
            },
        )
        for model, (evidence_source, proven) in _PROVEN_BY_MODEL.items()
    }
