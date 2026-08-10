"""E8 Packet Tracer adapter: typed mutation, read-back and behavior."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.security_plan import (
    ApplyDeviceHardening,
    CompiledDynamicNatPool,
    CompiledStaticNatMapping,
    ConfigureDynamicArpInspection,
    ConfigureSecurityNat,
    NatMode,
    SecurityCapabilityDimension,
    SecurityDecision,
    SecurityPhase,
    SecurityProbeKind,
    SecurityVerificationExpectation,
    SecurityVerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.security_runtime import (
    RuntimeSecurityVerification,
    SecurityVerificationStage,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_runtime import (
    PhoneExecutionMethod,
    RuntimeCallObservation,
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


class StaleSecurityIos(FakeSecurityIos):
    def execute(self, device_name, query_id, *, interface=""):
        return replace(
            super().execute(device_name, query_id, interface=interface),
            fresh_output_observed=False,
            window_strategy="no_fresh_window",
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


def test_matching_but_stale_direct_output_is_unobservable_not_verified():
    plan = _compile().plan
    action = next(item for item in plan.actions if isinstance(item, ConfigureSecurityNat))
    expectation = next(
        item for item in plan.verification_expectations
        if item.action_id == action.id
        and item.kind is SecurityVerificationKind.NAT_DIRECT_STATE
    )
    runtime = PacketTracerEnterpriseSecurityRuntime(
        _inventory, lambda _script: True, lambda _script, _timeout: None,
        ios_readiness=lambda _name: True, ios_executor=StaleSecurityIos(),
    )
    runtime._actions[action.id] = action

    result = runtime.observe([expectation])[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert not result.fresh_evidence


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


def test_voice_behavior_is_only_reached_through_injected_e7_call_port():
    class FakeE7CallPort:
        def __init__(self):
            self.calls = []

        def execute_planned_call(self, call_expectation_id):
            self.calls.append(call_expectation_id)
            return RuntimeCallObservation(
                call_expectation_id=call_expectation_id,
                call_attempt_id="attempt-1",
                source_phone_id="phone-1",
                dialed_extension="1002",
                connected=True,
                teardown_verified=True,
                execution_method=PhoneExecutionMethod.STRUCTURED_API,
                status=ActionExecutionStatus.VERIFIED,
                evidence_method="typed_e7_behavior",
                fresh_evidence=True,
            )

    call_port = FakeE7CallPort()
    expectation = SecurityVerificationExpectation(
        id="voice", kind=SecurityVerificationKind.TRAFFIC_POLICY,
        action_id="voice-acl", policy_id="voice-policy",
        probe_kind=SecurityProbeKind.VOICE_CALL,
        voice_call_expectation_id="call/local-1",
    )
    runtime = PacketTracerEnterpriseSecurityRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        voice_call_operation=call_port,
    )

    result = runtime.verify_behavior(
        [expectation], SecurityVerificationStage.ENFORCEMENT_BEHAVIOR,
    )[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.evidence_method == "e7_planned_voice_call_structured_api"
    assert call_port.calls == ["call/local-1"]


def test_generic_voice_callback_is_not_an_e8_runtime_parameter():
    import inspect

    parameters = inspect.signature(PacketTracerEnterpriseSecurityRuntime).parameters

    assert "voice_behavior" not in parameters
    assert "voice_call_operation" in parameters


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


class SequenceNatIos:
    def __init__(self, translations: list[str], statistics: list[str]) -> None:
        self._translations = iter(translations)
        self._statistics = iter(statistics)

    def execute(self, device_name, query_id, *, interface=""):
        del interface
        output = next(
            self._translations
            if query_id is OperationalQueryId.SHOW_IP_NAT_TRANSLATIONS
            else self._statistics
        )
        return IosCommandResult(
            device_name=device_name,
            query_id=query_id,
            executed=True,
            output=output,
            session_state=IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=True,
            window_strategy="prefix_delta",
        )


def _nat_action(mode: NatMode) -> ConfigureSecurityNat:
    updates = {}
    if mode is NatMode.STATIC:
        updates["static_mappings"] = [CompiledStaticNatMapping(
            inside_endpoint_id="inside-pc",
            inside_local_address="10.0.10.10",
            outside_global_address="198.51.100.20",
        )]
    elif mode is NatMode.DYNAMIC:
        updates["dynamic_pool"] = CompiledDynamicNatPool(
            name="E8_POOL",
            start_address="198.51.100.21",
            end_address="198.51.100.30",
            netmask="255.255.255.0",
        )
    return ConfigureSecurityNat(
        id=f"nat-{mode.value}",
        phase=SecurityPhase.ENFORCEMENT,
        device_id="r1",
        device_name="HQ-R1",
        model="2911",
        site_id="hq",
        required_capability={
            NatMode.PAT: SecurityCapabilityDimension.NAT_PAT_CONFIG,
            NatMode.STATIC: SecurityCapabilityDimension.NAT_STATIC_CONFIG,
            NatMode.DYNAMIC: SecurityCapabilityDimension.NAT_DYNAMIC_CONFIG,
        }[mode],
        policy_id=f"policy-{mode.value}",
        mode=mode,
        inside_interfaces=["GigabitEthernet0/0"],
        outside_interface="GigabitEthernet0/1",
        inside_networks=["10.0.10.0/24"],
        translation_acl_number=1 if mode is not NatMode.STATIC else 0,
        **updates,
    )


def _nat_expectation(action: ConfigureSecurityNat) -> SecurityVerificationExpectation:
    return SecurityVerificationExpectation(
        id=f"verify-{action.id}",
        kind=SecurityVerificationKind.NAT_TRANSLATION,
        action_id=action.id,
        policy_id=action.policy_id,
        probe_kind=SecurityProbeKind.ICMP_REACHABILITY,
        source_device_id="inside-pc",
        source_device_name="INSIDE-PC",
        source_address="10.0.10.10",
        destination_device_id="outside-pc",
        destination_device_name="OUTSIDE-PC",
        destination_address="203.0.113.10",
    )


def _statistics(hits: int) -> str:
    return (
        "show ip nat statistics\n"
        "Total translations: 1 (0 static, 1 dynamic, 1 extended)\n"
        "Outside Interfaces: GigabitEthernet0/1\n"
        "Inside Interfaces: GigabitEthernet0/0\n"
        f"Hits: {hits} Misses: 0\nRouter#"
    )


def test_nat_behavior_rejects_unrelated_translation_and_stale_hit_counter():
    action = _nat_action(NatMode.PAT)
    unrelated = (
        "show ip nat translations\n"
        "Pro Inside global Inside local Outside local Outside global\n"
        "icmp 198.51.100.1:9 10.0.10.99:9 203.0.113.10:9 203.0.113.10:9\n"
        "Router#"
    )
    runtime = PacketTracerEnterpriseSecurityRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ios_executor=SequenceNatIos([unrelated, unrelated], [_statistics(7), _statistics(7)]),
    )
    runtime._actions[action.id] = action
    runtime._typed_ping = lambda _expectation: (True, True)

    result = runtime.verify_behavior(
        [_nat_expectation(action)], SecurityVerificationStage.ENFORCEMENT_BEHAVIOR,
    )[0]

    assert result.status is not ActionExecutionStatus.VERIFIED
    assert result.fields["exact_translation"] is FieldVerificationStatus.FAILED


def test_nat_behavior_requires_exact_new_or_hit_delta_for_current_probe():
    action = _nat_action(NatMode.DYNAMIC)
    empty = "show ip nat translations\nRouter#"
    exact = (
        "show ip nat translations\n"
        "Pro Inside global Inside local Outside local Outside global\n"
        "icmp 198.51.100.21:4 10.0.10.10:4 203.0.113.10:4 203.0.113.10:4\n"
        "Router#"
    )
    runtime = PacketTracerEnterpriseSecurityRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ios_executor=SequenceNatIos([empty, exact], [_statistics(0), _statistics(1)]),
    )
    runtime._actions[action.id] = action
    runtime._typed_ping = lambda _expectation: (True, True)

    result = runtime.verify_behavior(
        [_nat_expectation(action)], SecurityVerificationStage.ENFORCEMENT_BEHAVIOR,
    )[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fields["exact_translation"] is FieldVerificationStatus.VERIFIED
    assert result.fields["translation_delta"] is FieldVerificationStatus.VERIFIED


def test_static_nat_requires_exact_mapping_and_current_hit_delta():
    action = _nat_action(NatMode.STATIC)
    exact = (
        "show ip nat translations\n"
        "Pro Inside global Inside local Outside local Outside global\n"
        "--- 198.51.100.20 10.0.10.10 --- ---\n"
        "Router#"
    )
    runtime = PacketTracerEnterpriseSecurityRuntime(
        lambda: [], lambda _script: True, lambda _script, _timeout: None,
        ios_executor=SequenceNatIos([exact, exact], [_statistics(2), _statistics(3)]),
    )
    runtime._actions[action.id] = action
    runtime._typed_ping = lambda _expectation: (True, True)

    result = runtime.verify_behavior(
        [_nat_expectation(action)], SecurityVerificationStage.ENFORCEMENT_BEHAVIOR,
    )[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.fields["exact_translation"] is FieldVerificationStatus.VERIFIED
    assert result.fields["translation_delta"] is FieldVerificationStatus.VERIFIED


def test_dai_vlan_readback_does_not_prove_default_untrusted_ports():
    action = ConfigureDynamicArpInspection(
        id="dai", phase=SecurityPhase.ENFORCEMENT,
        device_id="sw1", device_name="HQ-SW1", model="2960-24TT", site_id="hq",
        required_capability=SecurityCapabilityDimension.DAI_CONFIG,
        policy_id="inspection", vlan_ids=[10], trusted_interfaces=[],
    )
    expectation = SecurityVerificationExpectation(
        id="verify-dai", kind=SecurityVerificationKind.DAI_STATE,
        action_id=action.id, policy_id=action.policy_id,
        probe_kind=SecurityProbeKind.DIRECT_READBACK,
    )
    runtime = PacketTracerEnterpriseSecurityRuntime(
        _inventory, lambda _script: True, lambda _script, _timeout: None,
        ios_readiness=lambda _name: True, ios_executor=FakeSecurityIos(),
    )
    runtime._actions[action.id] = action

    result = runtime.observe([expectation])[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.fields["vlans"] is FieldVerificationStatus.VERIFIED
    assert result.fields["untrusted_interfaces"] is FieldVerificationStatus.UNOBSERVABLE
