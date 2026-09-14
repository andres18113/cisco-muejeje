"""`network.link_inventory`: which links the workspace holds, a window at a time.

The first reading of the workspace's links — an enumeration of its own, apart
from its devices. Four claims this module is responsible for:

* **Its own address domain, closed under relay.** Each link is published at the
  `workspace_link_index` it was handed over at and a window starts at
  `workspace_link_offset`; neither is a device position. The last position the
  inventory can publish is one `network.link_endpoints` admits and reads, with
  no ceiling on the position itself (MJ-029).
* **A bounded window that says so**, paged rather than capped (MJ-029).
* **The connection type stays the platform's number.** Any exact integer comes
  back as it was answered and is named nothing (MJ-014); anything else cannot be
  attributed, and takes the window with it.
* **No workspace is cached.** Two readings in one evaluation each report what
  the workspace held when they were taken (MJ-002).

What a link joins is `test_network_link_endpoints`. Everything here runs against
a stub under Node and establishes nothing about `9.0.1.0858` (MJ-015).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.measure import declared_platform_bound, js_code_only
from tests.muejeje.platform_stub import (
    CHASSIS_MODELS,
    LINKED_DEVICES,
    linked_stub,
    platform_stub,
)
from tests.muejeje.support import SCRIPT_ENGINE

OPERATION = "network.link_inventory"
RESULT_FIELDS = {
    "resolution", "unavailable_reason", "unavailable_member", "unavailable_argument",
    "available_count", "workspace_link_offset", "limit", "links", "window_truncated",
}
EXACT_MAX = declared_platform_bound("EXACT_INTEGER_MAX")
EXACT_MIN = declared_platform_bound("EXACT_INTEGER_MIN")
WINDOW = declared_platform_bound("MAX_LINK_WINDOW")

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(op: str = OPERATION, **args) -> str:
    return json.dumps({"v": 6, "operation_rid": "rid-links", "op": op, "args": args})


def _result(prelude: str = "", op: str = OPERATION, **args) -> dict:
    return dispatch_v6(_request(op, **args), prelude=prelude)["result"]


def _links(*specs: str) -> str:
    """The linked workspace's devices, joined by exactly `specs`."""
    return platform_stub(
        CHASSIS_MODELS, devices=LINKED_DEVICES, links=f"[{', '.join(specs)}]",
    )


# ---------------------------------------------------------------------------
# Structural: an operation, an adapter, and what the adapter never reaches for.
# ---------------------------------------------------------------------------

def test_the_operation_reads_links_only_through_its_adapter():
    """Operation -> adapter -> boundary; the dispatcher holds no bound (MJ-019)."""
    code = js_code_only((SCRIPT_ENGINE / "146_network_link_inventory.js").read_text(encoding="utf-8"))
    dispatcher = (SCRIPT_ENGINE / "210_dispatcher_v6.js").read_text(encoding="utf-8")

    assert "muejejeAdapterLinkInventory(" in code
    assert "muejejeAdapterCall" not in code and "ipc" not in code
    assert "MUEJEJE_NETWORK_LINK_INVENTORY_ARGS" in dispatcher
    for bound in ("EXACT_INTEGER_MAX", "MAX_LINK_WINDOW"):
        assert f"MUEJEJE_PLATFORM_LIMITS.{bound}" in code, bound
        assert bound not in dispatcher, "the dispatcher holds no bound"


def test_the_inventory_reads_no_end_and_decides_no_kind_of_link():
    """Which ports a link joins is another subject; which kind it is, nobody's."""
    adapter = SCRIPT_ENGINE / "086_network_link_inventory_adapter.js"
    code = js_code_only(adapter.read_text(encoding="utf-8"))

    for unowned in ("getPort", "getOwnerDevice", "getClassName", "Cable", "Antenna", "typeof"):
        assert unowned not in code, unowned


# ---------------------------------------------------------------------------
# Executable: what the inventory answers.
# ---------------------------------------------------------------------------

@requires_node
def test_the_result_shape_is_the_same_whether_the_platform_answered():
    absent = _result()

    assert set(absent) == set(_result(linked_stub())) == RESULT_FIELDS
    assert (absent["unavailable_reason"], absent["links"]) == ("PLATFORM_ABSENT", [])


@requires_node
def test_each_link_is_reported_at_its_position_with_what_it_reports():
    result = _result(linked_stub())

    assert (result["resolution"], result["available_count"]) == ("OBSERVED", 2)
    assert result["links"] == [
        {"workspace_link_index": 0, "connection_type": 5, "object_uuid": "link-uuid-0"},
        {"workspace_link_index": 1, "connection_type": 6, "object_uuid": "link-uuid-1"},
    ]
    assert (result["workspace_link_offset"], result["limit"]) == (0, WINDOW)
    assert result["window_truncated"] is False


@requires_node
@pytest.mark.parametrize(("args", "indexes", "truncated"), [
    ({"limit": 1}, [0], True),
    ({"workspace_link_offset": 1}, [1], False),
    ({"workspace_link_offset": 9}, [], False),
])
def test_the_window_is_reported_back_and_a_tail_is_marked(
    args: dict, indexes: list[int], truncated: bool,
):
    result = _result(linked_stub(), **args)

    assert (result["resolution"], result["available_count"]) == ("OBSERVED", 2)
    assert [link["workspace_link_index"] for link in result["links"]] == indexes
    assert result["window_truncated"] is truncated


@requires_node
def test_a_workspace_without_links_is_an_answer_that_asks_for_none():
    observed = dispatch_v6(
        _request(), prelude=_links(),
        report="{result: JSON.parse(mcpDispatchV6(REQUEST)).result, calls: CALLS}",
    )

    assert (observed["result"]["resolution"], observed["result"]["available_count"]) == (
        "OBSERVED", 0,
    )
    assert "Network.getLinkAt" not in observed["calls"]


@requires_node
def test_more_links_than_any_window_are_paged_rather_than_capped():
    tail = _result(linked_stub(link_count="1000000", dense=True), workspace_link_offset=999990)

    assert [link["workspace_link_index"] for link in tail["links"]] == list(range(999990, 1000000))
    assert tail["window_truncated"] is False


@requires_node
def test_the_last_link_position_that_can_exist_is_published_and_read_back():
    """Relay closure at the far end of the domain, then at it, then past it."""
    prelude = linked_stub(link_count=str(EXACT_MAX), dense=True)
    inventory = _result(prelude, workspace_link_offset=EXACT_MAX - 1, limit=8)
    published = [link["workspace_link_index"] for link in inventory["links"]]
    endpoints = dispatch_v6(
        _request("network.link_endpoints", workspace_link_index=published[-1]),
        prelude=prelude,
    )

    assert published == [EXACT_MAX - 1] and inventory["window_truncated"] is False
    assert endpoints["ok"] is True, endpoints["error"]
    assert (endpoints["result"]["link_present"], endpoints["result"]["workspace_link_index"]) == (
        True, EXACT_MAX - 1,
    )
    assert _result(prelude, workspace_link_offset=EXACT_MAX)["links"] == []
    past = dispatch_v6(_request(workspace_link_offset=EXACT_MAX + 1), prelude=prelude)
    assert past["error"]["code"] == "INVALID_ARGS"


@requires_node
@pytest.mark.parametrize("value", [EXACT_MIN, -1, 0, EXACT_MAX])
def test_a_connection_type_is_published_as_the_platform_answered_it(value: int):
    """Opaque: the whole value domain comes back unchanged, and nothing names it."""
    result = _result(_links(f"{{connection_type: {value}, object_uuid: 'l'}}"))

    assert result["resolution"] == "OBSERVED"
    assert result["links"][0]["connection_type"] == value


@requires_node
@pytest.mark.parametrize(("link", "member", "argument"), [
    ("null", "Network.getLinkAt", 0),
    ("{connection_type: '5', object_uuid: 'l'}", "Link.getConnectionType", None),
    ("{connection_type: 1.5, object_uuid: 'l'}", "Link.getConnectionType", None),
    (f"{{connection_type: {EXACT_MAX + 1}, object_uuid: 'l'}}", "Link.getConnectionType", None),
    ("{connection_type: 5, object_uuid: 7}", "Link.getObjectUuid", None),
    ("{connection_type: 5, object_uuid: 'x'.repeat(257)}", "Link.getObjectUuid", None),
])
def test_an_answer_that_cannot_be_attributed_names_where_it_stopped(
    link: str, member: str, argument: int | None,
):
    """A hole inside the count is not an absence, and a value this runtime cannot
    carry unchanged is not reported — the whole window goes with it."""
    result = _result(_links(link))

    assert (result["resolution"], result["unavailable_reason"]) == (
        "UNAVAILABLE", "PLATFORM_ANSWER_UNUSABLE",
    )
    assert (result["unavailable_member"], result["unavailable_argument"]) == (member, argument)
    assert result["links"] == []


@requires_node
@pytest.mark.parametrize(("prelude", "reason", "member"), [
    ("var ipc = null;", "PLATFORM_ABSENT", None),
    ("var ipc = {network: function () { return {}; }};",
     "PLATFORM_MEMBER_ABSENT", "Network.getLinkCount"),
    ("var ipc = {network: function () { return {getLinkCount: function () {"
     " throw new Error('refused'); }}; }};", "PLATFORM_CALL_FAILED", "Network.getLinkCount"),
    (_links("{connection_type: 5}"), "PLATFORM_MEMBER_ABSENT", "Link.getObjectUuid"),
], ids=["no-platform", "no-link-members", "count-refused", "no-uuid-member"])
def test_an_unreadable_workspace_is_an_observation_with_its_reason(
    prelude: str, reason: str, member: str | None,
):
    response = dispatch_v6(_request(), prelude=prelude)

    assert response["ok"] is True
    assert (response["result"]["unavailable_reason"], response["result"]["unavailable_member"]) == (
        reason, member,
    )
    assert "refused" not in json.dumps(response)


@requires_node
def test_no_reading_carries_a_workspace_forward():
    """The same request twice in one evaluation, with a link removed between."""
    counts = dispatch_v6(
        _request(), prelude=linked_stub(),
        report=(
            "(function () { var first = JSON.parse(mcpDispatchV6(REQUEST)).result;"
            " LINKS.pop(); var second = JSON.parse(mcpDispatchV6(REQUEST)).result;"
            " return [first.available_count, second.available_count,"
            " second.links.length]; }())"
        ),
    )

    assert counts == [2, 1, 1]


# ---------------------------------------------------------------------------
# Executable: what is refused before anything is read.
# ---------------------------------------------------------------------------

@requires_node
@pytest.mark.parametrize("args", [
    {"limit": 0}, {"limit": WINDOW + 1}, {"limit": "8"},
    {"workspace_link_offset": -1}, {"workspace_link_offset": EXACT_MAX + 1},
    {"workspace_link_offset": 1.5}, {"workspace_offset": 0}, {"offset": 0},
    {"workspace_link_index": 0},
])
def test_an_argument_outside_its_declared_rule_is_refused(args: dict):
    response = dispatch_v6(_request(**args))

    assert (response["ok"], response["error"]["code"]) == (False, "INVALID_ARGS")


@requires_node
@pytest.mark.parametrize("call", [
    "muejejeAdapterLinkInventory(-1, 1)",
    f"muejejeAdapterLinkInventory(0, {WINDOW + 1})",
    "muejejeAdapterLinkInventory('0', 1)",
    "muejejeAdapterLinkEndpoints(-1)",
    f"muejejeAdapterLinkEndpoints({EXACT_MAX + 1})",
    "muejejeAdapterLinkEndpoints(null)",
])
def test_an_argument_a_link_adapter_would_not_accept_is_a_defect_not_a_reading(call: str):
    """V6 admission refuses these from a caller, so one here came from us."""
    observed = dispatch_v6(
        _request(), prelude=linked_stub(),
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
    reported = json.dumps(_result(linked_stub()))

    assert next(e for e in catalogue if e["op"] == OPERATION)["read_only"] is True
    for verdict in ("VERIFIED", "QUALIFIED", "ATTESTED", "PASS", "SUPPORTED_BY"):
        assert verdict not in reported, verdict
