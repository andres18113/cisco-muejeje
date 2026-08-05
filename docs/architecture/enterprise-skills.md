# Enterprise Skills v1

The repository keeps the E1-E9 networking workflow as 17 progressively
loaded Skills under the top-level skills directory. Each Skill has a compact
SKILL.md with responsibility, workflow, rules, evidence/readiness,
stop-conditions and completion semantics. Detailed procedures live in the
direct references directory of the Skill that owns them.

## Activation model

The orchestrator is loaded for end-to-end enterprise requests. It selects
specialized Skills from the requested operation:

- design: enterprise-network-design, enterprise-ipam-capacity,
  enterprise-hardware;
- physical/runtime: packet-tracer-capabilities, packet-tracer-runtime,
  packet-tracer-layout;
- configuration and services: enterprise-configuration, enterprise-services,
  enterprise-voice, enterprise-security;
- control plane: campus-layer2, first-hop-redundancy, routing-igp;
- outcomes: network-acceptance, network-diagnosis, network-autofix.

packet-tracer-runtime is transversal only when Packet Tracer is actually
operated. A simple design request must not load live-runtime references.

## Boundary with the source code

SKILL.md describes how an agent should reason about enterprise networking.
AGENTS.md describes how an agent may modify this repository. Domain models,
typed actions, dependency DAGs, evidence provenance, semantic hashes and
runtime safety remain source-code contracts; Skills do not replace them.

Skills must consume the existing E4-E9 plans and runtimes. They must not create
a second IOS executor, dependency sorter, capability taxonomy or arbitrary
CLI/JavaScript path.

## Dynamic facts

Model support, Packet Tracer build behavior and runtime anomalies do not belong
in static Skills. They remain in CapabilityRegistry, runtime snapshots and
RuntimeQuirkRegistry, matched by environment fingerprint. Lack of evidence is
UNKNOWN, not UNSUPPORTED.

## Evidence contract

All Skills preserve the common state distinction:

COMPILED != APPLIED != DIRECTLY_OBSERVED != BEHAVIORALLY_VERIFIED

Control-plane and resilience Skills additionally separate adjacency, route
state, forwarding, failover and recovery. Acceptance, diagnosis and autofix
consume these results and never manufacture missing evidence.

## Deferred scope

The canonical set intentionally does not include BGP, IPv6 routing or route
redistribution. Those belong to E10 after Packet Tracer capability evidence
exists.
