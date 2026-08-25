"""V6 protocol client. Phase 1B-OFFLINE: orchestration, still no transport.

What this module is
-------------------
The three pieces built so far -- the encoder, the send seam, the parser -- with
nothing between them. One ``runtime.identify`` attempt encodes a request, hands
its text to a callable supplied from outside, and classifies whatever comes
back. That is the whole layer.

What it is not
--------------
A transport integration. The callable is injected, and this module imports no
channel, no adapter and no tool surface -- the same seam shape already used at
``enterprise_control_plane_runtime.py:656`` and elsewhere. Whether HTTP or the
file bridge can carry a V6 envelope is not established here, because nothing
here has asked one. Those claims stay UNVERIFIED_UNTIL_PHASE_1B_LIVE, along with
every claim about the Script Engine.

One send, and no policy on top of it
------------------------------------
An attempt calls the seam exactly once. No retry, no fallback to a second
channel, no replay. ``runtime.identify`` is read-only, so a retry would be safe
*here* -- and that is exactly why the discipline is set now rather than later:
the operations that follow will not all be read-only, and a retry hidden inside
a protocol client is a replay nobody chose. Retry belongs to a caller or a
transport policy layer that can name what it is replaying.

The two failures that are not protocol states
---------------------------------------------
**A non-response.** The seam returns ``str | None``, so ``None`` says one thing:
no response document arrived. It does not say timeout, dead channel, non-200,
or foreign protocol -- none of which this seam can observe. The V5 probe path
raises ``TimeoutError`` on the same value (``probe_runtime.py:1173``); that
reads a cause off a value which cannot carry one, and V6 does not copy it. There
is deliberately no parse outcome for a non-response: ``parse_runtime_result`` is
never called, so nothing downstream can mistake silence for a classification.

**A raising callable.** If the injected callable raises instead of returning,
it has broken its own contract, and no response document exists. The exception
propagates unchanged: this module catches nothing. It is emphatically *not*
turned into ``ENGINE_EXCEPTION``, which means the Script Engine ran the
operation and reported a failure envelope -- a statement about an execution that
in this case never happened.

Classification is not routing
-----------------------------
A ``NOT_V6`` document is reported with its legacy text intact and is *not* sent
down the V5 path from here. What to do with a legacy responder is an integration
policy, and it needs a caller that knows which channel it is talking to.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .runtime_operation_encoder import EncodedOperation, encode_runtime_identify
from .runtime_protocol import RuntimeParseOutcome, parse_runtime_result


@dataclass(frozen=True)
class RuntimeProtocolAttempt:
    """One dispatched operation, and what came back if anything did.

    ``operation`` is the request authority. The identity correlated against is
    read from it and not rebuilt, so the pair that went out on the wire is the
    pair the response is measured by.

    ``raw_response`` is ``None`` for exactly one reason: no response document
    arrived. It carries no further diagnosis, because the seam has none to give.

    There is deliberately no state enum here. A parallel transport taxonomy
    would have to invent distinctions -- timeout, channel down, protocol
    unsupported -- that ``str | None`` cannot support, and the repository
    already has vocabularies for the transport-side facts it *can* observe
    (``RequestDisposition``, ``TransportHealthState``, ``BridgePreflightState``).
    Those belong to their own layers and are not folded in here.
    """

    operation: EncodedOperation
    raw_response: str | None
    parse_outcome: RuntimeParseOutcome | None

    def __post_init__(self) -> None:
        if (self.raw_response is None) != (self.parse_outcome is None):
            raise ValueError(
                "an attempt holds a document together with its classification, "
                "or holds neither; a document nobody classified and a "
                "classification of nothing are both impossible outcomes"
            )

    @property
    def no_response_document(self) -> bool:
        """No document arrived.

        The whole meaning. Naming it here keeps callers from reaching for a
        cause the seam never supplied.
        """
        return self.raw_response is None


class RuntimeProtocolClient:
    """Runs one typed V6 operation over a channel it is handed, once."""

    def __init__(
        self,
        send_and_wait: Callable[[str, float], str | None],
        *,
        timeout_seconds: float,
    ) -> None:
        """The budget is required, and belongs to the caller.

        No default: Phase 1B-OFFLINE dispatches nothing real, so any number
        chosen here would be a policy with no measurement behind it. The
        budgets this repository does ship -- ``SAFE_PING_TIMEOUT_S``, for one --
        each sit next to the live measurement that produced them, and V6 has no
        such measurement yet.

        The value is handed to the callable and never interpreted here. This
        layer does not time anything.
        """
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds < 0
        ):
            raise ValueError("timeout_seconds must be non-negative.")
        self._send_and_wait = send_and_wait
        self._timeout = timeout_seconds

    def identify(self) -> RuntimeProtocolAttempt:
        """Encode, send once, and classify a document if one arrived."""
        operation = encode_runtime_identify()

        raw_response = self._send_and_wait(operation.payload, self._timeout)

        if raw_response is None:
            return RuntimeProtocolAttempt(
                operation=operation,
                raw_response=None,
                parse_outcome=None,
            )

        return RuntimeProtocolAttempt(
            operation=operation,
            raw_response=raw_response,
            parse_outcome=parse_runtime_result(
                raw_response,
                expected_operation_rid=operation.operation_rid,
                expected_op=operation.op,
            ),
        )
