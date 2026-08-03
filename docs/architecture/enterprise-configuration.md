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

Before mutation, `ConfigurationApplicator` checks the E4 semantic hash, runtime
device name/model identity, referenced physical interfaces, dependency graph,
and required capability status. Actions are submitted sequentially by phase and
batched per device. A failed prerequisite becomes `DEPENDENCY_BLOCKED`; an
unknown or explicitly unsupported capability becomes a structured `SKIPPED`
result and is never silently attempted.

IOS devices must reach the shared E3 `IosBootWaiter` state
`OPERATIONAL_READY` before their first configuration batch. Boot has its own
bounded budget and is not charged to a SHOW query. Trunk, L3, VLAN, and endpoint
state then use feature-specific convergence budgets; DHCP endpoint convergence
allows 30 seconds in Packet Tracer, while an individual IOS query retains its
shorter budget.

The Packet Tracer adapter reuses `configureIosDevice`, `configurePcIp`,
`StateConvergenceWaiter`, `ControlledIosExecutor`, and the existing typed SHOW
parsers. VLAN object state and endpoint IPv4/mask use bounded polling. Trunk and
L3 observations require a fresh current-query IOS window, so accumulated console
history cannot promote a feature. Packet Tracer 9.0.1 has no confirmed gateway
or DNS endpoint getter in this codebase; those DHCP fields remain explicitly
`UNOBSERVABLE` rather than inferred. Access-port and DHCP-pool getters are also
reported as observability limitations until independent APIs or behavioral
evidence are registered.

The default result is compact: it returns plan identity, source/config hashes,
counts by action/verification state, preflight errors, and duration. The plan
itself supports focused queries by device or typed action without dumping all
generated IOS. Application results also carry a backend-neutral runtime context
(`backend`, `backend_version`, and `capability_snapshot_hash`) for reproducible
evidence gates.

## Packet Tracer 9.0.1.0858 live baseline

The E5 controlled slices use only fresh `__MCP_E5_TEST_*` devices and restore
the original inventory after each run.

- L2: VLAN 910 was read back on both 2960 switches, both trunk endpoints were
  observed as 802.1Q `trunking` with VLAN 910 allowed/active, both endpoint
  IPv4/masks were read through structured getters, and a four-packet PC-to-PC
  ping had zero loss.
- Routed DHCP: a 2911 physical `GigabitEthernet0/0` was observed as
  `198.18.151.1`, `up/up`; the client obtained `198.18.151.2/24`; and a
  four-packet ping to the gateway had zero loss.
- DHCP gateway/DNS getters, direct DHCP-pool read-back, and direct access-port
  read-back remain `UNOBSERVABLE`. The successful behavioral paths complement
  but do not rewrite those field-level statuses.
- The 3560 SVI runtime remains `UNKNOWN`; compilation is supported, application
  stays capability-gated, and no unsupported inference is made.

Deferred features include DNS/HTTP/NTP/TFTP service hosting, telephony, ACL,
NAT, STP tuning, EtherChannel, first-hop redundancy, dynamic routing, IPv6
routing, redistribution, and QoS.
