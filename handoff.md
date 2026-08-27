# CP-SCALE continuation handoff

## Resume identity and hard boundaries

```text
BRANCH = feature/runtime-ripv2
UPSTREAM = personal/feature/runtime-ripv2
PACKET_TRACER_BUILD = 9.0.1.0858
CURRENT_PUSHED_HEAD = f53f296df070d85d4dfa63f3216bc9c0e027601a
LATEST_GOVERNED_LIVE_HEAD = 2db4c9d54d4f5b5694628f9353ebb523e46aebda
LATEST_CALIBRATION_LIVE_HEAD = d15a5b71dff8b95b56404e550540ca0f3aef018d
ACCESS_PORT_INGRESS_FRAME_IS_TAGGED = NO (measured, both control VLANs)
ACCESS_PORT_CALIBRATION = EXHAUSTED / STRUCTURALLY UNOBSERVABLE for the
    measured plain-host access-ingress representation
PHONE_DHCP_OUT_VLAN_ID = 20 (two governed LIVEs: c1c74fa, 2db4c9d)
SWITCH5_DHCP_IN_VLAN_ID = 20 (same two runs, same instant each run)
PHONE_DHCP_DIRECT_VLAN_VALUE = 20
SWITCH5_DHCP_DIRECT_VLAN_VALUE = 20
PHONE_DHCP_VLAN_IDENTITY = NOT_YET_GLOBALLY_QUALIFIED
PHONE_TO_SWITCH_VLAN_VALUE_PRESERVED = YES
DHCP_FRAME_TPID = -32512 (NOT 33024; field width unmeasured, no 802.1Q claim)
FRAME_VLAN_FIELD_SEMANTICS = DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED
TRUNK_ALLOWED_READBACK = IMPLEMENTED_AND_MEASURED
TRUNK_ACTIVE_READBACK = IMPLEMENTED_AND_MEASURED
TRUNK_FORWARDING_READBACK = IMPLEMENTED_AND_MEASURED
TRUNK_NATIVE_VLAN_READBACK = IMPLEMENTED_AND_MEASURED
TRUNK_CONTROL_742 = POLICY_QUALIFIED / 7-MEMBER UNTAGGED SHAPE / UNOBSERVABLE
TRUNK_CONTROL_743 = FORWARDING EMPTY / 7-MEMBER UNTAGGED SHAPE / UNOBSERVABLE
TRUNK_CONTROL_END_TO_END = NOT_PROVEN
TRUNK_POLICY_READBACK = MEASURED
SINGLE_ALLOWED_NON_NATIVE_TRUNK_POLICY = PROVEN_ON_CONTROL_742
SELECTED_TRUNK_FRAME_VLAN_IDENTITY = UNOBSERVABLE
SELECTED_TRUNK_FRAME_END_TO_END_DHCP_IDENTITY = NOT_ESTABLISHED
PARALLEL_TRUNK_CONTROL_INDEPENDENCE = NOT_ESTABLISHED
DO_NOT_RERUN_SAME_PARALLEL_TRUNK_TOPOLOGY = YES
NEXT_EVIDENCE_SEAM = CROSS_HOP_FRAME_CORRELATION
CROSS_HOP_FRAME_CORRELATION_CAPABILITY = NOT_YET_AUDITED
NEXT_ACTIVE_STEP = OFFLINE CROSS-HOP FRAME CORRELATION AUDIT
FALLBACK_NEXT_CAUSAL_EXPERIMENT = POSITIVE_DISPOSABLE_VOICE_AB
VLAN_SCOPED_STP_INTERPRETATION = STILL_INFERENCE
READ_GETTER_FIX = 8d594994c244e08a52c7945b64a8c5b7ae3642fa (pushed)
WORLD_B_OBSERVATION_FIX = 6eb0d8e4480a22353b8a9dc9cc47305ebdd0c039 (pushed)
ROUTING_CORE = GOVERNED VERIFIED (fresh run at e09f606)
ROUTER4_SWITCH10 = GOVERNED VERIFIED; forwarding converged at 30.983 seconds
FLOOR1_PHYSICAL = REACHED; the stage later failed in voice verification
FLOOR1_DHCP_CLIENT = 21/21 Vlan20 present, readable, TRUE
FLOOR1_ADDRESSING = 0/21 addressed
FLOOR1 = NOT VERIFIED
WORLD_A = REFUTED
WORLD_B_FORWARDING = REFUTED; all five trunk endpoints VERIFIED
WORLD_B_DHCP_BINDINGS = latest fresh at 1d2c186: DATA 23, VOICE 0, CCTV 0
DHCP_EXCHANGE_STATISTICS = checkpointed at 994e2ea; channel REFUTED at LIVE
PT_SCOPED_STATISTICS_SUPPORT = REFUTED BY FRESH OBSERVATION
POST_FAILURE_SIMULATION_DIAGNOSTIC = prior 40-step capture at 1d2c186; window insufficient
VOICE_REALTIME_CONTINUITY = VERIFIED at 1d2c186 (both edges Realtime)
ACCESS_PORT_DATA_VLAN = VERIFIED by direct PT port getter
ACCESS_PORT_VOICE_VLAN = VERIFIED 21/21 by fresh direct PT port getter
DHCP_FRAME_IDENTITY_THIS_RUN = OBSERVED_BY_PT (PT's own text named Discover)
DHCP_EVENT_LIST_VISIBILITY = OBSERVED
PERMANENT_TYPE7_MAPPING = NOT_IMPLEMENTED
STP_BLOCKING_IN_SIMULATION = OBSERVED (Switch5 phone ports, bounded capture)
STP_BLOCKING_IN_REALTIME = UNOBSERVABLE (CASE D at 540c746)
SOURCE_DEFECT_FOUND = YES
SOURCE_DEFECT = EDGE_STP_POLICY_STAGE_GATING_AND_ORDERING
PORTFAST_AS_VOICE_ROOT_CAUSE = NOT_CONFIRMED
VOICE_ROOT_CAUSE = NOT_YET_CONFIRMED
PHONE_EDGE_PORTFAST_INTENT = YES
PHONE_EDGE_PORTFAST_COMPILED = NO at FLOOR1 (YES at FLOOR3+)
PHONE_EDGE_PORTFAST_APPLIED = NO
SHOW_SPANNING_TREE_PAGER = QUALIFIED by fresh 2f2055c measurement
VLAN10_PHONE_PORTS_BEFORE_VOICE = 21/21 Desg FWD at 540c746
VLAN20_PHONE_PORT_ROWS = ABSENT in a COMPLETE capture at 540c746
STP_REALTIME_LOGICAL_ATTEMPTS = 2 (bounded, retry only on proven-safe terminal)
CP_SCALE_STATUS = OPEN / NOT VERIFIED
E10 = FORBIDDEN
```

Offline baseline at pushed HEAD `1d2c186`: **2787 passed / 0 failed / 4 warnings**
with the checkout-local `.venv`. The simulation-time patch below adds 34 focused
contracts and runs at **2821 passed / 0 failed / 4 warnings**; its selected
affected regression is **414 passed / 0 failed**. The prior governed run cleaned
every owned device and independently re-observed the empty semantic workspace
twice. Packet Tracer is open; its workspace is empty.

Everything through the phone-facing voice-VLAN readback is checkpointed in this
HEAD and has produced its LIVE reading. The simulation-time bounded diagnostic
described below is the current uncommitted pre-LIVE change; checkpoint it before
the next governed run.

## Decisive powered-phone measurement -- World A refuted

FACT: the read defect was fixed first and alone in `8d594994`: the voice SVI is
read with `isDhcpClientOn`, while the device-level absence remains `None`.

FACT: the next governed run mechanically established build `9.0.1.0858`, the
checkout-local production namespace, authenticated fresh HTTP, two complete
zero-device semantic inventories, and `safe_for_disposable_mutation=True`.

FACT: on the 21 powered Cisco 7960 phones in real Floor 1:

```text
VOICE_INTERFACE_PRESENT = 21
VOICE_INTERFACE_DHCP_READABLE = 21
VOICE_INTERFACE_DHCP_TRUE = 21
VOICE_INTERFACE_DHCP_FALSE = 0
VOICE_INTERFACE_DHCP_UNOBSERVABLE = 0
VOICE_INTERFACE_ADDRESS_CHANNEL = 21
VOICE_INTERFACE_ADDRESSED = 0
VOICE_DEVICE_DHCP = unreadable:21
```

FACT: the stage then observed all 21 phones without an IPv4 address. It failed
after the configured 180-second voice convergence window because 19 complete
`show ephone` rows remained `UNREGISTERED`; extensions 3001 and 3007 were absent
from the complete five-page table and therefore remained `UNOBSERVABLE`.

FACT: the runner exited by its own governed failure path. Cleanup was VERIFIED;
both fresh post-cleanup inventories were observed and contained zero semantic
devices.

CONCLUSION: `setDhcpClientFlag(true)` is forbidden on this evidence. No phone
acquisition action was added. World A is refuted and World B is primary.

## World B -- typed VLAN traversal observation

The independent source audit confirmed:

* FACT: `TrunkStatusRow` and `parse_show_interfaces_trunk` discarded the allowed,
  active, and STP-forwarding VLAN sections.
* FACT: `_verify_trunk` hard-coded `allowed_vlans=UNOBSERVABLE` while declaring
  the trunk verified.
* FACT: `SHOW_INTERFACES_TRUNK` was registered but not pagination-qualified.
* INCOMPLETE: no retained raw transcript proved the historical claim that those
  sections paged away on every relevant switch. The source risk was real; the
  universal LIVE claim was not accepted.

The minimum typed implementation now:

* preserves `None` (section absent), `()` (IOS explicitly said `none`), and a
  populated VLAN tuple as distinct states;
* captures the registered query through its bounded pager until a prompt;
* independently verifies the expected VLAN set in `allowed`, `active`, and
  `forwarding/not pruned` for each configured trunk;
* fails on an observed omission and remains `UNOBSERVABLE` on absent/incomplete
  evidence;
* records named per-device/per-interface traversal evidence in the governed
  runner.

FAIL-FIRST: four targeted regressions failed against the old code (two missing
row fields, one false VERIFIED result, one truncated pager result). Focused:
12 passed. Affected files: 101 passed. Full: 2718 passed / 0 failed.

Topology worth remembering: the 23 PCs that lease are all on **Switch4**; all 21
phones are on **Switch5**, one hop further out, and everything else on Switch5 is
static or not addressable, so that hop has never been proven to forward DHCP.

The next governed Floor-1 journal will name these five exact trunk endpoints,
each expecting VLANs 10/20/30:

```text
Switch10 GigabitEthernet0/1 <-> Router4 FastEthernet0/0
Switch10 FastEthernet0/1    <-> Switch4 GigabitEthernet0/1
Switch4  GigabitEthernet0/2 <-> Switch5 GigabitEthernet0/1
```

FACT, before the current change: `show ip dhcp binding` had **no registered
query**. `OperationalQueryId` carried `SHOW_IP_DHCP_SNOOPING` only, which is
switch security, not the server binding table. The fresh complete path evidence
below met the gate for adding the server-side observation.

## Fresh World-B LIVE checkpoint -- 8 seconds was not a forwarding lifecycle

FACT: from clean pushed HEAD `6eb0d8e`, the next governed run re-established the
checkout-local production namespace, a single import namespace, authenticated
fresh HTTP, a blank semantic workspace, and `safe_for_disposable_mutation`.
Routing core passed and was checkpointed/pushed at `43eba72`.

FACT: after resuming, `router4-switch10` exited through its own governed failure
path. On `Switch10 GigabitEthernet0/1` toward Router4, 25 fresh complete typed
reads over the configured 8-second budget established VLANs 10/20/30 as
`allowed=VERIFIED` and `active=VERIFIED`, while
`forwarding_vlans=FAILED` with `forwarding omitted 10,20,30` on the last read.

FACT: cleanup was VERIFIED and two fresh post-cleanup observations contained
zero semantic devices. The runner was not interrupted.

INFERENCE: this signature is consistent with a trunk observed during STP
transition; it does not yet prove either eventual forwarding or a persistent
path defect. The former generic 8-second default was demonstrably too short to
decide between those states.

FAIL-FIRST: the default-budget regression observed `8.0` where the new contract
requires `45.0`; the failed-stage journal regression found no named trunk
projection even though the full typed result already existed. Both failed
before implementation and now pass. The runtime keeps the same fail-closed
verdict after a bounded 45 seconds, and the runner writes the named projection
before contradiction handling. Focused: 9 passed. Affected: 93 passed. Full:
2720 passed / 0 failed.

## Fresh e09f606 LIVE -- complete VLAN20 path, still zero phone addresses

FACT: the governed run started from clean pushed `e09f606`, exact local
production namespace, build `9.0.1.0858`, authenticated fresh HTTP, blank
semantic workspace and `safe_for_disposable_mutation`. The runtime checkpoint
stayed under ignored `data/`; the worktree remained clean and no progress commit
was needed.

FACT: `router4-switch10` VERIFIED VLANs 10/20/30 as allowed, active and
forwarding on `Switch10 GigabitEthernet0/1` after 90 reads / 30.983 seconds.
That directly confirms the former 8-second result was a transition, not a
persistent forwarding omission.

FACT: Floor 1 then VERIFIED all five trunk endpoints and all three VLAN fields:

```text
Switch4  Gi0/2  89 reads / 33.250 s  VERIFIED
Switch4  Gi0/1  cache/current          VERIFIED
Switch5  Gi0/1  91 reads / 34.734 s  VERIFIED
Switch10 Fa0/1   1 read  /  0.108 s  VERIFIED
Switch10 Gi0/1  cache/current          VERIFIED
```

FACT: all 25 readable E5 endpoint observations verified their IPv4/netmask
fields, while all 21 phones again exposed `Vlan20`, an address channel and
`isDhcpClientOn()==true`, but zero held an address. Every one of the 47 E7 voice
actions was accepted. The complete CME observation remained 19 UNREGISTERED / 2
UNOBSERVABLE and the stage failed after the full 180-second window.

FACT: HTTP was connected with `last_poll_ago=0.0`, zero unauthenticated requests
and no resume-gate errors before both post-core stages. The runner exited on its
own voice contradiction and cleanup was VERIFIED twice with zero semantic
devices.

CONCLUSION: the complete Router4 -> Switch10 -> Switch4 -> Switch5 VLAN20 path
is not the missing evidence. World-B forwarding is refuted. The next strongest
observation is the Router4 server binding table, exactly as the original gate
specified.

The additive implementation registers privileged `SHOW_IP_DHCP_BINDING`, uses
the existing bounded pager, parses only the stable IPv4 first column, requires a
fresh complete source-attributed table with at least one typed row, and projects
counts for every configured pool. A voice-pool count of zero is emitted only
when the same complete table successfully exposes other bindings; no rows,
incomplete output, rejection or wrong device identity yields `None` /
UNOBSERVABLE. `VerificationKind.DHCP_POOL` is untouched.

FAIL-FIRST: the query/parser regression failed because the query was not
registered; the runner regressions failed because no additive evidence existed
and a voice failure discarded any such observation. Focused: 11 passed.
Affected: 199 passed. Full: 2725 passed / 0 failed.

## Pre-LIVE checkpoint self-dirty defect -- fresh and independently reproduced

FACT: `8b4cdd4` is the immutable pushed pre-LIVE checkpoint for the 45-second
trunk observation. A fresh governed run reached routing core VERIFIED on that
exact HEAD with authenticated HTTP and wrote its checkpoint evidence.

FACT: the runner then modified tracked
`docs/reference/cp-scale/live_canonical_checkpoint.json` itself and its own
resume gate immediately refused to advance because the worktree was dirty. The
run exited rather than bypassing the gate. Cleanup was VERIFIED; both fresh
post-cleanup inventories contained zero semantic devices.

FACT: this is a runner lifecycle defect exposed by the required no-progress-
commit discipline. The complete failure evidence remains under ignored
`data/cp-scale/live-canonical-progress.json`; the accidentally changed tracked
summary was restored byte-for-byte to the HEAD version.

FAIL-FIRST: `test_runtime_checkpoint_summary_cannot_dirty_the_governed_worktree`
failed because the runtime summary was neither colocated with ignored evidence
nor gitignored. The minimum fix makes ignored `data/cp-scale/` the default
checkpoint destination during every in-flight stage, while the tracked
reference summary is published only after terminal
`CP_SCALE_GOVERNED_VERIFIED` retention. Focused/affected: 21 passed. Full:
2722 passed / 0 failed.

## Scoped DHCP exchange statistics -- implemented, PT support UNKNOWN

The Floor-1 binding reading at `4b9fe11` localized the failure BEFORE server-side
voice lease allocation: Router4's table was fresh, complete, two-page and uniquely
attributed, with 23 DATA bindings, 0 in `172.16.20.0/24` and 0 CCTV. That says the
voice lease was never allocated. It does not say which step of the exchange is
missing, and the binding table cannot say: an absent row is the same absence
whether the DISCOVER never arrived or the ACK never left.

`SHOW_IP_DHCP_SERVER_STATISTICS_INTERFACE` is registered additively for that one
question. It is read-only, privileged EXEC, pagination-qualified, and goes through
the same `ControlledIosExecutor` path as every other registered query -- same
atomic pager guard, same freshness window, same echo classification, same unique
device attribution. `SHOW_IP_DHCP_BINDING` and the `DHCP_POOL` ceiling are
untouched.

**Packet Tracer 9.0.1.0858 support for the interface-scoped form is UNKNOWN.**
Cisco documents it on some IOS trains; that is not evidence about this build. The
runtime read fails closed on invalid input, an unsupported command, incomplete or
paged-incomplete output, ambiguous provenance, a malformed layout and any missing
decisive counter. There is no fallback to the global form: the 23 data clients
acquire inside the very window being measured, so a global answer cannot stand in
for a scoped one.

That confound is also why each observation point reads TWO scopes, not one. A
build that accepted `FastEthernet0/0.20` and answered with the global table would
be indistinguishable from a scoped answer while carrying every data client. The
control scope -- the next pool-backed subinterface on the same server, resolved to
`FastEthernet0/0.30` (CCTV) for Router4 -- makes the difference observable:

* control and voice deltas differ -> the interface argument scoped the read;
* control delta is all zeros -> no table, scoped or global, could have read zero
  across a window that carried the data clients;
* control and voice deltas are identical and non-zero -> `SCOPE_UNPROVEN`, and no
  fork is named.

`baseline` is captured at the governed `router4-switch10` checkpoint, where
Router4 already owns `FastEthernet0/0.20` and its voice pool but no Floor-1 client
exists yet. `post` is captured after the voice acquisition window and BEFORE the
stage raises, so `CanonicalLiveFailure.stage_evidence` carries it out with the
binding evidence. A delta needs both points usable, fresh, complete, on the same
device and scope; a counter that decreased is invalid for interpretation, never
negative traffic. Nothing fabricates a zero delta from missing evidence.

The fork it can support is bounded and non-causal: `A_NO_DISCOVER`,
`B_DISCOVER_WITHOUT_OFFER`, `C_OFFER_WITHOUT_REQUEST`, `D_REQUEST_WITHOUT_ACK`,
`E_ACK_WITHOUT_BINDING`, plus `ACK_OBSERVED_BINDING_UNOBSERVABLE`,
`UNCLASSIFIED_COUNTER_PATTERN`, `SCOPE_UNPROVEN` and `UNOBSERVABLE`. None of these
claims a phone did not transmit, a switch dropped a broadcast, or a server
rejected a client. Shrinking the fork is the whole objective; proving a cause is
not.

## Scoped DHCP server statistics -- channel REFUTED at LIVE

The governed run from `994e2ea` asked the support question before interpreting
anything, and Packet Tracer answered it. All four reads -- voice
`FastEthernet0/0.20` and control `FastEthernet0/0.30`, at the router4-switch10
baseline and the Floor-1 post point -- returned the same rejection:

```text
show ip dhcp server statistics FastEthernet0/0.20
                     ^
% Invalid input detected at '^' marker.
```

The caret sits at column 21, inside the `statistics` token, with
`show ip dhcp server s` accepted before it. The interface argument was never the
obstacle: this build does not implement the command in any form, scoped or
global. Cisco documents the scoped variant on some IOS trains; that is now
confirmed to say nothing about 9.0.1.0858.

The fail-closed path held on first contact. Every read was `executed`, fresh,
`output_complete`, one page, provenance `confirmed_unique` by session transcript
continuity -- a healthy attributed capture OF A REJECTION -- and the typed layer
still returned `usable=False`, `counters=None`. `% Invalid input` never became a
server that saw zero DHCP. `fork` stayed `UNOBSERVABLE` and no DORA step was
named. Do not re-attempt this channel; it is measured, not uncertain.

The same run independently reproduced every prior fact at the new HEAD: routing
core VERIFIED (3/3), router4-switch10 VERIFIED (4/4), five Floor-1 trunk
endpoints VERIFIED, Router4 bindings fresh/complete/two-page with DATA 23,
VOICE 0, CCTV 0, and 21 phones with Vlan20 present, channel readable, interface
DHCP enabled, zero addressed, 19 FAILED / 2 UNOBSERVABLE.

## Post-failure simulation capture -- implemented, LIVE pending

The binding table localizes the failure before server-side voice allocation and
cannot go further: an absent row is the same absence whether the DISCOVER never
arrived or the ACK never left. With the server-counter channel refuted, the
remaining observable is Packet Tracer's simulation event list.

Three ceilings shape what it can ever answer, and all three are measured, not
assumed:

* **Simulation mode changes execution semantics.** Packets stop progressing on
  their own and must be stepped. So this can never observe the original realtime
  voice acquisition -- entering Simulation during that window would replace the
  tested condition, not watch it. The capture is named
  `POST_FAILURE_SIMULATION_DIAGNOSTIC` and runs only after the voice stage has
  already failed and been read back, at the last moment the devices still exist.
* **There is no event-filter surface.** PT's "Edit Filters" decides which PDU
  types enter the event list and no IPC primitive for it exists in this repo.
  An empty phone capture is therefore indistinguishable from DHCP being filtered
  out, and no absence may be read from one.
* **Floor 1 is noisy against a 200-frame bound.** Device filtering happens
  server-side, but `total_in_event_list` is GLOBAL and can never stand in for a
  filtered match count.

So this first slice classifies NOTHING. `dhcp_trace_identity` and
`control_dhcp_visibility` are both fixed at `UNOBSERVABLE`, and a regression
forbids the strings that a classifier would need. The first LIVE after this
checkpoint is calibration: its product is the raw capture -- every hop with its
raw `getUserTrafficType()` integer beside the label, both simulation times, and
the FULL per-layer decision log -- so the representation can be discovered from
retained evidence instead of paid for with another governed run.

The mode is owned explicitly: a pure `read_simulation_state()` establishes the
original, Simulation is entered only if it was not already active, and the mode
is given back in a `finally` verified by ANOTHER pure read. A restoration that
cannot be verified is recorded on its own key and never overwrites, hides or
becomes the Floor-1 failure the stage is already carrying.

## Two windows, and the guard that keeps them apart

The same pure read now also protects the window it must never touch.

`NORMAL_WINDOW` is Realtime only: it is the authoritative voice acquisition and
the only thing 0/21 is a statement about. `POST_FAILURE_SIMULATION_DIAGNOSTIC` is
Simulation, bounded stepping, diagnostic, never configuration verification. A
180-second convergence that elapsed while Simulation was active did not measure
what the same wall clock measures in Realtime, so `voice_realtime_continuity`
takes a pure observation immediately before `VoiceApplicator.apply` and again
immediately after the convergence/readback window, and retains both whole.

The policy is fail-closed in both directions, and in neither does the runner
normalize the mode behind the operator:

* Simulation, unobservable or malformed BEFORE -> the authoritative acquisition
  is never attempted and the stage fails with the evidence it has.
* Simulation or unobservable AFTER -> the acquisition already ran and its
  evidence is kept, but `verified` stays false and nothing downstream reads
  0/21 as an authoritative DHCP failure. Bindings, statistics and the
  diagnostic are all skipped.
* The post-failure diagnostic refuses outright when no authoritative Realtime
  failure was established: `status = NOT_APPLICABLE`, and it does not open a
  Simulation window to produce evidence about nothing.

What two reads prove is exactly what the evidence claims: both BOUNDARIES were
Realtime. They do not prove nobody toggled the mode between them, and the
`proves` field says so in the journal.

## Simulation capture LIVE at b989eb0 -- mechanism proven, window too short

Both windows behaved exactly as designed. `voice_realtime_continuity` came back
`verified` with both edges `simulation_mode=false` and `frames=0`, and PT's own
sim clock advanced 323724 -> 487691 across the ~180 s wait, so the 0/21 result is
attributable to Realtime. Everything else reproduced: 21/21 Vlan20 present and
readable with DHCP enabled, 0/21 addressed, 19 FAILED / 2 UNOBSERVABLE, Router4
DATA 23 / VOICE 0 / CCTV 0.

The diagnostic then entered Simulation from an observed Realtime original, reset,
stepped its committed budget of 40, and gave the mode back -- restoration verified
by a pure read, cleanup verified twice at 0 devices / 0 links.

What it captured, and its ceiling:

* 40 steps produced 171 global frames, so stepping DOES generate and retain
  events. PHONE-02 and PC-01 returned 2 hops each, `limit_reached=false` on both,
  so neither capture was truncated.
* Every hop was raw traffic type 11 with destination `SSTP Multicast Address`,
  status `dropped`, at sim_times exactly 2000 apart -- an STP hello cadence. Type
  11 is recorded as `type11` and was NOT added to `TRAFFIC_TYPES`.
* **`getSourceString()` returned EMPTY and `getDestinationString()` returned a
  human-readable protocol name, not an IP.** The hypothesised
  `0.0.0.0 -> 255.255.255.255` discriminator is not a general shape on this
  build, so refusing to encode that classifier was load-bearing.
* The captured window spanned only 4953 sim units (~5 s), and no positive DHCP
  control was established, so **no absence may be read from it**. Not "PHONE-02
  does not send DHCP", not "DHCP is filtered", not "Switch5 drops it".

The budget behaved exactly as committed; it simply bought ~5 s. That observation
is the reason the next reviewed change below bounds the new window by elapsed
simulation time rather than treating a step count as elapsed time.

## Phone-facing last-mile LIVE at 1d2c186 -- access hypothesis closed

Fresh direct evidence from the same attributable physical switch-port object
closed the access edge. For PHONE-02 on Switch5 `FastEthernet0/2`,
`getAccessVlan()` observed 10 against expected 10 and `getVoipVlanId()` observed
20 against expected 20; both field verdicts were VERIFIED. Across all 21
phone-facing ports, data VERIFIED = 21, voice VERIFIED = 21, voice contradicted
= 0, and voice unobservable = 0. Do not reopen this configuration hypothesis
without new contradictory evidence.

In compact form: PHONE-02 data VLAN 10 VERIFIED; voice VLAN 20 VERIFIED.

The authoritative Realtime window independently remained VERIFIED at both
boundaries. All 21 phones exposed Vlan20 with a readable address channel and
DHCP enabled, but 0/21 held an IPv4 address after 180 seconds. Router4 retained
DATA = 23, VOICE = 0, CCTV = 0 bindings. The prior 40-step Simulation capture
again spanned only about 5,000 sim-time units (159 global frames) and established
no DHCP identity; it is operational but insufficient for a retry-lifecycle
investigation.

## Simulation-time bounded DHCP diagnostic -- implemented, LIVE observed

The pre-edit positive-control audit found no safe existing post-failure control.
Canonical endpoint DHCP application calls `configurePcIp(..., true, ...)`, and
the capability probe additionally creates/links/deletes a disposable endpoint
and configures a special router pool. Those are governed in their own contexts
but mutate endpoint, topology or configuration state, so they are not a safe
diagnostic control in the canonical failure window.

```text
POSITIVE_CONTROL_CAPABILITY = UNSAFE_OR_MUTATING
POSITIVE_CONTROL_IMPLEMENTED = NO
CONTROL_DHCP_VISIBILITY = UNOBSERVABLE
TARGET_SIM_TIME_SPAN = 60000
STEP_BATCH_SIZE = 10
HARD_MAX_STEPS = 600
HARD_WALL_CLOCK_SECONDS = 120
GLOBAL_EVENT_LIST_CEILING = 2500
SIM_TIME_STALL_BATCH_LIMIT = 3
TRACE_LIMIT_PER_SCOPE = 200
```

After entering Simulation and resetting, one pure state read establishes the
simulation-time origin. The runner advances in fixed 10-step batches and follows
every successful batch with another pure state read. It retains every step and
state observation, cumulative steps, sim-time span, global frame count, wall
time and consecutive stalls. It terminates explicitly on target span, hard step
count, wall clock, global event ceiling, unobservable state, non-monotonic time,
three repeated stalled batches, or a refused step. Every exit remains
non-negative evidence: positive observations survive; absence is never inferred.

At the boundary it reads four independently device-filtered raw scopes at the
runtime's hard maximum of 200 each: PHONE-02, Switch5, Router4 and passive PC-01.
Each hop keeps raw traffic identity, source/destination, timing, ports, status and
the ordered full PT decision list. `TRAFFIC_TYPES` remains exactly ICMP/ARP;
type 11 is not named DHCP and there is still no DHCP classifier. No endpoint or
topology mutator was added. Cheap post-restoration phone-address and Router4
voice-binding reads are explicitly deferred because the Simulation runtime has
no typed path for either and adding voice/IOS orchestration would broaden this
diagnostic.

## Phone-edge STP in Realtime -- CASE D, bounded retry pending LIVE

The bounded Simulation diagnostic ran and changed the fork. Packet Tracer named
PHONE-02's frames itself -- "DHCP client constructs a Discover packet" -- so DHCP
is demonstrably visible in the event list and a separate PC positive control is
no longer required to establish that. `TRAFFIC_TYPES` is still exactly ICMP/ARP:
the frames were identified BY PT in one run, which is not the same thing as a
permanent typed mapping, and none was added.

The same capture showed every retained Switch5 entry reporting the ingress phone
port blocked by STP. That capture is taken after `resetSimulation()`, so it
cannot say what the port was doing during the authoritative Realtime window. Two
readings remain open and the packet trace cannot choose between them: the same
operational condition existed in Realtime, or entering Simulation produced it.

```text
SOURCE_DEFECT = EDGE_STP_POLICY_STAGE_GATING_AND_ORDERING
LEG_1 = _completed_stp_sites() admits LARGE only at FLOOR3, so the FLOOR1
        projection compiles stp_domains=[] and ZERO ConfigureStpEdgePort
        actions -- while Switch5 already carries 21 voice-VLAN access ports.
LEG_2 = _execute_stage applies the control plane AFTER _stage_voice, so edge
        policy would not be effective before DHCP acquisition even where it
        does compile.
MEASURED = FLOOR1: SW5 access ports 25, edge actions 0, stage edge actions 0
           FLOOR3: SW5 edge actions 25 (portfast/bpduguard True, phase 30)
```

The defect is confirmed at the compilation layer and is NOT being fixed in this
patch. Fixing it first would change the condition before measuring it and
destroy the causal experiment. This patch only measures.

Two read-only observations now bracket the voice window from inside it:
`stp_realtime_before_voice` after the proven Realtime BEFORE boundary and
immediately before `_stage_voice`, and `stp_realtime_after_voice` immediately
after it returns -- taken before the closing boundary read, so the same two PURE
mode observations bracket the measurement, and long before Simulation is entered
at all.

The phone-facing set is DERIVED, never named: each `PhoneAssignment` resolves
through `access_configuration_action_id` to its typed `ConfigureAccessPort`,
yielding device, interface and voice VLAN from the plan. An assignment whose
action is not a typed access port -- a trunk, or one that no longer exists -- is
recorded as excluded rather than silently dropped. On the real canonical Floor 1
this lands on exactly Switch5 `Fa0/1-21` / VLAN 20 without those names appearing
anywhere in the implementation.

`OperationalQueryId.SHOW_SPANNING_TREE` and `parse_show_spanning_tree` are reused
unchanged; no new parser and no raw IOS. The query stays pagination-UNQUALIFIED,
because the only retained exact-build capture is a one-VLAN/one-port lab output
that proves nothing about a 3560 with three VLANs and 25 ports. This LIVE is what
establishes whether it needs qualification.

Per port the run retains device, interface, `vlan_id`, role, state, cost,
`priority_number` and `link_type`, plus the read's own `executed`, freshness,
completeness, pager marks and device attribution. Only `FWD` is FORWARDING and
only `BLK` is BLOCKING; every other REAL state is kept as OTHER_OBSERVED with its
token intact. Anything that weakens the evidence -- not executed, stale, IOS
rejection, pager truncation, incomplete, unattributable device, missing VLAN 20
instance, missing interface row, malformed state -- is UNOBSERVABLE. A missing row
is never BLOCKING and a truncated table is never absence. Collecting this
evidence can never itself fail a governed stage.

### First governed run at 2f2055c -- CASE C, and the pager is now measured

The run reached Floor 1, failed in voice as expected, and cleaned up: 74/74
mutations applied, `cleanup.verified = true`, nothing retained. Both Realtime
boundary reads were observed in Realtime (`verified: True`), so the placement
worked and the two STP reads really were inside the authoritative window.

```text
STP_REALTIME_BEFORE_VOICE = 21/21 UNOBSERVABLE (PAGER_TRUNCATED)
STP_REALTIME_AFTER_VOICE  = 21/21 UNOBSERVABLE (PAGER_TRUNCATED)
DEVICE_ATTRIBUTION = Switch5 / confirmed_unique / confirmed
QUERY = executed True, fresh True, complete False, pages 1, not_qualified
VLAN_INSTANCES_CAPTURED = [1]
VOICE = 21 phones staged; ephone rows UNREGISTERED before timeout
DHCP_BINDINGS = Router4 readable; data 23, voice 0, cctv 0
```

The fail-closed contract held exactly: zero FORWARDING, zero BLOCKING, and a
truncated table was never read as absence.

That truncation is the evidence the read surface was missing. Page one of
`show spanning-tree` on Switch5 ends mid-`VLAN0010` header, so the parser saw
only `VLAN0001`, whose single row is the `Gi0/1` uplink; `VLAN0020` with all 21
phone-facing rows lay entirely beyond the pager. The query cannot be narrowed --
PT 9.0.1 rejects `terminal length 0`, and `show spanning-tree vlan 20 interface
...` has no established support in this build, so reaching for it would be
inventing a command shape to dodge a pager. `SHOW_SPANNING_TREE` is therefore
pagination-qualified on that measurement, with the same hard bounds as every
other qualified query and the same fail-closed ceiling on an incomplete capture.
Both page fixtures are retained in `tests/test_ios_terminal.py`.

### Rerun at 540c746 -- CASE D, and what a complete capture actually showed

The pager qualification worked. The BEFORE read completed in three pages and
carried all four instances; the AFTER read lost its continuation and was
correctly held UNOBSERVABLE. Cleanup verified 74/74, nothing retained.

```text
BEFORE = COMPLETE (3 pages, continuation completed, confirmed_unique)
  VLAN1   Gi0/1
  VLAN10  Fa0/1..Fa0/21 all Desg FWD, + Gi0/1
  VLAN20  Gi0/1 ONLY
  VLAN30  Fa0/22 Fa0/23 Fa0/24 Gi0/2 Gi0/1
AFTER  = INCOMPLETE (1 page, continuation failed, executed True)
CASE   = CASE_D_REALTIME_STP_REPRESENTATION_UNRESOLVED
```

Two facts follow and neither is the one the fork needed. The phone-facing ports
are NOT globally STP-blocked before voice -- all 21 are `Desg FWD` in the data
VLAN. And VLAN 20 lists only the trunk uplink, in a capture that is complete, so
that absence is a property of the table, not of the pager.

Absent rows are not BLOCKING. Two readings remain: PT may list a port only under
its access VLAN, or VLAN 20 membership may appear only after the phone signals.
The AFTER read is exactly what separates them, and it is the one that was lost.

Do not read VLAN 30's access ports as evidence for the first: those ports' access
VLAN *is* 30, so they only confirm that a port appears under its access VLAN.
Real Cisco may expose a voice port under both instances; Packet Tracer is the
backend under qualification and fresh PT evidence wins.

### Bounded retry -- implemented, LIVE pending

One logical STP observation may now execute at most `_STP_MAX_LOGICAL_ATTEMPTS`
= 2 registered queries. The second is a NEW `ios.execute`, never a continuation
of the old transcript, and the runner never sends pager keys itself --
`ControlledIosExecutor` keeps owning pagination mechanics. The generic executor
is unchanged and the other six qualified queries are untouched.

Retry safety is derived from the existing result, not assumed. `executed` is the
discriminator: after an incomplete qualified capture the executor cancels the
pager, and the only path reaching `executed=True` is a CONFIRMED cancellation --
an unconfirmed one quarantines the device and returns `executed=False`. So a
retry is permitted only when the prior result was executed, with uncorrupted
dispatch, `confirmed_unique` attribution, no IOS rejection, and
`pager_continuation == "failed"`. Anything else refuses and stays UNOBSERVABLE:
TERMINAL_NOT_CONFIRMED_SAFE, DISPATCH_CORRUPTED, DEVICE_IDENTITY_NOT_CONFIRMED,
IOS_REJECTED, NOT_A_QUALIFIED_PAGER_FAILURE. Nothing in the executor was
weakened to make the retry possible; if the terminal is still bad its own atomic
guard refuses the dispatch and the second attempt is another `executed=False`.

Both attempts are retained with their own raw quality metadata and outputs are
never merged -- two commands are two observations. The first complete, fresh,
uniquely-attributed attempt is selected and is the only one the claimed state
comes from. BEFORE and AFTER use the same helper; AFTER is not special-cased.

Expected decision after the next LIVE: D1 phone rows present and FORWARDING ->
Simulation/Realtime divergence, and PortFast is still not a DHCP fix; D2 a
required row BLOCKING -> the staging defect becomes a strong causal candidate and
the two-leg autofix proceeds; D3 complete VLAN 20 still without phone rows ->
the query has proven its representation, not the port state, and a different
observation surface is required; D4 both attempts incomplete -> UNOBSERVABLE.

## Historical last-L2 defect -- why direct voice-VLAN readback was required

Before spending another Simulation run, the access edge was audited, and it had a
real hole. `ConfigureAccessPort` carries `data_vlan_id` AND `voice_vlan_id` for a
phone-facing port, but only the data one ever reached evidence:

* the compiler built `expected = {interface, vlan_id: data_vlan_id}` and dropped
  `voice_vlan_id` entirely, so nothing ever CLAIMED the voice VLAN;
* `_verify_access_port` read the port object's `getAccessVlan()` and nothing else.

The Floor-1 run at b989eb0 proves the consequence exactly. For Switch5
`FastEthernet0/2` -- PHONE-02's port -- the plan said `data_vlan_id=10`,
`voice_vlan_id=20`; the expectation said `{'interface': 'FastEthernet0/2',
'vlan_id': 10}`; the application said `applied` with `disposition=unknown`; and
the verification came back `verified` on `device_identity`, `interface`,
`switchport_mode`, `vlan_id`. All 49 access-port verifications had exactly those
four fields. **VLAN 20 on the phone port was APPLIED and never observed -- neither
verified nor contradicted.**

The fix uses a getter this repository already measured on this exact build:
`getVoipVlanId` reports `function` on a switch's physical ports in PT 9.0.1.0858
and `undefined` on a `Vlan1` SVI or an AP port (retained evidence in
`data/cp-scale/ap-addressability/result.json`). It rides the SAME JS call that
already reads `getAccessVlan()`, so covering all 21 phone ports costs zero extra
round-trips, and it is only probed when the expectation claims a voice VLAN --
the 28 data-only ports keep their exact previous shape.

Each field is decided on its own evidence. A readable value that differs is
CONTRADICTED; an absent or unreadable one is UNOBSERVABLE and never contradicts;
`vlan_id` VERIFIED with `voice_vlan_id` UNOBSERVABLE is a valid, narrower result.
A readable numeric mismatch travels in the message; unavailable and malformed
values are reported as bounded typed evidence rather than arbitrary object
dumps, so the result remains diagnosable without paying for another LIVE.

**Expect a different failure shape.** A FAILED verification is a blocking
contradiction, so if PT reports a readable voice VLAN other than 20 the next run
will stop at the CONFIGURATION stage rather than the voice stage -- and that would
be the root cause, correctly located at the last L2 boundary before Router4. If
the getter answers `undefined`, the field is UNOBSERVABLE, the aggregate is
PARTIAL and no contradiction is fabricated. CP-SCALE still fails closed at its
separate exact-evidence gate, because partial access-port readback is not an
admitted governed ceiling.

## Phase 3 -- the DHCP frame's VLAN tag, read as values

`c1c74fa` reads exactly four measured properties -- `vlanId`, `tpid`, `cfi`,
`userPriority` -- on the child that `getOutFrame`/`getInFrame` return, spelled
literally, on two frames only: PHONE-02's DHCP egress copy and Switch5's
correlated ingress copy. `2db4c9d` stops the derived hex rendering from
overstating a negative `tpid`.

Two governed LIVEs, `c1c74fa` and `2db4c9d`, agree on every field:

```text
                     PHONE-02 getOutFrame   Switch5 getInFrame
vlanId                     20                     20
tpid                   -32512                 -32512
cfi                         0                      0
userPriority                0                      0
```

Run 1 (`c1c74fa`): frames 411/415, both at getStartSimTime 20569405.
Run 2 (`2db4c9d`): frames 26/27, both at getStartSimTime 537115.
Each run's pair shares ONE observed instant; the two runs have their own clocks
and those numbers are not comparable across runs.

Both frames were identity-reconfirmed before any value was read -- device,
sim_time, traffic type and, new in this phase, the ingress port. PT's own text
identifies them: "The DHCP client constructs a Discover packet and sends it out."
and "FastEthernet0/2 is blocked by STP. The device drops the frame."

FACT: `PHONE_TO_SWITCH_VLAN_VALUE_PRESERVED = YES`. The phone tags this DHCP
Discover 20 and Switch5 receives 20 on Fa0/2 at the same observed instant. This
REFUTES "the phone used data VLAN 10 for this frame" and REFUTES "the voice tag
is lost between phone and Switch5". The frame is dropped by STP with its tag
intact. It says NOTHING about the Router4 path.

`tpid` did NOT equal 33024. It read -32512 in both runs. `-32512 & 0xFFFF` is
0x8100, which a signed 16-bit field would explain exactly, but PT's storage width
for `tpid` is UNMEASURED here, so that stays a lead and no 802.1Q semantics are
claimed from it. The hex rendering is withheld for a negative reading and the
omission is named.

`FRAME_VLAN_FIELD_SEMANTICS = DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED` in
both runs -- but see below: run 2 shows the window DID hold the calibration.

## Two heads, and why one of them is always one behind

`CURRENT_PUSHED_HEAD` and `LATEST_GOVERNED_LIVE_HEAD` are different facts and
collapsing them is how a docs-only commit starts looking like a LIVE.

* `CURRENT_PUSHED_HEAD` is the head that was pushed BEFORE this checkpoint. A
  commit cannot contain its own hash, so this line always names the previous
  one; read the real one with `git rev-parse HEAD`.
* `LATEST_GOVERNED_LIVE_HEAD` is the source head a governed LIVE actually ran
  from. It moves ONLY when another governed LIVE supersedes it, never when a
  checkpoint is pushed.

## The calibration control read the wrong side of the right frame

The control rule takes an already-captured frame on an access port the typed plan
gives ONE VLAN (a phone port carries data AND voice, so either value would look
right and it calibrates nothing). It prefers the ingress side and falls back to
egress. In both runs the known port was the EGRESS port, so it read `getOutFrame`
and got nothing.

Run 2, frame 58 on Switch5, is the whole finding in one object. It enters on
GigabitEthernet0/1 (trunk) and leaves on FastEthernet0/22, which the typed plan
configures as a single-VLAN access port on VLAN 30:

```text
getInFrame  -> 11 members, vlanId 30, tpid -32512, cfi 0, userPriority 0
getOutFrame ->  7 members: dstMacAddress, frameCheckSequence, lengthType,
                payload, pduSize, pduType, srcMacAddress -- no tag fields at all
```

So PT returns TWO different object shapes, and the tag fields appear exactly
where a tag would be and vanish exactly where one would not. The rule read the
untagged egress copy, got four `undefined`s, and correctly recorded `vlan_match`
as None rather than False -- an unread field is not a mismatch, which is why the
run did not fabricate a contradiction.

The ingress copy of that same frame carries vlanId 30 and is bound for a port the
plan puts on VLAN 30. That is the independently-known control this phase was
looking for, and 30 is a SECOND distinct VLAN from the DHCP frame's 20, so the
multi-VLAN qualification is reachable from evidence already retained.

It is NOT yet a qualification, because reading the egress port's VLAN onto the
ingress copy assumes the switch preserves VLAN across that forward. That is
ordinary L2 behaviour and it is NOT measured here. Any future slice that uses it
must name the assumption instead of absorbing it.

## Phase A audit -- there is no valid ingress control in the retained windows

A control qualifies `child.vlanId` only when the KNOWN port and the READ side
are BOTH the ingress: the expected VLAN comes from the port the frame entered
by, and the observed value from that same side's child. Anything else needs an
assumption about what the switch does between one boca and the other.

Both retained journals were audited offline, no LIVE:

```text
Switch5 single-VLAN access ports (typed plan, FLOOR1 projection): 4
  ALL on VLAN 30: Fa0/22, Fa0/23, Fa0/24, Gi0/2
Switch5 hops ENTERING one of them:      run1 0        run2 0
Switch5 hops touching one, either side: run1 21       run2 18   (all egress)
switch_trace capture:  run1 194 hops, limit_reached FALSE  -> COMPLETE
                       run2 200 hops, limit_reached TRUE   -> TRUNCATED
```

Two consequences, and they are different in strength:

* run1's Switch5 scope was captured COMPLETE, so "nothing entered a VLAN-30
  access port" is a real absence FOR THAT WINDOW -- not a truncation artifact.
  It is still a bounded window and says nothing about other windows.
* run2's capture hit its limit, so its zero is the weaker kind of absence.

`STRONGLY_SUPPORTED_BY_MULTIVLAN_CONTROL` is UNREACHABLE on Switch5 whatever the
traffic does: all four single-VLAN ports carry VLAN 30, so two controls could
never carry two DISTINCT known VLANs. The best Switch5 can yield is
`SUPPORTED_BY_CONTROL`.

The selector was NOT reading the wrong side by preference -- it already prefers
the ingress. It fell back to the egress because no hop entered a known port. The
fallback itself was the defect: an access-port egress copy is the 7-member
untagged shape, so it can never qualify anything, and emitting it as a control
with a null verdict dressed a structural impossibility as a failed measurement.
The fallback is gone. `_CONTROL_TAG_GETTER` is a constant, not a branch, so no
code path can pair a known port with the opposite side's tag.

FRAME_VLAN_FIELD_SEMANTICS is unchanged by that fix -- it was, and remains,
DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED. The measured DHCP values are
untouched: the fix is subtractive and changes only what the journal calls a
control and why it says none was found.

NOT REQUIRED: a fresh governed LIVE for this fix. The audit already establishes
from retained evidence that no ingress control existed in either window, so a
re-run would re-render a reason string at the cost of a full CP-SCALE run.

## The calibration ran, and it found the wall rather than the answer

`tools/cp_scale_vlan_calibration_live.py` builds its own disposable switch and
two PCs, puts each PC on an access port of its own known VLAN, arms the DHCP
client in Realtime, steps Simulation, and reads `getInFrame().vlanId` on the
frame that ENTERED by that port. Every step worked:

```text
control     access VLAN   direct readback   frame   identity   getInFrame
VLAN 742    Fa0/1         VERIFIED          idx 23  reconfirmed  non-null
VLAN 743    Fa0/10        VERIFIED          idx 1   reconfirmed  non-null
```

And the answer was still UNOBSERVABLE, for a reason that is itself the finding.
Both ingress children exposed SEVEN members:

```text
dstMacAddress, frameCheckSequence, frameType, payload, pduSize, pduType,
srcMacAddress
```

None of the four tag fields is among them. A frame arriving from a plain host on
an access port is UNTAGGED, so there is no `vlanId` on it to compare.

**An access port cannot calibrate `vlanId`, and not for want of trying: the port
whose VLAN is independently known is precisely the port whose frames carry no
tag.** That is structural on PT 9.0.1.0858, not a property of this window, and no
amount of re-running changes it.

Three measurements now agree on two distinct object shapes:

```text
11 members, tag fields present : PHONE-02 DHCP egress, Switch5 DHCP ingress,
                                 Switch5 trunk ingress (frame 58, vlanId 30)
 7 members, no tag fields      : Switch5 access egress (Fa0/22),
                                 disposable access ingress (Fa0/1, Fa0/10)
```

That also says something about the phone that was not obvious: PHONE-02's DHCP
Discover comes back in the TAGGED shape, while a plain PC's does not. The phone
is emitting a tagged frame. It still does not qualify what the 20 MEANS.

FRAME_VLAN_FIELD_SEMANTICS = DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED,
unchanged and now for a measured structural reason rather than an empty window.

The next non-circular candidate is a trunk whose allowed-VLAN list is a SINGLE
VLAN, proven by direct readback: trunk ingress frames do carry the tagged shape
(frame 58 measured `vlanId 30` on Gi0/1), and the expected VLAN would come from
that same ingress port's own configuration rather than from a forwarding
assumption. It is NOT started here: the governing instruction excluded a
trunk-sourced expectation, and whether a single-allowed-VLAN trunk escapes that
exclusion is a decision, not an inference.

## Historical pre-LIVE next step -- completed by the trunk calibration

The prior checkpoint assigned an offline capability audit for a non-circular
single-allowed-VLAN trunk ingress calibration.  This is historical context; the
audit and the one governed disposable LIVE are now complete.

Access-port calibration is finished and it did not work: the port whose VLAN is
independently known is the port whose frames carry no tag. Re-running it is not
useful. The remaining non-circular candidate is a trunk ingress, because trunk
ingress frames DO come back in the tagged shape -- Switch5 frame 58 measured
`vlanId 30` on Gi0/1 -- so a port could in principle supply both a known VLAN and
a readable one on the SAME side.

First determine, offline and without any LIVE, whether this repository can
directly read back each of:

```text
TRUNK_ALLOWED_READBACK
TRUNK_ACTIVE_READBACK
TRUNK_FORWARDING_READBACK
TRUNK_NATIVE_VLAN_READBACK
```

and only then whether it could attempt:

```text
PRE_LIVE_CAN_ATTEMPT_SINGLE_ALLOWED_NON_NATIVE_CONTROL = YES | NO
```

If that cannot be proven, the trunk calibration does not start either.

A trunk carrying one allowed VLAN does NOT automatically qualify `vlanId`. Any
eventual control has to survive all four of these, and each has already burned a
slice in this investigation:

* **opposite-side forwarding assumptions** -- the expectation must come from the
  ingress port's own configuration, never from where the frame is going;
* **native VLAN ambiguity** -- a native VLAN travels untagged, so a single
  allowed VLAN that IS the native one calibrates nothing;
* **unverified allowed-VLAN intent** -- applied is not verified, exactly as with
  `getAccessVlan()`;
* **dropped or disallowed frames masquerading as controls** -- a frame the trunk
  refused is not evidence of what the trunk carries.

`tools/cp_scale_vlan_calibration_live.py` and
`qualify_frame_vlan_calibration.py` are the shape to extend: disposable, owned,
reverse cleanup, mode restored and verified, workspace compared to baseline.
Their orchestration is covered against fakes, so the logic can be changed
without paying for a run to find out.

## SINGLE-ALLOWED NON-NATIVE trunk audit -- capability exists, pre-LIVE ready

The offline audit found one narrow source seam, not a Packet Tracer evidence
ceiling.  The same registered and pagination-qualified `show interfaces trunk`
query already returns every independent observation the control needs.  The
capabilities before this slice were:

```text
TRUNK_ALLOWED_READBACK = IMPLEMENTED_AND_MEASURED
TRUNK_ACTIVE_READBACK = IMPLEMENTED_AND_MEASURED
TRUNK_FORWARDING_READBACK = IMPLEMENTED_AND_MEASURED
TRUNK_NATIVE_VLAN_READBACK = IMPLEMENTED_BUT_NOT_MEASURED_ON_THIS_BUILD
```

Allowed, active, and forwarding/not-pruned were independently retained and
verified on PT 9.0.1.0858 in the governed `e09f606` LIVE.  Native VLAN was
already the fifth field of `TrunkStatusRow`, populated from the first table of
that same registered query, but it remained an unchecked string and no
governed result projected it.  No new IOS command or PT getter was necessary.

Therefore, before LIVE, the offline design audit judged that the disposable
control could attempt all three proof obligations:

```text
PRE_LIVE_CAN_ATTEMPT_SINGLE_ALLOWED_READBACK = YES
PRE_LIVE_CAN_ATTEMPT_TARGET_NON_NATIVE_READBACK = YES
PRE_LIVE_CAN_ATTEMPT_FRAME_ADMISSION_CONTROL = YES
```

Those were capability hypotheses, not measured conclusions.  The current
post-LIVE conclusions are recorded in the next section.

The minimum implementation is additive.  `TrunkStatusRow.native_vlan` is now a
strict `int | None`; malformed or out-of-range text cannot become VLAN
identity.  `PacketTracerEnterpriseConfigurationRuntime.read_trunk()` exposes
one fresh, complete, registered read-only snapshot without collapsing any of
the four VLAN dimensions.

`TrunkFrameVlanCalibrationQualifier` builds two owned 3560 switches, two owned
PCs, two access links and two parallel trunk links.  Control A admits only 742
on its target ingress; control B admits only 743 on a different target ingress.
Each control requires, on that exact ingress and in one current direct
readback: operational trunking, allowed exactly the singleton target, active
exactly the singleton target, forwarding/not-pruned exactly the singleton
target, and an independently read native VLAN different from the target.  The
expected VLAN is the singleton readback value after it matches the disposable
control request, never the source-side port or forwarding intent.

The measured traffic composition is unchanged: arm both endpoint DHCP clients
in Realtime, enter Simulation, reset and step a bounded window, then enumerate
at most two frames entering the target switch from the owned source switch.
Only `getInFrame()` on the exact read-back ingress is eligible.  Endpoint arming,
frame identity, tag-member presence, ownership, reverse cleanup, mode
restoration and final baseline equivalence are all journalled separately.

FAIL-FIRST: the native field was the string `"1"`, malformed native text was
retained, `read_trunk()` did not exist, and the trunk calibration module could
not import.  Focused: 12 passed.  Affected: 161 passed.  Full: 2997 passed / 0
failed.  The first full process was interrupted by a Windows access violation
at 91%; the isolated test passed and two subsequent complete full runs passed,
the final one after all source changes.

LIVE has NOT run yet in this checkpoint.  It may run once, and only from the
clean pushed commit containing this section and the implementation.  A valid
control must still prove the native readback on the real PT build; an offline
contract is capability, not measurement.

## Singleton non-native trunk LIVE -- policy proved, tag still unobservable

One governed disposable LIVE completed from exact clean pushed
`d15a5b71dff8b95b56404e550540ca0f3aef018d` on PT 9.0.1.0858.  The first bridge
attempt hard-stopped before inventory or mutation because the Packet Tracer
webview was not polling.  Foregrounding the already-open MCP Control Center
restored its own documented polling loop; no snippet was pasted or run.  The
single actual LIVE then passed the checkout-local interpreter, production
package path, single import namespace, clean HEAD/upstream, authenticated bridge
and fresh empty semantic-workspace gates.

The baseline and final inventory were identical: zero semantic devices, the
same one backend-managed Power Distribution Device, and zero links.  Four owned
links were recorded before mutation, all four owned devices were removed in
reverse order, `workspace_restored=TRUE`, `realtime_restored=TRUE`, and the
journal contains no orchestration errors.  No `.pkt` was saved.

Control 742 established all policy dimensions on target ingress
`FastEthernet0/1`:

```text
operational trunking = YES
allowed VLANs = {742}
active VLANs = {742}
forwarding/not pruned VLANs = {742}
native VLAN = 1
endpoint DHCP armed = YES
frame entered exact ingress from owned source switch = YES (index 2)
source-switch -> target-switch hop identity reconfirmed = YES
getInFrame child = non-null
child members = dstMacAddress, frameCheckSequence, lengthType, payload,
                pduSize, pduType, srcMacAddress
tag fields present = none
observed vlanId = UNOBSERVABLE
```

This control proves that the exact ingress was policy-qualified for VLAN 742
without any opposite-side forwarding assumption.  It does NOT prove that the
selected frame was admitted AS VLAN 742: the frame is not end-to-end attributed
to the endpoint DHCP retry and its child exposes no VLAN value.  The retained
LIVE journal's derived `frame_admitted_for_target_vlan=TRUE` label therefore
overstated the raw facts.  A post-LIVE source correction, covered from this
retained evidence without another run, now separates
`frame_entered_policy_qualified_trunk` from target-VLAN admission; the latter is
true only for a numeric matching control whose end-to-end DHCP identity is
separately established.

Control 743 directly read target ingress `FastEthernet0/10` as operational
trunking, allowed `{743}`, active `{743}`, native VLAN 1, but forwarding/not
pruned was the explicit empty set.  Its convergence gate therefore remained
false.  A frame still entered from the owned source switch (index 1), was
identity-reconfirmed, and its non-null child exposed the same seven-member shape
with no tag fields.  It is UNOBSERVABLE, not a negative VLAN match; a physically
arriving frame does not override the explicit forwarding-policy observation.

The two intended controls shared the same source and target switches over two
parallel physical L2 links.  Control 743's forwarding/not-pruned readback was
the explicit empty set, so the controls did not provide independent forwarding
conditions.  The exact cause of that empty set was not directly proven; do not
diagnose it as STP blocking.  A future calibration must not reuse this topology.
Use either two independent switch pairs or one disposable trunk reconfigured
sequentially, but do not implement either alternative during this closeout.

The result is:

```text
TRUNK_ALLOWED_READBACK = IMPLEMENTED_AND_MEASURED
TRUNK_ACTIVE_READBACK = IMPLEMENTED_AND_MEASURED
TRUNK_FORWARDING_READBACK = IMPLEMENTED_AND_MEASURED
TRUNK_NATIVE_VLAN_READBACK = IMPLEMENTED_AND_MEASURED

CAN_PROVE_SINGLE_ALLOWED_NON_NATIVE_TRUNK_POLICY = YES
CAN_PROVE_SELECTED_FRAME_BELONGS_TO_SINGLE_ALLOWED_VLAN = NO
CAN_COMPLETE_FRAME_VLAN_SEMANTIC_CONTROL = NO

CONTROL_742_POLICY = VERIFIED_SINGLE_ALLOWED_NON_NATIVE
CONTROL_742_SELECTED_FRAME_VLAN = UNOBSERVABLE
CONTROL_743_POLICY = NOT_FORWARDING
CONTROL_743_FRAME = UNOBSERVABLE
FRAME_ENTERED_POLICY_QUALIFIED_TRUNK = OBSERVED
SELECTED_TRUNK_FRAME_TAG_SHAPE = UNTAGGED / NO vlanId MEMBER
SELECTED_TRUNK_FRAME_END_TO_END_DHCP_IDENTITY = NOT_ESTABLISHED
PARALLEL_TRUNK_CONTROL_INDEPENDENCE = NOT_ESTABLISHED
CONTROL_743_CONFOUNDED_BY_PARALLEL_L2_TOPOLOGY = YES
DO_NOT_RERUN_SAME_PARALLEL_TRUNK_TOPOLOGY = YES
FRAME_VLAN_FIELD_SEMANTICS = DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED
```

There was no numeric contradiction, so
`CONTRADICTED_BY_CONTROL` is not justified.  There was also no matching control,
so neither support level is justified.  The direct PHONE-02 and Switch5 values
remain 20, but `PHONE_DHCP_VLAN_IDENTITY` remains
`NOT_YET_GLOBALLY_QUALIFIED`.

The next evidence seam is cross-hop frame correlation; whether existing
measured surfaces can provide it is not yet audited.  The target frames were
attributed to the owned source switch, but not end-to-end to the endpoint DHCP
retry across that switch.  The seven-member object therefore cannot be called a
forwarded DHCP frame or evidence that the source switch removed a tag.  The next
session must first inspect existing `srcMacAddress`, `dstMacAddress`, source and
destination strings, `previous_device`, ports, simulation time/start time,
traffic type, Packet Tracer decisions, and child/frame identity offline.  Do
not invent a permanent type-7 mapping, inspect payload recursively, or run
another Packet Tracer LIVE for that audit.

```text
NEXT_EVIDENCE_SEAM = CROSS_HOP_FRAME_CORRELATION
CROSS_HOP_FRAME_CORRELATION_CAPABILITY = NOT_YET_AUDITED
NEXT_ACTIVE_STEP = OFFLINE CROSS-HOP FRAME CORRELATION AUDIT
FALLBACK_NEXT_CAUSAL_EXPERIMENT = POSITIVE_DISPOSABLE_VOICE_AB
```

If existing surfaces cannot close correlation cheaply, stop the `frame.vlanId`
qualification line.  The next causal experiment after that is a known-good
disposable Voice A/B comparison against CP-SCALE, not an exact replay of
historical E7.  Record that alternative only; do not execute it in this
closeout.

FAIL-FIRST for the retained-evidence correction: a frame with an unobservable
VLAN still reported target-VLAN admission.  Focused: 13 passed.  Affected: 162
passed.  The full gate then found two intentionally pinned handoff-head
assertions, updated alongside this continuity record.  Final continuity gates:
focused 84 passed, affected 118 passed, full 2998 passed / 0 failed.

SESSION CLOSEOUT correction: five focused source assertions failed first on
the absent policy, hop-identity, end-to-end-identity and parallel-independence
contracts; two handoff assertions then failed first on the stale head and
ambiguous current terminology.  Final closeout gates: focused 14 passed,
affected 120 passed, full 3000 passed / 0 failed.  Graphify updated offline;
`git diff --check` passed.  No Packet Tracer LIVE ran during the closeout.
An intermediate full run failed four namespace-isolation contracts because a
new serializer test imported the production package into pytest; the test was
corrected to verify the source labels without loading that namespace.

## Reading the heads

Trust `git rev-parse HEAD`, never the handoff, for what is checked out. The
handoff records which commit ran which LIVE, and those are three different
facts:

```text
CURRENT_PUSHED_HEAD          the checkpoint pushed BEFORE this one. A commit
                             cannot contain its own hash, so this line always
                             names the previous one.
LATEST_GOVERNED_LIVE_HEAD    the source the last CP-SCALE LIVE ran from. Moves
                             only when another CP-SCALE LIVE supersedes it.
LATEST_CALIBRATION_LIVE_HEAD the source the last disposable calibration ran
                             from. Moves independently of the CP-SCALE one.
```

Forbidden from any future run's conclusions unless that run independently proves
that exact claim: "PHONE-02 does not send DHCP", "DHCP is filtered out",
"Switch5 drops DHCP", "Router4 never sees DISCOVER". A capture that reached its
limit makes every negative reading `UNOBSERVABLE`, and an empty control endpoint
is not proof of filtering.

Do not wire any new DHCP observation into `VerificationKind.DHCP_POOL`: the
ceiling at `qualify_cp_scale_live.py:625` enforces status UNOBSERVABLE +
`fresh_evidence` False + evidence_method `runtime_observability_limit` + every
field UNOBSERVABLE. New observations must be additive or the governed gate
rejects them.

Do not apply the PortFast fix as part of the calibration work.
`SOURCE_DEFECT_FOUND = YES`, `SOURCE_DEFECT =
EDGE_STP_POLICY_STAGE_GATING_AND_ORDERING`, and `VOICE_ROOT_CAUSE =
NOT_YET_CONFIRMED` all stand; the causal decision that would justify the fix has
not been taken. CP-SCALE remains `OPEN / NOT VERIFIED`.

## Bridge lifecycle -- PARTIAL PASS, still APPLIED NOT VERIFIED

`4c881d5` rechains the webview command poll past everything that can throw and
adds a watchdog above it, after the blocker reproduced with the recorded
signature (`last_poll_ago: None`, `unauth_count: 0`, file bridge alive, token
unchanged). Root cause was `log()` throwing inside `x.onload` before the
rechain, while `pollBridgeStatus`'s own interval kept the UI looking healthy.

FACT: a full Floor-1 run completed afterwards and the bridge stayed fresh; three
further HTTP sessions connected cleanly; no duplicate polling or execution.

FACT, fresh run at `78996aa`: authenticated HTTP connected with a fresh poll,
remained connected at both governed resume gates, and surfaced no transport
failure during the complete Floor-1 deployment and 180-second voice observation.
The runner then stopped its transport normally after its governed voice failure
and verified cleanup. A subsequent fresh session remains part of the next LIVE
preflight; the currently loaded webview source is still not independently
identifiable from Python.

FACT, fresh run ending after checkpoint `43eba72`: authenticated HTTP again
connected fresh, remained healthy through routing core and the resume gate, and
did not create the configuration failure. The runner stopped the transport
normally after its governed failure and verified cleanup.

FACT, fresh run at `8b4cdd4`: authenticated HTTP connected and routing core
completed. The failure was the runner's repository gate after its own tracked
summary write, not an HTTP disconnect. Transport stopped normally and cleanup
was verified.

FACT, fresh run at `e09f606`: authenticated HTTP stayed fresh through routing
core, `router4-switch10`, and the Floor-1 resume gate with zero unauthenticated
requests. The process completed its full 180-second voice observation, stopped
the transport normally after the governed failure, and verified cleanup.

UNOBSERVABLE: whether Packet Tracer has actually **loaded** the patched
`interface.js`. Nothing readable from Python distinguishes the patched loop from
the old one while both are healthy. Confirm by reloading the extension and
watching for the watchdog log line, or by inspecting the loaded source.

Diagnose a failure with:

```bash
PYTHONPATH=src .venv/Scripts/python.exe -c \
  "from packet_tracer_mcp.infrastructure.execution.live_bridge import PacketTracerHttpTransport as T; \
   from packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import canonical_bridge_polling_error; \
   t=T(); print('connected:', t.start(timeout_seconds=20.0)); \
   print(canonical_bridge_polling_error(t.status_dict()) or '(nothing to diagnose)'); t.stop()"
```

Never repoint the runner at the file bridge to get past it. The file bridge is
alive in every one of these failures -- it runs in the Script Engine with no
window, while this channel lives in the webview.

## Secondary anomalies -- recorded, not chased

* Complete 5-page `show ephone` captures name **19 of 21** ephones; `3001`
  (ephone-1) and `3007` (ephone-7) absent, reproduced in 2 of 3 complete
  captures. All 21 bindings applied, none refused. A duplicate MAC from
  `_phone_mac` is a HYPOTHESIS, not a finding.
* The raw capture is still not retained in the evidence. Retaining it is the
  cheapest next step on that question -- parsed verdicts cannot say why a row is
  missing, only that it is.
* Capture completeness is flaky run to run (complete / truncated / complete /
  truncated), always fail-closed, never fabricating absence.

Do not chase these ahead of acquisition: a phone with no address cannot register,
so that table stays UNREGISTERED regardless.

## Driving the live runner

This session used the persistent runner directly and left it waiting at each
explicit checkpoint while the Git commit/push was performed externally. No
scratchpad driver was relied upon or verified from this worktree.

Do not edit tracked files under `src/`, `tests/`,
`tools/cp_scale_canonical_live.py` or the two reference documents while a run is
in flight: the checkpoint refuses to advance if governed source changed.
`EXTENSION/` is not governed source.

**Do not stop a run mid-flight.** Physical ownership is runtime-instance-local by
design, so a killed run leaves its devices behind with no governed way to clean
them up.

A Floor-1 run now costs about seven minutes end to end. That is what makes
iterating on this cheap, and it is why the registration table is read once per
call control instead of once per phone.

## Commits since the previous handoff

```text
8d59499 fix(cp-scale): read phone DHCP client state from voice SVI
d0db204 docs(cp-scale): checkpoint governed routing core
78996aa docs(cp-scale): checkpoint router4-switch10
6eb0d8e fix(cp-scale): verify voice VLAN traversal on trunks
43eba72 docs(cp-scale): checkpoint fresh routing core
8b4cdd4 fix(cp-scale): allow bounded trunk forwarding convergence
e09f606 fix(cp-scale): keep runtime checkpoints outside tracked tree
4b9fe11 feat(cp-scale): observe DHCP server bindings
994e2ea feat(cp-scale): observe scoped DHCP exchange statistics
b989eb0 feat(cp-scale): capture post-failure simulation evidence
1d2c186 feat(cp-scale): observe phone-facing voice VLAN
8402d28 feat(cp-scale): bound DHCP diagnostic by simulation time
2f2055c feat(cp-scale): observe phone-edge STP in realtime
540c746 feat(cp-scale): qualify the spanning-tree pager on measured evidence
```
