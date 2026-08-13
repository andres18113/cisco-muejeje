# E9.5 Stage 3A4 — readiness and dependency map

Produced at **Debt Checkpoint 2**, 2026-08-12, on `feature/runtime-ripv2`.

This is not the Stage 3A4 implementation and not its acceptance record. It is
the dependency audit CP2 owes the stage: what 3A4 is, what already exists, what
does not, and which seams it must use.

## Provenance warning, stated first

**There is no governed specification of Stage 3A4 in this repository.** That was
verified exhaustively, not assumed: `3A4` appears in exactly five places in the
tree, and none of them states a scope, deliverable, gate or acceptance
criterion.

| Where | What it says |
| --- | --- |
| `handoff.md` | `Stage 3A4 (traffic + reference topology) is still pending` |
| `handoff.md` | `decide what CP2 must clear before Stage 3A4` |
| `technical-debt.md`, CP2 definition | `before returning to E9.5 Stage 3A4` |
| `technical-debt.md`, planned work | `- Stage 3A4;` |
| `tests/test_e95_capability_reconciliation.py` | `"Por eso la deuda no bloquea 3A4: la referencia fija sus candidatos."` |

`e95-stabilization.md` — the primary E9.5 governance document — contains the
strings `Stage` and `3A` **zero times** in 467 lines. The whole 3A1–3A4
decomposition survives only in commit messages, source comments and test
docstrings.

So the six-word parenthetical *"traffic + reference topology"* is the entire
governed statement of the phase. Everything in §1 below is recovered from
executable evidence and from the roadmap direction ratified at CP2. It is
recorded here so that Stage 3A4 does not have to be reconstructed from
conversation the way this checkpoint had to reconstruct it.

## 1. The Stage 3A4 contract, as recovered

### Where 3A4 sits

The reconstructed stage line, each attribution from source rather than memory:

- **3A1** — demand-to-capacity policy, offline. `link_performance.py`,
  `link_performance_planner.py`. Commit `4f36e93`, *"decide link capacity from
  demand instead of from a constant"*.
- **3A2** — serial clock measured live and bound to a runtime link.
  `PT_2911_HWIC2T_SERIAL_CLOCK` in `link_mode_capabilities.py`, annotated
  *"Medido en E9.5 Stage 3A2"*.
- **3A3 (+B…H)** — Ethernet runtime and capacity verification. **CLOSED.**
  Policy changelog pinned at `POLICY_VERSION = "6"` in
  `link_performance_planner.py`.
- **3A4** — traffic + reference topology. Pending.

The ledger's CP2 definition says *"before **returning** to E9.5 Stage 3A4"*.
That word is load-bearing: 3A4 resumes the link-performance line that the
RIPv2/acceptance work interrupted. It is not a continuation of routing work.

### What the phase must establish

The productive end-to-end path that does not yet exist:

```text
EnterprisePlan / typed enterprise intent
  → hardware / configuration plans
  → compiler
  → TopologyPlan / DeploymentManifest
  → production physical deployment runtime
  → production configuration applicator
  → control-plane application
  → authoritative readback
  → traffic execution / measurement
  → typed evidence / results
```

Two rules govern how it is built, both inherited from what the University
Acceptance got wrong:

- the acceptance harness is a **behavioural reference, not the implementation
  path**. A harness may orchestrate; it must not perform mutations;
- a missing production seam is **named and implemented**, never bypassed with
  raw JS or raw IOS to make the topology work.

## 2. What Stage 3A3 already guarantees — do not repeat it

Stage 3A3 is CLOSED and 3A4 **consumes** its output rather than recomputing it.

Already proven and not to be re-derived:

- measured Ethernet link-mode profiles on PT 9.0.1.0858
  (`link_mode_capabilities.py`), with the explicit rule that what is absent is
  *unmeasured*, not unsupported;
- the three-ceiling separation — nominal, auto-negotiable, forceable — in
  `link_performance.py`, and the correction that a negotiable ceiling is not
  the effective capacity;
- capacity bounded by the slower of the two endpoints;
- a productive gate that refuses to mutate an unmeasured mode: an unprofiled
  endpoint leaves capacity UNKNOWN, which is not permission;
- routed/switched classification derived from the interface, not the device
  category;
- the serial clock path verified against a real Packet Tracer link, with the
  rate ceiling established by bounded reproduction rather than by datasheet;
- `POLICY_ID = "enterprise-link-performance"`, `POLICY_VERSION = "6"`, including
  the deliberate v6 revert of v5.

3A4 must treat all of the above as given inputs. Re-measuring Ethernet capacity
would be repeating a closed stage.

## 3. Reference topology — what is missing

The artifact governed docs attach to 3A4 is the **offline** pinned reference,
`tests/test_e95_reference_regression.py`. Its own header says it *"intentionally
stop[s] at compilation and pure reconciliation"*. It never touches Packet
Tracer.

What it is: one HQ site, 30 PCs / 30 phones / 8 cameras / 4 printers / 3 APs /
1 server, hardware pinned by hand to `2960-24TT` and `2911`, hierarchy forced,
compiled E4→E9 and fingerprinted for determinism across nine runs.

Four gaps between that fixture and what 3A4 needs:

1. **It has no serial link, and structurally cannot have one.** The fixture
   cables through `topology_catalog.cable_for` → `infer_cable`, which resolves
   from `CABLE_RULES` with a `"straight"` default. That table maps
   `("router", "router")` to `"cross"` and contains **no rule yielding
   `"serial"`** — so every link the reference compiles is Ethernet regardless of
   how the intent grows. (Commit `d2d16f6` recorded the shape at the time as
   "64 links, all Ethernet, all on media-default autonegotiation"; treat that
   count as historical, since no current test asserts it.)

   This matters because serial is the *only* medium where demand actually
   changes the selected capacity: the Ethernet path is bounded by measured
   endpoint profiles, while the serial path falls through to
   `ENTERPRISE_SERIAL_FALLBACK_WITHOUT_TRAFFIC_INFORMATION` when no traffic is
   supplied. A traffic-driven capacity decision therefore **cannot be
   demonstrated on the reference as it stands**, and making it possible means
   changing how the reference is cabled, not merely adding traffic to it.
2. **Its `ControlPlaneIntent` carries only STP and security policy ids** — no
   `routing_domains`, no `failure_scenarios`. It exercises neither the typed
   RIPv2 path just accepted nor the fault machinery.
3. **It is compile-only, and pinned that way from outside its own file.** Three
   regressions consume `_compile_reference_chain` by import and assert the
   reference emits *no* forced link mode and *no* bandwidth:
   `tests/test_e95_productive_pipeline.py:144` and `:153`, and
   `tests/test_e95_interface_routing_semantics.py:327`. None of them lives in
   `tests/test_e95_reference_regression.py`, so grepping that file alone will
   not reveal the constraint. Extending the reference is a deliberate contract
   change across three files, not an incidental edit.
4. **It has never been deployed by the product.** See `TD-ACCEPTANCE-001`.

Note the naming collision, which has already caused confusion: the live
university topology is called a *"reference scenario"* in one commit message,
while every governed doc reserves *"reference topology"* for the offline
fixture. 3A4 should say which it means, every time.

## 4. Traffic — what is missing

### What already exists

The demand model is real and complete at the domain level:

- `TrafficContribution` — `source_id`, `per_unit_bps`, `units`, `concurrency`,
  with `demand_bps` as their product. Its docstring already states the semantic
  rule that matters: *summing every endpoint of a site onto a link they do not
  traverse is as wrong as ignoring the ones that do*;
- `HeadroomPolicy`, 25% engineering headroom, declared as project policy rather
  than a Cisco constant;
- `LinkPerformanceIntent.traffic` and `.failure_survival_bps`;
- `LinkPerformanceDecision.calculated_demand_bps` / `.engineered_demand_bps`;
- `CapacitySource.TRAFFIC_CALCULATION`, ranked in an explicit precedence order
  below explicit/policy/service and above topology-role and media defaults;
- the calculation itself, which takes `max(normal, survival, minimum)` rather
  than summing normal and survival — because they do not occur at once.

### The gap that makes 3A4 a stage at all

`link_performance_integration.intent_for_link` accepts `traffic=` and forwards
it. It has exactly two call sites, and **neither delivers traffic in
production**:

- `configuration_compiler.py:363` — the productive path. It supplies only the
  link, endpoint models and the bandwidth-sync flag. No `traffic=`, no
  `failure_survival_bps=`;
- `link_performance_integration.compile_topology` — passes `**intent_options`
  through, so it *could* carry traffic, but it is called only from
  `tests/test_e95_link_performance_identity.py` and never with traffic. It is
  also the wrong shape for the job: it would apply one identical traffic list to
  **every** link in the topology, which is precisely the error
  `TrafficContribution`'s own docstring warns against — a flow must be attributed
  to the links it actually traverses.

Consequently `CapacitySource.TRAFFIC_CALCULATION` is **unreachable in
production** — it can only be reached from hand-built intents in tests. This is
stated in the repository already, in commit `d2d16f6`: demand stays at zero and
every link lands on media policy *"a data gap, not a silent default"*.

`EnterprisePlan` has no traffic field at all, and no `TrafficProfile`,
`TrafficMatrix`, `FlowProfile` or `DemandProfile` type exists anywhere in the
repository.

### Traffic audit — what 3A4 does and does not require

| Question | Answer, from repository evidence |
| --- | --- |
| Typed traffic intents | **Required.** Nothing produces `TrafficContribution` in production; this is the core gap. |
| Traffic matrix / flow definitions | **Required in substance**, as whatever structure carries flows onto `EnterprisePlan`. No such type exists to reuse. |
| Source/destination semantic identities | **Required.** `TrafficContribution.source_id` exists; the endpoint identity that decides *which links a flow traverses* does not. Its docstring already names this as the correctness rule. |
| Capacity-aware traffic validation | **Available to consume.** The planner already validates demand against measured ceilings and emits `LinkPerformanceIssueCode`. 3A4 supplies the demand, not the validator. |
| Measured reachability | **Available.** `TypedPingExecutor`, with `SAFE_PING_TIMEOUT_S` justified by measurement, and `interpret_ping`. |
| Latency / loss evidence | **Partially available.** Ping statistics carry loss and round-trip min/avg/max, as the acceptance run recorded. This is per-probe evidence, not link utilisation. |
| Reference topology behavioural verification | **Required**, and blocked on §3 gap 1 until the reference can carry a serial link. |
| Failure/recovery traffic checks | **Not 3A4 scope** — see §7. |

### The hard observability ceiling

**There is no interface counter readback anywhere in `src/`.** No packet or byte
counts, no error counters, no input/output rate, no utilisation. `pt_inspect_ports`
reads port *state* — up, protocol, ip, mac, duplex, bandwidth, mtu, delay — and
no counters. `OperationalQueryId.SHOW_INTERFACE` is registered with the command
`show interfaces {interface}` but is **never dispatched by any code in `src/`**.

Separately, the OBSERVED tier of the link-performance triad is modelled but not
plumbed: `parse_ethernet_link_mode`, `parse_serial_controller` and
`ObservedLinkPerformance.from_runtime` have **no caller in `src/`** — they are
exercised only by tests.

And the backend forbids the obvious workaround: there is no `pt_send_pdu`, a
documented Packet Tracer limitation. Traffic can only be originated the way a
user would, which today means a ping.

**Claim ceiling this imposes on Stage 3A4:** without counters, 3A4 can prove
that a demand-derived capacity decision was *made*, *applied* and *read back* —
and that traffic *flows* — but it cannot prove that a link *carried* a given
volume. Any 3A4 acceptance wording must respect that boundary. Wiring
`SHOW_INTERFACE` and the OBSERVED tier is the narrow, already-scaffolded
capability that would raise this ceiling, and it is the natural first candidate
for 3A4's "missing seam" work.

## 5. Seams Stage 3A4 must use

Recovered by name from source. 3A4 builds on these rather than around them.

| Concern | Production seam |
| --- | --- |
| Physical deployment | `deploy_enterprise_topology` — documented as *"the backend-neutral production seam for physical deployment"*, emitting a manifest only after fresh exact read-back |
| Physical runtime | `packet_tracer_physical_runtime` — `ensure_device`, `ensure_link`, `observe_device`, `observe_link` |
| Deployment identity | `build_deployment_manifest`, `EnvironmentFingerprint`, `DeploymentLinkBinding` |
| Configuration | `compile_configuration` → `configuration_renderer` → `apply_configuration` |
| Link performance | `link_performance_planner`, `link_performance_integration`, `link_performance_renderer`, and the typed actions `ConfigureSerialClock` / `ConfigureInterfaceBandwidth` / `ConfigureEthernetLinkMode` |
| Control plane | `compile_control_plane` → `apply_control_plane` → `PacketTracerEnterpriseControlPlaneRuntime` |
| Authoritative readback | `ControlledIosExecutor` with registered `OperationalQueryId` values; `topology_observation.py` for link/device readback |
| Traffic probes | `TypedPingExecutor`, `stable_convergence` |
| Evidence semantics | `ApplicationExecutionJournal` — `dirty_state` final, `applied_dirty_state` historical |

`topology_observation.py` deserves specific mention: the acceptance harness
reimplemented link readback instead of calling it, and that reimplementation is
where the `getOwnerDevice()` defect lived. 3A4 must call the seam.

## 6. Debts that block Stage 3A4 **start**

```text
NONE
```

Every open entry was verified against source at CP2 and classified:

| Debt | Blocks 3A4 start | Why not |
| --- | --- | --- |
| TD-RUNTIME-006 | No | Four unreachable journal orderings; 3A4 drives the same applicators, so it cannot reach them either |
| TD-HARDWARE-001 | No | Regression-pinned: the reference fixture pins its hardware by hand and does not depend on dynamic selection |
| TD-SECURITY-001 | No | 3A4 dispatches no ACL or NAT mutation |
| TD-VOICE-001 | No | 3A4 dispatches no voice action |
| TD-PUBLIC-001 | No | Unrelated surface; 3A4 is forbidden from using the raw tool regardless |
| TD-TRANSPORT-001 | No | Containment already covers 3A4's mutation families, which are the ones 3A3 dispatched |
| TD-ACCEPTANCE-001 | No | This is 3A4's own work, not a precondition for it |

## 7. Debts with `RESOLVE_BEFORE: Stage 3A4 closure`

```text
TD-ACCEPTANCE-001
```

The reference topology must be exercised through the complete production
physical and configuration pipeline **before Stage 3A4 can close**. Deferring it
to E9.5 closure or CP3 would allow 3A4 to close on the same harness-shaped
evidence the entry exists to reject.

No other debt has its deadline moved by this checkpoint. Every other
`RESOLVE_BEFORE` stands exactly as written.

## Failure and recovery — explicitly out of scope

Recorded because the phase name is broad enough to attract it.

The machinery exists and is substantial: `LinkFailureScenarioIntent`,
`FailureScenarioExecutor`, `render_scenario`, the five-phase
`FailureTransitionPhase`, mandatory restore in `finally`, and a refusal to
inject without a stable reachable baseline.

Governed docs place it in **E9**, not 3A4:
`enterprise-control-plane.md` states E9 stops at *"deterministic planning,
guarded application, evidence separation, bounded failover execution, and
mandatory restore"*. Its live status is registered as UNKNOWN in
`docs/qa/e95-runtime-debt.md` — OSPF failover
`PENDING_ROOT_CAUSE_AND_LIVE_FAILOVER`, recovery
`PENDING_LIVE_RESTORE_AND_RECOVERY`.

3A4 should not adopt it. If a traffic-under-failure check is later wanted, that
is a contract change with its own evidence requirements.

## One governance discrepancy, recorded not resolved

The ledger defines Debt Checkpoint 2 as occurring *"After the university
topology passes its routing/**failure/recovery** acceptance scenario"*.

The acceptance that actually ran has eleven gates — workspace safety, physical
topology, link readback, addressing, local connectivity, capability, typed
application, configuration readback, route convergence, forwarding, final state
— and **no failure or recovery gate**. Its contract never proposed one.

So CP2's stated trigger was not literally satisfied: the routing half was, the
failure/recovery half was not. This does not invalidate the acceptance, which
passed against the contract written for it, and it does not block Stage 3A4,
since failure/recovery is E9 scope and already registered UNKNOWN. It is
recorded because a checkpoint definition that quietly does not match what
triggered it is exactly the kind of drift this ledger exists to prevent.
