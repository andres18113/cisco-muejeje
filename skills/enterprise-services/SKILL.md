---
name: enterprise-services
description: Plan or assess DNS, HTTP/HTTPS, NTP, and TFTP service behavior in an enterprise Packet Tracer topology. Use for service placement, dependencies, and client-visible outcomes; use enterprise-voice for telephony and enterprise-configuration for foundational device configuration.
---

# Enterprise Services

Own service intent, placement, dependencies, and evidence that clients can use the intended service.

Do not own addressing, DHCP, base interface configuration, voice, or whole-network acceptance. Those are inputs or handoffs. An implemented `ServicePlan`, compiler, applicator, or runtime is not by itself proof that the same workflow is exposed through the current public MCP surface.

## Decision flow

1. Identify the requested service and its declared client outcome.
2. Reuse approved host identities, addressing, and connectivity rather than recreating them.
3. Check the current public typed surface and current capability evidence before promising an operational action.
4. Build or inspect typed service intent through the existing plan/compiler seam.
5. Apply only through a currently exposed governed path.
6. Collect fresh service-state evidence and a service-specific client observation when the environment can provide one.
7. Report unsupported, unknown, or unobservable dimensions without converting them into success or failure.

Keep service state separate from client behavior. For example, a configured record is not a successful lookup, and a reachable server is not proof that the requested content or time/file operation worked.

Stop when placement, foundational connectivity, capability evidence, or the required observation path is missing. Do not invent an alternate API or substitute a generic reachability check for service behavior.

## Source navigation

When implementation detail matters, locate the current `ServicePlan`, `ServiceCompiler`, `ServiceApplicator`, and `PacketTracerEnterpriseServiceRuntime`, then read their focused tests. Treat those sources and fresh runtime results as authoritative; do not preserve their fields, supported operations, or evidence status in this Skill.
