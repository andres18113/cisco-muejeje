"""Relay closure: what Muejeje publishes as input, Muejeje admits as input.

    Any value or identifier Muejeje publishes as reusable input must be
    admissible by every operation that claims to consume it.

The runtime hands a consumer values whose *only* documented use is to be sent
back — a factory index that addresses a model, a `ModuleType` that asks whether
a model accepts it. A value published by one operation and refused by the one
that consumes it is a contract that contradicts itself: the consumer did
nothing wrong, and no amount of reading the two operations separately would
have told it so.

Two closures, and each one broke differently before this module existed:

* **`ModuleType`.** Descriptor discovery and the chassis walk published
  whatever whole number the platform answered, while
  `platform.module_type_support` admitted `0..65535`. The runtime emitted a
  platform-produced type and then refused that same value against a local
  bound the platform had never heard of.
* **Factory and workspace indexes.** A window could publish an index above the
  ceiling the consuming operations admitted, because the window's *first*
  index was bounded and its last was not.

**A bound is not the enemy; an incompatible pair of bounds is.** Execution
stays bounded by Muejeje's own resource limits (MJ-029) — how many entries one
window carries, how far one walk goes, how long a string may be. What closure
forbids is a *producer domain* and a *consumer domain* that disagree, so the
domains are declared once and both ends name the same declaration.

Nothing here is a claim about Packet Tracer. It is a claim about the contract
this artifact publishes, driven against a stub under Node (MJ-015).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available, platform_stub
from tests.muejeje.measure import js_code_only
from tests.muejeje.support import SCRIPT_ENGINE

# A model whose supported types sit at both ends of the published domain and
# outside the ceiling an earlier revision imposed, plus a chassis whose own
# type and slot types do the same. Every one of these is a value the platform
# is the only authority on, so publishing one and then refusing it is the
# defect this module exists to catch.
EXTREME_ROOT = (
    "{model: 'root', module_type: -1, hot_swappable: false,"
    " slot_types: [0, 70000], modules: []}"
)
EXTREME_MODELS = (
    "[{model: 'wide', type: 1, supported: true,"
    f" module_types: [-1, 0, 70000], root: {EXTREME_ROOT}}}]"
)

# A factory reporting far more models than this runtime addresses, so the
# ceiling under test is Muejeje's own and not the stub's. It stays inside
# `MAX_COUNT`, which bounds what count a reading will accept at all: a stub
# that tripped *that* bound would be testing a different refusal.
WIDE_FACTORY = 60000

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


def published_module_types(prelude: str) -> set[int]:
    """Every `ModuleType` the runtime hands a consumer, from both producers."""
    descriptors = _result(
        "platform.device_descriptors", {}, prelude,
    )["result"]["descriptors"]
    nodes = _result(
        "platform.module_descriptors", {"device_index": 0}, prelude,
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

@requires_node
def test_the_producers_publish_the_extreme_types_this_gate_needs():
    """Guards the closure gate below from passing because nothing was read.

    A stub whose types all sat inside the old ceiling would make the closure
    check vacuous, so what the producers actually published is asserted first.
    """
    published = published_module_types(platform_stub(EXTREME_MODELS))

    assert {-1, 0, 70000} <= published, (
        f"the producers did not publish the values under test: {sorted(published)}"
    )


@requires_node
@pytest.mark.parametrize("module_type", [-1, 0, 70000])
def test_a_published_module_type_is_admitted_by_the_operation_that_consumes_it(
    module_type: int,
):
    """The relay, driven end to end: publish a type, then send it back.

    `INVALID_ARGS` here means the runtime refused its own output. That is not
    a caller error — the caller read the value out of a reading this same
    artifact produced — so it is a defect in the contract, not in the request.
    """
    prelude = platform_stub(EXTREME_MODELS)
    assert module_type in published_module_types(prelude)

    response = _result(
        "platform.module_type_support",
        {"device_index": 0, "module_type": module_type},
        prelude,
    )

    assert response["ok"] is True, (
        f"the runtime published module type {module_type} and then refused it: "
        f"{response['error']}"
    )
    assert response["result"]["module_type"] == module_type
    assert response["result"]["resolution"] == "OBSERVED"


# ---------------------------------------------------------------------------
# A published index is one the consuming operations admit.
# ---------------------------------------------------------------------------

@requires_node
def test_no_reading_publishes_a_factory_index_above_the_addressable_ceiling():
    """A window's *last* index is bounded, not only its first.

    Bounding `offset` alone let a window whose offset sat at the ceiling
    publish `offset + limit - 1` above it — indexes the consuming operations
    would then refuse.
    """
    result = _result(
        "platform.device_descriptors",
        {"offset": _declared_bound("MAX_FACTORY_INDEX"), "limit": 8},
        platform_stub(EXTREME_MODELS, count=str(WIDE_FACTORY), dense=True),
    )["result"]
    ceiling = _declared_bound("MAX_FACTORY_INDEX")

    assert result["resolution"] == "OBSERVED"
    assert [d["device_index"] for d in result["descriptors"] if
            d["device_index"] > ceiling] == [], (
        "descriptor discovery published an index past its own ceiling"
    )
    assert result["max_device_index"] == ceiling, (
        "a consumer must be told where the addressable range ends rather than "
        "inferring it from a count"
    )
    assert result["window_truncated"] is True


@requires_node
@pytest.mark.parametrize(
    "op", ["platform.module_descriptors", "platform.module_type_support"],
)
def test_every_index_descriptor_discovery_publishes_is_one_a_consumer_may_send(
    op: str,
):
    """Both ends of the addressable range, against both consuming operations.

    The ceiling is the case that mattered: it is the index a paging consumer
    reaches last, and it was the one an unbounded window could publish while
    the consumer refused it.
    """
    prelude = platform_stub(EXTREME_MODELS, count=str(WIDE_FACTORY), dense=True)
    ceiling = _declared_bound("MAX_FACTORY_INDEX")
    published = [
        entry["device_index"]
        for entry in _result(
            "platform.device_descriptors",
            {"offset": ceiling, "limit": 1}, prelude,
        )["result"]["descriptors"]
    ]

    assert published == [ceiling], published
    for index in [0, ceiling]:
        args = {"device_index": index}
        if op == "platform.module_type_support":
            args["module_type"] = 0
        response = _result(op, args, prelude)
        assert response["ok"] is True, (
            f"{op} refused factory index {index}, which discovery publishes: "
            f"{response['error']}"
        )
        assert response["result"]["device_index"] == index


# ---------------------------------------------------------------------------
# Structural: one domain, named by both ends.
# ---------------------------------------------------------------------------

def _declared_bound(name: str) -> int:
    """A declared bound, read from the one file that defines them."""
    block = _body("platform_reading.js").split(
        "MUEJEJE_PLATFORM_LIMITS = {",
    )[1].split("};")[0]
    for line in js_code_only(block).splitlines():
        if line.strip().startswith(f"{name}:"):
            return int(line.split(":")[1].strip().rstrip(","))
    raise AssertionError(f"{name} is not a declared platform bound")


def test_the_module_type_domain_has_one_definition_and_two_named_ends():
    """Closure by construction, not by two numbers that happen to agree.

    A producer and a consumer that each wrote their own bound would be one
    edit away from disagreeing again, and the disagreement would look exactly
    like a working contract until a consumer relayed a value across it.
    """
    domain = ("MODULE_TYPE_MIN", "MODULE_TYPE_MAX")
    consumer = _body("platform_support.js")
    adapter = _body("platform_support_adapter.js")

    for bound in domain:
        assert f"MUEJEJE_PLATFORM_LIMITS.{bound}" in consumer, (
            f"the operation that consumes a ModuleType must name {bound}"
        )
        assert f"MUEJEJE_PLATFORM_LIMITS.{bound}" in adapter
    assert _declared_bound("MODULE_TYPE_MIN") < 0 < _declared_bound(
        "MODULE_TYPE_MAX",
    ), "the platform is the authority on which type values exist, not this list"


@pytest.mark.parametrize(
    "producer",
    ["platform_device_adapter.js", "platform_module_adapter.js"],
)
def test_every_producer_reads_a_module_type_through_the_domain_validator(
    producer: str,
):
    """A producer that validated a type its own way is a second domain.

    `muejejeReadingWholeNumber` is deliberately *not* enough here: it admits
    values the consumer cannot be given, which is exactly how the two ends
    drifted apart. A `ModuleType` goes through the validator that knows the
    published domain.
    """
    code = js_code_only(_body(producer))

    assert "muejejeReadingModuleType" in code, (
        f"{producer} publishes a ModuleType; it must read one through the "
        "validator that holds the published domain"
    )


def test_the_addressing_domains_are_declared_per_subject_and_named_by_both_ends():
    """A factory index and a workspace index are two enumerations.

    They are declared separately because they are different subjects, and each
    one is named by the reading that publishes it and by every operation that
    consumes it — so neither can be widened on one side alone.
    """
    factory = "MUEJEJE_PLATFORM_LIMITS.MAX_FACTORY_INDEX"
    workspace = "MUEJEJE_PLATFORM_LIMITS.MAX_WORKSPACE_INDEX"

    for logical in ("platform_discovery.js", "platform_modules.js",
                    "platform_support.js"):
        assert factory in _body(logical), f"{logical} must bound a factory index"
    assert workspace in _body("network_inventory.js")
    assert "MAX_OFFSET" not in _body("platform_reading.js"), (
        "one offset bound for two enumerations is how the domains drifted"
    )
