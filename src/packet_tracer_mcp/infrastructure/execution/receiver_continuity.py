"""Per-dispatch continuity of the one Packet Tracer receiver an attempt bound.

A governed attempt pairs one Packet Tracer incarnation before any transport
exists. Nothing keeps that process alive: a Packet Tracer that crashes and is
started again polls the same mailbox, and every command queued afterwards is
executed by a process the attempt never paired. So every governed dispatch
asks again, immediately before it is handed to the channel.

The portable answer is one full lifecycle reading per dispatch; it is correct
and costs what that reading costs (two PowerShell helpers). This module adds
the cheap answer, with the lifecycle reader's own observation shape so one
domain rule decides both. `HandleBoundReceiverContinuity` holds an
operating-system handle on the paired process. Windows does not reuse a process
id while a handle to that process is open, so the handle names one incarnation
for as long as it is held. The binding is confirmed by one more full reading
taken after the handle was opened; after that, each dispatch reads the handle
(not exited, same creation time, same image path) and the process table (no
Packet Tracer image other than the bound primary and the helper present at
binding). Each reading is fresh. Versions are properties of the bound image and
are carried from the confirmed pairing; no permission is cached.

Neither reader is an in-band fence. Between the reading and the receiver
executing the command the interval stays unfenced, and that is declared by
every envelope, not closed here. Neither reader contacts Packet Tracer,
starts, stops or signals a process, or touches the mailbox.
"""

from __future__ import annotations

import ctypes
import ntpath
import sys
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Protocol

from ...domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
)

#: Image-name prefix of every Packet Tracer process, primary or helper. The
#: lifecycle reader selects processes with the same prefix.
PACKET_TRACER_IMAGE_PREFIX = "packettracer"


@dataclass(frozen=True)
class ProcessTableRow:
    """One process-table entry, as the operating system listed it."""

    pid: int
    parent_pid: int
    image_name: str


class ProcessApi(Protocol):
    """The operating-system reads the handle-bound reader needs."""

    def open(self, pid: int) -> object | None:
        """Open a query/synchronize handle, or return None when refused."""

    def exited(self, handle: object) -> bool | None:
        """Return whether the process has exited, or None when unreadable."""

    def creation_time(self, handle: object) -> int | None:
        """Return the process creation time as an opaque integer."""

    def image_path(self, handle: object) -> str:
        """Return the full image path, or "" when unreadable."""

    def close(self, handle: object) -> None:
        """Close one handle; never raises."""

    def snapshot(self) -> list[ProcessTableRow] | None:
        """List the process table, or return None when it cannot be read."""


def _same_path(left: str, right: str) -> bool:
    return bool(left and right) and ntpath.normcase(
        ntpath.normpath(left)
    ) == ntpath.normcase(ntpath.normpath(right))


def _is_packet_tracer(row: ProcessTableRow) -> bool:
    return row.image_name.casefold().startswith(PACKET_TRACER_IMAGE_PREFIX)


class HandleBoundReceiverContinuity:
    """Answer each dispatch from a held handle and a fresh process table."""

    def __init__(
        self,
        preflight: DiagnosticLifecycleObservation,
        *,
        api: ProcessApi,
        handle: object,
        creation_time: int,
        helper_pid: int | None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        """Hold one confirmed binding; use `bind` to create one."""
        self._preflight = preflight
        self._api = api
        self._handle: object | None = handle
        self._creation_time = creation_time
        self._helper_pid = helper_pid
        self._clock = clock

    @classmethod
    def bind(
        cls,
        preflight: DiagnosticLifecycleObservation,
        deadline: float,
        *,
        lifecycle: Callable[[float | None], DiagnosticLifecycleObservation],
        api: ProcessApi | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> HandleBoundReceiverContinuity | None:
        """Bind the paired incarnation, or return None when it cannot.

        None tells the composition to fall back to one full lifecycle reading
        per dispatch, which is never a weaker check. It is returned whenever
        this process cannot hold a handle on the paired process, cannot read
        its creation time, image or process table, finds a cohort other than
        the primary and at most one helper it started, or the confirming
        reading does not show the same incarnation.
        """
        api = api if api is not None else windows_process_api()
        pid = preflight.process_id
        if api is None or preflight.error or not pid:
            return None
        handle = api.open(pid)
        if handle is None:
            return None
        try:
            created = api.creation_time(handle)
            path = api.image_path(handle)
            table = api.snapshot()
            if (
                created is None
                or not _same_path(path, preflight.process_path)
                or table is None
            ):
                raise LookupError("binding_unreadable")
            images = [row for row in table if _is_packet_tracer(row)]
            helpers = [
                row.pid for row in images if row.pid != pid and row.parent_pid == pid
            ]
            others = [
                row.pid for row in images if row.pid != pid and row.parent_pid != pid
            ]
            if pid not in {row.pid for row in images} or others or len(helpers) > 1:
                raise LookupError("binding_ambiguous")
            confirmed = lifecycle(deadline)
            if confirmed.error or _identity(confirmed) != _identity(preflight):
                raise LookupError("binding_not_confirmed")
            if api.exited(handle) is not False:
                raise LookupError("binding_exited")
        except LookupError:
            api.close(handle)
            return None
        return cls(
            preflight,
            api=api,
            handle=handle,
            creation_time=created,
            helper_pid=helpers[0] if helpers else None,
            clock=clock,
        )

    def observe(self, deadline: float) -> DiagnosticLifecycleObservation:
        """Return one fresh reading of the bound handle and the process table."""
        handle = self._handle
        if handle is None:
            return DiagnosticLifecycleObservation(error="receiver_binding_closed")
        exited = self._api.exited(handle)
        if exited is None:
            return DiagnosticLifecycleObservation(error="receiver_handle_unreadable")
        if exited:
            return DiagnosticLifecycleObservation(error="receiver_exited")
        created = self._api.creation_time(handle)
        path = self._api.image_path(handle)
        table = self._api.snapshot()
        if table is None:
            return DiagnosticLifecycleObservation(error="process_table_unreadable")
        pid = self._preflight.process_id
        images = [row for row in table if _is_packet_tracer(row)]
        allowed = {pid, self._helper_pid}
        foreign = [row for row in images if row.pid not in allowed]
        if pid not in {row.pid for row in images} or foreign:
            count = len([row for row in images if row.pid != self._helper_pid])
            return DiagnosticLifecycleObservation(
                error=f"packet_tracer_process_count:{count}"
            )
        if self._clock() > deadline:
            return DiagnosticLifecycleObservation(
                error="local_observation_deadline_exceeded:receiver"
            )
        # The paired spelling is kept only for the same image; any other path
        # is reported as read, so the identity comparison sees the change.
        same_image = _same_path(path, self._preflight.process_path)
        return DiagnosticLifecycleObservation(
            process_id=pid,
            process_path=self._preflight.process_path if same_image else path,
            product_version=self._preflight.product_version,
            file_version=self._preflight.file_version,
            process_incarnation=(
                self._preflight.process_incarnation
                if created == self._creation_time
                else ""
            ),
        )

    def close(self) -> None:
        """Close the held handle once."""
        handle, self._handle = self._handle, None
        if handle is not None:
            self._api.close(handle)


def _identity(observed: DiagnosticLifecycleObservation) -> tuple[object, ...]:
    return (
        observed.process_id,
        observed.process_path,
        observed.product_version,
        observed.file_version,
        observed.process_incarnation,
    )


# -- Windows implementation ------------------------------------------------------

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0x0
_WAIT_TIMEOUT = 0x102
_TH32CS_SNAPPROCESS = 0x2
_MAX_PATH = 260


class _FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


class _ProcessEntry32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_uint32),
        ("cntUsage", ctypes.c_uint32),
        ("th32ProcessID", ctypes.c_uint32),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", ctypes.c_uint32),
        ("cntThreads", ctypes.c_uint32),
        ("th32ParentProcessID", ctypes.c_uint32),
        ("pcPriClassBase", ctypes.c_int32),
        ("dwFlags", ctypes.c_uint32),
        ("szExeFile", ctypes.c_wchar * _MAX_PATH),
    ]


class WindowsProcessApi:
    """The Win32 reads the handle-bound reader needs, through `ctypes`."""

    def __init__(self) -> None:
        """Declare the exact signatures of the five kernel32 reads used."""
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32 = kernel32
        kernel32.OpenProcess.argtypes = (
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        )
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.GetProcessTimes.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(_FileTime),
            ctypes.POINTER(_FileTime),
            ctypes.POINTER(_FileTime),
            ctypes.POINTER(_FileTime),
        )
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.QueryFullProcessImageNameW.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        )
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessEntry32W),
        )
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessEntry32W),
        )
        kernel32.Process32NextW.restype = wintypes.BOOL
        self._invalid = ctypes.c_void_p(-1).value

    def open(self, pid: int) -> object | None:
        """Open a query/synchronize handle on one process id."""
        handle = self._kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION | _SYNCHRONIZE, False, int(pid)
        )
        return handle or None

    def exited(self, handle: object) -> bool | None:
        """Poll the handle without waiting."""
        state = self._kernel32.WaitForSingleObject(handle, 0)
        if state == _WAIT_TIMEOUT:
            return False
        if state == _WAIT_OBJECT_0:
            return True
        return None

    def creation_time(self, handle: object) -> int | None:
        """Return the creation FILETIME as one integer."""
        times = [_FileTime() for _ in range(4)]
        if not self._kernel32.GetProcessTimes(handle, *map(ctypes.byref, times)):
            return None
        return (times[0].high << 32) | times[0].low

    def image_path(self, handle: object) -> str:
        """Return the process image path in Win32 form."""
        from ctypes import wintypes

        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not self._kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            return ""
        return buffer.value

    def close(self, handle: object) -> None:
        """Close one handle; a failure to close is not an observation."""
        try:
            self._kernel32.CloseHandle(handle)
        except OSError:
            pass

    def snapshot(self) -> list[ProcessTableRow] | None:
        """List every process id, parent id and image name."""
        snapshot = self._kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if not snapshot or snapshot == self._invalid:
            return None
        rows: list[ProcessTableRow] = []
        try:
            entry = _ProcessEntry32W()
            entry.dwSize = ctypes.sizeof(_ProcessEntry32W)
            if not self._kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                return None
            while True:
                rows.append(
                    ProcessTableRow(
                        pid=int(entry.th32ProcessID),
                        parent_pid=int(entry.th32ParentProcessID),
                        image_name=str(entry.szExeFile),
                    )
                )
                if not self._kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
        finally:
            self._kernel32.CloseHandle(snapshot)
        return rows


def windows_process_api() -> WindowsProcessApi | None:
    """Return the Win32 reads on Windows, and None anywhere else."""
    if sys.platform != "win32":
        return None
    try:
        return WindowsProcessApi()
    except (OSError, AttributeError):
        return None
