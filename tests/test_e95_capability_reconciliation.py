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

import pathlib

import pytest

from src.packet_tracer_mcp.infrastructure.catalog.capability_providers import (
    ProbeCapabilityProvider,
    RuntimeCapabilityProvider,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
    packet_tracer_enterprise_capability_adapter,
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


def _probe_result(
    model: str,
    capability: str,
    *,
    status: CapabilityStatus,
    verified: bool,
) -> CapabilityProbeResult:
    """Un resultado de probe con estado y verificacion controlados."""
    return CapabilityProbeResult(
        probe_id=f"{capability}-probe",
        model=model,
        capability=capability,
        status=status,
        execution_status=(
            ProbeExecutionStatus.VERIFIED if verified
            else ProbeExecutionStatus.VERIFY_FAILED
        ),
        evidence_source=EvidenceSource.CONTROLLED_PROBE,
        configured=True,
        verified=verified,
        packet_tracer_version=MEASURED_VERSION,
        verification_method=CapabilityVerificationMethod.SIMULATION_TRACE,
    )


def _store_with(tmp_path_factory, name: str, results) -> CapabilitySnapshotStore:
    store = CapabilitySnapshotStore(tmp_path_factory.mktemp(name))
    store.save_runtime(CapabilitySnapshot(
        packet_tracer_version=MEASURED_VERSION,
        session=ProbeSessionResult(
            session=ProbeSession(
                session_id=f"hermetic-{name}",
                packet_tracer_version=MEASURED_VERSION,
            ),
            results=list(results),
        ),
    ))
    return store


@pytest.fixture(scope="module")
def store_unverified(tmp_path_factory) -> CapabilitySnapshotStore:
    """Multilayer SUPPORTED pero NO verificado: no puede implicar layer3."""
    return _store_with(tmp_path_factory, "unverified", [
        _probe_result(
            "3650-24PS", "multilayer_intervlan",
            status=CapabilityStatus.SUPPORTED, verified=False,
        ),
    ])


@pytest.fixture(scope="module")
def store_unsupported(tmp_path_factory) -> CapabilitySnapshotStore:
    """Un hecho negativo medido: conectar providers no lo vuelve positivo."""
    return _store_with(tmp_path_factory, "unsupported", [
        _probe_result(
            "3560-24PS", "layer3",
            status=CapabilityStatus.UNSUPPORTED, verified=True,
        ),
    ])


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
    """Sustituye al viejo tripwire negativo, con afirmaciones mas fuertes.

    Antes habia un test que fallaba el dia que alguien conectara providers en
    produccion. Conectarlos dejo de ser el accidente que ese test vigilaba y
    paso a ser el objetivo de TD-HARDWARE-001, asi que restaurarlo seria
    vigilar lo contrario de lo que se quiere. Se reemplaza por lo que si debe
    cumplirse siempre: la composicion productiva conecta la evidencia, la acota
    a una version exacta, y no asciende nada que no se haya observado.
    """

    def test_product_composition_wires_exact_version_providers(self, store):
        wired = packet_tracer_enterprise_capability_adapter(
            MEASURED_VERSION, store=store,
        )

        assert _layer3(wired, "3560-24PS") is CapabilityStatus.SUPPORTED

    def test_product_composition_wires_both_evidence_providers(self):
        """Ambos providers, no uno: probe y runtime son fuentes distintas."""
        wired = packet_tracer_enterprise_capability_adapter(MEASURED_VERSION)

        kinds = {type(provider) for provider in wired._providers}

        assert kinds == {ProbeCapabilityProvider, RuntimeCapabilityProvider}

    def test_the_composition_root_demands_an_exact_version(self):
        """Sin version exacta no hay composicion: no hay default razonable."""
        for blank in ("", "   "):
            with pytest.raises(ValueError):
                packet_tracer_enterprise_capability_adapter(blank)

    def test_a_model_without_evidence_stays_unknown(self, store):
        """Conectar providers no reparte capacidades a quien no fue medido."""
        wired = packet_tracer_enterprise_capability_adapter(
            MEASURED_VERSION, store=store,
        )
        measured = {"3560-24PS", "3650-24PS"}
        others = [
            candidate
            for candidate in wired.hardware_candidates("switch", MEASURED_VERSION)
            if candidate.model not in measured
        ]

        assert others, "el catalogo debe tener switches sin evidencia"
        for candidate in others:
            assert candidate.capabilities.layer3 is CapabilityStatus.UNKNOWN, (
                candidate.model
            )

    def test_product_composition_keeps_mismatched_evidence_unknown(self, store):
        wired = packet_tracer_enterprise_capability_adapter(
            "9.0.2.0000", store=store,
        )

        assert _layer3(wired, "3560-24PS") is CapabilityStatus.UNKNOWN

    def test_evidence_is_scoped_to_the_exact_asked_version_not_the_bound_one(self, store):
        """Preguntar por otra version no reetiqueta la evidencia medida.

        El adapter esta atado a una version; si la consulta nombra otra, la
        evidencia no se traslada silenciosamente a esa otra version.
        """
        wired = packet_tracer_enterprise_capability_adapter(
            MEASURED_VERSION, store=store,
        )

        for candidate in wired.hardware_candidates("switch", "9.0.2.0000"):
            if candidate.model == "3560-24PS":
                assert candidate.capabilities.layer3 is CapabilityStatus.UNKNOWN
                return
        raise AssertionError("3560-24PS is not a switch candidate")

    def test_verified_multilayer_forwarding_implies_layer3_without_model_case(self, store):
        wired = packet_tracer_enterprise_capability_adapter(
            MEASURED_VERSION, store=store,
        )

        assert _layer3(wired, "3650-24PS") is CapabilityStatus.SUPPORTED

    def test_the_implication_requires_supported_and_verified_evidence(self, store_unverified):
        """La implicacion se apoya en evidencia verificada, no en su forma.

        Un resultado con el mismo `capability` pero sin `verified`, o cuyo
        estado no sea SUPPORTED, no puede producir `layer3`. Si pudiera, la
        implicacion seria una forma de ascender lo no observado.
        """
        wired = packet_tracer_enterprise_capability_adapter(
            MEASURED_VERSION, store=store_unverified,
        )

        assert _layer3(wired, "3650-24PS") is CapabilityStatus.UNKNOWN

    def test_provider_wiring_never_promotes_an_unsupported_capability(self, store_unsupported):
        """Un hecho negativo medido sigue siendo negativo despues de conectar."""
        wired = packet_tracer_enterprise_capability_adapter(
            MEASURED_VERSION, store=store_unsupported,
        )

        # Medido: el hecho negativo llega intacto a la seleccion. Afirmar solo
        # "no es SUPPORTED" tambien pasaria si quedara en UNKNOWN, que seria
        # perder la evidencia en vez de respetarla.
        assert _layer3(wired, "3560-24PS") is CapabilityStatus.UNSUPPORTED

    def test_no_test_fixture_or_supported_shortcut_reaches_production(self):
        """La composicion productiva no puede fabricar evidencia.

        Su unica fuente son snapshots persistidos. Ni un perfil de test ni un
        atajo tipo `.supported()` pueden entrar por aqui: con un store vacio no
        hay ninguna capacidad promovida.
        """
        source = (
            PACKAGE / "infrastructure" / "catalog" / "enterprise_capabilities.py"
        ).read_text(encoding="utf-8")
        composition = source.split(
            "def packet_tracer_enterprise_capability_adapter"
        )[1].split("\ndef ")[0]

        assert ".supported(" not in composition
        assert "fixture" not in composition.casefold()
        assert "CapabilityStatus.SUPPORTED" not in composition


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
