"""Effect boundaries consumed by the CP-SCALE coordinator."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from .checkpoint import CPScaleCheckpointDecision

from .contracts import CPScaleLiveRequest, CPScalePreflightResult, CPScaleStageExecutionInput, CPScaleLiveStageResult
from .run_contracts import CPScaleRunReport, CPScaleCleanupAttestation, CPScaleBackendProgress, CPScaleTerminalEvent
from .session import CPScaleSessionPort, CPScaleRunObservationPort
from ..use_cases.compose_enterprise_reference import EnterpriseReferenceComposition
from ..use_cases.qualify_cp_scale_live import CPScaleEvidenceArchive


class CPScalePreflightPort(Protocol):
    def inspect(self, request: CPScaleLiveRequest, *, run_identity: str, started_at: datetime) -> CPScalePreflightResult: ...


class CPScaleStageExecutorPort(Protocol):
    def execute(self, request: CPScaleStageExecutionInput) -> CPScaleLiveStageResult: ...


class CPScaleEvidencePort(Protocol):
    def write_progress(self, report: CPScaleRunReport) -> None: ...
    def checkpoint(self, stage: str, report: CPScaleRunReport, *, final: bool = False) -> None: ...
    def archive(self, phase: str, payload: CPScaleRunReport | CPScaleCleanupAttestation, *, run_identity: str) -> CPScaleEvidenceArchive: ...


class CPScaleCheckpointPort(Protocol):
    def decide(self, stage: str, report: CPScaleRunReport, *, session_source_head: str) -> CPScaleCheckpointDecision: ...


class CPScalePresentationPort(Protocol):
    def core_rematerialized(self) -> None: ...
    def terminal(self, event: CPScaleTerminalEvent, report: CPScaleRunReport) -> None: ...
    def finalization_incomplete(self, report: CPScaleRunReport) -> None: ...


class CPScaleBackendPort(Protocol):
    def qualify(self, session: CPScaleSessionPort, report: CPScaleRunReport, progress: CPScaleBackendProgress) -> EnterpriseReferenceComposition: ...
    def polling_failure_status(self, session: CPScaleSessionPort) -> dict[str, object]: ...
