"""CP-SCALE canonical demand and exact semantic realization."""

from __future__ import annotations

from collections import Counter

from src.packet_tracer_mcp.domain.enterprise.models.compilation import (
    CompilationIssueCode,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.scenarios.cp_scale import (
    CP_SCALE_ACCESS_POINT_COUNT,
    CP_SCALE_SITE_WORKLOAD_COUNTS,
    CP_SCALE_WORKLOAD_COUNTS,
    CPScalePoint,
    cp_scale_intent,
    cp_scale_intent_for,
)
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import (
    EnterpriseDesigner,
)
from src.packet_tracer_mcp.domain.enterprise.services.endpoint_expander import (
    EndpointGroupExpander,
)
from src.packet_tracer_mcp.domain.enterprise.services.naming import (
    DeterministicNamingService,
)
from src.packet_tracer_mcp.domain.enterprise.services.segment_assignment import (
    SegmentAssignmentPolicy,
)
from src.packet_tracer_mcp.domain.enterprise.models.segments import SegmentRole
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_topology import (
    PacketTracerTopologyCatalogAdapter,
)


_IOT_ROLES = {
    DeviceRole.WEBCAM,
    DeviceRole.SMOKE_DETECTOR,
    DeviceRole.MOTION_DETECTOR,
    DeviceRole.HUMITURE_MONITOR,
    DeviceRole.TEMPERATURE_MONITOR,
}


def _requirements(intent):
    for site in intent.sites:
        yield from site.endpoints
        for building in site.buildings:
            for floor in building.floors:
                for zone in floor.zones:
                    for group in zone.endpoint_groups:
                        yield from group.requirements


def _counts(intent, *, include_access_points: bool = False) -> Counter[DeviceRole]:
    return Counter({
        role: sum(
            item.count for item in _requirements(intent)
            if item.role is role
        )
        for role in DeviceRole
        if include_access_points or role is not DeviceRole.ACCESS_POINT
    })


def test_canonical_intent_preserves_exact_branch_and_global_workload_counts():
    intent = cp_scale_intent()

    assert intent.default_growth_percent == 20
    assert len(intent.sites) == 3
    assert _counts(intent) == Counter(CP_SCALE_WORKLOAD_COUNTS)
    assert sum(CP_SCALE_WORKLOAD_COUNTS.values()) == 279
    assert sum(
        item.count for item in _requirements(intent)
        if item.role is DeviceRole.ACCESS_POINT
    ) == CP_SCALE_ACCESS_POINT_COUNT == 17

    for site in intent.sites:
        assert _counts(intent.model_copy(update={"sites": [site]})) == Counter(
            CP_SCALE_SITE_WORKLOAD_COUNTS[site.name]
        )


def test_scale_points_are_monotonic_slices_of_the_one_canonical_intent():
    expected = {
        CPScalePoint.A: (65, 3, 1),
        CPScalePoint.B: (118, 6, 1),
        CPScalePoint.C: (217, 12, 1),
        CPScalePoint.D: (279, 17, 3),
    }

    for point, (workload, access_points, sites) in expected.items():
        intent = cp_scale_intent_for(point)
        assert sum(_counts(intent).values()) == workload
        assert sum(
            item.count for item in _requirements(intent)
            if item.role is DeviceRole.ACCESS_POINT
        ) == access_points
        assert len(intent.sites) == sites


def test_full_scenario_declares_a_serial_triangle_and_three_branch_covering_flows():
    intent = cp_scale_intent()
    site_ids = {"large-branch", "multilayer-branch", "small-branch"}
    wan_pairs = {
        tuple(sorted((site.name.casefold().replace(" ", "-"), uplink.target_site_id)))
        for site in intent.sites
        for uplink in site.uplinks
    }

    assert wan_pairs == {
        ("large-branch", "multilayer-branch"),
        ("large-branch", "small-branch"),
        ("multilayer-branch", "small-branch"),
    }
    assert all(uplink.media.value == "serial" for site in intent.sites for uplink in site.uplinks)
    assert len(intent.traffic_flows) == 3
    assert {item.source_site_id for item in intent.traffic_flows} == site_ids
    assert {item.destination_site_id for item in intent.traffic_flows} == site_ids


def test_iot_semantics_are_wireless_and_segmented_without_claiming_association():
    intent = cp_scale_intent()
    policy = SegmentAssignmentPolicy()
    iot = [item for item in _requirements(intent) if item.role in _IOT_ROLES]

    assert iot
    assert all(item.wireless and not item.wired for item in iot)
    assert all(policy.segment_for(item) is SegmentRole.CCTV for item in iot)
    assert all(item.metadata.get("wireless_association") == "unqualified" for item in iot)
    assert all(
        item.wired and not item.wireless
        for item in _requirements(intent)
        if item.role in {DeviceRole.PRINTER, DeviceRole.LAPTOP, DeviceRole.ACCESS_POINT}
    )


def test_design_and_expansion_keep_exact_roles_and_unique_names():
    designed = EnterpriseDesigner().design(cp_scale_intent())

    assert designed.validation.is_valid, designed.validation.error_messages()
    assert designed.plan is not None
    expanded = EndpointGroupExpander().expand(
        designed.plan, DeterministicNamingService(),
    )
    role_counts = Counter(item.role for item in expanded)
    assert sum(role_counts.values()) == 279 + 17
    assert role_counts[DeviceRole.WEBCAM] == 26
    assert role_counts[DeviceRole.SMOKE_DETECTOR] == 42
    assert len({item.id for item in expanded}) == len(expanded)
    assert len({item.name for item in expanded}) == len(expanded)


def test_generic_thing_is_an_explicit_substitution_not_an_exact_sensor_model():
    profile = PacketTracerTopologyCatalogAdapter().compilation_profile()
    thing = profile.model_by_name("Thing")

    assert thing is not None and thing.generic
    assert {
        profile.endpoint_role_models[role] for role in _IOT_ROLES
    } == {"Thing"}
    assert CompilationIssueCode.ENDPOINT_MODEL_GENERIC.value == "ENDPOINT_MODEL_GENERIC"

