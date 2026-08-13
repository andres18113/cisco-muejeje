"""Intenciones declarativas de una red empresarial."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .hierarchy import BuildingIntent
from .requirements import EndpointRequirement, ServiceRequirement, WanLinkRequirement


class SiteType(str, Enum):
    HQ = "hq"
    BRANCH = "branch"
    WAREHOUSE = "warehouse"
    DATACENTER = "datacenter"
    CAMPUS = "campus"


class SiteIntent(BaseModel):
    """Necesidades de un sitio antes de asignar VLANs, IPs o modelos PT."""

    name: str
    type: SiteType
    endpoints: list[EndpointRequirement] = Field(default_factory=list)
    services: list[ServiceRequirement] = Field(default_factory=list)
    buildings: list[BuildingIntent] = Field(default_factory=list)
    growth_percent: float | None = None
    address_block: str | None = None
    pair_pc_with_ip_phone: bool | None = None
    uplinks: list[WanLinkRequirement] = Field(default_factory=list)


class EnterpriseIntent(BaseModel):
    """Entrada de alto nivel que el diseñador Enterprise transformará en un plan."""

    name: str
    sites: list[SiteIntent] = Field(default_factory=list)
    address_space: str | None = None
    routing_preference: str | None = None
    internet_required: bool = False
    default_growth_percent: float = 20.0
    metadata: dict[str, str] = Field(default_factory=dict)
