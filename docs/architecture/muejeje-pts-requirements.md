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
What never enters the runtime, the build tooling or the provenance schema is a
consumer's **identifiers** — the project a scenario belongs to, one topology's
device names, a fixed address — and any behaviour that assumes them.

**Generic networking vocabulary is not a consumer identifier.** DHCP, VLAN,
OSPF, PoE, EIGRP, voice and RIPv2 are Packet Tracer's domain, not any one
consumer's. Excluding them would forbid the runtime from ever describing the
platform it adapts to, which is a different requirement from this one and not a
desirable one.
**Rationale.** This is MJ-001 stated as an exclusion, so that a violation is
recognisable rather than arguable. Drawing the line at identifiers rather than
at subject matter is what keeps it recognisable: "does this name a specific
project, device or endpoint" has an answer, where "does this sound
scenario-ish" does not.
**Verification.** `tests/muejeje/test_source_root.py` fails if a project
identifier, a topology device name or a dotted-quad address appears in any
packaged source, and asserts in the same module that generic networking
vocabulary is *not* rejected — both directions, so neither half can invert
unnoticed.
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
**Status.** `ENFORCED` for the envelope and for the two read-only operations,
`runtime.identify` and `runtime.capabilities`; `BASELINED` for every operation
not yet migrated to V6 — consumers still reach the legacy runtime for those.

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
whitelist admits `runtime.capabilities` and `runtime.identify`, both read-only.
**Rationale.** A permissive dispatcher cannot bound what a consumer can cause.
**Verification.** One negative test per rejection class, plus a gate that the
dispatcher holds no operation implementation and the protocol module holds no
whitelist. See MJ-022 for the taxonomy those tests pin. A document that names
an operation the dispatcher does not admit — or omits one it does — fails
`tests/muejeje/test_unobserved_claims.py`.
**Status.** `ENFORCED` — the whitelist admits those two names, and every other
name fails closed.

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
(`build_state.py`), a schema (`manifest.py`), an inventory of the inputs this
repository declares (`inventory.py`), the untracked pinned material it does not
own (`references.py`) and source/hash/recipe identity (`provenance.py`). The
public API is the facade; splitting a module never changes it.
**Rationale.** One 540-line `build.py` held the state machine, the schema, the
path rules and every Git call, so no rule could be read, tested or changed
without loading all of them. Splitting by responsibility is what makes a rule
locatable — and the budget in MJ-020 is what forces the split to happen when a
module grows, rather than being argued about.
**Verification.** `tests/muejeje/test_auditor_layers.py` pins the module set
against the declared layers and fails on an undeclared module; the facade is
asserted to hold no vocabulary of its own; every auditor module must be a
declared tooling input, so no rule can move outside recipe identity.
**Status.** `ENFORCED`

### MJ-019 — Dependency direction is inward and one-way
**Requirement.** In the auditor, `build_state`, `manifest` and `provenance`
depend on no sibling; `inventory` may depend on `build_state` and `provenance`;
`references` may depend on those three; only `build` may depend on all of them.
In the runtime, the direction is `lifecycle → dispatcher/operations → protocol +
core`, and the V6 core depends on none of CP LIVE, WebView, HTTP, the File
Bridge, PTBuilder, legacy `runCode` or arbitrary JavaScript execution. Cisco IPC
access is an adapter concern and stays outside protocol, core and operation
logic.

**The runtime gate is layer-aware.** Core, protocol, dispatch, lifecycle and
operations may never name a transport or the platform. A *declared* adapter
may, because naming the layer it adapts is what an adapter is for. Adapters are
declared by path in the gate itself, both registries are empty today, and
adding one is therefore a visible edit rather than a relaxation of the rule.
**Rationale.** A cycle makes every module the whole system again, which is what
the split was for. Naming the direction is what lets a violation be detected
instead of argued. A blanket ban with no notion of an adapter would have to be
deleted or ignored the first time a transport arrives, and either outcome loses
the core boundary it was protecting.
**Verification.** An import-graph test per auditor module, which resolves every
spelling of an import — relative and absolute — to the sibling it names, so the
rule cannot be satisfied by rephrasing. A layer gate over the owned root for
transport symbols and for `ipc.*`, asserted on synthetic sources to report a
core file and not a declared adapter.
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
dependency direction, the absence of PTBuilder globals and of a consumer's
identifiers, the absence of arbitrary JavaScript execution and of a hard-coded
endpoint, exactly one `main()`, one `cleanUp()` and one `mcpDispatchV6`, the
transport and `ipc.*` boundaries, the agreement between what a document claims
and what the dispatcher admits, and the separation of the test area by
responsibility.

**A gate must be able to fail.** Where a rule distinguishes two cases — a
kernel file from a declared adapter, a consumer's identifier from the
platform's vocabulary, one spelling of an import from another — the gate is
asserted on synthetic inputs in both directions. Otherwise a gate that has
quietly stopped checking anything is indistinguishable from a rule nobody has
broken yet.
**Rationale.** M0E's boundary held because a test failed when it was crossed.
Rules that live only in a document are re-argued at every change.
**Verification.** `tests/muejeje/test_architecture.py`,
`test_auditor_layers.py`, `test_source_root.py` and `test_unobserved_claims.py`;
the retired monolithic test modules are asserted absent so the split cannot
silently reverse.
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
protocol mismatch, a validation failure and an exceeded bound are never
reported as one: nothing went wrong inside the engine when a request was
simply not admissible. Error messages are fixed strings and never echo a
caller-supplied name or value; a message is diagnostic prose, and `code` is
what a consumer branches on (MJ-030). The dispatcher never throws out of the
engine.
**Rationale.** One shape is what makes a consumer's parser total. One code per
cause is what makes a failure diagnosable without reading the runtime's source
— which MJ-005 forbids relying on anyway.
**Verification.** `tests/muejeje/test_protocol_v6.py` drives one case per
rejection class and asserts the shared envelope shape across success and
failure.
**Status.** `ENFORCED`

### MJ-023 — `runtime_session_id` is a correlation token, never authentication
**Requirement.** `runtime_session_id` is a **non-secret correlation token
generated once per engine evaluation**. It exists so two observations can be
attributed to the same evaluation. It grants nothing, proves nothing about who
is calling, and the runtime never compares it against anything.

**Its scope is one evaluation, and a module restart ends that scope.** Cisco's
installed reference says every script file is evaluated *"when the Script
Module starts"*, that *"as long as the Script Module is running, the Script
Engine is running"*, and that an engine change takes effect only once the
module *"has been stopped and started again"*. A stop and a start are therefore
a new evaluation, and a new token. Muejeje claims nothing beyond that, and a
consumer that needs an identity spanning a restart carries its own.

**No global uniqueness is claimed.** The token is a clock reading and a random
draw; the Script Engine guarantees neither, so two evaluations may in principle
produce the same value and nothing in the kernel would detect it. Correlation
is scoped to one observation window, and a consumer needing identity wider than
that carries its own and correlates on both.
**Rationale.** A stable per-evaluation token is exactly the shape people mistake
for a credential. Saying what it is not — in the contract and in the source —
is what stops it from quietly becoming one. Claiming uniqueness would be a
second mistake of the same kind: an unverifiable guarantee that consumers would
build on, and so would claiming a lifetime the platform does not give it.
**Verification.** `tests/muejeje/test_runtime_identify.py` asserts stability
across calls within one evaluation, that exactly one generation site exists and
binds the token once, that regenerating does not rebind the session, and that
no kernel source compares the id. `tests/muejeje/test_unobserved_claims.py`
quotes the three sentences above out of the installed page and fails if any
source or document restates the withdrawn lifetime.

> **Two claims here were wrong and are withdrawn, not restated.**
>
> An earlier revision required the token to be "different between sessions" and
> verified it by comparing two Node processes. Nothing in the kernel guarantees
> that, so the gate was probabilistic: it could fail with nothing wrong, which
> teaches a reader to re-run a red test rather than read it.
>
> A later revision claimed the token was stable *"including across a
> `cleanUp()`/`main()` cycle, because restarting the module is not
> re-evaluating it"*. That is a statement about Packet Tracer, it was verified
> by calling our own `main()` and `cleanUp()` under Node, and Cisco's own
> documentation contradicts it. What the Node run establishes is what this
> module's bookkeeping records when those two functions are called in that
> order — never what Packet Tracer does when a user stops and starts a module
> (MJ-015).

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

### MJ-025 — The Script Module packaging identity is baselined
**Requirement.** The module's packaging identity is decided, and every value is
validated rather than merely present:

| Option | Value | Why this one |
| --- | --- | --- |
| `module_id` | `io.github.andres18113.muejeje.runtime` | hierarchical and reverse-DNS shaped, rooted in a namespace the publisher demonstrably controls, so a second publisher's module cannot collide with this one |
| `startup` | `on_startup` | the module must be able to answer `runtime.identify` without a human opening anything first. It is safe to start unconditionally precisely because it initiates nothing: no transport, no polling, no platform call |
| `custom_interface_order` | `[muejeje_pts/interface/index.html]` | one static page, the only interface file that ships |
| `engine_script_order` | core → protocol → admission → operations (alphabetical) → dispatch → lifecycle | Packet Tracer evaluates in listed order, so the order *is* the dependency direction (MJ-019) |
| `privileges` | `[]` | no operation makes a Cisco IPC call, so the module needs nothing. An empty set is a decision, not an omission |

An option is **unresolved** when it is `null` — nobody has decided, which is not
a defect — and **invalid** when it carries a value the platform could not
accept. Those are different facts and stay different states (MJ-016). The two
file orders must additionally name exactly the declared artifact inputs of
their kind: an order pointing at a file that ships in no artifact describes a
build nobody can perform.
**Rationale.** `TODO-MODULE-ID`, `TODO-STARTUP` and `TODO-PRIVILEGES` blocked a
complete recipe, and a recipe that is never complete has no id, so nothing
downstream can be identified. Deciding them is what makes packaging reachable.
Validating them is what stops a decided-but-unusable value — `startup:
"whenever"` — from earning a recipe id.
**Verification.** `tests/muejeje/test_manifest.py` drives one case per invalid
shape per option and asserts `BUILD_INPUT_INVALID` with no recipe id;
`tests/muejeje/test_build_state.py` asserts that the resolved manifest with the
pinned builder reaches `PACKAGING_MANUAL_AVAILABLE` with a recipe id.
**Status.** `ENFORCED` for the values and their validation; `BASELINED` for
`module_id` acceptance by Packet Tracer itself, which needs target evidence
(MJ-015). If target evidence shows the representation is invalid, the nearest
official-compliant hierarchical form replaces it and the reason is recorded
here.

### MJ-026 — The transport and security contract, before any transport exists
**Requirement.** No transport is implemented. These terms are baselined now so
that the first one cannot be built with them left open:

```text
TOKEN_LOADED != HTTP_TOKEN_VALID
HTTP reachability != authentication
secrets never enter V6, logs or evidence; fingerprints may
no automatic port scanning and no port fallback
kernel and domain stay auth-agnostic and transport-agnostic
HTTP default: 127.0.0.1:18123
```

- **`TOKEN_LOADED != HTTP_TOKEN_VALID`.** That a token was read from disk says
  nothing about whether a peer accepted it. They are separate observations and
  are recorded separately.
- **Reachability is not authentication.** A socket that accepts a connection has
  proved a socket exists. Nothing more may be inferred from it.
- **Secrets never enter V6, logs or evidence.** A fingerprint — a truncated
  digest that identifies *which* secret without carrying it — may, because
  evidence needs to distinguish two tokens without ever holding one.
- **No scanning, no fallback.** A runtime that searches for a port turns a
  configuration error into a silent connection to something else. The default
  is a single loopback endpoint; anything else is configured explicitly.
- **The kernel stays agnostic.** No `mcpDispatchV6` path, operation or envelope
  field is aware of a transport or of authentication. A transport is an adapter
  that carries envelopes; it never changes what an envelope means.
**Rationale.** Every one of these is easier to state before a transport exists
than to retrofit into one. The default endpoint is written here rather than in
the kernel for the same reason: an address in the kernel is a topology
assumption (MJ-002).
**Verification.** `tests/muejeje/test_source_root.py` fails if a packaged source
names a transport symbol or hard-codes a dotted-quad address, and the adapter
registries that would permit one are declared empty. The rest is `BASELINED`
until a transport exists to test.
**Status.** `BASELINED`; the kernel-side exclusions are `ENFORCED`.

### MJ-027 — Batch and scale semantics
**Requirement.** When batch execution exists it will be **bounded batches with
per-item correlation and per-item outcome**. No implicit atomicity, no implicit
rollback, and no ambiguous retry: a batch is not a transaction, and a partially
applied batch reports exactly which items were applied and which were not.
Python owns chunking, checkpoints and backpressure, because Python owns the
evidence and the verdict (MJ-011).

**~360 endpoints is an integration and scale target, never a runtime topology
assumption.** The runtime never sizes itself to it, pre-allocates for it, or
behaves differently above or below it. It is a statement about what an
integration must eventually handle, not a property of the runtime (MJ-002).
**Rationale.** An unbounded batch has no reportable failure mode: it either
finishes or leaves an unknown prefix applied. Implicit atomicity would be a
promise Packet Tracer cannot keep, and a retry over an ambiguous outcome
converts one unknown into an unattributable one (MJ-012).
**Verification.** Nothing yet — no batch operation exists. This is the contract
the first one must satisfy.
**Status.** `BASELINED`

### MJ-028 — `runtime.capabilities` reports only what exists
**Requirement.** `runtime.capabilities` is read-only, makes no platform call,
and reports the runtime session token, the supported protocol versions, each
admitted operation with its `read_only` flag, and the kernel features behind
them. It reports **no roadmap**: a capability that does not exist is absent from
the answer, never listed as planned or pending. It reaches **no verification
verdict** about itself — the engine cannot audit the engine, so Python decides
what an observation establishes (MJ-011).

The whitelist has one owner. Both operations receive it from the dispatcher, so
`runtime.identify`'s operation names and `runtime.capabilities`' operation
descriptors can never describe different contracts.
**Rationale.** A consumer that must discover the contract can only do so from an
answer that is complete and current. A capability list that names future work is
worse than none: it cannot be acted on, and it fails at the moment of use rather
than at the moment of discovery.
**Verification.** `tests/muejeje/test_runtime_capabilities.py` pins the result
shape, asserts the reported whitelist equals the dispatcher's, asserts every
reported feature names a symbol that exists in a kernel source, asserts the
reply mentions no transport, platform or mutation concept, and asserts no
self-certified verdict. `tests/muejeje/test_unobserved_claims.py` fails if a
document names an operation the dispatcher does not admit, or omits one it does.
**Status.** `ENFORCED` for the kernel's own logic under Node;
`NOT_YET_LIVE_VERIFIED` against Packet Tracer `9.0.1.0858` (MJ-015).

### MJ-029 — V6 input is bounded, and every bound is Muejeje's own
**Requirement.** Nothing a caller sends is unbounded. V6 bounds the request
string before parsing it, the correlation id, the operation name, and both the
shape and the values of the arguments:

| Bound | Applies to | Refusal |
| --- | --- | --- |
| request length | the string, measured before `JSON.parse` | `MALFORMED_REQUEST` |
| `operation_rid` | length, and printable ASCII | `INVALID_REQUEST` |
| `op` | length, and `namespace.name` | `INVALID_REQUEST` |
| `args` field count | how many fields the envelope may carry | `INVALID_REQUEST` |
| `args` values | bounded scalars only; no nested object or array | `INVALID_REQUEST` |
| a declared argument's value | the rule the operation states for it | `INVALID_ARGS` |

**No bound is a Packet Tracer limit.** Nothing in this repository has measured
what PT's Script Engine accepts, so a number presented as the platform's would
be a claim about `9.0.1.0858` with no evidence behind it (MJ-015). Each number
is chosen for a reason that holds whatever the platform allows, and the reason
is written at its definition. A consumer that needs more than a bound allows
reopens *that number* with a stated case; it never reopens the principle.

**The taxonomy does not grow.** A bound belongs to the contract it bounds, so
an exceeded bound is reported as `MALFORMED_REQUEST`, `INVALID_REQUEST` or
`INVALID_ARGS` — never as a new code, and never as `ENGINE_EXCEPTION`. Adding a
seventh code would break every consumer that switches on the six (MJ-030).

**A refused name is not an unknown operation.** An `op` that the envelope could
not carry never reached the whitelist, so it is `INVALID_REQUEST`; a well-shaped
name the whitelist does not admit is `UNKNOWN_OPERATION`. Reporting the first as
the second would send a consumer looking for an operation.

**An argument rule the kernel cannot read refuses the argument.** A rule of an
unrecognised kind bounds nothing, so it admits nothing.
**Rationale.** Unbounded input hands the cost of a refusal to whoever sent it:
a caller could make the engine parse any length of JSON, correlate against any
length of id, and walk any depth of argument structure before a single check
ran. Bounding admission is what makes the cost of one request a property of the
runtime. Insisting the numbers are ours is what stops them from being read back
later as platform facts nobody measured.
**Verification.** `tests/muejeje/test_v6_admission.py` drives each bound in
both directions — refused past it, admitted at it — asserts that the limits are
declared in exactly one kernel file, and asserts that no bound is ever reported
as `ENGINE_EXCEPTION`. The per-operation argument rules are driven on a
synthetic operation, so the first operation to declare one inherits a tested
mechanism.
**Status.** `ENFORCED` for the kernel's own logic under Node;
`NOT_YET_LIVE_VERIFIED` against `9.0.1.0858` (MJ-015).

### MJ-030 — Compatible V6 evolution is additive, and everything else is breaking
**Requirement.** V6 is the contract Muejeje owns (MJ-005), so *changing the
runtime* and *breaking a consumer* must be distinguishable events. One rule
decides which happened:

> A result may gain a field. Nothing may lose one, be renamed, or keep its name
> while meaning something else.

**Compatible — no protocol version change:**

| Change | Why a consumer survives it |
| --- | --- |
| a new field in an operation's `result` | a consumer that does not read it cannot see it |
| a new operation name in the whitelist | nobody was sending it |
| a new argument an operation accepts | nobody was supplying it, and omitting it must keep the old behaviour |
| different `error.message` prose | the message is diagnostic; `error.code` is the contract |
| a new kernel feature in `supported_features` | the list is discovered, not enumerated by the consumer |
| a stricter *internal* bound that no admitted request crossed | nothing that was accepted is refused |

**Breaking — needs a new protocol version:**

| Change | What breaks |
| --- | --- |
| removing or renaming any envelope or result field | a field access |
| changing a field's type or meaning under the same name | a reader that still parses, and is now wrong |
| adding or removing an `error.code` | an exhaustive reader of the taxonomy |
| adding a required request field | every existing caller, at once |
| making an operation published as `read_only` mutate | the decision a consumer made from that flag |
| narrowing what an existing request may carry | callers that were within the old bound |

`error.message` is deliberately outside the contract: a fixed diagnostic string
that never echoes caller input (MJ-022), free to improve.

**A new protocol version is a new number, never a reinterpretation.** V6 has no
compatibility escape and never guesses at a neighbouring version's meaning
(MJ-008); a V7 would be admitted as V7 or refused as `PROTOCOL_MISMATCH`.
**Rationale.** Without this rule, every edit to a result is a negotiation, and
the safe answer becomes "change nothing" — which is how a contract stops being
usable. Writing down what is additive is what makes the runtime free to grow;
writing down what is breaking is what stops that freedom from being read as
permission to reshape a published answer.
**Verification.** `tests/muejeje/test_v6_compatibility.py` asserts the envelope
and the error taxonomy **equal** to what the kernel declares, and each
operation's published result fields as a **subset** of what it answers — so an
added field passes and a removed or renamed one fails. It asserts that measure
in both directions on synthetic field sets, that every admitted operation
declares a frozen result shape, that a read-only operation stays read-only, and
that this rule is stated here.
**Status.** `ENFORCED` for the kernel's own logic under Node;
`NOT_YET_LIVE_VERIFIED` against `9.0.1.0858` (MJ-015).

## Open decisions

Not requirements. Each needs a decision before it can become one.

| TODO | Question | Blocks |
| --- | --- | --- |
| **TODO-MANIFEST-HOME** | The manifest now lives at `muejeje_pts/manifest/`. Its path is pinned in `infrastructure/pts/manifest.py`; if the owned root is ever renamed, that pin moves with it. | — |
| **TODO-SIGNING** | Publisher signing (PKCS#12) and key custody. | reproducibility |

### Resolved

| TODO | Resolution |
| --- | --- |
| **TODO-SRC-ROOT** | **RESOLVED.** `muejeje_pts/` is the owned source root: `script-engine/`, `interface/`, `manifest/`. `EXTENSION/**` stays untouched, keeps serving the existing published `.pts`, and is no longer any part of Muejeje's inventory — the completeness check now sweeps the owned root alone. The legacy `main.js` was not copied. |
| **TODO-V6-SHAPE** | **RESOLVED for the kernel.** The envelope is `{v, operation_rid, op, args}` in and `{v, operation_rid, op, ok, result, error}` out, both as JSON strings, through the single entry point `mcpDispatchV6`. Operations are whitelisted by name, each admitted argument carries the rule its value must satisfy (MJ-029), and the failure taxonomy is MJ-022. Adding an operation extends the table, not the envelope; which operations the table holds is MJ-008, and it is not restated here, because a whitelist written down twice is one that will disagree with itself. |
| **TODO-MODULE-ID** | **RESOLVED** by `MJ-025`: `io.github.andres18113.muejeje.runtime`. Hierarchical and reverse-DNS shaped, rooted in a namespace the publisher controls. Stability across rebuilds is a property of the manifest, which is committed and hashed into recipe identity. Packet Tracer's own acceptance of the representation still needs target evidence (`MJ-015`). |
| **TODO-STARTUP** | **RESOLVED** by `MJ-025`: `on_startup`. The module must answer `runtime.identify` without a human opening anything, and starting it unconditionally is safe precisely because it initiates nothing — no transport, no polling, no platform call. Revisit if and when a channel that *does* initiate is added. |
| **TODO-PRIVILEGES** | **RESOLVED** by `MJ-025`: `[]`. No operation makes a Cisco IPC call, so the module requests nothing. The `.pki` privilege catalogue is still not installed, and this resolution deliberately does not need it: an empty set requires no catalogue to justify. The first operation that needs the platform reopens this with evidence for the one privilege it needs. |
| **TODO-RECIPE-SCOPE** | **RESOLVED.** Manifest `schema_version: 2` splits inputs into `artifact_inputs` (bytes packaged into the `.pts`, required to live under the owned root), `tooling_inputs` (the auditor — ships nothing, still part of recipe identity) and `reference_inputs` (empty). A path may not appear in two categories. |

## Related documents

- [Operating model](muejeje-runtime-operating-model.md) — governance and boundaries.
- [Packaging recipe](../qa/muejeje-pts-packaging-recipe.md) — the complete
  Scripting Interface procedure, its preconditions and what a run must record.
- [v2 preflight inventory](../qa/muejeje-pts-v2-preflight-inventory.md) — the
  per-symbol evidence behind MJ-012, MJ-013 and MJ-014.
- [ADR-001](../qa/muejeje-pts-adr-001-branch-realignment.md) and its
  [resolution](../qa/muejeje-pts-adr-001-resolution.md).
