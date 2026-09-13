"""The IpcAPI symbols Cisco's installed reference names, re-read from its bytes.

Split out of `test_privilege_evidence` when that module reached its line budget.
The two responsibilities are different in kind, and the difference is the point
of both: there, evidence about the target *binary*, which was read outside this
repository and cannot be re-derived here; here, evidence this module re-derives
itself, every time it runs, out of Cisco's own installed HTML (MJ-018, MJ-020,
MJ-032).

**A `Priv*` symbol is not a privilege token.** `PrivGetNetwork` and
`GET_NETWORK_INFO` read as two spellings of one thing, and nothing measured says
they are. These gates are what keeps that a measurement rather than an opinion:
each symbol is re-found in the page it was read from, the whole reference is
swept for one nobody recorded, and it is swept again for any sign that Cisco's
pages name a serialized token — which would be the first evidence a mapping
between the two namespaces exists, and would have to be recorded before any
validator assumed it.

The refusal these constants drive is `test_privileges`; the privilege policy they
are refused *under* is `FULL_TRUSTED_MODULE`, and it admits no extra namespace.
"""

from __future__ import annotations

import hashlib
import re

import pytest

from tests.muejeje.support import INSTALLED_HELP
from tests.muejeje.test_privilege_evidence import privileges

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

requires_installed_reference = pytest.mark.skipif(
    not (INSTALLED_HELP / API_REFERENCE).is_dir(),
    reason="the target build is not installed; its reference cannot be read",
)


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
