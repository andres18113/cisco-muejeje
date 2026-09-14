"""CP-SCALE closure policy over narrow facts, with no mutable run context."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .cleanup import CPScaleCleanup
from .checkpoint import CPScaleCheckpointDecision
from .contracts import CPScalePreflightOutcome, CPScalePreflightResult
from .run_contracts import CPScaleStageProgress, CPScaleRunReplayAudit, CPScaleTerminalEvent, CPScaleCleanupResult, CPScaleCleanupRealtime
from ..use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage, CPScaleCanonicalTarget, CPScaleCanonicalTargetContract,
    canonical_cp_scale_target_contract,
)
from ..use_cases.qualify_cp_scale_live import CPScaleFinalDisposition, canonical_final_disposition
from ...domain.enterprise.models.configuration_runtime import ConfigurationApplicationStatus


@dataclass(frozen=True)
class CPScaleBoundedTargetReview:
    replay: CPScaleRunReplayAudit | None
    error: str


@dataclass(frozen=True)
class CPScaleFullQualificationReview:
    """The whole run's replay audit FULL closure accepted, or why it refused."""

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


def _run_replay_audit(stages: tuple[CPScaleStageProgress, ...]) -> CPScaleRunReplayAudit:
    audits = tuple(item.result.replay_audit if item.result else None for item in stages)
    missing = tuple(item.projection.stage.value for item, audit in zip(stages, audits)
        if audit is None or audit.verified is not True or audit.claim != "NO_MUTATION_REPLAY")
    replayed = tuple(sorted({identifier for audit in audits if audit is not None
        for surface in audit.surfaces for identifier in surface.replayed_retained_ids}))
    return CPScaleRunReplayAudit(tuple(item.projection.stage.value for item in stages), missing, replayed)


def _replay_error(subject: str, replay: CPScaleRunReplayAudit) -> str:
    if replay.verified:
        return ""
    detail = ("; replayed retained actions: " + ", ".join(replay.replayed_retained_ids)
              if replay.replayed_retained_ids else "")
    return (subject + " closure cannot attest NO_MUTATION_REPLAY; stages without a verified runtime audit: "
            + ", ".join(replay.stages_without_verified_audit) + detail)


def _forwarding_complete(planned, requested, observations, verified, projection) -> bool:
    """Each derived check was requested and observed once, VERIFIED, from this plan."""
    return bool(
        planned
        and len(requested) == len(planned)
        and all(item is check for item, check in zip(requested, planned))
        and len({check.id for check in planned}) == len(planned)
        and verified is True
        and len(observations) == len(planned)
        and all(
            item.check is check and item.verified is True and item.attempts
            for check, item in zip(planned, observations)
        )
        and all(
            check.source_topology_hash == projection.topology.physical_identity_hash
            and check.source_configuration_hash == projection.configuration.semantic_hash
            for check in planned
        )
    )


def _remaining_transition_error(previous: CPScaleStageProgress, final: CPScaleStageProgress) -> str:
    transition = final.transition
    scope = final.result.report.scope
    if transition is None or scope is None:
        return "REMAINING has no transition contract or executed mutation scope."
    if (transition.previous_stage is not previous.projection.stage
            or transition.current_stage is not final.projection.stage
            or transition.previous_physical_topology_hash != previous.projection.topology.physical_identity_hash
            or transition.current_physical_topology_hash != final.projection.topology.physical_identity_hash):
        return "the REMAINING transition does not bind this run's previous and final projections."
    if not transition.physical_delta_empty:
        return "the REMAINING transition is not a zero physical delta."
    if not transition.mutation_scope_disjoint:
        return "the REMAINING transition claim is " + transition.claim + "."
    previous_voice = previous.projection.voice
    surfaces = (
        ("configuration", previous.projection.configuration.actions,
         transition.configuration_mutation_ids, transition.configuration_retained_ids,
         scope.configuration, scope.retained_configuration),
        ("control-plane", previous.projection.control_plane.actions,
         transition.control_plane_mutation_ids, transition.control_plane_retained_ids,
         scope.control_plane, scope.retained_control_plane),
        ("voice", previous_voice.actions if previous_voice is not None else (),
         transition.voice_mutation_ids, transition.voice_retained_ids,
         scope.voice, scope.retained_voice),
    )
    for surface, previous_actions, mutations, retained, executed, executed_retained in surfaces:
        if sorted(retained) != sorted(item.id for item in previous_actions):
            return f"the REMAINING {surface} retained scope is not the previous stage's plan."
        # The executor retains the final plan minus its mutations, so equal
        # executed and authorized scopes also prove the exact partition.
        if sorted(executed) != sorted(mutations) or sorted(executed_retained) != sorted(retained):
            return f"the executed REMAINING {surface} scope differs from the transition's authorized scope."
    return ""


def _full_qualification_error(preflight: CPScalePreflightResult, stages: tuple[CPScaleStageProgress, ...]) -> str:
    contract = canonical_cp_scale_target_contract(CPScaleCanonicalTarget.FULL_QUALIFICATION)
    authorization = preflight.live_authorization
    identity = preflight.identity
    if preflight.target != contract:
        return "the run target is not the exact FULL qualification contract."
    if (preflight.outcome is not CPScalePreflightOutcome.ADMITTED or identity is None
            or authorization is None or authorization.authorized_target is not contract.target
            or authorization.authorized_sha != identity.source_head):
        return "the run lacks an admitted FULL authorization bound to its own source provenance."
    executed = tuple(item.projection.stage for item in stages)
    if executed != contract.execution_stages:
        return ("the executed stages are not the exact build sequence followed by REMAINING: "
                + (", ".join(stage.value for stage in executed) or "none") + ".")
    for item in stages:
        result = item.result
        if (item.failed or result is None or result.outcome != "verified"
                or result.stage is not item.projection.stage or result.projection is not item.projection):
            return f"stage {item.projection.stage.value!r} has no VERIFIED result for its own projection."
    final = stages[-1]
    projection, result = final.projection, final.result
    report = result.report
    if result.configuration_accepted is not True:
        return "the REMAINING configuration was not accepted."
    if result.control_plane is None or result.control_plane.status is not ConfigurationApplicationStatus.VERIFIED:
        return "the REMAINING control plane was not VERIFIED."
    voice = projection.voice
    canonical_voice = report.canonical_voice
    if (voice is None or not voice.phone_assignments or canonical_voice is None
            or canonical_voice.complete is not True or canonical_voice.stage != projection.stage.value
            or canonical_voice.expected_phone_count != len(voice.phone_assignments)):
        return "the REMAINING canonical Voice evidence is not complete for every planned phone."
    forwarding = report.forwarding
    if forwarding is None or not _forwarding_complete(
            getattr(projection, "branch_forwarding_checks", ()), report.site_forwarding_checks,
            forwarding.site, forwarding.site_verified, projection):
        return "REMAINING site forwarding is not VERIFIED for every derived check."
    if not _forwarding_complete(
            getattr(projection, "branch_user_forwarding_checks", ()), report.user_forwarding_checks,
            forwarding.user, forwarding.user_verified, projection):
        return "REMAINING representative PC forwarding is not VERIFIED for every derived check."
    if report.workspace_verified is not True or report.workspace_first is None or report.workspace_second is None:
        return "the REMAINING workspace was not VERIFIED by two fresh readbacks."
    return _remaining_transition_error(stages[-2], final)


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
        replay = _run_replay_audit(stages)
        return CPScaleBoundedTargetReview(
            replay,
            _replay_error(f"Bounded target {target.terminal_stage.value!r}", replay),
        )

    def review_full_qualification(
        self,
        preflight: CPScalePreflightResult,
        stages: tuple[CPScaleStageProgress, ...],
    ) -> CPScaleFullQualificationReview:
        """Accept FULL only as its own authorized run closed by REMAINING.

        REMAINING is the single final authority. Every build stage and
        REMAINING must be VERIFIED under NO_MUTATION_REPLAY, and REMAINING must
        prove accepted configuration, a VERIFIED control plane, complete
        canonical Voice, every derived site and representative PC pair, two
        workspace readbacks, and a zero-delta transition whose authorized scope
        is exactly the scope that executed. Wireless association stays
        unqualified and intersite calling stays off in the product, so neither
        is a criterion here.
        """
        error = _full_qualification_error(preflight, stages)
        if error:
            return CPScaleFullQualificationReview(None, "Full qualification closure refused: " + error)
        replay = _run_replay_audit(stages)
        return CPScaleFullQualificationReview(replay, _replay_error("Full qualification", replay))

    def plan(self, target: CPScaleCanonicalTargetContract, command: CPScaleCheckpointDecision,
             *, retain_authorized: bool) -> CPScaleClosurePlan:
        # A cleanup-closed target never retains, whatever the final command.
        cleanup_closed = target.require_cleanup
        disposition = CPScaleFinalDisposition.CLEANUP if cleanup_closed else canonical_final_disposition(command.value, retain_authorized=retain_authorized)
        event = CPScaleTerminalEvent.RETAINED if disposition is CPScaleFinalDisposition.RETAIN else (
            CPScaleTerminalEvent(target.cleaned_closure)
            if cleanup_closed else CPScaleTerminalEvent.CANONICAL_CLEANED)
        return CPScaleClosurePlan(disposition, target.precleanup_closure, target.cleaned_closure,
            "CP_SCALE_GOVERNED_VOICE_VERIFIED_RETAINED", target.target.value if cleanup_closed else "",
            target.target.value if cleanup_closed else "full-qualification", target.run_full_qualification,
            cleanup_closed and not target.run_full_qualification, event)

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
