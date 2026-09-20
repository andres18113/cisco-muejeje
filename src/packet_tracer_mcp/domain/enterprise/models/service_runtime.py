"""Resultados E6 reutilizando los estados de ejecución establecidos en E5."""

from __future__ import annotations

from enum import Enum, StrEnum

from pydantic import BaseModel, Field

from .configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
)
from .evidence import (
    EvidenceRecord,
    ObservationStatus,
    VerificationStatus,
    evidence_from_legacy_result,
)
from .execution import ApplicationExecutionJournal, DirtyState
from .service_plan import ServiceEvidenceKind, ServiceType


class ObservationFact(StrEnum):
    """What one verification read established, separately from its status.

    Status answers "may the product claim this expectation holds"; the
    observation answers "what did the read actually see". They are different
    questions, and collapsing them is how a read that never happened became
    indistinguishable from one that contradicted the expectation.

    CONTRADICTED is deliberately fresh NEGATIVE evidence: a completed read
    that saw the wrong value observed something real, and calling it stale
    discarded a genuine measurement. INCONCLUSIVE is a completed read that
    cannot decide -- output that predates the request, an incomplete window, a
    refused or unstarted command, no response by the deadline. The transport
    facts name a read that never arrived, and none of them is evidence that
    the subject is in any particular state. UNSPECIFIED is the default and
    means the producer stated no fact, which is how a legacy producer is
    recognized and routed to the legacy evidence mapping.
    """

    __str__ = Enum.__str__

    OBSERVED = "observed"
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"
    SUBJECT_NOT_FOUND = "subject_not_found"
    MALFORMED = "malformed"
    ENGINE_ERROR = "engine_error"
    NOT_OBSERVED = "not_observed"
    LOST = "lost"
    ACCEPTANCE_UNKNOWN = "acceptance_unknown"
    NOT_SUBMITTED = "not_submitted"
    REJECTED = "rejected"
    NOT_ATTEMPTED = "not_attempted"
    UNSPECIFIED = "unspecified"


class RuntimeObservationStep(BaseModel):
    """One attempted observation inside a longer read, kept in order.

    A read that samples more than once used to keep only the sample it
    returned on. Every attempt is retained here with what it dispatched, what
    came back and when, so a reader can tell a sample that was never taken
    from one that was taken and saw nothing. A slot the schedule named but the
    read could not perform is recorded with `performed` false; it is never
    fabricated and never replayed later as a burst.
    """

    index: int
    label: str
    performed: bool = True
    dispatch: str = ""
    result: str = ""
    outcome: str = ""
    #: Monotonic seconds since the request this read is about was started.
    offset_seconds: float = 0.0
    #: What the caller's budget still allowed when this step ran, when the
    #: runtime was given a reader for it. `budget_observed` keeps a missing
    #: reader apart from an exhausted budget.
    budget_observed: bool = False
    remaining_operations: int = 0
    remaining_seconds: float = 0.0
    content_length: int = 0
    content_changed: bool = False
    marker_present: bool = False
    detail: str = ""


class RuntimeServiceVerification(BaseModel):
    """What a service runtime reports about one expectation."""

    expectation_id: str
    status: ActionExecutionStatus
    evidence_kind: ServiceEvidenceKind
    evidence_method: str = ""
    fresh_evidence: bool = False
    observed: dict[str, str | int | bool] = Field(default_factory=dict)
    #: Every attempted observation of this read, in order. Empty for readers
    #: that observe exactly once.
    trace: list[RuntimeObservationStep] = Field(default_factory=list)
    message: str = ""
    #: What the read established. UNSPECIFIED is the default and means the
    #: producer stated no fact; it never means OBSERVED.
    observation: ObservationFact = ObservationFact.UNSPECIFIED
    #: Why the observation is what it is, sanitized and bounded.
    cause: str = ""
    #: How strong a claim this row supports, when the runtime can say.
    claim_level: str = ""
    #: What this read could not establish. A limitation is part of the record,
    #: not a footnote: an empty-marker HTTPS fetch is PARTIAL because of one.
    limitations: list[str] = Field(default_factory=list)


class ServiceVerificationResult(RuntimeServiceVerification):
    """A runtime verification bound to its service, with a failure code."""

    service_id: str
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE


class ServiceOutcome(BaseModel):
    """The four separate status axes of one service."""

    service_id: str
    service_type: ServiceType
    application_status: ActionExecutionStatus
    direct_readback_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    behavioral_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    usability_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN


class ServiceApplicationResult(BaseModel):
    """Full typed outcome of one service application."""

    service_plan_id: str
    service_semantic_hash: str
    source_topology_hash: str
    source_configuration_hash: str
    runtime_context: ConfigurationRuntimeContext = Field(
        default_factory=ConfigurationRuntimeContext
    )
    status: ConfigurationApplicationStatus
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE
    action_results: list[ActionApplicationResult] = Field(default_factory=list)
    verification_results: list[ServiceVerificationResult] = Field(default_factory=list)
    services: list[ServiceOutcome] = Field(default_factory=list)
    preflight_errors: list[str] = Field(default_factory=list)
    deployment_id: str = ""
    execution_journal: ApplicationExecutionJournal | None = None
    dirty_state: DirtyState = DirtyState.CLEAN
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    #: What this run could not establish, one entry per unresolved item. A
    #: `residue_unknown:<id>:<cause>` entry names an action whose residue the
    #: observation could not settle; the run may still be VERIFIED, because a
    #: satisfied postcondition and an unobserved residue are different claims.
    limitations: list[str] = Field(default_factory=list)
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
            "service_plan_id": self.service_plan_id,
            "service_semantic_hash": self.service_semantic_hash,
            "source_topology_hash": self.source_topology_hash,
            "source_configuration_hash": self.source_configuration_hash,
            "runtime_context": self.runtime_context.model_dump(mode="json"),
            "status": self.status.value,
            "failure_code": self.failure_code.value,
            "actions": dict(sorted(action_counts.items())),
            "verification": dict(sorted(verification_counts.items())),
            "services": [item.model_dump(mode="json") for item in self.services],
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
            "duration_ms": self.duration_ms,
        }


#: Observation facts that name a transport that never delivered a correlated
#: read, plus the completed-but-undecided read. Each becomes a probe failure
#: with the fact named in `limitations`, never an absence of evidence that
#: could be mistaken for "not attempted".
_TRANSPORT_FACTS = {
    ObservationFact.NOT_OBSERVED,
    ObservationFact.LOST,
    ObservationFact.ACCEPTANCE_UNKNOWN,
    ObservationFact.INCONCLUSIVE,
}

#: The read could not observe its subject at all.
_UNOBSERVABLE_FACTS = {
    ObservationFact.ENGINE_ERROR,
    ObservationFact.MALFORMED,
    ObservationFact.SUBJECT_NOT_FOUND,
}

#: Explicitly nothing was attempted for this subject.
_NOT_ATTEMPTED_FACTS = {
    ObservationFact.NOT_ATTEMPTED,
    ObservationFact.NOT_SUBMITTED,
    ObservationFact.REJECTED,
}


def evidence_from_service_verification(
    result: RuntimeServiceVerification,
    *,
    identifier: str,
    subject: str,
    claim: str,
    backend: str = "",
    backend_version: str = "",
    environment_fingerprint: str = "",
    capability_snapshot_hash: str = "",
) -> EvidenceRecord:
    """Build one evidence record from a verification that stated its fact.

    A producer that stated no fact (observation UNSPECIFIED) is delegated to
    `evidence_from_legacy_result` verbatim, so an existing producer's records
    stay exactly what they were. Only an explicit fact takes this path, and it
    maps the fact rather than re-inferring it from the status: a status can be
    UNKNOWN for a lost result and for an undecidable window alike, and the
    evidence has to say which.
    """
    limitations = list(result.limitations)
    if result.message:
        limitations.append(result.message)
    if result.observation is ObservationFact.UNSPECIFIED:
        return evidence_from_legacy_result(
            identifier=identifier,
            subject=subject,
            claim=claim,
            status=result.status,
            evidence_method=result.evidence_method,
            fresh_evidence=result.fresh_evidence,
            observed_value=result.observed,
            backend=backend,
            backend_version=backend_version,
            environment_fingerprint=environment_fingerprint,
            capability_snapshot_hash=capability_snapshot_hash,
            limitations=limitations,
        )
    if result.cause:
        limitations.append(f"cause:{result.cause}")
    if result.observation in _TRANSPORT_FACTS:
        limitations.append(f"transport:{result.observation.value}")
    record = evidence_from_legacy_result(
        identifier=identifier,
        subject=subject,
        claim=claim,
        status=result.status,
        evidence_method=result.evidence_method,
        fresh_evidence=result.fresh_evidence,
        observed_value=result.observed,
        backend=backend,
        backend_version=backend_version,
        environment_fingerprint=environment_fingerprint,
        capability_snapshot_hash=capability_snapshot_hash,
        limitations=limitations,
    )
    if result.observation in {ObservationFact.OBSERVED, ObservationFact.CONTRADICTED}:
        observation_status = ObservationStatus.OBSERVED
    elif (
        result.observation in _UNOBSERVABLE_FACTS
        or result.observation in _TRANSPORT_FACTS
    ):
        observation_status = ObservationStatus.PROBE_FAILED
    elif result.observation in _NOT_ATTEMPTED_FACTS:
        observation_status = ObservationStatus.NOT_ATTEMPTED
    else:
        observation_status = record.observation_status
    verification_status = (
        VerificationStatus.VERIFIED
        if result.status is ActionExecutionStatus.VERIFIED and result.fresh_evidence
        else VerificationStatus.FAILED
        if result.observation is ObservationFact.CONTRADICTED
        else VerificationStatus.UNVERIFIED
    )
    return record.model_copy(
        update={
            "observation_status": observation_status,
            "verification_status": verification_status,
        },
    )
