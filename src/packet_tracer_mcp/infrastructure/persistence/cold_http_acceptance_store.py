"""Contained, atomic, write-once persistence for cold-HTTP acceptance envelopes.

It follows the qualification record store: the attempt identity is the only
value that reaches a path, and it goes through `safe_name_component` and then
`resolve_within`; every write goes to a temporary file first. Unlike that store,
nothing here is ever rewritten. The write-ahead envelope is created before any
contact, and the terminal envelope is created beside it exactly once. Both are
atomic no-overwrite creations, so two completions cannot both succeed and a
completed envelope can never be replaced: earlier evidence is never rewritten.
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from ...application.ports.service_run_record import RunRecordPersistenceError
from ...domain.enterprise.models.cold_http_acceptance import (
    ColdHttpAcceptanceEnvelope,
)
from ...shared.utils import resolve_within, safe_name_component

COMPLETED_SUFFIX = ".completed.json"


class ColdHttpAcceptanceStore:
    """Persist one write-ahead and one terminal JSON envelope per attempt."""

    def __init__(self, base_dir: str | Path) -> None:
        """Bind the store to its directory without touching the filesystem."""
        self.base_dir = Path(base_dir).absolute()

    def path_for(self, attempt_id: str) -> Path:
        """Return the contained path of one attempt's write-ahead envelope."""
        return self._contained(attempt_id, ".json")

    def completed_path_for(self, attempt_id: str) -> Path:
        """Return the contained path of one attempt's terminal envelope."""
        return self._contained(attempt_id, COMPLETED_SUFFIX)

    def begin(self, envelope: ColdHttpAcceptanceEnvelope) -> str:
        """Create the write-ahead envelope; an existing one refuses."""
        if envelope.completed_at is not None:
            raise RunRecordPersistenceError("A begun envelope cannot be completed.")
        path = self.path_for(envelope.attempt_id)
        self._create(path, envelope, "An acceptance envelope already exists.")
        return str(path)

    def complete(self, envelope: ColdHttpAcceptanceEnvelope) -> str:
        """Create the terminal envelope once, beside its own write-ahead one."""
        if envelope.completed_at is None:
            raise RunRecordPersistenceError("A completed envelope needs completed_at.")
        begun_path = self.path_for(envelope.attempt_id)
        if not begun_path.exists():
            raise RunRecordPersistenceError(
                "An acceptance envelope must be begun before it completes."
            )
        begun = self._read(begun_path)
        if begun.started_at != envelope.started_at:
            raise RunRecordPersistenceError(
                "The stored envelope belongs to another invocation."
            )
        path = self.completed_path_for(envelope.attempt_id)
        self._create(path, envelope, "A completed acceptance envelope is immutable.")
        return str(path)

    def load(self, attempt_id: str) -> ColdHttpAcceptanceEnvelope:
        """Return the terminal envelope, or the write-ahead one if none exists."""
        completed = self.completed_path_for(attempt_id)
        if completed.exists():
            return self._read(completed)
        return self._read(self.path_for(attempt_id))

    def _contained(self, attempt_id: str, suffix: str) -> Path:
        if not attempt_id or safe_name_component(attempt_id, "") != attempt_id:
            raise RunRecordPersistenceError("The attempt identity is not a safe name.")
        try:
            return resolve_within(self.base_dir, f"{attempt_id}{suffix}")
        except ValueError as exc:
            raise RunRecordPersistenceError(
                f"Acceptance envelope path escaped the store: {exc}"
            ) from exc

    @staticmethod
    def _read(path: Path) -> ColdHttpAcceptanceEnvelope:
        try:
            return ColdHttpAcceptanceEnvelope.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise RunRecordPersistenceError(
                f"Acceptance envelope is unreadable: {type(exc).__name__}"
            ) from exc

    @staticmethod
    def _create(path: Path, envelope: ColdHttpAcceptanceEnvelope, exists: str) -> None:
        """Write to a temporary file, then link it in only if nothing is there."""
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        payload = envelope.model_dump_json(indent=2) + "\n"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, path)
        except FileExistsError as exc:
            raise RunRecordPersistenceError(exists) from exc
        except OSError as exc:
            raise RunRecordPersistenceError(
                f"Acceptance envelope could not be written: {type(exc).__name__}"
            ) from exc
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
