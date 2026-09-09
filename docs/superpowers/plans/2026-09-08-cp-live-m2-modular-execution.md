# CP-LIVE M2 Modular Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the authorized offline M2-A stage-execution extraction and M2-B coordinator/session/CLI extraction while preserving the fixed `baseline-v3` behavior.

**Architecture:** M2-A moves the typed stage path into `application/cp_scale_live`, with one collaborator per Configuration, Voice, Control Plane, forwarding, and reconciliation responsibility and concrete observation/diagnostic adapters in infrastructure. M2-B places lifecycle and orchestration in application behind narrow ports, gives one infrastructure session object sole ownership of acquired transport/runtimes, places persistence and console composition in infrastructure/adapters, and leaves `tools/cp_scale_canonical_live.py` as a static compatibility façade.

**Tech Stack:** Python 3.11+, frozen dataclasses and Pydantic domain models, pytest, subprocess CLI probes, local Git, Graphify.

**Spec:** `docs/superpowers/specs/2026-09-08-cp-live-m0-modular-baseline.md`

## Global Constraints

- Entire delivery is offline: no Packet Tracer, bridge, LIVE capability acquisition, `.pts`, or productive admission change.
- Use the checkout-local `.venv/Scripts/python.exe`, no custom `PYTHONPATH`; tests import `src.packet_tracer_mcp`, production imports `packet_tracer_mcp`.
- Preserve the fixed `baseline-v3`; never regenerate it to hide candidate differences.
- Preserve exact order and multiplicity: physical delta → Configuration → Voice → Control Plane → forwarding → cumulative reconciliation.
- Preserve PARTIAL/UNOBSERVABLE ceilings, E4/E5/E9/Voice hashes, prerequisites, mutation-free rereads, legitimate Voice phases, and journal-based `NO_MUTATION_REPLAY`.
- Required observations and diagnostics are separate; diagnostics have `DIAGNOSTIC_ONLY` authority and cannot replace the first cause.
- One session keeps the same transport and runtime instances and has one close owner across partial acquisition, cancellation, persistence/report errors, cleanup and retention.
- No `src` import from `tools`, dynamic legacy-runner loading, global forwarding, generic workflow framework, event bus, universal Context, or duplicated physical deployment.
- Shared mechanisms know neither Router0 nor PoE authority; a test-only synthetic scenario demonstrates reuse without modifying the mechanism.
- Public schemas, paths, hashes, journals, dispatch identity/order/multiplicity and CLI flags/defaults/codes remain compatible.
- Functional corrections, M2-A, and M2-B are separate reviewed commits; no force-push, merge, or changes to `feature/runtime-ripv2`.

---

### Task 1: Correct the three bounded M1 defects

**Files:**
- Create: `src/packet_tracer_mcp/application/cp_scale_live/process_identity.py`
- Modify: `src/packet_tracer_mcp/application/cp_scale_live/contracts.py`
- Modify: `src/packet_tracer_mcp/infrastructure/execution/live_environment_preflight.py`
- Modify: `src/packet_tracer_mcp/infrastructure/execution/cp_scale_live_preflight.py`
- Test: `tests/test_cp_scale_live_local_preflight.py`
- Test: `tests/test_live_environment_preflight.py`

**Interfaces:**
- Produces: one pure application policy for ProductVersion/FileVersion fallback, expected-version matching and executable-path uniqueness.
- Produces: strict process-row parsing that accepts strings (and absent optional version fields) but never promotes arbitrary objects through `str(...)`.
- Produces: a repository snapshot whose tree is resolved as `<captured-head>^{tree}` and whose terminal rereads reject concurrent HEAD/upstream movement.

- [ ] **Step 1: Write strict-reader REDs**

  Add a table-driven test whose literal payload changes `ProcessName`, either version field, or `Path` to a non-string and asserts a failed observation with zero accepted records. Name the break: restoring `str(value)` makes every case fail.

- [ ] **Step 2: Run strict-reader REDs**

  Run `./.venv/Scripts/python.exe -m pytest tests/test_cp_scale_live_local_preflight.py -k "invalid_process or captured_head or moving_reference" -q`; expect failures caused by coercion and mutable `HEAD^{tree}`.

- [ ] **Step 3: Write repository-snapshot REDs**

  Add ordered fake-Git tests that require `rev-parse <HEAD>^{tree}`, then return a different final HEAD or upstream SHA and assert explicit fail-closed evidence and preflight rejection before process enumeration.

- [ ] **Step 4: Implement the minimum fixes**

  Parse required/optional strings explicitly, centralize the version/path decision in the application policy, delegate the infrastructure compatibility function and contract coherence to it, resolve the tree from captured SHA, and compare final reference reads with captured values.

- [ ] **Step 5: Run focal and affected gates**

  Run both preflight test modules, characterization, namespace isolation, Router0 runner, and `baseline-v3` equivalence with the local interpreter.

- [ ] **Step 6: Review and commit**

  Inspect the exact diff and commit only Task 1 as `fix(cp-live): harden local preflight snapshots`.

### Task 2: M2-A — extract typed stage execution and collaborators

**Files:**
- Modify: `src/packet_tracer_mcp/application/cp_scale_live/contracts.py`
- Create: `src/packet_tracer_mcp/application/cp_scale_live/stage_executor.py`
- Create: `src/packet_tracer_mcp/application/cp_scale_live/configuration_stage.py`
- Create: `src/packet_tracer_mcp/application/cp_scale_live/voice_stage.py`
- Create: `src/packet_tracer_mcp/application/cp_scale_live/control_plane_stage.py`
- Create: `src/packet_tracer_mcp/application/cp_scale_live/forwarding_stage.py`
- Create: `src/packet_tracer_mcp/application/cp_scale_live/reconciliation.py`
- Create: `src/packet_tracer_mcp/infrastructure/observation/cp_scale_live.py`
- Create: `src/packet_tracer_mcp/infrastructure/diagnostics/cp_scale_live.py`
- Modify: `tools/cp_scale_canonical_live.py`
- Test: `tests/test_cp_scale_stage_executor.py`
- Test: affected stage/voice/forwarding/diagnostic suites and `tests/cp_live_m0_harness.py`

**Interfaces:**
- Produces: frozen `CPScaleStageContinuity`, `CPScaleStageExecutionInput`, and `CPScaleLiveStageResult` values carrying typed domain results rather than JSON round-trips.
- Produces: `CPScaleStageExecutor.execute(input) -> CPScaleLiveStageResult` and focused injected collaborators for the five named responsibilities.
- Consumes: existing canonical projectors, deployer/reconciler, Configuration/Voice/Control Plane applicators, validators and runtime protocols.

- [ ] **Step 1: Write the real-executor RED**

  Exercise the new executor with controlled real applicators/runtimes and literal expected ordered trace `physical_delta, configuration, voice, control_plane, forwarding, reconciliation`; assert partial evidence remains present on failure.

- [ ] **Step 2: Write authority/continuity REDs**

  Assert PARTIAL is not promoted, UNOBSERVABLE blocks dependants, hashes and prerequisites survive, reread has zero mutation, legitimate Voice phases survive, and replay authority comes from action results/journals rather than static ID sets.

- [ ] **Step 3: Extract the five application collaborators**

  Move decisions—not concrete PT mechanics—behind focused typed collaborators, reusing every existing applicator/projector/validator and invoking physical deployment only in the outer coordinator path.

- [ ] **Step 4: Extract concrete observation and diagnostic adapters**

  Move IOS/ping/workspace/Realtime observation to infrastructure observation and Simulation/frame work to infrastructure diagnostics. Keep the diagnostic request/result separate and unable to set stage acceptance or first cause.

- [ ] **Step 5: Adapt legacy consumers without global forwarding**

  Point tests/harness at the new real executor and explicit dependency factories. Keep only static symbol aliases required by the temporary public/private compatibility surface; do not proxy mutable module globals.

- [ ] **Step 6: Gate A**

  Run the new real-executor tests, all existing stage/Voice/forwarding/diagnostic tests, architectural boundaries, Router0/default runner scenarios, and fixed equivalence oracle. Review order and multiplicity, then commit as `refactor(cp-live): extract stage execution`.

### Task 3: M2-B — extract coordinator, lifecycle, persistence and CLI

**Files:**
- Create: `src/packet_tracer_mcp/application/cp_scale_live/coordinator.py`
- Create: `src/packet_tracer_mcp/application/cp_scale_live/lifecycle.py`
- Create: `src/packet_tracer_mcp/infrastructure/execution/cp_scale_live_session.py`
- Create: `src/packet_tracer_mcp/infrastructure/persistence/cp_scale_live.py`
- Create: `src/packet_tracer_mcp/adapters/cli/cp_scale_live.py`
- Modify: `tools/cp_scale_canonical_live.py`
- Modify: `tests/cp_live_m0_harness.py`
- Test: `tests/test_cp_scale_live_coordinator.py`
- Test: `tests/test_cp_scale_live_cli.py`
- Test: finalization, Router0/default/full/retention/failure/cancellation suites.

**Interfaces:**
- Produces: a real application coordinator parameterized by preflight, stage executor, checkpoint, persistence and session-factory ports.
- Produces: one session owner that returns the same acquired runtime instances and attempts close once even after partial acquisition or cancellation.
- Produces: persistence methods rooted from adapter composition, retaining existing schemas/paths/hashes and atomic writes.
- Produces: adapter `main/run` with the existing signatures, flags, defaults, output and exit codes; the tool file statically imports/re-exports them.

- [ ] **Step 1: Write coordinator and lifecycle REDs**

  Use the real coordinator with a controlled executor to assert stage order, continuity identity, exact cleanup ownership, retention, first/secondary failure precedence, partial acquisition, cancellation and the rule that attempted stop never attests cleanup.

- [ ] **Step 2: Write persistence and CLI subprocess REDs**

  Compose the offline adapter under a temporary governed root, run the tool in subprocess without `--execute` and through injected offline seams, and assert schemas, paths, hashes, outputs, defaults and codes.

- [ ] **Step 3: Extract lifecycle and persistence**

  Give the session sole close ownership and move existing atomic write/archive mechanisms behind explicit ports. Pass governed root from adapter composition; do not derive it from the moved module's `__file__`.

- [ ] **Step 4: Extract the coordinator**

  Move the stage loop, checkpoints, cleanup/restoration and terminal-obligation sequencing into application while retaining typed state and first-cause precedence. Do not duplicate stage or physical deployment logic.

- [ ] **Step 5: Move composition/presentation and reduce the tool to a façade**

  Build concrete PT/session/observation/diagnostic/persistence dependencies in `adapters/cli/cp_scale_live.py`; keep compatible `main/run` and static imports in `tools/cp_scale_canonical_live.py` with no reverse dependency or dynamic load.

- [ ] **Step 6: Gate B and commit**

  Run coordinator/session/CLI tests, Router0/default/full/retention/failure/cancellation/finalization tests, architectural tests and fixed oracle. Review exact ownership/order/multiplicity, then commit as `refactor(cp-live): extract coordinator and CLI`.

### Task 4: Prove boundaries, reuse, bounded state and final equivalence

**Files:**
- Create or modify: `tests/test_cp_scale_live_architecture.py`
- Create: `tests/test_cp_scale_live_reuse_and_state.py`
- Modify: `docs/superpowers/specs/2026-09-08-cp-live-m0-modular-baseline.md`

**Interfaces:**
- Consumes: the shared stage/lifecycle mechanism without CP-SCALE names or PoE authority.
- Produces: measured counts and serialized byte sizes for increasing synthetic stage counts, preserving full journals without nested history copies.

- [ ] **Step 1: Add architecture REDs**

  Parse imports to reject `src -> tools`, cycles among coordinator/executor/observation/diagnostics/persistence, concrete PT dependencies in application, and a façade that contains coordination implementation.

- [ ] **Step 2: Add the synthetic reuse/state RED**

  Run a small non-canonical three-stage scenario with different names/policy/adapters through the unchanged shared mechanism; assert ordered outcomes and object identity. Measure 1, 2 and 4-stage snapshots and public JSON serialization, asserting linear entry growth, no nested completed history, and all journals retained.

- [ ] **Step 3: Run focused → affected → full → diff review**

  Run each new module, the complete affected matrix, `./.venv/Scripts/python.exe -m pytest -q`, `git diff --check`, import-cycle checks and fixed `baseline-v3` comparison.

- [ ] **Step 4: Update Graphify and documentation**

  Run `graphify update .`, inspect graph/diff, record M2-A/M2-B complete while leaving `PRODUCT_ADMISSION=BLOCKED` and `ROUTER0_LIVE=NOT_RUN`, and commit tests/docs separately from functional moves when appropriate.

- [ ] **Step 5: Final review, push and CI**

  Request whole-branch code review, fix all Critical/Important findings with causal tests, rerun the full suite, push only `refactor/cp-live-m0-baseline` to `cisco` without force, and verify all four CI jobs belong to the final SHA.
