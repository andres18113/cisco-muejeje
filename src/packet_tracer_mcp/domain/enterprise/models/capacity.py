"""Requisitos físicos agregados, antes de seleccionar switches."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PortAttachmentPolicy(str, Enum):
    DIRECT = "direct"
    PHONE_PASSTHROUGH = "phone_passthrough"
    WIRELESS = "wireless"


class AccessCapacityRequirement(BaseModel):
    site_id: str
    zone_id: str
    raw_wired_endpoints: int
    base_access_ports: int
    base_poe_ports: int
    pc_phone_pairs: int
    growth_percent: float
    growth_reserved_access_ports: int
    growth_reserved_poe_ports: int
    required_access_ports: int
    required_poe_ports: int
    required_uplink_ports: int
    attachment_policy: PortAttachmentPolicy
    layer3_required: bool = False
    redundancy_preference: bool = False


class CapacityPlan(BaseModel):
    requirements: list[AccessCapacityRequirement] = Field(default_factory=list)
