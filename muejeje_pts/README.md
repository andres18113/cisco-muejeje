# `muejeje_pts/` — owned source root

The source tree of the **Muejeje runtime** artifact (`dist/muejeje.pts`).

This tree is the artifact. Nothing here may carry a consumer's assumptions: no
CP LIVE, PoE, Router0, voice, VLAN or fixed-topology concept, and no reference
to any project that consumes Muejeje (`MJ-001`, `MJ-002`, `MJ-004`).

| Path | Packaged as |
| --- | --- |
| `script-engine/` | Script Engine files, evaluated in `engine_script_order`, then `main()` |
| `interface/` | Custom Interface files, imported into the Custom Interfaces tab |
| `manifest/` | the build manifest — build metadata, **not** packaged |

`README.md` files are documentation and are **not** packaged; only the
extensions the build manifest declares as artifact inputs are.

## The V6 kernel

Packet Tracer evaluates the Script Engine files in the order the Scripting
Interface lists them, so that order **is** the dependency direction (`MJ-019`).
It is declared once, in `build_options.engine_script_order`:

| Order | File | Responsibility |
| ---: | --- | --- |
| 1 | `core.js` | constants and session state; depends on nothing |
| 2 | `protocol_v6.js` | the response envelope and the failure taxonomy |
| 3 | `validation_v6.js` | bounded request admission, and the bounds themselves |
| 4 | `platform_adapter.js` | the **only** file that names `ipc`; the read-only call boundary |
| 5 | `platform_device_adapter.js` | the device-descriptor reading, through that boundary |
| 6 | `platform_discovery.js` | the `platform.device_descriptors` operation |
| 7 | `runtime_capabilities.js` | the `runtime.capabilities` operation |
| 8 | `runtime_identity.js` | the `runtime.identify` operation |
| 9 | `dispatcher_v6.js` | the whitelist and `mcpDispatchV6` |
| 10 | `lifecycle.js` | `main()` and `cleanUp()`, nothing else |

The arrows point one way — `lifecycle → dispatcher → operations → adapter →
protocol + core` — and nothing points back. An operation is never implemented
inside the dispatcher, and the dispatcher hands an operation what it needs
rather than being read by it. No operation depends on another, so among
themselves they are ordered alphabetically: a rule, rather than an accident a
later reader would have to reverse-engineer.

Shaping an answer and deciding whether a request deserves one are two
responsibilities, so they are two files. `validation_v6.js` owns every bound V6
applies to an incoming request — its length, its correlation id, its operation
name, and the shape and values of its arguments. **Those bounds are Muejeje's
own and none of them is a Packet Tracer limit** (`MJ-029`): nothing here has
measured what PT's engine accepts, and a number presented as the platform's
would be a claim with no evidence behind it.

The single entry point is `mcpDispatchV6(requestJson)`: a JSON string in, a
JSON string out.

```json
{"v": 6, "operation_rid": "rid-123", "op": "runtime.identify", "args": {}}
```

```json
{"v": 6, "operation_rid": "rid-123", "op": "runtime.identify",
 "ok": true, "result": {"...": "..."}, "error": null}
```

Failures use the same envelope with `ok: false`, `result: null` and an `error`
naming its class (`MJ-022`). There is no fallback to an earlier protocol and no
path that executes a caller's JavaScript.

Three operations are admitted, all read-only:

| Operation | Answers |
| --- | --- |
| `runtime.identify` | *who is this* — name, version, session token, provenance, the lifecycle the module recorded |
| `runtime.capabilities` | *what does it admit now* — session token, protocol versions, each whitelisted operation with its `read_only` flag, and the kernel features behind them |
| `platform.device_descriptors` | *what does this Packet Tracer offer* — each available device model with the DeviceType and the module types the platform reports for it, or a reason the reading was unavailable |

The two runtime operations read the same whitelist, from the dispatcher that
owns it, so they can never describe different contracts. None of the three
reports anything it has not observed, and none certifies its own verification:
the engine cannot audit the engine, so Python decides what an answer
establishes (`MJ-011`).

## The platform boundary

`platform_adapter.js` is the one file that names `ipc`, and the architecture
gates say so by path: naming the platform is legal there and a violation in
every other packaged source (`MJ-006`, `MJ-019`). Every platform call this
artifact makes goes through one function in it, by member name, and that
function admits only the names on a declared read-only allowlist. The adapters
beside it read one subject each — device descriptors today — and name no
platform object of their own.

**The read-only proof is that list, not a list of forbidden verbs.** A
blacklist admits every name nobody thought to forbid, and once the member name
is data it cannot see the call at all. So the allowlist holds documented
getters only, a gate holds it equal to what this repository can cite, another
fails if any adapter names a platform member at a call site, and a third
compares the calls that actually ran against the same set. The mutating-verb
pattern stays as a second line of defence over the list itself.

**A defect in here is never reported as something Packet Tracer did.** Only a
call the boundary made and an answer a validator refused become an unavailable
reading; anything else reaches the caller as `ENGINE_EXCEPTION` (`MJ-022`,
`MJ-031`). On a target, `PLATFORM_CALL_FAILED` is what a missing privilege
looks like — so a bug of ours wearing that name would be indistinguishable from
real evidence.

The numbers it reports are Packet Tracer's own, read back out of the platform.
That is the point: a hand-maintained numeric mirror of a Cisco enum is correct
only until Packet Tracer changes, and nothing here would notice (`MJ-014`). The
enumeration it uses takes no `DeviceType` argument, so no such table has to
exist at all — and the gates forbid the mirror rather than the vocabulary: no
Cisco enum identifier in any packaged source, and no numeric literal in an
adapter but its own declared bounds.

**The module still requests no privilege** (`privileges: []`). No privilege is
evidenced as the one these calls need — the catalogue lives in `.pki` files
Cisco does not install — and an invented name would be denied on the target
rather than refused here (`MJ-032`). So on a real Packet Tracer the platform
call is denied until that evidence exists, and
`platform.device_descriptors` reports an unavailable reading with its reason
instead of pretending otherwise. Nothing in this tree has ever run inside
Packet Tracer, so the capability's target state is pending, not proven.

## Relationship to `EXTENSION/`

`EXTENSION/**` is the legacy *MCP Control Center* extension. It keeps serving the
existing published `.pts` and is untouched by Muejeje. It is **not** a Muejeje
artifact input: sharing a source root is what stopped the owned artifact from
evolving independently, and `TODO-SRC-ROOT` resolved that by giving Muejeje this
tree instead.

No PTBuilder source is here, and none may be added. The legacy `main.js` was not
copied — its six PTBuilder globals are exactly what Muejeje must not inherit
(`MJ-013`).

## What is deliberately not here yet

No mutation of any kind: no device, link, module, IP or CLI operation. No
transport: no HTTP, no file mailbox, no polling. The platform adapter reads and
nothing else, and it grew from one operation actually needing the platform —
not ahead of one.

The kernel is verified offline. It has never run inside Packet Tracer, and no
`.pts` has been built from these sources. See
[the requirements baseline](../docs/architecture/muejeje-pts-requirements.md).
