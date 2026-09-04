"""Stage 3A4 — the exact-version capability evidence path reaches E5.

TD-CONFIG-CAPABILITY-001. The composition root
`packet_tracer_enterprise_capability_adapter` already existed and already fed
hardware selection; what did not exist was any route from it to the E5
compiler and the E5 applicator, so every configuration action resolved UNKNOWN
no matter what had been measured.

One adapter, one resolution, two consumers. The composition publishes the map
it compiled with, and the executor applies with that same map -- resolving
twice would let compile and apply disagree about what the build supports.

Everything here is hermetic: dynamic-provider tests build stores in temporary
directories and absence tests inject a provider-free catalogue.  Neither reads
`data/capabilities`, which is gitignored machine state.
"""

from __future__ import annotations

import importlib
import pathlib

import pytest

from src.packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from src.packet_tracer_mcp.application.use_cases.execute_enterprise_reference import (
    EnterpriseExecutionStage,
    EnterpriseExecutionStatus,
    EnterpriseRuntimes,
    execute_enterprise_reference,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    EvidenceSource,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ControlPlaneIntent,
    DynamicRoutingIntent,
    DynamicRoutingProtocol,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    CapabilityProbeResult,
    CapabilitySnapshot,
    CapabilityVerificationMethod,
    ProbeExecutionStatus,
    ProbeSession,
    ProbeSessionResult,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ConfigurationFailureCode,
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.services.hardware_planner import (
    HardwarePlanningPolicy,
)
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)
from src.packet_tracer_mcp.infrastructure.catalog.capability_providers import (
    ProbeCapabilityProvider,
    RuntimeCapabilityProvider,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)

from test_stage3a4_offline_adversarial_matrix import (
    FINGERPRINT,
    _bounded_intent,
    _control_plane_intent,
    _ForbiddenControlPlaneRuntime,
    _GenericOrientationRuntime,
    _GenericPhysicalRuntime,
    _QUALIFIED,
)
from test_enterprise_reference_execution import _isolated_preflight

MEASURED_VERSION = "9.0.1.0858"

#: Exactamente lo que el plan acotado de MEG-4 exige, y nada mas.
BOUNDED_REQUIREMENTS = (("IE-2000", "supports_vlan"), ("2911", "layer3"))
_INJECT_PROVIDER_FREE_CATALOG = object()


def _probe(model: str, capability: str, *, version: str = MEASURED_VERSION):
    return CapabilityProbeResult(
        probe_id=f"{capability}-probe",
        model=model,
        capability=capability,
        status=CapabilityStatus.SUPPORTED,
        execution_status=ProbeExecutionStatus.VERIFIED,
        evidence_source=EvidenceSource.CONTROLLED_PROBE,
        configured=True,
        verified=True,
        packet_tracer_version=version,
        verification_method=CapabilityVerificationMethod.CLI_PLUS_READBACK,
    )


def _store(tmp_path, name: str, results, *, version: str = MEASURED_VERSION):
    store = CapabilitySnapshotStore(tmp_path / name)
    store.save_runtime(CapabilitySnapshot(
        packet_tracer_version=version,
        session=ProbeSessionResult(
            session=ProbeSession(session_id=f"hermetic-{name}", packet_tracer_version=version),
            results=list(results),
        ),
    ))
    return store


def bounded_composition_inputs():
    """El intent acotado y su intent de plano de control, compuestos aparte."""
    intent = _bounded_intent()
    topology = compose_enterprise_reference(
        intent, policy=_QUALIFIED, packet_tracer_version=MEASURED_VERSION,
    ).topology
    return intent, topology, _control_plane_intent(topology)


def _dynamic_catalog(store: CapabilitySnapshotStore) -> EnterpriseCapabilityAdapter:
    return EnterpriseCapabilityAdapter(
        providers=[
            ProbeCapabilityProvider(store, MEASURED_VERSION),
            RuntimeCapabilityProvider(store, MEASURED_VERSION),
        ],
        bound_packet_tracer_version=MEASURED_VERSION,
    )


def _compose(store=None, *, capability_catalog=None):
    intent, _topology, _cp = bounded_composition_inputs()
    return compose_enterprise_reference(
        intent,
        policy=_QUALIFIED,
        packet_tracer_version=MEASURED_VERSION,
        capability_store=store,
        capability_catalog=capability_catalog,
    )


@pytest.fixture
def measured_store(tmp_path):
    return _store(tmp_path, "measured", [
        _probe(model, capability) for model, capability in BOUNDED_REQUIREMENTS
    ])


@pytest.fixture
def empty_store(tmp_path):
    """No dynamic evidence. Portable governed evidence is a separate source."""
    return CapabilitySnapshotStore(tmp_path / "empty")


def composed_with_store():
    """Helper compartido con `test_e95_e5_capability_authorization`."""
    import tempfile
    import pathlib

    directory = pathlib.Path(tempfile.mkdtemp())
    store = _store(directory, "measured", [
        _probe(model, capability) for model, capability in BOUNDED_REQUIREMENTS
    ])
    return _compose(store, capability_catalog=_dynamic_catalog(store)), store


# --------------------------------------------------------------------------
# the map the composition publishes
# --------------------------------------------------------------------------


def test_measured_evidence_reaches_the_e5_capability_map(measured_store):
    composed = _compose(
        measured_store, capability_catalog=_dynamic_catalog(measured_store),
    )

    assert composed.capabilities["IE-2000"].supports_vlan is CapabilityStatus.SUPPORTED
    assert composed.capabilities["2911"].layer3 is CapabilityStatus.SUPPORTED


def test_a_provider_free_catalogue_authorizes_nothing(empty_store):
    """Declaracion estatica de catalogo != evidencia de capacidad runtime."""
    composed = _compose(
        empty_store, capability_catalog=EnterpriseCapabilityAdapter(),
    )

    for model, capability in BOUNDED_REQUIREMENTS:
        assert getattr(composed.capabilities[model], capability) is CapabilityStatus.UNKNOWN
    assert composed.capabilities["IE-2000"].source == "packet_tracer_catalog"


def test_the_default_mutable_store_is_machine_state_and_tests_must_inject_it():
    """`CapabilitySnapshotStore()` lee `data/capabilities` relativo al CWD.

    Ese directorio esta gitignored: es estado de la maquina, no del repositorio.
    El baseline gobernado es Git-tracked, pero los providers de mayor prioridad
    tambien leen este directorio. Un test de evidencia dinamica o de ausencia
    debe inyectar su store para no depender de lo que haya en el disco.
    """
    assert CapabilitySnapshotStore().base_dir == pathlib.Path("data") / "capabilities"


def test_evidence_from_another_build_is_not_reused(tmp_path):
    store = _store(tmp_path, "other-build", [
        _probe(model, capability, version="9.0.2.0000")
        for model, capability in BOUNDED_REQUIREMENTS
    ], version="9.0.2.0000")

    composed = _compose(store, capability_catalog=_dynamic_catalog(store))

    for model, capability in BOUNDED_REQUIREMENTS:
        assert getattr(composed.capabilities[model], capability) is CapabilityStatus.UNKNOWN


def test_evidence_for_another_model_is_not_reused(tmp_path):
    store = _store(tmp_path, "other-model", [
        _probe("2960-24TT", "supports_vlan"),
        _probe("1941", "layer3"),
    ])

    composed = _compose(store, capability_catalog=_dynamic_catalog(store))

    assert composed.capabilities["IE-2000"].supports_vlan is CapabilityStatus.UNKNOWN
    assert composed.capabilities["2911"].layer3 is CapabilityStatus.UNKNOWN


def test_the_capability_map_is_deterministic(measured_store):
    catalog = _dynamic_catalog(measured_store)
    first = _compose(measured_store, capability_catalog=catalog).capabilities
    second = _compose(measured_store, capability_catalog=catalog).capabilities

    assert list(first) == list(second) == sorted(first)
    assert {k: v.model_dump(mode="json") for k, v in first.items()} == {
        k: v.model_dump(mode="json") for k, v in second.items()
    }


def test_the_map_covers_every_deployed_model_and_never_omits_one(measured_store):
    """Un modelo ausente del mapa resolveria UNKNOWN, pero por accidente."""
    composed = _compose(
        measured_store, capability_catalog=_dynamic_catalog(measured_store),
    )

    assert set(composed.capabilities) == {
        device.model for device in composed.topology.devices
    }


# --------------------------------------------------------------------------
# what an E5 capability refusal may not touch
# --------------------------------------------------------------------------


def _run(
    *, store, physical=None, capability_catalog=_INJECT_PROVIDER_FREE_CATALOG,
):
    intent = _bounded_intent()
    execution_catalog = (
        EnterpriseCapabilityAdapter()
        if capability_catalog is _INJECT_PROVIDER_FREE_CATALOG
        else capability_catalog
    )
    planning_catalog = execution_catalog or EnterpriseCapabilityAdapter()
    topology = compose_enterprise_reference(
        intent,
        policy=_QUALIFIED,
        packet_tracer_version=MEASURED_VERSION,
        capability_catalog=planning_catalog,
    ).topology
    physical = physical or _GenericPhysicalRuntime()
    physical.bind(topology)
    result = execute_enterprise_reference(
        intent,
        EnterpriseRuntimes(
            physical=physical,
            serial_orientation=_GenericOrientationRuntime(),
            configuration=_ForbiddenMutationConfigurationRuntime(topology),
            control_plane=_ForbiddenControlPlaneRuntime(),
        ),
        _control_plane_intent(topology),
        environment_fingerprint=FINGERPRINT,
        import_preflight=_isolated_preflight(),
        packet_tracer_version=MEASURED_VERSION,
        capability_store=store,
        capability_catalog=execution_catalog,
        policy=_QUALIFIED,
    )
    return result, physical


class _ForbiddenMutationConfigurationRuntime:
    """Inventario si; mutar no. Si el gate funciona, nunca se le pide mutar."""

    def __init__(self, topology) -> None:
        self.inventory_calls = 0
        ports: dict[str, set[str]] = {device.id: set() for device in topology.devices}
        for link in topology.links:
            ports[link.device_a_id].add(link.port_a)
            ports[link.device_b_id].add(link.port_b)
        self._inventory = [
            RuntimeConfigurationTarget(
                device_name=device.name,
                model=device.model,
                interfaces=sorted(ports[device.id]),
                runtime_identifier=f"runtime-{device.id}",
                runtime_identifier_stable=True,
                runtime_fingerprint=f"fp-{device.id}",
            )
            for device in topology.devices
        ]

    def inventory(self):
        self.inventory_calls += 1
        return self._inventory

    def apply_actions(self, actions):
        raise AssertionError(
            "configuration.apply_actions must not be reached when a required "
            "capability is UNKNOWN",
        )

    def verify(self, expectations):
        raise AssertionError(
            "configuration.verify must not be reached when nothing was applied",
        )


def test_default_execution_materializes_one_catalog_for_both_compositions(
    empty_store, monkeypatch,
):
    """Rebuilding the default root can change evidence after deployment."""
    hardware_composition = importlib.import_module(
        "src.packet_tracer_mcp.application.use_cases.plan_enterprise_hardware",
    )
    constructions = 0
    snapshots = []

    class RecordingCatalog(EnterpriseCapabilityAdapter):
        def __init__(self):
            super().__init__()
            self.hardware_calls = 0

        def execution_snapshot(self):
            snapshot = super().execution_snapshot()
            snapshots.append(snapshot)
            return snapshot

        def hardware_candidates(self, category, packet_tracer_version=None):
            self.hardware_calls += 1
            return super().hardware_candidates(category, packet_tracer_version)

    def one_shot_catalog(_version, *, store=None):
        nonlocal constructions
        constructions += 1
        if constructions > 1:
            raise AssertionError("default capability catalog was rebuilt")
        return RecordingCatalog()

    monkeypatch.setattr(
        hardware_composition,
        "packet_tracer_enterprise_capability_adapter",
        one_shot_catalog,
    )

    result, _physical = _run(
        store=empty_store,
        capability_catalog=None,
    )

    assert result.status is EnterpriseExecutionStatus.FAILED
    assert result.stopped_at is EnterpriseExecutionStage.CONFIGURATION_APPLY
    assert result.configuration_result is not None
    assert (
        result.configuration_result.failure_code
        is ConfigurationFailureCode.CAPABILITY_UNKNOWN
    )
    assert constructions == 1
    assert len(snapshots) == 1
    assert isinstance(snapshots[0], RecordingCatalog)
    assert snapshots[0].hardware_calls > 0


def test_an_unauthorized_e5_never_reaches_e9_and_never_mutates(empty_store):
    result, _physical = _run(store=empty_store)

    assert result.status is EnterpriseExecutionStatus.FAILED
    assert result.stopped_at is EnterpriseExecutionStage.CONFIGURATION_APPLY
    assert result.control_plane_result is None
    assert result.configuration_result is not None
    assert (
        result.configuration_result.failure_code
        is ConfigurationFailureCode.CAPABILITY_UNKNOWN
    )


def test_cleanup_still_runs_after_an_e5_capability_refusal(empty_store):
    result, physical = _run(store=empty_store)

    assert result.cleanup_results
    assert result.final_inventory is not None
    assert physical.calls.count("observe_workspace") >= 2


def test_an_e5_capability_refusal_preserves_the_e4_identity(empty_store):
    result, _physical = _run(store=empty_store)

    assert result.e4_identity_preserved is True


def test_an_e5_capability_refusal_never_removes_foreign_objects(empty_store):
    result, physical = _run(store=empty_store)

    planned = {item.name for item in result.composition.topology.devices}

    assert set(physical.removed) <= planned
    assert "Power Distribution Device0" not in physical.removed
