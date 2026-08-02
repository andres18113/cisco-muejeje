"""Fuentes de evidencia versionables; runtime/probe se implementarán en E3.5."""

from __future__ import annotations

from collections.abc import Iterable

from ...domain.enterprise.models.capabilities import CapabilityEvidence, EvidenceSource
from ...infrastructure.persistence.capability_snapshot_store import CapabilitySnapshotStore


class StaticVerifiedCapabilityProvider:
    """Provider inmutable para overrides comprobados, vacío por defecto en E3."""

    def __init__(self, evidence_by_model: dict[str, list[CapabilityEvidence]] | None = None) -> None:
        self._evidence_by_model = evidence_by_model or {}

    def evidence_for(self, model: str, packet_tracer_version: str | None = None) -> Iterable[CapabilityEvidence]:
        return tuple(self._evidence_by_model.get(model, ()))


class RuntimeCapabilityProvider:
    """Expone hechos runtime sólo cuando la versión de PT coincide exactamente."""

    def __init__(self, store: CapabilitySnapshotStore, packet_tracer_version: str | None = None) -> None:
        self._store = store
        self._packet_tracer_version = packet_tracer_version

    def evidence_for(self, model: str, packet_tracer_version: str | None = None) -> Iterable[CapabilityEvidence]:
        version = packet_tracer_version or self._packet_tracer_version
        return tuple(_snapshot_evidence(self._store.list_runtime(version), model, EvidenceSource.PACKET_TRACER_RUNTIME))


class ProbeCapabilityProvider:
    """Expone sólo resultados de probes controlados verificables y versionados."""

    def __init__(self, store: CapabilitySnapshotStore, packet_tracer_version: str | None = None) -> None:
        self._store = store
        self._packet_tracer_version = packet_tracer_version

    def evidence_for(self, model: str, packet_tracer_version: str | None = None) -> Iterable[CapabilityEvidence]:
        version = packet_tracer_version or self._packet_tracer_version
        return tuple(_snapshot_evidence(self._store.list_runtime(version), model, EvidenceSource.CONTROLLED_PROBE))


def _snapshot_evidence(snapshots, model: str, source: EvidenceSource) -> Iterable[CapabilityEvidence]:
    for snapshot in snapshots:
        for result in snapshot.session.results:
            if result.model != model or result.evidence_source is not source:
                continue
            evidence = result.evidence()
            if evidence is not None:
                yield evidence

    def evidence_for(self, model: str) -> Iterable[CapabilityEvidence]:
        return ()
