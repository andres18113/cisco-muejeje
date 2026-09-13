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

**What the manifest declares is a policy, not a reading of this page.** Since the
full-trust change it declares all eleven serialized tokens under
`PRIVILEGE_POLICY = FULL_TRUSTED_MODULE` — [fact 4](#fact-4--the-privilege-policy)
— and **No privilege on this page is recorded as required** by it. The evidence
here answers a different question, and goes on answering it: which privilege each
*known call* demands, which is what a least-privilege selection would be and what
a denial on the target is read against.

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
CHANGE_NETWORK_INFO_LIVE_VERIFIED            = PASS
```

`RECORDED` says the mapping and the descriptors are written down, against a
pinned binary, in a form a later reader can check against a re-derivation — and
for the two member calls, with the addresses to check them at.
`REPRODUCIBILITY` says whether such a re-derivation is possible from what is
*here*; it is not — a human with Ghidra and this binary can confirm the member
addresses, but no tool in this checkout does — so it stays `PENDING`.
`*_LIVE_VERIFIED` is the target's own answer. The `718db50` run carried
`GET_NETWORK_INFO` and reached both roots; the `6233d86` run added
`CHANGE_NETWORK_INFO` and reached both members it was introduced for. Both are
`PASS`, and neither moves `REPRODUCIBILITY` an inch — which is why there are
three states here and not two.

**Acting on this evidence and over-stating it are different things.** Each token
was selected before the target had confirmed it, and each was then confirmed by
the run that carried it, which is what makes the readings above `PASS` rather
than assumed. A call denied where this page says it should progress is a
contradiction between this page and the target, and it is recorded here as one.

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
and nothing here needs it to be: it is excluded from the declared set by name
and refused with its own reason, so no run depends on the question being settled.

**A token in this table is a token the binary carries.** Under
`FULL_TRUSTED_MODULE` every one of them except `none` is also a token this module
declares — [fact 4](#fact-4--the-privilege-policy) — and those are still two
different claims, kept in two places, because a vocabulary and a selection move
for different reasons.

**No requirement is inferred from a name, and none is inferred from the policy
either.** `CHANGE_NETWORK_INFO` reads like the privilege a mutation would want;
`IPC` reads like the privilege any IPC call would want. Neither reading is
evidence, and neither is the declaration: `CHANGE_NETWORK_INFO` is in fact 2
below because two **read** members were evidenced to require index 2, and `IPC`
is in the declared set because the policy covers the whole vocabulary — not
because any call this module makes was shown to need it.

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
`CHANGE_NETWORK_INFO`, so the **evidenced minimum** — what a least-privilege
selection would be — is derived from exactly that composition, deterministically
ordered:

```json
["CHANGE_NETWORK_INFO", "GET_NETWORK_INFO"]
```

That is `EVIDENCED_MINIMUM_PRIVILEGES`, and it is **not** what the manifest
declares; fact 4 is. It is kept because it is a separate measured fact: it is the
selection least privilege would choose, and it is what a denial on the target is
read against.

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
*read* — a device count and a device name. The `6233d86` run then carried it and
both members answered: `DeviceFactory.getAvailableDeviceCount` returned 172, and
`Device.getName` named the devices on the workspace. Nothing was written, and the
token's name is not a semantic this repository reads anything out of (`MJ-014`,
`MJ-032`).

## Fact 3 — what the target did, run by run

Three artifacts have been driven by hand on `9.0.1.0858`, and their observations
are kept apart because they carried different privilege sets:

| Artifact | Privileges | `IPC.hardwareFactory()` / `IPC.network()` | Member calls beneath |
| --- | --- | --- | --- |
| `d37ba37` | `[]` | **denied** both roots for insufficient privilege | not reached |
| `718db50` | `["GET_NETWORK_INFO"]` | **reachable** — both roots progressed | `getAvailableDeviceCount` and `getName` **privilege-denied** |
| `6233d86` | `["CHANGE_NETWORK_INFO", "GET_NETWORK_INFO"]` | **reachable** | both those members **answered**; `platform.module_descriptors` then came back `PLATFORM_ANSWER_UNUSABLE`, with **no privilege diagnostic** beside it |

The `d37ba37` run established that `privileges: []` is denied both roots. The
`718db50` run established that `GET_NETWORK_INFO` lifts that denial at both roots
— `GET_NETWORK_INFO_LIVE_VERIFIED = PASS` — and that the two members beneath
them are then denied in turn, which is what fact 2's Ghidra reading explains. The
`6233d86` run carried both tokens and both members answered, which is
`CHANGE_NETWORK_INFO_LIVE_VERIFIED = PASS` for the two members it was introduced
for, and for those members only.

**The `6233d86` run is valuable target evidence and not a clean canonical
qualification**, because its workspace fixture was corrected during execution, so
the run does not satisfy the procedure as written. What it observed is recorded
for what it is. The full observation list, and what each run did and did not
establish, is in [the offline audit](muejeje-pts-offline.md).

**Its remaining result is not a privilege fact.** `platform.module_descriptors`
came back `PLATFORM_ANSWER_UNUSABLE` with nothing printed beside it, and on this
build a privilege denial prints a diagnostic and surfaces as
`PLATFORM_CALL_FAILED` — both earlier runs show exactly that. So it is not
answered by selecting more privileges, and it was not: it is an adapter-chain
question, and what the artifact now reports about it is the `Interface.member` the
reading stopped at (`MJ-022`, `MJ-032`).

## Fact 4 — the privilege policy

```text
PRIVILEGE_POLICY = FULL_TRUSTED_MODULE
```

Muejeje is a private, local tool run by the owner of this repository, and it is
packaged as a **trusted local Script Module**. So the governed manifest declares
every serialized token fact 1 carries except `none` — eleven of them, in the
canonical `sorted` order:

```json
"privileges": [
  "ACTIVITY_WIZARD", "APPLICATION", "CHANGE_GUI", "CHANGE_NETWORK_INFO",
  "CHANGE_PREFERENCES", "FILE", "GET_NETWORK_INFO", "IPC", "MISC_GUI",
  "MULTIUSER", "SIMULATION_MODE"
]
```

**This is a decision, not a reading.** It is derived from fact 1's vocabulary
minus the non-privilege, never from fact 2's call evidence, and never typed out
in the production code. **No privilege on this page is recorded as required** by
it. The true statement, and the only one this page makes, is:

> Muejeje runs as a
> trusted local Script Module with the full Packet Tracer privilege set.
> Runtime V6 remains the capability/security boundary.

### Two policies, and why **full Packet Tracer privileges is not all Muejeje capabilities**

| Policy | What it bounds |
| --- | --- |
| `PACKET TRACER PRIVILEGE POLICY = FULL_TRUSTED_MODULE` | decides which IPC calls the Script Module process may make |
| `MUEJEJE CAPABILITY POLICY = EXPLICIT / TYPED / POSITIVE ALLOWLIST` | decides which operations Muejeje exposes to its consumers |

They are different namespaces and a reader who collapsed them would take an
eleven-token manifest for eleven new powers. The second is the real functional
boundary, and the full-trust change moved none of it: the same eight V6
operations, every one `read_only`, the same 27 admitted `Interface.member`
entries, the same failure taxonomy, the same bounds. `test_privilege_scope` holds
both against a baseline frozen at this change, written out there as literals
rather than read from the collections it is checking (`MJ-031`, `MJ-032`).

What the policy explicitly does **not** authorise: arbitrary JavaScript,
`eval`/`new Function`, an implicitly mutating operation, a new V6 operation, a new
admitted `Interface.member`, a silent fallback, or any route around the adapter
boundary.

### The vocabulary gate is unchanged

A wider policy admits more tokens. It admits no more *namespaces*, and the audit
still refuses, each with its own reason: an IpcAPI symbol such as
`PrivGetNetwork` (the wrong namespace); `none` (the binary's own name for the
absence of a privilege, never established to be storable); and any name the
pinned binary does not carry.

### And the build audit now enforces the policy itself

The vocabulary gate answers **is this a real token?** It cannot answer **is this
the declaration the policy requires?**, and for a while nothing did: every name
in `["GET_NETWORK_INFO"]` is real, so a committed manifest declaring one
privilege — or none — passed the audit and earned a `build_recipe_id` while this
page said eleven. The audit now asks both, in that order:

```text
vocabulary    every name is a serialized token the pinned binary carries
declaration   the list is exactly the 11 above, in that canonical order
```

Anything else is `BUILD_INPUT_INVALID`: no `PACKAGING_MANUAL_AVAILABLE`, no
recipe id, and a blocker naming the policy. Order is part of it because the
recipe id is taken over the manifest as written, so the same eleven tokens
reordered would be a second identity for one selection (`MJ-032`).

## The facts are not one fact

They are recorded separately because each can be true while another is wrong,
and only the separation makes that visible:

```text
binary map        index 1 is GET_NETWORK_INFO; index 2 is CHANGE_NETWORK_INFO
root descriptors  IPC.network() and IPC.hardwareFactory() require index 1
member descriptors  getAvailableDeviceCount and getName require index 2
LIVE 718db50      GET_NETWORK_INFO reached both roots; both members denied
LIVE 6233d86      both tokens carried; both members answered
policy            FULL_TRUSTED_MODULE declares all eleven tokens, required by nothing
```

What is established: the two roots need `GET_NETWORK_INFO`, the two members need
`CHANGE_NETWORK_INFO`, and the target honours both. What is **not** established
by any of it is that any *other* token is needed by any call — no run has tested
one, and the policy is why they are declared.

```text
GET_NETWORK_INFO_BINARY_EVIDENCE_RECORDED = PASS
BINARY_MAP_REPRODUCIBILITY                = PENDING
GET_NETWORK_INFO_LIVE_VERIFIED            = PASS
```

```text
CHANGE_NETWORK_INFO_MEMBER_EVIDENCE_RECORDED = PASS
CHANGE_NETWORK_INFO_LIVE_VERIFIED            = PASS
```

If a run carrying the full set is still denied at a call this page says it should
reach, that is a **contradiction between the binary evidence and the artifact's
behaviour**, and it is recorded and investigated here. There is no longer any
privilege left to select, which is the point: a refusal under
`FULL_TRUSTED_MODULE` is a fact about the call, never about the selection
(`MJ-032`).
