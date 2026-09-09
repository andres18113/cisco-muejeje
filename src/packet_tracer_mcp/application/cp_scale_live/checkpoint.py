"""Checkpoint policy returns narrow facts; publication is coordinator-owned."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

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


@dataclass(frozen=True)
class CPScaleCheckpointPrepared:
    stage: str
    at: datetime
    repository: CPScaleRepositoryState | None


@dataclass(frozen=True)
class CPScaleCheckpointPrompt:
    stage: str
    devices: int
    links: int


@dataclass(frozen=True)
class CPScaleCheckpointResumption:
    repository: CPScaleCheckpointRepository | None
    error: str


class CPScaleCheckpointRepositoryPort(Protocol):
    def read(self) -> CPScaleRepositoryState: ...
    def resumed(self, source_head: str) -> CPScaleCheckpointRepository: ...


class CPScaleCheckpointConsolePort(Protocol):
    def decide(self, prompt: CPScaleCheckpointPrompt) -> CPScaleCheckpointDecision: ...


class CPScaleCheckpoint:
    def __init__(self, *, repository: CPScaleCheckpointRepositoryPort,
                 console: CPScaleCheckpointConsolePort, persistence: CPScaleEvidencePort,
                 clock=lambda: datetime.now(timezone.utc)) -> None:
        self.repository = repository
        self.console = console
        self.persistence = persistence
        self.clock = clock

    def prepare(self, stage: str) -> CPScaleCheckpointPrepared:
        return CPScaleCheckpointPrepared(stage, self.clock(), self.repository.read())

    def publish_and_prompt(self, prepared: CPScaleCheckpointPrepared,
                           publication: CPScaleRunReport) -> CPScaleCheckpointDecision:
        self.persistence.write_progress(publication)
        self.persistence.checkpoint(prepared.stage, publication)
        return self.console.decide(CPScaleCheckpointPrompt(prepared.stage,
            publication.live_devices or 0, publication.live_links or 0))

    def resume(self, session_source_head: str) -> CPScaleCheckpointResumption:
        resumed = self.repository.resumed(session_source_head)
        error = canonical_checkpoint_repository_error(branch=resumed.repository.branch,
            upstream=resumed.repository.upstream, head=resumed.repository.head,
            upstream_head=resumed.upstream_head, dirty=resumed.dirty,
            governed_source_changed=resumed.governed_source_changed)
        failure = ("Checkpoint may not advance: " +
            (resumed.repository.error + " " if resumed.repository.error else "") + error
            if resumed.repository.error or error else "")
        return CPScaleCheckpointResumption(resumed, failure)

    def publish_resumed(self, resumed: CPScaleCheckpointResumption, publication: CPScaleRunReport) -> None:
        self.persistence.write_progress(publication)
