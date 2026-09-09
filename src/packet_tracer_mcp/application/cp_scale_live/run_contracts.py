"""Bounded run facts; no services, transport, operator or captured callbacks."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .checkpoint import CPScaleCheckpointRepository

from .contracts import CPScaleLiveStageResult, CPScaleObservationRecord, CPScalePreflightResult
from .contracts import CPScaleLiveSessionIdentity
from .errors import CPScaleStageFailure
from ..use_cases.compose_cp_scale_canonical import CPScaleCanonicalStageProjection, CPScaleCanonicalStageTransition, CPScaleCanonicalStage, CPScaleCanonicalTarget
from ..use_cases.qualify_cp_scale_live import CPScaleEvidenceArchive, CPScaleRepositoryState, CPScaleFinalDisposition
from ..use_cases.compose_enterprise_reference import EnterpriseReferenceComposition
from ...domain.enterprise.models.physical_deployment import PhysicalDeploymentResult, PhysicalWorkspaceObservation, PhysicalMutationResult
from ...domain.enterprise.models.discovery import CapabilitySnapshot


@dataclass(frozen=True)
class CPScaleStageProgress:
    projection: CPScaleCanonicalStageProjection
    delta: PhysicalDeploymentResult | None = None
    deployment: PhysicalDeploymentResult | None = None
    transition: CPScaleCanonicalStageTransition | None = None
    result: CPScaleLiveStageResult | None = None
    dhcp_baseline: CPScaleObservationRecord | None = None
    failed: bool = False
    remaining: bool = False
    failure_details: CPScaleStageFailure | None = None


@dataclass(frozen=True)
class CPScaleCleanupResult:
    verified: bool
    restoration_error: str = ""
    mutations: tuple[PhysicalMutationResult, ...] | None = None
    first: PhysicalWorkspaceObservation | None = None
    second: PhysicalWorkspaceObservation | None = None
    error: str = ""


@dataclass(frozen=True)
class CPScaleCleanupRealtime:
    verified: bool
    error: str = ""
    state: dict[str, object] | None = None


@dataclass(frozen=True)
class CPScaleCapabilityProbe:
    model: str
    required: tuple[str, ...]
    snapshot: CapabilitySnapshot
    cached: bool
    error: str


@dataclass(frozen=True)
class CPScaleCapabilityQualification:
    requirements: tuple[tuple[str, tuple[str, ...]], ...]
    sessions: tuple[CPScaleCapabilityProbe, ...]
    first: PhysicalWorkspaceObservation | None = None
    second: PhysicalWorkspaceObservation | None = None
    restoration_error: str = ""
    unresolved: tuple[str, ...] | None = None


@dataclass(frozen=True)
class CPScaleResumeGate:
    before_stage: str
    bridge: dict[str, object]
    observations: tuple[PhysicalWorkspaceObservation, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class CPScaleRunReplayAudit:
    audited_stages: tuple[str, ...]
    stages_without_verified_audit: tuple[str, ...]
    replayed_retained_ids: tuple[str, ...]

    @property
    def verified(self) -> bool:
        return not self.stages_without_verified_audit


@dataclass(frozen=True)
class CPScaleCleanupAttestation:
    run_identity: str
    source_head: str
    precleanup: CPScaleEvidenceArchive | None
    cleanup: CPScaleCleanupResult | None
    realtime: CPScaleCleanupRealtime
    completed_at: datetime
    closure: str = ""
    failure: str | None = None
    target_stage: str = ""
    closure_scope: str = ""
    replay: CPScaleRunReplayAudit | None = None


@dataclass
class CPScaleFinalizationState:
    """One coordinator execution owns this finite terminal-obligation ledger."""
    retain_confirmed: bool = False
    cleanup_attempted: bool = False
    cleanup_attestation_archived: bool = False
    terminal_cleanup_complete: bool = False
    precleanup_archive: CPScaleEvidenceArchive | None = None


@dataclass
class CPScaleBackendProgress:
    composition: EnterpriseReferenceComposition | None = None


class CPScaleRunOutcome(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class CPScaleLiveProgress:
    target: CPScaleCanonicalTarget
    completed_stages: tuple[CPScaleLiveStageResult, ...]
    active_stage: CPScaleCanonicalStage | None
    first_failed_boundary: str | None
    checkpoint_stage: str | None
    remaining_reconciled: bool


@dataclass(frozen=True)
class CPScaleLiveFinalResult:
    identity: CPScaleLiveSessionIdentity | None
    outcome: CPScaleRunOutcome
    target: CPScaleCanonicalTarget
    progress: CPScaleLiveProgress
    final_disposition: CPScaleFinalDisposition | None
    closure: str | None
    presentation_retained: bool
    cleanup: CPScaleCleanupResult | None
    archives: tuple[CPScaleEvidenceArchive, ...]
    primary_failure: str | None
    secondary_failures: tuple[str, ...]

    @classmethod
    def from_report(cls, outcome: CPScaleRunOutcome, report: CPScaleRunReport) -> CPScaleLiveFinalResult:
        stages = tuple(item.result for item in report.stages if item.result is not None)
        return cls(report.preflight.identity, outcome, report.preflight.target.target,
            CPScaleLiveProgress(report.preflight.target.target, stages,
                report.active_stage.projection.stage if report.active_stage else None,
                next((item.first_failed_boundary for item in stages if item.first_failed_boundary), None),
                report.checkpoint or None, any(item.remaining for item in report.stages)),
            report.final_disposition,
            report.closure or None, report.presentation_retained, report.cleanup, report.archives,
            report.failure or report.hard_stop or None, report.finalization_errors)


@dataclass
class CPScaleRunReport:
    """Publication facts owned by one execution, bounded by its target contract.

    Stages reference the original results and journals; serializers alone
    expand them. Archives contain receipts once per reached phase.
    """
    preflight: CPScalePreflightResult
    run_identity: str
    started_at: datetime
    packet_tracer_version: str
    stages: tuple[CPScaleStageProgress, ...] = ()
    presentation_retained: bool = False
    hard_stop: str = ""
    failure: str = ""
    http_bridge: dict[str, object] | None = None
    baseline: PhysicalWorkspaceObservation | None = None
    capability_prequalification: CPScaleCapabilityQualification | None = None
    active_stage: CPScaleStageProgress | None = None
    router0_transition: CPScaleCanonicalStageTransition | None = None
    resume_gates: tuple[CPScaleResumeGate, ...] = ()
    network_boundaries: tuple[tuple[str, CPScaleObservationRecord], ...] = ()
    full_qualification: CPScaleLiveStageResult | None = None
    live_devices: int | None = None
    live_links: int | None = None
    no_mutation_replay: CPScaleRunReplayAudit | None = None
    final_disposition: CPScaleFinalDisposition | None = None
    closure_scope: str = ""
    closure: str = ""
    completed_at: datetime | None = None
    cleanup_completed_at: datetime | None = None
    cleanup: CPScaleCleanupResult | None = None
    cleanup_realtime: CPScaleCleanupRealtime | None = None
    canonical_evidence_precleanup: CPScaleEvidenceArchive | None = None
    cleanup_attestation: CPScaleEvidenceArchive | None = None
    archives: tuple[CPScaleEvidenceArchive, ...] = ()
    precleanup_archive_error: str = ""
    cleanup_archive_error: str = ""
    finalization_errors: tuple[str, ...] = ()
    checkpoint: str = ""
    checkpoint_at: datetime | None = None
    checkpoint_repository: CPScaleRepositoryState | None = None
    checkpoint_resume_repository: CPScaleCheckpointRepository | None = None

    @property
    def completed_stage_limit(self) -> int:
        return len(self.preflight.target.build_stages) + int(self.preflight.target.run_remaining_reconciliation)

    @property
    def archive_phase_limit(self) -> int:
        return 2
