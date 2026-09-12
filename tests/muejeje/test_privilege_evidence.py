"""The evidence the privilege rule rests on, measured rather than restated.

Split out of `test_privileges` when that module crossed its line budget. The
two responsibilities are genuinely different: there, what the validator accepts
and refuses; here, that the things it accepts on were actually *read* — the
binary map and its pin to one `PacketTracer.exe`, the QA record that carries
the same map, and the IpcAPI symbols re-derived from Cisco's own installed
bytes (MJ-018, MJ-020, MJ-032).

This module owns the measured constants, and `test_privileges` imports the ones
it names in a refusal. Two copies of them could disagree.
"""

from __future__ import annotations

import hashlib
import re

import pytest

from tests.muejeje.support import (
    INSTALLED_HELP,
    REPO_ROOT,
    repo_manifest,
)

PRIVILEGE_RECORD = "docs/qa/muejeje-pts-privilege-map.md"
API_REFERENCE = "IpcAPI"

# Where each IpcAPI *symbol* was read from, with the bytes it was read in.
# Recorded so "Cisco names this identifier" can be re-checked rather than
# believed. None of these is a privilege token.
API_SYMBOL_EVIDENCE = {
    "PrivActivityWizard": (
        "class_activity_file.html",
        "350ceb374c5c7a118f64240994b7ddbc148c18ffae2ca29bdec7f95dbcb0f709",
    ),
    "PrivApplication": (
        "class_app_window.html",
        "0320f00edda413d760412de92c4c5166def03f42afa6f2cdca185cca0df969cb",
    ),
    "PrivGetNetwork": (
        "class_logical_workspace.html",
        "9828ee18b2886841821acd4d962b9ece08d4f9901da743098ed7cbba992558b1",
    ),
}

# The map and the call descriptors as the QA record writes them, so the record
# and the code cannot drift.
RECORDED_INDEX = re.compile(r"^\| (\d+) \| `([A-Za-z_]+)` \|$", re.MULTILINE)
RECORDED_CALL = re.compile(r"^\| `(IPC\.\w+\(\))` \| (\d+) \|$", re.MULTILINE)


def privileges():
    from src.packet_tracer_mcp.infrastructure.pts import privileges as module
    return module


def record_body() -> str:
    return (REPO_ROOT / PRIVILEGE_RECORD).read_text(encoding="utf-8")


requires_installed_reference = pytest.mark.skipif(
    not (INSTALLED_HELP / API_REFERENCE).is_dir(),
    reason="the target build is not installed; its reference cannot be read",
)


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
    assert recorded_calls == module.ROOT_CALL_PRIVILEGE_INDEX


def test_reproduction_detail_is_marked_pending_rather_than_invented():
    """An admitted gap beats a fabricated offset.

    No function, address or symbol was supplied with this evidence, so none is
    written down. Inventing one would make the mapping unfalsifiable, which is
    the failure mode `AGENTS.md` rule 6 exists to prevent.
    """
    assert privileges().BINARY_MAP_REPRODUCTION == "PENDING"
    assert "### Reproduction — `PENDING`" in record_body()


def test_the_record_keeps_the_three_facts_apart():
    """The map, the descriptors and the no-privilege run are three claims.

    Collapsing them into "GET_NETWORK_INFO is what these calls need" would
    state a conclusion no single observation supports, and would hide that the
    live half is still unverified.
    """
    body = record_body()

    assert "GET_NETWORK_INFO_BINARY_EVIDENCE = PASS" in body
    assert "GET_NETWORK_INFO_LIVE_VERIFIED   = PENDING" in body
    for heading in ("## Fact 1", "## Fact 2", "## Fact 3"):
        assert heading in body, heading



# ---------------------------------------------------------------------------
# The IpcAPI symbols, re-derived from Cisco's own bytes.
# ---------------------------------------------------------------------------

@requires_installed_reference
@pytest.mark.parametrize("symbol", sorted(API_SYMBOL_EVIDENCE))
def test_each_api_symbol_is_named_by_the_installed_reference(symbol: str):
    """Read out of Cisco's bytes, not out of our memory of them.

    The page is hashed as well as read: a future installed build that words
    this differently fails here, and the constant is re-derived against the new
    reference instead of being assumed to still hold (`AGENTS.md` rule 6).
    """
    page_name, digest = API_SYMBOL_EVIDENCE[symbol]
    page = INSTALLED_HELP / API_REFERENCE / page_name

    assert hashlib.sha256(page.read_bytes()).hexdigest() == digest, page_name
    assert symbol in page.read_text(encoding="utf-8", errors="replace")


@requires_installed_reference
def test_the_installed_reference_names_no_api_symbol_this_repository_missed():
    """The other direction: a symbol we did not record is one we cannot refuse.

    Sweeping the whole reference is what keeps the set a measurement. If a
    future build generates more of the `.pki` declarations into HTML, this
    fails and the set grows from evidence rather than from a guess.
    """
    pattern = re.compile(r"Priv[A-Z][A-Za-z]*")
    reference = INSTALLED_HELP / API_REFERENCE
    named: set[str] = set()
    for page in reference.glob("*.html"):
        named |= set(pattern.findall(page.read_text(encoding="utf-8", errors="replace")))

    assert named == set(API_SYMBOL_EVIDENCE), (
        "the installed reference names IpcAPI symbols this repository has not "
        f"recorded: {sorted(named - set(API_SYMBOL_EVIDENCE))}"
    )


# The serialized tokens that are *discriminating* in a generated C++ reference:
# the compound ones. The single-word tokens are ordinary identifiers there and
# their presence proves nothing — `IPC` is the name of a documented class,
# `FILE` a C type, and `MULTIUSER` and `APPLICATION` appear inside unrelated
# enums such as `MULTIUSERITEM`. Sweeping for those would report a mapping on
# every page that mentions the IPC class, which is not a measurement.
DISCRIMINATING_TOKENS = tuple(
    token for token in (
        "GET_NETWORK_INFO", "CHANGE_NETWORK_INFO", "SIMULATION_MODE",
        "MISC_GUI", "CHANGE_PREFERENCES", "CHANGE_GUI", "ACTIVITY_WIZARD",
    )
)


def test_the_discriminating_tokens_are_the_compound_ones():
    """The exclusion is a rule, not a list someone trimmed until it passed."""
    module = privileges()
    assert set(DISCRIMINATING_TOKENS) == {
        token for token in module.SERIALIZED_BY_INDEX if "_" in token
    }


@requires_installed_reference
def test_the_installed_reference_maps_no_symbol_onto_a_serialized_token():
    """The mapping the validator refuses to assume, checked rather than asserted.

    If a future build ever prints a serialized token in the API reference, that
    is the first evidence a mapping between the two namespaces exists — and it
    must be read and recorded, not discovered by a module being denied on a
    target.
    """
    reference = INSTALLED_HELP / API_REFERENCE
    word = {
        token: re.compile(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])")
        for token in DISCRIMINATING_TOKENS
    }
    found = [
        f"{page.name}: {token}"
        for page in reference.glob("*.html")
        for body in [page.read_text(encoding="utf-8", errors="replace")]
        for token, pattern in word.items()
        if pattern.search(body)
    ]

    assert not found, (
        "the installed reference now names serialized privilege tokens; record "
        f"what it says before the validator assumes anything: {found}"
    )
