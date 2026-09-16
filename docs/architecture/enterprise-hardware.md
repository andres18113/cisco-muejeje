# E3: Enterprise Hardware Planner

E3 turns a mathematically valid EnterprisePlan into a compact physical hardware
specification. It does not create layout coordinates, Packet Tracer files or
links, or IOS configuration. E4 consumes a valid hardware plan to compile those
later artifacts.

## Capability evidence

HardwarePlanner belongs to the domain and consumes HardwareCandidate values.
EnterpriseCapabilityAdapter is the infrastructure boundary that translates
catalog knowledge into those candidates.

An unobserved capability remains UNKNOWN. A model name or family does not prove
PoE, Layer 3 switching, routing, module support, or a physical slot. Evidence
is retained per capability and resolved by precedence: controlled probe/runtime
observation, manual verification, static override, catalog, then inference.

A candidate can be COMPATIBLE, NEEDS_VERIFICATION, or INCOMPATIBLE. A hardware
plan can therefore be VALID, PARTIALLY_RESOLVED, or UNRESOLVED; only VALID may
enter E4. A partial plan must not produce IOS, Packet Tracer, or physical
topology claims.

## Hierarchy, ports, and modules

E3 uses aggregate capacity requirements for access ports, PoE, endpoint pairs,
and dedicated uplinks. It selects a deterministic physical hierarchy while
keeping user-facing access capacity separate from uplink demand. Resilience
expresses physical-link redundancy only; it does not presume STP, EtherChannel,
HSRP, or a routing protocol.

Ports retain their catalog names and normalized roles. A PortAssignmentRange is
a normative contiguous binding from a source-group range to selected device
ports. E4 materializes that binding and does not select replacement ports.

ModulePlanner uses only catalog-declared compatibility and known slot
constraints. Insufficient evidence leaves a requirement unresolved; it does not
invent a card or a slot, and it does not convert UNKNOWN into UNSUPPORTED.
Serial demand is aggregated by router before module selection.

## Router role reconciliation and limits

EDGE_ROUTER and WAN_ROUTER remain separate logical roles. When a site requires
both, E3 may represent them by one physical router with a primary role and
explicit additional-role metadata. The combined candidate must meet the additive
Ethernet and serial requirements. Category, port, module, or slot
incompatibility prevents reconciliation.

Coverage reporting compares observed models with the catalog without adding them
automatically. Discovery and controlled probes provide evidence for later
review; E3 itself does not execute Packet Tracer or guess APIs.

E3 deliberately does not implement layout, Packet Tracer files, IOS, services,
VLANs, routing, voice, or simulation. Those boundaries are part of its contract,
not implicit missing work.
