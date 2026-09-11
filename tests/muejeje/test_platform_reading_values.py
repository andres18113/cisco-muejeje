"""The value rules every reported field of a platform reading is held to.

`test_platform_readings` decides *which* of the five readings comes back, and
whose failure it was. This module covers the other half: what a field has to be
before it is reported at all, and what the adapter does with a number it should
never have been handed.

Three rules, and they are not the same rule:

* **A badly answered field makes the whole reading unusable**, not partial.
  Reporting three fields of a model and dropping the fourth would look like an
  answer about the platform rather than about our inability to read it.
* **A bound is a bound and not a wall.** Every length and ceiling here is
  Muejeje's own (MJ-029), so each is driven from both sides — refused past it,
  answered at it — and a bound that is `undefined` compares false against
  everything and silently admits what it was written to refuse.
* **An argument outside the adapter's own bounds is a defect of ours.** V6
  admission has already refused anything outside an operation's rule, and an
  operation defaults an argument nobody sent, so such a value came from our own
  code. Clamping it would read a different window and report the result as an
  observation about Packet Tracer (MJ-022, MJ-031).

Everything here runs against a stub under Node: it establishes what our
validators do, and nothing about `9.0.1.0858` (MJ-015).

Split out of `test_platform_readings` when that module crossed its own line
budget (MJ-018, MJ-020).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.platform_stub import platform_stub

OPERATION = "platform.device_descriptors"

# Declared bounds that may be negative: the floor of a *value* domain rather
# than a ceiling on work. Named here so a second one cannot arrive unnoticed —
# a bound that stops being a limit on what one call does is a bound whose
# reason has to be restated.
SIGNED_VALUE_BOUNDS = {"MODULE_TYPE_MIN"}

THREE_MODELS = (
    "[{model: '2960-24TT', type: 1, supported: true, module_types: [18]},"
    " {model: '', type: 7, supported: false, module_types: [6, 18]},"
    " {model: '3650-24PS', type: 16, supported: true, module_types: [4, 18]}]"
)

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request(**args) -> str:
    return json.dumps({
        "v": 6, "operation_rid": "rid-reading-value", "op": OPERATION,
        "args": args,
    })


@requires_node
@pytest.mark.parametrize(("field", "value"), [
    ("model", "7"),
    ("model", "null"),
    ("model", "'x'.repeat(257)"),
    ("type", "'1'"),
    ("type", "1.5"),
    ("type", "null"),
    ("supported", "'true'"),
    ("supported", "1"),
    ("module_types", "['18']"),
])
def test_every_field_of_a_descriptor_is_checked_before_it_is_reported(
    field: str, value: str,
):
    """One malformed field makes the whole reading unusable, not partial.

    Each of these is a branch in the adapter's own validators, and each was
    written before anything drove it. A validator nothing exercises is a
    validator that can be silently inverted — and the failure would surface as
    a plausible-looking descriptor carrying a value nobody checked.

    A partial descriptor is deliberately not an option: reporting three fields
    of a model and dropping the fourth would look like an answer about the
    platform rather than about our inability to read it.
    """
    spec = {
        "model": "'2960-24TT'", "type": "1",
        "supported": "true", "module_types": "[18]",
    }
    spec[field] = value
    inner = ", ".join(f"{name}: {literal}" for name, literal in spec.items())

    result = dispatch_v6(_request(), prelude=platform_stub(f"[{{{inner}}}]"))["result"]

    assert result["resolution"] == "UNAVAILABLE"
    assert result["unavailable_reason"] == "PLATFORM_ANSWER_UNUSABLE"
    assert result["descriptors"] == []

@requires_node
def test_a_model_name_at_its_bound_is_still_a_readable_answer():
    """The other side of the length bound, so it is a bound and not a wall.

    The bound is a length of its own — Muejeje's, like every other number in
    the adapter (MJ-029) — rather than the node-count ceiling reused as one.
    """
    result = dispatch_v6(
        _request(),
        prelude=platform_stub(
            "[{model: 'x'.repeat(256), type: 1, supported: true, module_types: [18]}]"
        ),
    )["result"]

    assert result["resolution"] == "OBSERVED"
    assert len(result["descriptors"][0]["model"]) == 256

@requires_node
def test_every_adapter_bound_is_a_usable_whole_number():
    """The bounds are ours, and each one has to be a usable number.

    Asserted the same way as the V6 admission limits, because a bound that is
    `undefined` compares false against everything and silently admits what it
    was written to refuse.

    A ceiling on work is positive; the floor of a *value* domain need not be.
    `MODULE_TYPE_MIN` is the one bound that is legitimately negative, because a
    type value is the platform's and the platform is the authority on its sign.
    Requiring it to be positive would be the local ceiling that broke relay
    closure, in another spelling (MJ-029, `test_relay_closure`).
    """
    limits = dispatch_v6(_request(), report="MUEJEJE_PLATFORM_LIMITS")

    assert limits, "the adapter declares no bound at all"
    for name, bound in limits.items():
        assert isinstance(bound, int), f"{name}: {bound!r}"
        if name not in SIGNED_VALUE_BOUNDS:
            assert bound > 0, f"{name}: {bound!r}"
    assert limits["MODULE_TYPE_MIN"] < 0 < limits["MODULE_TYPE_MAX"], (
        "the published type domain must admit what the platform may answer"
    )

@requires_node
@pytest.mark.parametrize(("offset", "limit"), [
    ("-1", "4"), ("0", "0"), ("0", "33"), ("5000", "4"), ("'0'", "4"),
    ("1.5", "4"), ("0", "null"),
])
def test_an_argument_this_adapter_would_not_accept_is_a_defect_not_a_clamp(
    offset: str, limit: str,
):
    """The window is checked, never clamped.

    A value outside these bounds cannot have come from a caller: V6 admission
    refuses that, and the operation defaults an argument nobody sent. So it
    came from our own code, and reading a *different* window and reporting the
    result would answer a question nobody asked — as an observation about
    Packet Tracer, which is the failure mode this whole boundary exists for.
    """
    observed = dispatch_v6(
        _request(),
        prelude=platform_stub(THREE_MODELS),
        report=(
            "(function () {"
            f"  try {{ return {{read: muejejeAdapterDeviceDescriptors({offset}, {limit})}}; }}"
            "  catch (thrown) { return {refused: String(thrown)}; }"
            "}())"
        ),
    )

    assert "read" not in observed, "a bad argument was answered instead of refused"
    assert "PLATFORM_" not in observed["refused"], (
        "an argument defect is ours, and never a platform reading"
    )

@requires_node
def test_the_window_this_operation_asks_for_is_still_answered():
    """The other direction: the check is a bound, not a wall."""
    observed = dispatch_v6(
        _request(),
        prelude=platform_stub(THREE_MODELS),
        report="muejejeAdapterDeviceDescriptors(0, 32)",
    )

    assert observed["resolution"] == "OBSERVED"
    assert observed["offset"] == 0 and observed["limit"] == 32
