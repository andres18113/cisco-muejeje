"""Read-only OS process identity checks for governed LIVE execution."""

from __future__ import annotations

from src.packet_tracer_mcp.infrastructure.execution.live_environment_preflight import (
    packet_tracer_process_error,
)


def _process(process_id: int, *, version: str = "9.0.1.0858"):
    return {
        "ProcessName": "PacketTracer",
        "Id": process_id,
        "MainWindowHandle": 0,
        "ProductVersion": version,
        "FileVersion": version,
        "Path": "C:\\Program Files\\Cisco Packet Tracer 9.0.1\\bin\\PacketTracer.exe",
    }


def test_qt_process_identity_does_not_depend_on_main_window_handle():
    assert packet_tracer_process_error(
        [_process(4004), _process(10648)], "9.0.1.0858",
    ) == ""


def test_process_identity_still_rejects_version_and_path_ambiguity():
    assert "version mismatch" in packet_tracer_process_error(
        [_process(4004), _process(10648, version="8.2.2")], "9.0.1.0858",
    )
    different = _process(10648)
    different["Path"] = "D:\\PacketTracer.exe"
    assert "identity is ambiguous" in packet_tracer_process_error(
        [_process(4004), different], "9.0.1.0858",
    )
