---
name: packet-tracer-runtime
description: Operate an existing Packet Tracer workspace through controlled readiness, identity, typed live actions, fresh read-back, convergence, and cleanup. Use for live mechanics, not domain policy or capability discovery.
---

# Controlled Packet Tracer Runtime

## Responsibility

Carry an approved operation through the live runtime lifecycle and return evidence about what actually happened. Domain Skills own policy; `packet-tracer-capabilities` owns unresolved support questions. This Skill provides neither a raw fallback nor authority to invent an untyped operation.

## Method

1. Confirm the governed connection is ready and identify the active environment.
2. Resolve the intended target through the current deployment identity or other typed binding; reject ambiguity or staleness.
3. Establish the required device/application readiness, a freshness boundary, and any restoration plan before mutation.
4. Invoke the smallest current typed public operation that satisfies the approved request.
5. Isolate current output, perform independent read-back, and wait only for bounded, operation-specific convergence.
6. Verify behavior when the caller's acceptance criterion requires it.
7. Restore or clean up disposable changes, verify the final state, and report incomplete recovery explicitly.

## Evidence boundaries

- Transport success is not device readiness, direct observation, convergence, or behavioral proof.
- Historical terminal output is not fresh evidence for the current operation.
- A deployment name alone is not sufficient when the workflow provides a stronger typed identity.
- Do not compensate for a missing typed path with raw IOS or Script-Engine execution.

## Hard stops

Stop when connection/authentication, environment identity, target binding, readiness, freshness, required capability authorization, or safe cleanup cannot be established. Return the observed limitation; do not silently widen the operation.

## Source-of-truth navigation

Use a focal Graphify query for `DeploymentManifest`, `ControlledIosExecutor`, or `StableConvergenceWaiter`, then inspect the exact current source/tests. Start with:

- `src/packet_tracer_mcp/domain/enterprise/models/deployment.py`
- `src/packet_tracer_mcp/infrastructure/execution/device_lifecycle.py`
- `src/packet_tracer_mcp/infrastructure/execution/ios_terminal.py`
- `src/packet_tracer_mcp/infrastructure/execution/stable_convergence.py`
- focused deployment-manifest, lifecycle, terminal, and convergence tests

Read [device lifecycle](references/lifecycle.md) when a live target must become operational before use. Read [terminal evidence](references/ios-terminal.md) only for IOS or endpoint command-output observation. Read [runtime transactions](references/transactions.md) before a disposable mutation or any operation that needs restoration.
