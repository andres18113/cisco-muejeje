# E9.5 architecture and runtime stabilization

E9.5 is a stabilization boundary between the enterprise foundation (E4-E9)
and future routing work. It does not add BGP, IPv6, redistribution,
acceptance, diagnosis, or autofix. Its purpose is to make identity,
deployment, evidence, mutation, verification, and failure semantics explicit
before a later layer depends on them.

This document describes contracts present in the current source tree. It is
not Packet Tracer evidence. A parser, renderer, adapter, or offline test can
prove an architectural property, but cannot by itself prove that a particular
Packet Tracer version and model support a capability. Runtime debts are tracked
separately in [the E9.5 runtime debt register](../qa/e95-runtime-debt.md).

The central flow is:

```text
TopologyPlan (E4, hash schema v2)
       |
       +-- physical_topology_hash --> E5-E9 source binding
       +-- layout_hash ------------> presentation identity
       `-- artifact_hash ----------> complete E4 artifact identity
       |
physical ensure + independent read-back
       |
DeploymentManifest
       |
semantic device ID -> observed runtime target
       |
application DAG -> execution journal -> dirty state
       |
verification prerequisite graph -> EvidenceRecord
```

## Topology identity v2

`TopologyPlan` carries three independent SHA-256 identities and an explicit
`hash_schema_version`.

| Identity | Covers | Does not mean |
| --- | --- | --- |
| `physical_topology_hash` | Semantic device identities, models, categories, roles, physical hierarchy, non-visual metadata, modules, exact link endpoints and ports, cable intent, link role, redundancy metadata, and `dual_stack` | It does not cover coordinates, layout regions, visual metadata, warnings, or errors. |
| `layout_hash` | Device names and coordinates, regions, bounds, and the layout profile | It does not change the physical network identity. |
| `artifact_hash` | The physical hash, layout hash, warnings, and errors | It is the identity of the complete E4 artifact, not the source identity for E5-E9 configuration. |

Metadata keys beginning with `layout_`, `visual_`, or `display_` are excluded
from physical identity. Device order and link order are canonicalized before
hashing. A coordinate-only mutation therefore changes `layout_hash` and
`artifact_hash`, while `physical_topology_hash` remains stable.

For controlled compatibility, `semantic_hash` retains the complete-artifact
meaning and is stamped with `artifact_hash`. New E5-E9 plans bind to
`TopologyPlan.physical_identity_hash`, which returns
`physical_topology_hash` when available and falls back to the legacy
`semantic_hash` only for an explicitly legacy plan. The E4 physical deployer
is stricter: it requires schema `2`, requires a stored physical hash, and
recomputes that hash before mutation.

This split prevents a visual relocation from invalidating a configuration,
service, voice, security, or control-plane plan while still detecting a real
physical change such as a model, module, port, link, or redundancy mutation.

## DeploymentManifest and runtime identity

Plans contain semantic identities; Packet Tracer contains runtime objects.
`DeploymentManifest` is the explicit binding between them. It records:

- a deployment ID and the exact `physical_topology_hash`;
- backend, backend version, and an `EnvironmentFingerprint`;
- one unique `DeploymentBinding` per semantic device;
- the deployed name and model;
- an observed runtime identifier when it is stable;
- an optional composite runtime fingerprint;
- observed interface names and creation evidence;
- the identity method used for that binding.

Manifest creation is downstream of physical deployment. The production E4
use case first ensures devices, observes device name/model/required ports,
ensures links, and observes the exact two endpoints and ports. It emits no
manifest when any required device, port, or link observation fails or when a
binding is missing or ambiguous.

Semantic cable intent remains part of the physical hash. Packet Tracer may
expose exact link peers and ports without exposing a reliable cable-type
getter. In that case peer/port observation and cable observation remain two
separate claims: the manifest may identify the deployed objects, while the
cable claim is an `UNOBSERVABLE` `EvidenceRecord`. The absence of a cable
getter is not converted into verified cable evidence.

At application time E5-E9 verify that the manifest physical hash equals the
plan source hash. Resolution prefers a stable runtime identifier, then the
manifest's recorded deployed name. Every match must be unique and must retain
the planned model; a present runtime fingerprint must also match. Missing,
ambiguous, wrong-model, or wrong-fingerprint targets raise
`DeploymentIdentityError` before the affected plan can be applied.

`NAME_ONLY` exists in the identity vocabulary, but manifest construction does
not select it. A display name is a lookup fallback inside a previously
validated semantic binding, not an independent source of identity.

## EvidenceRecord: orthogonal evidence axes

`EvidenceRecord` deliberately avoids a single overloaded status. It keeps the
following axes independent:

| Axis | Examples | Question answered |
| --- | --- | --- |
| Method | structured API, operational CLI, behavioral, event stream, inferred, none | How was the claim examined? |
| Strength | claim-direct, claim-supporting, inferred, none | How directly does the observation support this particular claim? |
| Freshness | fresh, stale, unknown | Does it belong to the current attempt? |
| Support | supported, unsupported, partial, unknown | What is known about backend capability? |
| Observation | observed, unobservable, probe-failed, skipped, not-attempted | Was state obtained? |
| Verification | verified, failed, conflicted, unverified | Did the observed state satisfy the claim? |
| Readiness | compile/apply/verify are each ready, partial, unknown, unsupported, unobservable, or blocked | At which lifecycle stage can the capability be used? |

A record verifies a claim only when it is fresh, observed, and explicitly
verified. `UNSUPPORTED`, `UNOBSERVABLE`, `FAILED`, and `UNKNOWN` are distinct:

```text
UNKNOWN       support has not been established
UNSUPPORTED   exact negative capability evidence exists
UNOBSERVABLE  the feature may work, but the current observer cannot prove it
FAILED        a fresh attempted behavior or state did not satisfy the claim
```

The legacy result adapter preserves public E5-E9 result fields while those
APIs are migrated. It does not manufacture an observation from a partial
result without fresh evidence. An unmapped legacy evidence method is retained
as a limitation rather than guessed.

## Idempotency, journals, dirty state, and compensation

Typed actions can declare one of these operation semantics:

- `ENSURE_PRESENT` and `ENSURE_ABSENT` for desired membership;
- `SET_VALUE` and `REPLACE` for desired state;
- `TRANSITION` for a controlled state change;
- `EXECUTE_ONCE` for a non-repeatable operation.

Runtime disposition is recorded separately as `CHANGED`, `NO_OP`,
`REASSERTED`, `FAILED`, `BLOCKED`, `SKIPPED`, or `UNKNOWN`. `NO_OP` means the
desired state was already satisfied. `REASSERTED` means the backend accepted
the desired state again; it is not proof that no mutation occurred.

`ApplicationExecutionJournal` is append-only and enforces consecutive
ordinals. Each entry records the action, operation, disposition, batch,
inverse action identity, compensation availability, message, and timestamps.
The journal is the source for partial-application reporting; a final summary
must not erase earlier successful mutations when a later action fails.

Dirty state is derived conservatively:

- no mutation, or a failure before any mutation: `CLEAN`;
- an unknown disposition or ambiguous transport outcome: `UNKNOWN`;
- a failure after mutations with inverses for every mutation:
  `DIRTY_RECOVERABLE`;
- a failure after a mutation without an inverse: `DIRTY_UNRECOVERABLE`.

Cleanup is also explicit. Successful compensation returns the journal to
`CLEAN`; failed compensation makes it `DIRTY_UNRECOVERABLE`; unknown cleanup
keeps the result `UNKNOWN`. A transport timeout after a mutation must not be
reported as a clean failure.

The shared vocabulary makes idempotency observable, but does not imply that
every backend action already performs a native pre-read. Each runtime adapter
must return an honest disposition for its own operation.

## Application DAG versus verification prerequisites

Application order and verification eligibility are different graphs.

The application DAG uses typed action `depends_on` relationships and a stable
Kahn/heap topological order. It answers: "which mutation may be attempted
next?" A dependency is satisfied only by an applied, no-op, reasserted, or
verified result.

The verification graph uses `VerificationPrerequisite` and answers: "which
claim can be tested now?" Its prerequisite kinds include:

- action applied or action verified;
- another verification verified;
- physical link present;
- peer interface enabled;
- service usable;
- phone registered;
- another typed resource ready.

Verification-to-verification dependencies are ordered independently and reject
missing references, duplicate IDs, and cycles. Resource prerequisites are
resolved from observed resource state. This prevents, for example, a failed
foundation from being reinterpreted as a negative ACL test, or an unregistered
phone from being used to claim call-policy enforcement.

## Probe isolation, fingerprints, and cleanup confidence

Capability probes declare an isolation level:

- `SHARED_DEVICE`;
- `RESET_REQUIRED`;
- `FRESH_DEVICE_REQUIRED`;
- `FRESH_SESSION_REQUIRED`.

Legacy `requires_fresh_device` and `requires_power_cycle` flags are mapped into
that single effective isolation contract. VLAN, trunk, L3, static-route, and
OSPF probes require fresh temporary devices in the current registry; a
fresh-session probe is skipped when the runtime cannot guarantee the session.
A reset-required probe is skipped when reset or power-cycle cannot restore the
required baseline.

`ProbeEnvironment` fingerprints backend, exact version, transport, extension,
platform, snapshot schema, runtime mode, and relevant facts. Every probe
definition also has a semantic fingerprint covering its ID, version,
capability, target model, prerequisites, safety, isolation, cost, and relevant
inputs. Inventory fingerprints are canonical and order-independent.

A cached snapshot is considered only when schema, requested models and
capabilities, environment fingerprint, probe fingerprints, and an available
initial inventory fingerprint match. A dirty cleanup or a proven inventory
mismatch invalidates results: previously verified results are demoted to
`UNKNOWN`, their verification flag is cleared, and their execution result is
changed to verification failure.

There is one important confidence distinction in the current source:
`inventory_restored=False` blocks reuse, while `inventory_restored=None` does
not. `None` means the runtime did not supply enough inventory fingerprint data;
it must never be described as verified restoration. Runtime evidence that
requires proven cleanup should require `True`, not merely the snapshot's broad
`reusable` property.

Disposable objects live in two declared namespaces, and cleanup reports only
objects this project created.

`__MCP_PROBE_*` is the capability-discovery namespace. Those probes are created
through `lwAddDevice` and observed with registered queries; they never traverse
the typed control-plane renderer.

`MCP-PROBE-*` is the namespace for a disposable probe that a trusted renderer
may have to render a typed action for. The control-plane renderer validates
compiled device names against an allowlist whose first character must be
alphanumeric, so a leading underscore cannot reach it. The second prefix exists
to satisfy that validator, not to weaken it: the validator is unchanged.

Neither prefix is load-bearing. A temporary device is deleted by its exact
caller-supplied name, so cleanup correctness depends on that name being unique
and remembered, never on matching a prefix. The prefixes exist so that a human
reading the workspace, and a QA residue check, can tell at a glance what is
disposable.

Probe definitions, not tool arguments, select the mutation logic.

## IPAM reconciliation

`AddressReconciler` is backend-neutral and IPv4-only. It reconciles explicitly
requested infrastructure identities: SVI, management, transit, loopback, FHRP
member, and FHRP VIP addresses. Endpoint demand is rejected because the
service is not an endpoint allocator.

Reconciliation validates a strict enterprise address space, validates every
demand pool, rejects duplicate demand or binding identities, rejects duplicate
addresses, and matches existing state first by demand ID and then by a unique
semantic key `(purpose, owner, segment, group)`. Existing identities are
preserved whenever their address and prefix still satisfy the demand.

New demand is allocated deterministically from the first available usable
address after preserving existing bindings. A required change produces an
explicit `AddressRenumbering` and `RENUMBER_REQUIRED`; it is usable for review
but `can_apply_without_renumber` remains false until a caller obtains explicit
approval. Conflicts and insufficient capacity do not produce an applicable
plan. The final plan has a canonical semantic hash.

The reconciler computes desired state only. It does not apply Packet Tracer or
IOS mutations and cannot silently renumber an existing deployment.

## FailureDomain and shared-risk semantics

`FailureDomain` models device, link, chassis, power, site, uplink-provider, and
shared-risk blast radii with explicit provenance. The catalog safely derives
only facts available from E4:

- one domain per semantic device;
- one domain per semantic link;
- site membership only when `site_id` is present.

Chassis, power, carrier, and shared-risk domains must be supplied explicitly
with evidence provenance. Visual separation, naming conventions, and redundant
lines on the canvas do not create independence.

`FailureDomainAnalyzer` compares a primary and surviving path under an explicit
fault scope. Shared blocking domains produce `NOT_INDEPENDENT`. Missing required
coverage produces `UNKNOWN`, never `INDEPENDENT`. Common endpoint devices are
ignored only for a link-fault claim, and that exception is recorded in the
result. Both paths still require explicit physical link membership.

E9 control-plane compilation builds the catalog, attaches an independence
result to each compiled link-failure scenario, rejects a shared blocking
domain, and emits a structured warning when required coverage is incomplete.
This analysis constrains a failover claim; it does not prove convergence.

## Exact links, transport safety, and layout evidence

### Links

Exact link read-back examines both requested ports, requires both ports to have
a link, requires both references to identify the same link object, and compares
both link endpoint lists against the requested device/port pair in either
orientation. One-sided presence, a wrong peer, malformed output, or timeout is
not exact evidence. Convergence polling uses a bounded monotonic deadline.

The link query serializes every endpoint with `json.dumps` and only uses the
Packet Tracer API calls already exercised by this repository. `pt_add_link` and
the live deployment path pin one transport, wait for exact read-back, and
report an error when the acknowledgement does not converge into the requested
link.

### Transport

Transport health keeps these states distinct:

```text
TRANSPORT_UP
POLLING
COMMAND_PATH_RESPONSIVE
DEGRADED
UNRESPONSIVE
```

A listening HTTP bridge or an existing file mailbox is not proof that Packet
Tracer consumes commands. An optional read-only round trip proves the complete
command path. Selection occurs once per operation. The returned fallback is
diagnostic only: `pinned_for_operation` is true and
`silent_replay_allowed` is false. If an ambiguous mutation fails on the pinned
transport, the operation reports that ambiguity and does not replay it through
the other channel.

### Layout

Layout application records four distinct outcomes:

```text
REQUESTED -> ACKNOWLEDGED -> OBSERVED
                           `-> DRIFTED
```

The evidence retains requested coordinates, acknowledgement, independently
observed coordinates, tolerance, and per-axis drift. No acknowledgement leaves
the operation at `REQUESTED`. An acknowledgement without a usable coordinate
getter is only `ACKNOWLEDGED`. Coordinates are `OBSERVED` only when read back
within the explicit tolerance; otherwise they are `DRIFTED`.

This preserves the E4 distinction: deterministic layout calculation and a
mutation acknowledgement may be available even when coordinate read-back is
not. The latter must remain a separate observability claim.

## PhoneControl boundary

Phone execution stays behind an E7 application port:

```text
VoicePlan
   -> Voice applicator/runtime
   -> PhoneControlPort
        -> StructuredPhoneControlAdapter
        -> PacketTracerNativeUiPhoneControlAdapter
        -> UnavailablePhoneControl
```

The port accepts a typed `CallExpectation`, a unique attempt ID, and a start
timestamp. It returns a typed `RuntimeCallObservation`. Execution method remains
explicit as `STRUCTURED_API`, `PACKET_TRACER_NATIVE_UI`, `HYBRID`, or
`UNOBSERVABLE`.

The native UI adapter encapsulates the controlled driver; no domain or E8
security component receives clicks, coordinates, dial routines, or arbitrary
phone commands. E8 can request voice behavior only through an injected typed
E7 operation. With no phone-control adapter, E7 returns `UNOBSERVABLE` and does
not claim a failed or successful call attempt.

This boundary is an architectural result. It does not prove that the native UI
adapter can complete a call in a new live Packet Tracer session. PC-through-
phone data, RTP/audio, and intersite voice remain independent runtime debts.

## Gate discipline

E9.5 may classify an architectural debt from source, migrations, tests, and
documentation. It may classify a Packet Tracer limitation only after a
controlled reproduction records exact version, model, operation, observation
method, negative evidence, and cleanup. Until that happens, the runtime status
remains `UNKNOWN` or pending in the debt register.

The architecture never allows these substitutions:

```text
compiled            != applied
applied             != observed
observed            != behaviorally verified
feature supported   != current state observable
two drawn paths     != independent failure domains
transport listening != command path responsive
layout acknowledged != coordinates observed
registered phone    != call verified
```

## What makes an action APPLIED

The substitution list above says what `APPLIED` is *not*. Until Runtime Safety
R1 it never said what produces it: no document named the event, and
`ActionExecutionStatus` carried no documentation. Runtime Safety R1 adopts the
following contract. This is a **new normative statement, not a restatement of
an older one** — it formalises what the runtime already did, so that callers
stop having to guess.

```text
COMPILED   the typed action was produced by the compiler
APPLIED    the action was accepted by its selected runtime execution channel
OBSERVED   backend state was read through qualifying runtime evidence
VERIFIED   the intended claim satisfied its declared verification criterion
```

`APPLIED` asserts acceptance by the channel and nothing beyond it. It does
**not** assert backend acknowledgement of the intended state, a
`MutationDisposition` of `CHANGED`, directly observed backend state,
successful verification, or behavioural success.

The reason is the transport. The typed configuration channel is
fire-and-forget: `PacketTracerConfigurationRuntime` hands the payload to the
runtime channel and receives no acknowledgement from Packet Tracer. No signal
exists anywhere in the system that could sustain a stronger claim, so a
stronger reading of `APPLIED` would be unrepresentable rather than merely
unproven.

A mutation is therefore honestly described by three independent axes at once:

```text
ExecutionStatus     APPLIED        the channel accepted the dispatch
MutationDisposition UNKNOWN        nobody observed what changed
Verification        not verified   the claim has not been re-read yet
```

That combination is a valid, expected state. It means "the dispatch was
accepted, the backend effect is not yet known". Only verification moves the
third axis, and only qualifying evidence moves the second. A consumer that
reads `APPLIED` alone as proof that Packet Tracer reached the intended state
is making an inference this contract does not license.

Runtimes that *do* observe their own mutation — the physical topology runtime
is the current example — keep their stronger semantics by declaring a
`MutationDisposition`. The contract above narrows nothing for them.

E10 can start only after the architectural contracts have passed full
regression and every runtime capability it depends on has a precise supported,
unsupported, unobservable, failed, or blocked classification backed by the
required evidence. This document does not make that final recommendation.
