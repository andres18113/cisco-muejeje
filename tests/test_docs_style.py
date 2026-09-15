"""Contrato de estilo y vigencia para la documentación mantenida.

La documentación tiene que renderizar como Markdown estándar en cualquier visor,
no solo bajo Material for MkDocs: sin admonitions (`!!! `), bloques colapsables
(`??? `) ni tabs de contenido (`=== "..."`). La evidencia histórica bajo
`docs/reference/cp-scale/` es inmutable y queda deliberadamente fuera del
contrato.
"""

from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
IMMUTABLE_EVIDENCE = ROOT / "docs" / "reference" / "cp-scale"
MKDOCS_CONFIG = ROOT / "mkdocs.yml"
DOCS_WORKFLOW = ROOT / ".github" / "workflows" / "docs.yml"

MATERIAL_ONLY_SYNTAX = {
    "admonition (!!!)": re.compile(r"^\s*!!! "),
    "collapsible block (???)": re.compile(r"^\s*\?\?\? "),
    'content tab (=== "...")': re.compile(r'^\s*=== "'),
}

# Entradas de mkdocs.yml que solo existen para la sintaxis que ya no se usa.
MATERIAL_ONLY_SETTINGS = (
    "admonition",
    "attr_list",
    "md_in_html",
    "pymdownx.details",
    "pymdownx.tabbed",
    "content.tabs.link",
)

# La closure vigente de CP-SCALE. La anterior no debe reaparecer en documentación
# mantenida: la autoridad es docs/reference/cp-scale/current_state.json.
SUPERSEDED_CLOSURE = "FULL_TARGET_VERIFIED"


def maintained_docs() -> list[Path]:
    candidates = [
        *ROOT.glob("*.md"),
        *ROOT.glob("docs/**/*.md"),
        *ROOT.glob("EXTENSION/**/*.md"),
    ]
    return sorted(
        path
        for path in candidates
        if IMMUTABLE_EVIDENCE not in path.parents
    )


def test_maintained_docs_use_standard_markdown():
    offenders = []
    for path in maintained_docs():
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, start=1):
            for label, pattern in MATERIAL_ONLY_SYNTAX.items():
                if pattern.match(line):
                    relative = path.relative_to(ROOT).as_posix()
                    offenders.append(f"{relative}:{number}: {label}")

    assert offenders == []


def test_the_contract_covers_the_documentation_it_should():
    """Sin esto, estrechar el glob dejaría el contrato pasando y sin cubrir nada."""
    covered = {path.relative_to(ROOT).as_posix() for path in maintained_docs()}

    assert {"README.md", "docs/index.md", "docs/tools.md"} <= covered
    assert not any(name.startswith("docs/reference/cp-scale/") for name in covered)


def test_mkdocs_does_not_declare_material_only_syntax_support():
    """Reintroducir la extensión es el primer paso para reintroducir la sintaxis."""
    entries = {
        line.strip().lstrip("- ").rstrip(":")
        for line in MKDOCS_CONFIG.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("- ")
    }

    assert entries.isdisjoint(MATERIAL_ONLY_SETTINGS)


def test_maintained_docs_do_not_name_the_superseded_cp_scale_closure():
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in maintained_docs()
        if SUPERSEDED_CLOSURE in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_the_docs_build_has_one_dependency_source():
    """Un requirements aparte se desincroniza de pyproject sin que nadie lo note."""
    workflow = DOCS_WORKFLOW.read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert not (ROOT / "docs" / "requirements.txt").exists()
    assert "requirements.txt" not in workflow
    assert '".[docs]"' in workflow
    assert "docs = [" in pyproject
