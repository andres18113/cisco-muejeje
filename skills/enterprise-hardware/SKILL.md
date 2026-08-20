---
name: enterprise-hardware
description: Select Packet Tracer device models, modules, and physical interfaces that satisfy approved capacity, topology, and resilience demand using current capability evidence. Use after demand is known; do not use to estimate capacity or discover capabilities by guesswork.
---

# Enterprise Hardware Planning

Own physical candidate selection after logical design and capacity demand are approved. Consume capability evidence; do not create or probe it.

## Workflow

1. Confirm resolved topology intent, capacity demand, and resilience requirements. Route missing demand to `enterprise-ipam-capacity`.
2. Resolve the relevant Packet Tracer environment and obtain current candidate evidence, using `packet-tracer-capabilities` for missing or unknown requirements.
3. Evaluate candidates only against approved demand and current evidence. Reserve physical uplinks before endpoint attachment; logical interfaces never satisfy cable demand.
4. Keep incomplete-evidence selections provisional. Preserve reasons for rejection, uncertainty, and unresolved requirements.
5. Hand only a sufficiently resolved, deterministic hardware plan to the physical topology compiler.

## Boundaries and stops

- Do not maintain a model, module, port, or capability catalog in this Skill.
- Do not invent modules, infer support from model names, rerun capacity growth, or probe capabilities inside hardware planning.
- Aggregate capacity does not prove that each device or failure domain is viable.
- When no candidate satisfies a mandatory requirement, stop. When evidence is unknown, request only the evidence needed to decide; unknown is neither support nor rejection.

## Evidence and source navigation

Trace every final selection to approved demand and current evidence. Use Graphify only to locate symbols, then read `HardwarePlanner`, `plan_enterprise_hardware`, and focused hardware tests. Read physical compiler tests for cableable-interface validation, and inspect current MCP registration before claiming public exposure.

Read [device selection](references/device-selection.md) only when comparing concrete candidates, assigning physical ports, or resolving module-dependent demand.
