# Handoff — Stage 3A4

## Current checkpoint

- worktree: `.claude/worktrees/runtime-ripv2`
- branch: `feature/runtime-ripv2`
- Slice 2A implementation commit: `e846175b6e2154621e89d24d0809fae0e396d24b`
- Slice 2B/3 serialization: `ea7275e..b7c131f`, nine commits
- full regression: `1906 passed, 3 pre-existing pytest deprecation warnings`,
  from `python -m pytest` at the worktree root with **no** custom `PYTHONPATH`,
  on a clean tree
- Graphify: AST graph refreshed after the last code commit — 7062 nodes,
  23890 edges, 241 communities
- worktree: clean

```text
REFERENCE_TOPOLOGY_PRODUCT_PLANNING = READY_OFFLINE
STAGE_3A4                           = PARTIAL
TD_ACCEPTANCE_001                   = OPEN
TD_HARDWARE_001                     = OPEN
E9_5                                = OPEN
```

Offline planning remains authoritative. Do not reopen it unless executed
runtime evidence directly invalidates a planning contract.

## What happened since the last handoff

The previous handoff declared a HARD STOP with a clean worktree. **It was not
clean.** The tree carried 36 uncommitted paths written in a ~28-minute burst on
2026-08-13, undocumented and uncommitted, and `python -m pytest` could not even
collect the suite.

That burst was reconciled — not discarded, not restarted — and serialized into
nine reviewable commits, each qualified as a **commit snapshot** in a throwaway
`git worktree` rather than as a dirty-tree run. Full record:
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
LIVE_PACKET_TRACER_RUN             = NONE
SERIAL_ORIENTATION_CAPABILITY      = IMPLEMENTED / OFFLINE_VERIFIED
SERIAL_ORIENTATION_EXERCISED       = NO
TRAFFIC_ATTRIBUTION                = IMPLEMENTED / OFFLINE_VERIFIED
FLOW_BEHAVIOUR_ATTRIBUTION         = RIPV2_ONLY
MODULE_REPLAY_GUARD                = MEASURED_IN_NODE / NOT_IN_PACKET_TRACER
OSPF_ROUTER_ID / WILDCARD / SEGMENT_ID = UNOBSERVABLE / DECLARED_UNCLAIMED
CAPABILITY_COMPOSITION_ROOT        = EXISTS / NO_PRODUCTION_CONSUMER
```

Nothing in this slice was executed against Packet Tracer.

## Hard gate — live import isolation

**Discovered during reconciliation, and it governs every future live run.**

`.venv/Lib/site-packages/_editable_impl_packet_tracer_mcp.pth` points at the
**main checkout**, not this worktree. Measured from this worktree's root:

```text
import packet_tracer_mcp      -> ...\Cisco-MCP\src\packet_tracer_mcp\__init__.py
import src.packet_tracer_mcp  -> ...\worktrees\runtime-ripv2\src\...\__init__.py
packet_tracer_mcp is src.packet_tracer_mcp -> False
```

A live session driven through the bare production namespace would therefore
mutate a real workspace using **code from a different tree than the one under
test**. Before any live mutation, prove both:

```text
packet_tracer_mcp.__file__  resolves inside .claude/worktrees/runtime-ripv2/src
sys.modules holds exactly ONE of packet_tracer_mcp / src.packet_tracer_mcp
```

Do not perform live work otherwise. `tests/test_worktree_isolation.py` encodes
both checks; the gate makes passing them a precondition of execution. Repairing
the environment is a named prerequisite of the next live run and was
deliberately not done here — this slice was entirely offline.

## What was intentionally not performed

- no live Packet Tracer run of any kind;
- no 41-device reference deployment;
- no serial IOS application against a real device;
- no RIPv2 live orchestration, no traffic execution;
- no CP3, no E9.5 closure;
- no Skills modification or restructuring;
- no environment/editable-install repair.

## Remaining Stage 3A4 / E9.5 blockers

1. **`TD-ACCEPTANCE-001` — the live reference run.** Rows 1–4 and 6 must be
   satisfied in **one** run. Rows 2, 3 and 6 advanced as capabilities here;
   none is exercised. This is the stage's own deliverable and its closure gate.
2. **Live import isolation.** The hard gate above must be cleared before any
   run that would satisfy blocker 1.
3. **`TD-HARDWARE-001` — no consumer.** The exact-version capability
   composition root exists and is proven, but nothing in `src/` feeds a
   capability adapter into hardware selection. `tool_registry.py:1532/:1552`
   are not the answer — they use `identity_for` alone, which reads no evidence.
4. **No MCP surface for the new use cases.** `SerialOrientationObserver`,
   `PacketTracerSerialOrientationRuntime` and `attribute_enterprise_traffic`
   are reachable from no registered tool, so an operator cannot invoke them.
5. **Flow attribution is RIPv2-only.** A closing run on any other IGP would
   have no flow-attributed behaviour.
6. **Module replay containment is unmeasured against Packet Tracer.** It was
   measured in Node against an instrumented `addModule`, and the receipt-store
   eviction limit is documented rather than closed.

## Hard stop

HARD STOP after Slice 2B/3. The next governed session must recover this handoff
and `docs/architecture/stage-3a4-serial-product-slice-2b.md` before selecting
any further Stage 3A4 slice, and must clear the live import gate before any
live work.
