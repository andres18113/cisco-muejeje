"""A declared privilege must be one Cisco names, not one we invented.

`privileges` decides which IPC calls a Script Module may make: *"the security
privileges indicate which IPC calls this Script Module can make. Calls to
unselected privileges will be denied"*. So a wrong name does not fail at
packaging time — it fails at runtime, as a denied call, on the target, where
nothing in this repository can see it (MJ-032).

An **empty** list is a decision and needs no evidence: asking for nothing
cannot ask for the wrong thing (MJ-025). A **non-empty** list is a set of
names the platform will be asked to recognise, and every one of them has to
come from Cisco.

**The evidenced set is small, and that is a fact about the installation, not a
claim about Packet Tracer.** Privileges are declared in `.pki` files, which are
not installed; the generated reference leaks three identifiers through event
declarations, and those are the three this repository can point at. A name
absent from the set is *unevidenced here* — never "nonexistent". Which
privilege any particular IPC call requires is a separate unknown, recorded in
the v2 preflight inventory and still open.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.muejeje.support import (
    INSTALLED_HELP,
    build_api,
    commit_manifest,
    make_repo,
    manifest_document,
    resolved_options,
)

PRIVILEGE_REFERENCE = "IpcAPI"
# Where each evidenced identifier was read from, with the bytes it was read in.
# Recorded so the claim "Cisco names this" can be re-checked rather than
# believed, and so a differently generated future reference is noticed.
PRIVILEGE_EVIDENCE = {
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


def schema():
    from src.packet_tracer_mcp.infrastructure.pts import manifest
    return manifest


requires_installed_reference = pytest.mark.skipif(
    not (INSTALLED_HELP / PRIVILEGE_REFERENCE).is_dir(),
    reason="the target build is not installed; its reference cannot be read",
)


# ---------------------------------------------------------------------------
# The rule.
# ---------------------------------------------------------------------------

def test_an_empty_privilege_list_needs_no_evidence():
    """Asking for nothing cannot ask for the wrong thing (MJ-025)."""
    assert schema()._privileges_error([]) is None


def test_an_evidenced_privilege_is_accepted():
    """The gate is not a ban on privileges; it is a ban on invented ones.

    A rule that refused every non-empty list would be indistinguishable from
    "privileges are not supported", and the first operation that needs one
    would delete it instead of satisfying it.
    """
    assert schema()._privileges_error(sorted(PRIVILEGE_EVIDENCE)) is None


def test_an_unevidenced_privilege_is_refused_and_named():
    reason = schema()._privileges_error(["PrivGetNetwork", "PrivInvented"])

    assert reason is not None
    assert "no evidence" in reason
    assert "PrivInvented" in reason
    assert "PrivGetNetwork" not in reason, "only the unevidenced name is at fault"


def test_the_shape_rules_still_run_before_the_evidence_rule():
    """A malformed list is malformed, whatever it would have named.

    Reporting "no evidence for ''" instead of "must hold non-empty strings"
    would send a reader looking for a privilege catalogue over a typo.
    """
    assert "non-empty strings" in (schema()._privileges_error([""]) or "")
    assert "must be a list" in (schema()._privileges_error("PrivGetNetwork") or "")


# ---------------------------------------------------------------------------
# The evidence itself.
# ---------------------------------------------------------------------------

def test_the_evidenced_set_is_exactly_what_this_module_records():
    assert set(schema().EVIDENCED_PRIVILEGES) == set(PRIVILEGE_EVIDENCE)


@requires_installed_reference
@pytest.mark.parametrize("privilege", sorted(PRIVILEGE_EVIDENCE))
def test_each_evidenced_privilege_is_named_by_the_installed_reference(privilege: str):
    """Read out of Cisco's own bytes, not out of our memory of them.

    The page is hashed as well as read: a future installed build that words
    this differently fails here, and the constant is re-derived against the new
    reference instead of being assumed to still hold (`AGENTS.md` rule 6).
    """
    import hashlib

    page_name, digest = PRIVILEGE_EVIDENCE[privilege]
    page = INSTALLED_HELP / PRIVILEGE_REFERENCE / page_name

    assert hashlib.sha256(page.read_bytes()).hexdigest() == digest, page_name
    assert privilege in page.read_text(encoding="utf-8", errors="replace")


@requires_installed_reference
def test_the_installed_reference_names_no_privilege_this_repository_missed():
    """The other direction: an identifier we did not record is one we cannot use.

    Sweeping the whole reference is what keeps the set a measurement. If a
    future build generates more of the `.pki` declarations into HTML, this
    fails and the set grows from evidence rather than from a guess.
    """
    import re

    pattern = re.compile(r"Priv[A-Z][A-Za-z]*")
    reference = INSTALLED_HELP / PRIVILEGE_REFERENCE
    named: set[str] = set()
    for page in reference.glob("*.html"):
        named |= set(pattern.findall(page.read_text(encoding="utf-8", errors="replace")))

    assert named == set(PRIVILEGE_EVIDENCE), (
        "the installed reference names privileges this repository has not "
        f"recorded: {sorted(named - set(PRIVILEGE_EVIDENCE))}"
    )


# ---------------------------------------------------------------------------
# End to end, through the audit.
# ---------------------------------------------------------------------------

def test_this_repository_requests_no_privilege(tmp_path: Path):
    """`privileges: []` is what the manifest declares, and it is resolved.

    The kernel makes no platform call from any admitted operation, so it asks
    for nothing. The first operation that needs the platform reopens this with
    evidence for the one privilege it needs — and until that evidence exists,
    the honest state is an unsupported capability rather than a guessed name.
    """
    assert resolved_options()["privileges"] == []

    root, manifest_path = make_repo(tmp_path)
    manifest = manifest_document()
    manifest["build_options"] = resolved_options()
    commit_manifest(root, manifest_path, manifest)

    report = build_api().inspect_build(root, manifest_path)

    assert not any("privileges" in blocker for blocker in report["blockers"])
    assert report["packaging_state"]["unresolved_build_options"] == []
