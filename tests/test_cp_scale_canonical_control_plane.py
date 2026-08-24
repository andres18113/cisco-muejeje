"""Canonical CP-SCALE E9 intent owns exact STP and RIPv2 policy."""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.compile_control_plane import (
    compile_enterprise_control_plane,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureRipv2,
    ConfigureSpanningTree,
    ConfigureStpEdgePort,
    ControlPlaneCapabilityProfile,
    ControlPlaneVerificationKind,
    StpMode,
)
from src.packet_tracer_mcp.domain.enterprise.scenarios.cp_scale_physical import (
    MLS3,
    MLS7,
    SW3,
    SW8,
    SW10,
    cp_scale_canonical_control_plane_intent,
)
from tests.test_cp_scale_canonical_configuration import _configuration
from tests.test_cp_scale_canonical_physical import _compile


def _control_plane():
    enterprise, _, _ = _compile()
    topology, configuration = _configuration()
    intent = cp_scale_canonical_control_plane_intent(topology)
    capabilities = {
        item.model: ControlPlaneCapabilityProfile.supported(item.model)
        for item in topology.devices
    }
    result = compile_enterprise_control_plane(
        intent,
        topology,
        configuration,
        capabilities=capabilities,
        traffic_flows=enterprise.traffic_flows,
    )
    assert result.is_valid, [item.model_dump(mode="json") for item in result.issues]
    assert result.plan is not None
    return intent, topology, configuration, result.plan


def test_documented_stp_roots_and_governed_pvst_fallback_are_explicit():
    intent, _, _, plan = _control_plane()
    domains = {item.site_id: item for item in intent.stp_domains}

    assert all(item.mode is StpMode.PVST for item in domains.values())
    assert domains["large-branch"].root_primary_by_vlan == {
        10: SW8, 20: SW8, 30: SW8,
    }
    assert domains["large-branch"].root_secondary_by_vlan == {
        10: SW10, 20: SW10, 30: SW10,
    }
    assert domains["multilayer-branch"].root_primary_by_vlan == {
        10: MLS3, 20: MLS3, 30: MLS3,
    }
    assert domains["multilayer-branch"].root_secondary_by_vlan == {
        10: MLS7, 20: MLS7, 30: MLS7,
    }
    assert domains["small-branch"].root_primary_by_vlan == {
        10: SW3, 20: SW3, 30: SW3,
    }
    assert domains["small-branch"].root_secondary_by_vlan == {}

    actions = [item for item in plan.actions if isinstance(item, ConfigureSpanningTree)]
    by_name = {item.device_name: item for item in actions}
    assert len(actions) == 15
    assert by_name["Switch8"].root_primary_vlans == [10, 20, 30]
    assert by_name["Switch8"].priorities == {10: 24576, 20: 24576, 30: 24576}
    assert by_name["Switch10"].root_secondary_vlans == [10, 20, 30]
    assert by_name["Switch10"].priorities == {10: 28672, 20: 28672, 30: 28672}
    assert by_name["MLS3"].root_primary_vlans == [10, 20, 30]
    assert by_name["MLS7"].root_secondary_vlans == [10, 20, 30]
    assert by_name["Switch3"].root_primary_vlans == [10, 20, 30]


def test_ripv2_uses_only_canonical_routers_and_exact_connected_foundations():
    intent, _, _, plan = _control_plane()
    actions = [item for item in plan.actions if isinstance(item, ConfigureRipv2)]
    by_name = {item.device_name: item for item in actions}

    assert set(by_name) == {"Router0", "Router3", "Router4"}
    assert {
        name: [item.network for item in action.networks]
        for name, action in by_name.items()
    } == {
        "Router0": ["10.0.0.0", "172.18.0.0"],
        "Router3": ["10.0.0.0", "172.17.0.0"],
        "Router4": ["10.0.0.0", "172.16.0.0"],
    }
    assert all(
        sum(
            len(network.source_configuration_action_ids)
            for network in action.networks
        ) == 5
        for action in actions
    )
    assert intent.routing is not None
    assert len(intent.routing.transit_link_ids) == 3
    assert all(
        action.passive_interfaces == [
            "FastEthernet0/0.10",
            "FastEthernet0/0.20",
            "FastEthernet0/0.30",
        ]
        for action in actions
    )


def test_portfast_and_bpdu_guard_are_endpoint_only_and_fully_covered():
    _, topology, _, plan = _control_plane()
    edge_actions = [
        item for item in plan.actions if isinstance(item, ConfigureStpEdgePort)
    ]
    infrastructure_ports = {
        (device_id, port)
        for link in topology.links
        if link.link_role not in {
            "endpoint_access", "server_access", "phone_passthrough",
        }
        for device_id, port in (
            (link.device_a_id, link.port_a),
            (link.device_b_id, link.port_b),
        )
    }

    assert len(edge_actions) == 199
    assert all(item.portfast and item.bpduguard for item in edge_actions)
    assert not {
        (item.device_id, item.interface) for item in edge_actions
    } & infrastructure_ports


def test_every_stp_expectation_claims_numeric_primary_secondary_policy():
    _, _, _, plan = _control_plane()
    expectations = [
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.STP_STATE
    ]

    assert len(expectations) == 15
    assert all("root_secondary_vlans" in item.expected for item in expectations)
    assert all("priorities" in item.expected for item in expectations)
