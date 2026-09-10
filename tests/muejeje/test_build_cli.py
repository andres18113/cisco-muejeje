"""The build CLI: one fixed report destination, and nothing else touched.

`tools/build_muejeje_pts.py --check` inspects and writes
`dist/muejeje.build.json`. It compiles nothing, and it must never write
anywhere else — the destination checks here exist because a report path that is
a symlink or a hard-link alias would let a check overwrite a `.pts` somebody
still needs (MJ-017).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.muejeje.support import CLI, build_api, git, make_repo


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
