"""State-authorized DHCP endpoint reconciliation for CP-SCALE Configuration."""

from __future__ import annotations

from types import SimpleNamespace

from src.packet_tracer_mcp.application.cp_scale_live.configuration_stage import (
    CPScaleConfigurationStage,
)
from src.packet_tracer_mcp.application.cp_scale_live import (
    endpoint_dhcp_reassertion,
)
from src.packet_tracer_mcp.application.use_cases.apply_configuration import (
    ConfigurationApplicator,
)
from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigurationPlan,
    ConfigureAccessPort,
    SetEndpointDhcp,
    VerificationExpectation,
    VerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConvergenceReport,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
    RuntimeVerification,
    VerificationResult,
    VoiceSignalBarrierResult,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    EnvironmentFingerprint,
)
from src.packet_tracer_mcp.domain.enterprise.models.forwarding import (
    ForwardingAddressObservation,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)


class _EndpointObserver:
    def __init__(self, *values: tuple[str, str]) -> None:
        self._values = values
        self.calls = 0

    def observe(
        self,
        runtime_device_name: str,
        interface: str,
    ) -> ForwardingAddressObservation:
        index = min(self.calls, len(self._values) - 1)
        ipv4, netmask = self._values[index]
        self.calls += 1
        return ForwardingAddressObservation(
            runtime_device_name=runtime_device_name,
            interface=interface,
            device_found=True,
            port_found=True,
            address_channel=True,
            ipv4=ipv4,
            netmask=netmask,
            fresh_evidence=True,
        )


def _endpoint_expectation() -> VerificationExpectation:
    return VerificationExpectation(
        id="cfg/verify/dhcp-pc",
        action_id="cfg/endpoint-dhcp/pc",
        kind=VerificationKind.ENDPOINT_ADDRESSING,
        device_id="endpoint/pc",
        device_name="PC",
        expected={
            "interface": "FastEthernet0",
            "mode": "dhcp",
            "network": "172.16.10.0",
            "prefix": 24,
            "netmask": "255.255.255.0",
            "gateway": "172.16.10.1",
            "dns": "",
        },
    )


def test_endpoint_timeout_retains_the_exact_terminal_sample_without_an_extra_read() -> None:
    """A retry decision needs the value inside the wait, not a later read."""

    observer = _EndpointObserver(("", ""))
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: None,
        endpoint_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
        endpoint_address_observer=observer,
    )

    result = runtime.verify([_endpoint_expectation()])[0]

    assert result.status is ActionExecutionStatus.FAILED
    assert observer.calls == 1
    assert result.convergence is not None
    assert result.convergence.details == {
        "kind": "endpoint_addressing",
        "device_name": "PC",
        "interface": "FastEthernet0",
        "sample_rounds": 1,
        "transitions": [{
            "sample_round": 1,
            "device_found": True,
            "port_found": True,
            "address_channel": True,
            "interface": "FastEthernet0",
            "ipv4": "",
            "netmask": "",
            "fresh_evidence": True,
            "failure_reason": "",
        }],
        "last_observation": {
            "device_found": True,
            "port_found": True,
            "address_channel": True,
            "interface": "FastEthernet0",
            "ipv4": "",
            "netmask": "",
            "fresh_evidence": True,
            "failure_reason": "",
        },
    }


def _application(
    plan: ConfigurationPlan,
    *,
    endpoint_verified: bool,
    mutation_ids: list[str],
) -> ConfigurationApplicationResult:
    access, endpoint = plan.actions
    endpoint_fields = {
        "ipv4": (
            FieldVerificationStatus.VERIFIED
            if endpoint_verified else FieldVerificationStatus.FAILED
        ),
        "netmask": (
            FieldVerificationStatus.VERIFIED
            if endpoint_verified else FieldVerificationStatus.FAILED
        ),
        "gateway": FieldVerificationStatus.UNOBSERVABLE,
        "dns": FieldVerificationStatus.UNOBSERVABLE,
    }
    endpoint_status = (
        ActionExecutionStatus.PARTIAL
        if endpoint_verified else ActionExecutionStatus.FAILED
    )
    ipv4 = "172.16.10.20" if endpoint_verified else ""
    netmask = "255.255.255.0" if endpoint_verified else ""
    endpoint_result = VerificationResult(
        expectation_id="cfg/verify/dhcp-pc",
        action_id=endpoint.id,
        status=endpoint_status,
        evidence_method="structured_endpoint_getters",
        fresh_evidence=True,
        fields=endpoint_fields,
        convergence=ConvergenceReport(
            attempts=2,
            final_status=endpoint_status,
            last_observable_state="measured",
            details={
                "kind": "endpoint_addressing",
                "device_name": "PC",
                "interface": "FastEthernet0",
                "sample_rounds": 2,
                "transitions": [],
                "last_observation": {
                    "device_found": True,
                    "port_found": True,
                    "address_channel": True,
                    "interface": "FastEthernet0",
                    "ipv4": ipv4,
                    "netmask": netmask,
                    "fresh_evidence": True,
                    "failure_reason": "",
                },
            },
        ),
    )
    return ConfigurationApplicationResult(
        config_plan_id=plan.id,
        config_semantic_hash=plan.semantic_hash,
        source_topology_hash=plan.source_topology_hash,
        status=ConfigurationApplicationStatus.PARTIAL,
        failure_code=(
            ConfigurationFailureCode.NONE
            if endpoint_verified
            else ConfigurationFailureCode.VERIFICATION_FAILED
        ),
        action_results=[
            ActionApplicationResult(
                action_id=access.id,
                status=ActionExecutionStatus.APPLIED,
            ),
            ActionApplicationResult(
                action_id=endpoint.id,
                status=ActionExecutionStatus.APPLIED,
            ),
        ],
        mutation_action_ids=mutation_ids,
        retained_action_ids=[
            action.id for action in plan.actions
            if action.id not in mutation_ids
        ],
        verification_results=[
            VerificationResult(
                expectation_id="cfg/verify/access-pc",
                action_id=access.id,
                status=ActionExecutionStatus.VERIFIED,
                evidence_method="switch_port_object_state",
                fresh_evidence=True,
                fields={
                    "interface": FieldVerificationStatus.VERIFIED,
                    "vlan_id": FieldVerificationStatus.VERIFIED,
                },
            ),
            endpoint_result,
        ],
    )


def _reassertion_plan() -> ConfigurationPlan:
    access = ConfigureAccessPort(
        id="cfg/access/pc",
        phase=ConfigurationPhase.L2_INTERFACES,
        device_id="switch",
        device_name="Switch",
        site_id="large-branch",
        interface="FastEthernet0/1",
        data_vlan_id=10,
        endpoint_ids=["endpoint/pc"],
    )
    endpoint = SetEndpointDhcp(
        id="cfg/endpoint-dhcp/pc",
        phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
        device_id="endpoint/pc",
        device_name="PC",
        site_id="large-branch",
        interface="FastEthernet0",
        segment_id="large-branch-data",
        network="172.16.10.0",
        prefix=24,
        netmask="255.255.255.0",
        gateway="172.16.10.1",
        depends_on=[access.id],
        apply_dependencies=[access.id],
    )
    return ConfigurationPlan(
        id="cfg",
        semantic_hash="configuration",
        source_topology_id="topology",
        source_topology_hash="topology",
        actions=[access, endpoint],
        verification_expectations=[
            VerificationExpectation(
                id="cfg/verify/access-pc",
                action_id=access.id,
                kind=VerificationKind.ACCESS_PORT,
                device_id=access.device_id,
                device_name=access.device_name,
                expected={
                    "interface": access.interface,
                    "vlan_id": access.data_vlan_id,
                },
            ),
            _endpoint_expectation(),
        ],
    )


def test_only_exact_fresh_dhcp_absence_authorizes_one_delta_reassertion() -> None:
    plan = _reassertion_plan()
    first = _application(
        plan,
        endpoint_verified=False,
        mutation_ids=[action.id for action in plan.actions],
    )

    assert endpoint_dhcp_reassertion.retryable_endpoint_dhcp_absence(
        plan,
        first,
    )
    mutation_ids, retained = (
        endpoint_dhcp_reassertion.endpoint_dhcp_reassertion_scope(
            plan,
            first,
        )
    )
    assert mutation_ids == ("cfg/endpoint-dhcp/pc",)
    assert [item.action_id for item in retained] == ["cfg/access/pc"]

    contradicted = first.model_copy(deep=True)
    last = contradicted.verification_results[-1].convergence.details[
        "last_observation"
    ]
    last["ipv4"] = "192.0.2.44"
    last["netmask"] = "255.255.255.0"
    assert not (
        endpoint_dhcp_reassertion.retryable_endpoint_dhcp_absence(
            plan,
            contradicted,
        )
    )

    retained = first.model_copy(deep=True)
    retained.mutation_action_ids = ["cfg/access/pc"]
    retained.retained_action_ids = ["cfg/endpoint-dhcp/pc"]
    assert not (
        endpoint_dhcp_reassertion.retryable_endpoint_dhcp_absence(
            plan,
            retained,
        )
    )


def test_configuration_stage_preserves_failed_attempt_then_reasserts_only_the_delta() -> None:
    plan = _reassertion_plan()
    class _Runtime:
        def __init__(self) -> None:
            self.apply_calls: list[list[str]] = []
            self.verify_calls = 0

        def inventory(self):
            return [
                RuntimeConfigurationTarget(
                    device_name="Switch",
                    model="2960-24TT",
                    interfaces=["FastEthernet0/1"],
                ),
                RuntimeConfigurationTarget(
                    device_name="PC",
                    model="PC-PT",
                    interfaces=["FastEthernet0"],
                ),
            ]

        def apply_actions(self, actions):
            self.apply_calls.append([item.id for item in actions])
            return [
                RuntimeActionMutation(action_id=item.id, applied=True)
                for item in actions
            ]

        def verify(self, expectations):
            self.verify_calls += 1
            template = _application(
                plan,
                endpoint_verified=self.verify_calls > 1,
                mutation_ids=[],
            )
            by_id = {
                item.expectation_id: item
                for item in template.verification_results
            }
            return [
                RuntimeVerification(
                    expectation_id=item.id,
                    status=by_id[item.id].status,
                    evidence_method=by_id[item.id].evidence_method,
                    fresh_evidence=by_id[item.id].fresh_evidence,
                    fields=by_id[item.id].fields,
                    convergence=by_id[item.id].convergence,
                )
                for item in expectations
            ]

    runtime = _Runtime()
    stage = CPScaleConfigurationStage(
        ConfigurationApplicator(runtime),
        serial_wait=lambda _projection: (True, []),
    )
    projection = SimpleNamespace(
        stage=CPScaleCanonicalStage.FLOOR3,
        configuration=plan,
        topology=SimpleNamespace(physical_identity_hash="topology"),
    )
    request = SimpleNamespace(
        projection=projection,
        continuity=SimpleNamespace(previous_configuration=None),
        fingerprint=EnvironmentFingerprint(),
        composition=SimpleNamespace(capabilities={}),
    )

    result = stage.execute(
        request,
        None,
        tuple(action.id for action in plan.actions),
        defer_voice_signal=False,
        configuration_phase_observer=lambda _phase, _ids: None,
    )

    assert result.accepted
    assert result.configuration is result.attempts[1]
    assert len(result.attempts) == 2
    assert result.report.contradictions[0]
    assert result.report.contradictions[1] == ""
    assert runtime.apply_calls == [
        ["cfg/access/pc"],
        ["cfg/endpoint-dhcp/pc"],
        ["cfg/endpoint-dhcp/pc"],
    ]
    assert result.attempts[0].mutation_action_ids == [
        "cfg/access/pc",
        "cfg/endpoint-dhcp/pc",
    ]
    assert result.attempts[1].mutation_action_ids == [
        "cfg/endpoint-dhcp/pc",
    ]
    assert result.attempts[1].retained_action_ids == ["cfg/access/pc"]
    assert [
        item.action_id
        for item in result.attempts[0].execution_journal.entries
    ] == ["cfg/access/pc", "cfg/endpoint-dhcp/pc"]
    assert [
        item.action_id
        for item in result.attempts[1].execution_journal.entries
    ] == ["cfg/endpoint-dhcp/pc"]
    assert result.report.reread_scope is not None
    assert result.report.reread_scope.verified is False


def test_dhcp_reassertion_preserves_the_existing_data_only_voice_barrier() -> None:
    """The second attempt may not signal Voice while repairing data DHCP."""

    plan = _reassertion_plan()
    first = _application(
        plan,
        endpoint_verified=False,
        mutation_ids=[action.id for action in plan.actions],
    )
    voice = ConfigureAccessPort(
        id="cfg/access/voice",
        phase=ConfigurationPhase.L2_INTERFACES,
        device_id="switch",
        device_name="Switch",
        site_id="large-branch",
        interface="FastEthernet0/2",
        data_vlan_id=10,
        voice_vlan_id=20,
        endpoint_ids=["endpoint/phone"],
    )
    voice_expectation = VerificationExpectation(
        id="cfg/verify/access-voice",
        action_id=voice.id,
        kind=VerificationKind.ACCESS_PORT,
        device_id=voice.device_id,
        device_name=voice.device_name,
        expected={
            "interface": voice.interface,
            "vlan_id": voice.data_vlan_id,
            "voice_vlan_id": voice.voice_vlan_id,
        },
    )
    plan.actions.append(voice)
    plan.verification_expectations.append(voice_expectation)
    preparation = ActionApplicationResult(
        action_id=voice.id,
        status=ActionExecutionStatus.APPLIED,
    )
    first.action_results.append(ActionApplicationResult(
        action_id=voice.id,
        status=ActionExecutionStatus.PARTIAL,
        failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
    ))
    first.mutation_action_ids.append(voice.id)
    first.verification_results.append(VerificationResult(
        expectation_id=voice_expectation.id,
        action_id=voice.id,
        status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
        message="Blocked by the failed data endpoint.",
    ))
    first.voice_signal_barrier = VoiceSignalBarrierResult(
        required=True,
        deferred_action_ids=[voice.id],
        preparation_results=[preparation],
        foundation_status=ActionExecutionStatus.FAILED,
        signal_status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
    )

    assert endpoint_dhcp_reassertion.retryable_endpoint_dhcp_absence(
        plan,
        first,
        allow_deferred_voice_signal=True,
    )
    mutation_ids, retained = (
        endpoint_dhcp_reassertion.endpoint_dhcp_reassertion_scope(
            plan,
            first,
            allow_deferred_voice_signal=True,
        )
    )

    assert mutation_ids == ("cfg/endpoint-dhcp/pc",)
    retained_by_id = {item.action_id: item for item in retained}
    assert retained_by_id[voice.id].status is ActionExecutionStatus.APPLIED
