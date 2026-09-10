"""Validate and identify Muejeje build inputs without building a module."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from ...shared.utils import resolve_within, safe_name_component

_MAX_MANIFEST_BYTES = 256 * 1024
_MAX_INPUT_BYTES = 64 * 1024 * 1024
# The owned source root. Everything packaged into muejeje.pts lives here, and
# nothing else does. EXTENSION/** is the legacy MCP Control Center extension: it
# keeps serving its own product and is not Muejeje artifact content.
_OWNED_SOURCE_ROOT = "muejeje_pts/"
_PACKAGED_SUFFIXES = frozenset(
    {".js", ".html", ".htm", ".css", ".png", ".gif", ".jpg", ".svg"}
)
# Bytes that ship inside the artifact.
_EXPECTED_ARTIFACT_INPUTS = (
    "muejeje_pts/interface/index.html",
    "muejeje_pts/script-engine/lifecycle.js",
)
# The auditor. It ships nothing, but it decides how the artifact was inspected,
# so it belongs to recipe identity and never to artifact content.
_EXPECTED_TOOLING_INPUTS = (
    "src/packet_tracer_mcp/infrastructure/pts/build.py",
    "tools/build_muejeje_pts.py",
)
_EXPECTED_OPTIONS = (
    "engine_script_order", "custom_interface_order", "module_id", "startup",
    "privileges",
)
_HEX_DIGITS = frozenset("0123456789abcdef")
_AUTOMATION_PREREQUISITES = ("compiler_command", "content_validation")

# Five states, five different facts. The earlier model collapsed the last three
# into BUILD_TOOLCHAIN_BLOCKED, so "a human can package this in the Scripting
# Interface", "nobody has demonstrated an automated packager" and "we have not
# decided the module id yet" all read as the same failure.
BUILD_SOURCE_INVALID = "BUILD_SOURCE_INVALID"
BUILD_INPUT_INVALID = "BUILD_INPUT_INVALID"
BUILD_TOOLCHAIN_BLOCKED = "BUILD_TOOLCHAIN_BLOCKED"
BUILD_AUTOMATION_UNPROVEN = "BUILD_AUTOMATION_UNPROVEN"
PACKAGING_MANUAL_AVAILABLE = "PACKAGING_MANUAL_AVAILABLE"
PACKAGING_MANUAL_UNAVAILABLE = "PACKAGING_MANUAL_UNAVAILABLE"

BUILD_STATES = (
    BUILD_SOURCE_INVALID,
    BUILD_INPUT_INVALID,
    BUILD_TOOLCHAIN_BLOCKED,
    BUILD_AUTOMATION_UNPROVEN,
    PACKAGING_MANUAL_AVAILABLE,
)


def classify_build_state(
    *,
    source_unidentifiable: bool,
    input_invalid: bool,
    source_dirty: bool,
    toolchain_unusable: bool,
    recipe_complete: bool,
) -> str:
    """Reduce the five independent axes to one dominant state.

    Precedence runs from the fact that invalidates every downstream claim to the
    fact that invalidates none of them. Note that a *malformed manifest* outranks
    a *dirty tree*: a manifest we cannot read tells us nothing, while a dirty
    tree we can still describe precisely. That ordering predates this function
    and is preserved deliberately.

    ``BUILD_SOURCE_INVALID`` (``source_unidentifiable``)
        Git could not identify the source at all, so no recipe describes
        anything.
    ``BUILD_INPUT_INVALID``
        The manifest or an input violates the contract.
    ``BUILD_SOURCE_INVALID`` (``source_dirty``)
        The source is readable but not pinned: uncommitted or differing from
        HEAD, so a recipe built from it would not identify what it hashed.
    ``BUILD_TOOLCHAIN_BLOCKED``
        A genuine inability to build: no usable Packet Tracer, or a declared
        input that is not there. **Not** the mere absence of automation.
    ``BUILD_AUTOMATION_UNPROVEN``
        Nothing is broken; the recipe is not fully specified yet, and no
        automated packaging path has been demonstrated.
    ``PACKAGING_MANUAL_AVAILABLE``
        A human can package this recipe in the Scripting Interface right now.
        Automation is still unproven; ``packaging_state`` says so separately.
    """
    if source_unidentifiable:
        return BUILD_SOURCE_INVALID
    if input_invalid:
        return BUILD_INPUT_INVALID
    if source_dirty:
        return BUILD_SOURCE_INVALID
    if toolchain_unusable:
        return BUILD_TOOLCHAIN_BLOCKED
    if not recipe_complete:
        return BUILD_AUTOMATION_UNPROVEN
    return PACKAGING_MANUAL_AVAILABLE


def recipe_id(recipe: dict[str, Any]) -> str:
    """Return the SHA-256 of canonical, non-NaN JSON recipe bytes."""
    encoded = json.dumps(
        recipe, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def artifact_sha256(path: Path) -> str:
    """Measure an existing caller-selected artifact without qualifying it."""
    candidate = Path(path)
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return _hash_file(candidate, max_bytes=None)


def _hash_file(path: Path, *, max_bytes: int | None) -> str:
    size = path.stat().st_size
    if max_bytes is not None and size > max_bytes:
        raise ValueError(f"file exceeds {max_bytes} byte limit")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=root, text=True, encoding="utf-8",
            errors="replace", capture_output=True, check=False, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Git source inspection failed: {exc}") from exc
    if completed.returncode:
        raise ValueError(f"Git source inspection failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def _working_blob_matches_head(root: Path, logical: str) -> bool:
    try:
        head = _git(root, "rev-parse", f"HEAD:{logical}")
        completed = subprocess.run(
            ["git", "hash-object", f"--path={logical}", "--", logical],
            cwd=root, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Git source inspection failed: {exc}") from exc
    if completed.returncode:
        raise ValueError(f"cannot hash working input: {logical}")
    return completed.stdout.strip() == head


def _logical_path(root: Path, value: Any) -> tuple[str | None, Path | None, str | None]:
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


def _packaging_state(
    *,
    manual: str,
    manual_blockers: list[str],
    recipe_complete: bool,
    unresolved_build_options: list[str],
    unresolved_automation_prerequisites: list[str],
) -> dict[str, Any]:
    return {
        "manual": manual,
        "manual_blockers": manual_blockers,
        # No automated packaging path has been demonstrated for the Scripting
        # Interface. This stays UNPROVEN until evidence says otherwise; it is
        # never inferred from a clean report.
        "automation": BUILD_AUTOMATION_UNPROVEN,
        "automation_evidence": None,
        "recipe_complete": recipe_complete,
        "unresolved_build_options": unresolved_build_options,
        "unresolved_automation_prerequisites": unresolved_automation_prerequisites,
    }


def _base_report(status: str, blockers: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "blockers": blockers,
        "source": {"commit": None, "tree": None, "clean": False},
        "inputs": {"artifact": [], "tooling": [], "reference": []},
        "builder": None,
        "packaging_state": _packaging_state(
            manual=PACKAGING_MANUAL_UNAVAILABLE,
            manual_blockers=[],
            recipe_complete=False,
            unresolved_build_options=list(_EXPECTED_OPTIONS),
            unresolved_automation_prerequisites=list(_AUTOMATION_PREREQUISITES),
        ),
        "recipe": None,
        "build_recipe_id": None,
        "artifact_sha256": None,
    }


def inspect_build(
    root: Path,
    manifest_path: Path,
    *,
    builder_path: Path | None = None,
) -> dict[str, Any]:
    """Inspect a Git checkout and aggregate all available build blockers."""
    root = Path(root).resolve()
    blockers: list[str] = []
    # Blockers that stop a *human* from packaging in the Scripting Interface:
    # no usable Packet Tracer, or a declared input that is not on disk. Tracked
    # explicitly rather than recovered from blocker prose.
    manual_blockers: list[str] = []
    git_failed = False
    report = _base_report(BUILD_INPUT_INVALID, blockers)
    try:
        manifest_file = Path(manifest_path).resolve()
        if manifest_file != resolve_within(root, "muejeje_pts", "manifest", "muejeje-build-manifest.json"):
            raise ValueError("manifest path must be the fixed repository manifest")
        if manifest_file.stat().st_size > _MAX_MANIFEST_BYTES:
            raise ValueError("manifest exceeds size limit")
        manifest = json.loads(
            manifest_file.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON value: {value}")
            ),
        )
        try:
            json.dumps(manifest, allow_nan=False)
        except ValueError as exc:
            raise ValueError("non-finite JSON number") from exc
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        blockers.append(f"invalid manifest: {exc}")
        return report
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != 2
    ):
        blockers.append("invalid manifest schema_version: expected 2")
        return report

    required_sections = {
        "extension", "output", "artifact_inputs", "tooling_inputs",
        "reference_inputs", "builder", "build_options", "packaging",
    }
    expected_top_level = required_sections | {"schema_version"}
    if set(manifest) != expected_top_level:
        blockers.append("invalid manifest: top-level sections do not match schema")
        return report

    extension = manifest.get("extension")
    output = manifest.get("output")
    if extension != {"name": "muejeje", "version": "0.1.0"}:
        blockers.append("invalid extension identity")
    if output != {"artifact": "muejeje.pts", "report": "muejeje.build.json"}:
        blockers.append("unsafe output destinations; fixed names are required")
    try:
        dist = resolve_within(root, "dist")
        if dist.exists() and dist.resolve().parent != root:
            blockers.append("unsafe dist symlink escape")
    except ValueError as exc:
        blockers.append(f"unsafe dist path: {exc}")

    try:
        git_top = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
        if git_top != root:
            raise ValueError("Git source inspection failed: root is not the repository top-level")
        commit = _git(root, "rev-parse", "HEAD")
        tree = _git(root, "rev-parse", "HEAD^{tree}")
        tracked = set(_git(root, "ls-files").splitlines())
        dirty_lines = _git(root, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
        report["source"] = {"commit": commit, "tree": tree, "clean": not dirty_lines}
        if dirty_lines:
            blockers.append("dirty tracked source")
    except ValueError as exc:
        blockers.append(str(exc))
        tracked = set()
        git_failed = True

    manifest_logical = "muejeje_pts/manifest/muejeje-build-manifest.json"
    if manifest_logical not in tracked:
        blockers.append("manifest must be tracked")
    else:
        try:
            if not _working_blob_matches_head(root, manifest_logical):
                blockers.append("manifest bytes differ from HEAD")
                report["source"]["clean"] = False
        except ValueError as exc:
            blockers.append(f"invalid manifest Git identity: {exc}")

    def _measure(
        section: str, label: str, expected: tuple[str, ...],
    ) -> tuple[list[dict[str, str]], set[str]]:
        values = manifest.get(section)
        if not isinstance(values, list) or values != list(expected):
            blockers.append(
                f"{section} must equal the complete ordered {label} inventory"
            )
            values = values if isinstance(values, list) else []
        evidence: list[dict[str, str]] = []
        seen: set[str] = set()
        for value in values:
            logical, path, error = _logical_path(root, value)
            if error:
                blockers.append(error)
                continue
            assert logical is not None and path is not None
            seen.add(logical)
            if section == "artifact_inputs" and not logical.startswith(_OWNED_SOURCE_ROOT):
                blockers.append(
                    "artifact input must live under the owned source root "
                    f"{_OWNED_SOURCE_ROOT}: {logical}"
                )
            if logical not in tracked:
                blockers.append(f"{label} input is not tracked: {logical}")
            if not path.is_file():
                blockers.append(f"missing {label} input: {logical}")
                manual_blockers.append(f"missing {label} input: {logical}")
                continue
            try:
                actual_hash = _hash_file(path, max_bytes=_MAX_INPUT_BYTES)
                evidence.append({"path": logical, "sha256": actual_hash})
                if logical in tracked and not _working_blob_matches_head(root, logical):
                    blockers.append(f"{label} input bytes differ from HEAD: {logical}")
                    report["source"]["clean"] = False
            except (OSError, ValueError) as exc:
                blockers.append(f"invalid {label} input {logical}: {exc}")
        return evidence, seen

    artifact_evidence, artifact_paths = _measure(
        "artifact_inputs", "artifact", _EXPECTED_ARTIFACT_INPUTS,
    )
    tooling_evidence, tooling_paths = _measure(
        "tooling_inputs", "tooling", _EXPECTED_TOOLING_INPUTS,
    )
    report["inputs"]["artifact"] = artifact_evidence
    report["inputs"]["tooling"] = tooling_evidence

    # A path cannot both ship inside the artifact and decide how it was audited.
    for logical in sorted(artifact_paths & tooling_paths):
        blockers.append(
            f"invalid input {logical}: a path may not be both artifact content "
            "and tooling"
        )

    # Completeness is measured over the owned source root only. The legacy
    # EXTENSION tree belongs to another product and is deliberately not swept in.
    tracked_assets = {
        item for item in tracked
        if item.startswith(_OWNED_SOURCE_ROOT)
        and Path(item).suffix.lower() in _PACKAGED_SUFFIXES
    }
    unexpected = sorted(tracked_assets - set(_EXPECTED_ARTIFACT_INPUTS))
    for logical in unexpected:
        blockers.append(
            f"tracked owned source omitted from artifact_inputs: {logical}"
        )

    reference_values = manifest.get("reference_inputs")
    if not isinstance(reference_values, list):
        blockers.append("reference_inputs must be a list")
        reference_values = []
    reference_evidence: list[dict[str, Any]] = []
    seen_reference_paths: set[str] = set()
    for item in reference_values:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            blockers.append("invalid reference input entry")
            continue
        logical, path, error = _logical_path(root, item.get("path"))
        if error:
            blockers.append(error)
            continue
        assert logical is not None and path is not None
        if logical in seen_reference_paths:
            blockers.append(f"invalid duplicate reference input path: {logical}")
            continue
        seen_reference_paths.add(logical)
        pin = item.get("sha256")
        if logical in tracked:
            blockers.append(f"reference input must be untracked: {logical}")
        try:
            ignored = subprocess.run(
                ["git", "check-ignore", "-q", "--", logical], cwd=root,
                capture_output=True, check=False, timeout=10,
            ).returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            blockers.append(f"Git ignore inspection failed for {logical}: {exc}")
            ignored = False
        if not ignored:
            blockers.append(f"reference input must be ignored: {logical}")
        if not isinstance(pin, str) or len(pin) != 64 or any(ch not in _HEX_DIGITS for ch in pin):
            blockers.append(f"missing SHA-256 pin: {logical}")
            pin = None
        if not path.is_file():
            blockers.append(f"missing reference input: {logical}")
            manual_blockers.append(f"missing reference input: {logical}")
            reference_evidence.append({"path": logical, "expected_sha256": pin, "actual_sha256": None})
            continue
        try:
            actual = _hash_file(path, max_bytes=_MAX_INPUT_BYTES)
            reference_evidence.append({"path": logical, "expected_sha256": pin, "actual_sha256": actual})
            if pin is not None and actual != pin:
                blockers.append(f"reference SHA-256 mismatch: {logical}")
        except (OSError, ValueError) as exc:
            blockers.append(f"invalid reference input {logical}: {exc}")
    report["inputs"]["reference"] = reference_evidence

    builder = manifest.get("builder")
    report["builder"] = dict(builder) if isinstance(builder, dict) else None
    expected_builder = {
        "name": "Cisco Packet Tracer", "version": "9.0.1.0858",
        "kind": "packet-tracer-scripting-interface",
        "sha256": "843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1",
    }
    if builder != expected_builder:
        blockers.append("invalid builder identity")
        manual_blockers.append("invalid builder identity")
    if builder_path is None:
        blockers.append("missing explicit builder path")
        manual_blockers.append("missing explicit builder path")
    else:
        try:
            actual_builder = artifact_sha256(Path(builder_path))
            if report["builder"] is not None:
                report["builder"]["actual_sha256"] = actual_builder
            if isinstance(builder, dict) and actual_builder != builder.get("sha256"):
                blockers.append("builder SHA-256 mismatch")
                manual_blockers.append("builder SHA-256 mismatch")
        except (OSError, ValueError) as exc:
            blockers.append(f"invalid builder file: {exc}")
            manual_blockers.append(f"invalid builder file: {exc}")

    options = manifest.get("build_options")
    if not isinstance(options, dict) or set(options) != set(_EXPECTED_OPTIONS):
        blockers.append("invalid build_options shape")
        options = options if isinstance(options, dict) else {}
    unresolved_options: list[str] = []
    for name in _EXPECTED_OPTIONS:
        if options.get(name) is None:
            unresolved_options.append(name)
            blockers.append(f"unresolved build option: {name}")

    packaging = manifest.get("packaging")
    if not isinstance(packaging, dict) or packaging.get("status") != "unresolved":
        blockers.append("packaging status must remain unresolved without an adapter")
    unresolved_automation: list[str] = []
    for name in _AUTOMATION_PREREQUISITES:
        if not isinstance(packaging, dict) or packaging.get(name) is None:
            unresolved_automation.append(name)
            blockers.append(f"unresolved packaging prerequisite: {name}")
    # The absence of an automated packager is a standing fact about Packet
    # Tracer, not a defect in this repository, so it is reported in
    # packaging_state rather than appended unconditionally to every run's
    # blockers — which is what made BUILD_TOOLCHAIN_BLOCKED inescapable.

    input_invalid = any(
        marker in blocker.lower()
        for blocker in blockers
        for marker in (
            "invalid", "unsafe", "noncanonical", "tracked owned source",
            "must be untracked", "must be tracked", "not tracked",
            "mismatch", "omitted",
        )
    )
    input_invalid = input_invalid or any(
        marker in blocker.lower()
        for blocker in blockers
        for marker in (
            "artifact_inputs must", "tooling_inputs must",
            "reference_inputs must", "must be ignored",
            "must live under the owned source root",
        )
    )
    source_dirty = any(
        marker in b.lower() for b in blockers for marker in ("dirty", "differ from head")
    )
    toolchain_unusable = bool(manual_blockers)
    recipe_complete = not unresolved_options

    report["status"] = classify_build_state(
        source_unidentifiable=git_failed,
        input_invalid=input_invalid,
        source_dirty=source_dirty,
        toolchain_unusable=toolchain_unusable,
        recipe_complete=recipe_complete,
    )
    report["packaging_state"] = _packaging_state(
        manual=(
            PACKAGING_MANUAL_UNAVAILABLE
            if git_failed or input_invalid or source_dirty or toolchain_unusable
            else PACKAGING_MANUAL_AVAILABLE
        ),
        manual_blockers=manual_blockers,
        recipe_complete=recipe_complete,
        unresolved_build_options=unresolved_options,
        unresolved_automation_prerequisites=unresolved_automation,
    )
    manifest_hash = _hash_file(manifest_file, max_bytes=_MAX_MANIFEST_BYTES)
    report["recipe"] = {
        "source": {"commit": report["source"]["commit"], "tree": report["source"]["tree"]},
        "manifest": {"sha256": manifest_hash},
        "extension": extension,
        "output": output,
        "artifact_inputs": artifact_evidence,
        "tooling_inputs": tooling_evidence,
        "reference_inputs": reference_evidence,
        "builder": report["builder"],
        "build_options": options,
        "packaging": packaging,
    }
    # A complete input inventory earns a recipe id; an incomplete one never
    # does. The artifact hash stays external and is never derived from here.
    if report["status"] == PACKAGING_MANUAL_AVAILABLE:
        try:
            report["build_recipe_id"] = recipe_id(report["recipe"])
        except (TypeError, ValueError) as exc:
            blockers.append(f"invalid recipe for identity: {exc}")
            report["status"] = BUILD_INPUT_INVALID
            report["packaging_state"]["manual"] = PACKAGING_MANUAL_UNAVAILABLE
    return report
