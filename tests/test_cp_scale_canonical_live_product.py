"""Product-owned canonical CP-SCALE composition and routing-core projection."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    canonical_stage_configuration_mutation_ids,
    canonical_stage_control_plane_mutation_ids,
    canonical_stage_voice_mutation_ids,
    project_cp_scale_canonical_stage,
    project_cp_scale_canonical_delta,
    project_cp_scale_routing_core,
)
from tests.poe_delivery_capabilities import (
    compose_delivery_qualified_cp_scale_canonical as compose_cp_scale_canonical,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    EvidenceSource,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureRipv2,
    ControlPlaneVerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import (
    BindPhoneToExtension,
    CreateExtension,
    GeneratePhoneConfigurationFiles,
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
    # 445, not 609. Two classes of endpoint are no longer addressed here and
    # both for the same reason -- E5 cannot name an interface that will hold
    # the address:
    #
    #   -95  the wireless IoT endpoints expose no network port at all;
    #   -69  a 7960 on a voice VLAN brings up the SVI it acquires on only after
    #        the VLAN is signalled, and takes `Vlan1` down doing it.
    #
    # Every VLAN, access port, gateway and DHCP pool that serves them still
    # exists. What stopped is the pretence, and for the phones the claim moved
    # to E7, which owns option 150 and the call control that make it true.
    assert len(composition.configuration.actions) == 445
    assert len(composition.control_plane.actions) == 217


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
        CPScaleCanonicalStage.FLOOR3: (232, 160),
        CPScaleCanonicalStage.ROUTER0_BRANCH: (290, 202),
        CPScaleCanonicalStage.ROUTER3_BRANCH: (314, 219),
        CPScaleCanonicalStage.REMAINING: (314, 219),
    }
    expected_workloads_and_aps = {
        CPScaleCanonicalStage.ROUTING_CORE: (0, 0),
        CPScaleCanonicalStage.ROUTER4_SWITCH10: (0, 0),
        CPScaleCanonicalStage.FLOOR1: (65, 3),
        CPScaleCanonicalStage.FLOOR2: (118, 6),
        CPScaleCanonicalStage.FLOOR3: (208, 12),
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
            "distribution_uplink": 2, "access_uplink": 2, "endpoint_access": 60,
        }),
        CPScaleCanonicalStage.ROUTER0_BRANCH: Counter({
            "edge_link": 1,
            "distribution_uplink": 4,
            "endpoint_access": 35,
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
        CPScaleCanonicalStage.FLOOR3: (101, 64),
        CPScaleCanonicalStage.ROUTER0_BRANCH: (59, 42),
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


def test_floor2_configuration_mutation_is_delta_while_verification_stays_cumulative():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )
    floor1 = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.FLOOR1,
    )
    floor2 = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.FLOOR2,
    )

    mutation_ids = set(canonical_stage_configuration_mutation_ids(
        floor1.configuration,
        floor2.configuration,
    ))
    floor1_ids = {item.id for item in floor1.configuration.actions}
    floor2_ids = {item.id for item in floor2.configuration.actions}

    assert len(floor1_ids) == 115
    assert len(floor2_ids) == 191
    assert len(mutation_ids) == 76
    assert mutation_ids == floor2_ids - floor1_ids
    assert not mutation_ids & floor1_ids
    assert {
        (item.device_name, item.interface)
        for item in floor2.configuration.actions
        if item.id in mutation_ids
        and item.action_type is ConfigurationActionType.CONFIGURE_TRUNK
    } == {
        ("Switch10", "FastEthernet0/2"),
        ("Switch6", "GigabitEthernet0/1"),
        ("Switch6", "GigabitEthernet0/2"),
        ("Switch7", "GigabitEthernet0/1"),
    }
    assert {
        item.id for item in floor2.configuration.verification_expectations
    } > {
        item.id for item in floor1.configuration.verification_expectations
    }


def test_every_control_plane_stage_mutates_only_new_actions():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )
    expected = {
        CPScaleCanonicalStage.ROUTER4_SWITCH10: (3, 0, 3),
        CPScaleCanonicalStage.FLOOR1: (3, 0, 3),
        CPScaleCanonicalStage.FLOOR2: (3, 0, 3),
        CPScaleCanonicalStage.FLOOR3: (160, 157, 3),
        CPScaleCanonicalStage.ROUTER0_BRANCH: (200, 40, 160),
        CPScaleCanonicalStage.ROUTER3_BRANCH: (217, 17, 200),
    }
    previous = project_cp_scale_canonical_stage(
        composition,
        CPScaleCanonicalStage.ROUTING_CORE,
    ).control_plane
    for stage, counts in expected.items():
        current = project_cp_scale_canonical_stage(
            composition,
            stage,
        ).control_plane
        mutation_ids = canonical_stage_control_plane_mutation_ids(
            previous,
            current,
        )
        assert (
            len(current.actions),
            len(mutation_ids),
            len(current.actions) - len(mutation_ids),
        ) == counts
        previous = current

    assert canonical_stage_control_plane_mutation_ids(
        previous,
        composition.control_plane,
    ) == ()


def test_canonical_live_runner_uses_delta_mutation_with_cumulative_plan():
    source = Path("tools/cp_scale_canonical_live.py").read_text(
        encoding="utf-8",
    )

    assert "canonical_stage_configuration_mutation_ids(" in source
    assert "mutation_action_ids=configuration_mutation_ids" in source
    assert "retained_action_results=(" in source
    assert "previous_configuration.action_results" in source
    assert "previous_configuration = configuration" in source
    assert "canonical_stage_control_plane_mutation_ids(" in source
    assert "mutation_action_ids=control_plane_mutation_ids" in source
    assert "retained_action_results=retained_control_plane_action_results" in source
    assert "previous_control_plane_action_results = tuple(" in source


def test_floor2_voice_mutation_is_delta_with_phone_files_regenerated():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )
    floor1 = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.FLOOR1,
    )
    floor2 = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.FLOOR2,
    )
    assert floor1.voice is not None
    assert floor2.voice is not None

    mutation_ids = set(canonical_stage_voice_mutation_ids(
        floor1.voice,
        floor2.voice,
    ))
    actions = {
        item.id: item for item in floor2.voice.actions
        if item.id in mutation_ids
    }

    assert len(floor1.voice.actions) == 47
    assert len(floor2.voice.actions) == 75
    assert len(mutation_ids) == 29
    assert Counter(type(item) for item in actions.values()) == {
        CreateExtension: 14,
        BindPhoneToExtension: 14,
        GeneratePhoneConfigurationFiles: 1,
    }
    phone_files = next(
        item for item in floor2.voice.actions
        if isinstance(item, GeneratePhoneConfigurationFiles)
    )
    assert phone_files.id in mutation_ids


def test_every_later_voice_stage_has_an_exact_bounded_mutation_delta():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )
    expected = {
        CPScaleCanonicalStage.FLOOR2: (75, 29, 46),
        CPScaleCanonicalStage.FLOOR3: (89, 15, 74),
        CPScaleCanonicalStage.ROUTER0_BRANCH: (134, 45, 89),
        CPScaleCanonicalStage.ROUTER3_BRANCH: (153, 19, 134),
    }
    previous = project_cp_scale_canonical_stage(
        composition,
        CPScaleCanonicalStage.FLOOR1,
    ).voice
    assert previous is not None
    for stage, counts in expected.items():
        current = project_cp_scale_canonical_stage(
            composition,
            stage,
        ).voice
        assert current is not None
        mutation_ids = canonical_stage_voice_mutation_ids(
            previous,
            current,
        )
        assert (
            len(current.actions),
            len(mutation_ids),
            len(current.actions) - len(mutation_ids),
        ) == counts
        previous = current

    assert composition.voice is not None
    assert canonical_stage_voice_mutation_ids(
        previous,
        composition.voice,
    ) == ()


def test_voice_delta_rejects_changed_stable_action_outside_phone_files():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )
    floor1 = project_cp_scale_canonical_stage(
        composition,
        CPScaleCanonicalStage.FLOOR1,
    ).voice
    floor2 = project_cp_scale_canonical_stage(
        composition,
        CPScaleCanonicalStage.FLOOR2,
    ).voice
    assert floor1 is not None
    assert floor2 is not None
    changed = floor2.model_copy(deep=True)
    changed.actions[0] = changed.actions[0].model_copy(update={
        "max_phones": changed.actions[0].max_phones + 1,
    })

    with pytest.raises(
        ValueError,
        match="changed outside a monotonic phone-file dependency expansion",
    ):
        canonical_stage_voice_mutation_ids(floor1, changed)


def test_canonical_live_runner_uses_voice_delta_and_retained_results():
    source = Path("tools/cp_scale_canonical_live.py").read_text(
        encoding="utf-8",
    )

    assert "canonical_stage_voice_mutation_ids(" in source
    assert "mutation_action_ids=voice_mutation_ids" in source
    assert "retained_voice_action_results=retained_voice_action_results" in source
    assert "retained_action_results=retained_voice_action_results" in source
    assert "previous_voice_action_results = tuple(" in source
    assert "previous_projection=previous_projection" in source
    assert "retained_state_only=not voice_mutation_ids" in source


def test_canonical_live_retains_network_state_at_each_causal_boundary():
    source = Path("tools/cp_scale_canonical_live.py").read_text(
        encoding="utf-8",
    )

    for boundary in (
        "before_physical_delta",
        "after_physical_delta",
        "after_l2_definitions",
        "after_l2_interfaces",
    ):
        assert boundary in source
    assert "phase_observer=configuration_phase_observer" in source
    assert "trunk_transition_observer=" in source
    assert "parse_show_interfaces_trunk" in source
    assert "parse_show_spanning_tree" in source
    assert '"runtime_diagnostics"' in source
    assert "drain_diagnostic_evidence" in source
