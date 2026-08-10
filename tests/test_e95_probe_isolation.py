"""E9.5 probe isolation, provenance fingerprints and cleanup confidence gates."""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.capability_discovery import (
    CapabilityDiscoveryService,
    CapabilityProbeRegistry,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    EvidenceSource,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    CapabilityBackend,
    CapabilityProbeResult,
    CleanupStatus,
    ProbeCost,
    ProbeDefinition,
    ProbeEnvironment,
    ProbeExecutionStatus,
    ProbeContext,
    ProbeIsolationLevel,
    ProbeRequest,
    ProbeSafety,
    RuntimeDeviceObservation,
    RuntimePortDescriptor,
    semantic_inventory_fingerprint,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from src.packet_tracer_mcp.infrastructure.execution.fake_probe_runtime import (
    FakePacketTracerProbeRuntime,
)
from src.packet_tracer_mcp.infrastructure.execution.probe_runtime import (
    PacketTracerBridgeProbeRuntime,
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


def _service(tmp_path, runtime, registry: CapabilityProbeRegistry | None = None):
    return CapabilityDiscoveryService(
        runtime,
        CapabilitySnapshotStore(tmp_path / "capabilities"),
        EnterpriseCapabilityAdapter().identity_for,
        registry,
    )


class _ResetRegistry(CapabilityProbeRegistry):
    _definitions = {
        "model_exists": ProbeDefinition(
            id="model-exists",
            capability="model_exists",
            isolation_level=ProbeIsolationLevel.SHARED_DEVICE,
        ),
        "reset_test": ProbeDefinition(
            id="reset-test",
            probe_version="7",
            capability="reset_test",
            prerequisites=["model_exists"],
            safety=ProbeSafety.MUTATING,
            isolation_level=ProbeIsolationLevel.RESET_REQUIRED,
            cost=ProbeCost.NORMAL,
        ),
    }


class _VersionedRegistry(CapabilityProbeRegistry):
    def __init__(self, version: str) -> None:
        self._definitions = {
            "model_exists": ProbeDefinition(
                id="model-exists",
                probe_version=version,
                capability="model_exists",
                isolation_level=ProbeIsolationLevel.SHARED_DEVICE,
            ),
        }


def test_legacy_isolation_flags_map_to_explicit_effective_levels():
    fresh = ProbeDefinition(
        id="legacy-fresh", capability="x", requires_fresh_device=True,
    )
    reset = ProbeDefinition(
        id="legacy-reset", capability="x", requires_power_cycle=True,
    )

    assert fresh.effective_isolation_level is ProbeIsolationLevel.FRESH_DEVICE_REQUIRED
    assert reset.effective_isolation_level is ProbeIsolationLevel.RESET_REQUIRED
    assert all(
        definition.isolation_level is not None
        for definition in CapabilityProbeRegistry()._definitions.values()
    )


def test_fresh_device_probe_records_reusable_context_and_restores_inventory(tmp_path):
    result = CapabilityProbeResult(
        probe_id="layer3-probe",
        model="2911",
        capability="layer3",
        status=CapabilityStatus.SUPPORTED,
        execution_status=ProbeExecutionStatus.VERIFIED,
        evidence_source=EvidenceSource.CONTROLLED_PROBE,
        configured=True,
        verified=True,
    )
    runtime = FakePacketTracerProbeRuntime(
        {"2911": _observation()},
        {("2911", "layer3"): result},
    )

    snapshot, _ = _service(tmp_path, runtime).run(ProbeRequest(
        models=["2911"], capabilities=["layer3"], force=True,
    ))

    observed = next(item for item in snapshot.session.results if item.capability == "layer3")
    assert runtime.create_device_calls == 2
    assert observed.context is not None
    assert observed.context.isolation_level is ProbeIsolationLevel.FRESH_DEVICE_REQUIRED
    assert observed.context.inventory_restored is True
    assert observed.context.cleanup_status is CleanupStatus.CLEAN
    assert observed.context.probe_fingerprint
    assert observed.evidence() is not None


def test_reset_required_probe_resets_shared_device_before_execution(tmp_path):
    runtime = FakePacketTracerProbeRuntime(
        {"2911": _observation()},
        {("2911", "reset_test"): CapabilityProbeResult(
            probe_id="reset-test",
            model="2911",
            capability="reset_test",
            status=CapabilityStatus.SUPPORTED,
            execution_status=ProbeExecutionStatus.VERIFIED,
            evidence_source=EvidenceSource.CONTROLLED_PROBE,
            verified=True,
        )},
    )

    snapshot, _ = _service(tmp_path, runtime, _ResetRegistry()).run(ProbeRequest(
        models=["2911"], capabilities=["reset_test"], force=True,
    ))

    result = next(item for item in snapshot.session.results if item.capability == "reset_test")
    assert runtime.power_cycle_calls == 1
    assert result.status is CapabilityStatus.SUPPORTED
    assert result.context is not None
    assert result.context.isolation_level is ProbeIsolationLevel.RESET_REQUIRED


def test_cleanup_failure_downgrades_results_and_prevents_cache_reuse(tmp_path):
    runtime = FakePacketTracerProbeRuntime(
        {"2911": _observation()}, cleanup_failures={"*"},
    )
    service = _service(tmp_path, runtime)

    first, cached = service.run(ProbeRequest(models=["2911"]))
    _, cached_again = service.run(ProbeRequest(models=["2911"]))

    assert not cached
    assert not cached_again
    assert runtime.create_device_calls == 2
    assert first.session.session.cleanup_status is CleanupStatus.DIRTY_SESSION
    assert all(item.status is CapabilityStatus.UNKNOWN for item in first.session.results)
    assert all(item.evidence() is None for item in first.session.results)
    assert all(
        item.context is not None and not item.context.reusable
        for item in first.session.results
    )


def test_mutating_probe_without_inventory_restoration_proof_is_not_reusable():
    context = ProbeContext(
        probe_id="mutating-probe",
        device_model="2911",
        mutations=["temporary-device:2911"],
        cleanup_status=CleanupStatus.CLEAN,
        inventory_restored=None,
    )

    assert not context.reusable


def test_inventory_drift_is_a_hard_confidence_gate(tmp_path):
    runtime = FakePacketTracerProbeRuntime({"2911": _observation()})
    fingerprints = iter(("inventory-before", "inventory-after"))
    runtime.inventory_fingerprint = lambda: next(fingerprints)

    snapshot, _ = _service(tmp_path, runtime).run(ProbeRequest(
        models=["2911"], force=True,
    ))

    assert snapshot.inventory_restored is False
    assert snapshot.session.session.cleanup_status is CleanupStatus.DIRTY_SESSION
    assert all(item.status is CapabilityStatus.UNKNOWN for item in snapshot.session.results)
    assert all(item.evidence() is None for item in snapshot.session.results)


def test_create_timeout_still_cleans_the_controlled_candidate_name(tmp_path):
    class TimeoutAfterMutationRuntime(FakePacketTracerProbeRuntime):
        def create_temporary_device(self, runtime_model, temporary_name):
            self.create_device_calls += 1
            self._models_by_name[temporary_name] = runtime_model
            raise TimeoutError("response lost after mutation")

    runtime = TimeoutAfterMutationRuntime({"2911": _observation()})

    snapshot, _ = _service(tmp_path, runtime).run(ProbeRequest(
        models=["2911"], force=True,
    ))

    assert runtime.delete_device_calls == 1
    assert runtime._models_by_name == {}
    assert snapshot.inventory_restored is True
    assert snapshot.session.session.cleanup_status is CleanupStatus.CLEAN
    assert snapshot.session.cleanup_failed == []


def test_cleanup_waits_for_bounded_inventory_convergence_before_marking_dirty(tmp_path):
    class DelayedCleanupRuntime(FakePacketTracerProbeRuntime):
        def __init__(self):
            super().__init__({"2911": _observation()})
            self.wait_requests = []

        def wait_for_inventory_fingerprint(self, expected, timeout_seconds):
            self.wait_requests.append((expected, timeout_seconds))
            return expected

    runtime = DelayedCleanupRuntime()
    snapshot, _ = _service(tmp_path, runtime).run(ProbeRequest(
        models=["2911"], force=True,
    ))

    assert runtime.wait_requests == [(snapshot.initial_inventory_hash, 5.0)]
    assert snapshot.inventory_restored is True
    assert snapshot.session.session.cleanup_status is CleanupStatus.CLEAN


def test_cache_invalidates_on_environment_or_probe_version_change(tmp_path):
    runtime = FakePacketTracerProbeRuntime(
        {"2911": _observation()}, transport_channel="http",
    )
    store_path = tmp_path / "capabilities"
    first_service = CapabilityDiscoveryService(
        runtime, CapabilitySnapshotStore(store_path),
        EnterpriseCapabilityAdapter().identity_for,
        _VersionedRegistry("1"),
    )
    first_service.run(ProbeRequest(models=["2911"]))
    _, cached = first_service.run(ProbeRequest(models=["2911"]))
    assert cached

    runtime.transport_channel = "file"
    _, cached = first_service.run(ProbeRequest(models=["2911"]))
    assert not cached

    second_service = CapabilityDiscoveryService(
        runtime, CapabilitySnapshotStore(store_path),
        EnterpriseCapabilityAdapter().identity_for,
        _VersionedRegistry("2"),
    )
    _, cached = second_service.run(ProbeRequest(models=["2911"]))
    assert not cached
    assert runtime.create_device_calls == 3


def test_semantic_fingerprints_are_order_stable_and_exclude_session_data():
    environment_a = ProbeEnvironment(
        backend=CapabilityBackend.PACKET_TRACER,
        backend_version="9.0.1",
        transport_channel="http",
        extension_version="5",
    )
    environment_b = ProbeEnvironment.model_validate({
        "extension_version": "5",
        "transport_channel": "http",
        "backend_version": "9.0.1",
        "backend": "packet_tracer",
    })
    definition = ProbeDefinition(
        id="probe", probe_version="3", capability="layer3",
        isolation_level=ProbeIsolationLevel.FRESH_DEVICE_REQUIRED,
    )

    assert environment_a.semantic_fingerprint() == environment_b.semantic_fingerprint()
    assert definition.semantic_fingerprint("2911", {"b": 2, "a": 1}) == definition.semantic_fingerprint(
        "2911", {"a": 1, "b": 2},
    )
    assert semantic_inventory_fingerprint([
        {"name": "B", "model": "2960", "ports": ["Fa0/2", "Fa0/1"]},
        {"name": "A", "model": "2911"},
    ]) == semantic_inventory_fingerprint([
        {"model": "2911", "name": "A"},
        {"ports": ["Fa0/1", "Fa0/2"], "model": "2960", "name": "B"},
    ])


def test_snapshot_semantic_hash_is_stable_across_random_probe_sessions(tmp_path):
    runtime = FakePacketTracerProbeRuntime({"2911": _observation()})
    service = _service(tmp_path, runtime)

    first, _ = service.run(ProbeRequest(models=["2911"], force=True))
    second, _ = service.run(ProbeRequest(models=["2911"], force=True))

    assert first.session.session.session_id != second.session.session.session_id
    assert first.stable_hash() == second.stable_hash()


def test_live_inventory_fingerprint_uses_structured_device_and_link_readback():
    sent: list[str] = []

    def send_and_wait(js: str, _timeout: float) -> str:
        sent.append(js)
        return (
            '{"items":[{"kind":"device","name":"R1","model":"2911",'
            '"ports":["GigabitEthernet0/1","GigabitEthernet0/0"]}],'
            '"links":[{"kind":"link","a_device":"R1","a_port":"GigabitEthernet0/0",'
            '"b_device":"SW1","b_port":"GigabitEthernet0/1"}]}'
        )

    runtime = PacketTracerBridgeProbeRuntime(send_and_wait)

    assert runtime.inventory_fingerprint() == semantic_inventory_fingerprint([
        {
            "kind": "link", "a_device": "R1", "a_port": "GigabitEthernet0/0",
            "b_device": "SW1", "b_port": "GigabitEthernet0/1",
        },
        {
            "kind": "device", "name": "R1", "model": "2911",
            "ports": ["GigabitEthernet0/0", "GigabitEthernet0/1"],
        },
    ])
    assert "getDeviceCount" in sent[0]
    assert "getLinkAt" in sent[0]
