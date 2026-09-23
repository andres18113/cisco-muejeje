"""Bound one commissioning phase and retain every original channel answer."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class PhaseAuthorityLost(RuntimeError):
    """An exact claim, receiver or source check refused the next dispatch."""


class PhaseAllowanceExhausted(RuntimeError):
    """The phase cannot borrow another phase's operation or time reserve."""


class PhaseEvidenceLost(RuntimeError):
    """The original answer or a write-ahead dispatch could not be retained."""


class GovernedPhaseChannel:
    """Guard each bridge call and append original request/answer events durably.

    A write-ahead ``attempt`` event is fsynced before the bridge sees the
    request. If an answer cannot be appended, the channel stops all later
    dispatch. The journal records a missing answer as missing, never as a
    proved non-effect or permission to replay a mutation.
    """

    def __init__(
        self,
        transport: Any,
        journal_path: Path,
        *,
        phase: str,
        max_operations: int,
        max_seconds: float,
        reserve_operations: int = 0,
        reserve_seconds: float = 0.0,
        authority: Callable[[], tuple[str, ...]],
        clock: Callable[[], float] = time.monotonic,
        started_at: float | None = None,
    ) -> None:
        """Seal one exclusive journal and start one monotonic phase allowance."""
        if (
            max_operations <= 0
            or max_seconds <= 0
            or not 0 <= reserve_operations < max_operations
            or not 0 <= reserve_seconds < max_seconds
        ):
            raise ValueError("phase allowance must be positive")
        self.transport = transport
        self.path = Path(journal_path).absolute()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("xb"):
            pass
        self.phase = phase
        self.max_operations = max_operations
        self.max_seconds = max_seconds
        self.reserve_operations = reserve_operations
        self.reserve_seconds = reserve_seconds
        self.authority = authority
        self.clock = clock
        self.started = clock() if started_at is None else started_at
        self.used_operations = 0
        self.evidence_lost = False
        self._cleanup_depth = 0

    @contextmanager
    def cleanup_scope(self) -> Iterator[None]:
        """Permit only caller-owned removal/restoration to spend the reserve."""
        self._cleanup_depth += 1
        try:
            yield
        finally:
            self._cleanup_depth -= 1

    def _append(self, payload: dict[str, Any]) -> None:
        if self.evidence_lost:
            raise PhaseEvidenceLost("phase evidence was already lost")
        record = {
            "phase": self.phase,
            "purpose": self.phase,
            "sequence": self.used_operations,
            "at_utc": datetime.now(UTC).isoformat(),
            "elapsed_seconds": self.clock() - self.started,
            **payload,
        }
        try:
            with self.path.open("ab") as stream:
                stream.write((json.dumps(record, ensure_ascii=False) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
        except (OSError, ValueError) as exc:
            self.evidence_lost = True
            raise PhaseEvidenceLost(
                f"phase answer could not be retained:{type(exc).__name__}"
            ) from exc

    def _before(self, script: str, method: str) -> float:
        if self.evidence_lost:
            raise PhaseEvidenceLost("phase evidence was already lost")
        if self.used_operations >= self.max_operations:
            raise PhaseAllowanceExhausted("phase operations exhausted")
        if (
            not self._cleanup_depth
            and self.used_operations >= self.max_operations - self.reserve_operations
        ):
            raise PhaseAllowanceExhausted("phase ordinary operations exhausted")
        remaining = self.max_seconds - (self.clock() - self.started)
        if remaining <= 0:
            raise PhaseAllowanceExhausted("phase seconds exhausted")
        if not self._cleanup_depth and remaining <= self.reserve_seconds:
            raise PhaseAllowanceExhausted("phase ordinary seconds exhausted")
        reasons = self.authority()
        if reasons:
            raise PhaseAuthorityLost(",".join(reasons))
        remaining = self.max_seconds - (self.clock() - self.started)
        if remaining <= 0:
            raise PhaseAllowanceExhausted("phase seconds exhausted")
        if not self._cleanup_depth and remaining <= self.reserve_seconds:
            raise PhaseAllowanceExhausted("phase ordinary seconds exhausted")
        self.used_operations += 1
        self._append({"event": "attempt", "method": method, "request_js": script})
        return remaining

    def send_and_wait(self, script: str, timeout: float) -> str | None:
        """Keep an exact waited answer, using the lesser call/phase deadline."""
        remaining = self._before(script, "send_and_wait")
        try:
            answer = self.transport.send_and_wait(script, min(timeout, remaining))
        except BaseException as exc:
            self._append({"event": "error", "error_type": type(exc).__name__})
            raise
        self._append({"event": "answer", "raw_answer": answer})
        return answer

    def dispatch_and_wait(self, script: str, timeout: float):
        """Keep the correlated dispatch facts and unabridged answer."""
        remaining = self._before(script, "dispatch_and_wait")
        try:
            outcome = self.transport.dispatch_and_wait(script, min(timeout, remaining))
        except BaseException as exc:
            self._append({"event": "error", "error_type": type(exc).__name__})
            raise
        self._append(
            {"event": "answer", "raw_answer": outcome.body, "outcome": asdict(outcome)}
        )
        return outcome

    def send(self, script: str) -> bool:
        """Retain queued status without claiming that Packet Tracer applied it."""
        self._before(script, "send")
        try:
            queued = bool(self.transport.send(script))
        except BaseException as exc:
            self._append({"event": "error", "error_type": type(exc).__name__})
            raise
        self._append({"event": "answer", "queued": queued})
        return queued

    def pt_alive(self) -> bool:
        """Read channel liveness without spending a bridge operation."""
        return bool(self.transport.pt_alive())

    def collect_completed(self) -> int:
        """Delegate retirement of this bridge's own fire-and-forget sends."""
        return int(self.transport.collect_completed())

    def has_pending_requests(self) -> bool:
        """Report this bridge's unresolved sends without a new PT command."""
        return bool(self.transport.has_pending_requests())

    def stop(self) -> None:
        """Close the owned transport if it offers a local close operation."""
        close = getattr(self.transport, "stop", None)
        if callable(close):
            close()
