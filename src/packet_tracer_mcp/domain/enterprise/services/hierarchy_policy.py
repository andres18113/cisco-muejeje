"""Reglas deterministas de capas y patrones, sin escoger hardware."""

from __future__ import annotations

from ..models.enterprise_plan import SitePlan
from ..models.intent import SiteType
from ..models.topology import NetworkLayer, TopologyDesign, TopologyPattern


class HierarchyPlanner:
    """Selecciona una estructura semántica proporcional al tamaño del sitio."""

    def design(self, site_plan: SitePlan) -> TopologyDesign:
        endpoint_count = sum(segment.host_requirement for segment in site_plan.segments)
        if site_plan.type in {SiteType.HQ, SiteType.DATACENTER} or endpoint_count > 96:
            return TopologyDesign(
                pattern=TopologyPattern.HYBRID,
                network_layers=[
                    NetworkLayer.ACCESS, NetworkLayer.DISTRIBUTION,
                    NetworkLayer.CORE, NetworkLayer.EDGE,
                ],
                layer_patterns={
                    NetworkLayer.ACCESS: TopologyPattern.STAR,
                    NetworkLayer.DISTRIBUTION: TopologyPattern.HIERARCHICAL,
                    NetworkLayer.CORE: TopologyPattern.HIERARCHICAL,
                    NetworkLayer.EDGE: TopologyPattern.POINT_TO_POINT,
                },
            )
        if endpoint_count > 24:
            return TopologyDesign(
                pattern=TopologyPattern.EXTENDED_STAR,
                network_layers=[NetworkLayer.ACCESS, NetworkLayer.EDGE],
                layer_patterns={
                    NetworkLayer.ACCESS: TopologyPattern.STAR,
                    NetworkLayer.EDGE: TopologyPattern.POINT_TO_POINT,
                },
            )
        return TopologyDesign(
            pattern=TopologyPattern.STAR,
            network_layers=[NetworkLayer.ACCESS, NetworkLayer.EDGE],
            layer_patterns={
                NetworkLayer.ACCESS: TopologyPattern.STAR,
                NetworkLayer.EDGE: TopologyPattern.POINT_TO_POINT,
            },
        )
