"""Representative wireless topologies at three sizes.

Deliberately small. The point of the medium and advanced fixtures is to change
the *shape* — several clusters, several access points, several sites — not to
reproduce a large topology. Counts and names live here so no test hardcodes
them and no production module ever sees them.
"""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.requirements import (
    AddressingPreference,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.models.segments import (
    NetworkSegment,
    SegmentRole,
)
from src.packet_tracer_mcp.domain.enterprise.services.endpoint_expander import (
    ExpandedEndpoint,
)


def endpoint(
    role: DeviceRole,
    index: int,
    *,
    site_id: str,
    zone_id: str = "",
    building_id: str = "",
    floor_id: str = "",
    wireless: bool | None = None,
    addressing: AddressingPreference = AddressingPreference.DHCP,
    segment_role: SegmentRole | None = None,
    metadata: dict[str, str] | None = None,
) -> ExpandedEndpoint:
    """One expanded endpoint, with the wireless flag derived from the role."""
    radio = (role is not DeviceRole.ACCESS_POINT) if wireless is None else wireless
    scope = zone_id or floor_id or building_id or site_id
    return ExpandedEndpoint(
        id=f"endpoint/{scope}/{role.value}/{index:03d}",
        name=f"{scope.rsplit('/', 1)[-1].upper()}-{role.value.upper()}-{index:02d}",
        role=role,
        site_id=site_id,
        building_id=building_id,
        floor_id=floor_id,
        zone_id=zone_id,
        source_group=f"{scope}:wireless-cluster:{role.value}",
        source_index=index,
        requires_poe=False,
        wired=not radio,
        wireless=radio,
        addressing_preference=addressing,
        segment_role=segment_role,
        requirement_metadata=dict(metadata or {}),
    )


def simple_topology() -> list[ExpandedEndpoint]:
    """One access point, one sensor, one zone."""
    site = "site/lab"
    zone = "zone/lab-floor"
    return [
        endpoint(DeviceRole.ACCESS_POINT, 1, site_id=site, zone_id=zone),
        endpoint(DeviceRole.SMOKE_DETECTOR, 1, site_id=site, zone_id=zone),
    ]


def medium_topology() -> list[ExpandedEndpoint]:
    """Several IoT roles and several access points inside one zone."""
    site = "site/branch"
    zone = "zone/branch-ops"
    endpoints = [
        endpoint(DeviceRole.ACCESS_POINT, index, site_id=site, zone_id=zone)
        for index in (1, 2, 3)
    ]
    endpoints.extend(
        endpoint(DeviceRole.WEBCAM, index, site_id=site, zone_id=zone)
        for index in (1, 2)
    )
    endpoints.extend(
        endpoint(DeviceRole.SMOKE_DETECTOR, index, site_id=site, zone_id=zone)
        for index in (1, 2, 3)
    )
    endpoints.append(
        endpoint(DeviceRole.MOTION_DETECTOR, 1, site_id=site, zone_id=zone)
    )
    return endpoints


def advanced_topology() -> list[ExpandedEndpoint]:
    """Two sites, several zones, and one cluster split by segment role.

    The second site keeps a wireless laptop, which belongs to a different
    segment role and therefore to a different cluster in the same zone. That is
    the case a contract driven by a fixed IoT role list would get wrong.
    """
    endpoints: list[ExpandedEndpoint] = []
    site_a = "site/hq"
    for zone in ("zone/hq-north", "zone/hq-south"):
        endpoints.append(endpoint(
            DeviceRole.ACCESS_POINT, 1, site_id=site_a,
            building_id="building/hq-main", floor_id="floor/hq-1", zone_id=zone,
        ))
        endpoints.append(endpoint(
            DeviceRole.ACCESS_POINT, 2, site_id=site_a,
            building_id="building/hq-main", floor_id="floor/hq-1", zone_id=zone,
        ))
        endpoints.append(endpoint(
            DeviceRole.WEBCAM, 1, site_id=site_a,
            building_id="building/hq-main", floor_id="floor/hq-1", zone_id=zone,
        ))
        endpoints.append(endpoint(
            DeviceRole.MOTION_DETECTOR, 1, site_id=site_a,
            building_id="building/hq-main", floor_id="floor/hq-1", zone_id=zone,
        ))

    site_b = "site/plant"
    zone_b = "zone/plant-line"
    endpoints.append(endpoint(
        DeviceRole.ACCESS_POINT, 1, site_id=site_b,
        building_id="building/plant-a", floor_id="floor/plant-0", zone_id=zone_b,
    ))
    endpoints.append(endpoint(
        DeviceRole.SMOKE_DETECTOR, 1, site_id=site_b,
        building_id="building/plant-a", floor_id="floor/plant-0", zone_id=zone_b,
    ))
    endpoints.append(endpoint(
        DeviceRole.HUMITURE_MONITOR, 1, site_id=site_b,
        building_id="building/plant-a", floor_id="floor/plant-0", zone_id=zone_b,
    ))
    endpoints.append(endpoint(
        DeviceRole.LAPTOP, 1, site_id=site_b,
        building_id="building/plant-a", floor_id="floor/plant-0", zone_id=zone_b,
    ))
    return endpoints


def segments_for(site_id: str, subnet: str, vlan_id: int) -> list[NetworkSegment]:
    """One declared CCTV segment, so a test can exercise addressing intent."""
    return [NetworkSegment(
        name=f"{site_id}-{SegmentRole.CCTV.value}",
        role=SegmentRole.CCTV,
        site=site_id,
        host_requirement=8,
        dhcp=True,
        vlan_id=vlan_id,
        subnet=subnet,
        gateway=subnet.split("/", 1)[0].rsplit(".", 1)[0] + ".1",
    )]
