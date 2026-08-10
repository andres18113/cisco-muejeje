"""Guardas conductuales de las dos tools delgadas de E3.5.

El gate E3.6 se prueba ejecutando `pt_probe_capabilities` con un spy en lugar
del `CapabilityDiscoveryService` real: si el preflight no está READY, el probe
no debe alcanzar Packet Tracer. Inspeccionar el texto del registry no prueba
eso -- una refactorización que conserve el comportamiento rompería el test, y
una que lo pierda podría no romperlo.
"""

from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP

from src.packet_tracer_mcp.adapters.mcp import tool_registry
from src.packet_tracer_mcp.infrastructure.execution.transport_health import (
    TransportName,
    TransportSelection,
)


class _SpySnapshot:
    def compact_summary(self) -> dict:
        return {"models": 0}

    def blocking_unknowns(self) -> list:
        return []


class _StubCatalog:
    """Catálogo inerte: sólo aporta la callable que el composition root pasa."""

    @staticmethod
    def identity_for(*args, **kwargs):
        return None


class _SpyDiscoveryService:
    """Registra cada construcción y cada `run` sin tocar Packet Tracer."""

    constructions: list[dict] = []
    runs: list[object] = []

    def __init__(self, runtime=None, snapshots=None, identity_for=None):
        type(self).constructions.append({"runtime": runtime})

    @property
    def known_capabilities(self) -> list[str]:
        return ["vlan_create"]

    def run(self, request):
        type(self).runs.append(request)
        return (_SpySnapshot(), False)

    @classmethod
    def reset(cls) -> None:
        cls.constructions = []
        cls.runs = []


def _selection(selected: TransportName | None) -> TransportSelection:
    return TransportSelection(
        selected=selected,
        fallback=None,
        reason="test fixture",
    )


@pytest.fixture
def probe_tool(monkeypatch):
    """Devuelve (fn, spy) con el transporte y el token bajo control del test."""
    _SpyDiscoveryService.reset()

    # Mismo gate, reloj corto: el test comprueba la decisión, no la espera real.
    real_preflight = tool_registry.BridgeReadinessPreflight

    def _fast_preflight(**kwargs):
        kwargs.setdefault("timeout_s", 0.05)
        kwargs.setdefault("sleep", lambda _s: None)
        return real_preflight(**kwargs)

    monkeypatch.setattr(tool_registry, "BridgeReadinessPreflight", _fast_preflight)
    monkeypatch.setattr(tool_registry, "CapabilityDiscoveryService", _SpyDiscoveryService)
    monkeypatch.setattr(tool_registry, "PacketTracerBridgeProbeRuntime", lambda *a, **k: object())
    monkeypatch.setattr(tool_registry, "CapabilitySnapshotStore", lambda *a, **k: object())
    monkeypatch.setattr(tool_registry, "EnterpriseCapabilityAdapter", _StubCatalog)

    def _register(*, transport: TransportName | None, token: bool):
        monkeypatch.setattr(
            tool_registry, "select_transport", lambda *a, **k: _selection(transport),
        )
        monkeypatch.setattr(tool_registry, "has_persisted_bridge_token", lambda: token)
        server = FastMCP("test")
        tool_registry.register_tools(server)
        return server._tool_manager.get_tool("pt_probe_capabilities").fn

    return _register


class TestCapabilityProbeGate:
    def test_probe_does_not_run_when_the_token_is_missing(self, probe_tool):
        """Bridge disponible pero sin token: el preflight no está READY."""
        fn = probe_tool(transport=TransportName.HTTP, token=False)

        out = fn(models=["2911"])

        assert _SpyDiscoveryService.runs == []
        assert "BRIDGE_TOKEN_MISSING" in out

    def test_probe_does_not_run_when_no_transport_is_selectable(self, probe_tool):
        """Sin transporte seleccionable el bootstrap falla y el probe no corre."""
        fn = probe_tool(transport=None, token=True)

        out = fn(models=["2911"])

        assert _SpyDiscoveryService.runs == []
        assert "READY:" not in out

    def test_probe_runs_once_the_gate_is_ready(self, probe_tool):
        """Con bridge y token el gate deja pasar exactamente una ejecución."""
        fn = probe_tool(transport=TransportName.HTTP, token=True)

        out = fn(models=["2911"])

        assert len(_SpyDiscoveryService.runs) == 1
        assert _SpyDiscoveryService.runs[0].models == ["2911"]
        assert "summary" in out

    def test_transport_pinning_does_not_bypass_the_gate(self, probe_tool):
        """El servicio fijado al transporte se construye después del gate.

        `_run_on_pinned_transport` crea un segundo servicio con el canal de la
        operación. Si el gate rechaza, ese servicio no debe llegar a existir.
        """
        fn = probe_tool(transport=TransportName.HTTP, token=False)

        fn(models=["2911"])

        # Sólo el servicio de validación de nombres, ninguno fijado al canal.
        assert _SpyDiscoveryService.runs == []
        assert len(_SpyDiscoveryService.constructions) == 1

    def test_unknown_capability_is_rejected_before_any_probe(self, probe_tool):
        """Un nombre no registrado se rechaza sin consumir el gate."""
        fn = probe_tool(transport=TransportName.HTTP, token=True)

        out = fn(capabilities=["no_registrada"])

        assert _SpyDiscoveryService.runs == []
        assert "no registradas" in out


class TestCapabilityToolSurface:
    def test_probe_tool_exposes_no_raw_javascript_or_ios_parameter(self, probe_tool):
        """La superficie tipada no acepta scripts del usuario."""
        fn = probe_tool(transport=TransportName.HTTP, token=True)

        import inspect

        params = set(inspect.signature(fn).parameters)
        assert "js_code" not in params
        assert "ios_commands" not in params
        assert params == {
            "models", "categories", "capabilities", "probe_level",
            "detail_level", "force", "packet_tracer_version",
        }

    def test_both_e35_tools_are_registered(self, probe_tool):
        probe_tool(transport=TransportName.HTTP, token=True)
        server = FastMCP("test")
        tool_registry.register_tools(server)
        names = {tool.name for tool in server._tool_manager.list_tools()}
        assert {"pt_probe_capabilities", "pt_capability_report"} <= names
