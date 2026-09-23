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

import hashlib
import json
import os
from datetime import datetime
from itertools import islice
from pathlib import Path
from uuid import uuid4

from ...application.ports.service_run_record import RunRecordPersistenceError
from ...domain.enterprise.models.configuration_runtime import (
    ConfigurationFailureCode,
)
from ...domain.enterprise.models.execution import satisfies_apply_dependency
from ...domain.enterprise.models.service_run_record import (
    ServiceRunRecord,
)
from ...domain.enterprise.models.service_run_record import (
    generate_run_id as _generate_run_id,
)
from ...shared.utils import resolve_within, safe_name_component

#: Unbound admission records have no deployment identity to file them under.
#: They are kept, because "the run was refused before it bound anything" is a
#: fact worth having, and they are kept apart, because filing them under a
#: guessed deployment id would invent the identity the refusal says is absent.
UNBOUND_DIRECTORY = "_admission"
MAX_RETENTION_RECORDS = 256


def generate_run_id(now: datetime | None = None) -> str:
    """Backward-compatible import path for the domain run-id generator."""
    return _generate_run_id(now)


class ServiceRunRecordStore:
    """Persist one JSON record per run, under a contained local directory."""

    def __init__(self, base_dir: str | Path = Path("data") / "services") -> None:
        """Bind the store path without touching the filesystem."""
        self.base_dir = Path(base_dir).absolute()

    # -- lifecycle --------------------------------------------------------

    def begin(self, record: ServiceRunRecord) -> str:
        """Create the write-ahead record before any effect is dispatched."""
        return self._write(record, create_only=True)

    def advance(self, record: ServiceRunRecord) -> str:
        """Rewrite the record atomically at a stage boundary."""
        return self._write(record, require_existing=True)

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
        record = self._load(self.path_for(deployment_id, run_id))
        self._require_identity(record, deployment_id=deployment_id, run_id=run_id)
        return record

    def load_evidence(
        self, deployment_id: str, run_id: str
    ) -> tuple[ServiceRunRecord, str, str]:
        """Read one record once and return it with its path and byte digest.

        The digest is of the very bytes that were validated, so a caller that
        cites the record by hash cites what it actually interpreted.
        """
        path = self.path_for(deployment_id, run_id)
        try:
            raw = path.read_bytes()
            record = ServiceRunRecord.model_validate_json(raw.decode("utf-8"))
        except (OSError, ValueError) as exc:
            raise RunRecordPersistenceError(
                f"Stored service run record is unreadable: {path}"
            ) from exc
        self._require_identity(
            record, deployment_id=deployment_id, run_id=run_id, expected_path=path
        )
        return record, str(path), hashlib.sha256(raw).hexdigest()

    def deployment_history(self, deployment_id: str) -> tuple[str, ...]:
        """Name every stored entry of one deployment, whatever its status.

        This is the read a fresh-history precondition needs, so it judges
        nothing: a completed, refused, interrupted, malformed or half-written
        record is history all the same, and so is a leftover temporary file.
        A deployment directory that does not exist holds no history. One that
        cannot be listed raises, because missing access is not an empty
        history. The listing is bounded like the retention lookup.
        """
        if not deployment_id.strip():
            raise RunRecordPersistenceError("A deployment identity is required.")
        try:
            directory = resolve_within(
                self.base_dir, safe_name_component(deployment_id, UNBOUND_DIRECTORY)
            )
            if not directory.exists():
                return ()
            names = sorted(
                item.name
                for item in islice(directory.iterdir(), MAX_RETENTION_RECORDS + 1)
            )
        except (OSError, ValueError) as exc:
            raise RunRecordPersistenceError(
                "Could not inspect service run history."
            ) from exc
        if len(names) > MAX_RETENTION_RECORDS:
            raise RunRecordPersistenceError(
                "Service run history exceeds the bounded lookup budget."
            )
        return tuple(names)

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

        Lookup enumerates at most `MAX_RETENTION_RECORDS + 1` paths. A corrupt
        file is not silently skipped, and a newer uncertain attempt for the
        same configuration blocks an older exact-identity success.
        """
        if not deployment_id.strip():
            return None
        try:
            directory = resolve_within(
                self.base_dir, safe_name_component(deployment_id, UNBOUND_DIRECTORY)
            )
            if not directory.exists():
                return None
            paths = list(islice(directory.glob("*.json"), MAX_RETENTION_RECORDS + 1))
        except (OSError, ValueError) as exc:
            raise RunRecordPersistenceError(
                "Could not inspect service run history."
            ) from exc
        if len(paths) > MAX_RETENTION_RECORDS:
            raise RunRecordPersistenceError(
                "Service run history exceeds the bounded retention lookup budget."
            )
        newest: ServiceRunRecord | None = None
        newest_affected: ServiceRunRecord | None = None
        for path in paths:
            record = self._load(path)
            self._require_identity(
                record,
                deployment_id=deployment_id,
                run_id=record.run_id,
                expected_path=path,
            )
            if (
                record.configuration_semantic_hash
                and record.configuration_semantic_hash == configuration_semantic_hash
                and (
                    newest_affected is None
                    or (record.created_at, record.run_id)
                    > (newest_affected.created_at, newest_affected.run_id)
                )
            ):
                newest_affected = record
            if not record.identity_matches(
                deployment_id=deployment_id,
                manifest_hash=manifest_hash,
                configuration_semantic_hash=configuration_semantic_hash,
                environment_fingerprint_hash=environment_fingerprint_hash,
            ):
                continue
            if newest is None or (record.created_at, record.run_id) > (
                newest.created_at,
                newest.run_id,
            ):
                newest = record
        if (
            newest_affected is not None
            and (newest_affected.interrupted or newest_affected.e5_effect_uncertain)
            and (
                newest is None
                or (newest_affected.created_at, newest_affected.run_id)
                >= (newest.created_at, newest.run_id)
            )
        ):
            raise RunRecordPersistenceError(
                "A newer interrupted or uncertain run blocks retained reuse."
            )
        if newest is None:
            return None
        result = newest.configuration_result
        if result is None:
            return None
        governed_ids = {
            *newest.e5_effect_scope.mutated,
            *newest.e5_effect_scope.retained,
        } or set(result.mutation_action_ids)
        if any(
            not satisfies_apply_dependency(item.status)
            or item.failure_code is ConfigurationFailureCode.POSTCONDITION_UNSATISFIED
            for item in result.action_results
            if item.action_id in governed_ids
        ):
            return None
        return newest

    # -- internals --------------------------------------------------------

    def _write(
        self,
        record: ServiceRunRecord,
        *,
        create_only: bool = False,
        require_existing: bool = False,
    ) -> str:
        target = self.path_for(record.deployment_id, record.run_id)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        payload = record.model_dump_json(indent=2) + "\n"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            existed = target.exists()
            if create_only and existed:
                raise RunRecordPersistenceError(
                    "A service run record with this identity already exists."
                )
            if require_existing and not existed:
                raise RunRecordPersistenceError(
                    "The service run record cannot advance before begin."
                )
            if existed:
                current = self._load(target)
                self._require_identity(
                    current,
                    deployment_id=record.deployment_id,
                    run_id=record.run_id,
                    expected_path=target,
                )
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if existed:
                # Atomic update: a failure leaves the previous valid file.
                os.replace(temporary, target)
            else:
                # Atomic no-overwrite create. A colliding run cannot replace
                # the record that won the identity race.
                os.link(temporary, target)
                temporary.unlink()
        except RunRecordPersistenceError:
            raise
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
        try:
            resolved = Path(path).resolve()
            if not resolved.is_relative_to(self.base_dir):
                raise RunRecordPersistenceError(
                    f"Run record path escaped the configured store: {resolved}"
                )
            return ServiceRunRecord.model_validate_json(
                resolved.read_text(encoding="utf-8")
            )
        except RunRecordPersistenceError:
            raise
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RunRecordPersistenceError(
                f"Stored service run record is unreadable: {resolved}"
            ) from exc

    def _require_identity(
        self,
        record: ServiceRunRecord,
        *,
        deployment_id: str,
        run_id: str,
        expected_path: Path | None = None,
    ) -> None:
        """Bind internal record identity to the contained path being used."""
        if record.deployment_id != deployment_id or record.run_id != run_id:
            raise RunRecordPersistenceError(
                "Stored service run record identity does not match its path."
            )
        if expected_path is not None:
            try:
                actual = self.path_for(record.deployment_id, record.run_id)
                expected = expected_path.resolve()
            except OSError as exc:
                raise RunRecordPersistenceError(
                    "Stored service run record path could not be resolved."
                ) from exc
            if actual != expected:
                raise RunRecordPersistenceError(
                    "Stored service run record identity does not match its path."
                )
