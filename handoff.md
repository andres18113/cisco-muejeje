# Handoff

## Repository

- branch: `feature/runtime-ripv2`
- HEAD: see `git log -1` (latest commit is the University Acceptance milestone)
- status: clean
- tests: 1716 passing

## Completed

- **Stage 3A3** — Ethernet runtime and capacity verification: CLOSED.
- **Typed RIPv2 / R2** — CLOSED. Typed control-plane path from
  `ControlPlanePlan` through compiler, applicator, fresh readback and typed
  `ROUTE_PRESENT` verification.
- **Debt Checkpoint 1** — CLOSED.
- **University Topology Acceptance** — **PASS**. All eleven gates on PT
  9.0.1.0858: 41 devices, 41 links, RIPv2 applied once per router, all nine
  learned routes verified, all six inter-LAN directions forwarding, workspace
  restored with zero residue. Contract and result:
  `docs/architecture/university-topology-acceptance.md`.

## Current project position

- **E9.5 is NOT closed.**
- **CP2 is the next governed step.**
- Stage 3A4 (traffic + reference topology) is still pending and must not start
  before CP2.
- CP3 remains the HARD gate before E9.5 closure.

## Open debt

Authority is `docs/architecture/technical-debt.md`. Currently open:

| ID | Severity | RESOLVE_BEFORE |
| --- | --- | --- |
| TD-RUNTIME-006 | P2 | Diagnosis/Autofix work, at latest E9.5 closure |
| TD-HARDWARE-001 | P1 | E9.5 final closure |
| TD-SECURITY-001 | P1 | next security/NAT hardening, at latest E9.5 closure |
| TD-VOICE-001 | P2 | next voice hardening pass, at latest E9.5 closure |
| TD-PUBLIC-001 | P2 | Skills / public MCP facade phase |
| TD-TRANSPORT-001 | BACKEND_LIMITATION | E9.5 final closure (contained) |

None of these was due at University Acceptance. Do not start resolving debts
whose deadlines belong to later milestones.

## Next

Run **Debt Checkpoint 2**: review runtime and control-plane debt exposed by the
acceptance run, decide what CP2 must clear before Stage 3A4, and leave every
other deadline untouched. One thing worth raising there: the ledger records a
documentation limitation — there is still no formal specification of what
"University Topology Acceptance" requires, so this run was judged against a
contract written for it rather than against a governed standing definition.

## Standing constraint

The user's real university Packet Tracer file is graded coursework. Never
mutate, delete, or probe it. Live work runs only against an empty workspace,
creates only `MCP-PROBE-*` devices, and deletes exactly those by name.
