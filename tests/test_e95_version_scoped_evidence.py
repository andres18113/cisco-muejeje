"""La evidencia no cruza sesiones cuando nadie pudo nombrar la versión.

El file-bridge confirmado no expone la versión de Packet Tracer, así que una
snapshot puede quedar con `packet_tracer_version=None`. Dentro de su propia
sesión sigue siendo válida, pero dos builds distintas producirían snapshots
indistinguibles: `find_cached` no puede devolverla a una sesión posterior.
"""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.capability_discovery import (
    CapabilityDiscoveryService,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    BackendVersionProvenance,
    PROBE_SCHEMA_VERSION,
    ProbeRequest,
    RuntimeDeviceObservation,
    RuntimePortDescriptor,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from src.packet_tracer_mcp.infrastructure.execution.fake_probe_runtime import (
    FakePacketTracerProbeRuntime,
)
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)


def _observation(model: str = "2911") -> RuntimeDeviceObservation:
    return RuntimeDeviceObservation(
        found=True,
        runtime_id=model,
        display_name=model,
        ports=[RuntimePortDescriptor(name="GigabitEthernet0/0")],
    )


def _service(tmp_path, runtime):
    return CapabilityDiscoveryService(
        runtime,
        CapabilitySnapshotStore(tmp_path / "capabilities"),
        EnterpriseCapabilityAdapter().identity_for,
    )


def test_a_declared_version_is_never_recorded_as_directly_observed(tmp_path):
    """Lo más fuerte hoy es 'lo declaró el entorno'; no hay getter real."""
    runtime = FakePacketTracerProbeRuntime(
        {"2911": _observation()}, packet_tracer_version="9.0.1.0858",
    )

    snapshot, _ = _service(tmp_path, runtime).run(ProbeRequest(models=["2911"]))

    assert snapshot.packet_tracer_version == "9.0.1.0858"
    assert snapshot.backend_version_provenance is (
        BackendVersionProvenance.DECLARED_ENVIRONMENT
    )


def test_a_missing_version_is_recorded_as_unknown(tmp_path):
    runtime = FakePacketTracerProbeRuntime(
        {"2911": _observation()}, packet_tracer_version=None,
    )

    snapshot, _ = _service(tmp_path, runtime).run(ProbeRequest(models=["2911"]))

    assert snapshot.backend_version_provenance is BackendVersionProvenance.UNKNOWN


def test_evidence_with_an_unknown_version_is_not_reused_across_sessions(tmp_path):
    """El caso que motiva el gate: sin versión, sin reuso entre sesiones."""
    runtime = FakePacketTracerProbeRuntime(
        {"2911": _observation()}, packet_tracer_version=None,
    )
    service = _service(tmp_path, runtime)

    _, first_cached = service.run(ProbeRequest(models=["2911"]))
    _, second_cached = service.run(ProbeRequest(models=["2911"]))

    assert not first_cached
    assert not second_cached
    assert runtime.create_device_calls == 2


def test_evidence_with_a_declared_version_is_still_reusable(tmp_path):
    """El gate es estrecho: una versión nombrada conserva el caché."""
    runtime = FakePacketTracerProbeRuntime(
        {"2911": _observation()}, packet_tracer_version="9.0.1.0858",
    )
    service = _service(tmp_path, runtime)

    _, first_cached = service.run(ProbeRequest(models=["2911"]))
    _, second_cached = service.run(ProbeRequest(models=["2911"]))

    assert not first_cached
    assert second_cached
    assert runtime.create_device_calls == 1


def test_the_store_refuses_an_unknown_version_snapshot_directly(tmp_path):
    """Mismo gate en el store, sin pasar por el servicio."""
    runtime = FakePacketTracerProbeRuntime(
        {"2911": _observation()}, packet_tracer_version=None,
    )
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    snapshot, _ = CapabilityDiscoveryService(
        runtime, store, EnterpriseCapabilityAdapter().identity_for,
    ).run(ProbeRequest(models=["2911"]))

    assert store.find_cached(
        None, ["2911"], ["model_exists"], PROBE_SCHEMA_VERSION,
        environment_fingerprint=snapshot.environment_fingerprint,
        initial_inventory_hash=snapshot.initial_inventory_hash,
    ) is None
