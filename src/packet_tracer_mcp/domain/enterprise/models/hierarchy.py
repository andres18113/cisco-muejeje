"""Jerarquía organizativa y agrupaciones agregadas de endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .requirements import EndpointRequirement


class EndpointGroup(BaseModel):
    """Grupo agregado: conserva conteos sin expandir dispositivos individuales."""

    name: str
    requirements: list[EndpointRequirement] = Field(default_factory=list)


class ZoneIntent(BaseModel):
    name: str
    endpoint_groups: list[EndpointGroup] = Field(default_factory=list)


class FloorIntent(BaseModel):
    name: str
    zones: list[ZoneIntent] = Field(default_factory=list)


class BuildingIntent(BaseModel):
    name: str
    floors: list[FloorIntent] = Field(default_factory=list)


class ZonePlan(BaseModel):
    name: str
    zone_id: str
    endpoint_groups: list[EndpointGroup] = Field(default_factory=list)


class FloorPlan(BaseModel):
    name: str
    floor_id: str
    zones: list[ZonePlan] = Field(default_factory=list)


class BuildingPlan(BaseModel):
    name: str
    building_id: str
    floors: list[FloorPlan] = Field(default_factory=list)
