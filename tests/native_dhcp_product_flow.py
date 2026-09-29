"""Offline A1-E6 native DHCP product composition over the Node engine.

`run_native_product` wires the real endpoint E5 runtime, the real E6 service
runtime, the application use case and the durable record store to one
controlled channel. Everything past the channel is production code, so a test
controls only what Packet Tracer answers.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from service_entry_fixture import IsolationPreflight, RecordingConfigurationRuntime

from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    ServiceStageResult,
    ServiceStageRuntimes,
    TransportSelection,
    apply_enterprise_services,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    SetEndpointDhcp,
    SetEndpointStaticAddress,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    RuntimeActionMutation,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    SourceTreeIdentity,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    packet_tracer_service_capabilities,
)
from packet_tracer_mcp.infrastructure.execution.endpoint_address_observer import (
    PacketTracerEndpointAddressObserver,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)
from tests.service_qualification_engine import SIM_SHA, SIM_TREE, NodeEngineTransport


def run_native_product(
    tmp_path,
    contract,
    intent,
    transport: NodeEngineTransport,
    *,
    run_id: str,
    capability_catalog: Callable = packet_tracer_service_capabilities,
    state_samples: int = 3,
    device_capability_catalog=None,
    readiness=None,
    channel: str = "file",
) -> ServiceStageResult:
    """Run the product use case against a seeded engine behind `transport`.

    Endpoint E5 actions and readbacks run the real generated JavaScript; other
    E5 foundations are recorded as applied. E6 runs entirely for real, with
    `state_samples` native state samples and no sleeping between them.
    `readiness`, when given, answers routed forwarding and trunk continuity.
    """
    inventory = [item.model_dump(mode="json") for item in contract.inventory]
    real_e5 = PacketTracerEnterpriseConfigurationRuntime(
        lambda: inventory,
        transport.send,
        transport.send_and_wait,
        convergence_interval_seconds=0.0,
    )
    synthetic = RecordingConfigurationRuntime(targets=list(contract.inventory))

    class HybridE5:
        def inventory(self):
            return list(contract.inventory)

        def apply_actions(self, actions):
            endpoint = [
                item
                for item in actions
                if isinstance(item, SetEndpointStaticAddress | SetEndpointDhcp)
            ]
            actual = {item.action_id: item for item in real_e5.apply_actions(endpoint)}
            return [
                actual.get(item.id)
                or RuntimeActionMutation(action_id=item.id, applied=True)
                for item in actions
            ]

        def verify(self, expectations):
            endpoint = [
                item
                for item in expectations
                if item.kind
                in {
                    VerificationKind.ENDPOINT_ADDRESSING,
                    VerificationKind.ENDPOINT_DHCP_MODE,
                }
            ]
            actual = {item.expectation_id: item for item in real_e5.verify(endpoint)}
            other = [item for item in expectations if item.id not in actual]
            synthetic_rows = {
                item.expectation_id: item for item in synthetic.verify(other)
            }
            return [
                actual.get(item.id) or synthetic_rows[item.id] for item in expectations
            ]

        def observe_access_forwarding(self, *args, **kwargs):
            return synthetic.observe_access_forwarding(*args, **kwargs)

        def wait_for_voice_access_forwarding(self, expectations):
            return synthetic.wait_for_voice_access_forwarding(expectations)

        def observe_routed_forwarding(self, devices, **bounds):
            if readiness is None:
                raise NotImplementedError("no routed observer in this flow")
            return readiness.observe_routed_forwarding(devices, **bounds)

        def observe_trunk_continuity(self, switches, vlan_id, **bounds):
            if readiness is None:
                raise NotImplementedError("no trunk observer in this flow")
            return readiness.observe_trunk_continuity(switches, vlan_id, **bounds)

    real_e6 = PacketTracerEnterpriseServiceRuntime(
        lambda: inventory,
        transport.send_and_wait,
        dispatch_and_wait=transport.dispatch_and_wait,
        convergence_interval_seconds=0.0,
        sleeper=lambda _seconds: None,
        http_timeout_seconds=1.0,
    )
    real_e6._dhcp_state_interval = 0.0
    real_e6._dhcp_state_max_samples = state_samples

    class Manifest:
        def latest_by_deployment_id(self, identifier):
            return (
                contract.manifest
                if identifier == contract.manifest.deployment_id
                else None
            )

    return apply_enterprise_services(
        intent.model_dump_json(),
        deployment_id=contract.manifest.deployment_id,
        packet_tracer_version="9.0.1.0858",
        import_preflight=IsolationPreflight(),
        manifest_store=Manifest(),
        runtimes=ServiceStageRuntimes(configuration=HybridE5(), services=real_e6),
        record_store=ServiceRunRecordStore(tmp_path),
        environment_fingerprint=contract.manifest.environment_fingerprint,
        transport_selection=TransportSelection(
            channel=channel, fixed_at=datetime.now(UTC)
        ),
        endpoint_observer=PacketTracerEndpointAddressObserver(transport.send_and_wait),
        capability_catalog=capability_catalog,
        device_capability_catalog=device_capability_catalog,
        source_tree=SourceTreeIdentity(sha=SIM_SHA, tree=SIM_TREE, dirty=False),
        run_id=run_id,
    )
