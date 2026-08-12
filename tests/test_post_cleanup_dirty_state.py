"""Estado sucio final frente a estado histórico (TD-RUNTIME-001).

CONTRATO: `dirty_state` es el estado FINAL post-limpieza y es la fuente
autoritativa para aceptación/diagnóstico. `applied_dirty_state` es el estado
histórico derivado de `entries` y nunca se pisa.

La regla que cierra la deuda: una compensación exitosa sólo puede limpiar lo
que un inverso podía deshacer. No resuelve UNKNOWN --la duda es si la mutación
ocurrió-- ni DIRTY_UNRECOVERABLE, que es sucio porque no había inverso.
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


# ===================== estado antes de limpiar =============================


def test_no_mutation_is_clean_before_and_after():
    journal = _journal()

    assert journal.applied_dirty_state is DirtyState.CLEAN
    assert journal.dirty_state is DirtyState.CLEAN
    assert journal.cleanup_status is CompensationStatus.NOT_ATTEMPTED


def test_a_failure_after_a_recoverable_mutation_is_dirty_recoverable():
    journal = _journal(MutationDisposition.CHANGED, MutationDisposition.FAILED)

    assert journal.dirty_state is DirtyState.DIRTY_RECOVERABLE
    assert journal.applied_dirty_state is DirtyState.DIRTY_RECOVERABLE


def test_a_failure_after_a_mutation_without_inverse_is_unrecoverable():
    journal = _journal(
        MutationDisposition.CHANGED, MutationDisposition.FAILED, inverse=False,
    )

    assert journal.dirty_state is DirtyState.DIRTY_UNRECOVERABLE


def test_an_unknown_disposition_dominates():
    journal = _journal(MutationDisposition.CHANGED, MutationDisposition.UNKNOWN)

    assert journal.dirty_state is DirtyState.UNKNOWN


# ===================== limpieza exitosa: qué puede probar ==================


def test_successful_cleanup_clears_only_what_an_inverse_could_undo():
    journal = _journal(MutationDisposition.CHANGED, MutationDisposition.FAILED)
    assert journal.dirty_state is DirtyState.DIRTY_RECOVERABLE

    journal.mark_cleanup(CompensationStatus.SUCCEEDED)

    assert journal.dirty_state is DirtyState.CLEAN
    assert journal.cleanup_status is CompensationStatus.SUCCEEDED


def test_successful_cleanup_never_resolves_an_unknown_mutation():
    """El núcleo de TD-RUNTIME-001: la falsa limpieza."""
    journal = _journal(MutationDisposition.UNKNOWN)

    journal.mark_cleanup(CompensationStatus.SUCCEEDED)

    assert journal.cleanup_status is CompensationStatus.SUCCEEDED
    assert journal.dirty_state is DirtyState.UNKNOWN
    assert journal.applied_dirty_state is DirtyState.UNKNOWN


def test_successful_cleanup_never_clears_an_unrecoverable_mutation():
    journal = _journal(
        MutationDisposition.CHANGED, MutationDisposition.FAILED, inverse=False,
    )

    journal.mark_cleanup(CompensationStatus.SUCCEEDED)

    assert journal.dirty_state is DirtyState.DIRTY_UNRECOVERABLE


def test_successful_cleanup_over_a_clean_journal_stays_clean():
    journal = _journal(MutationDisposition.CHANGED)

    journal.mark_cleanup(CompensationStatus.SUCCEEDED)

    assert journal.dirty_state is DirtyState.CLEAN


# ===================== limpieza fallida y desconocida ======================


@pytest.mark.parametrize(
    "dispositions",
    [
        (MutationDisposition.CHANGED, MutationDisposition.FAILED),
        (MutationDisposition.UNKNOWN,),
        (MutationDisposition.CHANGED,),
    ],
    ids=["recoverable", "unknown", "clean"],
)
def test_failed_cleanup_always_reports_unrecoverable_residue(dispositions):
    """Contrato previo, conservado: una compensación fallida pide atención."""
    journal = _journal(*dispositions)

    journal.mark_cleanup(CompensationStatus.FAILED)

    assert journal.dirty_state is DirtyState.DIRTY_UNRECOVERABLE
    assert journal.cleanup_status is CompensationStatus.FAILED


def test_unknown_cleanup_is_unknown_whatever_preceded_it():
    journal = _journal(MutationDisposition.CHANGED, MutationDisposition.FAILED)

    journal.mark_cleanup(CompensationStatus.UNKNOWN)

    assert journal.dirty_state is DirtyState.UNKNOWN


# ===================== histórico frente a final ============================


def test_the_historical_state_survives_a_successful_cleanup():
    """Lo aplicado no se borra: `entries` es append-only."""
    journal = _journal(MutationDisposition.CHANGED, MutationDisposition.FAILED)

    journal.mark_cleanup(CompensationStatus.SUCCEEDED)

    assert journal.dirty_state is DirtyState.CLEAN
    assert journal.applied_dirty_state is DirtyState.DIRTY_RECOVERABLE
    assert len(journal.entries) == 2


def test_the_two_states_agree_when_no_cleanup_was_attempted():
    for dispositions in (
        (MutationDisposition.CHANGED,),
        (MutationDisposition.CHANGED, MutationDisposition.FAILED),
        (MutationDisposition.UNKNOWN,),
    ):
        journal = _journal(*dispositions)
        assert journal.dirty_state is journal.applied_dirty_state


def test_appending_after_cleanup_recomputes_from_entries():
    """Una entrada nueva no puede quedar tapada por una limpieza previa."""
    journal = _journal(MutationDisposition.CHANGED, MutationDisposition.FAILED)
    journal.mark_cleanup(CompensationStatus.SUCCEEDED)
    assert journal.dirty_state is DirtyState.CLEAN

    journal.append(_entry(3, MutationDisposition.UNKNOWN))

    assert journal.dirty_state is DirtyState.UNKNOWN
    assert journal.applied_dirty_state is DirtyState.UNKNOWN


# ===================== no hay falsa limpieza en ninguna combinación ========


@pytest.mark.parametrize("status", list(CompensationStatus))
@pytest.mark.parametrize(
    "dispositions",
    [
        (MutationDisposition.UNKNOWN,),
        (MutationDisposition.CHANGED, MutationDisposition.UNKNOWN),
    ],
    ids=["unknown-only", "changed-then-unknown"],
)
def test_an_unknown_mutation_never_becomes_clean(status, dispositions):
    """Barrido adversarial: ningún estado de compensación puede limpiar UNKNOWN."""
    journal = _journal(*dispositions)
    assert journal.dirty_state is DirtyState.UNKNOWN

    journal.mark_cleanup(status)

    assert journal.dirty_state is not DirtyState.CLEAN
