"""M0E: the Muejeje artifact owns its own source tree.

These are architecture tests over the real repository, not fixtures. They pin
the boundary that lets `muejeje.pts` evolve independently of the legacy
`EXTENSION/**` extension, and they pin what may never enter the owned tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "muejeje_pts"
MANIFEST = REPO_ROOT / "muejeje_pts/manifest/muejeje-build-manifest.json"
LEGACY_ROOT = "EXTENSION/"

# Packageable extensions. A README is documentation, not artifact content.
PACKAGED_SUFFIXES = {".js", ".html", ".htm", ".css", ".png", ".gif", ".jpg", ".svg"}

# The six globals PTBuilder supplies today. Inheriting any of them is what the
# owned source root exists to avoid (MJ-013).
PTBUILDER_GLOBALS = (
    "htmlWindow", "runCode", "configureIosDevice", "allModuleTypes",
    "addDevice", "addLink",
)

# Consumer-specific concepts. Muejeje is a generic Packet Tracer runtime
# (MJ-001, MJ-002, MJ-004); a consumer's vocabulary must not reach it.
CONSUMER_CONCEPTS = (
    "cp-live", "cp_live", "cplive", "cp-scale", "cp_scale",
    "poe", "router0", "ripv2", "vlan", "voice", "dhcp", "ospf", "eigrp",
)


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _packaged_sources() -> list[Path]:
    return sorted(
        path for path in SOURCE_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in PACKAGED_SUFFIXES
    )


def test_owned_source_root_has_an_engine_and_an_interface():
    assert (SOURCE_ROOT / "script-engine").is_dir()
    assert (SOURCE_ROOT / "interface").is_dir()
    assert _packaged_sources(), "the owned root must carry at least one packaged source"


def test_owned_sources_carry_no_consumer_specific_concept():
    offenders: list[str] = []
    for path in _packaged_sources():
        body = path.read_text(encoding="utf-8").lower()
        for concept in CONSUMER_CONCEPTS:
            if concept in body:
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {concept}")
    assert not offenders, (
        "Muejeje is project-independent; a consumer's vocabulary may not appear "
        f"in its own sources: {offenders}"
    )


def test_owned_sources_inherit_no_ptbuilder_global():
    offenders: list[str] = []
    for path in _packaged_sources():
        body = path.read_text(encoding="utf-8")
        for symbol in PTBUILDER_GLOBALS:
            if symbol in body:
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {symbol}")
    assert not offenders, f"owned sources must not depend on PTBuilder: {offenders}"


def test_lifecycle_owns_main_and_cleanup_without_a_dispatcher():
    body = (SOURCE_ROOT / "script-engine/lifecycle.js").read_text(encoding="utf-8")
    assert "function main()" in body
    assert "function cleanUp()" in body
    # V6 is not implemented in M0E and must not appear to be.
    for forbidden in ("mcpDispatchV6", "runtime.identify", "new Function"):
        assert forbidden not in body, f"{forbidden} must not exist yet"


def test_owned_sources_make_no_ipc_call_so_no_privilege_is_implied():
    for path in _packaged_sources():
        body = path.read_text(encoding="utf-8")
        assert "ipc." not in body, (
            f"{path.name} calls ipc.*; the privilege set is still TODO-PRIVILEGES"
        )


# --------------------------------------------------------------------------
# Manifest: artifact content, build tooling and references are three things.
# --------------------------------------------------------------------------

def test_every_packaged_owned_source_is_declared_as_an_artifact_input():
    declared = set(_manifest()["artifact_inputs"])  # type: ignore[index]
    on_disk = {
        path.relative_to(REPO_ROOT).as_posix() for path in _packaged_sources()
    }
    assert on_disk == declared, (
        "a packaged source that is not declared would ship unrecorded, and a "
        "declared path that is not on disk cannot ship at all"
    )


def test_artifact_inputs_live_only_under_the_owned_source_root():
    for logical in _manifest()["artifact_inputs"]:  # type: ignore[union-attr]
        assert logical.startswith("muejeje_pts/"), logical


def test_legacy_extension_is_not_a_muejeje_artifact_input():
    manifest = _manifest()
    for logical in manifest["artifact_inputs"]:  # type: ignore[union-attr]
        assert not logical.startswith(LEGACY_ROOT), (
            "the legacy MCP Control Center extension keeps serving its own "
            f"product; it is not Muejeje artifact content: {logical}"
        )
    # It is not smuggled in through the other categories either.
    for logical in manifest["tooling_inputs"]:  # type: ignore[union-attr]
        assert not logical.startswith(LEGACY_ROOT), logical


def test_tooling_inputs_are_the_auditor_not_artifact_content():
    tooling = set(_manifest()["tooling_inputs"])  # type: ignore[index]
    assert tooling == {
        "src/packet_tracer_mcp/infrastructure/pts/build.py",
        "tools/build_muejeje_pts.py",
    }
    for logical in tooling:
        assert not logical.startswith("muejeje_pts/"), (
            f"{logical} audits the artifact; it is not packaged into it"
        )


def test_artifact_and_tooling_inputs_cannot_overlap():
    manifest = _manifest()
    artifact = set(manifest["artifact_inputs"])  # type: ignore[index]
    tooling = set(manifest["tooling_inputs"])  # type: ignore[index]
    assert artifact.isdisjoint(tooling)


def test_reference_inputs_remain_empty():
    assert _manifest()["reference_inputs"] == []


def test_manifest_declares_schema_version_two():
    assert _manifest()["schema_version"] == 2


@pytest.mark.parametrize("legacy", [
    "EXTENSION/script-engine/main.js",
    "EXTENSION/webview/interface.js",
    "EXTENSION/webview/index.html",
])
def test_legacy_extension_sources_are_still_present_and_untouched(legacy: str):
    """M0E isolates the legacy tree; it does not remove or move it."""
    assert (REPO_ROOT / legacy).is_file()
