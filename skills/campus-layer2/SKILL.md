---
name: campus-layer2
description: Design or assess campus Layer 2 resilience through STP-family behavior and EtherChannel bundling, including forwarding roles, controlled failure, and recovery. Do not use for routine VLAN/trunk plumbing, first-hop gateway failover, or IP routing.
---

# Campus Layer 2

Own loop-prevention and link-aggregation resilience over an already approved physical and foundational switching design.

Routine VLAN creation, access/trunk configuration, and interface mechanics belong to enterprise configuration. Gateway role belongs to first-hop redundancy; route exchange belongs to routing IGP.

## Resilience workflow

1. Classify the request as STP-family, EtherChannel, or a coordinated L2 resilience scenario.
2. Confirm the exact topology links, intended redundancy, and current capability evidence.
3. Inspect or compile the relevant typed control-plane intent without assuming that every internally implemented action is publicly exposed.
4. Establish fresh state and a working forwarding baseline.
5. If failure testing is authorized, change one controlled condition and observe alternate forwarding.
6. Restore the condition and verify recovery independently.

For STP, keep root identity, port role/state, forwarding behavior, and convergence distinct. For EtherChannel, keep logical bundle state, member state, and traffic behavior distinct. Never infer one protocol or mode from evidence for another.

Stop before mutation when the topology has no intended redundant path, the baseline is not working, current support is unknown, or cleanup cannot be verified.

## Selective detail

- Read [the STP reference](references/stp.md) only for root, edge-port, role/state, or STP recovery work.
- Read [the EtherChannel reference](references/etherchannel.md) only for bundle membership, negotiation, forwarding, or bundle recovery work.

When source detail matters, locate `ControlPlanePlan`, `ControlPlaneCompiler`, `ControlPlaneApplicator`, the current control-plane runtime, and the focused L2 tests. Source and fresh observations own current behavior and exposure.
