# GitHub corrections and governed PoE handoff

Compact continuity note for the next AI. It is not authority. Resolve any
discrepancy in this order:

```text
source + tests + evidence
> docs/reference/cp-scale/current_state.json
> handoff.md
> handoff_github_corrections.md
> logs/history
```

## BASELINE_FINAL

- Repository/branch: `andres18113/cisco-muejeje`,
  `feature/runtime-ripv2`; publish only to
  `cisco/feature/runtime-ripv2`.
- Reproducibility correction:
  `d2fd950d93eebf41f2f1166c9a452fdb1f6f669c`.
- Original fail-closed PoE baseline:
  `9dcc9183f0891de91a7e5c2532c2aa3e492219f8`.
- Governed design:
  `0c8ec25dd4783a4096f082b57387ae3ea4a5d3e4`.
- Product implementation:
  `98a6b671539fb4c67e00ff04fdcce6ef8c09e844`.
- Governance split:
  `61fc5da8e2de1ffd59ccf2e7b9423d34b8d39111`.
- The commit containing this file is documentary only; the offline operational
  gate is deliberately bound to the product implementation SHA above.

## RESULTING_POE_ARCHITECTURE

- Typed domain observation models and fail-closed rules describe candidate and
  comparison switches, exact switch/endpoint bindings, observer identity,
  UTC observation time, visible indicators, deadline, cleanup and inventory
  restoration.
- The application service captures exact Packet Tracer build/inventory,
  creates the governed fixture, requests one typed manual observation, cleans
  endpoints before switches, verifies restoration, and persists only a fully
  valid result.
- Infrastructure supplies fixture operations and governed measured-capability
  persistence. There is no checked-in LIVE runner and none was executed.
- `MeasuredCapabilityRecord` carries Packet Tracer version plus immutable
  `dimensions`; `as_evidence()` returns a defensive copy.
- Only manual verification or curated static override can authorize a manual
  delivery claim. Automated provenance cannot relabel manual observation.
- Claims require exact canonical model/build, tested bindings, candidate and
  comparison states, simultaneous count, method, observer, timestamp,
  indicators, readiness, cleanup and restoration.
- Valid same-model/build claims may union exact bindings. `poe_ports` is the
  maximum simultaneous count from one execution, never a sum across runs.
- The planner and compiler both enforce the exact switch port, endpoint model
  and endpoint port. Evidence for a phone cannot authorize an AP or camera.

## CURRENT_GOVERNANCE

`docs/reference/cp-scale/current_state.json` schema v2 separates:

```text
last_live_state != current_offline_operational_gate
```

All previous LIVE source identity, run evidence, counters, hashes, artifacts,
Voice/PVST outcomes and compatibility projection remain under
`last_live_state`. The current offline gate records:

```text
source_head           = 98a6b671539fb4c67e00ff04fdcce6ef8c09e844
poe_delivery          = unknown
poe_ports             = null
hardware_plan         = partially_resolved
canonical_composition = blocked_before_topology
router0_authorized    = false
```

Router0 is not eligible until sufficient exact PoE-delivery evidence is
obtained, reviewed and persisted.

## VALIDATION

- Required focused product matrix: `255 passed`.
- Final governance matrix: `10 passed`.
- Final full offline suite: `3711 passed, 5 warnings`; warnings are the known
  Pydantic/pytest cache and fixture-deprecation noise.
- Import preflight used this worktree's `.venv`, resolved the production module
  inside this worktree and loaded exactly `packet_tracer_mcp`.
- Independent review found three real defects: generated-JS brace imbalance,
  a vacuous malformed-claim test provider, and uncaught whitespace-invalid
  manual observations. All three were reproduced with failing tests, fixed and
  covered by the final green gates. A later fresh review was interrupted and,
  at the user's direction, was not relaunched; it is not counted as a clean
  receipt.

## DO_NOT_REDISCOVER

- `UNKNOWN != SUPPORTED`; UNKNOWN never authorizes.
- `APPLIED != VERIFIED`; `FAILED != UNOBSERVABLE != UNKNOWN`.
- Do not derive delivery from `getPower()`, `isPowerOn()`, a `-PS` suffix,
  catalog analogy, or a different endpoint/model/port.
- A derived claim cannot exceed its evidence. Partial observations authorize
  only their exact triples. Independent simultaneous capacities are not added.
- Malformed evidence of equal or greater authority blocks; stale, incomplete,
  non-canonical or inconsistent snapshots fail closed.
- Do not reopen or alter Voice, convergence, Floor1/Floor2/Floor3 or PVST
  semantics without new contradictory evidence.
- ISO/IEC 25010 and ISO/IEC/IEEE 42010 are engineering lenses only; no ISO
  certification or formal conformity is claimed.

## OPEN_DECISIONS

- Before any future LIVE mutation, an authorized operator must choose the exact
  candidate/comparison fixture scope, tested ports/bindings, observer identity
  and deadline, then confirm the live-run import gate in the mutating process.
- The physical delivery result is intentionally unknown offline. Only the
  future governed observation can determine whether its exact evidence is
  sufficient for any Router0 eligibility decision.

## REMAINING_CP_LIVE_ROUTE

```text
one governed PoE delivery qualification
-> review and persist exact evidence
-> re-evaluate canonical PoE gate
-> Router0 only if authorized
-> Router3 -> final canonical qualification
-> Voice 69/69 -> routing/control-plane -> IoT closure
-> cleanup + evidence + gates -> CP-LIVE COMPLETE
```

## AGENTS_MUEJEJE

`agents-muejeje` may provide complementary independent reviews or bounded
specialist analysis. It never substitutes for autonomous agents, deterministic
repository evidence, or Codex's final authority. Treat every external finding
as a hypothesis until reconciled with source and tests.

## NO_LIVE

This closure was entirely offline. It did not execute Packet Tracer LIVE or
Router0 CP-LIVE and did not consume LIVE budget.

## NEXT_ACTIVE_STEP

```text
RUN_ONE_GOVERNED_POE_DELIVERY_QUALIFICATION_FROM_CLEAN_GREEN_HEAD
```
