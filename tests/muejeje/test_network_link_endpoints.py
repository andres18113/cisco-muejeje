"""`network.link_endpoints`: the two ports one link joins, in one reading.

It selects the link at one `workspace_link_index`, reads the object UUID the
platform reports for it, and reads the port at each end — its name, its object
UUID and its owner's object UUID. Four claims this module is responsible for:

* **One observation.** The link is handed over once, and its UUID and both ends
  are read off that hand-over (MJ-031).
* **Correlated by what the platform reports, on both sides.** An end's
  `object_uuid` is the UUID `network.device_ports` publishes for that port, and
  its `owner_device_object_uuid` the one the device inventory publishes — found
  by UUID alone, never by a name or a position, over a stub that hands out a
  fresh wrapper every time so JavaScript reference equality could not help.
* **A link that will not give its ends is a failure with its taxonomy, never a
  link without ends.** A missing getter is `PLATFORM_MEMBER_ABSENT`, a throwing
  one `PLATFORM_CALL_FAILED`, a `null` end or an ownerless port
  `PLATFORM_ANSWER_UNUSABLE` — each at its member, and none leaving one end
  published without the other (MJ-022).
* **A required position, in the link domain** (MJ-029).

Everything here runs against a stub under Node and establishes nothing about
`9.0.1.0858` (MJ-015).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.measure import declared_platform_bound, js_code_only
from tests.muejeje.platform_stub import (
    CHASSIS_MODELS,
    LINKED_DEVICES,
    LINKS,
    linked_stub,
    platform_stub,
)
from tests.muejeje.support import SCRIPT_ENGINE

OPERATION = "network.link_endpoints"
RESULT_FIELDS = {
    "resolution", "unavailable_reason", "unavailable_member", "unavailable_argument",
    "workspace_link_index", "available_count", "link_present",
    "object_uuid", "port1", "port2",
}
# Every fact the reading fills in once read, so a test asserts all are absent.
FACTS = ("object_uuid", "port1", "port2")
END_FIELDS = ("name", "object_uuid", "owner_device_object_uuid")
EXACT_MAX = declared_platform_bound("EXACT_INTEGER_MAX")

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(op: str = OPERATION, **args) -> str:
    return json.dumps({"v": 6, "operation_rid": "rid-ends", "op": op, "args": args})


def _result(prelude: str = "", op: str = OPERATION, **args) -> dict:
    return dispatch_v6(_request(op, **args), prelude=prelude)["result"]


def _devices_and(devices: str = LINKED_DEVICES, links: str = LINKS) -> str:
    return platform_stub(CHASSIS_MODELS, devices=devices, links=links)


# One way per member for a link to withhold its ends, and where each must stop.
# `ends` of the first link are `[[0, 0], [1, 1]]`: port `a-0`, then port `b-1`.
THROWING_END = (
    "\nvar handOverLink = workspaceLink;"
    "\nworkspaceLink = function (spec) { var link = handOverLink(spec);"
    " link.getPort1 = function () { log('Link.getPort1');"
    " throw new Error('refused'); }; return link; };"
)
FAILURES = {
    "a link that offers no ends": (
        _devices_and(links="[{connection_type: 5, object_uuid: 'l'}]"),
        "PLATFORM_MEMBER_ABSENT", "Link.getPort1",
    ),
    "an end getter that throws": (
        linked_stub() + THROWING_END, "PLATFORM_CALL_FAILED", "Link.getPort1",
    ),
    "a second end not handed over": (
        _devices_and(links="[{connection_type: 5, object_uuid: 'l', ends: [[0, 0], null]}]"),
        "PLATFORM_ANSWER_UNUSABLE", "Link.getPort2",
    ),
    "a port with no owner": (
        _devices_and(LINKED_DEVICES.replace("'port-uuid-b1'}", "'port-uuid-b1', orphan: true}")),
        "PLATFORM_ANSWER_UNUSABLE", "Port.getOwnerDevice",
    ),
    "an end port that offers no uuid": (
        _devices_and(LINKED_DEVICES.replace("{name: 'a-0', object_uuid: 'port-uuid-a0'}",
                                            "{name: 'a-0'}")),
        "PLATFORM_MEMBER_ABSENT", "Port.getObjectUuid",
    ),
    "a link that offers no uuid": (
        _devices_and(links="[{connection_type: 5, ends: [[0, 0], [1, 1]]}]"),
        "PLATFORM_MEMBER_ABSENT", "Link.getObjectUuid",
    ),
    "a hole inside the count": (
        _devices_and(links="[null]"), "PLATFORM_ANSWER_UNUSABLE", "Network.getLinkAt",
    ),
}


# ---------------------------------------------------------------------------
# Structural: an operation, an adapter, and nothing guessed.
# ---------------------------------------------------------------------------

def test_the_operation_reads_a_link_only_through_its_adapter():
    code = js_code_only((SCRIPT_ENGINE / "143_network_link_endpoints.js").read_text(encoding="utf-8"))
    dispatcher = (SCRIPT_ENGINE / "210_dispatcher_v6.js").read_text(encoding="utf-8")

    assert "muejejeAdapterLinkEndpoints(" in code
    assert "muejejeAdapterCall" not in code and "ipc" not in code
    assert "MUEJEJE_PLATFORM_LIMITS.EXACT_INTEGER_MAX" in code
    assert "MUEJEJE_NETWORK_LINK_ENDPOINTS_ARGS" in dispatcher


def test_the_adapter_never_decides_what_kind_of_link_it_was_handed():
    """No class name, no connection-type lookup, no probing, no route by name.

    Each would be an interface or an enum guessed rather than evidenced, and a
    link's state read beside its ends would be a convergence nobody asked about
    (MJ-014, MJ-031).
    """
    adapter = SCRIPT_ENGINE / "083_network_link_endpoints_adapter.js"
    code = js_code_only(adapter.read_text(encoding="utf-8"))

    for guessed in (
        "getClassName", "getConnectionType", "typeof", "Cable", "Antenna",
        "getRemotePortName", "getOtherPort", '"Port.getLink"', "isPortUp", "getIpAddress",
    ):
        assert guessed not in code, guessed


# ---------------------------------------------------------------------------
# Executable: both ends, from one hand-over, attributable by UUID.
# ---------------------------------------------------------------------------

@requires_node
def test_the_result_shape_is_the_same_whether_the_platform_answered():
    absent = _result(workspace_link_index=0)

    assert set(absent) == set(_result(linked_stub(), workspace_link_index=0)) == RESULT_FIELDS
    assert absent["unavailable_reason"] == "PLATFORM_ABSENT"
    assert [absent[fact] for fact in FACTS] == [None] * 3 and absent["link_present"] is False


@requires_node
@pytest.mark.parametrize(("index", "link", "port1", "port2"), [
    (0, "link-uuid-0", ("a-0", "port-uuid-a0", "device-uuid-a"),
     ("b-1", "port-uuid-b1", "device-uuid-b")),
    (1, "link-uuid-1", ("b-0", "port-uuid-b0", "device-uuid-b"),
     ("a-1", "port-uuid-a1", "device-uuid-a")),
])
def test_both_ends_are_read_off_the_link_at_that_position(
    index: int, link: str, port1: tuple, port2: tuple,
):
    result = _result(linked_stub(), workspace_link_index=index)

    assert (result["resolution"], result["available_count"], result["link_present"]) == (
        "OBSERVED", 2, True,
    )
    assert (result["workspace_link_index"], result["object_uuid"]) == (index, link)
    assert result["port1"] == dict(zip(END_FIELDS, port1))
    assert result["port2"] == dict(zip(END_FIELDS, port2))


@requires_node
@pytest.mark.parametrize("index", [0, 1])
def test_each_end_is_found_among_the_published_ports_by_uuid_alone(index: int):
    """The join a consumer makes, made here out of published readings only.

    The owner's UUID finds the device in the inventory, and that device's ports
    reading finds the port. The only thing compared at each step is a UUID the
    platform reported: no name and no position is consulted, and the address
    relayed to the ports reading is the one the inventory published.
    """
    prelude = linked_stub()
    devices = _result(prelude, "network.device_inventory")["devices"]
    link = _result(prelude, workspace_link_index=index)

    for end in (link["port1"], link["port2"]):
        owner = [d["workspace_index"] for d in devices
                 if d["object_uuid"] == end["owner_device_object_uuid"]]
        assert len(owner) == 1, end
        ports = _result(prelude, "network.device_ports", workspace_index=owner[0])
        assert ports["object_uuid"] == end["owner_device_object_uuid"]
        assert [p["object_uuid"] for p in ports["ports"]].count(end["object_uuid"]) == 1


@requires_node
def test_a_workspace_changing_between_hand_overs_cannot_split_one_reading():
    """This workspace hands over the other link each time it is asked.

    An adapter that asked for the link again per end would publish one link's
    UUID beside another link's ports — a link that never existed.
    """
    shifting = linked_stub() + (
        "\nvar HANDED = 0;"
        "\nNETWORK.getLinkAt = function (index) { log('Network.getLinkAt');"
        " return workspaceLink(LINKS[HANDED++ % LINKS.length]); };"
    )
    observed = dispatch_v6(
        _request(workspace_link_index=0), prelude=shifting,
        report="{response: JSON.parse(mcpDispatchV6(REQUEST)), calls: CALLS}",
    )
    result = observed["response"]["result"]

    assert observed["calls"].count("Network.getLinkAt") == 1
    assert (result["object_uuid"], result["port1"]["object_uuid"],
            result["port2"]["object_uuid"]) == ("link-uuid-0", "port-uuid-a0", "port-uuid-b1")


@requires_node
def test_a_position_past_the_end_is_an_answer_not_an_unreadable_platform():
    result = _result(linked_stub(), workspace_link_index=9)

    assert (result["resolution"], result["available_count"], result["link_present"]) == (
        "OBSERVED", 2, False,
    )
    assert [result[fact] for fact in FACTS] == [None] * 3


@requires_node
@pytest.mark.parametrize("case", sorted(FAILURES))
def test_a_link_that_will_not_give_its_ends_is_never_a_link_without_ends(case: str):
    prelude, reason, member = FAILURES[case]
    response = dispatch_v6(_request(workspace_link_index=0), prelude=prelude)
    result = response["result"]

    assert response["ok"] is True
    assert (result["resolution"], result["unavailable_reason"], result["unavailable_member"]) == (
        "UNAVAILABLE", reason, member,
    )
    assert result["link_present"] is False
    assert [result[fact] for fact in FACTS] == [None] * 3, "no end outlives the other"
    assert "refused" not in json.dumps(response)


# ---------------------------------------------------------------------------
# Executable: what is refused before anything is read.
# ---------------------------------------------------------------------------

@requires_node
def test_a_request_that_names_no_link_is_refused_and_reads_nothing():
    """Every position holds a different link, so no default could be honest."""
    observed = dispatch_v6(
        _request(), prelude=linked_stub(),
        report="{response: JSON.parse(mcpDispatchV6(REQUEST)), calls: CALLS}",
    )

    assert observed["response"]["error"]["code"] == "INVALID_ARGS"
    assert observed["calls"] == []


@requires_node
@pytest.mark.parametrize("args", [
    {"workspace_link_index": -1}, {"workspace_link_index": EXACT_MAX + 1},
    {"workspace_link_index": "0"}, {"workspace_link_index": 1.5},
    {"workspace_index": 0}, {"workspace_link_offset": 0},
    {"workspace_link_index": 0, "name": "a"}, {"workspace_link_index": 0, "limit": 1},
])
def test_an_argument_outside_its_declared_rule_is_refused(args: dict):
    """Including a name: addressing a link, or an end, by name is not this contract."""
    response = dispatch_v6(_request(**args))

    assert (response["ok"], response["error"]["code"]) == (False, "INVALID_ARGS")


@requires_node
def test_the_operation_is_read_only_and_reaches_no_verdict():
    catalogue = dispatch_v6(_request(), report="muejejeV6OperationCatalog()")
    reported = json.dumps(_result(linked_stub(), workspace_link_index=0))

    assert next(e for e in catalogue if e["op"] == OPERATION)["read_only"] is True
    for verdict in ("VERIFIED", "QUALIFIED", "ATTESTED", "PASS", "SUPPORTED_BY"):
        assert verdict not in reported, verdict
