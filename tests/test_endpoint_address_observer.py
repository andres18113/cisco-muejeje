"""One endpoint getter implementation serves E5 and forwarding bindings."""

from __future__ import annotations

import json

from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    VerificationExpectation,
    VerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from src.packet_tracer_mcp.infrastructure.execution.endpoint_address_observer import (
    PacketTracerEndpointAddressObserver,
    endpoint_address_read_js,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)


def test_e5_endpoint_verification_executes_the_shared_exact_interface_getter():
    scripts: list[str] = []

    def send_and_wait(script: str, _timeout: float) -> str:
        scripts.append(script)
        return json.dumps({
            "found": True,
            "port_found": True,
            "interface": "FastEthernet0",
            "address_channel": True,
            "ipv4": "172.18.10.24",
            "netmask": "255.255.255.0",
        })

    runtime = PacketTracerEnterpriseConfigurationRuntime(
        lambda: [],
        lambda _payload: True,
        send_and_wait,
        endpoint_timeout_seconds=0,
        convergence_interval_seconds=0,
    )
    expectation = VerificationExpectation(
        id="verify/endpoint",
        action_id="cfg/endpoint",
        kind=VerificationKind.ENDPOINT_ADDRESSING,
        device_id="endpoint/multilayer/pc/001",
        device_name="MULTILAYER-PC-01",
        expected={
            "mode": "dhcp",
            "interface": "FastEthernet0",
            "network": "172.18.10.0",
            "prefix": 24,
            "netmask": "255.255.255.0",
            "gateway": "172.18.10.1",
            "dns": "8.8.8.8",
        },
    )

    result = runtime._verify_endpoint(expectation)

    assert scripts
    assert set(scripts) == {
        endpoint_address_read_js("MULTILAYER-PC-01", "FastEthernet0"),
    }
    assert result.status is ActionExecutionStatus.PARTIAL
    assert result.fields["ipv4"] is FieldVerificationStatus.VERIFIED
    assert result.fields["netmask"] is FieldVerificationStatus.VERIFIED
    assert result.fields["gateway"] is FieldVerificationStatus.UNOBSERVABLE
    assert result.fields["dns"] is FieldVerificationStatus.UNOBSERVABLE


def test_endpoint_getter_transport_failure_is_typed_unobservable_evidence():
    def unavailable(_script: str, _timeout: float):
        raise RuntimeError("bridge read unavailable")

    result = PacketTracerEndpointAddressObserver(unavailable).observe(
        "MULTILAYER-PC-01",
        "FastEthernet0",
    )

    assert result.fresh_evidence is False
    assert result.device_found is False
    assert result.failure_reason == "RuntimeError: bridge read unavailable"
