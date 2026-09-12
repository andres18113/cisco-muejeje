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

## Three namespaces, and why they are not aliases

| Namespace | Example | What it is |
| --- | --- | --- |
| internal privilege index | `1` | the integer the binary compares a call against. Declared nowhere; it is what relates the other two |
| **serialized privilege token** | `GET_NETWORK_INFO` | what Packet Tracer stores for a Script Module. **The only namespace the manifest declares** |
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
`tests/muejeje/test_privileges.py`. They are kept so the gate can name them
when it refuses one. They are **not** a privilege namespace.

## Fact 1 — the binary privilege map

The serialized token each internal index carries, observed in the pinned
`PacketTracer.exe`:

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
call would want. Neither reading is evidence, and neither appears in fact 2.

### Reproduction — `PENDING`

**The exact functions, addresses and symbols these mappings were read at are
not recorded here, because they were not supplied.** That is a gap in this
record and it is marked as one rather than filled in: an invented offset would
make the claim unfalsifiable, which is worse than an admitted gap. Recording
them means editing this section and `BINARY_MAP_REPRODUCTION` in
`src/packet_tracer_mcp/infrastructure/pts/privileges.py` together, and a gate
holds the two in step.

## Fact 2 — the call descriptors

Which privilege index a call requires, for the calls this repository has
target-binary evidence for:

| Call | Required privilege index |
| --- | --- |
| `IPC.hardwareFactory()` | 1 |
| `IPC.network()` | 1 |

These two are the roots of the entire read-only surface: every `platform.*`
reading begins at `IPC.hardwareFactory()`, every `network.*` reading at
`IPC.network()`. No other call is listed, so no other call's requirement is
claimed — not their descendants, and not any call that happens to sit in the
same interface.

Composed with fact 1, index 1 is `GET_NETWORK_INFO`, and the minimum set the
manifest declares is derived from exactly that composition:

```json
"privileges": ["GET_NETWORK_INFO"]
```

## Fact 3 — what the target did with nothing selected

The official LIVE run of the governed artifact at source
`d37ba37786107ed8128d17d589d889ee1fe9b16f`, carrying `privileges: []`, was
denied both calls by Packet Tracer for insufficient privilege. It is recorded
in full in [the offline audit](muejeje-pts-offline.md).

## The three facts are not one fact

They are recorded separately because each can be true while another is wrong,
and only the separation makes that visible:

```text
binary map        index 1 serializes as GET_NETWORK_INFO
call descriptors  IPC.network() and IPC.hardwareFactory() require index 1
official LIVE []  both calls were denied for insufficient privilege
```

Fact 3 establishes that those calls need *a* privilege — Packet Tracer's
diagnostic names the IPC call and never an identifier — and nothing about
which. Facts 1 and 2 name one, from the binary rather than from the run. What
they do **not** yet establish is that selecting `GET_NETWORK_INFO` makes either
call succeed on the target: that is `GET_NETWORK_INFO_LIVE_VERIFIED`, and it is
`PENDING` until a governed artifact declaring it has been run.

```text
GET_NETWORK_INFO_BINARY_EVIDENCE = PASS
GET_NETWORK_INFO_LIVE_VERIFIED   = PENDING
```

If a run with `GET_NETWORK_INFO` selected is still denied at either root, that
is a **contradiction between the binary evidence and the artifact's behaviour**,
and it is recorded and investigated here. It is not answered by selecting more
privileges (`MJ-032`).
