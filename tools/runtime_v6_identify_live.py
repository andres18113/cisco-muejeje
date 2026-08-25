"""Operator-only READ-ONLY LIVE harness for the V6 operation runtime.identify.

What it does
------------
Builds the one transport the operator declared, proves that transport is ready,
hands its `send_and_wait` to the accepted `RuntimeProtocolClient`, runs exactly
one `runtime.identify`, and prints one JSON document describing what happened.

It observes. It creates no device, no link and no configuration, writes no
file into the workspace, issues no IOS, and touches no developer command
surface. It is safe against a blank disposable Packet Tracer instance, which is
the only kind it should ever meet.

One invocation, one channel
---------------------------
`--channel http` or `--channel file`, always explicit. There is no default and
no fallback in either direction. A harness that retried on the other channel
after a silent one would produce evidence nobody could attribute: the whole
point of the run is to learn whether *that* channel carries V6, and a result
that might have come from either answers nothing.

Ownership
---------
On HTTP the harness starts the transport it built and stops it in a `finally`,
so no server, thread or process outlives the run whatever the outcome. On the
file channel it requires a fresh Script Engine heartbeat before dispatching,
and reports the absence of one as exactly that -- a heartbeat fact -- never as
a timeout, a protocol verdict, or a Packet Tracer failure.

The client is the authority
---------------------------
The harness never encodes a payload or classifies a document itself. Both are
`RuntimeProtocolClient`'s job, and a LIVE run that reimplemented either would
validate something other than what ships. Operation identity, the single send,
and the correlation of the reply all stay where they were built and tested.

What a green run does not establish
-----------------------------------
One observation from one channel. Session persistence across commands, across a
webview reopen, or across a restart; agreement between the two channels; the
extension's own version -- none of them follows from a single successful
identify, and the emitted JSON says so in `non_claims` rather than leaving a
reader to infer it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from packet_tracer_mcp.infrastructure.execution.file_bridge import FileBridge
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
)
from packet_tracer_mcp.infrastructure.execution.live_bridge import (
    PacketTracerHttpTransport,
)
from packet_tracer_mcp.infrastructure.execution.runtime_protocol import ResultStatus
from packet_tracer_mcp.infrastructure.execution.runtime_protocol_client import (
    RuntimeProtocolClient,
)

PHASE = "1B-LIVE-A"

#: Declared by this file's location, never derived from the loaded package: if
#: the package came from the wrong tree, deriving the root from it would let the
#: check approve itself.
GOVERNED_ROOT = Path(__file__).resolve().parents[1]

#: Bridge readiness, not the operation budget. Ten seconds is what every
#: sibling operator runner in this directory already waits for fresh polling
#: (`cp_scale_canonical_live.py:967`); the V6 operation budget is the
#: operator's and has no default at all.
HTTP_START_TIMEOUT_SECONDS = 10.0

EXIT_VALID_V6_OK = 0
EXIT_CLASSIFIED_NOT_OK = 1
EXIT_NO_CLASSIFIED_DOCUMENT = 2

_VERDICTS = {
    EXIT_VALID_V6_OK: "VALID_V6_OK",
    EXIT_CLASSIFIED_NOT_OK: "CLASSIFIED_NOT_VALID_V6_OK",
    EXIT_NO_CLASSIFIED_DOCUMENT: "NO_CLASSIFIED_DOCUMENT",
}

#: Reported from the transport's own status. An allowlist rather than a
#: denylist: a key added to `status_dict()` later cannot leak through here
#: without someone naming it.
_BRIDGE_STATUS_KEYS = (
    "connected", "last_poll_ago", "unauth_recent", "unauth_count", "token_id",
)

_MAX_INTEGRATION_MESSAGE = 400

_EMPTY_RUNTIME = {
    "session_id": None,
    "session_storage": None,
    "session_minted_by": None,
    "extension_version": None,
    "protocol_version": None,
}

#: True of every run, however green. A single identify cannot show persistence,
#: cannot compare two channels, and cannot observe a version the wire holds as
#: null.
_ALWAYS_UNVERIFIED = (
    "SCRIPT_ENGINE_SESSION_PERSISTENCE",
    "WEBVIEW_REOPEN_PERSISTENCE",
    "PT_RESTART_SESSION_CHANGE",
    "CROSS_CHANNEL_SESSION_AGREEMENT",
    "EXTENSION_VERSION",
)

_CHANNEL_CLAIM = {"http": "HTTP_V6", "file": "FILE_V6"}


def _non_claims(channel: str, code: int) -> list[str]:
    """What this run did not establish, whatever its verdict.

    The other channel is always on the list: nothing observed here says
    anything about the one that was not used. The declared channel joins it
    unless the run actually produced a successful envelope.
    """
    other = "file" if channel == "http" else "http"
    claims = [_CHANNEL_CLAIM[other], *_ALWAYS_UNVERIFIED]
    if code != EXIT_VALID_V6_OK:
        claims.insert(0, _CHANNEL_CLAIM[channel])
    return claims


def _skeleton(channel: str, timeout_seconds: float) -> dict:
    """The same shape whatever happens, so two runs can be diffed."""
    return {
        "phase": PHASE,
        "channel": channel,
        "timeout_seconds": timeout_seconds,
        "operation": {"operation_rid": None, "op": None},
        "transport": {"preflight_ok": False, "dispatched": False},
        "response": {
            "document_received": False,
            "parse_state": None,
            "status": None,
            "detail": "",
        },
        "runtime": dict(_EMPTY_RUNTIME),
        "observed": {},
        "error": None,
        "integration_error": None,
        "verdict": _VERDICTS[EXIT_NO_CLASSIFIED_DOCUMENT],
        "exit_code": EXIT_NO_CLASSIFIED_DOCUMENT,
        "non_claims": [],
    }


def _finish(result: dict, code: int) -> tuple[dict, int]:
    result["exit_code"] = code
    result["verdict"] = _VERDICTS[code]
    result["non_claims"] = _non_claims(result["channel"], code)
    return result, code


def _refuse(result: dict, detail: str) -> tuple[dict, int]:
    """Preflight said no. Nothing was dispatched, so nothing is claimed."""
    result["transport"]["preflight_ok"] = False
    result["transport"]["preflight_detail"] = detail
    return _finish(result, EXIT_NO_CLASSIFIED_DOCUMENT)


def _safe_message(text: str, secret: str | None) -> str:
    """Redact first, then bound.

    The bridge token rides in the query string of every signed request, so a
    urllib failure can carry it verbatim. Truncating first would leave a prefix
    of it in the output, which is still a leak.
    """
    if secret and secret in text:
        text = text.replace(secret, "<redacted-bridge-token>")
    if len(text) > _MAX_INTEGRATION_MESSAGE:
        text = text[:_MAX_INTEGRATION_MESSAGE] + "..."
    return text


def _bridge_status(transport) -> dict:
    status = transport.status_dict()
    return {key: status[key] for key in _BRIDGE_STATUS_KEYS if key in status}


def _report(result: dict, attempt) -> tuple[dict, int]:
    """Turn one attempt into operator JSON, inventing nothing.

    The identity reported is the one that was *sent*, taken from the attempt's
    own operation rather than read back out of the reply -- a reply that
    answered a different operation must not get to relabel the question.
    """
    result["operation"] = {
        "operation_rid": attempt.operation.operation_rid,
        "op": attempt.operation.op,
    }

    if attempt.no_response_document:
        # All it means. The seam returns `str | None` and carries no
        # provenance, so this is not a timeout and must never be labelled one.
        result["response"]["detail"] = "NO_RESPONSE_DOCUMENT"
        return _finish(result, EXIT_NO_CLASSIFIED_DOCUMENT)

    outcome = attempt.parse_outcome
    result["response"]["document_received"] = True
    result["response"]["parse_state"] = outcome.state.value
    result["response"]["detail"] = outcome.detail

    envelope = outcome.envelope
    if envelope is None:
        # NOT_V6 keeps its text on the legacy path's side of the boundary and
        # is classified here, never routed. Everything else failed closed.
        return _finish(result, EXIT_CLASSIFIED_NOT_OK)

    result["response"]["status"] = envelope.status.value
    result["runtime"] = {
        "session_id": envelope.runtime.session_id,
        "session_storage": envelope.runtime.session_storage.value,
        "session_minted_by": envelope.runtime.session_minted_by.value,
        "extension_version": envelope.runtime.extension_version,
        "protocol_version": envelope.runtime.protocol_version,
    }
    result["observed"] = dict(envelope.observed)
    result["error"] = None if envelope.error is None else {
        "code": envelope.error.code.value,
        "detail": envelope.error.detail,
    }

    if envelope.status is ResultStatus.OK:
        return _finish(result, EXIT_VALID_V6_OK)
    # A protocol-valid report of a failed operation. The document is perfect
    # and the operation did not succeed; this is a validation harness, so that
    # is not a success.
    return _finish(result, EXIT_CLASSIFIED_NOT_OK)


def _identify(
    result: dict, send_and_wait, timeout_seconds: float, secret: str | None,
) -> tuple[dict, int]:
    """One client, one send. The budget reaches the client unaltered.

    The client validates it -- finite and non-negative -- and refuses before
    anything is dispatched, so a bad budget costs no request.
    """
    client = RuntimeProtocolClient(send_and_wait, timeout_seconds=timeout_seconds)
    result["transport"]["dispatched"] = True
    try:
        attempt = client.identify()
    except Exception as exc:
        # Caught only to render it and exit non-zero. It is an integration
        # fault, kept strictly apart from `error`: ENGINE_EXCEPTION asserts the
        # Script Engine ran the operation and reported a failure envelope, and
        # a callable that raised did no such thing.
        result["integration_error"] = {
            "type": type(exc).__name__,
            "message": _safe_message(str(exc), secret),
        }
        return _finish(result, EXIT_NO_CLASSIFIED_DOCUMENT)
    return _report(result, attempt)


def _run_http(result: dict, timeout_seconds: float) -> tuple[dict, int]:
    """The harness owns the server it starts, and stops it however it exits."""
    transport = PacketTracerHttpTransport()
    try:
        connected = transport.start(timeout_seconds=HTTP_START_TIMEOUT_SECONDS)
        result["transport"]["bridge"] = _bridge_status(transport)
        if not connected:
            return _refuse(
                result,
                "the authenticated bridge did not obtain fresh polling before "
                "the readiness window closed; nothing was dispatched",
            )
        result["transport"]["preflight_ok"] = True
        return _identify(result, transport.send_and_wait, timeout_seconds,
                         transport.token)
    finally:
        transport.stop()


def _run_file(result: dict, timeout_seconds: float) -> tuple[dict, int]:
    """A stale heartbeat is a heartbeat fact and stops the run before dispatch."""
    bridge = FileBridge()
    result["transport"]["mailbox"] = str(bridge.dir)
    alive = bridge.pt_alive()
    result["transport"]["pt_alive"] = alive
    if not alive:
        return _refuse(
            result,
            "the Script Engine has not touched its heartbeat recently; this "
            "is the only fact observed, and nothing was dispatched",
        )
    # And it stays only that fact: a fresh heartbeat says the engine is
    # running, not that it speaks V6, not that it will execute this request,
    # and nothing at all about a session.
    result["transport"]["preflight_ok"] = True
    return _identify(result, bridge.send_and_wait, timeout_seconds, None)


def run(*, channel: str, timeout_seconds: float) -> tuple[dict, int]:
    """One declared channel, one operation, one JSON document."""
    result = _skeleton(channel, timeout_seconds)

    isolation = ImportIsolationPreflight(GOVERNED_ROOT).ensure_isolated()
    result["transport"]["import_isolation"] = {
        "state": isolation.state.value,
        "detail": isolation.detail,
    }
    if not isolation.isolated:
        # Before any transport exists. Two module identities of the same files
        # make every enum comparison silently false, and this harness decides
        # its verdict by comparing them.
        return _refuse(result, isolation.render())

    if channel == "http":
        return _run_http(result, timeout_seconds)
    return _run_file(result, timeout_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Operator-only READ-ONLY LIVE harness for the V6 operation "
            "runtime.identify. One explicit channel per invocation; no "
            "fallback, no retry, no mutation."
        ),
    )
    parser.add_argument(
        "--channel",
        required=True,
        choices=("http", "file"),
        help=(
            "Which real transport carries this run: 'http' for the "
            "authenticated bridge, 'file' for the mailbox. Evidence stays "
            "attributable to one channel, so there is no default."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        required=True,
        type=float,
        help=(
            "Budget handed to the transport for this runtime.identify. "
            "Finite and non-negative; no default, because no measurement "
            "backs one for this operation yet."
        ),
    )
    args = parser.parse_args(argv)

    try:
        result, code = run(
            channel=args.channel, timeout_seconds=args.timeout_seconds,
        )
    except ValueError as exc:
        result, code = _refuse(
            _skeleton(args.channel, args.timeout_seconds), str(exc),
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
