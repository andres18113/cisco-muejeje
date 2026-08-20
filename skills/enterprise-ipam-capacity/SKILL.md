---
name: enterprise-ipam-capacity
description: Plan enterprise IPv4 allocation, reconcile existing address ownership, or calculate aggregate access-port, PoE, growth, and uplink demand before hardware selection. Use for addressing and capacity decisions; do not use for choosing models, modules, or configuration.
---

# Enterprise IPAM and Capacity

Keep one Skill with two branches. Select only the branch or branches the request needs.

## Addressing and reconciliation

1. Classify the task as initial allocation or reconciliation and establish the authoritative address space, logical demand, growth input, and existing assignments.
2. Delegate deterministic initial allocation to `IPAMPlanner`. Delegate identity-preserving matching and allocation to `AddressReconciler`; do not reproduce either algorithm manually.
3. Report conflicts, insufficient capacity, and proposed renumbering explicitly. A proposed renumber is not authorization to apply it.
4. Verify containment, non-overlap, usable capacity, determinism, and traceability to declared demand.

## Capacity demand

1. Start from normalized endpoint groups and the approved attachment policy.
2. Use `CapacityPlanner` to keep access attachment, PoE-port, growth, and uplink demand distinct.
3. Apply growth once. Count shared attachment only when declared, and distinguish wireless clients from their wired infrastructure.
4. Hand aggregate demand to `enterprise-hardware` without selecting a model.

## Boundaries and evidence

- Stop on invalid or overlapping address space, ambiguous ownership, insufficient capacity, unauthorized renumbering, or double-counted growth.
- Do not infer model capacity, treat logical interfaces as cable ports, or mutate Packet Tracer.
- Retain validation issues and show whether identities were preserved or why change is required. Source and tests own exact models, statuses, and calculations.

## Source navigation and references

Use Graphify only to locate symbols, then read `IPAMPlanner`, `AddressReconciler`, or `CapacityPlanner` and the focused tests for the selected branch.

- Read [initial addressing](references/addressing.md) only for new allocation and VLSM review.
- Read [reconciliation](references/reconciliation.md) only when existing assignments must be preserved.
