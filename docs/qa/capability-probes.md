# Capability-probe QA

Live capability probes are manual and do not belong to the normal pytest suite.
Before a run, open Packet Tracer with MCP Control Center, inspect bridge status,
and use a disposable project or an empty canvas region.

## Operating procedure

1. Run a bounded physical probe for the intended models.
2. Confirm that cleanup is clean and that no disposable name recorded by the
   session remains.
3. Record the Packet Tracer build explicitly when the runtime cannot observe it.
4. Review discovered ports against the GUI without automatically promoting a
   model or alias.

The repository uses two disposable naming schemes. Both must be checked for
residue:

| Prefix | Purpose |
| --- | --- |
| __MCP_PROBE_* | Capability-discovery temporary devices. |
| MCP-PROBE-* | Temporary devices created through a typed runtime path. |

Exact session-owned names, rather than a broad prefix match, control cleanup. If
a residue is found, remove only the names recorded by that session; never remove
user devices.

## Evidence discipline

If Packet Tracer does not expose reliable state, retain UNKNOWN. Record the
build, model, port, method, visible state, and result for any manual observation.
Do not derive a capability from a switch name or family.

Administrative and runtime PoE state are not proof of powered-endpoint delivery.
A reusable PoE claim requires coherent active-delivery evidence for the relevant
access ports. Likewise, a static endpoint address observation does not establish
a DHCP lifecycle without controlled configuration and independent read-back.

A timeout, invalid callback, or bridge disconnect is UNKNOWN, not UNSUPPORTED.
Preserve the session identity for inspection. A DIRTY_SESSION requires targeted
manual cleanup before another live attempt.

Historical governed measurements and their exact evidence are retained under
docs/reference/cp-scale/. That immutable record, not this operating guide, is
the authority for their claims.
