# IP Addressing

The repository has two addressing paths with different scopes. The classic
planner assigns fixed-size subnets for the topology templates. The Enterprise
IPAM planner performs deterministic VLSM from a declared address space. They do
not share code, and a plan uses one or the other.

## Classic planner

`domain/services/ip_planner.py`. `IPPlanner` draws LANs from `192.168.0.0/16`
and point-to-point links from `10.0.0.0/16`, both as sequential generators, so
the same topology always produces the same addresses.

| Element | Allocation |
|---|---|
| LAN, per router-to-switch link | The next `/24`: `192.168.0.0/24`, `192.168.1.0/24`, … |
| LAN gateway | The first usable address of the subnet, `.1`, on the router interface |
| LAN hosts | Consecutive addresses from `.2`, each host also receiving that gateway |
| Router-to-router link | The next `/30`: `10.0.0.0/30`, `10.0.0.4/30`, … The two usable addresses go to each end |
| Router-to-cloud link | The next `/30`; only the router end is addressed |

```text
LAN 1:  192.168.0.0/24  ->  R1 Gig0/1: .1 (gateway)   PC1: .2   PC2: .3
Link:   10.0.0.0/30     ->  R1 Gig0/0: 10.0.0.1       R2 Gig0/0: 10.0.0.2
```

In router-on-a-stick mode the router-to-switch link is a trunk and receives no
subnet of its own. Each VLAN takes one `/24`, the router subinterface
(`GigabitEthernet0/0.<vlan>`) holds the gateway, and the PCs of that VLAN take
consecutive host addresses. The subinterface address is also written to the
router's interface map, so OSPF, RIP and EIGRP advertise the VLANs without any
special case.

## Enterprise IPAM and VLSM

`domain/enterprise/services/ipam_planner.py`, with the typed results in
`domain/enterprise/models/addressing.py`. The planner runs only when the intent
declares an Enterprise address space, and that space must be a valid IPv4 CIDR;
this path does not address IPv6.

**Per-segment demand.** For each segment the planner computes the required
usable hosts as `host_requirement + growth + 1 gateway + reserved_hosts`. Growth
is applied once, with `Decimal` and `ROUND_CEILING`, and the input is accepted
either as a fraction (`0.30`) or as a percentage (`30`), normalised to one
internal meaning. The result is the smallest prefix that holds that demand,
bounded by `minimum_lan_prefix`, which defaults to `/30`.

**Largest-first, deterministically.** Segment requirements are sorted by prefix
length ascending, then by segment id; a shorter prefix is a larger subnet, so
the largest segment is placed first and ties never depend on dictionary order.
Site blocks are ordered the same way, by the site's own prefix and then by site
id.

**Summarisable block per site.** A site's footprint is the sum of its segment
sizes, rounded up to the next power of two. That single CIDR is the site block,
so one prefix covers the site and remains summarisable towards the rest of the
network.

**Explicit blocks are validated, not trusted.** A site may declare its own
`address_block`. The planner rejects it when it is not a strict IPv4 CIDR
(`ENTERPRISE_ADDRESS_SPACE_INVALID`), when it is not inside the Enterprise space
(`SITE_ADDRESS_SPACE_OUTSIDE_ENTERPRISE`), when it is smaller than the site's
VLSM footprint (`SITE_ADDRESS_SPACE_TOO_SMALL`), or when it overlaps another site
block (`SITE_ADDRESS_SPACE_OVERLAP`). A segment may likewise declare its own
subnet and gateway; it is rejected unless the subnet is inside the site block,
the gateway is a usable host of that subnet, and the subnet satisfies the
computed demand (`SEGMENT_ADDRESS_SPACE_TOO_SMALL`, `SUBNET_OVERLAP`).

**Gateways and what each allocation records.** The gateway policy is
`FIRST_USABLE`. Each `SubnetAllocation` records the network, prefix, netmask,
gateway, first and last usable address, broadcast, usable hosts, required hosts,
growth percentage and reserved hosts, which is what makes an allocation
auditable after the fact.

**WAN transits.** Site-to-site transits are allocated as `/30`, one per pair,
with both endpoint addresses recorded in a `WanTransitAllocation`. An explicit
transit network must contain two distinct hosts in a `/30`, and the planner fails
with a typed error when no `/30` remains.

**Reconciliation.** `domain/enterprise/services/address_reconciler.py`
reconciles infrastructure IPv4 demand without silently renumbering existing
state, so a second pass does not quietly move addresses that are already in use.

## DHCP and static addressing

These are alternatives for the same hosts.

- **DHCP.** With DHCP enabled the classic planner emits one pool per LAN on that
  LAN's router, and one pool per VLAN in router-on-a-stick mode. Each pool
  carries the network, mask, gateway and DNS, and excludes the gateway address.
  Clients receive address, mask and gateway from the router; the server does not
  write those fields on the device.
- **Static.** Without DHCP, host interfaces are set directly, and each host also
  receives its gateway. The Enterprise path compiles DHCP pools as typed
  configuration actions with explicit excluded ranges, validated so that a pool's
  own gateway and reservations cannot fall inside a distributable range.

## IPv4 and IPv6 boundary

IPv4 is planned end to end by both paths. IPv6 exists only as a dual-stack
addition on the classic path, enabled with `dual_stack=True`:

- Router interfaces, including router-on-a-stick subinterfaces, receive a `/64`
  from `2001:db8::/32` by default, applied through the IOS CLI together with
  `ipv6 unicast-routing`.
- Hosts receive no static IPv6 address. They use SLAAC, because Packet Tracer's
  Script Engine rejects `addIpv6Address` on a host port. The deploy path enables
  IPv6 and address auto-configuration on the host instead.
- The Enterprise IPAM path is IPv4 only and rejects a non-IPv4 address space.

## Implementation and evidence

Everything above describes what the planners compute, which the offline suite
covers: subnet assignment, growth and reservation arithmetic, explicit-block
validation, pool generation and the typed errors.

What Packet Tracer does with those addresses is a separate question, answered
only by governed runs. Endpoint addresses are read back through one qualified
getter path (`infrastructure/execution/endpoint_address_observer.py`), and the
CP-SCALE records state which addressing and forwarding claims were established,
on which Packet Tracer build, and which remain unqualified. The authority for
that state is `reference/cp-scale/current_state.json`; see
[CP-SCALE qualification](architecture/cp-scale-qualification.md).
