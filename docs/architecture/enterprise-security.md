# E8 enterprise security policy

E8 consumes the immutable decisions produced by E4-E7 and adds policy-driven
enforcement. It does not recreate devices, addressing, services, or voice
provisioning:

```text
Concrete TopologyPlan       E4: exact devices, links, ports and layout
ConfigurationPlan          E5: L2/L3 identity and endpoint addressing
ServicePlan (optional)     E6: service address and transport semantics
VoicePlan (optional)       E7: call-control and phone identity semantics
SecurityIntent
           |
SecurityPlan               E8: placement, typed enforcement and acceptance
           |
 compile / apply / observe / positive and negative behavior / cleanup
```

Every `SecurityPlan` binds the semantic hashes of the source plans it actually
uses. Stale sources, missing foundations, model mismatches, and missing physical
ports stop application before mutation. E8 references E4-E7 decisions; it never
recompiles or repairs them.

## Plan boundary and domain model

Security has its own plan because policy placement, negative controls, and
security evidence have a lifecycle distinct from E5 configuration. The plan
still reuses E5's issue model, deterministic dependency sorter, execution
statuses, runtime target identity, and compact summaries.

Intent is semantic. A policy names a source segment and a destination segment,
E6 service, or E7 call-control identity. The compiler resolves those identities
to the concrete addresses, protocol metadata, device, and interface already
chosen upstream. Raw IOS ACEs, arbitrary interfaces, generic shell commands,
and user-controlled JavaScript do not exist in the domain.

The initial closed action set is:

- typed IPv4 extended ACL rules and exact interface attachments;
- static NAT, dynamic pool NAT, and PAT with compiled inside/outside identity;
- endpoint port-security on the exact E4/E5 access binding;
- DHCP Snooping and Dynamic ARP Inspection on compiled VLANs and trusted
  uplinks;
- bounded device hardening for MOTD and password encryption.

Static NAT accepts typed E5 endpoint-to-global mappings. Dynamic NAT requires an
ordered pool contained in the compiled outside segment. PAT uses the compiled
outside interface. Voice transport ports come only from E7 evidence. E8 does
not infer an RTP range from general Cisco knowledge.

## Determinism, placement, and policy analysis

Extended ACLs are placed inbound at the first E5 L3 boundary of the source
segment. Interface identity therefore comes from E4 plus E5, not from an LLM or
a free-form string. Reversing source and destination changes the deterministic
placement. When E5 exposes redundant L3 boundaries for the source segment, E8
attaches equivalent policy ACLs at every boundary instead of protecting only
the lexicographically first path. Rules sort by explicit priority and stable
policy ID.

The compiler detects exact contradictions, duplicate ACE semantics, and a
broad source rule that can shadow later rules. Backend implicit deny is modeled
in policy analysis. When the security default is allow, the compiler adds a
deterministic final permit action explicitly.

Policy ACLs use the extended numbered range beginning at 100. PAT source-match
ACLs use the standard range 1-99 because the reused NAT renderer emits a
source-network ACE without protocol or destination. Allocation uses stable
hashing plus deterministic linear probing, avoiding both range misuse and
collisions.

The plan semantic hash is canonical SHA-256 over all source hashes, actions,
dependencies, foundations, and verification expectations. Runtime transcripts,
hit counters, timestamps, and UI state never enter it.

## Application and evidence

E8 preserves four distinct states:

```text
COMPILED != APPLIED != DIRECTLY_OBSERVED != BEHAVIORALLY_VERIFIED
```

The Packet Tracer adapter renders only typed actions through the existing ACL,
NAT, hardening, and switch-security generators. IOS observation uses registered
queries in `ControlledIosExecutor`; there is no generic security CLI query.
Interface-bearing queries accept a validated interface parameter only.

Packet Tracer 9.0.1 rejects `terminal length 0`. When a registered query reaches
`--More--`, the executor records that the output is truncated and cancels the
pager with a fixed `TerminalLine.enterCommand(String.fromCharCode(3))` call.
Only the fresh current-query window is parsed, so old ACLs, translations, or
violation counters cannot satisfy a new check.

Registered E8 observations are:

- `show access-lists` plus `show ip interface <compiled-interface>`;
- `show ip nat statistics` and `show ip nat translations`;
- `show port-security interface <compiled-interface>`;
- `show ip dhcp snooping`;
- `show ip arp inspection`.

Hardening reuses the existing structured `getBannerMotd()` and
`getServicePasswordEncryption()` getters. It never reads or returns secrets or
credential hashes.

Capability profiles gate configuration, read-back, and behavior independently.
`PARTIAL`, `UNKNOWN`, `UNSUPPORTED`, and `UNOBSERVABLE` are not promoted to
`SUPPORTED`. A partially observable query may still return verified fields
alongside an unobservable field.

## Positive, negative, and cleanup controls

Every deny policy requires a working positive baseline before any security
mutation. A failed or unobservable baseline aborts the run. The strong
disposable-slice sequence is:

```text
ALLOW before policy
DENY after policy
ALLOW after typed cleanup
```

ICMP and HTTP operations are typed and derived from plan identities. NAT
verification requires successful inside-to-outside traffic plus a fresh
translation row or incremented NAT hit counter. ACL read-back alone cannot
prove enforcement.

DNS and voice behavior are reached only through injected typed E6/E7 adapters.
E8 never calls phone callbacks, screen coordinates, dial routines, or clicks.
Without that adapter, the result is `UNOBSERVABLE`. `SUPPORTED_UI`,
`APPLIED_BY_UI`, registration, and call verification therefore remain distinct
E7 evidence. The existing PC-through-phone 0/4 result is E7 debt and is not
diagnosed or reclassified by E8.

HTTPS, NTP, and TFTP likewise require their matching typed E6 operation. A TCP
or UDP policy with no modeled client operation is `UNOBSERVABLE`; E8 never uses
an ICMP ping as substitute evidence for a transport-specific ACE.

## Packet Tracer 9.0.1.0858 baseline

Controlled disposable probes established the following conservative matrix:

| Model / capability | Apply | Direct read-back | Behavioral proof |
| --- | --- | --- | --- |
| 2911 IPv4 extended ACL | supported | supported | supported, HTTP allow-deny-allow |
| 2911 PAT | supported | supported | supported, ping plus fresh translation evidence |
| 2911 static/dynamic NAT | compiled | runtime unknown | runtime not evaluated |
| 2911 hardening | supported | supported for banner/encryption | not applicable |
| 2960-24TT port-security | supported | partial: maximum/mode visible, sticky learning absent | not evaluated |
| 2960-24TT DHCP Snooping | supported | supported, including trusted uplink | not evaluated |
| 2960-24TT DAI | supported | partial: VLAN active; trusted uplink paginated | not evaluated |
| 2811 security | unknown | unknown | unknown |
| 3560-24PS security | unknown | unknown | unknown |

The ACL control used a 2911 with directly connected PC and Server. Fresh HTTP
content succeeded before policy, failed after the inbound deny was attached,
and succeeded after typed cleanup. ACL rules and the exact interface attachment
were independently observed. PAT used a separate disposable slice and verified
inside/outside roles plus an actual translation after a typed PC ping.

The hardening getter returns the IOS banner delimiter as part of the value
(`#text#`); the observer compares that real PT representation. Port-security
does not claim sticky verification while `Sticky MAC Addresses` remains zero.
DAI does not claim trusted-uplink read-back when pagination hides that row.

Every live slice used reserved `__MCP_E8_*` names, removed its devices and the
temporary power-distribution object, and restored the initial empty topology
with zero links. No `.pkt` file was saved.

## Deferred scope

Port-security violation behavior, rogue DHCP, ARP spoofing, voice-specific ACL
behavior, 2811/3560 security coverage, and simulator-specific limits remain
explicit follow-up evidence. STP tuning, RSTP/MST, EtherChannel, HSRP/VRRP,
dynamic routing, IPv6 routing, redistribution, advanced QoS, a general
AcceptanceEngine, DiagnosisEngine, and Autofix remain outside E8.
