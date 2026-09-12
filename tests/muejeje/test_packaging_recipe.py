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
* every refusal it tells a person to provoke, driven the same way: each must
  come back with the code the recipe names, and together they must cover every
  class a request can reach;
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
from tests.muejeje.support import REPO_ROOT, SCRIPT_ENGINE, repo_manifest
from tests.muejeje.test_capability_claims import admitted_operations
from tests.muejeje.test_cisco_reference import (
    CISCO_DEBUG_DIALOG_SENTENCE,
    CISCO_SCRIPTING_INTERFACE_PAGE,
)

RECIPE = "docs/qa/muejeje-pts-packaging-recipe.md"

# One engine file per numbered step and nothing else on the line: how the
# recipe writes an import order a person follows one file at a time.
ORDERED_ENGINE_FILE = re.compile(r"^\d+\.\s+`([a-z0-9_]+\.js)`\s*$", re.MULTILINE)
# A block of statements the recipe tells a person to paste.
PASTED_BLOCK = re.compile(r"^```javascript\n(.*?)\n```", re.MULTILINE | re.DOTALL)
# A call in one of those blocks, and the request it sends.
QUALIFICATION_CALL = re.compile(r"mcpDispatchV6\('(\{[^'\n]*\})'\)")
# A refusal the recipe tells a person to provoke, and the code it must come back
# with. A table row rather than a block, so the two kinds of step cannot mix.
REFUSAL_ROW = re.compile(
    r"^\| `mcpDispatchV6\('([^'\n]*)'\)` \| `([A-Z_]+)` \|$", re.MULTILINE,
)

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


def _admitted_calls() -> list[str]:
    """The calls in pasted blocks, in the order the recipe drives them."""
    return [
        call for block in PASTED_BLOCK.findall(_recipe())
        for call in QUALIFICATION_CALL.findall(block)
    ]


def _request_refusal_codes() -> list[str]:
    """Every failure code a request can provoke: the taxonomy but the engine's own."""
    body = (SCRIPT_ENGINE / "020_protocol_v6.js").read_text(encoding="utf-8")
    taxonomy = body.split("var MUEJEJE_V6_ERRORS = {")[1].split("};")[0]
    codes = re.findall(r'^\s+([A-Z_]+): "', taxonomy, re.MULTILINE)
    return sorted(code for code in codes if code != "ENGINE_EXCEPTION")


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
    calls = _admitted_calls()

    assert calls, "the recipe names no qualification call"
    for call in calls:
        response = dispatch_v6(call)
        assert response["ok"] is True, (call, response["error"])


def test_the_qualification_calls_ask_every_admitted_operation():
    """The run exists to record every operation's first target answer."""
    asked = {json.loads(call)["op"] for call in _admitted_calls()}

    assert asked == admitted_operations()


def test_the_refusal_table_covers_every_class_a_request_can_provoke():
    """One row per class, no class twice, and none the kernel does not define."""
    rows = REFUSAL_ROW.findall(_recipe())

    assert sorted(code for _, code in rows) == _request_refusal_codes()


@requires_node
def test_every_refusal_the_recipe_provokes_comes_back_with_its_code():
    """A row is evidence only if this kernel refuses it for that reason too.

    A request this kernel refused for a different reason would have the run
    record Packet Tracer's engine disagreeing with Node, when the disagreement
    was the recipe's (MJ-015, MJ-022).
    """
    for request, code in REFUSAL_ROW.findall(_recipe()):
        response = dispatch_v6(request)
        assert response["ok"] is False, request
        assert response["error"]["code"] == code, (request, response["error"])


def test_the_recipe_restarts_the_module_before_the_readings():
    """A stop and a start, recorded by the operator, then who it is again.

    The operator's record, not the answers, separates the two evaluations
    (MJ-023), and the platform and workspace readings come after it, so every
    one of them belongs to the second evaluation.
    """
    rids = [json.loads(call)["operation_rid"] for call in _admitted_calls()]

    assert rids.index("qual-capabilities") < rids.index("qual-identify-restart")
    assert rids.index("qual-identify-restart") < rids.index("qual-descriptors")
    assert "Record when each happened" in _collapsed_recipe()


def test_the_recipe_readers_find_a_list_and_notice_a_short_one():
    """Guards the gates above from passing because a parser matched nothing."""
    text = "1. `010_core.js`\n2. `220_lifecycle.js`\n3. **Save** the module\n"
    call = "mcpDispatchV6('{\"v\":6,\"op\":\"runtime.identify\"}')"
    pasted = f"```javascript\n{call}\n```\n"
    refusal = "| `mcpDispatchV6('{not json')` | `MALFORMED_REQUEST` |\n"

    assert ORDERED_ENGINE_FILE.findall(text) == ["010_core.js", "220_lifecycle.js"]
    assert ORDERED_ENGINE_FILE.findall(text) != _declared_engine_files()
    assert QUALIFICATION_CALL.findall(call) == ['{"v":6,"op":"runtime.identify"}']
    assert PASTED_BLOCK.findall(pasted + refusal) == [call]
    assert REFUSAL_ROW.findall(pasted + refusal) == [("{not json", "MALFORMED_REQUEST")]


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


def test_the_recipe_quotes_the_page_that_documents_the_dialog():
    """The citation the run was asked to bring back is quoted, not deferred.

    `AGENTS.md` rule 6 forbids writing a step from memory. An earlier revision
    had the run bring the dialog's sentence back rather than assert it; the
    exploratory run did, from a page the v2 preflight inventory already pins,
    and `test_cisco_reference` re-reads it from the installed page. This holds
    the recipe to quoting exactly that sentence, from exactly that page.
    """
    collapsed = _collapsed_recipe()

    assert f"`{CISCO_SCRIPTING_INTERFACE_PAGE}`" in collapsed
    assert CISCO_DEBUG_DIALOG_SENTENCE in collapsed


def test_the_recipe_records_diagnostics_and_never_widens_privilege_mid_run():
    """A reading names no cause; what Packet Tracer printed beside it can.

    The only attribution either run has had came from a diagnostic printed
    beside each envelope, so the recipe requires recording one for every
    statement. A denial is not answered by selecting another privilege: that
    would make the rest of the run a different recipe's evidence (MJ-031,
    MJ-032).
    """
    collapsed = _collapsed_recipe()

    assert "Record, beside every envelope, whatever Packet Tracer printed" in collapsed
    assert (
        "If a root call is denied for privilege again, record the diagnostic "
        "and keep going through the rest of the list." in collapsed
    )
    assert "Never change the privileges during a run." in collapsed


def test_the_recipe_declares_the_minimum_privilege_and_has_it_read_back():
    """The one field this line changed, held to the manifest that declares it.

    A recipe that named a privilege the manifest does not — or that let the
    operator start importing before checking the selection — would package a
    module whose privilege set nobody confirmed, and its answers would belong
    to an artifact no recipe id identifies.
    """
    collapsed = _collapsed_recipe()
    declared = repo_manifest()["build_options"]["privileges"]

    assert declared == ["GET_NETWORK_INFO"]
    assert "| Privileges | `GET_NETWORK_INFO`, and nothing else |" in collapsed
    assert "Then read the selection back and record it" in collapsed
    assert "Every other privilege must be unselected." in collapsed


def test_the_recipe_keeps_a_root_denial_apart_from_a_descendant_failure():
    """Two different results, and a run that merges them evidences neither.

    If a root call now answers, the rest of that surface is exercised in the
    same run; a call that then fails is a fact about that `Interface.member`.
    Recording it as "the privilege is still wrong" would hide a working root
    behind a broken descendant.
    """
    collapsed = _collapsed_recipe()

    assert (
        "If a root call now succeeds, continue through every operation below "
        "it in the same run." in collapsed
    )
    assert "not about the root privilege" in collapsed
    assert "contradiction between the binary evidence" in collapsed
