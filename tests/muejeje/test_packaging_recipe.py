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
  declares them. That order *is* the dependency direction, so a partial or
  reordered list packages a module that fails on its first call (MJ-019);
* the Custom Interface files;
* every `mcpDispatchV6(...)` call it tells a person to paste, driven through
  the kernel it will be pasted into: each must be admitted, and together they
  must ask every operation the dispatcher admits.

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


def _declared_engine_files() -> list[str]:
    return [
        logical.rsplit("/", 1)[-1]
        for logical in repo_manifest()["build_options"]["engine_script_order"]
    ]


def test_the_recipe_imports_every_engine_file_in_the_declared_order():
    """Equality, in order. A missing file and a moved one break a module alike."""
    assert ORDERED_ENGINE_FILE.findall(_recipe()) == _declared_engine_files()


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
    text = "1. `core.js`\n2. `lifecycle.js`\n3. **Save** the module\n"
    call = "mcpDispatchV6('{\"v\":6,\"op\":\"runtime.identify\"}')"

    assert ORDERED_ENGINE_FILE.findall(text) == ["core.js", "lifecycle.js"]
    assert ORDERED_ENGINE_FILE.findall(text) != _declared_engine_files()
    assert QUALIFICATION_CALL.findall(call) == ['{"v":6,"op":"runtime.identify"}']
