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
of here when this module crossed its line budget (MJ-020).
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

def test_the_evidenced_serialized_token_is_accepted():
    """`GET_NETWORK_INFO` is admissible because a call is evidenced to need it.

    The gate is not a ban on privileges; it is a ban on unevidenced ones. A
    rule that refused every non-empty list would be indistinguishable from
    "privileges are not supported", and the first operation that needs one
    would delete it instead of satisfying it.
    """
    assert schema()._privileges_error(["GET_NETWORK_INFO"]) is None


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
    assert repo_manifest()["build_options"]["privileges"] == ["GET_NETWORK_INFO"]
    assert list(privileges().REQUIRED_PRIVILEGES) == ["GET_NETWORK_INFO"]


def test_the_declared_set_is_resolved_end_to_end(tmp_path: Path):
    """It passes the audit as a resolved option, not merely as a valid string."""
    assert resolved_options()["privileges"] == ["GET_NETWORK_INFO"]

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

@pytest.mark.parametrize("token", ["CHANGE_NETWORK_INFO", "IPC", "APPLICATION"])
def test_a_real_token_no_evidenced_call_requires_is_still_refused(token: str):
    """Least privilege, enforced against the binary's own vocabulary.

    These are tokens the target binary really carries, and `IPC` in particular
    reads like the privilege any IPC call would want. Admitting one on that
    reading is the guess this gate refuses: nothing is inferred from a
    privilege's *name*.
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
    record and this suite both hold.
    """
    module = privileges()
    derived = sorted({
        module.SERIALIZED_BY_INDEX[index]
        for index in module.ROOT_CALL_PRIVILEGE_INDEX.values()
    })

    assert list(module.REQUIRED_PRIVILEGES) == derived
    assert sorted(module.ROOT_CALL_PRIVILEGE_INDEX) == [
        "IPC.hardwareFactory()", "IPC.network()",
    ]


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




# ---------------------------------------------------------------------------
# The runbook that declares the next manual run.
# ---------------------------------------------------------------------------

RUNBOOK = "docs/qa/muejeje-pts-privilege-live-runbook.md"

# The state a person must find before starting the run. Written here as the
# claim, and read back from the document, so the two cannot drift — a runbook
# that promoted a milestone the repository has not is how a denied call becomes
# a qualification (MJ-033).
EXPECTED_ENTRY_STATE = """OFFICIAL_PACKAGING_PROVED = PASS
V6_KERNEL_VERIFIED        = PASS
M1_CORE_READY             = YES

GET_NETWORK_INFO_BINARY_EVIDENCE = PASS
GET_NETWORK_INFO_LIVE_VERIFIED   = PENDING

M0B_TARGET_API_BASELINED = NOT_COMPLETE
M2_CORE_READY            = NO
M3_CORE_READY            = NO
ZERO_CHANGE_CUTOVER      = NOT_ACHIEVED"""


def runbook_body() -> str:
    from tests.muejeje.support import REPO_ROOT
    return (REPO_ROOT / RUNBOOK).read_text(encoding="utf-8")


def runbook_prose() -> str:
    """The runbook with its line wrapping collapsed.

    A sentence gate that matched the wrapping would fail on a reflow that
    changed nothing, and teach the next reader to stop reflowing.
    """
    return " ".join(runbook_body().split())


def test_the_runbook_declares_the_privilege_set_the_manifest_does():
    """The one field the run exists to change, read from the manifest.

    A runbook naming a set the manifest does not declare would have a person
    package an artifact no recipe id identifies.
    """
    body = runbook_body()

    assert repo_manifest()["build_options"]["privileges"] == ["GET_NETWORK_INFO"]
    assert "**`GET_NETWORK_INFO`, and nothing else**" in body
    assert (
        "Confirm on the module itself that only `GET_NETWORK_INFO` is selected"
        in runbook_prose()
    )


def test_the_runbook_drives_the_whole_qualification_not_just_the_roots():
    prose = runbook_prose()

    assert "the whole existing qualification" in prose
    assert (
        "continue through all the platform and network operations in the same "
        "run" in prose
    )


def test_the_runbook_keeps_root_and_descendant_qualification_apart():
    prose = runbook_prose()

    assert "It does **not** invalidate the root result" in prose
    assert "record the exact `Interface.member` that was reached" in prose


def test_the_runbook_forbids_widening_privilege_on_a_denial():
    prose = runbook_prose()

    assert "**Do not add privileges.**" in prose
    assert "**No privilege is changed mid-artifact.**" in prose
    assert "contradiction" in prose


def test_the_runbook_states_the_entry_state_this_repository_actually_holds():
    assert EXPECTED_ENTRY_STATE in runbook_body()
