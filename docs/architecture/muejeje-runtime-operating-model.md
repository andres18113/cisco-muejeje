# Muejeje runtime operating model

Muejeje is a **generic Packet Tracer runtime**: an owned PT Script Module
(`muejeje.pts`) plus the Python side that speaks to it. It is not a feature of
any scenario, and it has no scenario-shaped concepts of its own.

## Authority

For claims about existing product behaviour, `src/`, tests and runtime evidence
are authoritative, then `AGENTS.md`, then this operating model, then ADR/QA
documents. A document never overrides observed product behaviour; when the two
disagree, the document is corrected. Every claim distinguishes evidence observed
from inference drawn.

## Lifecycle and roadmap ownership

**Muejeje owns its own lifecycle.** Its roadmap, gates and release cadence are
decided here, not inherited from any other work stream.

| Relationship | Role |
| --- | --- |
| Runtime Protocol V6 | **northbound / public contract** — what Muejeje offers its consumers |
| Packet Tracer + its IpcAPI | **southbound / platform compatibility contract** — what Muejeje consumes |
| CP LIVE | **one integration consumer.** It exercises Muejeje; it does not define it |
| `refactor/cp-live-m0-baseline` | the commit this branch was re-parented onto — an **initial ancestry correction only** |
| `feature/runtime-protocol-v6-foundation` | donor/reference for V6 shapes; never merged |

### Two contracts, not one

An earlier wording called Packet Tracer and its IpcAPI *the only* contract
Muejeje must satisfy. That is too broad: it describes the platform Muejeje
depends on and silently omits the contract Muejeje itself publishes.

```text
Consumers / MCP / projects
        │
 Runtime Protocol V6      ← northbound: what consumers may rely on
        │
   muejeje.pts
        │
    Cisco IpcAPI          ← southbound: what Muejeje must adapt to
        │
 Packet Tracer
```

- **Northbound (V6)** is a contract Muejeje **owns**. Consumers depend on it and
  on nothing else — not on internals, not on the transport, not on Packet Tracer
  specifics. Muejeje decides when it changes, and changing it is a consumer-
  visible event.
- **Southbound (IpcAPI)** is a contract Muejeje **does not own**. Muejeje adapts
  to it, never extends or reinterprets it, and every claim about its behaviour
  needs target-build evidence.

The two are independent: a southbound change must not reach consumers as a V6
change unless V6 genuinely changed. Keeping them named separately is what makes
that check possible. V6 itself is not designed here — see
[the requirements baseline](muejeje-pts-requirements.md) (`MJ-005`, `MJ-006`).

Consequences, stated so they cannot be quietly reversed:

- **CP LIVE is not Muejeje's upstream.** No branch is. Muejeje does not track,
  follow or wait on another branch's head.
- **Future CP LIVE commits do not automatically block Muejeje development.** A CP
  LIVE change matters here only when it changes something Muejeje actually
  depends on, and then only after that dependency is demonstrated.
- **A CP LIVE SHA may be recorded as integration evidence, never as the runtime
  contract.** Write it next to what it evidences ("integration observed against
  CP LIVE `<sha>`"), never as a version, prerequisite or watermark.
- **No scenario behaviour enters Muejeje.** No consumer's identifiers — a
  project name, one topology's device names, a fixed address — and no behaviour
  that assumes them belongs in the runtime, the build tooling or the provenance
  schema. Scenario knowledge lives in the consumer. Generic networking
  vocabulary is a different thing and is not excluded: DHCP, VLAN, OSPF and PoE
  are Packet Tracer's domain, and a runtime that may not name them could not
  describe the platform it adapts to (`MJ-004`).
- Re-parenting the branch onto the baseline was a one-time ancestry fix. It
  created no ongoing subordination and no obligation to re-sync.

### Ancestry record

`feature/muejeje-pts` was recreated from
`refactor/cp-live-m0-baseline` at `e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43`
(confirmed local, remote-tracking and on the real remote at the time), replacing
an older line whose merge-base was `a384a79f…`. The earlier governance model
named a moving branch as "UPSTREAM"; that framing is withdrawn. The pre-realign
state is preserved on the local ref `muejeje-pts-prealign-e2d912b`
(`e2d912b5fe8c67077c6b753e634967f626393d87`) for architectural review.

Details, with evidence markers, are in
[the v2 preflight inventory](../qa/muejeje-pts-v2-preflight-inventory.md),
[ADR-001](../qa/muejeje-pts-adr-001-branch-realignment.md) and its
[resolution](../qa/muejeje-pts-adr-001-resolution.md).

Binding requirements carry stable IDs in
[the requirements baseline](muejeje-pts-requirements.md); this document explains
the governance, that one records what is decided and how each item is verified.

## Runtime architecture

Stated in two halves, because an earlier revision of this section described the
target as though it were the present and then closed by asserting that
`mcpDispatchV6` did not exist — after it did. Both halves are needed: one says
what a consumer may send today, the other says what is still unbuilt.

**What exists.** One Script Module, seven engine files, one dispatcher, two
read-only operations, and no transport at all:

```text
consumer -> mcpDispatchV6(requestJson) -> bounded V6 admission -> V6 whitelist
         -> runtime.identify | runtime.capabilities
         -> one JSON envelope back
```

Admission is bounded: the request length, the correlation id, the operation
name and the shape and values of the arguments are all checked against limits
this runtime declares for itself, before any handler runs. **Those limits are
Muejeje's, not Packet Tracer's** (`MJ-029`).

Neither operation calls Packet Tracer: there is no `ipc.*` call anywhere in the
kernel, so the module requests no privilege to start. The artifact contains no
HTTP listener, no file mailbox and no polling loop, and the Custom Interface is
a static page that calls nothing and therefore reports no module state.

**What is not built.** The transport, the platform adapter and every mutating
operation. The target shape, with each stage marked:

```text
Python/MCP -> Runtime Protocol -> explicit channel policy   (unbuilt)
           -> HTTP webview | File Script Engine             (unbuilt)
           -> one runtime kernel -> mcpDispatchV6(...)      (built)
           -> whitelisted typed handler                     (built, read-only)
           -> documented ipc.*                              (unbuilt)
           -> structured result -> Python evidence/verdict  (built engine side)
```

**`APPLIED != VERIFIED`, permanently.** An acknowledged mutation is not an
observed effect. Every operation reports what was applied and what was
independently read back, and the two are never collapsed.

V6 principles:

- **One authoritative `mcpDispatchV6`.** No second dispatcher, no hidden retry,
  no ambiguous fallback after an ambiguous execution. It lives in
  `muejeje_pts/script-engine/dispatcher_v6.js` and a gate fails if a second one
  appears.
- **Typed, declarative, whitelisted, fail-closed.** The whitelist holds the
  read-only `runtime.identify` and `runtime.capabilities`. Version, schema and
  correlation mismatches fail closed.
- V6 identity is `(operation_rid, op)`. A request that does not declare protocol
  6 is refused as `PROTOCOL_MISMATCH` and never reinterpreted: V6 has no
  compatibility escape into V5, and the marker that once described one is
  withdrawn.
- **Raw JS is legacy V5 compatibility only.** Migrated operations accept no
  arbitrary JS input.
- `lwAddDevice` / `lwAddLink` may keep serving V5; they are **not** the V6 domain
  contract.

The kernel is verified offline, under Node, against our own JavaScript. It has
never run inside Packet Tracer and no `.pts` has yet been built from these
sources, so its live state is `NOT_YET_LIVE_VERIFIED` (`MJ-015`).

## PTBuilder independence

PTBuilder is **not** a required build input: the build manifest selects no
reference inputs, and the audit tool has no PTBuilder prerequisite.

At runtime the picture is different and must not be overstated. Six globals the
tracked sources still need are supplied by PTBuilder's script engine today —
`htmlWindow`, `runCode`, `configureIosDevice`, `allModuleTypes`, `addDevice`,
`addLink`. Removing them is Muejeje roadmap work; until each is replaced the
attribution stays in `EXTENSION/script-engine/README.md` and `.gitignore`, and no
document claims the runtime is already PTBuilder-free. Per-symbol evidence, owned
alternatives and the ADRs they need are in the v2 preflight inventory.

Numeric Cisco enum tables (`PT_DEVICE_TYPE`, `PT_CONNECT_TYPE`,
`ModuleSpec.module_type`) are working mirrors, **not** a source of truth.
`allModuleTypes` must ultimately resolve through the hardware factory's
**descriptor** API — `DeviceDescriptor.isModuleTypeSupported(...)` and
`ModuleDescriptor.getType()`, reached via
`ipc.hardwareFactory().devices().getDescriptor(...)`. A descriptor is not a
runtime `Module`, and the runtime module surface exposes neither. See `MJ-014`
for the evidenced distinction.

## Identity and provenance

Runtime identity reports name, version, source SHA, build recipe, session,
protocols, features and operations.

Recipe identity covers source commit/tree, the manifest, builder
identity/version/hash/options, and every artifact, tooling and reference input
hash. Tooling ships nothing into the artifact but still decides how it was
inspected, so it belongs to identity. The
external build manifest binds a recipe to a completed artifact's SHA-256; the
artifact hash is **never** embedded inside the artifact it describes. An
incomplete input inventory has no valid complete recipe ID — the tool returns
`null` while any blocker stands.

No byte-for-byte reproducibility is claimed. The two-build experiment that would
test it is specified in the v2 preflight inventory and is unexecuted.

## Connection evidence

Connection evidence separates: Script Engine liveness, File-channel activity,
webview presence, HTTP reachability, token validity, polling armed/time/
generation, and command received/completed/result. Reachability plus a valid
token with no observed polls is `POLLING_NOT_OBSERVED`, not proof of a connected
Packet Tracer. File-channel health says nothing about HTTP health.

Webview CORS behaviour, the `this-sm:` origin and IPC availability **cannot** be
established by offline tests. Say so rather than assuming.

## Build facts

Target build: Packet Tracer **9.0.1.0858**, `PacketTracer.exe` SHA-256
`843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1`.
PT 9.x behaviour claims require target-build evidence; Node- or fixture-level
tests never substitute for it.

Packaging is the Scripting Interface (Extensions → Scripting → New PT Script
Module → import engine and Custom Interface files → Save). Engine files evaluate
in listed order, then `main()`; `cleanUp()` runs on stop; `#include` resolves one
level and is expanded at save. `.pts` is an encrypted container, so content
validation is behavioural only. The complete procedure — preconditions, the
resolved recipe, the steps and what a run must record — is
[the packaging recipe](../qa/muejeje-pts-packaging-recipe.md). PTBuilder and
community or offline packagers are not used.

**Build state is five facts, not one.** The audit tool reports exactly one
dominant state and keeps the axes readable in a `packaging_state` block:

| State | Meaning |
| --- | --- |
| `BUILD_SOURCE_INVALID` | the source is unidentifiable, or dirty / differing from HEAD |
| `BUILD_INPUT_INVALID` | the manifest or an input violates the contract |
| `BUILD_TOOLCHAIN_BLOCKED` | **a genuine inability to build**: no usable Packet Tracer, or a declared input that is not on disk |
| `BUILD_AUTOMATION_UNPROVEN` | nothing is broken; the recipe is not fully specified and no automated packaging path is demonstrated |
| `PACKAGING_MANUAL_AVAILABLE` | a human can package this recipe in the Scripting Interface now |

`BUILD_TOOLCHAIN_BLOCKED` never means "no automation exists". Manual packaging
availability, automation provenness and recipe completeness are three separate
fields; no packaging CLI has been demonstrated, so `automation` stays
`BUILD_AUTOMATION_UNPROVEN` until evidence says otherwise and is never inferred
from a clean report.

`muejeje.pts` is an **owned artifact**. Candidate and report destinations are the
ignored `dist/muejeje.pts` and `dist/muejeje.build.json`; no existing `.pts` is
ever replaced automatically.

**The owned source root.** `muejeje_pts/` is what `muejeje.pts` is made of:

| Path | Role |
| --- | --- |
| `muejeje_pts/script-engine/` | Script Engine files, evaluated in listed order, then `main()` |
| `muejeje_pts/interface/` | Custom Interface files |
| `muejeje_pts/manifest/` | the build manifest — build metadata, not packaged |

`EXTENSION/**` is the legacy *MCP Control Center* extension. It is untouched, it
keeps serving the existing published `.pts`, and it is **not** a Muejeje input:
Muejeje's completeness check sweeps the owned root alone. The legacy `main.js`
was not copied — its six PTBuilder globals are what the owned artifact must not
inherit.

Build inputs are three categories, not one (`schema_version: 2`):

| Category | Contains | In the recipe? |
| --- | --- | --- |
| `artifact_inputs` | only bytes packaged into the `.pts`; must live under the owned root | yes |
| `tooling_inputs` | the auditor (`build.py`, the CLI) — ships nothing, but decides how the artifact was inspected | yes |
| `reference_inputs` | empty; any future entry stays untracked, ignored and hash-pinned | yes |

A path may not appear in two categories. `TODO-SRC-ROOT` and
`TODO-RECIPE-SCOPE` are resolved by this; see
[the requirements baseline](muejeje-pts-requirements.md).

The owned root being free of PTBuilder code does **not** make the runtime
PTBuilder-free (`MJ-013`). The owned root now carries the V6 kernel and two
read-only operations, but the runtime consumers actually use is still the
legacy one, and independence is proven when a built artifact demonstrates it
inside Packet Tracer — not before.

## Gates

Advance a gate only when its prerequisite is demonstrated, never when it is
assumed. Do not build or install a `.pts`, run LIVE, or rewrite shared history
without explicit authorization. An authorized LIVE session is read-only, records
source/artifact/session/channel/PT identities, and exercises both channel
lifecycles.
