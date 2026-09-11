"""The result shapes V6 publishes, top level and nested.

`test_v6_compatibility` holds the envelope and the failure taxonomy still; this
module holds the other half of MJ-030, which is about what an operation
*answers*:

    A result may gain a field. Nothing may lose one, be renamed, or keep its
    name while meaning something else.

Two measures, because the rule is asymmetric. Required fields and nested paths
are both asserted as a **floor** of what an operation answers, so an added
field or a new nested object passes and a removed or renamed one fails.

**A result is not only its top-level names.** A consumer reads
`descriptors[0].model` exactly as it reads `available_count`, so a rename
inside a nested object breaks a reader the same way, and only a gate that walks
the whole answer sees it: renaming `descriptors[].model_supported` once left
every compatibility check green.

Split out of `test_v6_compatibility` when that module crossed its own line
budget. The envelope a consumer parses and the answers it reads are two
claims, and the budget is what forced the split rather than letting it be
argued about (MJ-018, MJ-020). The frozen shapes themselves are declared data
and live with the rest of it in `support`, because they grow with every new
operation while these gates do not.

None of this is a claim about Packet Tracer. It is a claim about the contract
we publish, checked against the kernel that implements it under Node (MJ-015).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.platform_stub import CHASSIS_MODELS, PORT_DEVICES, platform_stub
from tests.muejeje.support import REQUIRED_NESTED_FIELDS, REQUIRED_RESULT_FIELDS

# Which operations have to be asked against a platform for their published
# shape to be visible at all. One answers an empty list when there is no
# platform, and an empty list publishes no nested object, so the reading a
# consumer actually parses is the one driven here.
NEEDS_PLATFORM = frozenset({
    "network.device_identity", "network.device_ports",
    "network.device_inventory", "platform.device_descriptors",
    "platform.module_descriptors", "platform.module_type_support",
})
# An operation whose arguments are not all optional needs them supplied before
# it will answer at all, and a shape gate has to see the answer.
REQUIRED_ARGS = {
    "network.device_identity": {"workspace_index": 0},
    "network.device_ports": {"workspace_index": 0},
    "platform.module_descriptors": {"factory_index": 0},
    "platform.module_type_support": {"factory_index": 0, "module_type": 6},
}

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def missing_fields(frozen: set[str], observed: set[str]) -> set[str]:
    """The frozen names `observed` no longer carries. Empty means compatible.

    The asymmetry is `broken_fields`' below, by names alone.
    """
    return frozen - observed


def _request(op: str) -> str:
    return json.dumps({
        "v": 6, "operation_rid": f"rid-shape-{op}", "op": op,
        "args": REQUIRED_ARGS.get(op, {}),
    })


def _answer(op: str) -> dict:
    stub = (
        platform_stub(CHASSIS_MODELS, devices=PORT_DEVICES)
        if op in NEEDS_PLATFORM else ""
    )
    return dispatch_v6(_request(op), prelude=stub)


def nested_shapes(result: dict) -> dict[str, list[dict]]:
    """`path -> every observed object` for each nested object in a result.

    One entry per object rather than a merge, so a list whose second item is
    missing a field is a failure rather than something the first item covers
    for it.
    """
    shapes: dict[str, list[dict]] = {}

    def visit(node: object, path: str) -> None:
        if isinstance(node, dict):
            if path:
                shapes.setdefault(path, []).append(node)
            for key, item in node.items():
                visit(item, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for item in node:
                visit(item, f"{path}[]")

    visit(result, "")
    return shapes


def broken_fields(frozen: dict, observed: dict) -> dict[str, str]:
    """Which frozen fields `observed` dropped, renamed, or retyped.

    Empty means compatible. A field that appeared is not in `frozen`, so it
    cannot show up here; one that was removed or renamed leaves its old name
    behind, and one that kept its name while changing type is the case a
    name-only reader would call compatible and a consumer would call broken.
    """
    faults = {}
    for name, kinds in frozen.items():
        if name not in observed:
            faults[name] = "gone"
        elif not isinstance(observed[name], kinds):
            faults[name] = f"is {type(observed[name]).__name__}"
    return faults


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

    Paths are a floor and fields are checked with their types: a result may
    publish a nested object nobody froze — additive, and invisible to a
    consumer that does not read it — but a frozen one may never stop being
    answered, lose a field, or keep a field's name while changing what it
    carries.
    """
    observed = nested_shapes(_answer(op)["result"])
    frozen = REQUIRED_NESTED_FIELDS[op]

    assert set(frozen) <= set(observed), (
        f"{op} stopped publishing a nested object a consumer parses: "
        f"{sorted(set(frozen) - set(observed))}"
    )
    for path, fields in frozen.items():
        for reported in observed[path]:
            assert broken_fields(fields, reported) == {}, (
                f"{op} broke a published field under {path}: "
                f"{broken_fields(fields, reported)}"
            )


def test_the_nested_reader_finds_every_container_and_can_tell_a_rename():
    """Asserted on a synthetic result, in every direction that matters.

    The gate was added because a real rename — `descriptors[].model_supported`
    — passed every other check in this area. It was then corrected in the other
    direction: asserting the set of paths *equal* made adding a nested object a
    failure, which is an additive change and must pass, or the rule would
    forbid the growth it was written to allow.
    """
    observed = nested_shapes({
        "count": 2,
        "provenance": {"state": "UNBOUND"},
        "descriptors": [{"model": "a"}, {"model_name": "b"}],
        "names": ["a", "b"],
    })

    assert set(observed) == {"provenance", "descriptors[]"}
    assert broken_fields({"model": str}, observed["descriptors[]"][0]) == {}
    assert broken_fields({"model": str}, observed["descriptors[]"][1]) == {
        "model": "gone",
    }
    assert broken_fields({"state": int}, observed["provenance"][0]) == {
        "state": "is str",
    }
    assert broken_fields({"state": str}, {"state": "UNBOUND", "added": 1}) == {}, (
        "a new field beside a frozen one is additive"
    )
