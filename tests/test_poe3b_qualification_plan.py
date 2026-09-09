"""Governed CP-SCALE PoE capacity qualification plan acceptance."""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    cp_scale_canonical_stage_includes_device,
)
from src.packet_tracer_mcp.application.use_cases.plan_cp_scale_poe_capacity import (
    cp_scale_poe_capacity_qualification_plan,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    PoEAuthorizedBinding,
)
from src.packet_tracer_mcp.domain.enterprise.scenarios.cp_scale import (
    cp_scale_intent,
)
from src.packet_tracer_mcp.domain.enterprise.scenarios.cp_scale_physical import (
    SW3,
    cp_scale_physical_design,
)
from src.packet_tracer_mcp.domain.enterprise.services.endpoint_expander import (
    EndpointGroupExpander,
)
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import (
    EnterpriseDesigner,
)
from src.packet_tracer_mcp.domain.enterprise.services.naming import (
    DeterministicNamingService,
)


BUILD = "9.0.1.0858"
EXPECTED_3560_BINDINGS = (
    PoEAuthorizedBinding("FastEthernet0/1", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/2", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/3", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/4", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/5", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/6", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/7", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/8", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/9", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/10", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/11", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/12", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/13", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/14", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/15", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/16", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/17", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/18", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/19", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/20", "7960", "Switch"),
    PoEAuthorizedBinding("FastEthernet0/21", "7960", "Switch"),
)
EXPECTED_3650_BINDINGS = (
    PoEAuthorizedBinding("GigabitEthernet1/0/2", "7960", "Switch"),
    PoEAuthorizedBinding("GigabitEthernet1/0/3", "7960", "Switch"),
    PoEAuthorizedBinding("GigabitEthernet1/0/5", "7960", "Switch"),
    PoEAuthorizedBinding("GigabitEthernet1/0/6", "7960", "Switch"),
    PoEAuthorizedBinding("GigabitEthernet1/0/7", "7960", "Switch"),
    PoEAuthorizedBinding("GigabitEthernet1/0/8", "7960", "Switch"),
    PoEAuthorizedBinding("GigabitEthernet1/0/9", "7960", "Switch"),
    PoEAuthorizedBinding("GigabitEthernet1/0/10", "7960", "Switch"),
    PoEAuthorizedBinding("GigabitEthernet1/0/11", "7960", "Switch"),
    PoEAuthorizedBinding("GigabitEthernet1/0/12", "7960", "Switch"),
    PoEAuthorizedBinding("GigabitEthernet1/0/13", "7960", "Switch"),
)


def _powered_bindings_by_device() -> dict[str, tuple[PoEAuthorizedBinding, ...]]:
    designed = EnterpriseDesigner().design(cp_scale_intent())
    assert designed.validation.is_valid
    assert designed.plan is not None
    powered_ids = {
        endpoint.id
        for endpoint in EndpointGroupExpander().expand(
            designed.plan, DeterministicNamingService(),
        )
        if endpoint.requires_poe
    }
    return {
        device.id: tuple(
            PoEAuthorizedBinding(
                binding.device_port,
                binding.endpoint_model,
                binding.endpoint_port,
            )
            for site in cp_scale_physical_design().sites
            for binding in site.endpoint_bindings
            if binding.device_id == device.id and binding.endpoint_id in powered_ids
        )
        for site in cp_scale_physical_design().sites
        for device in site.devices
    }


def test_router0_plan_has_exact_ordered_model_bindings_and_counts() -> None:
    plan = cp_scale_poe_capacity_qualification_plan(BUILD)

    assert plan.packet_tracer_build == BUILD
    assert plan.target_stage == CPScaleCanonicalStage.ROUTER0_BRANCH.value
    assert tuple(item.candidate_model for item in plan.models) == (
        "3560-24PS",
        "3650-24PS",
    )

    model_3560 = plan.for_model("3560-24PS")
    assert model_3560.packet_tracer_build == BUILD
    assert model_3560.candidate_model == "3560-24PS"
    assert model_3560.bindings == EXPECTED_3560_BINDINGS
    assert model_3560.simultaneous_active_ports == 21

    model_3650 = plan.for_model("3650-24PS")
    assert model_3650.packet_tracer_build == BUILD
    assert model_3650.candidate_model == "3650-24PS"
    assert model_3650.bindings == EXPECTED_3650_BINDINGS
    assert model_3650.simultaneous_active_ports == 11


def test_plan_excludes_externally_powered_access_points() -> None:
    plan = cp_scale_poe_capacity_qualification_plan(BUILD)

    assert all(
        binding.endpoint_model != "AccessPoint-PT"
        for model in plan.models
        for binding in model.bindings
    )


def test_model_scopes_cover_every_same_model_powered_device_by_exact_subset() -> None:
    design = cp_scale_physical_design()
    device_by_id = {
        device.id: device for site in design.sites for device in site.devices
    }
    powered_by_device = _powered_bindings_by_device()
    plan = cp_scale_poe_capacity_qualification_plan(BUILD)

    expected_powered_names = {
        "3560-24PS": {"Switch5", "Switch7", "Switch9", "Switch1", "MLS5", "Switch3"},
        "3650-24PS": {"MLS3", "MLS4"},
    }
    for model, expected_names in expected_powered_names.items():
        governed = set(plan.for_model(model).bindings)
        actual_names = {
            device_by_id[device_id].semantic_name
            for device_id, bindings in powered_by_device.items()
            if bindings and device_by_id[device_id].model == model
        }
        assert actual_names == expected_names
        for device_id, bindings in powered_by_device.items():
            if bindings and device_by_id[device_id].model == model:
                assert set(bindings) <= governed


def test_router0_stage_excludes_switch3_while_3560_scope_covers_its_demand() -> None:
    switch3 = next(
        device
        for site in cp_scale_physical_design().sites
        for device in site.devices
        if device.id == SW3
    )
    assert not cp_scale_canonical_stage_includes_device(
        CPScaleCanonicalStage.ROUTER0_BRANCH,
        switch3.id,
        switch3.site_id,
        switch3.parent_group,
    )

    plan_bindings = set(
        cp_scale_poe_capacity_qualification_plan(BUILD)
        .for_model("3560-24PS")
        .bindings
    )
    assert set(_powered_bindings_by_device()[SW3]) <= plan_bindings


def test_unknown_model_selection_fails_closed() -> None:
    plan = cp_scale_poe_capacity_qualification_plan(BUILD)

    with pytest.raises(ValueError, match="unknown-model"):
        plan.for_model("unknown-model")
