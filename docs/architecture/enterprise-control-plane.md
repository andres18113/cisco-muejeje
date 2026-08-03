# E9 enterprise control plane and resiliency

E9 consumes the concrete identities already selected by the preceding
enterprise layers and adds deterministic control-plane policy, evidence, and
failure scenarios:

```text
Concrete TopologyPlan       E4: exact devices, links, ports and link roles
ConfigurationPlan          E5: VLAN, trunk, L3 and endpoint identities
SecurityPlan (optional)    E8: only explicitly consumed policy foundations
ControlPlaneIntent
           |
ControlPlanePlan           E9: protocol actions, expectations and faults
           |
 compile / apply / observe / behavior / failover / restore
```

E4 and E5 semantic hashes are mandatory. E9 binds the E8 hash only when
`security_policy_ids` names policies that the control-plane intent actually
consumes. A stale E4/E5 source, an E8 plan compiled against different
foundations, or an unverified foundational action stops application before any
E9 mutation. E9 does not recreate topology, addressing, trunks, services,
voice, or security policy.

## Why `ControlPlanePlan` is separate

Control-plane configuration has a lifecycle that does not fit
`ConfigurationPlan` or `SecurityPlan`. An IOS mutation being accepted does not
prove protocol state; protocol state does not prove forwarding; forwarding in
steady state does not prove convergence after a link failure; and convergence
does not prove that the injected fault was restored.

`ControlPlanePlan` therefore owns a closed set of protocol actions, their DAG
dependencies, required capability dimensions, direct-state and behavioral
expectations, and typed link-failure scenarios. It references exact E4/E5/E8
foundations rather than copying or repairing them. Its semantic hash covers the
source hashes and the canonical plan content, while runtime transcripts,
timings, counters, and observations remain outside semantic identity.

The runtime preserves these stages explicitly:

```text
CONFIGURED != APPLIED != OBSERVED != BEHAVIOR != FAILOVER != RESTORE
```

A result may be `APPLIED` and still be `UNOBSERVABLE`. Capability status is
gated independently for configuration, state/read-back, behavior, and
failover. `PARTIAL`, `UNKNOWN`, `UNSUPPORTED`, and `UNOBSERVABLE` are never
promoted to verified evidence.

## Closed protocol surface

The domain contains no raw IOS, generic CLI, arbitrary JavaScript, or
user-selected operational query. Every interface, VLAN, process number,
autonomous-system number, IPv4 address, wildcard, area, channel group, and
dependency is derived from typed E4/E5 identities and validated again at the
Cisco renderer boundary.

### STP, RSTP, and MST

`StpIntent` supports PVST, Rapid-PVST, and MST. Rapid-PVST is the Cisco
per-VLAN realization of rapid spanning-tree behavior used by the E9 RSTP
surface. The compiler selects participating VLANs from E5, assigns primary and
secondary roots deterministically, emits typed edge-port actions for PortFast
and BPDU Guard, and binds every action to its source VLAN/access action.

Root roles are materialized as deterministic priorities: 24576 for primary and
28672 for secondary. The renderer emits an explicit priority once and does not
also emit a conflicting dynamic `root primary` or `root secondary` macro. MST
maps every selected VLAN to exactly one typed instance and collapses root and
priority semantics at instance scope. A device cannot be both primary and
secondary for the same MST instance.

### EtherChannel

EtherChannel intent names at least two exact E4 member links joining the same
two devices. Each endpoint must have matching E5 trunk semantics, and a
physical port cannot be reused by another bundle or access binding. Channel
groups are deterministic and bounded. The closed protocol choices are LACP,
PAgP, and static `on`; the resulting action carries exact member interfaces,
`Port-channel` identity, allowed VLANs, native VLAN, source links, and source
trunk actions.

Only LACP and member-link failover have live evidence in the current Packet
Tracer baseline. PAgP and static mode remain typed offline capabilities, not
live-verified claims.

### First-hop redundancy

The current FHRP surface is deliberately limited to HSRP. E9 derives the
segment, physical addresses, virtual IPv4 address, group number, deterministic
priority, preferred active device, and preemption policy from typed intent and
E5 L3 foundations. VRRP and GLBP are not members of the action union and are
not accepted as free-form alternatives.

HSRP behavior through the VIP is separate from steady-state role read-back.
The former can be proved by forwarding; the latter requires a valid independent
observer and must remain unobservable when Packet Tracer rejects the relevant
SHOW commands.

### OSPFv2 and EIGRP for IPv4

Dynamic routing domains are closed to OSPFv2 and classic EIGRP IPv4. E9 derives
router IDs, canonical networks and wildcards, OSPF areas, passive interfaces,
and exact transit-link peers from E4/E5. OSPF process IDs and EIGRP autonomous
system numbers are bounded typed values. Overlapping routing domains would
require redistribution, which is outside E9 and is rejected rather than
invented.

Neighbor adjacency, learned-route state, end-to-end forwarding, failover, and
post-restore recovery are independent expectations. An observed process or
interface is not evidence of a neighbor, a route, or reachable traffic.

## Control-plane evidence versus forwarding evidence

E9 distinguishes two evidence planes:

- control-plane evidence comes from a registered, current-command IOS query
  with a parser backed by Packet Tracer evidence;
- forwarding evidence comes from a typed operation whose source and
  destination are plan-derived, currently a fresh `ping <validated-IP>`
  command window.

Registered production observers cover the live-fixture-backed STP,
EtherChannel, and simple OSPF query surfaces. HSRP role state and unsupported or
empty routing output remain `UNOBSERVABLE`; configuration acceptance is never
used as substitute evidence. Typed ping requires the current command echo and
fresh statistics, recognizes both PC packet counts and IOS success-rate output,
and cannot accept a raw destination or command suffix.

Unbound failover expectations are reported separately from executable failure
scenarios. They do not become verified merely because a related steady-state
action was applied or observed.

## Failure scenarios and mandatory restoration

A `LinkFailureScenario` names the exact compiled link endpoint, device,
interface, peer, cable, probe source, probe destination IPv4, expected surviving
links, and its failure/recovery expectations. The Packet Tracer renderer emits
only these ephemeral payloads:

```text
interface <compiled-interface>
 shutdown

interface <same-compiled-interface>
 no shutdown
```

Fault payloads never contain `write memory`. The inverse payload is rendered
before shutdown can be dispatched. `restore_required` is mandatory, and the
runtime attempts restore in `finally` after every attempted injection,
including mutation exceptions and convergence timeouts. If restore is rejected,
E9 records the cleanup failure and does not claim an `after` recovery.

The behavioral sequence is:

```text
before   stable reachable baseline; otherwise do not inject
during   expected forwarding state with the compiled link down
after    stable reachable recovery after accepted no-shutdown
```

Each state requires at least two consecutive fresh equivalent samples.
Changing, stale, missing, or exception-producing observations reset the stable
streak. `before`, `during`, and `after` remain distinct runtime artifacts with
their own status and convergence report.

## Packet Tracer 9.0.1.0858 live baseline

The following matrix is deliberately narrower than the typed offline action
surface. It records only the supplied disposable live evidence for this exact
Packet Tracer build.

| Capability | Live result | E9 interpretation |
| --- | --- | --- |
| Rapid-PVST and link failover | [OK] RPVST state/forwarding and failover verified | Supported for the evaluated slice; PVST and MST are not implied by this result. |
| EtherChannel LACP and member failover | [OK] LACP bundle and forwarding through member failure verified | LACP behavior and evaluated member failover are supported; PAgP/static are not live-verified. |
| HSRP VIP and failover | [OK] VIP forwarding and failover behavior verified | Behavioral HSRP evidence is supported for the evaluated slice. |
| HSRP steady roles | [ADVERTENCIA] `show standby*` is invalid in this PT build | Active/standby steady-state roles remain unobservable; VIP behavior does not prove them. |
| Simple OSPF | [OK] neighbor, route, and forwarding behavior verified | Simple OSPFv2 control-plane and forwarding evidence is supported for the evaluated slice. |
| Redundant OSPF failover | [ERROR] failed: stale route persisted and adjacency recovery timed out | Redundant OSPF convergence is not supported by current evidence and must not be promoted. |
| EIGRP | [ADVERTENCIA] process/interface observed; neighbors and routes empty; behavior unverified | EIGRP configuration evidence is partial, while adjacency, learned routes, forwarding, and failover remain unverified. |
| MST | [ADVERTENCIA] not evaluated | MST remains typed and renderable offline, with no live capability claim. |

These results are protocol- and scenario-specific. A successful simple OSPF
slice does not override the failed redundant OSPF experiment, and successful
HSRP forwarding does not manufacture a steady-role observer.

## Deferred E10 scope

E9 stops at deterministic planning, guarded application, evidence separation,
bounded failover execution, and mandatory restore. E10 is reserved for advanced
routing and address families: BGP, IPv6 routing, protocol redistribution,
route maps, tagging and loop prevention, and dual-stack path verification. E9
does not diagnose the stale OSPF route, clear adjacencies, restart protocols,
change priorities, rewrite topology, or retry with unplanned commands.

General acceptance, diagnosis, remediation planning, and autofix remain later
milestones; E10 must not absorb them accidentally. The current live failures
and unobservable fields are structured inputs to future layers, not permission
for E9 or E10 to guess a repair.
