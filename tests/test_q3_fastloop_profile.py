"""DF6: the versioned Q3-FL profiles, and the historical ones left alone."""

from __future__ import annotations

import pytest

from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    Q3_FL_FORWARDING_OPERATIONS,
    Q3_FL_NATIVE_DEFAULT_POLICY,
    Q3_FL_PROFILE,
    Q3_FL_PROFILE_VERSION,
    Q3_FL_STAGES,
    REQUESTED_RENEWAL_CONTRACT_ABSENT,
    STAGE_CEILINGS,
    QualificationStage,
    RefusalSubject,
    request_refusals,
    stage_definition,
    step_selection_refusals,
)
from tests.service_qualification_engine import request_args

pytestmark = pytest.mark.parametrize("stage", [item.value for item in Q3_FL_STAGES])


def test_each_profile_pins_its_fixture_capacity_channel_and_identity(stage):
    """Two users or one, the same fixture, file channel and profile version."""
    definition = stage_definition(stage)
    assert definition.fixture_models == (
        "__MCP_E6Q_SRV:Server-PT",
        "__MCP_E6Q_PC1:PC-PT",
        "__MCP_E6Q_PC2:PC-PT",
        "__MCP_E6Q_SW:2960-24TT",
    )
    assert definition.link_bindings == (
        "__MCP_E6Q_SRV:FastEthernet0-__MCP_E6Q_SW:FastEthernet0/1",
        "__MCP_E6Q_PC1:FastEthernet0-__MCP_E6Q_SW:FastEthernet0/2",
        "__MCP_E6Q_PC2:FastEthernet0-__MCP_E6Q_SW:FastEthernet0/3",
    )
    assert definition.dhcp_pool_capacity == (1 if stage == "Q3-FL-C1" else 2)
    assert definition.allowed_channels == ("file",)
    assert (definition.profile_id, definition.profile_version) == (
        Q3_FL_PROFILE,
        Q3_FL_PROFILE_VERSION,
    )
    assert Q3_FL_NATIVE_DEFAULT_POLICY == "q3-fl-native-default/v1"


def test_the_worst_case_is_composed_and_fits_the_versioned_ceiling(stage):
    """17 setup, 411 of measurement worst case, 11 reserved: 439 of 440."""
    definition = stage_definition(stage)
    planned = {item.id: item.planned_operations for item in definition.experiments}
    assert planned["M-DHCP-1"] == 3 + 3 + Q3_FL_FORWARDING_OPERATIONS + 6 + 5
    assert planned["M-DHCP-6"] == 2 + 2 * 10
    assert (planned["M-DHCP-6-REPEAT"], planned["M-DHCP-6-TIME"]) == (2, 6)
    assert planned["M-DHCP-1-FINAL"] == 2
    assert definition.setup_operations == 17
    assert definition.reserve_operations == 11
    assert definition.planned_minimum_operations == 439
    assert STAGE_CEILINGS[QualificationStage(stage)] == (440, 1500)
    assert definition.budget.reserve_seconds == 300


def test_declared_omissions_carry_their_reasons(stage):
    """M-DHCP-3 stays deferred; requested renewal has no typed contract."""
    definition = stage_definition(stage)
    reasons = {item.id: item.omission_reason for item in definition.experiments}
    assert reasons["M-DHCP-3"].startswith("qualification_event_source_and_release")
    assert reasons["M-DHCP-6-RENEW"] == REQUESTED_RENEWAL_CONTRACT_ABSENT
    capacity_step = "Q3FL-capacity" in definition.step_ids
    assert capacity_step is (stage == "Q3-FL-C1")
    assert bool(reasons["M-DHCP-6-CAP"]) is (stage == "Q3-FL-C2")


def test_every_selection_needs_the_core_step(stage):
    """A repeat, timing or final reading without the core procedure is refused."""
    definition = stage_definition(stage)
    refused = step_selection_refusals(definition, ["Q3FL-repeat"])
    assert refused and "requires 'Q3FL-core'" in refused[0].detail
    assert step_selection_refusals(definition, list(definition.step_ids)) == []
    assert set(definition.experiments_of_steps(["Q3FL-core"])) >= {
        "M-DHCP-1",
        "M-DHCP-2",
        "M-DHCP-4",
        "M-DHCP-5",
        "M-DHCP-6",
    }


def test_the_profile_binds_the_whole_diagnostic_identity(stage):
    """No profile, tree, process or attempt: refused before any reader runs."""
    from packet_tracer_mcp.adapters.cli.service_qualification import _request

    targets = [
        value
        for name in stage_definition(stage).fixture_names
        for value in ("--authorized-target", name)
    ]
    request = _request(
        [
            *request_args(stage),
            "--authorization-id",
            "TD",
            "--authorized-stage",
            stage,
            "--authorized-sha",
            "a" * 40,
            "--authorized-channel",
            "file",
            "--authorized-build",
            "9.0.1.0858",
            "--authorized-max-operations",
            "440",
            "--authorized-max-seconds",
            "1500",
            *targets,
        ]
    )
    subjects = {item.subject for item in request_refusals(request)}
    assert {
        RefusalSubject.AUTHORIZED_PROFILE,
        RefusalSubject.AUTHORIZED_TREE,
        RefusalSubject.AUTHORIZED_PROCESS,
        RefusalSubject.ATTEMPT_IDENTITY,
        RefusalSubject.AUTHORIZED_STEPS,
    } <= subjects


def test_the_historical_profiles_are_untouched(stage):
    """Q3 keeps 60/1200 and its 59; D-DHCP keeps its v3 identity and 50/1500."""
    del stage
    q3 = stage_definition("Q3")
    assert STAGE_CEILINGS[QualificationStage.Q3] == (60, 1200)
    assert q3.planned_minimum_operations == 59
    assert q3.profile_id == "" and q3.steps == ()
    assert [item.id for item in q3.experiments] == [
        "M-DHCP-1",
        "M-DHCP-4",
        "M-DHCP-5",
        "M-DHCP-2",
        "M-DHCP-3",
        "M-DHCP-6",
    ]
    assert stage_definition("Q3").dhcp_pool_capacity == 0
    d_dhcp = stage_definition("D-DHCP")
    assert STAGE_CEILINGS[QualificationStage.D_DHCP] == (50, 1500)
    assert (d_dhcp.profile_id, d_dhcp.profile_version) == ("D-DHCP", "3")
