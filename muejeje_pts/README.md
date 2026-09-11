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
| 3 | `validation_v6.js` | bounded envelope admission, and the bounds themselves |
| 4 | `arguments_v6.js` | an operation's own argument rules, against what it declares |
| 5 | `platform_reading.js` | what a platform reading is: its bounds, its words, its value rules |
| 6 | `platform_adapter.js` | the **only** file that names `ipc`; the read-only call boundary |
| 7 | `network_adapter.js` | the workspace device inventory, through that boundary |
| 8 | `platform_device_adapter.js` | the device-descriptor reading, through that boundary |
| 9 | `platform_module_adapter.js` | the bounded chassis-module reading, through that boundary |
| 10 | `platform_support_adapter.js` | the module-type support reading, through that boundary |
| 11 | `network_inventory.js` | the `network.device_inventory` operation |
| 12 | `platform_discovery.js` | the `platform.device_descriptors` operation |
| 13 | `platform_modules.js` | the `platform.module_descriptors` operation |
| 14 | `platform_support.js` | the `platform.module_type_support` operation |
| 15 | `runtime_capabilities.js` | the `runtime.capabilities` operation |
| 16 | `runtime_identity.js` | the `runtime.identify` operation |
| 17 | `dispatcher_v6.js` | the whitelist and `mcpDispatchV6` |
| 18 | `lifecycle.js` | `main()` and `cleanUp()`, nothing else |

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

**This table is the catalogue.** The whitelist lives in `dispatcher_v6.js` and
is written out for a reader here, in one place: five documents each carrying a
copy is five that a new operation puts out of step, so every other document
names whichever operations it has a reason to name and a gate holds this one
complete (`MJ-008`).

Six operations are admitted, all read-only:

| Operation | Answers |
| --- | --- |
| `runtime.identify` | *who is this* — name, version, session token, provenance, the lifecycle the module recorded |
| `runtime.capabilities` | *what does it admit now* — session token, protocol versions, each whitelisted operation with its `read_only` flag, and the kernel features behind them |
| `platform.device_descriptors` | *what does this Packet Tracer offer* — each available device model with the index it was read at, the DeviceType and the module types the platform reports for it, plus the highest index this runtime will address, or a reason the reading was unavailable |
| `platform.module_descriptors` | *what is one model described as carrying* — the chassis of the model at a factory index, node by node, each with the index it was read at, its type, its slot types and its hot-swap flag, or a reason the reading was unavailable |
| `platform.module_type_support` | *does this model accept this module type* — the descriptor's own answer for one type value, with the model and DeviceType read back beside it, or a reason the reading was unavailable |
| `network.device_inventory` | *what does this Packet Tracer currently hold* — a bounded window over the devices on the workspace, each with the index it was read at and the name the platform gave it, or a reason the reading was unavailable |

The two runtime operations read the same whitelist, from the dispatcher that
owns it, so they can never describe different contracts. The platform ones
compose: the first reports which models exist and at which index, and the other
two ask about the model at one of those indexes — its chassis, or whether it
accepts a module type the platform itself named. None of them needs a
DeviceType, a module-type table or a catalogue of model names to be useful,
which is what keeps them free of a Cisco enum mirror (`MJ-014`).

**What one operation publishes, the next one admits.** A factory index and a
`ModuleType` are values a consumer relays among them, so each has one declared
domain and no consuming rule narrows it: this runtime never hands out
a value it will then refuse (`MJ-029`). Both are reported rather than left to
be derived — a model carries the index it was read at, and a window reports the
highest index this runtime will address, because `available_count` says how
many models the platform has and not which of them can be asked about.

`network.*` is the second namespace, and the difference from `platform.*` is
worth knowing: the factory describes what a *model* can be, and never changes
under a reading; a workspace describes what a *session* holds right now, and
two readings may legitimately differ with nothing wrong. The inventory reports
what is there and assumes nothing about it — no count, no naming scheme, no
role, no link, no address (`MJ-002`).

None of the six reports anything it has not observed, and none certifies its
own verification: the engine cannot audit the engine, so Python decides what an
answer establishes (`MJ-011`).

## The platform boundary

`platform_adapter.js` is the one file that names `ipc`, and the architecture
gates say so by path: naming the platform is legal there and a violation in
every other packaged source (`MJ-006`, `MJ-019`). Every platform call this
artifact makes goes through one function in it, by member name, and that
function admits only the names on a declared read-only allowlist. The adapters
beside it read one subject each — the device factory, the chassis of one model,
whether one model accepts one module type, and the devices on the workspace —
and name no platform object of their own.

**The read-only proof is that list, not a list of forbidden verbs.** A
blacklist admits every name nobody thought to forbid, and once the member name
is data it cannot see the call at all. So the allowlist holds documented
getters only, a gate holds it equal to what this repository can cite, another
fails if any adapter names a platform member at a call site, and a third
compares the calls that actually ran against the same set. The mutating-verb
pattern stays as a second line of defence over the list itself.

**A defect in here is never reported as something Packet Tracer did.** Only
something the boundary observed about the platform, and an answer a validator
refused, become an unavailable reading; anything else — a bug, or an argument
outside an adapter's own bounds — reaches the caller as `ENGINE_EXCEPTION`
(`MJ-022`, `MJ-031`). The boundary also checks that an admitted member is there
before calling it, and reports `PLATFORM_MEMBER_ABSENT` when it is not: nothing
was called, so nothing was refused, and a reading that says otherwise would be
a refusal nobody performed.

The numbers it reports are Packet Tracer's own, read back out of the platform.
That is the point: a hand-maintained numeric mirror of a Cisco enum is correct
only until Packet Tracer changes, and nothing here would notice (`MJ-014`). The
enumeration it uses takes no `DeviceType` argument, so no such table has to
exist at all — and the gates forbid the mirror rather than the vocabulary: no
Cisco enum identifier in any packaged source, and no numeric literal in an
adapter but its own declared bounds.

**The module still requests no privilege** (`privileges: []`). No privilege is
evidenced as the one these calls need — the catalogue lives in `.pki` files
Cisco does not install — and a name nobody can cite is refused at audit time
rather than shipped to find out (`MJ-032`).

**What a real Packet Tracer then does is unknown, and this tree does not guess
it.** Whether an unprivileged Script Module may make these calls, and which
privilege (if any) each one needs, are questions only a target run answers. The
operations report whichever reading comes back — an answer, or an unavailable
one with its reason — and nothing here predicts which. Nothing in this tree has
ever run inside Packet Tracer, so both capabilities' target state is pending,
not proven.

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
transport: no HTTP, no file mailbox, no polling. The platform surface reads and
nothing else, and each part of it grew from an operation that actually needed
it — never ahead of one.

The kernel is verified offline. It has never run inside Packet Tracer, and no
`.pts` has been built from these sources. See
[the requirements baseline](../docs/architecture/muejeje-pts-requirements.md).
