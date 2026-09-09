"""CP-SCALE terminal policy and failure cleanup, separate from close ownership."""
from __future__ import annotations

from datetime import datetime, timezone

from .cleanup import CPScaleCleanup
from .checkpoint import CPScaleCheckpointDecision
from .errors import CanonicalLiveFailure
from .run_contracts import (
    CPScaleCleanupAttestation, CPScaleCleanupResult, CPScaleFinalizationState,
    CPScaleRunReport, CPScaleRunReplayAudit, CPScaleTerminalEvent,
)
from .run_ports import CPScaleEvidencePort
from .session import CPScaleSessionPort, CPScaleRunObservationPort
from ..use_cases.compose_enterprise_reference import EnterpriseReferenceComposition
from ..use_cases.compose_cp_scale_canonical import CPScaleCanonicalTarget, CPScaleCanonicalStage
from ..use_cases.qualify_cp_scale_live import CPScaleFinalDisposition, canonical_final_disposition, CPScaleEvidenceArchive


class CPScaleCompletion:
    def __init__(self, *, evidence: CPScaleEvidencePort,
                 cleanup: CPScaleCleanup, clock=lambda: datetime.now(timezone.utc)) -> None:
        self.evidence = evidence
        self.cleanup = cleanup
        self.clock = clock

    def archive(self, phase: str, payload: CPScaleRunReport | CPScaleCleanupAttestation,
                report: CPScaleRunReport) -> CPScaleEvidenceArchive:
        receipt = self.evidence.archive(phase, payload, run_identity=report.run_identity)
        report.archives += (receipt,)
        return receipt

    def require_router0(self, report: CPScaleRunReport) -> None:
        latest = report.stages[-1].result if report.stages else None
        forwarding = latest.report.forwarding if latest else None
        checks = latest.report.site_forwarding_checks if latest else ()
        observations = forwarding.site if forwarding else ()
        covered = bool(checks and len(checks) == len(observations)
            and len({check.id for check in checks}) == len(checks)
            and all(item.check is check and item.verified for check, item in zip(checks, observations)))
        if (report.preflight.target.target is not CPScaleCanonicalTarget.ROUTER0_BRANCH
            or latest is None or latest.stage is not CPScaleCanonicalStage.ROUTER0_BRANCH
            or latest.outcome != "verified" or forwarding is None or forwarding.site_verified is not True
            or latest.report.workspace_verified is not True or not covered):
            raise CanonicalLiveFailure("Router0 terminal closure lacks verified stage, forwarding, or double workspace evidence.")
        audits = tuple(item.result.replay_audit if item.result else None for item in report.stages)
        missing = tuple(item.projection.stage.value for item, audit in zip(report.stages, audits)
            if audit is None or audit.verified is not True or audit.claim != "NO_MUTATION_REPLAY")
        replayed = tuple(sorted({identifier for audit in audits if audit is not None
            for surface in audit.surfaces for identifier in surface.replayed_retained_ids}))
        report.no_mutation_replay = CPScaleRunReplayAudit(
            tuple(item.projection.stage.value for item in report.stages), missing, replayed)
        if missing:
            detail = "; replayed retained actions: " + ", ".join(replayed) if replayed else ""
            raise CanonicalLiveFailure("Router0 terminal closure cannot attest NO_MUTATION_REPLAY; stages without a verified runtime audit: " + ", ".join(missing) + detail)

    def complete(self, *, report: CPScaleRunReport, state: CPScaleFinalizationState,
                 session: CPScaleSessionPort, composition: EnterpriseReferenceComposition, owned: frozenset[str],
                 observations: CPScaleRunObservationPort, command: CPScaleCheckpointDecision = CPScaleCheckpointDecision.CONTINUE,
                 retain_authorized: bool = False, router0: bool = False) -> CPScaleTerminalEvent:
        target = report.preflight.target
        if router0:
            self.require_router0(report)
            disposition = CPScaleFinalDisposition.CLEANUP
            report.closure_scope = CPScaleCanonicalStage.ROUTER0_BRANCH.value
        else:
            disposition = canonical_final_disposition(command.value, retain_authorized=retain_authorized)
        report.final_disposition = disposition
        report.closure = target.precleanup_closure
        report.completed_at = self.clock()
        self.evidence.write_progress(report)
        receipt = self.archive("precleanup", report, report)
        report.canonical_evidence_precleanup = receipt
        state.precleanup_archive = receipt
        if disposition is CPScaleFinalDisposition.RETAIN:
            report.presentation_retained = True
            report.closure = "CP_SCALE_GOVERNED_VOICE_VERIFIED_RETAINED"
            state.retain_confirmed = True
            self.evidence.write_progress(report)
            self.evidence.checkpoint("full-qualification", report, final=True)
            return CPScaleTerminalEvent.RETAINED
        cleanup = self.cleanup.restore(session.physical, composition.topology, owned, report.baseline)
        # Ownership is acquired by the returned cleanup result, before any
        # following observation can fail or cancel. A throwing restore still
        # leaves the historical failure-finalization retry available.
        report.cleanup = cleanup
        state.cleanup_attempted = True
        realtime = observations.cleanup_realtime()
        report.cleanup_realtime = realtime
        if not cleanup.verified or not realtime.verified:
            prefix = "Router0" if router0 else "Canonical"
            if cleanup.restoration_error and realtime.error:
                report.secondary_failures += ("cleanup_realtime: " + realtime.error,)
            raise CanonicalLiveFailure(prefix + " verification completed, but cleanup/restoration did not verify: " + (cleanup.restoration_error or realtime.error))
        completed_at = self.clock()
        if not router0:
            report.closure = target.cleaned_closure
            report.cleanup_completed_at = completed_at
        attestation = CPScaleCleanupAttestation(report.run_identity, report.preflight.identity.source_head,
            receipt, cleanup, realtime, completed_at, closure=target.cleaned_closure,
            target_stage=target.target.value if router0 else "", closure_scope=report.closure_scope,
            replay=report.no_mutation_replay if router0 else None)
        report.cleanup_attestation = self.archive("cleanup", attestation, report)
        state.cleanup_attestation_archived = True
        report.closure = target.cleaned_closure
        report.cleanup_completed_at = completed_at
        self.evidence.write_progress(report)
        self.evidence.checkpoint("router0-branch" if router0 else "full-qualification", report, final=not router0)
        if router0:
            state.terminal_cleanup_complete = True
        return CPScaleTerminalEvent.ROUTER0_CLEANED if router0 else CPScaleTerminalEvent.CANONICAL_CLEANED

    def prepare_finalization(self, *, report: CPScaleRunReport, state: CPScaleFinalizationState,
                             session: CPScaleSessionPort, composition: EnterpriseReferenceComposition | None,
                             owned: frozenset[str], observations: CPScaleRunObservationPort | None) -> None:
        if (session.physical is not None and report.baseline is not None
            and not state.retain_confirmed and not state.terminal_cleanup_complete and composition is not None):
            if state.precleanup_archive is None:
                try:
                    state.precleanup_archive = self.archive("failure-precleanup", report, report)
                    report.canonical_evidence_precleanup = state.precleanup_archive
                except Exception as exc:
                    report.precleanup_archive_error = f"{type(exc).__name__}: {exc}"
                    report.secondary_failures += ("precleanup_archive: " + report.precleanup_archive_error,)
            if not state.cleanup_attempted:
                try:
                    report.cleanup = self.cleanup.restore(session.physical, composition.topology, owned, report.baseline)
                    state.cleanup_attempted = True
                    if report.cleanup.error:
                        report.secondary_failures += ("cleanup: " + report.cleanup.error,)
                    if report.cleanup.restoration_error:
                        report.secondary_failures += ("cleanup_restoration: " + report.cleanup.restoration_error,)
                except Exception as exc:
                    report.cleanup = CPScaleCleanupResult(False, error=f"{type(exc).__name__}: {exc}")
                    report.secondary_failures += ("cleanup: " + report.cleanup.error,)
            report.cleanup_realtime = observations.cleanup_realtime()
            if report.cleanup_realtime.error:
                report.secondary_failures += ("cleanup_realtime: " + report.cleanup_realtime.error,)
            if not state.cleanup_attestation_archived:
                try:
                    attestation = CPScaleCleanupAttestation(report.run_identity, report.preflight.identity.source_head,
                        state.precleanup_archive, report.cleanup, report.cleanup_realtime, self.clock(), failure=report.failure)
                    phase = "cleanup" if report.cleanup and report.cleanup.verified and report.cleanup_realtime.verified else "cleanup-incomplete"
                    report.cleanup_attestation = self.archive(phase, attestation, report)
                    state.cleanup_attestation_archived = True
                except Exception as exc:
                    report.cleanup_archive_error = f"{type(exc).__name__}: {exc}"
                    report.secondary_failures += ("cleanup_archive: " + report.cleanup_archive_error,)
        report.presentation_retained = state.retain_confirmed
