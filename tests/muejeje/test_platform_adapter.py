"""The files that reach Packet Tracer, and what they are allowed to be.

`platform_adapter.js` is the declared platform-call boundary (MJ-006, MJ-019):
the only packaged source that names `ipc`, and the only one that invokes a
platform member at all. The subject adapters beside it are handed a platform
object and call it by name *through* that boundary. This module gates what
those permissions cost: no mutation, no kernel state, no envelope, no dispatch,
no Cisco enum mirror, and no call this repository cannot cite.

**The read-only proof is an allowlist, not a list of forbidden verbs.** A
blacklist of mutating prefixes admits every name nobody thought to forbid, and
it cannot see a call at all once the member name is data. So the boundary
carries the set of calls this artifact may make, the gates here hold that set
to Cisco's documented getters, and no adapter names a platform member at a call
site — which is checked positively, by reading every member call each adapter
makes. The verb pattern stays as a second, cheaper line of defence over the
allowlist itself.

The half a reader cannot check by eye is what actually ran, so the recorded
call log is compared against the same set in both directions. A call with no
reference behind it fails here rather than on a target as a bare `Invalid
arguments for IPC call "X"` (`AGENTS.md` rule 6).

What an adapter *reports* is `test_platform_readings`; the V6 surface of the
operation in front of it is `test_platform_descriptors`. Nothing in any of the
three has reached `9.0.1.0858`, so the capability's live state is
`PENDING_TARGET` (MJ-015, MJ-031).
"""

from __future__ import annotations

import json
import re

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available, platform_stub
from tests.muejeje.measure import js_code_only
from tests.muejeje.support import SCRIPT_ENGINE
from tests.muejeje.test_layer_boundaries import (
    IPC_ADAPTER_FILES,
    PLATFORM_ADAPTER_FILES,
)

BOUNDARY = "platform_adapter.js"
OPERATION = "platform.device_descriptors"

# Every platform method the boundary may admit, as Cisco's installed IpcAPI
# reference for 9.0.1.0858 names it. An undocumented call is a guess, and
# Packet Tracer answers a guess with a bare `Invalid arguments for IPC call
# "X"` that says nothing about why (`AGENTS.md` rule 6).
DOCUMENTED_CALLS = {
    "hardwareFactory", "devices",
    "getAvailableDeviceCount", "getAvailableDeviceAt",
    "getModel", "getType", "isModelSupported",
    "getSupportedModuleTypeCount", "getSupportedModuleTypeAt",
}

# A member call in JavaScript source, by the name it invokes.
MEMBER_CALL = re.compile(r"\.\s*([A-Za-z_$][A-Za-z0-9_$]*)\s*\(")
# The member calls an adapter is allowed to make in its own code: JavaScript's
# own, and nothing else. Every platform call goes through `muejejeAdapterCall`,
# which takes the member name as data, so a platform getter written at a call
# site is an adapter reaching past its own boundary.
LANGUAGE_MEMBER_CALLS = {"call", "min", "push"}

# The read-only allowlist, as the boundary declares it.
ALLOWLIST_ENTRY = re.compile(r"([A-Za-z_$][A-Za-z0-9_$]*):\s*true")
# Every documented mutator on these interfaces begins with one of these verbs:
# `addSupportedModuleType`, `setModelSupportedFlag`, `removeModuleAt`,
# `create`. Second line of defence, over the allowlist rather than the source.
MUTATING_NAME = re.compile(r"^(?:set|add|remove|create|delete|clear)[A-Z]")

THREE_MODELS = (
    "[{model: '2960-24TT', type: 1, supported: true, module_types: [18]},"
    " {model: '', type: 7, supported: false, module_types: [6, 18]},"
    " {model: '3650-24PS', type: 16, supported: true, module_types: [4, 18]}]"
)

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(**args) -> str:
    return json.dumps({
        "v": 6, "operation_rid": "rid-adapter", "op": OPERATION, "args": args,
    })


def _body(name: str) -> str:
    return (SCRIPT_ENGINE / name).read_text(encoding="utf-8")


def _adapter_names() -> list[str]:
    return [logical.rsplit("/", 1)[-1] for logical in PLATFORM_ADAPTER_FILES]


def platform_members_called(body: str) -> set[str]:
    """Member calls `body` makes that are not JavaScript's own.

    The positive form of the read-only rule: an adapter's own code names no
    platform member, so anything left over here is a call that never passed
    the boundary's allowlist.
    """
    return set(MEMBER_CALL.findall(js_code_only(body))) - LANGUAGE_MEMBER_CALLS


def admitted_calls() -> set[str]:
    """The allowlist, read from the boundary that declares it."""
    declared = _body(BOUNDARY).split("MUEJEJE_PLATFORM_READ_ONLY_CALLS = {")[1]
    return set(ALLOWLIST_ENTRY.findall(declared.split("};")[0]))


# ---------------------------------------------------------------------------
# Structural: one boundary, and adapters that go through it.
# ---------------------------------------------------------------------------

def test_the_boundary_is_the_only_file_that_names_the_platform():
    owners = [
        path.name for path in sorted(SCRIPT_ENGINE.glob("*.js"))
        if re.search(r"(?<![.\w$])ipc\b", js_code_only(path.read_text(encoding="utf-8")))
    ]
    assert owners == [BOUNDARY], owners
    assert IPC_ADAPTER_FILES == (f"muejeje_pts/script-engine/{BOUNDARY}",)


def test_only_a_declared_adapter_reaches_the_boundary():
    """The kernel calls an adapter; an adapter calls the platform (MJ-019).

    A kernel file that called `muejejeAdapterCall` itself would be making a
    platform call from outside every gate this module holds, so the set of
    files that name it is asserted rather than assumed.
    """
    callers = [
        path.name for path in sorted(SCRIPT_ENGINE.glob("*.js"))
        if "muejejeAdapterCall" in js_code_only(path.read_text(encoding="utf-8"))
    ]
    assert callers == sorted(_adapter_names()), callers


@pytest.mark.parametrize("name", sorted(_adapter_names()))
def test_no_adapter_names_a_platform_member_at_a_call_site(name: str):
    """Positive, and asserted in both directions on synthetic sources.

    A gate that matched nothing would be indistinguishable from a source that
    calls nothing, so the reader is exercised on a call that should trip it and
    on the language's own members, which should not.
    """
    assert platform_members_called(_body(name)) == set()

    assert platform_members_called("var m = descriptor.getModel();") == {"getModel"}
    assert platform_members_called("descriptor.addSupportedModuleType(4);") == {
        "addSupportedModuleType",
    }
    assert platform_members_called(
        "var n = Math.min(a, b); list.push(n);"
        " Object.prototype.hasOwnProperty.call(o, k);"
    ) == set()


@pytest.mark.parametrize("name", sorted(_adapter_names()))
def test_an_adapter_reads_no_kernel_state_and_answers_no_request(name: str):
    """It adapts. Shaping an answer and reading core belong to the kernel."""
    body = _body(name)
    for owned_elsewhere in (
        "MUEJEJE_CORE", "MUEJEJE_V6_ERRORS", "muejejeV6Ok", "muejejeV6Fail",
        "mcpDispatchV6", "muejejeV6OperationTable",
    ):
        assert owned_elsewhere not in body, owned_elsewhere


# ---------------------------------------------------------------------------
# Structural: the allowlist is the read-only proof.
#
# The other half of MJ-014 — that no Cisco enum *identifier* enters a packaged
# source at all — is a rule about the whole owned tree rather than about an
# adapter, and lives with the rest of those in `test_source_root`.
# ---------------------------------------------------------------------------

def test_the_allowlist_is_exactly_what_this_repository_can_cite():
    """Both directions: an uncited call fails, and a cited one stays available.

    Equality rather than containment, because either half alone is a different
    rule. A subset check would admit a call nobody can point at a reference
    for; a superset check would let a documented getter be dropped from the
    boundary while every citation still reads as current.
    """
    assert admitted_calls() == DOCUMENTED_CALLS


def test_no_admitted_call_is_shaped_like_a_mutation():
    """The verb pattern, over the allowlist rather than over the source.

    Second line of defence, and deliberately not the first: a blacklist admits
    every name nobody thought of, and cannot see a call whose member name is
    data. Asserted in both directions so it cannot quietly stop matching.
    """
    assert [name for name in admitted_calls() if MUTATING_NAME.search(name)] == []
    assert MUTATING_NAME.search("addSupportedModuleType") is not None
    assert MUTATING_NAME.search("getSupportedModuleTypeCount") is None


@pytest.mark.parametrize("name", sorted(_adapter_names()))
def test_the_only_numbers_an_adapter_carries_are_its_own_bounds(name: str):
    """A type value written down here would be a mirror by another spelling.

    Muejeje's bounds are declared in one block and are a limit on what an
    adapter will do in one call (MJ-029); `0` and `1` are structural — an index
    origin and a whole-number test. Any other literal is a number about the
    platform, and the platform is the only authority on those.
    """
    code = js_code_only(_body(name))
    if "MUEJEJE_PLATFORM_LIMITS = {" in code:
        code = code.replace(code.split("MUEJEJE_PLATFORM_LIMITS = {")[1].split("};")[0], "")
    literals = set(re.findall(r"(?<![\w.$])(\d+(?:\.\d+)?)", code)) - {"0", "1"}

    assert literals == set(), (
        f"{name} carries a number the platform should have answered: {literals}"
    )


# ---------------------------------------------------------------------------
# Executable: the boundary refuses, and only calls this repository can cite run.
# ---------------------------------------------------------------------------

@requires_node
def test_the_adapters_ask_for_nothing_this_repository_cannot_cite():
    """The call log, compared against the documented getters.

    A grep over the source shows what is written; this shows what actually
    ran, which is the half a reader cannot check by eye.
    """
    called = dispatch_v6(
        _request(),
        prelude=platform_stub(THREE_MODELS),
        report="{result: JSON.parse(mcpDispatchV6(REQUEST)).result, calls: CALLS}",
    )

    assert called["result"]["resolution"] == "OBSERVED"
    assert set(called["calls"]) == DOCUMENTED_CALLS


@requires_node
def test_the_call_log_would_notice_an_undocumented_call():
    """Guards the gate above from passing because the log recorded nothing."""
    called = dispatch_v6(
        _request(),
        prelude=platform_stub(THREE_MODELS) + "\nlog('getUndocumentedThing');",
        report="CALLS",
    )

    assert set(called) - DOCUMENTED_CALLS == {"getUndocumentedThing"}


@requires_node
def test_a_call_outside_the_allowlist_never_reaches_the_platform():
    """The boundary refuses by name, before the receiver is touched at all.

    And it refuses as a *defect*, not as a reading: asking for a call this
    artifact does not admit is our bug, and a bug that came back as
    `PLATFORM_CALL_FAILED` would be an observation about Packet Tracer that
    Packet Tracer never produced (MJ-031).
    """
    probe = "\n".join([
        "function attempt(name) {",
        "  var touched = false;",
        "  var receiver = {",
        "    setModel: function () { touched = true; return null; },",
        "    getModel: function () { touched = true; return 'read'; }",
        "  };",
        "  var answer = null;",
        "  var refused = null;",
        "  try { answer = muejejeAdapterCall(receiver, name); }",
        "  catch (thrown) { refused = String(thrown); }",
        "  return {answer: answer, refused: refused, touched: touched};",
        "}",
    ])
    observed = dispatch_v6(
        _request(), prelude=probe,
        report="{denied: attempt('setModel'), admitted: attempt('getModel')}",
    )

    assert observed["denied"]["touched"] is False
    assert observed["denied"]["refused"] is not None
    assert "PLATFORM_" not in observed["denied"]["refused"], (
        "a call this artifact may not make is a defect, not a platform reading"
    )
    assert observed["admitted"] == {
        "answer": "read", "refused": None, "touched": True,
    }
