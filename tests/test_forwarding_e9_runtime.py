"""E9 binds an opted-in DHCP workload before router-origin forwarding."""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureRipv2,
    ControlPlaneCapabilityDimension,
    ControlPlanePhase,
    ControlPlaneVerificationExpectation,
    ControlPlaneVerificationKind,
    RipNetwork,
)
from src.packet_tracer_mcp.domain.enterprise.models.forwarding import (
    ForwardingAddressMode,
    ForwardingAddressObservation,
    ForwardingEndpointSelection,
    ForwardingRuntimeEndpoint,
)
from src.packet_tracer_mcp.domain.models.typed_ping import TypedPingResult
from src.packet_tracer_mcp.infrastructure.execution.enterprise_control_plane_runtime import (
    PacketTracerEnterpriseControlPlaneRuntime,
)


def test_e9_observes_dhcp_binding_then_pings_it_without_plan_ip_literal():
    selection = ForwardingEndpointSelection(
        policy_id="cp-scale-wired-data-workload",
        policy_version="1",
        source_topology_id="topology/router0",
        source_topology_hash="physical-hash",
        source_configuration_id="configuration/router0",
        source_configuration_hash="configuration-hash",
        site_id="multilayer-branch",
        routing_device_id="router0",
        endpoint_device_id="endpoint/multilayer/pc/001",
        endpoint_device_name="MULTILAYER-PC-01",
        endpoint_model="PC-PT",
        endpoint_role="user_pc",
        link_id="link/multilayer/pc/001",
        endpoint_interface="FastEthernet0",
        peer_device_id="phone/multilayer/001",
        peer_interface="PC",
        segment_id="multilayer-data",
        address_mode=ForwardingAddressMode.DHCP,
        configuration_action_id="cfg/multilayer/pc/001",
        planned_ipv4=None,
        network="172.18.10.0",
        prefix_length=24,
        netmask="255.255.255.0",
    )
    target = ForwardingRuntimeEndpoint(
        selection=selection,
        runtime_device_name="MULTILAYER-PC-01",
        identity_method="semantic_binding",
        deployment_id="deployment/router0",
        deployment_manifest_hash="manifest-hash",
    )
    action = ConfigureRipv2(
        id="cp/rip/router4",
        phase=ControlPlanePhase.DYNAMIC_ROUTING,
        device_id="router4",
        device_name="Router4",
        model="2811",
        site_id="large-branch",
        required_capability=ControlPlaneCapabilityDimension.RIPV2_CONFIG,
        networks=[RipNetwork(network="172.16.0.0")],
    )
    expectation = ControlPlaneVerificationExpectation(
        id="cp/verify/large-to-multilayer",
        kind=ControlPlaneVerificationKind.END_TO_END_REACHABILITY,
        action_id=action.id,
        device_id=action.device_id,
        peer_device_id="router0",
        source_traffic_flow_id="flow/large-to-multilayer",
        forwarding_endpoint=selection,
        forwarding_runtime_endpoint=target,
        required_capability=ControlPlaneCapabilityDimension.ROUTING_BEHAVIOR,
        expected={"reachable": True, "protocol": "ripv2"},
    )
    reads: list[tuple[str, str]] = []

    class Addresses:
        def observe(self, device_name: str, interface: str):
            reads.append((device_name, interface))
            return ForwardingAddressObservation(
                device_name,
                interface,
                True,
                True,
                True,
                "172.18.10.24",
                "255.255.255.0",
                True,
            )

    class Ping:
        calls: list[tuple[str, str]] = []

        def ping(self, source: str, destination: str):
            self.calls.append((source, destination))
            return TypedPingResult(
                True,
                True,
                statistics="Success rate is 100 percent (5/5)",
                dispatched_destination=destination,
                observed_device_name=source,
                device_identity_provenance="confirmed_unique",
            )

    ping = Ping()
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [],
        lambda _script: True,
        lambda _script, _timeout: None,
        ping_executor=ping,
        endpoint_address_observer=Addresses(),
        reachability_convergence_attempts=1,
        reachability_convergence_interval_seconds=0,
    )
    runtime.apply_actions([action])

    result = runtime.verify([expectation])[0]

    assert "destination_ipv4" not in expectation.expected
    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fields["endpoint_binding"] is FieldVerificationStatus.VERIFIED
    assert ping.calls == [("Router4", "172.18.10.24")]
    assert reads == [
        ("MULTILAYER-PC-01", "FastEthernet0"),
        ("MULTILAYER-PC-01", "FastEthernet0"),
    ]
    assert result.convergence is not None
    assert result.convergence.details["resolved_binding"]["ipv4"] == "172.18.10.24"
