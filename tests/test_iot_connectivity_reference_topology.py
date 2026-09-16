"""The governed reference topology as an advanced fixture, nothing more.

It is used here only to show that an existing large enterprise design flows
through the same contract as a one-access-point lab. Nothing in this module
reads, writes or reopens its closure, and the assertions are derived from the
design itself rather than from any recorded number.
"""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.plan_iot_connectivity import (
    IoTConnectivityClosure,
    plan_iot_connectivity,
    qualify_iot_connectivity,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.models.wireless_connectivity import (
    AccessPointSelection,
    IoTFunction,
    WirelessAssociationState,
)
from src.packet_tracer_mcp.domain.enterprise.scenarios.cp_scale import cp_scale_intent
from src.packet_tracer_mcp.domain.enterprise.services.endpoint_expander import (
    EndpointGroupExpander,
)
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import (
    EnterpriseDesigner,
)
from src.packet_tracer_mcp.domain.enterprise.services.naming import (
    DeterministicNamingService,
)
from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
)
from src.packet_tracer_mcp.infrastructure.catalog.wireless_capabilities import (
    packet_tracer_wireless_capability_audit,
)


def _reference():
    designed = EnterpriseDesigner().design(cp_scale_intent())
    assert designed.validation.is_valid, designed.validation.error_messages()
    assert designed.plan is not None
    endpoints = EndpointGroupExpander().expand(
        designed.plan, DeterministicNamingService(),
    )
    segments = [item for site in designed.plan.sites for item in site.segments]
    return endpoints, segments


def test_an_existing_enterprise_design_flows_through_the_same_contract():
    endpoints, segments = _reference()

    result = plan_iot_connectivity(endpoints, segments=segments)

    assert result.is_valid, result.validation.error_messages()
    wireless_ids = {item.id for item in endpoints if item.wireless}
    assert wireless_ids, "the reference design carries wireless endpoints"
    assert {
        member.endpoint_id
        for cluster in result.plan.clusters
        for member in cluster.members
    } == wireless_ids
    assert len(result.plan.clusters) > 1
    for cluster in result.plan.clusters:
        assert cluster.has_candidate
        assert all(
            candidate.site_id == cluster.site_id
            for candidate in cluster.candidates
        )


def test_every_reference_access_point_stays_a_candidate_of_its_own_zone():
    endpoints, segments = _reference()
    access_points = {
        item.id: item for item in endpoints
        if item.role is DeviceRole.ACCESS_POINT
    }

    result = plan_iot_connectivity(endpoints, segments=segments)

    for cluster in result.plan.clusters:
        for candidate in cluster.candidates:
            planned = access_points[candidate.access_point_id]
            assert planned.site_id == cluster.site_id
            if candidate.zone_id:
                assert candidate.zone_id == cluster.zone_id


def test_the_reference_topology_pins_nothing_and_declares_every_function():
    endpoints, segments = _reference()

    result = plan_iot_connectivity(endpoints, segments=segments)

    assert all(
        intent.selection is AccessPointSelection.BACKEND_SELECTED
        for intent in result.plan.association_intents
    )
    functions = {item.function for item in result.plan.iot_functions}
    assert IoTFunction.UNCLASSIFIED not in functions
    assert functions <= set(IoTFunction)


def test_the_reference_topology_reaches_no_further_than_a_planned_state():
    endpoints, segments = _reference()
    plan = plan_iot_connectivity(endpoints, segments=segments).plan

    qualification = qualify_iot_connectivity(
        plan, audit=packet_tracer_wireless_capability_audit(MEASURED_BACKEND_VERSION),
    )

    assert qualification.closure is IoTConnectivityClosure.PLAN_ONLY
    assert set(qualification.association_summary) == {
        WirelessAssociationState.PLANNED.value,
    }
