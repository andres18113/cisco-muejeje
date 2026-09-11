"""`network.device_ports`: what one port reading refuses to report, and to read.

`test_network_ports` covers what the reading answers. This module covers what
decides whether that answer can be trusted: which platform answers cannot be
attributed — and that one of them makes the *whole* reading unavailable rather
than leaving a partial one — and which requests are refused before anything is
read, with an argument this adapter would not accept treated as a defect of
ours rather than as a platform reading (MJ-022, MJ-029, MJ-031).

Split from `test_network_ports` at the line budget (MJ-018, MJ-020). Everything
here runs against a stub under Node, and establishes nothing about `9.0.1.0858`
(MJ-015).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.measure import declared_platform_bound
from tests.muejeje.platform_stub import (
    CHASSIS_MODELS,
    IDENTITY_DEVICES,
    PORT_DEVICES,
    platform_stub,
)

OPERATION = "network.device_ports"
WINDOW = declared_platform_bound("MAX_PORT_WINDOW")
BEYOND = declared_platform_bound("EXACT_INTEGER_MAX") + 1

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(**args) -> str:
    return json.dumps({
        "v": 6, "operation_rid": "rid-port-values", "op": OPERATION, "args": args,
    })


def _stub(devices: str = PORT_DEVICES) -> str:
    return platform_stub(CHASSIS_MODELS, devices=devices)


# ---------------------------------------------------------------------------
# What cannot be attributed, and why none of it is partial.
# ---------------------------------------------------------------------------

@requires_node
@pytest.mark.parametrize("device", [
    "name: 7, model: 'm', ports: []",
    "name: 'x'.repeat(257), model: 'm', ports: []",
    "name: 'a', model: null, ports: []",
    "name: 'a', model: 'm', ports: [{name: 'p'}, null]",
    "name: 'a', model: 'm', ports: [{name: 7}]",
    "name: 'a', model: 'm', ports: [{name: 'x'.repeat(257)}]",
    "name: 'a', model: 'm', ports: [], port_count: -1",
    "name: 'a', model: 'm', ports: [], port_count: 1.5",
    f"name: 'a', model: 'm', ports: [], port_count: {BEYOND}",
])
def test_one_unattributable_fact_makes_the_whole_reading_unusable(device: str):
    """Identity and ports are one answer, so neither half outlives the other.

    A hole inside the port count is not an absence either: reporting fewer
    ports would invent an answer the platform did not give.
    """
    result = dispatch_v6(
        _request(workspace_index=0), prelude=_stub(f"[{{{device}}}]"),
    )["result"]

    assert (result["resolution"], result["unavailable_reason"]) == (
        "UNAVAILABLE", "PLATFORM_ANSWER_UNUSABLE",
    )
    assert [result[field] for field in ("name", "model", "port_count")] == [None] * 3
    assert result["ports"] == []


@requires_node
@pytest.mark.parametrize(("case", "reason"), [
    ("no platform", "PLATFORM_ABSENT"),
    ("no network members", "PLATFORM_MEMBER_ABSENT"),
    ("a device without ports", "PLATFORM_MEMBER_ABSENT"),
    ("a port call that throws", "PLATFORM_CALL_FAILED"),
])
def test_an_unreadable_platform_is_an_observation_with_its_reason(
    case: str, reason: str,
):
    """A device with no port members is not the interface this was written against."""
    preludes = {
        "no platform": "",
        "no network members": "var ipc = {network: function () { return {}; }};",
        "a device without ports": _stub(IDENTITY_DEVICES),
        "a port call that throws": _stub() + (
            "\nvar handOver = workspaceDevice;"
            "\nworkspaceDevice = function (spec) { var device = handOver(spec);"
            " device.getPortAt = function () { throw new Error('refused'); };"
            " return device; };"
        ),
    }
    response = dispatch_v6(_request(workspace_index=0), prelude=preludes[case])

    assert response["ok"] is True
    assert response["result"]["unavailable_reason"] == reason
    assert "refused" not in json.dumps(response["result"])


# ---------------------------------------------------------------------------
# What is refused before anything is read.
# ---------------------------------------------------------------------------

@requires_node
def test_a_request_that_names_no_device_is_refused_and_reads_nothing():
    """Every position holds a different device, so no default could be honest."""
    observed = dispatch_v6(
        _request(), prelude=_stub(),
        report="{response: JSON.parse(mcpDispatchV6(REQUEST)), calls: CALLS}",
    )

    assert observed["response"]["error"]["code"] == "INVALID_ARGS"
    assert observed["calls"] == []


@requires_node
@pytest.mark.parametrize("args", [
    {"workspace_index": -1}, {"workspace_index": BEYOND},
    {"workspace_index": "0"}, {"workspace_index": 1.5},
    {"workspace_index": 0, "limit": 0}, {"workspace_index": 0, "limit": WINDOW + 1},
    {"workspace_index": 0, "port_offset": -1},
    {"workspace_index": 0, "port_offset": BEYOND},
    {"workspace_index": 0, "name": "a"}, {"factory_index": 0},
    {"workspace_index": 0, "offset": 0}, {"workspace_index": 0, "workspace_offset": 0},
])
def test_an_argument_outside_its_declared_rule_is_refused(args: dict):
    """Including a name — addressing a device by name is not this contract."""
    response = dispatch_v6(_request(**args))

    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGS"


@requires_node
@pytest.mark.parametrize("call", [
    "muejejeAdapterDevicePorts(-1, 0, 1)",
    f"muejejeAdapterDevicePorts(0, {BEYOND}, 1)",
    f"muejejeAdapterDevicePorts(0, 0, {WINDOW + 1})",
    "muejejeAdapterDevicePorts('0', 0, 1)",
    "muejejeAdapterDevicePorts(0, null, 1)",
])
def test_an_argument_this_adapter_would_not_accept_is_a_defect_not_a_clamp(call: str):
    """V6 admission refuses these from a caller, so one here came from us.

    Reading a different device or a different window instead would report an
    observation about a question nobody asked.
    """
    observed = dispatch_v6(
        _request(workspace_index=0), prelude=_stub(),
        report=(
            f"(function () {{ try {{ return {{read: {call}}}; }}"
            " catch (thrown) { return {refused: String(thrown)}; } }())"
        ),
    )

    assert "read" not in observed, "a bad argument was answered, not refused"
    assert "PLATFORM_" not in observed["refused"]


@requires_node
def test_the_operation_is_read_only_and_reaches_no_verdict():
    catalogue = dispatch_v6(_request(), report="muejejeV6OperationCatalog()")
    reported = json.dumps(dispatch_v6(
        _request(workspace_index=0), prelude=_stub(),
    )["result"])

    assert next(e for e in catalogue if e["op"] == OPERATION)["read_only"] is True
    for verdict in ("VERIFIED", "QUALIFIED", "ATTESTED", "PASS", "SUPPORTED_BY"):
        assert verdict not in reported, verdict
