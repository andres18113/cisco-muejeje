# CP-SCALE continuation handoff

## Resume identity and hard boundaries

```text
BRANCH = feature/runtime-ripv2
UPSTREAM = personal/feature/runtime-ripv2
PACKET_TRACER_BUILD = 9.0.1.0858
HEAD = 32df973 (pushed)
ROUTING_CORE = GOVERNED VERIFIED (re-materialized twice this session)
ROUTER4_SWITCH10 = GOVERNED VERIFIED (re-materialized twice this session)
FLOOR1_PHYSICAL = VERIFIED (74 devices / 55 links / 3 modules, 132/132 observed)
FLOOR1_CONFIGURATION = VERIFIED (acceptance error empty, zero contradictions)
FLOOR1_VOICE = APPLIED, NOT VERIFIED
FLOOR1 = NOT VERIFIED
CP_SCALE = OPEN
E10 = FORBIDDEN
```

No live run is active. The last run's cleanup restored the workspace and it was
independently re-observed: semantic 0 devices / 0 links,
`safe_for_disposable_mutation: True`. Only backend-managed `Power Distribution
Device` objects remain, which the governed restoration check ignores.

Offline: **2682 passed**, no failures.

## Operational: the extension stops polling after every run

This is not a defect in the product and it will cost a retry every time if it is
not anticipated.

`tools/cp_scale_canonical_live.py` uses the authenticated HTTP bridge
(`PacketTracerHttpTransport`, loopback `127.0.0.1:54321`). **Every time a run
ends and its transport disconnects, the MCP BUILDER extension stops polling and
does not resume on its own.** The next run then hard-stops on
`"Authenticated Packet Tracer HTTP bridge did not obtain fresh polling"`.

Diagnose it, do not guess:

```bash
PYTHONPATH=src .venv/Scripts/python.exe -c \
  "from packet_tracer_mcp.infrastructure.execution.live_bridge import PacketTracerHttpTransport as T; \
   t=T(); print('connected:', t.start(timeout_seconds=15.0)); print(t.status_dict()); t.stop()"
```

* `last_poll_ago: None` **and** `unauth_count: 0` -> the extension is making no
  requests at all. Re-enable MCP BUILDER in Packet Tracer. Waiting does not help:
  it was probed twice for 25s with zero requests.
* `unauth_count > 0` -> a token mismatch instead. The shared token lives at
  `%LOCALAPPDATA%\packet-tracer-mcp\bridge_token` and is stable; compare
  `token_id` across runs before touching it.

The previous handoff described this as "usually transient". On this session it
was never transient. Note also that the **file bridge stays alive** while the
HTTP one is dead -- the two channels are independent, so `FileBridge().pt_alive()`
returning True says nothing about whether a governed run can start. Do not
repoint the runner at the file bridge to get past it: the authenticated channel
is the gate that makes a LIVE stage trustworthy.

## What this session closed

### 1. The 21 x 7960 contradiction -- ROOT-CAUSED AND FIXED

One mistaken premise, that a phone is an endpoint E5 addresses, failing on
measured behaviour in two independent ways.

Measured on 9.0.1.0858: a 7960 enumerates exactly `PC`, `Switch` and `Vlan1`.
Once its access port signals a voice VLAN the phone itself brings up
`Vlan<voice>` -- powered, up, protocol up -- and takes `Vlan1` down. So `Vlan1`
is the one interface guaranteed to hold no address, and the `Vlan20` that
replaces it does not exist when E5 is preflighted against the live inventory:
naming it fails target validation instead of verifying.

E5 now claims no addressing for a phone on a voice VLAN, exactly as it already
claims none for a wireless endpoint with no network port. Everything the phone
needs from E5 -- VLAN, voice access port, gateway, DHCP pool -- is still
compiled, and the pool survives its only client ceasing to be one this plan
configures. E7 owns the claim and verifies it two ways that must agree: what
`show ephone` reports the phone registered from, and what the phone reports on
the SVI it created.

Canonical configuration actions **514 -> 445**. Confirmed live: Floor-1
configuration acceptance error is now empty with zero contradictions.

### 2. Voice was unstageable -- TWO CIRCULAR GATES REMOVED

`VoiceApplicator` refused to run until the phone's addressing read back
VERIFIED, while that acquisition could only happen after the actions it was
refusing to apply. `phone_addressing` is now a foundation only where E5 really
did address the phone first.

The second gate only appeared once the first was gone: the plan also required
the **DHCP pool** foundation to be VERIFIED, and `VerificationKind.DHCP_POOL` is
answered UNOBSERVABLE unconditionally -- Packet Tracer exposes no pool getter.
That is not fail-closed but fail-impossible. `_ADMISSIBLE_FOUNDATION_STATUSES`
now names what evidence each foundation kind may rest on; VERIFIED remains the
rule wherever the backend has a read-back, and a voice VLAN foundation that
comes back UNOBSERVABLE still blocks.

### 3. Voice staged in the LIVE pipeline

`_execute_stage` applies E7 between foundational evidence and the control plane:
foundation -> option 150 + call control + extensions + bindings + cnf-files ->
acquisition -> registration -> fresh verification. Voice is compiled **per
stage**, because E7 binds the exact E4/E5 hashes it is applied against.

Confirmed live: Floor 1 applied **all 47 voice actions, zero refused**.

### 4. `supports_cme` -- MEASURED

Voice capability profiles read measured `DeviceCapabilities`, never a model
name. `_probe_cme` is a controlled configure/read-back on a disposable router: a
one-ephone `telephony-service` bound to a routed source address, an `ephone-dn`,
an `ephone`, then `show ephone`. It uses `show ephone` and not
`show telephony-service`, which exact-build evidence already recorded as absent.

```text
2811 supports_cme = SUPPORTED, verified (measured twice this session)
```

Prequalification derives it for every model hosting a call control, so the
existing "SUPPORTED after composition or hard stop" gate covers voice.

### 5. AccessPoint-PT -- NOT IP-ADDRESSABLE

Bounded exact-build probe, retained at `data/cp-scale/ap-addressability/`. An
AccessPoint-PT beside a PC-PT carrying an identical static claim on an identical
powered access port. The PC leased `172.31.10.2` and verified. The AP came up on
both `Port 0` and `Port 1`, up and powered, and exposed `getIpAddress`,
`setIpAddress`, `getSubnetMask`, `getDefaultGateway` and `isDhcpEnabled` as
`undefined` -- at device level and on both ports, before and after addressing.
It bridges; it does not host. It has no separate management interface.

Two fixes followed. The read-back already promised "a named interface that
cannot be found **or cannot expose an address** is UNOBSERVABLE, never FAILED"
and implemented only the first half -- the JS flag answering the second was
overwritten by the match result one line later. And the governed ceiling then
rejected the honest answer, so an absent address channel is now its own ceiling,
keyed on evidence method `structured_endpoint_getters_absent` so that an
interface which was never found still fails.

Confirmed live: the 3 APs read back UNOBSERVABLE and Floor 1 accepted them.

### 6. Three observation defects -- FIXED, NOT YET RE-RUN

Found by the first run that reached voice. All three are about reporting, not
provisioning, and together they made one misleading picture:

* `show ephone` **pages at 21 ephones**. Each phone's observation issues its own
  read and each captured a different scattered window -- extensions 3011, 3016,
  3020, 3021 matched, the other seventeen were reported as having no
  registration table at all. `IosCommandResult.output_complete` exists exactly
  for this and `inspect_call_control` was discarding it. Completeness now travels
  with the capture, and a truncated read that misses a row says so
  (`show_ephone_capture_incomplete`) instead of claiming the row is absent.
* The four rows that parsed reported `IP:0.0.0.0` -- a call control stating it
  has **no** address. Carried forward as an address it failed the segment check
  as "0.0.0.0 is outside the voice segment", a contradiction manufactured out of
  an absence, and the literal reason the stage failed. Both channels normalise
  it now; the endpoint side already did and the asymmetry was the bug.
* The phone-side read collapsed "the SVI is not there" into the same empty
  string as "it is there and holds nothing". Interface presence is now carried
  as its own fact (`endpoint_interface_present`) and reported per stage.

## The open question

**Whether the phones acquire at all is still genuinely unknown.** No phone was
observed to acquire -- but seventeen were never read, and the four that were
read were judged by a rule that was wrong. Do not record "phones do not
acquire" as a finding: it is not one yet.

What the last Floor-1 run does establish:

```text
POWER                  VERIFIED  132/132 physical items observed
LINK                   VERIFIED  74 devices / 55 links / 3 modules
VOICE_VLAN             VERIFIED  49/49 access ports, data 10 / voice 20
VOICE_INTERFACE        not captured (fixed since)
DHCP                   no acquisition observed on any channel that answered
CME_REGISTRATION       4 observed UNREGISTERED, 17 not read
DUAL_CHANNEL           not evaluable, no phone had both channels answer
```

## NEXT_ACTIVE_STEP

1. Re-enable MCP BUILDER, confirm `connected: True`, re-run Floor 1. The
   evidence now separates every link: per phone, whether `Vlan20` exists,
   whether it holds a lease, whether the `show ephone` capture that judged it
   was complete, and whether the two channels agree.
2. Read `voice.voice_interface_present` and
   `voice.registration_evidence_method` in the stage evidence before concluding
   anything. If SVIs are present and unaddressed, the defect is in acquisition
   (option 150 delivery, pool reachability, or CME source address). If SVIs are
   absent, the phones never learned their voice VLAN and the defect is earlier.
3. Then Floor 2 -> Floor 3 -> Router0/3650 -> Router3/2960 -> remaining -> full
   qualification -> retained presentation.

### Driving the live runner

`<scratchpad>/drive_live.py` performs the operator half of each checkpoint --
commit, push, answer `continue`. It accepts `--stop-after <stage>` and
`--retain`. Do not edit tracked files under `src/`, `tests/`,
`tools/cp_scale_canonical_live.py` or the two reference documents while a run is
in flight: the checkpoint refuses to advance if governed source changed.

**Do not stop a run mid-flight.** Physical ownership is runtime-instance-local
by design, so `remove_device` refuses to delete devices the current process did
not create, and a killed run leaves its devices behind with no governed way to
clean them up -- it cost a manual `File -> New` this session. Let a run fail on
its own: its `finally` cleans up and re-observes the baseline twice.

**Budget the registration wait.** `observe_registration` polls per phone for up
to 180s. Twenty-one phones that never register is ~63 minutes in that loop
alone, so a failing Floor 1 takes over an hour. That is bounded and correct, but
plan around it.

## Commits this session

```text
6ea254d fix(cp-scale): let the plan that owns the mechanism own the phone's address
4ee1974 feat(cp-scale): stage the voice plan in the governed LIVE pipeline
cc9a4f4 feat(cp-scale): measure call control instead of assuming it
e8ee880 fix(cp-scale): keep the phone's own address when its registration is unreadable
87ed5a0 fix(cp-scale): a port that cannot expose an address is unobservable
224289c fix(cp-scale): admit an absent address channel as its own governed ceiling
c2d06c0 fix(cp-scale): let a foundation rest on the ceiling its kind actually has
32df973 fix(cp-scale): tell absence apart from not having looked, on both channels
```
