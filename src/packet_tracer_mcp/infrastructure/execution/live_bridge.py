"""Authenticated HTTP command bridge for Packet Tracer.

The Packet Tracer webview polls this loopback server for JavaScript commands.
Every endpoint except ``/ping`` requires the shared bridge token. Loopback is
not an authentication boundary: browser pages can send CORS-simple requests to
it, so the token, Host validation, body limit, and queue limit are mandatory.

Result-bearing commands are registered with a unique ``rid`` before they are
queued. Packet Tracer returns that same ``rid`` with the result, and a waiter
can consume only the result registered for its own operation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hmac
import http.server
import json
import math
import re
import secrets
import threading
import time
from http.server import ThreadingHTTPServer
from queue import Empty, Full, Queue
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse

from .bridge_token import get_bridge_token, token_fingerprint


DEFAULT_PORT = 54321

# 1 MiB. Real commands are only a few KiB; this bounds abusive input.
MAX_BODY_BYTES = 1 << 20

# Both queues and correlated-result storage remain bounded if PT stalls.
MAX_QUEUE_ITEMS = 1000
MAX_RESULT_ITEMS = 256

# The caller owns the operation budget, subject to one global server ceiling.
MAX_RESULT_WAIT_SECONDS = 60.0
RESULT_SOCKET_GRACE_SECONDS = 5.0
DEFAULT_RESULT_WAIT_SECONDS = 9.0

# Consumed, timed-out, and orphaned results retain a short tombstone so late or
# duplicate writes fail deterministically instead of being reassigned.
RESULT_TTL_SECONDS = 120.0

# /next waits briefly for the first command, then drains a bounded batch.
NEXT_LONGPOLL_SECONDS = 2.0
MAX_BATCH_COMMANDS = 200

_RID_PATTERN = re.compile(r"[0-9a-f]{32}")


@dataclass
class _ResultSlot:
    state: str
    updated_at: float
    body: str | None = None


def next_rid() -> str:
    """Return a unique identity for one result-bearing HTTP operation."""
    return secrets.token_hex(16)


def bounded_result_wait(wait: float) -> float:
    """Normalize a caller wait budget while preserving the global ceiling."""
    value = float(wait)
    if not math.isfinite(value):
        raise ValueError("result wait must be finite")
    return min(max(value, 0.0), MAX_RESULT_WAIT_SECONDS)


def _valid_rid(rid: str) -> bool:
    return _RID_PATTERN.fullmatch(rid) is not None


def report_result_js(port: int, token: str, rid: str) -> str:
    """Build the single-line JS callback that returns one correlated result.

    Packet Tracer executes this function in the Script Engine, while the XHR
    itself must run in the webview. Every serialized field passes through JSON
    encoding; ``JSON.stringify`` serializes the dynamic result into the nested
    webview program.
    """
    if not _valid_rid(rid):
        raise ValueError("invalid bridge result rid")
    query = urlencode({"t": token, "rid": rid})
    result_url = "http://127.0.0.1:" + str(int(port)) + "/result?" + query
    inner_prefix = (
        "var x=new XMLHttpRequest();"
        "x.open('POST'," + json.dumps(result_url) + ",true);"
        "x.setRequestHeader('Content-Type','text/plain');"
        "x.send("
    )
    return (
        "function reportResult(d){var s=String(d);"
        "window.webview.evaluateJavaScriptAsync("
        + json.dumps(inner_prefix)
        + "+JSON.stringify(s)+"
        + json.dumps(");")
        + ")}"
    )


def correlated_http_send_and_wait(
    js_code: str,
    timeout: float,
    *,
    base_url: str,
    port: int,
    token: str,
    http_post: Callable[[str, str, float], tuple[int | None, str | None]],
    http_get: Callable[[str, float], tuple[int | None, str | None]],
) -> str | None:
    """Queue one HTTP operation and consume only its correlated result."""
    rid = next_rid()
    wait = bounded_result_wait(timeout)
    wrapped = report_result_js(port, token, rid) + ";" + js_code
    queue_url = base_url + "/queue?" + urlencode({"rid": rid})
    status_post, _ = http_post(queue_url, wrapped, 3.0)
    if status_post != 200:
        return None
    result_url = base_url + "/result?" + urlencode({"rid": rid, "wait": wait})
    status_get, body = http_get(
        result_url,
        wait + RESULT_SOCKET_GRACE_SECONDS,
    )
    return body if status_get == 200 else None


class PTCommandBridge:
    """HTTP bridge between Python and Packet Tracer's webview extension."""

    def __init__(self, port: int = DEFAULT_PORT, token: str | None = None):
        self.port = port
        self.token = token or get_bridge_token()
        self.token_id = token_fingerprint(self.token)
        self._queue: Queue[str] = Queue(maxsize=MAX_QUEUE_ITEMS)
        self._results: dict[str, _ResultSlot] = {}
        self._results_cv = threading.Condition()
        self._result_ttl = RESULT_TTL_SECONDS
        self._max_result_items = MAX_RESULT_ITEMS
        self._server = None
        self._thread = None
        self._connected = False
        self._last_poll_time = 0.0
        self._unauth_count = 0
        self._unauth_last = 0.0
        self._unauth_paths: set[str] = set()
        self._client_headers: dict[str, str] = {}

    @property
    def is_connected(self) -> bool:
        if self._last_poll_time == 0:
            return False
        return time.time() - self._last_poll_time < 10.0

    @property
    def saw_recent_unauthorized(self) -> bool:
        """Whether an unauthenticated request was observed recently."""
        return self._unauth_last > 0 and time.time() - self._unauth_last < 30.0

    def status_dict(self) -> dict:
        ago = time.time() - self._last_poll_time
        return {
            "connected": self._last_poll_time > 0 and ago < 10.0,
            "last_poll_ago": round(ago, 1) if self._last_poll_time else None,
            "unauth_recent": self.saw_recent_unauthorized,
            "unauth_count": self._unauth_count,
            "unauth_paths": sorted(self._unauth_paths),
            "client_headers": dict(self._client_headers),
            "token_id": self.token_id,
        }

    def _purge_results_locked(self) -> None:
        now = time.monotonic()
        expired = [
            rid
            for rid, slot in self._results.items()
            if now - slot.updated_at >= self._result_ttl
        ]
        for rid in expired:
            del self._results[rid]

    def _make_result_capacity_locked(self) -> bool:
        """Evict only terminal tombstones when admitting a new operation."""
        if len(self._results) < self._max_result_items:
            return True
        terminal = sorted(
            (
                (rid, slot.updated_at)
                for rid, slot in self._results.items()
                if slot.state in {"consumed", "timed_out"}
            ),
            key=lambda item: item[1],
        )
        for rid, _ in terminal:
            del self._results[rid]
            if len(self._results) < self._max_result_items:
                return True
        return False

    def register_result(self, rid: str) -> str:
        """Register a result-bearing operation before queueing its command."""
        with self._results_cv:
            self._purge_results_locked()
            if rid in self._results:
                return "duplicate"
            if not self._make_result_capacity_locked():
                return "full"
            self._results[rid] = _ResultSlot("pending", time.monotonic())
            return "registered"

    def discard_registered_result(self, rid: str) -> None:
        """Roll back registration when the command queue rejects a command."""
        with self._results_cv:
            slot = self._results.get(rid)
            if slot is not None and slot.state == "pending":
                del self._results[rid]

    def put_result(self, rid: str, body: str) -> str:
        """Associate a PT result with its known pending operation."""
        with self._results_cv:
            self._purge_results_locked()
            slot = self._results.get(rid)
            if slot is None:
                return "unknown"
            if slot.state == "timed_out":
                return "late"
            if slot.state != "pending":
                return "duplicate"
            slot.state = "ready"
            slot.body = body
            slot.updated_at = time.monotonic()
            self._results_cv.notify_all()
            return "stored"

    def take_result(self, rid: str, wait: float) -> tuple[str, str | None]:
        """Wait for and consume only the result registered to ``rid``."""
        deadline = time.monotonic() + bounded_result_wait(wait)
        with self._results_cv:
            self._purge_results_locked()
            while True:
                slot = self._results.get(rid)
                if slot is None:
                    return "unknown", None
                if slot.state == "ready":
                    body = slot.body
                    slot.state = "consumed"
                    slot.body = None
                    slot.updated_at = time.monotonic()
                    return "result", body
                if slot.state != "pending":
                    return "gone", None
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    slot.state = "timed_out"
                    slot.updated_at = time.monotonic()
                    return "timeout", None
                self._results_cv.wait(remaining)

    def drain_commands(self) -> list[str]:
        """Wait for the first command and drain one bounded PT batch."""
        commands: list[str] = []
        try:
            commands.append(self._queue.get(timeout=NEXT_LONGPOLL_SECONDS))
        except Empty:
            return commands
        while len(commands) < MAX_BATCH_COMMANDS:
            try:
                commands.append(self._queue.get_nowait())
            except Empty:
                break
        return commands

    def start(self) -> None:
        """Start the loopback HTTP command server."""
        bridge = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _parse(self):
                parsed = urlparse(self.path)
                return parsed.path, parse_qs(parsed.query)

            def _host_ok(self) -> bool:
                host = (self.headers.get("Host") or "").strip().lower()
                return host in (
                    f"127.0.0.1:{bridge.port}",
                    f"localhost:{bridge.port}",
                    f"[::1]:{bridge.port}",
                )

            def _token_from(self, query: dict) -> str:
                return (
                    query.get("t", [""])[0]
                    or self.headers.get("X-PT-Token", "")
                )

            def _authorized(self, query: dict) -> bool:
                if not self._host_ok():
                    return False
                return hmac.compare_digest(self._token_from(query), bridge.token)

            def _note_unauth(self, path: str) -> None:
                bridge._unauth_count += 1
                bridge._unauth_last = time.time()
                bridge._unauth_paths.add(path)

            def _remember_client(self) -> None:
                if bridge._client_headers:
                    return
                for header in (
                    "Origin",
                    "Sec-Fetch-Site",
                    "Sec-Fetch-Mode",
                    "User-Agent",
                ):
                    value = self.headers.get(header)
                    if value:
                        bridge._client_headers[header] = value

            def _read_body(self) -> str | None:
                try:
                    length = int(self.headers.get("Content-Length", 0) or 0)
                except ValueError:
                    self._deny(400)
                    return None
                if length < 0 or length > MAX_BODY_BYTES:
                    self._deny(413)
                    return None
                if not length:
                    return ""
                return self.rfile.read(length).decode("utf-8", "replace")

            def _deny(
                self,
                code: int = 401,
                path: str = "",
                *,
                body_already_read: bool = False,
            ) -> None:
                if code == 401 and path:
                    self._note_unauth(path)
                if not body_already_read:
                    try:
                        length = int(self.headers.get("Content-Length", 0) or 0)
                    except ValueError:
                        length = 0
                    if 0 < length <= 65536:
                        try:
                            self.rfile.read(length)
                        except OSError:
                            pass
                self.close_connection = True
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()

            def _required_rid(
                self,
                query: dict,
                *,
                body_already_read: bool = False,
            ) -> str | None:
                values = query.get("rid", [])
                if len(values) != 1 or not _valid_rid(values[0]):
                    self._deny(400, body_already_read=body_already_read)
                    return None
                return values[0]

            def do_GET(self):
                path, query = self._parse()

                if path == "/ping":
                    self._respond(
                        200,
                        json.dumps(
                            {
                                "service": "pt-mcp-bridge",
                                "proto": 1,
                                "id": bridge.token_id,
                            }
                        ),
                    )
                    return

                if not self._authorized(query):
                    self._deny(401, path)
                    return

                if path == "/next":
                    self._remember_client()
                    bridge._connected = True
                    bridge._last_poll_time = time.time()
                    self._respond(200, "\n".join(bridge.drain_commands()))
                elif path == "/status":
                    self._respond(200, json.dumps(bridge.status_dict()))
                elif path == "/result":
                    rid = self._required_rid(query)
                    if rid is None:
                        return
                    try:
                        wait_values = query.get(
                            "wait",
                            [str(DEFAULT_RESULT_WAIT_SECONDS)],
                        )
                        if len(wait_values) != 1:
                            raise ValueError
                        wait = bounded_result_wait(float(wait_values[0]))
                    except (TypeError, ValueError):
                        self._deny(400)
                        return
                    outcome, result = bridge.take_result(rid, wait)
                    if outcome == "result":
                        self._respond(200, result or "")
                    elif outcome == "timeout":
                        self._respond(204, "")
                    elif outcome == "unknown":
                        self._deny(404)
                    else:
                        self._deny(410)
                else:
                    self._deny(404)

            def do_POST(self):
                path, query = self._parse()

                if not self._authorized(query):
                    self._deny(401, path)
                    return

                body = self._read_body()
                if body is None:
                    return

                if path == "/result":
                    rid = self._required_rid(query, body_already_read=True)
                    if rid is None:
                        return
                    outcome = bridge.put_result(rid, body)
                    if outcome == "stored":
                        self._respond(200, "ok")
                    elif outcome == "unknown":
                        self._deny(404, body_already_read=True)
                    elif outcome == "late":
                        self._deny(410, body_already_read=True)
                    else:
                        self._deny(409, body_already_read=True)
                elif path == "/queue":
                    rid_values = query.get("rid", [])
                    rid = ""
                    if rid_values:
                        if len(rid_values) != 1 or not _valid_rid(rid_values[0]):
                            self._deny(400, body_already_read=True)
                            return
                        if not body:
                            self._deny(400, body_already_read=True)
                            return
                        rid = rid_values[0]
                        registration = bridge.register_result(rid)
                        if registration == "duplicate":
                            self._deny(409, body_already_read=True)
                            return
                        if registration == "full":
                            self._deny(503, body_already_read=True)
                            return
                    if body:
                        try:
                            bridge._queue.put_nowait(body)
                        except Full:
                            if rid:
                                bridge.discard_registered_result(rid)
                            self._deny(503, body_already_read=True)
                            return
                    self._respond(200, "queued")
                else:
                    self._deny(404, body_already_read=True)

            def do_OPTIONS(self):
                self.send_response(200)
                self._cors_headers()
                self.end_headers()

            def _respond(self, code: int, body: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self._cors_headers()
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

            def _cors_headers(self) -> None:
                # PT's observed webview origin requires readable successful
                # responses. Authentication, not CORS, protects the bridge.
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header(
                    "Access-Control-Allow-Headers",
                    "Content-Type, X-PT-Token",
                )

            def log_message(self, format, *args):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    # Result-bearing callers use the HTTP endpoints through
    # ``correlated_http_send_and_wait``. A second in-process send/wait path
    # would duplicate the correlation contract and permit drift.
