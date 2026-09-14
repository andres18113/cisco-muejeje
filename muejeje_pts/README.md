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
It is declared once, in `build_options.engine_script_order`, and the file names
spell it: the Scripting Interface lists engine files by name, and no control to
reorder them has been observed. Each name starts with its place — a three-digit
prefix in steps of ten, so a file can be inserted without renaming the kernel —
and the build audit refuses a declared order the names do not sort in:

| File | Responsibility |
| --- | --- |
| `010_core.js` | constants and session state; depends on nothing |
| `020_protocol_v6.js` | the response envelope and the failure taxonomy |
| `030_validation_v6.js` | bounded envelope admission, and the bounds themselves |
| `040_arguments_v6.js` | an operation's own argument rules, against what it declares |
| `050_platform_reading.js` | what a platform reading is: its bounds, its words, its value rules |
| `060_platform_adapter.js` | the **only** file that names `ipc`; the read-only call boundary |
| `070_network_adapter.js` | the workspace device inventory, through that boundary |
| `080_network_identity_adapter.js` | one workspace device's identity, in one reading |
| `083_network_link_endpoints_adapter.js` | one workspace link's two ends, with the UUIDs that attribute them, in one reading |
| `086_network_link_inventory_adapter.js` | the workspace link inventory, through that boundary |
| `090_network_ports_adapter.js` | one workspace device's ports beside its identity, in one reading |
| `100_platform_device_adapter.js` | the device-descriptor reading, through that boundary |
| `110_platform_module_adapter.js` | the bounded chassis-module reading, through that boundary |
| `120_platform_support_adapter.js` | the module-type support reading, through that boundary |
| `130_network_identity.js` | the `network.device_identity` operation |
| `140_network_inventory.js` | the `network.device_inventory` operation |
| `143_network_link_endpoints.js` | the `network.link_endpoints` operation |
| `146_network_link_inventory.js` | the `network.link_inventory` operation |
| `150_network_ports.js` | the `network.device_ports` operation |
| `160_platform_discovery.js` | the `platform.device_descriptors` operation |
| `170_platform_modules.js` | the `platform.module_descriptors` operation |
| `180_platform_support.js` | the `platform.module_type_support` operation |
| `190_runtime_capabilities.js` | the `runtime.capabilities` operation |
| `200_runtime_identity.js` | the `runtime.identify` operation |
| `210_dispatcher_v6.js` | the whitelist and `mcpDispatchV6` |
| `220_lifecycle.js` | `main()` and `cleanUp()`, nothing else |

The arrows point one way — `lifecycle → dispatcher → operations → adapter →
protocol + core` — and nothing points back. An operation is never implemented
inside the dispatcher, and the dispatcher hands an operation what it needs
rather than being read by it. No operation depends on another, so among
themselves they are ordered alphabetically: a rule, rather than an accident a
later reader would have to reverse-engineer.

Shaping an answer and deciding whether a request deserves one are two
responsibilities, so they are two files. `030_validation_v6.js` owns every bound V6
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

**This table is the catalogue.** The whitelist lives in `210_dispatcher_v6.js` and
is written out for a reader here, in one place: five documents each carrying a
copy is five that a new operation puts out of step, so every other document
names whichever operations it has a reason to name and a gate holds this one
complete (`MJ-008`).

Ten operations are admitted, all read-only:

| Operation | Answers |
| --- | --- |
| `runtime.identify` | *who is this* — name, version, session token, provenance, the lifecycle the module recorded |
| `runtime.capabilities` | *what does it admit now* — session token, protocol versions, each whitelisted operation with its `read_only` flag, and the kernel features behind them |
| `platform.device_descriptors` | *what does this Packet Tracer offer* — each available device model with the `factory_index` it was read at, the DeviceType and the module types the platform reports for it, or a reason the reading was unavailable |
| `platform.module_descriptors` | *what is one model described as carrying* — the chassis of the model at a `factory_index`, node by node, each with where it sits in the chassis, its type, its slot types, its hot-swap flag and the positions inside its module count that answered `null`, or a reason the reading was unavailable |
| `platform.module_type_support` | *does this model accept this module type* — for the model at a `factory_index`, the descriptor's own answer for one type value, with the model and DeviceType read back beside it, or a reason the reading was unavailable |
| `network.device_inventory` | *what does this Packet Tracer currently hold* — a bounded window over the devices on the workspace, each with the `workspace_index` it was read at, the name the platform gave it and the object UUID it reports, or a reason the reading was unavailable |
| `network.device_identity` | *what is the device at this position* — the name, model, DeviceType and object UUID the platform reports for the device at a `workspace_index`, all read in that same observation, or a reason the reading was unavailable |
| `network.device_ports` | *what ports does the device at this position have* — the name, model and object UUID of the device at a `workspace_index` and a bounded window of its ports, each with the `port_index` it was read at, the name the platform gave it and its object UUID, all from that one device in one observation, or a reason the reading was unavailable |
| `network.link_inventory` | *which links does this workspace hold* — a bounded window over the links on the workspace, each with the `workspace_link_index` it was read at, the connection type the platform reports as its own opaque number, and its object UUID, or a reason the reading was unavailable |
| `network.link_endpoints` | *which two ports does the link at this position join* — for the link at a `workspace_link_index`, its object UUID and, as `port1` and `port2`, each end's port name, port object UUID and owner device object UUID, all off that one link in one observation, or a reason the reading was unavailable |

The two runtime operations read the same whitelist, from the dispatcher that
owns it, so they can never describe different contracts. The platform ones
compose: the first reports which models exist and at which index, and the other
two ask about the model at one of those indexes — its chassis, or whether it
accepts a module type the platform itself named. None of them needs a
DeviceType, a module-type table or a catalogue of model names to be useful,
which is what keeps them free of a Cisco enum mirror (`MJ-014`).

**What one operation publishes, the next one admits.** A factory index, a
workspace index, a workspace link index and a `ModuleType` are values a consumer
relays among them, so
each has one declared domain and no consuming rule narrows it: this runtime
never hands out a value it will then refuse (`MJ-029`). That domain is
fidelity, not a ceiling — any whole number JSON carries exactly — so every
index below `available_count` can be sent back, and a topology of any size is
read one bounded window at a time. Each index is reported where it was read,
never left to be derived from an offset.

**Three address domains, and none answers for another.** A position in the
factory, a position among the workspace's devices and a position among its links
are numbers of the same shape in three different enumerations, so every argument
and field that carries one says which: `factory_index` and `factory_offset`,
`workspace_index` and `workspace_offset`, `workspace_link_index` and
`workspace_link_offset`. A value relayed by the name it was published under
reaches the domain it came from; sent to another, it is refused as
`INVALID_ARGS` rather than read as a different subject. An operation about one model or one
device also requires the index that selects it — nothing is ever read "by
default" at position 0 (`MJ-029`).

`network.*` is the second namespace, and the difference from `platform.*` is
worth knowing: the factory describes what a *model* can be, and never changes
under a reading; a workspace describes what a *session* holds right now, and
two readings may legitimately differ with nothing wrong. The inventory reports
what is there and assumes nothing about it — no count, no naming scheme, no
role, no link, no address (`MJ-002`).

`network.device_identity` is one reading of one device, and deliberately not a
join. A workspace position is where the platform handed a device over in *that*
observation — it is not stable identity, and it is not a factory index. Nothing
relates a workspace device to a factory descriptor: not by index, not by name,
not by model string. Cisco does document `Device.getDescriptor()`, which would
answer that properly from the device itself, and it is a further subject with
its own bounds and its own evidence rather than a field this reading may grow
(`MJ-002`, `MJ-015`).

`network.device_ports` is the same kind of reading one step further, and it
re-reports the identity on purpose. It selects the device at a
`workspace_index`, reads its name and model, and reads that same device's ports
in the same call, after one hand-over — so the ports are attributable without a
consumer combining an identity read at one moment with ports read at another,
which on a changing workspace would describe a device that never existed. Ports
come one bounded window at a time from `port_offset`; each carries the
`port_index` it was read at, the name the platform gave it and the object UUID it
reports, and nothing more: no link followed, no address, no state, and no
parsing of the name (`MJ-002`, `MJ-029`, `MJ-031`).

`network.link_inventory` and `network.link_endpoints` read the workspace's
links, and **decide nothing about what kind of link they were handed**. Cisco's
installed pages document a link's ends only on `Cable` and `Antenna`, while the
link enumeration hands over a `Link`; the endpoint and UUID getters are admitted
on `Link`, `Port` and `Device` as target-evidenced members, and no `Cable` or
`Antenna` member is admitted. So a link that does not offer an end is
`PLATFORM_MEMBER_ABSENT` at `Link.getPort1`, never a link without ends, and the
connection type is published as the platform's number and translated by nothing
(`MJ-014`). An end is related to a port and a device by the object UUIDs the
platform reports on both sides — never by a name, a position, or JavaScript
reference equality — and a UUID is the platform's answer in a session: what it
means across a restart, a save or a re-creation is not claimed. A link that
exists is not a link that converged, and no state is read (`MJ-002`, `MJ-031`).

None of the ten reports anything it has not observed, and none certifies its
own verification: the engine cannot audit the engine, so Python decides what an
answer establishes (`MJ-011`).

## The platform boundary

`060_platform_adapter.js` is the one file that names `ipc`, and the architecture
gates say so by path: naming the platform is legal there and a violation in
every other packaged source (`MJ-006`, `MJ-019`). Every platform call this
artifact makes goes through it, by **interface member** — `Device.getModel` and
`DeviceDescriptor.getModel` are two entries, not one name — and it admits only
the members on a declared read-only allowlist, asked of a platform object it
handed out itself as that interface. The adapters
beside it read one subject each — the device factory, the chassis of one model,
whether one model accepts one module type, the devices on the workspace, the
identity of one of them, one device's ports beside that identity, the links on
the workspace, and one link's two ends — and name no platform object of their own.

**The read-only proof is that list, not a list of forbidden verbs.** A
blacklist admits every name nobody thought to forbid, and once the member name
is data it cannot see the call at all. So the allowlist holds getters only, each
on one of two bases — DOCUMENTED on its own interface's installed page, or
TARGET_EVIDENCED on the object the boundary hands out as that interface and on
no page of its own — and a gate holds it equal to what this repository can cite,
re-reads each documented entry off its own page and holds each target-evidenced
one off it, another fails if
any adapter names a platform member at a call site or leaves one unspelled, and
a third compares the calls that actually ran, interface by interface, against
the same set. The mutating-verb pattern stays as a second line of defence over
the list itself.

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

**The module requests every privilege Packet Tracer offers a Script Module** —
all eleven serialized tokens, under `PRIVILEGE_POLICY = FULL_TRUSTED_MODULE`.
Muejeje is a private, local tool run by its owner, packaged as a **trusted Script
Module**, so the declared set is the pinned binary's whole vocabulary minus
`none` — derived from it, never typed out. It is a deployment decision, and **no
token is declared as required**. The audit refuses a name outside that
vocabulary — an IpcAPI symbol such as `PrivGetNetwork`, the non-privilege
`none`, or an invented token — **and any declaration that is not exactly those
eleven in that order**: a subset of real tokens is `BUILD_INPUT_INVALID` and
earns no recipe id, so a manifest cannot quietly package a narrower selection
than the policy it claims (`MJ-032`).

> Muejeje runs as a
> trusted local Script Module with the full Packet Tracer privilege set.
> Runtime V6 remains the capability/security boundary.

**Full Packet Tracer privileges is not all Muejeje capabilities.** Packet
Tracer's privileges decide which IPC calls this module's *process* may make. What
Muejeje *exposes* is the V6 whitelist — ten operations, every one read-only,
over a 36-entry `Interface.member` allowlist. The full-trust change moved
neither, and the read-only link slice that grew both changed no privilege
(`MJ-031`).

Which privilege each *call* requires is a separate fact, and it still holds.
Index 1, `GET_NETWORK_INFO`, is required for both `IPC.hardwareFactory()` and
`IPC.network()` — the two calls the whole read-only surface roots on. Index 2,
`CHANGE_NETWORK_INFO`, is required for two **read** members,
`DeviceFactory.getAvailableDeviceCount()` and `Device.getName()`, read from the
pinned `PacketTracer.exe` by Ghidra; the token reads like a write privilege and
is evidenced for the opposite reason.

The root map was **supplied from outside this repository** and the member
requirements are a **Ghidra static disassembly**; nothing here re-derives
either, so they are recorded evidence and not reproducible evidence. Both have
since been reached live:

```text
GET_NETWORK_INFO_BINARY_EVIDENCE_RECORDED = PASS
BINARY_MAP_REPRODUCIBILITY                = PENDING
GET_NETWORK_INFO_LIVE_VERIFIED            = PASS
```

```text
CHANGE_NETWORK_INFO_MEMBER_EVIDENCE_RECORDED = PASS
CHANGE_NETWORK_INFO_LIVE_VERIFIED            = PASS
```

**What a real Packet Tracer did is recorded, and not generalised.** Four
artifacts have run on `9.0.1.0858`. The `d37ba37` artifact, carrying
`privileges: []`, had its kernel answer — identify, capabilities, every refusal
class, and a stop and a start — while every `platform.*` and `network.*` reading
came back `PLATFORM_CALL_FAILED`, Packet Tracer printing that the module lacked
the privilege for the root call. The `718db50` artifact, carrying
`GET_NETWORK_INFO`, reached both roots and was then denied the two members
`getAvailableDeviceCount` and `getName` — the denial the index-2 Ghidra evidence
explains. The `6233d86` artifact carried both tokens and both members answered:
`platform.device_descriptors`, `platform.module_type_support` and
`network.device_inventory` were `OBSERVED`, while `platform.module_descriptors`
came back `PLATFORM_ANSWER_UNUSABLE` with no privilege diagnostic beside it. That
run's workspace fixture was corrected during execution, so it is **target
evidence and not a canonical qualification**, and those capabilities' target
state stays pending rather than proven. The `504a6e6` artifact carried all eleven
tokens: five of the six platform and workspace readings came back `OBSERVED`, and
`platform.module_descriptors` stopped at `ModuleDescriptor.getModuleAt`, argument
0 — a `null` inside a module count. An investigation on the same build found a
null there is an ordinary answer, so the walk now records it in
`null_module_positions` and goes on; what a null means physically is not
claimed, and no transcript of that run is committed.

**An unavailable reading now names where it stopped.** Beside
`unavailable_reason`, every platform and workspace reading reports
`unavailable_member` — the `Interface.member` the reading stopped at — and
`unavailable_argument`, the position or value that call was made with. It names a
place and never a cause: the reason stays what happened, and a privilege denial
is still only what Packet Tracer printed beside the call (`MJ-022`, `MJ-031`).

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

The kernel is verified offline, and it has also answered inside Packet Tracer:
the governed artifact at `d37ba37` was packaged from these sources, loaded and
started on `9.0.1.0858`, and answered from its own engine —
`V6_KERNEL_VERIFIED = PASS`, recorded in
[the offline audit](../docs/qa/muejeje-pts-offline.md). Every platform call the
same run made was denied, so that verdict covers the kernel and nothing wider.
See [the requirements baseline](../docs/architecture/muejeje-pts-requirements.md).
