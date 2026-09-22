"""Four lifetimes, kept apart: nested call, sample, episode and phase.

The reviewed closure folded them into two booleans. A call refused underneath
one sample became "the episode exhausted its budget", and an episode that ran
out of window became "the sample arrived late". Both statements refuse reads
that are in fact complete and timely, and neither names the boundary that
actually closed.

The tests here are organised by lifetime rather than by module. The runtime
level proves what one bounded observation episode observes and reports; the
domain level proves what the shared admission rule does with those reports; the
composed level proves that a spent phase allowance stops the nested IOS waiter
instead of leaving it polling locally against a clock that no longer moves.
"""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from typing import Any

import pytest
from service_entry_fixture import ForwardingBackend, SimulatedClock

from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    LedgeredTransport,
    LedgerPhase,
    OperationLedger,
    OperationRefused,
)
from packet_tracer_mcp.application.use_cases.service_access_readiness_gate import (
    READINESS_GROUP_DEADLINE_SECONDS,
    READINESS_GROUP_MAX_SAMPLES,
    READINESS_MAX_GROUPS,
    READINESS_TOTAL_BUDGET_SECONDS,
    ServiceAccessReadinessGate,
)
from packet_tracer_mcp.domain.enterprise.models.forwarding import (
    AccessForwardingObservation,
    AccessForwardingRow,
    AccessForwardingSampleEvidence,
)
from packet_tracer_mcp.domain.enterprise.services.access_forwarding import (
    DIMENSION_DEADLINE,
    DIMENSION_EXECUTION,
    DIMENSION_IDENTITY,
    DIMENSION_NON_FORWARDING,
    DIMENSION_NONE,
    DIMENSION_SAMPLE_BUDGET,
    access_forwarding_admission,
    access_forwarding_facts,
)
from packet_tracer_mcp.infrastructure.execution.device_lifecycle import (
    DeviceReadinessWaiter,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    _PAGER_CAPTURE_DEADLINE_SECONDS,
    ControlledIosExecutor,
    OperationalQueryId,
    PagerContinuation,
)
from packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (
    SimulationStateObservation,
)
from tests.test_access_forwarding_runtime import _stp_output
from tests.test_e95_serial_orientation_pager_capture import (
    _dce_pages,
    _EndlessTerminal,
    _FakeClock,
    _PagedTerminal,
)
from tests.test_service_access_readiness import SWITCH, SWITCH_NAME, _plan

PORTS = ("FastEthernet1/1", "FastEthernet1/2", "FastEthernet1/3")

#: How long one composed regression may take in real seconds before the test
#: itself declares the loop unbounded. The observations under test are driven
#: by a simulated clock, so a healthy one returns in milliseconds.
WATCHDOG_SECONDS = 20.0


class ControlledSwitchTerminal(_PagedTerminal):
    """One switch whose answer follows simulated time, not the call count.

    `stalled_dispatches` names the dispatch ordinals whose command window never
    appears. The executor then spends that sample's nested call budget reading
    a terminal that never converges, which is a read-only exhaustion: no key is
    delivered, no pager is entered and no quarantine is raised.
    """

    def __init__(
        self,
        clock: SimulatedClock,
        forwards_at: float | None,
        *,
        stalled_dispatches: tuple[int, ...] = (),
        seconds_per_call: float = 0.02,
        seconds_before_attribution: float = 0.0,
    ) -> None:
        """Bind one simulated switch to the clock the test advances."""
        self.clock = clock
        self.forwards_at = forwards_at
        self.stalled_dispatches = stalled_dispatches
        self.seconds_per_call = seconds_per_call
        #: Time the switch spends before the LAST call of a sample, the one
        #: that attributes the session. A sample can therefore be complete,
        #: fresh and correctly attributed and still land after the window.
        self.seconds_before_attribution = seconds_before_attribution
        self.dispatches = 0
        self.calls = 0
        self.timeouts: list[float] = []
        self.samples: list[tuple[float, str]] = []
        super().__init__([""], prompt=f"{SWITCH_NAME}#", command="show spanning-tree")

    def _state_now(self) -> str:
        forwarding = self.forwards_at is not None and self.clock.now >= self.forwards_at
        return "FWD" if forwarding else "LIS"

    def _emit_first_page(self) -> None:
        self.dispatches += 1
        if self.dispatches in self.stalled_dispatches:
            return
        state = self._state_now()
        self.samples.append((self.clock.now, state))
        rendered = _stp_output(dict.fromkeys(PORTS, state), vlan=10)
        body = rendered.split("show spanning-tree\n", 1)[1].rsplit("SW#", 1)[0]
        self.pages = [body]
        super()._emit_first_page()

    def __call__(self, js: str, timeout: float) -> str:
        """Answer one nested channel call and charge it to the clock."""
        self.calls += 1
        self.timeouts.append(timeout)
        self.clock.advance(min(timeout, self.seconds_per_call))
        if "ipc.simulation()" in js:
            # The auxiliary simulation-state read is a real read with a real
            # answer. A fake that refused it would make "the reader failed"
            # the accidental result of an unimplemented fixture branch.
            return json.dumps(
                {
                    "mode": False,
                    "frames": 0,
                    "sim_time": round(self.clock.now, 3),
                    "current_index": -1,
                }
            )
        if "owner_candidate_evidence" in js:
            self.clock.advance(self.seconds_before_attribution)
            return json.dumps(
                {
                    "found": True,
                    "configuration_channel": True,
                    "output": self.output,
                    "owner_name": SWITCH_NAME,
                    "owner_evidence": "session_transcript_continuity",
                    "owner_candidates": 1,
                }
            )
        return super().__call__(js, timeout)


def _runtime(
    terminal: ControlledSwitchTerminal,
    clock: SimulatedClock,
    **kwargs: Any,
) -> PacketTracerEnterpriseConfigurationRuntime:
    """Compose the real observer over one controlled terminal."""
    return PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=terminal,
        clock=clock,
        sleeper=clock.advance,
        **kwargs,
    )


def _observe(
    runtime: PacketTracerEnterpriseConfigurationRuntime,
    **bounds: Any,
) -> AccessForwardingObservation:
    """Take one product-shaped observation episode of the fixture group."""
    defaults: dict[str, Any] = {
        "max_samples": READINESS_GROUP_MAX_SAMPLES,
        "deadline_seconds": READINESS_GROUP_DEADLINE_SECONDS,
        "interval_seconds": 1.0,
        "sample_calls": 6,
    }
    defaults.update(bounds)
    return runtime.observe_access_forwarding(SWITCH_NAME, 10, PORTS, **defaults)


def _forwarding_rows() -> tuple[AccessForwardingRow, ...]:
    return tuple(
        AccessForwardingRow(interface=item, matches=1, state="FWD", role="Desg")
        for item in PORTS
    )


def _complete_observation(**overrides: Any) -> AccessForwardingObservation:
    """One sample that refuses on nothing, so each field can refuse alone."""
    fields: dict[str, Any] = {
        "switch_name": SWITCH_NAME,
        "vlan_id": 10,
        "requested_interfaces": PORTS,
        "rows": _forwarding_rows(),
        "executed": True,
        "fresh_output_observed": True,
        "output_complete": True,
        "observed_device_name": SWITCH_NAME,
        "device_identity_provenance": "confirmed_unique",
        "vlan_present": True,
        "samples": 1,
        "max_samples": READINESS_GROUP_MAX_SAMPLES,
        "deadline_seconds": READINESS_GROUP_DEADLINE_SECONDS,
        "sample_call_budget": 6,
        "channel_calls": 4,
    }
    fields.update(overrides)
    return AccessForwardingObservation(**fields)


# -- R1: an individual sample is valid or not; an episode is not the sample ----


@pytest.mark.parametrize("forwards_at", [4.0, 26.0])
def test_an_early_exhausted_read_does_not_refuse_a_later_valid_sample(
    forwards_at: float,
) -> None:
    """A spent first read says nothing about a complete, timely later one."""
    clock = SimulatedClock()
    terminal = ControlledSwitchTerminal(clock, forwards_at, stalled_dispatches=(1,))
    runtime = _runtime(terminal, clock)

    observation = _observe(runtime)
    admission = access_forwarding_admission(observation)

    # The authorizing sample is the last one, and it is whole.
    assert admission.admitted is True
    assert admission.dimension == DIMENSION_NONE
    assert admission.forwarding_interfaces == PORTS
    assert [row.state for row in observation.rows] == ["FWD"] * len(PORTS)
    assert observation.sample_budget_exhausted is False
    assert observation.deadline_reached is False
    assert observation.deadline_cause == ""
    assert observation.episode_end_reason == "forwarding_sample_admitted"

    # The failed read is retained and is still described as what it was.
    assert observation.episode_budget_exhausted is True
    assert observation.sample_history[0].sample_budget_exhausted is True
    assert observation.sample_history[0].rows == ()
    assert observation.sample_history[-1].sample_budget_exhausted is False
    assert observation.samples == len(observation.sample_history)
    assert observation.samples >= 2

    # The transition was observed in time, not counted into existence.
    assert terminal.samples[-1][0] >= forwards_at
    assert terminal.samples[-1][0] < READINESS_GROUP_DEADLINE_SECONDS

    # A read-only exhaustion is not an authority or quarantine loss.
    assert runtime._forwarding_ios._pager_quarantine == set()


def test_an_early_exhausted_read_agrees_after_the_record_is_reloaded() -> None:
    """The published projection of that episode says the same thing."""
    clock = SimulatedClock()
    terminal = ControlledSwitchTerminal(clock, 4.0, stalled_dispatches=(1,))
    observation = _observe(_runtime(terminal, clock))
    admission = access_forwarding_admission(observation)

    facts = json.loads(json.dumps(access_forwarding_facts(observation, admission)))

    assert facts["admitted"] is True
    assert facts["sample_budget_exhausted"] is False
    assert facts["episode_budget_exhausted"] is True
    assert facts["sample_history"][0]["sample_budget_exhausted"] is True
    assert facts["sample_history"][-1]["sample_budget_exhausted"] is False
    assert len(facts["sample_history"]) == facts["samples"]
    assert facts["deadline_cause"] == ""


def test_an_exhausted_final_forwarding_sample_still_refuses() -> None:
    """FWD-shaped rows from a read that ended on its budget grant nothing."""
    observation = _complete_observation(
        sample_budget_exhausted=True,
        episode_budget_exhausted=True,
        channel_calls=6,
    )

    admission = access_forwarding_admission(observation)

    assert admission.admitted is False
    assert admission.dimension == DIMENSION_SAMPLE_BUDGET
    assert admission.causes == ("sample_call_budget_exhausted",)


def test_an_episode_exhaustion_alone_never_refuses_the_authorizing_sample() -> None:
    """The cumulative diagnostic is a diagnostic, not a refusal."""
    refused = access_forwarding_admission(
        _complete_observation(
            sample_budget_exhausted=True, episode_budget_exhausted=True
        )
    )
    admitted = access_forwarding_admission(
        _complete_observation(
            sample_budget_exhausted=False, episode_budget_exhausted=True
        )
    )

    assert refused.admitted is False
    assert admitted.admitted is True
    assert admitted.dimension == DIMENSION_NONE


def test_an_exhausted_auxiliary_read_refuses_under_its_own_name() -> None:
    """The auxiliary read is not the sample, so it does not borrow its cause."""
    admission = access_forwarding_admission(
        _complete_observation(
            auxiliary_budget_exhausted=True, episode_budget_exhausted=True
        )
    )

    assert admission.admitted is False
    assert admission.dimension == DIMENSION_SAMPLE_BUDGET
    assert admission.causes == ("auxiliary_read_call_budget_exhausted",)


def test_authority_loss_is_never_recovered_by_a_later_sample() -> None:
    """Identity is not a budget: clearing a budget flag recovers nothing."""
    clock = SimulatedClock()
    terminal = ControlledSwitchTerminal(clock, 0.0)

    def foreign(js: str, timeout: float) -> str:
        if "owner_candidate_evidence" in js:
            terminal.calls += 1
            terminal.clock.advance(min(timeout, terminal.seconds_per_call))
            return json.dumps(
                {
                    "found": True,
                    "configuration_channel": True,
                    "output": terminal.output,
                    "owner_name": "FOREIGN-SW",
                    "owner_evidence": "session_transcript_continuity",
                    "owner_candidates": 1,
                }
            )
        return ControlledSwitchTerminal.__call__(terminal, js, timeout)

    observation = _observe(_runtime(foreign, clock))
    admission = access_forwarding_admission(observation)

    # Every sample of the episode is refused for the same reason, and no
    # budget flag is involved: the refusal has nothing to do with the change.
    assert observation.samples > 1
    assert admission.admitted is False
    assert admission.dimension in {DIMENSION_EXECUTION, DIMENSION_IDENTITY}
    assert observation.sample_budget_exhausted is False
    assert observation.episode_budget_exhausted is False
    assert "FOREIGN-SW" in admission.causes[0]

    # And it does not become admissible by clearing the flags this change
    # made narrower. Authority is not recoverable by a later read.
    cleared = replace(
        observation, sample_budget_exhausted=False, episode_budget_exhausted=False
    )
    assert access_forwarding_admission(cleared).admitted is False
    assert access_forwarding_admission(cleared).causes == admission.causes


# -- R2: lateness, termination, parent boundary and auxiliary delay ------------


def test_a_timely_persistent_lis_episode_does_not_claim_a_late_sample() -> None:
    """A window that ended says so; the last read was on time and was LIS."""
    clock = SimulatedClock()
    terminal = ControlledSwitchTerminal(clock, None)
    observation = _observe(_runtime(terminal, clock))

    admission = access_forwarding_admission(observation)

    assert observation.sample_after_deadline is False
    assert observation.sample_history[-1].deadline_reached is False
    assert observation.episode_end_reason in {"deadline", "max_samples_reached"}
    assert [row.state for row in observation.rows] == ["LIS"] * len(PORTS)
    assert admission.admitted is False
    if observation.deadline_reached:
        assert observation.deadline_cause == (
            "episode_window_ended_without_admissible_sample"
        )
        assert admission.dimension == DIMENSION_DEADLINE
        assert admission.causes == ("episode_window_ended_without_admissible_sample",)
    else:
        assert admission.dimension == DIMENSION_NON_FORWARDING


def test_a_genuinely_late_sample_is_reported_late() -> None:
    """A read that landed past the window is late, and it is named late."""
    clock = SimulatedClock()
    terminal = ControlledSwitchTerminal(clock, 0.0, seconds_before_attribution=4.0)
    observation = _observe(_runtime(terminal, clock), deadline_seconds=1.0)

    admission = access_forwarding_admission(observation)

    # Complete, fresh and correctly attributed -- and still too late.
    assert observation.executed is True
    assert observation.output_complete is True
    assert observation.device_identity_provenance == "confirmed_unique"
    assert [row.state for row in observation.rows] == ["FWD"] * len(PORTS)
    assert observation.sample_after_deadline is True
    assert observation.sample_history[-1].deadline_reached is True
    assert observation.deadline_reached is True
    assert observation.deadline_cause == "sample_after_deadline"
    assert admission.admitted is False
    assert admission.dimension == DIMENSION_DEADLINE
    assert admission.causes == ("sample_after_deadline",)


def test_a_timely_sample_refused_by_an_auxiliary_overrun_stays_timely() -> None:
    """The overrun is the auxiliary read's; the FWD sample is not rewritten."""
    clock = SimulatedClock()
    terminal = ControlledSwitchTerminal(clock, 0.0)

    def slow_auxiliary() -> SimulationStateObservation:
        clock.advance(5.0)
        return SimulationStateObservation(observed=False)

    observation = _observe(
        _runtime(terminal, clock, simulation_time_observer=slow_auxiliary),
        deadline_seconds=1.0,
    )
    admission = access_forwarding_admission(observation)

    assert [row.state for row in observation.rows] == ["FWD"] * len(PORTS)
    assert observation.sample_after_deadline is False
    assert observation.sample_history[-1].deadline_reached is False
    assert observation.auxiliary_read_after_deadline is True
    assert observation.deadline_reached is True
    assert observation.deadline_cause == "auxiliary_read_after_deadline"
    assert admission.admitted is False
    assert admission.dimension == DIMENSION_DEADLINE
    assert admission.causes == ("auxiliary_read_after_deadline",)


def test_exhaustion_before_any_sample_names_itself() -> None:
    """A first read that never completed refuses as execution, not lateness."""
    clock = SimulatedClock()
    terminal = ControlledSwitchTerminal(clock, 0.0, stalled_dispatches=(1,))
    observation = _observe(_runtime(terminal, clock), max_samples=1)

    admission = access_forwarding_admission(observation)

    assert observation.samples == 1
    assert observation.sample_budget_exhausted is True
    assert observation.episode_budget_exhausted is True
    assert observation.deadline_reached is False
    assert admission.admitted is False
    assert admission.dimension == DIMENSION_EXECUTION
    assert admission.causes == ("sample_call_budget_exhausted",)


def test_a_timely_admitted_sample_names_no_boundary_at_all() -> None:
    """The positive control: nothing expired, so nothing is reported expired."""
    clock = SimulatedClock()
    terminal = ControlledSwitchTerminal(clock, 0.0)
    observation = _observe(_runtime(terminal, clock))

    admission = access_forwarding_admission(observation)

    assert admission.admitted is True
    assert observation.deadline_reached is False
    assert observation.deadline_cause == ""
    assert observation.sample_after_deadline is False
    assert observation.auxiliary_read_after_deadline is False
    assert observation.episode_budget_exhausted is False
    assert observation.episode_end_reason == "forwarding_sample_admitted"


def _gated(
    forwards_at: float | None,
    *,
    total_budget_seconds: float = READINESS_TOTAL_BUDGET_SECONDS,
    **runtime_kwargs: Any,
) -> tuple[Any, list[dict[str, object]]]:
    """Decide one group through the product gate and return its public row."""
    clock = SimulatedClock()
    terminal = ControlledSwitchTerminal(clock, forwards_at, **runtime_kwargs)
    gate = ServiceAccessReadinessGate(
        _plan(),
        _runtime(terminal, clock),
        clock=clock,
        device_names={SWITCH: SWITCH_NAME},
        total_budget_seconds=total_budget_seconds,
    )
    decision = gate.decide("http-1")
    return decision, gate.rows()


@pytest.mark.parametrize(
    ("scenario", "expected_dimension", "expected_cause", "last_sample_was_late"),
    [
        # The last read was timely LIS; only the window ended.
        ("persistent_lis", DIMENSION_DEADLINE, "episode_window_ended", False),
        # The last read really did land after the window.
        ("late_sample", DIMENSION_DEADLINE, "sample_after_deadline", True),
        # Every read spent its call budget, and the last one also ran out of
        # window doing so -- both are true, and the more specific one refuses.
        ("early_exhaustion", DIMENSION_EXECUTION, "sample_call_budget_exhausted", True),
    ],
)
def test_the_gate_and_its_stored_row_name_the_boundary_that_expired(
    scenario: str,
    expected_dimension: str,
    expected_cause: str,
    last_sample_was_late: bool,
) -> None:
    """Every refused case reaches the public row with a truthful reason.

    The gate is the product's permission boundary, so this is where "no HTTP"
    is decided: a refused verdict is what stops the dependent request, and the
    row is what a later reader has. Both have to say the same true thing.
    """
    if scenario == "persistent_lis":
        decision, rows = _gated(None)
    elif scenario == "late_sample":
        decision, rows = _gated(
            0.0, seconds_before_attribution=4.0, total_budget_seconds=1.0
        )
    else:
        decision, rows = _gated(0.0, stalled_dispatches=tuple(range(1, 40)))

    assert decision is not None
    assert decision.admitted is False, rows
    sample = rows[0]["sample"]
    assert sample["dimension"] == expected_dimension
    assert any(expected_cause in str(item) for item in sample["causes"]), sample[
        "causes"
    ]
    # The stored projection survives a round trip unchanged.
    assert json.loads(json.dumps(sample)) == sample
    # And lateness is reported for exactly the reads that were late.
    assert sample["sample_after_deadline"] is last_sample_was_late
    assert sample["sample_history"][-1]["deadline_reached"] is last_sample_was_late


def test_the_gate_admits_the_timely_positive_and_names_no_boundary() -> None:
    """The control for the three refusals above, through the same gate."""
    decision, rows = _gated(0.0)

    assert decision is not None and decision.admitted is True
    sample = rows[0]["sample"]
    assert sample["dimension"] == DIMENSION_NONE
    assert sample["deadline_reached"] is False
    assert sample["deadline_cause"] == ""
    assert sample["sample_after_deadline"] is False
    assert sample["episode_end_reason"] == "forwarding_sample_admitted"


def test_the_applicable_parent_boundary_is_recorded_with_its_scope() -> None:
    """Which of the group and invocation bounds applied is a stated fact."""
    clock = SimulatedClock()
    group = _observe(_runtime(ControlledSwitchTerminal(clock, 0.0), clock))
    clock = SimulatedClock()
    parent = _observe(
        _runtime(ControlledSwitchTerminal(clock, 0.0), clock), remaining_seconds=5.0
    )

    assert group.deadline_scope == "group"
    assert group.deadline_seconds == READINESS_GROUP_DEADLINE_SECONDS
    assert parent.deadline_scope == "invocation_remaining"
    assert parent.deadline_seconds == 5.0


def test_a_legacy_record_without_a_named_cause_keeps_its_interpretation() -> None:
    """An older stored observation still reads as the late sample it was."""
    admission = access_forwarding_admission(
        _complete_observation(deadline_reached=True)
    )

    assert admission.admitted is False
    assert admission.dimension == DIMENSION_DEADLINE
    assert admission.causes == ("sample_after_deadline",)


def test_the_published_projection_separates_raw_facts_from_decisions() -> None:
    """Every new field reaches the durable record under its own key."""
    observation = _complete_observation(
        sample_history=(
            AccessForwardingSampleEvidence(
                elapsed_ms=10,
                rows=(),
                executed=False,
                fresh_output_observed=False,
                output_complete=False,
                observed_device_name="",
                device_identity_provenance="not_observed",
                vlan_present=False,
                channel_calls=6,
                sample_budget_exhausted=True,
                deadline_reached=False,
            ),
        ),
        episode_budget_exhausted=True,
        episode_end_reason="forwarding_sample_admitted",
        deadline_scope="group",
    )

    facts = access_forwarding_facts(
        observation, access_forwarding_admission(observation)
    )

    assert facts["sample_budget_exhausted"] is False
    assert facts["episode_budget_exhausted"] is True
    assert facts["auxiliary_budget_exhausted"] is False
    assert facts["sample_after_deadline"] is False
    assert facts["auxiliary_read_after_deadline"] is False
    assert facts["episode_end_reason"] == "forwarding_sample_admitted"
    assert facts["deadline_scope"] == "group"
    assert facts["deadline_cause"] == ""
    # The pre-existing keys keep their names and their meaning.
    assert facts["deadline_reached"] is False
    assert facts["channel_calls"] == 4
    assert facts["samples"] == 1


# -- R3: expiration stops the nested waiter, and names its own boundary --------


class _LedgeredComposition:
    """The actual diagnostic composition: ledger, transport, runtime, clock."""

    def __init__(
        self,
        *,
        max_seconds: float,
        max_operations: int = 200,
        reserve_operations: int = 5,
        reserve_seconds: float = 0.02,
        forwards_at: float | None = None,
    ) -> None:
        """Bind one bounded phase to one controlled switch."""
        self.clock = SimulatedClock()
        self.terminal = ControlledSwitchTerminal(self.clock, forwards_at)
        self.ledger = OperationLedger(
            max_operations=max_operations,
            max_seconds=max_seconds,
            clock=self.clock,
        )
        self.ledger.reserve(reserve_operations, reserve_seconds)
        self.ledger.enter(LedgerPhase.EXPERIMENT)
        self.sleeps: list[float] = []
        self.bound = LedgeredTransport(self.ledger, self, self._sleep, self.clock)
        self.runtime = PacketTracerEnterpriseConfigurationRuntime(
            lambda: [],
            self.bound.send,
            self.bound.send_and_wait,
            clock=self.bound.clock,
            sleeper=self.bound.capped_sleep,
        )

    def _sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.clock.advance(seconds)

    def send(self, _js: str) -> bool:
        """Accept one fire-and-forget command; this composition sends none."""
        return True

    def send_and_wait(self, js: str, timeout: float) -> str | None:
        """Dispatch one command at the one real point below the ledger."""
        return self.terminal(js, timeout)

    def observe(self, **bounds: Any) -> AccessForwardingObservation:
        """Run one episode under an outer watchdog and return its result."""
        box: dict[str, Any] = {}
        done = threading.Event()

        def run() -> None:
            try:
                box["observation"] = _observe(self.runtime, **bounds)
            except BaseException as exc:
                box["error"] = exc
            finally:
                done.set()

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        assert done.wait(WATCHDOG_SECONDS), (
            "the observation did not terminate: dispatches="
            f"{self.terminal.dispatches} ledger_entries={len(self.ledger.entries)} "
            f"clock={self.clock.now}"
        )
        if "error" in box:
            raise box["error"]
        return box["observation"]


def test_the_nested_waiter_stops_when_the_phase_allowance_is_spent() -> None:
    """A parent phase that expires first ends the episode, not a local poll."""
    composition = _LedgeredComposition(max_seconds=0.05, forwards_at=None)

    observation = composition.observe()
    dispatched = composition.terminal.calls

    assert observation.samples >= 1
    assert observation.sample_budget_exhausted is True
    # The loop stopped on the boundary, not after thousands of local turns.
    assert composition.terminal.calls == dispatched
    assert composition.ledger.refused_calls <= observation.samples * 6
    assert not [item for item in composition.sleeps if item > 0.05]
    # The protected cleanup reserve is untouched by the observation.
    composition.ledger.enter(LedgerPhase.FINALIZATION)
    operations, seconds = composition.ledger.allowance()
    assert operations > 0
    assert seconds > 0


def test_the_nested_waiter_stops_when_the_call_allowance_is_spent() -> None:
    """A sample whose six nested calls are gone stops reading immediately."""
    clock = SimulatedClock()
    terminal = ControlledSwitchTerminal(clock, None, stalled_dispatches=(1,))
    runtime = _runtime(terminal, clock)

    observation = _observe(runtime, max_samples=1)

    assert observation.samples == 1
    assert observation.sample_budget_exhausted is True
    assert observation.sample_history[0].channel_calls <= 6
    # Without the live control the convergence waiter burned its whole
    # eight-second snapshot polling a channel that could not dispatch.
    assert observation.sample_history[0].elapsed_ms < 1000
    assert clock.now < 1.0


def test_a_terminal_refusal_stops_the_nested_waiter() -> None:
    """A refusal underneath the channel ends the channel, promptly."""
    clock = SimulatedClock()
    calls: list[str] = []

    def refusing(js: str, _timeout: float) -> str | None:
        calls.append(js)
        if len(calls) > 2:
            raise OperationRefused("operation_budget_exhausted")
        return json.dumps(
            {
                "found": True,
                "booting": False,
                "terminal": True,
                "terminal_available": True,
                "terminal_kind": "ios_command_line",
                "prompt": f"{SWITCH_NAME}#",
                "output": f"{SWITCH_NAME}#",
            }
        )

    box: dict[str, Any] = {}
    done = threading.Event()

    def run() -> None:
        try:
            box["observation"] = _observe(
                _runtime(refusing, clock), max_samples=READINESS_GROUP_MAX_SAMPLES
            )
        except BaseException as exc:
            box["error"] = exc
        finally:
            done.set()

    threading.Thread(target=run, daemon=True).start()
    assert done.wait(WATCHDOG_SECONDS), f"unbounded loop after {len(calls)} calls"
    assert "error" not in box, box.get("error")

    observation = box["observation"]
    assert observation.samples >= 1
    assert observation.sample_budget_exhausted is True
    assert observation.episode_end_reason.startswith("channel_refused:")
    assert "OperationRefused" in observation.episode_end_reason
    # No read is attempted after the channel stopped granting them.
    assert len(calls) <= 8


def test_normal_progress_is_unchanged_in_the_same_composition() -> None:
    """The control: an allowance that is not spent observes and admits."""
    composition = _LedgeredComposition(max_seconds=120.0, forwards_at=0.0)

    observation = composition.observe()

    admission = access_forwarding_admission(observation)
    assert admission.admitted is True
    assert observation.samples == 1
    assert observation.episode_end_reason == "forwarding_sample_admitted"
    assert composition.ledger.refused_calls == 0


def test_a_pager_capture_that_owns_the_expired_deadline_still_says_so() -> None:
    """The control: the capture's own 25-second limit ran out, and it says so."""
    terminal = _EndlessTerminal(_dce_pages())

    result = ControlledIosExecutor(
        terminal,
        clock=_FakeClock(step=10.0),
        sleeper=lambda _seconds: None,
    ).execute(
        "MCP-R1",
        OperationalQueryId.SHOW_CONTROLLERS_SERIAL,
        interface="Serial0/0/0",
    )

    assert result.output_complete is False
    assert result.pager_continuation == PagerContinuation.FAILED.value
    assert "exceeded its bounded deadline" in result.failure_reason
    assert f"{_PAGER_CAPTURE_DEADLINE_SECONDS:.0f}s" in result.failure_reason
    assert "caller" not in result.failure_reason.casefold()


def test_a_shorter_caller_allowance_is_not_reported_as_the_pager_deadline() -> None:
    """The capture names the boundary that expired, not the one it owns.

    `_bounded_wait` applies both the capture's own deadline and the caller's
    remaining allowance, so a zero from it proves only that one of them ran
    out. Reporting the capture's own limit for a caller that ran out first
    sends a reader looking for a pager that was never slow.
    """
    terminal = _EndlessTerminal(_dce_pages())
    reads: list[int] = []

    def caller_allowance() -> float:
        # Generous at first, so the capture really starts, then spent.
        reads.append(len(reads))
        return 5.0 if len(reads) <= 4 else 0.0

    executor = ControlledIosExecutor(
        terminal,
        clock=_FakeClock(step=0.5),
        sleeper=lambda _seconds: None,
        remaining_budget=caller_allowance,
    )
    result = executor.execute(
        "MCP-R1",
        OperationalQueryId.SHOW_CONTROLLERS_SERIAL,
        interface="Serial0/0/0",
    )

    assert result.output_complete is False
    assert result.pager_continuation == PagerContinuation.FAILED.value
    assert "caller's remaining allowance" in result.failure_reason
    # The capture's own deadline is named as the one that did NOT expire.
    assert (
        "before its own bounded deadline of "
        f"{_PAGER_CAPTURE_DEADLINE_SECONDS:.0f}s" in result.failure_reason
    )
    # And the clock never reached that deadline, which is the whole point.
    assert executor._clock() < _PAGER_CAPTURE_DEADLINE_SECONDS


def test_a_readiness_waiter_without_a_control_polls_exactly_as_before() -> None:
    """Ordinary boot and ungated IOS waits keep their unbounded interval."""
    ticks: list[float] = []
    clock = SimulatedClock()

    waiter = DeviceReadinessWaiter(
        lambda: {"found": True},
        timeout_seconds=1.0,
        interval_seconds=0.25,
        clock=clock,
        sleeper=lambda seconds: (ticks.append(seconds), clock.advance(seconds))[1],
    )
    result = waiter.wait()

    assert ticks == [0.25, 0.25, 0.25, 0.25]
    assert result.attempts == 5


def test_a_readiness_waiter_stops_on_a_spent_control_without_sleeping() -> None:
    """The live control ends the poll; it never becomes an extra sleep."""
    ticks: list[float] = []
    clock = SimulatedClock()
    allowance = [1.0]

    def inspect() -> dict:
        allowance[0] -= 0.5
        return {"found": True}

    waiter = DeviceReadinessWaiter(
        inspect,
        timeout_seconds=600.0,
        interval_seconds=0.25,
        clock=clock,
        sleeper=lambda seconds: (ticks.append(seconds), clock.advance(seconds))[1],
        remaining_seconds=lambda: allowance[0],
    )
    result = waiter.wait()

    assert result.attempts == 2
    assert ticks == [0.25]
    assert result.state.value in {"timeout", "not_found"}


# -- P1: the shared absolute window is a policy, and it is stated --------------


def test_a_late_group_inherits_only_the_remaining_shared_window() -> None:
    """The 30-second horizon is a ceiling, never 30 fresh seconds per group."""
    backend = ForwardingBackend(forwards_at=None)
    gate = ServiceAccessReadinessGate(
        _plan(),
        backend,
        clock=backend.clock,
        device_names={SWITCH: SWITCH_NAME},
    )

    # The first readiness observation starts the shared window; HTTP time
    # spent between groups is neither paused nor refunded.
    gate._started = 0.0
    backend.clock.now = 106.0
    gate.decide("http-1")

    assert backend.limits[0]["remaining_seconds"] == pytest.approx(14.0)
    assert backend.limits[0]["deadline_seconds"] == READINESS_GROUP_DEADLINE_SECONDS
    assert READINESS_TOTAL_BUDGET_SECONDS == 120.0


def test_an_expired_shared_window_observes_nothing_at_all() -> None:
    """Past 120 seconds there is no group horizon left to spend."""
    backend = ForwardingBackend(forwards_at=0.0)
    gate = ServiceAccessReadinessGate(
        _plan(),
        backend,
        clock=backend.clock,
        device_names={SWITCH: SWITCH_NAME},
    )
    gate._started = 0.0
    backend.clock.now = 120.0

    decision = gate.decide("http-1")

    assert decision is not None and decision.admitted is False
    assert backend.calls == []


# -- P2: the durable record is measured at a supported public limit ------------


def test_the_serialized_readiness_record_is_measured_at_a_supported_limit() -> None:
    """Measure the worst supported record instead of assuming it is unbounded.

    The public ceilings are the product's own: four groups per invocation,
    thirty-one samples per group and the twenty-four access ports of the
    largest catalogued access switch. The measurement is recorded so a future
    truncation decision can be argued from a number.
    """
    interfaces = tuple(f"FastEthernet0/{index + 1}" for index in range(24))
    rows = tuple(
        AccessForwardingRow(interface=item, matches=1, state="FWD", role="Desg")
        for item in interfaces
    )
    history = tuple(
        AccessForwardingSampleEvidence(
            elapsed_ms=index * 1000,
            rows=rows,
            executed=True,
            fresh_output_observed=True,
            output_complete=True,
            observed_device_name=SWITCH_NAME,
            device_identity_provenance="confirmed_unique",
            vlan_present=True,
            channel_calls=6,
            sample_budget_exhausted=False,
            deadline_reached=False,
        )
        for index in range(READINESS_GROUP_MAX_SAMPLES)
    )
    observation = _complete_observation(
        requested_interfaces=interfaces,
        rows=rows,
        samples=READINESS_GROUP_MAX_SAMPLES,
        sample_history=history,
        channel_calls=READINESS_GROUP_MAX_SAMPLES * 6 + 1,
    )
    group = access_forwarding_facts(
        observation, access_forwarding_admission(observation)
    )

    one_group = len(json.dumps(group, separators=(",", ":")).encode("utf-8"))
    invocation = one_group * READINESS_MAX_GROUPS

    # Measured, not asserted into existence: about 0.6 MiB per group and
    # 2.5 MiB for a full invocation at the supported ceiling. The value is
    # pinned loosely so the test reports growth instead of exact formatting.
    assert one_group < 1_000_000, one_group
    assert invocation < 4_000_000, invocation
    assert len(group["sample_history"]) == READINESS_GROUP_MAX_SAMPLES
