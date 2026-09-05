# Governed PoE Delivery Qualification Design

## Purpose

Prepare an offline-tested production path that can qualify powered-device
delivery in a future governed Packet Tracer run without treating switch power
control state as delivery. The path must retain exact model/build identity,
exact switch ports, the powered endpoint involved, typed evidence, bounded
lifecycle state, and verified cleanup/restoration. Until such evidence exists,
the canonical CP-SCALE product remains blocked before topology with
`supports_poe = UNKNOWN`, `poe_ports = None`, and a
`PARTIALLY_RESOLVED` hardware plan.

This work uses ISO/IEC 25010 only as an engineering lens for modularity,
analysability, modifiability, and testability. It uses ISO/IEC/IEEE 42010 only
to make responsibilities, boundaries, dependencies, and decisions explicit.
It does not claim certification or formal conformity with either standard.

## Authoritative baseline

- Repository baseline: `9dcc9183f0891de91a7e5c2532c2aa3e492219f8`.
- `poe-inventory` version 3 observes administrative/runtime switch-port state.
- `RuntimePortDescriptor.power_delivery_active` is not populated by the
  production runtime.
- `getPower()` and `isPowerOn()` do not establish powered-device delivery.
- `MeasuredCapabilityRecord` does not currently preserve claim dimensions.
- `ReferenceHardwarePlanner` consumes a count even though powered endpoints
  are attached through exact `EndpointPortBinding` ports.
- No existing automated endpoint observation is independently attributable to
  PoE. The first qualification path therefore uses a typed manual visible-power
  observer plus a differential control. Automated observers remain
  non-authorizing until separately qualified as power-discriminating.

The authority order remains source, tests, and current evidence; governed
state; primary handoff; GitHub-corrections handoff; then logs/history.

## Decisions

### 1. Keep control inventory separate from delivery qualification

`poe-inventory` version 3 remains a non-mutating control-state observation. It
must not become a delivery probe and must not gain a positive path merely by
populating `power_delivery_active` from the two existing switch getters.

A separate `PoEDeliveryQualificationService` owns powered-device delivery
qualification. It produces evidence for the existing `supports_poe`
capability under a distinct producer/probe identity. Keeping it separate
avoids duplicate `supports_poe` results in ordinary discovery snapshots and
prevents a delivery cleanup failure from demoting unrelated capability probes
in the same session.

### 2. Qualify delivery through a differential visible-power observation

One qualification request names:

- the exact Packet Tracer build;
- the exact candidate switch model;
- an exact comparison-switch model used as the negative arm;
- one or more bindings consisting of candidate switch port, matching control
  port, powered endpoint model, and powered endpoint port;
- one simultaneous observation group.

The runtime creates fresh candidate and comparison fixtures and equivalent
fresh powered endpoints without adding a power adapter. It verifies each
requested and observed model identity, verifies each exact link, and invokes a
typed observation callback while the complete simultaneous fixture is present.
The first production callback records a human's direct visible-power judgment
for each endpoint arm, the visible indicator or boot state used, observer
identity, and observation time. This is persisted as
`MANUAL_VERIFICATION`, matching the repository's existing documented PoE
manual protocol. It is not silently upgraded to runtime evidence.

No current automated endpoint API may emit a positive delivery result. SVI
presence, DHCP state, registration, device creation, and link existence may be
retained as diagnostics, but remain non-authorizing until a separate governed
qualification establishes that a particular observer discriminates power.
An absent manual callback or incomplete judgment is `UNOBSERVABLE` and cannot
contribute an authorized binding.

For each binding, delivery is supported only when the powered state is visibly
observed on the candidate arm and a not-powered state is visibly observed on
the comparison arm during the same episode. Candidate powered plus comparison
powered means the comparison is not a negative control and yields `UNKNOWN`.
Missing identity, link, observation, observer attribution, or control also
yields `UNKNOWN`. The qualifier never turns `getPower()`, `isPowerOn()`,
device creation, link existence, or a comparison model's name into delivery.

All bindings contributing to the advertised powered-port count must be alive
in the same bounded observation episode. Sequential successes may be retained
as observations but cannot be summed into simultaneous capacity.

### 3. Make delivery evidence and failure states typed

The domain owns small types for:

- requested delivery bindings;
- per-arm endpoint observation state;
- per-binding differential outcome;
- qualification lifecycle and restoration state;
- the exact authorized delivery scope.

Models describe data. Validation stays in a domain service and returns the
repository's `ValidationResult`; Pydantic models do not become policy owners.
The application service orchestrates the request and fail-closed transitions.
Infrastructure owns Packet Tracer scripts and registered endpoint observers.
Persistence continues to use `CapabilityProbeResult`, `CapabilityEvidence`,
`CapabilitySnapshotStore`, and reviewed measured-capability records rather
than adding another evidence store.

`FAILED`, `UNOBSERVABLE`, and `UNKNOWN` remain distinct:

- lifecycle or execution failure is `FAILED`/probe execution failure;
- an absent observation channel is `UNOBSERVABLE`;
- incomplete or non-discriminating evidence has capability status `UNKNOWN`;
- only complete discriminating evidence may become `SUPPORTED`.

`APPLIED` setup actions never imply `VERIFIED` delivery.

### 4. Persist canonical exact scope, not just counts

The PoE claim dimensions use canonical JSON strings for structured values.
They preserve:

- observed access-port names;
- tested candidate/control binding pairs;
- candidate-active binding triples `(switch_port, endpoint_model,
  endpoint_port)`;
- the simultaneous candidate-active count;
- control-arm outcome;
- observation method and endpoint-observer identity.

The active binding triples are the primitive authorization data. Counts are
derived from and checked against those triples. Non-canonical JSON, duplicate
bindings, malformed fields, count/list disagreement, active bindings outside
the tested scope, or missing endpoint identity cap the claim at `UNKNOWN`.

`MeasuredCapabilityRecord` gains immutable dimensions and copies them into
`CapabilityEvidence`. Existing records default to an empty mapping, preserving
their current behavior. A future positive PoE measured record without the full
new scope remains `UNKNOWN`; old or incomplete snapshots therefore continue
to fail closed.

### 5. Authorize exact port-and-endpoint bindings

`DeviceCapabilities` receives a typed collection of authorized PoE binding
triples in addition to `poe_ports`. The resolver projects both values only
from the same winning evidence after the central PoE claim-ceiling parser has
validated it. Provenance is therefore not selected independently from the
scope it authorizes.

`EndpointPortBinding` records the endpoint model. Governed physical designs
must populate it for powered endpoints. The reference planner admits a
powered endpoint only when all of these match the evidence:

- selected switch model and Packet Tracer build;
- exact switch port;
- exact powered endpoint model;
- exact powered endpoint port.

The number of simultaneously demanded powered bindings on a selected device
must not exceed the simultaneous capacity carried by the same evidence. A
partial measurement may authorize only its exact active triples. It cannot
authorize another port, another endpoint model, another endpoint port, or a
larger concurrent group. Where equivalence is not demonstrated, the planner
returns `NEEDS_VERIFICATION` and the hardware plan remains
`PARTIALLY_RESOLVED`.

### 6. Govern the live lifecycle fail-closed

The application qualifier uses one fresh, isolated qualification session. It
captures an initial semantic inventory fingerprint, records every attempted
temporary identity and link, and always executes cleanup in `finally`. It
then waits through the repository's bounded convergence mechanism for a final
fingerprint and classifies restoration explicitly.

Positive reuse requires:

- exact requested/observed model identities for both switch arms and every
  powered endpoint;
- exact requested/observed links;
- complete differential observations;
- all claimed active endpoints observed simultaneously;
- every temporary device removed or proven absent;
- final semantic inventory equal to the initial inventory;
- cleanup status `CLEAN` and restoration `RESTORED`.

Any incomplete cleanup or unknown restoration invalidates the entire PoE
qualification result. No arbitrary sleep, retry-until-green, skip, or xfail is
introduced. Polling is bounded and uses injectable clock/sleeper seams in
tests.

### 7. Separate LIVE history from the current offline gate

`docs/reference/cp-scale/current_state.json` moves to a schema that explicitly
contains both `last_live_state` and `current_offline_operational_gate`.
Historical LIVE source head, latest run, counts, hashes, artifacts, and prior
stage evidence remain unchanged.

The offline gate is bound to the product implementation commit that precedes
the governance commit and records:

- PoE delivery `UNKNOWN`;
- `poe_ports = null`;
- `HardwarePlan = PARTIALLY_RESOLVED`;
- canonical composition blocked before topology;
- Router0 not authorized;
- next action
  `RUN_ONE_GOVERNED_POE_DELIVERY_QUALIFICATION_FROM_CLEAN_GREEN_HEAD`.

The compatibility projection updates the current status and next step without
rewriting the last LIVE facts.

## Component boundaries

The planned file responsibilities are:

- `domain/enterprise/models/poe_delivery.py`: immutable typed request,
  observation, outcome, scope, and lifecycle data.
- `domain/enterprise/services/poe_claims.py`: canonical dimension encoding,
  parsing, coherence checks, and claim ceiling.
- `application/use_cases/qualify_poe_delivery.py`: qualification orchestration,
  differential decision, simultaneous observation boundary, and cleanup.
- `infrastructure/execution/probe_runtime.py`: Packet Tracer fixture operations
  using only repository-confirmed APIs; it does not decide visible power.
- `infrastructure/execution/manual_poe_delivery_observer.py`: a narrow injected
  callback adapter that records typed, attributed visible-power judgments for
  a governed runner without embedding policy in the MCP registry.
- `domain/enterprise/models/capabilities.py` and
  `domain/enterprise/services/capability_resolver.py`: projection of one
  winning claim into count plus exact authorized scope.
- `domain/enterprise/models/hardware.py`, the governed CP-SCALE physical
  design, and `reference_hardware_planner.py`: exact endpoint-model binding and
  admission enforcement.
- `infrastructure/catalog/measured_capabilities.py`: lossless dimensions in
  reviewed portable records.
- a thin MCP registration only if needed to expose the new application use
  case; business logic must not be added to `tool_registry.py`.
- focused tests divided by domain ceiling, application lifecycle, runtime
  rendering/parsing, persistence, resolver projection, planner authorization,
  and current-state governance.

Dependencies point inward: infrastructure implements application protocols;
application orchestrates domain types and services; domain does not import
Packet Tracer or MCP adapters. Existing evidence storage remains the single
reusable evidence path.

## Causal tests

Tests must demonstrate failures without the implementation and cover at least:

1. `poe-inventory` v3 still cannot emit positive delivery from control getters.
2. Candidate-powered/comparison-not-powered exact manual observations can
   produce a scoped positive result in a fake runtime.
3. Candidate-powered/comparison-powered, missing comparison, unattributed or
   incomplete manual input, unreadable endpoint,
   identity mismatch, link mismatch, partial simultaneous observation, cleanup
   failure, or restoration uncertainty remain non-authorizing.
4. Sequential per-port success cannot inflate simultaneous capacity.
5. Dimensions round-trip through `CapabilityProbeResult`,
   `CapabilityEvidence`, snapshots, and `MeasuredCapabilityRecord`.
6. Missing, malformed, duplicate, non-canonical, or incoherent dimensions cap
   old and new positive claims at `UNKNOWN`.
7. Evidence for one switch port cannot authorize another.
8. Evidence for a 7960 cannot authorize an `AccessPoint-PT`, and endpoint-port
   mismatches cannot authorize.
9. A fully covered exact binding set can pass the planner while a partially
   covered set yields `PARTIALLY_RESOLVED` before topology.
10. The checked-in baseline remains `UNKNOWN` / `poe_ports=None`.
11. Governed state preserves every historical LIVE field and projects the new
    offline PoE gate and next action.

## Validation and publication

Implementation follows characterization/TDD, then focused tests, affected
tests, the checkout-local `.venv` full pytest suite, production import and
single-namespace checks, `git diff --check`, and `graphify update .` when code
dependencies change. A fresh independent review inspects the coherent final
diff after deterministic gates. Accepted material findings trigger correction,
rerun gates, and a fresh re-review.

The product changes are committed first. Governance and the existing
`handoff_github_corrections.md` are then committed with the product commit SHA
as the offline gate's non-self-referential implementation head. Only
`cisco/feature/runtime-ripv2` is pushed. GitHub Actions must be 4/4 green for
the exact final SHA. No Packet Tracer LIVE or Router0 CP-LIVE is run.

## Rejected alternatives

- Promoting homogeneous `getPower()`/`isPowerOn()` state: it measures control,
  not delivery.
- Treating endpoint creation, link presence, SVI presence, DHCP state, or
  registration alone as delivery: none is independently attributable to PoE.
- Treating another model as a negative control from its name or control getters:
  the negative arm must itself carry a visible not-powered observation.
- Summing sequential port observations into capacity: it exceeds evidence.
- Authorizing an entire model's access range from sampled ports: equivalence
  is unproven.
- Letting phone evidence authorize APs: powered endpoint equivalence is
  unproven.
- Adding a parallel PoE evidence store or embedding policy in the MCP hotspot:
  both weaken analyzability and provenance control without adding evidence.
