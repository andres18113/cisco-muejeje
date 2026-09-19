"""S3-02: E5 reads DHCP mode on the exact manifest-bound interface."""

from __future__ import annotations

import json
from dataclasses import dataclass

from packet_tracer_mcp.domain.enterprise.models.configuration import (
    VerificationExpectation,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
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
