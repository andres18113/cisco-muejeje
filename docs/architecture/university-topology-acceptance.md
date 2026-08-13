# University Topology Acceptance — contract

Acceptance of capabilities already implemented, above all the typed RIPv2
runtime. Not a development phase: nothing here designs routing.

Environment: Packet Tracer `9.0.1.0858`, declared through
`ConfigurationRuntimeContext.evidence_backend_version`.

## Topology under acceptance

Parent `150.1.0.0/16`. Three routers, three switches, thirty-five PCs, and
forty-one links.

| Segment | Network | Gateway | Switch | PCs |
| --- | --- | --- | --- | --- |
| LAN A — R1 | `150.1.1.64/28` | `.65` | `.66` | `.67`–`.73` (7) |
| LAN B — R3 | `150.1.1.32/27` | `.33` | `.34` | `.35`–`.48` (14) |
| LAN C — R2 | `150.1.1.0/27` | `.1` | `.2` | `.3`–`.16` (14) |

| WAN | Network | Ends |
| --- | --- | --- |
| R1–R3 | `150.1.1.80/30` | R1 `.81`, R3 `.82` |
| R1–R2 | `150.1.1.84/30` | R1 `.85`, R2 `.86` |
| R2–R3 | `150.1.1.88/30` | R2 `.89`, R3 `.90` |

Serial interfaces are **discovered**, never assumed. DCE/DTE is observed with
`show controllers`, and `clock rate` goes only to the observed DCE end.

## Expected RIPv2

Through the typed product path only: `ControlPlanePlan` → compiler →
applicator → fresh readback → typed `ROUTE_PRESENT`. No legacy generator, no
raw RIP, no blind retry.

Per router: `version 2`, `no auto-summary`, `network 150.1.0.0`; LAN interface
passive; router-to-router serials active.

## Expected learned routes

Each router learns every remote LAN and the WAN it does not touch:

| Router | Learns |
| --- | --- |
| R1 | `150.1.1.0/27`, `150.1.1.32/27`, `150.1.1.88/30` |
| R2 | `150.1.1.32/27`, `150.1.1.64/28`, `150.1.1.80/30` |
| R3 | `150.1.1.0/27`, `150.1.1.64/28`, `150.1.1.84/30` |

Convergence uses the bounded window from `TD-RUNTIME-007`. Only the read
retries; routing configuration is never redispatched while waiting.

## Expected forwarding

Representative, one PC per LAN, both directions: A↔B, A↔C, B↔C.

## Gate criteria

Eleven attributable gates: workspace safety, physical topology, link readback,
addressing, local connectivity, capability resolution, typed application,
configuration readback, route convergence, forwarding, final state.

- **PASS** — every gate satisfied.
- **PARTIAL** — topology, addressing and configuration verified, but route
  learning or forwarding incomplete on some pair.
- **BLOCKED** — a precondition prevents execution: user topology present, or
  capability resolving UNKNOWN/UNSUPPORTED. Nothing is mutated.
- **FAIL** — fresh evidence contradicts intent, for example a readback whose
  RIP state differs from the compiled action.

Evidence is kept separately for topology, addressing, RIP application, RIP
configuration verification, route learning, and forwarding. A ping never
substitutes for route evidence, and a route never substitutes for forwarding.

On partial failure: diagnose only the failing gate, no repository-wide audit,
and report every other gate as measured.

## Persistence and cleanup

Devices are created in the governed disposable namespace `MCP-PROBE-UACC-*`
and are **deleted at the end, by exact name, in finally-protected form**. This
is an acceptance run proving capability, not a delivered artifact; leaving
forty-one devices behind would be an unrequested durable change to the user's
workspace. Router configuration is persisted on-device by the renderer's
existing envelope while the run lasts.

Backend-managed `Power Distribution Device` objects are never deleted.

If retaining the built topology is ever wanted, that is a deliberate change to
this contract, not a default.

---

# Result — 2026-08-12

```text
UNIVERSITY_TOPOLOGY_ACCEPTANCE = PASS
```

Executed on PT `9.0.1.0858` against an empty workspace. All eleven gates
passed.

| Gate | Result |
| --- | --- |
| 1 workspace safety | 0 foreign devices before any mutation |
| 2 physical topology | 41 devices: 3 × 2911, 3 × 2960-24TT, 35 PCs |
| 3 link readback | 41 links, every planned pair confirmed by device and port |
| 4 addressing | 9 router L3 interfaces (3 LAN + 6 serial), 3 switch SVIs, 35 PCs |
| 5 local connectivity | 3 LAN gateways 4/4; 3 WAN peers 5/5 — proven **before** RIP |
| 6 capability | `ripv2_config`, `routing_process_state`, `routing_route_state` SUPPORTED, non-test provenance |
| 7 typed application | 3 dispatches, one per router, all APPLIED |
| 8 configuration readback | VERIFIED on all three via `fresh_show_ip_protocols` |
| 9 route convergence | 9 of 9 route expectations VERIFIED |
| 10 forwarding | all six directions 4/4, no loss, first attempt |
| 11 final state | 41 deleted by exact name, zero residue, 0 links |

Gate 4 was **corrected at Debt Checkpoint 2**. It originally read "6 router
interfaces", which undercounted: the run configured one LAN
`GigabitEthernet0/0` per router plus six serial ends across the three WAN
links.

Nine follows from the topology definition — three LANs plus three WAN links
with two ends each — so it is derived, not independently measured, and the
compiled plan's nine `ConfigureRoutedInterface` actions come from the same
constants and corroborate nothing on their own. What the persisted run state
does show live is the six serial ends: `wan_ports` records six router-to-port
bindings across its three WAN entries, and the `dce` map holds six keys, each
written from its own `show controllers` execution against a distinct end.

The count was wrong in the write-up only; the executed run addressed all nine.

Serial interfaces were discovered, not assumed: `Serial0/0/0` and
`Serial0/0/1` per router. DCE was observed on R1 for both its links and on R2
for the R2–R3 link; `clock rate` went only to those three ends.

Compiled RIP per router: `network 150.1.0.0`, LAN `GigabitEthernet0/0`
passive, both transit serials active. Every expected remote route was learned:
R1 `150.1.1.0/27`, `150.1.1.32/27`, `150.1.1.88/30`; R2 `150.1.1.32/27`,
`150.1.1.64/28`, `150.1.1.80/30`; R3 `150.1.1.0/27`, `150.1.1.64/28`,
`150.1.1.84/30`.

## Claim scope — product path versus acceptance harness

Established at Debt Checkpoint 2 by reading the harness source, **not** by
inferring from the successful live behaviour.

The run was driven by a four-module developer harness — `uacc_common.py`,
`uacc_build.py`, `uacc_address.py`, `uacc_rip.py` — which was never committed
and survives only in the executing session's scratchpad. This section, not
those scripts, is therefore the durable record of what each gate exercised.

| Concern | Mechanism actually used | Classification |
| --- | --- | --- |
| 41 devices created | `PacketTracerBridgeProbeRuntime.create_temporary_device` | HARNESS — capability-probe scaffolding, not `deploy_enterprise_topology` |
| 3 HWIC-2T modules | raw JS `addModule(...)` over `FileBridge` | HARNESS |
| 41 links | raw JS `lwAddLink(...)` over `FileBridge` | HARNESS — bypasses `ptbuilder_generator` / `packet_tracer_physical_runtime` |
| Serial/port discovery | raw JS `getPortAt(...)` | HARNESS |
| Workspace + link readback | raw JS `getDevices` / `getLinkAt` | HARNESS — parallel reimplementation of `topology_observation.py` |
| 9 router L3 interfaces | hand-written IOS lines → `PacketTracerConfigurationRuntime.configure_ios` | HARNESS — bypasses `compile_configuration` → `configuration_renderer` → `apply_configuration` |
| `clock rate` on DCE ends | same raw `configure_ios` | HARNESS |
| 3 switch management SVIs | same raw `configure_ios` | HARNESS |
| 35 PC addresses | raw JS `configurePcIp(...)` | HARNESS |
| DCE/DTE observation | `ControlledIosExecutor` + `SHOW_CONTROLLERS_SERIAL` | **PRODUCT PATH** (registered query) |
| Local connectivity + forwarding | `TypedPingExecutor` | **PRODUCT PATH** |
| Capability gate reporting | `ControlPlaneApplicator._capability_status` called directly | HARNESS instrumentation of a private method |
| RIPv2 compile → apply → readback → `ROUTE_PRESENT` | `compile_enterprise_control_plane` → `ControlPlaneApplicator.apply` → `PacketTracerEnterpriseControlPlaneRuntime` | **PRODUCT PATH** |
| Cleanup | `PacketTracerBridgeProbeRuntime.delete_temporary_device`, exact name | HARNESS — same probe-runtime class as device creation above |

Note on the capability gate: gate 6's *printed* evidence came from a private
method, but the load-bearing behaviour did not. `ControlPlaneApplicator.apply`
was called with no `capabilities` argument, so the three dispatches were gated
by the real resolution path. The gate result is sound; only its reporting was
instrumented.

**Note on the foundational-requirement gate, which is the sharpest edge here.**
`ControlPlaneApplicator.apply` checks that the configuration each action
depends on was actually verified — `_foundation_errors` iterates
`plan.foundational_requirements` and compares supplied statuses and hashes.
That gate is real product code. The harness satisfied it by **assertion rather
than evidence**: it passed

```python
foundational_statuses={i.source_id: ActionExecutionStatus.VERIFIED
                       for i in compiled.plan.foundational_requirements}
foundational_hashes={}
```

— a comprehension over the gate's own inputs, declaring every requirement
VERIFIED, with no hashes at all. The underlying L3 interfaces had been applied
by raw IOS followed by a fixed sleep, with no readback. So the statement "the
routers' addressing was verified" was supplied *to* the product by the harness,
not established *by* it.

This does not weaken the RIPv2 result. What RIPv2 verification actually rests
on is its own fresh `show ip protocols` and `show ip route rip` reads, which
the runtime performed itself, plus the forwarding pings — and the addressing
was independently demonstrated by gate 5, which proved every LAN gateway and
WAN peer reachable *before* RIP existed. But the foundational gate itself
proved nothing on this run, and a future harness must not read its silence as
confirmation. Closing `TD-ACCEPTANCE-001` requires those statuses to come from
`apply_configuration`, which produces them from real readback.

What this run therefore does and does not establish:

```text
REFERENCE_TOPOLOGY_BEHAVIOR                        = PASS
TYPED_RIPV2_PRODUCT_APPLICATION                    = PASS
TYPED_RIPV2_PRODUCT_READBACK                       = PASS
TYPED_RIPV2_ROUTE_LEARNING                         = PASS
TYPED_RIPV2_FORWARDING                             = PASS
CONTROL_PLANE_FOUNDATIONAL_REQUIREMENT_INTEGRATION = NOT_ESTABLISHED
FULL_PRODUCT_PIPELINE_ACCEPTANCE                   = NOT_ESTABLISHED
```

**These seven lines replace an earlier three-line form that read
`TYPED_CONTROL_PLANE_PRODUCT_ACCEPTANCE = PASS`.** That single line claimed too
much. The typed control-plane path is not one indivisible thing: it is an
application step, a readback step, a route-learning step, a forwarding step,
and a foundational-requirement gate that decides whether the first step should
run at all. Four of those five were exercised by production code on fresh
evidence and each keeps its PASS. The fifth was fed a fabricated precondition
and establishes nothing, so it is now named separately rather than absorbed
into a blanket claim that would have carried it silently.

The live result stands and is not weakened: a three-router RIPv2 triangle with
thirty-five hosts really was built on PT 9.0.1.0858, really converged, and
really forwarded in all six directions. The typed control-plane path — the
capability actually under acceptance — was exercised end to end through
production code.

What was **not** exercised is the product's own physical-build and
configuration pipeline at this scale. The topology and its addressing were
placed by raw bridge calls, so no claim may be made that
`deploy_enterprise_topology`, `ptbuilder_generator`,
`packet_tracer_physical_runtime`, or the `compile_configuration` →
`configuration_renderer` → `apply_configuration` chain can build this topology.
That gap is tracked as `TD-ACCEPTANCE-001`.

## Defect found by this acceptance

With three routers a prefix is reachable through two peers, and the compiler
emitted one route expectation **per peer pair**. Because the expectation id
does not include the peer, two expectations shared an id — ten expectations,
eight unique ids. The earlier offline tests used a three-router fixture but
compared sets, which hid it.

Fixed by emitting one expectation per `(device, prefix)`: the question is
whether the router learned the prefix, not which neighbour advertised it, and
the next hop is not part of the assertion. Two regressions now pin unique ids
across the whole plan and single emission for a prefix reachable through two
peers.

## Backend note

`Port.getDevice()` does not exist in PT 9.0.1.0858; the accessor is
`Port.getOwnerDevice()`. The first link readback returned empty device names
and was corrected before the gate was judged. Recorded here so the next live
harness does not rediscover it.

**Production was checked at Debt Checkpoint 2 and is already correct.** Every
link readback in `src/` uses `getOwnerDevice()`:
`topology_observation.py:87`, `probe_runtime.py:157`, and
`tool_registry.py:1672,1678-1679`. A search for a `Port` reached through
`getPort1`/`getPort2`/`getPortAt` and then asked for `.getDevice()` returns
nothing in `src/`. The defect existed only in the uncommitted harness, which
had reimplemented the readback instead of calling `topology_observation.py`.
No product fix is required and no debt is opened for it.

The reason the harness could hold a defect the product does not is itself the
finding recorded under "Claim scope" above: the harness reimplemented a
readback that production already provides.
