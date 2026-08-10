"""Caso de uso E9 para compilar un ControlPlanePlan backend-neutral."""

from __future__ import annotations

from collections.abc import Iterable

from ...domain.enterprise.models.configuration import ConfigurationPlan
from ...domain.enterprise.models.control_plane import (
    ControlPlaneCapabilityProfile,
    ControlPlaneCompileResult,
    ControlPlaneIntent,
)
from ...domain.enterprise.models.security_plan import SecurityPlan
from ...domain.enterprise.models.failure_domain import FailureDomain
from ...domain.enterprise.services.control_plane_compiler import ControlPlaneCompiler
from ...domain.models.plans import TopologyPlan


def compile_enterprise_control_plane(
    intent: ControlPlaneIntent,
    topology: TopologyPlan,
    configuration: ConfigurationPlan,
    *,
    security_plan: SecurityPlan | None = None,
    capabilities: dict[str, ControlPlaneCapabilityProfile] | None = None,
    failure_domains: Iterable[FailureDomain] = (),
) -> ControlPlaneCompileResult:
    return ControlPlaneCompiler().compile(
        intent,
        topology,
        configuration,
        security_plan=security_plan,
        capabilities=capabilities,
        failure_domains=failure_domains,
    )
