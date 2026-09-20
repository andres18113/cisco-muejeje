"""Contained, atomic persistence for qualification stage records.

It follows the S1 run-record store: every path component that is derived from
a value goes through `safe_name_component` and then `resolve_within`, writes are
tmp plus `os.replace`, and `begin` is create-only, so a run can never overwrite
another run's record. One rule is added. A record that reached a terminal
outcome is never rewritten, because earlier evidence is immutable, and a
completed record is what later reviews cite.

`ServiceRunRecordStore` is not reused directly: a stage record has no
deployment or manifest identity to file it under, and it carries an
authorization, a ledger and measurements that `ServiceRunRecord` does not
model. The failure type is shared (`RunRecordPersistenceError`).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from ...application.ports.service_run_record import RunRecordPersistenceError
from ...domain.enterprise.models.service_qualification import QualificationRecord
from ...shared.utils import resolve_within, safe_name_component


class QualificationRecordStore:
    """Persist one JSON record per qualification run."""

    def __init__(self, base_dir: str | Path) -> None:
        """Bind the store to its directory without touching the filesystem."""
        self.base_dir = Path(base_dir).absolute()

    def path_for(self, record: QualificationRecord) -> Path:
        """Return the contained path of one stage record."""
        if not record.run_id.strip():
            raise RunRecordPersistenceError("A qualification record needs a run id.")
        stage = safe_name_component(record.stage.value.lower(), "stage")
        name = safe_name_component(f"{stage}-{record.run_id}", "run")
        try:
            return resolve_within(self.base_dir, stage, f"{name}.json")
        except ValueError as exc:
            raise RunRecordPersistenceError(
                f"Qualification record path escaped the store: {exc}"
            ) from exc

    def begin(self, record: QualificationRecord) -> str:
        """Create the record before any contact; an existing file refuses."""
        return self._write(record, create_only=True)

    def advance(self, record: QualificationRecord) -> str:
        """Rewrite a started, not yet completed record at a step boundary."""
        return self._write(record, create_only=False)

    def complete(self, record: QualificationRecord) -> str:
        """Write the terminal record; later writes are refused."""
        if record.completed_at is None:
            raise RunRecordPersistenceError("A completed record needs completed_at.")
        return self._write(record, create_only=False)

    def attempt_exists(self, attempt_id: str) -> bool:
        """Whether any stored record already names this attempt identity.

        Uniqueness is decided from the records themselves, never from the
        caller's word. A malformed identity is refused rather than searched
        for, and a record this store cannot read counts as a match: an
        unreadable file is not proof that the attempt is new, and this control
        fails closed.
        """
        if not attempt_id or safe_name_component(attempt_id, "") != attempt_id:
            raise RunRecordPersistenceError("The attempt identity is not a safe name.")
        if not self.base_dir.exists():
            return False
        for path in sorted(self.base_dir.rglob("*.json")):
            try:
                stored = QualificationRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                return True
            if str(stored.authorization.get("attempt_id") or "") == attempt_id:
                return True
        return False

    def load(self, path: str | Path) -> QualificationRecord:
        """Read one record back and validate it against the typed contract."""
        try:
            resolved = Path(path).resolve()
            if not resolved.is_relative_to(self.base_dir.resolve()):
                raise ValueError("the path is outside the store")
            return QualificationRecord.model_validate_json(
                resolved.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise RunRecordPersistenceError(
                f"Qualification record is unreadable: {type(exc).__name__}"
            ) from exc

    def _write(self, record: QualificationRecord, *, create_only: bool) -> str:
        path = self.path_for(record)
        try:
            exists = path.exists()
            if create_only and exists:
                raise RunRecordPersistenceError(
                    "A qualification record already exists for this run id."
                )
            if not create_only:
                if not exists:
                    raise RunRecordPersistenceError(
                        "A qualification record must be begun before it advances."
                    )
                previous = QualificationRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
                if previous.completed_at is not None:
                    raise RunRecordPersistenceError(
                        "A completed qualification record is immutable."
                    )
                if (previous.run_id, previous.stage) != (record.run_id, record.stage):
                    raise RunRecordPersistenceError(
                        "The stored record belongs to another run."
                    )
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            payload = json.dumps(record.model_dump(mode="json"), indent=2)
            try:
                temporary.write_text(payload, encoding="utf-8")
                os.replace(temporary, path)
            finally:
                if temporary.exists():
                    temporary.unlink()
        except RunRecordPersistenceError:
            raise
        except (OSError, ValueError) as exc:
            raise RunRecordPersistenceError(
                f"Qualification record could not be written: {type(exc).__name__}"
            ) from exc
        return str(path)
