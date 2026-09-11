"""Relay closure: what Muejeje publishes as input, Muejeje admits as input.

    Any value or identifier Muejeje publishes as reusable input must be
    admissible by every operation that claims to consume it.

The runtime hands a consumer values whose *only* documented use is to be sent
back — a factory index that addresses a model, a workspace index that addresses
a device, a `ModuleType` that asks whether a model accepts it. A value published
by one operation and refused by the one that consumes it is a contract that
contradicts itself: the consumer did nothing wrong, and no amount of reading the
two operations separately would have told it so.

**One domain, and it is fidelity rather than a ceiling.** Every index, count
and platform value is held to the exact-integer range — the whole numbers a
JSON value carries unchanged — by the reading that publishes it and by every
rule that admits it back, named from one declaration (MJ-029). Execution stays
bounded by the window, the walk and the string length, and none of those is an
address domain. Earlier domains broke closure twice: a `ModuleType` relay that
published any whole number while its consumer admitted `0..65535`, and index
relays under a ceiling of 4096 that a window at the ceiling could step past.

**Each test exercises the extreme it names.** A test that says it drives the end
of a domain publishes a value *at* that end and sends that same value back —
never a value merely outside some older, narrower bound. Where the platform
decides where an enumeration ends, the stub reports the largest count this
runtime can carry, so the last index published is the last that can exist.

Nothing here is a claim about Packet Tracer. It is a claim about the contract
this artifact publishes, driven against a stub under Node (MJ-015).
"""

from __future__ import annotations

import json
import re

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.measure import declared_platform_bound, js_code_only
from tests.muejeje.platform_stub import (
    EXACT_INTEGER_END,
    EXTREME_MODELS,
    IDENTITY_DEVICES,
    platform_stub,
)
from tests.muejeje.support import SCRIPT_ENGINE

EXACT_MAX = declared_platform_bound("EXACT_INTEGER_MAX")
EXACT_MIN = declared_platform_bound("EXACT_INTEGER_MIN")
# The last index that can exist: one below the largest count this runtime carries.
LAST_INDEX = EXACT_MAX - 1

# Every bound the platform readings declare, by what it limits. A ceiling on an
# address or a count is the third kind, and the one this module keeps out.
WORK_BOUNDS = {
    "MAX_FACTORY_WINDOW", "MAX_WORKSPACE_WINDOW", "MAX_MODULE_TYPES",
    "MAX_SLOTS", "MAX_MODULE_NODES", "MAX_MODULE_DEPTH",
    "MAX_MODEL_CHARS", "MAX_NAME_CHARS", "MAX_PORT_WINDOW",
}
FIDELITY_BOUNDS = {"EXACT_INTEGER_MIN", "EXACT_INTEGER_MAX"}
DECLARED_BOUND = re.compile(r"^\s*([A-Z][A-Z_]*):", re.MULTILINE)

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(op: str, args: dict) -> str:
    return json.dumps({
        "v": 6, "operation_rid": "rid-closure", "op": op, "args": args,
    })


def _result(op: str, args: dict, prelude: str) -> dict:
    return dispatch_v6(_request(op, args), prelude=prelude)


def _body(name: str) -> str:
    return (SCRIPT_ENGINE / name).read_text(encoding="utf-8")


def _widest_factory() -> str:
    """A factory reporting the largest count this runtime carries."""
    return platform_stub(EXTREME_MODELS, count=str(EXACT_MAX), dense=True)


def _widest_workspace() -> str:
    """A workspace of that size, whose devices answer identity too."""
    return platform_stub(
        EXTREME_MODELS, devices=IDENTITY_DEVICES,
        device_count=str(EXACT_MAX), dense=True,
    )


def published_module_types(prelude: str) -> set[int]:
    """Every `ModuleType` the runtime hands a consumer, from both producers."""
    descriptors = _result(
        "platform.device_descriptors", {}, prelude,
    )["result"]["descriptors"]
    nodes = _result(
        "platform.module_descriptors", {"factory_index": 0}, prelude,
    )["result"]["nodes"]

    published: set[int] = set()
    for entry in descriptors:
        published |= set(entry["supported_module_types"])
    for node in nodes:
        published.add(node["module_type"])
        published |= set(node["slot_types"])
    return published


# ---------------------------------------------------------------------------
# A published ModuleType is one the consuming operation admits.
# ---------------------------------------------------------------------------

def test_the_fixture_ends_are_the_declared_domain_ends():
    """Written out in the fixture, so it cannot silently follow a moved bound."""
    assert EXACT_INTEGER_END == EXACT_MAX == -EXACT_MIN


@requires_node
def test_the_producers_publish_both_ends_of_the_value_domain():
    """Guards the relay below from passing because nothing extreme was read."""
    published = published_module_types(platform_stub(EXTREME_MODELS))

    assert {EXACT_MIN, 0, EXACT_MAX} <= published, sorted(published)


@requires_node
@pytest.mark.parametrize("module_type", [EXACT_MIN, 0, EXACT_MAX])
def test_a_module_type_published_at_either_end_is_admitted_back(module_type: int):
    """The relay, driven end to end: publish a type, then send it back.

    `INVALID_ARGS` here means the runtime refused its own output. That is not
    a caller error — the caller read the value out of a reading this same
    artifact produced — so it is a defect in the contract, not in the request.
    """
    prelude = platform_stub(EXTREME_MODELS)
    assert module_type in published_module_types(prelude)

    response = _result(
        "platform.module_type_support",
        {"factory_index": 0, "module_type": module_type}, prelude,
    )

    assert response["ok"] is True, response["error"]
    assert response["result"]["module_type"] == module_type
    assert response["result"]["resolution"] == "OBSERVED"


@requires_node
@pytest.mark.parametrize("beyond", [EXACT_MIN - 1, EXACT_MAX + 1])
def test_just_past_either_end_neither_half_carries_the_value(beyond: int):
    """Both halves agree at the edge: not published, and not admitted."""
    produced = _result(
        "platform.device_descriptors", {},
        platform_stub(
            f"[{{model: 'm', type: 1, supported: true, module_types: [{beyond}]}}]"
        ),
    )["result"]
    consumed = _result(
        "platform.module_type_support",
        {"factory_index": 0, "module_type": beyond}, platform_stub(EXTREME_MODELS),
    )

    assert produced["unavailable_reason"] == "PLATFORM_ANSWER_UNUSABLE"
    assert consumed["error"]["code"] == "INVALID_ARGS"


# ---------------------------------------------------------------------------
# A published index is one the consuming operations admit, and read.
# ---------------------------------------------------------------------------

@requires_node
def test_the_last_factory_index_that_can_exist_is_published():
    """A window at the far end of the widest factory publishes exactly that index."""
    result = _result(
        "platform.device_descriptors", {"factory_offset": LAST_INDEX, "limit": 32},
        _widest_factory(),
    )["result"]

    assert result["resolution"] == "OBSERVED"
    assert result["available_count"] == EXACT_MAX
    assert [d["factory_index"] for d in result["descriptors"]] == [LAST_INDEX]
    assert result["window_truncated"] is False


@requires_node
@pytest.mark.parametrize(
    "op", ["platform.module_descriptors", "platform.module_type_support"],
)
@pytest.mark.parametrize("index", [0, LAST_INDEX])
def test_every_factory_index_discovery_publishes_is_read_by_its_consumers(
    op: str, index: int,
):
    """Admitted *and* read: the model at that index is the one that answers."""
    args = {"factory_index": index}
    if op == "platform.module_type_support":
        args["module_type"] = 0
    response = _result(op, args, _widest_factory())

    assert response["ok"] is True, response["error"]
    assert response["result"]["resolution"] == "OBSERVED"
    assert response["result"]["descriptor_present"] is True
    assert response["result"]["factory_index"] == index


@requires_node
def test_the_last_workspace_index_that_can_exist_is_published_and_read_back():
    """The same closure on the other enumeration, at the same end."""
    prelude = _widest_workspace()
    inventory = _result(
        "network.device_inventory", {"workspace_offset": LAST_INDEX, "limit": 8},
        prelude,
    )["result"]

    assert inventory["resolution"] == "OBSERVED"
    assert [d["workspace_index"] for d in inventory["devices"]] == [LAST_INDEX]
    for index in [0, LAST_INDEX]:
        response = _result(
            "network.device_identity", {"workspace_index": index}, prelude,
        )
        assert response["ok"] is True, response["error"]
        assert response["result"]["resolution"] == "OBSERVED"
        assert response["result"]["device_present"] is True
        assert response["result"]["workspace_index"] == index


@requires_node
@pytest.mark.parametrize(
    "op", ["platform.device_descriptors", "network.device_inventory"],
)
def test_a_window_may_start_at_the_end_of_the_domain_and_not_past_it(op: str):
    """The admitted end is answered as an empty window; one past it is refused."""
    factory = op.startswith("platform")
    stub = _widest_factory() if factory else _widest_workspace()
    start = "factory_offset" if factory else "workspace_offset"
    at_end = _result(op, {start: EXACT_MAX}, stub)
    past_end = _result(op, {start: EXACT_MAX + 1}, stub)

    assert at_end["ok"] is True
    assert at_end["result"]["descriptors" if factory else "devices"] == []
    assert at_end["result"]["window_truncated"] is False
    assert past_end["error"]["code"] == "INVALID_ARGS"


# ---------------------------------------------------------------------------
# Structural: one domain, named by both ends, and no ceiling on an address.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("operation", "bounds"), [
    ("platform_discovery.js", ("EXACT_INTEGER_MAX",)),
    ("platform_modules.js", ("EXACT_INTEGER_MAX",)),
    ("platform_support.js", ("EXACT_INTEGER_MIN", "EXACT_INTEGER_MAX")),
    ("network_inventory.js", ("EXACT_INTEGER_MAX",)),
    ("network_identity.js", ("EXACT_INTEGER_MAX",)),
])
def test_every_consumer_names_the_one_fidelity_declaration(
    operation: str, bounds: tuple[str, ...],
):
    """Closure by construction, not by two numbers that happen to agree."""
    for bound in bounds:
        assert f"MUEJEJE_PLATFORM_LIMITS.{bound}" in _body(operation), (
            f"{operation} admits a published value; it must name {bound}"
        )


@pytest.mark.parametrize("producer", [
    "platform_device_adapter.js", "platform_module_adapter.js",
    "platform_support_adapter.js", "network_identity_adapter.js",
])
def test_every_producer_reads_a_platform_value_through_the_domain_validator(
    producer: str,
):
    """A producer that validated a value its own way would be a second domain."""
    assert "muejejeReadingExactInteger" in js_code_only(_body(producer))


def test_the_validators_name_the_declaration_the_consumers_name():
    reading = js_code_only(_body("platform_reading.js"))

    for bound in FIDELITY_BOUNDS:
        assert f"MUEJEJE_PLATFORM_LIMITS.{bound}" in reading, bound


def test_every_declared_bound_limits_work_or_fidelity_and_nothing_else():
    """A ceiling on an address or a count is a third kind, and bounds no work.

    Reading position three trillion costs what reading position three costs, so
    such a ceiling only decides which positions this runtime refuses to look at.
    The last ones — 4096 on an index, 65536 on a count — made a large enough
    topology unreadable rather than paged.
    """
    block = _body("platform_reading.js").split("MUEJEJE_PLATFORM_LIMITS = {")[1]
    declared = set(DECLARED_BOUND.findall(js_code_only(block.split("};")[0])))

    assert declared == WORK_BOUNDS | FIDELITY_BOUNDS
    assert WORK_BOUNDS.isdisjoint(FIDELITY_BOUNDS)
