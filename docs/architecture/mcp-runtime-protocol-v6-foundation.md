# MCP Runtime Protocol V6 — Foundation Audit and Design Slice

Status: **PHASE 1B-LIVE-A HARNESS IMPLEMENTED OFFLINE · NOT EXECUTED AGAINST PACKET TRACER**
Branch: `feature/runtime-protocol-v6-foundation`
Base: `43eba72f18ad4e29e0ff292ebca4dbbd4a47232e` (CP-LIVE checkpoint on `feature/runtime-ripv2`)
Phase: 0 — audit (accepted) · 0.5 — design corrections (accepted) · 1A — implemented ·
1A.1 — operation correlation hardened ·
1B-OFFLINE — client orchestration ·
1B.1 — finite timeout contract ·
1B-LIVE-A prep — operator harness, offline

This document is an audit of the **deployed V5 bridge**, the design corrected
after it, and the record of the first implemented slice. No `.pts` was rebuilt,
no Packet Tracer instance was touched, and no CP-SCALE run was performed.

Every claim below is cited to source in this checkout. Where the evidence does
not reach, the document says so instead of extrapolating. In particular, Phase
1A executes nothing against Packet Tracer, so every claim about runtime-session
*behaviour* is marked **UNVERIFIED_UNTIL_PHASE_1B_LIVE** and none of it was promoted
because tests pass.

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
   Corrected in §3.4 — a five-state protocol parser, with transport outcomes
   kept strictly outside it.
3. **Slice 1 was misnamed a typed dispatcher.** It generates JavaScript in
   Python and runs it on the legacy V5 executor. That is an *encoder*, not an
   extension dispatcher. Renamed throughout; the milestone is reserved.
4. **The proposed slice violated layering.** It planned to call
   `_bridge_send_and_wait`, which is a closure inside `register_tools()` in
   `adapters/mcp/tool_registry.py` (line 1520, nested under line 134) — an
   adapter-layer local that infrastructure must not depend on, and that
   `AGENTS.md` notes tests cannot import at all. Corrected in Part 5 by
   splitting into Phase 1A (pure, offline, new files only), Phase 1B-OFFLINE
   (the seam, driven by an injected callable) and Phase 1B-LIVE (a real
   channel, later and gated).

Two further corrections were made to claims about the runtime session and the
error taxonomy; see §3.5 and §3.2.

## Revision 1A — what was built

Phase 1A is implemented: two new modules under `infrastructure/execution/`, two
new test modules, and this document. Nothing else in the repository changed.

Two design items moved during implementation, both because the evidence did not
support them: `session_seed_owner` was dropped as uncomputable before a live response,
and an explicit U+2028/U+2029 escape was written and then removed once measured
to be dead — `json.dumps` already escapes them under its default
`ensure_ascii=True`. The invariant is now pinned by a test rather than by a
branch whose comment overstated what it did. Both are recorded in Part 5.

What Phase 1A does **not** establish is unchanged by any of it: the slice sends
nothing to Packet Tracer, so every runtime-session behaviour stays
UNVERIFIED_UNTIL_PHASE_1B_LIVE.

## Revision 1A.1 — operation correlation hardened

A review of the accepted Phase 1A found one protocol defect. This revision
fixes that and nothing else.

`parse_runtime_result` correlated on `operation_rid` alone. The envelope
carries `operation_rid` **and** `op`, so a schema-valid V6 document bearing the
requested rid and a *different* `op` was classified `VALID_V6` — a well-formed
answer to some other operation, consumed as the answer to ours. A rid is not an
operation identity. The pair is.

The contract is now:

- **Operation identity = `operation_rid` + `op`.** `parse_runtime_result`
  requires `expected_operation_rid` *and* `expected_op`. `expected_op` has no
  default and is never inferred from the rid: the rid is opaque, and this layer
  keeps no registry of operations in flight to look one up in.
- **`CORRELATION_MISMATCH` covers either half, and both together.** No new
  parse state was added, because all three mean one thing to a caller — a
  well-formed V6 document that does not answer the requested operation — and
  the required behaviour is identical: fail closed, no envelope, no legacy
  text. The `detail` names which half missed, so a stale answer and a wrong
  answer stay tellable apart; it names the *field*, never the document's own
  value, so a fail-closed outcome still leaks nothing.
- **Schema first, identity second.** A malformed `op` is still `INVALID_V6`; a
  well-formed `op` that was not requested is `CORRELATION_MISMATCH`.

Scope held: the parser, its two test modules, and this document.
`runtime_operation_encoder.py` needed no behavioural change — it already
embeds `op` in the envelope it builds — and no shared, transport, adapter or
extension file was touched.

## Revision 1B-OFFLINE — the three pieces, connected

Phase 1A built an encoder and a parser that had never met. This revision joins
them through a callable handed in from outside, and stops there.

`runtime_protocol_client.py` runs one `runtime.identify` attempt: encode, call
`send_and_wait(payload, timeout)` **once**, and classify whatever comes back
against the identity the encoder minted. It imports no channel, no adapter and
no tool surface — the injected-seam shape already used at
`enterprise_control_plane_runtime.py:656` and ten other modules.

**This is not transport integration, and it is not LIVE.** The only responder
that has ever answered this client is a Python fake in its test module. Whether
HTTP or the file bridge can carry a V6 envelope, and everything about the Script
Engine, stays UNVERIFIED_UNTIL_PHASE_1B_LIVE. A fake that answers correctly
proves the orchestration and proves nothing about a responder never asked.

Four decisions, each taken to avoid inventing a fact the seam cannot supply:

- **One send per attempt, whatever comes back.** No retry, no fallback channel,
  no replay. `runtime.identify` is read-only, so a retry would be safe *here* —
  which is exactly why the discipline is set now: the operations that follow will
  not all be read-only, and a retry hidden inside a protocol client is a replay
  nobody chose. Retry belongs to a layer that can name what it is replaying.
- **`None` means `NO_RESPONSE_DOCUMENT`, and nothing else.** Not timeout, not
  bridge down, not non-200, not unsupported protocol — none of which this seam
  can observe. `probe_runtime.py:1173` raises `TimeoutError` on the same value,
  reading a cause off a value that cannot carry one; that is V5 code, it stays as
  it is, and V6 does not copy the claim.
- **A raising callable propagates unchanged.** It has broken its own `str | None`
  contract, and no response document exists. It is emphatically not converted to
  `ENGINE_EXCEPTION`, which asserts that the Script Engine *ran* the operation and
  reported a failure envelope — an execution that in this case never happened.
- **Classification is not routing.** A `NOT_V6` document is reported with its
  legacy text intact and is not sent down the V5 path from here. What to do with
  a legacy responder needs a caller that knows which channel it is talking to.

Scope: one new module, one new test module, and this document. No existing file
changed — not the encoder, not the parser, not `execution/__init__.py`.

## Revision 1B-LIVE-A prep — the harness, built and not run

`tools/runtime_v6_identify_live.py` is the operator runner that will make the
first real `runtime.identify`. **It has not been executed.** No Packet Tracer
was opened, no HTTP server was started, and no file mailbox was touched:
`LIVE_EXECUTED = NO`. What exists is `HARNESS_IMPLEMENTED_OFFLINE`, and the two
must not be read as one.

It is operator-only: not an MCP tool, not on the enterprise surface, and
`tool_registry.py` is unchanged and does not know it exists.

What it does, when someone eventually runs it in the isolated VM: build the one
transport named by `--channel http` or `--channel file`, prove that transport is
ready, hand its own `send_and_wait` to `RuntimeProtocolClient`, run one
`runtime.identify`, and print one JSON document.

Five decisions worth stating:

- **One invocation owns one channel.** `--channel` is required, restricted to
  `http` and `file`, and there is no fallback in either direction. A run that
  could have answered from either channel answers nothing about the one being
  tested, and the whole purpose is attributable evidence.
- **The harness owns what it starts.** On HTTP it stops the transport in a
  `finally` — after success, after a protocol failure, after an integration
  exception, and after a budget the client refuses once the server is already
  up. Ten of those paths are asserted, so no server, thread or process outlives
  a run.
- **Preflight refuses before dispatch.** Import isolation first (the gate every
  sibling runner in `tools/` passes, and the one that keeps two module
  identities from making every enum comparison silently false); then the
  channel's own evidence — fresh authenticated polling on HTTP, `pt_alive()`
  on file. A stale heartbeat is reported as a heartbeat fact and nothing more:
  not a timeout, not an unsupported protocol, not a Packet Tracer failure.
- **The client stays the authority.** The harness never calls the encoder or the
  parser. A LIVE run that reimplemented either would validate something other
  than what ships, so the identity, the single send and the correlation all
  remain where 1B-OFFLINE built and tested them.
- **The token never leaves.** It rides in the query string of every signed
  request, so a `urllib` failure can carry it verbatim. Bridge status is emitted
  through a key allowlist, and an integration message is redacted before it is
  bounded — truncating first would leave a prefix of the token in the output.
  Only the transport's own non-invertible `token_id` is reported.


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
  importing an adapter. Phase 1B-OFFLINE takes exactly this shape, from a
  caller rather than from a transport (§3.7); Phase 1B-LIVE is where a real
  one is passed in.

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
| `operation_rid` + `op` (protocol identity) | **REQUIRED_FOR_FIRST_SLICE** | The operation identity is the pair, minted and named by the V6 caller, echoed in the envelope, and correlated on together. Independent of transport identity (§3.3). |
| `transport_rid` unification | **LATER** | Requires changing `live_bridge.py` / `file_bridge.py`. Forbidden now (§3.3). |
| JSON result envelope | **REQUIRED_FOR_FIRST_SLICE** | The whole point. Everything else rides on it. |
| Protocol parse states | **REQUIRED_FOR_FIRST_SLICE** | The correction in §3.4; without it detection is dishonest. |
| Structured error model | **REQUIRED_FOR_FIRST_SLICE** (parser layer only) | Engine-layer codes are reserved-not-producible in 1A (§3.2). |
| `runtime_session_id` contract | **REQUIRED_FOR_FIRST_SLICE** (contract + encoder) | Behaviour is LIVE-validated in 1B, not claimed in 1A (§3.5). |
| `runtime.identify` JS encoder | **REQUIRED_FOR_FIRST_SLICE** | The operation the envelope is prototyped against. |
| Client orchestration over an injected seam | **PHASE 1B-OFFLINE — IMPLEMENTED** | Encoder to parser across a callable supplied from outside (§3.7). Changes no shared file and dispatches nothing. |
| Operator harness wiring a real transport | **PHASE 1B-LIVE-A — IMPLEMENTED OFFLINE** | Builds one declared channel and runs the accepted client over it (§3.8). Written and tested; never executed against Packet Tracer. |
| LIVE execution against Packet Tracer | **PHASE 1B-LIVE — NOT STARTED** | Layering (Part 5); gated on operator review and an isolated VM, and forbidden while CP-SCALE is open. |
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

### 3.1 Result envelope — IMPLEMENTED

As emitted by `runtime.identify` and accepted by `parse_runtime_result`:

```json
{
  "v": 6,
  "operation_rid": "<echoed protocol identity>",
  "op": "runtime.identify",
  "status": "ok",
  "runtime": {
    "session_id": "<value held by the Script Engine global, or null>",
    "session_storage": "script_engine_global",
    "session_minted_by": "mcp_server",
    "extension_version": null,
    "protocol_version": 6
  },
  "observed": {"pt_file_version": "9.0.1.0858", "device_count": 12},
  "error": null
}
```

- `operation_rid` and `op` together are the **protocol** identity of an
  operation (§3.3), and the parser correlates on both. Neither half is
  sufficient: the rid alone cannot separate our operation's answer from another
  operation answered under our rid, and `op` alone cannot separate this call's
  answer from the previous call's. Neither is the transport correlation id, and
  neither must ever be described as validating one.
- `mutated` is **absent from the model entirely**, not null. The encoder has no
  branch that can emit the key, and the parser rejects an envelope carrying it
  for an operation in `READ_ONLY_OPERATIONS` — including `"mutated": null`,
  because a null default still reads as "nothing was mutated" rather than
  "mutation is not a fact this operation reports".
- `status` is a closed set — `ok` or `error` — and must agree with `error`:
  `ok` carrying an error, or `error` without one, is `INVALID_V6`.
- `session_id` may be `null`, and a null session is `VALID_V6`. Degradation has
  to stay expressible, or the encoder's only honest failure mode becomes
  unrepresentable.
- `session_minted_by: "mcp_server"` is the honest value (§3.5). `"extension"` is
  declared in the enum and is unreachable from Phase 1A.
- `session_seed_owner` was **dropped from Phase 1A**. It is computable only once
  a response exists, so it belongs to 1B; reserving an unused field would have
  been a claim about a phase that has not run.
- `extension_version: null`. Modelled as `str | None` for forward compatibility,
  hard-coded null by the encoder, and a test asserts that neither Phase 1A module
  so much as accepts a parameter of that name.

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

| Code | Layer | Emitted by the Phase 1A encoder |
|---|---|---|
| `ENGINE_EXCEPTION` | B — engine | **Yes** — see the decision below |
| `UNKNOWN_OPERATION` | B — engine | No (reserved) |
| `INVALID_ARGUMENTS` | B — engine | No (reserved) |
| `TARGET_NOT_FOUND` | B — engine | No (reserved) |

`PROTOCOL_MISMATCH` was moved **out** of the engine layer. A responder speaking
a different protocol version is a parser observation, not an engine failure, so
it is a parse state (§3.4), not an `error.code`.

**Decision: engine exceptions become envelopes, not `PT_ERROR:` text.** The
generated code catches its own exceptions and reports a complete V6 envelope
with `status: "error"` and `ENGINE_EXCEPTION`. The alternative — letting the
exception escape into the legacy guard that prefixes `PT_ERROR:` — would have
meant advertising a complete structured error contract while depending on V5
string semantics underneath for the one case that matters. It costs nothing but
generated text, so the explicit branch is the honest one. The three remaining
codes describe a typed dispatcher that does not exist and stay reserved.

**Testing rule, and what it is not.** Reserved codes must **not** be given
fabricated call sites to make them "reachable". Phase 1A asserts the opposite
properties: that the pure parser never constructs a code the document did not
carry, and that the encoder's payload contains `ENGINE_EXCEPTION` and none of
the other three. A reserved code becoming producible is a later event with its
own test.

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
| Purpose | with `op`, proves *this response answers this operation*; the rid alone proves only that *some* operation answered under it | proves *this HTTP/file result answers this transport request* |
| Relationship in Slice 1 | **none — independent** | **none — independent** |

What the operation identity honestly buys in Slice 1: a response that is
well-formed V6 but answers a *different* operation — a different rid, a
different `op`, or both — is detected and fails closed
(`CORRELATION_MISMATCH`, §3.4). That is a real property, and it is achievable
with zero changes to shared transport code.

It takes **both** halves. Correlating on the rid alone left a document carrying
our rid and somebody else's `op` indistinguishable from our own result, which
is the defect Revision 1A.1 closed.

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
| `VALID_V6` | parses as a JSON object, `v == 6`, schema-valid, and **both** `operation_rid` and `op` match the expected values | consume as V6 |
| `NOT_V6` | not JSON, **or** a JSON value with no `v` key | legacy V5 text/JSON — hand to the existing V5 path unchanged |
| `PROTOCOL_MISMATCH` | JSON object with `v` present and `v != 6` | **fail closed** |
| `INVALID_V6` | `v == 6` but the envelope is malformed (missing/ill-typed required fields) | **fail closed** |
| `CORRELATION_MISMATCH` | `v == 6`, schema-valid, and `operation_rid`, `op`, or both do not match | **fail closed** |

Four rules that make this honest:

1. **Fail closed means fail closed.** `INVALID_V6`, `CORRELATION_MISMATCH` and
   `PROTOCOL_MISMATCH` must **never** fall back to V5 parsing. A broken V6
   responder is a fault to surface, not a V5 responder to accommodate.
2. **`NOT_V6` is the only state that routes to V5**, and it is deliberately
   narrow: it requires the absence of a `v` key, not merely the absence of
   `v == 6`. This is what keeps the 118 existing `JSON.stringify` sites (§1.12)
   from being misclassified in either direction.
3. **Operation identity is the pair `(operation_rid, op)`.**
   `parse_runtime_result` requires both from the caller. `expected_op` has no
   default and is not inferred: the rid is opaque, and this layer holds no
   registry of operations in flight. `CORRELATION_MISMATCH` covers either half
   and both together — one meaning, one required caller behaviour, so no
   second state. Its `detail` names which half missed, and names the field
   rather than the document's value.
4. **Schema first, identity second, and the order is load-bearing.** A
   malformed `op` — missing, empty, not a string — is a broken responder and
   stays `INVALID_V6`. A well-formed `op` that was not the one requested is
   `CORRELATION_MISMATCH`. Collapsing the two would either report a schema
   defect that is not there, or correlate against a document whose shape was
   never established.

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
behaviour is a **LIVE-validation item for Phase 1B-LIVE**, and neither Phase
1A nor Phase 1B-OFFLINE asserts anything about it. A fake responder can be made
to return any session it likes, which is why the client deliberately does not
check the one it gets back (§3.7).

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

**What the contract will prove, once 1B validates it:** *the value returned
identifies one Script Engine global, stable from first V6 contact until that
engine instance ends.* It does **not** prove PT start time, and it does not make
the identity extension-originated.

**Degradation rule — IMPLEMENTED.** The seeding block has its own `catch`, and
that branch sets `session_id` to null rather than falling back to the injected
candidate. Echoing the candidate would be the subtle failure worth guarding
against: it would look exactly like a successful read-back while proving
nothing. A test pins the branch.

**What Phase 1A established, precisely.** The generated payload is valid
JavaScript; each of its branches builds an envelope this parser accepts; and its
seed is first-writer-wins when a second dispatch hits the same global — a later
operation does not displace an established session. That was measured by running
the payload in **Node**, under the same `(new Function("reportResult", js))(report)`
shape the file bridge uses.

**What that does not establish, and must not be read as establishing.** Node is
not Packet Tracer. Whether `this` is the Script Engine global on a dispatched
command's path, whether the seed survives real dispatches, whether it holds
across a webview reopen, and whether it changes across a PT restart are all
**UNVERIFIED_UNTIL_PHASE_1B_LIVE**. The existing evidence for the underlying pattern
remains what it was — `this.__mcpE8Http` and `this.__mcpE6HttpClients` in shipped
runtimes — which is strong evidence about *those* payloads, not proof about this
one. `AGENTS.md` is explicit that this boundary cannot be verified from tests,
and a green suite does not change that.

`extension_version` remains `null` throughout.

### 3.6 Naming — Slice 1 is not a typed dispatcher

Slice 1 generates JavaScript in Python and hands it to the **legacy V5
executor** (`runCode` on HTTP, `runFileBridgeCommand` on File). No structured
request is parsed by the extension; the extension is unchanged.

| Term | Means | Status |
|---|---|---|
| **typed V6 operation encoder** | Python builds a typed operation into a JS payload whose result is a V6 envelope | **Slice 1 (Phase 1A)** |
| **V6 result envelope parser** | Python classifies a response document into §3.4 states | **Slice 1 (Phase 1A)** |
| **V6 protocol client** | Python runs one operation over a `send_and_wait` it is handed, and classifies the answer | **Phase 1B-OFFLINE** |
| **operator LIVE harness** | an operator-only runner that builds one declared real transport and drives the client over it | **Phase 1B-LIVE-A — built, not run** |
| **transport integration** | a real channel carries a V6 payload and returns a V6 document | **PHASE 1B-LIVE — not started; only a real run can establish it** |
| **extension typed dispatcher** | the Script Engine parses a structured V6 *request* and routes it to a typed handler | **LATER — blocked by Q9** |

`SLICE1_ARCHITECTURE_NAME` = *typed V6 operation encoder + result envelope
parser (prototype)*. The module is named `runtime_operation_encoder.py`, not
`runtime_dispatcher.py`, so the code cannot drift into the stronger claim.

The same discipline applies to Phase 1B-OFFLINE: the module is named
`runtime_protocol_client.py`, not `runtime_transport.py`. It holds no channel;
it is handed one.

### 3.7 Client orchestration — IMPLEMENTED (Phase 1B-OFFLINE)

`RuntimeProtocolClient(send_and_wait, *, timeout_seconds).identify()` returns one
`RuntimeProtocolAttempt`:

| Field | Meaning |
|---|---|
| `operation` | the `EncodedOperation` that was sent. The **request authority**: the identity correlated against is read from it, never rebuilt |
| `raw_response` | what the seam returned, byte-for-byte, or `None` |
| `parse_outcome` | the §3.4 classification, or `None` |

`raw_response` and `parse_outcome` move together, enforced in `__post_init__`
rather than promised in prose: a document nobody classified and a classification
of nothing are both impossible to construct.

**The timeout budget.** Required, with no default, and it must be a *finite*,
non-negative number. Finite is a separate requirement from non-negative and is
not implied by it: `float("nan")` and `float("inf")` are both floats and neither
compares `< 0`, so a sign test alone hands a channel a wait it can never
satisfy. `live_bridge.bounded_result_wait` (`live_bridge.py:74`) already refuses
non-finite waits with `math.isfinite`; the *property* is reused here and the
function is not — importing the HTTP transport for one check would break this
phase's dependency boundary, and that function additionally clamps to a measured
HTTP ceiling this layer has no basis for. Zero stays allowed. There is no
default, no maximum and no clamping: an accepted budget reaches the seam with its
value and its type unaltered.

**`NO_RESPONSE_DOCUMENT`.** `raw_response is None` says one thing, and the model
says it structurally instead of naming a state. The seam's return type is
`str | None`, so the value carries no provenance: naming it TIMEOUT would read a
cause off a value that cannot hold one. The parser is **not called** on a
non-response, so nothing downstream can mistake silence for a classification.

**No parallel transport taxonomy.** There is deliberately no state enum here.
The transport-side facts this repository *can* observe already have vocabularies
— `RequestDisposition`, `TransportHealthState`, `BridgePreflightState` — and
they belong to the layers that can establish them (§3.2). A fourth enum invented
at this seam would have to distinguish timeout from channel-down from non-200,
none of which is visible from `str | None`.

**`CALLABLE_EXCEPTION`.** A callable that raises has broken its own return
contract, and no response document exists. The exception propagates unchanged;
the module contains no `try` at all, which a test asserts on its AST. It is not
`ENGINE_EXCEPTION`: that code asserts the Script Engine ran the operation and
reported a failure envelope, and here nothing ran.

**One dispatch per attempt.** Pinned three ways: a call count over eight
different responder behaviours, no loop anywhere in the module, and exactly one
call site for the seam in its source. Retry is a policy for a layer that can
name what it would be replaying — not a default hidden in a protocol client.

**Classification is not routing.** `NOT_V6` is reported with its legacy text
intact, and the client sends it nowhere. Routing needs a caller that knows which
channel answered.

### 3.8 Operator harness contract — IMPLEMENTED OFFLINE (Phase 1B-LIVE-A)

`runtime_v6_identify_live.py --channel {http|file} --timeout-seconds N` emits one
JSON document with a fixed top-level shape — `phase`, `channel`,
`timeout_seconds`, `operation`, `transport`, `response`, `runtime`, `observed`,
`error`, `integration_error`, `verdict`, `exit_code`, `non_claims` — whatever
the outcome, so two runs can be diffed as evidence.

Three exit codes, and the partition is structural rather than a taste:

| Code | Verdict | Means |
|---|---|---|
| `0` | `VALID_V6_OK` | a V6 envelope parsed, correlated, and reported `status: ok` |
| `1` | `CLASSIFIED_NOT_VALID_V6_OK` | a document arrived and was classified, but it was not that — `NOT_V6`, `PROTOCOL_MISMATCH`, `INVALID_V6`, `CORRELATION_MISMATCH`, or a valid envelope reporting `status: error` |
| `2` | `NO_CLASSIFIED_DOCUMENT` | no classified document exists: preflight refused, no response document, or an integration exception |

A protocol-valid envelope carrying `status: error` is deliberately **not**
success. The document parsed perfectly and the operation failed; this is a
validation harness, not a generic protocol decoder, and the JSON keeps both
facts separately so nothing is lost by the exit code being blunt.

`error` and `integration_error` are separate keys and never substitute for each
other. `error` is the engine's own structured failure, and only ever comes from
a `VALID_V6` envelope. `integration_error` is a Python exception from the
transport callable: type and a bounded, redacted message. It is never rendered
as `ENGINE_EXCEPTION`, which asserts the Script Engine ran the operation and
reported a failure envelope — an execution that, in that case, never happened.

`no_response_document` is reported as `NO_RESPONSE_DOCUMENT` and never as a
timeout. Neither transport hands timeout provenance to this layer, and the V6
client carries none (§3.7).

The `runtime` block is populated **only** from a `VALID_V6` envelope. Without
one, every field is `null` and `observed` is `{}`; nothing is filled in from the
request, from the transport, or from a document that answered some other
operation.

Every run also emits `non_claims`, naming what it did not establish: the other
channel always, its own channel unless the verdict was `VALID_V6_OK`, and
`SCRIPT_ENGINE_SESSION_PERSISTENCE`, `WEBVIEW_REOPEN_PERSISTENCE`,
`PT_RESTART_SESSION_CHANGE`, `CROSS_CHANNEL_SESSION_AGREEMENT` and
`EXTENSION_VERSION` unconditionally. One identify cannot show persistence,
cannot compare two channels, and cannot observe a version the Phase-1A wire
holds as null.

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
  **strong evidence, not proof** (§3.5) and is a Phase 1B-LIVE validation item.
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

### Phase 1A — pure protocol model — IMPLEMENTED

**Scope held exactly: new files only. No transport, no adapter, no live caller,
no Packet Tracer, no CP-SCALE surface.** `git status` after implementation shows
four new untracked files and nothing modified. Revision 1A.1 held the same
boundary, modifying three of those four files and this document.

Contents as built:

1. `runtime_protocol.py` — `PROTOCOL_VERSION = 6`; `operation_rid` minting and
   validation against its **own** pattern, deliberately not imported from the
   HTTP transport that happens to use the same shape; the operation-name
   predicate that keeps the contract generic without a registry; the envelope
   model; the five-state parser of §3.4 over a `str`, correlating on the
   `(operation_rid, op)` pair; the two-layer error model of §3.2.
2. `runtime_operation_encoder.py` — builds the `runtime.identify` payload
   (Q5). Every dynamic value passes through one `js_string_literal` choke
   point; the module contains no f-string at all, asserted on its AST.
3. Tests. The protocol and encoder are exercised offline; the generated text is
   additionally executed in Node, which is not Packet Tracer (§3.5).

`PHASE1A_FILES`:

| File | Change |
|---|---|
| `src/packet_tracer_mcp/infrastructure/execution/runtime_protocol.py` | **new** (450 lines; 1A.1 changed the parser signature and the correlation check) |
| `src/packet_tracer_mcp/infrastructure/execution/runtime_operation_encoder.py` | **new** (175 lines; **unchanged by 1A.1**) |
| `tests/test_runtime_protocol_v6.py` | **new** (640 lines) |
| `tests/test_runtime_protocol_v6_compatibility.py` | **new** (556 lines) |
| `docs/architecture/mcp-runtime-protocol-v6-foundation.md` | this document |

`SHARED_FILES_CHANGED` = **NONE**, verified by `git diff HEAD` over
`EXTENSION/`, `live_bridge.py`, `file_bridge.py`, `tool_registry.py`,
`adapters/`, `tools/` — all empty. `execution/__init__.py` was **not** touched:
it exports only a subset of the package and every existing test imports these
submodules by full path, so the convention did not require an export.

`PHASE1A_TESTS` — 143 tests, all passing (117 at Revision 1A, +26 for the
correlation hardening in 1A.1):

1. `operation_rid` uniqueness and validation, with twelve malformed shapes
   rejected (wrong length, uppercase, non-hex, whitespace, non-string types),
   and operation-*name* validation as shape only — any non-empty string is a
   name this parser can correlate against, seven malformed values are not,
   and no registry of known operations exists to reject an unfamiliar one.
2. A conforming document parses `VALID_V6` with every field recovered.
3. Operation identity is correlated as a pair. All three near misses — right
   rid with wrong `op`, wrong rid with right `op`, both wrong — are
   `CORRELATION_MISMATCH`, carry no envelope and **no legacy text**, and fail
   closed. The `detail` names which half missed, and quotes back neither the
   document, nor its `op`, nor its rid. A document that both mismatches *and*
   carries a malformed `op` stays `INVALID_V6`, pinning schema-before-identity.
   Removing the `op` half of the correlation fails six of these tests across
   both modules — measured, not assumed.
4. Twelve real V5 responses — `PT_ERROR:`, `ERROR:`, `OK`, `MISSING`, empty,
   bare scalars, and two verbatim structured shapes from the existing product —
   are `NOT_V6` and returned byte-for-byte unaltered.
5. A JSON object with no `v` key is `NOT_V6`, including one carrying `status`
   and `error` keys that could otherwise look V6-ish.
6. Eight foreign version values are `PROTOCOL_MISMATCH`, including `"6"`,
   `True` and `6.0` — the last two matter because `bool` is an `int` subclass
   and `6.0 == 6`, so a naive check would admit both.
7. Sixteen malformed-envelope mutations are `INVALID_V6`, plus status/error
   disagreement and six malformed runtime blocks.
8. The parser accepts `str` by annotation, raises `TypeError` on five non-string
   inputs, and raises `ValueError` on an invalid expected rid. `expected_op`
   has no default, so omitting it is a `TypeError` rather than a silent
   rid-only correlation, and five malformed expectations are a `ValueError`.
9. A null `session_id` is `VALID_V6`.
10. `extension_version` is null on the wire, and neither module accepts a
    parameter of that name.
11. The encoder emits no `mutated` key, and the parser rejects one on a
    read-only operation — `null` included.
12. Ten hostile session candidates reach the payload only as JSON literals that
    decode back to the exact input, and appear nowhere outside that form.
13. The payload names none of the canonical mutating Packet Tracer APIs — the
    list is **imported from the sweep that owns it**, so a new name there starts
    being enforced here on the same commit.
14. The parser never constructs an error code the document did not carry, and
    the encoder emits `ENGINE_EXCEPTION` and none of the other three.
15. The payload is one line, ends in `;`, contains no `//`, and survives being
    joined with another payload by a newline and split back apart.
16. Neither module imports any transport, adapter, or network primitive, and a
    legacy document is handed back identical.

Plus, guarded by `skipif` when Node is absent: the payload is syntactically
valid JavaScript; its success, null-file and throwing branches each build an
envelope this parser accepts; an engine fault becomes a structured envelope
rather than a thrown error; and the seed is first-writer-wins across two
dispatches and across a second operation in the same batch.

**Two things the implementation changed about the design, both corrections:**

- `session_seed_owner` was dropped (§3.1). It cannot be computed without a
  response, so it belonged to 1B.
- An explicit U+2028/U+2029 escape was written, then **removed as dead code**.
  The premise was wrong: `json.dumps` defaults to `ensure_ascii=True` and
  already escapes them. Rather than keep a branch whose comment claimed to close
  a gap it did not, the invariant is now pinned by a test asserting every
  emitted literal is ASCII-only — which fails immediately if anyone ever passes
  `ensure_ascii=False`. That is the actual regression risk.

`REGRESSION`: the full suite runs **37 failed, 2818 passed, 6 skipped** on the
worktree-local `.venv`. The identical 37 failures occur with these four files
removed (**37 failed, 2675 passed, 6 skipped**); the two failure lists were
captured and diffed and are byte-identical. The delta is exactly +143 passing.

The same comparison was re-run for Revision 1A.1 rather than inherited. The
base state is unchanged — still 2675 passed against the identical 37 failures
— and the delta moved from +117 to +143 with the correlation-hardening tests.

Those 37 are not ours and were not touched. Thirty-six are CP-SCALE canonical
and reference-hardware tests in flight at the base checkpoint. The thirty-
seventh, `test_repository_reader_observes_current_exact_branch_upstream_and_head`,
asserts the checkout is on `feature/runtime-ripv2` and so fails on any other
branch by construction — a branch-context artifact, not a defect, and it belongs
to CP-SCALE.

`PHASE1A_RISKS` as built:

| Risk | Severity | Status |
|---|---|---|
| A V5 JSON response misread as V6 | Low | Closed by requiring absence of `v`, tested against real shapes |
| A response answering a *different* operation accepted as ours | Medium | **Was open through Revision 1A; closed in 1A.1.** Correlation is the pair `(operation_rid, op)`; removing the `op` half again fails six tests |
| `bool`/`float` admitted as version 6 | Low | Closed by an explicit `type(...) is int` check, tested |
| A hostile value reaching the payload as code | Low | Closed by a single escaping choke point, ten hostile inputs tested |
| The encoder drifting into "dispatcher" | Low | Module name, docstring, and §3.6 |
| Reserved codes attracting fabricated tests | Low | Inverted into inertness assertions |
| The generated JS being syntactically invalid | Medium | Closed offline by `node --check` and execution |
| `this` not being the engine global in PT | **Medium** | **Open. UNVERIFIED_UNTIL_PHASE_1B_LIVE**; degradation to null is implemented and tested |

### Phase 1B-OFFLINE — client orchestration — IMPLEMENTED

**Scope held: two new files and this document. No existing file changed, no
transport imported, no dispatch performed, no Packet Tracer, no CP-SCALE
surface.** `execution/__init__.py` was again not touched, for the same reason as
in 1A: it exports a subset, and every test imports these submodules by full path.

`PHASE1B_OFFLINE_FILES`:

| File | Change |
|---|---|
| `src/packet_tracer_mcp/infrastructure/execution/runtime_protocol_client.py` | **new** (167 lines) |
| `tests/test_runtime_protocol_client_v6.py` | **new** (742 lines) |
| `docs/architecture/mcp-runtime-protocol-v6-foundation.md` | this document |

`SHARED_FILES_CHANGED` = **NONE**, verified by `git diff --name-only` over
`EXTENSION/`, `live_bridge.py`, `file_bridge.py`, `tool_registry.py`,
`adapters/`, `tools/` — all empty. The two Phase-1A modules are byte-identical
to their 1A.1 state: the client was built *on* them, not *into* them.

`PHASE1B_OFFLINE_TESTS` — 66 tests, all passing (54 as built, +12 for the
finite-budget correction in 1B.1). Written before the module existed: the first
run failed at collection with nothing to import, which is the only honest
fail-first for a file that does not yet exist.

1. One dispatch per attempt, asserted over eight responder behaviours — no
   response, legacy text, malformed V6, foreign version, both correlation
   misses, and success. Plus two structural locks: no loop anywhere in the
   module, and exactly one call site for the seam in its source.
2. The payload handed to the seam is the encoded payload, unaltered, and the
   timeout budget reaches it unchanged.
3. The budget has **no default** — omitting it is a `TypeError` — and must be a
   finite, non-negative number. Five dishonest values and all three non-finite
   ones (NaN, positive and negative infinity) are refused at construction, and
   the seam is never reached for any of them. Zero stays allowed, and an
   accepted budget arrives at the seam with its value *and* its type unaltered —
   no default, no ceiling, no clamping, none of which this layer has measured.
   No measurement backs a number here, and this repository keeps its measured
   budgets next to the measurement that produced them.
4. `None` yields `raw_response is None` **and** `parse_outcome is None`, and the
   parser is never called: a stand-in that raises on any call is installed, and
   the attempt still comes back empty.
5. The attempt model cannot hold half a result — constructing a document
   without a classification, or a classification without a document, raises.
6. A conforming responder yields `VALID_V6` with the envelope intact.
7. The correlated identity comes from the `EncodedOperation`. Proven twice: the
   rid is random per attempt, so it cannot be a constant; and the encoder is
   replaced by one naming a different `op`, after which the client follows the
   encoder rather than the module constant. With one encoded operation those two
   are the same *string*, so only the second test separates the *mechanism*.
8. Six real V5 shapes and one structured V5 JSON stay `NOT_V6` with their text
   byte-identical, and the client routes none of them anywhere.
9. Malformed V6 stays `INVALID_V6`; a foreign version stays `PROTOCOL_MISMATCH`;
   all three identity near misses stay `CORRELATION_MISMATCH` with the detail
   naming the half that missed — the 1A.1 contract surviving the seam.
10. A raising callable propagates unchanged and is never turned into
    `ENGINE_EXCEPTION`; the module contains no `try`, asserted on its AST.
11. The client imports no transport and no adapter, and its non-stdlib imports
    are exactly the two protocol modules — the dependency direction written as
    a test rather than as a diagram.
12. It names no mutating Packet Tracer API (the list imported from the
    containment sweep that owns it) and builds no JavaScript of its own.
13. Two attempts share no rid and no session candidate, and a returned
    `session_id` unequal to the candidate is still `VALID_V6`: enforcing
    equality would encode a guess about first-writer-wins as a protocol rule.
14. `extension_version` is whatever the responder said — null on the Phase-1A
    wire — and the client accepts no parameter of that name.

Four mutations were applied to the finished client and each was caught, so the
suite detects the regressions it claims to: correlating on the module constant
instead of the encoded op (1 failure), retrying once on a non-response (3),
swallowing the seam's exception (3), and handing a non-response to the parser
(4).

`PHASE1B_OFFLINE_NON_CLAIMS`. The seam that answered every test above is a
Python callable in the test module. Unchanged and still open: that HTTP carries
V6; that the file bridge carries V6; that `this` is the Script Engine global on
the dispatched-command path; that the seed survives across commands, across a
webview reopen, or changes across a PT restart; that both channels agree on one
session; and `extension_version`. All **UNVERIFIED_UNTIL_PHASE_1B_LIVE**.

`REGRESSION`: the full suite runs **37 failed, 2884 passed, 6 skipped**. With the
six V6 files removed, **37 failed, 2675 passed, 6 skipped**; the failure lists
were captured and diffed and are byte-identical, and identical again to the list
recorded at 1A.1. The delta is exactly +209 passing (143 protocol + 66 client).
The base state has not moved across 1A, 1A.1, 1B-OFFLINE and 1B.1 — 2675 passed
against the same 37 every time. Those 37 belong to it, and none of this work
touched them.

`PHASE1B_OFFLINE_RISKS`:

| Risk | Severity | Status |
|---|---|---|
| A retry appearing later inside the client | Low | Closed structurally: no loop, one call site, and a call-count test over every outcome |
| A transport fault read as a protocol state | Low | Closed: `None` is modelled as absence, the parser is not called, and no state enum exists to misuse |
| A seam exception dressed as an engine error | Low | Closed: nothing is caught, asserted on the AST |
| The client drifting into "transport integration" | Low | Module name, §3.6 table, and this section |
| The fake responder mistaken for evidence about Packet Tracer | **Medium** | **Open by construction.** Named in the test docstring, in §3.7, and in the non-claims above; only 1B-LIVE closes it |

### Phase 1B-LIVE-A — the operator harness — IMPLEMENTED OFFLINE

**`LIVE_EXECUTED = NO`.** The harness is written and tested; it has never run
against Packet Tracer. No instance was opened, no HTTP server was started, no
mailbox was touched, and the host CP-LIVE runtime was not inspected. The next
step is an operator review, then a run inside an isolated VM — never against
the host.

`PHASE1B_LIVE_A_FILES`:

| File | Change |
|---|---|
| `tools/runtime_v6_identify_live.py` | **new** (367 lines), operator-only |
| `tests/test_runtime_v6_identify_live_harness.py` | **new** (840 lines) |
| `docs/architecture/mcp-runtime-protocol-v6-foundation.md` | this document |

`SHARED_FILES_CHANGED` = **NONE.** `live_bridge.py` and `file_bridge.py` are
reused and untouched: the harness builds `PacketTracerHttpTransport` and
`FileBridge` and neither duplicates their logic nor asks them to expose more.
`tool_registry.py`, `adapters/`, `EXTENSION/` and the three V6 modules are
unchanged, and a test asserts the registry does not know this harness exists.

**Why the tests run in child processes.** The harness imports the production
`packet_tracer_mcp` namespace, as every operator runner in `tools/` does.
Importing it into the pytest process would break three existing assertions that
it must not be loaded there (`test_cp_scale_live_failure_evidence.py:187`,
`test_cp_scale_voice_staging.py:321`, `test_import_isolation_preflight.py:148`)
and would create the second module identity `ImportIsolationPreflight` exists to
prevent. So the harness is driven in a child with fake transports, the same
shape `test_cp_scale_live_failure_evidence.py` already uses; the structural
checks read the source, which needs no import at all.

`PHASE1B_LIVE_A_TESTS` — 126 tests, all passing, written before the harness
existed. The first run was 121 failures against a file that did not exist yet.

1. `--channel` is required and accepts only `http` and `file`;
   `--timeout-seconds` is required. Each rejection happens in argument parsing,
   before any transport is constructed, and prints no JSON.
2. The declared channel builds its transport **and no other**, in both
   directions: no HTTP run ever constructs a `FileBridge`, and no file run ever
   starts an HTTP server, including after a silent or fail-closed outcome.
3. HTTP starts before it identifies, and stops exactly once as the last thing it
   does — asserted across ten outcomes: success, engine error, `NOT_V6`,
   `PROTOCOL_MISMATCH`, `INVALID_V6`, both correlation misses, no response, an
   integration exception, and a refused readiness. An eleventh covers a budget
   the client refuses after the server is already up.
4. A refused import isolation constructs no transport at all.
5. The file channel checks `pt_alive()` before identifying, and a stale
   heartbeat costs exactly zero sends. What it reports is the heartbeat fact:
   the words timeout and unsupported appear nowhere in that verdict.
6. `RuntimeProtocolClient` is what runs, it receives the **bound method of the
   selected transport object** (`FakeHttpTransport.send_and_wait` or
   `FakeFileBridge.send_and_wait`, observed by owner), and the declared budget
   reaches it unaltered. The harness calls neither the encoder nor the parser,
   asserted on its AST.
7. Every outcome costs exactly one send; the source has one `identify` call site
   and no loop.
8. The exit code follows the classified outcome across all thirteen scenarios,
   including `VALID_V6` + `status: error` as a failure and no-response as `2`.
9. An integration exception is structured, typed, non-swallowed, and never
   rendered as `ENGINE_EXCEPTION`.
10. The raw bridge token appears in no output of any scenario — the fake puts
    it both inside `status_dict()` and inside the raised exception message, so
    the allowlist and the redaction are each exercised rather than assumed.
11. The `runtime` block is populated only from a `VALID_V6` envelope; eight
    non-envelope scenarios leave every field null and `observed` empty. A
    correlation mismatch still reports the identity that was *sent*, recovered
    from the payload that actually went out.
12. The harness names no mutating Packet Tracer API (list imported from the
    containment sweep), cannot save or create a Packet Tracer file, builds no
    JavaScript, never calls the fire-and-forget `send` on either transport, and
    is absent from the registry.
13. The JSON shape is identical across all thirteen scenarios and survives a
    round trip, and `non_claims` names what the run did not establish.

Five mutations were applied to the finished harness and each was caught:
dropping the HTTP `finally` (11 failures), falling back to the file channel
after an unsuccessful HTTP run (24), dispatching without the heartbeat gate (4),
emitting the transport status verbatim with its token (11), and dressing an
integration fault as an engine error (2).

`REGRESSION`: the full suite runs **37 failed, 3010 passed, 6 skipped**. With the
eight V6 files removed, **37 failed, 2675 passed, 6 skipped**; the failure lists
were captured and diffed and are byte-identical, and identical again to the
lists recorded at 1A.1, 1B-OFFLINE and 1B.1. The delta is exactly +335 passing
(143 protocol + 66 client + 126 harness). The base state has not moved once
across any of these phases.

**Unchanged and still open**, and a green harness run would not close most of
them by itself: `HTTP_V6`, `FILE_V6`, `SCRIPT_ENGINE_SESSION_PERSISTENCE`,
`WEBVIEW_REOPEN_PERSISTENCE`, `PT_RESTART_SESSION_CHANGE`,
`CROSS_CHANNEL_SESSION_AGREEMENT`, `EXTENSION_VERSION` — all
**UNVERIFIED_UNTIL_PHASE_1B_LIVE**.

### Phase 1B-LIVE — a real channel (later, gated)

**Gate: operator review of the harness, then an isolated VM, and a safe
CP-SCALE boundary. Not before, and never against the host instance.**
Neither earlier phase opens it: an injected callable is not a channel, and a
harness that has never run is not evidence about one.

Scope, when it opens:

1. Running `tools/runtime_v6_identify_live.py` (§3.8) inside an isolated VM,
   once per channel, after an operator has reviewed it. The caller that owns a
   channel now exists; what is missing is a run. **No import of any
   `tool_registry` closure**, in either direction — it is an adapter-layer
   closure, and that is the layering error Part 5 exists to prevent.
2. First transport invocation of `runtime.identify`. Until it happens, every
   HTTP and file-bridge claim about V6 stays UNVERIFIED_UNTIL_PHASE_1B_LIVE —
   the harness existing changes none of them.
3. LIVE validation of the §3.5 claims, which is the only way to establish them:
   that `this` is the Script Engine global on the dispatched-command path; that
   the seed survives across commands; that it survives the webview closing and
   reopening; that it changes across a PT restart; and that `session_seed_owner`
   behaves under two MCP processes sharing one PT.
4. Only then may the runtime-session contract be described as validated.

Deferred beyond 1B-LIVE and explicitly *not* authorised by it: transport-rid
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

**CP_SCALE_INTERFERENCE_RISK** — **NONE for Phase 1A, 1B-OFFLINE or the
1B-LIVE-A prep, by construction.** Between them they add three modules, one
operator runner and four test files, change no shared file, perform no dispatch,
and send nothing to Packet Tracer. 1B-OFFLINE adds no risk over 1A: it holds a
channel nowhere, and the only thing it ever called was a callable written in its
own test module. The 1B-LIVE-A prep adds none either: the harness can reach a
real transport, and has never been run, so the only processes that have ever
executed it are pytest children driving fakes. That changes the moment someone
runs it, which is why it runs in an isolated VM and not against the host. The residual concerns stay operational: creating a worktree-local
`.venv`, and using it rather than the main checkout's (`AGENTS.md`). The risk
assessment for Phase 1B-LIVE is deliberately **not** made here — it is a
precondition of opening that phase, not an inheritance from this one.
