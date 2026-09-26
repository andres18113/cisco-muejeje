"""Offline product A1-E6 flow over generated E5/E6 JavaScript and the Node engine."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from service_entry_fixture import IsolationPreflight, RecordingConfigurationRuntime

from packet_tracer_mcp.adapters.cli.service_qualification import (
    _native_candidate_capabilities,
    _native_dhcp_http_intent,
    native_dhcp_http_product_contract,
)
from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
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
from tests.service_qualification_engine import (
    FORWARDING_ROWS,
    SIM_SHA,
    SIM_TREE,
    NodeEngine,
    NodeEngineTransport,
    require_node,
)


@pytest.mark.parametrize(
    ("retry_on_enable", "pc2_late"),
    [(False, False), (True, False), (True, True)],
)
def test_product_native_dhcp_state_gates_cold_http(tmp_path, retry_on_enable, pc2_late):
    """The product can request HTTP only after an attributable native lease."""
    require_node()
    contract = native_dhcp_http_product_contract("9.0.1.0858", "node-product")
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior="resize",
        dhcp_mode_acquires=True,
        dhcp_retry_on_server_enable=retry_on_enable,
        pc2_mode_on_server_enable=pc2_late,
        stp_rows=FORWARDING_ROWS,
        terminals=True,
    )
    try:
        for device in contract.topology.devices:
            engine.seed_device(device.name, device.model)

        class CapturingTransport(NodeEngineTransport):
            native_body = None

            def dispatch_and_wait(self, js_code, timeout):
                outcome = super().dispatch_and_wait(js_code, timeout)
                if "native_start_drift" in js_code:
                    self.native_body = outcome.body
                return outcome

        transport = CapturingTransport(engine)
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
                actual = {
                    item.action_id: item for item in real_e5.apply_actions(endpoint)
                }
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
                actual = {
                    item.expectation_id: item for item in real_e5.verify(endpoint)
                }
                other = [item for item in expectations if item.id not in actual]
                synthetic_rows = {
                    item.expectation_id: item for item in synthetic.verify(other)
                }
                return [
                    actual.get(item.id) or synthetic_rows[item.id]
                    for item in expectations
                ]

            def observe_access_forwarding(self, *args, **kwargs):
                return synthetic.observe_access_forwarding(*args, **kwargs)

            def wait_for_voice_access_forwarding(self, expectations):
                return synthetic.wait_for_voice_access_forwarding(expectations)

        real_e6 = PacketTracerEnterpriseServiceRuntime(
            lambda: inventory,
            transport.send_and_wait,
            dispatch_and_wait=transport.dispatch_and_wait,
            convergence_interval_seconds=0.0,
            sleeper=lambda _seconds: None,
            http_timeout_seconds=1.0,
        )
        real_e6._dhcp_state_interval = 0.0
        real_e6._dhcp_state_max_samples = 3

        class Manifest:
            def latest_by_deployment_id(self, identifier):
                return (
                    contract.manifest
                    if identifier == contract.manifest.deployment_id
                    else None
                )

        result = apply_enterprise_services(
            json.dumps(_native_dhcp_http_intent().model_dump(mode="json")),
            deployment_id=contract.manifest.deployment_id,
            packet_tracer_version="9.0.1.0858",
            import_preflight=IsolationPreflight(),
            manifest_store=Manifest(),
            runtimes=ServiceStageRuntimes(configuration=HybridE5(), services=real_e6),
            record_store=ServiceRunRecordStore(tmp_path),
            environment_fingerprint=contract.manifest.environment_fingerprint,
            transport_selection=TransportSelection(
                channel="file", fixed_at=datetime.now(UTC)
            ),
            endpoint_observer=PacketTracerEndpointAddressObserver(
                transport.send_and_wait
            ),
            capability_catalog=_native_candidate_capabilities,
            source_tree=SourceTreeIdentity(sha=SIM_SHA, tree=SIM_TREE, dirty=False),
            run_id=f"native-node-{int(retry_on_enable)}-{int(pc2_late)}",
        )
        assert result.service_result is not None, (
            result.refusal_code,
            result.blocked_reason,
            result.stage,
        )
        snapshot = engine.snapshot()
        assert set(snapshot["dhcp_servers"]["Q3-DEFAULT-SERVER-01"]["pools"]) == {
            "serverPool"
        }
        assert snapshot["dhcp_runs"] == []
        assert snapshot["dhcp_setter_calls"]["configurePcIpDhcp"] == 1
        assert snapshot["dhcp_setter_calls"]["setEnable"] == 1, (
            [
                (
                    item.action_id,
                    item.status.value,
                    item.failure_code.value,
                    item.cause,
                    item.message[:100],
                )
                for item in result.service_result.action_results
                if "dhcp" in item.action_id
            ],
            json.loads(transport.native_body)["results"][0]
            if transport.native_body and transport.native_body.startswith("{")
            else transport.native_body,
            [
                ("native_start_drift" in script, "family_not_implemented" in script)
                for _kind, script in transport.calls
                if "server-dhcp-pool" in script
            ],
        )
        assert result.service_result is not None
        kinds = {
            item.expectation_id: item
            for item in result.service_result.verification_results
        }
        lease_id = next(
            item.id
            for item in contract.service_plan.verification_expectations
            if item.kind.value == "dhcp_lease"
        )
        fetch_id = next(
            item.id
            for item in contract.service_plan.verification_expectations
            if item.kind.value == "http_fetch"
        )
        ready = retry_on_enable and not pc2_late
        assert kinds[lease_id].status.value == ("verified" if ready else "failed")
        assert kinds[fetch_id].status.value == (
            "verified" if ready else "dependency_blocked"
        )
        requests = [script for _kind, script in transport.calls if ".go(" in script]
        assert len(requests) == (1 if ready else 0)
        assert all("192.0.2.10" in script for script in requests)
        assert not any("ping " in script for _kind, script in transport.calls)
        assert snapshot["live_clients"] == 0
    finally:
        engine.close()
