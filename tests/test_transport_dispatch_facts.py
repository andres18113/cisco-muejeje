"""Typed dispatch facts for the HTTP and file command channels.

The oracle for the HTTP classification is an independent truth table plus real
sockets on an ephemeral port, never the classifier read back to itself. The
differential table over `correlated_http_send_and_wait` is a regression guard
for the legacy projection and is green at the baseline by construction.
"""

from __future__ import annotations

import dataclasses
import itertools
import socket
import threading

import pytest

from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.infrastructure.execution.file_bridge import (
    FileBridge,
    RequestDisposition,
)
from packet_tracer_mcp.infrastructure.execution.live_bridge import (
    PacketTracerHttpTransport,
    PTCommandBridge,
    correlated_http_dispatch,
    correlated_http_send_and_wait,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
    HttpPostOutcome,
    PostPhase,
    sanitized_detail,
)

TOKEN = "test-token-that-is-long-enough-to-be-valid-0123456789"


# -- 1. the HTTP classification against an independent truth table -------

#: (post phase, post status, get status) -> (dispatch, result). Written from
#: the contract, not from the implementation: this table is the oracle.
_HTTP_TRUTH = {
    (PostPhase.NOT_SUBMITTED, None, None): (
        DispatchFact.NOT_SUBMITTED,
        ResultFact.NOT_APPLICABLE,
    ),
    (PostPhase.UNDECIDABLE, None, None): (
        DispatchFact.ACCEPTANCE_UNKNOWN,
        ResultFact.NOT_OBSERVED,
    ),
    (PostPhase.SENT, None, None): (
        DispatchFact.ACCEPTANCE_UNKNOWN,
        ResultFact.NOT_OBSERVED,
    ),
    (PostPhase.SENT, 400, None): (DispatchFact.REJECTED, ResultFact.NOT_APPLICABLE),
    (PostPhase.SENT, 401, None): (DispatchFact.REJECTED, ResultFact.NOT_APPLICABLE),
    (PostPhase.SENT, 409, None): (DispatchFact.REJECTED, ResultFact.NOT_APPLICABLE),
    (PostPhase.SENT, 503, None): (DispatchFact.REJECTED, ResultFact.NOT_APPLICABLE),
    (PostPhase.SENT, 200, 200): (DispatchFact.ACCEPTED, ResultFact.CORRELATED),
    (PostPhase.SENT, 200, 204): (DispatchFact.ACCEPTED, ResultFact.NOT_OBSERVED),
    (PostPhase.SENT, 200, 404): (DispatchFact.ACCEPTED, ResultFact.LOST),
    (PostPhase.SENT, 200, 410): (DispatchFact.ACCEPTED, ResultFact.LOST),
    (PostPhase.SENT, 200, None): (DispatchFact.ACCEPTED, ResultFact.NOT_OBSERVED),
}


def _dispatch(phase, post_status, get_status, *, body="RESULT"):
    def connect_post(url, payload, timeout):
        return HttpPostOutcome(
            status=post_status,
            body="queued" if post_status == 200 else None,
            phase=phase,
            detail="" if post_status is not None else "synthetic",
        )

    def http_get(url, timeout):
        return get_status, (body if get_status == 200 else None)

    return correlated_http_dispatch(
        "noop();",
        1.0,
        base_url="http://127.0.0.1:1",
        port=1,
        token=TOKEN,
        http_connect_post=connect_post,
        http_get=http_get,
    )


@pytest.mark.parametrize(("key", "expected"), sorted(_HTTP_TRUTH.items(), key=str))
def test_the_http_classification_matches_the_independent_truth_table(key, expected):
    """Each observable outcome maps to exactly the two facts it supports."""
    phase, post_status, get_status = key
    outcome = _dispatch(phase, post_status, get_status)

    assert (outcome.dispatch, outcome.result) == expected


def test_a_refused_connection_is_the_only_definite_local_negative():
    """NOT_SUBMITTED requires proof that no request byte left the process.

    A connection that broke after the request went out looks identical from
    `urllib`, and treating it as NOT_SUBMITTED would license a retry of a
    mutation that may already have run.
    """
    refused = _dispatch(PostPhase.NOT_SUBMITTED, None, None)
    broke_after = _dispatch(PostPhase.SENT, None, None)
    undecidable = _dispatch(PostPhase.UNDECIDABLE, None, None)

    assert refused.dispatch is DispatchFact.NOT_SUBMITTED
    assert broke_after.dispatch is DispatchFact.ACCEPTANCE_UNKNOWN
    assert undecidable.dispatch is DispatchFact.ACCEPTANCE_UNKNOWN


def test_an_unclassified_answered_status_is_never_reported_as_rejected():
    """REJECTED positively claims the command was not queued.

    An unknown status code does not support that claim, so the fail-closed
    answer is ACCEPTANCE_UNKNOWN, which claims nothing in either direction.
    """
    outcome = _dispatch(PostPhase.SENT, 418, None)

    assert outcome.dispatch is DispatchFact.ACCEPTANCE_UNKNOWN
    assert outcome.result is ResultFact.NOT_OBSERVED
    assert outcome.detail == "status_unclassified:418"


def test_a_no_content_result_names_the_timeout_that_refuses_a_late_write():
    """204 leaves the slot `timed_out`, so a later write is refused, not reused."""
    outcome = _dispatch(PostPhase.SENT, 200, 204)

    assert outcome.result is ResultFact.NOT_OBSERVED
    assert outcome.detail == "timed_out"
    assert outcome.body is None


def test_the_detail_is_sanitized_and_bounded():
    """An external error string never reaches a record unbounded."""
    long_error = OSError("x" * 5000)

    detail = sanitized_detail(long_error)

    assert detail.startswith("OSError:")
    assert len(detail) <= 200


# -- 2. differential characterization of the legacy projection -----------


def _baseline_correlated_http_send_and_wait(status_post, status_get, body):
    """Reproduce the baseline decision, as the regression guard for it.

    Copied from `live_bridge.py` at `6263344`: `None` unless the POST answered
    200 and the GET answered 200. It is a REGRESSION GUARD for the projection,
    not the oracle for the classification -- the baseline had no facts to
    classify.
    """
    if status_post != 200:
        return None
    return body if status_get == 200 else None


_STATUSES = (None, 200, 204, 400, 401, 404, 409, 410, 503)


@pytest.mark.parametrize(
    ("status_post", "status_get", "body"),
    [
        (post, get, body)
        for post, get, body in itertools.product(_STATUSES, _STATUSES, ("RESULT", ""))
    ],
)
def test_the_legacy_projection_returns_exactly_what_the_baseline_returned(
    status_post, status_get, body
):
    """Every existing caller of `send_and_wait` sees an unchanged contract."""

    def http_post(url, payload, timeout):
        return status_post, "queued" if status_post == 200 else None

    def http_get(url, timeout):
        return status_get, (body if status_get == 200 else None)

    observed = correlated_http_send_and_wait(
        "noop();",
        1.0,
        base_url="http://127.0.0.1:1",
        port=1,
        token=TOKEN,
        http_post=http_post,
        http_get=http_get,
    )

    assert observed == _baseline_correlated_http_send_and_wait(
        status_post, status_get, body
    )


# -- 3. real sockets on an ephemeral port --------------------------------


def test_a_closed_port_reports_not_submitted_over_a_real_socket():
    """Nothing was written, so the command definitively cannot run later."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    transport = PacketTracerHttpTransport(port=port, token=TOKEN)
    transport.base_url = f"http://127.0.0.1:{port}"

    outcome = transport.dispatch_and_wait("noop();", timeout=0.5)

    assert outcome.dispatch is DispatchFact.NOT_SUBMITTED
    assert outcome.result is ResultFact.NOT_APPLICABLE
    assert outcome.body is None


def test_a_server_that_reads_and_closes_reports_acceptance_unknown():
    """The request went out and no answer came back: nothing is decided.

    This is the case that used to be indistinguishable from a refused
    connection, and it is the one where a retry would be unsafe.
    """
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    ready = threading.Event()

    def serve():
        ready.set()
        connection, _ = listener.accept()
        with connection:
            connection.recv(65536)
        # Closed without a response line.

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    ready.wait(5.0)
    try:
        transport = PacketTracerHttpTransport(port=port, token=TOKEN)
        transport.base_url = f"http://127.0.0.1:{port}"

        outcome = transport.dispatch_and_wait("noop();", timeout=0.5)
    finally:
        worker.join(5.0)
        listener.close()

    assert outcome.dispatch is DispatchFact.ACCEPTANCE_UNKNOWN
    assert outcome.result is ResultFact.NOT_OBSERVED
    assert outcome.body is None


def test_the_real_bridge_without_a_webview_reports_accepted_and_not_observed():
    """The local queue accepted it; Packet Tracer never answered.

    ACCEPTED is acceptance by the bridge queue, and the absence of a webview
    is exactly why it must not be read as execution.
    """
    bridge = PTCommandBridge(port=0, token=TOKEN)
    bridge.start()
    try:
        transport = PacketTracerHttpTransport(port=bridge.port, token=TOKEN)
        transport.base_url = f"http://127.0.0.1:{bridge.port}"

        outcome = transport.dispatch_and_wait("noop();", timeout=0.2)
    finally:
        bridge.stop()

    assert outcome.dispatch is DispatchFact.ACCEPTED
    assert outcome.result is ResultFact.NOT_OBSERVED
    assert outcome.detail == "timed_out"


def test_a_duplicate_rid_is_rejected_by_the_real_bridge():
    """A registration collision is a definite refusal, so REJECTED is honest."""
    bridge = PTCommandBridge(port=0, token=TOKEN)
    bridge.start()
    try:
        transport = PacketTracerHttpTransport(port=bridge.port, token=TOKEN)
        transport.base_url = f"http://127.0.0.1:{bridge.port}"

        # Force every operation onto one rid so the second registration
        # collides inside the real handler.
        import packet_tracer_mcp.infrastructure.execution.live_bridge as live

        original = live.next_rid
        live.next_rid = lambda: "c" * 32
        try:
            first = transport.dispatch_and_wait("noop();", timeout=0.05)
            second = transport.dispatch_and_wait("noop();", timeout=0.05)
        finally:
            live.next_rid = original
    finally:
        bridge.stop()

    assert first.dispatch is DispatchFact.ACCEPTED
    assert second.dispatch is DispatchFact.REJECTED
    assert second.result is ResultFact.NOT_APPLICABLE
    assert second.detail == "rejected:409"


def test_a_result_posted_after_the_timeout_is_refused_and_never_attributed():
    """A late write must not land on the next operation's slot."""
    import urllib.error
    import urllib.parse
    import urllib.request

    bridge = PTCommandBridge(port=0, token=TOKEN)
    bridge.start()
    try:
        transport = PacketTracerHttpTransport(port=bridge.port, token=TOKEN)
        transport.base_url = f"http://127.0.0.1:{bridge.port}"

        import packet_tracer_mcp.infrastructure.execution.live_bridge as live

        original = live.next_rid
        live.next_rid = lambda: "d" * 32
        try:
            timed_out = transport.dispatch_and_wait("noop();", timeout=0.05)
        finally:
            live.next_rid = original
        bridge._queue.get_nowait()

        query = urllib.parse.urlencode({"t": TOKEN, "rid": "d" * 32})
        request = urllib.request.Request(
            f"http://127.0.0.1:{bridge.port}/result?{query}",
            data=b"LATE",
            method="POST",
        )
        request.add_header("Content-Type", "text/plain")
        late_status = None
        try:
            with urllib.request.urlopen(request, timeout=5.0) as response:
                late_status = response.status
        except urllib.error.HTTPError as error:
            late_status = error.code
    finally:
        bridge.stop()

    assert timed_out.result is ResultFact.NOT_OBSERVED
    assert timed_out.body is None
    assert late_status == 410


# -- 4. the file channel --------------------------------------------------


def test_a_publication_failure_leaves_no_request_and_reports_not_submitted(tmp_path):
    """Nothing reached the mailbox, so nothing can execute later."""
    bridge = FileBridge(tmp_path / "mailbox", cancel_observation_seconds=0.0)
    original = bridge._publish
    bridge._publish = lambda path, text: (False, "synthetic_write_error")

    outcome = bridge.dispatch_and_wait("noop();", timeout=0.05)
    bridge._publish = original

    assert outcome.dispatch is DispatchFact.NOT_SUBMITTED
    assert outcome.result is ResultFact.NOT_APPLICABLE
    assert outcome.disposition == ""
    assert not list((tmp_path / "mailbox").glob("req_*"))


def test_a_deadline_after_publication_reports_not_observed_with_a_disposition(
    tmp_path,
):
    """The request was published, so ACCEPTED holds and the outcome is unknown."""
    bridge = FileBridge(tmp_path / "mailbox", cancel_observation_seconds=0.0)

    outcome = bridge.dispatch_and_wait("noop();", timeout=0.05)

    assert outcome.dispatch is DispatchFact.ACCEPTED
    assert outcome.result is ResultFact.NOT_OBSERVED
    assert outcome.disposition == (
        RequestDisposition.WITHDRAWN_NO_EXECUTION_OBSERVED.value
    )


def test_a_second_call_never_reports_the_first_calls_disposition(tmp_path):
    """The disposition on an outcome is per call, not a channel-wide latch."""
    directory = tmp_path / "mailbox"
    bridge = FileBridge(directory, cancel_observation_seconds=0.0)
    first = bridge.dispatch_and_wait("noop();", timeout=0.05)

    # Answer the second request so it correlates.
    published = {"name": ""}

    def publish(path, text):
        published["name"] = path.name[len("req_") : -len(".js")]
        result = FileBridge._publish(bridge, path, text)
        (directory / f"res_{published['name']}.txt").write_text("OK", encoding="utf-8")
        return result

    bridge._publish = publish
    second = bridge.dispatch_and_wait("noop();", timeout=1.0)

    assert first.disposition == (
        RequestDisposition.WITHDRAWN_NO_EXECUTION_OBSERVED.value
    )
    assert second.result is ResultFact.CORRELATED
    assert second.body == "OK"
    assert second.disposition == RequestDisposition.COMPLETED.value


def test_no_file_disposition_ever_claims_the_command_did_not_run():
    """`proves_no_execution` is uniformly False, and the outcome relies on it.

    The deployed Script Engine publishes no claim marker, so a withdrawn
    request cannot be distinguished from one already being evaluated.
    """
    for disposition in RequestDisposition:
        assert disposition.proves_no_execution is False


def test_the_legacy_send_and_wait_behavior_is_unchanged(tmp_path):
    """`send_and_wait` still answers `None` and still sets `last_disposition`."""
    bridge = FileBridge(tmp_path / "mailbox", cancel_observation_seconds=0.0)

    body = bridge.send_and_wait("noop();", timeout=0.05)

    assert body is None
    assert bridge.last_disposition is (
        RequestDisposition.WITHDRAWN_NO_EXECUTION_OBSERVED
    )


def test_a_frozen_outcome_cannot_be_edited_after_the_fact():
    """The outcome is the record of one dispatch and stays that record."""
    outcome = BridgeDispatchOutcome(
        dispatch=DispatchFact.ACCEPTED,
        result=ResultFact.CORRELATED,
        body="OK",
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.dispatch = DispatchFact.NOT_SUBMITTED
