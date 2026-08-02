"""Cálculo agregado de puertos y PoE sin seleccionar modelos de switch."""

from __future__ import annotations

from ..models.capacity import AccessCapacityRequirement, PortAttachmentPolicy
from ..models.enterprise_plan import SitePlan
from ..models.roles import DeviceRole
from .hierarchy_planner import iter_zone_plans
from .ipam_planner import growth_hosts


_INFRASTRUCTURE_ROLES = {
    DeviceRole.ACCESS_SWITCH,
    DeviceRole.DISTRIBUTION_SWITCH,
    DeviceRole.CORE_SWITCH,
    DeviceRole.WAN_ROUTER,
    DeviceRole.EDGE_ROUTER,
    DeviceRole.FIREWALL,
}


class CapacityPlanner:
    """Opera en conteos por zona; nunca expande endpoints individuales."""

    def __init__(self, uplinks_per_access_switch: int = 2) -> None:
        self.uplinks_per_access_switch = uplinks_per_access_switch

    def plan_site(self, site: SitePlan) -> list[AccessCapacityRequirement]:
        requirements = [self._plan_zone(site, zone) for zone in iter_zone_plans(site)]
        site.capacity_requirements = requirements
        return requirements

    def _plan_zone(self, site: SitePlan, zone) -> AccessCapacityRequirement:
        wired_total = 0
        wired_pcs = 0
        wired_phones = 0
        poe_total = 0
        for group in zone.endpoint_groups:
            for endpoint in group.requirements:
                if endpoint.role in _INFRASTRUCTURE_ROLES or not endpoint.wired or endpoint.wireless:
                    continue
                wired_total += endpoint.count
                if endpoint.role is DeviceRole.USER_PC:
                    wired_pcs += endpoint.count
                if endpoint.role is DeviceRole.IP_PHONE:
                    wired_phones += endpoint.count
                if endpoint.requires_poe:
                    poe_total += endpoint.count

        pairs = min(wired_pcs, wired_phones) if site.pair_pc_with_ip_phone else 0
        base_access = wired_total - pairs
        growth = site.growth_percent
        reserved_access = growth_hosts(base_access, growth)
        reserved_poe = growth_hosts(poe_total, growth)
        return AccessCapacityRequirement(
            site_id=site.site_id,
            zone_id=zone.zone_id,
            raw_wired_endpoints=wired_total,
            base_access_ports=base_access,
            base_poe_ports=poe_total,
            pc_phone_pairs=pairs,
            growth_percent=growth,
            growth_reserved_access_ports=reserved_access,
            growth_reserved_poe_ports=reserved_poe,
            required_access_ports=base_access + reserved_access,
            required_poe_ports=poe_total + reserved_poe,
            required_uplink_ports=self.uplinks_per_access_switch if base_access else 0,
            attachment_policy=(
                PortAttachmentPolicy.PHONE_PASSTHROUGH
                if pairs else PortAttachmentPolicy.DIRECT
            ),
        )
