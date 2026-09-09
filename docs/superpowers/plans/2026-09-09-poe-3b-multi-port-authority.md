# POE-3B Multi-Port Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an offline-complete, fail-closed foundation for future multi-port PSE qualifications without acquiring LIVE evidence.

**Architecture:** Preserve the guarded `.pts` safety model and schema 2 as immutable historical contracts. Add sibling ephemeral safety and PSE schema 3 types, derive model plans from canonical E4/CP-SCALE data, and generalize the single POE-3A runner to consume those plans.

**Tech Stack:** Python 3.12, Pydantic v2, frozen dataclasses, pytest, CapabilitySnapshotStore, GitHub Actions, Graphify.

**Spec:** `docs/superpowers/specs/2026-09-09-poe-3b-multi-port-authority.md`

## Global Constraints

- Offline implementation only: no Packet Tracer, bridge, mailbox, `.pts`, capability acquisition or Router0 execution.
- Use `./.venv/Scripts/python.exe -m pytest` from this checkout with no custom `PYTHONPATH`.
- Production code imports only `packet_tracer_mcp`; tests import `src.packet_tracer_mcp`.
- Keep schema 2 decoding, historical bundles, prior snapshots, manual-vs-PSE separation and the existing claim ceiling unchanged.
- Do not change CP-SCALE topology or AP power semantics and do not add caller-supplied bindings, IOS or JavaScript.
- Every production change begins with a causal failing test.
- Commit and push only `feature/runtime-ripv2`, without force, then require exact-SHA CI 4/4.

---

### Task 1: Add the typed ephemeral safety mode

**Files:**
- Modify: `src/packet_tracer_mcp/domain/enterprise/models/discovery.py`
- Modify: `src/packet_tracer_mcp/domain/enterprise/rules/live_session_safety.py`
- Modify: `src/packet_tracer_mcp/application/live_session_safety.py`
- Modify: `src/packet_tracer_mcp/domain/enterprise/models/poe_delivery.py`
- Modify: `src/packet_tracer_mcp/application/use_cases/poe_delivery_qualification.py`
- Create: `tests/test_poe3b_live_session_safety.py`
- Test: `tests/test_poe_session_safety_fixture.py`

**Interfaces:**
- Consumes: existing `LiveSessionSafetyEvidence` and `validate_live_session_positive_admission()`.
- Produces: `LiveSessionSafetyMode`, `EphemeralUntitledWorkspaceSafetyEvidence`, and `LiveSessionSafetyAdmissionEvidence`.

- [ ] **Step 1: Write safety REDs**

Add tests that assert guarded evidence still serializes without a mode field and
still validates, while complete ephemeral evidence validates and every required
field fails closed when missing or contradictory. Use a table of literal field
mutations covering workspace counts, saved filenames, file-operation ledgers,
inventory, fixture, Realtime, PID, bridge/mailbox, Git identity/cleanliness,
runtime/crash and failure reasons.

- [ ] **Step 2: Verify the safety REDs fail causally**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest -q tests/test_poe3b_live_session_safety.py tests/test_poe_session_safety_fixture.py
```

Expected: import/validation failures because the new mode and model do not exist;
all historical guarded tests remain green when run separately.

- [ ] **Step 3: Implement the sibling evidence model and validator dispatch**

Keep `LiveSessionSafetyEvidence` fields unchanged and expose:

```python
class LiveSessionSafetyMode(str, Enum):
    GUARDED_PTS_COPY = "guarded_pts_copy"
    EPHEMERAL_UNTITLED_WORKSPACE = "ephemeral_untitled_workspace"

class EphemeralUntitledWorkspaceSafetyEvidence(BaseModel):
    mode: LiveSessionSafetyMode = LiveSessionSafetyMode.EPHEMERAL_UNTITLED_WORKSPACE
    initial_device_count: int | None = None
    final_device_count: int | None = None
    initial_link_count: int | None = None
    final_link_count: int | None = None
    initial_saved_filename: str | None = None
    final_saved_filename: str | None = None
    authorized_file_operations: tuple[str, ...] | None = None
    executed_file_operations: tuple[str, ...] | None = None
    initial_inventory_fingerprint: str = ""
    final_inventory_fingerprint: str = ""
    fixture_removed: bool | None = None
    initial_realtime: bool | None = None
    final_realtime: bool | None = None
    packet_tracer_pids_before: tuple[int, ...] | None = None
    packet_tracer_pids_after: tuple[int, ...] | None = None
    bridge_healthy_before: bool | None = None
    bridge_healthy_after: bool | None = None
    mailbox_entries_before: tuple[str, ...] | None = None
    mailbox_entries_after: tuple[str, ...] | None = None
    source_branch_before: str = ""
    source_branch_after: str = ""
    source_head_before: str = ""
    source_head_after: str = ""
    source_tree_before: str = ""
    source_tree_after: str = ""
    worktree_clean_before: bool | None = None
    worktree_clean_after: bool | None = None
    runtime_healthy: bool | None = None
    crash_detected: bool | None = None
    integrity_verified: bool = False
    session_reusable: bool = False
    positive_claim_allowed: bool = False
    failure_reasons: list[str] = Field(default_factory=list)
```

Add a non-serialized `mode` property to guarded evidence. Put all new coherence
checks in the rule module and update consuming type annotations to the union.

- [ ] **Step 4: Run GREEN and guarded regressions**

Run the Step 2 command plus `tests/test_poe_delivery_qualification.py` and
`tests/test_poe_delivery_provider.py`.

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- src/packet_tracer_mcp/domain/enterprise/models/discovery.py src/packet_tracer_mcp/domain/enterprise/rules/live_session_safety.py src/packet_tracer_mcp/application/live_session_safety.py src/packet_tracer_mcp/domain/enterprise/models/poe_delivery.py src/packet_tracer_mcp/application/use_cases/poe_delivery_qualification.py tests/test_poe3b_live_session_safety.py
git commit -m "feat(poe): add ephemeral untitled session safety"
```

### Task 2: Add PSE schema 3 without widening schema 2

**Files:**
- Create: `src/packet_tracer_mcp/domain/enterprise/services/poe_pse_multiport_claims.py`
- Modify: `src/packet_tracer_mcp/domain/enterprise/services/poe_claims.py`
- Create: `tests/test_poe3b_multi_port_pse.py`
- Test: `tests/test_poe3a_pse_authorization.py`
- Test: `tests/test_poe3a_hardening.py`

**Interfaces:**
- Consumes: `PoEAuthorizedBinding`, schema 2 common evidence kind/gates, and `PoEAuthorizedClaim`.
- Produces: `PoEPseBindingCapture`, `PoEPseMultiPortCapture`, `PoEPseMultiPortDeliveryScope`, `encode_poe_pse_multi_port_dimensions()` and `decode_poe_pse_multi_port_delivery_scope()`.

- [ ] **Step 1: Write schema REDs**

Create a valid two-binding literal fixture and mutations for missing, duplicate
and extra bindings; one AUTO binding not delivering; incomplete NEVER;
incorrect simultaneous count; wrong `observed_value`; wrong model/build; missing
or extra dimensions; and incomplete gates. Assert schema 2 still round-trips to
the same literal dimension mapping.

- [ ] **Step 2: Verify the schema REDs fail**

```powershell
./.venv/Scripts/python.exe -m pytest -q tests/test_poe3b_multi_port_pse.py tests/test_poe3a_pse_authorization.py tests/test_poe3a_hardening.py
```

Expected: new imports fail while existing schema 2 tests pass alone.

- [ ] **Step 3: Implement closed schema 3**

Use schema version `3`, one ordered unique binding tuple, three ordered captures,
and per-binding rows. Require AUTO rows to be present/on/positive/delivering and
NEVER rows to be absent-or-off/zero/not-delivering. Require
`simultaneous_active_ports == len(bindings) == result.observed_value` and exact
dimension re-encoding.

- [ ] **Step 4: Connect only at the canonical claim boundary**

After manual and schema 2 decoding, call the schema 3 decoder in
`decode_poe_authorized_claim()`. Return the same `PoEAuthorizedClaim`; do not
expose mechanism identity to the resolver.

- [ ] **Step 5: Run GREEN and commit Task 2**

Run the Step 2 command and commit only the new schema, canonical boundary and
tests as `feat(poe): add multi-port PSE claim schema`.

### Task 3: Derive governed Router0 qualification plans

**Files:**
- Create: `src/packet_tracer_mcp/domain/enterprise/models/poe_capacity.py`
- Create: `src/packet_tracer_mcp/application/use_cases/plan_cp_scale_poe_capacity.py`
- Modify: `src/packet_tracer_mcp/application/use_cases/compose_cp_scale_canonical.py`
- Create: `tests/test_poe3b_qualification_plan.py`

**Interfaces:**
- Produces: `PoEModelQualificationPlan`, `PoECapacityQualificationPlan`, `cp_scale_poe_capacity_qualification_plan(packet_tracer_build, target_stage=CPScaleCanonicalStage.ROUTER0_BRANCH)` and public `cp_scale_canonical_stage_includes_device()`.

- [ ] **Step 1: Write exact plan REDs**

Assert literal ordered binding triples and counts 21/11, exact build/model,
absence of `AccessPoint-PT`, coverage by subset for every powered 3560/3650
device including MLS5, Switch3, MLS3 and MLS4, and rejection of an unknown model.

- [ ] **Step 2: Verify plan RED**

```powershell
./.venv/Scripts/python.exe -m pytest -q tests/test_poe3b_qualification_plan.py
```

- [ ] **Step 3: Implement derivation**

Design E4 with `EnterpriseDesigner().design(cp_scale_intent())`, derive powered
endpoint IDs from `EndpointGroupExpander`, join them to
`cp_scale_physical_design()` bindings on included devices, group by device model,
and preserve first governed occurrence of each exact binding. The use case must
not contain port literals or endpoint counts.

- [ ] **Step 4: Run GREEN and commit Task 3**

Run the plan test plus CP-SCALE intent, physical and Router0 projection tests;
commit as `feat(poe): derive Router0 capacity qualification plans`.

### Task 4: Prove productive admission with synthetic contract fixtures

**Files:**
- Create: `tests/test_poe3b_product_admission.py`
- Test: `src/packet_tracer_mcp/domain/enterprise/services/capability_resolver.py`
- Test: `src/packet_tracer_mcp/infrastructure/catalog/capability_providers.py`

**Interfaces:**
- Consumes: schema 3, complete ephemeral safety, `CapabilitySnapshotStore`, productive capability providers, canonical composition and Router0 projection.
- Produces: test-only A/B snapshots; no production fixture provider.

- [ ] **Step 1: Write admission REDs**

Persist synthetic controlled-probe A and B into a temporary real store. Assert
two independent same-model scopes retain maximum rather than summed capacity;
A authorizes 3560 at 21 but leaves 3650/Router0 blocked; A+B materialize the
canonical composition and Router0 E4/E5/E9/Voice plans, each with a 64-hex hash,
and Voice source hashes equal its Router0 topology/configuration hashes.

- [ ] **Step 2: Run RED and diagnose only contract integration failures**

```powershell
./.venv/Scripts/python.exe -m pytest -q tests/test_poe3b_product_admission.py
```

- [ ] **Step 3: Apply only minimal integration fixes**

If schema 3 does not survive snapshot/provider/resolver composition, fix that
boundary without adding static evidence or relaxing safety. Do not change the
resolver's max-not-sum rule.

- [ ] **Step 4: Run GREEN and commit Task 4**

Run the admission test plus capability store/provider/resolver and canonical
product tests; commit as `test(poe): prove multi-port product admission` unless
a production integration correction is required, in which case use
`fix(poe): integrate multi-port productive authority`.

### Task 5: Generalize the single POE-3A runner

**Files:**
- Modify: `tools/poe2_ap_live.py`
- Modify: `tools/poe3a_pse_live.py`
- Modify: `tests/test_poe3a_hardening.py`
- Modify: `tests/test_poe3a_pse_authorization.py`
- Create: `tests/test_poe3b_capacity_runner.py`

**Interfaces:**
- Consumes: `PoEModelQualificationPlan`, schema 3 and ephemeral safety.
- Produces: a CLI requiring `--execute --model <model> --qualification-id <safe-id>`, with no binding/IOS/JavaScript input.

- [ ] **Step 1: Write runner REDs without invoking LIVE**

Import the runner under controlled test doubles. Assert parser refusal without
execute/model/qualification ID, governed plan selection, rejection of unknown
model or unsafe ID, multi-port apply/capture arguments, exact fixture count,
ephemeral evidence construction, positive-result construction only after both
validators, and no snapshot save on any incomplete boundary.

- [ ] **Step 2: Verify runner RED**

```powershell
./.venv/Scripts/python.exe -m pytest -q tests/test_poe3b_capacity_runner.py
```

- [ ] **Step 3: Generalize the existing experiment and runner**

Allow `Experiment` to carry an ordered unique `switch_ports` tuple while
retaining its historical one-port default and `switch_port` compatibility.
Apply each port from the plan and observe the complete tuple twice per capture.
Create one phone/link per plan binding, clean them all, build schema 3 and typed
ephemeral safety from measured facts, then persist a controlled-probe snapshot
only after cleanup, safety and schema decoding succeed.

- [ ] **Step 4: Preserve old runner/bundle behavior**

Keep committed POE-3A bundle bytes and pinned hashes unchanged. Update producer
tests to the schema 3 plan interface, while historical schema 1/2 classification
tests remain intact.

- [ ] **Step 5: Run GREEN and commit Task 5**

Run runner, POE-3A, observer/runtime, safety, schema and plan tests; commit as
`feat(poe): generalize governed capacity qualification runner`.

### Task 6: Offline closure and publication

**Files:**
- Modify only tests/docs if a causal review finding requires it.

**Interfaces:**
- Consumes: all POE-3B commits.
- Produces: reviewed, graph-current, exact-SHA CI-green `feature/runtime-ripv2`.

- [ ] **Step 1: Run gates in order**

Run focused POE-3B/POE-3A/safety, affected PoE/capability/hardware/CP-SCALE, then
`./.venv/Scripts/python.exe -m pytest -q`.

- [ ] **Step 2: Review and Graphify**

Run `git diff --check`, inspect every changed path against this spec, verify
historical evidence/baseline hashes, and run `graphify update .` inside the
protected-path sentinel.

- [ ] **Step 3: Commit any final review correction**

Each correction requires its own RED. Stage only intended paths and leave the
worktree clean.

- [ ] **Step 4: Push and verify exact-SHA CI**

Fetch `cisco`, stop if remote advanced, push
`HEAD:refs/heads/feature/runtime-ripv2` without force, and require exactly four
successful Windows/Ubuntu 3.11/3.13 jobs for the final SHA.

- [ ] **Step 5: Stop before LIVE**

Report `NEXT_LIVE = A: 3560-24PS / 21 x 7960, then audit before B`. Do not invoke
the runner, bridge, Packet Tracer or Router0.
