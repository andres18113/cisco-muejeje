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
| 4 addressing | 6 router interfaces, 3 switch SVIs, 35 PCs |
| 5 local connectivity | 3 LAN gateways 4/4; 3 WAN peers 5/5 — proven **before** RIP |
| 6 capability | `ripv2_config`, `routing_process_state`, `routing_route_state` SUPPORTED, non-test provenance |
| 7 typed application | 3 dispatches, one per router, all APPLIED |
| 8 configuration readback | VERIFIED on all three via `fresh_show_ip_protocols` |
| 9 route convergence | 9 of 9 route expectations VERIFIED |
| 10 forwarding | all six directions 4/4, no loss, first attempt |
| 11 final state | 41 deleted by exact name, zero residue, 0 links |

Serial interfaces were discovered, not assumed: `Serial0/0/0` and
`Serial0/0/1` per router. DCE was observed on R1 for both its links and on R2
for the R2–R3 link; `clock rate` went only to those three ends.

Compiled RIP per router: `network 150.1.0.0`, LAN `GigabitEthernet0/0`
passive, both transit serials active. Every expected remote route was learned:
R1 `150.1.1.0/27`, `150.1.1.32/27`, `150.1.1.88/30`; R2 `150.1.1.32/27`,
`150.1.1.64/28`, `150.1.1.80/30`; R3 `150.1.1.0/27`, `150.1.1.64/28`,
`150.1.1.84/30`.

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
