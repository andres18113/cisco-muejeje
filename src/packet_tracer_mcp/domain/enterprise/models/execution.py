"""Shared action operation, execution journal, and dirty-state semantics."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class OperationSemantics(str, Enum):
    ENSURE_PRESENT = "ensure_present"
    ENSURE_ABSENT = "ensure_absent"
    SET_VALUE = "set_value"
    REPLACE = "replace"
    TRANSITION = "transition"
    EXECUTE_ONCE = "execute_once"


class MutationDisposition(str, Enum):
    CHANGED = "changed"
    NO_OP = "no_op"
    REASSERTED = "reasserted"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


class DirtyState(str, Enum):
    CLEAN = "clean"
    DIRTY_RECOVERABLE = "dirty_recoverable"
    DIRTY_UNRECOVERABLE = "dirty_unrecoverable"
    UNKNOWN = "unknown"


class CompensationStatus(str, Enum):
    NOT_AVAILABLE = "not_available"
    AVAILABLE = "available"
    NOT_ATTEMPTED = "not_attempted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ExecutionJournalEntry(BaseModel):
    ordinal: int
    action_id: str
    operation: OperationSemantics
    disposition: MutationDisposition
    batch_id: str = ""
    inverse_action_id: str = ""
    inverse_available: bool = False
    compensation_status: CompensationStatus = CompensationStatus.NOT_AVAILABLE
    message: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ApplicationExecutionJournal(BaseModel):
    plan_id: str
    deployment_id: str = ""
    entries: list[ExecutionJournalEntry] = Field(default_factory=list)
    dirty_state: DirtyState = DirtyState.CLEAN
    preflight_errors: list[str] = Field(default_factory=list)
    cleanup_status: CompensationStatus = CompensationStatus.NOT_ATTEMPTED

    def append(self, entry: ExecutionJournalEntry) -> None:
        expected = len(self.entries) + 1
        if entry.ordinal != expected:
            raise ValueError(
                f"Journal ordinal {entry.ordinal} is invalid; expected {expected}."
            )
        self.entries.append(entry)
        self.dirty_state = _derive_dirty_state(self.entries)

    def mark_preflight_failure(self, message: str) -> None:
        self.preflight_errors.append(message)
        if not self.entries:
            self.dirty_state = DirtyState.CLEAN

    def mark_transport_unknown(self, message: str = "") -> None:
        if message:
            self.preflight_errors.append(message)
        self.dirty_state = DirtyState.UNKNOWN

    def mark_cleanup(self, status: CompensationStatus) -> None:
        self.cleanup_status = status
        if status is CompensationStatus.SUCCEEDED:
            self.dirty_state = DirtyState.CLEAN
        elif status is CompensationStatus.FAILED:
            self.dirty_state = DirtyState.DIRTY_UNRECOVERABLE
        elif status is CompensationStatus.UNKNOWN:
            self.dirty_state = DirtyState.UNKNOWN

    def compact_summary(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for entry in self.entries:
            counts[entry.disposition.value] = counts.get(entry.disposition.value, 0) + 1
        return {
            "plan_id": self.plan_id,
            "deployment_id": self.deployment_id,
            "attempted": len(self.entries),
            "counts": dict(sorted(counts.items())),
            "dirty_state": self.dirty_state.value,
            "cleanup_status": self.cleanup_status.value,
            "preflight_errors": list(self.preflight_errors),
        }


def satisfies_apply_dependency(status: Any) -> bool:
    value = status.value if isinstance(status, Enum) else str(status)
    return value in {"applied", "no_op", "reasserted", "verified"}


def disposition_from_status(status: Any) -> MutationDisposition:
    value = status.value if isinstance(status, Enum) else str(status)
    return {
        "applied": MutationDisposition.REASSERTED,
        "no_op": MutationDisposition.NO_OP,
        "reasserted": MutationDisposition.REASSERTED,
        "failed": MutationDisposition.FAILED,
        "dependency_blocked": MutationDisposition.BLOCKED,
        "skipped": MutationDisposition.SKIPPED,
    }.get(value, MutationDisposition.UNKNOWN)


def journal_from_action_results(
    *, plan_id: str, deployment_id: str, actions: list[Any], results: list[Any],
) -> ApplicationExecutionJournal:
    actions_by_id = {item.id: item for item in actions}
    operations = {
        identifier: getattr(item, "operation", OperationSemantics.SET_VALUE)
        for identifier, item in actions_by_id.items()
    }
    journal = ApplicationExecutionJournal(plan_id=plan_id, deployment_id=deployment_id)
    for ordinal, result in enumerate(results, start=1):
        explicit_disposition = getattr(
            result, "disposition", MutationDisposition.UNKNOWN,
        )
        journal.append(ExecutionJournalEntry(
            ordinal=ordinal,
            action_id=result.action_id,
            operation=operations.get(result.action_id, OperationSemantics.SET_VALUE),
            disposition=(
                explicit_disposition
                if explicit_disposition is not MutationDisposition.UNKNOWN
                else disposition_from_status(result.status)
            ),
            batch_id=getattr(result, "batch_id", ""),
            inverse_action_id=getattr(
                actions_by_id.get(result.action_id), "inverse_action_id", "",
            ),
            inverse_available=getattr(
                actions_by_id.get(result.action_id), "compensation_available", False,
            ),
            message=getattr(result, "message", ""),
        ))
    return journal


def _derive_dirty_state(entries: list[ExecutionJournalEntry]) -> DirtyState:
    if not entries:
        return DirtyState.CLEAN
    if any(item.disposition is MutationDisposition.UNKNOWN for item in entries):
        return DirtyState.UNKNOWN
    failed = any(item.disposition is MutationDisposition.FAILED for item in entries)
    mutations = [
        item for item in entries
        if item.disposition in {MutationDisposition.CHANGED, MutationDisposition.REASSERTED}
    ]
    if not failed:
        return DirtyState.CLEAN
    if not mutations:
        return DirtyState.CLEAN
    if all(item.inverse_available for item in mutations):
        return DirtyState.DIRTY_RECOVERABLE
    return DirtyState.DIRTY_UNRECOVERABLE
