"""Typed dispatch outcomes shared by the HTTP and file command channels.

Both channels answered a caller with `str | None` before this module existed,
and `None` had to stand for every way a command could fail to produce a
result: the socket was refused, the request was rejected, the engine raised,
the result was never written, the result was lost. Those are not the same
fact, and the difference decides whether a mutation may be claimed, retried or
called failed. So the channels report them separately here.

Layering: this module imports only domain facts. `file_bridge` and
`live_bridge` import it, never the reverse, so a transport detail can never
reach the domain through the back door.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum

from ...domain.enterprise.models.execution import DispatchFact, ResultFact

#: Free-text detail on an outcome is bounded. A sanitized socket error is a
#: diagnostic, and an unbounded one is an exfiltration surface.
MAX_DETAIL_CHARS = 200


class PostPhase(StrEnum):
    """How far one POST got before it stopped, as the sender can prove it.

    The distinction is the whole point. NOT_SUBMITTED is only for a failure
    that happened before any request byte left this process -- a refused
    connection, a name that did not resolve -- and it is the only phase that
    proves the command cannot run later. SENT means the bytes went out,
    whatever came back. UNDECIDABLE is the fail-closed value for a caller that
    cannot tell the two apart, including a legacy `http_post` that only
    reports a status or `None`.
    """

    __str__ = Enum.__str__

    NOT_SUBMITTED = "not_submitted"
    SENT = "sent"
    UNDECIDABLE = "undecidable"


@dataclass(frozen=True)
class HttpPostOutcome:
    """One POST attempt with the phase it reached."""

    status: int | None
    body: str | None
    phase: PostPhase
    detail: str = ""


@dataclass(frozen=True)
class BridgeDispatchOutcome:
    """What one channel established about one dispatch and its result.

    `dispatch` and `result` are the two independent facts the decision table
    consumes. `disposition` carries the file channel's `RequestDisposition`
    value and is empty for every other channel; it is per-call, so a second
    call never reports the first call's disposition. `detail` is a sanitized,
    bounded diagnostic and never an authority for anything.
    """

    dispatch: DispatchFact
    result: ResultFact
    body: str | None = None
    disposition: str = ""
    detail: str = ""


def detail_text(value: object) -> str:
    """Return one external value as text, before anything bounds it.

    This is the last point at which the text still says exactly what its
    producer said. A caller that has to remove something from it -- a
    resolved credential, say -- acts here, because the folding and the
    truncation below both destroy the substring it would have to match.
    """
    if isinstance(value, BaseException):
        return f"{type(value).__name__}:{value}"
    return str(value or "")


def bound_detail(text: str) -> str:
    """Fold one diagnostic onto a single line within the shared bound."""
    text = " ".join(text.split())
    if len(text) <= MAX_DETAIL_CHARS:
        return text
    return text[: MAX_DETAIL_CHARS - 1] + "…"


def sanitized_detail(value: object) -> str:
    """Reduce one external value to a bounded single-line diagnostic.

    Socket and OS errors carry paths, host names and, on some platforms,
    locale-dependent system text. The type name plus a bounded message is
    enough to debug a phase decision and small enough not to smuggle a
    payload into a stored record. This is NOT a credential boundary: a caller
    whose text can contain a resolved value redacts between `detail_text` and
    `bound_detail` instead of calling this.
    """
    return bound_detail(detail_text(value))
