"""What the packaging recipe tells a person to do, held to the artifact.

The recipe is the one document a human follows by hand, inside a GUI this
repository cannot drive, so a stale step in it is not a documentation nit: it
is a module packaged from the wrong files, or a qualification run that records
our own refusal as the target's answer. Both had happened. The recipe named
nine of the twenty engine files long after the kernel had split, and its
qualification calls omitted an admitted operation; each read as current, and
nothing compared either with the artifact (MJ-008, MJ-025).

So every part of it that restates the artifact is read back and compared:

* the Script Engine files, in the order `build_options.engine_script_order`
  declares them. That order *is* the dependency direction: a partial list
  packages a module missing part of its kernel, and a reordered one is what a
  person would hold Packet Tracer's own listing against (MJ-019);
* the check of that listing, because the file names — not the order they were
  imported in — decide what Packet Tracer lists and evaluates;
* the Custom Interface files;
* every `mcpDispatchV6(...)` call it tells a person to paste, driven through
  the kernel it will be pasted into: each must be admitted, and together they
  must ask every operation the dispatcher admits;
* the surface those calls are entered on, which decides what the run is
  evidence *about*.

Driving those calls under Node establishes that this kernel admits them, and
nothing about what Packet Tracer will answer (MJ-015).
"""

from __future__ import annotations

import json
import re

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.support import REPO_ROOT, repo_manifest
from tests.muejeje.test_capability_claims import admitted_operations

RECIPE = "docs/qa/muejeje-pts-packaging-recipe.md"

# One engine file per numbered step and nothing else on the line: how the
# recipe writes an import order a person follows one file at a time.
ORDERED_ENGINE_FILE = re.compile(r"^\d+\.\s+`([a-z0-9_]+\.js)`\s*$", re.MULTILINE)
# A call the recipe tells a person to paste, and the request it sends.
QUALIFICATION_CALL = re.compile(r"mcpDispatchV6\('(\{[^'\n]*\})'\)")

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _recipe() -> str:
    return (REPO_ROOT / RECIPE).read_text(encoding="utf-8")


def _collapsed_recipe() -> str:
    """The recipe as one line, so a sentence is found however it was wrapped."""
    return re.sub(r"\s+", " ", _recipe())


def _declared_engine_files() -> list[str]:
    return [
        logical.rsplit("/", 1)[-1]
        for logical in repo_manifest()["build_options"]["engine_script_order"]
    ]


def test_the_recipe_imports_every_engine_file_in_the_declared_order():
    """Equality, in order. A missing file and a moved one break a module alike."""
    assert ORDERED_ENGINE_FILE.findall(_recipe()) == _declared_engine_files()


def test_the_recipe_has_the_run_check_the_order_packet_tracer_lists():
    """Import order decides nothing; the listing is what gets evaluated.

    On `9.0.1.0858` the Scripting Interface lists engine files by name, whatever
    order they were imported in. An earlier revision told a person to import the
    files "in the order above" and never to look at the result, so a run could
    have recorded an evaluation order nobody saw. The recipe has the listing
    compared with the declared order and written down, stops the run when they
    differ, and forbids the renamed copies that made the exploratory run work:
    those are files no recipe declares.
    """
    collapsed = _collapsed_recipe()

    assert (
        "compare the list it shows with the list above, entry by entry, and "
        "record it" in collapsed
    )
    assert "If they differ, stop" in collapsed
    assert "no file is renamed or copied" in collapsed


def test_the_recipe_imports_every_declared_custom_interface():
    recipe = _recipe()
    for logical in repo_manifest()["build_options"]["custom_interface_order"]:
        assert f"`{logical}`" in recipe, logical


@requires_node
def test_every_qualification_call_is_one_the_kernel_admits():
    """A refused call would be recorded as the target's answer.

    Under Node there is no platform, so a platform reading comes back
    unavailable — which is still `ok: true`. What may never come back is a
    refusal: it would mean the recipe sends something this artifact does not
    accept, and the run would record our mistake as its observation.
    """
    calls = QUALIFICATION_CALL.findall(_recipe())

    assert calls, "the recipe names no qualification call"
    for call in calls:
        response = dispatch_v6(call)
        assert response["ok"] is True, (call, response["error"])


def test_the_qualification_calls_ask_every_admitted_operation():
    """The run exists to record every operation's first target answer."""
    asked = {json.loads(call)["op"] for call in QUALIFICATION_CALL.findall(_recipe())}

    assert asked == admitted_operations()


def test_the_recipe_readers_find_a_list_and_notice_a_short_one():
    """Guards the gates above from passing because a parser matched nothing."""
    text = "1. `010_core.js`\n2. `220_lifecycle.js`\n3. **Save** the module\n"
    call = "mcpDispatchV6('{\"v\":6,\"op\":\"runtime.identify\"}')"

    assert ORDERED_ENGINE_FILE.findall(text) == ["010_core.js", "220_lifecycle.js"]
    assert ORDERED_ENGINE_FILE.findall(text) != _declared_engine_files()
    assert QUALIFICATION_CALL.findall(call) == ['{"v":6,"op":"runtime.identify"}']


def test_the_recipe_names_the_debug_dialog_as_the_qualification_entry_point():
    """Which engine evaluated the statement is what the run is evidence about.

    An earlier revision left the surface to the operator: the editor "has a
    Debug part, and a consumer could call in another way", and no step named
    either. A run following it could have recorded an answer from anything,
    and the record would not have said from what — so the reading would not
    have been attributable to the saved artifact at all (MJ-015).

    The Debug Dialog is the entry point because a statement entered there is
    evaluated in that module's Script Engine, which is the engine the saved
    artifact's files were evaluated into when the module started.
    """
    collapsed = _collapsed_recipe()

    assert "Debug Dialog" in collapsed
    assert "evaluated **in that module's Script Engine**" in collapsed


def test_the_recipe_has_the_run_capture_the_citation_it_cannot_assert():
    """This repository has never read the page that documents the dialog.

    `AGENTS.md` rule 6 forbids writing a step from memory, and every other UI
    element in this document is quoted from an installed page. The dialog's
    own sentence is not quotable here yet, so the recipe requires the run to
    bring it back — page, hash and wording — rather than asserting it first.
    """
    collapsed = _collapsed_recipe()

    assert "the installed help page that documents the dialog, its SHA-256" in collapsed
    assert "captured **by** the run rather than asserted ahead of it" in collapsed
