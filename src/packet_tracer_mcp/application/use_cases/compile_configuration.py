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
from ...infrastructure.catalog.link_mode_capabilities import link_mode_capability_for


def compile_enterprise_configuration(
    enterprise: EnterprisePlan,
    topology: TopologyPlan,
    policy: ConfigurationPolicy = ConfigurationPolicy(),
    capabilities: dict[str, DeviceCapabilities] | None = None,
) -> ConfigurationCompileResult:
    """Compila la configuración con los perfiles de enlace del backend real.

    Aquí es donde el conocimiento concreto de Packet Tracer entra al pipeline:
    el compilador es de dominio y no sabe qué backend hay debajo, así que se lo
    inyecta quien sí puede saberlo.
    """
    return ConfigurationCompiler(
        link_mode_capability_resolver=link_mode_capability_for,
    ).compile(enterprise, topology, policy, capabilities)
