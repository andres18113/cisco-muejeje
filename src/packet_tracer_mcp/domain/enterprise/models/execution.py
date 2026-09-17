"""Shared action operation, execution journal, and dirty-state semantics."""

from __future__ import annotations

from datetime import datetime
from enum import Enum, StrEnum
from typing import Any

from pydantic import BaseModel, Field


class OperationSemantics(StrEnum):
    """What one action intends to do to the state it names."""

    __str__ = Enum.__str__

    ENSURE_PRESENT = "ensure_present"
    ENSURE_ABSENT = "ensure_absent"
    SET_VALUE = "set_value"
    REPLACE = "replace"
    TRANSITION = "transition"
    EXECUTE_ONCE = "execute_once"


class MutationDisposition(StrEnum):
    """What an applied action turned out to do to the observed state."""

    __str__ = Enum.__str__

    CHANGED = "changed"
    NO_OP = "no_op"
    REASSERTED = "reasserted"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


class DirtyState(StrEnum):
    """Residuo que una aplicación deja en el backend.

    `ApplicationExecutionJournal.dirty_state` es el estado FINAL, ya compuesto
    con el resultado de la compensación. El estado histórico, anterior a
    cualquier limpieza, se conserva en `entries` y se lee con
    `applied_dirty_state`. Los dos son distintos y ninguno se pisa al otro.
    """

    __str__ = Enum.__str__

    # No hubo mutación, o la que falló no llegó a mutar nada.
    CLEAN = "clean"
    # Falló algo después de mutar, pero toda mutación tiene inverso.
    DIRTY_RECOVERABLE = "dirty_recoverable"
    # Falló algo después de mutar y alguna mutación no tiene inverso.
    DIRTY_UNRECOVERABLE = "dirty_unrecoverable"
    # No se sabe si la mutación ocurrió. La duda no se limpia compensando.
    UNKNOWN = "unknown"


class CompensationStatus(StrEnum):
    """Resultado de la COMPENSACIÓN, que no es lo mismo que restauración.

    `SUCCEEDED` dice que la operación de compensación se completó, no que todo
    lo mutado haya vuelto a su sitio: una compensación sólo puede deshacer
    aquello para lo que existía un inverso. Por eso no basta para declarar
    CLEAN por sí sola.
    """

    __str__ = Enum.__str__

    NOT_AVAILABLE = "not_available"
    AVAILABLE = "available"
    NOT_ATTEMPTED = "not_attempted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class DispatchFact(StrEnum):
    """What the execution channel established about one dispatch.

    ACCEPTED names acceptance by the channel that was used, never acceptance by
    Packet Tracer. ACCEPTANCE_UNKNOWN is the fail-closed value for a phase that
    could not be decided: the request bytes may or may not have left this
    process, so nothing about the effect may be claimed either way.
    UNSPECIFIED means the producer stated no fact at all, which is how a legacy
    row is recognized.
    """

    __str__ = Enum.__str__

    NOT_SUBMITTED = "not_submitted"
    REJECTED = "rejected"
    ACCEPTED = "accepted"
    ACCEPTANCE_UNKNOWN = "acceptance_unknown"
    UNSPECIFIED = "unspecified"


class ResultFact(StrEnum):
    """Whether a correlated result for one dispatch was actually observed.

    CORRELATED means a result registered to this operation came back and was
    consumed by its own waiter. NOT_OBSERVED, LOST, ENGINE_ERROR and MALFORMED
    each name a different way the read failed to decide anything, and none of
    them is evidence that the command did not run.
    """

    __str__ = Enum.__str__

    CORRELATED = "correlated"
    ENGINE_ERROR = "engine_error"
    MALFORMED = "malformed"
    NOT_OBSERVED = "not_observed"
    LOST = "lost"
    NOT_APPLICABLE = "not_applicable"


class PostconditionFact(StrEnum):
    """Whether the state the action intended was read back as satisfied.

    Computed from the actual typed post value inside the same script
    evaluation that read it; UNOBSERVED means the read did not complete, which
    is not the same as UNSATISFIED.
    """

    __str__ = Enum.__str__

    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    UNOBSERVED = "unobserved"
    NOT_APPLICABLE = "not_applicable"


class TransitionFact(StrEnum):
    """The transition of the state that was actually read.

    CHANGED and UNCHANGED compare the actual typed values from the bracketing
    reads. Within the observed scope only: a transition is never a claim about
    execution count, about sole causation, or about anything the reads did not
    cover. UNOBSERVED means at least one of the two reads did not complete.
    """

    __str__ = Enum.__str__

    UNCHANGED = "unchanged"
    CHANGED = "changed"
    UNOBSERVED = "unobserved"
    NOT_APPLICABLE = "not_applicable"


class FootprintFact(StrEnum):
    """Whether the state that was read covers the setter's whole effect.

    COVERED means the observed scope is the documented effect footprint, so a
    satisfied postcondition with no observed change leaves no residue. PARTIAL
    means the setter can change state the read cannot see, so the residue
    outside that scope stays unobserved and is never reported clean.
    """

    __str__ = Enum.__str__

    COVERED = "covered"
    PARTIAL = "partial"
    NOT_APPLICABLE = "not_applicable"


class ExecutionJournalEntry(BaseModel):
    """One append-only record of what happened to one action."""

    ordinal: int
    action_id: str
    operation: OperationSemantics
    disposition: MutationDisposition
    batch_id: str = ""
    inverse_action_id: str = ""
    inverse_available: bool = False
    compensation_status: CompensationStatus = CompensationStatus.NOT_AVAILABLE
    message: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    #: Channel acceptance and correlated-read facts for this action, copied
    #: from the result that produced the entry. UNSPECIFIED and NOT_APPLICABLE
    #: are the legacy defaults, so a producer that states no fact is still
    #: recognizable as one.
    dispatch: DispatchFact = DispatchFact.UNSPECIFIED
    result: ResultFact = ResultFact.NOT_APPLICABLE
    #: An OBSERVED unintended change. `False` is only the ABSENCE of that
    #: observation, never a claim that nothing changed: unknown residue is
    #: carried by disposition UNKNOWN plus `cause`.
    residual_change: bool = False
    cause: str = ""


class ApplicationExecutionJournal(BaseModel):
    """Registro append-only de una aplicación, y su estado sucio.

    INVARIANTE AUTORITATIVA. `dirty_state` es el estado FINAL post-limpieza y
    es la única fuente de verdad para un consumidor que decida aceptación,
    diagnóstico o autofix. `applied_dirty_state` es el estado histórico
    derivado de `entries`, anterior a cualquier compensación, y nunca se pisa.

    Cuando no se intentó compensación los dos coinciden. Cuando sí se intentó,
    `dirty_state` es la composición de ambos según `mark_cleanup`, que jamás
    declara CLEAN sin evidencia de que lo mutado se restauró.
    """

    plan_id: str
    deployment_id: str = ""
    entries: list[ExecutionJournalEntry] = Field(default_factory=list)
    dirty_state: DirtyState = DirtyState.CLEAN
    preflight_errors: list[str] = Field(default_factory=list)
    cleanup_status: CompensationStatus = CompensationStatus.NOT_ATTEMPTED
    #: `mark_cleanup` ejecutó inversos contra lo aplicado; un restore de
    #: escenario no. Es lo único que distingue a los dos veredictos cuando
    #: SUCCEEDED, y se conserva para poder RECOMPONER el estado final en vez
    #: de escribirlo una sola vez y quedar a merced del siguiente `append`.
    cleanup_undid_mutations: bool = False
    #: Cuántas entradas había cuando se registró el veredicto. Una compensación
    #: sólo pudo deshacer lo que ya estaba: reaplicarla a entradas posteriores
    #: lavaría una mutación que la compensación nunca vio. `-1` significa "sin
    #: veredicto registrado", y hace que la composición cubra el journal entero,
    #: que es lo que hacía antes de existir este campo.
    cleanup_ordinal: int = -1
    #: El residuo más fuerte que CUALQUIER veredicto ya registrado estableció.
    #: Sólo sube. Un veredicto posterior puede empeorar el estado; ninguno puede
    #: borrar lo que otro ya probó que quedó sin deshacer.
    residue_floor: DirtyState = DirtyState.CLEAN
    #: El transporte no pudo probar que la mutación no ocurrió. Es pegajoso:
    #: una entrada posterior no despeja esa duda.
    transport_unknown: bool = False

    @property
    def applied_dirty_state(self) -> DirtyState:
        """Estado histórico, derivado sólo de lo aplicado.

        Se recalcula desde `entries`, que son append-only, así que una
        compensación posterior no puede borrarlo.
        """
        return _derive_dirty_state(self.entries)

    def append(self, entry: ExecutionJournalEntry) -> None:
        """Append one entry in ordinal order and recompose the dirty state."""
        expected = len(self.entries) + 1
        if entry.ordinal != expected:
            raise ValueError(
                f"Journal ordinal {entry.ordinal} is invalid; expected {expected}."
            )
        self.entries.append(entry)
        self._recompose()

    def mark_preflight_failure(self, message: str) -> None:
        """Record an admission failure that produced no mutation."""
        self.preflight_errors.append(message)
        self._recompose()

    def mark_transport_unknown(self, message: str = "") -> None:
        """Record that the transport could not prove the mutation did not run."""
        if message:
            self.preflight_errors.append(message)
        self.transport_unknown = True
        self._recompose()

    def mark_cleanup(self, status: CompensationStatus) -> None:
        """Compone el estado final con lo que la compensación puede probar.

        Una compensación exitosa sólo deshace aquello para lo que existía un
        inverso, así que sólo puede limpiar `DIRTY_RECOVERABLE`. No puede
        resolver `UNKNOWN` --la duda es si la mutación llegó a ocurrir, y
        compensar no la despeja-- ni `DIRTY_UNRECOVERABLE`, que es dirty
        precisamente porque no había inverso que ejecutar.
        """
        self.cleanup_status = status
        self.cleanup_undid_mutations = True
        self._record_verdict(status)

    def record_scenario_restore(self, status: CompensationStatus) -> None:
        """Restauración de un escenario inyectado, que NO compensa la aplicación.

        `mark_cleanup` es para una compensación que ejecutó inversos contra lo
        que se aplicó. Devolver un enlace que este mismo runtime tumbó no es
        eso: no dice nada sobre las mutaciones que dejó una aplicación fallida,
        así que sólo puede empeorar el estado, nunca mejorarlo.

        Separar las dos operaciones es lo que impide que un restore exitoso
        borre una suciedad que nadie deshizo.
        """
        self.cleanup_status = status
        self.cleanup_undid_mutations = False
        self._record_verdict(status)

    def _record_verdict(self, status: CompensationStatus) -> None:
        """Fija hasta dónde llega este veredicto y qué residuo deja probado.

        Dos cosas que la primera versión de la composición no tenía, y que una
        revisión adversarial encontró como debilitamientos reales:

        1. el veredicto sólo cubre las entradas que existían cuando se
           registró. Una compensación exitosa no pudo deshacer una mutación
           añadida después, así que reaplicarla la lavaría;
        2. un residuo ya probado no se borra porque llegue otro veredicto. El
           piso sólo sube: `record_scenario_restore(SUCCEEDED)` después de un
           `mark_cleanup(FAILED)` dejaba CLEAN una suciedad que nadie deshizo,
           contradiciendo la docstring del propio método.
        """
        self.cleanup_ordinal = len(self.entries)
        if status is CompensationStatus.FAILED:
            floor = DirtyState.DIRTY_UNRECOVERABLE
        elif status is CompensationStatus.UNKNOWN:
            floor = DirtyState.UNKNOWN
        else:
            floor = DirtyState.CLEAN
        self.residue_floor = max(
            self.residue_floor,
            floor,
            key=_RESIDUE_SEVERITY.__getitem__,
        )
        self._recompose()

    def _recompose(self) -> None:
        """Recompone el estado final desde lo aplicado y el veredicto vigente.

        Escribir `dirty_state` una sola vez dejaba el estado a merced del
        siguiente `append` o marcador de preflight, que recomputaban desde
        `entries` sin mirar `cleanup_status`. Componer en cada transición es lo
        que impide que un veredicto residual ya registrado quede contradicho.

        La semántica de cada veredicto es la de siempre, verbatim: una
        compensación exitosa sólo limpia lo que un inverso podía deshacer, un
        restore de escenario no limpia nada, y FAILED/UNKNOWN mandan. Lo único
        nuevo es que se vuelve a aplicar en vez de recordarse.
        """
        covered = (
            self.entries
            if self.cleanup_ordinal < 0
            else self.entries[: self.cleanup_ordinal]
        )
        uncovered = (
            [] if self.cleanup_ordinal < 0 else self.entries[self.cleanup_ordinal :]
        )
        state = _derive_dirty_state(covered)
        if self.cleanup_status is CompensationStatus.SUCCEEDED:
            if self.cleanup_undid_mutations and state in {
                DirtyState.CLEAN,
                DirtyState.DIRTY_RECOVERABLE,
            }:
                state = DirtyState.CLEAN
        elif self.cleanup_status is CompensationStatus.FAILED:
            # Sin cambios respecto al contrato previo, y a proposito: una
            # compensacion fallida se reporta como residuo que nadie puede
            # deshacer solo, que es la señal mas fuerte para pedir atencion.
            # Degradarla a UNKNOWN seria mas debil, no mas honesto.
            state = DirtyState.DIRTY_UNRECOVERABLE
        elif self.cleanup_status is CompensationStatus.UNKNOWN:
            state = DirtyState.UNKNOWN
        # Lo aplicado DESPUÉS del veredicto no lo cubrió ninguna compensación,
        # así que entra por su cuenta y sólo puede empeorar el resultado.
        floors = [state, self.residue_floor, _derive_dirty_state(uncovered)]
        if self.transport_unknown:
            floors.append(DirtyState.UNKNOWN)
        self.dirty_state = max(floors, key=_RESIDUE_SEVERITY.__getitem__)

    def compact_summary(self) -> dict[str, object]:
        """Return the stable report shape; consumers depend on these keys."""
        counts: dict[str, int] = {}
        for entry in self.entries:
            counts[entry.disposition.value] = counts.get(entry.disposition.value, 0) + 1
        return {
            "plan_id": self.plan_id,
            "deployment_id": self.deployment_id,
            "attempted": len(self.entries),
            "counts": dict(sorted(counts.items())),
            "dirty_state": self.dirty_state.value,
            "cleanup_status": self.cleanup_status.value,
            "preflight_errors": list(self.preflight_errors),
        }


def satisfies_apply_dependency(status: Any) -> bool:
    """Whether a dependent action may proceed after this status."""
    value = status.value if isinstance(status, Enum) else str(status)
    return value in {"applied", "no_op", "reasserted", "verified"}


def disposition_from_status(status: Any) -> MutationDisposition:
    """Deriva una disposición sólo desde estados que la evidencian.

    `applied` NO está en el mapa, a propósito. `APPLIED` significa que el canal
    de ejecución aceptó el despacho, y eso no observa nada del backend: inferir
    `REASSERTED` de ahí era ponerle un nombre observacional a algo que nadie
    miró. Un despacho sin disposición explícita queda `UNKNOWN`, que es el
    default de este `.get`.

    Los estados que sí quedan son los que ya cargan la observación: `no_op` y
    `reasserted` sólo se producen cuando un runtime declaró esa disposición,
    y `failed` / `dependency_blocked` / `skipped` describen lo que pasó con el
    intento, no con el estado del dispositivo.
    """
    value = status.value if isinstance(status, Enum) else str(status)
    return {
        "no_op": MutationDisposition.NO_OP,
        "reasserted": MutationDisposition.REASSERTED,
        "failed": MutationDisposition.FAILED,
        "dependency_blocked": MutationDisposition.BLOCKED,
        "skipped": MutationDisposition.SKIPPED,
    }.get(value, MutationDisposition.UNKNOWN)


def journal_from_action_results(
    *,
    plan_id: str,
    deployment_id: str,
    actions: list[Any],
    results: list[Any],
) -> ApplicationExecutionJournal:
    """Build a journal from action results, copying the facts they carry."""
    actions_by_id = {item.id: item for item in actions}
    operations = {
        identifier: getattr(item, "operation", OperationSemantics.SET_VALUE)
        for identifier, item in actions_by_id.items()
    }
    journal = ApplicationExecutionJournal(plan_id=plan_id, deployment_id=deployment_id)
    for ordinal, result in enumerate(results, start=1):
        explicit_disposition = getattr(
            result,
            "disposition",
            MutationDisposition.UNKNOWN,
        )
        journal.append(
            ExecutionJournalEntry(
                ordinal=ordinal,
                action_id=result.action_id,
                operation=operations.get(
                    result.action_id, OperationSemantics.SET_VALUE
                ),
                disposition=(
                    explicit_disposition
                    if explicit_disposition is not MutationDisposition.UNKNOWN
                    else disposition_from_status(result.status)
                ),
                batch_id=getattr(result, "batch_id", ""),
                inverse_action_id=getattr(
                    actions_by_id.get(result.action_id),
                    "inverse_action_id",
                    "",
                ),
                inverse_available=getattr(
                    actions_by_id.get(result.action_id),
                    "compensation_available",
                    False,
                ),
                message=getattr(result, "message", ""),
                # getattr defaults, not required fields: a legacy producer that
                # never heard of these facts still builds a valid entry, and
                # its defaults are exactly what marks the row as legacy.
                dispatch=getattr(result, "dispatch", DispatchFact.UNSPECIFIED),
                result=getattr(result, "result", ResultFact.NOT_APPLICABLE),
                residual_change=bool(getattr(result, "residual_change", False)),
                cause=getattr(result, "cause", ""),
            )
        )
    return journal


#: Cuánto afirma cada residuo. Sólo se usa para que una duda de transporte no
#: pueda PISAR un residuo ya conocido: UNKNOWN dice "no sé si mutó", y eso es
#: más débil que saber que mutó y que nadie lo deshizo.
_RESIDUE_SEVERITY = {
    DirtyState.CLEAN: 0,
    DirtyState.DIRTY_RECOVERABLE: 1,
    DirtyState.UNKNOWN: 2,
    DirtyState.DIRTY_UNRECOVERABLE: 3,
}


def _derive_dirty_state(entries: list[ExecutionJournalEntry]) -> DirtyState:
    """Derive the residue the entries can actually establish.

    One rule is new: a FAILED entry whose `residual_change` is True counts as a
    mutation. A setter that stored the wrong value and then reported failure
    left an OBSERVED change behind, and calling that CLEAN because its
    disposition is FAILED was the way a real residue disappeared from the
    report. Every other input maps exactly as before, including an UNKNOWN
    entry, which is how unobserved residue stays UNKNOWN instead of clean.
    """
    if not entries:
        return DirtyState.CLEAN
    if any(item.disposition is MutationDisposition.UNKNOWN for item in entries):
        return DirtyState.UNKNOWN
    failed = any(item.disposition is MutationDisposition.FAILED for item in entries)
    mutations = [
        item
        for item in entries
        if item.disposition
        in {MutationDisposition.CHANGED, MutationDisposition.REASSERTED}
        or (item.disposition is MutationDisposition.FAILED and item.residual_change)
    ]
    if not failed:
        return DirtyState.CLEAN
    if not mutations:
        return DirtyState.CLEAN
    if all(item.inverse_available for item in mutations):
        return DirtyState.DIRTY_RECOVERABLE
    return DirtyState.DIRTY_UNRECOVERABLE
