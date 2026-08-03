"""Orden y selección determinista de interfaces físicas para E4."""

from __future__ import annotations

import re

from ..models.hardware import PortDescriptor


_LOGICAL_PREFIXES = ("vlan", "loopback", "tunnel", "port-channel", "portchannel", "bvi")


def natural_interface_key(name: str) -> tuple[object, ...]:
    """Ordena Fa0/2 antes de Fa0/10 sin depender del orden del catálogo."""

    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", name)
        if part
    )


def is_logical_interface(name: str) -> bool:
    compact = re.sub(r"\s+", "", name).casefold()
    return compact.startswith(_LOGICAL_PREFIXES)


def physical_ports(ports: list[PortDescriptor]) -> list[PortDescriptor]:
    return sorted(
        (port for port in ports if port.physical and not is_logical_interface(port.name)),
        key=lambda port: natural_interface_key(port.name),
    )
