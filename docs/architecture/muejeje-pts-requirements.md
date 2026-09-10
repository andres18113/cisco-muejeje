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
**Status.** `ENFORCED` for the envelope and for every operation the
dispatcher admits, all of them read-only; the complete list is the catalogue in
`muejeje_pts/README.md` (MJ-008). `BASELINED` for every operation not yet
migrated to V6 — consumers still reach the legacy runtime for those.

### MJ-006 — Packet Tracer and its IpcAPI are the platform boundary
**Requirement.** The southbound compatibility contract is Packet Tracer and its
IpcAPI. Muejeje adapts to it; it does not extend or reinterpret it.
**Rationale.** The platform is the one thing Muejeje cannot change. Naming it as
the boundary keeps compatibility work in one place.
**Verification.** All platform access in the owned artifact goes through one
declared call boundary, which admits only names present in Cisco's installed
IpcAPI reference. A gate fails if any other packaged source names `ipc` or
names a platform member at a call site; another compares the calls actually
made, at runtime, against the documented set (MJ-031).
**Status.** `ENFORCED` for the owned artifact's own platform access, which is
one read-only boundary over documented getters; `BASELINED (deviation)` for the
legacy runtime consumers still use, where six PTBuilder globals sit between
Muejeje and the IpcAPI (MJ-013).

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
whitelist, and fail closed on version, schema or correlation mismatch. Every
admitted operation is read-only today.

**The whitelist is declared once and enumerated once.** It lives in
`dispatcher_v6.js`, which is the only thing that decides what may be sent, and
it is written out for a reader in exactly one document — the artifact's own
`muejeje_pts/README.md`, the authoritative catalogue, which a gate holds
complete. Every other document names whichever operations it has a reason to
name. Requiring all of them to enumerate all of it made the whitelist five
copies that one new operation could put out of step, and pushed each document
toward a list it had no reason to carry; what is checked instead is that no
document claims a capability this artifact does not have, and that any count it
writes — "three read-only operations" is a completeness claim in fewer words —
matches what the dispatcher admits, or what the namespace it names admits.
**Rationale.** A permissive dispatcher cannot bound what a consumer can cause.
A catalogue nobody can find is the same problem for a consumer, and five
catalogues are worse than one: they disagree, and the reader cannot tell which
is current.
**Verification.** One negative test per rejection class, plus a gate that the
dispatcher holds no operation implementation and the protocol module holds no
whitelist. See MJ-022 for the taxonomy those tests pin.
`tests/muejeje/test_capability_claims.py` holds the catalogue complete against
the dispatcher, fails on any document that names an operation or feature this
artifact does not have, and fails on a miscounted claim in any of them.
**Status.** `ENFORCED` — a name the whitelist does not hold fails closed, and
an operation name outside a declared namespace fails the claim gates rather
than passing unnoticed.

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
`tests/muejeje/test_inventory.py`, and `tests/muejeje/test_layer_boundaries.py`,
which fails if any of the six globals is *reached as a global* in the owned
sources.

**A global and a member of the same name are different dependencies.** Four of
the six names are also members of documented Cisco interfaces:
`ipc.network().addDevice(...)` is the platform's API, while a bare
`addDevice(...)` is PTBuilder's. The gate matches an identifier that is not
preceded by a dot, so it keeps the global out and leaves the official member
available to a declared adapter. A substring rule could not separate them, and
would therefore have to be deleted the first time an adapter needed the
official call — taking this boundary with it. A declared adapter is *not*
exempt from this one: a bare global is PTBuilder's whichever file names it.
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
marked as a mirror at its definition. In the owned artifact,
`platform.device_descriptors` reads `DeviceType` and the supported `ModuleType`
values back out of the descriptor API and reports them untranslated, and a gate
fails if any Cisco enum name appears in the packaged sources at all (MJ-031).
**Status.** `ENFORCED` for the owned artifact, which carries no mirror and
enumerates the factory without one — its enumeration takes no `DeviceType`
argument, so no table has to exist for it to work;
`NOT_YET_LIVE_VERIFIED` against `9.0.1.0858` (MJ-015).
`BASELINED (deviation)` for the legacy runtime — `PT_DEVICE_TYPE` (33 entries),
`PT_CONNECT_TYPE` (16) and `ModuleSpec.module_type` (151) are mirrors still in
use there, and `allModuleTypes` is still PTBuilder's table.

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
In the runtime, the direction is `lifecycle → dispatcher → operations →
adapter → protocol + core`, and the V6 core depends on none of CP LIVE,
WebView, HTTP, the File Bridge, PTBuilder, legacy `runCode` or arbitrary
JavaScript execution. Cisco IPC access is an adapter concern and stays outside
protocol, core, dispatch and operation logic: an operation calls the adapter,
and the adapter reads no kernel state, shapes no envelope and dispatches
nothing.

**The runtime gate is layer-aware.** Core, protocol, admission, dispatch,
lifecycle and operations may never name a transport or the platform. A
*declared* adapter may, because naming the layer it adapts is what an adapter
is for. Adapters are declared by path in the gate itself, so adding one is a
visible edit rather than a relaxation of the rule.

**A declaration is checked, not trusted.** An exemption that could be pointed
at any file would be a switch for turning the layer gates off, so a declared
adapter must be named `*_adapter.js`, must be a declared artifact input, must
exist, and must hold no dispatch, no envelope and no read of core — it adapts,
it does not answer. The platform gate also matches `ipc` as an identifier
rather than as the prefix `ipc.`, because an alias (`var p = ipc;`) is a
rename, not a boundary.
**Rationale.** A cycle makes every module the whole system again, which is what
the split was for. Naming the direction is what lets a violation be detected
instead of argued. A blanket ban with no notion of an adapter would have to be
deleted or ignored the first time a transport arrives, and either outcome loses
the core boundary it was protecting.
**Verification.** An import-graph test per auditor module, which resolves every
spelling of an import — relative and absolute — to the sibling it names, so the
rule cannot be satisfied by rephrasing. `tests/muejeje/test_layer_boundaries.py`
gates the owned root for transport symbols and for `ipc`, asserted on synthetic
sources to report a core file and not a declared adapter, and checks every
adapter declaration against the rules above.
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
kernel file from a declared adapter, a PTBuilder global from a documented
member of the same name, a consumer's identifier from the platform's
vocabulary, one spelling of an import from another, an operation from a kernel
feature, a text asset from an image — the gate is asserted on synthetic inputs
in both directions. Otherwise a gate that has quietly stopped checking
anything is indistinguishable from a rule nobody has broken yet.

**A gate must also survive the runtime growing.** A rule that would have to be
deleted the first time an adapter, a second operation namespace or a packaged
image arrived is a delay, not a rule. So the operation namespaces are declared
rather than hard-coded into a pattern, the layer gates name their adapters, and
every gate that reads prose reads only the assets whose bytes are text — an
earlier revision decoded the whole packaged inventory, `.png` included, so the
first packaged image would have replaced each of those verdicts with a
`UnicodeDecodeError`.
**Rationale.** M0E's boundary held because a test failed when it was crossed.
Rules that live only in a document are re-argued at every change.
**Verification.** `tests/muejeje/test_architecture.py`,
`test_auditor_layers.py`, `test_source_root.py`, `test_layer_boundaries.py`,
`test_capability_claims.py` and `test_unobserved_claims.py`;
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
simply not admissible. It reads in the other direction too — a defect inside
this artifact is *always* this code, and never a platform observation, which is
the attribution rule MJ-031 states. Error messages are fixed strings and never echo a
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
| `privileges` | `[]` | nothing this module calls has an *evidenced* privilege requirement, and an invented name would be denied on the target rather than refused here (`MJ-032`). An empty set is a decision, not an omission |

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
**Verification.** `tests/muejeje/test_layer_boundaries.py` fails if a packaged
source names a transport symbol, `tests/muejeje/test_source_root.py` fails on a
hard-coded dotted-quad address, and the transport adapter registry that would
permit one is asserted empty. The rest is `BASELINED`
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

**It stays platform-free even now that a platform capability exists.** The
operation being admitted, and the kernel feature behind it, are facts about
this artifact and are reported. Whether Packet Tracer answers is not, and is
never folded in: discovery that depended on a platform call would turn one
unavailable platform into "this runtime has no capabilities". What the platform
said is what `platform.device_descriptors` reports, when a consumer asks
(MJ-031).

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
reply promises nothing the kernel cannot do, and asserts no self-certified
verdict. `tests/muejeje/test_capability_claims.py` fails if the authoritative
catalogue omits an admitted operation, if any document names a capability — an
operation *or* a kernel feature — that this artifact does not have, or if a
document writes a count of operations that is not the number there are
(MJ-008). Operations and features share a shape, so
they are separated by the sets they belong to and the two sets must stay
disjoint: a name that is both would make "is this admitted" and "does this
exist" the same question.
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

### MJ-031 — Platform access is one read-only, cited call boundary
**Requirement.** Muejeje reaches Packet Tracer through **one boundary**: a
single packaged file names `ipc`, and a single function in it makes every
platform call this artifact makes, by member name, admitting only names on a
declared read-only allowlist. The adapters that read a subject — device
descriptors, chassis modules — are declared adapters beside it and call the
platform only through that function; they name no platform object of their own.
Core, protocol, admission, dispatch, lifecycle and every operation stay
platform-agnostic: an operation calls an adapter, and an adapter reads no
kernel state, shapes no envelope and dispatches nothing (MJ-019).

**Four rules bound what may cross it.**

1. **Documented or evidenced only.** Every name on the allowlist is named in
   Cisco's installed IpcAPI reference for the pinned build, or is already
   evidenced against it. A guess earns a bare `Invalid arguments for IPC call
   "X"` that says nothing about why (`AGENTS.md` rule 6).
2. **No mutation, proved positively.** The allowlist is the proof: it holds
   only documented getters, and an adapter names no platform member at a call
   site, so a call outside the list cannot be written — it is refused by the
   boundary before a receiver is touched. A blacklist of mutating verbs is kept
   as a second, cheaper line of defence over the allowlist itself, and is
   deliberately not the first: a forbidden-verb list admits every name nobody
   thought of, and once the member name is data it cannot see the call at all.
3. **No numeric Cisco enum as authority.** The values reported come back out of
   the platform and are never matched against a table of ours. Two gates, one
   per spelling: no Cisco enum *identifier* appears in any packaged source, and
   the only numeric literals an adapter carries are Muejeje's own declared
   bounds. An official API is **not** banned by name — `getDescriptor` is
   Cisco's, and forbidding the word would forbid the reference while leaving a
   hand-written table of type numbers legal. What is forbidden is the mirror,
   which is why the enumeration in use takes no `DeviceType` argument.
4. **No consumer or topology assumption.** It reads the *factory*, which
   describes what models exist and what hardware each model can accept. It
   never reads a workspace, a device instance, a link or an address (MJ-002,
   MJ-004).

**An unreadable platform is an observation, not a failure.** No V6 error is
reported for it: the request was admissible, and the answer is that no reading
was obtained. Three reasons stay distinct, because a consumer acts differently
on each — `PLATFORM_ABSENT` (there is no platform object here),
`PLATFORM_CALL_FAILED` (it was asked and the call did not return) and
`PLATFORM_ANSWER_UNUSABLE` (it answered, and the answer could not be
attributed). **A denied privilege is one cause of the second, and the adapter
does not claim to know which cause it was.**

**Whose failure was it is part of the contract.** Exactly two things become an
unavailable reading: a call made at the boundary, and an answer a declared
validator refused. Anything else thrown inside an adapter is a defect in *this
artifact*, and it is left to reach the dispatcher as `ENGINE_EXCEPTION`
(MJ-022). Reporting it as `PLATFORM_CALL_FAILED` would manufacture an
observation about Packet Tracer that Packet Tracer never produced — and on a
target, where that reading is exactly what a missing privilege looks like, a
consumer could not tell the two apart.

**A capability with no evidenced privilege stays pending.** This module
requests no privilege (MJ-025, MJ-032), so on a target these calls are denied
until one is evidenced. That is reported as an unavailable reading with its
reason — never as a claim about what Packet Tracer does or does not offer, and
never as a reason to guess a privilege name.

**`runtime.capabilities` may name a capability only once it exists.** The
operation being admitted, and the kernel feature behind it, are facts about
this artifact and are reported. Whether the platform answers is not, and is
never folded into the capability report: discovery that depended on a platform
call would turn one unavailable platform into "this runtime has no
capabilities" (MJ-028).
**Rationale.** MJ-003 asks for behaviour selected from observed capabilities
rather than from assumptions, and nothing could observe one until something
could ask. Bounding that reach to one cited, read-only call boundary is what
keeps the answer to "what does this artifact do to Packet Tracer" short enough
to check: it is a list, not a reading of every call site.
**Verification.** Four modules, one per responsibility.
`tests/muejeje/test_platform_adapter.py` asserts that one file names `ipc`,
that only declared adapters reach the boundary, that no adapter names a
platform member at a call site, that the allowlist equals the documented set,
that no admitted name is shaped like a mutation, and that an adapter carries no
number but its own bounds — then compares the calls actually made, recorded by
a stub, against the documented set, in both directions, and drives the boundary
refusing a name outside the allowlist without touching the receiver.
`tests/muejeje/test_platform_readings.py` drives every reading, every field
validator behind them, and that a defect inside an adapter reaches the caller
as `ENGINE_EXCEPTION` rather than as a platform reading.
`tests/muejeje/test_platform_descriptors.py` covers the operations: one result
shape whether the platform answered or not, the window and its truncation
marks, the declared argument rules, and no self-certified verdict.
`tests/muejeje/test_source_root.py` gates the enum identifiers, and
`tests/muejeje/test_layer_boundaries.py` checks the declarations themselves.
**Status.** `ENFORCED` for the boundary, the read-only rule, the failure
attribution and the adapters' own logic under Node; `PENDING_TARGET` for the
capabilities themselves. The `OBSERVED` branch has only ever been driven
against a stub, no `.pts` has been built from these sources, and nothing here
has reached `9.0.1.0858` (MJ-015).

### MJ-032 — A declared privilege must be a privilege Cisco names
**Requirement.** `build_options.privileges` may be empty, or may hold only
privilege identifiers this repository has evidence for. An empty list needs no
evidence: asking for nothing cannot ask for the wrong thing (MJ-025).

**Why a wrong name is worse than a missing one.** Cisco is explicit that *"the
security privileges indicate which IPC calls this Script Module can make. Calls
to unselected privileges will be denied"*. A misspelled or invented privilege
therefore passes packaging, ships inside the artifact, and fails on the target
as a denied IPC call — in the one place this repository cannot observe. The
audit is the last point at which the name can still be refused.

**The evidenced set is a measurement, not a catalogue.** Privileges are declared
in `.pki` files, which are **not installed**. The installed IpcAPI reference
leaks three identifiers through its event declarations —
`PrivActivityWizard`, `PrivApplication` and `PrivGetNetwork` — and those are the
three this repository can point at. A name absent from that set is *unevidenced
here*; it is never asserted to be nonexistent, and the set grows only from
evidence. Sweeping the whole installed reference in both directions is what
keeps it a measurement: a future build that generates more of the declarations
into HTML fails the gate rather than being missed.

**Which privilege a given IPC call requires is a separate unknown.** It is
recorded as open in the v2 preflight inventory, and MJ-031 is the case that
depends on it: the read-only descriptor capability ships with its code in place
and its target resolution pending, because the honest answer to "which
privilege does this need" is that nobody here knows yet.
**Rationale.** This is `AGENTS.md` rule 6 — never guess a PT API signature —
applied to the one field whose wrong value is invisible until the target runs.
The shape rules run before the evidence rule, so a typo is still reported as a
typo rather than sending a reader to look for a privilege catalogue.
**Verification.** `tests/muejeje/test_privileges.py` drives the rule in every
direction: empty accepted, every evidenced name accepted, an unevidenced name
refused and named while the evidenced ones are not, and the shape rules
reported first. It records the page and page hash each identifier was read from
and re-derives both directions against the installed reference when the target
build is present. `tests/muejeje/test_manifest.py` asserts `BUILD_INPUT_INVALID`
with no recipe id for an unevidenced entry.
**Status.** `ENFORCED` for the rule and its evidence; `BASELINED` for the
representation Packet Tracer accepts in a saved module, which needs target
evidence (MJ-015) exactly as `module_id` does.

### MJ-030 — Compatible V6 evolution is additive, and everything else is breaking
**Requirement.** V6 is the contract Muejeje owns (MJ-005), so *changing the
runtime* and *breaking a consumer* must be distinguishable events. One rule
decides which happened:

> A result may gain a field. Nothing may lose one, be renamed, or keep its name
> while meaning something else.

**The rule reaches every level of a published answer.** A consumer reads
`descriptors[0].model` exactly as it reads `available_count`, so a rename
inside a nested object breaks a reader in the same way — and a gate that reads
only top-level names cannot see it. That was measured, not supposed: renaming
`descriptors[].model_supported` passed the whole compatibility gate before it
walked results. So nested shapes are frozen by the path that reaches them, and
the *set of paths* is held equal rather than as a subset: a published nested
object nobody froze is one nothing is holding still.

**Compatible — no protocol version change:**

| Change | Why a consumer survives it |
| --- | --- |
| a new field in an operation's `result`, at any level | a consumer that does not read it cannot see it |
| a new operation name in the whitelist | nobody was sending it |
| a new argument an operation accepts | nobody was supplying it, and omitting it must keep the old behaviour |
| different `error.message` prose | the message is diagnostic; `error.code` is the contract |
| a new kernel feature in `supported_features` | the list is discovered, not enumerated by the consumer |
| a stricter *internal* bound that no admitted request crossed | nothing that was accepted is refused |

**Breaking — needs a new protocol version:**

| Change | What breaks |
| --- | --- |
| removing or renaming any envelope or result field, nested ones included | a field access |
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
**Verification.** Two modules, one per half.
`tests/muejeje/test_v6_compatibility.py` asserts the envelope and the error
taxonomy **equal** to what the kernel declares, that every admitted operation
answers in that envelope, that a read-only operation stays read-only, and that
this rule is stated here. `tests/muejeje/test_v6_result_shapes.py` asserts each
operation's published result fields as a **subset** of what it answers — so an
added field passes and a removed or renamed one fails — walks every nested
object a result publishes and holds the set of those paths equal, drives a
platform operation against a stub so an empty list cannot hide a shape, and
asserts both measures in both directions on synthetic results.
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
| **TODO-PRIVILEGES** | **RESOLVED** by `MJ-025` and `MJ-032`: `[]`. The `.pki` privilege catalogue is still not installed, and this resolution deliberately does not need it: an empty set requires no catalogue to justify. What a non-empty set would require is now decided rather than left open — only identifiers Cisco names, refused at audit time otherwise (`MJ-032`) — because an invented privilege is denied on the target where nothing here can see it. A capability whose privilege cannot be evidenced stays unsupported (`MJ-031`). |
| **TODO-RECIPE-SCOPE** | **RESOLVED.** Manifest `schema_version: 2` splits inputs into `artifact_inputs` (bytes packaged into the `.pts`, required to live under the owned root), `tooling_inputs` (the auditor — ships nothing, still part of recipe identity) and `reference_inputs` (empty). A path may not appear in two categories. |

## Related documents

- [Operating model](muejeje-runtime-operating-model.md) — governance and boundaries.
- [Packaging recipe](../qa/muejeje-pts-packaging-recipe.md) — the complete
  Scripting Interface procedure, its preconditions and what a run must record.
- [v2 preflight inventory](../qa/muejeje-pts-v2-preflight-inventory.md) — the
  per-symbol evidence behind MJ-012, MJ-013 and MJ-014.
- [ADR-001](../qa/muejeje-pts-adr-001-branch-realignment.md) and its
  [resolution](../qa/muejeje-pts-adr-001-resolution.md).
