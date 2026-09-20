"""The two prepared diagnostics, offline (unit and domain-integration level).

Nothing here dispatches anything. The plan projections are exercised against
the real Q3 product contract, so the sequences these profiles propose are the
ones the existing compiler can actually produce, and the one decomposition it
cannot produce is proven to be the declared seam rather than a copied setter.
"""

from __future__ import annotations

import dataclasses

import pytest

from packet_tracer_mcp.adapters.cli.service_qualification import (
    Q3_PACKET_TRACER_BUILD,
    q3_product_contract,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ConfigureServerDhcpPool,
    EnableServerDhcp,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    Q3_SERVER,
    STAGE_DEFINITIONS,
    QualificationStage,
)
from packet_tracer_mcp.domain.enterprise.services.service_diagnostic_profiles import (
    D_DHCP,
    D_WEB,
    GRANTED,
    POOL_BEFORE_ENABLE,
    DiagnosticAuthorization,
    DiagnosticEffect,
    d_dhcp_enable_only_plan,
    d_dhcp_pool_only_plan,
    d_dhcp_profile,
    d_dhcp_static_only_plan,
    d_web_profile,
    diagnostic_dispatch_refusal,
    prepared_profiles,
)

CHANNELS = ("http", "file")
Q3 = STAGE_DEFINITIONS[QualificationStage.Q3]


@pytest.fixture
def contract():
    """Return the real Q3 product contract the projections are built from."""
    return q3_product_contract(Q3_PACKET_TRACER_BUILD, "diagnostic-preparation")


@pytest.fixture
def profiles():
    """Return both prepared profiles for the measured build."""
    return prepared_profiles(build=Q3_PACKET_TRACER_BUILD, channels=CHANNELS)


def _granted(profile, **overrides) -> DiagnosticAuthorization:
    """Return the authorization a reviewer would have to write, then vary it."""
    values = {
        "profile_id": profile.id,
        "status": GRANTED,
        "granted": True,
        "authorization_id": "TD-DIAG-0001",
        "reviewer": "independent-reviewer",
        "build": profile.build,
        "channel": "file",
        "fixtures": profile.fixtures,
        "step_ids": tuple(
            item.id for item in profile.steps if not item.separately_authorized
        ),
        "max_operations": profile.budget.max_operations,
        "max_seconds": profile.budget.max_seconds,
        "approved_seams": profile.seam_ids,
    }
    values.update(overrides)
    return DiagnosticAuthorization(**values)


# -- the drafts grant nothing --------------------------------------------------


def test_both_prepared_profiles_carry_an_ungranted_draft(profiles):
    """Neither draft has a status, an identity or any granted flag."""
    assert [item.id for item in profiles] == [D_DHCP, D_WEB]
    for profile in profiles:
        draft = profile.authorization
        assert (draft.status, draft.granted) == ("DRAFT", False)
        assert (draft.authorization_id, draft.reviewer) == ("", "")
        assert (draft.step_ids, draft.approved_seams, draft.fixtures) == ((), (), ())
        assert diagnostic_dispatch_refusal(profile, draft) == (
            "diagnostic_authorization_not_granted:DRAFT"
        )
        assert diagnostic_dispatch_refusal(profile, None) == (
            "diagnostic_authorization_absent"
        )


def test_no_executable_stage_reaches_a_prepared_profile(profiles):
    """A profile is not a stage: no stage definition names one."""
    stages = {item.stage.value for item in STAGE_DEFINITIONS.values()}
    assert {item.id for item in profiles}.isdisjoint(stages)


@pytest.mark.parametrize(
    ("overrides", "refusal"),
    [
        ({"granted": False}, "diagnostic_authorization_not_granted:GRANTED"),
        ({"status": "DRAFT"}, "diagnostic_authorization_not_granted:DRAFT"),
        ({"authorization_id": ""}, "diagnostic_authorization_identity_missing"),
        ({"reviewer": ""}, "diagnostic_authorization_identity_missing"),
        ({"profile_id": D_WEB}, f"diagnostic_authorization_names:{D_WEB}"),
        ({"build": "9.0.1.9999"}, "diagnostic_build_not_authorized:9.0.1.9999"),
        ({"channel": "serial"}, "diagnostic_channel_not_authorized:serial"),
        ({"fixtures": (Q3_SERVER,)}, "diagnostic_fixture_set_not_authorized"),
        ({"max_operations": 61}, "diagnostic_ceiling_not_authorized"),
        ({"max_seconds": 1200}, "diagnostic_ceiling_not_authorized"),
        ({"step_ids": ()}, "diagnostic_no_step_authorized"),
        ({"step_ids": ("D9",)}, "diagnostic_step_not_defined:D9"),
        (
            {"approved_seams": ()},
            f"diagnostic_seam_not_approved:{POOL_BEFORE_ENABLE}",
        ),
    ],
)
def test_every_scope_mismatch_refuses_on_its_own(overrides, refusal):
    """Fail-closed: one wrong or missing value is enough to refuse."""
    profile = d_dhcp_profile(build=Q3_PACKET_TRACER_BUILD, channels=CHANNELS)
    assert diagnostic_dispatch_refusal(profile, _granted(profile, **overrides)) == (
        refusal
    )


def test_a_complete_exact_scope_authorization_is_the_only_thing_that_passes():
    """The gate is a gate, not a wall: an exact granted record does pass."""
    profile = d_dhcp_profile(build=Q3_PACKET_TRACER_BUILD, channels=CHANNELS)
    assert diagnostic_dispatch_refusal(profile, _granted(profile)) == ""


def test_a_selection_that_does_not_fit_the_ceiling_refuses():
    """The reserve counts: a selection that would spend it does not fit."""
    profile = d_dhcp_profile(build=Q3_PACKET_TRACER_BUILD, channels=CHANNELS)
    narrow = dataclasses.replace(
        profile,
        budget=dataclasses.replace(profile.budget, max_operations=20),
    )
    assert diagnostic_dispatch_refusal(narrow, _granted(narrow)) == (
        "diagnostic_selection_exceeds_ceiling"
    )


def test_activating_the_process_is_never_part_of_the_ordinary_selection(profiles):
    """Only the enable step and its reading are separately authorized."""
    dhcp = profiles[0]
    assert [item.id for item in dhcp.steps if item.separately_authorized] == [
        "D3-a",
        "D3-b",
    ]
    assert [item.id for item in dhcp.steps if item.effect is DiagnosticEffect.ACTIVATE]
    authorization = _granted(dhcp)
    assert "D3-a" not in authorization.step_ids


# -- budget arithmetic, finalization included ----------------------------------


def test_the_dhcp_sequence_fits_its_proposed_ceiling_with_its_reserve():
    """43 of 60, or 41 without the activation, with the 11-operation reserve."""
    profile = d_dhcp_profile(build=Q3_PACKET_TRACER_BUILD, channels=CHANNELS)
    steps = sum(item.operations for item in profile.steps)
    assert steps == 32
    assert profile.budget.reserve_operations == Q3.reserve_operations == 11
    assert profile.worst_case_operations() == steps + 11 == 43
    without_activation = tuple(
        item.id for item in profile.steps if not item.separately_authorized
    )
    assert profile.worst_case_operations(without_activation) == 41
    assert profile.fits and profile.budget.max_operations == 60


def test_the_web_sequence_fits_its_proposed_ceiling_with_its_reserve():
    """47 of 60 with the 10-operation reserve, both fetches included."""
    profile = d_web_profile(build=Q3_PACKET_TRACER_BUILD, channels=CHANNELS)
    steps = sum(item.operations for item in profile.steps)
    assert steps == 37
    assert profile.budget.reserve_operations == 10
    assert profile.worst_case_operations() == steps + 10 == 47
    assert profile.fits and profile.budget.max_operations == 60
    # One fetch is five operations: start, two inspections, the late control
    # read and the release, which is the existing four plus the new control.
    assert (
        sum(profile.step(item).operations for item in ("W2-a", "W2-b", "W2-c", "W2-d"))
        == 5
    )
    assert profile.step("W3").operations == 5


def test_no_step_of_either_profile_is_unaccounted_or_untargeted(profiles):
    """Every step names its effect, its targets, what it retains and its cost."""
    for profile in profiles:
        assert len(set(profile.step_ids)) == len(profile.step_ids)
        for step in profile.steps:
            assert step.targets and step.retains and step.purpose
            assert step.operations >= 1
            assert set(step.blocked_by) <= set(profile.seam_ids)


# -- D-DHCP: the generated sequence and its declared seam ----------------------


def test_the_static_only_projection_configures_the_server_and_no_client(contract):
    """D1-a touches the server's address only: no client enters DHCP mode."""
    projected = d_dhcp_static_only_plan(contract.configuration_plan)
    assert [item.device_name for item in projected.actions] == [Q3_SERVER]
    assert [item.action_type.value for item in projected.actions] == [
        "set_endpoint_static"
    ]
    assert [item.depends_on for item in projected.actions] == [[]]
    assert [item.apply_dependencies for item in projected.actions] == [[]]
    assert "set_endpoint_dhcp" not in {
        item.action_type.value for item in projected.actions
    }
    assert projected.semantic_hash
    assert projected.semantic_hash != contract.configuration_plan.semantic_hash
    assert projected.source_topology_hash == (
        contract.configuration_plan.source_topology_hash
    )


def test_the_compiled_pool_action_really_does_depend_on_the_enable_action(contract):
    """The seam is a fact about the compiled plan, not an assumption."""
    enable = next(
        item
        for item in contract.service_plan.actions
        if isinstance(item, EnableServerDhcp)
    )
    pool = next(
        item
        for item in contract.service_plan.actions
        if isinstance(item, ConfigureServerDhcpPool)
    )
    assert enable.id in pool.depends_on
    assert enable.id in pool.apply_dependencies


def test_the_pool_only_projection_names_the_dependency_it_rewrites(contract):
    """D2-a is blocked on exactly the dependency the projection removed."""
    projected, rewritten = d_dhcp_pool_only_plan(contract.service_plan)
    enable = next(
        item
        for item in contract.service_plan.actions
        if isinstance(item, EnableServerDhcp)
    )
    assert rewritten == (enable.id,)
    assert [item.action_type.value for item in projected.actions] == [
        "configure_server_dhcp_pool"
    ]
    assert [item.depends_on for item in projected.actions] == [[]]
    assert [item.apply_dependencies for item in projected.actions] == [[]]
    assert [item.kind for item in projected.verification_expectations] == [
        ServiceVerificationKind.DHCP_SERVER_STATE
    ]
    profile = d_dhcp_profile(build=Q3_PACKET_TRACER_BUILD, channels=CHANNELS)
    assert profile.step("D2-a").blocked_by == (POOL_BEFORE_ENABLE,)
    seam = next(item for item in profile.seams if item.id == POOL_BEFORE_ENABLE)
    assert "depends_on" in seam.contract


def test_the_enable_only_projection_carries_no_product_read_back(contract):
    """D3-a costs one operation because the read-back belongs to the pool row."""
    projected = d_dhcp_enable_only_plan(contract.service_plan)
    assert [item.action_type.value for item in projected.actions] == [
        "enable_server_dhcp"
    ]
    assert projected.verification_expectations == []
    profile = d_dhcp_profile(build=Q3_PACKET_TRACER_BUILD, channels=CHANNELS)
    assert profile.step("D3-a").operations == 1
    assert "enabled_boolean" in profile.step("D3-b").retains


def test_the_dhcp_sequence_acquires_nothing_and_never_writes_the_default():
    """Every excluded effect stays excluded, and no step targets the default."""
    profile = d_dhcp_profile(build=Q3_PACKET_TRACER_BUILD, channels=CHANNELS)
    targets = {item for step in profile.steps for item in step.targets}
    assert not [item for item in targets if "serverPool" in item]
    assert not [item for item in targets if "AcquireDhcpLease" in item]
    assert DiagnosticEffect.REQUEST not in {item.effect for item in profile.steps}
    assert "client acquisition" in profile.excluded
    assert "DHCP event observer registration" in profile.excluded
    assert "default-pool setter, removal or reset" in profile.excluded


def test_the_dhcp_readings_bracket_every_effect_of_the_sequence():
    """A transition falls between two adjacent readings, never across a phase."""
    profile = d_dhcp_profile(build=Q3_PACKET_TRACER_BUILD, channels=CHANNELS)
    order = [
        (item.id, item.effect)
        for item in profile.steps
        if (
            item.effect
            in (
                DiagnosticEffect.OBSERVE,
                DiagnosticEffect.CONFIGURE,
                DiagnosticEffect.ACTIVATE,
            )
            and "native_default" in item.purpose
        )
        or item.effect in (DiagnosticEffect.CONFIGURE, DiagnosticEffect.ACTIVATE)
    ]
    assert [item[0] for item in order] == [
        "D0-a",
        "D1-a",
        "D1-b",
        "D2-a",
        "D2-b",
        "D3-a",
        "D3-b",
        "D4",
    ]


# -- D-WEB: the narrow diagnostic and the vendor reference ---------------------


def test_the_web_comparison_is_the_same_fixture_under_two_client_modes():
    """The control is a mode comparison, not a longer timeout."""
    profile = d_web_profile(build=Q3_PACKET_TRACER_BUILD, channels=CHANNELS)
    assert profile.step("W2-a").targets == ("__MCP_E6Q_PC1:HttpBackgroundClient:http",)
    assert profile.step("W3").targets == ("__MCP_E6Q_PC1:HttpBackgroundClient:https",)
    assert "unconditional waits" in profile.excluded
    assert "automatic second fetches" in profile.excluded
    assert "PortFast or any forwarding change" in profile.excluded
    assert "switching the transport" in profile.excluded
    assert "unqualified event registration" in profile.excluded
    assert any(
        "timeout is never a negative listener claim" in item
        for item in profile.limitations
    )
    assert any("no TLS property is asserted" in item for item in profile.limitations)


def test_the_web_record_retains_exactly_what_the_reader_observed():
    """Every required field is named, and no field is inferred."""
    profile = d_web_profile(build=Q3_PACKET_TRACER_BUILD, channels=CHANNELS)
    retained = {item for step in profile.steps for item in step.retains}
    assert {
        "http_enabled",
        "https_enabled",
        "http_port_number",
        "https_port_number",
        "selected_url",
        "selected_path",
        "client_mode",
        "owner_device",
        "content_before",
        "marker_in_content_before",
        "go_result",
        "inspection_offset_seconds",
        "remaining_operations",
        "remaining_seconds",
        "changed_after_deadline",
        "found",
        "deleted",
        "present_after",
    } <= retained


def test_every_previously_unused_vendor_member_has_a_disposition():
    """Each documented member is read, deliberately unused, or refused."""
    profile = d_web_profile(build=Q3_PACKET_TRACER_BUILD, channels=CHANNELS)
    findings = {item.member: item for item in profile.vendor_findings}
    assert {item.disposition for item in profile.vendor_findings} <= {
        "read",
        "unused",
        "refused",
    }
    assert findings["HttpClient::isHttps()"].disposition == "read"
    assert findings["HttpClient::getOwnerDevice()"].disposition == "read"
    assert findings["HttpServer::getPortNumber()"].disposition == "read"
    assert findings["HttpsServer::isHttpsEnabled()"].disposition == "read"
    # Signatures without documented semantics, events without a documented
    # result type and credential readers are refused, not guessed at.
    for member in (
        "HttpClient::http_get/http_post/http_put/http_delete",
        "HttpClient::onStart/onDone",
        "HttpServer::onRequest(string, TcpConnection)",
        "HttpServer::getUsername/getPassword",
    ):
        assert findings[member].disposition == "refused"
        assert findings[member].reason
    assert (
        "HttpResponseType has no page"
        in findings["HttpClient::onStart/onDone"].reference
    )


def test_the_web_profile_states_what_it_cannot_separate():
    """Only layer-1 and layer-2 readiness is observable, and it says so."""
    profile = d_web_profile(build=Q3_PACKET_TRACER_BUILD, channels=CHANNELS)
    assert any("layer-1 and layer-2 readiness" in item for item in profile.limitations)
    assert any(
        "network path and the listener cannot be separated" in item
        for item in profile.limitations
    )


def test_every_web_seam_names_a_minimal_extension_not_a_copied_writer():
    """Each seam says what exists, what is needed and the smallest change."""
    profile = d_web_profile(build=Q3_PACKET_TRACER_BUILD, channels=CHANNELS)
    assert len(profile.seams) == 4
    for seam in profile.seams:
        assert seam.contract and seam.current and seam.required
        assert seam.minimal_extension
    blocked = {item for step in profile.steps for item in step.blocked_by}
    assert blocked == set(profile.seam_ids)
