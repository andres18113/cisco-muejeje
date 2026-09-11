"""`network.device_ports`: one device's ports, in the same reading as its identity.

The operation selects the device at one workspace position, reads what that
device says it is, and reads the same device's ports — and reports all of it as
one observation. Three claims this module is responsible for:

* **One observation, attributable.** The name and model beside the ports were
  read off the device the ports came from, after a single hand-over, in the same
  call. A consumer never joins `network.device_identity` from one moment with
  ports from another (MJ-031).
* **A bounded port window that says so.** How many ports exist is the
  platform's answer; how many one reading carries is `MAX_PORT_WINDOW`. A device
  with more is paged from `port_offset`, as far as its ports go, and a window
  that stops short reports `window_truncated` (MJ-029).
* **Positions, and nothing inferred.** `workspace_index` and `port_index` are
  positions in this reading. Nothing is joined to the factory, no port name is
  parsed, no link is followed and nothing is mutated (MJ-002).

What the reading refuses to report, and which requests it refuses to read, are
`test_network_port_values`, split from here at the line budget (MJ-020).

Everything here runs against a stub under Node. `Device.getPortCount()`,
`Device.getPortAt(int)` and `Port.getName()` are documented for 9.0.1.0858 and
called by legacy code; no Muejeje reading of them exists, so the capability is
`PENDING_TARGET` (MJ-015, MJ-031).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.measure import declared_platform_bound, js_code_only
from tests.muejeje.platform_stub import CHASSIS_MODELS, PORT_DEVICES, platform_stub
from tests.muejeje.support import SCRIPT_ENGINE

OPERATION = "network.device_ports"
RESULT_FIELDS = {
    "resolution", "unavailable_reason", "workspace_index", "available_count",
    "device_present", "name", "model", "port_offset", "limit", "port_count",
    "ports", "window_truncated",
}
EXACT_MAX = declared_platform_bound("EXACT_INTEGER_MAX")
WINDOW = declared_platform_bound("MAX_PORT_WINDOW")

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(**args) -> str:
    return json.dumps({
        "v": 6, "operation_rid": "rid-ports", "op": OPERATION, "args": args,
    })


def _stub(devices: str = PORT_DEVICES) -> str:
    return platform_stub(CHASSIS_MODELS, devices=devices)


def _observed(devices: str = PORT_DEVICES, **args) -> dict:
    args.setdefault("workspace_index", 0)
    return dispatch_v6(_request(**args), prelude=_stub(devices))["result"]


def _one_device(spec: str) -> str:
    """A workspace holding a single device described by `spec`."""
    return f"[{{{spec}}}]"


# ---------------------------------------------------------------------------
# Structural: an operation, an adapter, and what the adapter never reaches for.
# ---------------------------------------------------------------------------

def test_the_operation_reads_the_workspace_only_through_its_adapter():
    """Operation -> adapter -> boundary; the dispatcher holds no bound (MJ-019)."""
    body = (SCRIPT_ENGINE / "150_network_ports.js").read_text(encoding="utf-8")
    dispatcher = (SCRIPT_ENGINE / "210_dispatcher_v6.js").read_text(encoding="utf-8")

    assert "muejejeAdapterDevicePorts(" in body
    assert "muejejeAdapterCall" not in body and "ipc" not in js_code_only(body)
    assert "MUEJEJE_NETWORK_PORTS_ARGS = {" in body
    assert "MUEJEJE_NETWORK_PORTS_ARGS" in dispatcher
    for bound in ("EXACT_INTEGER_MAX", "MAX_PORT_WINDOW"):
        assert f"MUEJEJE_PLATFORM_LIMITS.{bound}" in body, bound
        assert bound not in dispatcher, "the dispatcher holds no bound"


def test_the_reading_follows_no_link_reads_no_state_and_joins_no_factory():
    """Each of these would be a further subject with its own evidence.

    The boundary would refuse every one of them; this is about what the adapter
    reaches for. A link is topology, and a factory join is a relationship
    nobody observed (MJ-002, MJ-031).
    """
    adapter = (SCRIPT_ENGINE / "090_network_ports_adapter.js").read_text(encoding="utf-8")
    code = js_code_only(adapter)

    for unowned in (
        "getLink", "getOwnerDevice", "getIpAddress", "getMacAddress", "isPortUp",
        "isProtocolUp", "getType", "hardwareFactory", "getDescriptor",
        "getRootModule",
    ):
        assert unowned not in code, unowned


# ---------------------------------------------------------------------------
# Executable: one observation, attributable.
# ---------------------------------------------------------------------------

@requires_node
def test_the_result_shape_is_the_same_whether_the_platform_answered():
    absent = dispatch_v6(_request(workspace_index=0))["result"]

    assert set(absent) == set(_observed()) == RESULT_FIELDS
    assert (absent["resolution"], absent["unavailable_reason"]) == (
        "UNAVAILABLE", "PLATFORM_ABSENT",
    )
    assert [absent[field] for field in ("name", "model", "port_count")] == [None] * 3
    assert absent["ports"] == [] and absent["device_present"] is False


@requires_node
def test_a_device_answers_with_its_identity_and_its_ports_from_one_reading():
    result = _observed()

    assert result["resolution"] == "OBSERVED"
    assert (result["workspace_index"], result["available_count"]) == (0, 2)
    assert (result["device_present"], result["name"], result["model"]) == (
        True, "a", "PT-Router",
    )
    assert result["port_count"] == 3
    assert result["ports"] == [
        {"port_index": 0, "name": "port-0"},
        {"port_index": 1, "name": "port-1"},
        {"port_index": 2, "name": ""},
    ]
    assert (result["port_offset"], result["limit"]) == (0, WINDOW)
    assert result["window_truncated"] is False


@requires_node
def test_a_workspace_changing_between_hand_overs_cannot_split_one_reading():
    """The device is handed over once, and every fact is read off that one.

    This workspace hands over a different device each time it is asked. An
    adapter that asked once for the identity and again for the ports would
    report one device's name beside another's ports — a device that never
    existed in that state.
    """
    shifting = _stub() + (
        "\nvar HANDED = 0;"
        "\nNETWORK.getDeviceAt = function (index) {"
        " log('Network.getDeviceAt');"
        " return workspaceDevice(DEVICES[HANDED++ % DEVICES.length]); };"
    )
    observed = dispatch_v6(
        _request(workspace_index=0), prelude=shifting,
        report="{response: JSON.parse(mcpDispatchV6(REQUEST)), calls: CALLS}",
    )
    result = observed["response"]["result"]

    assert observed["calls"].count("Network.getDeviceAt") == 1
    assert result["name"] == "a"
    assert [port["name"] for port in result["ports"]] == ["port-0", "port-1", ""]


# ---------------------------------------------------------------------------
# Executable: the port window.
# ---------------------------------------------------------------------------

@requires_node
@pytest.mark.parametrize(("args", "indexes", "truncated"), [
    ({"limit": 2}, [0, 1], True),
    ({"port_offset": 1, "limit": 1}, [1], True),
    ({"port_offset": 2}, [2], False),
    ({"port_offset": 9}, [], False),
])
def test_the_port_window_is_reported_back_and_a_tail_is_marked(
    args: dict, indexes: list[int], truncated: bool,
):
    result = _observed(**args)

    assert result["resolution"] == "OBSERVED" and result["port_count"] == 3
    assert [port["port_index"] for port in result["ports"]] == indexes
    assert result["window_truncated"] is truncated


@requires_node
def test_a_device_with_more_ports_than_any_window_is_paged_rather_than_capped():
    """A thousand ports is a count to page through, one bounded window at a time."""
    many = _one_device(
        "name: 'wide', model: 'm', ports: [{name: 'p'}], port_count: 1000,"
        " dense_ports: true"
    )
    first = _observed(many)
    last = _observed(many, port_offset=990)

    assert len(first["ports"]) == WINDOW and first["window_truncated"] is True
    assert [port["port_index"] for port in last["ports"]] == list(range(990, 1000))
    assert last["window_truncated"] is False


@requires_node
def test_a_published_port_index_is_admitted_back_at_the_end_of_its_domain():
    """Relay closure for the port window: the last port that can exist, then past it."""
    widest = _one_device(
        "name: 'wide', model: 'm', ports: [{name: 'p'}],"
        f" port_count: {EXACT_MAX}, dense_ports: true"
    )
    last = _observed(widest, port_offset=EXACT_MAX - 1)
    after = _observed(widest, port_offset=last["ports"][-1]["port_index"] + 1)
    past = dispatch_v6(
        _request(workspace_index=0, port_offset=EXACT_MAX + 1),
        prelude=_stub(widest),
    )

    assert [port["port_index"] for port in last["ports"]] == [EXACT_MAX - 1]
    assert after["resolution"] == "OBSERVED" and after["ports"] == []
    assert after["window_truncated"] is False
    assert past["error"]["code"] == "INVALID_ARGS"


@requires_node
@pytest.mark.parametrize(("args", "count", "present"), [
    ({"workspace_index": 9}, None, False),
    ({"workspace_index": 1}, 0, True),
])
def test_an_empty_answer_is_an_observation_not_an_unreadable_platform(
    args: dict, count: int | None, present: bool,
):
    """Past the end of the workspace, or a device with no ports: both are answers."""
    result = _observed(**args)

    assert result["resolution"] == "OBSERVED"
    assert result["device_present"] is present
    assert result["port_count"] == count
    assert result["ports"] == []
