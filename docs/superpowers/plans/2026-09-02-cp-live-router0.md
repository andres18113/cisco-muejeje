# Canonical CP-LIVE Router0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify the canonical CP-SCALE pipeline through `router0-branch`, archive authoritative evidence, restore the Packet Tracer workspace to Realtime and its exact baseline, and stop before `router3-branch`.

**Architecture:** Keep the existing cumulative compiler and persistent LIVE runner as the only mutation path. Correct the repository-authority seam once in the product use case and reuse it from the runner; publish a compact JSON current-state record plus an index while retaining the marked `handoff.md` block as a compatibility projection. A deliberate non-advance command at the verified Router0 checkpoint enters the runner's governed abort cleanup, so no Router3 projection is deployed.

**Tech Stack:** Python 3.12, Pydantic, pytest, Packet Tracer 9.0.1.0858, Git, Graphify.

**Spec:** `docs/reference/cp-scale/diseno_logico_IMP.md` and the session's canonical Router0 acceptance contract.

## Global Constraints

- Use only the checkout-local `.venv` interpreter and production namespace for LIVE.
- LIVE source must be clean, committed, pushed to `cisco/feature/runtime-ripv2`, and import-isolated.
- Derive all counts from `compose_cp_scale_canonical()` and stage projections.
- Preserve the verified Voice and PVST mechanisms absent contradictory evidence.
- Stop before `router3-branch`; no raw IOS/JavaScript, guessed capability, arbitrary sleep, or weakened verification.
- Archive pre-cleanup evidence and cleanup attestation; require two exact baseline observations and verified Realtime restoration.

---

### Task 1: Move canonical repository authority to `cisco`

**Files:**
- Modify: `tests/test_cp_scale_canonical_runtime_gates.py`
- Modify: `tests/test_cp_scale_live_qualification.py`
- Modify: `src/packet_tracer_mcp/application/use_cases/qualify_cp_scale_live.py`
- Modify: `tools/cp_scale_canonical_live.py`

**Interfaces:**
- Consumes: `read_git_repository_state(root: Path) -> CPScaleRepositoryState`.
- Produces: one `EXPECTED_UPSTREAM = "cisco/feature/runtime-ripv2"` authority reused by the canonical runner.

- [x] **Step 1: Write the failing authority tests**

  Change the controlled repository fixtures to `cisco/feature/runtime-ripv2`; assert that `canonical_checkpoint_repository_error()` accepts that upstream and rejects the former `personal/feature/runtime-ripv2` value.

- [x] **Step 2: Run the focused tests and verify RED**

  Run: `.\.venv\Scripts\python.exe -m pytest tests\test_cp_scale_canonical_runtime_gates.py::test_checkpoint_resume_requires_clean_pushed_unchanged_governed_source tests\test_cp_scale_live_qualification.py::test_repository_reader_observes_current_exact_branch_upstream_and_head -q`

  Expected: failure showing the product still requires or observes `personal/feature/runtime-ripv2`.

- [x] **Step 3: Implement the smallest authority correction**

  Set the product constant to `cisco/feature/runtime-ripv2`; import `EXPECTED_BRANCH` and `EXPECTED_UPSTREAM` into `tools/cp_scale_canonical_live.py` and delete its duplicate definitions.

- [x] **Step 4: Verify GREEN and affected repository gates**

  Run the two focused files with a fresh checkout-local `--basetemp` and no pytest cache provider.

### Task 2: Establish compact current-state authority without breaking handoff consumers

**Files:**
- Create: `docs/reference/cp-scale/current_state.json`
- Create: `docs/reference/cp-scale/README.md`
- Create: `tests/test_cp_scale_current_state.py`
- Modify: `handoff.md`

**Interfaces:**
- Consumes: the existing `<!-- CP_SCALE_STATE_BEGIN -->` compatibility block parsed by `tests/handoff_state.py`.
- Produces: `cp-scale-current-state-v1`, whose compatibility keys must match the legacy marked block exactly.

- [x] **Step 1: Write a failing state-contract test**

  Require a compact JSON object with schema, update timestamp, source head, active stage, status, first contradicted boundary, next active step, stage summaries, evidence links, and a small `handoff_compatibility` mapping. Verify every compatibility entry equals `parse_handoff_state(handoff.md)`.

- [x] **Step 2: Run the new test and verify RED**

  Run: `.\.venv\Scripts\python.exe -m pytest tests\test_cp_scale_current_state.py -q`

  Expected: failure because `current_state.json` does not exist.

- [x] **Step 3: Add the compact state and evidence index**

  Record the established Floor3/PVST boundary without copying historical narratives. Add a short pointer at the top of `handoff.md`; leave its markers and existing keys intact.

- [x] **Step 4: Verify GREEN and legacy compatibility**

  Run the new state test plus `tests/test_positive_voice_handoff.py` and `tests/test_cp_scale_canonical_voice_evidence_ledger.py`.

### Task 3: Establish a clean pushed LIVE source and exact Router0 scope

**Files:**
- Modify only the Task 1/2 paths and this plan.

**Interfaces:**
- Consumes: compiler projections for `floor3` and `router0-branch`.
- Produces: a committed source HEAD equal to `cisco/feature/runtime-ripv2` and a recorded derived scope.

- [x] **Step 1: Run focused and affected offline tests**

  Cover stage projection/deltas, configuration, control-plane, Voice verification, repository gates, state compatibility, and import isolation.

- [x] **Step 2: Run `graphify update .` and inspect the diff**

  Confirm no generated graph change masks an unrelated source edit.

- [ ] **Step 3: Commit and push only the coherent pre-LIVE change set**

  Push to `cisco/feature/runtime-ripv2`, set that branch as upstream, and prove local HEAD, upstream HEAD, and `cisco/feature/runtime-ripv2` are identical.

- [ ] **Step 4: Derive and retain the Router0 projection report**

  Use production imports only and report cumulative/delta devices, links, configuration actions, control actions and expectations, Voice actions and expectations, and the sole loaded namespace.

### Task 4: Execute canonical LIVE through Router0 only

**Files:**
- Runtime progress: `data/cp-scale/live-canonical-progress.json` (ignored).
- Runtime checkpoint: `data/cp-scale/live-canonical-checkpoint.json` (ignored).
- Archive: `docs/reference/cp-scale/canonical-live-evidence/`.

**Interfaces:**
- Consumes: `tools/cp_scale_canonical_live.py --execute --packet-tracer-version 9.0.1.0858 --expected-head <HEAD>`.
- Produces: a verified `router0-branch` stage followed by governed cleanup; no Router3 mutation.

- [ ] **Step 1: Prove all pre-mutation gates in the LIVE process**

  Verify checkout-local executable, local production package path, one namespace, exact pushed HEAD, Packet Tracer version/process, authenticated bridge, Realtime, and exact disposable inventory.

- [ ] **Step 2: Advance only verified checkpoints**

  Send `continue` after `routing-core`, `router4-switch10`, `floor1`, `floor2`, and `floor3`. At each boundary inspect the durable checkpoint before advancing.

- [ ] **Step 3: Classify any first contradiction before changing code**

  Retain the failing stage evidence, name the first contradicted boundary, diagnose from authoritative readback, add a failing regression test, implement the smallest principled fix, re-run offline gates, commit/push, clean up, and start a fresh informative LIVE.

- [ ] **Step 4: Stop at the verified Router0 checkpoint**

  Inspect that `router0-branch` is VERIFIED across physical, configuration ceilings, Voice, control plane, core forwarding and twice-read workspace. Send `stop` only then; this is an operator lifecycle abort, not a negative network result, and invokes the runner's governed cleanup before `router3-branch` can begin.

- [ ] **Step 5: Verify post-run evidence and restoration**

  Require the archive digest to match bytes, cleanup to restore the exact baseline twice, Realtime to be independently verified, and the archived stage list to contain Router0 but not Router3.

### Task 5: Publish Router0 state, review, and finalize

**Files:**
- Modify: `docs/reference/cp-scale/current_state.json`
- Modify: `handoff.md` compatibility keys only
- Modify if unresolved debt is confirmed: `docs/architecture/technical-debt.md`
- Add: generated Router0 evidence archives

**Interfaces:**
- Consumes: the retained LIVE archive and cleanup attestation.
- Produces: compact authoritative Router0 status, legacy compatibility, hashes, and a clean pushed branch.

- [ ] **Step 1: Update state from evidence, not memory**

  Set Router0 status/counts/boundaries/hashes and `NEXT_ACTIVE_STEP = REVIEW_ROUTER0_BEFORE_ROUTER3`; add no historical narrative to `handoff.md`.

- [ ] **Step 2: Record debt only if it remains unresolved**

  Include evidence and a concrete `RESOLVE_BEFORE`; otherwise record no new debt.

- [ ] **Step 3: Run focused, affected, and full verification**

  Use fresh workspace-local basetemp directories, run Graphify update, inspect diff/stat, and confirm no unexpected files.

- [ ] **Step 4: Obtain a fresh coherent-diff review**

  Validate every substantive finding against repository evidence, fix accepted findings, rerun gates, and re-review if a material fix changes the reviewed diff.

- [ ] **Step 5: Commit, push, and prove final identity**

  Require clean status and `HEAD == @{upstream} == cisco/feature/runtime-ripv2`; stop before Router3 and return the requested final report.
