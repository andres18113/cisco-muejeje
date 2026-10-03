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

The operator requested a read-only CP-SCALE review to clarify the earlier
power-command statement. Historical full phone functionality used API/IOS
IP/interface/DHCP and binding observations plus complete fresh attributed
`SHOW_EPHONE` registration/extension evidence after forwarding readiness.
`show power inline` is the power authority; it is not complete phone-function
validation. Historical calls remained unqualified. Phone UI validation remains
outside SP-2; no phone effects, native calls or phone-control validation will be
started here. The publication-race correction above is only an inherited
offline fake-provider unit fixture, with no phone/UI/PT interaction or phone
behavior evidence. Relevant handoffs retain this clarified distinction.


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


## Episode 7 closure and next causal source boundary (risk L)

Recovered checkpoint `032d422a036c5999f0127a4b71dc945a7376a2bc`, tree
`add28d80e1983ddbe846fd733fc644b080571bc5`, passed the clean delivery gate,
namespace, docs and whitespace and was published normally. Exact-SHA CI
`36661748379` passed all six jobs. Windows 3.11/3.13 each passed 8,657 with
six skips and three warnings (1,471.46/1,294.68 seconds); Ubuntu 3.11/3.13
passed 8,641 with 22 skips and three warnings (761.11/754.94 seconds). CI
Windows skips are the machine-local D-DHCP record, two absent historical voice
artifacts, two opt-in native-window tests and the absent docs extra. Ubuntu
adds 16 Windows-only checks (three receiver and thirteen process-census cases).
The dedicated docs job passed. Local skip categories above remain distinct.

Fresh e7 preparation retained a durable maker and nine hash-verified helpers,
corrected operator scope, complete CI metadata/logs, actual compiled hashes and
exclusive identities. It prospectively allocated 3,210 operations/4,200 seconds
only after clean exact-source and empty process/mailbox/lock admission. Owned
PID 2100 launched with a proven blank disposable document. Attempt
`a06b0134ff1d31156d482762f3df0c3e` executed the unchanged private mixed profile.
All 18 devices/17 links were created; product configuration held 51 actions and
93 service expectations with ten readiness observations. No phone work ran.

Product persisted status is FAILED, qualification outcome is STOPPED, and both acceptance measurements (product and terminal) concluded INCONCLUSIVE. The originating action is
native HQ enable `svc/enable-server-dhcp/0c4671f01c7fd697`: accepted/correlated,
setter not attempted, covered footprint, `not_attempted:refused:pool_conflict`.
BR1/BR2 enables were dependency-blocked; their disabled-policy/lease failures
are downstream and establish no serving. All selected clients were DHCP-on
with APIPA/16 addresses, zero gateway/resolver; the final process held the three
planned disabled pools and four exclusions. Recomposition matched every native
policy field and companion against the generated desired state. Guard-time
pre-client fields were not retained, only digests, so the originating APIPA
branch is a strong evidence-bound inference, not a reconstructed observation.

Qualification used 408 operations/684.375 seconds (435.512 seconds of local
process observation), restored fixtures, and finalized without secondary error,
residue or persistence failure. Maintained retirement exited only owned PID
2100. Final process/mailbox/lock census was empty. The closed ledger totals
1,591 operations/3,426.06543 seconds with no open episode; ordinary remaining
17,409 operations/17,573.93457 seconds. No e7 mutation will be replayed.

The immutable e7 archive has 166 files, exact file set and every hash verified.
MANIFEST SHA-256 is
`7336fd2bad09ef51a7c7f7ef503d3e946e950db05bc967d14d517d399fa16ffd`;
qualification digest `c0d72a33b78e6de0c9408cd4daf748a399de44b7f2d4b34ba3d47455c6089268`,
product digest `6f41e2680f1d55bd4c3ef7a0345afab9ecd9d35407d15d5496fde4bb323fdf04`.
Empty terminal prefix observations remain raw evidence; they do not qualify
selected serving, full-table convention, multiple active pools or capacity.
No default support record is promoted from this episode.

### Causal correction design before implementation

An independent actual generated-script stub with the exact disabled three-pool
policy reproduced unassigned 0/0 -> one enable/success; DHCP-on APIPA/16 -> zero
enables/pool_conflict; foreign assigned address -> zero enables/refusal. The
prospective startup predicate will distinguish a known DHCP-on pending/APIPA
state from a usable lease and allow ordinary server startup only with the exact
planned disabled policy and known client state. It will preserve refusal for
static, assigned in-policy/foreign, malformed and unreadable clients. Client
and policy refusal causes will be distinct and raw pre/post client and server
state will be retained prospectively. APIPA never satisfies usable DHCP or
service acceptance. RED stateful generated-script regressions precede the fix.

A separate independent SP2-04 audit reproduced false refusals for equivalent
48-bit MAC spellings. The existing group positive oracle wrongly required
literal equality; grouped and single-client joins/stability will instead use
valid nonempty normalized identities while retaining original readings and
observed values. Dot/colon/dash/case positives and representation-change stable
samples must pass; malformed/empty identities, normalized collisions, wrong
ports/IPs and first/later contradictions must remain refused. This correction
changes prospective decisions only and leaves all archives immutable.

After focused and affected verification, the complete source must again pass
local/clean-delivery/exact-SHA CI before the next freshly bound owned episode.
The capacity and public-scope designs above remain required; the private mixed
failure is a discriminator, not phase completion or a new permission request.


### Incomplete worker handoff at the next source boundary

The completion worker is handing ownership back to the coordinator because its
context is nearing exhaustion. This is not phase completion, a permission
request, or a change to the continuing operator mandate. Current branch remains
`feature/server-pt-goal-foundations`, committed HEAD `032d422a...`, tree
`add28d80...`. That checkpoint is cleanly published with exact six-job CI
success; current corrections below are uncommitted and have no new full-suite
or delivery/CI baseline. Preserve them and the sealed e7 archive.

Current dirty maintained paths are this brief, domain
`models/configuration_runtime.py`, infrastructure
`execution/enterprise_service_runtime.py`, and
`tests/test_native_dhcp_group_evidence.py` /
`tests/test_service_dhcp_script_harness.py`; the e7 archive directory is also
untracked. Exact current Python SHA-256 values and a fresh operational census
are recorded in `data/services/sp2-governed/continuation-2026-09-30.json`.

Completed prospective fixes and focused evidence:

- MAC joins/stability now reuse valid normalized identities across group and
  single-client paths while preserving raw tuples and derived `client_mac`.
  Seven maintained group RED cases failed in 1.82 seconds; five single-reader
  cases failed before the fix. The resulting twelve positives passed in
  1.96 seconds. Existing normalized collision negatives still require the
  complete affected-file run. No full pass is claimed for these changes.
- Generated native startup admits known DHCP-on APIPA/16 as pending, never as
  a usable lease, only under the exact disabled planned pool policy. It now
  separates `native_client_precondition` from `pool_conflict` and retains raw
  pre/post server/client observations. Eight focused startup positive/negative
  cases passed in 0.71 seconds after their prior RED. The raw observations
  travel through optional `RuntimeActionMutation.observation_details`, with a
  serializer omitting empty details to avoid widening legacy record bytes.
  Details are not read by the mutation classifier.

Concrete remaining correction work BEFORE the next source baseline:

1. Add RED and fix APIPA acquisition in group and single-client paths. A valid
   DHCP-on APIPA first sample must stay pending with zero stability, then two
   later usable attributed samples may verify. Persistent APIPA must never
   verify. Preserve MAC/address/counterpool censuses and malformed/static/
   foreign refusals; do not increase polling cadence/timeouts or accept late
   evidence. Current group sticky `native_client_outside_policy` and single
   immediate APIPA contradiction are still present.
2. Add RED and fix late client-local competing-pool evidence after an earlier
   local unreadable sample. The first cause/sample stays, later derived MAC/IP
   contradiction/sample must persist, and an independent PC1 remains accepted.
   The current sticky-failure `continue` skips this classification. Cover
   equivalent forms, disjoint controls, positive rows in unread tails and
   retained JSON facts. Raw rows alone are not the final classification.
3. The new startup helper currently coerces IP/mask/MAC getters with `String`
   and catches with hardcoded `__er`. Add malformed getter-type RED (numeric
   twelve-digit MAC would otherwise become valid bare text), retain raw values
   and their types, require strings for pending eligibility, and use the
   selected category/text reader for error privacy. These new-code findings
   are open; do not call this candidate ready.
4. Review/test present raw-detail retention/redaction and empty-field legacy
   serialization/persistence, including the unchanged scale byte budget.
   Also reproduce the existing native enable already-satisfied producer path
   against `_allowed_skips`: it currently lacks that skip. A premature added
   allowance was removed; write the causal RED before deciding its correction.
5. Finish the capacity/profile, work-derived wall bounds/sample timing, full
   same-host scope selector/provenance, default recorded support and registered
   four-input public acceptance designs above. None is implemented yet. The
   local 36 + remote 13/5 simultaneous native target remains unmeasured.

Focused logs are `%TEMP%/sp2-mac-normalization-red.log`,
and `sp2-start-and-single-mac-red.log`;
final focused passing outputs were observed directly. Recovery full v3
log/XML/exit remain `%TEMP%/sp2-recovery-full-v3.*`; delivery and all four
exact-SHA CI logs are retained under e7 lead/archive. Do not rerun unchanged
broad reviews; every remaining concrete finding needs its owning causal test,
focused/affected validation and then one complete fresh baseline/clean delivery
and exact-SHA CI before new LIVE.

Fresh handoff census at 2026-09-30T04:42:24Z confirms no Packet Tracer process,
mailbox file or campaign lock; campaign index has no discrepancies and no
open episode. Ledger remains 1,591 operations/3,426.06543 seconds, ordinary
17,409 operations/17,573.93457 seconds. Future effects remain authorized only
for newly bound owned disposable SP-2 scope; no e7 replay, main merge,
SP-3..SP-5, Final-Muejeje, foreign resources or phone effects. The corrected
CP-SCALE power-versus-functional distinction above remains in force.


### Continuation ownership and causal design (risk L)

The coordinator transferred sole integration-writer and LIVE ownership to the
continuation worker after the previous worker released both. Starting committed
identity remains `032d422a036c5999f0127a4b71dc945a7376a2bc`, tree
`add28d80e1983ddbe846fd733fc644b080571bc5`, on the same feature branch. The
five dirty maintained paths and sealed untracked e7 archive are preserved.
The active instructions, complete engineering standard, both assignments,
current brief and durable handoff were read; interactive loader remains pending.

The next change closes the inherited prospective causal findings. Group and
single-client acquisition must classify a valid DHCP-on APIPA/16 reading as
pending with zero stable usable samples. Only two subsequent exact attributed
usable readings may verify. Persistent APIPA remains unassigned; static,
malformed, foreign and contradictory observations remain non-authorizing. All
fresh group identity/address/competing-pool censuses continue and remain durable.

Client-local counterevidence is classified for every later readable sample even
when the first local failure is sticky. Preserve that first cause and sample;
record each later local contradiction with its cause/sample separately. A
competing row matching a client's valid MAC or assigned address is local to that
client unless it also proves a genuine selected-peer/shared identity conflict.
An unread competing tail still prevents positive acceptance while preserving
positive counterevidence. Index shared counterpool rows once per sample.

Generated startup must retain primitive raw getter values and explicit types,
require string IP/mask/MAC values for pending eligibility, and classify errors
with the selected text/category reader. Unknown or malformed raw values cannot
acquire authority through string coercion. Tests exercise the actual generated
script with independent stateful stubs, both privacy modes, exact-policy no-op,
raw-detail redaction/persistence and unchanged empty-detail serialization.

RED regressions precede each owning fix, then both affected files and dependent
service/commissioning/coexistence suites run before one complete local baseline.
New LIVE still requires clean exact delivery, docs/namespace/whitespace,
publication and all exact-SHA CI jobs. No existing deadline, historical archive,
spent accounting or measured support is relaxed. Capacity and registered public
acceptance remain required after these corrections.


### Prospective causal verification dispositions

Acquisition APIPA reproduced four failures (group and single pending/expiry)
with nine negative/startup controls already passing, then all thirteen focused
cases passed. Pending fallback contributes zero usable stability; two later
exact usable reads are required. Six late MAC/IP/equivalent counterpool cases
failed before classification, with two disjoint controls passing; all eight
then passed, including unread-tail counterevidence and retained shared raw
references. Empty later-contradiction fields are omitted from positive results.

Actual startup scripts reproduced numeric-MAC admission, raw getter coercion
and category/text privacy errors; corrected raw primitive/type eligibility and
selected reader passed fifteen focused controls. The committed pre-fix
`_allowed_skips` method was executed in memory against the current actual
producer: the exact already-enabled policy became an invalid unknown row.
The inherited allowance now passes the maintained exact-policy no-op regression.
This supersedes the incomplete handoff wording that claimed the allowance had
been removed: actual dirty bytes already contained it before ownership transfer.

The actual durable record round trip preserves sanitized received raw details
and deep snapshot isolation; empty details preserve the legacy mutation shape.
The six-file affected run passed 327 cases in 22.04 seconds. Independent focused
review then found successful IP/mask readings erased by a later MAC exception.
Four actual Node regressions failed first in both privacy modes; each field is
now saved immediately with explicit failed-field/type markers. All 112 harness
cases then passed in 7.70 seconds. This source still lacks a new complete local,
clean delivery and exact-SHA CI baseline; no new LIVE has been started.


### Capacity profile and finite acquisition work (risk L)

The maintained private capacity constructor now recomposes the selected 36-local
plus 13/5-remote fixture, independently from the unchanged mixed profile. Its
actual outputs are 64 devices, 65 links, 153 E5 actions/checks, ten E6 actions and
437 E6 expectations. Physical, manifest and E5 hashes match the prospective
values above. Normalized capacity E6 is
`0a28305599ba8f2c2a7d24c3850371c97de4badfd07ab745c9231740f44571f8`;
private capability digest is
`71e1945a5f0fe63428429e31e84a4047ef363af950db15e4bf07d6cbc7dca7cd`.
`data/services/sp2-governed/capacity-design-v1.json` keeps the dirty source hashes
and full prospective plans; its explicit offline label grants no native claim.

Structural native policy now accepts a valid finite IPv4 allocation up to the
256-index work ceiling, including the required /26 and 36 clients. Measured
admission remains separately scope-bound; inactive observations retain their
16-client bound. The original default native record's exact serialized SHA-256
is `af10ea312b2c491ec919f67aeca9c279ec2920fbbd52e3bb7e5c8852ff7911cf`,
unchanged with max two on `192.0.2.0/24`. Structural capacity is not promotion.
The old mixed topology and its 18/17/93 counts remain reconstructible.

The separately identified `SP2-CAPACITY-PRODUCT` v1 runs through the same
composer/coordinator/runtimes, with pinned fixture/plan/catalog identities.
Its prospective joint ceiling is 6,000 operations/10,800 seconds, including
5,500 product operations, 90 terminal operations and protected cleanup of
131 operations/5,400 seconds. Setup is 261 operations, so declared work sums
to 5,982 with 18 operation headroom. No old stage or spent allowance changes.
This is a finite experimental cutoff, not funding for every independent maximum
reader/helper tail at once. Phase admission and child read/wait caps enforce it;
an exhausted ordinary allowance stops with retained inconclusive evidence and
protected finalization, never a late positive or fabricated completion.

Independent budget derivation used the actual qualifier bindings: physical
observation ten seconds/mutation fifteen gives setup 3,255 and cleanup 1,630
seconds of core timeout envelopes. Cleanup additionally has 131 lifecycle
pairings/262 helpers, each helper separately bounded to thirty seconds by the
absolute phase deadline. The loose combined cleanup envelope is 9,490 seconds
before small local overhead, exceeding the finite joint reserve. The reserve
therefore allows 3,770 seconds of control work after core physical work; it does
not promise every helper's maximum. Slow or uncertain cleanup is recorded and
uses only already-authorized bounded owned-cohort retirement, never foreign
resources. Terminal has 76 core operations (72 router calls plus four bulk
reads) inside 90, and a 160-second core timeout envelope. Actual deployment
shape, current ledger and lifecycle allocations must be rechecked before LIVE.

Native acquisition retains thirteen samples and twelve ten-second waits.
Group work is thirteen times (five-second server read plus eight-second shared
snapshot plus five seconds per inactive client), plus 120 seconds of waits:
289 seconds per group with no inactive clients. Three groups have 78 bridge
reads and 867 seconds of loose envelopes. Each snapshot scans the three actual
pool windows (38/15/7 indexes); 39 maximum snapshots mean 2,340 in-engine index
reads, not bridge operations. Single-client bounds additionally include its
client and attribution reads. Current phase allowance caps each window and child
read; wait cadence is retained, and late positive server/client/pool readings
are non-authorizing. Shared sample timings and raw late snapshots are retained.

Actual readiness derives five access groups, one four-switch continuity group
and two routed groups with two/three routers per phase. Independent loose
per-reader maxima across both phases are 14,036 calls and 1,320 seconds;
per-client E6 core maximum is 1,227 operations and a loose 7,742-second envelope
under the qualifier's existing eight-second inspection cadence. Those independent
maxima exceed the joint stage cap and are not added into a completion guarantee.
The maintained registered public acceptance binding must record its actual
cadence separately; it may use the existing bounded native session while keeping
the real four tool arguments and default service/device catalogs.

Capacity composition RED had two failures and six valid negative controls;
eleven focused capacity/unchanged-mixed composition cases then passed. The new
stage initially exposed missing 2950/3560 ports and a /24-only simulated native
coupling assumption in the Node fixture. Its candidate fixture now supplies
literal model ports and subnet-based hypothetical coupling, explicitly not a
measured native algorithm. The real hybrid coordinator/product then passed all
54 client checks, final three-pool census and cleanup with 297 campus calls,
838 engine product calls, 1,586 stage operations and thirty simulated seconds.
This trace is substituted offline work only; native capacity, actual elapsed
cost and public support remain unmeasured. Controlled budget/tampering tests and
the full dependent/local/clean-CI baseline still precede a fresh native episode.


### Capacity discovery: selected L2 foundations are missing from E5 closure

The first hybrid capacity result was inspected before treating its pass as a
native preparation baseline. Its service effect scope excludes the HQ trunk
configuration actions, while the old campus fixture starts from all compiled
trunks. The new owned native fixture starts blank, so that substituted initial
state masks a prospective failure. This is an SP2-03/36-client path-closure
implementation defect, not a reason to promote capability or weaken readiness.

Before correction, add a pure real-composition scope regression for every trunk
end of the selected HQ VLAN component, including its cyclic routed host leg.
Also add an independent initially unconfigured campus control that changes VLAN,
access and trunk state only from actually dispatched IOS payloads. Both ends and
actual allowed VLANs must be configured before mode/lease/service admission; an
ignored trunk-end setter must block dependents. A local-only selection must not
apply unrelated branch/transit foundations. Ordinary path configuration is not
forwarding proof: the existing attributed continuity/routed observations still
decide readiness, including blocked redundant links.

Domain path indexes own the exact paired-link trunk IDs, indexed/cached once per
component. Application closes selected local L2 components and routed cyclic L2
legs through the existing E5 dependency graph. No alternative planner or service
engine is added. A9 eligibility, retention, immutable histories and unselected
components remain outside effects. Focused new regressions and affected SP-1/
campus path/coexistence tests precede the complete source baseline.


### Distinct configured-trunk contract for prospective cyclic service paths

Closing the actual L2 effects exposed two correctly STP-blocked trunk ends.
The legacy per-port `TRUNK` predicate requires every intended VLAN to forward,
so it contradicts a valid cyclic component before service continuity admission.
The originating design must distinguish configuration from component forwarding.
The legacy predicate, C31 inputs/hashes/results and strict forwarding kind stay.

A new typed `TRUNK_CONFIGURATION` expectation will require a fresh complete
uniquely attributed exact-interface trunking row, intended allowed VLANs and
active VLANs. Its field claims cover configuration only; raw forwarding VLANs
remain in its typed convergence observations, including empty/unreadable values.
It cannot authorize client modes, leases or service requests. Those still need
fresh attributed component forwarding evidence over the actual selected paths.
Unknown/missing configuration, wrong VLAN/interface/owner and no viable current
forwarding path remain refused or blocked.

The composition policy chooses this distinct kind only for cyclic VLAN
components in prospective service composition under the already selected v2
planning profile. Generic E5 defaults to the strict per-port predicate. The
exact-manifest v1 reconstruction carries its selected profile through policy
composition and retains strict kinds and its unchanged configuration identity.
This uses existing legitimate composition/version inputs; there is no campaign
name, client-count or model exception, generic blocked-link permission, default
capability promotion or historical reinterpretation.

RED module contracts cover blocked configuration versus strict forwarding,
allowed/active/freshness/owner negatives and exact raw-field retention. Real
capacity compiler tests cover explicit component/VLAN/interface assignment;
unconfigured-campus positive and ignored-end negatives cover the mandatory
forwarding gate. Frozen commissioning reconstruction and affected SP-1/static
campus/CP-SCALE contracts are required before the complete fresh baseline.
Capacity E5/E6/catalog hashes are re-pinned from the final maintained composition;
the earlier candidate-only artifact is retained as superseded preparation.


### Acquisition getter type correction

Two actual generated-reader regressions reproduced a numeric client MAC
`123456789012` becoming valid bare text through `String()` and then falsely
verifying against a textual pool row, in both single and grouped acquisition.
Startup typing alone does not protect a later observation. Before source
freeze, the existing acquisition/inactive/attribution producers must preserve
raw MAC values; typed validation rejects non-string identity without inventing
normalization authority. Malformed observations remain raw diagnostic evidence
and never usable joins. Valid string spellings and positive scale shapes remain
unchanged. This is a demonstrated SP2-04 implementation defect; no historical
archive is rewritten and no additional native support follows from the tests.


### Final prospective L2/type dispositions before source freeze

Full and local-only capacity scope regressions failed before the L2 closure
correction, and the initially unconfigured campus failed before actual trunk
configuration. The independent campus now starts with blank VLAN/access/trunk
state and parses only dispatched IOS payloads against physical link metadata.
Ignored trunk state remains non-authorizing. The distinct configured-trunk
reader passed eight explicit configuration/scope/authority controls while the
legacy per-port forwarding negative stayed strict. A further v1 service
reconstruction test preserves its strict kind and original configuration hash;
the original C31 bundle was compared as UTF-8 and all thirteen fields are equal.

The final capacity E5 hash is
`7ccda09a418d755c49f2d14f29c54f660b74f051a7c4b8b3a2715d6223b88b96`,
normalized E6 is
`09feeeb4d926ba06155297ec243dcdd73b1f5ae21b0d34dc772f8f79ae17fbeb`.
The earlier hashes are superseded prospective preparation only, never native
archives. `capacity-design-v2.json` retains the final candidate plans and
explicit dirty/offline source label; v1 preparation is preserved. Actual counts
remain 64/65/153/10/437 and the default native record bytes remain unchanged.
The complete initially unconfigured hybrid capacity now has 317 campus calls,
838 engine product calls, 1,606 stage operations and thirty simulated seconds.
Small ordinary-budget and wrong-profile controls both pass with terminal/owned
cleanup preserved; neither supplies native acceptance.

Numeric client-MAC coercion failed in both actual generated acquisition paths,
then the raw-MAC correction passed twelve focused identity/state cases. A
follow-up causal shared-census case failed because rejecting that MAC erased an
independently valid duplicate IP; the raw malformed MAC remains a local unknown
while its valid address remains in the shared census. The resulting thirty-three
MAC/APIPA/counterpool cases pass, with first local cause and raw frames retained.
No empty diagnostic field is added to positive clients. Final lint/format,
dependent suites, full local suite and clean published exact-SHA CI still gate
any new native effect. No native capacity or default public grant is claimed.


### Dependent baseline failures and originating corrections

The first complete affected run has 1,705 passed and seven failures in 478.11
seconds, with frozen Python hashes unchanged. Five commissioning failures share
one origin: its scoped trunk evidence can make v2 and v1 produce the same exact
physical shape, so the current-hash fast path incorrectly retains v2 verification
semantics. Exact-manifest reconstruction must also test v1 on such a tie and
conservatively preserve v1 when its complete physical hash matches; explicit
planning policies remain authoritative and never fall back. No campaign/model/
client-count exception or expected commissioning hash is changed.

The 21-client offline record is 845,208 bytes, exceeding its unchanged 840,000
byte gate after new raw/timing diagnostics. Preserve all observations and the
resource threshold. Equal raw indexed lease entries from separate fresh samples
may be stored once with an explicit per-sample content reference and equality
hash; physical pool, window, termination, indexes, source context and fresh
client readings remain per sample. Changed or unread/malformed entries are kept
verbatim. The evaluator still processes each actual fresh answer before the
storage projection; no observation is manufactured by the reference. A raw
round-trip/refusal regression and the actual unchanged scale gate verify this.

The final failure is a maintained diagnostic phrase: the 17-client public input
still refuses before effects, now at measured scope rather than the old structural
16 bound. Restore `does not admit` with explicit recorded-policy wording while
retaining structural/recorded separation and the zero-effect criterion.
Provisional main-relative quality gate, namespace, docs and whitespace passed;
e7 remains exactly 166 files with every hash and manifest digest verified.
No complete local/clean-CI/native source baseline is claimed from this red run.


### Complete prospective baseline exposes a static HTTP scope regression

Sole writer and LIVE ownership transferred to the current continuation worker
on unchanged committed `032d422a...` / `add28d80...`. The fresh complete frozen
run exited one: 8,688 passed, 61 failed, six skipped, three warnings and six
setup errors in 1,770.60 seconds. XML contains 8,761 cases. All 24 checkpoint
Python byte hashes still match at termination. Its full log, XML and exit are
`%TEMP%/sp2-finish-full-v2.*`; this is a complete RED baseline, not LIVE
admission. Provisional quality, namespace, docs and whitespace passed; sealed
e7 still has exactly 166 files, all hashes and its pinned manifest unchanged.

All 67 red outcomes share static campus HTTP acceptance preparation refusing
new trunk E5 effects outside its unchanged acceptance profile. Missing grants,
records and scope are downstream fixture failures. The new configuration claim
was selected for every v2 service composition, including static HTTP whose
accepted contract already establishes its L2 setup separately. Independently,
routed cyclic legs added trunk effects without consulting the selected typed
configuration claim. These are prospective implementation/design defects; the
old acceptance profile and grants must not be broadened to obtain green.

Before correction, explicit regressions will require static HTTP to retain its
strict original trunk verification and E5 effect scope, and the routed index's
legacy default to retain its original cyclic-leg scope. The new component
configuration mode is selected only by a derived delegated Server-PT DHCP
policy under the v2 planning profile. Routed indexing receives the exact
configured-trunk action IDs from that plan and intersects them with each
selected component. New capacity still configures all ten HQ trunk ends before
its existing attributed forwarding gate admits modes, leases or services.
No campaign-name, client-count or model exception is introduced. Existing
capacity full/local-only, initially blank, ignored-end, frozen C31 and static/
routed coexistence controls remain required, followed by all four failed files,
affected suites and a new complete source baseline.


### Prospective episode preparation, seal and public-cohort audit dispositions

Read-only continuation audits re-read the actual default/compiler/A9/registered
route and all nine retained e7 helpers. Their hashes and the original charter
match. e7's maker cannot be reused unchanged: episode/auth/provisional IDs,
private mixed hashes, selected count, allocation and old verification results
are hardcoded. Its archive lookup and description are also mixed-only and
would omit a capacity product record. New retained successors must derive the
actual registered stage, recompute all plan/catalog hashes and verify the next
ledger episode, fresh source/tree, complete six-job CI and actual source gates.
Opening's assigned episode and actual source must match prepared IDs before
launch. Qualification, close and archive identities must agree. Pre-open
census must also prove no campaign lock, not only no process/mailbox files.
The direct read-only store audit currently verifies every indexed byte and
finds episodes 1--7 closed, no open episode, 1,591 operations/3,426.06543 seconds
committed and 17,409 operations/17,573.93457 seconds ordinary remaining. This
observation grants no future allocation; recheck before each new episode.

To execute sequential distinct questions on the same clean source, each new
episode will first seal a complete immutable snapshot under the explicitly
ignored governed evidence store. The seal verifies the complete file set and
every SHA-256, source/tree, helper provenance, qualification/product records,
closed ledger, owned exit record and fresh empty process/mailbox/lock census.
It is not an untracked-source exception. The next episode still rechecks clean
Git, current source/tree, exact CI, import/process/cohort and current ledger.
Later publication copies each sealed tree byte-for-byte into the requested
docs archive and proves equal file set, every file hash and manifest digest.
The native observation remains attributed to its executed episode SHA; the
archive publication commit does not change that identity. Earlier helpers,
archives and consumed grants remain unchanged. Capacity successor archive
uses its actual M-SP2-CAPACITY-PRODUCT/FINAL IDs and 54 simultaneous clients.

The public audit confirms independent per-service bindings cannot establish
one complete same-host pool cohort. A separately keyed cohort model must leave
the old ClientOperationCapability/native record bytes intact. One pure domain
selector matches the complete derived host policy, placement, selected demands,
relay scope and build/file/reader against a measured complete-cohort record;
never union independently measured partial grants. Compilation derives all
policies before this admission. Carry the single selected host grant ID/hash,
complete policy hash and exact action/expectation references through A7/A9,
service resolution, E5/E6 and the durable capability snapshot, once per host.
Empty selections omit new fields and retain legacy hashes/shapes. A9 projections
must match the same measured complete policy or refuse before effects.

Global supports_dhcp_relay remains UNKNOWN. The same action-specific predicate
must verify the selected cohort and exact attributed model/interface/helper/
segment evidence at both public E5 admission and the configuration applicator;
direct E5 without that selected authority stays refused. Missing, ambiguous,
candidate/foreign/tampered records, changed host/pool/window/exclusion/demand,
unmeasured pool union, wrong relay and narrowed incomplete cohorts require
zero-effect regressions. Default entries are populated only from sufficient
new native observations. Final acceptance must invoke the real registered
four-input handler with default service AND device catalogs in a newly governed
native session. Private stages and substituted registered-tool tests remain
separate evidence and cannot complete that acceptance.


The explicit new static HTTP and legacy routed-index regressions plus the
original scalable preparation case reproduced three failures in 6.48 seconds.
After the narrow owning correction, 14 focused cases passed in 2.10 seconds.
The four complete RED files and configured-trunk/capacity/SP-1 path/admission/
readiness/hardware suites then passed 177 cases in 47.69 seconds, with zero
XML failures/errors. Exact command and preserved RED/affected log/XML/exit
bytes are retained in the ignored governed source-verification store. The new
capacity full/local-only closure, initially unconfigured positive and ignored
trunk negative passed; the unchanged C31 exact strict reconstructions passed.
Focused Ruff passes and all four newly edited Python paths remain CRLF.
The next complete suite remains mandatory before clean delivery/CI or LIVE.


### Corrected complete source and actual offline scale verification

The fresh complete corrected run exited zero: 8,757 passed, six skipped and
three existing fixture-deprecation warnings in 1,296.11 seconds. XML has 8,763
cases and zero failures/errors. All 24 frozen candidate Python hashes match at
termination. Skips are two unavailable Windows symlink privileges, two absent
ignored historical voice artifacts and two opt-in native-window checks; no SP2
case is skipped. Local interpreter is this checkout's Python 3.12.10 virtual
environment and package origin. No Packet Tracer episode was opened.

The four unchanged scale cases also passed, in 64.84 seconds. Transparent
wrappers returned original values and caused no additional backend effects;
actual records, their hashes, raw lookup metrics, full log/XML and the bounded
runner are retained under `data/services/sp2-governed/source-verification/`.
The original timer/tracemalloc envelope measures runtime/applicator/persistence
after real plan construction; it excludes Node process memory. These are
substituted offline costs and establish no native capacity or relay behavior.

| Actual clients | Services | Group scans | Dispatches | Response bytes | Record bytes | Seconds | Peak MiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | 2 | 4 | 32 | 14,305 | 143,492 | 0.41 | 1.8 |
| 21 | 5 | 10 | 164 | 85,771 | 784,443 | 1.13 | 6.5 |
| 201 | 5 | 10 | 1,244 | 757,916 | 5,351,206 | 6.86 | 40.1 |
| 997 | 5 | 10 | 6,020 | 3,559,991 | 24,607,704 | 47.60 | 184.3 |

| Actual clients | Pool scans decoded | Raw index observations | Intended rows indexed | Counterpool rows indexed | MAC join/stability comparisons | Identity/address census readings each |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 8 | 24 | 4 | 4 | 6 | 4 |
| 21 | 50 | 310 | 42 | 168 | 63 | 42 |
| 201 | 50 | 2,110 | 402 | 1,608 | 603 | 402 |
| 997 | 50 | 10,070 | 1,994 | 7,976 | 2,991 | 1,994 |

At the observed two/five groups, intended indexing and client census each visit
two readings per client, and exact MAC joins plus stability compare three per
client. Counterpool work follows the selected host's pools and fresh groups.
Every unchanged dispatch/response/record threshold passes, including the
21-client record below 840,000 bytes. Actual constructed populations remain
2/21/201/997 for requested targets 2/20/200/1000. Clean exact delivery and all
six CI jobs still precede fresh native mixed/capacity/public acceptance.


### Prospective helper gate closure (pending independent review/publication)

Risk remains L under the existing prospective preparation/seal design at
`docs/engineering/change-briefs/server-pt-sp2-generalized-dhcp-relay.md:1900`.
This correction changes only ignored prospective helper bytes. Maintained
runtime/source, e7 originals/archive and consumed campaign accounting are
unchanged. The candidate is ready for independent helper review, not SP2 phase
acceptance and not authorization to skip fresh native preflight.

The five handoff findings have causal offline fixes:

- **Launch opening binding:** every launch requires an exit-zero opening
  receipt with exact path/hash, verified store index and the indexed opening
  equal to the prepared campaign/episode/attempt/authorization/source/tree,
  limits, stage/profile/channel/build, instance, targets and selected clients.
  Validation precedes lifecycle claim and is repeated before Start-Process.
  Maker explicitly retains episode/campaign/authorization IDs in the plan.
- **Required seal evidence:** promised qualification/product paths must exist
  and match exact indexed path/size/hash pointers. Qualification binds run,
  authorization/attempt/profile/channel/build/source/tree and owned launch.
  Exactly one stage-specific PRODUCT and FINAL measurement is required.
  Product binds summary/run/deployment/source and prepared manifest/topology/
  configuration/catalog hashes. All checks precede archive-stage creation.
  A measurement that actually did not run and promised no product may preserve
  that absence; a ran measurement cannot omit its product record/summary.
- **Cleanup identity:** closing requires complete typed census with exact
  episode/attempt/stage and timestamp. Seal binds that census's exact hash and
  closing identity. Attributed actual exit uses the maintained exit predicate,
  indexed launch/capture bytes and exact source/PID/path/incarnation. Missing
  exit remains unattributed; dirty cleanup remains `process_exited_dirty` with
  `cleanup_clean=false`. It does not alter the clean source identity or promote
  the failed/inconclusive product to acceptance.
- **Final inventory:** the reusable publication verifier rejects nonregular,
  linked/escaping, malformed or duplicate paths and verifies a fresh exact file
  set and every SHA-256. Seal calls it before and after the move and compares
  both inventories and manifest digests. Added and mutated final files reject.
- **Executed helper snapshot:** all ten command entry points require the
  caller-pinned snapshot digest and exclusive `lead/tools` execution. The
  exact eleven-file set includes authority/maker/seal and every other executed
  helper. Preparation and later helpers rehash retained verification summary
  and all twenty artifacts. Helpers run with checkout-local Python `-B` so
  unreviewed cached code cannot enter the exclusive tool inventory. The seal
  preserves every helper/artifact byte; `.py` evidence paths become `.py.txt`
  with an explicit archive path map. The snapshot is never regenerated or
  self-accepted by an executing helper.

The first causal run on byte-preserved original helpers had seven failures and
one positive pass in 4.11 seconds. Missing receipt/pin reached lifecycle claim;
missing qualification/PRODUCT-FINAL, incomplete census plus truthy unverified
exit, and both post-move mutation/addition incorrectly sealed. The first fixed
run retained one positive failure: fixture `read_text()` had normalized CRLF
in capture_text, unlike the maintained producer's exact decoded bytes. The
fixture was corrected to `read_bytes().decode()`; the production byte predicate
was preserved. That run's log/XML remain intact. Eight core cases then passed.

Final bounded offline verification has 114 passes, zero failures/errors/skips,
in 39.28 seconds. It executes real helper statements with temporary files;
only external Git/OS/campaign boundaries are substituted. It includes foreign
opening/authorization/product/closing identities, required evidence and pointer
hashes, all helper entry points/pins, complete verification retention, actual
exit and dirty cleanup, pre/post-move corruption, and real mixed/capacity makers
on temporary empty ledgers. Ruff, format, syntax and all twelve Python CRLF
checks pass. The exact eleven executed helper hashes were frozen before this
run and match at termination. No maintained Python changed, so the existing
ECE source full-suite/CI baseline is retained; no new broad source or native
result is claimed.

Proof, complete original/updated helper bytes, full diff and exact hashes are
retained under `data/services/sp2-governed/helper-closure-20260930T2100Z/`.
The final census proves unchanged clean source `ece5fca`/tree `2c760bd`, empty
process/mailbox/lock, no e8 IDs/plan and closed ledger: 1,591 operations and
3,426.06543 seconds spent; 17,409 operations and 17,573.93457 seconds ordinary
remaining. E7 remains 166 exact files with manifest
`7336fd2bad09ef51a7c7f7ef503d3e946e950db05bc967d14d517d399fa16ffd`.

**Deferred publication:** insert this disposition into the existing SP2 brief
with later native archive/public integration publication, preserving the
executed native source identity. This pending source documentation step is
explicit; the current execution source remains clean. Independent review must
approve the exact helper snapshot before prospective preparation. Then retain
the reviewed snapshot in exclusive lead/tools, supply its externally pinned
digest and repeat exact-source CI/import/ledger/process/mailbox preflight.
The old partial e8 snapshot is still unqualified and has not been overwritten.


## Episode 8 result and unsealed preservation (risk L)

The helper snapshot above was independently approved (spec and quality PASS)
and pinned externally at
`db5128268d77188099cb82f6fad411785122c55e4dfbd9229a306a74ef0e0e8b`. Its
eleven helpers then ran only from the exclusive `lead/tools` copy with
checkout-local `python -B`. Episode 8 executed clean commit
`ece5fca0cf9b997aed185b86367cd00fa6e9cd6c`, tree
`2c760bd2b9e1727e149efc56eece0833c15f879f`, after exact CI `36764012258`
passed all six jobs. Stage was `SP2-MIXED-PRODUCT` v1, attempt
`ccc1b252c0751f2e26a053db26f32493`, run `2026-09-30T21-14-00Z-2e2eba33`,
owned PID 17032 on 9.0.1.0858/file. The receiver proved the build and an
empty workspace before effects.

E5 applied 44 actions and omitted seven; 43 checks verified, one partial and
seven omitted. All fifteen selected foundations verified, and remote pre-lease
readiness was admitted. E6 applied seven actions and reasserted three; five
server checks verified. All eleven clients stayed DHCP-on with APIPA/16
addresses and 0.0.0.0 gateway/resolver. That gave eleven `DHCP_LEASE` failures
(`native_client_unassigned_in_window`) and 77 blocked dependent checks.
PRODUCT and FINAL are inconclusive. The server held `serverPool`, `BR1_DATA`
and `BR2_DATA` enabled. Final scans were empty over 7/5/5 indexes, with the
end throw at 0 and its confirmation at 1. None of this proves usable leases,
serving, renewal or universal exhaustion. The stage used 492 operations and
1,196.422 seconds, including 494.803 seconds of local observation. Restoration
was proven with no residue or secondary failure. Retirement exited 0, and the
closing is `verified_clean`. Ledger after e8 is 2,083 operations/4,868.084212
seconds committed. Ordinary remaining is 16,917 operations/16,131.915788
seconds, with no open episode.

The governed seal refused before staging: the attempt store holds
`source-ref-qualification-record.json` but no `source-ref-product-record.json`.
The executed CLI's `_native_product_record_path` matched only
`M-NATIVE-PRODUCT` and `M-SP1-ROUTED-PRODUCT`. It returned an empty path for
`M-SP2-MIXED-PRODUCT`, and the campaign loop skipped an empty source without a
finding (`archive_findings: []`). The product record exists, and the
qualification record cites it. The approved helper controls covered the seal's
own requirements, not this maintained producer. The e7 archive's attempts
likewise have only qualification source references. Its product bytes were
archived directly, and it is not rewritten.

Disposition: no pointer is fabricated, and no consumed store, ledger, record
or lead byte changes. A distinct preservation helper,
`data/services/sp2-governed/continuation-20261002/tools/preserve_unsealed_e8.py`
(SHA-256 `1e93467b70b97a74761f9beb9ac9e64686225c7c74a0d40d5cc7215b7a6b83ba`),
first verified all ten handoff artifact hashes, the absent product source
reference, the campaign index, the closing identity and the unique product
citation. It then copied lead, store, record and product bytes into
`docs/reference/server-pt/evidence/sp2-generalized-dhcp-relay-01/e8/`,
labelled `NOT_SEALED` in `UNSEALED.json` and `README.md`. Its 260-file
manifest digest is
`32fbf85bcbdfff713d9b54f57afc6d0a4a16351c5dab26ec20339a2fba831bac`, verified
before and after the move. That directory is incomplete failed-run evidence,
not a campaign seal, and supports no capability.

### Product-record citation correction

Causal design: a measurement that assessed a product names its record in the
`product_record_path` fact. The campaign seals the one record the
qualification record cites, whatever the stage is called. A non-text citation
or two different cited records raise. The campaign phase then stops with
`product_record_unsealed:ValueError` instead of silently skipping the source.
An empty citation still names nothing, because that product's own summary
reports why it persisted nothing. Qualification-record sealing,
store containment and native/SP1 sealing are unchanged.

RED: a new campaign-route regression runs the real mixed stage through
`service_qualification.main --campaign sp2` and requires the sealed source's
path, SHA-256 and size to equal the cited product. It also requires an empty
finding list and a clean index. It failed exactly as e8 did. Eight
citation-contract cases also failed: SP2 mixed/capacity, a duplicate identical
citation, an ambiguous pair and four non-text values. The four controls passed
(native, SP1, empty and absent). After the owning adapter fix, those cases
and a forced-ambiguity campaign negative pass, 14 in total. The negative keeps
the qualification source, stops the phase and seals no product. The affected
native/SP1/SP2 sealing files pass 76 cases. The corrected selector, read-only
against the real e7, e8 and native `ad5bca34` records, returns their existing product
files. Logs, XML and exits are under
`data/services/sp2-governed/continuation-20261002/source-verification/`.


### Episode 8 causal comparison and the acquisition discriminator (risk L)

The retained timelines of e8, the four local native positives (`dc9df810`,
`fde47f98`, `a18db0b4`, `ad5bca34`) and the two remote positives
(`499773bf`, `17680441`) were compared read-only. The full comparison is
retained with its record key paths in
`data/services/sp2-governed/continuation-20261002/codex-e8-timeline.md`.
Remote `2eb93db8` completed but was inconclusive (unassigned, no binding);
it is not a positive.

- Every local positive put its selected clients in DHCP mode before the
  native enable. Its executed enable guard required each one to be DHCP-on
  with IP/mask `0.0.0.0`, a pending acquisition. The first attributed row
  appeared on group sample 2. Remote `17680441` was also mode-first and
  directly read true/zero before its pool write and enable. Remote
  `499773bf` enabled first and then activated the client.
- e8 ran the same order, but its E5 apply/verify/readiness phase lasted
  21:16:30.079-21:23:44.908 UTC before E6 started. The native enable's
  retained pre-state shows all five HQ clients DHCP-on with APIPA/16
  addresses (`state: apipa`). It also shows the exact planned disabled
  three-pool process. The enable changed false to true. Branch clients were
  APIPA from their first acquisition sample. No client acquired in any of
  thirteen samples per group.
- No run dispatched `AcquireDhcpLease`. e8 contains no client-mode assertion
  after the enable, so it does not test whether reasserting true restarts
  acquisition. Exact per-action timestamps were not retained (journal
  `started_at`/`finished_at` are null), so the APIPA onset time is unknown.
- Server differences remain. e8 is the only run combining a tuned native
  pool, two named pools, four process-wide exclusions and three enable calls
  (one false-to-true, two true-to-true reassertions).
- The installed vendor reference documents `Pc::setDhcpFlag(bool)`,
  `HostPort::setDhcpClientFlag(bool)`/`isDhcpClientOn()` and
  `DhcpClientProcess::dhcpRun(string)` ("start DHCP on the port"), plus
  `dhcpRelease`, `resetDhcpConfOn` and `getDataOfPort`. It documents no
  renewal member and no same-value setter or enable-restart semantics. These
  are DOCUMENTED, not qualified. The ordinary mode helper calls
  `device.setDhcpFlag(value)` unconditionally; the native guarded path
  refuses an already-on client.

Ranked hypotheses: (1) an APIPA client is not re-acquired when a server later
starts, while a pending client is (moderate confidence); (2) the mixed
native-plus-named startup prevents serving (moderate); (3) a relay-only
failure (low, because local HQ clients failed identically). MAC attribution is
excluded, because no lease row exists to mis-join. None is confirmed, so
product behavior does not change yet. Adding a post-enable acquisition step
or reordering activation needs a native discriminant first.

The next native question is a distinct private stage, `SP2-MIXED-ACQUISITION`
v1. `SP2-MIXED-PRODUCT` and `SP2-CAPACITY-PRODUCT` keep their definitions,
hashes and behavior. The new stage composes exactly the mixed contract and
runs the same private product, which reproduces or refutes the e8
precondition. Only if every arm client is then directly read DHCP-on/APIPA,
with the server enabled on the exact three planned pools, does it apply one
typed intervention per arm through existing runtimes:

| Arm | Clients | Intervention | Question |
| --- | --- | --- | --- |
| A `reassert` | HQ PC-01, BR1 PC-02 | ordinary DHCP-mode true reassertion on an already-on client | does a same-value assertion restart acquisition? |
| B `explicit_start` | HQ PC-02, HQ PC-03, BR1 PC-01, BR2 PC-01 | one `AcquireDhcpLease` (`dhcpRun(port)`) under its execute-once claim | does the documented explicit start recover APIPA? |
| C `control` | HQ PC-04/05, BR1 PC-03, BR2 PC-02/03 | none | does anything recover passively in the same window? |

Design revision before implementation was frozen: an earlier draft of this
table had a fourth arm, D (mode false, then true), on HQ PC-03 and BR1
PC-02. There is no typed action that turns DHCP mode off without assigning
a static address: the only typed mode-false path, `SetEndpointStaticAddress`,
installs an address. So D would have been an addressing change as well as a
mode transition, and it was dropped rather than modelled by a raw setter.
Its clients joined the explicit-start and reassertion arms. Every physical
pool therefore has an explicit start and a control, and HQ and BR1 also a
reassertion. The registered stage (`SP2_ACQUISITION_ARMS`) and the prepared
episode plan bind exactly this assignment.

One bounded shared window then reads all eleven clients and the three
physical pools with the existing readers and the stage's finite cadence. Each
arm reports its first usable reading, exact intended-pool row join, gateway,
resolver and stability. Outcomes decide the product change: B acquiring while
C stays APIPA supports an explicit post-enable acquisition. A acquiring contradicts the same-value no-op hypothesis. No arm
acquiring raises the server-startup hypothesis. A control that acquires
confounds attribution. A product that serves every client means e8 did not
reproduce; that is reported, not hidden. The intervention measurement is a
discriminator, never product acceptance, default support or capacity. It
adds no server restart, pool rewrite, renewal claim or retry of an
unknown-outcome effect. Unobserved preconditions skip every intervention.

Tests use independent stateful Node stubs that model APIPA fallback, no retry
on server enable and each arm's alternative behavior. Real composition proves
precondition refusal, per-arm evidence, the execute-once claim, budget/stop
behavior, terminal inventory and owned cleanup. Mixed and capacity definition
hashes and their offline traces stay unchanged.


### Acquisition discriminator implementation and offline verification

`SP2-MIXED-ACQUISITION` v1 is registered beside the mixed and capacity
stages. It reuses their fixture, contract binding, private product and
terminal readers. Its ceiling is 3,400 operations/4,200 seconds, with a
planned worst case of 3,202: setup 73, product 2,800, arms 200, terminal 90
and reserve 39. Ownership follows the layers:

- Domain `sp2_acquisition_discriminator.py` holds the pure precondition and
  per-arm decisions.
- `service_diagnostic_profiles.py` gains two projections. One is an ordinary
  DHCP-mode reassertion with the four native guard fields cleared. The other
  is one typed `AcquireDhcpLease` per client, derived from its own segment's
  pool and waiting on that service's server-state read-back.
- The driver is a second entry point in `workflows/sp2_mixed_product.py`,
  because workflows may not import one another.
- Q3-FL's dispatch classifier moved unchanged into `product_support` as
  `acquisition_request_outcome`, so the two workflows share one decision.
- The terminal gains an observation-only completeness mode; its default
  keeps the mixed/capacity behavior and record shape.

Fail-closed effects:

- Arms run only after the product completed with known effects and a
  persisted record. Every client must be read DHCP-on at 169.254/16 with a
  usable MAC. The server must be read enabled on exactly its three planned
  pools, and every pool scanned with no row for any client's MAC.
- An unreproduced state stops the run before any intervention, and the arms
  record states why it never ran. A product that serves everyone is NEGATIVE
  for the e8 hypothesis.
- Reassertion goes through the configuration applicator, and an unknown
  reassertion stops the stage before any explicit start.
- Explicit starts are applied one client per service application, with the
  product's server rows retained (never redispatched), a per-start nonce and
  a private copy of the acquisition capability.
- The first unknown start outcome stops every later start; nothing is
  retried. Every arm client always has a recorded intervention outcome.

A sample counts toward acquisition only when it is complete: the client
reading, an observed binding for the same address and mask, and every
planned physical pool scanned. Acquisition then needs two consecutive such
samples with one identity:

- DHCP mode on;
- an address in the intended lease window with the pool mask;
- gateway and resolver from the binding;
- an exact or normalization-equal row in the intended physical pool;
- no positive, repeated, wrong-MAC, MAC-elsewhere or MAC-without-address row
  in any other pool.

An unknown intervention, an unread client or a failed binding lookup leaves
a non-acquiring client undecided, never negative. A control that acquires
confounds every arm. The ordinary endpoint batch swallows setter exceptions,
so a reassertion is "dispatched" when its batch evaluated and its mode
read-back verified; that limitation is recorded.

Review dispositions (independent Codex passes; each finding reproduced RED
before its fix unless noted):

- Pass 1 was cut short by a session restart; its captured notes named two
  defects. A binding row for a failed lookup counted as an observation, and
  one application dispatched every start after an unknown outcome.
- Pass 3: a MAC-elsewhere row in a competing pool was not treated as
  competing; an unread competing pool still allowed acquisition; and the
  binding was not required to describe the joined address.
- Pass 4: a `pool_absent` answer counted as scanned, and the link-local
  test was a text prefix.
- Pass 5: two defects.
  - A reassertion row that failed without a known non-submission, or any
    reassertion over an unknown transport, was classified as not
    dispatched. It now becomes `outcome_unknown` and blocks every explicit
    start.
  - A scan with a row after its end (`non_monotone`) or an unexplained throw
    counted as read. A scan now counts only with contiguous rows from index
    0 and at least two null or observed native-end tail entries.
- Pass 6: a non-acquiring client with a missing MAC or a binding that
  disagreed with its reading still counted as completely observed, and so
  could become negative. Completeness now requires the identity and an
  agreeing binding. Separately, the terminal's observation-only predicate
  was evaluated for every stage: a mixed terminal binding row without a
  device raised `TypeError` where the code at HEAD concluded INCONCLUSIVE. It
  is now evaluated only for the discriminator and validates text device
  identities; a mixed-stage regression pins the HEAD behavior.
- Pass 7 approved: no violation of the five required properties survived,
  the moved classifier is text-identical, and the planned budget is
  3,202/3,400 operations.
- From the helper reviews: the arms phase concludes its record in a
  `finally` on every exit after the first effect, with every client's
  outcome, an in-flight effect recorded as unknown, and every completed
  window read retained. The persistence-loss regression was written after
  its fix; a mutation disabling the partial conclusion makes it fail.

Offline verification: 34 pure cases and nine real-composition stage cases
(43 in total) cover patterns, stability, competing and hidden rows,
undecided readings, failed bindings, absent, unread and incoherent pools,
mismatched bindings, the native end, the precondition, both projections and
the reassertion classifier. Stage scenarios cover:

- explicit start only;
- reassertion that also acquires;
- a product that serves everyone;
- a throwing `dhcpRun`;
- persistence loss after one start;
- a refusal midway through the window.

The Node stub gained `dhcp_mode_reassert_acquires`, whose default keeps
existing behavior. The e8 scenario uses a delayed APIPA fallback, because an
instantaneous one contradicts the native guard's pending post-read. The
refactor's handler inventory names the stage as an explicit successor
delta. The 23-file affected set passes 715 cases.

The e9 LIVE helpers are a reviewed successor of the approved e8 snapshot.
Only `authority.py`, `make_episode.py` and `seal_episode.py` change:

- they admit exactly three registered private stages;
- they bind the acquisition arm assignment into preparation and opening;
- every record must carry exactly its stage's declared measurement set;
- the acquisition ARMS record must name every prepared arm client or
  explain its absence;
- the e8-specific twenty-artifact count is replaced by an exact named
  verification set.

Round 1 of the independent helper review failed with four blocking
findings, all accepted: arm scope, ARMS evidence, a non-isolating allowlist
control and non-discriminating artifact controls. Fixing them exposed a
pre-existing weakness in the approved controls: their fixture ledger always
held a closing record, so every launch-level negative refused vacuously.
The harness now serves an open-episode ledger before sealing. A per-stage
positive control proves each fixture reaches the claim boundary.

Rounds 2 and 3 found two further blockers each: unrun ARMS after a
persistence loss and unvalidated outcome values, then interrupted windows
and an arm-agnostic outcome vocabulary. All are closed. Mutation evidence
for the successor controls: 152 pass against the fixed candidate, while
the round-1, round-2 and round-3 candidates fail 22, 12 and 1. Removing
the stage allowlist is caught only by the two allowlist controls. Replacing
the named set with a count of sixteen is caught only by the same-count
substitution. Removing the outcome check is caught only by the nine outcome
controls.

Round 4 passed spec and quality with no blocking finding. The approved
snapshot `137afcd5ff0a508681a49ccf1b3b891d531ab16023e40b4d68ddfa09b44479fa`
is the e9 lead's `helper-snapshot.json`, and the approval record is
`helper-review-approved-e9.json`. Helpers run only from `e9/lead/tools` with
`python -B` and that externally pinned digest. The review package is
retained under `data/services/sp2-governed/e9/helper-review/`.


### Episode 9 containment classification correction (2026-10-03, risk S)

Starting source is `c860f12ab24bf6275c4103f2632a3206185d7695` on
`feature/server-pt-goal-foundations` in the goal-foundations checkout. The
mutation-containment sweep mistakes descriptive `dhcpRun` strings in the mixed
workflow and pure acquisition discriminator for dispatch. Add both modules to
`PAYLOAD_BUILDERS_AND_PROSE`, with the existing explicit rationale precedent.
Acceptance requires the focused classification test and entire containment
file to pass, followed by the complete clean exact-commit gate set and six-job
exact-SHA CI before e9. Production behavior, containment families, the approved
three-arm design, and pinned e9 helper bytes remain unchanged. New unit,
integration, and LIVE tests are not applicable to this test-only correction;
the existing structural tests verify its contract. Episode 9 remains risk L
and follows its separately approved helper and evidence controls.


## Episode 9 acquisition discriminator result (2026-10-03, risk L)

Episode 9 executed `SP2-MIXED-ACQUISITION` v1 on clean source
`ec3b01f84896c9a392f7cc142443460c9d76b8eb`, tree
`dabbfd0a848e145e049f283073023f32dd842e07`, attempt
`fd5257f2868208764d6d76595d649a53`, PT `9.0.1.0858` through `file`.
The containment correction passed its focused test, all 35 containment tests,
Ruff and independent read-only review. The complete affected suite passed 718
on a no-change retry after a retained native Python/Pydantic access violation;
the initial failure and environment remain archived without an inferred cause.
The full suite passed 8,864 with 6 skipped and 3 warnings in 1,191.49 seconds;
scale, clean exact-commit delivery, docs, namespace and whitespace passed.
Exact-source CI `37131611036` passed all six jobs. Its complete metadata/logs
and all sixteen source-verification artifacts are retained. The independently
approved helper snapshot remained
`137afcd5ff0a508681a49ccf1b3b891d531ab16023e40b4d68ddfa09b44479fa`;
all eleven helpers ran unchanged with `python -B` from the e9 lead.

The qualification stopped after 535 operations with
`sp2_acquisition_precondition_not_reproduced`, with no secondary failure. The
product failed its complete mixed-service contract. At the precondition sample,
all eleven selected clients were observed in DHCP mode: ten held APIPA/16,
while `BR1-DEFAULT-PC-02` held `10.80.16.2/28`, MAC `00E0.8F11.0627`, and a
positive lease row in physical pool `BR1_DATA`. The precondition causes were
`client_not_link_local:BR1-DEFAULT-PC-02:not_link_local` and
`client_row_present:BR1-DEFAULT-PC-02:BR1_DATA`. The product measurement is
INCONCLUSIVE, not accepted product evidence.

The all-APIPA precondition was therefore not reproduced.
`M-SP2-ACQUISITION-ARMS` is `not_run` / `not_evaluated`, reason
`not_reached:sp2_acquisition_precondition_not_reproduced`: neither intervention
arm ran, and their comparison remains unanswered. The terminal measurement is
`supported_in_sample` only for its observation/inventory completeness contract.
The acquisition onset and mechanism were not observed; the one positive client
does not establish explicit-start or reassertion causality, renewal, exclusive
serving, general relay support, capacity, default-catalog support or acceptance
of the eleven-client product. No capability was promoted.

An operator-provided screenshot of the same PC/address/MAC is retained as
supplemental evidence; its capture time and process identity are not independently
bound. The operator also reported an Offline UI indicator. The archived
qualification records `transport.liveness=heartbeat_fresh` and the precondition
stop above. A separate session-only read-only mailbox check found a fresh file
heartbeat after the report; that supplemental check is not independently
replayable from the sealed archive. The indicator's underlying connection was
not diagnosed.

Restoration was proven with `dirty_state=clean` and empty engine/coordination
residue. The owned PID `16032` retired with `exited` on the first invocation.
The final census contained no Packet Tracer process, mailbox file or campaign
lock. Episode 9 closed `verified_clean`; the verified ledger has no open episode,
2,618 operations and 6,416.133691 seconds committed, leaving 16,382 ordinary
operations and 14,583.866309 seconds. No acquisition mutation was replayed and
no channel fallback occurred.

The approved seal/publication helpers verified 237 hashed entries and identical
sealed/published manifest digest
`05931aea66f633c233a49fe1a203b9cc961caa3be137ae23edc07c7e85110867`. The
[complete e9 archive](../../reference/server-pt/evidence/sp2-generalized-dhcp-relay-01/e9/README.md)
preserves qualification/product records, the closed campaign store, source
verification, helper approval/bytes, operator supplement and cleanup evidence.
The archive publication commit preserves the executed source identity above.
The e9 result is truthful private evidence ready for independent archive review;
SP2 phase completion and public-product acceptance are not claimed.

Independent read-only archive audit: PASS, zero blocking findings. The reviewer
verified the complete sealed/published/staged file set and byte hashes, exact
source/CI/helper identities, the cited product bytes, withheld arms, terminal
completeness versus usability, restoration/retirement/census and live/archived
ledger equality. Its narrative qualification is reflected above: the later
mailbox check is session context. Archive/evidence delivery is READY_FOR_REVIEW;
the intervention comparison and SP2 phase/public-product acceptance remain open.

## E9 continuation: eligible-cohort acquisition design (2026-10-03, risk L)

Authority: `SERVER-PT-SP2-E9-CONTINUATION-03` v1.0.0, retained under
`docs/reference/server-pt/assignments/Prompt_SP2_E9_Continuation.md`.
Starting checkout/branch: `Cisco-MCP-server-services-goal-foundations`,
`feature/server-pt-goal-foundations`, clean `2d38364dfc5269accc427ae1a99b359b3132d366`,
tree `2be89db07854b8bd266fc28e3f9e3804e3efb65b`. Current `cisco/main` is
`6263344e31ba3b0de6539d652f2cd06fc73a3562`. Interpreter and production import
origins match this checkout; no retired namespace or pytest was loaded in the
inspection process. Interactive loader effectiveness remains unobservable.

E9's original product status is failed. PC02's eleven later usable samples are
retained-state observations; the ten other clients' dependent requests were
withheld. The v1 all-APIPA oracle refused correctly; neither arm ran. Its source,
profile, spent attempt, archive bytes and interpretation remain immutable.

### Prospective question and rules

Select recovery of eligible clients as the smaller discriminator. Initial
activation ordering remains a competing hypothesis, not a supported correction.
Create a separate `SP2-ELIGIBLE-ACQUISITION` profile v2 using the same mixed
fixture, typed product, probes, runtimes, stores and ownership controls. Keep
`SP2-MIXED-ACQUISITION` v1 executable with its unchanged all-client oracle.

Before outcomes, assign HQ PC02/PC03, BR1 PC01 and BR2 PC01 to explicit start;
all other selected clients are no-intervention controls. Do not reassign arms.
Eligibility requires observed DHCP-on APIPA/16, usable unique MAC, observed
binding readers, exact enabled server policy, and complete scans with no client
identity row in any physical pool. A usable assigned client is an observer,
never an intervention success. Unknown/local unreadable state is ineligible;
shared unreadability, wrong/duplicate identity, competing pool or policy drift
refuses the affected comparison. Each compared pool needs eligible explicit
start and control subjects. Report the actual remaining family, not a universal
acquisition claim.

Take fresh shared client/binding/server/pool observations before each individual
typed `AcquireDhcpLease` effect. A client acquiring before its effect becomes an
observer by the declared rule; never force it back into failure. Freeze the
assignment and retain every reclassification. No reassertion arm is needed for
this question. Refuse after uncertain dispatch, persistence/authority loss or
exhausted budget; never repeat an ambiguous mutation.

Read all selected subjects and all pools in one shared window. Record actual
elapsed boundaries for every auxiliary read, intervention and sample; waits
alone are not elapsed time. Preserve activation order and uncertain activation
ages, which constrain causal interpretation. A stable pair records observed
acquisition; later missing/contradictory prerequisites cannot authorize a causal
success. Control acquisition confounds causal credit. A simulation schedule is
offline scenario evidence only. No manual UI interaction is part of measurement.

### Implementation and verification plan

1. Add pure eligibility and sustained-outcome rules with RED-first cases for
   E9's one assigned/ten APIPA mix, unreadable scans, duplicate identities,
   missing comparisons, pre-effect acquisition and late shared contradictions.
2. Register the separate profile and integrate it into existing qualification
   composition, admission and execution. Exercise real generated acquisition
   scripts and reloaded records, including dispatch/persistence/budget failures.
3. Correct the common session's omitted E6 wait allowance at its owning seam;
   its E5 already receives it. Reproduce the omission before correction and
   verify real polling bounds. This defect does not explain historical E9,
   whose qualification runtime separately supplies its enclosing allowance.
4. Publish the post-E9 passive investigation as a dated supplement outside the
   sealed E9 archive. Pin original bytes and distinguish reported observations
   from surviving raw inspection evidence and from causal inference.
5. Run focused/affected/full tests, actual offline scale, quality/docs/namespace/
   whitespace, clean exact-delivery gate and exact-SHA CI. Independently review
   the concrete prospective helper snapshot before any LIVE effect; the old
   helper approval covers only its old bytes.
6. Under verified fresh ledger/process/source authority, measure the discriminator
   and use its supported outcome to choose the smallest maintained correction.
   Then demonstrate mixed and simultaneous local-36 capacity through the public
   default-catalog path. Do not promote a private result or mark this step done
   before those native requirements are demonstrated.

The read-only ledger audit verified 2,618 committed operations and
6,416.133691 seconds, leaving 16,382 ordinary operations and 14,583.866309 seconds
with no open episode. This is a snapshot, not a new resource grant. Recheck before
effects and preserve 1,000 operations/600 seconds of campaign finalization.
Status remains ACTIVE_CONTINUATION_NOT_PHASE_ACCEPTANCE.
### V2 effect-boundary refinement

Independent review reproduced an excluded observer's wrong-MAC own-pool row
escaping shared refusal. A RED-first regression now covers that contradiction
in both cohort admission and the retained window. V2 checks own-pool conflicts
for all selected subjects; local exclusion cannot authorize shared evidence.

Source review also found that the typed explicit-start script only checks DHCP
mode immediately before claiming the effect. A passive acquisition between the
shared census and that call must not cause an unnecessary restart. Add an
internal serialized `required_address_state` to `AcquireDhcpLease`, defaulting
to its existing DHCP-mode contract. The eligible projection selects `link_local`;
the maintained generator observes the documented HostPort address/mask getters
inside the same guarded script, before the claim and `dhcpRun`. Changed or unread
state dispatches no acquisition. A known non-dispatch for an already-addressed
subject is re-read and reclassified as an observer; uncertainty remains stopped.
Test actual generated scripts for assigned, APIPA and unreadable states and
unchanged ordinary acquisition. This is a typed effect prerequisite, not a new
public input, transport, dispatcher or native retry claim.
### Continuation verification and originating test correction

Candidate `f4496f24bee4ef3b322f0d7c8edf93c1b4f37970`, tree
`4440c1cc13418a2f6254d417d7ce09f7e92f077c`, passed 220 focused cases, the
provisional quality/docs/namespace/whitespace checks and its clean exact-delivery
gate. Actual offline SP2 loads constructed 2/21/201/997 clients; the largest
used ten group scans, 6,020 dispatches, 3,559,991 response bytes, 24,607,650 record
bytes, 54.70 seconds and 184.3 MiB peak. These are substituted product components,
not native capacity. The complete local run returned 8,892 passed, six skipped,
three existing warnings and one failed architecture inventory case in 1,578.62
seconds. The initial failure and source identity remain retained.

The failure was reproduced alone before correction: the explicit named-successor
handler test omitted `SP2-ELIGIBLE-ACQUISITION`. Add its expected existing mixed
acquisition handler to that table; preserve the exact set and object-identity
assertions and the immutable starting-handler table. All 36 architecture tests
then passed. This is an originating test-design update for the new registered
profile; production Python bytes are unchanged. A fresh complete green run and
exact-source CI remain required before LIVE. No native episode was allocated.

Independent helper review closed an eligible-outcome omission and a v2 archive
label defect. The prospective README now separates the measurement conclusion
from the original product record status and prints the actual profile version.
Its exact reviewed helper snapshot is
`f74d300c8a21d04987ff72385853ae3e1238173409ab877f03d954fb019afed4`.
The old snapshots, findings and negative checks are retained separately. Scope is
exact helper bytes, not source delivery, LIVE admission or phase acceptance.

### E10 continuation checkpoint, 2026-10-03

Execution source `40d6cfc46f23a44c9e087c484664808324fe8436`, tree
`566f4635697484f328c3514f4a1b4b1d443620bf`, passed the complete local suite:
8,893 passed, six skipped, three existing warnings. All six exact-source CI jobs
in run `37153740989` succeeded; per-job skip reasons are retained in the
[checkpoint report](../../reference/server-pt/evidence/sp2-e10-continuation-2026-10-03/README.md).
The preceding architecture inventory failure was corrected and retained; it is
not the current source result. This publication successor changes evidence and
documentation only; native provenance stays attached to `40d6cfc`.

Episode 10, attempt `cc423f961af6c86f4917687541af4133`, measured the reviewed v2
eligible cohort on PT `9.0.1.0858` / file. Four fixed explicit-start subjects
acquired stable usable leases with exact intended-pool joins; seven untouched
controls stayed unassigned. The measured `explicit_start_only` contrast is
SUPPORTED_IN_SAMPLE. The original product status remains `failed`, with
`product_accepted=false`; dependent service requests were withheld before the
intervention. No post-intervention cold HTTP/public acceptance was demonstrated.
This supports selecting a maintained acquisition-lifecycle correction within
the observed scope, not promotion of generic/native/relay capability.

Qualification completed with 574 operations, 1,319.875 seconds elapsed and a
337.453 seconds of accumulated local authority observations. The shared
acquisition window separately lasted 139.531 seconds. Restoration was proven; owned
retirement and closing evidence prove final cleanup `verified_clean`, although
the qualification's earlier top-level dirty-state field is `unknown`. No owned
process, mailbox command or campaign lock remained. The immutable
[E10 archive](../../reference/server-pt/evidence/sp2-generalized-dhcp-relay-01/e10/README.md)
contains 248 manifest entries, all hash-verified against the sealed copy.

Fresh post-E10 accounting has zero index findings and no open episode:
3,192 cumulative charged operations / 9,018.09912 seconds; 15,808 ordinary
operations / 11,981.90088 seconds remain. E10's enclosing lifecycle charge is
574 operations / 2,601.965429 seconds. Preserve the separate 1,000-operation /
600-second finalization reserve and recheck admission before another effect.

Status remains ACTIVE_CONTINUATION_NOT_PHASE_ACCEPTANCE. Maintained public
product integration, registered four-argument default-catalog mixed 5+3+3
acceptance and simultaneous native local-36 remain pending. Offline 997-client
scale is not native capacity. No READY_FOR_REVIEW, phase closure or merge is
claimed. The user's requested commit/CI checkpoint and report preserve those
remaining requirements explicitly.
