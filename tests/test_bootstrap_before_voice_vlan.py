"""Causal contracts for Voice bootstrap readiness before VLAN signalling."""

from __future__ import annotations

from pathlib import Path

from src.packet_tracer_mcp.application.use_cases.qualify_positive_voice_slice import (
    ACQUISITION_NOT_STARTED_PRECONTROL_FOUNDATION_UNREADY,
    ACQUISITION_NOT_STARTED_VOICE_BOOTSTRAP_UNREADY,
    APPLIED,
    DATA_VLAN_ID,
    EXPERIMENT_VOICE_BOOTSTRAP_BEFORE_SIGNAL,
    NO,
    NOT_APPLIED,
    NOT_REGISTERED,
    UNOBSERVABLE,
    VERIFIED,
    VOICE_BOOTSTRAP_BEFORE_SIGNAL_CAUSAL_EFFECT_OBSERVED,
    VOICE_BOOTSTRAP_BEFORE_SIGNAL_INSUFFICIENT,
    VOICE_BOOTSTRAP_BEFORE_SIGNAL_NO_EFFECT,
    VOICE_BOOTSTRAP_BEFORE_SIGNAL_REVERSED,
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
    _empty_workspace,
    _mutation,
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


class _TimelineConfiguration(_FoundationConfiguration):
    def __init__(self, timeline, **kwargs):
        super().__init__(timeline=timeline, **kwargs)
        self.timeline = timeline
        self.batches: list[list] = []

    def apply_actions(self, actions):
        batch = list(actions)
        self.batches.append(batch)
        voice_ports = [
            item.interface for item in batch
            if (
                type(item).__name__ == "ConfigureAccessPort"
                and item.voice_vlan_id == VOICE_VLAN_ID
            )
        ]
        if voice_ports:
            self.timeline.append("voice_vlan:" + ",".join(voice_ports))
        return super().apply_actions(batch)


class _BootstrapCallControl(_FoundationCallControl):
    def __init__(
        self,
        timeline,
        *,
        p1_acquired: bool,
        p2_acquired: bool,
        refuse_bootstrap: bool = False,
        p1_addressed: bool = False,
        p2_addressed: bool = False,
        post_apply_unreadable_reads: int = 0,
    ):
        super().__init__()
        self.timeline = timeline
        self.acquired = {"_P1": p1_acquired, "_P2": p2_acquired}
        self.addressed = {"_P1": p1_addressed, "_P2": p2_addressed}
        self.refuse_bootstrap = refuse_bootstrap
        self.post_apply_unreadable_reads = post_apply_unreadable_reads
        self.post_apply_reads = 0

    def apply_actions(self, actions):
        batch = list(actions)
        self.timeline.append("voice_bootstrap")
        self.applied.extend(batch)
        return [
            _mutation(
                action_id=item.id,
                applied=not self.refuse_bootstrap,
                message="refused" if self.refuse_bootstrap else "",
            )
            for item in batch
        ]

    def inspect_call_control(self, device_name):
        self.inspected.append(device_name)
        if not self.applied:
            return None
        self.post_apply_reads += 1
        if self.post_apply_reads <= self.post_apply_unreadable_reads:
            return None
        return self.table

    def _for(self, endpoint_device_name: str):
        suffix = next(
            suffix for suffix in self.acquired
            if endpoint_device_name.endswith(suffix)
        )
        acquired = self.acquired[suffix]
        addressed = acquired or self.addressed[suffix]
        ipv4 = "10.93.0.11" if suffix == "_P1" else "10.93.0.10"
        if acquired:
            return _Registration(
                status="ActionExecutionStatus.VERIFIED",
                direct_readback="FieldVerificationStatus.VERIFIED",
                endpoint_ipv4=ipv4,
                endpoint_dhcp_enabled=True,
            )
        return _Registration(
            status="ActionExecutionStatus.FAILED",
            direct_readback=(
                "FieldVerificationStatus.VERIFIED" if addressed else ""
            ),
            endpoint_ipv4=ipv4 if addressed else "",
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
    refuse_bootstrap=False,
    control_addressed=False,
    post_apply_unreadable_reads=0,
    interfaces=None,
):
    timeline: list[str] = []
    p1_acquired = intervention_acquired if reverse_roles else control_acquired
    p2_acquired = control_acquired if reverse_roles else intervention_acquired
    p1_addressed = control_addressed if not reverse_roles else False
    p2_addressed = control_addressed if reverse_roles else False
    binding_addresses = []
    if p1_acquired or p1_addressed:
        binding_addresses.append("10.93.0.11")
    if p2_acquired or p2_addressed:
        binding_addresses.append("10.93.0.10")
    configuration_kwargs = {
        "bindings": [_Binding(item) for item in binding_addresses],
        "stp_sequence": [
            [_StpInstance(VOICE_VLAN_ID, ())],
            _paired_stp("FWD", "LIS"),
            _paired_stp("FWD", "FWD"),
        ],
    }
    if interfaces is not None:
        configuration_kwargs["interfaces"] = interfaces
    configuration = _TimelineConfiguration(
        timeline,
        **configuration_kwargs,
    )
    call_control = _BootstrapCallControl(
        timeline,
        p1_acquired=p1_acquired,
        p2_acquired=p2_acquired,
        refuse_bootstrap=refuse_bootstrap,
        p1_addressed=p1_addressed,
        p2_addressed=p2_addressed,
        post_apply_unreadable_reads=post_apply_unreadable_reads,
    )
    endpoints = _Endpoints()
    clock = _Clock()
    result = PositiveVoiceSliceQualifier(
        _Physical(_empty_workspace()),
        configuration,
        call_control,
        endpoints,
        _ModeRuntime(),
        token="bootstrap-order",
        bootstrap_before_voice_vlan=True,
        bootstrap_roles_reversed=reverse_roles,
        gate_timeout_seconds=10.0,
        gate_interval_seconds=2.0,
        gate_clock=clock,
        gate_sleeper=clock.sleep,
    ).qualify("2811", "3560-24PS", "7960")
    return result, configuration, call_control, endpoints, timeline


def test_mode_names_the_bootstrap_ordering_variable():
    result, *_ = _run()

    assert result.experiment == EXPERIMENT_VOICE_BOOTSTRAP_BEFORE_SIGNAL


def test_both_ports_start_data_only_then_straddle_one_bootstrap_dispatch():
    result, configuration, _, _, timeline = _run()

    batches = _access_batches(configuration)
    assert [
        [item.voice_vlan_id for item in batch] for batch in batches
    ] == [[None, None], [VOICE_VLAN_ID], [VOICE_VLAN_ID]]
    assert timeline.index("voice_vlan:" + P1) < timeline.index(
        "voice_bootstrap"
    ) < timeline.index("voice_vlan:" + P2)
    assert result.control_voice_bootstrap_dispatch == NOT_APPLIED
    assert result.voice_bootstrap_dispatch == APPLIED


def test_refused_bootstrap_fails_closed_before_intervention_signal():
    result, configuration, _, _, _ = _run(refuse_bootstrap=True)

    assert result.voice_bootstrap_dispatch == NOT_APPLIED
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_VOICE_BOOTSTRAP_UNREADY
    )
    assert len(_access_batches(configuration)) == 2


def test_unready_network_never_signals_either_phone():
    result, configuration, *_ = _run(interfaces=[])

    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_PRECONTROL_FOUNDATION_UNREADY
    )
    assert len(_access_batches(configuration)) == 1


def test_network_and_bootstrap_foundations_are_kept_separate():
    result, *_ = _run()

    assert result.pre_control_foundation_status == VERIFIED
    assert result.pre_control_foundation is not None
    assert result.pre_control_foundation.dhcp_pool_table_readback == VERIFIED
    assert result.pre_control_foundation.call_control_table == UNOBSERVABLE
    assert result.bootstrap_foundation_ready == VERIFIED
    assert result.pre_intervention_foundation is not None
    assert result.pre_intervention_foundation.call_control_table == VERIFIED


def test_bootstrap_readiness_waits_boundedly_for_call_control_readback():
    result, *_ = _run(post_apply_unreadable_reads=1)

    assert result.bootstrap_foundation_wait is not None
    assert result.bootstrap_foundation_wait.status == VERIFIED
    assert result.bootstrap_foundation_wait.samples == 2
    assert result.bootstrap_foundation_wait.first_verified_ms == 2_000


def test_mode_never_arms_or_toggles_phone_dhcp():
    _, _, _, endpoints, _ = _run()

    assert endpoints.armed == []


def test_control_failure_and_intervention_success_is_the_causal_verdict():
    result, *_ = _run()

    assert [item.addressed for item in result.phones] == [NO, YES]
    assert result.control_matching_binding == NO
    assert result.intervention_matching_binding == YES
    assert result.causal_experiment_result == (
        VOICE_BOOTSTRAP_BEFORE_SIGNAL_CAUSAL_EFFECT_OBSERVED
    )
    assert result.voice_bootstrap_controls_acquisition == YES


def test_control_lease_without_sccp_is_not_full_acquisition():
    result, *_ = _run(control_addressed=True)

    assert result.phones[0].addressed == YES
    assert result.control_matching_binding == YES
    assert result.phones[0].registration == NOT_REGISTERED
    assert result.causal_experiment_result == (
        VOICE_BOOTSTRAP_BEFORE_SIGNAL_CAUSAL_EFFECT_OBSERVED
    )


def test_both_phones_acquiring_refutes_bootstrap_order_effect():
    result, *_ = _run(control_acquired=True, intervention_acquired=True)

    assert result.causal_experiment_result == (
        VOICE_BOOTSTRAP_BEFORE_SIGNAL_NO_EFFECT
    )


def test_both_phones_failing_reports_bootstrap_insufficient():
    result, *_ = _run(
        control_acquired=False,
        intervention_acquired=False,
    )

    assert result.causal_experiment_result == (
        VOICE_BOOTSTRAP_BEFORE_SIGNAL_INSUFFICIENT
    )


def test_reversed_outcome_is_not_promoted_to_the_expected_effect():
    result, *_ = _run(
        control_acquired=True,
        intervention_acquired=False,
    )

    assert result.causal_experiment_result == (
        VOICE_BOOTSTRAP_BEFORE_SIGNAL_REVERSED
    )


def test_roles_can_be_reversed_without_changing_the_question():
    result, configuration, *_ = _run(reverse_roles=True)

    batches = _access_batches(configuration)
    assert [item.interface for item in batches[1]] == [P2]
    assert [item.interface for item in batches[2]] == [P1]
    assert result.bootstrap_roles_reversed is True
    assert result.causal_experiment_result == (
        VOICE_BOOTSTRAP_BEFORE_SIGNAL_CAUSAL_EFFECT_OBSERVED
    )


def test_live_runner_exposes_and_serializes_the_experiment():
    source = Path("tools/cp_scale_positive_voice_ab_live.py").read_text(
        encoding="utf-8",
    )

    assert '"--bootstrap-before-voice-vlan"' in source
    assert '"--reverse-bootstrap-roles"' in source
    assert "bootstrap_before_voice_vlan=bootstrap_before_voice_vlan" in source
    for key in (
        "voice_bootstrap_dispatch",
        "control_voice_bootstrap_dispatch",
        "bootstrap_foundation_ready",
        "bootstrap_foundation_wait",
        "bootstrap_roles_reversed",
        "voice_bootstrap_controls_acquisition",
    ):
        assert f'"{key}"' in source
