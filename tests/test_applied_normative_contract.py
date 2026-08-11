"""El contrato normativo de APPLIED y los tres ejes de un resultado.

Contexto historico, verificado contra git y no supuesto:
antes de Runtime Safety R1 NINGUN source definia que evento produce
`ActionExecutionStatus.APPLIED`. El enum no tenia documentacion y la
arquitectura sólo decia con que NO se confunde. R1 ADOPTA la definicion; no la
aclara ni la recupera.

Autoridad: docs/architecture/e95-stabilization.md, seccion
"What makes an action APPLIED".
"""

from __future__ import annotations

from pathlib import Path

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    RuntimeActionMutation,
    RuntimeVerification,
    mutation_execution_status,
)
from src.packet_tracer_mcp.domain.enterprise.models.execution import (
    MutationDisposition,
    disposition_from_status,
)

REPO = Path(__file__).resolve().parents[1]
AUTHORITY = REPO / "docs" / "architecture" / "e95-stabilization.md"


# -- la autoridad normativa existe y dice lo que debe ---------------------

def test_the_governing_document_defines_what_produces_applied():
    text = AUTHORITY.read_text(encoding="utf-8")

    assert "## What makes an action APPLIED" in text
    assert "accepted by its selected runtime execution channel" in text


def test_the_document_states_this_is_a_new_contract_not_an_old_one():
    """No se puede presentar como aclaracion algo que no existia."""
    text = AUTHORITY.read_text(encoding="utf-8")

    assert "new normative statement, not a restatement of" in text


def test_the_document_enumerates_what_applied_does_not_assert():
    text = AUTHORITY.read_text(encoding="utf-8")
    section = text.split("## What makes an action APPLIED")[1]

    for denial in (
        "backend acknowledgement", "`CHANGED`",
        "directly observed backend state", "successful verification",
    ):
        assert denial in section


# -- 3. los tres ejes son simultaneamente representables ------------------

def test_a_dispatch_only_mutation_is_representable_on_three_axes():
    """APPLIED + UNKNOWN + sin verificar es un estado valido y esperado.

    Significa: el canal acepto el despacho, el efecto todavia no se conoce.
    """
    mutation = RuntimeActionMutation(action_id="a1", applied=True)

    assert mutation_execution_status(mutation) is ActionExecutionStatus.APPLIED
    assert mutation.disposition is MutationDisposition.UNKNOWN
    # El tercer eje vive aparte: no hay ninguna verificacion todavia.
    assert RuntimeVerification(
        expectation_id="e1", status=ActionExecutionStatus.UNKNOWN,
    ).status is not ActionExecutionStatus.VERIFIED


def test_a_positive_readback_moves_only_the_verification_axis():
    mutation = RuntimeActionMutation(action_id="a1", applied=True)
    verification = RuntimeVerification(
        expectation_id="e1",
        status=ActionExecutionStatus.VERIFIED,
        fresh_evidence=True,
    )

    # La accion sigue siendo APPLIED: la verificacion no la reescribe.
    assert mutation_execution_status(mutation) is ActionExecutionStatus.APPLIED
    assert verification.status is ActionExecutionStatus.VERIFIED


def test_a_contradictory_readback_fails_verification_without_unsaying_the_dispatch():
    mutation = RuntimeActionMutation(action_id="a1", applied=True)
    verification = RuntimeVerification(
        expectation_id="e1",
        status=ActionExecutionStatus.FAILED,
        fresh_evidence=True,
    )

    assert mutation_execution_status(mutation) is ActionExecutionStatus.APPLIED
    assert verification.status is ActionExecutionStatus.FAILED


# -- 4. ningun productor promueve APPLIED a evidencia ---------------------

def test_dispatch_alone_never_produces_verified():
    for disposition in MutationDisposition:
        status = mutation_execution_status(
            RuntimeActionMutation(action_id="a", applied=True, disposition=disposition),
        )
        assert status is not ActionExecutionStatus.VERIFIED


def test_a_definite_local_failure_is_the_only_certain_negative():
    assert mutation_execution_status(
        RuntimeActionMutation(action_id="a", applied=False),
    ) is ActionExecutionStatus.FAILED


def test_the_journal_fallback_labels_a_dispatch_as_reasserted():
    """HALLAZGO REGISTRADO, no corregido en este stage de cierre.

    `journal_from_action_results` cae a `disposition_from_status` cuando la
    disposicion explicita es UNKNOWN, y ese mapeo convierte "applied" en
    REASSERTED -- un nombre que sugiere haber observado que el estado ya
    estaba. Nadie lo observo.

    Por que no se cambia aca: `_derive_dirty_state` cuenta REASSERTED COMO
    mutacion que necesita compensacion, y cualquier disposicion UNKNOWN fuerza
    `DirtyState.UNKNOWN`. Es decir, el mapeo actual es conservador para el
    rollback; lo impreciso es la ETIQUETA del journal, no la seguridad. Dejarlo
    en UNKNOWN volveria `DirtyState.UNKNOWN` a todo lote fire-and-forget, que
    es un cambio semantico mayor y no cabe en un cierre.

    Este test fija el comportamiento vigente para que el cambio, si se decide,
    sea deliberado y visible.
    """
    assert disposition_from_status(
        ActionExecutionStatus.APPLIED,
    ) is MutationDisposition.REASSERTED
