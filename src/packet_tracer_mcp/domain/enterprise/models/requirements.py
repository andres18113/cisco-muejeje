"""Requisitos expresados antes de escoger hardware físico."""

from __future__ import annotations

from enum import Enum, StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from .link_performance import LinkMedia
from .roles import DeviceRole
from .segments import SegmentRole
from .service_plan import (
    DnsRecordRequirement,
    EmailAccountRequirement,
    EmailClientRequirement,
    EmailPairRequirement,
    ServerDhcpPoolRequirement,
    ServiceType,
    TftpFileRequirement,
)


class AddressingPreference(StrEnum):
    """How an endpoint requirement asks to be addressed."""

    __str__ = Enum.__str__

    DHCP = "dhcp"
    STATIC = "static"
    SLAAC = "slaac"
    UNSPECIFIED = "unspecified"


class WanLinkRequirement(BaseModel):
    """Conectividad entre sitios antes de escoger routers, módulos o puertos."""

    target_site_id: str
    media: LinkMedia = LinkMedia.ETHERNET
    network: str | None = None
    source_ipv4: str | None = None
    target_ipv4: str | None = None


class EndpointRequirement(BaseModel):
    """Cantidad de endpoints con un mismo rol lógico dentro de un sitio."""

    role: DeviceRole
    count: int
    requires_poe: bool = False
    wired: bool = True
    wireless: bool = False
    addressing_preference: AddressingPreference = AddressingPreference.UNSPECIFIED
    segment_role: SegmentRole | None = None
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
    #: SMTP only: the server's mail domain, its accounts, the selected
    #: clients and which account each uses, and explicit message pairs.
    #: Without explicit pairs the clients form a ring (a self-send for one).
    domain_name: str = ""
    email_accounts: list[EmailAccountRequirement] = Field(default_factory=list)
    email_clients: list[EmailClientRequirement] = Field(default_factory=list)
    email_pairs: list[EmailPairRequirement] = Field(default_factory=list)
    #: `configure_only` configures and reads back; `effectful` also sends.
    verification_mode: Literal["effectful", "configure_only", "state_only"] = (
        "effectful"
    )
    dhcp_pool: ServerDhcpPoolRequirement | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
