"""E8 Cisco renderer consumes only trusted typed SecurityPlan actions."""

from __future__ import annotations

from src.packet_tracer_mcp.infrastructure.generator.security_renderer import (
    PacketTracerSecurityRenderer,
)
from tests.test_enterprise_security import _compile
from tests.test_enterprise_security import _fixture
from src.packet_tracer_mcp.application.use_cases.compile_security import (
    compile_enterprise_security,
)
from src.packet_tracer_mcp.domain.enterprise.models.security_plan import (
    AddSecurityAclRule,
    SecurityCapabilityDimension,
    SecurityDecision,
    SecurityPhase,
    DynamicNatPoolIntent,
    NatMode,
    NatPolicyIntent,
    StaticNatMappingIntent,
)


def test_acl_renderer_reuses_numbered_acl_semantics_and_exact_attachment():
    plan = _compile().plan
    rendered = PacketTracerSecurityRenderer().render_actions(plan.actions)
    payload = "\n".join(item.ios_payload for item in rendered)

    assert "access-list 100 permit tcp 10.0.10.0 0.0.0.255 host 10.0.50.10 eq 80" in payload
    assert "access-list 101 deny tcp 10.0.20.0 0.0.0.255 host 10.0.50.10 eq 80" in payload
    assert "ip access-group 100 in" in payload
    assert "interface GigabitEthernet0/0.10" in payload


def test_nat_port_security_hardening_and_inspection_reuse_existing_primitives():
    plan = _compile().plan
    rendered = PacketTracerSecurityRenderer().render_actions(plan.actions)
    payload = "\n".join(item.ios_payload for item in rendered)

    assert "ip nat inside" in payload
    assert "ip nat outside" in payload
    assert " overload" in payload
    nat = next(item for item in plan.actions if item.action_type.value == "configure_nat")
    assert f"access-list {nat.translation_acl_number} permit 10.0.10.0 0.0.0.255" in payload
    assert "switchport port-security maximum 1" in payload
    assert "switchport port-security violation restrict" in payload
    assert "service password-encryption" in payload
    assert "banner motd #Authorized access only#" in payload
    assert "ip dhcp snooping vlan 10" in payload
    assert "ip arp inspection vlan 10" in payload
    assert "interface GigabitEthernet0/1" in payload
    assert "ip dhcp snooping trust" in payload


def test_every_rendered_mutation_has_typed_cleanup_and_no_javascript_or_phone_ui():
    plan = _compile().plan
    rendered = PacketTracerSecurityRenderer().render_actions(plan.actions)

    assert len(rendered) == len(plan.actions)
    assert all(item.action_id and item.device_name for item in rendered)
    assert all(item.ios_payload.startswith("enable\nconfigure terminal\n") for item in rendered)
    assert all(item.cleanup_payload.startswith("enable\nconfigure terminal\n") for item in rendered)
    combined = "\n".join(
        item.ios_payload + "\n" + item.cleanup_payload for item in rendered
    ).casefold()
    assert "ipc." not in combined
    assert "phone" not in combined
    assert "screen" not in combined
    assert "click" not in combined


def test_renderer_is_deterministic_for_reordered_action_input():
    plan = _compile().plan
    renderer = PacketTracerSecurityRenderer()
    forward = renderer.render_actions(plan.actions)
    reverse = renderer.render_actions(list(reversed(plan.actions)))

    assert [item.model_dump() for item in forward] == [item.model_dump() for item in reverse]


def test_multiple_typed_source_ports_expand_instead_of_widening_the_acl():
    action = AddSecurityAclRule(
        id="ports", phase=SecurityPhase.ENFORCEMENT,
        device_id="r1", device_name="R1", model="2911", site_id="hq",
        required_capability=SecurityCapabilityDimension.ACL_CONFIG,
        acl_name="100", sequence=10, decision=SecurityDecision.ALLOW,
        protocol="tcp", source_cidr="10.0.10.0/24",
        destination_cidr="10.0.50.10/32",
        source_ports=[1024, 1025], destination_ports=[80],
    )

    payload = PacketTracerSecurityRenderer().render_action(action).ios_payload

    assert "eq 1024 host 10.0.50.10 eq 80" in payload
    assert "eq 1025 host 10.0.50.10 eq 80" in payload


def test_static_and_dynamic_nat_render_and_cleanup_from_typed_fields():
    topology, configuration, services, intent, capabilities = _fixture()
    intent.nat_policies = [
        NatPolicyIntent(
            id="static", router_device_id="r1", mode=NatMode.STATIC,
            inside_segment_ids=["servers"], outside_segment_id="wan",
            static_mappings=[StaticNatMappingIntent(
                inside_endpoint_id="web", outside_global_address="198.51.100.20",
            )],
        ),
        NatPolicyIntent(
            id="dynamic", router_device_id="r1", mode=NatMode.DYNAMIC,
            inside_segment_ids=["sales"], outside_segment_id="wan",
            dynamic_pool=DynamicNatPoolIntent(
                start_address="198.51.100.21", end_address="198.51.100.30",
                prefix=24,
            ),
        ),
    ]
    plan = compile_enterprise_security(
        intent, topology, configuration, service_plan=services,
        capabilities=capabilities,
    ).plan
    rendered = [
        PacketTracerSecurityRenderer().render_action(item)
        for item in plan.actions if item.action_type.value == "configure_nat"
    ]
    payload = "\n".join(item.ios_payload for item in rendered)
    cleanup = "\n".join(item.cleanup_payload for item in rendered)

    assert "ip nat inside source static 10.0.50.10 198.51.100.20" in payload
    assert "ip nat pool E8_DYNAMIC 198.51.100.21 198.51.100.30 netmask 255.255.255.0" in payload
    assert "ip nat inside source list" in payload and "pool E8_DYNAMIC" in payload
    assert "no ip nat inside source static 10.0.50.10 198.51.100.20" in cleanup
    assert "no ip nat pool E8_DYNAMIC" in cleanup
