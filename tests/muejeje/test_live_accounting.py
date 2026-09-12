"""Every admitted operation is accounted for, and none is entered to pad coverage.

Split out of `test_live_evidence` when the run acquired an accounting model of
its own (MJ-018, MJ-020). The contradiction this module exists for was found by
review: the procedure required every admitted operation to be entered once, and
also forbade entering a dependent operation with a value nobody observed. When a
reading publishes no relay input the two cannot both hold, and the only way to
satisfy the first was to enter a placeholder — an envelope that looks like
evidence and is about nothing.

Coverage is now the accounting being complete: one status per operation, and
only two statuses."""

from __future__ import annotations

import json
import re

import pytest

from tests.muejeje.support import REPO_ROOT
from tests.muejeje.test_live_evidence import RELAY_INPUTS
from tests.muejeje.test_live_runbook import runbook_body, runbook_prose
from tests.muejeje.test_packaging_recipe import PASTED_BLOCK, QUALIFICATION_CALL, RECIPE

EXECUTED = "EXECUTED"
NOT_EXERCISED = "NOT_EXERCISED_PREREQUISITE_UNAVAILABLE"
STATUS_NAME = re.compile(r"\bNOT_EXERCISED[A-Z_]*")

# The worked examples the runbook must carry, each its own block: a reading that
# published nothing a later operation needed, and what each operation became.
WORKED_EXAMPLES = (
    (
        "platform.device_descriptors     EXECUTED",
        "platform.module_descriptors     NOT_EXERCISED_PREREQUISITE_UNAVAILABLE",
        "platform.module_type_support    NOT_EXERCISED_PREREQUISITE_UNAVAILABLE",
    ),
    (
        "platform.module_type_support    NOT_EXERCISED_PREREQUISITE_UNAVAILABLE",
    ),
    (
        "network.device_inventory        EXECUTED",
        "network.device_identity         NOT_EXERCISED_PREREQUISITE_UNAVAILABLE",
        "network.device_ports            NOT_EXERCISED_PREREQUISITE_UNAVAILABLE",
    ),
)


def _flat(line: str) -> str:
    return " ".join(line.split())


def carries_block(lines: tuple[str, ...], text: str) -> bool:
    """Whether `text` holds exactly these lines as one standalone text block."""
    wanted = ["```text", *(_flat(line) for line in lines), "```"]
    have = [_flat(line) for line in text.splitlines()]
    return any(have[i:i + len(wanted)] == wanted for i in range(len(have)))


def recipe_text() -> str:
    return (REPO_ROOT / RECIPE).read_text(encoding="utf-8")


def written_requests() -> list[dict]:
    """Every request the recipe writes, parsed."""
    return [
        json.loads(call)
        for block in PASTED_BLOCK.findall(recipe_text())
        for call in QUALIFICATION_CALL.findall(block)
    ]


def dependent_operations() -> set[str]:
    """Operations whose written request carries a relay input."""
    return {
        request["op"] for request in written_requests()
        if set(request["args"]) & set(RELAY_INPUTS)
    }


# ---------------------------------------------------------------------------
# Two statuses, one per operation.
# ---------------------------------------------------------------------------

def test_every_operation_receives_exactly_one_of_two_statuses():
    prose = runbook_prose()

    assert "**Every operation `runtime.capabilities` reports receives exactly one status**" in prose
    assert "EXECUTED entered, and its envelope is in the transcript" in prose
    assert (
        "NOT_EXERCISED_PREREQUISITE_UNAVAILABLE a relay input it needs was not "
        "published in this run" in prose
    )


@pytest.mark.parametrize("document", ["runbook", "recipe"])
def test_no_third_status_is_invented(document: str):
    """A new spelling of "not exercised" is a new status nobody defined."""
    text = runbook_body() if document == "runbook" else recipe_text()

    assert set(STATUS_NAME.findall(text)) == {NOT_EXERCISED}, document


def test_the_accounting_is_complete_only_with_one_line_per_operation():
    assert (
        "The accounting is complete when every operation `runtime.capabilities` "
        "reported has exactly one line." in runbook_prose()
    )


# ---------------------------------------------------------------------------
# Which operations can go unexercised, derived from what the recipe writes.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("example", WORKED_EXAMPLES, ids=["no-factory", "no-type", "no-switch"])
def test_each_worked_example_is_carried_as_its_own_block(example: tuple[str, ...]):
    assert carries_block(example, runbook_body()), example


def test_the_examples_cover_every_dependent_operation():
    """Every operation that can go unexercised has been shown going unexercised.

    Derived from the requests the recipe actually writes: an operation is
    dependent when its request carries a relay input. If one is added, it has
    no worked example until someone writes it, and this fails until then.
    """
    unexercised = {
        line.split()[0]
        for example in WORKED_EXAMPLES
        for line in example
        if line.split()[1] == NOT_EXERCISED
    }

    assert unexercised == dependent_operations()


def test_every_independent_operation_is_always_executed():
    """No relay input, so nothing can be missing, so nothing can excuse it."""
    prose = runbook_prose()
    sentence = prose.split("An operation that carries no relay input")[1]
    sentence = sentence.split("is always `EXECUTED`")[0]
    independent = {request["op"] for request in written_requests()} - dependent_operations()

    assert "every `runtime.*` operation" in sentence
    for operation in sorted(independent):
        if not operation.startswith("runtime."):
            assert f"`{operation}`" in sentence, operation
    assert independent and dependent_operations(), "the recipe parsed into nothing"


# ---------------------------------------------------------------------------
# Never padded, and never read as a failure.
# ---------------------------------------------------------------------------

def test_a_placeholder_is_never_entered_to_satisfy_coverage():
    """The contradiction this module was written for, as the rule that resolves it."""
    prose = runbook_prose()

    assert "**A placeholder is never entered to satisfy coverage.**" in prose
    assert "Coverage is the accounting being complete" in prose


def test_an_unexercised_operation_is_incomplete_evidence_not_failure():
    """Unreached is not broken, and it is not permission to invent an input."""
    prose = runbook_prose()

    assert "**`NOT_EXERCISED_PREREQUISITE_UNAVAILABLE` is incomplete target evidence.**" in prose
    assert (
        "not a failure of that operation, not a finding about the platform, and "
        "never a reason to fabricate an input" in prose
    )


def test_the_recipe_accounts_rather_than_enters_every_statement():
    """The recipe a person follows must not still say "once each"."""
    recipe = _flat(recipe_text())

    assert (
        "each accounted for exactly once: `EXECUTED`, or "
        "`NOT_EXERCISED_PREREQUISITE_UNAVAILABLE`" in recipe
    )
    assert "**A placeholder is never entered.**" in recipe
    assert (
        "the gate holds what is *written*, and which statements a run enters "
        "depends on which relay inputs that run observed" in recipe
    )


def test_a_denied_root_is_accounted_for_rather_than_padded():
    """A denial publishes nothing, so its dependents go unexercised, not faked."""
    assert (
        "one whose relay input the denied reading could not publish is "
        "`NOT_EXERCISED_PREREQUISITE_UNAVAILABLE` and is not entered with a "
        "placeholder" in runbook_prose()
    )
    assert (
        "`NOT_EXERCISED_PREREQUISITE_UNAVAILABLE` rather than entered with a "
        "placeholder" in _flat(recipe_text())
    )
