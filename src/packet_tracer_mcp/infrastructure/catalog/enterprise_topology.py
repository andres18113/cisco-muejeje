"""Adapter del catálogo Packet Tracer al perfil físico backend-neutral de E4."""

from __future__ import annotations

from ...domain.enterprise.models.compilation import (
    PhysicalCompilationProfile,
    PhysicalModelProfile,
)
from ...domain.enterprise.models.roles import DeviceRole
from .cables import infer_cable
from .devices import ALL_MODELS


_ENDPOINT_MODELS = {
    DeviceRole.USER_PC: "PC-PT",
    DeviceRole.LAPTOP: "Laptop-PT",
    DeviceRole.IP_PHONE: "7960",
    DeviceRole.PRINTER: "Printer-PT",
    DeviceRole.IP_CAMERA: "WiredEndDevice-PT",
    DeviceRole.WEBCAM: "Webcam",
    DeviceRole.SMOKE_DETECTOR: "Smoke Detector",
    DeviceRole.MOTION_DETECTOR: "Motion Detector",
    DeviceRole.HUMITURE_MONITOR: "Humiture Monitor",
    DeviceRole.TEMPERATURE_MONITOR: "Temperature Monitor",
    DeviceRole.ACCESS_POINT: "AccessPoint-PT",
    DeviceRole.SERVER: "Server-PT",
    DeviceRole.WEB_SERVER: "Server-PT",
    DeviceRole.DNS_SERVER: "Server-PT",
    DeviceRole.DHCP_SERVER: "Server-PT",
    DeviceRole.NTP_SERVER: "Server-PT",
    DeviceRole.TFTP_SERVER: "Server-PT",
    DeviceRole.NVR: "Server-PT",
}


class PacketTracerTopologyCatalogAdapter:
    """Resuelve modelos/puertos en infraestructura; el compilador no conoce PT."""

    def compilation_profile(self) -> PhysicalCompilationProfile:
        models: list[PhysicalModelProfile] = []
        for model in sorted(ALL_MODELS.values(), key=lambda item: item.pt_type.casefold()):
            ports = [port.full_name for port in model.ports]
            models.append(PhysicalModelProfile(
                model=model.pt_type,
                category=model.category,
                physical_ports=ports,
                network_port=self._network_port(model.pt_type, ports),
                passthrough_port="PC" if model.pt_type == "7960" else "",
                generic=model.pt_type in {"WiredEndDevice-PT", "Thing"},
            ))
        return PhysicalCompilationProfile(
            models=models,
            endpoint_role_models=_ENDPOINT_MODELS,
        )

    @staticmethod
    def cable_for(category_a: str, category_b: str) -> str:
        return infer_cable(category_a, category_b)

    @staticmethod
    def _network_port(model: str, ports: list[str]) -> str:
        if model == "7960":
            return "Switch"
        return ports[0] if ports else ""
