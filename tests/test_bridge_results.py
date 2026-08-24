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

from src.packet_tracer_mcp.infrastructure.execution.live_bridge import (
    PacketTracerHttpTransport,
    PTCommandBridge,
    report_result_js,
)


TOKEN = "test-token-that-is-long-enough-to-be-valid-0123456789"
RID_A = "a" * 32
RID_B = "b" * 32


@pytest.fixture
def bridge():
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
    delay = 9.25
    assert _queue_result_operation(bridge, RID_A) == 200

    def respond_after_old_window() -> None:
        time.sleep(delay)
        _post_result(bridge, RID_A, "SLOW_RESULT")

    responder = threading.Thread(target=respond_after_old_window)
    responder.start()
    started = time.monotonic()
    result = _get_result(bridge, RID_A, wait=12.0)
    elapsed = time.monotonic() - started
    responder.join(timeout=5.0)

    assert result == (200, "SLOW_RESULT")
    assert elapsed >= delay
    assert not responder.is_alive()


def test_orphan_storage_is_bounded_and_stale_entries_expire(bridge):
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
    malformed = "not-a-valid-rid"
    unknown = "c" * 32
    known = "d" * 32

    assert _get_result(bridge, None, wait=0.0)[0] == 400
    assert _post_result(bridge, None, "ownerless") == 400
    assert _queue_result_operation(bridge, malformed) == 400
    assert _get_result(bridge, malformed, wait=0.0)[0] == 400
    assert _post_result(bridge, malformed, "malformed") == 400
    malformed_wait = urllib.parse.urlencode(
        {"t": TOKEN, "rid": unknown, "wait": "nan"}
    )
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
    from src.packet_tracer_mcp.infrastructure.execution.live_bridge import next_rid

    rids = {next_rid() for _ in range(1000)}

    assert len(rids) == 1000
    assert all(re.fullmatch(r"[0-9a-f]{32}", rid) for rid in rids)


def test_report_result_js_carries_encoded_token_and_rid_on_one_line():
    token = "token with spaces&rid=attacker"
    js = report_result_js(54321, token, RID_A)

    encoded_query = urllib.parse.urlencode({"t": token, "rid": RID_A})
    assert encoded_query in js
    assert "\n" not in js


def test_active_http_caller_reuses_one_rid_and_extends_the_socket_wait():
    from src.packet_tracer_mcp.infrastructure.execution.live_bridge import (
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
        urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        for url, _ in gets
    ]
    assert queue_rids[0] != queue_rids[1]
    assert [query["rid"][0] for query in result_queries] == queue_rids
    assert all(rid in body for rid, (_, body, _) in zip(queue_rids, posts))
    assert all(query["wait"] == ["15.0"] for query in result_queries)
    assert all(timeout == 15.0 + RESULT_SOCKET_GRACE_SECONDS for _, timeout in gets)
    assert first == "result-for-" + queue_rids[0]
    assert second == "result-for-" + queue_rids[1]


def test_wait_budget_has_a_finite_global_ceiling():
    from src.packet_tracer_mcp.infrastructure.execution.live_bridge import (
        MAX_RESULT_WAIT_SECONDS,
        bounded_result_wait,
    )

    assert bounded_result_wait(MAX_RESULT_WAIT_SECONDS + 100.0) == (
        MAX_RESULT_WAIT_SECONDS
    )
    with pytest.raises(ValueError):
        bounded_result_wait(float("inf"))
