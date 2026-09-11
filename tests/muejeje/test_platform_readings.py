"""Every reading the device adapter can report, and what it refuses.

A reading is what `platform.device_descriptors` comes back with, and there are
five: the factory answered, there was no platform object, the object did not
offer the member, the call did not return, or it answered something that could
not be attributed. They stay distinct because a consumer acts differently on
each — collapsing them would leave "Packet Tracer would not talk to us"
indistinguishable from "Packet Tracer is not the interface we were written
against" (MJ-031).

**None of them is a V6 failure**, and **none names a cause the adapter cannot
see**: it reports the symptom rather than guessing at a privilege. The reverse
also holds, and is asserted here: an argument this adapter would not accept, or
a bug inside it, is *ours* — refused or reported as `ENGINE_EXCEPTION`, never
dressed up as something Packet Tracer did.

**What runs here, and what it establishes.** `PLATFORM_ABSENT` is real — under
Node there is no platform object. The others are driven with a stub that
answers well, badly, partially, or by throwing. All of it establishes what
*our* adapter does; none of it establishes anything about `9.0.1.0858`, so the
capability's live state is `PENDING_TARGET` (MJ-015).

Split out of `test_platform_adapter` when that module crossed its own line
budget, and split again when it crossed its own: what the adapter is *allowed
to be*, *which* reading it comes back with, and the *value rules* each reported
field is held to are three responsibilities. The value rules are
`test_platform_reading_values` (MJ-018, MJ-020).
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
    """The call did not return, and nothing here says why.

    What made a platform call fail is not something the adapter can see, so it
    reports the symptom and stops. In particular it names no privilege: which
    privilege any of these calls needs, and what a target does with a Script
    Module that has none, are two things this repository has not measured, so
    a reading that named one would be a claim about `9.0.1.0858` with nothing
    behind it (MJ-015, MJ-032). The thrown value never reaches the result
    either: a consumer that could read it would be depending on an internal
    (MJ-005).
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
def test_a_member_the_platform_does_not_offer_is_absent_not_a_failed_call():
    """Nothing was called, so nothing failed.

    `PLATFORM_CALL_FAILED` says the member was reached and did not return; a
    member that is not there says the interface is not the one this artifact
    was written against. Reporting the second as the first invents a refusal
    nobody performed (MJ-031).
    """
    no_devices_member = "var ipc = {hardwareFactory: function () { return {}; }};"
    result = dispatch_v6(_request(), prelude=no_devices_member)["result"]

    assert result["resolution"] == "UNAVAILABLE"
    assert result["unavailable_reason"] == "PLATFORM_MEMBER_ABSENT"
    assert result["descriptors"] == []


@requires_node
def test_a_defect_in_this_artifact_is_never_reported_as_a_platform_failure():
    """The boundary this adapter exists to keep: whose failure was it?

    `PLATFORM_CALL_FAILED` is an *observation about Packet Tracer* — the
    module asked and the call did not return — and a consumer may record it as
    one, on a target, as target evidence about this build (MJ-031). A bug in
    our own reading code that came back under that name would therefore be
    evidence about the platform that nothing platform ever produced, and it
    would be indistinguishable from the real thing.

    So only two things become an unavailable reading: a call this adapter made
    at its declared platform-call boundary, and an answer its own validators
    refused. Anything else is a defect in this artifact, and it leaves the
    adapter as it was thrown — for the dispatcher to report as
    `ENGINE_EXCEPTION`, which is the code that means the engine itself broke
    (MJ-022).
    """
    defect = "\nmuejejeReadingCount = function () { throw new Error('defect'); };"
    response = dispatch_v6(
        _request(), prelude=platform_stub(THREE_MODELS) + defect,
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "ENGINE_EXCEPTION"
    assert response["result"] is None
    assert "defect" not in json.dumps(response), (
        "the thrown value is engine-internal and never reaches a consumer"
    )
