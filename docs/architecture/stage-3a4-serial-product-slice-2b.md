# Stage 3A4 — Serial product Slice 2B/3, and the burst reconciliation

Recorded 2026-08-17 on `feature/runtime-ripv2`.

## What this document is, stated first

This is **not** a live qualification record. Nothing in it was executed against
Packet Tracer. Slice 2A's evidence packet
([`stage-3a4-serial-product-slice-2a.md`](stage-3a4-serial-product-slice-2a.md))
remains the only live serial evidence this project holds.

Everything below is **offline-compiled and offline-verified only**:

```text
LIVE_PACKET_TRACER_RUN            = NONE
SERIAL_ORIENTATION_LIVE_OBSERVED  = NO
TRAFFIC_ATTRIBUTION_LIVE_OBSERVED = NO
OSPF_NARROWING_LIVE_OBSERVED      = NO
MODULE_REPLAY_GUARD               = MEASURED_IN_NODE / PACKET_TRACER_NOT_YET_QUALIFIED
```

## Why a reconciliation was needed

`handoff.md` declared a HARD STOP with a clean worktree at `5855585`. It was not
clean. The tree carried **36 uncommitted paths** — 29 modified, 7 untracked —
written in one ~28-minute burst on 2026-08-13, `14:28:59 → 14:57:10`, about 38
minutes after the `5855585` commit at `13:50:25`. No documentation, no commits,
and a handoff describing a state that no longer existed.

Two measurements framed the reconciliation:

| Invocation | Result |
| --- | --- |
| `python -m pytest` from the worktree root (the contract in `pyproject.toml`) | **could not collect the suite** — 3 ImportErrors, `Interrupted` |
| the same with `PYTHONPATH=<worktree>/src` (diagnostic only) | 2 failed, 1882 passed |

The burst was serialized into **nine reviewable commits**, `ea7275e..b7c131f`,
each qualified as a **commit snapshot** in a throwaway `git worktree` — not as a
dirty-tree run, because the other clusters could otherwise satisfy imports the
commit under test did not provide. That distinction caught a real defect; see
"What the isolation check found" below.

Test count across the serialization, every figure from a clean isolated
snapshot: 1815 (`5855585`, per handoff) → 1824 → 1863 → 1868 → 1872 → 1880 →
1880 → 1895 → 1897 → **1906** on the final clean tree.

## What the nine commits establish

| Commit | Establishes |
| --- | --- |
| `ea7275e` | Module insertion is guarded against same-payload replay by an in-payload receipt and an exact slot-effect pre-read |
| `79e27fc` | Every product mutation family carries a typed replay classification with structured evidence provenance |
| `0a43501` | Fault injection requires a fresh interface read-back; a successful ping never identifies the surviving path |
| `8b7d77c` | OSPF expectations claim only what a registered query establishes — without raising the aggregate claim |
| `2bee898` | Capability evidence has an exact-version production composition root |
| `43e3c57` | The domain can express WAN transit addressing and typed traffic flows |
| `5004a64` | Deployed serial DCE/DTE orientation is resolved from fresh registered read-back |
| `32c54b6` | Serial transit addressing and clock compile from an observed manifest |
| `b7c131f` | End-to-end behaviour is attributed to declared traffic flows, RIPv2 only |

### Serial orientation — Slice 2A's `UNRESOLVED` is now resolvable offline

Slice 2A recorded `SERIAL_ENDPOINT_ORIENTATION = UNRESOLVED`.
`SerialOrientationObserver` closes that as a *capability*: one registered,
read-only `show controllers` per bound endpoint, failing closed on stale,
truncated, mismatched-interface, unknown-role, or wrong-physical-hash evidence.
It never mutates E4 — a verified result is a deep-copied manifest whose semantic
hash covers the observed orientations while its physical topology hash stays the
E4 identity.

`configuration_compiler` now takes DCE/DTE **only** from that manifest binding.
Serial addressing is deterministic before deployment; which end may carry a
clock is not, because the cable decides it. Without an observed manifest the
compiler emits no clock at all rather than guessing.

```text
SERIAL_ORIENTATION_CAPABILITY  = IMPLEMENTED / OFFLINE_VERIFIED
SERIAL_ORIENTATION_EXERCISED   = NO
```

### Traffic — reachable in production for the first time

`CapacitySource.TRAFFIC_CALCULATION` was previously unreachable in production;
demand could only be supplied from hand-built intents in tests. `EnterprisePlan`
now carries `TrafficFlowIntent`, and `attribute_enterprise_traffic` maps each
flow onto the links it actually crosses, failing closed on both unreachable and
equal-cost-ambiguous paths.

Behaviour verification follows the same rule. With flows declared, RIPv2
compiles one `END_TO_END_REACHABILITY` expectation per flow whose prerequisite
is the `ROUTE_PRESENT` expectation for **that flow's destination prefix on that
flow's source device** — chosen by network containment, most specific first. A
route the flow does not use is not a prerequisite for it.

A verified route is still not forwarding evidence. The expectation keeps its own
`ROUTING_BEHAVIOR` dimension and its own `reachable`, satisfied only by a typed
ping. The prerequisite orders evidence; it does not substitute for it.

Scope, deliberately: **RIPv2 only.** OSPF and EIGRP keep their router
cross-product untouched. A generic implementation was written and then removed
because no fixture exercises it.

That scope is **sufficient for the governed Stage 3A4 reference topology**,
whose protocol is RIPv2, and is therefore **not by itself a Stage 3A4 blocker**.
Generic other-IGP flow attribution sits outside this reference closure unless a
governed E9.5 claim explicitly requires it; no such claim exists today. Record
it as a scope boundary, not as outstanding work.

## The OSPF claim ceiling — the sharpest finding

The burst narrowed OSPF `ROUTING_PROCESS` and `ROUTE_PRESENT` expectations,
dropping `router_id`, `wildcard` and `segment_id`.

**The observability half is true**, verified from source:
`_observe_ospf_process` (`enterprise_control_plane_runtime.py:1207`) reads
`show ip ospf neighbor`, which does not print the local router ID — the observer
says exactly that in its own message — and `parse_show_ip_route_ospf`
(`ios_terminal.py:743`) yields prefix, prefix length, next hop and interface,
never a wildcard or a semantic segment identity.

**The claim-ceiling half was false as written.** `_unobservable_fields` builds
its field map from `expected`, and `_direct_observation` (`:1413`) returns
VERIFIED only when every field is VERIFIED. So deleting the unmeetable fields
flipped both kinds from UNOBSERVABLE to VERIFIED **without observing anything
new**, and `apply_control_plane.py:378/381` aggregates those into the run's
`observed_status`:

| | before narrowing | after, as written | after, as landed |
| --- | --- | --- | --- |
| OSPF `ROUTING_PROCESS` | UNOBSERVABLE | **VERIFIED** | UNOBSERVABLE |
| OSPF `ROUTE_PRESENT` | UNOBSERVABLE | **VERIFIED** | UNOBSERVABLE |

`ControlPlaneVerificationExpectation.unclaimed_fields` records what an
expectation deliberately does not claim, and the observer renders those fields
UNOBSERVABLE exactly as if they were still in `expected`. The claim narrows; the
ceiling does not move.

```text
OSPF_ROUTER_ID          = UNOBSERVABLE / DECLARED_UNCLAIMED
OSPF_ROUTE_WILDCARD     = UNOBSERVABLE / DECLARED_UNCLAIMED
OSPF_ROUTE_SEGMENT_ID   = UNOBSERVABLE / DECLARED_UNCLAIMED
OSPF_PROCESS_AGGREGATE  = UNOBSERVABLE   # unchanged by the narrowing
```

RIPv2 expectations are untouched and keep all three fields.

## Module replay — measured, with its limit stated

The Slice 2A payload was a bare `addModule(...)!==true` throw. It now carries a
per-operation receipt, a fresh pre-read, and an exact slot-effect guard.
Measured in Node against an instrumented `addModule` — **not** against Packet
Tracer:

- one native call across all four post-states: accepted, rejected,
  threw-without-effect, threw-after-effect;
- a second evaluation reaches success only from a fresh slot re-read, never from
  the prior attempt; an attempt is never degraded to NO_OP;
- the global receipt store is bounded at exactly **128** entries — no
  operation-token leak.

**Known limit, declared rather than disguised:** after 128 intervening
operations evict a token, an identical resend whose effect never landed *does*
re-invoke `addModule`. It still cannot be promoted to success — the rejection
repeats — and a landed effect is caught by the exact slot pre-read regardless of
eviction (measured: zero extra native calls). The typed runtime never resends,
so reaching this needs a transport-level replay.

Exact module identity remains `UNOBSERVABLE` throughout. Port effect proves
effect, never a requested `HWIC-2T` identity.

## What the isolation check found

Qualifying each commit in a clean worktree — rather than trusting a dirty-tree
pytest run — caught a defect the symbol audit missed. The commit carrying the
fault-effect work also carried two edited assertions in an existing test,
changed from UNOBSERVABLE to VERIFIED. Those hunks belonged to the OSPF
narrowing, not to the fault-effect work, and the snapshot failed without it.

That edited assertion was itself the fingerprint of the claim upgrade described
above: the narrowing could not land without rewriting a test that asserted the
old, lower claim. The commit was amended to exclude them and re-qualified.

## Findings that did NOT survive verification

Recorded because a reconciliation that only lists confirmed findings is not
being honest about its own error rate.

- **`IPAMPlanner._wan_pairs` silently dropping mixed-media site pairs.** It does
  not: `requirements_validator.py:99` already rejects such a plan with
  `ENTERPRISE_WAN_MEDIA_CONFLICT` before IPAM runs, and
  `test_e95_serial_product_planning.py:339` pins it. The filter is defence in
  depth and now says so.
- **Wiring the capability composition root at `tool_registry.py:1532/:1552`
  would advance TD-HARDWARE-001.** It would not. Both sites live inside
  `_capability_discovery` and use `catalog.identity_for` alone, which consumes
  no evidence. See the ledger entry.

## Status

```text
MODULE_REPLAY_GUARD                 = MEASURED_IN_NODE / PACKET_TRACER_NOT_YET_QUALIFIED
REFERENCE_TOPOLOGY_PRODUCT_PLANNING = READY_OFFLINE
STAGE_3A4                           = PARTIAL
TD_ACCEPTANCE_001                   = OPEN
TD_HARDWARE_001                     = OPEN
E9_5                                = OPEN
CP3_HARD                            = NOT_STARTED / NOT_READY
```

Nothing here moves any of them. This reconciliation produced no live evidence,
and Stage 3A4 cannot close without it.

The full governed debt classification — every open entry, whether or not this
slice touched it, with its RESOLVE_BEFORE and exact closure requirement — lives
in `handoff.md`. This document deliberately does not restate it, so the two
cannot drift.

## Commit accounting

`5855585..HEAD` is **10 commits**: **9 code commits**, first
`ea7275e213349fd18b802aa4c0d2c29ca1b345dc` and last
`b7c131f685e87d2157d55bc5ae12b66de7012add`, touching only `src/` and `tests/`;
plus **1 docs-only checkpoint**, `7755c37ba39018dbff942a5b5ffa1e1c7f8fa79c`.

Use `git log 5855585..b7c131f` for the code serialization. `ea7275e..b7c131f`
is wrong — two-dot notation excludes the left endpoint and omits the first code
commit.
