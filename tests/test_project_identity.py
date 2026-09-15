"""Identidad del proyecto y atribución al upstream.

Cisco-Muejeje deriva de Mats2208/MCP-Packet-Tracer bajo MIT. Los mensajes que
el producto muestra deben dirigir al proyecto actual, pero la licencia y la
atribución del upstream tienen que sobrevivir a cualquier limpieza de branding.
"""

from __future__ import annotations

from pathlib import Path

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
