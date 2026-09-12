"""Which privilege identifiers a Muejeje module may declare, and on what evidence.

Three different things have been called "a privilege" in this repository, and
only one of them is what `build_options.privileges` holds. Keeping them apart is
the whole point of this module (MJ-032):

| Namespace | Example | What it is |
| --- | --- | --- |
| internal privilege index | `1` | the integer the target binary compares a call against. Never declared anywhere; it is how the other two are related |
| **serialized privilege token** | `GET_NETWORK_INFO` | what Packet Tracer stores for a Script Module, and therefore **the only namespace the manifest declares** |
| IpcAPI symbol | `PrivGetNetwork` | a documentation identifier that appears in Cisco's generated reference. Not a token, and not accepted here |

The two outer namespaces are *not* aliases of one another. `PrivGetNetwork` and
`GET_NETWORK_INFO` read as if they were the same thing, and nothing measured
says they are: no installed page, and nothing in the binary evidence below,
maps a `Priv*` symbol onto a stored token. A validator that accepted one
because the other exists would admit a name on a resemblance, which is exactly
the failure `MJ-032` exists to refuse — so the symbols are recorded here as
what they are, and refused with their own reason.

Declaring the wrong token is invisible until the target runs: Cisco is explicit
that *"the security privileges indicate which IPC calls this Script Module can
make. Calls to unselected privileges will be denied"*. The audit is the last
point at which a name can still be refused.
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

# The serialized privilege tokens, by internal index, as observed in that
# binary. Recorded as the evidence stated it, index 0 included: the binary's
# own name for *no privilege* is `none`, and whether that is a storable token
# or the absence of one was not established. Nothing needs it to be decided —
# the requestable set below is derived from call evidence, never from this
# tuple, so no entry here is admitted merely by being listed.
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

# How the map was reproduced — the function, address or symbol each mapping was
# read at — is **not recorded, because it was not supplied**. That is a gap in
# the record and it is marked as one: an invented offset would make the claim
# unfalsifiable, which is worse than an admitted gap. Recording the addresses
# means changing this constant and the QA record together.
BINARY_MAP_REPRODUCTION = "PENDING"

# Which privilege index a call requires, one entry per call this repository has
# target-binary evidence for. These two are the root calls the whole read-only
# surface goes through: every `platform.*` reading begins at
# `IPC.hardwareFactory()` and every `network.*` reading at `IPC.network()`.
#
# This is a *separate* fact from the map above, and from what the target did
# with `privileges: []`. The map says what index 1 is called; this says which
# calls want index 1; the official LIVE run says both calls were denied when
# nothing was selected. None of the three implies either of the others, and
# collapsing them into "GET_NETWORK_INFO is what these calls need" would state
# a conclusion no single observation supports.
#
# Nothing is inferred from a token's *name*. `CHANGE_NETWORK_INFO` reads like
# the privilege a write would want and no evidence here says so, so no call is
# listed against it.
ROOT_CALL_PRIVILEGE_INDEX = {
    "IPC.hardwareFactory()": 1,
    "IPC.network()": 1,
}

# The minimum set: exactly the tokens the recorded calls require, derived and
# never typed. Hand-writing it would let the manifest and the evidence drift
# apart in the one direction that matters — a privilege declared with nothing
# behind it.
REQUIRED_PRIVILEGES = tuple(sorted({
    SERIALIZED_BY_INDEX[index] for index in ROOT_CALL_PRIVILEGE_INDEX.values()
}))

# Identifiers Cisco's installed IpcAPI reference leaks through its event
# declarations. They are **documentation symbols**, kept so the gate can refuse
# them by name and say why, and they are not a privilege namespace. Where each
# was read from, with the page hash it was read in, is in
# `tests/muejeje/test_privileges.py`.
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
