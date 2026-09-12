"""What survives the next manual LIVE run: one transcript per execution.

Split out of `test_live_evidence` when the run acquired an identity model of its
own (MJ-018, MJ-020). Two contradictions this module exists for, both found by
review:

* the transcript was named by the artifact alone, so a second execution of the
  same saved `.pts` had nowhere to go but over the first. Artifact identity and
  run identity are different facts, and the name has to carry both;
* its header was immutable and written before the first statement, and it also
  required the `network.device_inventory` envelope — which does not exist until
  a statement has run. A header can hold only what is known before the run.

The inventory is still the provenance anchor for every later workspace address;
it simply lives where an observation lives, in the append-only body."""

from __future__ import annotations

import re

import pytest

from tests.muejeje.test_live_runbook import runbook_body, runbook_prose

TRANSCRIPT_PATH = "docs/qa/muejeje-pts-live-transcript-<artifact_sha256>-<run_id>.md"

# The pre-run header, field by field and in order. Every one is known before the
# first qualification statement is entered, and the gate below holds the
# document to exactly this list — so an observation cannot be added to it.
PRE_RUN_HEADER_FIELDS = (
    "run_id",
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
)

# Words that only an observation could supply. None may appear in the header.
OBSERVATION_WORDS = ("network.device_inventory", "inventory", "envelope", "operation_rid")

# What the body records for every statement entered.
BODY_FIELDS = (
    "statement / RID",
    "relay input",
    "returned value",
    "Packet Tracer output",
    "module start",
)

HEADER_HEADING = "#### The pre-run header, and it is immutable"
TEXT_BLOCK = re.compile(r"```text\n(.*?)\n```", re.DOTALL)


def header_lines() -> list[str]:
    """The lines of the first text block after the header's heading."""
    body = runbook_body()
    return TEXT_BLOCK.search(body[body.index(HEADER_HEADING):]).group(1).splitlines()


def header_field(line: str) -> str:
    """A header line's field name: everything before its column gap."""
    return re.split(r"\s{2,}", line.strip(), maxsplit=1)[0]


# ---------------------------------------------------------------------------
# Identity: the artifact that ran, and the execution that ran it.
# ---------------------------------------------------------------------------

def test_each_execution_has_its_own_transcript():
    """The name carries both identities, because they are two facts."""
    prose = runbook_prose()

    assert TRANSCRIPT_PATH in prose
    assert (
        "**Artifact identity and run identity are different, and the name "
        "carries both.**" in prose
    )


def test_neither_recipe_id_nor_artifact_hash_alone_names_an_execution():
    """A second run of one artifact must never land on top of the first.

    Named by recipe id, two saves from one build collide; named by artifact
    hash alone, two executions of one save collide. Only the pair is unique.
    """
    prose = runbook_prose()

    assert "Neither the recipe id nor the artifact hash alone identifies an execution." in prose
    assert "must never overwrite, extend or be merged into the first" in prose
    assert "-<artifact_sha256>.md" not in prose
    assert "<build_recipe_id>.md" not in prose


def test_the_run_id_exists_before_qualification_and_never_reuses_a_file():
    prose = runbook_prose()

    assert "**`run_id` is created before qualification begins**" in prose
    assert "If a transcript with that name already exists, the `run_id` is wrong" in prose
    assert "Another run's file is never opened for writing." in prose


# ---------------------------------------------------------------------------
# The header: only what exists before the first statement.
# ---------------------------------------------------------------------------

def test_the_pre_run_header_holds_exactly_the_pre_run_facts():
    """Field by field, in order, and nothing else.

    Holding the header to an exact list — rather than checking that each field
    is mentioned somewhere — is what makes it impossible to slip an
    observation back into it: an extra line fails here as surely as a missing
    one.
    """
    assert [header_field(line) for line in header_lines()] == list(PRE_RUN_HEADER_FIELDS)


@pytest.mark.parametrize("word", OBSERVATION_WORDS)
def test_no_observation_is_a_header_field(word: str):
    """The contradiction this module was written for.

    A header written before the first statement cannot contain what a
    statement returns. The previous revision required the inventory envelope
    there, which made the header either impossible to write first or
    impossible to keep immutable.
    """
    assert word not in "\n".join(header_lines()), word


def test_the_header_is_written_once_before_the_first_statement():
    prose = runbook_prose()

    assert "**Nothing a qualification statement observes belongs in the header.**" in prose
    assert "written once and never edited afterwards" in prose
    assert "Every field above is known before `typeof mcpDispatchV6` is entered." in prose


# ---------------------------------------------------------------------------
# The body: chronological, append-only, and where the inventory lives.
# ---------------------------------------------------------------------------

def test_the_body_is_append_only():
    prose = runbook_prose()

    assert "**chronological and append-only for the whole run**" in prose
    assert "nothing already written is edited, reordered or removed" in prose


def test_the_inventory_anchors_later_workspace_addresses_from_the_body():
    """Moving it out of the header keeps its job: every later index cites it.

    A `workspace_index` in a later statement is provenance-free unless the
    transcript says which observation it was read out of, so the body names
    that observation by `operation_rid`.
    """
    prose = runbook_prose()

    assert "**The `network.device_inventory` observation lives in the body**" in prose
    assert "It is the provenance anchor for every later workspace address" in prose
    assert "names the inventory observation it was read out of, by `operation_rid`" in prose


def test_the_body_records_all_five_things_per_statement():
    """A row missing one of them cannot be read back.

    Without the statement nobody knows what was asked; without the relay input
    and its source a dependent answer has no provenance; without the exact
    returned value there is no result shape; without the diagnostic a failure
    has no attribution; without the module start two evaluations merge (MJ-023).
    """
    prose = runbook_prose()

    missing = [field for field in BODY_FIELDS if f"| {field} |" not in prose]
    assert not missing, missing
    assert "or the word `none`" in prose


def test_the_transcript_is_preserved_rather_than_tidied():
    """A rewritten envelope is a paraphrase of the target."""
    prose = runbook_prose()

    assert (
        "**The transcript is preserved without normalizing or rewriting its "
        "envelopes.**" in prose
    )
    assert "no field reordering" in prose


def test_the_summary_interprets_the_transcript_and_never_replaces_it():
    """Python decides what a run established, from evidence it did not write (MJ-011)."""
    prose = runbook_prose()

    assert "interprets the transcript **afterwards** and cites it" in prose
    assert "where the two disagree, the transcript is what happened" in prose
    assert "no envelope is reconstructed" in prose


def test_the_header_reader_finds_a_block_and_notices_a_wrong_one():
    """Guards the exact-list gate from passing because it parsed nothing."""
    sample = "```text\nrun_id      created first\nobserved inventory  later\n```"

    assert header_field("run_id                    created before") == "run_id"
    assert header_field("PacketTracer.exe SHA-256  the pinned hash") == "PacketTracer.exe SHA-256"
    assert TEXT_BLOCK.search(sample).group(1).splitlines()[1].startswith("observed")
    assert len(header_lines()) == len(PRE_RUN_HEADER_FIELDS)
