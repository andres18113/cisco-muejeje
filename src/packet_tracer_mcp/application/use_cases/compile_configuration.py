"""Use case puro para compilar la configuración E5."""

from __future__ import annotations

from ...domain.enterprise.models.capabilities import DeviceCapabilities
from ...domain.enterprise.models.configuration import (
    ConfigurationCompileResult,
    ConfigurationPolicy,
)
from ...domain.enterprise.models.enterprise_plan import EnterprisePlan
from ...domain.enterprise.services.configuration_compiler import ConfigurationCompiler
from ...domain.models.plans import TopologyPlan


def compile_enterprise_configuration(
    enterprise: EnterprisePlan,
    topology: TopologyPlan,
    policy: ConfigurationPolicy = ConfigurationPolicy(),
    capabilities: dict[str, DeviceCapabilities] | None = None,
) -> ConfigurationCompileResult:
    return ConfigurationCompiler().compile(enterprise, topology, policy, capabilities)
