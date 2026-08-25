"""The authenticated bridge hard stop has to say which failure it is.

Three states reach the same hard stop and need three different actions, and the
runner reported them with one sentence that names none of them:

* the extension is making no requests at all -- the webview's command poll died
  and its status interval kept the UI green, so nothing looks wrong from inside
  Packet Tracer;
* the extension is polling and the bridge rejects it -- a token mismatch;
* the extension polled and went quiet -- a stall, not an absence.

The file bridge is alive in all three, which is exactly why its health may never
be read as an answer about this channel.
"""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    canonical_bridge_polling_error,
)


def test_no_request_at_all_names_the_extension_and_not_the_token():
    reason = canonical_bridge_polling_error({
        "connected": False, "last_poll_ago": None,
        "unauth_count": 0, "token_id": "395ba83c275764b9",
    })

    assert "no request" in reason.casefold()
    assert "mcp builder" in reason.casefold()
    assert "token" not in reason.casefold()


def test_rejected_requests_name_the_token_and_not_the_extension():
    reason = canonical_bridge_polling_error({
        "connected": False, "last_poll_ago": None,
        "unauth_count": 7, "unauth_paths": ["/next"],
        "token_id": "395ba83c275764b9",
    })

    assert "token" in reason.casefold()
    assert "395ba83c275764b9" in reason


def test_a_stalled_poll_is_not_reported_as_an_absent_one():
    reason = canonical_bridge_polling_error({
        "connected": False, "last_poll_ago": 42.0,
        "unauth_count": 0, "token_id": "395ba83c275764b9",
    })

    assert "42" in reason
    assert "no request" not in reason.casefold()


def test_a_connected_bridge_has_nothing_to_diagnose():
    assert canonical_bridge_polling_error({
        "connected": True, "last_poll_ago": 0.0, "unauth_count": 0,
    }) == ""


def test_the_file_bridge_is_never_the_answer_to_this_question():
    """Whatever else it says, it may not offer the other channel as health."""
    reason = canonical_bridge_polling_error({
        "connected": False, "last_poll_ago": None, "unauth_count": 0,
        "token_id": "x", "file_bridge_alive": True,
    })

    assert "file bridge" in reason.casefold()
    assert "says nothing" in reason.casefold()
