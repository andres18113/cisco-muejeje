"""Governed Router3 preparation stays typed, cumulative, and offline-only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.packet_tracer_mcp.application.cp_scale_live.checkpoint import (
    CPScaleCheckpointDecision,
)
from src.packet_tracer_mcp.application.cp_scale_live.completion import (
    CPScaleCompletion,
)
from src.packet_tracer_mcp.application.cp_scale_live.run_contracts import (
    CPScaleTerminalEvent,
)
from src.packet_tracer_mcp.application.cp_scale_live.step_policy import (
    canonical_step_decision,
)
from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    CPScaleCanonicalTarget,
    CPScaleForwardingAuthority,
    canonical_cp_scale_target_contract,
    canonical_stage_transition_contract,
    project_cp_scale_canonical_stage,
)
from src.packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    CPScaleFinalDisposition,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.scenarios.cp_scale_physical import SMALL
from tests.poe_delivery_capabilities import (
    compose_delivery_qualified_cp_scale_canonical,
)


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "docs" / "reference" / "cp-scale" / "current_state.json"
VERSION = "9.0.1.0858"


@pytest.fixture(scope="module")
def preparation():
    composition = compose_delivery_qualified_cp_scale_canonical(
        packet_tracer_version=VERSION,
    )
    router0 = project_cp_scale_canonical_stage(
        composition,
        CPScaleCanonicalStage.ROUTER0_BRANCH,
    )
    router3 = project_cp_scale_canonical_stage(
        composition,
        CPScaleCanonicalStage.ROUTER3_BRANCH,
    )
    transition = canonical_stage_transition_contract(router0, router3)
    return composition, router0, router3, transition


@pytest.mark.parametrize(
    ("target", "terminal", "precleanup", "cleaned"),
    [
        (
            CPScaleCanonicalTarget.ROUTER0_BRANCH,
            CPScaleCanonicalStage.ROUTER0_BRANCH,
            "ROUTER0_BRANCH_VERIFIED_PRECLEANUP",
            "ROUTER0_BRANCH_VERIFIED_AND_CLEANED",
        ),
        (
            CPScaleCanonicalTarget.ROUTER3_BRANCH,
            CPScaleCanonicalStage.ROUTER3_BRANCH,
            "ROUTER3_BRANCH_VERIFIED_PRECLEANUP",
            "ROUTER3_BRANCH_VERIFIED_AND_CLEANED",
        ),
    ],
)
def test_bounded_branch_targets_have_independent_cleanup_contracts(
    target,
    terminal,
    precleanup,
    cleaned,
):
    contract = canonical_cp_scale_target_contract(target)
    expected_stages = tuple(
        stage
        for stage in CPScaleCanonicalStage
        if stage is not CPScaleCanonicalStage.REMAINING
        and list(CPScaleCanonicalStage).index(stage)
        <= list(CPScaleCanonicalStage).index(terminal)
    )

    assert contract.build_stages == expected_stages
    assert contract.build_stages[-1] is contract.terminal_stage is terminal
    assert CPScaleCanonicalStage.REMAINING not in contract.build_stages
    assert contract.run_remaining_reconciliation is False
    assert contract.run_full_qualification is False
    assert contract.allow_retention is False
    assert contract.require_cleanup is True
    assert contract.precleanup_closure == precleanup
    assert contract.cleaned_closure == cleaned


def test_router0_to_router3_transition_is_the_product_delta(preparation):
    _composition, router0, router3, transition = preparation
    phone_role = DeviceRole.IP_PHONE.value

    assert transition.previous_stage is CPScaleCanonicalStage.ROUTER0_BRANCH
    assert transition.current_stage is CPScaleCanonicalStage.ROUTER3_BRANCH
    assert len(transition.new_device_ids) == 24
    assert len(transition.new_link_ids) == 17
    assert (
        sum(item.enterprise_role == phone_role for item in router3.topology.devices)
        - sum(item.enterprise_role == phone_role for item in router0.topology.devices)
    ) == 7

    surfaces = (
        (
            router0.configuration.actions,
            router3.configuration.actions,
            transition.configuration_retained_ids,
            transition.configuration_mutation_ids,
        ),
        (
            router0.control_plane.actions,
            router3.control_plane.actions,
            transition.control_plane_retained_ids,
            transition.control_plane_mutation_ids,
        ),
        (
            router0.voice.actions,
            router3.voice.actions,
            transition.voice_retained_ids,
            transition.voice_mutation_ids,
        ),
    )
    assert [len(item[3]) for item in surfaces] == [33, 17, 19]
    for previous, current, retained, mutations in surfaces:
        previous_ids = {item.id for item in previous}
        current_ids = {item.id for item in current}
        assert set(retained) == previous_ids
        assert set(mutations).isdisjoint(retained)
        assert set(mutations) | set(retained) == current_ids

    assert transition.mutation_scope_disjoint is True
    assert transition.claim == "MUTATION_SCOPE_DISJOINT"
    assert "NO_MUTATION_REPLAY" not in transition.claim


def test_router3_forwarding_is_derived_from_small_branch_intent(preparation):
    composition, _router0, router3, _transition = preparation
    flows = sorted(
        (
            item
            for item in composition.enterprise.traffic_flows
            if SMALL in (
                item.source_site_id,
                item.destination_site_id,
            )
        ),
        key=lambda item: item.id,
    )
    assert [item.id for item in flows] == [
        "flow/multilayer-to-small",
        "flow/small-to-large",
    ]

    site_checks = router3.branch_forwarding_checks
    user_checks = router3.branch_user_forwarding_checks
    by_direction = {item.direction: item for item in site_checks}
    assert len(site_checks) == 2 * len(flows)
    assert len(user_checks) == len(site_checks)
    assert len(by_direction) == len(site_checks)

    for flow in flows:
        direct = by_direction[
            f"{flow.source_site_id}-to-{flow.destination_site_id}"
        ]
        reverse = by_direction[
            f"{flow.destination_site_id}-to-{flow.source_site_id}"
        ]
        assert direct.authority is CPScaleForwardingAuthority.DECLARED_TRAFFIC_FLOW
        assert direct.declared_traffic_flow_id == flow.id
        assert direct.reverse_of_traffic_flow_id == ""
        assert reverse.authority is (
            CPScaleForwardingAuthority.REVERSE_PATH_OF_DECLARED_FLOW
        )
        assert reverse.declared_traffic_flow_id == ""
        assert reverse.reverse_of_traffic_flow_id == flow.id

    configuration_ids = {item.id for item in router3.configuration.actions}
    topology_ids = {item.id for item in router3.topology.devices}
    for check in site_checks:
        assert check.destination_ipv4 is None
        assert check.destination_action_id in configuration_ids
        assert check.destination_device_id in topology_ids
        assert check.destination_selection.site_id == check.destination_site_id
    assert {item.direction for item in user_checks} == {
        f"{item.source_site_id}-pc-to-{item.destination_site_id}-pc"
        for item in site_checks
    }
    assert all(
        item.target_policy_id == site_checks[0].destination_selection.policy_id
        and item.authority == "cp-scale-selected-wired-data-workload-pair"
        for item in user_checks
    )


def test_router3_terminal_policy_stops_before_remaining_and_requires_cleanup():
    router3 = canonical_cp_scale_target_contract(
        CPScaleCanonicalTarget.ROUTER3_BRANCH,
    )
    decisions = {
        stage: canonical_step_decision(router3, stage)
        for stage in router3.build_stages
    }
    assert {
        stage for stage, decision in decisions.items() if decision.site_forwarding
    } == {CPScaleCanonicalStage.ROUTER3_BRANCH}
    assert decisions[CPScaleCanonicalStage.ROUTER3_BRANCH].checkpoint_required is False

    full = canonical_cp_scale_target_contract(
        CPScaleCanonicalTarget.FULL_QUALIFICATION,
    )
    full_router3 = canonical_step_decision(
        full,
        CPScaleCanonicalStage.ROUTER3_BRANCH,
    )
    assert full_router3.site_forwarding is False
    assert full_router3.checkpoint_required is True

    plan = CPScaleCompletion(cleanup=object()).plan(
        router3,
        CPScaleCheckpointDecision.RETAIN,
        retain_authorized=True,
    )
    assert plan.disposition is CPScaleFinalDisposition.CLEANUP
    assert plan.event is CPScaleTerminalEvent.ROUTER3_CLEANED
    assert plan.scope == CPScaleCanonicalStage.ROUTER3_BRANCH.value
    assert plan.checkpoint == CPScaleCanonicalTarget.ROUTER3_BRANCH.value
    assert plan.final_checkpoint is False
    assert plan.bounded_target is True


def test_current_state_records_preparation_without_live_authority(preparation):
    composition, router0, router3, transition = preparation
    document = json.loads(STATE.read_text(encoding="utf-8"))
    state = document["operational_state"]["router3"]
    offline = state["offline_preparation"]
    contract = canonical_cp_scale_target_contract(
        CPScaleCanonicalTarget.ROUTER3_BRANCH,
    )
    flows = sorted(
        item.id
        for item in composition.enterprise.traffic_flows
        if SMALL in (item.source_site_id, item.destination_site_id)
    )

    assert state["status"] == "ROUTER3_OFFLINE_PREPARED"
    assert state["executed"] is False
    assert state["verification"] == "NOT_VERIFIED"
    assert state["live_evidence"] == "UNKNOWN"
    assert state["live_evidence_acquired"] is False
    assert state["live_execution_authorized"] is False
    assert document["operational_state"]["live_execution_authorized"] is False
    assert document["operational_state"]["next_active_step"] == (
        "AWAIT_EXPLICIT_ROUTER3_LIVE_AUTHORIZATION"
    )

    assert offline["target"] == "router3-branch"
    assert offline["terminal_stage"] == router3.stage.value
    assert offline["build_stages"] == [
        item.value for item in contract.build_stages
    ]
    assert offline["run_remaining_reconciliation"] is False
    assert offline["run_full_qualification"] is False
    assert offline["allow_retention"] is False
    assert offline["require_cleanup"] is True
    assert offline["precleanup_closure"] == contract.precleanup_closure
    assert offline["cleaned_closure"] == contract.cleaned_closure
    assert offline["transition"] == {
        "previous_stage": router0.stage.value,
        "current_stage": router3.stage.value,
        "new_devices": len(transition.new_device_ids),
        "new_links": len(transition.new_link_ids),
        "new_phones": 7,
        "configuration_mutations": len(transition.configuration_mutation_ids),
        "configuration_retained": len(transition.configuration_retained_ids),
        "control_plane_mutations": len(transition.control_plane_mutation_ids),
        "control_plane_retained": len(transition.control_plane_retained_ids),
        "voice_mutations": len(transition.voice_mutation_ids),
        "voice_retained": len(transition.voice_retained_ids),
        "claim": "MUTATION_SCOPE_DISJOINT",
        "runtime_replay_claim": "NOT_ACQUIRED",
    }
    assert offline["forwarding"] == {
        "declared_flow_ids": flows,
        "router_to_workload_checks": len(router3.branch_forwarding_checks),
        "representative_pc_checks": len(router3.branch_user_forwarding_checks),
        "authority_kinds": sorted({
            item.authority.value for item in router3.branch_forwarding_checks
        }),
    }
