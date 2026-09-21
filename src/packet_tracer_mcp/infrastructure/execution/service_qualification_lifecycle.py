"""Read-only local lifecycle evidence for executable service diagnostics."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from time import monotonic
from typing import Any

from ...domain.enterprise.models.service_qualification import (
    LOCAL_OBSERVATION_TIMEOUT_SECONDS,
    DiagnosticLifecycleObservation,
)
from .cp_scale_live_preflight import PowerShellPacketTracerProcessReader
from .file_bridge import bridge_dir


class PowerShellProcessIncarnationReader:
    """Read one process's creation time, which a reused PID does not carry.

    The operating system reuses process identifiers. A Packet Tracer that
    crashed and was replaced can therefore present the authorized PID and the
    authorized path while being a different process that this authority never
    bound, and it polls the same mailbox. Creation time is the incarnation
    identity that distinguishes them.

    This runs one read-only query about one PID, inside a finite local bound.
    It launches, stops and contacts nothing; the only process the timeout can
    terminate is the PowerShell helper this reader owns. An unreadable answer
    is returned as the empty string, which the domain gate treats as unknown
    rather than as a match. A timeout is NOT returned that way: it propagates,
    because a wait that expired is an unobservable authority and the caller
    has to be able to tell it apart from a process that answered "no time".
    """

    def __init__(
        self,
        *,
        run_command: Callable[..., Any] = subprocess.run,
        timeout_seconds: float = LOCAL_OBSERVATION_TIMEOUT_SECONDS,
    ) -> None:
        """Inject the command runner and the finite local observation bound."""
        self._run_command = run_command
        self._timeout_seconds = max(0.0, float(timeout_seconds))

    def read(self, pid: int, *, timeout_seconds: float | None = None) -> str:
        """Return the creation timestamp within both configured bounds."""
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            return ""
        # The PID is re-rendered from a validated integer, so no external text
        # reaches the command line.
        command = (
            f"$p = Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue; "
            "if ($p) { $p.StartTime.ToString('o') }"
        )
        effective = self._timeout_seconds
        if timeout_seconds is not None:
            effective = min(effective, max(0.0, float(timeout_seconds)))
        try:
            completed = self._run_command(
                ["powershell.exe", "-NoProfile", "-Command", command],
                check=True,
                capture_output=True,
                text=True,
                timeout=effective,
            )
        except subprocess.TimeoutExpired:
            # Unobservable, not unknown-and-harmless. The lifecycle reader
            # turns this into an error the continuity gate refuses on.
            raise
        except Exception:
            return ""
        value = str(getattr(completed, "stdout", "") or "").strip()
        return value.splitlines()[0].strip() if value else ""


class PacketTracerDiagnosticLifecycleReader:
    """Bind one exact PT process and an empty mailbox before any transport.

    Reading OS process metadata and directory entries does not contact Packet
    Tracer. The reader never launches or stops a process and never removes a
    stale artifact; ambiguity is returned as an error for the domain gate.
    """

    def __init__(
        self,
        *,
        process_reader=None,
        mailbox_dir: Path | None = None,
        incarnation_reader=None,
        timeout_seconds: float = LOCAL_OBSERVATION_TIMEOUT_SECONDS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        """Inject sources, the helper cap and their shared monotonic clock."""
        self._process_reader = process_reader or PowerShellPacketTracerProcessReader(
            timeout_seconds=timeout_seconds
        )
        self._mailbox_dir = Path(mailbox_dir) if mailbox_dir else bridge_dir()
        self._incarnation_reader = (
            incarnation_reader
            or PowerShellProcessIncarnationReader(timeout_seconds=timeout_seconds)
        )
        self._timeout_seconds = max(0.0, float(timeout_seconds))
        self._clock = clock

    def read(self, deadline: float | None = None) -> DiagnosticLifecycleObservation:
        """Return one process and mailbox pairing within one absolute deadline."""
        process_timeout = self._remaining_timeout(deadline)
        if process_timeout <= 0:
            return self._deadline_observation("process")
        process = self._process_reader.read(timeout_seconds=process_timeout)
        if self._overran(deadline):
            return self._overrun_observation("process")
        if process.error:
            return DiagnosticLifecycleObservation(error=process.error)
        if len(process.processes) != 1:
            return DiagnosticLifecycleObservation(
                error=f"packet_tracer_process_count:{len(process.processes)}"
            )
        if self._remaining_timeout(deadline) <= 0:
            return self._deadline_observation("mailbox")
        try:
            entries = self._mailbox_entries()
        except OSError as exc:
            return DiagnosticLifecycleObservation(
                error=f"mailbox_inspection_failed:{type(exc).__name__}"
            )
        if self._overran(deadline):
            return self._overrun_observation("mailbox")
        item = process.processes[0]
        incarnation_timeout = self._remaining_timeout(deadline)
        if incarnation_timeout <= 0:
            return self._deadline_observation("process_incarnation")
        try:
            incarnation = str(
                self._incarnation_reader.read(
                    item.pid, timeout_seconds=incarnation_timeout
                )
                or ""
            )
        except Exception as exc:
            return DiagnosticLifecycleObservation(
                error=f"process_incarnation_unreadable:{type(exc).__name__}"
            )
        if self._overran(deadline):
            return self._overrun_observation("process_incarnation")
        return DiagnosticLifecycleObservation(
            process_id=item.pid,
            process_path=item.executable_path,
            product_version=item.product_version,
            file_version=item.file_version,
            process_incarnation=incarnation,
            mailbox_entries=entries,
        )

    def _remaining_timeout(self, deadline: float | None) -> float:
        """Return this helper's cap within the shared remaining interval."""
        if deadline is None:
            return self._timeout_seconds
        return max(0.0, min(self._timeout_seconds, float(deadline) - self._clock()))

    def _overran(self, deadline: float | None) -> bool:
        """Return whether a helper completed after its absolute deadline."""
        return deadline is not None and self._clock() > float(deadline)

    @staticmethod
    def _deadline_observation(component: str) -> DiagnosticLifecycleObservation:
        return DiagnosticLifecycleObservation(
            error=f"local_observation_deadline_exhausted:{component}"
        )

    @staticmethod
    def _overrun_observation(component: str) -> DiagnosticLifecycleObservation:
        return DiagnosticLifecycleObservation(
            error=f"local_observation_deadline_exceeded:{component}"
        )

    def _mailbox_entries(self) -> tuple[str, ...]:
        """Return pending/temporary command artifacts, excluding heartbeat."""
        if not self._mailbox_dir.exists():
            return ()
        names: set[str] = set()
        for pattern in ("req_*", "res_*"):
            for path in self._mailbox_dir.glob(pattern):
                if path.is_file():
                    names.add(path.name)
        return tuple(sorted(names))
