"""Identidad y nombres estables para topologías Enterprise concretas."""

from __future__ import annotations

import hashlib
import re

from ..models.roles import DeviceRole


_ROLE_TOKENS = {
    DeviceRole.USER_PC: "PC",
    DeviceRole.LAPTOP: "LAPTOP",
    DeviceRole.IP_PHONE: "PHONE",
    DeviceRole.PRINTER: "PRINTER",
    DeviceRole.IP_CAMERA: "CAMERA",
    DeviceRole.WEBCAM: "WEBCAM",
    DeviceRole.SMOKE_DETECTOR: "SMOKE",
    DeviceRole.MOTION_DETECTOR: "MOTION",
    DeviceRole.HUMITURE_MONITOR: "HUMITURE",
    DeviceRole.TEMPERATURE_MONITOR: "TEMP",
    DeviceRole.ACCESS_POINT: "AP",
    DeviceRole.SERVER: "SERVER",
    DeviceRole.WEB_SERVER: "WEB",
    DeviceRole.DNS_SERVER: "DNS",
    DeviceRole.DHCP_SERVER: "DHCP",
    DeviceRole.NTP_SERVER: "NTP",
    DeviceRole.TFTP_SERVER: "TFTP",
    DeviceRole.NVR: "NVR",
    DeviceRole.ACCESS_SWITCH: "ACCESS-SW",
    DeviceRole.DISTRIBUTION_SWITCH: "DIST-SW",
    DeviceRole.CORE_SWITCH: "CORE-SW",
    DeviceRole.WAN_ROUTER: "WAN-RTR",
    DeviceRole.EDGE_ROUTER: "EDGE-RTR",
    DeviceRole.FIREWALL: "FW",
}


def _token(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-") or "ITEM"


class DeterministicNamingService:
    def __init__(self, max_length: int = 64, prefix: str = "") -> None:
        self._max_length = max(16, max_length)
        self._prefix = re.sub(r"[^A-Za-z0-9_-]+", "-", prefix)

    @staticmethod
    def role_token(role: DeviceRole) -> str:
        return _ROLE_TOKENS[role]

    def endpoint_id(self, zone_id: str, role: DeviceRole, index: int) -> str:
        return f"endpoint/{zone_id}/{role.value}/{index:03d}"

    def endpoint_name(
        self,
        site_id: str,
        building_id: str,
        floor_id: str,
        zone_id: str,
        role: DeviceRole,
        index: int,
    ) -> str:
        components = [_token(site_id.rsplit("/", 1)[-1])]
        if building_id:
            components.append(_token(building_id.rsplit("/", 1)[-1]))
        if floor_id:
            components.append(_token(floor_id.rsplit("/", 1)[-1]))
        components.extend([_token(zone_id.rsplit("/", 1)[-1]), self.role_token(role), f"{index:02d}"])
        return self._bounded("-".join(components))

    def network_name(
        self, site_id: str, role: DeviceRole, index: int, zone_id: str = "",
    ) -> str:
        components = [_token(site_id.rsplit("/", 1)[-1])]
        if zone_id and role is DeviceRole.ACCESS_SWITCH:
            components.append(_token(zone_id.rsplit("/", 1)[-1]))
        components.extend([self.role_token(role), f"{index:02d}"])
        return self._bounded("-".join(components))

    def _bounded(self, value: str) -> str:
        value = f"{self._prefix}{value}"
        if len(value) <= self._max_length:
            return value
        suffix = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8].upper()
        return f"{value[:self._max_length - len(suffix) - 1]}-{suffix}"
