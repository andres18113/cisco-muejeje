# Enterprise planning core (E2)

E2 enriches the logical Enterprise plan offline. It does not generate IOS,
Packet Tracer devices, coordinates, or `TopologyPlan` artifacts.

```text
EnterpriseIntent
      ↓
Physical hierarchy + segment assignment
      ↓
VLSM/IPAM + capacity planning
      ↓
Enriched EnterprisePlan
      ↓
[future EnterpriseCompiler]
      ↓
TopologyPlan
```

## Logical and physical views

The logical view contains `NetworkSegment` roles, IPv4 subnets, gateway data,
and later services and security zones. The physical view contains a hierarchy:

```text
Enterprise → Site → Building → Floor → Zone → EndpointGroup
```

`EndpointGroup` retains counts, such as thirty PCs or eight cameras. It never
expands them into individual devices. A legacy `SiteIntent.endpoints` remains
valid and is placed internally in `SITE_DEFAULT_ZONE`.

`TopologyDesign` declares semantic `NetworkLayer` values and concrete
`TopologyPattern` values. A `HYBRID` plan must include per-layer patterns; it
is not an unspecified topology.

## IPv4 VLSM and site summarization

`IPAMPlanner` uses only `ipaddress`. For every segment, it calculates:

```text
growth_hosts = ceil(raw_hosts × growth)
required_usable = raw_hosts + growth_hosts + gateway + reservations
```

The default gateway is the first usable address. LAN allocation never uses a
prefix longer than `/30`. Segments are allocated largest-first with stable
segment IDs. Each site reserves a contiguous block equal to the sum of the
actual VLSM subnet footprints, rounded to the next power of two; the block is
therefore summarizable. Sites are allocated largest-first, then by stable site
ID. Explicit site blocks are validated for IPv4 syntax, containment, overlap,
and capacity; they are never enlarged silently.

Growth accepts either a fraction (`0.30`) or a percentage (`30`). The effective
growth precedence is segment override, then site value, then Enterprise default.
It is applied exactly once.

## Capacity and PC/phone pass-through

`CapacityPlanner` works per zone and returns port requirements, not selected
hardware. It counts wired access-attached endpoints and PoE only when
`requires_poe=True`. Wireless clients consume no direct switch ports; their AP
does. When `pair_pc_with_ip_phone` is true, the planner pairs the minimum of
wired PCs and IP phones: each pair uses one access port but one PoE port for the
phone. Growth reserves access and PoE ports independently using the same ceil
rule. Uplink requirements are policy output, currently two per non-empty access
zone.

This separation lets E3 select hardware only when capability evidence supports
the requirement. `EnterprisePlan.compact_summary()` derives counts on demand,
which keeps future MCP responses compact without serializing groups, ports, or
individual endpoints by default.
