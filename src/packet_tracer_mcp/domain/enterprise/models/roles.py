"""Roles lógicos del dominio Enterprise, separados de los modelos físicos."""

from __future__ import annotations

from enum import Enum


class DeviceRole(str, Enum):
    USER_PC = "user_pc"
    LAPTOP = "laptop"
    IP_PHONE = "ip_phone"
    PRINTER = "printer"
    IP_CAMERA = "ip_camera"
    ACCESS_POINT = "access_point"
    SERVER = "server"
    WEB_SERVER = "web_server"
    DNS_SERVER = "dns_server"
    DHCP_SERVER = "dhcp_server"
    NTP_SERVER = "ntp_server"
    TFTP_SERVER = "tftp_server"
    NVR = "nvr"
    ACCESS_SWITCH = "access_switch"
    DISTRIBUTION_SWITCH = "distribution_switch"
    CORE_SWITCH = "core_switch"
    WAN_ROUTER = "wan_router"
    EDGE_ROUTER = "edge_router"
    FIREWALL = "firewall"
