"""Causal contracts for data-only access preparation before Voice signalling."""

from __future__ import annotations

from pathlib import Path

from src.packet_tracer_mcp.application.use_cases.qualify_positive_voice_slice import (
    APPLIED,
    CONTRADICTED,
    DATA_ACCESS_PREPARATION_CAUSAL_EFFECT_OBSERVED,
    DATA_ACCESS_PREPARATION_NO_EFFECT,
    DATA_VLAN_ID,
    EXPERIMENT_DATA_ACCESS_PREPARATION_BEFORE_VOICE,
    NO,
    NOT_APPLIED,
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
    _Port,
    _Registration,
    _StpInstance,
    _StpRow,
    _empty_workspace,
)


P1 = "FastEthernet0/1"
P2 = "FastEthernet0/2"


def _paired_stp(control: str, intervention: str):
    return [
        _StpInstance(VOICE_VLAN_ID, (
            _StpRow(P1, state=control),
            _StpRow(P2, state=intervention),
        )),
    ]


class _BatchedConfiguration(_FoundationConfiguration):
    def __init__(self, *, unprepared_port: str, **kwargs):
        super().__init__(**kwargs)
        self.unprepared_port = unprepared_port
        self.batches: list[list] = []
        self.voice_boundary_applied = False

    def apply_actions(self, actions):
        batch = list(actions)
        self.batches.append(batch)
        mutations = super().apply_actions(batch)
        if sum(
            type(item).__name__ == "ConfigureAccessPort"
            and item.voice_vlan_id == VOICE_VLAN_ID
            for item in batch
        ) == 2:
            self.voice_boundary_applied = True
        return mutations

    def read_access_port(self, device_name, interface, expected_access_vlan):
        self.access_reads.append((interface, expected_access_vlan))
        if self.voice_boundary_applied:
            return _Port(DATA_VLAN_ID, VOICE_VLAN_ID)
        if interface == self.unprepared_port:
            return _Port(1, None)
        return _Port(DATA_VLAN_ID, None)


class _SplitCallControl(_FoundationCallControl):
    def __init__(self, *, p1_acquired: bool, p2_acquired: bool):
        super().__init__()
        self.acquired = {"_P1": p1_acquired, "_P2": p2_acquired}

    def _for(self, endpoint_device_name: str):
        suffix = next(
            suffix for suffix in self.acquired
            if endpoint_device_name.endswith(suffix)
        )
        if self.acquired[suffix]:
            return _Registration(
                status="ActionExecutionStatus.VERIFIED",
                direct_readback="FieldVerificationStatus.VERIFIED",
                endpoint_ipv4=(
                    "10.93.0.11" if suffix == "_P1" else "10.93.0.10"
                ),
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


def _run(
    *,
    control_acquired=False,
    intervention_acquired=True,
    reverse_roles=False,
):
    p1_acquired = intervention_acquired if reverse_roles else control_acquired
    p2_acquired = control_acquired if reverse_roles else intervention_acquired
    bindings = []
    if p1_acquired:
        bindings.append(_Binding("10.93.0.11"))
    if p2_acquired:
        bindings.append(_Binding("10.93.0.10"))
    configuration = _BatchedConfiguration(
        unprepared_port=P2 if reverse_roles else P1,
        bindings=bindings,
        stp_sequence=[
            [_StpInstance(VOICE_VLAN_ID, ())],
            _paired_stp("LIS", "LIS"),
            _paired_stp("FWD", "FWD"),
        ],
    )
    endpoints = _Endpoints()
    clock = _Clock()
    result = PositiveVoiceSliceQualifier(
        _Physical(_empty_workspace()),
        configuration,
        _SplitCallControl(
            p1_acquired=p1_acquired,
            p2_acquired=p2_acquired,
        ),
        endpoints,
        _ModeRuntime(),
        token="access-prep",
        access_preparation_before_voice_vlan=True,
        access_preparation_roles_reversed=reverse_roles,
        gate_timeout_seconds=10.0,
        gate_interval_seconds=2.0,
        gate_clock=clock,
        gate_sleeper=clock.sleep,
    ).qualify("2811", "3560-24PS", "7960")
    return result, configuration, endpoints


def test_mode_names_the_access_preparation_variable():
    result, *_ = _run()

    assert result.experiment == (
        EXPERIMENT_DATA_ACCESS_PREPARATION_BEFORE_VOICE
    )


def test_only_intervention_port_receives_initial_data_only_preparation():
    result, configuration, _ = _run()

    batches = _access_batches(configuration)
    assert [item.interface for item in batches[0]] == [P2]
    assert [item.data_vlan_id for item in batches[0]] == [DATA_VLAN_ID]
    assert [item.voice_vlan_id for item in batches[0]] == [None]
    assert result.control_access_preparation == NOT_APPLIED
    assert result.intervention_access_preparation == APPLIED
    assert result.control_access_preparation_readback == CONTRADICTED
    assert result.intervention_access_preparation_readback == VERIFIED


def test_same_late_batch_signals_both_ports_from_one_clock():
    _, configuration, _ = _run()

    boundary = _access_batches(configuration)[1]
    assert [item.interface for item in boundary] == [P1, P2]
    assert [item.data_vlan_id for item in boundary] == [
        DATA_VLAN_ID, DATA_VLAN_ID,
    ]
    assert [item.voice_vlan_id for item in boundary] == [
        VOICE_VLAN_ID, VOICE_VLAN_ID,
    ]


def test_shared_foundation_is_verified_before_the_common_signal():
    result, *_ = _run()

    assert result.shared_foundation_ready == VERIFIED
    assert result.shared_foundation_wait is not None
    assert result.control_stp_port_gate.forwarding_observed is True
    assert result.intervention_stp_port_gate.forwarding_observed is True


def test_mode_never_arms_or_toggles_phone_dhcp():
    _, _, endpoints = _run()

    assert endpoints.armed == []


def test_only_prepared_phone_acquiring_is_the_causal_effect():
    result, *_ = _run()

    assert [item.addressed for item in result.phones] == [NO, YES]
    assert result.control_matching_binding == NO
    assert result.intervention_matching_binding == YES
    assert result.causal_experiment_result == (
        DATA_ACCESS_PREPARATION_CAUSAL_EFFECT_OBSERVED
    )
    assert result.data_access_preparation_controls_acquisition == YES


def test_both_phones_acquiring_refutes_access_preparation_effect():
    result, *_ = _run(control_acquired=True, intervention_acquired=True)

    assert result.causal_experiment_result == DATA_ACCESS_PREPARATION_NO_EFFECT


def test_roles_can_be_reversed_without_changing_the_question():
    result, configuration, _ = _run(reverse_roles=True)

    batches = _access_batches(configuration)
    assert [item.interface for item in batches[0]] == [P1]
    assert result.control_stp_port_gate.interface == P2
    assert result.intervention_stp_port_gate.interface == P1
    assert result.access_preparation_roles_reversed is True
    assert result.causal_experiment_result == (
        DATA_ACCESS_PREPARATION_CAUSAL_EFFECT_OBSERVED
    )


def test_live_runner_exposes_and_serializes_the_experiment():
    source = Path("tools/cp_scale_positive_voice_ab_live.py").read_text(
        encoding="utf-8",
    )

    assert '"--access-preparation-before-voice-vlan"' in source
    assert '"--reverse-access-preparation-roles"' in source
    assert (
        "access_preparation_before_voice_vlan="
        "access_preparation_before_voice_vlan"
    ) in source
    for key in (
        "control_access_preparation",
        "intervention_access_preparation",
        "control_access_preparation_readback",
        "intervention_access_preparation_readback",
        "access_preparation_roles_reversed",
        "data_access_preparation_controls_acquisition",
    ):
        assert f'"{key}"' in source
