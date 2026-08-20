---
name: enterprise-security
description: Plan, apply, or assess enterprise ACL, NAT, and Layer 2 security enforcement in Packet Tracer. Use for policy placement and positive/negative behavior evidence; use network-acceptance for a whole-deployment verdict and enterprise-configuration for non-security mechanics.
---

# Enterprise Security

Own security policy intent, placement, governed application, and evidence that the intended traffic is allowed or denied.

Do not use this Skill to certify the entire deployment, diagnose unrelated failures, or take ownership of foundational addressing and interface configuration. Treat the typed security plan/compiler/applicator/runtime as implementation seams. Before live work, confirm which bounded security operation is exposed by the current public MCP registry; internal support is not public exposure.

## Enforcement method

1. Translate the requested policy into explicit protected paths and expected positive and negative flows.
2. Derive placement from the current topology and Layer 3 boundaries, not interface-name intuition.
3. Confirm current capability evidence and the governed typed path for the requested control.
4. Compile and validate the policy with the existing security source owners.
5. Establish a known-good positive baseline before introducing a negative enforcement test.
6. Apply, read back, and exercise the specific policy behavior using the minimum sufficient evidence.
7. When mutation occurs, verify cleanup or restoration separately from the enforcement result.

Configuration presence is not enforcement proof. Keep read-back, allowed behavior, denied behavior, and recovery distinct. Unknown or unavailable probes must remain explicit.

Stop when placement, baseline behavior, capability evidence, a typed probe, or a safe restoration path is missing. Do not bypass the governed typed surface or expose secrets.

## Source navigation

Locate the current `SecurityPlan`, `SecurityCompiler`, `SecurityApplicator`, `PacketTracerEnterpriseSecurityRuntime`, public registry entries, and focused security tests when details matter. Read those owners rather than copying policy fields, commands, supported controls, or current observations into this Skill.
