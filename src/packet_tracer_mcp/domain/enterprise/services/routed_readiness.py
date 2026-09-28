"""Operational routed forwarding, decided from fresh router readings.

A routed dependency is admitted only when one timely, complete round of
authoritative readings shows, on every router its compiled chains name:

- each gateway and transit interface it uses up/up with its planned address;
- towards the server's address, every hop's longest-prefix match using only
  the planned next hop through the planned direct egress, and the server's
  gateway router delivering on its connected gateway interface;
- the same back towards the client's address.

A configured route, a successful setter or a link-up flag is not evidence
here; only these rows are. A wrong next hop, an extra equal-cost next hop, a
route that shadows the connected network, an interface down, a missing row
or an unreadable router refuses. Loops need no special case: the chain is the
compiled one, so a looping table shows up as a wrong next hop on some hop.
The rows are indexed once per reading, and every dependent of the group is
decided from the same round.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ..models.routed_forwarding import (
    DeviceForwardingReading,
    RoutedForwardingObservation,
    RoutedForwardingRound,
    RouteTableReading,
)
from ..models.service_plan import ServiceVerificationKind

#: Dimensions of a routed verdict, most specific first.
ROUTED_NOT_OBSERVED = "NOT_OBSERVED"
ROUTED_DEADLINE = "DEADLINE"
ROUTED_UNREADABLE = "ROUTER_UNREADABLE"
ROUTED_INTERFACE = "INTERFACE_NOT_FORWARDING"
ROUTED_ROUTE = "ROUTE_NOT_FORWARDING"
ROUTED_DRIFT = "ROUTE_DRIFT_AFTER_ADMISSION"
ROUTED_NONE = "NONE"

CAUSE_NO_ROUND = "no_routed_round_taken"
CAUSE_WINDOW_ENDED_UNSETTLED = "routed_window_ended_before_every_path_forwarded"
END_REASON_SETTLED = "required_paths_forwarding"


@dataclass(frozen=True)
class GatewayInterfaceExpectation:
    """One gateway interface a chain starts or ends on."""

    device_id: str
    interface: str
    ipv4: str


@dataclass(frozen=True)
class HopExpectation:
    """One compiled forwarding decision a router must still be making."""

    device_id: str
    next_hop: str
    egress_interface: str
    egress_ipv4: str
    peer_device_id: str
    ingress_interface: str
    ingress_ipv4: str


@dataclass(frozen=True)
class RoutedDependent:
    """One request whose routed path this group must prove."""

    expectation_id: str
    service_id: str
    kind: ServiceVerificationKind | str
    client_device_id: str
    host_device_id: str
    client_ipv4: str
    host_ipv4: str
    client_gateway: GatewayInterfaceExpectation
    host_gateway: GatewayInterfaceExpectation
    forward: tuple[HopExpectation, ...] = ()
    reverse: tuple[HopExpectation, ...] = ()
    client_network: str = ""

    @property
    def device_ids(self) -> tuple[str, ...]:
        """Every router this dependent's two chains read, in chain order."""
        found = [self.client_gateway.device_id]
        for hop in (*self.forward, *self.reverse):
            found.extend((hop.device_id, hop.peer_device_id))
        found.append(self.host_gateway.device_id)
        return tuple(dict.fromkeys(found))


GroupKey = tuple[str, str, str]


@dataclass(frozen=True)
class RoutedRequirement:
    """Every dependent between one client segment and one server segment."""

    client_segment_id: str
    host_segment_id: str
    device_ids: tuple[str, ...]
    dependents: tuple[RoutedDependent, ...]
    purpose: str = "routed_forwarding"

    @property
    def key(self) -> GroupKey:
        """Return the complete identity one routed observation answers."""
        return (self.purpose, self.client_segment_id, self.host_segment_id)


@dataclass(frozen=True)
class RoutedVerdict:
    """Whether one dependent's two chains forward in one set of readings."""

    admitted: bool
    dimension: str
    cause: str = ""


def _interface_cause(
    reading: DeviceForwardingReading, expected_interface: str, expected_ipv4: str
) -> str:
    rows = reading.interface(expected_interface)
    if len(rows) != 1:
        return f"interface_rows:{reading.device_name}:{expected_interface}:{len(rows)}"
    row = rows[0]
    if row.ipv4 != expected_ipv4:
        return (
            f"interface_address:{reading.device_name}:{expected_interface}:{row.ipv4}"
        )
    if not row.up:
        return (
            f"interface_down:{reading.device_name}:{expected_interface}:"
            f"{row.status}/{row.protocol}"
        )
    return ""


def network_route_coverage_cause(
    table: RouteTableReading,
    network: str,
    *,
    next_hop: str = "",
    interface: str,
    connected: bool = False,
    local_address: str = "",
) -> str:
    """Prove one observed route decision covers the whole DHCP segment.

    A more specific route within the segment is acceptable only when it
    preserves the same next hop and egress. The table must already be a
    complete, attributed router reading at the caller's boundary.
    """
    try:
        target = ipaddress.IPv4Network(network, strict=True)
        selected = table.longest_match(str(target.network_address))
        if not selected:
            return "network_route_missing"
        overlapping = [
            (ipaddress.IPv4Network(f"{row.network}/{row.prefix_length}"), row)
            for row in table.rows
            if ipaddress.IPv4Network(f"{row.network}/{row.prefix_length}").overlaps(
                target
            )
        ]
        selected_networks = [
            ipaddress.IPv4Network(f"{row.network}/{row.prefix_length}")
            for row in selected
        ]
    except ValueError:
        return "network_route_unreadable"
    if any(not target.subnet_of(item) for item in selected_networks):
        return "network_route_partial_coverage"

    def follows(row) -> bool:
        if connected:
            return row.connected and row.interface.casefold() == interface.casefold()
        return row.next_hop == next_hop and (
            not row.interface or row.interface.casefold() == interface.casefold()
        )

    if any(not follows(row) for row in selected):
        return "network_route_selected_path_differs"
    selected_prefix = selected_networks[0].prefixlen
    if any(
        route.prefixlen > selected_prefix
        and not (
            connected
            and row.code == "L"
            and row.network == local_address
            and row.interface.casefold() == interface.casefold()
        )
        and not follows(row)
        for route, row in overlapping
    ):
        return "network_route_shadow"
    return ""


def _direction(
    start: GatewayInterfaceExpectation,
    hops: Sequence[HopExpectation],
    end: GatewayInterfaceExpectation,
    destination: str,
    readings: Mapping[str, DeviceForwardingReading],
    *,
    destination_network: str = "",
) -> RoutedVerdict:
    """Walk one compiled chain against the readings; the first break decides."""

    def reading_of(device_id: str) -> DeviceForwardingReading | RoutedVerdict:
        reading = readings.get(device_id)
        if reading is None:
            return RoutedVerdict(False, ROUTED_NOT_OBSERVED, f"not_read:{device_id}")
        if not reading.authoritative:
            return RoutedVerdict(
                False,
                ROUTED_UNREADABLE,
                f"unreadable:{reading.device_name}:"
                f"{reading.failure_reason or 'not_authoritative'}",
            )
        return reading

    first = reading_of(start.device_id)
    if isinstance(first, RoutedVerdict):
        return first
    cause = _interface_cause(first, start.interface, start.ipv4)
    if cause:
        return RoutedVerdict(False, ROUTED_INTERFACE, cause)
    for hop in hops:
        here = reading_of(hop.device_id)
        if isinstance(here, RoutedVerdict):
            return here
        table = here.route_table
        assert table is not None  # authoritative implies a parsed table
        rows = table.longest_match(destination)
        if destination_network:
            network_cause = network_route_coverage_cause(
                table,
                destination_network,
                next_hop=hop.next_hop,
                interface=hop.egress_interface,
            )
            if network_cause:
                return RoutedVerdict(
                    False,
                    ROUTED_ROUTE,
                    f"{network_cause}:{here.device_name}:{destination_network}",
                )
        if not rows:
            return RoutedVerdict(
                False, ROUTED_ROUTE, f"route_missing:{here.device_name}:{destination}"
            )
        if any(row.connected for row in rows):
            return RoutedVerdict(
                False,
                ROUTED_ROUTE,
                f"route_unexpectedly_connected:{here.device_name}:{destination}",
            )
        hops_seen = sorted({row.next_hop for row in rows})
        if hops_seen != [hop.next_hop]:
            return RoutedVerdict(
                False,
                ROUTED_ROUTE,
                f"route_next_hop:{here.device_name}:{destination}:"
                + ",".join(hops_seen),
            )
        printed = sorted(
            {
                row.interface
                for row in rows
                if row.interface
                and row.interface.casefold() != hop.egress_interface.casefold()
            }
        )
        if printed:
            return RoutedVerdict(
                False,
                ROUTED_ROUTE,
                f"route_output_interface:{here.device_name}:{destination}:"
                + ",".join(printed),
            )
        resolved = table.longest_match(hop.next_hop)
        if not resolved:
            return RoutedVerdict(
                False,
                ROUTED_ROUTE,
                f"next_hop_unresolved:{here.device_name}:{hop.next_hop}",
            )
        if len(resolved) != 1:
            return RoutedVerdict(
                False,
                ROUTED_ROUTE,
                f"next_hop_ambiguous:{here.device_name}:{hop.next_hop}:{len(resolved)}",
            )
        [neighbor] = resolved
        if not neighbor.connected:
            return RoutedVerdict(
                False,
                ROUTED_ROUTE,
                f"next_hop_not_direct:{here.device_name}:{hop.next_hop}:"
                f"{neighbor.code}/{neighbor.network}/{neighbor.prefix_length}",
            )
        if neighbor.interface.casefold() != hop.egress_interface.casefold():
            return RoutedVerdict(
                False,
                ROUTED_ROUTE,
                f"next_hop_egress:{here.device_name}:{hop.next_hop}:"
                f"{neighbor.interface}",
            )
        cause = _interface_cause(here, hop.egress_interface, hop.egress_ipv4)
        if cause:
            return RoutedVerdict(False, ROUTED_INTERFACE, cause)
        peer = reading_of(hop.peer_device_id)
        if isinstance(peer, RoutedVerdict):
            return peer
        cause = _interface_cause(peer, hop.ingress_interface, hop.ingress_ipv4)
        if cause:
            return RoutedVerdict(False, ROUTED_INTERFACE, cause)
    last = reading_of(end.device_id)
    if isinstance(last, RoutedVerdict):
        return last
    table = last.route_table
    assert table is not None
    rows = table.longest_match(destination)
    if destination_network:
        network_cause = network_route_coverage_cause(
            table,
            destination_network,
            interface=end.interface,
            connected=True,
            local_address=end.ipv4,
        )
        if network_cause:
            return RoutedVerdict(
                False,
                ROUTED_ROUTE,
                f"{network_cause}:{last.device_name}:{destination_network}",
            )
    delivering = [
        row
        for row in rows
        if row.connected and row.interface.casefold() == end.interface.casefold()
    ]
    if not rows or len(delivering) != len(rows):
        return RoutedVerdict(
            False,
            ROUTED_ROUTE,
            f"destination_not_connected:{last.device_name}:{destination}:"
            + ",".join(
                sorted(f"{row.code}/{row.interface or row.next_hop}" for row in rows)
            ),
        )
    cause = _interface_cause(last, end.interface, end.ipv4)
    if cause:
        return RoutedVerdict(False, ROUTED_INTERFACE, cause)
    return RoutedVerdict(True, ROUTED_NONE)


def routed_verdict(
    dependent: RoutedDependent,
    readings: Mapping[str, DeviceForwardingReading],
) -> RoutedVerdict:
    """Decide one dependent from readings keyed by semantic device id."""
    forward = _direction(
        dependent.client_gateway,
        dependent.forward,
        dependent.host_gateway,
        dependent.host_ipv4,
        readings,
    )
    if not forward.admitted:
        return forward
    reverse = _direction(
        dependent.host_gateway,
        dependent.reverse,
        dependent.client_gateway,
        dependent.client_ipv4,
        readings,
        destination_network=(
            dependent.client_network
            if dependent.kind is ServiceVerificationKind.DHCP_LEASE
            else ""
        ),
    )
    if not reverse.admitted:
        return RoutedVerdict(False, reverse.dimension, "return_" + reverse.cause)
    return reverse


def round_readings(
    round_: RoutedForwardingRound, names: Mapping[str, str]
) -> dict[str, DeviceForwardingReading]:
    """Key an exact, uniquely attributed round by semantic device id."""
    observed = [item.device_name for item in round_.readings]
    if len(observed) != len(names) or set(observed) != set(names.values()):
        return {}
    by_name = {item.device_name: item for item in round_.readings}
    return {
        device_id: by_name[name] for device_id, name in names.items() if name in by_name
    }


def round_admits_all(
    requirement: RoutedRequirement,
    round_: RoutedForwardingRound,
    names: Mapping[str, str],
) -> bool:
    """Whether one complete round admits every dependent of the group."""
    if not round_.complete:
        return False
    readings = round_readings(round_, names)
    return all(
        routed_verdict(item, readings).admitted for item in requirement.dependents
    )


def routed_verdicts(
    requirement: RoutedRequirement,
    observation: RoutedForwardingObservation,
    names: Mapping[str, str],
) -> dict[str, RoutedVerdict]:
    """Decide every dependent from one episode.

    Only an episode that ended because a complete round admitted every
    dependent admits anything. A window that ran out admits nothing; each
    dependent then carries the cause its last complete round showed, which is
    what a narrowed episode may ask about again.
    """
    if not observation.rounds:
        return {
            item.expectation_id: RoutedVerdict(
                False, ROUTED_NOT_OBSERVED, CAUSE_NO_ROUND
            )
            for item in requirement.dependents
        }
    complete = [item for item in observation.rounds if item.complete]
    deciding = complete[-1] if complete else None
    settled = observation.episode_end_reason == END_REASON_SETTLED
    verdicts: dict[str, RoutedVerdict] = {}
    readings = round_readings(deciding, names) if deciding is not None else {}
    for dependent in requirement.dependents:
        if deciding is None:
            verdicts[dependent.expectation_id] = RoutedVerdict(
                False, ROUTED_NOT_OBSERVED, CAUSE_NO_ROUND
            )
            continue
        verdict = routed_verdict(dependent, readings)
        if settled and verdict.admitted:
            verdicts[dependent.expectation_id] = verdict
        elif verdict.admitted:
            verdicts[dependent.expectation_id] = RoutedVerdict(
                False, ROUTED_DEADLINE, CAUSE_WINDOW_ENDED_UNSETTLED
            )
        else:
            verdicts[dependent.expectation_id] = verdict
    return verdicts


def admitted_in_last_round(
    requirement: RoutedRequirement,
    observation: RoutedForwardingObservation,
    names: Mapping[str, str],
) -> tuple[str, ...]:
    """Return the dependents the last complete round showed forwarding.

    A narrowing hint only: it never admits anything on its own.
    """
    complete = [item for item in observation.rounds if item.complete]
    if not complete:
        return ()
    readings = round_readings(complete[-1], names)
    return tuple(
        item.expectation_id
        for item in requirement.dependents
        if routed_verdict(item, readings).admitted
    )


def routed_facts(
    requirement: RoutedRequirement,
    observation: RoutedForwardingObservation,
    names: Mapping[str, str],
) -> dict[str, object]:
    """Summarize one episode for the record without copying raw terminals.

    The deciding round's rows that the dependents' chains used are kept per
    device: the interface rows asked about and the longest-match route rows
    for each destination and next hop, so the decision can be re-derived.
    """
    complete = [item for item in observation.rounds if item.complete]
    deciding = complete[-1] if complete else None
    devices = (
        routed_round_facts(requirement.dependents, deciding, names)
        if deciding is not None
        else {}
    )
    return {
        "rounds": len(observation.rounds),
        "deciding_round": deciding.index if deciding is not None else None,
        "episode_end_reason": observation.episode_end_reason,
        "deadline_seconds": observation.deadline_seconds,
        "elapsed_ms": observation.elapsed_ms,
        "deadline_reached": observation.deadline_reached,
        "channel_calls": observation.channel_calls,
        "devices": devices,
    }


def routed_round_facts(
    dependents: Sequence[RoutedDependent],
    round_: RoutedForwardingRound,
    names: Mapping[str, str],
    *,
    device_ids: set[str] | None = None,
) -> dict[str, object]:
    """Keep only shared route and interface facts relevant to these chains."""
    readings = round_readings(round_, names)
    wanted_interfaces: dict[str, set[str]] = {}
    wanted_destinations: dict[str, set[str]] = {}
    wanted_networks: dict[str, set[str]] = {}
    for dependent in dependents:
        if (
            dependent.kind is ServiceVerificationKind.DHCP_LEASE
            and dependent.client_network
        ):
            for hop in dependent.reverse:
                wanted_networks.setdefault(hop.device_id, set()).add(
                    dependent.client_network
                )
            wanted_networks.setdefault(dependent.client_gateway.device_id, set()).add(
                dependent.client_network
            )
        for gateway in (dependent.client_gateway, dependent.host_gateway):
            wanted_interfaces.setdefault(gateway.device_id, set()).add(
                gateway.interface
            )
        for destination, hops, end in (
            (dependent.host_ipv4, dependent.forward, dependent.host_gateway),
            (dependent.client_ipv4, dependent.reverse, dependent.client_gateway),
        ):
            for hop in hops:
                wanted_interfaces.setdefault(hop.device_id, set()).add(
                    hop.egress_interface
                )
                wanted_interfaces.setdefault(hop.peer_device_id, set()).add(
                    hop.ingress_interface
                )
                wanted_destinations.setdefault(hop.device_id, set()).update(
                    (destination, hop.next_hop)
                )
            wanted_destinations.setdefault(end.device_id, set()).add(destination)
    devices: dict[str, object] = {}
    for device_id, reading in sorted(readings.items()):
        if device_ids is not None and device_id not in device_ids:
            continue
        table = reading.route_table
        devices[device_id] = {
            "device_name": reading.device_name,
            "authoritative": reading.authoritative,
            "failure_reason": reading.failure_reason,
            "route_rows": len(table.rows) if table is not None else None,
            "unparsed_route_lines": len(table.unparsed) if table is not None else None,
            "interfaces": {
                name: [
                    {"ipv4": row.ipv4, "status": row.status, "protocol": row.protocol}
                    for row in reading.interface(name)
                ]
                for name in sorted(wanted_interfaces.get(device_id, ()))
            },
            "network_routes": {
                network: [
                    {
                        "code": row.code,
                        "prefix": f"{row.network}/{row.prefix_length}",
                        "next_hop": row.next_hop,
                        "interface": row.interface,
                    }
                    for row in (table.rows if table is not None else ())
                    if ipaddress.IPv4Network(
                        f"{row.network}/{row.prefix_length}"
                    ).overlaps(ipaddress.IPv4Network(network))
                ]
                for network in sorted(wanted_networks.get(device_id, ()))
            },
            "routes": {
                destination: [
                    {
                        "code": row.code,
                        "prefix": f"{row.network}/{row.prefix_length}",
                        "next_hop": row.next_hop,
                        "interface": row.interface,
                    }
                    for row in (
                        table.longest_match(destination) if table is not None else ()
                    )
                ]
                for destination in sorted(wanted_destinations.get(device_id, ()))
            },
        }
    return devices


@dataclass(frozen=True)
class RoutedDependentResult:
    """Whether one dependent's routed chains were admitted, and why not."""

    expectation_id: str
    service_id: str
    kind: str
    client_device_id: str
    host_device_id: str
    admitted: bool
    dimension: str = ROUTED_NONE
    cause: str = ""

    def as_row(self) -> dict[str, object]:
        """Return the public per-dependent routed row."""
        return {
            "expectation_id": self.expectation_id,
            "service_id": self.service_id,
            "kind": self.kind,
            "client_device_id": self.client_device_id,
            "host_device_id": self.host_device_id,
            "admitted": self.admitted,
            "dimension": self.dimension,
            "cause": self.cause,
        }


@dataclass(frozen=True)
class RoutedGroupResult:
    """One routed observation of one segment pair, and its dependents."""

    requirement: RoutedRequirement
    status: str
    dimension: str
    causes: tuple[str, ...] = ()
    sample: Mapping[str, object] = field(default_factory=dict)
    dependents: tuple[RoutedDependentResult, ...] = ()
    episode: Mapping[str, object] = field(default_factory=dict)

    @property
    def key(self) -> GroupKey:
        """Return the identity this result answers."""
        return self.requirement.key

    def as_row(self) -> dict[str, object]:
        """Return the public routed row, sample included."""
        requirement = self.requirement
        row: dict[str, object] = {
            "kind": "routed_forwarding",
            "client_segment_id": requirement.client_segment_id,
            "host_segment_id": requirement.host_segment_id,
            "device_ids": list(requirement.device_ids),
            "status": self.status,
            "dimension": self.dimension,
            "causes": list(self.causes),
            "sample": dict(self.sample),
            "dependents": [item.as_row() for item in self.dependents],
        }
        if self.episode:
            row["episode"] = dict(self.episode)
        return row


def _kind_value(kind: object) -> str:
    return str(getattr(kind, "value", kind))


def _dependent_result(
    dependent: RoutedDependent, verdict: RoutedVerdict
) -> RoutedDependentResult:
    return RoutedDependentResult(
        expectation_id=dependent.expectation_id,
        service_id=dependent.service_id,
        kind=_kind_value(dependent.kind),
        client_device_id=dependent.client_device_id,
        host_device_id=dependent.host_device_id,
        admitted=verdict.admitted,
        dimension=verdict.dimension,
        cause="" if verdict.admitted else verdict.cause,
    )


def observed_routed_result(
    requirement: RoutedRequirement,
    *,
    verdicts: Mapping[str, RoutedVerdict],
    sample: Mapping[str, object],
) -> RoutedGroupResult:
    """Build the result of one observed routed episode."""
    dependents = tuple(
        _dependent_result(
            item,
            verdicts.get(
                item.expectation_id,
                RoutedVerdict(False, ROUTED_NOT_OBSERVED, CAUSE_NO_ROUND),
            ),
        )
        for item in requirement.dependents
    )
    refused = [item for item in dependents if not item.admitted]
    return RoutedGroupResult(
        requirement=requirement,
        status="admitted" if not refused else "refused",
        dimension=refused[0].dimension if refused else ROUTED_NONE,
        causes=tuple(dict.fromkeys(item.cause for item in refused)),
        sample=dict(sample),
        dependents=dependents,
    )


def unobserved_routed_result(
    requirement: RoutedRequirement, *, cause: str
) -> RoutedGroupResult:
    """Build the result of a routed group that took no observation."""
    verdict = RoutedVerdict(False, ROUTED_NOT_OBSERVED, cause)
    return RoutedGroupResult(
        requirement=requirement,
        status="not_observed",
        dimension=ROUTED_NOT_OBSERVED,
        causes=(cause,),
        dependents=tuple(
            _dependent_result(item, verdict) for item in requirement.dependents
        ),
    )


def revoked_dependents(
    result: RoutedGroupResult,
    latest: Mapping[str, DeviceForwardingReading],
    changed: set[str],
    pending: set[str],
) -> dict[str, str]:
    """Return the pending admitted dependents a newer reading now refutes.

    `latest` holds the newest AUTHORITATIVE reading of every router any routed
    episode of this invocation took, and `changed` the routers a later episode
    has just re-read. A pending dependent whose chain crosses a changed router
    is decided again from `latest`; if that decision refuses, the permission
    it had is withdrawn for the rest of the invocation, and a later valid
    reading does not restore it. An unreadable later reading never enters
    `latest`, so a local read failure revokes nothing.
    """
    requirement = result.requirement
    admitted = {item.expectation_id for item in result.dependents if item.admitted}
    eligible = admitted & pending
    revoked: dict[str, str] = {}
    changed_names = {
        latest[device_id].device_name for device_id in changed if device_id in latest
    }
    for dependent in requirement.dependents:
        if dependent.expectation_id not in eligible:
            continue
        if not set(dependent.device_ids) & changed:
            continue
        verdict = routed_verdict(dependent, latest)
        source_name = verdict.cause.split(":", 2)[1] if ":" in verdict.cause else ""
        if (
            not verdict.admitted
            and verdict.dimension in {ROUTED_ROUTE, ROUTED_INTERFACE}
            and source_name in changed_names
        ):
            revoked[dependent.expectation_id] = verdict.cause
    return revoked
