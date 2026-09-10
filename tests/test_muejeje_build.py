from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE = REPO_ROOT / "src/packet_tracer_mcp/infrastructure/pts/build.py"
CLI = REPO_ROOT / "tools/build_muejeje_pts.py"
REFERENCE_PATH = "local-references/api-reference.txt"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True,
        capture_output=True,
    )


def _manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "extension": {"name": "muejeje", "version": "0.1.0"},
        "output": {
            "artifact": "muejeje.pts", "report": "muejeje.build.json",
        },
        "own_inputs": [
            "EXTENSION/script-engine/main.js",
            "EXTENSION/webview/bootstrap.bundle.min.js",
            "EXTENSION/webview/bootstrap.min.css",
            "EXTENSION/webview/index.html",
            "EXTENSION/webview/interface.js",
            "src/packet_tracer_mcp/infrastructure/pts/build.py",
            "tools/build_muejeje_pts.py",
        ],
        "reference_inputs": [],
        "builder": {
            "name": "Cisco Packet Tracer", "version": "9.0.1.0858",
            "kind": "packet-tracer-scripting-interface",
            "sha256": "843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1",
        },
        "build_options": {
            "engine_script_order": None, "custom_interface_order": None,
            "module_id": None, "startup": None, "privileges": None,
        },
        "packaging": {
            "status": "unresolved", "compiler_command": None,
            "content_validation": None,
        },
    }


def make_repo(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "source"
    manifest_path = root / "EXTENSION/manifest/muejeje-build-manifest.json"
    for logical in _manifest()["own_inputs"]:  # type: ignore[index]
        path = root / logical
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"own:{logical}\n", encoding="utf-8")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    (root / ".gitignore").write_text(
        "dist/\nlocal-references/\n",
        encoding="utf-8",
    )
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Muejeje test")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "fixture")
    return root, manifest_path


def _commit_manifest(root: Path, manifest_path: Path, manifest: dict[str, object]) -> None:
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _git(root, "add", str(manifest_path.relative_to(root)))
    _git(root, "commit", "-qm", "update manifest")


def _reference_entry(root: Path) -> dict[str, str]:
    path = root / REFERENCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = b"synthetic API reference\n"
    path.write_bytes(contents)
    return {"path": REFERENCE_PATH, "sha256": hashlib.sha256(contents).hexdigest()}


def _build_api():
    assert MODULE.exists(), "build foundation module must exist"
    from src.packet_tracer_mcp.infrastructure.pts import build
    return build


def test_empty_reference_inventory_has_only_unresolved_toolchain_blockers(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    report = _build_api().inspect_build(root, manifest_path)

    assert report["status"] == "BUILD_TOOLCHAIN_BLOCKED"
    assert report["build_recipe_id"] is None
    assert report["artifact_sha256"] is None
    assert "artifact_sha256" not in report["recipe"]
    assert report["inputs"]["reference"] == []
    assert not any("reference" in blocker.lower() for blocker in report["blockers"])
    for option in _manifest()["build_options"]:  # type: ignore[union-attr]
        assert any(option in blocker for blocker in report["blockers"])
    assert any("compiler_command" in blocker for blocker in report["blockers"])
    assert any("content_validation" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize("bad_manifest", [
    "{", "[]", '{"schema_version":2}', '{"schema_version":true}',
    '{"schema_version":1,"value":NaN}',
])
def test_malformed_or_wrong_schema_is_invalid(tmp_path: Path, bad_manifest: str):
    root, manifest_path = make_repo(tmp_path)
    manifest_path.write_text(bad_manifest, encoding="utf-8")

    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert report["build_recipe_id"] is None


@pytest.mark.parametrize("bad_value", [True, float("nan")])
def test_noncanonical_json_values_are_invalid(tmp_path: Path, bad_value: object):
    root, manifest_path = make_repo(tmp_path)
    manifest = _manifest()
    if bad_value is True:
        manifest["schema_version"] = bad_value
    else:
        manifest["unexpected"] = bad_value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("manifest" in blocker.lower() for blocker in report["blockers"])


def test_dirty_source_and_omitted_or_unexpected_own_assets_are_invalid(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    (root / "EXTENSION/webview/index.html").write_text("dirty", encoding="utf-8")
    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_SOURCE_INVALID"
    assert any("dirty" in blocker.lower() for blocker in report["blockers"])

    _git(root, "checkout", "--", "EXTENSION/webview/index.html")
    extra = root / "EXTENSION/webview/extra.css"
    extra.write_text("extra", encoding="utf-8")
    _git(root, "add", "-f", "EXTENSION/webview/extra.css")
    _git(root, "commit", "-qm", "extra tracked asset")
    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("extra.css" in blocker for blocker in report["blockers"])


def test_missing_and_omitted_own_inputs_are_reported(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    missing = root / "EXTENSION/webview/index.html"
    missing.unlink()
    report = _build_api().inspect_build(root, manifest_path)
    assert report["build_recipe_id"] is None
    assert any("missing own input" in blocker and "index.html" in blocker for blocker in report["blockers"])

    _git(root, "checkout", "--", str(missing.relative_to(root)))
    manifest = _manifest()
    manifest["own_inputs"].remove("EXTENSION/webview/index.html")  # type: ignore[union-attr]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("complete ordered" in blocker for blocker in report["blockers"])


def test_optional_reference_with_matching_pin_is_accepted(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    manifest = _manifest()
    entry = _reference_entry(root)
    manifest["reference_inputs"] = [entry]
    _commit_manifest(root, manifest_path, manifest)

    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_TOOLCHAIN_BLOCKED"
    assert report["inputs"]["reference"] == [{
        "path": REFERENCE_PATH,
        "expected_sha256": entry["sha256"],
        "actual_sha256": entry["sha256"],
    }]
    assert not any("reference" in blocker.lower() for blocker in report["blockers"])


def test_optional_reference_hash_mismatch_is_invalid(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    manifest = _manifest()
    entry = _reference_entry(root)
    entry["sha256"] = "0" * 64
    manifest["reference_inputs"] = [entry]
    _commit_manifest(root, manifest_path, manifest)

    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("mismatch" in blocker.lower() for blocker in report["blockers"])


def test_tracked_reference_is_invalid_even_when_ignore_rule_matches(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    manifest = _manifest()
    entry = _reference_entry(root)
    manifest["reference_inputs"] = [entry]
    _commit_manifest(root, manifest_path, manifest)
    ref = root / REFERENCE_PATH
    _git(root, "add", "-f", str(ref.relative_to(root)))
    _git(root, "commit", "-qm", "bad tracked reference")

    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("tracked" in blocker and REFERENCE_PATH in blocker for blocker in report["blockers"])


def test_optional_reference_must_be_ignored(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    path = root / "api-reference.txt"
    contents = b"synthetic API reference\n"
    path.write_bytes(contents)
    manifest = _manifest()
    manifest["reference_inputs"] = [{
        "path": "api-reference.txt",
        "sha256": hashlib.sha256(contents).hexdigest(),
    }]
    _commit_manifest(root, manifest_path, manifest)

    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("must be ignored" in blocker for blocker in report["blockers"])


@pytest.mark.parametrize(
    ("entry", "expected_blocker", "expected_status"),
    [
        ({"path": REFERENCE_PATH, "sha256": None}, "missing SHA-256 pin", "BUILD_TOOLCHAIN_BLOCKED"),
        ({"path": REFERENCE_PATH, "sha256": "0" * 64}, "missing reference input", "BUILD_TOOLCHAIN_BLOCKED"),
        ({"path": REFERENCE_PATH, "sha256": "0" * 64, "extra": True}, "invalid reference input entry", "BUILD_INPUT_INVALID"),
        ({"sha256": "0" * 64}, "invalid reference input entry", "BUILD_INPUT_INVALID"),
        ("not-an-object", "invalid reference input entry", "BUILD_INPUT_INVALID"),
        ({"path": "../api-reference.txt", "sha256": "0" * 64}, "noncanonical logical path", "BUILD_INPUT_INVALID"),
    ],
)
def test_invalid_optional_reference_entries_are_rejected(
    tmp_path: Path,
    entry: object,
    expected_blocker: str,
    expected_status: str,
):
    root, manifest_path = make_repo(tmp_path)
    manifest = _manifest()
    manifest["reference_inputs"] = [entry]
    _commit_manifest(root, manifest_path, manifest)

    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == expected_status
    assert report["build_recipe_id"] is None
    assert report["artifact_sha256"] is None
    assert any(expected_blocker in blocker for blocker in report["blockers"])


def test_duplicate_optional_reference_paths_are_invalid(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    manifest = _manifest()
    entry = _reference_entry(root)
    manifest["reference_inputs"] = [entry, dict(entry)]
    _commit_manifest(root, manifest_path, manifest)

    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("duplicate reference input" in blocker for blocker in report["blockers"])


def test_manifest_must_be_tracked_and_own_bytes_must_match_head(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    _git(root, "rm", "--cached", str(manifest_path.relative_to(root)))
    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("manifest" in blocker and "tracked" in blocker for blocker in report["blockers"])

    _git(root, "add", str(manifest_path.relative_to(root)))
    own = root / "EXTENSION/webview/interface.js"
    _git(root, "update-index", "--assume-unchanged", str(own.relative_to(root)))
    own.write_text("hidden dirty bytes", encoding="utf-8")
    try:
        report = _build_api().inspect_build(root, manifest_path)
    finally:
        _git(root, "update-index", "--no-assume-unchanged", str(own.relative_to(root)))
    assert report["status"] == "BUILD_SOURCE_INVALID"
    assert report["source"]["clean"] is False
    assert any("HEAD" in blocker and "interface.js" in blocker for blocker in report["blockers"])


def test_manifest_bytes_must_match_head_even_when_assume_unchanged(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    logical = str(manifest_path.relative_to(root))
    _git(root, "update-index", "--assume-unchanged", logical)
    manifest = _manifest()
    manifest["build_options"]["module_id"] = "synthetic-module"  # type: ignore[index]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    try:
        report = _build_api().inspect_build(root, manifest_path)
    finally:
        _git(root, "update-index", "--no-assume-unchanged", logical)
    assert report["status"] == "BUILD_SOURCE_INVALID"
    assert report["source"]["clean"] is False
    assert any("manifest bytes differ from HEAD" in blocker for blocker in report["blockers"])


def test_overflowing_json_number_returns_structured_invalid_report(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    text = manifest_path.read_text(encoding="utf-8").replace(
        '"module_id": null', '"module_id": 1e999',
    )
    manifest_path.write_text(text, encoding="utf-8")
    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("non-finite" in blocker for blocker in report["blockers"])

    stable = root / "stable.pts"
    stable.write_bytes(b"stable overflow sentinel")
    result = subprocess.run(
        [sys.executable, str(CLI), "--check"], cwd=root, text=True,
        capture_output=True,
    )
    cli_report = json.loads((root / "dist/muejeje.build.json").read_text(encoding="utf-8"))
    assert result.returncode != 0
    assert result.stderr == ""
    assert cli_report["status"] == "BUILD_INPUT_INVALID"
    assert cli_report["build_recipe_id"] is None
    assert cli_report["artifact_sha256"] is None
    assert stable.read_bytes() == b"stable overflow sentinel"


def test_malformed_builder_with_explicit_file_returns_invalid_report(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    manifest = _manifest()
    manifest["builder"] = None
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    builder = tmp_path / "builder.exe"
    builder.write_bytes(b"synthetic builder")

    report = _build_api().inspect_build(root, manifest_path, builder_path=builder)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("builder" in blocker for blocker in report["blockers"])


def test_non_git_source_is_source_invalid(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    (root / ".git").rename(root / ".git-disabled")
    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_SOURCE_INVALID"
    assert any("Git source inspection failed" in blocker for blocker in report["blockers"])


def test_unsafe_input_and_output_paths_are_rejected(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    manifest = _manifest()
    manifest["own_inputs"][0] = "../secret.js"  # type: ignore[index]
    manifest["output"]["report"] = "../report.json"  # type: ignore[index]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("noncanonical" in blocker or "unsafe" in blocker for blocker in report["blockers"])


def test_cli_writes_only_fixed_report_and_preserves_stable_pts(tmp_path: Path):
    root, _ = make_repo(tmp_path)
    stable = root / "stable.pts"
    stable.write_bytes(b"stable sentinel")
    _git(root, "add", "stable.pts")
    _git(root, "commit", "-qm", "stable sentinel")

    result = subprocess.run(
        [sys.executable, str(CLI), "--check"], cwd=root, text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    report_path = root / "dist/muejeje.build.json"
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "BUILD_TOOLCHAIN_BLOCKED"
    assert not (root / "dist/muejeje.pts").exists()
    assert stable.read_bytes() == b"stable sentinel"
    assert list((root / "dist").iterdir()) == [report_path]


def test_cli_refuses_hardlink_alias_to_arbitrary_sentinel(tmp_path: Path):
    root, _ = make_repo(tmp_path)
    dist = root / "dist"
    dist.mkdir()
    artifact = dist / "stable-sentinel.pts"
    artifact.write_bytes(b"candidate sentinel")
    report_path = dist / "muejeje.build.json"
    try:
        os.link(artifact, report_path)
    except OSError as exc:
        pytest.skip(f"hardlink unavailable: {exc}")

    result = subprocess.run(
        [sys.executable, str(CLI), "--check"], cwd=root, text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert artifact.read_bytes() == b"candidate sentinel"


def test_cli_refuses_report_symlink_alias_without_overwriting_target(tmp_path: Path):
    root, _ = make_repo(tmp_path)
    dist = root / "dist"
    dist.mkdir()
    sentinel = dist / "sentinel.pts"
    sentinel.write_bytes(b"do not overwrite")
    try:
        (dist / "muejeje.build.json").symlink_to(sentinel)
    except OSError as exc:
        pytest.skip(f"symlink privilege unavailable: {exc}")

    result = subprocess.run(
        [sys.executable, str(CLI), "--check"], cwd=root, text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert sentinel.read_bytes() == b"do not overwrite"


def test_report_symlink_escape_is_rejected(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "dist").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink privilege unavailable: {exc}")

    report = _build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("dist" in blocker.lower() for blocker in report["blockers"])


# ---------------------------------------------------------------------------
# M0D: the build-state model must not collapse distinct facts.
#
# The previous model returned BUILD_TOOLCHAIN_BLOCKED for a repository whose
# inputs and source were fine, whose builder was verified, and whose only
# outstanding items were unresolved build options and the absence of an
# automated packaging path. Those are three different facts and one of them is
# not a defect at all: manual Scripting Interface packaging is available.
# ---------------------------------------------------------------------------

INSTALLED_BUILDER = Path(
    "C:/Program Files/Cisco Packet Tracer 9.0.1/bin/PacketTracer.exe"
)

RESOLVED_OPTIONS = {
    "engine_script_order": ["EXTENSION/script-engine/main.js"],
    "custom_interface_order": [
        "EXTENSION/webview/index.html",
        "EXTENSION/webview/interface.js",
        "EXTENSION/webview/bootstrap.min.css",
        "EXTENSION/webview/bootstrap.bundle.min.js",
    ],
    "module_id": "com.muejeje.runtime",
    "startup": "on_startup",
    "privileges": ["PrivGetNetwork"],
}


def test_build_states_are_five_distinct_names():
    build = _build_api()
    assert set(build.BUILD_STATES) == {
        "BUILD_SOURCE_INVALID",
        "BUILD_INPUT_INVALID",
        "BUILD_TOOLCHAIN_BLOCKED",
        "BUILD_AUTOMATION_UNPROVEN",
        "PACKAGING_MANUAL_AVAILABLE",
    }
    assert len(set(build.BUILD_STATES)) == len(build.BUILD_STATES)


def _axes(**overrides: bool) -> dict[str, bool]:
    axes = dict(
        source_unidentifiable=False, input_invalid=False, source_dirty=False,
        toolchain_unusable=False, recipe_complete=True,
    )
    axes.update(overrides)
    return axes


@pytest.mark.parametrize(
    "flags,expected",
    [
        # An unidentifiable source outranks everything: nothing downstream can
        # be described at all.
        (_axes(source_unidentifiable=True, input_invalid=True, source_dirty=True,
               toolchain_unusable=True), "BUILD_SOURCE_INVALID"),
        # A malformed manifest outranks a dirty tree: a manifest we cannot read
        # tells us nothing, while a dirty tree we can still describe precisely.
        # This ordering predates the refactor and is preserved deliberately.
        (_axes(input_invalid=True, source_dirty=True, toolchain_unusable=True),
         "BUILD_INPUT_INVALID"),
        (_axes(source_dirty=True, toolchain_unusable=True), "BUILD_SOURCE_INVALID"),
        # A genuine inability to build: no usable Packet Tracer.
        (_axes(toolchain_unusable=True), "BUILD_TOOLCHAIN_BLOCKED"),
        # Nothing is broken; the recipe simply is not fully specified yet.
        (_axes(recipe_complete=False), "BUILD_AUTOMATION_UNPROVEN"),
        # A human can package this now. Automation is still unproven, which the
        # packaging_state block says separately.
        (_axes(), "PACKAGING_MANUAL_AVAILABLE"),
    ],
)
def test_classify_build_state_precedence(flags: dict[str, bool], expected: str):
    assert _build_api().classify_build_state(**flags) == expected


def test_absent_automation_alone_is_not_a_toolchain_block(tmp_path: Path):
    """The old model appended an unconditional compile-adapter blocker, so
    BUILD_TOOLCHAIN_BLOCKED was unreachable-to-escape by construction."""
    root, manifest_path = make_repo(tmp_path)
    report = _build_api().inspect_build(root, manifest_path)

    assert not any(
        "compile adapter" in blocker.lower() for blocker in report["blockers"]
    ), "absence of an automated packager is a fact, not an unconditional blocker"


def test_missing_builder_is_a_genuine_toolchain_block(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    report = _build_api().inspect_build(root, manifest_path)

    assert report["status"] == "BUILD_TOOLCHAIN_BLOCKED"
    assert report["packaging_state"]["manual"] == "PACKAGING_MANUAL_UNAVAILABLE"
    assert any(
        "builder" in blocker for blocker in report["packaging_state"]["manual_blockers"]
    )


def test_automation_is_never_reported_as_proven(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    report = _build_api().inspect_build(root, manifest_path)

    state = report["packaging_state"]
    assert state["automation"] == "BUILD_AUTOMATION_UNPROVEN"
    assert state["automation_evidence"] is None
    assert set(state["unresolved_automation_prerequisites"]) == {
        "compiler_command", "content_validation",
    }


def test_unresolved_options_are_reported_apart_from_automation(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    report = _build_api().inspect_build(root, manifest_path)

    state = report["packaging_state"]
    assert state["recipe_complete"] is False
    assert set(state["unresolved_build_options"]) == {
        "engine_script_order", "custom_interface_order", "module_id",
        "startup", "privileges",
    }
    # Automation prerequisites are a different axis and must not appear here.
    assert "compiler_command" not in state["unresolved_build_options"]


@pytest.mark.skipif(
    not INSTALLED_BUILDER.is_file(),
    reason="the pinned Packet Tracer build is not installed on this machine",
)
def test_verified_builder_with_unresolved_options_is_automation_unproven(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    report = _build_api().inspect_build(
        root, manifest_path, builder_path=INSTALLED_BUILDER,
    )

    assert report["status"] == "BUILD_AUTOMATION_UNPROVEN"
    assert report["packaging_state"]["manual"] == "PACKAGING_MANUAL_AVAILABLE"
    assert report["packaging_state"]["recipe_complete"] is False
    assert report["build_recipe_id"] is None


@pytest.mark.skipif(
    not INSTALLED_BUILDER.is_file(),
    reason="the pinned Packet Tracer build is not installed on this machine",
)
def test_resolved_options_with_a_verified_builder_report_manual_packaging(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    manifest = _manifest()
    manifest["build_options"] = dict(RESOLVED_OPTIONS)
    _commit_manifest(root, manifest_path, manifest)

    report = _build_api().inspect_build(
        root, manifest_path, builder_path=INSTALLED_BUILDER,
    )

    assert report["status"] == "PACKAGING_MANUAL_AVAILABLE"
    assert report["packaging_state"]["manual"] == "PACKAGING_MANUAL_AVAILABLE"
    assert report["packaging_state"]["recipe_complete"] is True
    # A complete input inventory earns a recipe id; the artifact is still absent.
    assert report["build_recipe_id"] == _build_api().recipe_id(report["recipe"])
    assert report["artifact_sha256"] is None
    # Automation stays unproven even when a human could package this now.
    assert report["packaging_state"]["automation"] == "BUILD_AUTOMATION_UNPROVEN"
