"""Contrato de estilo para la documentación mantenida.

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

MATERIAL_ONLY_SYNTAX = {
    "admonition (!!!)": re.compile(r"^\s*!!! "),
    "collapsible block (???)": re.compile(r"^\s*\?\?\? "),
    'content tab (=== "...")': re.compile(r'^\s*=== "'),
}


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
