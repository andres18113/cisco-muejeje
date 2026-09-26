"""Bound the candidate native Server-PT DHCP policy independently of a fixture."""

from __future__ import annotations

from ipaddress import IPv4Address, IPv4Network, ip_address, ip_network

from ..models.service_plan import NativeDhcpPolicyScope

MAX_NATIVE_CLIENTS = 16
MAX_NATIVE_EXCLUSIONS = 16


def native_policy_network(
    *,
    network: str,
    netmask: str,
    gateway: str,
    dns_server: str,
    lease_start: str,
    lease_end: str,
    max_users: int,
    excluded_ranges: list[tuple[str, str]],
    selected_count: int,
) -> IPv4Network | None:
    """Return the admitted /24 or None; this is scope, not backend proof."""
    try:
        subnet = ip_network(f"{network}/{netmask}", strict=True)
        first = ip_address(lease_start)
        last = ip_address(lease_end)
        gateway_address = ip_address(gateway)
        dns_address = ip_address(dns_server)
        exclusions = [
            (ip_address(start), ip_address(end)) for start, end in excluded_ranges
        ]
    except ValueError:
        return None
    if (
        not isinstance(subnet, IPv4Network)
        or subnet.prefixlen != 24
        or not all(
            isinstance(value, IPv4Address)
            for value in (first, last, gateway_address, dns_address)
        )
        or isinstance(max_users, bool)
        or not isinstance(max_users, int)
        or not 1 <= selected_count <= max_users <= MAX_NATIVE_CLIENTS
        or len(exclusions) > MAX_NATIVE_EXCLUSIONS
        or first not in subnet
        or last not in subnet
        or first in {subnet.network_address, subnet.broadcast_address}
        or last in {subnet.network_address, subnet.broadcast_address}
        or int(last) - int(first) + 1 != max_users
        or gateway_address not in subnet
        or gateway_address in {subnet.network_address, subnet.broadcast_address}
    ):
        return None
    for start, end in exclusions:
        if (
            not isinstance(start, IPv4Address)
            or not isinstance(end, IPv4Address)
            or start not in subnet
            or end not in subnet
            or start > end
            or (start <= last and first <= end)
        ):
            return None
    if any(
        exclusions[index][0] <= exclusions[index - 1][1]
        for index in range(1, len(exclusions))
    ):
        return None
    return subnet


def native_policy_within_scope(
    scope: NativeDhcpPolicyScope | None,
    *,
    network: str,
    netmask: str,
    gateway: str,
    dns_server: str,
    lease_start: str,
    lease_end: str,
    max_users: int,
    exclusion_count: int,
) -> bool:
    """Admit only the bounds carried by the recorded capability."""
    if scope is None:
        return False
    try:
        first = ip_address(scope.first_lease)
        last = ip_address(scope.last_lease)
        start = ip_address(lease_start)
        end = ip_address(lease_end)
    except ValueError:
        return False
    return (
        all(isinstance(value, IPv4Address) for value in (first, last, start, end))
        and network == scope.network
        and netmask == scope.netmask
        and gateway == scope.gateway
        and dns_server == scope.dns_server
        and first <= start <= end <= last
        and 1 <= max_users <= scope.max_users <= MAX_NATIVE_CLIENTS
        and 0 <= exclusion_count <= scope.max_exclusion_ranges <= MAX_NATIVE_EXCLUSIONS
    )
