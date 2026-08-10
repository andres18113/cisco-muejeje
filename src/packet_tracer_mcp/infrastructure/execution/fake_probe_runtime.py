"""Doble offline de PacketTracerProbeRuntime para pruebas de E3.5."""

from __future__ import annotations

from copy import deepcopy

from ...domain.enterprise.models.capabilities import CapabilityStatus, EvidenceSource
from ...domain.enterprise.models.discovery import (
    CapabilityBackend,
    CapabilityVerificationMethod,
    CapabilityProbeResult,
    ProbeEnvironment,
    ProbeDefinition,
    ProbeExecutionStatus,
    RuntimeDeviceDescriptor,
    RuntimeDeviceObservation,
    semantic_inventory_fingerprint,
)


class FakePacketTracerProbeRuntime:
    def __init__(
        self,
        observations: dict[str, RuntimeDeviceObservation] | None = None,
        probe_results: dict[tuple[str, str], CapabilityProbeResult] | None = None,
        packet_tracer_version: str | None = "PT-test",
        enumerated_models: list[RuntimeDeviceDescriptor] | None = None,
        cleanup_failures: set[str] | None = None,
        create_failures: dict[str, Exception] | None = None,
        transport_channel: str = "offline_fake",
        extension_version: str = "",
        existing_inventory: list[dict[str, str]] | None = None,
    ) -> None:
        self.observations = observations or {}
        self.probe_results = probe_results or {}
        self._version = packet_tracer_version
        self.enumerated_models = enumerated_models
        self.cleanup_failures = cleanup_failures or set()
        self.create_failures = create_failures or {}
        self.transport_channel = transport_channel
        self.extension_version = extension_version
        self.existing_inventory = existing_inventory or []
        self.create_device_calls = 0
        self.delete_device_calls = 0
        self.created_names: list[str] = []
        self._models_by_name: dict[str, str] = {}
        self.power_cycle_calls = 0

    def packet_tracer_version(self) -> str | None:
        return self._version

    def probe_environment(self) -> ProbeEnvironment:
        return ProbeEnvironment(
            backend=CapabilityBackend.PACKET_TRACER,
            backend_version=self._version or "",
            transport_channel=self.transport_channel,
            extension_version=self.extension_version,
        )

    def inventory_fingerprint(self) -> str:
        temporary = [
            {"name": name, "model": model}
            for name, model in self._models_by_name.items()
        ]
        return semantic_inventory_fingerprint([*self.existing_inventory, *temporary])

    def discover_models(self) -> list[RuntimeDeviceDescriptor] | None:
        return deepcopy(self.enumerated_models)

    def create_temporary_device(self, runtime_model: str, temporary_name: str) -> RuntimeDeviceObservation:
        self.create_device_calls += 1
        if runtime_model in self.create_failures:
            raise self.create_failures[runtime_model]
        self.created_names.append(temporary_name)
        self._models_by_name[temporary_name] = runtime_model
        return deepcopy(self.observations.get(runtime_model, RuntimeDeviceObservation(found=False)))

    def delete_temporary_device(self, temporary_name: str) -> bool:
        self.delete_device_calls += 1
        if temporary_name in self.cleanup_failures or "*" in self.cleanup_failures:
            return False
        self._models_by_name.pop(temporary_name, None)
        return True

    def reset_temporary_device(self, temporary_name: str) -> bool:
        return self.power_cycle(temporary_name)

    def power_cycle(self, temporary_name: str) -> bool:
        """Hook explícito para tests futuros de módulos, sin sleeps reales."""
        self.power_cycle_calls += 1
        return temporary_name in self._models_by_name

    def probe_capability(
        self, temporary_name: str, capability: str, definition: ProbeDefinition
    ) -> CapabilityProbeResult:
        model = self._models_by_name.get(temporary_name, "")
        result = self.probe_results.get((model, capability))
        if result is not None:
            return deepcopy(result)
        if capability == "configuration_channel":
            return CapabilityProbeResult(
                probe_id=definition.id, model=model, capability=capability,
                status=CapabilityStatus.SUPPORTED, execution_status=ProbeExecutionStatus.VERIFIED,
                evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME, verified=True,
                verification_method=CapabilityVerificationMethod.DIRECT_RUNTIME_API,
            )
        return CapabilityProbeResult(
            probe_id=definition.id,
            model=model,
            capability=capability,
            execution_status=ProbeExecutionStatus.SKIPPED,
            evidence_source=EvidenceSource.CONTROLLED_PROBE,
        )
