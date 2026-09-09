from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CPScaleStageFailure:
    stage: str
    first_failed_boundary: str
    stage_outcome: str | None = None

class CanonicalLiveFailure(RuntimeError):
    """One governed operation failed after the session acquired its facts."""

    def __init__(
        self,
        message: str,
        *,
        partial_stage: CPScaleStageFailure | None = None,
    ) -> None:
        super().__init__(message)
        self.partial_stage = partial_stage
