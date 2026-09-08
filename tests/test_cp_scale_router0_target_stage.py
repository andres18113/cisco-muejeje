"""Behavioral contracts for the bounded Router0 canonical LIVE target."""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    CPScaleCanonicalTarget,
    CPScaleForwardingAuthority,
    canonical_cp_scale_target_contract,
    canonical_stage_transition_contract,
    derive_cp_scale_site_forwarding_checks,
    project_cp_scale_canonical_delta,
    project_cp_scale_canonical_stage,
)
from src.packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    CanonicalMutationSurfaceObservation,
    canonical_configuration_reread_scope,
    canonical_stage_mutation_replay_audit,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
    SetEndpointStaticAddress,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureRipv2,
    ConfigureSpanningTree,
    ConfigureStpEdgePort,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane_runtime import (
    ControlPlaneApplicationResult,
)
from src.packet_tracer_mcp.domain.enterprise.models.execution import (
    journal_from_action_results,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.models.voice_runtime import (
    VoiceApplicationResult,
)
from tests.poe_delivery_capabilities import (
    compose_delivery_qualified_cp_scale_canonical,
)


@pytest.fixture(scope="module")
def composition():
    composed = compose_delivery_qualified_cp_scale_canonical(
        packet_tracer_version="9.0.1.0858",
    )
    assert composed.valid
    return composed


def test_router0_target_stops_at_its_own_successful_cleanup_contract():
    contract = canonical_cp_scale_target_contract(
        CPScaleCanonicalTarget.ROUTER0_BRANCH,
    )

    assert contract.build_stages == (
        CPScaleCanonicalStage.ROUTING_CORE,
        CPScaleCanonicalStage.ROUTER4_SWITCH10,
        CPScaleCanonicalStage.FLOOR1,
        CPScaleCanonicalStage.FLOOR2,
        CPScaleCanonicalStage.FLOOR3,
        CPScaleCanonicalStage.ROUTER0_BRANCH,
    )
    assert contract.terminal_stage is CPScaleCanonicalStage.ROUTER0_BRANCH
    assert contract.run_remaining_reconciliation is False
    assert contract.run_full_qualification is False
    assert contract.allow_retention is False
    assert contract.precleanup_closure == "ROUTER0_BRANCH_VERIFIED_PRECLEANUP"
    assert contract.cleaned_closure == "ROUTER0_BRANCH_VERIFIED_AND_CLEANED"


def test_default_target_preserves_the_full_qualification_route():
    contract = canonical_cp_scale_target_contract(
        CPScaleCanonicalTarget.FULL_QUALIFICATION,
    )

    assert contract.build_stages == tuple(
        stage for stage in CPScaleCanonicalStage
        if stage is not CPScaleCanonicalStage.REMAINING
    )
    assert contract.terminal_stage is CPScaleCanonicalStage.ROUTER3_BRANCH
    assert contract.run_remaining_reconciliation is True
    assert contract.run_full_qualification is True
    assert contract.allow_retention is True
    assert contract.precleanup_closure == (
        "CP_SCALE_GOVERNED_VOICE_VERIFIED_PRECLEANUP"
    )
    assert contract.cleaned_closure == (
        "CP_SCALE_GOVERNED_VOICE_VERIFIED_AND_CLEANED"
    )


def test_floor3_to_router0_is_incremental_with_a_disjoint_scope(composition):
    floor3 = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.FLOOR3,
    )
    router0 = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
    )

    contract = canonical_stage_transition_contract(floor3, router0)
    delta = project_cp_scale_canonical_delta(
        floor3.topology, router0.topology,
    )

    assert contract.previous_stage is CPScaleCanonicalStage.FLOOR3
    assert contract.current_stage is CPScaleCanonicalStage.ROUTER0_BRANCH
    assert len(contract.new_device_ids) == 58
    assert contract.anchor_device_ids == ("r-edge-multilayer-branch-01",)
    assert len(contract.new_link_ids) == 42
    assert (len(router0.topology.devices), len(router0.topology.links)) == (290, 202)
    assert (len(delta.devices), len(delta.modules), len(delta.links)) == (59, 0, 42)
    assert len(contract.configuration_mutation_ids) == 84
    assert len(contract.configuration_retained_ids) == 328
    assert len(contract.control_plane_mutation_ids) == 40
    assert len(contract.control_plane_retained_ids) == 160
    assert len(contract.voice_mutation_ids) == 45
    assert len(contract.voice_retained_ids) == 89
    assert contract.replayed_configuration_ids == ()
    assert contract.replayed_control_plane_ids == ()
    assert contract.replayed_voice_ids == ()
    assert contract.mutation_scope_disjoint is True
    assert contract.claim == "MUTATION_SCOPE_DISJOINT"
    assert not hasattr(contract, "no_mutation_replay")

    new_devices = [
        item for item in router0.topology.devices
        if item.id in set(contract.new_device_ids)
    ]
    assert sum(
        item.enterprise_role == DeviceRole.IP_PHONE.value
        for item in new_devices
    ) == 20
    assert sum(
        item.enterprise_role == DeviceRole.ACCESS_POINT.value
        for item in new_devices
    ) == 3
    assert not any(
        item.requires_poe
        for item in new_devices
        if item.enterprise_role == DeviceRole.ACCESS_POINT.value
    )
    assert {
        item.name for item in new_devices
        if item.enterprise_role in {
            DeviceRole.ACCESS_SWITCH.value,
            DeviceRole.DISTRIBUTION_SWITCH.value,
        }
    } == {"MLS3", "MLS4", "MLS5", "MLS6", "MLS7"}

    control_delta = [
        item for item in router0.control_plane.actions
        if item.id in set(contract.control_plane_mutation_ids)
    ]
    assert sum(isinstance(item, ConfigureSpanningTree) for item in control_delta) == 5
    assert sum(isinstance(item, ConfigureStpEdgePort) for item in control_delta) == 35
    assert not any(isinstance(item, ConfigureRipv2) for item in control_delta)
    assert len([
        item for item in router0.control_plane.actions
        if isinstance(item, ConfigureRipv2)
    ]) == 3
    stp_by_name = {
        next(
            device.name for device in router0.topology.devices
            if device.id == action.device_id
        ): action
        for action in control_delta
        if isinstance(action, ConfigureSpanningTree)
    }
    assert stp_by_name["MLS3"].root_primary_vlans == [10, 20, 30]
    assert stp_by_name["MLS7"].root_secondary_vlans == [10, 20, 30]

    floor3_phones = {item.phone_id for item in floor3.voice.phone_assignments}
    router0_phones = {item.phone_id for item in router0.voice.phone_assignments}
    floor3_extensions = {
        item.extension for item in floor3.voice.phone_assignments
    }
    router0_extensions = {
        item.extension for item in router0.voice.phone_assignments
    }
    assert len(router0_phones - floor3_phones) == 20
    assert len(router0_phones) == 62
    assert len(router0_extensions - floor3_extensions) == 20
    assert router0.voice.source_topology_hash == (
        router0.topology.physical_identity_hash
    )
    assert router0.voice.source_configuration_hash == (
        router0.configuration.semantic_hash
    )


def test_large_multilayer_forwarding_is_derived_from_e4_and_e5(composition):
    projection = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
    )

    checks = derive_cp_scale_site_forwarding_checks(
        composition,
        projection,
        source_site_id="large-branch",
        destination_site_id="multilayer-branch",
    )

    assert checks == projection.branch_forwarding_checks
    assert len(checks) == 2
    assert {
        (item.source_site_id, item.destination_site_id)
        for item in checks
    } == {
        ("large-branch", "multilayer-branch"),
        ("multilayer-branch", "large-branch"),
    }
    assert {item.source_device_name for item in checks} == {"Router4", "Router0"}
    assert all(
        item.source_topology_hash == projection.topology.physical_identity_hash
        and item.source_configuration_hash == projection.configuration.semantic_hash
        for item in checks
    )

    destinations = {
        action.id: action
        for action in projection.configuration.actions
        if isinstance(action, SetEndpointStaticAddress)
    }
    assert all(
        item.destination_ipv4 == destinations[item.destination_action_id].ipv4
        and item.destination_segment_id
        == destinations[item.destination_action_id].segment_id
        and item.destination_device_id
        == destinations[item.destination_action_id].device_id
        for item in checks
    )
    assert {
        (item.direction, item.destination_ipv4) for item in checks
    } == {
        ("large-branch-to-multilayer-branch", "172.18.30.2"),
        ("multilayer-branch-to-large-branch", "172.16.30.2"),
    }


def test_only_the_declared_direction_is_attributed_to_the_e4_flow(composition):
    declared = [
        item for item in composition.enterprise.traffic_flows
        if {item.source_site_id, item.destination_site_id}
        == {"large-branch", "multilayer-branch"}
    ]
    assert [item.id for item in declared] == ["flow/large-to-multilayer"]
    assert declared[0].source_site_id == "large-branch"

    projection = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
    )
    by_direction = {
        item.direction: item for item in projection.branch_forwarding_checks
    }

    forward = by_direction["large-branch-to-multilayer-branch"]
    assert forward.authority is (
        CPScaleForwardingAuthority.DECLARED_TRAFFIC_FLOW
    )
    assert forward.declared_traffic_flow_id == "flow/large-to-multilayer"
    assert forward.reverse_of_traffic_flow_id == ""
    assert forward.id == (
        "forwarding/declared-traffic-flow/flow/large-to-multilayer/"
        f"large-branch-to-multilayer-branch/{forward.destination_action_id}"
    )

    reverse = by_direction["multilayer-branch-to-large-branch"]
    assert reverse.authority is (
        CPScaleForwardingAuthority.REVERSE_PATH_OF_DECLARED_FLOW
    )
    assert reverse.declared_traffic_flow_id == ""
    assert reverse.reverse_of_traffic_flow_id == "flow/large-to-multilayer"
    assert reverse.id == (
        "forwarding/reverse-path-of-declared-flow/flow/large-to-multilayer/"
        f"multilayer-branch-to-large-branch/{reverse.destination_action_id}"
    )
    assert not any(
        item.declared_traffic_flow_id == "flow/large-to-multilayer"
        for item in projection.branch_forwarding_checks
        if item.source_site_id == "multilayer-branch"
    )
    assert not hasattr(reverse, "traffic_flow_id")


def test_a_declared_reverse_flow_claims_its_own_direction(composition):
    enterprise = composition.enterprise.model_copy(deep=True)
    forward = next(
        item for item in enterprise.traffic_flows
        if item.id == "flow/large-to-multilayer"
    )
    reverse_flow = forward.model_copy(deep=True)
    reverse_flow.id = "flow/multilayer-to-large"
    reverse_flow.source_site_id = "multilayer-branch"
    reverse_flow.destination_site_id = "large-branch"
    reverse_flow.explicit_link_ids = []
    enterprise.traffic_flows = [*enterprise.traffic_flows, reverse_flow]
    projection = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
    )

    checks = derive_cp_scale_site_forwarding_checks(
        replace(composition, enterprise=enterprise),
        projection,
        source_site_id="large-branch",
        destination_site_id="multilayer-branch",
    )

    by_direction = {item.direction: item for item in checks}
    assert all(
        item.authority is CPScaleForwardingAuthority.DECLARED_TRAFFIC_FLOW
        for item in checks
    )
    assert by_direction[
        "multilayer-branch-to-large-branch"
    ].declared_traffic_flow_id == "flow/multilayer-to-large"
    assert by_direction[
        "large-branch-to-multilayer-branch"
    ].declared_traffic_flow_id == "flow/large-to-multilayer"
    assert all(
        item.reverse_of_traffic_flow_id == "" for item in checks
    )


def test_forwarding_fails_closed_on_ambiguous_reverse_declarations(composition):
    enterprise = composition.enterprise.model_copy(deep=True)
    forward = next(
        item for item in enterprise.traffic_flows
        if item.id == "flow/large-to-multilayer"
    )
    duplicates = []
    for suffix in ("a", "b"):
        item = forward.model_copy(deep=True)
        item.id = f"flow/multilayer-to-large-{suffix}"
        item.source_site_id = "multilayer-branch"
        item.destination_site_id = "large-branch"
        item.explicit_link_ids = []
        duplicates.append(item)
    enterprise.traffic_flows = [*enterprise.traffic_flows, *duplicates]
    projection = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
    )

    with pytest.raises(ValueError, match="cannot attribute a direction"):
        derive_cp_scale_site_forwarding_checks(
            replace(composition, enterprise=enterprise),
            projection,
            source_site_id="large-branch",
            destination_site_id="multilayer-branch",
        )


def test_forwarding_destination_changes_when_the_typed_e5_gateway_changes(
    composition,
):
    configuration = composition.configuration.model_copy(deep=True)
    multilayer = sorted(
        (
            action for action in configuration.actions
            if isinstance(action, SetEndpointStaticAddress)
            and action.site_id == "multilayer-branch"
        ),
        key=lambda item: (item.device_id, item.id),
    )
    first_ipv4, second_ipv4 = multilayer[0].ipv4, multilayer[1].ipv4
    multilayer[0].ipv4, multilayer[1].ipv4 = second_ipv4, first_ipv4
    changed_composition = replace(composition, configuration=configuration)
    changed_projection = project_cp_scale_canonical_stage(
        changed_composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
    )

    derived = next(
        item for item in changed_projection.branch_forwarding_checks
        if item.direction == "large-branch-to-multilayer-branch"
    )
    assert derived.destination_action_id == multilayer[0].id
    assert derived.destination_ipv4 == second_ipv4
    assert derived.destination_ipv4 != first_ipv4
    assert (
        derived.source_configuration_hash
        == changed_projection.configuration.semantic_hash
    )


def test_site_forwarding_fails_closed_without_its_e4_flow(composition):
    projection = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
    )
    enterprise = composition.enterprise.model_copy(deep=True)
    enterprise.traffic_flows = [
        item for item in enterprise.traffic_flows
        if item.id != "flow/large-to-multilayer"
    ]
    changed_composition = replace(composition, enterprise=enterprise)

    with pytest.raises(ValueError, match="traffic flow"):
        derive_cp_scale_site_forwarding_checks(
            changed_composition,
            projection,
            source_site_id="large-branch",
            destination_site_id="multilayer-branch",
        )


def test_site_forwarding_fails_closed_without_a_static_destination(composition):
    configuration = composition.configuration.model_copy(deep=True)
    configuration.actions = [
        item for item in configuration.actions
        if not (
            isinstance(item, SetEndpointStaticAddress)
            and item.site_id == "multilayer-branch"
        )
    ]
    changed_composition = replace(composition, configuration=configuration)

    with pytest.raises(ValueError, match="representative static"):
        project_cp_scale_canonical_stage(
            changed_composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
        )


def test_site_forwarding_fails_closed_when_destination_is_not_linked(composition):
    topology = composition.topology.model_copy(deep=True)
    representative_id = min(
        (
            item.device_id for item in composition.configuration.actions
            if isinstance(item, SetEndpointStaticAddress)
            and item.site_id == "multilayer-branch"
        ),
    )
    topology.links = [
        item for item in topology.links
        if representative_id not in {item.device_a_id, item.device_b_id}
    ]
    changed_composition = replace(composition, topology=topology)

    with pytest.raises(ValueError, match="present and linked"):
        project_cp_scale_canonical_stage(
            changed_composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
        )


@pytest.mark.parametrize(
    ("boundary", "message"),
    [
        ("e4", "E4 physical provenance"),
        ("e5-source", "does not match"),
        ("e5-semantic", "E5 semantic provenance"),
        ("e9", "control-plane provenance"),
    ],
)
def test_site_forwarding_rejects_stale_plan_provenance(
    composition,
    boundary,
    message,
):
    projection = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
    )
    if boundary == "e4":
        topology = projection.topology.model_copy(deep=True)
        topology.physical_topology_hash = "stale-topology"
        changed_projection = replace(projection, topology=topology)
    elif boundary == "e9":
        control_plane = projection.control_plane.model_copy(deep=True)
        control_plane.source_configuration_hash = "stale-configuration"
        changed_projection = replace(
            projection, control_plane=control_plane,
        )
    else:
        configuration = projection.configuration.model_copy(deep=True)
        if boundary == "e5-source":
            configuration.source_topology_hash = "stale-topology"
        else:
            configuration.semantic_hash = "stale-configuration"
        changed_projection = replace(
            projection, configuration=configuration,
        )

    with pytest.raises(ValueError, match=message):
        derive_cp_scale_site_forwarding_checks(
            composition,
            changed_projection,
            source_site_id="large-branch",
            destination_site_id="multilayer-branch",
        )


def test_transition_rejects_changed_or_duplicate_retained_actions(composition):
    floor3 = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.FLOOR3,
    )
    router0 = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
    )
    retained_id = floor3.configuration.actions[0].id

    changed_configuration = router0.configuration.model_copy(deep=True)
    changed_action = next(
        item for item in changed_configuration.actions
        if item.id == retained_id
    )
    changed_action.device_name += "-changed"
    with pytest.raises(ValueError, match="changed identity"):
        canonical_stage_transition_contract(
            floor3,
            replace(router0, configuration=changed_configuration),
        )

    duplicate_configuration = router0.configuration.model_copy(deep=True)
    duplicate_configuration.actions[-1].id = retained_id
    with pytest.raises(ValueError, match="duplicate action IDs"):
        canonical_stage_transition_contract(
            floor3,
            replace(router0, configuration=duplicate_configuration),
        )


def test_configuration_reread_scope_retains_every_action_and_mutates_none(
    composition,
):
    projection = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
    )
    results = [
        ActionApplicationResult(
            action_id=action.id,
            status=ActionExecutionStatus.APPLIED,
        )
        for action in projection.configuration.actions
    ]

    application = ConfigurationApplicationResult(
        config_plan_id=projection.configuration.id,
        config_semantic_hash=projection.configuration.semantic_hash,
        source_topology_hash=projection.configuration.source_topology_hash,
        status=ConfigurationApplicationStatus.PARTIAL,
        action_results=results,
    )

    mutation_ids, retained = canonical_configuration_reread_scope(
        projection.configuration, application,
    )

    assert mutation_ids == ()
    assert tuple(item.action_id for item in retained) == tuple(
        action.id for action in projection.configuration.actions
    )


@pytest.mark.parametrize("failure", ["missing", "duplicate", "not-applied"])
def test_configuration_reread_scope_fails_closed_on_unretained_state(
    composition,
    failure,
):
    projection = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
    )
    results = [
        ActionApplicationResult(
            action_id=action.id,
            status=ActionExecutionStatus.APPLIED,
        )
        for action in projection.configuration.actions
    ]
    if failure == "missing":
        results.pop()
    elif failure == "duplicate":
        results.append(results[-1].model_copy(deep=True))
    else:
        results[0].status = ActionExecutionStatus.FAILED

    with pytest.raises(ValueError, match="re-read"):
        application = ConfigurationApplicationResult(
            config_plan_id=projection.configuration.id,
            config_semantic_hash=projection.configuration.semantic_hash,
            source_topology_hash=projection.configuration.source_topology_hash,
            status=ConfigurationApplicationStatus.PARTIAL,
            action_results=results,
        )
        canonical_configuration_reread_scope(
            projection.configuration, application,
        )


def _journaled_result(model, plan, applied_ids, **fields):
    """A typed application result with the journal its applicator would write."""
    results = [
        ActionApplicationResult(
            action_id=identifier,
            status=ActionExecutionStatus.APPLIED,
            batch_id="batch/1",
        )
        for identifier in applied_ids
    ]
    return model(
        action_results=results,
        mutation_action_ids=list(applied_ids),
        execution_journal=journal_from_action_results(
            plan_id=plan.id,
            deployment_id="deployment/1",
            actions=list(plan.actions),
            results=results,
        ),
        **fields,
    )


def _configuration_attempt(plan, applied_ids):
    return _journaled_result(
        ConfigurationApplicationResult,
        plan,
        applied_ids,
        config_plan_id=plan.id,
        config_semantic_hash=plan.semantic_hash,
        source_topology_hash=plan.source_topology_hash,
        status=ConfigurationApplicationStatus.VERIFIED,
    )


def _control_plane_attempt(plan, applied_ids):
    return _journaled_result(
        ControlPlaneApplicationResult,
        plan,
        applied_ids,
        control_plane_plan_id=plan.id,
        control_plane_semantic_hash=plan.semantic_hash,
        source_topology_hash=plan.source_topology_hash,
        source_configuration_hash=plan.source_configuration_hash,
        status=ConfigurationApplicationStatus.VERIFIED,
    )


def _voice_attempt(plan, applied_ids):
    return _journaled_result(
        VoiceApplicationResult,
        plan,
        applied_ids,
        voice_plan_id=plan.id,
        voice_semantic_hash=plan.semantic_hash,
        source_topology_hash=plan.source_topology_hash,
        source_configuration_hash=plan.source_configuration_hash,
        status=ActionExecutionStatus.VERIFIED,
    )


@pytest.fixture(scope="module")
def router0_delta(composition):
    floor3 = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.FLOOR3,
    )
    router0 = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
    )
    return floor3, router0, canonical_stage_transition_contract(floor3, router0)


def _observations(projection, transition, *, configuration, control, voice):
    return (
        CanonicalMutationSurfaceObservation(
            surface="configuration",
            plan_action_ids=tuple(
                item.id for item in projection.configuration.actions
            ),
            authorized_mutation_ids=transition.configuration_mutation_ids,
            results=configuration,
        ),
        CanonicalMutationSurfaceObservation(
            surface="control-plane",
            plan_action_ids=tuple(
                item.id for item in projection.control_plane.actions
            ),
            authorized_mutation_ids=transition.control_plane_mutation_ids,
            results=control,
        ),
        CanonicalMutationSurfaceObservation(
            surface="voice",
            plan_action_ids=tuple(item.id for item in projection.voice.actions),
            authorized_mutation_ids=transition.voice_mutation_ids,
            results=voice,
        ),
    )


def test_no_mutation_replay_is_emitted_only_from_observed_ids_and_journals(
    router0_delta,
):
    _floor3, router0, transition = router0_delta

    audit = canonical_stage_mutation_replay_audit(
        router0.stage.value,
        _observations(
            router0,
            transition,
            configuration=(
                _configuration_attempt(
                    router0.configuration,
                    transition.configuration_mutation_ids,
                ),
                # The governed re-read: authorized to dispatch nothing at all.
                _configuration_attempt(router0.configuration, ()),
            ),
            control=(_control_plane_attempt(
                router0.control_plane, transition.control_plane_mutation_ids,
            ),),
            voice=(_voice_attempt(
                router0.voice, transition.voice_mutation_ids,
            ),),
        ),
    )

    assert audit.verified is True
    assert audit.claim == "NO_MUTATION_REPLAY"
    assert audit.replayed_retained_ids == ()
    by_surface = {item.surface: item for item in audit.surfaces}
    assert set(by_surface) == {"configuration", "control-plane", "voice"}
    assert by_surface["configuration"].journaled_action_ids == tuple(
        sorted(transition.configuration_mutation_ids)
    )
    assert by_surface["control-plane"].retained_action_ids == (
        transition.control_plane_retained_ids
    )
    assert by_surface["voice"].dispatched_mutation_ids == tuple(
        sorted(transition.voice_mutation_ids)
    )


@pytest.mark.parametrize(
    "surface", ["configuration", "control-plane", "voice"],
)
def test_a_retained_action_executed_again_refuses_the_claim(
    router0_delta,
    surface,
):
    _floor3, router0, transition = router0_delta
    identifier, plan = {
        "configuration": (
            transition.configuration_retained_ids[0], router0.configuration,
        ),
        "control-plane": (
            transition.control_plane_retained_ids[0], router0.control_plane,
        ),
        "voice": (transition.voice_retained_ids[0], router0.voice),
    }[surface]
    builder = {
        "configuration": _configuration_attempt,
        "control-plane": _control_plane_attempt,
        "voice": _voice_attempt,
    }[surface]
    attempts = {
        "configuration": [_configuration_attempt(
            router0.configuration, transition.configuration_mutation_ids,
        )],
        "control-plane": [_control_plane_attempt(
            router0.control_plane, transition.control_plane_mutation_ids,
        )],
        "voice": [_voice_attempt(
            router0.voice, transition.voice_mutation_ids,
        )],
    }
    attempts[surface].append(builder(plan, (identifier,)))

    audit = canonical_stage_mutation_replay_audit(
        router0.stage.value,
        _observations(
            router0,
            transition,
            configuration=tuple(attempts["configuration"]),
            control=tuple(attempts["control-plane"]),
            voice=tuple(attempts["voice"]),
        ),
    )

    assert audit.verified is False
    assert audit.claim == "MUTATION_REPLAY_DETECTED"
    assert audit.replayed_retained_ids == (f"{surface}:{identifier}",)
    offender = next(
        item for item in audit.surfaces if item.surface == surface
    )
    assert offender.replayed_retained_ids == (identifier,)
    assert identifier in offender.unauthorized_mutation_ids
    assert all(
        item.verified for item in audit.surfaces if item.surface != surface
    )


def test_a_dispatch_no_journal_attests_refuses_the_claim(router0_delta):
    _floor3, router0, transition = router0_delta
    unattested = _configuration_attempt(
        router0.configuration, transition.configuration_mutation_ids,
    ).model_copy(update={"execution_journal": None})

    audit = canonical_stage_mutation_replay_audit(
        router0.stage.value,
        _observations(
            router0,
            transition,
            configuration=(unattested,),
            control=(_control_plane_attempt(
                router0.control_plane, transition.control_plane_mutation_ids,
            ),),
            voice=(_voice_attempt(
                router0.voice, transition.voice_mutation_ids,
            ),),
        ),
    )

    offender = next(
        item for item in audit.surfaces if item.surface == "configuration"
    )
    assert audit.claim == "MUTATION_REPLAY_DETECTED"
    assert offender.unattested_mutation_ids == tuple(
        sorted(transition.configuration_mutation_ids)
    )
    assert "execution journal" in " ".join(offender.errors)


def test_an_authorized_surface_that_produced_nothing_refuses_the_claim(
    router0_delta,
):
    _floor3, router0, transition = router0_delta

    audit = canonical_stage_mutation_replay_audit(
        router0.stage.value,
        _observations(
            router0,
            transition,
            configuration=(_configuration_attempt(
                router0.configuration, transition.configuration_mutation_ids,
            ),),
            control=(_control_plane_attempt(
                router0.control_plane, transition.control_plane_mutation_ids,
            ),),
            voice=(),
        ),
    )

    offender = next(
        item for item in audit.surfaces if item.surface == "voice"
    )
    assert audit.verified is False
    assert offender.errors == (
        "authorized mutations produced no typed application result",
    )
