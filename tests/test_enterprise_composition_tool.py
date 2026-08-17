"""La superficie MCP del flujo de producto: transporte, y nada mas.

Decision registrada, no implicita: el punto de entrada de EJECUCION del producto
es `execute_enterprise_reference`, en la capa de aplicacion. La exposicion MCP de
mutacion queda diferida a proposito.

Por que, desde la evidencia gobernada vigente:

- TD-PUBLIC-001 situa la gobernanza de superficie publica en la fase de
  Skills/facade MCP, que no esta abierta. Publicar ahora una herramienta
  enterprise mutante se adelanta a un hito que nadie declaro;
- TD-ACCEPTANCE-001 ya permite que un harness ORQUESTE mientras no ejecute las
  mutaciones. Con la secuencia dentro del caso de uso esa condicion se cumple
  sin necesidad de una fachada MCP mutante.

Asi que lo que se expone aqui es la mitad determinista y no mutante, para que el
flujo sea inspeccionable por un operador. Esta herramienta NO cierra el requisito
de superficie de ejecucion; lo cierra el caso de uso.
"""

from __future__ import annotations

import ast
import inspect
import json
import pathlib

from mcp.server.fastmcp import FastMCP

from src.packet_tracer_mcp.adapters.mcp import tool_registry

_TOOL = "pt_compose_enterprise_reference"
_REGISTRY_SOURCE = pathlib.Path(inspect.getfile(tool_registry))


def _registered_tools() -> dict[str, object]:
    server = FastMCP("test")
    tool_registry.register_tools(server)
    return {tool.name: tool for tool in server._tool_manager.list_tools()}


def _calls_made_by(function_name: str) -> set[str]:
    """Nombres invocados dentro de una tool, via AST. El docstring no cuenta."""
    tree = ast.parse(_REGISTRY_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return {
                inner.func.id if isinstance(inner.func, ast.Name)
                else getattr(inner.func, "attr", "")
                for inner in ast.walk(node)
                if isinstance(inner, ast.Call)
            }
    raise AssertionError(f"{function_name} is not defined in {_REGISTRY_SOURCE.name}")


def _intent_json(**overrides) -> str:
    payload = {
        "name": "Reference planning closure",
        "internet_required": True,
        "default_growth_percent": 0,
        "address_space": "10.0.0.0/8",
        "sites": [
            {
                "name": "A", "type": "hq",
                "endpoints": [{"role": "user_pc", "count": 7}],
                "uplinks": [
                    {"target_site_id": "b", "media": "serial"},
                    {"target_site_id": "c", "media": "serial"},
                ],
            },
            {
                "name": "B", "type": "branch",
                "endpoints": [{"role": "user_pc", "count": 14}],
                "uplinks": [
                    {"target_site_id": "a", "media": "serial"},
                    {"target_site_id": "c", "media": "serial"},
                ],
            },
            {
                "name": "C", "type": "branch",
                "endpoints": [{"role": "user_pc", "count": 14}],
                "uplinks": [
                    {"target_site_id": "a", "media": "serial"},
                    {"target_site_id": "b", "media": "serial"},
                ],
            },
        ],
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestTheToolIsRegistered:
    def test_the_composition_tool_is_registered(self):
        assert _TOOL in _registered_tools()

    def test_it_exposes_no_raw_javascript_or_ios_parameter(self):
        """La superficie tipada no acepta scripts ni CLI del usuario."""
        tool = _registered_tools()[_TOOL]
        parameters = set(tool.parameters.get("properties", {}))

        assert "js_code" not in parameters
        assert "ios_commands" not in parameters
        assert parameters <= {"intent_json", "packet_tracer_version"}


class TestItOnlyTransportsAndSerializes:
    def test_the_closure_delegates_instead_of_sequencing(self):
        """El adaptador no puede contener la secuencia: los closures no son
        importables por tests, asi que cualquier logica ahi seria intesteable.

        Se miran las LLAMADAS, via AST, no el texto: nombrar el punto de entrada
        de ejecucion en el docstring es correcto y util; llamarlo desde aqui
        seria mover la secuencia al adaptador.
        """
        called = _calls_made_by(_TOOL)

        assert "compose_enterprise_reference" in called
        for forbidden in (
            "execute_enterprise_reference",
            "ConfigurationApplicator",
            "ControlPlaneApplicator",
            "EnterprisePhysicalTopologyDeployer",
            "SerialOrientationObserver",
        ):
            assert forbidden not in called, f"{forbidden} must not be called from the adapter"


class TestItReturnsTypedResults:
    def test_a_valid_intent_returns_the_composed_summary(self):
        tool = _registered_tools()[_TOOL]
        fn = tool.fn

        payload = json.loads(fn(intent_json=_intent_json()))

        assert payload["valid"] is True
        assert payload["devices"] == 41
        assert payload["links"] == 41
        assert payload["sites"] == 3
        assert payload["physical_topology_hash"]

    def test_malformed_json_returns_a_typed_error_not_a_traceback(self):
        fn = _registered_tools()[_TOOL].fn

        payload = json.loads(fn(intent_json="{not json"))

        assert payload["valid"] is False
        assert payload["issues"]

    def test_an_intent_the_domain_rejects_reports_its_issues(self):
        fn = _registered_tools()[_TOOL].fn

        payload = json.loads(fn(intent_json=_intent_json(sites=[])))

        assert payload["valid"] is False
        assert payload["issues"]
