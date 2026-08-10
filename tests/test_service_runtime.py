"""Adapter E6 Packet Tracer: sólo APIs documentadas y verificaciones tipadas."""

from __future__ import annotations

import json

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.service_plan import (
    AddDnsRecord,
    EnableDnsService,
    EnableHttpService,
    ServiceEvidenceKind,
    ServicePhase,
    ServiceType,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
    SetHttpContent,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)


def _common(service_id="service/hq/dns", service_type=ServiceType.DNS):
    return dict(
        service_id=service_id,
        service_type=service_type,
        host_device_id="srv-1",
        host_device_name="__MCP_E6_SERVER",
        host_model="Server-PT",
        site_id="hq",
        required_capability=f"service_{service_type.value}_application",
    )


def test_dns_actions_use_documented_process_api_and_json_escaping():
    captured = []

    def send_and_wait(js, timeout):
        captured.append(js)
        return json.dumps({"results": [
            {"id": "enable", "applied": True},
            {"id": "record", "applied": True},
        ]})

    runtime = PacketTracerEnterpriseServiceRuntime(lambda: [], send_and_wait)
    actions = [
        EnableDnsService(
            id="enable", phase=ServicePhase.ENABLE, **_common(),
        ),
        AddDnsRecord(
            id="record", phase=ServicePhase.CONTENT,
            depends_on=["enable"], hostname="safe.example.local",
            address="198.18.160.10", **_common(),
        ),
    ]
    result = runtime.apply_actions(actions)

    assert all(item.applied for item in result)
    assert 'getProcess("DnsServer")' in captured[0]
    assert ".setEnable(true)" in captured[0]
    assert '.addARecordToNameServerDb("safe.example.local","198.18.160.10")' in captured[0]


def test_http_content_is_serialized_and_never_interpolated_as_javascript():
    captured = []
    marker = 'MCP_E6_HTTP_OK_"quoted"\\tail'

    def send_and_wait(js, timeout):
        captured.append(js)
        return json.dumps({"results": [{"id": "content", "applied": True}]})

    runtime = PacketTracerEnterpriseServiceRuntime(lambda: [], send_and_wait)
    action = SetHttpContent(
        id="content", phase=ServicePhase.CONTENT,
        content=marker, content_sha256="hash",
        **_common("service/hq/http", ServiceType.HTTP),
    )
    result = runtime.apply_actions([action])

    assert result[0].applied
    assert json.dumps(marker) in captured[0]
    assert '.setPageContents("index.html",' in captured[0]


def test_direct_dns_readback_requires_enabled_state_and_expected_record():
    responses = [json.dumps({
        "found": True, "enabled": True,
        "records": {"web.e6.example.local": "198.18.160.10"},
    })]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [], lambda js, timeout: responses.pop(0),
    )
    expectation = ServiceVerificationExpectation(
        id="verify", service_id="service/hq/dns", action_id="record",
        kind=ServiceVerificationKind.DIRECT_SERVICE_STATE,
        evidence_kind=ServiceEvidenceKind.DIRECT_STATE,
        host_device_id="srv-1", host_device_name="__MCP_E6_SERVER",
        expected={
            "enabled": True, "service_type": "dns",
            "records_json": '{"web.e6.example.local":"198.18.160.10"}',
        },
    )

    result = runtime.verify(expectation)

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fresh_evidence
    assert result.evidence_method == "structured_service_getters"


def test_dns_behavior_starts_typed_ping_and_reads_only_fresh_command_output():
    calls = []

    def send_and_wait(js, timeout):
        calls.append(js)
        if "enterCommand" in js:
            return json.dumps({"started": True, "before": "C:\\>"})
        return json.dumps({
            "found": True,
            "output": (
                "C:\\>ping web.e6.example.local\n"
                "Pinging 198.18.160.10 with 32 bytes of data:\n"
                "Packets: Sent = 4, Received = 4, Lost = 0"
            ),
        })

    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [], send_and_wait,
        dns_timeout_seconds=0.1, convergence_interval_seconds=0.0,
    )
    expectation = ServiceVerificationExpectation(
        id="verify-dns", service_id="service/hq/dns", action_id="record",
        kind=ServiceVerificationKind.DNS_RESOLUTION,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="srv-1", host_device_name="__MCP_E6_SERVER",
        client_device_id="pc-1", client_device_name="__MCP_E6_PC",
        expected={"hostname": "web.e6.example.local", "address": "198.18.160.10"},
    )

    result = runtime.verify(expectation)

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.evidence_method == "typed_pc_ping_hostname_fresh_output"
    assert any("getCommandPrompt" in item for item in calls)
    assert any(json.dumps("ping web.e6.example.local") in item for item in calls)


def test_dns_negative_control_requires_fresh_not_found_output():
    responses = [
        json.dumps({"started": True, "before": "C:\\>old\n"}),
        json.dumps({
            "found": True,
            "output": (
                "C:\\>old\n"
                "ping missing.example.local\n"
                "Ping request could not find host missing.example.local.\nC:\\>"
            ),
        }),
    ]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [], lambda js, timeout: responses.pop(0),
        dns_timeout_seconds=0.1, convergence_interval_seconds=0.0,
    )
    expectation = ServiceVerificationExpectation(
        id="verify-dns-negative", service_id="service/hq/dns", action_id="enable",
        kind=ServiceVerificationKind.DNS_NEGATIVE_CONTROL,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="srv-1", host_device_name="__MCP_E6_SERVER",
        client_device_id="pc-1", client_device_name="__MCP_E6_PC",
        expected={"hostname": "missing.example.local", "must_resolve": False},
    )

    result = runtime.verify(expectation)

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fresh_evidence
    assert result.evidence_method == "typed_pc_ping_hostname_negative_control"


def test_dns_behavior_rejects_a_fresh_but_wrong_address():
    responses = [
        json.dumps({"started": True, "before": "C:\\>"}),
        json.dumps({
            "found": True,
            "output": (
                "C:\\>ping web.e6.example.local\n"
                "Pinging 198.18.160.99 with 32 bytes of data:\n"
                "Packets: Sent = 4, Received = 4, Lost = 0"
            ),
        }),
    ]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [], lambda js, timeout: responses.pop(0),
        dns_timeout_seconds=0.0, convergence_interval_seconds=0.0,
    )
    expectation = ServiceVerificationExpectation(
        id="verify-dns-wrong", service_id="service/hq/dns", action_id="record",
        kind=ServiceVerificationKind.DNS_RESOLUTION,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="srv-1", host_device_name="__MCP_E6_SERVER",
        client_device_id="pc-1", client_device_name="__MCP_E6_PC",
        expected={"hostname": "web.e6.example.local", "address": "198.18.160.10"},
    )

    result = runtime.verify(expectation)

    assert result.status is ActionExecutionStatus.FAILED
    assert not result.fresh_evidence


def test_http_behavior_uses_a_fresh_background_client_and_releases_it():
    calls = []
    responses = [
        json.dumps({"started": True, "content_before": ""}),
        json.dumps({"found": True, "content": "MCP_E6_FRESH"}),
        json.dumps({"released": True}),
    ]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [], lambda js, timeout: calls.append(js) or responses.pop(0),
        http_timeout_seconds=0.1, convergence_interval_seconds=0.0,
    )
    expectation = ServiceVerificationExpectation(
        id="verify-http-background", service_id="service/hq/http", action_id="content",
        kind=ServiceVerificationKind.HTTP_FETCH,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="srv-1", host_device_name="__MCP_E6_SERVER",
        client_device_id="pc-1", client_device_name="__MCP_E6_PC",
        expected={"address": "198.18.160.10", "marker": "MCP_E6_FRESH"},
    )

    result = runtime.verify(expectation)

    assert result.status is ActionExecutionStatus.VERIFIED
    assert 'getProcess("HttpBackgroundClientManager")' in calls[0]
    assert "createClient()" in calls[0]
    assert "deleteClient" in calls[-1]


def test_http_behavior_rejects_stale_marker_and_accepts_fresh_fetch():
    marker = "MCP_E6_HTTP_OK_FRESH"
    responses = [
        json.dumps({"started": True, "content_before": ""}),
        json.dumps({"found": True, "content": marker}),
        json.dumps({"released": True}),
    ]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [], lambda js, timeout: responses.pop(0),
        http_timeout_seconds=0.1, convergence_interval_seconds=0.0,
    )
    expectation = ServiceVerificationExpectation(
        id="verify-http", service_id="service/hq/http", action_id="content",
        kind=ServiceVerificationKind.HTTP_FETCH,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="srv-1", host_device_name="__MCP_E6_SERVER",
        client_device_id="pc-1", client_device_name="__MCP_E6_PC",
        expected={"address": "198.18.160.10", "marker": marker},
    )

    result = runtime.verify(expectation)

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fresh_evidence
    assert result.evidence_method == "http_client_fresh_content"

    stale = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: (
            json.dumps({"released": True})
            if "deleteClient" in js
            else json.dumps({"started": True, "content_before": marker})
        ),
    ).verify(expectation)
    assert stale.status is ActionExecutionStatus.FAILED
    assert not stale.fresh_evidence


def test_http_behavior_rejects_fresh_content_without_expected_marker():
    responses = [
        json.dumps({"started": True, "content_before": ""}),
        json.dumps({"found": True, "content": "WRONG_PAGE"}),
        json.dumps({"released": True}),
    ]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [], lambda js, timeout: responses.pop(0),
        http_timeout_seconds=0.0, convergence_interval_seconds=0.0,
    )
    expectation = ServiceVerificationExpectation(
        id="verify-http-wrong", service_id="service/hq/http", action_id="content",
        kind=ServiceVerificationKind.HTTP_FETCH,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="srv-1", host_device_name="__MCP_E6_SERVER",
        client_device_id="pc-1", client_device_name="__MCP_E6_PC",
        expected={"address": "198.18.160.10", "marker": "MCP_E6_EXPECTED"},
    )

    result = runtime.verify(expectation)

    assert result.status is ActionExecutionStatus.FAILED
    assert not result.fresh_evidence


def test_ntp_and_tftp_behavior_remain_unobservable_without_client_evidence():
    runtime = PacketTracerEnterpriseServiceRuntime(lambda: [], lambda js, timeout: "{}")
    for kind in (ServiceVerificationKind.NTP_SYNC, ServiceVerificationKind.TFTP_RETRIEVE):
        result = runtime.verify(ServiceVerificationExpectation(
            id=f"verify-{kind.value}", service_id=f"service/{kind.value}", action_id="a",
            kind=kind, evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
            host_device_id="srv", host_device_name="server",
            client_device_id="pc", client_device_name="client",
        ))
        assert result.status is ActionExecutionStatus.UNOBSERVABLE
        assert not result.fresh_evidence


def test_https_behavior_uses_https_url_and_never_substitutes_http():
    calls = []
    responses = [
        json.dumps({"started": True, "content_before": ""}),
        json.dumps({"found": True, "content": "Packet Tracer secure page"}),
        json.dumps({"released": True}),
    ]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [], lambda js, timeout: calls.append(js) or responses.pop(0),
        http_timeout_seconds=0.1, convergence_interval_seconds=0.0,
    )
    expectation = ServiceVerificationExpectation(
        id="verify-https", service_id="service/hq/https", action_id="enable",
        kind=ServiceVerificationKind.HTTPS_FETCH,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="srv", host_device_name="server",
        client_device_id="pc", client_device_name="client",
        expected={"address": "198.18.160.10", "marker": "", "scheme": "https"},
    )

    result = runtime.verify(expectation)

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.evidence_method == "https_client_fresh_content"
    assert json.dumps("https://198.18.160.10/") in calls[0]
    assert "http://198.18.160.10/" not in calls[0]
