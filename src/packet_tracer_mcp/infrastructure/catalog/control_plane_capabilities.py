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
    "route state from R2-B phase 4, typed measurement channel from R3; "
    "see docs/architecture/ripv2-runtime-qualification.md"
)

_RIPV2_1941_QUALIFICATION = (
    "R4 controlled Packet Tracer live qualification on a disposable 1941 slice "
    "(2x 1941 with HWIC-2T over a serial WAN, one LAN neighbour each) on "
    "9.0.1.0858; configuration and routing-process state from "
    "fresh_show_ip_protocols, learned routes from fresh_show_ip_route_rip in "
    "both directions, typed measurement channel from the production "
    "TypedPingExecutor; see docs/architecture/ripv2-runtime-qualification.md"
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
            # R3 midio en vivo, sobre este modelo y build, que el
            # `TypedPingExecutor` de produccion despacha su `ping` registrado en
            # el terminal de un 2911, obtiene ventana fresca con eco exacto,
            # parsea la linea de estadistica y atribuye la sesion a un unico
            # device enumerado del runtime.
            #
            # La dimension es el CANAL DE MEDIDA, no su resultado: R3 cerro sus
            # dos medidas con `Success rate is 0 percent (0/5)` y eso la
            # cualifica igual. Que un destino conteste es `reachable`, y lo mide
            # el producto en cada corrida. Marcarla SUPPORTED autoriza medir; no
            # afirma que nada reenvie.
            Dimension.ROUTING_BEHAVIOR: Status.SUPPORTED,
        },
    ),
    # 1941 / las cuatro dimensiones:
    #   La referencia de 41 dispositivos selecciona este modelo, y sin perfil el
    #   gate E9 dejaba sus acciones en SKIPPED -- capacidad UNKNOWN no autoriza.
    #   R4 lo midio sobre el mismo build con los runtimes de produccion: las
    #   cuatro salieron de una lectura fresca propia, ninguna se hereda del 2911.
    #
    #   Las rutas se verificaron en AMBOS sentidos (R1 aprendio
    #   `198.18.201.0/24`, R2 aprendio `198.18.200.0/24`), que es mas de lo que
    #   la dimension exige y menos ambiguo que una sola direccion.
    #
    #   ROUTING_BEHAVIOR sigue siendo el CANAL, no su resultado: R4 lo midio
    #   `reachable=True`, pero marcarla SUPPORTED autoriza medir y no afirma que
    #   ninguna topologia reenvie. Eso lo mide el producto en cada corrida.
    "1941": (
        _RIPV2_1941_QUALIFICATION,
        {
            Dimension.RIPV2_CONFIG: Status.SUPPORTED,
            Dimension.ROUTING_PROCESS_STATE: Status.SUPPORTED,
            Dimension.ROUTING_ROUTE_STATE: Status.SUPPORTED,
            Dimension.ROUTING_BEHAVIOR: Status.SUPPORTED,
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
