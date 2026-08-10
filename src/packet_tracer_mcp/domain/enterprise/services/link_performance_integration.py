"""Enlaza la politica de rendimiento con el pipeline enterprise existente.

No hay una segunda orquestacion ni un hash nuevo. Los dos seams ya existian:

* `_physical_payload` incluye `LinkPlan.metadata` y solo excluye las claves
  visuales, asi que un hecho fisico -- el medio, que extremo es el DCE --
  entra en `physical_topology_hash` por construccion.
* `ConfigurationPlan.semantic_hash` es el digest del plan completo, asi que
  una accion tipada de reloj, bandwidth o modo de enlace cambia la identidad
  de configuracion por construccion.

Lo observado en runtime no se escribe en ninguno de los dos.
"""

from __future__ import annotations

from collections.abc import Callable

from ..models.compilation import ConcreteLinkRole
from ..models.configuration import (
    ConfigurationPhase,
    ConfigureEthernetLinkMode,
    ConfigureInterfaceBandwidth,
    ConfigureSerialClock,
)
from ..models.link_performance import (
    CapacitySource,
    DuplexMode,
    EthernetLinkModeCapability,
    LinkMedia,
    LinkModeContext,
    LinkPerformanceDecision,
    LinkPerformanceIntent,
    LinkSpeedMode,
    TrafficContribution,
)
from .link_performance_planner import LinkPerformancePlanner

# Claves de identidad fisica. No llevan prefijo visual, de modo que el hash
# fisico las cubre; renombrarlas cambia la identidad y por eso son estables.
LINK_MEDIA_KEY = "link_media"
LINK_DCE_KEY = "serial_dce_device_id"
LINK_DTE_KEY = "serial_dte_device_id"

# Vocabulario real del catalogo (`CABLE_TYPES`). Se enumeran los dos conjuntos
# de medios de datos; todo lo demas -- consola, telefonia, coaxial, wireless,
# octal, celular, USB -- no es un medio de datos conmutado y no recibe politica
# de capacidad. Un cable desconocido nunca se asume Ethernet.
_SERIAL_CABLES = frozenset({"serial"})
_ETHERNET_CABLES = frozenset({"straight", "cross", "crossover", "fiber", "auto"})


def resolve_link_media(cable: str) -> LinkMedia:
    """El medio sale del cable planificado, no del nombre del dispositivo."""
    normalized = (cable or "").strip().casefold()
    if normalized in _SERIAL_CABLES:
        return LinkMedia.SERIAL
    if normalized in _ETHERNET_CABLES:
        return LinkMedia.ETHERNET
    return LinkMedia.UNKNOWN


class LinkPerformanceIntegration:
    """Traduce enlaces planificados a decisiones y a acciones tipadas."""

    def __init__(
        self,
        planner: LinkPerformancePlanner | None = None,
        capability_resolver: (
            "Callable[[str, str], EthernetLinkModeCapability | None] | None"
        ) = None,
    ) -> None:
        self._planner = planner or LinkPerformancePlanner()
        # Quién sabe qué backend hay debajo lo aporta la infraestructura. Sin
        # resolver, los extremos quedan sin perfil y la política se comporta
        # como antes de haber medido nada.
        self._capability_resolver = capability_resolver

    # -- intent ----------------------------------------------------------

    def intent_for_link(
        self,
        link,
        *,
        traffic: list[TrafficContribution] | None = None,
        failure_survival_bps: int | None = None,
        requested_capacity_bps: int | None = None,
        requested_speed: LinkSpeedMode = LinkSpeedMode.AUTO,
        requested_duplex: DuplexMode = DuplexMode.AUTO,
        sync_routing_bandwidth: bool = False,
        endpoint_models: dict[str, str] | None = None,
        link_context: LinkModeContext = LinkModeContext.LINKED,
        allow_unverified_mode_exploration: bool = False,
    ) -> LinkPerformanceIntent:
        metadata = dict(getattr(link, "metadata", {}) or {})
        role = self._role_for(getattr(link, "link_role", ""))
        local, peer = self._endpoint_capabilities(link, endpoint_models or {})
        return LinkPerformanceIntent(
            link_id=getattr(link, "id", "") or "",
            media=resolve_link_media(getattr(link, "cable", "")),
            role=role,
            requested_capacity_bps=requested_capacity_bps,
            requested_speed=requested_speed,
            requested_duplex=requested_duplex,
            traffic=list(traffic or []),
            failure_survival_bps=failure_survival_bps,
            sync_routing_bandwidth_to_effective_capacity=sync_routing_bandwidth,
            local_port_capability=local,
            peer_port_capability=peer,
            link_context=link_context,
            allow_unverified_mode_exploration=allow_unverified_mode_exploration,
            dce_endpoint_device_id=metadata.get(LINK_DCE_KEY, ""),
            dte_endpoint_device_id=metadata.get(LINK_DTE_KEY, ""),
        )

    def _endpoint_capabilities(self, link, endpoint_models: dict[str, str]):
        """Perfil medido de cada extremo, o None donde no haya evidencia.

        El modelo del dispositivo no viene en el enlace: lo aporta quien conoce
        el inventario, y quien sabe traducirlo a un perfil es la
        infraestructura. Sin resolver, ambos extremos quedan sin perfil.
        """
        if self._capability_resolver is None:
            return (None, None)
        pairs = (
            (getattr(link, "device_a", ""), getattr(link, "port_a", "")),
            (getattr(link, "device_b", ""), getattr(link, "port_b", "")),
        )
        return tuple(
            self._capability_resolver(endpoint_models.get(device, ""), interface)
            if device and interface else None
            for device, interface in pairs
        )

    @staticmethod
    def _role_for(value: str) -> ConcreteLinkRole | None:
        try:
            return ConcreteLinkRole(value)
        except ValueError:
            return None

    # -- decision --------------------------------------------------------

    def decide(self, intent: LinkPerformanceIntent) -> LinkPerformanceDecision:
        return self._planner.plan(intent)

    def stamp_physical_identity(self, link, decision: LinkPerformanceDecision) -> None:
        """Escribe solo hechos fisicos; nunca reloj, bandwidth ni duplex."""
        metadata = dict(getattr(link, "metadata", {}) or {})
        metadata[LINK_MEDIA_KEY] = decision.media.value
        if decision.dce_endpoint_device_id:
            metadata[LINK_DCE_KEY] = decision.dce_endpoint_device_id
        if decision.dte_endpoint_device_id:
            metadata[LINK_DTE_KEY] = decision.dte_endpoint_device_id
        link.metadata = metadata

    # -- typed actions ---------------------------------------------------

    def actions_for(
        self,
        decision: LinkPerformanceDecision,
        *,
        device_id: str,
        device_name: str,
        site_id: str,
        interface: str,
    ) -> list:
        """Acciones tipadas; ninguna se emite sobre una decision no aplicable."""
        if not decision.applicable:
            return []
        actions: list = []
        if decision.media is LinkMedia.SERIAL:
            # El reloj es del DCE resuelto y de nadie mas.
            if decision.serial_clock_rate_bps and decision.dce_endpoint_device_id == device_id:
                actions.append(ConfigureSerialClock(
                    id=f"{decision.link_id}/clock/{device_id}",
                    phase=ConfigurationPhase.L2_INTERFACES,
                    device_id=device_id, device_name=device_name, site_id=site_id,
                    interface=interface,
                    clock_rate_bps=decision.serial_clock_rate_bps,
                ))
        elif decision.media is LinkMedia.ETHERNET:
            # AUTO/AUTO no fuerza nada: no hay accion que emitir.
            if (
                decision.effective_speed is not LinkSpeedMode.AUTO
                or decision.effective_duplex is not DuplexMode.AUTO
            ):
                actions.append(ConfigureEthernetLinkMode(
                    id=f"{decision.link_id}/link-mode/{device_id}",
                    phase=ConfigurationPhase.L2_INTERFACES,
                    device_id=device_id, device_name=device_name, site_id=site_id,
                    interface=interface,
                    speed=decision.effective_speed.value,
                    duplex=decision.effective_duplex.value,
                ))
        if decision.routing_bandwidth_kbps:
            actions.append(ConfigureInterfaceBandwidth(
                id=f"{decision.link_id}/bandwidth/{device_id}",
                phase=ConfigurationPhase.L2_INTERFACES,
                device_id=device_id, device_name=device_name, site_id=site_id,
                interface=interface,
                bandwidth_kbps=decision.routing_bandwidth_kbps,
            ))
        return actions

    # -- compilacion de una topologia -----------------------------------

    def compile_topology(self, topology, **intent_options) -> list[LinkPerformanceDecision]:
        """Una decision por enlace, en orden estable de identidad de enlace."""
        links = sorted(
            getattr(topology, "links", []) or [],
            key=lambda item: (getattr(item, "id", "") or "", getattr(item, "device_a", "")),
        )
        decisions: list[LinkPerformanceDecision] = []
        for link in links:
            decision = self.decide(self.intent_for_link(link, **intent_options))
            self.stamp_physical_identity(link, decision)
            decisions.append(decision)
        return decisions


def summarize_decisions(decisions: list[LinkPerformanceDecision]) -> dict[str, object]:
    """Resumen compacto; no vuelca planes ni decisiones completas."""
    by_source: dict[str, int] = {}
    for decision in decisions:
        key = decision.capacity_source.value
        by_source[key] = by_source.get(key, 0) + 1
    return {
        "links": len(decisions),
        "roles": sorted({d.role.value for d in decisions if d.role}),
        "media": sorted({d.media.value for d in decisions}),
        "by_capacity_source": dict(sorted(by_source.items())),
        "unresolved": sum(
            1 for d in decisions
            if d.capacity_source is CapacitySource.UNRESOLVED
        ),
        "issues": sorted({
            item.code.value for decision in decisions for item in decision.issues
        }),
    }
