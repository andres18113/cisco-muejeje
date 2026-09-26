"""The neutral access observer's simulation-time extension.

Episode 7 of SERVER-PT-DHCP-AUTONOMOUS-02 saw both requested IE-2000 ports in
STP listening on its one complete sample; the next sample fell after the
30-second wall window and HTTP was withheld. PVST timers run on Packet
Tracer's simulation clock, which the retained measurement puts at 0.53 to 0.59
simulated seconds per wall second under load. These tests hold the correction
to its contract: a transitional window earns one bounded extension measured on
that clock, and admission still needs one timely, authoritative read with every
port forwarding.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from service_entry_fixture import SimulatedClock

from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    _GatedConfigurationRuntime,
    _MutationGate,
)
from packet_tracer_mcp.application.use_cases.service_access_readiness_gate import (
    READINESS_EPISODE_CALLS,
    READINESS_GROUP_DEADLINE_SECONDS,
    READINESS_GROUP_INTERVAL_SECONDS,
    READINESS_GROUP_MAX_SAMPLES,
    READINESS_SAMPLE_CALLS,
    READINESS_TOTAL_BUDGET_SECONDS,
    ServiceAccessReadinessGate,
)
from packet_tracer_mcp.domain.enterprise.models.forwarding import (
    AccessForwardingExtension,
    AccessForwardingObservation,
    AccessForwardingRow,
    AccessForwardingSampleEvidence,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.services.access_forwarding import (
    DIMENSION_DEADLINE,
    DIMENSION_NONE,
    access_forwarding_admission,
    access_forwarding_facts,
)
from packet_tracer_mcp.domain.enterprise.services.readiness_evidence import (
    parse_access_sample,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
    access_forwarding_extension_budget,
)
from packet_tracer_mcp.infrastructure.execution.simulation_time_convergence import (
    PVST_LISTENING_SIMULATION_PROGRESS_WALL_CAP_SECONDS,
    PVST_SIMULATION_PROGRESS_WALL_CAP_SECONDS,
)
from packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (
    SimulationStateObservation,
)
from tests.test_access_forwarding_runtime import _Clock, _result, _stp_output
from tests.test_sample_episode_phase_boundaries import (
    ControlledSwitchTerminal,
)
from tests.test_sample_episode_phase_boundaries import (
    _runtime as _terminal_runtime,
)
from tests.test_service_access_readiness import (
    PC1,
    PC2,
    SERVER,
    SWITCH,
    SWITCH_NAME,
    _Action,
    _Expectation,
    _plan,
)

PORTS = ("FastEthernet1/1", "FastEthernet1/3")
VLAN = 10
#: What one product readiness sample cost on episode 7's file channel.
SAMPLE_SECONDS = 19.0
#: The product gate's own bounds, and the allowance it offers a lone group.
BOUNDS: dict[str, Any] = {
    "max_samples": READINESS_GROUP_MAX_SAMPLES,
    "deadline_seconds": READINESS_GROUP_DEADLINE_SECONDS,
    "interval_seconds": READINESS_GROUP_INTERVAL_SECONDS,
    "sample_calls": READINESS_SAMPLE_CALLS,
    "episode_calls": READINESS_EPISODE_CALLS,
    "remaining_seconds": READINESS_TOTAL_BUDGET_SECONDS,
}
LONE_GROUP_ALLOWANCE = (
    READINESS_TOTAL_BUDGET_SECONDS
    - READINESS_GROUP_DEADLINE_SECONDS
    - READINESS_GROUP_INTERVAL_SECONDS
)


def _stp(*states: str, forward_delay: int = 15, vlan: int = VLAN) -> str:
    output = _stp_output(dict(zip(PORTS, states, strict=True)), vlan=vlan)
    return output.replace("Forward Delay 15 sec", f"Forward Delay {forward_delay} sec")


def _read(*states: str, **kwargs: Any):
    return _result(_stp(*states, **kwargs))


#: A read the window's own deadline cut short: nothing was executed.
TRUNCATED = _result(
    "",
    executed=False,
    fresh_output_observed=False,
    output_complete=False,
    observed_device_name="",
)
#: A complete read attributed to another device: a failure, not a truncation.
FOREIGN = _result(_stp("LIS", "LIS"), observed_device_name="OTHER")


class _TimedIos:
    """Answer each read in turn; every read costs wall time on the clock."""

    def __init__(self, clock: _Clock, results: list, cost: float) -> None:
        self.clock = clock
        self.results = list(results)
        self.cost = cost
        self.calls = 0

    def execute(self, device_name: str, query_id: object, **kwargs: Any):
        self.clock.now += self.cost
        self.calls += 1
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


class _SimulationClock:
    """Packet Tracer's protocol clock, in milliseconds, slower than wall time."""

    def __init__(
        self,
        wall: _Clock,
        rate: float = 0.55,
        *,
        observed: bool = True,
        simulation_mode: bool = False,
    ) -> None:
        self.wall = wall
        self.rate = rate
        self.observed = observed
        self.simulation_mode = simulation_mode
        self.reads = 0

    def __call__(self) -> SimulationStateObservation:
        self.reads += 1
        return SimulationStateObservation(
            observed=self.observed,
            simulation_mode=self.simulation_mode,
            sim_time=self.wall.now * self.rate * 1000.0,
        )


def _observe(
    results: list,
    *,
    cost: float = SAMPLE_SECONDS,
    extension_seconds: float = LONE_GROUP_ALLOWANCE,
    simulation: dict[str, Any] | None = None,
    **bounds: Any,
) -> tuple[AccessForwardingObservation, _TimedIos, _SimulationClock]:
    clock = _Clock()
    ios = _TimedIos(clock, results, cost)
    simulation_clock = _SimulationClock(clock, **(simulation or {}))
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: None,
        simulation_time_observer=simulation_clock,
        clock=clock,
        sleeper=clock.sleep,
    )
    runtime._forwarding_ios = ios
    observation = runtime.observe_access_forwarding(
        "SW",
        VLAN,
        PORTS,
        **{**BOUNDS, **bounds, "extension_seconds": extension_seconds},
    )
    return observation, ios, simulation_clock


# -- the budget rule --------------------------------------------------------------


def _rows(*states: str, matches: int = 1) -> tuple[AccessForwardingRow, ...]:
    return tuple(
        AccessForwardingRow(interface=name, matches=matches, state=state, role="Desg")
        for name, state in zip(PORTS, states, strict=True)
    )


def test_listening_earns_two_forward_delays_and_learning_earns_one():
    """The budgets are protocol arithmetic on the qualified forward delay."""
    assert access_forwarding_extension_budget(_rows("LIS", "FWD"), 15) == (
        35000.0,
        PVST_LISTENING_SIMULATION_PROGRESS_WALL_CAP_SECONDS,
    )
    assert access_forwarding_extension_budget(_rows("LRN", "FWD"), 15) == (
        20000.0,
        PVST_SIMULATION_PROGRESS_WALL_CAP_SECONDS,
    )
    assert access_forwarding_extension_budget(_rows("LIS", "LRN"), 15)[0] == 35000.0


@pytest.mark.parametrize(
    ("rows", "forward_delay"),
    [
        (_rows("BLK", "LIS"), 15),
        (_rows("FWD", "FWD"), 15),
        (_rows("LIS", "LIS", matches=0), 15),
        (_rows("LIS", "LIS", matches=2), 15),
        (_rows("LIS", "LIS"), 20),
        (_rows("LIS", "LIS"), None),
        ((), 15),
    ],
)
def test_anything_but_a_resolved_transitional_sample_earns_nothing(rows, forward_delay):
    """Blocked, forwarding, missing, duplicated or unqualified evidence."""
    assert access_forwarding_extension_budget(rows, forward_delay) is None


# -- the runtime observer ---------------------------------------------------------


def test_episode_seven_evidence_reaches_forwarding_inside_the_extension():
    """Listening, then a read the deadline cut, then learning and forwarding."""
    observation, ios, simulation_clock = _observe(
        [
            _read("LIS", "LIS"),
            TRUNCATED,
            _read("LRN", "LRN"),
            _read("FWD", "FWD"),
        ]
    )

    admission = access_forwarding_admission(observation)
    assert (admission.admitted, admission.dimension) == (True, DIMENSION_NONE)
    extension = observation.extension
    assert extension.candidate is True and extension.converged is True
    assert extension.target_ms == 35000.0
    assert extension.wall_cap_seconds == (
        PVST_LISTENING_SIMULATION_PROGRESS_WALL_CAP_SECONDS
    )
    assert extension.allowance_seconds == LONE_GROUP_ALLOWANCE
    assert extension.authorized is True
    assert (extension.stop_reason, extension.outcome) == ("converged", "converged")
    assert extension.samples == 2 and simulation_clock.reads == extension.clock_samples
    assert [item.phase for item in observation.sample_history] == [
        "window",
        "window",
        "extension",
        "extension",
    ]
    assert observation.samples == 4 == ios.calls
    assert observation.deadline_reached is False
    assert observation.deadline_cause == ""
    assert observation.sample_after_deadline is False
    assert (
        observation.episode_end_reason == "all_requested_interfaces_observed_forwarding"
    )


def test_the_recorded_extension_survives_the_durable_round_trip():
    """The facts carry the extension, and re-reading them admits the same way."""
    observation, _ios, _clock = _observe(
        [_read("LIS", "LIS"), TRUNCATED, _read("FWD", "FWD")]
    )
    facts = access_forwarding_facts(
        observation, access_forwarding_admission(observation)
    )

    assert json.loads(json.dumps(facts)) == facts
    assert facts["extension"]["converged"] is True
    assert facts["extension"]["clock"] == "packet_tracer_simulation_time"
    assert [item["phase"] for item in facts["sample_history"]] == [
        "window",
        "window",
        "extension",
    ]
    reparsed = parse_access_sample(facts)
    assert access_forwarding_admission(reparsed).admitted is True


def test_without_an_allowance_the_window_result_is_unchanged():
    """Zero, the default every other caller passes, grants no extension."""
    observation, ios, simulation_clock = _observe(
        [_read("LIS", "LIS"), TRUNCATED, _read("FWD", "FWD")],
        extension_seconds=0.0,
    )

    assert access_forwarding_admission(observation).admitted is False
    assert observation.extension == AccessForwardingExtension()
    assert observation.samples == 2 == ios.calls
    assert simulation_clock.reads == 0
    assert observation.episode_end_reason == "deadline"


def test_a_run_that_needs_no_extension_records_no_offer():
    """The offer is clock-derived, so equivalent runs must not record it."""
    observation, ios, _clock = _observe([_read("FWD", "FWD")])

    assert access_forwarding_admission(observation).admitted is True
    assert observation.extension == AccessForwardingExtension()
    assert observation.samples == ios.calls == 1


def test_learning_only_evidence_earns_the_qualified_learning_budget():
    """The existing 20-second, 45-second-cap contract, unchanged."""
    observation, _ios, _clock = _observe(
        [_read("LRN", "FWD"), TRUNCATED, _read("FWD", "FWD")]
    )

    assert observation.extension.target_ms == 20000.0
    assert observation.extension.wall_cap_seconds == (
        PVST_SIMULATION_PROGRESS_WALL_CAP_SECONDS
    )
    assert access_forwarding_admission(observation).admitted is True


def test_the_offered_allowance_bounds_the_wall_cap():
    """The caller's allowance is a ceiling the extension never exceeds."""
    # One sample ends the window at 19 s, inside it, so nothing is overrun.
    observation, _ios, _clock = _observe(
        [_read("LIS", "LIS"), _read("LIS", "LIS")],
        extension_seconds=10.0,
        max_samples=1,
    )

    assert observation.extension.wall_cap_seconds == 10.0
    assert observation.extension.converged is False


def test_a_window_read_that_overran_shortens_the_extension():
    """The offer is anchored to the episode start, never to the late read."""
    observation, _ios, _clock = _observe(
        [_read("LIS", "LIS"), TRUNCATED, _read("LIS", "LIS")],
        extension_seconds=59.0,
    )

    # The truncated window read ended at 39 s, nine seconds past the window.
    assert observation.extension.wall_cap_seconds == pytest.approx(50.0)


@pytest.mark.parametrize(
    ("first", "late"),
    [
        (_read("BLK", "LIS"), _read("LIS", "LIS")),
        (_read("LIS", "LIS"), FOREIGN),
        (_read("LIS", "LIS"), _read("BLK", "LIS")),
    ],
    ids=["late_listening_after_blocked", "late_foreign_device", "late_blocked"],
)
def test_only_timely_authoritative_window_reads_seed_an_extension(first, late):
    """A late complete read never seeds one and a contradicting one denies it."""
    observation, _ios, simulation_clock = _observe([first, late])

    assert observation.extension.candidate is False
    assert simulation_clock.reads == 0
    assert access_forwarding_admission(observation).admitted is False


def test_no_read_opens_after_the_simulation_budget_is_spent():
    """The protocol target bounds admission, not only the waiting."""
    observation, ios, _clock = _observe(
        [_read("LIS", "LIS"), TRUNCATED, _read("LIS", "LIS"), _read("FWD", "FWD")],
        simulation={"rate": 2.0},
    )

    assert observation.extension.stop_reason == "simulation_progress_exhausted"
    assert observation.extension.converged is False
    # The forwarding read after the spent budget was never opened.
    assert ios.calls == 3
    assert access_forwarding_admission(observation).admitted is False


def test_the_extension_never_outlives_the_callers_remaining_allowance():
    """An offer larger than the invocation's remaining time is cut to it."""
    observation, _ios, _clock = _observe(
        [_read("LIS", "LIS"), TRUNCATED, _read("FWD", "FWD")],
        remaining_seconds=40.0,
    )

    assert observation.extension.wall_cap_seconds == pytest.approx(1.0)
    assert observation.extension.converged is False
    assert access_forwarding_admission(observation).admitted is False


@pytest.mark.parametrize(
    "terminal",
    [
        _read("BLK", "LIS"),
        _result(_stp_output({PORTS[0]: "LIS"}, vlan=VLAN)),
        _read("LIS", "LIS", forward_delay=20),
        _read("LIS", "LIS", vlan=1),
    ],
    ids=["blocked", "missing_row", "unqualified_forward_delay", "absent_vlan"],
)
def test_ineligible_window_evidence_earns_no_extension(terminal):
    """Only resolved transitional evidence on the qualified timer earns one."""
    observation, ios, simulation_clock = _observe([terminal, TRUNCATED])

    assert observation.extension.candidate is False
    assert simulation_clock.reads == 0
    assert observation.samples == ios.calls == 2
    assert access_forwarding_admission(observation).admitted is False


def test_a_later_failed_read_inside_the_window_denies_the_extension():
    """Only the window's own deadline may cut a later read without cost."""
    observation, _ios, simulation_clock = _observe(
        [_read("LIS", "LIS"), FOREIGN], cost=5.0
    )

    assert observation.extension.candidate is False
    assert simulation_clock.reads == 0
    assert access_forwarding_admission(observation).admitted is False


def test_exhausted_simulation_progress_grants_nothing():
    """A protocol budget spent without forwarding is a network answer."""
    observation, _ios, _clock = _observe(
        [_read("LIS", "LIS"), TRUNCATED, _read("LIS", "LIS")],
        simulation={"rate": 2.0},
    )

    extension = observation.extension
    assert extension.candidate is True and extension.converged is False
    assert extension.stop_reason == "simulation_progress_exhausted"
    assert extension.outcome == "network_measured"
    assert extension.simulation_progress_ms >= 35000.0
    assert observation.deadline_reached is True
    assert observation.episode_end_reason == ("extension:simulation_progress_exhausted")
    assert access_forwarding_admission(observation).admitted is False


@pytest.mark.parametrize(
    ("simulation", "stop_reason"),
    [
        ({"observed": False}, "simulation_clock_unobservable"),
        ({"simulation_mode": True}, "simulation_clock_not_realtime"),
    ],
)
def test_an_unusable_simulation_clock_ends_the_extension(simulation, stop_reason):
    """No trustworthy protocol clock, no extension read at all."""
    observation, ios, _clock = _observe(
        [_read("LIS", "LIS"), TRUNCATED, _read("FWD", "FWD")],
        simulation=simulation,
    )

    extension = observation.extension
    assert extension.candidate is True
    assert extension.authorized is False
    assert extension.stop_reason == stop_reason
    assert extension.outcome == "observer_incomplete"
    assert extension.samples == 0 and ios.calls == 2
    assert access_forwarding_admission(observation).admitted is False


def test_a_forwarding_read_ending_after_the_extension_boundary_is_late():
    """The extension's boundary is as hard as the window's."""
    observation, _ios, _clock = _observe(
        [_read("LIS", "LIS"), TRUNCATED, _read("FWD", "FWD")],
        extension_seconds=15.0,
    )

    assert observation.extension.converged is False
    assert observation.sample_history[-1].phase == "extension"
    assert observation.sample_history[-1].deadline_reached is True
    assert observation.sample_after_deadline is True
    assert access_forwarding_admission(observation).admitted is False


def test_blocking_during_the_extension_ends_it():
    """A port that leaves the transitional path earns no more reads."""
    observation, ios, _clock = _observe(
        [_read("LIS", "LIS"), TRUNCATED, _read("BLK", "LIS"), _read("FWD", "FWD")]
    )

    assert observation.extension.stop_reason == "continuation_unauthorized"
    assert observation.extension.samples == 1 and ios.calls == 3
    assert access_forwarding_admission(observation).admitted is False


def test_the_episode_call_budget_bounds_the_extension():
    """Clock reads and extension samples draw on the one episode allowance."""
    observation, ios, _clock = _observe(
        [_read("LIS", "LIS"), TRUNCATED, _read("FWD", "FWD")],
        episode_calls=2,
    )

    assert observation.extension.candidate is True
    assert observation.extension.converged is False
    assert observation.extension.samples == 0 and ios.calls == 2
    assert observation.episode_budget_exhausted is True
    assert access_forwarding_admission(observation).admitted is False


# -- the product gate -------------------------------------------------------------


def _gated(forwards_at: float | None, **terminal: Any):
    clock = SimulatedClock()
    switch = ControlledSwitchTerminal(clock, forwards_at, **terminal)
    gate = ServiceAccessReadinessGate(
        _plan(),
        _terminal_runtime(switch, clock),
        clock=clock,
        device_names={SWITCH: SWITCH_NAME},
    )
    return gate.decide("http-1"), gate.rows(), switch


def test_the_gate_admits_forwarding_first_seen_inside_an_extension():
    """The real observer and channel: listening until 60 s, then forwarding."""
    decision, rows, switch = _gated(60.0, seconds_per_call=3.0)

    assert decision is not None and decision.admitted is True, rows
    sample = rows[0]["sample"]
    assert sample["dimension"] == DIMENSION_NONE
    assert sample["extension"]["converged"] is True
    assert sample["sample_history"][0]["phase"] == "window"
    assert sample["sample_history"][-1]["phase"] == "extension"
    assert switch.samples[0][1] == "LIS" and switch.samples[-1][1] == "FWD"
    assert switch.samples[-1][0] > READINESS_GROUP_DEADLINE_SECONDS


def test_the_gate_refuses_forwarding_that_never_arrives():
    """Listening throughout: the extension ends on its cap and grants nothing."""
    decision, rows, _switch = _gated(None, seconds_per_call=3.0)

    assert decision is not None and decision.admitted is False
    sample = rows[0]["sample"]
    assert sample["dimension"] == DIMENSION_DEADLINE
    assert sample["extension"]["candidate"] is True
    assert sample["extension"]["converged"] is False
    assert sample["extension"]["stop_reason"] == "wall_clock_safety_cap"


def _two_group_plan():
    """Two access groups on one switch: VLAN 10 and VLAN 20."""
    server_two = "endpoint/hq/default/server/002"
    return _plan(
        actions=[
            _Action("FastEthernet1/1", (PC1,)),
            _Action("FastEthernet1/3", (SERVER,)),
            _Action("FastEthernet1/2", (PC2,), vlan=20),
            _Action("FastEthernet1/4", (server_two,), vlan=20),
        ],
        expectations=[
            _Expectation("http-1", ServiceVerificationKind.HTTP_FETCH, client=PC1),
            _Expectation(
                "http-2",
                ServiceVerificationKind.HTTP_FETCH,
                client=PC2,
                host=server_two,
            ),
        ],
    )


@pytest.mark.parametrize(("seconds", "admitted"), [(85.0, True), (95.0, False)])
def test_a_converged_extension_never_runs_into_a_later_groups_window(seconds, admitted):
    """With another group still owed 30 s, 90 s is the first group's limit."""
    clock = SimulatedClock()
    observer = _LateReporter(clock, cap_over_allowance=-1.0, seconds=seconds)
    gate = ServiceAccessReadinessGate(
        _two_group_plan(), observer, clock=clock, device_names={SWITCH: SWITCH_NAME}
    )

    decision = gate.decide("http-1")

    assert observer.offered == [
        pytest.approx(
            READINESS_TOTAL_BUDGET_SECONDS
            - 2 * READINESS_GROUP_DEADLINE_SECONDS
            - READINESS_GROUP_INTERVAL_SECONDS
        )
    ]
    assert decision is not None and decision.admitted is admitted


def test_an_extension_never_spends_a_later_groups_first_window():
    """Two groups: the first may extend only past the window it still owes."""
    plan = _two_group_plan()
    gate = ServiceAccessReadinessGate(
        plan, _NeverCalled(), clock=SimulatedClock(), device_names={}
    )
    first, second = (item.key for item in plan.requirements)

    assert len(plan.requirements) == 2
    assert gate._extension_allowance(first, 120.0) == pytest.approx(
        120.0
        - READINESS_GROUP_DEADLINE_SECONDS
        - READINESS_GROUP_DEADLINE_SECONDS
        - READINESS_GROUP_INTERVAL_SECONDS
    )
    lone = ServiceAccessReadinessGate(
        _plan(), _NeverCalled(), clock=SimulatedClock(), device_names={}
    )
    (only,) = (item.key for item in _plan().requirements)
    assert lone._extension_allowance(only, 120.0) == LONE_GROUP_ALLOWANCE
    assert lone._extension_allowance(only, 20.0) == 0.0
    assert second != first


class _NeverCalled:
    def observe_access_forwarding(self, *args: Any, **kwargs: Any):
        raise AssertionError("not observed in this test")


def _authoritative(
    device_name: str,
    vlan_id: int,
    interfaces: Any,
    states: dict[str, str],
    bounds: dict[str, Any],
    **fields: Any,
) -> AccessForwardingObservation:
    """One authoritative observation whose last read shows `states`."""
    rows = tuple(
        AccessForwardingRow(interface=item, matches=1, state=states[item], role="Desg")
        for item in interfaces
    )
    evidence = AccessForwardingSampleEvidence(
        elapsed_ms=1_000,
        rows=rows,
        executed=True,
        fresh_output_observed=True,
        output_complete=True,
        observed_device_name=device_name,
        device_identity_provenance="confirmed_unique",
        vlan_present=True,
        channel_calls=4,
        sample_budget_exhausted=False,
        deadline_reached=False,
    )
    return AccessForwardingObservation(
        switch_name=device_name,
        vlan_id=vlan_id,
        requested_interfaces=tuple(interfaces),
        rows=rows,
        executed=True,
        fresh_output_observed=True,
        output_complete=True,
        observed_device_name=device_name,
        device_identity_provenance="confirmed_unique",
        vlan_present=True,
        samples=1,
        sample_history=(evidence,),
        max_samples=bounds["max_samples"],
        deadline_seconds=bounds["deadline_seconds"],
        deadline_scope="group",
        sample_call_budget=bounds["sample_calls"],
        channel_calls=4,
        **fields,
    )


class _PartialThenForwarding:
    """First a non-converged extension with one client port still listening."""

    def __init__(self, clock: SimulatedClock) -> None:
        self.clock = clock
        self.calls: list[tuple[int, tuple[str, ...], float]] = []

    def observe_access_forwarding(self, device_name, vlan_id, interfaces, **bounds):
        first = not self.calls
        self.calls.append((vlan_id, tuple(interfaces), bounds["remaining_seconds"]))
        self.clock.advance(
            89.0
            if first
            else min(bounds["remaining_seconds"], READINESS_GROUP_DEADLINE_SECONDS)
        )
        states = {
            item: "LIS" if first and item == "FastEthernet1/5" else "FWD"
            for item in interfaces
        }
        return _authoritative(
            device_name,
            vlan_id,
            interfaces,
            states,
            bounds,
            deadline_reached=first,
            deadline_cause="episode_window_ended_without_admissible_sample"
            if first
            else "",
        )


def test_a_narrowed_observation_after_an_extension_keeps_a_later_groups_window():
    """Narrowing after a long first episode cannot take another group's window."""
    pc3 = "endpoint/hq/default/user_pc/003"
    server_two = "endpoint/hq/default/server/002"
    plan = _plan(
        actions=[
            _Action("FastEthernet1/1", (PC1,)),
            _Action("FastEthernet1/3", (SERVER,)),
            _Action("FastEthernet1/5", (pc3,)),
            _Action("FastEthernet1/2", (PC2,), vlan=20),
            _Action("FastEthernet1/4", (server_two,), vlan=20),
        ],
        expectations=[
            _Expectation("http-1", ServiceVerificationKind.HTTP_FETCH, client=PC1),
            _Expectation("http-3", ServiceVerificationKind.HTTP_FETCH, client=pc3),
            _Expectation(
                "http-2",
                ServiceVerificationKind.HTTP_FETCH,
                client=PC2,
                host=server_two,
            ),
        ],
    )
    clock = SimulatedClock()
    observer = _PartialThenForwarding(clock)
    gate = ServiceAccessReadinessGate(
        plan, observer, clock=clock, device_names={SWITCH: SWITCH_NAME}
    )

    gate.decide("http-1")
    gate.decide("http-2")

    vlans = [vlan for vlan, _interfaces, _remaining in observer.calls]
    assert vlans == [10, 10, 20], observer.calls
    # The narrowed VLAN 10 episode got only what VLAN 20 was not owed ...
    assert observer.calls[1][2] == pytest.approx(
        READINESS_TOTAL_BUDGET_SECONDS - 89.0 - READINESS_GROUP_DEADLINE_SECONDS
    )
    # ... so VLAN 20 still had its whole first window.
    assert observer.calls[2][2] >= READINESS_GROUP_DEADLINE_SECONDS


class _LateReporter:
    """Report a converged extension after the window, as told to."""

    def __init__(
        self,
        clock: SimulatedClock,
        *,
        cap_over_allowance: float,
        seconds: float = READINESS_GROUP_DEADLINE_SECONDS + 20.0,
    ) -> None:
        self.clock = clock
        self.cap_over_allowance = cap_over_allowance
        self.seconds = seconds
        self.offered: list[float] = []

    def observe_access_forwarding(self, device_name, vlan_id, interfaces, **bounds):
        allowance = bounds["extension_seconds"]
        self.offered.append(allowance)
        self.clock.advance(self.seconds)
        rows = tuple(
            AccessForwardingRow(interface=item, matches=1, state="FWD", role="Desg")
            for item in interfaces
        )
        evidence = AccessForwardingSampleEvidence(
            elapsed_ms=50_000,
            rows=rows,
            executed=True,
            fresh_output_observed=True,
            output_complete=True,
            observed_device_name=device_name,
            device_identity_provenance="confirmed_unique",
            vlan_present=True,
            channel_calls=4,
            sample_budget_exhausted=False,
            deadline_reached=False,
            phase="extension",
        )
        return AccessForwardingObservation(
            switch_name=device_name,
            vlan_id=vlan_id,
            requested_interfaces=tuple(interfaces),
            rows=rows,
            executed=True,
            fresh_output_observed=True,
            output_complete=True,
            observed_device_name=device_name,
            device_identity_provenance="confirmed_unique",
            vlan_present=True,
            samples=1,
            sample_history=(evidence,),
            max_samples=bounds["max_samples"],
            deadline_seconds=bounds["deadline_seconds"],
            deadline_scope="group",
            sample_call_budget=bounds["sample_calls"],
            channel_calls=4,
            episode_end_reason="all_requested_interfaces_observed_forwarding",
            extension=AccessForwardingExtension(
                candidate=True,
                target_ms=35000.0,
                wall_cap_seconds=allowance + self.cap_over_allowance,
                allowance_seconds=allowance,
                authorized=True,
                stop_reason="converged",
                outcome="converged",
                converged=True,
            ),
        )


@pytest.mark.parametrize(
    ("cap_over_allowance", "admitted"),
    [(-1.0, True), (1.0, False)],
    ids=["within_the_offer", "beyond_the_offer"],
)
def test_the_gate_honours_only_an_extension_it_offered(cap_over_allowance, admitted):
    """A post-window result is timely only within the allowance offered."""
    clock = SimulatedClock()
    observer = _LateReporter(clock, cap_over_allowance=cap_over_allowance)
    gate = ServiceAccessReadinessGate(
        _plan(), observer, clock=clock, device_names={SWITCH: SWITCH_NAME}
    )

    decision = gate.decide("http-1")

    assert observer.offered == [LONE_GROUP_ALLOWANCE]
    assert decision is not None and decision.admitted is admitted
    if not admitted:
        assert gate.rows()[0]["sample"]["dimension"] == DIMENSION_DEADLINE


# -- the product wrapper ----------------------------------------------------------


def test_the_product_configuration_wrapper_forwards_the_allowance():
    """The gated E5 runtime is a read path; it must not drop the offer."""

    class Inner:
        def __init__(self) -> None:
            self.bounds: dict[str, Any] = {}

        def observe_access_forwarding(self, device_name, vlan_id, interfaces, **bounds):
            self.bounds = bounds
            return "observed"

    inner = Inner()
    wrapper = _GatedConfigurationRuntime(inner, _MutationGate())

    result = wrapper.observe_access_forwarding(
        "SW",
        VLAN,
        PORTS,
        **{**BOUNDS, "extension_seconds": 42.0},
    )

    assert result == "observed"
    assert inner.bounds["extension_seconds"] == 42.0
