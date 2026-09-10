"""What the real repository declares as build input, category by category.

`test_inventory` drives the same rules over synthetic repositories; this module
asserts them about the manifest this repository actually ships, so a
declaration that drifted from the tree on disk fails here rather than at
packaging time (MJ-013, MJ-017).
"""

from __future__ import annotations

import pytest

from tests.muejeje.measure import (
    packaged_sources,
    relative,
)
from tests.muejeje.support import (
    REPO_ROOT,
    repo_manifest,
)

LEGACY_ROOT = "EXTENSION/"


def test_every_packaged_owned_source_is_declared_as_an_artifact_input():
    declared = set(repo_manifest()["artifact_inputs"])
    on_disk = {relative(path) for path in packaged_sources()}
    assert on_disk == declared, (
        "a packaged source that is not declared would ship unrecorded, and a "
        "declared path that is not on disk cannot ship at all"
    )


def test_artifact_inputs_live_only_under_the_owned_source_root():
    for logical in repo_manifest()["artifact_inputs"]:
        assert logical.startswith("muejeje_pts/"), logical


def test_legacy_extension_is_not_a_muejeje_artifact_input():
    manifest = repo_manifest()
    for logical in manifest["artifact_inputs"]:
        assert not logical.startswith(LEGACY_ROOT), (
            "the legacy MCP Control Center extension keeps serving its own "
            f"product; it is not Muejeje artifact content: {logical}"
        )
    for logical in manifest["tooling_inputs"]:
        assert not logical.startswith(LEGACY_ROOT), logical


def test_tooling_inputs_are_the_auditor_not_artifact_content():
    from src.packet_tracer_mcp.infrastructure.pts import inventory

    tooling = list(repo_manifest()["tooling_inputs"])
    assert tooling == list(inventory.EXPECTED_TOOLING_INPUTS)
    for logical in tooling:
        assert not logical.startswith("muejeje_pts/"), (
            f"{logical} audits the artifact; it is not packaged into it"
        )


def test_artifact_inputs_match_the_auditor_expectation():
    from src.packet_tracer_mcp.infrastructure.pts import inventory

    assert list(repo_manifest()["artifact_inputs"]) == list(
        inventory.EXPECTED_ARTIFACT_INPUTS
    )


def test_artifact_and_tooling_inputs_cannot_overlap():
    manifest = repo_manifest()
    assert set(manifest["artifact_inputs"]).isdisjoint(manifest["tooling_inputs"])


def test_reference_inputs_remain_empty():
    assert repo_manifest()["reference_inputs"] == []


def test_manifest_declares_schema_version_two():
    assert repo_manifest()["schema_version"] == 2


@pytest.mark.parametrize("legacy", [
    "EXTENSION/script-engine/main.js",
    "EXTENSION/webview/interface.js",
    "EXTENSION/webview/index.html",
])
def test_legacy_extension_sources_are_still_present_and_untouched(legacy: str):
    """M0E isolates the legacy tree; it does not remove or move it."""
    assert (REPO_ROOT / legacy).is_file()
