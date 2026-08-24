# CP-SCALE current handoff

## Checkpoint identity

```text
BRANCH                    = feature/runtime-ripv2
UPSTREAM                  = personal/feature/runtime-ripv2
PRE_CHECKPOINT_HEAD       = 0846472e8e666120cc7e690563ad8f7c0ed4fe0f
PT_BUILD                  = 9.0.1.0858
STAGE                     = CANONICAL_ROUTING_CORE_GOVERNED_VERIFIED
LIVE_GATE                 = ROUTER4_TO_SWITCH10
CP_SCALE                  = OPEN
E10                       = BLOCKED_BY_CP_SCALE
CANONICAL_CORE_MUTATED    = VERIFIED_THEN_CLEANED
```

Use only `./.venv/Scripts/python.exe` from this worktree. Before any live
Packet Tracer mutation, the executing process must prove the checkout-local
interpreter, `packet_tracer_mcp.__file__` inside this worktree, exactly one of
the production/test import namespaces, exact PT build `9.0.1.0858`, and a
read-only workspace classification. Never mutate manual/user topology.

## Authority and canonical design

The governed authority boundary is now resolved:

- `docs/reference/cp-scale/diseno_logico_IMP.md`
- `docs/reference/cp-scale/topologia_completa_IMP.md`

Those documents define **what** the CP-SCALE topology is. Current typed source
and tests define **how** it is represented and compiled. Fresh Packet Tracer
evidence defines what the exact backend/model/build supports. Historical code
snippets in the references are not implementation authority.

The historical `318 devices / 235 links` capacity topology remains a regression
fixture only. It is not the canonical physical target and its historical VLAN
policy remains isolated from the canonical scenario.

The current canonical typed pipeline is:

```text
EnterpriseIntent
  -> EnterprisePlan / explicit IPAM
  -> reference-governed HardwarePlan
  -> TopologyPlan
  -> ConfigurationPlan
  -> ControlPlanePlan

TOPOLOGY DEVICES          = 314
TOPOLOGY LINKS            = 219
NETWORK DEVICES           = 18
ENDPOINT/AP DEVICES       = 296
WORKLOAD ENDPOINTS        = 279
ACCESS POINTS             = 17
INFRASTRUCTURE LINKS      = 18
SWITCH-DIRECT LINKS       = 199
PHONE-PC PASSTHROUGH      = 2
WIRELESS PLACEMENTS       = 95 visual/ownership only
WIRELESS LINKPLAN         = 0
TOPOLOGY SEMANTIC HASH    = 73b55f22bc4670498737025887720c08974ff4af7a429df09914f808f6fb1767
```

Network hardware is exactly `3x 2811`, `10x 2960-24TT`, `3x 3650-24PS`, and
`2x 3560-24PS`. Semantic name, PT name, and governed IOS hostname are the
documented names (`Router0`, `Router3`, `Router4`, `Switch0..10`, `MLS3..7`)
where applicable. Every 2811 has one typed `NM-4A/S` in slot `1`; the canonical
serial ports are `Serial1/0..Serial1/3`.

Exact endpoint models are preserved. In particular:

```text
WEBCAM              -> Webcam
SMOKE_DETECTOR      -> Smoke Detector
MOTION_DETECTOR     -> Motion Detector
HUMITURE_MONITOR    -> Humiture Monitor
TEMPERATURE_MONITOR -> Temperature Monitor
```

There is no silent generic `Thing` substitution.

## Exact model/port qualification and containment

Fresh PT `9.0.1.0858` qualification now records the exact inventories required
by the canonical compiler:

```text
2811 bare           = FastEthernet0/0, FastEthernet0/1, Vlan1
2811 + NM-4A/S@1    = bare ports + Serial1/0..Serial1/3
2960-24TT           = FastEthernet0/1..24, GigabitEthernet0/1..2, Vlan1
3650-24PS           = GigabitEthernet1/0/1..24, GigabitEthernet1/1/1..4, Vlan1
3560-24PS           = previously exact-build qualified inventory/PoE/VLAN/trunk evidence
Laptop-PT           = Bluetooth, FastEthernet0
```

The reference hardware planner refuses the canonical design unless every
required port/module has exact-build evidence. The physical compiler now takes
typed semantic names and exact endpoint-port bindings; it validates both sides
and never silently falls back to the old capacity allocator.

Qualifier containment bugs were proved fail-first and fixed:

- disposable mutation requires a safe read-only baseline classification;
- incomplete or links-only baselines cannot authorize mutation;
- ambiguous or raised creation attempts clean up only the exact reserved name;
- cleanup is never attempted before a post-gate creation attempt;
- cleanup `NO_OP` is accepted when fresh readback already proves absence;
- manual/user topology remains outside the disposable ownership boundary.

All disposable exact-model/port probes were removed. The canonical core was
subsequently materialized only inside the governed ownership boundary,
verified, and restored to the exact empty baseline.

## Canonical configuration result

```text
CONFIGURATION ACTIONS      = 609
CONFIGURATION ERRORS       = 0
CONFIGURATION WARNINGS     = 7 evidence ceilings
CONFIGURATION HASH         = 0ed0dd39f9beac78c9ece9e32c0c3389508762e5cd186f55db8d98669108d586

configure_hostname         = 18
create_vlan                = 45
configure_access_port      = 199
configure_trunk            = 27
configure_subinterface     = 9
configure_dhcp_pool        = 9
configure_routed_interface = 6
set_endpoint_dhcp          = 271
set_endpoint_static        = 25
```

Each site has only the explicit governed VLANs:

```text
VLAN 10 DATA
VLAN 20 VOICE
VLAN 30 IOT / printers / access points
```

Every trunk allows exactly `[10,20,30]`; VLAN 1 is excluded from the allowed
set. No native/parking VLAN policy is claimed beyond the typed plan. Every
phone-facing switch port uses access/data VLAN 10 plus voice VLAN 20. PortFast
and BPDU Guard compile only for the 199 proven endpoint-facing switch ports,
never for router or switch infrastructure links; exact live edge-policy
readback remains a later capability gate.

Router-on-a-stick is explicit on `FastEthernet0/0` for all three routers:

```text
Router4 = 172.16.10.1/24, 172.16.20.1/24, 172.16.30.1/24
Router3 = 172.17.10.1/24, 172.17.20.1/24, 172.17.30.1/24
Router0 = 172.18.10.1/24, 172.18.20.1/24, 172.18.30.1/24
```

The three intentional transit networks are:

```text
Router4 Serial1/0 <-> Router0 Serial1/0 = 10.0.0.1/30 <-> 10.0.0.2/30
Router4 Serial1/1 <-> Router3 Serial1/1 = 10.0.0.5/30 <-> 10.0.0.6/30
Router3 Serial1/0 <-> Router0 Serial1/1 = 10.0.0.9/30 <-> 10.0.0.10/30
```

Serial DCE orientation must be observed after link creation; clocking may be
applied only to the freshly observed DCE side.

## STP governed state

The canonical plan deliberately uses ordinary PVST as the strongest governed
fallback. Root ownership is explicit and numeric:

```text
large-branch      primary Switch8 / secondary Switch10 / 24576 / 28672
multilayer-branch primary MLS3    / secondary MLS7      / 24576 / 28672
small-branch      primary Switch3 / no secondary        / 24576
```

The compiler preserves primary, secondary, and numeric priorities in typed
verification expectations. Runtime verification understands PVST protocol
`ieee`, Rapid-PVST protocol `rstp`, and compares the parser-backed bridge base
priority rather than the VLAN-extended priority. This unit/runtime path is not
itself model-attributed live capability evidence.

Rapid-PVST remains **UNOBSERVABLE** on the exact build. Its typed mutation was
accepted on a disposable 3560, but four fresh registered `show spanning-tree`
reads produced no parser-backed instance. No Rapid-PVST capability was promoted.
Cleanup restored the owned disposable baseline.

## RIPv2 current state

The canonical control-plane plan compiles `217` actions, `57` verification
expectations, and exactly three typed `ConfigureRipv2` actions for Router4,
Router0, and Router3. Each router advertises its connected `10.0.0.0` classful
transit foundation plus its site `172.16/17/18.0.0` foundation; all three LAN
subinterfaces are passive and the serial interfaces remain active.

RIPv2 is the current governed IGP and introduces no E10 features. Exact-model
`2811` layer3 plus RIPv2 configuration/process/route/behavior are now
SUPPORTED for exact build `9.0.1.0858` by the R5 canonical-core qualification.
The final repeat passed both governed applicators and fresh forwarding. RIP has
no adjacency-state table in this contract; do not invent or claim one.

```text
CONTROL-PLANE HASH        = 29be238e89d68e8d4aeb2eb6f72fe846ed9b1b2f83c888c2bb51812d591b41ba
RIPV2 LIVE ON 2811        = GOVERNED VERIFIED
RIPV2 ADJACENCY CLAIM     = N/A
```

## Checkpoint validation and live boundary

```text
AFFECTED REGRESSION       = PASS
BOUNDED AFFECTED SUITE    = PASS
COMPILEALL src            = PASS
GIT DIFF CHECK            = PASS
GRAPHIFY UPDATE           = PASS
FULL SUITE                = 2609 passed, 5 warnings
CANONICAL CORE LIVE       = GOVERNED VERIFIED; CLEANUP VERIFIED
```

The affected historical-fixture regression remains valid without weakening
canonical semantics: canonical printers/APs stay on VLAN 30, while the explicit
318/235 regression fixture retains its old five-segment capacity policy.

The canonical core was materialized, qualified, repeated through governed E5
and E9, and removed with two baseline-restoration observations. The next live
stage starts from that clean baseline, rematerializes the verified core, then
adds the exact Router4-to-Switch10 branch through typed/product paths.

```text
NEXT_ACTIVE_STEP = rematerialize verified core, then Router4 -> Switch10
```
