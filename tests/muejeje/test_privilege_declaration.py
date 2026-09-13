"""Under `FULL_TRUSTED_MODULE` the manifest declares the whole set, or nothing builds.

Two different questions had one answer, and the weaker one was what the build
audit enforced (MJ-032):

A. **vocabulary** — is this name a serialized privilege token the pinned binary
   carries? A question about *one* name, and the only thing that can refuse an
   IpcAPI symbol, `none`, or an invented token, each with its own reason.
B. **declaration** — is this the set the policy in force says a Muejeje manifest
   declares? A question about the *list*, and under `FULL_TRUSTED_MODULE` there
   is exactly one admissible answer: `list(DECLARED_PRIVILEGES)`, in canonical
   order.

The audit asked only A. Every name in `["GET_NETWORK_INFO"]` is a real token, so
a committed manifest declaring one privilege — or none — passed the build audit
and earned a `build_recipe_id` and `PACKAGING_MANUAL_AVAILABLE`, while
`PRIVILEGE_POLICY` said all eleven. A recipe id over that manifest identifies a
module the policy does not permit, and the artifact it names would carry a
privilege selection nothing in this repository had agreed to.

`test_privileges` holds the policy and the vocabulary themselves; here only what
a *manifest* may declare, and what the audit does when it declares something
else. The end-to-end gates are what make this a build-audit rule rather than a
validator opinion: the same synthetic checkout is audited twice, so what the
second audit refuses can only be the privilege list.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.muejeje.support import (
    INSTALLED_BUILDER,
    build_api,
    commit_manifest,
    make_repo,
    manifest_document,
    resolved_options,
)
from tests.muejeje.test_privilege_evidence import privileges
from tests.muejeje.test_privileges import FULL_TRUSTED_SET, schema

# What a partial declaration looks like, one way of being partial per entry.
# Every name in every one of them is a legitimate serialized token, which is
# the point: the vocabulary gate has nothing to say about any of these.
PARTIAL_DECLARATIONS = {
    "nothing at all": [],
    "one token": ["GET_NETWORK_INFO"],
    "the evidenced minimum": ["CHANGE_NETWORK_INFO", "GET_NETWORK_INFO"],
    "all but one": [name for name in FULL_TRUSTED_SET if name != "IPC"],
}
# The whole set, and not the declaration: canonical order is part of the rule,
# because the recipe id is taken over the manifest's own bytes and a reordered
# list is a different recipe identifying the same selection.
NONCANONICAL_ORDERS = {
    "reversed": list(reversed(FULL_TRUSTED_SET)),
    "one pair swapped": (
        FULL_TRUSTED_SET[:3] + [FULL_TRUSTED_SET[4], FULL_TRUSTED_SET[3]]
        + FULL_TRUSTED_SET[5:]
    ),
}
INADMISSIBLE = {**PARTIAL_DECLARATIONS, **NONCANONICAL_ORDERS}


def audit_with(tmp_path: Path, declaration: list[str], **kwargs: object) -> dict:
    """Audit a clean synthetic checkout whose manifest declares `declaration`."""
    root, manifest_path = make_repo(tmp_path)
    manifest = manifest_document()
    manifest["build_options"] = {**resolved_options(), "privileges": declaration}
    commit_manifest(root, manifest_path, manifest)
    return build_api().inspect_build(root, manifest_path, **kwargs)


# ---------------------------------------------------------------------------
# 1. The two validations are separate, and answer different questions.
# ---------------------------------------------------------------------------

def test_the_vocabulary_answers_about_a_token_and_not_about_a_declaration():
    """`GET_NETWORK_INFO` is a real token. It is not a declaration.

    Keeping A answerable on its own is what lets the manifest report an IpcAPI
    symbol as the wrong namespace rather than as a set of the wrong size.
    """
    module = privileges()

    assert module.vocabulary_error(["GET_NETWORK_INFO"]) is None
    assert module.vocabulary_error([]) is None
    assert module.declaration_error(["GET_NETWORK_INFO"]) is not None
    assert module.declaration_error([]) is not None


def test_the_only_admissible_declaration_is_the_canonical_full_set():
    module = privileges()

    assert module.declaration_error(list(module.DECLARED_PRIVILEGES)) is None
    assert module.declaration_error(FULL_TRUSTED_SET) is None
    assert schema()._privileges_error(FULL_TRUSTED_SET) is None


def test_the_declared_set_is_the_vocabulary_the_policy_covers():
    """Two constants, because they answer A and B and could diverge.

    `SERIALIZED_PRIVILEGE_TOKENS` is what the binary carries; what a manifest
    declares is whatever `PRIVILEGE_POLICY` makes of it. Under
    `FULL_TRUSTED_MODULE` those are the same eleven names, derived rather than
    typed, so neither can be edited without the other following.
    """
    module = privileges()

    assert list(module.SERIALIZED_PRIVILEGE_TOKENS) == FULL_TRUSTED_SET
    assert list(module.DECLARED_PRIVILEGES) == list(module.SERIALIZED_PRIVILEGE_TOKENS)
    assert module.NON_PRIVILEGE_TOKEN not in module.SERIALIZED_PRIVILEGE_TOKENS


# ---------------------------------------------------------------------------
# 2. What the declaration rule refuses, and how it says so.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", sorted(INADMISSIBLE))
def test_no_declaration_but_the_canonical_full_set_is_admissible(case: str):
    reason = schema()._privileges_error(INADMISSIBLE[case])

    assert reason is not None, case
    assert "FULL_TRUSTED_MODULE" in reason, "the reason must name the policy"


@pytest.mark.parametrize("case", sorted(PARTIAL_DECLARATIONS))
def test_a_partial_declaration_is_refused_for_what_it_omits(case: str):
    """Named, so a reader fixes the manifest instead of reading the policy."""
    reason = schema()._privileges_error(PARTIAL_DECLARATIONS[case])
    missing = [
        name for name in FULL_TRUSTED_SET if name not in PARTIAL_DECLARATIONS[case]
    ]

    assert "omits" in (reason or "")
    for name in missing:
        assert name in reason, name


@pytest.mark.parametrize("case", sorted(NONCANONICAL_ORDERS))
def test_the_whole_set_in_another_order_is_refused_as_an_order(case: str):
    """A different fault needs a different reason.

    Reporting "this omits ACTIVITY_WIZARD" about a list that carries all eleven
    would send a reader looking for a missing token that is right there.
    """
    reason = schema()._privileges_error(NONCANONICAL_ORDERS[case])

    assert "canonical" in (reason or "")
    assert "in another order" in reason
    assert "omits" not in reason


def test_the_vocabulary_diagnostics_still_answer_before_the_declaration_rule():
    """A wider rule about the list must not swallow the reason about a name.

    Each of these is *also* not the canonical eleven, so a declaration-first
    validator would report every one of them as a set of the wrong size and
    lose the namespace fault that is the actual defect (MJ-032).
    """
    error = schema()._privileges_error

    assert "IpcAPI symbols" in (error(["PrivGetNetwork"]) or "")
    assert "absence of one" in (error(["none"]) or "")
    assert "no evidence" in (error(["GET_EVERYTHING"]) or "")
    assert "no evidence" in (error(FULL_TRUSTED_SET + ["GET_EVERYTHING"]) or "")


def test_the_shape_rules_still_answer_before_either(tmp_path: Path):
    """A typo is reported as a typo, not as a privilege policy violation."""
    error = schema()._privileges_error

    assert "must be a list" in (error("GET_NETWORK_INFO") or "")
    assert "non-empty strings" in (error([""]) or "")
    assert "must not repeat" in (error(FULL_TRUSTED_SET + ["IPC"]) or "")


# ---------------------------------------------------------------------------
# 3. End to end: a clean committed manifest, and how far it gets.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", sorted(INADMISSIBLE))
def test_a_clean_checkout_declaring_less_than_the_policy_is_input_invalid(
    tmp_path: Path, case: str,
):
    """The regression this module exists for, driven through the real audit.

    Nothing else about the checkout is wrong: it is committed, its declared
    inputs are all on disk and tracked, its every other build option is this
    repository's own. Before the declaration rule existed, each of these
    reached `PACKAGING_MANUAL_AVAILABLE` and earned a `build_recipe_id` —
    a governed identity for a build the policy forbids.
    """
    report = audit_with(tmp_path, INADMISSIBLE[case])

    assert report["status"] == "BUILD_INPUT_INVALID", report["blockers"]
    assert report["packaging_state"]["manual"] == "PACKAGING_MANUAL_UNAVAILABLE"
    assert report["build_recipe_id"] is None
    assert any(
        "privileges" in blocker and "FULL_TRUSTED_MODULE" in blocker
        for blocker in report["blockers"]
    ), report["blockers"]


def test_the_refusal_outranks_a_missing_builder(tmp_path: Path):
    """An invalid input is a different state from an unusable toolchain.

    Audited on a machine with no Packet Tracer, a partial declaration must
    still report `BUILD_INPUT_INVALID` rather than `BUILD_TOOLCHAIN_BLOCKED`:
    the manifest is wrong whether or not anything could build it, and the
    precedence in `classify_build_state` is what keeps the two apart (MJ-016).
    """
    report = audit_with(tmp_path, ["GET_NETWORK_INFO"])

    assert report["status"] == "BUILD_INPUT_INVALID", report["blockers"]
    assert "missing explicit builder path" in report["blockers"]


@pytest.mark.skipif(
    not INSTALLED_BUILDER.is_file(),
    reason="the pinned Packet Tracer build is not installed on this machine",
)
@pytest.mark.parametrize("case", sorted(INADMISSIBLE))
def test_only_the_privilege_list_stops_an_otherwise_packageable_checkout(
    tmp_path: Path, case: str,
):
    """The same checkout, audited twice, with a verified builder in hand.

    The canonical declaration reaches `PACKAGING_MANUAL_AVAILABLE` with a
    recipe id, so what the second audit refuses can only be the privilege list
    — not the fixture, not the builder, not an unresolved option.
    """
    packageable = audit_with(
        tmp_path / "full", FULL_TRUSTED_SET, builder_path=INSTALLED_BUILDER,
    )
    assert packageable["status"] == "PACKAGING_MANUAL_AVAILABLE", (
        packageable["blockers"]
    )
    assert packageable["build_recipe_id"] is not None

    report = audit_with(
        tmp_path / case.replace(" ", "-"),
        INADMISSIBLE[case],
        builder_path=INSTALLED_BUILDER,
    )

    assert report["source"]["clean"] is True, "the checkout is still clean"
    assert report["packaging_state"]["unresolved_build_options"] == []
    assert report["status"] == "BUILD_INPUT_INVALID"
    assert report["packaging_state"]["manual"] == "PACKAGING_MANUAL_UNAVAILABLE"
    assert report["build_recipe_id"] is None


@pytest.mark.skipif(
    not INSTALLED_BUILDER.is_file(),
    reason="the pinned Packet Tracer build is not installed on this machine",
)
def test_the_real_manifest_declares_what_the_policy_requires(tmp_path: Path):
    """This repository's own declaration, audited as a build option.

    `resolved_options` reads the real manifest, so a privilege set edited there
    fails here rather than in the pinned-builder audit run by hand.
    """
    report = audit_with(
        tmp_path, resolved_options()["privileges"], builder_path=INSTALLED_BUILDER,
    )

    assert resolved_options()["privileges"] == FULL_TRUSTED_SET
    assert report["status"] == "PACKAGING_MANUAL_AVAILABLE", report["blockers"]
    assert report["recipe"]["build_options"]["privileges"] == FULL_TRUSTED_SET
