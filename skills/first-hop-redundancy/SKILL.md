---
name: first-hop-redundancy
description: Design or assess redundant default-gateway behavior in Packet Tracer, including virtual gateway forwarding, role evidence, failover, and recovery. Use routing-igp for route exchange and campus-layer2 for STP or EtherChannel resilience.
---

# First-Hop Redundancy

Own first-hop gateway intent and the evidence that a virtual gateway continues forwarding across an authorized failure and restoration.

Do not own Layer 2 path selection, dynamic route exchange, or foundational interface configuration. Do not encode a static Packet Tracer protocol/support matrix here; obtain current capability evidence for the active environment.

## Decision sequence

1. Confirm the intended gateway subnet, virtual address, participating devices, and deterministic preference policy.
2. Reject address collisions or an ambiguous ownership/failover objective.
3. Check current capability and public-exposure evidence before selecting or applying a concrete FHRP mechanism.
4. Use the existing typed control-plane plan/compiler/applicator seams for supported work.
5. Establish fresh virtual-gateway forwarding and whatever role evidence the runtime can actually observe.
6. Only after a valid baseline, perform one authorized failure, verify continued forwarding, restore it, and verify recovery.

Virtual-address forwarding does not prove active/standby role. An event message does not prove persistent state. If the current runtime cannot observe a role or transition dimension, keep it unknown or unobservable while reporting separately supported forwarding evidence.

Stop when subnet identity, addresses, participants, capability evidence, the forwarding baseline, or restoration safety is unresolved. Never invent another protocol or a raw configuration fallback.

## Source navigation

For implementation detail, locate the FHRP intent and evidence types in `ControlPlanePlan`, then inspect `ControlPlaneCompiler`, `ControlPlaneApplicator`, the current control-plane runtime, and focused control-plane tests. Those sources and current runtime evidence own protocol availability and observation ceilings.
