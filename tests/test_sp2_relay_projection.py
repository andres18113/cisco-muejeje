"""SP-2 remote relay applies its compiled foundations before PC DHCP mode."""

from __future__ import annotations

import pytest

from packet_tracer_mcp.adapters.cli.service_qualification import (
    sp2_remote_relay_contract,
)
from packet_tracer_mcp.domain.enterprise.models.verification import (
    PrerequisiteKind,
    VerificationPrerequisite,
)
from packet_tracer_mcp.domain.enterprise.services import service_diagnostic_profiles


def test_preclient_plan_retains_routed_foundations_without_client_mode():
    """The E5 projection owns every path effect but cannot bind the PC early."""
    contract = sp2_remote_relay_contract("9.0.1.0858", "sp2-e3-preclient")
    project = getattr(
        service_diagnostic_profiles, "sp2_preclient_configuration_plan", None
    )
    assert callable(project)

    plan, rewrites = project(contract.configuration_plan)

    assert len(plan.actions) == 18
    kinds = {item.action_type.value for item in plan.actions}
    assert "set_endpoint_dhcp" not in kinds
    assert {
        "configure_dhcp_relay",
        "configure_static_route",
        "configure_routed_interface",
        "configure_access_port",
        "set_endpoint_static",
    } <= kinds
    action_ids = {item.id for item in plan.actions}
    assert all(set(item.depends_on) <= action_ids for item in plan.actions)
    assert all(set(item.apply_dependencies) <= action_ids for item in plan.actions)
    assert all(item.action_id in action_ids for item in plan.verification_expectations)
    assert all(set(item.action_ids) <= action_ids for item in plan.devices)
    assert not any(item.device_name == "BR1-DEFAULT-PC-01" for item in plan.devices)
    assert all(
        set(item.required_capabilities)
        == {
            action.required_capability
            for action in plan.actions
            if action.device_id == item.device_id and action.required_capability
        }
        for item in plan.devices
    )
    assert plan.source_topology_hash == contract.configuration_plan.source_topology_hash
    assert (
        plan.semantic_hash
        and plan.semantic_hash != contract.configuration_plan.semantic_hash
    )
    assert [item.kind for item in rewrites] == ["action_omitted"]


def test_preclient_plan_refuses_a_path_action_that_depends_on_client_mode():
    """A projection cannot erase a real dependency to reach relay effects."""
    contract = sp2_remote_relay_contract("9.0.1.0858", "sp2-e3-bad-dependency")
    plan = contract.configuration_plan.model_copy(deep=True)
    mode = next(
        item for item in plan.actions if item.action_type.value == "set_endpoint_dhcp"
    )
    relay = next(
        item
        for item in plan.actions
        if item.action_type.value == "configure_dhcp_relay"
    )
    relay.depends_on.append(mode.id)

    with pytest.raises(ValueError, match="missing dependency"):
        service_diagnostic_profiles.sp2_preclient_configuration_plan(plan)


def test_preclient_plan_refuses_a_readback_dependent_on_client_mode():
    """A retained E5 readback cannot borrow the deferred PC action."""
    contract = sp2_remote_relay_contract("9.0.1.0858", "sp2-e3-bad-readback")
    plan = contract.configuration_plan.model_copy(deep=True)
    mode = next(
        item for item in plan.actions if item.action_type.value == "set_endpoint_dhcp"
    )
    relay = next(
        item
        for item in plan.verification_expectations
        if item.kind.value == "dhcp_relay"
    )
    relay.verification_prerequisites.append(
        VerificationPrerequisite(
            kind=PrerequisiteKind.ACTION_APPLIED, reference_id=mode.id
        )
    )

    with pytest.raises(ValueError, match="readback prerequisite"):
        service_diagnostic_profiles.sp2_preclient_configuration_plan(plan)


def test_preclient_plan_refuses_a_missing_retained_device_row():
    """Every retained E5 action needs its compiler-owned device metadata."""
    contract = sp2_remote_relay_contract("9.0.1.0858", "sp2-e3-missing-device")
    plan = contract.configuration_plan.model_copy(deep=True)
    plan.devices = [
        item for item in plan.devices if item.device_name != "BR1-EDGE-RTR-01"
    ]

    with pytest.raises(ValueError, match="device row is missing"):
        service_diagnostic_profiles.sp2_preclient_configuration_plan(plan)
