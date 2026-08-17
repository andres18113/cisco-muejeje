"""Use case puro para compilar la configuración E5."""

from __future__ import annotations

from ...domain.enterprise.models.capabilities import DeviceCapabilities
from ...domain.enterprise.models.configuration import (
    ConfigurationCompileResult,
    ConfigurationPolicy,
)
from ...domain.enterprise.models.enterprise_plan import EnterprisePlan
from ...domain.enterprise.models.deployment import DeploymentManifest
from ...domain.enterprise.models.link_performance import TrafficContribution
from ...domain.enterprise.services.configuration_compiler import ConfigurationCompiler
from ...domain.enterprise.services.link_performance_planner import LinkPerformancePlanner
from ...domain.models.plans import TopologyPlan
from ...infrastructure.catalog.link_mode_capabilities import (
    PT_2911_HWIC2T_SERIAL_CLOCK,
    link_mode_capability_for,
)


def compile_enterprise_configuration(
    enterprise: EnterprisePlan,
    topology: TopologyPlan,
    policy: ConfigurationPolicy = ConfigurationPolicy(),
    capabilities: dict[str, DeviceCapabilities] | None = None,
    *,
    deployment_manifest: DeploymentManifest | None = None,
    traffic_by_link: dict[str, list[TrafficContribution]] | None = None,
    packet_tracer_version: str = "",
) -> ConfigurationCompileResult:
    """Compila la configuración con los perfiles de enlace del backend real.

    Aquí es donde el conocimiento concreto de Packet Tracer entra al pipeline:
    el compilador es de dominio y no sabe qué backend hay debajo, así que se lo
    inyecta quien sí puede saberlo.
    """
    if packet_tracer_version:
        measured = PT_2911_HWIC2T_SERIAL_CLOCK.backend_version
        if packet_tracer_version != measured:
            raise ValueError(
                "No verified 2911/HWIC-2T serial-clock rates exist for Packet "
                f"Tracer {packet_tracer_version!r}; measured version is {measured!r}."
            )
        if (
            deployment_manifest is not None
            and deployment_manifest.backend_version != packet_tracer_version
        ):
            raise ValueError(
                "DeploymentManifest backend version does not match the requested "
                "Packet Tracer capability profile."
            )

    def resolve_link_mode(model: str, interface: str):
        return link_mode_capability_for(
            model,
            interface,
            backend_version=packet_tracer_version,
        )

    planner = (
        LinkPerformancePlanner(
            supported_serial_rates_bps=(
                PT_2911_HWIC2T_SERIAL_CLOCK.verified_rates_bps
            ),
        )
        if packet_tracer_version
        else None
    )
    return ConfigurationCompiler(
        link_mode_capability_resolver=resolve_link_mode,
        link_performance_planner=planner,
    ).compile(
        enterprise,
        topology,
        policy,
        capabilities,
        deployment_manifest=deployment_manifest,
        traffic_by_link=traffic_by_link,
    )
