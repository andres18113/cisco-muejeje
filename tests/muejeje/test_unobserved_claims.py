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
budget (MJ-020).
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
    INSTALLED_HELP,
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
)

# Sources that describe the runtime in prose, the way a document does. A
# withdrawn claim in a comment reads as evidence exactly as one in a document
# does, and drifts more quietly, because nothing about a comment looks like a
# claim. Engine sources are always JavaScript, so reading them as text is safe.
DESCRIBING_SOURCES = tuple(
    relative(path) for path in sorted(SCRIPT_ENGINE.glob("*.js"))
)

# What Cisco's installed reference says about the Script Engine lifecycle.
# Quoted, not paraphrased: the claim these sentences correct was a claim about
# Packet Tracer, so only Packet Tracer's own documentation can settle it
# (MJ-015, `AGENTS.md` rule 6). The page is hash-pinned in the v2 preflight
# inventory as `d22cafa8...`.
CISCO_SCRIPT_ENGINE_PAGE = "scriptModules_scriptEngine.htm"
CISCO_LIFECYCLE_SENTENCES = (
    "When the Script Module starts, all script files are executed (evaluated)"
    " in the Script Engine in the same order as listed in the Scripting"
    " Interface.",
    "As long as the Script Module is running, the Script Engine is running.",
    "Changes made to the Script Engine after it has started DO NOT take effect"
    " until it has been stopped and started again.",
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


@pytest.mark.skipif(
    not INSTALLED_HELP.is_dir(),
    reason="the target build is not installed; its documentation cannot be read",
)
@pytest.mark.parametrize("sentence", CISCO_LIFECYCLE_SENTENCES)
def test_cisco_documents_that_a_module_start_evaluates_the_engine(sentence: str):
    """The evidence behind the correction, read from the installed reference.

    An earlier revision claimed the session token survived a module restart,
    "because restarting the module is not re-evaluating it". Cisco's page says
    the opposite in three places: every engine file is evaluated when the
    module *starts*, the engine lives exactly as long as the module runs, and
    an engine change needs a stop and a start to take effect. So a restart is
    a new evaluation and a new token, and the withdrawn claim was a statement
    about Packet Tracer that Packet Tracer's own documentation contradicts.

    Quoting it here is what keeps the correction checkable: if a future
    installed build words this differently, this gate fails and the
    requirement is re-read against the new wording rather than assumed.
    """
    page = (INSTALLED_HELP / CISCO_SCRIPT_ENGINE_PAGE).read_text(
        encoding="utf-8", errors="replace",
    )
    collapsed = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))

    assert sentence in collapsed, CISCO_SCRIPT_ENGINE_PAGE


def test_the_withdrawn_claim_gate_reads_the_kernel_sources_too():
    """Guards the gate above from passing because it swept no source.

    The claim it was added for lived in a `core.js` comment, not in a
    document, so a gate that reads only documents would have reported the
    tree clean while the artifact itself still carried the claim.
    """
    assert "muejeje_pts/script-engine/core.js" in DESCRIBING_SOURCES
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
