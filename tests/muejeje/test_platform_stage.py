"""Which `Interface.member` an unavailable reading stopped at.

A reading already says *what* happened — `PLATFORM_ABSENT`,
`PLATFORM_MEMBER_ABSENT`, `PLATFORM_CALL_FAILED`, `PLATFORM_ANSWER_UNUSABLE`.
It now also says *where*: the member it stopped at, and the argument that call
was made with. This module is why that can be relied on.

**The defect it was added for was a real one.** The first governed artifact to
reach `platform.module_descriptors` on `9.0.1.0858` answered `UNAVAILABLE` with
`PLATFORM_ANSWER_UNUSABLE` and nothing else, while the two readings either side
of it — `platform.device_descriptors` and `platform.module_type_support` — were
`OBSERVED` at the same `factory_index`. Eight interface members sit between a
`factory_index` and a finished chassis tree, every one of them can produce that
one word, and the result could not say which. The run was target evidence that
something in that chain is unreadable, and no evidence at all about where.

**So every case here pins the member exactly.** A stage that drifted one call
early or late would still look plausible in a transcript, and would send the
next run's reader to the wrong member — which is worse than the silence it
replaced. What a stage may *never* say is `test_platform_stage_scope`, split out
for the reason these splits usually happen: naming the member and bounding the
claim are two responsibilities (MJ-018, MJ-020).

Everything here runs under Node against a stub, and establishes what *our*
boundary records. It establishes nothing about what `9.0.1.0858` answers — that
is exactly what it exists to let the next run find out (MJ-015).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.platform_stub import CHASSIS_MODELS, platform_stub

MODULES = "platform.module_descriptors"
# Every operation that reads the platform, with the arguments it needs to answer
# at all. The stage is part of each one's result shape rather than one
# operation's private field, which is what `test_platform_stage_scope` drives
# this over.
PLATFORM_OPERATIONS = {
    "platform.device_descriptors": {},
    "platform.module_descriptors": {"factory_index": 0},
    "platform.module_type_support": {"factory_index": 0, "module_type": 6},
    "network.device_inventory": {},
    "network.device_identity": {"workspace_index": 0},
    "network.device_ports": {"workspace_index": 0},
    "network.link_inventory": {},
    "network.link_endpoints": {"workspace_link_index": 0},
}
STAGE_FIELDS = ("unavailable_member", "unavailable_argument")

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def request_for(op: str = MODULES, **args) -> str:
    if not args:
        args = PLATFORM_OPERATIONS[op]
    return json.dumps({
        "v": 6, "operation_rid": "rid-stage", "op": op, "args": args,
    })


def reading(prelude: str, op: str = MODULES, **args) -> dict:
    return dispatch_v6(request_for(op, **args), prelude=prelude)["result"]


def stage_of(result: dict) -> tuple:
    return (result["unavailable_member"], result["unavailable_argument"])


def _chassis(root: str) -> str:
    """One model carrying `root`, so a planted fault is the only thing in reach."""
    return (
        "[{model: 'one', type: 1, supported: true, module_types: [],"
        f" root: {root}}}]"
    )


def _root(**fields) -> str:
    """A well-formed chassis root, with the named fields replaced."""
    node = {
        "model": "'root'", "module_type": "18", "hot_swappable": "false",
        "slot_types": "[]", "modules": "[]",
    }
    node.update(fields)
    return "{" + ", ".join(f"{name}: {value}" for name, value in node.items()) + "}"


# One planted fault per member of the chassis chain, and the member each has to
# be reported at. The root's own getters run in the order the adapter reads them
# — the two slot getters first, then model, type, hot-swap, count — so each
# fixture plants exactly one fault and leaves the rest well formed.
MODULE_FAULTS = (
    ("ModuleDescriptor.getSlotCount", _root(slot_count="-1")),
    ("ModuleDescriptor.getSlotTypeAt", _root(slot_types="['6']")),
    ("ModuleDescriptor.getModel", _root(model="7")),
    ("ModuleDescriptor.getType", _root(module_type="'18'")),
    ("ModuleDescriptor.isHotSwappable", _root(hot_swappable="1")),
    ("ModuleDescriptor.getModuleCount", _root(module_count="-1")),
    ("ModuleDescriptor.getModuleAt", _root(modules="[undefined]")),
)


# ---------------------------------------------------------------------------
# The chassis chain, member by member.
# ---------------------------------------------------------------------------

@requires_node
@pytest.mark.parametrize(("member", "root"), MODULE_FAULTS, ids=[
    member for member, _ in MODULE_FAULTS
])
def test_each_member_of_the_chassis_chain_reports_itself(member: str, root: str):
    """The discrimination the `6233d86` run did not have.

    One fault, one member. Every one of these answers
    `PLATFORM_ANSWER_UNUSABLE`, which is why the reason alone could not tell
    them apart, and why the member has to be exact rather than nearby.
    """
    result = reading(platform_stub(_chassis(root)))

    assert result["unavailable_reason"] == "PLATFORM_ANSWER_UNUSABLE"
    assert result["unavailable_member"] == member


@requires_node
def test_a_root_that_is_not_a_module_is_told_from_a_root_that_is_absent():
    """The one stage an `OBSERVED` reading could otherwise be confused with.

    A root module the platform does not have is an answer: `root_present` is
    false and the reading is `OBSERVED`. A root module that is not an object
    cannot be attributed. The two differ in `root_present` not at all, and the
    member is what says which of them happened.
    """
    not_an_object = "\nmoduleDescriptor = function () { return 'not-an-object'; };"
    refused = reading(platform_stub(CHASSIS_MODELS) + not_an_object)

    assert refused["unavailable_reason"] == "PLATFORM_ANSWER_UNUSABLE"
    assert stage_of(refused) == ("DeviceDescriptor.getRootModule", None)
    assert refused["root_present"] is False

    no_root = reading(platform_stub(
        "[{model: 'bare', type: 1, supported: true, module_types: []}]"
    ))

    assert no_root["resolution"] == "OBSERVED"
    assert no_root["root_present"] is False
    assert stage_of(no_root) == (None, None)


@requires_node
def test_the_stage_carries_the_position_the_member_was_called_with():
    """A member addressed by position says which position, not only which member.

    `getModuleAt` is called once per module the platform counted, so "the walk
    stopped in `getModuleAt`" is a different finding from "it stopped at the
    second position of the root".
    """
    one_good_then_undefined = _root(
        modules="[{model: 'card', module_type: 4, hot_swappable: true,"
                " slot_types: [], modules: []}, undefined]",
    )
    result = reading(platform_stub(_chassis(one_good_then_undefined)))

    assert stage_of(result) == ("ModuleDescriptor.getModuleAt", 1)


@requires_node
def test_a_member_that_takes_no_argument_reports_none():
    """`null` is "this member takes no argument", not "the argument is unknown"."""
    result = reading(platform_stub(CHASSIS_MODELS, count="'many'"))

    assert stage_of(result) == ("DeviceFactory.getAvailableDeviceCount", None)


@requires_node
def test_a_descriptor_the_factory_will_not_hand_over_names_the_factory_member():
    """The stage before the chassis chain begins at all, with its own index."""
    result = reading(platform_stub("[]", count="3"), factory_index=2)

    assert result["unavailable_reason"] == "PLATFORM_ANSWER_UNUSABLE"
    assert stage_of(result) == ("DeviceFactory.getAvailableDeviceAt", 2)


# ---------------------------------------------------------------------------
# A stage is not only for a refused answer.
# ---------------------------------------------------------------------------

@requires_node
@pytest.mark.parametrize(("reason", "member", "prelude"), [
    ("PLATFORM_CALL_FAILED", "IPC.hardwareFactory",
     platform_stub(CHASSIS_MODELS, fail=True)),
    ("PLATFORM_MEMBER_ABSENT", "HardwareFactory.devices",
     "var ipc = {hardwareFactory: function () { return {}; }};"),
    ("PLATFORM_ANSWER_UNUSABLE", "HardwareFactory.devices",
     "var ipc = {hardwareFactory: function () { return null; }};"),
], ids=["call-failed", "member-absent", "receiver-nothing"])
def test_every_reason_that_reached_a_member_names_it(
    reason: str, member: str, prelude: str,
):
    """A call that did not return, a member not offered, and a null receiver.

    Three different readings, each about a member a reader needs named. The
    third names the member it could not *call* rather than the one that handed
    over nothing, because that is the call this artifact was making when the
    reading stopped.
    """
    result = reading(prelude)

    assert result["unavailable_reason"] == reason
    assert result["unavailable_member"] == member
