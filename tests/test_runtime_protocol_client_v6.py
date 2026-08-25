"""Phase 1B-OFFLINE: encoder to parser through an injected send seam.

What this establishes
---------------------
That one `runtime.identify` attempt encodes, sends **once** through a callable
handed in from outside, keeps a transport non-response out of the protocol
layer, and returns the parser's classification unchanged. Nothing more.

What it does not establish
--------------------------
Every claim about a real channel or a real Script Engine stays
UNVERIFIED_UNTIL_PHASE_1B_LIVE. The seam here is a Python callable written in
this file. It is not HTTP, it is not the file bridge, and it is not Packet
Tracer: a fake that answers correctly proves the orchestration, and proves
nothing whatsoever about a responder that was never asked.

The fakes read the operation identity **out of the payload**, the way an engine
would have to. Nothing below is told a rid or an op out of band, so a client
that sent one identity and correlated on another would be caught here rather
than agreed with.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import sys
from dataclasses import replace

import pytest

from src.packet_tracer_mcp.infrastructure.execution import runtime_protocol_client
from src.packet_tracer_mcp.infrastructure.execution.runtime_operation_encoder import (
    RUNTIME_IDENTIFY,
    encode_runtime_identify,
)
from src.packet_tracer_mcp.infrastructure.execution.runtime_protocol import (
    ProtocolParseState,
    RuntimeErrorCode,
    new_operation_rid,
    parse_runtime_result,
)
from src.packet_tracer_mcp.infrastructure.execution.runtime_protocol_client import (
    RuntimeProtocolAttempt,
    RuntimeProtocolClient,
)

# Imported from the modules that own them rather than copied, so a change there
# starts being enforced here on the same commit.
from tests.test_runtime_protocol_v6_compatibility import _imported_modules
from tests.test_transport_mutation_containment import _MUTATING_PT_APIS

REPO = pathlib.Path(__file__).resolve().parents[1]
CLIENT_MODULE = (
    REPO / "src" / "packet_tracer_mcp" / "infrastructure" / "execution"
    / "runtime_protocol_client.py"
)

#: A distinctive budget, so "passed through unchanged" is an observation rather
#: than a coincidence with somebody's default.
BUDGET = 4.5

OTHER_OP = "some.other.operation"


# --------------------------------------------------------------- fakes -----


class RecordingSeam:
    """A `send_and_wait` that records every call and answers from a script."""

    def __init__(self, responder) -> None:
        self.calls: list[tuple[str, float]] = []
        self._responder = responder

    def __call__(self, payload: str, timeout: float) -> str | None:
        self.calls.append((payload, timeout))
        return self._responder(payload)


def answers(document):
    """A responder that returns the same document whatever it is sent."""
    return lambda payload: document


def embedded_rid(payload: str) -> str:
    found = re.search(r'operation_rid:"([0-9a-f]{32})"', payload)
    assert found is not None, "the payload carries no operation_rid"
    return found.group(1)


def embedded_op(payload: str) -> str:
    found = re.search(r'op:"([a-z.]+)"', payload)
    assert found is not None, "the payload carries no op"
    return found.group(1)


def conforming(
    payload: str,
    *,
    operation_rid: str | None = None,
    op: str | None = None,
    session_id: str | None = "ses_from_the_engine",
    extension_version: str | None = None,
) -> str:
    """What a conforming V6 responder would return for this payload."""
    return json.dumps(
        {
            "v": 6,
            "operation_rid": embedded_rid(payload)
            if operation_rid is None
            else operation_rid,
            "op": embedded_op(payload) if op is None else op,
            "status": "ok",
            "runtime": {
                "session_id": session_id,
                "session_storage": "script_engine_global",
                "session_minted_by": "mcp_server",
                "extension_version": extension_version,
                "protocol_version": 6,
            },
            "observed": {"pt_file_version": "9.0.1.0858", "device_count": 12},
            "error": None,
        }
    )


def identify_through(responder):
    seam = RecordingSeam(responder)
    client = RuntimeProtocolClient(seam, timeout_seconds=BUDGET)

    return client.identify(), seam


# ------------------------------------------------------- 1/2/3. the send ---


def test_one_identify_sends_exactly_once():
    """No retry, no replay, no second channel. One attempt, one dispatch."""
    _, seam = identify_through(lambda payload: conforming(payload))

    assert len(seam.calls) == 1


def test_the_payload_sent_is_the_encoded_payload_unaltered():
    attempt, seam = identify_through(lambda payload: conforming(payload))

    sent_payload, _ = seam.calls[0]
    assert sent_payload == attempt.operation.payload


def test_the_timeout_budget_reaches_the_seam_unchanged():
    """The protocol layer does not interpret the budget; it hands it over."""
    _, seam = identify_through(lambda payload: conforming(payload))

    _, sent_timeout = seam.calls[0]
    assert sent_timeout == BUDGET


@pytest.mark.parametrize("budget", [None, "5", True, -1, -0.5])
def test_a_dishonest_timeout_budget_is_refused_at_construction(budget):
    with pytest.raises(ValueError):
        RuntimeProtocolClient(RecordingSeam(answers(None)), timeout_seconds=budget)


NON_FINITE_BUDGETS = [
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
]


@pytest.mark.parametrize("budget", NON_FINITE_BUDGETS)
def test_a_non_finite_timeout_budget_is_refused(budget):
    """A value that is not a finite duration is not a budget.

    NaN and positive infinity are both floats, and neither compares `< 0`, so a
    sign test alone lets both through -- and a caller would then hand a channel
    a wait it can never satisfy. `live_bridge.py:74` already refuses them with
    `math.isfinite`; the *property* is reused here, the function is not, because
    importing the HTTP transport for a one-line check would break the
    Phase-1B-OFFLINE dependency boundary.
    """
    with pytest.raises(ValueError):
        RuntimeProtocolClient(RecordingSeam(answers(None)), timeout_seconds=budget)


@pytest.mark.parametrize("budget", NON_FINITE_BUDGETS)
def test_a_refused_budget_never_reaches_the_seam(budget):
    """Refused at construction, so nothing was dispatched to find out."""
    seam = RecordingSeam(answers(None))

    with pytest.raises(ValueError):
        RuntimeProtocolClient(seam, timeout_seconds=budget)

    assert seam.calls == []


@pytest.mark.parametrize("budget", [0, 0.0, 1, 2.5, 30.0])
def test_a_finite_non_negative_budget_is_accepted_and_passed_through(budget):
    """Zero stays allowed, and an accepted budget reaches the seam unaltered.

    `type` as well as value: `bounded_result_wait` normalises through `float()`
    before clamping, and this layer does neither. What the caller chose is what
    the channel is asked for.
    """
    seam = RecordingSeam(lambda payload: conforming(payload))
    client = RuntimeProtocolClient(seam, timeout_seconds=budget)

    client.identify()

    _, sent_timeout = seam.calls[0]
    assert sent_timeout == budget
    assert type(sent_timeout) is type(budget)


def test_no_ceiling_is_imposed_on_an_accepted_budget():
    """`bounded_result_wait` clamps to a maximum because it owns an HTTP result
    queue and measured one. This layer owns no channel and has measured nothing,
    so it imposes no ceiling and no clamp."""
    seam = RecordingSeam(lambda payload: conforming(payload))

    RuntimeProtocolClient(seam, timeout_seconds=86_400.0).identify()

    assert seam.calls[0][1] == 86_400.0


def test_the_timeout_budget_has_no_default():
    """No measurement backs a number here, so none is invented.

    Phase 1B-OFFLINE sends nothing real. A default would be a policy this phase
    has no evidence for, and this repository keeps its measured budgets next to
    the measurement that produced them.
    """
    with pytest.raises(TypeError):
        RuntimeProtocolClient(RecordingSeam(answers(None)))


# ------------------------------------------- 4/5. no response document -----


def test_a_non_response_yields_no_document_and_no_parse_outcome():
    """`None` means one thing: no document arrived. It is not a protocol state."""
    attempt, seam = identify_through(answers(None))

    assert attempt.raw_response is None
    assert attempt.parse_outcome is None
    assert attempt.no_response_document is True
    assert len(seam.calls) == 1


def test_a_non_response_never_reaches_the_parser(monkeypatch):
    """Structurally, not by convention: the parser is not called at all."""

    def refuse(*args, **kwargs):
        raise AssertionError("the parser was asked to classify a non-response")

    monkeypatch.setattr(runtime_protocol_client, "parse_runtime_result", refuse)

    attempt, _ = identify_through(answers(None))

    assert attempt.parse_outcome is None


def test_a_non_response_is_not_called_a_timeout():
    """The seam returns `str | None`. It carries no timeout provenance.

    `probe_runtime.py:1173` raises `TimeoutError` on the same `None`, reading a
    cause off a value that cannot carry one. That is V5 code and stays as it is;
    V6 must not copy the claim.
    """
    attempt, _ = identify_through(answers(None))

    assert attempt.raw_response is None
    assert "timeout" not in repr(attempt).lower()


def test_the_attempt_model_cannot_hold_half_a_result():
    """The biconditional is enforced, so no caller is handed an impossible
    attempt: a document with no classification, or a classification of nothing."""
    answered, _ = identify_through(lambda payload: conforming(payload))

    with pytest.raises(ValueError):
        RuntimeProtocolAttempt(
            operation=answered.operation,
            raw_response=None,
            parse_outcome=answered.parse_outcome,
        )
    with pytest.raises(ValueError):
        RuntimeProtocolAttempt(
            operation=answered.operation,
            raw_response="{}",
            parse_outcome=None,
        )


# ------------------------------------------------- 6/7/8. the happy path ---


def test_a_conforming_responder_yields_valid_v6_unchanged():
    attempt, _ = identify_through(lambda payload: conforming(payload))

    assert attempt.parse_outcome.state is ProtocolParseState.VALID_V6
    assert attempt.parse_outcome.envelope.op == RUNTIME_IDENTIFY
    assert attempt.parse_outcome.envelope.operation_rid == (
        attempt.operation.operation_rid
    )
    assert attempt.parse_outcome.envelope.observed == {
        "pt_file_version": "9.0.1.0858",
        "device_count": 12,
    }
    assert attempt.raw_response is not None
    assert attempt.no_response_document is False


def test_the_expected_identity_comes_from_the_encoded_operation(monkeypatch):
    """The EncodedOperation is the request authority, not a value rebuilt here."""
    seen = {}

    def capture(document, **kwargs):
        seen.update(kwargs)
        return parse_runtime_result(document, **kwargs)

    monkeypatch.setattr(runtime_protocol_client, "parse_runtime_result", capture)

    attempt, _ = identify_through(lambda payload: conforming(payload))

    assert seen["expected_operation_rid"] == attempt.operation.operation_rid
    assert seen["expected_op"] == attempt.operation.op
    assert seen["expected_op"] == RUNTIME_IDENTIFY


def test_the_expected_op_follows_the_encoder_and_not_a_module_constant(
    monkeypatch,
):
    """Today `encoded.op` and `RUNTIME_IDENTIFY` are the same string. They
    must not be the same *mechanism*: the day a second typed operation
    exists, a client correlating on the constant would accept the wrong
    answer for it, and every assertion tying the two together would still
    have passed. So the encoder is made to name something else, and the
    client has to follow it.
    """
    later = replace(encode_runtime_identify(), op="runtime.some-later-op")
    monkeypatch.setattr(
        runtime_protocol_client, "encode_runtime_identify", lambda: later,
    )
    seen = {}

    def capture(document, **kwargs):
        seen.update(kwargs)
        return parse_runtime_result(document, **kwargs)

    monkeypatch.setattr(runtime_protocol_client, "parse_runtime_result", capture)

    attempt, _ = identify_through(lambda payload: conforming(payload))

    assert seen["expected_op"] == "runtime.some-later-op"
    assert seen["expected_op"] != RUNTIME_IDENTIFY
    # The payload still names runtime.identify, so following the encoder is
    # observable in the outcome and not only in the captured argument.
    assert attempt.parse_outcome.state is ProtocolParseState.CORRELATION_MISMATCH


def test_the_correlated_identity_is_the_one_that_went_out_on_the_wire():
    """Recovered from the payload, so an identity swapped in flight is caught."""
    attempt, seam = identify_through(lambda payload: conforming(payload))

    sent_payload, _ = seam.calls[0]
    assert embedded_rid(sent_payload) == attempt.operation.operation_rid
    assert embedded_op(sent_payload) == attempt.operation.op
    assert attempt.parse_outcome.state is ProtocolParseState.VALID_V6


# --------------------------------------------- 9/10. legacy V5 responses ---


@pytest.mark.parametrize(
    "document",
    [
        "PT_ERROR: TypeError: undefined is not a function",
        "ERROR:ReferenceError: ipc is not defined",
        "OK",
        "MISSING",
        "",
        "9.0.1.0858",
    ],
)
def test_a_legacy_v5_text_response_stays_not_v6_and_byte_identical(document):
    attempt, _ = identify_through(answers(document))

    assert attempt.parse_outcome.state is ProtocolParseState.NOT_V6
    assert attempt.parse_outcome.legacy_text == document
    assert attempt.raw_response == document


def test_a_structured_v5_json_response_stays_not_v6():
    """The 118 existing JSON.stringify sites must not be misread as V6."""
    document = json.dumps(
        {"found": True, "pt_version": "9.0.1", "devices": 12, "links": 14},
    )

    attempt, _ = identify_through(answers(document))

    assert attempt.parse_outcome.state is ProtocolParseState.NOT_V6
    assert attempt.parse_outcome.legacy_text == document


def test_the_client_does_not_route_a_legacy_response_anywhere():
    """It classifies. Routing is a later integration policy, not this layer's."""
    attempt, seam = identify_through(answers("PT_ERROR: boom"))

    assert attempt.parse_outcome.routes_to_legacy_v5 is True
    # The decisive part: knowing it *could* be routed changed nothing here.
    assert len(seam.calls) == 1


# ------------------------------------------- 11/12/13/14. fail closed ------


def test_a_malformed_v6_response_stays_invalid_v6():
    broken = json.dumps({"v": 6, "op": "runtime.identify"})

    attempt, _ = identify_through(answers(broken))

    assert attempt.parse_outcome.state is ProtocolParseState.INVALID_V6
    assert attempt.parse_outcome.envelope is None
    assert attempt.parse_outcome.legacy_text is None
    assert attempt.parse_outcome.fails_closed is True


def test_a_foreign_protocol_version_stays_protocol_mismatch():
    def respond(payload):
        document = json.loads(conforming(payload))
        document["v"] = 7
        return json.dumps(document)

    attempt, _ = identify_through(respond)

    assert attempt.parse_outcome.state is ProtocolParseState.PROTOCOL_MISMATCH
    assert attempt.parse_outcome.legacy_text is None
    assert attempt.parse_outcome.fails_closed is True


NEAR_MISSES = [
    pytest.param(False, True, ["operation_rid"], id="wrong-rid-right-op"),
    pytest.param(True, False, ["op"], id="right-rid-wrong-op"),
    pytest.param(False, False, ["operation_rid", "op"], id="wrong-rid-wrong-op"),
]


@pytest.mark.parametrize(
    ("rid_matches", "op_matches", "mismatched"), NEAR_MISSES,
)
def test_a_response_to_another_operation_stays_correlation_mismatch(
    rid_matches, op_matches, mismatched,
):
    """The 1A.1 contract survives the seam: identity is the pair, both halves."""

    def respond(payload):
        return conforming(
            payload,
            operation_rid=None if rid_matches else new_operation_rid(),
            op=None if op_matches else OTHER_OP,
        )

    attempt, seam = identify_through(respond)

    assert attempt.parse_outcome.state is ProtocolParseState.CORRELATION_MISMATCH
    assert attempt.parse_outcome.envelope is None
    assert attempt.parse_outcome.legacy_text is None
    assert attempt.parse_outcome.fails_closed is True
    listed = attempt.parse_outcome.detail.rsplit(": ", 1)[-1].rstrip(")")
    assert listed.split(", ") == mismatched
    # Still exactly one dispatch. A fail-closed outcome is not a reason to ask
    # again, and asking again is how a read-only discipline becomes a replay.
    assert len(seam.calls) == 1


def test_an_engine_error_envelope_is_a_successful_parse():
    """A failed operation is not a failed attempt; the client reports both."""

    def respond(payload):
        document = json.loads(conforming(payload))
        document["status"] = "error"
        document["observed"] = {}
        document["error"] = {"code": "ENGINE_EXCEPTION", "detail": "TypeError: x"}
        return json.dumps(document)

    attempt, _ = identify_through(respond)

    assert attempt.parse_outcome.state is ProtocolParseState.VALID_V6
    assert attempt.parse_outcome.envelope.error.code is (
        RuntimeErrorCode.ENGINE_EXCEPTION
    )


# ------------------------------------------------ 15. a raising callable ---


class SeamFailure(RuntimeError):
    """Whatever a real integration would raise. Not a protocol outcome."""


def test_a_raising_seam_propagates_unchanged():
    """No response document exists, so there is nothing to classify.

    The smaller contract: a callable that breaks its own `str | None` return
    contract is an integration fault, and this layer neither models it nor
    hides it.
    """

    def explode(payload):
        raise SeamFailure("the channel was never opened")

    client = RuntimeProtocolClient(RecordingSeam(explode), timeout_seconds=BUDGET)

    with pytest.raises(SeamFailure, match="the channel was never opened"):
        client.identify()


def test_a_raising_seam_is_never_turned_into_an_engine_exception():
    """ENGINE_EXCEPTION means the Script Engine ran the operation and reported a
    failure envelope. Nothing ran here, so claiming it would fabricate the one
    fact this layer exists to keep honest."""

    def explode(payload):
        raise SeamFailure("boom")

    client = RuntimeProtocolClient(RecordingSeam(explode), timeout_seconds=BUDGET)

    try:
        client.identify()
    except SeamFailure as raised:
        assert RuntimeErrorCode.ENGINE_EXCEPTION.value not in str(raised)
    else:
        raise AssertionError("the integration fault was swallowed")


def test_the_client_catches_nothing_at_all():
    """A `try` in this module is a place a fault could be quietly absorbed.

    Three could be: the seam's own exception, and the parser's `TypeError` and
    `ValueError` caller-bug guards. None of them may become an outcome.
    """
    tree = ast.parse(CLIENT_MODULE.read_text(encoding="utf-8"))

    handlers = [node for node in ast.walk(tree) if isinstance(node, ast.Try)]

    assert handlers == [], "the protocol client catches nothing"


# --------------------------------------- 16. no retry, no fallback --------


@pytest.mark.parametrize(
    "responder",
    [
        answers(None),
        answers("PT_ERROR: boom"),
        answers("OK"),
        answers(json.dumps({"v": 6})),
        answers(json.dumps({"v": 7, "op": "runtime.identify"})),
        lambda payload: conforming(payload, operation_rid=new_operation_rid()),
        lambda payload: conforming(payload, op=OTHER_OP),
        lambda payload: conforming(payload),
    ],
)
def test_every_outcome_costs_exactly_one_dispatch(responder):
    """Whatever comes back -- or does not -- the client sends once and stops."""
    _, seam = identify_through(responder)

    assert len(seam.calls) == 1


def test_the_module_has_no_loop_to_retry_from():
    """The only reason to loop in a one-send client is to send again."""
    tree = ast.parse(CLIENT_MODULE.read_text(encoding="utf-8"))

    loops = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.For, ast.While, ast.AsyncFor))
    ]

    assert loops == [], "a one-send client has nothing to iterate"


def test_the_seam_is_invoked_from_exactly_one_place_in_the_source():
    """A second call site is a fallback or a replay, whatever it is called."""
    tree = ast.parse(CLIENT_MODULE.read_text(encoding="utf-8"))

    call_sites = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_send_and_wait"
    ]

    assert len(call_sites) == 1


# ---------------------------- 17/18. the client reaches nothing it must not


def test_the_client_imports_no_transport_and_no_adapter():
    """The dependency direction: the client depends on the protocol modules and
    receives its channel from outside. It cannot dispatch on its own."""
    forbidden = (
        "live_bridge",
        "file_bridge",
        "tool_registry",
        "adapters",
        "bridge_token",
        "transport_health",
        "urllib",
        "http",
        "socket",
        "subprocess",
    )
    imported = _imported_modules(CLIENT_MODULE)

    offenders = sorted(
        name for name in imported if any(bad in name for bad in forbidden)
    )
    assert offenders == [], f"the client reaches outside Phase 1B-OFFLINE: {offenders}"


def test_the_client_depends_only_on_the_two_protocol_modules():
    """Stated as a whitelist, so a new dependency has to be argued for here.

    Everything that is not stdlib, which for this module is the two protocol
    modules and nothing else. That is the dependency direction of Phase
    1B-OFFLINE written as a test rather than as a diagram.
    """
    imported = _imported_modules(CLIENT_MODULE)

    in_project = sorted(
        name for name in imported
        if name and name.split(".")[0] not in sys.stdlib_module_names
    )
    assert in_project == [
        "runtime_operation_encoder",
        "runtime_operation_encoder.EncodedOperation",
        "runtime_operation_encoder.encode_runtime_identify",
        "runtime_protocol",
        "runtime_protocol.RuntimeParseOutcome",
        "runtime_protocol.parse_runtime_result",
    ]


def test_the_client_names_no_mutating_packet_tracer_api():
    """The list is imported from the containment sweep that owns it."""
    source = CLIENT_MODULE.read_text(encoding="utf-8")

    named = sorted(name for name in _MUTATING_PT_APIS if name in source)

    assert named == [], f"a read-only client names mutating APIs: {named}"


def test_the_client_builds_no_javascript_of_its_own():
    """It orchestrates the encoder's text. A second JS source here would be a
    payload nobody escaped through `js_string_literal`."""
    source = CLIENT_MODULE.read_text(encoding="utf-8")

    assert "reportResult" not in source
    assert "JSON.stringify" not in source


def test_the_attempt_carries_no_mutation_evidence():
    attempt, _ = identify_through(lambda payload: conforming(payload))

    assert not hasattr(attempt, "mutated")
    assert "mutated" not in attempt.operation.payload


# --------------------------- 19/20. what this phase still cannot observe ---


def test_two_attempts_share_no_session_and_no_identity():
    """The client holds nothing between attempts, so it claims nothing about
    what the engine holds. Session persistence is the engine's behaviour, and an
    offline phase cannot observe it."""
    client = RuntimeProtocolClient(
        RecordingSeam(lambda payload: conforming(payload)), timeout_seconds=BUDGET,
    )

    first = client.identify()
    second = client.identify()

    assert first.operation.operation_rid != second.operation.operation_rid
    assert first.operation.session_candidate != second.operation.session_candidate


def test_the_client_does_not_check_the_session_it_gets_back():
    """UNVERIFIED means unverified.

    First-writer-wins says an engine already holding a session returns *that*
    one, not the candidate just sent. Whether it does is a live fact. So a
    session_id unequal to the candidate must stay `VALID_V6`: enforcing equality
    here would encode a guess about the engine as a protocol rule.
    """
    attempt, _ = identify_through(
        lambda payload: conforming(payload, session_id="ses_somebody_elses"),
    )

    assert attempt.parse_outcome.state is ProtocolParseState.VALID_V6
    assert attempt.parse_outcome.envelope.runtime.session_id == "ses_somebody_elses"
    assert attempt.operation.session_candidate != "ses_somebody_elses"


def test_a_null_session_is_still_a_valid_attempt():
    """Degradation stays expressible through the seam, not only in the parser."""
    attempt, _ = identify_through(
        lambda payload: conforming(payload, session_id=None),
    )

    assert attempt.parse_outcome.state is ProtocolParseState.VALID_V6
    assert attempt.parse_outcome.envelope.runtime.session_id is None


def test_the_client_accepts_no_extension_version_input():
    """It cannot back-fill what only the extension could state."""
    tree = ast.parse(CLIENT_MODULE.read_text(encoding="utf-8"))

    accepted = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.arg) and node.arg == "extension_version"
    ]

    assert accepted == []


def test_extension_version_is_whatever_the_responder_said_and_nothing_else():
    """Observed, never supplied. On the Phase-1A wire that value is null."""
    phase_1a, _ = identify_through(lambda payload: conforming(payload))
    claiming, _ = identify_through(
        lambda payload: conforming(payload, extension_version="9.9.9"),
    )

    assert phase_1a.parse_outcome.envelope.runtime.extension_version is None
    assert claiming.parse_outcome.envelope.runtime.extension_version == "9.9.9"
