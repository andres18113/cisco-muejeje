"""Expansión E4 de grupos agregados a endpoints concretos, sin runtime."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models.enterprise_plan import EnterprisePlan, SitePlan
from ..models.hierarchy import EndpointGroup, ZonePlan
from ..models.requirements import AddressingPreference
from ..models.roles import DeviceRole
from .naming import DeterministicNamingService


@dataclass(frozen=True)
class ZoneContext:
    site_id: str
    site_name: str
    building_id: str
    floor_id: str
    zone: ZonePlan


@dataclass
class ExpandedEndpoint:
    id: str
    name: str
    role: DeviceRole
    site_id: str
    building_id: str
    floor_id: str
    zone_id: str
    source_group: str
    source_index: int
    requires_poe: bool
    wired: bool
    wireless: bool
    addressing_preference: AddressingPreference
    requirement_metadata: dict[str, str] = field(default_factory=dict)
    pair_id: str = ""


def iter_zone_contexts(site: SitePlan) -> list[ZoneContext]:
    contexts: list[ZoneContext] = []
    if site.default_zone is not None:
        contexts.append(ZoneContext(site.site_id, site.name, "", "", site.default_zone))
    for building in sorted(site.buildings, key=lambda item: item.building_id):
        for floor in sorted(building.floors, key=lambda item: item.floor_id):
            for zone in sorted(floor.zones, key=lambda item: item.zone_id):
                contexts.append(ZoneContext(
                    site.site_id, site.name, building.building_id, floor.floor_id, zone,
                ))
    return sorted(contexts, key=lambda item: item.zone.zone_id)


class EndpointGroupExpander:
    """Materializa sólo conteos actuales; el growth permanece como reserva E2/E3."""

    def expand(
        self, enterprise: EnterprisePlan, naming: DeterministicNamingService,
    ) -> list[ExpandedEndpoint]:
        endpoints: list[ExpandedEndpoint] = []
        for site in sorted(enterprise.sites, key=lambda item: item.site_id):
            pair_counts = {item.zone_id: item.pc_phone_pairs for item in site.capacity_requirements}
            for context in iter_zone_contexts(site):
                zone_endpoints = self._expand_zone(context, naming)
                self._pair(zone_endpoints, pair_counts.get(context.zone.zone_id, 0))
                endpoints.extend(zone_endpoints)
        return sorted(endpoints, key=lambda item: item.id)

    @staticmethod
    def _expand_zone(
        context: ZoneContext, naming: DeterministicNamingService,
    ) -> list[ExpandedEndpoint]:
        endpoints: list[ExpandedEndpoint] = []
        role_positions: dict[DeviceRole, int] = {}
        groups = sorted(context.zone.endpoint_groups, key=lambda item: item.name.casefold())
        for group in groups:
            requirements = sorted(
                group.requirements,
                key=lambda item: (
                    item.role.value, item.wireless, item.wired, item.requires_poe,
                    tuple(sorted(item.metadata.items())),
                ),
            )
            local_positions: dict[DeviceRole, int] = {}
            for requirement in requirements:
                for _ in range(requirement.count):
                    role_positions[requirement.role] = role_positions.get(requirement.role, 0) + 1
                    local_positions[requirement.role] = local_positions.get(requirement.role, 0) + 1
                    role_index = role_positions[requirement.role]
                    endpoints.append(ExpandedEndpoint(
                        id=naming.endpoint_id(context.zone.zone_id, requirement.role, role_index),
                        name=naming.endpoint_name(
                            context.site_id, context.building_id, context.floor_id,
                            context.zone.zone_id, requirement.role, role_index,
                        ),
                        role=requirement.role,
                        site_id=context.site_id,
                        building_id=context.building_id,
                        floor_id=context.floor_id,
                        zone_id=context.zone.zone_id,
                        source_group=(
                            f"{context.zone.zone_id}:{group.name}:{requirement.role.value}"
                        ),
                        source_index=local_positions[requirement.role],
                        requires_poe=requirement.requires_poe,
                        wired=requirement.wired,
                        wireless=requirement.wireless,
                        addressing_preference=requirement.addressing_preference,
                        requirement_metadata=dict(sorted(requirement.metadata.items())),
                    ))
        return endpoints

    @staticmethod
    def _pair(endpoints: list[ExpandedEndpoint], requested_pairs: int) -> None:
        pcs = sorted(
            (item for item in endpoints if item.role is DeviceRole.USER_PC and item.wired and not item.wireless),
            key=lambda item: item.id,
        )
        phones = sorted(
            (item for item in endpoints if item.role is DeviceRole.IP_PHONE and item.wired and not item.wireless),
            key=lambda item: item.id,
        )
        count = min(requested_pairs, len(pcs), len(phones))
        for index, (pc, phone) in enumerate(zip(pcs[:count], phones[:count]), start=1):
            pair_id = f"{pc.zone_id}:pc-phone:{index:03d}"
            phone.pair_id = pair_id
            phone.source_group = f"{phone.zone_id}:pc-phone"
            phone.source_index = index
            pc.pair_id = pair_id
            pc.source_group = f"{pc.zone_id}:pc-phone-downstream"
            pc.source_index = index
