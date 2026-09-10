"""The one file that reaches Packet Tracer, and what it is allowed to be.

`platform_adapter.js` is the declared platform adapter (MJ-006, MJ-019): the
only packaged source that may name `ipc`, and the only one that does. This
module gates what that permission costs — no mutation, no kernel state, no
envelope, no dispatch, and no call this repository cannot cite — and it drives
the readings the adapter reports when the platform will not answer.

**What runs here, and what it establishes.** The unavailable branches are real:
under Node there is no platform object, so `PLATFORM_ABSENT` is the honest
reading and this suite observes it. The refused and unusable branches are
driven with a stub that misbehaves on purpose. All of it establishes what *our*
adapter does; none of it establishes anything about `9.0.1.0858`, whose factory
is a different implementation. No call below has ever reached the target, so
the capability's live state is `PENDING_TARGET` (MJ-015, MJ-031).
"""

from __future__ import annotations

import json
import re

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available, platform_stub
from tests.muejeje.support import SCRIPT_ENGINE

ADAPTER = "platform_adapter.js"
OPERATION = "platform.device_descriptors"

# Every platform method the adapter may call, as Cisco's installed IpcAPI
# reference for 9.0.1.0858 names it. An undocumented call is a guess, and
# Packet Tracer answers a guess with a bare `Invalid arguments for IPC call
# "X"` that says nothing about why (`AGENTS.md` rule 6).
DOCUMENTED_CALLS = {
    "hardwareFactory", "devices",
    "getAvailableDeviceCount", "getAvailableDeviceAt",
    "getModel", "getType", "isModelSupported",
    "getSupportedModuleTypeCount", "getSupportedModuleTypeAt",
}

# Every documented mutator on these interfaces begins with one of these verbs:
# `addSupportedModuleType`, `setModelSupportedFlag`, `removeModuleAt`,
# `create`. Matching the member-call shape is what makes "read-only" checkable
# rather than promised.
MUTATING_MEMBER = re.compile(r"\.\s*(?:set|add|remove|create|delete|clear)[A-Z]")

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
        "v": 6, "operation_rid": "rid-adapter", "op": OPERATION, "args": args,
    })


def _adapter_body() -> str:
    return (SCRIPT_ENGINE / ADAPTER).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Structural: what a declared adapter may be.
# ---------------------------------------------------------------------------

def test_the_adapter_is_the_only_file_that_reaches_the_platform():
    owners = [
        path.name for path in sorted(SCRIPT_ENGINE.glob("*.js"))
        if "ipc." in path.read_text(encoding="utf-8")
    ]
    assert owners == [ADAPTER], owners


def test_the_adapter_reads_no_kernel_state_and_answers_no_request():
    """It adapts. Shaping an answer and reading core belong to the kernel."""
    body = _adapter_body()
    for owned_elsewhere in (
        "MUEJEJE_CORE", "MUEJEJE_V6_ERRORS", "muejejeV6Ok", "muejejeV6Fail",
        "mcpDispatchV6", "muejejeV6OperationTable",
    ):
        assert owned_elsewhere not in body, owned_elsewhere


def test_the_adapter_calls_no_mutating_platform_member():
    """Read-only, asserted on the source and in both directions.

    A gate that matched nothing would be indistinguishable from a source that
    mutates nothing, so the pattern is exercised on a call that should trip it
    and one that should not.
    """
    assert MUTATING_MEMBER.search(_adapter_body()) is None
    assert MUTATING_MEMBER.search("descriptor.addSupportedModuleType(4);") is not None
    assert MUTATING_MEMBER.search("descriptor.getSupportedModuleTypeCount();") is None


def test_the_adapter_carries_no_numeric_cisco_enum_mirror():
    """MJ-014: the descriptor API is the authority, never a table of ours.

    A mirrored constant is correct only until Packet Tracer changes, and
    nothing in the repository would notice. The enumeration this adapter uses
    takes no `DeviceType` argument for exactly that reason, so no name from
    Cisco's enums has to appear anywhere in the artifact.
    """
    kernel = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(SCRIPT_ENGINE.glob("*.js"))
    )
    for mirrored in (
        "eRouter", "eSwitch", "eMultiLayerSwitch", "eAccessPoint",
        "ePtSwitchModule", "eIpPhonePowerAdapter", "getDescriptor",
    ):
        assert mirrored not in kernel, (
            f"{mirrored} would put a Cisco enum or a type-keyed lookup inside "
            "the artifact"
        )


# ---------------------------------------------------------------------------
# Executable: the readings when the platform will not answer.
# ---------------------------------------------------------------------------

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
def test_the_adapter_never_throws_out_of_the_engine():
    """Whatever the platform does, the caller gets a reading.

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


# ---------------------------------------------------------------------------
# Executable: only calls this repository can cite.
# ---------------------------------------------------------------------------

@requires_node
def test_the_adapter_asks_for_nothing_this_repository_cannot_cite():
    """The call log, compared against the documented getters.

    A grep over the source shows what is written; this shows what actually
    ran, which is the half a reader cannot check by eye.
    """
    called = dispatch_v6(
        _request(),
        prelude=platform_stub(THREE_MODELS),
        report="{result: JSON.parse(mcpDispatchV6(REQUEST)).result, calls: CALLS}",
    )

    assert called["result"]["resolution"] == "OBSERVED"
    assert set(called["calls"]) == DOCUMENTED_CALLS


@requires_node
def test_the_call_log_would_notice_an_undocumented_call():
    """Guards the gate above from passing because the log recorded nothing."""
    called = dispatch_v6(
        _request(),
        prelude=platform_stub(THREE_MODELS) + "\nlog('getUndocumentedThing');",
        report="CALLS",
    )

    assert set(called) - DOCUMENTED_CALLS == {"getUndocumentedThing"}
