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


def test_cp_scale_stage_application_has_no_transport_tools_or_serialization_dependency():
    for path in (PACKAGE / "application" / "cp_scale_live").glob("*.py"):
        imports = _imports(path)
        assert not any("infrastructure" in name or name.startswith("tools") for name in imports), path
        assert not any(name in {"json", "subprocess"} for name in imports), path


def test_cp_live_tool_is_a_static_facade_and_session_owns_stop():
    facade = ast.parse((ROOT / "tools/cp_scale_canonical_live.py").read_text(encoding="utf-8"))
    assert not any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in ast.walk(facade))
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id in {"eval", "exec", "__import__"} for node in ast.walk(facade))
    for path in (PACKAGE / "application/cp_scale_live").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not any(isinstance(node, ast.Attribute) and node.attr in {"send_and_wait", "stop"}
                       for node in ast.walk(tree)), path


def test_cp_live_runtime_imports_are_acyclic():
    from importlib.util import resolve_name
    checked = list((PACKAGE / "application/cp_scale_live").glob("*.py"))
    checked += list((PACKAGE / "infrastructure").glob("*/cp_scale_live*.py"))
    checked += [PACKAGE / "adapters/cli/cp_scale_live.py"]
    names = {"packet_tracer_mcp." + path.relative_to(PACKAGE).with_suffix("").as_posix().replace("/", "."): path for path in checked}
    graph = {}
    for name, path in names.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        runtime_nodes = []
        def visit(node):
            if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
                return
            runtime_nodes.append(node)
            for child in ast.iter_child_nodes(node):
                visit(child)
        visit(tree)
        imports = []
        for node in runtime_nodes:
            if isinstance(node, ast.ImportFrom):
                module = "." * node.level + (node.module or "")
                imports.append(resolve_name(module, name.rsplit(".", 1)[0]) if node.level else module)
            elif isinstance(node, ast.Import):
                imports.extend(item.name for item in node.names)
        graph[name] = [item for item in imports if item in names]
    def walk(name, active):
        assert name not in active, " -> ".join((*active, name))
        for dependency in graph[name]:
            walk(dependency, (*active, name))
    for name in graph:
        walk(name, ())
