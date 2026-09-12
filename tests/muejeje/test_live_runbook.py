"""The runbook that declares the next manual LIVE run, held to what it must be.

Split out of `test_privileges` when that module crossed its line budget, and
the two responsibilities really are different: there, which privilege names the
audit accepts; here, whether the one manual procedure this repository cannot
drive is capable of establishing anything at all (MJ-018, MJ-020).

A runbook is the only artefact in this repository that a person executes by
hand inside a GUI, so a gap in it is not a documentation nit — it is a run that
comes back with observations nobody can read a verdict out of. The previous
official run is the case in point twice over: it kept a summary rather than its
envelopes, so it established no result shape, and it said nothing about what
had to be in the workspace, so an answering `network.*` root could have
qualified nothing beneath it.

Both of those are now preconditions of the next run, and these gates hold the
document to them.
"""

from __future__ import annotations

from tests.muejeje.support import REPO_ROOT, repo_manifest

RUNBOOK = "docs/qa/muejeje-pts-privilege-live-runbook.md"

# The state a person must find before starting the run. Written here as the
# claim, and read back from the document, so the two cannot drift — a runbook
# that promoted a milestone the repository has not is how a denied call becomes
# a qualification (MJ-033).
EXPECTED_ENTRY_STATE = """OFFICIAL_PACKAGING_PROVED = PASS
V6_KERNEL_VERIFIED        = PASS
M1_CORE_READY             = YES

GET_NETWORK_INFO_BINARY_EVIDENCE_RECORDED = PASS
BINARY_MAP_REPRODUCIBILITY                = PENDING
GET_NETWORK_INFO_LIVE_VERIFIED            = PENDING

M0B_TARGET_API_BASELINED = NOT_COMPLETE
M2_CORE_READY            = NO
M3_CORE_READY            = NO
ZERO_CHANGE_CUTOVER      = NOT_ACHIEVED"""

# The disposable fixture the run is taken over. Two devices, because one that
# answers is what makes the members below the root actually run; no cable and
# no configuration, because nothing below a link or an address is admitted; not
# saved, because the run touches nobody's work (MJ-002).
WORKSPACE_FIXTURE = """workspace_index 0: 2960-24TT, name Switch0
workspace_index 1: PC-PT, name PC0
no cable
no configuration
topology not saved"""

# The members a `network.*` root that answers has to reach over that fixture.
# An empty workspace reaches none of them: `available_count: 0` is a valid
# reading that calls nothing further.
EXERCISED_MEMBERS = (
    "Network.getDeviceCount",
    "Network.getDeviceAt",
    "Device.getName",
    "Device.getModel",
    "Device.getType",
    "Device.getPortCount",
    "Device.getPortAt",
    "Port.getName",
)

# What the single raw evidence file records for every statement entered.
TRANSCRIPT_FIELDS = (
    "statement / RID",
    "returned value",
    "Packet Tracer output",
    "module start",
)


def runbook_body() -> str:
    return (REPO_ROOT / RUNBOOK).read_text(encoding="utf-8")


def runbook_prose() -> str:
    """The runbook with its line wrapping collapsed.

    A sentence gate that matched the wrapping would fail on a reflow that
    changed nothing, and teach the next reader to stop reflowing.
    """
    return " ".join(runbook_body().split())


def runbook_flush_left() -> str:
    """The runbook with each line's leading indentation removed.

    A block inside a numbered step is indented to sit in that step, and a gate
    that required column zero would force the fixture out of the precondition
    it belongs to. Line *breaks* still matter here — a block is a block — so
    this is not the collapsed prose.
    """
    return "\n".join(line.lstrip() for line in runbook_body().splitlines())


# ---------------------------------------------------------------------------
# The one field the run exists to change.
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# The run must be able to establish something: a workspace with devices in it.
# ---------------------------------------------------------------------------

def test_the_runbook_requires_the_two_device_disposable_workspace():
    """A non-empty workspace is a precondition, not a suggestion.

    The recipe allows "a minimal disposable workspace"; this run needs a
    specific one, because what it is trying to measure lives below the root
    call and an empty workspace never reaches it.
    """
    body = runbook_flush_left()

    assert WORKSPACE_FIXTURE in body, (
        "the exact fixture must be written down — a run over a workspace "
        "nobody specified is a run nobody can repeat"
    )
    assert "A disposable workspace holding two devices is open" in runbook_prose()


def test_the_operator_builds_the_fixture_and_muejeje_changes_nothing():
    """Read-only is the whole surface, so the fixture is placed by hand.

    A runbook that had the artifact create its own devices would make the run
    evidence about a mutation this repository does not implement and must not
    acquire (MJ-002).
    """
    prose = runbook_prose()

    assert "The operator creates it. Muejeje creates, modifies and saves nothing"in prose
    assert "never anyone's real work" in prose


def test_the_runbook_refuses_to_qualify_descendants_on_an_empty_workspace():
    """A root that answered is not a member that answered.

    This is the vacuity the fixture exists to prevent: `IPC.network()` can
    succeed while every member beneath it stays exactly as unobserved as it was
    before, and a record that merged the two would report an API as reached
    when nothing called it.
    """
    prose = runbook_prose()

    assert "**A member is qualified by its own answer, never by its root's.**" in prose
    assert (
        "no `network.*` member below it is recorded as observed" in prose
    ), "the empty-workspace outcome must be stated as its own result"
    assert (
        "a root answers over an empty workspace | the root result, and "
        "**nothing** about any member below it" in prose
    ), "the reading table must carry the vacuous case as a row of its own"


def test_the_recipe_sends_a_reader_to_the_fixture_rather_than_softening_it():
    """Two documents, one rule about what a workspace reading is taken over.

    The recipe is the procedure every run follows and the runbook declares one
    run, so the fixture lives in the runbook — but a recipe that still said a
    workspace reading "may" be taken on any minimal workspace would leave a
    reader with two answers and no way to tell which was current.
    """
    recipe = " ".join(
        (REPO_ROOT / "docs/qa/muejeje-pts-packaging-recipe.md")
        .read_text(encoding="utf-8").split()
    )

    assert "muejeje-pts-privilege-live-runbook.md" in recipe
    assert (
        "that workspace decides what the run can establish" in recipe
    ), "the recipe must say that an empty workspace bounds what a run can show"


def test_the_runbook_names_the_members_the_fixture_makes_reachable():
    """Named one by one, so a thinner fixture is visibly a thinner run.

    Two devices, one of them a switch with ports, is what causes each of these
    to be called at all. Writing the list down is what makes it checkable that
    the fixture still covers it.
    """
    body = runbook_body()

    missing = [member for member in EXERCISED_MEMBERS if member not in body]
    assert not missing, missing


# ---------------------------------------------------------------------------
# The run must leave evidence somebody else can read: one raw transcript.
# ---------------------------------------------------------------------------

def test_the_runbook_requires_one_raw_transcript_file():
    """The correction the previous official run forces.

    That run preserved the operator's observations and not its envelopes, so it
    established packaging, execution, lifecycle and the denial diagnostics —
    and no result shape at all, because there was nothing field-level to check.
    One file, written as the run happens, is what makes the next one different.
    """
    prose = runbook_prose()

    assert "docs/qa/muejeje-pts-live-transcript-<build_recipe_id>.md" in prose
    assert "**This run produces a single raw evidence file**" in prose


def test_the_transcript_records_all_four_things_per_statement():
    """A row that is missing one of them cannot be read back.

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
