# MCP Runtime Protocol V6 — Foundation Audit and Design Slice

Status: **DESIGN ONLY — NOT IMPLEMENTED**
Branch: `feature/runtime-protocol-v6-foundation`
Base: `43eba72f18ad4e29e0ff292ebca4dbbd4a47232e` (CP-LIVE checkpoint on `feature/runtime-ripv2`)
Phase: 0 — audit (accepted) · 0.5 — design corrections (this revision)

This document is an audit of the **deployed V5 bridge** and a proposal for the
smallest safe V6 slice. Nothing here was implemented. No `.pts` was rebuilt, no
Packet Tracer instance was touched, and no CP-SCALE run was performed.

Every claim below is cited to source in this checkout. Where the evidence does
not reach, the document says so instead of extrapolating.

## Revision 0.5 — what changed and why

Part 1 (the audit) is unchanged and accepted. Four design defects in the
original Part 3–5 were corrected:

1. **The rid cross-check was an overclaim.** The original text said an in-band
   V6 rid would "cross-check the out-of-band correlation both transports already
   do". It cannot: both transports mint their correlation identity *privately*
   and expose it to nobody. Corrected in §3.3 — `operation_rid` and
   `transport_rid` are now separate contracts, independent for Slice 1.
2. **Protocol detection conflated transport failure with V5.** "No V6 response
   means V5" silently turned a timeout into evidence about a responder.
   Corrected in §3.4 — a four-state protocol parser, with transport outcomes
   kept strictly outside it.
3. **Slice 1 was misnamed a typed dispatcher.** It generates JavaScript in
   Python and runs it on the legacy V5 executor. That is an *encoder*, not an
   extension dispatcher. Renamed throughout; the milestone is reserved.
4. **The proposed slice violated layering.** It planned to call
   `_bridge_send_and_wait`, which is a closure inside `register_tools()` in
   `adapters/mcp/tool_registry.py` (line 1520, nested under line 134) — an
   adapter-layer local that infrastructure must not depend on, and that
   `AGENTS.md` notes tests cannot import at all. Corrected in Part 5 by
   splitting into Phase 1A (pure, offline, new files only) and Phase 1B
   (integration seam, later).

Two further corrections were made to claims about the runtime session and the
error taxonomy; see §3.5 and §3.2.

---

## Part 1 — Current V5 architecture, traced independently

### 1.1 Two channels, one payload format

There are two transports and they are **not** symmetric. The asymmetry is the
single most important fact in this audit, because most of the V6 design follows
from it.

```
HTTP channel                                FILE channel
------------                                ------------
Python                                      Python
  POST /queue?rid=<32hex>                     write req_<pid>_<boot>_<seq>.js  (tmp+os.replace)
  body = JS text                              body = JS text
        |                                            |
  live_bridge.PTCommandBridge._queue          %LOCALAPPDATA%/packet-tracer-mcp/bridge/
        |                                            |
  GET /next  (long-poll <=2s, <=200 cmds)     fileBridgeTick() polls 250ms / 1500ms
        |                                            |
  WEBVIEW  interface.js pollCommands()        SCRIPT ENGINE  main.js
    runBatch() -> $se("runCode", batch)         runFileBridgeCommand(js)
        |                                            |
  PT-NATIVE runCode == new Function(text)     OUR new Function("reportResult", js)
        |                                            |
  reportResult defined by *PYTHON*            reportResult defined by *EXTENSION*
    (report_result_js, prepended)               (local `report` closure)
        |                                            |
  Script Engine -> window.webview             captured string
    .evaluateJavaScriptAsync(XHR)                    |
        |                                      write res_<name>.txt
  POST /result?rid=<32hex>  body=text                |
        |                                      Python polls res, reads, unlinks
  GET /result?rid&wait -> body
```

Sources: `EXTENSION/webview/interface.js:494-541`,
`EXTENSION/script-engine/main.js:133-195`,
`src/packet_tracer_mcp/infrastructure/execution/live_bridge.py:83-134,473-579`,
`src/packet_tracer_mcp/infrastructure/execution/file_bridge.py:187-308`.

### 1.2 HTTP command lifecycle

1. `correlated_http_send_and_wait` mints `rid = secrets.token_hex(16)`
   (`live_bridge.py:66-68,111-134`). **Identity originates in Python, privately.**
2. It prepends `report_result_js(port, token, rid)` — a Python-generated JS
   function definition — to the caller's JS, joined with `;`
   (`live_bridge.py:124`).
3. `POST /queue?rid=...` first calls `register_result(rid)`, which fails closed
   on `duplicate` (409) and `full` (503), then enqueues the **body text**
   (`live_bridge.py:551-577`). Registration precedes enqueue, and a queue
   rejection rolls the registration back (`discard_registered_result`,
   `live_bridge.py:314-319,573-575`).
4. The webview's chained long-poll `GET /next` drains up to
   `MAX_BATCH_COMMANDS = 200` commands joined by `\n`
   (`live_bridge.py:362-374,493-497`).
5. `runBatch()` hands the entire newline-joined batch to `$se("runCode", batch)`
   (`interface.js:527-541`).
6. `runCode` is **not ours**. It is Packet Tracer's own script-engine entry
   point; `SECURITY.md:22` states it is `new Function(scriptText)`. It appears
   nowhere in `EXTENSION/`; the only repo references are comments and docs.
7. The executed `reportResult` runs in the Script Engine and re-enters the
   webview via `window.webview.evaluateJavaScriptAsync(...)` to issue the XHR,
   because the Script Engine has no `XMLHttpRequest`
   (`live_bridge.py:101-108`, `EXTENSION/script-engine/README.md`).
8. `POST /result?rid=...` transitions the slot `pending -> ready`
   (`live_bridge.py:321-336`); the waiting `GET /result?rid&wait` consumes it
   exactly once, marking `consumed` (`live_bridge.py:338-360`).

### 1.3 FileBridge lifecycle

1. `FileBridge._next_name()` mints `<pid>_<boot_hex8>_<seq:06d>`
   (`file_bridge.py:168-173`). **Identity originates in Python, privately, and
   it is the filename** — there is no request id inside the payload.
2. `_write_atomic` writes `tmp` then `os.replace`, and writes **bytes**, not
   text, so Windows never translates `\n` into `\r\n` inside a JS string literal
   (`file_bridge.py:175-185`).
3. `fileBridgeTick()` lists the directory, purges `req_`/`res_` older than
   `FILE_BRIDGE_ORPHAN_S = 60`, then for each `req_*.js`: reads it, executes it,
   writes `res_<name>.txt`, and **only then** removes the request
   (`main.js:144-195`).
4. The engine also touches `alive.txt` every tick; Python reads its mtime as a
   liveness heartbeat with `HEARTBEAT_FRESH_S = 6.0`
   (`main.js:155`, `file_bridge.py:157-164`).
5. On timeout Python **withdraws** the request rather than leaving it
   (`file_bridge.py:267,270-308`), then classifies the outcome into
   `RequestDisposition`.

### 1.4 Token and authentication ownership

- The token file is written by the **MCP server** and read from disk by both
  sides. `bridge_token.get_bridge_token()` on the Python side; `getMcpToken()`
  on the Script Engine side, searching three candidate paths derived from
  `ipc.appWindow().getUserFolder()` (`main.js:43-88`).
- The **webview cannot read files**. It obtains the token by asking the Script
  Engine over `$se("getMcpToken")`, deliberately re-reading on each start and
  never caching it, so a rotated token cannot go stale invisibly
  (`interface.js:36-90,108-112`).
- Every HTTP endpoint except `/ping` requires the token, compared with
  `hmac.compare_digest`, plus a `Host` header check
  (`live_bridge.py:385-402,489-491,530-532`).
- **The file channel has no token by design.** The mailbox lives under a
  user-ACL'd `%LOCALAPPDATA%` directory a browser page cannot write, so the CORS
  vector that forced HTTP authentication does not exist there
  (`file_bridge.py:15-18`, `AGENTS.md` rule 3).

Authority summary: **the MCP server owns the credential; the Script Engine is
the only extension component with filesystem access, so it is the token's
distribution point to the webview.**

### 1.5 Request identity

| | HTTP | File |
|---|---|---|
| Identity | `rid` = 32 hex chars | filename `<pid>_<boot>_<seq>` |
| Minted by | Python (`live_bridge.py:66`) | Python (`file_bridge.py:168`) |
| Carried | out-of-band, in the URL query | out-of-band, in the filename |
| In the payload | **no** | **no** |
| Validated | `_RID_PATTERN.fullmatch` (`live_bridge.py:56,79`) | not applicable |
| **Visible to the caller** | **no** | **no** |

**Neither transport carries the request identity inside the message, and neither
exposes it to its caller.** `correlated_http_send_and_wait` mints and consumes
the `rid` entirely within one function; `FileBridge.send_and_wait` does the same
with the filename; `_bridge_send_and_wait` returns `str | None` and surfaces
neither. This is the structural reason a result cannot self-attribute today —
and the reason §3.3 keeps `operation_rid` and `transport_rid` separate.

### 1.6 Response identity

- HTTP: the `rid` in `POST /result?rid=...`. Correlation is enforced
  server-side and fails closed — `unknown` -> 404, `late` -> 410, `duplicate`
  -> 409 (`live_bridge.py:321-336,538-550`). Consumed/timed-out slots retain
  tombstones for `RESULT_TTL_SECONDS = 120`, and capacity eviction only ever
  removes terminal tombstones, never a pending operation
  (`live_bridge.py:275-301`).
- File: the filename `res_<name>.txt`. A response arriving after cancellation is
  discarded and **never attributed to another operation**
  (`file_bridge.py:310-316`).
- Both response bodies are **untyped text**. There is no envelope.

### 1.7 Execution mechanism

| Path | Executor | Owner | `reportResult` provided by |
|---|---|---|---|
| HTTP | `runCode` -> `new Function(scriptText)` | **Packet Tracer** | Python (`report_result_js`) |
| File | `new Function("reportResult", js)` | **This project** (`main.js:133-142`) | The extension |

This is the asymmetry. On HTTP, the result-return mechanism is injected by
Python into every payload. On File, the extension already owns it. V6 should
converge on the extension owning it in both — but see Q9 for why that cannot be
in the first slice.

Both executors evaluate a **function body**, so `var` declarations are local to
the command; the shared surface is the Script Engine global object.

### 1.8 Error propagation

There are **at least four** distinct, unrelated error conventions in use today:

1. `PT_ERROR: <e>` — injected by the transport guard in
   `_bridge_send_and_wait` (`tool_registry.py:1537-1539`) and by
   `PacketTracerHttpTransport.send_and_wait` (`live_bridge.py:185-189`); also
   produced by the file engine's own catch (`main.js:139`).
2. `ERROR:<e>` — the convention inside most generated payloads, e.g.
   `enterprise_security_runtime.py:571`, `tool_registry.py:4751`.
3. Bare sentinel strings — `'OK'` / `'MISSING'` (`tool_registry.py:1149-1153`).
4. **Silence** — fire-and-forget is wrapped `try{...}catch(__pterr){}`, which
   swallows the error entirely (`tool_registry.py:862-871`). The reason is
   documented and real: an uncaught error inside `runCode` opens a modal
   QMessageBox that freezes the webview and kills polling.

There is also `None` from both `send_and_wait` paths, which conflates
*timeout*, *transport failure*, and *HTTP non-200* into one value
(`live_bridge.py:126-134`, `file_bridge.py:238-268`). **That conflation is a
transport-layer fact, and §3.4 keeps it out of the protocol parser.**

**No error carries a machine-readable code, and no error is distinguishable from
a successful result whose text happens to start with the same prefix.**

### 1.9 Runtime / session identity

**There is none.** Concretely:

- `"proto": 1` exists in the `/ping` response, but it is emitted by *Python*
  about *Python* (`live_bridge.py:482`). The extension never states a version.
- `extension_version` is a **caller-supplied MCP tool parameter**
  (`tool_registry.py:1016,1081`), not an observation. Tests pass `"5"`,
  `"e95"`, `"script-engine"` (`tests/test_e95_deployment_manifest.py:52`,
  `tests/test_meg5_reference_is_authorised.py:57`). It is recorded in the
  deployment manifest as if it were evidence.
- The only `v5` string in the extension is a cosmetic badge
  (`index.html:921`) and a comment (`interface.js:2`). It is not on any wire.
- `session_id` exists only as a Python-side *probe* session
  (`capability_discovery.py:253`), unrelated to the runtime.
- `token_id` (`token_fingerprint`) identifies the **credential**, not the
  runtime instance (`live_bridge.py:237,272`).

Consequence: **the product cannot tell whether two results came from the same
Packet Tracer process.** A PT restart mid-operation is invisible to the
protocol.

### 1.10 Duplicate-command protection

| | HTTP | File |
|---|---|---|
| Duplicate *request* | `register_result` -> `duplicate` -> 409 (`live_bridge.py:307-308,563-565`) | none — names are unique by construction, never checked |
| Duplicate *result* | `put_result` -> `duplicate` -> 409, `late` -> 410 (`live_bridge.py:328-331`) | orphan `res` discarded (`file_bridge.py:310-316`) |
| Duplicate *execution* | prevented only by single-drain of the queue | **NOT PREVENTED** |

The last cell is `TD-TRANSPORT-001`. The engine deletes the request inside a
`try/catch` that swallows failure (`main.js:187`); if that delete fails, the
same payload is re-evaluated on every tick until the 60s orphan purge. For a
`configureIosDevice` that means reapplying configuration repeatedly.

Python-side mitigations exist and are real but partial: `send_and_wait` unlinks
the request after reading the response (`file_bridge.py:260`), and
`collect_completed()` retires answered fire-and-forget requests at the *top* of
the next `send()` (`file_bridge.py:198,208-230`). Two honest gaps remain, both
already written down in `technical-debt.md`: the window between the engine
writing the response and Python unlinking, and the fact that the **most recent**
fire-and-forget request is never retired until another send occurs.

### 1.11 Raw JS execution paths

**Every operation is a raw JS path.** The transport carries executable text and
nothing else; there is no typed channel. `SECURITY.md:24-26` states this
plainly: *"Every tool that builds a topology ultimately generates JavaScript...
The MCP server is a code generator pointed at a script engine; that is the whole
architecture."*

Within that, the distinguishable surfaces are:

| Surface | Location | Governance |
|---|---|---|
| `pt_send_raw(js_code, wait_result)` | `tool_registry.py:2333` | **Gated.** Not registered on the default `enterprise` surface; requires `PT_MCP_PUBLIC_SURFACE=developer-capability-investigation`, ambiguous values fail closed (`public_surface.py:16-31`). `TD-PUBLIC-001` RESOLVED. |
| Typed tool payload builders | ~216 `reportResult` sites across `src/` | Governed by `AGENTS.md` rule 1: every interpolated field via `json.dumps`, never f-strings. |
| `PAGER_GUARD_JS` / `IDLE_GUARD_JS` | `command_dispatch.py:91-122` | Fixed literals; no interpolation. |
| `bootstrapSnippet()` | `interface.js:50-61` | Display-only; the token is `encodeURIComponent`-escaped. |
| `report_result_js` | `live_bridge.py:83-108` | Every field `json.dumps`-encoded; `rid` regex-validated before use. |

### 1.12 Structured vs textual observations

Counted in `src/`: **216** `reportResult` call sites, of which **118** already
use `JSON.stringify`. So structured observation is already the majority
practice — but it is *ad hoc*. Each call site invents its own object shape, its
own error convention, and its own parse on the Python side. There is no shared
envelope, no version field, and no way to tell a structured result from a
textual one without trying `json.loads` and seeing what happens.

**This is also why §3.4 cannot treat "parses as JSON" as evidence of V6.** 118
existing sites already return JSON.

### 1.13 What already exists and must not be reinvented

The codebase already has the vocabulary V6 needs. Reusing it is mandatory;
inventing a parallel one would be the real risk.

- `command_dispatch.py:13-17` — `REQUESTED / DISPATCHED / EXECUTED / OBSERVED`,
  with the explicit rule *"Ninguno implica el siguiente."*
- `RequestDisposition` (`file_bridge.py:80-111`) — with
  `proves_no_execution` returning `False` for **every** value, enumerated by a
  regression (`test_transport_mutation_containment.py:277-287`).
- `TransportHealth` / `select_transport` (`transport_health.py`) — layered
  evidence, `selectable`, pinned-for-operation, informational fallback.
- `BridgePreflightState` (`bridge_preflight.py:12-18`).
- **Dependency injection of a send callable** — `configuration_runtime.py:13`
  takes `send: Callable[[str], bool]`;
  `enterprise_control_plane_runtime.py:655-656` takes both `send` and
  `send_and_wait: Callable[[str, float], str | None]`. This is the existing,
  correct seam for reaching a transport from `infrastructure/execution/` without
  importing an adapter. Phase 1B uses it (Part 5).

---

## Part 2 — Target architecture evaluation

The proposed target:

```
Python RuntimeOperation -> MCP Runtime Protocol -> HTTP / File transport
  -> MCP BUILDER -> Typed Dispatcher -> ipc.* -> Structured Observation -> Python Evidence
```

**Verdict: sound as an end state.** Three observations that shape how to get
there:

1. `_bridge_send_and_wait` (`tool_registry.py:1520-1552`) is the point where the
   transport split currently collapses — but it is an **adapter closure**, not
   an infrastructure seam. The reusable seam is the injected
   `send_and_wait: Callable[[str, float], str | None]` already used by the
   enterprise runtimes (§1.13).
2. The "Typed Dispatcher" box in that diagram is an **extension** component. It
   does not exist and cannot be built from this repository today (Q9). Slice 1
   does not build it and must not be described as if it did (§3.6).
3. The authority boundary is already enforced structurally and must not be
   loosened. In particular: **APPLIED must remain distinct from VERIFIED**, and
   the extension must never emit a verdict. The extension reports *what it
   mutated and what it observed*; Python decides what that means.

Authority split for V6, unchanged from today:

| PYTHON owns | EXTENSION owns |
|---|---|
| planning, policy, topology intent | the exact mutation performed |
| capability decisions | the exact observation read back |
| verification verdicts | runtime identity (session, versions) |
| evidence composition | the structured execution result |

The one boundary that **should** move in V6: runtime identity from Python
(caller-declared `extension_version`) to the extension (observed). **It does not
move in Slice 1** — see §3.5, where the honest position is that Slice 1 keeps
minting in Python and says so.

---

## Part 3 — V6 foundation proposal, corrected

### 3.0 Classification

| Item | Classification | Rationale |
|---|---|---|
| `protocol_version` | **REQUIRED_FOR_FIRST_SLICE** | Without it nothing can be detected or rolled forward. One integer. |
| `operation_rid` (protocol identity) | **REQUIRED_FOR_FIRST_SLICE** | Minted by the V6 caller, echoed in the envelope. Independent of transport identity (§3.3). |
| `transport_rid` unification | **LATER** | Requires changing `live_bridge.py` / `file_bridge.py`. Forbidden now (§3.3). |
| JSON result envelope | **REQUIRED_FOR_FIRST_SLICE** | The whole point. Everything else rides on it. |
| Protocol parse states | **REQUIRED_FOR_FIRST_SLICE** | The correction in §3.4; without it detection is dishonest. |
| Structured error model | **REQUIRED_FOR_FIRST_SLICE** (parser layer only) | Engine-layer codes are reserved-not-producible in 1A (§3.2). |
| `runtime_session_id` contract | **REQUIRED_FOR_FIRST_SLICE** (contract + encoder) | Behaviour is LIVE-validated in 1B, not claimed in 1A (§3.5). |
| `runtime.identify` JS encoder | **REQUIRED_FOR_FIRST_SLICE** | The operation the envelope is prototyped against. |
| Transport integration | **PHASE 1B** | Layering (Part 5); also forbidden while CP-SCALE is open. |
| JSON *request* envelope | **LATER** | Needs an engine-side parser in the `.pts` — blocked (Q9). |
| Extension typed dispatcher | **LATER** | The actual architectural milestone. Blocked (Q9). Not claimed by Slice 1 (§3.6). |
| `extension_version` observed | **LATER** | Requires the `.pts` to state it. Stays `null`. |
| requested / mutated / observed separation | **LATER** (envelope reserves the fields) | Slice 1 is read-only, so `mutated` is structurally absent. |
| Raw-JS policy | **LATER** (already governed) | `TD-PUBLIC-001` is RESOLVED. V6 adds a rule, not a mechanism. |
| FileBridge claim lifecycle (`run_<name>`) | **LATER — blocked** | Needs a `.pts` rebuild (Q4, Q9). |
| V5 compatibility boundary | **REQUIRED_FOR_FIRST_SLICE** | Slice 1 must be additive and invisible to every existing caller. |
| Removing V5 code | **NOT_NEEDED** (and forbidden now) | CP-SCALE is open. |
| Migrating product callers | **NOT_NEEDED** for Slice 1 | Later, separate decision. |
| Transactional / atomic file protocol | **NOT_NEEDED** | Cannot be honestly claimed (Q4). |
| New bridge endpoints | **NOT_NEEDED** | `/queue` + `/result` already carry everything; `AGENTS.md` rule 3. |

### 3.1 Result envelope (proposed)

```json
{
  "v": 6,
  "operation_rid": "<echoed protocol identity>",
  "op": "runtime.identify",
  "status": "ok",
  "runtime": {
    "session_id": "<value held by the Script Engine global>",
    "session_storage": "script_engine_global",
    "session_minted_by": "mcp_server",
    "session_seed_owner": true,
    "extension_version": null,
    "protocol_version": 6
  },
  "observed": {},
  "error": null
}
```

- `operation_rid` is the **protocol** identity (§3.3). It is *not* the transport
  correlation id and must never be described as validating one.
- `mutated` is **absent**, not `null`, for a read-only operation. A read-only
  encoder has no code path that can emit the key at all — see Part 5, test 7.
  The field is reserved in the schema for mutating operations in a later phase.
- `session_minted_by: "mcp_server"` is the honest value for Slice 1 (§3.5). It
  becomes `"extension"` only when the `.pts` mints it.
- `session_seed_owner` records whether *this* caller's injected candidate is the
  one the engine kept. It is only computable once a response exists, so it is a
  **Phase 1B** field; the 1A schema reserves it.
- `extension_version: null` is the honest value until the `.pts` states it. It
  must **not** be back-filled from the caller-supplied MCP parameter.

### 3.2 Error model — two layers, separately scoped

The original single taxonomy mixed a protocol-parser concern with a Packet
Tracer engine concern. They are separated, and their producibility in Phase 1A
is stated rather than assumed.

**Layer A — protocol/parser outcomes. Produced entirely in Python. PRODUCIBLE IN
PHASE 1A.** These are the parse states of §3.4, not `error.code` values; they
describe what happened to a *response document*, and they never reach the
envelope's `error` field.

**Layer B — engine error codes. Produced by the Script Engine inside the
envelope. RESERVED BY THE SCHEMA, NOT PRODUCIBLE IN PHASE 1A**, because Phase 1A
performs no transport call and therefore never receives an engine error.

| Code | Layer | Producible in 1A |
|---|---|---|
| `UNKNOWN_OPERATION` | B — engine | **No** (reserved) |
| `INVALID_ARGUMENTS` | B — engine | **No** (reserved) |
| `TARGET_NOT_FOUND` | B — engine | **No** (reserved) |
| `ENGINE_EXCEPTION` | B — engine | **No** (reserved) |

`PROTOCOL_MISMATCH` was moved **out** of the engine layer. A responder speaking
a different protocol version is a parser observation, not an engine failure, so
it is a parse state (§3.4), not an `error.code`.

**Testing rule.** Reserved codes must **not** be given fabricated call sites to
make them "reachable". Phase 1A asserts the opposite property: that the
`runtime.identify` encoder emits none of them and that no 1A code path
constructs one. A reserved code becoming producible is a Phase 1B/2 event with
its own test.

Python-side outcomes that are neither layer keep their own existing vocabulary
and must not be folded in: `RequestDisposition`, `TransportHealthState`,
`BridgePreflightState`.

### 3.3 `operation_rid` vs `transport_rid` — CORRECTED

The original design claimed an in-band rid would cross-check the transports'
existing correlation. **It cannot.** Evidence (§1.5):

- `correlated_http_send_and_wait` mints `rid = next_rid()` at
  `live_bridge.py:122` and consumes it at `live_bridge.py:129` — it is never
  returned, never logged to a caller, never a parameter.
- `FileBridge.send_and_wait` calls `self._next_name()` at `file_bridge.py:242`
  and keeps the name local — same.
- `_bridge_send_and_wait(js_call, timeout, channel) -> str | None` surfaces
  neither.

Making them cross-checkable would require changing `live_bridge.py` and
`file_bridge.py` — the two files CP-SCALE depends on most, and the two this
phase forbids touching.

Two independent contracts, therefore:

| | `operation_rid` | `transport_rid` |
|---|---|---|
| Layer | V6 protocol | legacy V5 transport |
| Minted by | the V6 caller (`runtime_protocol`) | `live_bridge` / `file_bridge`, privately |
| Visible to | the V6 caller and the envelope | nobody outside its own function |
| Carried | **in-band**, inside the envelope | out-of-band (URL query / filename) |
| Purpose | proves *this response answers this operation* | proves *this HTTP/file result answers this transport request* |
| Relationship in Slice 1 | **none — independent** | **none — independent** |

What `operation_rid` honestly buys in Slice 1: a response that is well-formed V6
but answers a *different* operation is detected and fails closed
(`CORRELATION_MISMATCH`, §3.4). That is a real property, and it is achievable
with zero changes to shared transport code.

What it does **not** buy: any statement about transport-level correlation. The
transports' own correlation remains correct and untouched; V6 simply cannot see
it, and must not pretend to.

**RID_UNIFICATION = LATER.** A future migration may thread a single identity
through both layers by giving the transports an optional caller-supplied id.
That is a change to `live_bridge.py` and `file_bridge.py`, gated on CP-SCALE
being closed, and out of scope here.

### 3.4 Protocol detection — CORRECTED

The original rule — *"a responder that does not answer V6 is a V5 responder"* —
turned a timeout into a claim about a responder. Corrected by separating two
questions that were collapsed:

**Question 1 (transport): did a response document arrive at all?** Answered by
the transport, outside the protocol parser. `None` from `send_and_wait` already
conflates timeout, transport failure and non-200 (§1.8). The parser is **never
invoked** on a non-response. There is no parse state meaning "no response", by
construction.

**Question 2 (protocol): given a response document, what is it?** Answered by
the parser, on a `str` that definitely arrived:

| State | Condition | Handling |
|---|---|---|
| `VALID_V6` | parses as a JSON object, `v == 6`, schema-valid, `operation_rid` matches the expected value | consume as V6 |
| `NOT_V6` | not JSON, **or** a JSON value with no `v` key | legacy V5 text/JSON — hand to the existing V5 path unchanged |
| `PROTOCOL_MISMATCH` | JSON object with `v` present and `v != 6` | **fail closed** |
| `INVALID_V6` | `v == 6` but the envelope is malformed (missing/ill-typed required fields) | **fail closed** |
| `CORRELATION_MISMATCH` | `v == 6`, schema-valid, `operation_rid` does not match | **fail closed** |

Two rules that make this honest:

1. **Fail closed means fail closed.** `INVALID_V6`, `CORRELATION_MISMATCH` and
   `PROTOCOL_MISMATCH` must **never** fall back to V5 parsing. A broken V6
   responder is a fault to surface, not a V5 responder to accommodate.
2. **`NOT_V6` is the only state that routes to V5**, and it is deliberately
   narrow: it requires the absence of a `v` key, not merely the absence of
   `v == 6`. This is what keeps the 118 existing `JSON.stringify` sites (§1.12)
   from being misclassified in either direction.

`TRANSPORT_FAILURE_SEPARATION`: the parser's input type is `str`, never
`str | None`. A caller that has `None` has a transport outcome and must not
consult the protocol layer at all. Phase 1A can enforce this at the signature.

### 3.5 Runtime session — storage owner vs minting origin, CORRECTED

The original text said the session id would be *"Script-Engine-scoped"* in a way
that read as extension-origin identity. It is not, and the distinction matters.

**Storage owner — PROPOSED: the Script Engine global.** The value is held on
`this.__mcp*`, whose lifetime is the Script Engine instance, i.e. as long as PT
is open with the extension loaded. That lifetime is what the contract needs: it
survives the webview closing and reopening, and it is reachable from both
transports.

Evidence that cross-command global persistence is real: `this.__mcpE8Http` is
written at `enterprise_security_runtime.py:566` and read back in **separate,
later** dispatches at `:581` and `:591`; `this.__mcpE6HttpClients` behaves the
same at `enterprise_service_runtime.py:384-406`. Both run through the same
send/send-and-wait seam, so the behaviour holds on both transports.

**This is strong evidence, not proof for our path.** It establishes the property
for *those* payloads. `AGENTS.md` is explicit that anything about the PT
webview/script-engine boundary cannot be verified from tests. So the storage
behaviour is a **LIVE-validation item for Phase 1B**, and Phase 1A asserts
nothing about it.

**Minting origin — Slice 1: Python. Stated, not disguised.** The encoder emits a
first-writer-wins seed:

```
this.__mcpRuntime = this.__mcpRuntime || { session_id: <python-minted literal>, v: 6 };
```

Every dispatched command carries a *fresh* candidate; only the first one in a
given engine instance is kept. So the value's origin is the MCP server, and the
envelope says `session_minted_by: "mcp_server"`.

Why not mint in the engine instead? Because the primitives are not proven.
Measured in this checkout:

- `Date.now()` and `Math.floor()` **are** used in the Script Engine
  (`main.js:155,161`), so they exist there.
- `Math.random()` is **never used in any of our code**. The only occurrences in
  the repository are inside the vendored `EXTENSION/webview/bootstrap.bundle.min.js`,
  which runs in the **webview**, not the Script Engine.

Engine-side minting from `Date.now()` alone would be a millisecond timestamp —
adequate for distinguishing engine instances in practice, but it cannot be
validated offline at all, and adopting an unproven `Math.random()` would violate
the spirit of `AGENTS.md` rule 6. So engine-side minting is documented as the
LATER option and not chosen now.

**What the contract honestly proves, once 1B validates it:** *the value returned
identifies one Script Engine global, stable from first V6 contact until that
engine instance ends.* It does **not** prove PT start time, and it does not make
the identity extension-originated. `session_seed_owner` additionally tells a
caller whether it won the seed race — informative when several MCP processes
share one PT.

**Degradation rule:** if the global is unreachable on some evaluation path, the
operation must report `session_id: null`. It must never fabricate a value, and
it must never echo the injected candidate as if it had been read back.

`extension_version` remains `null` throughout.

### 3.6 Naming — Slice 1 is not a typed dispatcher

Slice 1 generates JavaScript in Python and hands it to the **legacy V5
executor** (`runCode` on HTTP, `runFileBridgeCommand` on File). No structured
request is parsed by the extension; the extension is unchanged.

| Term | Means | Status |
|---|---|---|
| **typed V6 operation encoder** | Python builds a typed operation into a JS payload whose result is a V6 envelope | **Slice 1 (Phase 1A)** |
| **V6 result envelope parser** | Python classifies a response document into §3.4 states | **Slice 1 (Phase 1A)** |
| **extension typed dispatcher** | the Script Engine parses a structured V6 *request* and routes it to a typed handler | **LATER — blocked by Q9** |

`SLICE1_ARCHITECTURE_NAME` = *typed V6 operation encoder + result envelope
parser (prototype)*. The module is named `runtime_operation_encoder.py`, not
`runtime_dispatcher.py`, so the code cannot drift into the stronger claim.

---

## Part 4 — Critical questions, answered from source

### Q1 — Where should `runtime_session_id` originate: WebView or Script Engine?

**Storage: Script Engine, decisively. Minting in Slice 1: Python, explicitly.**
See §3.5 for the full corrected contract.

Lifetimes settle the storage question:

| Component | Lifetime | Evidence |
|---|---|---|
| WebView | only while the window is open; can reload independently | `interface.js` header comments; `file_bridge.py:4-9` |
| Script Engine | the whole time PT is open, window or not | `main.js:352-362`; `EXTENSION/script-engine/README.md` |

A webview-held id would reset when the user closes and reopens the window,
falsely signalling a new runtime while PT and its network model persisted
unchanged. It would also be *absent* on the file channel, which has no webview
at all — so it could not be a protocol invariant.

The Script Engine is also the only side that can stamp it on **both**
transports, because `reportResult` executes there in both cases (§1.7).

The minting origin is a separate question, and for Slice 1 the honest answer is
Python (§3.5). Engine-side minting is blocked less by architecture than by
proof: `Math.random()` is unproven in the Script Engine.

### Q2 — Can HTTP and File transport share one dispatcher cleanly?

**Yes for the *encoder*; the shared piece is smaller than originally claimed.**
In both channels the executed body has a function named `reportResult(d)` in
scope — supplied by Python on HTTP (`live_bridge.py:101-108`), by the extension
on File (`main.js:133-142`). A payload that ends with
`reportResult(JSON.stringify(envelope))` is therefore transport-agnostic.

Three differences that must be respected rather than abstracted away:

1. **Batching.** HTTP joins up to 200 commands with `\n` and evaluates them in
   one `runCode` (`live_bridge.py:369`, `interface.js:527-541`). The file
   channel is strictly one request per file. A typed op must be a self-contained
   statement that survives being concatenated with others.
2. **Correlation is private to each transport and stays that way.** The original
   answer claimed in-band rid "unifies the check". Corrected: `operation_rid`
   is an independent protocol identity and validates nothing about transport
   correlation (§3.3).
3. **Delivery guarantees differ** (Q3). One encoder, two honest guarantees — the
   envelope must not paper over that.

Note also that the natural integration point is **not** `_bridge_send_and_wait`:
that is an adapter closure (Part 5). The seam is the injected
`send_and_wait: Callable[[str, float], str | None]` already used at
`enterprise_control_plane_runtime.py:656`.

### Q3 — Strongest honest delivery guarantee FileBridge can support?

**At-least-once, with a bounded and named ambiguity window. Nothing stronger.**

The engine writes the response *before* deleting the request, and that delete is
inside a `try/catch` that swallows failure (`main.js:186-187`). So a failed
delete re-executes the same payload every tick until the 60s orphan purge.

The Python side narrows this — `send_and_wait` unlinks after reading
(`file_bridge.py:260`), `collect_completed()` retires answered fire-and-forget
at the top of the next send (`file_bridge.py:198`) — but two gaps survive, both
already recorded in `technical-debt.md`: the write-response-to-unlink window,
and the most-recent fire-and-forget that is never retired until another send
occurs.

For cancellation, the ceiling is lower still and already correctly named. The
deployed engine publishes **no claim marker**, so "read and evaluating" is
indistinguishable from "never read" through the filesystem, and there is no
proven upper bound on an in-progress evaluation. Hence
`WITHDRAWN_NO_EXECUTION_OBSERVED` — an observation, not a guarantee — and
`proves_no_execution` returning `False` for every disposition
(`file_bridge.py:102-111`).

**V6 must not claim more.** If the envelope ever grows a field that reads as
"delivered exactly once", it is wrong.

### Q4 — Can `req_ -> run_ -> res_` be implemented without claiming false atomicity?

**The design is sound and already written down. It cannot be implemented from
this repository, and it is not what Slice 1 should do.**

`file_bridge.py:40-48` specifies it: the Script Engine writes `run_<name>`
*before* reading the request and removes it on completion. Python, after a
successful `unlink` of the request, checks the marker — **absent proves
evaluation had not begun**, because a later `getFileContents` would fail on an
already-withdrawn file. It deliberately uses only APIs confirmed present on
`systemFileManager` (`writePlainTextToFile`, `removeFile`) and specifically
**not** `renameFile`, which is not on the measured surface.

What it would honestly buy: splitting `WITHDRAWN_NO_EXECUTION_OBSERVED` into a
*provable* no-execution case and a residual ambiguous one. That is a real gain.

What it still would **not** buy: atomicity. There is no transaction. Three
separate filesystem operations with no ordering guarantee against a crash
between them. `os.replace` is atomic *per file* (`file_bridge.py:175-185`); the
*protocol* is not, and no arrangement of these APIs makes it so.

Blocked because it requires recompiling the `.pts`, and the PTBuilder reference
files are `.gitignore`d and not redistributed (Q9). Verified in this checkout:
`EXTENSION/script-engine/` contains only `main.js` and `README.md`.

### Q5 — Smallest typed operation that proves the design without touching CP-SCALE?

**`runtime.identify` — read-only, mutation-free, and the operation whose entire
purpose is the thing the slice establishes.** What it proves is now scoped
correctly: it proves the **encoder and envelope**, not an extension dispatcher
(§3.6).

Constraints it satisfies: read-only; only APIs already proven in this repo
(`AGENTS.md` rule 6 forbids guessing a PT signature); no shared state with any
CP-SCALE path; exercises every envelope field that Phase 1A defines.

Encoder output shape (Phase 1A produces the **text**; nothing executes it):

```
this.__mcpRuntime = this.__mcpRuntime || { session_id: <json.dumps(candidate)>, v: 6 };
reportResult(JSON.stringify({
  v: 6,
  operation_rid: <json.dumps(operation_rid)>,
  op: "runtime.identify",
  status: "ok",
  runtime: { session_id: this.__mcpRuntime.session_id,
             session_storage: "script_engine_global",
             session_minted_by: "mcp_server",
             extension_version: null,
             protocol_version: 6 },
  observed: { pt_file_version: <String(getActiveFile().getVersion()||"")>,
              device_count: <ipc.network().getDeviceCount()> },
  error: null
}));
```

Both reads are proven in-repo: `getActiveFile().getVersion()` at
`tool_registry.py:4746`, `ipc.network().getDeviceCount()` at
`tool_registry.py:4748`.

Honest limits, stated up front rather than discovered later:

- The id is seeded on the **first V6 command of an engine instance**, not at
  extension load. It proves "same Script Engine global since first V6 contact".
- The candidate value is **minted in Python** (§3.5). Do not describe the
  resulting identity as extension-originated.
- `getActiveFile().getVersion()` is the **file's** PT version, not the running
  application's. The field is named `pt_file_version` for that reason.
- `extension_version` stays `null`; the caller-supplied MCP parameter must not
  fill it.
- Whether `this` is the Script Engine global on every evaluation path is
  **strong evidence, not proof** (§3.5) and is a Phase 1B LIVE-validation item.
  Degrade to `session_id: null`; never fabricate.
- **Phase 1A executes none of this.** It produces and tests the encoded text.

### Q6 — How should legacy V5 coexist with V6 during migration?

**Additively, with V6 as an opt-in second reader and V5 untouched as the
default. No shared mutable state, and no protocol conclusion drawn from a
transport failure.**

1. V5 payload builders, guards, and prefixes are **frozen**. Not deprecated, not
   rewritten — frozen.
2. V6 adds new modules. It does not change `_bridge_send_and_wait`'s behaviour
   or signature, and in Phase 1A it does not reference it at all (Part 5).
3. Detection follows §3.4: a response document is classified into one of five
   states, and **only `NOT_V6` routes to the V5 path**. `INVALID_V6`,
   `CORRELATION_MISMATCH` and `PROTOCOL_MISMATCH` fail closed.
4. A transport failure (`None`) is **not** a protocol state and never reaches
   the parser. It says nothing about which protocol the responder speaks.
5. `protocol_version` is established by *observation*, never assumed. A
   responder that returns a document with no `v` key is a V5 responder; that is
   a normal state, not an error.
6. No caller migrates in Slice 1.
7. V5 removal is gated on CP-SCALE being closed **and** every caller migrated.
   Neither is true.

### Q7 — What exact raw-JS paths must remain legacy-only?

Given that the transport *is* a raw-JS path (§1.11), "legacy-only" means: paths
that must never be reachable *through a typed V6 operation*, and must never
produce a V6 envelope.

| Path | Rule |
|---|---|
| `pt_send_raw` (`tool_registry.py:2333`) | **Never** gains a typed op, never emits a V6 envelope, never gains a `runtime` block. It must remain unable to masquerade as a typed mutation — the property `TD-PUBLIC-001` was closed on. Stays behind `PT_MCP_PUBLIC_SURFACE=developer-capability-investigation`. |
| `bootstrapSnippet()` display string (`interface.js:50-61`) | Legacy V5 HTTP bootstrap. Not a V6 surface. |
| `report_result_js` (`live_bridge.py:83-108`) | Stays as the V5 HTTP result mechanism. V6 rides *on top of* it rather than replacing it; replacing it needs a `.pts` change. |
| `_js_guard` silent catch (`tool_registry.py:862-871`) | Stays for V5 fire-and-forget. V6 must **not** adopt a silent catch: an error becomes a structured `error`, never silence. |
| `PAGER_GUARD_JS` / `IDLE_GUARD_JS` (`command_dispatch.py:91-122`) | Terminal-dispatch internals. Out of V6 scope entirely; do not fold IOS dispatch into the runtime protocol. |
| Every existing typed payload builder | Legacy until individually migrated. `AGENTS.md` rule 1 (`json.dumps` per field, never f-strings) applies unchanged to any V6 code. |

### Q8 — Which current tests can protect backward compatibility?

All of these exist and pass today. **They are the V6 regression net: they must
keep passing unchanged, and a V6 change that requires editing one of them is a
V6 design error, not a test that needs updating.**

| Test | Protects |
|---|---|
| `test_bridge_results.py` (11 tests) | rid correlation, late/duplicate isolation, tombstone bounds, wait ceiling, `report_result_js` shape (`:241`) |
| `test_bridge_security.py` | token enforcement, Host validation, body limits — drives a real `PTCommandBridge` on an ephemeral port |
| `test_file_bridge.py` (6) | round-trip, fire-and-forget consumption, heartbeat, **exact-bytes newline writing** (`:111`), no partial reads under concurrency |
| `test_file_bridge_lifecycle.py` (13) | withdrawal, `EXECUTED_LATE`, name non-reuse across restarts, stale-response isolation, `test_no_disposition_claims_the_command_never_ran` (`:176`) |
| `test_transport_mutation_containment.py` (12) | every dispatching module is a classified family; `proves_no_execution` is `False` for every disposition; only read-only retries exist |
| `test_fire_and_forget_surface.py` | `pt_send_raw` absent from the enterprise surface; exact developer opt-in; ambiguous env values fail closed |
| `test_fire_and_forget_taxonomy.py` (14) | every family classified; transport safety not claimed absolute |
| `test_command_dispatch_integrity.py` (735 lines) | REQUESTED/DISPATCHED/EXECUTED/OBSERVED separation |
| `test_applied_normative_contract.py` | **APPLIED is not VERIFIED** — the boundary V6 must not blur |
| `test_bridge_preflight.py` | readiness states, no alternative bridges/tokens |
| `test_worktree_isolation.py` | no bare `import packet_tracer_mcp` in tests |

Two caveats. First, `test_transport_mutation_containment.py:289-313` sweeps
`src/packet_tracer_mcp` for modules that dispatch mutations and requires each to
be a classified family — **a new V6 module will trip it unless it is registered
or is provably non-mutating.** Phase 1A performing no dispatch at all, and
`runtime.identify` being strictly read-only, is what keeps this clean. Second,
this worktree has **no `.venv`**; per `AGENTS.md` the suite must run on the
checkout-local interpreter, so one must be created here before any V6 test run.

### Q9 — Which pieces depend on PTBuilder or untracked external files?

| Piece | Dependency | Status in this checkout |
|---|---|---|
| Rebuilding the `.pts` | `userfunctions.js`, `devices.js`, `links.js`, `modules.js`, `runcode.js`, `windows.js` — PTBuilder reference copies | **ABSENT.** `.gitignore` excludes `EXTENSION/script-engine/*.js` except `main.js`; verified — only `main.js` and `README.md` are present. PTBuilder carries **no license**, so they are not redistributed. |
| `runCode` (the HTTP executor) | Packet Tracer built-in | Not ours, not in this repo, not modifiable |
| Any `main.js` change | requires the above to package | **BLOCKED** |
| **Extension typed dispatcher** | requires a `main.js` change | **BLOCKED** — the reason §3.6 reserves the term |
| `run_<name>` claim marker (Q4) | requires a `main.js` change | **BLOCKED** |
| Extension-reported `extension_version` | requires a `main.js` change | **BLOCKED** |
| JSON *request* envelope parsing in the engine | requires a `main.js` change | **BLOCKED** |
| Engine-side session minting | `Math.random()` unproven in the Script Engine (§3.5) | **NOT CHOSEN** — proof gap, not a hard block |
| `installMcpHelpers()` improvements | requires a `main.js` change | **BLOCKED** |
| **Phase 1A (encoder + parser)** | **none** | **NOT BLOCKED** — this is why 1A is shaped this way |
| `infrastructure/generator/ptbuilder_generator.py` | name only; PTBuilder-*style* JS | Tracked, fine |

Also untracked/environmental: `.venv/`, `projects/`, `data/`, `.claude/`,
`graphify-out/`, the bridge token file and mailbox under `%LOCALAPPDATA%`.

### Q10 — What would be dangerous to implement while CP-SCALE is still open?

Ranked by blast radius.

1. **Rebuilding or reinstalling the `.pts`.** Doubly blocked — dependencies
   absent (Q9) — and it would interrupt a live CP-SCALE run at an arbitrary
   point. Any in-flight fire-and-forget would land in an undefined state.
2. **Changing `_bridge_send_and_wait`, `_js_guard`, `_channel_send`, or
   `_pick_channel`.** Every CP-SCALE mutation and readback passes through these
   (`tool_registry.py:862-1009,1520-1552`). **Phase 1A does not touch
   `tool_registry.py` at all.**
3. **Changing `live_bridge.py` or `file_bridge.py` to expose or unify the
   transport rid.** This is exactly what §3.3 defers. It would alter the two
   files CP-SCALE depends on most.
4. **Changing `report_result_js` or the `PT_ERROR:` / `ERROR:` prefixes.** ~216
   call sites parse these by prefix. A prefix change is a silent
   mass-misclassification.
5. **Touching the shared mailbox lifecycle.** CP-SCALE and any V6 experiment
   share one directory. `_purge_own_stale` is deliberately scoped to
   `<pid>_<boot>_` and must stay that way (`file_bridge.py:318-335`) — a broader
   purge would delete a live CP-SCALE request.
6. **Any mutating V6 probe.** Would enter the shared PT network model. Phase 1A
   sends nothing at all.
7. **Changing transport selection or health semantics.** `select_transport`
   pins a transport for a whole operation and forbids replaying an ambiguous
   mutation (`transport_health.py:86-128`). Perturbing it mid-run could re-route
   a CP-SCALE operation across channels — precisely what the design forbids.
8. **Adding a bridge endpoint.** `AGENTS.md` rule 3; also a restart of the HTTP
   bridge would drop the queue.
9. **Running the suite with the wrong interpreter.** `AGENTS.md` documents that
   the main-checkout `.venv` silently resolves `packet_tracer_mcp` to the *main
   checkout* — a V6 test run could import CP-SCALE's tree.
10. **`graphify update .`** — writes to a shared, gitignored working directory.

---

## Part 5 — Implementation split, corrected

The original single slice planned to call `_bridge_send_and_wait`. That is an
**adapter-layer closure**: `tool_registry.py:1520`, indented inside
`register_tools()` at `tool_registry.py:134`. A module under
`infrastructure/execution/` depending on it would invert the layering, and
`AGENTS.md` states such helpers *"cannot be imported by tests"* at all. The
slice is therefore split.

### Phase 1A — pure protocol model (the approved slice)

**Scope: new files only. No transport. No adapter. No live caller. No Packet
Tracer. No CP-SCALE surface.**

Contents:

1. `runtime_protocol.py` — `PROTOCOL_VERSION = 6`; `operation_rid` generation
   and validation; the result-envelope model; the five-state parser of §3.4
   over a `str` input; the two-layer error model of §3.2 with engine codes
   declared-but-inert.
2. `runtime_operation_encoder.py` — builds the `runtime.identify` payload text
   (Q5), every interpolated field via `json.dumps` per `AGENTS.md` rule 1.
3. Offline tests. Nothing is executed anywhere.

`PHASE1A_FILES`:

| File | Change |
|---|---|
| `src/packet_tracer_mcp/infrastructure/execution/runtime_protocol.py` | **new** |
| `src/packet_tracer_mcp/infrastructure/execution/runtime_operation_encoder.py` | **new** |
| `tests/test_runtime_protocol_v6.py` | **new** |
| `tests/test_runtime_protocol_v6_compatibility.py` | **new** |
| `docs/architecture/mcp-runtime-protocol-v6-foundation.md` | this document |

`SHARED_FILES_CHANGED` = **NONE**. Explicitly unchanged: `EXTENSION/**`,
`live_bridge.py`, `file_bridge.py`, `tool_registry.py`, every CP-SCALE tool
under `tools/`, and every checkpoint file. `execution/__init__.py` is touched
only if that package's existing convention requires an export line; if it does
not, it stays untouched too.

`PHASE1A_TESTS`:

1. A well-formed V6 envelope with a matching `operation_rid` parses `VALID_V6`.
2. A mismatched `operation_rid` parses `CORRELATION_MISMATCH` and **does not**
   fall back to V5.
3. `v == 6` with a missing or ill-typed required field parses `INVALID_V6` and
   does not fall back to V5.
4. A JSON object with `v` present and `!= 6` parses `PROTOCOL_MISMATCH`.
5. Legacy V5 text — `PT_ERROR: ...`, `ERROR:...`, `OK`, `MISSING` — parses
   `NOT_V6` and is returned unaltered.
6. A JSON object with **no `v` key** parses `NOT_V6` (guards the 118 existing
   `JSON.stringify` sites, §1.12).
7. `runtime.identify` is read-only: the encoder emits **no** `mutated` key at
   all, and names no mutating PT API — which also keeps
   `test_transport_mutation_containment.py`'s sweep green by construction.
8. `extension_version` is `null` in the encoded payload and there is no code
   path populating it from a caller-supplied parameter.
9. The encoded payload interpolates every dynamic field through `json.dumps`
   and contains no f-string interpolation — asserted on source, in the style of
   `test_probe_naming_contract.py`.
10. The encoded payload is a self-contained statement that survives `\n`
    concatenation with other commands (HTTP batching, `live_bridge.py:369`).
11. Engine-layer error codes (§3.2 Layer B) are **declared and inert**: no
    Phase 1A code path constructs one. *No fabricated call site is added to make
    them reachable.*
12. The parser's signature accepts `str`, not `str | None` — a transport
    non-response cannot reach the protocol layer (§3.4).
13. The full existing suite still passes, on a worktree-local `.venv`.

`PHASE1A_RISKS`:

| Risk | Severity | Mitigation |
|---|---|---|
| A V5 JSON response is misread as V6 | Low | `NOT_V6` requires absence of a `v` key, not absence of `v == 6`. Test 6. |
| The encoder drifts into being called a dispatcher | Low | Module name and §3.6; the term is reserved. |
| Reserved engine codes attract fabricated tests | Low | Test 11 asserts inertness instead. |
| Scope creep into transport integration | **Medium** | 1A has no transport import; the seam is 1B. |
| Scope creep into the claim marker / `.pts` | **Medium** | Blocked by Q9 and stated out-of-scope. |

Phase 1A validates **nothing** about the Script Engine. It cannot: it sends
nothing. Every runtime-session claim of §3.5 is deferred to 1B.

### Phase 1B — integration seam (later, gated)

**Gate: a safe CP-SCALE boundary. Not before.**

Scope, when it opens:

1. An integration seam taking an injected
   `send_and_wait: Callable[[str, float], str | None]` — the pattern already
   used at `enterprise_control_plane_runtime.py:656` and
   `configuration_runtime.py:13`. **No import of any `tool_registry` closure**,
   in either direction.
2. First transport invocation of `runtime.identify`.
3. LIVE validation of the §3.5 claims, which is the only way to establish them:
   that `this` is the Script Engine global on the dispatched-command path; that
   the seed survives across commands; that it survives the webview closing and
   reopening; that it changes across a PT restart; and that `session_seed_owner`
   behaves under two MCP processes sharing one PT.
4. Only then may the runtime-session contract be described as validated.

Deferred beyond 1B and explicitly *not* authorised by it: transport-rid
unification (§3.3), the `run_<name>` claim marker (Q4), extension-reported
`extension_version`, engine-side JSON request parsing, and the extension typed
dispatcher (§3.6) — all blocked by Q9.

---

## Part 6 — Interference and dependency assessment

**PTBUILDER_DEPENDENCIES** — Rebuilding the `.pts` needs six PTBuilder reference
`.js` files that are `.gitignore`d and not redistributed (no license). Verified
absent: `EXTENSION/script-engine/` holds only `main.js` and `README.md`. This
blocks the extension typed dispatcher, the `run_<name>` claim marker,
extension-reported `extension_version`, and engine-side JSON request parsing. A
separate, softer constraint blocks engine-side session minting: `Math.random()`
is unproven in the Script Engine (§3.5). Neither blocks Phase 1A, which is pure
Python by design.

**CP_SCALE_INTERFERENCE_RISK** — **NONE for Phase 1A, by construction.** Phase
1A adds two new modules and two new test files, changes no shared file, imports
no transport, performs no dispatch, and sends nothing to Packet Tracer. The only
residual concerns are operational: creating a worktree-local `.venv`, and using
it rather than the main checkout's (`AGENTS.md`). The risk assessment for Phase
1B is deliberately **not** made here — it is a precondition of opening that
phase, not an inheritance from this one.
