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
_EXPECTED_OWN_INPUTS = (
    "EXTENSION/script-engine/main.js",
    "EXTENSION/webview/bootstrap.bundle.min.js",
    "EXTENSION/webview/bootstrap.min.css",
    "EXTENSION/webview/index.html",
    "EXTENSION/webview/interface.js",
    "src/packet_tracer_mcp/infrastructure/pts/build.py",
    "tools/build_muejeje_pts.py",
)
_EXPECTED_OPTIONS = (
    "engine_script_order", "custom_interface_order", "module_id", "startup",
    "privileges",
)
_HEX_DIGITS = frozenset("0123456789abcdef")


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


def _base_report(status: str, blockers: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "blockers": blockers,
        "source": {"commit": None, "tree": None, "clean": False},
        "inputs": {"own": [], "reference": []},
        "builder": None,
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
    git_failed = False
    report = _base_report("BUILD_INPUT_INVALID", blockers)
    try:
        manifest_file = Path(manifest_path).resolve()
        if manifest_file != resolve_within(root, "EXTENSION", "manifest", "muejeje-build-manifest.json"):
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
        or manifest.get("schema_version") != 1
    ):
        blockers.append("invalid manifest schema_version: expected 1")
        return report

    required_sections = {
        "extension", "output", "own_inputs", "reference_inputs", "builder",
        "build_options", "packaging",
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

    manifest_logical = "EXTENSION/manifest/muejeje-build-manifest.json"
    if manifest_logical not in tracked:
        blockers.append("manifest must be tracked")
    else:
        try:
            if not _working_blob_matches_head(root, manifest_logical):
                blockers.append("manifest bytes differ from HEAD")
                report["source"]["clean"] = False
        except ValueError as exc:
            blockers.append(f"invalid manifest Git identity: {exc}")

    own_values = manifest.get("own_inputs")
    if not isinstance(own_values, list) or own_values != list(_EXPECTED_OWN_INPUTS):
        blockers.append("own_inputs must equal the complete ordered own input inventory")
        own_values = own_values if isinstance(own_values, list) else []
    own_evidence: list[dict[str, str]] = []
    for value in own_values:
        logical, path, error = _logical_path(root, value)
        if error:
            blockers.append(error)
            continue
        assert logical is not None and path is not None
        if logical not in tracked:
            blockers.append(f"own input is not tracked: {logical}")
        if not path.is_file():
            blockers.append(f"missing own input: {logical}")
            continue
        try:
            actual_hash = _hash_file(path, max_bytes=_MAX_INPUT_BYTES)
            own_evidence.append({"path": logical, "sha256": actual_hash})
            if logical in tracked and not _working_blob_matches_head(root, logical):
                blockers.append(f"own input bytes differ from HEAD: {logical}")
                report["source"]["clean"] = False
        except (OSError, ValueError) as exc:
            blockers.append(f"invalid own input {logical}: {exc}")
    report["inputs"]["own"] = own_evidence

    tracked_assets = {
        item for item in tracked
        if item.startswith("EXTENSION/") and Path(item).suffix.lower() in {".js", ".html", ".css"}
    }
    unexpected = sorted(tracked_assets - set(_EXPECTED_OWN_INPUTS))
    for logical in unexpected:
        blockers.append(f"tracked EXTENSION asset omitted from own_inputs: {logical}")

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
    if builder_path is None:
        blockers.append("missing explicit builder path")
    else:
        try:
            actual_builder = artifact_sha256(Path(builder_path))
            if report["builder"] is not None:
                report["builder"]["actual_sha256"] = actual_builder
            if isinstance(builder, dict) and actual_builder != builder.get("sha256"):
                blockers.append("builder SHA-256 mismatch")
        except (OSError, ValueError) as exc:
            blockers.append(f"invalid builder file: {exc}")

    options = manifest.get("build_options")
    if not isinstance(options, dict) or set(options) != set(_EXPECTED_OPTIONS):
        blockers.append("invalid build_options shape")
        options = options if isinstance(options, dict) else {}
    for name in _EXPECTED_OPTIONS:
        if options.get(name) is None:
            blockers.append(f"unresolved build option: {name}")

    packaging = manifest.get("packaging")
    if not isinstance(packaging, dict) or packaging.get("status") != "unresolved":
        blockers.append("packaging status must remain unresolved without an adapter")
    for name in ("compiler_command", "content_validation"):
        if not isinstance(packaging, dict) or packaging.get(name) is None:
            blockers.append(f"unresolved packaging prerequisite: {name}")
    blockers.append("no compile adapter is implemented for Packet Tracer GUI packaging")

    input_invalid = any(
        marker in blocker.lower()
        for blocker in blockers
        for marker in ("invalid", "unsafe", "noncanonical", "tracked extension", "must be untracked", "must be tracked", "not tracked", "mismatch", "omitted")
    )
    report["status"] = (
        "BUILD_SOURCE_INVALID" if git_failed
        else "BUILD_INPUT_INVALID" if input_invalid or any(
            marker in blocker.lower()
            for blocker in blockers
            for marker in ("own_inputs must", "reference_inputs must", "must be ignored")
        )
        else "BUILD_SOURCE_INVALID" if any(
            marker in b.lower() for b in blockers for marker in ("dirty", "differ from head")
        )
        else "BUILD_TOOLCHAIN_BLOCKED"
    )
    manifest_hash = _hash_file(manifest_file, max_bytes=_MAX_MANIFEST_BYTES)
    report["recipe"] = {
        "source": {"commit": report["source"]["commit"], "tree": report["source"]["tree"]},
        "manifest": {"sha256": manifest_hash},
        "extension": extension,
        "output": output,
        "own_inputs": own_evidence,
        "reference_inputs": reference_evidence,
        "builder": report["builder"],
        "build_options": options,
        "packaging": packaging,
    }
    return report
