"""Resultados E5 que mantienen COMPILED, APPLIED y VERIFIED separados."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum

from pydantic import BaseModel, Field

from .deployment import EnvironmentFingerprint
from .evidence import EvidenceRecord
from .execution import (
    ApplicationExecutionJournal,
    DirtyState,
    DispatchFact,
    FootprintFact,
    MutationDisposition,
    OperationSemantics,
    PostconditionFact,
    ResultFact,
    TransitionFact,
    satisfies_apply_dependency,
)


class ActionExecutionStatus(StrEnum):
    """Estado de una acción a lo largo de su ciclo de vida.

    Qué evento produce APPLIED
    --------------------------
    Hasta R1-E esto no estaba escrito en ninguna parte. La arquitectura decía
    con qué NO se confunde -- `compiled != applied`, `applied != observed`,
    "a result may be APPLIED and still be UNOBSERVABLE" -- pero ningún source
    nombraba el evento que lo produce, y el enum no tenía documentación.

    Se fija aquí lo único que el transporte puede sustentar:

        APPLIED = el payload fue aceptado por el canal del runtime.

    Ni más ni menos. El canal de configuración es fire-and-forget: entrega el
    payload y no recibe acuse de Packet Tracer. Por eso APPLIED no puede
    significar "el backend confirmó la aplicación" -- no existe en el sistema
    ninguna señal capaz de sostener esa afirmación --, y tampoco "el estado
    quedó aplicado", que es precisamente lo que la verificación va a averiguar.

    Esto DOCUMENTA el comportamiento vigente; no lo cambia. Si la intención
    original era la lectura más fuerte ("el estado intencionado quedó aplicado
    aunque no sea observable"), entonces el transporte actual no puede
    entregarla y eso es una decisión semántica propia, no un ajuste de wording.

    FAILED aquí es una certeza LOCAL: el payload no salió del proceso, así que
    no puede aplicarse más tarde. VERIFIED es lo contrario de APPLIED en cuanto
    a evidencia: sale de releer el estado, nunca del envío.
    """

    __str__ = Enum.__str__

    INTENDED = "intended"
    COMPILED = "compiled"
    # Aceptado por el canal del runtime. NO implica efecto en el backend.
    APPLIED = "applied"
    # Releído del dispositivo. Es el único que afirma efecto.
    VERIFIED = "verified"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"
    DEPENDENCY_BLOCKED = "dependency_blocked"
    UNOBSERVABLE = "unobservable"
    NO_OP = "no_op"
    REASSERTED = "reasserted"


class ConfigurationApplicationStatus(StrEnum):
    """Aggregate status of one configuration application."""

    __str__ = Enum.__str__

    APPLIED = "applied"
    VERIFIED = "verified"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class ConfigurationFailureCode(StrEnum):
    """Typed reason a configuration action or run did not succeed."""

    __str__ = Enum.__str__

    NONE = "none"
    SOURCE_TOPOLOGY_MISMATCH = "source_topology_mismatch"
    TARGET_NOT_FOUND = "target_not_found"
    TARGET_IDENTITY_MISMATCH = "target_identity_mismatch"
    INTERFACE_NOT_FOUND = "interface_not_found"
    CAPABILITY_UNKNOWN = "capability_unknown"
    CAPABILITY_UNSUPPORTED = "capability_unsupported"
    APPLICATION_FAILED = "application_failed"
    SESSION_FAILED = "session_failed"
    CONVERGENCE_TIMEOUT = "convergence_timeout"
    VERIFICATION_FAILED = "verification_failed"
    OBSERVABILITY_LIMITATION = "observability_limitation"
    DEPENDENCY_BLOCKED = "dependency_blocked"
    SOURCE_CONFIGURATION_MISMATCH = "source_configuration_mismatch"
    FOUNDATIONAL_CONFIGURATION_MISSING = "foundational_configuration_missing"
    SERVICE_COMPILE_ERROR = "service_compile_error"
    SERVICE_HOST_MISSING = "service_host_missing"
    BEHAVIORAL_VERIFICATION_FAILED = "behavioral_verification_failed"
    DIRECT_READBACK_UNOBSERVABLE = "direct_readback_unobservable"
    CLEANUP_FAILED = "cleanup_failed"
    VOICE_COMPILE_ERROR = "voice_compile_error"
    CALL_CONTROL_APPLICATION_FAILED = "call_control_application_failed"
    PHONE_REGISTRATION_TIMEOUT = "phone_registration_timeout"
    PHONE_REGISTRATION_UNOBSERVABLE = "phone_registration_unobservable"
    CALL_SETUP_FAILED = "call_setup_failed"
    CALL_CONNECT_TIMEOUT = "call_connect_timeout"
    CALL_TEARDOWN_FAILED = "call_teardown_failed"
    SECURITY_COMPILE_ERROR = "security_compile_error"
    SECURITY_BASELINE_FAILED = "security_baseline_failed"
    SECURITY_APPLICATION_FAILED = "security_application_failed"
    SECURITY_DIRECT_READBACK_FAILED = "security_direct_readback_failed"
    SECURITY_ENFORCEMENT_FAILED = "security_enforcement_failed"
    SECURITY_BEHAVIOR_UNOBSERVABLE = "security_behavior_unobservable"
    SECURITY_CLEANUP_FAILED = "security_cleanup_failed"
    DEPLOYMENT_MANIFEST_REQUIRED = "deployment_manifest_required"
    ENVIRONMENT_FINGERPRINT_MISMATCH = "environment_fingerprint_mismatch"
    #: The channel accepted the dispatch and no correlated read decided
    #: the outcome. It is not a failure and not a success.
    OUTCOME_UNKNOWN = "outcome_unknown"
    #: A correlated read arrived in a shape the contract does not admit,
    #: so it states nothing about the action it was supposed to report.
    RESPONSE_MALFORMED = "response_malformed"
    #: The post-read completed and the intended state was not there.
    POSTCONDITION_UNSATISFIED = "postcondition_unsatisfied"


class FieldVerificationStatus(StrEnum):
    """Per-field outcome of one verification read."""

    __str__ = Enum.__str__

    VERIFIED = "verified"
    FAILED = "failed"
    UNKNOWN = "unknown"
    UNOBSERVABLE = "unobservable"


class ConvergenceOutcome(StrEnum):
    """Why a bounded convergence authority stopped -- as a product claim.

    A terminal network reading and a terminal OBSERVER reading are different
    claims, and collapsing them is how a lost clock or a failed read becomes a
    confident statement about the network. Keep them apart:

    * ``CONVERGED`` -- the observed state reached the intended one.
    * ``NETWORK_MEASURED`` -- the authority ran to its own end on a fresh
      sample, so the terminal state IS the answer. A qualified simulation-time
      budget that expired with the port still learning belongs here: that is a
      real negative.
    * ``OBSERVER_INCOMPLETE`` -- the authority could not finish. Whatever state
      is retained describes the last sample the observer managed to take, never
      a conclusion about the device.
    * ``UNKNOWN`` -- no typed convergence evidence survived at all.

    Only ``CONVERGED`` and ``NETWORK_MEASURED`` may support a product verdict.
    """

    __str__ = Enum.__str__

    CONVERGED = "converged"
    NETWORK_MEASURED = "network_measured"
    OBSERVER_INCOMPLETE = "observer_incomplete"
    UNKNOWN = "unknown"


class ConvergenceReport(BaseModel):
    """Terminal evidence of one bounded convergence authority."""

    attempts: int = 0
    elapsed_ms: int = 0
    final_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    last_observable_state: str = ""
    #: Optional structured terminal evidence for convergence observers.  The
    #: generic fields above remain the stable summary; observer-specific
    #: details preserve the exact members and authority dimensions needed to
    #: audit a grouped decision without parsing a human message.
    details: dict[str, object] = Field(default_factory=dict)


class RuntimeConfigurationTarget(BaseModel):
    """One device as the runtime actually reports it."""

    device_name: str
    model: str
    interfaces: list[str] = Field(default_factory=list)
    runtime_identifier: str = ""
    runtime_identifier_stable: bool = False
    runtime_fingerprint: str = ""


class ConfigurationRuntimeContext(BaseModel):
    """Backend identity carried into every evidence record of a run."""

    backend: str = ""
    backend_version: str = ""
    capability_snapshot_hash: str = ""
    environment_fingerprint: EnvironmentFingerprint | None = None

    @property
    def evidence_backend(self) -> str:
        """Backend name the fingerprint establishes, else the declared one."""
        if self.environment_fingerprint is not None:
            return self.environment_fingerprint.backend
        return self.backend

    @property
    def evidence_backend_version(self) -> str:
        """Backend version the fingerprint establishes, else the declared one."""
        if self.environment_fingerprint is not None:
            return self.environment_fingerprint.backend_version
        return self.backend_version

    @property
    def environment_semantic_hash(self) -> str:
        """Semantic hash of the environment, empty without a fingerprint."""
        if self.environment_fingerprint is None:
            return ""
        return self.environment_fingerprint.semantic_hash


class RuntimeActionMutation(BaseModel):
    """What a runtime reports about one dispatched action.

    Observations only. There is deliberately no `residual_change` input: a
    runtime reports what it read, and residue is something the decision
    derives from those readings plus the effect footprint.
    """

    action_id: str
    applied: bool
    operation: OperationSemantics = OperationSemantics.SET_VALUE
    disposition: MutationDisposition = MutationDisposition.UNKNOWN
    message: str = ""
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE
    batch_id: str = ""
    dispatch: DispatchFact = DispatchFact.UNSPECIFIED
    result: ResultFact = ResultFact.NOT_APPLICABLE
    postcondition: PostconditionFact = PostconditionFact.NOT_APPLICABLE
    transition: TransitionFact = TransitionFact.NOT_APPLICABLE
    footprint: FootprintFact = FootprintFact.NOT_APPLICABLE
    #: `None` means the producer stated nothing about whether the setter ran.
    #: It is distinct from False, which is a positive report that no call was
    #: made, and that distinction is what separates a skipped row from a row
    #: whose whole batch was never observed.
    attempted: bool | None = None
    cause: str = ""
    #: The bounded, sanitized detail the setter itself produced, kept apart
    #: from `cause` because they are different meanings: `cause` carries the
    #: canonical reason the row is what it is -- `pre_read_failed`,
    #: `footprint_partial:<scope>` -- and this field carries what the vendor
    #: call reported while that reason was being established. A row that has
    #: both used to lose this one. `decide_mutation` never reads it: a
    #: producer's diagnostic classifies nothing and authorizes nothing.
    call_error: str = ""


class MutationResidue(StrEnum):
    """What the journal may claim about state the action left behind.

    NONE means no unintended change within a COVERED footprint, or no call at
    all. CHANGED means an unintended change was OBSERVED. UNKNOWN means the
    observation could not establish either, and it is carried as disposition
    UNKNOWN plus a cause -- never as `residual_change=False`, which only ever
    means "no change was observed".
    """

    __str__ = Enum.__str__

    NONE = "none"
    CHANGED = "changed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MutationDecision:
    """The one decision that maps a fact tuple to a product outcome.

    `frontier` is the only input of `effect_established`: a dependent action
    may proceed on a validated SATISFIED postcondition, or on a legacy row's
    baseline dependency rule, and never on the raw `postcondition` field.
    `sticky` is the `mark_transport_unknown` trigger, and no field predicate
    re-derives it. `row` names the table row that decided, so an audit can
    tell row 7 (an invalid row after proven acceptance) from row 15 (no
    dispatch fact at all).
    """

    status: ActionExecutionStatus
    disposition: MutationDisposition
    failure_code: ConfigurationFailureCode
    residue: MutationResidue
    frontier: bool
    sticky: bool
    cause: str
    row: str


#: The observation defaults. A mutation carrying exactly these stated no fact,
#: which is what identifies a legacy producer -- not its name, its module or
#: the age of its code.
_LEGACY_FACTS = (
    DispatchFact.UNSPECIFIED,
    ResultFact.NOT_APPLICABLE,
    PostconditionFact.NOT_APPLICABLE,
    TransitionFact.NOT_APPLICABLE,
    FootprintFact.NOT_APPLICABLE,
    None,
)

#: Free text that reaches a stored snapshot or a public cause is bounded here.
#: Generated script bodies and page contents are orders of magnitude larger
#: than any diagnostic needs to be, so a bound is what keeps one out.
MUTATION_TEXT_LIMIT = 200


def _bounded(text: str) -> str:
    """Bound one free-text diagnostic field without hiding that it was cut."""
    value = str(text or "")
    if len(value) <= MUTATION_TEXT_LIMIT:
        return value
    return value[: MUTATION_TEXT_LIMIT - 1] + "\u2026"


def sanitized_mutation_snapshot(
    mutation: RuntimeActionMutation,
) -> RuntimeActionMutation:
    """Copy the exact classifier input, bounded, for later re-evaluation.

    TD-12.1. The public result carries decided outputs, so without this copy
    the tuple that was actually classified is gone and the only way back to it
    is reconstruction -- `applied` from `dispatch is ACCEPTED`, or from a
    derived status. Both are prohibited, because a reconstruction turns the
    inconsistent tuple ACCEPTED/CORRELATED/SATISFIED/CHANGED/COVERED/
    attempted=True/applied=False into row 12 and silently grants it a
    satisfied postcondition it never had.

    The copy is deep, so mutating the caller's object afterwards cannot reach
    it, and every free-text field is bounded. Nothing is dropped and nothing is
    renamed: it is the input, not a summary of it.
    """
    snapshot = mutation.model_copy(deep=True)
    return snapshot.model_copy(
        update={
            "message": _bounded(snapshot.message),
            "cause": _bounded(snapshot.cause),
            "call_error": _bounded(snapshot.call_error),
        },
    )


def _legacy_status(mutation: RuntimeActionMutation) -> ActionExecutionStatus:
    """Apply the baseline rule on `applied` and the given disposition."""
    if not mutation.applied:
        return ActionExecutionStatus.FAILED
    if mutation.disposition is MutationDisposition.NO_OP:
        return ActionExecutionStatus.NO_OP
    if mutation.disposition is MutationDisposition.REASSERTED:
        return ActionExecutionStatus.REASSERTED
    return ActionExecutionStatus.APPLIED


def _legacy_decision(mutation: RuntimeActionMutation) -> MutationDecision:
    """Row 16: a producer that stated no fact keeps the baseline mapping."""
    status = _legacy_status(mutation)
    if mutation.failure_code is not ConfigurationFailureCode.NONE:
        failure_code = mutation.failure_code
    elif mutation.applied:
        failure_code = ConfigurationFailureCode.NONE
    else:
        failure_code = ConfigurationFailureCode.APPLICATION_FAILED
    return MutationDecision(
        status=status,
        disposition=mutation.disposition,
        failure_code=failure_code,
        residue=MutationResidue.NONE,
        frontier=satisfies_apply_dependency(status),
        sticky=False,
        cause="",
        row="16",
    )


def _compose_cause(template: str, received: str) -> str:
    """Join the row's canonical reason with the producer's detail, once.

    The table writes causes like `rejected:<code>` and `post_read_failed`
    (+ `call_error`): the canonical token is the row's, the detail is the
    producer's. A producer that already supplied the detailed form is not
    prefixed twice.
    """
    detail = _bounded(received)
    if not template:
        return detail
    if not detail:
        return template
    if detail == template or detail.startswith(template + ":"):
        return detail
    return _bounded(f"{template}:{detail}")


#: One admitted row: the decided outputs, the canonical cause template, and
#: the row name. Expanded into an exact tuple lookup below, so "matches
#: exactly one row" is a property of the table and not of the order in which
#: a chain of `if`s happens to be written.
_RowSpec = tuple[
    ActionExecutionStatus,
    MutationDisposition,
    ConfigurationFailureCode,
    MutationResidue,
    bool,
    bool,
    str,
    str,
]

_ROWS: dict[tuple, _RowSpec] = {}


def _admit(
    dispatch: DispatchFact,
    result: ResultFact | tuple[ResultFact, ...],
    postcondition: PostconditionFact,
    transition: TransitionFact | tuple[TransitionFact, ...],
    footprint: FootprintFact | tuple[FootprintFact, ...],
    attempted: bool | tuple[bool | None, ...] | None,
    applied: bool,
    *,
    status: ActionExecutionStatus,
    disposition: MutationDisposition,
    failure_code: ConfigurationFailureCode,
    residue: MutationResidue,
    frontier: bool,
    sticky: bool,
    cause: str = "",
    row: str,
) -> None:
    """Register one table row, refusing any tuple two rows would both claim."""

    def spread(value):
        return value if isinstance(value, tuple) else (value,)

    for one_result in spread(result):
        for one_transition in spread(transition):
            for one_footprint in spread(footprint):
                for one_attempted in spread(attempted):
                    key = (
                        dispatch,
                        one_result,
                        postcondition,
                        one_transition,
                        one_footprint,
                        one_attempted,
                        applied,
                    )
                    if key in _ROWS:
                        raise ValueError(f"row {row} overlaps an admitted tuple")
                    _ROWS[key] = (
                        status,
                        disposition,
                        failure_code,
                        residue,
                        frontier,
                        sticky,
                        cause,
                        row,
                    )


_admit(
    DispatchFact.NOT_SUBMITTED,
    ResultFact.NOT_APPLICABLE,
    PostconditionFact.NOT_APPLICABLE,
    TransitionFact.NOT_APPLICABLE,
    FootprintFact.NOT_APPLICABLE,
    None,
    False,
    status=ActionExecutionStatus.FAILED,
    disposition=MutationDisposition.FAILED,
    failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
    residue=MutationResidue.NONE,
    frontier=False,
    sticky=False,
    cause="not_submitted",
    row="1",
)
_admit(
    DispatchFact.REJECTED,
    ResultFact.NOT_APPLICABLE,
    PostconditionFact.NOT_APPLICABLE,
    TransitionFact.NOT_APPLICABLE,
    FootprintFact.NOT_APPLICABLE,
    None,
    False,
    status=ActionExecutionStatus.FAILED,
    disposition=MutationDisposition.FAILED,
    failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
    residue=MutationResidue.NONE,
    frontier=False,
    sticky=False,
    cause="rejected",
    row="2",
)
_admit(
    DispatchFact.ACCEPTANCE_UNKNOWN,
    ResultFact.NOT_OBSERVED,
    PostconditionFact.UNOBSERVED,
    TransitionFact.UNOBSERVED,
    FootprintFact.NOT_APPLICABLE,
    None,
    False,
    status=ActionExecutionStatus.UNKNOWN,
    disposition=MutationDisposition.UNKNOWN,
    failure_code=ConfigurationFailureCode.OUTCOME_UNKNOWN,
    residue=MutationResidue.UNKNOWN,
    frontier=False,
    sticky=True,
    row="3",
)
_admit(
    DispatchFact.ACCEPTED,
    (ResultFact.NOT_OBSERVED, ResultFact.LOST),
    PostconditionFact.UNOBSERVED,
    TransitionFact.UNOBSERVED,
    FootprintFact.NOT_APPLICABLE,
    None,
    True,
    status=ActionExecutionStatus.APPLIED,
    disposition=MutationDisposition.UNKNOWN,
    failure_code=ConfigurationFailureCode.OUTCOME_UNKNOWN,
    residue=MutationResidue.UNKNOWN,
    frontier=False,
    sticky=True,
    row="4",
)
_admit(
    DispatchFact.ACCEPTED,
    ResultFact.ENGINE_ERROR,
    PostconditionFact.UNOBSERVED,
    TransitionFact.UNOBSERVED,
    FootprintFact.NOT_APPLICABLE,
    None,
    True,
    status=ActionExecutionStatus.APPLIED,
    disposition=MutationDisposition.UNKNOWN,
    failure_code=ConfigurationFailureCode.OUTCOME_UNKNOWN,
    residue=MutationResidue.UNKNOWN,
    frontier=False,
    sticky=True,
    cause="engine_error",
    row="5",
)
_admit(
    DispatchFact.ACCEPTED,
    ResultFact.MALFORMED,
    PostconditionFact.UNOBSERVED,
    TransitionFact.UNOBSERVED,
    FootprintFact.NOT_APPLICABLE,
    None,
    True,
    status=ActionExecutionStatus.APPLIED,
    disposition=MutationDisposition.UNKNOWN,
    failure_code=ConfigurationFailureCode.RESPONSE_MALFORMED,
    residue=MutationResidue.UNKNOWN,
    frontier=False,
    sticky=True,
    row="6",
)
_admit(
    DispatchFact.ACCEPTED,
    ResultFact.CORRELATED,
    PostconditionFact.UNOBSERVED,
    TransitionFact.UNOBSERVED,
    FootprintFact.NOT_APPLICABLE,
    None,
    True,
    status=ActionExecutionStatus.APPLIED,
    disposition=MutationDisposition.UNKNOWN,
    failure_code=ConfigurationFailureCode.RESPONSE_MALFORMED,
    residue=MutationResidue.UNKNOWN,
    frontier=False,
    sticky=True,
    row="7",
)
_admit(
    DispatchFact.ACCEPTED,
    ResultFact.CORRELATED,
    PostconditionFact.UNOBSERVED,
    TransitionFact.UNOBSERVED,
    (FootprintFact.COVERED, FootprintFact.PARTIAL),
    (True, False),
    True,
    status=ActionExecutionStatus.APPLIED,
    disposition=MutationDisposition.UNKNOWN,
    failure_code=ConfigurationFailureCode.OUTCOME_UNKNOWN,
    residue=MutationResidue.UNKNOWN,
    frontier=False,
    sticky=True,
    cause="post_read_failed",
    row="8",
)
_admit(
    DispatchFact.ACCEPTED,
    ResultFact.CORRELATED,
    PostconditionFact.SATISFIED,
    TransitionFact.UNOBSERVED,
    (FootprintFact.COVERED, FootprintFact.PARTIAL),
    True,
    True,
    status=ActionExecutionStatus.APPLIED,
    disposition=MutationDisposition.UNKNOWN,
    failure_code=ConfigurationFailureCode.NONE,
    residue=MutationResidue.UNKNOWN,
    frontier=True,
    sticky=False,
    cause="pre_read_failed",
    row="9",
)
_admit(
    DispatchFact.ACCEPTED,
    ResultFact.CORRELATED,
    PostconditionFact.UNSATISFIED,
    TransitionFact.UNOBSERVED,
    (FootprintFact.COVERED, FootprintFact.PARTIAL),
    True,
    True,
    status=ActionExecutionStatus.PARTIAL,
    disposition=MutationDisposition.UNKNOWN,
    failure_code=ConfigurationFailureCode.POSTCONDITION_UNSATISFIED,
    residue=MutationResidue.UNKNOWN,
    frontier=False,
    sticky=True,
    cause="pre_read_failed",
    row="10",
)
_admit(
    DispatchFact.ACCEPTED,
    ResultFact.CORRELATED,
    PostconditionFact.SATISFIED,
    TransitionFact.UNCHANGED,
    FootprintFact.COVERED,
    True,
    True,
    status=ActionExecutionStatus.REASSERTED,
    disposition=MutationDisposition.REASSERTED,
    failure_code=ConfigurationFailureCode.NONE,
    residue=MutationResidue.NONE,
    frontier=True,
    sticky=False,
    row="11",
)
_admit(
    DispatchFact.ACCEPTED,
    ResultFact.CORRELATED,
    PostconditionFact.SATISFIED,
    TransitionFact.CHANGED,
    FootprintFact.COVERED,
    True,
    True,
    status=ActionExecutionStatus.APPLIED,
    disposition=MutationDisposition.CHANGED,
    failure_code=ConfigurationFailureCode.NONE,
    residue=MutationResidue.NONE,
    frontier=True,
    sticky=False,
    row="12",
)
_admit(
    DispatchFact.ACCEPTED,
    ResultFact.CORRELATED,
    PostconditionFact.UNSATISFIED,
    TransitionFact.UNCHANGED,
    FootprintFact.COVERED,
    True,
    True,
    status=ActionExecutionStatus.PARTIAL,
    disposition=MutationDisposition.FAILED,
    failure_code=ConfigurationFailureCode.POSTCONDITION_UNSATISFIED,
    residue=MutationResidue.NONE,
    frontier=False,
    sticky=False,
    row="13",
)
_admit(
    DispatchFact.ACCEPTED,
    ResultFact.CORRELATED,
    PostconditionFact.UNSATISFIED,
    TransitionFact.CHANGED,
    FootprintFact.COVERED,
    True,
    True,
    status=ActionExecutionStatus.PARTIAL,
    disposition=MutationDisposition.FAILED,
    failure_code=ConfigurationFailureCode.POSTCONDITION_UNSATISFIED,
    residue=MutationResidue.CHANGED,
    frontier=False,
    sticky=False,
    row="14",
)
_admit(
    DispatchFact.UNSPECIFIED,
    ResultFact.NOT_APPLICABLE,
    PostconditionFact.UNOBSERVED,
    TransitionFact.UNOBSERVED,
    FootprintFact.NOT_APPLICABLE,
    None,
    False,
    status=ActionExecutionStatus.UNKNOWN,
    disposition=MutationDisposition.UNKNOWN,
    failure_code=ConfigurationFailureCode.SESSION_FAILED,
    residue=MutationResidue.UNKNOWN,
    frontier=False,
    sticky=True,
    cause="exception",
    row="15",
)
_admit(
    DispatchFact.ACCEPTED,
    ResultFact.CORRELATED,
    PostconditionFact.SATISFIED,
    TransitionFact.UNCHANGED,
    FootprintFact.COVERED,
    False,
    True,
    status=ActionExecutionStatus.NO_OP,
    disposition=MutationDisposition.NO_OP,
    failure_code=ConfigurationFailureCode.NONE,
    residue=MutationResidue.NONE,
    frontier=True,
    sticky=False,
    cause="skipped:already_satisfied",
    row="17",
)
_admit(
    DispatchFact.ACCEPTED,
    ResultFact.CORRELATED,
    PostconditionFact.SATISFIED,
    (TransitionFact.CHANGED, TransitionFact.UNCHANGED),
    FootprintFact.PARTIAL,
    True,
    True,
    status=ActionExecutionStatus.APPLIED,
    disposition=MutationDisposition.UNKNOWN,
    failure_code=ConfigurationFailureCode.NONE,
    residue=MutationResidue.UNKNOWN,
    frontier=True,
    sticky=False,
    cause="footprint_partial",
    row="18",
)
_admit(
    DispatchFact.ACCEPTED,
    ResultFact.CORRELATED,
    PostconditionFact.UNSATISFIED,
    (TransitionFact.CHANGED, TransitionFact.UNCHANGED),
    FootprintFact.PARTIAL,
    True,
    True,
    status=ActionExecutionStatus.PARTIAL,
    disposition=MutationDisposition.UNKNOWN,
    failure_code=ConfigurationFailureCode.POSTCONDITION_UNSATISFIED,
    residue=MutationResidue.UNKNOWN,
    frontier=False,
    sticky=True,
    cause="footprint_partial",
    row="19",
)
_admit(
    DispatchFact.ACCEPTED,
    ResultFact.CORRELATED,
    PostconditionFact.UNOBSERVED,
    TransitionFact.NOT_APPLICABLE,
    FootprintFact.NOT_APPLICABLE,
    False,
    True,
    status=ActionExecutionStatus.FAILED,
    disposition=MutationDisposition.FAILED,
    failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
    residue=MutationResidue.NONE,
    frontier=False,
    sticky=False,
    cause="not_attempted:family_not_implemented",
    row="20",
)


#: Everything the table does not admit. The received fields stay on the result
#: as diagnostics and grant nothing: the cause is exactly `inconsistent_facts`
#: and is never composed with the producer's string, so an incidental error
#: message cannot stand where the classification belongs.
_INCONSISTENT = MutationDecision(
    status=ActionExecutionStatus.UNKNOWN,
    disposition=MutationDisposition.UNKNOWN,
    failure_code=ConfigurationFailureCode.OUTCOME_UNKNOWN,
    residue=MutationResidue.UNKNOWN,
    frontier=False,
    sticky=True,
    cause="inconsistent_facts",
    row="inconsistent",
)


def decide_mutation(mutation: RuntimeActionMutation) -> MutationDecision:
    """Map one fact tuple to one product outcome. The only such mapping.

    Evaluated in this order, and the order is the contract:

    1. legacy detection -- a mutation whose every new fact is at its default
       stated no fact, so it selects row 16 and the baseline rule;
    2. admission -- the tuple must match exactly one listed row;
    3. everything else is inconsistent.

    Step 3 is what makes `applied` worth retaining. A tuple whose `applied`
    disagrees with `dispatch is ACCEPTED`, a SATISFIED postcondition under a
    dispatch that was never accepted, or a CORRELATED result without
    acceptance are all contradictions, and a contradiction is UNKNOWN, closed
    and sticky -- not whichever half of it happens to be read first.
    """
    facts = (
        mutation.dispatch,
        mutation.result,
        mutation.postcondition,
        mutation.transition,
        mutation.footprint,
        mutation.attempted,
    )
    if facts == _LEGACY_FACTS:
        return _legacy_decision(mutation)
    spec = _ROWS.get((*facts, mutation.applied))
    if spec is None:
        return _INCONSISTENT
    status, disposition, failure_code, residue, frontier, sticky, template, row = spec
    return MutationDecision(
        status=status,
        disposition=disposition,
        failure_code=failure_code,
        residue=residue,
        frontier=frontier,
        sticky=sticky,
        cause=_compose_cause(template, mutation.cause),
        row=row,
    )


def mutation_execution_status(
    mutation: RuntimeActionMutation,
) -> ActionExecutionStatus:
    """Estado de ejecución de una mutación despachada. Una sola definición.

    Vivía duplicada, idéntica, en cinco applicators.

    `APPLIED` acá significa DESPACHADO POR EL CANAL DEL RUNTIME, no "el backend
    confirmó el efecto". No es una laxitud heredada: es el contrato que la
    arquitectura fija de forma explícita.

        docs/architecture/e95-stabilization.md   compiled != applied
                                                 applied  != observed
        docs/architecture/enterprise-control-plane.md
            "A result may be APPLIED and still be UNOBSERVABLE."

    Por eso el canal de configuración puede ser asíncrono sin mentir: el envío
    sostiene APPLIED y nada más. Quien afirma el efecto es la verificación, que
    relee el estado y produce VERIFIED, y ningún camino promueve lo uno a lo
    otro. Colapsar los dos estados en uno "más conservador" no agregaría
    seguridad -- borraría la distinción que ya los mantiene separados.

    `applied=False` sí es una certeza local: el payload no salió del proceso,
    así que no puede aplicarse más tarde.

    Since S0 this is a projection of `decide_mutation`, not a second rule. It
    stays the status entry point for a baseline caller, and for a legacy row --
    every new fact at its default -- the decision reproduces exactly the
    mapping this docstring describes. A caller that needs the frontier, the
    residue or the sticky flag must ask for the decision itself: those are not
    derivable from the status.
    """
    return decide_mutation(mutation).status


class RuntimeVerification(BaseModel):
    """What a runtime reports about one verification read."""

    expectation_id: str
    status: ActionExecutionStatus
    evidence_method: str = ""
    fresh_evidence: bool = False
    fields: dict[str, FieldVerificationStatus] = Field(default_factory=dict)
    message: str = ""
    convergence: ConvergenceReport | None = None


class ActionApplicationResult(BaseModel):
    """The applicator's decided outcome for one action.

    Three kinds of field live here and they are not interchangeable: the
    observations the runtime reported, the outputs the canonical decision
    produced from them, and -- for a fact-bearing row -- the retained input
    the decision was actually given.
    """

    action_id: str
    status: ActionExecutionStatus
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE
    message: str = ""
    batch_id: str = ""
    operation: OperationSemantics = OperationSemantics.SET_VALUE
    disposition: MutationDisposition = MutationDisposition.UNKNOWN
    #: Received observations, kept as reported.
    dispatch: DispatchFact = DispatchFact.UNSPECIFIED
    result: ResultFact = ResultFact.NOT_APPLICABLE
    postcondition: PostconditionFact = PostconditionFact.NOT_APPLICABLE
    transition: TransitionFact = TransitionFact.NOT_APPLICABLE
    footprint: FootprintFact = FootprintFact.NOT_APPLICABLE
    attempted: bool | None = None
    #: Decision outputs. `residual_change` is True only for an OBSERVED
    #: unintended change; False is the absence of that observation and never a
    #: claim that nothing changed. `cause` is the decision's canonical
    #: classification reason, which for an inconsistent tuple is exactly
    #: `inconsistent_facts` -- the producer's own string stays in
    #: `received_mutation` so it cannot stand in for the classification.
    residual_change: bool = False
    cause: str = ""
    #: TD-12.1: the exact typed mutation the decision classified, copied
    #: defensively and bounded. Optional, so baseline-shaped JSON still
    #: validates and an old producer need not populate it. A stored result
    #: without it is a legacy record: it gains no fact-bearing authority by
    #: inference, and `applied` is never fabricated for it.
    received_mutation: RuntimeActionMutation | None = None


class VerificationResult(BaseModel):
    """One verification outcome bound to the action it observes."""

    expectation_id: str
    action_id: str
    status: ActionExecutionStatus
    evidence_method: str = ""
    fresh_evidence: bool = False
    fields: dict[str, FieldVerificationStatus] = Field(default_factory=dict)
    message: str = ""
    convergence: ConvergenceReport | None = None


class VoiceSignalBarrierResult(BaseModel):
    """Typed evidence for data-only preparation and late Voice signalling."""

    required: bool = False
    deferred_action_ids: list[str] = Field(default_factory=list)
    foundation_expectation_ids: list[str] = Field(default_factory=list)
    preparation_results: list[ActionApplicationResult] = Field(
        default_factory=list,
    )
    foundation_verification_results: list[VerificationResult] = Field(
        default_factory=list,
    )
    signal_results: list[ActionApplicationResult] = Field(
        default_factory=list,
    )
    post_signal_convergence_results: list[VerificationResult] = Field(
        default_factory=list,
    )
    foundation_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    signal_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    message: str = ""

    def compact_summary(self) -> dict[str, object]:
        """Return the stable barrier report shape; consumers depend on it."""
        return {
            "required": self.required,
            "deferred_action_ids": self.deferred_action_ids,
            "foundation_expectation_ids": self.foundation_expectation_ids,
            "preparation_statuses": {
                item.action_id: item.status.value for item in self.preparation_results
            },
            "foundation_status": self.foundation_status.value,
            "signal_status": self.signal_status.value,
            "message": self.message,
        }


class ConfigurationApplicationResult(BaseModel):
    """Full typed outcome of one configuration application."""

    config_plan_id: str
    config_semantic_hash: str
    source_topology_hash: str
    runtime_context: ConfigurationRuntimeContext = Field(
        default_factory=ConfigurationRuntimeContext,
    )
    status: ConfigurationApplicationStatus
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE
    action_results: list[ActionApplicationResult] = Field(default_factory=list)
    mutation_action_ids: list[str] = Field(default_factory=list)
    retained_action_ids: list[str] = Field(default_factory=list)
    verification_results: list[VerificationResult] = Field(default_factory=list)
    preflight_errors: list[str] = Field(default_factory=list)
    deployment_id: str = ""
    execution_journal: ApplicationExecutionJournal | None = None
    dirty_state: DirtyState = DirtyState.CLEAN
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    voice_signal_barrier: VoiceSignalBarrierResult | None = None
    duration_ms: int = 0

    def compact_summary(self) -> dict[str, object]:
        """Return the stable report shape; consumers depend on these keys."""
        action_counts: dict[str, int] = {}
        for item in self.action_results:
            action_counts[item.status.value] = (
                action_counts.get(item.status.value, 0) + 1
            )
        verification_counts: dict[str, int] = {}
        for item in self.verification_results:
            verification_counts[item.status.value] = (
                verification_counts.get(item.status.value, 0) + 1
            )
        return {
            "config_plan_id": self.config_plan_id,
            "config_semantic_hash": self.config_semantic_hash,
            "source_topology_hash": self.source_topology_hash,
            "runtime_context": self.runtime_context.model_dump(mode="json"),
            "status": self.status.value,
            "failure_code": self.failure_code.value,
            "actions": dict(sorted(action_counts.items())),
            "mutation_action_ids": self.mutation_action_ids,
            "retained_action_ids": self.retained_action_ids,
            "verification": dict(sorted(verification_counts.items())),
            "preflight_errors": self.preflight_errors,
            "deployment_id": self.deployment_id,
            "dirty_state": self.dirty_state.value,
            "execution_journal": (
                self.execution_journal.compact_summary()
                if self.execution_journal
                else None
            ),
            "evidence_records": [
                item.compact_summary() for item in self.evidence_records
            ],
            "voice_signal_barrier": (
                self.voice_signal_barrier.compact_summary()
                if self.voice_signal_barrier is not None
                else None
            ),
            "duration_ms": self.duration_ms,
        }
