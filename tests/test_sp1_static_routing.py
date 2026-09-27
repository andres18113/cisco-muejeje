"""SP-1 A-2/A-3: foundational routing and its route-table read-back.

Expectations are derived from the compiled plan's own transit and gateway
actions, never from literal addresses: a route must point at the neighbour on
the shortest transit path and name the egress interface it depends on.
"""

from __future__ import annotations

import ipaddress
from collections import deque

import pytest
from sp1_routed_fixture import compose, topology_payload

from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigureRoutedInterface,
    ConfigureStaticRoute,
    ConfigureSubinterface,
    VerificationKind,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    parse_show_ip_route,
)
from packet_tracer_mcp.infrastructure.generator.configuration_renderer import (
    PacketTracerIosRenderer,
)


def _transits(plan):
    return [
        item
        for item in plan.actions
        if isinstance(item, ConfigureRoutedInterface)
        and item.segment_id.startswith("transit/")
    ]


def _routes(plan):
    return [item for item in plan.actions if isinstance(item, ConfigureStaticRoute)]


def _gateways(plan):
    return [
        item
        for item in plan.actions
        if isinstance(item, ConfigureRoutedInterface | ConfigureSubinterface)
        and not item.segment_id.startswith("transit/")
    ]


@pytest.fixture(scope="module")
def chain():
    """Three sites, HQ-BR1-BR2, Ethernet WAN, static routing requested."""
    return compose(topology_payload(), services=False).configuration


def test_every_ethernet_wan_link_is_addressed_on_both_ends(chain):
    """Two links, four transit interfaces, one /30 per link."""
    by_segment: dict[str, list[ConfigureRoutedInterface]] = {}
    for item in _transits(chain):
        by_segment.setdefault(item.segment_id, []).append(item)

    assert len(by_segment) == 2
    for pair in by_segment.values():
        assert len(pair) == 2 and pair[0].device_id != pair[1].device_id
        networks = {
            ipaddress.ip_interface(f"{item.ipv4}/{item.prefix}").network
            for item in pair
        }
        assert len(networks) == 1 and next(iter(networks)).prefixlen == 30


def _expected_routes(plan) -> dict[tuple[str, str, int], str]:
    """Shortest-path next hops computed independently from the transit pairs."""
    pairs: dict[str, list[ConfigureRoutedInterface]] = {}
    for item in _transits(plan):
        pairs.setdefault(item.segment_id, []).append(item)
    graph: dict[str, list[tuple[str, str]]] = {}
    for left, right in pairs.values():
        graph.setdefault(left.device_id, []).append((right.device_id, right.ipv4))
        graph.setdefault(right.device_id, []).append((left.device_id, left.ipv4))
    expected: dict[tuple[str, str, int], str] = {}
    for router in graph:
        hop: dict[str, str] = {}
        queue = deque([(router, "")])
        seen = {router}
        while queue:
            current, first = queue.popleft()
            for peer, address in sorted(graph[current]):
                if peer in seen:
                    continue
                seen.add(peer)
                hop[peer] = first or address
                queue.append((peer, first or address))
        for gateway in _gateways(plan):
            if gateway.device_id == router or gateway.device_id not in hop:
                continue
            network = ipaddress.ip_interface(f"{gateway.ipv4}/{gateway.prefix}").network
            expected[(router, str(network.network_address), network.prefixlen)] = hop[
                gateway.device_id
            ]
    return expected


def test_routes_follow_the_shortest_transit_path(chain):
    """Every router reaches every remote gateway segment via its first hop."""
    observed = {
        (item.device_id, item.network, item.prefix): item.next_hop
        for item in _routes(chain)
    }

    assert observed == _expected_routes(chain)
    # The chain makes BR2 reach HQ through BR1: a real two-hop path.
    hq_prefixes = {
        (
            str(ipaddress.ip_interface(f"{item.ipv4}/{item.prefix}").network[0]),
            item.prefix,
        )
        for item in _gateways(chain)
        if item.device_id == "r-edge-hq-01"
    }
    br2 = {
        (item.network, item.prefix): item.next_hop
        for item in _routes(chain)
        if item.device_id == "r-edge-br2-01"
    }
    br1_toward_br2 = next(
        item.ipv4
        for item in _transits(chain)
        if item.device_id == "r-edge-br1-01"
        and any(
            other.device_id == "r-edge-br2-01" and other.segment_id == item.segment_id
            for other in _transits(chain)
        )
    )
    assert {br2[prefix] for prefix in hq_prefixes} == {br1_toward_br2}


def test_each_route_depends_on_its_egress_transit_interface(chain):
    """A route is applied after, and only with, the interface it leaves by."""
    transits = {item.id: item for item in _transits(chain)}
    for route in _routes(chain):
        assert route.phase is ConfigurationPhase.L3_ROUTING
        assert route.required_capability == "supports_static_routes"
        assert len(route.depends_on) == 1
        egress = transits[route.depends_on[0]]
        assert egress.device_id == route.device_id
        assert egress.interface == route.egress_interface
        assert (
            ipaddress.ip_address(route.next_hop)
            in ipaddress.ip_interface(f"{egress.ipv4}/{egress.prefix}").network
        )


def test_each_route_is_read_back_from_the_routing_table(chain):
    """E5 read-back asks `show ip route` for the exact prefix and next hop."""
    expectations = {
        item.action_id: item
        for item in chain.verification_expectations
        if item.kind is VerificationKind.STATIC_ROUTE
    }
    for route in _routes(chain):
        expectation = expectations[route.id]
        assert expectation.required_query == "show_ip_route"
        assert expectation.expected == {
            "network": route.network,
            "prefix": route.prefix,
            "next_hop": route.next_hop,
        }


@pytest.mark.parametrize("routing", ["", "ripv2", "Static-ish"])
def test_no_route_is_compiled_unless_static_routing_is_requested(routing):
    """Any other preference compiles transit addressing and no route."""
    plan = compose(topology_payload(routing=routing), services=False).configuration

    assert _routes(plan) == []
    assert len(_transits(plan)) == 4


def test_a_hub_design_routes_branch_to_branch_through_the_hub():
    """Without a direct link, BR1 reaches BR2 via HQ."""
    plan = compose(topology_payload(chain=False), services=False).configuration

    assert {
        (item.device_id, item.network, item.prefix): item.next_hop
        for item in _routes(plan)
    } == _expected_routes(plan)


def test_the_route_renders_as_one_ip_route_line(chain):
    """The CLI is the network, mask and next hop, nothing else."""
    route = _routes(chain)[0]
    batches = PacketTracerIosRenderer().render_device_batches(
        route.device_name, "1941", [route]
    )

    network = ipaddress.ip_network(f"{route.network}/{route.prefix}")
    assert len(batches) == 1
    assert (
        f"ip route {network.network_address} {network.netmask} {route.next_hop}"
        in batches[0].ios_payload.splitlines()
    )


# -- the route-table reader ---------------------------------------------------

_IOS15 = """BR2-EDGE-RTR-01>show ip route
Codes: L - local, C - connected, S - static, R - RIP, M - mobile, B - BGP
       D - EIGRP, EX - EIGRP external, O - OSPF, IA - OSPF inter area
       N1 - OSPF NSSA external type 1, N2 - OSPF NSSA external type 2
       E1 - OSPF external type 1, E2 - OSPF external type 2, E - EGP
       i - IS-IS, L1 - IS-IS level-1, L2 - IS-IS level-2, ia - IS-IS inter area
       * - candidate default, U - per-user static route, o - ODR
       P - periodic downloaded static route

Gateway of last resort is not set

     10.0.0.0/8 is variably subnetted, 6 subnets, 3 masks
S       10.40.0.0/29 [1/0] via 10.40.0.33
C       10.40.0.24/29 is directly connected, GigabitEthernet0/1
L       10.40.0.25/32 is directly connected, GigabitEthernet0/1
C       10.40.0.32/30 is directly connected, GigabitEthernet0/0
L       10.40.0.34/32 is directly connected, GigabitEthernet0/0
S       10.40.0.8/29 [1/0] via 10.40.0.33

BR2-EDGE-RTR-01>"""


def test_the_ios15_table_parses_every_row():
    """Connected, local and static rows with explicit lengths."""
    table = parse_show_ip_route(_IOS15)

    assert table.parse_complete and table.routing_enabled is True
    assert table.gateway_of_last_resort == "not set"
    assert len(table.rows) == 6
    [static] = table.exact("10.40.0.8", 29)
    assert (static.code, static.next_hop, static.distance) == ("S", "10.40.0.33", 1)
    [connected] = table.longest_match("10.40.0.26")
    assert connected.connected and connected.interface == "GigabitEthernet0/1"
    # The /32 local row is the longest match for the router's own address.
    assert table.longest_match("10.40.0.25")[0].code == "L"
    assert table.longest_match("192.0.2.1") == ()


def test_a_single_mask_header_supplies_the_row_length():
    """IOS omits `/length` under an `is subnetted` header."""
    output = (
        "Gateway of last resort is not set\n\n"
        "     10.0.0.0/30 is subnetted, 3 subnets\n"
        "C       10.0.0.4 is directly connected, Serial0/0/0\n"
        "S       10.0.0.8 [1/0] via 10.0.0.5\n"
    )
    table = parse_show_ip_route(output)

    assert table.parse_complete
    assert [(row.network, row.prefix_length) for row in table.rows] == [
        ("10.0.0.4", 30),
        ("10.0.0.8", 30),
    ]


def test_equal_cost_continuations_are_kept_as_rows():
    """The measured CP-SCALE shape: a second `[d/m] via` line, no code."""
    output = (
        "Router4>show ip route rip\n"
        "Gateway of last resort is not set\n"
        "     10.0.0.0/30 is subnetted, 3 subnets\n"
        "R       10.0.0.8 [120/1] via 10.0.0.2, 00:00:16, Serial1/0\n"
        "                 [120/1] via 10.0.0.6, 00:00:16, Serial1/1\n"
    )
    table = parse_show_ip_route(output)

    rows = table.exact("10.0.0.8", 30)
    assert [(row.next_hop, row.interface) for row in rows] == [
        ("10.0.0.2", "Serial1/0"),
        ("10.0.0.6", "Serial1/1"),
    ]


def test_the_routing_disabled_host_form_is_not_a_table():
    """An L3 switch without `ip routing` prints its host gateway instead."""
    output = (
        "SW>show ip route\nDefault gateway is not set\n\n"
        "Host               Gateway           Last Use    Total Uses  Interface\n"
        "ICMP redirect cache is empty\nSW>"
    )
    table = parse_show_ip_route(output)

    assert table.routing_enabled is False and table.rows == ()


@pytest.mark.parametrize(
    "line",
    [
        "S       10.40.0.8 [1/0] via 10.40.0.33",  # no length, no header
        "C       10.40.0.0/29 is directly connectd, Gi0/1",
        "O IA    10.1.0.0/24 [110/2] via",
    ],
)
def test_an_unreadable_route_line_makes_the_table_incomplete(line):
    """Nothing route-shaped is dropped silently."""
    table = parse_show_ip_route(f"Gateway of last resort is not set\n{line}\n")

    assert not table.parse_complete
    assert table.unparsed == (line,)


def test_without_the_table_header_the_reading_is_incomplete():
    """A first page cut before the header cannot say what is absent."""
    table = parse_show_ip_route("S       10.40.0.8/29 [1/0] via 10.40.0.33\n")

    assert len(table.rows) == 1 and not table.parse_complete
