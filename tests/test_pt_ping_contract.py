"""Contrato publico de `pt_verify_connectivity` (el "pt_ping" del handoff).

Por que existe:
La tool despachaba `enterCommand` por su cuenta y decidia contando marcadores
de estadistica en la consola. Ese conteo no podia distinguir `ping` de `ing`:
veia aparecer un bloque nuevo y lo daba por resultado. Al enrutarla por
`TypedPingExecutor` cambio la forma de algunas respuestas, y no habia ni un
solo test que fijara esa forma.
"""

from __future__ import annotations

import pytest
from mcp.server.fastmcp import FastMCP

from src.packet_tracer_mcp.adapters.mcp import tool_registry
from src.packet_tracer_mcp.infrastructure.execution.transport_health import (
    TransportName,
    TransportSelection,
)
from src.packet_tracer_mcp.infrastructure.execution.typed_ping import (
    TypedPingExecutor,
    TypedPingResult,
)


def _selection() -> TransportSelection:
    return TransportSelection(
        selected=TransportName.FILE, fallback=None, reason="test fixture",
    )


@pytest.fixture
def ping_tool(monkeypatch):
    """Devuelve una fabrica: `ping_tool(executor_factory)` -> fn de la tool."""
    monkeypatch.setattr(tool_registry, "select_transport", lambda *a, **k: _selection())

    def _register(executor_factory):
        monkeypatch.setattr(tool_registry, "TypedPingExecutor", executor_factory)
        server = FastMCP("test")
        tool_registry.register_tools(server)
        return server._tool_manager.get_tool("pt_verify_connectivity").fn

    return _register


def _fixed(result: TypedPingResult):
    class _Executor:
        def __init__(self, *args, **kwargs):
            pass

        def ping(self, source_device, destination):
            return result

    return _Executor


def _driven_by(terminal_output: str, *, before: str = "C:\\>"):
    """Fabrica que corre el ejecutor REAL contra una terminal guionada."""
    import json

    def send_and_wait(script, _timeout):
        if "enterCommand" in script:
            return json.dumps({"started": True, "before": before})
        return json.dumps({"found": True, "output": terminal_output})

    def factory(_bridge_callable, **kwargs):
        kwargs["timeout_seconds"] = 0
        return TypedPingExecutor(send_and_wait, **kwargs)

    return factory


# -- forma de la respuesta ------------------------------------------------

def test_a_reachable_ping_reports_connectivity_with_its_full_statistic(ping_tool):
    fn = ping_tool(_fixed(TypedPingResult(
        reachable=True, fresh_output_observed=True,
        statistics="Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)",
    )))

    out = fn(from_device="PC0", to_ip="10.0.0.1")

    assert "CONECTIVIDAD OK" in out
    # El contrato anterior mostraba `Lost` y el porcentaje; recortar la linea
    # en `Received` los perdia silenciosamente.
    assert "Lost = 0 (0% loss)" in out


def test_an_unreachable_ping_reports_no_connectivity_not_an_error(ping_tool):
    fn = ping_tool(_fixed(TypedPingResult(
        reachable=False, fresh_output_observed=True,
        statistics="Packets: Sent = 4, Received = 0, Lost = 4 (100% loss)",
    )))

    out = fn(from_device="PC0", to_ip="10.0.0.1")

    assert "SIN CONECTIVIDAD" in out
    assert "Lost = 4 (100% loss)" in out


def test_a_corrupted_dispatch_is_never_reported_as_connectivity(ping_tool):
    """`ping` que llego como `ing` no es un resultado de conectividad."""
    fn = ping_tool(_fixed(TypedPingResult(
        reachable=False, fresh_output_observed=False,
        failure_reason="command_dispatch_mismatch:prefix_loss:ing 10.0.0.1",
    )))

    out = fn(from_device="PC0", to_ip="10.0.0.1")

    assert "CONECTIVIDAD OK" not in out
    assert "SIN CONECTIVIDAD" not in out
    assert "command_dispatch_mismatch" in out


def test_an_unobservable_echo_is_reported_as_not_attributable(ping_tool):
    fn = ping_tool(_fixed(TypedPingResult(
        reachable=False, fresh_output_observed=False,
        failure_reason="current_ping_echo_not_observed",
    )))

    out = fn(from_device="PC0", to_ip="10.0.0.1")

    assert "CONECTIVIDAD OK" not in out
    assert "sin resultado atribuible" in out
    assert "current_ping_echo_not_observed" in out


def test_a_pager_blocked_dispatch_is_reported_not_swallowed(ping_tool):
    fn = ping_tool(_fixed(TypedPingResult(
        reachable=False, fresh_output_observed=False,
        failure_reason="prompt_not_ready_pager_active",
    )))

    out = fn(from_device="PC0", to_ip="10.0.0.1")

    assert "prompt_not_ready_pager_active" in out
    assert "CONECTIVIDAD OK" not in out


def test_an_invalid_destination_never_reaches_the_bridge(ping_tool):
    reached = []

    class _Executor:
        def __init__(self, *args, **kwargs):
            pass

        def ping(self, source_device, destination):
            reached.append(destination)
            return TypedPingResult(False, False)

    out = ping_tool(_Executor)(from_device="PC0", to_ip="no-es-una-ip")

    assert reached == []
    assert "inválido" in out.casefold() or "invalido" in out.casefold()


# -- la propiedad de fondo, con el ejecutor real --------------------------

def test_an_old_successful_ping_in_the_buffer_is_not_a_new_success(ping_tool):
    """Sin ventana atribuible no hay conectividad, por mas exito que haya arriba.

    El conteo de marcadores anterior miraba cuantos bloques de estadistica
    habia; una consola con un ping exitoso viejo y una ejecucion nueva que no
    imprimio nada podia leerse como exito.
    """
    stale_success = (
        "C:\\>ping 10.0.0.1\n"
        "Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)\nC:\\>"
    )
    # `before` ya contiene el exito viejo, asi que la ventana fresca es vacia.
    fn = ping_tool(_driven_by(stale_success, before=stale_success))

    out = fn(from_device="PC0", to_ip="10.0.0.1")

    assert "CONECTIVIDAD OK" not in out
    assert "sin resultado atribuible" in out


def test_a_freshly_attributed_success_still_reports_connectivity(ping_tool):
    """El control positivo del test anterior: con ventana fresca, si mide."""
    fn = ping_tool(_driven_by(
        "C:\\>ping 10.0.0.1\n"
        "Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)\nC:\\>",
    ))

    out = fn(from_device="PC0", to_ip="10.0.0.1")

    assert "CONECTIVIDAD OK" in out
    assert "Lost = 0 (0% loss)" in out
