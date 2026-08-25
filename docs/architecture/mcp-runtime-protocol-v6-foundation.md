# MCP Runtime Protocol V6 — Foundation Audit and Design Slice

Status: **DESIGN ONLY — NOT IMPLEMENTED**
Branch: `feature/runtime-protocol-v6-foundation`
Base: `43eba72f18ad4e29e0ff292ebca4dbbd4a47232e` (CP-LIVE checkpoint on `feature/runtime-ripv2`)
Phase: 0 — isolation + architecture audit

This document is an audit of the **deployed V5 bridge** and a proposal for the
smallest safe V6 slice. Nothing here was implemented. No `.pts` was rebuilt, no
Packet Tracer instance was touched, and no CP-SCALE run was performed.

Every claim below is cited to source in this checkout. Where the evidence does
not reach, the document says so instead of extrapolating.

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
   (`live_bridge.py:66-68,111-134`). **Identity originates in Python.**
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
   (`file_bridge.py:168-173`). **Identity originates in Python, and it is the
   filename** — there is no request id inside the payload.
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

**Neither transport carries the request identity inside the message.** The
payload is opaque executable text in both cases. This is the structural reason
a result cannot self-attribute today.

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
converge on the extension owning it in both — but see §3 for why that cannot be
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
(`live_bridge.py:126-134`, `file_bridge.py:238-268`).

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

---

## Part 2 — Target architecture evaluation

The proposed target:

```
Python RuntimeOperation -> MCP Runtime Protocol -> HTTP / File transport
  -> MCP BUILDER -> Typed Dispatcher -> ipc.* -> Structured Observation -> Python Evidence
```

**Verdict: sound, and it matches where the code is already drifting.** Three
observations from the audit that shape it:

1. `_bridge_send_and_wait` (`tool_registry.py:1520-1552`) is *already* a
   transport-agnostic dispatcher — it just dispatches JS text rather than typed
   operations. It is the correct seam, and it is one function.
2. The typed dispatcher does **not** have to live in the `.pts` to exist. See
   Q5 — the deployed engine already supports a Python-delivered dispatcher.
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

The one boundary that **moves** in V6: **runtime identity moves from Python
(caller-declared `extension_version`) to the extension (observed).** That is the
single largest honesty gain available, and it is cheap.

---

## Part 3 — V6 foundation proposal, classified

| Item | Classification | Rationale |
|---|---|---|
| `protocol_version` | **REQUIRED_FOR_FIRST_SLICE** | Without it, nothing after it can be rolled forward or detected. One integer. |
| `rid` in-band | **REQUIRED_FOR_FIRST_SLICE** | Lets a result self-attribute and cross-check the out-of-band correlation both transports already do. Zero extension cost. |
| JSON result envelope | **REQUIRED_FOR_FIRST_SLICE** | The whole point. Everything else rides on it. |
| `runtime_session_id` | **REQUIRED_FOR_FIRST_SLICE** | Achievable with no `.pts` change (Q5), and it is the fix for the invisible-PT-restart hole. |
| Typed operation dispatcher | **REQUIRED_FOR_FIRST_SLICE** (one op) | The slice exists to prove this shape. |
| Structured errors | **REQUIRED_FOR_FIRST_SLICE** | Four conventions collapsing into one taxonomy is most of the value. |
| JSON *request* envelope | **LATER** | The deployed engine executes text. A JSON request needs a parser in the `.pts` — blocked (Q9). |
| `extension_version` observed | **LATER** | Requires the `.pts` to state it. Slice 1 must report it as *unknown*, never as a caller-supplied string. |
| requested / mutated / observed separation | **LATER** (envelope reserves the fields) | Slice 1 is read-only, so `mutated` is structurally empty. Reserve, do not populate. |
| Raw-JS policy | **LATER** (already governed) | `TD-PUBLIC-001` is RESOLVED. V6 adds a rule, not a mechanism. |
| FileBridge claim lifecycle (`run_<rid>`) | **LATER — blocked** | Needs a `.pts` rebuild. See Q4/Q9 and `TD-TRANSPORT-001`. |
| V5 compatibility boundary | **REQUIRED_FOR_FIRST_SLICE** | Slice 1 must be additive and invisible to every existing caller. |
| Removing V5 code | **NOT_NEEDED** (and forbidden now) | CP-SCALE is open. |
| Migrating product callers | **NOT_NEEDED** for slice 1 | The slice proves the shape; migration is a later, separate decision. |
| Transactional / atomic file protocol | **NOT_NEEDED** | Cannot be honestly claimed (Q4). Do not build a mechanism that implies it. |
| New bridge endpoints | **NOT_NEEDED** | `/queue` + `/result` already carry everything. A new endpoint would also collide with `AGENTS.md` rule 3. |

### 3.1 Result envelope (proposed)

```json
{
  "v": 6,
  "rid": "<echoed request id>",
  "op": "<typed operation name>",
  "status": "ok",
  "runtime": {
    "session_id": "<script-engine-scoped id>",
    "session_origin": "script_engine_global",
    "extension_version": null,
    "protocol_version": 6
  },
  "observed": {},
  "mutated": null,
  "error": null
}
```

- `mutated: null` in slice 1 is a **structural** fact (the op is read-only), not
  a default. A read-only op must never be able to emit a non-null `mutated`.
- `observed` is whatever the typed op read. It is an observation, never a
  verdict.
- `extension_version: null` is the honest value until the `.pts` states it.
  It must **not** be back-filled from the caller-supplied MCP parameter.

### 3.2 Error taxonomy (proposed)

```json
"error": { "code": "<CODE>", "detail": "<engine text, never parsed for meaning>" }
```

| Code | Meaning |
|---|---|
| `UNKNOWN_OPERATION` | dispatcher has no handler for `op` |
| `INVALID_ARGUMENTS` | handler rejected its typed arguments |
| `TARGET_NOT_FOUND` | the named device/port/file does not exist |
| `ENGINE_EXCEPTION` | `ipc.*` threw; `detail` carries the engine text |
| `PROTOCOL_MISMATCH` | responder does not speak the requested `v` |

Mapped to Python as an exception/result type, never a string prefix. The legacy
`PT_ERROR:` / `ERROR:` prefixes stay exactly as they are on the V5 path.

Python-side outcomes that are **not** engine errors keep their own vocabulary
and must not be folded in: `RequestDisposition`, `TransportHealthState`,
`BridgePreflightState`.

---

## Part 4 — Critical questions, answered from source

### Q1 — Where should `runtime_session_id` originate: WebView or Script Engine?

**Script Engine. Not close.**

Lifetimes decide it:

| Component | Lifetime | Evidence |
|---|---|---|
| WebView | only while the window is open; can reload independently | `interface.js` header comments; `file_bridge.py:4-9` |
| Script Engine | the whole time PT is open, window or not | `main.js:352-362`; `EXTENSION/script-engine/README.md` |

A webview-minted id would change when the user closes and reopens the window,
falsely signalling a new runtime while PT and its entire network model persisted
unchanged. It would also be *absent* on the file channel, which has no webview
at all — so it could not be a protocol invariant.

The Script Engine is also the only side that can stamp it on **both**
transports, because `reportResult` executes there in both cases (§1.7).

### Q2 — Can HTTP and File transport share one dispatcher cleanly?

**Yes, and more cleanly than expected.** In both channels the executed body has
a function named `reportResult(d)` in scope — supplied by Python on HTTP
(`live_bridge.py:101-108`), by the extension on File (`main.js:133-142`). A
dispatcher that ends every operation with
`reportResult(JSON.stringify(envelope))` is therefore transport-agnostic, and
`_bridge_send_and_wait` (`tool_registry.py:1520-1552`) is already the single
function where the split lives.

Three differences that must be respected rather than abstracted away:

1. **Batching.** HTTP joins up to 200 commands with `\n` and evaluates them in
   one `runCode` (`live_bridge.py:369`, `interface.js:527-541`). The file
   channel is strictly one request per file. A typed op must be a self-contained
   statement that survives being concatenated with others.
2. **Correlation.** HTTP correlates on `rid` in a URL; File correlates on a
   filename. In-band `rid` unifies the *check*, not the mechanism.
3. **Delivery guarantees differ** (Q3). One dispatcher, two honest guarantees —
   the envelope must not paper over that.

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
this repository, and it is not what slice 1 should do.**

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

### Q5 — Smallest typed operation that proves the dispatcher without touching CP-SCALE?

**`runtime.identify` — read-only, mutation-free, and it is the one operation
whose entire purpose is the thing slice 1 is trying to establish.**

It must satisfy four constraints: read-only; only APIs already proven in this
repo (`AGENTS.md` rule 6 forbids guessing a PT signature); no shared state with
any CP-SCALE path; and it must exercise every envelope field.

Proposed behaviour — lazily seed a Script-Engine-global session id, then report
identity:

```
this.__mcpRuntime = this.__mcpRuntime || { session_id: <minted once>, protocol: 6 };
reportResult(JSON.stringify({ v:6, rid:<rid>, op:"runtime.identify", status:"ok",
  runtime:{ session_id: this.__mcpRuntime.session_id,
            session_origin:"script_engine_global",
            extension_version:null, protocol_version:6 },
  observed:{ pt_file_version: <String(getActiveFile().getVersion()||"")>,
             device_count: <ipc.network().getDeviceCount()> },
  mutated:null, error:null }));
```

**Why the global-seeding works without a `.pts` rebuild — and this is the
load-bearing finding of the audit.** Cross-command persistence on `this` is
*already shipped production behaviour*, not a hypothesis:

- `enterprise_security_runtime.py:566` writes
  `this.__mcpE8Http = this.__mcpE8Http || {}` and stores a live client handle
  into it;
- `enterprise_security_runtime.py:581,591` read that same object back in
  **separate, later** dispatches and find the handle;
- `enterprise_service_runtime.py:384-406` does the same with
  `this.__mcpE6HttpClients`;
- both run through `_bridge_send_and_wait`, so the behaviour holds on **both**
  transports.

So `this` at the top of a generated command body is the Script Engine global,
and it survives across dispatches. That is exactly the lifetime
`runtime_session_id` requires — and it means the id is genuinely
Script-Engine-scoped (survives the webview closing) without recompiling
anything.

Both reads are proven in-repo: `getActiveFile().getVersion()` at
`tool_registry.py:4746`, `ipc.network().getDeviceCount()` at
`tool_registry.py:4748`.

Honest limits to state in the implementation, not discover later:

- The id is seeded on the **first V6 command of a PT session**, not at extension
  load. It proves "same Script Engine global since first V6 contact" — which is
  the property actually needed — not "PT started at time T".
- `getActiveFile().getVersion()` is the **file's** PT version, not the running
  application's. Name the field `pt_file_version`, never `pt_version`.
- `extension_version` stays `null`. The caller-supplied `extension_version`
  parameter must not be used to fill it.
- Whether `this` resolves to the global under *every* PT evaluation path is
  proven for the two shipped runtimes above; if a future path differs, the
  operation must degrade to `session_id: null`, never to a fabricated value.
  Per `AGENTS.md`, anything about the PT webview/script-engine boundary
  **cannot be verified from tests** and must be labelled as requiring live
  confirmation.

### Q6 — How should legacy V5 coexist with V6 during migration?

**Additively, with V6 as an opt-in second reader and V5 untouched as the
default. No shared mutable state.**

1. V5 payload builders, guards, and prefixes are **frozen**. Not deprecated, not
   rewritten — frozen.
2. V6 adds a *parallel* helper alongside `_bridge_send_and_wait`; it does not
   change that function's behaviour or signature.
3. Detection is by parse, not by flag: a response that parses as JSON **and**
   carries `v: 6` **and** echoes the expected `rid` is V6. Anything else is V5
   text, handled exactly as today. No response can be misread as V6 by accident,
   because `rid` echo is required.
4. `protocol_version` is negotiated by *observation*, never assumed. A responder
   that does not answer V6 is a V5 responder; that is a normal state, not an
   error.
5. No caller migrates in slice 1.
6. V5 removal is gated on CP-SCALE being closed **and** every caller migrated.
   Neither is true.

### Q7 — What exact raw-JS paths must remain legacy-only?

Given that the transport *is* a raw-JS path (§1.11), "legacy-only" means: paths
that must never be reachable *through the typed dispatcher*, and must never
produce a V6 envelope.

| Path | Rule |
|---|---|
| `pt_send_raw` (`tool_registry.py:2333`) | **Never** gains a typed op, never emits a V6 envelope, never gains `runtime_session_id`. It must remain unable to masquerade as a typed mutation — the property `TD-PUBLIC-001` was closed on. Stays behind `PT_MCP_PUBLIC_SURFACE=developer-capability-investigation`. |
| `bootstrapSnippet()` display string (`interface.js:50-61`) | Legacy V5 HTTP bootstrap. Not a V6 surface. |
| `report_result_js` (`live_bridge.py:83-108`) | Stays as the V5 HTTP result mechanism. V6 rides *on top of* it in slice 1 rather than replacing it — replacing it needs a `.pts` change. |
| `_js_guard` silent catch (`tool_registry.py:862-871`) | Stays for V5 fire-and-forget. V6 must **not** adopt a silent catch: an error must become a structured `error`, never silence. |
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
or is provably non-mutating.** `runtime.identify` being strictly read-only is
what keeps this clean. Second, this worktree has **no `.venv`**; per `AGENTS.md`
the suite must run on the checkout-local interpreter, so one must be created
here before any V6 test run.

### Q9 — Which pieces depend on PTBuilder or untracked external files?

| Piece | Dependency | Status in this checkout |
|---|---|---|
| Rebuilding the `.pts` | `userfunctions.js`, `devices.js`, `links.js`, `modules.js`, `runcode.js`, `windows.js` — PTBuilder reference copies | **ABSENT.** `.gitignore` excludes `EXTENSION/script-engine/*.js` except `main.js`; verified — only `main.js` and `README.md` are present. PTBuilder carries **no license**, so they are not redistributed. |
| `runCode` (the HTTP executor) | Packet Tracer built-in | Not ours, not in this repo, not modifiable |
| Any `main.js` change | requires the above to package | **BLOCKED** |
| `run_<name>` claim marker (Q4) | requires a `main.js` change | **BLOCKED** |
| Extension-reported `extension_version` | requires a `main.js` change | **BLOCKED** |
| JSON *request* envelope parsing in the engine | requires a `main.js` change | **BLOCKED** |
| `installMcpHelpers()` improvements | requires a `main.js` change | **BLOCKED** |
| **Python-generated typed dispatcher (slice 1)** | **none** | **NOT BLOCKED** — this is why slice 1 is shaped this way |
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
   (`tool_registry.py:862-1009,1520-1552`). Additive helpers only.
3. **Changing `report_result_js` or the `PT_ERROR:` / `ERROR:` prefixes.** ~216
   call sites parse these by prefix. A prefix change is a silent
   mass-misclassification.
4. **Touching the shared mailbox lifecycle.** CP-SCALE and any V6 experiment
   share one directory. `_purge_own_stale` is deliberately scoped to
   `<pid>_<boot>_` and must stay that way (`file_bridge.py:318-335`) — a broader
   purge would delete a live CP-SCALE request.
5. **Any mutating V6 probe.** Would enter the shared PT network model. This is
   why slice 1 is read-only.
6. **Changing transport selection or health semantics.** `select_transport`
   pins a transport for a whole operation and forbids replaying an ambiguous
   mutation (`transport_health.py:86-128`). Perturbing it mid-run could re-route
   a CP-SCALE operation across channels — precisely what the design forbids.
7. **Adding a bridge endpoint.** `AGENTS.md` rule 3; also a restart of the HTTP
   bridge would drop the queue.
8. **Running the suite with the wrong interpreter.** `AGENTS.md` documents that
   the main-checkout `.venv` silently resolves `packet_tracer_mcp` to the *main
   checkout* — a V6 test run could import CP-SCALE's tree.
9. **`graphify update .`** — writes to a shared, gitignored working directory.

---

## Part 5 — First implementation slice (proposed, NOT implemented)

**Scope: one read-only typed operation, one result envelope, one error taxonomy,
Python-side only. No extension change. No caller migration. No V5 removal.**

Deliverables:

1. `infrastructure/execution/runtime_protocol.py` (new) — `PROTOCOL_VERSION = 6`,
   `RuntimeErrorCode`, `RuntimeResultEnvelope`, `parse_runtime_envelope()`
   returning `None` for anything that is not a valid V6 envelope with a matching
   `rid`.
2. `infrastructure/execution/runtime_dispatcher.py` (new) — builds the
   Script-Engine dispatcher JS for one op (`runtime.identify`), with every
   interpolated field via `json.dumps` per `AGENTS.md` rule 1.
3. A thin caller that sends via the **existing** `_bridge_send_and_wait` and
   parses via `parse_runtime_envelope`. No transport code changes.

Explicitly out of scope: JSON request envelope, `run_<rid>` claim marker,
extension-reported version, mutating ops, migrating any caller, removing any V5
code, any `.pts` work.

### Files likely to change

| File | Change |
|---|---|
| `src/packet_tracer_mcp/infrastructure/execution/runtime_protocol.py` | **new** |
| `src/packet_tracer_mcp/infrastructure/execution/runtime_dispatcher.py` | **new** |
| `tests/test_runtime_protocol_v6.py` | **new** |
| `tests/test_runtime_protocol_v6_compatibility.py` | **new** |
| `docs/architecture/mcp-runtime-protocol-v6-foundation.md` | this document |
| `src/packet_tracer_mcp/infrastructure/execution/__init__.py` | export only, if the module's convention requires it |
| `EXTENSION/**` | **none** |
| `live_bridge.py`, `file_bridge.py`, `tool_registry.py` | **none** |

### Tests to add

1. A V6 envelope round-trips; a mismatched `rid` is rejected.
2. A V5 text response (`PT_ERROR: ...`, `ERROR:...`, `OK`, `MISSING`) parses as
   **not-V6** and is left untouched — no V5 string is ever reinterpreted.
3. A JSON response *without* `v: 6` is not-V6 (guards against the 118 existing
   `JSON.stringify` sites being misread as V6).
4. Every `RuntimeErrorCode` is reachable and distinct from `RequestDisposition`,
   `TransportHealthState`, and `BridgePreflightState`.
5. The generated dispatcher JS contains no f-string interpolation; every dynamic
   field is `json.dumps`-encoded (`AGENTS.md` rule 1). Assert on source, in the
   style of `test_probe_naming_contract.py`.
6. The generated JS names **no** mutating PT API — keeps
   `test_transport_mutation_containment.py`'s sweep green by construction.
7. `runtime.identify` emits `mutated: null` structurally; a read-only op cannot
   express a mutation.
8. `extension_version` is `null` and is never populated from the caller-supplied
   MCP parameter.
9. The dispatcher JS is a self-contained statement that survives `\n`
   concatenation with other commands (HTTP batching, `live_bridge.py:369`).
10. The full existing suite still passes, on a worktree-local `.venv`.

### Risks

| Risk | Severity | Mitigation |
|---|---|---|
| `this` is not the Script Engine global on some evaluation path | **Medium** | Proven for two shipped runtimes on both transports (Q5), but unverifiable offline per `AGENTS.md`. Degrade to `session_id: null`; never fabricate. Label as requiring live confirmation. |
| A V5 JSON response is misread as V6 | Low | Require `v == 6` **and** `rid` echo. Test 3. |
| The new module trips the mutation-containment sweep | Low | Strictly read-only; test 6 asserts it. |
| Session id seeded late reads as "PT start time" | Low | Name it `session_origin: "script_engine_global"` and document what it proves. |
| `pt_file_version` mistaken for the app version | Low | Name the field for what it is. |
| Slice 1 perturbs CP-SCALE | Low | No shared file changed; no mutation; no transport change. |
| Scope creep into the claim marker / `.pts` | **Medium** | Blocked by Q9 and stated out-of-scope here. |

---

## Part 6 — Interference and dependency assessment

**PTBUILDER_DEPENDENCIES** — Rebuilding the `.pts` needs six PTBuilder reference
`.js` files that are `.gitignore`d and not redistributed (no license). Verified
absent: `EXTENSION/script-engine/` holds only `main.js` and `README.md`. This
blocks the `run_<rid>` claim marker, extension-reported `extension_version`,
engine-side JSON request parsing, and any `installMcpHelpers` change. It does
**not** block slice 1, which is Python-only by design.

**CP_SCALE_INTERFERENCE_RISK** — **LOW, conditional on the stated scope.** Slice
1 adds two new Python modules and two new test files, changes no shared file,
performs no mutation, alters no transport behaviour, and requires no PT
interaction to develop. The residual risks are operational, not architectural:
the shared mailbox directory (untouched by slice 1), and using the wrong
interpreter (`AGENTS.md`). This assessment holds **only** while the scope in
Part 5 holds; it does not extend to migrating callers or touching the `.pts`.
