# CP-SCALE Floor2 NETWORK_FOUNDATION offline root-cause diagnosis

## Decision

The canonical failure remains a **PRODUCT** failure. The strongest offline
conclusion is **STRONG_CANDIDATE**, not `CONFIRMED`:

> The Floor2 boundary changes a persistent, already-converged workspace in two
> coupled ways before it verifies the network foundation. It installs a new
> two-switch trunk chain into a naturally elected PVST domain whose intended
> large-site policy has not yet been applied, and it cumulatively reapplies all
> 115 Floor1 configuration actions, including the already-working Floor1 VLAN,
> access-port, and trunk actions. That boundary can restart or extend PVST
> convergence across VLANs 10, 20, and 30, which is consistent with the old
> Floor1 trunk disappearing from one terminal read and both new Floor2 links
> having a non-forwarding terminal side.

The retained artifact does not identify which of those two mutations produced
the first runtime state change. It retained the terminal `show interfaces
trunk` result and aggregate attempt count for each expectation, not the
intermediate rows or per-sample STP roots. A cumulative-replay correction and
an STP stage-order correction are therefore observationally equivalent on the
available evidence. Neither is applied in this phase; stacking them would
destroy the next causal comparison.

No Packet Tracer LIVE was run. Voice, topology, VLAN/addressing, phone,
routing, and physical-link intent are unchanged.

## Method and evidence boundary

The investigation followed
`voice_root_cause_implementation_retrospective.md`: first observable
divergence, explicit hypotheses, negative-evidence updates, separation of
measured/source/inferred claims, and `APPLIED != VERIFIED`. It used the
pre-cleanup canonical artifact
`canonical-cp-scale-voice-20260830T202000133616Z-f5e72f08a4e9-failure-precleanup.json`
(SHA-256
`d4b017332c1f0b7f12e5e6fef977a508c7b1fcdb72e1f605ad095143b54a60db`),
the canonical ledger, design authorities, source, tests, and repository
history. Graphify was used first to scope stage projection, runtime mutation,
and contradiction paths.

Labels in this document are strict:

- **MEASURED FACT** is retained output from the valid canonical LIVE.
- **SOURCE FACT** is a deterministic property of the pinned source/projection.
- **INFERENCE** is the smallest explanation consistent with both.

## Positive control and failed boundary

### Floor1 positive control

**MEASURED FACT:** Floor1 completed the production causal order:
`VOICE_SIGNAL_VERIFIED -> PHONE_ACCESS_FWD_VERIFIED -> REGISTRATION_STARTED`.
All 21 phones had authoritative access forwarding, addresses, matching DHCP
bindings, and SCCP `REGISTERED`.

**MEASURED FACT:** the Floor1 configuration application verified both ends of
the internal Floor1 trunk:

- Switch4 `Gi0/2`: 104 samples, 36,639 ms;
- Switch5 `Gi0/1`: 106 samples, 42,578 ms.

**MEASURED FACT:** the post-Voice `show spanning-tree` read on Switch5 was
executed, fresh, complete, uniquely attributed, and pagination-complete. For
VLANs 10, 20, and 30, Switch5 declared `This bridge is the root`, with base
priority 32768 and root MAC `0002.4A64.87E5`. This is not the intended
large-site final root or secondary policy; it is natural election.

### Floor2 failure

**MEASURED FACT:** Floor2 stopped at `NETWORK_FOUNDATION` before any Floor2
Voice processing. Three fresh, complete, source-attributed trunk expectations
contradicted the plan:

- Switch4 `Gi0/2`: no matching row at the terminal read, 120 samples,
  45,233 ms;
- Switch6 `Gi0/1`: trunking, VLANs 10/20/30 allowed and active, none
  forwarding, 98 samples, 45,468 ms;
- Switch7 `Gi0/1`: the same terminal VLAN omission, 81 samples, 45,047 ms.

The corresponding peer expectations verified. The exact Floor2 physical delta
also verified. No Floor2 phone was failed: all 48 phones beyond Floor1 are
`NOT_REACHED`.

## Stage semantics and first source divergence

`CPScaleCanonicalStageProjection` calls each boundary cumulative.
`_project_stage_configuration()` selects every full-plan action whose device,
link, endpoint, and site are present in the cumulative topology. It does not
subtract the preceding stage. `_execute_stage()` then passes that cumulative
plan directly to `ConfigurationApplicator.apply()`.

This differs from the physical path. `project_cp_scale_canonical_delta()`
explicitly excludes already-verified physical modules because replay would
invalidate causation. There is no corresponding configuration delta.

**SOURCE FACT:** Floor1 has 115 configuration actions; Floor2 has 191. Every
one of the 115 Floor1 IDs appears unchanged in Floor2. Floor2 therefore applies
115 old actions plus 76 new actions, not just the new 76.

**FIRST SOURCE DIVERGENCE:** the cumulative configuration view is used as a
mutation set against a persistent, already-verified workspace. Floor2 is the
first boundary where that decision reconfigures a complete, converged access
chain that the canonical run already used successfully.

The replay registry labels VLAN, access-port, and trunk actions `REPLAY_SAFE`,
but their basis is `PAYLOAD_SHAPE_ONLY` plus declarative reapplication. For a
trunk, the evidence says the complete allowed-VLAN set is assigned without an
additive form. That establishes final payload shape; it does not establish
that reissuing trunk mode, encapsulation, allowed VLANs, or access mode is
non-disruptive to Packet Tracer's live PVST state. The canonical result is the
first retained negative evidence against using that classification as a
continuity guarantee.

## Actions reapplied at Floor2

All 115 Floor1 actions are reapplied, with stable identities:

| Action type | Reapplied count |
| --- | ---: |
| `configure_access_port` | 49 |
| `set_endpoint_dhcp` | 23 |
| `create_vlan` | 9 |
| `configure_subinterface` | 9 |
| `configure_hostname` | 6 |
| `configure_routed_interface` | 6 |
| `configure_trunk` | 5 |
| `set_endpoint_static` | 5 |
| `configure_dhcp_pool` | 3 |

The old network-device totals are Switch4 30, Switch5 30, Switch10 6,
Router4 9, Router0 6, and Router3 6. Floor1's 21 Voice access actions are
again dispatched in their data-only form because Floor2's cumulative Voice
signals are deferred. The data-only renderer omits a new Voice command; it
still reissues access mode and data VLAN. It does not issue `no switchport
voice vlan`.

For trunks, the 3560 renderer reissues `switchport trunk encapsulation dot1q`,
`switchport mode trunk`, and the complete `switchport trunk allowed vlan
10,20,30` assignment. The 2960 omits the unsupported encapsulation command but
reissues trunk mode and the allowed set. A Packet Tracer batch being accepted
means `APPLIED`; it does not prove the preexisting operational or STP state
survived unchanged.

## Failed trunk action matrix

Plan positions below are one-based. Action and expectation identities are
stable across the stages in which they appear.

| Link / side | Source link ID | Action ID (position) | Expectation ID | Stages | Floor2 terminal result |
| --- | --- | --- | --- | --- | --- |
| Switch4 `Gi0/2` | `link/access_uplink/ed124a1bb284` | `cfg/trunk/6d7d7076f7253ebf` (48) | `cfg/verify/506997bfeb712df8` | Floor1, Floor2 | no matching row; failed |
| Switch5 `Gi0/1` | `link/access_uplink/ed124a1bb284` | `cfg/trunk/41efa59e3d18653e` (75) | `cfg/verify/513093c8f479dc43` | Floor1, Floor2 | verified |
| Switch6 `Gi0/1` | `link/distribution_uplink/836a589db958` | `cfg/trunk/0ec8eba3ea9d6eb6` (97) | `cfg/verify/e3a93eaca47434b8` | Floor2 | forwarding omitted 10/20/30; failed |
| Switch10 `Fa0/2` | `link/distribution_uplink/836a589db958` | `cfg/trunk/d33dce17274d176b` (119) | `cfg/verify/9d1f41b443862b38` | Floor2 | verified from current device query cache |
| Switch6 `Gi0/2` | `link/access_uplink/d52184dc92ca` | `cfg/trunk/1fbef0a80f89b4a6` (98) | `cfg/verify/3fddeb23504ebbc3` | Floor2 | verified |
| Switch7 `Gi0/1` | `link/access_uplink/d52184dc92ca` | `cfg/trunk/2eb8c2e5bff21418` (117) | `cfg/verify/a5a13a7e12eb7f2e` | Floor2 | forwarding omitted 10/20/30; failed |

Every action in this matrix was reported `APPLIED`. There is no regenerated
equivalent under a new ID, missing dependency, stale expectation, or
link/expectation cross-correlation.

## Floor1-to-Floor2 mutation order

The source-level order between Floor1 Voice success and the failed Floor2
verification is:

1. Floor1 records the after-Voice STP read, Voice bindings and canonical Voice
   correlation.
2. Floor1 applies its control plan. At this stage it contains three RIPv2
   actions and no large-site STP action.
3. Floor1 performs core pings and two read-only workspace observations.
4. Resume checks are read-only.
5. Floor2 applies and reconciles its physical delta: 58 new semantic devices
   and 41 new links; the delta plan has 59 devices because Switch10 is the
   existing anchor. The only new infrastructure devices are Switch6 and
   Switch7, and the only new infrastructure links are Switch10--Switch6 and
   Switch6--Switch7. It does not recreate the Floor1 links.
6. Floor2 applies the cumulative 191-action configuration by phase. Phase 20
   reissues VLANs 10/20/30 on Switch10, Switch4, and Switch5 and creates them on
   Switch6 and Switch7. Phase 30 reissues the old and new L2 interface policy.
   IOS devices are batched in deterministic name order: Switch10, Switch4,
   Switch5, Switch6, Switch7 among the relevant devices. Thus the Switch10 side
   of the new Floor2 uplink is configured before Switch6, and Switch6 before
   Switch7.
7. Only after all actions are accepted does verification run sequentially in
   plan order. It reaches the three terminal contradictions above.
8. Floor2 never reaches Voice or its control-plane application. Therefore no
   Floor2 RIPv2 or STP control-plane action can have caused this failure.

No mutation between the stages changes the physical Floor1 links. The relevant
mutations are the new Floor2 bridge/link membership and the cumulative VLAN,
trunk, and access-policy replay.

## Structural differential

| Dimension | Floor1 `Switch10 -> Switch4 -> Switch5` | Floor2 `Switch10 -> Switch6 -> Switch7` |
| --- | --- | --- |
| Distribution model | Switch10 `2960-24TT` | same device/model |
| Access models | Switch4/5 `3560-24PS` | Switch6/7 `3560-24PS` |
| Distribution port | Switch10 `Fa0/1` | Switch10 `Fa0/2` |
| Access uplinks | `Gi0/1`, internal `Gi0/2 -> Gi0/1` | same port pattern |
| Link intent | one distribution + one access uplink, no redundancy | same |
| VLAN intent | 10/20/30 | 10/20/30 |
| Trunk payload/dependencies | phase 30; depends on local VLAN 10/20/30 creates | same |
| STP policy during foundation | none | none |
| Runtime configuration | 115 cumulative actions, no earlier access chain to replay | 191 cumulative actions: all 115 prior + 76 new |
| Measured root before next stage | Switch5 natural root at priority 32768 | no Floor2 STP root retained |

The switch models, port roles, link shape, VLANs, action types, dependencies,
and final intent are equivalent. The meaningful new conditions are accumulated
replay and a larger naturally elected PVST domain.

## STP control-plane effect

The canonical final policy is PVST for VLANs 10/20/30, Switch8 primary at
priority 24576 and Switch10 secondary at 28672, with edge policy on access
ports. `_completed_stp_sites()` withholds the entire large-site domain until
Floor3 because the final primary Switch8 does not exist before that stage.
Consequently:

- Floor1 and Floor2 compile no large-site `ConfigureSpanningTree` or
  `ConfigureStpEdgePort` actions;
- `_execute_stage()` would apply the control plan only after Voice even if one
  were present;
- the Floor1 measurement proves the actual interim result was natural election
  with leaf Switch5 as root;
- Floor2 introduces and activates two more bridges and two more trunks in that
  unguided domain while reasserting existing VLAN/trunk/access state.

**INFERENCE:** a PVST topology/election transition is the common mechanism that
can account for old and new links together. The trigger is the Floor2 boundary,
not elapsed time. The exact first trigger within that boundary—new bridge/link
activation or old-policy replay—is not retained and must remain unresolved.

## Peer asymmetry

The peer asymmetry is not an identity or normalization defect. Every side has
the intended source link, stable action ID, stable expectation ID, exact
interface, and accepted action. `GigabitEthernet`/`FastEthernet` normalization
matched the correct rows.

Nor were the peer observations simultaneous. Verification is sequential:

| Expectation order | Result | Attempts / elapsed |
| --- | --- | ---: |
| Switch4 `Gi0/2` | failed | 120 / 45,233 ms |
| Switch4 `Gi0/1` | verified | 2 / 782 ms |
| Switch5 `Gi0/1` | verified | 1 / 250 ms |
| Switch6 `Gi0/1` | failed | 98 / 45,468 ms |
| Switch6 `Gi0/2` | verified | 34 / 17,141 ms |
| Switch7 `Gi0/1` | failed | 81 / 45,047 ms |
| Switch10 `Fa0/1` | verified | 1 / 311 ms |
| Switch10 `Fa0/2` | verified | cached current query |
| Switch10 `Gi0/1` | verified | cached current query |

The Switch5 peer was observed after the Switch4-side 45-second window. The
Switch6 downstream side needed another 17 seconds after its upstream side
timed out. Switch10 was read after the three access-switch windows and reused
the same fresh device query for its remaining interfaces. The observations are
authoritative for their own instants but do not prove a stable, simultaneous
one-sided physical condition. This is compatible with real evolving
control-plane state and does not convert the failure to an observer defect.

## Timeout and retained temporal evidence

The artifact retains `attempts`, `elapsed_ms`, final field verdicts, and a
generic final `last_observable_state`. It does not retain the intermediate
`show interfaces trunk` rows, allowed/active/forwarding sets, or STP root and
port-state samples for the Floor2 window.

Therefore:

- Switch4's terminal class is `NO_MATCHING_ROW`, but progression, stable
  absence, or oscillation cannot be distinguished;
- Switch6 and Switch7 terminate `NON_FORWARDING` with allowed and active VLANs,
  but progression, stable non-forwarding, or oscillation cannot be
  distinguished;
- the requested temporal classification for all three is
  `INSUFFICIENT_TEMPORAL_EVIDENCE`;
- `TIMEOUT_TOO_SHORT` is not established. The similar 45.5-second Floor1 phone
  forwarding duration measures a different predicate at a different boundary
  and provides no causal evidence.

The timeout classification is `NOT_ESTABLISHED`, not `TOO_SHORT` and not a
basis for increasing the bound.

## Hypothesis matrix

| Hypothesis | Supporting evidence | Negative evidence / limitation | Status |
| --- | --- | --- | --- |
| H1: cumulative configuration replay disrupts or restarts the converged L2/PVST state | 115/115 old actions are reapplied; old Switch4 trunk moves from verified to absent; old VLAN/trunk/access commands are actually accepted again | replay basis proves payload shape, not runtime continuity; intermediate state absent | **STRONG CANDIDATE**, not isolated |
| H2: adding Floor2 bridges/trunks to unguided natural PVST causes a domain-wide election/convergence transition | intended large-site policy is withheld; Switch5 is measured natural root; two new bridges/trunks are activated; terminal omissions are specifically forwarding | no Floor2 STP root/port samples; cannot show whether the root changed or when | **STRONG CANDIDATE**, coupled with H1 |
| H3: the 45-second timeout is simply too short | all failures hit approximately the bound | no progress samples; elapsed similarity to phone FWD is a different predicate; peer reads are later | **NOT ESTABLISHED** |
| H4: action IDs or expectations were regenerated/stale/miscorrelated | none | all 115 IDs stable; every failed/peer source-link/action/expectation mapping exact | **REFUTED** |
| H5: one link end was omitted or applied nondeterministically | deterministic device order creates temporary asymmetry | all six relevant actions accepted before verification; both ends present | **REFUTED AS ROOT**, ordering may shape transient state |
| H6: topology intent contains redundant or wrong Floor2 links | none | docs, projection, and exact physical delta agree on a nonredundant chain | **REFUTED** |
| H7: parser/interface normalization or stale observation fabricated the contradictions | none for the terminal verdict | fresh, complete, uniquely attributed reads and correct identities; only temporal history is missing | **REFUTED AS FAILURE CAUSE** |
| H8: Floor1/Floor2 control-plane replay caused the regression | none | Floor1 control is RIPv2 only; Floor2 fails before control application | **REFUTED** |
| H9: the Voice correction caused Floor2 | none | Floor2 stops before Voice; Floor1 Voice is the positive control | **REFUTED** |

## Why no production correction is applied offline

A delta-only configuration change would isolate H1. Moving or partially
projecting STP policy would address H2 and the previously confirmed
`EDGE_STP_POLICY_STAGE_GATING_AND_ORDERING` defect. Applying both would likely
remove the symptom while making causal attribution impossible. Applying either
as the canonical correction now would claim more than the retained evidence
supports.

The offline fix standard is therefore not met: the source establishes two
coupled contract defects/candidates, but the artifact cannot show which one is
the first runtime divergence. No timeout increase, sleep, retry, PortFast
workaround, DHCP mutation, raw IOS/JS, topology change, or manual correction is
introduced.

## Minimum evidence and exact next LIVE question

Any next LIVE requires separate authorization. It should be a single-variable
causal run, not another unchanged canonical attempt:

1. keep the same topology, Voice correction, VLANs, action identities, device
   order, and verification contract;
2. at Floor2, apply only the 76 configuration actions not already verified in
   Floor1; do not replay the prior 115;
3. retain round-robin, bounded `show interfaces trunk` samples for all nine
   switch trunk expectations: both switch ends of the four switch-to-switch
   links and Switch10's Router4-facing interface, including every row
   transition and allowed/active/forwarding set;
4. retain fresh, complete `show spanning-tree` root IDs and relevant trunk
   port states immediately before Floor2 physical delta, after physical delta,
   after phases 20 and 30, and at each trunk state transition.

The causal question is:

> With the previously verified 115 Floor1 actions suppressed and every other
> canonical condition unchanged, does Floor2 preserve the Floor1 trunk and
> bring both Floor2 links to forwarding? If yes, cumulative replay receives
> causal credit. If the first divergence occurs before any old action could
> replay, or persists under delta-only application, the retained root/port
> transitions decide the unguided-STP branch.

Until that result exists, `ROOT_CAUSE = STRONG_CANDIDATE`,
`TIMEOUT_CLASSIFICATION = NOT_ESTABLISHED`, and no product correction is
authorized by this offline phase.

## Authorized causal implementation

Authorization was subsequently granted for the exact experiment above.
Commit `ff1be60f0dad31a17fdb44d27834d251e2927732` implements the candidate
without changing the topology, Voice correction, PVST policy, timeout, or
verification standard:

- Floor2 mutates only the 76 action IDs absent from the VERIFIED Floor1 plan.
- The 115 retained Floor1 application results continue to close typed
  dependencies, while all 191 Floor2 expectations are freshly verified.
- Previously signalled Floor1 phone ports are never returned to the data-only
  preparation path; cumulative phone forwarding is still re-observed.
- Trunk verification is bounded and round-robin across devices. Every
  allowed/active/forwarding transition retains a correlated, registered PVST
  root and relevant port-state observation.
- Read-only trunk/PVST snapshots are also retained before and after the
  physical delta and after phases 20 and 30.

The implementation passed the complete offline gate (`3457 passed, 2
skipped`). No LIVE had run when this addendum was written. Therefore this is
still a causal candidate and `ROOT_CAUSE = STRONG_CANDIDATE` remains in force
until the governed runtime result answers the question above.

## First authorized attempt did not reach Floor2

The governed run
`canonical-cp-scale-voice-20260901T010136612890Z-2976329769f9` started from
pushed source `2976329769f9747fa819935f851742b300f81333`, but stopped at the
preceding Floor1 SCCP boundary. Floor1 network forwarding, endpoint addressing,
and all 21 matching Voice DHCP bindings verified. A fresh complete five-page
`show ephone` table exposed 19 registered extensions and omitted `3001` and
`3007` after the full registration window.

Because Floor2 was not reached, this run neither supports nor weakens H1 or H2.
It is not a negative result for delta-only mutation. Commit
`bd8e8b80bd170704e3f403263186f0469a4d0839` retains the raw registration table,
measured phone MACs, and exact ephone batch for the next run and corrects the
observer's boundary label from endpoint address to SCCP while keeping SCCP
mandatory. The Floor2 classification remains `STRONG_CANDIDATE`.

The subsequent raw-diagnostic run
`canonical-cp-scale-voice-20260901T013000402201Z-144ebaa65c5f` also stopped
at Floor1. It confirmed that raw IOS contains registered `ephone-7` and the
parser lost it on an indented `IP:` line, while `ephone-1` was absent from all
33 raw samples despite a unique measured MAC and an exact typed binding block
in the accepted phase-40 payload. Commit `dcb156753bce9c5b4559e5c1dc8db6ac323a8f72`
fixes the parser and isolates every phone binding into one typed, single-dispatch
batch for the next causal run. Floor2 again received no evidence.

That single-action batch experiment was negative:
`canonical-cp-scale-voice-20260901T015150996119Z-4802eb6de95b` emitted 21
one-action binding batches, but `ephone-1` remained absent from all 35 raw
samples while ephones 2-21 registered. Renderer batch size is therefore
refuted as sufficient. Commit `a97e645e479ff72377b8775d3f634e291c507307`
adds one exact registered ephone readback between bindings so state, not time,
authorizes each subsequent mutation. This run also did not reach Floor2.

The first readback-gated run
`canonical-cp-scale-voice-20260901T021410113093Z-6b7a9d37d81b` verified 11
bindings, then failed closed on a pager-incomplete read of the 12th before Voice
signalling. This was an observer stop, not an absent-row result. Commit
`7d694309ac75df2d3605ce35f5f892279d794aa1` permits one additional read-only
query only for the exact qualified pager-failure shape and never replays a
binding. Floor2 again received no evidence.

The qualified observer run
`canonical-cp-scale-voice-20260901T023109308451Z-f1cf32ad7391` then verified
18 bindings and proved ephone 1 absent from a fresh complete five-page table
immediately after its single dispatch. Because hash-ID ordering placed
directory index 1 nineteenth, commit
`6a81a6f47a9b10b5d16de4c89bc87418aad5b7f6` moves only phone-binding order to
semantic directory index for the next causal run. Floor2 still received no
evidence.

The semantic-order run
`canonical-cp-scale-voice-20260901T025406307135Z-ea9b93f0da73` verified
ephones 1-18 and then lost ephone 19, still the nineteenth binding. Index and
hash order are refuted; the failure follows ordinal 19. Commit
`6fd0a0a69fdd5f9a5054f073ed6534e4a4fc7ee8` disables unmanaged CME
auto-registration while preserving every explicit MAC binding for the next
causal run. Floor2 again received no evidence.

The managed-CME run
`canonical-cp-scale-voice-20260901T031054739651Z-ba2b036561c7` again lost the
nineteenth binding, refuting auto-registration as the cause. Commit
`a9115cdd65fe467bf54968b1d86c5e6dbcec1aca` adds one state-authorized
reconciliation only after complete row absence, with exact readback and no
second replay. Floor2 still received no evidence.

The immediate-reconciliation run
`canonical-cp-scale-voice-20260901T032640436029Z-3e5b385cb8f2` still showed
ephone 19 absent after the one accepted reconciliation, refuting immediate
reapply. Commit `e0e4f8848404ea7d48feedb5d52fb0d0c1cfdf8c` completes all
independent initial bindings before reconciling proven absences and keeps every
downstream Voice action closed. Floor2 again received no evidence.

The deferred-frontier run
`canonical-cp-scale-voice-20260901T034510704353Z-ab0a890a6229` still ended
with exactly 20 of 21 binding rows after reconciliation. Commit
`942f35716d04d89e7f59fbb57bf654dd04bc5e58` projects Router4's authoritative
final 51-phone capacity from Floor1 instead of replay-resizing it 21→35→51.
Floor2 again received no evidence.

The 51-capacity run
`canonical-cp-scale-voice-20260901T040356110829Z-0b0f2def9748` produced an
empty ephone table, proving that inferred capacity invalid. Commit
`e83ae0c431c18b5c6e24bcd424a08c5b45d0270d` models the documented capacities
Router4=42, Router0=12, Router3=7 generically. Floor2 again received no evidence.
