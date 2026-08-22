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


PROBE_SCHEMA_VERSION = 2
SNAPSHOT_SCHEMA_VERSION = 2


def semantic_fingerprint(payload: object) -> str:
    """Hash semantico: estable, ordenado y libre de datos de sesion."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def semantic_inventory_fingerprint(items: list[object]) -> str:
    """Fingerprint de inventario independiente del orden de enumeracion runtime."""
    normalized = [_canonical_inventory_value(item) for item in items]
    ordered = sorted(
        normalized,
        key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
    )
    return semantic_fingerprint({"inventory": ordered})


def _canonical_inventory_value(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _canonical_inventory_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set)):
        normalized = [_canonical_inventory_value(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        )
    return value


class DiscoverySource(str, Enum):
    RUNTIME_ENUMERATION = "runtime_enumeration"
    CONTROLLED_CREATE_PROBE = "controlled_create_probe"
    OBSERVED_SEED = "observed_seed"


class CapabilityBackend(str, Enum):
    """Backend que produjo la evidencia; no todos los laboratorios son PT."""

    PACKET_TRACER = "packet_tracer"
    CML = "cml"
    EVE_NG = "eve_ng"
    GNS3 = "gns3"
    IOS_XE = "ios_xe"


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


class Layer3ProbeStrategy(str, Enum):
    """Cómo alcanza un modelo una dirección IPv4 propia.

    Un switch L2 y un multilayer soportan ambos VLANs, así que la estrategia no
    puede deducirse de `supports_vlan`: se declara por modelo.
    """

    ROUTED_PHYSICAL_INTERFACE = "routed_physical_interface"
    SVI = "svi"
    NONE = "none"


class MultilayerDimension(str, Enum):
    """Propiedades que un cierre multilayer debe poder distinguir."""

    SVI_CONFIGURATION = "svi_configuration"
    SVI_ADDRESS_READBACK = "svi_address_readback"
    SVI_ADMIN_STATE = "svi_admin_state"
    SVI_OPERATIONAL_STATE = "svi_operational_state"
    IP_ROUTING = "ip_routing"
    ENDPOINT_GATEWAY = "endpoint_gateway"
    INTERVLAN_FORWARDING = "intervlan_forwarding"


class BackendVersionProvenance(str, Enum):
    """Cómo se supo la versión del backend que produjo una evidencia.

    El file-bridge no expone hoy una versión verificable, así que una snapshot
    puede quedar sin versión. Eso no la invalida dentro de su propia sesión,
    pero dos versiones distintas de Packet Tracer producirían snapshots
    indistinguibles, de modo que no puede reutilizarse entre sesiones.
    """

    DIRECTLY_OBSERVED = "directly_observed"
    DECLARED_ENVIRONMENT = "declared_environment"
    UNKNOWN = "unknown"


_INVENTORY_PARTS = 2


def encode_inventory_observation(
    semantic_fingerprint_value: str, backend_managed: list[str],
) -> str:
    """Huella de inventario con la parte backend-managed separada.

    Packet Tracer materializa objetos por su cuenta (hoy, el Power Distribution
    Device) y los conserva después de que el probe borre los suyos. Contarlos
    junto al resto hacía imposible restaurar; ignorarlos del todo escondía que
    un objeto preexistente del usuario hubiera desaparecido. Se guardan aparte
    para poder exigir cosas distintas de cada mitad.
    """
    ordered = ";".join(sorted(set(backend_managed)))
    return f"{semantic_fingerprint_value}|{ordered}"


def decode_inventory_observation(value: str) -> tuple[str, frozenset[str]]:
    """Devuelve (huella semántica, identidades backend-managed)."""
    if not value:
        return "", frozenset()
    parts = value.split("|", 1)
    if len(parts) != _INVENTORY_PARTS:
        # Huella heredada, sin mitad backend-managed.
        return value, frozenset()
    semantic, managed = parts
    return semantic, frozenset(item for item in managed.split(";") if item)


def inventory_restoration_matches(initial: str, final: str) -> bool:
    """La mitad semántica debe coincidir; la backend-managed sólo puede crecer.

    Un objeto backend-managed nuevo es una consecuencia de la sesión que el
    probe no puede revertir, y no invalida la restauración. La desaparición o
    el cambio de uno preexistente sí: nadie autorizó tocarlo.
    """
    initial_semantic, initial_managed = decode_inventory_observation(initial)
    final_semantic, final_managed = decode_inventory_observation(final)
    if initial_semantic != final_semantic:
        return False
    return initial_managed <= final_managed


class InventoryRestoration(str, Enum):
    """Clasificación explícita de `inventory_restored` frente a la mutación.

    El booleano opcional almacenado no distingue "no había nada que
    restaurar" de "no se pudo medir". Esa diferencia decide si una sesión
    puede reutilizarse, así que se expone como un valor propio en vez de
    dejarla implícita en un `None`.
    """

    RESTORED = "restored"
    NOT_RESTORED = "not_restored"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


def classify_inventory_restoration(
    inventory_restored: bool | None, *, mutated: bool,
) -> InventoryRestoration:
    """Deriva la clasificación; nunca convierte `None` en restauración."""
    if inventory_restored is True:
        return InventoryRestoration.RESTORED
    if inventory_restored is False:
        return InventoryRestoration.NOT_RESTORED
    return (
        InventoryRestoration.UNKNOWN if mutated
        else InventoryRestoration.NOT_APPLICABLE
    )


# Sólo una restauración probada, o la ausencia de algo que restaurar, permiten
# reutilizar. UNKNOWN bloquea: una sesión mutada sin restauración observada no
# es una sesión limpia.
_REUSABLE_RESTORATIONS = frozenset({
    InventoryRestoration.RESTORED,
    InventoryRestoration.NOT_APPLICABLE,
})


class ProbeIsolationLevel(str, Enum):
    SHARED_DEVICE = "shared_device"
    RESET_REQUIRED = "reset_required"
    FRESH_DEVICE_REQUIRED = "fresh_device_required"
    FRESH_SESSION_REQUIRED = "fresh_session_required"


class ProbeEnvironment(BaseModel):
    """Hechos estables que pueden cambiar la validez de una observacion."""

    backend: CapabilityBackend = CapabilityBackend.PACKET_TRACER
    backend_version: str = ""
    transport_channel: str = ""
    extension_version: str = ""
    platform: str = ""
    capability_snapshot_version: str = str(SNAPSHOT_SCHEMA_VERSION)
    runtime_mode: str = ""
    relevant_facts: dict[str, str] = Field(default_factory=dict)

    def semantic_fingerprint(self) -> str:
        return semantic_fingerprint(self.model_dump(mode="json"))


class ProbeContext(BaseModel):
    """Proveniencia y condiciones de confianza de un resultado de probe."""

    probe_id: str
    probe_version: str = "1"
    backend: CapabilityBackend = CapabilityBackend.PACKET_TRACER
    backend_version: str = ""
    device_model: str
    environment_fingerprint: str = ""
    initial_inventory_hash: str = ""
    final_inventory_hash: str = ""
    inventory_restored: bool | None = None
    isolation_level: ProbeIsolationLevel = ProbeIsolationLevel.SHARED_DEVICE
    mutations: list[str] = Field(default_factory=list)
    cleanup_status: CleanupStatus = CleanupStatus.NOT_REQUIRED
    result_status: CapabilityStatus = CapabilityStatus.UNKNOWN
    execution_status: ProbeExecutionStatus = ProbeExecutionStatus.SKIPPED
    probe_fingerprint: str = ""

    @property
    def restoration(self) -> InventoryRestoration:
        return classify_inventory_restoration(
            self.inventory_restored, mutated=bool(self.mutations),
        )

    @property
    def reusable(self) -> bool:
        return (
            self.cleanup_status is not CleanupStatus.DIRTY_SESSION
            and self.restoration in _REUSABLE_RESTORATIONS
        )


class DeviceInitializationState(str, Enum):
    CREATED = "created"
    CONFIGURATION_READY = "configuration_ready"
    OPERATIONAL_READY = "operational_ready"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"


class CapabilityVerificationMethod(str, Enum):
    DIRECT_RUNTIME_API = "direct_runtime_api"
    CLI_PLUS_READBACK = "cli_plus_readback"
    OBJECT_STATE = "object_state"
    SIMULATION_TRACE = "simulation_trace"
    MANUAL_VERIFIED = "manual_verified"
    UNOBSERVABLE = "unobservable"


class DeviceInitializationResult(BaseModel):
    state: DeviceInitializationState = DeviceInitializationState.CREATED
    attempts: int = 0
    elapsed_ms: int = 0
    power: bool | None = None
    command_prompt: bool = False
    terminal_available: bool = False
    terminal_kind: str = "unavailable"
    booting: bool | None = None
    configuration_channel: bool = False
    components_seen: list[str] = Field(default_factory=list)
    failure_reason: str = ""


class RuntimePortDescriptor(BaseModel):
    name: str
    interface_type: str = ""
    speed: str = ""
    slot: str = ""
    module: str | None = None
    physical: bool = True
    logical: bool = False
    # `getPower()` and `isPowerOn()` are separate observations on PT's port
    # object.  Neither is powered-device delivery: a fresh, unlinked 3560 port
    # reports both as true.  Keep the dimensions separate and leave delivery
    # unobserved until a governed powered-device control exists.
    power_admin_enabled: bool | None = None
    power_runtime_on: bool | None = None
    power_delivery_active: bool | None = None
    power_observation_complete: bool = False
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
    # Packet Tracer devuelve un código numérico de slot, no un tipo nombrado.
    slot_type_code: str = ""
    port_count: int = 0
    # El getter de nombre existe y responde, pero devuelve "None" incluso para
    # un módulo que expone puertos. Enumerar un slot y nombrar lo que contiene
    # son observaciones distintas y se registran por separado.
    identity_observable: bool = False


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
    initialization: DeviceInitializationResult | None = None
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
    verification_method: CapabilityVerificationMethod | None = None
    context: ProbeContext | None = None
    # Un probe compuesto observa varias propiedades en una sola construcción.
    # Colapsarlas en el status perdería exactamente lo que hay que distinguir:
    # una SVI configurada pero sin line protocol no es lo mismo que una SVI
    # ausente, ni que un forwarding que falla.
    dimensions: dict[str, str] = Field(default_factory=dict)

    def evidence(self):
        """Convierte sólo resultados verificados en evidencia reusable."""
        from .capabilities import CapabilityEvidence

        if self.execution_status is not ProbeExecutionStatus.VERIFIED:
            return None
        if self.context is not None and not self.context.reusable:
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
    probe_version: str = "1"
    capability: str
    supported_categories: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    safety: ProbeSafety = ProbeSafety.SAFE
    requires_power_cycle: bool = False
    requires_fresh_device: bool = False
    isolation_level: ProbeIsolationLevel | None = None
    cost: ProbeCost = ProbeCost.CHEAP

    @property
    def effective_isolation_level(self) -> ProbeIsolationLevel:
        """Migra flags E3.5 sin convertirlos en una segunda fuente de verdad."""
        if self.isolation_level is not None:
            return self.isolation_level
        if self.requires_fresh_device:
            return ProbeIsolationLevel.FRESH_DEVICE_REQUIRED
        if self.requires_power_cycle:
            return ProbeIsolationLevel.RESET_REQUIRED
        return ProbeIsolationLevel.SHARED_DEVICE

    def semantic_fingerprint(
        self, model: str, relevant_inputs: dict[str, object] | None = None,
    ) -> str:
        return semantic_fingerprint({
            "probe_id": self.id,
            "probe_version": self.probe_version,
            "capability": self.capability,
            "target_model": model,
            "supported_categories": sorted(self.supported_categories),
            "prerequisites": sorted(self.prerequisites),
            "safety": self.safety.value,
            "isolation_level": self.effective_isolation_level.value,
            "cost": self.cost.value,
            "relevant_inputs": relevant_inputs or {},
        })


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
    backend_version_provenance: BackendVersionProvenance = (
        BackendVersionProvenance.UNKNOWN
    )
    backend: CapabilityBackend = CapabilityBackend.PACKET_TRACER
    environment_fingerprint: str = ""
    probe_fingerprints: dict[str, str] = Field(default_factory=dict)
    initial_inventory_hash: str = ""
    final_inventory_hash: str = ""
    inventory_restored: bool | None = None
    session: ProbeSessionResult

    @property
    def restoration(self) -> InventoryRestoration:
        return classify_inventory_restoration(
            self.inventory_restored,
            mutated=bool(self.session.session.mutations),
        )

    @property
    def reusable(self) -> bool:
        return (
            self.session.session.cleanup_status is not CleanupStatus.DIRTY_SESSION
            and self.restoration in _REUSABLE_RESTORATIONS
            and all(
                result.context is None or result.context.reusable
                for result in self.session.results
            )
        )

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
    non_poe_e4: E4ReadinessState = E4ReadinessState.PARTIAL
    full_poe_e4: E4ReadinessState = E4ReadinessState.PARTIAL
    required_capabilities_by_role: dict[str, list[str]] = Field(default_factory=dict)
    blockers_by_role: dict[str, list[str]] = Field(default_factory=dict)

    @property
    def e4_ready(self) -> bool:
        """E4 base puede continuar si el escenario no-PoE está completamente listo."""
        return self.non_poe_e4 is E4ReadinessState.READY
