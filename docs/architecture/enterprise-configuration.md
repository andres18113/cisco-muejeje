# E5 enterprise configuration

E4 and E5 have separate guarantees:

```text
EnterprisePlan + HardwarePlan
             |
             v
Concrete TopologyPlan       E4: devices, models, ports, links, coordinates
             |
             v
ConfigurationPlan           E5: typed configuration and dependencies
             |
      compile / apply / verify
```

E5 never selects a replacement model, physical link, interface, name, or
coordinate. Every interface in a configuration action comes from the source E4
`TopologyPlan`, whose semantic hash is embedded in `ConfigurationPlan`.

## Typed actions

The backend-neutral plan supports VLAN creation, data/voice access ports,
trunks, routed interfaces, SVIs, router subinterfaces, DHCP pools, static
endpoint addressing, and DHCP endpoint activation. There is no raw CLI action.
An infrastructure renderer converts this closed action set into validated IOS
batches only at the Packet Tracer boundary.

Actions carry stable IDs, phases, explicit dependencies, required capabilities,
and verification expectations. A deterministic Kahn topological sort enforces
dependencies with stable tie-breaking. Missing dependencies and cycles are
compile errors. Duplicate VLAN creation is normalized, access/trunk conflicts
are rejected, and IPAM is checked defensively for duplicate static addresses
and DHCP overlap.

## Addressing and VLAN policy

Segment intent remains authoritative. An explicit `segment.vlan_id` wins;
otherwise `ConfigurationPolicy.vlan_ids_by_role` supplies a deterministic
policy value. VLANs 1002-1005 and values outside 1-4094 are rejected rather than
renumbered. DHCP exclusions contain the gateway and every static assignment;
endpoint addresses are derived from the E2 `AddressingPlan`, never from an LLM.

Phone/PC passthrough is compiled as one switch-facing access action carrying a
data VLAN and a voice VLAN. The downstream phone-to-PC link is not treated as a
second switchport. Voice transport therefore remains distinct from telephony
service, which is deferred.

## Compile, apply, verify

`COMPILED`, `APPLIED`, and `VERIFIED` are different states. Compilation is pure
and can include a valid SVI action even when the target runtime capability is
unknown. The application preflight owns capability gating; operational
verification must use independent current-query evidence. Packet Tracer bridge,
TerminalLine, IOS session readiness, convergence, and runtime results do not
enter the Enterprise compiler.

Deferred features include DNS/HTTP/NTP/TFTP service hosting, telephony, ACL,
NAT, STP tuning, EtherChannel, first-hop redundancy, dynamic routing, IPv6
routing, redistribution, and QoS.
