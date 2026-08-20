---
name: routing-igp
description: Design or assess typed IPv4 IGP behavior in Packet Tracer for RIPv2, OSPFv2, or EIGRP, including adjacency or peer state, learned routes, forwarding, convergence, and recovery. Do not use for first-hop gateway roles, static routing, or Layer 2 resilience.
---

# Enterprise IGP Routing

Own dynamic IPv4 routing intent and protocol-specific evidence for RIPv2, OSPFv2, or EIGRP over an approved addressing and interface foundation.

Do not invent addresses, peers, networks, or protocol substitutions. The unified `ControlPlanePlan` and compiler are source ownership, not a reason to merge this responsibility with Layer 2 or first-hop redundancy.

## Routing workflow

1. Identify the requested protocol and whether the task concerns design, application, observation, or controlled failure.
2. Reuse approved router/interface identities and obtain current capability/public-exposure evidence.
3. Read only the matching protocol reference below.
4. Build or inspect typed intent through the existing control-plane plan/compiler seam.
5. Apply only through a currently exposed governed path.
6. Query fresh protocol state, learned routes, and forwarding evidence appropriate to that protocol.
7. For authorized convergence tests, require a working baseline, observe the changed path, restore it, and verify recovery separately.

Configuration, protocol state, route installation, forwarding, convergence, and recovery are distinct evidence dimensions. In particular, retrieve current EIGRP evidence before making a claim; preserve `UNKNOWN` or `UNOBSERVABLE` ceilings when current capability/runtime evidence does not support stronger conclusions.

Stop on stale output, unresolved capability, missing baseline routes/forwarding, or an unsafe restoration path. Do not reinterpret an empty or unsupported observation as proof that a protocol is unavailable.

## Protocol detail

- Read [the RIPv2 reference](references/ripv2.md) only for RIPv2 intent, route evidence, or convergence work.
- Read [the OSPFv2 reference](references/ospf.md) only for OSPF area, adjacency, route, or convergence work.
- Read [the EIGRP reference](references/eigrp.md) only for EIGRP intent or evidence work.

For implementation truth, locate `ControlPlanePlan`, `ControlPlaneCompiler`, `ControlPlaneApplicator`, the current control-plane runtime, and focused protocol tests, including the typed RIPv2 tests.
