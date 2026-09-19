"""Regression tests for correlated HTTP bridge results.

These tests drive the real local HTTP server. Packet Tracer is simulated only
at the `/next` and `/result` boundary, where its webview normally participates.
"""

from __future__ import annotations

import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

from packet_tracer_mcp.infrastructure.execution.live_bridge import (
    PacketTracerHttpTransport,
    PTCommandBridge,
    report_result_js,
)

TOKEN = "test-token-that-is-long-enough-to-be-valid-0123456789"
RID_A = "a" * 32
RID_B = "b" * 32

#: What a measured duration may read below the duration that actually
#: elapsed. `time.monotonic()` returns seconds since boot as a float, so at a
#: modest uptime its representation granularity already exceeds the margin an
#: exact lower bound leaves: a true 9.25 s wait read back as
#: 9.249999999999972 is one ulp of the clock value at an uptime of 128-256 s,
#: not a short wait. `monotonic_ns` has no such error, so what is left is the
#: clock's own resolution -- 1 ns where `clock_gettime` backs it, 15.625 ms
#: where `GetTickCount64` does.
CLOCK_RESOLUTION_NS = max(1, round(time.get_clock_info("monotonic").resolution * 1e9))


@pytest.fixture
def bridge():
    """Serve one real bridge on an ephemeral port, stopped after the test."""
    instance = PTCommandBridge(port=0, token=TOKEN)
    instance.start()
    yield instance
    instance.stop()


def _request(
    bridge,
    path: str,
    method: str = "GET",
    body: str | None = None,
    *,
    socket_timeout: float = 5.0,
) -> tuple[int, str]:
    url = f"http://127.0.0.1:{bridge.port}{path}"
    data = body.encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "text/plain")
    try:
        with urllib.request.urlopen(request, timeout=socket_timeout) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def _queue_result_operation(bridge, rid: str, body: str = "noop();") -> int:
    query = urllib.parse.urlencode({"t": TOKEN, "rid": rid})
    return _request(bridge, f"/queue?{query}", "POST", body)[0]


def _post_result(bridge, rid: str | None, body: str) -> int:
    values = {"t": TOKEN}
    if rid is not None:
        values["rid"] = rid
    query = urllib.parse.urlencode(values)
    return _request(bridge, f"/result?{query}", "POST", body)[0]


def _get_result(
    bridge,
    rid: str | None,
    wait: float,
) -> tuple[int, str]:
    values = {"t": TOKEN, "wait": str(wait)}
    if rid is not None:
        values["rid"] = rid
    query = urllib.parse.urlencode(values)
    return _request(
        bridge,
        f"/result?{query}",
        socket_timeout=max(wait, 0.0) + 5.0,
    )


def test_product_http_transport_authenticates_and_guards_fire_and_forget():
    """A fire-and-forget send reaches the queue wrapped in its catch guard."""
    transport = PacketTracerHttpTransport(port=0, token=TOKEN)
    assert transport.bridge_transport == "http"
    transport.start(wait_for_connection=False)
    try:
        assert transport.send("noop();")
        assert transport._bridge.drain_commands() == [
            "try{noop();}catch(__pterr){}",
        ]
    finally:
        transport.stop()


def test_late_result_is_isolated_from_the_next_operation(bridge):
    """A result posted after its wait expired is refused, not handed on.

    The timed-out caller gets 204, the late post gets 410, and the next
    operation's result is its own: a stale answer never becomes someone
    else's.
    """
    assert _queue_result_operation(bridge, RID_A) == 200
    bridge._queue.get_nowait()

    started = time.monotonic()
    timed_out = _get_result(bridge, RID_A, wait=0.05)
    elapsed = time.monotonic() - started
    late_status = _post_result(bridge, RID_A, "RESULT_A")

    assert _queue_result_operation(bridge, RID_B) == 200
    assert _post_result(bridge, RID_B, "RESULT_B") == 200
    result_b = _get_result(bridge, RID_B, wait=0.5)

    assert timed_out == (204, "")
    assert elapsed < 0.5
    assert late_status == 410
    assert result_b == (200, "RESULT_B")


def test_concurrent_out_of_order_results_do_not_cross(bridge):
    """Two waiters each receive their own rid's result, posted in reverse."""
    assert _queue_result_operation(bridge, RID_A) == 200
    assert _queue_result_operation(bridge, RID_B) == 200
    observed: dict[str, tuple[int, str]] = {}

    def collect(rid: str) -> None:
        observed[rid] = _get_result(bridge, rid, wait=2.0)

    waiter_a = threading.Thread(target=collect, args=(RID_A,))
    waiter_b = threading.Thread(target=collect, args=(RID_B,))
    waiter_a.start()
    time.sleep(0.1)
    waiter_b.start()
    time.sleep(0.1)

    assert _post_result(bridge, RID_B, "RESULT_B") == 200
    assert _post_result(bridge, RID_A, "RESULT_A") == 200
    waiter_a.join(timeout=5.0)
    waiter_b.join(timeout=5.0)

    assert not waiter_a.is_alive()
    assert not waiter_b.is_alive()
    assert observed == {
        RID_A: (200, "RESULT_A"),
        RID_B: (200, "RESULT_B"),
    }


def test_governed_wait_longer_than_the_old_fixed_window_is_honored(bridge):
    """A result arriving well past the old fixed window is still delivered.

    Receiving SLOW_RESULT is the primary fact: the bridge could only answer
    with it after the post, so the call blocked for the whole delay. The
    elapsed bound is the quantitative check on that, and it is measured
    against the clock's own resolution rather than as an exact float
    inequality.
    """
    delay = 9.25
    assert _queue_result_operation(bridge, RID_A) == 200

    def respond_after_old_window() -> None:
        time.sleep(delay)
        _post_result(bridge, RID_A, "SLOW_RESULT")

    responder = threading.Thread(target=respond_after_old_window)
    # Read BEFORE the thread starts. Taken afterwards, the sleep being
    # measured can begin before the measurement point, so the observed window
    # is shorter than the sleep by however long the start took.
    started = time.monotonic_ns()
    responder.start()
    result = _get_result(bridge, RID_A, wait=12.0)
    elapsed = time.monotonic_ns() - started
    responder.join(timeout=5.0)

    assert result == (200, "SLOW_RESULT")
    assert elapsed >= round(delay * 1e9) - CLOCK_RESOLUTION_NS
    assert not responder.is_alive()


def test_orphan_storage_is_bounded_and_stale_entries_expire(bridge):
    """The result store is capped: a full store refuses, an expired one makes room."""
    bridge._max_result_items = 3
    bridge._result_ttl = 60.0

    for index in range(3):
        rid = f"{index:032x}"
        assert _queue_result_operation(bridge, rid) == 200
        assert _post_result(bridge, rid, f"result-{index}") == 200

    rejected_rid = "e" * 32
    assert _queue_result_operation(bridge, rejected_rid) == 503
    assert len(bridge._results) == 3

    bridge._result_ttl = 0.0
    fresh_rid = "f" * 32
    assert _queue_result_operation(bridge, fresh_rid) == 200
    assert list(bridge._results) == [fresh_rid]


def test_consumed_tombstones_do_not_exhaust_scale_capacity(bridge):
    """A consumed rid keeps its tombstone without holding a capacity slot.

    The tombstone still has to refuse a very late post for that rid, which is
    what separates "already delivered" from "never existed".
    """
    bridge._max_result_items = 2
    first = "1" * 32
    second = "2" * 32
    third = "3" * 32

    for rid in (first, second):
        assert _queue_result_operation(bridge, rid) == 200
        assert _post_result(bridge, rid, rid) == 200
        assert _get_result(bridge, rid, wait=0.0) == (200, rid)

    assert len(bridge._results) == 2
    assert _queue_result_operation(bridge, third) == 200
    assert len(bridge._results) == 2
    assert first not in bridge._results
    assert _post_result(bridge, first, "very-late") == 404


def test_rid_validation_and_duplicate_results_fail_closed(bridge):
    """Every rid and wait the caller supplies is validated before it is used.

    A missing, malformed or unknown rid and a non-finite wait are refused,
    and a second queue or post for one rid never overwrites the first.
    """
    malformed = "not-a-valid-rid"
    unknown = "c" * 32
    known = "d" * 32

    assert _get_result(bridge, None, wait=0.0)[0] == 400
    assert _post_result(bridge, None, "ownerless") == 400
    assert _queue_result_operation(bridge, malformed) == 400
    assert _get_result(bridge, malformed, wait=0.0)[0] == 400
    assert _post_result(bridge, malformed, "malformed") == 400
    malformed_wait = urllib.parse.urlencode({"t": TOKEN, "rid": unknown, "wait": "nan"})
    assert _request(bridge, f"/result?{malformed_wait}")[0] == 400
    assert _get_result(bridge, unknown, wait=0.0)[0] == 404
    assert _post_result(bridge, unknown, "unknown") == 404

    assert _queue_result_operation(bridge, known) == 200
    assert _queue_result_operation(bridge, known) == 409
    assert _post_result(bridge, known, "FIRST") == 200
    assert _post_result(bridge, known, "SECOND") == 409
    assert _get_result(bridge, known, wait=0.0) == (200, "FIRST")
    assert _post_result(bridge, known, "AFTER_CONSUME") == 409

    assert _queue_result_operation(bridge, RID_B) == 200
    assert _post_result(bridge, RID_B, "RESULT_B") == 200
    assert _get_result(bridge, RID_B, wait=0.0) == (200, "RESULT_B")


def test_generated_rids_are_unique_and_strictly_serializable():
    """A thousand generated rids are distinct and all match the wire pattern."""
    from packet_tracer_mcp.infrastructure.execution.live_bridge import next_rid

    rids = {next_rid() for _ in range(1000)}

    assert len(rids) == 1000
    assert all(re.fullmatch(r"[0-9a-f]{32}", rid) for rid in rids)


def test_report_result_js_carries_encoded_token_and_rid_on_one_line():
    """The callback encodes its query and stays one line, as PT requires."""
    token = "token with spaces&rid=attacker"
    js = report_result_js(54321, token, RID_A)

    encoded_query = urllib.parse.urlencode({"t": token, "rid": RID_A})
    assert encoded_query in js
    assert "\n" not in js


def test_active_http_caller_reuses_one_rid_and_extends_the_socket_wait():
    """Each call takes a fresh rid, and the socket wait exceeds the result wait.

    The socket has to outlive the governed wait by its grace, or the caller
    would abandon a result the bridge was still entitled to deliver.
    """
    from packet_tracer_mcp.infrastructure.execution.live_bridge import (
        RESULT_SOCKET_GRACE_SECONDS,
        correlated_http_send_and_wait,
    )

    posts: list[tuple[str, str, float]] = []
    gets: list[tuple[str, float]] = []

    def post(url: str, body: str, timeout: float):
        posts.append((url, body, timeout))
        return 200, "queued"

    def get(url: str, timeout: float):
        gets.append((url, timeout))
        rid = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["rid"][0]
        return 200, "result-for-" + rid

    first = correlated_http_send_and_wait(
        "reportResult('first');",
        15.0,
        base_url="http://127.0.0.1:54321",
        port=54321,
        token=TOKEN,
        http_post=post,
        http_get=get,
    )
    second = correlated_http_send_and_wait(
        "reportResult('second');",
        15.0,
        base_url="http://127.0.0.1:54321",
        port=54321,
        token=TOKEN,
        http_post=post,
        http_get=get,
    )

    queue_rids = [
        urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["rid"][0]
        for url, _, _ in posts
    ]
    result_queries = [
        urllib.parse.parse_qs(urllib.parse.urlparse(url).query) for url, _ in gets
    ]
    assert queue_rids[0] != queue_rids[1]
    assert [query["rid"][0] for query in result_queries] == queue_rids
    assert all(rid in body for rid, (_, body, _) in zip(queue_rids, posts, strict=True))
    assert all(query["wait"] == ["15.0"] for query in result_queries)
    assert all(timeout == 15.0 + RESULT_SOCKET_GRACE_SECONDS for _, timeout in gets)
    assert first == "result-for-" + queue_rids[0]
    assert second == "result-for-" + queue_rids[1]


def test_wait_budget_has_a_finite_global_ceiling():
    """A caller cannot ask for an unbounded or non-finite wait."""
    from packet_tracer_mcp.infrastructure.execution.live_bridge import (
        MAX_RESULT_WAIT_SECONDS,
        bounded_result_wait,
    )

    assert bounded_result_wait(MAX_RESULT_WAIT_SECONDS + 100.0) == (
        MAX_RESULT_WAIT_SECONDS
    )
    with pytest.raises(ValueError):
        bounded_result_wait(float("inf"))
