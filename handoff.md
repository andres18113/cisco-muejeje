# CP-SCALE continuation handoff

## Resume identity and hard boundaries

```text
BRANCH = feature/runtime-ripv2
UPSTREAM = personal/feature/runtime-ripv2
PACKET_TRACER_BUILD = 9.0.1.0858
CURRENT_PUSHED_HEAD = 4b9fe11c54001d6f1713831e52814deb94078918
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
WORLD_B_DHCP_BINDINGS = OBSERVED at 4b9fe11: DATA 23, VOICE 0, CCTV 0
DHCP_EXCHANGE_STATISTICS = implemented, NOT COMMITTED, LIVE pending
PT_SCOPED_STATISTICS_SUPPORT = UNVERIFIED_UNTIL_LIVE
CP_SCALE = OPEN
E10 = FORBIDDEN
```

Offline baseline at pushed HEAD `4b9fe11`: **2725 passed / 0 failed** with the
checkout-local `.venv` and a writable, gitignored pytest basetemp. The scoped
DHCP-exchange work below adds eight tests and runs at **2733 passed / 0 failed**
in the same checkout. The latest failed Floor-1 run cleaned every owned device
and independently re-observed the empty semantic workspace twice. Packet Tracer
is open; its workspace is empty.

The DHCP-binding observation is checkpointed in this HEAD and has since produced
its LIVE reading. The scoped DHCP-exchange statistics described below are NOT
checkpointed; commit and push them before the next LIVE mutation.

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

## NEXT_ACTIVE_STEP

1. Commit/push the scoped DHCP-exchange observation on a clean exact upstream
   HEAD. Files: `ios_terminal.py`, `tools/cp_scale_canonical_live.py`, the two
   test modules, and this handoff.
2. Re-run governed routing-core -> router4-switch10 -> Floor 1 from that exact
   committed HEAD, without stopping a stage mid-flight or creating progress
   commits.
3. Read `dhcp_voice_statistics_baseline` from the router4-switch10 stage and
   `dhcp_voice_exchange` from the durable Floor-1 failed-stage journal. Answer
   the support question FIRST: if `usable` is false at either point, PT does not
   expose this observation and the fork stays where `4b9fe11` left it.
4. If `scope_discriminated` is false, the reading was the server's, not the
   interface's. Do not interpret its numbers.
5. Only a readable, scope-discriminated delta names a fork, and it names exactly
   one step of the exchange -- not a cause.

Do not wire any new DHCP observation into `VerificationKind.DHCP_POOL`: the
ceiling at `qualify_cp_scale_live.py:625` enforces status UNOBSERVABLE +
`fresh_evidence` False + evidence_method `runtime_observability_limit` + every
field UNOBSERVABLE. New observations must be additive or the governed gate
rejects them.

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
```

The scoped DHCP-exchange observation and this handoff update are the next fix
checkpoint; record their final pushed HEAD here on the following turn.
