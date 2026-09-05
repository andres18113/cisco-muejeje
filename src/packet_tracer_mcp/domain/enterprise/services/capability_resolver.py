"""Transforma hechos de un catálogo externo en capacidades Enterprise explícitas."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from ..models.capabilities import CapabilityEvidence, CapabilityStatus, DeviceCapabilities, EvidenceSource
from .poe_claims import decode_poe_delivery_scope, poe_claim_has_delivery_basis


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
        raw_candidates = [
            item for item in evidence
            if item.capability == capability and _evidence_matches_version(item, packet_tracer_version)
        ]
        if not raw_candidates:
            return None
        if capability == "supports_poe":
            return _winning_poe_evidence(raw_candidates, packet_tracer_version)
        return max(raw_candidates, key=_evidence_rank)

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
        raw_evidence = list(evidence)
        collected = [_cap_claim_to_evidence(item) for item in raw_evidence]
        updates = {"evidence": [*capabilities.evidence, *collected]}
        for capability in (
            "layer2", "layer3", "supports_modules", "supports_vlan",
            "supports_trunk", "supports_svi", "supports_routing", "supports_static_routes",
            "supports_rip", "supports_eigrp", "supports_ospf", "supports_bgp", "supports_stp",
            "supports_acl", "supports_nat", "supports_dhcp_server", "supports_voice",
            "supports_cme", "supports_ipv6", "supports_wireless",
        ):
            status = self.resolve_evidence(capability, collected, packet_tracer_version)
            if status is not CapabilityStatus.UNKNOWN:
                updates[capability] = status
        winner = self.winning_evidence(
            "supports_poe", raw_evidence, packet_tracer_version,
        )
        if winner is not None:
            updates.update(_poe_projection(
                raw_evidence,
                winner,
                model=capabilities.model,
                packet_tracer_version=packet_tracer_version,
            ))
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
        for item in (_cap_claim_to_evidence(entry) for entry in evidence):
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


def _cap_claim_to_evidence(evidence: CapabilityEvidence) -> CapabilityEvidence:
    """Apply the PoE claim ceiling at the resolver's authority boundary."""

    if poe_claim_has_delivery_basis(evidence):
        return evidence
    return evidence.model_copy(update={
        "status": CapabilityStatus.UNKNOWN,
        "observed_value": None,
        "notes": (
            f"{evidence.notes} Claim capped at UNKNOWN: no coherent "
            "powered-device delivery measurement."
        ).strip(),
    })


def _evidence_rank(evidence: CapabilityEvidence) -> tuple[int, bool, bool, str]:
    return (
        _EVIDENCE_PRIORITY[evidence.source],
        evidence.verified,
        evidence.status is not CapabilityStatus.UNKNOWN,
        evidence.source.value,
    )


def _winning_poe_evidence(
    evidence: list[CapabilityEvidence],
    packet_tracer_version: str | None,
) -> CapabilityEvidence:
    """Prefer real delivery over control-only UNKNOWN without hiding bad claims.

    An UNKNOWN inventory observation carries no contrary delivery fact.  A
    malformed decided claim at equal or greater authority is different: it is
    retained as the winner and capped, so a lower record cannot lend it scope.
    """

    valid_delivery = [
        item for item in evidence
        if decode_poe_delivery_scope(
            item,
            expected_packet_tracer_version=packet_tracer_version,
        ) is not None
    ]
    if valid_delivery:
        winner = max(valid_delivery, key=_evidence_rank)
        invalid_decided = [
            item for item in evidence
            if item.status is not CapabilityStatus.UNKNOWN
            and decode_poe_delivery_scope(
                item,
                expected_packet_tracer_version=packet_tracer_version,
            ) is None
            and _evidence_rank(item) >= _evidence_rank(winner)
        ]
        if invalid_decided:
            return _cap_claim_to_evidence(
                max(invalid_decided, key=_evidence_rank)
            )
        return winner
    return max(
        (_cap_claim_to_evidence(item) for item in evidence),
        key=_evidence_rank,
    )


def _poe_projection(
    evidence: list[CapabilityEvidence],
    winner: CapabilityEvidence,
    *,
    model: str,
    packet_tracer_version: str | None,
) -> dict[str, object]:
    """Project only the exact union proven by coherent delivery claims.

    Independent runs can prove additional endpoint/port triples, but their
    simultaneous-active counts cannot be added.  The projected capacity is
    therefore the largest single-run count, while the authorization set is the
    union of the exact bindings retained with their individual provenance.
    """

    unknown = {
        "supports_poe": CapabilityStatus.UNKNOWN,
        "poe_ports": None,
        "poe_authorized_bindings": [],
    }
    winner_scope = decode_poe_delivery_scope(
        winner,
        expected_model=model,
        expected_packet_tracer_version=packet_tracer_version,
    )
    if winner_scope is None:
        return unknown

    winner_rank = _evidence_rank(winner)
    if any(
        item.capability == "supports_poe"
        and item.status is not CapabilityStatus.UNKNOWN
        and decode_poe_delivery_scope(
            item,
            expected_model=model,
            expected_packet_tracer_version=packet_tracer_version,
        ) is None
        and _evidence_rank(item) >= winner_rank
        for item in evidence
    ):
        return unknown

    if winner.status is CapabilityStatus.UNSUPPORTED:
        return {
            "supports_poe": CapabilityStatus.UNSUPPORTED,
            "poe_ports": None,
            "poe_authorized_bindings": [],
        }

    supported_scopes = []
    for item in evidence:
        if (
            item.capability != "supports_poe"
            or item.status is not CapabilityStatus.SUPPORTED
        ):
            continue
        scope = decode_poe_delivery_scope(
            item,
            expected_model=model,
            expected_packet_tracer_version=packet_tracer_version,
        )
        if scope is not None:
            supported_scopes.append(scope)
    if not supported_scopes:
        return unknown

    return {
        "supports_poe": CapabilityStatus.SUPPORTED,
        "poe_ports": max(
            scope.simultaneous_active_ports for scope in supported_scopes
        ),
        "poe_authorized_bindings": sorted({
            binding
            for scope in supported_scopes
            for binding in scope.active_bindings
        }),
    }
