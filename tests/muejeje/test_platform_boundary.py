"""What the platform-call boundary refuses, and what it hands back.

`060_platform_adapter.js` makes every platform call this artifact makes, and a call
is an interface member (MJ-031). This module drives the boundary itself, with
synthetic receivers, because the adapters above it are all well-behaved — and a
refusal no caller ever triggers is a refusal nobody has seen work.

Two families of outcome, kept apart on purpose (MJ-022, MJ-031):

* **Our defects.** A member outside the allowlist, a member of one interface
  asked of an object that is another, the wrong number of arguments, a receiver
  the boundary never handed out. Each is refused before anything is touched,
  and refused as a plain error — never as a `PLATFORM_*` reading, because
  nothing about Packet Tracer was observed.
* **Platform readings.** A member the object does not offer, a call that does
  not return, an answer that is not the object the reference documents, and a
  member that handed over nothing where an object was needed next.

**A name never inherits another interface's admission.** `getRootModule` is
admitted on `DeviceDescriptor`, where it hands over a descriptor; on `Device` it
hands over installed hardware, and it is not admitted there. The same spelling
on a different receiver is a different call, and this is where that is enforced
rather than assumed. Each synthetic receiver below *offers* the bare name, so
only the qualification can be what refuses it.

Everything here runs under Node and establishes what our boundary does, and
nothing about `9.0.1.0858` (MJ-015).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.measure import js_code_only
from tests.muejeje.support import SCRIPT_ENGINE

BOUNDARY = "060_platform_adapter.js"
# What decides which interface a platform object is. Only the boundary may name
# either, or an adapter could assert a receiver's interface instead of the
# boundary deriving it from the member that produced the object.
MARKING_SYMBOLS = ("MUEJEJE_PLATFORM_HANDLE", "muejejeAdapterHandle")

IDENTIFY = json.dumps({
    "v": 6, "operation_rid": "rid-boundary", "op": "runtime.identify", "args": {},
})
# A receiver that offers the bare names it is given and records every touch,
# and a way to run one boundary call and keep whatever it threw.
PROBE = "\n".join([
    "function receiverOf(platformInterface, members) {",
    "  var touched = [];",
    "  var object = {};",
    "  members.forEach(function (name) {",
    "    object[name] = function () { touched.push(name); return 'answered'; };",
    "  });",
    "  return {handle: muejejeAdapterHandle(platformInterface, object),",
    "          object: object, touched: touched};",
    "}",
    "function attempt(call) {",
    "  try { return {answer: call()}; }",
    "  catch (thrown) { return {refused: String(thrown)}; }",
    "}",
])

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _probe(expression: str) -> dict:
    return dispatch_v6(IDENTIFY, prelude=PROBE, report=expression)


def _call_on(receiver: str, member: str) -> dict:
    """Ask `member` of a receiver marked `receiver` that offers its bare name."""
    bare = member.split(".")[1]
    return _probe(
        "(function () {"
        f" var r = receiverOf({json.dumps(receiver)}, [{json.dumps(bare)}]);"
        " var outcome = attempt(function () {"
        f"   return muejejeAdapterCall(r.handle, {json.dumps(member)}); }});"
        " return {outcome: outcome, touched: r.touched};"
        " }())"
    )


def test_only_the_boundary_decides_which_interface_a_platform_object_is():
    """An adapter that could mark an object could claim any receiver's interface."""
    owners = sorted({
        path.name for path in SCRIPT_ENGINE.glob("*.js")
        for symbol in MARKING_SYMBOLS
        if symbol in js_code_only(path.read_text(encoding="utf-8"))
    })

    assert owners == [BOUNDARY], owners


@requires_node
@pytest.mark.parametrize(("receiver", "member"), [
    ("Device", "Device.getModel"),
    ("DeviceDescriptor", "DeviceDescriptor.getType"),
])
def test_a_member_asked_of_its_own_interface_is_answered(receiver: str, member: str):
    """The positive control: the refusals below are not a boundary refusing all."""
    assert _call_on(receiver, member) == {
        "outcome": {"answer": "answered"}, "touched": [member.split(".")[1]],
    }


@requires_node
@pytest.mark.parametrize(("receiver", "member"), [
    ("Device", "DeviceDescriptor.getModel"),
    ("DeviceDescriptor", "Device.getType"),
    ("ModuleDescriptor", "DeviceDescriptor.getType"),
    ("Network", "DeviceFactory.getAvailableDeviceCount"),
    ("Port", "Device.getName"),
    ("Device", "Port.getName"),
])
def test_a_member_admitted_on_one_interface_is_refused_on_another(
    receiver: str, member: str,
):
    """Admitted, and still refused: asked of an object that is not its interface."""
    observed = _call_on(receiver, member)

    assert observed["touched"] == []
    assert "does not declare it" in observed["outcome"]["refused"]


@requires_node
@pytest.mark.parametrize(("receiver", "member"), [
    ("Device", "Device.getRootModule"),
    ("Device", "Device.getDescriptor"),
    ("DeviceDescriptor", "DeviceDescriptor.setModel"),
])
def test_a_member_nobody_admitted_is_refused_whatever_else_shares_its_name(
    receiver: str, member: str,
):
    """`Device.getRootModule` is documented, and `DeviceDescriptor`'s is admitted.

    Neither fact admits it: on `Device` it hands over installed hardware, a
    different subject with its own evidence (MJ-014). `Device.getDescriptor`
    is documented and deliberately absent, and a mutator is absent by rule.
    """
    observed = _call_on(receiver, member)

    assert observed["touched"] == []
    assert "outside the read-only boundary" in observed["outcome"]["refused"]


@requires_node
@pytest.mark.parametrize("call", [
    "muejejeAdapterCall(r.handle, 'Network.getDeviceAt')",
    "muejejeAdapterCallWith(r.handle, 'Network.getDeviceCount', 0)",
])
def test_a_call_with_the_wrong_number_of_arguments_is_refused(call: str):
    """The documented arity decides the call shape, not whoever wrote the site."""
    observed = _probe(
        "(function () {"
        " var r = receiverOf('Network', ['getDeviceAt', 'getDeviceCount']);"
        f" var outcome = attempt(function () {{ return {call}; }});"
        " return {outcome: outcome, touched: r.touched};"
        " }())"
    )

    assert observed["touched"] == []
    assert "wrong number of arguments" in observed["outcome"]["refused"]


@requires_node
def test_only_an_object_the_boundary_handed_out_may_be_called():
    """An unmarked receiver, or one marked by somebody else, is not a platform one."""
    observed = _probe(
        "(function () {"
        " var r = receiverOf('Device', ['getModel']);"
        " var forged = {mark: {}, platform_interface: 'Device',"
        "   platform_object: r.object};"
        " return {"
        "  raw: attempt(function () {"
        "    return muejejeAdapterCall(r.object, 'Device.getModel'); }),"
        "  forged: attempt(function () {"
        "    return muejejeAdapterCall(forged, 'Device.getModel'); }),"
        "  touched: r.touched};"
        " }())"
    )

    assert observed["touched"] == []
    for case in ("raw", "forged"):
        assert "did not hand out" in observed[case]["refused"], case


@requires_node
def test_an_object_is_handed_over_as_the_interface_its_member_documents():
    """The next receiver's interface comes from the entry, never from the object."""
    observed = _probe(
        "(function () {"
        " var network = {getDeviceCount: function () { return 3; },"
        "   getName: function () { return 'not a device'; }};"
        " var root = muejejeAdapterHandle('IPC', {network: function () {"
        "   return network; }});"
        " var handed = muejejeAdapterCall(root, 'IPC.network');"
        " return {"
        "  platform_interface: handed.platform_interface,"
        "  count: attempt(function () {"
        "    return muejejeAdapterCall(handed, 'Network.getDeviceCount'); }),"
        "  borrowed: attempt(function () {"
        "    return muejejeAdapterCall(handed, 'Device.getName'); })};"
        " }())"
    )

    assert observed["platform_interface"] == "Network"
    assert observed["count"] == {"answer": 3}
    assert "does not declare it" in observed["borrowed"]["refused"]


@requires_node
def test_the_platform_object_itself_is_marked_as_ipc():
    marked = dispatch_v6(
        IDENTIFY, prelude="var ipc = {};",
        report="muejejeAdapterPlatform().platform_interface",
    )

    assert marked == "IPC"


@requires_node
@pytest.mark.parametrize(("answer", "expected"), [
    ("7", {"refused": "PLATFORM_ANSWER_UNUSABLE"}),
    ("'a string'", {"refused": "PLATFORM_ANSWER_UNUSABLE"}),
    ("null", {"answer": None}),
    ("undefined", {"answer": None}),
])
def test_an_answer_that_is_not_the_documented_object_cannot_be_attributed(
    answer: str, expected: dict,
):
    """Nothing handed over is an answer; something else in its place is not."""
    observed = _probe(
        "attempt(function () { return muejejeAdapterCall("
        f" muejejeAdapterHandle('IPC', {{network: function () {{ return {answer}; }}}}),"
        " 'IPC.network'); })"
    )

    assert observed == expected


@requires_node
def test_a_value_member_hands_back_whatever_came_for_the_validators_to_judge():
    observed = _probe(
        "attempt(function () { return muejejeAdapterCall(muejejeAdapterHandle("
        " 'Network', {getDeviceCount: function () { return 'many'; }}),"
        " 'Network.getDeviceCount'); })"
    )

    assert observed == {"answer": "many"}


@requires_node
def test_the_readings_the_boundary_itself_can_report_stay_distinct():
    """Absent, failed, unusable: three observations, three next steps."""
    observed = _probe(
        "({absent: attempt(function () { return muejejeAdapterCall("
        "   muejejeAdapterHandle('Device', {}), 'Device.getType'); }),"
        " failed: attempt(function () { return muejejeAdapterCall("
        "   muejejeAdapterHandle('Device', {getType: function () {"
        "     throw new Error('refused inside the platform'); }}),"
        "   'Device.getType'); }),"
        " nothing: attempt(function () {"
        "   return muejejeAdapterCall(null, 'HardwareFactory.devices'); }),"
        " scalar: attempt(function () { return muejejeAdapterCall("
        "   muejejeAdapterHandle('IPC', 5), 'IPC.network'); })})"
    )

    assert observed == {
        "absent": {"refused": "PLATFORM_MEMBER_ABSENT"},
        "failed": {"refused": "PLATFORM_CALL_FAILED"},
        "nothing": {"refused": "PLATFORM_ANSWER_UNUSABLE"},
        "scalar": {"refused": "PLATFORM_ANSWER_UNUSABLE"},
    }
