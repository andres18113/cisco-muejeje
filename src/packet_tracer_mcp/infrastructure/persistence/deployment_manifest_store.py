"""Append-only persistence for verified enterprise deployment manifests."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ...domain.enterprise.models.deployment import DeploymentManifest
from ...shared.utils import resolve_within, safe_name_component


class ManifestPersistenceError(RuntimeError):
    """Raised when a verified manifest cannot be stored without data loss."""


class DeploymentManifestStore:
    """Persist verified manifests as immutable, content-addressed records.

    ``semantic_hash`` deliberately excludes runtime session identifiers.  A
    later Packet Tracer session can therefore have the same semantic identity
    while carrying different stable runtime bindings.  Keeping a full-record
    digest in the filename preserves both observations instead of overwriting
    the earlier session.
    """

    def __init__(
        self,
        base_dir: str | Path = Path("data") / "deployments",
    ) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_verified(self, manifest: DeploymentManifest) -> Path:
        """Atomically persist one manifest emitted by a verified deployment.

        Re-saving the exact same record is idempotent.  An existing path whose
        contents do not match its content address is treated as corruption and
        is never silently replaced.
        """

        self._validate_identity(manifest)
        canonical = _canonical_payload(manifest)
        record_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        target_dir = self._record_dir(
            manifest.deployment_id,
            manifest.semantic_hash,
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        target = resolve_within(target_dir, f"{record_hash}.json")
        if target.exists():
            self._assert_existing_record(target, canonical)
            return target

        temporary = resolve_within(
            target_dir,
            f".{record_hash}.{uuid4().hex}.tmp",
        )
        payload = manifest.model_dump_json(indent=2) + "\n"
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            # A concurrent writer can only target the same full-record digest.
            # Validate it and retain the existing immutable record.
            if target.exists():
                self._assert_existing_record(target, canonical)
                return target
            os.replace(temporary, target)
        except ManifestPersistenceError:
            raise
        except OSError as exc:
            raise ManifestPersistenceError(
                f"Could not persist verified DeploymentManifest: {exc}"
            ) from exc
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        return target

    def latest_by_deployment_id(
        self,
        deployment_id: str,
    ) -> DeploymentManifest | None:
        """Return the newest exact deployment ID, never a sanitized alias."""

        records = self._records_for_deployment(deployment_id)
        return records[-1] if records else None

    def find_by_semantic_hash(
        self,
        semantic_hash: str,
    ) -> list[DeploymentManifest]:
        """Return every immutable runtime observation for one semantic hash."""

        if not semantic_hash.strip():
            return []
        semantic_component = safe_name_component(semantic_hash, "semantic")
        records: list[DeploymentManifest] = []
        for path in sorted(self.base_dir.glob(f"*/{semantic_component}/*.json")):
            manifest = self._load(path)
            if manifest.semantic_hash == semantic_hash:
                records.append(manifest)
        return sorted(records, key=_manifest_sort_key)

    def _records_for_deployment(
        self,
        deployment_id: str,
    ) -> list[DeploymentManifest]:
        if not deployment_id.strip():
            return []
        deployment_component = safe_name_component(deployment_id, "deployment")
        root = resolve_within(self.base_dir, deployment_component)
        if not root.exists():
            return []
        records: list[DeploymentManifest] = []
        for path in sorted(root.glob("*/*.json")):
            manifest = self._load(path)
            if manifest.deployment_id == deployment_id:
                records.append(manifest)
        return sorted(records, key=_manifest_sort_key)

    def _record_dir(self, deployment_id: str, semantic_hash: str) -> Path:
        return resolve_within(
            self.base_dir,
            safe_name_component(deployment_id, "deployment"),
            safe_name_component(semantic_hash, "semantic"),
        )

    def _load(self, path: Path) -> DeploymentManifest:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.base_dir):
            raise ManifestPersistenceError(
                f"Manifest path escaped the configured store: {resolved}"
            )
        try:
            return DeploymentManifest.model_validate_json(
                resolved.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ManifestPersistenceError(
                f"Stored DeploymentManifest is unreadable: {resolved}"
            ) from exc

    def _assert_existing_record(self, path: Path, expected: str) -> None:
        try:
            existing = self._load(path)
        except ManifestPersistenceError as exc:
            raise ManifestPersistenceError(
                f"Refusing to overwrite existing manifest record: {path}"
            ) from exc
        if _canonical_payload(existing) != expected:
            raise ManifestPersistenceError(
                f"Refusing to overwrite existing manifest record: {path}"
            )

    @staticmethod
    def _validate_identity(manifest: DeploymentManifest) -> None:
        missing = [
            field
            for field, value in (
                ("deployment_id", manifest.deployment_id),
                ("physical_topology_hash", manifest.physical_topology_hash),
                ("semantic_hash", manifest.semantic_hash),
            )
            if not value.strip()
        ]
        if missing:
            raise ManifestPersistenceError(
                "Verified DeploymentManifest is missing identity field(s): "
                + ", ".join(missing)
            )


def _canonical_payload(manifest: DeploymentManifest) -> str:
    return json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _manifest_sort_key(manifest: DeploymentManifest) -> tuple[datetime, str]:
    created_at = manifest.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at, hashlib.sha256(
        _canonical_payload(manifest).encode("utf-8")
    ).hexdigest()
