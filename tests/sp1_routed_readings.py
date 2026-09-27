"""Builders for SP-1 routed readiness tests: one three-router chain.

`R1` routes the client segment 10.1.0.0/24 (gateway 10.1.0.1 on Gi0/1), `R3`
the server segment 10.3.0.0/24 (gateway 10.3.0.1 on Gi0/1), and `R2` sits
between them on 10.12.0.0/30 and 10.23.0.0/30. The expected readings are the
healthy state of exactly that chain; tests break one fact at a time.
"""

from __future__ import annotations

from dataclasses import replace

from packet_tracer_mcp.domain.enterprise.models.routed_forwarding import (
    CONFIRMED_UNIQUE_IDENTITY,
    DeviceForwardingReading,
    ObservedInterface,
    ObservedRoute,
    RoutedForwardingObservation,
    RoutedForwardingRound,
    RouteTableReading,
)
from packet_tracer_mcp.domain.enterprise.services.routed_readiness import (
    GatewayInterfaceExpectation,
    HopExpectation,
    RoutedDependent,
    RoutedRequirement,
)

CLIENT_GW = GatewayInterfaceExpectation("r1", "GigabitEthernet0/1", "10.1.0.1")
HOST_GW = GatewayInterfaceExpectation("r3", "GigabitEthernet0/1", "10.3.0.1")
FORWARD = (
    HopExpectation(
        "r1",
        "10.12.0.2",
        "GigabitEthernet0/0",
        "10.12.0.1",
        "r2",
        "GigabitEthernet0/0",
        "10.12.0.2",
    ),
    HopExpectation(
        "r2",
        "10.23.0.2",
        "GigabitEthernet0/1",
        "10.23.0.1",
        "r3",
        "GigabitEthernet0/0",
        "10.23.0.2",
    ),
)
REVERSE = (
    HopExpectation(
        "r3",
        "10.23.0.1",
        "GigabitEthernet0/0",
        "10.23.0.2",
        "r2",
        "GigabitEthernet0/1",
        "10.23.0.1",
    ),
    HopExpectation(
        "r2",
        "10.12.0.1",
        "GigabitEthernet0/0",
        "10.12.0.2",
        "r1",
        "GigabitEthernet0/0",
        "10.12.0.1",
    ),
)
NAMES = {"r1": "R1", "r2": "R2", "r3": "R3"}


def dependent(index: int = 1, *, client: str = "", host: str = "10.3.0.10"):
    """Return one request from client `index` of the client segment."""
    return RoutedDependent(
        expectation_id=f"verify-{index}",
        service_id="web",
        kind="http_fetch",
        client_device_id=f"pc-{index}",
        host_device_id="web",
        client_ipv4=client or f"10.1.0.{10 + index}",
        host_ipv4=host,
        client_gateway=CLIENT_GW,
        host_gateway=HOST_GW,
        forward=FORWARD,
        reverse=REVERSE,
    )


def requirement(count: int = 2, *, segment: str = "client") -> RoutedRequirement:
    """Return one routed group with `count` dependents."""
    return RoutedRequirement(
        client_segment_id=segment,
        host_segment_id="servers",
        device_ids=("r1", "r2", "r3"),
        dependents=tuple(dependent(index) for index in range(1, count + 1)),
    )


def _table(*rows: ObservedRoute) -> RouteTableReading:
    return RouteTableReading(
        rows=rows,
        gateway_of_last_resort="not set",
        routing_enabled=True,
        header_seen=True,
    )


def _up(name: str, ipv4: str) -> ObservedInterface:
    return ObservedInterface(name, ipv4, "up", "up")


def healthy() -> dict[str, DeviceForwardingReading]:
    """Return an authoritative reading of every router of the healthy chain."""
    return {
        "r1": reading(
            "R1",
            _table(
                ObservedRoute("C", "10.1.0.0", 24, interface="GigabitEthernet0/1"),
                ObservedRoute("C", "10.12.0.0", 30, interface="GigabitEthernet0/0"),
                ObservedRoute("S", "10.3.0.0", 24, next_hop="10.12.0.2"),
            ),
            [
                _up("GigabitEthernet0/1", "10.1.0.1"),
                _up("GigabitEthernet0/0", "10.12.0.1"),
            ],
        ),
        "r2": reading(
            "R2",
            _table(
                ObservedRoute("C", "10.12.0.0", 30, interface="GigabitEthernet0/0"),
                ObservedRoute("C", "10.23.0.0", 30, interface="GigabitEthernet0/1"),
                ObservedRoute("S", "10.1.0.0", 24, next_hop="10.12.0.1"),
                ObservedRoute("S", "10.3.0.0", 24, next_hop="10.23.0.2"),
            ),
            [
                _up("GigabitEthernet0/0", "10.12.0.2"),
                _up("GigabitEthernet0/1", "10.23.0.1"),
            ],
        ),
        "r3": reading(
            "R3",
            _table(
                ObservedRoute("C", "10.3.0.0", 24, interface="GigabitEthernet0/1"),
                ObservedRoute("C", "10.23.0.0", 30, interface="GigabitEthernet0/0"),
                ObservedRoute("S", "10.1.0.0", 24, next_hop="10.23.0.1"),
            ),
            [
                _up("GigabitEthernet0/1", "10.3.0.1"),
                _up("GigabitEthernet0/0", "10.23.0.2"),
            ],
        ),
    }


def reading(
    name: str,
    table: RouteTableReading | None,
    interfaces: list[ObservedInterface],
    **overrides,
) -> DeviceForwardingReading:
    """Return one authoritative reading unless `overrides` weaken it."""
    base = DeviceForwardingReading(
        device_name=name,
        executed=True,
        fresh_output_observed=True,
        output_complete=True,
        observed_device_name=name,
        device_identity_provenance=CONFIRMED_UNIQUE_IDENTITY,
        route_table=table,
        interfaces=tuple(interfaces),
    )
    return replace(base, **overrides)


def with_routes(
    readings: dict[str, DeviceForwardingReading], device: str, *rows: ObservedRoute
) -> dict[str, DeviceForwardingReading]:
    """Replace one router's table rows, keeping everything else."""
    changed = dict(readings)
    changed[device] = replace(changed[device], route_table=_table(*rows))
    return changed


def with_interface(
    readings: dict[str, DeviceForwardingReading],
    device: str,
    interface: ObservedInterface,
) -> dict[str, DeviceForwardingReading]:
    """Replace one interface row of one router."""
    changed = dict(readings)
    rows = [
        interface if item.name == interface.name else item
        for item in changed[device].interfaces
    ]
    changed[device] = replace(changed[device], interfaces=tuple(rows))
    return changed


def round_of(
    index: int, readings: dict[str, DeviceForwardingReading]
) -> RoutedForwardingRound:
    """Return one complete round over R1, R2, R3."""
    return RoutedForwardingRound(
        index=index,
        elapsed_ms=index * 1000,
        readings=tuple(readings[device] for device in ("r1", "r2", "r3")),
        complete=True,
    )


def observation(
    *rounds: RoutedForwardingRound, end: str = "required_paths_forwarding"
) -> RoutedForwardingObservation:
    """Return one episode over R1, R2, R3."""
    return RoutedForwardingObservation(
        device_names=("R1", "R2", "R3"),
        rounds=rounds,
        deadline_seconds=30.0,
        elapsed_ms=len(rounds) * 1000,
        episode_end_reason=end,
    )
