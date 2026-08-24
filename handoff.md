# CP-SCALE continuation handoff

## Resume identity and hard boundaries

```text
BRANCH = feature/runtime-ripv2
UPSTREAM = personal/feature/runtime-ripv2
PACKET_TRACER_BUILD = 9.0.1.0858
ROUTING_CORE = GOVERNED VERIFIED (re-materialized this session)
ROUTER4_SWITCH10 = GOVERNED VERIFIED (re-materialized this session)
FLOOR1_PHYSICAL = VERIFIED (74 devices / 55 links / 3 modules, 132 items observed)
FLOOR1_CONFIGURATION = CONTRADICTED (24 of 49 endpoint addressing read-backs)
FLOOR1 = NOT VERIFIED
CP_SCALE = OPEN
E10 = FORBIDDEN
```

No live run is active. Cleanup verified twice; semantic workspace is 0 devices.
Packet Tracer keeps a growing number of backend-managed `Power Distribution
Device` objects with zero ports outside the semantic workspace; the governed
restoration check ignores them and was satisfied on every run this session.

## The scale envelope was wrong

The previous handoff recorded `PT_MCP_RELIABLE_SCALE_ENVELOPE = 4 devices / 4
links`. That is not the limit. Floor 1 deployed **74 devices, 55 links and 3
modules with all 132 items observed and `status=verified`**, and all 136 typed
configuration actions applied. Physical scale is not the blocker and has not
been for some time.

## What this session closed

Offline: **2645 passed**, no failures.

### 1. PoE admission failed open -- FIXED

`ReferenceHardwarePlanner` validated model, module and port names but never read
`AccessBlockPlan.required_poe_ports` nor per-binding `requires_poe`, so a design
demanding 86 powered ports across 13 access switches compiled `VALID` with
`poe_capacity=None` on every one of them.

Powered demand is now derived from expanded endpoint truth joined to the exact
bindings, reconciled against each block aggregate, and decided per selected
build:

```text
UNSUPPORTED               -> UNRESOLVED,         device INCOMPATIBLE
UNKNOWN                   -> PARTIALLY_RESOLVED, device NEEDS_VERIFICATION
SUPPORTED but over budget -> UNRESOLVED,         device INCOMPATIBLE
powered endpoint off an access port -> UNRESOLVED
```

E5 already refuses anything but `VALID`, so this is the live gate.

### 2. Exact-build PoE evidence -- MEASURED

```text
2960-24TT = UNSUPPORTED, verified   (24 access ports, complete power-OFF state)
3560-24PS = SUPPORTED,   24 ports,  verified
3650-24PS = SUPPORTED,   24 ports,  verified
```

`3650-24PS` needed a product fix first: `supports_poe` selected access ports by
interface-type name (`ethernet`/`fastethernet`) and a 3650 has no FastEthernet
at all -- its access ports are `Gi1/0/1..24`. The set came back empty and a
fully observed power-ON state collapsed to UNKNOWN, so a PoE switch could never
be admitted for PoE. Access-ness now comes from the catalogue's declared
`access_port_names`, the same rule `_port_descriptor` already used.

**Do not pin this evidence statically.** It was tried and reverted:
`tests/test_cp_scale_poe_authorization.py` deliberately forbids a model *name*
from promoting PoE, and a `StaticVerifiedCapabilityProvider` entry does exactly
that. The consequence is that PoE evidence is environment-local -- it lives in
the git-ignored `data/capabilities/runtime/9.0.1.0858/` snapshot store, and
`tests/test_cp_scale_canonical_physical.py` needs that snapshot to pass. On a
fresh checkout, re-measure with `data/cp-scale/poe-evidence-2960-3650/session.py`
before expecting the canonical design to compile.

### 3. Canonical authority corrected

Nine access switches were pinned to `2960-24TT` while carrying 72 powered
endpoints, and every one of them bound its access points to `Gi0/1-0/2` while
spending FastEthernet access ports on infrastructure uplinks.

```text
9 access switches 2960-24TT -> 3560-24PS  (identical port layout, PoE evidenced)
Switch10 stays 2960-24TT                  (powers nothing)
uplinks   -> GigabitEthernet
endpoints -> FastEthernet0/1..24
```

Target unchanged: 314 devices / 219 links / 18 network devices / 199
endpoint-access / 2 phone-passthrough, same endpoint pairing. Census is now
`3x2811, 1x2960-24TT, 11x3560-24PS, 3x3650-24PS`. Both reference documents were
updated with the models, the port roles and the measurement that decides them.

**Confirmed live**: every `configure_access_port` verification passed, including
on the new `GigabitEthernet0/1` and `GigabitEthernet0/2` uplinks.

### 4. Endpoint addressing read-back -- FIXED

The read-back walked `getPortAt(i)` and accepted the first port exposing
`getIpAddress`, which coincides with the addressed port only on single-port
endpoints. The expectation now carries the addressed interface and the runtime
reads that exact port; an interface it cannot find is `UNOBSERVABLE`, never
`FAILED` -- not having looked at the right port is not evidence the plan was
wrong.

The 19 wireless IoT actions had no interface at all: those catalogue models
expose an empty port inventory and `_validate_targets` skips empty interfaces,
so a `critical=True` action reached a live device aimed at nothing. CP-SCALE
already carries them with `wireless_association=unqualified`, and addressing
rides on association, so none is claimed for them now. Their VLAN stays
structural and their segment keeps its DHCP pool.

Configuration actions 609 -> 514; DHCP pools still 9.

### 5. Live failure evidence -- DURABLE

`_execute_stage` journalled the full typed configuration result three lines
before the raise that discarded it. `CanonicalLiveFailure` now carries
`stage_evidence`, all ten raise sites attach it, and the runner persists it with
`stage_outcome="failed"`. This session's root-causing depended entirely on it.

Its regression drives `_execute_stage` in a child process -- importing the tool
pulls the production `packet_tracer_mcp` namespace into pytest, which is exactly
what `ImportIsolationPreflight` exists to prevent.

## Floor-1 result: 43 contradictions -> 24

```text
partial       23 PC-PT + 2 Printer-PT   ipv4/netmask VERIFIED  <- governed ceiling, success
unobservable   3 DHCP pools                                    <- governed ceiling
failed        21 x 7960   on Vlan1
failed         3 x AccessPoint-PT on Port 0
```

The 19 wireless IoT contradictions are gone. All 136 actions applied; all 49
access-port verifications passed.

## Defect C -- live staging never applies the voice plan (ROOT-CAUSED, NOT FIXED)

Bounded live probes, each cleaned up and restored twice:

* **PoE works.** A 7960 on a 3560-24PS access port powers on and its `Switch`
  port comes up (`port_up`, `proto_up`, `power_on` all true). The red phone
  links in the operator's capture of the previous run were the 2960-24TT
  delivering no power, and that is fixed.
* **The port is right.** With the real compiled configuration applied,
  `FastEthernet0/1` reads `access_vlan=10, voice_vlan=20`, powered and up.
* **Passthrough works.** The PC behind the phone took `172.31.10.2` by DHCP
  through the phone.
* **The phone still never acquires.** Its `Vlan1` stays `0.0.0.0` and down for
  180 seconds. This is not a convergence timeout -- the address never arrives.

The reason is structural: a Packet Tracer 7960 acquires and registers through
the **voice** path, and the product already models it --
`VoiceActionType.CONFIGURE_VOICE_DHCP_OPTION` (option 150),
`ENABLE_CALL_CONTROL`, `GENERATE_PHONE_CONFIGURATION_FILES`,
`BIND_PHONE_TO_EXTENSION`. `qualify_cp_scale_offline.py:458`
(`cp_scale_voice_intent`) builds that intent and the offline qualifier applies
it. `tools/cp_scale_canonical_live.py` contains **zero** references to voice.

So CP-SCALE plans phone addressing as an ordinary endpoint action, stages it
live without the mechanism that makes it true, and then reports a contradiction.
The 3 AccessPoint-PT failures are still unexplained and were not probed; do not
assume they share this cause.

## NEXT_ACTIVE_STEP

1. Decide the governed treatment of phone addressing and implement it fail-first:
   either stage the voice plan in `_execute_stage` (compile with
   `cp_scale_voice_intent`, apply with `VoiceApplicator`, gate it) so the
   addressing claim becomes true, or stop claiming endpoint addressing for
   IP phones and let the voice path own it. Prefer the former -- the reference
   design does intend phones on VLAN 20 by DHCP.
2. Probe the 3 `AccessPoint-PT` `Port 0` failures separately before assuming a
   cause. An AccessPoint-PT may not be IP-addressable in this build at all, in
   which case it is the wireless-IoT case again.
3. Re-run Floor 1, then continue Floor 2 -> Floor 3 -> Router0/3650 ->
   Router3/2960 -> remaining -> full qualification -> retained presentation.

### Driving the live runner

It is interactive by design. At each `CHECKPOINT_READY` it writes the tracked
`docs/reference/cp-scale/live_canonical_checkpoint.json` and then refuses to
advance unless the worktree is clean and HEAD is pushed to upstream -- so the
operator must **commit and push, then answer `continue`**. Piping a stream of
`continue` lines fails on the first checkpoint. A working driver is at
`<scratchpad>/drive_live.py`; do not edit tracked files while a run is in
flight.

If the run hard-stops on `"Authenticated Packet Tracer HTTP bridge did not
obtain fresh polling"`, it is usually transient: the PT extension does poll
`127.0.0.1:54321`, and a direct `PacketTracerHttpTransport.start()` connects in
about 1.4s. Probe the transport before concluding anything about the extension.

## Commits this session

```text
1b85c33 fix(cp-scale): fail closed on PoE and read back the addressed interface
9386817 fix(cp-scale): decide PoE on access ports, and measure 2960/3650
7e5d639 fix(cp-scale): power the access layer from evidence, not from a model name
355effb chore(cp-scale): checkpoint routing-core
c4a2c58 chore(cp-scale): checkpoint router4-switch10
```
