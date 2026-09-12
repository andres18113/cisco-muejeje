"""Focused policy/observation/execution contracts for forwarding workloads."""

from __future__ import annotations

import json
from dataclasses import replace

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.forwarding import (
    ForwardingAddressMode,
    ForwardingAddressObservation,
    ForwardingEndpointSelection,
    ForwardingKnownAddress,
    ForwardingRuntimeEndpoint,
)
from src.packet_tracer_mcp.domain.enterprise.services.forwarding_target import (
    bind_forwarding_address,
    forwarding_binding_stability,
)
from src.packet_tracer_mcp.domain.models.typed_ping import TypedPingResult


def _selection(
    site: str,
    address_mode: ForwardingAddressMode = ForwardingAddressMode.DHCP,
) -> ForwardingEndpointSelection:
    octet = "18" if site == "multilayer" else "16"
    return ForwardingEndpointSelection(
        policy_id="cp-scale-wired-data-workload",
        policy_version="1",
        source_topology_id="topology/router0",
        source_topology_hash="physical-hash",
        source_configuration_id="configuration/router0",
        source_configuration_hash="configuration-hash",
        site_id=site,
        routing_device_id=f"router/{site}",
        endpoint_device_id=f"endpoint/{site}/pc/001",
        endpoint_device_name=f"{site.upper()}-PC-01",
        endpoint_model="PC-PT",
        endpoint_role="user_pc",
        link_id=f"link/{site}/pc/001",
        endpoint_interface="FastEthernet0",
        peer_device_id=f"phone/{site}/001",
        peer_interface="PC",
        segment_id=f"{site}-data",
        address_mode=address_mode,
        configuration_action_id=f"cfg/{site}/pc/001",
        planned_ipv4=(f"172.{octet}.10.20" if address_mode is ForwardingAddressMode.STATIC else None),
        network=f"172.{octet}.10.0",
        prefix_length=24,
        netmask="255.255.255.0",
        known_plan_addresses=(ForwardingKnownAddress(
            ipv4=f"172.{octet}.10.1",
            action_id=f"cfg/{site}/gateway",
            device_id=f"router/{site}",
        ),),
    )


def _runtime(selection: ForwardingEndpointSelection) -> ForwardingRuntimeEndpoint:
    return ForwardingRuntimeEndpoint(
        selection=selection,
        runtime_device_name=selection.endpoint_device_name,
        identity_method="semantic_binding",
        deployment_id="deployment/router0",
        deployment_manifest_hash="manifest-hash",
        runtime_link_identifier="runtime-link-1",
        runtime_link_identity_observed=True,
    )


def _address(
    target: ForwardingRuntimeEndpoint,
    ipv4: str,
    *,
    fresh: bool = True,
    channel: bool = True,
) -> ForwardingAddressObservation:
    return ForwardingAddressObservation(
        runtime_device_name=target.runtime_device_name,
        interface=target.selection.endpoint_interface,
        device_found=True,
        port_found=True,
        address_channel=channel,
        ipv4=ipv4,
        netmask="255.255.255.0",
        fresh_evidence=fresh,
    )


def test_dhcp_binding_uses_observed_ip_without_putting_one_in_the_plan():
    target = _runtime(_selection("multilayer"))

    decision = bind_forwarding_address(target, _address(target, "172.18.10.24"))

    assert target.selection.planned_ipv4 is None
    assert decision.status is ActionExecutionStatus.VERIFIED
    assert decision.binding is not None
    assert decision.binding.ipv4 == "172.18.10.24"
    assert decision.binding.netmask == "255.255.255.0"
    assert "co-observed" in decision.binding.conflict_validation_scope


def test_static_binding_requires_the_fresh_planned_address():
    target = _runtime(_selection("large", ForwardingAddressMode.STATIC))

    decision = bind_forwarding_address(target, _address(target, "172.16.10.21"))

    assert decision.status is ActionExecutionStatus.FAILED
    assert decision.binding is None
    assert "contradicts" in decision.message


def test_binding_drift_fails_without_changing_the_selected_endpoint():
    target = _runtime(_selection("large"))
    initial = bind_forwarding_address(target, _address(target, "172.16.10.20"))
    assert initial.binding is not None

    changed = forwarding_binding_stability(
        initial.binding,
        _address(target, "172.16.10.21"),
    )

    assert changed.status is ActionExecutionStatus.FAILED
    assert changed.binding is None
    assert initial.binding.target.selection.endpoint_device_id == "endpoint/large/pc/001"


def test_pc_to_pc_probe_binds_both_endpoints_before_typed_ping_and_rechecks_them():
    from src.packet_tracer_mcp.infrastructure.execution.forwarding_probe import (
        ForwardingProbeExecutor,
        forwarding_probe_evidence,
    )

    source = _runtime(_selection("large"))
    destination = _runtime(_selection("multilayer"))
    events: list[tuple[str, str]] = []

    class Addresses:
        def observe(self, device_name: str, interface: str):
            events.append(("address", device_name))
            target = source if device_name == source.runtime_device_name else destination
            ipv4 = "172.16.10.20" if target is source else "172.18.10.24"
            return _address(target, ipv4)

    reply = TypedPingResult(
        True,
        True,
        statistics="Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)",
        dispatched_destination="172.18.10.24",
        observed_device_name=source.runtime_device_name,
        device_identity_provenance="confirmed_unique",
    )

    class Ping:
        def ping(self, source_name: str, destination_ipv4: str):
            events.append(("ping", f"{source_name}->{destination_ipv4}"))
            return reply

    result = ForwardingProbeExecutor(Addresses(), Ping()).probe_once(
        source_device_name=source.runtime_device_name,
        source_endpoint=source,
        destination_endpoint=destination,
    )

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.source_binding is not None
    assert result.destination_binding is not None
    assert result.ping is reply
    assert events == [
        ("address", source.runtime_device_name),
        ("address", destination.runtime_device_name),
        ("ping", f"{source.runtime_device_name}->172.18.10.24"),
        ("address", source.runtime_device_name),
        ("address", destination.runtime_device_name),
    ]
    serialized = json.loads(json.dumps(forwarding_probe_evidence(result)))
    assert serialized["source_binding"]["ipv4"] == "172.16.10.20"
    assert serialized["destination_binding"]["ipv4"] == "172.18.10.24"


def _probe_with_reply(
    reply: TypedPingResult,
    *,
    source_drift: bool = False,
    destination_drift: bool = False,
):
    from src.packet_tracer_mcp.infrastructure.execution.forwarding_probe import (
        ForwardingProbeExecutor,
    )

    source = _runtime(_selection("large"))
    destination = _runtime(_selection("multilayer"))
    reads = {source.runtime_device_name: 0, destination.runtime_device_name: 0}

    class Addresses:
        def observe(self, device_name: str, _interface: str):
            reads[device_name] += 1
            target = source if device_name == source.runtime_device_name else destination
            if target is source:
                ipv4 = (
                    "172.16.10.21"
                    if source_drift and reads[device_name] > 1
                    else "172.16.10.20"
                )
            else:
                ipv4 = (
                    "172.18.10.25"
                    if destination_drift and reads[device_name] > 1
                    else "172.18.10.24"
                )
            return _address(target, ipv4)

    class Ping:
        calls: list[tuple[str, str]] = []

        def ping(self, source_name: str, destination_ipv4: str):
            self.calls.append((source_name, destination_ipv4))
            return reply

    ping = Ping()
    result = ForwardingProbeExecutor(Addresses(), ping).probe_once(
        source_device_name=source.runtime_device_name,
        source_endpoint=source,
        destination_endpoint=destination,
    )
    return result, ping.calls


def test_fresh_attributed_ping_without_replies_remains_a_communication_failure():
    result, calls = _probe_with_reply(TypedPingResult(
        False,
        True,
        statistics="Packets: Sent = 4, Received = 0, Lost = 4 (100% loss)",
        dispatched_destination="172.18.10.24",
        observed_device_name="LARGE-PC-01",
        device_identity_provenance="confirmed_unique",
    ))

    assert result.status is ActionExecutionStatus.FAILED
    assert result.communication_observed is True
    assert result.retryable_reachability_mismatch is True
    assert calls == [("LARGE-PC-01", "172.18.10.24")]


def test_stale_or_unattributed_source_terminal_is_unobservable_not_a_pass():
    result, calls = _probe_with_reply(TypedPingResult(
        False,
        False,
        failure_reason="no_fresh_ping_result",
    ))

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.communication_observed is False
    assert result.bindings_stable is True
    assert result.source_binding is not None
    assert result.destination_binding is not None
    assert result.verified is False
    assert calls == [("LARGE-PC-01", "172.18.10.24")]


def test_source_address_change_during_ping_invalidates_the_attempt():
    result, _calls = _probe_with_reply(
        TypedPingResult(
            True,
            True,
            dispatched_destination="172.18.10.24",
            observed_device_name="LARGE-PC-01",
            device_identity_provenance="confirmed_unique",
        ),
        source_drift=True,
    )

    assert result.status is ActionExecutionStatus.FAILED
    assert result.communication_observed is False
    assert "changed during" in result.message


def test_destination_address_change_during_ping_invalidates_the_attempt():
    result, _calls = _probe_with_reply(
        TypedPingResult(
            True,
            True,
            dispatched_destination="172.18.10.24",
            observed_device_name="LARGE-PC-01",
            device_identity_provenance="confirmed_unique",
        ),
        destination_drift=True,
    )

    assert result.status is ActionExecutionStatus.FAILED
    assert result.communication_observed is False
    assert "changed during" in result.message


def test_fresh_ping_from_the_wrong_runtime_device_is_not_attributable():
    result, _calls = _probe_with_reply(TypedPingResult(
        True,
        True,
        dispatched_destination="172.18.10.24",
        observed_device_name="SOME-OTHER-PC",
        device_identity_provenance="mismatched",
    ))

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.communication_observed is False
    assert result.verified is False


def test_absent_address_getter_channel_is_unobservable_and_dispatches_no_ping():
    from src.packet_tracer_mcp.infrastructure.execution.forwarding_probe import (
        ForwardingProbeExecutor,
    )

    destination = _runtime(_selection("multilayer"))

    class Addresses:
        def observe(self, _device_name: str, _interface: str):
            return _address(
                destination,
                "",
                channel=False,
            )

    class Ping:
        calls = []

        def ping(self, source_name: str, destination_ipv4: str):
            self.calls.append((source_name, destination_ipv4))
            raise AssertionError("ping must not run without an address binding")

    ping = Ping()
    result = ForwardingProbeExecutor(Addresses(), ping).probe_once(
        source_device_name="Router4",
        destination_endpoint=destination,
    )

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.ping is None
    assert result.verified is False
    assert ping.calls == []


def test_observed_dhcp_address_conflicting_with_known_e5_identity_fails_closed():
    selection = replace(
        _selection("large"),
        known_plan_addresses=(ForwardingKnownAddress(
            ipv4="172.16.10.20",
            action_id="cfg/large/other-static",
            device_id="endpoint/large/other",
        ),),
    )
    target = _runtime(selection)

    decision = bind_forwarding_address(target, _address(target, "172.16.10.20"))

    assert decision.status is ActionExecutionStatus.FAILED
    assert "known E5 action" in decision.message
    assert "universal" in decision.message
