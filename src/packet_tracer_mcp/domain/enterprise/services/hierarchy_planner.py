"""Planificador de jerarquía física sin coordenadas ni hardware concreto."""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..models.enterprise_plan import SitePlan
from ..models.hierarchy import (
    BuildingPlan,
    EndpointGroup,
    FloorPlan,
    ZonePlan,
)
from ..models.intent import SiteIntent


def hierarchy_id(*names: str) -> str:
    """ID estable derivado de su ruta organizativa."""
    parts = [
        re.sub(r"[^a-z0-9]+", "-", component.casefold()).strip("-")
        for name in names
        for component in name.split("/")
    ]
    return "/".join(part or "item" for part in parts)


class PhysicalHierarchyPlanner:
    """Convierte edificios, pisos y zonas declarados en planes identificables."""

    def plan(self, intent: SiteIntent, site_plan: SitePlan) -> None:
        buildings: list[BuildingPlan] = []
        for building in intent.buildings:
            building_id = hierarchy_id(site_plan.site_id, building.name)
            floors: list[FloorPlan] = []
            for floor in building.floors:
                floor_id = hierarchy_id(building_id, floor.name)
                zones = [
                    ZonePlan(
                        name=zone.name,
                        zone_id=hierarchy_id(floor_id, zone.name),
                        endpoint_groups=zone.endpoint_groups,
                    )
                    for zone in floor.zones
                ]
                floors.append(FloorPlan(name=floor.name, floor_id=floor_id, zones=zones))
            buildings.append(BuildingPlan(name=building.name, building_id=building_id, floors=floors))
        site_plan.buildings = buildings

        if intent.endpoints:
            site_plan.default_zone = ZonePlan(
                name="SITE_DEFAULT_ZONE",
                zone_id=hierarchy_id(site_plan.site_id, "default"),
                endpoint_groups=[EndpointGroup(name="site-default", requirements=intent.endpoints)],
            )


def iter_zone_plans(site_plan: SitePlan) -> Iterator[ZonePlan]:
    """Recorre zonas en un orden estable, incluida la zona interna legacy."""
    if site_plan.default_zone is not None:
        yield site_plan.default_zone
    for building in site_plan.buildings:
        for floor in building.floors:
            yield from floor.zones
