"""The Muejeje build-manifest schema and its validation.

Everything here is about the manifest *document*: can it be read at all, does
its shape match schema 2, and are its declarative fields resolved. Which files
the declarations point at is `inventory`; what the answers mean is
`build_state`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...shared.utils import resolve_within

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
    """Return `(options, unresolved_names, blockers)`."""
    options = manifest.get("build_options")
    blockers: list[str] = []
    if not isinstance(options, dict) or set(options) != set(EXPECTED_OPTIONS):
        blockers.append("invalid build_options shape")
        options = options if isinstance(options, dict) else {}
    unresolved = [name for name in EXPECTED_OPTIONS if options.get(name) is None]
    blockers.extend(f"unresolved build option: {name}" for name in unresolved)
    return options, unresolved, blockers


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
