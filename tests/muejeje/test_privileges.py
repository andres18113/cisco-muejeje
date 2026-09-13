"""A declared privilege must be the token Packet Tracer stores, on call evidence.

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

The admissible set is not a catalogue of tokens that exist. It is derived from
the *calls* this repository has target-binary evidence for, so a real token
nobody evidenced a use for is refused exactly like an invented one.

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
from tests.muejeje.test_privilege_evidence import API_SYMBOL_EVIDENCE, privileges


def schema():
    from src.packet_tracer_mcp.infrastructure.pts import manifest
    return manifest


# ---------------------------------------------------------------------------
# 1. The evidenced token is accepted.
# ---------------------------------------------------------------------------

def test_the_evidenced_serialized_tokens_are_accepted():
    """Both tokens are admissible because an evidenced call needs each.

    The gate is not a ban on privileges; it is a ban on unevidenced ones. A
    rule that refused every non-empty list would be indistinguishable from
    "privileges are not supported", and the first operation that needs one
    would delete it instead of satisfying it. `GET_NETWORK_INFO` is required by
    the two root calls; `CHANGE_NETWORK_INFO` by two read members.
    """
    assert schema()._privileges_error(["GET_NETWORK_INFO"]) is None
    assert schema()._privileges_error(["CHANGE_NETWORK_INFO"]) is None
    assert schema()._privileges_error(
        ["CHANGE_NETWORK_INFO", "GET_NETWORK_INFO"]
    ) is None


def test_an_empty_privilege_list_still_needs_no_evidence():
    """Asking for nothing cannot ask for the wrong thing (MJ-025)."""
    assert schema()._privileges_error([]) is None


# ---------------------------------------------------------------------------
# 2. An invented token is refused.
# ---------------------------------------------------------------------------

def test_an_invented_serialized_token_is_refused_and_named():
    reason = schema()._privileges_error(["GET_NETWORK_INFO", "GET_EVERYTHING"])

    assert reason is not None
    assert "no evidence" in reason
    assert "GET_EVERYTHING" in reason
    assert "GET_NETWORK_INFO" not in reason, "only the unevidenced name is at fault"


def test_the_shape_rules_still_run_before_the_evidence_rule():
    """A malformed list is malformed, whatever it would have named.

    Reporting "no evidence for ''" instead of "must hold non-empty strings"
    would send a reader looking for a privilege catalogue over a typo.
    """
    assert "non-empty strings" in (schema()._privileges_error([""]) or "")
    assert "must be a list" in (schema()._privileges_error("GET_NETWORK_INFO") or "")


# ---------------------------------------------------------------------------
# 3. The API namespace cannot stand in for the serialized one.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol", sorted(API_SYMBOL_EVIDENCE))
def test_an_ipcapi_symbol_is_refused_as_the_wrong_namespace(symbol: str):
    """The correction this module exists for.

    `PrivGetNetwork` is an identifier Cisco really does name, and it reads like
    a spelling of `GET_NETWORK_INFO`. Accepting it on that resemblance would
    let a validator admit a privilege because a *similarly named API symbol*
    exists — and the module would ship a name Packet Tracer never stores, which
    fails in the one place nothing here can observe.
    """
    reason = schema()._privileges_error([symbol])

    assert reason is not None
    assert symbol in reason
    assert "IpcAPI symbols" in reason, "the refusal must name the namespace fault"


def test_the_two_namespaces_are_disjoint_and_neither_maps_to_the_other():
    module = privileges()

    assert set(module.IPC_API_SYMBOLS).isdisjoint(module.SERIALIZED_BY_INDEX)
    assert set(module.IPC_API_SYMBOLS).isdisjoint(module.REQUIRED_PRIVILEGES)
    assert set(module.IPC_API_SYMBOLS) == set(API_SYMBOL_EVIDENCE)


# ---------------------------------------------------------------------------
# 4. The manifest holds exactly the proven minimum.
# ---------------------------------------------------------------------------

def test_the_manifest_declares_exactly_the_proven_minimum_set():
    proven = ["CHANGE_NETWORK_INFO", "GET_NETWORK_INFO"]
    assert repo_manifest()["build_options"]["privileges"] == proven
    assert list(privileges().REQUIRED_PRIVILEGES) == proven


def test_the_declared_set_is_resolved_end_to_end(tmp_path: Path):
    """It passes the audit as a resolved option, not merely as a valid string."""
    assert resolved_options()["privileges"] == ["CHANGE_NETWORK_INFO", "GET_NETWORK_INFO"]

    root, manifest_path = make_repo(tmp_path)
    manifest = manifest_document()
    manifest["build_options"] = resolved_options()
    commit_manifest(root, manifest_path, manifest)

    report = build_api().inspect_build(root, manifest_path)

    assert not any("privileges" in blocker for blocker in report["blockers"])
    assert report["packaging_state"]["unresolved_build_options"] == []


# ---------------------------------------------------------------------------
# 5. Another privilege needs evidence, not an edit.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token", ["SIMULATION_MODE", "IPC", "APPLICATION"])
def test_a_real_token_no_evidenced_call_requires_is_still_refused(token: str):
    """Least privilege, enforced against the binary's own vocabulary.

    These are tokens the target binary really carries, and `IPC` in particular
    reads like the privilege any IPC call would want. Admitting one on that
    reading is the guess this gate refuses: nothing is inferred from a
    privilege's *name*. `CHANGE_NETWORK_INFO` is now admissible for the opposite
    reason — two read members are evidenced to require it, not because its name
    reads like a mutation — so it is no longer among the refused tokens here.
    """
    reason = schema()._privileges_error(["GET_NETWORK_INFO", token])

    assert reason is not None
    assert token in reason
    assert "no call this module makes is evidenced to require it" in reason


def test_the_admissible_set_is_derived_from_call_evidence_not_written_down():
    """Editing the manifest cannot widen it; only a call descriptor can.

    The set is composed from the recorded calls and the recorded index map, so
    a privilege can only become admissible by someone recording *which call
    requires which index* — which is a claim about the target that the QA
    record and this suite both hold. Root-call and member-call evidence compose
    into one relation but stay separable, so a root answering is never read as a
    member answering.
    """
    module = privileges()
    derived = sorted({
        module.SERIALIZED_BY_INDEX[index]
        for index in module.CALL_PRIVILEGE_INDEX.values()
    })

    assert list(module.REQUIRED_PRIVILEGES) == derived
    assert list(module.REQUIRED_PRIVILEGES) == ["CHANGE_NETWORK_INFO", "GET_NETWORK_INFO"]
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
# 7. The privilege set is part of the recipe's identity.
# ---------------------------------------------------------------------------

def test_changing_the_privilege_set_changes_the_recipe_identity(tmp_path: Path):
    """A different privilege set is a different artifact, and must say so.

    Otherwise a qualification run's evidence would attach to a recipe id that
    an unqualified privilege set also answers to — which is exactly how a
    privilege changed mid-line would become invisible.
    """
    build = build_api()
    root, manifest_path = make_repo(tmp_path)

    manifest = manifest_document()
    manifest["build_options"] = resolved_options()
    commit_manifest(root, manifest_path, manifest)
    governed = build.recipe_id(build.inspect_build(root, manifest_path)["recipe"])

    manifest["build_options"] = {**resolved_options(), "privileges": []}
    commit_manifest(root, manifest_path, manifest)
    without = build.recipe_id(build.inspect_build(root, manifest_path)["recipe"])

    assert governed != without
