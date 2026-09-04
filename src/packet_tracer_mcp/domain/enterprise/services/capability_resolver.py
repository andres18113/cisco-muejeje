"""Transforma hechos de un catálogo externo en capacidades Enterprise explícitas."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from ..models.capabilities import CapabilityEvidence, CapabilityStatus, DeviceCapabilities, EvidenceSource


_EVIDENCE_PRIORITY = {
    EvidenceSource.CONTROLLED_PROBE: 6,
    EvidenceSource.PACKET_TRACER_RUNTIME: 6,
    EvidenceSource.MANUAL_VERIFICATION: 5,
    EvidenceSource.STATIC_OVERRIDE: 4,
    EvidenceSource.CATALOG: 3,
    EvidenceSource.INFERRED: 2,
}


class CapabilityProvider(Protocol):
    """Contrato para fuentes futuras, incluidas runtime y probes controlados."""

    def evidence_for(
        self, model: str, packet_tracer_version: str | None = None,
    ) -> Iterable[CapabilityEvidence]: ...


@dataclass(frozen=True)
class CatalogDeviceFacts:
    """Datos físicos que una infraestructura puede proporcionar sin depender de Enterprise."""

    model: str
    category: str
    aliases: tuple[str, ...] = ()
    port_speeds: tuple[str, ...] = ()
    compatible_modules: tuple[str, ...] = ()
    source: str = "catalog"
    packet_tracer_version: str | None = None
    verified: bool = False


class CapabilityResolver:
    """Conserva UNKNOWN cuando el catálogo no aporta evidencia de una capacidad lógica."""

    def resolve(self, facts: CatalogDeviceFacts) -> DeviceCapabilities:
        speeds = tuple(speed.casefold() for speed in facts.port_speeds)
        modules_known = bool(facts.compatible_modules)
        return DeviceCapabilities(
            model=facts.model,
            category=facts.category,
            aliases=sorted(set(facts.aliases), key=str.casefold),
            port_count=len(speeds),
            ethernet_ports=speeds.count("ethernet"),
            fastethernet_ports=speeds.count("fastethernet"),
            gigabit_ports=speeds.count("gigabitethernet"),
            ten_gigabit_ports=speeds.count("tengigabitethernet"),
            serial_ports=speeds.count("serial"),
            supports_modules=(
                CapabilityStatus.SUPPORTED if modules_known else CapabilityStatus.UNKNOWN
            ),
            compatible_modules=sorted(facts.compatible_modules, key=str.casefold),
            source=facts.source,
            packet_tracer_version=facts.packet_tracer_version,
            verified=facts.verified,
        )

    @staticmethod
    def winning_evidence(
        capability: str,
        evidence: Iterable[CapabilityEvidence],
        packet_tracer_version: str | None = None,
    ) -> CapabilityEvidence | None:
        """Return the authoritative matching fact without discarding provenance."""
        candidates = [
            item for item in evidence
            if item.capability == capability and _evidence_matches_version(item, packet_tracer_version)
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: (_EVIDENCE_PRIORITY[item.source], item.verified, item.source.value),
        )

    @classmethod
    def resolve_evidence(
        cls,
        capability: str,
        evidence: Iterable[CapabilityEvidence],
        packet_tracer_version: str | None = None,
    ) -> CapabilityStatus:
        """Escoge evidencia por autoridad, sin convertir ausencia de evidencia en False."""
        winner = cls.winning_evidence(
            capability, evidence, packet_tracer_version,
        )
        if winner is None:
            return CapabilityStatus.UNKNOWN
        return winner.status

    def with_evidence(
        self,
        capabilities: DeviceCapabilities,
        evidence: Iterable[CapabilityEvidence],
        packet_tracer_version: str | None = None,
    ) -> DeviceCapabilities:
        """Devuelve una copia con estados respaldados por las fuentes disponibles."""
        collected = list(evidence)
        updates = {"evidence": [*capabilities.evidence, *collected]}
        for capability in (
            "supports_poe", "layer2", "layer3", "supports_modules", "supports_vlan",
            "supports_trunk", "supports_svi", "supports_routing", "supports_static_routes",
            "supports_rip", "supports_eigrp", "supports_ospf", "supports_bgp", "supports_stp",
            "supports_acl", "supports_nat", "supports_dhcp_server", "supports_voice",
            "supports_cme", "supports_ipv6", "supports_wireless",
        ):
            status = self.resolve_evidence(capability, collected, packet_tracer_version)
            if status is not CapabilityStatus.UNKNOWN:
                updates[capability] = status
        winner = self.winning_evidence(
            "supports_poe", collected, packet_tracer_version,
        )
        if winner is not None:
            if winner.status is CapabilityStatus.SUPPORTED and winner.observed_value is not None:
                updates["poe_ports"] = winner.observed_value
            elif winner.status is CapabilityStatus.UNSUPPORTED:
                updates["poe_ports"] = None
        if packet_tracer_version is not None:
            updates["packet_tracer_version"] = packet_tracer_version
        return capabilities.model_copy(update=updates)

    @classmethod
    def conflicts(
        cls,
        model: str,
        evidence: Iterable[CapabilityEvidence],
        packet_tracer_version: str | None = None,
    ):
        """Conserva conflictos para reportarlos; la precedencia no borra historia."""
        from ..models.discovery import CapabilityConflict

        grouped: dict[str, list[CapabilityEvidence]] = {}
        for item in evidence:
            if _evidence_matches_version(item, packet_tracer_version):
                grouped.setdefault(item.capability, []).append(item)
        conflicts = []
        for capability, entries in grouped.items():
            statuses = {entry.status for entry in entries}
            if len(statuses) < 2:
                continue
            winning_evidence = cls.winning_evidence(
                capability, entries, packet_tracer_version,
            )
            if winning_evidence is None:
                continue
            conflicts.append(CapabilityConflict(
                model=model,
                capability=capability,
                winner=winning_evidence.source,
                evidence_sources=sorted({item.source for item in entries}, key=lambda item: item.value),
                message=f"EVIDENCE_CONFLICT: {capability} has contradictory retained evidence.",
            ))
        return conflicts


def _evidence_matches_version(
    evidence: CapabilityEvidence,
    packet_tracer_version: str | None,
) -> bool:
    """La evidencia runtime/probe se reutiliza sólo con versión exacta."""
    if evidence.packet_tracer_version is None:
        return True
    return packet_tracer_version is not None and evidence.packet_tracer_version == packet_tracer_version
