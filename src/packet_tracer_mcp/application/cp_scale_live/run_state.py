"""Finite immutable ledgers owned only by one coordinator execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .build_policy import CPScalePhysicalContinuity
from .checkpoint import CPScaleCheckpointPrepared, CPScaleCheckpointRepository
from .contracts import CPScaleLiveStageResult, CPScaleObservationRecord, CPScalePreflightResult
from .run_contracts import (
    CPScaleBridgeStatus, CPScaleCapabilityQualification, CPScaleStageProgress,
    CPScaleResumeGate, CPScaleRunReplayAudit, CPScaleCleanupResult, CPScaleCleanupRealtime,
    CPScaleRunOutcome, CPScaleTerminalEvent,
    CPScaleRunReport,
)
from ..use_cases.compose_cp_scale_canonical import CPScaleCanonicalStageTransition
from ..use_cases.compose_enterprise_reference import EnterpriseReferenceComposition
from ..use_cases.qualify_cp_scale_live import CPScaleEvidenceArchive, CPScaleFinalDisposition
from ...domain.enterprise.models.physical_deployment import PhysicalWorkspaceObservation


@dataclass(frozen=True)
class CPScaleQualificationState:
    bridge: CPScaleBridgeStatus | None = None
    baseline: PhysicalWorkspaceObservation | None = None
    composition: EnterpriseReferenceComposition | None = None
    capabilities: CPScaleCapabilityQualification | None = None


@dataclass(frozen=True)
class CPScaleProgressState:
    physical: CPScalePhysicalContinuity = field(default_factory=CPScalePhysicalContinuity)
    stages: tuple[CPScaleStageProgress, ...] = ()
    active_stage: CPScaleStageProgress | None = None
    resume_gates: tuple[CPScaleResumeGate, ...] = ()
    network_boundaries: tuple[tuple[str, CPScaleObservationRecord], ...] = ()
    router0_transition: CPScaleCanonicalStageTransition | None = None
    full_qualification: CPScaleLiveStageResult | None = None
    live_devices: int | None = None
    live_links: int | None = None
    checkpoint: CPScaleCheckpointPrepared | None = None
    checkpoint_resumption: CPScaleCheckpointRepository | None = None


@dataclass(frozen=True)
class CPScaleTerminalState:
    outcome: CPScaleRunOutcome | None = None
    event: CPScaleTerminalEvent | None = None
    hard_stop: str = ""
    failure: str = ""
    secondary_failures: tuple[str, ...] = ()
    finalization_errors: tuple[str, ...] = ()
    disposition: CPScaleFinalDisposition | None = None
    closure: str = ""
    closure_scope: str = ""
    completed_at: datetime | None = None
    cleanup_completed_at: datetime | None = None
    replay: CPScaleRunReplayAudit | None = None
    cleanup: CPScaleCleanupResult | None = None
    realtime: CPScaleCleanupRealtime | None = None
    precleanup: CPScaleEvidenceArchive | None = None
    attestation: CPScaleEvidenceArchive | None = None
    archives: tuple[CPScaleEvidenceArchive, ...] = ()
    retained: bool = False
    cleanup_attempted: bool = False
    terminal_cleanup_complete: bool = False
    precleanup_archive_error: str = ""
    cleanup_archive_error: str = ""


def publication_snapshot(preflight: CPScalePreflightResult, run_identity: str, started_at: datetime,
                         version: str, qualification: CPScaleQualificationState,
                         progress: CPScaleProgressState, terminal: CPScaleTerminalState) -> CPScaleRunReport:
    """Read-only compatibility projection; no state/effect is acquired here."""
    checkpoint = progress.checkpoint
    return CPScaleRunReport(preflight, run_identity, started_at, version,
        stages=progress.stages, presentation_retained=terminal.retained,
        hard_stop=terminal.hard_stop, failure=terminal.failure, http_bridge=qualification.bridge,
        baseline=qualification.baseline, capability_prequalification=qualification.capabilities,
        active_stage=progress.active_stage, router0_transition=progress.router0_transition,
        resume_gates=progress.resume_gates, network_boundaries=progress.network_boundaries,
        full_qualification=progress.full_qualification, live_devices=progress.live_devices,
        live_links=progress.live_links, no_mutation_replay=terminal.replay,
        final_disposition=terminal.disposition, closure_scope=terminal.closure_scope,
        closure=terminal.closure, completed_at=terminal.completed_at,
        cleanup_completed_at=terminal.cleanup_completed_at, cleanup=terminal.cleanup,
        cleanup_realtime=terminal.realtime, canonical_evidence_precleanup=terminal.precleanup,
        cleanup_attestation=terminal.attestation, archives=terminal.archives,
        precleanup_archive_error=terminal.precleanup_archive_error,
        cleanup_archive_error=terminal.cleanup_archive_error,
        secondary_failures=terminal.secondary_failures, finalization_errors=terminal.finalization_errors,
        checkpoint=checkpoint.stage if checkpoint else "", checkpoint_at=checkpoint.at if checkpoint else None,
        checkpoint_repository=checkpoint.repository if checkpoint else None,
        checkpoint_resume_repository=progress.checkpoint_resumption)
