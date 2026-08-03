"""Requisitos expresados antes de escoger hardware físico."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .roles import DeviceRole
from .service_plan import DnsRecordRequirement, ServiceType, TftpFileRequirement


class AddressingPreference(str, Enum):
    DHCP = "dhcp"
    STATIC = "static"
    SLAAC = "slaac"
    UNSPECIFIED = "unspecified"


class EndpointRequirement(BaseModel):
    """Cantidad de endpoints con un mismo rol lógico dentro de un sitio."""

    role: DeviceRole
    count: int
    requires_poe: bool = False
    wired: bool = True
    wireless: bool = False
    addressing_preference: AddressingPreference = AddressingPreference.UNSPECIFIED
    metadata: dict[str, str] = Field(default_factory=dict)


class ServiceRequirement(BaseModel):
    """Servicio que debe existir, sin imponer todavía un modelo de servidor."""

    name: str
    required: bool = True
    service_type: ServiceType | None = None
    host_device_id: str = ""
    segment_id: str = ""
    address: str = ""
    client_device_ids: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    verification_required: bool = True
    dns_records: list[DnsRecordRequirement] = Field(default_factory=list)
    hostname: str = ""
    http_content: str = ""
    ntp_authoritative: bool = True
    tftp_files: list[TftpFileRequirement] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
