"""Which files the manifest may name, and what those files actually are.

Three input categories, three different meanings:

``artifact``
    bytes packaged into `muejeje.pts`. Must live under the owned source root.
``tooling``
    the auditor. Ships nothing, still decides how the artifact was inspected,
    so it belongs to recipe identity.
The third category, `reference` — untracked, ignored, hash-pinned material this
repository does not own — lives in `references`, because "our declared inputs"
and "somebody else's bytes we checked against" are answered by different rules.

The builder binary is measured here: it is a declared input with a pinned hash,
even though it is neither packaged nor tracked.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from ...shared.utils import resolve_within, safe_name_component
from .build_state import Findings
from .provenance import (
    MAX_INPUT_BYTES,
    artifact_sha256,
    hash_file,
    working_blob_matches_head,
)

# The owned source root. Everything packaged into muejeje.pts lives here, and
# nothing else does. EXTENSION/** is the legacy MCP Control Center extension: it
# keeps serving its own product and is not Muejeje artifact content.
OWNED_SOURCE_ROOT = "muejeje_pts/"
# The two kinds of packaged input, each with its own declared order in
# `build_options`: engine files evaluate in order, interface files are imported
# into the Custom Interfaces tab.
ENGINE_SOURCE_ROOT = "muejeje_pts/script-engine/"
INTERFACE_SOURCE_ROOT = "muejeje_pts/interface/"
PACKAGED_SUFFIXES = frozenset(
    {".js", ".html", ".htm", ".css", ".png", ".gif", ".jpg", ".svg"}
)
# Bytes that ship inside the artifact.
EXPECTED_ARTIFACT_INPUTS = (
    "muejeje_pts/interface/index.html",
    "muejeje_pts/script-engine/core.js",
    "muejeje_pts/script-engine/dispatcher_v6.js",
    "muejeje_pts/script-engine/lifecycle.js",
    "muejeje_pts/script-engine/protocol_v6.js",
    "muejeje_pts/script-engine/runtime_capabilities.js",
    "muejeje_pts/script-engine/runtime_identity.js",
)
# The auditor. It ships nothing, but it decides how the artifact was inspected,
# so it belongs to recipe identity and never to artifact content. Every module
# of the auditor is listed: splitting it into cohesive modules must not let a
# change escape recipe identity by moving into a file nobody declared.
EXPECTED_TOOLING_INPUTS = (
    "src/packet_tracer_mcp/infrastructure/pts/__init__.py",
    "src/packet_tracer_mcp/infrastructure/pts/build.py",
    "src/packet_tracer_mcp/infrastructure/pts/build_state.py",
    "src/packet_tracer_mcp/infrastructure/pts/inventory.py",
    "src/packet_tracer_mcp/infrastructure/pts/manifest.py",
    "src/packet_tracer_mcp/infrastructure/pts/provenance.py",
    "src/packet_tracer_mcp/infrastructure/pts/references.py",
    "tools/build_muejeje_pts.py",
)
EXPECTED_BUILDER = {
    "name": "Cisco Packet Tracer", "version": "9.0.1.0858",
    "kind": "packet-tracer-scripting-interface",
    "sha256": "843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1",
}


def logical_path(root: Path, value: Any) -> tuple[str | None, Path | None, str | None]:
    """Validate a manifest path declaration before it reaches the filesystem."""
    if not isinstance(value, str) or not value or "\\" in value:
        return None, None, f"unsafe logical path: {value!r}"
    logical = PurePosixPath(value)
    if logical.is_absolute() or any(
        part in ("", ".", "..") or safe_name_component(part, "") != part
        for part in logical.parts
    ):
        return None, None, f"noncanonical logical path: {value!r}"
    try:
        resolved = resolve_within(root, *logical.parts)
    except ValueError as exc:
        return None, None, f"unsafe logical path {value!r}: {exc}"
    return logical.as_posix(), resolved, None


class Measurement:
    """Hash evidence plus the two side facts the caller needs."""

    def __init__(self) -> None:
        self.evidence: list[dict[str, str]] = []
        self.paths: set[str] = set()
        self.dirty = False


def measure_declared_inputs(
    root: Path,
    manifest: dict[str, Any],
    *,
    section: str,
    label: str,
    expected: tuple[str, ...],
    tracked: frozenset[str],
    findings: Findings,
) -> Measurement:
    """Hash one declared, ordered, complete input inventory."""
    values = manifest.get(section)
    if not isinstance(values, list) or values != list(expected):
        findings.block(
            f"{section} must equal the complete ordered {label} inventory"
        )
        values = values if isinstance(values, list) else []
    measured = Measurement()
    for value in values:
        logical, path, error = logical_path(root, value)
        if error:
            findings.block(error)
            continue
        assert logical is not None and path is not None
        measured.paths.add(logical)
        _measure_one(
            root, logical, path, section=section, label=label,
            tracked=tracked, findings=findings, measured=measured,
        )
    return measured


def _measure_one(
    root: Path,
    logical: str,
    path: Path,
    *,
    section: str,
    label: str,
    tracked: frozenset[str],
    findings: Findings,
    measured: Measurement,
) -> None:
    if section == "artifact_inputs" and not logical.startswith(OWNED_SOURCE_ROOT):
        findings.block(
            "artifact input must live under the owned source root "
            f"{OWNED_SOURCE_ROOT}: {logical}"
        )
    if logical not in tracked:
        findings.block(f"{label} input is not tracked: {logical}")
    if not path.is_file():
        findings.block_manual(f"missing {label} input: {logical}")
        return
    try:
        measured.evidence.append(
            {"path": logical, "sha256": hash_file(path, max_bytes=MAX_INPUT_BYTES)}
        )
        if logical in tracked and not working_blob_matches_head(root, logical):
            findings.block(f"{label} input bytes differ from HEAD: {logical}")
            measured.dirty = True
    except (OSError, ValueError) as exc:
        findings.block(f"invalid {label} input {logical}: {exc}")


def check_declared_orders(options: dict[str, Any], *, findings: Findings) -> None:
    """The two file orders must name exactly the artifact inputs of their kind.

    `manifest` decides whether an order is a well-formed list of paths; this
    decides whether those paths are files that actually ship. An order naming a
    file no artifact contains describes a build nobody can perform, and one
    omitting a file that does ship would leave it unevaluated in the module.
    """
    for name, prefix in (
        ("engine_script_order", ENGINE_SOURCE_ROOT),
        ("custom_interface_order", INTERFACE_SOURCE_ROOT),
    ):
        declared = options.get(name)
        if not isinstance(declared, list):
            continue  # Shape is the manifest's answer, already blocked there.
        expected = {
            logical for logical in EXPECTED_ARTIFACT_INPUTS
            if logical.startswith(prefix)
        }
        if set(declared) != expected:
            findings.block(
                f"invalid build option {name}: must name exactly the declared "
                f"artifact inputs under {prefix}"
            )


def sweep_owned_sources(tracked: frozenset[str]) -> list[str]:
    """Tracked packageable sources under the owned root that nobody declared.

    Completeness is measured over the owned source root only. The legacy
    EXTENSION tree belongs to another product and is deliberately not swept in.
    """
    tracked_assets = {
        item for item in tracked
        if item.startswith(OWNED_SOURCE_ROOT)
        and Path(item).suffix.lower() in PACKAGED_SUFFIXES
    }
    return sorted(tracked_assets - set(EXPECTED_ARTIFACT_INPUTS))


def check_builder(
    manifest: dict[str, Any],
    builder_path: Path | None,
    *,
    findings: Findings,
) -> dict[str, Any] | None:
    """Verify the declared builder identity against the file the caller named."""
    builder = manifest.get("builder")
    report = dict(builder) if isinstance(builder, dict) else None
    if builder != EXPECTED_BUILDER:
        findings.block_manual("invalid builder identity")
    if builder_path is None:
        findings.block_manual("missing explicit builder path")
        return report
    try:
        actual = artifact_sha256(Path(builder_path))
    except (OSError, ValueError) as exc:
        findings.block_manual(f"invalid builder file: {exc}")
        return report
    if report is not None:
        report["actual_sha256"] = actual
    if isinstance(builder, dict) and actual != builder.get("sha256"):
        findings.block_manual("builder SHA-256 mismatch")
    return report
