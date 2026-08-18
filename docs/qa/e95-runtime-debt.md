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
| Access-port direct getter | E5 can return `UNOBSERVABLE` when no independent direct getter is available. | [ADVERTENCIA] `UNKNOWN — PENDING_REGISTERED_QUERY_AND_LIVE_VALIDATION`. Reached live for the first time in Stage 3A4 MEG-4 run 5: six applied access-port actions returned `UNOBSERVABLE` with `runtime_observability_limit`, because `enterprise_configuration_runtime.py:265` routes `ACCESS_PORT` to `_unobservable` — this repository registers no access-port read-back. Whether Packet Tracer exposes one was NOT probed, so this is a missing registered query, not a backend limitation. Evidence: `../architecture/stage-3a4-bounded-live-qualification.md`, "Run 5". Owned by `TD-ACCESSPORT-READBACK-001`, which defines the minimum evidence set and records that no existing registered query or structured getter covers port membership or switchport mode. |
| DHCP pool getter | E5 models direct DHCP-pool observation separately from application. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_VALIDATION`. |
| DHCP gateway getter | Gateway is an independent DHCP verification field. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_VALIDATION`. |
| DHCP DNS getter | DNS is an independent DHCP verification field. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_VALIDATION`. |
| HTTPS behavior | E6 compiles a typed HTTPS fetch and preserves the `https` scheme; it does not substitute HTTP. | [ADVERTENCIA] `UNKNOWN — PENDING_LIVE_BEHAVIOR`; compile readiness is not behavior. |
| NTP sync | Service readiness can classify verification as unobservable without treating activation as synchronization. | [ADVERTENCIA] `UNKNOWN — PENDING_CONTROLLED_REPRODUCTION` of an independent synchronization observer. |
| TFTP publication | TFTP enablement and file publication are separate typed actions. | [ADVERTENCIA] `UNKNOWN — PENDING_CONTROLLED_REPRODUCTION`. |
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
