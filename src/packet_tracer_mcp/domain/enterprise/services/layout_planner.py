"""Layout jerárquico, determinista y completamente offline para E4."""

from __future__ import annotations

from collections import defaultdict

from ...models.plans import DevicePlan, TopologyPlan
from ..models.compilation import LayoutProfile, LayoutRegion
from ..models.roles import DeviceRole
from ..models.topology import NetworkLayer


_LAYER_ROW = {
    NetworkLayer.WAN.value: 0,
    NetworkLayer.EDGE.value: 1,
    NetworkLayer.CORE.value: 2,
    NetworkLayer.DISTRIBUTION.value: 3,
    NetworkLayer.ACCESS.value: 4,
}


class LayoutPlanner:
    """Agrupa sitios/edificios/pisos/zonas y evita stacks de dispositivos."""

    def plan(
        self, topology: TopologyPlan, profile: LayoutProfile = LayoutProfile(),
    ) -> tuple[TopologyPlan, list[LayoutRegion]]:
        plan = topology.model_copy(deep=True)
        by_site: dict[str, list[DevicePlan]] = defaultdict(list)
        for device in plan.devices:
            by_site[device.site_id].append(device)

        site_base_x = profile.origin_x
        for site_id in sorted(by_site):
            devices = by_site[site_id]
            zones = sorted({device.zone_id for device in devices if device.zone_id})
            zone_width = (profile.endpoint_row_size + 2) * profile.horizontal_spacing
            site_width = max(zone_width, max(1, len(zones)) * zone_width)
            zone_origins = {
                zone_id: site_base_x + index * zone_width
                for index, zone_id in enumerate(zones)
            }
            self._place_site_infrastructure(devices, site_base_x, site_width, profile)
            for zone_id in zones:
                self._place_zone(
                    [device for device in devices if device.zone_id == zone_id],
                    zone_origins[zone_id], profile,
                )
            self._place_unowned_access(devices, site_base_x, site_width, profile)
            site_base_x += site_width + profile.site_spacing

        regions = self._regions(plan.devices, profile)
        return plan, regions

    @staticmethod
    def _place_site_infrastructure(
        devices: list[DevicePlan], site_x: int, site_width: int, profile: LayoutProfile,
    ) -> None:
        layers: dict[str, list[DevicePlan]] = defaultdict(list)
        for device in devices:
            if device.network_layer and device.network_layer != NetworkLayer.ACCESS.value:
                layers[device.network_layer].append(device)
        for layer, layer_devices in sorted(layers.items(), key=lambda item: _LAYER_ROW.get(item[0], 99)):
            ordered = sorted(layer_devices, key=lambda item: item.id)
            total_width = max(0, len(ordered) - 1) * profile.horizontal_spacing
            start_x = site_x + max(profile.horizontal_spacing, (site_width - total_width) // 2)
            y = profile.origin_y + _LAYER_ROW.get(layer, 0) * profile.vertical_spacing
            for index, device in enumerate(ordered):
                device.x = start_x + index * profile.horizontal_spacing
                device.y = y

    @staticmethod
    def _place_zone(devices: list[DevicePlan], zone_x: int, profile: LayoutProfile) -> None:
        access = sorted(
            (device for device in devices if device.network_layer == NetworkLayer.ACCESS.value),
            key=lambda item: item.id,
        )
        for index, device in enumerate(access):
            device.x = zone_x + profile.horizontal_spacing + index * profile.horizontal_spacing
            device.y = profile.origin_y + _LAYER_ROW[NetworkLayer.ACCESS.value] * profile.vertical_spacing

        endpoints = sorted(
            (device for device in devices if not device.network_layer),
            key=lambda item: (item.enterprise_role, item.id),
        )
        paired: dict[str, list[DevicePlan]] = defaultdict(list)
        unpaired: list[DevicePlan] = []
        for endpoint in endpoints:
            pair_id = endpoint.metadata.get("pair_id", "")
            if pair_id:
                paired[pair_id].append(endpoint)
            else:
                unpaired.append(endpoint)

        endpoint_y = profile.origin_y + 5 * profile.vertical_spacing
        for pair_index, pair_id in enumerate(sorted(paired)):
            row, column = divmod(pair_index, profile.endpoint_row_size)
            x = zone_x + profile.horizontal_spacing + column * profile.horizontal_spacing
            y = endpoint_y + row * profile.vertical_spacing * 2
            pair_devices = sorted(
                paired[pair_id],
                key=lambda item: 0 if item.enterprise_role == DeviceRole.IP_PHONE.value else 1,
            )
            for endpoint in pair_devices:
                endpoint.x = x
                endpoint.y = y if endpoint.enterprise_role == DeviceRole.IP_PHONE.value else y + profile.paired_endpoint_offset

        pair_rows = (len(paired) + profile.endpoint_row_size - 1) // profile.endpoint_row_size
        unpaired_y = endpoint_y + pair_rows * profile.vertical_spacing * 2
        role_groups: dict[str, list[DevicePlan]] = defaultdict(list)
        for endpoint in unpaired:
            role_groups[endpoint.enterprise_role].append(endpoint)
        role_row = 0
        for role in sorted(role_groups):
            role_devices = sorted(role_groups[role], key=lambda item: item.id)
            for item_index, endpoint in enumerate(role_devices):
                row, column = divmod(item_index, profile.endpoint_row_size)
                endpoint.x = zone_x + profile.horizontal_spacing + column * profile.horizontal_spacing
                endpoint.y = unpaired_y + (role_row + row) * profile.vertical_spacing
            role_row += max(1, (len(role_devices) + profile.endpoint_row_size - 1) // profile.endpoint_row_size)

    @staticmethod
    def _place_unowned_access(
        devices: list[DevicePlan], site_x: int, site_width: int, profile: LayoutProfile,
    ) -> None:
        unowned = sorted(
            (
                device for device in devices
                if device.network_layer == NetworkLayer.ACCESS.value and not device.zone_id
            ),
            key=lambda item: item.id,
        )
        for index, device in enumerate(unowned):
            device.x = site_x + site_width // 2 + index * profile.horizontal_spacing
            device.y = profile.origin_y + _LAYER_ROW[NetworkLayer.ACCESS.value] * profile.vertical_spacing

    @staticmethod
    def _regions(devices: list[DevicePlan], profile: LayoutProfile) -> list[LayoutRegion]:
        regions: list[LayoutRegion] = []
        groupings = (
            ("site", "site_id", ""),
            ("building", "building_id", "site_id"),
            ("floor", "floor_id", "building_id"),
            ("zone", "zone_id", "floor_id"),
        )
        for kind, attribute, parent_attribute in groupings:
            ids = sorted({getattr(device, attribute) for device in devices if getattr(device, attribute)})
            for group_id in ids:
                members = [device for device in devices if getattr(device, attribute) == group_id]
                if not members:
                    continue
                padding = profile.horizontal_spacing // 2
                min_x = min(device.x for device in members) - padding
                min_y = min(device.y for device in members) - padding
                max_x = max(device.x for device in members) + padding
                max_y = max(device.y for device in members) + padding
                parent_id = getattr(members[0], parent_attribute) if parent_attribute else ""
                regions.append(LayoutRegion(
                    id=group_id,
                    kind=kind,
                    parent_id=parent_id,
                    x=min_x,
                    y=min_y,
                    width=max_x - min_x,
                    height=max_y - min_y,
                ))
        return sorted(regions, key=lambda item: (item.kind, item.id))
