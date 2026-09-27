"""The routed path one client-to-server dependency needs, from compiled plans.

`service_path_closure` classifies a dependency whose endpoints are in
different segments as routed. This module says whether such a path is
complete in the compiled E4 topology and E5 configuration and, when it is,
exactly which compiled actions it depends on:

- **two L2 legs**: each endpoint's access port to the switch port that faces
  its segment's gateway, on one switch or across a compiled trunk component;
- **two gateway interfaces**: a router subinterface (router-on-a-stick) or a
  routed interface whose switch side is compiled;
- **two route chains**: from the client's gateway router to the server's
  address and back, followed hop by hop through the compiled static routes,
  each next hop resolved to the adjacent transit interface that owns it.

Nothing is inferred from names or positions, and nothing missing is filled
in. A path that cannot be followed is refused with the first reason found,
and one index of the plans is built once and shared by every dependency.

A gateway that is an L3-switch SVI is refused as
`routed_gateway_svi_unsupported`: no compiled action enables IPv4 routing on
that switch, and its `supports_svi` evidence is UNKNOWN.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from .service_path_closure import AccessPlacement, L2Component, PathTopology

SUBINTERFACE = "configure_subinterface"
ROUTED_INTERFACE = "configure_routed_interface"
SVI = "configure_svi"
STATIC_ROUTE = "configure_static_route"
SERIAL_CLOCK = "configure_serial_clock"
TRUNK = "configure_trunk"
ACCESS_PORT = "configure_access_port"
TRANSIT_PREFIX = "transit/"


def _kind(action: object) -> str:
    declared = getattr(action, "action_type", None)
    return str(getattr(declared, "value", declared))


@dataclass(frozen=True)
class GatewayAttachment:
    """One segment's gateway interface and the switch port that faces it."""

    segment_id: str
    gateway_action_id: str
    device_id: str
    device_name: str
    interface: str
    ipv4: str
    prefix: int
    kind: str
    vlan_id: int
    switch_device_id: str
    switch_device_name: str
    switch_interface: str
    switch_action_id: str

    @property
    def network(self) -> ipaddress.IPv4Network:
        """Return the segment network the gateway interface is on."""
        return ipaddress.ip_interface(f"{self.ipv4}/{self.prefix}").network


@dataclass(frozen=True)
class L2Leg:
    """One endpoint's switched leg to its gateway's switch port."""

    endpoint_id: str
    access: AccessPlacement
    attachment: GatewayAttachment
    component: L2Component | None
    cyclic: bool
    trunk_action_ids: tuple[str, ...]

    @property
    def local(self) -> bool:
        """Whether the endpoint and the gateway port share one switch."""
        return self.access.switch_device_id == self.attachment.switch_device_id


@dataclass(frozen=True)
class RouteHop:
    """One router's forwarding decision towards one destination address."""

    device_id: str
    device_name: str
    destination: str
    route_action_id: str
    network: str
    prefix: int
    next_hop: str
    egress_action_id: str
    egress_interface: str
    egress_ipv4: str
    peer_device_id: str
    ingress_action_id: str
    ingress_interface: str
    ingress_ipv4: str


@dataclass(frozen=True)
class RoutedPath:
    """A complete routed dependency, or the reason it is not one."""

    client_device_id: str
    host_device_id: str
    client_ipv4: str = ""
    client_network: str = ""
    host_ipv4: str = ""
    client_leg: L2Leg | None = None
    host_leg: L2Leg | None = None
    forward: tuple[RouteHop, ...] = ()
    reverse: tuple[RouteHop, ...] = ()
    reason: str = ""
    action_ids: frozenset[str] = field(default_factory=frozenset)

    @property
    def admitted(self) -> bool:
        """Whether every leg, gateway and hop was found."""
        return not self.reason

    @property
    def single_gateway(self) -> bool:
        """Whether both segments are routed by one device (inter-VLAN)."""
        return bool(
            self.client_leg
            and self.host_leg
            and self.client_leg.attachment.device_id
            == self.host_leg.attachment.device_id
        )

    @property
    def routing_devices(self) -> tuple[str, ...]:
        """Every router either chain passes through, in first-seen order."""
        found: list[str] = []
        for leg in (self.client_leg, self.host_leg):
            if leg is not None:
                found.append(leg.attachment.device_id)
        for hop in (*self.forward, *self.reverse):
            found.append(hop.device_id)
            found.append(hop.peer_device_id)
        return tuple(dict.fromkeys(item for item in found if item))


@dataclass(frozen=True)
class EndpointAddress:
    """Static address or DHCP segment route target from a compiled E5 action."""

    device_id: str
    ipv4: str
    netmask: str
    gateway: str
    segment_id: str
    network: str = ""


class RoutedPlanIndex:
    """The compiled facts routed paths need, indexed once per plan pair."""

    def __init__(self, actions: Iterable[object], links: Iterable[object]) -> None:
        """Index gateways, transits, routes, switch ports and physical links."""
        materialized = list(actions)
        self.topology = PathTopology(materialized)
        self.gateways: dict[str, list[object]] = {}
        self.transits_by_address: dict[str, list[object]] = {}
        self.transits_by_segment: dict[str, list[object]] = {}
        self.transits_by_id: dict[str, object] = {}
        self.routes: dict[str, list[tuple[ipaddress.IPv4Network, object]]] = {}
        self.switch_ports: dict[tuple[str, str], list[object]] = {}
        self.clocks: dict[tuple[str, str], list[str]] = {}
        self.names: dict[str, str] = {}
        for action in materialized:
            kind = _kind(action)
            device_id = str(getattr(action, "device_id", "") or "")
            self.names.setdefault(device_id, str(getattr(action, "device_name", "")))
            segment_id = str(getattr(action, "segment_id", "") or "")
            if kind in {SUBINTERFACE, ROUTED_INTERFACE, SVI}:
                if segment_id.startswith(TRANSIT_PREFIX):
                    self.transits_by_address.setdefault(str(action.ipv4), []).append(
                        action
                    )
                    self.transits_by_segment.setdefault(segment_id, []).append(action)
                    self.transits_by_id[str(action.id)] = action
                elif segment_id:
                    self.gateways.setdefault(segment_id, []).append(action)
            elif kind == STATIC_ROUTE:
                network = ipaddress.ip_network(
                    f"{action.network}/{action.prefix}", strict=False
                )
                self.routes.setdefault(device_id, []).append((network, action))
            elif kind in {TRUNK, ACCESS_PORT}:
                self.switch_ports.setdefault(
                    (device_id, str(action.interface).casefold()), []
                ).append(action)
            elif kind == SERIAL_CLOCK:
                self.clocks.setdefault(
                    (device_id, str(action.interface).casefold()), []
                ).append(str(action.id))
        for rows in self.routes.values():
            rows.sort(key=lambda item: -item[0].prefixlen)
        self.link_ends: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for link in links:
            a = (str(link.device_a_id), str(link.port_a).casefold())
            b = (str(link.device_b_id), str(link.port_b).casefold())
            self.link_ends.setdefault(a, []).append((b[0], str(link.port_b)))
            self.link_ends.setdefault(b, []).append((a[0], str(link.port_a)))

    def attachment(self, segment_id: str) -> GatewayAttachment | str:
        """Return the segment's gateway attachment or the reason there is none."""
        found = self.gateways.get(segment_id, [])
        if not found:
            return f"routed_gateway_missing:{segment_id}"
        if len(found) != 1:
            return f"routed_gateway_ambiguous:{segment_id}"
        action = found[0]
        kind = _kind(action)
        if kind == SVI:
            return f"routed_gateway_svi_unsupported:{segment_id}"
        port = str(
            action.parent_interface if kind == SUBINTERFACE else action.interface
        )
        router_id = str(action.device_id)
        peers = self.link_ends.get((router_id, port.casefold()), [])
        if len(peers) != 1:
            return f"routed_gateway_unattached:{segment_id}"
        switch_id, switch_port = peers[0]
        switch_actions = self.switch_ports.get((switch_id, switch_port.casefold()), [])
        wanted = TRUNK if kind == SUBINTERFACE else ACCESS_PORT
        matching = [item for item in switch_actions if _kind(item) == wanted]
        if len(matching) != 1:
            return f"routed_gateway_switch_port_uncompiled:{segment_id}"
        switch_action = matching[0]
        vlan_id = (
            int(action.vlan_id)
            if kind == SUBINTERFACE
            else int(switch_action.data_vlan_id)
        )
        if kind == SUBINTERFACE and vlan_id not in set(
            switch_action.allowed_vlans or ()
        ):
            return f"routed_gateway_vlan_not_trunked:{segment_id}"
        if kind == SUBINTERFACE and str(switch_action.peer_device_id) != router_id:
            return f"routed_gateway_trunk_peer_mismatch:{segment_id}"
        interface = f"{port}.{vlan_id}" if kind == SUBINTERFACE else port
        return GatewayAttachment(
            segment_id=segment_id,
            gateway_action_id=str(action.id),
            device_id=router_id,
            device_name=str(action.device_name),
            interface=interface,
            ipv4=str(action.ipv4),
            prefix=int(action.prefix),
            kind=kind,
            vlan_id=vlan_id,
            switch_device_id=switch_id,
            switch_device_name=str(switch_action.device_name),
            switch_interface=switch_port,
            switch_action_id=str(switch_action.id),
        )

    def leg(self, endpoint_id: str, attachment: GatewayAttachment) -> L2Leg | str:
        """Return one endpoint's leg to its gateway port, or why there is none."""
        placements = self.topology.placements.get(endpoint_id, [])
        if len(placements) != 1:
            return "endpoint_not_on_one_access_port"
        access = placements[0]
        if access.vlan_id != attachment.vlan_id:
            return f"access_vlan_differs_from_gateway:{attachment.segment_id}"
        if access.switch_device_id == attachment.switch_device_id:
            return L2Leg(endpoint_id, access, attachment, None, False, ())
        component = self.topology.component_of(access.vlan_id, access.switch_device_id)
        if component is None or attachment.switch_device_id not in set(
            component.switch_device_ids
        ):
            return f"gateway_switch_not_joined:{attachment.segment_id}"
        cyclic = len(component.links) >= len(component.switch_device_ids)
        trunks: tuple[str, ...] = ()
        if not cyclic:
            trunks = self._tree_path_trunks(
                component, access.switch_device_id, attachment.switch_device_id
            )
        return L2Leg(endpoint_id, access, attachment, component, cyclic, trunks)

    def _tree_path_trunks(
        self, component: L2Component, start: str, end: str
    ) -> tuple[str, ...]:
        """Return the trunk action ids of the unique tree path between two switches."""
        adjacency: dict[str, list[tuple[str, object]]] = {}
        for link in component.links:
            adjacency.setdefault(link.switch_a_id, []).append((link.switch_b_id, link))
            adjacency.setdefault(link.switch_b_id, []).append((link.switch_a_id, link))
        previous: dict[str, tuple[str, object]] = {}
        pending = [start]
        seen = {start}
        while pending:
            current = pending.pop()
            for peer, link in adjacency.get(current, ()):
                if peer not in seen:
                    seen.add(peer)
                    previous[peer] = (current, link)
                    pending.append(peer)
        ids: list[str] = []
        cursor = end
        while cursor != start and cursor in previous:
            parent, link = previous[cursor]
            for switch_id, interface in (
                (link.switch_a_id, link.interface_a),
                (link.switch_b_id, link.interface_b),
            ):
                for action in self.switch_ports.get(
                    (switch_id, interface.casefold()), []
                ):
                    if _kind(action) == TRUNK:
                        ids.append(str(action.id))
            cursor = parent
        return tuple(sorted(set(ids)))

    def chain(
        self,
        start: GatewayAttachment,
        destination: EndpointAddress,
        target: GatewayAttachment,
        router_count: int,
    ) -> tuple[RouteHop, ...] | str:
        """Follow the compiled routes from `start` to the destination segment."""
        target_network = (
            ipaddress.ip_network(destination.network, strict=True)
            if destination.network
            else None
        )
        address = (
            target_network.network_address
            if target_network is not None
            else ipaddress.ip_address(destination.ipv4)
        )
        hops: list[RouteHop] = []
        current = start.device_id
        visited: list[str] = []
        while current != target.device_id:
            if current in visited:
                return "route_loop:" + ">".join([*visited, current])
            if len(visited) > router_count:
                return f"route_chain_unbounded:{destination.segment_id}"
            visited.append(current)
            candidates = self.routes.get(current, ())
            if target_network is not None and any(
                network.subnet_of(target_network)
                and network.prefixlen > target_network.prefixlen
                for network, _action in candidates
            ):
                return (
                    "route_shadows_client_network:"
                    f"{self.names.get(current, current)}:{target_network}"
                )
            matches = [
                (network, action)
                for network, action in candidates
                if (
                    target_network.subnet_of(network)
                    if target_network is not None
                    else address in network
                )
            ]
            if not matches:
                return f"route_missing:{self.names.get(current, current)}:{destination.segment_id}"
            longest = matches[0][0].prefixlen
            best = [
                action for network, action in matches if network.prefixlen == longest
            ]
            if len({str(item.next_hop) for item in best}) != 1:
                return f"route_ambiguous:{self.names.get(current, current)}:{destination.segment_id}"
            route = best[0]
            egress = next(
                (
                    candidate
                    for item in getattr(route, "depends_on", ())
                    if (candidate := self.transits_by_id.get(str(item))) is not None
                    and str(candidate.device_id) == current
                ),
                None,
            )
            owners = [
                item
                for item in self.transits_by_address.get(str(route.next_hop), [])
                if str(item.device_id) != current
            ]
            if len(owners) != 1:
                return f"route_next_hop_unresolved:{self.names.get(current, current)}:{route.next_hop}"
            ingress = owners[0]
            if egress is None or str(egress.segment_id) != str(ingress.segment_id):
                return f"route_next_hop_not_adjacent:{self.names.get(current, current)}:{route.next_hop}"
            hops.append(
                RouteHop(
                    device_id=current,
                    device_name=self.names.get(current, current),
                    destination=str(address),
                    route_action_id=str(route.id),
                    network=str(route.network),
                    prefix=int(route.prefix),
                    next_hop=str(route.next_hop),
                    egress_action_id=str(egress.id),
                    egress_interface=str(egress.interface),
                    egress_ipv4=str(egress.ipv4),
                    peer_device_id=str(ingress.device_id),
                    ingress_action_id=str(ingress.id),
                    ingress_interface=str(ingress.interface),
                    ingress_ipv4=str(ingress.ipv4),
                )
            )
            current = str(ingress.device_id)
        return tuple(hops)

    def router_count(self) -> int:
        """Return how many devices own a transit interface or a gateway."""
        owners = {
            str(item.device_id)
            for items in (*self.transits_by_segment.values(), *self.gateways.values())
            for item in items
        }
        return len(owners)


def derive_routed_path(
    index: RoutedPlanIndex,
    *,
    client: EndpointAddress,
    host: EndpointAddress,
) -> RoutedPath:
    """Derive one routed dependency from the compiled plans alone."""

    def refused(reason: str) -> RoutedPath:
        return RoutedPath(client.device_id, host.device_id, reason=reason)

    client_gateway = index.attachment(client.segment_id)
    if isinstance(client_gateway, str):
        return refused(client_gateway)
    host_gateway = index.attachment(host.segment_id)
    if isinstance(host_gateway, str):
        return refused(host_gateway)
    for endpoint, gateway in ((client, client_gateway), (host, host_gateway)):
        if endpoint.gateway != gateway.ipv4:
            return refused(
                f"endpoint_gateway_mismatch:{endpoint.device_id}:"
                f"{endpoint.gateway or 'unset'}!={gateway.ipv4}"
            )
        if endpoint.network:
            try:
                selected_network = ipaddress.ip_network(endpoint.network, strict=True)
            except ValueError:
                return refused(f"endpoint_network_invalid:{endpoint.device_id}")
            if selected_network != gateway.network:
                return refused(
                    f"endpoint_network_differs_from_gateway:{endpoint.device_id}"
                )
        elif ipaddress.ip_address(endpoint.ipv4) not in gateway.network:
            return refused(f"endpoint_outside_gateway_network:{endpoint.device_id}")
    client_leg = index.leg(client.device_id, client_gateway)
    if isinstance(client_leg, str):
        return refused(client_leg)
    host_leg = index.leg(host.device_id, host_gateway)
    if isinstance(host_leg, str):
        return refused(host_leg)
    bound = index.router_count()
    forward = index.chain(client_gateway, host, host_gateway, bound)
    if isinstance(forward, str):
        return refused(forward)
    reverse = index.chain(host_gateway, client, client_gateway, bound)
    if isinstance(reverse, str):
        return refused("return_" + reverse)
    ids: set[str] = {
        client_gateway.gateway_action_id,
        host_gateway.gateway_action_id,
        client_gateway.switch_action_id,
        host_gateway.switch_action_id,
        *client_leg.trunk_action_ids,
        *host_leg.trunk_action_ids,
    }
    for hop in (*forward, *reverse):
        ids.update({hop.route_action_id, hop.egress_action_id, hop.ingress_action_id})
    for hop in (*forward, *reverse):
        for device_id, action_id in (
            (hop.device_id, hop.egress_action_id),
            (hop.peer_device_id, hop.ingress_action_id),
        ):
            transit = index.transits_by_id.get(action_id)
            interface = str(getattr(transit, "interface", "") or "")
            ids.update(index.clocks.get((device_id, interface.casefold()), []))
    return RoutedPath(
        client_device_id=client.device_id,
        host_device_id=host.device_id,
        client_ipv4=client.ipv4,
        client_network=client.network,
        host_ipv4=host.ipv4,
        client_leg=client_leg,
        host_leg=host_leg,
        forward=forward,
        reverse=reverse,
        action_ids=frozenset(ids),
    )


def dhcp_endpoint_networks(
    actions: Iterable[object],
) -> Mapping[str, EndpointAddress]:
    """Index DHCP clients by their selected segment, never by a guessed IP."""
    found: dict[str, EndpointAddress] = {}
    for action in actions:
        if _kind(action) != "set_endpoint_dhcp":
            continue
        try:
            network = ipaddress.ip_network(
                f"{action.network}/{action.prefix}", strict=True
            )
        except ValueError:
            continue
        if not isinstance(network, ipaddress.IPv4Network):
            continue
        found[str(action.device_id)] = EndpointAddress(
            device_id=str(action.device_id),
            ipv4="",
            netmask=str(action.netmask),
            gateway=str(action.gateway),
            segment_id=str(action.segment_id),
            network=str(network),
        )
    return found


def endpoint_addresses(actions: Iterable[object]) -> Mapping[str, EndpointAddress]:
    """Index every static endpoint address of a configuration plan by device."""
    found: dict[str, EndpointAddress] = {}
    for action in actions:
        if _kind(action) != "set_endpoint_static":
            continue
        found[str(action.device_id)] = EndpointAddress(
            device_id=str(action.device_id),
            ipv4=str(action.ipv4),
            netmask=str(action.netmask),
            gateway=str(getattr(action, "gateway", "") or ""),
            segment_id=str(action.segment_id),
        )
    return found
