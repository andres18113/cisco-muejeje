# E7 enterprise voice and telephony

E7 consumes immutable artifacts from the three preceding enterprise layers:

```text
Concrete TopologyPlan       E4: phones, call-control hosts, ports and links
           |
ConfigurationPlan          E5: voice VLAN, addressing, L3 and DHCP pool
           |
ServicePlan (optional)     E6: only services explicitly consumed by voice
           |
VoicePlan                  E7: extensions, bindings, dial rules and acceptance
           |
  compile / apply / register / call / teardown
```

E7 does not create devices, reconnect links, choose hardware, repair VLANs, or
reapply E5/E6. Every plan binds the E4 and E5 semantic hashes and binds E6 only
when the voice intent names a real service dependency. A stale source or a
foundation that is not independently `VERIFIED` stops the runtime before any
mutation.

## Domain boundary

`VoicePlan` is separate from `ConfigurationPlan` and `ServicePlan`. It has a
different lifecycle and acceptance model: a configuration accepted by IOS does
not prove phone registration, and registration does not prove that a call can
ring, connect, and tear down.

The backend-neutral action set is closed:

- enable call control and set its signaling source;
- create a numeric directory number;
- bind an existing physical phone identity to an extension;
- set DHCP option 150 on an existing E5 pool;
- generate phone configuration files;
- define local or intersite dial rules.

There is no arbitrary IOS, JavaScript, phone command, or extension-provided
filesystem path in the domain. Extension allocation is deterministic, reserves
explicit assignments first, rejects collisions and range exhaustion, and uses
stable natural device identity rather than input order.

## Dependencies and semantic identity

Phone assignments reuse the concrete E4 phone ID/name/model and the E5 access
port, explicit voice VLAN, voice segment, and addressing action. Call-control
source addresses are reused from an E5 L3 action on that same voice segment.
Implicitly treating a data VLAN as a voice VLAN is rejected.

When the call-control host owns the E5 DHCP pool for a voice segment, E7 emits
typed option-150 configuration and makes configuration-file generation depend
on it and on all phone bindings. A missing Packet Tracer getter remains a
runtime observability limitation; it is not replaced with invented evidence.

The semantic hash is canonical SHA-256 over the plan except its hash field. It
includes source hashes, assignments, directory indexes, actions, dependencies,
dial rules, foundations, and verification expectations. Runtime session IDs,
timestamps, MAC observations, IOS transcripts, and call attempts do not enter
the hash.

## Apply, register, call, and accept

E7 keeps the following states independent:

```text
COMPILED != APPLIED != REGISTERED != CALL_VERIFIED
```

The Packet Tracer adapter renders only typed actions. Phone MAC addresses are
read from the existing device at apply time, validated, and used for the CME
binding. IOS operational evidence is obtained with the registered privileged
query `show ephone` through `Device.getCommandLine()` and `TerminalLine`.
`ControlledIosExecutor` enters privileged EXEC only for that query, isolates a
fresh current-command output window, and returns to user EXEC afterwards.

Registration convergence is bounded. A phone is verified only when its current
extension row is `REGISTERED`; an old console transcript cannot satisfy a new
observation. Call verification additionally requires a unique attempt ID,
evidence produced after that attempt began, the expected connected or rejected
behavior, and successful teardown. A ringing-only call and a teardown failure
are distinct outcomes.

The Extensions API exposes no documented operation for off-hook, dialing,
answer, or hang-up on a 7960. The production adapter therefore accepts an
injected controlled call driver and otherwise reports call initiation as
unobservable. It never promotes configuration acceptance or registration into
a verified call.

## Packet Tracer 9.0.1.0858 evidence

Controlled disposable probes established this conservative baseline:

| Capability | Evidence | Status |
| --- | --- | --- |
| CME on 2811 | `telephony-service` accepted | supported |
| CME on 2911 | IOS rejects `telephony-service` | unsupported in this PT build |
| SCCP registration | fresh privileged `show ephone` | supported on the 2811 slice |
| DHCP option 150 | IOS help plus `DhcpPool.getTftpAddress()` | supported |
| phone file generation | `telephony-service` `create cnf-files` | supported for the slice |
| local A to B and B to A calls | controlled phone GUI state transitions | behaviorally verified |
| unassigned number | current attempt rejected without target ringing | behaviorally verified |
| audio media | no documented or observed media getter | unobservable |
| NTP use by phone | no reliable phone-side read-back | unobservable |
| intersite calling | typed offline dial plan only | runtime not evaluated |

The successful local slice used one 2811, one 3560-24PS, two 7960 phones, voice
VLAN 930, DHCP addresses, and extensions 3101/3102. Both phones registered by
SCCP. Calls in both directions reached ringing, connected, and disconnected
states. The unassigned 3200 negative control was rejected as soon as Packet
Tracer recognized its invalid prefix; the peer never rang.

A second slice linked a PC through the phone's PC port. Voice continued to
ring, connect, and tear down, proving that adding the passthrough link did not
invalidate telephony. The PC port was linked and statically addressed, while a
fresh ping across the data VLAN returned 0/4. Data passthrough therefore remains
`PARTIAL`; it is neither a verified feature nor a blocker for the local voice
compiler and registration runtime.

All live E7 devices use the reserved `__MCP_E7_TEST_*` prefix and are removed
after each slice. The final reference run restored the original empty inventory
and zero links without saving a `.pkt` file.

