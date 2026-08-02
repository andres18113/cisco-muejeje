"""Contratos E3.5 para descubrimiento de capacidades de Packet Tracer.

Estos modelos describen observaciones y resultados; no importan el bridge ni
asumen que una observación parcial prueba una capacidad lógica.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from .capabilities import CapabilityStatus, EvidenceSource


PROBE_SCHEMA_VERSION = 1
SNAPSHOT_SCHEMA_VERSION = 1


class DiscoverySource(str, Enum):
    RUNTIME_ENUMERATION = "runtime_enumeration"
    CONTROLLED_CREATE_PROBE = "controlled_create_probe"
    OBSERVED_SEED = "observed_seed"


class ModelIdentityStatus(str, Enum):
    CATALOG_MATCHED = "catalog_matched"
    RUNTIME_ONLY = "runtime_only"
    CATALOG_ONLY = "catalog_only"
    UNRESOLVED_IDENTITY = "unresolved_identity"


class ProbeLevel(str, Enum):
    DISCOVERY = "discovery"
    PHYSICAL = "physical"
    LOGICAL = "logical"


class DetailLevel(str, Enum):
    COMPACT = "compact"
    NORMAL = "normal"
    DEBUG = "debug"


class ProbeExecutionStatus(str, Enum):
    VERIFIED = "verified"
    VERIFY_FAILED = "verify_failed"
    EXECUTION_ERROR = "execution_error"
    TIMEOUT = "timeout"
    BRIDGE_ERROR = "bridge_error"
    PACKET_TRACER_ERROR = "packet_tracer_error"
    SKIPPED = "skipped"
    PREREQUISITE_MISSING = "prerequisite_missing"


class ProbeSafety(str, Enum):
    SAFE = "safe"
    MUTATING = "mutating"
    DESTRUCTIVE_TO_PROBE_DEVICE = "destructive_to_probe_device"


class ProbeCost(str, Enum):
    CHEAP = "cheap"
    NORMAL = "normal"
    EXPENSIVE = "expensive"


class CleanupStatus(str, Enum):
    CLEAN = "clean"
    DIRTY_SESSION = "dirty_session"
    NOT_REQUIRED = "not_required"


class RuntimePortDescriptor(BaseModel):
    name: str
    interface_type: str = ""
    speed: str = ""
    slot: str = ""
    module: str | None = None
    physical: bool = True
    logical: bool = False
    poe_status: CapabilityStatus = CapabilityStatus.UNKNOWN
    access_capable: CapabilityStatus = CapabilityStatus.UNKNOWN
    uplink_capable: CapabilityStatus = CapabilityStatus.UNKNOWN
    evidence_source: EvidenceSource = EvidenceSource.PACKET_TRACER_RUNTIME


class RuntimeModuleDescriptor(BaseModel):
    name: str
    slot: str | None = None
    installed: bool = False
    resulting_ports: list[RuntimePortDescriptor] = Field(default_factory=list)
    evidence_source: EvidenceSource = EvidenceSource.PACKET_TRACER_RUNTIME


class DeviceIdentity(BaseModel):
    canonical_id: str | None = None
    runtime_id: str | None = None
    display_name: str = ""
    aliases: list[str] = Field(default_factory=list)
    category: str | None = None
    packet_tracer_version: str | None = None
    status: ModelIdentityStatus = ModelIdentityStatus.UNRESOLVED_IDENTITY


class RuntimeDeviceDescriptor(BaseModel):
    identity: DeviceIdentity
    discovery_source: DiscoverySource
    ports: list[RuntimePortDescriptor] = Field(default_factory=list)
    modules: list[RuntimeModuleDescriptor] = Field(default_factory=list)
    observed: bool = False
    warnings: list[str] = Field(default_factory=list)


class RuntimeDeviceObservation(BaseModel):
    """Respuesta estructurada del runtime para un dispositivo temporal."""

    found: bool = False
    runtime_id: str | None = None
    display_name: str = ""
    category: str | None = None
    ports: list[RuntimePortDescriptor] = Field(default_factory=list)
    modules: list[RuntimeModuleDescriptor] = Field(default_factory=list)
    error: str = ""


class CapabilityProbeResult(BaseModel):
    probe_id: str
    model: str
    capability: str
    status: CapabilityStatus = CapabilityStatus.UNKNOWN
    execution_status: ProbeExecutionStatus
    evidence_source: EvidenceSource
    configured: bool = False
    verified: bool = False
    observed_value: int | None = None
    raw_summary: str = ""
    failure_reason: str = ""
    duration_ms: int = 0
    packet_tracer_version: str | None = None

    def evidence(self):
        """Convierte sólo resultados verificados en evidencia reusable."""
        from .capabilities import CapabilityEvidence

        if self.execution_status is not ProbeExecutionStatus.VERIFIED:
            return None
        return CapabilityEvidence(
            capability=self.capability,
            status=self.status,
            source=self.evidence_source,
            source_detail=self.probe_id,
            packet_tracer_version=self.packet_tracer_version,
            verified=self.verified,
            observed_value=self.observed_value,
            notes=self.raw_summary,
        )


class ProbeDefinition(BaseModel):
    id: str
    capability: str
    supported_categories: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    safety: ProbeSafety = ProbeSafety.SAFE
    requires_power_cycle: bool = False
    cost: ProbeCost = ProbeCost.CHEAP


class ProbeRequest(BaseModel):
    models: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    probe_level: ProbeLevel = ProbeLevel.PHYSICAL
    detail_level: DetailLevel = DetailLevel.COMPACT
    force: bool = False
    packet_tracer_version: str | None = None


class ProbeSession(BaseModel):
    session_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    packet_tracer_version: str | None = None
    created_devices: list[str] = Field(default_factory=list)
    mutations: list[str] = Field(default_factory=list)
    cleanup_status: CleanupStatus = CleanupStatus.NOT_REQUIRED
    warnings: list[str] = Field(default_factory=list)


class ProbeSessionResult(BaseModel):
    session: ProbeSession
    devices: list[RuntimeDeviceDescriptor] = Field(default_factory=list)
    results: list[CapabilityProbeResult] = Field(default_factory=list)
    cleanup_deleted: list[str] = Field(default_factory=list)
    cleanup_failed: list[str] = Field(default_factory=list)

    def compact_summary(self) -> dict[str, int | str | list[str]]:
        statuses = {status.value: 0 for status in CapabilityStatus}
        for result in self.results:
            statuses[result.status.value] += 1
        return {
            "probe_session_id": self.session.session_id,
            "models": len(self.devices),
            "capabilities_checked": len(self.results),
            **statuses,
            "errors": sum(
                result.execution_status not in {ProbeExecutionStatus.VERIFIED, ProbeExecutionStatus.SKIPPED}
                for result in self.results
            ),
            "cleanup_status": self.session.cleanup_status.value,
            "cleanup_failed": self.cleanup_failed,
        }


class CapabilitySnapshot(BaseModel):
    schema_version: int = SNAPSHOT_SCHEMA_VERSION
    probe_schema_version: int = PROBE_SCHEMA_VERSION
    packet_tracer_version: str | None = None
    session: ProbeSessionResult

    def stable_hash(self) -> str:
        payload = self.model_dump(mode="json")
        session = payload["session"]["session"]
        session["started_at"] = ""
        session["session_id"] = ""
        session["created_devices"] = ["<probe>" for _ in session["created_devices"]]
        payload["session"]["cleanup_deleted"] = ["<probe>" for _ in payload["session"]["cleanup_deleted"]]
        payload["session"]["cleanup_failed"] = ["<probe>" for _ in payload["session"]["cleanup_failed"]]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def compact_summary(self) -> dict[str, int | str | list[str]]:
        summary = self.session.compact_summary()
        summary["packet_tracer_version"] = self.packet_tracer_version or "unknown"
        summary["snapshot_hash"] = self.stable_hash()
        return summary

    def blocking_unknowns(self) -> dict[str, list[str]]:
        blocking = {"poe": [], "layer3": [], "model_identity": []}
        for device in self.session.devices:
            identity = device.identity
            model = identity.canonical_id or identity.runtime_id or identity.display_name
            if identity.status is ModelIdentityStatus.UNRESOLVED_IDENTITY:
                blocking["model_identity"].append(model)
        for result in self.session.results:
            if result.status is not CapabilityStatus.UNKNOWN:
                continue
            if result.capability in {"supports_poe", "layer3"}:
                key = "poe" if result.capability == "supports_poe" else "layer3"
                if result.model not in blocking[key]:
                    blocking[key].append(result.model)
        return {key: value for key, value in blocking.items() if value}


class SnapshotDiff(BaseModel):
    models_added: list[str] = Field(default_factory=list)
    models_removed: list[str] = Field(default_factory=list)
    ports_changed: list[str] = Field(default_factory=list)
    capabilities_changed: list[str] = Field(default_factory=list)
    modules_changed: list[str] = Field(default_factory=list)


class CapabilityConflict(BaseModel):
    model: str
    capability: str
    winner: EvidenceSource
    evidence_sources: list[EvidenceSource] = Field(default_factory=list)
    message: str


class CatalogGapReport(BaseModel):
    known: list[str] = Field(default_factory=list)
    runtime_only: list[str] = Field(default_factory=list)
    catalog_only: list[str] = Field(default_factory=list)
    alias_mismatches: list[str] = Field(default_factory=list)
    capability_gaps: dict[str, list[str]] = Field(default_factory=dict)


class E4ReadinessState(str, Enum):
    READY = "ready"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class E4ReadinessReport(BaseModel):
    model_identity: E4ReadinessState
    port_inventory: E4ReadinessState
    module_support: E4ReadinessState
    access_switch_selection: E4ReadinessState
    poe_selection: E4ReadinessState
    distribution_l3: E4ReadinessState
    core_l3: E4ReadinessState
    edge_router: E4ReadinessState
    blocking_unknowns: dict[str, list[str]] = Field(default_factory=dict)
    p01_status: str = "still_pending"

    @property
    def e4_ready(self) -> bool:
        return not self.blocking_unknowns and all(
            value is E4ReadinessState.READY
            for value in (
                self.model_identity, self.port_inventory, self.module_support,
                self.access_switch_selection, self.poe_selection, self.distribution_l3,
                self.core_l3, self.edge_router,
            )
        )
