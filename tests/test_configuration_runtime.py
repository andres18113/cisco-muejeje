"""Adapter Packet Tracer E5: batching seguro y read-back operacional fresco."""

from __future__ import annotations

import json

from src.packet_tracer_mcp.application.use_cases.compile_configuration import (
    compile_enterprise_configuration,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
    VerificationExpectation,
    VerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosCommandResult,
    OperationalQueryId,
)

from test_enterprise_configuration import _fixture


def _plan():
    enterprise, topology, policy = _fixture()
    return topology, compile_enterprise_configuration(enterprise, topology, policy).plan


def _inventory(topology):
    return [
        {
            "name": device.name,
            "model": device.model,
            "ports": [
                {"name": port}
                for link in topology.links
                for endpoint_id, port in (
                    (link.device_a_id, link.port_a), (link.device_b_id, link.port_b),
                )
                if endpoint_id == device.id
            ],
        }
        for device in topology.devices
    ]


def test_runtime_batches_ios_per_device_phase_and_endpoints_in_one_safe_call():
    topology, plan = _plan()
    sent: list[str] = []
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: _inventory(topology),
        send=lambda payload: sent.append(payload) or True,
        send_and_wait=lambda _payload, _timeout: None,
        ios_readiness=lambda _device: True,
    )

    results = runtime.apply_actions(plan.actions)

    assert all(result.applied for result in results)
    assert len(sent) < len(plan.actions)
    assert sum("configurePcIp" in payload for payload in sent) == 1
    endpoint_payload = next(payload for payload in sent if "configurePcIp" in payload)
    assert "__MCP_E5_PC" in endpoint_payload
    assert "__MCP_E5_PHONE" in endpoint_payload
    assert "198.18.151.2" in endpoint_payload
    assert "255.255.255.0" in endpoint_payload
    assert "198.18.151.1" in endpoint_payload
    assert '"Vlan1"' in endpoint_payload


def test_runtime_inventory_normalizes_port_objects_and_strings():
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [{
            "name": "SW1", "model": "2960-24TT",
            "ports": [{"name": "FastEthernet0/1"}, "GigabitEthernet0/1"],
        }],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: None,
    )

    targets = runtime.inventory()

    assert len(targets) == 1
    assert targets[0].interfaces == ["FastEthernet0/1", "GigabitEthernet0/1"]


def test_vlan_verifier_uses_existing_vlan_manager_and_bounded_convergence():
    _, plan = _plan()
    expectation = next(
        item for item in plan.verification_expectations
        if item.kind.value == "vlan"
    )
    responses = iter((
        '{"found":true,"configuration_channel":false,"present":false}',
        '{"found":true,"configuration_channel":true,"present":true}',
    ))
    payloads: list[str] = []
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda payload, _timeout: payloads.append(payload) or next(responses),
        convergence_interval_seconds=0,
    )

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.convergence is not None
    assert result.convergence.attempts == 2
    assert result.fields["vlan_id"] is FieldVerificationStatus.VERIFIED
    assert all("VlanManager" in payload for payload in payloads)


def test_l3_verifier_uses_controlled_fresh_show_window():
    _, plan = _plan()
    expectation = next(
        item for item in plan.verification_expectations
        if item.required_query == "show_ip_interface_brief"
    )
    responses = iter((
        '{"found":true,"booting":false,"terminal":true,"prompt":"R1#","output":"R1#"}',
        '{"ok":true,"before":"R1#"}',
        '{"found":true,"configuration_channel":true,"output":"R1#show ip interface brief\\nInterface IP-Address OK? Method Status Protocol\\nGig0/0.10 198.18.150.1 YES manual up up\\nR1#"}',
        '{"found":true,"configuration_channel":true,"output":"R1#show ip interface brief\\nInterface IP-Address OK? Method Status Protocol\\nGig0/0.10 198.18.150.1 YES manual up up\\nR1#"}',
    ))
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: next(responses),
    )

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fresh_evidence
    assert result.fields["ipv4"] is FieldVerificationStatus.VERIFIED
    assert result.fields["interface"] is FieldVerificationStatus.VERIFIED
    assert result.fields["status"] is FieldVerificationStatus.VERIFIED
    assert result.fields["protocol"] is FieldVerificationStatus.VERIFIED


def test_l3_verifier_separates_configured_admin_state_from_down_link_state():
    _, plan = _plan()
    expectation = next(
        item for item in plan.verification_expectations
        if item.required_query == "show_ip_interface_brief"
    )
    current = (
        '{"found":true,"configuration_channel":true,'
        '"output":"R1#show ip interface brief\\nInterface IP-Address OK? Method Status Protocol\\n'
        'Gig0/0.10 198.18.150.1 YES manual down down\\nR1#"}'
    )
    responses = iter((
        '{"found":true,"booting":false,"terminal":true,"prompt":"R1#","output":"R1#"}',
        '{"ok":true,"before":"R1#"}',
        current,
        current,
    ))
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: next(responses),
        l3_timeout_seconds=0,
        convergence_interval_seconds=0,
    )

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fields["ipv4"] is FieldVerificationStatus.VERIFIED
    assert result.fields["administrative_state"] is FieldVerificationStatus.VERIFIED
    assert result.fields["status"] is FieldVerificationStatus.UNKNOWN
    assert result.fields["protocol"] is FieldVerificationStatus.UNKNOWN
    assert "operational link is not up/up" in result.message


def test_l3_verifier_requires_administratively_down_state_when_requested():
    _, plan = _plan()
    expectation = next(
        item for item in plan.verification_expectations
        if item.required_query == "show_ip_interface_brief"
    )
    expectation.expected["administrative_up"] = False
    current = (
        '{"found":true,"configuration_channel":true,'
        '"output":"R1#show ip interface brief\\nInterface IP-Address OK? Method Status Protocol\\n'
        'Gig0/0.10 198.18.150.1 YES manual up up\\nR1#"}'
    )
    responses = iter((
        '{"found":true,"booting":false,"terminal":true,"prompt":"R1#","output":"R1#"}',
        '{"ok":true,"before":"R1#"}',
        current,
        current,
    ))
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: next(responses),
        l3_timeout_seconds=0,
        convergence_interval_seconds=0,
    )

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.FAILED
    assert result.fields["status"] is FieldVerificationStatus.FAILED
    assert result.fields["protocol"] is FieldVerificationStatus.FAILED


def test_l3_verifier_accepts_fresh_administratively_down_state_when_requested():
    _, plan = _plan()
    expectation = next(
        item for item in plan.verification_expectations
        if item.required_query == "show_ip_interface_brief"
    )
    expectation.expected["administrative_up"] = False
    current = (
        '{"found":true,"configuration_channel":true,'
        '"output":"R1#show ip interface brief\\nInterface IP-Address OK? Method Status Protocol\\n'
        'Gig0/0.10 198.18.150.1 YES manual administratively down down\\nR1#"}'
    )
    responses = iter((
        '{"found":true,"booting":false,"terminal":true,"prompt":"R1#","output":"R1#"}',
        '{"ok":true,"before":"R1#"}',
        current,
        current,
    ))
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: next(responses),
        convergence_interval_seconds=0,
    )

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fields["status"] is FieldVerificationStatus.VERIFIED
    assert result.fields["protocol"] is FieldVerificationStatus.VERIFIED


def test_trunk_verifier_uses_existing_typed_parser_and_current_query_only():
    _, plan = _plan()
    expectation = next(
        item for item in plan.verification_expectations
        if item.required_query == "show_interfaces_trunk"
    )
    interface = expectation.expected["interface"]
    output = "SW#show interfaces trunk\nGig0/1 on 802.1q trunking 1\nSW#"
    current = json.dumps({
        "found": True,
        "configuration_channel": True,
        "output": output,
    })
    responses = iter((
        '{"found":true,"booting":false,"terminal":true,"prompt":"SW#","output":"SW#"}',
        '{"ok":true,"before":"SW#"}',
        current,
        current,
    ))
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: next(responses),
    )

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fresh_evidence
    assert result.fields["interface"] is FieldVerificationStatus.VERIFIED
    assert result.fields["status"] is FieldVerificationStatus.VERIFIED
    assert result.fields["allowed_vlans"] is FieldVerificationStatus.UNOBSERVABLE


def test_trunk_verifier_polls_until_operational_state_converges():
    _, plan = _plan()
    expectation = next(
        item for item in plan.verification_expectations
        if item.required_query == "show_interfaces_trunk"
    )
    interface = expectation.expected["interface"]

    def query_responses(output: str):
        current = json.dumps({
            "found": True,
            "configuration_channel": True,
            "output": output,
        })
        return (
            '{"found":true,"booting":false,"terminal":true,"prompt":"SW#","output":"SW#"}',
            '{"ok":true,"before":"SW#"}',
            current,
            current,
        )

    empty = "SW#show interfaces trunk\nPort Mode Encapsulation Status Native vlan\nSW#"
    ready = "SW#show interfaces trunk\nGig0/1 on 802.1q trunking 1\nSW#"
    responses = iter((*query_responses(empty), *query_responses(ready)))
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: next(responses),
        convergence_interval_seconds=0,
    )

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.convergence is not None
    assert result.convergence.attempts == 2
    assert result.fresh_evidence


def test_endpoint_dhcp_verification_keeps_gateway_and_dns_unobservable():
    _, plan = _plan()
    expectation = next(
        item for item in plan.verification_expectations
        if item.expected.get("mode") == "dhcp"
    )
    observed = (
        '{"found":true,"configuration_channel":true,'
        '"ipv4":"198.18.150.54","netmask":"255.255.255.0",'
        '"gateway":null,"dns":null}'
    )
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: observed,
    )

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.PARTIAL
    assert result.fields["ipv4"] is FieldVerificationStatus.VERIFIED
    assert result.fields["netmask"] is FieldVerificationStatus.VERIFIED
    assert result.fields["gateway"] is FieldVerificationStatus.UNOBSERVABLE
    assert result.fields["dns"] is FieldVerificationStatus.UNOBSERVABLE


def test_access_port_and_dhcp_pool_without_getters_are_unobservable_not_partial():
    _, plan = _plan()
    expectations = [
        item for item in plan.verification_expectations
        if item.kind.value in {"access_port", "dhcp_pool"}
    ]
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: None,
    )

    results = runtime.verify(expectations)

    assert results
    assert all(item.status is ActionExecutionStatus.UNOBSERVABLE for item in results)
    assert all(not item.fresh_evidence for item in results)
    assert all(
        set(item.fields.values()) == {FieldVerificationStatus.UNOBSERVABLE}
        for item in results
    )


def test_endpoint_timeout_cannot_be_promoted_by_a_late_matching_read():
    _, plan = _plan()
    expectation = next(
        item for item in plan.verification_expectations
        if item.expected.get("mode") == "dhcp"
    )
    calls = 0

    def observe(_payload, _timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            return (
                '{"found":true,"configuration_channel":false,'
                '"ipv4":"","netmask":"","gateway":null,"dns":null}'
            )
        return (
            '{"found":true,"configuration_channel":true,'
            '"ipv4":"198.18.150.54","netmask":"255.255.255.0",'
            '"gateway":null,"dns":null}'
        )

    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=observe,
        endpoint_timeout_seconds=0,
        convergence_interval_seconds=0,
    )

    result = runtime.verify([expectation])[0]

    assert calls == 2
    assert result.status is ActionExecutionStatus.FAILED
    assert result.convergence is not None
    assert result.convergence.last_observable_state == "convergence_timeout"


def test_runtime_never_accepts_or_emits_a_raw_ios_action_type():
    _, plan = _plan()

    assert "raw_cli" not in {item.value for item in ConfigurationActionType}
    assert all(action.action_type.value != "raw_cli" for action in plan.actions)


def test_ios_boot_failure_stops_device_batch_before_configuration_mutation():
    topology, plan = _plan()
    sent: list[str] = []
    vlan = next(
        action for action in plan.actions
        if action.action_type is ConfigurationActionType.CREATE_VLAN
    )
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: _inventory(topology),
        send=lambda payload: sent.append(payload) or True,
        send_and_wait=lambda _payload, _timeout: None,
        ios_readiness=lambda _device: False,
    )

    result = runtime.apply_actions([vlan])[0]

    assert not result.applied
    assert result.failure_code.value == "session_failed"
    assert not sent


class _StaticIos:
    def __init__(self, result: IosCommandResult) -> None:
        self.result = result
        self.calls: list[tuple[str, OperationalQueryId, str]] = []

    def execute(self, device_name, query_id, *, interface=""):
        self.calls.append((device_name, query_id, interface))
        return self.result


def _serial_expectation() -> VerificationExpectation:
    return VerificationExpectation(
        id="verify/clock",
        action_id="clock",
        kind=VerificationKind.SERIAL_CONTROLLER,
        device_id="r-a",
        device_name="R-A",
        required_query="show_controllers_serial",
        expected={
            "interface": "Serial0/0/0",
            "serial_endpoint_role": "dce",
            "clock_rate_bps": 128_000,
        },
    )


def _configuration_runtime_with_ios(result: IosCommandResult):
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: None,
    )
    ios = _StaticIos(result)
    runtime._ios = ios
    return runtime, ios


def test_serial_clock_verifier_requires_fresh_exact_controller_state():
    output = (
        "R-A#show controllers Serial0/0/0\n"
        "Interface Serial0/0/0\n"
        "DCE V.35, clock rate 128000\n"
        "R-A#"
    )
    runtime, ios = _configuration_runtime_with_ios(IosCommandResult(
        "R-A",
        OperationalQueryId.SHOW_CONTROLLERS_SERIAL,
        True,
        output=output,
        fresh_output_observed=True,
        output_complete=True,
    ))

    result = runtime.verify([_serial_expectation()])[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fresh_evidence
    assert set(result.fields.values()) == {FieldVerificationStatus.VERIFIED}
    assert ios.calls == [(
        "R-A", OperationalQueryId.SHOW_CONTROLLERS_SERIAL, "Serial0/0/0",
    )]


def test_serial_clock_verifier_never_promotes_incomplete_or_contradictory_state():
    cases = (
        IosCommandResult(
            "R-A", OperationalQueryId.SHOW_CONTROLLERS_SERIAL, True,
            output=(
                "Interface Serial0/0/0\nDCE V.35, clock rate 128000\n--More--"
            ),
            fresh_output_observed=True,
            truncated_by_pager=True,
        ),
        IosCommandResult(
            "R-A", OperationalQueryId.SHOW_CONTROLLERS_SERIAL, True,
            output="Interface Serial0/0/0\nDTE V.35 TX and RX clocks detected\n",
            fresh_output_observed=True,
            output_complete=True,
        ),
        IosCommandResult(
            "R-A", OperationalQueryId.SHOW_CONTROLLERS_SERIAL, True,
            output="Interface Serial0/0/0\nDCE V.35, clock rate 64000\n",
            fresh_output_observed=True,
            output_complete=True,
        ),
        IosCommandResult(
            "R-A", OperationalQueryId.SHOW_CONTROLLERS_SERIAL, True,
            output="Interface Serial0/0/0\nDCE V.35, clock rate 128000\n",
            fresh_output_observed=False,
            output_complete=True,
        ),
        IosCommandResult(
            "R-A", OperationalQueryId.SHOW_CONTROLLERS_SERIAL, True,
            output="% Invalid input detected",
            fresh_output_observed=True,
            output_complete=True,
        ),
    )

    statuses = []
    for show in cases:
        runtime, _ = _configuration_runtime_with_ios(show)
        statuses.append(runtime.verify([_serial_expectation()])[0].status)

    assert ActionExecutionStatus.VERIFIED not in statuses
    assert statuses == [
        ActionExecutionStatus.UNOBSERVABLE,
        ActionExecutionStatus.FAILED,
        ActionExecutionStatus.FAILED,
        ActionExecutionStatus.UNOBSERVABLE,
        ActionExecutionStatus.UNOBSERVABLE,
    ]
