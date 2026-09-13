"""Broadening the privilege set widens no surface Muejeje exposes.

The manifest now declares `CHANGE_NETWORK_INFO` beside `GET_NETWORK_INFO`,
because two **read** members of the target require privilege index 2. The token
reads like the privilege a mutation would want, and this module exists so that
resemblance can never quietly become one: a privilege change may broaden what
Packet Tracer would let the Script Module process *call*, and it must not add a
mutating Runtime V6 operation or a new admitted `Interface.member`.

Both are pinned here against a baseline frozen at the two-privilege change. The
V6 whitelist is eight read-only operations; the platform allowlist is the same
member set it was before the privilege grew. A future change that added either
alongside a privilege would fail here, which is what keeps the privilege the
authority on what the process may call and the positive V6 allowlist the
authority on what Muejeje exposes (MJ-031, MJ-032).
"""

from __future__ import annotations

import re

from tests.muejeje.support import SCRIPT_ENGINE, repo_manifest
from tests.muejeje.test_capability_claims import admitted_operations
from tests.muejeje.test_platform_allowlist import (
    DOCUMENTED_CALLS,
    MUTATING_NAME,
    admitted_calls,
)

# The V6 whitelist as it stands at the two-privilege change: eight operations,
# every one read-only. Frozen so a privilege added later cannot smuggle an
# operation in beside it without failing here.
EXPECTED_OPERATIONS = frozenset({
    "network.device_identity",
    "network.device_inventory",
    "network.device_ports",
    "platform.device_descriptors",
    "platform.module_descriptors",
    "platform.module_type_support",
    "runtime.capabilities",
    "runtime.identify",
})

# The read-only member allowlist as it stands at the same change. It is the set
# `test_platform_allowlist` already pins as documented; re-pinned here so a
# privilege change that also grew the allowlist is caught as a privilege-scope
# regression, not only as an allowlist one.
EXPECTED_MEMBERS = frozenset(DOCUMENTED_CALLS)

# The two evidenced tokens, in the manifest's canonical order.
EVIDENCED_PRIVILEGES = ["CHANGE_NETWORK_INFO", "GET_NETWORK_INFO"]

READ_ONLY_FLAG = re.compile(r"read_only:\s*(true|false)")


def dispatcher_body() -> str:
    return (SCRIPT_ENGINE / "210_dispatcher_v6.js").read_text(encoding="utf-8")


def test_the_privilege_change_is_the_two_evidenced_tokens():
    """The premise of every claim below: the set is exactly the two tokens."""
    assert repo_manifest()["build_options"]["privileges"] == EVIDENCED_PRIVILEGES


def test_the_privilege_change_adds_no_runtime_v6_operation():
    """The whitelist is the same eight operations, whatever the privilege set.

    `CHANGE_NETWORK_INFO` broadens what Packet Tracer permits the process to
    call. It does not add an operation a consumer may send, and the frozen set
    is what proves the two are unrelated.
    """
    assert admitted_operations() == EXPECTED_OPERATIONS


def test_every_admitted_operation_stays_read_only():
    """No operation the privilege change touched, or any other, may mutate.

    Read from the dispatcher table directly: every `read_only` flag is `true`,
    and there is one per admitted operation, so a mutating operation cannot be
    added without either a `false` here or a missing flag.
    """
    flags = READ_ONLY_FLAG.findall(dispatcher_body())

    assert flags, "the dispatcher table was not read"
    assert set(flags) == {"true"}
    assert len(flags) == len(EXPECTED_OPERATIONS)


def test_no_admitted_operation_is_named_like_a_mutation():
    """A second, cheaper line over the read-only flags, on the operation names."""
    mutating = re.compile(r"\.(?:set|add|remove|create|delete|clear|save|write)_")
    offenders = [op for op in admitted_operations() if mutating.search(op)]

    assert offenders == []


def test_the_privilege_change_adds_no_admitted_interface_member():
    """The platform allowlist is the member set it was before the token grew.

    Adding `CHANGE_NETWORK_INFO` records that the target *requires* index 2 for
    two members this artifact already calls; it authorises no new call. The
    allowlist equality is what holds that true.
    """
    assert admitted_calls() == EXPECTED_MEMBERS


def test_no_admitted_member_is_shaped_like_a_mutation():
    """Even with a `CHANGE_*` privilege declared, no admitted member mutates."""
    assert [
        member for member in admitted_calls()
        if MUTATING_NAME.search(member.split(".")[1])
    ] == []
