"""The Muejeje build-manifest schema and its validation.

Everything here is about the manifest *document*: can it be read at all, does
its shape match schema 2, and are its declarative fields resolved. Which files
the declarations point at is `inventory`; what the answers mean is
`build_state`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from ...shared.utils import resolve_within
from .privileges import evidence_error

SCHEMA_VERSION = 2
MAX_MANIFEST_BYTES = 256 * 1024
# TODO-MANIFEST-HOME: the manifest home is pinned here. If the owned source root
# is ever renamed, this pin moves with it.
MANIFEST_LOGICAL = "muejeje_pts/manifest/muejeje-build-manifest.json"
MANIFEST_PARTS = ("muejeje_pts", "manifest", "muejeje-build-manifest.json")

REQUIRED_SECTIONS = frozenset({
    "extension", "output", "artifact_inputs", "tooling_inputs",
    "reference_inputs", "builder", "build_options", "packaging",
})
EXPECTED_TOP_LEVEL = REQUIRED_SECTIONS | {"schema_version"}

EXPECTED_EXTENSION = {"name": "muejeje", "version": "0.1.0"}
EXPECTED_OUTPUT = {"artifact": "muejeje.pts", "report": "muejeje.build.json"}
EXPECTED_OPTIONS = (
    "engine_script_order", "custom_interface_order", "module_id", "startup",
    "privileges",
)
AUTOMATION_PREREQUISITES = ("compiler_command", "content_validation")

# The three startup modes the Scripting Interface offers, as recorded from
# Cisco's own help pages in the v2 preflight inventory: On Startup, On Demand,
# Disabled. The validator checks against the platform's enum, not against our
# preference — which of the three this module uses is a decision (MJ-025), and
# anything outside the three names no mode Packet Tracer could be asked for.
STARTUP_VALUES = ("disabled", "on_demand", "on_startup")
# A module id is hierarchical and reverse-DNS shaped: lowercase segments, at
# least three of them, so one publisher's modules cannot collide with another's.
MODULE_ID_SEGMENT = re.compile(r"^[a-z][a-z0-9]*(?:[_-][a-z0-9]+)*$")
MODULE_ID_MIN_SEGMENTS = 3
# A declared list is a hand-written inventory, not a generated one.
MAX_OPTION_ITEMS = 64

# Which privilege identifiers may be declared, and on what evidence, is
# `privileges` — a namespace of its own, because three different things have
# been called "a privilege" here and only one of them belongs in this document.
# This module owns the *shape* of the field and nothing about its meaning.


def _reject_non_finite(value: str) -> Any:
    raise ValueError(f"non-finite JSON value: {value}")


def read_manifest(root: Path, manifest_path: Path) -> Any:
    """Read the one manifest this repository owns. Raises `ValueError`."""
    manifest_file = Path(manifest_path).resolve()
    if manifest_file != resolve_within(root, *MANIFEST_PARTS):
        raise ValueError("manifest path must be the fixed repository manifest")
    if manifest_file.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("manifest exceeds size limit")
    manifest = json.loads(
        manifest_file.read_text(encoding="utf-8"),
        parse_constant=_reject_non_finite,
    )
    try:
        json.dumps(manifest, allow_nan=False)
    except ValueError as exc:
        raise ValueError("non-finite JSON number") from exc
    return manifest


def schema_blocker(manifest: Any) -> str | None:
    """The one fatal shape error, if any. A fatal error ends the audit.

    `type(...) is not int` on purpose: `True` is an `int` in Python, and a
    manifest whose `schema_version` is a boolean is not schema 2.
    """
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != SCHEMA_VERSION
    ):
        return f"invalid manifest schema_version: expected {SCHEMA_VERSION}"
    if set(manifest) != EXPECTED_TOP_LEVEL:
        return "invalid manifest: top-level sections do not match schema"
    return None


def check_declared_identity(root: Path, manifest: dict[str, Any]) -> list[str]:
    """Extension identity and output destinations, which are both fixed."""
    blockers: list[str] = []
    if manifest.get("extension") != EXPECTED_EXTENSION:
        blockers.append("invalid extension identity")
    if manifest.get("output") != EXPECTED_OUTPUT:
        blockers.append("unsafe output destinations; fixed names are required")
    try:
        dist = resolve_within(root, "dist")
        if dist.exists() and dist.resolve().parent != root:
            blockers.append("unsafe dist symlink escape")
    except ValueError as exc:
        blockers.append(f"unsafe dist path: {exc}")
    return blockers


def check_build_options(manifest: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    """Return `(options, unresolved_names, blockers)`.

    *Unresolved* and *invalid* are two different facts and stay two different
    blockers. `null` means nobody has decided yet, which is not a defect;
    a decided value the platform could not accept is one. Only the second makes
    the inputs invalid, so "we have not chosen a module id" and "this module id
    cannot work" never read the same (MJ-016).
    """
    options = manifest.get("build_options")
    blockers: list[str] = []
    if not isinstance(options, dict) or set(options) != set(EXPECTED_OPTIONS):
        blockers.append("invalid build_options shape")
        options = options if isinstance(options, dict) else {}
    unresolved = [name for name in EXPECTED_OPTIONS if options.get(name) is None]
    blockers.extend(f"unresolved build option: {name}" for name in unresolved)
    blockers.extend(
        f"invalid build option {name}: {reason}"
        for name, reason in _option_value_errors(options, unresolved)
    )
    return options, unresolved, blockers


def _option_value_errors(
    options: dict[str, Any], unresolved: list[str],
) -> list[tuple[str, str]]:
    """`(option, reason)` for every resolved option whose value is unusable."""
    errors: list[tuple[str, str]] = []
    for name in EXPECTED_OPTIONS:
        if name in unresolved or name not in options:
            continue
        reason = _OPTION_VALIDATORS[name](options[name])
        if reason is not None:
            errors.append((name, reason))
    return errors


def _string_list_error(value: Any) -> str | None:
    """A bounded, duplicate-free list of non-empty strings."""
    if not isinstance(value, list):
        return "must be a list"
    if len(value) > MAX_OPTION_ITEMS:
        return f"must hold at most {MAX_OPTION_ITEMS} entries"
    if any(not isinstance(item, str) or not item for item in value):
        return "must hold non-empty strings"
    if len(set(value)) != len(value):
        return "must not repeat an entry"
    return None


def _path_list_error(value: Any) -> str | None:
    """A file order: at least one entry, each a relative POSIX path."""
    reason = _string_list_error(value)
    if reason is not None:
        return reason
    if not value:
        return "must name at least one file"
    for item in value:
        candidate = PurePosixPath(item)
        if "\\" in item or candidate.is_absolute() or ".." in candidate.parts:
            return f"must be a relative POSIX path: {item}"
    return None


def _module_id_error(value: Any) -> str | None:
    if not isinstance(value, str):
        return "must be a string"
    segments = value.split(".")
    if len(segments) < MODULE_ID_MIN_SEGMENTS:
        return f"must be hierarchical: at least {MODULE_ID_MIN_SEGMENTS} segments"
    if not all(MODULE_ID_SEGMENT.match(segment) for segment in segments):
        return "segments must be lowercase alphanumeric, '-' or '_'"
    return None


def _startup_error(value: Any) -> str | None:
    if not isinstance(value, str) or value not in STARTUP_VALUES:
        return f"must be one of {', '.join(STARTUP_VALUES)}"
    return None


def _privileges_error(value: Any) -> str | None:
    """A bounded list of evidenced serialized privilege tokens, or an empty one.

    The shape rules run first, so a typo is reported as a typo rather than as
    a missing privilege catalogue. Which names are admissible, and why a given
    one is not, is `privileges`: only the faulty names are reported back, since
    a reason listing the valid ones alongside them would read as if all of them
    were at fault.
    """
    reason = _string_list_error(value)
    if reason is not None:
        return reason
    return evidence_error(value)


_OPTION_VALIDATORS = {
    "engine_script_order": _path_list_error,
    "custom_interface_order": _path_list_error,
    "module_id": _module_id_error,
    "startup": _startup_error,
    "privileges": _privileges_error,
}


def check_packaging(manifest: dict[str, Any]) -> tuple[Any, list[str], list[str]]:
    """Return `(packaging, unresolved_prerequisites, blockers)`.

    The absence of an automated packager is a standing fact about Packet
    Tracer, not a defect in this repository, so it is reported in
    `packaging_state` rather than appended unconditionally to every run's
    blockers — which is what made `BUILD_TOOLCHAIN_BLOCKED` inescapable.
    """
    packaging = manifest.get("packaging")
    blockers: list[str] = []
    if not isinstance(packaging, dict) or packaging.get("status") != "unresolved":
        blockers.append("packaging status must remain unresolved without an adapter")
    unresolved = [
        name for name in AUTOMATION_PREREQUISITES
        if not isinstance(packaging, dict) or packaging.get(name) is None
    ]
    blockers.extend(f"unresolved packaging prerequisite: {name}" for name in unresolved)
    return packaging, unresolved, blockers
