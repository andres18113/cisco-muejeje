"""Typed V6 operation encoder. Phase 1A: builds text, executes nothing.

What this is, and what it is not
--------------------------------
This builds the JavaScript for one typed V6 operation and nothing else. It does
not send it, and it has no way to: no transport is imported here.

It is an **encoder**, not an extension dispatcher. The generated text is
evaluated by the deployed V5 executor -- Packet Tracer's own ``runCode`` on the
HTTP channel, the file bridge's ``new Function`` on the file channel -- and the
extension is unchanged. A real typed dispatcher would parse a structured V6
*request* inside the Script Engine; that needs a rebuilt ``.pts``, whose
PTBuilder dependencies this repository does not redistribute. Reserving the term
keeps the code from drifting into the stronger claim.

Read-only by construction
-------------------------
``runtime.identify`` observes and never mutates. It names no mutating Packet
Tracer API, and it cannot emit mutation evidence: no branch here produces a
``mutated`` key, so a read-only result can never be read as a disposition of
some mutation.

The two reads it performs are already proven in this repository rather than
guessed from a reference: ``getActiveFile().getVersion()`` and
``getDeviceCount()`` both appear in the existing project-metadata read. The
version field is named ``pt_file_version`` because that is what it is -- the
version recorded in the open file, not the running application's.

Engine failures become envelopes
--------------------------------
The generated code catches its own exceptions and reports a complete V6 envelope
with ``status: "error"`` and an ``ENGINE_EXCEPTION`` code. The alternative was to
let the exception escape into the legacy ``PT_ERROR:`` guard, which would mean
claiming a complete structured error contract while quietly depending on V5
string semantics underneath. Costing nothing but text, the explicit branch is
the honest one.

Runtime session: storage and origin are different claims
--------------------------------------------------------
The value is seeded into the Script Engine global, first writer wins, because
that object's lifetime is the engine instance -- it survives the webview being
closed and reopened, and both channels can reach it. Persisting state there
across separate dispatches is an established pattern in this codebase.

But the value itself is minted **here**, in Python, so the envelope says
``session_minted_by: "mcp_server"``. Minting it engine-side would need a random
primitive that is not proven available in the Script Engine, and guessing one is
exactly what this repository forbids.

None of that seeding behaviour is established by Phase 1A, which executes
nothing. It stays UNVERIFIED_UNTIL_PHASE_1B.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .runtime_protocol import (
    is_valid_operation_rid,
    new_operation_rid,
    new_session_candidate,
)

#: The one typed operation Phase 1A encodes.
RUNTIME_IDENTIFY = "runtime.identify"

def js_string_literal(value: str) -> str:
    """Encode a Python string as a JavaScript string literal.

    Every dynamic value reaching the payload goes through here. Building the
    literal by hand -- or with an f-string -- is how a device name becomes
    arbitrary code in a script engine.

    JSON string escapes are a subset of JavaScript's, with one classic
    exception: U+2028 and U+2029 are legal raw inside a JSON string and are
    line terminators in JavaScript, so raw they would end the literal
    mid-value. ``json.dumps`` defaults to ``ensure_ascii=True`` and therefore
    escapes them along with every other non-ASCII character, which closes that
    gap here. That default is load-bearing rather than incidental, so a test
    pins the resulting literal as ASCII-only instead of trusting it.
    """
    if not isinstance(value, str):
        raise TypeError("only a string can be encoded as a JS string literal")
    return json.dumps(value)


@dataclass(frozen=True)
class EncodedOperation:
    """One encoded operation: its identities and the text that carries them.

    ``payload`` is a single self-contained statement on one line. The HTTP
    channel joins up to two hundred commands with newlines into one evaluation,
    so a payload that spanned lines or leaked a variable into that shared scope
    could collide with an unrelated command in the same batch.
    """

    operation_rid: str
    op: str
    session_candidate: str
    payload: str


def encode_runtime_identify(
    *,
    operation_rid: str | None = None,
    session_candidate: str | None = None,
) -> EncodedOperation:
    """Encode ``runtime.identify``: report runtime identity, mutate nothing."""
    rid = new_operation_rid() if operation_rid is None else operation_rid
    if not is_valid_operation_rid(rid):
        raise ValueError("operation_rid is not a valid protocol identity")

    candidate = (
        new_session_candidate() if session_candidate is None else session_candidate
    )
    if not isinstance(candidate, str):
        raise TypeError("session_candidate must be a string")

    payload = "".join(
        [
            # `this` at the top of a dispatched body is the Script Engine
            # global; it is captured here and passed in, so the proven pattern
            # is evaluated exactly where it is proven, and nothing leaks into a
            # batch's shared scope.
            "(function(__g){",
            "var __sid=null;",
            "try{",
            "if(!__g.__mcpRuntime){__g.__mcpRuntime={session_id:",
            js_string_literal(candidate),
            ",v:6};}",
            "__sid=__g.__mcpRuntime.session_id;",
            # An unreachable global must degrade to a null session, never to a
            # fabricated one and never to the candidate echoed back as if read.
            "}catch(__e0){__sid=null;}",
            "function __env(__st,__ob,__er){return JSON.stringify({",
            "v:6,",
            "operation_rid:",
            js_string_literal(rid),
            ",op:",
            js_string_literal(RUNTIME_IDENTIFY),
            ",status:__st,",
            "runtime:{session_id:__sid,",
            "session_storage:",
            js_string_literal("script_engine_global"),
            ",session_minted_by:",
            js_string_literal("mcp_server"),
            ",extension_version:null,",
            "protocol_version:6},",
            "observed:__ob,error:__er});}",
            "try{",
            "var __f=ipc.appWindow().getActiveFile();",
            "var __n=ipc.network();",
            "reportResult(__env(",
            js_string_literal("ok"),
            ",{pt_file_version:__f?String(__f.getVersion()||",
            js_string_literal(""),
            "):",
            js_string_literal(""),
            ",device_count:__n.getDeviceCount()},null));",
            "}catch(__e){reportResult(__env(",
            js_string_literal("error"),
            ",{},{code:",
            js_string_literal("ENGINE_EXCEPTION"),
            ",detail:String(__e)}));}",
            "})(this);",
        ]
    )

    return EncodedOperation(
        operation_rid=rid,
        op=RUNTIME_IDENTIFY,
        session_candidate=candidate,
        payload=payload,
    )
