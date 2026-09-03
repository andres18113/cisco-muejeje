"""Bounded convergence against Packet Tracer's own Realtime simulation clock."""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ConvergenceOutcome,
)
from src.packet_tracer_mcp.infrastructure.execution.simulation_time_convergence import (
    OBSERVER_INCOMPLETE_STOP_REASONS,
    PVST_SIMULATION_PROGRESS_WALL_CAP_SECONDS,
    BoundedPvstLearningExtension,
    SimulationTimeConvergenceWaiter,
    classify_extension_stop_reason,
    pvst_learning_progress_target_ms,
)
from src.packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (
    SimulationStateObservation,
)


class _WallClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _simulation_clock(*sim_times: float, observed: bool = True, realtime: bool = True):
    values = iter(sim_times)

    def observe() -> SimulationStateObservation:
        return SimulationStateObservation(
            observed=observed,
            simulation_mode=not realtime,
            sim_time=next(values),
        )

    return observe


def test_slower_simulation_progress_can_reach_forwarding_within_the_wall_cap():
    wall = _WallClock()
    samples = iter((False, False, True))
    waiter = SimulationTimeConvergenceWaiter(
        lambda: {
            "configuration_channel": next(samples),
            "continuation_authorized": True,
        },
        observe_simulation_state=_simulation_clock(0, 0, 10_000, 20_000),
        required_simulation_progress_ms=20_000,
        max_wall_seconds=45.0,
        interval_seconds=20.0,
        clock=wall,
        sleeper=wall.sleep,
    )

    result = waiter.wait()

    assert result.converged is True
    assert result.attempts == 3
    assert result.elapsed_ms == 40_000
    assert result.simulation_progress_ms == 20_000
    assert result.stop_reason == "converged"


def test_full_simulated_window_still_learning_fails_closed():
    wall = _WallClock()
    waiter = SimulationTimeConvergenceWaiter(
        lambda: {
            "configuration_channel": False,
            "continuation_authorized": True,
        },
        observe_simulation_state=_simulation_clock(100, 100, 20_100),
        required_simulation_progress_ms=20_000,
        max_wall_seconds=45.0,
        interval_seconds=1.0,
        clock=wall,
        sleeper=wall.sleep,
    )

    result = waiter.wait()

    assert result.converged is False
    assert result.attempts == 2
    assert result.simulation_progress_ms == 20_000
    assert result.stop_reason == "simulation_progress_exhausted"


def test_insufficient_simulation_progress_stops_at_the_wall_safety_cap():
    wall = _WallClock()
    waiter = SimulationTimeConvergenceWaiter(
        lambda: {
            "configuration_channel": False,
            "continuation_authorized": True,
        },
        observe_simulation_state=_simulation_clock(0, 0, 5_000, 10_000),
        required_simulation_progress_ms=20_000,
        max_wall_seconds=45.0,
        interval_seconds=20.0,
        clock=wall,
        sleeper=wall.sleep,
    )

    result = waiter.wait()

    assert result.converged is False
    assert result.attempts == 3
    assert result.elapsed_ms == 45_000
    assert result.simulation_progress_ms == 10_000
    assert result.stop_reason == "wall_clock_safety_cap"


def test_invalid_simulation_clock_evidence_never_inspects_or_authorizes():
    inspected = []
    for observation, reason in (
        (
            SimulationStateObservation(observed=False, message="no readback"),
            "simulation_clock_unobservable",
        ),
        (
            SimulationStateObservation(
                observed=True, simulation_mode=True, sim_time=1,
            ),
            "simulation_clock_not_realtime",
        ),
        (
            SimulationStateObservation(
                observed=True, simulation_mode=False, sim_time=None,
            ),
            "simulation_clock_invalid",
        ),
    ):
        result = SimulationTimeConvergenceWaiter(
            lambda: inspected.append(True) or {
                "configuration_channel": True,
                "continuation_authorized": True,
            },
            observe_simulation_state=lambda observation=observation: observation,
            required_simulation_progress_ms=20_000,
            max_wall_seconds=45.0,
            interval_seconds=0.0,
        ).wait()

        assert result.converged is False
        assert result.attempts == 0
        assert result.stop_reason == reason
    assert inspected == []


def test_regressing_simulation_clock_fails_closed():
    result = SimulationTimeConvergenceWaiter(
        lambda: {
            "configuration_channel": False,
            "continuation_authorized": True,
        },
        observe_simulation_state=_simulation_clock(20_000, 19_999),
        required_simulation_progress_ms=20_000,
        max_wall_seconds=45.0,
        interval_seconds=0.0,
    ).wait()

    assert result.converged is False
    assert result.attempts == 0
    assert result.stop_reason == "simulation_clock_regressed"


def test_first_unauthorized_terminal_sample_ends_the_single_extension():
    simulation_reads = []

    def observe() -> SimulationStateObservation:
        simulation_reads.append(len(simulation_reads))
        return SimulationStateObservation(
            observed=True,
            simulation_mode=False,
            sim_time=len(simulation_reads) * 1_000,
        )

    result = SimulationTimeConvergenceWaiter(
        lambda: {
            "configuration_channel": False,
            "continuation_authorized": False,
            "failure_reason": "terminal evidence lost authority",
        },
        observe_simulation_state=observe,
        required_simulation_progress_ms=20_000,
        max_wall_seconds=45.0,
        interval_seconds=0.0,
    ).wait()

    assert result.converged is False
    assert result.attempts == 1
    assert result.clock_samples == 2
    assert result.stop_reason == "continuation_unauthorized"
    assert result.failure_reason == "terminal evidence lost authority"


def test_only_the_qualified_forward_delay_buys_a_protocol_budget():
    """The budget is qualified evidence, never a guess at a missing timer."""
    assert pvst_learning_progress_target_ms(15) == 20_000.0
    assert pvst_learning_progress_target_ms(15.0) == 20_000.0
    for unqualified in (
        None, "15", True, False, 0, 4, 14.9, 20, float("nan"), float("inf"),
    ):
        assert pvst_learning_progress_target_ms(unqualified) is None, unqualified


def test_a_raised_clock_read_keeps_its_detail_out_of_the_stop_token():
    """Retained stop reasons stay queryable tokens; detail has its own field."""

    def explode():
        raise RuntimeError("bridge closed")

    result = SimulationTimeConvergenceWaiter(
        lambda: {"configuration_channel": True},
        observe_simulation_state=explode,
        required_simulation_progress_ms=20_000,
        max_wall_seconds=45.0,
        interval_seconds=0.0,
    ).wait()

    assert result.converged is False
    assert result.attempts == 0
    assert result.stop_reason == "simulation_clock_read_failed"
    assert result.failure_reason == "RuntimeError: bridge closed"


def test_the_shared_extension_seam_pins_one_cap_for_every_caller():
    """Trunk and Voice cannot drift onto different bounds or a second window."""
    granted = []

    def inspect():
        granted.append(True)
        return {"configuration_channel": True, "continuation_authorized": True}

    extension = BoundedPvstLearningExtension(
        _simulation_clock(0, 1_000),
        interval_seconds=0.0,
    )
    assert extension.max_wall_seconds == (
        PVST_SIMULATION_PROGRESS_WALL_CAP_SECONDS
    )

    result = extension.grant(inspect, required_simulation_progress_ms=20_000.0)

    assert result.converged is True
    assert result.required_simulation_progress_ms == 20_000.0
    assert granted == [True]

    # The projected evidence names the bound this seam actually spent, so a
    # different cap can never be reported as the qualified one.
    tightened = BoundedPvstLearningExtension(
        _simulation_clock(0, 1_000),
        interval_seconds=0.0,
        max_wall_seconds=12.5,
    )
    evidence = tightened.evidence(result, requested_progress_ms=20_000.0)
    assert evidence["learning_extension_max_wall_seconds"] == 12.5
    assert evidence["learning_extension_clock"] == (
        "packet_tracer_simulation_time"
    )
    assert extension.evidence(result, requested_progress_ms=20_000.0)[
        "learning_extension_max_wall_seconds"
    ] == PVST_SIMULATION_PROGRESS_WALL_CAP_SECONDS
    assert extension.evidence(None, requested_progress_ms=None) == {
        **extension.evidence(None, requested_progress_ms=None),
        "learning_extension_authorized": False,
        "learning_extension_max_wall_seconds": 0.0,
        "learning_extension_stop_reason": "not_authorized",
    }


def _drive(inspect, observer, *, interval=0.0, wall=45.0):
    return SimulationTimeConvergenceWaiter(
        inspect,
        observe_simulation_state=observer,
        required_simulation_progress_ms=20_000,
        max_wall_seconds=wall,
        interval_seconds=interval,
    ).wait()


def _raises():
    raise RuntimeError("bridge closed")


def test_every_stop_cause_the_waiter_can_reach_carries_its_own_outcome():
    """Drive each terminal path and read back what it lets a consumer claim."""
    learning = {"configuration_channel": False, "continuation_authorized": True}
    wall = _WallClock()
    reached = {
        "converged": _drive(
            lambda: {"configuration_channel": True},
            _simulation_clock(0, 0),
        ),
        "simulation_progress_exhausted": _drive(
            lambda: learning, _simulation_clock(0, 0, 20_000),
        ),
        "continuation_unauthorized": _drive(
            lambda: {
                "configuration_channel": False,
                "continuation_authorized": False,
            },
            _simulation_clock(0, 0),
        ),
        "inspection_failed": _drive(
            _raises, _simulation_clock(0, 0),
        ),
        "simulation_clock_regressed": _drive(
            lambda: learning, _simulation_clock(20_000, 19_999),
        ),
        "simulation_clock_read_failed": _drive(lambda: learning, _raises),
        "simulation_clock_untyped": _drive(lambda: learning, lambda: None),
        "simulation_clock_unobservable": _drive(
            lambda: learning, _simulation_clock(0, observed=False),
        ),
        "simulation_clock_not_realtime": _drive(
            lambda: learning, _simulation_clock(0, realtime=False),
        ),
        "simulation_clock_invalid": _drive(
            lambda: learning, _simulation_clock(None),
        ),
        "wall_clock_safety_cap": SimulationTimeConvergenceWaiter(
            lambda: learning,
            observe_simulation_state=_simulation_clock(0, 0),
            required_simulation_progress_ms=20_000,
            max_wall_seconds=45.0,
            interval_seconds=45.0,
            clock=wall,
            sleeper=wall.sleep,
        ).wait(),
    }

    assert {
        reason: result.stop_reason for reason, result in reached.items()
    } == {reason: reason for reason in reached}

    extension = BoundedPvstLearningExtension(
        _simulation_clock(), interval_seconds=0.0,
    )
    assert {
        reason: extension.evidence(
            result, requested_progress_ms=20_000.0,
        )["learning_extension_outcome"]
        for reason, result in reached.items()
    } == {
        "converged": "converged",
        "simulation_progress_exhausted": "network_measured",
        "continuation_unauthorized": "network_measured",
        "inspection_failed": "observer_incomplete",
        "simulation_clock_regressed": "observer_incomplete",
        "simulation_clock_read_failed": "observer_incomplete",
        "simulation_clock_untyped": "observer_incomplete",
        "simulation_clock_unobservable": "observer_incomplete",
        "simulation_clock_not_realtime": "observer_incomplete",
        "simulation_clock_invalid": "observer_incomplete",
        "wall_clock_safety_cap": "observer_incomplete",
    }
    # The declared table must not drift from what the waiter actually emits.
    assert OBSERVER_INCOMPLETE_STOP_REASONS == {
        reason for reason, result in reached.items()
        if classify_extension_stop_reason(result.stop_reason)
        is ConvergenceOutcome.OBSERVER_INCOMPLETE
    }


def test_an_unknown_or_absent_stop_cause_never_speaks_for_the_network():
    """A token this classifier does not know is not one it may trust."""
    # Including values that are not even hashable: this runs while a
    # conclusion is being formed and must not raise past its caller.
    for unknown in (None, "", "banana", 0, object(), [], {"a": 1}):
        assert classify_extension_stop_reason(unknown) is (
            ConvergenceOutcome.OBSERVER_INCOMPLETE
        ), unknown


def test_the_projected_evidence_carries_the_causal_outcome():
    """Every consumer reads one typed outcome, never a prose stop string."""
    wall = _WallClock()
    result = SimulationTimeConvergenceWaiter(
        lambda: {"configuration_channel": False, "continuation_authorized": True},
        observe_simulation_state=_simulation_clock(0, 0, 20_000),
        required_simulation_progress_ms=20_000,
        max_wall_seconds=45.0,
        interval_seconds=1.0,
        clock=wall,
        sleeper=wall.sleep,
    ).wait()
    extension = BoundedPvstLearningExtension(
        _simulation_clock(), interval_seconds=0.0,
    )

    spent = extension.evidence(result, requested_progress_ms=20_000.0)
    assert spent["learning_extension_stop_reason"] == (
        "simulation_progress_exhausted"
    )
    assert spent["learning_extension_outcome"] == "network_measured"

    none_granted = extension.evidence(None, requested_progress_ms=None)
    assert none_granted["learning_extension_stop_reason"] == "not_authorized"
    assert none_granted["learning_extension_outcome"] == "network_measured"


def test_the_wall_cap_stops_admitting_rounds_without_interrupting_one():
    """The cap is an admission boundary; an in-flight read still finishes."""
    wall = _WallClock()

    def slow_inspect():
        # A bounded IOS read that happens to return after the boundary.
        wall.now += 44.0
        return {"configuration_channel": False, "continuation_authorized": True}

    result = SimulationTimeConvergenceWaiter(
        slow_inspect,
        observe_simulation_state=_simulation_clock(0, 0, 1_000, 2_000),
        required_simulation_progress_ms=20_000,
        max_wall_seconds=45.0,
        interval_seconds=0.0,
        clock=wall,
        sleeper=wall.sleep,
    ).wait()

    assert result.stop_reason == "wall_clock_safety_cap"
    assert result.attempts == 2, "the second round was admitted before the cap"
    # Honest accounting: the boundary bounds admission, not total elapsed.
    assert result.elapsed_ms == 88_000
