"""Broadening the privilege set widens no surface Muejeje exposes.

The manifest now declares all eleven serialized privilege tokens the pinned
binary carries, under `PRIVILEGE_POLICY = FULL_TRUSTED_MODULE`: Muejeje is a
private local tool, and it runs as a trusted Script Module. That is a decision
about what the *process* may call, and this module exists so it can never
quietly become a decision about what Muejeje *exposes*.

    full Packet Tracer privileges != all Muejeje capabilities

Two things are pinned here against a baseline **frozen at the full-trust
change**: the V6 whitelist was eight read-only operations, and the platform
allowlist the same 27 `Interface.member` entries it was before the privilege
set grew. **Growth since is written out beside the baseline, named for the
change that brought it** — the read-only link slice added two operations and
nine members, none of them a privilege change — so the baseline stays the set
somebody froze, and nothing grows by growing something else.

**Both baselines are written out here, as literals.** The member baseline used to
be `frozenset(DOCUMENTED_CALLS)` — the same collection the allowlist gate reads
— so a change that added a member to the boundary *and* to that citation list
would have satisfied this gate as well, and the two would have grown together
with nothing watching. A frozen set has to be a set somebody froze. The two are
still reconciled below, so the baseline cannot drift away from the citations
either (MJ-031, MJ-032).
"""

from __future__ import annotations

import re

from tests.muejeje.support import SCRIPT_ENGINE, repo_manifest
from tests.muejeje.test_capability_claims import admitted_operations
from tests.muejeje.test_platform_allowlist import (
    CITED_CALLS,
    MUTATING_NAME,
    admitted_calls,
)
from tests.muejeje.test_privileges import FULL_TRUSTED_SET

# The V6 whitelist as it stood at the full-trust change: eight operations,
# every one read-only. Frozen so a privilege set cannot smuggle an operation in
# beside it without failing here.
FULL_TRUST_OPERATIONS = frozenset({
    "network.device_identity",
    "network.device_inventory",
    "network.device_ports",
    "platform.device_descriptors",
    "platform.module_descriptors",
    "platform.module_type_support",
    "runtime.capabilities",
    "runtime.identify",
})
# What the read-only link slice added, under the same full-trust selection.
LINK_SLICE_OPERATIONS = frozenset({"network.link_endpoints", "network.link_inventory"})
EXPECTED_OPERATIONS = FULL_TRUST_OPERATIONS | LINK_SLICE_OPERATIONS

# The read-only member allowlist as it stood at the same change, written out
# rather than read from the collection the allowlist gate also reads. Nothing
# derives it, so nothing can grow it by growing something else.
FULL_TRUST_MEMBERS = frozenset({
    "IPC.hardwareFactory",
    "IPC.network",
    "HardwareFactory.devices",
    "DeviceFactory.getAvailableDeviceCount",
    "DeviceFactory.getAvailableDeviceAt",
    "DeviceDescriptor.getModel",
    "DeviceDescriptor.getType",
    "DeviceDescriptor.isModelSupported",
    "DeviceDescriptor.isModuleTypeSupported",
    "DeviceDescriptor.getSupportedModuleTypeCount",
    "DeviceDescriptor.getSupportedModuleTypeAt",
    "DeviceDescriptor.getRootModule",
    "ModuleDescriptor.getModel",
    "ModuleDescriptor.getType",
    "ModuleDescriptor.isHotSwappable",
    "ModuleDescriptor.getSlotCount",
    "ModuleDescriptor.getSlotTypeAt",
    "ModuleDescriptor.getModuleCount",
    "ModuleDescriptor.getModuleAt",
    "Network.getDeviceCount",
    "Network.getDeviceAt",
    "Device.getName",
    "Device.getModel",
    "Device.getType",
    "Device.getPortCount",
    "Device.getPortAt",
    "Port.getName",
})
# The members the read-only link slice added: four documented, five evidenced on
# the target. Written out for the same reason the baseline is.
LINK_SLICE_MEMBERS = frozenset({
    "Network.getLinkCount",
    "Network.getLinkAt",
    "Link.getConnectionType",
    "Port.getOwnerDevice",
    "Link.getObjectUuid",
    "Link.getPort1",
    "Link.getPort2",
    "Device.getObjectUuid",
    "Port.getObjectUuid",
})
EXPECTED_MEMBERS = FULL_TRUST_MEMBERS | LINK_SLICE_MEMBERS

READ_ONLY_FLAG = re.compile(r"read_only:\s*(true|false)")


def dispatcher_body() -> str:
    return (SCRIPT_ENGINE / "210_dispatcher_v6.js").read_text(encoding="utf-8")


def test_the_privilege_change_is_the_full_trusted_set():
    """The premise of every claim below: the set is the eleven real tokens."""
    assert repo_manifest()["build_options"]["privileges"] == FULL_TRUSTED_SET
    assert len(FULL_TRUSTED_SET) == 11


def test_the_frozen_member_baseline_is_not_the_citation_list_itself():
    """The strengthening this module needed, asserted rather than assumed.

    Equality with `CITED_CALLS` is the reconciliation — the baseline must not
    drift away from the citations either — and identity with it would be the
    hole: two collections that can only ever agree cannot catch a member added
    to both.
    """
    assert EXPECTED_MEMBERS == frozenset(CITED_CALLS)
    assert EXPECTED_MEMBERS is not CITED_CALLS
    assert len(FULL_TRUST_MEMBERS) == 27 and len(EXPECTED_MEMBERS) == 36
    assert FULL_TRUST_MEMBERS.isdisjoint(LINK_SLICE_MEMBERS)
    assert FULL_TRUST_OPERATIONS.isdisjoint(LINK_SLICE_OPERATIONS)


def test_the_privilege_change_adds_no_runtime_v6_operation():
    """The whitelist is the frozen baseline and its named additions, whatever
    the privilege set.

    The full set broadens what Packet Tracer permits the process to call. It
    adds no operation a consumer may send, and the frozen set is what proves the
    two are unrelated.
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
    """The platform allowlist is the member set it was before the tokens grew.

    Declaring a token records that Packet Tracer *would permit* a call; it
    authorises no call this artifact makes. The allowlist equality is what holds
    that true, and it is the reason eleven tokens is not eleven new reaches into
    the platform.
    """
    assert admitted_calls() == EXPECTED_MEMBERS


def test_no_admitted_member_is_shaped_like_a_mutation():
    """Even with every `CHANGE_*` and `FILE` privilege declared, none mutates."""
    assert [
        member for member in admitted_calls()
        if MUTATING_NAME.search(member.split(".")[1])
    ] == []
