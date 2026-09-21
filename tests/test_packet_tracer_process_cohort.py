"""Packet Tracer primary/progress-helper process cohort regressions."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from packet_tracer_mcp.infrastructure.execution.cp_scale_live_preflight import (
    PowerShellPacketTracerProcessReader,
)

EXECUTABLE = r"C:\Program Files\Cisco Packet Tracer 9.0.1\bin\PacketTracer.exe"


def _primary() -> dict[str, object]:
    """Return one complete primary receiver row."""
    return {
        "ProcessName": "PacketTracer",
        "Id": 47056,
        "ParentProcessId": 30504,
        "MainWindowHandle": 70001,
        "ProductVersion": "9.0.1.0858",
        "FileVersion": "9.0.1.0858",
        "Path": EXECUTABLE,
        "CommandLine": f'"{EXECUTABLE}"',
    }


def _helper() -> dict[str, object]:
    """Return the complete progress helper observed from the exact build."""
    return {
        "ProcessName": "PacketTracer",
        "Id": 47164,
        "ParentProcessId": 47056,
        "MainWindowHandle": 0,
        "ProductVersion": "9.0.1.0858",
        "FileVersion": "9.0.1.0858",
        "Path": EXECUTABLE,
        "CommandLine": f'"{EXECUTABLE}" --progress-bar-server',
    }


def _read(payload: list[dict[str, object]]):
    """Run the production reader against one complete OS payload."""
    return PowerShellPacketTracerProcessReader(
        run_command=lambda *_args, **_kwargs: SimpleNamespace(
            stdout=json.dumps(payload),
        ),
    ).read()


def test_process_reader_binds_the_primary_and_excludes_its_exact_progress_helper():
    """A standard PT launch is one receiver, not two same-executable processes."""
    result = _read([_primary(), _helper()])

    assert result.error == ""
    assert tuple(item.pid for item in result.processes) == (47056,)


@pytest.mark.parametrize(
    "defect",
    (
        "helper_only",
        "second_helper",
        "wrong_parent",
        "wrong_path",
        "missing_command_line",
        "invalid_command_line",
        "invalid_parent",
    ),
)
def test_process_reader_refuses_an_unproven_progress_helper_cohort(defect):
    """A helper is excluded only from a complete, exact primary-owned cohort."""
    primary = _primary()
    helper = _helper()
    payload = [primary, helper]
    if defect == "helper_only":
        payload = [helper]
    elif defect == "second_helper":
        payload.append(dict(helper, Id=47165))
    elif defect == "wrong_parent":
        helper["ParentProcessId"] = 99999
    elif defect == "wrong_path":
        helper["Path"] = r"C:\Other\PacketTracer.exe"
    elif defect == "missing_command_line":
        helper.pop("CommandLine")
    elif defect == "invalid_command_line":
        helper["CommandLine"] = [f'"{EXECUTABLE}" --progress-bar-server']
    else:
        helper["ParentProcessId"] = "47056"

    result = _read(payload)

    assert result.processes == ()
    assert result.error.startswith("Packet Tracer process inspection failed:")
