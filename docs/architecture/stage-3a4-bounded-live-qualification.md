# Stage 3A4 — MEG-4 bounded live qualification

Executed 2026-08-17 on `feature/runtime-ripv2`, worktree
`.claude/worktrees/runtime-ripv2`.

## Outcome, stated first

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
