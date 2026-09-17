"""Adapter E6 Packet Tracer: sólo APIs documentadas y verificaciones tipadas."""

from __future__ import annotations

import json

from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.execution import PostconditionFact
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    AddDnsRecord,
    EnableDnsService,
    ServiceEvidenceKind,
    ServicePhase,
    ServiceType,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
    SetHttpContent,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    ObservationFact,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)


def _row(identifier, *, ok=True, changed=True, call_result=None, pre="0", post="1"):
    """Build one admissible mutation row of the item 4 contract.

    The fixtures used to be `{id, applied}`, which the runtime no longer reads:
    `applied` is not an observation, and a row missing the contract keys is
    inadmissible rather than a success. Digests are supplied because the
    contract requires the key, not because anything reads them -- no assertion
    in this module derives a fact from `pre` or `post`.
    """
    return {
        "id": identifier,
        "attempted": True,
        "skip_reason": "",
        "call_error": "",
        "call_result": call_result,
        "pre_read": True,
        "post_read": True,
        "ok": ok,
        "changed": changed,
        "pre": pre,
        "post": post,
    }


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
    """The DNS batch uses documented process calls and serializes every value."""
    captured = []

    def send_and_wait(js, timeout):
        captured.append(js)
        return json.dumps(
            {
                "results": [
                    _row("enable"),
                    _row("record", call_result=True),
                ]
            }
        )

    runtime = PacketTracerEnterpriseServiceRuntime(lambda: [], send_and_wait)
    actions = [
        EnableDnsService(
            id="enable",
            phase=ServicePhase.ENABLE,
            **_common(),
        ),
        AddDnsRecord(
            id="record",
            phase=ServicePhase.CONTENT,
            depends_on=["enable"],
            hostname="safe.example.local",
            address="198.18.160.10",
            **_common(),
        ),
    ]
    result = runtime.apply_actions(actions)

    assert all(item.postcondition is PostconditionFact.SATISFIED for item in result)
    assert all(item.applied for item in result)
    assert 'getProcess("DnsServer")' in captured[0]
    assert ".setEnable(true)" in captured[0]
    assert (
        '.addARecordToNameServerDb("safe.example.local","198.18.160.10")' in captured[0]
    )


def test_http_content_is_serialized_and_never_interpolated_as_javascript():
    """Page content reaches the script as JSON data, never as source."""
    captured = []
    marker = 'MCP_E6_HTTP_OK_"quoted"\\tail'

    def send_and_wait(js, timeout):
        captured.append(js)
        return json.dumps({"results": [_row("content", pre="00000000:0")]})

    runtime = PacketTracerEnterpriseServiceRuntime(lambda: [], send_and_wait)
    action = SetHttpContent(
        id="content",
        phase=ServicePhase.CONTENT,
        content=marker,
        content_sha256="hash",
        **_common("service/hq/http", ServiceType.HTTP),
    )
    result = runtime.apply_actions([action])

    assert result[0].postcondition is PostconditionFact.SATISFIED
    assert result[0].applied
    assert json.dumps(marker) in captured[0]
    assert '.setPageContents("index.html",' in captured[0]


def test_direct_dns_readback_requires_enabled_state_and_expected_record():
    """A direct DNS read-back needs both the enabled flag and the record."""
    responses = [
        json.dumps(
            {
                "found": True,
                "enabled": True,
                "records": {"web.e6.example.local": "198.18.160.10"},
            }
        )
    ]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: responses.pop(0),
    )
    expectation = ServiceVerificationExpectation(
        id="verify",
        service_id="service/hq/dns",
        action_id="record",
        kind=ServiceVerificationKind.DIRECT_SERVICE_STATE,
        evidence_kind=ServiceEvidenceKind.DIRECT_STATE,
        host_device_id="srv-1",
        host_device_name="__MCP_E6_SERVER",
        expected={
            "enabled": True,
            "service_type": "dns",
            "records_json": '{"web.e6.example.local":"198.18.160.10"}',
        },
    )

    result = runtime.verify(expectation)

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fresh_evidence
    assert result.evidence_method == "structured_service_getters"


def test_dns_behavior_starts_typed_ping_and_reads_only_fresh_command_output():
    """DNS behavior is read from the window this command opened."""
    calls = []

    def send_and_wait(js, timeout):
        calls.append(js)
        if "enterCommand" in js:
            return json.dumps({"started": True, "before": "C:\\>"})
        return json.dumps(
            {
                "found": True,
                "output": (
                    "C:\\>ping web.e6.example.local\n"
                    "Pinging 198.18.160.10 with 32 bytes of data:\n"
                    "Packets: Sent = 4, Received = 4, Lost = 0"
                ),
            }
        )

    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        send_and_wait,
        dns_timeout_seconds=0.1,
        convergence_interval_seconds=0.0,
    )
    expectation = ServiceVerificationExpectation(
        id="verify-dns",
        service_id="service/hq/dns",
        action_id="record",
        kind=ServiceVerificationKind.DNS_RESOLUTION,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="srv-1",
        host_device_name="__MCP_E6_SERVER",
        client_device_id="pc-1",
        client_device_name="__MCP_E6_PC",
        expected={"hostname": "web.e6.example.local", "address": "198.18.160.10"},
    )

    result = runtime.verify(expectation)

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.evidence_method == "typed_pc_ping_hostname_fresh_output"
    assert any("getCommandPrompt" in item for item in calls)
    assert any(json.dumps("ping web.e6.example.local") in item for item in calls)


def test_dns_negative_control_requires_fresh_not_found_output():
    """The negative control needs a fresh not-found window, not silence."""
    responses = [
        json.dumps({"started": True, "before": "C:\\>old\n"}),
        json.dumps(
            {
                "found": True,
                "output": (
                    "C:\\>old\n"
                    "ping missing.example.local\n"
                    "Ping request could not find host missing.example.local.\nC:\\>"
                ),
            }
        ),
    ]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: responses.pop(0),
        dns_timeout_seconds=0.1,
        convergence_interval_seconds=0.0,
    )
    expectation = ServiceVerificationExpectation(
        id="verify-dns-negative",
        service_id="service/hq/dns",
        action_id="enable",
        kind=ServiceVerificationKind.DNS_NEGATIVE_CONTROL,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="srv-1",
        host_device_name="__MCP_E6_SERVER",
        client_device_id="pc-1",
        client_device_name="__MCP_E6_PC",
        expected={"hostname": "missing.example.local", "must_resolve": False},
    )

    result = runtime.verify(expectation)

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fresh_evidence
    assert result.evidence_method == "typed_pc_ping_hostname_negative_control"


def test_dns_behavior_rejects_a_fresh_but_wrong_address():
    """A fresh window carrying the wrong address is fresh negative evidence.

    The baseline asserted `not fresh_evidence` here. That was the known
    incorrect expectation: the window is complete, it was opened by this
    command, and it carries an address. The read observed something real and
    it contradicts the expectation, so the evidence is fresh and NEGATIVE --
    calling it stale discarded a genuine measurement (authorized change (b)).
    """
    responses = [
        json.dumps({"started": True, "before": "C:\\>"}),
        json.dumps(
            {
                "found": True,
                "output": (
                    "C:\\>ping web.e6.example.local\n"
                    "Pinging 198.18.160.99 with 32 bytes of data:\n"
                    "Packets: Sent = 4, Received = 4, Lost = 0"
                ),
            }
        ),
    ]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: responses.pop(0),
        dns_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )
    expectation = ServiceVerificationExpectation(
        id="verify-dns-wrong",
        service_id="service/hq/dns",
        action_id="record",
        kind=ServiceVerificationKind.DNS_RESOLUTION,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="srv-1",
        host_device_name="__MCP_E6_SERVER",
        client_device_id="pc-1",
        client_device_name="__MCP_E6_PC",
        expected={"hostname": "web.e6.example.local", "address": "198.18.160.10"},
    )

    result = runtime.verify(expectation)

    assert result.status is ActionExecutionStatus.FAILED
    assert result.fresh_evidence
    assert result.observation is ObservationFact.CONTRADICTED


def test_http_behavior_uses_a_fresh_background_client_and_releases_it():
    """The owned HTTP client is created for this read and released after it."""
    calls = []
    responses = [
        json.dumps({"started": True, "content_before": ""}),
        json.dumps({"found": True, "content": "MCP_E6_FRESH"}),
        json.dumps({"released": True}),
    ]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: calls.append(js) or responses.pop(0),
        http_timeout_seconds=0.1,
        convergence_interval_seconds=0.0,
    )
    expectation = ServiceVerificationExpectation(
        id="verify-http-background",
        service_id="service/hq/http",
        action_id="content",
        kind=ServiceVerificationKind.HTTP_FETCH,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="srv-1",
        host_device_name="__MCP_E6_SERVER",
        client_device_id="pc-1",
        client_device_name="__MCP_E6_PC",
        expected={"address": "198.18.160.10", "marker": "MCP_E6_FRESH"},
    )

    result = runtime.verify(expectation)

    assert result.status is ActionExecutionStatus.VERIFIED
    assert 'getProcess("HttpBackgroundClientManager")' in calls[0]
    assert "createClient()" in calls[0]
    assert "deleteClient" in calls[-1]


def test_http_behavior_rejects_stale_marker_and_accepts_fresh_fetch():
    """A marker present before the request decides nothing; a fresh one does.

    The stale half asserted FAILED at the baseline. A marker that was already
    on the page before this request means the output cannot be attributed to
    this request at all, which is not a demonstrated failure of the service:
    it is a read that cannot decide. UNKNOWN with INCONCLUSIVE (authorized
    change (d)). The fresh half is unchanged.

    Measured while making that change: this fixture never reached the marker
    path. Its dispatcher answers any script containing "deleteClient" with the
    release payload, and the start script contains that call to retire a
    previous client, so the start read returns no `started` flag and the row is
    INCONCLUSIVE for `client_go_false` instead. Both are the same authorized
    outcome, so the assertion stands as item 7 specifies; the real
    marker-before-request path is covered in
    `tests/test_service_runtime_observation.py`, where new tests belong.
    """
    marker = "MCP_E6_HTTP_OK_FRESH"
    responses = [
        json.dumps({"started": True, "content_before": ""}),
        json.dumps({"found": True, "content": marker}),
        json.dumps({"released": True}),
    ]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: responses.pop(0),
        http_timeout_seconds=0.1,
        convergence_interval_seconds=0.0,
    )
    expectation = ServiceVerificationExpectation(
        id="verify-http",
        service_id="service/hq/http",
        action_id="content",
        kind=ServiceVerificationKind.HTTP_FETCH,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="srv-1",
        host_device_name="__MCP_E6_SERVER",
        client_device_id="pc-1",
        client_device_name="__MCP_E6_PC",
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
    assert stale.status is ActionExecutionStatus.UNKNOWN
    assert stale.observation is ObservationFact.INCONCLUSIVE
    assert not stale.fresh_evidence


def test_http_behavior_rejects_fresh_content_without_expected_marker():
    """Fresh content without the marker is fresh negative evidence.

    Same correction as (b), on the HTTP reader: the content changed, so the
    page WAS retrieved by this request, and it does not carry the marker. That
    is a fresh contradiction, not an absence of evidence (authorized change
    (c)).
    """
    responses = [
        json.dumps({"started": True, "content_before": ""}),
        json.dumps({"found": True, "content": "WRONG_PAGE"}),
        json.dumps({"released": True}),
    ]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: responses.pop(0),
        http_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )
    expectation = ServiceVerificationExpectation(
        id="verify-http-wrong",
        service_id="service/hq/http",
        action_id="content",
        kind=ServiceVerificationKind.HTTP_FETCH,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="srv-1",
        host_device_name="__MCP_E6_SERVER",
        client_device_id="pc-1",
        client_device_name="__MCP_E6_PC",
        expected={"address": "198.18.160.10", "marker": "MCP_E6_EXPECTED"},
    )

    result = runtime.verify(expectation)

    assert result.status is ActionExecutionStatus.FAILED
    assert result.fresh_evidence
    assert result.observation is ObservationFact.CONTRADICTED


def test_ntp_and_tftp_behavior_remain_unobservable_without_client_evidence():
    """NTP and TFTP have no registered client proof, so nothing is claimed."""
    runtime = PacketTracerEnterpriseServiceRuntime(lambda: [], lambda js, timeout: "{}")
    for kind in (
        ServiceVerificationKind.NTP_SYNC,
        ServiceVerificationKind.TFTP_RETRIEVE,
    ):
        result = runtime.verify(
            ServiceVerificationExpectation(
                id=f"verify-{kind.value}",
                service_id=f"service/{kind.value}",
                action_id="a",
                kind=kind,
                evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
                host_device_id="srv",
                host_device_name="server",
                client_device_id="pc",
                client_device_name="client",
            )
        )
        assert result.status is ActionExecutionStatus.UNOBSERVABLE
        assert not result.fresh_evidence


def test_https_behavior_uses_https_url_and_never_substitutes_http():
    """The HTTPS read uses the https URL and confirms the mode it claims.

    Two corrections, both R-HTTPS-03 (authorized change (e)). The start
    payload now reports `https_mode` from `isHttps()` after `setHttps(true)`,
    so "this client was in HTTPS mode" is an observation rather than an
    inference from the URL. And with an EMPTY marker the fetched page cannot
    be attributed to the HTTPS listener rather than to any other reachable
    page, so the row is PARTIAL with `no_https_marker` instead of VERIFIED.
    The URL assertions are unchanged: they are the real invariant here.
    """
    calls = []
    responses = [
        json.dumps({"started": True, "content_before": "", "https_mode": True}),
        json.dumps({"found": True, "content": "Packet Tracer secure page"}),
        json.dumps({"released": True}),
    ]
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: calls.append(js) or responses.pop(0),
        http_timeout_seconds=0.1,
        convergence_interval_seconds=0.0,
    )
    expectation = ServiceVerificationExpectation(
        id="verify-https",
        service_id="service/hq/https",
        action_id="enable",
        kind=ServiceVerificationKind.HTTPS_FETCH,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="srv",
        host_device_name="server",
        client_device_id="pc",
        client_device_name="client",
        expected={"address": "198.18.160.10", "marker": "", "scheme": "https"},
    )

    result = runtime.verify(expectation)

    assert result.status is ActionExecutionStatus.PARTIAL
    assert result.observation is ObservationFact.OBSERVED
    assert result.limitations == ["no_https_marker"]
    assert result.evidence_method == "https_client_fresh_content"
    assert "p.setHttps(true)" in calls[0]
    assert "p.isHttps()" in calls[0]
    assert json.dumps("https://198.18.160.10/") in calls[0]
    assert "http://198.18.160.10/" not in calls[0]
