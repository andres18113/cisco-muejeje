"""Router0 representative PC-to-PC forwarding is a distinct required result."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    project_cp_scale_canonical_stage,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    DeploymentBinding,
    DeploymentLinkBinding,
    DeploymentLinkEndpoint,
    DeploymentManifest,
    EnvironmentFingerprint,
)
from src.packet_tracer_mcp.domain.enterprise.models.forwarding import (
    ForwardingAddressObservation,
)
from src.packet_tracer_mcp.domain.models.typed_ping import TypedPingResult
from src.packet_tracer_mcp.infrastructure.execution.forwarding_probe import (
    ForwardingProbeExecutor,
)
from src.packet_tracer_mcp.infrastructure.observation.cp_scale_live import (
    PacketTracerCPScaleObservations,
    _observe_user_forwarding,
)
from src.packet_tracer_mcp.application.cp_scale_live.forwarding_stage import (
    CPScaleForwardingStage,
)
from src.packet_tracer_mcp.application.cp_scale_live.contracts import (
    CPScaleSiteForwardingObservation,
    CPScaleUserForwardingObservation,
)
from tests.poe_delivery_capabilities import (
    compose_delivery_qualified_cp_scale_canonical,
)


@pytest.fixture(scope="module")
def projection():
    composition = compose_delivery_qualified_cp_scale_canonical(
        packet_tracer_version="9.0.1.0858",
    )
    return project_cp_scale_canonical_stage(
        composition,
        CPScaleCanonicalStage.ROUTER0_BRANCH,
    )


def _manifest(projection) -> DeploymentManifest:
    selections = {
        item.source_endpoint.endpoint_device_id: item.source_endpoint
        for item in projection.branch_user_forwarding_checks
    }
    return DeploymentManifest(
        deployment_id="deployment/router0",
        physical_topology_hash=projection.topology.physical_identity_hash,
        backend="packet_tracer",
        backend_version="9.0.1.0858",
        environment_fingerprint=EnvironmentFingerprint(
            backend="packet_tracer",
            backend_version="9.0.1.0858",
            runtime_mode="live",
        ),
        semantic_hash="manifest-hash",
        bindings=[
            DeploymentBinding(
                semantic_device_id=item.endpoint_device_id,
                deployed_name=item.endpoint_device_name,
                model=item.endpoint_model,
                ports=[item.endpoint_interface],
            )
            for item in selections.values()
        ],
        link_bindings=[
            DeploymentLinkBinding(
                semantic_link_id=item.link_id,
                endpoint_a=DeploymentLinkEndpoint(
                    semantic_device_id=item.endpoint_device_id,
                    interface=item.endpoint_interface,
                ),
                endpoint_b=DeploymentLinkEndpoint(
                    semantic_device_id=item.peer_device_id,
                    interface=item.peer_interface,
                ),
                runtime_link_identifier=f"runtime/{item.link_id}",
                runtime_link_identity_observed=True,
            )
            for item in selections.values()
        ],
    )


def test_router0_user_checks_run_from_each_selected_pc_with_observed_bindings(
    projection,
):
    addresses = {
        "large-branch": "172.16.10.20",
        "multilayer-branch": "172.18.10.24",
    }

    class AddressReader:
        def observe(self, device_name: str, interface: str):
            selection = next(
                item.source_endpoint
                for item in projection.branch_user_forwarding_checks
                if item.source_endpoint.endpoint_device_name == device_name
            )
            return ForwardingAddressObservation(
                device_name,
                interface,
                True,
                True,
                True,
                addresses[selection.site_id],
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
                statistics="Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)",
                dispatched_destination=destination,
                observed_device_name=source,
                device_identity_provenance="confirmed_unique",
            )

    ping = Ping()
    observations = PacketTracerCPScaleObservations.__new__(
        PacketTracerCPScaleObservations,
    )
    observations.forwarding_probe = ForwardingProbeExecutor(
        AddressReader(),
        ping,
    )

    results = observations.user_forwarding(
        projection.branch_user_forwarding_checks,
        _manifest(projection),
    )

    assert len(results) == 2
    assert all(item.status is ActionExecutionStatus.VERIFIED for item in results)
    assert all(item.verified and item.attempts for item in results)
    assert ping.calls == [
        (
            "LARGE-BRANCH-CAMPUS-FLOOR-1-ZONE-A-PC-01",
            "172.18.10.24",
        ),
        (
            "MULTILAYER-BRANCH-MULTILAYER-CAMPUS-ACCESS-MLS3-PC-01",
            "172.16.10.20",
        ),
    ]
    assert results[0].source_binding.ipv4 == "172.16.10.20"
    assert results[0].destination_binding.ipv4 == "172.18.10.24"


def test_router_origin_check_uses_the_same_selected_dhcp_workload(projection):
    check = next(
        item
        for item in projection.branch_forwarding_checks
        if item.direction == "large-branch-to-multilayer-branch"
    )

    class AddressReader:
        def observe(self, device_name: str, interface: str):
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
    observations = PacketTracerCPScaleObservations.__new__(
        PacketTracerCPScaleObservations,
    )
    observations.ping = ping
    observations.forwarding_probe = ForwardingProbeExecutor(
        AddressReader(),
        ping,
    )

    result = observations.site_forwarding((check,), _manifest(projection))[0]

    assert result.verified
    assert result.destination_binding.ipv4 == "172.18.10.24"
    assert ping.calls == [("Router4", "172.18.10.24")]


def test_required_user_check_cannot_pass_when_the_adapter_returns_an_empty_list(
    projection,
):
    request = SimpleNamespace(
        projection=SimpleNamespace(
            stage=CPScaleCanonicalStage.ROUTER0_BRANCH,
            forwarding_checks={},
        ),
        deployment=SimpleNamespace(manifest=_manifest(projection)),
        site_forwarding_checks=(),
        user_forwarding_checks=projection.branch_user_forwarding_checks,
    )
    observations = SimpleNamespace(
        core_forwarding=lambda _checks: (),
        site_forwarding=lambda _checks, _manifest: (),
        user_forwarding=lambda _checks, _manifest: (),
    )

    result = CPScaleForwardingStage(observations).execute(request)

    assert result.verified is False
    assert result.user_verified is False
    assert result.user_first_failure == request.user_forwarding_checks[0].id


def test_selected_router_check_cannot_borrow_a_legacy_ping_without_its_binding(
    projection,
):
    check = projection.branch_forwarding_checks[0]
    reply = TypedPingResult(
        True,
        True,
        dispatched_destination="172.18.10.24",
        observed_device_name=check.source_device_name,
        device_identity_provenance="confirmed_unique",
    )
    request = SimpleNamespace(
        projection=SimpleNamespace(
            stage=CPScaleCanonicalStage.ROUTER0_BRANCH,
            forwarding_checks={},
        ),
        deployment=SimpleNamespace(manifest=_manifest(projection)),
        site_forwarding_checks=(check,),
        user_forwarding_checks=(),
    )
    observations = SimpleNamespace(
        core_forwarding=lambda _checks: (),
        site_forwarding=lambda _checks, _manifest: (
            CPScaleSiteForwardingObservation(check, (reply,), True),
        ),
    )

    result = CPScaleForwardingStage(observations).execute(request)

    assert result.verified is False
    assert result.first_failure == check.id


def test_incomplete_user_probe_object_cannot_borrow_verified_fields(projection):
    check = projection.branch_user_forwarding_checks[0]
    reply = TypedPingResult(
        True,
        True,
        dispatched_destination="172.18.10.24",
        observed_device_name=check.source_endpoint.endpoint_device_name,
        device_identity_provenance="confirmed_unique",
    )
    forged = CPScaleUserForwardingObservation(
        check=check,
        attempts=(reply,),
        status=ActionExecutionStatus.VERIFIED,
        verified=True,
        source_binding=SimpleNamespace(ipv4="172.16.10.20"),
        destination_binding=SimpleNamespace(ipv4="172.18.10.24"),
        probes=(object(),),
    )
    request = SimpleNamespace(
        projection=SimpleNamespace(
            stage=CPScaleCanonicalStage.ROUTER0_BRANCH,
            forwarding_checks={},
        ),
        deployment=SimpleNamespace(manifest=_manifest(projection)),
        site_forwarding_checks=(),
        user_forwarding_checks=(check,),
    )
    observations = SimpleNamespace(
        core_forwarding=lambda _checks: (),
        user_forwarding=lambda _checks, _manifest: (forged,),
    )

    result = CPScaleForwardingStage(observations).execute(request)

    assert result.verified is False
    assert result.user_first_failure == check.id


def test_real_plan_getters_bindings_and_typed_ping_assemble_into_cp_live_results(
    projection,
):
    large_name = "LARGE-BRANCH-CAMPUS-FLOOR-1-ZONE-A-PC-01"
    multilayer_name = (
        "MULTILAYER-BRANCH-MULTILAYER-CAMPUS-ACCESS-MLS3-PC-01"
    )
    addresses = {
        large_name: "172.16.10.20",
        multilayer_name: "172.18.10.24",
    }

    class Transport:
        current_source = ""
        current_destination = ""

        def send_and_wait(self, script: str, _timeout: float):
            if "getIpAddress" in script:
                name = next(item for item in addresses if json.dumps(item) in script)
                return json.dumps({
                    "found": True,
                    "port_found": True,
                    "interface": "FastEthernet0",
                    "address_channel": True,
                    "ipv4": addresses[name],
                    "netmask": "255.255.255.0",
                })
            if "enterCommand" in script:
                self.current_source = next(
                    item for item in addresses if json.dumps(item) in script
                )
                self.current_destination = next(
                    value
                    for value in addresses.values()
                    if f"ping {value}" in script
                )
                return json.dumps({"started": True, "blocked": "", "before": "C:\\>"})
            output = (
                "C:\\>ping "
                + self.current_destination
                + "\nPackets: Sent = 4, Received = 4, Lost = 0 (0% loss)\nC:\\>"
            )
            if "byObject" in script:
                return json.dumps({
                    "found": True,
                    "configuration_channel": True,
                    "output": output,
                    "owner_name": self.current_source,
                    "owner_evidence": "terminal_object_identity",
                    "owner_candidates": 1,
                    "device_count": 2,
                })
            return json.dumps({
                "found": True,
                "terminal_kind": "command_prompt",
                "output": output,
            })

    transport = Transport()
    observations = PacketTracerCPScaleObservations(
        transport,
        SimpleNamespace(observe_workspace=lambda: None),
    )

    results = observations.user_forwarding(
        projection.branch_user_forwarding_checks,
        _manifest(projection),
    )

    assert [item.status for item in results] == [
        ActionExecutionStatus.VERIFIED,
        ActionExecutionStatus.VERIFIED,
    ]
    assert [item.attempts[0].statistics for item in results] == [
        "Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)",
        "Packets: Sent = 4, Received = 4, Lost = 0 (0% loss)",
    ]
    assert [item.source_binding.ipv4 for item in results] == [
        "172.16.10.20",
        "172.18.10.24",
    ]
    assert [item.destination_binding.ipv4 for item in results] == [
        "172.18.10.24",
        "172.16.10.20",
    ]


def test_fresh_negative_pc_ping_uses_the_existing_window_and_stays_failed(
    projection,
):
    check = projection.branch_user_forwarding_checks[0]
    addresses = {
        check.source_endpoint.endpoint_device_name: "172.16.10.20",
        check.destination_endpoint.endpoint_device_name: "172.18.10.24",
    }

    class AddressReader:
        def observe(self, device_name: str, interface: str):
            return ForwardingAddressObservation(
                device_name,
                interface,
                True,
                True,
                True,
                addresses[device_name],
                "255.255.255.0",
                True,
            )

    class Ping:
        calls = 0

        def ping(self, source: str, destination: str):
            self.calls += 1
            return TypedPingResult(
                False,
                True,
                statistics="Packets: Sent = 4, Received = 0, Lost = 4 (100% loss)",
                dispatched_destination=destination,
                observed_device_name=source,
                device_identity_provenance="confirmed_unique",
            )

    ping = Ping()
    result = _observe_user_forwarding(
        ForwardingProbeExecutor(AddressReader(), ping),
        (check,),
        _manifest(projection),
        attempts=4,
        interval_seconds=0,
    )[0]

    assert result.status is ActionExecutionStatus.FAILED
    assert result.verified is False
    assert len(result.attempts) == 4
    assert ping.calls == 4
    assert all(item.reachable is False for item in result.attempts)


def test_unobservable_pc_ping_is_not_retried_as_a_reachability_failure(projection):
    check = projection.branch_user_forwarding_checks[0]
    addresses = {
        check.source_endpoint.endpoint_device_name: "172.16.10.20",
        check.destination_endpoint.endpoint_device_name: "172.18.10.24",
    }

    class AddressReader:
        def observe(self, device_name: str, interface: str):
            return ForwardingAddressObservation(
                device_name,
                interface,
                True,
                True,
                True,
                addresses[device_name],
                "255.255.255.0",
                True,
            )

    class Ping:
        calls = 0

        def ping(self, _source: str, _destination: str):
            self.calls += 1
            return TypedPingResult(
                False,
                False,
                failure_reason="no_fresh_ping_result",
            )

    ping = Ping()
    result = _observe_user_forwarding(
        ForwardingProbeExecutor(AddressReader(), ping),
        (check,),
        _manifest(projection),
        attempts=4,
        interval_seconds=0,
    )[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.verified is False
    assert len(result.attempts) == 1
    assert ping.calls == 1
