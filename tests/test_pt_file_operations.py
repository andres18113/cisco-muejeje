"""Causal tests for the governed Packet Tracer file-operation boundary."""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.infrastructure.execution.pt_file_operations import (
    PacketTracerFileOperationDenied,
    PacketTracerFileOperationGuard,
)


def test_ephemeral_policy_starts_as_an_observed_empty_ledger() -> None:
    ledger = PacketTracerFileOperationGuard.ephemeral().snapshot()

    assert ledger.authorized_operations == ()
    assert ledger.attempted_operations == ()
    assert ledger.executed_operations == ()
    assert ledger.denied_operations == ()
    assert ledger.ephemeral_safe


def test_denied_operation_is_observed_before_dispatch() -> None:
    guard = PacketTracerFileOperationGuard.ephemeral()
    dispatched: list[str] = []

    with pytest.raises(PacketTracerFileOperationDenied, match="save"):
        guard.attempt("save", lambda: dispatched.append("save"))

    ledger = guard.snapshot()
    assert dispatched == []
    assert ledger.attempted_operations == ("save",)
    assert ledger.denied_operations == ("save",)
    assert ledger.executed_operations == ()
    assert not ledger.ephemeral_safe


def test_authorized_boundary_records_dispatch_before_callback_failure() -> None:
    guard = PacketTracerFileOperationGuard(authorized_operations=("open",))

    def fail_after_dispatch() -> None:
        raise RuntimeError("synthetic adapter failure")

    with pytest.raises(RuntimeError, match="adapter failure"):
        guard.attempt("open", fail_after_dispatch)

    ledger = guard.snapshot()
    assert ledger.authorized_operations == ("open",)
    assert ledger.attempted_operations == ("open",)
    assert ledger.executed_operations == ("open",)
    assert ledger.denied_operations == ()
