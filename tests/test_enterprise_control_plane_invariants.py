from __future__ import annotations

from copy import deepcopy

from src.packet_tracer_mcp.application.use_cases.compile_control_plane import (
    compile_enterprise_control_plane,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationIssueCode,
    ConfigurationPhase,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureHsrp,
    ControlPlaneVerificationKind,
    EtherChannelIntent,
    EtherChannelProtocol,
    FirstHopRedundancyIntent,
)
from src.packet_tracer_mcp.domain.models.plans import LinkPlan

from tests.test_enterprise_control_plane import _fixture


def _compile_fixture(intent, topology, configuration, capabilities):
    return compile_enterprise_control_plane(
        intent,
        topology,
        configuration,
        capabilities=capabilities,
    )


def test_hsrp_vip_cannot_collide_with_an_e5_endpoint_address():
    intent, topology, configuration, capabilities = _fixture()
    intent.first_hop_redundancy[0].virtual_ipv4 = "10.0.10.10"

    result = _compile_fixture(intent, topology, configuration, capabilities)

    assert not result.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_HSRP_VIP_COLLISION in {
        issue.code for issue in result.issues
    }


def test_hsrp_virtual_address_cannot_be_owned_by_two_groups():
    intent, topology, configuration, capabilities = _fixture()
    intent.first_hop_redundancy.append(FirstHopRedundancyIntent(
        id="hsrp/hq-data-duplicate",
        segment_id="hq-data",
        device_ids=["r1", "r2"],
        virtual_ipv4="10.0.10.1",
    ))

    result = _compile_fixture(intent, topology, configuration, capabilities)

    assert not result.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_HSRP_VIP_COLLISION in {
        issue.code for issue in result.issues
    }


def test_hsrp_expectations_name_active_standby_and_use_an_endpoint_probe():
    intent, topology, configuration, capabilities = _fixture()
    intent.first_hop_redundancy[0].priority_by_device = {"r1": 100, "r2": 120}

    result = _compile_fixture(intent, topology, configuration, capabilities)

    assert result.is_valid, result.issues
    hsrp_actions = {
        action.device_id: action
        for action in result.plan.actions
        if isinstance(action, ConfigureHsrp)
    }
    states = {
        expectation.device_id: expectation.expected
        for expectation in result.plan.verification_expectations
        if expectation.kind is ControlPlaneVerificationKind.HSRP_STATE
    }
    behavior = [
        expectation
        for expectation in result.plan.verification_expectations
        if expectation.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
        and expectation.expected.get("virtual_gateway_ipv4") == "10.0.10.1"
    ]

    assert hsrp_actions["r2"].priority == 120
    assert states["r2"]["expected_role"] == "active"
    assert states["r1"]["expected_role"] == "standby"
    assert states["r1"]["preferred_active_device_id"] == "r2"
    assert len(behavior) == 1
    assert behavior[0].device_id == "pc1"
    assert behavior[0].expected["destination_ipv4"] == "10.0.10.1"


def test_hsrp_priority_map_cannot_reference_a_non_member():
    intent, topology, configuration, capabilities = _fixture()
    intent.first_hop_redundancy[0].priority_by_device = {"not-a-member": 150}

    result = _compile_fixture(intent, topology, configuration, capabilities)

    assert not result.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_INTENT_INVALID in {
        issue.code for issue in result.issues
    }


def test_etherchannel_rejects_two_e4_links_reusing_one_physical_port():
    intent, topology, configuration, capabilities = _fixture()
    duplicate = next(link for link in topology.links if link.id == "sw-member-b")
    duplicate.port_a = "GigabitEthernet0/1"
    trunk = next(
        action for action in configuration.actions
        if getattr(action, "id", "") == "cfg/trunk/sw1/sw-member-b"
    )
    trunk.interface = "GigabitEthernet0/1"

    result = _compile_fixture(intent, topology, configuration, capabilities)

    assert not result.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_ETHERCHANNEL_MEMBER_INVALID in {
        issue.code for issue in result.issues
    }


def test_etherchannel_rejects_members_with_different_e4_link_roles():
    intent, topology, configuration, capabilities = _fixture()
    first, second = topology.links[:2]
    first.link_role = "distribution_uplink"
    second.link_role = "unrelated_backup"

    result = _compile_fixture(intent, topology, configuration, capabilities)

    assert not result.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_ETHERCHANNEL_MEMBER_INVALID in {
        issue.code for issue in result.issues
    }


def test_etherchannel_rejects_same_physical_port_across_two_bundles():
    intent, topology, configuration, capabilities = _fixture()
    base_a, base_b = topology.links[:2]
    topology.links.extend([
        LinkPlan(
            id="sw-second-a",
            device_a=base_a.device_a,
            device_a_id=base_a.device_a_id,
            port_a=base_a.port_a,
            device_b=base_a.device_b,
            device_b_id=base_a.device_b_id,
            port_b="GigabitEthernet0/3",
            cable="cross",
            link_role=base_a.link_role,
        ),
        LinkPlan(
            id="sw-second-b",
            device_a=base_b.device_a,
            device_a_id=base_b.device_a_id,
            port_a="GigabitEthernet0/4",
            device_b=base_b.device_b,
            device_b_id=base_b.device_b_id,
            port_b="GigabitEthernet0/4",
            cable="cross",
            link_role=base_a.link_role,
        ),
    ])
    # The new members deliberately reuse sw1:GigabitEthernet0/1 in another bundle.
    from src.packet_tracer_mcp.domain.enterprise.models.configuration import ConfigureTrunk

    for link in topology.links[-2:]:
        configuration.actions.extend([
            ConfigureTrunk(
                id=f"cfg/trunk/sw1/{link.id}",
                phase=ConfigurationPhase.L2_INTERFACES,
                device_id="sw1",
                device_name="HQ-SW1",
                site_id="hq",
                interface=link.port_a,
                allowed_vlans=[10, 20],
                source_link_id=link.id,
                peer_device_id="sw2",
            ),
            ConfigureTrunk(
                id=f"cfg/trunk/sw2/{link.id}",
                phase=ConfigurationPhase.L2_INTERFACES,
                device_id="sw2",
                device_name="HQ-SW2",
                site_id="hq",
                interface=link.port_b,
                allowed_vlans=[10, 20],
                source_link_id=link.id,
                peer_device_id="sw1",
            ),
        ])
    intent.etherchannels.append(EtherChannelIntent(
        id="ec/hq-second",
        member_link_ids=["sw-second-a", "sw-second-b"],
        protocol=EtherChannelProtocol.LACP,
    ))

    result = _compile_fixture(intent, topology, configuration, capabilities)

    assert not result.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_ETHERCHANNEL_CONFLICT in {
        issue.code for issue in result.issues
    }


def test_route_expectations_keep_prefix_but_ospf_omits_unobservable_metadata():
    intent, topology, configuration, capabilities = _fixture()

    result = _compile_fixture(intent, topology, configuration, capabilities)

    assert result.is_valid, result.issues
    routes = [
        expectation
        for expectation in result.plan.verification_expectations
        if expectation.kind is ControlPlaneVerificationKind.ROUTE_PRESENT
    ]
    assert routes
    assert all(
        isinstance(item.expected.get("prefix_length"), int) for item in routes
    )
    ospf = [item for item in routes if item.expected.get("protocol") == "ospfv2"]
    other = [item for item in routes if item.expected.get("protocol") != "ospfv2"]
    assert ospf
    assert all(
        set(item.expected) == {"network", "prefix_length", "protocol"}
        for item in ospf
    )
    # Omitido de `expected` no es lo mismo que olvidado: sigue declarado como
    # no reclamable, y por eso el estado agregado no sube al estrecharlo.
    assert all(item.unclaimed_fields == ["wildcard", "segment_id"] for item in ospf)
    assert all(item.expected.get("segment_id") for item in other)
    assert all(item.unclaimed_fields == [] for item in other)


def test_routing_behavior_uses_e5_endpoint_identities_when_available():
    intent, topology, configuration, capabilities = _fixture()

    result = _compile_fixture(intent, topology, configuration, capabilities)

    assert result.is_valid, result.issues
    endpoint_checks = [
        expectation
        for expectation in result.plan.verification_expectations
        if expectation.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
        and expectation.device_id == "pc1"
        and expectation.peer_device_id == "pc2"
    ]
    assert len(endpoint_checks) == 1
    assert endpoint_checks[0].expected == {
        "destination_ipv4": "10.0.102.10",
        "reachable": True,
        "protocol": "ospfv2",
    }


def test_failure_survivor_links_must_form_an_actual_alternate_e4_path():
    intent, topology, configuration, capabilities = _fixture()
    intent.failure_scenarios[0].expected_surviving_link_ids = ["hq-transit"]

    result = _compile_fixture(intent, topology, configuration, capabilities)

    assert not result.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_INTENT_INVALID in {
        issue.code for issue in result.issues
    }


def test_router_id_collision_is_a_structured_compiler_error():
    intent, topology, configuration, capabilities = _fixture()
    intent.routing_domains[0].router_ids = {"r1": "1.1.1.1", "r2": "1.1.1.1"}

    result = _compile_fixture(intent, topology, configuration, capabilities)

    assert not result.is_valid
    assert ConfigurationIssueCode.CONTROL_PLANE_ROUTER_ID_COLLISION in {
        issue.code for issue in result.issues
    }


def test_new_invariants_do_not_mutate_the_source_plans():
    intent, topology, configuration, capabilities = _fixture()
    before = (deepcopy(intent), deepcopy(topology), deepcopy(configuration))

    _compile_fixture(intent, topology, configuration, capabilities)

    assert (intent, topology, configuration) == before
