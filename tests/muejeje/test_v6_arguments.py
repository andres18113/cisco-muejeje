"""What an operation's own arguments must be, once the envelope is admitted.

`test_v6_admission` covers the envelope: what a caller's string may be at all,
and the bounds every request is held to. This module covers the other half of
admission — the rules a *particular* operation declares for the arguments it
names, which is what `040_arguments_v6.js` owns (MJ-029).

Driven on a synthetic operation, so the mechanism is tested before an operation
depends on it: whitelisting an argument by name says nothing about its value,
and an unimplemented rule must refuse rather than admit.

Split out of `test_v6_admission` when that module crossed its own line budget,
along the same line the sources split on (MJ-018, MJ-020).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available

VALID = {"v": 6, "operation_rid": "rid-bound", "op": "runtime.identify", "args": {}}

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _limits() -> dict:
    return dispatch_v6(json.dumps(VALID), report="MUEJEJE_V6_LIMITS")


def _request(**overrides) -> str:
    return json.dumps({**VALID, **overrides})

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(**overrides) -> str:
    return json.dumps({**VALID, **overrides})


DECLARE_INTEGER_ARG = (
    "muejejeV6OperationTable()['runtime.identify'].args ="
    " {depth: {kind: 'integer', min: 0, max: 4}};"
)


@requires_node
@pytest.mark.parametrize(("depth", "code"), [
    (2, None), (0, None), (4, None),
    (5, "INVALID_ARGS"), (-1, "INVALID_ARGS"), (1.5, "INVALID_ARGS"),
])
def test_a_declared_integer_argument_is_bounded_by_its_rule(
    depth: object, code: str | None,
):
    """The rule is driven on a synthetic operation, before one declares it.

    Whitelisting an argument by name says nothing about its value, so an
    operation that accepted `depth` would accept `depth: 1e12` until a rule
    bounded it. The rule is exercised here so the first operation that needs
    one inherits a tested mechanism rather than an untested promise.
    """
    response = dispatch_v6(
        _request(args={"depth": depth}), prelude=DECLARE_INTEGER_ARG,
    )
    if code is None:
        assert response["ok"] is True, response
    else:
        assert response["ok"] is False
        assert response["error"]["code"] == code


@requires_node
@pytest.mark.parametrize(("args", "ok"), [
    ({"depth": 2}, True), ({}, False), ({"depth": 9}, False),
])
def test_a_required_argument_is_refused_by_its_absence(args: dict, ok: bool):
    """Both directions, on the same synthetic operation.

    An operation declares an argument required only when no default would be
    honest — where every value is a different question. Its absence is
    `INVALID_ARGS`, the code that already means "a whitelisted operation given
    arguments it does not support"; it is never a reading, because nothing was
    read, and never a new code, because the taxonomy does not grow (MJ-029).
    """
    response = dispatch_v6(
        _request(args=args),
        prelude=(
            "muejejeV6OperationTable()['runtime.identify'].args ="
            " {depth: {kind: 'integer', required: true, min: 0, max: 4}};"
        ),
    )

    assert response["ok"] is ok, response
    if not ok:
        assert response["error"]["code"] == "INVALID_ARGS"


@requires_node
def test_an_argument_nobody_required_stays_optional():
    """The default case is unchanged: a rule with no `required` admits absence."""
    response = dispatch_v6(_request(args={}), prelude=DECLARE_INTEGER_ARG)

    assert response["ok"] is True, response


@requires_node
def test_an_argument_rule_the_kernel_cannot_read_refuses_the_argument():
    """Fail closed. An unimplemented rule admits nothing, it refuses."""
    response = dispatch_v6(
        _request(args={"depth": 1}),
        prelude=(
            "muejejeV6OperationTable()['runtime.identify'].args ="
            " {depth: {kind: 'colour', min: 0, max: 4}};"
        ),
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGS"


# ---------------------------------------------------------------------------
# A bound is never reported as the engine breaking.
# ---------------------------------------------------------------------------

@requires_node
def test_no_bound_is_ever_reported_as_an_engine_exception():
    """Nothing went wrong inside the engine when a request was too big."""
    limits = _limits()
    refusals = [
        " " * (limits["REQUEST_CHARS"] + 1),
        _request(operation_rid="r" * (limits["RID_CHARS"] + 1)),
        _request(op="o" * (limits["OP_CHARS"] + 1)),
        _request(args={"text": "x" * (limits["ARG_STRING_CHARS"] + 1)}),
        _request(args={f"field{index}": 1 for index in range(limits["ARG_COUNT"] + 1)}),
    ]
    for request in refusals:
        response = dispatch_v6(request)
        assert response["ok"] is False
        assert response["error"]["code"] != "ENGINE_EXCEPTION", request[:40]
