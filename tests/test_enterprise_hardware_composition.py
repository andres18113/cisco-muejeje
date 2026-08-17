"""TD-HARDWARE-001: la evidencia de capacidad llega a la seleccion de hardware.

`test_e95_capability_reconciliation.py` fija que el seam de enriquecimiento
funciona *cuando alguien lo conecta*, y que por defecto nadie lo conecta. Lo que
faltaba era el consumidor: nada en `src/` llamaba a la raiz de composicion, y
nada en `src/` llamaba a `HardwarePlanner`. Medido con Graphify: las 47 aristas
de `HardwarePlanner` entran todas desde tests o desde su propio modulo.

Estos tests fijan al consumidor productivo y, sobre todo, fijan lo que NO puede
hacer. Conectar evidencia es facil; conectarla sin ascender nada que no se haya
observado es el punto entero de la deuda.
"""

from __future__ import annotations

import pathlib

import pytest

from src.packet_tracer_mcp.application.use_cases.plan_enterprise_hardware import (
    plan_enterprise_hardware,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from src.packet_tracer_mcp.domain.enterprise.models.hardware import HardwareCandidate
from tests.test_e95_capability_reconciliation import (
    MEASURED_VERSION,
    _probe_result,
    _store_with,
    store,  # noqa: F401  -- fixture reutilizada, no duplicada
)
from tests.test_e95_serial_product_planning import _design, _reference_planning_intent

REPO = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = REPO / "src" / "packet_tracer_mcp"

_MEASURED_LAYER3 = "3560-24PS"
_MEASURED_MULTILAYER = "3650-24PS"


@pytest.fixture(scope="module")
def enterprise():
    return _design(_reference_planning_intent())


def _candidate(composition, model: str) -> HardwareCandidate:
    for item in [*composition.switch_candidates, *composition.router_candidates]:
        if item.model == model:
            return item
    raise AssertionError(f"{model} is not among the composed candidates")


class TestTheProductionConsumerExists:
    def test_the_composition_drives_the_real_hardware_planner(self, enterprise):
        """El consumidor produce un HardwarePlan real, no un contenedor vacio."""
        composition = plan_enterprise_hardware(enterprise)

        assert composition.plan.site_hardware
        assert composition.switch_candidates and composition.router_candidates
        assert any(
            device.selected_model or device.provisional_model
            for site in composition.plan.site_hardware
            for device in site.devices
        )

    def test_the_same_inputs_produce_an_identical_plan(self, enterprise):
        first = plan_enterprise_hardware(enterprise)
        second = plan_enterprise_hardware(enterprise)

        assert first.plan.model_dump(mode="json") == second.plan.model_dump(mode="json")


class TestEvidenceReachesEligibility:
    def test_exact_version_evidence_reaches_the_candidates(self, enterprise, store):  # noqa: F811
        composition = plan_enterprise_hardware(
            enterprise,
            packet_tracer_version=MEASURED_VERSION,
            capability_store=store,
        )

        assert _candidate(composition, _MEASURED_LAYER3).capabilities.layer3 is (
            CapabilityStatus.SUPPORTED
        )

    def test_without_a_version_nothing_is_promoted(self, enterprise, store):  # noqa: F811
        """Sin version exacta no hay evidencia elegible, aunque el store la tenga."""
        composition = plan_enterprise_hardware(enterprise, capability_store=store)

        assert _candidate(composition, _MEASURED_LAYER3).capabilities.layer3 is (
            CapabilityStatus.UNKNOWN
        )


class TestWhatMustNeverBePromoted:
    def test_a_model_without_evidence_stays_unknown(self, enterprise, store):  # noqa: F811
        """Conectar providers no reparte capacidades a quien no fue medido."""
        composition = plan_enterprise_hardware(
            enterprise,
            packet_tracer_version=MEASURED_VERSION,
            capability_store=store,
        )
        measured = {_MEASURED_LAYER3, _MEASURED_MULTILAYER}
        others = [
            item for item in composition.switch_candidates if item.model not in measured
        ]

        assert others, "el catalogo debe tener switches sin evidencia"
        for item in others:
            assert item.capabilities.layer3 is CapabilityStatus.UNKNOWN, item.model

    def test_a_version_mismatch_stays_unknown(self, enterprise, store):  # noqa: F811
        composition = plan_enterprise_hardware(
            enterprise,
            packet_tracer_version="9.0.2.0000",
            capability_store=store,
        )

        assert _candidate(composition, _MEASURED_LAYER3).capabilities.layer3 is (
            CapabilityStatus.UNKNOWN
        )

    def test_evidence_is_never_redistributed_to_another_model(self, enterprise, tmp_path_factory):
        """Medir un modelo no habilita a su vecino de catalogo."""
        store = _store_with(tmp_path_factory, "one-model-only", [
            _probe_result(
                _MEASURED_LAYER3, "layer3",
                status=CapabilityStatus.SUPPORTED, verified=True,
            ),
        ])

        composition = plan_enterprise_hardware(
            enterprise,
            packet_tracer_version=MEASURED_VERSION,
            capability_store=store,
        )

        assert _candidate(composition, _MEASURED_LAYER3).capabilities.layer3 is (
            CapabilityStatus.SUPPORTED
        )
        for item in composition.switch_candidates:
            if item.model != _MEASURED_LAYER3:
                assert item.capabilities.layer3 is CapabilityStatus.UNKNOWN, item.model

    def test_a_measured_negative_survives_the_wiring(self, enterprise, tmp_path_factory):
        """Un hecho negativo medido llega intacto.

        Afirmar solo "no es SUPPORTED" tambien pasaria si quedara UNKNOWN, que
        seria perder la evidencia en vez de respetarla.
        """
        store = _store_with(tmp_path_factory, "measured-negative", [
            _probe_result(
                _MEASURED_LAYER3, "layer3",
                status=CapabilityStatus.UNSUPPORTED, verified=True,
            ),
        ])

        composition = plan_enterprise_hardware(
            enterprise,
            packet_tracer_version=MEASURED_VERSION,
            capability_store=store,
        )

        assert _candidate(composition, _MEASURED_LAYER3).capabilities.layer3 is (
            CapabilityStatus.UNSUPPORTED
        )


class TestTheProductionPathCannotFabricateEvidence:
    def test_no_fixture_or_supported_shortcut_reaches_the_consumer(self):
        """El consumidor no puede inventar capacidades: solo compone fuentes."""
        source = (
            PACKAGE / "application" / "use_cases" / "plan_enterprise_hardware.py"
        ).read_text(encoding="utf-8")

        assert ".supported(" not in source
        assert "fixture" not in source.casefold()
        assert "CapabilityStatus.SUPPORTED" not in source

    def test_no_model_name_exception_lives_in_planning(self):
        """La reconciliacion de capacidad no se contrabandea como excepcion fija.

        Un hecho modelo->slot que vive en el catalogo de infraestructura es
        legitimo: describir modelos fisicos es el trabajo de un catalogo. Una
        excepcion por nombre de modelo dentro del planificador NO lo es, porque
        haria pasar la referencia sin que la evidencia decidiera nada.
        """
        import re

        forbidden = re.compile(
            r"""["'](?:\d{4}(?:-\d+[A-Z]{2,})?|ISR\d{4})["']""",
        )
        planning = (
            PACKAGE / "domain" / "enterprise" / "services" / "hardware_planner.py",
            PACKAGE / "domain" / "enterprise" / "services" / "device_selector.py",
            PACKAGE / "domain" / "enterprise" / "services" / "enterprise_designer.py",
            PACKAGE / "application" / "use_cases" / "plan_enterprise_hardware.py",
        )

        for path in planning:
            found = forbidden.findall(path.read_text(encoding="utf-8"))
            assert not found, f"{path.name} carries model-name literals: {found}"
