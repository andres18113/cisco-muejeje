"""Bounded POE-3B session composition, entirely offline."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.packet_tracer_mcp.infrastructure.execution.poe3b_session import (
    PacketTracerPoE3BLiveTransport,
    PacketTracerPoE3BSession,
    PoE3BSessionOperation,
    PoEInlineMode,
)


class _Bridge:
    def __init__(self) -> None:
        self.payloads: list[str] = []
        self._pending: list[str] = []
        self.last_disposition = SimpleNamespace(value="completed")

    def send(self, payload: str) -> bool:
        self.payloads.append(payload)
        return True

    def send_and_wait(self, payload: str, timeout: float):
        raise AssertionError("This test authorizes no result-bearing raw dispatch")

    def collect_completed(self) -> int:
        return 0


def test_live_transport_builds_only_closed_inline_payloads_for_ordered_ports() -> None:
    bridge = _Bridge()
    sleeps: list[float] = []
    transport = PacketTracerPoE3BLiveTransport(
        bridge=bridge,
        sleeper=sleeps.append,
    )

    transport.apply_inline_mode(
        "SW",
        ("FastEthernet0/2", "FastEthernet0/1"),
        PoEInlineMode.NEVER,
    )

    assert len(bridge.payloads) == 2
    assert [
        payload.split("interface ", 1)[1].split("\\n", 1)[0]
        for payload in bridge.payloads
    ] == ["FastEthernet0/2", "FastEthernet0/1"]
    assert all(" power inline never" in payload for payload in bridge.payloads)
    assert all("write" not in payload.casefold() for payload in bridge.payloads)
    assert sleeps == [6.0, 6.0]


def test_failed_bounded_transport_call_remains_observed() -> None:
    def fail() -> bool:
        raise RuntimeError("synthetic health failure")

    session = PacketTracerPoE3BSession(
        "offline-failure",
        switch_ports=("FastEthernet0/1",),
        transport=SimpleNamespace(bridge_healthy=fail),
    )

    with pytest.raises(RuntimeError, match="health failure"):
        session.bridge_healthy()

    assert tuple(record.operation for record in session.dispatches) == (
        PoE3BSessionOperation.TRANSPORT_HEALTH,
    )
