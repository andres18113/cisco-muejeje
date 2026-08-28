# CP-SCALE continuation handoff

## Canonical current state

This deliberately small block is the only machine-readable current-state
contract in this document. Historical `KEY = VALUE` prose outside it is not
authoritative and must not be parsed as state.

<!-- CP_SCALE_STATE_BEGIN -->
DHCP_DORA_QUERY_STATUS = MEASURED_UNSUPPORTED
DORA_EXISTING_SURFACE_USABLE = NO
DORA_QUERY_READBACK = UNOBSERVABLE
FIRST_DHCP_RUNTIME_BOUNDARY = NOT_ESTABLISHED
FIRST_COMMON_VOICE_OBSERVABILITY_BOUNDARY = ENDPOINT_ADDRESS_CONTRADICTED
DHCP_POOL_EXISTENCE_READBACK = VERIFIED
DHCP_POOL_RANGE_READBACK = VERIFIED
DHCP_POOL_AVAILABLE_SPACE_READBACK = VERIFIED
DHCP_POOL_CONFIGURATION_READBACK = NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS
DHCP_POOL_DEFAULT_ROUTER_READBACK = NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS
DHCP_POOL_EXCLUSIONS_READBACK = NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS
POOL_EXISTENCE_CAUSE = WEAKENED
POOL_EXHAUSTION_CAUSE = REFUTED_FOR_THIS_DISPOSABLE
OPTION150_READBACK = NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS
PORTFAST_CAUSAL_BRANCH = CLOSED_FOR_NOW
PORTFAST_AS_VOICE_ROOT_CAUSE = STRONGLY_WEAKENED_FOR_GOVERNED_DISPATCH
SERVER_RECEIVES_DISCOVER = UNOBSERVABLE
DHCP_TRANSACTION_PROGRESS = UNOBSERVABLE
VOICE_VLAN_REALTIME_DATA_PLANE_FORWARDING = NOT_ESTABLISHED
ACCESS_VLAN_SHAPE_CONTROLS_STP_MEMBERSHIP = ESTABLISHED
ACCESS_VLAN_SHAPE_CONTROLS_DHCP = NOT_YET_ESTABLISHED
VOICE_ENDPOINT_OUTCOME_RUN9 = SAME_FAILURE
CAUSAL_EXPERIMENT_RESULT_RUN9 = PARTIAL_OR_DIVERGENT
INTERVENTION_FWD_OBSERVED_RUN9 = NO
INTERVENTION_NEVER_FWD_DURING_RUN9 = NOT_ESTABLISHED
FRESH_DHCP_TRIGGER = NOT_ESTABLISHED_RUN11_PRE_FLAGS_ALREADY_YES
FRESH_7960_DHCP_TRANSACTION = NOT_INDEPENDENTLY_ESTABLISHED
PHONE_DHCP_LIFECYCLE_DIAGNOSTIC = READY
PHONE_DHCP_LIFECYCLE_LIVE_EXECUTED = NO
PHONE_DHCP_LIFECYCLE_CHANNELS = SVI_DHCP | DEVICE_DHCP
PHONE_DHCP_LIFECYCLE_DERIVATIONS = PER_PHONE
PHONE_DHCP_LIFECYCLE_LEDGER_ROLE = PHONE_DHCP_LIFECYCLE_QUALIFICATION
FIRST_OBSERVED_SVI_DHCP_ENABLED_MILESTONE = NOT_ESTABLISHED
FIRST_OBSERVED_DEVICE_DHCP_ENABLED_MILESTONE = NOT_ESTABLISHED
SVI_DHCP_ENABLED_BEFORE_FWD = UNOBSERVABLE
DEVICE_DHCP_ENABLED_BEFORE_FWD = UNOBSERVABLE
RUN10_EXECUTED = YES
RUN10_RESULT = STP_PRECONDITION_NOT_ESTABLISHED
RUN10_FWD_GATE = UNOBSERVABLE
RUN10_STP_GATE_OBSERVED_STATES = LIS -> LRN -> UNOBSERVABLE
RUN10_STP_GATE_DURATION_MS = 21844
RUN10_STP_GATE_SAMPLES = 11
RUN10_STP_GATE_IDENTITY = NOT_ESTABLISHED
RUN10_TERMINAL_STP_FAILURE_DIMENSION = NOT_RETAINED
STP_GATE_DIAGNOSTIC_RETENTION = READY
STP_GATE_GAP_TOLERANCE = READY
STP_GATE_SUCCESS_CONTRACT = EXECUTED + FRESH + COMPLETE + CONFIRMED_UNIQUE + FWD
STP_GATE_FAILURE_DIMENSIONS = EXECUTION | FRESHNESS | COMPLETENESS | IDENTITY | PARSING | QUERY_SESSION
STP_GATE_QUERY_COUNT_PER_SAMPLE = ONE
SECOND_STP_QUERY_ADDED = NO
RUN10_DHCP_FLAG_TRANSITION_CONTRACT = PRE_NO + ARM_ACCEPTED + POST_YES_REQUIRED
RUN10_DHCP_FLAG_TRANSITION = UNOBSERVABLE
RUN10_ACQUISITION_STARTED = NO
RUN10_ACQUISITION_BOUNDARY = ACQUISITION_NOT_STARTED_STP_PRECONDITION_UNMET
RUN10_TRUNK_VOICE_FORWARDING = CONTRADICTED
RUN10_TRUNK_ALLOWED_VLANS = NOT_RETAINED
RUN10_TRUNK_ACTIVE_VLANS = NOT_RETAINED
RUN10_TRUNK_FORWARDING_VLANS = NOT_RETAINED
RUN10_TRUNK_VLAN930_ALLOWED = YES
RUN10_TRUNK_VLAN930_ACTIVE = YES
RUN10_TRUNK_VLAN930_FORWARDING = NO
RUN11_EXECUTED = YES
RUN11_RESULT = FRESH_DHCP_TRIGGER_UNPROVEN
RUN11_FWD_GATE = FORWARDING
RUN11_STP_GATE_OBSERVED_STATES = LIS -> LRN -> UNOBSERVABLE -> LRN -> UNOBSERVABLE -> FORWARDING
RUN11_STP_AUTHORITY_TRANSITIONS = LIS(AUTHORITATIVE) -> LRN(AUTHORITATIVE) -> UNOBSERVABLE(COMPLETENESS) -> LRN(AUTHORITATIVE) -> UNOBSERVABLE(COMPLETENESS) -> FORWARDING(AUTHORITATIVE)
RUN11_STP_FAILURE_DIMENSIONS = COMPLETENESS
RUN11_STP_GATE_DURATION_MS = 30327
RUN11_STP_GATE_SAMPLES = 15
RUN11_AUTHORITATIVE_FWD_OBSERVED = YES
RUN11_TRUNK_ALLOWED_VLANS = (930, 931)
RUN11_TRUNK_ACTIVE_VLANS = (930, 931)
RUN11_TRUNK_FORWARDING_VLANS = (930, 931)
RUN11_TRUNK_READ_AUTHORITY = AUTHORITATIVE
RUN11_CONTROL_DHCP_PRE = YES
RUN11_INTERVENTION_DHCP_PRE = YES
RUN11_CONTROL_ARM_ACCEPTED = UNOBSERVABLE
RUN11_INTERVENTION_ARM_ACCEPTED = UNOBSERVABLE
RUN11_CONTROL_DHCP_POST = UNOBSERVABLE
RUN11_INTERVENTION_DHCP_POST = UNOBSERVABLE
RUN11_DHCP_FLAG_TRANSITION_VALID = UNOBSERVABLE
RUN11_ACQUISITION_STARTED = NO
RUN11_ACQUISITION_BOUNDARY = ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN
TRUNK_FORWARDING_SEMANTIC_AUDIT = IOS_STP_FORWARDING_AND_NOT_PRUNED_SET_ON_SHARED_TRUNK
TRUNK_READ_AUTHORITY_RETENTION = READY
STP_VS_TRUNK_RELATION = NOT_ESTABLISHED
VOICE_ROOT_CAUSE = STRONG_CANDIDATE / NOT_CONFIRMED
NEXT_ACTIVE_STEP = PHONE_DHCP_LIFECYCLE_QUALIFICATION_LIVE
CP_SCALE_STATUS = OPEN / NOT VERIFIED
<!-- CP_SCALE_STATE_END -->

## Phone DHCP lifecycle qualification prepared -- not run LIVE

The opt-in observational mode retains each phone's separate SVI and device DHCP
flags, SVI presence, SVI IPv4, device IPv4 and already-exposed evidence
authority from the same endpoint observation.  It reads after creation, link
creation, the existing full network configuration batch (L2, L3, services and
DHCP pool), Voice/CME configuration, Realtime verification, immediately before
the existing FWD gate and immediately after authoritative FWD.  Each selected
point performs one bounded existing endpoint/SVI read per phone without retry;
that sequential read latency may shift later observation times and is retained
as the timing-intrusion assessment.

The mode never calls `configure_endpoint_dhcp()`, opens no acquisition window
and adds no IOS query, PT observer or mutation primitive.  The default and
RUN11 modes remain unchanged.  Per-phone earliest-observed-YES and
enabled-before-FWD derivations are ready independently for the SVI and device
channels, and the dedicated lifecycle ledger role is accepted.  All lifecycle
results remain unestablished until a governed LIVE; Packet Tracer was not run
during preparation.

## RUN10 STP boundary and trunk forensics

The immutable RUN10 artifact
`positive-voice-ab-run10-stp-precondition-unobservable.json` still hashes to
`6c128bae161cb41bf5c879ac7fde14aaad9750e1d5922aa256dfbcd0bd5c3297`.
Its STP gate retained only `LIS -> LRN -> UNOBSERVABLE`, 11 samples and
21,844 ms. It did not retain the terminal `IosCommandResult`, so execution,
freshness, completeness, identity, parser and query/session failure cannot be
reconstructed honestly. The terminal failure dimension remains NOT_RETAINED.

The same artifact retained the shared-trunk membership verdicts but not their
source tuples. It proves only that VLAN 930 was in the IOS allowed set and the
allowed-and-active set, but absent from the section IOS labels `Vlans in
spanning tree forwarding state and not pruned`. That is the trunk uplink's
forwarding/not-pruned membership, not the phone access port's STP state. The
exact forwarding set, and therefore whether VLAN 931 was also affected, is
NOT_RETAINED; the two surfaces do not establish a causal relation.

The prepared harness now keeps parsed STP state and compact authority metadata
from one registered `show spanning-tree` result. Transient UNOBSERVABLE samples
remain in its meaningful state/authority transitions while polling continues
inside the existing 60-second bound; only a new CONFIRMED_UNIQUE FWD sample can
authorize acquisition. The trunk
foundation similarly keeps its exact operational status, native VLAN, allowed,
active and forwarding tuples plus compact authority metadata. No second STP
query, new observer, mutation, Packet Tracer LIVE, RUN10 rewrite or RUN11 was
introduced.

## Resume identity and hard boundaries

```text
BRANCH = feature/runtime-ripv2
UPSTREAM = personal/feature/runtime-ripv2
PACKET_TRACER_BUILD = 9.0.1.0858
LATEST_PREPARED_IMPLEMENTATION_HEAD = 8ecee845c0553ae25e4e82d965671e98cf135bf3
NEXT_LIVE_HEAD_SOURCE = git rev-parse HEAD (authoritative)
LATEST_GOVERNED_LIVE_HEAD = 8ecee845c0553ae25e4e82d965671e98cf135bf3
LATEST_FRAME_VLAN_CALIBRATION_LIVE_HEAD = d15a5b71dff8b95b56404e550540ca0f3aef018d
LATEST_VOICE_AB_LIVE_HEAD = 8ecee845c0553ae25e4e82d965671e98cf135bf3
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
CROSS_HOP_FRAME_CORRELATION_WITH_EXISTING_SURFACES = NO
CROSS_HOP_FRAME_CORRELATION_CAPABILITY = NOT_AVAILABLE_WITH_CURRENT_MEASURED_SURFACES
CROSS_HOP_CORRELATION_BLOCKER_IDENTITY_FIELD = NONE_MEASURED
CROSS_HOP_CORRELATION_BLOCKER_RETAINED_CHAIN = LEGS_3_AND_4_ABSENT
BEST_EXISTING_CORRELATION_KEY = PREVIOUS_DEVICE_PLUS_IN_PORT
FRAME_MAC_MEMBERS = DISCOVERED_NOT_MEASURED
FRAME_OBJECT_UUID = NOT_MEASURED_ON_FRAMES
RETAINED_DHCP_CHAIN_LONGEST = 2_OF_4_LEGS
CROSS_HOP_CORRELATOR_IMPLEMENTED = NO
FRAME_VLAN_QUALIFICATION_LINE = STOPPED
POSITIVE_VOICE_AB_IMPLEMENTED = YES
POSITIVE_VOICE_AB_LIVE = RUN at c9d6ead (governed, Realtime, cleaned up)
PACKET_TRACER_PROCESS_PRESENT = YES
POSITIVE_VOICE_AB_RESULT = SAME_FAILURE
RAW_VOICE_AB_RUNS_PINNED = 11 (run1..run11, SHA-256 in
    docs/reference/cp-scale/positive_voice_ab_runs.json)
DISPOSABLE_VOICE_NAMESPACE = MCP-VOICEAB- (typed, not the `__MCP_` discovery
    one: the trusted control-plane renderer cannot reach that prefix)
LIFECYCLE_APPLIED_VERIFIED_BOUNDARY = SEPARATED at 241e64b
POSITIVE_SLICE_PORTFAST = APPLIED (run 6; run 4 was NOT_APPLIED)
PORTFAST_READBACK = UNOBSERVABLE (Type column reads P2p; no edge marker has
    ever been measured on this build, so its absence says nothing)
PORTFAST_EXPERIMENT_BPDU_GUARD = OFF (one variable, deliberately)
PORTFAST_INTERVENTION_RESULT = NO_EFFECT
PORTFAST_SUFFICIENCY_IN_DISPOSABLE_VOICE = NOT_ESTABLISHED
GOVERNED_EDGE_PORTFAST_MUTATION = APPLIED_NO_OBSERVED_EFFECT
GOVERNED_EDGE_PORTFAST_DISPATCH_EFFECT = NO_OBSERVED_EFFECT
PORTFAST_RUNTIME_STATE = UNOBSERVABLE
PORTFAST_CAUSAL_BRANCH = CLOSED_FOR_NOW
RUN6 = CURRENT_NAMESPACE_PORTFAST_INTERVENTION
RUN7 = CURRENT_NAMESPACE_NO_PORTFAST_PAIRED_BASELINE
PAIRED_BASELINE_MATCH = YES
PAIRED_NETWORK_OUTCOME_MATCH = YES
FIRST_STAGE_CHANGED_BETWEEN_PAIRED_RUNS = NONE
RUN6_VS_RUN7_SAME_CODE_REVISION = NO
RUN6_VS_RUN7_SAME_NETWORK_MUTATION_PATH = YES
RUN6_VS_RUN7_SAME_VOICE_CONFIGURATION = YES
RUN6_VS_RUN7_OBSERVER_DIFFERENCE = EDGE_MARKER_CLASSIFIER_FIX_ONLY
RUN4_VS_RUN6_SINGLE_VARIABLE = NOT_STRICTLY_ESTABLISHED
RUN4_VS_RUN6_SECOND_VARIABLE = DISPOSABLE_NAMESPACE_CHANGED
DISPOSABLE_NAMESPACE_EFFECT = NONE_OBSERVED (run 7 matches run 4 on every
    decisive field across the namespace change)
ISOLATED_PORTFAST_COMPONENT_TESTED = YES
EXACT_CANONICAL_STP_REPAIR_TESTED = NO
POSITIVE_SLICE_VOICE_VLAN_READBACK = VERIFIED 2/2
POSITIVE_SLICE_PHONE_DHCP_ENABLED = YES 2/2 (read on Vlan930)
POSITIVE_SLICE_VOICE_SVI_PRESENT = YES 2/2
POSITIVE_SLICE_PHONE_IPV4 = NONE 2/2 (channel present and answered none)
POSITIVE_SLICE_VOICE_DHCP_BINDINGS = 0 (fresh + complete table)
POSITIVE_SLICE_SCCP_REGISTRATION = NOT_REGISTERED 2/2
POSITIVE_SLICE_STP_VOICE_PHONE_ROW = ABSENT before and after
POSITIVE_SLICE_TRUNK_OPERATIONAL = VERIFIED (Gi0/1 trunking)
POSITIVE_SLICE_TRUNK_ALLOWED_930 = VERIFIED
POSITIVE_SLICE_TRUNK_ACTIVE_930 = VERIFIED
POSITIVE_SLICE_TRUNK_FORWARDING_930 = VERIFIED
POSITIVE_SLICE_TRUNK_NATIVE = VERIFIED (1)
POSITIVE_SLICE_ROUTER_VOICE_SUBINTERFACE = VERIFIED (FastEthernet0/0.930)
POSITIVE_SLICE_ROUTER_VOICE_IPV4 = VERIFIED (10.93.0.1)
POSITIVE_SLICE_ROUTER_VOICE_STATE = VERIFIED (up/up)
CALL_CONTROL_EPHONE_TABLE = VERIFIED (fresh + complete, 2 ephone rows)
DHCP_DORA_QUERY_STATUS = MEASURED_UNSUPPORTED
DORA_EXISTING_SURFACE_USABLE = NO
EXISTING_DORA_SURFACE = UNSUPPORTED_ON_PT_9_0_1_0858
VOICE_DHCP_DORA_QUERY = SHOW_IP_DHCP_SERVER_STATISTICS_INTERFACE / UNSUPPORTED_ON_PT_9_0_1_0858
DORA_BEFORE = NOT_CAPTURED / QUERY_MEASURED_UNSUPPORTED
DORA_AFTER = NOT_CAPTURED / QUERY_MEASURED_UNSUPPORTED
DORA_QUERY_READBACK = UNOBSERVABLE
VOICE_DHCP_DORA_DELTA = UNOBSERVABLE
DHCP_SERVER_OBSERVED_DISCOVER = UNOBSERVABLE
DHCP_SERVER_SENT_OFFER = UNOBSERVABLE
FIRST_DHCP_RUNTIME_BOUNDARY = NOT_ESTABLISHED
DHCP_POOL_CONFIGURATION_READBACK = NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS
OPTION150_READBACK = NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS
TELEPHONY_SERVICE_READBACK = NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS
FIRST_COMMON_VOICE_OBSERVABILITY_BOUNDARY = DHCP_POOL_DEFINITION / UNOBSERVABLE
FIRST_CONTRADICTED_VOICE_STAGE = ENDPOINT_ADDRESS
COMMON_VOICE_FOUNDATION = VERIFIED as far as governed reads reach
SAME_ROOT_CAUSE = NOT_ESTABLISHED
SCALE_SPECIFIC_VOICE_FAILURE = NOT_ESTABLISHED / WEAKENED
SCALE_SPECIFIC_VOICE_FAILURE_LEVEL = WEAKENED_AT_SYMPTOM_LEVEL (not REFUTED)
NEXT_ACTIVE_STEP = DHCP_POOL_OBSERVER_ARCHITECTURE_DECISION
FALLBACK_NEXT_CAUSAL_EXPERIMENT = POSITIVE_DISPOSABLE_VOICE_AB_WITH_PORTFAST
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
PORTFAST_AS_VOICE_ROOT_CAUSE = STRONGLY_WEAKENED_FOR_GOVERNED_DISPATCH
VOICE_VLAN_STP_ROW_ABSENCE_CAUSAL_STATUS = NOT_ESTABLISHED_AS_CAUSE;
    co-occurs with the failure at four devices as well as at CP-SCALE size
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

That retained LIVE establishes the disposable Voice observer checkpoint too.
Changing the target from `FastEthernet0/0.20` to `FastEthernet0/0.930` cannot
restore a command rejected inside the `statistics` token, before IOS reaches the
interface argument. No qualification rerun, before/after capture, counter reset,
new query, or run8 is justified:

```text
DHCP_DORA_QUERY_STATUS = MEASURED_UNSUPPORTED
DORA_EXISTING_SURFACE_USABLE = NO
EXISTING_DORA_SURFACE = UNSUPPORTED_ON_PT_9_0_1_0858
VOICE_DHCP_DORA_QUERY = SHOW_IP_DHCP_SERVER_STATISTICS_INTERFACE / UNSUPPORTED_ON_PT_9_0_1_0858
DORA_QUERY_READBACK = UNOBSERVABLE
VOICE_DHCP_DORA_DELTA = UNOBSERVABLE
FIRST_DHCP_RUNTIME_BOUNDARY = NOT_ESTABLISHED
NEXT_ACTIVE_STEP = DHCP_POOL_OBSERVER_ARCHITECTURE_DECISION
```

This DORA result is separate from pool-definition observability.
`FIRST_COMMON_VOICE_OBSERVABILITY_BOUNDARY = DHCP_POOL_DEFINITION /
UNOBSERVABLE` remains unchanged, and option 150 remains downstream of address
acquisition rather than the immediate blocker for `PHONE_IPV4 = NONE`.

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
CROSS_HOP_FRAME_CORRELATION_CAPABILITY = NOT_AVAILABLE_WITH_CURRENT_MEASURED_SURFACES
NEXT_ACTIVE_STEP = COMMON_VOICE_LIFECYCLE_INVESTIGATION
FALLBACK_NEXT_CAUSAL_EXPERIMENT = POSITIVE_DISPOSABLE_VOICE_AB_WITH_PORTFAST
```

If existing surfaces cannot close correlation cheaply, stop the `frame.vlanId`
qualification line.  The next causal experiment after that is a known-good
disposable Voice A/B comparison against CP-SCALE, not an exact replay of
historical E7.  Record that alternative only; do not execute it in this
closeout.

## Cross-hop frame correlation audit -- answered OFFLINE, seam closed

The audit ran with no Packet Tracer LIVE, against already-measured surfaces and
retained evidence only.  It answered NO, for two independent reasons.  Both are
recorded because closing only one would let a later session believe the seam had
reopened.

**Reason 1 -- no measured packet-identity field.**  The event-list hop carries
`index`, `device`, `previous_device`, `in_port`, `out_port`, `source`,
`destination`, `traffic_type`/`traffic_type_raw`, `status`, `reason`, `sim_time`,
`transit_time` and the flowchart `decisions`.  None of them identifies a packet.
`getSourceString()` came back empty on 100% of the measured DHCP rows (0/84 at
Switch5, 0/5 at the phone), and `getDestinationString()` is the broadcast
255.255.255.255 that all 21 phones share.  The seven enumerated child members --
`dstMacAddress`, `frameCheckSequence`, `lengthType`, `payload`, `pduSize`,
`pduType`, `srcMacAddress` -- were DISCOVERED, never READ: the child probe reads
values only for `vlanId`, `tpid`, `cfi` and `userPriority`.  Reading a MAC would
mean invoking a newly discovered member, which is the new-getter boundary this
line is not allowed to cross.  `getObjectUuid` is measured only on LINKS in
topology observation; it identifies a topology object, and nothing measured shows
it surviving a hop copy.

**Reason 2 -- the retained chain does not have the legs.**  The governed LIVE at
2db4c9d retains 392 hops in four device-filtered traces.  Of the DHCP frames:
the phone emitted 5 (`sent`, out_port present), Switch5 received 84, and the
router/control traces contain zero.  All 84 Switch5 DHCP rows are `dropped` with
an empty `out_port` -- PT's own decision text reads "is blocked by STP. The
device drops the frame."  So legs 3 and 4 of the chain never existed to be
correlated:

```text
LEG 1 endpoint DHCP emission        PRESENT
LEG 2 source switch ingress         PRESENT   (previous_device + in_port)
LEG 3 source switch egress          ABSENT    (0/84 out_port; all dropped)
LEG 4 target switch ingress         ABSENT    (0 DHCP rows in router trace)
```

Candidate keys, each judged separately:

```text
srcMacAddress + dstMacAddress          NOT_AVAILABLE (values never measured)
                                       and AMBIGUOUS by design: retries share a
                                       source MAC and a broadcast destination
source/destination + sim_time          NOT_AVAILABLE (source empty 100%);
                                       sim_time collides: 77 distinct / 84 rows
MAC pair + getStartSimTime             NOT_AVAILABLE (MAC values never measured)
PT decision lineage / flowchart        AMBIGUOUS: 21 distinct signatures / 84
                                       rows -- it names the PORT, not the
                                       packet, so a phone's retries are identical
traffic source + MAC + adjacency       NOT_AVAILABLE (source empty, MAC unread)
event-list index                       SEMANTICALLY_UNQUALIFIED: a live list
                                       position, not an identity
```

The best key existing evidence supports is `previous_device` + `in_port`, and
that is exactly ONE hop.  It is the same hop identity already recorded, and it
must not be promoted into the end-to-end identity it never proved.

No correlator was built.  Building an observer to keep this line alive is the
thing the boundary exists to prevent.

```text
CROSS_HOP_FRAME_CORRELATION_WITH_EXISTING_SURFACES = NO
CROSS_HOP_FRAME_CORRELATION_CAPABILITY = NOT_AVAILABLE_WITH_CURRENT_MEASURED_SURFACES
CROSS_HOP_CORRELATION_BLOCKER_IDENTITY_FIELD = NONE_MEASURED
CROSS_HOP_CORRELATION_BLOCKER_RETAINED_CHAIN = LEGS_3_AND_4_ABSENT
BEST_EXISTING_CORRELATION_KEY = PREVIOUS_DEVICE_PLUS_IN_PORT
FRAME_MAC_MEMBERS = DISCOVERED_NOT_MEASURED
FRAME_OBJECT_UUID = NOT_MEASURED_ON_FRAMES
RETAINED_DHCP_CHAIN_LONGEST = 2_OF_4_LEGS
CROSS_HOP_CORRELATOR_IMPLEMENTED = NO
FRAME_VLAN_QUALIFICATION_LINE = STOPPED
NEXT_ACTIVE_STEP = COMMON_VOICE_LIFECYCLE_INVESTIGATION
```

The STP drop text above is consistent with the already-recorded
`STP_BLOCKING_IN_SIMULATION = OBSERVED`; it is NOT a new root-cause proof.
`resetSimulation` changes engine state, realtime never showed VLAN20 phone ports
BLOCKING, and `PORTFAST_AS_VOICE_ROOT_CAUSE` stays `NOT_CONFIRMED`.

## Positive disposable Voice A/B -- built offline, LIVE not run

The A side exists: `qualify_positive_voice_slice.py` and the governed runner
`tools/cp_scale_positive_voice_ab_live.py`.  One 2811, one 3560-24PS, two 7960s,
voice VLAN 930, extensions 3101/3102, no PC passthrough and no redundant links.
Every mutation is an existing typed action; the wrapper orders them and journals
when each happened, and creates no primitive of its own.

The offline audit that preceded it found every component already present:

```text
VOICE_DISPOSABLE_COMPONENTS = ALL_EXISTING
NEW_MUTATION_PRIMITIVE_REQUIRED = NO
2811_SUPPORTS_CME = SUPPORTED (measured controlled probe, 9 snapshots)
2811_SUPPORTS_DHCP_SERVER = SUPPORTED (measured, 14 snapshots)
7960_IN_CATALOG = YES (pt_type 7960; measured ports PC / Switch / Vlan1)
REGISTRATION_OBSERVER = show ephone via observe_registrations
```

`show ephone` reading empty on a BARE 2811 is a property of an unconfigured
router, not a capability verdict.  The measured `supports_cme` probe writes
`telephony-service` and reads the ephone table back, and it resolves SUPPORTED.

The slice applies NO edge STP policy.  PortFast is emitted by the control-plane
stage, not by the configuration or voice paths, so a slice built from those
paths carries none.  That is deliberate: adding one would engineer the success
the experiment exists to test, and a slice that registers WITHOUT PortFast is
exactly the evidence that would weaken PortFast as the explanation.

The LIVE has since run.  It is recorded in full in the next section; the
paragraph that used to stand here said the bridge would not connect, which was
true of that session and is no longer true of the experiment.

Historical E7 stays a POSITIVE OUTCOME REFERENCE and never an exact reproducible
fixture, so the reconstructed slice must not be called the same E7 run.

## Positive disposable Voice A/B -- RUN, and it fails the same way

Three governed LIVEs, each from a clean pushed HEAD.  The first attempt of the
session did not connect to the bridge at all; a second attempt minutes later
connected with nothing else changed, so `BRIDGE_DID_NOT_CONNECT` is a transient
on this machine and not a property of the runner.

Runs 1 and 2 each exposed a defect in the harness -- not in the network -- and
each was corrected fail-first before the next run.  Run 3 is the measurement:

```text
LIVE_HEAD = 485ef137e3a1ce365022898925057872074602d9
POSITIVE_TOPOLOGY = 1x2811 + 1x3560-24PS + 2x7960, voice VLAN 930, data 931
POSITIVE_SLICE_PORTFAST = NOT_APPLIED
DATA_VLAN_READBACK = VERIFIED 2/2
VOICE_VLAN_READBACK = VERIFIED 2/2
PHONE_DHCP_ENABLED = YES 2/2 (read on Vlan930, the SVI the plan addressed)
VOICE_SVI_PRESENT = YES 2/2 (the phones DID learn the voice VLAN)
PHONE_ADDRESS_CHANNEL = PRESENT 2/2
PHONE_IPV4 = NONE 2/2 (a channel that exists answered none)
PHONE_DEVICE_IPV4 = NONE 2/2 (no address elsewhere on the phone either)
VOICE_DHCP_BINDINGS = 0 (fresh + complete `show ip dhcp binding`)
SCCP_REGISTRATION = NOT_REGISTERED 2/2
STP_BEFORE = voice-VLAN phone rows ABSENT (fresh + complete)
STP_AFTER = voice-VLAN phone rows ABSENT (fresh + complete)
POSITIVE_CONTROL_RESULT = SAME_FAILURE
CLEANUP = 4/4 removed, workspace restored, Realtime restored, 0 errors
```

The smallest Voice topology that could possibly work reproduces the CP-SCALE
Floor-1 signature exactly: DHCP enabled, no address, no binding, unregistered.
There is no scale here -- four devices, three links, one trunk, no redundant L2,
no PC passthrough, no parallel path -- so:

```text
SCALE_SPECIFIC_VOICE_FAILURE = NOT_ESTABLISHED / WEAKENED
```

The failure is in the Voice lifecycle or runtime path that both runs share, and
that is where the next investigation goes.  It is NOT in CP-SCALE's size.

What this run does NOT settle, and must not be read as settling:

* PortFast.  The positive control carried none either, so "no PortFast" is
  present on both sides and separates nothing.  `PORTFAST_AS_VOICE_ROOT_CAUSE`
  stays `NOT_CONFIRMED`, and the CASE-A branch that would have weakened it
  needed a slice that REGISTERED without PortFast.  This one did not.
* The absent voice-VLAN STP rows.  They are now measured at four devices as
  well as at CP-SCALE size, from a fresh and complete capture with the
  interface-name reconciliation the earlier code was missing.  Co-occurrence at
  both sizes is not causation:
  `VOICE_VLAN_STP_ROW_ABSENCE_CAUSAL_STATUS = NOT_ESTABLISHED_AS_CAUSE`.
* The router side.  `WHEN_DHCP_POOL_EXISTS` and the subinterface milestones are
  APPLIED, which on this architecture means DISPATCHED, not confirmed by a
  readback.  The switch-side access port WAS read back; the router's pool and
  subinterfaces were not.  "The pool existed and served nothing" is therefore
  NOT established -- only "the pool action applied and the binding table showed
  no voice binding".
* Phone power.  `WHEN_PHONE_IS_POWERED` is UNOBSERVABLE; this build publishes
  no boot surface.  The phones are not inert -- they created Vlan930 and report
  a DHCP client on it -- but powered is not something this run measured.

The two harness defects the LIVE exposed, both corrected fail-first:

```text
RUN_1_DEFECT = arming and reading the phone on `Switch`, the RJ45 the cable
    lands on.  Real port, no DHCP client, no address; every phone came back
    UNOBSERVABLE on both decisive dimensions.  A 7960 addresses on the SVI it
    creates for its voice VLAN, which is what the production compiler names
    (`_phone_addressing_interface`).  Fixed at c77ed96.
RUN_2_DEFECT = every empty address string read as UNOBSERVABLE.  The runtime
    already separates "the SVI never existed", "it exposes no address getter"
    and "it answered none"; the qualifier read none of those fields, so it
    could not reach NO even after the phone had plainly been asked.  Fixed at
    485ef13.
```

Both were harness-only and neither touched the canonical configuration, the
topology, the VLANs, PortFast, Router4 or any Packet Tracer backend semantics.
The hardening committed before the first run is what made them visible instead
of fatal: every one of these gaps read UNOBSERVABLE rather than silently
becoming the CP-SCALE signature the comparison was looking for.

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

## Two claims the run 3 journal made and had not earned

`RuntimeActionMutation.applied = True` says the runtime channel accepted a
dispatch. The lifecycle journal read that as VERIFIED, so the run 3 artefact
published the router's DHCP pool, both subinterfaces, option 150, CME, the
ephone bindings and the cnf files as verified state when not one of them had
been read back. Eight milestones, all promoted by a status expression one term
long.

`241e64b` gives a milestone the kind of evidence it rests on. APPLICATION rests
on a mutation and stops at APPLIED; only OBSERVATION, a milestone that read
something back, may reach VERIFIED; and the default is the weaker one, so a
milestone added later that forgets to say what it rests on cannot silently
claim verification. UNOBSERVABLE stays its own answer, which is still the
honest reading of phone boot state on this build. The milestone publishes its
own retained shape too -- the runner had been rebuilding that dict by hand,
which is how a distinction that exists in the model goes missing from the
artefact somebody reads months later.

The run 4 journal below reads APPLIED fourteen times and VERIFIED six, and the
six are the two Realtime reads, the acquisition window and the three new
foundation observations. Nothing about run 3's measurements changed; what
changed is that the file no longer says the router was verified.

## The whole shared foundation, finally read -- and it is not the problem

Run 4 at `824f936` is run 3's experiment with more eyes on it: same four
devices, same VLANs, same configuration, same absence of PortFast, same
everything. The only difference is that it reads the foundation both sides of
the A/B share, through surfaces this repository already governs -- the
enterprise runtime's typed trunk readback, `show ip interface brief` on the
router with the bounded per-interface read behind it, and the one call-control
table PT 9.0.1 publishes.

```text
LIVE_HEAD = 824f93665a0957b979a82fa3d21e72761ad4808e
SWITCH_TRUNK_OPERATIONAL = VERIFIED (Gi0/1, trunking)
SWITCH_TRUNK_ALLOWED_930 = VERIFIED
SWITCH_TRUNK_ACTIVE_930 = VERIFIED
SWITCH_TRUNK_FORWARDING_930 = VERIFIED
SWITCH_TRUNK_NATIVE = VERIFIED (1)
ROUTER_VOICE_SUBINTERFACE_PRESENT = VERIFIED (FastEthernet0/0.930)
ROUTER_VOICE_SUBINTERFACE_IPV4 = VERIFIED (10.93.0.1)
ROUTER_VOICE_SUBINTERFACE_STATE = VERIFIED (up/up)
CALL_CONTROL_EPHONE_TABLE = VERIFIED (fresh + complete show ephone, 2 rows)
DHCP_POOL_CONFIGURATION_READBACK = NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS
OPTION150_READBACK = NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS
PHONE_VOICE_VLAN = VERIFIED 2/2
PHONE_DHCP_ENABLED = YES 2/2
PHONE_IPV4 = NONE 2/2 (channel present, answered none)
VOICE_DHCP_BINDINGS = 0 (fresh + complete)
SCCP_REGISTRATION = NOT_REGISTERED 2/2
STP_VOICE_PHONE_ROW = ABSENT before and after
OUTCOME = SAME_FAILURE
CLEANUP = 4/4 removed, workspace restored, Realtime restored, 0 errors
```

The ordered walk, phone port outwards, stopping at the first stage that is not
VERIFIED:

```text
PHONE_ACCESS_AND_VOICE_VLAN  VERIFIED
SWITCH_TRUNK                 VERIFIED
ROUTER_VOICE_SUBINTERFACE    VERIFIED
DHCP_POOL_DEFINITION         UNOBSERVABLE   <- first boundary
CALL_CONTROL_FOUNDATION      VERIFIED
ENDPOINT_DHCP                VERIFIED
ENDPOINT_ADDRESS             CONTRADICTED   <- first contradiction
VOICE_DHCP_BINDING           CONTRADICTED
SCCP_REGISTRATION            CONTRADICTED
```

Read it carefully, because the two markers mean different things.

`FIRST_COMMON_VOICE_OBSERVABILITY_BOUNDARY = DHCP_POOL_DEFINITION /
UNOBSERVABLE` is a statement about the OBSERVER, and the label now says so:
the earlier `..._FAILURE_BOUNDARY` name invited the next reader to hear a
finding where there is only a ceiling. No registered query on `9.0.1.0858` exposes a pool
definition, `VerificationKind.DHCP_POOL` is pinned UNOBSERVABLE by its own
ceiling at `qualify_cp_scale_live.py:625`, and `show telephony-service` does not
exist on this image. The pool may be perfect. It may be absent. Nothing in this
repository can currently tell those apart, so shortening that readback to a
pool that is not there is a sentence nobody has earned -- and a handoff that
wrote it would hand the next session a root cause nobody measured.

`FIRST_CONTRADICTED_VOICE_STAGE = ENDPOINT_ADDRESS` is a statement about the
network: two phones with a voice SVI, DHCP enabled on it and a readable address
channel answered no address, and the server's binding table -- fresh, complete
-- held none.

What that pair rules out is most of the search space. Between an armed phone and
a server that hands out nothing, every hop that any governed read can reach is
verified at four devices: the access port carries voice VLAN 930, the trunk
carries 930 allowed AND active AND forwarding, the router holds
`FastEthernet0/0.930` at `10.93.0.1` with the line up/up, and the call control
answers a complete `show ephone` with a row per phone. The Voice foundation is
not where this fails.

So the two failures still are not shown to share a cause:

```text
SAME_ROOT_CAUSE = NOT_ESTABLISHED
SCALE_SPECIFIC_VOICE_FAILURE_LEVEL = WEAKENED_AT_SYMPTOM_LEVEL (not REFUTED)
```

CP-SCALE's foundation has not been read this way. Four devices sharing an
endpoint signature with 279 is a symptom-level match, and the comparison that
would make it a cause-level one needs the same ladder run against the canonical
topology. This run makes that comparison possible; it does not perform it.

Two things this run does NOT settle, unchanged from run 3:

* PortFast. Still absent on both sides, so it still separates nothing.
  `PORTFAST_AS_VOICE_ROOT_CAUSE = NOT_CONFIRMED`.
* The absent voice-VLAN STP rows. Now measured beside a trunk that IS forwarding
  VLAN 930, which makes the co-occurrence stranger and no more causal:
  `VOICE_VLAN_STP_ROW_ABSENCE_CAUSAL_STATUS = NOT_ESTABLISHED_AS_CAUSE`.

The earlier run 3 note that "the router's pool and subinterfaces were not read
back" is superseded for the SUBINTERFACES and stands for the POOL.

`NEXT_ACTIVE_STEP = DHCP_POOL_OBSERVER_ARCHITECTURE_DECISION`. The existing DORA
surface is measured unsupported on this Packet Tracer build, so the next thing
worth knowing needs a governed pool-definition observer that does not exist.
Option 150 stays secondary while the phones have no lease. Building either
observer is a new architectural decision, not a continuation -- and reaching
for `show running-config` or a raw send to get there is exactly the shortcut
this whole line of work refuses.

## PortFast, applied on purpose, and it changed nothing

Run 6 at `a2a3e27` moved the variable this branch is about. Two typed
`ConfigureStpEdgePort` actions on the two phone-facing ports, PortFast on, BPDU
Guard deliberately off, applied with zero errors. Same router, same switch, same
phones, same links, same VLANs, same subinterfaces, same pool, same option 150,
same CME, same extensions, same arming, same window.

It is NOT a strict one-variable comparison against run 4, and saying so was the
overclaim in the first draft of this section. TD-RUNTIME-004 forced the
disposable namespace from `__MCP_VOICEAB_` to `MCP-VOICEAB-` between the two
runs, so run 4 and run 6 differ by two things and only one of them was the
experiment. There is no evidence that a device name changes Voice behaviour --
and no measurement saying it does not, which is precisely the assumption a
causal A/B may not make silently about its own second variable.

```text
RUN6 = VALID_ISOLATED_PORTFAST_INTERVENTION_ATTEMPT
RUN4_VS_RUN6_SINGLE_VARIABLE = NOT_STRICTLY_ESTABLISHED
RUN4_VS_RUN6_SECOND_VARIABLE = DISPOSABLE_NAMESPACE_CHANGED
```

```text
LIVE_HEAD = a2a3e279f663539d0ff0d88be501ae2a595642d2
PORTFAST_ACTIONS = 2 (FastEthernet0/1, FastEthernet0/2)
PORTFAST_APPLIED = APPLIED (0 errors)
PORTFAST_READBACK = UNOBSERVABLE (Type column: P2p)
BPDU_GUARD = OFF
SWITCH_TRUNK = VERIFIED on all four dimensions, native 1
ROUTER_VOICE_SUBINTERFACE = VERIFIED present, 10.93.0.1, up/up
CALL_CONTROL_EPHONE_TABLE = VERIFIED (fresh + complete, 2 rows)
PHONE_DHCP_ENABLED = YES 2/2
PHONE_IPV4 = NONE 2/2
VOICE_DHCP_BINDINGS = 0
SCCP_REGISTRATION = NOT_REGISTERED 2/2
STP_BEFORE = voice-VLAN phone rows ABSENT
STP_AFTER = voice-VLAN phone rows ABSENT
OUTCOME = SAME_FAILURE
CLEANUP = 4/4 removed, workspace restored, Realtime restored, 0 errors
```

Every stage of the ordered walk sits exactly where run 4 left it, including
both markers. Nothing moved. Not one field of run 6 differs from run 4 except
the two edge actions themselves.

```text
PORTFAST_INTERVENTION_RESULT = NO_OBSERVED_EFFECT_PENDING_PAIRED_BASELINE
PORTFAST_AS_VOICE_ROOT_CAUSE = WEAKENED_PENDING_PAIRED_BASELINE
GOVERNED_EDGE_PORTFAST_MUTATION = APPLIED_NO_OBSERVED_EFFECT
FIRST_STAGE_CHANGED_FROM_RUN4 = NONE
```

Two bounds sit on that conclusion, and both are real.

The first is the readback. `PORTFAST_APPLIED` is the typed mutation being
accepted by the switch's configuration channel with no error;
`PORTFAST_RUNTIME_STATE` is UNOBSERVABLE, because the phone-facing Type column
reads `P2p` and nobody has ever measured this build printing an edge marker at
all, so a column without one cannot separate "PortFast is off" from "this IOS
does not say". What run 6 speaks to is therefore
`GOVERNED_EDGE_PORTFAST_MUTATION = APPLIED_NO_OBSERVED_EFFECT`, never a switch
demonstrably running PortFast. `PORTFAST_SUFFICIENCY_IN_DISPOSABLE_VOICE` stays
`NOT_ESTABLISHED` in both directions.

The second is the pairing, above: the namespace moved too.

What run 6 DID test is the isolated PortFast component of the known STP defect,
and it is worth being exact about how that differs from the eventual repair. The
canonical compiler emits `ConfigureSpanningTree` for the device, emits
`ConfigureStpEdgePort` only where that device participates in the STP domain,
makes the edge action depend on the global one, and takes both
`portfast_access_ports` and `bpduguard_access_ports` from policy. Run 6 emitted
no global STP action, no dependency and no BPDU Guard -- which is correct
isolation, and which is also why it is not the repair.

```text
ISOLATED_PORTFAST_COMPONENT_TESTED = YES
EXACT_CANONICAL_STP_REPAIR_TESTED = NO
```

`EDGE_STP_POLICY_STAGE_GATING_AND_ORDERING` remains a real architectural defect
and `SOURCE_DEFECT_FOUND = YES` stands.

The absent voice-VLAN STP rows survive the intervention unchanged, which is
worth stating precisely: the phone ports never joined VLAN 930's spanning tree
before PortFast and they still do not after it. Co-occurrence at three sizes and
across an intervention is still not causation, and
`VOICE_VLAN_STP_ROW_ABSENCE_CAUSAL_STATUS = NOT_ESTABLISHED_AS_CAUSE`.

`NEXT_ACTIVE_STEP` does not change: the pool definition and option 150 are still
the only things in the chain nobody can read, and reading them still needs an
observer that does not exist.

## The paired baseline, and the branch closes

Run 7 at `c9d6ead` is run 6's paired network baseline, but the two runs did not
use the same code revision: run 6 used `a2a3e27`. The audited source diff between
them changes only the post-acquisition edge-marker classifier and its evidence
serialization. It does not change the topology, VLANs, trunk, router
subinterfaces, DHCP-pool or option-150 intent, CME, endpoint DHCP arming,
acquisition window, or PortFast mutation path.

Both runs use the `MCP-VOICEAB-` namespace and the same Voice configuration.
Run 7 sets `edge_portfast=False`; run 6 carries the intended PortFast dispatch.
Their network outcomes match across every foundation dimension, every phone
field, both ladder markers, the binding count, the STP rows and the final outcome:

```text
portfast:  APPLIED  ->  NOT_APPLIED
lifecycle: run 6 carries WHEN_EDGE_PORTFAST_APPLIED; run 7 does not
```

```text
PAIRED_BASELINE_MATCH = YES
PAIRED_NETWORK_OUTCOME_MATCH = YES
RUN6_VS_RUN7_SAME_CODE_REVISION = NO
RUN6_VS_RUN7_SAME_NETWORK_MUTATION_PATH = YES
RUN6_VS_RUN7_SAME_VOICE_CONFIGURATION = YES
RUN6_VS_RUN7_OBSERVER_DIFFERENCE = EDGE_MARKER_CLASSIFIER_FIX_ONLY
FIRST_STAGE_CHANGED_BETWEEN_PAIRED_RUNS = NONE
GOVERNED_EDGE_PORTFAST_DISPATCH_EFFECT = NO_OBSERVED_EFFECT
PORTFAST_INTERVENTION_RESULT = NO_EFFECT
PORTFAST_AS_VOICE_ROOT_CAUSE = STRONGLY_WEAKENED_FOR_GOVERNED_DISPATCH
```

Run 7 settles the second variable as well. It matches run 4 -- the old
`__MCP_VOICEAB_` namespace, also without PortFast -- on every decisive field,
so `DISPOSABLE_NAMESPACE_EFFECT = NONE_OBSERVED` and the pairing objection
against run 6 is answered by measurement rather than by assumption.

What stays unresolved is stated as plainly as what closed. `PORTFAST_RUNTIME_
STATE` is still UNOBSERVABLE: both runs print `P2p` in the phone-facing Type
column and this build has never been measured printing an edge marker at all.
So the finding is about the DISPATCH -- applying the governed edge policy
changes nothing observable -- and not about a switch demonstrably running
PortFast. `PORTFAST_SUFFICIENCY_IN_DISPOSABLE_VOICE` stays `NOT_ESTABLISHED`:
neither a refutation of PortFast nor a verified runtime state has been earned,
and writing either would be the promotion this pair was built to avoid.

```text
PORTFAST_CAUSAL_BRANCH = CLOSED_FOR_NOW
```

Closed, not answered. `EDGE_STP_POLICY_STAGE_GATING_AND_ORDERING` is still a
real architectural defect and `SOURCE_DEFECT_FOUND = YES` stands; what this pair
removes is its standing as the explanation for THIS Voice DHCP failure. The
eventual repair remains untested -- the canonical compiler couples the edge
action to a global STP action and takes both policy flags, and run 6 emitted
neither coupling on purpose.

The absent voice-VLAN phone rows are ABSENT in both halves, which is one more
size and one more intervention of co-occurrence and still not causation:
`VOICE_VLAN_STP_ROW_ABSENCE_CAUSAL_STATUS = NOT_ESTABLISHED_AS_CAUSE`.

`NEXT_ACTIVE_STEP = DHCP_POOL_OBSERVER_ARCHITECTURE_DECISION`. The existing
governed DORA query is already measured unsupported on this Packet Tracer build,
so it must not be rerun. Pool-definition observation is the next architectural
checkpoint; option 150 remains secondary while the phones have no lease. Neither
observer was started here.

## Run 5, the intervention that never happened

Run 5 asked for PortFast at `819d8f8` and did not get it. Both edge mutations
came back `Invalid compiled device name`, so `portfast` read NOT_APPLIED and the
run was run 4 repeated -- a baseline wearing an experiment's name. The guard
that made this visible rather than fatal is the same one everywhere else here:
the refusal reached the evidence and nothing claimed an intervention that had
not happened.

The cause is TD-RUNTIME-004 met from the other side. Two disposable namespaces
exist on purpose: `__MCP_*` for objects that never pass the typed control-plane
renderer, and `MCP-*` for objects that must, because that renderer's allowlist
requires an alphanumeric first character. The resolution on record is a
compatible namespace and explicitly NOT a relaxed validator; the contract that
keeps anyone from widening it is still green. The Voice slice moved to
`MCP-VOICEAB-`. Cleanup was never involved: it tracks the objects it created,
not a string.

Run 5 is filed as the boundary it was rather than the intervention it asked to
be, and it did measure one thing worth keeping: the phone-facing Type column
reads `P2p` with no edge marker while PortFast is definitely absent, which is
the before half of a readback whose after half looks identical.

## Preserving the raw runs

Four governed Voice A/B LIVEs have produced four raw journals, and they live
under ignored `data/` because that is where this repository keeps generated
runtime evidence. The cost is identity: `positive-voice-ab.json` is overwritten
by every LIVE, so a measurement that is not archived under a unique name and
pinned by digest stops existing the moment the next run starts.

`docs/reference/cp-scale/positive_voice_ab_runs.json` is the tracked record, in
the shape `live_canonical_checkpoint.json` already set. It names each ignored
artefact, pins its SHA-256, and says HOW its source head is known -- run 3's and
run 4's were written down live, while runs 1 and 2 were recovered afterwards by
bracketing the artefact's mtime between two commit timestamps, which is a weaker
kind of knowing and says so.

```text
run1  0d92e12f...  4ddf2d3  HARNESS_BOUNDARY_WRONG_PHONE_ADDRESSING_INTERFACE
run2  85fd0a24...  c77ed96  HARNESS_BOUNDARY_EMPTY_ADDRESS_SEMANTICS
run3  d0b3d885...  485ef13  AUTHORITATIVE_SAME_FAILURE_MEASUREMENT
run4  ba6b1ad6...  824f936  FOUNDATION_QUALIFICATION_MEASUREMENT
run5  bfc217f7...  819d8f8  HARNESS_BOUNDARY_EDGE_ACTION_NAME_REJECTED
run6  ca36d99e...  a2a3e27  PORTFAST_ONLY_CAUSAL_INTERVENTION
run7  aeaf13ed...  c9d6ead  CURRENT_NAMESPACE_NO_PORTFAST_PAIRED_BASELINE
```

`tools/cp_scale_voice_ab_ledger.py --archive --run runN ...` archives the
canonical file to a unique name and records it; it computes every digest itself
and refuses to archive over a run that already exists. `--verify` re-hashes
whatever survives locally. Run it after every Voice A/B LIVE, before anything
else touches `data/`. Never `git clean -fdx` during this investigation.

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
LATEST_FRAME_VLAN_CALIBRATION_LIVE_HEAD
                             the source the last frame/trunk VLAN calibration
                             ran from. Moves independently of both others.
LATEST_VOICE_AB_LIVE_HEAD    the source the last disposable Voice A/B ran from.
                             It is NOT the frame calibration head; one name for
                             both let a Voice run overwrite the record of a
                             calibration it had nothing to do with.
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

## The pool is there, it has room, and the phones still have no address

`show ip dhcp pool` was qualified as supported on this build at `ce222ed`, then
promoted to a registered operational query at `92e115c` and wired into the A/B
adapter at `91927d9`. Run 8 is run 7's configuration exactly -- the
`MCP-VOICEAB-` namespace, one 2811, one 3560, two 7960s, voice VLAN 930, data
VLAN 931, `edge_portfast=False`, Realtime only -- with ONE new READ-ONLY
dimension and no other causal variable moved.

The table parsed on the first read. No boundary capture was written, which is
the recorded way of saying the parser built from the qualification fixture also
holds on the Voice router:

```text
DHCP_POOL_NAME = VOICEAB_VOICE
DHCP_POOL_RANGE = 10.93.0.1 - 10.93.0.254
DHCP_POOL_TOTAL = 254
DHCP_POOL_LEASED = 0
DHCP_POOL_EXCLUDED_COUNT = 1
DHCP_POOL_AVAILABLE = 253
DHCP_POOL_EXISTENCE_READBACK = VERIFIED
DHCP_POOL_RANGE_READBACK = VERIFIED
DHCP_POOL_AVAILABLE_SPACE_READBACK = VERIFIED
DHCP_POOL_BOUNDARY_CAPTURES = 0
```

Three dimensions were kept apart on purpose, because presence does not prove the
intended range and a matching range does not prove any address is left. All
three answered, and they answered well. Meanwhile nothing downstream moved:

```text
PHONE_DHCP_ENABLED = YES
PHONE_IPV4 = NONE
VOICE_DHCP_BINDINGS = 0
SCCP_REGISTRATION = NOT_REGISTERED
OUTCOME = SAME_FAILURE
```

So this is CASE A. Two candidate causes go down at once:

```text
POOL_EXISTENCE_CAUSE = WEAKENED
POOL_EXHAUSTION_CAUSE = REFUTED_FOR_THIS_DISPOSABLE
```

The boundary moved downstream. Before run 8 the pool stage was the first
non-VERIFIED stage in the ladder and it was UNOBSERVABLE -- an observer ceiling,
not a finding. Now every stage from the phone access port through the trunk, the
router subinterface, the pool table, call control and endpoint DHCP arming reads
VERIFIED, and the first stage that is not is `ENDPOINT_ADDRESS`, CONTRADICTED.
That is a measurement, not a ceiling. The next question is the DHCP transaction
and the path it takes, not the server-side pool.

What this evidence does NOT establish is stated as plainly. The measured table
prints an excluded COUNT and never the excluded ranges, so `1` against a
configured `10.93.0.1-10.93.0.9` exclusion is an unresolved reading, not a
finding about the configuration -- it is equally consistent with PT counting
ranges and with only one address being excluded, and this run cannot separate
them. Default-router and option 150 are not on this surface at all:

```text
DHCP_POOL_DEFAULT_ROUTER_READBACK = NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS
DHCP_POOL_EXCLUSIONS_READBACK = NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS
OPTION150_READBACK = NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS
```

Option 150 stays secondary. While `PHONE_IPV4 = NONE` the phones never reach the
stage where a TFTP option would matter, so promoting it now would be chasing the
symptom furthest downstream -- the same mistake the ladder exists to prevent.

The ladder stage is called `DHCP_POOL_TABLE_READBACK`, not
`DHCP_POOL_DEFINITION`. VERIFIED there means the pool exists, its range covers
the intended lease window and addresses remain. It does not mean the pool is
configured correctly, and the rename is what stops a later session reading it
that way.

Run 8 is archived as `positive-voice-ab-run8-measured-dhcp-pool-readback.json`,
SHA-256 `7f508ad8e9e337237d721672beef9b180cb6cf1bee0f20d13b5dff62fd449889`, source
head `91927d9`. Cleanup was clean: the workspace was restored, Realtime was
restored, and the run reported no errors.

## Run 9 -- the access-VLAN paired control, and what it split apart

The strongest post-run-8 candidate was a property of the phone-facing access
port SHAPE: with `access 931` + `voice 930` every fresh+complete realtime STP
capture -- disposable runs 3 through 8 and the CP-SCALE CASE-D VLAN20 capture
alike -- lists the port only under its data VLAN, and the one simulation
window that ever saw a phone's Discover saw the switch drop it at that port.
Run 9 tested that shape causally, as a SAME-RUN two-phone A/B so both halves
shared one Packet Tracer session, one switch, one trunk, one pool, one CME and
one acquisition window: the control phone kept `access 931 / voice 930`
exactly as run 8, and the intervention phone's port carried
`access 930 / voice 930`.  One variable, inside one run.

The qualifier gained `phone_access_vlans` -- one access VLAN per phone,
refused unless it names every phone exactly once and uses only the two VLANs
the slice itself creates -- and each port's readback is now judged against ITS
OWN intent, which travels into the adapter's `verify` expectation and comes
back retained as `access_vlan_expected`.  Judging the intervention port
against the shared data-VLAN constant would have manufactured a CONTRADICTED
reading on a switch that did exactly what it was asked.  The default mapping
is pinned byte-for-byte to the run-8 shape by the same tests that pin the
paired one.

The primary metric did not move, and the secondary one did:

```text
CONTROL      Fa0/1 access 931 / voice 930: access+voice readback VERIFIED,
             Vlan930 SVI present, DHCP on, IPV4 NONE, NOT_REGISTERED,
             VLAN0930 STP row ABSENT before AND after -- runs 3-8 exactly
INTERVENTION Fa0/2 access 930 / voice 930: access+voice readback VERIFIED,
             Vlan930 SVI present, DHCP on, IPV4 NONE, NOT_REGISTERED,
             VLAN0930 STP row LIS before the window, LRN after it
SHARED       trunk VERIFIED on all five dimensions, Fa0/0.930 up/up at
             10.93.0.1, pool 254/0 leased/253 free, ephone table fresh and
             complete with 2 rows, 0 errors, workspace and Realtime restored
```

So the run is PARTIAL_OR_DIVERGENT, and deliberately not forced into either
clean case.  What it establishes: the access-VLAN shape CONTROLS voice-VLAN
spanning-tree membership on this build.  The moment the access VLAN equals the
voice VLAN the port enters the VLAN0930 instance -- something no distinct-VLAN
run ever showed -- which is measured, mechanical support for the shape
hypothesis at the representation layer.  What it does NOT establish: any DHCP
effect.  Both phones ended the window without an address, so
`PAIRED_ACCESS_VLAN_DHCP_EFFECT = NOT_OBSERVED_WITHIN_WINDOW`.

The reason the DHCP question stayed open is itself the run's sharpest finding:
the intervention port was read `LIS` immediately before the acquisition window
and `LRN` immediately after it.  Forwarding was never OBSERVED at either
qualified read, so the intervention half was never SEEN past convergence while
the phones were being judged.  Two snapshots do not prove every intermediate
state: that the port never reached FWD at some unread moment inside the window
is NOT established, and the corrected claims are exactly
`INTERVENTION_FWD_OBSERVED_RUN9 = NO` and
`INTERVENTION_NEVER_FWD_DURING_RUN9 = NOT_ESTABLISHED`.  A port that is
LEARNING drops data frames by design, on real IOS and in PT alike -- at the
two instants it was read.  That also retroactively sharpens the
control side's meaning: ABSENT and never-converging are different starting
states, and only run 9 has ever shown a phone port converging INTO the voice
VLAN at all.

Two mandated corrections from the independent audit are recorded beside this,
because run 9's evidence obeys both: zero bindings prove NO LEASE, never that
no Discover reached the server, so `SERVER_RECEIVES_DISCOVER = UNOBSERVABLE`;
and an STP table row -- present, absent, or converging -- is a representation,
not a measured data plane, so
`VOICE_VLAN_REALTIME_DATA_PLANE_FORWARDING = NOT_ESTABLISHED`.

The next step names itself: give the intervention shape an OBSERVED-forwarding
port before judging acquisition.  That step is now built and named
`RUN10_PAIRED_ACCESS_VLAN_FWD_GATED_ACQUISITION`; its design is the next
section's subject.  Natural convergence is the chosen lever -- PortFast would
be a second variable riding on an already-changed membership -- and the
criterion is a qualified read observing FWD, never elapsed time.

Run 9 is archived as
`positive-voice-ab-run9-paired-access-vlan-stp-divergence.json`, SHA-256
`44e9886286207ec5c1b92c13f10790d34fabfe6991e0ad5ae8a6cb476c8d5086`, source
head `c7fefb0`.  Cleanup was clean: the workspace was restored, Realtime was
restored, and the run reported no errors.

## Run 10 prepared -- the FWD-gated fresh-DHCP paired control, not yet run

Before any reordering, the fresh-DHCP trigger semantics were audited across
the qualifier, the endpoint protocol, `PacketTracerConfigurationRuntime`, the
bridge helper, the voice runtime's observation path, the historical E7 tools
and the debt ledger.  What that audit established, classification by
classification:

```text
NEW_7960_DHCP_INITIAL_STATE = UNOBSERVED_TO_DATE -- no run and no probe has
    ever read the flag BEFORE arming; every YES on record is post-arm
PRE_ARM_READ_SURFACE = SOURCE_SUPPORTED_NOT_MEASURED -- the voice runtime's
    per-phone SVI read (the registration pass's own) is now callable
    standalone as observe_endpoint; the read itself is the measured surface
    every run 3-9 used, invoked at a moment it was never invoked before
OFF_TO_ON_TRANSITION = MEASURED_SUPPORTED on a PC-class endpoint (the DHCP
    capability probe observes a fresh lease); SOURCE_SUPPORTED_NOT_MEASURED
    on the 7960
ON_TO_ON_RETRY = UNOBSERVABLE -- no measured evidence anywhere that repeating
    setDhcpFlag(true) creates a fresh attempt; never assumed
DISABLE/RENEW/RESTART/REBOOT/POWER/LINK_BOUNCE = NOT_AVAILABLE for this
    experiment -- the typed disposable runtime has none of them, and adding a
    power/reboot mutation is a checkpoint decision, not a workaround
FRESH_DHCP_TRIGGER = NOT_ESTABLISHED_BEFORE_RUN10; the run can establish the
    phone's DHCP FLAG OFF-to-ON transition, and refuses to interpret DHCP when
    it cannot
FRESH_7960_DHCP_TRANSACTION = NOT_INDEPENDENTLY_ESTABLISHED -- neither the
    typed call's acceptance nor the flag transition observes Discover, Offer,
    Request or Ack
```

The run-10 mode encodes that audit as sequence.  After the network and Voice
foundations are applied and Realtime is verified, a bounded gate polls the
SAME qualified `show spanning-tree` read -- 60 s budget, 2 s interval,
monotonic clock, no new observer -- until a fresh+complete capture shows the
intervention port FORWARDING in VLAN0930 and the existing IOS result attributes
the source as `CONFIRMED_UNIQUE`.  LIS, LRN, BLK and ABSENT keep the poll alive
and expire as TIMEOUT, which is never promoted to never-forwards; an unreadable,
unattributed, ambiguous or mismatched capture ends the gate UNOBSERVABLE
immediately, so no decision ever rides on a stale sample.  The observed
classifications are retained with adjacent repeats collapsed -- run 9's
`ABSENT/LIS/LRN` lesson, kept cheap.

Only after the gate observes FWD is the flag-transition precondition measured:
every phone's DHCP flag is read on its own SVI immediately before the arming call.
All-NO authorizes one existing typed arm batch.  Every call must return exactly
True, and every post-arm flag must then read YES, before the window opens.  The
three facts remain per phone as `dhcp_enabled_pre_arm`, `arm_call_accepted` and
`dhcp_enabled_post_arm`; diagnostic post-arm reads are retained after a refused
or partial batch, but can never reopen the window.  There is no retry and no
second mutation.  A flag already ON, an unreadable flag, any rejected arm, or
anything short of all post-arm YES fails closed as
`ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN`; a gate that never saw an
authoritative FWD fails closed as
`ACQUISITION_NOT_STARTED_STP_PRECONDITION_UNMET`.  No acquisition window means
no endpoint failure verdict: the outcome reads UNOBSERVABLE rather than another
ambiguous SAME_FAILURE.

The successful PRE-NO / accepted / POST-YES contract is published as
`dhcp_flag_transition = OBSERVED_OFF_TO_ON` and
`dhcp_flag_transition_valid_for_experiment = YES`.  It is not promoted into a
7960 transaction claim: `fresh_7960_dhcp_transaction` remains
`NOT_INDEPENDENTLY_ESTABLISHED`, while `server_receives_discover` and
`dhcp_transaction_progress` remain UNOBSERVABLE.

Run 9's two result concepts are now two fields everywhere: the VOICE endpoint
outcome keeps its meaning, and `causal_experiment_result` answers the gated
experiment alone -- the two boundaries above, then per the decision matrix
`ACCESS_VLAN_DHCP_CAUSAL_EFFECT_OBSERVED` for the strong control-NONE /
intervention-OBSERVED positive, or the deliberately asymmetric
`NO_ADDRESS_AFTER_FWD_AND_DHCP_FLAG_TRANSITION` when neither phone obtains an
address.  That negative means causal effect NOT OBSERVED and the access-VLAN
hypothesis NOT YET ESTABLISHED; it cannot prove a fresh 7960 transaction and
therefore cannot refute or strongly weaken the hypothesis.  Both addresses
remain `RUN9_FAILURE_NOT_REPRODUCED`, the reversed half is
`OBSERVED_REVERSED_ADDRESS_OUTCOME`, and an unreadable half remains
`PARTIAL_OR_DIVERGENT`.  Ungated runs answer NOT_FWD_GATED, because without the
gate the premises the verdict rests on are exactly what run 9 could not prove.

Two run-9 evidence defects are corrected beside this.  The paired lifecycle
journal wrote `data vlan 931` for both ports -- false for the intervention
port the moment the experiment existed -- and now records the actual per-port
intent, `FastEthernet0/1:931, FastEthernet0/2:930`, with the uniform baseline
keeping its own exact shape.  And the run-9 wording that promoted two
snapshots into "never reached forwarding during the entire window" is
corrected in place and in the ledger note: FWD_OBSERVED = NO is the
measurement; NEVER_FWD is NOT_ESTABLISHED.

The runner exposes the mode as `--paired-access-vlan-fwd-gated`, mutually
exclusive with every other intervention flag.  The A/B itself is untouched --
same ports, same VLANs, same pool, same CME, same extensions, no PortFast, no
new mutation primitive -- and the default and run-9 paired behaviours are
pinned unchanged by the same contracts that pin the new mode.  Packet Tracer
was not run.  The pushed result of `git rev-parse HEAD`, not a self-referential
documentation pin, is the source head for exactly one next LIVE.

## Run 10 LIVE -- STP precondition not established

Exactly one governed LIVE ran from clean pushed source head
`d7a43778b377dbf7f83e214d7cd390fb34309360` on Packet Tracer `9.0.1.0858`.
The mutating process proved the checkout-local interpreter, the package inside
this worktree, and only the production import namespace before it connected.
The read-only baseline was Realtime with zero semantic devices and zero links.
The experiment remained the prepared pair: control `FastEthernet0/1` access
931 / voice 930, intervention `FastEthernet0/2` access 930 / voice 930, natural
convergence, no PortFast and no BPDU Guard.

The intervention VLAN930 gate retained `LIS -> LRN -> UNOBSERVABLE` across 11
samples and 21,844 ms.  It never established the full executed + fresh +
complete + `CONFIRMED_UNIQUE` contract together with FWD.  The retained gate
evidence does not distinguish which required read dimension failed in the
terminal sample, so identity itself remains NOT ESTABLISHED rather than being
guessed.  The governed result is `STP_PRECONDITION_NOT_ESTABLISHED`, with
boundary `ACQUISITION_NOT_STARTED_STP_PRECONDITION_UNMET`.

The fail-closed consequence is the experiment result, not a harness retry:
there were no PRE-arm flag reads, no arm calls, no POST-arm reads, no
acquisition window and therefore no per-phone IPv4 or SCCP verdict.  The later
read-only surfaces reported zero voice bindings, but that is not DHCP causal
evidence when acquisition never started.  `FRESH_7960_DHCP_TRANSACTION` stays
`NOT_INDEPENDENTLY_ESTABLISHED`; server Discover and transaction progress stay
UNOBSERVABLE; `ACCESS_VLAN_SHAPE_CONTROLS_DHCP` stays NOT YET ESTABLISHED.

Cleanup reported zero errors, restored Realtime, and restored the empty
semantic workspace.  An independent post-read observed zero semantic devices,
zero links and one allowed backend-managed PDD.  There was no automatic rerun.
The unique archive is
`positive-voice-ab-run10-stp-precondition-unobservable.json`, SHA-256
`6c128bae161cb41bf5c879ac7fde14aaad9750e1d5922aa256dfbcd0bd5c3297`;
the tracked ledger records provenance only.

## Run 11 LIVE -- authoritative FWD, fresh DHCP trigger unproven

Exactly one governed LIVE ran from clean pushed source head
`8ecee845c0553ae25e4e82d965671e98cf135bf3` on Packet Tracer
`9.0.1.0858`.  The mutating process proved the checkout-local interpreter,
the package inside this worktree and only the production import namespace.
The read-only preflight observed Realtime, zero semantic devices and zero
links.

The intervention VLAN930 gate retained `LIS -> LRN -> UNOBSERVABLE -> LRN ->
UNOBSERVABLE -> FORWARDING` across 15 samples and 30,327 ms.  Both unreadable
transitions failed only the `COMPLETENESS` dimension; polling continued, and
the terminal sample was executed, fresh, complete, uniquely attributed and
FORWARDING.  This establishes the prepared network-forwarding precondition
for the intervention in RUN11 without rewriting RUN10's earlier boundary.

Independently, the authoritative shared-trunk read observed interface
`Gig0/1`, status `trunking`, native VLAN 1, and allowed, active and IOS
forwarding/not-pruned tuples all equal to `(930, 931)`.  This exact uplink
membership remains a separate IOS surface from the phone-port STP state.

After FWD, both phone DHCP PRE reads were `YES`, not the required `NO`.
Therefore no DHCP arm call was issued, no POST read was taken and no
acquisition window opened.  The result is `FRESH_DHCP_TRIGGER_UNPROVEN` with
boundary `ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN`.  The later
read-only endpoint surface observed no IPv4 on either phone, zero voice DHCP
bindings and unobservable SCCP registration, but none is a DHCP causal outcome
because acquisition never started.  `FRESH_7960_DHCP_TRANSACTION` remains
`NOT_INDEPENDENTLY_ESTABLISHED`; server Discover and transaction progress
remain UNOBSERVABLE; `ACCESS_VLAN_SHAPE_CONTROLS_DHCP` remains NOT YET
ESTABLISHED.

Cleanup reported zero errors and restored Realtime and the empty semantic
workspace; an independent post-read confirmed zero semantic devices and zero
links.  No rerun occurred.  The unique archive is
`positive-voice-ab-run11-fresh-dhcp-trigger-unproven.json`, SHA-256
`8619852a1b405a4191067abefc453d4ccfc14cd28f3702521dd87a981b349a82`;
the tracked ledger records its source provenance.

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
