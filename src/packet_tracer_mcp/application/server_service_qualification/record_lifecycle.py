"""The write-ahead record lifecycle of one admitted invocation.

The initial record is built before contact. Every step boundary is written
ahead of the work it announces, the ledger is synchronized into the record
before each write, and a persistence failure closes the effect gate instead
of raising.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from ...domain.enterprise.models.execution import DirtyState
from ...domain.enterprise.models.service_qualification import (
    BudgetRecord,
    DiagnosticLifecycleObservation,
    EnvironmentIdentity,
    FixtureRecord,
    MeasurementRecord,
    MeasurementStatus,
    QualificationOutcome,
    QualificationRecord,
    QualificationRefusal,
    QualificationRequest,
    QualificationTransition,
    RepositoryIdentity,
    SourceIdentity,
    StageDefinition,
)
from ..ports.service_run_record import RunRecordPersistenceError
from .campaign_authority import CampaignHold
from .contracts import (
    IsolationObservation,
    QualificationBoundaries,
    QualificationResult,
    RuntimeIdentity,
    bounded,
    refused_result,
)
from .operation_budget import OperationLedger


def initial_record(
    request: QualificationRequest,
    definition: StageDefinition,
    boundaries: QualificationBoundaries,
    isolation: IsolationObservation,
    repository: RepositoryIdentity,
    capabilities: frozenset[str],
    *,
    moment: datetime | None = None,
    run_id: str = "",
    diagnostic_lifecycle: DiagnosticLifecycleObservation | None = None,
) -> QualificationRecord:
    """Build the write-ahead record of one invocation before any contact."""
    moment = moment or boundaries.now()
    try:
        runtime = boundaries.runtime_identity()
    except Exception:
        runtime = RuntimeIdentity("", "")
    authorization = request.authorization
    measurements = [
        MeasurementRecord(
            experiment_id=item.id,
            hypothesis=item.hypothesis,
            required=item.required,
            status=(
                MeasurementStatus.OMITTED
                if item.omission_reason
                else MeasurementStatus.NOT_RUN
            ),
            reason=item.omission_reason,
        )
        for item in definition.experiments
    ]
    return QualificationRecord(
        run_id=run_id or boundaries.new_run_id(moment),
        stage=definition.stage,
        execution_mode=boundaries.execution_mode,
        created_at=moment,
        authorization=(
            {**asdict(authorization), "targets": list(authorization.targets)}
            if authorization is not None
            else {}
        ),
        source=SourceIdentity(
            expected_head=request.expected_head,
            executed_sha=repository.head,
            executed_tree=repository.tree,
            clean=repository.clean,
            branch=repository.branch,
            upstream=repository.upstream,
            upstream_head=repository.upstream_head,
        ),
        environment=EnvironmentIdentity(
            python_executable=runtime.python_executable,
            package_file=runtime.package_file,
            isolation_state=isolation.state,
            requested_build=request.packet_tracer_build,
        ),
        fixtures=[
            FixtureRecord(
                name=item.name,
                model=item.model,
                ipv4=item.ipv4,
                netmask=item.netmask,
                dns_server=item.dns_server,
            )
            for item in definition.fixtures
        ],
        budget=BudgetRecord(
            max_operations=definition.budget.max_operations,
            max_seconds=definition.budget.max_seconds,
            reserve_operations=definition.reserve_operations,
            reserve_seconds=definition.budget.reserve_seconds,
            planned_minimum_operations=definition.planned_minimum_operations,
        ),
        experimental_capabilities=sorted(capabilities),
        measurements=measurements,
        admission_reads=[
            f"isolation:{isolation.state}",
            f"repository:{repository.head}:{repository.tree}",
        ],
        diagnostic_lifecycle=(
            asdict(diagnostic_lifecycle) if diagnostic_lifecycle is not None else {}
        ),
    )


class Run:
    """The record lifecycle of one admitted invocation."""

    def __init__(
        self,
        record: QualificationRecord,
        boundaries: QualificationBoundaries,
        record_path: str,
        diagnostic_lifecycle: DiagnosticLifecycleObservation | None = None,
        hold: CampaignHold | None = None,
    ) -> None:
        """Bind the record, its store and the campaign hold it releases into."""
        self.record = record
        self.boundaries = boundaries
        self.record_path = record_path
        self.ledger: OperationLedger | None = None
        #: What the admission reading observed, kept so finalization can
        #: state whether that pairing is still the one it is describing.
        self.diagnostic_lifecycle = diagnostic_lifecycle
        self.hold = hold if hold is not None else CampaignHold()

    def sync(self) -> None:
        """Copy the ledger into the record before every write."""
        if self.ledger is None:
            return
        self.record.operations = list(self.ledger.entries)
        self.record.budget.used_operations = self.ledger.used
        self.record.budget.refused_calls = self.ledger.refused_calls
        self.record.budget.elapsed_seconds = round(self.ledger.elapsed(), 3)

    def transition(self, step: str, outcome: str = "") -> bool:
        """Write one step boundary ahead of the work it announces.

        A failed write closes the effect gate instead of raising: the primary
        error must survive, and bounded observation plus owned finalization
        still have to run.
        """
        previous = self.record.persisted_step
        self.record.transitions.append(
            QualificationTransition(
                step=step, at=self.boundaries.now(), outcome=outcome
            )
        )
        self.record.persisted_step = step
        self.sync()
        try:
            self.record_path = self.boundaries.record_store.advance(self.record)
        except RunRecordPersistenceError as exc:
            self.record.persisted_step = previous
            if not self.record.persist_error:
                self.record.persist_error = bounded(exc)
            self.record.limitations.append(f"persist_error:{step}")
            if self.ledger is not None:
                self.ledger.close_effects(f"record_not_advanced_past:{previous}")
            return False
        return True

    def complete(self, outcome: QualificationOutcome) -> None:
        """Write the terminal record; a failure is secondary."""
        self.record.outcome = outcome
        self.record.completed_at = self.boundaries.now()
        self.sync()
        try:
            self.record_path = self.boundaries.record_store.complete(self.record)
        except RunRecordPersistenceError as exc:
            if not self.record.persist_error:
                self.record.persist_error = bounded(exc)
            self.record.secondary_failures.append("record_completion_failed")

    def refuse_after_contact(self, reason: QualificationRefusal) -> QualificationResult:
        """Refuse once contact began but before any effect."""
        self.record.refusals.append(reason)
        self.record.dirty_state = DirtyState.CLEAN
        self.record.primary_failure = f"refused:{reason.subject.value}"
        claim_release = self.hold.finalize(self.record)
        self.complete(QualificationOutcome.REFUSED)
        return refused_result(
            [reason], self.record, self.record_path, claim_release=claim_release
        )
