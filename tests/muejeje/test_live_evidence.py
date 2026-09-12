"""How the next manual run must obtain and preserve what it observes.

Split out of `test_live_runbook` when that module reached its line budget, and
the two really are different work: there, what the run declares and what state
it may start from; here, where the run's numbers come from and what survives it
(MJ-018, MJ-020).

Two defects this module exists for, both found by review:

* the declaration assigned each fixture device a `workspace_index`. That is a
  position the platform handed a device over at, in **one** reading — never
  identity and never placement order — so predicting one would have had the run
  record our assumption as Packet Tracer's answer, and the first workspace that
  ordered differently would have been read as a wrong reading (MJ-002);
* the transcript was named by recipe id. A recipe id identifies the bytes a
  build *should* produce; the evidence is about the bytes that actually loaded,
  and only the artifact's own SHA-256 names those.

Every gate below reads the runbook and fails when it stops requiring what the
run needs. None runs Packet Tracer: what a person is told to do is all this
repository can check (MJ-011, MJ-015)."""

from __future__ import annotations

import re

import pytest

from tests.muejeje.support import REPO_ROOT
from tests.muejeje.test_live_runbook import RUNBOOK, runbook_body, runbook_prose

# The three arguments a qualification statement carries that address a subject.
# Each is published by a reading this run takes, and none may be typed from a
# document — that is what "evidence-driven" means for an address.
OBSERVED_ARGUMENTS = ("factory_index", "workspace_index", "module_type")

# What the immutable run header ties the evidence to. Without these the
# transcript is a list of answers with no artifact, no build and no workspace
# behind it, and nothing in it can be attributed.
RUN_HEADER_FIELDS = (
    "candidate source SHA",
    "source tree",
    "build recipe id",
    "artifact SHA-256",
    "artifact size",
    "Packet Tracer version",
    "PacketTracer.exe SHA-256",
    "privilege selection",
    "Script Engine listing",
    "workspace precondition",
    "observed device inventory",
)

# What the transcript records for every statement entered.
TRANSCRIPT_FIELDS = (
    "statement / RID",
    "returned value",
    "Packet Tracer output",
    "module start",
)

# A position written next to `workspace_index` anywhere in the declaration.
# There is no legitimate one: the runbook may name the argument, and may say
# which reading publishes it, and may never say what its value will be.
PREDICTED_WORKSPACE_INDEX = re.compile(r"workspace_index[^A-Za-z0-9_]{0,4}\d")


# ---------------------------------------------------------------------------
# Addresses are read out of a reading, not out of this repository.
# ---------------------------------------------------------------------------

def test_the_runbook_predicts_no_workspace_position_anywhere():
    """The defect this module was written for, as a pattern.

    A workspace index is where the platform handed a device over in one
    reading. Writing "Switch0 is at 0" into the declaration turns an
    observation into an expectation, and a run that met a different ordering
    would record the disagreement as the target's mistake rather than as ours.
    """
    found = PREDICTED_WORKSPACE_INDEX.findall(runbook_body())

    assert not found, (
        "the runbook predicts a workspace position; an address is read out of "
        f"the reading that reports it, never declared here: {found}"
    )


def test_the_fixture_names_devices_without_placing_them():
    """Two devices, by model and name, and no order at all."""
    prose = runbook_prose()

    assert "2960-24TT named Switch0" in prose
    assert "PC-PT named PC0" in prose
    assert "No position is part of the fixture, and none is predicted here." in prose


@pytest.mark.parametrize("argument", OBSERVED_ARGUMENTS)
def test_every_addressing_argument_is_declared_as_a_placeholder(argument: str):
    """The literals in the procedure are enterable requests, not values.

    A gate drives every statement the recipe writes through the kernel, so each
    has to be a complete admissible request — a literal address is unavoidable
    there. What makes that safe is the declaration saying, for each of them,
    that it is replaced before entry by what the preceding reading reported.
    """
    prose = runbook_prose()

    assert f"`{argument}`" in prose, argument
    assert "The literal values in the recipe's blocks are **placeholders**." in prose
    assert (
        "a placeholder entered unchanged makes the answer evidence about a "
        "position nobody observed" in prose
    )


def test_the_workspace_chain_runs_on_the_index_the_inventory_reported():
    """Inventory first, its index reused, and the identity checked back.

    Both readings take the name and the model off the same hand-over they take
    everything else from, so requiring them to re-report the intended device is
    a check their own answers can support — and the only one that catches a
    workspace that moved.
    """
    prose = runbook_prose()

    assert "**`network.device_inventory` runs first**" in prose
    assert "find the entry whose `name` is `Switch0`" in prose
    assert "Enter `network.device_ports` with **that same observed address**" in prose
    assert "`name` `Switch0` and `model` `2960-24TT`" in prose


def test_an_unstable_attribution_qualifies_no_descendant():
    """An address that pointed at two devices in one run attributes nothing.

    Calling it a descendant failure would blame a member for a workspace that
    moved; calling it a success would attribute a reading to a device that may
    not have produced it. It is its own outcome, and it stops the chain.
    """
    prose = runbook_prose()

    assert "WORKSPACE_ATTRIBUTION_UNSTABLE" in prose
    assert "**qualify no descendant member**" in prose
    assert (
        "a descendant re-reports a different device | "
        "`WORKSPACE_ATTRIBUTION_UNSTABLE`" in prose
    ), "the reading table must carry the unstable case as a row of its own"


def test_the_factory_chain_sends_back_only_what_the_platform_published():
    """The same rule one subject over, including Cisco's own vocabulary.

    A `module_type` taken from documentation, or from a fixture that worked
    once, is a number this target never emitted — and an answer about it is
    evidence about our table rather than about Packet Tracer (MJ-014).
    """
    prose = runbook_prose()

    assert "**`platform.device_descriptors` runs first**" in prose
    assert "Take a `factory_index` **that reading actually reported**" in prose
    assert "a `module_type` **the platform itself emitted in this run**" in prose
    assert (
        "**No module type is taken from this page, from Cisco's documentation "
        "or from a previous run.**" in prose
    )


def test_an_unpublished_module_type_is_recorded_as_not_exercised():
    """A missing observation stays missing rather than becoming a fabricated one."""
    prose = runbook_prose()

    assert "record `platform.module_type_support` as **not exercised**" in prose
    assert "Entering an invented number instead" in prose


def test_substituting_an_address_never_widens_a_request():
    """Bounds are Muejeje's and an observed address does not touch them (MJ-029)."""
    assert (
        "Every request stays inside the bounds the recipe declares. Substituting "
        "an observed address changes *which* subject is read, never how much is "
        "read." in runbook_prose()
    )


# ---------------------------------------------------------------------------
# One transcript, named by the artifact, opening with the run's identity.
# ---------------------------------------------------------------------------

def test_the_transcript_is_named_by_the_artifact_it_is_evidence_about():
    """A recipe id names intended bytes; a run happened to real ones.

    Two saves from one recipe id are two artifacts, and a transcript that could
    belong to either attributes to neither — so the file carries the hash
    measured outside the artifact after saving (MJ-017).
    """
    prose = runbook_prose()

    assert "docs/qa/muejeje-pts-live-transcript-<artifact_sha256>.md" in prose
    assert "<build_recipe_id>.md" not in prose, (
        "the transcript is named by the artifact, not by the recipe"
    )
    assert "**It is named by the artifact, not by the recipe.**" in prose


@pytest.mark.parametrize("field", RUN_HEADER_FIELDS)
def test_the_run_header_carries_every_identity_field(field: str):
    """Eleven facts, written before the first statement and never edited.

    Each answers a question a later reader asks of any line in the file: which
    bytes, built from what, on which build, with what selected, over which
    workspace. A transcript missing one has answers nobody can attach to
    anything.
    """
    assert field in runbook_body(), field


def test_the_run_header_is_declared_immutable_and_comes_first():
    prose = runbook_prose()

    assert "#### The run header, and it is immutable" in prose
    assert (
        "written once, before the first statement, and never edited afterwards"
        in prose
    )


def test_the_header_ties_every_workspace_address_to_the_target():
    """The inventory envelope is what gives a later index its provenance."""
    prose = runbook_prose()

    assert "the network.device_inventory envelope, verbatim" in prose
    assert (
        "a `workspace_index` in a later statement is a number with no "
        "provenance" in prose
    )


# ---------------------------------------------------------------------------
# What the transcript holds per statement, and that nothing tidies it.
# ---------------------------------------------------------------------------

def test_the_transcript_records_all_four_things_per_statement():
    """A row missing one of them cannot be read back.

    Without the statement nobody knows what was asked; without the exact
    returned value there is no result shape; without the diagnostic a failure
    has no attribution; without the module start two evaluations merge into one
    (MJ-023).
    """
    prose = runbook_prose()

    missing = [field for field in TRANSCRIPT_FIELDS if f"| {field} |" not in prose]
    assert not missing, missing
    assert "or the word `none`" in prose, (
        "a statement Packet Tracer printed nothing for is recorded as such, "
        "never left blank"
    )


def test_the_transcript_is_preserved_rather_than_tidied():
    """A rewritten envelope is a paraphrase of the target.

    Normalizing is the quiet way a summary replaces evidence: nothing about a
    pretty-printed result looks like a claim, and the field-level facts the run
    exists to capture are exactly what reformatting loses.
    """
    prose = runbook_prose()

    assert (
        "**The transcript is preserved without normalizing or rewriting its "
        "envelopes.**" in prose
    )
    assert "no field reordering" in prose


def test_the_summary_interprets_the_transcript_and_never_replaces_it():
    """Python decides what a run established, from evidence it did not write.

    The QA record may interpret the transcript afterwards; if the two ever
    disagree the transcript is what happened, because it is the only one of the
    two that was written while the target was answering (MJ-011).
    """
    prose = runbook_prose()

    assert "interprets the transcript **afterwards** and cites it" in prose
    assert "where the two disagree, the transcript is what happened" in prose
    assert "no envelope is reconstructed" in prose


def test_the_pattern_that_finds_a_predicted_position_actually_finds_one():
    """Guards the sweep above from passing because it matched nothing.

    A regex gate that cannot fire is a gate that reports every document clean,
    which is how the assigned positions survived review in the first place.
    """
    assert PREDICTED_WORKSPACE_INDEX.search("workspace_index 0: 2960-24TT")
    assert PREDICTED_WORKSPACE_INDEX.search('{"workspace_index":1}')
    assert not PREDICTED_WORKSPACE_INDEX.search(
        "the `workspace_index` the inventory reports"
    )
    assert (REPO_ROOT / RUNBOOK).is_file()
