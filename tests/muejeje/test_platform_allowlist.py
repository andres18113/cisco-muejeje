"""What this artifact may call on Packet Tracer, and what it actually called.

The read-only allowlist in `platform_adapter.js` is the whole of what this
artifact may ask the platform for, one entry per interface member. This module
holds it to three things: every entry is one this repository can cite, every
entry is one an adapter's source actually spells out, and every entry is one an
operation actually reaches when it runs — an entry nothing calls is a permission
granted for nothing, and a citation beside it that has stopped describing the
artifact.

**An entry is an interface member, not a name** (MJ-031). The citation list here
is written `Interface.member`, the call sites are read for the same spelling,
and the stub logs the interface each call landed on — so `Device.getModel` and
`DeviceDescriptor.getModel` are two entries, and reaching one never counts for
the other. What Cisco's installed pages say about each entry is
`test_platform_reference`.

**A list, not a list of forbidden verbs.** A blacklist admits every name nobody
thought to forbid, and once the member name is data it cannot see the call at
all. The mutating-verb pattern stays as a second, cheaper line of defence over
the allowlist itself.

**What was written and what ran are different halves.** The call sites show the
first; the recorded call log shows the second, per operation and as a union,
which is the half a reader cannot check by eye. What the boundary refuses when a
call does not match its entry is `test_platform_boundary`, and who may call at
all is `test_platform_adapter` (MJ-018, MJ-020). Nothing in any of them has
reached `9.0.1.0858` (MJ-015, MJ-031).
"""

from __future__ import annotations

import json
import re

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.measure import js_code_only
from tests.muejeje.platform_stub import (
    ACCESS_POINT_ROOT,
    IDENTITY_DEVICES,
    platform_stub,
)
from tests.muejeje.support import REPO_ROOT, SCRIPT_ENGINE
from tests.muejeje.test_platform_declarations import (
    IPC_ADAPTER_FILES,
    PLATFORM_ADAPTER_FILES,
)

BOUNDARY = "platform_adapter.js"

# Every interface member the boundary may admit, as Cisco's installed IpcAPI
# reference for 9.0.1.0858 documents it. An undocumented call is a guess, and
# Packet Tracer answers a guess with a bare `Invalid arguments for IPC call
# "X"` that says nothing about why (`AGENTS.md` rule 6).
DOCUMENTED_CALLS = {
    "IPC.hardwareFactory", "IPC.network",
    "HardwareFactory.devices",
    "DeviceFactory.getAvailableDeviceCount", "DeviceFactory.getAvailableDeviceAt",
    "DeviceDescriptor.getModel", "DeviceDescriptor.getType",
    "DeviceDescriptor.isModelSupported", "DeviceDescriptor.isModuleTypeSupported",
    "DeviceDescriptor.getSupportedModuleTypeCount",
    "DeviceDescriptor.getSupportedModuleTypeAt", "DeviceDescriptor.getRootModule",
    "ModuleDescriptor.getModel", "ModuleDescriptor.getType",
    "ModuleDescriptor.isHotSwappable", "ModuleDescriptor.getSlotCount",
    "ModuleDescriptor.getSlotTypeAt", "ModuleDescriptor.getModuleCount",
    "ModuleDescriptor.getModuleAt",
    "Network.getDeviceCount", "Network.getDeviceAt",
    "Device.getName", "Device.getModel", "Device.getType",
}
# Which operation exercises which part of that list. No single call reaches all
# of it, so the log is compared per operation and as a union: an entry nobody
# calls would otherwise sit on the allowlist unnoticed.
CALL_DRIVERS = (
    "platform.device_descriptors", "platform.module_descriptors",
    "platform.module_type_support", "network.device_inventory",
    "network.device_identity",
)
# An operation that requires an argument answers nothing without it.
REQUIRED_ARGS = {
    "network.device_identity": {"workspace_index": 0},
    "platform.module_descriptors": {"factory_index": 0},
    "platform.module_type_support": {"factory_index": 0, "module_type": 6},
}

# An entry of the read-only allowlist, as the boundary declares it.
ALLOWLIST_ENTRY = re.compile(r'"([A-Za-z]+\.[A-Za-z]+)":\s*\{')
# Every documented mutator on these interfaces begins with one of these verbs:
# `addSupportedModuleType`, `setModelSupportedFlag`, `removeModuleAt`, `create`.
MUTATING_NAME = re.compile(r"^(?:set|add|remove|create|delete|clear)[A-Z]")
# A call into the boundary, and the member it spells out.
CALL_SITE = re.compile(r"\bmuejejeAdapterCall(?:With)?\s*\(")
QUALIFIED_MEMBER = re.compile(r'"([A-Z][A-Za-z]*\.[a-z][A-Za-z]*)"')

# Three models, the first of them carrying a chassis, so one stub drives every
# factory operation and the whole factory half of the allowlist is reachable.
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


def _stub() -> str:
    """The factory above, and a workspace whose devices answer identity too."""
    return platform_stub(THREE_MODELS, devices=IDENTITY_DEVICES)


def admitted_calls() -> set[str]:
    """The allowlist, read from the boundary that declares it."""
    body = (SCRIPT_ENGINE / BOUNDARY).read_text(encoding="utf-8")
    declared = body.split("MUEJEJE_PLATFORM_READ_ONLY_CALLS = {")[1]
    return set(ALLOWLIST_ENTRY.findall(declared.split("};")[0]))


def test_the_allowlist_is_exactly_what_this_repository_can_cite():
    """Equality, because either half alone is a different rule: a subset check
    admits an uncited call, a superset check lets a cited one disappear."""
    assert admitted_calls() == DOCUMENTED_CALLS


def test_no_admitted_call_is_shaped_like_a_mutation():
    """The verb pattern, over the allowlist rather than the source: a second
    line of defence, asserted both ways so it cannot stop matching."""
    assert [
        entry for entry in admitted_calls()
        if MUTATING_NAME.search(entry.split(".")[1])
    ] == []
    assert MUTATING_NAME.search("addSupportedModuleType") is not None
    assert MUTATING_NAME.search("getSupportedModuleTypeCount") is None


def test_every_call_site_spells_the_interface_member_it_means():
    """Written, not only run: each call into the boundary names one member.

    Counted per file, so a call whose member is not a literal — a variable, a
    computed string — shows up as a call site with no spelled member rather
    than as a call nothing can read. The union has to be the whole allowlist,
    so an entry no source spells out is noticed without running anything.
    """
    named: set[str] = set()
    for logical in PLATFORM_ADAPTER_FILES:
        if logical in IPC_ADAPTER_FILES:
            continue
        code = js_code_only((REPO_ROOT / logical).read_text(encoding="utf-8"))
        members = QUALIFIED_MEMBER.findall(code)
        assert len(members) == len(CALL_SITE.findall(code)), logical
        named |= set(members)

    assert named == admitted_calls()


def test_the_call_site_reader_tells_a_spelled_member_from_a_computed_one():
    """Guards the gate above from passing because it matched nothing."""
    spelled = 'var n = muejejeAdapterCall(platform, "IPC.network");'
    computed = "var n = muejejeAdapterCall(platform, member);"

    assert QUALIFIED_MEMBER.findall(spelled) == ["IPC.network"]
    assert len(CALL_SITE.findall(computed)) == 1
    assert QUALIFIED_MEMBER.findall(computed) == []


@requires_node
@pytest.mark.parametrize("op", CALL_DRIVERS)
def test_an_operation_asks_for_nothing_this_repository_cannot_cite(op: str):
    """A grep shows what is written; the log shows what ran."""
    called = dispatch_v6(
        _request(op), prelude=_stub(),
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
            _request(op), prelude=_stub(),
            report="{done: mcpDispatchV6(REQUEST) !== null, calls: CALLS}",
        )["calls"])

    assert reached == DOCUMENTED_CALLS


@requires_node
def test_the_log_keeps_one_member_name_on_two_interfaces_apart():
    """`getModel` is two entries, and reaching one never counts for the other.

    Descriptor discovery reads a factory descriptor's model; the identity
    reading reads a workspace device's. A log of bare names would record one
    word for both, and either operation would then appear to have exercised the
    other's entry.
    """
    logs = {
        op: set(dispatch_v6(
            _request(op), prelude=_stub(),
            report="{done: mcpDispatchV6(REQUEST) !== null, calls: CALLS}",
        )["calls"])
        for op in ("platform.device_descriptors", "network.device_identity")
    }

    assert "DeviceDescriptor.getModel" in logs["platform.device_descriptors"]
    assert "Device.getModel" not in logs["platform.device_descriptors"]
    assert "Device.getModel" in logs["network.device_identity"]
    assert "DeviceDescriptor.getModel" not in logs["network.device_identity"]


@requires_node
def test_the_call_log_would_notice_an_undocumented_call():
    """Guards the gates above from passing because the log recorded nothing."""
    called = dispatch_v6(
        _request(),
        prelude=_stub() + "\nlog('Device.getUndocumentedThing');",
        report="CALLS",
    )

    assert set(called) - DOCUMENTED_CALLS == {"Device.getUndocumentedThing"}
