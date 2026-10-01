"""The counted operation ledger every engine call of one invocation passes.

It owns the stage ceilings, the finalization reserve, the phase and purpose
labels and the refusal semantics. A refusal proves only that the refused
call did not run.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import Enum, StrEnum

from ...domain.enterprise.models.execution import DispatchFact, ResultFact
from ...domain.enterprise.models.service_qualification import OperationEntry


class LedgerPhase(StrEnum):
    """The phase a counted operation belongs to."""

    __str__ = Enum.__str__

    ADMISSION = "admission"
    SETUP = "setup"
    EXPERIMENT = "experiment"
    #: A read-only final observation of what the run is about to leave
    #: behind. It is not an effect, so a closed effect gate does not
    #: suppress it -- the gate exists to stop further mutation, and a
    #: persistence failure is a reason to observe rather than to stop
    #: looking. It is not finalization either, so it spends the ordinary
    #: allowance and never the cleanup reserve.
    TERMINAL_OBSERVATION = "terminal_observation"
    FINALIZATION = "finalization"


class OperationRefused(RuntimeError):
    """Raised when the ledger refuses a call before it is dispatched.

    The refusal proves that this one call did not run. It says nothing about
    any earlier call, which is why it is never used as evidence of non-effect.
    """

    def __init__(self, reason: str) -> None:
        """Carry the typed reason for the refusal."""
        super().__init__(reason)
        self.reason = reason


class OperationLedger:
    """Count every engine operation against one stage ceiling.

    The counting unit is one command dispatched through the fixed transport,
    whatever its result. Outside finalization the reserve is untouchable,
    except to a call admitted inside `protected_release`, and each call's
    timeout is capped so that the reserved seconds survive too.
    """

    def __init__(
        self,
        *,
        max_operations: int,
        max_seconds: float,
        clock: Callable[[], float],
    ) -> None:
        """Start the ledger clock for one invocation."""
        self._max_operations = max_operations
        self._max_seconds = float(max_seconds)
        self._clock = clock
        self._start = clock()
        self._reserve_operations = 0
        self._reserve_seconds = 0.0
        self._reserved = False
        self._effects_open = True
        self._halt_reason = ""
        #: The control every dispatch inside an effect scope is admitted
        #: against, bound once before the invocation's first effect.
        self._effect_guard: Callable[[str, float], str] | None = None
        self._effect_scope = 0
        #: Depth of the protected-release scope. Only a caller that owns an
        #: owned-resource release opens it, and only around that one dispatch.
        self._protected_release = 0
        self._ordinary_cap_operations: int | None = None
        self._ordinary_cap_deadline: float | None = None
        self.phase = LedgerPhase.ADMISSION
        self.purpose = ""
        self.used = 0
        #: Counted calls that were charged to the reserve rather than to the
        #: ordinary allowance. Zero for every caller that never opens
        #: `protected_release`, which keeps their arithmetic exactly as it was.
        self.reserve_used = 0
        self.entries: list[OperationEntry] = []

    @property
    def refused_calls(self) -> int:
        """Return how many calls were refused before dispatch."""
        return sum(1 for item in self.entries if item.refused)

    def elapsed(self) -> float:
        """Return the seconds since the ledger started."""
        return max(0.0, self._clock() - self._start)

    def reserve(self, operations: int, seconds: float) -> None:
        """Set the finalization reserve once, before the first effect."""
        if self._reserved:
            raise RuntimeError("The finalization reserve is set exactly once.")
        self._reserve_operations = operations
        self._reserve_seconds = float(seconds)
        self._reserved = True

    def enter(self, phase: LedgerPhase) -> None:
        """Mark the phase that subsequent calls belong to."""
        self.phase = phase

    def close_effects(self, reason: str) -> None:
        """Admit only finalization calls from now on."""
        self._effects_open = False
        self._halt_reason = reason

    @contextmanager
    def purpose_of(self, purpose: str) -> Iterator[None]:
        """Label every call made inside the block."""
        previous = self.purpose
        self.purpose = purpose
        try:
            yield
        finally:
            self.purpose = previous

    def bind_effect_guard(self, guard: Callable[[str, float], str]) -> None:
        """Bind the control every effect dispatch is decided against.

        It is bound exactly once, after the invocation's execution state
        exists and before its first effect. Until then an effect scope has no
        control to satisfy, which `admit` treats as a refusal rather than as
        permission.
        """
        self._effect_guard = guard

    @contextmanager
    def effect_of(self, purpose: str) -> Iterator[None]:
        """Label a block whose dispatches change state in the receiver.

        Read-only work keeps `purpose_of`. What this adds is that each call
        admitted inside the block is decided against the effect guard
        immediately before it is handed to the channel, so one decision
        authorizes one dispatch instead of a whole phase. Scopes nest, because
        a runtime composed inside one may open its own.
        """
        self._effect_scope += 1
        try:
            with self.purpose_of(purpose):
                yield
        finally:
            self._effect_scope -= 1

    @contextmanager
    def protected_release(self) -> Iterator[None]:
        """Admit the calls inside the block against the reserve, one scope at a time.

        This is for a caller that releases a resource the invocation owns
        while ordinary work may still follow, which is why it is a scope and
        not a phase: the invocation is never switched into finalization, and
        the next call after the block is ordinary again. A call admitted here
        is charged to the reserve, may use the absolute deadline, and is still
        decided by the effect guard when one applies. It never makes reserve
        available to anything outside the block.
        """
        self._protected_release += 1
        try:
            yield
        finally:
            self._protected_release -= 1

    @contextmanager
    def ordinary_limit(
        self, *, operations: int, leave_seconds: float
    ) -> Iterator[None]:
        """Cap one product procedure while preserving later ordinary reads.

        This scope never exposes the protected cleanup reserve. Its operation
        cap starts at the current count; its time cap is absolute against the
        stage deadline so setup time cannot be borrowed back.
        """
        if (
            not self._reserved
            or self._ordinary_cap_operations is not None
            or operations < 0
            or leave_seconds < 0
        ):
            raise ValueError("ordinary product limit is not admissible")
        self._ordinary_cap_operations = self.used + operations
        self._ordinary_cap_deadline = (
            self._start + self._max_seconds - self._reserve_seconds - leave_seconds
        )
        try:
            yield
        finally:
            self._ordinary_cap_operations = None
            self._ordinary_cap_deadline = None

    def allowance(self) -> tuple[int, float]:
        """Return the operations and seconds the current phase may still use."""
        deadline = self._start + self._max_seconds
        if self._protected_release:
            operations = self._reserve_operations - self.reserve_used
        elif self.phase is LedgerPhase.FINALIZATION:
            operations = self._max_operations - self.used
        else:
            operations = (
                self._max_operations
                - self._reserve_operations
                - (self.used - self.reserve_used)
            )
            deadline -= self._reserve_seconds
            if self._ordinary_cap_operations is not None:
                operations = min(operations, self._ordinary_cap_operations - self.used)
                assert self._ordinary_cap_deadline is not None
                deadline = min(deadline, self._ordinary_cap_deadline)
        seconds = deadline - self._clock()
        return operations, seconds

    def deadline(self) -> float:
        """Return the absolute monotonic deadline for the active phase."""
        deadline = self._start + self._max_seconds
        if self.phase is not LedgerPhase.FINALIZATION and not self._protected_release:
            deadline -= self._reserve_seconds
            if self._ordinary_cap_deadline is not None:
                deadline = min(deadline, self._ordinary_cap_deadline)
        return deadline

    def can_afford(self, operations: int) -> bool:
        """Return whether `operations` more calls fit without the reserve."""
        remaining, seconds = self.allowance()
        return remaining >= operations and seconds > 0

    def wait(self, seconds: float, sleep: Callable[[float], None]) -> float:
        """Sleep at most `seconds`, capped by the phase's remaining time."""
        _operations, remaining = self.allowance()
        allowed = max(0.0, min(seconds, remaining))
        if allowed > 0:
            sleep(allowed)
        return allowed

    def admit(self, call: str, requested_timeout: float) -> tuple[int, float]:
        """Count one call and return its index and capped timeout, or refuse it.

        A call with no remaining allowance is refused before its potentially
        expensive effect guard. When the guard does run, it receives the one
        absolute deadline for this phase, and allowance is recomputed before
        dispatch because the local authority observation spends wall-clock.
        """
        reason = ""
        protected = bool(self._protected_release)
        exhausted = (
            "protected_reserve_exhausted" if protected else "operation_budget_exhausted"
        )
        phase = "protected_release" if protected else self.phase.value
        halted = (
            not self._effects_open
            and not protected
            and self.phase
            not in (
                LedgerPhase.FINALIZATION,
                LedgerPhase.TERMINAL_OBSERVATION,
            )
        )
        if halted:
            reason = f"effects_halted:{self._halt_reason}"
        operations, seconds = self.allowance()
        if not reason and operations < 1:
            reason = exhausted
        if not reason and seconds <= 0:
            reason = "time_budget_exhausted"
        if not reason and self._effect_scope:
            if self._effect_guard is None:
                # A control that is absent cannot be satisfied, and an effect
                # never proceeds on the strength of a check nobody made.
                reason = "effect_guard_not_bound"
            else:
                lost = self._effect_guard(self.purpose, self.deadline())
                if lost:
                    reason = f"execution_authority_lost:{lost}"
        # The authority read may have spent the phase's last second. A stale
        # pre-read allowance never authorizes the subsequent bridge dispatch.
        operations, seconds = self.allowance()
        if not reason and operations < 1:
            reason = exhausted
        if not reason and seconds <= 0:
            reason = "time_budget_exhausted"
        if reason:
            self.entries.append(
                OperationEntry(
                    seq=0,
                    phase=phase,
                    call=call,
                    purpose=self.purpose,
                    started_offset_seconds=round(self.elapsed(), 3),
                    refused=reason,
                )
            )
            raise OperationRefused(reason)
        timeout = max(0.0, min(float(requested_timeout), seconds))
        self.used += 1
        if protected:
            self.reserve_used += 1
        self.entries.append(
            OperationEntry(
                seq=self.used,
                phase=phase,
                call=call,
                purpose=self.purpose,
                timeout_seconds=round(timeout, 3),
                started_offset_seconds=round(self.elapsed(), 3),
            )
        )
        return len(self.entries) - 1, timeout

    def settle(
        self, index: int, *, dispatch: DispatchFact, result: ResultFact, started: float
    ) -> None:
        """Attach the channel's facts to one counted call."""
        entry = self.entries[index]
        self.entries[index] = entry.model_copy(
            update={
                "dispatch": dispatch.value,
                "result": result.value,
                "elapsed_seconds": round(max(0.0, self.elapsed() - started), 3),
            }
        )


def counted_seq(ledger: OperationLedger, start: int) -> int:
    """Return the sequence of the last call counted since `start`, or 0.

    A refused call carries sequence 0, so a window that only refused reports
    no association rather than borrowing the previous call's number.
    """
    counted = [item.seq for item in ledger.entries[start:] if item.seq]
    return counted[-1] if counted else 0
