"""Observe, close and terminate exactly one campaign-owned Packet Tracer PID.

Every command names one PID re-rendered from a validated integer, so no
external text reaches a command line, and nothing here enumerates windows or
matches processes by name except the read-only census. Observation reports the
operating system's own view of the process: its image, creation time, command
line and main window title. An unanswered or malformed reading is returned as
an error, never as an absent process.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: One local helper call; it contacts no Packet Tracer mailbox.
PROCESS_CONTROL_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class OwnedProcessObservation:
    """What the operating system reports about one PID at one instant."""

    process_id: int
    present: bool = False
    process_path: str = ""
    process_incarnation: str = ""
    command_line: str = ""
    main_window_title: str = ""
    error: str = ""


def _pid(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("process ID must be a positive int")
    return value


class PowerShellOwnedProcessControl:
    """Windows PowerShell helpers bound to one exact PID per call."""

    def __init__(
        self,
        *,
        run_command: Callable[..., Any] = subprocess.run,
        timeout_seconds: float = PROCESS_CONTROL_TIMEOUT_SECONDS,
    ) -> None:
        """Inject the command runner and the finite helper bound."""
        self._run_command = run_command
        self._timeout_seconds = float(timeout_seconds)

    def _run(self, command: str) -> str:
        completed = self._run_command(
            ["powershell.exe", "-NoProfile", "-Command", command],
            check=True,
            capture_output=True,
            text=True,
            timeout=self._timeout_seconds,
        )
        return str(getattr(completed, "stdout", "") or "").strip()

    def observe(self, pid: int) -> OwnedProcessObservation:
        """Read image, creation time, command line and title of one PID."""
        pid = _pid(pid)
        command = (
            f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
            "if (-not $p) { '{\"present\":false}' } else { "
            f"$c = Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; "
            "[PSCustomObject]@{ present=$true; path=$p.MainModule.FileName; "
            "incarnation=$p.StartTime.ToString('o'); "
            "command_line=[string]$c.CommandLine; "
            "title=[string]$p.MainWindowTitle } | ConvertTo-Json -Compress }"
        )
        try:
            value = json.loads(self._run(command) or "null")
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return OwnedProcessObservation(
                pid, error=f"process_unobservable:{type(exc).__name__}"
            )
        if not isinstance(value, dict) or not isinstance(value.get("present"), bool):
            return OwnedProcessObservation(pid, error="process_reading_malformed")
        if not value["present"]:
            return OwnedProcessObservation(pid, present=False)
        fields = ("path", "incarnation", "command_line", "title")
        if any(not isinstance(value.get(name), str) for name in fields):
            return OwnedProcessObservation(pid, error="process_reading_malformed")
        return OwnedProcessObservation(
            pid,
            present=True,
            process_path=value["path"],
            process_incarnation=value["incarnation"],
            command_line=value["command_line"],
            main_window_title=value["title"],
        )

    def request_close(self, pid: int) -> bool:
        """Ask the process's own main window to close; report the request."""
        pid = _pid(pid)
        command = (
            f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
            "if ($p) { [string]$p.CloseMainWindow() } else { 'False' }"
        )
        try:
            return self._run(command).splitlines()[-1].strip() == "True"
        except (OSError, IndexError, subprocess.SubprocessError):
            return False

    def terminate(self, pid: int) -> bool:
        """Terminate exactly this PID; the caller has rechecked its identity."""
        pid = _pid(pid)
        try:
            self._run(f"Stop-Process -Id {pid} -Force -ErrorAction Stop; 'ok'")
        except (OSError, subprocess.SubprocessError):
            return False
        return True

    def census(self) -> int | None:
        """Count every PacketTracer* process; `None` when unreadable."""
        command = (
            "@(Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -like 'PacketTracer*' }).Count"
        )
        try:
            return int(self._run(command).splitlines()[-1].strip())
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return None
