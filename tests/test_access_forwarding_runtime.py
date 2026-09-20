"""The neutral access-forwarding observer on the real runtime (integration).

It reuses the registered `show spanning-tree` dispatch, the maintained parser
and the existing freshness/completeness/identity contract. What it does not
reuse is Voice semantics: no `voice_vlan_id` input, no `voice_forwarding`
field, and none of the PVST learning extension's simulation-time window.

The Voice observer's own behaviour is proven unchanged here as well, because
both now read the same extracted authority core.
"""

from __future__ import annotations

import pytest

from packet_tracer_mcp.domain.enterprise.models.configuration import (
    VerificationExpectation,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from packet_tracer_mcp.domain.enterprise.services.access_forwarding import (
    access_forwarding_admission,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    ACCESS_FORWARDING_MAX_SAMPLES,
    PacketTracerEnterpriseConfigurationRuntime,
    spanning_tree_sample_is_authoritative,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosCommandResult,
    OperationalQueryId,
)

PORTS = ("FastEthernet0/1", "FastEthernet0/2")


def _stp_output(states: dict[str, str], vlan: int = 1) -> str:
    rows = [
        f"{interface.replace('FastEthernet', 'Fa'):<16} Desg {state:<3} "
        "19        128.1    P2p"
        for interface, state in states.items()
    ]
    return "\n".join(
        [
            "SW#show spanning-tree",
            f"VLAN{vlan:04d}",
            "  Spanning tree enabled protocol ieee",
            "  Root ID    Priority    32769",
            "             Address     0001.4392.0108",
            "             This bridge is the root",
            "             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec",
            "",
            "  Bridge ID  Priority    32769  (priority 32768 sys-id-ext 1)",
            "             Address     0030.A3A1.89E8",
            "             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec",
            "             Aging Time  20",
            "",
            "Interface        Role Sts Cost      Prio.Nbr Type",
            "---------------- ---- --- --------- -------- ----------------------",
            *rows,
            "SW#",
        ]
    )


def _result(output: str, **overrides) -> IosCommandResult:
    values = {
        "executed": True,
        "output": output,
        "fresh_output_observed": True,
        "output_complete": True,
        "observed_device_name": "SW",
        "device_identity_provenance": "confirmed_unique",
    }
    values.update(overrides)
    executed = values.pop("executed")
    return IosCommandResult(
        "SW", OperationalQueryId.SHOW_SPANNING_TREE, executed, **values
    )


class _SequenceIos:
    """Answer each `execute` from a fixed sequence, and record every call."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def execute(self, device_name, query_id, **kwargs):
        self.calls.append((device_name, query_id, kwargs))
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


class _Clock:
    """A monotonic clock that only moves when the observer sleeps."""

    def __init__(self, step: float = 0.0) -> None:
        self.now = 0.0
        self.step = step
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += max(seconds, self.step)


def _runtime(ios, clock: _Clock):
    dispatched: list[str] = []
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda payload: dispatched.append(payload) or True,
        send_and_wait=lambda _payload, _timeout: None,
        clock=clock,
        sleeper=clock.sleep,
    )
    # The neutral observation dispatches through its own executor, the
    # one bound to the counting channel, so that is the seam a
    # sampling-rule test replaces. `_ios` stays wired for every other
    # query this runtime answers.
    runtime._ios = ios
    runtime._forwarding_ios = ios
    return runtime, dispatched


def test_one_admissible_sample_ends_the_bounded_loop(monkeypatch):
    """The first sample where every requested port forwards is the last one."""
    clock = _Clock()
    ios = _SequenceIos([_result(_stp_output(dict.fromkeys(PORTS, "FWD")))])
    runtime, dispatched = _runtime(ios, clock)

    observation = runtime.observe_access_forwarding("SW", 1, PORTS)

    assert observation.samples == 1
    assert len(ios.calls) == 1
    assert {query for _, query, _ in ios.calls} == {
        OperationalQueryId.SHOW_SPANNING_TREE
    }
    assert access_forwarding_admission(observation).admitted is True
    # Nothing was configured to make it converge.
    assert dispatched == [] and clock.sleeps == []


def test_a_non_forwarding_port_is_resampled_up_to_the_hard_ceiling():
    """Sampling is a bound, not a retry budget, and it stops on its own."""
    clock = _Clock()
    ios = _SequenceIos([_result(_stp_output({PORTS[0]: "FWD", PORTS[1]: "LRN"}))])
    runtime, dispatched = _runtime(ios, clock)

    observation = runtime.observe_access_forwarding("SW", 1, PORTS)

    assert observation.samples == ACCESS_FORWARDING_MAX_SAMPLES == 3
    assert len(clock.sleeps) == ACCESS_FORWARDING_MAX_SAMPLES - 1
    admission = access_forwarding_admission(observation)
    assert (admission.admitted, admission.dimension) == (False, "NON_FORWARDING")
    assert dispatched == []


def test_a_port_that_comes_up_between_samples_is_observed_when_it_does():
    """Convergence is observed, never assumed from an earlier sample."""
    clock = _Clock()
    ios = _SequenceIos(
        [
            _result(_stp_output({PORTS[0]: "FWD", PORTS[1]: "LRN"})),
            _result(_stp_output(dict.fromkeys(PORTS, "FWD"))),
        ]
    )
    runtime, _dispatched = _runtime(ios, clock)

    observation = runtime.observe_access_forwarding("SW", 1, PORTS)

    assert observation.samples == 2
    assert access_forwarding_admission(observation).admitted is True


def test_a_deadline_that_passes_stops_the_loop_and_grants_nothing():
    """Wall-clock time is its own bound, separate from the sample count."""
    clock = _Clock(step=100.0)
    ios = _SequenceIos([_result(_stp_output({PORTS[0]: "FWD", PORTS[1]: "LRN"}))])
    runtime, _dispatched = _runtime(ios, clock)

    observation = runtime.observe_access_forwarding(
        "SW", 1, PORTS, deadline_seconds=1.0
    )

    assert observation.deadline_reached is True
    assert observation.samples < ACCESS_FORWARDING_MAX_SAMPLES
    assert access_forwarding_admission(observation).admitted is False


def test_zero_samples_is_a_hard_ceiling_and_dispatches_nothing():
    """A caller that grants no sample cannot be silently widened to one."""
    clock = _Clock()
    ios = _SequenceIos([_result(_stp_output(dict.fromkeys(PORTS, "FWD")))])
    runtime, _dispatched = _runtime(ios, clock)

    observation = runtime.observe_access_forwarding("SW", 1, PORTS, max_samples=0)

    assert observation.samples == 0
    assert observation.max_samples == 0
    assert ios.calls == []
    assert access_forwarding_admission(observation).dimension == "NOT_ATTEMPTED"


@pytest.mark.parametrize(
    "bounds",
    [
        {"max_samples": -1},
        {"max_samples": True},
        {"deadline_seconds": -1.0},
        {"deadline_seconds": float("nan")},
        {"interval_seconds": -1.0},
        {"interval_seconds": float("inf")},
    ],
)
def test_invalid_sampling_bounds_refuse_before_the_registered_query(bounds):
    """Negative, non-finite and boolean limits are not hard numeric bounds."""
    clock = _Clock()
    ios = _SequenceIos([_result(_stp_output(dict.fromkeys(PORTS, "FWD")))])
    runtime, _dispatched = _runtime(ios, clock)

    with pytest.raises(ValueError, match="access forwarding"):
        runtime.observe_access_forwarding("SW", 1, PORTS, **bounds)

    assert ios.calls == []


def test_a_sample_returning_exactly_at_the_deadline_is_late_evidence():
    """The closed deadline boundary grants nothing, even for FWD rows."""
    clock = _Clock()

    class _DeadlineIos(_SequenceIos):
        def execute(self, device_name, query_id, **kwargs):
            result = super().execute(device_name, query_id, **kwargs)
            clock.now = 1.0
            return result

    ios = _DeadlineIos([_result(_stp_output(dict.fromkeys(PORTS, "FWD")))])
    runtime, _dispatched = _runtime(ios, clock)

    observation = runtime.observe_access_forwarding(
        "SW", 1, PORTS, deadline_seconds=1.0
    )

    assert observation.deadline_reached is True
    assert access_forwarding_admission(observation).dimension == "DEADLINE"


@pytest.mark.parametrize(
    "overrides",
    [
        {"executed": False},
        {"fresh_output_observed": False},
        {"output_complete": False},
        {"observed_device_name": "OTHER"},
        {"device_identity_provenance": "ambiguous"},
    ],
)
def test_a_sample_that_is_not_authoritative_is_never_parsed(overrides):
    """No row of an unattributed window means anything, so none is read."""
    clock = _Clock()
    ios = _SequenceIos([_result(_stp_output(dict.fromkeys(PORTS, "FWD")), **overrides)])
    runtime, _dispatched = _runtime(ios, clock)

    observation = runtime.observe_access_forwarding("SW", 1, PORTS)

    assert observation.rows == ()
    assert observation.vlan_present is False
    assert access_forwarding_admission(observation).admitted is False


def test_the_wrong_vlan_instance_is_absent_not_forwarding():
    """A port forwarding in VLAN 20 says nothing about VLAN 1."""
    clock = _Clock()
    ios = _SequenceIos([_result(_stp_output(dict.fromkeys(PORTS, "FWD"), vlan=20))])
    runtime, _dispatched = _runtime(ios, clock)

    observation = runtime.observe_access_forwarding("SW", 1, PORTS)

    assert observation.vlan_present is False
    assert access_forwarding_admission(observation).dimension == "VLAN_INSTANCE"


def test_the_neutral_observation_carries_no_voice_semantics():
    """Ordinary service clients get no `voice_vlan_id` and no voice field."""
    clock = _Clock()
    ios = _SequenceIos([_result(_stp_output(dict.fromkeys(PORTS, "FWD")))])
    runtime, _dispatched = _runtime(ios, clock)

    observation = runtime.observe_access_forwarding("SW", 1, PORTS)

    fields = set(vars(observation))
    assert not any("voice" in item for item in fields)
    assert observation.vlan_id == 1


def test_the_voice_observer_keeps_its_own_contract(monkeypatch):
    """The extracted core changed no Voice behaviour (noninterference)."""
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
    ios = _SequenceIos([_result(_stp_output({"FastEthernet0/1": "FWD"}, vlan=20))])
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
    assert result.fields["voice_forwarding"] is FieldVerificationStatus.VERIFIED
    assert result.evidence_method == "fresh_show_spanning_tree_voice_access"
    assert result.convergence.details["kind"] == "voice_access_forwarding_group"
    assert result.convergence.details["voice_vlan_id"] == 20


def test_both_observers_decide_authority_with_the_one_extracted_core():
    """One predicate, so the two paths cannot drift about the same sample."""
    fresh = _result(_stp_output(dict.fromkeys(PORTS, "FWD")))
    stale = _result(
        _stp_output(dict.fromkeys(PORTS, "FWD")), fresh_output_observed=False
    )

    assert spanning_tree_sample_is_authoritative(fresh, "SW") is True
    assert spanning_tree_sample_is_authoritative(stale, "SW") is False
    assert spanning_tree_sample_is_authoritative(fresh, "OTHER") is False
