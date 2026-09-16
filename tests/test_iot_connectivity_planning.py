"""The same wireless contract at three topology sizes.

The assertions are invariants: how endpoints, clusters, candidates and segments
relate. None of them depends on a particular count, name or VLAN, so a topology
can grow without the test needing to grow with it.
"""

from __future__ import annotations

from collections import Counter

import pytest

from src.packet_tracer_mcp.application.use_cases.plan_iot_connectivity import (
    IoTConnectivityPolicy,
    plan_iot_connectivity,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.models.segments import SegmentRole
from src.packet_tracer_mcp.domain.enterprise.models.wireless_connectivity import (
    AccessPointOwnership,
    AccessPointSelection,
    IoTFunction,
    WirelessClusterScope,
    WirelessSecurityMode,
    WirelessServiceSetIntent,
)
from tests.support.iot_connectivity_scenarios import (
    advanced_topology,
    endpoint,
    medium_topology,
    segments_for,
    simple_topology,
)


ALL_TOPOLOGIES = {
    "simple": simple_topology,
    "medium": medium_topology,
    "advanced": advanced_topology,
}


@pytest.mark.parametrize("name", sorted(ALL_TOPOLOGIES))
def test_every_topology_size_satisfies_the_same_plan_contract(name):
    endpoints = ALL_TOPOLOGIES[name]()

    result = plan_iot_connectivity(endpoints)

    assert result.is_valid, result.validation.error_messages()
    assert result.plan.unclustered_endpoint_ids == ()
    wireless_ids = {item.id for item in endpoints if item.wireless}
    planned_ids = {
        member.endpoint_id
        for cluster in result.plan.clusters
        for member in cluster.members
    }
    assert planned_ids == wireless_ids
    assert {item.endpoint_id for item in result.plan.association_intents} == wireless_ids
    assert {item.endpoint_id for item in result.plan.iot_functions} == wireless_ids
    for cluster in result.plan.clusters:
        assert cluster.has_candidate
        assert cluster.segment.segment_id
        assert all(
            member.segment_id == cluster.segment.segment_id
            for member in cluster.members
        )


def test_simple_topology_produces_one_cluster_owning_its_access_point():
    result = plan_iot_connectivity(simple_topology())

    (cluster,) = result.plan.clusters
    (candidate,) = cluster.candidates
    assert candidate.ownership is AccessPointOwnership.CLUSTER_OWNED
    assert cluster.scope is WirelessClusterScope.ZONE
    (member,) = cluster.members
    assert member.iot_function is IoTFunction.SMOKE_DETECTION


def test_medium_topology_keeps_every_access_point_as_a_candidate():
    endpoints = medium_topology()

    result = plan_iot_connectivity(endpoints)

    access_point_ids = {
        item.id for item in endpoints if item.role is DeviceRole.ACCESS_POINT
    }
    (cluster,) = result.plan.clusters
    assert set(cluster.candidate_ids) == access_point_ids
    assert len(cluster.members) == sum(1 for item in endpoints if item.wireless)
    # Several IoT roles share one segment, so they share one cluster.
    assert {member.role for member in cluster.members} == {
        DeviceRole.WEBCAM, DeviceRole.SMOKE_DETECTOR, DeviceRole.MOTION_DETECTOR,
    }


def test_medium_topology_never_pins_an_endpoint_to_one_access_point():
    result = plan_iot_connectivity(medium_topology())

    for intent in result.plan.association_intents:
        assert intent.selection is AccessPointSelection.BACKEND_SELECTED
        assert intent.pinned_access_point_id == ""
        assert len(intent.candidate_access_point_ids) > 1


def test_advanced_topology_separates_sites_zones_and_segment_roles():
    endpoints = advanced_topology()

    result = plan_iot_connectivity(endpoints)

    assert result.is_valid, result.validation.error_messages()
    assert len({cluster.site_id for cluster in result.plan.clusters}) > 1
    assert len({cluster.zone_id for cluster in result.plan.clusters}) > 1
    # A wireless laptop belongs to the corporate wireless segment, so it forms a
    # second cluster inside a zone that already has an IoT one.
    by_zone = Counter(cluster.zone_id for cluster in result.plan.clusters)
    split_zone = max(by_zone, key=lambda key: (by_zone[key], key))
    assert by_zone[split_zone] > 1
    roles = {
        cluster.segment.role
        for cluster in result.plan.clusters if cluster.zone_id == split_zone
    }
    assert roles == {SegmentRole.CCTV, SegmentRole.WIRELESS_CORPORATE}
    for cluster in result.plan.clusters:
        for candidate in cluster.candidates:
            assert candidate.site_id == cluster.site_id


def test_a_shared_access_point_is_marked_shared_not_owned():
    endpoints = advanced_topology()

    result = plan_iot_connectivity(endpoints)

    shared = [
        candidate
        for cluster in result.plan.clusters
        for candidate in cluster.candidates
        if candidate.ownership is AccessPointOwnership.SHARED
    ]
    assert shared, "a zone with two clusters shares its access points"
    for cluster in result.plan.clusters:
        owned = [
            item for item in cluster.candidates
            if item.ownership is AccessPointOwnership.CLUSTER_OWNED
        ]
        if owned:
            assert len([
                other for other in result.plan.clusters
                if other.zone_id == cluster.zone_id
            ]) == 1


def test_a_site_level_access_point_is_an_external_candidate():
    endpoints = simple_topology()
    endpoints.append(endpoint(
        DeviceRole.ACCESS_POINT, 9, site_id="site/lab", zone_id="",
    ))

    result = plan_iot_connectivity(endpoints)

    (cluster,) = result.plan.clusters
    ownerships = {
        candidate.access_point_id: candidate.ownership
        for candidate in cluster.candidates
    }
    assert AccessPointOwnership.EXTERNAL in ownerships.values()
    assert len(ownerships) == 2


def test_widening_the_scope_merges_zones_without_changing_the_contract():
    endpoints = advanced_topology()

    zoned = plan_iot_connectivity(endpoints)
    sited = plan_iot_connectivity(
        endpoints,
        policy=IoTConnectivityPolicy(scope=WirelessClusterScope.SITE),
    )

    assert sited.is_valid, sited.validation.error_messages()
    assert len(sited.plan.clusters) < len(zoned.plan.clusters)
    assert sited.plan.member_count == zoned.plan.member_count
    assert all(cluster.zone_id == "" for cluster in sited.plan.clusters)


def test_declared_segments_carry_vlan_and_subnet_into_the_cluster():
    endpoints = simple_topology()
    segments = segments_for("site/lab", "10.20.30.0/24", vlan_id=412)

    result = plan_iot_connectivity(endpoints, segments=segments)

    (cluster,) = result.plan.clusters
    assert cluster.segment.vlan_id == 412
    assert cluster.segment.subnet == "10.20.30.0/24"
    assert cluster.segment.contains("10.20.30.44") is True
    assert cluster.segment.contains("10.99.0.1") is False


def test_a_plan_without_ipam_still_names_its_segment_and_invents_no_numbers():
    result = plan_iot_connectivity(simple_topology())

    (cluster,) = result.plan.clusters
    assert cluster.segment.segment_id
    assert cluster.segment.vlan_id is None
    assert cluster.segment.subnet == ""
    assert cluster.segment.contains("10.0.0.1") is None


def test_an_endpoint_outside_the_cluster_scope_is_reported_not_dropped():
    endpoints = simple_topology()
    endpoints.append(endpoint(
        DeviceRole.WEBCAM, 7, site_id="site/lab", zone_id="",
    ))

    result = plan_iot_connectivity(endpoints)

    assert not result.is_valid
    assert result.plan.unclustered_endpoint_ids == ("endpoint/site/lab/webcam/007",)


def test_a_cluster_without_a_candidate_access_point_is_refused_by_default():
    endpoints = [item for item in simple_topology() if item.wireless]

    refused = plan_iot_connectivity(endpoints)
    accepted = plan_iot_connectivity(
        endpoints,
        policy=IoTConnectivityPolicy(require_candidate_access_point=False),
    )

    assert not refused.is_valid
    assert accepted.is_valid
    assert accepted.validation.warnings


def test_pinning_is_opt_in_and_has_to_name_a_cluster_candidate():
    endpoints = medium_topology()
    target = next(item for item in endpoints if item.wireless)
    access_point = next(
        item.id for item in endpoints if item.role is DeviceRole.ACCESS_POINT
    )

    valid = plan_iot_connectivity(
        endpoints,
        policy=IoTConnectivityPolicy(
            pinned_access_points={target.id: access_point},
        ),
    )
    invalid = plan_iot_connectivity(
        endpoints,
        policy=IoTConnectivityPolicy(
            pinned_access_points={target.id: "endpoint/elsewhere/access_point/001"},
        ),
    )

    intent = valid.plan.intent_for(target.id)
    assert intent.selection is AccessPointSelection.PINNED
    assert intent.pinned_access_point_id == access_point
    assert valid.validation.is_valid
    assert valid.validation.warnings, "narrowing the backend choice is worth saying"
    assert not invalid.validation.is_valid


def test_a_custom_service_set_reaches_every_member_of_its_segment_role():
    corporate = WirelessServiceSetIntent(
        ssid="plant-iot", security_mode=WirelessSecurityMode.WPA2_PSK,
    )

    result = plan_iot_connectivity(
        advanced_topology(),
        policy=IoTConnectivityPolicy(service_sets={SegmentRole.CCTV: corporate}),
    )

    for cluster in result.plan.clusters:
        expected = corporate if cluster.segment.role is SegmentRole.CCTV else None
        if expected is not None:
            assert cluster.service_set == expected
            assert not cluster.service_set.uses_backend_default
        else:
            assert cluster.service_set.uses_backend_default
        for member in cluster.members:
            assert result.plan.intent_for(member.endpoint_id).service_set == cluster.service_set


def test_humiture_and_temperature_need_no_new_architecture():
    """The roles enter through the same flag and get their declared function."""
    endpoints = advanced_topology()

    result = plan_iot_connectivity(endpoints)

    declared = {item.endpoint_id: item.function for item in result.plan.iot_functions}
    humiture = next(
        item.id for item in endpoints if item.role is DeviceRole.HUMITURE_MONITOR
    )
    laptop = next(item.id for item in endpoints if item.role is DeviceRole.LAPTOP)
    assert declared[humiture] is IoTFunction.ENVIRONMENTAL_SENSING
    assert declared[laptop] is IoTFunction.NONE


def test_planning_is_deterministic():
    first = plan_iot_connectivity(advanced_topology()).plan
    second = plan_iot_connectivity(advanced_topology()).plan

    assert first == second
