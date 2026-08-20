---
name: enterprise-voice
description: Plan, verify, or troubleshoot enterprise IP telephony in Packet Tracer, including failed phone registration, voice access intent, bootstrap, call control, and call evidence. Use enterprise-services for non-voice services and enterprise-configuration for foundational VLAN or interface mechanics.
---

# Enterprise Voice

Own voice-specific intent and the evidence chain from an approved network foundation to phone registration and call behavior.

Voice consumes addressing, access configuration, and service reachability; it does not silently take ownership of those domains. Keep logical phone identity distinct from physical attachment, and keep registration, call setup, call state, and media observability as separate questions.

## Voice sequence

1. Confirm the requested voice outcome, endpoint identities, numbering policy, and approved voice access intent.
2. Resolve current capability evidence before choosing a bootstrap or call-control mechanism.
3. Use the existing typed voice plan/compiler seam to detect collisions and unsatisfied prerequisites.
4. Verify that the intended operation is available through the current public surface before attempting live work. Internal applicator/runtime support does not create a public entrypoint.
5. Observe registration before initiating a call, then record call behavior and any evidence ceiling separately.
6. Preserve unknown or unobservable stages instead of inferring success from configuration or UI state.

Stop if endpoint identity, addressing, foundational connectivity, capability evidence, or the required governed adapter is absent. Do not invent callbacks, UI coordinates, dialing routines, or a raw fallback.

## Source navigation

For development or disputed behavior, locate the current `VoicePlan`, `VoiceCompiler`, `VoiceApplicator`, `PacketTracerEnterpriseVoiceRuntime`, and their focused tests. Read those owners directly for supported actions and observation semantics; runtime registration and call results remain dynamic evidence.
