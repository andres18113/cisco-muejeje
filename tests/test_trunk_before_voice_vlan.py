"""Causal contracts for trunk forwarding before Voice VLAN signalling."""

from __future__ import annotations

from pathlib import Path

from src.packet_tracer_mcp.application.use_cases.qualify_positive_voice_slice import (
    ACQUISITION_NOT_STARTED_PRECONTROL_FOUNDATION_UNREADY,
    ACQUISITION_NOT_STARTED_POSTCONTROL_TRUNK_STATE_UNPROVEN,
    CONTRADICTED,
    DATA_VLAN_ID,
    EXPERIMENT_TRUNK_FORWARDING_BEFORE_VOICE,
    NO,
    TRUNK_FORWARDING_BEFORE_VOICE_CAUSAL_EFFECT_OBSERVED,
    TRUNK_FORWARDING_BEFORE_VOICE_NO_EFFECT,
    VERIFIED,
    VOICE_VLAN_ID,
    YES,
    PositiveVoiceSliceQualifier,
)
from tests.test_positive_voice_slice import (
    _Binding,
    _Clock,
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
)


CONTROL_PORT = "FastEthernet0/1"
INTERVENTION_PORT = "FastEthernet0/2"


def _paired_stp(control_state: str, intervention_state: str):
    return [
        _StpInstance(VOICE_VLAN_ID, (
            _StpRow(CONTROL_PORT, state=control_state),
            _StpRow(INTERVENTION_PORT, state=intervention_state),
        )),
    ]


def _no_phone_rows():
    return [_StpInstance(VOICE_VLAN_ID, ())]


class _SequencedFoundation(_FoundationConfiguration):
    def __init__(self, trunks, **kwargs):
        super().__init__(**kwargs)
        self.trunks = list(trunks)
        self.batches: list[list] = []

    def apply_actions(self, actions):
        batch = list(actions)
        self.batches.append(batch)
        return super().apply_actions(batch)

    def read_trunk(self, device_name, interface):
        self.trunk_reads.append((device_name, interface))
        if len(self.trunks) > 1:
            return self.trunks.pop(0)
        return self.trunks[0]


class _SplitCallControl(_FoundationCallControl):
    def __init__(self, *, control_acquired: bool, intervention_acquired: bool):
        super().__init__()
        self._acquired = {
            "_P1": control_acquired,
            "_P2": intervention_acquired,
        }

    def _for(self, endpoint_device_name: str):
        acquired = next(
            value for suffix, value in self._acquired.items()
            if endpoint_device_name.endswith(suffix)
        )
        if acquired:
            return _Registration(
                status="ActionExecutionStatus.VERIFIED",
                direct_readback="FieldVerificationStatus.VERIFIED",
                endpoint_ipv4="10.93.0.10",
                endpoint_dhcp_enabled=True,
            )
        return _Registration(
            status="ActionExecutionStatus.FAILED",
            direct_readback="",
            endpoint_ipv4="",
            endpoint_dhcp_enabled=True,
        )


def _access_batches(configuration):
    return [
        [
            item for item in batch
            if type(item).__name__ == "ConfigureAccessPort"
        ]
        for batch in configuration.batches
        if any(type(item).__name__ == "ConfigureAccessPort" for item in batch)
    ]


_DEFAULT = object()


def _run_trunk_order(
    *,
    trunks=None,
    interfaces=_DEFAULT,
    control_acquired=False,
    intervention_acquired=True,
    reverse_roles=False,
):
    trunks = trunks or (
        _Trunk(forwarding_vlans=()),
        _Trunk(forwarding_vlans=()),
        _Trunk(forwarding_vlans=()),
        _Trunk(forwarding_vlans=(DATA_VLAN_ID, VOICE_VLAN_ID)),
    )
    configuration_kwargs = {
        "bindings": (
            [_Binding("10.93.0.10")] if intervention_acquired else []
        ),
        "stp_sequence": [
            _no_phone_rows(),
            _paired_stp("FWD", "LIS"),
            _paired_stp("FWD", "FWD"),
        ],
    }
    if interfaces is not _DEFAULT:
        configuration_kwargs["interfaces"] = interfaces
    configuration = _SequencedFoundation(trunks, **configuration_kwargs)
    call_control = _SplitCallControl(
        control_acquired=(
            intervention_acquired if reverse_roles else control_acquired
        ),
        intervention_acquired=(
            control_acquired if reverse_roles else intervention_acquired
        ),
    )
    endpoints = _Endpoints()
    clock = _Clock()
    result = PositiveVoiceSliceQualifier(
        _Physical(_empty_workspace()),
        configuration,
        call_control,
        endpoints,
        _ModeRuntime(),
        token="trunk-order",
        trunk_before_voice_vlan=True,
        trunk_roles_reversed=reverse_roles,
        gate_timeout_seconds=10.0,
        gate_interval_seconds=2.0,
        gate_clock=clock,
        gate_sleeper=clock.sleep,
    ).qualify("2811", "3560-24PS", "7960")
    return result, configuration, endpoints


def test_mode_names_the_single_trunk_ordering_variable():
    result, _, _ = _run_trunk_order()

    assert result.experiment == EXPERIMENT_TRUNK_FORWARDING_BEFORE_VOICE


def test_control_and_intervention_receive_voice_in_separate_ordered_batches():
    result, configuration, _ = _run_trunk_order()

    batches = _access_batches(configuration)
    assert [
        [item.interface for item in batch] for batch in batches
    ] == [
        [CONTROL_PORT, INTERVENTION_PORT],
        [CONTROL_PORT],
        [INTERVENTION_PORT],
    ]
    assert [
        [item.voice_vlan_id for item in batch] for batch in batches
    ] == [
        [None, None],
        [VOICE_VLAN_ID],
        [VOICE_VLAN_ID],
    ]
    names = [item.name for item in result.lifecycle]
    assert names.index("WHEN_CONTROL_VOICE_VLAN_APPLIED") < names.index(
        "WHEN_INTERVENTION_VOICE_VLAN_APPLIED"
    )


def test_control_signal_requires_every_other_foundation_dimension_ready():
    result, configuration, _ = _run_trunk_order(interfaces=[])

    assert result.pre_control_foundation_status == CONTRADICTED
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_PRECONTROL_FOUNDATION_UNREADY
    )
    assert len(_access_batches(configuration)) == 1


def test_control_signal_requires_authoritative_not_forwarding_trunk():
    forwarding = _Trunk(
        forwarding_vlans=(DATA_VLAN_ID, VOICE_VLAN_ID),
    )
    result, configuration, _ = _run_trunk_order(
        trunks=(forwarding, forwarding),
    )

    assert result.pre_control_foundation_status == CONTRADICTED
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_PRECONTROL_FOUNDATION_UNREADY
    )
    assert len(_access_batches(configuration)) == 1


def test_same_trunk_is_observed_not_forwarding_then_forwarding():
    result, _, _ = _run_trunk_order()

    assert result.pre_control_foundation_status == VERIFIED
    assert result.pre_control_foundation is not None
    assert (
        result.pre_control_foundation.trunk_forwarding_voice
        == CONTRADICTED
    )
    assert result.post_control_signal_foundation is not None
    assert (
        result.post_control_signal_foundation.trunk_forwarding_voice
        == CONTRADICTED
    )
    assert result.pre_intervention_foundation is not None
    assert (
        result.pre_intervention_foundation.trunk_forwarding_voice
        == VERIFIED
    )
    assert result.trunk_order_forwarding_transition == (
        "NOT_FORWARDING -> FORWARDING"
    )
    assert result.shared_foundation_ready == VERIFIED
    assert result.shared_foundation_wait is not None
    assert result.shared_foundation_wait.trunk_forwarding_transition == (
        "NOT_FORWARDING -> FORWARDING"
    )
    assert result.control_stp_port_gate.forwarding_observed is True
    assert result.intervention_stp_port_gate.forwarding_observed is True


def test_mode_never_arms_or_toggles_phone_dhcp():
    _, _, endpoints = _run_trunk_order()

    assert endpoints.armed == []


def test_control_signal_is_bracketed_by_not_forwarding_reads():
    result, configuration, _ = _run_trunk_order(
        trunks=(
            _Trunk(forwarding_vlans=()),
            _Trunk(forwarding_vlans=(DATA_VLAN_ID, VOICE_VLAN_ID)),
        ),
    )

    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_POSTCONTROL_TRUNK_STATE_UNPROVEN
    )
    assert len(_access_batches(configuration)) == 2


def test_control_failure_and_intervention_success_is_the_causal_verdict():
    result, _, _ = _run_trunk_order()

    assert [item.addressed for item in result.phones] == [NO, YES]
    assert result.control_matching_binding == NO
    assert result.intervention_matching_binding == YES
    assert result.causal_experiment_result == (
        TRUNK_FORWARDING_BEFORE_VOICE_CAUSAL_EFFECT_OBSERVED
    )
    assert result.trunk_forwarding_controls_voice_acquisition == YES


def test_both_phones_acquiring_refutes_a_trunk_order_effect():
    result, _, _ = _run_trunk_order(
        control_acquired=True,
        intervention_acquired=True,
    )

    assert result.causal_experiment_result == (
        TRUNK_FORWARDING_BEFORE_VOICE_NO_EFFECT
    )


def test_reversed_roles_remove_fixed_phone_and_port_identity():
    result, configuration, _ = _run_trunk_order(
        control_acquired=False,
        intervention_acquired=True,
        reverse_roles=True,
    )

    batches = _access_batches(configuration)
    assert [item.interface for item in batches[1]] == [INTERVENTION_PORT]
    assert [item.interface for item in batches[2]] == [CONTROL_PORT]
    assert result.control_stp_port_gate.interface == INTERVENTION_PORT
    assert result.intervention_stp_port_gate.interface == CONTROL_PORT
    assert result.trunk_roles_reversed is True
    assert result.causal_experiment_result == (
        TRUNK_FORWARDING_BEFORE_VOICE_CAUSAL_EFFECT_OBSERVED
    )


def test_stp_timings_are_not_claimed_comparable_across_signal_origins():
    result, _, _ = _run_trunk_order()

    assert result.paired_stp_timing_comparability == (
        "NOT_COMPARABLE_DIFFERENT_VOICE_SIGNAL_ORIGINS"
    )


def test_live_runner_exposes_and_serializes_the_experiment():
    source = Path("tools/cp_scale_positive_voice_ab_live.py").read_text(
        encoding="utf-8",
    )

    assert '"--trunk-before-voice-vlan"' in source
    assert '"--reverse-trunk-roles"' in source
    assert "trunk_before_voice_vlan=trunk_before_voice_vlan" in source
    for key in (
        "pre_control_foundation",
        "pre_control_foundation_status",
        "post_control_signal_foundation",
        "pre_intervention_foundation",
        "trunk_order_forwarding_transition",
        "trunk_forwarding_controls_voice_acquisition",
        "trunk_roles_reversed",
        "paired_stp_timing_comparability",
        "control_voice_vlan_boundary",
        "intervention_voice_vlan_boundary",
    ):
        assert f'"{key}"' in source
