# CP-SCALE continuation handoff

## Resume identity and hard boundaries

```text
BRANCH = feature/runtime-ripv2
UPSTREAM = personal/feature/runtime-ripv2
PACKET_TRACER_BUILD = 9.0.1.0858
HEAD = 4c881d5 (pushed)
ROUTING_CORE = GOVERNED VERIFIED (re-materialized 3x this session)
ROUTER4_SWITCH10 = GOVERNED VERIFIED (re-materialized 3x this session)
FLOOR1_PHYSICAL = VERIFIED (74 devices / 55 links / 3 modules)
FLOOR1_CONFIGURATION = VERIFIED (acceptance error empty, zero contradictions)
FLOOR1_VOICE = APPLIED (47/47, zero refused), NOT VERIFIED
FLOOR1 = NOT VERIFIED -- phones do not acquire
CP_SCALE = OPEN
E10 = FORBIDDEN
```

Offline: **2709 passed**, no failures.

Three governed LIVE runs reached Floor 1 and failed there on the same wall. A
fourth never started: the authenticated bridge blocker reproduced. Every run
that acquired ownership cleaned up and re-observed the baseline twice; run four
created nothing.

**A LIVE run cannot start until the operator re-enables MCP BUILDER.** That is
the current state of the bridge, not a guess -- see below.

## The acquisition question is ANSWERED. Its cause is not.

This is the finding, and it is a finding now rather than an artefact of not
having looked:

```text
POWER                  VERIFIED   132/132 physical items
LINK                   VERIFIED   74 devices / 55 links / 3 modules
VOICE_VLAN             VERIFIED   49/49 access ports, data 10 / voice 20
VOICE_INTERFACE        VERIFIED   Vlan20 present on 21/21 phones
PHONE_ADDRESS_CHANNEL  VERIFIED   readable on 21/21 -- the channel answers
PHONE_DHCP             FAILED     0/21 hold an address (reproduced 3 runs)
CME_REGISTRATION       FAILED     19 UNREGISTERED from a COMPLETE table
EPHONE_POPULATION      DEFECT     Router4 holds 19 ephones, not 21
DUAL_CHANNEL           AGREE      both channels report no address; no phone
                                  ever had two positive reads to compare
```

Every phone learns its voice VLAN and builds `Vlan20`. None acquires. The chain
breaks **at acquisition**, not before it -- so the defect is not in VLAN
learning, port configuration, power or voice-interface creation, and evidence
now excludes each of those rather than merely not implicating them.

Do not read `PHONE_DHCP = FAILED` as "DHCP is broken". What is established is
that no phone holds an address on a channel proven able to report one. Whether
the phones never solicited or solicited and got nothing is **still open**, and
the two want opposite investigations.

### The strongest lead

The Floor-1 stage carries **zero configuration actions targeting any of the 21
phones**. 28 endpoint actions cover 23 PCs, 2 printers and 3 APs; the phones get
none.

That is a consequence of `6ea254d`, and that commit is right: E5 stopped
claiming a phone on a voice VLAN because the `Vlan20` it would address does not
exist when E5 is preflighted against the live inventory. But nothing took over
the job of telling the phone to acquire on the SVI it later builds. If a PT 7960
does not solicit by itself, that is the whole defect and it sits upstream of the
pool, option 150 and reachability alike.

Measured against that lead, and why it is not yet settled:

* `Vlan20` exposes `getIpAddress` and **no `isDhcpEnabled`** -- measured, all 21,
  run three. So the SVI cannot answer whether it was asked to acquire.
* `56537ca` asks the phone at **device level** as well, on the precedent of the
  AccessPoint-PT probe, which had to ask the device AND both ports because this
  build does not put the same getters in both places. **That read has never
  run**: run four died at the bridge before deploying anything.

### The other half of the topology worth suspecting

The DHCP server demonstrably works: 23 PCs leased `172.16.10.x` and read their
addresses back. Those PCs are all on **Switch4**. The phones are all on
**Switch5**, one hop further out:

```text
Router4:Fa0/0 (.10 .20 .30 dot1Q, all three pools)
  |  Switch10:Gi0/1 -- Switch10:Fa0/1   (2960-24TT)
  |  Switch4:Gi0/1  -- Switch4:Gi0/2    (3560-24PS)  <- 23 PC-PT, DHCP, LEASED
  |  Switch5:Gi0/1                      (3560-24PS)  <- 21 x 7960, NO LEASE
```

Everything else on Switch5 -- 2 printers, 2 APs -- is static or not
IP-addressable, so **nothing has ever proven that the Switch4 <-> Switch5 hop
forwards DHCP at all**. VLAN 20 is created on all three switches and all five
trunk ports read back as trunks, but `allowed_vlans` is UNOBSERVABLE on this
build, so a trunk that does not carry VLAN 20 would look identical.

Two candidate causes remain and they are separable:

1. the phones never solicit (device-level read, already implemented, unexercised);
2. VLAN 20 does not reach Router4 from Switch5.

If the device-level read comes back unreadable too, the phone's structured API is
exhausted and the next honest observation is **the server's own record** --
`show ip dhcp binding` on Router4, which is not a registered query yet. It splits
the two cleanly: `172.16.10.x` bindings and no `172.16.20.x` means the DISCOVERs
never arrive; any `172.16.20.x` binding means the phones do acquire and the
phone-side read is looking in the wrong place.

### Two ephones are missing from the call control

Reproduced exactly in runs one and three, from a **complete** 5-page capture:

```text
A complete show ephone capture of 5 page(s) named 19 extension(s) and not 3001
A complete show ephone capture of 5 page(s) named 19 extension(s) and not 3007
```

Router4 holds 19 ephones, not 21, and the two absent are `ephone-1` and
`ephone-7`. All 21 `BindPhoneToExtension` actions applied and none was refused,
so two typed bindings did not survive on the device. A duplicate MAC is the
obvious suspect -- `_phone_mac` takes each phone's first non-zero port MAC, and
`ephone N mac-address X` for an X another ephone already holds does not leave two
rows. Nothing has measured this yet.

The raw capture is **not retained** in the evidence. Fixing that is the cheapest
next step on this question: the parsed verdicts cannot answer why a row is
missing, only that it is.

## The bridge blocker: ROOT-CAUSED AND FIXED, NOT VERIFIED

It reproduced on run four with the recorded signature exactly:

```text
connected: False   last_poll_ago: None   unauth_count: 0
file bridge: alive   token_id: unchanged
```

The webview's command loop is documented as reencadenandose siempre, "nunca hay
una rama que deje el bucle muerto". It was not. Everything between receiving a
response and rechaining ran outside any `try`: `log()` writes to the DOM and
compiles a `RegExp` out of the search box, and one exception there took the
`again()` with it. The loop died silently while `pollBridgeStatus` kept its own
`setInterval` alive -- which is why the window still looks healthy, and why the
file bridge (Script Engine, no window) is alive through every occurrence. A
CP-SCALE run pushes thousands of commands through that loop.

`4c881d5` rechains past everything that can throw and adds a watchdog above it,
because a self-rechaining loop still cannot recover from its window reloading or
from a request that calls none of its callbacks. A generation counter stops a
rescue from leaving two chains running.

**This is APPLIED, NOT VERIFIED.** It takes effect when Packet Tracer reloads the
extension, and nothing in this session exercised it. The next session should
confirm the loop survives a full run, and confirm it recovers if it does not.

The runner's hard stop now names which of the three failures it is instead of
one sentence naming none of them. Diagnose with:

```bash
PYTHONPATH=src .venv/Scripts/python.exe -c \
  "from packet_tracer_mcp.infrastructure.execution.live_bridge import PacketTracerHttpTransport as T; \
   from packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import canonical_bridge_polling_error; \
   t=T(); print('connected:', t.start(timeout_seconds=20.0)); \
   print(canonical_bridge_polling_error(t.status_dict()) or '(nothing to diagnose)'); t.stop()"
```

Never repoint the runner at the file bridge to get past this. The authenticated
channel is the gate that makes a LIVE stage trustworthy, and the file bridge is
alive in every one of these failures.

## What this session closed

### 1. `show ephone` was unreadable at floor scale -- FIXED

21 ephones page, and `SHOW_EPHONE` was not a pagination-qualified query, so every
capture stopped at its first page. Since `32df973` that is reported honestly,
which left the call-control channel unable to say anything at all about Floor 1 --
not UNREGISTERED, not registered. It is qualified now, on the same measured
grounds as the serial controller and `show ip protocols`, with the same hard
bounds; a capture that cannot close is still truncated and still claims nothing.

Completeness is **flaky across runs**: runs one and three walked all 5 pages,
run two truncated after page 1 and read the same scattered four the previous
handoff recorded (3011, 3016, 3020, 3021). It fails closed every time, so it
never fabricates absence, but the channel is not yet reliable.

### 2. One table, read once -- FIXED

`show ephone` is one table per call control and it was read once per phone: 21
expectations each opened their own bounded convergence episode over the same
rows. The observation is now one episode per host, closing early only when every
phone in the group has registered, so no phone gets a shorter window than the
contract gives it.

Floor 1 went from an estimated ~63 minutes of registration polling to a **~7
minute whole run**. That is what made four iterations possible in one session.

### 3. Three channels that could not tell absent from empty -- FIXED

The same defect class, three times, and the last one was standing between the
session and the answer:

* the phone's voice SVI reported `""` both when it had no address getter and when
  it had one and held nothing. `ce53b15` carries the address channel as its own
  fact -- this is what turned "no address, cause unknown" into "readable, and
  holds none";
* a row absent from a **complete** table was reported with the message for a
  phone no `show ephone` session is bound to at all. It has its own evidence
  method now and carries what the capture did contain;
* `97119e0` and `56537ca` add the DHCP flag and the device-level pair with the
  same three states throughout: enabled, disabled, and no getter to ask. Absent
  never collapses into False.

### 4. A stub that mirrored the model by hand -- FIXED

The voice staging stub drifted three times in one session, once per honest field
the stage learned to report. It is built from the real result model now.

## NEXT_ACTIVE_STEP

1. Re-enable MCP BUILDER. Confirm `connected: True`. **Reload the extension** so
   `4c881d5` is actually in play, and watch whether the loop survives the run.
2. Re-run Floor 1. Read `voice_device_dhcp` and `voice_device_addressed` first --
   they have never run, and they may settle the acquisition cause outright.
3. If the device level is unreadable too, register `show ip dhcp binding` on the
   call-control host. It splits "never solicited" from "solicited and got
   nothing" with the server's own record, independent of every phone getter.
4. Retain the raw `show ephone` capture in the evidence, then settle why Router4
   holds 19 ephones and not 21. Check `_phone_mac` for duplicate MACs first.
5. Then Floor 2 -> Floor 3 -> Router0/3650 -> Router3/2960 -> remaining -> full
   qualification -> retained presentation.

### Driving the live runner

`<scratchpad>/drive_live.py` performs the operator half of each checkpoint --
commit, push, answer `continue`. It accepts `--stop-after <stage>` and
`--retain`, and it never kills a run: `--stop-after` answers a checkpoint with a
refusal so the runner raises on its own and its governed `finally` cleans up.
Do not edit tracked files under `src/`, `tests/`,
`tools/cp_scale_canonical_live.py` or the two reference documents while a run is
in flight: the checkpoint refuses to advance if governed source changed.
`EXTENSION/` is not governed source.

**Do not stop a run mid-flight.** Physical ownership is runtime-instance-local by
design, so a killed run leaves its devices behind with no governed way to clean
them up.

## Commits this session

```text
9677e05 fix(cp-scale): read one registration table once, and read all of it
ce53b15 fix(cp-scale): tell an unread address channel apart from an unacquired phone
97119e0 feat(cp-scale): read whether the phone was ever asked to acquire
56537ca feat(cp-scale): ask the phone, not only the interface the plan named
4c881d5 fix(runtime): let the command poll survive its own logging, and watch it
```

plus six `chore(cp-scale): checkpoint ...` commits from the three runs that
reached and passed routing-core and router4-switch10.
