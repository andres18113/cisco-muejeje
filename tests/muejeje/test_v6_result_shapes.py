"""The result shapes V6 publishes, top level and nested.

`test_v6_compatibility` holds the envelope and the failure taxonomy still; this
module holds the other half of MJ-030, which is about what an operation
*answers*:

    A result may gain a field. Nothing may lose one, be renamed, or keep its
    name while meaning something else.

Two measures, because the rule is asymmetric. Required fields are asserted as a
**subset** of what an operation answers, so an added field passes and a removed
or renamed one fails. The set of nested *paths* is asserted **equal**, because
a published nested object nobody froze is one nothing is holding still.

**A result is not only its top-level names.** A consumer reads
`descriptors[0].model` exactly as it reads `available_count`, so a rename
inside a nested object breaks a reader the same way — and only a gate that
walks the whole answer can see it. Measured before this module existed:
renaming `descriptors[].model_supported` left every compatibility check green.

Split out of `test_v6_compatibility` when that module crossed its own line
budget. The envelope a consumer parses and the answers it reads are two
claims, and the budget is what forced the split rather than letting it be
argued about (MJ-018, MJ-020).

None of this is a claim about Packet Tracer. It is a claim about the contract
we publish, checked against the kernel that implements it under Node (MJ-015).
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

# Per operation, the result fields a consumer may already be reading. An
# operation may answer with more; it may never answer with fewer.
REQUIRED_RESULT_FIELDS = {
    "platform.device_descriptors": {
        "resolution", "unavailable_reason", "available_count", "offset",
        "limit", "descriptors", "window_truncated",
    },
    "platform.module_descriptors": {
        "resolution", "unavailable_reason", "device_index", "available_count",
        "descriptor_present", "model", "device_type", "root_present", "nodes",
        "nodes_truncated", "depth_truncated",
    },
    "runtime.identify": {
        "extension_name", "extension_version", "protocol_versions",
        "operations", "supported_features", "runtime_session_id",
        "provenance", "lifecycle",
    },
    "runtime.capabilities": {
        "runtime_session_id", "protocol_versions", "operations",
        "supported_features",
    },
}

# The nested objects inside those results, by the path that reaches them.
# `descriptors[]` means "every object in that list". Same rule as above: a
# nested object may gain a field and may never lose one.
REQUIRED_NESTED_FIELDS = {
    "platform.device_descriptors": {
        "descriptors[]": {
            "model", "device_type", "model_supported",
            "supported_module_types", "module_types_truncated",
        },
    },
    "platform.module_descriptors": {
        "nodes[]": {
            "index", "parent_index", "depth", "slot_index", "model",
            "module_type", "hot_swappable", "slot_types",
            "slot_types_truncated", "module_count", "children_present",
            "children_truncated",
        },
    },
    "runtime.identify": {
        "provenance": {"state", "source_sha", "build_recipe_id"},
        "lifecycle": {"started", "started_at", "stopped_at", "start_count"},
    },
    "runtime.capabilities": {
        "operations[]": {"op", "read_only"},
    },
}

# What each operation has to be asked against for its published shape to be
# visible at all. A platform operation answers an empty list when there is no
# platform, and an empty list publishes no nested object, so the reading a
# consumer actually parses is the one driven here.
PRELUDE = {
    "platform.device_descriptors": platform_stub(CHASSIS_MODELS),
    "platform.module_descriptors": platform_stub(CHASSIS_MODELS),
}

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def missing_fields(frozen: set[str], observed: set[str]) -> set[str]:
    """The frozen fields `observed` no longer carries. Empty means compatible.

    This is the whole compatibility test for a result: a field that appeared is
    not in `frozen`, so it cannot show up here, while a field that was removed
    or renamed leaves its old name behind and does.
    """
    return frozen - observed


def _request(op: str) -> str:
    return json.dumps({
        "v": 6, "operation_rid": f"rid-shape-{op}", "op": op, "args": {},
    })


def _answer(op: str) -> dict:
    return dispatch_v6(_request(op), prelude=PRELUDE.get(op, ""))


def nested_shapes(result: dict) -> dict[str, list[set[str]]]:
    """`path -> every observed key set` for each nested object in a result.

    One entry per object rather than a union, so a list whose second item is
    missing a field is a failure rather than something the first item covers
    for it.
    """
    shapes: dict[str, list[set[str]]] = {}

    def visit(node: object, path: str) -> None:
        if isinstance(node, dict):
            if path:
                shapes.setdefault(path, []).append(set(node))
            for key, item in node.items():
                visit(item, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for item in node:
                visit(item, f"{path}[]")

    visit(result, "")
    return shapes


# ---------------------------------------------------------------------------
# The gate can tell an addition from a removal.
# ---------------------------------------------------------------------------

def test_the_compatibility_measure_admits_additions_and_catches_the_rest():
    """Asserted on synthetic field sets, in every direction that matters.

    A gate that reported "different" would fail on a compatible change and
    teach the next reader to edit the frozen set to make it pass, which is
    exactly how a breaking change gets waved through.
    """
    frozen = {"model", "device_type"}

    assert missing_fields(frozen, {"model", "device_type"}) == set()
    assert missing_fields(frozen, {"model", "device_type", "slot_types"}) == set()
    assert missing_fields(frozen, {"model"}) == {"device_type"}
    assert missing_fields(frozen, {"model", "deviceType"}) == {"device_type"}


# ---------------------------------------------------------------------------
# A result may grow. It may not shrink, rename, or change meaning.
# ---------------------------------------------------------------------------

@requires_node
@pytest.mark.parametrize("op", sorted(REQUIRED_RESULT_FIELDS))
def test_a_result_still_carries_every_field_already_published(op: str):
    observed = set(_answer(op)["result"])

    assert missing_fields(REQUIRED_RESULT_FIELDS[op], observed) == set(), (
        f"{op} dropped or renamed a published field; that needs a new protocol "
        "version, not a new field list"
    )


def test_every_admitted_operation_publishes_a_frozen_result_shape():
    """An operation with no frozen shape is one nothing is holding still.

    Adding an operation therefore means declaring what its result promises, in
    the same commit — not later, once a consumer has started reading it.
    """
    from tests.muejeje.test_capability_claims import admitted_operations

    assert set(REQUIRED_RESULT_FIELDS) == admitted_operations()


@requires_node
@pytest.mark.parametrize("op", sorted(REQUIRED_NESTED_FIELDS))
def test_every_published_nested_object_still_carries_its_fields(op: str):
    """The same rule, one level down, where a rename hides best.

    Paths are asserted equal and fields as a subset: a nested object may gain
    a field, but a published one that stops being answered — or starts being
    answered somewhere new — is a change to what a consumer already parses.
    """
    observed = nested_shapes(_answer(op)["result"])
    frozen = REQUIRED_NESTED_FIELDS[op]

    assert set(observed) == set(frozen), (
        f"{op} publishes nested objects nobody froze, or dropped one: "
        f"{sorted(set(observed) ^ set(frozen))}"
    )
    for path, fields in frozen.items():
        for reported in observed[path]:
            assert missing_fields(fields, reported) == set(), (
                f"{op} dropped or renamed a published field under {path}"
            )


def test_the_nested_reader_finds_every_container_and_can_tell_a_rename():
    """Asserted on a synthetic result, in both directions.

    The gate above was added because a real rename —
    `descriptors[].model_supported` — passed every other check in this module.
    A reader that walked nothing would report the same clean tree, so what it
    finds is asserted here rather than assumed.
    """
    observed = nested_shapes({
        "count": 2,
        "provenance": {"state": "UNBOUND"},
        "descriptors": [{"model": "a"}, {"model_name": "b"}],
        "names": ["a", "b"],
    })

    assert set(observed) == {"provenance", "descriptors[]"}
    assert observed["descriptors[]"] == [{"model"}, {"model_name"}]
    assert missing_fields({"model"}, observed["descriptors[]"][1]) == {"model"}
