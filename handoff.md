# Handoff — Stage 3A4

## Current checkpoint

- worktree: `.claude/worktrees/runtime-ripv2`
- branch: `feature/runtime-ripv2`
- working tree: **clean** (`git status --short` empty)
- Slice 2A implementation commit: `e846175b6e2154621e89d24d0809fae0e396d24b`

**The body of this file describes Slice 2B/3 and its tip `aa7cc18`. Four
governed sessions have landed since, and the MEG table below is corrected from
Git rather than left as written.** The authoritative record of MEG-4 is
`docs/architecture/stage-3a4-bounded-live-qualification.md`, whose run 4 is the
current state; the authoritative debt state is
`docs/architecture/technical-debt.md`. Where this file and those disagree, they
win.

Corrected figures, measured rather than carried forward:

```text
canonical regression   2082 passed, 3 pre-existing warnings
                       ./.venv/Scripts/python.exe -m pytest, no custom PYTHONPATH
Graphify               7806 nodes, 26696 edges, 270 communities
```

## Stage 3A4 execution — gates 1–3 CLOSED, gate 4 still open

Executed 2026-08-17 against the master mission's strict order. Naming below uses
**MEG-n** for the master's 1→7 execution order and **OAG** for its
`PHASE 4 — OFFLINE CLOSURE TESTS`, because the master's own section headings and
its order list number differently and "Phase 4" was readable as live permission.

```text
MEG-1  live import isolation ................... CLOSED   0587995, 5641445
MEG-2  capability consumer / TD-HARDWARE ....... CLOSED   ea4eb3a, 06217ac
MEG-3  product execution surface ............... CLOSED   7de805a, 6ef25bf
OAG    offline adversarial matrix .............. CLOSED   c1ea586
MEG-4  bounded live qualification ............. FAILED / CLEAN, 4 runs
MEG-5  full same-run 41/41 acceptance ......... NOT_OPENED
MEG-6  TD-ACCEPTANCE-001 closure .............. NOT_STARTED
MEG-7  Stage 3A4 closure ...................... NOT_STARTED
```

MEG-4 has now been executed five times against Packet Tracer `9.0.1.0858`, each
time failing clean with the workspace restored. Run 5 applied **17 of 17**
configuration actions on measured exact-version capability evidence: physical
deployment VERIFIED, serial orientation VERIFIED with exactly one DCE and one
DTE, serial transit addressing VERIFIED, clock on the observed DCE read back
VERIFIED. It stopped because six applied access-port actions cannot be read
back at all — this repository registers no access-port getter — so E5 ended
`partial` and only VERIFIED may carry the control plane. The "MEG-4 is blocked,
and on what" section below describes run *zero* — the state before any run —
and is history, not status.

```text
MEG_5               = NOT_OPENED
MEG_5_EXECUTION     = BLOCKED
REFERENCE_41_41_RUN = NOT_EXECUTED
```

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
