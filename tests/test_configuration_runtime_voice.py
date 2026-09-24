"""Focused Voice STP observation tests extracted from the legacy E5 suite."""

from __future__ import annotations

import itertools

from test_configuration_runtime import (
    _FirstThenFailingIos,
    _SequenceIos,
    _simulation_clock,
)

from packet_tracer_mcp.domain.enterprise.models.configuration import (
    VerificationExpectation,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from packet_tracer_mcp.infrastructure.execution import (
    enterprise_configuration_runtime as configuration_runtime_module,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
    voice_access_learning_extension_is_authorized,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosCommandResult,
    OperationalQueryId,
)
from packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (
    SimulationStateObservation,
)


def _voice_stp_output(state: str) -> str:
    return "\n".join(
        (
            "SW#show spanning-tree",
            "VLAN0020",
            "  Spanning tree enabled protocol ieee",
            "  Root ID    Priority    32788",
            "             Address     0001.4392.0108",
            "             Cost        4",
            "             Port        25(GigabitEthernet0/1)",
            "             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec",
            "",
            "  Bridge ID  Priority    32788  (priority 32768 sys-id-ext 20)",
            "             Address     0030.A3A1.89E8",
            "             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec",
            "             Aging Time  20",
            "",
            "Interface        Role Sts Cost      Prio.Nbr Type",
            "---------------- ---- --- --------- -------- --------------------------------",
            f"Fa0/1            Desg {state} 19        128.1    P2p",
            "SW#",
        )
    )


def _voice_stp_group_output(states: dict[str, str]) -> str:
    rows = [
        f"{interface:<16} Desg {state:<3} 19        128.1    P2p"
        for interface, state in states.items()
    ]
    return "\n".join(
        (
            "SW#show spanning-tree",
            "VLAN0020",
            "  Spanning tree enabled protocol ieee",
            "  Root ID    Priority    32788",
            "             Address     0001.4392.0108",
            "             Cost        4",
            "             Port        25(GigabitEthernet0/1)",
            "             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec",
            "",
            "  Bridge ID  Priority    32788  (priority 32768 sys-id-ext 20)",
            "             Address     0030.A3A1.89E8",
            "             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec",
            "             Aging Time  20",
            "",
            "Interface        Role Sts Cost      Prio.Nbr Type",
            "---------------- ---- --- --------- -------- --------------------------------",
            *rows,
            "SW#",
        )
    )


def test_voice_access_forwarding_waits_on_one_registered_stp_query():
    """Verify voice access forwarding waits on one registered stp query."""
    expectation = VerificationExpectation(
        id="verify/voice-access",
        action_id="access/voice",
        kind=VerificationKind.ACCESS_PORT,
        device_id="sw",
        device_name="SW",
        expected={
            "interface": "FastEthernet0/1",
            "vlan_id": 10,
            "voice_vlan_id": 20,
        },
    )
    ios = _SequenceIos(
        [
            IosCommandResult(
                "SW",
                OperationalQueryId.SHOW_SPANNING_TREE,
                True,
                output=_voice_stp_output("LIS"),
                fresh_output_observed=True,
                output_complete=True,
                observed_device_name="SW",
                device_identity_provenance="confirmed_unique",
            ),
            IosCommandResult(
                "SW",
                OperationalQueryId.SHOW_SPANNING_TREE,
                True,
                output=_voice_stp_output("FWD"),
                fresh_output_observed=True,
                output_complete=True,
                observed_device_name="SW",
                device_identity_provenance="confirmed_unique",
            ),
        ]
    )
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: None,
        trunk_timeout_seconds=1.0,
        convergence_interval_seconds=0.0,
    )
    runtime._ios = ios

    result = runtime.wait_for_voice_access_forwarding([expectation])[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fields["voice_forwarding"] is (FieldVerificationStatus.VERIFIED)
    assert len(ios.calls) == 2
    assert {query_id for _, query_id, _ in ios.calls} == {
        OperationalQueryId.SHOW_SPANNING_TREE
    }


def _voice_expectation():
    return VerificationExpectation(
        id="verify/voice-access/learning",
        action_id="access/voice/learning",
        kind=VerificationKind.ACCESS_PORT,
        device_id="sw",
        device_name="SW",
        expected={
            "interface": "FastEthernet0/1",
            "vlan_id": 10,
            "voice_vlan_id": 20,
        },
    )


def _voice_stp_result(state, *, observed_device_name="SW"):
    return IosCommandResult(
        "SW",
        OperationalQueryId.SHOW_SPANNING_TREE,
        True,
        output=_voice_stp_output(state),
        fresh_output_observed=True,
        output_complete=True,
        observed_device_name=observed_device_name,
        device_identity_provenance="confirmed_unique",
    )


def _voice_runtime(
    ios,
    *,
    trunk_timeout_seconds=0.0,
    simulation_time_observer=None,
):
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: None,
        trunk_timeout_seconds=trunk_timeout_seconds,
        convergence_interval_seconds=0.0,
        simulation_time_observer=(
            simulation_time_observer or _simulation_clock(0, 20_000)
        ),
    )
    runtime._ios = ios
    return runtime


def test_voice_access_forwarding_extends_once_from_learning_to_forwarding():
    """Verify voice access forwarding extends once from learning to forwarding."""
    ios = _SequenceIos(
        [
            _voice_stp_result("LRN"),
            _voice_stp_result("LRN"),
            _voice_stp_result("LRN"),
            _voice_stp_result("FWD"),
        ]
    )
    runtime = _voice_runtime(
        ios,
        simulation_time_observer=_simulation_clock(0, 0, 10_000, 20_000),
    )

    result = runtime.wait_for_voice_access_forwarding([_voice_expectation()])[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert len(ios.calls) == 4
    assert result.convergence is not None
    assert result.convergence.details["initial_sample_count"] == 1
    assert result.convergence.details["learning_extension_authorized"] is True
    assert result.convergence.details["learning_extension_seconds"] == 20.0
    assert result.convergence.details["learning_extension_clock"] == (
        "packet_tracer_simulation_time"
    )
    assert (
        result.convergence.details["learning_extension_simulation_progress_ms"]
        == 20_000
    )
    assert result.convergence.details["learning_extension_sample_count"] == 3
    assert result.convergence.details["sample_count"] == 4
    assert result.convergence.details["terminal_failure_dimension"] == "NONE"


def test_voice_access_forwarding_buys_exactly_one_protocol_sized_window():
    """LRN gets one 20 s PT-simulation budget, then fails closed."""
    observed_sim_times = iter((0, 0, 20_000))
    simulation_reads = []

    def observe_simulation_time():
        sim_time = next(observed_sim_times)
        simulation_reads.append(sim_time)
        return SimulationStateObservation(
            observed=True,
            simulation_mode=False,
            sim_time=sim_time,
        )

    ios = _SequenceIos([_voice_stp_result("LRN")])
    runtime = _voice_runtime(
        ios,
        simulation_time_observer=observe_simulation_time,
    )

    result = runtime.wait_for_voice_access_forwarding([_voice_expectation()])[0]

    assert simulation_reads == [0, 0, 20_000]
    assert len(ios.calls) == 3, "one initial read plus one bounded extension"
    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.convergence is not None
    assert result.convergence.details["learning_extension_authorized"] is True
    assert result.convergence.details["learning_extension_sample_count"] == 2
    assert result.convergence.details["learning_extension_stop_reason"] == (
        "simulation_progress_exhausted"
    )
    assert result.convergence.details["terminal_failure_dimension"] == (
        "NON_FORWARDING"
    )


def test_voice_access_forwarding_refuses_to_extend_a_failed_terminal_round(
    monkeypatch,
):
    """A surviving earlier LRN snapshot is not terminal evidence."""
    real_waiter = configuration_runtime_module.StateConvergenceWaiter
    # Exactly two initial rounds: the first observes LRN, the second loses the
    # channel. A scripted clock keeps that split off wall-clock timing.
    scripted = [0.0, 0.0, 5.0, 5.0]
    later = itertools.count(1000.0, 1000.0)

    def clock() -> float:
        # Strictly increasing once the script runs out, so a waiter this test
        # does not expect at all still terminates instead of spinning.
        return scripted.pop(0) if scripted else next(later)

    class TwoRoundWaiter:
        def __init__(
            self,
            inspect,
            *,
            timeout_seconds: float,
            interval_seconds: float,
        ) -> None:
            self._waiter = real_waiter(
                inspect,
                timeout_seconds=1.0,
                interval_seconds=0,
                clock=clock,
            )

        def wait(self):
            return self._waiter.wait()

    monkeypatch.setattr(
        configuration_runtime_module,
        "StateConvergenceWaiter",
        TwoRoundWaiter,
    )
    ios = _FirstThenFailingIos(_voice_stp_result("LRN"))
    runtime = _voice_runtime(ios)

    result = runtime.wait_for_voice_access_forwarding([_voice_expectation()])[0]

    assert len(ios.calls) == 2, "the terminal round is the one that failed"
    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.convergence is not None
    assert result.convergence.details["initial_sample_count"] == 2
    assert result.convergence.details["learning_extension_authorized"] is False
    assert result.convergence.details["learning_extension_sample_count"] == 0


def test_voice_access_forwarding_refuses_to_extend_unattributed_evidence():
    """Verify voice access forwarding refuses to extend unattributed evidence."""
    ios = _SequenceIos([_voice_stp_result("LRN", observed_device_name="")])
    runtime = _voice_runtime(ios)

    result = runtime.wait_for_voice_access_forwarding([_voice_expectation()])[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert len(ios.calls) == 1, "an unattributed sample must not buy a window"
    assert result.convergence is not None
    assert result.convergence.details["learning_extension_authorized"] is False


def test_voice_access_forwarding_rejects_wrong_device_terminal_fwd():
    """Verify voice access forwarding rejects wrong device terminal fwd."""
    simulation_reads = []
    ios = _SequenceIos(
        [
            _voice_stp_result("FWD", observed_device_name="OTHER"),
        ]
    )
    runtime = _voice_runtime(
        ios,
        simulation_time_observer=lambda: simulation_reads.append(True),
    )

    result = runtime.wait_for_voice_access_forwarding([_voice_expectation()])[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.fresh_evidence is False
    assert simulation_reads == []
    assert result.convergence is not None
    assert result.convergence.details["terminal_failure_dimension"] == "IDENTITY"


def test_voice_access_forwarding_refuses_an_unqualified_forward_delay():
    """LRN authority alone never buys a window of unmeasured protocol length."""
    qualified = _voice_stp_output("LRN")
    for label, output in (
        ("unqualified", qualified.replace("Delay 15 sec", "Delay 4 sec")),
        ("ambiguous", qualified.replace("Delay 15 sec", "Delay 4 sec", 1)),
        (
            "absent",
            "\n".join(
                line for line in qualified.splitlines() if "Forward Delay" not in line
            ),
        ),
    ):
        simulation_reads = []
        ios = _SequenceIos(
            [
                IosCommandResult(
                    "SW",
                    OperationalQueryId.SHOW_SPANNING_TREE,
                    True,
                    output=output,
                    fresh_output_observed=True,
                    output_complete=True,
                    observed_device_name="SW",
                    device_identity_provenance="confirmed_unique",
                ),
            ]
        )
        runtime = _voice_runtime(
            ios,
            simulation_time_observer=lambda reads=simulation_reads: reads.append(True),
        )

        result = runtime.wait_for_voice_access_forwarding(
            [_voice_expectation()],
        )[0]

        assert result.status is ActionExecutionStatus.UNOBSERVABLE, label
        assert simulation_reads == [], label
        assert len(ios.calls) == 1, label
        details = result.convergence.details
        assert details["observed_forward_delay_seconds"] != 15, label
        # The LRN authority itself still held; only the budget was unqualified.
        assert details["learning_extension_candidate"] is True, label
        assert details["learning_extension_authorized"] is False, label
        assert details["learning_extension_seconds"] == 0.0, label
        assert details["learning_extension_stop_reason"] == ("not_authorized"), label
        assert details["terminal_failure_dimension"] == "NON_FORWARDING", label


def _voice_learning_observation(states, **overrides):
    observation = {
        "authoritative": True,
        "vlan_present": True,
        "observed_device_name": "SW",
        "sample_round": 7,
        "states": states,
    }
    observation.update(overrides)
    return observation


def _authorizes(observation, *, expected_count=1, device_name="SW"):
    return voice_access_learning_extension_is_authorized(
        observation,
        device_name=device_name,
        expected_count=expected_count,
        terminal_sample_round=7,
    )


def test_voice_learning_extension_authorizes_only_terminal_pending_lrn():
    """Verify voice learning extension authorizes only terminal pending lrn."""
    assert _authorizes(_voice_learning_observation({"a": "LRN"}))
    assert _authorizes(
        _voice_learning_observation({"a": "LRN", "b": "FWD"}),
        expected_count=2,
    )


def test_voice_learning_extension_fails_closed_outside_that_evidence():
    """Verify voice learning extension fails closed outside that evidence."""
    refused = {
        "listening": _voice_learning_observation({"a": "LIS"}),
        "blocking": _voice_learning_observation({"a": "BLK"}),
        "ambiguous_state": _voice_learning_observation({"a": ""}),
        "mixed_non_learning": (_voice_learning_observation({"a": "LRN", "b": "LIS"})),
        "stale_round": _voice_learning_observation(
            {"a": "LRN"},
            sample_round=6,
        ),
        "unobservable": _voice_learning_observation(
            {"a": "LRN"},
            authoritative=False,
        ),
        "vlan_instance_absent": _voice_learning_observation(
            {"a": "LRN"},
            vlan_present=False,
        ),
        "other_device": _voice_learning_observation(
            {"a": "LRN"},
            observed_device_name="OTHER",
        ),
        "unattributed": _voice_learning_observation(
            {"a": "LRN"},
            observed_device_name="",
        ),
        "untyped_states": _voice_learning_observation("LRN"),
        "nothing_pending": _voice_learning_observation({"a": "FWD"}),
    }
    assert {
        name: _authorizes(observation) for name, observation in refused.items()
    } == {name: False for name in refused}

    # A missing row is never covered by a shorter observation.
    assert not _authorizes(
        _voice_learning_observation({"a": "LRN"}),
        expected_count=2,
    )
    assert not _authorizes(
        _voice_learning_observation({"a": "LRN"}),
        expected_count=0,
    )
    assert not _authorizes(
        _voice_learning_observation({"a": "LRN"}),
        device_name="",
    )


def test_voice_access_forwarding_retains_one_structured_group_observation():
    """Verify voice access forwarding retains one structured group observation."""
    expectations = [
        VerificationExpectation(
            id=f"verify/voice-access/{index}",
            action_id=f"access/voice/{index}",
            kind=VerificationKind.ACCESS_PORT,
            device_id="sw",
            device_name="SW",
            expected={
                "interface": f"FastEthernet0/{index}",
                "vlan_id": 10,
                "voice_vlan_id": 20,
            },
        )
        for index in (1, 2)
    ]
    ios = _SequenceIos(
        [
            IosCommandResult(
                "SW",
                OperationalQueryId.SHOW_SPANNING_TREE,
                True,
                output=_voice_stp_group_output({"Fa0/1": "LIS", "Fa0/2": "LRN"}),
                fresh_output_observed=True,
                output_complete=True,
                observed_device_name="SW",
                device_identity_provenance="confirmed_unique",
            ),
            IosCommandResult(
                "SW",
                OperationalQueryId.SHOW_SPANNING_TREE,
                True,
                output=_voice_stp_group_output({"Fa0/1": "FWD", "Fa0/2": "FWD"}),
                fresh_output_observed=True,
                output_complete=True,
                observed_device_name="SW",
                device_identity_provenance="confirmed_unique",
            ),
        ]
    )
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: None,
        trunk_timeout_seconds=1.0,
        convergence_interval_seconds=0.0,
    )
    runtime._ios = ios

    results = runtime.wait_for_voice_access_forwarding(expectations)

    assert len(ios.calls) == 2, "one STP sample must classify the whole group"
    assert all(item.convergence is not None for item in results)
    details = [item.convergence.details for item in results]
    assert details[0] == details[1]
    assert details[0] == {
        "kind": "voice_access_forwarding_group",
        "switch": "SW",
        "voice_vlan_id": 20,
        "expected_interfaces": ["FastEthernet0/1", "FastEthernet0/2"],
        "verified_fwd_interfaces": ["FastEthernet0/1", "FastEthernet0/2"],
        "missing_interfaces": [],
        "non_fwd_interfaces": {},
        "initial_sample_count": 2,
        "terminal_sample_round": 2,
        "observed_forward_delay_seconds": 15,
        "learning_extension_candidate": False,
        "learning_extension_authorized": False,
        "learning_extension_seconds": 0.0,
        "learning_extension_clock": "none",
        "learning_extension_max_wall_seconds": 0.0,
        "learning_extension_simulation_start_ms": None,
        "learning_extension_simulation_end_ms": None,
        "learning_extension_simulation_progress_ms": 0.0,
        "learning_extension_clock_samples": 0,
        "learning_extension_stop_reason": "not_authorized",
        "learning_extension_outcome": "network_measured",
        "learning_extension_failure_reason": "",
        "learning_extension_sample_count": 0,
        "sample_count": 2,
        "elapsed_ms": results[0].convergence.elapsed_ms,
        "terminal_authority": "AUTHORITATIVE",
        "terminal_failure_dimension": "NONE",
    }


def test_voice_access_forwarding_names_incomplete_terminal_evidence():
    """Verify voice access forwarding names incomplete terminal evidence."""
    expectation = VerificationExpectation(
        id="verify/voice-access/incomplete",
        action_id="access/voice/incomplete",
        kind=VerificationKind.ACCESS_PORT,
        device_id="sw",
        device_name="SW",
        expected={
            "interface": "FastEthernet0/1",
            "vlan_id": 10,
            "voice_vlan_id": 20,
        },
    )
    ios = _SequenceIos(
        [
            IosCommandResult(
                "SW",
                OperationalQueryId.SHOW_SPANNING_TREE,
                True,
                output=_voice_stp_output("FWD") + "\n--More--",
                fresh_output_observed=True,
                output_complete=False,
                truncated_by_pager=True,
                device_identity_provenance="confirmed_unique",
            )
        ]
    )
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: None,
        trunk_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )
    runtime._ios = ios

    result = runtime.wait_for_voice_access_forwarding([expectation])[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.convergence is not None
    assert result.convergence.details["terminal_authority"] == "UNOBSERVABLE"
    assert result.convergence.details["terminal_failure_dimension"] == "COMPLETENESS"
    assert result.convergence.details["missing_interfaces"] == [
        "FastEthernet0/1",
    ]
