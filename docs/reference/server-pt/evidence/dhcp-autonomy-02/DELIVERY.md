# SERVER-PT-DHCP-AUTONOMOUS-02: delivery

**Status: READY_FOR_REVIEW.** This is the experimental delivery the mandate
(`docs/reference/server-pt/assignments/ServerPT_DHCP_Delegated_Autonomy_Mandate.md`,
SHA-256 `3bb343ef80d75c0ebf37204c8fbfd57da23eea4e5de57a7227ee1ded2e2d1ea2`)
asks for. Self-review and the Codex adversarial reviews recorded below are not
the independent audit; final approval, capability promotion and any merge to
`main` remain with an independent reviewer. The design record is
[`server-pt-dhcp-fastloop.md`](../../../../engineering/change-briefs/server-pt-dhcp-fastloop.md),
versions 5 to 13.

## Outcome

On Packet Tracer 9.0.1.0858, episode 8 ran the maintained A1-E6 product path
on an owned disposable Server-PT, IE-2000 and two-PC fixture and completed with
overall status `verified`:

- the native physical `serverPool` carried the requested one-user policy
  (`192.0.2.0/24`, window `.100`-`.100`, gateway `.1`, DNS `.10`, exclusions
  `.1` and `.10`) while the separately named logical pool stayed absent;
- PC1 acquired `192.0.2.100/24` autonomously after DHCP mode was set, and the
  required `DHCP_LEASE` check verified it against the exact IP/MAC/port row of
  the effective pool (`attributed_to_effective_server_pool`) while PC2 stayed
  DHCP-off and unassigned;
- access readiness waited for both VLAN 10 access ports to forward, on Packet
  Tracer's own simulation clock, and the required `HTTP_FETCH` check verified
  one cold request from PC1 to `http://192.0.2.10/` with fresh content;
- no explicit `dhcpRun`, ping, DNS, warm-up or client static address was
  dispatched, and the fixture was restored and the lab retired cleanly.

## Source and CI identities

Branch `feature/server-pt-goal-foundations` on `andres18113/cisco-muejeje`,
published fast-forward only; `main` is untouched.

| Identity | Commit | Tree | Evidence |
| --- | --- | --- | --- |
| Episode 8 executed source | `04c06adee4ac6a53299fc35556e8f31bac366ae5` | `6c5a6442f3ced8ba2f1552b9fd3fe99c37faccdd` | Codex review 246c06f..04c06ad: approve |
| Last code change | `2751ff0b4ba6216b5b2a4b430f151ac907f7ed3f` | `5d3fa8da90f1444d6321ecef21981714991f960e` | exact-SHA CI reported with the delivery commit |

Commits after `04c06ad` are the episode 8 archive and this document, and one
recording-only change (`2751ff0`): an access observation records nothing about
an extension unless one was a candidate. Episode 8's readiness group was a
candidate, so its behavior and recorded facts are unchanged by it, and no LIVE
rerun is claimed or needed. Exact-SHA CI was green at `93bb643` and `81af939`;
the three drift failures inherited from `27ee68c` and the two Windows
long-path failures were fixed first (brief versions 10 and 11).

## Chosen design

1. **Effective pool.** An unnamed, state-only, one-user DHCP requirement on
   Server-PT `FastEthernet0` binds to the native physical `serverPool` only
   when the exact-build capability snapshot carries a recorded-run native
   binding; the logical pool label stays distinct in the plan and record. The
   compiler admits only the measured policy. An explicitly named pool refuses
   the native strategy.
2. **Guarded effects.** E5 checks the owned, disabled Server-PT and both exact
   client ports in the same evaluation that can change PC1's mode. E6
   configures the pool while the process is disabled, reads it back after each
   setter, verifies the complete policy, then enables.
3. **State-only lease verification.** Two fresh, stable client readings must
   join an exact IP/MAC/port row in the effective pool and the complete server
   policy, with the inactive client re-read unassigned on every sample. No
   `dhcpRun` is compiled; acquisition causality stays unclaimed.
4. **Dependent HTTP.** The scheduler stages the required lease before any HTTP
   effect. The request is the cold first one, by IP.
5. **Access readiness on the protocol clock.** When the 30-second wall window
   ends on authoritative `LIS`/`LRN` evidence with the qualified 15-second
   forward delay, the observer spends one extension on Packet Tracer's
   simulation clock (35 simulated seconds under an 80-second wall cap for
   listening, the existing 20/45 for learning). The extension never exceeds the
   gate's offer, the caller's remaining time or the time owed to other groups,
   and admission still needs one timely, authoritative read with every port
   forwarding (brief version 12).
6. **Evidence integrity.** The qualification and product records are both
   sealed as campaign external sources, and any sealing or status-write
   failure stops the phase and never exits 0 (brief version 11).

## Rejected alternatives

- Substituting router DHCP, or changing the requested network to match an
  accidental lease.
- Keeping a separately named intended pool beside `serverPool`: episode 1
  showed the native pool serving while the named pool served nobody, and the
  intent never required a named pool.
- Claiming lease causality from an explicit `dhcpRun`.
- Binary patching, memory manipulation or undocumented APIs.
- For readiness: a longer fixed wall window for every group, a second
  wall-clock episode, `spanning-tree portfast` in E5, and a new per-VLAN
  `show spanning-tree vlan` query (brief version 12).
- Registering the native binding in the default catalog now: the evidence
  covers one exact policy and one client, so a default registration would
  publish a capability that refuses every other address plan. The public
  four-argument `pt_apply_enterprise_services` path therefore still refuses
  state-only DHCP and was not run LIVE with the native binding.

## Decisive original records

| Episode | Record | SHA-256 |
| --- | --- | --- |
| 8 | `e8/record/q3-native-product-2026-09-26T04-06-23Z-dc9df810.json` | `127d0c0a7116b988b50afc5b58394350878368f3d134283a98867688938516e4` |
| 8 | `e8/record/2026-09-26T04-06-23Z-dc9df810-product.json` | `6fa7a8dc0dbbbb3113ac90a61fdb5fe577459410d1b57aaa5ee309a035ad4c15` |
| 7 | `e7/record/q3-native-product-2026-09-26T03-08-22Z-aad4b6b4.json` | `a8b0ce28b50ba30bcbb34f2d65b672fafc5033b38913598d1f26131f482fe4cc` |
| 7 | `e7/record/2026-09-26T03-08-22Z-aad4b6b4-product.json` | `574e52e9d02d17e39b544333dda30a341ea37b47feaeccb9c62d058c79a0a9ee` |
| 6 | `e6/record/q3-native-product-2026-09-26T02-07-22Z-2d529b69.json` | `4146e705c5d57a242be64fb1685b32631d882ea3c9eae8c9d80bac65c406c143` |
| 5 | `e5/record/q3-native-serve-2026-09-26T00-30-30Z-f961bd3d.json` | `83e01280787c46b422c1339c2d6b7e8bce58a44aee6ac67804b3bf1edb775149` |

Every episode archive is immutable and carries its own `MANIFEST.sha256`,
whose digests are pinned in `DELIVERY-MANIFEST.sha256` beside this file.

## Scale measurements

- **LIVE:** one selected client on the native path; episode 8 used 93
  qualification operations and 330.3 seconds end to end, of which about 34
  seconds were the readiness window and extension.
- **Offline:** `tests/test_service_product_scale.py` passes at 2, 20, 200 and
  1000 clients for reporting assembly and DHCP reporting (the 1000-client
  assembly runs in about 0.06 s), and the grouped lease-evidence and DHCP
  readiness suites pass; the full suite passed locally (8130 passed, 6 skipped)
  at `246c06f`. These are offline composition measurements. No native capacity
  beyond one user was measured, and no thousand-client LIVE claim is made.

## Resource use

| Episode | Profile | Source | Operations | Seconds | Outcome |
| --- | --- | --- | --- | --- | --- |
| 1 | Q3-NATIVE | `c76ab02` | 34 | 347.474369 | stopped |
| 2 | Q3-NATIVE-SIZE | `fcafebd` | 36 | 305.361640 | completed |
| 3 | Q3-NATIVE-POLICY | `76a60a8` | 45 | 258.046850 | completed |
| 4 | Q3-NATIVE-STABILITY | `fee6a15` | 48 | 221.202394 | completed |
| 5 | Q3-NATIVE-SERVE | `04f5337` | 63 | 217.331687 | completed |
| 6 | Q3-NATIVE-PRODUCT | `7e06fdc` | 34 | 326.697598 | stopped |
| 7 | Q3-NATIVE-PRODUCT | `81af939` | 78 | 342.694246 | stopped |
| 8 | Q3-NATIVE-PRODUCT | `04c06ad` | 93 | 330.315531 | completed |

The campaign ledger totals 431 operations and 2349.124315 seconds, leaving
8,569 ordinary operations and 11,450.875685 ordinary seconds outside protected
reserve. Every episode left zero Packet Tracer processes, an empty mailbox and
no campaign lock. Offline work, reviews and CI are not charged to the ledger.

## Residual limitations

- The native binding is a private, exact-build candidate snapshot: one policy,
  one client, one fixture, build 9.0.1.0858, file channel. It is not in the
  default catalog, and the public four-argument path was not run with it.
- Renewal, explicit `dhcpRun` causality, lease-table end and native capacity
  above one user are unmeasured. The optional `dhcp_lease_attributed` check
  was unobservable in episodes 7 and 8 (`lease_client_identity_invalid`).
- The listening budget of the readiness extension is protocol arithmetic on the
  retained 15-second forward delay and the retained 0.53 to 0.59 clock-rate
  measurement; episode 8 qualifies it for this fixture and does not measure the
  rate.
- Effects run under the declared unfenced receiver interval: no dispatcher
  carries a receiver-verified session token, and exclusivity plus the
  per-dispatch process guard are local controls (brief version 11).
- A status JSON written without its digest leaves no governed retirement
  basis; that pre-existing path fails closed by quarantining the lab.
- The product record's own `dirty_state` is `unknown`; the qualification run
  proved restoration of the fixture.
- The interactive instruction-loader check (`/context`) was not observable in
  this session and remains pending.

## Next steps for the reviewer or a later mission

Qualify native pool policies beyond the one measured plan and native capacity
above one user on an owned fixture; only then consider an evidence-backed
default catalog registration and a LIVE run of the public four-argument path.
