"""The auditor's modular cohesion and its dependency direction.

`build_state`, `privileges` and `provenance` depend on no sibling; `manifest`
may depend on `privileges`; `inventory` may depend on `build_state` and
`provenance`; `references` may depend on those three; only `build` may depend
on all of them (MJ-018, MJ-019).

`privileges` sits at the bottom on purpose. It is the authority on which
privilege identifiers exist and which may be declared, and an authority that
could reach back up into the document schema would be deciding shape and
meaning in one place.

A direction rule is only a rule if it holds however an import is spelled, so
the gate resolves relative and absolute forms of the same dependency alike.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.muejeje.measure import (
    imported_siblings,
    relative,
)
from tests.muejeje.support import (
    CLI,
    PTS_PACKAGE,
)

# Allowed intra-package imports, innermost layer first. A module may import from
# the layers below it and never from a layer at or above its own.
LAYERS: dict[str, frozenset[str]] = {
    "build_state": frozenset(),
    "privileges": frozenset(),
    "provenance": frozenset(),
    "manifest": frozenset({"privileges"}),
    "inventory": frozenset({"build_state", "provenance"}),
    "references": frozenset({"build_state", "provenance", "inventory"}),
    "build": frozenset({
        "build_state", "privileges", "provenance", "manifest", "inventory",
        "references",
    }),
    "__init__": frozenset({"build"}),
}


def owned_python_modules() -> list[Path]:
    return sorted(PTS_PACKAGE.glob("*.py")) + [CLI]


def test_the_auditor_is_split_into_the_layers_it_declares():
    on_disk = {path.stem for path in PTS_PACKAGE.glob("*.py")}
    assert on_disk == set(LAYERS), (
        "every auditor module is a declared layer, and every declared layer "
        f"exists: {on_disk ^ set(LAYERS)}"
    )


@pytest.mark.parametrize("module", sorted(LAYERS))
def test_auditor_imports_only_flow_inward(module: str):
    path = PTS_PACKAGE / f"{module}.py"
    imported = imported_siblings(path.read_text(encoding="utf-8"), set(LAYERS))
    forbidden = imported - LAYERS[module]
    assert not forbidden, (
        f"{module} may import {sorted(LAYERS[module])}; it reaches for {sorted(forbidden)}"
    )


@pytest.mark.parametrize("spelling", [
    "from .manifest import read_manifest",
    "from . import manifest",
    "from ..pts import manifest",
    "from src.packet_tracer_mcp.infrastructure.pts import manifest",
    "from packet_tracer_mcp.infrastructure.pts.manifest import read_manifest",
    "import packet_tracer_mcp.infrastructure.pts.manifest",
])
def test_the_dependency_gate_reads_every_spelling_of_the_same_import(spelling: str):
    """One module, six ways to name it. A gate that reads one reads none.

    The gate previously matched relative `ImportFrom` at level 1 alone, so
    writing the absolute path to a sibling — the same dependency, a different
    spelling — passed it silently. A direction rule that can be satisfied by
    rephrasing is not a rule.
    """
    assert imported_siblings(spelling, set(LAYERS)) == {"manifest"}


def test_the_dependency_gate_does_not_flag_a_foreign_package():
    """`shared.utils` and the standard library are not siblings."""
    unrelated = "import ast\nfrom ...shared.utils import resolve_within\n"
    assert imported_siblings(unrelated, set(LAYERS)) == set()


def test_the_facade_holds_no_rule_of_its_own():
    """`build.py` orchestrates. The vocabulary lives in the layers below it."""
    body = (PTS_PACKAGE / "build.py").read_text(encoding="utf-8")
    for owned_elsewhere in (
        "PACKAGING_MANUAL_UNAVAILABLE =",
        "OWNED_SOURCE_ROOT =",
        "EXPECTED_ARTIFACT_INPUTS =",
        "SCHEMA_VERSION =",
        "hashlib",
        "subprocess",
    ):
        assert owned_elsewhere not in body, owned_elsewhere


def test_every_auditor_module_is_declared_as_a_tooling_input():
    """A module nobody declared would change the audit outside recipe identity."""
    from src.packet_tracer_mcp.infrastructure.pts import inventory

    on_disk = {relative(path) for path in owned_python_modules()}
    assert on_disk == set(inventory.EXPECTED_TOOLING_INPUTS), (
        f"undeclared auditor modules: {sorted(on_disk ^ set(inventory.EXPECTED_TOOLING_INPUTS))}"
    )
