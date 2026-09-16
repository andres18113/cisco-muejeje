# domain/rules/

Rules validate domain values without performing I/O. They cover classic device,
link, addressing, and DHCP consistency as well as ACL, VLAN, NAT, hardening,
interface-tuning, NetFlow, switch-security, and Enterprise compilation
constraints.

Rules return `ValidationResult`, `PlanError`, warnings, or typed compilation
issues as defined by the relevant contract. They do not mutate Packet Tracer or
choose a transport. Application use cases decide whether a validation result
permits planning, rendering, deployment, or a refusal.
