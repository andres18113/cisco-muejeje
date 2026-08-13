# Handoff — Stage 3A4

## Repository

- worktree: `.claude/worktrees/runtime-ripv2` — **`main` does not contain
  E9.5**; the branches diverged and a worktree off `main` has no
  `docs/architecture/` at all.
- branch: `feature/runtime-ripv2`; HEAD: see `git log -1`; status: clean
- tests: **1751 passing**

**Import contract.** Tests import `src.packet_tracer_mcp`, never the bare name.
Run `python -m pytest` from the worktree root, no custom `PYTHONPATH`
(`pyproject.toml` sets `pythonpath = ["."]`). Both names resolve to this
worktree's source, but they are **distinct module objects**, so `isinstance`
across them is always false and an assertion written that way passes without
checking anything; `test_no_test_imports_the_package_outside_the_repo_namespace`
guards it. The editable `.pth` is pinned to this worktree, so any *other*
worktree sharing the virtualenv resolves a bare import to *this* source.

## Position

Stage 3A3 **CLOSED** (do not reopen; 3A4 consumes it) · CP1, CP2 **CLOSED** ·
Stage 3A4 **PARTIAL** · E9.5 **OPEN**. Do not start CP3.

## Completed in Stage 3A4

`application/use_cases/foundational_evidence.py` + 35 tests, commit `d52bc60`.

Derives control-plane foundational evidence from executed results only, with no
parameter through which a status can be supplied — so the harness's fabricated
`{req.source_id: VERIFIED}` has no door to enter through. VERIFIED is copied,
never minted: configuration foundations read `verification_results` (never
`action_results`, whose ceiling is APPLIED); link foundations reach VERIFIED
only via `OBSERVED` with the `observed` flag set; conflicts resolve to the
weaker; no evidence yields `{}` so the gate refuses. `unmet_foundations`
previews the gate, pinned against the real `_foundation_errors` so it cannot
drift.

## Blocking gates

```text
FOUNDATIONAL_EVIDENCE_DERIVATION      = READY (offline; strongest obtained)
FOUNDATIONAL_INTEGRATION              = NOT ESTABLISHED live
SERIAL_REFERENCE_TOPOLOGY             = BLOCKED
REFERENCE_TOPOLOGY_PRODUCT_PLANNING   = BLOCKED
REFERENCE_TOPOLOGY_PRODUCT_DEPLOYMENT = NOT REACHED
REFERENCE_TOPOLOGY_PRODUCT_CONFIG     = NOT REACHED
TRAFFIC_PRODUCTION_INTEGRATION        = BLOCKED
TRAFFIC_BEHAVIORAL_VERIFICATION       = NOT REACHED
TD_ACCEPTANCE_001                     = OPEN
E9_5                                  = OPEN
STAGE_3A4                             = PARTIAL
```

## TD-ACCEPTANCE-001 — six rows

| Row | Requirement | State | Evidence | Remaining |
| --- | --- | --- | --- | --- |
| 1 | Production physical deployment | Wired, unreached | `pt_live_deploy` → `EnterprisePhysicalTopologyDeployer`; manifest only from verified read-back | Needs a plan to feed it (row 2) |
| 2 | Serial topology support | **BLOCKED** | `CABLE_RULES` yields no `"serial"`; deployer refuses any plan with modules | Dependency map below |
| 3 | Production config + addressing | Mostly present | Host addressing already typed: `SetEndpointStaticAddress` → 7-arg `configurePcIp`; router L3 and `clock rate` supported | One gap: compiler path emitting `ConfigureSvi` for a **non-gateway** switch (type + renderer exist) |
| 4 | Authentic foundational evidence | **Implemented, not exercised** | `foundational_evidence.py`; drift check vs real gate | Run against a real deployment + configuration result |
| 5 | Typed control plane | **Already correct — no work** | The University run used the real typed RIPv2 path end to end (compile → apply → fresh readback → `ROUTE_PRESENT`) | Re-exercise in the closing run; do not rebuild |
| 6 | Authoritative readback | Present, must be used | `topology_observation.py` provides link readback | Call it; do not reimplement — that is where the harness's `getOwnerDevice()` bug lived |

## Serial critical path

Dependency order, not nine mandatory tickets:

```text
cable/media ─┐
router↔router planning ─┼→ SERIAL port class → media-aware config compiler
ModulePlanner reachable ─┘                          ↑
module effect observation → deploy modular plan ────┤
manifest link_bindings → serial-clock capability ───┘
parser → SerialEndpointOrientation ─────────────────┘
```

- **cable/media** — `CABLE_RULES` is category-only (`router,router`→`cross`);
  cannot express "serial WAN" without link-role or requirement input.
- **router↔router** — no planner emits such a `HardwareLinkRequirement`;
  `DeviceRole.WAN_ROUTER` never instantiated; `LinkRole.WAN_LINK` never emitted.
- **ModulePlanner** — `plan_serial` is correct with **zero production callers**;
  `module_plan` never populated; `available_slots` has no source.
- **port class** — module ports are `[MODULE_PROVIDED, WAN]`, never
  `PortClass.SERIAL`, so `required_port_class=SERIAL` cannot select a serial.
- **link_bindings** — `build_deployment_manifest` never populates them, so
  `resolve_serial_clock_target` is unreachable in production.
- **compiler** — the `unprofiled` gate is Ethernet-shaped and `continue`s every
  serial link *before* `decide()`, so no `ConfigureSerialClock` is emitted.
- **capability / orientation** — `PT_2911_HWIC2T_SERIAL_CLOCK` has no resolver
  or consumer; `parse_serial_controller` returns a bare `"dce"`/`"dte"` string
  that nothing maps to `SerialEndpointOrientation`.

**Reusable Stage 3A3 assets — do NOT reimplement:**
`PT_CONNECT_TYPE["serial"]=8106` already flows through `generate_link_command`;
`resolve_link_media` accepts `"serial"`; `_plan_serial` is complete (rates,
fallback, DCE-only clock); `ConfigureSerialClock` / `ConfigureInterfaceBandwidth`
+ `render_link_performance` exist and are whitelisted;
`DeploymentLinkBinding.resolve_serial_clock_target` exists;
`SHOW_CONTROLLERS_SERIAL` + `parse_serial_controller` are qualified;
`build_exact_link_readback_js` is media-agnostic; `LINK_DCE_KEY` is already in
the physical hash.

## Traffic

`intent_for_link` already accepts `traffic=`; the one productive caller
(`configuration_compiler`) never passes it, so `CapacitySource.TRAFFIC_CALCULATION`
is unreachable outside tests. `EnterprisePlan` carries no bps field anywhere,
and no path computation returns edge sets — only reachability booleans and a
first-hop name — so flow-to-link attribution needs new code or must be bounded
by `ConcreteLinkRole` plus site/zone ids.

- **serial** — demand selects the rate, sets `TRAFFIC_CALCULATION` and
  `serial_clock_rate_bps`, changing the emitted action and the configuration
  semantic hash. The only hash-visible traffic effect.
- **ethernet** — demand never selects capacity, speed or duplex; AUTO stays
  AUTO. But `_check_demand` compares demand against the measured ceiling, and
  `LINK_CAPACITY_INSUFFICIENT` makes the decision inapplicable and suppresses
  every action for that link. **Do not call Ethernet demand irrelevant.**
- inert only where Stage 3A3 measured no profile (both ceilings `None`).

## Evidence ceilings — preserve

- **Module identity is UNOBSERVABLE** on PT 9.0.1.0858: the name getter returns
  the literal `"None"` for a module exposing ports. Never infer requested
  HWIC-2T → observed HWIC-2T. Intended direction is **effect verification**
  (expected slot occupancy, expected resulting ports, observable port count).
  **Do not weaken the physical-manifest gate merely to deploy** — it refuses
  today precisely to avoid a false manifest.
- **No interface counters exist.** `SHOW_INTERFACE` is registered but never
  dispatched; `ObservedLinkPerformance.from_runtime` has no production caller.
  3A4 may prove a decision was made, applied and read back — never that a link
  *carried* a volume.
- **`endpoint_address`, `access_port`, `dhcp_pool` foundations can never reach
  VERIFIED** (endpoint readback returns `gateway`/`dns` null → PARTIAL; the
  others are unconditionally unobservable). A closing run must compile only
  `l3_interface` and `link` foundations — a RIPv2 topology does.
- **Failure/recovery is not in Stage 3A4** — E9 scope, still UNKNOWN in
  `docs/qa/e95-runtime-debt.md`. Do not mark it satisfied.

## Orchestration

Physical is wired (`pt_live_deploy`). The **E5/E9 composition seam does not
exist**: `grep -rE "[A-Za-z]+Applicator\(" src/` returns nothing, so no
enterprise applicator is constructed in production. The `pt_apply_*` tools are
legacy CLI-generator paths through `configureIosDevice` — **not** a precedent;
copying them reproduces the harness rather than replacing it.

## Next — first Codex slice

Starting plan, not immutable architecture. Smallest productive serial slice
before any traffic work:

1. Make the product **express** one serial link — cable/media, router↔router
   requirement, `PortClass.SERIAL`, `plan_serial` reachable. Offline, no PT.
2. Make the product **deploy** it — module effect observation + `ensure_module`,
   without weakening the manifest gate.
3. Make the product **configure** it — media-aware compiler gate, manifest
   `link_bindings`, serial-clock capability, orientation mapping.
4. Only then first live qualification: **2× 2911 + required modules + one serial
   WAN**, through the product path, disposable `MCP-PROBE-*`, exact cleanup.
   **Not** the 41-device reference topology.
5. Traffic last — it needs serial to produce any hash-visible effect.

## Standing constraint

The user's real university Packet Tracer file is graded coursework. Never
mutate, delete, or probe it. Before any mutation run a read-only workspace
inventory and HARD STOP if any foreign device is present. Live work runs only
against an empty workspace, creates only `MCP-PROBE-*` devices, and deletes
exactly those by name.
