"""Renderer IOS de las acciones de rendimiento de enlace.

El dominio decide; aqui y solo aqui se convierte en CLI. El reloj se emite
unicamente sobre el DCE resuelto, y `bandwidth` es ancho de banda logico de
routing: nunca sustituye al reloj ni se deriva de el sin politica explicita.

Verificado contra PT 9.0.1.0858 sobre 2911 + HWIC-2T: `clock rate 2000000` en
el DCE se relee como "DCE V.35, clock rate 2000000", el DTE responde
"DTE V.35 TX and RX clocks detected" sin reloj propio, y `bandwidth 2000` se
relee por separado como "BW 2000 Kbit".
"""

from __future__ import annotations

from ...domain.enterprise.models.configuration import (
    ConfigureEthernetLinkMode,
    ConfigureInterfaceBandwidth,
    ConfigureSerialClock,
)


def render_serial_clock(action: ConfigureSerialClock) -> list[str]:
    """`clock rate` toma bits por segundo, no kbps."""
    return [f"interface {action.interface}", f" clock rate {action.clock_rate_bps}"]


def render_interface_bandwidth(action: ConfigureInterfaceBandwidth) -> list[str]:
    """`bandwidth` toma kbps y solo alimenta metricas de routing."""
    return [f"interface {action.interface}", f" bandwidth {action.bandwidth_kbps}"]


def render_ethernet_link_mode(action: ConfigureEthernetLinkMode) -> list[str]:
    """AUTO no se escribe: negociar es la ausencia de un valor forzado."""
    lines = [f"interface {action.interface}"]
    speed = {"10m": "10", "100m": "100", "1g": "1000"}.get(action.speed)
    if speed:
        lines.append(f" speed {speed}")
    if action.duplex in {"full", "half"}:
        lines.append(f" duplex {action.duplex}")
    return lines if len(lines) > 1 else []
