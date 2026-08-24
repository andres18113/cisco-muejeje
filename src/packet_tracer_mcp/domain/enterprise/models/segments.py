"""Segmentos semánticos; E1 no les asigna aún VLAN ni direccionamiento."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class SegmentRole(str, Enum):
    DATA = "data"
    VOICE = "voice"
    CCTV = "cctv"
    PRINTERS = "printers"
    SERVERS = "servers"
    MANAGEMENT = "management"
    GUEST = "guest"
    WIRELESS_CORPORATE = "wireless_corporate"
    WAN = "wan"
    TRANSIT = "transit"


class SegmentRequirement(BaseModel):
    """Necesidad lógica que alimentará al VLSM/VLAN planner en E2."""

    role: SegmentRole
    hosts: int
    dhcp: bool = False
    security_zone: str = ""
    vlan_id: int | None = None
    subnet: str | None = None
    gateway: str | None = None


class NetworkSegment(BaseModel):
    """Segmento del plan Enterprise, con asignaciones futuras opcionales."""

    name: str
    role: SegmentRole
    site: str
    host_requirement: int
    growth_percent: float | None = None
    dhcp: bool = False
    security_zone: str = ""
    vlan_id: int | None = None
    subnet: str | None = None
    gateway: str | None = None
