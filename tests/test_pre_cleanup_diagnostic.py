"""Stage 3A4 — el observador previo a la limpieza, y lo que NO puede hacer.

La limpieza vive dentro de `execute_enterprise_reference`: cuando el caso de uso
devuelve, la topologia ya no esta. Localizar un `reachable=False` exige mirar
ANTES, y la unica alternativa seria que un harness ordenara las etapas, que es
lo que MEG-3 prohibe. Por eso el producto invoca al observador.

Lo que estos tests fijan es la contencion, no la utilidad:

* corre UNA vez, despues de la etapa terminal y ANTES de la limpieza;
* un observador que explota no convierte una corrida en fallida;
* nada de lo que devuelve toca `status`, `errors`, la evidencia de
  configuracion ni las fundaciones -- solo `diagnostics`.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.execute_enterprise_reference import (
    EnterpriseDiagnosticContext,
    EnterpriseExecutionStage,
    EnterpriseExecutionStatus,
)

from test_stage3a4_offline_adversarial_matrix import (
    _ForbiddenControlPlaneRuntime,
    _FailingConfigurationRuntime,
    _GenericPhysicalRuntime,
    _run,
)


class _Spy:
    """Anota el orden en el que lo llamaron y que vio."""

    def __init__(self, journal: list[str], lines=("seen",), boom: bool = False) -> None:
        self.journal = journal
        self.lines = lines
        self.boom = boom
        self.contexts: list[EnterpriseDiagnosticContext] = []

    def __call__(self, context):
        self.journal.append("diagnostic")
        self.contexts.append(context)
        if self.boom:
            raise RuntimeError("the observer is broken")
        return self.lines


def _failing_run(diagnostic, journal):
    physical = _GenericPhysicalRuntime()
    original = physical.remove_device

    def _watched(device):
        journal.append("cleanup")
        return original(device)

    physical.remove_device = _watched
    return _run(
        physical=physical,
        configuration=_FailingConfigurationRuntime([]),
        control_plane=_ForbiddenControlPlaneRuntime(),
        pre_cleanup_diagnostic=diagnostic,
    )


class TestItRunsBeforeCleanupExactlyOnce:
    def test_the_observer_sees_the_scene_that_cleanup_is_about_to_destroy(self):
        journal: list[str] = []
        spy = _Spy(journal)

        result = _failing_run(spy, journal)

        assert journal.count("diagnostic") == 1
        assert journal[0] == "diagnostic"
        assert journal.count("cleanup") > 0
        assert result.cleanup_results, "cleanup still ran after the diagnostic"

    def test_the_context_carries_the_run_that_actually_executed(self):
        journal: list[str] = []
        spy = _Spy(journal)

        _failing_run(spy, journal)

        context = spy.contexts[0]
        assert context.stage is EnterpriseExecutionStage.CONFIGURATION_APPLY
        # Lo compilado en ESTA corrida, no valores historicos.
        assert context.composition is not None
        assert context.oriented_manifest is not None
        assert context.topology is not None

    def test_without_an_observer_nothing_changes(self):
        journal: list[str] = []

        result = _failing_run(None, journal)

        assert journal.count("diagnostic") == 0
        assert result.diagnostics == []


class TestItCannotChangeTheRun:
    def test_a_broken_observer_is_recorded_and_never_becomes_a_run_error(self):
        journal: list[str] = []
        spy = _Spy(journal, boom=True)

        result = _failing_run(spy, journal)

        assert any(item.startswith("diagnostic_failed:") for item in result.diagnostics)
        # El fallo del observador NO aparece entre los errores de la corrida.
        assert not any("observer is broken" in item for item in result.errors)
        # Y la limpieza corrio igual.
        assert result.cleanup_results

    def test_its_output_lands_only_in_diagnostics(self):
        journal: list[str] = []
        spy = _Spy(journal, lines=("dropped at SW1", "reason: ..."))

        result = _failing_run(spy, journal)

        assert result.diagnostics == ["dropped at SW1", "reason: ..."]
        assert result.errors and "dropped at SW1" not in " ".join(result.errors)

    def test_a_clean_observer_does_not_rescue_a_failed_run(self):
        journal: list[str] = []

        result = _failing_run(_Spy(journal, lines=("everything is fine",)), journal)

        assert result.status is EnterpriseExecutionStatus.FAILED
        assert result.stopped_at is EnterpriseExecutionStage.CONFIGURATION_APPLY

    def test_diagnostics_never_touch_configuration_or_foundation_evidence(self):
        journal: list[str] = []
        spy = _Spy(journal, lines=("ACCESS_PORT VERIFIED",))

        result = _failing_run(spy, journal)

        # Aunque el observador escriba literalmente eso, no hay via por la que
        # llegue a la evidencia: son listas distintas y nadie las reconcilia.
        assert result.diagnostics == ["ACCESS_PORT VERIFIED"]
        assert result.foundational_statuses == {}
        assert "ACCESS_PORT VERIFIED" not in str(result.configuration_result)

    def test_the_summary_exposes_diagnostics_apart_from_errors(self):
        journal: list[str] = []

        result = _failing_run(_Spy(journal, lines=("line",)), journal)
        summary = result.compact_summary()

        assert summary["diagnostics"] == ["line"]
        assert "line" not in summary["errors"]


class TestBlockedRunsNeverDiagnose:
    """BLOCKED significa que no se toco Packet Tracer: no hay escena que mirar."""

    def test_a_blocked_run_does_not_call_the_observer(self):
        from src.packet_tracer_mcp.application.use_cases.execute_enterprise_reference import (
            EnterpriseRuntimes,
            execute_enterprise_reference,
        )
        from test_stage3a4_offline_adversarial_matrix import (
            FINGERPRINT,
            _GenericOrientationRuntime,
            _QUALIFIED,
            _bounded_intent,
            _control_plane_intent,
        )
        from src.packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
            compose_enterprise_reference,
        )
        from test_enterprise_reference_execution import _isolated_preflight

        journal: list[str] = []
        physical = _GenericPhysicalRuntime(preexisting=["Someone Elses Router"])
        intent = _bounded_intent()
        topology = compose_enterprise_reference(
            intent, policy=_QUALIFIED, packet_tracer_version="9.0.1.0858",
        ).topology
        physical.bind(topology)

        result = execute_enterprise_reference(
            intent,
            EnterpriseRuntimes(
                physical=physical,
                serial_orientation=_GenericOrientationRuntime(),
                configuration=_FailingConfigurationRuntime([]),
                control_plane=_ForbiddenControlPlaneRuntime(),
            ),
            _control_plane_intent(topology),
            environment_fingerprint=FINGERPRINT,
            import_preflight=_isolated_preflight(),
            packet_tracer_version="9.0.1.0858",
            policy=_QUALIFIED,
            pre_cleanup_diagnostic=_Spy(journal),
        )

        assert result.status is EnterpriseExecutionStatus.BLOCKED
        assert journal == []
        assert result.diagnostics == []
