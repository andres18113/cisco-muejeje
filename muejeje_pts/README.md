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
| 4 | `runtime_capabilities.js` | the `runtime.capabilities` operation |
| 5 | `runtime_identity.js` | the `runtime.identify` operation |
| 6 | `dispatcher_v6.js` | the whitelist and `mcpDispatchV6` |
| 7 | `lifecycle.js` | `main()` and `cleanUp()`, nothing else |

The arrows point one way — `lifecycle → dispatcher/operations → protocol +
core` — and nothing points back. An operation is never implemented inside the
dispatcher, and the dispatcher hands an operation what it needs rather than
being read by it. Operations depend on nothing but core and protocol, so among
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
naming its class (`MJ-022`). There is no fallback to an earlier protocol, no
path that executes a caller's JavaScript, and no Cisco IPC call anywhere in the
kernel — so the module requests no privilege at all (`privileges: []`).

Two operations are admitted, both read-only:

| Operation | Answers |
| --- | --- |
| `runtime.identify` | *who is this* — name, version, session token, provenance, the lifecycle the module recorded |
| `runtime.capabilities` | *what does it admit now* — session token, protocol versions, each whitelisted operation with its `read_only` flag, and the kernel features behind them |

Both read the same whitelist, from the dispatcher that owns it, so the two can
never describe different contracts. Neither reports anything it has not
observed, and neither certifies its own verification: the engine cannot audit
the engine, so Python decides what an answer establishes (`MJ-011`).

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

No device, link, module, IP or CLI operation. No transport: no HTTP, no file
mailbox, no polling. No Cisco IPC adapter — one arrives when an operation
actually needs the platform, and not before.

The kernel is verified offline. It has never run inside Packet Tracer, and no
`.pts` has been built from these sources. See
[the requirements baseline](../docs/architecture/muejeje-pts-requirements.md).
