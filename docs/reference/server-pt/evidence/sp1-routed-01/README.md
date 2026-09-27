# SP-1 routed DNS/HTTP: evidence package

Campaign `SERVER-PT-SP1-ROUTED-01`, experimental, chartered by the work order
`SERVER-PT-SP1-ROUTED-DNS-HTTP-01` v1.0.0. This page indexes the package; the
four episode directories are immutable and each is pinned by its own
`MANIFEST.sha256`. The design, requirements and traceability live in the
[SP-1 brief](../../../../engineering/change-briefs/server-pt-sp1-routed-dns-http.md).

## Identities

| Item | Value |
| --- | --- |
| Starting SHA | `890c950663d035cfe3d182c97a16a415bbb24522` |
| Base | `cisco/main` `6263344e31ba3b0de6539d652f2cd06fc73a3562` |
| Final LIVE source | `a04369a88298d452ce5a9043e160d2c14fe83ca5` (tree `d41ecc27d4fa92b846f43d06df37421c76fdca1a`), published on `cisco/feature/server-pt-goal-foundations` |
| Final LIVE CI | run 36306639618, success: quality, pytest Windows/Linux x Python 3.11/3.13, docs |
| Work order | `docs/reference/server-pt/assignments/Prompt_SP1_Routed_DNS_HTTP.md`, 17,976 bytes, SHA-256 `df2291e7db938c4bd022b49286fb4934b226d7940b7355eaedc2ec78b793440e` |
| Campaign grant | `SP1_ROUTED_CAMPAIGN` binds that exact digest; owned-laboratory LIVE, bounded force retirement of the verified owned cohort; allowance 40,000 operations / 36,000 s (protected 1,000 / 900) |
| FM-REF 1.0.0 | `docs/reference/final-muejeje/Final-Muejeje.md`, SHA-256 `090238b17ddfc95b8f2dc1d637f18b462ad19b6ab5c0eec4eaf357ccf0cae37a`, blob `1483914563813dc1b8b99884e4ef3f8734324946`, `-text` |
| Build, channel | Packet Tracer 9.0.1.0858, file channel, owned disposable lab per episode |

## Episodes

| Episode | Stage | Source | Catalog | Outcome | Ops | Active s | Manifest SHA-256 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [e1](e1/README.md) | W2 | `6e5e527` | candidate static routes | product PARTIAL; HQ and BR1 verified, BR2 refused by the 30 s routed window | 367 | 639.9 | `b68fdbd3...0ec8` |
| [e2](e2/README.md) | W2 | `710faca` | candidate static routes | product VERIFIED, six clients | 413 | 721.2 | `cc582ab5...0de84` |
| [e3](e3/README.md) | W1 | `a04369a` | default | product VERIFIED, two HQ clients | 228 | 370.3 | `1b6cafee...fc1b` |
| [e4](e4/README.md) | W2 | `a04369a` | default | product VERIFIED, six clients over one, two and three routers | 423 | 738.0 | `d912800a...a03c` |

Campaign ledger after episode 4: 1,431 operations and 3,103.98 charged
seconds used, no open episode. Every episode ended with fixture restoration
proven, maintained retirement of its own process
(`owned_qualification_restored`), and a final census of zero Packet Tracer
processes, an empty mailbox and no campaign lock.

## Acceptance (SP1-L) and per-client outcomes

The work order asks LIVE for an inter-VLAN, single-gateway workload and a
multi-site workload of at least three routers with a path across several
routing devices, all selected clients, separate DNS and HTTP hosts, cold
by-IP ordering, then DNS and host-name HTTP, and useful controlled negatives.

- W1 (e3): HQ-PC-01 and HQ-PC-02, data VLAN to the servers VLAN over the HQ
  1941 subinterfaces. Every row VERIFIED.
- W2 (e4): the two HQ clients, BR1-PC-01/02 over HQ and BR1 routers, BR2-PC-01/02
  over HQ, BR1 and BR2 routers. Every row VERIFIED.
- Rows per client, in rank order: gateway read (`HostIpProcess`), HTTP by
  address (run marker), resolver read (`DnsClient`), DNS A record of the run
  host name, nonexistent name qualified by that client's own positive, HTTP
  by host name. Addresses, marker and host name differ in every run.
- Controlled negatives LIVE: the qualified nonexistent-name control on every
  client of every run; the BR2 routed group of e1 refused before any of its
  requests while its tables were being read (after E5 had applied). Missing
  and wrong routes, down links, wrong resolvers, stale markers and
  unsupported shapes are covered offline (see the brief's traceability
  table), not LIVE. No pre-effect product refusal was run LIVE, although the
  SP-1 brief lists one; it is recorded there as unmet.

## Offline measurements

At 2, 20, 200 and 997 clients over simulated routed campuses
(`tests/test_sp1_routed_scale.py`): one routed episode per segment pair; at
997 clients about 54 s, a 9.7 MB response, a 31 MB record and 260 MiB peak.
The simulated W2 stage spends 235 product dispatches (324 stage operations).
These are orchestration costs, never Packet Tracer capacity.

## What is measured, simulated, inferred and uncertain

- **Measured (native, this build and channel):** the SP-1 composition applied
  and verified end to end through the registered tool with the default
  catalog; static routes on the 1941 and 2911 read back from fresh
  `show ip route`; unpaged route tables for this composition;
  `DnsClient.getServerIp` and `HostIpProcess.getDefaultGateway` on PC-PT;
  `getProcess('HostIp')` throwing on PC-PT.
- **Offline simulation only:** fault families (withheld or wrong routes, down
  transit links, wrong resolvers), receiver replacement, cancellation,
  persistence and ledger failures, and scale.
- **Inference, not claimed:** that other router models, larger route tables,
  dynamic routing, DHCP clients, other builds or the HTTP channel behave the
  same.
- **Uncertain:** pagination of long routing tables (paged reads fail closed);
  timing margins on slower hosts (a three-router readiness round took about
  32 s); independent acceptance (delivery is READY_FOR_REVIEW).
