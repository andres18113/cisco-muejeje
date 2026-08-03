"""Waiter de convergencia estable sin sleeps ni reloj reales."""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.infrastructure.execution.stable_convergence import (
    StableConvergenceStatus,
    StableConvergenceWaiter,
)


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _sequence(values):
    items = iter(values)
    return lambda: next(items)


def test_matching_but_changing_fingerprints_do_not_converge():
    time = FakeTime()
    waiter = StableConvergenceWaiter(
        _sequence([
            {"ready": True, "state": "a"},
            {"ready": True, "state": "b"},
            {"ready": True, "state": "a"},
            {"ready": True, "state": "a"},
        ]),
        lambda item: item["ready"],
        lambda item: item["state"],
        timeout_seconds=2.0,
        interval_seconds=0.1,
        stable_samples=2,
        clock=time.clock,
        sleeper=time.sleep,
    )

    result = waiter.wait()

    assert result.status is StableConvergenceStatus.CONVERGED
    assert result.attempts == 4
    assert result.stable_samples == 2
    assert result.last_fingerprint == "a"


def test_converges_only_after_requested_number_of_stable_samples():
    time = FakeTime()
    waiter = StableConvergenceWaiter(
        _sequence([
            {"ready": False, "state": "warming"},
            {"ready": True, "state": "full"},
            {"ready": True, "state": "full"},
            {"ready": True, "state": "full"},
        ]),
        lambda item: item["ready"],
        lambda item: item["state"],
        timeout_seconds=2.0,
        interval_seconds=0.25,
        stable_samples=3,
        clock=time.clock,
        sleeper=time.sleep,
    )

    result = waiter.wait()

    assert result.converged and not result.timed_out
    assert result.attempts == 4
    assert result.elapsed_ms == 750
    assert time.sleeps == [0.25, 0.25, 0.25]
    assert result.last_snapshot == {"ready": True, "state": "full"}


def test_timeout_is_distinct_and_keeps_only_last_snapshot():
    time = FakeTime()
    counter = {"value": 0}

    def inspect():
        counter["value"] += 1
        return {"ready": False, "attempt": counter["value"]}

    result = StableConvergenceWaiter(
        inspect,
        lambda item: item["ready"],
        lambda item: item["attempt"],
        timeout_seconds=1.0,
        interval_seconds=0.25,
        clock=time.clock,
        sleeper=time.sleep,
    ).wait()

    assert result.status is StableConvergenceStatus.TIMEOUT
    assert result.timed_out and not result.converged
    assert result.attempts == 5
    assert result.elapsed_ms == 1000
    assert result.last_snapshot == {"ready": False, "attempt": 5}
    assert result.stable_samples == 0


def test_sleep_is_capped_by_remaining_timeout():
    time = FakeTime()

    result = StableConvergenceWaiter(
        lambda: {"ready": False},
        lambda item: item["ready"],
        lambda _item: "unused",
        timeout_seconds=1.0,
        interval_seconds=0.6,
        clock=time.clock,
        sleeper=time.sleep,
    ).wait()

    assert result.timed_out
    assert result.elapsed_ms == 1000
    assert time.sleeps == [0.6, 0.4]


def test_inspection_exception_resets_streak_and_can_recover():
    time = FakeTime()
    values = iter((
        {"ready": True, "state": "full"},
        RuntimeError("temporary bridge failure"),
        {"ready": True, "state": "full"},
        {"ready": True, "state": "full"},
    ))

    def inspect():
        value = next(values)
        if isinstance(value, Exception):
            raise value
        return value

    result = StableConvergenceWaiter(
        inspect,
        lambda item: item["ready"],
        lambda item: item["state"],
        timeout_seconds=2.0,
        interval_seconds=0.1,
        clock=time.clock,
        sleeper=time.sleep,
    ).wait()

    assert result.converged
    assert result.attempts == 4
    assert result.inspection_errors == 1
    assert result.last_error == "temporary bridge failure"


@pytest.mark.parametrize(
    "overrides",
    (
        {"stable_samples": 1},
        {"stable_samples": 2.5},
        {"stable_samples": True},
        {"timeout_seconds": -1},
        {"interval_seconds": -0.1},
        {"max_attempts": 0},
        {"max_attempts": 1.5},
        {"max_attempts": True},
    ),
)
def test_invalid_waiter_budgets_are_rejected(overrides):
    with pytest.raises(ValueError):
        StableConvergenceWaiter(lambda: {}, lambda _item: True, lambda _item: 1, **overrides)


def test_max_attempts_is_independent_from_the_poll_interval_budget():
    time = FakeTime()
    snapshots = iter(("ready", "ready"))

    def inspect():
        time.now += 3.0
        return next(snapshots)

    result = StableConvergenceWaiter(
        inspect,
        lambda value: value == "ready",
        lambda value: value,
        timeout_seconds=12.0,
        interval_seconds=0.25,
        stable_samples=2,
        max_attempts=6,
        clock=time.clock,
        sleeper=time.sleep,
    ).wait()

    assert result.converged
    assert result.attempts == 2
    assert result.elapsed_ms == 6250


def test_max_attempts_stops_an_unstable_wait_without_an_extra_poll():
    calls: list[int] = []

    result = StableConvergenceWaiter(
        lambda: calls.append(len(calls)) or calls[-1],
        lambda _value: False,
        lambda value: value,
        timeout_seconds=60.0,
        interval_seconds=0,
        stable_samples=2,
        max_attempts=3,
    ).wait()

    assert result.timed_out
    assert result.attempts == 3
    assert len(calls) == 3
