# Stage 3A4 — MEG-4 bounded live qualification

Thirteen bounded runs plus the reference acceptance, all on
`feature/runtime-ripv2`, worktree `.claude/worktrees/runtime-ripv2`. **The
reference acceptance at the end of this document is the current state, and it
PASSES.** Bounded run 12 (reproduced by 13) closed MEG-4 and is kept below as
history. Every earlier run is left exactly as it was recorded — they are
history, not a summary of where things stand.

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

---

# Run 6 — 2026-08-18, after the foundation-scoped E5→E9 gate

## Outcome, stated first

```text
MEG_4_STATUS                  = FAILED / CLEAN
STOPPED_AT                    = control_plane_apply
LIVE_PACKET_TRACER_RUN        = YES
PHYSICAL_DEPLOYMENT           = VERIFIED
SERIAL_ORIENTATION            = VERIFIED  (4 pages per endpoint, third live capture)
E5_ACTIONS_APPLIED            = 17 of 17
REQUIRED_FOUNDATIONS          = 5 of 5 VERIFIED
RIPV2_APPLIED                 = YES, both routers
RIPV2_LEARNED_ROUTES_OBSERVED = YES, both routers, fresh
SEMANTIC_INVENTORY_RESTORED   = YES  (verified by independent re-observation)
E4_IDENTITY_PRESERVED         = YES
RAW_IOS_OR_JS_USED            = NONE
HARNESS_PERFORMED_A_MUTATION  = NO
```

**The control plane ran.** RIPv2 was applied through the typed product path on
both edge routers, `show ip protocols` read back a process matching the typed
intent field for field, and `show ip route rip` observed the far-side prefix
learned across the serial WAN. No earlier run reached E9 at all.

It stopped on one field, and the same field, in both control-plane
observations: `source_device_name`.

## Gates, in order

### G2 — same-process import isolation

```text
state              = ISOLATED
sys.executable     = <worktree>/.venv/Scripts/python.exe
loaded identities  = ['packet_tracer_mcp']          # exactly one
```

Run twice: the mutating process before its first mutation, and the independent
post-cleanup re-observation. `PT_MCP_GOVERNED_ROOT` process-local, never
persisted.

### G3 — process rediscovery, inventory, build, classification

Processes re-enumerated; no historical PID assumed.

```text
PID 16584  MainWindowHandle = 264778   <- GUI
PID  4212  MainWindowHandle = 0        <- helper
both       FileVersion = ProductVersion = 9.0.1.0858, same executable

inventory       = observed=True, semantic_devices=0, links=0,
                  backend_managed=1 ("Power Distribution Device0", zero ports)
classification  = DISPOSABLE
```

`BRIDGE_PEER_PROCESS_IDENTITY` and `BRIDGE_PEER_BUILD_SELF_REPORT` remain
`NOT_ATTESTED`, unchanged. No Packet Tracer API was guessed.

## What the foundation-scoped gate changed

Same shape, same hash, same capability evidence as run 5. The difference is
only which evidence decides:

```text
E5 aggregate                 = partial            (unchanged from run 5)
configuration_fully_verified = False              (stated explicitly, not implied)
E5 actions                   = 17 applied
E5 verifications             = 7 verified, 6 unobservable, 4 partial

required foundations, derived from the typed ControlPlanePlan:
    cfg/routed/d011557…        l3_interface   VERIFIED
    cfg/routed/f383b9e…        l3_interface   VERIFIED
    cfg/transit-l3/5273926…    l3_interface   VERIFIED
    cfg/transit-l3/e737d0e…    l3_interface   VERIFIED
    link/wan_link/23682ae…     link           VERIFIED

E9 preflight                 = passed, failure_code none, preflight_errors []
```

The six access-port and four endpoint-address statuses stayed exactly as
measured — `unobservable` and `partial` — and appear in
`foundational_statuses` at those values. None was promoted; none was required.

## The control plane, measured

```text
cp/ripv2/c3968dee…  A-EDGE-RTR-01   applied   batch A-EDGE-RTR-01:50
cp/ripv2/271fe98f…  B-EDGE-RTR-01   applied   batch B-EDGE-RTR-01:50

configured_status = compiled
applied_status    = applied
observed_status   = unobservable
behavior_status   = dependency_blocked
failover_status   = skipped
```

**Routing process, both routers**, from `fresh_show_ip_protocols`,
`fresh_evidence = true`:

```text
protocol            verified
version_send        verified
version_recv        verified
auto_summary        verified
networks            verified
passive_interfaces  verified
source_device_name  unobservable      <- the only one
message: "Fresh RIP state was compared semantically against the typed intent."
```

**Learned routes, both routers**, from `fresh_show_ip_route_rip`,
`fresh_evidence = true`:

```text
network             verified
prefix_length       verified
protocol            verified
source_device_name  unobservable      <- the only one
message: "Fresh RIP route rows matched the expected prefix after 1 read(s)."
```

RIPv2 genuinely converged: each router observed the other side's prefix as a
RIP route across the serial WAN, on a link whose DCE/DTE orientation this same
run established from a four-page controller capture. That is the strongest
control-plane evidence any run in this stage has produced.

## The defect this run found

`source_device_name` is part of both expectations' `expected` map, and neither
registered query reports it: `show ip protocols` and `show ip route rip` print
routing state, not the identity of the device that answered. So the field
resolves UNOBSERVABLE, and `_direct_observation` holds the aggregate at
UNOBSERVABLE because one field of the claim was not observed.

**Narrowing is not available, by design.**
`enterprise_control_plane_runtime.py:1398-1413` folds `unclaimed_fields` into
the unobservable map precisely so that shrinking an expectation cannot make
`_direct_observation` see "all fields verified" and raise the conclusion
without observing anything new. That guard is correct and was not touched.

The forwarding expectation then reported `dependency_blocked` —
`Blocked by: verification_verified:cp/verify-rip-route/…` — so typed end-to-end
behaviour was never attempted. That is the prerequisite gate working: it will
not ping to manufacture evidence for a route claim that did not close.

**Not worked around.** Substituting the device this process *asked* for the
device the output *claims* would be exactly the substitution the evidence
discipline forbids, and dropping the field from the expectation is the
narrowing the runtime explicitly refuses. Recorded as the next blocker rather
than repaired here.

This is the same shape as the decision taken one layer up, one layer down: an
observation whose every semantic field is verified is held at UNOBSERVABLE by a
field the backend does not expose. Whether the right answer is an evidence-
bearing device-identity read, or an explicit claim ceiling for these two
queries, is a governed decision and is **not** taken in this run.

## Module and orientation evidence, unchanged

```text
module port effect     VERIFIED, both routers
module identity        UNOBSERVABLE
module placement       UNOBSERVABLE
serial orientation     A-EDGE-RTR-01 dce (4 pages, completed)
                       B-EDGE-RTR-01 dte (4 pages, completed)
CAN_PACKET_TRACER_AUTHENTICALLY_QUALIFY_MODULE_REPLAY_CONTAINMENT = NO
```

## G4 — cleanup and restoration

```text
cleanup entries    = 8, all applied, reverse order, exactly the planned names
inventory_restored = True
control-plane dirty_state = unknown
```

Independent post-run re-observation, separate process:

```text
semantic_device_count = 0
link_count            = 0
backend_managed       = 2  ("Power Distribution Device0", "Power Distribution
                            Device1"), both zero ports
```

**A second power-distribution object appeared during this run** and is recorded
rather than smoothed over: baseline carried one, the final inventory carries
two. Both are backend-created, zero-port, and exactly what
`disposable_workspace_error` tolerates. No foreign, pre-existing or
backend-managed object was removed. `SEMANTIC_INVENTORY_RESTORED` is claimed
for the semantic inventory, which is what the restoration comparison covers.

`dirty_state = unknown` on the control-plane result is the honest value for a
fire-and-forget configuration channel and is unchanged from its recorded
meaning; it is not evidence of residue, and the independent re-observation is
what establishes the workspace state.

## Exit matrix

| # | Item | Result |
| --- | --- | --- |
| 1 | exact-version capability consumption by the normal path | **PASS** |
| 2 | product-generated `TopologyPlan` | **PASS** |
| 3 | module effect containment | **PASS** |
| 4 | fresh two-ended serial orientation | **PASS** |
| 5 | exactly one DCE and one DTE | **PASS** |
| 6 | typed E5 serial transit addressing | **PASS** |
| 7 | clock on the observed DCE only | **PASS** |
| 8 | independent clock readback | **PASS** |
| 9 | authentic foundational evidence | **PASS** — 5 of 5 declared foundations VERIFIED from `apply_configuration` read-back, and the E9 gate decided on them |
| 10 | typed RIPv2 process state | **PARTIAL** — every semantic field verified on both routers; aggregate held UNOBSERVABLE by `source_device_name` |
| 11 | typed learned-route readback | **PARTIAL** — prefix, length and protocol verified on both routers; same single field |
| 12 | typed forwarding behaviour | **NOT REACHED** — dependency-blocked by row 11 |
| 13 | semantic cleanup / restoration | **PASS** — verified by independent re-observation |

Row 9 moves NOT REACHED → **PASS** and rows 10 and 11 NOT REACHED → **PARTIAL**,
all three for the first time.

## What this does and does not establish

```text
FOUNDATION_SCOPED_GATE_EXERCISED_LIVE  = YES
REQUIRED_FOUNDATIONS_VERIFIED          = 5 of 5
RIPV2_APPLIED_THROUGH_THE_PRODUCT      = YES (both routers, typed path)
RIPV2_PROCESS_SEMANTICS_OBSERVED       = YES (every claimed field but one)
RIPV2_LEARNED_ROUTES_OBSERVED          = YES (both routers, fresh, matched)
TYPED_FORWARDING_OBSERVED              = NO  (dependency-blocked, not attempted)
CONFIGURATION_FULLY_VERIFIED           = NO  (stated explicitly in the result)
FULL_PRODUCT_PIPELINE_ACCEPTANCE       = NOT_ESTABLISHED (unchanged)
CONTROL_PLANE_FOUNDATIONAL_REQUIREMENT_INTEGRATION = NOT_ESTABLISHED (unchanged)
TD_ACCEPTANCE_001                      = OPEN (unchanged; bounded shape, not the reference run)
TD_HARDWARE_001                        = OPEN (unchanged)
TD_MODULE_SLOT_001                     = BACKEND_LIMITATION (unchanged)
TD_CATALOG_PORT_001                    = RESOLVED (unchanged)
TD_ORIENTATION_PAGER_001               = RESOLVED (unchanged)
TD_CONFIG_CAPABILITY_001               = RESOLVED (unchanged)
TD_ACCESSPORT_READBACK_001             = OPEN, no longer blocking MEG-4
```

```text
MEG_5                  = NOT_OPENED
MEG_5_EXECUTION        = BLOCKED
REFERENCE_41_41_RUN    = NOT_EXECUTED
```

MEG-5 must not open. The bounded run still has to succeed, rows 10–12 are not
closed, and the reference topology's own models still have neither measured
capability evidence nor measured port inventories.

---

# Run 7 — 2026-08-19, first run with execution-envelope provenance

## Outcome, stated first

```text
MEG_4_STATUS                  = FAILED / CLEAN
STOPPED_AT                    = control_plane_apply
HEAD                          = ad5b8fe
LIVE_PACKET_TRACER_RUN        = YES
PHYSICAL_DEPLOYMENT           = VERIFIED
SERIAL_ORIENTATION            = VERIFIED  (4 pages per endpoint)
E5_ACTIONS_APPLIED            = 17 of 17
REQUIRED_FOUNDATIONS          = VERIFIED
RIPV2_APPLIED                 = YES, both routers
SOURCE_DEVICE_NAME            = VERIFIED on 3 of 4 observations
SEMANTIC_INVENTORY_RESTORED   = YES
E4_IDENTITY_PRESERVED         = YES
RAW_IOS_OR_JS_USED            = NONE
HARNESS_PERFORMED_A_MUTATION  = NO
```

`physical_topology_hash = 1d2324aa7cf334584f2b6ecb27791e113676a5076a54c7c5c32285ca22d67692`,
unchanged from runs 3-6. Duration 42 s.

## What the provenance change did

`source_device_name` was VERIFIED for the first time — on both learned-route
observations and on one of the two routing-process observations:

```text
cp/verify-rip-process/f988ae8c   verified     source_device_name verified
cp/verify-rip-route/5d922032     verified     source_device_name verified
cp/verify-rip-route/90182acd     verified     source_device_name verified
cp/verify-rip-process/ee78a086   unobservable source_device_name unobservable   <- the gap
```

No name was ever substituted. The one that did not close reported exactly what
it measured: the session was not uniquely attributed, so the field stayed
UNOBSERVABLE.

## The defect this run found

The attribution predicate required a candidate device's transcript to **start
with** the baseline captured at dispatch. This repository had already measured
that a fresh session need not: `fresh_command_window`
(`command_dispatch.py:215-245`) names two cases where `after` stops beginning
with `before` and is still fresh and attributable — IOS erases its `--More--`
on leaving the pager, and a long buffer rolls off the head. A strict prefix
rejects exactly those reads, and `show ip protocols` is read with the pager
permitted.

Fixed at `38e4a8c` by anchoring on the **retained suffix** instead — the
trailing 512 characters of the baseline, whitespace-trimmed — and additionally
requiring the dispatched command to appear behind that anchor. That is strictly
more discriminating than the rule it replaces, not looser: an idle twin router
no longer qualifies by sharing a boot banner.

## Also surfaced

With both learned-route claims closed, the forwarding expectation stopped being
`dependency_blocked` and reached the next gate:

```text
cp/verify-flow-reachability/1a2c4b34  behavior  unobservable
    evidence_method = control_plane_capability_gate
    message         = "2911:routing_behavior is unknown."
```

The verification-prerequisite gate is satisfied. What now blocks typed
forwarding is capability evidence, not provenance.

---

# Run 8 — 2026-08-19, after the retained-suffix anchor

## Outcome, stated first

```text
MEG_4_STATUS                  = FAILED / CLEAN
STOPPED_AT                    = control_plane_apply
HEAD                          = 38e4a8c
LIVE_PACKET_TRACER_RUN        = YES
PHYSICAL_DEPLOYMENT           = VERIFIED   (status verified, dirty_state clean)
SERIAL_ORIENTATION            = VERIFIED   (A-EDGE-RTR-01 dce @ 2000000 bps,
                                            B-EDGE-RTR-01 dte; 4 pages each,
                                            pagination completed)
E5_ACTIONS_APPLIED            = 17 of 17
E5_AGGREGATE                  = partial / observability_limitation
CONFIGURATION_FULLY_VERIFIED  = NO         (stated explicitly)
REQUIRED_FOUNDATIONS          = VERIFIED   (4 x l3_interface + 1 x link)
E9_OBSERVED_STATUS            = VERIFIED   <- first time
RIPV2_PROCESS_AGGREGATE       = VERIFIED, both routers
LEARNED_ROUTE_AGGREGATE       = VERIFIED, both routers
SOURCE_DEVICE_NAME            = VERIFIED on 4 of 4 observations
TYPED_FORWARDING              = UNOBSERVABLE / capability gate
SEMANTIC_INVENTORY_RESTORED   = YES  (independent re-observation, separate process)
E4_IDENTITY_PRESERVED         = YES
RAW_IOS_OR_JS_USED            = NONE
HARNESS_PERFORMED_A_MUTATION  = NO
NO_PKT_SAVED                  = YES
```

Duration 43 s. Same hash, same shape, same 17 E5 actions as runs 3-7.

## The control plane, measured

```text
configured = compiled   applied = applied   observed = VERIFIED
behavior   = unobservable          failover = skipped
```

All four observations, `fresh_evidence = true`:

```text
cp/verify-rip-process/ee78a086  verified  fresh_show_ip_protocols
    protocol, version_send, version_recv, auto_summary, networks,
    passive_interfaces, source_device_name   -- all verified
cp/verify-rip-process/f988ae8c  verified  fresh_show_ip_protocols
    same seven fields, all verified
cp/verify-rip-route/5d922032    verified  fresh_show_ip_route_rip
    network, prefix_length, protocol, source_device_name -- all verified
    convergence: 1 read, last_observable_state 10.0.0.8/29
cp/verify-rip-route/90182acd    verified  fresh_show_ip_route_rip
    same four fields, all verified
    convergence: 1 read, last_observable_state 10.0.0.0/29
```

`source_device_name` is established by execution provenance, never by the
requested name. The output that was parsed and the device it is attributed to
come from the same enumeration pass, so evidence and provenance cannot
originate on different devices.

## The blocker this run leaves

```text
cp/verify-flow-reachability/1a2c4b34  end_to_end_reachability  behavior
    status          = unobservable
    evidence_method = control_plane_capability_gate
    fields          = {capability: unobservable}
    message         = "2911:routing_behavior is unknown."
```

`infrastructure/catalog/control_plane_capabilities.py` grants `2911` only
`RIPV2_CONFIG`, `ROUTING_PROCESS_STATE` and `ROUTING_ROUTE_STATE`, each from a
model-attributed live qualification. `ROUTING_BEHAVIOR` is UNKNOWN because no
live measurement of forwarding behaviour has ever been attributed to this
model, and that catalogue refuses to claim a dimension without one.

**Not worked around.** Adding the dimension to the catalogue, or admitting
UNKNOWN into `_RUNNABLE_CAPABILITIES`, would fabricate exactly the
model-attributed evidence the gate exists to require. Invoking the ping
directly would bypass the product path. Recorded as the next blocker; the
decision about how first-time behaviour evidence may be obtained is **not**
taken in this run.

## G4 — cleanup and restoration

```text
cleanup entries    = 8, all applied, exactly the planned names
inventory_restored = True
```

Independent post-run re-observation, separate process with its own G2:

```text
semantic_device_count = 0
link_count            = 0
backend_managed       = 2  (both "Power Distribution Device", zero ports)
```

Unchanged from this run's baseline — unlike run 6, no additional
power-distribution object appeared.

## Exit matrix

| # | Item | Result |
| --- | --- | --- |
| 1 | exact-version capability consumption by the normal path | **PASS** |
| 2 | product-generated `TopologyPlan` | **PASS** |
| 3 | module effect containment | **PASS** |
| 4 | fresh two-ended serial orientation | **PASS** |
| 5 | exactly one DCE and one DTE | **PASS** |
| 6 | typed E5 serial transit addressing | **PASS** |
| 7 | clock on the observed DCE only | **PASS** |
| 8 | independent clock readback | **PASS** |
| 9 | authentic foundational evidence | **PASS** |
| 10 | typed RIPv2 process state | **PASS** — every claimed field verified on both routers, aggregate VERIFIED |
| 11 | typed learned-route readback | **PASS** — every claimed field verified on both routers, aggregate VERIFIED |
| 12 | typed forwarding behaviour | **NOT REACHED** — `2911:routing_behavior` is UNKNOWN |
| 13 | semantic cleanup / restoration | **PASS** — verified by independent re-observation |

Rows 10 and 11 move PARTIAL to **PASS**, both for the first time.

## What this does and does not establish

```text
CONTROL_PLANE_SOURCE_PROVENANCE        = ESTABLISHED (4 of 4, live)
RIPV2_PROCESS_SEMANTICS_OBSERVED       = YES, aggregate VERIFIED
RIPV2_LEARNED_ROUTES_OBSERVED          = YES, aggregate VERIFIED
TYPED_FORWARDING_OBSERVED              = NO (capability gate, not attempted)
CONFIGURATION_FULLY_VERIFIED           = NO
FULL_PRODUCT_PIPELINE_ACCEPTANCE       = NOT_ESTABLISHED (unchanged)
TD_ACCEPTANCE_001                      = OPEN (unchanged)
TD_HARDWARE_001                        = OPEN (unchanged)
TD_MODULE_SLOT_001                     = BACKEND_LIMITATION (unchanged)
TD_CATALOG_PORT_001                    = RESOLVED (unchanged)
TD_ORIENTATION_PAGER_001               = RESOLVED (unchanged)
TD_CONFIG_CAPABILITY_001               = RESOLVED (unchanged)
TD_ACCESSPORT_READBACK_001             = OPEN, still not blocking MEG-4
```

```text
MEG_5                  = NOT_OPENED
MEG_5_EXECUTION        = BLOCKED
REFERENCE_41_41_RUN    = NOT_EXECUTED
```

---

# Run 9 — 2026-08-19, after the reachability field accounting

## Outcome, stated first

```text
MEG_4_STATUS                  = FAILED / CLEAN
STOPPED_AT                    = control_plane_apply
HEAD                          = 4803f5e
LIVE_PACKET_TRACER_RUN        = YES
PHYSICAL_DEPLOYMENT           = VERIFIED   (dirty_state clean)
SERIAL_ORIENTATION            = VERIFIED
E5_ACTIONS_APPLIED            = 17 of 17
CONFIGURATION_FULLY_VERIFIED  = NO
E9_OBSERVED_STATUS            = VERIFIED
RIPV2_PROCESS_AGGREGATE       = VERIFIED, both routers
LEARNED_ROUTE_AGGREGATE       = VERIFIED, both routers
SOURCE_DEVICE_NAME            = VERIFIED, 4 of 4 observations
FORWARDING_GATE               = control_plane_capability_gate
TYPED_FORWARDING              = UNOBSERVABLE — "2911:routing_behavior is unknown."
SEMANTIC_INVENTORY_RESTORED   = YES  (independent re-observation, separate process)
E4_IDENTITY_PRESERVED         = YES
RAW_IOS_OR_JS_USED            = NONE
HARNESS_PERFORMED_A_MUTATION  = NO
NO_PKT_SAVED                  = YES
```

Same hash `1d2324aa…`, same shape, 43 s. This run exists to prove the field
accounting and shared-provenance changes regressed nothing live, and to record
that the gate is unchanged. It did not move any exit-matrix row.

## The gate is not circular — traced, not assumed

The question put to this session was whether `routing_behavior` must be known
before running the measurement that produces `routing_behavior` evidence. It
does not, because the dimension is not the result.

```text
required_capability   = what authorises EXECUTING the measurement
expected / fields     = what the measurement ESTABLISHES
```

The whole behaviour family is built that way, and the pattern is uniform:

```text
STP_BEHAVIOR           expected {loop_free, forwarding_converged}
ETHERCHANNEL_BEHAVIOR  expected {reachable, bundled}
HSRP_BEHAVIOR          expected {...}
ROUTING_BEHAVIOR       expected {traffic_flow_id, destination_ipv4,
                                 reachable, protocol}
```

`LINK_FAILURE_CONTROL` is the same shape one step further: a *control* channel
required to induce a fault, separate from the `*_FAILOVER` dimension that
authorises observing the result. So requiring `ROUTING_BEHAVIOR` before pinging
asks "may this model be measured this way", not "does it already forward".
`docs/architecture/stage-3a4-serial-product-slice-2b.md:96` states the same
split in words: the expectation "keeps its own `ROUTING_BEHAVIOR` dimension and
its own `reachable`, satisfied only by a typed ping".

**The gate is preserved.** No dimension was promoted, no model hardcoded,
`_RUNNABLE_CAPABILITIES` is untouched at `{SUPPORTED, PARTIAL}`, and
regressions now pin all three.

## The actual missing evidence producer

Traced end to end: `packet_tracer_control_plane_capabilities` is the **only**
producer of control-plane capability profiles in the product. There is no
runtime discovery path for any control-plane dimension — E3.5
`CapabilityDiscoveryService` produces hardware dimensions (`supports_vlan`,
`layer3`, model identity), not these. Every dimension `2911` holds today was
established out of band, by a governed live qualification, and then encoded:
`docs/architecture/ripv2-runtime-qualification.md` is cited in the catalogue
for exactly that reason.

So the producer path exists and is not blocked by the gate — it runs outside
it. `ControlPlaneApplicator.__init__` even carries the injection seam
(`capability_provider`) such a qualification would feed.

What is missing is a governed live qualification of **forwarding** on `2911`,
attributed to model and build, of the same kind that produced the three
dimensions already granted. Noted and deliberately not acted on: R2-B phase 4
already records forwarding rows on 2911 / `9.0.1.0858` — endpoint-to-endpoint
4/4 each way, and router-to-router 5/5 across the WAN, the latter measured
before RIP existed. Whether those rows qualify **this** dimension, whose gate
protects the typed product measurement channel, is a claim-scope decision. It
is not taken here, and nothing was promoted on the strength of it.

## A second ceiling, now visible rather than hidden

Fixing the reachability observer's field accounting exposed a ceiling that the
old hand-built `fields` map had been concealing. The observer claimed four
fields and reported one:

```text
before   fields = {reachable}                       aggregate could reach VERIFIED
after    fields = {traffic_flow_id, destination_ipv4, reachable,
                   protocol, source_device_name}
```

`reachable` is measured and `source_device_name` is certified from execution
provenance, fail-closed. `protocol` and `traffic_flow_id` are reported
UNOBSERVABLE, because an ICMP echo observes neither which protocol installed
the route nor which compiled flow the claim belongs to. The route prerequisite
orders that evidence and, by this stage's stated contract, does not substitute
for it.

**Consequence, stated plainly.** With honest accounting a reachability
expectation cannot reach VERIFIED today, so MEG-4 row 12 now has two
independent blockers rather than one:

```text
1. capability   2911:routing_behavior is UNKNOWN — needs the governed
                qualification described above
2. claim ceiling  protocol / traffic_flow_id are not observable from a typed
                ping — needs a governed decision on what a behaviour
                expectation may claim
```

Neither was created by this session; the second was previously invisible
because the fields were dropped instead of reported. Recorded as a ceiling, not
repaired by narrowing.

## G4 — cleanup and restoration

```text
cleanup entries    = 8, all applied
inventory_restored = True
```

Independent post-run re-observation, separate process with its own G2:
`semantic_device_count = 0`, `link_count = 0`, `backend_managed = 2`, both
zero-port Power Distribution Devices — unchanged from this run's baseline.

## Exit matrix — unchanged from run 8

Rows 1–11 and 13 **PASS**; row 12 **NOT REACHED**, now for two recorded
reasons rather than one.

```text
MEG_5                  = NOT_OPENED
MEG_5_EXECUTION        = BLOCKED
REFERENCE_41_41_RUN    = NOT_EXECUTED
```

---

# Run 10 — 2026-08-19, typed forwarding executes for the first time

## Outcome, stated first

```text
MEG_4_STATUS                  = FAILED / CLEAN
STOPPED_AT                    = control_plane_apply
HEAD                          = 60ef5c7
E9_STATUS                     = partial / verification_failed
E9_OBSERVED_STATUS            = VERIFIED
E9_BEHAVIOR_STATUS            = FAILED        <- measured, not gated
TYPED_FORWARDING              = EXECUTED and MEASURED reachable=False
SEMANTIC_INVENTORY_RESTORED   = YES  (independent re-observation, separate process)
E4_IDENTITY_PRESERVED         = YES
RAW_IOS_OR_JS_USED            = NONE
HARNESS_PERFORMED_A_MUTATION  = NO
NO_PKT_SAVED                  = YES
```

Same hash `1d2324aa…`, 17 of 17 E5 actions applied, all four control-plane
observations VERIFIED as in runs 8 and 9. Duration 56 s.

## The measurement

`2911:routing_behavior` is SUPPORTED as of the R3 qualification, so the gate
authorised the measurement and the product ran it:

```text
cp/verify-flow-reachability/1a2c4b34  end_to_end_reachability  behavior
    status          = failed
    evidence_method = typed_ping_current_command_window
    fresh_evidence  = true
    fields = {traffic_flow_id:  unobservable,
              destination_ipv4: verified,
              reachable:        failed,
              protocol:         verified,
              source_device_name: verified}
    message = "Fresh typed ping differed from reachable=True."
    convergence: attempts=1, last_observable_state=reachable=False
```

**The measurement itself is sound and says so field by field.** The session was
attributed to the claimed source device, the executor confirmed it dispatched
and echoed the claimed destination, and the protocol matched the RIPv2 action
actually applied. What failed is `reachable`: the fresh typed ping measured
`False` where the flow claims `True`.

One attempt is correct here and is not a thinness of the measurement.
`TypedPingExecutor.ping` retries only while no attributable window exists — "un
resultado fresco, alcanzable o no, se devuelve de inmediato: el reintento busca
evidencia atribuible, nunca un resultado favorable". Retrying a fresh
`reachable=False` until it turned true would be manufacturing the result.

`traffic_flow_id` stays UNOBSERVABLE, unchanged: it is the label the compiler
attaches to the claim, read by no code, and the only registered command is
`ping <ip>`, which returns nothing that could carry it.

## What this establishes, and what it does not

```text
FORWARDING_MEASUREMENT_CHANNEL   = WORKS on this model and build (R3, then live here)
FORWARDING_MEASURED              = YES, first time in this stage
FORWARDING_SUCCEEDED             = NO
CAUSE_OF_THE_FAILURE             = NOT ESTABLISHED by this run
```

The claim is deliberately narrow. The measurement ran and returned a negative;
this run did not diagnose why.

## Where the failure sits, from evidence already in this run

The measured path is `A-EDGE-RTR-01 → serial WAN → B-EDGE-RTR-01 → access
switch → PC`, because `_destination_address_for` prefers a static endpoint in
the destination site over the far router's own interface — deliberately, so the
claim covers the whole path rather than stopping at the edge.

Every hop this stage **can** observe is verified:

```text
serial orientation      VERIFIED  (one DCE @ 2000000 bps, one DTE)
transit + routed L3     VERIFIED  (4 of 4 foundations)
RIPv2 process           VERIFIED  both routers
learned routes          VERIFIED  both routers, far-side prefix across the WAN
endpoint ipv4/netmask   VERIFIED  all four PCs
```

The hops it **cannot** observe are exactly the remaining ones:

```text
access-port VLAN membership   UNOBSERVABLE   TD-ACCESSPORT-READBACK-001, OPEN
endpoint gateway              UNOBSERVABLE   no PT getter evidence exists
```

The gateway is applied (`configurePcIp(..., gateway, ...)`) and the access
ports are applied, but neither is readable in this backend, so neither can be
confirmed or excluded as the cause. **No cause is claimed here.** Isolating it
needs access-port read-back — its own governed work item, explicitly out of
this session's scope — or a diagnostic run designed to observe that segment.

## G4 — cleanup and restoration

```text
cleanup entries    = 8, all applied
inventory_restored = True
```

Independent post-run re-observation, separate process with its own G2:
`semantic_device_count = 0`, `link_count = 0`, `backend_managed = 0`.

## Exit matrix

Rows 1–11 and 13 unchanged (**PASS**). Row 12 moves NOT REACHED → **FAIL**:
typed forwarding was measured for the first time and did not reach the
destination. That is a stronger, worse and more useful result than not
measuring at all.

```text
MEG_5                  = NOT_OPENED
MEG_5_EXECUTION        = BLOCKED
REFERENCE_41_41_RUN    = NOT_EXECUTED
```

# Run 11 — 2026-08-19, the simulation trace localizes the negative

## Outcome, stated first

```text
MEG_4_STATUS        = FAILED / CLEAN
STOPPED_AT          = control_plane_apply
HEAD                = bd04b5a
TYPED_FORWARDING    = EXECUTED, reachable measured False (as in runs 10)
TRACE_COMPLETE      = YES   89 frames, simulation_mode confirmed
CAUSE               = ESTABLISHED, for the first time
REALTIME_RESTORED   = YES
NO_PKT_SAVED        = YES
```

Same hash `1d2324aa`, same 17 of 17 E5 actions, same four control-plane
observations, same `reachable=False`. What is new is that the product invoked
the pre-cleanup diagnostic and Packet Tracer said what happened.

## What the trace measured

Correlated to the run's own compiled flow, not to a historical one:

```text
PING_SOURCE           = A-EDGE-RTR-01
PING_DESTINATION      = 10.0.0.10
EXPECTATION_ID        = cp/verify-flow-reachability/1a2c4b34322ee7f0
SIM_MODE              = entered (before=False, after=True), reset to 0 frames
SIM_STEP              = 1 -> 89 frames
TRACE                 = observed, simulation_mode=True, 89 hops
FIRST_FAILING_DEVICE  = B-EDGE-RTR-01
FIRST_FAILING_PORT    = in=Serial0/0/0
FIRST_FAILING_LAYER   = 2   (the decision PT attributes to the ARP process)
PT_DECISION           = "The next-hop IP address is not in the ARP table. The
                         ARP process tries to send an ARP request for that IP
                         address and drops this packet."
```

And then, in the same event list:

```text
idx 2..7    ARP broadcast   B-EDGE-RTR-01 -> switch -> B-DEFAULT-PC-01 -> back
            "The ARP process updates the ARP table with received information."
idx 16..21  ICMP echo       A-RTR -> serial -> B-RTR -> switch -> B-PC -> back
idx 22      A-EDGE-RTR-01   "The Ping process received an Echo Reply message."
```

**The path works.** The access ports bridge the frames, the endpoint answers,
and its reply routes back across the WAN. The first echo is lost to ARP, which
is ordinary, and the ones after it are not.

## What that does and does not establish

```text
FORWARDING_PATH_FUNCTIONAL_AT_TRACE_TIME = YES, by PT's own decision log
ACCESS_PORT                              = UNOBSERVABLE  (unchanged)
ENDPOINT_GATEWAY                         = UNOBSERVABLE  (unchanged)
```

Neither is promoted, and the trace is not evidence for either. A frame crossing
a switch is not a reading of a port's VLAN, and a host replying is not a
reading of its default gateway. The gap named in run 10 is exactly as open as
it was; what changed is that it is no longer a *suspect*, because the segment it
owns was observed carrying traffic.

## The defects this run found

Two, both in the product, neither in the network.

**1. The forwarding measurement had no convergence window.** Every other
observation in `PacketTracerEnterpriseControlPlaneRuntime` that depends on a
plane that converges already had a bounded re-read: `_observe_rip_route`
retries up to 45 s because RIP advertises every 30 s. The reachability
measurement — which depends on RIP *plus* ARP on the destination LAN *plus* a
just-created access switch — was taken exactly once, immediately after apply.
Run 11 measured `False` at t≈0 and the trace measured Echo Replies ~30 s later
over the same unchanged topology.

**2. `traffic_flow_id` was accounted as a device property.** It is the
compiler's label for which intent flow the claim covers; no registered query can
return it, because the only command is `ping <ip>`. Inside `expected` it
rendered UNOBSERVABLE on every reachability observation, so the aggregate could
never be VERIFIED no matter what the network did — and `_overall` turns a single
UNOBSERVABLE into PARTIAL, which is what `execute_enterprise_reference` gates
E9 on.

Both are fixed in `14854bf`, with regressions that pin the discipline: the
window stops on **agreement**, not on a favourable answer, and moving the label
to `source_traffic_flow_id` narrows nothing — the four claimed device
properties are exactly the previous four, and putting the label back into
`expected` makes it count again.

## G4

```text
cleanup entries    = 8, all applied
inventory_restored = True
REALTIME_RESTORED  = YES (set_simulation_mode(False), observed after=False)
```

---

# Run 12 — 2026-08-19, MEG-4 PASSES

## Outcome, stated first

```text
MEG_4_STATUS                  = PASS
HEAD                          = 14854bf
STATUS / STOPPED_AT           = completed / completed
DURATION                      = 65.5 s
E9_STATUS                     = VERIFIED
TYPED_FORWARDING              = VERIFIED   reachable=True after 2 bounded
                                measurements; nothing redispatched
SEMANTIC_INVENTORY_RESTORED   = YES  (independent re-observation, separate process)
E4_IDENTITY_PRESERVED         = YES
RAW_IOS_OR_JS_USED            = NONE
HARNESS_PERFORMED_A_MUTATION  = NO
NO_PKT_SAVED                  = YES
ERRORS                        = []
```

Confirmed by a second run (**run 13**, 65.1 s) with the same result, same two
bounded measurements, same restoration. The pass is reproducible, not a
one-off.

## The measurement that closes row 12

```text
cp/verify-flow-reachability/1a2c4b34322ee7f0  end_to_end_reachability  behavior
    status          = verified
    evidence_method = typed_ping_current_command_window
    fresh_evidence  = true
    fields = {destination_ipv4: verified, protocol: verified,
              reachable: verified, source_device_name: verified}
    message = "Fresh typed ping matched reachable=True after 2 bounded
               measurement(s)."
    convergence: attempts=2, last_observable_state=reachable=True
```

Two measurements, not one — and the second is the first that agreed. That is
the defect run 11 found, measured closing.

The pre-cleanup diagnostic ran and reported `no_failing_reachability_observation`:
there was no negative to localize, so it never entered Simulation mode. Packet
Tracer stayed in Realtime for the whole run.

## Control plane, in full

```text
cp/verify-rip-process   x2   VERIFIED   protocol, version_send, version_recv,
                                        networks, passive_interfaces,
                                        auto_summary, source_device_name
cp/verify-rip-route     x2   VERIFIED   network, prefix_length, protocol,
                                        source_device_name
cp/verify-flow-reach    x1   VERIFIED   as above
CONTROL_PLANE_STATUS         = VERIFIED
```

## What is deliberately still not VERIFIED

```text
CONFIGURATION_STATUS         = partial
CONFIGURATION_FULLY_VERIFIED = NO
ACCESS_PORT                  = UNOBSERVABLE   x6, TD-ACCESSPORT-READBACK-001 OPEN
ENDPOINT_STATIC              = PARTIAL        x4 (gateway unreadable)
```

Unchanged and preserved. The E5→E9 gate is foundation-scoped (run 6), and every
declared foundation is VERIFIED: four L3 interfaces, two VLANs, the serial clock
and all seven links. **MEG-4 passing does not close `TD-ACCESSPORT-READBACK-001`
and does not make the endpoint gateway observable.** Forwarding was measured
behaviourally; neither field was read.

## G4 — cleanup and restoration

```text
cleanup entries    = 8, all applied
inventory_restored = True
```

Independent post-run re-observation, separate process with its own G2:

```text
G2                    = ISOLATED
semantic_device_count = 0
link_count            = 0
backend_managed       = 1  ("Power Distribution Device0", zero ports)
simulation_mode       = before=False   (Realtime confirmed, not merely set)
```

## Exit matrix

| # | Item | Result |
| --- | --- | --- |
| 1 | exact-version capability consumption by the normal path | **PASS** |
| 2 | product-generated `TopologyPlan` | **PASS** |
| 3 | module effect containment | **PARTIAL** — port effect verified; slot placement unobservable (`TD-MODULE-SLOT-001`, backend limitation) |
| 4 | fresh two-ended serial orientation | **PASS** |
| 5 | exactly one DCE and one DTE | **PASS** |
| 6 | typed E5 serial transit addressing | **PASS** |
| 7 | clock on the observed DCE only | **PASS** |
| 8 | independent clock readback | **PASS** |
| 9 | authentic foundational evidence | **PASS** |
| 10 | typed RIPv2 process state | **PASS** |
| 11 | typed learned-route readback | **PASS** |
| 12 | typed forwarding behaviour | **PASS** — verified, reproducibly |
| 13 | semantic cleanup / restoration | **PASS** — verified by re-observation |

```text
MEG_5                  = NOT_OPENED
MEG_5_EXECUTION        = BLOCKED (not opened in this session)
REFERENCE_41_41_RUN    = NOT_EXECUTED
```


# Reference acceptance — 2026-08-19, 41/41 through the product, first run

This is the run `TD-ACCEPTANCE-001` was written for. It is **not** a MEG-4 or
MEG-5 result and nothing here is inferred from either: those closed the bounded
slice and the model qualification respectively, and this is the reference.

## Outcome, stated first

```text
REFERENCE_RESULT              = PASS
HEAD                          = cd6272d
STATUS / STOPPED_AT           = completed / completed
DURATION                      = 162.4 s
SAME_RUN                      = YES (one call to execute_enterprise_reference;
                                no evidence combined from any other attempt)
ATTEMPTS                      = 1 (first run; no defect required fixing)
E4_IDENTITY_PRESERVED         = YES
RAW_IOS_OR_JS_USED            = NONE on the product path
HARNESS_PERFORMED_A_MUTATION  = NO
NO_PKT_SAVED                  = YES
ERRORS                        = []
```

## Gates

```text
G2  ISOLATED, loaded_identities = ['packet_tracer_mcp'] (exactly one)
G3  observed=True, semantic_devices=0, links=0, backend_managed=3
    message = fresh_complete_workspace_inventory
G4  cleanup=41, all applied, inventory_restored=True
```

Independent post-run re-observation, separate process with its own G2:

```text
semantic_device_count = 0
link_count            = 0
backend_managed       = 3  (Power Distribution Device0..2, zero ports)
simulation_mode       = before=False  (Realtime confirmed by reading it)
```

## The topology, derived from the typed plan rather than assumed

```text
DEVICE_COUNT           = 41
LINK_COUNT             = 41   (38 straight, 3 serial)
MODELS                 = 1941 x3, 2950T-24 x2, IE-2000 x1, PC-PT x35
REQUIRED_MODULE_STATES = HWIC-2T @ 0/0, x3
physical_topology_hash = d34103311e097ef914c8742626edbff348fd0015e8a0551afda381c33a8d6cf0
```

Hardware came from capability-driven selection over the whole catalogue, with no
`preferred_router_model` steering and no hand-pinned candidates.

## Stage by stage, from the run's own result

```text
DEPLOY   status=verified  dirty_state=clean  items=85 (41 devices + 41 links + 3 modules)
         manifest: 41 device bindings, 41 link bindings,
                   identity_methods = {composite_fingerprint: 41}
                   semantic_hash a48c63ed...
ORIENT   verified=True, errors=[]
E5       88 of 88 actions APPLIED
         verification: 15 verified / 38 unobservable / 35 partial
         aggregate = partial   <- truthful, and preserved deliberately
FOUND    12 required foundations declared by the control plane
         (9 l3_interface + 3 link), all VERIFIED before the runtime was touched
E9       status=verified  applied=applied  observed=verified  behavior=verified
```

### E9 in full

```text
3 x configure_ripv2                       APPLIED
3 x routing_process    VERIFIED  fresh_show_ip_protocols, 7 fields each
9 x route_present      VERIFIED  fresh_show_ip_route_rip, first read each
      learned prefixes observed: 10.0.0.0/27, 10.0.0.32/27, 10.0.0.64/28,
                                 10.0.0.80/30, 10.0.0.84/30, 10.0.0.88/30
1 x end_to_end_reachability  VERIFIED  typed_ping_current_command_window
      reachable=True after 1 bounded measurement
      fields: destination_ipv4, protocol, reachable, source_device_name
```

Nine learned routes across three routers and three serial WAN links, each read
fresh and matched against prefixes derived from the E5 L3 identities — not from
the classful `network` statement.

## Claim ceilings, unchanged by this run

```text
ACCESS_PORT                  = UNOBSERVABLE   38 of them, TD-ACCESSPORT-READBACK-001 OPEN
ENDPOINT_GATEWAY             = UNOBSERVABLE   35 endpoint actions PARTIAL
CONFIGURATION_FULLY_VERIFIED = NO
MODULE_IDENTITY              = UNOBSERVABLE   TD-MODULE-SLOT-001, backend limitation
```

The E5 aggregate is `partial` and is reported as `partial`. Behavioural
forwarding verified end to end and promoted **nothing**: no access port and no
default gateway was read, and neither moved.

## TD-ACCEPTANCE-001, row by row

| # | What closure requires | This run |
| --- | --- | --- |
| 1 | Production physical deployment through `deploy_enterprise_topology` / `packet_tracer_physical_runtime`, manifest from fresh exact read-back | **SATISFIED.** 41 devices and 41 links deployed by the product; manifest emitted with 41 + 41 bindings, every one by composite fingerprint; `dirty_state=clean` |
| 2 | Serial topology support in the product; the reference must carry serial | **SATISFIED.** 3 serial WAN links compiled from `LinkMedia.SERIAL`, deployed, and orientation verified |
| 3 | Production configuration and addressing through `compile_configuration` → `configuration_renderer` → `apply_configuration`, including host addressing | **SATISFIED.** 88 of 88 typed actions applied, including 35 `set_endpoint_static` for the PCs. No hand-written IOS, no raw `configurePcIp` |
| 4 | Authentic foundational evidence; statuses and hashes from real read-back so the gate decides on evidence | **SATISFIED.** 12 declared foundations derived by `derive_foundational_statuses` from executed results; `ControlPlaneApplicator` refused nothing because all 12 were VERIFIED, decided before the runtime was touched |
| 5 | Typed control plane, capability resolution left to the product | **SATISFIED.** `compile_control_plane` → `ControlPlaneApplicator.apply` → `PacketTracerEnterpriseControlPlaneRuntime`, with the capability store passed and the product resolving |
| 6 | Authoritative read-back and traffic evidence through `topology_observation.py`, registered `OperationalQueryId` queries and the typed traffic primitives | **SATISFIED.** Workspace, device, module and two-ended link read-back through the physical runtime; RIP state through `SHOW_IP_PROTOCOLS` and `SHOW_IP_ROUTE_RIP`; forwarding through `TypedPingExecutor`. No parallel reimplementation |

The three rules:

* **the harness orchestrated and did not mutate.** It ran G2, read the workspace,
  composed the intent, made one call, and read the result. Every mutation was the
  product's;
* **no missing capability was worked around.** Nothing needed one;
* **the lines this upgrades are named**, below.

One thing recorded rather than glossed: the runtimes take `query_inventory` as a
constructor dependency, and the harness supplies the same read-only device
enumeration the MCP facade supplies at its own composition root. That is
dependency injection at a composition root, not a parallel read-back — every
piece of *evidence* went through a production seam.

## What this upgrades

```text
CONTROL_PLANE_FOUNDATIONAL_REQUIREMENT_INTEGRATION = ESTABLISHED  (was NOT_ESTABLISHED)
FULL_PRODUCT_PIPELINE_ACCEPTANCE                   = ESTABLISHED  (was NOT_ESTABLISHED)
```

Both move because rows 1–4 and 6 were satisfied **in this same run**, which is
the condition the entry set for them.

## What it does not upgrade, measured rather than assumed

`TD-HARDWARE-001` stays **OPEN**. Its criterion is that capability evidence used
by the enterprise resolver reconciles into *eligible physical hardware*. Composed
three ways against this same store — no store, exact build `9.0.1.0858`, and a
deliberately wrong build — selection returned the identical 41 devices and the
identical candidate lists. So this run exercised evidence at the configuration
and control-plane gates, not at the selection resolver, and it is not the
"first governed live gate that exercises real exact-version capability
consumption" that entry defers to. Its deadline is E9.5 final closure and it
does not block Stage 3A4.
