# E9.5 runtime debt register

This register is the work queue for controlled Packet Tracer validation during
E9.5. It intentionally does not convert source code, parsers, fixtures, prior
documentation, or configuration acceptance into fresh runtime evidence.

The current entries are therefore conservative. Except for the isolated
PhoneControl boundary noted below, live debts remain `UNKNOWN` and pending
until the E9.5 run records a controlled result. This file must be updated with
evidence references before the final E9.5 recommendation.

## Closure rules

Every final row must end in exactly one project-level closure classification:

- `FIXED_AND_VERIFIED`: root cause, code fix, regression, full suite, and live
  proof where runtime is involved;
- `ARCHITECTURALLY_RESOLVED`: model, migration, tests, documentation, and no
  dependency regression;
- `BACKEND_LIMITATION_CONFIRMED`: controlled negative reproduction for an
  exact backend version/model/operation, with a safe gate in code;
- `NOT_REPRODUCED_WITH_EVIDENCE`: the reported defect did not reproduce under
  the recorded controlled conditions;
- `BLOCKING_FAILURE`: required behavior remains broken after bounded diagnosis
  and prevents the next milestone.

`UNKNOWN`, `UNSUPPORTED`, `UNOBSERVABLE`, and `FAILED` remain distinct runtime
semantics:

| Runtime status | Meaning |
| --- | --- |
| `UNKNOWN` | Support has not been established. |
| `UNSUPPORTED` | Exact negative capability evidence establishes lack of support for the recorded scope. |
| `UNOBSERVABLE` | The feature may work, but the available observer cannot prove the claim. |
| `FAILED` | A fresh attempted expected behavior did not occur. |

A timeout is not `UNSUPPORTED`; a missing getter is not proof that the feature
does not work; empty neighbor output is not proof that a routing protocol is
unsupported; and a behavioral failure is not `UNOBSERVABLE`.

## Required evidence packet

Closing a runtime row requires all of the following:

1. exact Packet Tracer version and platform;
2. exact device model or service process;
3. disposable topology/slice identity and physical hash where available;
4. exact typed operation or registered query;
5. isolation level and pre-probe inventory fingerprint;
6. fresh observation method and current-attempt window;
7. positive and negative controls when the claim is behavioral;
8. observed value or bounded negative evidence;
9. cleanup result and post-probe inventory fingerprint;
10. evidence record or artifact reference;
11. final runtime status and one allowed closure classification.

If inventory restoration cannot be measured, record
`inventory_restored=None`; do not write that cleanup was verified.

## Runtime closure table

`PENDING_LIVE_VALIDATION` is a work state, not a final closure classification.
The source-level guardrail column records what is implemented without claiming
that Packet Tracer has been measured in this E9.5 run.

| Debt | Current source-level guardrail | E9.5 closure state |
| --- | --- | --- |
| 3560 SVI | Typed L3 configuration and fresh operational verification paths keep configured/admin state separate from line protocol state. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_VALIDATION` on a fresh 3560 device/session. |
| PoE | Capability discovery preserves absent reliable port-power evidence as unknown. | [ADVERTENCIA] `UNKNOWN — PENDING_CONTROLLED_REPRODUCTION`; do not infer from model names. |
| Modules | Product deployment now separates one-shot module application, fresh physical-effect readback, and exact identity. The 2911/HWIC-2T slice verifies added serial ports without equating requested slot `0/0`, observed module number `0`, or requested identity. | [OK] `BACKEND_LIMITATION_CONFIRMED` for exact module identity on Packet Tracer `9.0.1.0858` / 2911: the direct name remained absent while the physical effect was `VERIFIED`. Scope is this exact model/module slice; other modular models remain `UNKNOWN`. Evidence: `../architecture/stage-3a4-serial-product-slice-2a.md`. |
| Access-port direct getter | `ACCESS_PORT` is verified from a direct `SwitchPort` object read: owner device, port name, `getAdminOpMode()` against a measured code table, and `getAccessVlan()`, each a separate field status. | [OK] `FIXED_AND_VERIFIED` on Packet Tracer `9.0.1.0858` / `2950T-24`. Qualified live with three controls in one session — an access port on VLAN 742, a trunk, and an untouched port — each corroborated by an independent `show interfaces <if> switchport` read: the shipped read-back returned `verified` on the first and `failed` on the other two. `isAccessPort()` was measured to be `True` for an unconfigured `dynamic desirable` port and is deliberately NOT the mode gate. The registered IOS query paginates even scoped to one interface, stays out of `_PAGINATION_QUALIFIED_QUERIES`, and corroborates rather than claims. Owned by `TD-ACCESSPORT-READBACK-001`, now RESOLVED. Scope is this exact model/build; `DHCP_POOL` is untouched. |
| DHCP pool getter | E5 models direct DHCP-pool observation separately from application. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_VALIDATION`. |
| DHCP gateway getter | Gateway is an independent DHCP verification field. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_VALIDATION`. |
| DHCP DNS getter | DNS is an independent DHCP verification field. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_VALIDATION`. |
| HTTPS behavior | E6 compiles a typed HTTPS fetch and preserves the `https` scheme; it does not substitute HTTP. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_BEHAVIOR`; compile readiness is not behavior. |
| NTP sync | Service readiness can classify verification as unobservable without treating activation as synchronization. | [ADVERTENCIA] `UNKNOWN — PENDING_CONTROLLED_REPRODUCTION` of an independent synchronization observer. |
| TFTP publication | TFTP enablement and file publication are separate typed actions, and `create cnf-files` now declares `EXECUTE_ONCE` rather than `REPLACE`. | [OK] `BACKEND_LIMITATION_CONFIRMED` for the REPEAT EFFECT on Packet Tracer `9.0.1.0858` / `2811`: the command was dispatched twice under control and no observer exists — `show telephony-service` is not implemented in that image, `show ephone` answers empty, none of the 146 enumerated `Router` members touches telephony, and only `VlanManager` answers `getProcess` out of nine candidates. Two identical silences are NOT idempotence: publication itself remains unclaimed. Owned by `TD-VOICE-001`, now RESOLVED. |
| TFTP transfer | Typed client behavior is separate from server activation/publication. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_BEHAVIOR`. |
| Phone structured call API | `UnavailablePhoneControl` produces an `UNOBSERVABLE` typed result when no documented structured adapter is supplied. | [ADVERTENCIA] `UNKNOWN — PENDING_BACKEND_LIMITATION_REPRODUCTION`; source policy alone does not close the limitation. |
| Phone UI call adapter | Native UI control is encapsulated behind `PhoneControlPort`; E8 receives only a typed E7 behavior operation. | [OK] `ARCHITECTURALLY_RESOLVED` for the boundary; live call behavior remains `UNKNOWN — PENDING_LIVE_VALIDATION`. |
| PC-through-phone data | Data behavior remains independent from phone registration and call behavior. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_BEHAVIOR`; do not diagnose it from E8. |
| Audio/RTP | `VoiceApplicationResult` keeps audio observability independent and defaults it to unobservable. | [ADVERTENCIA] `UNKNOWN — PENDING_CONTROLLED_REPRODUCTION` before any backend-limitation closure. |
| Intersite voice | Non-local dial rendering returns `CAPABILITY_UNKNOWN`, not unsupported. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_VALIDATION`. |
| Static NAT | E8 requires typed traffic plus an exact matching translation and a current row/hit delta; a stale row cannot verify the attempt. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_BEHAVIOR` for the exact static mapping. |
| Dynamic NAT | E8 checks the translated address against the compiled pool and requires a current delta. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_BEHAVIOR` for dynamic pool allocation. |
| Port-security violation | Direct configuration/read-back is not treated as a controlled violation; sticky learning and behavior can remain unobservable. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_NEGATIVE_CONTROL`. |
| DAI trusted readback | VLAN/active state and interface trust fields are separate; missing/paginated trust rows remain unobservable. | [ADVERTENCIA] `UNKNOWN — PENDING_REAL_OUTPUT_FIXTURE_AND_LIVE_VALIDATION`. |
| 2811 security | The capability profile contains no controlled E8 security probe for this model. | [ADVERTENCIA] `UNKNOWN — PENDING_BOUNDED_MODEL_SLICE`. |
| 3560 security | The capability profile contains no controlled E8 security probe for this model. | [ADVERTENCIA] `UNKNOWN — PENDING_BOUNDED_MODEL_SLICE`. |
| MST | The E9 domain/compiler has a typed MST surface, but renderability is not runtime state or behavior. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_VALIDATION`. |
| PAgP EtherChannel | PAgP is typed and renderable without a fresh E9.5 operational proof. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_VALIDATION`. |
| Static EtherChannel | Static `on` is typed and renderable without a fresh E9.5 operational proof. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_VALIDATION`. |
| HSRP direct role readback | HSRP forwarding and steady active/standby role observation are distinct claims. | [ADVERTENCIA] `UNKNOWN — PENDING_CONTROLLED_QUERY_REPRODUCTION`; forwarding cannot substitute for roles. |
| OSPF failover | E9 has typed failure scenarios, bounded convergence, exact links, and restore semantics. | [ADVERTENCIA] `UNKNOWN — PENDING_ROOT_CAUSE_AND_LIVE_FAILOVER`. |
| OSPF recovery | Restore is a separate mandatory stage and cannot silently restart OSPF to manufacture recovery. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_RESTORE_AND_RECOVERY`. |
| EIGRP adjacency | Process/application evidence is separate from neighbor adjacency. | [ADVERTENCIA] `UNKNOWN — PENDING_ROOT_CAUSE_AND_FRESH_NEIGHBOR_OUTPUT`. |
| EIGRP routes | Learned-route state is separate from process and neighbor state. | [ADVERTENCIA] `UNKNOWN — PENDING_FRESH_ROUTE_OUTPUT`. |
| EIGRP behavior | Forwarding is separate from configured, adjacent, and route-learned states. | [ADVERTENCIA] `UNKNOWN — PENDING_TYPED_BEHAVIOR`. |
| EIGRP failover | Failover requires a verified baseline, fault transition, convergence, and restoration. | [ADVERTENCIA] `UNKNOWN — PENDING_COMPOSED_LIVE_SCENARIO`. |
| Bridge command-path health | Health distinguishes transport-up, polling, full command round trip, degraded, and unresponsive; selection is pinned per operation. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_HTTP_AND_FILE_HEALTH_SLICE`. |
| Direct low-level link creation | `pt_add_link` validates inputs, pins a transport, receives an ACK, and requires bounded exact two-ended peer/port read-back. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_VALIDATION`; ACK alone is not closure. |
| Exact layout readback | Requested, acknowledged, observed, drifted, and tolerance are separate results. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_GETTER_VALIDATION`; ACK alone is not observed layout. |

## Update discipline

For every executed slice, add the evidence reference and replace the pending
work state with one allowed final classification. Never bulk-promote related
rows. For example:

- exact static NAT evidence does not close dynamic NAT;
- HSRP forwarding does not close direct role read-back;
- a simple OSPF adjacency does not close failover or recovery;
- phone registration does not close call control, RTP, or PC passthrough;
- layout acknowledgement does not close coordinate read-back;
- an HTTP bridge listener does not close command-path responsiveness.

If a row remains `UNKNOWN` after bounded investigation and E10 depends on it,
the final recommendation must not be `START_E10`. If E10 does not depend on the
row, preserve the precise limitation and gate only the affected scenario.

## E5 read-back coverage — measured 2026-08-18

Stage 3A4 MEG-4 run 5 is the first run in which every compiled E5 action was
authorised and applied, so it is the first measurement of what the product can
actually read back after applying. Recorded per verification kind, from that
one run on PT `9.0.1.0858`:

| Verification kind | Result | Method |
| --- | --- | --- |
| VLAN | `VERIFIED` | `vlan_manager_object_state` |
| Serial controller | `VERIFIED` | `fresh_show_controllers_serial` (multi-page capture) |
| L3 interface | `VERIFIED` | `fresh_show_ip_interface_brief` — interface, ipv4, admin state, status, protocol |
| Access port | `UNOBSERVABLE` | no registered getter |
| Endpoint addressing | `PARTIAL` | `structured_endpoint_getters` — ipv4 and netmask verified; gateway and DNS unobservable |

Only the access-port row is promoted from a work state above, and only to a
sharper work state. The endpoint gateway/DNS observation is **not** the same
claim as the `DHCP gateway getter` and `DHCP DNS getter` rows, which are about
a DHCP server's pool configuration rather than a statically addressed endpoint;
those rows are untouched. No other row moves.

## RIPv2 control-plane observation ceiling — remeasured 2026-08-19

Stage 3A4 MEG-4 run 8 applied RIPv2 through the typed product path, read it
back, and closed the source-identity field. The rows below are measured on PT
`9.0.1.0858`, not derived from source. They supersede the 2026-08-18 rows
measured at run 6.

| Row | Observed | State |
| --- | --- | --- |
| RIP routing-process observation | `protocol`, `version_send`, `version_recv`, `auto_summary`, `networks`, `passive_interfaces`, `source_device_name` all VERIFIED on both routers from a fresh `show ip protocols` | `CLOSED — aggregate VERIFIED`. |
| RIP learned-route observation | `network`, `prefix_length`, `protocol`, `source_device_name` VERIFIED on both routers from a fresh `show ip route rip`; each router learned the far-side prefix across the serial WAN | `CLOSED — aggregate VERIFIED`. |
| RIP end-to-end forwarding | measured live at runs 12 and 13: fresh typed ping, session attributed, destination and protocol bound to the execution, `reachable = True` after a bounded convergence window; reproduced in the 41-device reference acceptance with one bounded measurement | `CLOSED — VERIFIED`. Superseded run 10's `MEASURED — FAILED`, whose cause **is** now established: the measurement was premature, not the path broken. See "Reconciliation" below. |

What closed the first two rows is **execution provenance**, not a new IOS
command. `show ip protocols` and `show ip route rip` still print no hostname.
The identity comes from the envelope: the read enumerates the runtime network
and keeps the single device that can have produced that session, and the output
that gets parsed is that device's. Requested-name substitution is refused by
construction — a session owned by another device returns no output at all.

The forwarding row was measured for the first time at run 10 and returned a
negative. Both earlier blockers moved. The three numbered notes below record the
run-10 state; the negative itself was superseded at runs 12-13 — see
"Reconciliation — runs 11-13".

**1 — capability evidence: CLOSED.** `2911:routing_behavior` is SUPPORTED from
the R3 qualification (`../architecture/ripv2-runtime-qualification.md`), which
measured that the production `TypedPingExecutor` can dispatch, echo-confirm,
parse and attribute a `ping` on this model and build. Both of R3's own
measurements returned `Success rate is 0 percent (0/5)`, and that is what
qualifies the channel: the dimension is measurability, not success. The gate
was preserved and nothing was promoted without a measurement.

**2 — claim ceiling: NARROWED.** `destination_ipv4` is now certified from the
destination the executor reports dispatching and echo-confirming, and
`protocol` from the control-plane action actually applied. `traffic_flow_id`
remains UNOBSERVABLE: it is the label the compiler attaches to the claim, read
by no code, and no registered command can return it.

**3 — at run 10, the then-current blocker.** `reachable` measured `False`. Every
hop that stage could observe was verified — serial orientation, transit and
routed L3, RIPv2 process, learned routes on both routers, endpoint ipv4 and
netmask. The two it could not observe were access-port VLAN membership and the
endpoint gateway, so at that point **no cause was claimed**.

Evidence: `../architecture/stage-3a4-bounded-live-qualification.md`, "Run 10".

### Reconciliation — runs 11-13, absorbed at Debt Checkpoint 3, 2026-08-20

The paragraph above was left standing after the runs that superseded it, and
CP3 absorbed it rather than closing E9.5 over a stale negative. **The cause of
run 10's negative is established, and it was ours.** Run 11 read Packet Tracer's
own simulation event list over the failing flow: the first echo was dropped
because the next-hop IP was not yet in the ARP table, and in the same event list
ARP then resolved and the following echo crossed. The path worked; the
measurement was premature.

Two product defects followed from that, both fixed:

- reachability had **no bounded convergence window**, while every other
  observation depending on a converging plane already had one
  (`_observe_rip_route`, 45 s). It now re-reads under the same discipline —
  it stops on *agreement*, not on a favourable answer, an unattributable window
  aborts at once as UNOBSERVABLE, and nothing is ever redispatched;
- `traffic_flow_id` was accounted as a device property, so it rendered
  UNOBSERVABLE on every reachability observation and one UNOBSERVABLE turned
  the aggregate PARTIAL — E9 could never reach VERIFIED regardless of the
  network. It moved to `source_traffic_flow_id`. The claim did not narrow.

```text
run 12 / run 13   TYPED_FORWARDING = VERIFIED, reachable=True after 2 bounded
                  measurements (run 13 reproduced it)
reference         FORWARDING = VERIFIED, reachable=True, 1 bounded measurement,
                  41 devices / 41 links
```

`traffic_flow_id` remains UNOBSERVABLE as a *device* property — that part of the
run-10 ceiling stands. `TD-ACCESSPORT-READBACK-001`, recorded as OPEN in run
10's own exit record, is **RESOLVED**; access-port VLAN membership is no longer a suspect, because run
11's trace observed that segment carrying traffic. The endpoint gateway remains
UNOBSERVABLE, and forwarding verifying end to end promotes neither it nor
access-port DHCP state.

## OSPF observation ceiling — recorded 2026-08-17

Established from source at Stage 3A4 Slice 2B/3, not from a live run. Full
rationale in `docs/architecture/technical-debt.md`, "Claim ceiling — OSPF
control-plane observation".

| Row | Contract | State |
| --- | --- | --- |
| OSPF routing-process observation | `show ip ospf neighbor` establishes that the process operates. | `PARTIAL — protocol VERIFIED, router_id UNOBSERVABLE`. The local router ID is absent from that SHOW; it is declared unclaimed, not dropped. Aggregate stays UNOBSERVABLE. |
| OSPF route observation | `show ip route ospf` establishes prefix, length, next hop and interface. | `PARTIAL — wildcard and segment_id UNOBSERVABLE`. Declared unclaimed. Aggregate stays UNOBSERVABLE. |
| Narrowing discipline | Reducing what an expectation claims never raises what an observation concludes. | `ENFORCED` by `unclaimed_fields` plus regressions; a status may improve only from new observation. |

Do not promote either row on the strength of the narrowing itself. Only a live
run producing new registered evidence can move them, and neither `router_id`
nor `wildcard`/`segment_id` is obtainable from the currently registered queries
at all.

## Final E9.5 recommendation — Debt Checkpoint 3 (HARD), 2026-08-20

```text
CP3_HARD           = PASS
E9_5               = CLOSED
RECOMMENDATION     = NOT_START_E10
UNKNOWN_ROWS       = 33   31 whose closure state is UNKNOWN, plus the residual
                          UNKNOWN scopes on `Modules` (other modular models) and
                          `Phone UI call adapter` (live call behavior), both of
                          which carry a final closure classification otherwise
ROWS_PROMOTED      = 0    of those 33
ROWS_RECONCILED    = 1    `RIP end-to-end forwarding`, which was not among them
```

This is the recommendation the header of this file requires before E9.5 closes.
Full reasoning: `../architecture/technical-debt.md`, "Debt Checkpoint 3 — HARD
— result".

**No row moved, and that is the finding rather than an absence of one.** Every
row above was classified against the current typed contracts — what it claims,
whether E9.5 claims it, whether an E9.5 product path depends on it, whether E10
depends on it instead, and whether authentic evidence already exists that this
register has not absorbed. Five promotions were proposed on the strength of the
five live qualifications E9.5 ran; an adversarial pass refuted all five, in each
case because the evidence measured a different claim, a different model or a
different protocol than the row it was offered for. The `3560 SVI` row is the
sharpest example: `svi_admin_state` and `svi_operational_state` were both
observed, but both read `up`, so the state-collapse hazard the row exists to
guard against was never exercised, and the evidence does not satisfy the
required evidence packet above: no isolation fingerprint, no negative control
and no post-probe fingerprint.

**Dispositions.**

```text
BLOCKS_E9_5 ..............  0
NO_E9_5_CLAIM_DEPENDS .... 29   no E9.5 claim asserts the property, and either
                                no E9.5 path depends on the row or the path that
                                does is fail-closed. Where a written ceiling
                                exists it is cited on the row; most of these 29
                                have none, and an absence of measurement is not
                                a ceiling
DEFERRED_TO_E10 ..........  2   EIGRP adjacency, EIGRP routes
OUTSIDE_E9_5_CLAIM .......  2   HTTPS behavior, NTP sync — no E9.5 claim asserts
                                HTTPS behavior or NTP synchronization. The
                                replay matrix does reach `EnableHttpsService`
                                and `ConfigureNtpService`, but claims only that
                                the enable flag is set and read back, on a
                                PAYLOAD_SHAPE_ONLY basis: activation is not
                                behavior, and `ServiceApplicator` has no product
                                caller
```

The 29 are **not** a count of rows with an explicit written ceiling. Only two
explicit ceilings were measured for this checkpoint, both on backend
limitations (TD-MODULE-SLOT-001, TD-TRANSPORT-001), and that narrow permission
is not extended here to rows that are not backend limitations.

**Why UNKNOWN is correct rather than outstanding.** E9.5 is a stabilization
boundary for identity, deployment, evidence, mutation, verification and failure
semantics. It declares itself not to be Packet Tracer evidence, and its gate
discipline holds a runtime status at `UNKNOWN` until a controlled reproduction
exists. These rows are that contract being honoured. An UNKNOWN invalidates an
E9.5 claim only where E9.5 claims the property or an E9.5 path depends on it —
and where a path does depend on one, `Bridge command-path health`, the gate is
fail-closed: an unselectable transport refuses the operation instead of making a
weaker claim.

**Why the recommendation is not `START_E10`.** `EIGRP adjacency` and `EIGRP
routes` remain UNKNOWN after bounded investigation, and E10 depends on them: E10
owns protocol redistribution, redistribution verification reads routes learned
by a source protocol, and E9 places overlapping routing domains outside its
scope. The rule stated above in "Update discipline" is therefore applied
literally. This gates E10's start; it does not hold E9.5 open, because
qualifying EIGRP is unstarted work belonging to the milestone that needs it
rather than an unresolved E9.5 defect.

**Unchanged by this checkpoint**, and stated so that a later reader does not
read closure as coverage: `ACCESS_PORT` is observable only for the fields listed
in TD-ACCESSPORT-READBACK-001 and `DHCP_POOL` is untouched; `ENDPOINT_GATEWAY`
remains UNOBSERVABLE; `MODULE_IDENTITY` and `MODULE_PLACEMENT` remain the
TD-MODULE-SLOT-001 backend ceiling; `CONFIGURATION_FULLY_VERIFIED = NO`;
`traffic_flow_id` remains UNOBSERVABLE as a device property; and capability
evidence remains machine-local and gitignored, so a fresh checkout resolves
every capability UNKNOWN and refuses the same plan, fail-closed.

**`OSPF failover` and `OSPF recovery` remain UNKNOWN and E9 scope.** They are
named here explicitly because Debt Checkpoint 2 instructed that "no later
milestone may treat it as discharged here", and CP3 is the last gate before
E9.5 closes. CP3 did not advance them, does not discharge them, and counts them
among the rows no E9.5 claim rests on — not among rows anything established.

**One row was reconciled rather than closed over.** `RIP end-to-end forwarding`
was still recorded as `MEASURED — FAILED` from run 10 while runs 12, 13 and the
reference acceptance had measured `reachable = True`. CP3 absorbed that
evidence — see "Reconciliation — runs 11-13" above. It was found by adversarial
review of this checkpoint's own diff, after the checkpoint had refused five
promotions for want of evidence and missed the one row where evidence existed.

## Canonicalization audit correction — 2026-08-20

The `CP3_HARD = PASS` and `E9_5 = CLOSED` recommendation above is superseded.
The literal CP3-HARD clause at its parent commit required `debt that blocks
E10: 0`. The closure commit introduced `(ledger entries)` only after this
register identified `EIGRP adjacency` and `EIGRP routes` as UNKNOWN debts that
gate E10's start. That scope did not pre-exist the closure and cannot be added
by the checkpoint being measured.

```text
CP3_E10_CLAUSE_SCOPE_PREEXISTED = NO
CP3_HARD                        = FAIL
E9_5                            = OPEN
CANONICAL_E9_5_BASELINE         = NOT_READY
UNKNOWN_DEBTS_BLOCKING_E10      = 2
```

The classifications remain exact: 29 rows are
`NO_E9_5_CLAIM_DEPENDS`, not `CEILING_ACCEPTED`; two rows are
`OUTSIDE_E9_5_CLAIM`; and the only two explicit ceiling rows are the contained
backend limitations TD-MODULE-SLOT-001 and TD-TRANSPORT-001. E10 still requires
fresh governed EIGRP adjacency and learned-route evidence with precise register
classifications before it can start.
