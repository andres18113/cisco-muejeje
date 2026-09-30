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

The private contract composes the topology, addressed manifest, and final
DHCP intent in three passes. Before returning, it checks exact device and
link counts, models, ports, helper, routes, client mode, pool strategy,
Server-PT interface, exclusions and native pool policy. Its only device
capability candidate is `1941.supports_dhcp_relay`, which the default
catalog still marks `UNKNOWN`; a changed default relay status refuses this
private contract so its candidate attribution cannot drift. Generic named
Server-PT DHCP uses the existing
private E6 candidate records. The contract refuses another build, changed
topology, or an incomplete E5/E6 result. Candidate support in this contract
is a diagnostic input, never a public capability record or LIVE outcome.
The resolver must project `supports_dhcp_relay` from provenance-bearing device
evidence like other E5 capabilities; a private candidate can then reach the
typed relay action without modifying the default catalog. Missing evidence
still resolves to `UNKNOWN` and refuses at the effect boundary.
Touching the legacy resolver also brought that file under the current Ruff
gate: seven existing lint findings and its local formatting were corrected;
the intended semantic change is the relay capability projection alone.

For e3, project the real E5 plan to all compiled network, switch, relay,
route and server-address actions while omitting only the selected PC's DHCP
mode action and its expectation. Refuse a retained dependency on the omitted
action and give the projection its own semantic hash. The mode effect is a
later separate projection, admitted only after attributed helper and
forward/return readiness. Keep the remote stage unregistered until its
procedure, worst-case work budget, terminal reads and offline refusal tests
are complete.
The projection also removes a device row with no retained action, recomputes
each retained device's required capabilities, and refuses a readback that
still depends on the deferred mode action or expectation.

The composed pre-lease path has two access groups, no continuity group and
one routed group. Existing gate ceilings permit at most two episodes per
group: `2 × 2 × 181 = 724` access calls and
`1 × 2 × 31 × 2 × 12 = 1,488` routed calls, or 2,212 before effects and
physical samples. A prospective single-client stage may reserve 3,000
operations for its product procedure, 80 for terminal observation, 25 for
fixture setup and 15 for cleanup within a 3,200-operation ceiling and a
3,600-second clock with 420 seconds reserved for finalization. The remaining
788 product operations cover the 19 E5 actions, two E6 actions, bounded
pre-client and two separated post-client reads, and local observation
overheads. These are offline design bounds, not an episode allocation;
prove the worst case with the registered procedure before enabling the stage.

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

## Continuation at dbbc029: remote discriminator and product closure (2026-09-27)

This risk-L continuation starts from clean commit
`dbbc0297630d400c1d7c9ce327176cbff5e32433`, tree
`aebfa113b069ab1cbc8e76b129e04fb7f95aa8a2`, on
`feature/server-pt-goal-foundations`. The parent mandate and SP2-01 through
SP2-06 above remain the acceptance contract. No historical episode, FM-REF,
SP-1 behavior or public capability record is reinterpreted by this delta.

The next discriminator uses the existing six-device private contract to test
whether a remote selected PC receives a usable physical `BR1_DATA` lease
through the BR1 relay while `serverPool` remains a visible competitor. Register
a dedicated private stage only after its exact fixture/port and composed
intent/manifest/E5/E6 hashes, operation/time budget and protected finalization
are checked. Its one lead owns the file-channel session, record and cleanup.
The coordinator uses the current lifecycle, ledger, typed E5/E6 applicators,
readback/runtime ports, probes and store. It applies the pre-client E5
projection, observes access plus both routed directions and exact helper
readback, proves the DHCP process disabled by reading it, applies the named
pool before enable, then reads both pools around enable. Only then may it
apply the deferred selected-PC mode projection. Two separated client binding,
mode, IP, mask, MAC, gateway and resolver samples join exact physical pool
rows. Incomplete table termination stays unknown; a positive can claim only
relay-associated pool selection, not observed packet `giaddr`. A negative or
unknown stops dependent effects and retains terminal observations.

The stage has one bounded product procedure and one read-only terminal
procedure. The budget is derived from actual nested access/routed probe calls,
E5/E6 actions, snapshots, two samples, setup and cleanup; ordinary work may
never consume protected finalization. Stateful substituted-boundary tests
exercise admissible slow progress, operation and time exhaustion, early
negative, read failure, record-write failure, cancellation and receiver loss.
The stage was registered after initial successful and bounded-stop
coordinator tests. LIVE remains unopened pending focused/broad verification,
clean exact-SHA delivery and prospective episode authority.

The resulting native observation drives the unchanged product requirements:
segment authority and native pool policy stay fail-closed before effects;
physical attribution, observed client address and cold HTTP order gate routed
services; shared pool scans retain cross-client contradictions; and group
work scales with selected clients plus topology and lease rows. Public
capability entries are scoped to measured build, channel, placement, range,
pool strategy and simultaneous demand only. Offline system loads of actual
constructed 2/20/200/1000 clients measure work, bytes, time and memory but
cannot establish native capacity. Unit tests cover policy, dependency and
identity rules; integration tests cover real composition/applicators with
substituted runtimes; system tests cover the four-input route and store;
acceptance requires owned native evidence. Exact-SHA CI and independent audit
remain delivery gates.

### Routed gateway local-row correction

The stateful remote coordinator run exposed a requirements/implementation gap
in the pre-lease route gate: IOS emits an `L` host route for the selected
router's own gateway inside its connected client prefix. Treating that row as
a competing forwarding path rejects a valid whole-prefix observation. The
coverage rule now exempts only that exact gateway IPv4 on the expected
interface; another local host row or a more specific wrong route still
refuses. A failing focused regression preceded the correction. This changes
no SP-1 exact-client route rule or DHCP capability claim.

### Remote procedure budget and evidence corrections

The private remote procedure is capped at 3,000 product operations inside the
3,200-operation stage. The 25 planned setup, 80 planned read-only terminal
observation and 15 protected owned-cleanup operations retain independent
allowance; a product run that consumes its cap stops with an explicit cause.
The product time window ends at least 180 seconds before the ordinary phase
ends, preserving the terminal's four bounded IOS captures, three probes
and a 30-second authority/persistence margin;
420 more seconds remain protected for owned cleanup. Theoretical simultaneous
maximum IOS boot polling plus every readiness episode exceeds the successful
product cap, so that trace must stop, not overdraw. Stateful coordinator tests
cover both success and bounded exhaustion.

Two-sample usability needs a physical named-row association and usable client
binding in each sample. A malformed/repeated named scan or conflicting
normalized MAC/IP rows cannot support the claim. A read failure in the
pre-mode pool scan blocks client activation, while an uncalibrated cleanly
observed pool end remains an explicit limitation. Terminal support requires
four fresh complete uniquely attributed router captures, an observed server
snapshot and client binding, after the subject session was established.

### Exact private binding and observed identity

Before fixture effects, the e3 coordinator recomputes the physical topology,
manifest, E5 and E6 semantic hashes; compares exact device/link/port/selected
service bindings; and checks build, source chain, catalog and the E5-required
router/switch capability evidence. Ambient unrelated device capability fields
are not promoted; the actual capability snapshot digest is retained in the
record. A stale stored hash, wrong helper or missing route remains a refusal.

Each client probe needs exactly one selected device and FastEthernet0 answer;
duplicate/foreign answers are retained and unobserved. Indexed lease scans
retain duplicate pool answers and refuse them. Two-sample attribution refuses
malformed or repeated named rows, normalized IP/MAC conflicts, and rows above
the physical configured capacity. Terminal support requires complete raw IOS
captures with exact unique router identities plus the enabled named policy and
a usable DHCP-mode client binding; an early negative retains its raw terminal
facts without becoming support.

### Controlled coordinator budget traces

The e3 product cap comes from the registered experiment's planned operations,
not an independently hardcoded allowance. In a substituted 250-operation
stage with a 120-operation product allocation, the real coordinator counted
23 setup, 120 product, 19 terminal and 14 finalization calls (178 total),
recorded `budget:sp2_remote_product:operation_budget_exhausted`, and proved
owned restoration. The 72 refused calls were never dispatched. At simulated
elapsed 3,001 seconds in the registered 3,600-second stage, the product-only
time cap recorded `budget:sp2_remote_product:time_budget_exhausted`; the
terminal still ran and owned restoration was proved. These traces establish
bounded stops and reserve separation, not native serving or capacity.

## Episode 3 remote relay result (2026-09-28)

`SP2-REMOTE-RELAY` profile v1 executed clean commit
`9f93721f128f7e9ced2a151ba0a83870efe8872a`, tree
`62582242a459ac18ea30d93b30aaf5c2a5f8057d`, on Packet Tracer `9.0.1.0858`
through the file channel, attempt `37f799295fbf7c1ecee0da9f53bb5055`. Before
opening, the local full suite passed 8,513 with 6 skipped, the clean
exact-commit delivery gate, namespace, whitespace and MkDocs checks passed,
and exact-SHA CI `36368695039` succeeded in all six jobs. The episode was
opened prospectively with 3,210 operations and 4,200 seconds.

The stage stopped with `sp2_remote_helper_readback_unverified` after 120
bridge operations. All six fixtures, both hostnames, VLANs, access and
gateway ports, four routed interfaces and both static routes verified. The
BR1 helper action was applied, but its fresh
`show ip interface GigabitEthernet0/1` readback was executed and fresh
without being a complete attributed capture, so it stayed `UNOBSERVABLE`.
No pool, process-enable or client-mode effect followed. The fixture
restoration was proven with `dirty_state=clean`. `M-SP2-REMOTE-POOL` and
`M-SP2-REMOTE-FINAL` are `INCONCLUSIVE`. Relay, named-pool serving and
capacity remain `UNKNOWN`; this is not a relay negative.

The first maintained retirement posted `WM_CLOSE` and refused to answer the
owned Exit prompt after its window set changed. The recovery retirement found
the owned PID already absent, so no owned `process-exit` record exists and the
exit is not attributed. The final census found no Packet Tracer process,
mailbox file or campaign lock; the ledger closing states
`process_absent_exit_unattributed`. The campaign then committed 349
operations and 1,211.65 seconds. The e3 archive has 95 files and
`MANIFEST.sha256` digest
`239877576e9f08d95754f22a458cea18af0870c540622eff109df7a4451b8771`. Future
retirement recovery should follow a prompt refusal immediately.

### Relay helper pager correction

The record retains no raw helper output, so the failing attribution condition
was derived from code: a non-qualified query that meets the IOS pager keeps
its first page as truncated evidence with `output_complete=False` while its
window remains fresh. Every other IOS read of the same routers verified with
the same identity rule, and PT 9.0.1 rejects `terminal length 0`. A failing
regression drove the real `ControlledIosExecutor` and relay verifier through
an independent paged-terminal stub with synthetic two-page output; the pager
was never advanced and the helper stayed unobservable. The correction adds a
separate registered identity, `SHOW_IP_INTERFACE_HELPER`, with the same
per-interface command. Only the relay readback uses it, and only it is
pagination-qualified under the unchanged hard page, byte and time bounds.
First-page `SHOW_IP_INTERFACE` readers for ACLs, the control plane and SVI
readiness polling keep their current behavior and call counts. An unattributed
helper read now names executed, fresh, complete, pager, page-count,
truncation and identity facts in its bounded message without raw terminal
text. The next governed helper capture is this query's first native page-count
evidence. Touching the legacy terminal test file brought it under the current
Ruff gate: its imports and formatting were normalized and its tests gained
docstrings, with no semantic change beyond the pager guard.

## Episode 4 remote relay result (2026-09-28)

Profile v1 executed clean commit `81f7821cc2ef150283132d01e80689f36ae948d2`,
tree `25d04fea60d1c5edd601732123aa290b6587f243`, attempt
`05a97b2af74fc9c078d0fe9c4a4f0898`, on `9.0.1.0858` through the file channel.
The local full suite passed 8,516 with 6 skipped at that commit. The stage
completed without a primary failure in 273 operations and proved restoration
with `dirty_state=clean`. The maintained retirement observed the owned exit,
the final census was empty, and the ledger closing is `verified_clean`.

The pagination-qualified helper readback verified the BR1 helper natively.
Access and both routed directions were admitted. The process was read
disabled, `BR1_DATA` was written and read while disabled, the process was
enabled and read, and only the selected PC entered DHCP mode. Both separated
samples, 2 seconds apart after the mode effect, read the PC in DHCP mode at
`0.0.0.0/0.0.0.0` with gateway and resolver `0.0.0.0`. Every indexed read of
both physical pools threw at index 0, an empty-table signature whose end is
still uncalibrated. `M-SP2-REMOTE-POOL` is `INCONCLUSIVE`: no lease was
observed from either pool within the window. This neither supports nor
refutes relay serving.

The server's static endpoint row verified address and mask, but its gateway
and resolver stayed unobservable, because that verifier reads the `HostIp`
getter that throws on this build. The static writer is the same
`configurePcIp` path SP-1 used for routed service replies, so a missing server
return hop is possible but unobserved. Two confounds therefore remain: the
two fixed 2-second samples may precede a slower relayed exchange, and the
server's return hop was never read.

### Remote profile v2

Profile v2 changes only these observations. Before the mode effect it reads
the Server-PT binding through the maintained binding reader and requires the
planned address, mask and default gateway. Every getter that answers without
error, including the SP-1-measured `HostIpProcess`, must name that gateway.
Otherwise it stops with `sp2_remote_server_gateway_unverified` and makes no
client effect. After the mode effect it reads the selected client passively
every 2 seconds, for at most 30 reads, until a non-zero, non-link-local
address appears. The two separated samples and their assessment then follow
unchanged, so exhausting the window is a retained finding, not a retry.
Nothing is sent to the client beyond the one mode effect: no `dhcpRun`, ping
or warm-up. The 30 reads fit inside the unchanged 3,000-operation product
cap and its time window.

Stateful regressions reproduced e4 before the change: a lease arriving after
20 later evaluations left v1 with e4's five causes, and a dropped server
gateway went unnoticed. With v2, the delayed lease is observed and supported
in sample, an exhausted window keeps both samples without support, and a
dropped gateway stops before client mode. All 40 remote-stage tests pass,
including the budget, time-cap, cancellation and receiver-loss traces.

## Episode 5 remote relay result (2026-09-28)

Profile v2 executed clean commit `3541ff5b502e0dbf414d477cae9efc9e591b2136`,
tree `3586174635021e92665ae12735bcf05ec1c676e1`, attempt
`7612f2f54796e2c20939425cb969d934`, on `9.0.1.0858` through the file channel.
The local full suite passed 8,519 with 6 skipped at that commit. Exact-SHA CI
`36451482659` for its parent `81f7821c` succeeded in all six jobs. The stage
completed in 281 operations without a failure and proved restoration with
`dirty_state=clean`. The owned exit was observed and the ledger closing is
`verified_clean`. The campaign has committed 903 operations and 1,923.06
seconds.

The Server-PT binding read `10.72.0.2/29` with gateway `10.72.0.1` through
`HostIpProcess`, while `HostIp` threw. After the selected PC's mode effect,
six passive reads saw `0.0.0.0` and the seventh, about 14 seconds later,
saw `10.72.32.2`. Both separated samples then read DHCP mode, `10.72.32.2`,
mask `255.255.255.248`, gateway `10.72.32.1`, resolver `10.72.0.2`, lease
`1 days 0:0:0` and MAC `0002.4AC9.9676`. Each sample joins an exact IP/MAC row
at index 0 of physical `BR1_DATA`. Every `serverPool` read threw at index 0.
The terminal read four complete uniquely attributed router captures, the
enabled named policy and the usable DHCP-mode binding.
`M-SP2-REMOTE-POOL` and `M-SP2-REMOTE-FINAL` are `SUPPORTED_IN_SAMPLE`. The
archive has 122 files and `MANIFEST.sha256` digest
`736eb8f42ef06f9e2fc55bdb7d90ef33a0aecae6914a527f8a39924de1872e5b`.

The supported claim is narrow: on this build and channel, one remote PC-PT
behind a 1941 `ip helper-address` held a usable sampled binding from the
matching physical named pool. Packet `giaddr` bytes, the ends of both tables,
exclusive serving, renewal, `dhcpRun` causality and capacity remain
unobserved. The e4 negative was an observation window, not a relay failure.

Together with e1/e2, this defines the next product strategy: segments that
share the Server-PT's subnet are served by the native `serverPool`, whose
range the server realigns to its own address; routed segments are served by
per-segment named pools through an attributed relay. Both are physical pool
strategies of one Server-PT authority. Acquisition evidence must allow a
bounded window well beyond two seconds. Public support still requires the
product route, multiple segments and sites, simultaneous clients and the
routed service sequence.

### Remote profile v3: the product order

The public product sets a remote client's DHCP mode in E5, before E6 writes
the pool and enables the process. Episode 5 used the reverse order, so it
cannot show that a relayed client already in DHCP mode acquires after a later
enable. Profile v3 changes only that order, and it observes each pre-effect
condition. Before the mode effect, v3 requires:

- a pre-mode scan that reads the named pool absent and `serverPool` observed,
  with no row for the client's MAC in either;
- the server's planned gateway, as in v2.

After the mode effect and before the pool write, it requires:

- the client read in DHCP mode and still unbound;
- the process read disabled with only `serverPool`.

Otherwise it stops before any E6 effect. E6 then receives the verified mode
foundation together with its identifier. The pool, the enable, the passive
acquisition window and the two samples are unchanged.

Offline tests show that a client in mode before enable acquires only when the
engine retries on enable. That is a simulation setting, not native evidence,
so a retry-disabled control keeps both samples without support. Three new
regressions stop on a named pool present before mode, a client bound before
the pool and a process enabled before the pool; none applies the pool. All 43
remote-stage tests pass. One episode on an owned lab measures the native
answer; a negative result would put the product's mode-first order for
remote clients in question.

## Episode 6 remote relay result (2026-09-28)

Profile v3 executed `bef524dd` on Packet Tracer `9.0.1.0858` through the file
channel in 280 operations, archived at `e6/` in commit `1c0d8a50`. The remote
BR1 PC entered DHCP mode first and was then read in mode at `0.0.0.0` with the
process disabled and only `serverPool` present. After `BR1_DATA` was written
and the process enabled, the client read `10.72.32.2/29`, gateway
`10.72.32.1` and resolver `10.72.0.2` on passive poll 4 (about 8 s). Two
samples join an exact IP/MAC row in the physical `BR1_DATA` pool, and
`serverPool` read empty. The claim is a sampled, relay-associated named-pool
binding in the product's mode-first order. It does not observe `giaddr`,
exclusive serving or capacity. Cleanup was verified clean.

## Step 2 design delta: two physical pool strategies (2026-09-28)

Evidence now supports two physical strategies on one Server-PT. A client
segment that contains the server is served by the native `serverPool`
(e1/e2, DHCP autonomy e8 to e10). A remote client segment reached through
exactly one helper is served by a named pool for that segment (e5, e6). The
public route must compose both on one host without either strategy breaking
the other. Codex's read-only map at `1c0d8a50` confirmed these gaps.

Decisions:

1. **Strategy selection (compiler).** A `state_only` DHCP service selects its
   strategy from placement. A local segment keeps the existing native binding
   and its recorded scope. A remote segment compiles a named physical pool,
   derived from the segment or given explicitly, together with its one exact
   E5 helper. It is admitted only through a new exact record
   `Server-PT:dhcp_relay_named_pool_binding` with the same provenance fields as
   the native record. The default catalog does not carry that record, so the
   public route refuses remote `state_only` before E5 until a private product
   stage supplies a candidate. No default record is promoted.
2. **Host-wide pool admission (compiler).** Before any effect, the pools of
   one Server-PT must have distinct physical names, never the name
   `serverPool` for a named pool, and disjoint networks. The process-wide
   exclusion union must not intersect any pool's lease window. Violations
   refuse the whole host's DHCP services with zero effects.
3. **Native-first order (binding, reused at A9).** The native pool's
   pristine-state transition requires one pool and no exclusions, so it runs
   first on its host. Named pools follow in stable order. The native enable
   waits for the last pool, and every non-native enable on that host also
   waits for the native enable. A9 strips edges to omitted pools and omitted
   enables before rebinding.
4. **Mixed-process native checks (runtime).** After the native transition,
   the native enable and server readback accept exactly the planned
   additional physical pools and the planned exclusion union. An unplanned
   pool or exclusion is still a conflict. The native mode guard stays for
   local clients only; remote clients keep the ordinary E5 mode path.
5. **Named-pool state verifier (runtime).** `state_only` on a named pool
   reuses the usable-state loop. Each sample reads the server policy, the
   client's fresh mode, address, mask and MAC, the intended pool row, and
   every other physical pool on the process for competing rows of the
   client's MAC or IP. Two stable joined samples produce the existing
   `attributed_to_effective_server_pool` claim. A competing row contradicts,
   and an unreadable competing pool leaves the claim inconclusive. The
   apply-services lease gate is unchanged.
6. **Readiness.** The E5 pre-DHCP routed gate and the E6 lease-bound gate
   remain separate decisions.
7. **Scale.** An offline 2/20/200/1000 harness drives the real compiler,
   applicators, evaluator and store and reports constructed counts, scans,
   bytes, time and memory. It is not native capacity.

Holds: the native one/two-client scope and its `/24` literal stay; the relay
record is absent from the default catalog; SP-3 to SP-5 remain excluded.
Tests are written RED first per decision, from compiler to runtime.

### Step 2 review corrections

An adversarial Codex review of the working tree found three defects, each
fixed from a failing regression:

- **Transport scope.** A9 kept a run on the recorded file channel only when
  the selected plan held the native pool. A named-only plan, including one
  left after A9 drops an optional native service, could run over HTTP. A9 now
  refuses any recorded pool binding, native or named, off the file channel.
- **Unplanned pools.** Competition was read only from planned pools. A named
  pool's server readback does not pin the process inventory, so a named
  group sample now reads the inventory through the documented
  `getPoolCount`/`getPoolAt` and scans every other pool, planned or not. An
  unreadable or oversized inventory (over 64 pools) leaves competition
  inconclusive. The native readback now also checks the companion names, not
  only their count, so a native sample pins its inventory and scans only its
  planned companions. A single-pool native snapshot is unchanged, and the
  recorded e11 samples still replay to their verified rows.
- **Scan cost.** Before any effect, one host is limited to 64 planned pools
  and 1,024 planned lease rows, since every sample may scan every pool of the
  process. These are offline budgets, not Packet Tracer capacity.

A second review pass found two more, also fixed from failing regressions:

- **Verifiable pool size.** A named pool above 255 leases could never show
  its terminating null within the 256-read scan, so its evidence could not
  complete. The compiler now refuses a named pool above 255 leases.
- **Same-dispatch inventory.** A mixed native snapshot relied on the
  inventory from the earlier server readback, so a pool added between the two
  dispatches went unseen. The snapshot now reads the inventory itself and
  requires it to equal the planned names.

A third pass found the same race in the legacy single-pool native snapshot,
which the verifier could still mark verified after a pool appeared. Every
native snapshot now reads its inventory in the same dispatch and requires
exactly the planned names. This is an explicit oracle delta: the recorded e11
snapshots carry no inventory, so the current reader leaves them inconclusive
as recorded; with the single-pool inventory the process had, every other
decision and value replays unchanged. The archive itself is untouched.

A fourth pass found that the named-pool writer could add a pool and
process-wide exclusions without inspecting pools already on the process.
Before any setter, it now reads every other pool through the documented
inventory calls. It refuses on an unreadable inventory, an overlapping
network, or a new exclusion inside another pool's lease window. In the
offline fixture the stock `serverPool` realigns to 512 addresses from the
server's network, which covers the branch exclusions, so a named-only plan
there is refused unless that default is narrowed first. This is a real
fail-closed outcome, and the stock pool's native window matters for relay
placement.

Passes five and six found four more pre-effect gaps, each fixed from a
failing regression. The named writer now also refuses a new pool when the
inventory already holds 64 pools, when an existing process-wide exclusion
falls inside its lease window, or when another pool's stored lease range
overlaps it, whatever that pool's declared network. A7 now refuses a
supported native or relay binding whose build or Packet Tracer version
differs from the deployed build, including in an injected catalog.
Pass seven found that the pool budget ignored the stock `serverPool`: a
named-only host with 64 planned pools passed admission and then stopped
after partial writes. A host without a planned native pool now counts the
stock pool against the 64-pool budget.
Pass eight found that a named-pool scan cut short by a read error, or
ending at its bound, could still attribute a client from one matching row.
A named snapshot now reads one row past the pool's capacity and requires a
clean terminating null; otherwise the group is inconclusive
(`named_pool_scan_incomplete`). The native pool keeps its recorded
contract, whose limitation already states that a positive row does not
establish the table end.
Pass nine found that a named pool smaller than its selected clients was
written before its verifier refused it. The compiler now refuses a named
state-only pool whose capacity is below its selected client count.
A tenth pass, on the committed Step 2 diff, found that a relayed pool
explicitly named like the native service's logical label (for example
`HQ_DATA`) was admitted and written, after which the native readback, which
treats any pool of that label as stale, refused the verified process. The
readback now accepts that label exactly when it is a planned companion; the
pinned inventory comparison still refuses any unplanned pool of that name.
A mixed public-route regression and a four-case readback unit reproduced it
first.

### Step 2 offline results

Unit and composition tests cover strategy selection, refusal by the default
catalog, host conflicts and budgets, native-first ordering and A9 narrowing,
companion stamping, and the local-only native mode guard. The public use case
runs over the Node engine with an explicit per-client pool setting, which is
a test scenario and not a selection rule. In that setup every local client
joins `serverPool` and every relayed client its segment's named pool. A lease
from the wrong pool, a competing row in a planned or unplanned pool, and a
named-only plan on HTTP are each refused.

The scale harness keeps the real E6 runtime and grouped verifier; router
effects are recorded and routed readiness is rendered from the plan. One
native HQ client plus relayed branches measured:

| Clients | Services | Group scans | Dispatches per client | Response bytes | Record bytes | Seconds | Peak MiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | 2 | 4 | 16.0 | 14,249 | 132,407 | 0.37 | 1.7 |
| 21 | 5 | 10 | 7.8 | 85,715 | 732,242 | 1.34 | 6.3 |
| 201 | 5 | 10 | 6.2 | 755,708 | 5,057,260 | 9.23 | 38.7 |
| 997 | 5 | 10 | 6.0 | 3,552,751 | 23,444,735 | 91.14 | 175.7 |

Group scans follow services and samples, not clients. A 1,001-client plan is
refused at A7 by the existing reporting budget of 1,000 clients, before any
effect. None of this is native capacity, relay or selection evidence. The
default catalog still has no relay record, so the public route refuses remote
`state_only` until a recorded binding exists.

## Step 3 design: private mixed product stage (2026-09-28)

Step 2 composes both physical strategies on one Server-PT, but no native run
has driven the product through a local native pool, relayed named pools and
the routed service sequence together. The public route also still refuses
remote `state_only` DHCP because the default catalog has no relay record.
Step 3 measures that composition once, privately, before any record is
promoted.

Stage `SP2-MIXED-PRODUCT` runs under the SP-2 campaign on build `9.0.1.0858`
over the file channel only:

- **Fixture.** The product designer's composition of one fixed intent: three
  chained sites HQ, BR1 and BR2 with static routing; one Server-PT at HQ on
  the HQ data segment `10.80.1.0/24` at `10.80.1.10`, hosting DHCP, DNS and
  HTTP; five HQ PCs, three BR1 PCs and three BR2 PCs, all in DHCP mode. BR1
  uses `10.80.16.0/28` and BR2 `10.80.33.64/27` with a start offset, so the
  three pools differ in prefix, window and placement. The routers, switches,
  ports and cables are whatever the designer composes; the stage lists them
  and refuses any drift.
- **Policy.** HQ is local, so the native `serverPool` serves it with five
  leases from `.100`. BR1 and BR2 are remote, so each gets a named pool and
  one helper on its branch gateway. BR2's relay path crosses two routers.
- **Services.** Three `state_only` DHCP services, one DNS record and one HTTP
  page, both run-derived, for all eleven clients: cold HTTP by address, then
  resolver, DNS, the negative control and HTTP by name.
- **Private candidates.** The relay record
  `Server-PT:dhcp_relay_named_pool_binding` cites episodes 5 and 6. A native
  scope candidate names exactly this network, server, gateway, resolver,
  exclusions and at most five leases, while the default record stays
  `192.0.2.0/24` with two. Device candidates give `supports_dhcp_relay` to the
  1941 and 2911. None of them touches the default catalogs.
- **Entry.** The stage calls the internal `apply_enterprise_services` with
  those catalogs, as the Q3 private branch did, because the registered
  four-input tool cannot take a service catalog. Its record carries the
  injected-catalog limitation.
- **Binding.** Before any effect the coordinator recomputes the topology,
  manifest, E5 and E6 hashes, compares devices, links, ports and the selected
  services, and checks the build, file channel, source identity and a digest
  of the candidate rows. Any difference refuses.
- **Acceptance.** `M-SP2-MIXED-PRODUCT` is supported only if the product
  reports `VERIFIED`, completed and persisted, and for every client the lease
  is verified and attributed to the intended physical pool (`serverPool` for
  HQ, the segment's named pool otherwise), with gateway, resolver, HTTP by
  address, DNS, negative control and HTTP by name verified. Every server
  state row must verify, and every branch pre-lease and service routed group
  must be admitted.
- **Terminal.** `M-SP2-MIXED-FINAL` keeps router captures, every client
  binding, the server's pool inventory and one bounded scan per pool.
- **Budget.** Operation and time ceilings come from an offline run of the
  real coordinator over a hybrid simulation: the Node engine answers the
  DHCP server and client scripts, and the routed campus answers IOS, DNS and
  HTTP from the leases the engine assigned. The stage has 3,200 operations
  and 3,600 seconds with 420 reserved for finalization.

A positive result is private candidate evidence. It justifies exact-scope
catalog records for this build, channel, placement and policy only; no
default record changes until then. A negative narrows the domain or names
the next discriminator. The 36-client capacity episode is designed
separately after this result.

### Step 3 offline results

The stage, its contract composer and its coordinator are implemented through
the existing composition, lifecycle, ledger, runtimes and record stores. The
designer composes the fixture as 18 devices and 17 links: a 1941 at HQ and
BR2, a 2911 at BR1, an IE-2000 per site, the Server-PT and eleven PC-PT
clients. The helpers are on BR1 `GigabitEthernet0/2` and BR2
`GigabitEthernet0/1`. The contract pins the run-independent topology,
configuration and manifest hashes and the digest of the whole private service
catalog. It also recomputes the run's canonical intent, checks each physical
pool per segment, both helpers, the candidate device evidence and the eleven
clients' seven checks each.

Offline, a hybrid simulation drives the real coordinator and the real
product. The Node engine answers every endpoint script: the DHCP server and
clients, and a new `dns_server_stub` knob for the server's DNS calls and name
resolution. The routed campus answers every router and switch. A product
script naming both sides fails the test. Results:

- The positive trace verifies all eleven clients in their intended pools and
  all seven checks, both pre-lease and both service routed groups, every
  server state and the terminal. The product used 389 dispatches (198 to the
  campus, 191 to the engine); the stage used 516 of 3,200 operations.
- A relayed client answered from `serverPool` is not supported, and the
  stage stops with `sp2_mixed_product_not_verified`.
- A changed intent value or an extra service candidate stops before any
  product dispatch.
- A route missing from E5 readback stops the product with
  `e5_contradiction`; no DHCP setter runs and the process stays disabled.
- A return route lost after E6 starts blocks BR2's services and its routed
  group, while every HQ and BR1 client still verifies.
- A 300-operation grant stops ordinary work at its cap and still runs the
  terminal and owned cleanup; a cancellation mid-product is recorded and
  cleaned up; an unwritable product record refuses at A6 with nothing
  configured.

These results prove binding, composition, evidence handling and bounded
stops, not native serving, relay or capacity.

An adversarial review of the uncommitted stage found that the terminal
counted client binding rows without checking them. The probe returns a row
for every requested client even when its port lookup fails, so eleven rows
did not prove eleven observations. The terminal now requires exactly one row
per selected client, with the device and port found, no row error, and the
resolver and at least one gateway getter answered. A regression with one
failed port lookup reproduced the false support first.

A second pass found three more terminal gaps, each reproduced by a stage
regression before the correction. A pool absent at the final scan counted as
scanned; an emptied binding row still passed; and a complete router capture
without proven identity counted as that router's table. The terminal now
reuses the remote stage's rule of one fresh, complete, uniquely attributed
capture per router and query. It also requires the enabled process with
exactly the three planned pools, a present scan of each, and every client's
final address inside its planned pool with that pool's mask, gateway and
resolver.

### Native table-end correction (before episode 7)

The third review pass on the terminal led to the archived native scans. On
build `9.0.1.0858`, `DhcpPool.getLeaseAt(index)` never returned null in any
SP-2 episode. Every index at or past a pool's row count threw
`invalid vector subscript`: empty pools threw at index 0, and the one-lease
`BR1_DATA` of e5 and e6 returned its row at index 0 and threw from index 1.
Cisco's reference does not document out-of-range reads, and there is no
lease-count getter.

Step 2's pass-8 rule required a terminating null before a named pool could
attribute a client, and competing pools needed one too. The Node engine
returns null, so every offline test passed, but natively every relayed and
every mixed local client would have stayed inconclusive. A mixed
public-route regression with the engine set to the native end reproduced
this: all six clients were `unknown`.

The product's group snapshot now reads exactly that throw text as the end
of a table, and only when the next index throws the same way. The mission
allows this: an uncalibrated end must not block a narrower usability claim,
so the verified row names the limitation
`lease_table_end_by_out_of_range_throw`. Any other error, a row after the
throw, or a categorized error text still leaves the table unread and the
claim inconclusive, as a second regression shows. The terminal applies the
same rule to its final scans: rows contiguous from index 0, exactly one per
client's final address, within capacity, and only nulls or the measured
throw after them. The mixed stage tests now run with the native end.

A fourth review pass found two more gaps, each reproduced first. The scan
script caught a throw from reading a returned row's fields in the same place
as a throw from the index call, so a last row whose MAC getter threw the end
text read as an empty tail: a competing pool then looked empty while it held
a row, and BR1 clients verified over it. Only the index call can now end a
table; any field failure leaves it unread. The terminal also joined leases by
address alone. It now reads each client's MAC in the same terminal and
requires every pool's rows to join its clients one to one by address and
MAC, with repeated or malformed scans refused.

A fifth pass found three more, each reproduced first. The E6 plan was
checked only against its own hash, so a changed service value with a
recomputed hash passed binding. The coordinator now also pins a normalized
plan hash, 6e978c7e..., in which only the run-derived marker, its digest,
the host name and derived action identities are abstracted. Three different
run identities normalize to that same value. The shared lease-calibration
probe caught a failure to read a returned row's fields together with a
failing index call, so the terminal could not tell them apart. It now
records ield_throw for a field failure, which the classifier still treats
as an error. The terminal also reads two indices past a full pool and
requires every later index to end by a null or the measured index throw.
Finally, the product ran without its own cap and could consume the required
terminal's allowance. It now runs under the ledger's ordinary limit of its
2,800 planned operations, leaving 240 seconds, as the remote stage does. A
300-operation grant stops the product and still completes the terminal.

A sixth pass found that the terminal did not require the final client
readings to be in DHCP mode, so a client switched to static addressing after
verification, keeping its address and lease, could still support the
terminal. Every final reading must now be in DHCP mode; a regression with
one client's mode read as off reproduced it first.

### Capacity design defect: trunk evidence for a hierarchical single segment

Composing the 36-client demand as one branch data segment exposed a designer
defect. Thirty-six users need two access switches, so the site becomes
hierarchical and every access uplink to the distribution pair is a trunk.
The planner asked for trunk evidence only when a site has more than one
segment, so it chose the 2950T-24, whose trunk support is `UNKNOWN`, and E5
then refuses those trunks as capability-unknown before any client can be
reached. A site that needs more access switches than a flat design allows
now chooses among trunk-evidenced models whenever one fits, exactly as a
multi-segment site already does. A site that fits one switch is unchanged.
A failing composition regression preceded the correction.


## Recovery continuation v1 (2026-09-29, risk L)

Authority: `SERVER-PT-SP2-RECOVERY-CONTINUATION-02` v1.0.0 from the
operator-supplied recovery assignment, extending the unchanged parent mandate.
Starting checkout is `Cisco-MCP-server-services-goal-foundations`, branch
`feature/server-pt-goal-foundations`, commit
`d03fb1cfaf913f2097510f2677a3b96c618b0463`, tree
`e822e1cceb8a4617af09d1f8bdaa95a6af333d57`; the tree and index were clean.
The active AGENTS.md, CLAUDE.md, engineering standard, parent assignment and
current brief were read. Interactive loader verification remains pending.

The intended outcome and SP2-01 through SP2-06 above remain required. This is
active implementation, not phase acceptance. One integration writer and one
LIVE owner work here; three read-only investigations cover trunk provenance,
lease-end semantics, and the adjacent SP-1 terminal observation.

### Recovery design and verification plan

1. Reproduce C31 commissioning failures. Forward-revert the scoped planner and
   test delta of `82c70970`, retaining history and the other SP-2 changes. Its
   single-segment trunk ranking is withdrawn pending a compatibility solution;
   the earlier paragraph describing delivery is superseded by this decision.
   Preserve C31's exact reviewed models, links, inputs and guard. Prove new
   36-client hardware suitability through existing legitimate composition/model
   inputs or a versioned profile, with no campaign-name or client-count exception.
2. Inspect original preliminary trunk evidence via the commissioning store.
   Verify raw readbacks, source/build/model/interface, result meaning, integrity
   and cleanup before scoped reuse. Configured trunk capability, forwarding,
   and redundant-path behavior are separate claims. Historical records and
   consumed grants remain immutable.
3. Qualify the native scan-end convention through maintained composition for
   the exact source/build/file channel/reader contract. Infrastructure decodes
   native strings into evidence semantics; domain predicates consume those
   semantics. Retain physical pool, ordered rows, first failure and confirming
   observation plus provenance. Empty/one/multiple/full scans and stateful
   negatives cover field failures, other errors, malformed/duplicate/conflicting
   rows, cap exhaustion and a row after an alleged end. Unknown contexts refuse.
4. Reproduce and narrowly fix invalid SP-1 terminal row counting. Inspect
   accepted original fields to distinguish terminal and acceptance consequences.
   Keep static SP-1 independent of DHCP-mode requirements; rerun coexistence.
5. Validate focused regressions, full affected commissioning/SP-1/DHCP/Voice/
   Printer/CP-SCALE suites, then full local pytest with a test-only bridge token,
   quality/docs/namespace/whitespace and clean exact-commit delivery checks.
   Publish fast-forward and inspect every exact-SHA CI job before new LIVE.
6. Recompute fresh mixed/capacity contracts, durable helpers, hashes and episode
   arguments from the executed source. Verify current ledger and ownership;
   reserve terminal/cleanup before activation. Measure simultaneous physical
   pools and 36 usable attributed leases, cold HTTP by IP, resolver/DNS and
   hostname services. Budgets follow compiled plans, scans and polling; the
   120-second lease window must be evaluated against measured workload.
7. Integrate only observed support into scope-bound default records and exercise
   the registered four-input public route. Independent review and complete
   requirement/evidence dispositions are required for READY_FOR_REVIEW.

Unit levels cover scan decoding/predicates and policy; integration levels cover
real generated scripts, composition, terminal and persistence; system levels
cover coordinator/public-route behavior and full offline scale; native acceptance
covers measured lease capacity, attribution and services. No applicable level is
waived. No LIVE is admitted on a failing execution baseline. SP-3 through SP-5,
main merge, Final-Muejeje construction, foreign resources and historical edits
remain outside this continuation.


### Recovery findings and dispositions

Containment commit `472fe973` forward-reverts `82c70970`; the rejected commit
remains in history. Commissioning reproduced 19 failures and 18 passes at the
reviewed source, then the rollback passed 44 commissioning/hardware tests.
A versioned profile now replaces that temporary containment: `segment-count-v1`
reconstructs commissioning inputs; default `site-hierarchy-v2` ranks suitable
trunk-evidenced hardware for new hierarchical workloads. Manifest-bound
composition recognizes v1 only when its complete physical hash matches the
persisted manifest. Explicit policies never fall back. The same planner and
compiler implement both; public target and capability guards remain active.

The original attempt `5b09a9c35fd572f00945bdb18040d2fb` bundle was reconstructed
with all 13 fields equal. Intent `9d353bfc...`, topology `fcff5b9d...`, physical
`753cf2ec...` and configuration `35618f4d...` remain pinned by regressions.
The store's complete 301-file C31 index verified with zero discrepancies.
Preliminary raw digest is
`cafe7c331d7a1353bec79f3799efb4135bf52774e3ef19afb374aa6b2f5ba2aa`.
Source `633e25e9`, tree `711244a1`, CI `35938917658`, PT `9.0.1.0858`/file
bind the original administrative Fa0/1 trunk readback, restoration to access,
deletion and two empty inventories. Setup raw additionally shows configured
2950 Gig0/1 and Gig0/2 trunks. All ten trunk forwarding verifications failed
with empty forwarding VLANs; four VLAN reads verified and 14 selected mutations
were applied. This supports configuration only. No forwarding, redundant-path
or generic catalog promotion follows. Existing scoped setup evidence remains
build-bound. Original cleanup removed 35 devices, restored twice and recorded
owned process exit; the spent old campaign remains BLOCKED and is not reopened.

The SP-1 terminal counted missing-device rows as observations. Four stage
regressions reproduced support with a missing device, empty address, failed DNS
or duplicate client row. The prospective predicate requires exact unique client
identities and successful valid static address/mask, resolver and agreeing
successful gateway observations. It preserves isolated failed HostIp getters
when HostIpProcess answers, and requires no DHCP mode or lease fields. Review
also reproduced dotted hostmasks incorrectly accepted as netmasks; two negative
controls now enforce the actual contiguous netmask. The hybrid fixture now
projects actual campus state into its endpoint reader rather than accepting
empty bindings. Product acceptance remains independent of terminal inventory.
Original accepted e3/e4/e5 fields verified for 2/2, 6/6 and 6/6 clients; complete
archive file sets and hashes (103/103/126 files) verified. Their product claims
remain intact. Historical nonaccepted e1's weaker terminal is retained unchanged.
No uncovered native SP-1 behavior requires a new run.

The old native table-end paragraph is superseded: e1/e5/e6 raw archive manifests
verified, but their executed producer merged index and field exceptions. Those
bytes are an empirical lead, not independent qualification of the current
field-separated reader. Infrastructure now reads every bounded index, records
raw object/null/undefined/index-throw/field-throw results, and decodes the exact
native exception only for an explicitly observed clean source SHA/tree,
`9.0.1.0858`, file channel and `getLeaseAt-index-and-fields-v2` reader. Current
same-run prefix observations retain first and confirming indexes and execution
provenance; they establish neither universal absence, exhaustion nor renewal.
Unknown contexts do not inherit the convention. Domain/application decisions
consume semantic outcomes rather than vendor text. Raw shared traces and final
LeaseScan facts preserve observations and decoder refusals.

Generated-script regressions cover unknown context and a row after an alleged
null/throw. Review reproduced three native evaluator bypasses and three terminal
bypasses; all now preserve decoder refusal. Further controls cover independently
conflicting MAC/IP identities and strict repeated confirmation. Native group
and terminal read bounds accommodate the selected 36-index workload; public
native capability policy bounds remain independently recorded. Existing raw
scripted fixtures are adapted to emit actual indexed/type-bearing observations,
not predecoded rows. Offline substituted evidence never promotes native support.

Current status remains ACTIVE_CONTINUATION_NOT_PHASE_ACCEPTANCE. Mixed/capacity
LIVE, public default scope integration, final full suite/exact-SHA CI and complete
requirement dispositions remain required before READY_FOR_REVIEW.


### Additional causal corrections and verification accounting

Independent review reproduced backend refusal being erased by domain null
calibration, and contradictory null/throw entries carrying a row. Six focused
regressions (including overflowing numeric lease time) now keep calibration and
attribution inconclusive, preserve raw entries, and reject incoherent return
fields. Invalid rows do not enter the derived valid-row projection. A foreign
backend cannot inherit the convention merely by returning the same version text.
A stateful competing-pool getter regression also proved that the requested name
was being substituted for the returned object's identity; the snapshot now reads
the actual physical name and refuses a mismatch.

Qualification configuration waits omitted the existing caller wait allowance.
Their fallback used real eight-second waits even after the phase allowance was
spent. The ledger now exposes remaining seconds and composition passes that
control into nested waiters. A regression failed with 11 extra observations at
an exhausted budget, then passed with one bounded observation. The real hostname
verifier stops after its last failed read and preserves nine cleanup operations
and three seconds. Test transport views delegate the same control. This is
finite phase-budget wiring, not a timeout increase or simulation acceleration.
The focused stage run passed 91 tests; final affected/full verification follows.

Retaining fixed 258-index competing windows caused the 21-client record to exceed
its unchanged 40,000-bytes/client budget (2,299,942 bytes). Competing windows now
use observed configuration capacity plus two actual confirmation reads, capped
at the existing scan ceiling plus two. Configuration is not a lease count.
Malformed/unreadable capacity remains non-authorizing; source/build/reader and
raw index evidence still determine the observed prefix claim. Shared trace
storage retains raw indexed fields and valid-row index references, shares
execution provenance, and omits redundant decoded row copies and empty derived
success diagnostics. It does not remove errors or recreate missing historical
observations. The 21-client control passed at 837,632 bytes with 10 group scans,
164 dispatches and 85,770 response bytes; all four loads will be remeasured.

The modern reader refuses old e11 snapshots lacking new index observations,
while the regression preserves original verified results and original client
fields. No historical observation is synthesized to make those snapshots pass
the prospective contract. Known selected-client contradictions and first local
failures remain independently retained when a later shared scan refuses.

The first affected run was intentionally interrupted for budget-wiring diagnosis;
a later run was interrupted by the daemon restart after partial progress. Neither
is a complete verification result. The isolated scale failure above was reproduced
and corrected without increasing its budget. One earlier test process reported a
Windows access violation; the required fresh full result remains the baseline.
No new LIVE episode has been allocated or executed. The verified campaign ledger
still holds 1,183 committed operations and 2,319.580361 seconds, with no open
phase/episode, 17,817 ordinary operations and 18,680.419639 ordinary seconds left.

An offline design-only recomposition of 36 BR1 clients plus five HQ and three BR2
clients produced 54 devices, 55 links, 133 E5 actions, 10 E6 actions and 357 E6
expectations. Access 2960-24TT and distribution 3560-24PS trunks use existing
supported evidence. These counts prove a legitimate compiled hardware input,
not fixture authority, native forwarding, serving capacity or product acceptance.
The durable capacity contract and its final allocations remain prospective.


### Complete recovery baseline: three causal fixture failures

The complete Windows run finished with 8,651 passed, six skipped, three failed
and three existing warnings in 1,572.88 seconds. All four SP-2 scale loads
passed, but this red full result grants no LIVE baseline. The three failures
were reproduced together (three failed in 3.50 seconds) before correction.
The Fastloop experimental simulation reconstructed default v2 while consuming
the frozen v1 commissioning bundle/manifest; it now explicitly composes v1 and
asserts exact physical identity before loading that manifest. The native serve
positive stub used the generic `lease table end` exception; the positive now
uses the exact scoped native exception, and a separate generic-error negative
keeps the valid row and assigned address while refusing serving. The incomplete
index test now asserts backend scan refusal and preserved raw error/rows instead
of expecting a refused scan to be observed. No product predicate is relaxed.

The red full run measured the following offline substituted orchestration
costs; these are neither native capacity nor relay evidence:

| Constructed clients | Pools/groups | Group scans | Dispatches | Response bytes | Record bytes | Seconds | Peak MiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | 2 | 4 | 32 | 14,305 | 141,211 | 0.38 | 1.7 |
| 21 | 5 | 10 | 164 | 85,771 | 837,632 | 1.09 | 6.6 |
| 201 | 5 | 10 | 1,244 | 755,764 | 5,824,713 | 7.61 | 40.9 |
| 997 | 5 | 10 | 6,020 | 3,552,807 | 27,165,772 | 74.54 | 187.5 |

The six skips are two unavailable Windows symlink privileges, two absent
ignored legacy voice artifacts, and two opt-in native-window tests because
`PT_MCP_NATIVE_WINDOW_TESTS` is unset. The three warnings are the pre-existing
class-scoped fixture instance-method deprecation. A fresh complete green run,
clean delivery and exact-SHA CI remain required before e7 allocation.


The three corrections passed all six focused cases in 5.62 seconds and both
complete affected files (106 tests in 31.62 seconds). A fresh complete suite
is running against those unchanged Python bytes. Self-review preserves the
exact manifest fallback, explicit profile choice, raw index/field evidence
and decoder refusal; no new product control was weakened.

### Prospective capacity and public integration design (risk L)

The selected capacity fixture will hold 36 local HQ clients on
`10.80.1.0/26`, 13 remote BR1 clients on `10.80.16.0/27` and five remote BR2
clients on `10.80.33.64/27`, simultaneously on one Server-PT. Local native
`serverPool` will use `.16` through `.51`, gateway `.1`, server/resolver `.10`;
BR1 and BR2 use separate named pools. This satisfies the original local 36
requirement and exercises the selected 13/5 independent pool demands. These
are chosen fixture policies, not recovered Final-Muejeje DHCP facts.

Topology and E5-only design recomposition succeeds: 64 devices, 65 links,
153 E5 actions and 153 expectations; topology
`ef36487fe87642d286c8d11ba4beb35536c2c1edd8438f1b61368bf4bac69b34`,
manifest `e35d69a9e846c0a37908f50114d0208f58f9e8da7b66cdbbb89d28c8fcb37143`,
E5 `69bcf483ff9448be1f5a51eee76059c285ae63dd08b75191cfbbcf42723639db`.
The selected clients imply 437 E6 expectations if the unchanged eight checks
per client and five server checks compile. That E6 count/hash is prospective
and must be verified after implementation. HQ access uses 2960-24TT with
3560-24PS distribution; BR1's flat 2950 has no trunk requirement. Setup needs
261 operations and fixture cleanup 131 before lifecycle work.

A separate versioned capacity stage will use the existing mixed composer,
coordinator, applicators, terminal and persistence, with separately pinned
fixture/plan identity. The existing eleven-client profile and historical
archives remain reconstructible. Native IPv4 structural validity and finite
work limits will admit a /26 and 36 only as structure; default support still
requires a separately measured grant. Tests will pair new composition and
zero-effect refusal with unchanged historical native/commissioning inputs.

Budget design will follow the final compiled actions, readiness and scans,
plus the actual polling schedule. The existing thirteen sample cycles and
twelve ten-second waits do not constitute a hard 120-second wall deadline.
Shared sample timings and a finite wall limit derived from bounded read work
will reject late results without increasing all timeouts or accelerating the
simulation. Stage and episode allocations must additionally reserve terminal,
cleanup and lifecycle work before activation; final values remain prospective
until final compiled/hybrid measurements and current ledger verification.

Public records will preserve the old `192.0.2.0/24` one/two-client grant and
its original serialized provenance. New independently keyed records will bind
the complete native-plus-named host policy set to one observed cohort, including
build/file channel, reader contract, server/interface, placement, physical pool
names, address bounds, exclusions and demand bounds. One host cannot combine
independent grants into an unmeasured pool set. A pure selector shared by
compiler/admission/resolver will refuse absent, foreign, ambiguous or changed
bindings before effects and retain selected grant hashes/provenance once in
the durable record. Router relay evidence will remain constrained to actually
observed model/interface/helper/segment scope. Private candidates do not become
public entries through their earlier basis SHA/run. Actual native evidence must
precede any default promotion and the registered four-input/default-catalog
route must then pass the complete selected-client checks.


### Complete rerun exposes a simulated native-UI publication race

The fresh complete suite passed the three corrected cases, with 8,654 passed,
six skipped and one failure in 1,145.65 seconds. The additional warning records
an unhandled fake-provider thread exception: the readiness request path was
visible while its writer still held it, and the simulated provider's one-shot
read raised Windows `PermissionError`. The driver returned false and retained
its fail-closed handshake. This red result is not a LIVE baseline.

Before correction, deterministic fixture regressions will inject a first-read
permission error and partial JSON, then require the same fresh correlated
handshake within the unchanged two-second bound. The fake provider will poll
read-only for complete readable bytes until that existing deadline. No timeout,
receipt identity/freshness predicate or production native-UI code is relaxed.


Both deterministic publication-race regressions failed first (two failed and
two worker-thread warnings in 10.32 seconds), then passed in 0.41 seconds after
the bounded read-only fixture correction. The complete native-UI driver file
passed all 15 cases in 7.57 seconds. Its readiness and call fake providers now
share the same complete-request wait; production behavior and deadlines remain
unchanged. The full suite will run again from these exact Python bytes.


### Explicit operator restriction on phone validation

The operator reiterated during this continuation that phone validation uses
only `show power inline`; phone UI validation is prohibited. No native phone
UI, native call or phone-control validation is part of SP-2 or will be started
or extended. The publication-race correction above is an inherited offline
fake-provider unit fixture in the complete suite, with no phone, UI, Packet
Tracer or native call interaction. It is not evidence of phone behavior. Any
later relevant handoff must preserve the operator's `show power inline` limit.


### Recovery checkpoint: complete green local baseline

The fresh complete v3 run exited zero: 8,657 passed, six skipped, three existing
fixture-deprecation warnings in 1,188.21 seconds. XML reports 8,663 cases,
zero failures and zero errors. Former commissioning/native scan cases and the
deterministic fake-provider race cases all passed. Skip categories remain the
two unavailable Windows symlink privileges, two absent ignored historical voice
artifacts, and two opt-in native-window tests; no new SP-2 test was skipped.
The unchanged Python snapshot was retained throughout this run.

Final actual SP-2 orchestration samples still constructed 2/21/201/997 clients.
Group scans, dispatches, response/record bytes and peak memory equal the table
above; final elapsed times were 0.34/1.19/5.63/58.95 seconds respectively. These
remain explicitly substituted offline costs, with no native capacity claim.
The full provisional quality gate passed after the final fixture correction;
namespace inventory and docs passed, with only existing documentation links.
Self-review and the bounded independent reviews found no additional important
recovery defect. Clean delivery and exact-SHA CI are next required gates.

This green recovery checkpoint is not SP-2 acceptance. No new episode has yet
been allocated or executed. Fresh mixed evidence, 36-client capacity, measured
scope-bound default records and registered public-route acceptance remain
required, with the phone-validation restriction above in force.
