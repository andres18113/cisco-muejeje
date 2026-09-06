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

Next active step:

```text
AWAIT_EXPLICIT_AUTHORIZATION_FOR_ANY_FUTURE_FRESH_DISPOSABLE_POE_SESSION
```
