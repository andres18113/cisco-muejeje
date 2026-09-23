"""The per-dispatch receiver reader: binding, detection, fallback and cost.

The handle-bound reader is driven through a fake process table for its
decisions, and the Win32 reads it relies on are exercised for real against
this Python process and a child it starts and stops. Packet Tracer is never
read, started or signalled.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from cold_http_acceptance_harness import PROCESS_PATH, paired_process

from packet_tracer_mcp.adapters.cli.cold_http_acceptance import (
    bind_production_receiver,
)
from packet_tracer_mcp.application.use_cases.accept_cold_http import (
    LifecycleReceiverContinuity,
)
from packet_tracer_mcp.domain.enterprise.models.cold_http_acceptance import (
    receiver_continuity_findings,
)
from packet_tracer_mcp.infrastructure.execution.receiver_continuity import (
    HandleBoundReceiverContinuity,
    ProcessTableRow,
    windows_process_api,
)

BUILD = "9.0.1.0858"
PRIMARY = 4242
HELPER = 5151


@dataclass(frozen=True)
class _Handle:
    """An opaque handle that remembers which process it was opened on."""

    pid: int


@dataclass
class FakeProcessApi:
    """A process table the test edits between readings.

    `exited_state`, `created` and `path` describe the paired primary; the
    helper keeps its own fixed identity, so a change to the primary never
    passes for a change to the helper.
    """

    rows: list[ProcessTableRow] = field(
        default_factory=lambda: [
            ProcessTableRow(PRIMARY, 1, "PacketTracer.exe"),
            ProcessTableRow(HELPER, PRIMARY, "PacketTracer.exe"),
            ProcessTableRow(77, 1, "explorer.exe"),
        ]
    )
    exited_state: bool | None = False
    created: int | None = 1234
    path: str = PROCESS_PATH
    table_readable: bool = True
    opened: list[int] = field(default_factory=list)
    closed: int = 0
    open_refused: bool = False

    def open(self, pid: int):
        """Hand out an opaque handle unless opening is refused."""
        if self.open_refused:
            return None
        self.opened.append(pid)
        return _Handle(pid)

    def exited(self, handle) -> bool | None:
        """Report the scripted exit state of the primary; the helper lives."""
        return self.exited_state if handle.pid == PRIMARY else False

    def creation_time(self, handle) -> int | None:
        """Report the scripted creation time of the primary."""
        return self.created if handle.pid == PRIMARY else 555

    def image_path(self, handle) -> str:
        """Report the scripted image path of the primary."""
        return self.path if handle.pid == PRIMARY else PROCESS_PATH

    def close(self, handle) -> None:
        """Count one closed handle."""
        self.closed += 1

    def snapshot(self):
        """List the scripted process table, or nothing when unreadable."""
        return list(self.rows) if self.table_readable else None


def _bind(api: FakeProcessApi, *, confirmed=None, clock=time.monotonic):
    readings = []

    def lifecycle(deadline):
        readings.append(deadline)
        return confirmed if confirmed is not None else paired_process()

    bound = HandleBoundReceiverContinuity.bind(
        paired_process(), 10.0**9, lifecycle=lifecycle, api=api, clock=clock
    )
    return bound, readings


def _judge(bound) -> tuple[str, ...]:
    return receiver_continuity_findings(BUILD, paired_process(), bound.observe(10.0**9))


def test_a_confirmed_binding_answers_as_the_paired_incarnation():
    """One confirming full reading binds; later readings need no other."""
    api = FakeProcessApi()
    bound, readings = _bind(api)

    assert isinstance(bound, HandleBoundReceiverContinuity)
    assert len(readings) == 1  # one confirming full reading, then none
    assert api.opened == [PRIMARY, HELPER]  # the helper is held too
    for _ in range(3):
        assert _judge(bound) == ()
    assert len(readings) == 1


@pytest.mark.parametrize(
    ("change", "finding"),
    [
        (lambda api: setattr(api, "exited_state", True), "receiver_exited"),
        (lambda api: setattr(api, "exited_state", None), "receiver_handle_unreadable"),
        (
            lambda api: api.rows.append(ProcessTableRow(999, 1, "PacketTracer.exe")),
            "packet_tracer_process_count:2",
        ),
        (
            lambda api: api.rows.append(
                ProcessTableRow(998, PRIMARY, "PacketTracer.exe")
            ),
            "packet_tracer_process_count:2",
        ),
        (lambda api: setattr(api, "table_readable", False), "process_table_unreadable"),
        (lambda api: setattr(api, "created", 999), "incarnation_unobserved"),
        (lambda api: setattr(api, "path", r"C:\Temp\PacketTracer.exe"), "changed"),
    ],
)
def test_every_change_of_receiver_is_a_finding(change, finding):
    """A replacement, a second receiver or an unreadable identity is never the same."""
    api = FakeProcessApi()
    bound, _ = _bind(api)

    change(api)

    found = _judge(bound)
    assert any(finding in item for item in found), found


def test_the_helper_leaving_is_not_a_new_receiver():
    """The progress helper exiting leaves the paired primary as it was."""
    api = FakeProcessApi()
    bound, _ = _bind(api)

    api.rows = [row for row in api.rows if row.pid != HELPER]

    assert _judge(bound) == ()


def test_a_reading_that_overruns_its_deadline_is_unobservable():
    """A late reading is unknown, never a match."""
    api = FakeProcessApi()
    now = {"t": 0.0}
    bound, _ = _bind(api, clock=lambda: now["t"])
    now["t"] = 50.0

    observed = bound.observe(10.0)

    assert observed.error == "local_observation_deadline_exceeded:receiver"


@pytest.mark.parametrize(
    "setup",
    [
        lambda api: setattr(api, "open_refused", True),
        lambda api: setattr(api, "created", None),
        lambda api: setattr(api, "path", r"C:\elsewhere\PacketTracer.exe"),
        lambda api: setattr(api, "table_readable", False),
        lambda api: api.rows.append(ProcessTableRow(999, 1, "PacketTracer.exe")),
        lambda api: api.rows.append(ProcessTableRow(998, PRIMARY, "PacketTracer.exe")),
        lambda api: setattr(api, "exited_state", True),
    ],
)
def test_an_unconfirmable_binding_is_declined_and_releases_its_handle(setup):
    """No binding means the full reading per dispatch, never a weaker check."""
    api = FakeProcessApi()
    setup(api)

    bound, _ = _bind(api)

    assert bound is None
    assert api.closed == len(api.opened)


def test_a_confirming_reading_of_another_incarnation_declines_the_binding():
    """A handle opened on a reused slot is never bound."""
    api = FakeProcessApi()

    bound, _ = _bind(
        api, confirmed=paired_process(process_incarnation="2026-09-22T10:00:00Z")
    )

    assert bound is None
    assert api.closed == len(api.opened) == 2


def test_close_releases_the_handle_once_and_later_readings_fail_closed():
    """Closing twice closes once; a closed binding authorizes nothing."""
    api = FakeProcessApi()
    bound, _ = _bind(api)

    bound.close()
    bound.close()

    assert api.closed == 2  # the primary and the helper, each once
    assert bound.observe(10.0**9).error == "receiver_binding_closed"


def test_the_production_composition_falls_back_to_full_readings(monkeypatch):
    """Where no handle can be held, every dispatch still gets a full reading."""
    from packet_tracer_mcp.infrastructure.execution import receiver_continuity

    monkeypatch.setattr(receiver_continuity, "windows_process_api", lambda: None)
    readings = []

    def lifecycle(deadline):
        readings.append(deadline)
        return paired_process()

    receiver = bind_production_receiver(paired_process(), 5.0, lifecycle=lifecycle)

    assert isinstance(receiver, LifecycleReceiverContinuity)
    receiver.observe(7.0)
    receiver.observe(8.0)
    assert readings == [7.0, 8.0]


# -- the Win32 reads themselves, against processes this test owns ---------------------


windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="the Win32 process reads exist only on Windows"
)


@windows_only
def test_the_win32_reads_describe_this_process():
    """Open, poll, time, image and table reads work on a live process."""
    api = windows_process_api()
    assert api is not None
    handle = api.open(os.getpid())
    try:
        assert handle is not None
        assert api.exited(handle) is False
        created = api.creation_time(handle)
        assert isinstance(created, int) and created > 0
        assert api.creation_time(handle) == created
        image = Path(api.image_path(handle))
        assert image.is_file() and image.suffix.casefold() == ".exe"
        rows = api.snapshot()
        mine = [row for row in rows if row.pid == os.getpid()]
        assert len(mine) == 1 and mine[0].image_name.casefold().endswith(".exe")
    finally:
        api.close(handle)


@windows_only
def test_the_win32_handle_sees_a_child_exit_and_keeps_its_identity():
    """Exit is seen through the handle, and the held identity survives it."""
    api = windows_process_api()
    child = subprocess.Popen(
        [
            getattr(sys, "_base_executable", sys.executable),
            "-c",
            "import time; time.sleep(60)",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    handle = api.open(child.pid)
    try:
        created = api.creation_time(handle)
        assert api.exited(handle) is False
        child.terminate()
        child.wait(timeout=30)
        assert api.exited(handle) is True
        # The held handle still names the same incarnation after exit.
        assert api.creation_time(handle) == created
    finally:
        api.close(handle)
        if child.poll() is None:
            child.kill()


@windows_only
def test_one_win32_reading_costs_milliseconds_not_a_powershell_launch():
    """The per-dispatch cost the feasibility arithmetic charges, measured here."""
    api = windows_process_api()
    handle = api.open(os.getpid())
    try:
        costs = []
        for _ in range(50):
            started = time.perf_counter()
            api.exited(handle)
            api.creation_time(handle)
            api.image_path(handle)
            api.snapshot()
            costs.append(time.perf_counter() - started)
    finally:
        api.close(handle)
    costs.sort()
    # Generous: the measured median on the delivery machine is about 5 ms.
    assert costs[len(costs) // 2] < 0.25


class PerProcessApi:
    """A process table whose handles keep naming the process they opened."""

    def __init__(self) -> None:
        """Start with the paired primary and its progress helper."""
        self.table: dict[int, dict] = {}
        self.closed: list[dict] = []
        self.spawn(PRIMARY, parent=1, created=100)
        self.spawn(HELPER, parent=PRIMARY, created=200)

    def spawn(self, pid: int, *, parent: int, created: int) -> None:
        """Put a live Packet Tracer image at `pid`; an old holder keeps its own."""
        self.table[pid] = {
            "pid": pid,
            "parent": parent,
            "created": created,
            "alive": True,
            "path": PROCESS_PATH,
        }

    def exit(self, pid: int) -> None:
        """End the process at `pid`; held handles see it exited."""
        self.table.pop(pid)["alive"] = False

    def open(self, pid: int):
        """Open a handle that keeps naming this very process."""
        return self.table.get(pid)

    def exited(self, handle) -> bool | None:
        """Report whether the held process ended."""
        return not handle["alive"]

    def creation_time(self, handle) -> int | None:
        """Report the held process's creation time."""
        return handle["created"]

    def image_path(self, handle) -> str:
        """Report the held process's image."""
        return handle["path"]

    def close(self, handle) -> None:
        """Remember the closed handle."""
        self.closed.append(handle)

    def snapshot(self):
        """List the live processes."""
        return [
            ProcessTableRow(item["pid"], item["parent"], "PacketTracer.exe")
            for item in self.table.values()
        ]


@pytest.mark.parametrize("parent", [1, PRIMARY])
def test_a_reused_helper_pid_is_never_the_bound_helper(parent: int):
    """The helper exits and another Packet Tracer takes its id: a new receiver."""
    api = PerProcessApi()
    bound = HandleBoundReceiverContinuity.bind(
        paired_process(), 10.0**9, lifecycle=lambda deadline: paired_process(), api=api
    )
    assert _judge(bound) == ()

    api.exit(HELPER)
    api.spawn(HELPER, parent=parent, created=999)

    found = _judge(bound)
    assert any("packet_tracer_process_count" in item for item in found), found


def test_the_helper_is_held_and_released_with_the_binding():
    """Both handles are held while bound and closed once."""
    api = PerProcessApi()
    bound = HandleBoundReceiverContinuity.bind(
        paired_process(), 10.0**9, lifecycle=lambda deadline: paired_process(), api=api
    )

    bound.close()

    assert sorted(item["pid"] for item in api.closed) == [PRIMARY, HELPER]
