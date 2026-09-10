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
    layer_offenders,
    packaged_sources,
    relative,
    symbols_present,
)

# The six globals PTBuilder supplies today. Inheriting any of them is what the
# owned source root exists to avoid (MJ-013).
PTBUILDER_GLOBALS = (
    "htmlWindow", "runCode", "configureIosDevice", "allModuleTypes",
    "addDevice", "addLink",
)

# A consumer's *identifiers*: the project a scenario belongs to, and the device
# names one topology happens to use. These are what MJ-004 excludes.
CONSUMER_PROJECT_IDENTIFIERS = (
    "cp-live", "cp_live", "cplive", "cp-scale", "cp_scale",
)
TOPOLOGY_IDENTIFIERS = ("router0", "switch0", "pc0", "server0", "laptop0")

# Generic networking vocabulary is *not* a consumer identifier. DHCP, VLAN,
# OSPF and PoE are Packet Tracer's domain rather than any one consumer's, and a
# runtime forbidden from naming them could never describe the platform it
# adapts to. An earlier gate listed them beside the project identifiers, which
# made "generic" and "project-specific" indistinguishable.
GENERIC_NETWORKING_VOCABULARY = (
    "dhcp", "vlan", "ospf", "eigrp", "poe", "voice", "ripv2",
)

# Layers outside the V6 kernel. Naming one is how a dependency on it starts.
TRANSPORT_SYMBOLS = (
    "webview", "XMLHttpRequest", "systemFileManager", "localStorage",
    "fileBridge", "file_bridge", "bridge_token", "http://", "https://",
)
IPC_SYMBOLS = ("ipc.",)

# Declared adapters, by path. Only a declared adapter may name the layer it
# adapts; every other packaged source is kernel and may not. Both are empty
# today — no operation needs a transport or the platform yet — so the strict
# boundary currently applies to every packaged source. Declaring one later is
# an edit to this gate, which is the point: an adapter arrives visibly.
TRANSPORT_ADAPTER_FILES: tuple[str, ...] = ()
IPC_ADAPTER_FILES: tuple[str, ...] = ()

# A dotted-quad literal is a hard-coded endpoint, which is a topology
# assumption wearing a transport's clothes (MJ-002). The baselined HTTP default
# lives in the requirements; it never lives in the kernel.
ADDRESS_LITERAL = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def _packaged_bodies() -> dict[str, str]:
    return {
        relative(path): path.read_text(encoding="utf-8")
        for path in packaged_sources()
    }


def test_owned_source_root_has_an_engine_and_an_interface():
    assert (SOURCE_ROOT / "script-engine").is_dir()
    assert (SOURCE_ROOT / "interface").is_dir()
    assert packaged_sources(), "the owned root must carry at least one packaged source"


# ---------------------------------------------------------------------------
# Vocabulary: a consumer's identifiers stay out; the platform's domain does not.
# ---------------------------------------------------------------------------

def test_owned_sources_carry_no_consumer_project_or_topology_identifier():
    offenders = layer_offenders(
        _packaged_bodies(),
        CONSUMER_PROJECT_IDENTIFIERS + TOPOLOGY_IDENTIFIERS,
        adapters=(),
    )
    assert not offenders, (
        "Muejeje is project-independent; a consumer's own identifiers may not "
        f"appear in its sources: {offenders}"
    )


def test_the_vocabulary_gate_rejects_identifiers_without_rejecting_the_domain():
    """The correction, asserted in both directions on synthetic sources.

    Rejecting `dhcp` as if it were consumer-specific would forbid the runtime
    from ever naming what Packet Tracer does, so the gate has to separate "a
    consumer's project" from "the platform's domain" rather than treat every
    networking word as the former.
    """
    identifiers = CONSUMER_PROJECT_IDENTIFIERS + TOPOLOGY_IDENTIFIERS
    domain = "var note = 'DHCP, VLAN, OSPF and PoE are the platform domain';"
    scenario = "var note = 'this is the CP-LIVE Router0 topology';"

    assert symbols_present(domain, identifiers) == []
    assert symbols_present(domain, GENERIC_NETWORKING_VOCABULARY)
    assert sorted(symbols_present(scenario, identifiers)) == ["cp-live", "router0"]


def test_owned_sources_inherit_no_ptbuilder_global():
    offenders = layer_offenders(_packaged_bodies(), PTBUILDER_GLOBALS, adapters=())
    assert not offenders, f"owned sources must not depend on PTBuilder: {offenders}"


# ---------------------------------------------------------------------------
# Layers: the kernel stays independent, and an adapter stays possible.
# ---------------------------------------------------------------------------

def test_the_kernel_reaches_for_no_transport_layer():
    """WebView, HTTP, the File Bridge and browser storage are outside it."""
    offenders = layer_offenders(
        _packaged_bodies(), TRANSPORT_SYMBOLS, adapters=TRANSPORT_ADAPTER_FILES,
    )
    assert not offenders, f"the V6 kernel depends on none of these: {offenders}"


def test_ipc_access_stays_out_of_protocol_core_and_domain_logic():
    """`ipc.*` is an adapter concern, and no adapter exists yet (MJ-006)."""
    offenders = layer_offenders(
        _packaged_bodies(), IPC_SYMBOLS, adapters=IPC_ADAPTER_FILES,
    )
    assert not offenders, (
        "core, protocol, dispatcher, lifecycle and read-only operations make no "
        f"IPC call; the module requests no privilege: {offenders}"
    )


def test_no_transport_or_platform_adapter_is_declared_yet():
    """The registries are evidence. An empty one is a claim, not an omission."""
    assert TRANSPORT_ADAPTER_FILES == ()
    assert IPC_ADAPTER_FILES == ()


def test_the_layer_gate_admits_a_declared_adapter_without_weakening_the_core():
    """Layer-aware, asserted on synthetic sources so it cannot pass vacuously.

    One symbol is a violation in the kernel and the adapter's whole reason to
    exist. A gate that could not tell those apart would have to be deleted or
    ignored the day a transport arrives, and both outcomes lose the boundary
    the gate was protecting.
    """
    bodies = {
        "muejeje_pts/script-engine/core.js": "var x = new XMLHttpRequest();",
        "muejeje_pts/script-engine/http_adapter.js": "var y = new XMLHttpRequest();",
    }
    declared = ("muejeje_pts/script-engine/http_adapter.js",)

    assert layer_offenders(bodies, TRANSPORT_SYMBOLS, adapters=declared) == [
        "muejeje_pts/script-engine/core.js: XMLHttpRequest"
    ]
    assert len(layer_offenders(bodies, TRANSPORT_SYMBOLS, adapters=())) == 2


def test_owned_sources_hardcode_no_endpoint_address():
    offenders = [
        f"{path}: {found.group(0)}"
        for path, body in sorted(_packaged_bodies().items())
        for found in [ADDRESS_LITERAL.search(body)]
        if found is not None
    ]
    assert not offenders, (
        f"the kernel is transport-agnostic; an endpoint is a consumer's: {offenders}"
    )


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
