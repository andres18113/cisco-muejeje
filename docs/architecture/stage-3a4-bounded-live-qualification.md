# Stage 3A4 — MEG-4 bounded live qualification

Two runs so far, both on `feature/runtime-ripv2`, worktree
`.claude/worktrees/runtime-ripv2`. **Run 1 is below; run 2 is at the end of
this document and is the current state.** Run 1's outcome block is left
exactly as it was recorded — it is history, not a summary of where things
stand.

## Run 1 — 2026-08-17

### Outcome, stated first

```text
MEG_4_STATUS                  = FAILED / CLEAN
STOPPED_AT                    = physical_deployment
LIVE_PACKET_TRACER_RUN        = YES  (first product-path live run of this stage)
WORKSPACE_RESTORED            = YES  (verified by independent re-observation)
E4_IDENTITY_PRESERVED         = YES
RAW_IOS_OR_JS_USED            = NONE
HARNESS_PERFORMED_A_MUTATION  = NO
```

The run mutated Packet Tracer, deployed eight product-generated devices, hit a
real defect at module verification, refused to emit a manifest, cleaned up, and
restored the workspace. **It did not complete, and nothing here upgrades any
acceptance line.**

## Gates, in order

### G2 — same-process import isolation

```text
state              = ISOLATED
sys.executable     = <worktree>/.venv/Scripts/python.exe
loaded identities  = ['packet_tracer_mcp']          # exactly one
packet_tracer_mcp.__file__ = <worktree>/src/packet_tracer_mcp/__init__.py
```

Run twice — once in the read-only probe, once inside the mutating process
itself, before the first mutation. `PT_MCP_GOVERNED_ROOT` was set for the run
process only and not persisted.

### G3 — read-only inventory, build, classification

```text
inventory       = observed=True, semantic_devices=0, links=0, backend_managed=0
                  message="fresh_complete_workspace_inventory"
classification  = DISPOSABLE
packet_tracer   = 9.0.1.0858
```

**How the build was confirmed, and why not through PT.** The first attempt read
`pt.system.version` through the bridge and got
`PT_ERROR: ReferenceError: pt is not defined`. That was a guessed API and
`AGENTS.md` rule 6 forbids exactly that. There is no confirmed PT API in this
repository for reading the version — every existing path takes it from the
caller. The build was therefore confirmed at OS level from the running GUI
process:

```text
PID 41784 -> C:\Program Files\Cisco Packet Tracer 9.0.1\bin\PacketTracer.exe
FileVersion / ProductVersion = 9.0.1.0858
MainWindowHandle = 1968802   (non-zero: the GUI instance, not the helper)
```

That is authoritative for *which build is running* and involves no API guess.
Recorded as a limitation: it identifies the process, not the bridge peer.

## The run

Semantic request → the single product execution entry point
(`execute_enterprise_reference`). The harness built the intent, constructed the
four production runtimes, called the entry point once, and recorded the result.
It sequenced nothing.

Planned shape, composed by the product from the intent:

```text
devices  = 8    (2x 2911 edge routers, 2 access switches, 4 PCs)
links    = 7    (2 edge links, 4 endpoint access links, 1 serial WAN)
routers  = 2911 (steered via HardwarePlanningPolicy.preferred_router_model)
serial   = link/wan_link/23682ae56217
physical_topology_hash = 5bb34605303299c4de1d24fe5a1a77af80f2c87078fc6af4a2ba1a65262e03dd
```

Deployment reached: **8 devices applied, 10 journal entries changed, 2 failed.**

## The defect this run found

Both routers failed module verification with `did not converge`, and the
deployment correctly refused to emit a manifest. But the module **did land**:

```text
ports_before            = [Gi0/0, Gi0/1, Gi0/2, Vlan1]
ports_after             = [Gi0/0, Gi0/1, Gi0/2, Serial0/0/0, Serial0/0/1, Vlan1]
added_ports             = [Serial0/0/0, Serial0/0/1]
observed_expected_ports = [Serial0/0/0, Serial0/0/1]
effect_observed         = True
slot_effect_observed    = False      <-- the refusal
```

Root cause, from the captured evidence rather than inference:

```text
requested_slot                      = "0/0"     (port-namespace, from the catalogue)
slot_observations                   = exactly one entry:
    observed_module_number = "0"    (module-tree namespace)
    slot_type_code         = "18"
    port_count             = 3      (the three onboard Gigabit ports)
```

`packet_tracer_physical_runtime.py:596` computes
`slot_effect_observed` as `effect_observed and after.module_tree_observed and
any(item.observed_module_number == module.slot ...)`. That compares a
**module-tree number** against a **port-namespace slot**. They are different
namespaces, and Slice 2A's own record already said so:

> *"The requested insertion slot `0/0` and observed module number `0` are kept
> as [distinct]"* — `stage-3a4-serial-product-slice-2a.md:69`

So the comparison can never be satisfied on 2911. Worse, the inserted HWIC-2T
does not appear in the module tree at all — the single reported slot is the
onboard module with three Gigabit ports. Matching `"0"` would therefore claim
the HWIC landed in the onboard slot, which is false.

**Why no test caught it.** `tests/test_e95_serial_physical_product_slice.py`
sets `slot_effect_observed=True` directly in its fake, so no regression ever
exercised the real derivation. The gate shipped in Slice 2A's own commit
`e846175`; this is not a later regression.

**Not worked around.** The obvious way to make this run succeed is to relax the
gate to accept port evidence alone. That would be manufacturing a pass, and the
master forbids it. The gate keeps refusing; the narrow missing capability is
named and opened as governed debt (`TD-MODULE-SLOT-001`).

## Module replay qualification — the required decision

```text
CAN_PACKET_TRACER_AUTHENTICALLY_QUALIFY_MODULE_REPLAY_CONTAINMENT = NO
```

Each module was inserted once and no replay condition arose. Provoking one would
require a transport-level resend, and manufacturing that is explicitly
forbidden. The backend exposed no path to a genuine replay during this bounded
run, so the ceiling stands unchanged:

```text
MODULE_REPLAY_GUARD = MEASURED_IN_NODE / PACKET_TRACER_NOT_YET_QUALIFIED
                    + BACKEND_LIMITATION for provoking replay in a bounded run
                    + payload-local containment (receipt + exact slot pre-read)
```

**No claim of global exactly-once delivery is made or implied.**

## G4 — cleanup and restoration

```text
cleanup entries    = 8, all disposition=changed, applied=True
removal order      = reverse of deployment
inventory_restored = True   (physical_workspace_restoration_matches)
```

Independent post-run re-observation, in a separate process:

```text
semantic_device_count = 0
link_count            = 0
backend_managed       = 1  ("Power Distribution Device0", zero ports)
classification        = disposable
```

The Power Distribution Device is backend-created and is exactly the zero-port
object `disposable_workspace_error` permits; it was absent at baseline and
present after, which the restoration comparison tolerates. Recorded rather than
smoothed over.

**Only product-managed devices were removed.** Cleanup targeted exactly the
eight names the product planned, in reverse order.

## Exit matrix

| # | Item | Result |
| --- | --- | --- |
| 1 | exact-version capability consumption attempted by the normal path | **YES** — bound to 9.0.1.0858; no special probe added |
| 2 | product-generated `TopologyPlan` | **PASS** — 8 devices / 7 links from a semantic intent |
| 3 | module effect containment | **PARTIAL** — port effect verified; slot placement unobservable |
| 4 | fresh two-ended serial orientation | **NOT REACHED** |
| 5 | exactly one DCE and one DTE | **NOT REACHED** |
| 6 | typed E5 serial transit addressing | **NOT REACHED** |
| 7 | clock on the observed DCE only | **NOT REACHED** |
| 8 | independent clock readback | **NOT REACHED** |
| 9 | authentic foundational evidence | **NOT REACHED** |
| 10 | typed RIPv2 process state | **NOT REACHED** |
| 11 | typed learned-route readback | **NOT REACHED** |
| 12 | typed forwarding behaviour | **NOT REACHED** |
| 13 | semantic cleanup / restoration | **PASS** — verified by re-observation |

Preserved unchanged:

```text
MODULE_IDENTITY = UNOBSERVABLE   (unchanged; port effect never proves identity)
CABLE_IDENTITY  = UNOBSERVABLE
APPLIED        != VERIFIED
```

## What this does and does not establish

```text
PRODUCT_PATH_REACHES_LIVE_DEPLOYMENT   = YES
PRODUCT_GENERATED_TOPOLOGY_DEPLOYED    = YES (8 devices)
SERIAL_ORIENTATION_EXERCISED           = NO
FULL_PRODUCT_PIPELINE_ACCEPTANCE       = NOT_ESTABLISHED (unchanged)
CONTROL_PLANE_FOUNDATIONAL_REQUIREMENT_INTEGRATION = NOT_ESTABLISHED (unchanged)
TD_ACCEPTANCE_001                      = OPEN (unchanged)
TD_HARDWARE_001                        = OPEN (unchanged; no capability evidence produced)
```

MEG-5 must not open. The bounded run has to succeed first.

---

# Run 2 — 2026-08-18, after the TD-MODULE-SLOT-001 branch-B correction

## Outcome, stated first

```text
MEG_4_STATUS                  = FAILED / CLEAN
STOPPED_AT                    = physical_deployment (device port observation)
FAILURE_CODE                  = port_observation_failed
LIVE_PACKET_TRACER_RUN        = YES
SEMANTIC_INVENTORY_RESTORED   = YES  (verified by independent re-observation)
E4_IDENTITY_PRESERVED         = YES
RAW_IOS_OR_JS_USED            = NONE
HARNESS_PERFORMED_A_MUTATION  = NO
```

**The module gate this run existed to unblock is closed.** Both HWIC-2T modules
verified, and the run advanced past the point where run 1 died. It then hit a
different, genuine defect — one run 1 never reached because the module gate
stopped it first. Nothing here upgrades any acceptance line.

## Gates, in order

### G2 — same-process import isolation

```text
state              = ISOLATED
sys.executable     = <worktree>/.venv/Scripts/python.exe
loaded identities  = ['packet_tracer_mcp']          # exactly one
packet_tracer_mcp.__file__ = <worktree>/src/packet_tracer_mcp/__init__.py
```

Run three times: in the read-only probe, in the mutating process itself before
its first mutation, and in the independent post-cleanup re-observation.
`PT_MCP_GOVERNED_ROOT` was set per run process and never persisted.

### G3 — process rediscovery, inventory, build, classification

The previous run's PID was **not** assumed. Processes were re-enumerated:

```text
PID 41784  MainWindowHandle = 1968802   <- the GUI instance
PID 7832   MainWindowHandle = 0         <- helper
both       C:\Program Files\Cisco Packet Tracer 9.0.1\bin\PacketTracer.exe
both       FileVersion = ProductVersion = 9.0.1.0858
StartTime  unchanged since run 1 — the instance was never restarted
```

```text
inventory       = observed=True, semantic_devices=0, links=0, backend_managed=1
                  ("Power Distribution Device0", zero ports)
classification  = DISPOSABLE
```

**Build evidence, and its exact limit.** Run 1's probe asked Packet Tracer for
its version through a guessed API (`pt.system.version`) and got
`ReferenceError: pt is not defined`. That guess is not repeated — `AGENTS.md`
rule 6 forbids it, and this repository still has no confirmed Packet Tracer API
that reports the build. What the OS evidence establishes, and what it does not:

```text
PT_GUI_PROCESS_BUILD           = 9.0.1.0858   (Windows process metadata)
ALL_PT_PROCESSES_SAME_BINARY   = YES          -> whichever serves the bridge,
                                                 the build is 9.0.1.0858
BRIDGE_PEER_PROCESS_IDENTITY   = NOT_ATTESTED
BRIDGE_PEER_BUILD_SELF_REPORT  = NOT_ATTESTED
```

A bounded limitation, stated rather than inferred away. It is *stronger* than
run 1's record, which identified only one process: because both running Packet
Tracer processes come from the same 9.0.1.0858 executable, the build question is
answered even though the peer's identity is not.

## The run

Semantic request → `execute_enterprise_reference`, called once. The harness
built the intent, constructed the four production runtimes, and recorded the
result. It sequenced nothing and mutated nothing.

```text
devices  = 8    (2x 2911 edge routers, 2 access switches, 4 PCs)
links    = 7    (2 edge links, 4 endpoint access links, 1 serial WAN)
routers  = 2911 (steered via HardwarePlanningPolicy.preferred_router_model)
switches = IE-2000 (selected by the product, not steered)
serial   = link/wan_link/23682ae56217
physical_topology_hash = 5bb34605303299c4de1d24fe5a1a77af80f2c87078fc6af4a2ba1a65262e03dd
```

Identical planned shape and hash to run 1, so the two runs are comparable.
Deployment: **8 devices applied, 10 journal entries changed, 2 failed.**

## What the branch-B correction proved

Both modules verified. The manifest evidence, per module:

```text
e4/module-effect/<device>:0/0:HWIC-2T     observed     / VERIFIED   / verifies_claim=True
e4/module-identity/<device>:0/0:HWIC-2T   unobservable / UNVERIFIED / verifies_claim=False
e4/module-placement/<device>:0/0:HWIC-2T  unobservable / UNVERIFIED / verifies_claim=False
   limitation: "Packet Tracer reports module-tree numbers in a namespace this
   repository cannot map to the requested slot; exact physical placement is not
   claimed. TD-MODULE-SLOT-001."
```

The port effect is verified from before/after evidence that this transaction
caused it. Identity and placement remain UNOBSERVABLE and are recorded as such
in the manifest rather than omitted.

## The defect this run found

```text
Device 'sw-acc-a-default-01' is missing planned physical port(s):
    FastEthernet0/1, FastEthernet0/2, GigabitEthernet0/1.
Device 'sw-acc-b-default-01' — identical.
```

Measured, from the live read-back of the deployed device:

```text
planned  (from the catalogue) : FastEthernet0/1..0/8, GigabitEthernet0/1, 0/2
observed (from PT 9.0.1.0858) : FastEthernet1/1..1/8, GigabitEthernet1/1, 1/2, Vlan1
model                         : IE-2000
```

Root cause, traced rather than guessed:
`infrastructure/catalog/devices.py:173` declares the IE-2000's ports in the
`0/x` namespace. The real Packet Tracer IE-2000 numbers them `1/x`. From there
the wrong names flow straight through the product —
`port_descriptors_for` → `HardwareCandidate.ports` → `HardwarePlanner` →
`EnterpriseCompiler` link endpoints → the deployer's required-port set — so
every plan that selects an IE-2000 asks Packet Tracer for ports that cannot
exist.

**Why this was never hit before.** The pinned reference topology chooses
`2960-24TT` by hand, and `2960-24TT` really is a `0/x` device.
Capability-driven selection picks the *smallest viable* access switch, which for
a two-endpoint site is the eight-port IE-2000 — a model the reference never
exercises. Run 1 did not reach this stage because the module gate stopped it
first.

**Not worked around.** Steering the switch model the way the router is steered
would have made this run pass while leaving the catalogue wrong, and rewriting
one catalogue entry from a single observation would leave every other unmeasured
model in the same state. Opened as `TD-CATALOG-PORT-001`.

## Module replay qualification — the required decision

```text
CAN_PACKET_TRACER_AUTHENTICALLY_QUALIFY_MODULE_REPLAY_CONTAINMENT = NO
```

Unchanged from run 1, and for the same reason: each module was inserted once and
no replay condition arose. Provoking one would require a transport-level resend,
which is forbidden. The ceiling stands:

```text
MODULE_REPLAY_GUARD = MEASURED_IN_NODE / PACKET_TRACER_NOT_YET_QUALIFIED
                    + BACKEND_LIMITATION for provoking replay in a bounded run
                    + payload-local containment (receipt + exact slot pre-read)

PACKET_TRACER_REPLAY_QUALIFICATION = NOT_ESTABLISHED / backend-limited
GLOBAL EXACTLY_ONCE  = NOT CLAIMED
GLOBAL AT_MOST_ONCE  = NOT CLAIMED
```

## TD-HARDWARE-001 — explicit re-evaluation

Read from the composition the product actually produced, not asserted:

```text
CAPABILITY_CONSUMER_INVOKED       = YES
    consumer   = application.use_cases.plan_enterprise_hardware
    bound to   = 9.0.1.0858
    candidates = 15 routers + 8 switches, all reaching the resolver

PINNED_BACKEND_EVIDENCE_AVAILABLE = NO
    data/capabilities/ does not exist; no runtime or verified snapshot for
    9.0.1.0858 exists anywhere in the repository

PINNED_BACKEND_EVIDENCE_USED      = NO

TD_HARDWARE_LITERAL_CRITERION     = NOT_SATISFIED
```

Every functional capability on every candidate resolved `unknown`. The only
non-unknown fields are `supports_modules`, `category` and `source`, and `source`
reads `packet_tracer_catalog` — catalogue data, not backend evidence. **UNKNOWN
was preserved everywhere and nothing was fabricated.** No capability probe was
added to force closure.

Did UNKNOWN block the concrete operation? No. Selection proceeded on ports and
category, and the deployment failed on a catalogue *port-name* error, not on
absent capability evidence.

```text
TD_HARDWARE_001 = OPEN (unchanged)
```

## G4 — cleanup and restoration

```text
cleanup entries    = 8, all disposition=changed, applied=True
removal order      = reverse of deployment
targets            = exactly the eight names the product planned
inventory_restored = True
```

Independent post-run re-observation, separate process:

```text
semantic_device_count = 0
link_count            = 0
backend_managed       = 1  ("Power Distribution Device0", zero ports)
classification        = disposable
```

The power-distribution object was present at baseline **and** after, so this is
a full match rather than the tolerated-difference case run 1 recorded. No
foreign, pre-existing or backend-managed object was removed.

## Exit matrix

| # | Item | Result |
| --- | --- | --- |
| 1 | exact-version capability consumption attempted by the normal path | **YES** — bound to 9.0.1.0858, 23 candidates; no evidence available, UNKNOWN preserved |
| 2 | product-generated `TopologyPlan` | **PASS** — 8 devices / 7 links from a semantic intent |
| 3 | module effect containment | **PASS** — port effect VERIFIED on both routers; identity and placement UNOBSERVABLE and recorded |
| 4 | fresh two-ended serial orientation | **NOT REACHED** |
| 5 | exactly one DCE and one DTE | **NOT REACHED** |
| 6 | typed E5 serial transit addressing | **NOT REACHED** |
| 7 | clock on the observed DCE only | **NOT REACHED** |
| 8 | independent clock readback | **NOT REACHED** |
| 9 | authentic foundational evidence | **NOT REACHED** |
| 10 | typed RIPv2 process state | **NOT REACHED** |
| 11 | typed learned-route readback | **NOT REACHED** |
| 12 | typed forwarding behaviour | **NOT REACHED** |
| 13 | semantic cleanup / restoration | **PASS** — verified by independent re-observation |

Row 3 moves from **PARTIAL** to **PASS**; everything else is unchanged from
run 1.

Preserved unchanged:

```text
MODULE_IDENTITY  = UNOBSERVABLE
MODULE_PLACEMENT = UNOBSERVABLE
CABLE_IDENTITY   = UNOBSERVABLE
APPLIED         != VERIFIED
```

## What this does and does not establish

```text
PRODUCT_PATH_REACHES_LIVE_DEPLOYMENT   = YES
PRODUCT_GENERATED_TOPOLOGY_DEPLOYED    = YES (8 devices)
MODULE_PORT_EFFECT_VERIFIED_LIVE       = YES (both routers, this run)
SERIAL_ORIENTATION_EXERCISED           = NO
FULL_PRODUCT_PIPELINE_ACCEPTANCE       = NOT_ESTABLISHED (unchanged)
CONTROL_PLANE_FOUNDATIONAL_REQUIREMENT_INTEGRATION = NOT_ESTABLISHED (unchanged)
TD_ACCEPTANCE_001                      = OPEN (unchanged)
TD_HARDWARE_001                        = OPEN (unchanged)
TD_MODULE_SLOT_001                     = BACKEND_LIMITATION (closed this session)
TD_CATALOG_PORT_001                    = OPEN (opened by this run)
```

MEG-5 must not open. The bounded run has to succeed first.
