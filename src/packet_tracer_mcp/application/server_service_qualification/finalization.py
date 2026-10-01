"""Guaranteed finalization of one admitted qualification invocation.

The terminal read-only observation is taken first, owned engine state and
owned devices are released only under proven authority, restoration is read
twice, and every failure here is secondary to the primary outcome.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict

from ...domain.enterprise.models.execution import DirtyState, MutationDisposition
from ...domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
    ReleaseRecord,
    diagnostic_lifecycle_continuity,
)
from ...domain.enterprise.services.service_qualification_evidence import ProbeReading
from .contracts import bounded
from .execution import Execution
from .operation_budget import LedgerPhase, OperationRefused


def observe_terminal(execution: Execution) -> KeyboardInterrupt | None:
    """Take the stage's terminal reading once, before anything is deleted.

    This is the only place the reading happens. Registering it and taking it
    are separate so that every exit which reaches cleanup reaches the reading
    first: a normal completion, a handled stop, an `OperationRefused` inside a
    procedure, an ordinary Python exception raised out of the middle of the
    sequence, and a run whose record stopped advancing.

    Three rules it never breaks. A cancelled run does not take it: the
    operator asked the run to stop doing work, so the measurement is declared
    `not_observed:cancelled` and no stimulus is restarted or re-dispatched. A
    failure inside the reading is secondary -- it never replaces the primary
    error and never stops owned cleanup, which is why nothing raises out of
    here. And the reading itself is read-only and paid for out of the ordinary
    allowance, which `begin_terminal` already enforces.
    """
    phase = execution.terminal
    if phase is None or execution.terminal_taken:
        return None
    execution.terminal_taken = True
    if execution.cancelled:
        execution.not_observed(phase.ids, "cancelled")
        return None
    try:
        phase.observe()
    except KeyboardInterrupt as exc:
        execution.cancelled = True
        execution.stop("cancelled")
        execution.not_observed(phase.ids, "cancelled")
        execution.record.secondary_failures.append(
            f"terminal_observation:{phase.procedure}:cancelled"
        )
        return exc
    except OperationRefused as exc:
        execution.not_observed(phase.ids, f"operation_refused:{exc.reason}")
        execution.record.secondary_failures.append(
            f"terminal_observation:{phase.procedure}:refused:{exc.reason}"
        )
    except Exception as exc:
        execution.not_observed(phase.ids, f"exception:{type(exc).__name__}")
        execution.record.secondary_failures.append(
            f"terminal_observation:{phase.procedure}:exception:{type(exc).__name__}"
        )
    finally:
        execution.in_flight = ()
    return None


def release_campaign_claim(execution: Execution) -> None:
    """Release the campaign claim into this record, before it is completed.

    A claim this run cannot release keeps the next campaign out of the shared
    scope, so it is a finalization result the record has to carry rather than
    something that happens to the filesystem after the record is closed. It is
    deliberately not engine residue: a lock left behind says nothing about
    whether the engine workspace was restored, and the two claims stay apart.
    """
    execution.hold.finalize(execution.record)


def finalize(execution: Execution) -> None:
    """Release owned state, remove owned devices and prove restoration twice.

    The receiver is proven before anything is deleted, not afterwards. A
    Packet Tracer that was replaced mid-run polls the same mailbox, so a
    removal dispatched now would land in a workspace this authority never
    bound; learning that after the fact invalidates the report without undoing
    the deletion. With authority lost this finalization deletes nothing, names
    every action it did not take, and still reads what it can. The postflight
    reading below keeps its detection role for everything that came earlier.
    """
    ledger = execution.ledger
    ledger.enter(LedgerPhase.FINALIZATION)
    record = execution.record
    execution.in_flight = ()
    execution.run.transition("finalization:started")
    owned = execution.live_authority("finalization:owned_cleanup")
    if not owned:
        _refuse_owned_cleanup(execution)
    else:
        _release_engine_state(execution)
    for plan in reversed(execution.removal_candidates) if owned else ():
        fixture = next(item for item in record.fixtures if item.name == plan.name)
        try:
            with ledger.effect_of(f"remove:{plan.name}"):
                result = execution.physical.remove_device(plan)
        except OperationRefused as exc:
            record.secondary_failures.append(f"remove:{plan.name}:{exc.reason}")
            record.releases.append(
                ReleaseRecord(
                    resource=f"device:{plan.name}",
                    kind="device",
                    outcome="not_attempted",
                    detail=exc.reason,
                )
            )
            record.engine_residue.append(f"device:{plan.name}:removal_not_attempted")
            continue
        except Exception as exc:
            record.secondary_failures.append(
                f"remove:{plan.name}:exception:{type(exc).__name__}"
            )
            record.engine_residue.append(f"device:{plan.name}:removal_unknown")
            continue
        outcome = {
            MutationDisposition.CHANGED: "removed",
            MutationDisposition.NO_OP: "already_absent",
            MutationDisposition.UNKNOWN: "unknown",
        }.get(result.disposition, "failed")
        record.releases.append(
            ReleaseRecord(
                resource=f"device:{plan.name}",
                kind="device",
                outcome=outcome,
                detail=bounded(result.message),
            )
        )
        if outcome in ("unknown", "failed"):
            # An ambiguous removal is never repeated as if it had not run.
            record.engine_residue.append(f"device:{plan.name}:removal_{outcome}")
            record.secondary_failures.append(f"remove:{plan.name}:{outcome}")
        fixture.detail = bounded(f"{fixture.detail} | cleanup:{outcome}")
    observations: list[PhysicalWorkspaceObservation | None] = []
    for index in (1, 2):
        try:
            with ledger.purpose_of(f"read:restoration:{index}"):
                observations.append(execution.physical.observe_workspace())
        except OperationRefused as exc:
            record.secondary_failures.append(f"restoration:{index}:{exc.reason}")
            observations.append(None)
        except Exception as exc:
            record.secondary_failures.append(
                f"restoration:{index}:exception:{type(exc).__name__}"
            )
            observations.append(None)
    record.restoration = [
        item.compact_summary() if item is not None else {"observed": False}
        for item in observations
    ]
    _restoration_scope(execution, observations)
    # Authority held at the start of finalization is not authority held at the
    # end of it: the effect gate can refuse a removal halfway through the loop
    # above. A restoration claim needs the receiver to still be the bound one
    # when the last reading was taken, so the two are one condition here.
    attributable = owned and not execution.authority_lost
    record.restoration_proven = attributable and all(
        item is not None
        and physical_workspace_restoration_matches(execution.baseline, item)
        for item in observations
    )
    if not attributable:
        # These reads describe whatever answers the mailbox now. They are kept
        # as observations and they prove nothing about the bound instance's
        # workspace, so they never become a restoration claim.
        record.limitations.append(
            "restoration_reads_not_attributable_to_the_authorized_process"
        )
    if owned and not attributable:
        # The run entered cleanup holding the receiver and lost it partway.
        # Whatever it had not deleted by then was not dispatched at all.
        record.limitations.append(
            "owned_cleanup_not_dispatched_to_an_unproven_receiver"
        )
    if execution.bound.settle_pending_sends():
        record.engine_residue.append("transport:pending_fire_and_forget")
        record.secondary_failures.append("transport:pending_fire_and_forget")
        record.limitations.append("transport_pending_send_not_replayed")
        record.restoration_proven = False
    _lifecycle_postflight(execution)
    for name in sorted(execution.observers_unresolved):
        record.engine_residue.append(f"observer:{name}")
    record.dirty_state = _dirty_state(execution, observations)
    execution.run.transition("finalization:completed")


def _refuse_owned_cleanup(execution: Execution) -> None:
    """Name every owned deletion this run declined to dispatch, and why.

    Nothing here is a guess about what the replacement receiver holds. The
    fixtures this run created are still reported as residue, because that is
    what an operator has to reconcile; they are simply not deleted through a
    session whose identity can no longer be proven.
    """
    record = execution.record
    cause = (
        execution.authority_lost
        or execution.authority_observation_refused
        or "execution_authority_lost"
    )
    if execution.bag_touched:
        # Only state is left behind that this run actually wrote. A bag
        # it never claimed is not residue it declined to clean.
        record.releases.append(
            ReleaseRecord(
                resource="bag:run",
                kind="bag",
                outcome="not_attempted",
                detail=f"execution authority lost before cleanup: {cause}",
            )
        )
    for plan in reversed(execution.removal_candidates):
        record.releases.append(
            ReleaseRecord(
                resource=f"device:{plan.name}",
                kind="device",
                outcome="not_attempted",
                detail=f"execution authority lost before cleanup: {cause}",
            )
        )
        record.engine_residue.append(
            f"device:{plan.name}:removal_refused_unproven_receiver"
        )
    record.limitations.append("owned_cleanup_not_dispatched_to_an_unproven_receiver")


def _lifecycle_postflight(execution: Execution) -> None:
    """Read the local process pairing again, after owned finalization.

    The admission reading bound one Packet Tracer before a transport
    existed. Nothing holds that process for the rest of the run: a crashed
    instance is replaced by one that polls the same mailbox, and the
    removals and both restoration reads above would then have been answered
    by a process this authority never bound. Reading the pairing again is
    what decides whether that evidence is still about the authorized
    instance, and whether this run left anything a later one could execute.

    It enumerates local processes and lists one directory. It contacts
    Packet Tracer through nothing, launches and stops nothing, deletes no
    artifact and spends no ledger operation, but it does spend finalization
    wall-clock. Every helper is bounded by the remaining finalization deadline;
    when none remains, the record retains an explicit unobserved postflight
    instead of launching another helper. A broken or unavailable pairing is
    not a new primary failure -- the run already happened -- but restoration
    stops being proven, because the final evidence is not attributable to the
    process under authority.
    """
    record = execution.record
    lifecycle = execution.run.boundaries.diagnostic_lifecycle
    if not callable(lifecycle) or execution.run.diagnostic_lifecycle is None:
        return
    deadline = execution.ledger.deadline()
    if execution.run.boundaries.clock() >= deadline:
        observed = DiagnosticLifecycleObservation(
            error="local_observation_not_admitted:time_budget_exhausted"
        )
    else:
        observed = execution.observe_lifecycle(lifecycle, deadline)
    record.diagnostic_lifecycle_postflight = asdict(observed)
    reasons = diagnostic_lifecycle_continuity(
        execution.run.diagnostic_lifecycle, observed
    )
    if not reasons:
        return
    record.engine_residue.extend(reasons)
    record.secondary_failures.extend(f"lifecycle:{item}" for item in reasons)
    record.limitations.append(
        "finalization_evidence_not_paired_to_the_authorized_process"
    )
    record.restoration_proven = False


def _restoration_scope(
    execution: Execution,
    observations: Sequence[PhysicalWorkspaceObservation | None],
) -> None:
    """State what restoration compares, and name a changed raw count.

    Restoration compares semantic devices and links and permits Packet
    Tracer's own backend-managed devices. That is not equality of the whole
    workspace, so a record whose backend-managed count differs from the
    baseline says so -- the raw reads stay unchanged beside it.
    """
    if execution.baseline is None or not execution.baseline.observed:
        return
    baseline = len(execution.baseline.backend_managed_devices)
    counts = sorted(
        {
            len(item.backend_managed_devices)
            for item in observations
            if item is not None and item.observed
        }
    )
    if not counts:
        return
    limitations = execution.record.limitations
    if "restoration_scope:semantic_devices_and_links" not in limitations:
        limitations.append("restoration_scope:semantic_devices_and_links")
    for count in counts:
        if count != baseline:
            limitations.append(f"backend_managed_devices_changed:{baseline}->{count}")


def _release_engine_state(execution: Execution) -> None:
    """Delete the run's own bag once; never touch a key it cannot prove it owns.

    Two gates stand in front of the delete and they are not the same one. Here,
    a reported collision means the claim wrote nothing, so there is nothing to
    release and nothing is dispatched. Inside the engine, the release proves
    this invocation's nonce in the evaluation that would delete, so a claim
    whose acknowledgement was lost still cannot make this adopt a key that
    belongs to someone else.
    """
    record = execution.record
    if execution.bag_collision:
        record.engine_residue.append("bag:run_key_not_exclusively_owned")
        record.releases.append(
            ReleaseRecord(
                resource="bag:run",
                kind="bag",
                outcome="not_attempted",
                detail="run key collision; nothing was written and nothing is deleted",
            )
        )
        return
    if not execution.bag_touched:
        return
    # Even when every step released its own entry, the run key itself is
    # still present in the engine, so the finalizer always removes it.
    try:
        with execution.ledger.effect_of("release:run_bag"):
            reading = execution.probes.release_run_bag()
    except OperationRefused as exc:
        record.secondary_failures.append(f"release:run_bag:{exc.reason}")
        reading = None
    except Exception as exc:
        record.secondary_failures.append(
            f"release:run_bag:exception:{type(exc).__name__}"
        )
        reading = None
    if reading is not None and reading.observed:
        if _bag_released(execution, reading):
            return
    record.releases.append(
        ReleaseRecord(
            resource="bag:run",
            kind="bag",
            outcome="release_unverified",
            detail=reading.cause if reading is not None else "not_dispatched",
        )
    )
    # The run key itself is residue even when every step released its own
    # entry: nothing observed its deletion.
    record.engine_residue.append("bag:run_key:release_unverified")
    _unreleased_residue(execution)


def _bag_released(execution: Execution, reading: ProbeReading) -> bool:
    """Record what one observed release reading settled, or return False."""
    record = execution.record
    keys = "keys=" + ",".join(str(item) for item in reading.payload["keys"])
    if not reading.payload["had_run_bag"]:
        record.releases.append(
            ReleaseRecord(
                resource="bag:run",
                kind="bag",
                outcome="absent_at_release",
                detail=keys,
            )
        )
        execution.bag_unreleased.clear()
        return True
    if not reading.payload["owned"]:
        # A key exists under this run's name that this invocation cannot prove
        # it wrote. It is reported as residue, never adopted and never deleted.
        record.releases.append(
            ReleaseRecord(
                resource="bag:run",
                kind="bag",
                outcome="not_attempted",
                detail="run key present but not owned by this invocation",
            )
        )
        record.engine_residue.append("bag:run_key_not_owned")
        _unreleased_residue(execution)
        return True
    if reading.payload["deleted"] and not reading.payload["present_after"]:
        record.releases.append(
            ReleaseRecord(
                resource="bag:run", kind="bag", outcome="released", detail=keys
            )
        )
        if execution.bag_unreleased & {"atom"}:
            # A contender that has not run yet can recreate its entry later.
            record.engine_residue.append("bag:atom:contender_may_still_run")
        execution.bag_unreleased.clear()
        return True
    return False


def _unreleased_residue(execution: Execution) -> None:
    """Report every run-bag entry whose release this run could not observe."""
    for name in sorted(execution.bag_unreleased):
        execution.record.engine_residue.append(f"bag:{name}:release_unverified")


def _dirty_state(
    execution: Execution, observations: Sequence[PhysicalWorkspaceObservation | None]
) -> DirtyState:
    record = execution.record
    if record.restoration_proven and not record.engine_residue:
        return DirtyState.CLEAN
    owned = {plan.name for plan in execution.removal_candidates}
    known_devices_only = bool(record.engine_residue) and all(
        item.startswith("device:") for item in record.engine_residue
    )
    if (
        known_devices_only
        and all(item is not None and item.observed for item in observations)
        and all(
            {device.name for device in item.semantic_devices} <= owned
            for item in observations
            if item is not None
        )
    ):
        return DirtyState.DIRTY_RECOVERABLE
    return DirtyState.UNKNOWN
