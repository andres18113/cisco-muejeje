"""Artifact content, build tooling and references are three categories.

The v1 manifest put `muejeje_pts` sources and the auditor itself in one
`own_inputs` list, so "what ships inside the .pts" and "what decides how it was
audited" were indistinguishable. Both belong to recipe identity; only one
belongs to the artifact.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.muejeje.support import (
    REFERENCE_PATH,
    build_api,
    commit_manifest,
    git,
    make_repo,
    manifest_document,
    reference_entry,
)

LEGACY_ASSET = "EXTENSION/script-engine/main.js"


def test_report_separates_artifact_from_tooling_inputs(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    report = build_api().inspect_build(root, manifest_path)

    artifact = [entry["path"] for entry in report["inputs"]["artifact"]]
    tooling = [entry["path"] for entry in report["inputs"]["tooling"]]

    assert artifact == list(manifest_document()["artifact_inputs"])
    assert tooling == list(manifest_document()["tooling_inputs"])
    assert set(artifact).isdisjoint(tooling)
    assert all(path.startswith("muejeje_pts/") for path in artifact)
    assert not any(path.startswith("muejeje_pts/") for path in tooling)


def test_artifact_and_tooling_inputs_may_not_overlap(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    manifest = manifest_document()
    manifest["tooling_inputs"].append("muejeje_pts/script-engine/220_lifecycle.js")
    commit_manifest(root, manifest_path, manifest)

    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any(
        "may not be both artifact content and tooling" in blocker
        for blocker in report["blockers"]
    )


def test_missing_and_omitted_artifact_inputs_are_reported(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    missing = root / "muejeje_pts/interface/index.html"
    missing.unlink()
    report = build_api().inspect_build(root, manifest_path)
    assert report["build_recipe_id"] is None
    assert any(
        "missing artifact input" in blocker and "index.html" in blocker
        for blocker in report["blockers"]
    )

    git(root, "checkout", "--", str(missing.relative_to(root)))
    manifest = manifest_document()
    manifest["artifact_inputs"].remove("muejeje_pts/interface/index.html")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("complete ordered" in blocker for blocker in report["blockers"])


def test_dirty_source_and_unexpected_owned_assets_are_invalid(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    (root / "muejeje_pts/interface/index.html").write_text("dirty", encoding="utf-8")
    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_SOURCE_INVALID"
    assert any("dirty" in blocker.lower() for blocker in report["blockers"])

    git(root, "checkout", "--", "muejeje_pts/interface/index.html")
    extra = root / "muejeje_pts/interface/extra.css"
    extra.write_text("extra", encoding="utf-8")
    git(root, "add", "-f", "muejeje_pts/interface/extra.css")
    git(root, "commit", "-qm", "extra tracked asset")
    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("extra.css" in blocker for blocker in report["blockers"])


def test_untracked_artifact_input_is_still_rejected(tmp_path: Path):
    """A path-safety regression that must survive the recategorisation."""
    root, manifest_path = make_repo(tmp_path)
    git(root, "rm", "--cached", "-q", "muejeje_pts/script-engine/220_lifecycle.js")
    git(root, "commit", "-qm", "untrack an artifact input")

    report = build_api().inspect_build(root, manifest_path)
    assert any(
        "not tracked" in blocker and "220_lifecycle.js" in blocker
        for blocker in report["blockers"]
    )


def test_legacy_extension_asset_is_rejected_as_artifact_content(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    legacy = root / LEGACY_ASSET
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("legacy\n", encoding="utf-8")
    manifest = manifest_document()
    manifest["artifact_inputs"].append(LEGACY_ASSET)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    git(root, "add", LEGACY_ASSET, "muejeje_pts/manifest/muejeje-build-manifest.json")
    git(root, "commit", "-qm", "legacy asset")

    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any(
        "artifact input must live under the owned source root" in blocker
        and LEGACY_ASSET in blocker
        for blocker in report["blockers"]
    )


def test_legacy_extension_assets_are_not_swept_into_the_inventory(tmp_path: Path):
    """The v1 model required every tracked EXTENSION asset to be declared. The
    legacy extension now serves its own product and is none of Muejeje's."""
    root, manifest_path = make_repo(tmp_path)
    legacy = root / "EXTENSION/webview/legacy-only.js"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("legacy only\n", encoding="utf-8")
    git(root, "add", "EXTENSION/webview/legacy-only.js")
    git(root, "commit", "-qm", "legacy-only asset")

    report = build_api().inspect_build(root, manifest_path)
    assert not any("legacy-only.js" in blocker for blocker in report["blockers"])
    assert not any(
        entry["path"] == "EXTENSION/webview/legacy-only.js"
        for entry in report["inputs"]["artifact"] + report["inputs"]["tooling"]
    )


# ---------------------------------------------------------------------------
# Reference inputs: untracked, ignored, hash-pinned. Empty today (MJ-013).
# ---------------------------------------------------------------------------

def test_optional_reference_with_matching_pin_is_accepted(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    manifest = manifest_document()
    entry = reference_entry(root)
    manifest["reference_inputs"] = [entry]
    commit_manifest(root, manifest_path, manifest)

    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_TOOLCHAIN_BLOCKED"
    assert report["inputs"]["reference"] == [{
        "path": REFERENCE_PATH,
        "expected_sha256": entry["sha256"],
        "actual_sha256": entry["sha256"],
    }]
    assert not any("reference" in blocker.lower() for blocker in report["blockers"])


def test_optional_reference_hash_mismatch_is_invalid(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    manifest = manifest_document()
    entry = reference_entry(root)
    entry["sha256"] = "0" * 64
    manifest["reference_inputs"] = [entry]
    commit_manifest(root, manifest_path, manifest)

    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("mismatch" in blocker.lower() for blocker in report["blockers"])


def test_tracked_reference_is_invalid_even_when_ignore_rule_matches(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    manifest = manifest_document()
    entry = reference_entry(root)
    manifest["reference_inputs"] = [entry]
    commit_manifest(root, manifest_path, manifest)
    ref = root / REFERENCE_PATH
    git(root, "add", "-f", str(ref.relative_to(root)))
    git(root, "commit", "-qm", "bad tracked reference")

    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any(
        "tracked" in blocker and REFERENCE_PATH in blocker
        for blocker in report["blockers"]
    )


def test_optional_reference_must_be_ignored(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    path = root / "api-reference.txt"
    contents = b"synthetic API reference\n"
    path.write_bytes(contents)
    manifest = manifest_document()
    manifest["reference_inputs"] = [{
        "path": "api-reference.txt",
        "sha256": hashlib.sha256(contents).hexdigest(),
    }]
    commit_manifest(root, manifest_path, manifest)

    report = build_api().inspect_build(root, manifest_path)
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
    manifest = manifest_document()
    manifest["reference_inputs"] = [entry]
    commit_manifest(root, manifest_path, manifest)

    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == expected_status
    assert report["build_recipe_id"] is None
    assert report["artifact_sha256"] is None
    assert any(expected_blocker in blocker for blocker in report["blockers"])


def test_duplicate_optional_reference_paths_are_invalid(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    manifest = manifest_document()
    entry = reference_entry(root)
    manifest["reference_inputs"] = [entry, dict(entry)]
    commit_manifest(root, manifest_path, manifest)

    report = build_api().inspect_build(root, manifest_path)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("duplicate reference input" in blocker for blocker in report["blockers"])


# ---------------------------------------------------------------------------
# The builder is a declared input with a pinned hash.
# ---------------------------------------------------------------------------

def test_malformed_builder_with_explicit_file_returns_invalid_report(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    manifest = manifest_document()
    manifest["builder"] = None
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    builder = tmp_path / "builder.exe"
    builder.write_bytes(b"synthetic builder")

    report = build_api().inspect_build(root, manifest_path, builder_path=builder)
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert any("builder" in blocker for blocker in report["blockers"])


def test_builder_hash_mismatch_blocks_manual_packaging(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    builder = tmp_path / "not-packet-tracer.exe"
    builder.write_bytes(b"a different binary")

    report = build_api().inspect_build(root, manifest_path, builder_path=builder)
    assert "builder SHA-256 mismatch" in report["packaging_state"]["manual_blockers"]
    assert report["packaging_state"]["manual"] == "PACKAGING_MANUAL_UNAVAILABLE"
