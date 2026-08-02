"""Regresiones del punto de entrada de consola."""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp import server


def test_main_help_exits_without_starting_the_server(capsys, monkeypatch):
    started = []
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: started.append(kwargs))

    with pytest.raises(SystemExit) as exc:
        server.main(["--help"])

    assert exc.value.code == 0
    assert "Cisco Packet Tracer" in capsys.readouterr().out
    assert started == []


def test_main_uses_requested_stdio_transport(monkeypatch):
    started = []
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: started.append(kwargs))

    assert server.main(["--stdio"]) == 0
    assert started == [{"transport": "stdio"}]


def test_main_returns_130_when_stopped_from_the_console(monkeypatch):
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: (_ for _ in ()).throw(KeyboardInterrupt))

    assert server.main([]) == 130
