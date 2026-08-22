"""Primitiva segura y compartida para la configuracion IOS de Packet Tracer."""

from __future__ import annotations

import json
from collections.abc import Callable

from ...shared.ios_config import build_configure_ios_call

class PacketTracerConfigurationRuntime:
    """Envio asincrono del canal de configuracion oficial del MCP."""

    def __init__(self, send: Callable[[str], bool]) -> None:
        self._send = send

    def configure_ios(self, device: str, ios_payload: str) -> bool:
        return self._send(build_configure_ios_call(device, ios_payload))

    def configure_endpoint_ipv4(
        self, device: str, address: str, mask: str, gateway: str,
    ) -> bool:
        """Direccion estatica de un endpoint por el helper oficial de PT.

        Un PC no tiene canal IOS: PT expone `configurePcIp`, que es el mismo
        helper que ya usa el generador PTBuilder.
        """
        arguments = ", ".join((
            json.dumps(device), "false",
            json.dumps(address), json.dumps(mask), json.dumps(gateway),
        ))
        return self._send("configurePcIp(" + arguments + ");")

    def configure_endpoint_dhcp(
        self, device: str, interface: str = "FastEthernet0",
    ) -> bool:
        """Solicita DHCP por el helper tipado que usa el runtime enterprise."""

        arguments = ",".join((
            json.dumps(device), "true", "null", "null", "null", "null",
            json.dumps(interface),
        ))
        return self._send("configurePcIp(" + arguments + ");")
