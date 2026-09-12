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

How the run must *obtain and preserve* its evidence is split the same way, one
module per concern: `test_live_evidence` for where its relay inputs come from
and what an unstable attribution invalidates, `test_live_transcript` for what
survives the run, and `test_live_accounting` for the status every operation
receives. Declaring a run and capturing it are different work (MJ-018, MJ-020).
"""

from __future__ import annotations

from tests.muejeje.support import REPO_ROOT, repo_manifest

RUNBOOK = "docs/qa/muejeje-pts-privilege-live-runbook.md"

# The state a person must find before starting the run. Written here as the
# claim, and read back from the document, so the two cannot drift — a runbook
# that promoted a milestone the repository has not is how a denied call becomes
# a qualification (MJ-033).
EXPECTED_ENTRY_STATE = """M1_CORE_READY = YES

GET_NETWORK_INFO_BINARY_EVIDENCE_RECORDED = PASS
BINARY_MAP_REPRODUCIBILITY                = PENDING

CURRENT_CANDIDATE_PACKAGED                = PENDING
CURRENT_CANDIDATE_V6_LIVE_VERIFIED        = PENDING
GET_NETWORK_INFO_LIVE_VERIFIED            = PENDING

M0B_TARGET_API_BASELINED = NOT_COMPLETE
M2_CORE_READY            = NO
M3_CORE_READY            = NO
ZERO_CHANGE_CUTOVER      = NOT_ACHIEVED"""

# The two artifacts the run has to keep apart: the one whose verdicts exist,
# and the one being built. Written as the block the runbook must carry.
ARTIFACT_SPLIT = """LAST_QUALIFIED_ARTIFACT (d37ba37)
  OFFICIAL_PACKAGING_PROVED = PASS
  V6_KERNEL_VERIFIED        = PASS

CURRENT_CANDIDATE
  PACKAGED              = PENDING
  V6_LIVE_VERIFIED      = PENDING
  GET_NETWORK_INFO_LIVE = PENDING"""

# The disposable fixture the run is taken over. Two devices, because one that
# answers is what makes the members below the root actually run; no cable and
# no configuration, because nothing below a link or an address is admitted; not
# saved, because the run touches nobody's work (MJ-002).
#
# What it deliberately does **not** say is where either device sits. A
# `workspace_index` is the position the platform handed a device over at in one
# reading; it is not identity and not placement order, so a fixture that
# assigned one would be declaring a workspace ordering the runtime refuses to
# promise.
WORKSPACE_FIXTURE = """2960-24TT named Switch0
PC-PT named PC0
no cable
no configuration
not saved"""

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
# A verdict about one artifact is not a verdict about another.
# ---------------------------------------------------------------------------

def test_the_runbook_keeps_the_qualified_artifact_apart_from_this_candidate():
    """`d37ba37` was packaged and driven. This candidate has been neither.

    The two share a source line and nothing else that matters here: a different
    privilege set is a different recipe id identifying different bytes. Letting
    the first artifact's `PASS` stand in for the second would make a run that
    never happened look like one that did, which is the one thing a
    qualification record must never do (MJ-015, MJ-033).
    """
    body = runbook_body()

    assert ARTIFACT_SPLIT in body
    assert "M1_CORE_READY = YES" in body

    prose = runbook_prose()
    assert "is the milestone state the **previous** governed artifact" in prose
    assert (
        "This run moves no candidate-specific state until the candidate itself "
        "produces the evidence for it" in prose
    )


def test_the_entry_state_carries_no_candidate_verdict():
    """Guards the gate above from passing on a block that still promotes.

    If `OFFICIAL_PACKAGING_PROVED = PASS` ever reappears unqualified in the
    entry state, a reader starts the run believing this artifact is already
    packaged.
    """
    entry = EXPECTED_ENTRY_STATE

    assert "OFFICIAL_PACKAGING_PROVED" not in entry
    assert "V6_KERNEL_VERIFIED        = PASS" not in entry
    assert "CURRENT_CANDIDATE_PACKAGED                = PENDING" in entry
