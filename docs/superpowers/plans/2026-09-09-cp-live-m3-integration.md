# CP-LIVE M3 Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close CP-LIVE's offline migration by making invocation-root authority independent, preserving partial failures, isolating every test state surface, removing temporary private compatibility imports, and typing the stage Realtime boundary.

**Architecture:** The existing `PT_MCP_GOVERNED_ROOT` declaration becomes the sole root authority for adapter `run()`; there is no package-derived fallback. The coordinator and existing ports remain unchanged in authority, while persistence serializers become total over their optional typed fields. Test harness state is isolated and guarded independently of Git, and stage Realtime uses the existing finite state shape through a dedicated required-observation contract.

**Tech Stack:** Python 3.12, frozen dataclasses, pytest, subprocess isolation, Git, Graphify.

**Spec:** `docs/superpowers/specs/2026-09-08-cp-live-m0-modular-baseline.md`

## Global Constraints

- Offline only: no Packet Tracer, bridge, LIVE capability acquisition, probes, or `.pts` changes.
- Use `./.venv/Scripts/python.exe -m pytest` from this checkout with no custom `PYTHONPATH`.
- Preserve public `main`/`run` arguments, defaults, exit codes, JSON schemas, paths, hashes, order, identity and multiplicity.
- Keep `baseline-v3` and SHA-256 `639cd07674460c83c9a78d6c66459f0ce84648cc18a21579bcbc83826766baa7` byte-identical.
- No `src -> tools`, import cycles, dynamic global forwarding, universal Context, new PoE authority, merge, force-push, or product-branch push.
- Every functional fix starts with a causal RED and lands separately from migration-only movement.
- Preserve the ignored incident file at its M3-entry bytes and hash; absence in CI is also a protected state.

---

### Task 1: Make governed-root authority independent

**Files:**
- Modify: `src/packet_tracer_mcp/adapters/cli/cp_scale_live.py`
- Modify: `tools/cp_scale_canonical_live.py`
- Create: `tests/test_cp_scale_live_governed_root.py`
- Modify: `tests/test_cp_scale_live_cli.py`
- Modify: `tests/test_cp_scale_live_architecture.py`

**Interfaces:**
- Consumes: `governed_root_from_env()` and `PT_MCP_GOVERNED_ROOT` from import-isolation infrastructure.
- Produces: `build_coordinator(request, *, governed_root: Path)` with no default and unchanged public `run(...) -> int` / `main() -> int`.

- [ ] **Step 1: Write the root REDs**

  Add a missing-declaration test proving `run()` returns `2` without constructing persistence/backend, and a real-entry test that creates checkout A and checkout B at the same SHA, runs `A/tools/cp_scale_canonical_live.py --execute ...` using B's venv/package with `PT_MCP_GOVERNED_ROOT=A`, and asserts rejection plus no writes under B and no backend/capability evidence.

- [ ] **Step 2: Verify the REDs fail causally**

  Run `.venv/Scripts/python.exe -m pytest -q tests/test_cp_scale_live_governed_root.py`; expect the current package-derived root either to self-approve B or to write under B.

- [ ] **Step 3: Implement the minimal root correction**

  Remove module-level package-derived root/path constants. Resolve only the caller declaration at invocation time, reject an absent declaration before assembly, require an explicit root in `build_coordinator`, and pass that same `Path` to local preflight, capability adapters, checkpoint repository and `CPScaleLivePersistence`.

- [ ] **Step 4: Retain the entry contract**

  Keep the tool as a static import façade for `main` and `run`; keep CLI flags/defaults and the 0/1/2 mapping unchanged. Strengthen the architecture test so a package-file fallback is rejected rather than exempted.

- [ ] **Step 5: Run focused GREEN and commit**

  Run governed-root, CLI, import-isolation, worktree-isolation and architecture tests; commit as `fix(cp-live): make governed root caller-authoritative`.

### Task 2: Serialize partial acquired failure state

**Files:**
- Modify: `src/packet_tracer_mcp/infrastructure/persistence/cp_scale_run_evidence.py`
- Create: `tests/test_cp_scale_live_partial_persistence.py`

**Interfaces:**
- Consumes: optional `first`, `second`, `unresolved`, cleanup error and restoration fields already present in frozen contracts.
- Produces: the same public schemas with explicit `None` for an absent acquired peer and without fabricated summaries.

- [ ] **Step 1: Write the coordinator-through-writer RED**

  Use the real coordinator, `run_evidence`, `CPScaleLivePersistence` and cleanup/finalization with a controlled backend/session. Make the second capability workspace observation raise after the first is acquired; assert the original exception is primary, one close occurs, the first summary persists, the second is `None`, and no `VERIFIED`/invented read appears.

- [ ] **Step 2: Add table-driven partial serializer REDs**

  Cover first-only, second-only, unresolved-without-workspace and cleanup carrying both operation/restoration failures. Derive literal expected mappings independently of the serializer.

- [ ] **Step 3: Verify RED, then implement minimal total serialization**

  Branch on each optional field independently. Preserve the historical list form only when neither workspace nor unresolved state was acquired; otherwise emit a structured qualification mapping with nullable observations.

- [ ] **Step 4: Run focused GREEN and commit**

  Run partial persistence, coordinator, terminal obligations, public writer and fixed oracle; commit as `fix(cp-live): serialize acquired partial failures`.

### Task 3: Seal test-state isolation and classify the incident

**Files:**
- Create: `tests/cp_live_data_integrity.py`
- Modify: `tests/conftest.py`
- Modify: `tests/subprocess_harness.py`
- Modify: CP-LIVE subprocess harness tests that still call `subprocess.run` directly
- Modify: `docs/superpowers/specs/2026-09-08-cp-live-m0-modular-baseline.md`

**Interfaces:**
- Consumes: workspace protected paths and the host token location before test environment redirection.
- Produces: immutable before/after snapshots of existence, relative path, byte length and SHA-256; isolated subprocess environment for `LOCALAPPDATA`, `TEMP`, `TMP`, token and optional governed root.

- [ ] **Step 1: Capture and record incident provenance**

  Record, without rewriting, the observed ignored file: 1,218 bytes, SHA-256 `bf2ac3bfda1326ee274a5714df0d16bebd53afb9e31e4f90d49ba28eaef9c60d`, timestamp and its synthetic Router0+retention preflight-rejection classification. State explicitly that prior bytes are unknown and restoration is not claimed.

- [ ] **Step 2: Write sentinel/isolation REDs**

  Against temporary paths, prove the snapshot detects creation, deletion and byte changes including ignored files. Add a harness test whose child would inherit host state without the new environment helper.

- [ ] **Step 3: Implement suite and subprocess isolation**

  Snapshot `data/cp-scale`, `data/capabilities`, canonical evidence/checkpoint paths and the original token file once per session. Redirect machine-local dirs/token for the entire suite and every CP-LIVE child; preserve explicit root declarations. Compare protected snapshots at teardown even when Git is clean.

- [ ] **Step 4: Verify the real incident file remains byte-identical**

  Recompute its hash after focused and affected tests. Do not delete, replace or claim restoration.

- [ ] **Step 5: Commit isolation separately**

  Commit as `test(cp-live): enforce data isolation beyond git status`.

### Task 4: Finish private-helper migration and type stage Realtime

**Files:**
- Modify: `src/packet_tracer_mcp/application/cp_scale_live/contracts.py`
- Modify: `src/packet_tracer_mcp/application/cp_scale_live/observation.py`
- Modify: `src/packet_tracer_mcp/application/cp_scale_live/voice_stage.py`
- Modify: `src/packet_tracer_mcp/application/cp_scale_live/stage_executor.py`
- Modify: `src/packet_tracer_mcp/application/cp_scale_live/run_contracts.py`
- Modify: `src/packet_tracer_mcp/infrastructure/observation/cp_scale_live.py`
- Modify: `src/packet_tracer_mcp/infrastructure/observation/cp_scale_live_run.py`
- Modify: `src/packet_tracer_mcp/infrastructure/persistence/cp_scale_stage_evidence.py`
- Modify: `src/packet_tracer_mcp/adapters/cli/cp_scale_live.py`
- Modify: `tools/cp_scale_canonical_live.py`
- Modify: affected tests/harness imports

**Interfaces:**
- Consumes: existing finite `CPScaleRealtimeState` semantics and `SimulationStateObservation` from the PT adapter.
- Produces: `CPScaleRealtimeObservation` plus typed `CPScaleRealtimeWindow`; compatibility mapping is created only in persistence.

- [ ] **Step 1: Write Realtime typing REDs**

  Assert the observation port returns a finite typed state; stage before/after retain absence, error/provenance and required-observation authority; `realtime_boundary_error` accepts no raw mapping; serialized evidence remains byte/value compatible.

- [ ] **Step 2: Verify RED, then move the finite type to the shared contract owner**

  Add a dedicated Realtime observation record, use it in the stage window and required-observation union, convert the infrastructure runtime result field-by-field, and serialize its `present` fields at the persistence boundary. Do not type unrelated historical evidence mappings.

- [ ] **Step 3: Migrate private consumers to owners**

  Import observation helpers from infrastructure observation, diagnostics helpers from infrastructure diagnostics, Voice policy from application, and evidence renderers from persistence. Replace monkeypatched adapter globals with explicit owner/factory injection. Remove temporary adapter/tool reexports and obsolete adapter result/writer wrappers.

- [ ] **Step 4: Preserve the oracle and commit migration**

  Run Voice, Realtime, diagnostics, frame observer, real stage executor, Router0/default/retention and baseline-v3 tests. Commit as `refactor(cp-live): close temporary compatibility surface`.

### Task 5: Integration closure, documentation and publication

**Files:**
- Modify: `docs/superpowers/specs/2026-09-08-cp-live-m0-modular-baseline.md`
- Modify: architecture/integration tests only if a causal gap is found

**Interfaces:**
- Consumes: final M3 commits and `cisco/feature/runtime-ripv2`.
- Produces: one concise requirement → implementation → test → evidence matrix and final offline status.

- [ ] **Step 1: Verify compatibility reference**

  Fetch without merging, record M3 base/head and current feature SHA. Verify merge-base/divergence and inspect relevant overlapping paths; do not require equality or import unreviewed advances.

- [ ] **Step 2: Run gates in order**

  Focused per correction, affected matrix, then `.venv/Scripts/python.exe -m pytest -q`; run `git diff --check`, protected-data snapshot comparison, baseline hash and Graphify update.

- [ ] **Step 3: Update the existing spec concisely**

  Mark M3 technically complete offline while retaining `PRODUCT_ADMISSION=BLOCKED` and `ROUTER0_LIVE=NOT_RUN`. Add only the requested short matrix and incident/compatibility evidence.

- [ ] **Step 4: Request independent code review**

  Review from `fae7a7f9ae7db80c1fad921ddc81ed57d695d853` to candidate HEAD. Fix every Critical/Important finding with causal tests and rerun affected/full.

- [ ] **Step 5: Commit, push and verify CI**

  Push only `refactor/cp-live-m0-baseline` to `cisco` without force. Verify all four Windows/Ubuntu × Python 3.11/3.13 jobs belong to the final SHA and finish successfully. Do not merge or run LIVE.
