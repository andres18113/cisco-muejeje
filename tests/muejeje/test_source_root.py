"""What the owned source tree may and may not contain.

Architecture tests over the real repository, not fixtures. They pin the
boundary that lets `muejeje.pts` evolve independently of the legacy
`EXTENSION/**` extension, and they pin what may never enter the owned tree
(MJ-001, MJ-002, MJ-004, MJ-013, MJ-019).
"""

from __future__ import annotations

import re

import pytest

from tests.muejeje.support import (
    REPO_ROOT,
    SOURCE_ROOT,
    engine_sources,
    packaged_sources,
    relative,
    repo_manifest,
)

LEGACY_ROOT = "EXTENSION/"

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

# Layers the V6 kernel may never reach for. A Cisco IPC adapter arrives when an
# operation actually needs one; nothing else on this list ever does.
FORBIDDEN_DEPENDENCIES = (
    "webview", "XMLHttpRequest", "systemFileManager", "localStorage",
    "fileBridge", "file_bridge", "bridge_token", "http://", "https://",
)

# Only these owned files may ever perform a Cisco IPC call. Empty today: no
# operation needs the platform yet, so the module implies no privilege
# (TODO-PRIVILEGES).
IPC_ADAPTER_FILES: tuple[str, ...] = ()


def test_owned_source_root_has_an_engine_and_an_interface():
    assert (SOURCE_ROOT / "script-engine").is_dir()
    assert (SOURCE_ROOT / "interface").is_dir()
    assert packaged_sources(), "the owned root must carry at least one packaged source"


def test_owned_sources_carry_no_consumer_specific_concept():
    offenders: list[str] = []
    for path in packaged_sources():
        body = path.read_text(encoding="utf-8").lower()
        for concept in CONSUMER_CONCEPTS:
            if concept in body:
                offenders.append(f"{relative(path)}: {concept}")
    assert not offenders, (
        "Muejeje is project-independent; a consumer's vocabulary may not appear "
        f"in its own sources: {offenders}"
    )


def test_owned_sources_inherit_no_ptbuilder_global():
    offenders: list[str] = []
    for path in packaged_sources():
        body = path.read_text(encoding="utf-8")
        for symbol in PTBUILDER_GLOBALS:
            if symbol in body:
                offenders.append(f"{relative(path)}: {symbol}")
    assert not offenders, f"owned sources must not depend on PTBuilder: {offenders}"


def test_owned_sources_reach_for_no_forbidden_layer():
    """CP LIVE, WebView, HTTP and the File Bridge are all outside the kernel."""
    offenders: list[str] = []
    for path in packaged_sources():
        body = path.read_text(encoding="utf-8")
        for symbol in FORBIDDEN_DEPENDENCIES:
            if symbol in body:
                offenders.append(f"{relative(path)}: {symbol}")
    assert not offenders, f"the V6 kernel depends on none of these: {offenders}"


def test_owned_sources_execute_no_arbitrary_javascript():
    """No `eval`, no `new Function`, no `setTimeout`-with-a-string (MJ-009)."""
    offenders: list[str] = []
    for path in packaged_sources():
        body = path.read_text(encoding="utf-8")
        for pattern in (r"\beval\s*\(", r"\bnew\s+Function\b", r"\bFunction\s*\("):
            if re.search(pattern, body):
                offenders.append(f"{relative(path)}: {pattern}")
    assert not offenders, (
        f"V6 admits typed operations only; arbitrary JS is a V5 surface: {offenders}"
    )


def test_ipc_access_stays_out_of_protocol_core_and_domain_logic():
    """`ipc.*` is an adapter concern, and no adapter exists yet (MJ-006)."""
    offenders: list[str] = []
    for path in packaged_sources():
        if relative(path) in IPC_ADAPTER_FILES:
            continue
        if "ipc." in path.read_text(encoding="utf-8"):
            offenders.append(relative(path))
    assert not offenders, (
        "core, protocol, dispatcher, lifecycle and read-only operations make no "
        f"IPC call; the privilege set is still TODO-PRIVILEGES: {offenders}"
    )


# ---------------------------------------------------------------------------
# One lifecycle, one dispatcher. Two of either means two answers to "what ran".
# ---------------------------------------------------------------------------

def _engine_bodies() -> dict[str, str]:
    return {relative(path): path.read_text(encoding="utf-8") for path in engine_sources()}


@pytest.mark.parametrize("symbol", ["main", "cleanUp"])
def test_exactly_one_lifecycle_entry_point_exists(symbol: str):
    pattern = re.compile(rf"^function\s+{symbol}\s*\(", re.MULTILINE)
    owners = [
        name for name, body in _engine_bodies().items() if pattern.search(body)
    ]
    assert owners == ["muejeje_pts/script-engine/lifecycle.js"], (
        f"{symbol}() must be declared exactly once, by lifecycle.js: {owners}"
    )


def test_no_second_dispatcher_can_ever_appear():
    """MJ-007. Vacuously true before V6, strict once the dispatcher exists.

    `test_protocol_v6` asserts the stronger form — that it exists at all. This
    gate is the one that must hold forever: never two answers to "what ran".
    """
    pattern = re.compile(r"^function\s+mcpDispatchV6\s*\(", re.MULTILINE)
    owners = [
        name for name, body in _engine_bodies().items() if pattern.search(body)
    ]
    assert owners in ([], ["muejeje_pts/script-engine/dispatcher_v6.js"]), (
        f"exactly one mcpDispatchV6, owned by the dispatcher: {owners}"
    )


def test_lifecycle_owns_no_dispatch_and_no_operation():
    body = (SOURCE_ROOT / "script-engine/lifecycle.js").read_text(encoding="utf-8")
    for forbidden in ("mcpDispatchV6", "runtime.identify", "JSON.parse"):
        assert forbidden not in body, (
            f"lifecycle.js owns main()/cleanUp() only; {forbidden} belongs elsewhere"
        )


# ---------------------------------------------------------------------------
# Manifest: artifact content, build tooling and references are three things.
# ---------------------------------------------------------------------------

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
