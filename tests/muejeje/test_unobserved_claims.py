"""Nothing may claim what nobody observed.

Every defect this module gates for was a real one found by review: a document
that still said the dispatcher did not exist after it did, a static page that
reported the lifecycle as running without looking at it, and a protocol escape
hatch that was withdrawn but still written down. Each of those reads as
evidence, and none of them was.

The rule is one rule. A claim about what the runtime *is doing* has to be
traceable to something that watched it, and a claim about what the runtime
*admits* has to agree with the whitelist itself (MJ-021).
"""

from __future__ import annotations

import re

import pytest

from tests.muejeje.support import (
    REPO_ROOT,
    SCRIPT_ENGINE,
    SOURCE_ROOT,
    packaged_sources,
    relative,
)

# Documents that describe the runtime to a reader. A claim here carries the
# same weight as one in the source, and drifts more easily.
DESCRIBING_DOCUMENTS = (
    "docs/architecture/muejeje-pts-requirements.md",
    "docs/architecture/muejeje-runtime-operating-model.md",
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
)

# An operation name as a document writes it: inside backticks, or inside a
# <code> element on the Custom Interface page.
DOCUMENTED_OPERATION = re.compile(r"[`>](runtime\.[a-z_]+)[`<]")
# An entry in the dispatcher's whitelist table.
ADMITTED_OPERATION = re.compile(r'"(runtime\.[a-z_]+)":\s*\{')

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


def admitted_operations() -> set[str]:
    """The whitelist, read from the dispatcher that owns it."""
    body = (SCRIPT_ENGINE / "dispatcher_v6.js").read_text(encoding="utf-8")
    return set(ADMITTED_OPERATION.findall(body))


# ---------------------------------------------------------------------------
# Documents describe the runtime that exists.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("logical", DESCRIBING_DOCUMENTS)
def test_no_document_repeats_a_withdrawn_claim(logical: str):
    body = _document(logical)
    offenders = [
        f"{logical}: {found.group(0)!r} — {because}"
        for pattern, because in RETIRED_CLAIMS
        for found in [re.search(pattern, body)]
        if found is not None
    ]
    assert not offenders, offenders


@pytest.mark.parametrize("logical", DESCRIBING_DOCUMENTS)
def test_a_document_names_every_admitted_operation_and_no_other(logical: str):
    """A whitelist written twice is a whitelist that will disagree with itself.

    Naming an operation the dispatcher does not admit is a roadmap promise
    read as a present capability; omitting one leaves a consumer unable to
    discover what it may actually send.
    """
    documented = set(DOCUMENTED_OPERATION.findall(_document(logical)))
    assert documented == admitted_operations(), (
        f"{logical} documents {sorted(documented)}; the dispatcher admits "
        f"{sorted(admitted_operations())}"
    )


def test_the_whitelist_is_read_from_the_dispatcher_and_is_not_empty():
    """Guards the gate above from passing because it parsed nothing."""
    assert admitted_operations(), "the whitelist reader found no operation"


# ---------------------------------------------------------------------------
# The Custom Interface observes nothing, so it asserts nothing.
# ---------------------------------------------------------------------------

def _interface_files() -> dict[str, str]:
    return {
        relative(path): path.read_text(encoding="utf-8")
        for path in sorted((SOURCE_ROOT / "interface").rglob("*"))
        if path.is_file()
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
        f"{relative(path)}: {found.group(0)}"
        for path in packaged_sources()
        for found in SELF_CERTIFICATION.finditer(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "Python owns verification, from outside the artifact; the runtime "
        f"reports observations and reaches no verdict about them: {offenders}"
    )
