"""Parsers tipados para salidas de seguridad observadas en PT 9.0.1."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ios_terminal import normalize_terminal_output


@dataclass(frozen=True)
class AccessListRuleRow:
    acl_name: str
    sequence: int
    decision: str
    protocol: str
    expression: str
    hit_count: int | None = None


@dataclass(frozen=True)
class IpInterfaceSecurityState:
    interface: str
    inbound_acl: str
    outbound_acl: str


@dataclass(frozen=True)
class NatTranslationRow:
    protocol: str
    inside_global: str
    inside_local: str
    outside_local: str
    outside_global: str


@dataclass(frozen=True)
class NatStatisticsState:
    total_translations: int
    static_translations: int
    dynamic_translations: int
    extended_translations: int
    inside_interfaces: list[str] = field(default_factory=list)
    outside_interfaces: list[str] = field(default_factory=list)
    hits: int = 0
    misses: int = 0


@dataclass(frozen=True)
class PortSecurityState:
    interface: str
    enabled: bool
    port_status: str
    violation_mode: str
    maximum_macs: int
    sticky_macs: int
    violation_count: int


@dataclass(frozen=True)
class DhcpSnoopingState:
    enabled: bool
    vlan_ids: list[int] = field(default_factory=list)
    trusted_interfaces: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DynamicArpInspectionState:
    enabled_vlans: list[int] = field(default_factory=list)
    active_vlans: list[int] = field(default_factory=list)


def parse_show_access_lists(value: str) -> list[AccessListRuleRow]:
    """Parse numbered extended ACLs from the current PT query window."""
    acl_name = ""
    rows: list[AccessListRuleRow] = []
    for line in normalize_terminal_output(value).splitlines():
        header = re.match(r"^Extended IP access list\s+(\S+)\s*$", line.strip(), re.I)
        if header:
            acl_name = header.group(1)
            continue
        match = re.match(
            r"^\s*(\d+)\s+(permit|deny)\s+(\S+)\s+(.+?)"
            r"(?:\s+\((\d+)\s+matches?\))?\s*$",
            line,
            re.I,
        )
        if not acl_name or match is None:
            continue
        rows.append(AccessListRuleRow(
            acl_name=acl_name,
            sequence=int(match.group(1)),
            decision=match.group(2).lower(),
            protocol=match.group(3).lower(),
            expression=match.group(4).strip(),
            hit_count=int(match.group(5)) if match.group(5) is not None else None,
        ))
    return rows


def parse_show_ip_interface_security(value: str) -> IpInterfaceSecurityState | None:
    output = normalize_terminal_output(value)
    first = next((line.strip() for line in output.splitlines() if " is " in line), "")
    interface_match = re.match(r"^(\S+)\s+is\s+", first)
    inbound = re.search(r"(?mi)^\s*Inbound\s+access list is\s+(.+?)\s*$", output)
    outbound = re.search(r"(?mi)^\s*Outgoing access list is\s+(.+?)\s*$", output)
    if interface_match is None or inbound is None or outbound is None:
        return None
    return IpInterfaceSecurityState(
        interface=interface_match.group(1),
        inbound_acl=_normalize_acl_binding(inbound.group(1)),
        outbound_acl=_normalize_acl_binding(outbound.group(1)),
    )


def parse_show_ip_nat_translations(value: str) -> list[NatTranslationRow]:
    rows: list[NatTranslationRow] = []
    for line in normalize_terminal_output(value).splitlines():
        parts = line.split()
        if len(parts) != 5 or parts[0].casefold() in {"pro", "show"}:
            continue
        if parts[0].casefold() not in {"icmp", "tcp", "udp", "---"}:
            continue
        rows.append(NatTranslationRow(*parts))
    return rows


def parse_show_ip_nat_statistics(value: str) -> NatStatisticsState | None:
    output = normalize_terminal_output(value)
    totals = re.search(
        r"Total translations:\s*(\d+)\s*\((\d+) static,\s*(\d+) dynamic,\s*(\d+) extended\)",
        output,
        re.I,
    )
    counters = re.search(r"Hits:\s*(\d+)\s+Misses:\s*(\d+)", output, re.I)
    if totals is None or counters is None:
        return None
    return NatStatisticsState(
        total_translations=int(totals.group(1)),
        static_translations=int(totals.group(2)),
        dynamic_translations=int(totals.group(3)),
        extended_translations=int(totals.group(4)),
        outside_interfaces=_comma_values(output, "Outside Interfaces"),
        inside_interfaces=_comma_values(output, "Inside Interfaces"),
        hits=int(counters.group(1)),
        misses=int(counters.group(2)),
    )


def parse_show_port_security_interface(value: str) -> PortSecurityState | None:
    output = normalize_terminal_output(value)
    fields = {
        key.strip().casefold(): item.strip()
        for line in output.splitlines()
        if ":" in line
        for key, item in [line.split(":", 1)]
    }
    required = {
        "port security", "port status", "violation mode",
        "maximum mac addresses", "sticky mac addresses", "security violation count",
    }
    if not required.issubset(fields):
        return None
    command = re.search(r"show port-security interface\s+(\S+)", output, re.I)
    return PortSecurityState(
        interface=command.group(1) if command else "",
        enabled=fields["port security"].casefold() == "enabled",
        port_status=fields["port status"],
        violation_mode=fields["violation mode"].casefold(),
        maximum_macs=int(fields["maximum mac addresses"]),
        sticky_macs=int(fields["sticky mac addresses"]),
        violation_count=int(fields["security violation count"]),
    )


def parse_show_ip_dhcp_snooping(value: str) -> DhcpSnoopingState | None:
    output = normalize_terminal_output(value)
    enabled = re.search(r"Switch DHCP snooping is\s+(enabled|disabled)", output, re.I)
    if enabled is None:
        return None
    vlan_ids: list[int] = []
    vlan_block = re.search(
        r"configured on following VLANs:\s*\n([^\n]*)", output, re.I,
    )
    if vlan_block:
        vlan_ids = _parse_vlan_values(vlan_block.group(1))
    trusted: list[str] = []
    for line in output.splitlines():
        match = re.match(r"^\s*(\S+)\s+yes\s+(?:unlimited|\d+)\s*$", line, re.I)
        if match:
            trusted.append(match.group(1))
    return DhcpSnoopingState(
        enabled=enabled.group(1).casefold() == "enabled",
        vlan_ids=sorted(set(vlan_ids)),
        trusted_interfaces=sorted(set(trusted), key=str.casefold),
    )


def parse_show_ip_arp_inspection(value: str) -> DynamicArpInspectionState | None:
    enabled: list[int] = []
    active: list[int] = []
    for line in normalize_terminal_output(value).splitlines():
        match = re.match(r"^\s*(\d+)\s+Enabled\s+(Active|Inactive)\b", line, re.I)
        if not match:
            continue
        vlan_id = int(match.group(1))
        enabled.append(vlan_id)
        if match.group(2).casefold() == "active":
            active.append(vlan_id)
    if not enabled and "show ip arp inspection" not in value.casefold():
        return None
    return DynamicArpInspectionState(sorted(set(enabled)), sorted(set(active)))


def _normalize_acl_binding(value: str) -> str:
    return "" if value.strip().casefold() == "not set" else value.strip()


def _comma_values(output: str, label: str) -> list[str]:
    match = re.search(rf"(?mi)^{re.escape(label)}:\s*(.*?)\s*$", output)
    if not match:
        return []
    return [item.strip() for item in match.group(1).split(",") if item.strip()]


def _parse_vlan_values(value: str) -> list[int]:
    result: list[int] = []
    for item in re.split(r"[ ,]+", value.strip()):
        if not item:
            continue
        if "-" in item:
            start, end = item.split("-", 1)
            result.extend(range(int(start), int(end) + 1))
        elif item.isdigit():
            result.append(int(item))
    return result
