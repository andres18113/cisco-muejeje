# Handoff — Stage 3A4

## Current checkpoint

- worktree: `.claude/worktrees/runtime-ripv2`
- branch: `feature/runtime-ripv2`
- working tree: **clean** (`git status --short` empty)
- Slice 2A implementation commit: `e846175b6e2154621e89d24d0809fae0e396d24b`

### Commit accounting — from Git, not from memory

Pre-slice baseline (previous handoff's checkpoint):

```text
5855585 = 585558576bf7734e6f0cc164f6e79fe5ea8c7c4b
```

Current tip:

```text
HEAD    = 7755c37ba39018dbff942a5b5ffa1e1c7f8fa79c
```

`5855585..HEAD` contains **10 commits total**, which split into two distinct
things that must not be conflated:

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
  from `python -m pytest` at the worktree root with **no** custom `PYTHONPATH`,
  on the clean tree
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

**The current environment is `KNOWN_UNSAFE` for live mutation.** This is a
measurement on this machine at this checkpoint, not a caution.

`.venv/Lib/site-packages/_editable_impl_packet_tracer_mcp.pth` contains one
line, the **main checkout** `…\Cisco-MCP\src`. Measured now:

```text
cwd = worktree root   ->  import packet_tracer_mcp  ->  ...\Cisco-MCP\src\packet_tracer_mcp\__init__.py   [WRONG TREE]
cwd = <worktree>/src  ->  import packet_tracer_mcp  ->  ...\runtime-ripv2\src\packet_tracer_mcp\__init__.py [correct]
packet_tracer_mcp is src.packet_tracer_mcp  ->  False
both namespaces can be resident simultaneously as distinct module objects
```

So the default invocation resolves the production namespace to a **different
tree than the one under test**. A live session started that way would mutate a
real Packet Tracer workspace using code that is not this worktree's.

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
1. packet_tracer_mcp.__file__ resolves inside
   .claude/worktrees/runtime-ripv2/src/packet_tracer_mcp/
2. sys.modules contains exactly ONE of
   {packet_tracer_mcp, src.packet_tracer_mcp}
```

Both checks must run **in the executing process**, before the first mutation,
and must abort the run on failure. A preflight performed in a different process,
or inferred from a passing suite, does not satisfy this gate.

Clearing it means either invoking with `cwd` at `src/`, or reinstalling the
editable install against this worktree. Neither was done here — this slice was
entirely offline and deliberately did not touch the environment.

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
