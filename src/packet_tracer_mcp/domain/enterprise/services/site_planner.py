"""Conversión determinista de un SiteIntent a su representación lógica."""

from __future__ import annotations

from collections import defaultdict

from ..models.enterprise_plan import SitePlan
from ..models.intent import SiteIntent
from ..models.requirements import AddressingPreference
from ..models.segments import NetworkSegment, SegmentRole
from .hierarchy_planner import PhysicalHierarchyPlanner, iter_zone_plans
from .hierarchy_policy import HierarchyPlanner
from .segment_assignment import SegmentAssignmentPolicy


def site_id_for(name: str) -> str:
    """Identificador estable para consultas y patches futuros, sin depender del modelo PT."""
    from .hierarchy_planner import hierarchy_id
    return hierarchy_id(name)


def plan_site(intent: SiteIntent, default_growth_percent: float) -> SitePlan:
    """Agrupa endpoints en segmentos semánticos sin asignar VLANs ni subredes."""
    growth_percent = intent.growth_percent if intent.growth_percent is not None else default_growth_percent
    plan = SitePlan(
        name=intent.name,
        site_id=site_id_for(intent.name),
        type=intent.type,
        endpoint_requirements=intent.endpoints,
        services=intent.services,
        growth_percent=growth_percent,
        address_block=intent.address_block,
        pair_pc_with_ip_phone=(
            intent.pair_pc_with_ip_phone
            if intent.pair_pc_with_ip_phone is not None else True
        ),
    )
    PhysicalHierarchyPlanner().plan(intent, plan)

    assignment = SegmentAssignmentPolicy()
    counts: dict[SegmentRole, int] = defaultdict(int)
    dhcp: dict[SegmentRole, bool] = defaultdict(bool)
    for zone in iter_zone_plans(plan):
        for group in zone.endpoint_groups:
            for endpoint in group.requirements:
                if not assignment.consumes_ipv4(endpoint):
                    continue
                role = assignment.segment_for(endpoint)
                counts[role] += endpoint.count
                dhcp[role] = dhcp[role] or endpoint.addressing_preference == AddressingPreference.DHCP

    plan.segments = [
        NetworkSegment(
            name=f"{plan.site_id}-{role.value}",
            role=role,
            site=plan.site_id,
            host_requirement=count,
            growth_percent=None,
            dhcp=dhcp[role],
        )
        for role, count in sorted(counts.items(), key=lambda item: item[0].value)
    ]
    plan.topology = HierarchyPlanner().design(plan)
    return plan
