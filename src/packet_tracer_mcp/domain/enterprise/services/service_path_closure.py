"""The wired path each client-to-server dependency needs, derived from the plan.

A service request from a static client travels from the client's access port,
through whatever the compiled plan puts between the two endpoints, to the
server's access port. This module answers, from the compiled E5 configuration
plan alone and without I/O, which of three shapes that path has and what it
depends on:

- **local access**: both endpoints on one access switch and one VLAN;
- **multi-access L2**: one VLAN on two access switches that compiled trunk
  links carrying that VLAN connect, through switches on which the plan creates
  that VLAN;
- **routed**: the endpoints are in different segments.

Nothing is inferred from names, port numbers or positions. A trunk link is
only usable in the derivation when both of its ends are compiled, name each
other, and allow the VLAN, and when both switches create it. An ambiguous or
missing placement is named, never guessed.

The routed shape is derived but not supported. The planner routes a separate
server segment through gateway interfaces on an L3 device; no registered E5
action enables IPv4 routing on that device and no registered observable reads
its routing table (`show ip route` is registered only filtered by OSPF, EIGRP
and RIP). `ROUTED_PATH_CONTRACT` names that gap exactly.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum, StrEnum

ACCESS_PORT_ACTION_TYPE = "configure_access_port"
TRUNK_ACTION_TYPE = "configure_trunk"
CREATE_VLAN_ACTION_TYPE = "create_vlan"
#: Configuration action types that own an IPv4 gateway interface.
GATEWAY_ACTION_TYPES = frozenset(
    {"configure_svi", "configure_subinterface", "configure_routed_interface"}
)

#: The exact missing contract that keeps routed paths unsupported.
ROUTED_PATH_CONTRACT = (
    "routed_path_unobservable:ipv4_routing_action_and_route_table_reader_unregistered"
)


class PathKind(StrEnum):
    """The shape of one client-to-server path."""

    __str__ = Enum.__str__

    LOCAL_ACCESS = "local_access"
    L2_MULTI_ACCESS = "l2_multi_access"
    ROUTED = "routed"
    UNPLACED = "unplaced"


def _declared_type(action: object) -> str:
    declared = getattr(action, "action_type", None)
    return str(getattr(declared, "value", declared))


@dataclass(frozen=True)
class AccessPlacement:
    """One endpoint's compiled access port."""

    switch_device_id: str
    switch_device_name: str
    interface: str
    vlan_id: int


@dataclass(frozen=True)
class TrunkLink:
    """One compiled trunk link whose two ends name each other."""

    link_id: str
    switch_a_id: str
    switch_a_name: str
    interface_a: str
    switch_b_id: str
    switch_b_name: str
    interface_b: str
    allowed_vlans: tuple[int, ...]

    def carries(self, vlan_id: int) -> bool:
        """Whether both ends were compiled to allow this VLAN."""
        return vlan_id in self.allowed_vlans


@dataclass(frozen=True)
class L2Component:
    """The switches one VLAN connects through compiled trunk links."""

    vlan_id: int
    switch_device_ids: tuple[str, ...]
    switch_device_names: tuple[str, ...]
    links: tuple[TrunkLink, ...]

    @property
    def key(self) -> tuple[str, int, tuple[str, ...]]:
        """Return the complete identity one continuity observation answers."""
        return ("trunk_continuity", self.vlan_id, self.switch_device_ids)

    def interfaces_by_switch(self) -> dict[str, tuple[str, ...]]:
        """Return, per switch, the trunk interfaces of this component."""
        found: dict[str, list[str]] = {item: [] for item in self.switch_device_ids}
        for link in self.links:
            found[link.switch_a_id].append(link.interface_a)
            found[link.switch_b_id].append(link.interface_b)
        return {
            key: tuple(dict.fromkeys(sorted(value))) for key, value in found.items()
        }


@dataclass(frozen=True)
class GatewayInterface:
    """One compiled L3 interface that owns a segment gateway address."""

    device_id: str
    device_name: str
    action_type: str
    name: str
    ipv4: str
    segment_id: str


@dataclass(frozen=True)
class ServicePath:
    """One client-to-server path and every compiled element it depends on."""

    kind: PathKind
    client_device_id: str
    host_device_id: str
    client_access: AccessPlacement | None = None
    host_access: AccessPlacement | None = None
    component: L2Component | None = None
    gateways: tuple[GatewayInterface, ...] = ()
    reason: str = ""


def access_placements_by_endpoint(
    actions: Iterable[object],
) -> dict[str, list[AccessPlacement]]:
    """Map each endpoint to the access ports the plan places it on."""
    found: dict[str, list[AccessPlacement]] = {}
    for action in actions:
        if _declared_type(action) != ACCESS_PORT_ACTION_TYPE:
            continue
        interface = getattr(action, "interface", None)
        vlan_id = getattr(action, "data_vlan_id", None)
        device_id = getattr(action, "device_id", None)
        endpoint_ids = getattr(action, "endpoint_ids", None)
        if (
            not isinstance(interface, str)
            or not interface
            or isinstance(vlan_id, bool)
            or not isinstance(vlan_id, int)
            or not isinstance(device_id, str)
            or not device_id
            or not isinstance(endpoint_ids, (list, tuple))
        ):
            continue
        placement = AccessPlacement(
            switch_device_id=device_id,
            switch_device_name=str(getattr(action, "device_name", "") or ""),
            interface=interface,
            vlan_id=vlan_id,
        )
        for endpoint in endpoint_ids:
            if isinstance(endpoint, str) and endpoint:
                bucket = found.setdefault(endpoint, [])
                if placement not in bucket:
                    bucket.append(placement)
    return found


def compiled_trunk_links(actions: Iterable[object]) -> tuple[TrunkLink, ...]:
    """Pair the two compiled ends of each trunk link, and nothing else.

    Ends are paired by the source link they were compiled from. A link with
    one end, three ends, two ends on one device, or ends that do not name each
    other as peers is not a link this derivation may route through.
    """
    ends: dict[str, list[object]] = {}
    for action in actions:
        if _declared_type(action) != TRUNK_ACTION_TYPE:
            continue
        link_id = str(getattr(action, "source_link_id", "") or "")
        if link_id:
            ends.setdefault(link_id, []).append(action)
    links: list[TrunkLink] = []
    for link_id, pair in sorted(ends.items()):
        if len(pair) != 2:
            continue
        first, second = sorted(pair, key=lambda item: str(item.device_id))
        if (
            first.device_id == second.device_id
            or getattr(first, "peer_device_id", "") != second.device_id
            or getattr(second, "peer_device_id", "") != first.device_id
        ):
            continue
        allowed = set(getattr(first, "allowed_vlans", None) or ()) & set(
            getattr(second, "allowed_vlans", None) or ()
        )
        links.append(
            TrunkLink(
                link_id=link_id,
                switch_a_id=str(first.device_id),
                switch_a_name=str(getattr(first, "device_name", "") or ""),
                interface_a=str(first.interface),
                switch_b_id=str(second.device_id),
                switch_b_name=str(getattr(second, "device_name", "") or ""),
                interface_b=str(second.interface),
                allowed_vlans=tuple(
                    sorted(item for item in allowed if isinstance(item, int))
                ),
            )
        )
    return tuple(links)


def vlan_devices(actions: Iterable[object]) -> dict[int, set[str]]:
    """Map each VLAN to the devices on which the plan creates it."""
    found: dict[int, set[str]] = {}
    for action in actions:
        if _declared_type(action) != CREATE_VLAN_ACTION_TYPE:
            continue
        vlan_id = getattr(action, "vlan_id", None)
        device_id = getattr(action, "device_id", None)
        if isinstance(vlan_id, int) and not isinstance(vlan_id, bool) and device_id:
            found.setdefault(vlan_id, set()).add(str(device_id))
    return found


class PathTopology:
    """The compiled switching facts one plan offers, indexed once."""

    def __init__(self, actions: Iterable[object]) -> None:
        """Index placements, trunk links, VLANs and gateways of one plan."""
        materialized = list(actions)
        self.placements = access_placements_by_endpoint(materialized)
        self.links = compiled_trunk_links(materialized)
        self.vlans = vlan_devices(materialized)
        self.gateways = tuple(
            GatewayInterface(
                device_id=str(action.device_id),
                device_name=str(getattr(action, "device_name", "") or ""),
                action_type=_declared_type(action),
                name=str(
                    getattr(action, "interface", "")
                    or getattr(action, "parent_interface", "")
                    or f"Vlan{getattr(action, 'vlan_id', '')}"
                ),
                ipv4=str(getattr(action, "ipv4", "") or ""),
                segment_id=str(getattr(action, "segment_id", "") or ""),
            )
            for action in materialized
            if _declared_type(action) in GATEWAY_ACTION_TYPES
        )
        self._components: dict[int, dict[str, L2Component]] = {}

    def component_of(self, vlan_id: int, switch_device_id: str) -> L2Component | None:
        """Return the VLAN component a switch belongs to, or None."""
        if vlan_id not in self._components:
            self._components[vlan_id] = self._build_components(vlan_id)
        return self._components[vlan_id].get(switch_device_id)

    def _build_components(self, vlan_id: int) -> dict[str, L2Component]:
        members = self.vlans.get(vlan_id, set())
        usable = [
            link
            for link in self.links
            if link.carries(vlan_id)
            and link.switch_a_id in members
            and link.switch_b_id in members
        ]
        parent: dict[str, str] = {item: item for item in members}

        def root(item: str) -> str:
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        for link in usable:
            left, right = root(link.switch_a_id), root(link.switch_b_id)
            if left != right:
                parent[max(left, right)] = min(left, right)
        grouped: dict[str, list[str]] = {}
        for item in members:
            grouped.setdefault(root(item), []).append(item)
        names: dict[str, str] = {}
        for link in usable:
            names.setdefault(link.switch_a_id, link.switch_a_name)
            names.setdefault(link.switch_b_id, link.switch_b_name)
        by_switch: dict[str, L2Component] = {}
        for switches in grouped.values():
            ordered = tuple(sorted(switches))
            chosen = set(ordered)
            component = L2Component(
                vlan_id=vlan_id,
                switch_device_ids=ordered,
                switch_device_names=tuple(names.get(item, "") for item in ordered),
                links=tuple(
                    link
                    for link in usable
                    if link.switch_a_id in chosen and link.switch_b_id in chosen
                ),
            )
            for item in ordered:
                by_switch[item] = component
        return by_switch

    def gateways_for(self, segment_ids: Iterable[str]) -> tuple[GatewayInterface, ...]:
        """Return the compiled gateway interfaces of the given segments."""
        wanted = set(segment_ids)
        return tuple(item for item in self.gateways if item.segment_id in wanted)


def classify_path(
    topology: PathTopology,
    *,
    client_device_id: str,
    host_device_id: str,
    segments: Mapping[str, str] | None = None,
) -> ServicePath:
    """Classify one client-to-server path from the compiled plan alone.

    `segments` maps endpoint ids to their foundation segment. Different
    segments are a routed path whatever the placements say; the path's
    gateway interfaces are named so the blocker is concrete.
    """
    segments = segments or {}
    client_segment = segments.get(client_device_id, "")
    host_segment = segments.get(host_device_id, "")
    client = topology.placements.get(client_device_id, [])
    host = topology.placements.get(host_device_id, [])
    client_access = client[0] if len(client) == 1 else None
    host_access = host[0] if len(host) == 1 else None
    if client_segment and host_segment and client_segment != host_segment:
        return ServicePath(
            kind=PathKind.ROUTED,
            client_device_id=client_device_id,
            host_device_id=host_device_id,
            client_access=client_access,
            host_access=host_access,
            gateways=topology.gateways_for((client_segment, host_segment)),
            reason=ROUTED_PATH_CONTRACT,
        )
    if client_access is None or host_access is None:
        return ServicePath(
            kind=PathKind.UNPLACED,
            client_device_id=client_device_id,
            host_device_id=host_device_id,
            client_access=client_access,
            host_access=host_access,
            reason="endpoint_not_on_one_access_port",
        )
    if client_access.vlan_id != host_access.vlan_id:
        return ServicePath(
            kind=PathKind.UNPLACED,
            client_device_id=client_device_id,
            host_device_id=host_device_id,
            client_access=client_access,
            host_access=host_access,
            reason="access_vlans_differ",
        )
    if client_access.switch_device_id == host_access.switch_device_id:
        return ServicePath(
            kind=PathKind.LOCAL_ACCESS,
            client_device_id=client_device_id,
            host_device_id=host_device_id,
            client_access=client_access,
            host_access=host_access,
        )
    component = topology.component_of(
        client_access.vlan_id, client_access.switch_device_id
    )
    if component is None or host_access.switch_device_id not in set(
        component.switch_device_ids
    ):
        return ServicePath(
            kind=PathKind.UNPLACED,
            client_device_id=client_device_id,
            host_device_id=host_device_id,
            client_access=client_access,
            host_access=host_access,
            reason="inter_switch",
        )
    return ServicePath(
        kind=PathKind.L2_MULTI_ACCESS,
        client_device_id=client_device_id,
        host_device_id=host_device_id,
        client_access=client_access,
        host_access=host_access,
        component=component,
    )
