from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CPScaleStageFailure:
    stage: str
    first_failed_boundary: str
    stage_outcome: str | None = None

class CanonicalLiveFailure(RuntimeError):
    """One governed stage failed after the session had acquired ownership.

    `stage_evidence` is whatever that stage had already journalled when it gave
    up. A stage that fails is exactly the stage whose read-backs are worth
    keeping, and they only exist inside `_execute_stage` until it returns.
    """

    def __init__(
        self,
        message: str,
        *,
        stage_evidence: dict[str, object] | None = None,
        partial_stage: CPScaleStageFailure | None = None,
    ) -> None:
        super().__init__(message)
        self.stage_evidence = stage_evidence
        self.partial_stage = partial_stage
