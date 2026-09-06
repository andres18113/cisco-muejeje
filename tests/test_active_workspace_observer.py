"""Productive observation of the bridge-serving Packet Tracer module identity."""

from __future__ import annotations

import json

import pytest

from src.packet_tracer_mcp.infrastructure.execution.active_workspace_observer import (
    PacketTracerActiveWorkspaceObserver,
)


def test_observer_reads_identity_from_the_executing_script_module() -> None:
    calls: list[tuple[str, float]] = []

    def send_and_wait(script: str, timeout: float) -> str:
        calls.append((script, timeout))
        return json.dumps({
            "path": r"C:\live\run-1\packet-tracer-live.pts",
            "instance_id": "instance-1",
            "module_id": "module-1",
            "module_name": "Packet Tracer MCP",
        })

    sample = PacketTracerActiveWorkspaceObserver(send_and_wait).capture()

    assert sample.path == r"C:\live\run-1\packet-tracer-live.pts"
    assert sample.instance_id == "instance-1"
    assert sample.module_id == "module-1"
    assert sample.module_name == "Packet Tracer MCP"
    assert len(calls) == 1
    script, timeout = calls[0]
    assert "ipc.ipcManager().thisInstance()" in script
    assert ".getCommandLineArg()" in script
    assert ".getInstanceId()" in script
    assert timeout == 3.0


@pytest.mark.parametrize(
    "response",
    [
        None,
        "",
        "ERROR: unavailable",
        "not-json",
        "{}",
        '{"path":"C:\\\\live\\\\run.pts","instance_id":""}',
    ],
)
def test_unobservable_or_ambiguous_module_identity_fails_closed(response: str | None) -> None:
    observer = PacketTracerActiveWorkspaceObserver(lambda _script, _timeout: response)

    with pytest.raises(RuntimeError, match="identity"):
        observer.capture()
