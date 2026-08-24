"""Canonical declarative demand for the CP-SCALE qualification.

The historical documents explain where the demand came from. This typed intent
is the product authority used by design, IPAM, capacity, hardware, compilation,
and any later runtime qualification.
"""

from __future__ import annotations

from enum import Enum

from ..models.hierarchy import BuildingIntent, EndpointGroup, FloorIntent, ZoneIntent
from ..models.intent import EnterpriseIntent, SiteIntent, SiteType
from ..models.link_performance import LinkMedia, TrafficFlowIntent
from ..models.requirements import (
    AddressingPreference,
    EndpointRequirement,
    WanLinkRequirement,
)
from ..models.roles import DeviceRole
from ..models.segments import SegmentRequirement, SegmentRole


class CPScalePoint(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


CP_SCALE_WORKLOAD_COUNTS: dict[DeviceRole, int] = {
    DeviceRole.USER_PC: 104,
    DeviceRole.LAPTOP: 3,
    DeviceRole.IP_PHONE: 69,
    DeviceRole.PRINTER: 8,
    DeviceRole.WEBCAM: 26,
    DeviceRole.SMOKE_DETECTOR: 42,
    DeviceRole.MOTION_DETECTOR: 22,
    DeviceRole.HUMITURE_MONITOR: 2,
    DeviceRole.TEMPERATURE_MONITOR: 3,
}

CP_SCALE_SITE_WORKLOAD_COUNTS: dict[str, dict[DeviceRole, int]] = {
    "Large Branch": {
        DeviceRole.USER_PC: 86,
        DeviceRole.IP_PHONE: 51,
        DeviceRole.PRINTER: 8,
        DeviceRole.WEBCAM: 16,
        DeviceRole.SMOKE_DETECTOR: 38,
        DeviceRole.MOTION_DETECTOR: 16,
        DeviceRole.HUMITURE_MONITOR: 2,
    },
    "Multilayer Branch": {
        DeviceRole.USER_PC: 12,
        DeviceRole.LAPTOP: 2,
        DeviceRole.IP_PHONE: 11,
        DeviceRole.WEBCAM: 10,
        DeviceRole.SMOKE_DETECTOR: 1,
        DeviceRole.MOTION_DETECTOR: 3,
        DeviceRole.TEMPERATURE_MONITOR: 2,
    },
    "Small Branch": {
        DeviceRole.USER_PC: 6,
        DeviceRole.LAPTOP: 1,
        DeviceRole.IP_PHONE: 7,
        DeviceRole.SMOKE_DETECTOR: 3,
        DeviceRole.MOTION_DETECTOR: 3,
        DeviceRole.TEMPERATURE_MONITOR: 1,
    },
}

CP_SCALE_ACCESS_POINT_COUNT = 17

_IOT_ROLES = {
    DeviceRole.WEBCAM,
    DeviceRole.SMOKE_DETECTOR,
    DeviceRole.MOTION_DETECTOR,
    DeviceRole.HUMITURE_MONITOR,
    DeviceRole.TEMPERATURE_MONITOR,
}


def _workload(
    role: DeviceRole,
    count: int,
    *,
    canonical: bool,
) -> EndpointRequirement:
    wireless = role in _IOT_ROLES
    metadata = {"workload_endpoint": "true"}
    if wireless:
        metadata.update({
            "physical_realization": "exact_catalog_model",
            "wireless_association": "unqualified",
        })
    return EndpointRequirement(
        role=role,
        count=count,
        requires_poe=role is DeviceRole.IP_PHONE,
        wired=not wireless,
        wireless=wireless,
        addressing_preference=(
            AddressingPreference.STATIC
            if role is DeviceRole.PRINTER else AddressingPreference.DHCP
        ),
        segment_role=(
            SegmentRole.CCTV
            if canonical and role is DeviceRole.PRINTER else None
        ),
        metadata=metadata,
    )


def _access_points(count: int, *, canonical: bool) -> EndpointRequirement:
    return EndpointRequirement(
        role=DeviceRole.ACCESS_POINT,
        count=count,
        requires_poe=True,
        wired=True,
        wireless=False,
        addressing_preference=AddressingPreference.STATIC,
        segment_role=SegmentRole.CCTV if canonical else None,
        metadata={
            "workload_endpoint": "false",
            "infrastructure_class": "access_point",
        },
    )


def _zone(
    name: str,
    demands: list[tuple[DeviceRole, int]],
    *,
    access_points: int,
    canonical: bool,
) -> ZoneIntent:
    wired = [
        _workload(role, count, canonical=canonical)
        for role, count in demands if role not in _IOT_ROLES
    ]
    wireless = [
        _workload(role, count, canonical=canonical)
        for role, count in demands if role in _IOT_ROLES
    ]
    groups = [EndpointGroup(name="wired-workload", requirements=wired)]
    if wireless or access_points:
        groups.append(EndpointGroup(
            name="visual-wireless-cluster",
            requirements=[
                *wireless,
                *(
                    [_access_points(access_points, canonical=canonical)]
                    if access_points else []
                ),
            ],
        ))
    return ZoneIntent(name=name, endpoint_groups=groups)


def _segments(
    site_octet: int,
    *,
    data_hosts: int,
    voice_hosts: int,
    iot_hosts: int,
) -> list[SegmentRequirement]:
    return [
        SegmentRequirement(
            role=SegmentRole.DATA,
            hosts=data_hosts,
            dhcp=True,
            vlan_id=10,
            subnet=f"172.{site_octet}.10.0/24",
            gateway=f"172.{site_octet}.10.1",
        ),
        SegmentRequirement(
            role=SegmentRole.VOICE,
            hosts=voice_hosts,
            dhcp=True,
            vlan_id=20,
            subnet=f"172.{site_octet}.20.0/24",
            gateway=f"172.{site_octet}.20.1",
        ),
        SegmentRequirement(
            role=SegmentRole.CCTV,
            hosts=iot_hosts,
            dhcp=True,
            vlan_id=30,
            subnet=f"172.{site_octet}.30.0/24",
            gateway=f"172.{site_octet}.30.1",
        ),
    ]


def _large_branch(*, canonical: bool = True) -> SiteIntent:
    return SiteIntent(
        name="Large Branch",
        type=SiteType.HQ,
        buildings=[BuildingIntent(name="Campus", floors=[
            FloorIntent(name="Floor 1", zones=[_zone(
                "Zone A",
                [
                    (DeviceRole.USER_PC, 23), (DeviceRole.IP_PHONE, 21),
                    (DeviceRole.PRINTER, 2), (DeviceRole.WEBCAM, 4),
                    (DeviceRole.SMOKE_DETECTOR, 11),
                    (DeviceRole.MOTION_DETECTOR, 4),
                ],
                access_points=3,
                canonical=canonical,
            )]),
            FloorIntent(name="Floor 2", zones=[_zone(
                "Zone B",
                [
                    (DeviceRole.USER_PC, 20), (DeviceRole.IP_PHONE, 14),
                    (DeviceRole.PRINTER, 2), (DeviceRole.WEBCAM, 4),
                    (DeviceRole.SMOKE_DETECTOR, 9),
                    (DeviceRole.MOTION_DETECTOR, 4),
                ],
                access_points=3,
                canonical=canonical,
            )]),
            FloorIntent(name="Floor 3", zones=[
                _zone(
                    "Zone C",
                    [
                        (DeviceRole.USER_PC, 23), (DeviceRole.IP_PHONE, 3),
                        (DeviceRole.PRINTER, 2), (DeviceRole.WEBCAM, 4),
                        (DeviceRole.SMOKE_DETECTOR, 10),
                        (DeviceRole.MOTION_DETECTOR, 4),
                        (DeviceRole.HUMITURE_MONITOR, 2),
                    ],
                    access_points=3,
                    canonical=canonical,
                ),
                _zone(
                    "Zone D",
                    [
                        (DeviceRole.USER_PC, 20), (DeviceRole.IP_PHONE, 13),
                        (DeviceRole.PRINTER, 2), (DeviceRole.WEBCAM, 4),
                        (DeviceRole.SMOKE_DETECTOR, 8),
                        (DeviceRole.MOTION_DETECTOR, 4),
                    ],
                    access_points=3,
                    canonical=canonical,
                ),
            ]),
        ])],
        address_block="172.16.0.0/16" if canonical else None,
        pair_pc_with_ip_phone=False if canonical else None,
        segments=(
            _segments(16, data_hosts=86, voice_hosts=51, iot_hosts=92)
            if canonical else []
        ),
        uplinks=[
            WanLinkRequirement(
                target_site_id="multilayer-branch",
                media=LinkMedia.SERIAL,
                network="10.0.0.0/30" if canonical else None,
                source_ipv4="10.0.0.1" if canonical else None,
                target_ipv4="10.0.0.2" if canonical else None,
            ),
            WanLinkRequirement(
                target_site_id="small-branch",
                media=LinkMedia.SERIAL,
                network="10.0.0.4/30" if canonical else None,
                source_ipv4="10.0.0.5" if canonical else None,
                target_ipv4="10.0.0.6" if canonical else None,
            ),
        ],
    )


def _multilayer_branch(*, canonical: bool = True) -> SiteIntent:
    return SiteIntent(
        name="Multilayer Branch",
        type=SiteType.BRANCH,
        buildings=[BuildingIntent(name="Multilayer Campus", floors=[FloorIntent(
            name="Access",
            zones=[
                _zone(
                    "MLS3",
                    [
                        (DeviceRole.USER_PC, 2), (DeviceRole.IP_PHONE, 2),
                        (DeviceRole.WEBCAM, 1), (DeviceRole.MOTION_DETECTOR, 2),
                        (DeviceRole.TEMPERATURE_MONITOR, 1),
                    ],
                    access_points=1,
                    canonical=canonical,
                ),
                _zone(
                    "MLS4",
                    [
                        (DeviceRole.IP_PHONE, 1), (DeviceRole.WEBCAM, 8),
                        (DeviceRole.TEMPERATURE_MONITOR, 1),
                    ],
                    access_points=1,
                    canonical=canonical,
                ),
                _zone(
                    "MLS5",
                    [(DeviceRole.IP_PHONE, 8)],
                    access_points=0,
                    canonical=canonical,
                ),
                _zone(
                    "MLS6",
                    [
                        (DeviceRole.USER_PC, 10), (DeviceRole.LAPTOP, 2),
                        (DeviceRole.WEBCAM, 1), (DeviceRole.SMOKE_DETECTOR, 1),
                        (DeviceRole.MOTION_DETECTOR, 1),
                    ],
                    access_points=1,
                    canonical=canonical,
                ),
            ],
        )])],
        address_block="172.18.0.0/16" if canonical else None,
        pair_pc_with_ip_phone=True,
        segments=(
            _segments(18, data_hosts=14, voice_hosts=11, iot_hosts=19)
            if canonical else []
        ),
        uplinks=[
            WanLinkRequirement(
                target_site_id="small-branch",
                media=LinkMedia.SERIAL,
                network="10.0.0.8/30" if canonical else None,
                source_ipv4="10.0.0.10" if canonical else None,
                target_ipv4="10.0.0.9" if canonical else None,
            ),
        ],
    )


def _small_branch(*, canonical: bool = True) -> SiteIntent:
    return SiteIntent(
        name="Small Branch",
        type=SiteType.BRANCH,
        buildings=[BuildingIntent(name="Branch", floors=[FloorIntent(
            name="Access",
            zones=[_zone(
                "Branch Zone",
                [
                    (DeviceRole.USER_PC, 6), (DeviceRole.LAPTOP, 1),
                    (DeviceRole.IP_PHONE, 7), (DeviceRole.SMOKE_DETECTOR, 3),
                    (DeviceRole.MOTION_DETECTOR, 3),
                    (DeviceRole.TEMPERATURE_MONITOR, 1),
                ],
                access_points=2,
                canonical=canonical,
            )],
        )])],
        address_block="172.17.0.0/16" if canonical else None,
        pair_pc_with_ip_phone=False if canonical else None,
        segments=(
            _segments(17, data_hosts=7, voice_hosts=7, iot_hosts=9)
            if canonical else []
        ),
    )


def _full_intent(*, canonical: bool) -> EnterpriseIntent:
    return EnterpriseIntent(
        name="CP-SCALE 279 Endpoint Enterprise",
        address_space="172.16.0.0/14" if canonical else "10.0.0.0/8",
        routing_preference="ripv2",
        internet_required=True,
        default_growth_percent=20,
        sites=[
            _large_branch(canonical=canonical),
            _multilayer_branch(canonical=canonical),
            _small_branch(canonical=canonical),
        ],
        metadata={
            "scenario": "cp-scale",
            "scale_point": CPScalePoint.D.value,
            "workload_endpoints": "279",
            "access_points": "17",
            "wireless_association": "unqualified",
        },
        traffic_flows=[
            TrafficFlowIntent(
                id="flow/large-to-multilayer",
                source_site_id="large-branch",
                destination_site_id="multilayer-branch",
                per_unit_bps=100_000,
            ),
            TrafficFlowIntent(
                id="flow/multilayer-to-small",
                source_site_id="multilayer-branch",
                destination_site_id="small-branch",
                per_unit_bps=100_000,
            ),
            TrafficFlowIntent(
                id="flow/small-to-large",
                source_site_id="small-branch",
                destination_site_id="large-branch",
                per_unit_bps=100_000,
            ),
        ],
    )


def cp_scale_intent() -> EnterpriseIntent:
    """Return the canonical documented logical target."""
    return _full_intent(canonical=True)


def cp_scale_scale_fixture_intent() -> EnterpriseIntent:
    """Preserve the historical capacity-driven 318/235 regression input."""
    return _full_intent(canonical=False)


def cp_scale_intent_for(point: CPScalePoint) -> EnterpriseIntent:
    """Derive a progressive live point without introducing another scenario."""
    point = CPScalePoint(point)
    if point is CPScalePoint.D:
        return cp_scale_scale_fixture_intent()

    intent = cp_scale_scale_fixture_intent()
    site = intent.sites[0]
    site.uplinks = []
    floors = site.buildings[0].floors
    if point is CPScalePoint.A:
        site.buildings[0].floors = [floors[0]]
    elif point is CPScalePoint.B:
        site.buildings[0].floors = floors[:2]
    intent.sites = [site]
    intent.traffic_flows = []
    intent.metadata = {
        **intent.metadata,
        "scale_point": point.value,
        "workload_endpoints": {
            CPScalePoint.A: "65",
            CPScalePoint.B: "118",
            CPScalePoint.C: "217",
        }[point],
        "access_points": {
            CPScalePoint.A: "3",
            CPScalePoint.B: "6",
            CPScalePoint.C: "12",
        }[point],
    }
    return intent
