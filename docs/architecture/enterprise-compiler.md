# E4: Enterprise Compiler and deterministic physical topology

E4 converts the aggregated Enterprise design into the existing concrete
`TopologyPlan`. It decides physical identity, ports, links, and coordinates,
but deliberately does not generate or apply network configuration.

```text
EnterprisePlan + HardwarePlan + physical catalog profile
                         |
                         v
                 EnterpriseCompiler
        +----------------+----------------+
        |                |                |
 endpoint expansion  port/link plan  hierarchical layout
        +----------------+----------------+
                         |
                         v
              concrete TopologyPlan
                         |
                         v
              Packet Tracer adapter
```

## Compilation boundary

`EndpointGroup` remains aggregated through E1-E3. E4 is the only boundary that
turns counts into current device instances. Growth remains hardware capacity
metadata: thirty requested PCs produce thirty PCs, not thirty-nine synthetic
users.

The compiler is pure and deterministic. Equal semantic inputs produce equal
device IDs, backend names, natural port ordering, link IDs, coordinates, and a
SHA-256 semantic fingerprint. It sorts semantically unordered collections and
uses no UUID, timestamp, runtime session, LLM call, bridge, or Packet Tracer API.

The existing `TopologyPlan`, `DevicePlan`, and `LinkPlan` are reused. Their new
optional fields retain Enterprise identity, site/building/floor/zone ownership,
network layer, physical link role, redundancy group, and later E5 intent
references while preserving old callers.

## Physical allocation

The adapter `PacketTracerTopologyCatalogAdapter` translates the existing model
and cable catalogs into the backend-neutral `PhysicalCompilationProfile`. The
Enterprise intent still contains logical roles and never carries strings such
as `2911` or `3560-24PS`.

Allocation order is:

1. planned infrastructure links and explicit uplink reservations;
2. endpoint access assignments from `HardwarePlan`;
3. phone-to-PC downstream links.

Every physical interface is single-use. `Vlan*`, `Loopback*`, `Tunnel*`,
`Port-channel*`, and `BVI*` are rejected, as are ports classified
`physical=false`. Natural ordering places `Fa0/2` before `Fa0/10`. Missing
models, exhausted ports, duplicate identity, self-links, and incomplete
endpoint expansion are hard errors: an invalid compile result does not expose a
partial `TopologyPlan`.

PC/phone pairs compile as `switch -> phone -> PC`, consuming one switch access
port per pair. PoE requirements remain metadata. Unknown PoE or a provisional
hardware selection is a structured warning, not a fabricated capability and
not an E4 physical blocker. The current IP-camera mapping uses the catalog's
generic wired endpoint and is reported once as reduced-assurance metadata.

## Hierarchical layout

`LayoutPlanner` operates offline. It assigns separate site regions, then groups
buildings, floors, and zones while placing WAN/edge, core, distribution,
access, and endpoints in stable rows. Endpoints use deterministic grids; paired
phones and PCs share an x-axis with a small vertical offset. Major site and zone
regions do not overlap.

The compiled coordinates can be sent through the existing production placement
path. In PT 9.0.1.0858, `pt_export_topology` reads coordinates back, but the
returned icon/canvas coordinates are transformed and do not equal the requested
`moveToLocation` values. The exact readiness distinction is therefore:

```text
layout calculated deterministically  READY
layout sent to Packet Tracer          READY
coordinates read back independently  PARTIAL
```

## Compile versus deploy

`compile_enterprise_topology()` is non-mutating and returns a compact summary by
default: plan ID, semantic hash, counts, issues, and layout bounds. The full
plan is available to an internal caller for validation and deployment. A
backend adapter must execute that exact plan; it must not choose new names,
models, ports, links, or coordinates.

E4 does not generate or apply VLAN, trunk, SVI, routing, DHCP, DNS, ACL, NAT,
STP, EtherChannel, HSRP, VoIP, QoS, or control-plane configuration. Those are
E5 responsibilities. Runtime acceptance, fault injection, diagnosis, and
autofix remain later milestones.
