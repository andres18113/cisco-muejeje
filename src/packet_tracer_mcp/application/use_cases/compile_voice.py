"""Caso de uso E7 para compilar un VoicePlan backend-neutral."""

from __future__ import annotations

from ...domain.enterprise.models.configuration import ConfigurationPlan
from ...domain.enterprise.models.enterprise_plan import EnterprisePlan
from ...domain.enterprise.models.service_plan import ServicePlan
from ...domain.enterprise.models.voice_plan import (
    VoiceCapabilityProfile,
    VoiceCompileResult,
    VoiceIntent,
)
from ...domain.enterprise.services.voice_compiler import VoiceCompiler
from ...domain.models.plans import TopologyPlan


def compile_enterprise_voice(
    intent: VoiceIntent,
    enterprise: EnterprisePlan,
    topology: TopologyPlan,
    configuration: ConfigurationPlan,
    *,
    service_plan: ServicePlan | None = None,
    capabilities: dict[str, VoiceCapabilityProfile] | None = None,
) -> VoiceCompileResult:
    return VoiceCompiler().compile(
        intent,
        enterprise,
        topology,
        configuration,
        service_plan=service_plan,
        capabilities=capabilities,
    )
