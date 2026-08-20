# Multi-domain orchestration

Read this reference only after a request has been classified as multi-phase or multi-domain.

## Handoff map

- Logical requirements belong to `enterprise-network-design`.
- Addressing/reconciliation and physical demand belong to the two branches of `enterprise-ipam-capacity`.
- Device and module selection belongs to `enterprise-hardware`; unresolved support is a separate capability-preflight step.
- Foundational typed configuration belongs to `enterprise-configuration`; services, voice, security, Layer 2 resilience, gateway redundancy and IGP policy remain with their domain owners.
- Live readiness, read-back, convergence and cleanup use `packet-tracer-runtime` as support, not as a policy owner.
- Acceptance evaluates declared expectations. Diagnosis becomes primary only for a failed result that needs causal explanation. Planned autofix is never a normal handoff.

## Per-step rule

Choose one primary Skill for the active reasoning step and no more than two allowed supporters. A handoff changes ownership of the next step; it does not claim literal context eviction.

Pass stable artifacts and evidence provenance between owners. Do not keep unrelated domain references active merely because the overall request mentions them.
