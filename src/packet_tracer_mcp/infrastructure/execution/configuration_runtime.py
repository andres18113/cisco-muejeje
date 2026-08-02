"""Primitiva segura y compartida para la configuracion IOS de Packet Tracer."""

from __future__ import annotations

from collections.abc import Callable

from ...shared.ios_config import build_configure_ios_call

class PacketTracerConfigurationRuntime:
    """Envio asincrono del canal de configuracion oficial del MCP."""

    def __init__(self, send: Callable[[str], bool]) -> None:
        self._send = send

    def configure_ios(self, device: str, ios_payload: str) -> bool:
        return self._send(build_configure_ios_call(device, ios_payload))
