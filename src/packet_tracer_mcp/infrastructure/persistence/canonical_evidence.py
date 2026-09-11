"""Durable publication boundary for canonical measured-evidence bundles."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ...shared.utils import resolve_within, safe_name_component


def publish_canonical_evidence(
    directory: Path,
    *,
    raw_files: Mapping[str, bytes],
    evidence: Mapping[str, Any],
) -> Path:
    """Publish every raw first and ``evidence.json`` last.

    Each file becomes visible through an atomic replace only after its bytes
    have been flushed. A caller may promote separate runtime authority only
    after this function returns.
    """

    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Canonical evidence directory is unavailable")
    if "evidence.json" in raw_files:
        raise ValueError("Raw evidence cannot replace the bundle manifest")

    for name, content in raw_files.items():
        if not isinstance(content, bytes):
            raise TypeError("Canonical raw evidence must be bytes")
        exact_name = safe_name_component(name)
        if exact_name != name:
            raise ValueError("Canonical raw evidence name is not exact")
        _write_durable(resolve_within(root, exact_name), content)

    manifest = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode()
    evidence_path = resolve_within(root, "evidence.json")
    _write_durable(evidence_path, manifest)
    return evidence_path


def publish_runtime_promotion_receipt(
    directory: Path,
    *,
    evidence_path: Path,
    runtime_snapshot_path: Path,
    runtime_payload_sha256: str,
) -> Path:
    """Atomically link completed runtime authority to immutable evidence.

    The receipt is intentionally separate from ``evidence.json``. Runtime
    authority begins when the snapshot promotion completes; a receipt failure
    can therefore leave missing metadata, but can never rewrite measured facts
    or contradict the already-enumerable authority.
    """

    root = Path(directory)
    exact_evidence = resolve_within(root, "evidence.json")
    if Path(evidence_path).resolve() != exact_evidence.resolve():
        raise ValueError("Promotion receipt requires the canonical evidence path")
    if (
        type(runtime_payload_sha256) is not str
        or len(runtime_payload_sha256) != 64
        or any(character not in "0123456789abcdef" for character in runtime_payload_sha256)
    ):
        raise ValueError("Promotion receipt requires an exact payload SHA-256")
    evidence_bytes = exact_evidence.read_bytes()
    snapshot = Path(runtime_snapshot_path)
    snapshot_bytes = snapshot.read_bytes()
    receipt = {
        "schema_version": 1,
        "kind": "runtime-promotion-receipt",
        "evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
        "runtime_payload_sha256": runtime_payload_sha256,
        "runtime_snapshot_file_sha256": hashlib.sha256(snapshot_bytes).hexdigest(),
        "runtime_snapshot_path": str(snapshot),
    }
    target = resolve_within(root, "promotion.json")
    _write_durable(
        target,
        (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode(),
    )
    return target


def _write_durable(target: Path, content: bytes) -> None:
    handle, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=target.name + ".",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
