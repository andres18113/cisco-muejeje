"""Validated access to immutable pre-Router0 historical state."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_SCHEMA = "cp-scale-historical-pre-router0-v1"
HISTORICAL_CLASSIFICATION = "HISTORICAL_PRE_ROUTER0_NON_GOVERNING"


def load_historical_pre_router0(
    current_state: Mapping[str, Any],
    *,
    repository_root: Path = ROOT,
) -> dict[str, Any]:
    """Load the hash-pinned history artifact after validating its authority."""
    reference = current_state["historical_pre_router0"]
    if reference.get("classification") != HISTORICAL_CLASSIFICATION:
        raise ValueError("Historical reference must remain non-governing.")
    if reference.get("governs_current_operation") is not False:
        raise ValueError("Historical reference cannot govern current operation.")
    if reference.get("authorization_effect") != "NONE":
        raise ValueError("Historical reference cannot authorize execution.")

    artifact = reference["artifact"]
    if artifact.get("schema") != HISTORICAL_SCHEMA:
        raise ValueError("Historical artifact schema reference is invalid.")

    root = repository_root.resolve()
    relative_path = Path(artifact["path"])
    if relative_path.is_absolute():
        raise ValueError("Historical artifact path must be repository-relative.")
    artifact_path = (root / relative_path).resolve()
    try:
        artifact_path.relative_to(root)
    except ValueError as exc:
        raise ValueError("Historical artifact path must remain within repository.") from exc
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Historical artifact does not exist: {relative_path}")

    raw = artifact_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != artifact.get("sha256"):
        raise ValueError("Historical artifact SHA-256 does not match its reference.")

    document = json.loads(raw)
    if document.get("schema") != HISTORICAL_SCHEMA:
        raise ValueError("Historical artifact schema is invalid.")
    payload = document["payload"]
    if payload.get("classification") != HISTORICAL_CLASSIFICATION:
        raise ValueError("Historical payload must remain non-governing.")
    if payload.get("governs_current_operation") is not False:
        raise ValueError("Historical payload cannot govern current operation.")
    if payload.get("authorization_effect") != "NONE":
        raise ValueError("Historical payload cannot authorize execution.")
    return payload
