# Server-PT SP-2: generalized DHCP and relay (risk L)

Work order `SERVER-PT-SP2-GENERALIZED-DHCP-RELAY-01` v1.0.0, SHA-256
`edeb6e45ef047a308b4d9cc6688f86ceb4cd3af44ccfd77297366c94e4889477`.
The operator authorizes implementation, offline delegation, feature-branch
publication, and owned disposable-lab LIVE investigation and acceptance for
SP-2. Delivery stops at `READY_FOR_REVIEW`; independent audit accepts the work.

## Identity and source boundary

- Checkout `Cisco-MCP-server-services-goal-foundations`; branch
  `feature/server-pt-goal-foundations`; clean starting commit
  `c6a77782d884cf2b2c21859146f5b17d19bb4c6e`, tree
  `ebd9bab939741b9ef4c1fde4820136dd596d98cc`. Its accepted SP-1
  predecessor is the starting commit. `cisco/main` resolves to
  `6263344e31ba3b0de6539d652f2cd06fc73a3562`.
- This checkout's `AGENTS.md`, `CLAUDE.md`, and
  `docs/engineering/standards.md` were read. The interactive Claude loader
  check is not observable here and remains pending. The checkout-local
  interpreter imports only `packet_tracer_mcp` from this checkout; that
  process check is not a substitute for a later LIVE process preflight.
- FM-REF 1.0.0 at `docs/reference/final-muejeje/Final-Muejeje.md` has verified
  SHA-256 `090238b17ddfc95b8f2dc1d637f18b462ad19b6ab5c0eec4eaf357ccf0cae37a`.
  Its bytes, IDs, provenance, and gap register are protected. It is
  requirements context, not a configuration, lease, or capability record.

## Problem, outcome, and provisional fixture matrix

The maintained public route currently delegates DHCP only when the Server-PT
host and selected clients share one segment. The only recorded native binding
is a narrow default `serverPool` policy with one or two PC-PT clients. A
configured pool or client address cannot establish the physical lease source.
The outcome is reusable, plan-derived Server-PT DHCP for selected wired PC-PT
clients in local and routed segments, with native lease identity and usable
gateway/resolver evidence, cold HTTP by IP, DNS, and hostname HTTP.

FM-REF identifies 87 PC-PT subjects, 80 complete PC address pairs across
eight data prefixes, and a largest recoverable PC population of 36 in
`172.16.1.128/26`. The other complete-pair populations are 6, 10, 13, 5,
3, 4, and 3. These are observed static-looking address pairs, not DHCP modes,
lease counts, or confirmed client gateways. Its nominal DHCP Server-PT is
`172.16.100.6/28`, but pool ownership, exclusions, relay, authority, and
physical attachment are unknown. Seven PC-PT subjects lack complete address
pairs. No missing fact is filled into that historical reference.

| Fixture | Engineering choice and demand | Question proved | Source boundary |
| --- | --- | --- | --- |
| Local capacity | Disposable local data segment; 36 simultaneously selected wired PCs, one policy-bound physical pool with at least 36 usable leases; vary /26 addressing, names and exclusions | Largest recoverable PC data-segment demand and exact physical pool attribution | The 36 count motivates capacity; fixture addresses and DHCP modes are chosen for SP-2 |
| Local independent pools | Two disjoint selected data segments with 13 and 5 simultaneous clients; hypothesize two named pools in one Server-PT `DhcpServerProcess` | Native named-pool selection, startup order, capacity, and no stock-default competition | Counts derive from recoverable PC populations; all policies are provisional. If the same-process hypothesis fails, record the failed discriminator and leave that domain unsupported; separate servers do not prove it |
| Routed relay | Server-PT on its own subnet, at least two client subnets at different sites, with 4 and 3 simultaneous clients, explicit relay interfaces and forward/return routes | Real intended-pool leases, per-segment gateway/resolver, cold routed services | Sites, relay, attachment and authority are fixture choices |
| Controlled negatives | Competing pool/default, conflicting authority, duplicate IP/MAC, wrong relay, missing return route, malformed or stale readings | Zero-effect admission and local/shared contradiction handling | No negative is attributed to Final-Muejeje |

The 36 simultaneous-lease target is a native measurement goal, not a claim of
current support. The initial LIVE target is Packet Tracer `9.0.1.0858` and
the existing `file` channel. Policy admitted by the public route is the
intersection of structurally valid IPv4 policy and a recorded capability
scope for the exact build/channel/pool strategy. Any unmeasured combination
of prefix, range, exclusions, pool count, placement, relay, or client count
remains refused or `UNKNOWN`. The existing one/two-client scope is retained
until new evidence justifies a separate record.

## Scope and architecture

In scope: intent-to-segment authority derivation before E5; typed E5 relay
configuration and observation on the client gateway; E6 native pool handling
and selected client lease evidence; plan-derived DHCP effect closure and
readiness; public service integration; bounded group sampling and durable
records; offline scale; owned disposable-lab LIVE campaigns; exact-scope
catalog entries and documentation. Existing E4/E5/E6 composition and the
four-input `pt_apply_enterprise_services` boundary remain the only product
route. Domain rules own authority, policy, path and evidence decisions;
application owns ordering and group lifecycle; infrastructure owns Cisco
scripts, IOS reads, transport and persistence.

Excluded: SP-3 through SP-5, wholesale Final-Muejeje replication, generic
DHCP capability promotion, explicit `dhcpRun` causality, renewal and
universal lease-table exhaustion claims, original Final-Muejeje or CP-SCALE
lab mutation, new bridges or raw-command bypasses, historical evidence
rewrites, merge to `main`, and a Final-Muejeje branch.

Authority is derived from the canonical selected client segment before E5:
one explicit DHCP service for that segment selects Server-PT; otherwise an
existing IOS/Voice segment policy keeps IOS/Voice; an explicitly DHCP-mode
client with neither authority is refused. An explicit site-level IOS owner
conflicts with Server-PT selection for a segment it owns. Duplicate Server-PT
claims, a client outside the declared segment, and an unresolved host are
refused. A requested remote Server-PT host must have its own resolved static
server segment and an explicit routed relay path; it is never silently moved
onto the client segment.

Before lease acquisition, the path model uses the selected client segment,
its gateway and client-facing relay interface, server address, and complete
forward/return routes. It requires attributed helper-address readback and
operational route/access readiness before any dependent acquisition. After
the lease, service readiness binds the freshly observed client IPv4, mask,
gateway, resolver and MAC to that same segment and path. No static stand-in
is compiled or used to unlock HTTP. A missing relay observation blocks only
its dependent group. Each fresh lease sample reads and indexes the intended
pool plus every relevant competing physical pool, including the stock
default, once per group; duplicated rows and cross-pool conflicts remain
visible. A shared scan trace is retained once with per-client references.

The implementation plan follows the established layers in order: derive
segment authority and validate address policy; compile relay and pool
actions; add attributed readback and lease joins; extend dependency/effect
closure and service order; prove offline behavior and scale; then perform
bounded native experiments and publish only measured support. Address
allocation avoids enumerating an entire large IPv4 prefix when only a
bounded selected pool is needed. Each causal defect gets a failing
regression before the owning-layer fix.

## Requirements paired with acceptance

| ID | Requirement | Acceptance and evidence |
| --- | --- | --- |
| SP2-01 | Exactly one authority per selected client segment; IOS/Voice stays authoritative where chosen; reject ambiguous or invalid policies before effects | Real-composition zero-effect tests for conflicting/absent authority, range, exclusion, capacity, and foreign-site identity; public support/refusal text |
| SP2-02 | Physical native pool strategy and startup order are known; multiple pools and simultaneous selected clients are supported only within measured bounds | Independent stateful-script stub tests plus native exact pool-row joins for each selected client; wrong/default pool negative; 36-client target measured or precisely blocked |
| SP2-03 | Relay interface, server target, client access and forward/return routes are in effect closure and observed readiness | Wrong helper/return route and shared-path negatives; remote clients on different subnets/sites hold intended-pool rows and complete routed services |
| SP2-04 | One indexed scan per pool/group/sample; repeated/conflicting identity rows and later shared contradictions survive local errors; usable mask/gateway/resolver and stable identity gate services | Malformed, stale, duplicated IP/MAC, conflicting pool and client-local reader regressions; per-client and shared cause records retained |
| SP2-05 | Four public inputs, observed DHCP client address, cold HTTP-by-IP first, then DHCP resolver/DNS/hostname; all selected clients recorded, including blocked | Product composition tests and native route with default catalog; request order, no static fallback, retention, uncertainty, cancellation and record-write failure |
| SP2-06 | Grouped O(N plus topology and lease rows) orchestration with finite work-based budgets | Real compiler/applicator/evaluator/store offline loads at 2/20/200/1000 constructed clients; counts, lookup work, response/record bytes, elapsed time, peak memory |

## Invariants and test levels

- Admission and capability resolution precede effects. An outcome-unknown
  mutation is quarantined without replay or channel fallback. Process,
  source, build, receiver, mailbox and cohort identities are proven in the
  exact LIVE execution process before any LIVE mutation.
- A setter is configuration, not a lease; an address in a range is not pool
  attribution. Missing, unreadable, foreign, stale or contradictory evidence
  never becomes absence or success. State usability is independent of
  `dhcpRun` causality and table-end calibration.
- Client-local failures leave later shared scans and identity checks active.
  Shared-path failures block only their dependents. SP-1 chronological
  revocation, direct-neighbor egress, durable causes and cold order remain.
- One active writer owns this worktree; offline subagents are read-only.
  LIVE has one lead and one owned mailbox. Historical archives and foreign
  processes are untouched. Allocations reserve bounded finalization before
  effects; exact-owned cleanup outcomes are recorded.
- Unit tests cover policy and lease input/output/error contracts. Integration
  tests use real E4/E5/E6 composition with substituted backend boundaries.
  System tests run the public route and persistence. Acceptance needs native
  Packet Tracer evidence for supported capability domains. Offline tests
  cannot establish native or relay support. CI and independent audit remain
  separate delivery gates.

## Current projection

Design recorded before product behavior changes. The current implementation
adds an internal typed E5 relay action and exact-interface IOS helper readback,
with a phase barrier before PC DHCP mode. The E6 plan can represent separate
remote client-segment pools, and the public admission path derives complete
planned route closure for the whole DHCP segment without inventing a client
address. An E5 operational readiness gate now samples selected access and
network paths before the mode effect; a separate E6 gate binds only a fresh,
stable, physically attributed lease to later HTTP/DNS readiness. Lease rows,
competing rows and malformed MAC representations remain explicit. These are
offline candidate controls, not Packet Tracer support claims.

The original recorded `serverPool` scope remains one/two clients. Router relay
capability stays `UNKNOWN`; there is no new catalog promotion for named pools,
remote DHCP, or 36 simultaneous clients. The SP-2 diagnostic campaign is
being integrated to answer the first native pool-selection hypothesis. Its
`SP2-NATIVE-POOL` stage uses two clients on an owned access segment and reads
the named pool and stock `serverPool` separately. It cannot establish native
capacity or relay. A fresh campaign ledger prospectively caps SP-2 at 20,000
operations and 21,600 seconds with 1,000 operations and 600 seconds protected
for finalization; the diagnostic stage itself is bounded to 440 operations
and 1,800 seconds. The first measurement must treat normalized-equivalent
MAC rows in either pool as competing identity, and an uncalibrated null as
unknown absence. Its current two-client procedure can report a positive
named-pool row while still returning `INCONCLUSIVE` for exclusive named
serving when it has not calibrated the default table's end in the same run.
That outcome calls for a different controlled native question, not a
capability promotion or a replay of the same fixture. Before any LIVE effect
it needs a clean exact source commit
and tree, episode allocation with protected finalization, owned process and
mailbox preflight, and an immutable result. Full product acceptance and
offline 2/20/200/1000 composition metrics remain open.

## Episode 1 native pool result (2026-09-27)

The first owned `SP2-NATIVE-POOL` episode executed commit
`a8b6274158b4346c6ccaba69ec8267730a015724`, tree
`a80a5d953cd05830ac3b09fd3a239159162b73ce`, on Packet Tracer
`9.0.1.0858` through the file channel. `M-SP2-POOL-IDENTITY` is
`NEGATIVE_OBSERVED`: both selected PC-PT clients had fresh native addresses
`192.0.2.2` and `.3` with exact IP/MAC lease rows in physical `serverPool`.
The named-pool rows were absent from an incomplete scan; the observation does
not establish why the native default won or that named serving is impossible
under another topology or startup policy. The configured named policy and
setter results are not lease attribution. No named-pool support entry is
promoted from this episode.

The stage finalized after 123 bridge operations and the campaign ledger
closed at 413.5273 seconds, with no unsettled phase. Fixture restoration was
proven; the qualification record separately reports `dirty_state=unknown`.
Maintained retirement exited only owned PID `30016`, and the fresh final
census found no Packet Tracer process, mailbox file or campaign lock. The
immutable e1 archive has 53 files and a verified `MANIFEST.sha256` digest
`70ddebdb578793ea252226584ceab87ec731d2697bf581e67089837e33a49a71`.

The next native question must change one causal condition: determine whether
the stock default competes with an independently configured named pool, or
whether relay `giaddr` selects the matching remote pool despite this local
negative. Use a new prospective episode and fixture/operation bound, with
readback of every physical pool and actual client identity; do not replay e1
unchanged. The 36-simultaneous-client target and remote relay/service
acceptance remain unmeasured. Offline full pytest on the executed commit
passed 8,444 with 6 skipped. Exact-SHA CI run `36340608026` passed quality,
docs, both Ubuntu jobs and Windows Python 3.13; Windows Python 3.11 is being
rerun after a timed simulated SP-1 fault test reported `group_deadline_reached`
instead of its expected down-interface cause on its first attempt.

## Episode 2 design delta (2026-09-27)

Episode 1 enabled both PCs' DHCP modes before writing the named pool. This is
an observed ordering confound, not an established cause of default serving.
Episode 2 changes that one causal condition on the same owned four-device
fixture: keep both PCs unbound while applying static server addressing and
observing forwarding; read the disabled physical `serverPool` baseline; write
and verify the named pool while the process is disabled; read both physical
pool configurations and bounded indexed lease windows; enable and read the
DHCP process; then enable PC1 only. Record its DHCP mode, IPv4, mask, gateway,
resolver, MAC and both physical lease windows in two separated samples. Enable
PC2 only if PC1 has two stable, usable binding samples, an exact named-pool
IP/MAC row in both, and a complete bounded default-pool window with no
observed competing row or identity conflict. This is a bounded probe-expansion
gate; an uncalibrated default-pool absence still withholds exclusive named-pool
support. Otherwise stop the client expansion
and retain the negative or unknown finding. No explicit `dhcpRun` is needed
for this startup-order probe. An unreadable binding or table end stays
unknown. A throwing or incomplete pre-client lease window may still permit
PC1 as an investigative sample, but it blocks PC2 and caps any apparent
positive at `INCONCLUSIVE`; a physical default row remains a negative finding
without a proven causal acquisition. Use a new versioned profile,
clean source commit/tree, prospective bounded episode, owned process and
mailbox preflight, protected cleanup and immutable archive.

Separately, code review found that generic E6 compiles `EnableServerDhcp`
before its named `ConfigureServerDhcpPool`. For multiple pools, changing each
service's local edge alone would still allow one process enable before all
pools are ready, because the dependency sort favors the enable phase. Correct
that product ordering with a failing multi-pool regression and a process-wide
pool-before-enable barrier after the native startup question is measured.
This remains a candidate causal correction; neither e1 nor offline tests prove
native named-pool or relay support.

## Episode 2 native pool result (2026-09-27)

The pool-first profile v2 executed commit
`865604e168ed068b598c7c141781b7954974a1f4`, tree
`f5e82dfb0ee8668847444b68027507797934cdb4`, on Packet Tracer
`9.0.1.0858` through the file channel. The named `MCP_E6Q_DHCP` policy was
verified while the process was disabled and both PCs were unbound. The process
was then enabled, and only PC1 entered DHCP mode. Two separated client and
physical-pool samples found PC1 at `192.0.2.2/24`, MAC `00E0.8FC4.9984`,
with an exact row in physical `serverPool`. PC2 remained off and unbound.
The named-pool indexed window threw on every attempted empty read, so its
absence and table end remain unknown. PC1 reported resolver `192.0.2.10`
but gateway `0.0.0.0`; this is not a usable intended policy binding.
`M-SP2-POOL-IDENTITY` is `NEGATIVE_OBSERVED` for physical default serving in
this fixture. The changed startup order did not prevent that result; this does
not establish that named-pool serving is impossible under relay or another
policy.

The stage used 106 bridge operations and completed without a primary or
secondary failure. Fixture restoration was proven and `dirty_state=clean`.
The owned PID `2528` and its helper exited; the final process and mailbox
census was empty with no campaign lock. Episode 2 closed with no open ledger
phase and 229 campaign operations committed across episodes 1 and 2. The
separate e2 archive has 72 files and a verified `MANIFEST.sha256` digest
`0d62078c603719ee4af034046159d0e7710ce4df277f42afc2e7494628cd2bd7`.
The named-pool, remote relay, simultaneous capacity, and product acceptance
claims remain `UNKNOWN`.

## Remote relay discriminator design (after episode 2)

The second local observation removes the PC-before-pool ordering confound but
still finds an exact `serverPool` row. The next diagnostic changes pool
selection context, not the public catalog: a client on a remote data subnet
requests through a configured router relay. Packet Tracer's maintained
readers do not expose the DHCP packet's `giaddr` bytes, so the measurement
will report relay-associated physical pool selection and keep direct `giaddr`
observation `UNKNOWN`.

Use a new versioned SP-2 diagnostic stage and a six-device, five-link owned
fixture: one Server-PT on an HQ servers segment, one PC-PT on a BR1 data
segment, two 1941 routers, two IE-2000 access switches, and one Ethernet WAN.
Compose all topology, E5 and E6 actions through the maintained intent and
compilers. Use explicit disjoint server/client prefixes separated far enough
that the auto-realigned physical `serverPool` range cannot overlap the
client pool. The provisional fixture uses HQ `10.72.0.0/29`, BR1
`10.72.32.0/29`, and an Ethernet WAN. An offline composition at build
`9.0.1.0858` produced six devices and five links with zero issues: server
`10.72.0.2`, BR1 client gateway `10.72.32.1`, helper on BR1 1941
`GigabitEthernet0/1` to `10.72.0.2`, a BR1 forward route via `10.72.64.2`,
an HQ return route via `10.72.64.1`, and named pool `BR1_DATA` at
`10.72.32.2`–`.3`. These are candidate compiled values, not LIVE readbacks;
the exact plan and manifest must be bound to any future episode grant. The
DHCP service uses `configure_only` so no explicit acquisition is dispatched.
Keep both segments, site roles and pool policy as engineering fixture
choices, not recovered Final-Muejeje facts.

The offline composition is reproducible from global address space
`10.72.0.0/16`, explicit HQ/BR1 site blocks `10.72.0.0/19` and
`10.72.32.0/19`, and explicit servers/data segments `10.72.0.0/29` and
`10.72.32.0/29` with `.1` gateways. HQ has one static `dns_server` role;
BR1 has one DHCP-mode `user_pc`. Its DHCP service selects the HQ server and
BR1 PC, `BR1_DATA`, `max_users=2`, `start_offset=1`, DNS `10.72.0.2`, and
`configure_only`. A fresh offline recomposition produced six devices, five
links, 19 E5 actions, two E6 actions, and zero issues. These constructed
values still need an exact hash-bound contract and stage before e3.

Before PC DHCP mode, require a fresh disabled Server-PT/default-pool baseline,
static server and switching results, exact client-facing `ip helper-address`
readback, operational forward and return route/interface readiness, and a
verified named-pool policy written while the DHCP process is disabled.
Read both physical pools before and after process enable, then activate only
the one selected PC. Take two spaced client mode/IP/mask/MAC/gateway/DNS and
indexed named/default lease samples. Exact physical IP/MAC attribution and
usable gateway/resolver are separate outcomes; unreadable pool ends and
unobserved `giaddr` never become absence or packet-level proof. Wrong helper,
missing return route, default-pool service and contradictory identities are
controlled refusal or negative paths. Retain the full pre-client and terminal
readbacks and protected cleanup result.

The stage remains private, exact-build/file-channel and single-client. It
does not promote relay, named pools, multi-site service or public support.
Its operation/time ceiling and protected finalization allocation will be
derived from the two access groups, two-router routed gate, E5/E6 calls,
repeated reads and six-device cleanup, then verified in an offline worst-case
test before a prospective e3 opening. The generic multi-pool E6 ordering
correction remains a separate product change with its own regression.

## Generic E6 process ordering correction (2026-09-27)

The real two-segment composition demonstrated that a generic named pool
depended on `EnableServerDhcp`. A new regression failed on that edge before
the correction. The compiler now gives each pool no enable prerequisite and
chains the pools on each Server-PT in stable order. Each enable retains its
own-pool dependency and waits for the last pool in that host's chain. The
dependency sorter and applicator use the resulting `depends_on` and
`apply_dependencies` closure, with linear edge count. Other hosts remain
separate.

Review exposed two boundary cases in that graph. A9 can exclude an optional
DHCP service after E6 compilation. Its projection must discard only the
compiler's pool barrier edges to omitted physical pools, then reconnect the
same host's surviving pools before enable; explicit dependencies still refuse
when their required service is absent. A same-host DHCP service cannot depend
on completion of another same-host DHCP service: the latter's process enable
must wait for every pool, so that request is a typed dependency-cycle refusal
before any effect. Focused real-composition regressions cover both cases.

The private D-DHCP pool-only projection now rebinds its direct server-state
readback from enable to the retained pool action, with an explicit rewrite.
Its later enable-only projection records the removal of pool dependencies
that the preceding diagnostic stage already applied. This preserves disabled
pool readback and a verified enable transition in staged diagnostics. The
current diagnostic seam description reflects the compiler's new source
order; historical evidence remains unchanged.

This fixes compiled action ordering only. Episode 2 already tested pool-first
startup and still observed a physical `serverPool` lease. Named-pool service,
relay selection, simultaneous capacity, and public admission remain unknown.
