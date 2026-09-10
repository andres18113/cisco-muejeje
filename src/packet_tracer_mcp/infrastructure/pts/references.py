"""The reference inventory: material this repository does not own.

A reference input is somebody else's bytes — an installed vendor page, an API
dump — that the audit still wants pinned, because what a build was checked
against is part of what the build was. Three rules follow from not owning it:
it must be **untracked** (committing it would make it ours), **ignored** (so it
cannot arrive by accident), and **SHA-256 pinned** (so the audit notices when
the copy on this machine is a different copy).

The inventory is empty today (MJ-013). This module exists so that staying empty
is a measured fact rather than an untested code path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .build_state import Findings
from .inventory import logical_path
from .provenance import MAX_INPUT_BYTES, hash_file, path_is_ignored

_HEX_DIGITS = frozenset("0123456789abcdef")


def measure_reference_inputs(
    root: Path,
    manifest: dict[str, Any],
    *,
    tracked: frozenset[str],
    findings: Findings,
) -> list[dict[str, Any]]:
    """Hash the untracked, ignored, pinned reference inventory (empty today)."""
    values = manifest.get("reference_inputs")
    if not isinstance(values, list):
        findings.block("reference_inputs must be a list")
        values = []
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in values:
        entry = _reference_entry(
            root, item, tracked=tracked, findings=findings, seen=seen,
        )
        if entry is not None:
            evidence.append(entry)
    return evidence


def _reference_entry(
    root: Path,
    item: Any,
    *,
    tracked: frozenset[str],
    findings: Findings,
    seen: set[str],
) -> dict[str, Any] | None:
    if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
        findings.block("invalid reference input entry")
        return None
    logical, path, error = logical_path(root, item.get("path"))
    if error:
        findings.block(error)
        return None
    assert logical is not None and path is not None
    if logical in seen:
        findings.block(f"invalid duplicate reference input path: {logical}")
        return None
    seen.add(logical)
    _check_reference_location(root, logical, tracked=tracked, findings=findings)
    pin = _reference_pin(item.get("sha256"), logical, findings)
    if not path.is_file():
        findings.block_manual(f"missing reference input: {logical}")
        return {"path": logical, "expected_sha256": pin, "actual_sha256": None}
    try:
        actual = hash_file(path, max_bytes=MAX_INPUT_BYTES)
    except (OSError, ValueError) as exc:
        findings.block(f"invalid reference input {logical}: {exc}")
        return None
    if pin is not None and actual != pin:
        findings.block(f"reference SHA-256 mismatch: {logical}")
    return {"path": logical, "expected_sha256": pin, "actual_sha256": actual}


def _check_reference_location(
    root: Path,
    logical: str,
    *,
    tracked: frozenset[str],
    findings: Findings,
) -> None:
    """A reference must be untracked and ignored: it is somebody else's bytes."""
    if logical in tracked:
        findings.block(f"reference input must be untracked: {logical}")
    try:
        ignored = path_is_ignored(root, logical)
    except ValueError as exc:
        # Git could not be asked, so "ignored" is unknown. Unknown fails closed.
        findings.block(str(exc))
        ignored = False
    if not ignored:
        findings.block(f"reference input must be ignored: {logical}")


def _reference_pin(pin: Any, logical: str, findings: Findings) -> str | None:
    if not isinstance(pin, str) or len(pin) != 64 or any(
        ch not in _HEX_DIGITS for ch in pin
    ):
        findings.block(f"missing SHA-256 pin: {logical}")
        return None
    return pin
