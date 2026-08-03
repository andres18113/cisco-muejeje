"""Caso de uso E8 para compilar un SecurityPlan backend-neutral."""

from __future__ import annotations

from ...domain.enterprise.models.configuration import ConfigurationPlan
from ...domain.enterprise.models.security_plan import (
    SecurityCapabilityProfile,
    SecurityCompileResult,
    SecurityIntent,
)
from ...domain.enterprise.models.service_plan import ServicePlan
from ...domain.enterprise.models.voice_plan import VoicePlan
from ...domain.enterprise.services.security_compiler import SecurityCompiler
from ...domain.models.plans import TopologyPlan


def compile_enterprise_security(
    intent: SecurityIntent,
    topology: TopologyPlan,
    configuration: ConfigurationPlan,
    *,
    service_plan: ServicePlan | None = None,
    voice_plan: VoicePlan | None = None,
    capabilities: dict[str, SecurityCapabilityProfile] | None = None,
) -> SecurityCompileResult:
    return SecurityCompiler().compile(
        intent,
        topology,
        configuration,
        service_plan=service_plan,
        voice_plan=voice_plan,
        capabilities=capabilities,
    )
