"""Contracts for RUN15: the edge-before-voice-VLAN causal experiment.

The leading hypothesis is that a 7960 creates its voice SVI and makes its one
DHCP attempt while the phone-facing VLAN930 STP instance is still
non-forwarding, and that Packet Tracer produces no useful later retry.

The experiment isolates ONE variable.  Both phones share every part of the
foundation and receive the SAME voice VLAN in the SAME batch; only the
intervention port carries a typed edge policy, dispatched BEFORE that batch.
The voice-VLAN batch is therefore a causal clock boundary, and both ports are
measured from it against one observation per sample.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.packet_tracer_mcp.application.use_cases.qualify_positive_voice_slice import (
    ACQUISITION_NOT_STARTED_SHARED_FOUNDATION_UNREADY,
    ACQUISITION_NOT_STARTED_STP_PRECONDITION_UNMET,
    DATA_VLAN_ID,
    EDGE_BEFORE_VOICE_VLAN_CAUSAL_EFFECT_OBSERVED,
    EDGE_BEFORE_VOICE_VLAN_MILESTONES,
    EDGE_POLICY_EFFECT_NOT_ESTABLISHED,
    EDGE_STP_EFFECT_OBSERVED_WITHOUT_DHCP_EFFECT,
    EXPERIMENT_EDGE_BEFORE_VOICE_VLAN,
    FORWARDING,
    NO,
    NOT_REGISTERED,
    OBSERVATION,
    PHONE_ADDRESSING_INTERFACE,
    SHARED_PREPARED_FOUNDATION_ACQUISITION,
    UNOBSERVABLE,
    VERIFIED,
    VOICE_VLAN_ID,
    YES,
    EdgeVoiceSviObservation,
    PairedStpPortGate,
    await_paired_stp_forwarding,
)
from tests.test_positive_voice_slice import (
    _CallControl,
    _Clock,
    _Configuration,
    _ControlPlane,
    _EndpointObservation,
    _Endpoints,
    _FoundationCallControl,
    _FoundationConfiguration,
    _ModeRuntime,
    _Physical,
    _Registration,
    _StpInstance,
    _StpRow,
    _Trunk,
    _empty_workspace,
    _mutation,
    _qualifier,
)
from src.packet_tracer_mcp.application.use_cases.qualify_positive_voice_slice import (
    PositiveVoiceSliceQualifier,
)


CONTROL_PORT = "FastEthernet0/1"
INTERVENTION_PORT = "FastEthernet0/2"


def _paired_stp(control_state: str, intervention_state: str, *, edge=False):
    """One `show spanning-tree` answer covering BOTH phone-facing ports."""
    return [
        _StpInstance(VOICE_VLAN_ID, (
            _StpRow(CONTROL_PORT, state=control_state, link_type="P2p"),
            _StpRow(
                INTERVENTION_PORT, state=intervention_state,
                link_type="P2p Edge" if edge else "P2p",
            ),
        )),
    ]


class _EdgeConfiguration(_FoundationConfiguration):
    """The foundation surfaces plus a scripted paired STP script."""

    def __init__(self, *, stp_sequence=None, timeline=None, **kwargs):
        super().__init__(stp_sequence=stp_sequence, timeline=timeline, **kwargs)
        #: Every batch handed to `apply_actions`, kept apart.  The whole
        #: experiment turns on WHICH batch the voice VLAN arrived in, so a
        #: flattened `applied` list cannot answer it.
        self.batches: list[list] = []

    def apply_actions(self, actions):
        batch = list(actions)
        self.batches.append(batch)
        if self.timeline is not None:
            names = {type(item).__name__ for item in batch}
            self.timeline.append("config_batch:" + ",".join(sorted(names)))
        return super().apply_actions(batch)


class _EdgeControlPlane(_ControlPlane):
    def __init__(self, timeline=None, mutations=None):
        super().__init__(mutations=mutations)
        self.timeline = timeline

    def apply_actions(self, actions):
        batch = list(actions)
        if self.timeline is not None:
            self.timeline.append(
                "edge:" + ",".join(item.interface for item in batch)
            )
        return super().apply_actions(batch)


def _access_ports(batch):
    return [
        item for item in batch
        if type(item).__name__ == "ConfigureAccessPort"
    ]


def _access_batches(configuration):
    return [
        batch for batch in configuration.batches if _access_ports(batch)
    ]


def _edge_actions(control_plane):
    return [
        item for item in control_plane.applied
        if type(item).__name__ == "ConfigureStpEdgePort"
    ]


def _run_edge(
    *, stp_sequence=None, configuration=None, call_control=None,
    endpoints=None, control_plane=None, timeline=None, registration=None,
    physical=None, clock=None, **kwargs,
):
    clock = clock if clock is not None else _Clock()
    if stp_sequence is None:
        stp_sequence = [_paired_stp("FWD", "FWD", edge=True)]
    configuration = configuration if configuration is not None else (
        _EdgeConfiguration(stp_sequence=stp_sequence, timeline=timeline)
    )
    if call_control is None:
        call_control = _FoundationCallControl(
            registration=registration
        ) if registration is not None else _FoundationCallControl()
    endpoints = endpoints if endpoints is not None else _Endpoints(
        observation=_EndpointObservation(
            present=True, dhcp_enabled=True, address_channel=True,
        ),
    )
    control_plane = control_plane if control_plane is not None else (
        _EdgeControlPlane(timeline=timeline)
    )
    physical = physical if physical is not None else _Physical(_empty_workspace())
    qualifier = PositiveVoiceSliceQualifier(
        physical, configuration, call_control, endpoints, _ModeRuntime(),
        token="test15", control_plane=control_plane,
        edge_before_voice_vlan=True,
        gate_clock=clock, gate_sleeper=clock.sleep,
        **kwargs,
    )
    result = qualifier.qualify("2811", "3560-24PS", "7960")
    return result, configuration, control_plane, endpoints, call_control, clock


# --- the experiment is its own named comparison -----------------------------

def test_the_mode_names_itself_as_its_own_experiment():
    result, *_ = _run_edge()

    assert result.experiment == EXPERIMENT_EDGE_BEFORE_VOICE_VLAN


def test_the_mode_refuses_to_share_a_run_with_another_causal_variable():
    for other in (
        "fwd_gated_fresh_dhcp", "phone_dhcp_lifecycle",
        "phone_svi_dhcp_retrigger",
    ):
        with pytest.raises(ValueError, match="one causal variable"):
            _qualifier(
                _Physical(_empty_workspace()), _Configuration(),
                _CallControl(), _Endpoints(), _ModeRuntime(),
                control_plane=_ControlPlane(),
                edge_before_voice_vlan=True, **{other: True},
            )


def test_the_mode_needs_a_typed_control_plane_to_dispatch_the_edge_policy():
    with pytest.raises(ValueError, match="control-plane"):
        _qualifier(
            _Physical(_empty_workspace()), _Configuration(), _CallControl(),
            _Endpoints(), _ModeRuntime(), edge_before_voice_vlan=True,
        )


def test_both_phones_share_the_same_access_vlan_shape():
    result, configuration, *_ = _run_edge()

    # The access VLAN is NOT the variable here; run 9 already turned that one.
    assert [item.access_vlan_expected for item in result.phones] == [
        DATA_VLAN_ID, DATA_VLAN_ID,
    ]


# --- the voice VLAN is withheld until the boundary ---------------------------

def test_the_foundation_batch_puts_no_voice_vlan_on_the_phone_ports():
    _, configuration, *_ = _run_edge()

    foundation = _access_batches(configuration)[0]
    assert [item.interface for item in _access_ports(foundation)] == [
        CONTROL_PORT, INTERVENTION_PORT,
    ]
    # The whole experiment is that VLAN930 has NOT been signalled yet while the
    # upstream foundation is being brought up and verified.
    assert [item.voice_vlan_id for item in _access_ports(foundation)] == [
        None, None,
    ]
    assert [item.data_vlan_id for item in _access_ports(foundation)] == [
        DATA_VLAN_ID, DATA_VLAN_ID,
    ]


def test_the_voice_vlan_arrives_in_its_own_later_batch_for_both_ports():
    _, configuration, *_ = _run_edge()

    batches = _access_batches(configuration)
    assert len(batches) == 2
    boundary = _access_ports(batches[1])
    assert [item.interface for item in boundary] == [
        CONTROL_PORT, INTERVENTION_PORT,
    ]
    # The SAME voice VLAN reaches both ports in the SAME batch: the edge policy
    # is the only thing that differs between them.
    assert [item.voice_vlan_id for item in boundary] == [
        VOICE_VLAN_ID, VOICE_VLAN_ID,
    ]
    assert [item.data_vlan_id for item in boundary] == [
        DATA_VLAN_ID, DATA_VLAN_ID,
    ]


def test_the_boundary_batch_carries_nothing_but_the_two_access_ports():
    _, configuration, *_ = _run_edge()

    boundary = _access_batches(configuration)[1]
    # A pool, a subinterface or a trunk riding along would move the foundation
    # across the clock boundary and confound the measurement.
    assert [type(item).__name__ for item in boundary] == [
        "ConfigureAccessPort", "ConfigureAccessPort",
    ]


def test_the_journal_names_the_voice_vlan_application_boundary():
    result, *_ = _run_edge()

    names = [item.name for item in result.lifecycle]
    assert "WHEN_VOICE_VLAN_APPLICATION_BOUNDARY" in names


def test_the_initial_batch_journals_voice_vlan_as_withheld_not_applied():
    result, *_ = _run_edge()

    names = [item.name for item in result.lifecycle]
    assert "WHEN_VOICE_VLAN_WITHHELD" in names
    assert "WHEN_VOICE_VLAN_APPLIED" not in names
    assert names.count("WHEN_VOICE_VLAN_APPLICATION_BOUNDARY") == 1


# --- the edge policy is the one variable, and it lands first ----------------

def test_only_the_intervention_port_receives_the_edge_policy():
    _, _, control_plane, *_ = _run_edge()

    actions = _edge_actions(control_plane)
    assert len(actions) == 1
    assert actions[0].interface == INTERVENTION_PORT
    assert actions[0].portfast is True
    # BPDU Guard would be a second variable.
    assert actions[0].bpduguard is False


def test_the_edge_policy_is_dispatched_before_the_voice_vlan_boundary():
    timeline: list[str] = []
    _run_edge(timeline=timeline)

    edge = timeline.index("edge:" + INTERVENTION_PORT)
    access_batches = [
        index for index, item in enumerate(timeline)
        if item.startswith("config_batch:") and "ConfigureAccessPort" in item
    ]
    # The foundation batch precedes the edge dispatch, and the boundary batch
    # follows it.  That order IS the hypothesis under test.
    assert access_batches[0] < edge < access_batches[1]


def test_edge_policy_dispatch_and_runtime_state_are_reported_apart():
    result, *_ = _run_edge(
        stp_sequence=[_paired_stp("FWD", "FWD", edge=True)],
    )

    assert result.edge_policy_dispatch == "APPLIED"
    # An existing read-only surface -- the STP Type column -- verifies it here.
    assert result.edge_policy_runtime_state == VERIFIED


def test_a_silent_type_column_leaves_the_edge_runtime_state_unobservable():
    result, *_ = _run_edge(
        stp_sequence=[_paired_stp("FWD", "FWD", edge=False)],
    )

    # APPLIED is dispatch, never runtime truth.
    assert result.edge_policy_dispatch == "APPLIED"
    assert result.edge_policy_runtime_state == UNOBSERVABLE


def test_a_refused_edge_dispatch_is_reported_as_not_applied():
    control_plane = _EdgeControlPlane(
        mutations=lambda action_id: _mutation(
            action_id=action_id, applied=False, message="refused",
        ),
    )
    result, *_ = _run_edge(control_plane=control_plane)

    assert result.edge_policy_dispatch == "NOT_APPLIED"


def test_a_refused_edge_dispatch_fails_closed_before_voice_signalling():
    control_plane = _EdgeControlPlane(
        mutations=lambda action_id: _mutation(
            action_id=action_id, applied=False, message="refused",
        ),
    )
    result, configuration, *_ = _run_edge(control_plane=control_plane)

    assert result.acquisition_boundary == (
        "ACQUISITION_NOT_STARTED_EDGE_POLICY_DISPATCH_UNPROVEN"
    )
    assert result.acquisition_started is False
    assert len(_access_batches(configuration)) == 1
    names = [item.name for item in result.lifecycle]
    assert "WHEN_VOICE_VLAN_APPLICATION_BOUNDARY" not in names


# --- the shared foundation must be ready BEFORE the boundary ----------------

def test_a_contradicted_shared_foundation_fails_closed_before_the_boundary():
    class _NoTrunk(_EdgeConfiguration):
        def read_trunk(self, device_name, interface):
            return None

    result, configuration, control_plane, *_ = _run_edge(
        configuration=_NoTrunk(
            stp_sequence=[_paired_stp("FWD", "FWD", edge=True)],
        ),
    )

    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_SHARED_FOUNDATION_UNREADY
    )
    assert result.shared_foundation_ready == UNOBSERVABLE
    # The causal clock never started: VLAN930 was never signalled to a phone.
    assert len(_access_batches(configuration)) == 1
    assert result.acquisition_started is False


def test_a_ready_shared_foundation_is_reported_and_lets_the_boundary_run():
    result, configuration, *_ = _run_edge()

    assert result.shared_foundation_ready == VERIFIED
    assert len(_access_batches(configuration)) == 2


def test_the_shared_foundation_waits_until_forwarding_then_authorizes_boundary():
    class _ConvergingTrunk(_EdgeConfiguration):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._trunks = [
                _Trunk(forwarding_vlans=()),
                _Trunk(forwarding_vlans=(DATA_VLAN_ID, VOICE_VLAN_ID)),
            ]

        def read_trunk(self, device_name, interface):
            self.trunk_reads.append((device_name, interface))
            if len(self._trunks) > 1:
                return self._trunks.pop(0)
            return self._trunks[0]

    result, configuration, *_ = _run_edge(
        configuration=_ConvergingTrunk(
            stp_sequence=[_paired_stp("FWD", "FWD", edge=True)],
        ),
        gate_timeout_seconds=10.0,
        gate_interval_seconds=2.0,
    )

    wait = result.shared_foundation_wait
    assert wait.status == VERIFIED
    assert wait.samples == 2
    assert wait.duration_ms == 2_000
    assert wait.first_verified_ms == 2_000
    assert [item.status for item in wait.transitions] == [
        "CONTRADICTED", VERIFIED,
    ]
    assert wait.transitions[0].failure_dimensions == (
        "trunk_forwarding_voice",
    )
    assert wait.trunk_forwarding_transition == (
        "NOT_FORWARDING -> FORWARDING"
    )
    assert wait.trunk_forwarding_convergence == "DIRECTLY_OBSERVED"
    assert len(_access_batches(configuration)) == 2


def test_the_shared_foundation_timeout_retains_authority_and_fails_closed():
    configuration = _EdgeConfiguration(
        trunk=_Trunk(forwarding_vlans=()),
        stp_sequence=[_paired_stp("FWD", "FWD", edge=True)],
    )
    result, configuration, control_plane, *_ = _run_edge(
        configuration=configuration,
        gate_timeout_seconds=4.0,
        gate_interval_seconds=2.0,
    )

    wait = result.shared_foundation_wait
    assert wait.status == "TIMEOUT"
    assert wait.samples == 3
    assert wait.duration_ms == 4_000
    assert wait.first_verified_ms is None
    assert wait.terminal_read_authority == "AUTHORITATIVE"
    assert wait.terminal_failure_dimensions == ("trunk_forwarding_voice",)
    assert result.shared_foundation_ready == "CONTRADICTED"
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_SHARED_FOUNDATION_UNREADY
    )
    assert _edge_actions(control_plane) == []
    assert len(_access_batches(configuration)) == 1


def test_an_unobservable_foundation_never_authorizes_mutation_after_timeout():
    class _UnreadTrunk(_EdgeConfiguration):
        def read_trunk(self, device_name, interface):
            self.trunk_reads.append((device_name, interface))
            return None

    result, configuration, control_plane, *_ = _run_edge(
        configuration=_UnreadTrunk(
            stp_sequence=[_paired_stp("FWD", "FWD", edge=True)],
        ),
        gate_timeout_seconds=2.0,
        gate_interval_seconds=1.0,
    )

    assert result.shared_foundation_wait.status == "TIMEOUT"
    assert "trunk_operational" in (
        result.shared_foundation_wait.terminal_failure_dimensions
    )
    assert result.shared_foundation_ready == UNOBSERVABLE
    assert _edge_actions(control_plane) == []
    assert len(_access_batches(configuration)) == 1


def test_the_shared_foundation_is_read_before_the_boundary_batch():
    timeline: list[str] = []
    _, configuration, *_ = _run_edge(timeline=timeline)

    # The pool read is the last shared-foundation surface; it must precede the
    # boundary, otherwise "ready first" is a claim rather than a measurement.
    assert configuration.pool_reads
    access_batches = [
        index for index, item in enumerate(timeline)
        if item.startswith("config_batch:") and "ConfigureAccessPort" in item
    ]
    assert len(access_batches) == 2


# --- both ports, one observation per sample, one clock ----------------------

def test_the_paired_gate_reads_one_observation_per_sample_for_both_ports():
    timeline: list[str] = []
    result, configuration, *_ = _run_edge(
        stp_sequence=[
            _paired_stp("LIS", "FWD", edge=True),
            _paired_stp("LRN", "FWD", edge=True),
            _paired_stp("FWD", "FWD", edge=True),
        ],
        timeline=timeline,
    )

    control = result.control_stp_port_gate
    intervention = result.intervention_stp_port_gate
    assert isinstance(control, PairedStpPortGate)
    assert isinstance(intervention, PairedStpPortGate)
    # One query per sample, and the SAME query answered both ports.
    assert control.samples == intervention.samples


def test_the_paired_gate_retains_each_ports_first_state_and_sequence():
    result, *_ = _run_edge(
        # The first scripted answer is the pre-boundary snapshot the slice
        # always takes; the gate's own samples follow it.
        stp_sequence=[
            _paired_stp("BLK", "BLK", edge=True),
            _paired_stp("LIS", "FWD", edge=True),
            _paired_stp("LRN", "FWD", edge=True),
            _paired_stp("FWD", "FWD", edge=True),
        ],
    )

    control = result.control_stp_port_gate
    intervention = result.intervention_stp_port_gate
    assert control.first_authoritative_state == "LIS"
    assert control.observed_states == ("LIS", "LRN", FORWARDING)
    assert intervention.first_authoritative_state == FORWARDING
    assert intervention.observed_states == (FORWARDING,)
    assert control.status == FORWARDING
    assert intervention.status == FORWARDING


def test_each_port_retains_its_time_from_the_boundary_to_forwarding():
    result, _, _, _, _, clock = _run_edge(
        stp_sequence=[
            _paired_stp("LIS", "FWD", edge=True),
            _paired_stp("LRN", "FWD", edge=True),
            _paired_stp("FWD", "FWD", edge=True),
        ],
    )

    control = result.control_stp_port_gate
    intervention = result.intervention_stp_port_gate
    # Both clocks start at the SAME boundary, so the difference is the answer.
    assert intervention.time_to_forwarding_ms == 0
    assert control.time_to_forwarding_ms > intervention.time_to_forwarding_ms
    assert control.time_to_first_authoritative_ms == 0
    assert intervention.time_to_first_authoritative_ms == 0


def test_both_stp_times_use_the_voice_vlan_boundary_before_svi_reads():
    clock = _Clock()

    class _TimedEndpoints(_Endpoints):
        def read_endpoint_address(self, device_name, interface):
            clock.sleep(0.25)
            return super().read_endpoint_address(device_name, interface)

    result, *_ = _run_edge(
        clock=clock,
        endpoints=_TimedEndpoints(
            observation=_EndpointObservation(
                present=True, dhcp_enabled=True, address_channel=True,
            ),
        ),
        stp_sequence=[_paired_stp("FWD", "FWD", edge=True)],
    )

    # The two immediate SVI reads take 500 ms.  Both port clocks include that
    # delay because their one origin is the preceding voice-VLAN batch.
    assert result.control_stp_port_gate.time_to_first_authoritative_ms == 500
    assert result.intervention_stp_port_gate.time_to_first_authoritative_ms == 500
    assert result.control_stp_port_gate.time_to_forwarding_ms == 500
    assert result.intervention_stp_port_gate.time_to_forwarding_ms == 500


def test_a_port_that_never_forwards_times_out_without_inventing_a_state():
    result, *_ = _run_edge(
        stp_sequence=[_paired_stp("LIS", "FWD", edge=True)],
        gate_timeout_seconds=6.0, gate_interval_seconds=2.0,
    )

    control = result.control_stp_port_gate
    assert control.status == "TIMEOUT"
    assert control.time_to_forwarding_ms is None
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_STP_PRECONDITION_UNMET
    )


# --- bounded SVI milestones -------------------------------------------------

def test_the_phone_svi_is_observed_at_the_four_bounded_milestones():
    result, *_ = _run_edge(
        stp_sequence=[
            _paired_stp("LIS", "FWD", edge=True),
            _paired_stp("FWD", "FWD", edge=True),
        ],
    )

    assert EDGE_BEFORE_VOICE_VLAN_MILESTONES == (
        "IMMEDIATELY_AFTER_VOICE_VLAN",
        "FIRST_AUTHORITATIVE_STP_SAMPLE",
        "AUTHORITATIVE_FWD",
        "END_OF_ACQUISITION_WINDOW",
    )
    observed = result.edge_voice_svi_lifecycle
    assert all(isinstance(item, EdgeVoiceSviObservation) for item in observed)
    for phone in (result.phones[0].phone_name, result.phones[1].phone_name):
        milestones = tuple(
            item.milestone for item in observed if item.phone == phone
        )
        assert milestones == EDGE_BEFORE_VOICE_VLAN_MILESTONES


def test_each_milestone_retains_the_five_governed_endpoint_fields():
    result, *_ = _run_edge()

    item = result.edge_voice_svi_lifecycle[0]
    evidence = item.as_evidence()
    assert set(evidence) >= {
        "milestone", "phone", "svi_present", "dhcp_enabled",
        "address_channel", "ipv4", "addressed",
    }
    assert evidence["svi_present"] == YES
    assert evidence["dhcp_enabled"] == YES
    assert evidence["addressed"] == NO


def test_the_milestone_read_uses_the_existing_voice_svi_surface():
    _, _, _, endpoints, *_ = _run_edge()

    # No new observer: the registration pass's own per-phone SVI read.
    assert set(endpoints.read_interfaces) == {PHONE_ADDRESSING_INTERFACE}


# --- nothing in this mode touches a DHCP flag -------------------------------

def test_no_dhcp_flag_is_armed_or_mutated_in_this_mode():
    result, _, _, endpoints, *_ = _run_edge()

    assert endpoints.armed == []
    assert result.dhcp_flag_transition == UNOBSERVABLE
    assert result.phone_svi_dhcp_transitions == ()


def test_the_mode_never_reaches_for_the_svi_dhcp_setter():
    class _Trap(_Endpoints):
        def set_endpoint_dhcp_client_state(self, device_name, interface, on):
            raise AssertionError(
                "RUN15 must not mutate a DHCP client flag"
            )

    result, *_ = _run_edge(
        endpoints=_Trap(
            observation=_EndpointObservation(
                present=True, dhcp_enabled=True, address_channel=True,
            ),
        ),
    )

    assert result.experiment == EXPERIMENT_EDGE_BEFORE_VOICE_VLAN


# --- the causal verdicts ----------------------------------------------------

def _acquired_registration():
    return _Registration(
        status="ActionExecutionStatus.VERIFIED",
        direct_readback="FieldVerificationStatus.VERIFIED",
        endpoint_ipv4="10.93.0.10", endpoint_dhcp_enabled=True,
    )


def _unaddressed_registration():
    return _Registration(
        status="ActionExecutionStatus.FAILED", direct_readback="",
        endpoint_ipv4="", endpoint_dhcp_enabled=True,
    )


class _SplitCallControl(_FoundationCallControl):
    """Answers one phone acquired and the other not, by phone name."""

    def __init__(self, acquired_suffix="_P2", **kwargs):
        super().__init__(**kwargs)
        self.acquired_suffix = acquired_suffix

    def _for(self, endpoint_device_name: str):
        if endpoint_device_name.endswith(self.acquired_suffix):
            return _acquired_registration()
        return _unaddressed_registration()


def test_only_the_intervention_acquiring_is_the_strong_positive_result():
    result, *_ = _run_edge(
        stp_sequence=[
            _paired_stp("LIS", "FWD", edge=True),
            _paired_stp("LRN", "FWD", edge=True),
            _paired_stp("FWD", "FWD", edge=True),
        ],
        call_control=_SplitCallControl(),
        endpoints=_Endpoints(
            observation=_EndpointObservation(
                present=True, dhcp_enabled=True, address_channel=True,
            ),
        ),
    )

    assert result.phones[0].addressed == NO
    assert result.phones[1].addressed == YES
    assert result.causal_experiment_result == (
        EDGE_BEFORE_VOICE_VLAN_CAUSAL_EFFECT_OBSERVED
    )
    assert result.stp_timing_controls_dhcp_acquisition == YES


def test_both_phones_acquiring_credits_the_foundation_and_not_the_edge():
    result, *_ = _run_edge(
        stp_sequence=[
            _paired_stp("LIS", "FWD", edge=True),
            _paired_stp("FWD", "FWD", edge=True),
        ],
        call_control=_FoundationCallControl(
            registration=_acquired_registration(),
        ),
    )

    assert result.causal_experiment_result == (
        SHARED_PREPARED_FOUNDATION_ACQUISITION
    )
    # The edge policy was not isolated as the cause, so it earns no credit.
    assert result.stp_timing_controls_dhcp_acquisition == NOT_ESTABLISHED_VALUE


NOT_ESTABLISHED_VALUE = "NOT_ESTABLISHED"


def test_an_stp_difference_without_an_address_weakens_the_hypothesis():
    result, *_ = _run_edge(
        stp_sequence=[
            _paired_stp("LIS", "FWD", edge=True),
            _paired_stp("LRN", "FWD", edge=True),
            _paired_stp("FWD", "FWD", edge=True),
        ],
        call_control=_FoundationCallControl(
            registration=_unaddressed_registration(),
        ),
        configuration=_EdgeConfiguration(
            stp_sequence=[
                _paired_stp("LIS", "FWD", edge=True),
                _paired_stp("LRN", "FWD", edge=True),
                _paired_stp("FWD", "FWD", edge=True),
            ],
            bindings=[],
        ),
    )

    assert [item.addressed for item in result.phones] == [NO, NO]
    assert result.causal_experiment_result == (
        EDGE_STP_EFFECT_OBSERVED_WITHOUT_DHCP_EFFECT
    )
    assert result.stp_timing_controls_dhcp_acquisition == NO


def test_no_behavioural_stp_difference_establishes_no_edge_effect():
    result, *_ = _run_edge(
        stp_sequence=[
            _paired_stp("LIS", "LIS", edge=False),
            _paired_stp("FWD", "FWD", edge=False),
        ],
        call_control=_FoundationCallControl(
            registration=_unaddressed_registration(),
        ),
        configuration=_EdgeConfiguration(
            stp_sequence=[
                _paired_stp("LIS", "LIS", edge=False),
                _paired_stp("FWD", "FWD", edge=False),
            ],
            bindings=[],
        ),
    )

    assert result.causal_experiment_result == (
        EDGE_POLICY_EFFECT_NOT_ESTABLISHED
    )
    # A DHCP outcome under no STP difference is not a PortFast test.
    assert result.stp_timing_controls_dhcp_acquisition == NOT_ESTABLISHED_VALUE


def test_an_unreadable_gate_never_reports_a_causal_verdict():
    result, *_ = _run_edge(
        stp_sequence=[None],
        configuration=_EdgeConfiguration(stp_sequence=[None]),
    )

    assert result.causal_experiment_result == UNOBSERVABLE
    assert result.stp_timing_controls_dhcp_acquisition == NOT_ESTABLISHED_VALUE


# --- the transaction claims stay where they were ----------------------------

def test_the_mode_promotes_no_discover_or_transaction_claim():
    result, *_ = _run_edge(
        call_control=_FoundationCallControl(
            registration=_unaddressed_registration(),
        ),
    )

    assert result.fresh_7960_dhcp_transaction == "NOT_INDEPENDENTLY_ESTABLISHED"
    # An STP verdict is not a licence to promote a transaction claim nothing
    # observed, so the runner keeps saying so in the archived artifact.
    source = _LIVE_SOURCE
    assert '"server_receives_discover": "UNOBSERVABLE"' in source
    assert '"dhcp_transaction_progress": "UNOBSERVABLE"' in source


# This module sorts BEFORE `test_import_isolation_preflight`, which proves the
# pytest process never loaded the bare production namespace.  Importing the
# LIVE runner here would load it and break that proof, so the runner is read as
# source -- the same way the other pre-preflight suites assert about it.
_LIVE_SOURCE = Path("tools/cp_scale_positive_voice_ab_live.py").read_text(
    encoding="utf-8",
)


def test_the_archived_artifact_carries_the_run15_evidence():
    result, *_ = _run_edge(
        stp_sequence=[
            _paired_stp("BLK", "BLK", edge=True),
            _paired_stp("LIS", "FWD", edge=True),
            _paired_stp("FWD", "FWD", edge=True),
        ],
    )

    # The values, from the result the runner serializes.
    assert result.experiment == EXPERIMENT_EDGE_BEFORE_VOICE_VLAN
    assert result.shared_foundation_ready == VERIFIED
    assert result.edge_policy_dispatch == "APPLIED"
    assert result.edge_policy_runtime_state == VERIFIED
    assert result.control_stp_port_gate.interface == CONTROL_PORT
    assert result.intervention_stp_port_gate.interface == INTERVENTION_PORT
    assert result.control_stp_port_gate.first_authoritative_state == "LIS"
    assert len(result.edge_voice_svi_lifecycle) == 8

    # And the keys, so none of it can be measured and then dropped on the way
    # into the file that outlives the run.
    for key in (
        "shared_foundation_ready", "edge_policy_dispatch",
        "shared_foundation_wait", "trunk_forwarding_convergence",
        "control_edge_dispatch", "intervention_edge_dispatch",
        "intervention_edge_runtime_state", "voice_vlan_clock_boundary",
        "edge_policy_runtime_state", "edge_stp_effect_observed",
        "control_stp_port_gate", "intervention_stp_port_gate",
        "edge_voice_svi_lifecycle", "control_matching_binding",
        "intervention_matching_binding",
        "stp_timing_controls_dhcp_acquisition",
    ):
        assert f'"{key}"' in _LIVE_SOURCE


def test_the_live_runner_exposes_the_mode_as_its_own_flag():
    assert '"--edge-before-voice-vlan"' in _LIVE_SOURCE
    assert "edge_before_voice_vlan=edge_before_voice_vlan" in _LIVE_SOURCE
    # One causal variable per run is enforced at the CLI too.
    assert '("--edge-before-voice-vlan", args.edge_before_voice_vlan)' in (
        _LIVE_SOURCE
    )


# --- the standalone paired gate ---------------------------------------------

def test_the_paired_gate_classifies_every_named_port_from_one_read():
    clock = _Clock()
    configuration = _Configuration(
        stp_sequence=[
            _paired_stp("LIS", "FWD"),
            _paired_stp("FWD", "FWD"),
        ],
    )
    errors: list[str] = []

    gates = await_paired_stp_forwarding(
        configuration, "SW", VOICE_VLAN_ID,
        ((("control"), CONTROL_PORT), ("intervention", INTERVENTION_PORT)),
        timeout_seconds=30.0, interval_seconds=2.0,
        clock=clock, sleeper=clock.sleep, errors=errors,
    )

    assert set(gates) == {"control", "intervention"}
    assert gates["control"].status == FORWARDING
    assert gates["intervention"].status == FORWARDING
    assert gates["control"].samples == gates["intervention"].samples
    assert errors == []
