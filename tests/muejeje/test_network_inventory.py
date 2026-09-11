"""`network.device_inventory`: what this Packet Tracer currently holds.

The first reading of a *workspace* rather than of the hardware factory, and the
first operation in the `network` namespace.

**It reports an inventory and assumes no topology.** No count, no naming
scheme, no role, no ordering that outlives one reading, and no link, address or
port — MJ-002 is not "never look at a workspace", it is "never assume one", and
the difference is what this module drives: the same code answers an empty
workspace, a small one, and one whose names are nothing like each other.

**A workspace changes and a factory catalogue does not.** Two readings may
differ with nothing wrong, so the answer is an observation at a moment and
nothing here caches or carries one forward (MJ-011).

**Nothing here mutates.** `Network` offers members that create a device or a
link; none is on the boundary's allowlist, which is checked in
`test_platform_allowlist` rather than promised here.

The `OBSERVED` branch is stub-driven and establishes what our code does.
Nothing has reached `9.0.1.0858`, so the capability is `PENDING_TARGET`
(MJ-015, MJ-031).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.platform_stub import CHASSIS_MODELS, platform_stub
from tests.muejeje.support import SCRIPT_ENGINE

OPERATION = "network.device_inventory"

RESULT_FIELDS = {
    "resolution", "unavailable_reason", "available_count", "offset", "limit",
    "max_device_index", "devices", "window_truncated",
}
DEVICE_FIELDS = {"index", "name"}

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(**args) -> str:
    return json.dumps({
        "v": 6, "operation_rid": "rid-inventory", "op": OPERATION, "args": args,
    })


def _observed(devices: str | None = None, **args) -> dict:
    stub = (
        platform_stub(CHASSIS_MODELS) if devices is None
        else platform_stub(CHASSIS_MODELS, devices=devices)
    )
    return dispatch_v6(_request(**args), prelude=stub)["result"]


# ---------------------------------------------------------------------------
# Structural: the operation sits behind the adapter, and never beside it.
# ---------------------------------------------------------------------------

def test_the_operation_names_no_platform_symbol_of_its_own():
    """Operation -> adapter -> boundary -> platform, never a shortcut (MJ-019)."""
    body = (SCRIPT_ENGINE / "network_inventory.js").read_text(encoding="utf-8")

    assert "muejejeAdapterDeviceInventory(" in body
    assert "ipc" not in body
    assert "muejejeAdapterCall" not in body
    assert "getDeviceCount" not in body


def test_the_operation_declares_its_own_argument_rules():
    body = (SCRIPT_ENGINE / "network_inventory.js").read_text(encoding="utf-8")
    dispatcher = (SCRIPT_ENGINE / "dispatcher_v6.js").read_text(encoding="utf-8")

    assert "MUEJEJE_NETWORK_INVENTORY_ARGS = {" in body
    assert "MUEJEJE_PLATFORM_LIMITS.MAX_DEVICE_WINDOW" in body
    assert "MUEJEJE_NETWORK_INVENTORY_ARGS" in dispatcher
    assert "MAX_DEVICE_WINDOW" not in dispatcher, "the dispatcher holds no bound"


def test_the_workspace_reading_reads_no_topology_of_any_kind():
    """The adapter asks for an inventory, and for nothing that implies a shape.

    A link, an address, a port or a configuration would each be a second
    subject, and each would need its own evidence and its own bounds. The
    boundary would refuse them anyway — none is on the allowlist — so this
    gate is about intent: the file does not reach for them (MJ-002, MJ-004).
    """
    body = (SCRIPT_ENGINE / "network_adapter.js").read_text(encoding="utf-8")

    for unowned in ("getLink", "getPort", "getIpAddress", "getConfig"):
        assert unowned not in body, unowned


# ---------------------------------------------------------------------------
# Executable: one shape, and an inventory that assumes nothing.
# ---------------------------------------------------------------------------

@requires_node
def test_the_result_shape_is_the_same_whether_the_platform_answered():
    absent = dispatch_v6(_request())["result"]

    assert set(absent) == set(_observed()) == RESULT_FIELDS
    assert absent["resolution"] == "UNAVAILABLE"
    assert absent["unavailable_reason"] == "PLATFORM_ABSENT"
    assert absent["devices"] == []


@requires_node
def test_the_workspace_is_reported_device_by_device():
    result = _observed()

    assert result["resolution"] == "OBSERVED"
    assert result["unavailable_reason"] is None
    assert result["available_count"] == 3
    assert result["window_truncated"] is False
    assert [device["name"] for device in result["devices"]] == ["n1", "n2", "n3"]
    assert [device["index"] for device in result["devices"]] == [0, 1, 2]
    assert all(set(device) == DEVICE_FIELDS for device in result["devices"])


@requires_node
@pytest.mark.parametrize(("devices", "names"), [
    ("[]", []),
    ("[{name: 'only-one'}]", ["only-one"]),
    ("[{name: ''}, {name: 'x'}]", ["", "x"]),
    ("[{name: 'a-b-c'}, {name: 'A'}, {name: '1'}, {name: 'z9'}]",
     ["a-b-c", "A", "1", "z9"]),
])
def test_whatever_is_on_the_workspace_is_what_comes_back(
    devices: str, names: list[str],
):
    """Topology-agnostic, driven rather than asserted (MJ-002).

    An empty workspace, one device, an unnamed one, four unrelated names: the
    same code answers all of them, because it reports what the platform listed
    and expects nothing of it. An empty name is a real answer here for the same
    reason an empty model is: the platform said it.
    """
    result = _observed(devices)

    assert result["resolution"] == "OBSERVED"
    assert result["available_count"] == len(names)
    assert [device["name"] for device in result["devices"]] == names


@requires_node
def test_the_window_is_reported_back_and_a_tail_is_marked_truncated():
    result = _observed(offset=0, limit=2)

    assert result["offset"] == 0
    assert result["limit"] == 2
    assert result["available_count"] == 3
    assert result["window_truncated"] is True
    assert [device["name"] for device in result["devices"]] == ["n1", "n2"]
    assert [device["index"] for device in result["devices"]] == [0, 1]


@requires_node
def test_an_offset_past_the_end_reports_the_count_and_no_device():
    result = _observed(offset=9)

    assert result["resolution"] == "OBSERVED"
    assert result["available_count"] == 3
    assert result["devices"] == []
    assert result["window_truncated"] is False


@requires_node
def test_both_arguments_are_optional_and_default_to_the_first_window():
    result = _observed()

    assert result["offset"] == 0
    assert result["limit"] == 64


# ---------------------------------------------------------------------------
# Executable: what it refuses to report.
# ---------------------------------------------------------------------------

@requires_node
def test_a_device_inside_the_count_that_is_not_handed_over_is_unusable():
    """A hole is not an absence; reporting fewer devices would invent an answer."""
    result = _observed("[{name: 'n1'}, null, {name: 'n3'}]")

    assert result["resolution"] == "UNAVAILABLE"
    assert result["unavailable_reason"] == "PLATFORM_ANSWER_UNUSABLE"
    assert result["devices"] == []


@requires_node
@pytest.mark.parametrize("name", ["7", "null", "'x'.repeat(257)"])
def test_a_name_that_is_not_a_bounded_string_cannot_be_attributed(name: str):
    result = _observed(f"[{{name: {name}}}]")

    assert result["resolution"] == "UNAVAILABLE"
    assert result["unavailable_reason"] == "PLATFORM_ANSWER_UNUSABLE"


@requires_node
def test_a_name_at_its_bound_is_still_a_readable_answer():
    """The other side of the bound, so it is a bound and not a wall."""
    result = _observed("[{name: 'x'.repeat(256)}]")

    assert result["resolution"] == "OBSERVED"
    assert len(result["devices"][0]["name"]) == 256


@requires_node
@pytest.mark.parametrize(("prelude", "reason"), [
    ("", "PLATFORM_ABSENT"),
    ("var ipc = null;", "PLATFORM_ABSENT"),
    ("var ipc = {};", "PLATFORM_MEMBER_ABSENT"),
    ("var ipc = {network: function () { return {}; }};", "PLATFORM_MEMBER_ABSENT"),
    ("var ipc = {network: function () { throw new Error('refused'); }};",
     "PLATFORM_CALL_FAILED"),
])
def test_an_unreadable_workspace_is_an_observation_with_its_reason(
    prelude: str, reason: str,
):
    """Every reason the boundary can report, driven on this operation too.

    A member that is not there is not a call that failed, and neither is a
    platform that is not there: each says something different about the engine
    the module was started in (MJ-031).
    """
    response = dispatch_v6(_request(), prelude=prelude)

    assert response["ok"] is True
    assert response["result"]["unavailable_reason"] == reason


@requires_node
@pytest.mark.parametrize("args", [
    {"limit": 0}, {"limit": 65}, {"offset": -1}, {"offset": 5000},
    {"limit": "8"}, {"limit": 1.5}, {"page": 1},
])
def test_an_argument_outside_its_declared_rule_is_refused(args: dict):
    response = dispatch_v6(_request(**args))

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGS"


@requires_node
def test_the_operation_reaches_no_verdict_about_what_it_read():
    reported = json.dumps(_observed())

    for verdict in ("VERIFIED", "QUALIFIED", "ATTESTED", "PASS", "SUPPORTED_BY"):
        assert verdict not in reported, verdict


@requires_node
def test_the_operation_is_read_only_in_the_catalogue_it_publishes():
    catalogue = dispatch_v6(_request(), report="muejejeV6OperationCatalog()")
    entry = next(item for item in catalogue if item["op"] == OPERATION)

    assert entry["read_only"] is True
