"""Pure MCP Runtime Protocol V6 model. Phase 1A: offline, no transport.

What this module is for
-----------------------
The V5 bridge carries executable JavaScript in both directions and answers with
untyped text. Four unrelated error conventions coexist on that wire, results
cannot say which operation they answer, and nothing on it identifies the Packet
Tracer runtime that produced them. This module is the first typed layer over
that wire: one result envelope, one finite status vocabulary, one error schema,
and a parser that classifies a response document without guessing.

Two identities, deliberately separate
-------------------------------------
``operation_rid`` is the V6 protocol identity. It is minted here, echoed inside
the envelope, and its only guarantee is that a document *claims to answer this
operation*.

It is **not** the transport correlation identity. Both deployed transports mint
their own privately and expose it to nobody: the HTTP path mints and consumes
its rid inside one function, and the file path keeps the request filename local.
Nothing in this module can observe or validate either, so nothing here may claim
to. Unifying the two is a later migration that would have to change the shared
transport modules, and it is out of scope.

The parser never sees a failure
-------------------------------
``parse_runtime_result`` accepts ``str``, never ``str | None``. A timeout, a
dead channel and a non-200 all arrive as ``None`` from the transport, and those
are transport outcomes -- they say nothing about which protocol a responder
speaks. A caller holding ``None`` must not consult this layer at all. There is
deliberately no parse state meaning "no response".

Failing closed
--------------
Only ``NOT_V6`` may be handed to the legacy V5 path, and it is deliberately
narrow: it requires the *absence* of a ``v`` key, not merely the absence of
``v == 6``. The repository already returns JSON from many call sites, so "it
parses as JSON" is not evidence of V6. A malformed V6 envelope, a foreign
protocol version and a mismatched correlation are faults to surface, never V5
responders to accommodate -- so they carry no legacy text at all, which makes
the routing gate structural rather than a convention a caller must remember.

What Phase 1A does not establish
--------------------------------
Nothing about the Script Engine. This module sends nothing, so every claim about
runtime-session behaviour -- first-writer-wins seeding, stability across a
webview reopen, change across a Packet Tracer restart -- stays
UNVERIFIED_UNTIL_PHASE_1B. The schema can express those facts; only a live run
can establish them.
"""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

#: The protocol version this module speaks. The discriminator on the wire.
PROTOCOL_VERSION = 6

#: 32 lowercase hex characters. Deliberately *not* imported from the HTTP
#: transport, which happens to use the same shape: coupling the two identities
#: in code is exactly the confusion this module exists to prevent.
_OPERATION_RID_PATTERN = re.compile(r"[0-9a-f]{32}")

#: Session candidates are prefixed so they can never be mistaken for an
#: operation_rid when read out of a log.
_SESSION_CANDIDATE_PREFIX = "ses_"

#: Operations that observe and never mutate. A result for one of these may not
#: carry mutation evidence at all -- APPLIED stays distinct from VERIFIED, and
#: a read-only observation is not a disposition of any mutation.
READ_ONLY_OPERATIONS = frozenset({"runtime.identify"})


class ProtocolParseState(str, Enum):
    """What a response document turned out to be. Never why it did not arrive."""

    VALID_V6 = "VALID_V6"
    #: Not JSON, or JSON with no protocol-version key. The only state that may
    #: be handed to the legacy V5 path.
    NOT_V6 = "NOT_V6"
    #: A ``v`` key that is not this protocol version.
    PROTOCOL_MISMATCH = "PROTOCOL_MISMATCH"
    #: Announces this protocol version and then breaks its schema.
    INVALID_V6 = "INVALID_V6"
    #: Well-formed, but answering some other operation.
    CORRELATION_MISMATCH = "CORRELATION_MISMATCH"


#: The three states that must never reach the legacy path.
_FAIL_CLOSED_STATES = frozenset(
    {
        ProtocolParseState.PROTOCOL_MISMATCH,
        ProtocolParseState.INVALID_V6,
        ProtocolParseState.CORRELATION_MISMATCH,
    }
)


class ResultStatus(str, Enum):
    """A closed set. ``status`` is a discriminator, not free text."""

    OK = "ok"
    ERROR = "error"


class RuntimeErrorCode(str, Enum):
    """Engine-side failure codes carried inside an envelope.

    These are produced by the Script Engine, not by this parser. Phase 1A emits
    only ``ENGINE_EXCEPTION``, from the ``runtime.identify`` encoder's own catch
    branch; the other three describe a typed dispatcher that does not exist yet
    and are reserved so their meanings are fixed before anything can produce
    them. They are declared here and left inert on purpose -- no Phase 1A code
    path constructs one, and none should be given a fabricated call site merely
    to make it reachable.
    """

    UNKNOWN_OPERATION = "UNKNOWN_OPERATION"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    ENGINE_EXCEPTION = "ENGINE_EXCEPTION"


class SessionStorage(str, Enum):
    """Where the runtime session value is held, as claimed by the responder."""

    SCRIPT_ENGINE_GLOBAL = "script_engine_global"


class SessionMintedBy(str, Enum):
    """Who originated the runtime session value.

    Storage and origin are separate facts. Phase 1A holds the value in the
    Script Engine global but mints it in Python, so the honest value is
    ``MCP_SERVER``. ``EXTENSION`` is reserved for the phase where a rebuilt
    ``.pts`` mints it; nothing in Phase 1A can emit it.
    """

    MCP_SERVER = "mcp_server"
    EXTENSION = "extension"


def new_operation_rid() -> str:
    """Mint a V6 protocol identity for one operation."""
    return secrets.token_hex(16)


def is_valid_operation_rid(value: object) -> bool:
    """Whether a value is a well-formed protocol identity."""
    if not isinstance(value, str):
        return False
    return _OPERATION_RID_PATTERN.fullmatch(value) is not None


def new_session_candidate() -> str:
    """Mint a runtime-session candidate for the engine to keep or discard.

    Whether the engine keeps this particular value depends on whether it already
    holds one, which Phase 1A cannot observe.
    """
    return _SESSION_CANDIDATE_PREFIX + secrets.token_hex(12)


@dataclass(frozen=True)
class RuntimeIdentity:
    """The responder's statement about itself."""

    session_id: str | None
    session_storage: SessionStorage
    session_minted_by: SessionMintedBy
    extension_version: str | None
    protocol_version: int


@dataclass(frozen=True)
class EngineError:
    """A structured engine failure. Not an exception; a reported outcome."""

    code: RuntimeErrorCode
    detail: str


@dataclass(frozen=True)
class RuntimeResultEnvelope:
    """One typed V6 result.

    ``mutated`` is absent from this model, not null. Phase 1A carries only a
    read-only operation, and a field that could hold "nothing was mutated" is
    indistinguishable from one that was never populated.
    """

    operation_rid: str
    op: str
    status: ResultStatus
    runtime: RuntimeIdentity
    observed: Mapping[str, Any]
    error: EngineError | None


@dataclass(frozen=True)
class RuntimeParseOutcome:
    """The classification of one response document.

    ``legacy_text`` is populated only for :attr:`ProtocolParseState.NOT_V6`. A
    caller therefore cannot route a fail-closed document to the V5 path even by
    mistake: there is nothing to route.
    """

    state: ProtocolParseState
    envelope: RuntimeResultEnvelope | None = None
    legacy_text: str | None = None
    detail: str = ""

    @property
    def routes_to_legacy_v5(self) -> bool:
        return self.state is ProtocolParseState.NOT_V6

    @property
    def fails_closed(self) -> bool:
        return self.state in _FAIL_CLOSED_STATES


def _not_v6(document: str, detail: str) -> RuntimeParseOutcome:
    return RuntimeParseOutcome(
        state=ProtocolParseState.NOT_V6,
        legacy_text=document,
        detail=detail,
    )


def _invalid(detail: str) -> RuntimeParseOutcome:
    return RuntimeParseOutcome(state=ProtocolParseState.INVALID_V6, detail=detail)


def _is_plain_int(value: object) -> bool:
    """``True`` for a real integer only.

    ``bool`` is a subclass of ``int`` and ``6.0 == 6`` compares equal, so an
    ``isinstance`` check or a bare ``==`` would both admit a document that does
    not actually declare this protocol version.
    """
    return type(value) is int


def _parse_runtime_block(raw: object) -> RuntimeIdentity | str:
    """Return the identity, or a string describing why it is invalid."""
    if not isinstance(raw, dict):
        return "runtime is not an object"

    session_id = raw.get("session_id", ...)
    if session_id is ...:
        return "runtime.session_id missing"
    if session_id is not None and not isinstance(session_id, str):
        return "runtime.session_id is neither a string nor null"

    try:
        storage = SessionStorage(raw.get("session_storage"))
    except ValueError:
        return "runtime.session_storage is not a known storage"

    try:
        minted_by = SessionMintedBy(raw.get("session_minted_by"))
    except ValueError:
        return "runtime.session_minted_by is not a known origin"

    extension_version = raw.get("extension_version", ...)
    if extension_version is ...:
        return "runtime.extension_version missing"
    if extension_version is not None and not isinstance(extension_version, str):
        return "runtime.extension_version is neither a string nor null"

    protocol_version = raw.get("protocol_version")
    if not _is_plain_int(protocol_version) or protocol_version != PROTOCOL_VERSION:
        return "runtime.protocol_version is not this protocol version"

    return RuntimeIdentity(
        session_id=session_id,
        session_storage=storage,
        session_minted_by=minted_by,
        extension_version=extension_version,
        protocol_version=protocol_version,
    )


def _parse_error_block(raw: object) -> EngineError | None | str:
    """Return the error, ``None`` for no error, or a string describing a fault."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return "error is neither an object nor null"

    try:
        code = RuntimeErrorCode(raw.get("code"))
    except ValueError:
        return "error.code is not a declared engine error code"

    detail = raw.get("detail")
    if not isinstance(detail, str):
        return "error.detail is not a string"

    return EngineError(code=code, detail=detail)


def parse_runtime_result(
    document: str,
    *,
    expected_operation_rid: str,
) -> RuntimeParseOutcome:
    """Classify one response document that definitely arrived.

    ``document`` is a ``str`` by contract. A transport that produced no response
    has no document to classify, and must not reach this layer.
    """
    if not isinstance(document, str):
        raise TypeError(
            "parse_runtime_result classifies a response document that arrived; "
            "a transport failure is not a protocol state"
        )
    if not is_valid_operation_rid(expected_operation_rid):
        raise ValueError("expected_operation_rid is not a valid protocol identity")

    try:
        payload = json.loads(document)
    except (ValueError, TypeError):
        return _not_v6(document, "not JSON")

    if not isinstance(payload, dict):
        return _not_v6(document, "JSON, but not an object")
    if "v" not in payload:
        return _not_v6(document, "JSON object without a protocol-version key")

    version = payload["v"]
    if not _is_plain_int(version) or version != PROTOCOL_VERSION:
        return RuntimeParseOutcome(
            state=ProtocolParseState.PROTOCOL_MISMATCH,
            detail=f"responder declares protocol version {version!r}",
        )

    operation_rid = payload.get("operation_rid")
    if not is_valid_operation_rid(operation_rid):
        return _invalid("operation_rid missing or malformed")

    op = payload.get("op")
    if not isinstance(op, str) or not op:
        return _invalid("op missing or not a non-empty string")

    try:
        status = ResultStatus(payload.get("status"))
    except ValueError:
        return _invalid("status is not one of the declared result statuses")

    if "mutated" in payload and op in READ_ONLY_OPERATIONS:
        return _invalid(f"{op} is read-only and may not carry mutation evidence")

    runtime = _parse_runtime_block(payload.get("runtime", ...))
    if isinstance(runtime, str):
        return _invalid(runtime)

    if "observed" not in payload:
        return _invalid("observed missing")
    observed = payload["observed"]
    if not isinstance(observed, dict):
        return _invalid("observed is not an object")

    if "error" not in payload:
        return _invalid("error missing; a null error is explicit, not implied")
    error = _parse_error_block(payload["error"])
    if isinstance(error, str):
        return _invalid(error)

    if (status is ResultStatus.ERROR) != (error is not None):
        return _invalid("status and error disagree")

    envelope = RuntimeResultEnvelope(
        operation_rid=operation_rid,
        op=op,
        status=status,
        runtime=runtime,
        observed=observed,
        error=error,
    )

    if operation_rid != expected_operation_rid:
        return RuntimeParseOutcome(
            state=ProtocolParseState.CORRELATION_MISMATCH,
            detail="the document answers a different operation",
        )

    return RuntimeParseOutcome(
        state=ProtocolParseState.VALID_V6,
        envelope=envelope,
    )
