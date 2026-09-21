"""The bounded ping's inspection schedule, driven by time rather than by reads.

R4: `interval = timeout / max_inspections` with an immediate first read placed
six inspections of a 30-second window at 0, 5, 10, 15, 20 and 25 seconds, so a
destination that published its statistics at 26 or 29 seconds was never read,
although both are inside the window the safe timeout exists to provide.

Every fake here releases its statistics at a wall-clock TIME. That distinction
is the whole point: a channel that answers after N reads cannot tell a schedule
that covers the window from one that closes an interval early, because both
take the same number of reads. Time can.

Nothing here observes Packet Tracer. The terminal is a scripted fake.
"""

from __future__ import annotations

import json
from itertools import pairwise

import pytest

from packet_tracer_mcp.infrastructure.execution.typed_ping import (
    SAFE_PING_TIMEOUT_S,
    TypedPingExecutor,
    inspection_schedule,
)

NEWLINE = chr(10)
PROMPT = "PC>"
TARGET = "198.18.140.1"
COMMAND = "ping " + TARGET
#: The echo alone: the command was dispatched and is still printing, which is
#: what every read before the statistics appear actually sees.
ECHOED = PROMPT + COMMAND + NEWLINE
INSPECTIONS = 6


def _statistics(received: int) -> str:
    return (
        ECHOED
        + f"Packets: Sent = 4, Received = {received}, Lost = {4 - received}"
        + NEWLINE
        + PROMPT
    )


class _Clock:
    """A monotonic clock that only moves when something spends time on it."""

    def __init__(self) -> None:
        """Start at zero."""
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        """Return the current time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Advance by the full requested wait."""
        self.slept.append(seconds)
        self.now += seconds


class _CappedClock(_Clock):
    """A clock whose sleeper cannot honour a wait longer than its cap.

    This is the ledger's own `capped_sleep`: a phase with less time left than
    the schedule asks for grants what remains and no more. It is the one real
    way a finite schedule can run out while the window is still open.
    """

    def __init__(self, cap: float) -> None:
        """Bind the largest wait this sleeper will ever perform."""
        super().__init__()
        self.cap = cap

    def sleep(self, seconds: float) -> None:
        """Advance by the capped wait."""
        self.slept.append(seconds)
        self.now += min(seconds, self.cap)


class _TimedTerminal:
    """A terminal that publishes its statistics at a time, not after N reads.

    `publishes_at` is `None` for output that never completes. `latency` is the
    wall clock each channel call costs; a sequence gives a different cost to
    each call, which is how a schedule of absolute slots is distinguished from
    a schedule of delays between reads.
    """

    def __init__(
        self,
        clock: _Clock,
        *,
        publishes_at: float | None,
        received: int = 4,
        latency: float | list[float] = 0.0,
    ) -> None:
        """Script one terminal against one clock."""
        self.clock = clock
        self.publishes_at = publishes_at
        self.received = received
        self._latency = latency
        self._sequence = iter(latency) if isinstance(latency, list) else None
        self.dispatched_at: float | None = None
        self.reads: list[float] = []
        self.attributions: list[float] = []
        self.scripts: list[str] = []

    @property
    def calls(self) -> int:
        """Return every channel call this terminal answered."""
        return len(self.scripts)

    def _spend(self) -> None:
        if self._sequence is not None:
            self.clock.now += next(self._sequence, 0.0)
        else:
            self.clock.now += float(self._latency)

    def _output(self) -> str:
        if self.publishes_at is None or self.clock() < self.publishes_at:
            return ECHOED
        return _statistics(self.received)

    def __call__(self, script: str, _timeout: float) -> str:
        """Answer one script the way the engine would, and charge its time."""
        self.scripts.append(script)
        if "enterCommand" in script:
            self.dispatched_at = self.clock()
            self._spend()
            return json.dumps({"started": True, "before": PROMPT})
        if "found:!!t" in script:
            self.reads.append(self.clock())
            self._spend()
            return json.dumps({"found": True, "output": self._output()})
        self.attributions.append(self.clock())
        self._spend()
        return json.dumps({"found": True, "output": self._output()})


def _offsets(terminal: _TimedTerminal) -> list[float]:
    """Return each read time as an offset from the poll's own origin.

    The window is measured from the moment the dispatch returned, so the
    schedule is checked against that origin rather than against zero.
    """
    origin = terminal.reads[0]
    return [round(item - origin, 6) for item in terminal.reads]


def _ping(terminal: _TimedTerminal, clock: _Clock, **overrides):
    """Run one bounded ping over the scripted terminal and its clock."""
    values = {
        "timeout_seconds": SAFE_PING_TIMEOUT_S,
        "measurement_attempts": 1,
        "max_inspections": INSPECTIONS,
        "clock": clock,
        "sleeper": clock.sleep,
    }
    values.update(overrides)
    return TypedPingExecutor(terminal, **values).ping("PC0", TARGET)


# -- the schedule itself ---------------------------------------------------------


def test_the_schedule_is_the_endpoints_of_the_closed_window():
    """Six slots over 30 seconds are 0, 6, 12, 18, 24 and 30, not 0 to 25."""
    assert inspection_schedule(30.0, 6) == (0.0, 6.0, 12.0, 18.0, 24.0, 30.0)
    assert inspection_schedule(30.0, 2) == (0.0, 30.0)


@pytest.mark.parametrize("inspections", [1, 2, 3, 6, 7, 40])
def test_every_schedule_starts_no_later_than_it_ends_on_the_deadline(inspections):
    """Whatever the count, the last slot IS the deadline and none passes it."""
    schedule = inspection_schedule(SAFE_PING_TIMEOUT_S, inspections)

    assert len(schedule) == inspections
    assert schedule[-1] == SAFE_PING_TIMEOUT_S
    assert list(schedule) == sorted(schedule)
    assert all(0.0 <= item <= SAFE_PING_TIMEOUT_S for item in schedule)


def test_one_inspection_is_taken_at_the_deadline_and_divides_by_nothing():
    """A lone read cannot be immediate and cover the window; the window wins."""
    assert inspection_schedule(SAFE_PING_TIMEOUT_S, 1) == (SAFE_PING_TIMEOUT_S,)
    assert inspection_schedule(0.0, 1) == (0.0,)
    # The degenerate window is built without the partition, so no division by
    # `inspections - 1` can be reached with a zero denominator.
    assert inspection_schedule(0.0, 6) == (0.0,) * 6


# -- statistics inside the window ------------------------------------------------


@pytest.mark.parametrize("published", [26.0, 29.0, 29.999])
def test_statistics_late_in_the_window_are_observed(published):
    """R4: 26 s and 29 s are inside the promised window, and now they are read."""
    clock = _Clock()
    terminal = _TimedTerminal(clock, publishes_at=published)

    result = _ping(terminal, clock)

    assert result.fresh_output_observed is True
    assert result.reachable is True
    assert result.statistics.startswith("Packets: Sent = 4, Received = 4")
    # The reads are the schedule, and the last one lands on the deadline.
    assert terminal.reads == [0.0, 6.0, 12.0, 18.0, 24.0, 30.0]
    assert terminal.reads[-1] == SAFE_PING_TIMEOUT_S
    # One dispatch, six inspections, one attribution: the composed budget.
    assert terminal.calls == 1 + INSPECTIONS + 1
    assert len(terminal.attributions) == 1
    assert terminal.dispatched_at == 0.0


@pytest.mark.parametrize("published", [26.0, 29.0])
def test_an_unreachable_result_late_in_the_window_is_classified(published):
    """An unreachable destination measured late is a measurement, not an absence."""
    clock = _Clock()
    terminal = _TimedTerminal(clock, publishes_at=published, received=0)

    result = _ping(terminal, clock)

    assert result.fresh_output_observed is True
    assert result.reachable is False
    assert result.statistics.startswith("Packets: Sent = 4, Received = 0")
    assert result.failure_reason == ""
    assert terminal.reads[-1] == SAFE_PING_TIMEOUT_S


def test_the_old_schedule_would_have_missed_these():
    """The control: the previous last read was 25 s, and 26 s is after it."""
    # `timeout / max_inspections` with an immediate first read, which is what
    # this correction replaced. It is computed here, not imported, precisely
    # because no production path may produce it any more.
    superseded = [index * (SAFE_PING_TIMEOUT_S / INSPECTIONS) for index in range(6)]

    assert superseded[-1] == 25.0
    assert max(superseded) < 26.0
    assert inspection_schedule(SAFE_PING_TIMEOUT_S, INSPECTIONS)[-1] == 30.0


# -- output that never completes -------------------------------------------------


def test_output_that_never_completes_ends_on_the_window():
    """Nothing published means the window closed, not that the cap ran out."""
    clock = _Clock()
    terminal = _TimedTerminal(clock, publishes_at=None)

    result = _ping(terminal, clock)

    assert result.fresh_output_observed is False
    assert result.reachable is False
    # The sample is incomplete and names the bound that ended it: the whole
    # promised window elapsed, which is not the same claim as an unreachable
    # destination and is not the inspection cap closing early either.
    assert result.failure_reason == "no_fresh_ping_result"
    assert terminal.reads == [0.0, 6.0, 12.0, 18.0, 24.0, 30.0]
    assert terminal.calls == 1 + INSPECTIONS + 1


def test_a_sleeper_that_cannot_honour_the_schedule_reports_the_inspection_bound():
    """The one real case where the schedule, not the window, ends the sample."""
    clock = _CappedClock(cap=2.0)
    terminal = _TimedTerminal(clock, publishes_at=None)

    result = _ping(terminal, clock)

    # Every wait was cut to the cap, so the six reads were spent long before
    # the deadline. That is a bounded-incomplete sample with its own cause.
    assert terminal.reads == [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]
    assert clock.now < SAFE_PING_TIMEOUT_S
    assert result.failure_reason == "ping_inspection_budget_exhausted"
    assert result.reachable is False
    assert result.fresh_output_observed is False


# -- elapsed I/O -----------------------------------------------------------------


def test_the_window_is_measured_from_the_dispatch_returning():
    """The promised window starts when the command is in, not before it."""
    clock = _Clock()
    terminal = _TimedTerminal(clock, publishes_at=None, latency=0.4)

    _ping(terminal, clock)

    # The dispatch was entered at 0 and cost 0.4 s, so the poll's origin is
    # 0.4 and its last slot is 0.4 + 30. The window is never shortened by the
    # time it took to get the command in.
    assert terminal.dispatched_at == 0.0
    assert terminal.reads[0] == 0.4
    assert terminal.reads[-1] == 0.4 + SAFE_PING_TIMEOUT_S


def test_nonzero_io_latency_does_not_push_the_schedule_past_the_deadline():
    """Slots are absolute times, so the cost of a read is elapsed window."""
    clock = _Clock()
    terminal = _TimedTerminal(clock, publishes_at=None, latency=0.4)

    _ping(terminal, clock)

    # Each read STARTS on its slot: the 0.4 s it costs comes out of the wait
    # to the next one instead of being added on top of it.
    assert _offsets(terminal) == [0.0, 6.0, 12.0, 18.0, 24.0, 30.0]
    assert all(item <= SAFE_PING_TIMEOUT_S for item in _offsets(terminal))


def test_variable_io_latency_neither_bursts_nor_overruns():
    """Different costs per call still land the reads on the same slots."""
    clock = _Clock()
    # The dispatch, then a slow read, a fast one, a slow one, and so on.
    terminal = _TimedTerminal(
        clock, publishes_at=None, latency=[0.5, 3.0, 0.1, 2.5, 0.2, 1.0, 0.3, 0.4]
    )

    _ping(terminal, clock)

    # Every read is still on its own slot rather than one latency behind, and
    # the last one is still the deadline.
    assert _offsets(terminal) == [0.0, 6.0, 12.0, 18.0, 24.0, 30.0]
    gaps = [b - a for a, b in pairwise(terminal.reads)]
    assert all(gap > 1.0 for gap in gaps), "no two reads may collapse into a burst"


def test_a_missed_slot_is_skipped_and_never_batched():
    """A read slower than its interval loses slots; it does not catch up."""
    clock = _Clock()
    terminal = _TimedTerminal(clock, publishes_at=None, latency=7.0)

    result = _ping(terminal, clock)

    # Slot 0 ends at +7, so the 6 s slot is gone; slot 12 ends at +19, so 18
    # is gone; slot 24 ends at +31, which is past the deadline.
    assert _offsets(terminal) == [0.0, 12.0, 24.0]
    gaps = [b - a for a, b in pairwise(terminal.reads)]
    assert all(gap >= 6.0 for gap in gaps), "missed slots are skipped, not batched"
    # Fewer reads than the cap allows, and the window is still what ended it.
    assert len(terminal.reads) < INSPECTIONS
    assert result.failure_reason == "no_fresh_ping_result"


# -- one inspection, and the unbounded default ------------------------------------


def test_a_single_inspection_reads_at_the_deadline():
    """One read cannot be immediate and cover the window, so it covers it."""
    clock = _Clock()
    terminal = _TimedTerminal(clock, publishes_at=29.0)

    result = _ping(terminal, clock, max_inspections=1)

    assert terminal.reads == [SAFE_PING_TIMEOUT_S]
    assert result.fresh_output_observed is True
    assert result.reachable is True
    assert terminal.calls == 1 + 1 + 1


def test_the_unbounded_default_is_unchanged():
    """Every existing caller keeps the caller's own interval and no schedule."""
    clock = _Clock()
    terminal = _TimedTerminal(clock, publishes_at=None)

    result = TypedPingExecutor(
        terminal,
        timeout_seconds=1.0,
        interval_seconds=0.25,
        measurement_attempts=1,
        clock=clock,
        sleeper=clock.sleep,
    ).ping("PC0", TARGET)

    assert terminal.reads == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert clock.slept == [0.25, 0.25, 0.25, 0.25]
    assert result.failure_reason == "no_fresh_ping_result"


def test_the_unbounded_default_still_stops_on_the_first_complete_read():
    """An answered ping is returned immediately, bounded or not."""
    clock = _Clock()
    terminal = _TimedTerminal(clock, publishes_at=0.0)

    result = TypedPingExecutor(
        terminal,
        timeout_seconds=SAFE_PING_TIMEOUT_S,
        measurement_attempts=1,
        clock=clock,
        sleeper=clock.sleep,
    ).ping("PC0", TARGET)

    assert terminal.reads == [0.0]
    assert result.reachable is True
    assert clock.slept == []


@pytest.mark.parametrize("value", [0, -1, 1.5, True])
def test_a_non_positive_inspection_bound_is_rejected(value):
    """The bound is a positive whole number of reads or it is absent."""
    with pytest.raises(ValueError):
        TypedPingExecutor(lambda _s, _t: None, max_inspections=value)
