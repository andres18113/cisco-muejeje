"""Every reading the platform adapter can report, and what it refuses.

A reading is what `platform.device_descriptors` comes back with, and there are
four of them: the factory answered, there was no platform object, the call did
not return, or it answered something that could not be attributed. They stay
four distinct facts because a consumer acts differently on each — and because
collapsing them would leave "Packet Tracer would not talk to us"
indistinguishable from "Packet Tracer said something we cannot read" (MJ-031).

**None of them is a V6 failure.** The request was admissible; the answer is
that no reading was obtained. And **none of them names a cause the adapter
cannot see**: a denied privilege is one cause of a call that did not return,
and the adapter reports the symptom rather than guessing the cause.

**What runs here, and what it establishes.** `PLATFORM_ABSENT` is real — under
Node there is no platform object, so that is the honest reading and this suite
observes it. The other three are driven with a stub that answers well, badly,
or by throwing. All of it establishes what *our* adapter does; none of it
establishes anything about `9.0.1.0858`, whose hardware factory is a different
implementation, so the capability's live state is `PENDING_TARGET` (MJ-015).

Split out of `test_platform_adapter` when that module crossed its own line
budget: what the adapter is *allowed to be* and what it *reports* are two
responsibilities (MJ-018, MJ-020).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available, platform_stub

OPERATION = "platform.device_descriptors"

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
        "v": 6, "operation_rid": "rid-reading", "op": OPERATION, "args": args,
    })


@requires_node
def test_no_platform_object_is_an_observation_not_a_failure():
    """The honest reading under Node, and the one a denied module also needs.

    `ok: true` on purpose: the operation succeeded in answering "there is no
    platform to read here". A V6 failure would say the request was
    inadmissible, which it was not.
    """
    response = dispatch_v6(_request())

    assert response["ok"] is True
    assert response["error"] is None
    assert response["result"]["resolution"] == "UNAVAILABLE"
    assert response["result"]["unavailable_reason"] == "PLATFORM_ABSENT"
    assert response["result"]["available_count"] is None
    assert response["result"]["descriptors"] == []


@requires_node
def test_a_refused_platform_call_is_reported_without_its_error():
    """A denied privilege is one cause of this, and it is not named as one.

    The adapter cannot tell a denied privilege from any other engine-side
    refusal, so it reports that the call did not return and stops there. The
    thrown value never reaches the result: a consumer that could read it would
    be depending on an internal (MJ-005).
    """
    result = dispatch_v6(
        _request(), prelude=platform_stub(THREE_MODELS, fail=True),
    )["result"]

    assert result["resolution"] == "UNAVAILABLE"
    assert result["unavailable_reason"] == "PLATFORM_CALL_FAILED"
    assert "refused this call" not in json.dumps(result)


@requires_node
@pytest.mark.parametrize("count", ["'many'", "-1", "1.5", "999999999"])
def test_an_answer_that_cannot_be_attributed_is_its_own_reason(count: str):
    """It answered, and the answer is unusable. Different from not answering.

    Collapsing the two would leave a consumer unable to tell "Packet Tracer
    would not talk to us" from "Packet Tracer said something we cannot read",
    and those need different next steps.
    """
    result = dispatch_v6(
        _request(), prelude=platform_stub(THREE_MODELS, count=count),
    )["result"]

    assert result["resolution"] == "UNAVAILABLE"
    assert result["unavailable_reason"] == "PLATFORM_ANSWER_UNUSABLE"


@requires_node
def test_a_missing_descriptor_inside_the_window_is_unusable_not_empty():
    """A hole is not an absence. Reporting fewer models would invent an answer."""
    result = dispatch_v6(_request(), prelude=platform_stub("[]", count="3"))["result"]

    assert result["unavailable_reason"] == "PLATFORM_ANSWER_UNUSABLE"


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
def test_every_adapter_bound_is_a_positive_whole_number():
    """The bounds are ours, and each one has to be a usable number.

    Asserted the same way as the V6 admission limits, because a bound that is
    `undefined` compares false against everything and silently admits what it
    was written to refuse.
    """
    limits = dispatch_v6(_request(), report="MUEJEJE_PLATFORM_LIMITS")

    assert limits, "the adapter declares no bound at all"
    for name, bound in limits.items():
        assert isinstance(bound, int) and bound > 0, f"{name}: {bound!r}"


@requires_node
def test_whatever_the_platform_does_the_caller_still_gets_a_reading():
    """Every platform-shaped outcome is an answer, not an exception.

    An uncaught error inside a Script Engine call is not something a consumer
    can correlate, diagnose or retry, and in Packet Tracer it opens a modal.
    """
    for prelude in (
        "",
        platform_stub(THREE_MODELS, fail=True),
        platform_stub(THREE_MODELS, count="'many'"),
        "var ipc = null;",
        "var ipc = {hardwareFactory: function () { return null; }};",
    ):
        response = dispatch_v6(_request(), prelude=prelude)
        assert response["ok"] is True, prelude[:40]
        assert response["result"]["resolution"] in {"OBSERVED", "UNAVAILABLE"}


@requires_node
def test_a_defect_in_this_artifact_is_never_reported_as_a_platform_failure():
    """The boundary this adapter exists to keep: whose failure was it?

    `PLATFORM_CALL_FAILED` is an *observation about Packet Tracer* — the
    module asked and the call did not return — and a consumer may record it as
    one, on a target, as the reading that says a privilege is missing
    (MJ-031, MJ-032). A bug in our own reading code that came back under that
    name would therefore be evidence about the platform that nothing platform
    ever produced, and it would be indistinguishable from the real thing.

    So only two things become an unavailable reading: a call this adapter made
    at its declared platform-call boundary, and an answer its own validators
    refused. Anything else is a defect in this artifact, and it leaves the
    adapter as it was thrown — for the dispatcher to report as
    `ENGINE_EXCEPTION`, which is the code that means the engine itself broke
    (MJ-022).
    """
    defect = "\nmuejejeAdapterCount = function () { throw new Error('defect'); };"
    response = dispatch_v6(
        _request(), prelude=platform_stub(THREE_MODELS) + defect,
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "ENGINE_EXCEPTION"
    assert response["result"] is None
    assert "defect" not in json.dumps(response), (
        "the thrown value is engine-internal and never reaches a consumer"
    )
