"""Caso de uso E3.5: descubrimiento seguro y versionado de capacidades PT."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from ...domain.enterprise.models.capabilities import CapabilityStatus, EvidenceSource
from ...domain.enterprise.models.discovery import (
    PROBE_SCHEMA_VERSION,
    CapabilityProbeResult,
    CapabilitySnapshot,
    CapabilityBackend,
    CapabilityVerificationMethod,
    CatalogGapReport,
    CleanupStatus,
    DeviceIdentity,
    DiscoverySource,
    E4ReadinessReport,
    BackendVersionProvenance,
    E4ReadinessState,
    ModelIdentityStatus,
    inventory_restoration_matches,
    ProbeCost,
    ProbeContext,
    ProbeDefinition,
    ProbeEnvironment,
    ProbeExecutionStatus,
    ProbeIsolationLevel,
    ProbeLevel,
    ProbeRequest,
    ProbeSafety,
    ProbeSession,
    ProbeSessionResult,
    RuntimeDeviceDescriptor,
    RuntimeDeviceObservation,
)


DEFAULT_SAFE_MODELS = ("PC-PT", "2911", "2960-24TT", "3560-24PS")

if TYPE_CHECKING:
    from ...domain.enterprise.models.hardware import HardwarePlan
    from ...domain.enterprise.models.roles import DeviceRole


class PacketTracerProbeRuntime(Protocol):
    """Puerto tipado: el dominio no conoce bridge, JavaScript ni FastMCP."""

    def packet_tracer_version(self) -> str | None: ...

    def probe_environment(self) -> ProbeEnvironment: ...

    def inventory_fingerprint(self) -> str: ...

    def discover_models(self) -> list[RuntimeDeviceDescriptor] | None: ...

    def create_temporary_device(self, runtime_model: str, temporary_name: str) -> RuntimeDeviceObservation: ...

    def delete_temporary_device(self, temporary_name: str) -> bool: ...

    def probe_capability(
        self, temporary_name: str, capability: str, definition: ProbeDefinition
    ) -> CapabilityProbeResult: ...


class SnapshotRepository(Protocol):
    def find_cached(
        self, packet_tracer_version: str | None, models: list[str], capabilities: list[str],
        probe_schema_version: int, environment_fingerprint: str = "",
        probe_fingerprints: dict[str, str] | None = None,
        initial_inventory_hash: str = "",
    ) -> CapabilitySnapshot | None: ...

    def save_runtime(self, snapshot: CapabilitySnapshot): ...


class CapabilityProbeRegistry:
    """Registro pequeño y declarativo; los comandos nunca provienen del usuario."""

    _definitions = {
        "model_exists": ProbeDefinition(
            id="model-exists", capability="model_exists", cost=ProbeCost.CHEAP,
            isolation_level=ProbeIsolationLevel.SHARED_DEVICE,
        ),
        "port_inventory": ProbeDefinition(
            id="port-inventory", capability="port_inventory", prerequisites=["model_exists"],
            cost=ProbeCost.CHEAP, isolation_level=ProbeIsolationLevel.SHARED_DEVICE,
        ),
        "supports_modules": ProbeDefinition(
            id="module-inventory", capability="supports_modules", prerequisites=["model_exists"],
            cost=ProbeCost.NORMAL, safety=ProbeSafety.MUTATING, requires_power_cycle=True,
            isolation_level=ProbeIsolationLevel.RESET_REQUIRED,
        ),
        "module_slot_enumeration": ProbeDefinition(
            id="module-slot-enumeration", capability="module_slot_enumeration",
            prerequisites=["model_exists"], cost=ProbeCost.CHEAP,
            isolation_level=ProbeIsolationLevel.SHARED_DEVICE,
        ),
        "module_installed_identity": ProbeDefinition(
            id="module-installed-identity", capability="module_installed_identity",
            prerequisites=["module_slot_enumeration"], cost=ProbeCost.CHEAP,
            isolation_level=ProbeIsolationLevel.SHARED_DEVICE,
        ),
        "supports_poe": ProbeDefinition(
            id="poe-inventory", probe_version="2", capability="supports_poe",
            prerequisites=["port_inventory"],
            cost=ProbeCost.CHEAP, isolation_level=ProbeIsolationLevel.SHARED_DEVICE,
        ),
        "layer2": ProbeDefinition(
            id="layer2-probe", capability="layer2", prerequisites=["port_inventory"],
            cost=ProbeCost.NORMAL, safety=ProbeSafety.DESTRUCTIVE_TO_PROBE_DEVICE,
            isolation_level=ProbeIsolationLevel.SHARED_DEVICE,
        ),
        "configuration_channel": ProbeDefinition(
            id="configuration-channel", capability="configuration_channel", prerequisites=["model_exists"],
            cost=ProbeCost.NORMAL, safety=ProbeSafety.DESTRUCTIVE_TO_PROBE_DEVICE,
            isolation_level=ProbeIsolationLevel.SHARED_DEVICE,
        ),
        "supports_vlan": ProbeDefinition(
            id="vlan-probe", capability="supports_vlan", prerequisites=["layer2", "configuration_channel"],
            cost=ProbeCost.NORMAL, safety=ProbeSafety.DESTRUCTIVE_TO_PROBE_DEVICE, requires_fresh_device=True,
            isolation_level=ProbeIsolationLevel.FRESH_DEVICE_REQUIRED,
        ),
        "supports_trunk": ProbeDefinition(
            id="trunk-probe", capability="supports_trunk", prerequisites=["supports_vlan"],
            cost=ProbeCost.NORMAL, safety=ProbeSafety.DESTRUCTIVE_TO_PROBE_DEVICE, requires_fresh_device=True,
            isolation_level=ProbeIsolationLevel.FRESH_DEVICE_REQUIRED,
        ),
        "layer3": ProbeDefinition(
            id="layer3-probe", capability="layer3", prerequisites=["port_inventory", "configuration_channel"],
            cost=ProbeCost.NORMAL, safety=ProbeSafety.DESTRUCTIVE_TO_PROBE_DEVICE, requires_fresh_device=True,
            isolation_level=ProbeIsolationLevel.FRESH_DEVICE_REQUIRED,
        ),
        "multilayer_intervlan": ProbeDefinition(
            id="multilayer-intervlan-probe", capability="multilayer_intervlan",
            prerequisites=["supports_vlan", "configuration_channel"],
            cost=ProbeCost.EXPENSIVE, safety=ProbeSafety.DESTRUCTIVE_TO_PROBE_DEVICE,
            requires_fresh_device=True,
            isolation_level=ProbeIsolationLevel.FRESH_DEVICE_REQUIRED,
        ),
        "supports_static_routes": ProbeDefinition(
            id="static-route-probe", capability="supports_static_routes", prerequisites=["layer3"],
            cost=ProbeCost.NORMAL, safety=ProbeSafety.DESTRUCTIVE_TO_PROBE_DEVICE,
            isolation_level=ProbeIsolationLevel.FRESH_DEVICE_REQUIRED,
        ),
        "supports_ospf": ProbeDefinition(
            id="ospf-probe", capability="supports_ospf", prerequisites=["layer3"],
            cost=ProbeCost.NORMAL, safety=ProbeSafety.DESTRUCTIVE_TO_PROBE_DEVICE,
            isolation_level=ProbeIsolationLevel.FRESH_DEVICE_REQUIRED,
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
        environment = self._probe_environment(version)
        environment_fingerprint = environment.semantic_fingerprint()
        initial_inventory_hash = self._inventory_fingerprint()
        definitions = {
            definition.capability: definition
            for definition in self._registry.definitions_for(capabilities)
        }
        probe_fingerprints = {
            _probe_fingerprint_key(model, capability): definitions[capability].semantic_fingerprint(
                model,
                {
                    "probe_level": request.probe_level.value,
                    "categories": sorted(request.categories),
                },
            )
            for model in models
            for capability in capabilities
            if capability in definitions
        }
        if not request.force:
            cached = self._snapshots.find_cached(
                version,
                models,
                capabilities,
                PROBE_SCHEMA_VERSION,
                environment_fingerprint=environment_fingerprint,
                probe_fingerprints=probe_fingerprints,
                initial_inventory_hash=initial_inventory_hash,
            )
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
            session.mutations.append(f"temporary-device-attempt:{model}")
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
                    session.mutations.append(f"temporary-device:{model}")
                descriptor = self._descriptor(model, observation, version)
                descriptors.append(descriptor)
                if observation.found:
                    self._append_observed_results(descriptor, capabilities, results, version)
                    self._run_runtime_probes(name, model, capabilities, results, version, session, deleted, failed)
                else:
                    results.append(CapabilityProbeResult(
                        probe_id="model-exists", model=model, capability="model_exists",
                        execution_status=ProbeExecutionStatus.VERIFY_FAILED,
                        evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME,
                        failure_reason=observation.error or "Controlled create did not produce a device; runtime identity remains unresolved.",
                        packet_tracer_version=version,
                    ))
            finally:
                self._cleanup_temporary_device(name, deleted, failed)

        if failed:
            session.cleanup_status = CleanupStatus.DIRTY_SESSION
            session.warnings.append("Cleanup incompleto; revisar exclusivamente los devices temporales listados.")
        elif session.mutations:
            session.cleanup_status = CleanupStatus.CLEAN
        final_inventory_hash = self._converged_inventory_fingerprint(
            initial_inventory_hash,
        )
        inventory_restored = (
            inventory_restoration_matches(
                initial_inventory_hash, final_inventory_hash,
            )
            if initial_inventory_hash and final_inventory_hash
            else None
        )
        if inventory_restored is False:
            session.cleanup_status = CleanupStatus.DIRTY_SESSION
            session.warnings.append(
                "El inventario runtime final no coincide con el inventario previo al probe."
            )
        finalized_results = _finalize_probe_results(
            _dedupe_results(results),
            definitions=definitions,
            environment=environment,
            environment_fingerprint=environment_fingerprint,
            probe_fingerprints=probe_fingerprints,
            initial_inventory_hash=initial_inventory_hash,
            final_inventory_hash=final_inventory_hash,
            inventory_restored=inventory_restored,
            cleanup_status=session.cleanup_status,
            session_mutations=session.mutations,
        )
        result = ProbeSessionResult(
            session=session, devices=descriptors, results=finalized_results,
            cleanup_deleted=deleted, cleanup_failed=failed,
        )
        snapshot = CapabilitySnapshot(
            packet_tracer_version=version,
            # El bridge confirmado no expone versión: lo más fuerte que puede
            # afirmarse hoy es que el entorno la declaró. Nunca se marca como
            # observada directamente sin un getter real.
            backend_version_provenance=(
                BackendVersionProvenance.DECLARED_ENVIRONMENT if version
                else BackendVersionProvenance.UNKNOWN
            ),
            backend=environment.backend,
            environment_fingerprint=environment_fingerprint,
            probe_fingerprints=probe_fingerprints,
            initial_inventory_hash=initial_inventory_hash,
            final_inventory_hash=final_inventory_hash,
            inventory_restored=inventory_restored,
            session=result,
        )
        self._snapshots.save_runtime(snapshot)
        return snapshot, False

    def _probe_environment(self, version: str | None) -> ProbeEnvironment:
        provider = getattr(self._runtime, "probe_environment", None)
        environment = provider() if callable(provider) else None
        if not isinstance(environment, ProbeEnvironment):
            environment = ProbeEnvironment(
                backend=CapabilityBackend.PACKET_TRACER,
                backend_version=version or "",
            )
        elif not environment.backend_version and version:
            environment = environment.model_copy(update={"backend_version": version})
        return environment

    def _inventory_fingerprint(self) -> str:
        provider = getattr(self._runtime, "inventory_fingerprint", None)
        if not callable(provider):
            return ""
        try:
            value = provider()
        except Exception:
            return ""
        return value if isinstance(value, str) else ""

    def _converged_inventory_fingerprint(self, expected: str) -> str:
        """Permite que el adapter espere la convergencia asíncrona del cleanup."""
        waiter = getattr(self._runtime, "wait_for_inventory_fingerprint", None)
        if callable(waiter) and expected:
            try:
                value = waiter(expected, 5.0)
            except Exception:
                value = ""
            if isinstance(value, str) and value:
                return value
        return self._inventory_fingerprint()

    def readiness_report(
        self, snapshot: CapabilitySnapshot, hardware_plan: HardwarePlan | None = None,
    ) -> E4ReadinessReport:
        """Calcula readiness por rol; una capability no requerida no bloquea E4."""
        unknowns = snapshot.blocking_unknowns()
        result_map = {(item.model, item.capability): item.status for item in snapshot.session.results}
        models = {item.identity.canonical_id or item.identity.runtime_id or item.identity.display_name for item in snapshot.session.devices}
        identity = E4ReadinessState.READY if not unknowns.get("model_identity") else E4ReadinessState.BLOCKED
        ports = _aggregate_state(result_map, models, "port_inventory")
        modules = _aggregate_state(result_map, models, "supports_modules")
        poe = _aggregate_state(result_map, models, "supports_poe")
        l3 = _aggregate_state(result_map, models, "layer3")
        required_by_role, models_by_role = _scenario_requirements(hardware_plan, models)
        blockers_by_role: dict[str, list[str]] = {}
        non_poe_states: list[E4ReadinessState] = []
        full_poe_states: list[E4ReadinessState] = []
        for role, required in required_by_role.items():
            role_states = [
                _aggregate_state(result_map, {model}, capability)
                for model in models_by_role.get(role, set())
                for capability in required
            ]
            role_state = _combine_states(role_states)
            non_poe_states.append(role_state)
            missing = [
                model + ":" + capability
                for model in sorted(models_by_role.get(role, set()))
                for capability in required
                if result_map.get((model, capability), CapabilityStatus.UNKNOWN) is not CapabilityStatus.SUPPORTED
            ]
            if missing:
                blockers_by_role[role] = missing
            full_poe_states.append(role_state)

        poe_models = models_by_role.get("access_switch", set())
        poe_states = [_aggregate_state(result_map, {model}, "supports_poe") for model in poe_models]
        if poe_states:
            full_poe_states.extend(poe_states)
            poe_missing = [
                model + ":supports_poe" for model in sorted(poe_models)
                if result_map.get((model, "supports_poe"), CapabilityStatus.UNKNOWN) is not CapabilityStatus.SUPPORTED
            ]
            if poe_missing:
                blockers_by_role["access_switch_poe"] = poe_missing

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
            non_poe_e4=_combine_states(non_poe_states),
            full_poe_e4=_combine_states(full_poe_states),
            required_capabilities_by_role=required_by_role,
            blockers_by_role=blockers_by_role,
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
            requested = ["model_exists", "port_inventory", "layer2", "configuration_channel", "supports_vlan", "supports_trunk", "layer3"]
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
            elif capability == "module_slot_enumeration":
                slots = len(descriptor.modules)
                results.append(_physical_result(
                    model, capability,
                    CapabilityStatus.SUPPORTED if slots else CapabilityStatus.UNKNOWN,
                    version,
                    f"{slots} slot(s) enumerated with type code(s) "
                    + ",".join(sorted({item.slot_type_code for item in descriptor.modules}))
                    if slots else "Runtime exposed no module tree.",
                    observed_value=slots or None,
                ))
            elif capability == "module_installed_identity":
                named = [item for item in descriptor.modules if item.identity_observable]
                with_ports = [item for item in descriptor.modules if item.port_count]
                results.append(_physical_result(
                    model, capability,
                    CapabilityStatus.SUPPORTED if named else CapabilityStatus.UNKNOWN,
                    version,
                    f"{len(named)} module name(s) observed." if named else (
                        "The module name getter answered without a name for "
                        f"{len(descriptor.modules)} enumerated slot(s), including "
                        f"{len(with_ports)} that expose ports; module identity is "
                        "not observable on this surface."
                        if descriptor.modules else "No module tree to identify."
                    ),
                    observed_value=len(named) or None,
                ))
            elif capability == "supports_poe":
                access_ports = [
                    port for port in descriptor.ports
                    if port.physical
                    and port.interface_type.casefold() in {"ethernet", "fastethernet"}
                ]
                statuses = {port.poe_status for port in access_ports}
                status = _observed_status(statuses)
                supported_count = sum(
                    port.poe_status is CapabilityStatus.SUPPORTED
                    for port in access_ports
                )
                if status is CapabilityStatus.SUPPORTED:
                    summary = (
                        f"{supported_count} fresh access port(s) exposed complete "
                        "administrative/runtime power-on state; powered-device "
                        "delivery was not observed."
                    )
                elif status is CapabilityStatus.UNSUPPORTED:
                    summary = (
                        f"{len(access_ports)} fresh access port(s) exposed complete "
                        "administrative/runtime power-off state; powered-device "
                        "delivery was not observed."
                    )
                else:
                    summary = (
                        "Access-port power fields were empty, missing, malformed, "
                        "mixed, or incomplete; powered-device delivery remains "
                        "unobserved."
                    )
                results.append(_physical_result(
                    model, capability, status, version,
                    summary,
                    observed_value=(
                        supported_count
                        if status is CapabilityStatus.SUPPORTED else None
                    ),
                    verification_method=CapabilityVerificationMethod.OBJECT_STATE,
                ))

    def _run_runtime_probes(
        self, name: str, model: str, capabilities: list[str], results: list[CapabilityProbeResult], version: str | None,
        session: ProbeSession, deleted: list[str], failed: list[str],
    ) -> None:
        observed = {item.capability: item.status for item in results if item.model == model}
        for definition in self._registry.definitions_for(capabilities):
            if definition.capability in {"model_exists", "port_inventory", "supports_modules", "supports_poe", "module_slot_enumeration", "module_installed_identity"}:
                continue
            if any(observed.get(prerequisite) is not CapabilityStatus.SUPPORTED for prerequisite in definition.prerequisites):
                results.append(CapabilityProbeResult(
                    probe_id=definition.id, model=model, capability=definition.capability,
                    # La ausencia de evidencia en un prerequisito no es un fallo
                    # del bridge ni una capability no soportada. El dependiente no
                    # se ejecutó y debe conservarse como UNKNOWN/SKIPPED.
                    execution_status=ProbeExecutionStatus.SKIPPED,
                    evidence_source=EvidenceSource.CONTROLLED_PROBE,
                    failure_reason="Prerequisite capability was not verified.",
                    packet_tracer_version=version,
                ))
                continue
            isolation = definition.effective_isolation_level
            if isolation is ProbeIsolationLevel.FRESH_SESSION_REQUIRED:
                begin_session = getattr(self._runtime, "start_fresh_probe_session", None)
                try:
                    fresh_session = bool(begin_session(definition.id)) if callable(begin_session) else False
                except Exception:
                    fresh_session = False
                if not fresh_session:
                    results.append(CapabilityProbeResult(
                        probe_id=definition.id,
                        model=model,
                        capability=definition.capability,
                        execution_status=ProbeExecutionStatus.PREREQUISITE_MISSING,
                        evidence_source=EvidenceSource.CONTROLLED_PROBE,
                        failure_reason="Runtime cannot guarantee a fresh probe session.",
                        packet_tracer_version=version,
                    ))
                    continue
            probe_name = name
            uses_fresh_device = isolation in {
                ProbeIsolationLevel.FRESH_DEVICE_REQUIRED,
                ProbeIsolationLevel.FRESH_SESSION_REQUIRED,
            }
            if uses_fresh_device:
                probe_name = f"{name}_{definition.id}"
                session.mutations.append(
                    f"fresh-device-attempt:{model}:{definition.capability}"
                )
                try:
                    fresh = self._runtime.create_temporary_device(model, probe_name)
                    if not fresh.found:
                        results.append(CapabilityProbeResult(
                            probe_id=definition.id, model=model, capability=definition.capability,
                            execution_status=ProbeExecutionStatus.VERIFY_FAILED,
                            evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME,
                            failure_reason=fresh.error or "Fresh temporary device was not created.",
                            packet_tracer_version=version,
                        ))
                        self._cleanup_temporary_device(probe_name, deleted, failed)
                        continue
                    session.created_devices.append(probe_name)
                    session.mutations.append(f"fresh-device:{model}:{definition.capability}")
                except Exception as exc:
                    results.append(_error_result(model, definition.capability, ProbeExecutionStatus.EXECUTION_ERROR, str(exc), version))
                    self._cleanup_temporary_device(probe_name, deleted, failed)
                    continue
            if isolation is ProbeIsolationLevel.RESET_REQUIRED:
                reset = getattr(self._runtime, "reset_temporary_device", None)
                if not callable(reset):
                    reset = getattr(self._runtime, "power_cycle", None)
                try:
                    reset_ok = bool(reset(probe_name)) if callable(reset) else False
                except Exception:
                    reset_ok = False
                if not reset_ok:
                    results.append(CapabilityProbeResult(
                        probe_id=definition.id,
                        model=model,
                        capability=definition.capability,
                        execution_status=ProbeExecutionStatus.PREREQUISITE_MISSING,
                        evidence_source=EvidenceSource.CONTROLLED_PROBE,
                        failure_reason="Runtime did not restore the required probe baseline.",
                        packet_tracer_version=version,
                    ))
                    continue
                session.mutations.append(f"reset-device:{model}:{definition.capability}")
            try:
                result = self._runtime.probe_capability(probe_name, definition.capability, definition)
            except TimeoutError as exc:
                result = _error_result(
                    model, definition.capability, ProbeExecutionStatus.TIMEOUT, str(exc), version,
                )
            except Exception as exc:
                result = _error_result(
                    model, definition.capability, ProbeExecutionStatus.EXECUTION_ERROR, str(exc), version,
                )
            copied = result.model_copy(update={"model": model, "packet_tracer_version": version})
            results.append(copied)
            observed[definition.capability] = copied.status
            if copied.configured:
                session.mutations.append(f"configure:{model}:{definition.capability}")
            if uses_fresh_device:
                self._cleanup_temporary_device(probe_name, deleted, failed)

    def _cleanup_temporary_device(
        self,
        name: str,
        deleted: list[str],
        failed: list[str],
    ) -> None:
        """Idempotently remove an attempted controlled name, even after timeout."""

        try:
            removed_or_absent = self._runtime.delete_temporary_device(name)
        except Exception:
            removed_or_absent = False
        target = deleted if removed_or_absent else failed
        if name not in target:
            target.append(name)


def _probe_fingerprint_key(model: str, capability: str) -> str:
    return f"{model}:{capability}"


def _finalize_probe_results(
    results: list[CapabilityProbeResult],
    *,
    definitions: dict[str, ProbeDefinition],
    environment: ProbeEnvironment,
    environment_fingerprint: str,
    probe_fingerprints: dict[str, str],
    initial_inventory_hash: str,
    final_inventory_hash: str,
    inventory_restored: bool | None,
    cleanup_status: CleanupStatus,
    session_mutations: list[str],
) -> list[CapabilityProbeResult]:
    invalid = (
        cleanup_status is CleanupStatus.DIRTY_SESSION
        or inventory_restored is False
        or (bool(session_mutations) and inventory_restored is not True)
    )
    finalized: list[CapabilityProbeResult] = []
    for result in results:
        definition = definitions.get(result.capability)
        isolation = (
            definition.effective_isolation_level
            if definition is not None
            else ProbeIsolationLevel.SHARED_DEVICE
        )
        expected_mutations = {
            f"temporary-device-attempt:{result.model}",
            f"temporary-device:{result.model}",
            f"fresh-device-attempt:{result.model}:{result.capability}",
            f"fresh-device:{result.model}:{result.capability}",
            f"reset-device:{result.model}:{result.capability}",
            f"configure:{result.model}:{result.capability}",
        }
        mutations = sorted(
            mutation for mutation in session_mutations
            if mutation in expected_mutations
        )
        status = CapabilityStatus.UNKNOWN if invalid else result.status
        verified = False if invalid else result.verified
        execution_status = result.execution_status
        failure_reason = result.failure_reason
        if invalid:
            if execution_status is ProbeExecutionStatus.VERIFIED:
                execution_status = ProbeExecutionStatus.VERIFY_FAILED
            reason = "Probe cleanup or inventory restoration was not verified."
            failure_reason = f"{failure_reason} {reason}".strip()
        context = ProbeContext(
            probe_id=result.probe_id,
            probe_version=definition.probe_version if definition is not None else "legacy",
            backend=environment.backend,
            backend_version=environment.backend_version,
            device_model=result.model,
            environment_fingerprint=environment_fingerprint,
            initial_inventory_hash=initial_inventory_hash,
            final_inventory_hash=final_inventory_hash,
            inventory_restored=inventory_restored,
            isolation_level=isolation,
            mutations=mutations,
            cleanup_status=cleanup_status,
            result_status=status,
            execution_status=execution_status,
            probe_fingerprint=probe_fingerprints.get(
                _probe_fingerprint_key(result.model, result.capability), "",
            ),
        )
        finalized.append(result.model_copy(update={
            "status": status,
            "verified": verified,
            "execution_status": execution_status,
            "failure_reason": failure_reason,
            "context": context,
        }))
    return finalized


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
    verification_method: CapabilityVerificationMethod | None = None,
) -> CapabilityProbeResult:
    return CapabilityProbeResult(
        probe_id=capability.replace("_", "-"), model=model, capability=capability, status=status,
        execution_status=ProbeExecutionStatus.VERIFIED if status is not CapabilityStatus.UNKNOWN else ProbeExecutionStatus.SKIPPED,
        evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME,
        verified=status is not CapabilityStatus.UNKNOWN,
        raw_summary=summary, observed_value=observed_value, packet_tracer_version=version,
        verification_method=verification_method,
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


def _combine_states(states: list[E4ReadinessState]) -> E4ReadinessState:
    if states and all(state is E4ReadinessState.READY for state in states):
        return E4ReadinessState.READY
    if any(state is E4ReadinessState.BLOCKED for state in states):
        return E4ReadinessState.BLOCKED
    return E4ReadinessState.PARTIAL


def _scenario_requirements(
    hardware_plan: HardwarePlan | None, observed_models: set[str],
) -> tuple[dict[str, list[str]], dict[str, set[str]]]:
    """Devuelve requisitos mínimos sólo para los roles realmente planificados."""
    from ...domain.enterprise.models.roles import DeviceRole

    profiles = {
        "endpoint": ["model_exists", "port_inventory"],
        "access_switch": ["model_exists", "port_inventory", "layer2", "supports_vlan", "supports_trunk"],
        "distribution_switch": ["model_exists", "port_inventory", "layer2", "supports_vlan", "supports_trunk", "layer3"],
        "core_switch": ["model_exists", "port_inventory", "layer2", "supports_vlan", "supports_trunk", "layer3"],
        "edge_router": ["model_exists", "port_inventory", "layer3"],
    }
    role_names = {
        DeviceRole.ACCESS_SWITCH: "access_switch",
        DeviceRole.DISTRIBUTION_SWITCH: "distribution_switch",
        DeviceRole.CORE_SWITCH: "core_switch",
        DeviceRole.EDGE_ROUTER: "edge_router",
        DeviceRole.WAN_ROUTER: "edge_router",
    }
    models_by_role: dict[str, set[str]] = {}
    if hardware_plan is not None:
        for site in hardware_plan.site_hardware:
            for device in site.devices:
                role = role_names.get(device.role, "endpoint")
                model = device.selected_model or device.provisional_model
                if model:
                    models_by_role.setdefault(role, set()).add(model)
                if device.required_capabilities and device.required_capabilities.requires_modules:
                    profiles.setdefault(role, []).append("supports_modules")
    else:
        for model in observed_models:
            lowered = model.casefold()
            if "2911" in lowered:
                role = "edge_router"
            elif "3560" in lowered:
                role = "distribution_switch"
            elif "2960" in lowered:
                role = "access_switch"
            else:
                role = "endpoint"
            models_by_role.setdefault(role, set()).add(model)
    required = {role: list(dict.fromkeys(profiles[role])) for role in sorted(models_by_role)}
    return required, models_by_role
