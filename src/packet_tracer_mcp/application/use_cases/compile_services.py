"""Caso de uso E6 para compilar un ServicePlan backend-neutral."""

from __future__ import annotations

from ...domain.enterprise.models.configuration import ConfigurationPlan
from ...domain.enterprise.models.enterprise_plan import EnterprisePlan
from ...domain.enterprise.models.service_plan import (
    ServiceCapabilityProfile,
    ServiceCompileResult,
)
from ...domain.enterprise.services.service_compiler import ServiceCompiler
from ...domain.models.plans import TopologyPlan


def compile_enterprise_services(
    enterprise: EnterprisePlan,
    topology: TopologyPlan,
    configuration: ConfigurationPlan,
    *,
    capabilities: dict[str, ServiceCapabilityProfile] | None = None,
) -> ServiceCompileResult:
    return ServiceCompiler().compile(
        enterprise, topology, configuration, capabilities=capabilities,
    )
