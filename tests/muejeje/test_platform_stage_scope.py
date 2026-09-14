"""What a stage may never say, and what it must say on every reading.

Which member an unavailable reading stopped at is `test_platform_stage`. This is
the other half: the stage names a place and never a cause, it belongs to the
reading being shaped and to no other, and it exists on every platform reading
rather than on the one operation that needed it first (MJ-018, MJ-020).

Four ways a field like this goes wrong, one gate each:

* **naming a member nothing reached.** An absent platform called nothing, so a
  member in that result would be pure invention.
* **surviving its own reading.** The record is module-scoped, so without a reset
  a later reading would publish whatever an earlier one happened to end on.
* **escaping a reading.** A defect in this artifact produces no reading at all,
  and must leave no Packet Tracer member's name in the failure envelope
  (MJ-022).
* **becoming free text.** A member is read out of the boundary's own allowlist,
  so it can only ever be a call this artifact is permitted to make — which is
  what stops an explanation being written into it later.

Nothing here establishes anything about `9.0.1.0858` (MJ-015).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.measure import js_code_only
from tests.muejeje.platform_stub import CHASSIS_MODELS, linked_stub, platform_stub
from tests.muejeje.support import SCRIPT_ENGINE
from tests.muejeje.test_platform_allowlist import CITED_CALLS
from tests.muejeje.test_platform_stage import (
    PLATFORM_OPERATIONS,
    STAGE_FIELDS,
    reading,
    request_for,
    stage_of,
)

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


# ---------------------------------------------------------------------------
# A stage only exists where a reading stopped.
# ---------------------------------------------------------------------------

@requires_node
@pytest.mark.parametrize("prelude", ["", "var ipc = null;"], ids=["undefined", "null"])
def test_no_platform_object_reached_no_member_and_says_so(prelude: str):
    """Nothing was called, so no member may be named.

    A stage here would be the worst kind: a member that was never reached,
    standing in a result whose own reason says the platform was not there.
    """
    result = reading(prelude)

    assert result["unavailable_reason"] == "PLATFORM_ABSENT"
    assert stage_of(result) == (None, None)


@requires_node
def test_an_observed_reading_stopped_nowhere():
    """The last member a reading called successfully is not where it stopped."""
    result = reading(platform_stub(CHASSIS_MODELS))

    assert result["resolution"] == "OBSERVED"
    assert stage_of(result) == (None, None)


@requires_node
def test_a_reading_never_publishes_the_member_a_previous_one_stopped_at():
    """Two readings in one evaluation, and the second owes nothing to the first.

    Without a reset where a reading begins, an absent platform would come back
    naming a member nothing had asked it for — which is the same class of
    mistake as reporting our own defect as a platform failure.
    """
    request = request_for("platform.device_descriptors")
    both = dispatch_v6(
        request,
        prelude=platform_stub(CHASSIS_MODELS),
        report="(function () {"
               " var first = JSON.parse(mcpDispatchV6(REQUEST)).result;"
               " ipc = null;"
               " var second = JSON.parse(mcpDispatchV6(REQUEST)).result;"
               " return {first: first, second: second};"
               " }())",
    )

    assert both["first"]["resolution"] == "OBSERVED"
    assert stage_of(both["first"]) == (None, None)
    assert both["second"]["unavailable_reason"] == "PLATFORM_ABSENT"
    assert stage_of(both["second"]) == (None, None)


@requires_node
def test_an_engine_exception_publishes_no_reading_and_so_no_stage():
    """A defect in this artifact is still not a platform observation (MJ-022).

    The stage is a field of a reading, and a defect produces no reading — so the
    failure envelope carries no member, and a bug inside an adapter cannot leave
    a Packet Tracer member's name in a result.
    """
    defect = "\nmuejejeReadingCount = function () { throw new Error('defect'); };"
    response = dispatch_v6(
        request_for(), prelude=platform_stub(CHASSIS_MODELS) + defect,
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "ENGINE_EXCEPTION"
    assert response["result"] is None
    for field in STAGE_FIELDS:
        assert field not in json.dumps(response), field


# ---------------------------------------------------------------------------
# One contract, over every platform reading.
# ---------------------------------------------------------------------------

@requires_node
@pytest.mark.parametrize("op", sorted(PLATFORM_OPERATIONS))
def test_every_platform_reading_publishes_the_stage_pair(op: str):
    """Not one operation's private field.

    The next run exercises the whole read-only surface with the full privilege
    set, and an unexplained `UNAVAILABLE` on any of these would otherwise need
    its own cycle to locate.
    """
    observed = reading(linked_stub(), op)
    absent = reading("", op)

    for field in STAGE_FIELDS:
        assert field in observed, f"{op}: {field}"
        assert field in absent, f"{op}: {field}"
    assert stage_of(absent) == (None, None)


@requires_node
@pytest.mark.parametrize("op", sorted(PLATFORM_OPERATIONS))
def test_a_published_member_is_always_one_the_boundary_admits(op: str):
    """A stage is an admitted `Interface.member` or nothing.

    A platform object offering neither root is what makes every one stop at a
    member: `fail` refuses only the factory, and the workspace readings would
    answer straight through it.
    """
    refused = reading("var ipc = {};", op)

    assert refused["resolution"] == "UNAVAILABLE"
    assert refused["unavailable_reason"] == "PLATFORM_MEMBER_ABSENT"
    assert refused["unavailable_member"] in CITED_CALLS, refused


def test_the_stage_is_recorded_by_the_boundary_and_nowhere_else():
    """Structural: one writer, so a stage can only be a call that was made.

    An adapter that could set it would be able to name a member it never
    reached, which is the same failure as an adapter asserting a receiver's
    interface (MJ-031).
    """
    writers = sorted(
        path.name for path in SCRIPT_ENGINE.glob("*.js")
        if "muejejeReadingStage(" in js_code_only(path.read_text(encoding="utf-8"))
    )
    definers = sorted(
        path.name for path in SCRIPT_ENGINE.glob("*.js")
        if "function muejejeReadingStage(" in path.read_text(encoding="utf-8")
    )

    assert definers == ["050_platform_reading.js"]
    assert writers == ["050_platform_reading.js", "060_platform_adapter.js"], (
        "the boundary records where a reading stopped; nothing else may"
    )
