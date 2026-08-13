# Handoff

## Repository

- worktree: `.claude/worktrees/runtime-ripv2` — **this branch is not checked
  out anywhere else, and `main` does not contain E9.5**. `main` and
  `feature/runtime-ripv2` diverged; opening a fresh worktree from `main` gets a
  tree with no `docs/architecture/` at all.
- branch: `feature/runtime-ripv2`
- HEAD: see `git log -1` (latest commit is Debt Checkpoint 2)
- status: clean
- tests: 1716 passing

## Completed

- **Stage 3A3** — Ethernet runtime and capacity verification: CLOSED.
  Do not reopen or repeat it; Stage 3A4 consumes its output.
- **Typed RIPv2 / R2** — CLOSED. Typed control-plane path from
  `ControlPlanePlan` through compiler, applicator, fresh readback and typed
  `ROUTE_PRESENT` verification.
- **Debt Checkpoint 1** — CLOSED.
- **University Topology Acceptance** — **PASS**, with a bounded claim. All
  eleven gates on PT 9.0.1.0858: 41 devices, 41 links, RIPv2 applied once per
  router, all nine learned routes verified, all six inter-LAN directions
  forwarding, workspace restored with zero residue.

  ```text
  REFERENCE_TOPOLOGY_BEHAVIOR                        = PASS
  TYPED_RIPV2_PRODUCT_APPLICATION                    = PASS
  TYPED_RIPV2_PRODUCT_READBACK                       = PASS
  TYPED_RIPV2_ROUTE_LEARNING                         = PASS
  TYPED_RIPV2_FORWARDING                             = PASS
  CONTROL_PLANE_FOUNDATIONAL_REQUIREMENT_INTEGRATION = NOT_ESTABLISHED
  FULL_PRODUCT_PIPELINE_ACCEPTANCE                   = NOT_ESTABLISHED
  ```

  The physical build, addressing and host configuration were done by an
  uncommitted developer harness using raw JS and raw IOS, not by the product
  pipeline. RIPv2 and the ping probes did go through production code. Claim
  scope table: `docs/architecture/university-topology-acceptance.md`.
  Do **not** rerun the acceptance merely to upgrade that wording.
- **Debt Checkpoint 2** — CLOSED. No debt blocks Stage 3A4 start.
  Result in `docs/architecture/technical-debt.md`; dependency map in
  `docs/architecture/e95-stage-3a4-readiness.md`.

## Current project position

- **E9.5 is NOT closed.**
- **Stage 3A4 — TRAFFIC + REFERENCE TOPOLOGY is the next implementation phase.**
- CP3 remains the HARD gate before E9.5 closure.

## Open debt

Authority is `docs/architecture/technical-debt.md`. Currently open:

| ID | Severity | RESOLVE_BEFORE |
| --- | --- | --- |
| TD-ACCEPTANCE-001 | P1 | **Stage 3A4 closure** (Stage 3A4 scope) |
| TD-RUNTIME-006 | P2 | Diagnosis/Autofix work, at latest E9.5 closure |
| TD-HARDWARE-001 | P1 | E9.5 final closure |
| TD-SECURITY-001 | P1 | next security/NAT hardening, at latest E9.5 closure |
| TD-VOICE-001 | P2 | next voice hardening pass, at latest E9.5 closure |
| TD-PUBLIC-001 | P2 | Skills / public MCP facade phase |
| TD-TRANSPORT-001 | BACKEND_LIMITATION | E9.5 final closure (contained) |

Only TD-ACCEPTANCE-001 is due at Stage 3A4. Do not start resolving debts whose
deadlines belong to later milestones.

## Next — Stage 3A4

Read `docs/architecture/e95-stage-3a4-readiness.md` first. It records that there
is **no governed specification of Stage 3A4** in the repository — the phase name
is a six-word parenthetical — and reconstructs the contract from source.

The path to establish:

```text
EnterprisePlan / typed enterprise intent → hardware / configuration plans
  → compiler → TopologyPlan / DeploymentManifest
  → production physical deployment runtime → production configuration applicator
  → control-plane application → authoritative readback
  → traffic execution / measurement → typed evidence
```

The three concrete gaps, all verified:

1. **Traffic never reaches the planner.** `TrafficContribution` and
   `CapacitySource.TRAFFIC_CALCULATION` exist, but the one production caller in
   `configuration_compiler.py` never passes `traffic=`, so that source is
   unreachable outside tests. `EnterprisePlan` has no traffic field.
2. **The reference topology cannot demonstrate it.** The pinned fixture is
   compile-only and all-Ethernet; serial is the only medium where demand changes
   the selected capacity.
3. **No counters exist.** No packet, byte, error or rate readback anywhere in
   `src/`; `SHOW_INTERFACE` is registered but never dispatched, and the OBSERVED
   tier of link performance has no production caller. So 3A4 can prove a
   decision was made, applied and read back — not that a link carried a volume.

Rules: use the production seams named in the readiness map; do not use the
acceptance harness as the implementation path; do not bypass a missing seam with
raw JS or raw IOS — name it and implement it. Failure/recovery is E9 scope and
is out of 3A4.

## Standing constraint

The user's real university Packet Tracer file is graded coursework. Never
mutate, delete, or probe it. Live work runs only against an empty workspace,
creates only `MCP-PROBE-*` devices, and deletes exactly those by name.
