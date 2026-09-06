# Retired governed PoE LIVE relay

This relay was consumed by governed session `poe-9d0d21961c1c`. It must not be
used to authorize or repeat a LIVE qualification.

The session ended:

```text
C — UNOBSERVABLE / INVALID EVIDENCE
```

The observer returned no visual observation inside the governed `observe(...)`
call. Packet Tracer later recorded `0xc0000005`; available evidence has no
stack or dump that attributes the native crash to PoE or repository code. The
run did not record canonical `.pts` identity or pre/post SHA-256, so the session
is not reusable even though its earlier semantic cleanup was green.

The offline hardening at
`b356c57aa06443aea8947992e8901aa1af2726d0` adds the synchronous,
fixture-attributed observer adapter and common disposable `.pts` integrity
guard, bound through a mandatory pre-persistence session gate. This document
records that state; it grants no LIVE authority.

Current claim ceiling:

```text
supports_poe      = UNKNOWN
poe_ports         = null
Router0           = BLOCKED
session reusable  = false
```

Authoritative compact state and retained incident evidence:

```text
docs/reference/cp-scale/current_state.json
docs/reference/cp-scale/canonical-live-evidence/poe-delivery-20260906T033734787716Z-9d0d21961c1c-incident.json
```

## Authorized attempt from `d782a0e` — blocked before `qualify()`

A later operator authorization for exactly one governed LIVE, from frozen
source `d782a0e5ed85776a2f5f6a89f368350df49c6bb3` with GitHub Actions run
`34047619642` green 4/4, was NOT consumed. The attempt stopped at the bridge
precondition, before any Packet Tracer mutation and before
`PoEDeliveryQualificationService.qualify()`.

`PacketTracerHttpTransport.start()` could not bind `127.0.0.1:54321`
(`WinError 10013`). `netsh int ipv4 show excludedportrange protocol=tcp`
reports a non-administered reservation covering `54280-54379`, held by the
Hyper-V/WSL NAT stack (`winnat`, `hns`, `vmcompute`, `vmms` all running).
Nothing was listening on the port, and `54279` and `54200` bound normally, so
this is an OS reservation rather than a conflict or a stale server. The port is
fixed on both sides — `DEFAULT_PORT = 54321` in `live_bridge.py` and the
extension's own webview poll — and the encrypted `.pts` exposes no port to
renegotiate, so relocating the Python transport would only orphan the poller.

Nothing was prepared and nothing was left behind: no disposable, no session
directory, unchanged canonical SHA-256, no snapshot and no evidence artifact.

Clear the reservation from an elevated shell, then re-probe the bind before
preparing a disposable:

```text
net stop winnat
netsh int ipv4 add excludedportrange protocol=tcp startport=54321 numberofports=1
net start winnat
```

A reboot also reshuffles the dynamic ranges. This section records a machine
state; like the rest of this document it grants no LIVE authority.

Next active step:

```text
AWAIT_EXPLICIT_AUTHORIZATION_FOR_ANY_FUTURE_FRESH_DISPOSABLE_POE_SESSION
```
