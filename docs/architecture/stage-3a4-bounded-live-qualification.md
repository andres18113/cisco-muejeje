# Stage 3A4 — MEG-4 bounded live qualification

Three runs so far, all on `feature/runtime-ripv2`, worktree
`.claude/worktrees/runtime-ripv2`. **Run 3, at the end of this document, is
the current state.** Runs 1 and 2 are left exactly as they were recorded —
they are history, not a summary of where things stand.

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

---

# Run 3 — 2026-08-18, after the TD-CATALOG-PORT-001 port-evidence contract

## Outcome, stated first

```text
MEG_4_STATUS                  = FAILED / CLEAN
STOPPED_AT                    = serial_orientation
LIVE_PACKET_TRACER_RUN        = YES
PHYSICAL_DEPLOYMENT           = VERIFIED  (first time, with a manifest)
SEMANTIC_INVENTORY_RESTORED   = YES  (verified by independent re-observation)
E4_IDENTITY_PRESERVED         = YES
RAW_IOS_OR_JS_USED            = NONE
HARNESS_PERFORMED_A_MUTATION  = NO
```

**The whole physical stage closed.** Eight product-generated devices, seven
links including the serial WAN, both module port effects verified, seventeen
items observed, `dirty_state = clean`, and a deployment manifest emitted from
fresh exact read-back. Run 2 never produced a manifest; run 1 never reached
link creation.

It then stopped at serial orientation, on a condition neither earlier run could
reach. **Nothing here upgrades any acceptance line** — TD-ACCEPTANCE-001 closes
on rows 1–4 and 6 in one *reference* run, and this is the bounded shape.

## Gates, in order

### G2 — same-process import isolation

```text
state              = ISOLATED
sys.executable     = <worktree>/.venv/Scripts/python.exe
loaded identities  = ['packet_tracer_mcp']          # exactly one
```

Run three times: read-only probe, the mutating process before its first
mutation, and the independent post-cleanup re-observation.
`PT_MCP_GOVERNED_ROOT` was set per run process and never persisted.

### G3 — process rediscovery, inventory, build, classification

The historical PID was not assumed; processes were re-enumerated.

```text
PID 41784  MainWindowHandle = 1968802   <- the GUI instance
PID 7832   MainWindowHandle = 0         <- helper
both       FileVersion = ProductVersion = 9.0.1.0858, same executable

inventory       = observed=True, semantic_devices=0, links=0, backend_managed=1
classification  = DISPOSABLE
```

Build evidence and its limit are unchanged from run 2: `PT_GUI_PROCESS_BUILD =
9.0.1.0858` from Windows process metadata, with
`BRIDGE_PEER_PROCESS_IDENTITY` and `BRIDGE_PEER_BUILD_SELF_REPORT` both
`NOT_ATTESTED`. No Packet Tracer API was guessed.

## What the port-evidence contract changed

The bounded plan is the same shape as run 2 with different port names, because
`IE-2000` now plans from what Packet Tracer reported rather than from what the
catalogue declares:

```text
devices  = 8    (2x 2911 edge routers, 2x IE-2000 access switches, 4 PCs)
links    = 7    (2 edge links, 4 endpoint access links, 1 serial WAN)
access   = FastEthernet1/1, FastEthernet1/2      (run 2 planned 0/1, 0/2)
uplink   = GigabitEthernet1/1                    (run 2 planned 0/1)
physical_topology_hash = 1d2324aa7cf334584f2b6ecb27791e113676a5076a54c7c5c32285ca22d67692
```

The hash differs from run 2's `5bb34605…` for exactly that reason, and the
change is confined to the one model with a measured inventory.

Deployment result:

```text
status       = VERIFIED
failure_code = none
items        = 17 observed, 0 failed
journal      = 17 attempted, 17 changed, dirty_state = clean
manifest     = 8 device bindings, 7 link bindings
               identity method: composite_fingerprint x8
               semantic_hash 816fab9da5317d0272fb8f7849ce44bbbf50a2cb29f19f982f735b3d1a0da5cc
```

Module evidence, per router, unchanged in shape from run 2:

```text
e4/module-effect/<device>:0/0:HWIC-2T     observed     / VERIFIED   / verifies_claim=True
e4/module-identity/<device>:0/0:HWIC-2T   unobservable / UNVERIFIED
e4/module-placement/<device>:0/0:HWIC-2T  unobservable / UNVERIFIED
```

## The defect this run found

```text
Serial endpoint 'r-edge-a-01' on 'link/wan_link/23682ae56217':
    Registered controller query was truncated by the pager.
Serial endpoint 'r-edge-b-01' — identical.
```

Both endpoints, same cause. The orientation observer refused rather than read
DCE/DTE out of a half-captured buffer, which is the behaviour it was built for.

What is already known in this repository, and what is new:

```text
known    ios_terminal.py:1153 and :462, command_dispatch.py:154 all record that
         PT 9.0.1 REJECTS `terminal length 0`, so the pager cannot be disabled
         the ordinary way on this build
known    TD-RUNTIME-003 handles pager truncation for `show ip protocols` by
         reporting UNOBSERVABLE rather than FAILED
new      `show controllers Serial0/0/0` on a 2911 with an HWIC-2T exceeds one
         page on this build, so the orientation query truncates every time
new      the executor cancels the pager to stop it poisoning the next query and
         keeps the first page; the observer then fails closed
```

The query is already interface-scoped — `SHOW_CONTROLLERS_SERIAL` with
`interface=Serial0/0/0`, not a whole-chassis dump — so narrowing it further is
not available.

**Not worked around.** Whether the DCE/DTE line sits on the captured first page
is not known, and reading it out of a buffer the product itself flagged as
truncated would be exactly the "parse it anyway" shortcut the flag exists to
prevent. Opened as `TD-ORIENTATION-PAGER-001`.

## Module replay qualification — the required decision

```text
CAN_PACKET_TRACER_AUTHENTICALLY_QUALIFY_MODULE_REPLAY_CONTAINMENT = NO
```

Unchanged, and for the same reason as both earlier runs: each module was
inserted once and no replay condition arose. The ceiling stands:

```text
MODULE_REPLAY_GUARD = MEASURED_IN_NODE / PACKET_TRACER_NOT_YET_QUALIFIED
                    + BACKEND_LIMITATION for provoking replay in a bounded run
                    + payload-local containment (receipt + exact slot pre-read)

PACKET_TRACER_REPLAY_QUALIFICATION = NOT_ESTABLISHED / backend-limited
GLOBAL EXACTLY_ONCE  = NOT CLAIMED
GLOBAL AT_MOST_ONCE  = NOT CLAIMED
```

## TD-HARDWARE-001 — explicit re-evaluation

Read from the composition the product produced, not asserted:

```text
CAPABILITY_CONSUMER_INVOKED       = YES  (plan_enterprise_hardware, bound to 9.0.1.0858)
PINNED_BACKEND_EVIDENCE_AVAILABLE = NO   (data/capabilities/ still does not exist)
PINNED_BACKEND_EVIDENCE_USED      = NO
TD_HARDWARE_LITERAL_CRITERION     = NOT_SATISFIED
IE2000_SELECTION_EVIDENCE_TIER    = DECLARED (category and port counts)
                                  + UNKNOWN (every functional capability)
                                  + no BACKEND_VERIFIED input to the decision
```

Every functional capability on all 23 candidates resolved `unknown`; the only
non-unknown fields are `category`, `supports_modules` and `source`, and `source`
reads `packet_tracer_catalog`. UNKNOWN was preserved and nothing was fabricated.
No capability probe was added.

Did UNKNOWN block the concrete operation? No. The deployment succeeded, and the
run stopped on pager truncation — an IOS read-back condition, not absent
capability evidence.

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

`SEMANTIC_INVENTORY_RESTORED = YES`. No foreign, pre-existing or
backend-managed object was removed.

## Exit matrix

| # | Item | Result |
| --- | --- | --- |
| 1 | exact-version capability consumption attempted by the normal path | **YES** — bound to 9.0.1.0858, 23 candidates; no evidence available, UNKNOWN preserved |
| 2 | product-generated `TopologyPlan` | **PASS** — 8 devices / 7 links from a semantic intent |
| 3 | module effect containment | **PASS** — port effect VERIFIED on both routers; identity and placement UNOBSERVABLE |
| 4 | fresh two-ended serial orientation | **FAIL** — both endpoints truncated by the pager |
| 5 | exactly one DCE and one DTE | **NOT REACHED** |
| 6 | typed E5 serial transit addressing | **NOT REACHED** |
| 7 | clock on the observed DCE only | **NOT REACHED** |
| 8 | independent clock readback | **NOT REACHED** |
| 9 | authentic foundational evidence | **NOT REACHED** |
| 10 | typed RIPv2 process state | **NOT REACHED** |
| 11 | typed learned-route readback | **NOT REACHED** |
| 12 | typed forwarding behaviour | **NOT REACHED** |
| 13 | semantic cleanup / restoration | **PASS** — verified by independent re-observation |

Row 4 moves from **NOT REACHED** to **FAIL**, which is progress: the stage was
exercised for the first time and returned a measurement. Rows 1, 2, 3 and 13
hold from run 2. Row 3's manifest is now real rather than refused.

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
PRODUCT_GENERATED_TOPOLOGY_DEPLOYED    = YES (8 devices, 7 links)
PHYSICAL_DEPLOYMENT_MANIFEST_EMITTED   = YES (first time, from fresh read-back)
MODULE_PORT_EFFECT_VERIFIED_LIVE       = YES (both routers)
SERIAL_ORIENTATION_OBSERVED            = NO  (measured, and it failed closed)
FULL_PRODUCT_PIPELINE_ACCEPTANCE       = NOT_ESTABLISHED (unchanged)
CONTROL_PLANE_FOUNDATIONAL_REQUIREMENT_INTEGRATION = NOT_ESTABLISHED (unchanged)
TD_ACCEPTANCE_001                      = OPEN (unchanged; bounded shape, not the reference run)
TD_HARDWARE_001                        = OPEN (unchanged)
TD_MODULE_SLOT_001                     = BACKEND_LIMITATION (unchanged)
TD_CATALOG_PORT_001                    = RESOLVED (this session)
TD_ORIENTATION_PAGER_001               = OPEN (opened by this run)
```

MEG-5 must not open. The bounded run has to succeed first, and separately the
reference run's own models need measured port inventories.

---

# Run 4 — 2026-08-18, after the TD-ORIENTATION-PAGER-001 branch-A capture

## Outcome, stated first

```text
MEG_4_STATUS                  = FAILED / CLEAN
STOPPED_AT                    = configuration_apply
LIVE_PACKET_TRACER_RUN        = YES
PHYSICAL_DEPLOYMENT           = VERIFIED
SERIAL_ORIENTATION            = VERIFIED  (first time, both endpoints)
SEMANTIC_INVENTORY_RESTORED   = YES  (verified by independent re-observation)
E4_IDENTITY_PRESERVED         = YES
RAW_IOS_OR_JS_USED            = NONE
HARNESS_PERFORMED_A_MUTATION  = NO
```

**Serial orientation closed.** Both bound endpoints returned a complete
multi-page controller read-back, one DCE and one DTE, and the deployment
manifest was oriented. The clock was applied to the observed DCE only and read
back independently as VERIFIED. Run 3 could not reach any of that.

It then stopped at configuration application, on a condition no earlier run
reached, and one that is not new code: the E5 capability gate has no evidence
to resolve. **Nothing here upgrades any acceptance line** — TD-ACCEPTANCE-001
closes on rows 1–4 and 6 in one *reference* run, and this is the bounded shape.

## Gates, in order

### G2 — same-process import isolation

```text
state              = ISOLATED
sys.executable     = <worktree>/.venv/Scripts/python.exe
packet_tracer_mcp.__file__ = <worktree>/src/packet_tracer_mcp/__init__.py
loaded identities  = ['packet_tracer_mcp']          # exactly one
```

Run three times: read-only probe, the mutating process before its first
mutation, and the independent post-cleanup re-observation.
`PT_MCP_GOVERNED_ROOT` was set per run process and never persisted.

### G3 — process rediscovery, transport, inventory, build, classification

**The historical PID was not assumed, and this time that mattered.** Run 3's
GUI instance was PID `41784`; it is gone. Re-enumeration found a different pair:

```text
PID 16584  MainWindowHandle = 264778  StartTime 2026-08-18 09:40:21   <- GUI
PID  4212  MainWindowHandle = 0       StartTime 2026-08-18 09:40:25   <- helper
both       C:\Program Files\Cisco Packet Tracer 9.0.1\bin\PacketTracer.exe
both       FileVersion = ProductVersion = 9.0.1.0858
```

Packet Tracer was restarted between run 3 and run 4. Had the PID been carried
forward from the record, the build evidence would have described a process that
no longer exists.

```text
transport       = file bridge (heartbeat age 0.6s at probe time)
inventory       = observed=True, semantic_devices=0, links=0, backend_managed=0
                  message="fresh_complete_workspace_inventory"
classification  = DISPOSABLE
```

No semantic, manual, user or graded topology was present, so no HARD STOP was
triggered. Build evidence keeps the same bounded limit as runs 2 and 3:

```text
PT_GUI_PROCESS_BUILD           = 9.0.1.0858   (Windows process metadata)
ALL_PT_PROCESSES_SAME_BINARY   = YES
BRIDGE_PEER_PROCESS_IDENTITY   = NOT_ATTESTED
BRIDGE_PEER_BUILD_SELF_REPORT  = NOT_ATTESTED
```

No Packet Tracer API was guessed. Run 1's `pt.system.version` guess is still not
repeated.

## The run

Semantic request → `execute_enterprise_reference`, called once. The harness
built the intent, constructed the four production runtimes over the file
bridge, and recorded the result. It sequenced nothing and mutated nothing.

```text
devices  = 8    (2x 2911 edge routers, 2x IE-2000 access switches, 4 PCs)
links    = 7    (2 edge links, 4 endpoint access links, 1 serial WAN)
routers  = 2911 (steered via HardwarePlanningPolicy.preferred_router_model)
serial   = link/wan_link/23682ae56217
physical_topology_hash = 1d2324aa7cf334584f2b6ecb27791e113676a5076a54c7c5c32285ca22d67692
```

Identical planned shape and hash to run 3, so the two runs are directly
comparable.

```text
deployment   status = VERIFIED, failure_code = none
             items  = 17 observed, 0 failed
             journal= 17 attempted, 17 changed, dirty_state = clean
             manifest = 8 device bindings, 7 link bindings
                        identity method: composite_fingerprint x8
                        semantic_hash f0fa22f49616c42306456d729706c9e0e3c84e85388e16162b4b45caa931b383
```

Module evidence per router, unchanged in shape from runs 2 and 3: port effect
`VERIFIED`; identity and placement `unobservable / UNVERIFIED` under
TD-MODULE-SLOT-001.

## What the pager capture established

The first live measurement of a bounded multi-page registered read-back:

```text
A-EDGE-RTR-01  Serial0/0/0  orientation=dce  clock_rate_bps=2000000
               pages_captured=4  pagination=completed
               executed=True fresh=True complete=True truncated=False
               parseable=True interface_identity_match=True

B-EDGE-RTR-01  Serial0/0/0  orientation=dte  clock_rate_bps=None
               pages_captured=4  pagination=completed
               executed=True fresh=True complete=True truncated=False
               parseable=True interface_identity_match=True
```

Four pages per endpoint, on the same query that returned `truncated_by_pager`
on every attempt in run 3. Packet Tracer does deliver the single key the
`--More--` consumes, and the assembled read closed on a prompt both times.

```text
orientation status                  = verified
source_manifest_semantic_hash       = f0fa22f4…
oriented_manifest_semantic_hash     = aa8e76e4…
physical_topology_hash              = 1d2324aa…  (unchanged — E4 identity intact)
exactly one DCE and one DTE         = YES
```

`TD-ORIENTATION-PAGER-001` is closed by this measurement. Branch B's premise —
that the role line might always sit on page one — is now moot and was never
relied on. The DCE line was in fact on page 1 of 4, which is precisely why
accepting a truncated first page would have *looked* like it worked and would
still have been unsound.

## The defect this run found

```text
Configuration application ended partial, and only VERIFIED is evidence the
control plane may build on.
```

Of 17 compiled configuration actions:

```text
applied              1   the serial clock on the observed DCE
skipped             12   failure_code = capability_unknown
dependency_blocked   4   endpoint addressing, blocked by the skipped access ports
```

The twelve skips, verbatim:

```text
supports_vlan is unknown for IE-2000.   x8   (vlan, access, gateway-access)
layer3 is unknown for 2911.             x4   (routed interfaces, transit L3)
```

Verification followed the same shape: **1 verified, 16 dependency_blocked.**

Root cause, read from the resolver rather than inferred: **no capability
evidence reaches the E5 gate for any model.** Measured offline against the same
adapter and build:

```text
model        supports_vlan   layer2     layer3     source
2911         unknown         unknown    unknown    packet_tracer_catalog
IE-2000      unknown         unknown    unknown    packet_tracer_catalog
2960-24TT    unknown         unknown    unknown    packet_tracer_catalog
1941         unknown         unknown    unknown    packet_tracer_catalog
3560         unknown         unknown    unknown    packet_tracer_catalog
3650         unknown         unknown    unknown    packet_tracer_catalog
```

Every model, every functional dimension. `supports_modules` is the only
non-unknown capability and it comes from the catalogue, not from the backend.
So this is **not** an IE-2000 problem and not a consequence of model steering:
the same gate would skip the same action families on the 41-device reference.

**The gate is correct.** UNKNOWN is not permission, nothing was dispatched on
absent evidence, and no claim was inflated. What is missing is the evidence
path: `execute_enterprise_reference` never gathers capability evidence, and no
capability snapshot exists for this build (`data/capabilities/` still does not
exist). `CapabilityDiscoveryService` and its probes exist in the product but are
not part of the execution path, and running them is itself a mutation that this
ticket had no authorisation to perform.

**Why the serial clock got through, stated exactly rather than flatteringly.**
Not because it has measured evidence. `ConfigureSerialClock` inherits
`required_capability = ""` from `BaseConfigurationAction`, and
`configuration_compiler.py:1178` skips the capability check entirely for an
action that declares no requirement. A real mutation reached a live device
without passing the gate that stopped every other action. Recorded as an
observation, not resolved here.

**Not worked around.** Supplying a hand-built capability profile, or relaxing
the gate to treat UNKNOWN as permissive, would each have manufactured a pass.
Opened as `TD-CONFIG-CAPABILITY-001`.

## Module replay qualification — the required decision

```text
CAN_PACKET_TRACER_AUTHENTICALLY_QUALIFY_MODULE_REPLAY_CONTAINMENT = NO
```

Unchanged, and for the same reason as all three earlier runs: each module was
inserted once and no replay condition arose. The ceiling stands:

```text
MODULE_REPLAY_GUARD = MEASURED_IN_NODE / PACKET_TRACER_NOT_YET_QUALIFIED
                    + BACKEND_LIMITATION for provoking replay in a bounded run
                    + payload-local containment (receipt + exact slot pre-read)

PACKET_TRACER_REPLAY_QUALIFICATION = NOT_ESTABLISHED / backend-limited
GLOBAL EXACTLY_ONCE  = NOT CLAIMED
GLOBAL AT_MOST_ONCE  = NOT CLAIMED
```

## TD-HARDWARE-001 — explicit re-evaluation

```text
CAPABILITY_CONSUMER_INVOKED       = YES  (plan_enterprise_hardware, bound to 9.0.1.0858)
PINNED_BACKEND_EVIDENCE_AVAILABLE = NO   (data/capabilities/ still does not exist)
PINNED_BACKEND_EVIDENCE_USED      = NO
TD_HARDWARE_LITERAL_CRITERION     = NOT_SATISFIED
UNKNOWN_PRESERVED                 = YES, everywhere; nothing fabricated
```

**One answer changes from runs 2 and 3.** Did UNKNOWN block the concrete
operation? Runs 2 and 3 recorded *no* — the failures were a catalogue port-name
error and a pager truncation. Run 4 records **yes**: absent capability evidence
is exactly what stopped this run. The debt's practical cost is now measured
rather than argued.

That does not close it and does not change its criterion. `TD-HARDWARE-001` is
about capability evidence reconciling into *hardware selection*; what run 4 hit
is the same missing evidence arriving at the *configuration* gate. The new entry
records that seam.

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

Independent post-run re-observation, separate process, separate G2:

```text
semantic_device_count = 0
link_count            = 0
backend_managed       = 1  ("Power Distribution Device0", zero ports)
classification        = disposable
```

The power-distribution object was **absent at baseline and present after**, the
same tolerated-difference case run 1 recorded and unlike run 3's exact match. It
is backend-created, carries zero ports, and is exactly what
`disposable_workspace_error` permits. Recorded rather than smoothed over. No
foreign, pre-existing or backend-managed object was removed.

## Exit matrix

| # | Item | Result |
| --- | --- | --- |
| 1 | exact-version capability consumption attempted by the normal path | **YES** — bound to 9.0.1.0858; no evidence available, UNKNOWN preserved |
| 2 | product-generated `TopologyPlan` | **PASS** — 8 devices / 7 links from a semantic intent |
| 3 | module effect containment | **PASS** — port effect VERIFIED on both routers; identity and placement UNOBSERVABLE |
| 4 | fresh two-ended serial orientation | **PASS** — 4 pages captured per endpoint, complete, non-truncated |
| 5 | exactly one DCE and one DTE | **PASS** — DCE on A-EDGE-RTR-01, DTE on B-EDGE-RTR-01 |
| 6 | typed E5 serial transit addressing | **FAIL** — skipped, `layer3 is unknown for 2911` |
| 7 | clock on the observed DCE only | **PASS** — one clock action, on the observed DCE |
| 8 | independent clock readback | **PASS** — interface, role and rate VERIFIED from `fresh_show_controllers_serial` |
| 9 | authentic foundational evidence | **NOT REACHED** |
| 10 | typed RIPv2 process state | **NOT REACHED** |
| 11 | typed learned-route readback | **NOT REACHED** |
| 12 | typed forwarding behaviour | **NOT REACHED** |
| 13 | semantic cleanup / restoration | **PASS** — verified by independent re-observation |

Rows 4, 5, 7 and 8 move to **PASS** for the first time. Row 6 moves NOT REACHED
→ **FAIL**, which is progress in the same sense row 4 was in run 3: the stage
was exercised and returned a measurement.

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
PRODUCT_GENERATED_TOPOLOGY_DEPLOYED    = YES (8 devices, 7 links)
PHYSICAL_DEPLOYMENT_MANIFEST_EMITTED   = YES
MODULE_PORT_EFFECT_VERIFIED_LIVE       = YES (both routers)
SERIAL_ORIENTATION_OBSERVED            = YES (both endpoints, complete capture)
BOUNDED_MULTI_PAGE_CAPTURE             = LIVE_QUALIFIED (4 pages x 2 endpoints)
SERIAL_CLOCK_APPLIED_AND_READ_BACK     = YES (DCE only)
E5_CONFIGURATION_VERIFIED              = NO  (partial: 1 of 17)
FULL_PRODUCT_PIPELINE_ACCEPTANCE       = NOT_ESTABLISHED (unchanged)
CONTROL_PLANE_FOUNDATIONAL_REQUIREMENT_INTEGRATION = NOT_ESTABLISHED (unchanged)
TD_ACCEPTANCE_001                      = OPEN (unchanged; bounded shape, not the reference run)
TD_HARDWARE_001                        = OPEN (unchanged)
TD_MODULE_SLOT_001                     = BACKEND_LIMITATION (unchanged)
TD_CATALOG_PORT_001                    = RESOLVED (unchanged)
TD_ORIENTATION_PAGER_001               = RESOLVED (closed by this run)
TD_CONFIG_CAPABILITY_001               = OPEN (opened by this run)
```

```text
MEG_5                  = NOT_OPENED
MEG_5_EXECUTION        = BLOCKED
REFERENCE_41_41_RUN    = NOT_EXECUTED
```

MEG-5 must not open. The bounded run still has to succeed, and the blocker that
stopped it is model-independent, so the 41-device reference would meet the same
gate on its first configuration action.

---

# Run 5 — 2026-08-18, after the required-batch preflight fix and the E5 evidence path

## Outcome, stated first

```text
MEG_4_STATUS                  = FAILED / CLEAN
STOPPED_AT                    = configuration_apply
FAILURE                       = observability limitation, not authorisation
LIVE_PACKET_TRACER_RUN        = YES
PHYSICAL_DEPLOYMENT           = VERIFIED
SERIAL_ORIENTATION            = VERIFIED  (both endpoints, 4 pages each)
E5_ACTIONS_APPLIED            = 17 of 17
SEMANTIC_INVENTORY_RESTORED   = YES  (verified by independent re-observation)
E4_IDENTITY_PRESERVED         = YES
RAW_IOS_OR_JS_USED            = NONE
HARNESS_PERFORMED_A_MUTATION  = NO
```

**Every compiled configuration action applied.** Run 4 applied one of
seventeen and skipped twelve on absent capability evidence; run 5 applied all
seventeen on measured evidence, and stopped on what the read-back could not
observe rather than on what the product was not allowed to do.

## Gates, in order

### G2 — same-process import isolation

```text
state              = ISOLATED
sys.executable     = <worktree>/.venv/Scripts/python.exe
loaded identities  = ['packet_tracer_mcp']          # exactly one
```

Run four times this session: the read-only probe, the capability
qualification, the mutating run before its first mutation, and the independent
post-cleanup re-observation. `PT_MCP_GOVERNED_ROOT` was set per process and
never persisted.

### G3 — process rediscovery, inventory, build, classification

The historical PID was not assumed; processes were re-enumerated before each
live phase.

```text
PID 16584  MainWindowHandle = 264778  StartTime 2026-08-18 09:40:21   <- GUI
PID  4212  MainWindowHandle = 0       StartTime 2026-08-18 09:40:25   <- helper
both       FileVersion = ProductVersion = 9.0.1.0858, same executable

transport       = file bridge
inventory       = observed=True, semantic_devices=0, links=0,
                  backend_managed=1 ("Power Distribution Device0", zero ports)
classification  = DISPOSABLE
```

Build evidence keeps its bounded limit: `PT_GUI_PROCESS_BUILD = 9.0.1.0858`
from Windows process metadata, with `BRIDGE_PEER_PROCESS_IDENTITY` and
`BRIDGE_PEER_BUILD_SELF_REPORT` both `NOT_ATTESTED`. No PT API was guessed.

## Controlled capability qualification, before the run

Evidence production only, through the existing governed producer
(`CapabilityDiscoveryService`), bounded to exactly the two model/capability
pairs the 17-action plan requires. It is not the product execution path and
did not become one.

```text
IE-2000 : supports_vlan   session probe-53e0138d91ac
    created  __MCP_PROBE_53e0138d91ac_01, __MCP_PROBE_53e0138d91ac_01_vlan-probe
    cleanup  clean, both deleted, inventory_restored = True
    results  supports_vlan SUPPORTED / verified / controlled_probe
             layer2        SUPPORTED / verified / controlled_probe
             configuration_channel, model_exists, port_inventory (prerequisites)

2911 : layer3             session probe-71001ad19110
    created  __MCP_PROBE_71001ad19110_01, __MCP_PROBE_71001ad19110_01_layer3-probe
    cleanup  clean, both deleted, inventory_restored = True
    results  layer3        SUPPORTED / verified / controlled_probe
             configuration_channel, model_exists, port_inventory (prerequisites)
```

The prerequisite capabilities come with the probe graph — `supports_vlan`
requires `layer2` and `configuration_channel`, which require `port_inventory`
and `model_exists`. They are recorded because they were measured, not because
anything asked for them.

**Nothing else was qualified.** After the sessions, through the exact-version
composition root:

```text
2911         supports_vlan=unknown     layer2=unknown     layer3=supported
IE-2000      supports_vlan=supported   layer2=supported   layer3=unknown
PC-PT        supports_vlan=unknown     layer2=unknown     layer3=unknown
2960-24TT    supports_vlan=unknown     layer2=unknown     layer3=unknown
```

`2960-24TT` is the reference topology's access switch and stays UNKNOWN
deliberately: qualifying it belongs to the pre-MEG-5 pass, not to this ticket.

## The run

Semantic request → `execute_enterprise_reference`, called once. Same planned
shape and same physical topology hash as runs 3 and 4, so all three are
directly comparable.

```text
devices  = 8    (2x 2911, 2x IE-2000, 4x PC-PT)
links    = 7    (2 edge, 4 access, 1 serial WAN)
physical_topology_hash = 1d2324aa7cf334584f2b6ecb27791e113676a5076a54c7c5c32285ca22d67692

deployment   status = VERIFIED, 17 items observed, 0 failed
             journal 17 attempted / 17 changed, dirty_state = clean
             manifest 8 device bindings, 7 link bindings

orientation  A-EDGE-RTR-01 Se0/0/0  dce, clock 2000000, pages=4, completed
             B-EDGE-RTR-01 Se0/0/0  dte, clock None,    pages=4, completed
             status verified, exactly one DCE and one DTE
```

The pager capture reproduced run 4's result exactly — four pages per endpoint,
`pagination = completed` — which is the second independent live observation of
that path.

## What the E5 evidence path changed

```text
                          run 4                    run 5
applied                       1                       17
skipped (capability)         12                        0
dependency_blocked            4                        0
```

Every action that run 4 refused now carried measured, exact-version,
model-scoped evidence. The capability map the composition resolved and the map
the applicator authorised with are the same object:

```text
2911      layer3        = supported    (controlled probe, 9.0.1.0858)
IE-2000   supports_vlan = supported    (controlled probe, 9.0.1.0858)
PC-PT     everything    = unknown      (endpoint actions are ungated by contract)
```

Verification, which is a separate claim from application:

```text
verified       7   2 vlan (vlan_manager_object_state)
                   1 serial clock (fresh_show_controllers_serial)
                   4 routed interfaces (fresh_show_ip_interface_brief:
                     interface, ipv4, administrative_state, status, protocol)
unobservable   6   access ports — "No independent getter is registered for access_port"
partial        4   endpoint static — ipv4 and netmask verified,
                   gateway and dns unobservable
```

## The defect this run found

```text
Configuration application ended partial, and only VERIFIED is evidence the
control plane may build on.
```

Not an authorisation failure this time. All seventeen actions were authorised
and applied; six of them cannot be read back at all, because
`enterprise_configuration_runtime.py:265` routes `VerificationKind.ACCESS_PORT`
and `VerificationKind.DHCP_POOL` to `_unobservable`, and four more can only be
read back in part.

**This is an already-registered gap, not a new discovery.**
`docs/qa/e95-runtime-debt.md` carries the row *"Access-port direct getter — E5
can return UNOBSERVABLE when no independent direct getter is available.
`UNKNOWN — PENDING_LIVE_VALIDATION`; application acceptance is not read-back."*
Run 5 is that live validation: the product path reaches the row, and the answer
is that this repository registers no access-port read-back query.

What is **not** established, and must not be recorded as if it were: whether
Packet Tracer exposes such a getter at all. Nothing probed for one. The gap is
a missing registered query in this repository until a controlled reproduction
says otherwise, so the row keeps `UNKNOWN` rather than becoming
`BACKEND_LIMITATION_CONFIRMED`.

**Not worked around.** Accepting APPLIED as VERIFIED for the six unobservable
rows would have produced a green MEG-4 and would have been exactly the
substitution this project's whole evidence discipline exists to prevent.

## Module replay qualification — the required decision

```text
CAN_PACKET_TRACER_AUTHENTICALLY_QUALIFY_MODULE_REPLAY_CONTAINMENT = NO
```

Unchanged, and for the same reason as all four earlier runs: each module was
inserted once and no replay condition arose.

```text
MODULE_REPLAY_GUARD = MEASURED_IN_NODE / PACKET_TRACER_NOT_YET_QUALIFIED
                    + BACKEND_LIMITATION for provoking replay in a bounded run
                    + payload-local containment (receipt + exact slot pre-read)
GLOBAL EXACTLY_ONCE  = NOT CLAIMED
GLOBAL AT_MOST_ONCE  = NOT CLAIMED
```

## TD-HARDWARE-001 — explicit re-evaluation

```text
CAPABILITY_CONSUMER_INVOKED       = YES  (plan_enterprise_hardware, 9.0.1.0858)
PINNED_BACKEND_EVIDENCE_AVAILABLE = YES, for the first time, and bounded:
                                    IE-2000 supports_vlan/layer2, 2911 layer3
PINNED_BACKEND_EVIDENCE_USED      = YES, by E5 authorisation
TD_HARDWARE_LITERAL_CRITERION     = NOT_SATISFIED
```

The literal criterion is about capability evidence reconciling **into eligible
physical hardware selection**, and selection in this run was still steered by
`HardwarePlanningPolicy.preferred_router_model="2911"`. The new evidence did
not decide which model was selected; it decided which actions were authorised
once a model had been selected. Those are different consumers, and only the
second one moved.

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

Baseline and final inventories match exactly — one zero-port
`Power Distribution Device0` in both, no semantic devices, no links. Independent
post-run re-observation in a separate process confirms it. No foreign,
pre-existing or backend-managed object was removed. The two probe devices from
the capability qualification were deleted by their own sessions before the run
began, and both sessions reported `inventory_restored = True`.

## Exit matrix

| # | Item | Result |
| --- | --- | --- |
| 1 | exact-version capability consumption attempted by the normal path | **PASS** — bound to 9.0.1.0858, measured evidence consumed, everything unmeasured still UNKNOWN |
| 2 | product-generated `TopologyPlan` | **PASS** |
| 3 | module effect containment | **PASS** — port effect VERIFIED both routers; identity and placement UNOBSERVABLE |
| 4 | fresh two-ended serial orientation | **PASS** — 4 pages per endpoint, complete |
| 5 | exactly one DCE and one DTE | **PASS** |
| 6 | typed E5 serial transit addressing | **PASS** — 4 routed interfaces VERIFIED from `show ip interface brief` |
| 7 | clock on the observed DCE only | **PASS** |
| 8 | independent clock readback | **PASS** |
| 9 | authentic foundational evidence | **NOT REACHED** |
| 10 | typed RIPv2 process state | **NOT REACHED** |
| 11 | typed learned-route readback | **NOT REACHED** |
| 12 | typed forwarding behaviour | **NOT REACHED** |
| 13 | semantic cleanup / restoration | **PASS** — verified by independent re-observation |

Row 1 moves from a bare YES to **PASS**, and row 6 from FAIL to **PASS**. Rows
2, 3, 4, 5, 7, 8 and 13 hold from run 4. Rows 9–12 are unchanged and remain
unreached.

Preserved unchanged:

```text
MODULE_IDENTITY  = UNOBSERVABLE
MODULE_PLACEMENT = UNOBSERVABLE
CABLE_IDENTITY   = UNOBSERVABLE
APPLIED         != VERIFIED
```

## What this does and does not establish

```text
E5_CAPABILITY_AUTHORIZATION_FROM_MEASURED_EVIDENCE = YES (first time)
E5_ACTIONS_APPLIED                     = 17 of 17
E5_CONFIGURATION_VERIFIED              = NO — 7 verified, 6 unobservable, 4 partial
REQUIRED_BATCH_PREFLIGHT               = ENFORCED (zero mutation on any required refusal)
BOUNDED_MULTI_PAGE_CAPTURE             = LIVE_QUALIFIED (second independent run)
FULL_PRODUCT_PIPELINE_ACCEPTANCE       = NOT_ESTABLISHED (unchanged)
CONTROL_PLANE_FOUNDATIONAL_REQUIREMENT_INTEGRATION = NOT_ESTABLISHED (unchanged)
TD_ACCEPTANCE_001                      = OPEN (unchanged; bounded shape, not the reference run)
TD_HARDWARE_001                        = OPEN (unchanged)
TD_MODULE_SLOT_001                     = BACKEND_LIMITATION (unchanged)
TD_CATALOG_PORT_001                    = RESOLVED (unchanged)
TD_ORIENTATION_PAGER_001               = RESOLVED (unchanged)
TD_CONFIG_CAPABILITY_001               = RESOLVED (closed by this run)
```

```text
MEG_5                  = NOT_OPENED
MEG_5_EXECUTION        = BLOCKED
REFERENCE_41_41_RUN    = NOT_EXECUTED
```

MEG-5 must not open. The bounded run still has to succeed, the access-port
read-back gap blocks it, and separately the reference topology's own models
have no measured capability or port evidence yet.
