"""What this artifact may call on Packet Tracer, and what it actually called.

The read-only allowlist in `platform_adapter.js` is the whole of what this
artifact may ask the platform for. This module holds it to two things: every
name on it is one this repository can cite in Cisco's installed IpcAPI
reference for 9.0.1.0858, and every name on it is one an operation actually
reaches — an entry nothing calls is a permission granted for nothing, and a
citation that has stopped describing the artifact.

**A list, not a list of forbidden verbs.** A blacklist admits every name nobody
thought to forbid, and once the member name is data it cannot see the call at
all. The mutating-verb pattern stays as a second, cheaper line of defence over
the allowlist itself.

**What was written and what ran are different halves.** A grep over the source
shows the first; the recorded call log shows the second, per operation and as a
union, which is the half a reader cannot check by eye. A call with no reference
behind it fails here rather than on a target as a bare `Invalid arguments for
IPC call "X"` (`AGENTS.md` rule 6).

Who may call at all — the one file that names `ipc`, and the adapters that go
through it — is `test_platform_adapter`, split from here at the line budget
(MJ-018, MJ-020). Nothing in either has reached `9.0.1.0858` (MJ-015, MJ-031).
"""

from __future__ import annotations

import json
import re

import pytest

from tests.muejeje.engine_harness import (
    ACCESS_POINT_ROOT,
    dispatch_v6,
    node_available,
    platform_stub,
)
from tests.muejeje.support import SCRIPT_ENGINE

BOUNDARY = "platform_adapter.js"

# Every platform method the boundary may admit, as Cisco's installed IpcAPI
# reference for 9.0.1.0858 names it. An undocumented call is a guess, and
# Packet Tracer answers a guess with a bare `Invalid arguments for IPC call
# "X"` that says nothing about why (`AGENTS.md` rule 6).
DOCUMENTED_CALLS = {
    "hardwareFactory", "devices",
    "getAvailableDeviceCount", "getAvailableDeviceAt",
    "getModel", "getType", "isModelSupported",
    "getSupportedModuleTypeCount", "getSupportedModuleTypeAt",
    "getRootModule", "isHotSwappable", "getSlotCount", "getSlotTypeAt",
    "getModuleCount", "getModuleAt", "isModuleTypeSupported",
    "network", "getDeviceCount", "getDeviceAt", "getName",
}
# Which operation exercises which half of that list. No single call reaches all
# of it, so the log is compared per operation and as a union: a name nobody
# calls would otherwise sit on the allowlist unnoticed.
CALL_DRIVERS = (
    "platform.device_descriptors", "platform.module_descriptors",
    "platform.module_type_support", "network.device_inventory",
)
# An operation that requires an argument answers nothing without it.
REQUIRED_ARGS = {"platform.module_type_support": {"module_type": 6}}

# The read-only allowlist, as the boundary declares it.
ALLOWLIST_ENTRY = re.compile(r"([A-Za-z_$][A-Za-z0-9_$]*):\s*true")
# Every documented mutator on these interfaces begins with one of these verbs:
# `addSupportedModuleType`, `setModelSupportedFlag`, `removeModuleAt`, `create`.
MUTATING_NAME = re.compile(r"^(?:set|add|remove|create|delete|clear)[A-Z]")

# Three models, the first of them carrying a chassis, so one stub drives both
# platform operations and the whole allowlist is reachable from it.
THREE_MODELS = (
    "[{model: '2960-24TT', type: 1, supported: true, module_types: [18],"
    f" root: {ACCESS_POINT_ROOT}}},"
    " {model: '', type: 7, supported: false, module_types: [6, 18]},"
    " {model: '3650-24PS', type: 16, supported: true, module_types: [4, 18]}]"
)

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(op: str = CALL_DRIVERS[0]) -> str:
    return json.dumps({
        "v": 6, "operation_rid": "rid-adapter", "op": op,
        "args": REQUIRED_ARGS.get(op, {}),
    })


def _body(name: str) -> str:
    return (SCRIPT_ENGINE / name).read_text(encoding="utf-8")


def admitted_calls() -> set[str]:
    """The allowlist, read from the boundary that declares it."""
    declared = _body(BOUNDARY).split("MUEJEJE_PLATFORM_READ_ONLY_CALLS = {")[1]
    return set(ALLOWLIST_ENTRY.findall(declared.split("};")[0]))


def test_the_allowlist_is_exactly_what_this_repository_can_cite():
    """Equality, because either half alone is a different rule: a subset check
    admits an uncited call, a superset check lets a cited one disappear."""
    assert admitted_calls() == DOCUMENTED_CALLS


def test_no_admitted_call_is_shaped_like_a_mutation():
    """The verb pattern, over the allowlist rather than the source: a second
    line of defence, asserted both ways so it cannot stop matching."""
    assert [name for name in admitted_calls() if MUTATING_NAME.search(name)] == []
    assert MUTATING_NAME.search("addSupportedModuleType") is not None
    assert MUTATING_NAME.search("getSupportedModuleTypeCount") is None

@requires_node
@pytest.mark.parametrize("op", CALL_DRIVERS)
def test_an_operation_asks_for_nothing_this_repository_cannot_cite(op: str):
    """A grep shows what is written; the log shows what ran."""
    called = dispatch_v6(
        _request(op),
        prelude=platform_stub(THREE_MODELS),
        report="{result: JSON.parse(mcpDispatchV6(REQUEST)).result, calls: CALLS}",
    )

    assert called["result"]["resolution"] == "OBSERVED"
    assert set(called["calls"]) <= DOCUMENTED_CALLS, (
        f"{op} called something with no reference behind it: "
        f"{sorted(set(called['calls']) - DOCUMENTED_CALLS)}"
    )


@requires_node
def test_every_admitted_call_is_one_an_operation_actually_makes():
    """An entry no operation reaches is a permission granted for nothing, and
    a citation beside it that has stopped describing the artifact."""
    reached = set()
    for op in CALL_DRIVERS:
        reached |= set(dispatch_v6(
            _request(op),
            prelude=platform_stub(THREE_MODELS),
            report="{done: mcpDispatchV6(REQUEST) !== null, calls: CALLS}",
        )["calls"])

    assert reached == DOCUMENTED_CALLS


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
    """Refused by name, before the receiver is touched — and refused as a
    *defect*, since a bug of ours wearing `PLATFORM_CALL_FAILED` would be an
    observation Packet Tracer never produced. An admitted member that is
    missing is the opposite case, and is a reading."""
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
        report=(
            "{denied: attempt('setModel'), admitted: attempt('getModel'),"
            " missing: attempt('getType')}"
        ),
    )

    assert observed["denied"]["touched"] is False
    assert observed["denied"]["refused"] is not None
    assert "PLATFORM_" not in observed["denied"]["refused"], (
        "a call this artifact may not make is a defect, not a platform reading"
    )
    assert observed["admitted"] == {
        "answer": "read", "refused": None, "touched": True,
    }
    assert observed["missing"]["refused"] == "PLATFORM_MEMBER_ABSENT", (
        "a member that is not there was never called, so nothing failed"
    )
