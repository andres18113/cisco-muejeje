"""Contained, atomic persistence for enterprise-services run records.

The containment is the same one `deployment_manifest_store.py` uses and for the
same reason: both path components come from outside the process. The deployment
id arrives from an MCP caller and the run id is generated here, and both go
through `safe_name_component` and then `resolve_within`, so sanitization is the
first barrier and the post-resolve containment check is the one that decides.

`run_label` is display metadata. It never reaches a path, and it never selects
which file a run writes to: a label is how a person recognizes a run, not
authority to overwrite a different one.

Writes are tmp + `os.replace`. A failed replace leaves the previous valid file
in place, which matters because the record is the only durable statement about
what a partially completed run had already done.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ...application.ports.service_run_record import RunRecordPersistenceError
from ...domain.enterprise.models.service_run_record import ServiceRunRecord
from ...shared.utils import resolve_within, safe_name_component

#: Unbound admission records have no deployment identity to file them under.
#: They are kept, because "the run was refused before it bound anything" is a
#: fact worth having, and they are kept apart, because filing them under a
#: guessed deployment id would invent the identity the refusal says is absent.
UNBOUND_DIRECTORY = "_admission"


def generate_run_id(now: datetime | None = None) -> str:
    """Generate a run id independently of anything the caller supplied.

    Sortable by time so a directory listing reads chronologically, and
    suffixed with entropy so two runs that start in the same second cannot
    collide. Never derived from `run_label`.
    """
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    return f"{moment.strftime('%Y-%m-%dT%H-%M-%SZ')}-{uuid4().hex[:8]}"


class ServiceRunRecordStore:
    """Persist one JSON record per run, under a contained local directory."""

    def __init__(self, base_dir: str | Path = Path("data") / "services") -> None:
        """Bind the store to its base directory, creating it if needed."""
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # -- lifecycle --------------------------------------------------------

    def begin(self, record: ServiceRunRecord) -> str:
        """Create the write-ahead record before any effect is dispatched."""
        return self._write(record)

    def advance(self, record: ServiceRunRecord) -> str:
        """Rewrite the record atomically at a stage boundary."""
        return self._write(record)

    def complete(self, record: ServiceRunRecord) -> str:
        """Write the terminal record."""
        return self._write(record)

    def path_for(self, deployment_id: str, run_id: str) -> Path:
        """Return the contained path one record occupies."""
        if not run_id.strip():
            raise RunRecordPersistenceError("A run record needs a run id.")
        directory = (
            safe_name_component(deployment_id, UNBOUND_DIRECTORY)
            if deployment_id.strip()
            else UNBOUND_DIRECTORY
        )
        try:
            return resolve_within(
                self.base_dir,
                directory,
                f"{safe_name_component(run_id, 'run')}.json",
            )
        except ValueError as exc:
            raise RunRecordPersistenceError(
                f"Run record path escaped the configured store: {exc}"
            ) from exc

    # -- reads ------------------------------------------------------------

    def load(self, deployment_id: str, run_id: str) -> ServiceRunRecord:
        """Read one record back, validating it against the typed contract."""
        return self._load(self.path_for(deployment_id, run_id))

    def retained_result_for(
        self,
        deployment_id: str,
        *,
        manifest_hash: str,
        configuration_semantic_hash: str,
        environment_fingerprint_hash: str,
    ) -> ServiceRunRecord | None:
        """Return the newest completed record with this exact bound identity.

        Every reuse condition of R-RET-01 that this store can decide is decided
        here, and the rest belongs to admission, which still re-verifies the
        prerequisites freshly before trusting anything:

        - the identity must match on all four values;
        - the run must have completed, so an interrupted record is never
          reused;
        - it must carry no effect uncertainty, because an action whose outcome
          is unknown is not an action whose result may be retained;
        - it must hold a configuration result, since the rows ARE the retained
          evidence.

        A corrupt file in the directory is not silently skipped: it raises, so
        a broken record is a refusal rather than an invisible absence.
        """
        if not deployment_id.strip():
            return None
        directory = resolve_within(
            self.base_dir, safe_name_component(deployment_id, UNBOUND_DIRECTORY)
        )
        if not directory.exists():
            return None
        candidates: list[ServiceRunRecord] = []
        for path in sorted(directory.glob("*.json")):
            record = self._load(path)
            if not record.identity_matches(
                deployment_id=deployment_id,
                manifest_hash=manifest_hash,
                configuration_semantic_hash=configuration_semantic_hash,
                environment_fingerprint_hash=environment_fingerprint_hash,
            ):
                continue
            if record.interrupted or record.e5_effect_uncertain:
                continue
            if record.configuration_result is None:
                continue
            candidates.append(record)
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item.created_at, item.run_id))

    # -- internals --------------------------------------------------------

    def _write(self, record: ServiceRunRecord) -> str:
        target = self.path_for(record.deployment_id, record.run_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        payload = record.model_dump_json(indent=2) + "\n"
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            # Atomic: a failure here leaves the previous valid record intact,
            # which is the whole point of writing ahead in the first place.
            os.replace(temporary, target)
        except OSError as exc:
            raise RunRecordPersistenceError(
                f"Could not persist the service run record: {exc}"
            ) from exc
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        return str(target)

    def _load(self, path: Path) -> ServiceRunRecord:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(self.base_dir):
            raise RunRecordPersistenceError(
                f"Run record path escaped the configured store: {resolved}"
            )
        try:
            return ServiceRunRecord.model_validate_json(
                resolved.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RunRecordPersistenceError(
                f"Stored service run record is unreadable: {resolved}"
            ) from exc
