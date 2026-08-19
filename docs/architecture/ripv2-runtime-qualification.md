# RIPv2 Runtime Replay-Safety Qualification

Runtime R2-0. This document answers one question only:

> If the exact intended RIPv2 configuration is applied twice to Packet Tracer,
> does the resulting semantic RIP configuration remain unchanged?

No typed RIP code was written for this qualification.

## Environment

| Item | Value |
| --- | --- |
| Packet Tracer version | `9.0.1.0858` |
| Version provenance | `ipc.appWindow().getVersion()` read live during this run |
| Device model | `2911` |
| Probe device | `__MCP_PROBE_R2_R1` (disposable) |
| Workspace precondition | 0 routers, 0 switches, 0 PCs before creation |
| Dispatch boundary | Runtime Safety R1 hardened boundary (pager guard, exact echo) |
| Mutation channel | `PacketTracerConfigurationRuntime.configure_ios` (existing typed transport) |

## Exact payload

Applied verbatim, twice, with one deliberate dispatch each time and no retry:

```text
enable
configure terminal
router rip
version 2
no auto-summary
network 150.1.0.0
passive-interface GigabitEthernet0/0
end
write memory
```

## Readback method

`show ip protocols`, dispatched through the R1 guarded boundary with exact echo
verification and fresh-window attribution.

The comparison is **semantic, not textual**. Timer fields such as
`Sending updates every 30 seconds, next due in N seconds` change between reads
and are deliberately excluded from the compared state.

Compared fields: RIP presence, send/receive version, automatic summarization,
the set of advertised networks, and the set of passive interfaces.

## Baseline

```json
{
  "rip_present": false,
  "version_send": null,
  "version_recv": null,
  "auto_summary": null,
  "networks": [],
  "passive_interfaces": []
}
```

The intended RIP configuration was absent before the first application.

## STATE_AFTER_APPLY_1

```json
{
  "rip_present": true,
  "version_send": 2,
  "version_recv": 2,
  "auto_summary": false,
  "networks": ["150.1.0.0"],
  "passive_interfaces": ["GigabitEthernet0/0"]
}
```

## STATE_AFTER_APPLY_2

```json
{
  "rip_present": true,
  "version_send": 2,
  "version_recv": 2,
  "auto_summary": false,
  "networks": ["150.1.0.0"],
  "passive_interfaces": ["GigabitEthernet0/0"]
}
```

Raw readback after the second application:

```text
show ip protocols
Routing Protocol is "rip"
Sending updates every 30 seconds, next due in 21 seconds
Invalid after 180 seconds, hold down 180, flushed after 240
Outgoing update filter list for all interfaces is not set
Incoming update filter list for all interfaces is not set
Redistributing: rip
Default version control: send version 2, receive 2
  Interface             Send  Recv  Triggered RIP  Key-chain
Automatic network summarization is not in effect
Maximum path: 4
Routing for Networks:
	150.1.0.0
Passive Interface(s):
	GigabitEthernet0/0
Routing Information Sources:
	Gateway         Distance      Last Update
Distance: (default is 120)
Router>
```

## Semantic comparison

| Check | Result |
| --- | --- |
| RIP version unchanged | PASS (send 2 / receive 2 both times) |
| `no auto-summary` unchanged | PASS (`not in effect` both times) |
| Network statement set unchanged | PASS (`["150.1.0.0"]`) |
| Passive-interface set unchanged | PASS (`["GigabitEthernet0/0"]`) |
| No duplicate network declarations | PASS (set size equals list size) |
| No duplicate passive declarations | PASS (set size equals list size) |
| `STATE_AFTER_APPLY_1 == STATE_AFTER_APPLY_2` | PASS |

The second application produced no additional semantic configuration. The
network and passive-interface declarations behave as **sets**, which is the
structural property that separates them from ordered lists such as numbered
ACL entries.

## Operational check

Optional and cheap only. After the second application the router still reports
`Routing Protocol is "rip"` with an active update timer, so the protocol
remained operational rather than being torn down by the repeated application.

No second router and no routing-convergence scenario was exercised. That
belongs to typed R2, not to this gate.

## Cleanup

`__MCP_PROBE_R2_R1` was deleted. Residue of `__MCP_PROBE_R2_*`: none.

Two backend-managed `Power Distribution Device` objects remained in the
workspace. Packet Tracer creates these itself when devices are placed; they are
not probe residue and are not removable by this project.

## Limitations of this evidence

1. One model (`2911`), one Packet Tracer build (`9.0.1.0858`), one repetition
   (two applications). This is a qualification, not a statistical claim.
2. The readback is `show ip protocols`. The running-config RIP block was not
   read, because `show running-config` paginates in this backend. Duplicate
   declarations would have surfaced as repeated entries in the compared sets,
   but a running-config-level diff was not performed.
3. `passive-interface` was verified on an interface without an IPv4 address, so
   the `Interface` table of `show ip protocols` is empty in both states. That
   does not affect the compared fields.
4. The FileBridge duplicate-execution limitation (`TD-TRANSPORT-001`) is
   unchanged by this result. This qualification shows the RIP payload tolerates
   repeated application; it does not make replay deliberate or acceptable.

## Result

```text
RIPV2_REPLAY_LIVE_QUALIFICATION   = READY
RIPV2_CURRENT_TRANSPORT_SAFETY    = READY_FOR_TYPED_IMPLEMENTATION
GLOBAL_COMMAND_TRANSPORT_INTEGRITY = PARTIAL   (unchanged by this gate)
```

---

# R2-B phase 4 — typed RIPv2 route exchange and forwarding

A later stage on the same Packet Tracer build. Recorded here so the evidence
and its ceiling outlive the session that produced them.

## Environment and slice

| Item | Value |
| --- | --- |
| Packet Tracer version | `9.0.1.0858`, declared through `ConfigurationRuntimeContext.evidence_backend_version` |
| Routers | 2× `2911` with `HWIC-2T`, serial interface **discovered** as `Serial0/0/0`, not assumed |
| Endpoints | 2× `PC-PT` |
| Probe names | `MCP-PROBE-R2B-R1`, `-R2`, `-PCA`, `-PCC` |
| Serial roles | `show controllers`: R1 **DCE**, R2 **DTE**; `clock rate` applied only to R1 |
| Addressing | R1 LAN `150.1.1.64/28`, WAN `150.1.1.84/30`, R2 LAN `150.1.1.0/27` |

Local reachability was proven **before** RIP existed, so a later failure could
not be misattributed to routing: each PC reached its own gateway 4/4, and R1
reached R2 across the WAN 5/5.

## What was verified live

| Claim | Result |
| --- | --- |
| Capability resolution for `ripv2_config` and `routing_process_state` on 2911 | SUPPORTED, non-test provenance, version-scoped |
| LAN interface passive, serial interface active | compiled that way on both routers |
| Typed RIP application | one deliberate dispatch per router, APPLIED |
| Configuration read-back | VERIFIED on both, via `fresh_show_ip_protocols` |
| Learned route on R1 | `R 150.1.1.0/27 [120/1] via 150.1.1.86, Serial0/0/0` |
| Learned route on R2 | `R 150.1.1.64/28 [120/1] via 150.1.1.85, Serial0/0/0` |
| Forwarding PC-A → PC-C and PC-C → PC-A | 4/4 each, no loss, first attempt |

Routes were read through the registered query `SHOW_IP_ROUTE_RIP` and
`parse_show_ip_route_rip`, both added in this stage because neither existing
route parser matches a RIP row arriving over a serial interface.

This is **RIP route exchange**, not an OSPF-style adjacency. RIP has no
neighbour state machine, and none is required or claimed.

## Claim ceiling

Route-learning *behaviour* was verified here, in phase 4. At the time this was
written the typed *expectation* plumbing did not exist, so route learning did
not appear inside `ControlPlaneApplicationResult`.

**Closed at Debt Checkpoint 1 (2026-08-12).** `TD-RUNTIME-005` is RESOLVED:
compiled `ROUTE_PRESENT` expectations for typed RIPv2 now bind this read-back,
with expected prefixes derived from the E5 L3 identities rather than the
classful `network` statement.

```text
RIPV2_ROUTE_LEARNING_BEHAVIOR       = VERIFIED
RIPV2_ROUTE_EXPECTATION_INTEGRATION = READY   (was NOT_READY in phase 4)
```

The evidence above is also what qualifies `ROUTING_ROUTE_STATE` as SUPPORTED
for the 2911 in the control-plane capability catalog.

## Cleanup

All four disposable devices were deleted by exact name in a finally-protected
block: `MCP-PROBE-R2B-R1`, `-R2`, `-PCA`, `-PCC`.

Residue of `MCP-PROBE-R2B-*`: none. Semantic probe links remaining: 0. The
backend-managed `Power Distribution Device` was preserved, as it is not probe
residue and is not removable by this project.

---

# R3 — typed measurement channel on 2911, 2026-08-19

Qualifies the capability the control-plane gate protects: whether the
**production** `TypedPingExecutor` can measure at all on this model and build.
It deliberately does not qualify forwarding. Whether a destination answers is
`reachable`, which the product measures per run.

## Environment and slice

| Item | Value |
| --- | --- |
| Packet Tracer version | `9.0.1.0858`, confirmed at OS level from the running GUI process |
| Device | one disposable `2911`, probe name `__MCP_PROBE_RB_R1` |
| Import isolation | `ISOLATED`, measured in the qualifying process before any mutation |
| Baseline workspace | 0 semantic devices, 0 links |
| Path | production runtimes only — physical create, typed `ConfigureRoutedInterface`, registered `SHOW_IP_INTERFACE_BRIEF`, `TypedPingExecutor` |

`GigabitEthernet0/0` was addressed `10.254.254.1/30` through the typed
configuration action and read back live as
`GigabitEthernet0/0 10.254.254.1 down down` — unlinked, so nothing answers.

## What was measured live

| Claim | Result |
| --- | --- |
| Typed ping dispatches on a 2911 IOS terminal | yes, after the registered read-back settled the session |
| Fresh attributable window | yes, `window_strategy = prefix_delta` |
| Exact echo of the dispatched `ping <ip>` | yes — no `command_dispatch_mismatch` |
| Statistics line parsed by the production parser | `Success rate is 0 percent (0/5)`, both measurements |
| Execution provenance | `confirmed_unique`, `observed_device_name = __MCP_PROBE_RB_R1`, evidence `session_transcript_continuity` |
| Reachability | `False` on the interface address and on an unreachable target |

**Both measurements returned `reachable = False`, and that is what qualifies
the channel.** The dimension is measurability, not success. A qualification
that had required a successful ping would have been qualifying forwarding.

Recorded rather than smoothed over: the first attempt returned
`prompt_not_ready_command_in_flight`. The idle guard refused to dispatch into a
terminal still printing the configuration batch. That is the guard working; a
registered query was used to settle the session before measuring.

## Cleanup

`__MCP_PROBE_RB_R1` deleted by exact name in a finally-protected block.
Semantic inventory returned to 0 devices and 0 links. Backend-managed
`Power Distribution Device` objects went from two to three; they are
backend-created, zero-port, not probe residue and not removable by this
project.

## Limitations of this evidence

1. One model (`2911`), one build (`9.0.1.0858`), one session. A qualification,
   not a statistical claim.
2. It qualifies the **measurement channel only**. It says nothing about whether
   any route forwards, and must never be cited for that.
3. The interface was `down/down`, so no ICMP left the device. What was
   exercised is dispatch, echo, window attribution, statistic parsing and
   execution provenance — precisely what the gate protects.

## Result

```text
ROUTING_BEHAVIOR_CHANNEL_2911_9_0_1_0858 = QUALIFIED
FORWARDING_SUCCESS                       = NOT CLAIMED BY THIS QUALIFICATION
```
