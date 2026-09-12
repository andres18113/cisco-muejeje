"""Bounded STP read-back retry when source provenance is transiently absent."""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureSpanningTree,
    ControlPlaneCapabilityDimension,
    ControlPlanePhase,
    ControlPlaneVerificationExpectation,
    ControlPlaneVerificationKind,
    StpMode,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_control_plane_runtime import (
    PacketTracerEnterpriseControlPlaneRuntime,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    DeviceIdentityProvenance,
    IosCommandResult,
    OperationalQueryId,
)
from test_ios_terminal import _PT_9_0_1_0858_STP_ROOT


class _SequenceIos:
    def __init__(self, outcomes: list[IosCommandResult]) -> None:
        self.outcomes = iter(outcomes)
        self.calls = 0

    def execute(self, *_args: object, **_kwargs: object) -> IosCommandResult:
        self.calls += 1
        return next(self.outcomes)


def _show(provenance: DeviceIdentityProvenance) -> IosCommandResult:
    confirmed = provenance is DeviceIdentityProvenance.CONFIRMED_UNIQUE
    return IosCommandResult(
        device_name="SW",
        query_id=OperationalQueryId.SHOW_SPANNING_TREE,
        executed=True,
        output=_PT_9_0_1_0858_STP_ROOT,
        fresh_output_observed=True,
        output_complete=True,
        observed_device_name="SW" if confirmed else "",
        device_identity_provenance=provenance.value,
    )


def _exercise(*provenances: DeviceIdentityProvenance):
    action = ConfigureSpanningTree(
        id="cp/stp/sw",
        phase=ControlPlanePhase.L2_FOUNDATION,
        device_id="sw",
        device_name="SW",
        model="2960-24TT",
        site_id="site",
        required_capability=(
            ControlPlaneCapabilityDimension.STP_RAPID_PVST_CONFIG
        ),
        mode=StpMode.RAPID_PVST,
        vlan_ids=[1],
    )
    expectation = ControlPlaneVerificationExpectation(
        id="cp/verify-stp/sw",
        kind=ControlPlaneVerificationKind.STP_STATE,
        action_id=action.id,
        device_id=action.device_id,
        required_capability=ControlPlaneCapabilityDimension.STP_STATE,
        expected={
            "mode": StpMode.RAPID_PVST.value,
            "vlan_ids": [1],
            "source_device_name": "SW",
        },
    )
    ios = _SequenceIos([_show(item) for item in provenances])
    mutations: list[str] = []
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [],
        lambda payload: mutations.append(payload) or True,
        lambda _payload, _timeout: None,
        ios_executor=ios,
        stp_convergence_attempts=2,
        stp_convergence_timeout_seconds=1.0,
        stp_convergence_interval_seconds=0.0,
        sleeper=lambda _seconds: None,
    )
    runtime.apply_actions([action])
    mutation_count = len(mutations)
    result = runtime.verify([expectation])[0]
    return result, ios.calls, mutation_count, len(mutations)


def test_stp_retries_transiently_unattributed_source_without_redispatch() -> None:
    """LIVE Floor3 proved five early STP reads lacked only source identity."""

    result, calls, mutation_count, final_mutation_count = _exercise(
        DeviceIdentityProvenance.NOT_OBSERVED,
        DeviceIdentityProvenance.CONFIRMED_UNIQUE,
    )

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fields["source_device_name"] is FieldVerificationStatus.VERIFIED
    assert result.convergence is not None
    assert result.convergence.attempts == 2
    assert calls == 2
    assert final_mutation_count == mutation_count


def test_stp_stays_unobservable_when_bounded_retries_never_attribute_source() -> None:
    result, calls, mutation_count, final_mutation_count = _exercise(
        DeviceIdentityProvenance.NOT_OBSERVED,
        DeviceIdentityProvenance.AMBIGUOUS,
    )

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.fields["source_device_name"] is (
        FieldVerificationStatus.UNOBSERVABLE
    )
    assert result.convergence is not None
    assert result.convergence.attempts == 2
    assert result.convergence.last_observable_state == "source_device_unattributed"
    assert calls == 2
    assert final_mutation_count == mutation_count
