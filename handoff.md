# CP-SCALE continuation handoff

## Resume identity and hard boundaries

```text
BRANCH = feature/runtime-ripv2
UPSTREAM = personal/feature/runtime-ripv2
HANDOFF_BASE_HEAD = a519987acb168ec6d3af14a7d81c0c1ef034f1f5
PACKET_TRACER_BUILD = 9.0.1.0858
ROUTING_CORE = GOVERNED VERIFIED
ROUTER4_SWITCH10 = GOVERNED VERIFIED
PT_MCP_RELIABLE_SCALE_ENVELOPE = 4 devices / 4 links
LIVE_SEMANTIC_WORKSPACE = 0 devices / 0 links
CLEANUP = VERIFIED twice
FLOOR1 = NOT VERIFIED
CP_SCALE = OPEN
E10 = FORBIDDEN
```

No live run remains active. Persistent exec session `42867` terminated safely after the
Floor-1 failure and cleanup. Do not resume or reuse it. Stay OFFLINE until both Floor-1
defect classes below have typed, fail-first fixes and affected/full regression is green.
Do not re-qualify the routing core or Router4/Switch10 absent a real regression.

Commits produced and already pushed during this run, after the requested starting HEAD
`38bf3665881d5d367f43256668ac37c1745fd496`:

```text
420cf38 feat(cp-scale): add governed persistent live staging
2d90b0c fix(cp-scale): reverify after serial convergence
8a15b14 fix(e5): keep carrier outside configuration claims
f324912 chore(cp-scale): checkpoint rematerialized routing core
390c199 fix(cp-scale): prequalify canonical capabilities
a9c2e57 chore(cp-scale): checkpoint reverified routing core
d49cef7 fix(cp-scale): govern trunk readback ceiling
b424c9e chore(cp-scale): checkpoint core with trunk evidence
6e8196d fix(cp-scale): retain verified serial orientation
d96b045 chore(cp-scale): checkpoint core serial inheritance
a519987 chore(cp-scale): checkpoint Router4 Switch10
```

## Canonical authority and invariants

The topology authority is:

- `docs/reference/cp-scale/diseno_logico_IMP.md`
- `docs/reference/cp-scale/topologia_completa_IMP.md`

Typed sources are:

- `src/packet_tracer_mcp/domain/enterprise/scenarios/cp_scale.py`
- `src/packet_tracer_mcp/domain/enterprise/scenarios/cp_scale_physical.py`
- `src/packet_tracer_mcp/application/use_cases/compose_cp_scale_canonical.py`

The governed target is exactly 314 devices / 219 links: 18 network devices, 296
endpoint/AP devices, 279 workload endpoints, 17 APs, 18 infrastructure links, 199
switch-direct endpoint links, and 2 documented phone-PC passthrough links. Current
authority pins 3x2811, 10x2960-24TT, 3x3650-24PS, and 2x3560-24PS. If evidence requires
a stronger successor topology, update typed authority, reference documents, and tests
together; do not silently substitute a model or change endpoint pairing.

VLAN policy is DATA 10, VOICE 20, and IoT/AP/printers 30. Phone ports require access
VLAN 10 plus voice VLAN 20. Trunks allow only 10/20/30. The STP ceiling is PVST;
Rapid-PVST remains unqualified. UNKNOWN fails closed and APPLIED is never VERIFIED.
Use typed/product paths only: no raw IOS/JS, `pt_send_raw`, or E10.

## Terminated Floor-1 run and durable evidence

The ignored durable artifact is `data/cp-scale/live-canonical-progress.json` (last write
`2026-08-24T18:42:56.4327703Z`). It contains only successful `routing-core` and
`router4-switch10` stage checkpoints; Floor 1 was never checkpointed. Its Floor-1
failure is:

```text
CanonicalLiveFailure: Configuration at 'floor1' contradicted the plan:
Configuration read-back contradicted the plan for: <43 action IDs>
```

Cleanup reports `verified=true`. It was independently observed twice as 0 semantic
devices / 0 links. Six backend-managed `Power Distribution Device` objects with zero
ports remained outside the semantic workspace on both observations. No presentation
topology was retained.

The user-provided canvas capture is
`C:\Users\Andres\Downloads\topologia_floor1.png` (198204 bytes; UTC
`2026-08-24T18:29:25`). It visibly shows all 21 Cisco 7960 switch links red while nearby
PC/AP links are mostly green. Computer Use confirmed the MCP Control Center/log window
had HTTP and file bridges connected with valid token state. Two exact Packet Tracer
window activation/capture attempts timed out, so UI automation was stopped; the user's
capture is the reliable visual evidence. It proves the symptom, not its cause.

## Defect A: PoE admission fails open

This defect is mechanically proven and is independent of the 43 configuration
contradictions unless later evidence connects them.

- Floor 1 declares `required_poe_ports=24` in `cp_scale_physical.py`.
- `cp_scale.py` marks every Cisco 7960 and AP `requires_poe=True`.
- Floor 1 binds 21 phones to Switch5 Fa0/1..21; each phone uses its `Switch` port.
  Switch4/Switch5 are currently exact-reference `2960-24TT` devices.
- `ReferenceHardwarePlanner.plan()` in
  `src/packet_tracer_mcp/domain/enterprise/services/reference_hardware_planner.py`
  validates model/module/port counts but consumes neither block `required_poe_ports`
  nor per-binding `ExpandedEndpoint.requires_poe`. It therefore admits a selected
  exact-reference switch with `poe_capacity=None`.
- `EnterpriseCompiler._compile_endpoint_links()` and `_capability_warnings()` in
  `src/packet_tracer_mcp/domain/enterprise/services/enterprise_compiler.py` allocate
  only `ACCESS_CAPABLE` and reduce unknown PoE to a warning. Explicit `_PortAllocator`
  reservations also skip required-class validation.

Direct PoE endpoint demand in the current canonical bindings is:

```text
Switch4=1  Switch5=23  Switch6=1  Switch7=16  Switch8=1  Switch9=5
Switch0=1  Switch1=15  Switch3=9   MLS3=3     MLS4=2     MLS5=8  MLS6=1
```

The fix must derive per-switch demand from expanded endpoint truth plus the exact
binding, reconcile the block aggregate, require exact-build PoE capability evidence,
and reject UNKNOWN/unsupported/insufficient capacity from live admission. Do not infer
PoE from a model name. An aggregate block total alone cannot prove each selected switch
is compatible.

Port-class blast radius must be handled deliberately: 17 canonical infrastructure
bindings currently put `UPLINK_CAPABLE` demand on FastEthernet access-only ports and are
allowed by explicit non-serial fallback; 16 endpoint bindings use Gigabit uplink-only
ports. A strict allocator fix will expose those endpoint bindings and must not erase the
documented infrastructure fallback ceiling.

Two temporary fail-first regressions were proved, then reverted when implementation was
stopped, so the worktree contains no half-fix:

1. In `tests/test_reference_hardware_planner.py`, one PoE-required IP phone explicitly
   bound to exact-build 2960 currently returns
   `valid compatible 2960-24TT None None []` instead of failing closed.
2. In `tests/test_cp_scale_canonical_physical.py`, every direct PoE endpoint is required
   to fit an exact per-switch capacity; current selected devices expose
   `poe_capacity=None`.

Recreate those tests first and add a per-switch over-capacity case (for example demands
3+1 against capacities 2+2). A draft narrow planner fix made its focused regression
green, but was fully reverted because topology, per-port evidence, and canonical blast
radius were not yet closed. Preferred semantics to validate are UNKNOWN => provisional
`PARTIALLY_RESOLVED` / `NEEDS_VERIFICATION`; unsupported or insufficient =>
`UNRESOLVED`; neither may pass the live compiler gate.

A read-only in-memory candidate was mechanically compiled, but not adopted: replacing
only Switch5/7/9/1/3 with 3560, consolidating phones/APs on those switches, and enabling
PC/phone passthrough produced exactly 314 devices / 219 links (142 endpoint-access, 59
phone-passthrough, 18 infrastructure; models 7x3560, 5x2960, 3x3650, 3x2811). Treat this
only as evidence that one governed redesign is structurally possible. It changes the
current canonical pairing/link-role authority and still cannot establish chassis power
budget or active delivery, so do not select it without closing those governance gaps.

## Exact-build capability evidence

Evidence below is for Packet Tracer `9.0.1.0858` only:

- 2960-24TT: exact port inventory VERIFIED; fresh VLAN/trunk support VERIFIED; PoE is
  UNKNOWN and no `supports_poe` capability is admitted.
- 3560-24PS: exact port inventory VERIFIED; VLAN/trunk support VERIFIED; current typed
  PoE capability reports 24 powered FastEthernet ports. Raw `getPower`/`isPowerOn`
  signals also appear on Gigabit ports, but must not be counted without a governed
  contract. `power_delivery_active=None`: powered-device delivery and watt-budget
  headroom remain unobserved. Twenty-one phones plus three APs would consume all 24
  admitted powered ports, not prove budget margin.
- 3650-24PS: exact inventory VERIFIED (Gi1/0/1..24 and Gi1/1/1..4); VLAN/trunk support
  VERIFIED; PoE is UNKNOWN and no `supports_poe` capability is admitted.
- Cisco 7960: exact identity and port inventory VERIFIED (`PC`, `Switch`, plus observed
  logical Vlan1); phone runtime/power delivery is UNKNOWN. Its live switch links were
  visually red.

`src/packet_tracer_mcp/domain/enterprise/models/discovery.py` explicitly separates
port `getPower`/`isPowerOn` observations from powered-device delivery. Do not upgrade
the latter by inference.

## Defect B: 43 independent configuration contradictions

Offline projection maps all 43 failed IDs to `endpoint_addressing`: 3 AP static actions,
21 Cisco7960 DHCP actions, 4 Motion Detector DHCP actions, 11 Smoke Detector DHCP
actions, and 4 Webcam DHCP actions. No PC or printer action contradicted. Map expected
actions with
`project_cp_scale_canonical_stage(comp, CPScaleCanonicalStage.FLOOR1).configuration`.

```text
AP:
5182633057691afc bb7bcd44f41d6d47 454539fd45427dd8

PHONE:
432556a02ddf724f 5457b517cd3f9637 fa24a758f868fc29 38669eb3340e6892
7ab8a9f84fd7e49b 340d7b7459a80c91 12eb81e8261bcb03 9297694740a6bb36
79da1d6279963b2d 63d372b30354d120 20042b96a790cc53 b362216e16eef648
4b72636c210666b4 dfbd3dda98ac7c11 19a5594b874504c4 1b67b90adcb4c169
c88d6f2e4949a99b 60f73066a2a34381 3f34feb723de1e29 bc5c5cb129183cdc
3a69cc03bb9c2463

MOTION:
61b00a15ea63221e 898cf104c8c124de 077535d05c89fd14 cc82f2cfaafa7bcf

SMOKE:
9d84c297c8272cc5 59feb0d394ba7f49 df8b1f44736fa013 25d3cf1b3a00d079
d89eebdffb84214a a1ac3b84c4970f5b 472bfe7ef521a2b9 5c4b41d835c72ad5
3a953e4e1d3174b2 0ed800efcf801051 bd1d9475f715b518

WEBCAM:
853c8e540de748a0 d317eed31d68ea33 54b85bbd8b1f33c6 ff13c1596933a033
```

The IDs live in the artifact's top-level failure string. Exact per-field actual
readbacks were lost because `_execute_stage()` retains stage evidence locally and the
outer runner appends it only after stage success; an exception therefore omits partial
failure evidence from the journal. Before another live attempt, add a fail-first test
and typed fix for durable partial/failure evidence capture (or another governed method
that preserves exact actual fields), then group contradictions by observed root cause.
Do not attribute these actions to PoE without evidence.

## Verification ledger

```text
ROUTING_CORE = GOVERNED VERIFIED
ROUTER4_SWITCH10 = GOVERNED VERIFIED
FLOOR1_PHYSICAL = transiently APPLIED, then discredited and cleaned
FLOOR1_CONFIGURATION = CONTRADICTED
PHONE_POWER_AND_LINK = NOT VERIFIED
VOICE_DATA_VLAN_10_20 = NOT VERIFIED
POE_ADMISSION_DEFECT = PROVEN FAIL-OPEN
2960_POE = UNKNOWN
3650_POE = UNKNOWN
3560_POWERED_PORT_COUNT = SUPPORTED (24 FastEthernet ports)
3560_ACTIVE_POWER_DELIVERY_AND_WATT_BUDGET = UNKNOWN
```

Earlier full regression was `2622 passed, 5 warnings`; the last retained affected run
was `76 passed`. The temporary two-test PoE fail-first run failed for the intended
product reason; the experimental narrow fix passed before all diagnostic code/test
edits were reverted. Only this handoff is intended to be uncommitted at checkpoint.

## NEXT_ACTIVE_STEP

1. Verify branch/HEAD/upstream/worktree, read this file, and inspect the ignored progress
   artifact. Remain OFFLINE.
2. Recreate the PoE admission regressions and the per-switch capacity case; fix the typed
   planner/compiler/capability seam so exact demand, capacity, port class, and UNKNOWN
   semantics fail closed.
3. Map all 43 configuration IDs to expected action and exact readback. First preserve
   partial contradiction evidence durably; then write fail-first tests for each proven
   root-cause group and AUTOFIX the typed product path independently of PoE.
4. Reconcile any topology/model change with exact-build capability evidence and update
   both canonical documents plus typed tests. Do not assume the candidate redesign.
5. Run affected and full checkout-local `.venv` regression; update graphify after source
   changes.
6. Only after offline closure, pass the live-run namespace gate, rematerialize the
   verified core, Router4/Switch10, and Floor 1 through governed typed staging.
7. Verify fresh switch/phone physical bindings, cable identity, admin/oper state, actual
   phone power/runtime state, PoE delivery evidence, access VLAN 10 + voice VLAN 20,
   endpoint addressing, and fresh readback. Red expected phone links are blocking.
8. Qualify Floor 1 only with clean LIVE evidence; checkpoint and push to
   `personal/feature/runtime-ripv2`.
9. Continue sequentially with Floor 2, Floor 3, Router0/3650, Router3/2960, remaining
   canonical topology, full CP-SCALE qualification, and a verified visible presentation.
