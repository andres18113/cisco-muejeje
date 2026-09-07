# PoE claim authority and canonical execution admission

**Goal:** Restore canonical CP-LIVE execution while preserving exact PoE claim authority.
**Spec:** Operator instruction RESTORE_EXECUTABLE_CP_LIVE_AND_FINISH, 2026-09-06.
**Architecture:** The exact-reference planner records unresolved PoE demand separately from physical selection. A typed executable-with-unverified-PoE hardware state reaches E5 with exact uncertainty records. E5 still validates inventory, attachment identities and all runtime stage boundaries. Providers and the PoE claim decoder retain their existing authority.
**Tech stack:** Python, Pydantic, checkout-local pytest, productive Packet Tracer runtime.

## Constraints

- UNKNOWN is not a supported claim; exact Fa0/1 -> 7960/Switch and its single-port simultaneous scope stay unchanged.
- No boolean bypass, synthetic production evidence, inferred mappings, Voice/PVST/Floor changes, or .pts modernization.
- No tests during live boundaries. Require exact source/import identity, port 54321 attribution, authenticated polling, Realtime, semantic baseline and file/runtime safety.

## Implementation and verification

- [x] Add causal tests in tests/test_cp_scale_poe_execution_admission.py for all seven operator requirements; run RED before source edits.
- [x] Add passive uncertainty data and an execution status in models/hardware.py; separate physical compatibility from unresolved claim demand in reference_hardware_planner.py.
- [x] Teach enterprise_compiler.py to carry the exact unknown demand into compiled metadata/warnings without granting a delivery claim; keep unaccounted bindings and physical errors fail-closed.
- [x] Update directly affected prior hard-gate assertions. Run focused and affected tests, then the complete checkout-local suite.
- [x] Verify production import isolation, graphify update, git diff --check, and fresh adversarial review for claim leaks and planner/compiler divergence.
- [ ] Commit a focused change, push only cisco/feature/runtime-ripv2, and require exact-SHA Actions 4/4.
- [ ] Run the already-authorized productive canonical CP-LIVE; preserve mutation delta and cumulative verification through Router0, Router3, Voice 69/69, routing/control plane, IoT, and verified cleanup.

## Verified change evidence

- Causal admission tests and review regressions failed before their corresponding corrections.
- Focused and affected validation: 225 passed. Complete checkout-local validation: 3860 passed, with three existing pytest deprecation warnings.
- Production import gate: checkout-local interpreter and one production namespace; diff whitespace check and graphify AST update passed.
- Fresh independent adversarial review accepted exact-demand reconciliation, unchanged claim authority, both link paths, and the stage evidence journal.
- Runtime execution and final CP-LIVE acceptance remain to be measured on the committed, green SHA.
