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
**Reading what is there is not assuming what is there.** `network.device_inventory`
reports the devices a workspace currently holds; it expects no count, no naming
scheme, no role and no ordering that outlives the reading, and the same code
answers an empty workspace and a full one. A runtime that could not look at a
workspace at all could never serve a consumer that has one; a runtime that
*expects* a particular one has become part of that consumer.
**Rationale.** Topology is the consumer's domain. A runtime that knows a topology
has silently become part of that consumer.
**Verification.** Review; absence of topology fixtures in the runtime and in the
build inputs; `tests/muejeje/test_network_inventory.py` drives the inventory
against an empty workspace, a single device, an unnamed one and four unrelated
names, so "assumes nothing" is exercised rather than asserted.
**Status.** `ENFORCED` for the one workspace reading that exists; `BASELINED`
for everything not yet built.

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
dispatcher admits, each of them read-only; the complete list is the catalogue
in `muejeje_pts/README.md` (MJ-008). `BASELINED` for every operation not yet
migrated to V6 — consumers still reach the legacy runtime for those.

### MJ-006 — Packet Tracer and its IpcAPI are the platform boundary
**Requirement.** The southbound compatibility contract is Packet Tracer and its
IpcAPI. Muejeje adapts to it; it does not extend or reinterpret it.
**Rationale.** The platform is the one thing Muejeje cannot change. Naming it as
the boundary keeps compatibility work in one place.
**Both subjects are the platform.** The factory and the workspace are reached
through the same call boundary and the same allowlist, so "what does this
artifact do to Packet Tracer" stays one list — and that list is what keeps the
workspace read-only, since the same `Network` interface offers members that
create a device or a link and none of them is on it.
**Verification.** All platform access in the owned artifact goes through one
declared call boundary, which admits only interface members documented on
their own interface's page of Cisco's installed IpcAPI reference, or already
evidenced against the pinned build. A gate fails if any other packaged source
names `ipc` or names a platform member at a call site; another compares the
calls actually made, at runtime and per interface, against the documented set
(MJ-031).
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
`tests/muejeje/test_protocol_v6.py` fails if the one in `210_dispatcher_v6.js`
disappears.
**Status.** `ENFORCED` — one dispatcher, in `210_dispatcher_v6.js`.

### MJ-008 — V6 is typed, declarative, whitelisted and fail-closed
**Requirement.** V6 operations are typed and declarative, admitted by an explicit
whitelist, and fail closed on version, schema or correlation mismatch. Every
admitted operation is read-only today.

**The whitelist is declared once and enumerated once.** It lives in
`210_dispatcher_v6.js`, which is the only thing that decides what may be sent, and
it is written out for a reader in exactly one document — the artifact's own
`muejeje_pts/README.md`, the authoritative catalogue, which a gate holds
complete. Every other document names whichever operations it has a reason to
name. Requiring all of them to enumerate all of it made the whitelist five
copies that one new operation could put out of step, and pushed each document
toward a list it had no reason to carry; what is checked instead is that no
document claims a capability this artifact does not have, and that any count it
writes matches what the dispatcher admits, or what the namespace it names
admits: a sentence that counts the read-only operations is a completeness claim
in fewer words, and it goes stale exactly as a list does.
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
> now has behaviour — the kernel and `runtime.identify` — and a governed
> artifact built from it has run in Packet Tracer and answered. What it has not
> done is serve a consumer: the runtime consumers actually use is still the
> legacy one, and every platform call the governed artifact made was denied.
> Independence is proven when a built artifact reaches the platform and
> demonstrates it, not before.

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

**The owned artifact now walks the descriptor column of that table**, in
`110_platform_module_adapter.js`: `getRootModule()` and the `ModuleDescriptor`
getters beside it, reached from a descriptor the factory enumeration handed
back rather than from `getDescriptor(DeviceType, model)`. Asking by type would
need a table of type numbers to ask with, which is what this requirement
forbids; asking by index needs nothing. **Those legacy runs are not this
artifact's evidence** (MJ-015): they were driven from another channel with its
own privileges, so they establish that the getters answer on this build, and
nothing about whether a Script Module carrying `privileges: []` may call them.

**Verification.** Enum values reconciled against the descriptor API; each mirror
marked as a mirror at its definition. In the owned artifact,
`platform.device_descriptors` reads `DeviceType` and the supported `ModuleType`
values back out of the descriptor API and reports them untranslated. Two gates,
one per spelling a mirror can take: `tests/muejeje/test_source_root.py` fails if
a Cisco enum *identifier* appears in any packaged source, and
`tests/muejeje/test_platform_adapter.py` fails if an adapter carries any numeric
literal but its own declared bounds. Cisco's own API names are deliberately not
on either list — `getDescriptor` is one, and forbidding the word would forbid
the reference while leaving a hand-written table of type numbers legal
(MJ-031).
**Status.** `ENFORCED` for the owned artifact, which carries no mirror and
both enumerates the factory and walks a model's chassis without one — the
enumeration takes no `DeviceType` argument and a model is addressed by its
index in it, so no table has to exist for either to work;
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

**The entry point never throws, and that is enforced rather than assumed.**
Admission, the whitelist lookup, the argument rules and the encoder are ordinary
code that can fail the way ordinary code does, so the whole of dispatch runs
behind one boundary and any unexpected failure inside it becomes an
`ENGINE_EXCEPTION` envelope. The last-resort answer is a fixed string, because
the encoder is one of the things that may have broken; it is the only hard-coded
envelope in the artifact, and a gate holds it equal to what the kernel would
have shaped.

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
| `engine_script_order` | core → protocol → admission → platform reading → boundary and adapters → operations (alphabetical) → dispatch → lifecycle, `010_core.js` to `220_lifecycle.js` | Packet Tracer evaluates in listed order, so the order *is* the dependency direction (MJ-019); it lists engine files by name, so every name carries its place as a unique three-digit prefix |
| `privileges` | `["GET_NETWORK_INFO"]` | the minimum evidenced set. The pinned `PacketTracer.exe` requires privilege index 1 for `IPC.hardwareFactory()` and `IPC.network()` — the two root calls of the whole read-only surface — and index 1 serializes as `GET_NETWORK_INFO`. Nothing else is declared: a token no call this module makes is evidenced to require is refused at audit time, whatever its name suggests (`MJ-032`). An artifact carrying `[]` was observed on `9.0.1.0858` to be denied both calls; whether this set lifts that is `GET_NETWORK_INFO_LIVE_VERIFIED`, still `PENDING` |

An option is **unresolved** when it is `null` — nobody has decided, which is not
a defect — and **invalid** when it carries a value the platform could not
accept. Those are different facts and stay different states (MJ-016). The two
file orders must additionally name exactly the declared artifact inputs of
their kind: an order pointing at a file that ships in no artifact describes a
build nobody can perform.

**The engine order must be the order its file names sort in.** On `9.0.1.0858`
the Scripting Interface lists engine files by name whatever order they were
imported in, and no control to reorder them was observed (an exploratory run at
`ed3a0b0`, recorded in the packaging recipe), so a module evaluates in name
order. A declared order the names do not spell is therefore one no module can
be evaluated in, and it is invalid input: no recipe id, and never
`PACKAGING_MANUAL_AVAILABLE`. Every name carries a three-digit prefix, in steps
of ten, and no two share one — how Packet Tracer collates the rest of a name
was never measured, so the prefix alone decides.
**Rationale.** `TODO-MODULE-ID`, `TODO-STARTUP` and `TODO-PRIVILEGES` blocked a
complete recipe, and a recipe that is never complete has no id, so nothing
downstream can be identified. Deciding them is what makes packaging reachable.
Validating them is what stops a decided-but-unusable value — `startup:
"whenever"` — from earning a recipe id.
**Verification.** `tests/muejeje/test_manifest.py` drives one case per invalid
shape per option and asserts `BUILD_INPUT_INVALID` with no recipe id;
`tests/muejeje/test_build_state.py` asserts that the resolved manifest with the
pinned builder reaches `PACKAGING_MANUAL_AVAILABLE` with a recipe id, and that
the same checkout with two engine files swapped does not. `test_manifest.py`
also drives an engine order out of name order, a name with no prefix and two
names sharing one; `tests/muejeje/test_kernel_layout.py` holds the real names to
the declared order, and the Node harness to the manifest where no name agrees.
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
| a required argument's absence | the operation declares it required | `INVALID_ARGS` |

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

**Relay closure: a bound may not refuse what this runtime published.**

> Any value or identifier Muejeje publishes as reusable input must be
> admissible by every operation that claims to consume it.

Some values a reading reports exist *to be sent back*: a factory index that
addresses a model, a workspace index that addresses a device, a `ModuleType`
that asks whether a model accepts it. For those, a producer's domain and a
consumer's domain are not two decisions. A value this runtime emits and then
refuses is a contract that contradicts itself, and the consumer cannot discover
it by reading either operation — it did nothing but relay an answer this
artifact produced.

So a relayed value has **one** declared domain, named by the reading that
publishes it and by every rule that admits it, and a consuming rule may never
narrow it. An index a reading exposes is also *reported*, not inferred: a
consumer that has to count `offset + i` to learn what to send back is deriving a
reusable input, and two consumers will derive it differently.

**Three things limit a request, and they are kept apart:**

| Limit | Owner | Decides | Bounded by |
| --- | --- | --- | --- |
| work per request | Muejeje | how much one call does | the window, the walk and the string length — each reported as truncation when reached |
| numeric fidelity | Muejeje | which numbers travel and come back unchanged | the exact-integer range, `±(2^53 − 1)`: indexes and counts take its non-negative half, platform values both halves |
| capacity | Packet Tracer | how many models, devices or ports exist | nothing here: the platform's own count, read in the same observation |

**An address is bounded by fidelity, never by a ceiling.** Reading position
three trillion costs what reading position three costs, so an index ceiling
bounds no work; it only decides which of the platform's own positions this
runtime refuses to look at. An earlier revision capped every index at 4096 and
refused any count above 65536, which made a large enough workspace unreadable
rather than paged, and it then had to report the ceiling beside the count so a
consumer could find where addressing stopped. All three are withdrawn. An index
below `available_count` is always addressable, so the count is the whole
answer; the window alone bounds what one request does; and a consumer reaches
any position, in a topology of any size, one bounded window at a time. A count
or a value outside the exact-integer range is `PLATFORM_ANSWER_UNUSABLE` — it
could not be carried back unchanged — and never a verdict about its size.

**Closure is not the absence of bounds.** Execution stays bounded, and every
bound stays Muejeje's own. What closure forbids is an incompatible *pair* of
domains, and dressing a value domain up as a resource bound: a ceiling on a
`ModuleType` bounded no work at all, since the cost of a request does not depend
on a type's magnitude, and only decided which platform-produced values this
runtime would accept back — which is not a decision this runtime is entitled to
make (MJ-014). An index ceiling was the same mistake, made about addresses.

**An argument is required only where no default would be honest.** A window
has honest defaults — its start is the origin of its enumeration and its size is
the widest this runtime reads — because a first window over an enumeration *is*
the question a consumer who knows nothing yet is asking. But where every value
in a space is a *different question*, defaulting answers a question the caller
did not ask and reports the answer as an observation, which is the failure this
contract exists to prevent. `module_type` was the first such argument. The index
that selects the one model or device a reading is about is another —
`factory_index`, `workspace_index` — and an earlier revision defaulted each to
0, reporting whatever occupied that position as the answer. Every operation
about one subject now requires it. Its absence is `INVALID_ARGS` — the code that
already means "a whitelisted operation given arguments it does not support" —
and never a reading, because nothing was read.

**An address names its domain.** A position in the hardware factory and a
position on the workspace are numbers of the same shape in two enumerations of
two subjects, so every argument and field that carries one says which:
`factory_index` and `factory_offset`, `workspace_index` and `workspace_offset`.
One name for both — `device_index`, `offset` — let a workspace position relayed
by the name it was published under be admitted as a factory position, with
nothing to refuse it. A value relayed by its own name now reaches only its own
domain, and the other domain refuses it as `INVALID_ARGS`.
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
mechanism. `tests/muejeje/test_relay_closure.py` drives closure itself, end
to end and in both halves: it reads a value out of a reading, sends that same
value back to the operation that consumes it, and fails if the runtime refuses
its own output — for a `ModuleType` published at each end of the exact-integer
range, and for the last factory and workspace index that can exist, published
from a stub reporting the largest count this runtime carries and then read back.
Just past either end of the value range it asserts that both halves agree: the
reading cannot publish the value and the operation does not admit it. It holds
the structure that makes closure hold by construction rather than by two
numbers that happen to agree — one fidelity declaration, named by every
producer and every consumer — and holds the declared bounds to two kinds, work
and fidelity, so a ceiling on an address cannot return unnoticed.
`tests/muejeje/test_network_inventory.py` and `test_platform_descriptors.py`
page past where the withdrawn ceilings stood.
`tests/muejeje/test_address_domains.py` holds every address argument and
published address to a name that says its domain, refuses an address sent to
the other domain and both retired names, and drives every operation about one
subject refusing a request that names none — without reading anything.
**Status.** `ENFORCED` for the kernel's own logic under Node;
`NOT_YET_LIVE_VERIFIED` against `9.0.1.0858` (MJ-015).

### MJ-031 — Platform access is one read-only, cited call boundary
**Requirement.** Muejeje reaches Packet Tracer through **one boundary**: a
single packaged file names `ipc`, and one pair of functions in it makes every
platform call this artifact makes, by **interface member** — `Interface.member`
— admitting only members on a declared read-only allowlist, and only on a
platform object that boundary itself handed out as that interface. The adapters
that read a subject — device
descriptors, chassis modules — are declared adapters beside it and call the
platform only through that function; they name no platform object of their own.
Core, protocol, admission, dispatch, lifecycle and every operation stay
platform-agnostic: an operation calls an adapter, and an adapter reads no
kernel state, shapes no envelope and dispatches nothing (MJ-019).

**Four rules bound what may cross it.**

1. **Documented or evidenced only, per interface.** Every entry on the
   allowlist is a member documented on its own interface's page of Cisco's
   installed IpcAPI reference for the pinned build — with that arity, handing
   over that interface — or is already evidenced against it. A citation never
   transfers between interfaces: `getType` on `Device`, `DeviceDescriptor` and
   `ModuleDescriptor` is three signatures with three standings, and
   `getRootModule` hands over installed hardware on `Device` and a descriptor
   on `DeviceDescriptor`. A guess earns a bare `Invalid arguments for IPC call
   "X"` that says nothing about why (`AGENTS.md` rule 6).
2. **No mutation, proved positively.** The allowlist is the proof: it holds
   only documented getters, and an adapter names no platform member at a call
   site, so a call outside the list cannot be written — it is refused by the
   boundary before a receiver is touched. So is an admitted member asked of an
   object that is a different interface, and a call with the wrong number of
   arguments: a name admitted on one interface is never admitted on another,
   and every receiver's interface is decided by the boundary from the member
   that produced it, never asserted by an adapter. A blacklist of mutating
   verbs is kept
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
4. **No consumer or topology assumption.** Two subjects, and the difference
   matters. The *factory* describes what models exist and what hardware each
   can accept; it does not change under a reading. The *workspace* is what a
   session happens to hold, and it does — so a reading of it is an observation
   at a moment, never a fact about "the network", and nothing caches one.

   Reading an inventory is not assuming a topology, which is what MJ-002
   forbids: no expected count, no naming scheme, no role, no ordering that
   outlives a reading. What is still unread is unread on purpose — a link, an
   address, a port's state and a configuration are each a further subject with
   its own evidence and its own bounds, and none has an operation that needs
   it yet. A port's *name* is read, by `network.device_ports`, and nothing else
   about it: no link is followed from it, no address or up/down state is read,
   and the name is never parsed into a slot or a kind. Nothing anywhere reads
   or writes a device instance's state.

   **A workspace reading is one observation, and never a join.**
   `network.device_identity` reports what one device *is* — its name, model and
   DeviceType — and every one of those facts is read off that one device in
   that one reading. A `workspace_index` is the position the platform handed
   the device over at, in that reading: it is not stable identity, and it is not
   a `factory_index` — they are different arguments, so neither can be sent
   where the other is expected. Nothing relates a workspace device to a factory descriptor,
   and in particular nothing infers the relation from an index, from an equal
   or similar name, or from a model string. Cisco documents
   `Device.getDescriptor()`, which would answer it from the device itself with
   no matching of ours involved; it is a further subject with its own bounds
   and its own evidence, named here so that the relation having an API is on
   record and so that nothing manufactures one without it (MJ-002, MJ-015).

   **A port reading carries the identity that attributes it.**
   `network.device_ports` selects one device by `workspace_index`, reads its
   name and model, and reads that same device's ports, after a single
   hand-over, in one call. A consumer never joins an identity read at one
   moment with ports read at another, because a workspace position is not an
   identity and the two moments need not describe the same device.
   Re-reporting the name and model is snapshot consistency, not duplication.
   The DeviceType is not re-read: it attributes nothing a port needs, and
   `Device.getType()` has the least standing of the three identity getters.
   Ports are read one bounded window at a time from `port_offset`, each
   `port_index` is a position in that reading, and a window that stops short
   of `port_count` says so.

**An unreadable platform is an observation, not a failure.** No V6 error is
reported for it: the request was admissible, and the answer is that no reading
was obtained. Four reasons stay distinct, because a consumer acts differently on
each:

| Reason | What was observed |
| --- | --- |
| `PLATFORM_ABSENT` | there is no platform object here at all |
| `PLATFORM_MEMBER_ABSENT` | the object is here and does not offer the member — **nothing was called** |
| `PLATFORM_CALL_FAILED` | the member was called and the call did not return |
| `PLATFORM_ANSWER_UNUSABLE` | it answered, and the answer could not be attributed |

**A member that is not there is not a failed call**, and the boundary checks
before it invokes. Nothing was called, so nothing was refused: that reading says
the interface is not the one this artifact was written against, which is a
different next step from a call that was reached and did not return. Collapsing
them would invent a refusal nobody performed. **The adapter never names what
made a call fail** — it cannot see that, and it does not guess.

**Whose failure was it is part of the contract.** Exactly two things become an
unavailable reading: something the boundary observed about the platform, and an
answer a declared validator refused. Anything else thrown inside an adapter is a
defect in *this artifact* and reaches the dispatcher as `ENGINE_EXCEPTION`
(MJ-022). That cuts both ways, and the second direction is easy to miss: **an
argument outside an adapter's own declared bounds is a defect too.** V6
admission has already refused anything outside an operation's rule and an
operation defaults an argument nobody sent, so such a value came from our own
code — clamping it would read a *different* window, or a different model, and
report the result as an observation about Packet Tracer.

**A capability with no evidenced privilege stays pending, and a target reading
is attributed only by what the target printed.** This module requests no
privilege (MJ-025, MJ-032). An exploratory run on `9.0.1.0858` observed what a
Script Module carrying none gets: `IPC.hardwareFactory()` and `IPC.network()`
were denied, every `platform.*` and `network.*` reading came back
`PLATFORM_CALL_FAILED`, and for each Packet Tracer printed that the module
*"does not have the necessary privilege for IPC call"* `hardwareFactory` or
`network`. That diagnostic, recorded beside the envelope, is what attributes
those failures; the reading names no cause, and never will. Which privilege
each call needs is still unmeasured, so the capabilities stay `PENDING_TARGET`,
and `PLATFORM_CALL_FAILED` from any other call, build or module is not read as
a denied privilege unless a diagnostic says so. An earlier revision refused to
predict that first reading, and was right to: a prediction that came true would
still have been a claim with nothing behind it (MJ-015).

**A capability may compose with another without owning its vocabulary.**
`platform.device_descriptors` reports which models the factory offers and at
which index; `platform.module_descriptors` and `platform.module_type_support`
ask about the model at one of those indexes. The second takes a `ModuleType`
value as an argument, and that value comes from the platform too — from a
descriptor's own supported-type list, or from a module in its chassis. Passing a
number the platform produced back to the platform is not a mirror; it is the
opposite of one, and it is what lets a consumer ask "does this model accept
this" without either side carrying a table of what the types are (MJ-014).

**Composition is what makes relay closure binding here.** Both values a
consumer relays among them — the factory index and the `ModuleType` — are
published by one operation and admitted by the others, so each has a single
declared domain and no consuming rule narrows it (MJ-029). The index a
model was read at is reported on the model itself, so it never has to be
derived from `factory_offset`, and every index below `available_count` can be sent
back, so the count is all a consumer needs to page the whole factory.

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
**Verification.** One module per responsibility.
`tests/muejeje/test_platform_adapter.py` asserts that one file names `ipc`,
that only declared adapters reach the boundary, that no adapter names a
platform member at a call site, and that an adapter carries no number but its
own bounds. `tests/muejeje/test_platform_allowlist.py` holds the allowlist equal
to the documented set of interface members, refuses a mutation-shaped entry,
requires every call site to spell one admitted `Interface.member`, and compares
the calls actually made — recorded by a stub that logs the interface each call
landed on — against that set, per operation and as a union.
`tests/muejeje/test_platform_boundary.py` drives the boundary refusing a member
outside the allowlist, an admitted member asked of another interface, the wrong
arity and a receiver it never handed out, each without touching the receiver,
and keeps the readings it can report distinct.
`tests/muejeje/test_platform_reference.py` re-derives every entry from its own
interface's installed page — member, arity and what it hands over — with each
page hash-pinned, and holds the evidence table in the offline audit to one row
per entry citing that page.
`tests/muejeje/test_workspace_links_blocked.py` holds the allowlist to admitting
no member that reads a link, and re-derives from the installed pages why none
is admitted: every documented route to a link hands over the base `Link`, no
member hands over a `Cable`, and no page documents `getClassName()`.
`tests/muejeje/test_platform_readings.py` drives every device reading, every
field validator behind them, and that a defect inside an adapter reaches the
caller as `ENGINE_EXCEPTION` rather than as a platform reading;
`tests/muejeje/test_platform_module_walk.py` does the same for the chassis
walk, including each bound and the subtree it marks.
`tests/muejeje/test_platform_descriptors.py` and
`tests/muejeje/test_platform_modules.py` and
`tests/muejeje/test_platform_support.py` cover the platform operations: one
result shape whether the platform answered or not, the window or chassis it reports,
the declared argument rules, and no self-certified verdict.
`tests/muejeje/test_network_inventory.py`,
`tests/muejeje/test_network_identity.py`, `test_network_ports.py` and
`test_network_port_values.py` do the same for the workspace ones. The identity
and port modules additionally assert that their adapters name no factory symbol
at all — the positive form of "nothing is correlated" — and the port modules
that one hand-over serves the identity and the ports alike, even on a workspace
that hands over a different device each time it is asked.
`tests/muejeje/test_source_root.py` gates the enum identifiers, and
`tests/muejeje/test_platform_declarations.py` checks the declarations
themselves — which files may name `ipc`, which are adapters, and which may
shape a reading at all.
**Status.** `ENFORCED` for the boundary, the read-only rule, the failure
attribution and the adapters' own logic under Node; `PENDING_TARGET` for every
capability that reaches the platform — `platform.device_descriptors`,
`platform.module_descriptors`, `platform.module_type_support`,
`network.device_inventory`, `network.device_identity` and
`network.device_ports`. Their `OBSERVED`
branches have only ever been driven against a stub, and both target runs — the
official one at `d37ba37` and the earlier exploratory one — were denied at each
capability's root call (MJ-015).

### MJ-032 — A declared privilege must be a serialized token an evidenced call requires
**Requirement.** `build_options.privileges` may be empty, or may hold only
**serialized privilege tokens** that a call this module makes is evidenced to
require. An empty list needs no evidence: asking for nothing cannot ask for the
wrong thing (MJ-025).

**Why a wrong name is worse than a missing one.** Cisco is explicit that *"the
security privileges indicate which IPC calls this Script Module can make. Calls
to unselected privileges will be denied"*. A misspelled or invented privilege
therefore passes packaging and ships inside the artifact, and whatever it then
does happens in the one place this repository cannot observe. The audit is the
last point at which the name can still be refused, which is why it is refused
there rather than shipped to find out.

**This is a rule about the name, not a prediction about the run.** Cisco's
sentence says what an unselected privilege means for a call that needs it; it
does not say which privilege any of these calls need, and nothing here has
measured that. So the empty set is justified by the absence of evidence for any
name, and never by a forecast of what the target will answer.

**Three namespaces, and they are not aliases.** An *internal privilege index*
is an integer the binary compares a call against. A *serialized token* —
`GET_NETWORK_INFO` — is what Packet Tracer stores for a Script Module, and is
the only namespace this field holds. An *IpcAPI symbol* — `PrivGetNetwork`,
`PrivApplication`, `PrivActivityWizard` — is an identifier in Cisco's generated
HTML reference, read from pages this repository hash-pins. `PrivGetNetwork` and
`GET_NETWORK_INFO` read like two spellings of one thing and **nothing measured
says they are**, so the validator refuses the symbol with its own reason rather
than accepting it on the resemblance. A validator that admitted a privilege
because a similarly named API symbol existed would ship a name Packet Tracer
never stores.

**The admissible set is derived from call evidence, not from a catalogue.** The
pinned `PacketTracer.exe` carries twelve indexed tokens; that a token *exists*
does not make it askable. What makes one askable is a recorded call descriptor:
`IPC.hardwareFactory()` and `IPC.network()` both require index 1, and index 1
serializes as `GET_NETWORK_INFO`, so the minimum set is that one token and the
manifest declares exactly it. `CHANGE_NETWORK_INFO` and `IPC` are real tokens
and are refused, because no call this module makes is evidenced to need them —
nothing is inferred from a privilege's *name*. Widening the set means recording
which call requires which index, not editing the manifest.

**Three facts, kept apart.** The binary mapping (index 1 is
`GET_NETWORK_INFO`), the call requirement (both roots want index 1) and the
target's behaviour under `privileges: []` (both roots denied, official LIVE run
at `d37ba37`) are three claims, each able to be true while another is wrong.
Collapsed into one they would assert something no single observation supports.
In particular, that the binary requires `GET_NETWORK_INFO` is **not** evidence
that selecting it makes either call answer: `GET_NETWORK_INFO_BINARY_EVIDENCE`
is `PASS` and `GET_NETWORK_INFO_LIVE_VERIFIED` is `PENDING`. A root still
denied while carrying it is a contradiction to investigate, never a reason to
add privileges. All of it is recorded, with the binary's SHA-256, in
`docs/qa/muejeje-pts-privilege-map.md`; reproduction detail that was not
supplied is marked `PENDING` there rather than invented.
**Rationale.** This is `AGENTS.md` rule 6 — never guess a PT API signature —
applied to the one field whose wrong value is invisible until the target runs.
The shape rules run before the evidence rule, so a typo is still reported as a
typo rather than sending a reader to look for a privilege catalogue.
**Verification.** `tests/muejeje/test_privileges.py` drives the rule in every
direction: empty accepted, the evidenced token accepted, an invented token
refused and named while the evidenced one is not, an IpcAPI symbol refused as
the wrong namespace, a real-but-unrequired token refused, the admissible set
derived from the call descriptors rather than written down, and the shape rules
reported first. It also holds the privilege set to being part of the recipe
id, so a different set is a different artifact.
`tests/muejeje/test_privilege_evidence.py` is the measurement half: the binary
map pinned to the manifest's builder hash, the QA record carrying the same map
and call descriptors, reproduction marked `PENDING` rather than invented, and
the IpcAPI symbols re-derived in both directions from the installed reference —
including that it names no serialized token, which is the mapping the validator
refuses to assume. `tests/muejeje/test_manifest.py` asserts
`BUILD_INPUT_INVALID` with no recipe id for every refused entry.
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
walked results.

**A nested path is a floor, not a fixed set.** An earlier revision held the set
of published paths *equal*, which made publishing a new nested object a failure
— an additive change, invisible to a consumer that does not read it, refused by
a rule written to permit exactly that kind of growth. What is held is that every
frozen path is still answered, that every field under it is still there, and
that each still carries the type it carried: "keeps its name while meaning
something else" is the half of this rule a name-only reader cannot see.

**Compatible — no protocol version change:**

| Change | Why a consumer survives it |
| --- | --- |
| a new field in an operation's `result`, at any level | a consumer that does not read it cannot see it |
| a new nested object in a `result` | same: nothing was reading a path that did not exist |
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

**A published shape is externally frozen once it is release-qualified — not
before.** V6's guarantees are made to consumers of a *released* artifact, and
nothing here has been released: one governed `.pts` is packaged and
kernel-qualified and no version is release-qualified, every platform capability
is `PENDING_TARGET` (MJ-031), and the only readers of these results are this
repository's own tests. While that holds, a result field
that turns out to misdescribe what the platform actually said is **corrected**
rather than carried forward, and the correction is recorded here with the
evidence that forced it. Preserving a known mistake because a gate froze it
would be the gate defeating its own purpose: it exists to make a contract change
*visible and deliberate*, not to make a wrong answer permanent.

Once a version is release-qualified against the target — packaged, run and
recorded — the tables in `tests/muejeje/test_v6_result_shapes.py` stop being a
working baseline and become the promise this section describes, and a change to
one is a new protocol version.

**Corrections made under that rule, so far:**

| Shape | Why it was wrong |
| --- | --- |
| `nodes[].slot_index` → `nodes[].module_index` | `getModuleAt(i)` indexes a module enumeration; nothing evidenced it as a slot position, and `getSlotCount()`/`getSlotTypeAt()` are a separate enumeration this repository has never observed to correspond with it |
| `nodes[].children_present` withdrawn | it counted "bays that hold a module", which required reading a `null` from `getModuleAt` as an empty bay — a semantic no target evidence supports |
| `max_device_index` withdrawn from `platform.device_descriptors` and `network.device_inventory` | it reported an addressing ceiling of 4096 that bounded no work (MJ-029). With every index admitted up to the exact-integer limit, any index below `available_count` is addressable, so the field could only ever repeat a constant the count already implies |
| `device_index` split into `factory_index` (`platform.module_descriptors`, `platform.module_type_support`, `descriptors[]`) and `workspace_index` (`network.device_identity`); `offset` into `factory_offset` and `workspace_offset`; `devices[].index` renamed `devices[].workspace_index` | one name carried positions from two enumerations of two subjects, so a workspace position relayed by the name it was published under was admitted as a factory position with nothing to refuse it (MJ-029) |
| `factory_index` and `workspace_index` required by the operations about one model or one device | each defaulted to 0 and answered about whatever occupied the first position when the caller had selected none — a question nobody asked, reported as an observation (MJ-029) |

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
object a result publishes, holds every frozen path to still being answered with
its fields *and their types*, admits a path nobody froze as additive, drives a
platform operation against a stub so an empty list cannot hide a shape, and
asserts each measure in both directions on synthetic results.
**Status.** `ENFORCED` for the kernel's own logic under Node;
`NOT_YET_LIVE_VERIFIED` against `9.0.1.0858` (MJ-015).

## Milestones and release

### MJ-033 — Milestone Core Readiness
**Requirement.** M1–M6 may progress in implementation while earlier milestones
are still waiting on target evidence. Implementation order is not blocked by
evidence order — a capability whose code is complete and whose target reading
does not exist yet is a normal state, not a stalled one (MJ-015).

**But no milestone is `DONE` until it is `CORE_READY`.** Those are two different
claims, and collapsing them is what lets a milestone be reported finished while
something it promised is still missing. Core Readiness requires, at minimum, all
of:

| Gate | What it asks |
| --- | --- |
| complete intended scope | everything the milestone said it would do, not the part that was easy |
| coherent, stable contract | one vocabulary, no self-contradiction, nothing a consumer must guess (MJ-005, MJ-029) |
| no known P0/P1 defect | no open defect of that severity, whether or not anyone has filed it |
| bounded behaviour | every input, walk and window bounded, and every bound Muejeje's own (MJ-029) |
| correct failure attribution | our defect never wears the platform's name, and no reading names a cause nothing observed (MJ-022, MJ-031) |
| preserved architecture boundaries | one `mcpDispatchV6`, platform access only through the declared boundary, dependency direction inward (MJ-007, MJ-019) |
| genericity | no consumer, project or topology assumption anywhere in the artifact (MJ-001, MJ-002, MJ-004) |
| compatibility assessment | what changed, and whether it was additive or breaking, decided by the rule rather than by judgement (MJ-030) |
| maintainability gates | complexity budgets met, or an exception named and justified (MJ-020, MJ-021) |
| applicable tests | every new behaviour tested, and every gate the milestone claims actually asserting it |
| exact-SHA CI | CI green on the exact pushed commit, not on "the branch" |
| target evidence | for every Packet-Tracer-dependent claim the milestone makes (MJ-015) |

**The list is a floor, not a ceiling.** "At minimum" is load-bearing: a
milestone that satisfies all twelve and still has a known reason not to be
trusted is not `CORE_READY`, and the reason is written down rather than argued
away.

**Target evidence gates the verdict, not the work.** A milestone whose code,
tests and CI are complete and whose only outstanding gate is a target reading is
reported exactly that way — implementation complete, `CORE_READY = NO`, with the
missing gate named. What it is never reported as is `DONE`.

**Current state, and it is a measurement rather than a plan:**

```text
M0B = NOT_COMPLETE
M0C = NOT_COMPLETE
M1_CORE_READY = YES
M2_CORE_READY = NO
M3_CORE_READY = NO
ZERO_CHANGE_CUTOVER = NOT_ACHIEVED
```

- **M0B** is not complete: it still includes credential and transport API
  qualification. No transport exists, and MJ-026's terms are `BASELINED` rather
  than exercised — there is nothing yet to qualify a credential against. Before
  any of it comes IPC privilege: a governed artifact carrying none was denied
  both root IPC calls on the target. Which privilege they require is now
  evidenced from the pinned binary (MJ-032), and no API reached through them is
  baselined until a run shows them answering.
- **M0C** is not complete: it still includes batch and auth-boundary semantics.
  MJ-027 is the contract the first batch operation must satisfy, and no batch
  operation exists; the auth boundary is in the same position under MJ-026.
- **M1** is `CORE_READY`: the governed artifact at `d37ba37` was packaged from
  its declared recipe, loaded and started on `9.0.1.0858`, and answered from its
  own engine — `mcpDispatchV6` present, identify and capabilities, all five
  refusal classes, and identify again across a stop and a start.
  `OFFICIAL_PACKAGING_PROVED` and `V6_KERNEL_VERIFIED` are both `PASS` on that
  evidence, and on nothing wider: the same run's platform calls were all denied
  (MJ-015).
- **M2** is not `CORE_READY`: every platform capability is `PENDING_TARGET`.
  The official run carried `privileges: []` and had `IPC.hardwareFactory()`
  denied. `GET_NETWORK_INFO` is now evidenced as what that call requires, the
  manifest declares it, and no artifact carrying it has been run — so no
  platform member has answered yet.
- **M3** is not `CORE_READY`: its read-only topology scope is incomplete. The
  workspace inventory, one device's identity and one device's ports are
  implemented; the workspace's links are not. Every documented route to a link
  — `Network.getLinkAt(int)`, or `getLink()` on a port — hands over the base
  `Link`, which documents only its connection type; endpoints are documented
  only on the derived `Cable` and `Antenna`, which no documented member hands
  over from a `Link`; and nothing installed says which one a handed-over `Link`
  is. The `CONNECT_TYPES` list names no interface, and matching a value against
  a table of ours would be a mirror (MJ-014). Reading links waits on target
  evidence of what a Script Module is handed. Every workspace capability is
  also `PENDING_TARGET`, its root call `IPC.network()` denied the same way
  (MJ-015, MJ-031).
- **The zero-change cutover** is `NOT_ACHIEVED` (MJ-034): one artifact is
  packaged and kernel-qualified, no version is release-qualified, and no
  compatibility facade exists outside the V6 core.

**The next task for M0B, M2 and M3 is the minimum-privilege qualification, not
more implementation**: its own declared run, changing exactly one thing — the
privilege set, from `[]` to the one token evidenced for both root calls
(MJ-032) — with Packet Tracer's diagnostics recorded beside every envelope.
None of them is marked `CORE_READY`, or complete, on the strength of a call
that was denied, or of a requirement read out of a binary.

Each stays at that value until its own gates are satisfied. None of them moves
because a later milestone started, because the test suite is green, or because
the work looks finished from inside the repository.
**Rationale.** The failure this prevents is a milestone marked `DONE` on the
strength of a green offline run. `APPLIED != VERIFIED` already says a change
being made is not a change being proved (MJ-010); this says the same thing about
a milestone, and names the gates so "done" cannot be re-argued each time. Letting
implementation run ahead of evidence is deliberate: the alternative is a line
that stops dead whenever a target is unavailable, which would make the evidence
rule expensive enough that somebody eventually weakens it.
**Verification.** The states above are recorded here and in the offline audit,
which is where each gate's evidence lives. Nothing automated asserts them yet: a
gate that read this table would be checking that a document agrees with itself.
**Status.** `BASELINED`.

### MJ-034 — Zero-change artifact cutover
**Requirement.** The release-qualified `muejeje.pts` must eventually be able to
replace the legacy artifact **without changes to existing production code,
tests, domain, application or integration code**. If adopting Muejeje requires
editing a consumer, the cutover has not been achieved — it has been traded for a
migration, which is the thing this requirement exists to refuse.

**Legacy compatibility is a facade, and it lives outside the generic V6 core.**
Whatever the legacy artifact's callers depend on — its shapes, its names, its
accidents — is adapted in a compatibility layer that sits outside the kernel.
None of it enters V6, the operations, or the platform adapters. A kernel that
carried one consumer's legacy shape would have stopped being a generic runtime
the moment it did (MJ-001, MJ-004), and the facade is what lets the cutover be
compatible without the core being compromised.

**CP LIVE remains a consumer, never a kernel dependency.** It exercises Muejeje;
it does not define it. A CP LIVE SHA may be recorded as integration evidence,
never as a version, prerequisite or watermark.

**This is not claimed to be achieved.** One governed artifact has been packaged
and kernel-qualified (`d37ba37`); no version is release-qualified, no
compatibility facade exists, and no consumer has been cut over. The requirement states the target and the shape of
an acceptable solution; it records no progress toward it, and its state is
`ZERO_CHANGE_CUTOVER = NOT_ACHIEVED`, recorded beside the milestone states
under MJ-033.
**Rationale.** "Replace the artifact, then fix the callers" is how a runtime
acquires a consumer's assumptions permanently: the edits land in the core
because that is where they are cheapest, and the generic runtime quietly becomes
one project's. Naming the facade as the only legal home for legacy shape decides
that in advance, while there is still nothing to move.
**Verification.** Nothing yet, and deliberately so — there is no facade, no
built artifact and no cutover to verify. The architecture gates already keep the
core generic (MJ-001, MJ-019), which is the half of this that can be enforced
before the other half exists.
**Status.** `BASELINED`.

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
| **TODO-PRIVILEGES** | **RESOLVED** by `MJ-025` and `MJ-032`: `["GET_NETWORK_INFO"]`. The `.pki` privilege catalogue is still not installed, and this resolution does not need it — the requirement was read out of the pinned `PacketTracer.exe` instead: both root calls require privilege index 1, which serializes as `GET_NETWORK_INFO`. The set is the minimum that evidence supports, and it grows only by recording another call descriptor (`MJ-032`). What a target does *with* it is not yet observed: an artifact carrying `[]` was denied both calls on `9.0.1.0858`, and a capability stays `PENDING_TARGET` until a platform reading answers (`MJ-031`). |
| **TODO-RECIPE-SCOPE** | **RESOLVED.** Manifest `schema_version: 2` splits inputs into `artifact_inputs` (bytes packaged into the `.pts`, required to live under the owned root), `tooling_inputs` (the auditor — ships nothing, still part of recipe identity) and `reference_inputs` (empty). A path may not appear in two categories. |

## Related documents

- [Operating model](muejeje-runtime-operating-model.md) — governance and boundaries.
- [Packaging recipe](../qa/muejeje-pts-packaging-recipe.md) — the complete
  Scripting Interface procedure, its preconditions and what a run must record.
- [Privilege map](../qa/muejeje-pts-privilege-map.md) — the three privilege
  namespaces, the binary map and the call descriptors behind MJ-032, tied to
  the pinned `PacketTracer.exe` SHA-256.
- [Minimum-privilege LIVE runbook](../qa/muejeje-pts-privilege-live-runbook.md)
  — what the next manual run changes, and how each outcome is read.
- [v2 preflight inventory](../qa/muejeje-pts-v2-preflight-inventory.md) — the
  per-symbol evidence behind MJ-012, MJ-013 and MJ-014.
- [ADR-001](../qa/muejeje-pts-adr-001-branch-realignment.md) and its
  [resolution](../qa/muejeje-pts-adr-001-resolution.md).
