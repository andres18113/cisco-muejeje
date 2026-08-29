"""Product-owned canonical CP-SCALE composition and routing-core projection."""

from __future__ import annotations

from collections import Counter

from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    compose_cp_scale_canonical,
    project_cp_scale_canonical_stage,
    project_cp_scale_canonical_delta,
    project_cp_scale_routing_core,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
    EndpointDhcpVerificationMode,
    SetEndpointDhcp,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    EvidenceSource,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureRipv2,
    ControlPlaneVerificationKind,
)
from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
)


def test_product_composes_the_exact_canonical_topology_and_plans():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )

    assert composition.valid, composition.issues
    assert composition.topology is not None
    assert composition.configuration is not None
    assert composition.control_plane is not None
    assert len(composition.topology.devices) == 314
    assert len(composition.topology.links) == 219
    # 514, not the former 445. Wireless endpoints still expose no interface,
    # while each of the 69 phones now retains one activation-only DHCP action:
    #
    #   -95  the wireless IoT endpoints expose no network port at all;
    #   +69  Vlan1 lets the measured helper trigger device.setDhcpFlag before
    #        E7; Vlan<voice> independently verifies only the client state.
    #
    # Every VLAN, access port, gateway and DHCP pool that serves them still
    # exists. E7 continues to own the eventual address/registration claim.
    assert len(composition.configuration.actions) == 514
    assert len(composition.control_plane.actions) == 217

    activations = [
        item for item in composition.configuration.actions
        if isinstance(item, SetEndpointDhcp)
        and item.verification_mode is EndpointDhcpVerificationMode.CLIENT_ENABLED
    ]
    assert len(activations) == 69
    assert {item.interface for item in activations} == {"Vlan1"}
    assert {
        item.verification_interface for item in activations
    } == {"Vlan20"}
    assert len([
        item for item in composition.voice.foundational_requirements
        if item.kind == "phone_dhcp_activation"
    ]) == 69


def test_canonical_composition_uses_exact_build_2811_layer3_live_evidence():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )

    capability = composition.capabilities["2811"]
    assert capability.layer3 is CapabilityStatus.SUPPORTED
    assert any(
        item.capability == "layer3"
        and item.source is EvidenceSource.STATIC_OVERRIDE
        and item.verified
        and item.packet_tracer_version == MEASURED_BACKEND_VERSION
        for item in capability.evidence
    )


def test_product_projects_only_the_canonical_routing_core():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )
    core = project_cp_scale_routing_core(composition)

    assert {item.name for item in core.topology.devices} == {
        "Router0", "Router3", "Router4",
    }
    assert len(core.topology.modules) == 3
    assert len(core.topology.links) == 3
    assert {item.cable for item in core.topology.links} == {"serial"}

    assert {
        item.action_type for item in core.configuration.actions
    } == {
        ConfigurationActionType.CONFIGURE_HOSTNAME,
        ConfigurationActionType.CONFIGURE_ROUTED_INTERFACE,
        ConfigurationActionType.CONFIGURE_SUBINTERFACE,
    }
    assert len([
        item for item in core.control_plane.actions
        if isinstance(item, ConfigureRipv2)
    ]) == 3

    process = [
        item for item in core.control_plane.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTING_PROCESS
    ]
    routes = [
        item for item in core.control_plane.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTE_PRESENT
    ]
    assert len(process) == 3
    assert [item.kind for item in core.control_plane.verification_expectations] == [
        *([ControlPlaneVerificationKind.ROUTING_PROCESS] * 3),
        *([ControlPlaneVerificationKind.ROUTE_PRESENT] * 3),
    ]
    assert {
        (str(item.expected["network"]), int(item.expected["prefix_length"]))
        for item in routes
    } == {
        ("10.0.0.0", 30),
        ("10.0.0.4", 30),
        ("10.0.0.8", 30),
    }
    assert len(routes) == 3
    assert core.forwarding_checks == {
        "Router4": "10.0.0.10",
        "Router0": "10.0.0.6",
        "Router3": "10.0.0.1",
    }


def test_canonical_live_stages_are_exact_monotonic_physical_closures():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )
    expected_counts = {
        CPScaleCanonicalStage.ROUTING_CORE: (3, 3),
        CPScaleCanonicalStage.ROUTER4_SWITCH10: (4, 4),
        CPScaleCanonicalStage.FLOOR1: (74, 55),
        CPScaleCanonicalStage.FLOOR2: (132, 96),
        CPScaleCanonicalStage.FLOOR3: (241, 169),
        CPScaleCanonicalStage.ROUTER0_BRANCH: (290, 202),
        CPScaleCanonicalStage.ROUTER3_BRANCH: (314, 219),
        CPScaleCanonicalStage.REMAINING: (314, 219),
    }
    expected_workloads_and_aps = {
        CPScaleCanonicalStage.ROUTING_CORE: (0, 0),
        CPScaleCanonicalStage.ROUTER4_SWITCH10: (0, 0),
        CPScaleCanonicalStage.FLOOR1: (65, 3),
        CPScaleCanonicalStage.FLOOR2: (118, 6),
        CPScaleCanonicalStage.FLOOR3: (217, 12),
        CPScaleCanonicalStage.ROUTER0_BRANCH: (258, 15),
        CPScaleCanonicalStage.ROUTER3_BRANCH: (279, 17),
        CPScaleCanonicalStage.REMAINING: (279, 17),
    }

    expected_new_network_devices = {
        CPScaleCanonicalStage.ROUTING_CORE: {"Router0", "Router3", "Router4"},
        CPScaleCanonicalStage.ROUTER4_SWITCH10: {"Switch10"},
        CPScaleCanonicalStage.FLOOR1: {"Switch4", "Switch5"},
        CPScaleCanonicalStage.FLOOR2: {"Switch6", "Switch7"},
        CPScaleCanonicalStage.FLOOR3: {"Switch0", "Switch1", "Switch8", "Switch9"},
        CPScaleCanonicalStage.ROUTER0_BRANCH: {
            "MLS3", "MLS4", "MLS5", "MLS6", "MLS7",
        },
        CPScaleCanonicalStage.ROUTER3_BRANCH: {"Switch3"},
        CPScaleCanonicalStage.REMAINING: set(),
    }
    expected_link_deltas = {
        CPScaleCanonicalStage.ROUTING_CORE: Counter({"wan_link": 3}),
        CPScaleCanonicalStage.ROUTER4_SWITCH10: Counter({"edge_link": 1}),
        CPScaleCanonicalStage.FLOOR1: Counter({
            "distribution_uplink": 1, "access_uplink": 1, "endpoint_access": 49,
        }),
        CPScaleCanonicalStage.FLOOR2: Counter({
            "distribution_uplink": 1, "access_uplink": 1, "endpoint_access": 39,
        }),
        CPScaleCanonicalStage.FLOOR3: Counter({
            "distribution_uplink": 2, "access_uplink": 2, "endpoint_access": 69,
        }),
        CPScaleCanonicalStage.ROUTER0_BRANCH: Counter({
            "edge_link": 1,
            "distribution_uplink": 4,
            "endpoint_access": 26,
            "phone_passthrough": 2,
        }),
        CPScaleCanonicalStage.ROUTER3_BRANCH: Counter({
            "edge_link": 1, "endpoint_access": 16,
        }),
        CPScaleCanonicalStage.REMAINING: Counter(),
    }

    previous_devices: set[str] = set()
    previous_links: set[str] = set()
    previous_network_names: set[str] = set()
    projections = {}
    for stage, (device_count, link_count) in expected_counts.items():
        projected = project_cp_scale_canonical_stage(composition, stage)
        projections[stage] = projected
        device_ids = {item.id for item in projected.topology.devices}
        link_ids = {item.id for item in projected.topology.links}
        network_names = {
            item.name for item in projected.topology.devices
            if item.category in {"router", "switch"}
        }

        assert len(device_ids) == device_count
        assert len(link_ids) == link_count
        access_points = sum(
            item.model == "AccessPoint-PT" for item in projected.topology.devices
        )
        workloads = sum(
            item.category not in {"router", "switch", "accesspoint"}
            for item in projected.topology.devices
        )
        assert (workloads, access_points) == expected_workloads_and_aps[stage]
        assert len(projected.topology.modules) == 3
        assert previous_devices <= device_ids
        assert previous_links <= link_ids
        assert network_names - previous_network_names == expected_new_network_devices[stage]
        assert Counter(
            item.link_role
            for item in projected.topology.links
            if item.id not in previous_links
        ) == expected_link_deltas[stage]
        assert all(
            item.device_a_id in device_ids and item.device_b_id in device_ids
            for item in projected.topology.links
        )
        previous_devices = device_ids
        previous_links = link_ids
        previous_network_names = network_names

    assert previous_devices == {
        item.id for item in composition.topology.devices
    }
    assert previous_links == {
        item.id for item in composition.topology.links
    }
    governed_core = project_cp_scale_routing_core(composition)
    staged_core = projections[CPScaleCanonicalStage.ROUTING_CORE]
    assert staged_core.topology == governed_core.topology
    assert staged_core.configuration == governed_core.configuration
    assert staged_core.control_plane == governed_core.control_plane
    assert staged_core.forwarding_checks == governed_core.forwarding_checks
    assert (
        projections[CPScaleCanonicalStage.REMAINING].topology.physical_identity_hash
        == composition.topology.physical_identity_hash
        == projections[CPScaleCanonicalStage.ROUTER3_BRANCH].topology.physical_identity_hash
    )
    assert len(
        projections[CPScaleCanonicalStage.REMAINING]
        .control_plane.verification_expectations
    ) == 57
    final = projections[CPScaleCanonicalStage.REMAINING]
    assert {item.id for item in final.configuration.actions} == {
        item.id for item in composition.configuration.actions
    }
    assert {
        item.id for item in final.configuration.verification_expectations
    } == {
        item.id for item in composition.configuration.verification_expectations
    }
    assert {
        item.id for item in final.control_plane.actions
    } == {
        item.id for item in composition.control_plane.actions
    }
    assert {
        item.id for item in final.control_plane.verification_expectations
    } == {
        item.id for item in composition.control_plane.verification_expectations
    }
    assert Counter(
        item.kind for item in final.control_plane.verification_expectations
    ) == Counter({
        ControlPlaneVerificationKind.ROUTE_PRESENT: 21,
        ControlPlaneVerificationKind.END_TO_END_REACHABILITY: 18,
        ControlPlaneVerificationKind.STP_STATE: 15,
        ControlPlaneVerificationKind.ROUTING_PROCESS: 3,
    })


def test_router4_switch10_stage_contains_no_future_branch_configuration():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )
    projected = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTER4_SWITCH10,
    )

    assert {item.name for item in projected.topology.devices} == {
        "Router0", "Router3", "Router4", "Switch10",
    }
    edge_links = [
        item for item in projected.topology.links if item.cable != "serial"
    ]
    assert len(edge_links) == 1
    assert {
        (edge_links[0].device_a, edge_links[0].port_a),
        (edge_links[0].device_b, edge_links[0].port_b),
    } == {
        ("Router4", "FastEthernet0/0"),
        ("Switch10", "GigabitEthernet0/1"),
    }

    action_ids = {item.id for item in projected.configuration.actions}
    link_ids = {item.id for item in projected.topology.links}
    assert all(
        dependency in action_ids
        for item in projected.configuration.actions
        for dependency in item.depends_on
    )
    assert all(
        not getattr(item, "source_link_id", "")
        or item.source_link_id in link_ids
        for item in projected.configuration.actions
    )
    assert {
        item.interface
        for item in projected.configuration.actions
        if item.action_type is ConfigurationActionType.CONFIGURE_TRUNK
    } == {"GigabitEthernet0/1"}


def test_post_core_physical_stages_deploy_only_new_delta_without_core_modules():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )
    core = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTING_CORE,
    )
    router4_switch10 = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTER4_SWITCH10,
    )

    delta = project_cp_scale_canonical_delta(
        core.topology, router4_switch10.topology,
    )

    assert {item.name for item in delta.devices} == {"Router4", "Switch10"}
    assert delta.modules == []
    assert len(delta.links) == 1
    assert {
        (delta.links[0].device_a, delta.links[0].port_a),
        (delta.links[0].device_b, delta.links[0].port_b),
    } == {
        ("Router4", "FastEthernet0/0"),
        ("Switch10", "GigabitEthernet0/1"),
    }


def test_every_post_core_delta_is_exact_closed_and_module_free():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )
    stages = list(CPScaleCanonicalStage)
    expected = {
        CPScaleCanonicalStage.ROUTER4_SWITCH10: (2, 1),
        CPScaleCanonicalStage.FLOOR1: (71, 51),
        CPScaleCanonicalStage.FLOOR2: (59, 41),
        CPScaleCanonicalStage.FLOOR3: (110, 73),
        CPScaleCanonicalStage.ROUTER0_BRANCH: (50, 33),
        CPScaleCanonicalStage.ROUTER3_BRANCH: (25, 17),
        CPScaleCanonicalStage.REMAINING: (0, 0),
    }
    previous = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTING_CORE,
    ).topology
    for stage in stages[1:]:
        current = project_cp_scale_canonical_stage(composition, stage).topology
        delta = project_cp_scale_canonical_delta(previous, current)
        assert (len(delta.devices), len(delta.links)) == expected[stage]
        assert delta.modules == []
        delta_device_ids = {item.id for item in delta.devices}
        assert all(
            item.device_a_id in delta_device_ids
            and item.device_b_id in delta_device_ids
            for item in delta.links
        )
        previous = current
