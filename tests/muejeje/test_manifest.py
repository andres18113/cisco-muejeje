"""The manifest document itself: can it be read, and is its shape schema 2.

Everything here is about the JSON document: its shape, its Git identity, and
whether each declared build option carries a value the platform could accept.
What the declarations point at is `test_inventory`; what the answers mean is
`test_build_state`; where the report is written is `test_build_cli`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.muejeje.support import (
    RESOLVED_OPTIONS,
    build_api,
    commit_manifest,
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
    # A *valid* edit, so the only fact this test leaves standing is that the
    # working bytes drifted from HEAD. An unusable value would be an invalid
    # input as well, and that outranks a dirty tree.
    manifest["build_options"]["startup"] = "on_demand"
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
# Build options carry values, not just non-null placeholders.
# ---------------------------------------------------------------------------

INVALID_OPTIONS = [
    ("module_id", "muejeje", "hierarchical"),
    ("module_id", "IO.GitHub.Muejeje.Runtime", "lowercase"),
    ("module_id", "io..runtime", "lowercase"),
    ("module_id", 7, "must be a string"),
    ("startup", "whenever", "must be one of"),
    ("startup", True, "must be one of"),
    ("startup", ["on_startup"], "must be one of"),
    ("custom_interface_order", "muejeje_pts/interface/index.html", "must be a list"),
    ("custom_interface_order", [], "at least one"),
    ("custom_interface_order", ["../secret.html"], "relative POSIX path"),
    ("custom_interface_order", [r"muejeje_pts\interface\index.html"],
     "relative POSIX path"),
    ("custom_interface_order", ["muejeje_pts/interface/nowhere.html"],
     "declared artifact inputs"),
    ("custom_interface_order", [7], "non-empty strings"),
    ("privileges", "PrivGetNetwork", "must be a list"),
    ("privileges", [""], "non-empty strings"),
    ("privileges", ["PrivOne", "PrivOne"], "must not repeat"),
    ("engine_script_order", ["muejeje_pts/script-engine/core.js"],
     "declared artifact inputs"),
]


@pytest.mark.parametrize(("option", "value", "reason"), INVALID_OPTIONS)
def test_a_resolved_build_option_with_an_unusable_value_is_invalid(
    tmp_path: Path, option: str, value: object, reason: str,
):
    """Non-null is not resolved. `startup: "whenever"` names no startup mode.

    The audit previously asked only whether each option was set, so a manifest
    could reach a complete recipe carrying a module id Packet Tracer would
    reject, a startup mode that does not exist, or an interface order pointing
    at a file that ships in no artifact. A recipe id over values like those
    identifies a build nobody can perform.
    """
    root, manifest_path = make_repo(tmp_path)
    manifest = manifest_document()
    manifest["build_options"] = dict(RESOLVED_OPTIONS) | {option: value}
    commit_manifest(root, manifest_path, manifest)

    report = build_api().inspect_build(root, manifest_path)

    assert report["status"] == "BUILD_INPUT_INVALID"
    assert report["build_recipe_id"] is None
    assert any(reason in blocker for blocker in report["blockers"]), report["blockers"]


def test_an_unset_option_is_unresolved_rather_than_invalid(tmp_path: Path):
    """The two are different facts, and the states must stay different.

    `null` means nobody has decided yet — nothing is broken, so the audit
    reports `BUILD_AUTOMATION_UNPROVEN`. A decided-but-unusable value is a
    contract violation. Collapsing them would make "we have not chosen a
    module id" and "this module id cannot work" read the same (MJ-016).
    """
    root, manifest_path = make_repo(tmp_path)
    manifest = manifest_document()
    manifest["build_options"] = dict(RESOLVED_OPTIONS) | {"module_id": None}
    commit_manifest(root, manifest_path, manifest)

    report = build_api().inspect_build(root, manifest_path)

    assert report["status"] != "BUILD_INPUT_INVALID"
    assert report["packaging_state"]["unresolved_build_options"] == ["module_id"]
    assert any("unresolved build option: module_id" in b for b in report["blockers"])
    assert not any("invalid build option" in b for b in report["blockers"])


def test_an_empty_privilege_set_is_a_decision_not_an_omission(tmp_path: Path):
    """`privileges: []` is resolved: the module asks for nothing (MJ-025)."""
    root, manifest_path = make_repo(tmp_path)
    manifest = manifest_document()
    manifest["build_options"] = dict(RESOLVED_OPTIONS)
    commit_manifest(root, manifest_path, manifest)

    report = build_api().inspect_build(root, manifest_path)

    assert report["packaging_state"]["unresolved_build_options"] == []
    assert report["packaging_state"]["recipe_complete"] is True
    assert not any("privileges" in blocker for blocker in report["blockers"])
