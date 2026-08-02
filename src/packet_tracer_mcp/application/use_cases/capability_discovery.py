"""Caso de uso E3.5: descubrimiento seguro y versionado de capacidades PT."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from ...domain.enterprise.models.capabilities import CapabilityStatus, EvidenceSource
from ...domain.enterprise.models.discovery import (
    PROBE_SCHEMA_VERSION,
    CapabilityProbeResult,
    CapabilitySnapshot,
    CatalogGapReport,
    CleanupStatus,
    DeviceIdentity,
    DiscoverySource,
    E4ReadinessReport,
    E4ReadinessState,
    ModelIdentityStatus,
    ProbeCost,
    ProbeDefinition,
    ProbeExecutionStatus,
    ProbeLevel,
    ProbeRequest,
    ProbeSafety,
    ProbeSession,
    ProbeSessionResult,
    RuntimeDeviceDescriptor,
    RuntimeDeviceObservation,
)


DEFAULT_SAFE_MODELS = ("PC-PT", "2911", "2960-24TT", "3560-24PS")


class PacketTracerProbeRuntime(Protocol):
    """Puerto tipado: el dominio no conoce bridge, JavaScript ni FastMCP."""

    def packet_tracer_version(self) -> str | None: ...

    def discover_models(self) -> list[RuntimeDeviceDescriptor] | None: ...

    def create_temporary_device(self, runtime_model: str, temporary_name: str) -> RuntimeDeviceObservation: ...

    def delete_temporary_device(self, temporary_name: str) -> bool: ...

    def probe_capability(
        self, temporary_name: str, capability: str, definition: ProbeDefinition
    ) -> CapabilityProbeResult: ...


class SnapshotRepository(Protocol):
    def find_cached(
        self, packet_tracer_version: str | None, models: list[str], capabilities: list[str],
        probe_schema_version: int,
    ) -> CapabilitySnapshot | None: ...

    def save_runtime(self, snapshot: CapabilitySnapshot): ...


class CapabilityProbeRegistry:
    """Registro pequeño y declarativo; los comandos nunca provienen del usuario."""

    _definitions = {
        "model_exists": ProbeDefinition(
            id="model-exists", capability="model_exists", cost=ProbeCost.CHEAP,
        ),
        "port_inventory": ProbeDefinition(
            id="port-inventory", capability="port_inventory", prerequisites=["model_exists"],
            cost=ProbeCost.CHEAP,
        ),
        "supports_modules": ProbeDefinition(
            id="module-inventory", capability="supports_modules", prerequisites=["model_exists"],
            cost=ProbeCost.NORMAL, safety=ProbeSafety.MUTATING, requires_power_cycle=True,
        ),
        "supports_poe": ProbeDefinition(
            id="poe-inventory", capability="supports_poe", prerequisites=["port_inventory"],
            cost=ProbeCost.CHEAP,
        ),
        "layer2": ProbeDefinition(
            id="layer2-probe", capability="layer2", prerequisites=["port_inventory"],
            cost=ProbeCost.NORMAL, safety=ProbeSafety.DESTRUCTIVE_TO_PROBE_DEVICE,
        ),
        "supports_vlan": ProbeDefinition(
            id="vlan-probe", capability="supports_vlan", prerequisites=["layer2"],
            cost=ProbeCost.NORMAL, safety=ProbeSafety.DESTRUCTIVE_TO_PROBE_DEVICE,
        ),
        "supports_trunk": ProbeDefinition(
            id="trunk-probe", capability="supports_trunk", prerequisites=["supports_vlan"],
            cost=ProbeCost.NORMAL, safety=ProbeSafety.DESTRUCTIVE_TO_PROBE_DEVICE,
        ),
        "layer3": ProbeDefinition(
            id="layer3-probe", capability="layer3", prerequisites=["port_inventory"],
            cost=ProbeCost.NORMAL, safety=ProbeSafety.DESTRUCTIVE_TO_PROBE_DEVICE,
        ),
        "supports_static_routes": ProbeDefinition(
            id="static-route-probe", capability="supports_static_routes", prerequisites=["layer3"],
            cost=ProbeCost.NORMAL, safety=ProbeSafety.DESTRUCTIVE_TO_PROBE_DEVICE,
        ),
        "supports_ospf": ProbeDefinition(
            id="ospf-probe", capability="supports_ospf", prerequisites=["layer3"],
            cost=ProbeCost.NORMAL, safety=ProbeSafety.DESTRUCTIVE_TO_PROBE_DEVICE,
        ),
    }

    def definitions_for(self, capabilities: Iterable[str]) -> list[ProbeDefinition]:
        selected: dict[str, ProbeDefinition] = {}

        def include(capability: str) -> None:
            definition = self._definitions.get(capability)
            if definition is None or capability in selected:
                return
            for prerequisite in definition.prerequisites:
                include(prerequisite)
            selected[capability] = definition

        for capability in capabilities:
            include(capability)
        return list(selected.values())

    @property
    def known_capabilities(self) -> list[str]:
        return list(self._definitions)


class CapabilityDiscoveryService:
    """Orquesta sesiones secuenciales, cleanup y snapshots sin depender de MCP."""

    def __init__(
        self,
        runtime: PacketTracerProbeRuntime,
        snapshots: SnapshotRepository,
        identity_for: Callable[[str, str | None], DeviceIdentity],
        registry: CapabilityProbeRegistry | None = None,
    ) -> None:
        self._runtime = runtime
        self._snapshots = snapshots
        self._identity_for = identity_for
        self._registry = registry or CapabilityProbeRegistry()

    @property
    def known_capabilities(self) -> list[str]:
        return self._registry.known_capabilities

    def run(self, request: ProbeRequest) -> tuple[CapabilitySnapshot, bool]:
        version = request.packet_tracer_version or self._runtime.packet_tracer_version()
        models = request.models or list(DEFAULT_SAFE_MODELS)
        capabilities = self._requested_capabilities(request)
        if not request.force:
            cached = self._snapshots.find_cached(version, models, capabilities, PROBE_SCHEMA_VERSION)
            if cached is not None:
                return cached, True

        session = ProbeSession(
            session_id=f"probe-{uuid4().hex[:12]}",
            packet_tracer_version=version,
        )
        descriptors: list[RuntimeDeviceDescriptor] = []
        results: list[CapabilityProbeResult] = []
        deleted: list[str] = []
        failed: list[str] = []
        enumerated = self._runtime.discover_models() if request.probe_level is ProbeLevel.DISCOVERY else None
        if enumerated:
            descriptors.extend(enumerated)
            requested = {model.casefold() for model in models}
            descriptors = [
                descriptor for descriptor in descriptors
                if not requested or _descriptor_name(descriptor).casefold() in requested
            ]

        for index, model in enumerate(models, start=1):
            existing = next((item for item in descriptors if _descriptor_name(item).casefold() == model.casefold()), None)
            if existing is not None and existing.observed:
                self._append_observed_results(existing, capabilities, results, version)
                continue
            name = f"__MCP_PROBE_{session.session_id.rsplit('-', 1)[-1]}_{index:02d}"
            try:
                observation = self._runtime.create_temporary_device(model, name)
            except TimeoutError as exc:
                observation = RuntimeDeviceObservation(error=str(exc))
                results.append(_error_result(model, "model_exists", ProbeExecutionStatus.TIMEOUT, str(exc), version))
            except Exception as exc:
                observation = RuntimeDeviceObservation(error=str(exc))
                results.append(_error_result(model, "model_exists", ProbeExecutionStatus.EXECUTION_ERROR, str(exc), version))
            else:
                if observation.found:
                    session.created_devices.append(name)
                descriptor = self._descriptor(model, observation, version)
                descriptors.append(descriptor)
                if observation.found:
                    self._append_observed_results(descriptor, capabilities, results, version)
                    self._run_runtime_probes(name, model, capabilities, results, version)
                else:
                    results.append(CapabilityProbeResult(
                        probe_id="model-exists", model=model, capability="model_exists",
                        execution_status=ProbeExecutionStatus.VERIFY_FAILED,
                        evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME,
                        failure_reason=observation.error or "Controlled create did not produce a device; runtime identity remains unresolved.",
                        packet_tracer_version=version,
                    ))
            finally:
                if name in session.created_devices:
                    try:
                        if self._runtime.delete_temporary_device(name):
                            deleted.append(name)
                        else:
                            failed.append(name)
                    except Exception:
                        failed.append(name)

        if failed:
            session.cleanup_status = CleanupStatus.DIRTY_SESSION
            session.warnings.append("Cleanup incompleto; revisar exclusivamente los devices temporales listados.")
        elif session.created_devices:
            session.cleanup_status = CleanupStatus.CLEAN
        result = ProbeSessionResult(
            session=session, devices=descriptors, results=_dedupe_results(results),
            cleanup_deleted=deleted, cleanup_failed=failed,
        )
        snapshot = CapabilitySnapshot(packet_tracer_version=version, session=result)
        self._snapshots.save_runtime(snapshot)
        return snapshot, False

    def readiness_report(self, snapshot: CapabilitySnapshot) -> E4ReadinessReport:
        unknowns = snapshot.blocking_unknowns()
        result_map = {(item.model, item.capability): item.status for item in snapshot.session.results}
        models = {item.identity.canonical_id or item.identity.runtime_id or item.identity.display_name for item in snapshot.session.devices}
        identity = E4ReadinessState.READY if not unknowns.get("model_identity") else E4ReadinessState.BLOCKED
        ports = _aggregate_state(result_map, models, "port_inventory")
        modules = _aggregate_state(result_map, models, "supports_modules")
        poe = _aggregate_state(result_map, models, "supports_poe")
        l3 = _aggregate_state(result_map, models, "layer3")
        return E4ReadinessReport(
            model_identity=identity,
            port_inventory=ports,
            module_support=modules,
            access_switch_selection=poe,
            poe_selection=poe,
            distribution_l3=l3,
            core_l3=l3,
            edge_router=l3,
            blocking_unknowns=unknowns,
        )

    @staticmethod
    def catalog_gap_report(snapshot: CapabilitySnapshot, catalog_models: Iterable[str]) -> CatalogGapReport:
        """Compara únicamente el alcance observado; nunca promociona modelos."""
        catalog = set(catalog_models)
        matched = {
            item.identity.canonical_id for item in snapshot.session.devices
            if item.identity.status is ModelIdentityStatus.CATALOG_MATCHED and item.identity.canonical_id
        }
        runtime_only = sorted({
            item.identity.runtime_id or item.identity.display_name
            for item in snapshot.session.devices if item.identity.status is ModelIdentityStatus.RUNTIME_ONLY
        })
        gaps: dict[str, list[str]] = {}
        for result in snapshot.session.results:
            if result.status is CapabilityStatus.UNKNOWN:
                gaps.setdefault(result.model, []).append(result.capability)
        return CatalogGapReport(
            known=sorted(matched),
            runtime_only=runtime_only,
            catalog_only=sorted(catalog - matched),
            capability_gaps={model: sorted(values) for model, values in sorted(gaps.items())},
        )

    def _requested_capabilities(self, request: ProbeRequest) -> list[str]:
        if request.capabilities:
            requested = request.capabilities
        elif request.probe_level is ProbeLevel.DISCOVERY:
            requested = ["model_exists"]
        elif request.probe_level is ProbeLevel.LOGICAL:
            requested = ["model_exists", "port_inventory", "layer2", "supports_vlan", "supports_trunk", "layer3"]
        else:
            requested = ["model_exists", "port_inventory", "supports_modules", "supports_poe"]
        return [
            definition.capability
            for definition in self._registry.definitions_for(requested)
        ]

    def _descriptor(
        self, requested_model: str, observation: RuntimeDeviceObservation, version: str | None
    ) -> RuntimeDeviceDescriptor:
        identity = self._identity_for(observation.runtime_id or requested_model, version)
        if observation.found and identity.status is ModelIdentityStatus.UNRESOLVED_IDENTITY:
            identity = identity.model_copy(update={
                "runtime_id": observation.runtime_id or requested_model,
                "display_name": observation.display_name or requested_model,
                "category": observation.category,
                "packet_tracer_version": version,
                "status": ModelIdentityStatus.RUNTIME_ONLY,
            })
        if not observation.found:
            identity = DeviceIdentity(
                runtime_id=requested_model,
                display_name=requested_model,
                packet_tracer_version=version,
                status=ModelIdentityStatus.UNRESOLVED_IDENTITY,
            )
        return RuntimeDeviceDescriptor(
            identity=identity,
            discovery_source=DiscoverySource.CONTROLLED_CREATE_PROBE,
            ports=observation.ports,
            modules=observation.modules,
            observed=observation.found,
            warnings=[observation.error] if observation.error else [],
        )

    def _append_observed_results(
        self,
        descriptor: RuntimeDeviceDescriptor,
        capabilities: list[str],
        results: list[CapabilityProbeResult],
        version: str | None,
    ) -> None:
        model = _descriptor_name(descriptor)
        for capability in capabilities:
            if capability == "model_exists":
                results.append(_physical_result(model, capability, CapabilityStatus.SUPPORTED, version, "Device created and read back."))
            elif capability == "port_inventory":
                results.append(_physical_result(model, capability, CapabilityStatus.SUPPORTED, version, f"{len(descriptor.ports)} port(s) observed."))
            elif capability == "supports_modules":
                status = CapabilityStatus.SUPPORTED if descriptor.modules else CapabilityStatus.UNKNOWN
                results.append(_physical_result(model, capability, status, version, "Module inventory observed." if descriptor.modules else "No runtime module inventory available."))
            elif capability == "supports_poe":
                statuses = {port.poe_status for port in descriptor.ports}
                status = _observed_status(statuses)
                results.append(_physical_result(
                    model, capability, status, version,
                    "Port power state observed." if status is not CapabilityStatus.UNKNOWN else "Runtime does not expose reliable PoE state.",
                    observed_value=sum(port.poe_status is CapabilityStatus.SUPPORTED for port in descriptor.ports) if status is CapabilityStatus.SUPPORTED else None,
                ))

    def _run_runtime_probes(
        self, name: str, model: str, capabilities: list[str], results: list[CapabilityProbeResult], version: str | None
    ) -> None:
        observed = {item.capability: item.status for item in results if item.model == model}
        for definition in self._registry.definitions_for(capabilities):
            if definition.capability in {"model_exists", "port_inventory", "supports_modules", "supports_poe"}:
                continue
            if any(observed.get(prerequisite) is not CapabilityStatus.SUPPORTED for prerequisite in definition.prerequisites):
                results.append(CapabilityProbeResult(
                    probe_id=definition.id, model=model, capability=definition.capability,
                    execution_status=ProbeExecutionStatus.PREREQUISITE_MISSING,
                    evidence_source=EvidenceSource.CONTROLLED_PROBE,
                    failure_reason="Prerequisite capability was not verified.",
                    packet_tracer_version=version,
                ))
                continue
            result = self._runtime.probe_capability(name, definition.capability, definition)
            results.append(result.model_copy(update={"model": model, "packet_tracer_version": version}))
            observed[definition.capability] = result.status


def _descriptor_name(descriptor: RuntimeDeviceDescriptor) -> str:
    return descriptor.identity.canonical_id or descriptor.identity.runtime_id or descriptor.identity.display_name


def _observed_status(statuses: set[CapabilityStatus]) -> CapabilityStatus:
    known = statuses - {CapabilityStatus.UNKNOWN}
    if len(known) == 1 and CapabilityStatus.UNKNOWN not in statuses:
        return next(iter(known))
    return CapabilityStatus.UNKNOWN


def _physical_result(
    model: str, capability: str, status: CapabilityStatus, version: str | None, summary: str,
    observed_value: int | None = None,
) -> CapabilityProbeResult:
    return CapabilityProbeResult(
        probe_id=capability.replace("_", "-"), model=model, capability=capability, status=status,
        execution_status=ProbeExecutionStatus.VERIFIED if status is not CapabilityStatus.UNKNOWN else ProbeExecutionStatus.SKIPPED,
        evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME,
        verified=status is not CapabilityStatus.UNKNOWN,
        raw_summary=summary, observed_value=observed_value, packet_tracer_version=version,
    )


def _error_result(model: str, capability: str, execution: ProbeExecutionStatus, reason: str, version: str | None) -> CapabilityProbeResult:
    return CapabilityProbeResult(
        probe_id=capability.replace("_", "-"), model=model, capability=capability,
        execution_status=execution, evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME,
        failure_reason=reason, packet_tracer_version=version,
    )


def _dedupe_results(results: list[CapabilityProbeResult]) -> list[CapabilityProbeResult]:
    selected: dict[tuple[str, str], CapabilityProbeResult] = {}
    for result in results:
        key = (result.model, result.capability)
        existing = selected.get(key)
        if existing is None or result.execution_status is ProbeExecutionStatus.VERIFIED:
            selected[key] = result
    return [selected[key] for key in sorted(selected)]


def _aggregate_state(
    results: dict[tuple[str, str], CapabilityStatus], models: set[str], capability: str
) -> E4ReadinessState:
    statuses = [results.get((model, capability), CapabilityStatus.UNKNOWN) for model in models]
    if statuses and all(status is CapabilityStatus.SUPPORTED for status in statuses):
        return E4ReadinessState.READY
    if any(status is CapabilityStatus.UNSUPPORTED for status in statuses):
        return E4ReadinessState.BLOCKED
    return E4ReadinessState.PARTIAL
