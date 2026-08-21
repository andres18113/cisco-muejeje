"""Typed hard and soft metrics for an Enterprise physical layout."""

from __future__ import annotations

from collections import Counter, defaultdict
from math import hypot

from ...models.plans import DevicePlan, LinkPlan, TopologyPlan
from ..models.compilation import ConcreteLinkRole, LayoutMetrics, LayoutProfile
from ..models.roles import DeviceRole


_WIRELESS_IOT_ROLES = {
    DeviceRole.WEBCAM.value,
    DeviceRole.SMOKE_DETECTOR.value,
    DeviceRole.MOTION_DETECTOR.value,
    DeviceRole.HUMITURE_MONITOR.value,
    DeviceRole.TEMPERATURE_MONITOR.value,
}


class LayoutMetricsEvaluator:
    """Measure layout correctness without mutating or querying a backend."""

    def evaluate(
        self,
        topology: TopologyPlan,
        profile: LayoutProfile = LayoutProfile(),
    ) -> LayoutMetrics:
        devices = list(topology.devices)
        footprint_width, footprint_height = self._footprint(profile)
        overlaps = self._overlaps(devices, footprint_width, footprint_height)
        coordinate_counts = Counter((item.x, item.y) for item in devices)
        duplicates = sum(count - 1 for count in coordinate_counts.values() if count > 1)
        out_of_bounds = sum(
            item.x - footprint_width / 2 < 0
            or item.y - footprint_height / 2 < 0
            or item.x + footprint_width / 2 > profile.canvas_width
            or item.y + footprint_height / 2 > profile.canvas_height
            for item in devices
        )

        by_id = {item.id: item for item in devices if item.id}
        by_name = {item.name: item for item in devices}
        resolved_links: list[tuple[LinkPlan, DevicePlan, DevicePlan]] = []
        valid_references = 0
        for link in topology.links:
            endpoint_a = by_id.get(link.device_a_id) or by_name.get(link.device_a)
            endpoint_b = by_id.get(link.device_b_id) or by_name.get(link.device_b)
            valid_references += int(endpoint_a is not None) + int(endpoint_b is not None)
            if endpoint_a is not None and endpoint_b is not None:
                resolved_links.append((link, endpoint_a, endpoint_b))
        total_references = len(topology.links) * 2

        site_violations = sum(
            link.link_role != ConcreteLinkRole.WAN_LINK.value
            and endpoint_a.site_id != endpoint_b.site_id
            for link, endpoint_a, endpoint_b in resolved_links
        )
        cluster_violations = self._cluster_violations(devices, resolved_links)
        compactness_violations, maximum_dispersion = self._group_metrics(
            devices, profile,
        )
        lengths = [
            hypot(endpoint_b.x - endpoint_a.x, endpoint_b.y - endpoint_a.y)
            for _, endpoint_a, endpoint_b in resolved_links
        ]

        return LayoutMetrics(
            device_count=len(devices),
            device_footprint_width=footprint_width,
            device_footprint_height=footprint_height,
            canvas_width=profile.canvas_width,
            canvas_height=profile.canvas_height,
            rectangle_overlaps=overlaps,
            duplicate_coordinates=duplicates,
            out_of_bounds_devices=out_of_bounds,
            link_endpoint_references=total_references,
            valid_link_endpoint_references=valid_references,
            valid_link_endpoint_percent=(
                round(valid_references * 100 / total_references, 3)
                if total_references else 100.0
            ),
            site_ownership_violations=site_violations,
            cluster_ownership_violations=cluster_violations,
            endpoint_group_compactness_violations=compactness_violations,
            edge_crossings=self._edge_crossings(resolved_links),
            average_link_length=(round(sum(lengths) / len(lengths), 3) if lengths else 0.0),
            maximum_link_length=(round(max(lengths), 3) if lengths else 0.0),
            maximum_group_dispersion=round(maximum_dispersion, 3),
        )

    @staticmethod
    def _footprint(profile: LayoutProfile) -> tuple[int, int]:
        return (
            max(16, profile.horizontal_spacing // 2),
            max(16, min(profile.vertical_spacing // 3, profile.paired_endpoint_offset - 1)),
        )

    @staticmethod
    def _overlaps(devices: list[DevicePlan], width: int, height: int) -> int:
        overlaps = 0
        for index, left in enumerate(devices):
            for right in devices[index + 1:]:
                if abs(left.x - right.x) < width and abs(left.y - right.y) < height:
                    overlaps += 1
        return overlaps

    @staticmethod
    def _group_key(device: DevicePlan) -> str:
        source = device.metadata.get("source_group", "")
        return source.rsplit(":", 1)[0] if ":" in source else source

    def _cluster_violations(
        self,
        devices: list[DevicePlan],
        resolved_links: list[tuple[LinkPlan, DevicePlan, DevicePlan]],
    ) -> int:
        violations = 0
        for link, endpoint_a, endpoint_b in resolved_links:
            if link.link_role in {
                ConcreteLinkRole.ENDPOINT_ACCESS.value,
                ConcreteLinkRole.SERVER_ACCESS.value,
            }:
                endpoint, owner = (
                    (endpoint_a, endpoint_b)
                    if not endpoint_a.network_layer else (endpoint_b, endpoint_a)
                )
                if (
                    endpoint.site_id != owner.site_id
                    or bool(endpoint.zone_id and owner.zone_id and endpoint.zone_id != owner.zone_id)
                ):
                    violations += 1
            elif link.link_role == ConcreteLinkRole.PHONE_PASSTHROUGH.value:
                if (
                    endpoint_a.site_id != endpoint_b.site_id
                    or endpoint_a.zone_id != endpoint_b.zone_id
                ):
                    violations += 1

        access_points: dict[str, list[DevicePlan]] = defaultdict(list)
        for device in devices:
            if device.enterprise_role == DeviceRole.ACCESS_POINT.value:
                access_points[self._group_key(device)].append(device)
        for device in devices:
            if device.enterprise_role not in _WIRELESS_IOT_ROLES:
                continue
            owners = access_points.get(self._group_key(device), [])
            if not owners or not any(
                owner.site_id == device.site_id and owner.zone_id == device.zone_id
                for owner in owners
            ):
                violations += 1
        return violations

    def _group_metrics(
        self,
        devices: list[DevicePlan],
        profile: LayoutProfile,
    ) -> tuple[int, float]:
        groups: dict[str, list[DevicePlan]] = defaultdict(list)
        for device in devices:
            if device.network_layer:
                continue
            key = self._group_key(device)
            if key:
                groups[key].append(device)

        maximum_width = max(0, profile.endpoint_row_size - 1) * profile.horizontal_spacing
        violations = 0
        maximum_dispersion = 0.0
        for members in groups.values():
            if max(item.x for item in members) - min(item.x for item in members) > maximum_width:
                violations += 1
            centroid_x = sum(item.x for item in members) / len(members)
            centroid_y = sum(item.y for item in members) / len(members)
            dispersion = sum(
                hypot(item.x - centroid_x, item.y - centroid_y) for item in members
            ) / len(members)
            maximum_dispersion = max(maximum_dispersion, dispersion)
        return violations, maximum_dispersion

    @staticmethod
    def _edge_crossings(
        links: list[tuple[LinkPlan, DevicePlan, DevicePlan]],
    ) -> int:
        crossings = 0
        for index, (_, a1, a2) in enumerate(links):
            first_ids = {a1.id or a1.name, a2.id or a2.name}
            for _, b1, b2 in links[index + 1:]:
                if first_ids & {b1.id or b1.name, b2.id or b2.name}:
                    continue
                if _proper_intersection(
                    (a1.x, a1.y), (a2.x, a2.y),
                    (b1.x, b1.y), (b2.x, b2.y),
                ):
                    crossings += 1
        return crossings


def _proper_intersection(
    a: tuple[int, int],
    b: tuple[int, int],
    c: tuple[int, int],
    d: tuple[int, int],
) -> bool:
    def orientation(
        left: tuple[int, int], middle: tuple[int, int], right: tuple[int, int],
    ) -> int:
        value = (
            (middle[1] - left[1]) * (right[0] - middle[0])
            - (middle[0] - left[0]) * (right[1] - middle[1])
        )
        return (value > 0) - (value < 0)

    return (
        orientation(a, b, c) != orientation(a, b, d)
        and orientation(c, d, a) != orientation(c, d, b)
        and 0 not in {
            orientation(a, b, c), orientation(a, b, d),
            orientation(c, d, a), orientation(c, d, b),
        }
    )
