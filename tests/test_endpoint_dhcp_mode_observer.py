"""S3-02: E5 reads DHCP mode on the exact manifest-bound interface."""

from __future__ import annotations

import json
from dataclasses import dataclass

from packet_tracer_mcp.application.use_cases.apply_configuration import (
    ConfigurationApplicator,
)
from packet_tracer_mcp.application.use_cases.foundational_evidence import (
    derive_service_foundational_statuses,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigurationPlan,
    SetEndpointDhcp,
    VerificationExpectation,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
    RuntimeConfigurationTarget,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    FoundationalServiceRequirement,
    ServicePlan,
)
from packet_tracer_mcp.domain.enterprise.services.configuration_compiler import (
    configuration_plan_semantic_hash,
)
from packet_tracer_mcp.infrastructure.execution.endpoint_dhcp_mode_observer import (
    DhcpModeObservation,
    PacketTracerEndpointDhcpModeObserver,
    endpoint_dhcp_mode_read_js,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)


def _expectation(interface: str = "FastEthernet0") -> VerificationExpectation:
    return VerificationExpectation(
        id="verify-mode",
        action_id="endpoint-dhcp",
        kind=VerificationKind.ENDPOINT_DHCP_MODE,
        device_id="client-1",
        device_name="PC-01",
        expected={"mode": "dhcp", "interface": interface},
    )


def test_mode_script_names_the_exact_interface_and_only_the_documented_getter():
    """Generate only the exact documented mode read for the bound port."""
    script = endpoint_dhcp_mode_read_js('PC "quoted"', "FastEthernet0")

    assert json.dumps('PC "quoted"') in script
    assert json.dumps("FastEthernet0") in script
    assert "isDhcpClientOn" in script
    assert "getIpAddress" not in script
    assert "getSubnetMask" not in script


def test_observer_accepts_only_a_typed_fresh_mode_payload():
    """Preserve a coherent correlated mode result as fresh evidence."""
    raw = json.dumps(
        {
            "found": True,
            "port_found": True,
            "interface": "FastEthernet0",
            "mode_channel": True,
            "mode_value_valid": True,
            "mode_error": False,
            "dhcp_mode": True,
        }
    )

    observed = PacketTracerEndpointDhcpModeObserver(lambda _js, _timeout: raw).observe(
        "PC-01", "FastEthernet0"
    )

    assert observed == DhcpModeObservation(
        runtime_device_name="PC-01",
        interface="FastEthernet0",
        device_found=True,
        port_found=True,
        mode_channel=True,
        dhcp_mode=True,
        fresh_evidence=True,
    )


@dataclass
class _ModeReader:
    observation: DhcpModeObservation

    def observe(self, _device_name: str, _interface: str) -> DhcpModeObservation:
        return self.observation


def _runtime(observation: DhcpModeObservation):
    return PacketTracerEnterpriseConfigurationRuntime(
        lambda: [],
        lambda _js: True,
        lambda _js, _timeout: None,
        endpoint_dhcp_mode_observer=_ModeReader(observation),
        endpoint_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )


def _observation(**updates) -> DhcpModeObservation:
    values = dict(
        runtime_device_name="PC-01",
        interface="FastEthernet0",
        device_found=True,
        port_found=True,
        mode_channel=True,
        dhcp_mode=True,
        fresh_evidence=True,
        failure_reason="",
    )
    values.update(updates)
    return DhcpModeObservation(**values)


def test_true_mode_is_verified_without_waiting_for_an_address():
    """Treat true mode as bootstrap evidence without an address claim."""
    row = _runtime(_observation())._verify_endpoint_dhcp_mode(_expectation())

    assert row.status is ActionExecutionStatus.VERIFIED
    assert row.fields == {"dhcp_mode": FieldVerificationStatus.VERIFIED}
    assert row.evidence_method == "structured_endpoint_dhcp_mode"
    assert row.fresh_evidence is True


def test_false_mode_is_a_fresh_contradiction():
    """Treat a fresh false flag as a contradiction, not an absence."""
    row = _runtime(_observation(dhcp_mode=False))._verify_endpoint_dhcp_mode(
        _expectation()
    )

    assert row.status is ActionExecutionStatus.FAILED
    assert row.fields["dhcp_mode"] is FieldVerificationStatus.FAILED


def test_wrong_interface_and_unreadable_mode_are_unobservable():
    """Fail closed when subject identity or the getter channel is missing."""
    wrong = _runtime(
        _observation(interface="FastEthernet1")
    )._verify_endpoint_dhcp_mode(_expectation())
    unreadable = _runtime(
        _observation(mode_channel=False, dhcp_mode=None, fresh_evidence=False)
    )._verify_endpoint_dhcp_mode(_expectation())

    assert wrong.status is ActionExecutionStatus.UNOBSERVABLE
    assert unreadable.status is ActionExecutionStatus.UNOBSERVABLE


def test_invalid_native_mode_cannot_become_an_e6_foundation():
    """Carry an invalid getter result through real E5 verification and gating."""
    action = SetEndpointDhcp(
        id="endpoint-dhcp",
        phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
        device_id="client-1",
        device_name="PC-01",
        site_id="hq",
        interface="FastEthernet0",
        segment_id="hq-data",
        network="192.0.2.0",
        prefix=24,
        netmask="255.255.255.0",
        gateway="192.0.2.1",
        required_capability="endpoint_dhcp",
    )
    plan = ConfigurationPlan(
        id="cfg-invalid-dhcp-mode",
        source_topology_id="topology",
        source_topology_hash="topology-hash",
        actions=[action],
        verification_expectations=[_expectation()],
    )
    plan.semantic_hash = configuration_plan_semantic_hash(plan)
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        lambda: [],
        lambda _js: True,
        lambda _js, _timeout: None,
        endpoint_dhcp_mode_observer=_ModeReader(
            _observation(
                dhcp_mode=None,
                fresh_evidence=False,
                failure_reason="mode_value_invalid",
            )
        ),
        endpoint_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )
    applied = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash="topology-hash",
        capabilities={},
    )
    services = ServicePlan(
        id="services",
        source_topology_id="topology",
        source_topology_hash="topology-hash",
        source_configuration_id=plan.id,
        source_configuration_hash=plan.semantic_hash,
        foundational_requirements=[
            FoundationalServiceRequirement(
                id="foundation-mode",
                device_id="client-1",
                device_name="PC-01",
                model="PC-PT",
                ipv4="",
                segment_id="hq-data",
                configuration_action_id=action.id,
                kind="endpoint_dhcp_mode",
            )
        ],
    )

    statuses = derive_service_foundational_statuses(services, applied)

    assert applied.verification_results[0].status is ActionExecutionStatus.UNOBSERVABLE
    assert statuses == {action.id: ActionExecutionStatus.UNOBSERVABLE}


def test_real_e5_route_founds_e6_on_mode_true_with_no_address():
    """Carry the actual E5 reader result into the E6 foundation predicate."""
    action = SetEndpointDhcp(
        id="endpoint-dhcp",
        phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
        device_id="client-1",
        device_name="PC-01",
        site_id="hq",
        interface="FastEthernet0",
        segment_id="hq-data",
        network="192.0.2.0",
        prefix=24,
        netmask="255.255.255.0",
        gateway="192.0.2.1",
        required_capability="endpoint_dhcp",
    )
    expectation = _expectation()
    plan = ConfigurationPlan(
        id="cfg-dhcp-mode",
        source_topology_id="topology",
        source_topology_hash="topology-hash",
        actions=[action],
        verification_expectations=[expectation],
    )
    plan.semantic_hash = configuration_plan_semantic_hash(plan)
    payload = json.dumps(
        {
            "found": True,
            "port_found": True,
            "interface": "FastEthernet0",
            "mode_channel": True,
            "mode_value_valid": True,
            "mode_error": False,
            "dhcp_mode": True,
        }
    )
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        lambda: [
            RuntimeConfigurationTarget(
                device_name="PC-01",
                model="PC-PT",
                interfaces=["FastEthernet0"],
            ).model_dump(mode="json")
        ],
        lambda _script: True,
        lambda _script, _timeout: payload,
        endpoint_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )

    applied = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash="topology-hash",
        capabilities={},
    )
    service_plan = ServicePlan(
        id="services",
        source_topology_id="topology",
        source_topology_hash="topology-hash",
        source_configuration_id=plan.id,
        source_configuration_hash=plan.semantic_hash,
        foundational_requirements=[
            FoundationalServiceRequirement(
                id="foundation-mode",
                device_id="client-1",
                device_name="PC-01",
                model="PC-PT",
                ipv4="",
                segment_id="hq-data",
                configuration_action_id=action.id,
                kind="endpoint_dhcp_mode",
            )
        ],
    )

    statuses = derive_service_foundational_statuses(service_plan, applied)

    assert applied.action_results[0].status is ActionExecutionStatus.APPLIED
    assert applied.verification_results[0].status is ActionExecutionStatus.VERIFIED
    assert statuses == {action.id: ActionExecutionStatus.VERIFIED}
