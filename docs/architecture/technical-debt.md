# Technical Debt Ledger

This document tracks confirmed technical debt and contained backend
limitations that remain relevant to the MCP-Packet-Tracer architecture.

It is not a generic TODO list.

Every OPEN debt item must have:

- an identifier;
- severity;
- current status;
- evidence/reason;
- what it blocks;
- a mandatory RESOLVE_BEFORE milestone;
- an explicit closure criterion.

A debt item may be deferred only when it does not invalidate a correctness
gate required by the current milestone.

"Backlog someday" is not an acceptable disposition.

## Severity

### P0

Current correctness/safety blocker.

P0 debt must be resolved before continuing the affected milestone.

### P1

Correctness, evidence, runtime, or architectural debt that can be temporarily
contained but must be resolved before its declared milestone.

### P2

Non-critical contained debt with a mandatory future resolution milestone.

### BACKEND_LIMITATION

A limitation caused by Packet Tracer or the deployed bridge/backend that may
not be removable with the currently available primitives.

Closure does not necessarily require eliminating the limitation.

It requires:

- accurate classification;
- safe containment;
- no false claims;
- an explicit architectural boundary.

## Status

- OPEN
- CONTAINED
- BACKEND_LIMITATION
- RESOLVED
- DEFERRED_TO_DECLARED_MILESTONE

## Debt policy

When new debt is discovered:

1. Determine whether it invalidates a correctness gate of the current task.
2. If yes, it blocks the task.
3. If no, record it with a mandatory resolution milestone.
4. Do not expand the current task solely because unrelated debt exists.
5. Revisit debts at the mandatory checkpoints defined below.

A debt item must never lose its RESOLVE_BEFORE milestone merely because later
work is more interesting.

---

# Mandatory Debt Checkpoints

## DEBT CHECKPOINT 1

When:

After typed RIPv2 is implemented and verified.

Purpose:

Review runtime, transport, routing, evidence, and control-plane debt before
the university topology becomes an acceptance scenario.

## DEBT CHECKPOINT 2

When:

**Corrected at Debt Checkpoint 2, 2026-08-12.** The original wording was:

> After the university topology passes its routing/failure/recovery acceptance
> scenario and before returning to E9.5 Stage 3A4.

That sentence encoded a prerequisite that was never satisfied, and leaving it
would have recorded a failure/recovery scenario as having occurred when none
did. The University Topology Acceptance had eleven gates — workspace safety,
physical topology, link readback, addressing, local connectivity, capability,
typed application, configuration readback, route convergence, forwarding, final
state — and **no failure gate and no recovery gate**. Its contract never
proposed one. The routing half of the trigger was met; the failure/recovery
half was not, and was not attempted.

The corrected trigger, which is the sequence the project actually follows:

```text
CP1 → University Topology Acceptance → CP2 → Stage 3A4
```

CP2 occurs after the University Topology Acceptance completes and before Stage
3A4 begins. **Failure/recovery is not a CP2 prerequisite and was not satisfied
by CP2.** It remains E9 scope — `enterprise-control-plane.md` places bounded
failover execution and mandatory restore there — and its live status remains
UNKNOWN in `docs/qa/e95-runtime-debt.md`, registered as
`PENDING_ROOT_CAUSE_AND_LIVE_FAILOVER` and
`PENDING_LIVE_RESTORE_AND_RECOVERY`. Nothing in this checkpoint advanced it,
and no later milestone may treat it as discharged here.

Purpose:

Resolve or deliberately reschedule newly exposed runtime/control-plane debt.

## DEBT CHECKPOINT 3 — HARD

When:

Before declaring E9.5 CLOSED.

Requirements:

- P0 open debt: 0
- P1 correctness/evidence debt that affects E9.5 claims: 0
- UNKNOWN states that invalidate final E9.5 claims: 0
- debt that blocks E10: 0

A backend limitation may remain only when its containment and claim ceiling
are explicit.

---

# Debt Checkpoint 2 — result, 2026-08-12

```text
DEBT_CHECKPOINT_2      = CLOSED
STAGE_3A4_PREREQUISITE = READY
NEXT                   = STAGE_3A4_TRAFFIC_REFERENCE_TOPOLOGY
```

Ran on `feature/runtime-ripv2` after University Topology Acceptance and before
Stage 3A4. Dependency map: `e95-stage-3a4-readiness.md`.

**Entry inventory:** six carried entries — TD-RUNTIME-006, TD-HARDWARE-001,
TD-SECURITY-001, TD-VOICE-001, TD-PUBLIC-001, TD-TRANSPORT-001 — plus
TD-ACCEPTANCE-001 opened by this checkpoint.

**Debts blocking Stage 3A4 start: none.** Each was verified against source, not
against its own prose. The reasoning per entry is recorded in that entry's
CP2 verification subsection and summarised in the readiness map.

**Deadline moved: one.** TD-ACCEPTANCE-001 resolves before **Stage 3A4
closure**, earlier than the E9.5 deadline it would otherwise inherit, because
3A4 is the first milestone whose definition requires the production
physical/configuration pipeline to work. No other `RESOLVE_BEFORE` was touched.

**No debt was promoted for being ugly, and none was deferred for being
inconvenient.** Severity changed on nothing. TD-RUNTIME-006 gained two further
unreachable orderings and stayed P2, because four unreachable orderings are no
more reachable than two.

**What this checkpoint corrected rather than closed.** Five entries described
code accurately but incompletely, and the corrections are the substance of CP2:

- TD-RUNTIME-006 — wrong file cited, two of four orderings enumerated, and the
  stated reason for unreachability wrong for `deploy_enterprise_topology.py`;
- TD-HARDWARE-001 — the "3650 has multilayer runtime evidence" claim has **no
  support anywhere in this repository** and must not be assumed at closure;
- TD-SECURITY-001 — the typed security renderer and the NAT generator inherit
  the additive ACL body verbatim, so the eventual live reproduction is wider
  than "the normal ACL generator";
- TD-VOICE-001 — containment is currently stronger than recorded, because no
  voice capability catalog exists at all; and the action model declares
  `REPLACE` for behaviour this entry classifies as UNKNOWN;
- TD-TRANSPORT-001 — containment is understated; Python-side request retirement
  narrows the re-evaluation window and was not listed.

Also corrected: the Documentation limitation section, which asserted no
University Topology Acceptance specification existed after one had been
committed; and TD-RUNTIME-005's resolution, which was written before its
compiled expectations had ever run against three routers.

**Source changed: none.** This checkpoint is documentation and governance only,
and `src/` is byte-identical to the University Acceptance commit.

An earlier revision of CP2 deleted a stranded `def evidence_for(self, ...)`
nested inside the module-level `_snapshot_evidence` generator in
`capability_providers.py`. That deletion was **reverted**: on inspection it
fixed no correctness or evidence defect. The nested function was never
executed as a method and never referenced, so removing it changed no behaviour;
the justification offered for it — that a future reader might "repair" it by
un-indenting and blank out every provider's evidence — was a speculative
hazard, not an observed defect. Incidental cleanup does not belong on a
checkpoint line, where it would blur what the checkpoint is accountable for.

The observation itself is kept, under `TD-HARDWARE-001`, whose evidence path
that file sits in. Suite unchanged at 1716 passing.

**Governance discrepancy, now corrected in the definition itself.** This
checkpoint's trigger originally read *"after the university topology passes its
routing/failure/recovery acceptance scenario"*. The executed acceptance had
eleven gates and no failure or recovery gate, so half that trigger was never
satisfied. The DEBT CHECKPOINT 2 definition above has been rewritten to state
the sequence the project actually follows — CP1 → University Topology
Acceptance → CP2 → Stage 3A4 — with the original wording preserved verbatim and
an explicit statement that failure/recovery is **not** a CP2 prerequisite and
was **not** discharged here. It remains E9 scope and UNKNOWN in
`docs/qa/e95-runtime-debt.md`.

**Not done, deliberately:** no live Packet Tracer probe was run. Every closure
criterion touched at this checkpoint was satisfiable from persisted evidence,
and rerunning the acceptance to improve wording was explicitly out of scope.

---

# Documentation limitation

**As written at Debt Checkpoint 1, verbatim, and true then:**

> There is no formal specification of **University Topology Acceptance** anywhere
> in `docs/`. Debt maturity at Debt Checkpoint 1 was therefore classified from
> each entry's own governed `RESOLVE_BEFORE` field, which is the authority this
> ledger defines, and not from an assumed acceptance scope. Writing that
> specification is future work; nothing in this checkpoint invented one.

**Superseded at Debt Checkpoint 2 (2026-08-12).**
`docs/architecture/university-topology-acceptance.md` now exists, committed at
`79bc1e6`, and carries a contract — topology, expected RIPv2, expected learned
routes, eleven named gates, PASS/PARTIAL/BLOCKED/FAIL definitions, and a
persistence/cleanup rule — followed by the executed result. The paragraph above
is kept because it was the honest state at CP1, not deleted to make the ledger
look tidier.

The narrower limitation that remains: that contract was written **for** its own
run rather than as a standing definition, so it governs one acceptance and not
the next one. CP2 treats it as a precedent to imitate, not as a general
standard.

---

# Open Debt

## TD-ACCEPTANCE-001 — The physical/configuration product pipeline has never been live-accepted

Status:
OPEN

Severity:
P1

Discovered:
Debt Checkpoint 2, claim-scope audit of the University Topology Acceptance

Description:

The University Topology Acceptance built a 41-device, 41-link topology live on
PT 9.0.1.0858 and it worked. It was built by an **uncommitted developer
harness**, not by the product.

Traced from the harness source rather than inferred from the successful result
(the four modules survive only in the executing session's scratchpad; the
durable record is the "Claim scope" table in
`university-topology-acceptance.md`):

- devices came from `PacketTracerBridgeProbeRuntime.create_temporary_device`,
  which is capability-probe scaffolding, not `deploy_enterprise_topology`;
- links and modules came from raw JS `lwAddLink` / `addModule` over
  `FileBridge`, bypassing `packet_tracer_physical_runtime`, whose
  `ensure_device` / `ensure_link` / `observe_link` exist precisely for this and
  whose module is documented as "the backend-neutral production seam for
  physical deployment";
- all nine router L3 interfaces, the three switch SVIs and every `clock rate`
  came from hand-written IOS through `configure_ios`, bypassing
  `compile_configuration` → `configuration_renderer` → `apply_configuration`;
- the 35 PC addresses came from raw JS `configurePcIp`.

What *was* product path: the typed RIPv2 chain end to end, the
`ControlledIosExecutor` registered queries, and `TypedPingExecutor`.

So the acceptance is sound for what it was chartered to accept — the typed
control plane — and unsound as evidence that the product can build this
topology. At debt discovery, `deploy_enterprise_topology` and
`packet_tracer_physical_runtime` had **no recorded live execution anywhere in
`docs/`**. Slice 2A later added bounded physical/module/link evidence; it did
not execute the complete reference pipeline and therefore does not close this
entry.

Consequence, already recorded in the acceptance document:

```text
REFERENCE_TOPOLOGY_BEHAVIOR                        = PASS
TYPED_RIPV2_PRODUCT_APPLICATION                    = PASS
TYPED_RIPV2_PRODUCT_READBACK                       = PASS
TYPED_RIPV2_ROUTE_LEARNING                         = PASS
TYPED_RIPV2_FORWARDING                             = PASS
CONTROL_PLANE_FOUNDATIONAL_REQUIREMENT_INTEGRATION = NOT_ESTABLISHED
FULL_PRODUCT_PIPELINE_ACCEPTANCE                   = NOT_ESTABLISHED
```

`CONTROL_PLANE_FOUNDATIONAL_REQUIREMENT_INTEGRATION` is the line this entry
most directly owns. `ControlPlaneApplicator` gates every action on the
configuration it depends on having been verified, and the harness satisfied
that gate by declaring every requirement VERIFIED in a comprehension over the
gate's own inputs, with no hashes. The gate is real product code; on this run
it decided nothing.

Classification:
```text
STAGE_3A4_SCOPE
```

Blocks Stage 3A4 **start**:
**No.** This is not a prerequisite that must exist before the phase begins — it
is a substantial part of what the phase is for. Stage 3A4 is the governed phase
in which the reference topology and the traffic path are exercised end to end
through production seams, so "the reference topology has not yet been exercised
through the complete production physical/configuration pipeline" describes
3A4's own work, not an obstacle to starting it.

Nothing in repository governance and no architectural dependency requires the
pipeline to be proven before 3A4 opens. The seams already exist
(`deploy_enterprise_topology`, `packet_tracer_physical_runtime`,
`compile_configuration` → `configuration_renderer` → `apply_configuration`);
what is missing is an executed run through them, which is exactly a 3A4
deliverable.

Blocks claims of:
any statement that the product can deploy and configure a topology of this
scale, and any E9.5 closure claim that rests on one. That ceiling holds for the
whole of Stage 3A4 until the run exists.

RESOLVE_BEFORE:
**Stage 3A4 closure.** Not E9.5 closure and not CP3 — bringing the deadline
forward is deliberate, because 3A4 is the first milestone whose own definition
requires this path to work, and deferring it to CP3 would let 3A4 close on the
same harness-shaped evidence this entry exists to reject.

Closure criterion:

One live run of the Stage 3A4 reference topology in which **every bypass the
University Acceptance harness used is eliminated**. The criterion is written as
a one-to-one answer to what that harness actually did, so closure cannot be
claimed while any single substitution survives.

| # | Harness bypass | What closure requires |
| --- | --- | --- |
| 1 | devices via `create_temporary_device`, links and modules via raw JS `lwAddLink` / `addModule` | **Production physical deployment** through `deploy_enterprise_topology` / `packet_tracer_physical_runtime`, with the deployment manifest emitted from fresh exact read-back as that use case already requires |
| 2 | serial links placed by raw JS because no product path expresses them | **Serial topology support in the product.** `CABLE_RULES` has no rule yielding `serial`, so the reference cannot currently express a serial link at all. This is the narrow missing capability referred to below, and the reference must carry serial for a traffic-driven capacity decision to be demonstrable |
| 3 | nine router interfaces, three SVIs and `clock rate` by hand-written IOS through `configure_ios`; 35 PC addresses by raw JS `configurePcIp` | **Production configuration and addressing** through `compile_configuration` → `configuration_renderer` → `apply_configuration`, including host addressing |
| 4 | `foundational_statuses` supplied as a comprehension declaring every requirement VERIFIED, `foundational_hashes={}` | **Authentic foundational-requirement evidence.** Statuses and hashes must be produced by `apply_configuration` from real readback, so `ControlPlaneApplicator`'s gate decides on evidence instead of on an assertion |
| 5 | — (this one the harness did correctly) | **Typed control plane** through `compile_control_plane` → `ControlPlaneApplicator.apply` → `PacketTracerEnterpriseControlPlaneRuntime`, with capability resolution left to the product. Retained explicitly so a future run cannot regress the one part that was already right |
| 6 | workspace and link readback reimplemented in raw JS, which is where the `getOwnerDevice()` defect lived | **Authoritative readback and traffic evidence** through `topology_observation.py`, registered `OperationalQueryId` queries, and the typed traffic/ping primitives — never a parallel reimplementation |

Scale may be smaller than 41 devices: the claim to establish is that the seams
work, not that they scale. It must include at least one multi-device link, one
routed interface, and — because of row 2 — at least one serial link.

Three rules decide whether this closes or merely repeats:

- a harness may **orchestrate** the run; it may not **perform** the mutations.
  The University Acceptance harness stays useful as a behavioural reference and
  must not become the implementation path;
- a missing product capability may not be worked around with raw JS or raw IOS
  to make the run succeed. If a seam is genuinely absent — row 2 is the known
  case — the narrow missing capability is named and either implemented as Stage
  3A4 work or opened as governed debt with its own deadline;
- the claim recorded at closure must name which of the seven acceptance lines
  it upgrades. In particular
  `CONTROL_PLANE_FOUNDATIONAL_REQUIREMENT_INTEGRATION` and
  `FULL_PRODUCT_PIPELINE_ACCEPTANCE` may move off `NOT_ESTABLISHED` only when
  rows 1–4 and row 6 are all satisfied in the same run.

### Progress — Stage 3A4, 2026-08-13

Row-by-row, from source audit and one implemented slice. Details in
`e95-stage-3a4-readiness.md`.

| Row | State |
| --- | --- |
| 1 physical deployment | **Bounded product slice VERIFIED; reference run pending.** Slice 2A deployed `2×2911 + requested module effects + 1 serial WAN` through `EnterprisePhysicalTopologyDeployer` / `PacketTracerPhysicalTopologyRuntime`, emitted a fresh-readback manifest, and restored the workspace. This advances row 1 but does not satisfy its same-run 41-device closure criterion. Evidence: `stage-3a4-serial-product-slice-2a.md`. |
| 2 serial support | **Physical serial product capability VERIFIED for 2911/HWIC-2T; reference run pending.** The adapter now inserts once, independently verifies fresh `Serial0/0/0` and `Serial0/0/1` effects, preserves exact module identity as `UNOBSERVABLE`, and deploys one exact serial WAN. Serial IOS/orientation and the full reference execution remain outside Slice 2A. |
| 3 configuration and addressing | **Better than this entry assumed.** Host addressing is already fully typed — `SetEndpointStaticAddress` → a seven-argument `configurePcIp`, a superset of the harness call. Router L3 and `clock rate` are supported. The one real gap is a compiler path emitting `ConfigureSvi` for a **non-gateway** switch management address; the action type and renderer already exist. |
| 4 foundational evidence | **Implemented.** `application/use_cases/foundational_evidence.py` derives statuses from executed results only, with no parameter through which a status could be supplied. Thirty-five regressions, including a drift check against the real gate. Row 4 is satisfied *as a capability*; it is not yet *exercised*, which needs rows 1–3. |
| 5 typed control plane | Unchanged and already correct. |
| 6 authoritative readback | **Physical portion VERIFIED on the bounded slice.** Production exact two-ended readback observed both serial endpoints and their shared runtime UUID; the manifest binding was derived from those observations. Registered query and traffic evidence for the closing reference run remain pending. |

`TD-ACCEPTANCE-001` remains `OPEN`. Its closure criterion requires rows 1–4
and 6 in the same reference-topology run; Slice 2A intentionally performed no
configuration, foundational-evidence composition, control-plane work, or
traffic.

### Progress — Stage 3A4 Slice 2B/3, 2026-08-17

Offline only. **No live Packet Tracer run was performed**, so no row moves to
satisfied. Full record: `stage-3a4-serial-product-slice-2b.md`.

| Row | Change |
| --- | --- |
| 2 serial support | **Orientation resolved as a capability.** Slice 2A left `SERIAL_ENDPOINT_ORIENTATION = UNRESOLVED`. `SerialOrientationObserver` now derives DCE/DTE from one registered read-only `show controllers` per bound endpoint, failing closed on stale, truncated, mismatched-interface or wrong-physical-hash evidence, and never mutating E4. Not exercised live. |
| 3 configuration and addressing | **Serial transit addressing and clock now compile.** Deterministic /30s per site pair, materialised on both ends; the clock is emitted only from an observed manifest binding, never from planning metadata, because the cable decides which end may carry it. `apply_configuration` revalidates every serial-clock target against the manifest before dispatch. |
| 6 authoritative readback | **Traffic evidence becomes expressible.** `CapacitySource.TRAFFIC_CALCULATION` was unreachable in production; typed `TrafficFlowIntent` plus `attribute_enterprise_traffic` now attribute demand to the links a flow actually crosses. RIPv2 compiles one reachability expectation per declared flow, gated on the route to that flow's own destination prefix. Still no registered-query or traffic evidence from a live run. |

Two ceilings this slice adds to the closing run, both narrowing what a future
claim may say:

- **Flow attribution is RIPv2-only.** OSPF and EIGRP keep their router
  cross-product. A generic implementation was written and removed because no
  fixture exercises it. This is a **scope boundary, not an open blocker**: the
  governed Stage 3A4 reference topology is RIPv2, so RIPv2-only attribution is
  sufficient to close it. Generic other-IGP attribution falls outside this
  reference closure unless a governed E9.5 claim explicitly requires it, and no
  such claim exists. A closing run on any other IGP would simply not have
  flow-attributed behaviour.
- **A verified route is not forwarding evidence.** `ROUTE_PRESENT` and
  `END_TO_END_REACHABILITY` keep disjoint capability dimensions, and the flow
  prerequisite orders evidence rather than substituting for it. No closure claim
  may treat a satisfied route prerequisite as reachability.

New ceiling discovered while implementing row 4, and it constrains the closing
run: **`endpoint_address`, `access_port` and `dhcp_pool` foundations can never
reach VERIFIED** on this backend. Endpoint verification reads IP and mask but
returns `gateway: null` and `dns: null`, so it resolves PARTIAL; the other two
route to `_unobservable` unconditionally. A closing run must therefore compile
only `l3_interface` and `link` foundations — which a RIPv2 reference topology
does — or it will fail a gate that no amount of correct execution can satisfy.

---

## Claim ceiling — OSPF control-plane observation, 2026-08-17

Not a debt entry: a recorded ceiling, so no later milestone can quietly exceed
it. Established from source at Stage 3A4 Slice 2B/3 (`8b7d77c`).

**What OSPF observation can establish:**

| Query | Establishes | Does NOT establish |
| --- | --- | --- |
| `show ip ospf neighbor` (`enterprise_control_plane_runtime.py:1207`) | the OSPF process is operating (`protocol`) | the local **`router_id`** — it is absent from this SHOW, and the observer says so in its own message |
| `show ip route ospf` (`ios_terminal.py:743`) | `network`, `prefix_length`, `next_hop`, `outgoing_interface` | the **`wildcard`** and the semantic **`segment_id`** — neither appears in the output |

Those three fields were therefore removed from what OSPF expectations *claim*.

**The trap that removal opened, and how it is closed.**
`_unobservable_fields` builds its field map from `expected`, and
`_direct_observation` (`:1413`) returns VERIFIED only when every field is
VERIFIED. Deleting the unmeetable fields therefore flipped OSPF
`ROUTING_PROCESS` and `ROUTE_PRESENT` from UNOBSERVABLE to **VERIFIED without
observing anything new**, and `apply_control_plane.py:378/381` aggregates those
into a run's `observed_status`.

`ControlPlaneVerificationExpectation.unclaimed_fields` now records what an
expectation deliberately does not claim, and the observer renders those fields
UNOBSERVABLE exactly as if they were still in `expected`.

```text
OSPF_ROUTER_ID          = UNOBSERVABLE / DECLARED_UNCLAIMED
OSPF_ROUTE_WILDCARD     = UNOBSERVABLE / DECLARED_UNCLAIMED
OSPF_ROUTE_SEGMENT_ID   = UNOBSERVABLE / DECLARED_UNCLAIMED
OSPF_PROCESS_AGGREGATE  = UNOBSERVABLE   # unchanged by the narrowing
OSPF_ROUTE_AGGREGATE    = UNOBSERVABLE   # unchanged by the narrowing
```

**The rule this establishes, which outlives OSPF:** narrowing what an
expectation claims may never raise what an observation concludes. If an
aggregate status improves, it must be because something new was observed — never
because an unmeetable field was deleted. Regressions in
`test_enterprise_control_plane_runtime.py` pin exactly that, including that
route evidence never stands in for forwarding evidence and that nothing here
implies failure or recovery state.

RIPv2 expectations are untouched and keep all three fields.

---

## TD-RUNTIME-007 — Route expectations have no convergence window

Status:
RESOLVED

Severity:
P1

Discovered:
Debt Checkpoint 1, independent review of the TD-RUNTIME-005 integration

Description:

`ControlPlaneApplicator.verify` is single-shot. `_observe_rip_route` performs
one registered read and decides, and `ROUTE_PRESENT` belongs to
`_OBSERVED_KINDS`, so a FAILED observation drives the whole application result
to `PARTIAL` / `VERIFICATION_FAILED`.

RIP advertises on a 30-second update timer. A correct deployment verified
immediately after application therefore reports FAILED for a route that simply
has not arrived yet, and the failure is indistinguishable from a route that will
never arrive.

The R2-B phase 4 evidence hid this: the operator harness slept 35 seconds before
reading, and observed route ages of `00:00:26` and `00:00:00`. Nothing in the
product reproduces that wait.

Blocks now:
**Yes.** University-topology acceptance applies RIPv2 and verifies it in the
same run. Without a convergence window the acceptance would report failure for
a working network, which is worse than no verification: it produces a false
negative that an operator would reasonably act on.

RESOLVE_BEFORE:
university-topology acceptance.

Closure criterion:

Route verification retries the **read only**, within an explicit bounded budget,
and never redispatches configuration. A route that appears within the budget
verifies; a route absent at the end of the budget FAILS; stale or truncated
evidence remains UNOBSERVABLE rather than consuming the budget or being reported
as failure. Every sample must still require the exact prefix, prefix length and
RIP source.

### Resolution

Resolved: 2026-08-12, stage "Debt Checkpoint 1".

Commit subject:
`fix: bound RIP route verification with a convergence window`
on `feature/runtime-ripv2`.

`_observe_rip_route` now reads inside a bounded window. Defaults are 45 s,
sampled every 5 s, capped at 10 reads. The budget is derived from measurement,
not taste: RIP advertises on a 30-second timer, and the R2-B phase 4 evidence
showed both routes present after a 35-second wait with ages `00:00:26` and
`00:00:00`. One full update cycle plus margin.

What the window does and does not do:

- it retries the **registered read only**. No configuration is redispatched,
  and a regression asserts the mutation channel stays silent for the whole
  window while only `SHOW_IP_ROUTE_RIP` is issued;
- stale evidence and a pager-truncated table **abort immediately** rather than
  consuming the budget. Neither improves by waiting, and spending the window on
  them would disguise an unobservable read as a failure;
- the comparison never relaxes. Every sample still requires the exact prefix,
  prefix length and RIP source, proven for a wrong length, a wrong network, a
  mismatched pair, and an OSPF row carrying the right prefix;
- the per-device query cache is invalidated between samples, since a cached
  read cannot converge.

The result carries a `ConvergenceReport` with the attempt count and the last
observable state, matching how stable ping probes already report.

Evidence: a route absent on the first two reads and present on the third
VERIFIES in three reads; a route that never appears FAILS after exactly the
budgeted reads and says so without claiming anything was redispatched.

One thing this exposed, worth recording: the earlier route tests inherited the
real budget and slept through it, taking the module from 0.5 s to 200 s. They
now inject a single attempt, because they are about comparison semantics rather
than convergence, which has its own tests with a deterministic clock.

---

## TD-RUNTIME-006 — Two unreachable journal lifecycle transitions

Status:
OPEN

Severity:
P2

Discovered:
Debt Checkpoint 1, independent review of the TD-RUNTIME-001 fix

Description:

Two orderings on `ApplicationExecutionJournal` can produce a state that
contradicts a recorded cleanup verdict. Neither is reachable through any
current applicator, and both were found by reading the model rather than by
observing a failure.

1. `append` after `mark_cleanup`. `append` recomputes `dirty_state` from the
   entries and does not consult `cleanup_status`. A journal that recorded
   `mark_cleanup(FAILED)` — final state `DIRTY_UNRECOVERABLE` — and then
   appended a benign entry recomputes to `CLEAN` while `cleanup_status` remains
   `FAILED`.

2. `mark_preflight_failure` after `mark_cleanup`. It forces `CLEAN` whenever
   `entries` is empty, regardless of any cleanup verdict already recorded.

Why unreachable today: every applicator builds its journal from action results,
appends all entries, and only then records cleanup; the failure paths construct
a fresh journal. So no production sequence appends or marks preflight after a
cleanup transition.

Blocks now:
No. Not reachable through any current applicator, and the model is documented
as the authority for final state, so the risk is to future callers rather than
to present behaviour.

RESOLVE_BEFORE:
Diagnosis/Autofix work, which is the first consumer expected to drive a journal
through transitions the applicators do not currently produce, and at latest
E9.5 final closure.

Closure criterion:

Either the journal refuses these orderings explicitly, or the composition
accounts for a recorded cleanup verdict so a later `append` or preflight marker
cannot contradict it. A regression must cover both sequences.

### Correction — Debt Checkpoint 2, 2026-08-12

The entry above under-counts the problem and gives the wrong reason for the
conclusion. The conclusion itself survives. Corrected here rather than rewritten
above, so the original claim stays visible.

**The model lives in `domain/enterprise/models/execution.py:81`**, not in
`configuration_runtime.py`, which only holds a field reference.

**Four orderings exist, not two.** `record_scenario_restore`
(`execution.py:155`) writes `dirty_state` by the same mechanism as
`mark_cleanup` — `FAILED` → `DIRTY_UNRECOVERABLE`, `UNKNOWN` → `UNKNOWN` — so
it is exposed to exactly the same two successors:

3. `append` after `record_scenario_restore(FAILED)` recomputes to `CLEAN` while
   `cleanup_status` stays `FAILED`;
4. `mark_preflight_failure` after `record_scenario_restore(FAILED)` forces
   `CLEAN` on empty entries.

This matters for attribution: `record_scenario_restore` was introduced in
`fix: keep scenario restore from clearing application dirtiness`, which
*precedes* the commit that wrote this debt. The method was in front of the
author and was not enumerated. The closure criterion's "a regression must cover
both sequences" therefore under-specifies the fix by two.

**`mark_transport_unknown` (`execution.py:124`) has no caller at all** — not in
`src/`, not in `tests/`. It sets `dirty_state = UNKNOWN` and is subject to the
same `append` overwrite. It is dead code today, so it adds no present risk, but
a future caller would inherit the defect silently. Closure should either delete
it or bring it under the same composition rule.

**The stated reason is wrong for one applicator.** The entry says "every
applicator builds its journal from action results, appends all entries, and
only then records cleanup". `deploy_enterprise_topology.py` does not: it
constructs a bare journal and appends incrementally through the device and
module loops. The orderings are still unreachable there, but for a different
reason — that applicator never calls `mark_cleanup` or
`record_scenario_restore` at all, and both its `mark_preflight_failure` calls
sit in early-return preflight blocks that run before the first append.

**Disposition unchanged: OPEN, P2, does not block Stage 3A4.** Verified by
complete caller inventory — `mark_cleanup` is called only from
`apply_security.py`, `record_scenario_restore` only from the
`_record_scenario_restore` helper in `apply_control_plane.py`, and every
`mark_preflight_failure` site either follows an empty-results journal
construction or precedes any append. Stage 3A4 drives the same applicators, so
it cannot reach these orderings either. The severity is not raised: four
unreachable orderings are no more reachable than two.

---

## TD-RUNTIME-005 — RIP route learning is observable but not a compiled expectation

Status:
RESOLVED

Severity:
P2

Discovered:
Runtime R2-B phase 4 (live route learning and forwarding)

Description:

R2-B phase 4 added the production read-back for learned RIP routes: the
registered query `SHOW_IP_ROUTE_RIP` and `parse_show_ip_route_rip`, qualified
live on PT 9.0.1.0858 and pinned by regressions against the real capture.

What does not yet exist is the typed *expectation* around it. The compiler's
RIPv2 branch emits only a `ROUTING_PROCESS` expectation, and
`_observe_route` still answers `rip_route_readback_unavailable` for a
`ConfigureRipv2` action, which was the deliberate R2-A boundary between
configuration and behaviour.

Consequence: route learning was proven in phase 4 by executing the registered
query and the production parser directly, and comparing the result against the
intended remote prefixes. That is production code and fresh evidence, but it is
not surfaced inside `ControlPlaneApplicationResult`, so an automated caller
cannot yet ask "did R1 learn R2's LAN?" through the typed plan.

Compiling such an expectation needs the remote device's actual subnets. The
RIPv2 action deliberately stores only the classful `network` statement plus
provenance, so the expectation would have to be derived from the configuration
plan rather than from `RipNetwork`.

Blocks now:
No. Route learning and forwarding were both verified live in phase 4.

RESOLVE_BEFORE:
university-topology acceptance, where route learning must be asserted
automatically rather than by an operator harness.

Closure criterion:

A compiled `ROUTE_PRESENT` expectation exists for typed RIPv2, bound to the
remote prefixes derived from the configuration plan, and
`_observe_route` verifies it with `parse_show_ip_route_rip` and fresh evidence.
Absent, stale, or non-RIP route output must not verify.

### Resolution

Resolved: 2026-08-12, stage "Debt Checkpoint 1".

Commit subject:
`feat: integrate RIP route expectations into control-plane results`
on `feature/runtime-ripv2`.

The route read-back was already live-qualified in R2-B phase 4. What this adds
is the typed expectation that carries it into
`ControlPlaneApplicationResult`, so an automated caller can finally ask "did
this router learn the remote LAN?" through the plan instead of through an
operator harness.

Expected prefixes come from the **E5 L3 identities**, never from `RipNetwork`,
which is classful and does not know the real `/27` or `/28`. For each ordered
pair of routers the compiler emits one expectation per network the remote is
connected to and the local is not, so a locally connected prefix can never
satisfy a remote route expectation. Nothing keys on device names.

The expectation carries exactly `network`, `prefix_length` and
`protocol = ripv2`. Next hop, outgoing interface and metric are deliberately
absent: the qualified evidence arrived over a serial, and requiring those
fields would bind acceptance to one topology shape.

`ROUTING_ROUTE_STATE` is now SUPPORTED for the 2911, on the R2-B phase 4 live
read of `show ip route rip` on that exact model and build.

Fail-closed behaviour, all regression-covered: a wrong prefix or wrong prefix
length FAILS; an OSPF, EIGRP or connected row FAILS rather than satisfying a
RIP expectation; a pager-truncated route table is UNOBSERVABLE with
`rip_route_readback_truncated`, never FAILED; evidence without a fresh window is
UNOBSERVABLE; and an APPLIED configuration never proves a learned route.

Two earlier tests changed, both because this debt is chartered to move the
boundary they pinned. R2-A had asserted that RIP compiles only a
`ROUTING_PROCESS` expectation; that test now asserts configuration **and**
route expectations, while still proving no neighbour or reachability
expectation is invented. The capability test now lists the third supported
dimension. Route verification stays distinct from forwarding: no
`END_TO_END_REACHABILITY` expectation is compiled for RIP.

### Corrective evidence — University Topology Acceptance, 2026-08-12

**The closure above was written before the compiled expectations had ever been
executed against three routers, and executing them falsified part of it.**
Recorded here so the ledger does not read as though the closure was clean on
first attempt.

The resolution claimed the compiler emitted "one expectation per network the
remote is connected to and the local is not". With two routers that is also one
expectation per prefix, so the distinction never surfaced. With three routers a
prefix is reachable through two peers, and the compiler emitted one expectation
**per ordered peer pair** while `_stable_id` keys only on
`(local_id, network, prefix_length)`. Two expectations therefore shared an id:
ten emitted, eight unique.

The offline tests did not catch it. They used a three-router fixture — so the
shape was covered — but compared **sets**, which silently absorbs a duplicate.
Set comparison is what hid a real defect behind a passing suite.

Correction, in `feat: complete university topology acceptance`: the compiler
emits exactly one expectation per `(device, remote prefix)`, keeping the first
contributing peer for `depends_on` and `peer_device_id`. This is also the
honest semantics — the assertion is that the router *learned the prefix*, not
which neighbour advertised it, and next hop was already deliberately excluded
from the comparison.

Regression coverage, both in `tests/test_typed_ripv2_control_plane.py`:

- `test_every_compiled_expectation_has_a_unique_id` — ids unique across the
  whole plan, not merely within route expectations;
- `test_a_prefix_reachable_through_two_peers_is_expected_once` — the r2–r3
  transit prefix, reachable from r1 through both peers, is expected exactly
  once.

Both compare a **list against its set**, which is precisely the check the
earlier tests omitted.

Disposition: **TD-RUNTIME-005 remains RESOLVED.** Its closure criterion — a
compiled `ROUTE_PRESENT` expectation bound to remote prefixes derived from the
configuration plan, verified with `parse_show_ip_route_rip` and fresh evidence,
with absent, stale or non-RIP output never verifying — is satisfied, and is now
satisfied under executed multi-peer evidence rather than under an untested
two-router assumption. Nine semantically unique `(device, prefix)` expectations
were emitted and all nine VERIFIED live on PT 9.0.1.0858.

---

## TD-CAPABILITY-001 — No product provider populates control-plane capability profiles

Status:
RESOLVED

Severity:
P0

Discovered:
Runtime R2-B (capability gate, hard precondition)

Description:

`ControlPlaneApplicator` gates every typed control-plane action on
`ControlPlaneCapabilityProfile`. Nothing in `src/` ever constructs one.

Measured on `feature/runtime-ripv2` @ `dc7046c`:

- `ControlPlaneCapabilityProfile(` appears in `src/` only as the class
  definition; all 13 constructions live in `tests/`;
- the only constructor is the classmethod `.supported()`, whose own
  `evidence_source` field is the literal string `"test fixture"`;
- no `ControlPlaneCapabilityDimension` value (`ripv2_config`,
  `ospfv2_config`, `eigrp_ipv4_config`, `stp_pvst_config`, `hsrp_config`)
  appears anywhere in `src/` outside the enum that declares it, so the
  capability snapshot store holds no control-plane evidence at all;
- there is no bridge from `DeviceCapabilities`, the model the real providers
  populate, to `ControlPlaneCapabilityProfile`.

Consequently `capabilities=None`, the production default of
`ControlPlaneApplicator.apply`, resolves every dimension to UNKNOWN.

Executed against the real applicator with a valid runtime inventory and a
runtime that would have accepted every mutation:

```text
2911:ripv2_config is unknown.
status = skipped   failure_code = capability_unknown   disposition = skipped
dispatched to runtime: nothing
```

Substituting a test profile built with `.supported()` dispatches both actions,
which isolates the capability gate as the cause.

This is not specific to RIPv2 and was not introduced by R2-A: OSPFv2, EIGRP,
STP and HSRP resolve UNKNOWN on the same model. The typed control-plane
application path has only ever been exercised with test-supplied profiles.

The gate itself behaves correctly. UNKNOWN stays UNKNOWN, nothing is
dispatched, and no claim is inflated. The debt is the missing evidence path,
not the gate.

Related:
`TD-HARDWARE-001` is the same family — capability evidence not reaching its
consumer — but concerns hardware selection rather than control-plane
dimensions.

Blocks now:
Yes. `RIPV2_PRODUCT_CAPABILITY_RESOLUTION = BLOCKED` stopped Runtime R2-B at
its declared hard precondition. Every live R2-B gate is unreachable without
injecting a fake SUPPORTED capability, which R2-B explicitly forbids.

Also blocks:
any live acceptance that applies typed control-plane actions, including the
university-topology scenario.

RESOLVE_BEFORE:
the next runtime ticket, before Runtime R2-B can be retried, and necessarily
before university-topology acceptance.

Closure criterion:

A production provider resolves `ControlPlaneCapabilityProfile` for a given
model from real catalog/runtime/probe evidence, with recorded provenance and
Packet Tracer version, and the control-plane application path consumes it
without a caller-supplied fixture. UNKNOWN must remain UNKNOWN when evidence is
absent: the closure is a real evidence path, never a default of SUPPORTED.

### Resolution

Resolved: 2026-08-11, stage "Resolve TD-CAPABILITY-001".

Commit subject:
`fix: wire control-plane capability evidence into product runtime`
on `feature/runtime-ripv2`.

Implementation path:

`infrastructure/catalog/control_plane_capabilities.py` mirrors the existing
`security_capabilities.py` catalog and returns
`dict[str, ControlPlaneCapabilityProfile]`. `ControlPlaneApplicator` gained a
`capability_provider` constructor parameter defaulting to that catalog, and
`apply()` now treats `capabilities=None` as "resolve authoritative evidence"
instead of "no evidence". An explicit mapping, including `{}`, is still
honoured verbatim so tests can isolate the gate.

The precedent for a use case importing an authoritative catalog is
`compile_configuration.py`, which already imports `link_mode_capability_for`
from the same package.

Evidence mapping:

Only live evidence **attributed to a model** is encoded. The E9 live baseline
in `enterprise-control-plane.md` records STP, EtherChannel, HSRP, OSPF and
EIGRP results but names no device model, so none of them is claimed; inventing
that attribution is exactly what the mapping must not do.

- `2911` / `RIPV2_CONFIG` = SUPPORTED, from the R2-0 live qualification;
- `2911` / `ROUTING_PROCESS_STATE` = SUPPORTED, from the same live
  `show ip protocols` read-back, which demonstrates the observation channel on
  this model and build. It does not make OSPF or EIGRP observable: the runtime
  reads those with different queries and still requires its own fresh parse;
- every other dimension on every model = UNKNOWN, declared explicitly rather
  than omitted, so a new dimension must be classified instead of inheriting a
  default.

Live qualification:

One disposable 2911 on PT 9.0.1.0858, applied through the real product path
with no `capabilities` argument:

```text
2911:ripv2_config              -> supported
provenance                     -> R2-0 controlled live qualification (non-test)
action                         -> applied, failure_code none
RIP configuration dispatches   -> 1
read-back                      -> send/recv 2/2, auto-summary false,
                                  networks ['150.1.0.0'],
                                  passive ['GigabitEthernet0/0',
                                           'GigabitEthernet0/1']
typed verification             -> routing_process VERIFIED via
                                  fresh_show_ip_protocols, fresh evidence,
                                  all six compared fields verified
```

Cleanup left no probe residue.

Fail-closed behaviour is unchanged and regression-covered: an explicit empty
mapping still yields UNKNOWN, `CAPABILITY_UNKNOWN` and zero mutations, and
explicit UNSUPPORTED evidence yields `CAPABILITY_UNSUPPORTED` and zero
mutations.

### Scope closure — 2026-08-11

Two questions were left open by the resolution above and are now settled.

**Environment scope is enforced, not merely recorded.**

The first implementation stored `packet_tracer_version` on the profile as
metadata and never consulted it, so evidence qualified on any build. The gate
now applies the rule that
`capability_resolver._evidence_matches_version` already fixes for runtime and
probe evidence: reuse requires an **exact** version match.

`ControlPlaneApplicator.apply` filters resolved profiles through
`_profiles_in_environment_scope` against
`ConfigurationRuntimeContext.evidence_backend_version`, which is the existing
declared-environment mechanism and prefers the `EnvironmentFingerprint` when
one is present. No second version system was introduced.

- a profile that declares no version claims no scope and is preserved, which
  keeps caller-supplied profiles working unchanged;
- a profile that declares a version is dropped when the declared environment
  differs **or is absent**, and a dropped profile means the model has no
  profile, which the gate resolves as UNKNOWN.

Consequence for callers: the product path must now declare the environment it
is running against. The live qualification recorded above ran before this rule
existed and did not declare one; the environment was in fact `9.0.1.0858`, but
that run would today require the caller to say so. Counterfactuals for a newer
build, an older build, an undeclared environment and a malformed version are
regression-covered, and mutation checks confirm the rule is load-bearing.

**`ROUTING_PROCESS_STATE` is a device observation-channel gate.**

The contract was determined from structure and from runtime behaviour rather
than from what RIP verification needs:

- the enum splits *configuration* per protocol and mode — three STP config
  dimensions, three EtherChannel config dimensions, three routing config
  dimensions — but declares exactly **one** state dimension per family;
- both compiler branches, RIP and OSPF/EIGRP, request the same
  `ROUTING_PROCESS_STATE`, so it is protocol-independent by construction;
- narrowing by protocol or mode happens at observation time in the runtime and
  predates RIP: `mst_readback_unavailable`,
  `etherchannel_protocol_readback_unavailable`, `hsrp_role_readback_unavailable`
  and `eigrp_readback_unavailable` all narrow within a coarse state dimension.

So the dimension means "this device exposes routing-process state that a
registered query can observe", not "every routing protocol is observable". The
R2-0 live `show ip protocols` read on the qualified 2911 evidences exactly
that, and it cannot manufacture an OSPF or EIGRP claim: with the gate
SUPPORTED, an EIGRP routing-process expectation still returns UNOBSERVABLE with
`eigrp_readback_unavailable`, which is regression-covered.

`ROUTING_PROCESS_STATE` therefore stays SUPPORTED for the 2911 on evidence, not
on convenience.

---

## TD-RUNTIME-001 — Post-cleanup result DirtyState may be stale

Status:
RESOLVED

Severity:
P1

Discovered:
Runtime Safety R1 final closure

Description:

`execution_journal.cleanup_status` can become `CompensationStatus.SUCCEEDED`
while a previously materialized execution result still carries
`DirtyState.UNKNOWN`.

The result appears to preserve a snapshot taken before the later cleanup
transition.

Current impact:

Does not affect:

- command dispatch integrity;
- RIPv2 replay qualification;
- initial typed RIPv2 implementation.

It may affect later consumers that reason about final post-cleanup state,
especially Acceptance, Diagnosis, Compensation, or Autofix.

Blocks now:
No.

RESOLVE_BEFORE:
Acceptance/Diagnosis/Autofix work and, at latest, E9.5 final closure.

Closure criterion:

Determine explicitly whether `result.dirty_state` is intended to represent:

1. historical state at result materialization time; or
2. final journal state after cleanup.

Then make implementation, naming, documentation, and tests consistent with
that contract.

### Resolution

Resolved: 2026-08-12, stage "Debt Checkpoint 1".

Commit subject:
`fix: reconcile final dirty state after cleanup`
on `feature/runtime-ripv2`.

**The stated mechanism was wrong, and the correction matters.** There is no
stale snapshot. In every applicator the cleanup transition happens *before* the
result is built — `apply_control_plane.py` constructs the journal, calls
`_record_scenario_restore`, and only then materialises the result reading
`journal.dirty_state`. Because no enterprise model revalidates instances, the
result holds the same journal object, so `result.dirty_state` and
`result.execution_journal.dirty_state` could never disagree. Fixing "staleness"
would have fixed nothing.

The real defect was a **false CLEAN**. `mark_cleanup(SUCCEEDED)` overwrote
`dirty_state` to `CLEAN` unconditionally, including over `UNKNOWN`. Since a
fire-and-forget dispatch carries an `UNKNOWN` disposition, a mutation nobody
could confirm, compensated by another dispatch nobody could confirm, was being
reported as clean. `apply_control_plane.py` had a hand-written bypass to dodge
exactly this, while `apply_security.py` did not — two applicators with opposite
semantics for the same situation, each pinned by a test in the same file.

Contract chosen:

```text
EXECUTION_RESULT_CONTRACT = HISTORICAL_AND_FINAL_STATE_ARE_DISTINCT
```

Chosen from behaviour, not diff size: the result is already materialised after
cleanup, so the field is structurally final, while the append-only entries are
the historical record this document already says must not be erased.

Authoritative invariant, now documented in `e95-stabilization.md`:

- `dirty_state` is the **final post-cleanup state** and is the only value a
  consumer should use for acceptance, diagnosis, or autofix;
- `applied_dirty_state` is a property derived from the append-only entries and
  records the **historical** application state; compensation never overwrites
  it;
- with no compensation attempted, the two are equal.

`mark_cleanup` now composes them with what compensation can actually prove:
`SUCCEEDED` clears only `CLEAN` and `DIRTY_RECOVERABLE`, because those are what
an inverse could undo. It never resolves `UNKNOWN`, and never clears
`DIRTY_UNRECOVERABLE`. `FAILED` and `UNKNOWN` keep their previous meaning
deliberately: a failed compensation still reports unrecoverable residue, which
is the strongest call for attention, and weakening it to UNKNOWN would be less
safe, not more honest.

Consequences:

- the control-plane bypass is deleted; both applicators now take one path;
- one security test changed from `CLEAN` to `UNKNOWN`. That removes an unearned
  claim rather than weakening a check, and the test now also asserts the
  historical state;
- `e95-stabilization.md` said "Successful compensation returns the journal to
  `CLEAN`" without qualification. That sentence was unsound and is corrected.

Evidence:

- focused regressions covering the **full cross product** of four application
  states against all six compensation statuses, plus historical state surviving
  a successful cleanup, a post-cleanup append recomputing from entries, and an
  adversarial sweep proving no `CompensationStatus` value can turn an `UNKNOWN`
  mutation into `CLEAN`;
- full suite green.

### Correction found by independent review

The first implementation deleted the `apply_control_plane.py` bypass and routed
the scenario restore through `mark_cleanup`, on the argument that the two
applicators had "opposite semantics for the same situation". **That argument was
wrong, and it introduced a new false CLEAN**: with the bypass gone, a
`DIRTY_RECOVERABLE` application followed by a successful scenario restore
reported `CLEAN`. Reproduced directly before fixing.

The two situations are not the same. `apply_security.py` computes its cleanup
outcome from cleanup actions actually executed against the applied actions, so
`SUCCEEDED` clearing `DIRTY_RECOVERABLE` is earned there. The control-plane
path records the restoration of a link fault this same runtime injected; it
runs no inverse against the mutations of a failed application, so it can prove
nothing about them.

`ApplicationExecutionJournal.record_scenario_restore` now expresses that
difference explicitly. It records `cleanup_status` and may only worsen the
state — `FAILED` to `DIRTY_UNRECOVERABLE`, `UNKNOWN` to `UNKNOWN` — never
improve it. `mark_cleanup` keeps its meaning for real compensation. The
deleted comment had been right; what was missing was a name for the operation
rather than an inline field write.

A regression now pins this for all four application states, and the route
observer additionally fails closed when an expectation lacks a typed prefix and
length, which previously fell back to matching on network address alone.

---

## TD-HARDWARE-001 — Capability-to-hardware reconciliation remains partial

Status:
OPEN

Severity:
P1

Discovered:
E9.5 Stage 3A3-E

Description:

Runtime capability evidence does not yet fully drive hardware selection.

Known example:

- ProbeCapabilityProvider can make 3560 multilayer capability SUPPORTED;
- 3650 has multilayer runtime evidence but current capability-to-selector
  mapping does not fully reconcile it into dynamic hardware selection.

The pinned E9.5 regression reference remains valid and does not depend on
dynamic selection.

Blocks now:
No for the pinned reference topology.

Blocks claims of:
fully dynamic capability-driven hardware selection.

RESOLVE_BEFORE:
E9.5 final closure.

Closure criterion:

Capability evidence used by the enterprise resolver must reconcile
deterministically into eligible physical hardware without model-string
special casing, while UNKNOWN remains UNKNOWN.

### Verification — Debt Checkpoint 2, 2026-08-12

Re-verified against source. **Still accurate, with one claim I could not
substantiate and one part already satisfied.**

Confirmed: the gap is live. Both productive constructions of
`EnterpriseCapabilityAdapter` (`tool_registry.py:1532` and `:1552`) pass no
providers, and neither `ProbeCapabilityProvider` nor
`RuntimeCapabilityProvider` is instantiated anywhere in `src/`. The in-code
marker at `enterprise_capabilities.py:38` says the same thing and is correctly
mirrored here.

Already satisfied: the "without model-string special casing" half.
`device_selector.py` branches only on category, port counts and
`CapabilityStatus`; model strings appear solely as sort keys and in the
caller-supplied `preferred_model` comparison. `capability_resolver.py` contains
no model literal. What remains unsatisfied is the evidence *reaching* the
resolver, and `UNKNOWN` already remains `UNKNOWN` — distribution and core roles
land in `needs_verification` rather than being selected on absent evidence.

**Could not verify:** the claim "3650 has multilayer runtime evidence". No such
evidence exists anywhere in this repository — no capability snapshot content,
no attributed record in `src/`. The only 3650 layer-3 statement is prose in
`docs/devices.md:28` carrying no provenance and no Packet Tracer version. The
3560 half of the example is exact; the 3650 half should be treated as
unsubstantiated until a probe record exists, and closure must not assume it.

Hygiene item observed in this same path at CP2 and **deliberately left in
place**: a stranded `def evidence_for(self, ...)` is nested inside the
module-level `_snapshot_evidence` generator in `capability_providers.py`,
unreachable and carrying a `self` parameter it has no class for. It is dead —
all three providers define their own `evidence_for` — so it fixes nothing to
remove and CP2 does not touch source. Recorded here because this file is the
evidence path this debt must eventually rewire, and whoever does that work
should delete the fragment then rather than leave a reader to "repair" it by
un-indenting, which would silently blank out every provider's evidence.

### Verification — Stage 3A4 Slice 2B/3, 2026-08-17

**Still OPEN, and the reason is now sharper than "not wired yet".**

Implemented (`2bee898`): `packet_tracer_enterprise_capability_adapter(version)`
is an exact-version composition root that wires both `ProbeCapabilityProvider`
and `RuntimeCapabilityProvider`, binds the adapter to one Packet Tracer version,
and returns evidence-free capabilities when the asked version differs. It also
adds the model-neutral one-way implication this entry's closure criterion needs:
verified SUPPORTED `multilayer_intervlan` implies `layer3`, with no model-string
special casing. Measured: `3560-24PS.layer3` goes UNKNOWN → SUPPORTED through
that root, and `3650-24PS.layer3` reaches SUPPORTED through the implication.

**Why the entry does not close.** The criterion requires capability evidence to
reconcile into *eligible physical hardware*. Re-measured at this slice: the two
productive constructions cited above (`tool_registry.py:1532` and `:1552`) both
live inside `_capability_discovery` and consume `catalog.identity_for` alone,
which reads no evidence. Wiring providers there would satisfy a grep and change
nothing. Nothing anywhere in `src/` feeds a capability adapter into hardware
selection at all. **The mechanism now exists and is proven; the consumer does
not exist.** That is the remaining work, and it is a narrower statement than the
one this entry opened with.

The CP2 tripwire `test_no_production_site_wires_the_providers` was deliberately
**not** restored. It existed to fire the day someone wired providers by
accident; wiring them is now this entry's intended direction, so keeping it
would guard the opposite of the goal. It is replaced by strictly stronger
assertions: both providers wired, exact version mandatory, no-evidence stays
UNKNOWN, version-mismatched stays UNKNOWN in both directions, the implication
fires only on SUPPORTED *and* verified evidence, a measured UNSUPPORTED survives
wiring as UNSUPPORTED, and no `.supported()` shortcut or test fixture exists in
the composition root.

The stranded `evidence_for` fragment described above **was deleted** in
`2bee898`, as this entry anticipated.

The "3650 has multilayer runtime evidence" claim remains **unsubstantiated**.
The tests above use a hermetic fixture that constructs that evidence; they prove
the implication mechanism, not that any real 3650 probe record exists. Closure
must still not assume it.

Does not block Stage 3A4: regression-pinned by
`TestTheRegressionReferenceDoesNotDependOnSelection`, whose docstring states
the reason and whose assertions prove the reference fixture pins `2960-24TT`
and `2911` by hand and admits neither `3560-24PS` nor `3650-24PS`.

### Progress — Stage 3A4 MEG-2, 2026-08-17

```text
PHASE_2_IMPLEMENTATION = COMPLETE / OFFLINE_QUALIFIED
TD_HARDWARE_001        = OPEN
```

**The consumer now exists.** `application/use_cases/plan_enterprise_hardware.py`
is the first production caller of both
`packet_tracer_enterprise_capability_adapter` and `HardwarePlanner`. It composes
only: candidates come from `hardware_candidates(category, version)`, planning is
delegated to `HardwarePlanner` unchanged, and the result carries the candidates
next to the plan so the evidence *used by* the resolver stays recoverable.

Confirmed with Graphify before the change, not assumed: all 47 inbound edges of
`HardwarePlanner` came from tests or from its own module.

Ten regressions in `tests/test_enterprise_hardware_composition.py`, one per
invariant this entry cares about — exact-version evidence reaches eligibility;
no evidence stays UNKNOWN; version mismatch stays UNKNOWN; evidence is never
redistributed to another model; a measured UNSUPPORTED survives as UNSUPPORTED;
and no fixture or `.supported()` shortcut exists on the production path.

**Why the entry still does not close.** The criterion governs *"capability
evidence used by the enterprise resolver"*. Every test above seeds its own
`CapabilitySnapshotStore`. Seeded evidence proves **code properties** — that the
wiring carries evidence and that the negative semantics hold. It is **not**
machine or backend evidence, and presenting it as such would be exactly the
substitution this entry exists to reject. The literal criterion is therefore
re-evaluated after the first governed live gate that exercises real
exact-version capability consumption, and `RESOLVED` is recorded only from that
evidence. If no such evidence is produced during Stage 3A4, the entry stays
`OPEN` against its E9.5 deadline — which changes nothing, because it does not
block Stage 3A4.

The "3650 has multilayer runtime evidence" claim remains **unsubstantiated** and
is still not assumed anywhere.

**`_SERIAL_MODULE_SLOT_BY_MODEL` — classified, as this entry's criterion
requires.** `infrastructure/catalog/enterprise_capabilities.py:28` is a
model-string-keyed dict, so it deserves an explicit verdict rather than silence:

| Construct | Verdict |
| --- | --- |
| A backend/catalog-owned model→slot fact, living in `infrastructure/catalog/` and consumed as data | **LEGITIMATE.** Stating physical facts about models is precisely a catalog's job. It maps a chassis to the slot its serial module occupies; it promotes no capability and gates no eligibility |
| A model-name exception inside `EnterprisePlan`, `HardwarePlanner` or `DeviceSelector` | **PROHIBITED.** That would be capability reconciliation smuggled into hardcoded planning, and would let the reference pass without evidence deciding anything |

The prohibited half is now regression-enforced:
`test_no_model_name_exception_lives_in_planning` scans the planning modules and
the new use case for model-name literals. They are clean today and cannot
silently stop being clean. **No closure of this entry may depend on such an
exception.**

### Note — which evidence tier eligibility rests on, 2026-08-18

Recorded by `TD-CATALOG-PORT-001`, which is a **distinct** entry and closes
nothing here. It answers a different question about different evidence: this
entry asks whether capability evidence reconciles into an *eligible* model;
that one asks whether the concrete port *names* a chosen model is bound by are
authorised by the backend. Either can hold without the other.

The seam between them is worth stating so a future closure does not assume more
than it has. `DeviceSelector` filters on `min_access_ports` / `min_uplinks` and
ranks on surplus port count, and those counts come from the declared catalogue,
not from measurement. Eligibility therefore reconciles on **DECLARED**-tier
data. That is legitimate — planning is not binding, and the tier model now says
so in the data — but whoever closes this entry should name the tier its
eligibility evidence came from rather than leave it implied.

Measured during MEG-4 run 2 and unchanged by that work:

```text
CAPABILITY_CONSUMER_INVOKED       = YES  (plan_enterprise_hardware, bound to 9.0.1.0858)
PINNED_BACKEND_EVIDENCE_AVAILABLE = NO   (no capability snapshot exists for any build)
PINNED_BACKEND_EVIDENCE_USED      = NO
TD_HARDWARE_LITERAL_CRITERION     = NOT_SATISFIED
```

`TD-HARDWARE-001` therefore remains **OPEN** against its E9.5 deadline.

---

## TD-MODULE-SLOT-001 — Module slot placement is unverifiable, and the gate compares two namespaces

Status:
BACKEND_LIMITATION

Severity:
BACKEND_LIMITATION

Discovered:
Stage 3A4 MEG-4 bounded live qualification, 2026-08-17, on 2911 / PT `9.0.1.0858`.
Evidence: `stage-3a4-bounded-live-qualification.md`.

Description:

`EnterprisePhysicalTopologyDeployer` refuses a module whose
`slot_effect_observed` is false. `packet_tracer_physical_runtime.py:596` derives
that flag as `effect_observed and after.module_tree_observed and
any(item.observed_module_number == module.slot ...)`.

That comparison puts two different namespaces on either side of `==`:

```text
module.slot                  = "0/0"   port-namespace, from _SERIAL_MODULE_SLOT_BY_MODEL
item.observed_module_number  = "0"     module-tree namespace, from the backend
```

They cannot be equal for 2911, so the flag is unreachable on this model. Slice
2A's own record already stated the two are distinct
(`stage-3a4-serial-product-slice-2a.md:69`), and the check was nonetheless
written as an equality. It shipped in Slice 2A's implementation commit
`e846175`; it is not a later regression.

Measured live, the module *does* land and its effect *is* independently
verified — `Serial0/0/0` and `Serial0/0/1` appear in a fresh read-back that did
not contain them before. What cannot be observed is **which slot** they came
from: the module tree reports exactly one entry, the onboard module with three
Gigabit ports, and the inserted HWIC-2T never appears. Matching against `"0"`
would therefore be worse than not matching — it would assert the HWIC occupies
the onboard slot, which the evidence contradicts.

Why no regression caught it: `tests/test_e95_serial_physical_product_slice.py`
set `slot_effect_observed=True` directly in its double, so the real derivation
was never exercised. It was first pinned by `tests/test_e95_module_slot_namespace.py`;
that file has since been retired in favour of `tests/test_module_port_effect_contract.py`,
which drives the real runtime instead of a hand-built observation — see the
Resolution below.

Classification:
```text
STAGE_3A4_SCOPE
BACKEND_LIMITATION for slot attribution     # remains
PRODUCT_DEFECT in the comparison            # fixed 2026-08-17, see Resolution
```

Blocks Stage 3A4:
**No, since the branch-B resolution below.** At discovery this read **Yes** --
no bounded live product run could pass module verification on 2911 while the
namespace comparison stood. The comparison is gone and module verification now
rests on port-effect evidence, which is verifiable. The residual backend
limitation blocks only claims about placement, and no Stage 3A4 acceptance row
asks for one.

Blocks claims of:
any claim that a module was installed **in a specific slot**. Port-effect
evidence remains valid and unaffected; it proves effect, never placement, and
never identity.

RESOLVE_BEFORE:
Stage 3A4 MEG-4 completion.

Closure criterion:

One of the following, decided deliberately and recorded with its claim ceiling:

- **A.** A confirmed backend path that attributes an inserted module to its
  requested slot. If one exists it must be verified against Cisco's reference
  before use — `AGENTS.md` rule 6 — and not guessed.
- **B.** Slot placement is classified `UNOBSERVABLE` for this backend/model, the
  same way module *identity* already is, and the deployment gate is changed to
  stop treating an unobservable placement as a failed effect. Any such change
  must state explicitly what is no longer claimed, and port-effect verification
  must remain mandatory.

**Neither branch may be taken by relaxing the gate to make a run succeed.** The
MEG-4 run that found this deliberately left the refusal in place.

### Resolution — branch B, 2026-08-17, commits `8d385f9` / `1483762`

Branch B was selected and implemented. The `PRODUCT_DEFECT` half of the
classification is fixed; what remains is the backend limitation, which is why
this entry closes as `BACKEND_LIMITATION` rather than `RESOLVED` — the
limitation is classified and contained, not eliminated.

**What the product now claims, and what it stopped claiming.**

```text
MUTATION_SUBMISSION       = APPLIED only
REQUESTED_INSERTION_SLOT  = mutation intent only
MODULE_PORT_EFFECT        = VERIFIED, from fresh before/after evidence that this
                            transaction caused the complete expected port set
EXACT_MODULE_IDENTITY     = UNOBSERVABLE
EXACT_MODULE_PLACEMENT    = UNOBSERVABLE
```

No `SLOT_VERIFIED` is emitted or implied anywhere. The deployment manifest
carries an `e4/module-placement/<target>` evidence record whose claim is
"requested module physically occupies the requested slot" and whose verdict is
`UNOBSERVABLE` / `UNVERIFIED` with an explicit limitation, so a reader cannot
mistake silence for assent.

**Identity was corrected too, and for the same reason.** The old derivation
selected which module-tree entry to read an identity from by the same invalid
`observed_module_number == module.slot` comparison. It never fired on 2911, so
the outcome was accidentally right; on a backend where the two namespaces
happened to collide it would have attributed a card identity to a placement
nothing established. Identity is now UNOBSERVABLE because placement is: without
knowing which tree entry corresponds to the requested slot, no observed identity
can be attributed to *this* module.

**The gate is stricter than it was, not looser.** Two conditions were dropped —
reading the module tree, and the namespace comparison — one unreachable and one
semantically invalid. Two were added that did not exist before:

- the complete expected port set must have been **absent before** and **present
  after** the mutation, so a pre-existing port set no longer counts as an effect
  this run caused (the old gate would have accepted it);
- the device must be **newly owned by the current disposable transaction**, read
  from the runtime's own ownership ledger rather than assumed.

The verdict lives in `PhysicalModuleObservation.effect_verification_status`, a
**computed field**. It cannot be assigned by production code or by a test
double. That is deliberate containment: what hid the original defect for a whole
slice was `slot_effect_observed=True` written by hand in a double, which meant
no regression ever exercised the real derivation.

**Closure criteria, evaluated one at a time.**

| # | Criterion | Verdict |
| --- | --- | --- |
| 1 | Stage 3A4 acceptance does not literally require VERIFIED exact placement | **Holds.** TD-ACCEPTANCE-001 rows 1–6 were read individually. Row 1 requires production deployment with a fresh-readback manifest; row 2 requires the adapter to insert once, independently verify fresh `Serial0/0/0` / `Serial0/0/1` effects, and preserve exact module identity as `UNOBSERVABLE`. No row asks for placement. |
| 2 | No production code reports or implies verified exact placement | **Holds.** The only occurrence of the placement sentence in `src/` is the `claim` field of the evidence record that reports it unverified; `verifies_claim` is false there. Pinned by `test_e95_serial_physical_product_slice.py`. |
| 3 | Module effect is independently verified | **Holds.** From a fresh port inventory read before and after, against the catalogued expected port set — never from the mutation receipt. |
| 4 | Replay containment remains intact | **Holds.** Containment lives entirely in `ensure_module` and never read this flag: a complete pre-existing effect is `NO_OP`, a partial one refuses to overwrite, a conflicting one refuses to mutate, an ambiguous receipt is never replayed, and insertion still requires an owned new device. Re-pinned as rows 10 and 11. |
| 5 | Cleanup / ownership safety remains intact | **Holds.** Cleanup targets `attempted_devices` and is unrelated to module evidence; a module-effect failure still runs it, still removes only product-planned names, and still spares the backend-managed power-distribution object. Re-pinned as rows 12 and 13. |
| 6 | Interface / link binding remains adequately evidenced | **Holds.** Links are created only after module observation succeeds, and what link binding needs is that the **port** exists — which is exactly what is now verified. Placement was never an input to it. |

**Residual limitation, stated plainly.** Packet Tracer `9.0.1.0858` exposes no
path this repository can use to attribute an inserted module to its requested
slot. Branch A stays available if a confirmed backend path is ever found; it
must be verified against Cisco's reference before use (`AGENTS.md` rule 6) and
not guessed. Until then, no claim about physical module placement may be made
from this product.

Regressions: `tests/test_module_port_effect_contract.py` (rows 1–11, driving the
real runtime against the measured Packet Tracer payload) and
`tests/test_e95_serial_physical_product_slice.py` (rows 12–13, plus the manifest
record). `tests/test_e95_module_slot_namespace.py` was retired: it existed to
force this decision to be deliberate, and everything it pinned is now pinned
through the real derivation instead of a hand-built observation.

## TD-CATALOG-PORT-001 — Catalogued port names are not verified against the backend

Status:
RESOLVED

Severity:
P1

Discovered:
Stage 3A4 MEG-4 bounded live qualification, run 2, 2026-08-18, on PT `9.0.1.0858`.
Evidence: `stage-3a4-bounded-live-qualification.md`, "Run 2".

Description:

`infrastructure/catalog/devices.py` declares each model's physical ports by
hand, and those names are the ones the product asks Packet Tracer for. Measured
live, at least one model's declaration is wrong:

```text
model    : IE-2000
declared : FastEthernet0/1..0/8, GigabitEthernet0/1, GigabitEthernet0/2
           (devices.py:173)
observed : FastEthernet1/1..1/8, GigabitEthernet1/1, GigabitEthernet1/2, Vlan1
           (fresh read-back of a device Packet Tracer had just created)
```

Every port name is in the wrong slot namespace — `0/x` where the device uses
`1/x` — so no port the plan names exists. The wrong names propagate through the
whole product: `port_descriptors_for` → `HardwareCandidate.ports` →
`HardwarePlanner` port assignment → `EnterpriseCompiler` link endpoints → the
deployer's required-port set. The deployment then fails at device port
observation with `port_observation_failed`, which is the correct outcome: the
gate refused to bind links to ports it could not observe.

**The scope of the entry is wider than the one wrong model, deliberately.** What
the run established is not merely that IE-2000 is misdeclared; it is that
*nothing verifies any catalogued port list against the backend*. The models the
pinned reference uses happen to be right — `2960-24TT` really is a `0/x` device
— and that is exactly why this survived: capability-driven selection reaches
models the hand-pinned reference never exercises. IE-2000 is the first one
measured, not necessarily the only one wrong.

Why the selector reached it: the bounded intent asks for two endpoints per site,
and IE-2000 is the smallest viable access switch in the catalogue. Choosing the
smallest viable model is correct behaviour; it just walks into unverified data.

Classification:
```text
STAGE_3A4_SCOPE
PRODUCT_DEFECT in catalogued data + MISSING_VERIFICATION of the catalogue
```

Blocks Stage 3A4:
**No, since the resolution below.** At discovery this read **Yes, for MEG-4**:
the bounded qualification could not complete while the product planned ports
that did not exist on the model it selected. The bounded path is now qualified.
What remains is not this entry's residue but its contract in force -- MEG-5
cannot open until the reference run's own models are measured for the build it
will run against. That is recorded in the resolution.

Blocks claims of:
any statement that capability-driven hardware selection produces a deployable
plan for a model outside the hand-pinned reference set.

RESOLVE_BEFORE:
Stage 3A4 MEG-4 completion.

Closure criterion, refined 2026-08-18:

The original criterion was written as a choice between correcting one row (A)
and certifying every selectable model (B). Both readings were wrong in the same
way: they treated the catalogue as the thing to fix. The catalogue was not
wrong to *declare* what a model should have — it was wrong for the product to
treat a declaration as authorisation. The criterion below replaces that
either/or; it is a narrowing, not a widening, and the entry is evaluated
against it.

- declared port schema is distinct from backend-verified evidence, in the data
  rather than by convention;
- an executable live binding requires adequate evidence for the selected model
  in the backend context it will run against;
- missing or mismatched evidence stays UNKNOWN and fails closed;
- no model-name special casing enters planning or runtime;
- the model/build combinations the Stage 3A4 bounded path requires are
  qualified;
- every other selectable model remains declared/UNKNOWN, with no bulk
  promotion;
- no runtime observation silently rewrites backend-agnostic catalogue truth.

### Relationship to TD-HARDWARE-001 — distinct, with one shared seam

These are **not** duplicates, and this entry is not a subproblem of
TD-HARDWARE-001. They answer different questions about different evidence:

```text
TD-HARDWARE-001   does CAPABILITY evidence reach the resolver and reconcile
                  into ELIGIBLE hardware?          -> which model may be chosen
TD-CATALOG-PORT   does PORT evidence authorise the concrete NAMES the chosen
                  model will be bound by?          -> what may be said to the backend
```

Either can hold without the other. Perfect capability evidence still names
ports from a declaration; a fully measured port inventory still says nothing
about whether a model supports layer 3. Closing this entry therefore closes
nothing of TD-HARDWARE-001, and TD-HARDWARE-001 is left exactly as it was.

**The one seam worth recording**, because it is where a future reader would
otherwise assume more than is true: `DeviceSelector` filters on
`min_access_ports` / `min_uplinks` and ranks on surplus port count, and those
counts are derived from the same declared port list. Eligibility therefore
rests on DECLARED-tier data. That is legitimate — it is planning, not binding,
and the tier model says so explicitly — but it means TD-HARDWARE-001's
"reconcile deterministically into eligible physical hardware" is satisfied on
declared counts, not measured ones. For IE-2000 the counts happened to agree
with the backend (ten physical ports either way); only the names differed.
Whoever closes TD-HARDWARE-001 should say which tier its eligibility evidence
came from rather than leave it implied.

### Resolution — 2026-08-18, commit `571809c`

Implemented as **B's evidence model with A's qualification scope**: the
declared/backend-verified distinction is global, live qualification is not.

```text
DECLARED          static catalogue knowledge. Plan with it, never bind with it.
BACKEND_VERIFIED  one build's own report, for one model, in one module state.
UNKNOWN           neither. Not permission.
```

Evidence is scoped to model, build and module state and migrates along none of
them. A port that exists only once a card is installed is not evidence about
the same device without it, so the `2911` measurement answers for
`2911 + HWIC-2T@0/0` and stays silent about an empty chassis.

A concrete-port preflight runs before the first mutation and fails closed, so a
plan naming ports nothing authorises is refused offline rather than discovered
against a live workspace. The resolver is injectable for the same reason the
runtime is: a caller driving a substitute backend must supply the port evidence
of *that* backend instead of borrowing measurements taken against a real one.
The default is the measured catalogue, so a caller that says nothing gets the
strict contract.

`devices.py` is untouched and still declares `FastEthernet0/1..0/8` for the
IE-2000. It is backend-agnostic, and correcting it from one observation would
convert a planning declaration into a claim about a specific build — the exact
confusion this entry exists to undo. The measurements live in
`infrastructure/catalog/measured_port_inventories.py`, build-pinned, in the
shape `link_mode_capabilities.py` already established.

Qualified, all from MEG-4 run 2's own production read-backs on `9.0.1.0858`:

| Model | Module state | Ports as reported |
| --- | --- | --- |
| `2911` | `HWIC-2T@0/0` | `Gi0/0`, `Gi0/1`, `Gi0/2`, `Se0/0/0`, `Se0/0/1`, `Vlan1` |
| `IE-2000` | none | `Fa1/1..1/8`, `Gi1/1`, `Gi1/2`, `Vlan1` |
| `PC-PT` | none | `Bluetooth`, `FastEthernet0` |

Each list is the complete inventory as observed, logical interfaces included;
trimming them in the record would turn an observation into an interpretation.
They do not become planning descriptors — that filter is by interface class,
not by model name.

Criteria, one at a time:

| # | Criterion | Verdict |
| --- | --- | --- |
| 1 | Declared distinguished from backend-verified in the data | **Holds.** `PortInventoryEvidenceTier`, carried on every resolution and on `PortDescriptor.source`. |
| 2 | Executable binding requires adequate evidence | **Holds.** `_port_evidence_errors` runs in preflight, before the first mutation, and returns `PORT_EVIDENCE_UNAVAILABLE`. |
| 3 | Missing or mismatched evidence fails closed | **Holds.** Wrong build, wrong model and wrong module state each resolve UNKNOWN with a distinct reason, and UNKNOWN authorises nothing — not even partially. |
| 4 | No model-name special casing | **Holds.** The measured data is data; a structural regression guards the six planning/runtime files where such a branch would go. |
| 5 | Stage 3A4 bounded model/build combinations qualified | **Holds.** The three above, which is exactly what the bounded path selects. |
| 6 | Everything else stays declared/UNKNOWN | **Holds, and is load-bearing.** `2960-24TT`, `1941` and every other selectable model resolve UNKNOWN. Pinned by regressions so a later commit cannot promote them quietly. |
| 7 | No observation rewrites universal catalogue truth | **Holds.** `devices.py` unchanged, pinned by a regression that reads it. |

**What this costs, said plainly rather than buried.** MEG-5 cannot open on the
41-device reference until `2960-24TT` — and any other model that run selects —
has a measured port inventory for the build it will run against. That is the
contract working, not a residue of this entry: the reference has never been
executed through the production physical seam, so nothing has ever confirmed
that its declared port names are the ones Packet Tracer accepts. Before this
change the run would have discovered that live; now it is refused offline.

A second defect surfaced while qualifying this one and is fixed in the same
commit: cleanup walked `topology.devices` and asked to remove all eight planned
names even when the preflight had refused before creating any of them. Planned
is not created, and removing by name what the transaction never made is a
mutation against resources that could belong to someone else. It now removes
exactly what the deployment reported attempting.

Regressions: `tests/test_port_inventory_evidence.py` for the twelve contract
rows, plus the end-to-end refusal and the cleanup case in
`tests/test_stage3a4_offline_adversarial_matrix.py` and
`tests/test_enterprise_reference_execution.py`.

Status: **RESOLVED.** The architectural defect is gone and the bounded path is
qualified. It is not `BACKEND_LIMITATION`: Packet Tracer reports its ports
perfectly well: this repository had simply never written them down.

---

## TD-ORIENTATION-PAGER-001 — Serial controller read-back truncates and orientation cannot complete

Status:
OPEN

Severity:
P1

Discovered:
Stage 3A4 MEG-4 bounded live qualification, run 3, 2026-08-18, on 2911 with
HWIC-2T, PT `9.0.1.0858`. Evidence:
`stage-3a4-bounded-live-qualification.md`, "Run 3".

Description:

`SerialOrientationObserver` derives DCE/DTE from one registered read-only
`show controllers` per bound endpoint. Exercised live for the first time, both
endpoints returned the same result:

```text
Serial endpoint 'r-edge-a-01' on 'link/wan_link/23682ae56217':
    Registered controller query was truncated by the pager.
Serial endpoint 'r-edge-b-01' — identical.
```

The observer refused rather than reading an orientation out of a half-captured
buffer. That is the behaviour it was built for and it is not the defect; the
defect is that the evidence the product needs cannot currently be captured.

What was already known:

- PT 9.0.1 **rejects `terminal length 0`**, recorded independently at
  `ios_terminal.py:462`, `ios_terminal.py:1153` and `command_dispatch.py:154`.
  The ordinary way to disable the pager is unavailable on this build;
- `TD-RUNTIME-003` already handles pager truncation for `show ip protocols` by
  reporting UNOBSERVABLE rather than FAILED. Same phenomenon, different query,
  and that entry is `RESOLVED` on containment rather than on capture.

What run 3 established that was not known:

- `show controllers Serial0/0/0` on a 2911 carrying an HWIC-2T exceeds one page
  on this build, so the orientation query truncates **every time** rather than
  occasionally;
- `ControlledIosExecutor` cancels the pager to stop a paginated SHOW poisoning
  the next registered query, and keeps the first page as evidence. Whether the
  DCE/DTE line is on that first page is **not known** — nothing has measured it;
- the query is already interface-scoped (`SHOW_CONTROLLERS_SERIAL` with
  `interface=Serial0/0/0`), so narrowing the command further is not available.

Classification:
```text
STAGE_3A4_SCOPE
BACKEND_LIMITATION for disabling the pager on this build
+ MISSING_CAPABILITY for capturing a paginated registered read-back
```

Blocks Stage 3A4:
**Yes, for MEG-4.** The bounded qualification cannot reach E5, foundations, E9
or behaviour while serial orientation cannot be observed, because every later
stage depends on the oriented manifest. It blocks nothing offline and changes
no claim already recorded.

Blocks claims of:
any statement about observed DCE/DTE orientation, and therefore about serial
clock placement, on this backend. `SERIAL_ENDPOINT_ORIENTATION` remains
unobserved live.

RESOLVE_BEFORE:
Stage 3A4 MEG-4 completion.

Closure criterion:

One of the following, decided deliberately and recorded with its claim ceiling:

- **A.** A governed multi-page capture for registered read-only queries: page
  through the pager and concatenate, with the completeness of the assembled
  output proven rather than assumed. This is the only branch that yields
  orientation evidence, and it widens the registered-query contract, so it must
  keep the existing guarantees — no mutation, no poisoning of the next query,
  and a truncated-and-not-completed capture still failing closed.
- **B.** Establish, by measurement rather than by assumption, that the DCE/DTE
  line is always within the first captured page, and accept the first page as
  complete evidence *for this query only*. This must not weaken
  `truncated_by_pager` anywhere else, and must state what is being relied on.
- **C.** Classify live serial orientation `UNOBSERVABLE` for this build, which
  forfeits exit-matrix rows 4, 5, 7 and 8 and every claim that rests on an
  observed DCE. This is a real option and the most honest one if A and B both
  fail, but it is a claim ceiling, not a fix.

**No branch may be taken by parsing the buffer the product already flagged as
truncated.** That flag exists precisely to stop a hidden line being mistaken for
an absent one, and run 3 deliberately left the refusal in place.

---

## TD-TRANSPORT-001 — FileBridge does not provide exactly-once or at-most-once execution

Status:
BACKEND_LIMITATION

Severity:
BACKEND_LIMITATION

Discovered:
Runtime Safety R1-B through R1-F

Description:

The deployed Script Engine protocol can re-evaluate a request when:

- the request was evaluated;
- a response was written;
- deletion of the request file fails;
- the request remains discoverable on later bridge ticks.

The current deployed `.pts` does not expose a claim marker or transactional
request lifecycle sufficient to prove exactly-once or at-most-once
execution.

Current containment:

- no false cancellation claims;
- no blind retry for ambiguous operations;
- typed product paths require verification/readback where applicable;
- replay-sensitive operation families are classified separately;
- raw paths do not satisfy typed mutation contracts.

Blocks now:
No for RIPv2 qualification, provided RIPv2 proves replay-safe under the
current transport and follows its predeclared no-blind-retry/readback
contract.

RESOLVE_BEFORE:
E9.5 final closure.

Closure criterion:

Either:

A. backend protocol gains stronger execution semantics;

or

B. the limitation remains explicitly classified and every E9.5 product
mutation family is safely contained with no claim stronger than the
available evidence.

### Verification — Debt Checkpoint 2, 2026-08-12

Confirmed against `file_bridge.py`, which corroborates this entry in its own
prose: the module docstring states that the deployed Script Engine publishes no
claim marker, so "read and evaluating" is indistinguishable from "never read"
through the filesystem, and it records the deferred fix — a `run_<name>` marker
written before the request is read — together with why it was not applied
(recompiling the `.pts` needs PTBuilder dependencies this repository does not
redistribute). Branch A is therefore blocked by something outside the repo, and
closure realistically runs through branch B.

The "no false cancellation claims" containment is enforced structurally rather
than merely asserted: `RequestDisposition.proves_no_execution` returns `False`
for every value, and exists specifically so a caller cannot assume otherwise.

**The containment list is understated.** Python-side request retirement is a
real mitigation and is not listed: on a successful `send_and_wait`, the request
file is discarded from Python after the response is read, closing the silent
re-execution window the engine's swallowed delete would otherwise leave. For
fire-and-forget the same retirement happens through `collect_completed()`,
called at the *top* of the next `send()`. Two honest limits on that: the window
between the engine writing the response and Python unlinking the request
remains open, and the most recent fire-and-forget request is never retired
until another send occurs.

This narrows the limitation; it does not remove it, and the classification
stays BACKEND_LIMITATION.

Sufficient for Stage 3A4: 3A4 dispatches link-mode, bandwidth and serial-clock
mutations — the same families Stage 3A3 already dispatched under this
containment, each with typed readback and no blind retry. No new mutation
family is introduced that would need a fresh classification.

---

## TD-SECURITY-001 — ACL/NAT replay safety is not proven

Status:
OPEN

Severity:
P1

Discovered:
Runtime Safety R1-E

Description:

Numbered ACL generation is structurally additive:

`access-list N permit/deny ...`

The normal ACL generator does not automatically prepend:

`no access-list N`

The reset exists in a separate removal path.

This establishes:

- STRUCTURALLY_ADDITIVE
- REPLAY_SAFETY_NOT_PROVEN
- TREAT_AS_REPLAY_UNSAFE_FOR_PRODUCT_SAFETY

It does NOT establish that Packet Tracer definitely stores duplicate ACEs;
that behavior has not been measured live.

NAT paths that depend on those ACL bodies inherit the same conservative
classification.

Blocks now:
No for RIPv2.

RESOLVE_BEFORE:
next security/NAT mutation hardening work and, at latest, E9.5 final closure.

Closure criterion:

Controlled disposable PT reproduction of repeated identical ACL/NAT
application, followed by direct readback and behavioral verification.

Then classify the operation family from evidence.

### Verification — Debt Checkpoint 2, 2026-08-12

Confirmed against source, and **the scope is wider than this entry states**.

`generate_acl_cli` is purely additive, and the full dispatch payload adds no
reset either — `enable`, `configure terminal`, the ACL body, the optional
binding, `end`, `write memory`. `no access-list` exists only in
`build_remove_payload`.

The wording "the normal ACL generator" reads as though a typed enterprise path
might behave differently. It does not: `security_renderer.py` returns the
additive payload as the action **body** and `build_remove_payload` only in the
separate **cleanup** slot, so the typed security path inherits the additive
shape verbatim. `nat_cli_generator.py` emits its inline `access-list ... permit`
lines the same way, with `no access-list` again confined to cleanup.

Nothing here changes the classification — `TREAT_AS_REPLAY_UNSAFE_FOR_PRODUCT_SAFETY`
is still the right call and is still not a measurement. It widens what the
eventual live reproduction must cover: the typed security and NAT paths, not
only the standalone generator.

Does not block Stage 3A4, which dispatches no ACL or NAT mutation.

---

## TD-VOICE-001 — `create cnf-files` replay behavior is unknown

Status:
OPEN

Severity:
P2

Discovered:
Runtime Safety R1-E

Description:

The typed voice path contains:

`telephony-service create cnf-files`

This is an imperative operation whose behavior under duplicate execution has
not been measured.

Current classification:
UNKNOWN.

Blocks now:
No for RIPv2.

RESOLVE_BEFORE:
next voice hardening/acceptance pass and, at latest, E9.5 final closure.

Closure criterion:

Controlled disposable voice runtime probe determines whether repeated
execution is:

- replay-safe;
- produces additional side effects;
- or remains unobservable.

Update the product containment rule accordingly.

### Verification — Debt Checkpoint 2, 2026-08-12

Confirmed: exactly one occurrence in `src/`, emitted only for
`GeneratePhoneConfigurationFiles`, compiled at one site carrying
`required_capability=TFTP_PHONE_BOOTSTRAP`, and gated in `apply_voice.py` so an
UNKNOWN capability yields SKIPPED with `CAPABILITY_UNKNOWN` and no dispatch.

Two things this entry does not record.

**Containment is currently stronger than described, for a reason that is itself
a gap.** `apply_voice.py` resolves `capabilities = capabilities or {}` and has
**no default capability provider** — there is no `voice_capabilities.py` in the
catalog package, unlike `control_plane_capabilities.py` and
`security_capabilities.py`. So with no caller-supplied profile every voice
action resolves UNKNOWN and is skipped, and `create cnf-files` is never
dispatched at all. That is the same shape as `TD-CAPABILITY-001`, which was
resolved for the control plane only. It is not separately ledgered; it is
recorded here rather than opened as a new entry, because its practical effect
today is to *strengthen* this containment, and the voice hardening pass that
closes this debt is the natural place to resolve both together.

**One inconsistency worth carrying into that pass.** The action model declares
`operation: Literal[OperationSemantics.REPLACE]`, while this entry classifies
the replay behaviour as UNKNOWN. `OperationSemantics.EXECUTE_ONCE` exists and is
used elsewhere in the same file, so the stronger semantics was chosen
deliberately and is not evidenced. A typed `REPLACE` asserts more than the
measurement supports; the live probe must either substantiate it or the
declaration must change.

Does not block Stage 3A4, which dispatches no voice action.

---

## TD-RUNTIME-002 — `terminal_is_idle` is blinded by a trailing asynchronous syslog

Status:
RESOLVED

Severity:
P1

Discovered:
Runtime R2-0 (RIPv2 live replay qualification)

Description:

`terminal_is_idle` decides that a console has returned control by checking
that the rendered output ends with a prompt.

After `configureIosDevice` completes, IOS emits the asynchronous notice:

```text
Router>
%SYS-5-CONFIG_I: Configured from console by console
```

The syslog line lands **after** the prompt, so the buffer no longer ends with
one and the check returns False indefinitely. Measured during R2-0: still
False at t+35s, with the tail unchanged.

Runtime Safety R1-E already applied the equivalent correction to
`first_echo_line`, which skips recognisable `%FACILITY-severity-MNEMONIC:`
lines. `terminal_is_idle` never received that treatment.

Consequence:

`TypedPingExecutor` uses `IDLE_GUARD_JS`, whose JavaScript check has the same
shape. A typed ping issued after a configuration change on the same device can
be refused with `prompt_not_ready_command_in_flight` even though the CLI has
returned control.

Not affected:

`ControlledIosExecutor` registered queries, which use `getPrompt()` rather
than the output tail and are immune to a trailing syslog line.

Blocks now:
No. R2-0 completed by using `getPrompt()` readiness, the same signal the
hardened IOS executor already uses.

RESOLVE_BEFORE:
typed RIPv2 behavioural verification, because that step pings immediately
after configuring, and at latest E9.5 final closure.

Closure criterion:

Idle detection ignores recognisable asynchronous IOS syslog lines when
deciding whether the console returned control, in both the Python helper and
the JavaScript guard, with a deterministic regression covering a syslog line
arriving after the prompt.

### Resolution

Resolved: 2026-08-11, stage "Resolve TD-RUNTIME-002".

Commit subject:
`fix: tolerate trailing IOS syslog in idle detection`
on `feature/runtime-ripv2`.

What changed:

Both `terminal_is_idle` and `IDLE_GUARD_JS` now discard trailing lines that
match the recognisable `%FACILITY-severity-MNEMONIC:` shape before looking for
the prompt. The rule is the one `first_echo_line` already used; no second
syslog regex was introduced.

Evidence:

- deterministic regressions for prompt only, prompt plus `CONFIG_I`, prompt
  plus `LINK`, several consecutive notices, and the exact tail recorded live
  during R2-0;
- negative regressions holding the R1 guarantees: pager behind a notice,
  command in flight, arbitrary trailing text, `% Invalid input`, partial
  prompt, and syslog with no prompt behind it;
- a `TypedPingExecutor` regression proving the retry barrier is passed after a
  configuration notice;
- live confirmation on disposable `__MCP_PROBE_R2_IDLE_R1` (2911, PT
  9.0.1.0858): tail `Router>` followed by `%SYS-5-CONFIG_I`, with the Python
  helper and the in-Packet-Tracer JavaScript guard both reporting ready and no
  pager. Cleanup left no `__MCP_PROBE_R2_*` residue.

---

## TD-RUNTIME-003 — RIPv2 read-back is qualified against one live output shape

Status:
RESOLVED

Severity:
P2

Discovered:
Runtime R2-A (typed RIPv2 implementation)

Description:

`parse_show_ip_protocols_rip` and the RIPv2 configuration verification are
validated against the exact `show ip protocols` output captured during R2-0:
one router, one routing protocol, no IPv4-addressed RIP interface, and no
pagination.

Two shapes are implemented and unit-tested but never observed live in Packet
Tracer:

1. a device running RIP alongside another routing protocol, where
   `show ip protocols` emits several `Routing Protocol is "..."` blocks and the
   RIP block must be read in isolation;
2. a `show ip protocols` long enough to trigger the IOS pager.

Current containment:

- the parser scopes the RIP block between `Routing Protocol is` headers, so a
  neighbouring block cannot contribute networks, passive interfaces, or the
  auto-summary flag;
- a read-back flagged `truncated_by_pager` is reported UNOBSERVABLE rather than
  FAILED, so a hidden line cannot be mistaken for a missing network statement;
- both behaviours are covered by deterministic regressions and by mutation
  checks that fail when either guard is removed.

Blocks now:
No. The offline typed implementation and its verification do not depend on
either shape, and neither shape can silently produce a false VERIFIED.

RESOLVE_BEFORE:
R2-B live behavioural verification, and at latest E9.5 final closure.

Closure criterion:

Observe both shapes on a disposable Packet Tracer device and confirm that the
parser reads the RIP block correctly beside another protocol, and that a
paginated read-back is reported UNOBSERVABLE rather than FAILED. Then either
promote the fixture to live-captured evidence or correct the parser.

### Deadline status — 2026-08-11

The deadline is **active but not yet violated**, and the milestone is
unchanged.

The RESOLVE_BEFORE milestone is R2-B *completion*. R2-B did not complete: it
stopped at its hard precondition, because the product capability gate resolved
`2911:ripv2_config` to UNKNOWN and skipped every typed RIPv2 action
(`TD-CAPABILITY-001`, since resolved). R2-B therefore never reached a live
stage, and its own rules forbade both bypassing the gate with raw IOS and
injecting a fake capability.

The two output shapes were not qualified live. Neither a live result nor
NOT_REPRODUCED is claimed for them: no probe was run.

This debt MUST be resolved when R2-B resumes.

### Resolution

Resolved: 2026-08-11, stage "R2-B phase 3 — live read-back qualification".

Commit subject:
`test: qualify RIPv2 protocol readback shapes live`
on `feature/runtime-ripv2`.

Environment: PT `9.0.1.0858`, declared through
`ConfigurationRuntimeContext.evidence_backend_version` so the capability
evidence applied. RIP was applied through the real product path
(`ControlPlaneApplicator` → typed renderer → `configureIosDevice`), one
deliberate dispatch. Disposable devices only, named `MCP-PROBE-R2B-*` per the
naming contract in `TD-RUNTIME-004`.

**Shape 2 — paginated read-back: reproduced, fail-closed confirmed.**

Adding any second routing process makes `show ip protocols` exceed the pager
window on this build. The production read-back reported:

```text
truncated_by_pager = True
verification       = UNOBSERVABLE, evidence rip_readback_truncated
fresh_evidence     = False
```

Not a false VERIFIED, and not a false FAILED from the cut-off fields. This is
the contract the debt required.

**Shape 1 — RIP beside another protocol: qualified against a real capture.**

Three measured properties of PT 9.0.1.0858 constrain how this shape can be
observed at all, and each was established by a failed attempt rather than
assumed:

- the EIGRP block alone fills the ~24-line pager window;
- protocol blocks print with EIGRP before RIP, so RIP falls outside that
  window;
- `terminal length 0` dispatches successfully on the command line and Packet
  Tracer **ignores it**; a static route produces no second protocol block.

So a single production read can never expose the RIP block while a second
protocol exists on this build — which is exactly Shape 2, already fail-closed.
The full output was therefore reconstructed by walking the pager, and the
production parser was qualified against that real capture:

```text
protocol blocks : ['Routing Protocol is "eigrp  100 "',
                   'Routing Protocol is "rip"']
parsed RIP      : version 2/2, auto-summary false,
                  networks ['150.1.0.0'],
                  passive ['GigabitEthernet0/0']
```

The EIGRP block carried its own `Routing for Networks: 10.0.0.0` and
`Passive Interface(s): GigabitEthernet0/1`, printed before RIP. Neither leaked:
ten leakage checks passed, including exact network and passive-interface sets.

The capture is persisted as
`_PT_9_0_1_0858_SHOW_IP_PROTOCOLS_EIGRP_THEN_RIP` in
`tests/test_typed_ripv2_control_plane.py`, replacing the synthetic two-protocol
fixture with live evidence. It also pins that one real output carries both
indentation styles: EIGRP with spaces, RIP with TAB.

No source changed. The parser needed no correction.

Residual limit, recorded rather than glossed: on this build a device running
RIP alongside another routing protocol is **UNOBSERVABLE** through the product
read-back, because the pager truncates before RIP is reachable and cannot be
disabled. That is safe — it never yields a wrong answer — but it is a real
observability ceiling for multi-protocol devices, and a future stage that needs
RIP state on such a device will have to page through or find another query.

---

## TD-RUNTIME-004 — The typed renderer rejects the project's probe naming convention

Status:
RESOLVED

Severity:
P2

Discovered:
Resolve TD-CAPABILITY-001 (live qualification)

Description:

Every controlled probe in this project is named `__MCP_PROBE_*`, and the
standing safety rule is that only resources with that prefix may be created and
deleted.

> **Correction, added at resolution.** The second clause was never true of the
> code: no production path has ever selected devices by prefix, and deletion is
> by exact caller-supplied name. The original wording is preserved above because
> it is what this debt was opened against.

The trusted control-plane renderer validates device names with
`_SAFE_DEVICE = ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$`, which requires an
alphanumeric first character. Measured directly:

```text
__MCP_PROBE_CAP_R1   -> rejected: Invalid compiled device name
MCP-PROBE-CAP-R1     -> accepted
```

A typed control-plane action therefore cannot be rendered for a device that
follows the project's own probe convention. Earlier live stages never hit this
because R2-0 dispatched through `configure_ios` rather than the typed renderer.

Current containment:

The TD-CAPABILITY-001 live qualification used `MCP-PROBE-CAP-R1`, which is
still unmistakably a probe and was the only device created or deleted. The
safety intent — never touch user topology, delete only what was created — was
fully preserved, and cleanup left no residue.

Blocks now:
No. It did not block the live qualification.

Blocks:
any future live control-plane probe that expects the `__MCP_PROBE_*` prefix to
work end to end through the typed path, which includes R2-B as its ticket is
currently written.

RESOLVE_BEFORE:
R2-B resumption.

Closure criterion:

Reconcile the two rules deliberately: either the probe convention adopts a
prefix the renderer accepts and the standing safety rule is restated, or
`_SAFE_DEVICE` is widened with an explicit justification that it still rejects
the injection-shaped names it was written to reject. Whichever is chosen, a
regression must pin it.

### Resolution

Resolved: 2026-08-11, stage "TD-RUNTIME-004 scoped probe naming contract".

Commit subject:
`fix: define renderer-safe typed probe naming`
on `feature/runtime-ripv2`.

**The resolution is a scoped naming-contract clarification, not a renderer
relaxation.** `_SAFE_DEVICE` is byte-for-byte unchanged, and a regression pins
both that fact and the continued rejection of `__MCP_PROBE_CAP_R1` through the
typed path.

What the audit established:

- no production code anywhere selects devices by either prefix; deletion is by
  exact caller-supplied name and is idempotent on absence, so cleanup
  correctness needs a unique remembered name, never a prefix;
- isolation is proven by whole-workspace inventory fingerprint diff, in which
  names are opaque values. There is no probe-versus-user discrimination step:
  the session deletes exactly the names it created and requires the workspace
  fingerprint to converge back. The one model-based rule, `_BACKEND_MANAGED_MODELS`,
  excludes a backend-created Power Distribution Device from the fingerprint so
  restoration stays decidable; it is not a probe classifier;
- the two prefixes therefore serve human and QA recognition, not enforcement;
- the conflict was never two rules governing the same objects. Capability
  discovery probes are created through `lwAddDevice` and observed with
  registered queries, and never reach the typed renderer. A probe that must be
  rendered by a trusted renderer is a newer population that neither rule
  anticipated.

The contract now declared:

| Prefix | Created by | Traverses trusted renderers |
| --- | --- | --- |
| `__MCP_PROBE_*` | capability discovery | No |
| `MCP-PROBE-*` | disposable probes on a typed path | Yes |

Recorded in `e95-stabilization.md`, which previously claimed a single universal
namespace, and in `docs/qa/capability-probes.md`, whose residue check now
covers both.

Not changed, deliberately: the `capability_discovery.py` generator, its
`__MCP_PROBE_*` output, `_SAFE_DEVICE`, the `__MCP_E4_TEST_*` test namespace,
and every historical run record.

Evidence:

- capability discovery still emits `__MCP_PROBE_*`, proven by running the real
  use case and reading the names the runtime was asked to create;
- `MCP-PROBE-*` is accepted by both the typed control-plane renderer and the
  fault renderer. This is renderer-level only: the regressions call
  `render_action` and `render_scenario` and inspect the returned payloads.
  Nothing is dispatched and Packet Tracer is not involved;
- ten hostile shapes still reject — newline, leading and trailing space,
  carriage return, semicolon, quote, leading hyphen, leading dot, empty, and
  over-length;
- deletion is exact-name for four unrelated name shapes, with no prefix scan in
  the emitted script;
- five mutations were run against these regressions during this stage —
  widening `_SAFE_DEVICE`, renaming the discovery generator, switching deletion
  to a prefix scan, and reverting each of the two documents — and all five
  failed the suite. The prefix-scan mutation is caught by the emitted-script
  assertions, which reject `startsWith` and `indexOf` in the deletion script.

Known limits of this closure, recorded rather than glossed:

- `MCP-PROBE-*` has no producer in `src/`. Nothing in production emits or
  requires it, because a typed-path probe is created by an operator harness,
  not by the product. The contract is a declared convention with a regression
  that pins renderer compatibility, not an enforced invariant;
- two scoped statements naming only `__MCP_PROBE_*` remain outside the two
  edited documents, and both are still literally true of capability discovery:
  the `pt_probe_capabilities` docstring in `tool_registry.py` and
  `packet-tracer-capability-discovery.md`. Neither is covered by a regression.

---

## TD-PUBLIC-001 — Raw fire-and-forget tool remains publicly invokable

Status:
DEFERRED_TO_DECLARED_MILESTONE

Severity:
P2

Discovered:
Runtime Safety R1-D/R1-E

Description:

`pt_send_raw(wait_result=False)` remains publicly invokable.

It is proven to be separate from:

- RuntimeActionMutation;
- typed `configure_ios`;
- ActionExecutionStatus;
- normal typed enterprise mutation contracts.

Therefore it cannot masquerade as a successful typed enterprise mutation.

However, its public exposure is not yet governed by the future reduced
enterprise MCP surface.

Blocks now:
No.

RESOLVE_BEFORE:
Skills/public MCP facade phase.

Closure criterion:

Public-surface governance explicitly limits arbitrary raw IOS/JS to the
controlled developer/capability-investigation boundary and prevents it from
being treated as a normal enterprise operation.

### Verification — Debt Checkpoint 2, 2026-08-12

Confirmed, and sharper than written on three points:

- `wait_result: bool = False` is the **default**, so an unqualified call gets
  the un-awaited branch rather than opting into it;
- registration is unconditional. The `@mcp.tool()` decorator sits inside
  `register_tools` with no feature flag, environment gate or conditional, and
  the only precondition is a bridge-liveness check, which is not authorization;
- the tool is **advertised** as a capability through the resource registry's
  `"raw_js"` flag, and documented in the adapter README.

The separation claim holds: the raw path returns a bare string and never
constructs a `RuntimeActionMutation` or an `ActionExecutionStatus`, so it still
cannot masquerade as a typed enterprise mutation.

**Deadline is not verifiable from the repository, and that is a finding.** The
milestone is "Skills/public MCP facade phase". A `skills/` tree with seventeen
packages already exists and predates this ledger, so the deadline cannot mean
"when skills exist". The ledger's own planned-work list names a "future reduced
public enterprise MCP facade", which is the reading that makes the deadline
coherent — but no document in `docs/` defines that phase or its entry criteria,
so nothing in the repository can establish whether the deadline has arrived.
This is the same class of gap the Documentation limitation section above
records. Treated as NOT passed at CP2, on the facade reading.

Does not block Stage 3A4. Stage 3A4 must not use this tool: its rule is that a
missing production seam is named and implemented, never bypassed with raw JS or
raw IOS.

---

# Planned Work That Is Not Technical Debt

The following are planned capabilities and must not be mislabeled as debt:

- typed RIPv2 support;
- typed PC tracert/traceroute support if later scheduled;
- Stage 3A4;
- future AcceptanceEngine;
- future Diagnosis/Autofix;
- future reduced public enterprise MCP facade.

Missing planned functionality is not automatically technical debt.

---

# Resolution Log

Move an item here only when its closure criterion has been satisfied.

Do not delete historical debt entries.

- **TD-RUNTIME-003** — resolved 2026-08-11. Both remaining read-back shapes now
  have live evidence on PT 9.0.1.0858. A paginated `show ip protocols` is
  reported UNOBSERVABLE via `rip_readback_truncated`, never a false VERIFIED or
  FAILED. The two-protocol shape was captured live by walking the pager and the
  production parser reads only the RIP block from it, excluding the EIGRP
  block's own networks and passive interfaces. That capture supplements the
  synthetic fixtures rather than replacing them: the RIP-first order, where the
  parser must stop at the next block header, is still covered offline. No
  source changed. The entry above is kept in full and
  records the residual observability ceiling. The prior "deadline status" note
  remains as written.
- **TD-RUNTIME-007** — resolved 2026-08-12 at Debt Checkpoint 1. Route
  verification now reads inside a bounded convergence window of 45 s, sampled
  every 5 s, capped at 10 reads, derived from RIP's 30-second update timer and
  the R2-B phase 4 measurement. Only the read retries; configuration is never
  redispatched. Stale and truncated evidence abort immediately instead of
  consuming the budget, and every sample still requires the exact prefix,
  length and RIP source. The entry above is kept in full.
- **TD-RUNTIME-001** — resolved 2026-08-12 at Debt Checkpoint 1. The stated
  mechanism was wrong: cleanup always precedes result materialisation, so no
  snapshot was ever stale. The real defect was a false CLEAN, because
  `mark_cleanup(SUCCEEDED)` erased UNKNOWN. Historical and final state are now
  distinct, `dirty_state` is the authoritative final value, and successful
  compensation clears only what an inverse could undo. The entry above is kept
  in full.
- **TD-RUNTIME-005** — resolved 2026-08-12 at Debt Checkpoint 1. Typed
  ROUTE_PRESENT expectations for RIPv2 now carry the already-qualified route
  read-back into ControlPlaneApplicationResult. Expected prefixes derive from
  the E5 L3 identities, never from the classful RipNetwork, and a locally
  connected prefix can never satisfy a remote route expectation. **Corrected
  2026-08-12 by executed acceptance evidence**: the closure had assumed one
  expectation per prefix, but the compiler emitted one per peer pair, so with
  three routers two expectations collided on the same id. Fixed to one
  expectation per `(device, remote prefix)` and pinned by two regressions that
  compare a list against its set. Still RESOLVED, now on multi-peer evidence.
  The entry above is kept in full.
- **TD-RUNTIME-004** — resolved 2026-08-11. Two disposable namespaces are now
  declared explicitly: `__MCP_PROBE_*` for capability discovery, which never
  reaches a trusted renderer, and `MCP-PROBE-*` for probes that do. The
  resolution is a naming-contract clarification, not a renderer relaxation:
  `_SAFE_DEVICE` is unchanged and still refuses the discovery prefix through
  the typed path. Cleanup remains exact-name and prefix-independent. The entry
  above is kept in full.
- **TD-CAPABILITY-001** — resolved 2026-08-11. A control-plane capability
  catalog now derives `ControlPlaneCapabilityProfile` from live evidence
  attributed to a model, and `ControlPlaneApplicator` resolves it by default
  instead of treating an absent argument as "no evidence". Only RIPv2
  configuration and routing-process state on the 2911 carry live evidence;
  every other dimension is explicitly UNKNOWN. Confirmed by one disposable live
  qualification with a single deliberate dispatch and a verified read-back. The
  entry above is kept in full.
- **TD-RUNTIME-002** — resolved 2026-08-11. Idle detection now discards
  trailing recognisable IOS syslog lines before looking for the prompt, in both
  the Python helper and the in-Packet-Tracer JavaScript guard, reusing the rule
  `first_echo_line` already applied. Confirmed by deterministic regressions and
  by one live disposable reproduction. The entry above is kept in full.
