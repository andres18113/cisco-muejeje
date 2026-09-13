"""What `getModuleAt` answers inside the count, and what one position costs.

What `platform.module_descriptors` reports is `test_platform_modules`, and where
its walk stops is `test_platform_module_walk`. This module holds what the
full-trust target investigation on `9.0.1.0858` changed about both (MJ-018).

**The evidence.** Inside the count `getModuleAt(i)` answered a
`ModuleDescriptor` or JavaScript `null` — 172 descriptors, 669 module nodes,
1551 positions: 497 objects, 1054 nulls, no error — while outside it Packet
Tracer raised `invalid vector subscript`, and a null could precede a module in
the same node. So a null is an ordinary answer on that build, and the walk goes
past it. It is recorded as `null_module_positions`: positions this reading
actually asked that answered `null` — never an empty or a free slot, because
what it means was not observed (MJ-015). The record is
`docs/qa/muejeje-pts-offline.md`, and it is about that build only.

**Positions are not nodes**: `MAX_MODULE_POSITIONS` bounds the `getModuleAt`
calls one reading makes, `MAX_MODULE_NODES` the nodes it keeps — queued, walked
and published, never what Packet Tracer built on its own side. A null spends a
position; a module spends both, unless it is dropped with a child set that did
not fit. Both are Muejeje's own (MJ-029) and read from the kernel here, and the
position budget stays within the node budget, which reserved these same calls
before the two were separated. Everything runs under Node against a stub and
establishes our walker only.
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.measure import declared_platform_bound, js_code_only
from tests.muejeje.platform_stub import CHASSIS_MODELS, platform_stub
from tests.muejeje.support import SCRIPT_ENGINE

OPERATION = "platform.module_descriptors"
GET_MODULE_AT = "ModuleDescriptor.getModuleAt"
# A module holding no modules, planted wherever a position must answer one.
CARD = "{model: 'card', module_type: 4, hot_swappable: true, slot_types: [], modules: []}"

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _entries(*entries: str) -> str:
    return "[" + ", ".join(entries) + "]"


def _chassis(modules: str) -> str:
    """One model whose root answers `modules`, position by position."""
    return (
        "[{model: 'chassis', type: 1, supported: true, module_types: [], root:"
        " {model: 'root', module_type: 18, hot_swappable: false,"
        f" slot_types: [], modules: {modules}}}}}]"
    )


def _read(models: str) -> dict:
    """The reading, and how many `getModuleAt` calls it actually made."""
    request = json.dumps({
        "v": 6, "operation_rid": "rid-positions", "op": OPERATION,
        "args": {"factory_index": 0},
    })
    return dispatch_v6(
        request, prelude=platform_stub(models),
        report="(function () {"
               " var result = JSON.parse(mcpDispatchV6(REQUEST)).result;"
               " var asked = CALLS.filter(function (name) {"
               f" return name === {json.dumps(GET_MODULE_AT)}; }}).length;"
               " return {result: result, asked: asked};"
               " }())",
    )


def _refused(models: str) -> tuple:
    result = _read(models)["result"]
    return (
        result["resolution"], result["unavailable_reason"],
        result["unavailable_member"], result["unavailable_argument"],
        result["nodes"],
    )


# ---------------------------------------------------------------------------
# A null inside the count is an answer, and the walk goes past it.
# ---------------------------------------------------------------------------

@requires_node
def test_the_first_failing_target_shape_is_observed_with_its_nulls_on_the_child():
    """The 1841 entry's shape, not its values: a root handing over one module
    whose own count of two answered `null` at both positions. It stopped the
    target reading at `getModuleAt` argument 0 as `PLATFORM_ANSWER_UNUSABLE`.
    """
    child = (
        "{model: 'child', module_type: 2, hot_swappable: false,"
        " slot_types: [], modules: [null, null]}"
    )
    observed = _read(_chassis(_entries(child)))
    result = observed["result"]
    root, module = result["nodes"]

    assert result["resolution"] == "OBSERVED"
    assert (result["unavailable_member"], result["unavailable_argument"]) == (None, None)
    assert root["null_module_positions"] == []
    assert (module["module_count"], module["null_module_positions"]) == (2, [0, 1])
    assert module["children_truncated"] is False
    assert result["module_positions_truncated"] is False
    assert observed["asked"] == 3


@requires_node
def test_mixed_positions_record_each_null_and_materialize_each_module():
    observed = _read(_chassis(_entries("null", CARD, "null", CARD)))
    nodes = observed["result"]["nodes"]

    assert observed["result"]["resolution"] == "OBSERVED"
    assert nodes[0]["null_module_positions"] == [0, 2]
    assert [node["module_index"] for node in nodes] == [None, 1, 3]
    assert [node["parent_index"] for node in nodes] == [None, 0, 0]
    assert observed["asked"] == 4


@requires_node
def test_a_null_before_a_module_does_not_end_the_walk():
    """The survey found this inside real nodes: a null, then a module after it."""
    observed = _read(_chassis(_entries("null", CARD)))
    nodes = observed["result"]["nodes"]

    assert observed["asked"] == 2, "the position after the null was asked"
    assert [(node["model"], node["module_index"]) for node in nodes] == [
        ("root", None), ("card", 1),
    ]
    assert nodes[0]["null_module_positions"] == [0]


@requires_node
def test_a_chassis_with_no_null_reads_as_it_did_and_says_so():
    """The recorded access-point shape, every position a module."""
    observed = _read(CHASSIS_MODELS)
    nodes = observed["result"]["nodes"]

    assert [node["model"] for node in nodes] == ["", "PT-REPEATER-NM-1CFE", ""]
    assert [node["module_index"] for node in nodes] == [None, 0, 1]
    assert [node["null_module_positions"] for node in nodes] == [[], [], []]
    assert observed["asked"] == 2


def test_a_null_position_is_published_under_no_name_that_explains_it():
    """What a null means physically is not observed, so no field may say."""
    code = js_code_only(
        (SCRIPT_ENGINE / "110_platform_module_adapter.js").read_text(encoding="utf-8")
    )

    assert "null_module_positions" in code
    for name in ("empty_slot", "free_slot", "unused_slot", "absent_hardware"):
        assert name not in code, name


# ---------------------------------------------------------------------------
# What is still not an answer.
# ---------------------------------------------------------------------------

@requires_node
def test_a_position_whose_call_throws_is_a_failed_call_at_that_position():
    assert _refused(_chassis(_entries(CARD, "null", "{throws: true}"))) == (
        "UNAVAILABLE", "PLATFORM_CALL_FAILED", GET_MODULE_AT, 2, [],
    )


@requires_node
@pytest.mark.parametrize(("entries", "position"), [
    (_entries("undefined"), 0), (_entries("null", CARD, "undefined"), 2),
])
def test_undefined_is_not_null_and_cannot_be_attributed(entries: str, position: int):
    assert _refused(_chassis(entries)) == (
        "UNAVAILABLE", "PLATFORM_ANSWER_UNUSABLE", GET_MODULE_AT, position, [],
    )


@requires_node
@pytest.mark.parametrize("primitive", ["7", "0", "false", "true", "''", "'card'"])
def test_a_primitive_where_a_module_is_documented_cannot_be_attributed(primitive: str):
    """`0`, `false` and `''` are what a truthiness test would read as null."""
    assert _refused(_chassis(_entries("null", primitive))) == (
        "UNAVAILABLE", "PLATFORM_ANSWER_UNUSABLE", GET_MODULE_AT, 1, [],
    )


# ---------------------------------------------------------------------------
# Two budgets: a null spends a position, a module spends a position and a node.
# ---------------------------------------------------------------------------

@requires_node
def test_nulls_spend_positions_and_never_the_node_budget():
    """A whole position budget of nulls on one node: every one asked, one node
    read, nothing truncated — a null names no descriptor this walk could keep."""
    count = declared_platform_bound("MAX_MODULE_POSITIONS")
    observed = _read(_chassis(_entries(*["null"] * count)))
    result = observed["result"]

    assert (result["resolution"], len(result["nodes"])) == ("OBSERVED", 1)
    assert (result["nodes_truncated"], result["module_positions_truncated"]) == (
        False, False,
    )
    assert result["nodes"][0]["null_module_positions"] == list(range(count))
    assert observed["asked"] == count


@requires_node
def test_a_module_spends_a_position_and_a_node_and_the_root_holds_the_last_one():
    """The widest child set the budgets allow is a whole position budget of
    modules, and it fills the node budget exactly: the root already holds the
    unit the walk began with, so `MAX_MODULE_POSITIONS` modules beside it are
    `MAX_MODULE_NODES` nodes. One more position is refused before any is asked,
    on the position budget — which by construction runs out first.
    """
    positions = declared_platform_bound("MAX_MODULE_POSITIONS")
    nodes = declared_platform_bound("MAX_MODULE_NODES")
    fits = _read(_chassis(_entries(*[CARD] * positions)))
    crosses = _read(_chassis(_entries(*[CARD] * (positions + 1))))
    result = crosses["result"]
    root = result["nodes"][0]

    assert fits["result"]["resolution"] == "OBSERVED"
    assert (fits["result"]["nodes_truncated"], fits["asked"]) == (False, positions)
    assert len(fits["result"]["nodes"]) == 1 + positions == nodes
    assert result["nodes"] == [root]
    assert (result["nodes_truncated"], result["module_positions_truncated"]) == (False, True)
    assert (root["children_truncated"], root["null_module_positions"]) == (True, [])
    assert crosses["asked"] == 0, "refused before Packet Tracer was asked anything"


@requires_node
def test_a_node_whose_positions_would_cross_the_budget_asks_none_of_them():
    """Refused whole and up front: a position nobody asked is never a null."""
    count = declared_platform_bound("MAX_MODULE_POSITIONS") + 1
    observed = _read(_chassis(_entries(*["null"] * count)))
    result = observed["result"]
    root = result["nodes"][0]

    assert result["resolution"] == "OBSERVED"
    assert result["module_positions_truncated"] is True
    assert (result["nodes_truncated"], result["depth_truncated"]) == (False, False)
    assert (root["module_count"], root["children_truncated"]) == (count, True)
    assert root["null_module_positions"] == []
    assert observed["asked"] == 0


@requires_node
def test_modules_spend_positions_too_and_the_budget_ends_between_nodes():
    """Sized from the bounds so the nulls alone would fit: only the modules'
    own positions make the budget run out, part-way through the children.
    """
    positions = declared_platform_bound("MAX_MODULE_POSITIONS")
    wide = min(declared_platform_bound("MAX_MODULE_NODES") - 1, 400)
    nulls = positions // wide
    holder = (
        "{model: 'holder', module_type: 4, hot_swappable: false,"
        f" slot_types: [], modules: {_entries(*['null'] * nulls)}}}"
    )
    answered = (positions - wide) // nulls
    assert wide * nulls <= positions < wide + wide * nulls and answered < wide
    observed = _read(_chassis(_entries(*[holder] * wide)))
    result = observed["result"]
    children = result["nodes"][1:]

    assert (result["module_positions_truncated"], result["nodes_truncated"]) == (True, False)
    assert len(children) == wide
    assert all(
        (child["null_module_positions"], child["children_truncated"])
        == (list(range(nulls)), False) for child in children[:answered]
    )
    assert all(
        (child["null_module_positions"], child["children_truncated"]) == ([], True)
        for child in children[answered:]
    )
    assert observed["asked"] == wide + answered * nulls <= positions


@requires_node
def test_a_node_at_the_depth_ceiling_asks_none_of_its_positions():
    depth = declared_platform_bound("MAX_MODULE_DEPTH")
    node = "{model: 'leaf', module_type: 1, hot_swappable: false, slot_types: [], modules: [null]}"
    for _ in range(depth):
        node = f"{{model: 'bay', module_type: 1, hot_swappable: false, slot_types: [], modules: [{node}]}}"
    observed = _read(
        f"[{{model: 'deep', type: 1, supported: true, module_types: [], root: {node}}}]"
    )
    deepest = observed["result"]["nodes"][-1]

    assert observed["result"]["depth_truncated"] is True
    assert observed["result"]["module_positions_truncated"] is False
    assert (deepest["model"], deepest["depth"], deepest["children_truncated"]) == (
        "leaf", depth, True,
    )
    assert deepest["null_module_positions"] == []
    assert observed["asked"] == depth
