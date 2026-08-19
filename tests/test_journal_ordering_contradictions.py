"""Órdenes que contradicen un veredicto de limpieza ya registrado (TD-RUNTIME-006).

CONTRATO. `dirty_state` es el estado FINAL y `cleanup_status` es el veredicto
que lo compuso. Ninguna operación posterior --`append`, `mark_preflight_failure`
o `mark_transport_unknown`-- puede dejar los dos contradiciéndose: un journal
que registró una compensación FAILED no puede terminar CLEAN porque después se
añadió una entrada benigna.

La corrección de Debt Checkpoint 2 cuenta CUATRO órdenes, no dos:
`record_scenario_restore` escribe `dirty_state` por el mismo mecanismo que
`mark_cleanup`, así que está expuesto a los mismos dos sucesores. Las cuatro
están aquí, y también `mark_transport_unknown`, que hoy no tiene ningún
llamador y heredaría el defecto en silencio.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.execution import (
    ApplicationExecutionJournal,
    CompensationStatus,
    DirtyState,
    ExecutionJournalEntry,
    MutationDisposition,
    OperationSemantics,
)


def _entry(ordinal: int, disposition: MutationDisposition, *, inverse: bool = True):
    return ExecutionJournalEntry(
        ordinal=ordinal,
        action_id=f"action-{ordinal}",
        operation=OperationSemantics.SET_VALUE,
        disposition=disposition,
        inverse_available=inverse,
    )


def _journal(*dispositions, inverse: bool = True) -> ApplicationExecutionJournal:
    journal = ApplicationExecutionJournal(plan_id="plan")
    for index, disposition in enumerate(dispositions, start=1):
        journal.append(_entry(index, disposition, inverse=inverse))
    return journal


#: Los dos veredictos que dejan un residuo que nadie deshizo. SUCCEEDED no
#: entra: no hay nada que una entrada posterior pueda contradecir.
_RESIDUAL_VERDICTS = [
    (CompensationStatus.FAILED, DirtyState.DIRTY_UNRECOVERABLE),
    (CompensationStatus.UNKNOWN, DirtyState.UNKNOWN),
]

#: Las dos formas de registrar un veredicto. Ambas escriben `cleanup_status`.
_RECORDERS = [
    ("mark_cleanup", lambda journal, status: journal.mark_cleanup(status)),
    ("record_scenario_restore", lambda journal, status: journal.record_scenario_restore(status)),
]


# ===================== append después de un veredicto ======================


@pytest.mark.parametrize("recorder,record", _RECORDERS, ids=[item[0] for item in _RECORDERS])
@pytest.mark.parametrize("status,expected", _RESIDUAL_VERDICTS, ids=["failed", "unknown"])
def test_a_benign_append_cannot_erase_a_residual_verdict(recorder, record, status, expected):
    """Órdenes 1 y 3: `append` recomputaba desde `entries` sin mirar el veredicto."""
    journal = _journal(MutationDisposition.CHANGED)
    assert journal.dirty_state is DirtyState.CLEAN

    record(journal, status)
    assert journal.dirty_state is expected

    journal.append(_entry(2, MutationDisposition.NO_OP))

    assert journal.cleanup_status is status
    assert journal.dirty_state is expected, (
        f"{recorder}({status.value}) quedó contradicho por un append benigno"
    )


def test_an_append_still_escalates_a_state_the_verdict_did_not_cover():
    """La composición no congela: una entrada peor sigue empeorando el estado."""
    journal = _journal(MutationDisposition.CHANGED, MutationDisposition.FAILED)
    journal.mark_cleanup(CompensationStatus.SUCCEEDED)
    assert journal.dirty_state is DirtyState.CLEAN

    journal.append(_entry(3, MutationDisposition.UNKNOWN))

    assert journal.dirty_state is DirtyState.UNKNOWN


# ===================== preflight después de un veredicto ===================


@pytest.mark.parametrize("recorder,record", _RECORDERS, ids=[item[0] for item in _RECORDERS])
@pytest.mark.parametrize("status,expected", _RESIDUAL_VERDICTS, ids=["failed", "unknown"])
def test_a_preflight_marker_cannot_erase_a_residual_verdict(recorder, record, status, expected):
    """Órdenes 2 y 4: `mark_preflight_failure` forzaba CLEAN con `entries` vacío."""
    journal = ApplicationExecutionJournal(plan_id="plan")

    record(journal, status)
    assert journal.dirty_state is expected

    journal.mark_preflight_failure("preflight refused the batch")

    assert journal.cleanup_status is status
    assert journal.dirty_state is expected, (
        f"{recorder}({status.value}) quedó contradicho por un marcador de preflight"
    )
    assert journal.preflight_errors == ["preflight refused the batch"]


def test_a_preflight_marker_on_a_virgin_journal_is_still_clean():
    """Sin veredicto no hay nada que componer, y el contrato previo se conserva."""
    journal = ApplicationExecutionJournal(plan_id="plan")

    journal.mark_preflight_failure("nothing was dispatched")

    assert journal.dirty_state is DirtyState.CLEAN
    assert journal.cleanup_status is CompensationStatus.NOT_ATTEMPTED


# ===================== transporte desconocido =============================


def test_transport_unknown_survives_a_later_append():
    """Hoy no tiene llamadores; un futuro llamador heredaría el mismo defecto."""
    journal = _journal(MutationDisposition.CHANGED)

    journal.mark_transport_unknown("the bridge could not prove non-execution")
    assert journal.dirty_state is DirtyState.UNKNOWN

    journal.append(_entry(2, MutationDisposition.NO_OP))

    assert journal.dirty_state is DirtyState.UNKNOWN


def test_transport_unknown_never_downgrades_an_unrecoverable_residue():
    """UNKNOWN es más débil que DIRTY_UNRECOVERABLE: no puede pisarlo."""
    journal = _journal(
        MutationDisposition.CHANGED, MutationDisposition.FAILED, inverse=False,
    )
    assert journal.dirty_state is DirtyState.DIRTY_UNRECOVERABLE

    journal.mark_transport_unknown()

    assert journal.dirty_state is DirtyState.DIRTY_UNRECOVERABLE


# ===================== barrido: ninguna orden contradice ==================


@pytest.mark.parametrize("recorder,record", _RECORDERS, ids=[item[0] for item in _RECORDERS])
@pytest.mark.parametrize("status", list(CompensationStatus))
def test_no_ordering_leaves_a_clean_state_under_a_residual_verdict(recorder, record, status):
    """Producto cruzado: 2 registradores x 6 veredictos x 3 sucesores."""
    for successor in (
        lambda item: item.append(_entry(len(item.entries) + 1, MutationDisposition.NO_OP)),
        lambda item: item.mark_preflight_failure("late refusal"),
        lambda item: item.mark_transport_unknown(),
    ):
        journal = _journal(MutationDisposition.CHANGED)
        record(journal, status)
        before = journal.dirty_state

        successor(journal)

        if status in {CompensationStatus.FAILED, CompensationStatus.UNKNOWN}:
            assert journal.dirty_state is not DirtyState.CLEAN
        if journal.dirty_state is not before:
            assert before is DirtyState.CLEAN, (
                f"{recorder}({status.value}) fue degradado por un sucesor"
            )


# ===================== un veredicto no puede borrar a otro =================


def test_a_scenario_restore_cannot_erase_a_failed_compensation():
    """Un restore exitoso no deshizo nada de lo que la compensación no pudo.

    Encontrado por revisión adversarial de la propia composición: registrar un
    segundo veredicto reescribía `cleanup_status`, y recomponer desde cero
    devolvía CLEAN sobre una compensación que había FALLADO. Es la misma clase
    de contradicción que esta deuda cierra, en el eje que faltaba: veredicto
    después de veredicto, no sucesor después de veredicto.
    """
    journal = _journal(MutationDisposition.CHANGED)
    journal.mark_cleanup(CompensationStatus.FAILED)
    assert journal.dirty_state is DirtyState.DIRTY_UNRECOVERABLE

    journal.record_scenario_restore(CompensationStatus.SUCCEEDED)

    assert journal.dirty_state is DirtyState.DIRTY_UNRECOVERABLE


def test_a_scenario_restore_cannot_erase_an_unknown_compensation():
    journal = _journal(MutationDisposition.CHANGED)
    journal.mark_cleanup(CompensationStatus.UNKNOWN)

    journal.record_scenario_restore(CompensationStatus.SUCCEEDED)

    assert journal.dirty_state is DirtyState.UNKNOWN


@pytest.mark.parametrize("first", [CompensationStatus.FAILED, CompensationStatus.UNKNOWN])
def test_no_second_verdict_of_any_kind_improves_a_residue(first):
    for record in (
        lambda item: item.mark_cleanup(CompensationStatus.SUCCEEDED),
        lambda item: item.record_scenario_restore(CompensationStatus.SUCCEEDED),
    ):
        journal = _journal(MutationDisposition.CHANGED)
        journal.mark_cleanup(first)
        before = journal.dirty_state

        record(journal)

        assert journal.dirty_state is before


# ============ una compensación sólo limpia lo que ya estaba ================


def test_a_successful_compensation_never_clears_a_mutation_it_could_not_have_seen():
    """La compensación corrió ANTES de estas entradas; no pudo deshacerlas.

    También adversarial: el flag "esta compensación ejecutó inversos" se
    reaplicaba a entradas añadidas DESPUÉS, así que un append posterior quedaba
    lavado a CLEAN por un veredicto que no lo cubría.
    """
    journal = _journal(MutationDisposition.CHANGED, MutationDisposition.FAILED)
    journal.mark_cleanup(CompensationStatus.SUCCEEDED)
    assert journal.dirty_state is DirtyState.CLEAN

    journal.append(_entry(3, MutationDisposition.CHANGED))
    journal.append(_entry(4, MutationDisposition.FAILED))

    assert journal.dirty_state is DirtyState.DIRTY_RECOVERABLE


def test_what_the_compensation_did_cover_stays_covered():
    """Y lo de antes sigue limpio: la partición es por ordinal, no por todo o nada."""
    journal = _journal(MutationDisposition.CHANGED, MutationDisposition.FAILED)
    journal.mark_cleanup(CompensationStatus.SUCCEEDED)

    journal.append(_entry(3, MutationDisposition.NO_OP))

    assert journal.dirty_state is DirtyState.CLEAN
    assert journal.applied_dirty_state is DirtyState.DIRTY_RECOVERABLE
