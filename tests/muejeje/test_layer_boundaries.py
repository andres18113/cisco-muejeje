"""Layer boundaries in the owned artifact: PTBuilder, transport and the platform.

Three rules, one shape. The V6 kernel inherits no PTBuilder global (MJ-013),
names no transport (MJ-026), and reaches the Cisco platform only from a
*declared* adapter (MJ-006, MJ-019).

**Each of these has to survive the runtime growing**, which is what most of
this module is about. A gate that forbade `addDevice` as a substring would
also forbid Cisco's documented `ipc.network().addDevice(...)`, and would be
deleted the first time an adapter needed it. A gate with no notion of an
adapter would be deleted the first time one arrived. So the PTBuilder rule
separates a global from a member of the same name, the layer rules name their
adapters by path, and every declaration is itself checked — an exemption that
could be pointed at `core.js` is a switch for turning these gates off
(MJ-021).
"""

from __future__ import annotations

import re

import pytest

from tests.muejeje.measure import (
    global_pattern,
    layer_offenders,
    literal_pattern,
    packaged_text_bodies,
)
from tests.muejeje.support import REPO_ROOT, repo_manifest

# The six globals PTBuilder supplies today. Inheriting any of them is what the
# owned source root exists to avoid (MJ-013).
#
# They are matched as *globals*: not preceded by a dot, so a bare `addDevice(…)`
# is an offender and Cisco's own `ipc.network().addDevice(…)` is not. Four of
# these six names are also members of documented Cisco interfaces, so a
# substring rule would forbid the official API — and would have to be deleted
# the first time a platform adapter needed it, taking the PTBuilder boundary
# with it.
PTBUILDER_GLOBALS = (
    "htmlWindow", "runCode", "configureIosDevice", "allModuleTypes",
    "addDevice", "addLink",
)

# Layers outside the V6 kernel. Naming one is how a dependency on it starts.
TRANSPORT_SYMBOLS = (
    "webview", "XMLHttpRequest", "systemFileManager", "localStorage",
    "fileBridge", "file_bridge", "bridge_token", "http://", "https://",
)

# Declared adapters, by path. Only a declared adapter may name the layer it
# adapts; every other packaged source is kernel and may not. Declaring one is
# an edit to this gate, which is the point: an adapter arrives visibly, and
# every declaration is checked against the rules below.
TRANSPORT_ADAPTER_FILES: tuple[str, ...] = ()
IPC_ADAPTER_FILES: tuple[str, ...] = ()

# What a declared adapter must be. Without these, the layer gate could be
# silenced by declaring `core.js` an adapter, which is the one way a boundary
# like this fails without anybody noticing.
ADAPTER_SUFFIX = "_adapter.js"
# An adapter adapts. It does not answer a request, shape an envelope, or decide
# what is admitted; those belong to the kernel it is called from (MJ-019).
ADAPTER_MAY_NOT_NAME = (
    "mcpDispatchV6", "muejejeV6Ok", "muejejeV6Fail", "muejejeV6OperationTable",
    "MUEJEJE_V6_ERRORS", "MUEJEJE_CORE",
)

DECLARED_ADAPTERS = sorted(set(TRANSPORT_ADAPTER_FILES) | set(IPC_ADAPTER_FILES))


def ptbuilder_patterns() -> list[tuple[str, re.Pattern[str]]]:
    return [global_pattern(name) for name in PTBUILDER_GLOBALS]


def transport_patterns() -> list[tuple[str, re.Pattern[str]]]:
    return [literal_pattern(symbol) for symbol in TRANSPORT_SYMBOLS]


def ipc_patterns() -> list[tuple[str, re.Pattern[str]]]:
    """`ipc` reached at all, however it is spelled.

    `ipc.` alone would miss `var platform = ipc;` followed by
    `platform.network()`. The identifier is matched case-sensitively, because
    the kernel's own comments discuss "IPC" in prose and a boundary gate that
    fires on an explanation of the boundary teaches people to stop explaining.
    """
    return [global_pattern("ipc")]


def adapter_declaration_error(logical: str, artifact_inputs: set[str]) -> str | None:
    """Why `logical` may not be declared an adapter, or None.

    A declared adapter is an exemption from the layer gates, so the
    declaration itself is checked: it has to name a file that ships, and the
    name has to say what it is. Otherwise the exemption is a way to turn the
    gate off.
    """
    if not logical.endswith(ADAPTER_SUFFIX):
        return f"an adapter's name must end with {ADAPTER_SUFFIX}: {logical}"
    if logical not in artifact_inputs:
        return f"a declared adapter must be a declared artifact input: {logical}"
    if not (REPO_ROOT / logical).is_file():
        return f"a declared adapter must exist: {logical}"
    return None


def _packaged_bodies() -> dict[str, str]:
    return packaged_text_bodies()


# ---------------------------------------------------------------------------
# PTBuilder: a global is inherited, a documented member is adapted to.
# ---------------------------------------------------------------------------

def test_owned_sources_inherit_no_ptbuilder_global():
    offenders = layer_offenders(_packaged_bodies(), ptbuilder_patterns(), adapters=())
    assert not offenders, f"owned sources must not depend on PTBuilder: {offenders}"


def test_the_ptbuilder_gate_tells_a_global_from_an_official_member():
    """One spelling, two dependencies. Asserted in both directions.

    PTBuilder supplies a global `addDevice(...)`; Cisco documents `addDevice`
    as a member reached through `ipc`. The gate has to keep the first out
    while leaving the second available to a declared adapter, because a rule
    that forbids the official API is one that gets deleted — and the PTBuilder
    boundary would go with it (MJ-013).

    A declared adapter is *not* exempt here: a bare global is PTBuilder's
    whatever file names it, so this gate takes no adapter list at all.
    """
    ptbuilder = "var d = addDevice('Router', 0, 0); runCode(src);"
    official = "var d = ipc.network().addDevice('Router', 0, 0);"

    assert sorted(layer_offenders(
        {"kernel.js": ptbuilder}, ptbuilder_patterns(), adapters=(),
    )) == ["kernel.js: addDevice", "kernel.js: runCode"]
    assert layer_offenders(
        {"platform_adapter.js": official}, ptbuilder_patterns(), adapters=(),
    ) == []


# ---------------------------------------------------------------------------
# Layers: the kernel stays independent, and an adapter stays possible.
# ---------------------------------------------------------------------------

def test_the_kernel_reaches_for_no_transport_layer():
    """WebView, HTTP, the File Bridge and browser storage are outside it."""
    offenders = layer_offenders(
        _packaged_bodies(), transport_patterns(), adapters=TRANSPORT_ADAPTER_FILES,
    )
    assert not offenders, f"the V6 kernel depends on none of these: {offenders}"


def test_ipc_access_stays_out_of_everything_but_a_declared_adapter():
    """`ipc` is an adapter concern, wherever it is reached from (MJ-006)."""
    offenders = layer_offenders(
        _packaged_bodies(), ipc_patterns(), adapters=IPC_ADAPTER_FILES,
    )
    assert not offenders, (
        "core, protocol, admission, dispatch, lifecycle and operations make no "
        f"platform call; only a declared adapter may: {offenders}"
    )


def test_the_ipc_gate_is_not_satisfied_by_renaming_the_object():
    """`ipc.` alone would miss an alias, which is a rename, not a boundary.

    Case-sensitively, so the kernel's own comments can go on explaining that
    it makes no IPC call. A gate that fired on the explanation of itself
    teaches people to delete the explanation.
    """
    aliased = "var platform = ipc; var n = platform.network();"
    prose = "/* No Cisco IPC call is made here, and the module needs no privilege. */"

    assert layer_offenders({"core.js": aliased}, ipc_patterns(), adapters=()) == [
        "core.js: ipc"
    ]
    assert layer_offenders({"core.js": prose}, ipc_patterns(), adapters=()) == []


@pytest.mark.parametrize(
    "logical", sorted(set(TRANSPORT_ADAPTER_FILES) | set(IPC_ADAPTER_FILES)),
)
def test_every_declared_adapter_is_a_file_that_ships_and_says_so(logical: str):
    inputs = set(repo_manifest()["artifact_inputs"])
    assert adapter_declaration_error(logical, inputs) is None


@pytest.mark.parametrize(
    "logical", sorted(set(TRANSPORT_ADAPTER_FILES) | set(IPC_ADAPTER_FILES)),
)
def test_a_declared_adapter_adapts_and_does_not_answer(logical: str):
    body = (REPO_ROOT / logical).read_text(encoding="utf-8")
    named = [symbol for symbol in ADAPTER_MAY_NOT_NAME if symbol in body]
    assert named == [], (
        f"{logical} is an adapter; dispatching, shaping an envelope and "
        f"reading core belong to the kernel that calls it: {named}"
    )


def test_the_declared_adapter_registries_are_what_this_artifact_ships():
    """A registry is evidence, and an empty one is a claim, not an omission.

    Adding an entry is an edit to this assertion, which is what makes an
    adapter arrive visibly rather than by a file quietly matching a naming
    convention.
    """
    assert TRANSPORT_ADAPTER_FILES == ()
    assert IPC_ADAPTER_FILES == ()


def test_the_adapter_declaration_rule_refuses_a_kernel_file():
    """Asserted in every direction, so the exemption cannot become a switch.

    Declaring `core.js` an adapter would silence the layer gates for the one
    file they exist to protect, so the declaration is checked rather than
    trusted. Each reason is exercised here because the registries themselves
    are empty, and a check nobody has run is a check nobody can rely on.
    """
    shipped = "muejeje_pts/script-engine/core.js"
    missing = "muejeje_pts/script-engine/absent_adapter.js"
    inputs = {shipped, missing}

    assert "must end with" in (adapter_declaration_error(shipped, inputs) or "")
    assert "declared artifact input" in (
        adapter_declaration_error(missing, {shipped}) or ""
    )
    assert "must exist" in (adapter_declaration_error(missing, inputs) or "")
    assert not (REPO_ROOT / missing).exists(), "the missing-file case needs a gap"


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

    assert layer_offenders(bodies, transport_patterns(), adapters=declared) == [
        "muejeje_pts/script-engine/core.js: XMLHttpRequest"
    ]
    assert len(layer_offenders(bodies, transport_patterns(), adapters=())) == 2
