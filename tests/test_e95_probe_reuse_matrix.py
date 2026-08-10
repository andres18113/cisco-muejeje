"""Matriz de reuso de sesión E9.5: mutación x restauración x cleanup.

`inventory_restored` es un `bool | None` almacenado. El `None` significaba dos
cosas incompatibles -- "no había nada que restaurar" y "no se pudo medir" -- y
sólo la segunda debe bloquear el reuso. Estos tests fijan las dos lecturas por
separado y comprueban que UNKNOWN nunca se comporta como CLEAN.
"""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    CleanupStatus,
    InventoryRestoration,
    ProbeContext,
    classify_inventory_restoration,
)
from src.packet_tracer_mcp.infrastructure.execution.fake_probe_runtime import (
    FakePacketTracerProbeRuntime,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    ProbeRequest,
    RuntimeDeviceObservation,
    RuntimePortDescriptor,
)
from src.packet_tracer_mcp.application.use_cases.capability_discovery import (
    CapabilityDiscoveryService,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
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


def _context(**overrides) -> ProbeContext:
    base = {
        "probe_id": "matrix-probe",
        "device_model": "2911",
        "cleanup_status": CleanupStatus.CLEAN,
    }
    base.update(overrides)
    return ProbeContext(**base)


class TestRestorationClassification:
    """El booleano almacenado se traduce a una clasificación explícita."""

    def test_no_mutation_and_unmeasured_inventory_is_not_applicable(self):
        assert classify_inventory_restoration(None, mutated=False) is (
            InventoryRestoration.NOT_APPLICABLE
        )

    def test_mutation_and_unmeasured_inventory_is_unknown(self):
        assert classify_inventory_restoration(None, mutated=True) is (
            InventoryRestoration.UNKNOWN
        )

    def test_measured_values_are_independent_of_mutation(self):
        for mutated in (True, False):
            assert classify_inventory_restoration(True, mutated=mutated) is (
                InventoryRestoration.RESTORED
            )
            assert classify_inventory_restoration(False, mutated=mutated) is (
                InventoryRestoration.NOT_RESTORED
            )

    def test_unknown_is_never_reported_as_not_applicable(self):
        """La distinción es el punto: un None mutado no puede leerse benigno."""
        mutated = classify_inventory_restoration(None, mutated=True)
        clean = classify_inventory_restoration(None, mutated=False)
        assert mutated is not clean


class TestSessionReuseMatrix:
    """Los siete casos de la matriz, sobre el contrato de `reusable`."""

    def test_case_1_read_only_probe_with_restoration_not_applicable_reuses(self):
        context = _context(mutations=[], inventory_restored=None)

        assert context.restoration is InventoryRestoration.NOT_APPLICABLE
        assert context.reusable

    def test_case_2_mutating_probe_with_proven_restoration_reuses(self):
        context = _context(
            mutations=["temporary-device:2911"], inventory_restored=True,
        )

        assert context.restoration is InventoryRestoration.RESTORED
        assert context.reusable

    def test_case_3_mutating_probe_with_failed_restoration_is_blocked(self):
        context = _context(
            mutations=["temporary-device:2911"], inventory_restored=False,
        )

        assert context.restoration is InventoryRestoration.NOT_RESTORED
        assert not context.reusable

    def test_case_4_mutating_probe_with_unknown_restoration_is_blocked(self):
        context = _context(
            mutations=["temporary-device:2911"], inventory_restored=None,
        )

        assert context.restoration is InventoryRestoration.UNKNOWN
        assert not context.reusable

    def test_case_5_possible_mutation_without_measurable_inventory_is_blocked(
        self, tmp_path,
    ):
        """Timeout tras despachar la creación y sin huella de inventario.

        El intento se registra antes del dispatch, así que la sesión sabe que
        pudo haber mutado aunque la respuesta se perdiera.
        """

        class TimeoutWithoutFingerprint(FakePacketTracerProbeRuntime):
            def create_temporary_device(self, runtime_model, temporary_name):
                self.create_device_calls += 1
                self._models_by_name[temporary_name] = runtime_model
                raise TimeoutError("response lost after a possible mutation")

            def inventory_fingerprint(self):
                return ""

        runtime = TimeoutWithoutFingerprint({"2911": _observation()})

        snapshot, _ = _service(tmp_path, runtime).run(
            ProbeRequest(models=["2911"], force=True),
        )

        assert snapshot.session.session.mutations
        assert snapshot.inventory_restored is None
        assert snapshot.restoration is InventoryRestoration.UNKNOWN
        assert not snapshot.reusable

    def test_case_6_async_cleanup_converging_in_time_is_restored(self, tmp_path):
        class DelayedButConverging(FakePacketTracerProbeRuntime):
            def __init__(self):
                super().__init__({"2911": _observation()})
                self.waits = []

            def wait_for_inventory_fingerprint(self, expected, timeout_seconds):
                self.waits.append((expected, timeout_seconds))
                return expected

        runtime = DelayedButConverging()

        snapshot, _ = _service(tmp_path, runtime).run(
            ProbeRequest(models=["2911"], force=True),
        )

        assert runtime.waits == [(snapshot.initial_inventory_hash, 5.0)]
        assert snapshot.restoration is InventoryRestoration.RESTORED
        assert snapshot.reusable

    def test_case_7_cleanup_that_never_converges_produces_no_clean_state(
        self, tmp_path,
    ):
        """La espera acotada expira: el resultado es sucio, no limpio."""

        class NeverConverging(FakePacketTracerProbeRuntime):
            def wait_for_inventory_fingerprint(self, expected, timeout_seconds):
                return "inventory-still-drifted"

        runtime = NeverConverging({"2911": _observation()})

        snapshot, _ = _service(tmp_path, runtime).run(
            ProbeRequest(models=["2911"], force=True),
        )

        assert snapshot.restoration is InventoryRestoration.NOT_RESTORED
        assert snapshot.session.session.cleanup_status is CleanupStatus.DIRTY_SESSION
        assert not snapshot.reusable

    def test_dirty_cleanup_blocks_reuse_even_with_restored_inventory(self):
        """Cleanup sucio y restauración probada no se compensan entre sí."""
        context = _context(
            mutations=["temporary-device:2911"],
            inventory_restored=True,
            cleanup_status=CleanupStatus.DIRTY_SESSION,
        )

        assert context.restoration is InventoryRestoration.RESTORED
        assert not context.reusable
