"""Typed readings of a router's forwarding state, as the domain consumes them.

The IOS reader in infrastructure produces these values; the routed readiness
rule and E5 route read-back consume them. They carry what one fresh reading
said and nothing else: a row the parser could not read is kept as unparsed
text, never dropped, and an index is built once per reading so that many
dependents can ask about the same table without rescanning it.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass, field

#: The attribution a registered IOS read carries when it came from exactly
#: the device asked about (the same value the access observer requires).
CONFIRMED_UNIQUE_IDENTITY = "confirmed_unique"

#: Route codes that mean "this router delivers to that prefix itself".
CONNECTED_ROUTE_CODES = frozenset({"C"})


@dataclass(frozen=True)
class ObservedRoute:
    """One route row of a `show ip route` reading.

    `next_hop` is empty for a connected row. `interface` is empty when the row
    printed none. Several rows may share one prefix: equal-cost paths and
    duplicates are both retained so a decision can see them.
    """

    code: str
    network: str
    prefix_length: int
    next_hop: str = ""
    interface: str = ""
    distance: int | None = None
    metric: int | None = None

    @property
    def connected(self) -> bool:
        """Whether this row is a directly connected network."""
        return self.code in CONNECTED_ROUTE_CODES


@dataclass(frozen=True)
class RouteTableReading:
    """One parsed routing table.

    `routing_enabled` is False only for the host form an L3 switch prints
    while IPv4 routing is off, and None when the output shows neither form.
    `parse_complete` says the table header was seen and every route-like line
    parsed; the transport's own completeness (pager, freshness) is carried by
    the reading that holds this table.
    """

    rows: tuple[ObservedRoute, ...] = ()
    unparsed: tuple[str, ...] = ()
    gateway_of_last_resort: str = ""
    routing_enabled: bool | None = None
    header_seen: bool = False
    _index: dict[int, dict[int, tuple[ObservedRoute, ...]]] = field(
        default_factory=dict, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        """Index the rows once by prefix length and network."""
        grouped: dict[int, dict[int, list[ObservedRoute]]] = {}
        for row in self.rows:
            try:
                network = int(ipaddress.IPv4Address(row.network))
            except ValueError:
                continue
            grouped.setdefault(row.prefix_length, {}).setdefault(network, []).append(
                row
            )
        object.__setattr__(
            self,
            "_index",
            {
                length: {key: tuple(value) for key, value in rows.items()}
                for length, rows in grouped.items()
            },
        )

    @property
    def parse_complete(self) -> bool:
        """Whether the header was read and no route-like line was left over."""
        return self.header_seen and not self.unparsed

    def longest_match(self, address: str) -> tuple[ObservedRoute, ...]:
        """Return every row of the longest prefix that contains `address`."""
        value = int(ipaddress.IPv4Address(address))
        for length in range(32, -1, -1):
            rows = self._index.get(length)
            if not rows:
                continue
            mask = ((1 << 32) - 1) ^ ((1 << (32 - length)) - 1) if length else 0
            found = rows.get(value & mask)
            if found:
                return found
        return ()

    def exact(self, network: str, prefix_length: int) -> tuple[ObservedRoute, ...]:
        """Return every row for exactly this prefix."""
        return self._index.get(prefix_length, {}).get(
            int(ipaddress.IPv4Address(network)), ()
        )


@dataclass(frozen=True)
class ObservedInterface:
    """One `show ip interface brief` row."""

    name: str
    ipv4: str
    status: str
    protocol: str

    @property
    def up(self) -> bool:
        """Whether the interface is up/up."""
        return self.status.casefold() == "up" and self.protocol.casefold() == "up"


@dataclass(frozen=True)
class DeviceForwardingReading:
    """One device's `show ip interface brief` and `show ip route` in one round.

    Both registered reads must have executed, returned fresh output walked to
    the prompt, and been attributed to exactly this device; the table must
    parse completely with IPv4 routing on. Anything less is kept as observed
    and is not authoritative, so it can refuse nothing and admit nothing.
    """

    device_name: str
    executed: bool = False
    fresh_output_observed: bool = False
    output_complete: bool = False
    observed_device_name: str = ""
    device_identity_provenance: str = ""
    route_table: RouteTableReading | None = None
    interfaces: tuple[ObservedInterface, ...] = ()
    channel_calls: int = 0
    call_budget_exhausted: bool = False
    after_deadline: bool = False
    failure_reason: str = ""

    @property
    def authoritative(self) -> bool:
        """Whether this reading may speak for its device at all."""
        return bool(
            self.executed
            and self.fresh_output_observed
            and self.output_complete
            and not self.call_budget_exhausted
            and not self.after_deadline
            and self.observed_device_name == self.device_name
            and self.device_identity_provenance == CONFIRMED_UNIQUE_IDENTITY
            and self.route_table is not None
            and self.route_table.parse_complete
            and self.route_table.routing_enabled is True
        )

    def interface(self, name: str) -> tuple[ObservedInterface, ...]:
        """Return every row naming this interface (duplicates retained)."""
        wanted = name.casefold()
        return tuple(item for item in self.interfaces if item.name.casefold() == wanted)


@dataclass(frozen=True)
class RoutedForwardingRound:
    """Every router of one routed group read once, or as many as time allowed."""

    index: int
    elapsed_ms: int
    readings: tuple[DeviceForwardingReading, ...]
    complete: bool

    def reading(self, device_name: str) -> DeviceForwardingReading | None:
        """Return this round's reading of one device, if it was taken."""
        return next(
            (item for item in self.readings if item.device_name == device_name), None
        )


@dataclass(frozen=True)
class RoutedForwardingObservation:
    """One bounded routed-forwarding episode over one group's routers."""

    device_names: tuple[str, ...]
    rounds: tuple[RoutedForwardingRound, ...] = ()
    deadline_seconds: float = 0.0
    elapsed_ms: int = 0
    deadline_reached: bool = False
    deadline_cause: str = ""
    episode_end_reason: str = ""
    channel_calls: int = 0


def interfaces_by_name(
    rows: Iterable[ObservedInterface],
) -> dict[str, tuple[ObservedInterface, ...]]:
    """Index interface rows once by case-folded name, keeping duplicates."""
    grouped: dict[str, list[ObservedInterface]] = {}
    for row in rows:
        grouped.setdefault(row.name.casefold(), []).append(row)
    return {key: tuple(value) for key, value in grouped.items()}
