"""Per-dispatch authority, budget and raw-answer retention for commissioning."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class _Bridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    def send_and_wait(self, script: str, timeout: float) -> str:
        self.calls.append((script, timeout))
        return '{"raw":"original IOS answer"}'

    def send(self, script: str) -> bool:
        self.calls.append((script, 0.0))
        return True


def test_phase_channel_archives_original_answer_and_denies_lost_receiver(
    tmp_path: Path,
):
    """A lost receiver prevents the second request, preserving the first body."""
    from packet_tracer_mcp.infrastructure.execution.server_pt_phase_channel import (
        GovernedPhaseChannel,
        PhaseAuthorityLost,
    )

    bridge = _Bridge()
    readings = 0

    def authority():
        nonlocal readings
        readings += 1
        return () if readings == 1 else ("receiver_lost",)

    path = tmp_path / "raw-setup.jsonl"
    channel = GovernedPhaseChannel(
        bridge,
        path,
        phase="setup",
        max_operations=2,
        max_seconds=20,
        authority=authority,
    )

    assert channel.send_and_wait("show interfaces trunk", 5.0) == (
        '{"raw":"original IOS answer"}'
    )
    with pytest.raises(PhaseAuthorityLost, match="receiver_lost"):
        channel.send("configure something")

    events = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(bridge.calls) == 1
    assert [event["event"] for event in events] == ["attempt", "answer"]
    assert events[1]["raw_answer"] == '{"raw":"original IOS answer"}'
    assert events[0]["purpose"] == "setup"


def test_phase_channel_refuses_operation_cap_before_dispatch(tmp_path: Path):
    """No bridge operation can borrow the acceptance reserve."""
    from packet_tracer_mcp.infrastructure.execution.server_pt_phase_channel import (
        GovernedPhaseChannel,
        PhaseAllowanceExhausted,
    )

    bridge = _Bridge()
    channel = GovernedPhaseChannel(
        bridge,
        tmp_path / "raw-setup.jsonl",
        phase="setup",
        max_operations=1,
        max_seconds=20,
        authority=lambda: (),
    )

    assert channel.send("first") is True
    with pytest.raises(PhaseAllowanceExhausted, match="operations"):
        channel.send("second")
    assert len(bridge.calls) == 1


def test_prequalification_reserve_remains_for_owned_cleanup(tmp_path: Path):
    """Probe reads cannot consume the reserved removal and restoration calls."""
    from packet_tracer_mcp.infrastructure.execution.server_pt_phase_channel import (
        GovernedPhaseChannel,
        PhaseAllowanceExhausted,
    )

    bridge = _Bridge()
    now = [0.0]
    channel = GovernedPhaseChannel(
        bridge,
        tmp_path / "raw-prequalification.jsonl",
        phase="prequalification",
        max_operations=3,
        max_seconds=10,
        reserve_operations=1,
        reserve_seconds=3,
        authority=lambda: (),
        clock=lambda: now[0],
    )

    assert channel.send("probe-1")
    assert channel.send("probe-2")
    with pytest.raises(PhaseAllowanceExhausted, match="ordinary"):
        channel.send("unbudgeted-probe")
    now[0] = 8.0
    with channel.cleanup_scope():
        assert channel.send("owned-cleanup")
    with pytest.raises(PhaseAllowanceExhausted, match="operations"):
        channel.send("fourth")
    assert len(bridge.calls) == 3
