"""CP-SCALE closure policy over narrow facts, with no mutable run context."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .cleanup import CPScaleCleanup
from .checkpoint import CPScaleCheckpointDecision
from .run_contracts import CPScaleStageProgress, CPScaleRunReplayAudit, CPScaleTerminalEvent, CPScaleCleanupResult, CPScaleCleanupRealtime
from ..use_cases.compose_cp_scale_canonical import CPScaleCanonicalStage, CPScaleCanonicalTargetContract
from ..use_cases.qualify_cp_scale_live import CPScaleFinalDisposition, canonical_final_disposition


@dataclass(frozen=True)
class CPScaleBoundedTargetReview:
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
    bounded_target: bool
    event: CPScaleTerminalEvent


@dataclass(frozen=True)
class CPScaleCleanupReview:
    error: str
    secondary_failures: tuple[str, ...] = ()


class CPScaleCompletion:
    def __init__(self, *, cleanup: CPScaleCleanup, clock=lambda: datetime.now(timezone.utc)) -> None:
        self.cleanup = cleanup
        self.clock = clock

    def review_bounded_target(
        self,
        target: CPScaleCanonicalTargetContract,
        stages: tuple[CPScaleStageProgress, ...],
    ) -> CPScaleBoundedTargetReview:
        latest = stages[-1].result if stages else None
        forwarding = latest.report.forwarding if latest else None
        checks = latest.report.site_forwarding_checks if latest else ()
        observations = forwarding.site if forwarding else ()
        covered = bool(checks and len(checks) == len(observations)
            and len({check.id for check in checks}) == len(checks)
            and all(item.check is check and item.verified for check, item in zip(checks, observations)))
        projected_user_checks = (
            getattr(latest.projection, "branch_user_forwarding_checks", None)
            if latest else None
        )
        user_checks = latest.report.user_forwarding_checks if latest else ()
        user_observations = forwarding.user if forwarding else ()
        # ``None`` is the explicit historical projection compatibility path.
        # Current canonical projections always expose the field and therefore
        # must carry the required pair; an empty current contract fails closed.
        user_covered = bool(
            projected_user_checks is None
            or (
                projected_user_checks
                and user_checks == projected_user_checks
                and len(user_checks) == len(user_observations)
                and len({check.id for check in user_checks}) == len(user_checks)
                and all(
                    item.check is check and item.verified
                    for check, item in zip(user_checks, user_observations)
                )
            )
        )
        if (not target.require_cleanup or target.run_full_qualification
            or latest is None or latest.stage is not target.terminal_stage
            or latest.outcome != "verified" or forwarding is None or forwarding.site_verified is not True
            or latest.report.workspace_verified is not True or not covered
            or (
                projected_user_checks is not None
                and forwarding.user_verified is not True
            )
            or not user_covered):
            return CPScaleBoundedTargetReview(
                None,
                f"Bounded target {target.terminal_stage.value!r} closure lacks "
                "verified stage, forwarding, or double workspace evidence.",
            )
        audits = tuple(item.result.replay_audit if item.result else None for item in stages)
        missing = tuple(item.projection.stage.value for item, audit in zip(stages, audits)
            if audit is None or audit.verified is not True or audit.claim != "NO_MUTATION_REPLAY")
        replayed = tuple(sorted({identifier for audit in audits if audit is not None
            for surface in audit.surfaces for identifier in surface.replayed_retained_ids}))
        replay = CPScaleRunReplayAudit(tuple(item.projection.stage.value for item in stages), missing, replayed)
        detail = "; replayed retained actions: " + ", ".join(replayed) if replayed else ""
        error = (f"Bounded target {target.terminal_stage.value!r} closure cannot attest NO_MUTATION_REPLAY; stages without a verified runtime audit: "
            + ", ".join(missing) + detail if missing else "")
        return CPScaleBoundedTargetReview(replay, error)

    def plan(self, target: CPScaleCanonicalTargetContract, command: CPScaleCheckpointDecision,
             *, retain_authorized: bool) -> CPScaleClosurePlan:
        bounded = target.require_cleanup and not target.run_full_qualification
        disposition = CPScaleFinalDisposition.CLEANUP if bounded else canonical_final_disposition(command.value, retain_authorized=retain_authorized)
        event = CPScaleTerminalEvent.RETAINED if disposition is CPScaleFinalDisposition.RETAIN else (
            CPScaleTerminalEvent(target.cleaned_closure)
            if bounded else CPScaleTerminalEvent.CANONICAL_CLEANED)
        return CPScaleClosurePlan(disposition, target.precleanup_closure, target.cleaned_closure,
            "CP_SCALE_GOVERNED_VOICE_VERIFIED_RETAINED", target.terminal_stage.value if bounded else "",
            target.target.value if bounded else "full-qualification", not bounded, bounded, event)

    def review_cleanup(self, cleanup: CPScaleCleanupResult, realtime: CPScaleCleanupRealtime,
                       *, target_stage: CPScaleCanonicalStage | None) -> CPScaleCleanupReview:
        if cleanup.verified and realtime.verified:
            return CPScaleCleanupReview("")
        prefix = (
            target_stage.value.partition("-")[0].capitalize()
            if target_stage is not None else "Canonical"
        )
        secondaries = ("cleanup_realtime: " + realtime.error,) if (
            (cleanup.error or cleanup.restoration_error) and realtime.error
        ) else ()
        return CPScaleCleanupReview(prefix + " verification completed, but cleanup/restoration did not verify: "
            + (cleanup.error or cleanup.restoration_error or realtime.error), secondaries)
