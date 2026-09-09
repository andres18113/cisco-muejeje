"""CP-SCALE closure policy over narrow facts, with no mutable run context."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .cleanup import CPScaleCleanup
from .checkpoint import CPScaleCheckpointDecision
from .run_contracts import CPScaleStageProgress, CPScaleRunReplayAudit, CPScaleTerminalEvent, CPScaleCleanupResult, CPScaleCleanupRealtime
from ..use_cases.compose_cp_scale_canonical import CPScaleCanonicalTarget, CPScaleCanonicalStage, CPScaleCanonicalTargetContract
from ..use_cases.qualify_cp_scale_live import CPScaleFinalDisposition, canonical_final_disposition


@dataclass(frozen=True)
class CPScaleRouter0Review:
    replay: CPScaleRunReplayAudit | None
    error: str


@dataclass(frozen=True)
class CPScaleClosurePlan:
    disposition: CPScaleFinalDisposition
    precleanup_closure: str
    cleaned_closure: str
    retained_closure: str
    scope: str
    checkpoint: str
    final_checkpoint: bool
    router0: bool
    event: CPScaleTerminalEvent


@dataclass(frozen=True)
class CPScaleCleanupReview:
    error: str
    secondary_failures: tuple[str, ...] = ()


class CPScaleCompletion:
    def __init__(self, *, cleanup: CPScaleCleanup, clock=lambda: datetime.now(timezone.utc)) -> None:
        self.cleanup = cleanup
        self.clock = clock

    def review_router0(self, target: CPScaleCanonicalTargetContract,
                       stages: tuple[CPScaleStageProgress, ...]) -> CPScaleRouter0Review:
        latest = stages[-1].result if stages else None
        forwarding = latest.report.forwarding if latest else None
        checks = latest.report.site_forwarding_checks if latest else ()
        observations = forwarding.site if forwarding else ()
        covered = bool(checks and len(checks) == len(observations)
            and len({check.id for check in checks}) == len(checks)
            and all(item.check is check and item.verified for check, item in zip(checks, observations)))
        if (target.target is not CPScaleCanonicalTarget.ROUTER0_BRANCH
            or latest is None or latest.stage is not CPScaleCanonicalStage.ROUTER0_BRANCH
            or latest.outcome != "verified" or forwarding is None or forwarding.site_verified is not True
            or latest.report.workspace_verified is not True or not covered):
            return CPScaleRouter0Review(None, "Router0 terminal closure lacks verified stage, forwarding, or double workspace evidence.")
        audits = tuple(item.result.replay_audit if item.result else None for item in stages)
        missing = tuple(item.projection.stage.value for item, audit in zip(stages, audits)
            if audit is None or audit.verified is not True or audit.claim != "NO_MUTATION_REPLAY")
        replayed = tuple(sorted({identifier for audit in audits if audit is not None
            for surface in audit.surfaces for identifier in surface.replayed_retained_ids}))
        replay = CPScaleRunReplayAudit(tuple(item.projection.stage.value for item in stages), missing, replayed)
        detail = "; replayed retained actions: " + ", ".join(replayed) if replayed else ""
        error = ("Router0 terminal closure cannot attest NO_MUTATION_REPLAY; stages without a verified runtime audit: "
            + ", ".join(missing) + detail if missing else "")
        return CPScaleRouter0Review(replay, error)

    def plan(self, target: CPScaleCanonicalTargetContract, command: CPScaleCheckpointDecision,
             *, retain_authorized: bool) -> CPScaleClosurePlan:
        router0 = target.target is CPScaleCanonicalTarget.ROUTER0_BRANCH
        disposition = CPScaleFinalDisposition.CLEANUP if router0 else canonical_final_disposition(command.value, retain_authorized=retain_authorized)
        event = CPScaleTerminalEvent.RETAINED if disposition is CPScaleFinalDisposition.RETAIN else (
            CPScaleTerminalEvent.ROUTER0_CLEANED if router0 else CPScaleTerminalEvent.CANONICAL_CLEANED)
        return CPScaleClosurePlan(disposition, target.precleanup_closure, target.cleaned_closure,
            "CP_SCALE_GOVERNED_VOICE_VERIFIED_RETAINED", CPScaleCanonicalStage.ROUTER0_BRANCH.value if router0 else "",
            "router0-branch" if router0 else "full-qualification", not router0, router0, event)

    def review_cleanup(self, cleanup: CPScaleCleanupResult, realtime: CPScaleCleanupRealtime,
                       *, router0: bool) -> CPScaleCleanupReview:
        if cleanup.verified and realtime.verified:
            return CPScaleCleanupReview("")
        prefix = "Router0" if router0 else "Canonical"
        secondaries = ("cleanup_realtime: " + realtime.error,) if (
            (cleanup.error or cleanup.restoration_error) and realtime.error
        ) else ()
        return CPScaleCleanupReview(prefix + " verification completed, but cleanup/restoration did not verify: "
            + (cleanup.error or cleanup.restoration_error or realtime.error), secondaries)
