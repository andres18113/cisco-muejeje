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
**Verification.** Review of every change for consumer names or consumer-shaped
concepts; the operating model's consumer rule.
**Status.** `BASELINED`

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
**Verification.** Review; the contamination check applied to build inputs.
**Status.** `ENFORCED` — build inputs and `pts/` are free of these terms.

## Contract boundaries

### MJ-005 — Runtime Protocol V6 is the consumer-facing contract
**Requirement.** Everything a consumer may rely on is expressed in Runtime
Protocol V6. Consumers do not depend on Muejeje internals, on the transport, or
on Packet Tracer specifics.
**Rationale.** One northbound contract is what makes consumers replaceable and
makes Muejeje's own internals free to change.
**Verification.** V6 schema and its conformance tests, once V6 exists.
**Status.** `BASELINED` — V6 is not implemented.

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
**Verification.** Runtime source review; a test asserting a single dispatch
symbol, once V6 exists.
**Status.** `BASELINED` — not implemented.

### MJ-008 — V6 is typed, declarative, whitelisted and fail-closed
**Requirement.** V6 operations are typed and declarative, admitted by an explicit
whitelist, and fail closed on version, schema or correlation mismatch. The
initial whitelist contains only read-only `runtime.identify`.
**Rationale.** A permissive dispatcher cannot bound what a consumer can cause.
**Verification.** Schema validation tests and negative tests per mismatch class,
once V6 exists.
**Status.** `BASELINED` — not implemented.

### MJ-009 — Raw JavaScript is V5 compatibility only
**Requirement.** Arbitrary JavaScript execution is a legacy V5 surface. Migrated
V6 operations accept no arbitrary JS.
**Rationale.** Raw JS is unbounded by construction; keeping it out of V6 is what
lets V6 make any guarantee at all.
**Verification.** V6 handlers reject free-form source; review of any new raw-JS
call site.
**Status.** `BASELINED` — the V5 surface is in use today.

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
**Verification.** `reference_inputs: []` in the manifest and the regressions in
`tests/test_muejeje_build.py`; a runtime check once the six globals are replaced.
**Status.** `ENFORCED` for the build; `BASELINED (deviation)` for the runtime —
`htmlWindow`, `runCode`, `configureIosDevice`, `allModuleTypes`, `addDevice` and
`addLink` are still PTBuilder-supplied.

### MJ-014 — No numeric Cisco enum table is a source of truth
**Requirement.** Hand-maintained numeric tables mirroring Cisco enums are working
copies. Authoritative values come from Cisco runtime discovery or descriptors.
**Rationale.** A mirrored constant is correct only until Packet Tracer changes,
and nothing in the repository would notice.
**Verification.** Enum values reconciled against runtime descriptors; the mirror
marked as a mirror at its definition.
**Status.** `BASELINED (deviation)` — `PT_DEVICE_TYPE` (33 entries),
`PT_CONNECT_TYPE` (16) and `ModuleSpec.module_type` (151) are mirrors in use.
`allModuleTypes` in particular must move to descriptor lookup
(`module.getType()`, `device.isModuleTypeSupported(int)`).

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
`packaging_state` block; `tests/test_muejeje_build.py`.
**Status.** `ENFORCED`

### MJ-017 — An incomplete input inventory has no recipe id
**Requirement.** `build_recipe_id` is null while any input is unresolved. The
artifact SHA-256 is measured externally and is never embedded in the artifact it
describes. Byte-for-byte reproducibility is not claimed.
**Rationale.** A recipe id over an incomplete inventory identifies nothing, and a
self-embedded hash cannot be checked.
**Verification.** `tests/test_muejeje_build_identity.py`; the recipe id is set
only in `PACKAGING_MANUAL_AVAILABLE`.
**Status.** `ENFORCED`

## Open decisions

Not requirements. Each needs a decision before it can become one.

| TODO | Question | Blocks |
| --- | --- | --- |
| **TODO-SRC-ROOT** | Does the owned artifact keep `EXTENSION/**` as its permanent source root? The manifest's `own_inputs` are today the legacy *MCP Control Center* extension's sources — the same tree that produces the existing published `.pts`, and whose `main.js` carries the six PTBuilder globals. An owned artifact sharing a source root with the legacy extension cannot evolve independently. **Assessed in M0D; no migration performed.** | MJ-001, MJ-013; the engine/interface file orders |
| **TODO-RECIPE-SCOPE** | `own_inputs` also lists `src/…/pts/build.py` and `tools/build_muejeje_pts.py`, which are the *auditor*, not artifact content. Should the recipe separate artifact inputs from tooling identity? | MJ-017 |
| **TODO-MODULE-ID** | The Script Module ID and its stability across rebuilds. | `build_options.module_id` |
| **TODO-STARTUP** | `On Startup` vs `On Demand`. The file channel only runs while the module runs. | `build_options.startup` |
| **TODO-PRIVILEGES** | The requested IPC privilege set. The privilege catalogue lives in `.pki` files that are not installed. | `build_options.privileges` |
| **TODO-SIGNING** | Publisher signing (PKCS#12) and key custody. | reproducibility |
| **TODO-V6-SHAPE** | The V6 schema itself. Explicitly out of scope until the runtime kernel task. | MJ-005, MJ-007, MJ-008 |

## Related documents

- [Operating model](muejeje-runtime-operating-model.md) — governance and boundaries.
- [v2 preflight inventory](../qa/muejeje-pts-v2-preflight-inventory.md) — the
  per-symbol evidence behind MJ-012, MJ-013 and MJ-014.
- [ADR-001](../qa/muejeje-pts-adr-001-branch-realignment.md) and its
  [resolution](../qa/muejeje-pts-adr-001-resolution.md).
