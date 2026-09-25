"""Versioned native-pool experiment under the delegated DHCP mandate."""

from __future__ import annotations

from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    stage_definition,
    step_selection_refusals,
)


def test_native_pool_profile_has_one_fixed_intervention_and_finite_budget() -> None:
    """A probe cannot silently inherit the old C1 acquisition procedure."""
    definition = stage_definition("Q3-NATIVE-PROBE")
    assert definition is not None
    assert (definition.profile_id, definition.profile_version) == ("Q3-NATIVE", "1")
    assert definition.fixture_models == (
        "__MCP_E6Q_SRV:Server-PT",
        "__MCP_E6Q_PC1:PC-PT",
        "__MCP_E6Q_PC2:PC-PT",
        "__MCP_E6Q_SW:2960-24TT",
    )
    assert definition.allowed_channels == ("file",)
    assert definition.step_ids == ("NATIVE-start",)
    assert definition.experiments_of_steps(definition.step_ids) == (
        "M-NATIVE-START",
        "M-NATIVE-FINAL",
    )
    assert definition.budget.max_operations == 120
    assert definition.budget.max_seconds == 600
    assert definition.budget.reserve_seconds == 300
    assert definition.planned_minimum_operations <= 120
    assert step_selection_refusals(definition, ["NATIVE-start"]) == []
