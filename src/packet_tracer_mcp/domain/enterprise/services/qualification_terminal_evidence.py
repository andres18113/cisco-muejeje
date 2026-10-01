"""Pure predicates over terminal client, pool, server and router observations.

Each predicate decides whether one final observation is complete for the
claim its stage makes. Distinct predicates keep distinct meanings; none of
them dispatches or reads anything.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from ipaddress import IPv4Address, IPv4Network
from typing import Any

from ..models.service_plan import ConfigureServerDhcpPool
from ..models.service_qualification import SP2_MIXED_SERVER
from .dhcp_lease_evidence import (
    TERMINATION_NULL,
    TERMINATION_THROW,
    AddressRange,
    LeaseScan,
    normalized_mac,
)


def sp1_terminal_bindings_observed(bindings: object, clients: Sequence[str]) -> bool:
    """Require successful static address, gateway and resolver observations."""
    expected = set(clients)
    if (
        len(expected) != len(clients)
        or not isinstance(bindings, list)
        or len(bindings) != len(clients)
    ):
        return False

    def concrete_ipv4(value: object) -> bool:
        if not isinstance(value, str):
            return False
        try:
            address = IPv4Address(value)
        except ValueError:
            return False
        return not address.is_unspecified and not address.is_multicast

    seen: set[str] = set()
    for row in bindings:
        if not isinstance(row, Mapping):
            return False
        name = row.get("device")
        if not isinstance(name, str) or name not in expected or name in seen:
            return False
        seen.add(name)
        if not (
            row.get("found") is True
            and row.get("port_found") is True
            and row.get("error") == ""
            and concrete_ipv4(row.get("ipv4"))
            and row.get("dns_api") is True
            and row.get("dns_error") == ""
            and concrete_ipv4(row.get("dns_server"))
        ):
            return False
        mask = row.get("netmask")
        if not isinstance(mask, str):
            return False
        try:
            IPv4Address(mask)
            network = IPv4Network("0.0.0.0/" + mask)
            if str(network.netmask) != mask:
                return False
        except ValueError:
            return False
        gateways = row.get("gateway_reads")
        if not isinstance(gateways, list):
            return False
        processes: set[str] = set()
        answered: list[str] = []
        for reading in gateways:
            if not isinstance(reading, Mapping):
                return False
            process = reading.get("process")
            if (
                not isinstance(process, str)
                or process not in {"HostIp", "HostIpProcess"}
                or process in processes
                or type(reading.get("found")) is not bool
                or type(reading.get("api")) is not bool
                or not isinstance(reading.get("error"), str)
            ):
                return False
            processes.add(process)
            if reading["api"] is True and reading["error"] == "":
                if reading["found"] is not True or not concrete_ipv4(
                    reading.get("value")
                ):
                    return False
                answered.append(reading["value"])
        if (
            processes != {"HostIp", "HostIpProcess"}
            or not answered
            or len(set(answered)) != 1
        ):
            return False
    return seen == expected


def sp2_mixed_bindings_usable(
    bindings: object, pools: Mapping[str, ConfigureServerDhcpPool]
) -> bool:
    """Whether every selected client's final binding was read and is usable.

    The probe emits a row per requested client even when its lookup failed,
    so a row count is not an observation. `pools` maps each selected client
    to its planned physical pool; each row must name its client once, have
    found the device and its port without error, and read an address inside
    that pool's lease window with its mask, gateway and resolver.
    """
    if not isinstance(bindings, list) or len(bindings) != len(pools):
        return False
    rows: dict[object, Mapping[str, Any]] = {}
    for row in bindings:
        if not isinstance(row, Mapping) or row.get("device") in rows:
            return False
        rows[row.get("device")] = row
    if set(rows) != set(pools):
        return False
    for name, row in rows.items():
        pool = pools[name]
        gateways = row.get("gateway_reads")
        answered = (
            [
                item.get("value")
                for item in gateways
                if isinstance(item, Mapping)
                and item.get("api") is True
                and item.get("error") == ""
            ]
            if isinstance(gateways, list)
            else []
        )
        if not (
            row.get("found") is True
            and row.get("port_found") is True
            and row.get("error") == ""
            and AddressRange(pool.lease_start, pool.lease_end).contains(
                str(row.get("ipv4") or "")
            )
            and row.get("netmask") == pool.netmask
            and answered
            and all(value == pool.gateway for value in answered)
            and row.get("dns_api") is True
            and row.get("dns_error") == ""
            and row.get("dns_server") == pool.dns_server
        ):
            return False
    return True


def sp2_mixed_scan_complete(
    scan: LeaseScan, identities: Sequence[tuple[str, str]]
) -> bool:
    """Whether one final pool scan holds exactly these clients' leases.

    `identities` are the pool's clients as (address, normalized MAC). The rows
    must be contiguous from index 0, cleanly classified (not repeated or
    malformed), within capacity, and join those identities one to one; at
    least two later indices, all of the window's, must each be a null or the
    measured out-of-range throw from the index call itself. An absent pool, a
    failed read, a row whose fields failed, or an unexplained error is not a
    scanned table.
    """
    entries = list(scan.entries)
    count = len(scan.rows)
    found = [(row.ip, normalized_mac(row.mac)) for row in scan.rows]
    return bool(
        scan.observed
        and not scan.end_observation.get("scan_error")
        and scan.termination in {TERMINATION_NULL, TERMINATION_THROW}
        and scan.capacity is not None
        and count <= scan.capacity
        and len(entries) >= count + 2
        and [row.index for row in scan.rows] == list(range(count))
        and len(set(identities)) == len(identities)
        and all(mac for _ip, mac in identities)
        and sorted(found) == sorted(identities)
        and all(
            item.get("return_kind") == "null"
            or (
                item.get("return_kind") == "throw"
                and item.get("end_semantics") == "observed_native_index_end"
                and bool(scan.reader_provenance)
            )
            for item in entries[count:]
        )
    )


def sp2_mixed_server_complete(server: object, pools: Sequence[str]) -> bool:
    """Whether the final read saw the enabled process with exactly its pools."""
    rows = server.get("pools") if isinstance(server, Mapping) else None
    return bool(
        isinstance(server, Mapping)
        and server.get("device") == SP2_MIXED_SERVER
        and server.get("interface") == "FastEthernet0"
        and server.get("found") is True
        and server.get("process_found") is True
        and server.get("error") == ""
        and server.get("truncated") is False
        and server.get("enabled") is True
        and isinstance(rows, list)
        and server.get("pool_count") == len(rows) == len(pools)
        and all(isinstance(row, Mapping) for row in rows)
        and sorted(row.get("name") for row in rows) == sorted(pools)
    )


def terminal_router_rows_complete(
    rows: Sequence[Mapping[str, Any]], routers: Sequence[str]
) -> bool:
    """Require every final router query to be fresh, complete and unique."""
    expected = {
        (name, query)
        for name in routers
        for query in ("show_ip_interface_brief", "show_ip_route")
    }
    identities = [(row.get("device"), row.get("query")) for row in rows]
    return (
        len(rows) == len(expected)
        and len(set(identities)) == len(rows)
        and set(identities) == expected
        and all(
            row.get("executed") is True
            and row.get("fresh_output_observed") is True
            and row.get("output_complete") is True
            and isinstance(row.get("output"), str)
            and bool(row["output"])
            and type(row.get("output_characters")) is int
            and len(row["output"]) == row["output_characters"]
            and row.get("truncated_by_pager") is False
            and row.get("observed_device_name") == row.get("device")
            and row.get("device_identity_provenance") == "confirmed_unique"
            and row.get("failure_reason") == ""
            for row in rows
        )
    )
