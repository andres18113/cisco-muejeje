"""Cisco's own installed pages, quoted rather than remembered.

Split out of `test_unobserved_claims` when that module crossed its line budget,
and the two are genuinely different work (MJ-018, MJ-020). There: sweeping this
repository's own text for a claim that has been withdrawn. Here: reading Packet
Tracer's installed documentation and checking that it still says what a
correction was made on.

The distinction matters because of what each can settle. A withdrawn claim is
ours to delete. A claim *about Packet Tracer* can only be settled by Packet
Tracer, so the sentences it rests on are quoted from `help/default/`, re-read on
every run, and never paraphrased (MJ-015, `AGENTS.md` rule 6). A future
installed build that words one differently fails here, and the requirement is
re-read against the new wording instead of assumed to still hold.

Both gates skip when the pinned build is not installed. `test_packaging_recipe`
imports the Debug Dialog constants from this module, so the recipe quotes
exactly the sentence that was read.
"""

from __future__ import annotations

import re

import pytest

from tests.muejeje.support import INSTALLED_HELP

# What Cisco's installed reference says about the Script Engine lifecycle.
# Quoted, not paraphrased: the claim these sentences correct was a claim about
# Packet Tracer, so only Packet Tracer's own documentation can settle it. The
# page is hash-pinned in the v2 preflight inventory as `d22cafa8...`.
CISCO_SCRIPT_ENGINE_PAGE = "scriptModules_scriptEngine.htm"
CISCO_LIFECYCLE_SENTENCES = (
    "When the Script Module starts, all script files are executed (evaluated)"
    " in the Script Engine in the same order as listed in the Scripting"
    " Interface.",
    "As long as the Script Module is running, the Script Engine is running.",
    "Changes made to the Script Engine after it has started DO NOT take effect"
    " until it has been stopped and started again.",
)
# What it says about the Debug Dialog, the surface the packaging recipe's
# qualification statements are entered on. The page is hash-pinned in the v2
# preflight inventory as `4bc04309...`; this sentence was brought back from it
# by the exploratory run, and is re-read below rather than believed.
CISCO_SCRIPTING_INTERFACE_PAGE = "scriptModules_scriptingInterface.htm"
CISCO_DEBUG_DIALOG_SENTENCE = (
    "Each Script Module has its own debug dialog that accesses only the Script"
    " Module. Statements can be entered into the input field, and they will be"
    " evaluated in the script engine."
)

requires_installed_help = pytest.mark.skipif(
    not INSTALLED_HELP.is_dir(),
    reason="the target build is not installed; its documentation cannot be read",
)


def _collapsed(page_name: str) -> str:
    """One installed page as running text: tags dropped, whitespace collapsed.

    The sentences are checked against the prose a reader sees, not against the
    generated markup around it, so a regenerated page that changes only its
    tags does not fail a gate about what Cisco says.
    """
    page = (INSTALLED_HELP / page_name).read_text(encoding="utf-8", errors="replace")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))


@requires_installed_help
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
    assert sentence in _collapsed(CISCO_SCRIPT_ENGINE_PAGE), CISCO_SCRIPT_ENGINE_PAGE


@requires_installed_help
def test_cisco_documents_that_the_debug_dialog_evaluates_in_the_module_engine():
    """What makes a qualification statement a reading of the artifact.

    The recipe enters every statement in the module's Debug Dialog because a
    statement there is evaluated in that module's engine. That was written
    before any citation for it existed, and the run was asked to bring one
    back; this is it, read from the installed page, so a build that words it
    differently fails here (MJ-015, `AGENTS.md` rule 6).
    """
    collapsed = _collapsed(CISCO_SCRIPTING_INTERFACE_PAGE)

    assert CISCO_DEBUG_DIALOG_SENTENCE in collapsed, CISCO_SCRIPTING_INTERFACE_PAGE
