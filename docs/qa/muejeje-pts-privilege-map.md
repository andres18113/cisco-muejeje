# Muejeje — the Script Module privilege map, read from the target binary

What a Packet Tracer privilege *is*, in the three different senses this
repository has used that word, and which of them
`build_options.privileges` declares. Everything here is tied to one binary:

| Pin | Value |
| --- | --- |
| Packet Tracer | `9.0.1.0858` |
| `bin/PacketTracer.exe` SHA-256 | `843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1` |

That hash is the same pin the build manifest's `builder` carries, and a gate
holds the two equal. A different build needs this page re-derived against it
rather than assumed to still hold (`AGENTS.md` rule 6).

## Where this evidence came from, and how strong that makes it

**The binary readings on this page were read outside this repository.** The
index map and the two root-call requirements were a reverse-engineering summary
this checkout received; the two member-call requirements are a Ghidra static
disassembly whose exact strings, addresses and registration blocks are recorded
verbatim below. Both were read against the pinned `PacketTracer.exe`, and
**nothing in it performs that reading**: no test, tool or procedure here opens
the binary and recovers the map or a call's index, so nobody reading this
repository can re-derive a row by running it.

That is why the strength of the evidence is written as several states rather
than as one word:

```text
GET_NETWORK_INFO_BINARY_EVIDENCE_RECORDED = PASS
BINARY_MAP_REPRODUCIBILITY                = PENDING
GET_NETWORK_INFO_LIVE_VERIFIED            = PASS
```

```text
CHANGE_NETWORK_INFO_MEMBER_EVIDENCE_RECORDED = PASS
CHANGE_NETWORK_INFO_LIVE_VERIFIED            = PENDING
```

`RECORDED` says the mapping and the descriptors are written down, against a
pinned binary, in a form a later reader can check against a re-derivation — and
for the two member calls, with the addresses to check them at.
`REPRODUCIBILITY` says whether such a re-derivation is possible from what is
*here*; it is not — a human with Ghidra and this binary can confirm the member
addresses, but no tool in this checkout does — so it stays `PENDING`.
`*_LIVE_VERIFIED` is the target's own answer. The `718db50` run carried
`GET_NETWORK_INFO` and reached both roots, so that one is `PASS`;
`CHANGE_NETWORK_INFO` has been carried by no run, so it is `PENDING`.

**The production decision is made on this evidence, deliberately.** The governed
manifest declares exactly the tokens these readings compose to, and the next
official LIVE run selects exactly those two tokens — so the run tests the member
requirement independently rather than inheriting it. A call denied where this
page says it should progress is a contradiction between this page and the
target, and it is recorded here as one. Acting on a reading a run will test is a
different thing from recording it as though this repository had measured it, and
only the second is forbidden.

## Three namespaces, and why they are not aliases

| Namespace | Example | What it is |
| --- | --- | --- |
| internal privilege index | `2` | the integer the binary compares a call against. Declared nowhere; it is what relates the other two |
| **serialized privilege token** | `CHANGE_NETWORK_INFO` | what Packet Tracer stores for a Script Module. **The only namespace the manifest declares** |
| IpcAPI symbol | `PrivGetNetwork` | an identifier in Cisco's generated HTML reference. Not a stored token |

`PrivGetNetwork` and `GET_NETWORK_INFO` read as though they were two spellings
of one thing. **Nothing measured says they are.** No installed page and no part
of the evidence below maps a `Priv*` symbol onto a stored token, so the
resemblance is a resemblance and the validator refuses the symbol with its own
reason. If a mapping is ever evidenced, it is recorded here first and the
validator changes afterwards — never the other way round.

The IpcAPI symbols this repository can point at are `PrivActivityWizard`,
`PrivApplication` and `PrivGetNetwork`, each read out of the installed
reference and re-derived, page by page and hash by hash, in
`tests/muejeje/test_privilege_evidence.py`. They are kept so the gate can name
them when it refuses one. They are **not** a privilege namespace.

## Fact 1 — the binary privilege map

The serialized token each internal index carries, as the supplied reading of
the pinned `PacketTracer.exe` states it:

| Index | Serialized token |
| --- | --- |
| 0 | `none` |
| 1 | `GET_NETWORK_INFO` |
| 2 | `CHANGE_NETWORK_INFO` |
| 3 | `SIMULATION_MODE` |
| 4 | `MISC_GUI` |
| 5 | `FILE` |
| 6 | `CHANGE_PREFERENCES` |
| 7 | `CHANGE_GUI` |
| 8 | `ACTIVITY_WIZARD` |
| 9 | `MULTIUSER` |
| 10 | `IPC` |
| 11 | `APPLICATION` |

Index 0 is recorded as the evidence stated it. Whether `none` is a storable
token or the binary's own name for the absence of one **was not established**,
and nothing here needs it to be: what may be declared is derived from fact 2,
never from this table, so no entry is admissible merely by appearing in it.

**A token in this table is a token that exists. It is not a token this module
may ask for**, and the two are different claims.

**No requirement is inferred from a name.** `CHANGE_NETWORK_INFO` reads like
the privilege a mutation would want; `IPC` reads like the privilege any IPC
call would want. Neither reading is evidence. `CHANGE_NETWORK_INFO` is in fact 2
below only because two **read** members were evidenced to require index 2; `IPC`
is required by no evidenced call and is refused.

### Reproducibility — `PENDING`

**The index map and the two root-call requirements were supplied without
functions, addresses or symbols**, so nothing in this checkout can re-derive
them. The two member-call requirements come with exact Ghidra addresses,
recorded verbatim in fact 2, which a human with Ghidra and the pinned binary can
confirm — but no tool *here* re-derives them either. So `BINARY_MAP_REPRODUCIBILITY`
stays `PENDING`: recording an address is not the same as this repository being
able to reproduce the reading. Promoting it means writing a tool here that opens
the binary and recovers a row, and a gate holds
`BINARY_MAP_REPRODUCIBILITY` in `privileges.py` in step with this section until
one exists. An invented offset would make the claim unfalsifiable, which is
worse than an admitted gap.

## Fact 2 — the call descriptors

Which privilege index a call requires, for the calls this repository has
recorded target-binary evidence for. Root-call and member-call evidence are
kept apart: a root answering is a different fact from a member beneath it
answering, and the `718db50` LIVE run observed exactly that split.

| Call | Required privilege index |
| --- | --- |
| `IPC.hardwareFactory()` | 1 |
| `IPC.network()` | 1 |
| `DeviceFactory.getAvailableDeviceCount()` | 2 |
| `Device.getName()` | 2 |

The first two are the roots of the entire read-only surface: every `platform.*`
reading begins at `IPC.hardwareFactory()`, every `network.*` reading at
`IPC.network()`. Their index-1 requirement was the externally supplied summary.

The last two are read members the `718db50` run reached and Packet Tracer
denied for privilege — `getAvailableDeviceCount` under
`platform.device_descriptors`, `getName` under `network.device_inventory`.
Ghidra then read their registration sites, recorded verbatim below. No other
call's requirement is claimed: not their siblings, not any call that happens to
sit in the same interface.

Composed with fact 1, index 1 is `GET_NETWORK_INFO` and index 2 is
`CHANGE_NETWORK_INFO`, and the minimum set the manifest declares is derived from
exactly that composition, deterministically ordered:

```json
"privileges": ["CHANGE_NETWORK_INFO", "GET_NETWORK_INFO"]
```

### The member registration blocks, verbatim (Ghidra, pinned `PacketTracer.exe`)

Recorded exactly as read, against the SHA-256 pinned above. Each member is
registered by a call to `FUN_14012b850` that passes the required privilege index
in `R8D` immediately before it. Both pass `0x2`.

**`DeviceFactory.getAvailableDeviceCount` — index 2.**

```text
string               getAvailableDeviceCount
address              142b6fa78
registration func    FUN_141a7b3c0
```

```asm
141a7ba08  LEA  R9,[FUN_141a7c0d0]
141a7ba0f  MOV  R8D,0x2
141a7ba15  LEA  RDX,[RBP+0x2f]
141a7ba19  MOV  RCX,RDI
141a7ba1c  CALL FUN_14012b850
```

**`Device.getName` — index 2.** The Device registration site was isolated
through neighbouring members in `FUN_141a452c0`.

```text
string               s_getName_142a1bb50
XREF                 FUN_141a452c0:141a4585e
registration func    FUN_141a452c0
```

```asm
141a4585e  MOV  RAX,[s_getName_142a1bb50]
...
141a458d1  LEA  R9,[FUN_141a4ae70]
141a458d8  MOV  R8D,0x2
141a458de  LEA  RDX,[RBP+0x1f]
141a458e2  MOV  RCX,RDI
141a458e5  CALL FUN_14012b850
```

`setName` appears with the same index 2 at a neighbouring site. It is
**corroborating evidence only** — the two members registered with `getName`
share the index it was read at — and it is used to infer the requirement of no
other member.

### `CHANGE_NETWORK_INFO` is a call requirement, not a mutation claim

Index 2 serializes as `CHANGE_NETWORK_INFO`, and the token reads like the
privilege a write would need. **That reading is not what puts it here.** What
puts it here is that the target demands index 2 for two members that only
*read* — a device count and a device name. Selecting the token broadens what
Packet Tracer will let the Script Module process **call**; it says nothing about
what Muejeje **exposes**. The Runtime V6 surface is read-only, its positive
allowlist is the authority on what this artifact does, and a gate holds that the
privilege expansion adds no mutating V6 operation and no new admitted
`Interface.member` (`test_privilege_scope`). No requirement is read from the
token's name (`MJ-014`, `MJ-032`).

## Fact 3 — what the target did, run by run

Two governed artifacts have been driven by hand on `9.0.1.0858`, and their
observations are kept apart because they carried different privilege sets:

| Artifact | Privileges | `IPC.hardwareFactory()` / `IPC.network()` | Member calls beneath |
| --- | --- | --- | --- |
| `d37ba37` | `[]` | **denied** both roots for insufficient privilege | not reached |
| `718db50` | `["GET_NETWORK_INFO"]` | **reachable** — both roots progressed | `getAvailableDeviceCount` and `getName` **privilege-denied** |

The `d37ba37` run established that `privileges: []` is denied both roots; the
`718db50` run established that `GET_NETWORK_INFO` lifts that denial at both roots
— `GET_NETWORK_INFO_LIVE_VERIFIED = PASS` — and that the two members beneath
them are then denied in turn. That member denial is what fact 2's Ghidra reading
explains: they require index 2, `CHANGE_NETWORK_INFO`, which neither run carried.
The full observation list, and what the `718db50` run did and did not establish,
is in [the offline audit](muejeje-pts-offline.md).

## The facts are not one fact

They are recorded separately because each can be true while another is wrong,
and only the separation makes that visible:

```text
binary map        index 1 is GET_NETWORK_INFO; index 2 is CHANGE_NETWORK_INFO
root descriptors  IPC.network() and IPC.hardwareFactory() require index 1
member descriptors  getAvailableDeviceCount and getName require index 2
LIVE 718db50      GET_NETWORK_INFO reached both roots; both members denied
```

What is established: the two roots need `GET_NETWORK_INFO` and the target honours
it; the two members need `CHANGE_NETWORK_INFO`. What is **not** yet established
is that carrying `CHANGE_NETWORK_INFO` makes either member progress on the
target — that is `CHANGE_NETWORK_INFO_LIVE_VERIFIED`, `PENDING` until a governed
artifact declaring it has been run.

```text
GET_NETWORK_INFO_BINARY_EVIDENCE_RECORDED = PASS
BINARY_MAP_REPRODUCIBILITY                = PENDING
GET_NETWORK_INFO_LIVE_VERIFIED            = PASS
```

```text
CHANGE_NETWORK_INFO_MEMBER_EVIDENCE_RECORDED = PASS
CHANGE_NETWORK_INFO_LIVE_VERIFIED            = PENDING
```

If a run carrying both tokens is still denied at a call this page says it should
reach, that is a **contradiction between the binary evidence and the artifact's
behaviour**, and it is recorded and investigated here. It is not answered by
selecting more privileges (`MJ-032`).
