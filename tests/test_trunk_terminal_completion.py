"""Terminal-completion boundary for authoritative trunk observations."""

from __future__ import annotations

import json
from pathlib import Path

from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    VerificationExpectation,
    VerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)


FIXTURES = Path(__file__).with_name("fixtures")
MEASURED_SWITCH4_TRUNKS = (
    FIXTURES / "packet_tracer_9_0_1_0858_switch4_show_interfaces_trunk.txt"
).read_text(encoding="utf-8").removesuffix("\n")
MEASURED_EMPTY_TRUNK_TABLE = (
    FIXTURES / "packet_tracer_9_0_1_0858_show_interfaces_trunk_empty.txt"
).read_text(encoding="utf-8").removesuffix("\n")


class _StagedTerminal:
    """Expose successive render states below the real IOS observer."""

    def __init__(self, device_name: str, windows: list[str]) -> None:
        self.device_name = device_name
        self.baseline = f"{device_name}>"
        self._windows = windows
        self.observation_reads = 0
        self.current = self.baseline

    def __call__(self, javascript: str, _timeout: float) -> str:
        if "terminal_kind:'ios_command_line'" in javascript:
            return json.dumps({
                "found": True,
                "booting": False,
                "terminal": True,
                "terminal_available": True,
                "terminal_kind": "ios_command_line",
                "prompt": self.baseline,
                "output": self.baseline,
            })
        if "var before=String(t.getOutput())" in javascript:
            assert 'enterCommand("show interfaces trunk")' in javascript
            return json.dumps({
                "ok": True,
                "before": self.baseline,
                "expected_prompt": self.baseline,
            })
        if "configuration_channel:o!==" in javascript:
            index = min(self.observation_reads, len(self._windows) - 1)
            self.current = self.baseline + self._windows[index]
            self.observation_reads += 1
            return json.dumps({
                "found": True,
                "configuration_channel": True,
                "output": self.current,
            })
        if "owner_name:owner" in javascript:
            return json.dumps({
                "found": True,
                "configuration_channel": self.current != self.baseline,
                "output": self.current,
                "owner_name": self.device_name,
                "owner_evidence": "terminal_object_identity",
                "owner_candidates": 1,
                "device_count": 1,
            })
        raise AssertionError(f"Unexpected terminal interaction: {javascript}")


def _expectation(device_name: str) -> VerificationExpectation:
    return VerificationExpectation(
        id=f"cfg/verify/measured-{device_name.casefold()}-gig0-1",
        action_id=f"cfg/trunk/measured-{device_name.casefold()}-gig0-1",
        kind=VerificationKind.TRUNK,
        device_id=f"measured-{device_name.casefold()}",
        device_name=device_name,
        expected={
            "interface": "GigabitEthernet0/1",
            "allowed_vlans": [10, 20, 30],
        },
    )


def _observe(device_name: str, windows: list[str]):
    terminal = _StagedTerminal(device_name, windows)
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=terminal,
    )
    return runtime.read_trunk(device_name, "GigabitEthernet0/1"), terminal


def test_trunk_observer_waits_past_an_echo_only_render_before_calling_it_complete() -> None:
    """A changed buffer is not a complete table until IOS returns to prompt.

    The final window is retained verbatim from Floor3 network-state evidence in
    ``canonical-cp-scale-voice-20260912T233455597224Z-09d2003dd529``.  Its
    command-only prefix models the rendering boundary that the executor must
    not promote to a complete empty response.
    """

    command_only = MEASURED_SWITCH4_TRUNKS.split(
        "Port        Mode", maxsplit=1,
    )[0]

    observed, terminal = _observe(
        "Switch4", [command_only, MEASURED_SWITCH4_TRUNKS],
    )

    assert terminal.observation_reads == 2
    assert observed.output_complete
    assert observed.interface == "Gig0/1"
    assert observed.status == "trunking"
    assert observed.allowed_vlans == (10, 20, 30)
    assert observed.active_vlans == (10, 20, 30)
    assert observed.forwarding_vlans == (10, 20, 30)


def test_prompt_closed_measured_empty_trunk_table_remains_an_authoritative_absence() -> None:
    """Completion hardening must not turn every missing row unobservable."""

    terminal = _StagedTerminal("Switch", [MEASURED_EMPTY_TRUNK_TABLE])
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=terminal,
        trunk_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )

    result = runtime.verify([_expectation("Switch")])[0]

    assert terminal.observation_reads == 1
    assert result.status is ActionExecutionStatus.FAILED
    assert result.convergence is not None
    assert result.convergence.details["terminal_failure_dimension"] == (
        "NO_MATCHING_ROW"
    )
    assert result.convergence.details["transitions"][0]["raw_output"] == (
        MEASURED_EMPTY_TRUNK_TABLE
    )


def test_trunk_transition_retains_the_exact_window_that_entered_the_parser() -> None:
    """A future missing row must be diagnosable from measured raw evidence."""

    expectation = _expectation("Switch4")
    terminal = _StagedTerminal("Switch4", [MEASURED_SWITCH4_TRUNKS])
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=terminal,
        trunk_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.convergence is not None
    transition = result.convergence.details["transitions"][0]
    assert transition["raw_output"] == MEASURED_SWITCH4_TRUNKS
