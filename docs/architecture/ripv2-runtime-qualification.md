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
