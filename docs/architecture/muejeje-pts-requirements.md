# Muejeje `.pts` — requirements baseline

Stable requirement IDs for the Muejeje runtime. Every ID is permanent: it is
superseded or withdrawn, never renumbered or reused.

This baseline records **only decisions already taken**. Anything still undecided
is in [Open decisions](#open-decisions) as a TODO, not as a requirement.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| `ENFORCED` | Decided **and** verified by a test, a tool check, or recorded evidence. |
| `BASELINED` | Decided and binding, but nothing yet verifies it automatically. |
| `BASELINED (deviation)` | Decided and binding; the current code knowingly does not meet it yet, and the gap is named. |

`APPLIED != VERIFIED` applies to this table too: a requirement marked
`BASELINED` is a commitment, not a claim that the system already satisfies it.

## Architecture position

```text
Consumers / MCP / projects
        │
 Runtime Protocol V6      ← northbound: the public contract Muejeje offers
        │
   muejeje.pts
        │
    Cisco IpcAPI          ← southbound: the platform contract Muejeje consumes
        │
 Packet Tracer
```

## Scope and independence

### MJ-001 — Generic, project-independent runtime
**Requirement.** Muejeje is a general-purpose Packet Tracer runtime. It contains
no logic specific to any consumer project, deployment or customer.
**Rationale.** A runtime that encodes one consumer's assumptions cannot serve a
second one, and its behaviour stops being explainable from its own contract.
**Verification.** The artifact has its own source root, `muejeje_pts/`, and an
architecture test pins that nothing else is packaged into it.
**Status.** `ENFORCED` for the source boundary; `BASELINED` for behaviour, which
does not exist yet.

### MJ-002 — Topology agnostic
**Requirement.** Muejeje makes no assumption about device counts, models, roles,
naming, addressing or link layout. It never hardcodes a topology or a fragment
of one.
**Rationale.** Topology is the consumer's domain. A runtime that knows a topology
has silently become part of that consumer.
**Verification.** Review; absence of topology fixtures in the runtime and in the
build inputs.
**Status.** `BASELINED`

### MJ-003 — Capability-driven behaviour
**Requirement.** Behaviour is selected from capabilities observed at runtime, not
from assumptions about what a Packet Tracer build supports.
**Rationale.** Packet Tracer builds differ in what the IpcAPI exposes. Assuming
support produces a bare `Invalid arguments for IPC call "X"` with no diagnosis.
**Verification.** Capability probes and their recorded evidence; `AGENTS.md`
rule 6 ("never guess a PT API signature").
**Status.** `BASELINED`

### MJ-004 — Consumer-specific logic stays outside Muejeje
**Requirement.** Scenario, project and integration logic lives in the consumer.
CP LIVE, PoE, Router0, voice, VLAN and topology concerns never enter the
runtime, the build tooling or the provenance schema.
**Rationale.** This is MJ-001 stated as an exclusion, so that a violation is
recognisable rather than arguable.
**Verification.** `tests/muejeje/test_source_root.py` fails if a consumer's
vocabulary appears in any packaged source under the owned root.
**Status.** `ENFORCED`

## Contract boundaries

### MJ-005 — Runtime Protocol V6 is the consumer-facing contract
**Requirement.** Everything a consumer may rely on is expressed in Runtime
Protocol V6. Consumers do not depend on Muejeje internals, on the transport, or
on Packet Tracer specifics.
**Rationale.** One northbound contract is what makes consumers replaceable and
makes Muejeje's own internals free to change.
**Verification.** The V6 envelope and its conformance tests
(`tests/muejeje/test_protocol_v6.py`).
**Status.** `ENFORCED` for the envelope and for `runtime.identify`; `BASELINED`
for every operation not yet migrated to V6 — consumers still reach the legacy
runtime for those.

### MJ-006 — Packet Tracer and its IpcAPI are the platform boundary
**Requirement.** The southbound compatibility contract is Packet Tracer and its
IpcAPI. Muejeje adapts to it; it does not extend or reinterpret it.
**Rationale.** The platform is the one thing Muejeje cannot change. Naming it as
the boundary keeps compatibility work in one place.
**Verification.** All platform access goes through documented or evidenced
`ipc.*` calls; deviations recorded with evidence.
**Status.** `BASELINED (deviation)` — six PTBuilder globals still sit between
Muejeje and the IpcAPI; see MJ-012.

## V6 dispatch

### MJ-007 — One authoritative `mcpDispatchV6`
**Requirement.** Exactly one dispatcher. No second dispatcher, no alternate
entry point, no shadow path.
**Rationale.** Two dispatchers means two answers to "what actually ran", and
evidence stops being attributable.
**Verification.** Two gates: `tests/muejeje/test_source_root.py` fails if a
second `mcpDispatchV6` appears anywhere in the owned tree, and
`tests/muejeje/test_protocol_v6.py` fails if the one in `dispatcher_v6.js`
disappears.
**Status.** `ENFORCED` — one dispatcher, in `dispatcher_v6.js`.

### MJ-008 — V6 is typed, declarative, whitelisted and fail-closed
**Requirement.** V6 operations are typed and declarative, admitted by an explicit
whitelist, and fail closed on version, schema or correlation mismatch. The
initial whitelist contains only read-only `runtime.identify`.
**Rationale.** A permissive dispatcher cannot bound what a consumer can cause.
**Verification.** One negative test per rejection class, plus a gate that the
dispatcher holds no operation implementation and the protocol module holds no
whitelist. See MJ-022 for the taxonomy those tests pin.
**Status.** `ENFORCED` — the whitelist admits `runtime.identify` alone, and
every other name fails closed.

### MJ-009 — Raw JavaScript is V5 compatibility only
**Requirement.** Arbitrary JavaScript execution is a legacy V5 surface. Migrated
V6 operations accept no arbitrary JS.
**Rationale.** Raw JS is unbounded by construction; keeping it out of V6 is what
lets V6 make any guarantee at all.
**Verification.** `tests/muejeje/test_source_root.py` fails on `eval`,
`new Function` or any `Function(` call in the owned tree; the V6 dispatcher
admits no argument that is not on an operation's whitelist.
**Status.** `ENFORCED` for the owned V6 kernel, which has no path that executes
a caller's JavaScript; `BASELINED` for the legacy V5 surface, which is still in
use outside the owned tree.

## Evidence

### MJ-010 — `APPLIED != VERIFIED`
**Requirement.** An acknowledged mutation is never reported as an observed
effect. Every operation distinguishes what was applied from what was
independently read back.
**Rationale.** Packet Tracer acknowledges work it has not completed. Collapsing
the two produces confident false results.
**Verification.** Read-back assertions in runtime tests; recorded evidence keeps
the two fields separate.
**Status.** `ENFORCED` for existing operations that read back (for example the
exact link read-back after `addLink`); `BASELINED` for V6.

### MJ-011 — Python owns the final evidence and verdict
**Requirement.** The script engine returns structured observations. The verdict —
whether an operation succeeded — is decided in Python.
**Rationale.** The engine cannot audit itself, and a verdict computed where the
mutation happened is not independent.
**Verification.** Runtime handlers return data, not verdicts; Python-side
qualification tests.
**Status.** `BASELINED`

### MJ-012 — No hidden retry or fallback after an ambiguous execution
**Requirement.** When an execution's outcome is ambiguous, Muejeje stops and
reports. It never silently retries, and it never falls back to a second path.
**Rationale.** A hidden retry converts one ambiguous result into an unattributable
one, and a silent fallback hides which path produced the effect.
**Verification.** Review of every `catch` that continues; explicit ambiguity
outcomes in operation results.
**Status.** `BASELINED (deviation)` — `main.js` `lwAddDevice` falls back to the
global `addDevice` inside `try{…}catch(e){}` when the logical-workspace call
returns falsy. Recorded in the v2 preflight inventory; not yet fixed.

## Platform independence

### MJ-013 — No PTBuilder production or build dependency
**Requirement.** PTBuilder is neither a build input nor a runtime dependency of
the owned artifact. Its attribution stays while any dependency remains, and no
document claims independence that the code has not reached.
**Rationale.** PTBuilder is unlicensed; depending on it blocks distribution and
makes the runtime unexplainable from its own sources.
**Verification.** `reference_inputs: []` in the manifest, the regressions in
`tests/muejeje/test_inventory.py`, and an architecture test that fails if any of
the six globals appears in the owned sources.
**Status.** `ENFORCED` for the build inputs; `BASELINED (deviation)` for the
runtime — `htmlWindow`, `runCode`, `configureIosDevice`, `allModuleTypes`,
`addDevice` and `addLink` are still PTBuilder-supplied.

> An owned source root that contains no PTBuilder code does **not** satisfy this
> requirement, and neither does a V6 kernel that runs under Node. The owned tree
> now has behaviour — the kernel and `runtime.identify` — but the runtime that
> consumers actually use is still the legacy one, and no `.pts` has been built
> from these sources. Independence is proven when a built artifact runs in
> Packet Tracer and demonstrates it, not before.

### MJ-014 — No numeric Cisco enum table is a source of truth
**Requirement.** Hand-maintained numeric tables mirroring Cisco enums are working
copies. Authoritative values come from the Packet Tracer hardware factory's
descriptor API.
**Rationale.** A mirrored constant is correct only until Packet Tracer changes,
and nothing in the repository would notice.

**The two APIs are different, and only one answers this question.** Both are
evidenced in this repository against Packet Tracer `9.0.1.0858`; neither is
guessed (`AGENTS.md` rule 6).

| | Runtime `Module` | `ModuleDescriptor` |
| --- | --- | --- |
| Reached from | `ipc.network().getDevice(name)` → `Device.getRootModule()` | `ipc.hardwareFactory().devices().getDescriptor(DeviceType, model)` → `DeviceDescriptor.getRootModule()` |
| Describes | hardware installed in an instantiated device on the workspace | what a model *can* accept, without instantiating or powering anything |
| Observed getters | `getModuleCount()`, `getModuleAt(i)`, `getSlotTypeAt(i)`, `getModuleNameAsString()`, `getModuleNumber()`, `getPortCount()` | `getModel()`, `getType()`, `isHotSwappable()`, `getSlotCount()`, `getSlotTypeAt(i)`, `getModuleCount()`, `getModuleAt(j)` |
| Module-type support | not exposed here | `DeviceDescriptor.isModuleTypeSupported(int)` |

So the authoritative lookup for a module type is
`DeviceDescriptor.isModuleTypeSupported(...)` together with
`ModuleDescriptor.getType()` — **`isModuleTypeSupported` is a descriptor method,
not a method on a runtime device**, and the runtime `Module` surface evidenced
here exposes no `getType()` at all. A descriptor is not a runtime `Module`, and
no descriptor field establishes installed hardware or power delivery.

**Evidence.** `infrastructure/execution/poe_delivery_runtime.py`
(`observe_factory_structure`) drives the descriptor path and names the API in its
docstring; `infrastructure/execution/probe_runtime.py` and
`packet_tracer_physical_runtime.py` drive the runtime path;
`docs/reference/cp-scale/ROUTER0_POE_FACTORY_STRUCTURE_20260907.md` records the
LIVE observation against `9.0.1.0858`.

**Verification.** Enum values reconciled against the descriptor API; each mirror
marked as a mirror at its definition.
**Status.** `BASELINED (deviation)` — `PT_DEVICE_TYPE` (33 entries),
`PT_CONNECT_TYPE` (16) and `ModuleSpec.module_type` (151) are mirrors in use, and
`allModuleTypes` is still PTBuilder's table.

> An earlier revision of this requirement cited
> `device.isModuleTypeSupported(int)` and `module.getType()`, attributing both to
> the runtime device/module surface. That was wrong on both counts and is
> corrected above.

### MJ-015 — Packet Tracer 9.x claims require target-build evidence
**Requirement.** No statement about Packet Tracer 9.x behaviour is made without
evidence from the pinned target build. Fixture, Node or offline tests never
substitute for it.
**Rationale.** Offline tests establish our code's behaviour, not the platform's.
`AGENTS.md` already forbids guessing a PT API signature.
**Verification.** The manifest pins the builder identity and hash; PT-dependent
tests are guarded and skip when the target build is absent.
**Status.** `ENFORCED` — builder pinned to `9.0.1.0858`, SHA-256
`843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1`; the two
builder-dependent tests skip when it is not installed.

## Build and provenance state

### MJ-016 — Build state distinguishes five facts
**Requirement.** The build audit reports `BUILD_SOURCE_INVALID`,
`BUILD_INPUT_INVALID`, `BUILD_TOOLCHAIN_BLOCKED`, `BUILD_AUTOMATION_UNPROVEN`
and `PACKAGING_MANUAL_AVAILABLE` as distinct states.
`BUILD_TOOLCHAIN_BLOCKED` means a genuine inability to build, never the mere
absence of automation.
**Rationale.** The earlier model appended an unconditional compile-adapter
blocker, so every clean repository reported `BUILD_TOOLCHAIN_BLOCKED` and three
different facts were indistinguishable.
**Verification.** `classify_build_state()` and its precedence test; the
`packaging_state` block; `tests/muejeje/test_build_state.py`.
**Status.** `ENFORCED`

### MJ-017 — An incomplete input inventory has no recipe id
**Requirement.** `build_recipe_id` is null while any input is unresolved. The
artifact SHA-256 is measured externally and is never embedded in the artifact it
describes. Byte-for-byte reproducibility is not claimed.
**Rationale.** A recipe id over an incomplete inventory identifies nothing, and a
self-embedded hash cannot be checked.
**Verification.** `tests/muejeje/test_provenance.py`; the recipe id is set
only in `PACKAGING_MANUAL_AVAILABLE`.
**Status.** `ENFORCED`

## Architecture and maintainability

These apply to **Muejeje-owned code going forward** — the owned source root, the
build auditor, its CLI and the Muejeje test area. They are not a claim about
unrelated legacy code, which was written under no such budget and is out of
scope until it is rewritten for another reason.

### MJ-018 — Modular cohesion and single responsibility
**Requirement.** Every owned module has one responsibility, named in its own
docstring. The build auditor is split into a facade (`build.py`), a state model
(`build_state.py`), a schema (`manifest.py`), an input inventory
(`inventory.py`) and source/hash/recipe identity (`provenance.py`). The public
API is the facade; splitting a module never changes it.
**Rationale.** One 540-line `build.py` held the state machine, the schema, the
path rules and every Git call, so no rule could be read, tested or changed
without loading all of them. Splitting by responsibility is what makes a rule
locatable.
**Verification.** `tests/muejeje/test_architecture.py` pins the module set
against the declared layers and fails on an undeclared module; the facade is
asserted to hold no vocabulary of its own.
**Status.** `ENFORCED`

### MJ-019 — Dependency direction is inward and one-way
**Requirement.** In the auditor, `build_state`, `manifest` and `provenance`
depend on no sibling; `inventory` may depend on `build_state` and `provenance`;
only `build` may depend on all of them. In the runtime, the direction is
`lifecycle → dispatcher/operations → protocol + core`, and the V6 core depends
on none of CP LIVE, WebView, HTTP, the File Bridge, PTBuilder, legacy `runCode`
or arbitrary JavaScript execution. Cisco IPC access is an adapter concern and
stays outside protocol, core and operation logic.
**Rationale.** A cycle makes every module the whole system again, which is what
the split was for. Naming the direction is what lets a violation be detected
instead of argued.
**Verification.** An import-graph test per auditor module; a source gate over
the owned root for the forbidden runtime layers and for `ipc.*`.
**Status.** `ENFORCED`

### MJ-020 — Source and test complexity budgets
**Requirement.** Owned files stay within a target and never cross a hard limit:

| Type | Target | Hard limit |
| --- | ---: | ---: |
| Python module | 300 | 500 |
| Python test module | 300 | 500 |
| Script Engine JS | 250 | 400 |
| function/method | 40 | 80 |

Generated, minified, data and evidence files are excluded. A file over target
carries a named justification in the gate itself. A hard-limit exception
requires an explicit architectural justification, and moving the same oversized
responsibility into another file does not satisfy it.
**Rationale.** A budget nobody measures is a preference. These numbers are the
point at which a reviewer stops holding a file in their head.
**Verification.** `tests/muejeje/test_architecture.py` measures every owned
Python module, test module and Script Engine file, and every function in them.
Function length is measured as code lines with the docstring subtracted, so the
budget constrains branching and never discourages an explanation.
**Status.** `ENFORCED`

### MJ-021 — Architecture fitness is a gate, not a review note
**Requirement.** Every architectural rule Muejeje states about its own code is
enforced by a test that fails when the rule is broken: complexity budgets,
dependency direction, the absence of PTBuilder globals and consumer vocabulary,
the absence of arbitrary JavaScript execution, exactly one `main()`, one
`cleanUp()` and one `mcpDispatchV6`, the `ipc.*` boundary, and the separation of
the test area by responsibility.
**Rationale.** M0E's boundary held because a test failed when it was crossed.
Rules that live only in a document are re-argued at every change.
**Verification.** `tests/muejeje/test_architecture.py` and
`tests/muejeje/test_source_root.py`; the retired monolithic test modules are
asserted absent so the split cannot silently reverse.
**Status.** `ENFORCED`

## Runtime Protocol V6 contract

### MJ-022 — One envelope, and a failure taxonomy that names the cause
**Requirement.** `mcpDispatchV6(requestJson)` takes a JSON string and returns a
JSON string. Every outcome uses the same envelope —
`{v, operation_rid, op, ok, result, error}` — so a consumer parses one shape.
A refusal names its class:

| Code | Cause |
| --- | --- |
| `MALFORMED_REQUEST` | not a JSON string, not JSON, or not a JSON object |
| `PROTOCOL_MISMATCH` | readable, but not addressed to protocol 6 |
| `INVALID_REQUEST` | a V6 envelope that violates the envelope contract |
| `UNKNOWN_OPERATION` | an operation the whitelist does not admit |
| `INVALID_ARGS` | a whitelisted operation given arguments it does not support |
| `ENGINE_EXCEPTION` | the operation handler itself failed |

`ENGINE_EXCEPTION` is reserved for the last row. A malformed request, a
protocol mismatch and a validation failure are never reported as one: nothing
went wrong inside the engine when a request was simply not admissible.
Error messages are fixed strings and never echo a caller-supplied name or
value. The dispatcher never throws out of the engine.
**Rationale.** One shape is what makes a consumer's parser total. One code per
cause is what makes a failure diagnosable without reading the runtime's source
— which MJ-005 forbids relying on anyway.
**Verification.** `tests/muejeje/test_protocol_v6.py` drives one case per
rejection class and asserts the shared envelope shape across success and
failure.
**Status.** `ENFORCED`

### MJ-023 — `runtime_session_id` is correlation evidence, never authentication
**Requirement.** The runtime session id is non-secret, stable for one Script
Module session, and different between sessions. It exists so two observations
can be attributed to the same run. It grants nothing, proves nothing about who
is calling, and the runtime never compares it against anything.
**Rationale.** A stable per-session token is exactly the shape people mistake
for a credential. Saying what it is not, in the contract and in the source, is
what stops it from quietly becoming one.
**Verification.** `tests/muejeje/test_runtime_identify.py` asserts stability
within a session (including across a `main()`/`cleanUp()`/`main()` cycle),
difference between sessions, and that no kernel source compares the id.
**Status.** `ENFORCED`

### MJ-024 — The runtime reports provenance as bound or explicitly unbound
**Requirement.** `runtime.identify` reports `provenance` with an explicit
`state`. Nothing binds a source SHA or a build recipe id into the artifact
today, so it reports `UNBOUND` with both fields null. Neither value is ever
guessed, derived at runtime, or filled in from anything the runtime can reach.
The artifact's own SHA-256 is never embedded in the artifact.
**Rationale.** An unbound field reported as a value is a fabricated provenance
claim, and a fabricated one is worse than a missing one because it looks
checkable. MJ-017 says this about the build report; this says it about the
runtime.
**Verification.** `tests/muejeje/test_runtime_identify.py` pins the unbound
shape and fails if any kernel source mentions `ARTIFACT_SHA256`.
**Status.** `ENFORCED`

## Open decisions

Not requirements. Each needs a decision before it can become one.

| TODO | Question | Blocks |
| --- | --- | --- |
| **TODO-MANIFEST-HOME** | The manifest now lives at `muejeje_pts/manifest/`. Its path is pinned in `infrastructure/pts/manifest.py`; if the owned root is ever renamed, that pin moves with it. | — |
| **TODO-MODULE-ID** | The Script Module ID and its stability across rebuilds. | `build_options.module_id` |
| **TODO-STARTUP** | `On Startup` vs `On Demand`. The file channel only runs while the module runs. | `build_options.startup` |
| **TODO-PRIVILEGES** | The requested IPC privilege set. The privilege catalogue lives in `.pki` files that are not installed. | `build_options.privileges` |
| **TODO-SIGNING** | Publisher signing (PKCS#12) and key custody. | reproducibility |

### Resolved

| TODO | Resolution |
| --- | --- |
| **TODO-SRC-ROOT** | **RESOLVED.** `muejeje_pts/` is the owned source root: `script-engine/`, `interface/`, `manifest/`. `EXTENSION/**` stays untouched, keeps serving the existing published `.pts`, and is no longer any part of Muejeje's inventory — the completeness check now sweeps the owned root alone. The legacy `main.js` was not copied. |
| **TODO-V6-SHAPE** | **RESOLVED for the kernel.** The envelope is `{v, operation_rid, op, args}` in and `{v, operation_rid, op, ok, result, error}` out, both as JSON strings, through the single entry point `mcpDispatchV6`. Operations are whitelisted by name with a per-operation argument whitelist, and the failure taxonomy is MJ-022. The whitelist admits `runtime.identify` alone; adding an operation extends the table, not the envelope. |
| **TODO-RECIPE-SCOPE** | **RESOLVED.** Manifest `schema_version: 2` splits inputs into `artifact_inputs` (bytes packaged into the `.pts`, required to live under the owned root), `tooling_inputs` (the auditor — ships nothing, still part of recipe identity) and `reference_inputs` (empty). A path may not appear in two categories. |

## Related documents

- [Operating model](muejeje-runtime-operating-model.md) — governance and boundaries.
- [v2 preflight inventory](../qa/muejeje-pts-v2-preflight-inventory.md) — the
  per-symbol evidence behind MJ-012, MJ-013 and MJ-014.
- [ADR-001](../qa/muejeje-pts-adr-001-branch-realignment.md) and its
  [resolution](../qa/muejeje-pts-adr-001-resolution.md).
