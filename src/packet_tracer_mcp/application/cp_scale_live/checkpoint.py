"""Checkpoint permission is distinct from network verification authority."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from .errors import CanonicalLiveFailure
from .run_contracts import CPScaleRunReport
from .run_ports import CPScaleEvidencePort
from ..use_cases.qualify_cp_scale_live import canonical_checkpoint_repository_error, CPScaleRepositoryState


class CPScaleCheckpointDecision(str, Enum):
    CONTINUE = "continue"
    RETAIN = "retain"


@dataclass(frozen=True)
class CPScaleCheckpointRepository:
    repository: CPScaleRepositoryState
    upstream_head: str
    dirty: bool
    governed_source_changed: bool


class CPScaleCheckpointRepositoryPort(Protocol):
    def read(self) -> CPScaleRepositoryState: ...
    def resumed(self, source_head: str) -> CPScaleCheckpointRepository: ...


class CPScaleCheckpointConsolePort(Protocol):
    def decide(self, stage: str, report: CPScaleRunReport) -> CPScaleCheckpointDecision: ...


class CPScaleCheckpoint:
    def __init__(self, *, repository: CPScaleCheckpointRepositoryPort,
                 console: CPScaleCheckpointConsolePort, persistence: CPScaleEvidencePort,
                 clock=lambda: datetime.now(timezone.utc)) -> None:
        self.repository = repository
        self.console = console
        self.persistence = persistence
        self.clock = clock

    def decide(self, stage: str, report: CPScaleRunReport, *, session_source_head: str) -> CPScaleCheckpointDecision:
        report.checkpoint = stage
        report.checkpoint_at = self.clock()
        report.checkpoint_repository = self.repository.read()
        self.persistence.write_progress(report)
        self.persistence.checkpoint(stage, report)
        command = self.console.decide(stage, report)
        resumed = self.repository.resumed(session_source_head)
        error = canonical_checkpoint_repository_error(branch=resumed.repository.branch,
            upstream=resumed.repository.upstream, head=resumed.repository.head,
            upstream_head=resumed.upstream_head, dirty=resumed.dirty,
            governed_source_changed=resumed.governed_source_changed)
        report.checkpoint_resume_repository = resumed
        self.persistence.write_progress(report)
        if resumed.repository.error or error:
            raise CanonicalLiveFailure("Checkpoint may not advance: " + (
                resumed.repository.error + " " if resumed.repository.error else "") + error)
        return command
