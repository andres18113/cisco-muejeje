"""The chassis walk: where it stops, and what it refuses to report.

`test_platform_modules` covers what `platform.module_descriptors` reports; this
module covers the two things that decide whether that report can be trusted —
the bounds the walk stops at, and the answers it refuses to attribute.

**Every bound is Muejeje's own** (MJ-029). Nothing in this repository has
measured how large a Packet Tracer chassis descriptor can be, so each ceiling
is a limit on what one call will do, and every subtree it omits is marked: a
truncated branch stays visibly absent and can never be read as an observed
absence. A node whose children did not fit reports none of them rather than a
prefix, because half a bay list read as a complete one is the failure the
marking exists to prevent.

**An unreadable platform is an observation, not a V6 failure** (MJ-031), and a
malformed node makes the whole reading unusable rather than a partial one:
reporting three fields of a module and dropping the fourth would look like an
answer about the platform rather than about our inability to read it.

Split out of `test_platform_modules` at the line budget — what a capability
reports and where it stops reading are two claims (MJ-018, MJ-020). Nothing
here has reached `9.0.1.0858` (MJ-015).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import (
    CHASSIS_MODELS,
    dispatch_v6,
    node_available,
    platform_stub,
)

OPERATION = "platform.module_descriptors"

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(**args) -> str:
    return json.dumps({
        "v": 6, "operation_rid": "rid-modules", "op": OPERATION, "args": args,
    })


def _observed(models: str = CHASSIS_MODELS, **args) -> dict:
    return dispatch_v6(_request(**args), prelude=platform_stub(models))["result"]


def _deep(depth: int) -> str:
    """A chassis `depth` levels deep, one module per level."""
    node = (
        "{model: 'leaf', module_type: 1, hot_swappable: false,"
        " slot_types: [], modules: []}"
    )
    for _ in range(depth):
        node = (
            "{model: 'bay', module_type: 1, hot_swappable: false,"
            f" slot_types: [1], modules: [{node}]}}"
        )
    return (
        "[{model: 'deep', type: 1, supported: true, module_types: [],"
        f" root: {node}}}]"
    )


@requires_node
def test_a_tree_deeper_than_the_bound_is_marked_rather_than_cut_silently():
    """An omitted subtree stays visibly absent (MJ-029)."""
    result = _observed(_deep(14))
    deepest = result["nodes"][-1]

    assert result["resolution"] == "OBSERVED"
    assert result["depth_truncated"] is True
    assert result["nodes_truncated"] is False
    assert deepest["depth"] == 12
    assert deepest["children_truncated"] is True
    assert deepest["module_count"] == 1, (
        "the count the platform reported is still reported; what is missing is "
        "the subtree, and the mark says so"
    )


@requires_node
def test_more_nodes_than_the_bound_reads_are_marked_truncated():
    """The node ceiling refuses a whole set of children, never a prefix.

    Half a bay list reported as a complete one is the failure this marking
    exists to prevent, so a node whose children did not fit reports none of
    them and says so.
    """
    wide = ", ".join(
        "{model: 'card', module_type: 4, hot_swappable: true,"
        " slot_types: [], modules: []}" for _ in range(400)
    )
    models = (
        "[{model: 'wide', type: 1, supported: true, module_types: [], root:"
        " {model: 'root', module_type: 18, hot_swappable: false,"
        f" slot_types: [], modules: [{wide}]}}}}]"
    )
    result = _observed(models)

    assert result["resolution"] == "OBSERVED"
    assert len(result["nodes"]) == 401
    assert result["nodes"][0]["module_count"] == 400
    assert result["nodes"][1]["module_count"] == 0
    assert result["nodes_truncated"] is False

    deeper = models.replace("modules: []}", "modules: [null, null]}", 1)
    assert _observed(deeper)["nodes_truncated"] is False


@requires_node
def test_a_child_set_that_would_cross_the_node_ceiling_is_refused_whole():
    wide = ", ".join(
        "{model: 'card', module_type: 4, hot_swappable: true,"
        " slot_types: [], modules: []}" for _ in range(600)
    )
    models = (
        "[{model: 'wider', type: 1, supported: true, module_types: [], root:"
        " {model: 'root', module_type: 18, hot_swappable: false,"
        f" slot_types: [], modules: [{wide}]}}}}]"
    )
    result = _observed(models)

    assert result["nodes_truncated"] is True
    assert result["nodes"] == [result["nodes"][0]]
    assert result["nodes"][0]["children_truncated"] is True
    assert result["nodes"][0]["module_count"] == 600


@requires_node
def test_more_slot_types_than_the_adapter_reads_are_marked_truncated():
    many = ", ".join(str(value) for value in range(80))
    models = (
        "[{model: 'slots', type: 1, supported: true, module_types: [], root:"
        " {model: 'root', module_type: 18, hot_swappable: false,"
        f" slot_types: [{many}], modules: [], module_count: 0}}}}]"
    )
    root = _observed(models)["nodes"][0]

    assert len(root["slot_types"]) == 64
    assert root["slot_types_truncated"] is True


# ---------------------------------------------------------------------------
# Executable: an unreadable platform, and the arguments.
# ---------------------------------------------------------------------------

@requires_node
@pytest.mark.parametrize(("prelude", "reason"), [
    ("", "PLATFORM_ABSENT"),
    ("var ipc = null;", "PLATFORM_ABSENT"),
])
def test_no_platform_object_is_an_observation_not_a_failure(
    prelude: str, reason: str,
):
    response = dispatch_v6(_request(), prelude=prelude)

    assert response["ok"] is True
    assert response["result"]["unavailable_reason"] == reason


@requires_node
def test_a_refused_platform_call_is_reported_without_its_error():
    result = dispatch_v6(
        _request(), prelude=platform_stub(CHASSIS_MODELS, fail=True),
    )["result"]

    assert result["unavailable_reason"] == "PLATFORM_CALL_FAILED"
    assert "refused this call" not in json.dumps(result)


@requires_node
@pytest.mark.parametrize("models", [
    "[{model: 'bad', type: 1, supported: true, module_types: [], root:"
    " {model: 7, module_type: 18, hot_swappable: false,"
    " slot_types: [], modules: []}}]",
    "[{model: 'bad', type: 1, supported: true, module_types: [], root:"
    " {model: 'root', module_type: '18', hot_swappable: false,"
    " slot_types: [], modules: []}}]",
    "[{model: 'bad', type: 1, supported: true, module_types: [], root:"
    " {model: 'root', module_type: 18, hot_swappable: 1,"
    " slot_types: [], modules: []}}]",
    "[{model: 'bad', type: 1, supported: true, module_types: [], root:"
    " {model: 'root', module_type: 18, hot_swappable: false,"
    " slot_types: ['6'], modules: []}}]",
    "[{model: 'bad', type: 1, supported: true, module_types: [], root:"
    " {model: 'root', module_type: 18, hot_swappable: false,"
    " slot_types: [], modules: [], module_count: -1}}]",
])
def test_every_field_of_a_node_is_checked_before_it_is_reported(models: str):
    """One malformed field makes the whole reading unusable, not partial."""
    result = _observed(models)

    assert result["resolution"] == "UNAVAILABLE"
    assert result["unavailable_reason"] == "PLATFORM_ANSWER_UNUSABLE"
    assert result["nodes"] == []


@requires_node
def test_a_missing_descriptor_inside_the_count_is_unusable_not_empty():
    result = dispatch_v6(
        _request(), prelude=platform_stub("[]", count="3"),
    )["result"]

    assert result["unavailable_reason"] == "PLATFORM_ANSWER_UNUSABLE"
