"""Nothing may claim what nobody observed.

Every defect this module gates for was a real one found by review: a document
that still said the dispatcher did not exist after it did, a static page that
reported the lifecycle as running without looking at it, a protocol escape
hatch that was withdrawn but still written down, and a comment claiming a
Packet Tracer restart semantic that Cisco's own reference contradicts. Each of
those reads as evidence, and none of them was.

A claim about what the runtime *is doing* has to be traceable to something
that watched it. A withdrawn claim has to be gone from the sources as well as
from the documents, because a comment drifts more quietly than a document
does: nothing about a comment looks like a claim (MJ-021).

What the runtime *admits* is the other half of the rule, and it lives in
`test_capability_claims` — split out when this module crossed its own line
budget (MJ-020). Cisco's own installed sentences, which are what settles a
withdrawn claim *about Packet Tracer*, moved to `test_cisco_reference` the same
way: deleting our text and re-reading Cisco's are different work.
"""

from __future__ import annotations

import re

import pytest

from tests.muejeje.measure import (
    packaged_binary_sources,
    packaged_sources,
    packaged_text_bodies,
    relative,
)
from tests.muejeje.support import (
    REPO_ROOT,
    SCRIPT_ENGINE,
    SOURCE_ROOT,
)

# Documents that describe the runtime to a reader. A claim here carries the
# same weight as one in the source, and drifts more easily.
DESCRIBING_DOCUMENTS = (
    "docs/architecture/muejeje-pts-requirements.md",
    "docs/architecture/muejeje-runtime-operating-model.md",
    "docs/qa/muejeje-pts-packaging-recipe.md",
    "docs/qa/muejeje-pts-privilege-live-runbook.md",
    "docs/qa/muejeje-pts-privilege-map.md",
    "docs/qa/muejeje-pts-offline.md",
    "muejeje_pts/README.md",
    "muejeje_pts/interface/index.html",
)

# Claims that were true once and are not any more. Each is written as the
# pattern that would find it again, not as prose about it.
RETIRED_CLAIMS = (
    (r"mcpDispatchV6[^\n]{0,80}not implemented",
     "the dispatcher exists and is the single V6 entry point"),
    (r"\bNOT_V6\b",
     "V6 has no compatibility escape; a non-V6 request is refused"),
    (r"empty of behaviour",
     "the owned source root carries the V6 kernel"),
    (r"restarting the module is not re-?evaluating",
     "Cisco documents the opposite: a module start evaluates every engine file"),
    (r"including across a [`']?cleanUp\(\)",
     "the session token spans one evaluation, and a restart is a new one"),
    (r"runtime_session_id`? (?:will|must|should) differ",
     "a new evaluation generates a new token; the kernel guarantees no "
     "uniqueness and could not detect a collision (MJ-023)"),
    (r"different tokens (?:say|mean|show|prove)\b",
     "token inequality establishes nothing, so no step reads one evaluation "
     "or a restart out of it (MJ-023)"),
    (r"never\s+(?:been\s+)?run\s+inside\s+Packet\s+Tracer",
     "an exploratory module ran the kernel's source inside 9.0.1.0858; what "
     "has not run is a governed artifact (MJ-015)"),
    (r"\bno\s+`?\.pts`?\s+has\s+(?:yet\s+)?been\s+built",
     "a module was packaged from these sources, exploratorily; what does not "
     "exist is a governed artifact (MJ-015)"),

    # The privilege line. Each was true while `privileges: []` was declared and
    # false once a call descriptor was recorded for both root calls. Present
    # tense on purpose: a statement scoped to the `[]` artifact or run stays.
    (r"module\s+(?:still\s+)?requests\s+no\s+privilege",
     "the governed manifest declares exactly GET_NETWORK_INFO (MJ-025)"),
    (r"module\s+requests\s+none\b",
     "the module requests one token, and which one is recorded (MJ-032)"),
    (r"nothing\s+evidences\s+which\s+privilege"
     r"|no\s+evidence\s+(?:says|names)\s+which\s+privilege"
     r"|nothing\s+it\s+calls\s+has\s+an\s+evidenced\s+privilege",
     "both root calls have a recorded requirement: index 1 (MJ-032)"),
    (r"[Ww]hich\s+privilege[\s\S]{0,120}?\bis\s+still\s+unmeasured",
     "the requirement is recorded; whether it works is unmeasured (MJ-032)"),
    (r"[Tt]he\s+empty\s+set\s+is\s+justified"
     r"|[Nn]o\s+privilege\s+is\s+evidenced",
     "the justified set is what the recorded descriptors compose to (MJ-032)"),

    # One word for three evidence strengths is how supplied, unreproducible
    # evidence reads as a measurement made here.
    (r"GET_NETWORK_INFO_BINARY_EVIDENCE(?!_RECORDED)",
     "three states, each able to hold alone: _RECORDED, "
     "BINARY_MAP_REPRODUCIBILITY, GET_NETWORK_INFO_LIVE_VERIFIED (MJ-032)"),
    (r"reported\s+back\s+verbatim",
     "neither run preserved its envelopes; both records keep the "
     "operator-reported observations (MJ-011, MJ-015)"),

    # Two claims that described the artifact as reading less than it does, and
    # one that predicted a position the runtime refuses to promise.
    (r"[Nn]othing\s+(?:anywhere\s+)?reads\s+(?:or\s+writes\s+)?a\s+device"
     r"\s+instance",
     "a workspace device instance is read: name, model, DeviceType, port "
     "count and port names. What is unread is mutable operational and "
     "configuration state (MJ-031)"),
    (r"every\s+piece\s+of\s+device\s+state\s+deliberately\s+unread",
     "identity and structural metadata are read off the instance; only "
     "mutable operational and configuration state is unread (MJ-031)"),
    (r"workspace_index\s+\d\s*:",
     "a workspace index is the position one reading handed a device over at, "
     "never identity or placement order, so no document predicts one "
     "(MJ-002, MJ-029)"),
    (r"live-transcript-<build_recipe_id>",
     "the raw transcript is named by the artifact SHA-256 it is evidence "
     "about; a recipe id names intended bytes, not the ones that ran"),

    # The LIVE procedure's own withdrawn rules: coverage by entering every
    # statement, one transcript per artifact rather than per execution, a header
    # that needed an answer, and an attribution finding that erased answers.
    (r"(?:reported|reports),\s+once\s+each"
     r"|is\s+still\s+entered\s+once"
     r"|statement\s+is\s+entered\s+exactly\s+once",
     "every operation is accounted for, EXECUTED or "
     "NOT_EXERCISED_PREREQUISITE_UNAVAILABLE; no placeholder is entered to "
     "satisfy coverage"),
    (r"placeholder\s+entered\s+unchanged",
     "a placeholder is never entered"),
    (r"live-transcript-<artifact_sha256>\.md",
     "a transcript names an execution: the artifact SHA-256 and a run id"),
    (r"observed\s+device\s+inventory\s+the\s+network\.device_inventory",
     "the inventory is a body observation, never a pre-run header field"),
    (r"qualify\s+no\s+descendant\s+member",
     "an unstable attribution invalidates cross-reading continuity, not the "
     "answers each call gave"),
)

# Sources that describe the runtime in prose, the way a document does. A
# withdrawn claim in a comment reads as evidence exactly as one in a document
# does, and drifts more quietly, because nothing about a comment looks like a
# claim. Engine sources are always JavaScript, so reading them as text is safe.
DESCRIBING_SOURCES = tuple(
    relative(path) for path in sorted(SCRIPT_ENGINE.glob("*.js"))
)

# Present-tense liveness. A static page cannot know any of these.
LIVENESS_CLAIM = re.compile(
    r"\b(?:is|are|has)\s+(?:currently\s+)?"
    r"(?:running|started|connected|live|active|polling)\b",
    re.IGNORECASE,
)

# A verdict the runtime is not entitled to reach about itself. Verification is
# Python's, from outside; a runtime that certifies its own evidence has only
# restated its own opinion (MJ-011).
SELF_CERTIFICATION = re.compile(r"\b(?:VERIFIED|QUALIFIED|ATTESTED)\b")


def _document(logical: str) -> str:
    return (REPO_ROOT / logical).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Documents describe the runtime that exists.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("logical", DESCRIBING_DOCUMENTS + DESCRIBING_SOURCES)
def test_nothing_that_describes_the_runtime_repeats_a_withdrawn_claim(logical: str):
    """Documents and source comments are held to the same claim."""
    body = _document(logical)
    offenders = [
        f"{logical}: {found.group(0)!r} — {because}"
        for pattern, because in RETIRED_CLAIMS
        for found in [re.search(pattern, body)]
        if found is not None
    ]
    assert not offenders, offenders


def test_the_withdrawn_claim_gate_reads_the_kernel_sources_too():
    """Guards the gate above from passing because it swept no source.

    The claim it was added for lived in a `010_core.js` comment, not in a
    document, so a gate that reads only documents would have reported the
    tree clean while the artifact itself still carried the claim.
    """
    assert "muejeje_pts/script-engine/010_core.js" in DESCRIBING_SOURCES
    assert len(DESCRIBING_SOURCES) == len(list(SCRIPT_ENGINE.glob("*.js")))

# ---------------------------------------------------------------------------
# The Custom Interface observes nothing, so it asserts nothing.
# ---------------------------------------------------------------------------

def _interface_files() -> dict[str, str]:
    """The interface files that carry prose. An image carries none.

    Reading only the text assets is what lets the Custom Interface ship a logo
    without this gate crashing on its bytes (MJ-021).
    """
    interface = f"{relative(SOURCE_ROOT / 'interface')}/"
    return {
        logical: body
        for logical, body in packaged_text_bodies().items()
        if logical.startswith(interface)
    }


def test_the_custom_interface_claims_no_lifecycle_it_did_not_observe():
    """It is a static page. It cannot see whether `main()` ran.

    The page previously opened with "its lifecycle is running", which is a
    reading of a state nothing on the page had read. `runtime.identify`
    reports that state because it looks at what `main()` recorded; a page
    that renders identically before and after startup may not.
    """
    offenders = [
        f"{logical}: {found.group(0)!r}"
        for logical, body in sorted(_interface_files().items())
        for found in LIVENESS_CLAIM.finditer(body)
    ]
    assert not offenders, (
        f"a static interface reports no liveness; it describes: {offenders}"
    )


def test_the_custom_interface_calls_nothing_and_stays_static():
    """No script, no fetch, no timer: nothing that could observe or initiate."""
    for logical, body in sorted(_interface_files().items()):
        for forbidden in ("<script", "setInterval", "setTimeout", "fetch("):
            assert forbidden not in body, f"{logical}: {forbidden}"


# ---------------------------------------------------------------------------
# The runtime does not certify itself.
# ---------------------------------------------------------------------------

def test_no_packaged_source_certifies_its_own_verification():
    offenders = [
        f"{logical}: {found.group(0)}"
        for logical, body in sorted(packaged_text_bodies().items())
        for found in SELF_CERTIFICATION.finditer(body)
    ]
    assert not offenders, (
        "Python owns verification, from outside the artifact; the runtime "
        f"reports observations and reaches no verdict about them: {offenders}"
    )


def test_the_self_certification_sweep_covers_every_text_asset():
    """Guards the gate above from passing because it read the wrong list.

    It used to decode the whole packaged inventory, images included, so the
    first packaged `.png` would have replaced its verdict with a
    `UnicodeDecodeError`. It now reads the text assets, and this asserts that
    the two lists differ only by the assets that are not text.
    """
    text = set(packaged_text_bodies())
    every = {relative(path) for path in packaged_sources()}
    binary = {relative(path) for path in packaged_binary_sources()}

    assert text, "the sweep found no text asset to read"
    assert text | binary == every
    assert text.isdisjoint(binary)
