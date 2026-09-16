"""Derivation of wireless clusters from already expanded endpoints.

Pure and deterministic: the same endpoints always produce the same clusters,
candidates and intents. The planner decides nothing about acceptance and knows
no backend; both belong one layer up.

The membership criterion is the endpoint intent itself (``wireless``), not a
list of IoT roles. A smoke detector, a webcam and a wireless laptop enter the
same way, and a humiture or temperature monitor needs no new code to join.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from ..models.roles import DeviceRole
from ..models.segments import NetworkSegment, SegmentRole
from ..models.wireless_connectivity import (
    AccessPointCandidate,
    AccessPointOwnership,
    AccessPointSelection,
    IntendedNetworkSegment,
    IoTFunctionDeclaration,
    WirelessAssociationIntent,
    WirelessCluster,
    WirelessClusterScope,
    WirelessConnectivityPlan,
    WirelessEndpointMembership,
    WirelessServiceSetIntent,
    iot_function_for_role,
)
from .endpoint_expander import ExpandedEndpoint
from .naming import DeterministicNamingService
from .segment_assignment import SegmentAssignmentPolicy


_SCOPE_FIELDS: Mapping[WirelessClusterScope, tuple[str, ...]] = {
    WirelessClusterScope.SITE: ("site_id",),
    WirelessClusterScope.BUILDING: ("site_id", "building_id"),
    WirelessClusterScope.FLOOR: ("site_id", "building_id", "floor_id"),
    WirelessClusterScope.ZONE: ("site_id", "building_id", "floor_id", "zone_id"),
}


class WirelessClusterPlanner:
    """Group wireless endpoints and their candidate access points."""

    def __init__(
        self,
        segment_policy: SegmentAssignmentPolicy | None = None,
        naming: DeterministicNamingService | None = None,
    ) -> None:
        self._segments = segment_policy or SegmentAssignmentPolicy()
        self._naming = naming or DeterministicNamingService()

    def plan(
        self,
        endpoints: Sequence[ExpandedEndpoint],
        *,
        scope: WirelessClusterScope = WirelessClusterScope.ZONE,
        segments: Sequence[NetworkSegment] = (),
        service_set: WirelessServiceSetIntent = WirelessServiceSetIntent(),
        service_sets: Mapping[SegmentRole, WirelessServiceSetIntent] | None = None,
        pinned_access_points: Mapping[str, str] | None = None,
    ) -> WirelessConnectivityPlan:
        members = [item for item in endpoints if item.wireless]
        access_points = [
            item for item in endpoints if item.role is DeviceRole.ACCESS_POINT
        ]
        declared_segments = self._segment_index(segments)
        pinned = dict(pinned_access_points or {})

        grouped: dict[tuple[str, SegmentRole], list[ExpandedEndpoint]] = defaultdict(list)
        unclustered: list[str] = []
        for endpoint in sorted(members, key=lambda item: item.id):
            key = self._scope_key(endpoint, scope)
            if key is None:
                unclustered.append(endpoint.id)
                continue
            segment_role = self._segments.segment_for_role(
                endpoint.role,
                wireless=endpoint.wireless,
                declared=endpoint.segment_role,
            )
            grouped[(key, segment_role)].append(endpoint)

        clusters_per_scope: dict[str, int] = defaultdict(int)
        for scope_key, _ in grouped:
            clusters_per_scope[scope_key] += 1

        clusters: list[WirelessCluster] = []
        intents: list[WirelessAssociationIntent] = []
        functions: list[IoTFunctionDeclaration] = []
        for (scope_key, segment_role), grouped_endpoints in sorted(
            grouped.items(), key=lambda item: (item[0][0], item[0][1].value),
        ):
            anchor = grouped_endpoints[0]
            segment = self._intended_segment(
                anchor.site_id, segment_role, declared_segments,
            )
            cluster_id = self._naming.wireless_cluster_id(
                scope.value, scope_key, segment_role.value,
            )
            candidates = self._candidates(
                access_points,
                scope=scope,
                scope_key=scope_key,
                site_id=anchor.site_id,
                shared=clusters_per_scope[scope_key] > 1,
            )
            cluster_service_set = (service_sets or {}).get(segment_role, service_set)
            membership = tuple(
                WirelessEndpointMembership(
                    endpoint_id=endpoint.id,
                    name=endpoint.name,
                    role=endpoint.role,
                    cluster_id=cluster_id,
                    segment_id=segment.segment_id,
                    iot_function=iot_function_for_role(endpoint.role),
                    addressing_preference=endpoint.addressing_preference,
                    site_id=endpoint.site_id,
                    building_id=endpoint.building_id,
                    floor_id=endpoint.floor_id,
                    zone_id=endpoint.zone_id,
                    source_group=endpoint.source_group,
                    metadata=dict(endpoint.requirement_metadata),
                )
                for endpoint in grouped_endpoints
            )
            clusters.append(WirelessCluster(
                cluster_id=cluster_id,
                name=self._naming.wireless_cluster_name(scope_key, segment_role.value),
                scope=scope,
                site_id=anchor.site_id,
                building_id=anchor.building_id if scope is not WirelessClusterScope.SITE else "",
                floor_id=(
                    anchor.floor_id
                    if scope in {WirelessClusterScope.FLOOR, WirelessClusterScope.ZONE}
                    else ""
                ),
                zone_id=anchor.zone_id if scope is WirelessClusterScope.ZONE else "",
                segment=segment,
                service_set=cluster_service_set,
                candidates=candidates,
                members=membership,
            ))
            candidate_ids = tuple(item.access_point_id for item in candidates)
            for endpoint in grouped_endpoints:
                pinned_id = pinned.get(endpoint.id, "")
                intents.append(WirelessAssociationIntent(
                    endpoint_id=endpoint.id,
                    cluster_id=cluster_id,
                    service_set=cluster_service_set,
                    selection=(
                        AccessPointSelection.PINNED
                        if pinned_id else AccessPointSelection.BACKEND_SELECTED
                    ),
                    candidate_access_point_ids=candidate_ids,
                    pinned_access_point_id=pinned_id,
                    addressing_preference=endpoint.addressing_preference,
                ))
                functions.append(IoTFunctionDeclaration(
                    endpoint_id=endpoint.id,
                    function=iot_function_for_role(endpoint.role),
                ))

        return WirelessConnectivityPlan(
            clusters=tuple(clusters),
            association_intents=tuple(
                sorted(intents, key=lambda item: item.endpoint_id)
            ),
            iot_functions=tuple(
                sorted(functions, key=lambda item: item.endpoint_id)
            ),
            unclustered_endpoint_ids=tuple(sorted(unclustered)),
            scope=scope,
        )

    @staticmethod
    def _scope_key(
        endpoint: ExpandedEndpoint, scope: WirelessClusterScope,
    ) -> str | None:
        """``None`` when the endpoint is not placed deeply enough to be scoped."""
        values = [getattr(endpoint, name) for name in _SCOPE_FIELDS[scope]]
        if not values[0] or not values[-1]:
            return None
        return "/".join(value for value in values if value)

    @staticmethod
    def _access_point_key(
        endpoint: ExpandedEndpoint, scope: WirelessClusterScope,
    ) -> str | None:
        return WirelessClusterPlanner._scope_key(endpoint, scope)

    @staticmethod
    def _candidates(
        access_points: Sequence[ExpandedEndpoint],
        *,
        scope: WirelessClusterScope,
        scope_key: str,
        site_id: str,
        shared: bool,
    ) -> tuple[AccessPointCandidate, ...]:
        """In-scope access points first, then the site ones placed less deeply.

        An access point that the hierarchy never placed at the cluster depth is
        still a candidate — refusing it would leave a site-level access point
        unusable — but it is marked EXTERNAL so nothing reads it as dedicated.
        """
        candidates: list[AccessPointCandidate] = []
        for endpoint in sorted(access_points, key=lambda item: item.id):
            key = WirelessClusterPlanner._access_point_key(endpoint, scope)
            if key == scope_key:
                ownership = (
                    AccessPointOwnership.SHARED
                    if shared else AccessPointOwnership.CLUSTER_OWNED
                )
            elif key is None and endpoint.site_id == site_id:
                ownership = AccessPointOwnership.EXTERNAL
            else:
                continue
            candidates.append(AccessPointCandidate(
                access_point_id=endpoint.id,
                name=endpoint.name,
                site_id=endpoint.site_id,
                building_id=endpoint.building_id,
                floor_id=endpoint.floor_id,
                zone_id=endpoint.zone_id,
                ownership=ownership,
            ))
        return tuple(candidates)

    @staticmethod
    def _segment_index(
        segments: Sequence[NetworkSegment],
    ) -> Mapping[tuple[str, SegmentRole], NetworkSegment]:
        return {(item.site, item.role): item for item in segments}

    @staticmethod
    def _intended_segment(
        site_id: str,
        role: SegmentRole,
        declared: Mapping[tuple[str, SegmentRole], NetworkSegment],
    ) -> IntendedNetworkSegment:
        segment = declared.get((site_id, role))
        if segment is None:
            # No numbers are invented here: a plan that has not reached IPAM
            # still names its segment, and VLAN/subnet stay absent.
            return IntendedNetworkSegment(
                segment_id=f"{site_id}-{role.value}", role=role,
            )
        return IntendedNetworkSegment(
            segment_id=segment.name,
            role=segment.role,
            vlan_id=segment.vlan_id,
            subnet=segment.subnet or "",
            gateway=segment.gateway or "",
            dhcp=segment.dhcp,
        )
