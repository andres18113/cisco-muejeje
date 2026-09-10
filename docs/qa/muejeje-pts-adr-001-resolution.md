# ADR-001 — resolution record

**Status: `ACCEPTED` · Strategy B `EXECUTED`.**

This is the resolution of
[ADR-001 — branch realignment](muejeje-pts-adr-001-branch-realignment.md), which
remains at `PROPOSED` **by design**: it is the historical audit that produced the
recommendation, and it is accurate as of its own timestamp. Nothing in it is
rewritten here. This record states only what was decided and what was done.

## Decision

Strategy **B** — recreate `feature/muejeje-pts` from the approved baseline and
selectively replay only the valid, adapted work — accepted and executed.

Strategies A, C and D were rejected for the reasons in §4 of the audit. The
deciding facts: the conflict surface between the six feature commits and the 75
baseline commits was measured as empty, and the branch existed on no remote, so
history could be shaped without cost to anyone.

## Lineage

| | |
| --- | --- |
| Old feature HEAD | `e2d912b5fe8c67077c6b753e634967f626393d87` |
| Old merge-base with the baseline | `a384a79f53215436f636e8f3b989365caa16e540` (75 behind / 6 ahead) |
| Baseline re-parented onto | `refactor/cp-live-m0-baseline` @ `e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43` |
| New merge-base with the baseline | `e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43` — the baseline itself |
| Safety ref preserving the old line | `muejeje-pts-prealign-e2d912b` → `e2d912b5…` (local) |

The rebuilt branch descends from `e9e26b3f…` directly. It carries no merge with
the old line and no commit from it: the recovered work was reconstructed, not
cherry-picked.

## Replay outcome

| Old commit | Disposition |
| --- | --- |
| `45dee1d` docs preflight | adapted — stale watermark and branch-role table removed |
| `2134aed` build audit | adapted — replayed with the later hardening folded in, so no revision ever makes PTBuilder a required build input |
| `9d88f2f` owned-V5 plan | not replayed — unresolved design |
| `1344789` owned V5 executor | not replayed — preserved on the safety ref for later architectural review |
| `876e584` mixed WIP | split — reference-input removal and hardening kept; the attribution deletion dropped; the revert re-decided |
| `e2d912b` stale closure | dropped |

## What this decision did **not** create

The CP LIVE baseline was used **once**, as an initial ancestry correction.

- It created **no continuous-upstream relationship.** Muejeje does not track,
  follow, or re-sync with `refactor/cp-live-m0-baseline`,
  `feature/runtime-ripv2`, or any other branch.
- Future CP LIVE commits do not automatically block Muejeje work. A CP LIVE
  change matters here only when it changes something Muejeje demonstrably
  depends on.
- CP LIVE is an **integration consumer**. A CP LIVE SHA may be recorded as
  integration evidence, never as the runtime contract, a version, a prerequisite
  or a watermark.

The withdrawn model — a branch named "UPSTREAM, sole living product source" and a
`MUEJEJE_UPSTREAM_BASE_SHA` watermark requiring a fetch-and-resync ritual before
every unit — is not reinstated by this record and must not be reintroduced.

See [the operating model](../architecture/muejeje-runtime-operating-model.md) for
the governance this replaced it with, and
[the requirements baseline](../architecture/muejeje-pts-requirements.md) for the
binding requirements that came out of it.

## Consequences carried forward

- `MJ-013` — PTBuilder is not a build input; six globals remain a runtime
  dependency, and the attribution stays until each is replaced.
- `TODO-SRC-ROOT` — the owned artifact still declares the legacy `EXTENSION/**`
  tree as its source root. Assessed, not migrated.
- The audit's own acceptance list asked for zero `a384a79f` occurrences in
  tracked docs. That check is satisfied in substance but not literally: the two
  QA reports are now tracked verbatim, and they quote the old watermark while
  recording that it was withdrawn. No live document asserts it.
