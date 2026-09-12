# POE-3I Exact-Build Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the POE-3H false negative for one exact 3650 factory contract, ratchet the runtime hotspot, and advance through LIVE B to Router0 when admitted.

**Architecture:** Keep raw Packet Tracer collection capture in the runtime adapter, but move Python occupancy authority and verification into focused modules. Select an exact-build authority path only for the governed 3650 policy; preserve PhysicalView as diagnostics and retain legacy behavior outside that policy. The existing governed runner remains the only LIVE mutation path and keeps the structural and 0-to-390 W gates separate.

**Tech Stack:** Python 3.12, dataclasses, pytest, Packet Tracer script-engine JavaScript, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-12-poe-3i-exact-build-authority.md`

## Global Constraints

- Use the checkout-local `.venv` and never mix `packet_tracer_mcp` with `src.packet_tracer_mcp` in one live process.
- Never build JavaScript with raw f-strings; JSON-encode every interpolated field.
- Do not modify historical evidence or the capability store before a newly admitted LIVE result.
- Do not operate Router3.
- Run `graphify update .` after code changes.

---

### Task 1: Lock the exact authority in focal REDs

**Files:**
- Create: `tests/test_factory_module_occupancy_authority.py`
- Modify: `tests/test_factory_module_target_agreement.py`
- Reuse: `tests/support/factory_module_cases.py`
- Fixture: `docs/reference/cp-scale/canonical-live-evidence/poe3b-router0-b-3650-11-psu-host-inventory-20260912T045537Z-766e4a93/evidence.json`

**Interfaces:**
- Consumes: `PacketTracerFactoryModulePreparer`, the committed POE-3H before/install/after wire captures, and support-owned response builders.
- Produces: failing behavioral tests for diagnostic-only PhysicalView, fresh-only authority, exact identity, non-target drift, exact target, and corrupt target rejection.

- [ ] Add a fixture loader that reads the existing bundle and returns its raw before observation, normal derived installation response, and raw after observation without copying JSON.
- [ ] Assert the real false-PhysicalView post collection verifies the exact PSU and records diagnostic inconsistency.
- [ ] Assert the same initial observation is fail-closed when `fresh_owned=False`.
- [ ] Mutate only the post target descriptor identity and assert hard failure.
- [ ] Mutate one non-target collection entry and assert inventory incoherence.
- [ ] Remove post target identity observability and assert hard failure.
- [ ] Change the existing corrupt-target characterization to require fail-closed behavior.
- [ ] Run the focal tests and record expected semantic failures before production edits.

### Task 2: Implement exact-build occupancy and verification

**Files:**
- Create: `src/packet_tracer_mcp/infrastructure/execution/factory_module_occupancy.py`
- Create: `src/packet_tracer_mcp/infrastructure/execution/factory_module_verification.py`
- Modify: `src/packet_tracer_mcp/infrastructure/execution/factory_module_contracts.py`
- Modify: `src/packet_tracer_mcp/infrastructure/execution/factory_module_runtime.py`
- Modify: `src/packet_tracer_mcp/infrastructure/execution/factory_module_preparation.py`

**Interfaces:**
- Produces: `_parse_observation(raw, device_name, requirement, *, fresh_owned)` whose exact-policy path maps indexed collection entries only under the governed factory contract, plus `_inventory_effect(before, installation, after, requirement)` requiring the exact observed delta.
- Produces: `FactoryModuleVerification.diagnostic_inconsistent_with_runtime: bool`.
- Preserves: `_observe_module_slots_js`, `_install_factory_module_js`, and response parsing as runtime-adapter entry points.

- [ ] Add the minimum exact-policy discriminator; do not change authority for other model/build tuples.
- [ ] Derive initial compatible EMPTY only from fresh-owned exact-policy semantics and a null indexed entry; keep non-fresh unknown.
- [ ] Derive the post target identity from the measured indexed entry and ignore PhysicalView for state/guard decisions while retaining every captured view.
- [ ] Make the JavaScript pre-mutation guard use the same exact authority facts, so PhysicalView cannot veto the one attempt.
- [ ] Require a structurally valid reported target equal to the selected target for an attempted acknowledgement.
- [ ] Verify exact target identity, unchanged non-target entries, and unchanged slot/container structure; reject missing/different identity and competing drift.
- [ ] Require `identity_matches is True` in the factory power hypothesis.
- [ ] Run focal tests GREEN, then affected factory/runner tests GREEN.

### Task 3: Ratchet production maintainability

**Files:**
- Create: `tests/test_factory_module_runtime_architecture.py`
- Modify: `src/packet_tracer_mcp/infrastructure/execution/factory_module_runtime.py`

**Interfaces:**
- Consumes: focused occupancy and verification modules from Task 2.
- Produces: a file-specific post-fix LOC ceiling for `factory_module_runtime.py`.

- [ ] Move Python inventory parsing/authority and verification out of the runtime adapter without changing behavior beyond Task 2.
- [ ] Add a runtime-only LOC ratchet using the measured post-extraction size; do not add a global LOC budget.
- [ ] Run the architecture guard and all factory-module tests.

### Task 4: Offline gates and source integration

**Files:**
- Update generated graph under `graphify-out/` only through `graphify update .`.

- [ ] Run focused tests, affected PoE/CP-LIVE tests, and the full `.venv` pytest suite.
- [ ] Review `git diff --check`, changed paths, historical bundle hashes, baseline-v3 integrity, and capability-store diff.
- [ ] Run `graphify update .` and re-run maintenance guards.
- [ ] Commit, push only `feature/runtime-ripv2`, wait for exact-SHA CI, and require all four jobs GREEN with local HEAD equal to upstream.

### Task 5: Governed LIVE B and productive admission

**Files:**
- Execute: `tools/poe3a_pse_live.py`
- Create only on an executed run: a new canonical LIVE evidence bundle and admitted runtime snapshot/receipt.

- [ ] Prove the live-process interpreter, production module path, and single namespace.
- [ ] Run model `3650-24PS` with the governed 11-port plan.
- [ ] Require structural PSU PASS, `Available 0.0 -> 390.0 W`, `AUTO_1=11/11`, `NEVER=0/11`, `AUTO_2=11/11`, and complete RESTORE.
- [ ] If a reproducible software defect occurs after exact cleanup and decided mutation outcome, fix it through a new RED, repeat all code/CI gates, and rerun with a new cause/fix only.
- [ ] Commit/push newly admitted evidence and store data, require exact-SHA 4/4 CI, then evaluate real A+B composition.

### Task 6: Router0 continuation

**Files:**
- Reuse the existing Router0 offline projection and CP-LIVE runner; do not create Router3 work.

- [ ] With real A+B admission, project Router0 offline and validate E4/E5/E9/Voice hashes plus the shared 3650 preparer wiring.
- [ ] Re-establish clean/upstream/exact-SHA CI gates.
- [ ] Execute Router0 CP-LIVE only if every preceding gate passes; apply the same bounded autofix loop and stop conditions.
- [ ] Report every requested status field with exact SHAs, evidence paths, tests, CI, integrity, and blockers.
