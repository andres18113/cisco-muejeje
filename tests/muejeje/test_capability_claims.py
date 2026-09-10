"""What the runtime admits, and what a document may call a capability.

The rule is one rule: a claim about what the runtime *admits* has to agree
with the artifact itself. Two lists decide that — the dispatcher's whitelist
and the kernel's feature list — and both are read out of the sources here
rather than written down again (MJ-008, MJ-028, MJ-021).

**One catalogue is complete; every other claim is checked, not repeated.**
Requiring every descriptive document to enumerate every operation made the
whitelist five copies that a single new operation could put out of step, and it
pushed each document toward a list it had no reason to carry. So exactly one
document is the authoritative catalogue and is held complete; everywhere else,
a document names whichever operations it has a reason to name, may claim no
capability that does not exist, and may not miscount the ones that do — a
count is a completeness claim in fewer words, and "three read-only operations"
goes stale exactly as a list does.

**An operation and a feature share a shape.** `runtime.capabilities` is one,
`runtime.session_id` is the other, and a reader that knew only about
operations would either miss a false feature claim or reject a true one. So a
documented capability is checked against the union of both sets, and the two
sets must stay disjoint.

**Namespaces are declared, not hard-coded.** An earlier revision matched the
literal prefix `runtime.` in every regex, so the first operation in a second
namespace would have been invisible to each of these gates: undocumented and
unnoticed at the same time.

Split out of `test_unobserved_claims` when that module crossed its own line
budget: what the runtime *is doing* and what it *admits* are two claims and
two responsibilities (MJ-020).
"""

from __future__ import annotations

import re

import pytest

from tests.muejeje.support import FEATURE_EVIDENCE, REPO_ROOT, SCRIPT_ENGINE

# Documents that describe the runtime to a reader. A claim here carries the
# same weight as one in the source, and drifts more easily.
DESCRIBING_DOCUMENTS = (
    "docs/architecture/muejeje-pts-requirements.md",
    "docs/architecture/muejeje-runtime-operating-model.md",
    "docs/qa/muejeje-pts-packaging-recipe.md",
    "muejeje_pts/README.md",
    "muejeje_pts/interface/index.html",
)
# The one document that enumerates the whitelist for a reader: the artifact's
# own README, which is where somebody holding `muejeje.pts` looks for what they
# may send. It is held complete. Every other document names whichever
# operations it has a reason to name, and is held to the claim rules below
# rather than to the list.
AUTHORITATIVE_CATALOGUE = "muejeje_pts/README.md"

# The namespaces V6 operations live in. The dispatcher may admit a name only
# in one of these, so adding a namespace is an edit here — which is what makes
# a new one visible.
OPERATION_NAMESPACES = ("network", "platform", "runtime")
# Namespaces a document may name a *capability* in — an operation or a kernel
# feature. `protocol.v6` is a feature, not an operation, and the two share a
# shape, so they are told apart by the sets they belong to rather than by how
# they are spelled.
CAPABILITY_NAMESPACES = ("network", "platform", "protocol", "runtime")

_SEGMENT = r"[a-z][a-z0-9_]*"


def _dotted(namespaces: tuple[str, ...]) -> str:
    return rf"(?:{'|'.join(namespaces)})\.{_SEGMENT}"


# A capability name as a document writes it: inside backticks, or inside a
# <code> element on the Custom Interface page. Anchored on both sides and
# restricted to declared namespaces, so a file path such as `core.js` is not
# read as a capability claim.
DOCUMENTED_OPERATION = re.compile(rf"[`>]({_dotted(OPERATION_NAMESPACES)})[`<]")
DOCUMENTED_CAPABILITY = re.compile(rf"[`>]({_dotted(CAPABILITY_NAMESPACES)})[`<]")
# A written count of operations — "three operations", "two runtime
# operations", "four read-only operations". Spelled numbers because that is how
# a document writes one, and the words between the number and the noun are
# captured because one of them may name the namespace being counted.
WORD_COUNTS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
OPERATION_COUNT = re.compile(
    rf"\b({'|'.join(WORD_COUNTS)}|\d+)((?:\s+[a-z-]+)*)\s+operations\b",
    re.IGNORECASE,
)
# An entry in the dispatcher's whitelist table, in *any* namespace: an
# operation this reader cannot see is one nothing holds to the contract.
ADMITTED_OPERATION = re.compile(rf'"({_SEGMENT}\.{_SEGMENT})":\s*\{{')
# The kernel's own feature list, read from the core that declares it.
DECLARED_FEATURE = re.compile(rf'"({_dotted(CAPABILITY_NAMESPACES)})"')



def _document(logical: str) -> str:
    return (REPO_ROOT / logical).read_text(encoding="utf-8")


def admitted_operations() -> set[str]:
    """The whitelist, read from the dispatcher that owns it."""
    body = (SCRIPT_ENGINE / "dispatcher_v6.js").read_text(encoding="utf-8")
    return set(ADMITTED_OPERATION.findall(body))


def declared_features() -> set[str]:
    """The kernel feature list, read from the core that declares it."""
    body = (SCRIPT_ENGINE / "core.js").read_text(encoding="utf-8")
    listed = body.split("SUPPORTED_FEATURES: [")[1].split("]")[0]
    return set(DECLARED_FEATURE.findall(listed))


def declared_capabilities() -> set[str]:
    """Everything a document may legitimately call a capability."""
    return admitted_operations() | declared_features()


def counted_operations(body: str) -> list[tuple[int, str]]:
    """`(how many, which namespace)` for every operation count `body` writes.

    The namespace is `""` when the count is unqualified, which makes it a claim
    about the whole whitelist rather than about one namespace.
    """
    counts = []
    for found in OPERATION_COUNT.finditer(body):
        written = found.group(1).lower()
        modifiers = found.group(2).lower().split()
        scope = next(
            (word for word in modifiers if word in OPERATION_NAMESPACES), "",
        )
        counts.append((WORD_COUNTS.get(written, 0) or int(written), scope))
    return counts


def test_the_authoritative_catalogue_names_every_admitted_operation():
    """One place a consumer can read the whole whitelist from.

    Omitting an admitted operation there leaves a consumer unable to discover
    what it may actually send. Naming one the dispatcher does not admit is
    caught by the capability gate below, which covers every document and also
    covers a claimed kernel feature that does not exist.
    """
    documented = set(DOCUMENTED_OPERATION.findall(_document(AUTHORITATIVE_CATALOGUE)))
    assert admitted_operations() <= documented, (
        f"{AUTHORITATIVE_CATALOGUE} omits "
        f"{sorted(admitted_operations() - documented)}"
    )


def test_the_catalogue_is_one_of_the_documents_held_to_the_claim_rules():
    """A catalogue outside the swept set would be checked for completeness and
    for nothing else, which is the one combination that lets it be complete and
    wrong at the same time."""
    assert AUTHORITATIVE_CATALOGUE in DESCRIBING_DOCUMENTS


@pytest.mark.parametrize("logical", DESCRIBING_DOCUMENTS)
def test_every_written_operation_count_is_the_number_that_exists(logical: str):
    """A count is a completeness claim in fewer words, so it is checked.

    This is what replaced "every document lists every admitted operation".
    Repeating the list everywhere made one new operation a five-document edit
    and pushed each document toward a list it had no reason to carry; a stale
    count is the same failure, and it is the one worth catching, because
    "three read-only operations" reads as evidence that there are three.

    A count qualified by a namespace is a claim about that namespace and is
    checked against it, so a document may go on saying "the two runtime
    operations" while the platform namespace grows.
    """
    admitted = admitted_operations()
    for claimed, scope in counted_operations(_document(logical)):
        counted = (
            {op for op in admitted if op.startswith(f"{scope}.")} if scope
            else admitted
        )
        assert claimed == len(counted), (
            f"{logical} says {claimed} {scope or 'admitted'} operations; the "
            f"dispatcher admits {len(counted)}"
        )


@pytest.mark.parametrize("logical", DESCRIBING_DOCUMENTS)
def test_a_document_claims_no_capability_that_does_not_exist(logical: str):
    """Every capability a document names is an operation or a kernel feature.

    This is the contradiction gate. An operation and a feature share a shape —
    `runtime.capabilities` is one, `runtime.session_id` is the other — so a
    reader that knew only about operations would either miss a false feature
    claim or reject a true one. Both sets are read from the artifact, so a
    document that promises `platform.something` the kernel does not have fails
    here rather than at the moment a consumer tries to use it (MJ-028).
    """
    claimed = set(DOCUMENTED_CAPABILITY.findall(_document(logical)))
    invented = claimed - declared_capabilities()

    assert invented == set(), (
        f"{logical} names capabilities this artifact does not have: "
        f"{sorted(invented)}"
    )


def test_an_operation_and_a_feature_are_never_the_same_name():
    """Two kinds of thing, one namespace. A shared name means neither.

    A name that is both would make "is this admitted" and "does this exist"
    the same question, and a consumer reading one answer as the other is
    exactly the confusion the two lists exist to prevent.
    """
    assert admitted_operations().isdisjoint(declared_features())


def test_every_admitted_operation_lives_in_a_declared_namespace():
    """A namespace nobody declared is one no claim gate is reading."""
    undeclared = {
        op for op in admitted_operations()
        if op.split(".")[0] not in OPERATION_NAMESPACES
    }
    assert undeclared == set(), (
        f"declare the namespace in OPERATION_NAMESPACES first: {sorted(undeclared)}"
    )


def test_every_declared_feature_is_backed_by_named_evidence():
    """The kernel's feature list and the evidence map are one claim.

    A feature the kernel declares with no entry in the map is unbacked; an
    entry with no feature is evidence for a claim nobody makes. Either way the
    two disagree, and a capability report built on the disagreement would be
    reporting something nobody checked.
    """
    assert declared_features() == set(FEATURE_EVIDENCE)


def test_the_claim_readers_find_something_and_read_every_namespace():
    """Guards every gate above from passing because it parsed nothing.

    The synthetic bodies are the second half: an earlier reader matched
    `runtime\\.` literally, so a `platform.*` operation was invisible to it.
    A gate that cannot see a whole namespace reports a clean tree.
    """
    assert admitted_operations(), "the whitelist reader found no operation"
    assert declared_features(), "the feature reader found no feature"

    table = '{"platform.device_descriptors": {\n"runtime.identify": {'
    assert set(ADMITTED_OPERATION.findall(table)) == {
        "platform.device_descriptors", "runtime.identify",
    }
    assert DOCUMENTED_CAPABILITY.findall("`platform.x` `protocol.v6` `core.js`") == [
        "platform.x", "protocol.v6",
    ]
    assert counted_operations(
        "three operations are admitted; the two runtime operations;"
        " four read-only operations; operations"
    ) == [(3, ""), (2, "runtime"), (4, "")]
