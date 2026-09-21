"""Diagnostic finalization of fire-and-forget transport state."""

from __future__ import annotations

from typing import Any

from service_qualification_engine import stage

__all__ = ["stage"]


class _PendingTransport:
    """Expose one pending send around the real offline engine transport."""

    def __init__(self, inner: Any, *, resolves: bool) -> None:
        self.inner = inner
        self.resolves = resolves
        self.pending = True
        self.collect_calls = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def collect_completed(self) -> int:
        """Resolve the injected pending response when configured to do so."""
        self.collect_calls += 1
        if self.resolves:
            self.pending = False
            return 1
        return 0

    def has_pending_requests(self) -> bool:
        """Report whether the injected asynchronous command remains pending."""
        return self.pending


def _run(stage, *, resolves: bool):
    """Run D-DHCP with one injected pending transport lifecycle fact."""
    observed: list[_PendingTransport] = []

    def wrap(inner):
        transport = _PendingTransport(inner, resolves=resolves)
        observed.append(transport)
        return transport

    run = stage("D-DHCP", wrap_transport=wrap)
    return run, observed[0]


def test_finalization_collects_a_completed_send_before_lifecycle_postflight(stage):
    """A locally retired response permits the ordinary clean finalization."""
    run, transport = _run(stage, resolves=True)
    record = run.record()

    assert transport.collect_calls == 1
    assert record.restoration_proven is True
    assert record.outcome.value == "completed"
    assert "transport:pending_fire_and_forget" not in record.engine_residue


def test_finalization_reports_an_unresolved_pending_send_as_residue(stage):
    """An invisible but pending send cannot support a clean restoration claim."""
    run, transport = _run(stage, resolves=False)
    record = run.record()

    assert transport.collect_calls == 1
    assert record.restoration_proven is False
    assert record.outcome.value == "stopped"
    assert "transport:pending_fire_and_forget" in record.engine_residue
    assert "transport:pending_fire_and_forget" in record.secondary_failures
