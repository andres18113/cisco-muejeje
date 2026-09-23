"""The shipped Win32 census refuses incomplete tables in the governed route."""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path

import pytest
from cold_http_acceptance_harness import (
    ATTEMPT,
    PROCESS_ID,
    PROCESS_PATH,
    build_harness,
    paired_process,
)

from packet_tracer_mcp.adapters.cli.cold_http_acceptance import (
    bind_production_receiver,
)
from packet_tracer_mcp.application.use_cases.accept_cold_http import (
    LifecycleReceiverContinuity,
)
from packet_tracer_mcp.infrastructure.execution import receiver_continuity
from packet_tracer_mcp.infrastructure.execution.receiver_continuity import (
    HandleBoundReceiverContinuity,
    ProcessTableRow,
    ReceiverBindingDeclined,
    WindowsProcessApi,
)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Win32 ctypes only")

PRIMARY = (PROCESS_ID, 1, "PacketTracer.exe")
OTHER = (77, 1, "explorer.exe")
SECOND_RECEIVER = (9999, 1, "PacketTracer.exe")


@dataclass
class Kernel32:
    """Provide Win32 return values while the shipped adapter owns enumeration."""

    rows: list[tuple[int, int, str]] = field(default_factory=lambda: [PRIMARY, OTHER])
    failure_rows: list[tuple[int, int, str]] | None = None
    fail_snapshot: int | None = None
    fail_after_rows: int | None = None
    failure_error: int = 31
    first_error: int | None = None
    snapshot_error: int | None = None
    zero_snapshot: bool = False
    closed_snapshots: list[int] = field(default_factory=list)
    closed_processes: list[int] = field(default_factory=list)
    snapshot_calls: int = 0
    _cursor: int = 0
    _active_rows: list[tuple[int, int, str]] = field(default_factory=list)
    _active_failure: bool = False

    def CreateToolhelp32Snapshot(self, flags: int, pid: int) -> int:
        """Return one fake snapshot handle or a chosen creation failure."""
        assert flags == 2 and pid == 0
        self.snapshot_calls += 1
        if self.snapshot_error is not None:
            ctypes.set_last_error(self.snapshot_error)
            return 0 if self.zero_snapshot else ctypes.c_void_p(-1).value
        self._active_failure = self.fail_after_rows is not None and (
            self.fail_snapshot is None or self.snapshot_calls == self.fail_snapshot
        )
        self._active_rows = (
            self.failure_rows
            if self._active_failure and self.failure_rows is not None
            else self.rows
        )
        self._cursor = 0
        return 1234

    def Process32FirstW(self, handle: int, entry: object) -> bool:
        """Copy the first row or report a scripted first-read error."""
        assert handle == 1234
        if self.first_error is not None or not self._active_rows:
            ctypes.set_last_error(
                self.first_error if self.first_error is not None else 18
            )
            return False
        self._fill(entry, self._active_rows[0])
        ctypes.set_last_error(77)
        return True

    def Process32NextW(self, handle: int, entry: object) -> bool:
        """Copy the next row, terminate, or fail at the scripted row."""
        assert handle == 1234
        if self._active_failure and self._cursor + 1 == self.fail_after_rows:
            if self.failure_error:
                ctypes.set_last_error(self.failure_error)
            return False
        self._cursor += 1
        if self._cursor == len(self._active_rows):
            ctypes.set_last_error(18)
            return False
        self._fill(entry, self._active_rows[self._cursor])
        ctypes.set_last_error(77)
        return True

    def CloseHandle(self, handle: int) -> bool:
        """Track snapshot and process cleanup and replace last error."""
        if handle == 1234:
            self.closed_snapshots.append(handle)
        else:
            self.closed_processes.append(handle)
        ctypes.set_last_error(99)
        return True

    def OpenProcess(self, access: int, inherit: bool, pid: int) -> int:
        """Return a query handle for the paired primary only."""
        assert access == 0x101000 and inherit is False and pid == PROCESS_ID
        return 10000 + pid

    def WaitForSingleObject(self, handle: int, timeout: int) -> int:
        """Keep the paired process alive for the entire fake run."""
        assert handle == 10000 + PROCESS_ID and timeout == 0
        return 0x102

    def GetProcessTimes(self, handle: int, creation: object, *other: object) -> bool:
        """Write a stable creation FILETIME behind the ctypes pointer."""
        assert handle == 10000 + PROCESS_ID and len(other) == 3
        creation._obj.low = 1234
        creation._obj.high = 0
        return True

    def QueryFullProcessImageNameW(
        self, handle: int, flags: int, buffer: object, size: object
    ) -> bool:
        """Write the paired image path into the supplied Unicode buffer."""
        assert handle == 10000 + PROCESS_ID and flags == 0
        buffer.value = PROCESS_PATH
        size._obj.value = len(PROCESS_PATH)
        return True

    @staticmethod
    def _fill(entry: object, row: tuple[int, int, str]) -> None:
        entry._obj.th32ProcessID = row[0]
        entry._obj.th32ParentProcessID = row[1]
        entry._obj.szExeFile = row[2]


def _api(kernel: Kernel32) -> WindowsProcessApi:
    api = WindowsProcessApi()
    api._kernel32 = kernel
    return api


def _unreadable(api: WindowsProcessApi, cause: str, rows_read: int) -> None:
    with pytest.raises(OSError) as raised:
        api.snapshot()
    assert raised.value.cause == cause
    assert raised.value.rows_read == rows_read


def test_documented_end_returns_every_row_and_closes_once() -> None:
    """Only error 18 after the last row completes a full table."""
    kernel = Kernel32(rows=[PRIMARY, OTHER, SECOND_RECEIVER])

    assert _api(kernel).snapshot() == [
        ProcessTableRow(*PRIMARY),
        ProcessTableRow(*OTHER),
        ProcessTableRow(*SECOND_RECEIVER),
    ]
    assert kernel.closed_snapshots == [1234]


@pytest.mark.parametrize("error", [0, 5, 18])
def test_first_read_failure_is_unreadable_even_for_no_more_files(error: int) -> None:
    """A failed first read never establishes a complete census."""
    kernel = Kernel32(rows=[], first_error=error)

    _unreadable(_api(kernel), f"process32first_failed:winerror={error}", 0)
    assert kernel.closed_snapshots == [1234]


def test_failure_after_primary_reports_one_row_and_closes_once() -> None:
    """A partial table carries its diagnostic count but grants nothing."""
    kernel = Kernel32(rows=[PRIMARY, OTHER], fail_after_rows=1)

    _unreadable(_api(kernel), "process32next_failed:winerror=31:rows=1", 1)
    assert kernel.closed_snapshots == [1234]


def test_failure_before_second_receiver_declines_bind_and_observe() -> None:
    """A hidden second receiver cannot become a single-receiver reading."""
    kernel = Kernel32(rows=[PRIMARY, OTHER, SECOND_RECEIVER], fail_after_rows=2)
    api = _api(kernel)

    with pytest.raises(ReceiverBindingDeclined) as raised:
        HandleBoundReceiverContinuity.bind(
            paired_process(),
            10**9,
            lifecycle=lambda deadline: paired_process(),
            api=api,
        )
    assert raised.value.reason == (
        "process_table_unreadable:process32next_failed:winerror=31:rows=2"
    )
    assert kernel.closed_processes == [10000 + PROCESS_ID]

    kernel.failure_rows = [PRIMARY, OTHER, SECOND_RECEIVER]
    kernel.rows = [PRIMARY, OTHER]
    kernel.fail_snapshot = 2
    kernel.snapshot_calls = 0
    kernel.closed_processes.clear()
    bound = HandleBoundReceiverContinuity.bind(
        paired_process(), 10**9, lifecycle=lambda deadline: paired_process(), api=api
    )
    try:
        assert bound.observe(10**9).error == (
            "process_table_unreadable:process32next_failed:winerror=31:rows=2"
        )
    finally:
        bound.close()
    assert kernel.closed_snapshots == [1234, 1234, 1234]
    assert kernel.closed_processes == [10000 + PROCESS_ID]


def test_false_next_without_error_is_unreadable() -> None:
    """Clearing stale last error makes an unexplained false return fail."""
    kernel = Kernel32(rows=[PRIMARY], fail_after_rows=1, failure_error=0)

    _unreadable(_api(kernel), "process32next_failed:winerror=0:rows=1", 1)
    assert kernel.closed_snapshots == [1234]


def test_next_error_is_captured_before_close_replaces_it() -> None:
    """Cleanup cannot replace the enumeration error in the cause."""
    kernel = Kernel32(rows=[PRIMARY], fail_after_rows=1, failure_error=31)

    _unreadable(_api(kernel), "process32next_failed:winerror=31:rows=1", 1)
    assert ctypes.get_last_error() == 99
    assert kernel.closed_snapshots == [1234]


@pytest.mark.parametrize("error,zero_handle", [(5, False), (18, False), (31, True)])
def test_invalid_snapshot_has_no_handle_to_close(error: int, zero_handle: bool) -> None:
    """An invalid or zero snapshot is unreadable without cleanup."""
    kernel = Kernel32(snapshot_error=error, zero_snapshot=zero_handle)

    _unreadable(_api(kernel), f"toolhelp_snapshot_failed:winerror={error}", 0)
    assert kernel.closed_snapshots == []


def _route_binding(harness: object, api: WindowsProcessApi):
    """Bind as `bind_production_receiver` does, on the harness's fake clock.

    The production composition reads the receiver against the monotonic clock
    its coordinator also uses; the harness's coordinator runs on a fake clock,
    so the per-dispatch deadline is only comparable when the reader shares it.
    """

    def bind(preflight, deadline):
        try:
            return HandleBoundReceiverContinuity.bind(
                preflight,
                deadline,
                lifecycle=harness.boundaries.lifecycle,
                api=api,
                clock=harness.clock,
            )
        except ReceiverBindingDeclined as declined:
            return LifecycleReceiverContinuity(
                harness.boundaries.lifecycle, declined=declined.reason
            )

    harness.boundaries = replace(harness.boundaries, bind_receiver=bind)


def test_governed_route_refuses_binding_failure_before_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The production composition records the cause and opens no channel."""
    kernel = Kernel32(
        failure_rows=[PRIMARY, OTHER, SECOND_RECEIVER],
        fail_snapshot=1,
        fail_after_rows=2,
    )
    monkeypatch.setattr(
        receiver_continuity, "windows_process_api", lambda: _api(kernel)
    )
    harness = build_harness(tmp_path)
    harness.boundaries = replace(
        harness.boundaries,
        bind_receiver=partial(
            bind_production_receiver, lifecycle=harness.boundaries.lifecycle
        ),
    )

    result = harness.run()
    envelope = result.envelope

    assert harness.opened_channels == []
    assert harness.terminal.log == []
    assert envelope.process_preflight["receiver_binding_declined"] == (
        "process_table_unreadable:process32next_failed:winerror=31:rows=2"
    )
    assert (
        "receiver_mode_not_bounded:lifecycle_per_dispatch:"
        "process_table_unreadable:process32next_failed:winerror=31:rows=2"
    ) in envelope.primary_failure
    assert envelope.completed_at is not None
    assert envelope.http_accepted is False
    assert result.persisted is True
    assert harness.envelope_store.load(ATTEMPT).primary_failure == (
        envelope.primary_failure
    )


def test_governed_route_stops_at_failed_dispatch_and_owned_releases(
    tmp_path: Path,
) -> None:
    """A failed later census blocks the request and owned cleanup dispatch."""
    kernel = Kernel32(
        failure_rows=[PRIMARY, OTHER, SECOND_RECEIVER],
        fail_snapshot=27,
        fail_after_rows=2,
    )
    harness = build_harness(tmp_path)
    _route_binding(harness, _api(kernel))

    result = harness.run()
    envelope = result.envelope

    assert len(harness.terminal.log) == 25
    assert harness.product_dispatches()[-1] == "http_start"
    assert "http_release" not in harness.product_dispatches()
    assert harness.terminal.owned_clients
    assert kernel.snapshot_calls >= 27
    assert envelope.primary_failure.startswith(
        "authority_lost:process_instance:unobservable:"
        "process_table_unreadable:process32next_failed"
    )
    assert envelope.completed_at is not None
    assert envelope.http_accepted is False
    assert result.persisted is True
    assert harness.envelope_store.load(ATTEMPT).primary_failure == (
        envelope.primary_failure
    )
