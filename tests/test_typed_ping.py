"""Pruebas offline del ping cerrado y de su ventana de evidencia fresca."""

from __future__ import annotations

import json

import pytest

from src.packet_tracer_mcp.infrastructure.execution.typed_ping import TypedPingExecutor


@pytest.mark.parametrize(
    ("received", "reachable"),
    ((4, True), (0, False)),
)
def test_typed_ping_distinguishes_fresh_positive_and_negative(received, reachable):
    scripts: list[str] = []
    before = "C:\\>"
    output = (
        before
        + "ping 10.0.50.10\n"
        + f"Packets: Sent = 4, Received = {received}, Lost = {4 - received}\nC:\\>"
    )

    def send_and_wait(script, _timeout):
        scripts.append(script)
        if "enterCommand" in script:
            return json.dumps({"started": True, "before": before})
        return json.dumps({"found": True, "output": output})

    result = TypedPingExecutor(send_and_wait, timeout_seconds=0).ping(
        "GUEST-PC", "10.0.50.10",
    )

    assert result.reachable is reachable
    assert result.fresh_output_observed
    assert result.window_strategy == "prefix_delta"
    assert any('enterCommand("ping 10.0.50.10")' in script for script in scripts)
    assert any("getCommandPrompt" in script for script in scripts)
    assert any("getCommandLine" in script for script in scripts)


def test_typed_ping_rejects_stale_output_as_evidence():
    before = (
        "C:\\>ping 10.0.50.10\n"
        "Packets: Sent = 4, Received = 4, Lost = 0\nC:\\>"
    )

    def send_and_wait(script, _timeout):
        if "enterCommand" in script:
            return json.dumps({"started": True, "before": before})
        return json.dumps({"found": True, "output": before})

    result = TypedPingExecutor(send_and_wait, timeout_seconds=0).ping(
        "GUEST-PC", "10.0.50.10",
    )

    assert not result.reachable
    assert not result.fresh_output_observed
    assert result.window_strategy == "no_fresh_window"


def test_typed_ping_rejects_invalid_destination_before_bridge_call():
    scripts: list[str] = []

    result = TypedPingExecutor(
        lambda script, _timeout: scripts.append(script) or None,
    ).ping("GUEST-PC", "not-an-ip")

    assert not result.reachable
    assert not result.fresh_output_observed
    assert result.failure_reason == "invalid_destination"
    assert scripts == []


def test_typed_ping_rejects_destination_command_injection_before_bridge_call():
    scripts: list[str] = []

    result = TypedPingExecutor(
        lambda script, _timeout: scripts.append(script) or None,
    ).ping("GUEST-PC", "10.0.50.10\nconfigure terminal")

    assert not result.reachable
    assert not result.fresh_output_observed
    assert result.failure_reason == "invalid_destination"
    assert scripts == []


def test_typed_ping_requires_the_current_command_echo_for_attribution():
    before = "C:\\>"
    unrelated_delta = (
        before
        + "Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)\nC:\\>"
    )

    def send_and_wait(script, _timeout):
        if "enterCommand" in script:
            return json.dumps({"started": True, "before": before})
        return json.dumps({"found": True, "output": unrelated_delta})

    result = TypedPingExecutor(send_and_wait, timeout_seconds=0).ping(
        "GUEST-PC", "10.0.50.10",
    )

    assert not result.reachable
    assert not result.fresh_output_observed
    assert result.failure_reason == "current_ping_echo_not_observed"


def test_typed_ping_recognizes_fresh_ios_success_rate_output():
    scripts: list[str] = []
    before = "Router#"
    output = (
        before
        + "ping 10.0.50.10\n"
        + "Success rate is 80 percent (4/5), round-trip min/avg/max = 1/2/4 ms\n"
        + "Router#"
    )

    def send_and_wait(script, _timeout):
        scripts.append(script)
        if "enterCommand" in script:
            return json.dumps({"started": True, "before": before})
        return json.dumps({"found": True, "output": output})

    result = TypedPingExecutor(send_and_wait, timeout_seconds=0).ping(
        "HQ-R1", "10.0.50.10",
    )

    assert result.reachable
    assert result.fresh_output_observed
    assert result.window_strategy == "prefix_delta"
    assert "getCommandLine" in next(
        script for script in scripts if "enterCommand" in script
    )


def test_typed_ping_rejects_noncanonical_source_before_bridge_call():
    scripts: list[str] = []

    result = TypedPingExecutor(
        lambda script, _timeout: scripts.append(script) or None,
    ).ping(" HQ-R1", "10.0.50.10")

    assert not result.reachable
    assert not result.fresh_output_observed
    assert result.failure_reason == "invalid_source_device"
    assert scripts == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout_seconds": -0.1},
        {"interval_seconds": -0.1},
    ],
)
def test_typed_ping_rejects_negative_wait_budgets(kwargs):
    with pytest.raises(ValueError):
        TypedPingExecutor(lambda _script, _timeout: None, **kwargs)
