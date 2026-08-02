"""Requisitos expresados antes de escoger hardware físico."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .roles import DeviceRole


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
    metadata: dict[str, str] = Field(default_factory=dict)
