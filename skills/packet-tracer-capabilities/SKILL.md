---
name: packet-tracer-capabilities
description: Establish whether a Packet Tracer feature is supported in the current environment by resolving scoped evidence or using a registered isolated probe. Use for capability uncertainty, not deployment or design selection.
---

# Packet Tracer Capability Evidence

## Responsibility

Resolve a precise support question against evidence for the active Packet Tracer environment. This Skill does not choose architecture or hardware, and it does not own ordinary live operations.

## Method

1. State the exact capability, target, scenario, and evidence needed.
2. Establish the active environment fingerprint before reusing stored evidence.
3. Ask the current resolver and snapshot store for matching evidence; retain contradictions and provenance.
4. If evidence remains unresolved and probing is appropriate, use only the registered typed discovery path in an isolated, owned session.
5. Require an independent observation, bounded execution, cleanup, and cleanup verification.
6. Report the scoped conclusion, evidence limits, and what would resolve any remaining uncertainty.

## Interpretation boundaries

- `UNKNOWN` means the available evidence does not decide the question; it does not mean unsupported.
- An observation failure, timeout, parser failure, or unsafe cleanup does not prove absence of support.
- A successful dispatch is not operational proof without the required read-back or behavior.
- Never generalize model-, version-, or scenario-specific evidence beyond its matching fingerprint and scope.
- Do not replace the registered probe workflow with arbitrary commands or scripts.

## Stops and handoffs

Stop when the environment cannot be identified, the required probe is unregistered, isolation is unavailable, or cleanup cannot be established safely. Hand hardware choice to `enterprise-hardware` after evidence is resolved; hand ordinary live execution to `packet-tracer-runtime`.

## Source-of-truth navigation

Use a focal Graphify query for `CapabilityDiscoveryService` or `CapabilityResolver`, then read the exact current source and focused tests. Start with:

- `src/packet_tracer_mcp/application/use_cases/capability_discovery.py`
- `src/packet_tracer_mcp/domain/enterprise/services/capability_resolver.py`
- `src/packet_tracer_mcp/infrastructure/persistence/capability_snapshot_store.py`
- `tests/test_capability_discovery.py` and the isolation/version-scoping tests

Read [capability evidence](references/evidence.md) when matching, conflicting, or stale evidence affects the conclusion. Read [probe protocol](references/probes.md) only when existing evidence cannot answer the question and a governed probe is warranted.
