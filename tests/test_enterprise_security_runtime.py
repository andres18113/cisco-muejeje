"""E8 Packet Tracer adapter: typed mutation, read-back and behavior."""

from __future__ import annotations

import json
from pathlib import Path

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.security_plan import (
    ApplyDeviceHardening,
    SecurityDecision,
    SecurityProbeKind,
    SecurityVerificationExpectation,
    SecurityVerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.security_runtime import (
    RuntimeSecurityVerification,
    SecurityVerificationStage,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_security_runtime import (
    PacketTracerEnterpriseSecurityRuntime,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosCommandResult,
    IosSessionState,
    OperationalQueryId,
)
from tests.test_enterprise_security import _compile


FIXTURES = Path(__file__).parent / "fixtures"


class FakeSecurityIos:
    def __init__(self) -> None:
        self.calls: list[tuple[str, OperationalQueryId, str]] = []

    def execute(self, device_name, query_id, *, interface=""):
        self.calls.append((device_name, query_id, interface))
        if query_id is OperationalQueryId.SHOW_ACCESS_LISTS:
            output = (
                "show access-lists\nExtended IP access list 100\n"
                "  10 permit tcp 10.0.10.0 0.0.0.255 host 10.0.50.10 eq 80\n"
                "Extended IP access list 101\n"
                "  10 deny tcp 10.0.20.0 0.0.0.255 host 10.0.50.10 eq 80\nRouter#"
            )
        elif query_id is OperationalQueryId.SHOW_IP_INTERFACE:
            acl = "100" if interface.endswith(".10") else "101"
            output = (
                f"show ip interface {interface}\n{interface} is up, line protocol is up\n"
                f"  Outgoing access list is not set\n  Inbound  access list is {acl}\nRouter#"
            )
        elif query_id is OperationalQueryId.SHOW_IP_NAT_STATISTICS:
            output = (
                "show ip nat statistics\nTotal translations: 0 (0 static, 0 dynamic, 0 extended)\n"
                "Outside Interfaces: GigabitEthernet0/1.900\n"
                "Inside Interfaces: GigabitEthernet0/0.10, GigabitEthernet0/0.20, GigabitEthernet0/0.50\n"
                "Hits: 0 Misses: 0\nRouter#"
            )
        else:
            output = None
        fixture = {
            OperationalQueryId.SHOW_IP_NAT_TRANSLATIONS:
                "packet_tracer_9_0_1_0858_show_ip_nat_translations_empty.txt",
            OperationalQueryId.SHOW_PORT_SECURITY_INTERFACE:
                "packet_tracer_9_0_1_0858_show_port_security_interface.txt",
            OperationalQueryId.SHOW_IP_DHCP_SNOOPING:
                "packet_tracer_9_0_1_0858_show_ip_dhcp_snooping.txt",
            OperationalQueryId.SHOW_IP_ARP_INSPECTION:
                "packet_tracer_9_0_1_0858_show_ip_arp_inspection.txt",
        }.get(query_id)
        if output is None:
            output = (FIXTURES / fixture).read_text(encoding="utf-8")
        return IosCommandResult(
            device_name=device_name,
            query_id=query_id,
            executed=True,
            output=output,
            session_state=IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=True,
            window_strategy="prefix_delta",
        )


def _inventory():
    return {"devices": [
        {"name": "HQ-R1", "model": "2911", "ports": [
            {"name": "GigabitEthernet0/0"},
            {"name": "GigabitEthernet0/1"},
        ]},
        {"name": "HQ-SW1", "model": "2960-24TT", "ports": [
            {"name": "FastEthernet0/1"},
            {"name": "GigabitEthernet0/1"},
        ]},
    ]}


def test_runtime_applies_and_cleans_only_renderer_owned_security_payloads():
    sent = []
    plan = _compile().plan
    runtime = PacketTracerEnterpriseSecurityRuntime(
        _inventory,
        lambda script: sent.append(script) or True,
        lambda _script, _timeout: None,
        ios_readiness=lambda _name: True,
        ios_executor=FakeSecurityIos(),
    )
    runtime.inventory()

    applied = runtime.apply_actions(plan.actions)
    cleaned = runtime.cleanup_actions(list(reversed(plan.actions)))

    assert all(item.applied for item in applied)
    assert all(item.applied for item in cleaned)
    assert len(sent) == len(plan.actions) * 2
    assert all("configureIosDevice" in item for item in sent)
    assert not any("getCommandPrompt" in item or "getScreen" in item for item in sent)


def test_runtime_direct_readback_preserves_verified_and_unobservable_fields():
    plan = _compile().plan
    ios = FakeSecurityIos()
    runtime = PacketTracerEnterpriseSecurityRuntime(
        _inventory, lambda _script: True, lambda _script, _timeout: None,
        ios_readiness=lambda _name: True, ios_executor=ios,
    )
    runtime.inventory()
    runtime.apply_actions(plan.actions)

    direct = [
        item for item in plan.verification_expectations
        if item.probe_kind is SecurityProbeKind.DIRECT_READBACK
    ]
    observed = runtime.observe(direct)
    by_kind = {
        expectation.kind: result
        for expectation, result in zip(direct, observed, strict=True)
    }

    assert by_kind[SecurityVerificationKind.ACL_DIRECT_STATE].status is ActionExecutionStatus.VERIFIED
    assert by_kind[SecurityVerificationKind.NAT_DIRECT_STATE].status is ActionExecutionStatus.VERIFIED
    assert by_kind[SecurityVerificationKind.PORT_SECURITY_STATE].status is ActionExecutionStatus.UNOBSERVABLE
    assert by_kind[SecurityVerificationKind.PORT_SECURITY_STATE].fields["policy"] is FieldVerificationStatus.VERIFIED
    assert by_kind[SecurityVerificationKind.DHCP_SNOOPING_STATE].status is ActionExecutionStatus.VERIFIED
    assert by_kind[SecurityVerificationKind.DAI_STATE].status is ActionExecutionStatus.UNOBSERVABLE
    assert by_kind[SecurityVerificationKind.DAI_STATE].fields["vlans"] is FieldVerificationStatus.VERIFIED
    assert by_kind[SecurityVerificationKind.DAI_STATE].fields["trusted_interfaces"] is FieldVerificationStatus.UNOBSERVABLE
    assert by_kind[SecurityVerificationKind.HARDENING_STATE].status is ActionExecutionStatus.UNOBSERVABLE


def test_typed_ping_uses_plan_address_and_proves_allow_or_deny():
    scripts = []
    output = (
        "C:\\>ping 10.0.50.10\n"
        "Packets: Sent = 4, Received = 0, Lost = 4 (100% loss)\nC:\\>"
    )

    def send_and_wait(script, _timeout):
        scripts.append(script)
        if "enterCommand" in script:
            return json.dumps({"started": True, "before": "C:\\>"})
        return json.dumps({"found": True, "output": "C:\\>" + output})

    runtime = PacketTracerEnterpriseSecurityRuntime(
        lambda: [], lambda _script: True, send_and_wait,
        behavior_timeout_seconds=0,
    )
    expectation = SecurityVerificationExpectation(
        id="deny", kind=SecurityVerificationKind.TRAFFIC_POLICY,
        action_id="acl", policy_id="deny",
        probe_kind=SecurityProbeKind.ICMP_REACHABILITY,
        expected_decision=SecurityDecision.DENY,
        source_device_id="pc", source_device_name="GUEST-PC",
        destination_device_id="server", destination_device_name="WEB-SRV",
        destination_address="10.0.50.10", protocol="icmp",
    )

    deny = runtime.verify_behavior(
        [expectation], SecurityVerificationStage.ENFORCEMENT_BEHAVIOR,
    )[0]
    baseline = runtime.verify_behavior(
        [expectation], SecurityVerificationStage.BASELINE,
    )[0]

    assert deny.status is ActionExecutionStatus.VERIFIED
    assert baseline.status is ActionExecutionStatus.FAILED
    assert deny.fresh_evidence
    assert any('enterCommand("ping 10.0.50.10")' in item for item in scripts)


def test_voice_behavior_is_only_reached_through_injected_typed_e7_adapter():
    calls = []

    def voice_driver(expectation, stage):
        calls.append((expectation.id, stage))
        return RuntimeSecurityVerification(
            expectation_id=expectation.id, stage=stage,
            status=ActionExecutionStatus.VERIFIED,
            evidence_method="typed_e7_behavior",
            fresh_evidence=True,
        )

    expectation = SecurityVerificationExpectation(
        id="voice", kind=SecurityVerificationKind.TRAFFIC_POLICY,
        action_id="voice-acl", policy_id="voice-policy",
        probe_kind=SecurityProbeKind.VOICE_CALL,
    )
    runtime = PacketTracerEnterpriseSecurityRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        voice_behavior=voice_driver,
    )

    result = runtime.verify_behavior(
        [expectation], SecurityVerificationStage.ENFORCEMENT_BEHAVIOR,
    )[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert calls == [("voice", SecurityVerificationStage.ENFORCEMENT_BEHAVIOR)]


def test_missing_voice_adapter_is_unobservable_without_bridge_or_ui_calls():
    scripts = []
    expectation = SecurityVerificationExpectation(
        id="voice", kind=SecurityVerificationKind.TRAFFIC_POLICY,
        action_id="voice-acl", policy_id="voice-policy",
        probe_kind=SecurityProbeKind.VOICE_CALL,
    )
    runtime = PacketTracerEnterpriseSecurityRuntime(
        lambda: [], lambda _script: True,
        lambda script, _timeout: scripts.append(script) or None,
    )

    result = runtime.verify_behavior(
        [expectation], SecurityVerificationStage.ENFORCEMENT_BEHAVIOR,
    )[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert scripts == []


def test_hardening_reuses_existing_structured_security_getters():
    plan = _compile().plan
    action = next(item for item in plan.actions if isinstance(item, ApplyDeviceHardening))
    expectation = next(
        item for item in plan.verification_expectations
        if item.action_id == action.id
    )
    scripts = []

    def send_and_wait(script, _timeout):
        scripts.append(script)
        return json.dumps({
            "found": True,
            "banner_getter": True,
            "banner": f"#{action.banner_motd}#",
            "encryption_getter": True,
            "encryption": action.service_password_encryption,
        })

    runtime = PacketTracerEnterpriseSecurityRuntime(
        _inventory, lambda _script: True, send_and_wait,
        ios_readiness=lambda _name: True, ios_executor=FakeSecurityIos(),
    )
    runtime.inventory()
    runtime.apply_actions([action])
    result = runtime.observe([expectation])[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.evidence_method == "structured_security_getters"
    assert any("getBannerMotd" in item for item in scripts)
    assert not any("getEnableSecret" in item or "getUserPass" in item for item in scripts)
