"""La evidencia de runtime no llega a la seleccion de hardware. Medido, no supuesto.

Stage 2D verifico en vivo SVI e inter-VLAN sobre 3560-24PS y 3650-24PS, y esos
resultados estan persistidos. Stage 3A3-D leyo `layer3 = UNKNOWN` en los
candidatos y concluyo que "el planner elige L2 correctamente porque nadie tiene
capacidad verificada". Esa explicacion era falsa: el planner nunca vio la
evidencia, porque `EnterpriseCapabilityAdapter` se construye sin providers en
todas las rutas productivas.

Estos tests fijan la frontera para que no se pueda volver a describir como una
decision informada, y para que se note el dia que se cierre.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from src.packet_tracer_mcp.infrastructure.catalog.capability_providers import (
    ProbeCapabilityProvider,
    RuntimeCapabilityProvider,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    EvidenceSource,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    CapabilityProbeResult,
    CapabilitySnapshot,
    CapabilityVerificationMethod,
    ProbeExecutionStatus,
    ProbeSession,
    ProbeSessionResult,
)
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = REPO / "src" / "packet_tracer_mcp"
MEASURED_VERSION = "9.0.1.0858"


def _verified(model: str, capability: str, probe_id: str, method) -> CapabilityProbeResult:
    return CapabilityProbeResult(
        probe_id=probe_id,
        model=model,
        capability=capability,
        status=CapabilityStatus.SUPPORTED,
        execution_status=ProbeExecutionStatus.VERIFIED,
        evidence_source=EvidenceSource.CONTROLLED_PROBE,
        configured=True,
        verified=True,
        packet_tracer_version=MEASURED_VERSION,
        verification_method=method,
    )


def _stage_2d_snapshot() -> CapabilitySnapshot:
    """La forma minima de lo que Stage 2D verifico en vivo.

    Reproduce exactamente los cuatro hechos de los que dependen estos tests:
    3560-24PS tiene layer3 e inter-VLAN multilayer verificados, y 3650-24PS
    tiene el multilayer verificado pero ningun layer3 -- que es justamente la
    asimetria que hace visible la deuda de reconciliacion.
    """
    return CapabilitySnapshot(
        packet_tracer_version=MEASURED_VERSION,
        session=ProbeSessionResult(
            session=ProbeSession(
                session_id="stage-2d-hermetic-fixture",
                packet_tracer_version=MEASURED_VERSION,
            ),
            results=[
                _verified(
                    "3560-24PS", "layer3", "layer3-probe",
                    CapabilityVerificationMethod.CLI_PLUS_READBACK,
                ),
                _verified(
                    "3560-24PS", "multilayer_intervlan", "multilayer-intervlan-probe",
                    CapabilityVerificationMethod.SIMULATION_TRACE,
                ),
                _verified(
                    "3650-24PS", "multilayer_intervlan", "multilayer-intervlan-probe",
                    CapabilityVerificationMethod.SIMULATION_TRACE,
                ),
            ],
        ),
    )


@pytest.fixture(scope="module")
def store(tmp_path_factory) -> CapabilitySnapshotStore:
    """Store efimero con exactamente la evidencia que estos tests necesitan.

    Antes construia `CapabilitySnapshotStore()` sin argumentos, que lee
    `data/capabilities` relativo al CWD. Ese directorio esta gitignored, asi
    que un worktree recien creado hacia fallar dos tests hasta que alguien
    copiaba snapshots a mano desde otro checkout. Los snapshots son estado
    runtime mutable, no fixtures: en vez de versionarlos, se reconstruye la
    forma minima y el resultado deja de depender de la maquina.
    """
    store = CapabilitySnapshotStore(tmp_path_factory.mktemp("capabilities"))
    store.save_runtime(_stage_2d_snapshot())
    return store


def _layer3(adapter: EnterpriseCapabilityAdapter, model: str):
    for candidate in adapter.hardware_candidates("switch", MEASURED_VERSION):
        if candidate.model == model:
            return candidate.capabilities.layer3
    raise AssertionError(f"{model} is not a switch candidate")


class TestTheEvidenceExistsAndIsReachable:
    def test_stage_2d_multilayer_evidence_is_persisted(self, store):
        """Round-trip de la evidencia: guardada, releida y filtrable.

        Antes esto afirmaba algo sobre la maquina -- que el `data/capabilities`
        de este disco tuviera la corrida real de Stage 2D. Eso no era una
        propiedad del codigo y no sobrevivia a un checkout limpio. Lo que si es
        del codigo, y lo que aqui se prueba, es que un snapshot con esa forma
        se persiste y vuelve a salir por `list_runtime`.
        """
        verified = {
            (result.model, result.capability)
            for snapshot in store.list_runtime(None)
            for result in snapshot.session.results
            if result.verified and result.model in {"3560-24PS", "3650-24PS"}
        }

        assert any(capability == "multilayer_intervlan" for _, capability in verified), (
            f"Stage 2D multilayer evidence is missing from the store: {sorted(verified)}"
        )

    def test_the_enrichment_seam_works_when_it_is_wired(self, store):
        """No esta roto: esta desconectado. La distincion importa."""
        wired = EnterpriseCapabilityAdapter(providers=[
            ProbeCapabilityProvider(store, MEASURED_VERSION),
            RuntimeCapabilityProvider(store, MEASURED_VERSION),
        ])

        assert _layer3(wired, "3560-24PS").value == "supported"

    def test_the_default_construction_sees_none_of_it(self, store):
        assert _layer3(EnterpriseCapabilityAdapter(), "3560-24PS").value == "unknown"


class TestTheBoundaryIsExactAndVisible:
    def test_no_production_site_wires_the_providers(self):
        """El dia que alguien los conecte, este test cae y hay que revisarlo."""
        wired = []
        for path in sorted(PACKAGE.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                target = node.func
                name = getattr(target, "id", "") or getattr(target, "attr", "")
                if name != "EnterpriseCapabilityAdapter":
                    continue
                if any(keyword.arg == "providers" for keyword in node.keywords):
                    wired.append(path.relative_to(REPO).as_posix())

        assert wired == [], (
            "Runtime capability providers are now wired in production; "
            f"CAPABILITY_TO_HARDWARE_RECONCILIATION must be re-evaluated: {wired}"
        )

    def test_even_wired_the_3650_evidence_does_not_map_to_a_field(self, store):
        """La segunda mitad de la deuda: `multilayer_intervlan` no tiene destino.

        Conectar los providers no basta; la capacidad probada tampoco alimenta
        ningun campo que el selector lea para ese modelo.
        """
        wired = EnterpriseCapabilityAdapter(providers=[
            ProbeCapabilityProvider(store, MEASURED_VERSION),
            RuntimeCapabilityProvider(store, MEASURED_VERSION),
        ])

        assert _layer3(wired, "3650-24PS").value == "unknown"


class TestTheRegressionReferenceDoesNotDependOnSelection:
    """Por eso la deuda no bloquea 3A4: la referencia fija sus candidatos."""

    def test_the_reference_pins_its_hardware_by_hand(self):
        source = (REPO / "tests" / "test_e95_reference_regression.py").read_text(
            encoding="utf-8",
        )

        assert 'item.model == "2960-24TT"' in source
        assert 'item.model == "2911"' in source

    def test_the_reference_hardware_is_what_the_fixture_pinned(self):
        from tests.test_e95_reference_regression import _compile_reference_chain

        models = {device.model for device in _compile_reference_chain().e4.plan.devices}

        assert {"2960-24TT", "2911"} <= models
        assert "3560-24PS" not in models
        assert "3650-24PS" not in models
