"""Deterministic semantic-flow attribution over concrete Enterprise WAN links."""

from __future__ import annotations

from collections import defaultdict, deque

from ...models.plans import TopologyPlan
from ..models.compilation import ConcreteLinkRole
from ..models.enterprise_plan import EnterprisePlan
from ..models.link_performance import (
    TrafficAttributionIssue,
    TrafficAttributionResult,
)


def attribute_enterprise_traffic(
    enterprise: EnterprisePlan,
    topology: TopologyPlan,
) -> TrafficAttributionResult:
    """Map each flow to one path; disconnected or equal-cost paths fail closed."""

    devices = {item.id or item.name: item for item in topology.devices}
    wan_links = {
        item.id: item for item in topology.links
        if item.id and item.link_role == ConcreteLinkRole.WAN_LINK.value
    }
    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    endpoints_by_link: dict[str, tuple[str, str]] = {}
    for link_id, link in sorted(wan_links.items()):
        a = devices.get(link.device_a_id or link.device_a)
        b = devices.get(link.device_b_id or link.device_b)
        if a is None or b is None or not a.site_id or not b.site_id:
            continue
        endpoints_by_link[link_id] = (a.site_id, b.site_id)
        adjacency[a.site_id].append((b.site_id, link_id))
        adjacency[b.site_id].append((a.site_id, link_id))
    for values in adjacency.values():
        values.sort(key=lambda item: (item[0], item[1]))

    result = TrafficAttributionResult(
        contributions_by_link={link_id: [] for link_id in sorted(wan_links)},
    )
    known_sites = {site.site_id for site in enterprise.sites}
    seen_ids: set[str] = set()
    for flow in sorted(enterprise.traffic_flows, key=lambda item: item.id):
        if not flow.id or flow.id in seen_ids:
            result.issues.append(TrafficAttributionIssue(
                code="FLOW_ID_INVALID",
                flow_id=flow.id,
                message="Traffic flow IDs must be non-empty and unique.",
            ))
            continue
        seen_ids.add(flow.id)
        if (
            flow.source_site_id not in known_sites
            or flow.destination_site_id not in known_sites
            or flow.source_site_id == flow.destination_site_id
        ):
            result.issues.append(TrafficAttributionIssue(
                code="FLOW_ENDPOINT_INVALID",
                flow_id=flow.id,
                message="Traffic flow endpoints must name two distinct known sites.",
            ))
            continue
        if flow.explicit_link_ids:
            path = _validate_explicit_path(
                flow.source_site_id,
                flow.destination_site_id,
                flow.explicit_link_ids,
                endpoints_by_link,
            )
            paths = [path] if path is not None else []
        else:
            paths = _shortest_paths(
                flow.source_site_id, flow.destination_site_id, adjacency,
            )
        if not paths:
            result.issues.append(TrafficAttributionIssue(
                code="FLOW_PATH_UNREACHABLE",
                flow_id=flow.id,
                message="No valid WAN path connects the flow endpoints.",
            ))
            continue
        if len(paths) != 1:
            result.issues.append(TrafficAttributionIssue(
                code="FLOW_PATH_AMBIGUOUS",
                flow_id=flow.id,
                message=(
                    "Multiple equal-cost WAN paths exist; an explicit path is "
                    "required before capacity can be attributed."
                ),
            ))
            continue
        path = paths[0]
        result.paths_by_flow[flow.id] = path
        contribution = flow.contribution()
        for link_id in path:
            result.contributions_by_link[link_id].append(contribution)
    return result


def _validate_explicit_path(source, destination, link_ids, endpoints_by_link):
    current = source
    used: set[str] = set()
    path: list[str] = []
    for link_id in link_ids:
        endpoints = endpoints_by_link.get(link_id)
        if endpoints is None or link_id in used or current not in endpoints:
            return None
        used.add(link_id)
        current = endpoints[1] if endpoints[0] == current else endpoints[0]
        path.append(link_id)
    return path if current == destination else None


def _shortest_paths(source, destination, adjacency):
    queue = deque([(source, [], frozenset({source}))])
    shortest: int | None = None
    found: list[list[str]] = []
    while queue:
        site, path, visited = queue.popleft()
        if shortest is not None and len(path) >= shortest:
            continue
        for peer, link_id in adjacency.get(site, []):
            if peer in visited:
                continue
            candidate = [*path, link_id]
            if peer == destination:
                shortest = len(candidate) if shortest is None else shortest
                if len(candidate) == shortest:
                    found.append(candidate)
                continue
            queue.append((peer, candidate, visited | {peer}))
    return sorted(found)
