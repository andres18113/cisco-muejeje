"""Causal tests for the governed Packet Tracer file-operation boundary."""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.infrastructure.execution.pt_file_operations import (
    PacketTracerFileOperationDenied,
    PacketTracerFileOperationGuard,
    PacketTracerFileOperationResult,
)


def test_ephemeral_policy_starts_as_an_observed_empty_ledger() -> None:
    ledger = PacketTracerFileOperationGuard.ephemeral().snapshot()

    assert ledger.authorized_operations == ()
    assert ledger.attempted_operations == ()
    assert ledger.denied_operations == ()
    assert ledger.invoked_operations == ()
    assert ledger.completed_operations == ()
    assert ledger.indeterminate_operations == ()
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
    assert ledger.invoked_operations == ()
    assert ledger.completed_operations == ()
    assert ledger.indeterminate_operations == ()
    assert not ledger.ephemeral_safe


def test_authorized_callback_failure_is_invoked_and_indeterminate_not_completed() -> None:
    guard = PacketTracerFileOperationGuard(authorized_operations=("open",))

    def fail_after_dispatch() -> None:
        raise RuntimeError("synthetic adapter failure")

    with pytest.raises(RuntimeError, match="adapter failure"):
        guard.attempt("open", fail_after_dispatch)

    ledger = guard.snapshot()
    assert ledger.authorized_operations == ("open",)
    assert ledger.attempted_operations == ("open",)
    assert ledger.denied_operations == ()
    assert ledger.invoked_operations == ("open",)
    assert ledger.completed_operations == ()
    assert ledger.indeterminate_operations == ("open",)


def test_completion_requires_an_explicit_observed_receipt() -> None:
    guard = PacketTracerFileOperationGuard(authorized_operations=("save",))

    result = guard.attempt(
        "save",
        lambda: PacketTracerFileOperationResult(
            value="saved",
            completion_observed=True,
        ),
    )

    ledger = guard.snapshot()
    assert result == "saved"
    assert ledger.invoked_operations == ("save",)
    assert ledger.completed_operations == ("save",)
    assert ledger.indeterminate_operations == ()


def test_plain_callback_return_cannot_be_misreported_as_external_completion() -> None:
    guard = PacketTracerFileOperationGuard(authorized_operations=("save_as",))

    with pytest.raises(TypeError, match="completion receipt"):
        guard.attempt("save_as", lambda: True)  # type: ignore[arg-type,return-value]

    ledger = guard.snapshot()
    assert ledger.invoked_operations == ("save_as",)
    assert ledger.completed_operations == ()
    assert ledger.indeterminate_operations == ("save_as",)
