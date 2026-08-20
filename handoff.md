# Handoff — E9.5 CLOSED

## Current checkpoint

Executable state, from Git rather than from memory. **E9.5 is CLOSED**: Debt
Checkpoint 3 (HARD) was entered on 2026-08-20 and passed. The E9.5 debt closure
was measured at the commits listed under "E9.5"; the Stage 3A4 reference
acceptance ran at `cd6272d` and was NOT re-run, because no source change since
then invalidates a property only that live run can establish. CP3 changed no
source at all.

```text
branch            feature/runtime-ripv2
HEAD at measure   bb7810f   — the base CP3 ran against; the closure commit on
                              top of it is docs-only and changes no source
working tree      clean  (git status --short empty, git diff --check clean)
worktree          .claude/worktrees/runtime-ripv2   (operational location only)
interpreter       ./.venv/Scripts/python.exe        (worktree-local, authoritative)
PYTHONPATH        unset
regression        2417 passed, 3 pre-existing pytest deprecation warnings
Packet Tracer     9.0.1.0858, workspace restored: 0 semantic devices, 0 links
```

Run the suite as `./.venv/Scripts/python.exe -m pytest` from the worktree root.
The `python` on `PATH` is a different installation with no `pytest`.

**Authority order.** Current Git, source and tests win over any prose in this
file. The authoritative MEG-4 record is
`docs/architecture/stage-3a4-bounded-live-qualification.md`, whose **run 12** is
the current state and PASSES (run 13 reproduced it); the authoritative debt state is
`docs/architecture/technical-debt.md`; the runtime register is
`docs/qa/e95-runtime-debt.md`. Everything from "History below this line" onward
is Slice 2B/3 history, not status.

## MEG status

Naming: **MEG-n** is the master mission's 1→7 execution order; **OAG** is its
offline adversarial matrix.

```text
MEG-1  live import isolation ................... CLOSED   0587995, 5641445
MEG-2  capability consumer / TD-HARDWARE ....... CLOSED   ea4eb3a, 06217ac
MEG-3  product execution surface ............... CLOSED   7de805a, 6ef25bf
OAG    offline adversarial matrix .............. CLOSED   c1ea586
MEG-4  bounded live qualification ............ PASS     14854bf, runs 12-13
MEG-5  reference qualification (its opening) .. PASS     6e965fb, 63c9f18
MEG-6  TD-ACCEPTANCE-001 closure .............. CLOSED   reference acceptance
MEG-7  Stage 3A4 closure ...................... CLOSED

MEG_5               = CLOSED / PASS
MEG_5_EXECUTION     = EXECUTED
REFERENCE_41_41_RUN = EXECUTED / PASS   (41/41, first attempt, 162.4 s)
STAGE_3A4           = CLOSED
```

## Reference acceptance — the state that closed Stage 3A4

One live run of the 41-device reference through the single product entry point,
**first attempt**, no defect to fix. Full record in
`docs/architecture/stage-3a4-bounded-live-qualification.md`, "Reference
acceptance". Nothing here is inferred from MEG-4 or MEG-5.

```text
REFERENCE_RESULT       = PASS
STATUS / STOPPED_AT    = completed / completed
DURATION               = 162.4 s
SAME_RUN               = YES   one call; no evidence combined across attempts

DEVICES / LINKS        = 41 / 41   (38 straight, 3 serial), 3x HWIC-2T @ 0/0
MODELS                 = 1941 x3, 2950T-24 x2, IE-2000 x1, PC-PT x35
                         capability-driven selection, no steering
physical_topology_hash = d34103311e097ef914c8742626edbff348fd0015e8a0551afda381c33a8d6cf0

DEPLOY                 = VERIFIED, dirty_state clean, 85 items
                         manifest 41 device + 41 link bindings, all by
                         composite fingerprint
ORIENTATION            = VERIFIED
E5                     = 88 of 88 APPLIED; aggregate `partial` (truthful)
                         15 verified / 38 unobservable / 35 partial
FOUNDATIONS            = 12 declared (9 l3_interface + 3 link), all VERIFIED
                         before the runtime was touched -- see row 4 below
RIPV2_PROCESS          = VERIFIED x3, fresh_show_ip_protocols, 7 fields each
LEARNED_ROUTES         = VERIFIED x9, fresh_show_ip_route_rip, first read each
FORWARDING             = VERIFIED, reachable=True, 1 bounded measurement
CLEANUP                = 41 entries all applied, restored=True,
                         e4_identity_preserved=True
```

Independent post-run re-observation, separate process with its own G2: 0
semantic devices, 0 links, 3 backend-managed Power Distribution Devices,
Realtime confirmed by reading it rather than by setting it.

### Row 4 — the foundational-evidence record, exactly

```text
REQUIRED_FOUNDATION_COUNT = 12
REQUIRED_FOUNDATION_KINDS = l3_interface x9, link x3
FOUNDATION_STATUSES       = VERIFIED, all 12
FOUNDATION_HASHES_PRESENT = NO -- and correctly no
FOUNDATION_SOURCE         = apply_configuration real readback
CONTROL_PLANE_GATE        = PASSED, before the runtime was touched
```

`FOUNDATION_HASHES_PRESENT = NO` is a contract, not a gap, and is spelled out
because the short form reads like one. Only `kind="security"` requirements carry
a `source_hash`; a routing-only plan declares none, so
`derive_foundational_hashes` returns `{}` and
`ControlPlaneApplicator._foundation_errors` compares a hash only where one is
declared (`if requirement.source_hash and ...`). Verified against this exact
plan: 12 requirements, **0** declaring a `source_hash`, derived map empty.

What decided the gate was therefore the **statuses**, and those came from
`derive_foundational_statuses` over executed `apply_configuration` results —
there is no parameter through which a status could be supplied. The gate refused
nothing because all 12 were VERIFIED.

### Ceilings this run did not move

```text
ACCESS_PORT                  = UNOBSERVABLE, TD-ACCESSPORT-READBACK-001 OPEN
ENDPOINT_GATEWAY             = UNOBSERVABLE
CONFIGURATION_FULLY_VERIFIED = NO
MODULE_IDENTITY              = UNOBSERVABLE, TD-MODULE-SLOT-001 backend limit
```

Forwarding verified end to end and promoted nothing. A ping is not a read-back
of a VLAN membership or of a default gateway.

### Debt

```text
TD_ACCEPTANCE_001 = RESOLVED   rows 1-6 in this same run; it upgrades
                    CONTROL_PLANE_FOUNDATIONAL_REQUIREMENT_INTEGRATION and
                    FULL_PRODUCT_PIPELINE_ACCEPTANCE off NOT_ESTABLISHED
TD_HARDWARE_001   = OPEN            <- recovered from the entry, not from prose
  RESOLVE_BEFORE    = E9.5 final closure
  BLOCKS_STAGE_3A4  = NO (the entry says so in its own words)
  CRITERION         = "Capability evidence used by the enterprise resolver must
                      reconcile deterministically into eligible physical
                      hardware without model-string special casing, while
                      UNKNOWN remains UNKNOWN."
                    NOT satisfied, measured not assumed: composing the reference with no
                    store, with the exact build and with a deliberately wrong
                    build returned identical devices and identical candidate
                    lists, so this run exercised evidence at the E5 and E9
                    gates and NOT at the selection resolver. E9.5 deadline;
                    does not block Stage 3A4
```

`TD-ACCEPTANCE-001` was the only entry whose `RESOLVE_BEFORE` was Stage 3A4
closure. Every other open entry is deadlined at E9.5 or later, or is a recorded
backend limitation. **That is why Stage 3A4 closes here and not earlier.**

## MEG-4 run 12 — the current executed state

Thirteen bounded live runs against PT `9.0.1.0858`. Runs 1-11 failed clean with
the workspace restored; **run 12 completed**, and run 13 reproduced it. Run 11
is the one that made the difference: it read Packet Tracer's simulation event
list over the failing flow and turned an aggregate negative into a device, a
port and PT's own decision.

```text
MEG_4                          = PASS
STATUS / STOPPED_AT            = completed / completed
DURATION                       = 65.5 s (run 12), 65.1 s (run 13)
PHYSICAL_DEPLOYMENT            = VERIFIED   (dirty_state clean)
SERIAL_ORIENTATION             = VERIFIED   (one DCE, one DTE)
E5_ACTIONS                     = 17 of 17 APPLIED
E5_AGGREGATE                   = partial / observability_limitation
ACCESS_PORT                    = UNOBSERVABLE   (preserved, not required)
ENDPOINT_STATIC                = PARTIAL        (preserved; acceptable)
CONFIGURATION_FULLY_VERIFIED   = NO             (stated explicitly)

AUTHENTIC_FOUNDATION_GATE      = PASS
REQUIRED_FOUNDATIONS           = 4 x l3_interface + 1 x link, all VERIFIED

E9_STATUS                      = VERIFIED
RIPV2_PROCESS                  = VERIFIED, both routers
LEARNED_ROUTES                 = VERIFIED, both routers
TYPED_FORWARDING               = VERIFIED   reachable=True after 2 bounded
                                 measurements; destination_ipv4, protocol and
                                 source_device_name all VERIFIED

E4_IDENTITY_PRESERVED          = YES
SEMANTIC_INVENTORY_RESTORED    = YES  (independent re-observation, separate
                                       process: 0 semantic devices, 0 links)
PACKET_TRACER_MODE             = Realtime, confirmed by reading `before`
```

Reproduced: run 12 (65.5 s) and run 13 (65.1 s) are identical in outcome,
in the number of bounded measurements and in restoration.

## What closed it

Two product defects, both found by Packet Tracer's own simulation trace in
**run 11** rather than argued from outside. The trace read the event list over
the very flow the product had just recorded as `reachable=False`:

```text
FIRST_FAILING_DEVICE = B-EDGE-RTR-01
FIRST_FAILING_PORT   = in=Serial0/0/0
PT_DECISION          = "The next-hop IP address is not in the ARP table..."
THEN, same event list = ARP resolves; the next echo crosses router -> switch ->
                        PC and A-EDGE-RTR-01 reports
                        "The Ping process received an Echo Reply message."
```

The path worked. The measurement was premature.

1. **No convergence window on the forwarding measurement.** Every other
   observation in the control-plane runtime that depends on a plane that
   converges already had a bounded RE-READ (`_observe_rip_route`, 45 s, because
   RIP advertises every 30 s). Reachability — which depends on RIP plus ARP on
   the destination LAN plus a just-created access switch — was measured once.
   It now has the same bounded window, and the same discipline: it stops on
   **agreement**, not on a favourable answer; an unattributable window aborts
   at once as UNOBSERVABLE; nothing is ever redispatched.
   `TypedPingExecutor`'s own contract is untouched.

2. **`traffic_flow_id` was accounted as a device property.** It is the
   compiler's label for which intent flow the claim covers, and no registered
   query could return it. Inside `expected` it rendered UNOBSERVABLE on every
   reachability observation, and `_overall` turns one UNOBSERVABLE into
   PARTIAL — so E9 could never be VERIFIED regardless of the network. It moved
   to `source_traffic_flow_id`, beside `source_link_id`, which is the pattern
   the model already used for plan identifiers. The claim did not narrow: the
   four claimed device properties are exactly the previous four, and putting the
   label back into `expected` makes it count again. Both pinned by tests.

## What MEG-4 passing does NOT mean

```text
ACCESS_PORT                = UNOBSERVABLE, TD-ACCESSPORT-READBACK-001 still OPEN
ENDPOINT_GATEWAY           = UNOBSERVABLE, no PT getter exists
MODULE_IDENTITY            = UNOBSERVABLE, TD-MODULE-SLOT-001 backend limitation
CONFIGURATION_FULLY_VERIFIED = NO
```

Forwarding was measured **behaviourally**. A frame crossing a switch is not a
reading of a port's VLAN, and a host replying is not a reading of its default
gateway. The simulation trace is diagnostic and promotes nothing; the runtime
that reads it is pinned by a test that fails if it ever imports the
configuration evidence types. What the trace did change is that the segment
those two gaps own is no longer a *suspect* — it was observed carrying traffic.

## New seams from this session

```text
simulation_trace_runtime.py        PT event list -> typed observation. DIAGNOSTIC.
                                   The JS lives below the MCP facade and
                                   tool_registry imports it, so the public tool
                                   and the governed runtime cannot drift.
pre_cleanup_diagnostic             The PRODUCT invokes an observer once, after
                                   the terminal stage and before cleanup. Its
                                   output lands only in `result.diagnostics`:
                                   it cannot reach status, errors, configuration
                                   evidence or foundations, a broken observer
                                   cannot fail a run, a clean one cannot rescue
                                   one, and a BLOCKED run never calls it.
```



`source_device_name` is now established by **execution provenance**, not by a
new IOS command and never by the requested name. When a registered query's
output is read, the same script enumerates the runtime network and keeps the
single device that can have produced that session — its terminal object is the
one dispatched to, or its transcript retains the dispatch-time baseline with
the dispatched command behind it — and the output that gets parsed comes from
that device.

Refusals, not promotions:

```text
requested A, session owned by B  -> executor returns NO output; nothing can certify A
no attribution / >1 candidate    -> source_device_name stays UNOBSERVABLE
attributed, but not the manifest-bound device -> FAILED (cross-device mixing)
unknown provenance classification -> certifies nothing
manifest binding two semantic devices to one runtime target -> DeploymentIdentityError
```

Run 7 attributed 3 of 4 and left one gap; the predicate had required the
candidate transcript to *start with* the baseline. `fresh_command_window`
already measured that a fresh session need not — the pager erases its
`--More--` and long buffers roll. `38e4a8c` anchors on the retained suffix plus
the dispatched command instead, which is strictly more discriminating.

## MEG-5 — what its contract actually said, and what closed it

The one-line summary in the table used to read *"full same-run 41/41
acceptance"*, which reads as if MEG-5 **were** the reference run. It is not, and
the governed record separates them in three keys. The literal contract is in
`technical-debt.md`, twice:

* `TD-CATALOG-PORT-001`: *"MEG-5 cannot open on the 41-device reference until
  `2960-24TT` — and any other model that run selects — has a measured port
  inventory for the build it will run against."*
* `TD-CONFIG-CAPABILITY-001`: *"Qualifying the reference topology's models
  belongs to the pre-MEG-5 pass"*, and *"the 41-device reference would meet the
  same gate on its first VLAN action"*.

So MEG-5 is the **qualification that makes the reference executable**. The
reference run itself is `REFERENCE_41_41_RUN`, and it has not been started.

### What the reference actually selects

Composed offline, capability-driven, no hand-pinned candidates:

```text
1941       x3   routers, HWIC-2T@0/0 each
2950T-24   x2   access switches
IE-2000    x1   access switch
PC-PT      x35  endpoints
```

Not `2960-24TT` — that is what the *hand-pinned* reference uses, and nothing
this repository executes selects it. It stays unmeasured, and a test says so.

### Three gates, measured in order

```text
1. PORT EVIDENCE     5 refusals across 1941 and 2950T-24   ->  0
2. E5 CAPABILITY     supports_vlan unknown for 2950T-24    ->  88/88 authorised
3. E9 CAPABILITY     1941 had no control-plane profile     ->  3/3 applied
```

**Gate 1** had a circle in it: port evidence came from a device the *product* had
deployed and read back, and a model the gate refuses to deploy could never be
read back. `PortInventoryQualifier` breaks it without touching the gate — one
disposable `__MCP_PORTQUAL_*` device per (model, module state), read back through
the same production seam, then removed. It refuses to emit an inventory when the
read-back saw no interfaces, or when a declared module did not apply, and it
writes nothing: pinning a record is a versioned act, because that evidence has
to survive a checkout.

**Gate 2** exposed a real defect. `1941` came back `layer3` UNKNOWN — *"No
model-specific IPv4 probe target is available for this device"* — with `2911`
already qualified by the identical mechanism, because the probe strategy was a
hand-listed model map. Routers now come from the catalogue's category; multilayer
switches stay listed, because `switch` covers a 2950 and a 3560 and only one of
them reaches an IPv4 of its own.

**Gate 3** is R4, recorded in `ripv2-runtime-qualification.md`: two disposable
1941s over a serial WAN, production runtimes only, all four dimensions from their
own fresh read-backs, routes verified in both directions. Two faults in that
slice were mine and are written down — a class-C `network` statement that
advertises nothing, and a router LAN that stays `down/down` with nothing cabled
to it.

### What MEG-5 does NOT claim

```text
REFERENCE_41_41_RUN          = NOT_EXECUTED. Authorised is not executed.
ACCESS_PORT                  = UNOBSERVABLE, TD-ACCESSPORT-READBACK-001 OPEN
ENDPOINT_GATEWAY             = UNOBSERVABLE
CONFIGURATION_FULLY_VERIFIED = NO
MODULE_IDENTITY              = UNOBSERVABLE, TD-MODULE-SLOT-001 backend limit
2960-24TT / 3560-24PS / 2901 = UNKNOWN, untouched by this pass
```

No gate was relaxed to get here, and a test asserts an unmeasured model is still
refused by the same predicate.

## Governed debt — states as at MEG-4/MEG-5, superseded below

These are the values as they stood during Stage 3A4, kept as that record. Where
they disagree with the sections below, those win: `TD_HARDWARE_001` and
`TD_ACCESSPORT_READBACK_001` are **RESOLVED** as of E9.5 closure, recorded under
"E9.5 — every deadlined entry, discharged"; `TD_ACCEPTANCE_001` was already
**RESOLVED** earlier, at Stage 3A4 closure, recorded under "Final Stage 3A4
checkpoint".

```text
TD_ORIENTATION_PAGER_001   = RESOLVED
TD_MODULE_SLOT_001         = BACKEND_LIMITATION
TD_CATALOG_PORT_001        = RESOLVED — its MEG-5 contract is now satisfied
                             too: 1941 and 2950T-24 are measured
TD_CONFIG_CAPABILITY_001   = RESOLVED
TD_HARDWARE_001            = OPEN
TD_ACCESSPORT_READBACK_001 = OPEN — no longer diagnosis-relevant: run 11's
                             trace observed that segment carrying traffic, so it
                             is a read-back gap, not a suspect
TD_ACCEPTANCE_001          = OPEN
```

## Current blocker

```text
NONE FOR MEG-4. It PASSES at 14854bf, reproducibly.
```

## Final Stage 3A4 checkpoint

```text
MEG_4               = CLOSED / PASS
MEG_5               = CLOSED / PASS
MEG_5_EXECUTION     = EXECUTED
REFERENCE_41_41_RUN = EXECUTED / PASS / SAME-RUN
TD_ACCEPTANCE_001   = RESOLVED
STAGE_3A4           = CLOSED
```

Residuals, explicit and unmoved:

```text
TD_ACCESSPORT_READBACK_001   = OPEN
ACCESS_PORT                  = UNOBSERVABLE
ENDPOINT_GATEWAY             = UNOBSERVABLE
MODULE_IDENTITY              = existing backend ceiling (TD-MODULE-SLOT-001)
CONFIGURATION_FULLY_VERIFIED = NO
CAPABILITY_EVIDENCE          = machine-local, gitignored (`data/capabilities/`).
                               A fresh checkout resolves it UNKNOWN and refuses
                               the same plan, fail-closed. It must be
                               regenerated by the governed qualification path;
                               it may not be hand-written or assumed.

E9_5     = CLOSED   — CP3-HARD passed 2026-08-20; see "Next phase"
CP3_HARD = PASS
SKILLS   = not entered
```

Those residuals are the Stage 3A4 record and are superseded below where E9.5
work moved them: `ACCESS_PORT` is no longer UNOBSERVABLE, and
`TD-ACCESSPORT-READBACK-001` is RESOLVED. The rest stand.

## E9.5 — every deadlined entry, discharged

Recovered from each entry's own `RESOLVE_BEFORE` field rather than from a list
anyone carried forward. Six entries had a literal E9.5 deadline; all six are
discharged, and the ledger is the authority.

```text
6e88491  feat: close TD-HARDWARE-001, TD-ACCESSPORT-READBACK-001 and TD-RUNTIME-006
4ea6c1b  fix: parse standard ACLs, and measure what a repeated E8 batch actually does
9035e95  feat: discharge TD-TRANSPORT-001 branch B with a containment matrix that locks
98d139c  feat: close TD-SECURITY-001 with read-back and behaviour in one run
6d58137  feat: close TD-VOICE-001 on the outcome its criterion admits, and widen the sweep
81894e4  fix: four ways the voice pass could have answered reassuringly, and two blind spots
```

```text
TD-RUNTIME-006              RESOLVED   journal composition, 0 divergences over
                                       11 200 reachable sequences
TD-ACCESSPORT-READBACK-001  RESOLVED   SwitchPort object read-back, 3 controls
TD-HARDWARE-001             RESOLVED   real probe evidence moved eligibility
TD-SECURITY-001             RESOLVED   read-back AND behaviour, one run
TD-VOICE-001                RESOLVED   measured, and UNOBSERVABLE on this build
TD-TRANSPORT-001            BACKEND_LIMITATION, branch B discharged
```

Nothing else in the ledger carries an E9.5 deadline. `TD-MODULE-SLOT-001`
remains a recorded backend limitation past its own MEG-4 deadline, and
`TD-PUBLIC-001` is deferred to the Skills/public-facade phase, which is not this
one.

### What was measured live, and what it cost

Five bounded qualifications on Packet Tracer `9.0.1.0858`, each on its own
disposable resources, each cleaned up and compared against its baseline:

```text
access-port read-back   2950T-24, 3 controls, re-run after the type fixes
capability discovery    3560-24PS, multilayer inter-VLAN forwarding demonstrated
security replay         1941, ACL + NAT twice, then again with a 2-endpoint slice
voice replay            2811, create cnf-files twice, every observer silent
workspace, at the end   0 semantic devices, 0 links
```

The 41-device reference acceptance was **not** re-run. No source change
invalidated a property only that run can establish; the four claims it carries —
selection, deployment, foundations, forwarding — are untouched by this work.

### Defects found and fixed on the way

Each was found by doing the work, not by looking for it:

- the multilayer probe's retry budget was consumed by its own first
  measurement, so `0/0` retries meant "could not", not "did not need to". That
  single defect was what kept `TD-HARDWARE-001` without evidence;
- `parse_show_access_lists` attributed a standard ACL's ACE to the previous
  **extended** list, so a filter ACL with no rules could have verified from the
  NAT translation list's entry;
- an exception escaping the access-port qualification left a probe switch in the
  operator's workspace. It happened; it was removed through the product's own
  path, and the disposable is now registered for cleanup the moment it exists;
- adversarial review caught two weakenings in the journal composition and one
  place where an unreadable value was reported as a contradiction rather than as
  unobservable. All three were fixed before their commit;
- the mutation-containment sweep scanned one directory, which would have let a
  dispatcher outside `infrastructure/execution/` sit unclassified. It walks the
  package now.

### What did NOT move

```text
ACCESS_PORT                  observable now, but only for the fields listed in
                             TD-ACCESSPORT-READBACK-001; DHCP_POOL untouched
ENDPOINT_GATEWAY             UNOBSERVABLE, unchanged
MODULE_IDENTITY              TD-MODULE-SLOT-001 backend ceiling, unchanged
CONFIGURATION_FULLY_VERIFIED NO
CAPABILITY_EVIDENCE          machine-local and gitignored. A fresh checkout
                             resolves every capability UNKNOWN and refuses the
                             same role fail-closed. Regenerate it through the
                             governed qualification path; never by hand
```

## Next phase

**DEBT CHECKPOINT 3 — HARD**, which `technical-debt.md` defines as the gate
*before declaring E9.5 CLOSED*. It was entered on 2026-08-20 and **passed**.

Its ledger-side requirements were measurable and held: P0 open debt 0, every P1
entry RESOLVED, and both remaining backend limitations carrying an explicit
containment and claim ceiling. The part that needed judgement rather than a scan
— which of the runtime register's UNKNOWN rows invalidate a final E9.5 claim,
and which of them E10 depends on — was decided row by row.

```text
E9_5     = CLOSED — CP3-HARD passed, 2026-08-20
CP3_HARD = PASS   — was READY
SKILLS   = not entered
NEXT     = NOT_START_E10
```

**The result, in one paragraph.** All 33 register rows carrying an open UNKNOWN
(31 UNKNOWN-state, plus the residual scopes on `Modules` and `Phone UI call
adapter`) were classified against the current typed contracts. **None blocks
E9.5, and none moved.** Five promotions were proposed on the strength of E9.5's
five live qualifications and an adversarial pass refuted all five — in each case
the evidence measured a different claim, model or protocol than the row it was
offered for. 29 rows are NO_E9_5_CLAIM_DEPENDS, 2 are OUTSIDE_E9_5_CLAIM (HTTPS
behavior, NTP sync), and 2 are DEFERRED_TO_E10 (EIGRP adjacency, EIGRP routes).

**One row outside that set was reconciled, and review found it, not the
checkpoint.** `RIP end-to-end forwarding` still read `MEASURED — FAILED` from
run 10 with "no cause established", while runs 12/13 and the reference
acceptance had measured `reachable = True` and run 11 had established the cause
— a premature measurement with no convergence window, fixed in product code.
The register now records the run-12/13 state. A checkpoint that scrutinises only
what it is asked to promote will miss what it should have promoted; that is
recorded in the ledger rather than smoothed over.

**Why the recommendation is `NOT_START_E10`.** E10 owns protocol redistribution,
which reads routes learned by a source protocol, so it depends on a second
protocol's adjacency and route observability — and both remain UNKNOWN. That
gates E10's start without holding E9.5 open: qualifying EIGRP is unstarted work
belonging to the milestone that needs it, not an unresolved E9.5 defect. The
argument rests on the register's own Update discipline, which prescribes
`NOT_START_E10` and nothing further — **not** on CP2 as precedent. CP2 carries
no requirement clauses, so its closing proves nothing about a HARD gate whose
clauses are numeric zeroes.

`OSPF failover` and `OSPF recovery` also remain UNKNOWN and E9 scope. CP2
instructed that no later milestone may treat them as discharged there, so CP3
names them rather than absorbing them silently: it did not advance them and does
not discharge them.

Full record: `docs/architecture/technical-debt.md`, "Debt Checkpoint 3 — HARD —
result"; recommendation in `docs/qa/e95-runtime-debt.md`.

Closure changed no source. The 41-device reference acceptance was not re-run,
because nothing it establishes was invalidated.

## Operating constraints, still in force

- the main agent is the implementation owner; read-only subagents may audit,
  but must not edit the same seam;
- no Skills modifications; E9.5 did not enter them either;
- no 41/41 reference run until it is deliberately opened; MEG-4, MEG-5 and the
  E9.5 debt closure are all done and none of them authorises starting it as a
  side effect;
- no raw IOS or raw JS product bypass; no harness-performed mutation;
- no fabricated identity, capability, foundation or readback evidence;
- current source, tests and Git beat stale historical prose — including this
  file's history sections.

Production code carries no dependency on Claude, `.claude`, a worktree name or
an absolute filesystem path. `PT_MCP_GOVERNED_ROOT` stays an operator-declared,
process-local input.

---

# History below this line

Everything that follows is the Slice 2B/3 record and the pre-run-1 analysis,
kept verbatim. It is **not** status: where it disagrees with the checkpoint
above or with the documents that checkpoint cites, they win. In particular
the "MEG-4 is blocked, and on what" section describes the state before any
live run existed.

Suite 1906 → **1964 passed**, 3 pre-existing warnings. Terminal gate green:
`--collect-only`, full run, `compileall -q src`, `git diff --check`,
`git status --short` all clean on the terminal state.

### What each gate established

**MEG-1.** The earlier `KNOWN_UNSAFE` diagnosis was measured against the wrong
interpreter and is corrected above. `ENVIRONMENT_REPAIR = NONE_REQUIRED`,
determined by re-measurement, not assumed — no repository state and no local
environment state was changed. The executable gate now proves three things in
the mutating process and fails closed: interpreter, tree, single identity. The
third is the one reproducible today, and the observation never creates what it
observes — the resolver reads `sys.modules` instead of importing.

**MEG-2.** `application/use_cases/plan_enterprise_hardware.py` is the first
production caller of both the exact-version composition root and
`HardwarePlanner`. Graphify confirmed beforehand that all 47 inbound
`HardwarePlanner` edges came from tests.
`PHASE_2_IMPLEMENTATION = COMPLETE / OFFLINE_QUALIFIED`;
**`TD_HARDWARE_001` stays `OPEN`** — seeded stores prove wiring and negative
semantics, not machine evidence.

**MEG-3.** `execute_enterprise_reference` is the single product execution entry
point and owns the whole live lifecycle. A harness may start it and collect
evidence; it may not order the stages. `compose_enterprise_reference` is the
pure offline half beneath it and, from a semantic intent, reproduces the
governed reference shape — **41 devices, 41 links, 3 serial WAN links** — with
hardware chosen from the whole catalogue rather than hand-pinned.
One offline MCP tool (`pt_compose_enterprise_reference`) makes the flow
operator-inspectable; MCP *mutation* exposure stays deferred under TD-PUBLIC-001.

**OAG.** Three rows added that could not exist while the sequence lived in a
harness — failed E5 never mutates E9, cleanup after failure verified by
re-observation, foreign objects never deleted. Eleven other rows were cited to
their existing owners rather than duplicated. It found one real defect: the
configuration gate compared against a non-existent enum member and now requires
**VERIFIED**, since APPLIED is not evidence of effect.

### MEG-4 is blocked, and on what

Two findings, both from executed offline evidence:

1. **Model steering.** Capability-driven selection picks `1941` for the bounded
   shape, and the control-plane capability catalogue holds live evidence only
   for `2911`. RIPv2 on 1941 is therefore UNKNOWN and the compiler refuses —
   correct behaviour, and "UNKNOWN is not permission" working end to end. The
   bounded live run must **steer selection to 2911** rather than trust the
   catalogue to choose it. Pinned by a passing assertion in the OAG matrix.
2. **Operator declaration and workspace classification.** `PT_MCP_GOVERNED_ROOT`
   is declared by the operator by design, and is unset. Packet Tracer is running
   (two instances) with a live bridge on `127.0.0.1:9080`. G3 requires a complete
   read-only inventory, an exact build confirmation and a workspace
   classification, and mandates **HARD STOP** if any semantic, manual, user or
   graded topology is present. That classification has not been performed and
   cannot be assumed.

No Packet Tracer mutation was attempted. `LIVE_PACKET_TRACER_RUN = NONE` still
holds, and every claim in this section is offline.

### Commit accounting — from Git, not from memory

Pre-slice baseline (previous handoff's checkpoint):

```text
5855585 = 585558576bf7734e6f0cc164f6e79fe5ea8c7c4b
```

Current tip:

```text
HEAD    = aa7cc18dfe201dad068a4e82999b41a8b48d2cd3
```

`5855585..HEAD` contains **11 commits total**: the 9 code commits plus **two**
docs-only checkpoints, `7755c37` and `aa7cc18`. An earlier revision of this file
recorded the tip as `7755c37` and the count as 10 — it was written by `aa7cc18`
itself and did not update its own tip pointer. Corrected from Git.

The split that must not be conflated:

| | Count | Boundary commits | Touches |
| --- | --- | --- | --- |
| **Code serialization** | **9** | first `ea7275e213349fd18b802aa4c0d2c29ca1b345dc`, last `b7c131f685e87d2157d55bc5ae12b66de7012add` | `src/` and `tests/` only — zero doc paths |
| **Governed doc checkpoint** | **1** | `7755c37ba39018dbff942a5b5ffa1e1c7f8fa79c` | 6 doc paths only — zero `src/` or `tests/` |

**Range notation matters.** `ea7275e..b7c131f` is *not* the code serialization:
two-dot range notation excludes its left endpoint, so that expression omits the
first code commit. The correct expressions are:

```text
git log 5855585..b7c131f      # the 9 code commits
git log 5855585..HEAD         # the 9 code commits + the doc checkpoint
git show 7755c37              # the doc checkpoint alone
```

The nine code commits, in order:

```text
ea7275e feat: guard module insertion against same-payload replay
79e27fc feat: classify every product mutation family in a typed registry
0a43501 feat: require a fresh interface read-back before claiming fault injection
8b7d77c fix: narrow OSPF expectations without raising the aggregate claim
2bee898 feat: give capability evidence an exact-version production composition root
43e3c57 feat: give the enterprise domain WAN transits and typed traffic flows
5004a64 feat: resolve deployed serial orientation from fresh registered read-back
32c54b6 feat: compile serial transit addressing and clock from observed orientation
b7c131f feat: attribute end-to-end behaviour to declared traffic flows
```

The final clean checkpoint is `7755c37` — the docs-only commit. It is the state
this handoff describes. It is **not** part of the code serialization and adds no
executable change.

### Verification state

- full regression: `1906 passed, 3 pre-existing pytest deprecation warnings`,
  from **`./.venv/Scripts/python.exe -m pytest`** at the worktree root with
  **no** custom `PYTHONPATH`, on the clean tree.

  Earlier revisions of this file wrote that command as bare `python -m pytest`.
  That was wrong and is corrected here: measured on this machine, the `python`
  on `PATH` is a separate installation with **no `pytest` installed**, so the
  shorthand fails outright. Only the worktree-local `.venv` reproduces the
  baseline. This is documentation drift only — the 1906 figure itself was
  re-verified at `aa7cc18` and is unchanged
- each of the nine code commits was additionally qualified as a **commit
  snapshot** in a throwaway worktree, not as a dirty-tree run
- Graphify: AST graph refreshed after `b7c131f` — 7062 nodes, 23890 edges,
  241 communities

### Governed status

```text
MODULE_REPLAY_GUARD                 = MEASURED_IN_NODE / PACKET_TRACER_NOT_YET_QUALIFIED
REFERENCE_TOPOLOGY_PRODUCT_PLANNING = READY_OFFLINE
STAGE_3A4                           = PARTIAL
TD_ACCEPTANCE_001                   = OPEN
E9_5                                = OPEN
CP3_HARD                            = NOT_STARTED / NOT_READY
```

Note on `CP3_HARD`: the ledger contains **no governed CP3 definition**. `CP3`
appears exactly twice in `technical-debt.md`, both inside TD-ACCEPTANCE-001's
`RESOLVE_BEFORE`, and only to state that the deadline is *not* deferred to CP3.
Whoever opens CP3 must define it first; it cannot be inherited from this file.

Offline planning remains authoritative. Do not reopen it unless executed
runtime evidence directly invalidates a planning contract.

## What happened since the last handoff

The previous handoff declared a HARD STOP with a clean worktree at `5855585`.
**It was not clean.** The tree carried 36 uncommitted paths written in a
~28-minute burst on 2026-08-13, undocumented and uncommitted, and
`python -m pytest` could not even collect the suite.

That burst was reconciled — not discarded, not restarted — and serialized as
recorded above. Full record:
`docs/architecture/stage-3a4-serial-product-slice-2b.md`.

```text
STAGE 3A4 — SERIAL PRODUCT SLICE 2B/3
ORIENTATION + TRANSIT ADDRESSING + TYPED TRAFFIC + E5 COMPOSITION
```

Slice 2A's `SERIAL_ENDPOINT_ORIENTATION = UNRESOLVED` is now resolvable from a
registered read-only `show controllers` per bound endpoint, and the compiler
refuses to emit a serial clock without an observed manifest binding.
`CapacitySource.TRAFFIC_CALCULATION`, previously unreachable in production, is
now reachable through typed `TrafficFlowIntent` and path attribution.

Evidence boundaries:

```text
LIVE_PACKET_TRACER_RUN                 = NONE
SERIAL_ORIENTATION_CAPABILITY          = IMPLEMENTED / OFFLINE_VERIFIED
SERIAL_ORIENTATION_EXERCISED           = NO
TRAFFIC_ATTRIBUTION                    = IMPLEMENTED / OFFLINE_VERIFIED
FLOW_BEHAVIOUR_ATTRIBUTION             = RIPV2 — SUFFICIENT FOR THE GOVERNED REFERENCE
MODULE_REPLAY_GUARD                    = MEASURED_IN_NODE / PACKET_TRACER_NOT_YET_QUALIFIED
OSPF_ROUTER_ID / WILDCARD / SEGMENT_ID = UNOBSERVABLE / DECLARED_UNCLAIMED
CAPABILITY_COMPOSITION_ROOT            = EXISTS / NO_PRODUCTION_CONSUMER
```

Nothing in this slice was executed against Packet Tracer.

### Flow attribution scope — corrected

Flow-keyed behaviour attribution is implemented for **RIPv2**. That is the
protocol of the governed Stage 3A4 reference topology, so:

- RIPv2-only flow attribution is **sufficient** for the governed Stage 3A4
  reference topology, and is **not by itself a Stage 3A4 blocker**;
- generic other-IGP flow attribution is **outside this reference closure**
  unless a governed E9.5 claim explicitly requires it. No such claim exists
  today;
- OSPF and EIGRP keep their router cross-product behaviour, unchanged. A
  generic implementation was written and removed because no fixture exercises
  it, and untested code is worse than absent code.

Do not record this as an outstanding blocker. Record it as a scope boundary.

## Hard gate — live import isolation

**Re-measured at `aa7cc18`. The earlier `KNOWN_UNSAFE` diagnosis was measured
against the wrong interpreter and is corrected below.** The gate itself is not
relaxed — it is made precise.

The file the previous revision cited,
`.venv/Lib/site-packages/_editable_impl_packet_tracer_mcp.pth`, **does not exist
in this worktree's venv.** It exists only in the *main checkout's* venv. This
worktree has its own `.venv`, carrying `_r2_worktree_editable.pth` whose **first
line is this worktree's `src`**, followed by the main venv's `site-packages` for
dependencies only. Nested `.pth` files are not processed recursively by
`site.addpackage`, so the main checkout's `src` never reaches `sys.path` here —
measured `False`.

Measured now, per interpreter:

```text
worktree .venv   -> import packet_tracer_mcp -> ...\runtime-ripv2\src\...\__init__.py  [CORRECT, any cwd]
main checkout .venv -> import packet_tracer_mcp -> ...\Cisco-MCP\src\...\__init__.py   [WRONG TREE]
PATH python      -> import packet_tracer_mcp -> ModuleNotFoundError  (and no pytest)
```

So the hazard is **not** "this worktree's environment is poisoned." It is that
**three interpreters are reachable and only one is correct**, and nothing in the
repository pins which one runs. That is the first thing the gate must check.

The second hazard is real, interpreter-independent, and was understated.
Measured on the **correct** venv:

```text
bare -> ...runtime-ripv2\src\packet_tracer_mcp\__init__.py
src. -> ...runtime-ripv2\src\packet_tracer_mcp\__init__.py
same file   -> True
same object -> False
CapabilityStatus.SUPPORTED is CapabilityStatus.SUPPORTED  ->  False
```

Two distinct module objects over the *same files*. Every cross-namespace
`isinstance`, enum identity and registry-singleton check silently misfires. This
survives choosing the right interpreter and is what the preflight must refuse.

```text
ENVIRONMENT_REPAIR = NONE_REQUIRED
```

Determined, not assumed: the governed invocation already resolves the production
namespace inside this worktree, so there is nothing to repair. Rewriting the main
checkout's `.pth`, or reinstalling the editable install against this worktree,
were rejected as **unsafe** — they would break the main checkout and the other
worktrees — not as "repair forbidden." No repository state and no local
environment state was changed by this determination.

### Static namespace tests are not a live preflight

`tests/test_worktree_isolation.py` is a **static/suite-level** guard. It proves
two things, and only those two:

- no test file imports the bare namespace (AST scan);
- there **exists** an invocation — `cwd` at `src/` — under which the bare name
  resolves locally, and under which only one identity loads.

It does **not** prove that any particular live process is isolated, because it
constructs its own subprocess with its own `cwd`. **Do not cite a green
`test_worktree_isolation.py` as evidence that the live environment is currently
isolated.** It is not: the measured bare import from the default working
directory still resolves to the main checkout.

### Required executable live preflight

Before **any** Packet Tracer mutation, the process that will perform the
mutation must itself prove, at runtime:

```text
1. sys.executable is the worktree-local .venv interpreter
2. packet_tracer_mcp.__file__ resolves inside
   .claude/worktrees/runtime-ripv2/src/packet_tracer_mcp/
3. sys.modules contains exactly ONE of
   {packet_tracer_mcp, src.packet_tracer_mcp}
```

Check 1 is an addition beyond the previous two: interpreter choice is what
decides checks 2 and 3, so leaving it implicit made the gate depend on an
unstated assumption.

All three must run **in the executing process**, before the first mutation, and
must abort the run on failure. A preflight performed in a different process, or
inferred from a passing suite, does not satisfy this gate.

Clearing it means invoking through the worktree's own `.venv`. Invoking with
`cwd` at `src/` is no longer necessary — that was a workaround for the
misdiagnosed `.pth` and does nothing for check 3.

## What was intentionally not performed

- no live Packet Tracer run of any kind;
- no 41-device reference deployment;
- no serial IOS application against a real device;
- no RIPv2 live orchestration, no traffic execution;
- no CP3, no E9.5 closure;
- no Skills modification or restructuring;
- no environment/editable-install repair.

## Governed debt — current classification

Read from the current `docs/architecture/technical-debt.md` and
`docs/qa/e95-runtime-debt.md` at this checkpoint. **Nothing below is marked
resolved without current evidence**, and nothing is omitted merely because
Slice 2B/3 did not touch it.

| Item | Current classification | Blocks Stage 3A4? | Blocks E9.5? | RESOLVE_BEFORE | Exact current closure requirement |
| --- | --- | --- | --- | --- | --- |
| **TD-ACCEPTANCE-001** | `OPEN`, P1 | **YES** | **YES** (via Stage 3A4) | Stage 3A4 closure — explicitly *not* E9.5 closure and *not* CP3 | One live reference-topology run in which **every** University-harness bypass is eliminated; rows 1–4 **and** 6 satisfied **in the same run**. A harness may orchestrate but must not perform mutations, and no missing seam may be worked around with raw JS/IOS. |
| **TD-HARDWARE-001** | `OPEN`, P1 | **NO** — ledger: "No for the pinned reference topology" | **YES** | E9.5 final closure | Capability evidence used by the enterprise resolver must reconcile deterministically into eligible physical hardware without model-string special casing, while UNKNOWN remains UNKNOWN. Slice 2B/3 built the exact-version composition root and proved it; **no production consumer exists** — nothing in `src/` feeds a capability adapter into hardware selection. The "3650 has multilayer runtime evidence" claim remains unsubstantiated. |
| **TD-SECURITY-001** | `OPEN`, P1 | **NO** — "No for RIPv2" | **YES** | next security/NAT mutation hardening work, and at latest E9.5 final closure | Controlled disposable PT reproduction of repeated identical ACL/NAT application, followed by direct readback and behavioural verification. Slice 2B/3 re-registered `pt_apply_acl (ACLPlan)` as `TREAT_AS_REPLAY_UNSAFE` with `NONE_ESTABLISHED` containment; that is classification, **not** closure. |
| **TD-VOICE-001** | `OPEN`, P2 | **NO** — "No for RIPv2" | **YES** | next voice hardening/acceptance pass, and at latest E9.5 final closure | Controlled disposable voice runtime probe determining whether repeated `create cnf-files` execution is replay-safe, produces additional side effects, or remains unobservable; then update the product containment rule. |
| **TD-TRANSPORT-001** | `BACKEND_LIMITATION` | **NO** — "No for RIPv2 qualification, provided RIPv2 proves replay-safe under the current transport" | **YES** | E9.5 final closure | Branch **A** (backend protocol gains stronger execution semantics) or branch **B** (limitation stays explicitly classified and every E9.5 product mutation family is safely contained with no claim stronger than the evidence). CP2 recorded that A is blocked outside this repository, so closure realistically runs through B. |
| **TD-RUNTIME-006** | `OPEN`, P2 | **NO** — not reachable through any current applicator | **YES** | Diagnosis/Autofix work, and at latest E9.5 final closure | Either the journal explicitly refuses the two unreachable orderings, or the composition accounts for a recorded cleanup verdict so a later `append` or preflight marker cannot contradict it. A regression must cover **both** sequences. |
| **TD-PUBLIC-001** | `DEFERRED_TO_DECLARED_MILESTONE`, P2 | **NO** | **NO** — its milestone is not E9.5 | Skills/public MCP facade phase | Public-surface governance explicitly limits arbitrary raw IOS/JS to the controlled developer/capability-investigation boundary and prevents it from being treated as a normal enterprise operation. |
| **E9 failure/recovery final classification** | `UNKNOWN` — E9 scope | **NO** — explicitly out of Stage 3A4 scope per the readiness doc | **YES** — every register row needs one final classification before the E9.5 recommendation | E9.5 final recommendation | Live failover and live restore/recovery evidence. Register rows: OSPF failover `PENDING_ROOT_CAUSE_AND_LIVE_FAILOVER`; OSPF recovery `PENDING_LIVE_RESTORE_AND_RECOVERY`. **Not a CP2 prerequisite and not discharged by CP2** — no later milestone may treat it as satisfied there. |
| **E9 runtime UNKNOWNs (register)** | **36** register rows still carry `UNKNOWN` in `docs/qa/e95-runtime-debt.md`. Exactly **2** rows carry a final closure classification: *Modules* → `BACKEND_LIMITATION_CONFIRMED` (exact module identity on PT `9.0.1.0858`/2911 only), and *Phone UI call adapter* → `ARCHITECTURALLY_RESOLVED` for the boundary, with its live call behaviour still `UNKNOWN` | **NO** for the RIPv2 reference | **YES** | E9.5 final recommendation | Each row must end in exactly one project-level closure classification with an evidence reference. Rows most relevant to a future CP3: HSRP direct role readback; OSPF failover; OSPF recovery; EIGRP adjacency, routes, behavior and failover. Never bulk-promote related rows — the register's own update discipline forbids it. |

Slice 2B/3 **resolved none of the above.** It advanced TD-ACCEPTANCE-001 rows
2, 3 and 6 as *capabilities only*, with no live evidence.

## Non-debt blockers introduced or confirmed by this slice

1. **Live import isolation** — environment `KNOWN_UNSAFE`; executable preflight
   required before any mutation. See the hard gate above.
2. **No MCP surface for the new use cases.** `SerialOrientationObserver`,
   `PacketTracerSerialOrientationRuntime` and `attribute_enterprise_traffic`
   are reachable from no registered tool, so an operator cannot invoke them and
   no live run can exercise them.
3. **Module replay containment is not Packet Tracer qualified.** It was measured
   in Node against an instrumented `addModule`; the receipt-store eviction limit
   is documented rather than closed.

## Next governed phase

```text
LIVE CLOSURE PRECONDITIONS
  → import isolation
  → production capability consumer / TD-HARDWARE
  → real product E4→E5→E9/MCP composition
  → bounded live qualification
  → full same-run reference acceptance
```

Each arrow is a precondition of the next, not a parallel track. In particular a
bounded live qualification must not be attempted before the import gate is
cleared, and full same-run reference acceptance is the only thing that can close
`TD-ACCEPTANCE-001`.

## Hard stop

HARD STOP after Slice 2B/3. The next governed session must recover this handoff
and `docs/architecture/stage-3a4-serial-product-slice-2b.md` before selecting
any further Stage 3A4 slice, and must clear the live import gate before any
live work.
