"""Identidad del proyecto y atribución al upstream.

Cisco-Muejeje deriva de Mats2208/MCP-Packet-Tracer bajo MIT. Los mensajes que
el producto muestra deben dirigir al proyecto actual, pero la licencia y la
atribución del upstream tienen que sobrevivir a cualquier limpieza de branding.
"""

from __future__ import annotations

from pathlib import Path
import re

from packet_tracer_mcp.settings import (
    DEVELOPER_CAPABILITY_INVESTIGATION_INSTRUCTIONS,
    SERVER_INSTRUCTIONS,
)

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_REPOSITORY = "Mats2208/MCP-Packet-Tracer"


def test_production_source_does_not_link_to_the_upstream_repository():
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "src").rglob("*.py"))
        if UPSTREAM_REPOSITORY.casefold()
        in path.read_text(encoding="utf-8").casefold()
    ]

    assert offenders == []


def test_license_keeps_the_upstream_copyright_notice():
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

    assert license_text.startswith("MIT License")
    assert "Copyright (c) 2026 Mateo - Packet Tracer MCP Server" in license_text


def test_notice_attributes_the_upstream_project_and_ptbuilder():
    notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")

    assert f"https://github.com/{UPSTREAM_REPOSITORY}" in notice
    assert "MIT License" in notice
    assert "[`LICENSE`](LICENSE)" in notice
    assert "https://github.com/kimmknight/PTBuilder" in notice


def test_server_instructions_do_not_hardcode_a_tool_count():
    """El registro decide cuántas tools hay; fijar el número deja el prompt mintiendo."""
    instructions = SERVER_INSTRUCTIONS + DEVELOPER_CAPABILITY_INVESTIGATION_INSTRUCTIONS

    assert re.search(r"\b\d+\s+tools\b", instructions) is None


def test_server_instructions_do_not_present_ptbuilder_as_the_server_identity():
    """PTBuilder es referencia histórica del generador, no lo que el servidor automatiza."""
    assert "PTBuilder" not in SERVER_INSTRUCTIONS
    assert "PTBuilder" not in DEVELOPER_CAPABILITY_INVESTIGATION_INSTRUCTIONS


def test_package_docstring_names_the_project():
    source = (ROOT / "src" / "packet_tracer_mcp" / "__init__.py").read_text(
        encoding="utf-8"
    )

    assert "Cisco-Muejeje" in source
