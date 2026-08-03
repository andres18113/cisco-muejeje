"""Invariantes defensivos del ConfigurationPlan E5."""

from __future__ import annotations

import ipaddress
from collections import defaultdict

from ..models.configuration import (
    ConfigurationAction,
    ConfigurationIssue,
    ConfigurationIssueCode,
    ConfigurationIssueSeverity,
    ConfigureAccessPort,
    ConfigureDhcpPool,
    ConfigureTrunk,
    SetEndpointStaticAddress,
)


def _error(code: ConfigurationIssueCode, message: str, subject: str = "") -> ConfigurationIssue:
    return ConfigurationIssue(
        severity=ConfigurationIssueSeverity.ERROR,
        code=code,
        message=message,
        subject=subject,
    )


def validate_configuration_actions(
    actions: list[ConfigurationAction],
) -> list[ConfigurationIssue]:
    issues: list[ConfigurationIssue] = []
    interface_modes: dict[tuple[str, str], set[str]] = defaultdict(set)
    static_ips: dict[str, list[str]] = defaultdict(list)
    pools: list[ConfigureDhcpPool] = []

    for action in actions:
        if isinstance(action, ConfigureAccessPort):
            interface_modes[(action.device_id, action.interface)].add("access")
        elif isinstance(action, ConfigureTrunk):
            interface_modes[(action.device_id, action.interface)].add("trunk")
        elif isinstance(action, SetEndpointStaticAddress):
            static_ips[action.ipv4].append(action.id)
        elif isinstance(action, ConfigureDhcpPool):
            pools.append(action)

    for (device_id, interface), modes in sorted(interface_modes.items()):
        if modes == {"access", "trunk"}:
            issues.append(_error(
                ConfigurationIssueCode.ACCESS_TRUNK_CONFLICT,
                f"{device_id} {interface} cannot be both access and trunk.",
                f"{device_id}:{interface}",
            ))

    for address, action_ids in sorted(static_ips.items()):
        if len(action_ids) > 1:
            issues.append(_error(
                ConfigurationIssueCode.DUPLICATE_IPV4,
                f"IPv4 {address} is assigned by multiple static actions.",
                address,
            ))

    for pool in pools:
        start = ipaddress.ip_address(pool.lease_start)
        end = ipaddress.ip_address(pool.lease_end)
        excluded = [
            (ipaddress.ip_address(item.start), ipaddress.ip_address(item.end))
            for item in pool.excluded_ranges
        ]
        for address in sorted(static_ips):
            value = ipaddress.ip_address(address)
            if start <= value <= end and not any(left <= value <= right for left, right in excluded):
                issues.append(_error(
                    ConfigurationIssueCode.DHCP_STATIC_COLLISION,
                    f"Static IPv4 {address} overlaps DHCP pool {pool.pool_name} without exclusion.",
                    pool.id,
                ))
    return issues
