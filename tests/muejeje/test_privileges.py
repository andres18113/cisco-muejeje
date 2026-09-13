"""A declared privilege must be a token Packet Tracer stores, under a named policy.

`privileges` decides which IPC calls a Script Module may make: *"the security
privileges indicate which IPC calls this Script Module can make. Calls to
unselected privileges will be denied"*. So a wrong name does not fail at
packaging time — it fails at runtime, as a denied call, on the target, where
nothing in this repository can see it (MJ-032).

Three different things have been called "a privilege" here, and this module
holds them apart (see `docs/qa/muejeje-pts-privilege-map.md`):

* the **internal privilege index**, an integer the binary compares against;
* the **serialized token**, `GET_NETWORK_INFO`, which is what the manifest
  declares and the only namespace the validator accepts;
* the **IpcAPI symbol**, `PrivGetNetwork`, a documentation identifier with no
  evidenced mapping onto a stored token — and therefore refused.

**The policy is `FULL_TRUSTED_MODULE`**, and that is a deployment decision, not
a reading of evidence: Muejeje is a private local tool, so it declares every
serialized token the pinned binary carries. What the gate still refuses is a name
the *vocabulary* does not contain — an invented token, an API symbol, and the
binary's own name for no privilege — because each of those ships a name Packet
Tracer never stores, and fails where nothing here can watch.

**Full privileges is not all capabilities**, and that is the claim this module
must never be read as making. What Muejeje exposes is the V6 whitelist, and
`test_privilege_scope` holds it frozen against exactly this change.

**Vocabulary and declaration are two questions**, and this module holds the
first: whether a name is a serialized token the pinned binary carries. Whether a
*list* of such names is the declaration `FULL_TRUSTED_MODULE` requires — all
eleven, in canonical order, so a subset of real tokens never earns a recipe id —
is `test_privilege_declaration`, added when review found the manifest gate
admitting every subset the policy forbids (MJ-032).

That the evidence was *measured* — the binary map pinned to one
`PacketTracer.exe`, the QA record carrying the same map, the IpcAPI symbols
re-read from Cisco's installed bytes — is `test_privilege_evidence`, split out
of here when this module crossed its line budget (MJ-020). The runbook that
declares the next manual run is `test_live_runbook`, split out the same way
when the run acquired a workspace fixture and a transcript to be held to.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.muejeje.support import (
    build_api,
    commit_manifest,
    make_repo,
    manifest_document,
    repo_manifest,
    resolved_options,
)
from tests.muejeje.test_privilege_api_symbols import API_SYMBOL_EVIDENCE
from tests.muejeje.test_privilege_evidence import privileges

# The eleven serialized tokens the pinned binary carries, in the manifest's
# canonical order. Written out here, where the policy is gated, so the declared
# set is checked against a list a reader can count rather than against the same
# derivation the production code performs.
FULL_TRUSTED_SET = [
    "ACTIVITY_WIZARD",
    "APPLICATION",
    "CHANGE_GUI",
    "CHANGE_NETWORK_INFO",
    "CHANGE_PREFERENCES",
    "FILE",
    "GET_NETWORK_INFO",
    "IPC",
    "MISC_GUI",
    "MULTIUSER",
    "SIMULATION_MODE",
]


def schema():
    from src.packet_tracer_mcp.infrastructure.pts import manifest
    return manifest


# ---------------------------------------------------------------------------
# 1. The policy, and the set it produces.
# ---------------------------------------------------------------------------

def test_the_policy_is_named_rather_than_left_to_be_inferred():
    """One word, so nobody has to read the set to work out which rule is in force.

    A set of eleven tokens with no policy beside it is indistinguishable from a
    minimum that grew eleven times without anybody noticing.
    """
    assert privileges().PRIVILEGE_POLICY == "FULL_TRUSTED_MODULE"


def test_the_declared_set_is_the_eleven_real_tokens():
    assert repo_manifest()["build_options"]["privileges"] == FULL_TRUSTED_SET
    assert list(privileges().DECLARED_PRIVILEGES) == FULL_TRUSTED_SET
    assert len(FULL_TRUSTED_SET) == 11


def test_the_declared_set_is_derived_from_the_vocabulary_not_typed():
    """It is the observed vocabulary minus the non-privilege, and nothing else.

    Derived rather than written down, so a token added to the binary map cannot
    be carried in the map and left out of the set — or the reverse.
    """
    module = privileges()
    derived = sorted(set(module.SERIALIZED_BY_INDEX) - {module.NON_PRIVILEGE_TOKEN})

    assert list(module.DECLARED_PRIVILEGES) == derived
    assert module.NON_PRIVILEGE_TOKEN == "none"
    assert module.NON_PRIVILEGE_TOKEN not in module.DECLARED_PRIVILEGES


def test_the_policy_set_is_not_derived_from_the_call_evidence():
    """The two are different claims, and the wider one is not read off the narrower.

    `CALL_PRIVILEGE_INDEX` is what a call *requires*. Deriving the policy set
    from it would make the declared set grow every time a call descriptor was
    recorded, and would make "declared" and "required" one word again.
    """
    module = privileges()
    from_calls = sorted({
        module.SERIALIZED_BY_INDEX[index]
        for index in module.CALL_PRIVILEGE_INDEX.values()
    })

    assert list(module.EVIDENCED_MINIMUM_PRIVILEGES) == from_calls
    assert set(module.EVIDENCED_MINIMUM_PRIVILEGES) < set(module.DECLARED_PRIVILEGES)
    assert list(module.DECLARED_PRIVILEGES) != from_calls


def test_the_evidenced_minimum_is_still_recorded_as_its_own_fact():
    """Least privilege is no longer the policy, and is still a measured fact.

    It is what a target denial is read against, so it stays derived from the
    call descriptors rather than deleted along with the rule that used it.
    """
    module = privileges()

    assert list(module.EVIDENCED_MINIMUM_PRIVILEGES) == [
        "CHANGE_NETWORK_INFO", "GET_NETWORK_INFO",
    ]
    assert sorted(module.ROOT_CALL_PRIVILEGE_INDEX) == [
        "IPC.hardwareFactory()", "IPC.network()",
    ]
    assert sorted(module.MEMBER_CALL_PRIVILEGE_INDEX) == [
        "Device.getName()", "DeviceFactory.getAvailableDeviceCount()",
    ]
    assert set(module.MEMBER_CALL_PRIVILEGE_INDEX.values()) == {2}
    assert module.SERIALIZED_BY_INDEX[2] == "CHANGE_NETWORK_INFO"
    # The two groups compose into the authoritative relation and nothing else.
    assert module.CALL_PRIVILEGE_INDEX == {
        **module.ROOT_CALL_PRIVILEGE_INDEX, **module.MEMBER_CALL_PRIVILEGE_INDEX,
    }


# ---------------------------------------------------------------------------
# 2. What the vocabulary contains.
#
# Whether a list of real tokens is a declaration a manifest may carry is a
# different question, asked separately and gated in `test_privilege_declaration`.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token", FULL_TRUSTED_SET)
def test_every_token_the_policy_covers_is_in_the_vocabulary(token: str):
    assert privileges().vocabulary_error([token]) is None


def test_an_empty_privilege_list_names_no_wrong_token():
    """Asking for nothing cannot ask for the wrong *name*.

    It can still be the wrong *declaration*, and under `FULL_TRUSTED_MODULE`
    it is — which is the second question, and the one the manifest also asks.
    """
    assert privileges().vocabulary_error([]) is None
    assert schema()._privileges_error([]) is not None


# ---------------------------------------------------------------------------
# 3. What it still refuses, each with its own reason.
# ---------------------------------------------------------------------------

def test_an_invented_serialized_token_is_refused_and_named():
    reason = schema()._privileges_error(["GET_NETWORK_INFO", "GET_EVERYTHING"])

    assert reason is not None
    assert "no evidence" in reason
    assert "GET_EVERYTHING" in reason
    assert "GET_NETWORK_INFO" not in reason, "only the unknown name is at fault"


def test_the_binarys_name_for_no_privilege_is_refused_as_what_it_is():
    """`none` is index 0 of the map and is not a privilege.

    Whether Packet Tracer would even store it was never established, so it gets
    its own reason rather than being reported as a token nobody has evidence
    for — which would send a reader looking for evidence that cannot exist.
    """
    reason = schema()._privileges_error(["none"])

    assert reason is not None
    assert "absence of one" in reason
    assert "none" in reason
    assert "none" in privileges().SERIALIZED_BY_INDEX, (
        "the refusal is about a name the map really carries"
    )


def test_the_shape_rules_still_run_before_the_policy_rule():
    """A malformed list is malformed, whatever it would have named.

    Reporting "no evidence for ''" instead of "must hold non-empty strings"
    would send a reader looking for a privilege catalogue over a typo.
    """
    assert "non-empty strings" in (schema()._privileges_error([""]) or "")
    assert "must be a list" in (schema()._privileges_error("GET_NETWORK_INFO") or "")


@pytest.mark.parametrize("symbol", sorted(API_SYMBOL_EVIDENCE))
def test_an_ipcapi_symbol_is_refused_as_the_wrong_namespace(symbol: str):
    """The correction this module exists for, and the policy does not lift it.

    `PrivGetNetwork` is an identifier Cisco really does name, and it reads like
    a spelling of `GET_NETWORK_INFO`. Accepting it on that resemblance would
    let a validator admit a privilege because a *similarly named API symbol*
    exists — and the module would ship a name Packet Tracer never stores, which
    fails in the one place nothing here can observe. A wider policy admits more
    tokens; it admits no more namespaces.
    """
    reason = schema()._privileges_error([symbol])

    assert reason is not None
    assert symbol in reason
    assert "IpcAPI symbols" in reason, "the refusal must name the namespace fault"


def test_the_two_namespaces_are_disjoint_and_neither_maps_to_the_other():
    module = privileges()

    assert set(module.IPC_API_SYMBOLS).isdisjoint(module.SERIALIZED_BY_INDEX)
    assert set(module.IPC_API_SYMBOLS).isdisjoint(module.DECLARED_PRIVILEGES)
    assert set(module.IPC_API_SYMBOLS) == set(API_SYMBOL_EVIDENCE)


# ---------------------------------------------------------------------------
# 4. The declaration resolves end to end.
# ---------------------------------------------------------------------------

def test_the_declared_set_is_resolved_end_to_end(tmp_path: Path):
    """It passes the audit as a resolved option, not merely as a valid string."""
    assert resolved_options()["privileges"] == FULL_TRUSTED_SET

    root, manifest_path = make_repo(tmp_path)
    manifest = manifest_document()
    manifest["build_options"] = resolved_options()
    commit_manifest(root, manifest_path, manifest)

    report = build_api().inspect_build(root, manifest_path)

    assert not any("privileges" in blocker for blocker in report["blockers"])
    assert report["packaging_state"]["unresolved_build_options"] == []


# ---------------------------------------------------------------------------
# 5. The privilege set is part of the recipe's identity.
# ---------------------------------------------------------------------------

def test_changing_the_privilege_set_changes_the_recipe_identity(tmp_path: Path):
    """A different privilege set is a different artifact, and must say so.

    Otherwise a qualification run's evidence would attach to a recipe id that
    a different privilege set also answers to — which is exactly how a
    privilege changed mid-line would become invisible. Asserted against both
    the empty set and the set this candidate superseded, so the full-trust
    declaration cannot collide with the minimum it replaced.
    """
    build = build_api()
    root, manifest_path = make_repo(tmp_path)

    manifest = manifest_document()
    manifest["build_options"] = resolved_options()
    commit_manifest(root, manifest_path, manifest)
    governed = build.recipe_id(build.inspect_build(root, manifest_path)["recipe"])

    identities = {governed}
    for superseded in ([], list(privileges().EVIDENCED_MINIMUM_PRIVILEGES)):
        manifest["build_options"] = {
            **resolved_options(), "privileges": superseded,
        }
        commit_manifest(root, manifest_path, manifest)
        identities.add(
            build.recipe_id(build.inspect_build(root, manifest_path)["recipe"])
        )

    assert len(identities) == 3
