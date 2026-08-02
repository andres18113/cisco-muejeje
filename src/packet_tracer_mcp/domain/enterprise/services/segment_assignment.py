"""Política única para asignar requisitos de endpoints a segmentos semánticos."""

from __future__ import annotations

from ..models.requirements import EndpointRequirement
from ..models.roles import DeviceRole
from ..models.segments import SegmentRole


class SegmentAssignmentPolicy:
    """Decisiones explícitas de E2, separadas de VLSM y de la capacidad física."""

    _BY_ROLE = {
        DeviceRole.IP_PHONE: SegmentRole.VOICE,
        DeviceRole.IP_CAMERA: SegmentRole.CCTV,
        DeviceRole.PRINTER: SegmentRole.PRINTERS,
        DeviceRole.ACCESS_POINT: SegmentRole.MANAGEMENT,
        DeviceRole.SERVER: SegmentRole.SERVERS,
        DeviceRole.WEB_SERVER: SegmentRole.SERVERS,
        DeviceRole.DNS_SERVER: SegmentRole.SERVERS,
        DeviceRole.DHCP_SERVER: SegmentRole.SERVERS,
        DeviceRole.NTP_SERVER: SegmentRole.SERVERS,
        DeviceRole.TFTP_SERVER: SegmentRole.SERVERS,
        DeviceRole.NVR: SegmentRole.SERVERS,
        DeviceRole.ACCESS_SWITCH: SegmentRole.MANAGEMENT,
        DeviceRole.DISTRIBUTION_SWITCH: SegmentRole.MANAGEMENT,
        DeviceRole.CORE_SWITCH: SegmentRole.MANAGEMENT,
        DeviceRole.WAN_ROUTER: SegmentRole.MANAGEMENT,
        DeviceRole.EDGE_ROUTER: SegmentRole.MANAGEMENT,
        DeviceRole.FIREWALL: SegmentRole.MANAGEMENT,
    }

    def segment_for(self, requirement: EndpointRequirement) -> SegmentRole:
        if requirement.role is DeviceRole.LAPTOP and requirement.wireless:
            return SegmentRole.WIRELESS_CORPORATE
        return self._BY_ROLE.get(requirement.role, SegmentRole.DATA)

    @staticmethod
    def consumes_ipv4(requirement: EndpointRequirement) -> bool:
        """Aísla la política E2 para poder incorporar endpoints no-IP en el futuro."""
        return requirement.role not in {DeviceRole.WAN_ROUTER, DeviceRole.EDGE_ROUTER}
