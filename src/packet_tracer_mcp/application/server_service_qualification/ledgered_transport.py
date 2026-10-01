"""The fixed-channel transport bound to one invocation's ledger.

Every runtime and probe of an invocation receives these callables and
nothing else, so no dispatch reaches the channel uncounted and a call that
raised inside the transport keeps a typed unknown outcome.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ...domain.enterprise.models.execution import DispatchFact, ResultFact
from ..ports.service_qualification import DispatchOutcome, QualificationTransport
from .operation_budget import OperationLedger


@dataclass(frozen=True)
class _Outcome:
    """A dispatch outcome for a call that raised inside the transport."""

    dispatch: DispatchFact
    result: ResultFact
    body: str | None = None
    detail: str = ""


class LedgeredTransport:
    """The only callables any runtime or probe of one invocation receives."""

    def __init__(
        self,
        ledger: OperationLedger,
        transport: QualificationTransport,
        sleep: Callable[[float], None],
        clock: Callable[[], float],
    ) -> None:
        """Bind the fixed transport to its ledger, clock and sleeper."""
        self.observation_context: Mapping[str, object] | None = None
        self._ledger = ledger
        self._transport = transport
        self._sleep = sleep
        self._clock = clock

    def clock(self) -> float:
        """Return the invocation's monotonic time, for runtimes that poll."""
        return self._clock()

    def remaining_seconds(self) -> float:
        """Return the current purpose's finite remaining wall-clock allowance."""
        return self._ledger.allowance()[1]

    def capped_sleep(self, seconds: float) -> None:
        """Sleep for a runtime's poll, capped by the phase's remaining time."""
        self._ledger.wait(seconds, self._sleep)

    def settle_pending_sends(self) -> bool:
        """Retire completed local sends and report any unresolved one fail-closed."""
        collect = getattr(self._transport, "collect_completed", None)
        pending = getattr(self._transport, "has_pending_requests", None)
        if not callable(collect) and not callable(pending):
            return False
        try:
            if callable(collect):
                collect()
            return bool(pending()) if callable(pending) else False
        except Exception:
            return True

    def send(self, js_code: str) -> bool:
        """Queue one counted fire-and-forget command."""
        index, _timeout = self._ledger.admit("send", 0.0)
        started = self._ledger.elapsed()
        try:
            accepted = bool(self._transport.send(js_code))
        except Exception:
            accepted = False
        self._ledger.settle(
            index,
            dispatch=(
                DispatchFact.ACCEPTED if accepted else DispatchFact.ACCEPTANCE_UNKNOWN
            ),
            result=ResultFact.NOT_APPLICABLE,
            started=started,
        )
        return accepted

    def send_and_wait(self, js_code: str, timeout: float) -> str | None:
        """Dispatch one counted command and return its correlated body."""
        index, capped = self._ledger.admit("send_and_wait", timeout)
        started = self._ledger.elapsed()
        try:
            raw = self._transport.send_and_wait(js_code, capped)
        except Exception:
            raw = None
        self._ledger.settle(
            index,
            dispatch=(
                DispatchFact.ACCEPTED
                if raw is not None
                else DispatchFact.ACCEPTANCE_UNKNOWN
            ),
            result=ResultFact.CORRELATED
            if raw is not None
            else ResultFact.NOT_OBSERVED,
            started=started,
        )
        return raw

    def dispatch_and_wait(self, js_code: str, timeout: float) -> DispatchOutcome:
        """Dispatch one counted command and keep its typed facts."""
        index, capped = self._ledger.admit("dispatch_and_wait", timeout)
        started = self._ledger.elapsed()
        try:
            outcome: DispatchOutcome = self._transport.dispatch_and_wait(
                js_code, capped
            )
        except Exception as exc:
            outcome = _Outcome(
                DispatchFact.ACCEPTANCE_UNKNOWN,
                ResultFact.NOT_OBSERVED,
                detail=f"transport_exception:{type(exc).__name__}",
            )
        self._ledger.settle(
            index, dispatch=outcome.dispatch, result=outcome.result, started=started
        )
        return outcome
