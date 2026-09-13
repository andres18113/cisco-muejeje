"""Which privilege identifiers a Muejeje module may declare, and on what evidence.

Three different things have been called "a privilege" in this repository, and
only one of them is what `build_options.privileges` holds. Keeping them apart is
the whole point of this module (MJ-032):

| Namespace | Example | What it is |
| --- | --- | --- |
| internal privilege index | `2` | the integer the target binary compares a call against. Never declared anywhere; it is how the other two are related |
| **serialized privilege token** | `CHANGE_NETWORK_INFO` | what Packet Tracer stores for a Script Module, and therefore **the only namespace the manifest declares** |
| IpcAPI symbol | `PrivGetNetwork` | a documentation identifier that appears in Cisco's generated reference. Not a token, and not accepted here |

The two outer namespaces are *not* aliases of one another. `PrivGetNetwork` and
`GET_NETWORK_INFO` read as if they were the same thing, and nothing measured
says they are: no installed page, and nothing in the binary evidence below,
maps a `Priv*` symbol onto a stored token. A validator that accepted one
because the other exists would admit a name on a resemblance, which is exactly
the failure `MJ-032` exists to refuse — so the symbols are recorded here as
what they are, and refused with their own reason.

**Nothing is inferred from a token's name.** `CHANGE_NETWORK_INFO` reads like
the privilege a mutation would want. It is required here for the opposite
reason: the target binary demands it for two **read** members —
`DeviceFactory.getAvailableDeviceCount()` and `Device.getName()` — and index 2
serializes as `CHANGE_NETWORK_INFO`. The token broadens what Packet Tracer
would let the Script Module process *call*; it says nothing about what Muejeje
exposes. The Runtime V6 surface stays read-only, and the positive V6 allowlist
remains the authority on what this artifact does (`MJ-031`, `MJ-032`).

Declaring the wrong token is invisible until the target runs: Cisco is explicit
that *"the security privileges indicate which IPC calls this Script Module can
make. Calls to unselected privileges will be denied"*. The audit is the last
point at which a name can still be refused.

**The binary evidence below was read outside this repository**, against the
pinned `PacketTracer.exe`. Nothing here re-derives it: no test, tool or
procedure in this checkout opens that binary and recovers the map or a call's
index. So *recorded* and *reproducible* are two different states, tracked as two
constants rather than one word — even now that the member evidence carries exact
Ghidra addresses. Recording an externally read reading as if this repository had
performed it is the same failure as inventing an offset, one step later.

It is still what the production decision is made on, and that is deliberate: the
`718db50` official LIVE run selected exactly the `GET_NETWORK_INFO` this evidence
names and reached both root calls, and the next official LIVE run selects the
two tokens and tests the member requirement independently. A run denied where
the evidence says it should progress is recorded as a contradiction (MJ-032).
"""

from __future__ import annotations

from typing import Any, Iterable

# The build the privilege map below was read out of. It is pinned here as well
# as in the manifest's `builder` so the map cannot outlive the binary it
# describes: a gate holds the two equal, and a different build needs the map
# re-derived rather than assumed to still hold (`AGENTS.md` rule 6).
BINARY_EVIDENCE_VERSION = "9.0.1.0858"
BINARY_EVIDENCE_SHA256 = (
    "843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1"
)
# Who read the binary is part of the evidence. The index map and the two root
# call requirements were a summary supplied to this repository; the two member
# call requirements are a Ghidra static disassembly with exact addresses,
# recorded verbatim in the QA record. Both are external to this checkout —
# nothing here opens the binary — which is why reproducibility stays PENDING
# even though the member addresses are now written down.
BINARY_EVIDENCE_PROVENANCE = "EXTERNALLY_SUPPLIED"
MEMBER_CALL_EVIDENCE_PROVENANCE = "GHIDRA_STATIC_DISASSEMBLY"

# How strong the privilege evidence is, in the senses that can differ. They are
# separate constants because each can hold while another does not, and a single
# word for all of them would let the weakest be read as the strongest.
#
#   RECORDED         the map and the call descriptors are written down here and
#                    in the QA record, against a pinned binary. PASS.
#   REPRODUCIBILITY  whether anything in *this repository* can re-derive a row
#                    from that binary. Nothing can — the member addresses are
#                    recorded for a human to check in Ghidra, not re-derived by
#                    any tool here — so this stays PENDING.
#   *_LIVE_VERIFIED  whether selecting the token makes the calls it is evidenced
#                    for progress on the target. Only a run can say.
#                    `GET_NETWORK_INFO` reached both roots in the `718db50` run,
#                    so it is PASS. `CHANGE_NETWORK_INFO` has been carried by no
#                    run yet, so it is PENDING.
BINARY_EVIDENCE_RECORDED = "PASS"
MEMBER_STATIC_EVIDENCE_RECORDED = "PASS"
BINARY_MAP_REPRODUCIBILITY = "PENDING"
GET_NETWORK_INFO_LIVE_VERIFIED = "PASS"
CHANGE_NETWORK_INFO_LIVE_VERIFIED = "PENDING"

# The serialized privilege tokens, by internal index, as read from that binary.
# Recorded as the evidence stated it, index 0 included: the binary's own name
# for *no privilege* is `none`, and whether that is a storable token or the
# absence of one was not established. Nothing needs it decided — the requestable
# set below is derived from call evidence, never from this tuple, so no entry
# here is admitted merely by being listed.
#
# A name in this tuple is **a token that exists**, not a token this module may
# ask for. The two are different claims and stay different.
SERIALIZED_BY_INDEX = (
    "none",                 # 0
    "GET_NETWORK_INFO",     # 1
    "CHANGE_NETWORK_INFO",  # 2
    "SIMULATION_MODE",      # 3
    "MISC_GUI",             # 4
    "FILE",                 # 5
    "CHANGE_PREFERENCES",   # 6
    "CHANGE_GUI",           # 7
    "ACTIVITY_WIZARD",      # 8
    "MULTIUSER",            # 9
    "IPC",                  # 10
    "APPLICATION",          # 11
)

# Which privilege index a call requires, one entry per call this repository has
# target-binary evidence for. Root-call and member-call evidence are kept in
# two named groups so they never collapse into one another: a root answering is
# a different fact from a member beneath it answering, and the `718db50` run
# observed exactly that split — both roots reachable, two members denied.
#
# The roots are where the whole read-only surface begins: every `platform.*`
# reading at `IPC.hardwareFactory()`, every `network.*` reading at
# `IPC.network()`. Their index-1 requirement was an externally supplied summary.
ROOT_CALL_PRIVILEGE_INDEX = {
    "IPC.hardwareFactory()": 1,
    "IPC.network()": 1,
}
# Two read members the `718db50` run reached and Packet Tracer denied for
# privilege. Ghidra then read their registration sites in the pinned binary,
# each passing privilege index 2 (`MOV R8D,0x2`) to the registrar
# `FUN_14012b850`; the exact strings, addresses and blocks are recorded verbatim
# in `docs/qa/muejeje-pts-privilege-map.md`. `setName` shares that index and is
# corroborating only — no other member's requirement is inferred from it.
MEMBER_CALL_PRIVILEGE_INDEX = {
    "DeviceFactory.getAvailableDeviceCount()": 2,
    "Device.getName()": 2,
}
# The one authoritative evidenced call -> index relation. The minimum privilege
# set is derived from this, never typed, so the manifest and the call evidence
# cannot drift apart in the one direction that matters — a privilege declared
# with nothing behind it. Root and member evidence stay separable above.
CALL_PRIVILEGE_INDEX = {**ROOT_CALL_PRIVILEGE_INDEX, **MEMBER_CALL_PRIVILEGE_INDEX}

# The minimum set: exactly the tokens the recorded calls require, derived and
# never typed. Deterministically ordered by `sorted`, which is the manifest's
# canonical order for this field.
REQUIRED_PRIVILEGES = tuple(sorted({
    SERIALIZED_BY_INDEX[index] for index in CALL_PRIVILEGE_INDEX.values()
}))

# Identifiers Cisco's installed IpcAPI reference leaks through its event
# declarations. They are **documentation symbols**, kept so the gate can refuse
# them by name and say why, and they are not a privilege namespace. Where each
# was read from, with the page hash it was read in, is in
# `tests/muejeje/test_privilege_evidence.py`.
IPC_API_SYMBOLS = ("PrivActivityWizard", "PrivApplication", "PrivGetNetwork")


def evidence_error(names: Iterable[Any]) -> str | None:
    """Why this set of tokens may not be declared, or `None` when it may.

    Shape is somebody else's job: `manifest` checks that the value is a bounded,
    duplicate-free list of non-empty strings before asking this, so a typo is
    reported as a typo rather than as a missing privilege catalogue.

    Each way of being wrong gets its own reason, because they send a reader to
    three different places: an API symbol means the wrong namespace, a real
    token means the evidence for the *call* is missing, and anything else means
    the name is not a privilege at all.
    """
    unproven = sorted(set(names) - set(REQUIRED_PRIVILEGES))
    if not unproven:
        return None
    symbols = [name for name in unproven if name in IPC_API_SYMBOLS]
    if symbols:
        return (
            "must name serialized privilege tokens, not IpcAPI symbols: "
            f"{', '.join(symbols)} is a documented API identifier, and nothing "
            "maps one onto a privilege Packet Tracer stores"
        )
    existing = [name for name in unproven if name in SERIALIZED_BY_INDEX]
    if existing:
        return (
            "must name only privileges an evidenced call requires; the target "
            f"binary carries {', '.join(existing)}, and no call this module "
            "makes is evidenced to require it"
        )
    return (
        "must name a serialized privilege token the target binary carries; "
        f"this repository has no evidence for {', '.join(unproven)}"
    )
