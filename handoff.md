# CP-SCALE current handoff

## Git and governed state

```text
BRANCH                     = feature/runtime-ripv2
UPSTREAM                   = personal/feature/runtime-ripv2
SESSION_BASE               = e72b1280fa3c56225ffca7fae311084813ec846b
PRE_HANDOFF_HEAD           = 9c62096b8431eaf610d03d85a9c9dc94ea097a09
PT_BUILD                   = 9.0.1.0858
CP_SCALE                   = OPEN
E10                        = BLOCKED_BY_CP_SCALE
PT_MCP_RELIABLE_ENVELOPE   = 0 qualified live points
```

Current commits after the session base, before the containing checkpoint commit:

```text
a1828b7 feat(capabilities): qualify typed PoE hardware evidence
ad66e5e feat(runtime): qualify CP-SCALE port inventories
3e3e32c fix(runtime): preserve physical port alias identity
466b362 fix(runtime): observe Packet Tracer antenna links
838d5b9 feat(capabilities): qualify Stage A runtime gates
3ce7b09 fix(topology): map CP-SCALE IoT roles exactly
fbaaa63 fix(runtime): confine disposable device cleanup
9c62096 test(governance): stabilize refreshed runtime baseline
```

Use only `./.venv/Scripts/python.exe` from this worktree. Before every live
mutation, the executing process must prove the checkout-local interpreter,
`packet_tracer_mcp.__file__` inside this worktree, and exactly one import
namespace.

## Current corrected topology and PoE result

Exact canonical endpoint-role mappings now used by CP-SCALE:

```text
WEBCAM              -> Webcam
SMOKE_DETECTOR      -> Smoke Detector
MOTION_DETECTOR     -> Motion Detector
HUMITURE_MONITOR    -> Humiture Monitor
TEMPERATURE_MONITOR -> Temperature Monitor
```

All five exact identifiers were created and read back by model/name through the
typed physical runtime on PT `9.0.1.0858`; cleanup restored the semantic
workspace twice. Generic `Thing` is no longer the canonical substitute for
these roles. Smoke detectors are wireless (`Bluetooth`, `Wireless0`) and add no
PoE demand.

Corrected Stage A composition:

```text
DEVICES                    = 73
LINKS                      = 55
WORKLOAD_ENDPOINTS         = 65
ACCESS_POINTS              = 3
POE_REQUIRED               = YES
POE_REQUIREMENT_SOURCE     = 21 phones + 3 access points
POE_BASE_DEMAND            = 24 ports
POE_HEADROOM_20_PERCENT    = 5 ports
POE_DEMAND                 = 29 ports
HARDWARE_BEFORE            = provisional 2950T-24; PoE UNKNOWN; inadmissible
HARDWARE_AFTER             = two 3560-24PS access switches; 48 measured PoE ports
PROVISIONAL_SWITCHES_AFTER = 0
IMPLEMENTATION_PATH        = A
```

Path A is correct because an existing eligible model has exact-build typed
evidence; the defects were evidence consumption/eligibility and the endpoint
identity substitution, not a false phone/AP demand and not a need for a new PoE
subsystem. UNKNOWN remains fail-closed and there is no model-name promotion.

## Exact-build capability evidence

Current reusable evidence for PT `9.0.1.0858` includes:

- `3560-24PS`: model existence, 27-port inventory, 24 access ports with complete
  administrative/runtime power-on state, PoE capability `SUPPORTED` with
  observed value 24, VLAN creation/readback, and trunk configuration/readback.
- `819HG-4G-IOX`: model existence, 10-port inventory, typed L3 interface
  configuration/readback, and controlled DHCP-server behavior.
- Exact Stage A port inventories and physical alias normalization; an 819 alias
  no longer produces duplicate physical-link identity.
- Antenna links are observed through the typed physical topology runtime.
- The five IoT models listed above are exact model/build observations.

All qualification sessions restored owned objects and independently re-observed
their baselines. Evidence is exact-model and exact-build scoped.

## Router-on-a-stick and distribution correction

Current intent is router-on-a-stick, not a routed L3 distribution-edge transit.
The prior collapsed-core topology generated two distribution-to-one-router
links while configuration governed only one, leaving the other at IOS/VLAN 1
defaults. Current source now:

- creates one deterministic distribution-to-edge-router link per collapsed-core
  site;
- creates a distribution-peer `redundant_link` trunk for the second
  distribution switch;
- preserves access-switch uplinks to both distinct distribution switches as
  ordinary STP redundancy, never as one cross-device EtherChannel;
- allocates the highest-speed compatible physical port first, so the 819
  router-on-a-stick link uses `GigabitEthernet0`, not FastEthernet aliases;
- requires typed trunk actions for governed switch-facing infrastructure links;
- carries the explicit site VLAN set and excludes VLAN 1 from allowed VLANs;
- emits all 819 router subinterfaces on the one selected Gigabit trunk.

The current profile defines VLANs `10,20,30,40,99`. It defines no native or
parking VLAN, so no VLAN 999 or unused-port shutdown policy was invented.
Existing endpoint topology logic continues to apply PortFast/BPDU Guard only to
proven endpoint-facing access ports and keeps phone data/voice VLAN duties
separate. No HSRP is present in CP-SCALE.

## Typed IOS hostname identity

The canonical configuration architecture now has an identity phase and typed
`ConfigureHostname` action. The compiler emits it for routers/switches only when
the semantic name is already an exact safe IOS identifier; it warns and emits
nothing rather than silently changing an invalid name. Rendering, runtime
routing, replay classification, and verification are typed.

Live disposable `3560-24PS` evidence on PT `9.0.1.0858` verified:

```text
CONFIGURE_HOSTNAME mutation = accepted
CONFIGURE_VLAN_10 mutation  = accepted
HOSTNAME readback           = VERIFIED / packet_tracer_device_hostname_getter
VLAN readback               = VERIFIED / vlan_manager_object_state
```

`getPrompt()` is empty for this model/build, so the verifier now prefers the
existing structured `getHostName()` device getter. Terminal prompt/output
identity remains a fail-closed fallback. Exact mismatch fails.

## STP current state

The existing `ControlPlanePlan` already represents STP mode and explicit
per-VLAN primary/secondary ownership with priorities `24576/28672`. CP-SCALE
currently requests PVST and deterministically places all site VLAN roots on the
first distribution with the second as secondary; placement is plan-derived,
not MAC-order-derived. Redundant access uplinks remain an STP topology.

Rapid-PVST is NOT yet qualified or promoted for `3560-24PS`:

```text
RAPID_PVST typed mutation       = ACCEPTED in the completed disposable run
VLAN 10 / priority 24576        = applied through typed control-plane action
fresh show spanning-tree parse  = UNOBSERVABLE / no parser-backed instance
3560 Rapid capability profile  = ABSENT
CP-SCALE requested STP mode     = PVST / unchanged
```

After that result, the shared control-plane runtime gained a bounded STP
observation window: it reissues only the registered read query, never the
configuration mutation, and preserves UNOBSERVABLE if no parser-backed instance
appears. The fail-first regression now passes. The live rerun of this current
code was deliberately interrupted before completion and MUST NOT be treated as
qualification evidence.

At checkpoint recovery, no qualification Python process was running. A fresh
governed typed workspace observation showed zero semantic devices and zero
links, with four backend-managed Power Distribution Devices preserved. No
cleanup mutation was required.

## Validation and evidence boundaries

```text
FULL_PYTEST_CURRENT                = 2554 passed, 4 warnings
CURRENT_AFFECTED_REGRESSION        = 188 passed
COMPILEALL_SRC                     = PASS
GIT_DIFF_CHECK                     = PASS
GRAPHIFY_UPDATE                    = 9187 nodes / 30853 edges / 289 communities
LAST_CORRECTED_OFFLINE_COMPOSE     = 318 devices / 235 links /
                                     637 configuration actions /
                                     164 control-plane actions /
                                     159 voice actions /
                                     zero hard layout violations /
                                     zero generic substitutions
```

The ignored canonical `data/cp-scale/offline-full/` artifacts were regenerated
from current source and the exact-build capability store. `summary.json` is
valid, has zero substitutions, and records physical/configuration/control-plane/
voice hashes `0b44a90a... / d0c7c79b... / 1b21d1bb... / 2978a2d1...`.

The stale pre-correction Stage A run is not qualification evidence: it used
generic IoT models and the old duplicate router links/ports. It stopped during
configuration with 57 verified, 3 unobservable, 2 partial, 71 failed; control
plane and voice did not run. Do not infer the corrected result from it.

## 2026-08-22 bounded continuation result

The fixed-code Stage-A network qualification ran against PT `9.0.1.0858` with
the checkout-local interpreter, one production namespace, a fresh heartbeat,
and an empty semantic workspace. Hostname and VLAN 10 were VERIFIED. The typed
Rapid-PVST mutation was APPLIED, but four fresh registered STP reads returned
no parser-backed instance, so mode/VLAN/root stayed UNOBSERVABLE. Cleanup was
attempted only after the post-gate creation attempt and two final inventories
both matched baseline. Promote no Rapid-PVST dimension; CP-SCALE remains PVST
intent with deterministic `24576/28672` ownership, not a live PVST readback
claim.

A fail-first review exposed that the ignored session script previously called
cleanup even when a pre-mutation gate failed. The local runner now gates cleanup
on a post-gate creation attempt. More importantly, tracked production runtime
commit `fbaaa63` refuses `remove_device()` for a device this runtime never
attempted, while preserving cleanup after an ambiguous attempted creation.

The full suite first exposed a stale hostname taxonomy count and a wall-clock
TTL race in the bridge capacity test. Both were corrected; the final governed
run is `2554 passed, 4 warnings`, and `compileall src` passes. Graphify was
refreshed to `9187 nodes / 30853 edges / 289 communities`.

## Mechanically established topology governance hard stop

Do not start Checkpoint 1 until one topology is made authoritative in current
typed source/tests. The two candidates cannot be silently combined:

```text
CURRENT PRODUCT AUTHORITY (cp_scale.py + normal compiler)
  318 devices / 235 links / 22 network devices
  3x 1941 + 19x 3560-24PS
  deterministic generated semantic names

HISTORICAL NAMED PHYSICAL REFERENCE (mission checkpoints)
  Router4/Router0/Router3 = 3x 2811
  Switch10/floor/Router3 access = 2960-24TT
  Router0 branch includes 3650-24PS
  314 devices / 219 derived cabled links / 18 network devices
```

`docs/architecture/cp-scale-qualification.md` explicitly makes the former
product authority and the historical documents immutable workload inputs. The
current CP-SCALE points also have no governed three-router-core-only slice:
points A-C are only the large branch and Router0/Router3 first appear at D.

The historical shape cannot pass the current product preflight anyway:

- `2811`, `2960-24TT`, `3650-24PS`, and `Laptop-PT` have no exact-build measured
  port inventory; deployment fails `PORT_EVIDENCE_UNAVAILABLE` before mutation.
- `2811` has no model-attributed control-plane profile. Canonical RIPv2 therefore
  stays UNKNOWN for configuration/process/routes/behavior on the required core.
- `2960-24TT` has all STP dimensions UNKNOWN; the unobservable 3560 Rapid result
  cannot authorize another model.
- Several historical endpoint-to-switch port assignments are explicitly left
  unresolved, so exact links cannot be guessed.

The last live observation after qualification is zero semantic devices and zero
links, with one backend-managed Power Distribution Device preserved. No core or
presentation topology was mutated.

```text
NEXT_ACTIVE_STEP = Obtain a governed topology-identity decision in source/tests:
                   either execute the current 318/235 product plan, which does
                   not satisfy the named Router4/2811 checkpoints, or promote
                   the historical 314/219 design into typed product authority
                   and qualify every missing exact model/build/port/control-
                   plane dimension first. Never merge the two shapes or borrow
                   evidence across models.
CP_SCALE         = OPEN / HARD_STOP_TOPOLOGY_IDENTITY_AND_MODEL_EVIDENCE
E10              = BLOCKED_BY_CP_SCALE
```
