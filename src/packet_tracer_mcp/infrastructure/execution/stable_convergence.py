"""Espera acotada de un estado equivalente durante varias observaciones."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from time import monotonic, sleep
from typing import Generic, TypeVar


SnapshotT = TypeVar("SnapshotT")
FingerprintT = TypeVar("FingerprintT")


class StableConvergenceStatus(str, Enum):
    CONVERGED = "converged"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class StableConvergenceResult(Generic[SnapshotT, FingerprintT]):
    status: StableConvergenceStatus
    attempts: int
    elapsed_ms: int
    stable_samples: int
    last_snapshot: SnapshotT | None = None
    last_fingerprint: FingerprintT | None = None
    inspection_errors: int = 0
    last_error: str = ""

    @property
    def converged(self) -> bool:
        return self.status is StableConvergenceStatus.CONVERGED

    @property
    def timed_out(self) -> bool:
        return self.status is StableConvergenceStatus.TIMEOUT


class StableConvergenceWaiter(Generic[SnapshotT, FingerprintT]):
    """Converge tras N snapshots consecutivos, válidos y equivalentes.

    Una excepción de ``inspect``, ``predicate`` o ``fingerprint`` no escapa del
    waiter: cuenta como error de inspección, reinicia la racha estable y permite
    que observaciones posteriores se recuperen dentro del mismo presupuesto.
    """

    def __init__(
        self,
        inspect: Callable[[], SnapshotT],
        predicate: Callable[[SnapshotT], bool],
        fingerprint: Callable[[SnapshotT], FingerprintT],
        *,
        timeout_seconds: float = 8.0,
        interval_seconds: float = 0.25,
        stable_samples: int = 2,
        max_attempts: int | None = None,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative.")
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be non-negative.")
        if (
            isinstance(stable_samples, bool)
            or not isinstance(stable_samples, int)
            or stable_samples < 2
        ):
            raise ValueError("stable_samples must be at least 2.")
        if (
            max_attempts is not None
            and (
                isinstance(max_attempts, bool)
                or not isinstance(max_attempts, int)
                or max_attempts < 1
            )
        ):
            raise ValueError("max_attempts must be a positive integer or None.")
        self._inspect = inspect
        self._predicate = predicate
        self._fingerprint = fingerprint
        self._timeout = timeout_seconds
        self._interval = interval_seconds
        self._stable_samples = stable_samples
        self._max_attempts = max_attempts
        self._clock = clock
        self._sleep = sleeper

    def wait(self) -> StableConvergenceResult[SnapshotT, FingerprintT]:
        started = self._clock()
        attempts = 0
        streak = 0
        last_snapshot: SnapshotT | None = None
        last_fingerprint: FingerprintT | None = None
        comparison_fingerprint: FingerprintT | None = None
        has_comparison_fingerprint = False
        inspection_errors = 0
        last_error = ""

        while True:
            attempts += 1
            try:
                snapshot = self._inspect()
                last_snapshot = snapshot
                if self._predicate(snapshot):
                    current_fingerprint = self._fingerprint(snapshot)
                    last_fingerprint = current_fingerprint
                    if (
                        has_comparison_fingerprint
                        and current_fingerprint == comparison_fingerprint
                    ):
                        streak += 1
                    else:
                        comparison_fingerprint = current_fingerprint
                        has_comparison_fingerprint = True
                        streak = 1
                else:
                    streak = 0
                    last_fingerprint = None
                    comparison_fingerprint = None
                    has_comparison_fingerprint = False
            except Exception as exc:
                inspection_errors += 1
                last_error = str(exc)
                streak = 0
                last_fingerprint = None
                comparison_fingerprint = None
                has_comparison_fingerprint = False

            now = self._clock()
            elapsed_ms = int((now - started) * 1000)
            if streak >= self._stable_samples:
                return StableConvergenceResult(
                    status=StableConvergenceStatus.CONVERGED,
                    attempts=attempts,
                    elapsed_ms=elapsed_ms,
                    stable_samples=streak,
                    last_snapshot=last_snapshot,
                    last_fingerprint=last_fingerprint,
                    inspection_errors=inspection_errors,
                    last_error=last_error,
                )
            if (
                now - started >= self._timeout
                or (
                    self._max_attempts is not None
                    and attempts >= self._max_attempts
                )
            ):
                return StableConvergenceResult(
                    status=StableConvergenceStatus.TIMEOUT,
                    attempts=attempts,
                    elapsed_ms=elapsed_ms,
                    stable_samples=streak,
                    last_snapshot=last_snapshot,
                    last_fingerprint=last_fingerprint,
                    inspection_errors=inspection_errors,
                    last_error=last_error,
                )
            remaining = self._timeout - (now - started)
            self._sleep(min(self._interval, remaining))
