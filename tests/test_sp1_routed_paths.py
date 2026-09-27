"""SP-1 A-4: routed dependencies are derived from compiled plans, or refused.

Each negative case edits one compiled fact of a real plan (a route, a next
hop, a link, a gateway) and expects the first precise reason; each positive
case checks the legs, chains and action ids against the plan's own actions.
"""

from __future__ import annotations

import pytest
from sp1_routed_fixture import routed_workload

from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigureStaticRoute,
    ConfigureSvi,
)
from packet_tracer_mcp.domain.enterprise.services.routed_service_path import (
    RoutedPlanIndex,
    derive_routed_path,
    endpoint_addresses,
)


@pytest.fixture(scope="module")
def plans():
    """Return the three-site chain with DNS and HTTP at HQ."""
    return routed_workload()[1]


def _derive(plans, client_name: str, *, actions=None, links=None):
    configuration = plans.configuration
    actions = list(configuration.actions) if actions is None else actions
    links = list(plans.composition.topology.links) if links is None else links
    index = RoutedPlanIndex(actions, links)
    addresses = endpoint_addresses(actions)
    ids = plans.ids()
    return derive_routed_path(
        index,
        client=addresses[ids[client_name]],
        host=addresses[ids["HQ-DEFAULT-WEB-01"]],
    )


def _replace(actions, match, **update):
    return [
        item.model_copy(update=update, deep=True) if match(item) else item
        for item in actions
    ]


def _route(plans, router: str, prefix_of: str):
    """Return the compiled route on `router` towards the segment of an endpoint."""
    target = plans.endpoint(prefix_of)
    return next(
        item
        for item in plans.configuration.actions
        if isinstance(item, ConfigureStaticRoute)
        and item.device_name == router
        and item.destination_segment_id == target.segment_id
    )


def test_hq_users_use_one_gateway(plans):
    """Inter-VLAN: both segments end on the HQ router; no chain at all."""
    path = _derive(plans, "HQ-DEFAULT-PC-01")

    assert path.admitted and path.single_gateway
    assert path.forward == () and path.reverse == ()
    assert path.client_leg.attachment.kind == "configure_subinterface"
    assert path.client_leg.attachment.vlan_id != path.host_leg.attachment.vlan_id


def test_a_two_hop_branch_path_crosses_every_router(plans):
    """BR2 to HQ crosses BR2 and BR1 forward, HQ and BR1 back."""
    path = _derive(plans, "BR2-DEFAULT-PC-01")

    assert path.admitted and not path.single_gateway
    assert [hop.device_name for hop in path.forward] == [
        "BR2-EDGE-RTR-01",
        "BR1-EDGE-RTR-01",
    ]
    assert [hop.device_name for hop in path.reverse] == [
        "HQ-EDGE-RTR-01",
        "BR1-EDGE-RTR-01",
    ]
    assert set(path.routing_devices) == {
        "r-edge-br2-01",
        "r-edge-br1-01",
        "r-edge-hq-01",
    }


def test_the_path_names_exactly_the_actions_it_needs(plans):
    """Gateways, gateway switch ports, routes and both ends of each transit."""
    path = _derive(plans, "BR2-DEFAULT-PC-01")
    by_id = {item.id: item for item in plans.configuration.actions}

    kinds = sorted(by_id[item].action_type.value for item in path.action_ids)
    assert kinds.count("configure_static_route") == 4
    # BR2-BR1 and BR1-HQ transits, both ends each.
    assert kinds.count("configure_routed_interface") == 4 + 1
    assert kinds.count("configure_subinterface") == 1
    assert {by_id[item].device_name for item in path.action_ids} == {
        "BR2-EDGE-RTR-01",
        "BR1-EDGE-RTR-01",
        "HQ-EDGE-RTR-01",
        "BR2-DEFAULT-ACCESS-SW-01",
        "HQ-DEFAULT-ACCESS-SW-01",
    }


def test_a_missing_forward_route_is_refused_by_name(plans):
    """Without BR2's route to HQ the forward chain stops at BR2."""
    route = _route(plans, "BR2-EDGE-RTR-01", "HQ-DEFAULT-WEB-01")
    actions = [item for item in plans.configuration.actions if item.id != route.id]

    path = _derive(plans, "BR2-DEFAULT-PC-01", actions=actions)

    assert (
        path.reason == f"route_missing:BR2-EDGE-RTR-01:{route.destination_segment_id}"
    )


def test_a_missing_return_route_is_refused_by_name(plans):
    """Without BR1's route back to BR2 the return chain stops at BR1."""
    route = _route(plans, "BR1-EDGE-RTR-01", "BR2-DEFAULT-PC-01")
    actions = [item for item in plans.configuration.actions if item.id != route.id]

    path = _derive(plans, "BR2-DEFAULT-PC-01", actions=actions)

    assert path.reason == (
        f"return_route_missing:BR1-EDGE-RTR-01:{route.destination_segment_id}"
    )
    # A client whose own routes are intact is unaffected.
    assert _derive(plans, "BR1-DEFAULT-PC-01", actions=actions).admitted


def test_a_next_hop_nobody_owns_is_refused(plans):
    """A next hop no transit interface owns cannot be followed."""
    route = _route(plans, "BR2-EDGE-RTR-01", "HQ-DEFAULT-WEB-01")
    actions = _replace(
        plans.configuration.actions,
        lambda item: item.id == route.id,
        next_hop="192.0.2.77",
    )

    assert _derive(plans, "BR2-DEFAULT-PC-01", actions=actions).reason == (
        "route_next_hop_unresolved:BR2-EDGE-RTR-01:192.0.2.77"
    )


def test_a_next_hop_across_another_link_is_not_adjacent(plans):
    """HQ's transit address is real, but not on BR2's link."""
    route = _route(plans, "BR2-EDGE-RTR-01", "HQ-DEFAULT-WEB-01")
    hq_transit = next(
        item.ipv4
        for item in plans.configuration.actions
        if item.action_type.value == "configure_routed_interface"
        and item.device_name == "HQ-EDGE-RTR-01"
    )
    actions = _replace(
        plans.configuration.actions,
        lambda item: item.id == route.id,
        next_hop=hq_transit,
    )

    assert _derive(plans, "BR2-DEFAULT-PC-01", actions=actions).reason == (
        f"route_next_hop_not_adjacent:BR2-EDGE-RTR-01:{hq_transit}"
    )


def test_two_routers_pointing_at_each_other_is_a_loop(plans):
    """BR1 sends HQ-bound traffic back to BR2, which sends it to BR1."""
    route = _route(plans, "BR1-EDGE-RTR-01", "HQ-DEFAULT-WEB-01")
    toward_br2 = _route(plans, "BR1-EDGE-RTR-01", "BR2-DEFAULT-PC-01")
    actions = _replace(
        plans.configuration.actions,
        lambda item: item.id == route.id,
        next_hop=toward_br2.next_hop,
        depends_on=list(toward_br2.depends_on),
    )

    reason = _derive(plans, "BR2-DEFAULT-PC-01", actions=actions).reason
    assert reason.startswith("route_loop:r-edge-br2-01>r-edge-br1-01>r-edge-br2-01")


def test_an_unattached_gateway_router_is_refused(plans):
    """Without the router-switch link the gateway serves nobody."""
    links = [
        link
        for link in plans.composition.topology.links
        if {link.device_a, link.device_b}
        != {"BR2-EDGE-RTR-01", "BR2-DEFAULT-ACCESS-SW-01"}
    ]
    path = _derive(plans, "BR2-DEFAULT-PC-01", links=links)

    assert path.reason == "routed_gateway_unattached:br2-data"


def test_an_svi_gateway_is_refused_as_unsupported(plans):
    """An L3-switch SVI gateway has no compiled routing enable."""
    client = plans.endpoint("BR2-DEFAULT-PC-01")
    actions = [
        item
        for item in plans.configuration.actions
        if not (
            getattr(item, "segment_id", "") == client.segment_id
            and item.action_type.value == "configure_routed_interface"
        )
    ] + [
        ConfigureSvi(
            id="svi-br2",
            phase=40,
            device_id="sw",
            device_name="SW",
            site_id="br2",
            vlan_id=10,
            ipv4=client.gateway,
            prefix=29,
            netmask="255.255.255.248",
            segment_id=client.segment_id,
        )
    ]

    assert _derive(plans, "BR2-DEFAULT-PC-01", actions=actions).reason == (
        "routed_gateway_svi_unsupported:br2-data"
    )


def test_an_endpoint_with_another_gateway_is_refused(plans):
    """A client configured with another gateway contradicts the plan."""
    client = plans.endpoint("BR1-DEFAULT-PC-01")
    actions = _replace(
        plans.configuration.actions,
        lambda item: item.id == client.id,
        gateway="10.99.0.1",
    )

    reason = _derive(plans, "BR1-DEFAULT-PC-01", actions=actions).reason
    assert reason == (
        f"endpoint_gateway_mismatch:{client.device_id}:10.99.0.1!={client.gateway}"
    )
