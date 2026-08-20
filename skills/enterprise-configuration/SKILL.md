---
name: enterprise-configuration
description: Compile and apply approved foundational enterprise configuration through typed plans and runtime bindings. Use for VLAN, interface, addressing, DHCP, and endpoint mechanics, not services, security, voice, or control-plane policy.
---

# Enterprise Configuration

## Responsibility

Translate approved foundational intent into the repository's current typed configuration plan, apply it through the governed runtime, and preserve the distinction between application and evidence.

This Skill owns configuration mechanics. It does not choose service, security, voice, STP/EtherChannel, first-hop redundancy, or dynamic-routing policy. Ordinary VLAN and trunk plumbing belongs here; Layer 2 resilience decisions belong to `campus-layer2`.

## Method

1. Confirm that upstream intent, physical topology identity, and required capability evidence are current enough for compilation.
2. Compile with the current `ConfigurationCompiler`; treat its typed output and validation result as authoritative.
3. Review prerequisite failures and affected dependents without recreating dependency rules in prose.
4. Apply through `ConfigurationApplicator` and the typed runtime binding. Never add an untyped command escape hatch.
5. Collect direct read-back and, where the approved requirement demands it, separate behavioral evidence.
6. Report compilation, dispatch, observation, behavior, and recovery as distinct outcomes.

## Hard stops and handoffs

Stop when domain intent is missing, target identity is stale or ambiguous, a required capability is not authorized by current evidence, a mandatory prerequisite fails, or mutation recovery is unresolved. Hand policy questions to the relevant domain Skill and live lifecycle mechanics to `packet-tracer-runtime`.

## Source-of-truth navigation

Use a focal Graphify query for `ConfigurationCompiler`, `ConfigurationApplicator`, or `PacketTracerEnterpriseConfigurationRuntime`, then inspect:

- `src/packet_tracer_mcp/domain/enterprise/services/configuration_compiler.py`
- `src/packet_tracer_mcp/application/use_cases/compile_configuration.py`
- `src/packet_tracer_mcp/application/use_cases/apply_configuration.py`
- `src/packet_tracer_mcp/infrastructure/execution/enterprise_configuration_runtime.py`
- focused compiler, application, and deployment-manifest tests

Read [typed configuration actions](references/actions.md) only when a request spans multiple foundational changes or requires reasoning about prerequisites, desired state, and verification expectations.
