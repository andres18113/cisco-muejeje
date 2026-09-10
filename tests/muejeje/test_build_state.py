"""The build-state model: five facts must stay five distinct states.

The previous model returned `BUILD_TOOLCHAIN_BLOCKED` for a repository whose
inputs and source were fine, whose builder was verified, and whose only
outstanding items were unresolved build options and the absence of an automated
packaging path. Those are three different facts and one of them is not a defect
at all: manual Scripting Interface packaging is available (MJ-016).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.muejeje.support import (
    INSTALLED_BUILDER,
    resolved_options,
    build_api,
    commit_manifest,
    make_repo,
    manifest_document,
)


def test_build_states_are_five_distinct_names():
    build = build_api()
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
    assert build_api().classify_build_state(**flags) == expected


def test_classify_build_state_is_pure_and_needs_no_repository():
    """The state machine is separable from every measurement that feeds it."""
    from src.packet_tracer_mcp.infrastructure.pts import build_state

    assert build_state.classify_build_state(**_axes()) == "PACKAGING_MANUAL_AVAILABLE"
    # The state model imports nothing that touches a repository, a file or a
    # process, so it can never grow a measurement it should be handed instead.
    for forbidden in ("subprocess", "hashlib", "json", "Path", "inventory"):
        assert forbidden not in vars(build_state), forbidden


def test_findings_split_blockers_from_manual_blockers():
    from src.packet_tracer_mcp.infrastructure.pts.build_state import Findings

    findings = Findings()
    findings.block("unresolved build option: module_id")
    assert findings.toolchain_unusable is False

    findings.block_manual("missing artifact input: muejeje_pts/x.js")
    assert findings.toolchain_unusable is True
    assert findings.manual_blockers == ["missing artifact input: muejeje_pts/x.js"]
    # A manual blocker is always a blocker too; it is never only one of the two.
    assert findings.manual_blockers[0] in findings.blockers


def test_empty_reference_inventory_has_only_unresolved_toolchain_blockers(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    report = build_api().inspect_build(root, manifest_path)

    assert report["status"] == "BUILD_TOOLCHAIN_BLOCKED"
    assert report["build_recipe_id"] is None
    assert report["artifact_sha256"] is None
    assert "artifact_sha256" not in report["recipe"]
    assert report["inputs"]["reference"] == []
    assert not any("reference" in blocker.lower() for blocker in report["blockers"])
    for option in manifest_document()["build_options"]:
        assert any(option in blocker for blocker in report["blockers"])
    assert any("compiler_command" in blocker for blocker in report["blockers"])
    assert any("content_validation" in blocker for blocker in report["blockers"])


def test_absent_automation_alone_is_not_a_toolchain_block(tmp_path: Path):
    """The old model appended an unconditional compile-adapter blocker, so
    BUILD_TOOLCHAIN_BLOCKED was unreachable-to-escape by construction."""
    root, manifest_path = make_repo(tmp_path)
    report = build_api().inspect_build(root, manifest_path)

    assert not any(
        "compile adapter" in blocker.lower() for blocker in report["blockers"]
    ), "absence of an automated packager is a fact, not an unconditional blocker"


def test_missing_builder_is_a_genuine_toolchain_block(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    report = build_api().inspect_build(root, manifest_path)

    assert report["status"] == "BUILD_TOOLCHAIN_BLOCKED"
    assert report["packaging_state"]["manual"] == "PACKAGING_MANUAL_UNAVAILABLE"
    assert any(
        "builder" in blocker for blocker in report["packaging_state"]["manual_blockers"]
    )


def test_automation_is_never_reported_as_proven(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    report = build_api().inspect_build(root, manifest_path)

    state = report["packaging_state"]
    assert state["automation"] == "BUILD_AUTOMATION_UNPROVEN"
    assert state["automation_evidence"] is None
    assert set(state["unresolved_automation_prerequisites"]) == {
        "compiler_command", "content_validation",
    }


def test_unresolved_options_are_reported_apart_from_automation(tmp_path: Path):
    root, manifest_path = make_repo(tmp_path)
    report = build_api().inspect_build(root, manifest_path)

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
    report = build_api().inspect_build(
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
    manifest = manifest_document()
    manifest["build_options"] = resolved_options()
    commit_manifest(root, manifest_path, manifest)

    report = build_api().inspect_build(
        root, manifest_path, builder_path=INSTALLED_BUILDER,
    )

    assert report["status"] == "PACKAGING_MANUAL_AVAILABLE"
    assert report["packaging_state"]["manual"] == "PACKAGING_MANUAL_AVAILABLE"
    assert report["packaging_state"]["recipe_complete"] is True
    # A complete input inventory earns a recipe id; the artifact is still absent.
    assert report["build_recipe_id"] == build_api().recipe_id(report["recipe"])
    assert report["artifact_sha256"] is None
    # Automation stays unproven even when a human could package this now.
    assert report["packaging_state"]["automation"] == "BUILD_AUTOMATION_UNPROVEN"
