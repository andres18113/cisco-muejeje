"""Only ordered stepping, exact continuity threading and first-failure stop."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

StageId = TypeVar("StageId")
Continuity = TypeVar("Continuity")
Value = TypeVar("Value")


@dataclass(frozen=True)
class StageStepResult(Generic[Continuity, Value]):
    value: Value
    continuity: Continuity
    succeeded: bool
    secondary_failures: tuple[str, ...] = ()


class StageStepPort(Protocol[StageId, Continuity, Value]):
    def __call__(self, stage: StageId, continuity: Continuity) -> StageStepResult[Continuity, Value]: ...


@dataclass(frozen=True)
class StageSequenceResult(Generic[Continuity, Value]):
    steps: tuple[StageStepResult[Continuity, Value], ...]
    continuity: Continuity
    succeeded: bool
    secondary_failures: tuple[str, ...]


def execute_stage_sequence(stages: tuple[StageId, ...], initial: Continuity,
                           step: StageStepPort[StageId, Continuity, Value]) -> StageSequenceResult[Continuity, Value]:
    completed: list[StageStepResult[Continuity, Value]] = []
    continuity = initial
    secondaries: list[str] = []
    for stage in stages:
        acquired = step(stage, continuity)
        completed.append(acquired)
        continuity = acquired.continuity
        secondaries.extend(acquired.secondary_failures)
        if not acquired.succeeded:
            return StageSequenceResult(
                tuple(completed), continuity, False, tuple(secondaries),
            )
    return StageSequenceResult(
        tuple(completed), continuity, True, tuple(secondaries),
    )
