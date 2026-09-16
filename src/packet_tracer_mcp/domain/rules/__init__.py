"""Validation rules for devices, addressing, DHCP and cabling."""

from .device_rules import validate_devices
from .ip_rules import validate_ips, validate_dhcp
from .cable_rules import validate_links
