"""Contained, atomic, write-once persistence for cold-HTTP acceptance envelopes.

It follows the qualification record store: the attempt identity is the only
value that reaches a path, and it goes through `safe_name_component` and then
`resolve_within`; every write goes to a temporary file first. Unlike that store,
nothing here is ever rewritten. The write-ahead envelope is created before any
contact, and the terminal envelope is created beside it exactly once. Both are
atomic no-overwrite creations, so two completions cannot both succeed and a
completed envelope can never be replaced: earlier evidence is never rewritten.

The terminal link is the publication point. `complete` lets its caller decide
again after every step that shapes the published bytes -- the begun
envelope's reload, the serialization, the flush -- the last one immediately
before the link; a checkpoint that raises leaves nothing linked. After the
link, the caller records one write-once publication fact beside the envelope,
bound to the terminal file's digest.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from ...application.ports.service_run_record import RunRecordPersistenceError
from ...domain.enterprise.models.cold_http_acceptance import (
    AcceptancePublication,
    ColdHttpAcceptanceEnvelope,
)
from ...shared.utils import resolve_within, safe_name_component

COMPLETED_SUFFIX = ".completed.json"
PUBLICATION_SUFFIX = ".publication.json"

#: Called with the name of each step of `complete` once it is done.
Checkpoint = Callable[[str], None]


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

    def publication_path_for(self, attempt_id: str) -> Path:
        """Return the contained path of one attempt's publication fact."""
        return self._contained(attempt_id, PUBLICATION_SUFFIX)

    def begin(self, envelope: ColdHttpAcceptanceEnvelope) -> str:
        """Create the write-ahead envelope; an existing one refuses."""
        if envelope.completed_at is not None:
            raise RunRecordPersistenceError("A begun envelope cannot be completed.")
        path = self.path_for(envelope.attempt_id)
        self._create(path, envelope, "An acceptance envelope already exists.")
        return str(path)

    def complete(
        self,
        envelope: ColdHttpAcceptanceEnvelope,
        *,
        checkpoint: Checkpoint | None = None,
    ) -> str:
        """Create the terminal envelope once, beside its own write-ahead one.

        `checkpoint` is called after the begun envelope's reload
        (`envelope_reload`), after serialization (`envelope_serialization`) and
        after the flush (`envelope_flush`), which is immediately before the
        link. If it raises, nothing is linked and its exception propagates.
        """
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
        if checkpoint is not None:
            checkpoint("envelope_reload")
        path = self.completed_path_for(envelope.attempt_id)
        self._create(
            path,
            envelope,
            "A completed acceptance envelope is immutable.",
            checkpoint=checkpoint,
        )
        return str(path)

    def record_publication(
        self, publication: AcceptancePublication
    ) -> tuple[str, AcceptancePublication]:
        """Record the publication fact of this invocation's terminal envelope once.

        The fact is bound to the terminal file's SHA-256, read here; a terminal
        envelope of another invocation, or none, refuses.
        """
        terminal = self.completed_path_for(publication.attempt_id)
        found = self._read(terminal)
        if (
            found.attempt_id != publication.attempt_id
            or found.started_at != publication.started_at
        ):
            raise RunRecordPersistenceError(
                "The terminal envelope belongs to another invocation."
            )
        try:
            digest = hashlib.sha256(terminal.read_bytes()).hexdigest()
        except OSError as exc:
            raise RunRecordPersistenceError(
                f"Acceptance envelope is unreadable: {type(exc).__name__}"
            ) from exc
        recorded = publication.model_copy(
            update={"terminal_path": str(terminal), "terminal_sha256": digest}
        )
        path = self.publication_path_for(publication.attempt_id)
        self._create(path, recorded, "A publication fact is immutable.")
        return str(path), recorded

    def stored_publication(self, envelope: ColdHttpAcceptanceEnvelope) -> str | None:
        """Return the path of this invocation's publication fact, or None.

        An unreadable fact raises, because whose it is cannot be known.
        """
        path = self.publication_path_for(envelope.attempt_id)
        if not path.exists():
            return None
        found = self.load_publication(envelope.attempt_id)
        if (
            found.attempt_id != envelope.attempt_id
            or found.started_at != envelope.started_at
        ):
            return None
        return str(path)

    def load_publication(self, attempt_id: str) -> AcceptancePublication:
        """Return the recorded publication fact of one attempt."""
        path = self.publication_path_for(attempt_id)
        try:
            return AcceptancePublication.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise RunRecordPersistenceError(
                f"Publication fact is unreadable: {type(exc).__name__}"
            ) from exc

    def stored(
        self, envelope: ColdHttpAcceptanceEnvelope, *, completed: bool
    ) -> str | None:
        """Return the path this invocation stored at one stage, or None.

        An invocation is its attempt identity and its `started_at`; a file of
        another invocation, or none, answers None. An unreadable file raises,
        because whether it is this invocation's cannot be known.
        """
        if completed:
            path = self.completed_path_for(envelope.attempt_id)
        else:
            path = self.path_for(envelope.attempt_id)
        if not path.exists():
            return None
        found = self._read(path)
        if (
            found.attempt_id != envelope.attempt_id
            or found.started_at != envelope.started_at
        ):
            return None
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
    def _create(
        path: Path,
        document: BaseModel,
        exists: str,
        *,
        checkpoint: Checkpoint | None = None,
    ) -> None:
        """Write to a temporary file, then link it in only if nothing is there."""
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        payload = document.model_dump_json(indent=2) + "\n"
        if checkpoint is not None:
            checkpoint("envelope_serialization")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if checkpoint is not None:
                # The last controlled instant before publication.
                checkpoint("envelope_flush")
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
