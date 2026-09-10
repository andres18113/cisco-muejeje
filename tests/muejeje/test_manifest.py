"""The manifest document itself: can it be read, and is its shape schema 2.

Everything here is about the JSON document. What the declarations point at is
`test_inventory`; what the answers mean is `test_build_state`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.muejeje.support import (
    CLI,
    build_api,
    git,
    make_repo,
    manifest_document,
)


@pytest.mark.parametrize("bad_manifest", [
    "{", "[]", '{"schema_version":2}', '{"schema_version":true}',
    '{"schema_version":1,"value":NaN}',
])
def test_malformed_or_wrong_schema_is_invalid(tmp_path: Path, bad_manifest: str):
    root, manifest_path = make_repo(tmp_path)
    manifest_path.write_text(bad_manifest, encoding="utf-8")

    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert report["build_recipe_id"] is None


@pytest.mark.parametrize("bad_value", [True, float("nan")])
def test_noncanonical_json_values_are_invalid(tmp_path: Path, bad_value: object):
    root, manifest_path = make_repo(tmp_path)
    manifest = manifest_document()
    if bad_value is True:
        manifest["schema_version"] = bad_value
    else:
        manifest["unexpected"] = bad_value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("manifest" in blocker.lower() for blocker in report["blockers"])


def test_schema_blocker_is_the_one_fatal_shape_error():
    from src.packet_tracer_mcp.infrastructure.pts import manifest as schema

    assert schema.schema_blocker(manifest_document()) is None
    assert "schema_version" in (schema.schema_blocker({"schema_version": 1}) or "")
    document = manifest_document()
    del document["packaging"]
    assert "top-level sections" in (schema.schema_blocker(document) or "")


def test_manifest_must_be_tracked_and_own_bytes_must_match_head(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    git(root, "rm", "--cached", str(manifest_path.relative_to(root)))
    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any(
        "manifest" in blocker and "tracked" in blocker
        for blocker in report["blockers"]
    )

    git(root, "add", str(manifest_path.relative_to(root)))
    own = root / "muejeje_pts/script-engine/lifecycle.js"
    git(root, "update-index", "--assume-unchanged", str(own.relative_to(root)))
    own.write_text("hidden dirty bytes", encoding="utf-8")
    try:
        report = build_api().inspect_build(root, manifest_path)
    finally:
        git(root, "update-index", "--no-assume-unchanged", str(own.relative_to(root)))
    assert report["status"] == "BUILD_SOURCE_INVALID"
    assert report["source"]["clean"] is False
    assert any("HEAD" in blocker and "lifecycle.js" in blocker for blocker in report["blockers"])


def test_manifest_bytes_must_match_head_even_when_assume_unchanged(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    logical = str(manifest_path.relative_to(root))
    git(root, "update-index", "--assume-unchanged", logical)
    manifest = manifest_document()
    manifest["build_options"]["module_id"] = "synthetic-module"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    try:
        report = build_api().inspect_build(root, manifest_path)
    finally:
        git(root, "update-index", "--no-assume-unchanged", logical)
    assert report["status"] == "BUILD_SOURCE_INVALID"
    assert report["source"]["clean"] is False
    assert any("manifest bytes differ from HEAD" in blocker for blocker in report["blockers"])


def test_non_git_source_is_source_invalid(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    (root / ".git").rename(root / ".git-disabled")
    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_SOURCE_INVALID"
    assert any("Git source inspection failed" in blocker for blocker in report["blockers"])


def test_unsafe_input_and_output_paths_are_rejected(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    manifest = manifest_document()
    manifest["artifact_inputs"][0] = "../secret.js"
    manifest["output"]["report"] = "../report.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any(
        "noncanonical" in blocker or "unsafe" in blocker
        for blocker in report["blockers"]
    )


def test_report_symlink_escape_is_rejected(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "dist").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink privilege unavailable: {exc}")

    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("dist" in blocker.lower() for blocker in report["blockers"])


# ---------------------------------------------------------------------------
# The CLI writes one fixed report and never anything else.
# ---------------------------------------------------------------------------

def test_overflowing_json_number_returns_structured_invalid_report(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    text = manifest_path.read_text(encoding="utf-8").replace(
        '"module_id": null', '"module_id": 1e999',
    )
    manifest_path.write_text(text, encoding="utf-8")
    report = build_api().inspect_build(root, manifest_path)
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


def test_cli_writes_only_fixed_report_and_preserves_stable_pts(tmp_path: Path):
    root, _ = make_repo(tmp_path)
    stable = root / "stable.pts"
    stable.write_bytes(b"stable sentinel")
    git(root, "add", "stable.pts")
    git(root, "commit", "-qm", "stable sentinel")

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
