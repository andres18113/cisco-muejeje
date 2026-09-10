"""The files that reach Packet Tracer, and what they are allowed to be.

`platform_adapter.js` is the declared platform-call boundary (MJ-006, MJ-019):
the only packaged source that names `ipc`, and the only one that invokes a
platform member at all. The subject adapters beside it are handed a platform
object and call it by name *through* that boundary. This module gates what
those permissions cost: no mutation, no kernel state, no envelope, no dispatch,
no Cisco enum mirror, and no call this repository cannot cite.

**No adapter names a platform member at a call site.** Every platform call goes
through one function that takes the member name as data, so what this artifact
may ask Packet Tracer for is one list rather than a sweep of every call site —
and that list, and the calls that actually ran against it, are
`test_platform_allowlist`, split from here at the line budget (MJ-018, MJ-020).

That an adapter shapes no envelope and reads no kernel state is checked once,
over every declared adapter, in `test_platform_declarations`. What an adapter
*reports*, and the V6 surface in front of it, are the `test_platform_*` modules
beside this one. Nothing in any of them has reached `9.0.1.0858` (MJ-015,
MJ-031).
"""

from __future__ import annotations

import json
import re

import pytest

from tests.muejeje.engine_harness import (
    ACCESS_POINT_ROOT,
    dispatch_v6,
    node_available,
    platform_stub,
)
from tests.muejeje.measure import js_code_only
from tests.muejeje.support import SCRIPT_ENGINE
from tests.muejeje.test_platform_declarations import (
    IPC_ADAPTER_FILES,
    PLATFORM_ADAPTER_FILES,
    PLATFORM_SOURCE_FILES,
)

BOUNDARY = "platform_adapter.js"

# A member call in JavaScript source, by the name it invokes.
MEMBER_CALL = re.compile(r"\.\s*([A-Za-z_$][A-Za-z0-9_$]*)\s*\(")
# The member calls an adapter is allowed to make in its own code: JavaScript's
# own, and nothing else. Every platform call goes through `muejejeAdapterCall`,
# which takes the member name as data, so a platform getter written at a call
# site is an adapter reaching past its own boundary.
LANGUAGE_MEMBER_CALLS = {"call", "min", "push"}

# Three models, the first of them carrying a chassis, so one stub drives both
# platform operations and the whole allowlist is reachable from it.
THREE_MODELS = (
    "[{model: '2960-24TT', type: 1, supported: true, module_types: [18],"
    f" root: {ACCESS_POINT_ROOT}}},"
    " {model: '', type: 7, supported: false, module_types: [6, 18]},"
    " {model: '3650-24PS', type: 16, supported: true, module_types: [4, 18]}]"
)

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _request() -> str:
    return json.dumps({
        "v": 6, "operation_rid": "rid-adapter",
        "op": "platform.device_descriptors", "args": {},
    })


def _body(name: str) -> str:
    return (SCRIPT_ENGINE / name).read_text(encoding="utf-8")


def _adapter_names() -> list[str]:
    return [logical.rsplit("/", 1)[-1] for logical in PLATFORM_ADAPTER_FILES]


def _platform_source_names() -> list[str]:
    return [logical.rsplit("/", 1)[-1] for logical in PLATFORM_SOURCE_FILES]


def platform_members_called(body: str) -> set[str]:
    """Member calls `body` makes that are not JavaScript's own.

    The positive form of the read-only rule: an adapter's own code names no
    platform member, so anything left over here is a call that never passed
    the boundary's allowlist.
    """
    return set(MEMBER_CALL.findall(js_code_only(body))) - LANGUAGE_MEMBER_CALLS


# ---------------------------------------------------------------------------
# Structural: one boundary, and adapters that go through it.
# ---------------------------------------------------------------------------

def test_the_boundary_is_the_only_file_that_names_the_platform():
    owners = [
        path.name for path in sorted(SCRIPT_ENGINE.glob("*.js"))
        if re.search(r"(?<![.\w$])ipc\b", js_code_only(path.read_text(encoding="utf-8")))
    ]
    assert owners == [BOUNDARY], owners
    assert IPC_ADAPTER_FILES == (f"muejeje_pts/script-engine/{BOUNDARY}",)


def test_only_a_declared_adapter_reaches_the_boundary():
    """A kernel file naming `muejejeAdapterCall` would be calling the platform
    from outside every gate here, so the set that names it is asserted."""
    callers = [
        path.name for path in sorted(SCRIPT_ENGINE.glob("*.js"))
        if "muejejeAdapterCall" in js_code_only(path.read_text(encoding="utf-8"))
    ]
    assert callers == sorted(_adapter_names()), callers


@pytest.mark.parametrize("name", sorted(_adapter_names()))
def test_no_adapter_names_a_platform_member_at_a_call_site(name: str):
    """Positive, and asserted in both directions on synthetic sources: a gate
    matching nothing looks exactly like a source that calls nothing."""
    assert platform_members_called(_body(name)) == set()

    assert platform_members_called("var m = descriptor.getModel();") == {"getModel"}
    assert platform_members_called("descriptor.addSupportedModuleType(4);") == {
        "addSupportedModuleType",
    }
    assert platform_members_called(
        "var n = Math.min(a, b); list.push(n);"
        " Object.prototype.hasOwnProperty.call(o, k);"
    ) == set()


@pytest.mark.parametrize("name", sorted(_platform_source_names()))
def test_the_only_numbers_a_platform_source_carries_are_its_own_bounds(name: str):
    """A type value written down here would be a mirror by another spelling.

    Muejeje's bounds are declared in one block (MJ-029); `0` and `1` are
    structural. Any other literal is a number about the platform, and the
    platform is the only authority on those.
    """
    code = js_code_only(_body(name))
    if "MUEJEJE_PLATFORM_LIMITS = {" in code:
        code = code.replace(code.split("MUEJEJE_PLATFORM_LIMITS = {")[1].split("};")[0], "")
    literals = set(re.findall(r"(?<![\w.$])(\d+(?:\.\d+)?)", code)) - {"0", "1"}

    assert literals == set(), (
        f"{name} carries a number the platform should have answered: {literals}"
    )
