"""The single mutable context of one admitted qualification invocation.

It holds what the run owns, has concluded and has left behind, applies the
measurement admission and stop rules, and registers the stage's terminal
observation for guaranteed finalization. It imports no workflow and no
finalization code.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from ...domain.enterprise.models.physical_deployment import PhysicalWorkspaceObservation
from ...domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
    ExperimentSpec,
    MeasurementConclusion,
    MeasurementRecord,
    MeasurementStatus,
    QualificationRecord,
    StageDefinition,
)
from ...domain.enterprise.services.service_qualification_evidence import Assessment
from ...domain.models.plans import DevicePlan, LinkPlan
from ..use_cases.deploy_enterprise_topology import PhysicalTopologyRuntime
from .campaign_authority import CampaignHold, ExecutionAuthority
from .contracts import Q3ProductContract, bounded
from .ledgered_transport import LedgeredTransport
from .operation_budget import LedgerPhase, OperationLedger, OperationRefused
from .record_lifecycle import Run

#: Why a measurement the authority scoped out did not run. It is the one
#: omission reason that does not keep a stage from completing: the run did
#: everything it was authorized to do.
NOT_SELECTED = "not_selected_by_authorization"


@dataclass(frozen=True)
class TerminalPhase:
    """One stage's terminal read-only observation, and what it measures.

    It is registered before the stage's first procedure, over the state object
    the procedures fill in, so the reading still has the baseline, the ordered
    interventions and the declared call footprint it needs to be interpreted
    even when the sequence raised out of the middle of itself.
    """

    ids: tuple[str, ...]
    procedure: str
    observe: Callable[[], None]


@dataclass
class Execution:
    """What one admitted run owns, has concluded and has left behind."""

    run: Run
    nonce: str
    definition: StageDefinition
    devices: tuple[DevicePlan, ...]
    links: tuple[LinkPlan, ...]
    bound: LedgeredTransport
    physical: PhysicalTopologyRuntime
    baseline: PhysicalWorkspaceObservation
    channel: str
    capabilities: frozenset[str]
    probes: Any
    product_contract: Q3ProductContract | None = None
    #: The campaign claim this invocation holds, or None for a stage that
    #: declares no diagnostic profile. It is re-verified before effects.
    claim: Any | None = None
    #: The releasable hold over that claim. Finalization releases it before
    #: the record is completed; the caller's outer path only mops up.
    hold: CampaignHold = field(default_factory=CampaignHold)
    #: The steps this invocation's authority selected, in stage order. Empty
    #: for a stage that declares none, where every procedure runs.
    authorized_steps: tuple[str, ...] = ()
    #: Operational preconditions this run has actually established, which is
    #: not the same thing as what its measurements concluded. A diagnostic
    #: step is admitted from this set; a negative experimental finding is the
    #: result the diagnostic exists to produce and never revokes a state the
    #: run did establish.
    established: set[str] = field(default_factory=set)
    removal_candidates: list[DevicePlan] = field(default_factory=list)
    fixtures_ready: bool = False
    #: Run-bag state the finalizer must release. A collision means the run key
    #: is not exclusively ours, and then nothing under it is deleted.
    bag_touched: bool = False
    bag_unreleased: set[str] = field(default_factory=set)
    bag_collision: bool = False
    observers_unresolved: set[str] = field(default_factory=set)
    in_flight: tuple[str, ...] = ()
    e5_accepted: bool = False
    #: The stage's terminal read-only phase, registered before its first
    #: procedure and taken exactly once from guaranteed finalization.
    terminal: TerminalPhase | None = None
    terminal_taken: bool = False
    #: Whether the operator interrupted the run. A cancelled run stops doing
    #: work: it declares its terminal reading instead of taking it, and
    #: restarts no stimulus.
    cancelled: bool = False
    #: This invocation's live execution authority: the sticky first loss, a
    #: phase-local refusal to observe, and the local observation time spent.
    authority: ExecutionAuthority = field(init=False)

    def __post_init__(self) -> None:
        """Bind this execution's authority and effect guard before any dispatch.

        Binding here rather than at one call site is deliberate: an execution
        that exists over a ledger is the only thing that can answer for that
        ledger's effects, and a composition that forgot the step would
        otherwise refuse every effect it makes. The ledger still fails closed
        for anything that opens an effect scope without one.
        """
        self.authority = ExecutionAuthority(
            boundaries=self.run.boundaries,
            record=self.run.record,
            diagnostic=self.definition.profile_id != "",
            admitted_lifecycle=self.run.diagnostic_lifecycle,
            claim=self.claim,
        )
        ledger = self.run.ledger
        if ledger is not None:
            ledger.bind_effect_guard(self.effect_guard)

    @property
    def record(self) -> QualificationRecord:
        """Return the record under construction."""
        return self.run.record

    @property
    def default_pool_differences(self) -> list[str]:
        """Return every difference the run's default readings revealed.

        The readings live on the record, which is the one authoritative sink,
        so this stays true after a stop and after the procedure that took them
        has concluded.
        """
        seen: list[str] = []
        for entry in self.record.native_default_pool:
            for item in entry.differences:
                if item not in seen:
                    seen.append(item)
        return seen

    @property
    def ledger(self) -> OperationLedger:
        """Return the invocation ledger."""
        assert self.run.ledger is not None
        return self.run.ledger

    @property
    def stopped(self) -> bool:
        """Return whether new effects are no longer started."""
        return bool(self.record.primary_failure)

    def selected(self, step_id: str) -> bool:
        """Return whether the authority selected one diagnostic step.

        A stage that declares no steps selects everything it defines, which is
        what Q0/Q1/Q3 have always done. Selecting a step is permission to
        attempt it; it never bypasses the state the run must already have
        established, which the measurement prerequisites still decide.
        """
        if not self.definition.steps:
            return True
        return step_id in self.authorized_steps

    def stop(self, reason: str) -> None:
        """Keep the first stop reason as the primary failure."""
        if not self.record.primary_failure:
            self.record.primary_failure = bounded(reason)

    def establish(self, *preconditions: str) -> None:
        """Record that this run observed one operational precondition."""
        self.established.update(preconditions)

    def live_authority(self, moment: str, deadline: float | None = None) -> bool:
        """Re-decide whether this invocation still holds execution authority.

        The decision is `ExecutionAuthority.live`. Its phase deadline is the
        given absolute `deadline` or, when none is given, the ledger's
        deadline for the active phase, read only once an observation is
        needed. A loss stops the run through this execution's stop rule.
        """
        return self.authority.live(
            moment,
            (lambda: self.ledger.deadline())
            if deadline is None
            else (lambda: float(deadline)),
            self.stop,
        )

    def observe_lifecycle(
        self,
        lifecycle: Callable[[float | None], DiagnosticLifecycleObservation],
        deadline: float,
    ) -> DiagnosticLifecycleObservation:
        """Read and charge one local pairing under an absolute deadline."""
        return self.authority.observe_lifecycle(lifecycle, deadline)

    def effect_guard(self, purpose: str, deadline: float) -> str:
        """Return why this one effect may not be dispatched, or "".

        The ledger asks this immediately before it admits a call inside an
        effect scope, which is the narrowest point this process controls. It
        is not an in-band receiver fence: no existing dispatcher carries a
        session token the receiver itself verifies in the evaluation that
        mutates, so the interval between this answer and the receiver
        consuming the command stays unfenced and is declared as a limitation
        of every diagnostic record. What it does close is the case the
        finalizer used to cache away -- a receiver replaced between two
        removals, or between a cleanup pre-read and the delete that follows
        it -- because the replacement is already in the local process table
        when the next dispatch asks.
        """
        if self.live_authority(f"effect:{purpose}" if purpose else "effect", deadline):
            return ""
        return (
            self.authority.lost
            or self.authority.observation_refused
            or "execution_authority_lost"
        )

    def measurement(self, experiment_id: str) -> MeasurementRecord:
        """Return one measurement entry of the record."""
        return next(
            item
            for item in self.record.measurements
            if item.experiment_id == experiment_id
        )

    def interrupt_in_flight(self, reason: str) -> None:
        """Mark measurements that were running when the run was cut short."""
        for experiment_id in self.in_flight:
            item = self.measurement(experiment_id)
            if item.status is MeasurementStatus.NOT_RUN:
                item.status = MeasurementStatus.INTERRUPTED
                item.reason = bounded(reason)
                item.outcome_unknown = True
        self.in_flight = ()

    def not_run(self, ids: Sequence[str], reason: str) -> None:
        """Record why required work did not start."""
        for experiment_id in ids:
            item = self.measurement(experiment_id)
            if item.status is MeasurementStatus.NOT_RUN and not item.reason:
                item.reason = bounded(reason)

    def not_observed(self, ids: Sequence[str], cause: str) -> None:
        """Record why the terminal reading was not taken, over any earlier note.

        The terminal phase is a decision taken after the sequence ended, so
        its absence is its own statement. A generic earlier note -- the stage
        never reached this measurement -- is true about the sequence and says
        nothing about the reading finalization just declined, so the specific
        cause replaces it. The run-level primary failure is untouched and
        still names what actually stopped the run.
        """
        for experiment_id in ids:
            item = self.measurement(experiment_id)
            if item.status is MeasurementStatus.NOT_RUN:
                item.reason = bounded(f"not_observed:{cause}")

    def begin(self, ids: Sequence[str], procedure: str) -> bool:
        """Decide whether one procedure may start, and announce it durably."""
        if not self.live_authority(f"experiment:{procedure}"):
            reason = self.authority.lost or self.authority.observation_refused
            self.not_run(ids, f"execution_authority_unavailable:{reason}")
            return False
        return self.admissible(ids, procedure) and self.announce(ids, procedure)

    def register_terminal(
        self, ids: Sequence[str], procedure: str, observe: Callable[[], None]
    ) -> None:
        """Declare the stage's terminal reading before its first procedure.

        Registering is not taking. The reading is taken once, from guaranteed
        pre-cleanup finalization, whatever the sequence between here and there
        did -- completed, stopped, raised or lost its persistence.
        """
        self.terminal = TerminalPhase(tuple(ids), procedure, observe)

    def begin_terminal(self, ids: Sequence[str], procedure: str) -> bool:
        """Admit one read-only terminal observation, success or not.

        The final reading of a diagnostic is evidence about what the run left
        behind, so a primary failure is the reason to take it rather than a
        reason to skip it. What it still requires is everything that makes the
        reading meaningful and safe: the authorized subject and session, the
        operational state the measurement names, its capability scope, and the
        ordinary allowance -- never the finalization reserve, which belongs to
        cleanup alone. A reading that cannot satisfy those is recorded as an
        explicit absence with its cause instead of being silently dropped.
        """
        specs = [self.definition.experiment(item) for item in ids]
        if not all(item.terminal_observation for item in specs):
            return self.begin(ids, procedure)
        if not self.live_authority(f"terminal:{procedure}"):
            if self.authority.observation_refused:
                self.not_observed(ids, "time_budget_exhausted")
            else:
                self.not_observed(ids, f"authority_lost:{self.authority.lost}")
            return False
        reason = self._unmet(specs)
        if reason:
            self.not_observed(ids, reason)
            return False
        planned = sum(item.planned_operations for item in specs)
        if not self.ledger.can_afford(planned):
            self.not_observed(ids, f"unaffordable:{procedure}")
            return False
        # The boundary is still written ahead of the reading. A record that
        # cannot advance loses durability, not the observation: the reading is
        # kept in memory and the record says which of the two it is.
        if not self.run.transition(f"experiment:{procedure}:started"):
            self.record.limitations.append(
                f"terminal_observation_retained_in_memory_only:{bounded(procedure)}"
            )
        self.ledger.enter(LedgerPhase.TERMINAL_OBSERVATION)
        self.ledger.purpose = f"experiment:{procedure}"
        self.in_flight = tuple(ids)
        return True

    def admissible(
        self, ids: Sequence[str], procedure: str, extra_operations: int = 0
    ) -> bool:
        """Check stop state, prerequisites, capability scope and budget."""
        specs = [self.definition.experiment(item) for item in ids]
        if self.stopped:
            self.not_run(ids, f"stopped:{self.record.primary_failure}")
            return False
        reason = self._unmet(specs)
        if reason:
            self.not_run(ids, reason)
            return False
        planned = sum(item.planned_operations for item in specs) + extra_operations
        if not self.ledger.can_afford(planned):
            self.not_run(ids, f"budget_insufficient_for:{procedure}")
            self.stop(f"budget:{procedure}")
            return False
        return True

    def _unmet(self, specs: Sequence[ExperimentSpec]) -> str:
        """Return why these measurements may not be attempted, or "".

        A stage that declares a diagnostic profile is admitted from the
        operational state the run established; every other stage keeps the
        conclusion rule it always had, so no NEGATIVE or UNKNOWN prerequisite
        is admitted for Q0/Q1/Q3 or for any product caller.
        """
        diagnostic = bool(self.definition.profile_id)
        for spec in specs:
            if diagnostic:
                for precondition in spec.operational_prerequisites:
                    if precondition not in self.established:
                        return f"operational_precondition_unmet:{precondition}"
            else:
                for prerequisite in spec.prerequisites:
                    conclusion = self.measurement(prerequisite).conclusion
                    if conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
                        return f"prerequisite_unmet:{prerequisite}={conclusion.value}"
            missing = sorted(set(spec.capabilities) - self.capabilities)
            if missing:
                return "capability_not_in_scope:" + ",".join(missing)
        return ""

    def announce(self, ids: Sequence[str], procedure: str) -> bool:
        """Write the procedure boundary ahead of its first effect."""
        if self.stopped:
            self.not_run(ids, f"stopped:{self.record.primary_failure}")
            return False
        if not self.run.transition(f"experiment:{procedure}:started"):
            self.not_run(ids, "record_not_advanced")
            self.stop("persistence:record_not_advanced")
            return False
        self.ledger.enter(LedgerPhase.EXPERIMENT)
        self.ledger.purpose = f"experiment:{procedure}"
        self.in_flight = tuple(ids)
        return True

    def conclude(self, experiment_id: str, assessment: Assessment) -> None:
        """Store one assessment and apply the stop rules."""
        item = self.measurement(experiment_id)
        item.status = MeasurementStatus.RAN
        item.conclusion = assessment.conclusion
        item.facts = assessment.facts
        item.causes = assessment.causes
        item.limitations = assessment.limitations
        item.outcome_unknown = assessment.outcome_unknown
        self.in_flight = tuple(
            value for value in self.in_flight if value != experiment_id
        )
        if assessment.conclusion is MeasurementConclusion.CONTRADICTED:
            self.stop(f"contradiction:{experiment_id}")
        if assessment.outcome_unknown:
            self.stop(f"outcome_unknown:{experiment_id}")

    def finish(self, procedure: str) -> None:
        """Write the boundary after a procedure concluded."""
        self.ledger.purpose = ""
        if not self.run.transition(f"experiment:{procedure}:concluded"):
            self.stop("persistence:record_not_advanced")

    def settle(self) -> None:
        """Wait for asynchronous engine work, capped by the phase deadline."""
        self.ledger.wait(self.run.boundaries.settle_seconds, self.run.boundaries.sleep)

    @contextmanager
    def procedure(self, ids: Sequence[str]) -> Iterator[None]:
        """Turn a refused call inside a procedure into an interruption."""
        try:
            yield
        except OperationRefused as exc:
            self.interrupt_in_flight(f"operation_refused:{exc.reason}")
            self.stop(f"operation_refused:{exc.reason}")
        finally:
            self.not_run(ids, "not_reached")
