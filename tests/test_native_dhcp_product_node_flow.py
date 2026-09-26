"""Offline product A1-E6 flow over generated E5/E6 JavaScript and the Node engine."""

from __future__ import annotations

import json

import pytest
from native_dhcp_product_flow import run_native_product

from packet_tracer_mcp.adapters.cli.service_qualification import (
    _native_candidate_capabilities,
    _native_dhcp_http_intent,
    dhcp_product_contract,
    native_dhcp_http_product_contract,
)
from tests.service_qualification_engine import (
    FORWARDING_ROWS,
    NodeEngine,
    NodeEngineTransport,
    require_node,
)


@pytest.mark.parametrize(
    (
        "retry_on_enable",
        "pc2_late",
        "client_count",
        "duplicate_address",
        "skip_second",
        "getter_throw_second",
    ),
    [
        (False, False, 1, False, False, False),
        (True, False, 1, False, False, False),
        (True, True, 1, False, False, False),
        (True, False, 2, False, False, False),
        (True, False, 2, True, False, False),
        (True, False, 2, False, True, False),
        (True, False, 2, False, False, True),
    ],
)
def test_product_native_dhcp_state_gates_cold_http(
    tmp_path,
    retry_on_enable,
    pc2_late,
    client_count,
    duplicate_address,
    skip_second,
    getter_throw_second,
):
    """The product can request HTTP only after an attributable native lease."""
    require_node()
    intent = _native_dhcp_http_intent()
    if client_count == 2:
        payload = intent.model_dump(mode="json")
        services = payload["sites"][0]["services"]
        selected = [
            "endpoint/q3/default/user_pc/001",
            "endpoint/q3/default/user_pc/002",
        ]
        services[0]["client_device_ids"] = selected
        services[0]["dhcp_pool"]["max_users"] = 2
        services[1]["client_device_ids"] = selected
        intent = type(intent).model_validate(payload)
        contract = dhcp_product_contract(
            "9.0.1.0858",
            "node-product-two",
            2,
            intent_override=intent,
            capabilities_override=_native_candidate_capabilities("9.0.1.0858"),
            preserve_reference_topology=True,
        )
    else:
        contract = native_dhcp_http_product_contract("9.0.1.0858", "node-product")
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled",
        dhcp_native_max_behavior=(
            "resize_candidate" if client_count == 2 else "resize"
        ),
        dhcp_mode_acquires=True,
        dhcp_retry_on_server_enable=retry_on_enable,
        dhcp_client_address_override=("192.0.2.100" if duplicate_address else ""),
        dhcp_skip_client="Q3-DEFAULT-PC-02" if skip_second else "",
        dhcp_client_read_throw_device=(
            "Q3-DEFAULT-PC-02" if getter_throw_second else ""
        ),
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
        result = run_native_product(
            tmp_path,
            contract,
            intent,
            transport,
            capability_catalog=_native_candidate_capabilities,
            run_id=(
                f"native-node-{int(retry_on_enable)}-{int(pc2_late)}-"
                f"{client_count}-{int(duplicate_address)}-"
                f"{int(skip_second)}-{int(getter_throw_second)}"
            ),
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
        assert snapshot["dhcp_setter_calls"]["configurePcIpDhcp"] == client_count
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
        lease_ids = [
            item.id
            for item in contract.service_plan.verification_expectations
            if item.kind.value == "dhcp_lease"
        ]
        fetch_ids = [
            item.id
            for item in contract.service_plan.verification_expectations
            if item.kind.value == "http_fetch"
        ]
        assert len(lease_ids) == len(fetch_ids) == client_count
        ready = retry_on_enable and not pc2_late and not duplicate_address
        for index, identifier in enumerate(lease_ids):
            client_ready = ready and not (
                (skip_second or getter_throw_second) and index == 1
            )
            assert kinds[identifier].status.value == (
                "unknown"
                if getter_throw_second and index == 1
                else "verified"
                if client_ready
                else "failed"
            ), [(kinds[item].status.value, kinds[item].cause) for item in lease_ids]
        for index, identifier in enumerate(fetch_ids):
            client_ready = ready and not (
                (skip_second or getter_throw_second) and index == 1
            )
            assert kinds[identifier].status.value == (
                "verified" if client_ready else "dependency_blocked"
            )
        requests = [script for _kind, script in transport.calls if ".go(" in script]
        assert len(requests) == (
            client_count - int(skip_second or getter_throw_second) if ready else 0
        )
        if client_count == 2:
            scans = [
                script
                for _kind, script in transport.calls
                if "pool.getLeaseAt(j)" in script
            ]
            assert len(scans) == (1 if duplicate_address else 3 if skip_second else 2)
            if ready:
                addresses = {
                    kinds[identifier].observed["client_ipv4"]
                    for identifier in lease_ids
                }
                assert addresses == (
                    {"", "192.0.2.100"}
                    if skip_second or getter_throw_second
                    else {"192.0.2.100", "192.0.2.101"}
                )
                traces = [
                    kinds[identifier].observed["group_trace_json"]
                    for identifier in lease_ids
                ]
                assert sum(bool(value) for value in traces) == 1
        assert all("192.0.2.10" in script for script in requests)
        assert not any("ping " in script for _kind, script in transport.calls)
        assert snapshot["live_clients"] == 0
    finally:
        engine.close()
