"""Authority for a bounded PVST learning extension across trunk groups."""

from __future__ import annotations

from packet_tracer_mcp.domain.enterprise.models.configuration import (
    VerificationExpectation,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosCommandResult,
    OperationalQueryId,
)
from packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (
    SimulationStateObservation,
)


VLANS = (10, 20, 30)


class _SequenceIos:
    def __init__(self, results: list[IosCommandResult]) -> None:
        self.results = results

    def execute(
        self,
        _device_name: str,
        _query_id: OperationalQueryId,
        **_kwargs: object,
    ) -> IosCommandResult:
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


def _simulation_clock(*sim_times: float):
    values = iter(sim_times)

    def observe() -> SimulationStateObservation:
        return SimulationStateObservation(
            observed=True,
            simulation_mode=False,
            sim_time=next(values),
        )

    return observe


def _expectation(identifier: str, interface: str) -> VerificationExpectation:
    return VerificationExpectation(
        id="verify/trunk/" + identifier,
        action_id="configure/trunk/" + identifier,
        kind=VerificationKind.TRUNK,
        device_id="sw",
        device_name="SW",
        expected={"interface": interface, "allowed_vlans": list(VLANS)},
    )


def _trunk_output(*, old_present: bool, new_forwarding: bool) -> str:
    vlans = ",".join(str(item) for item in VLANS)
    present = (["Gig0/1 on 802.1q trunking 1"] if old_present else []) + [
        "Gig0/2 on 802.1q trunking 1",
    ]
    allowed = (["Gig0/1 " + vlans] if old_present else []) + [
        "Gig0/2 " + vlans,
    ]
    forwarding = (["Gig0/1 " + vlans] if old_present else []) + [
        "Gig0/2 " + (vlans if new_forwarding else "none"),
    ]
    return "\n".join((
        "SW#show interfaces trunk",
        "Port Mode Encapsulation Status Native vlan",
        *present,
        "Port Vlans allowed on trunk",
        *allowed,
        "Port Vlans allowed and active in management domain",
        *allowed,
        "Port Vlans in spanning tree forwarding state and not pruned",
        *forwarding,
        "SW#",
    ))


def _trunk_result(output: str) -> IosCommandResult:
    return IosCommandResult(
        "SW",
        OperationalQueryId.SHOW_INTERFACES_TRUNK,
        True,
        output=output,
        fresh_output_observed=True,
        output_complete=True,
        observed_device_name="SW",
        device_identity_provenance="confirmed_unique",
    )


def _stp_observation(states: dict[str, str]) -> dict[str, object]:
    return {
        "authoritative": True,
        "device_name": "SW",
        "instances": [
            {
                "authoritative": True,
                "vlan_id": vlan,
                "forward_delay_seconds": 15,
                "ports": [
                    {
                        "interface": interface,
                        "row_present": True,
                        "state": state,
                    }
                    for interface, state in states.items()
                ],
            }
            for vlan in VLANS
        ],
    }


def test_old_fwd_row_flicker_does_not_revoke_an_earned_lrn_extension() -> None:
    """Only the boundary LRN cohort decides continuation of its one window.

    LIVE Router0 ``...T165448035171Z-3bb959fc20ac`` entered the extension
    with the new Floor2 chain in LRN. An old Switch4 row then disappeared for
    one sample while its exact PVST port remained FWD. Retroactively adding
    that old expectation to the cohort stopped the 20 s budget after 1021 ms.
    """

    old = _expectation("old", "GigabitEthernet0/1")
    new = _expectation("new", "GigabitEthernet0/2")
    stp_states = iter((
        {"GigabitEthernet0/1": "FWD", "GigabitEthernet0/2": "LIS"},
        {"GigabitEthernet0/1": "FWD", "GigabitEthernet0/2": "LRN"},
        {"GigabitEthernet0/1": "FWD", "GigabitEthernet0/2": "LRN"},
    ))

    def stp(_device_name: str) -> dict[str, object]:
        return _stp_observation(next(stp_states))

    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: None,
        trunk_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
        trunk_transition_observer=stp,
        simulation_time_observer=_simulation_clock(0, 0, 1_000),
    )
    runtime._ios = _SequenceIos([
        _trunk_result(_trunk_output(old_present=True, new_forwarding=False)),
        _trunk_result(_trunk_output(old_present=True, new_forwarding=False)),
        _trunk_result(_trunk_output(old_present=False, new_forwarding=False)),
        _trunk_result(_trunk_output(old_present=True, new_forwarding=True)),
    ])

    results = runtime.verify([old, new])

    diagnostic = [
        {
            "status": item.status.value,
            "candidate": item.convergence.details["learning_extension_candidate"],
            "cohort": item.convergence.details["learning_extension_expectation_ids"],
            "stop": item.convergence.details["learning_extension_stop_reason"],
            "samples": item.convergence.details["learning_extension_sample_count"],
            "progress": item.convergence.details[
                "learning_extension_simulation_progress_ms"
            ],
        }
        for item in results
        if item.convergence is not None
    ]
    assert [item.status for item in results] == [
        ActionExecutionStatus.VERIFIED,
        ActionExecutionStatus.VERIFIED,
    ], diagnostic
    details = results[0].convergence.details
    assert details["learning_extension_authorized"] is True
    assert details["learning_extension_stop_reason"] == "converged"
    assert details["learning_extension_simulation_progress_ms"] == 1_000


def test_old_fwd_row_flicker_cannot_join_the_fresh_boundary_cohort() -> None:
    """The refresh may shrink the captured LRN cohort, never grow it.

    LIVE Router0 ``...T182313631883Z-83fa738dee54`` captured every new
    Floor3 trunk as exact LRN.  Both old Switch4 trunks were already FWD at
    the end of the ordinary window, then their CLI rows flickered absent only
    in the post-capture refresh.  That later flicker must not retroactively
    enter the captured pending set and veto its one governed extension.
    """

    old = _expectation("old", "GigabitEthernet0/1")
    new = _expectation("new", "GigabitEthernet0/2")

    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: None,
        trunk_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
        trunk_transition_observer=lambda _device_name: _stp_observation({
            "GigabitEthernet0/1": "FWD",
            "GigabitEthernet0/2": "LRN",
        }),
        simulation_time_observer=_simulation_clock(0, 0),
    )
    runtime._ios = _SequenceIos([
        _trunk_result(_trunk_output(old_present=True, new_forwarding=False)),
        _trunk_result(_trunk_output(old_present=False, new_forwarding=False)),
        _trunk_result(_trunk_output(old_present=True, new_forwarding=True)),
    ])

    results = runtime.verify([old, new])

    assert [item.status for item in results] == [
        ActionExecutionStatus.VERIFIED,
        ActionExecutionStatus.VERIFIED,
    ]
    details = results[0].convergence.details
    assert details["learning_extension_candidate"] is True
    assert details["learning_extension_expectation_ids"] == [new.id]
    assert details["learning_extension_authorized"] is True
    assert details["learning_extension_stop_reason"] == "converged"


def test_lrn_cohort_progressing_to_fwd_keeps_its_earned_observation_window() -> None:
    """FWD may continue a window earned at LRN, but cannot verify trunk data.

    Floor3 ``...T011017280517Z-008da3f6c4c9`` entered its one extension from
    an exact LRN boundary.  On the first extension sample STP advanced to FWD
    while the independent trunk table still reported no forwarding VLANs.
    Revoking the already-earned window there prevented the next bounded SHOW
    from observing the trunk table catch up.
    """

    trunk = _expectation("floor3", "GigabitEthernet0/2")
    nonforwarding = _trunk_output(old_present=True, new_forwarding=False)
    forwarding = _trunk_output(old_present=True, new_forwarding=True)
    stp_states = iter(("LIS", "LRN", "FWD", "FWD"))

    def stp(_device_name: str) -> dict[str, object]:
        state = next(stp_states)
        return _stp_observation({
            "GigabitEthernet0/1": state,
            "GigabitEthernet0/2": state,
        })

    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: None,
        trunk_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
        trunk_transition_observer=stp,
        simulation_time_observer=_simulation_clock(0, 0, 1_000),
    )
    runtime._ios = _SequenceIos([
        _trunk_result(nonforwarding),
        _trunk_result(nonforwarding),
        _trunk_result(nonforwarding),
        _trunk_result(forwarding),
    ])

    result = runtime.verify([trunk])[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    details = result.convergence.details
    assert details["learning_extension_candidate"] is True
    assert details["learning_extension_authorized"] is True
    assert details["learning_extension_stop_reason"] == "converged"
    assert details["learning_extension_sample_count"] == 2
    assert details["learning_boundary_stp"]["instances"][0]["ports"][0][
        "state"
    ] == "FWD"


def test_boundary_refresh_cannot_revoke_verified_trunk_outside_its_cohort() -> None:
    """A scoped refresh may resolve its pending trunk, not reread old devices.

    Floor2 LIVE ``...T134138442128Z-814d25880d87`` ended its ordinary window
    with both Switch4 trunks VERIFIED and one different trunk pending. The
    boundary refresh resolved that one trunk, but an unrelated Switch4 read
    landed exactly on a buffer rollover and replaced both earned rows with
    UNOBSERVABLE. The refresh is authorized only for the frozen pending cohort.
    """

    old = _expectation("old", "GigabitEthernet0/1").model_copy(update={
        "device_id": "old",
        "device_name": "A-OLD",
    })
    new = _expectation("new", "GigabitEthernet0/2").model_copy(update={
        "device_id": "new",
        "device_name": "B-NEW",
    })

    def result(device_name: str, output: str) -> IosCommandResult:
        return IosCommandResult(
            device_name,
            OperationalQueryId.SHOW_INTERFACES_TRUNK,
            True,
            output=output,
            fresh_output_observed=True,
            output_complete=True,
            observed_device_name=device_name,
            device_identity_provenance="confirmed_unique",
        )

    class BoundaryRefreshIos:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.by_device = {"A-OLD": 0, "B-NEW": 0}

        def execute(
            self,
            device_name: str,
            _query_id: OperationalQueryId,
            **_kwargs: object,
        ) -> IosCommandResult:
            self.calls.append(device_name)
            self.by_device[device_name] += 1
            if device_name == "A-OLD":
                if self.by_device[device_name] == 1:
                    return result(
                        device_name,
                        _trunk_output(old_present=True, new_forwarding=True),
                    )
                return IosCommandResult(
                    device_name,
                    OperationalQueryId.SHOW_INTERFACES_TRUNK,
                    False,
                    failure_reason=(
                        "No fresh current-command output window was observed."
                    ),
                    window_strategy="rolled_unattributable",
                    observed_device_name=device_name,
                    device_identity_provenance="confirmed_unique",
                )
            return result(
                device_name,
                _trunk_output(
                    old_present=False,
                    new_forwarding=self.by_device[device_name] > 1,
                ),
            )

    def stp(device_name: str) -> dict[str, object]:
        observation = _stp_observation({
            "GigabitEthernet0/1": "FWD",
            "GigabitEthernet0/2": (
                "LRN" if device_name == "B-NEW" else "FWD"
            ),
        })
        observation["device_name"] = device_name
        return observation

    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: None,
        trunk_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
        trunk_transition_observer=stp,
    )
    ios = BoundaryRefreshIos()
    runtime._ios = ios

    results = runtime.verify([old, new])
    diagnostic = {
        "calls": ios.calls,
        "results": [
            {
                "status": item.status.value,
                "details": item.convergence.details,
            }
            for item in results
            if item.convergence is not None
        ],
    }

    assert [item.status for item in results] == [
        ActionExecutionStatus.VERIFIED,
        ActionExecutionStatus.VERIFIED,
    ], diagnostic
    assert ios.calls == ["A-OLD", "B-NEW", "B-NEW"]
    details = results[0].convergence.details
    assert details["learning_boundary_expectation_ids"] == [new.id]
    assert details["learning_boundary_refresh_complete"] is True
