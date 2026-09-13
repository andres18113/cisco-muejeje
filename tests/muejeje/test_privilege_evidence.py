"""The binary evidence the privilege map rests on, recorded rather than restated.

Split out of `test_privileges` when that module crossed its line budget. The
two responsibilities are genuinely different: there, what the validator accepts
and refuses; here, that what it rests on was actually *read* — the index map and
its pin to one `PacketTracer.exe`, the call descriptors, and the QA record that
carries the same map (MJ-018, MJ-020, MJ-032).

**None of it was measured here, and that is the point.** The map and the call
descriptors were read outside this checkout — the root map a supplied summary,
the member requirements a Ghidra reading — so they are *recorded* evidence and
not *reproducible* evidence, and the gates below hold the code and the QA record
to saying so. The IpcAPI symbols, which this repository *can* re-derive from
Cisco's installed bytes, are `test_privilege_api_symbols`, split out when this
module reached its own budget: evidence nobody here can reproduce and evidence
re-read on every run are two different things to be responsible for.

**The declared set is no longer derived from any of it.** The policy is
`FULL_TRUSTED_MODULE`, a deployment decision, and the last gate here holds the
record to stating that as a decision rather than as a requirement — and to
keeping it apart from what Muejeje exposes.
"""

from __future__ import annotations

import re

import pytest

from tests.muejeje.support import REPO_ROOT, repo_manifest

PRIVILEGE_RECORD = "docs/qa/muejeje-pts-privilege-map.md"

# The map and the call descriptors as the QA record writes them, so the record
# and the code cannot drift. A call row is any `Interface.member()` — a root or
# a member — so the record has to carry the whole evidenced relation, not just
# the roots.
RECORDED_INDEX = re.compile(r"^\| (\d+) \| `([A-Za-z_]+)` \|$", re.MULTILINE)
RECORDED_CALL = re.compile(r"^\| `([A-Za-z]+\.\w+\(\))` \| (\d+) \|$", re.MULTILINE)


def privileges():
    from src.packet_tracer_mcp.infrastructure.pts import privileges as module
    return module


def record_body() -> str:
    return (REPO_ROOT / PRIVILEGE_RECORD).read_text(encoding="utf-8")


def record_prose() -> str:
    """The record with its line wrapping collapsed.

    A sentence gate that matched the wrapping would fail on a reflow that
    changed nothing, and teach the next reader to stop reflowing.
    """
    return " ".join(record_body().split())


# ---------------------------------------------------------------------------
# 6. The map stays tied to the binary it was read from.
# ---------------------------------------------------------------------------

def test_the_binary_map_is_pinned_to_the_manifest_builder():
    """One binary, one map. A new build re-derives it rather than inheriting it."""
    module = privileges()
    builder = repo_manifest()["builder"]

    assert module.BINARY_EVIDENCE_VERSION == builder["version"] == "9.0.1.0858"
    assert module.BINARY_EVIDENCE_SHA256 == builder["sha256"]
    assert f"`{builder['sha256']}`" in record_body()
    assert f"`{builder['version']}`" in record_body()


def test_the_qa_record_and_the_code_carry_the_same_evidence():
    module = privileges()
    body = record_body()

    recorded_map = {int(index): token for index, token in RECORDED_INDEX.findall(body)}
    recorded_calls = {call: int(index) for call, index in RECORDED_CALL.findall(body)}

    assert recorded_map == dict(enumerate(module.SERIALIZED_BY_INDEX))
    assert recorded_calls == module.CALL_PRIVILEGE_INDEX


def test_reproducibility_is_marked_pending_rather_than_invented():
    """An admitted gap beats a fabricated offset.

    No function, address or symbol was supplied with this evidence, so none is
    written down. Inventing one would make the mapping unfalsifiable, which is
    the failure mode `AGENTS.md` rule 6 exists to prevent.
    """
    assert privileges().BINARY_MAP_REPRODUCIBILITY == "PENDING"
    assert "### Reproducibility — `PENDING`" in record_body()


# ---------------------------------------------------------------------------
# Evidence strength: three states, because each can hold while another does not.
# ---------------------------------------------------------------------------

EVIDENCE_STATES = """GET_NETWORK_INFO_BINARY_EVIDENCE_RECORDED = PASS
BINARY_MAP_REPRODUCIBILITY                = PENDING
GET_NETWORK_INFO_LIVE_VERIFIED            = PASS"""


def test_recorded_reproducible_and_live_verified_are_three_states():
    """Recorded, reproducible and live-verified are distinct states.

    A reading can be written down against a pinned SHA-256 (`RECORDED`) while no
    tool here re-derives a row (`REPRODUCIBILITY = PENDING`); whether the target
    honours a token is a third question a run answers. `GET_NETWORK_INFO` was
    reached by the `718db50` run and `CHANGE_NETWORK_INFO` by the `6233d86` run,
    so both are `PASS` — and neither makes the map reproducible here, which is
    why three states and not two.
    """
    module = privileges()

    assert module.BINARY_EVIDENCE_RECORDED == "PASS"
    assert module.MEMBER_STATIC_EVIDENCE_RECORDED == "PASS"
    assert module.BINARY_MAP_REPRODUCIBILITY == "PENDING"
    assert module.GET_NETWORK_INFO_LIVE_VERIFIED == "PASS"
    assert module.CHANGE_NETWORK_INFO_LIVE_VERIFIED == "PASS"
    assert len({
        module.MEMBER_STATIC_EVIDENCE_RECORDED,
        module.BINARY_MAP_REPRODUCIBILITY,
    }) == 2, "a recorded reading and a reproducible one are different states"


def test_the_provenance_of_the_binary_evidence_is_recorded_as_external():
    """Who read the binary is part of the evidence: map supplied, members Ghidra.

    Both are external to this checkout, which is what makes
    `BINARY_MAP_REPRODUCIBILITY = PENDING` a statement rather than an accident.
    """
    assert privileges().BINARY_EVIDENCE_PROVENANCE == "EXTERNALLY_SUPPLIED"
    assert privileges().MEMBER_CALL_EVIDENCE_PROVENANCE == "GHIDRA_STATIC_DISASSEMBLY"

    prose = record_prose()
    assert "read outside this repository" in prose
    assert "nothing in it performs that reading" in prose


@pytest.mark.parametrize("logical", [
    PRIVILEGE_RECORD,
    "docs/qa/muejeje-pts-offline.md",
    "docs/architecture/muejeje-pts-requirements.md",
    "docs/qa/muejeje-pts-privilege-live-runbook.md",
])
def test_every_authoritative_record_carries_the_three_states(logical: str):
    """One current truth, in every document that states the evidence.

    A page that carried only the strongest of the three would let a reader take
    a recorded reading for a reproducible one, or for a target result.
    """
    body = (REPO_ROOT / logical).read_text(encoding="utf-8")

    for state in EVIDENCE_STATES.splitlines():
        assert state in body, f"{logical} is missing: {state}"


def test_the_record_keeps_the_three_facts_apart():
    """The map, the descriptors and the run behaviour are separate claims.

    Collapsing them would state a conclusion no single observation supports.
    """
    body = record_body()

    assert EVIDENCE_STATES in body
    for heading in ("## Fact 1", "## Fact 2", "## Fact 3"):
        assert heading in body, heading


def test_the_record_states_the_policy_as_a_policy_and_not_as_evidence():
    """A deployment decision and a measurement are different kinds of claim.

    The declared set is `FULL_TRUSTED_MODULE` — a decision about how this module
    is deployed — while the call descriptors are readings of a binary. A record
    that stated the eleven tokens as *requirements* would present a decision as
    evidence, and one that let "full privileges" read as "all capabilities" would
    turn an eleven-token manifest into eleven new powers. Packet Tracer's
    privileges bound what the process may *call*; the V6 whitelist bounds what
    Muejeje *exposes*.
    """
    prose = record_prose()

    assert "## Fact 4" in record_body(), "the policy is its own fact"
    assert "FULL_TRUSTED_MODULE" in prose
    assert (
        "trusted local Script Module with the full Packet Tracer privilege set"
        in prose
    )
    assert "Runtime V6 remains the capability/security boundary" in prose
    assert "No privilege on this page is recorded as required" in prose
    assert "full Packet Tracer privileges is not all Muejeje capabilities" in prose
    assert "decides which IPC calls the Script Module process may make" in prose
    assert "decides which operations Muejeje exposes" in prose
