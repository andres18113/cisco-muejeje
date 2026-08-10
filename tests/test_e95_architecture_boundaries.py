"""Regresiones de dependencias para las fronteras transversales de E9.5."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "packet_tracer_mcp"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            result.add(("." * node.level) + (node.module or ""))
    return result


def test_enterprise_domain_never_imports_packet_tracer_infrastructure():
    offenders: dict[str, list[str]] = {}
    domain = PACKAGE / "domain" / "enterprise"
    for path in domain.rglob("*.py"):
        forbidden = sorted(
            item for item in _imports(path)
            if "infrastructure" in item or "adapters" in item
        )
        if forbidden:
            offenders[str(path.relative_to(ROOT))] = forbidden

    assert offenders == {}


def test_security_and_control_plane_do_not_reach_phone_ui_adapter():
    checked = [
        PACKAGE / "application" / "use_cases" / "apply_security.py",
        PACKAGE / "application" / "use_cases" / "apply_control_plane.py",
        PACKAGE / "infrastructure" / "execution" / "enterprise_security_runtime.py",
        PACKAGE / "infrastructure" / "execution" / "enterprise_control_plane_runtime.py",
    ]

    for path in checked:
        source = path.read_text(encoding="utf-8")
        assert "PacketTracerNativeUiPhoneControlAdapter" not in source
        assert not any(item.endswith("phone_control") for item in _imports(path))


def test_phone_control_port_exposes_no_ui_coordinates_or_callbacks():
    path = PACKAGE / "application" / "ports" / "phone_control.py"
    source = path.read_text(encoding="utf-8")

    assert "Callable" not in source
    assert "coordinate" not in source.casefold()
    assert "click" not in source.casefold()
    assert "infrastructure" not in _imports(path)
