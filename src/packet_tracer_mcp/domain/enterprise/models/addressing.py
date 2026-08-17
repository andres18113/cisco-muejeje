"""Resultados IPv4 de IPAM, independientes de CLI y Packet Tracer."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class GatewayPolicy(str, Enum):
    FIRST_USABLE = "first_usable"


class AddressSpace(BaseModel):
    network: str


class SiteAddressBlock(BaseModel):
    site_id: str
    network: str
    prefix: int
    explicit: bool = False


class SubnetRequirement(BaseModel):
    segment_id: str
    raw_hosts: int
    growth_percent: float
    growth_hosts: int
    gateway_count: int = 1
    reserved_hosts: int = 0
    required_usable_hosts: int
    prefix: int


class SubnetAllocation(BaseModel):
    segment_id: str
    network: str
    prefix: int
    netmask: str
    gateway: str
    first_usable: str
    last_usable: str
    broadcast: str
    usable_hosts: int
    required_hosts: int
    growth_percent: float
    reserved_hosts: int = 0


class WanTransitAllocation(BaseModel):
    id: str
    source_site_id: str
    target_site_id: str
    media: str
    network: str
    prefix: int = 30
    netmask: str
    source_ipv4: str
    target_ipv4: str


class AddressingPlan(BaseModel):
    address_space: AddressSpace
    site_blocks: list[SiteAddressBlock] = Field(default_factory=list)
    allocations: list[SubnetAllocation] = Field(default_factory=list)
    transit_allocations: list[WanTransitAllocation] = Field(default_factory=list)
    gateway_policy: GatewayPolicy = GatewayPolicy.FIRST_USABLE
