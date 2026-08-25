# CP-SCALE continuation handoff

## Resume identity and hard boundaries

```text
BRANCH = feature/runtime-ripv2
UPSTREAM = personal/feature/runtime-ripv2
PACKET_TRACER_BUILD = 9.0.1.0858
HEAD = 884dd5e (pushed)
ROUTING_CORE = GOVERNED VERIFIED (re-materialized 4x)
ROUTER4_SWITCH10 = GOVERNED VERIFIED (re-materialized 4x)
FLOOR1_PHYSICAL = VERIFIED (74 devices / 55 links / 3 modules)
FLOOR1_CONFIGURATION = VERIFIED (acceptance error empty, zero contradictions)
FLOOR1_VOICE = APPLIED (47/47, zero refused), NOT VERIFIED
FLOOR1 = NOT VERIFIED -- phones do not acquire, and the cause is now known
CP_SCALE = OPEN
E10 = FORBIDDEN
```

Offline: **2709 passed**. Four governed LIVE runs reached Floor 1; all cleaned up
and re-observed the baseline twice. Packet Tracer workspace is empty.

**The last phase was DIAGNOSTIC. No implementation landed.** The only commits
since `21d2d94` are two evidence checkpoints (`63edcf7`, `884dd5e`).

## ROOT CAUSE -- FOUND AND MEASURED

**The product asks a getter name that does not exist on this model.**

FACT, measured by enumerating the live objects on 9.0.1.0858 (not by guessing
names -- guessing is how this was missed three times):

```text
7960 Vlan port     isDhcpClientOn      present   <- the real name
                   setDhcpClientFlag   present   <- the real setter
                   getIpAddress        present
                   isDhcpEnabled       ABSENT    <- what the product asks
                   setIpAddress        ABSENT
7960 device        no dhcp/ip/addr member at all (134 members enumerated)
7960 Switch/PC     no address members; carry getAccessVlan/getVoipVlanId
```

`enterprise_voice_runtime.py:426-427` (port) and `:434-435` (device) both ask
`isDhcpEnabled`. So `voice_interface_dhcp = {unreadable: 21}` and
`voice_device_dhcp = {unreadable: 21}` are statements about the **name**, not
observations about the phones. The device-level answer is a genuine model limit;
the port-level one was a bug.

FACT: a fresh 7960 reads `Vlan1.isDhcpClientOn() == false`.
FACT: nothing in the Floor-1 plan ever calls `setDhcpClientFlag` -- zero
configuration actions target any of the 21 phones (the 28 endpoint actions cover
23 PC-PT, 2 Printer-PT, 3 AccessPoint-PT).

INFERENCE, strong: the phones are never made DHCP clients, so they never
solicit. **WORLD A.**

Evidence retained at `data/cp-scale/phone-dhcp-client/` (both probes and their
raw results; `data/` is gitignored, as with `ap-addressability/`).

### What is still open

UNOBSERVABLE this session: `isDhcpClientOn` on a **powered** phone's `Vlan20` in
the real topology. The bounded probe placed and powered a 7960 (`setPower`
returned true) but its ports never came operational without the CP-SCALE PoE
scaffolding, so `Vlan20` never appeared.

If a powered `Vlan20` reads `isDhcpClientOn == true`, World A is wrong and the
VLAN-20 path becomes primary. **Do not skip that check.** Correcting the read
name is one symbol and settles it on the next Floor-1 run.

### The path world, if it survives

Not excluded, demoted. If the phone is not a DHCP client, forwarding cannot be
the primary cause. Re-test only after World A is fixed.

The evidence for it is **already in reach with no new command**:

* FACT: `_verify_trunk` (`enterprise_configuration_runtime.py:515`) already runs
  `show interfaces trunk`, then hardcodes `"allowed_vlans": UNOBSERVABLE`
  (`:551`).
* FACT: `parse_show_interfaces_trunk` keeps only section 1 (`TrunkStatusRow` =
  interface/mode/encapsulation/status/native_vlan). "Vlans allowed on trunk",
  "Vlans allowed and active in management domain" and "Vlans in spanning tree
  forwarding state and not pruned" are discarded -- the last of those is exactly
  the question.
* FACT: `SHOW_INTERFACES_TRUNK` is not pagination-qualified, so those sections
  page away regardless.

Topology worth remembering: the 23 PCs that lease are all on **Switch4**; all 21
phones are on **Switch5**, one hop further out, and everything else on Switch5 is
static or not addressable, so that hop has never been proven to forward DHCP.

FACT: `show ip dhcp binding` has **no registered query**. `OperationalQueryId`
carries `SHOW_IP_DHCP_SNOOPING` only, which is switch security, not the server
binding table. Needed only if the path world survives.

## NEXT_ACTIVE_STEP -- for the implementation agent

The full implementation handoff (FILES_TO_CHANGE, SYMBOLS_TO_CHANGE,
FAIL_FIRST_TEST, LIVE_ACCEPTANCE_CRITERIA, DO_NOT_CHANGE) was delivered
separately. In short:

1. **Minimum correct fix first, alone:** read `isDhcpClientOn` on the voice SVI,
   keeping the three-state absent/false/true contract. Re-run Floor 1. This
   converts the last inference into a measurement.
2. Only then, gated on that evidence: a typed action making the phone a DHCP
   client on the SVI it builds (`setDhcpClientFlag(true)`), applied after
   `Vlan20` can exist, with an independent read-back.
3. Owning stage is **E7 / voice acquisition, not E5**. `6ea254d` is correct and
   must stand: `Vlan20` does not exist at E5 preflight. E7 already owns the
   phone's address claim, so it must own causing the acquisition it judges.

Architectural blocker to solve first: `apply_actions` refuses any batch not
targeting exactly one call-control host and routes everything through
`PacketTracerVoiceRenderer` -> `configure_ios(host, payload)`. A phone-side
acquisition action targets the **phone** and is a structured PT call, not IOS.
That path does not exist yet.

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

`<scratchpad>/drive_live.py` performs the operator half of each checkpoint --
commit, push, answer `continue`. It accepts `--stop-after <stage>` and
`--retain`, and never kills a run: `--stop-after` answers a checkpoint with a
refusal so the runner raises on its own and its governed `finally` cleans up.

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
63edcf7 chore(cp-scale): checkpoint routing-core
884dd5e chore(cp-scale): checkpoint router4-switch10
```

Both are evidence checkpoints from the diagnostic run. No implementation.
