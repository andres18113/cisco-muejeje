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

The operator then stopped `winnat` in the same session, `54321` bound, and the
bridge connected and authenticated. The port is resolved.

## The binding, not the port, is what blocks the next LIVE

With the bridge live the attempt still stopped before `qualify()`. Read-only,
no mutation: build `9.0.1.0858`, Realtime `observed=True`,
`simulation_mode=False`, inventory `0` devices and `0` links, bridge fresh with
zero unauthenticated requests. The serving Script Module answered completely:

```text
getCommandLineArg()   = ""   (typeof "string", length 0)
getInstanceId()       = {00489806-7f44-e52b-868e-b6f1a68ef950}
getCep().getId()      = com.matsoto.mcpbuilder
getCep().getName()    = MCP-BUILDER
ipcManager().getOpenData() = ""
```

`PacketTracerActiveWorkspaceObserver` derives its `path` from
`getCommandLineArg()`, so the empty value makes `capture()` raise and
`bind_active_workspace()` fail closed. `finalize()` would then force
`workspace_binding_verified=False`, `session_reusable=False` and
`positive_claim_allowed=False`, which makes classification A unreachable no
matter what the observer sees. Spending the single authorization on that was
not justified, so no run was made.

`getCommandLineArg()` is a launch argument, not a module-identity accessor, and
a module opened from **Extensions -> MCP BUILDER** has none. The CEP exposes no
path, directory or filename accessor, `ipc.appWindow()` exposes nothing that
identifies the loaded `.pts`, and no global holds one.

Closing this needs an offline change to how the serving module's `.pts`
identity is observed, a fresh frozen SHA with 4/4 green CI, and a new
single-LIVE authorization. This section records observed state; like the rest of
this document it grants no LIVE authority.

## The LIVE ran, and delivery is verified for exactly one binding

Session `poe-7950198d050f`, from `961229e` with Actions `34051683550` green
4/4, on Packet Tracer `9.0.1.0858`. One human capture inside `observe(...)`
recorded `3560-24PS Fa0/1 -> 7960 Switch = powered` against
`2960-24TT Fa0/1 -> 7960 Switch = not_powered`, simultaneously. Every governed
gate passed and the canonical `.pts` was byte-identical before and after.

The ceiling is `supports_poe = SUPPORTED`, `poe_ports = 1`, for that exact
binding only, with no port extrapolation. Router0 remains BLOCKED.

Packet Tracer crashed `0xc0000005` at offset `0x00000000020e5204` 9.462 s after
the decision was persisted and after every gate had closed, so under the strict
temporal boundary it is a separate reliability incident. It is the third crash
at that identical instruction -- one after each of the three most recent PoE
sessions -- and a full WER dump was retained for every one of them under
`%LOCALAPPDATA%\CrashDumps`. Analysing those dumps, not reproducing the crash,
is the next active step.

Evidence:

```text
docs/reference/cp-scale/canonical-live-evidence/poe-delivery-20260906T184155139196Z-7950198d050f-verified.json
```

Next active step:

```text
ATTRIBUTE_0XC0000005_POST_BOUNDARY_CRASH_BEFORE_ANY_ROUTER0_DECISION
```
