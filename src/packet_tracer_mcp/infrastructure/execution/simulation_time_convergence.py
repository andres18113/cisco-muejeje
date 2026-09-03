"""Bounded convergence measured against Packet Tracer simulation time."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic, sleep

from ...domain.enterprise.models.configuration_runtime import (
    ConvergenceOutcome,
)
from .simulation_trace_runtime import SimulationStateObservation


Inspection = Callable[[], dict[str, object]]
SimulationStateObserver = Callable[[], SimulationStateObservation]


# PT 9.0.1.0858's retained, complete ``show spanning-tree`` output reports a
# 15 s Forward Delay.  The prior governed policy added 5 s of observation
# margin.  Those 20 s are now spent on PT's simulation clock.  The 45 s wall
# figure is an ADMISSION boundary, not an execution deadline: retained
# canonical runs measured 0.53 and 0.59 simulated seconds per wall second
# under load, so it lets the qualified target be reached at the slower
# measured rate while refusing to open further rounds after it.  Past the
# boundary no new round is started and nothing further is slept; a bounded
# read already in flight still returns on its own timeout, so total elapsed
# time can exceed 45 s.  Cancelling an in-flight read would need a
# cancellation contract the bridge does not offer.
QUALIFIED_PVST_FORWARD_DELAY_SECONDS = 15.0
PVST_FORWARD_DELAY_MARGIN_SECONDS = 5.0
PVST_SIMULATION_PROGRESS_WALL_CAP_SECONDS = 45.0


def pvst_learning_progress_target_ms(
    observed_forward_delay_seconds: object,
) -> float | None:
    """Return the qualified simulation-time budget, otherwise fail closed."""
    if (
        isinstance(observed_forward_delay_seconds, bool)
        or not isinstance(observed_forward_delay_seconds, (int, float))
        or not math.isfinite(float(observed_forward_delay_seconds))
        or float(observed_forward_delay_seconds)
        != QUALIFIED_PVST_FORWARD_DELAY_SECONDS
    ):
        return None
    return (
        QUALIFIED_PVST_FORWARD_DELAY_SECONDS
        + PVST_FORWARD_DELAY_MARGIN_SECONDS
    ) * 1000.0


#: Stop causes that mean the OBSERVER ran out of authority, not that the
#: network answered.  Each one leaves whatever sample was last retained
#: describing a round the observer could not complete, so none of them may
#: support a network verdict.  ``wall_clock_safety_cap`` is here deliberately:
#: it means the qualified simulation budget was NOT spent.
OBSERVER_INCOMPLETE_STOP_REASONS = frozenset({
    "simulation_clock_read_failed",
    "simulation_clock_unobservable",
    "simulation_clock_not_realtime",
    "simulation_clock_invalid",
    "simulation_clock_untyped",
    "simulation_clock_regressed",
    "wall_clock_safety_cap",
    "inspection_failed",
})

#: Stop causes where a fresh sample ended the authority, so the terminal state
#: is the answer.  ``not_authorized`` means no extension was ever granted and
#: the initial convergence's own terminal sample stands.
NETWORK_MEASURED_STOP_REASONS = frozenset({
    "simulation_progress_exhausted",
    "continuation_unauthorized",
    "not_authorized",
})


def classify_extension_stop_reason(stop_reason: object) -> ConvergenceOutcome:
    """Map one retained stop cause to what it may legitimately conclude.

    An unrecognised token fails closed as ``OBSERVER_INCOMPLETE``: a stop
    cause this classifier does not know is not a cause it may let speak for
    the network.  This must stay total -- it runs while a conclusion is
    being formed, so malformed evidence has to fail closed rather than
    raise past the caller.
    """
    if not isinstance(stop_reason, str):
        return ConvergenceOutcome.OBSERVER_INCOMPLETE
    if stop_reason == "converged":
        return ConvergenceOutcome.CONVERGED
    if stop_reason in NETWORK_MEASURED_STOP_REASONS:
        return ConvergenceOutcome.NETWORK_MEASURED
    return ConvergenceOutcome.OBSERVER_INCOMPLETE


@dataclass(frozen=True)
class SimulationTimeConvergenceResult:
    """Outcome and clock evidence for one bounded convergence authority."""

    converged: bool
    attempts: int
    elapsed_ms: int
    simulation_start_ms: float | None
    simulation_end_ms: float | None
    simulation_progress_ms: float
    required_simulation_progress_ms: float
    clock_samples: int
    stop_reason: str
    failure_reason: str = ""

    @property
    def configuration_channel(self) -> bool:
        return self.converged


def simulation_time_extension_evidence(
    result: SimulationTimeConvergenceResult | None,
    *,
    requested_progress_ms: float | None,
    max_wall_seconds: float = PVST_SIMULATION_PROGRESS_WALL_CAP_SECONDS,
) -> dict[str, object]:
    """Project one stable evidence shape for every convergence consumer."""
    authorized = bool(
        result is not None and result.simulation_start_ms is not None
    )
    stop_reason = (
        result.stop_reason if result is not None else "not_authorized"
    )
    return {
        "learning_extension_authorized": authorized,
        "learning_extension_seconds": (
            requested_progress_ms / 1000.0
            if requested_progress_ms is not None else 0.0
        ),
        "learning_extension_clock": (
            "packet_tracer_simulation_time" if authorized else "none"
        ),
        "learning_extension_max_wall_seconds": (
            max_wall_seconds
            if requested_progress_ms is not None else 0.0
        ),
        "learning_extension_simulation_start_ms": (
            result.simulation_start_ms if result is not None else None
        ),
        "learning_extension_simulation_end_ms": (
            result.simulation_end_ms if result is not None else None
        ),
        "learning_extension_simulation_progress_ms": (
            result.simulation_progress_ms if result is not None else 0.0
        ),
        "learning_extension_clock_samples": (
            result.clock_samples if result is not None else 0
        ),
        "learning_extension_sample_count": (
            result.attempts if result is not None else 0
        ),
        "learning_extension_stop_reason": stop_reason,
        "learning_extension_outcome": classify_extension_stop_reason(
            stop_reason,
        ).value,
        "learning_extension_failure_reason": (
            result.failure_reason if result is not None else ""
        ),
    }


class SimulationTimeConvergenceWaiter:
    """Poll a read-only state until it converges or one clock budget ends.

    Packet Tracer protocol timers advance in simulation time even in Realtime
    mode.  The protocol budget therefore comes from ``getCurrentSimTime()``;
    wall time only bounds how long this observer keeps ADMITTING rounds when
    the simulator is stalled or very slow.  Neither clock is a deadline that
    interrupts work already started: an inspection or a clock read in flight
    runs to its own bounded end, so ``elapsed_ms`` may exceed the wall cap by
    one such read.  What is guaranteed is that no round is opened and no
    sleep is taken past the boundary, and that neither an invalid clock nor
    an unauthorized terminal sample is retryable inside this authority.
    """

    def __init__(
        self,
        inspect: Inspection,
        *,
        observe_simulation_state: SimulationStateObserver,
        required_simulation_progress_ms: float,
        max_wall_seconds: float,
        interval_seconds: float = 0.25,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if required_simulation_progress_ms <= 0:
            raise ValueError("required simulation progress must be positive")
        if max_wall_seconds <= 0:
            raise ValueError("wall-clock safety cap must be positive")
        if interval_seconds < 0:
            raise ValueError("poll interval cannot be negative")
        self._inspect = inspect
        self._observe_simulation_state = observe_simulation_state
        self._required_progress_ms = float(required_simulation_progress_ms)
        self._max_wall_seconds = float(max_wall_seconds)
        self._interval_seconds = float(interval_seconds)
        self._clock = clock
        self._sleep = sleeper

    def wait(self) -> SimulationTimeConvergenceResult:
        started = self._clock()
        attempts = 0
        clock_samples = 0
        start_sim_time: float | None = None
        last_sim_time: float | None = None

        baseline, reason, detail = self._read_simulation_time()
        clock_samples += 1
        if baseline is None:
            return self._result(
                False, attempts, started, start_sim_time, last_sim_time,
                clock_samples, reason, detail,
            )
        start_sim_time = baseline
        last_sim_time = baseline

        while True:
            # Admission boundary: past it no further round is opened.  A
            # round already under way is not interrupted.
            if self._clock() - started >= self._max_wall_seconds:
                return self._result(
                    False, attempts, started, start_sim_time, last_sim_time,
                    clock_samples, "wall_clock_safety_cap",
                )

            current, reason, detail = self._read_simulation_time()
            clock_samples += 1
            if current is None:
                return self._result(
                    False, attempts, started, start_sim_time, last_sim_time,
                    clock_samples, reason, detail,
                )
            if current < last_sim_time:
                return self._result(
                    False, attempts, started, start_sim_time, current,
                    clock_samples, "simulation_clock_regressed",
                )
            last_sim_time = current

            attempts += 1
            try:
                observed = self._inspect()
            except Exception as exc:
                return self._result(
                    False, attempts, started, start_sim_time, last_sim_time,
                    clock_samples, "inspection_failed",
                    f"{type(exc).__name__}: {exc}",
                )
            if observed.get("configuration_channel") is True:
                return self._result(
                    True, attempts, started, start_sim_time, last_sim_time,
                    clock_samples, "converged",
                )
            if observed.get("continuation_authorized") is not True:
                return self._result(
                    False, attempts, started, start_sim_time, last_sim_time,
                    clock_samples, "continuation_unauthorized",
                    str(observed.get("failure_reason") or ""),
                )
            if current - start_sim_time >= self._required_progress_ms:
                return self._result(
                    False, attempts, started, start_sim_time, last_sim_time,
                    clock_samples, "simulation_progress_exhausted",
                    str(observed.get("failure_reason") or ""),
                )
            remaining_wall_seconds = max(
                0.0,
                self._max_wall_seconds - (self._clock() - started),
            )
            self._sleep(min(self._interval_seconds, remaining_wall_seconds))

    def _read_simulation_time(self) -> tuple[float | None, str, str]:
        """Return the clock, a stable stop token, and any raised detail."""
        try:
            observation = self._observe_simulation_state()
        except Exception as exc:
            return None, "simulation_clock_read_failed", (
                f"{type(exc).__name__}: {exc}"
            )
        if not isinstance(observation, SimulationStateObservation):
            return None, "simulation_clock_untyped", ""
        if not observation.observed:
            return None, "simulation_clock_unobservable", observation.message
        if observation.simulation_mode:
            return None, "simulation_clock_not_realtime", ""
        value = observation.sim_time
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            return None, "simulation_clock_invalid", ""
        return float(value), "", ""

    def _result(
        self,
        converged: bool,
        attempts: int,
        started: float,
        start_sim_time: float | None,
        end_sim_time: float | None,
        clock_samples: int,
        stop_reason: str,
        failure_reason: str = "",
    ) -> SimulationTimeConvergenceResult:
        progress = (
            max(0.0, end_sim_time - start_sim_time)
            if start_sim_time is not None and end_sim_time is not None
            else 0.0
        )
        return SimulationTimeConvergenceResult(
            converged=converged,
            attempts=attempts,
            elapsed_ms=int((self._clock() - started) * 1000),
            simulation_start_ms=start_sim_time,
            simulation_end_ms=end_sim_time,
            simulation_progress_ms=progress,
            required_simulation_progress_ms=self._required_progress_ms,
            clock_samples=clock_samples,
            stop_reason=stop_reason,
            failure_reason=failure_reason,
        )


@dataclass(frozen=True)
class BoundedPvstLearningExtension:
    """Grant at most ONE protocol-sized PVST learning extension.

    Trunk and Voice observe different surfaces, but the extension itself is
    one contract: a single LRN-only window spent on Packet Tracer's own
    simulation clock under a finite wall-clock admission boundary.  Owning
    that wiring here is what keeps the two callers from drifting apart --
    neither can quietly acquire a different clock, a different cap or a
    second window.
    """

    observe_simulation_state: SimulationStateObserver
    interval_seconds: float
    max_wall_seconds: float = PVST_SIMULATION_PROGRESS_WALL_CAP_SECONDS

    def grant(
        self,
        inspect: Inspection,
        *,
        required_simulation_progress_ms: float,
    ) -> SimulationTimeConvergenceResult:
        """Spend the single window; the caller decides it was earned."""
        return SimulationTimeConvergenceWaiter(
            inspect,
            observe_simulation_state=self.observe_simulation_state,
            required_simulation_progress_ms=required_simulation_progress_ms,
            max_wall_seconds=self.max_wall_seconds,
            interval_seconds=self.interval_seconds,
        ).wait()

    def evidence(
        self,
        result: SimulationTimeConvergenceResult | None,
        *,
        requested_progress_ms: float | None,
    ) -> dict[str, object]:
        """Project the outcome against the bounds this seam actually holds."""
        return simulation_time_extension_evidence(
            result,
            requested_progress_ms=requested_progress_ms,
            max_wall_seconds=self.max_wall_seconds,
        )
