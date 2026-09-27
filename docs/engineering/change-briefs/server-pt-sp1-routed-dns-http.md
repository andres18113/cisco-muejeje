# Server-PT SP-1: routed DNS and HTTP (risk L)

Work order `SERVER-PT-SP1-ROUTED-DNS-HTTP-01` v1.0.0 (2026-09-26), file
`Prompt_SP1_Routed_DNS_HTTP.md`, SHA-256
`df2291e7db938c4bd022b49286fb4934b226d7940b7355eaedc2ec78b793440e`. It
authorizes implementation, causal autofix, offline delegation, feature-branch
publication and owned-laboratory LIVE for SP-1 only. Delivery ends at
`READY_FOR_REVIEW`.

## Identity

- Checkout `Cisco-MCP-server-services-goal-foundations`, branch
  `feature/server-pt-goal-foundations`, starting SHA
  `890c950663d035cfe3d182c97a16a415bbb24522` (the last reviewed baseline, clean
  apart from the untracked operator `.mcp.json`).
- Authoritative base `cisco/main` = `6263344e31ba3b0de6539d652f2cd06fc73a3562`,
  an ancestor of HEAD; `cisco` is `andres18113/cisco-muejeje`.
- Interpreter `.venv\Scripts\python.exe` of this checkout; `packet_tracer_mcp`
  resolves to this checkout's `src`.
- `AGENTS.md` `a9f0e384...`, `CLAUDE.md` `29312201...` and
  `docs/engineering/standards.md` `1b4e2494...` were read from this checkout.
  The interactive `/context` loader check cannot be observed from this
  session and stays **pending**.
- FM-REF 1.0.0 was incorporated byte-for-byte in `7a3f1d3` at
  `docs/reference/final-muejeje/Final-Muejeje.md`: 233,815 bytes, SHA-256
  `090238b17ddfc95b8f2dc1d637f18b462ad19b6ab5c0eec4eaf357ccf0cae37a`, blob
  `1483914563813dc1b8b99884e4ef3f8734324946`, protected by a path-specific
  `-text` attribute. Its status, gap register and `exact_replication_ready:
  false` are unchanged; it is requirements context only, never runtime
  evidence, and SP-1 uses its own fixtures.

## Problem and intended outcome

The public four-input `pt_apply_enterprise_services` admits static PC-PT
clients only on the same site and segment as the Server-PT host. Every routed
dependency refuses at A8 as
`routed_path_unobservable:ipv4_routing_action_and_route_table_reader_unregistered`.
Investigation at `890c950` found the gap is wider than that message:

1. E5 compiles no inter-site routing at all, and materializes transit
   addresses only for serial WAN links; IPAM already allocates the Ethernet
   `/30`s and E5 drops them.
2. No registered observable reads a routing table (`show ip route` is
   registered only filtered by OSPF/EIGRP/RIP), and the client's gateway and
   resolver are "deliberately unobservable" in E5 endpoint verification.
3. The E4 hardware planner ranks models by port excess only, so every
   multi-segment design it emits carries a model whose required E5 capability
   is UNKNOWN (IE-2000/2950T-24 trunks, 1841 layer 3); the E5 applicator
   refuses such a plan before any effect.
4. The applicator orders verifications by expectation id, so every client's
   `svc/verify-dns/...` query runs before its `svc/verify-http-ip/...` request:
   the cold-by-IP order is violated whenever DNS and HTTP are both selected.
5. The DNS negative control is not qualified by a positive answer, and Packet
   Tracer prints the same "could not find host" text for an unreachable
   resolver and a nonexistent name.

Outcome: selected wired, statically addressed PC-PT clients consume DNS and
HTTP from separate Server-PT hosts across VLANs, subnets and sites through the
maintained deployment and public route, with plan-derived admission and
effect scope, fresh operational routed prerequisites, cold HTTP-by-IP first,
then resolver verification, DNS and HTTP by hostname, and durable per-client
evidence, while local/L2, DHCP, Voice, Printer and CP-SCALE behaviour stay
intact.

## Scope and exclusions

In scope: E4 evidence-aware model ranking; E5 Ethernet transit
materialization, static IPv4 routes and their read-back; the registered
`show ip route` reader; the routed path derivation, admission, effect closure
and operational readiness; the client gateway/resolver reader; the product
request order and qualified DNS negative; E6 evidence and records; scale
tests; an SP-1 campaign and governed LIVE runner; source-backed catalog
records; maintained docs.

Excluded: SP-2 (DHCP relay and generalized DHCP), SP-3 (SMTP/POP3), SP-4
(HTTPS qualification, nslookup), SP-5 (release integration); dynamic routing
changes, NAT, VPN, IPv6, HA, wireless; L3-switch SVI gateways as routed
service paths (see A-7); a new transport or monolithic acceptance runner;
merge to `main`; `feature/final-muejeje-non-iot`; mutation of CP-SCALE or
Final-Muejeje labs; rewriting historical records or grants.

## Requirements and acceptance

| Id | Maps to | Requirement | Acceptance | Tests |
| --- | --- | --- | --- | --- |
| SP1-01a | R-NET-01, R-B4/B7 | Each selected client-to-host dependency is classified from the compiled plans: local, L2 multi-access or routed; a routed path is admitted only when both gateways, the L2 legs to them and complete forward and return static-route chains are compiled | Admitted/refused decisions and reasons for local, inter-VLAN, 1/2-hop routed, missing forward route, missing return route, wrong next hop, next hop not adjacent, route loop, unplaced leg, SVI gateway, foreign-site host | `test_routed_service_paths.py` |
| SP1-01b | R-ENTRY, A10 | The E5 effect scope is the closure of the admitted paths' foundations: endpoints, access ports, VLANs, gateway subinterface/routed interface, switch side of the gateway attachment, transit interfaces, static routes and the trunks of acyclic L2 legs; nothing else | Exact mutated/excluded ids for each family; unrelated sites' actions excluded; stale hash, mismatched subject, unsupported model or E5 capability refuse before E1 with zero mutating calls | `test_routed_service_admission.py` |
| SP1-01c | R-A9 | Required ineligible services, explicit exclusions and retained results keep their semantics | Existing admission suites unchanged | existing |
| SP1-02a | R-B5/B6 | Before the first dependent request, fresh readings establish: client/host access forwarding (including the gateway-facing port), trunk continuity of cyclic legs, client gateway binding, gateway and transit interfaces up/up with the planned address, and a usable forward and return route chain | Sequences: LIS then timely FWD; exhausted sample then valid sample; late FWD; wrong next hop; route loop; missing return route; interface down; wrong switch/VLAN payload; route drift after an earlier admission blocks later dependents and is never regained | `test_routed_readiness.py`, `test_routed_readiness_gate.py` |
| SP1-02b | R-C2 | One routing-table and one interface reading per device per episode, indexed once, shared by every dependent of the group; revisions invalidate after relevant changes | Engine-call counts independent of client count; duplicate/conflicting rows retained and fail closed | `test_routed_readiness_gate.py`, scale |
| SP1-03 | R-COLD | In the product DAG every selected client's HTTP-by-IP request precedes any DNS query, hostname request or other client traffic of the invocation; no retry after an ambiguous outcome | Ordered request log for mixed DNS/HTTP intents; each first request retains marker-before, URL, mode/owner, start, timing and one release | `test_request_order.py`, existing cold HTTP suites |
| SP1-04 | R-DNS | Each DNS client's configured resolver is freshly read and must equal the planned address before its DNS query; a positive A record resolves to the expected address; a nonexistent name is VERIFIED negative only after the same client's positive; hostname HTTP needs both | Wrong resolver blocks only that client's DNS and hostname rows; unqualified negative is DEPENDENCY_BLOCKED; by-IP results are never revoked | `test_client_binding_reader.py`, `test_dns_qualification.py` |
| SP1-05 | R-ENTRY-06, A1-A4 | Record provenance, plans, scope, observations, first requests, releases; persistence loss, deadline, cancellation and receiver loss stop later effects; the reloaded record agrees with the response | Persist failure between effects, cancellation between clients, receiver replacement: no later ordinary effect, owned releases still attempted, no success | `test_routed_failure_boundaries.py` |
| SP1-06 | R-B3, R-C1-C4 | N clients over multiple VLANs and sites; no all-pairs or per-client whole-workspace reads | 2/20/200/1000 clients through real compilation, orchestration, evaluators and storage over a simulated routed campus; calls, bytes, time and memory measured | `test_routed_service_scale.py` |
| SP1-L | work order 5 | LIVE public-route acceptance | W1 inter-VLAN single gateway and W2 multi-site (three routers, a path crossing multiple routers), all selected clients, separate DNS and HTTP hosts, cold-by-IP first, then DNS and hostname HTTP, a qualified nonexistent-name negative and a pre-effect LIVE refusal | evidence package |

## Architecture and affected contracts

**A-1 E4 evidence-aware ranking (owning layer: hardware planner).** A WAN
router that must also be the site gateway prefers a layer-3-evidenced model
after the preferred model and the module count, so serial designs keep the
measured `819HG-4G-IOX` and Ethernet designs choose `1941`/`2911` over the
unmeasured `1841`. An access switch of a site with more than one segment
carries trunks, so a `supports_trunk`-evidenced model ranks first after the
PoE verification key. Single-segment sites (every existing Server-PT S1/DHCP
fixture) and the CP-SCALE reference planner are unchanged. The single-site
internet edge selection (`_layer_devices`) is deliberately untouched: CP-SCALE
pins its measured 819.

**A-2 E5 foundational routing (owning layer: configuration compiler).**
Ethernet WAN links between site routers are materialized from the existing IPAM
transit allocation exactly like serial ones. `ConfigureStaticRoute` (phase
`L3_ROUTING`, capability `supports_static_routes`, CLI `ip route <network>
<mask> <next-hop>`) is compiled only when the intent's
`routing_preference` is `static`: for every site router and every gateway
segment it does not own, the next hop is the neighbour on the shortest transit
path (breadth-first, ties by device id). Each route depends on its egress
transit interface. `STATIC_ROUTE` read-back is a fresh `show ip route` row with
code `S`, the exact prefix and the planned next hop. Other routing preferences
compile no routes, and their routed paths refuse naming the missing hop.

**A-3 Route-table reader (owning layer: IOS terminal registry).**
`OperationalQueryId.SHOW_IP_ROUTE` = `show ip route`, pagination-qualified
with the existing hard bounds, parsed to typed rows (code, prefix, length
inherited from a classful "is subnetted" header when a row omits it, distance,
metric, next hop, interface) plus the "Gateway of last resort" and
routing-disabled forms. A row it cannot parse is retained as unparsed, never
dropped, and makes the reading incomplete. The shape is derived from IOS and
must be confirmed by the first SP-1 LIVE capture before it can support
acceptance; a mismatch is a parser defect fixed from the capture.

**A-4 Routed path derivation (owning layer: domain).** A pure module derives,
per selected dependency, the client leg (client access switch/VLAN to the
switch port facing its gateway: same switch, or a compiled trunk component),
the host leg, both gateway interfaces, and the forward and return hop chains by
following the compiled static-route actions (longest prefix, next-hop address
resolved to the transit interface that owns it, adjacency required, bounded by
the router count, loops named). It returns the E5 action ids each leg and hop
needs. Single-gateway inter-VLAN is the chain of length zero. The admission
rule (`_unsupported_paths`) consumes it; the foreign-site guard now applies to
the host only. A cyclic L2 leg keeps S1c semantics (trunks proven by
continuity, not configured); an acyclic leg's trunks join the closure.

**A-5 Operational routed readiness (owning layers: domain rule, application
gate, infrastructure observer).** The readiness plan gains a routed group per
directed segment pair, naming its devices, required interfaces and route
predicates. The gate asks a new optional observer
`observe_routed_forwarding(devices, bounds)` for one bounded episode, which
reads `show ip interface brief` and `show ip route` once per device per round.
The pure evaluator indexes each reading once and walks both chains for the
group. Access groups add the gateway-facing port. Admission of a routed
dependent requires every group it names. After a group is admitted, any later
reading of one of its devices that no longer satisfies its predicate revokes
the group for the rest of the invocation (`route_drift_after_admission`); a
later valid reading does not restore it.

**A-6 Client bindings (owning layer: E6 runtime).** One bounded reader returns
the client's port address/mask, `HostIp.getDefaultGateway()` and
`DnsClient.getServerIp()` (documented in the bundled 8.1.0 IpcAPI reference;
DOCUMENTED, not SUPPORTED, until measured on 9.0.1.0858). New expectation kind
`CLIENT_GATEWAY` is compiled for routed client-host pairs and gates that
client's HTTP-by-IP request; `CLIENT_DNS_SERVER` becomes required for a
required DNS resolution and gates it. Both are state reads with no traffic.

**A-7 Explicit limits.** An SVI gateway on an L3 switch has no compiled
routing enable and `supports_svi` is UNKNOWN; routed paths through it refuse as
`routed_gateway_svi_unsupported`. Same-VLAN L2 paths keep S1c behaviour. The
WAN router is LAN-attached by the planner only when the intent sets
`internet_required`; the SP-1 fixtures set it for that reason alone (no ISP,
NAT or default route is compiled from it), and an unattached router's routed
paths refuse.

**A-8 Request order and DNS qualification (owning layers: domain rule,
applicator).** A pure rank puts HTTP-by-IP requests and traffic-free state
reads in phase 0 and every other client-traffic expectation (DNS, hostname
HTTP, HTTPS, NTP, TFTP, mail) in phase 1; `order_verification_expectations`
takes the rank as its first heap key, which is a barrier because no phase-0
expectation may depend on a phase-1 one (validated). The DNS negative control
depends on the same client's positive resolution.

**A-9 Catalog and campaign.** SP-1 LIVE runs under a new campaign identity
chartered by this work order, with experimental episodes on committed local
checkpoints and a delivery episode on published, CI-green source. Exploratory
episodes may inject candidate capability records through keyword-only seams
that the MCP tool never exposes. Closing SP-1 adds source-backed records
(`supports_static_routes` for the measured routers, the client binding reader)
and runs the public route with the default catalog.

Affected contracts: `ConfigurationActionType`, `ConfigurationPhase`,
`VerificationKind`, `ServiceVerificationKind`, the effect closure and run
record (routed paths and readiness rows), the capability catalogs, the tool
docstring and `docs/tools.md`. The four MCP inputs are unchanged.

## Invariants

- No effect before admission is complete; every refusal happens before E1 and
  reaches no mutating runtime call.
- Nothing outside the admitted closure is mutated; unrelated sites, VLANs and
  routes stay excluded.
- A configured route, a successful setter, a link-up flag or an aggregate
  PARTIAL is never operational evidence; only a fresh, complete, attributed
  reading is.
- Passive readiness never claims delivery; the service response is the
  end-to-end oracle.
- A shared contradiction blocks exactly its dependents; lost authority, lost
  persistence, deadline and cancellation stop every later ordinary effect.
- A timeout is not NXDOMAIN, a ping is not HTTP, a configured resolver is not
  a DNS exchange.
- Historical evidence and grants are immutable; LIVE is bound to its executed
  source.

## Test design

Unit: parser, transit/route compilation, E4 ranking, path derivation, route
evaluator, request rank, client binding payload rules. Integration: admission
and closure through the real use case with recording fakes; readiness gate
sequences with scripted observers; generated JavaScript under the maintained
Node harness. System: the registered MCP handler over a plan-driven SIMULATED
routed campus (switches, routers, route tables, client bindings, HTTP/DNS
answers derived from the simulated tables), real record store. Scale:
2/20/200/1000 clients. Acceptance: LIVE W1/W2 through the maintained deployment
and public route. Causal RED precedes each behavioural fix where a defect is
reproducible offline; documentation needs none.

## Current projection

SP-1 is implemented and accepted LIVE on published source: final W1 and W2
ran at `a04369a` (exact-SHA CI run 36306639618 green) through the registered
tool with the default catalog, and both VERIFIED. Evidence package:
`docs/reference/server-pt/evidence/sp1-routed-01/`. Delivery status is
READY_FOR_REVIEW. Starting SHA
`890c950`, base `cisco/main` `6263344`.

| Commit | What landed |
| --- | --- |
| `7a3f1d3` | FM-REF 1.0.0 `Final-Muejeje.md`, byte-for-byte (`-text`) |
| `f6a8542` | this brief |
| `7bd5011` | A-7: layer-3 evidence ranks gateway routers; trunk evidence ranks multi-segment access switches |
| `d6b4f38` | A-1/A-2: Ethernet WAN transit /30s, static routes along shortest transit paths (`CONFIGURE_STATIC_ROUTE`, phase `L3_ROUTING`), `ip route` rendering, `show ip route` parser and `STATIC_ROUTE` read-back |
| `f959b3c` | A-3/A-4: routed path derivation (gateways, L2 legs, forward and return chains) and admission with the routed effect closure |
| `f444d99` | A-5: routed readiness groups over fresh `show ip interface brief` + `show ip route` readings, sticky revocation on route drift |
| `3bba610` | A-6: request rank (every HTTP-by-IP before any DNS or hostname request), client gateway/resolver readers, DNS negatives qualified by the same client's positive |
| `8ffc299` | system tests of the registered tool over a SIMULATED routed campus |
| `9dbd0f2` | SP1-06 scale measurement |
| `35483ea` | campaign `SERVER-PT-SP1-ROUTED-01` bound to the archived work order |
| `2057070` | qualification stages `SP1-ROUTED-W1`/`W2`; refusal record `persisted_stage` fix |
| `ec638b8` | from LIVE e1: routed window per router, 20 s DNS read bound, resolver reader recorded (Q1 M-DNS-3), per-getter binding probe |
| `473db4a`, `0d15b14`, `c299ee9` | from three independent adversarial review passes: exact closure and routed-group coverage, candidate provenance, ledger settlement, and the whole intent bound to the run's canonical intent (a fourth pass approved) |
| `9ba3bb0`, `8492205` | immutable archives of LIVE e1 and e2 (`docs/reference/server-pt/evidence/sp1-routed-01/`) |
| `26ee053` | promotions from e2: measured 1941/2911 static routes, `client_gateway` via `HostIpProcess`; resolver and gateway reads become required prerequisites (SP1-04, SP1-02a) |
| `efa2352` | docs: routed scope in `tools.md`, the tool docstring and the architecture page |
| `9175fd6`, `8e27fde`, `b6368ab`, `fc57be2`, `9b05628` | SP1-03 at dispatch, from five further review passes (the last approved): a client's later traffic (DNS, negative control, host name) runs only once its selected HTTP-by-address request provably started; the reader records `request_started` only after validating the start and keeps it through later exceptions; no cross-service prerequisite remains |

LIVE (Packet Tracer 9.0.1.0858, file channel, owned disposable lab, each
episode opened, launched, retired and closed through the campaign ledger):

| Episode | Source | Result | What it established |
| --- | --- | --- | --- |
| e1, `SP1-ROUTED-W2` | `6e5e527`, candidate static routes | product PARTIAL, 367 ops | HQ inter-VLAN and BR1 (one transit hop) verified end to end; route tables complete, unpaged and parsed (`S`, `C`, `L`); BR2 refused only by the 30 s window (one three-router round took 32.4 s); `getProcess('HostIp')` throws on PC-PT; one routed DNS read missed the 5 s bound |
| e2, `SP1-ROUTED-W2` | `710faca`, candidate static routes | product VERIFIED, 413 ops | all six clients over one, two and three routers: HTTP by address first, fresh resolver read, DNS, qualified negative, HTTP by name; all three routed groups admitted; `HostIpProcess.getDefaultGateway()` returned every planned gateway; two terminal `brief` captures did not converge in six calls |
| e3, `SP1-ROUTED-W1` (final) | `a04369a` published, CI green, default catalog | product VERIFIED, 228 ops | both HQ inter-VLAN clients, every row including the product's own gateway and resolver reads; complete terminal capture |
| e4, `SP1-ROUTED-W2` (final) | `a04369a` published, CI green, default catalog | product VERIFIED, 423 ops | all six clients over one, two and three routers, every row; the three expected routed groups admitted once each; complete terminal capture |

Traceability to the maintained tests:

| Requirement | Tests |
| --- | --- |
| SP1-01a | `test_sp1_routed_paths.py`, `test_sp1_static_routing.py`, `test_sp1_evidence_aware_hardware.py` |
| SP1-01b | `test_sp1_routed_admission.py`, `test_campus_service_paths.py`, `test_sp1_routed_stage.py` (contract guard) |
| SP1-01c | existing admission suites, unchanged |
| SP1-02a/b | `test_sp1_routed_readiness.py`, `test_sp1_routed_readiness_gate.py`, `test_sp1_routed_observer_runtime.py`, `test_sp1_static_route_readback.py`, `test_sp1_request_order.py` (gateway prerequisite) |
| SP1-03 | `test_sp1_request_order.py`, `test_sp1_routed_public_route.py`, `test_sp1_cold_request_gate.py` |
| SP1-04 | `test_sp1_client_binding_reader.py`, `test_sp1_dns_window.py`, `test_sp1_routed_public_route.py` (wrong resolver caught by the read), `test_apply_enterprise_services.py` |
| SP1-05 | `test_sp1_failure_boundaries.py`, `test_sp1_routed_stage.py` (receiver replacement, cancellation, withheld route, ledger settlement), `test_sp1_routed_public_route.py` (durable record agreement) |
| SP1-06 | `test_sp1_routed_scale.py` |
| SP1-L | LIVE e3 (W1) and e4 (W2), final, default catalog; e1 and e2 exploratory. Controlled negatives LIVE: the qualified nonexistent-name control on every client, and e1's BR2 routed refusal before any of its requests (after E5 applied). NOT MET: the pre-effect LIVE refusal this brief lists was not performed; the product's pre-effect refusals (capability unknown, unsupported or incomplete paths, contract mismatch) are covered offline only |

Offline measurements (simulation, never Packet Tracer capacity): at 997
clients the routed run completes in about 54 s with a 9.7 MB response, a
31 MB record and 260 MiB peak; router reads are one episode per segment pair.
The simulated W2 stage spends 235 product dispatches (324 stage operations);
LIVE e2 spent 413 against a planned 2568 and a ceiling of 3000 / 3600 s.

Defects found and fixed on the way, each with a causal RED first: a refusal
after the write-ahead record stored `persisted_stage` none while the response
said `admission`; a fixed routed window refused a correct three-router path;
routed DNS reads could miss a 5 s bound; one guard around every binding getter
hid the resolver when the gateway process threw; and the review findings above.

Open:

1. SP1-L's own "pre-effect LIVE refusal" criterion is unmet (see the
   traceability table). The work order itself asks only for useful
   controlled negatives, which e1-e4 provide; whether to run one more
   episode for it is a reviewer decision, not silently dropped here.
2. Show-route pagination remains unqualified: every LIVE table fit one page,
   and paged reads still fail closed.
3. Independent review of the delivery; SP-2..SP-5 are out of scope.

## SP-1 readiness closure amendment (2026-09-27, risk L)

Work order `SERVER-PT-SP1-READINESS-CLOSURE-01` v1.0.0 starts from clean
`feature/server-pt-goal-foundations` SHA
`41bb624671d9a3a3c0177dea1012960ccf1e3727`, tree
`749204caabc00af237ef33f92cf19201e3c24625`; `cisco/main` is
`6263344e31ba3b0de6539d652f2cd06fc73a3562`. The checkout's
`AGENTS.md`, `CLAUDE.md` and engineering standard were read. Independent
interactive Codex and Claude instruction-loader checks remain pending. The
FM-REF file and every historical W1/W2 record stay byte-identical. Only this
amendment and its implementation may change current source and records.

### Requirements and verification pairing

| Id | Requirement and acceptance | Verification |
| --- | --- | --- |
| SP1-C1 | Inspect authoritative later rounds in chronological order. A contradictory route or interface observation withdraws only previously admitted, still-pending dependents whose chain it refutes; the withdrawal survives a healthy later round. Unknown, late, malformed, incomplete or foreign data creates no observed contradiction. Initial convergence and decided results remain valid. | Rule and gate unit sequences; product integration with a bad-then-good round in one later episode, actual request exclusion, record reload, and controls for permanent bad, separate episodes, unrelated and return-only drift. |
| SP1-C2 | A selected destination route must match the planned next hop and any printed output interface. Its next-hop address must have a uniquely consistent direct connected longest-prefix resolution through the planned transit interface; unresolved, ambiguous, recursive, shadowed and looping resolution refuses in forward and return directions. | Parsed-IOS unit tests and product integration for both directions, downstream exclusion and persisted causes; healthy W1/W2-shaped, L2 and independent-client controls. |
| SP1-C3 | Keep a bounded shared chronological cause for each withdrawal: dependent and source group/episode/round, changed router, relevant route and interface rows, cause and order. Existing run records hold the data after reload without per-client table copies. The normal routed sample also records next-hop resolution rows. | Durable row/reload assertions and scale counters including the actual 997-client maximum. |
| SP1-C4 | Preserve the public four-input API, registered IOS operations, native W1/W2 source identity and unqualified pagination boundary. | Public-route/system tests, affected suites, replay of archived W1/W2 readings through corrected pure rule if operations and parser remain equivalent; exact-delivery gate, namespace inventory, MkDocs, whitespace, CI and archive integrity. |

### Design and boundaries

The domain rule continues to use the indexed full `RouteTableReading`; it
checks direct adjacency by a second longest-prefix lookup of the next-hop
address in the **same** complete table. Every best row must be connected on
the planned egress interface. A route naming an output interface must name
that same interface. This deliberately refuses recursive next-hop routes;
there is no new IOS query, parser extension, generated operation or general
recursive-routing claim. The planned local and peer interfaces still need
their independently attributed up/up address readings.
The [Cisco IOS `ip route` command reference](https://www.cisco.com/c/en/us/td/docs/ios/iproute_pi/command/reference/iri_book/iri_pi1.html)
states that a next-hop-only route derives its output interface from next-hop
resolution and may use an unintended interface after a link change. That IOS
rule informs this direct-neighbor proof; Packet Tracer support is bounded by
separate observations.

The application gate consumes rounds in order and evaluates previously
admitted pending dependents immediately after each applicable authoritative
round update. It latches the first contradiction for each dependent. The
existing readiness record gains compact shared round facts and references
from revoked dependents, including the source group and episode. The
projection records only routes and interfaces used to explain those
withdrawals, including next-hop resolution, and stays bounded by observed
rounds and relevant devices. The usual last-round sample remains for the
current group's decision. No second persistence channel is introduced.

Module tests cover rule inputs and failure causes; integration tests exercise
the real gate and its observer contract; system tests run the registered
product entry, recording effect boundary and `ServiceRunRecordStore`; scale
tests exercise real compilation/evaluation/storage over simulated routers.
LIVE acceptance remains the immutable final W1/W2 observations from
`a04369a`/tree `d41ecc27`: 2 and 6 clients respectively. A pure evaluator
change can be replayed offline against their archived inputs; any changed
operation, parse scope, observable semantics or public execution requires the
smallest discriminating SP-1 LIVE measurement before a native claim.

The archived product readiness rows kept destination-route and interface
selections but **not** the next-hop longest-match rows newly required by
SP1-C2. The later qualification terminal captures do contain full tables,
and the corrected rule admits them offline, but those captures cannot be
substituted for exact readiness-time input. This missing historical input
prevents the requested exact replay. The smallest discriminating additional
measurement is one governed W2 run at the corrected, CI-verified source:
its BR1/BR2 paths exercise the direct-neighbor predicate, while W1's
single-gateway inter-VLAN path has no transit next hop. It will be a new
episode, never a retrospective modification of e3/e4. Prospective attempt,
process, operation/time bounds, finalization reserve and cleanup must be
frozen in the campaign ledger before Packet Tracer effects.

The original SP1-L table's pre-effect **LIVE** refusal remains historically
unmet. This closure's reviewer replaces that particular method with product
composition/admission tests at a recording effect boundary, asserting exact
zero calls, alongside the native W1/W2 success and each client's qualified
nonexistent-name negative. Episode 1's post-E5 refusal remains post-E5.
Pagination is still unqualified and fails closed. Offline scale is not a
native-capacity claim. Independent approval remains outside this delivery.

### Closure verification snapshot before the new LIVE measurement

Behavioral RED at `41bb624`: the real gate admitted a pending dependent
after bad-then-good rounds in one later episode; three parsed-IOS table
counterexamples (printed wrong egress, shadowing connected route and
recursive next-hop route) were also falsely admitted. All four failed for
the intended behavior before source correction.

The corrected tests now exercise chronological sticky revocation, permanent
bad and separate bad/good episodes, unknown-then-good, unrelated and
return-only drift, incomplete/duplicate/foreign rounds, initial convergence,
decided results, and a 200-client group referencing one shared contradiction
projection. Product tests enter through the registered four-input tool with
parsed IOS: a bad then good BR1 route read during BR2's episode leaves BR1's
already decided HTTP result intact, blocks its pending DNS call, admits BR2
on the later round and reloads the cause, source episode/round, router facts
and order. Forward printed-egress and return next-hop-shadow faults each
exclude the affected HTTP call, keep an independent HQ client working and
survive record reload. Existing composition/admission tests now assert zero
E5/E6 effect and verification calls for unknown static-route capability and
missing compiled routes, satisfying the reviewer's changed pre-effect method.

Offline scale uses real planning, the corrected rule, parsed IOS and the
record store with E5/E6 runtimes substituted. Nominal size keys
`2/20/200/1000` select **3/21/201/997 actual clients**. At 997 clients:
five routed groups, 15 router reads, four continuity episodes, 9,704,006
response bytes, 30,798,367 record bytes, 49.16 s and 261.9 MiB peak in the
local run. These are offline costs, not Packet Tracer capacity.

The archive replay test recomposes W1/W2 from each qualification run's
identity, matches the archived topology/configuration/service semantic hashes,
and feeds later complete IOS captures through the current parser and rule:
W1's one group admits 8/8 dependents; W2's three groups each admit 8/8.
The old readiness-selected destination routes and interfaces match those
captures (W1 4/2 selections, W2 24/12), but the old readiness projection
contains no next-hop selections. This is compatibility evidence across
timestamps, **not** exact replay of the original readiness input or a new
native observation. The executed `a04369a` source still matches current HEAD
in production/test/extension trees before this closure; the candidate diff
changes only the pure routed rule and application evidence/gate there. No IOS
operation, parser, generated configuration, observer or public MCP registration
changes. Original W1/W2 claims remain bound to `a04369a`.

The e3/e4 immutable archive manifests each list 103 files and verify with
zero missing, extra or mismatched entries; their manifest SHA-256 values are
`1b6cafee023cd34b7db0d72ed378e5a8e445ccd61e19974c075e9bfcbc17fc1b`
and `d912800a3ce226c360495e1457bccac680b25af3f7e7ec81eea90058a08ca03c`.
FM-REF still hashes to
`090238b17ddfc95b8f2dc1d637f18b462ad19b6ab5c0eec4eaf357ccf0cae37a`.
The original pre-effect LIVE negative remains unmet and the reviewer-approved
offline method replaces it. Pagination remains unqualified and fails closed.

Windows local verification before the new LIVE checkpoint: focused SP-1
routing/IOS/admission/observer tests 80 passed; affected services, Voice,
CP-SCALE and E95 subset 174 passed; final closure focus 50 passed; scale
four sizes passed; full suite **8,389 passed, 6 skipped, 3 warnings** in
989.77 s. The six unchanged skips are two unavailable symlink-privilege
cases, two absent machine-local/raw Voice evidence cases, and two opt-in
native-window tests. The three warnings are the existing pytest class-scoped
fixture deprecation in E95 tests. Provisional quality gate against verified
`cisco/main`, namespace inventory (zero active legacy imports/references),
MkDocs and `git diff --check` passed. Exact clean-tree delivery validation,
published exact-SHA CI and the new W2 result are recorded only after they
actually complete.
