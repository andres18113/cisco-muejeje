"""Bounded V6 admission: what the kernel refuses before it reads a request.

V6 input used to be unbounded. A request could be any length, its
`operation_rid` and `op` any string, and `args` any JSON object of any shape,
so the cost of a refusal was decided by the caller rather than by the kernel.

**Every bound asserted here is Muejeje's own.** None of them is a Packet Tracer
limit: nothing in this repository has measured what PT's Script Engine accepts,
and a bound presented as the platform's would be a claim about `9.0.1.0858`
that no evidence supports (MJ-015, MJ-029). They exist so that refusing an
input costs one comparison instead of a full parse, and so that what a single
request can cost is decided before any handler runs.

The taxonomy does not grow to say so. A request that could not be read is
`MALFORMED_REQUEST`, an envelope that violates the envelope contract is
`INVALID_REQUEST`, and an operation given an argument it does not accept is
`INVALID_ARGS` — the same three codes as before, because a bound belongs to
those contracts rather than being a fourth kind of failure (MJ-022).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.measure import (
    engine_sources,
    relative,
)
from tests.muejeje.support import (
    SCRIPT_ENGINE,
)

VALID = {"v": 6, "operation_rid": "rid-bound", "op": "runtime.identify", "args": {}}

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _limits() -> dict:
    return dispatch_v6(json.dumps(VALID), report="MUEJEJE_V6_LIMITS")


def _request(**overrides) -> str:
    return json.dumps({**VALID, **overrides})


# ---------------------------------------------------------------------------
# The bounds are declared once, and they are ours.
# ---------------------------------------------------------------------------

def test_the_bounds_are_declared_in_exactly_one_kernel_file():
    """One owner. A second copy is a second answer to what is admitted."""
    owners = [
        relative(path) for path in engine_sources()
        if "MUEJEJE_V6_LIMITS = {" in path.read_text(encoding="utf-8")
    ]
    assert owners == ["muejeje_pts/script-engine/validation_v6.js"], owners


def test_the_validation_module_holds_no_operation_and_no_whitelist():
    body = (SCRIPT_ENGINE / "validation_v6.js").read_text(encoding="utf-8")
    assert "runtime.identify" not in body, (
        "admission validates envelopes; which operations exist is dispatch"
    )
    assert "muejejeV6OperationTable" not in body


@requires_node
def test_every_declared_bound_is_a_positive_whole_number():
    limits = _limits()

    assert limits, "the kernel declares no bound at all"
    for name, bound in limits.items():
        assert isinstance(bound, int) and bound > 0, f"{name}: {bound!r}"


# ---------------------------------------------------------------------------
# The request itself.
# ---------------------------------------------------------------------------

@requires_node
def test_an_oversized_request_is_refused_without_being_read():
    """Refused on length, so a hostile payload never reaches the parser.

    The reply carries a null `operation_rid` because nothing was parsed: the
    correlation id lives inside the bytes that were not read, and inventing
    one would correlate an answer to a request nobody could show us.
    """
    oversized = " " * (_limits()["REQUEST_CHARS"] + 1)
    response = dispatch_v6(oversized)

    assert response["ok"] is False
    assert response["error"]["code"] == "MALFORMED_REQUEST"
    assert response["operation_rid"] is None
    assert response["result"] is None


@requires_node
def test_a_request_just_inside_the_bound_is_still_read():
    """A bound that refuses what it admits is not a bound, it is a wall.

    JSON tolerates trailing whitespace, so this is a valid envelope padded to
    one character under the limit: the same request, at the edge.
    """
    envelope = _request()
    padded = envelope + " " * (_limits()["REQUEST_CHARS"] - len(envelope) - 1)
    response = dispatch_v6(padded)

    assert response["ok"] is True
    assert response["operation_rid"] == "rid-bound"


# ---------------------------------------------------------------------------
# operation_rid and op.
# ---------------------------------------------------------------------------

@requires_node
def test_an_over_long_operation_rid_is_an_invalid_envelope():
    long_rid = "r" * (_limits()["RID_CHARS"] + 1)
    response = dispatch_v6(_request(operation_rid=long_rid))

    assert response["error"]["code"] == "INVALID_REQUEST"
    assert response["operation_rid"] is None, "an id we will not accept is not an id"


@requires_node
def test_an_operation_rid_at_the_bound_is_admitted_and_echoed():
    exact = "r" * _limits()["RID_CHARS"]
    response = dispatch_v6(_request(operation_rid=exact))

    assert response["ok"] is True
    assert response["operation_rid"] == exact


@requires_node
@pytest.mark.parametrize("rid", [
    "rid\nsecond", "rid\u0000tail", "rid\u007f", "rid\t", "rid-caf\u00e9",
])
def test_an_unprintable_or_non_ascii_operation_rid_is_refused(rid: str):
    """A correlation id ends up in logs and evidence, so it stays printable.

    Printable ASCII is Muejeje's bound, not the platform's: a rid is compared,
    echoed and written down, and restricting it to one encoding is what keeps
    those three readings of the same id identical. A caller needing more
    carries its own id and correlates on both (MJ-023).
    """
    response = dispatch_v6(_request(operation_rid=rid))

    assert response["error"]["code"] == "INVALID_REQUEST"
    assert response["operation_rid"] is None


@requires_node
@pytest.mark.parametrize("op", [
    "o" * 65, "runtime.", ".identify", "Runtime.Identify", "runtime identify",
    "runtime.identify.now.and.forever", "runtime.identify\n", "ipc.network()",
])
def test_an_operation_name_that_is_not_a_bounded_dotted_name_is_refused(op: str):
    """Shape before whitelist: an unusable name is not an unknown operation.

    `UNKNOWN_OPERATION` says "the whitelist does not admit this name". A name
    the envelope could never carry has not reached the whitelist at all, and
    reporting it as unknown would send a caller looking for the operation.
    """
    response = dispatch_v6(_request(op=op))

    assert response["error"]["code"] == "INVALID_REQUEST"
    assert response["op"] is None


@requires_node
def test_a_well_shaped_name_the_whitelist_rejects_is_still_unknown():
    """The other direction, so the two refusals cannot collapse into one."""
    response = dispatch_v6(_request(op="runtime.reboot"))

    assert response["error"]["code"] == "UNKNOWN_OPERATION"
    assert response["op"] == "runtime.reboot"


# ---------------------------------------------------------------------------
# args: the envelope bounds the shape, the operation bounds the values.
# ---------------------------------------------------------------------------

@requires_node
def test_more_argument_fields_than_the_envelope_admits_is_an_invalid_envelope():
    """How many fields `args` may carry at all is the envelope's bound.

    Which of them an operation accepts is the operation's, and that answer is
    `INVALID_ARGS`. Keeping the two apart is what lets a caller tell "this
    envelope is too big to be read" from "this operation takes no arguments".
    """
    crowded = {f"field{index}": index for index in range(_limits()["ARG_COUNT"] + 1)}
    response = dispatch_v6(_request(args=crowded))

    assert response["error"]["code"] == "INVALID_REQUEST"


@requires_node
@pytest.mark.parametrize("value", [{"nested": 1}, [1, 2], [[]], {}])
def test_a_structured_argument_value_is_refused(value: object):
    """V6 arguments are scalars. A nested value has no bound of its own."""
    response = dispatch_v6(_request(args={"shape": value}))

    assert response["error"]["code"] == "INVALID_REQUEST"


@requires_node
def test_an_over_long_argument_string_is_refused():
    response = dispatch_v6(
        _request(args={"text": "x" * (_limits()["ARG_STRING_CHARS"] + 1)})
    )
    assert response["error"]["code"] == "INVALID_REQUEST"


@requires_node
def test_a_scalar_argument_reaches_the_operation_whitelist():
    """A well-shaped argument the operation does not declare is INVALID_ARGS."""
    response = dispatch_v6(_request(args={"text": "short"}))

    assert response["error"]["code"] == "INVALID_ARGS"
