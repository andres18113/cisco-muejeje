"""Observe, close and terminate exactly one campaign-owned Packet Tracer PID.

Every command names one PID re-rendered from a validated integer, so no
external text reaches a command line. Nothing here matches processes by name
except the read-only census. Observation reports the operating system's own
view of the process: its image, creation time, command line and main window
title. The window census reads class and title only of windows that PID owns,
and the only close it sends targets one revalidated window handle. An
unanswered or malformed reading is returned as an error, never as an absent
process or an empty window set.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: One local helper call; it contacts no Packet Tracer mailbox.
PROCESS_CONTROL_TIMEOUT_SECONDS = 15.0
#: The most top-level windows one owned process may show in a complete
#: census. Reaching it stops the enumeration and makes the census incomplete.
WINDOW_CENSUS_LIMIT = 256
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


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


@dataclass(frozen=True)
class OwnedWindow:
    r"""One top-level window the operating system attributes to a PID.

    `owner_handle` is the window's owner (`GW_OWNER`); a visible window with
    an owner is a dialog, possibly modal. `identity_digest` is SHA-256 of
    `class_name + "\\n" + title`, computed by the helper that read them.
    """

    handle: int
    owner_pid: int
    class_name: str
    title: str
    visible: bool
    enabled: bool
    owner_handle: int
    identity_digest: str


@dataclass(frozen=True)
class OwnedWindowCensus:
    """Every top-level window of one PID at one instant, or why not.

    `complete` is true only when the enumeration finished below the limit and
    every row was attributed to the PID. An `error` means nothing was read.
    `process_start_ticks` is the process's creation time in UTC .NET ticks,
    and `visible_set_digest` names its visible windows; a later close or
    termination is sent only while both are still what this census saw.
    """

    process_id: int
    windows: tuple[OwnedWindow, ...] = ()
    complete: bool = False
    error: str = ""
    process_start_ticks: int = 0
    visible_set_digest: str = ""


@dataclass(frozen=True)
class WindowCloseResult:
    """Whether one revalidated `WM_CLOSE` was posted, and why not otherwise."""

    process_id: int
    handle: int
    sent: bool = False
    refusal: str = ""
    error: str = ""


@dataclass(frozen=True)
class TerminationResult:
    """Whether one revalidated termination was issued, and why not otherwise.

    An `error` leaves the outcome unknown: the helper may have acted.
    """

    process_id: int
    sent: bool = False
    refusal: str = ""
    error: str = ""


def _pid(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("process ID must be a positive int")
    return value


def _handle(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("window handle must be a positive int")
    return value


def window_identity_digest(class_name: str, title: str) -> str:
    """Return the digest the helper computes for one window's class and title."""
    return hashlib.sha256(f"{class_name}\n{title}".encode()).hexdigest()


def visible_set_digest(windows: tuple[OwnedWindow, ...]) -> str:
    """Return the digest the helper computes over the visible windows.

    Each visible window contributes handle, owner window, enablement and
    identity digest; the rows are sorted, so focus and enumeration order do
    not change it, while any window appearing, closing, gaining an owner,
    being disabled or retitled does.
    """
    rows = sorted(
        f"{window.handle}|{window.owner_handle}|{int(window.enabled)}|"
        f"{window.identity_digest}"
        for window in windows
        if window.visible
    )
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def _ticks(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("process start ticks must be a positive int")
    return value


def _hex_digest(value: object) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError("digest must be lowercase SHA-256 hex")
    return value


#: One user32 helper, compiled per call. Its source is constant: the only
#: values a command appends are validated integers and one hex digest. Its
#: output is ASCII JSON, so no console code page can alter a title.
_WINDOW_HELPER = r"""
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
public static class PtMcpOwnedWindows {
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsWindowEnabled(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr h, uint cmd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
    const uint GW_OWNER = 4;
    const uint WM_CLOSE = 0x0010;
    static string Esc(string s) {
        var b = new StringBuilder("\"");
        foreach (char c in s) {
            if (c == '"' || c == '\\') { b.Append('\\').Append(c); }
            else if (c < 0x20 || c > 0x7e) { b.Append("\\u").Append(((int)c).ToString("x4")); }
            else { b.Append(c); }
        }
        return b.Append("\"").ToString();
    }
    static string Digest(string cls, string title) {
        using (var sha = SHA256.Create()) {
            var bytes = sha.ComputeHash(Encoding.UTF8.GetBytes(cls + "\n" + title));
            var b = new StringBuilder();
            foreach (var x in bytes) { b.Append(x.ToString("x2")); }
            return b.ToString();
        }
    }
    static string ClassOf(IntPtr h) { var s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }
    static string TitleOf(IntPtr h) { var s = new StringBuilder(512); GetWindowText(h, s, 512); return s.ToString(); }
    static string Hex(string text) {
        using (var sha = SHA256.Create()) {
            var bytes = sha.ComputeHash(Encoding.UTF8.GetBytes(text));
            var b = new StringBuilder();
            foreach (var x in bytes) { b.Append(x.ToString("x2")); }
            return b.ToString();
        }
    }
    static long StartTicks(uint target) {
        try {
            using (var p = System.Diagnostics.Process.GetProcessById((int)target)) {
                return p.StartTime.ToUniversalTime().Ticks;
            }
        } catch (Exception) { return -1; }
    }
    // Visible windows of the PID as sorted rows; null if not enumerable.
    static List<string> VisibleRows(uint target, int limit) {
        var rows = new List<string>();
        int seen = 0;
        bool over = false;
        bool finished = EnumWindows(delegate (IntPtr h, IntPtr l) {
            uint owner;
            GetWindowThreadProcessId(h, out owner);
            if (owner != target) { return true; }
            if (++seen > limit) { over = true; return false; }
            if (IsWindowVisible(h)) {
                rows.Add(h.ToInt64() + "|" + GetWindow(h, GW_OWNER).ToInt64() + "|"
                    + (IsWindowEnabled(h) ? "1" : "0") + "|" + Digest(ClassOf(h), TitleOf(h)));
            }
            return true;
        }, IntPtr.Zero);
        if (!finished || over) { return null; }
        rows.Sort(StringComparer.Ordinal);
        return rows;
    }
    static string SetDigest(uint target, int limit) {
        var rows = VisibleRows(target, limit);
        return rows == null ? "" : Hex(string.Join("\n", rows));
    }
    public static string Census(uint target, int limit) {
        var rows = new List<string>();
        bool over = false;
        long ticks = StartTicks(target);
        bool finished = EnumWindows(delegate (IntPtr h, IntPtr l) {
            uint owner;
            GetWindowThreadProcessId(h, out owner);
            if (owner != target) { return true; }
            if (rows.Count >= limit) { over = true; return false; }
            string cls = ClassOf(h);
            string title = TitleOf(h);
            rows.Add("{\"handle\":" + h.ToInt64() + ",\"owner_pid\":" + owner
                + ",\"class_name\":" + Esc(cls) + ",\"title\":" + Esc(title)
                + ",\"visible\":" + (IsWindowVisible(h) ? "true" : "false")
                + ",\"enabled\":" + (IsWindowEnabled(h) ? "true" : "false")
                + ",\"owner_handle\":" + GetWindow(h, GW_OWNER).ToInt64()
                + ",\"identity_digest\":\"" + Digest(cls, title) + "\"}");
            return true;
        }, IntPtr.Zero);
        return "{\"complete\":" + (finished && !over ? "true" : "false")
            + ",\"process_start_ticks\":" + ticks
            + ",\"visible_set_digest\":\"" + SetDigest(target, limit) + "\""
            + ",\"windows\":[" + string.Join(",", rows) + "]}";
    }
    static string Refused(string reason) { return "{\"sent\":false,\"refusal\":\"" + reason + "\"}"; }
    public static string Close(uint target, long handle, string expected, string set, long ticks, int limit) {
        if (StartTicks(target) != ticks) { return Refused("process_changed"); }
        if (SetDigest(target, limit) != set) { return Refused("window_set_changed"); }
        var h = new IntPtr(handle);
        if (!IsWindow(h)) { return Refused("window_absent"); }
        uint owner;
        GetWindowThreadProcessId(h, out owner);
        if (owner != target) { return Refused("window_owner_changed"); }
        if (GetWindow(h, GW_OWNER) != IntPtr.Zero || !IsWindowVisible(h) || !IsWindowEnabled(h)) {
            return Refused("window_not_selectable");
        }
        if (Digest(ClassOf(h), TitleOf(h)) != expected) { return Refused("window_identity_changed"); }
        if (!PostMessage(h, WM_CLOSE, IntPtr.Zero, IntPtr.Zero)) { return Refused("close_not_posted"); }
        return "{\"sent\":true,\"refusal\":\"\"}";
    }
    // Kill through the very process object whose creation time was checked.
    public static string Terminate(uint target, string set, long ticks, int limit) {
        System.Diagnostics.Process p;
        try { p = System.Diagnostics.Process.GetProcessById((int)target); }
        catch (Exception) { return Refused("process_absent"); }
        using (p) {
            long started;
            try { started = p.StartTime.ToUniversalTime().Ticks; }
            catch (Exception) { return Refused("process_unreadable"); }
            if (started != ticks) { return Refused("process_changed"); }
            if (SetDigest(target, limit) != set) { return Refused("window_set_changed"); }
            try { p.Kill(); } catch (Exception) { return Refused("kill_failed"); }
            return "{\"sent\":true,\"refusal\":\"\"}";
        }
    }
}
'@
"""


def _window_row(pid: int, item: object) -> OwnedWindow:
    """Validate one census row; any deviation raises and fails the census."""
    if not isinstance(item, dict):
        raise ValueError("window row is not an object")
    integers = ("handle", "owner_pid", "owner_handle")
    if any(
        isinstance(item.get(name), bool) or not isinstance(item.get(name), int)
        for name in integers
    ):
        raise ValueError("window row integer is malformed")
    if item["handle"] <= 0 or item["owner_handle"] < 0:
        raise ValueError("window handle is malformed")
    if item["owner_pid"] != pid:
        raise LookupError("window attributed to another process")
    if not all(isinstance(item.get(name), str) for name in ("class_name", "title")):
        raise ValueError("window row text is malformed")
    if not all(isinstance(item.get(name), bool) for name in ("visible", "enabled")):
        raise ValueError("window row flag is malformed")
    digest = item.get("identity_digest")
    if not isinstance(digest, str) or digest != window_identity_digest(
        item["class_name"], item["title"]
    ):
        # A title that did not survive transport intact is not evidence.
        raise ValueError("window identity digest does not match its text")
    return OwnedWindow(
        handle=item["handle"],
        owner_pid=pid,
        class_name=item["class_name"],
        title=item["title"],
        visible=item["visible"],
        enabled=item["enabled"],
        owner_handle=item["owner_handle"],
        identity_digest=digest,
    )


def parse_window_census(pid: int, raw: str) -> OwnedWindowCensus:
    """Turn the helper's output into a census; anything doubtful is an error."""
    try:
        value = json.loads(raw)
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("complete"), bool)
            or not isinstance(value.get("windows"), list)
            or isinstance(value.get("process_start_ticks"), bool)
            or not isinstance(value.get("process_start_ticks"), int)
            or not isinstance(value.get("visible_set_digest"), str)
        ):
            raise ValueError("window census is malformed")
        windows = tuple(_window_row(pid, item) for item in value["windows"])
    except LookupError:
        return OwnedWindowCensus(pid, error="window_attribution_mismatch")
    except ValueError:
        return OwnedWindowCensus(pid, error="window_census_malformed")
    if len(windows) > WINDOW_CENSUS_LIMIT or len(
        {item.handle for item in windows}
    ) != len(windows):
        return OwnedWindowCensus(pid, error="window_census_malformed")
    if value["process_start_ticks"] <= 0:
        return OwnedWindowCensus(pid, error="window_census_process_unreadable")
    complete = value["complete"]
    if complete and value["visible_set_digest"] != visible_set_digest(windows):
        # The set the helper saw is not the set these rows describe.
        return OwnedWindowCensus(pid, error="window_census_malformed")
    return OwnedWindowCensus(
        pid,
        windows=windows,
        complete=complete,
        process_start_ticks=value["process_start_ticks"],
        visible_set_digest=value["visible_set_digest"] if complete else "",
    )


def _effect_answer(raw: str) -> tuple[bool, str] | None:
    """Return (sent, refusal) from an effect helper, or `None` if doubtful."""
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("sent"), bool)
        or not isinstance(value.get("refusal"), str)
        or value["sent"] == bool(value["refusal"])
    ):
        return None
    return value["sent"], value["refusal"]


def parse_window_close(pid: int, handle: int, raw: str) -> WindowCloseResult:
    """Turn the close helper's output into a result; doubt is an error."""
    answer = _effect_answer(raw)
    if answer is None:
        return WindowCloseResult(pid, handle, error="window_close_malformed")
    return WindowCloseResult(pid, handle, sent=answer[0], refusal=answer[1])


def parse_termination(pid: int, raw: str) -> TerminationResult:
    """Turn the termination helper's output into a result; doubt is an error."""
    answer = _effect_answer(raw)
    if answer is None:
        return TerminationResult(pid, error="termination_malformed")
    return TerminationResult(pid, sent=answer[0], refusal=answer[1])


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

    def _run_window_helper(self, call: str) -> str:
        """Run the constant helper plus one validated call, encoded whole."""
        script = _WINDOW_HELPER + call + "\n"
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        completed = self._run_command(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                encoded,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=self._timeout_seconds,
        )
        lines = str(getattr(completed, "stdout", "") or "").strip().splitlines()
        return lines[-1].strip() if lines else ""

    def windows(self, pid: int) -> OwnedWindowCensus:
        """Enumerate every top-level window this exact PID owns, bounded."""
        pid = _pid(pid)
        try:
            raw = self._run_window_helper(
                f"[PtMcpOwnedWindows]::Census({pid}, {WINDOW_CENSUS_LIMIT})"
            )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return OwnedWindowCensus(
                pid, error=f"window_census_unobservable:{type(exc).__name__}"
            )
        return parse_window_census(pid, raw)

    def close_window(
        self,
        pid: int,
        handle: int,
        digest: str,
        *,
        set_digest: str,
        start_ticks: int,
    ) -> WindowCloseResult:
        """Post `WM_CLOSE` to one handle only if nothing changed since the census.

        In the same helper call the process must still have the census's
        creation time, its visible windows must still be the census's set,
        and the handle must still exist, belong to the PID, be a visible,
        enabled, unowned top-level window and carry the selected identity
        digest. Nothing else is ever closed.
        """
        pid = _pid(pid)
        handle = _handle(handle)
        digest = _hex_digest(digest)
        set_digest = _hex_digest(set_digest)
        start_ticks = _ticks(start_ticks)
        try:
            raw = self._run_window_helper(
                f"[PtMcpOwnedWindows]::Close({pid}, {handle}, '{digest}', "
                f"'{set_digest}', {start_ticks}, {WINDOW_CENSUS_LIMIT})"
            )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return WindowCloseResult(
                pid, handle, error=f"window_close_unobservable:{type(exc).__name__}"
            )
        return parse_window_close(pid, handle, raw)

    def terminate(
        self, pid: int, *, set_digest: str, start_ticks: int
    ) -> TerminationResult:
        """Kill this PID only if it is still the census's process and window set.

        The helper opens the process, checks its creation time and the
        visible window set, and kills through that same process object, so
        a reused PID or a window that appeared since the census stops it.
        """
        pid = _pid(pid)
        set_digest = _hex_digest(set_digest)
        start_ticks = _ticks(start_ticks)
        try:
            raw = self._run_window_helper(
                f"[PtMcpOwnedWindows]::Terminate({pid}, '{set_digest}', "
                f"{start_ticks}, {WINDOW_CENSUS_LIMIT})"
            )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return TerminationResult(
                pid, error=f"termination_unobservable:{type(exc).__name__}"
            )
        return parse_termination(pid, raw)

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
