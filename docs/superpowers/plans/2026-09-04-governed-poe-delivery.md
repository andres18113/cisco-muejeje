# Governed PoE Delivery Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining offline PoE audit findings without performing a LIVE run, leaving a typed, fail-closed path that can qualify exact powered-device delivery later and authorize only the exact endpoint bindings that the evidence covers.

**Architecture:** Keep `poe-inventory v3` as a control-only observation. Add a separate governed qualification slice with typed request/observation/result models, a lifecycle-owning application service, and a narrow Packet Tracer fixture runtime. Encode the reusable PoE claim in one canonical dimension codec; both the resolver and the reference planner consume that same decoded scope. Persist dimensions unchanged through curated measured records. Update governance only after the productive implementation has a stable commit, so the offline gate can name that non-self-referential HEAD while the historical LIVE state remains immutable.

**Tech Stack:** Python 3.11+, Pydantic v2, dataclasses/protocols, pytest, Packet Tracer bridge JavaScript built only with `json.dumps`, JSON governance documents, graphify, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-04-governed-poe-delivery-design.md`

## Global constraints

- Do not execute Packet Tracer LIVE or Router0 CP-LIVE.
- Preserve `UNKNOWN != SUPPORTED`, `APPLIED != VERIFIED`, and the distinct execution outcomes `FAILED`, `UNOBSERVABLE`, and capability `UNKNOWN`.
- Never derive delivery from `getPower()` or `isPowerOn()`.
- A positive claim must retain exact build, switch model, switch port, endpoint model, endpoint port, observation method, observer, comparison arm, simultaneous episode, and clean restoration provenance.
- Existing or incomplete snapshots remain fail-closed; no migration may synthesize missing dimensions.
- Keep Voice/convergence, Floor1/Floor2/Floor3, PVST, and Router0 semantics unchanged.
- Use ISO/IEC 25010 only as a maintainability lens and ISO/IEC/IEEE 42010 only to review responsibilities and boundaries; do not claim certification or formal conformity.
- Use the checkout-local `.venv\Scripts\python.exe` without `PYTHONPATH` for every Python gate.

---

## Task 1: Characterize the current PoE claim boundary and dimension-loss bug

**Files:**

- Modify: `tests/test_measured_capabilities.py`
- Modify: `tests/test_capability_discovery.py`

- [ ] Add a regression test showing that `MeasuredCapabilityRecord.as_evidence()` currently loses a supplied dimension map.

```python
def test_measured_capability_record_preserves_claim_dimensions():
    dimensions = governed_poe_dimensions(
        access_ports=["FastEthernet0/1"],
        tested_bindings=[("FastEthernet0/1", "7960", "Switch")],
        active_bindings=[("FastEthernet0/1", "7960", "Switch")],
        comparison_model="2960-24TT",
        comparison_states=["not_powered"],
        observation_method="manual_visible_power_state",
        observer_id="reviewer-1",
    )
    record = MeasuredCapabilityRecord(
        model="3560-24PS",
        capability="supports_poe",
        status=CapabilityStatus.SUPPORTED,
        snapshot_hash="a" * 64,
        producer="poe-delivery-qualification",
        original_source=EvidenceSource.MANUAL_VERIFICATION,
        verification_method="manual_visible_power_state",
        summary="one exact binding",
        observed_value=1,
        dimensions=dimensions,
    )

    assert record.as_evidence().dimensions == dimensions
```

- [ ] Add parameterized claim-ceiling tests for missing exact bindings, non-canonical JSON, duplicate bindings, an active binding outside the tested set, mismatched counts, and a model/build-mismatched evidence record. Each case must resolve to `UNKNOWN` with `poe_ports is None`.
- [ ] Run the red tests and record that the dimension constructor/type is absent or the dimensions are discarded:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_measured_capabilities.py tests/test_capability_discovery.py -q
```

- [ ] Do not change production code in this task.

## Task 2: Introduce the canonical exact-scope PoE claim codec

**Files:**

- Modify: `src/packet_tracer_mcp/domain/enterprise/services/poe_claims.py`
- Modify: `src/packet_tracer_mcp/domain/enterprise/services/__init__.py`
- Modify: `tests/test_capability_discovery.py`
- Modify: `tests/poe_delivery_capabilities.py`

- [ ] Define `PoEAuthorizedBinding` as a frozen dataclass with `switch_port`, `endpoint_model`, and `endpoint_port`; define `PoEDeliveryTestedBinding` with the matching comparison port/state; define `PoEDeliveryClaimScope` with the exact candidate model/build, access ports, tested pairs, active bindings, simultaneous count, comparison model, observation method, observer identity, cleanup status, and inventory restoration.
- [ ] Add dimension keys for canonical JSON arrays and observation provenance while retaining the existing count keys for readable compatibility projections.
- [ ] Implement `encode_poe_delivery_dimensions(scope)` using `json.dumps(..., sort_keys=True, separators=(",", ":"))` and deterministic sorted unique values.
- [ ] Implement `decode_poe_delivery_scope(result) -> PoEDeliveryClaimScope | None`. It must reject:

  - missing keys or empty identity strings;
  - JSON whose original string is not the canonical re-encoding;
  - duplicate or malformed triples;
  - active triples not present in tested triples;
  - tested ports outside the exact access-port list;
  - count dimensions that disagree with decoded collections;
  - simultaneous count that differs from the number of active triples;
  - `observed_value` that differs from the simultaneous active count;
  - a non-verified or non-authoritative evidence source.
  - missing/mismatched candidate model or Packet Tracer build;
  - an observation method other than the currently qualified `manual_visible_power_state`;
  - cleanup/restoration other than `clean`/`restored`.

- [ ] Make `poe_claim_has_delivery_basis()` delegate to the decoder. Preserve `UNKNOWN` as non-authorizing, and keep the old inventory assessment control-only.
- [ ] Update test evidence builders so every intentionally positive PoE fixture names the exact covered triples. Do not give production measured UNKNOWN records invented dimensions.
- [ ] Run the focused claim tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_capability_discovery.py tests/test_measured_capabilities.py -q
```

## Task 3: Preserve dimensions through curated measured records

**Files:**

- Modify: `src/packet_tracer_mcp/infrastructure/catalog/measured_capabilities.py`
- Modify: `tests/test_measured_capabilities.py`

- [ ] Add an immutable `dimensions` field to `MeasuredCapabilityRecord` without changing the existing reviewed records:

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class MeasuredCapabilityRecord:
    # existing fields remain unchanged
    dimensions: dict[str, str] = field(default_factory=dict)
```

- [ ] Copy with `dimensions=dict(self.dimensions)` in `as_evidence()` so callers cannot mutate the record through returned evidence.
- [ ] Thread optional dimensions through `_supported()` and `_unknown()` without supplying them to old snapshots.
- [ ] Prove causal persistence with assertions against both `as_evidence()` and `measured_capability_evidence()`.
- [ ] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_measured_capabilities.py -q
```

## Task 4: Project exact authorization from the winning evidence only

**Files:**

- Modify: `src/packet_tracer_mcp/domain/enterprise/models/capabilities.py`
- Modify: `src/packet_tracer_mcp/domain/enterprise/services/capability_resolver.py`
- Modify: `src/packet_tracer_mcp/infrastructure/catalog/capability_providers.py`
- Modify: `src/packet_tracer_mcp/infrastructure/catalog/enterprise_capabilities.py`
- Modify: `tests/test_enterprise_hardware.py`
- Modify: `tests/test_capability_discovery.py`

- [ ] Add `poe_authorized_bindings: list[PoEAuthorizedBinding]` to `DeviceCapabilities`; it defaults empty and is not inferred from catalogue ports.
- [ ] In `CapabilityResolver.with_evidence()`, use the authoritative winner as the fail-closed gate. Union only exact bindings from independently valid same-model/build positive claims, retain all contributing provenance, and set `poe_ports` to the maximum single-run simultaneous count rather than summing runs.
- [ ] When the winner is unknown, unsupported, malformed, old, or incomplete, set `poe_ports=None` and clear `poe_authorized_bindings`.
- [ ] Make PoE winner selection distinguish valid delivery scope from a control-only `supports_poe=UNKNOWN` record. A verified control observation must not outrank a valid delivery observation, and no general capability precedence rule should change.
- [ ] Add `ManualVerificationCapabilityProvider` and register it in the productive adapter so a future persisted qualification snapshot is reachable without relabelling its source.
- [ ] Add causal tests where:

  - strong exact evidence wins over a weaker conflicting record and its dimensions alone are projected;
  - a higher-priority malformed winner does not borrow dimensions from a lower-priority valid record;
  - one evidenced triple does not project an adjacent switch port or another endpoint model;
  - exact-build mismatch leaves the capability and authorization unknown.
  - a valid manual delivery claim remains selected alongside a higher generic-source-priority control-only UNKNOWN record;
  - a saved manual qualification snapshot round-trips through the productive adapter.

- [ ] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_enterprise_hardware.py tests/test_capability_discovery.py -q
```

## Task 5: Carry endpoint model identity into physical bindings

**Files:**

- Modify: `src/packet_tracer_mcp/domain/enterprise/models/hardware.py`
- Modify: `src/packet_tracer_mcp/domain/enterprise/scenarios/cp_scale_physical.py`
- Modify: `tests/test_cp_scale_canonical_physical.py`
- Modify: `tests/test_reference_hardware_planner.py`

- [ ] Add `endpoint_model: str = ""` to `EndpointPortBinding`. The empty default keeps old serialized designs readable but never authorizes powered delivery.
- [ ] Extend `_binding()` and `_range()` to require the endpoint model supplied by the CP-scale role/model mapping already used to instantiate endpoints.
- [ ] Populate the canonical CP-scale phone bindings with `7960` and powered AP bindings with `AccessPoint-PT`; populate non-powered endpoints too so the physical contract remains explicit.
- [ ] Update test fixtures to name their endpoint model. Add a characterization proving an old binding with no model remains parseable but cannot pass PoE authorization.
- [ ] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cp_scale_canonical_physical.py tests/test_reference_hardware_planner.py -q
```

## Task 6: Enforce exact PoE authorization in the reference planner

**Files:**

- Modify: `src/packet_tracer_mcp/domain/enterprise/services/reference_hardware_planner.py`
- Modify: `src/packet_tracer_mcp/domain/enterprise/services/hardware_planner.py`
- Modify: `src/packet_tracer_mcp/domain/enterprise/models/hardware.py`
- Modify: `tests/test_reference_hardware_planner.py`
- Modify: `tests/test_cp_scale_poe_authorization.py`
- Modify: `tests/test_enterprise_hardware.py`

- [ ] Change the powered-demand projection from `device_id -> set[port]` to exact requested bindings including endpoint model and endpoint port.
- [ ] In `_admit_powered_ports()`, require every demanded triple to occur in `candidate.capabilities.poe_authorized_bindings` and require the total simultaneous demand not to exceed the decoded count.
- [ ] Fail closed as `NEEDS_VERIFICATION`/`PARTIALLY_RESOLVED` when the model, switch port, endpoint model, or endpoint port differs or is absent. Use `INCOMPATIBLE` only for coherent evidence that proves a real capacity shortfall or unsupported capability.
- [ ] Add causal tests:

  - evidence for `FastEthernet0/1` authorizes that exact 7960 binding;
  - the same evidence does not authorize `FastEthernet0/2`;
  - evidence for a 7960 does not authorize `AccessPoint-PT` on the same port;
  - evidence for endpoint port `Switch` does not authorize a different endpoint port;
  - two individually tested but non-simultaneous ports do not authorize a two-endpoint simultaneous design;
  - exact two-binding simultaneous evidence authorizes exactly those two bindings.

- [ ] Replace count-only `_rebudget()` test mutations with exact decoded scopes where the tests intentionally expect compatibility.
- [ ] Carry authorized switch ports into `PlannedNetworkDevice` and make generic `PortAssignmentPlanner` restrict every `requires_poe` slice to those ports. After the endpoint model is resolved, make `EnterpriseCompiler` reject any switch-port/endpoint-model/endpoint-port triple absent from the claim. One authorized port or endpoint kind may never become another.
- [ ] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_reference_hardware_planner.py tests/test_cp_scale_poe_authorization.py tests/test_enterprise_hardware.py -q
```

## Task 7: Define typed qualification observations and validation rules

**Files:**

- Create: `src/packet_tracer_mcp/domain/enterprise/models/poe_delivery.py`
- Create: `src/packet_tracer_mcp/domain/enterprise/rules/poe_delivery.py`
- Modify: `src/packet_tracer_mcp/domain/enterprise/models/__init__.py`
- Create: `src/packet_tracer_mcp/domain/enterprise/rules/__init__.py`
- Modify: `tests/test_poe_delivery_qualification.py`

- [ ] Define passive Pydantic models only—no business validation in models:

  - `PoEDeliveryQualificationRequest`: exact PT build, candidate/comparison models, one non-empty simultaneous binding group;
  - `PoEDeliveryBindingRequest`: candidate port, comparison port, endpoint model, endpoint port;
  - `PoEDeliveryFixtureIdentity`: exact created device names/models and exact observed link endpoints;
  - `PoEDeliveryArmState`: `POWERED`, `NOT_POWERED`, `UNOBSERVABLE`;
  - `PoEDeliveryArmObservation`: switch/model/port and endpoint/model/port plus visible indicator text and explicit switch-ready/link-ready/endpoint-settled attestations;
  - `PoEDeliveryManualObservation`: observer ID, UTC timestamp, method, simultaneous flag, and candidate/comparison observations for every binding;
  - `PoEDeliveryQualificationResult`: execution status, capability result, cleanup status, initial/final fingerprints, created/deleted identities, failure reason, and optional runtime snapshot path.

- [ ] Add rule functions returning `ValidationResult`, with new specific `ErrorCode` members for incomplete PoE fixture/observation if needed.
- [ ] Validate exact identity equality, one-to-one binding coverage, non-empty visible indicators, ready/linked/settled arms, candidate `POWERED`, comparison `NOT_POWERED`, and `simultaneous=True` before a positive claim is constructed.
- [ ] Candidate and comparison both powered, either arm unobservable, missing observer data, duplicated observations, or identity drift must produce a non-valid rule result and must never imply unsupported hardware.
- [ ] Add tests for each causal failure and one complete positive observation.
- [ ] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_poe_delivery_qualification.py -q
```

## Task 8: Implement the lifecycle-owning qualification use case

**Files:**

- Create: `src/packet_tracer_mcp/application/use_cases/poe_delivery_qualification.py`
- Modify: `src/packet_tracer_mcp/application/use_cases/__init__.py`
- Modify: `tests/test_poe_delivery_qualification.py`

- [ ] Define narrow protocols `PoEDeliveryFixtureRuntime`, `PoEDeliveryObserver`, and `CapabilitySnapshotWriter`. The use case owns ordering; runtime and observer only perform their respective operations. Pass the observer a deadline derived from an injected clock without adding sleep/retry policy.
- [ ] Implement `PoEDeliveryQualificationService.qualify(request)` with this exact control flow:

  1. capture initial inventory fingerprint;
  2. create candidate/comparison switches and one powered endpoint per arm per binding;
  3. verify exact created model identity and both link endpoints;
  4. invoke the injected manual visible-state observer once for the complete simultaneous fixture;
  5. validate the typed observation;
  6. always remove all created objects in `finally`, endpoint-first;
  7. wait with the existing bounded fingerprint restoration mechanism;
  8. produce a reusable positive result only if observation and cleanup/restoration both verify;
  9. persist a runtime `CapabilitySnapshot` whose result contains the canonical exact-scope dimensions and `MANUAL_VERIFICATION` provenance.

- [ ] Separate outcomes:

  - runtime exception or creation/link failure -> `ProbeExecutionStatus.EXECUTION_ERROR`, capability `UNKNOWN`;
  - observer cannot see a required state -> `ProbeExecutionStatus.VERIFY_FAILED` with explicit unobservable reason, capability `UNKNOWN`;
  - visible candidate/control mismatch -> verification failed, capability `UNKNOWN`;
  - valid observation but dirty cleanup/restoration -> result not reusable, capability `UNKNOWN`;
  - only complete observation plus clean restoration -> `VERIFIED` and `SUPPORTED`.

- [ ] Do not use arbitrary sleeps or retry-until-green. Depend only on the bounded inventory restoration API already present.
- [ ] Build a deterministic fake runtime and observer in tests. Prove cleanup is attempted after failures at every stage, cleanup failures are retained, all created identities are accounted for, and the result itself cannot expose evidence unless restoration is clean.
- [ ] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_poe_delivery_qualification.py -q
```

## Task 9: Add the productive Packet Tracer fixture runtime without claiming LIVE evidence

**Files:**

- Create: `src/packet_tracer_mcp/infrastructure/execution/poe_delivery_runtime.py`
- Modify: `src/packet_tracer_mcp/infrastructure/execution/__init__.py`
- Create: `tests/test_poe_delivery_runtime.py`

- [ ] Implement `PacketTracerPoEDeliveryFixtureRuntime` around the same injected `send_and_wait` transport as `PacketTracerBridgeProbeRuntime`.
- [ ] Delegate fingerprint capture/restoration to `PacketTracerBridgeProbeRuntime`; do not duplicate lifecycle policy.
- [ ] Generate compact one-line JavaScript with `json.dumps` for every model, name, and port. Use only already-confirmed repository APIs: `lwAddDevice`, `lwAddLink`, `getDevice`, `getModel`, `getPort`, `getLink`, `getPort1`, `getPort2`, `getOwnerDevice`, and logical-workspace `removeDevice`.
- [ ] Device creation must inspect identity and requested port existence but must not reuse either `create_temporary_device` or `_create_probe_endpoint`: both reach power getters through creation/readiness code. Delegate only inventory fingerprint/restoration behavior.
- [ ] Link creation must return typed exact endpoints observed from the created link. A mere truthy `getLink()` is insufficient.
- [ ] Cleanup must target only names recorded as successfully attempted by this qualification and return per-object outcomes.
- [ ] Add transport-recording tests proving:

  - adversarial names/models/ports remain JSON string literals;
  - no generated script contains `.getPower(` or `.isPowerOn(`;
  - exact candidate and comparison models/ports are returned;
  - malformed bridge payloads fail closed;
  - deletion is endpoint-first and confined to recorded fixture identities.

- [ ] Do not instantiate this runtime, contact the bridge, or create a new MCP tool in this offline task. The typed constructor plus application service is the prepared productive seam for the future governed runner.
- [ ] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_poe_delivery_runtime.py tests/test_bridge_security.py tests/test_transport_mutation_containment.py -q
```

## Task 10: Run affected gates and create the productive implementation commit

**Files:** all productive and test files from Tasks 1–9.

- [ ] Run import isolation and environment checks:

```powershell
.\.venv\Scripts\python.exe -c "import pathlib,sys,packet_tracer_mcp; root=pathlib.Path.cwd().resolve(); module=pathlib.Path(packet_tracer_mcp.__file__).resolve(); assert pathlib.Path(sys.executable).resolve()==(root/'.venv/Scripts/python.exe').resolve(); assert module.is_relative_to(root); assert ('packet_tracer_mcp' in sys.modules) != ('src.packet_tracer_mcp' in sys.modules); print(sys.executable); print(module)"
.\.venv\Scripts\python.exe -m pytest tests/test_worktree_isolation.py -q
```

- [ ] Run the complete affected set:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_poe_delivery_qualification.py tests/test_poe_delivery_runtime.py tests/test_capability_discovery.py tests/test_measured_capabilities.py tests/test_enterprise_hardware.py tests/test_reference_hardware_planner.py tests/test_cp_scale_poe_authorization.py tests/test_cp_scale_canonical_physical.py tests/test_cp_scale_offline_qualification.py tests/test_cp_scale_layout.py tests/test_e95_reference_regression.py -q
```

- [ ] Run `graphify update .`, inspect only relevant graph changes, and run `git diff --check`.
- [ ] Run the full offline suite:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

- [ ] Review the complete productive diff directly against source, tests, and the approved spec. Resolve every unexplained failure.
- [ ] Obtain a fresh independent `code-review` of this coherent change set. Verify the reviewer used the exact absolute worktree and inspected the named changed paths/commands. Treat each finding as a hypothesis, validate it from repository evidence, fix accepted material findings, rerun gates, and re-review if the material diff changes.
- [ ] Commit only productive code/tests/spec/plan/graph updates as a coherent implementation commit:

```powershell
git add -- docs/superpowers src tests graphify-out
git commit -m "feat: prepare governed PoE delivery qualification"
```

- [ ] Record this implementation SHA. It is the SHA that the offline operational gate will bind to.

## Task 11: Separate historical LIVE state from the current offline gate

**Files:**

- Modify: `docs/reference/cp-scale/current_state.json`
- Modify: `tests/test_cp_scale_current_state.py`

- [ ] First add/update tests asserting explicit top-level `last_live_state` and `current_offline_operational_gate` projections.
- [ ] Preserve byte-for-byte-equivalent historical values under `last_live_state`: historical `source_head`, `latest_live_run`, run counters, hashes, artifacts, evidence, and outcomes.
- [ ] Bind `current_offline_operational_gate.source_head` to the Task 10 implementation SHA, not to the later governance commit.
- [ ] Represent the current gate explicitly:

```json
{
  "poe_delivery": "unknown",
  "poe_ports": null,
  "hardware_plan": "partially_resolved",
  "canonical_composition": "blocked_before_topology",
  "router0_authorized": false,
  "next_active_step": "RUN_ONE_GOVERNED_POE_DELIVERY_QUALIFICATION_FROM_CLEAN_GREEN_HEAD"
}
```

- [ ] Update the compatibility projection of `next_active_step` to the same PoE-specific step and ensure no compatibility field implies Router0 authorization.
- [ ] Add causality tests that detect historical-value drift and that fail if Router0 becomes the next step while PoE is unknown.
- [ ] Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cp_scale_current_state.py tests/test_cp_scale_poe_authorization.py tests/test_cp_scale_offline_qualification.py -q
```

## Task 12: Update the single handoff and close offline validation

**Files:**

- Modify: `handoff_github_corrections.md`

- [ ] Keep the handoff compact and oriented to another AI. Include:

  - final baseline and both implementation/governance SHAs;
  - what `d2fd950`, `9dcc9183`, and the new implementation changed;
  - resulting PoE architecture and exact authorization boundary;
  - `DO_NOT_REDISCOVER` facts;
  - `OPEN_DECISIONS` only for genuinely unresolved future LIVE choices;
  - the remaining CP-LIVE path, beginning with exactly one governed PoE delivery qualification;
  - `agents-muejeje` as complementary reviewers/specialists, never substitutes for autonomous agents or Codex's final authority;
  - explicit `NO_LIVE` statement.

- [ ] Do not paste long logs and do not create another handoff.
- [ ] Run the focused governance tests, all affected tests, `git diff --check`, import checks, and the full pytest suite again.
- [ ] Run `graphify update .` again if governance or handoff links change the graph.
- [ ] Perform a fresh direct review of the final diff. If the governance/handoff changes are substantive enough to alter review scope, obtain a fresh independent code review and adjudicate findings.
- [ ] Commit the governance state and handoff, including the previously untracked handoff file:

```powershell
git add -- docs/reference/cp-scale/current_state.json tests/test_cp_scale_current_state.py handoff_github_corrections.md graphify-out
git commit -m "docs: govern the next PoE delivery qualification"
```

## Task 13: Push only the governed upstream and verify exact-SHA CI

- [ ] Confirm branch, remotes, commits, and cleanliness before the external mutation:

```powershell
git status --short --branch
git remote -v
git log --oneline --decorate -5
```

- [ ] Push only the current branch to the requested upstream; do not force and do not rewrite history:

```powershell
git push cisco HEAD:feature/runtime-ripv2
```

- [ ] Record the exact pushed SHA and verify GitHub Actions for that SHA until all four required checks reach terminal success. Use bounded polling and report any terminal failure; do not retry commits or workflows until green.
- [ ] Confirm `git status --porcelain` is empty and `git rev-parse HEAD` equals the SHA whose four checks are green.
- [ ] Deliver the requested report sections: `SKILLS_USED`, `START_STATE`, `AUDIT_FINDINGS`, `ARCHITECTURE_DECISIONS`, `GOVERNANCE`, `POE_DELIVERY_OBSERVATION`, `CLAIM_PERSISTENCE`, `AUTHORIZATION_GRANULARITY`, `CHANGES`, `VALIDATION`, `FINAL_HEAD`, `GITHUB_ACTIONS`, `HANDOFF`, `WORKTREE_STATE`, `NO_LIVE`, and `NEXT_ACTIVE_STEP`.

## Completion invariant

Do not declare completion unless all of the following are simultaneously true:

- current state separates immutable LIVE history from the current offline gate;
- Router0 remains unauthorized;
- a typed productive path can capture real visible powered-device delivery later without claiming it now;
- incomplete or historical PoE evidence cannot authorize a claim;
- dimensions survive governed persistence and reproduce the claim ceiling;
- exact port/endpoint authorization is protected by causal tests;
- baseline remains `UNKNOWN` with `poe_ports=None`;
- full offline suite and four exact-SHA GitHub checks are green;
- the worktree is clean;
- no LIVE budget was consumed;
- the only next active step is `RUN_ONE_GOVERNED_POE_DELIVERY_QUALIFICATION_FROM_CLEAN_GREEN_HEAD`.
