"""Composicion offline del producto: intent semantico -> planes compilados.

Puro y sin runtime. No abre un bridge, no toca Packet Tracer y no muta nada.
Existe para que la mitad determinista del producto sea una sola funcion en vez
de una cadena que cada llamador vuelva a ensamblar a mano -- que es exactamente
lo que pasaba: la cadena completa solo existia como `_product_chain()` dentro de
`tests/test_stage3a4_product_composition.py`, y una cadena que solo vive en un
test no es una superficie de producto.

El manifiesto de despliegue es opcional y esa opcionalidad es el punto:

- sin manifiesto -> se compone hasta trafico. Es lo que puede saberse antes de
  desplegar, y es lo que una superficie de inspeccion offline debe poder pedir.
- con manifiesto -> ademas configuracion y plano de control, porque la
  orientacion DCE/DTE la decide el cable y solo se conoce leyendola del
  despliegue.

Sin manifiesto observado el compilador no emite reloj serial en vez de
adivinarlo, y esa decision vive en `configuration_compiler`, no aqui.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...domain.enterprise.models.capabilities import DeviceCapabilities
from ...domain.enterprise.models.control_plane import ControlPlaneIntent, ControlPlanePlan
from ...domain.enterprise.models.configuration import ConfigurationPlan
from ...domain.enterprise.models.deployment import DeploymentManifest
from ...domain.enterprise.models.enterprise_plan import EnterprisePlan
from ...domain.enterprise.models.hardware import HardwarePlan
from ...domain.enterprise.models.intent import EnterpriseIntent
from ...domain.enterprise.models.link_performance import TrafficAttributionResult
from ...domain.enterprise.services.enterprise_designer import EnterpriseDesigner
from ...domain.enterprise.services.hardware_planner import HardwarePlanningPolicy
from ...domain.enterprise.services.traffic_attribution import attribute_enterprise_traffic
from ...infrastructure.catalog.enterprise_topology import PacketTracerTopologyCatalogAdapter
from ...infrastructure.persistence.capability_snapshot_store import CapabilitySnapshotStore
from ...domain.models.plans import TopologyPlan
from .compile_configuration import compile_enterprise_configuration
from .compile_control_plane import compile_enterprise_control_plane
from .compile_enterprise import compile_enterprise_topology
from .plan_enterprise_hardware import (
    EnterpriseHardwareComposition,
    capability_catalog_for,
    plan_enterprise_hardware,
)


@dataclass(frozen=True)
class EnterpriseReferenceComposition:
    """Lo que se pudo componer, y por que se detuvo si se detuvo."""

    enterprise: EnterprisePlan | None = None
    hardware: EnterpriseHardwareComposition | None = None
    topology: TopologyPlan | None = None
    traffic: TrafficAttributionResult | None = None
    configuration: ConfigurationPlan | None = None
    control_plane: ControlPlanePlan | None = None
    #: La resolucion de capacidades con la que se compilo E5, publicada para
    #: que quien aplique use EXACTAMENTE la misma. Resolverla dos veces dejaria
    #: que compilacion y aplicacion discrepen sobre que soporta el build.
    capabilities: dict[str, DeviceCapabilities] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        """Compuesto hasta donde se pidio, sin incidencias."""
        return not self.issues

    @property
    def hardware_plan(self) -> HardwarePlan | None:
        return self.hardware.plan if self.hardware is not None else None

    def compact_summary(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "sites": len(self.enterprise.sites) if self.enterprise else 0,
            "devices": len(self.topology.devices) if self.topology else 0,
            "links": len(self.topology.links) if self.topology else 0,
            "physical_topology_hash": (
                self.topology.physical_identity_hash if self.topology else ""
            ),
            "configuration_actions": (
                len(self.configuration.actions) if self.configuration else 0
            ),
            "control_plane_actions": (
                len(self.control_plane.actions) if self.control_plane else 0
            ),
            "issues": list(self.issues),
        }


def compose_enterprise_reference(
    intent: EnterpriseIntent,
    *,
    packet_tracer_version: str | None = None,
    capability_store: CapabilitySnapshotStore | None = None,
    deployment_manifest: DeploymentManifest | None = None,
    control_plane_intent: ControlPlaneIntent | None = None,
    policy: HardwarePlanningPolicy | None = None,
) -> EnterpriseReferenceComposition:
    """Compone el producto offline y se detiene en la primera etapa invalida."""
    designed = EnterpriseDesigner().design(intent)
    if not designed.validation.is_valid or designed.plan is None:
        return EnterpriseReferenceComposition(issues=[
            f"E4 design: {issue.message}" for issue in designed.validation.issues
        ] or ["E4 design produced no plan."])
    enterprise = designed.plan

    # Un solo adapter para toda la composicion: la seleccion de hardware y la
    # autorizacion de E5 tienen que leer la MISMA evidencia, de la misma
    # version exacta. Construir uno por consumidor abre la puerta a que
    # discrepen sin que nadie lo note.
    capability_catalog = capability_catalog_for(
        packet_tracer_version, capability_store=capability_store,
    )
    hardware = plan_enterprise_hardware(
        enterprise,
        packet_tracer_version=packet_tracer_version,
        capability_catalog=capability_catalog,
        policy=policy,
    )

    catalog = PacketTracerTopologyCatalogAdapter()
    compiled = compile_enterprise_topology(
        enterprise, hardware.plan, catalog.compilation_profile(), catalog.cable_for,
    )
    if not compiled.is_valid or compiled.plan is None:
        return EnterpriseReferenceComposition(
            enterprise=enterprise,
            hardware=hardware,
            issues=[f"E5 compile: {issue.message}" for issue in compiled.issues]
            or ["E5 compilation produced no topology."],
        )
    topology = compiled.plan
    # Resuelto sobre los modelos realmente desplegados. Un modelo sin
    # evidencia no queda fuera del mapa: entra con todo en UNKNOWN, que es
    # rechazo explicito y no una ausencia que alguien pueda leer como permiso.
    capabilities = {
        model: (
            capability_catalog.capabilities_for(model, packet_tracer_version)
            or DeviceCapabilities(model=model)
        )
        for model in sorted({device.model for device in topology.devices})
    }

    traffic = attribute_enterprise_traffic(enterprise, topology)
    if not traffic.is_valid:
        return EnterpriseReferenceComposition(
            enterprise=enterprise, hardware=hardware, topology=topology, traffic=traffic,
            capabilities=capabilities,
            issues=[f"traffic: {issue.message}" for issue in traffic.issues],
        )

    if deployment_manifest is None:
        return EnterpriseReferenceComposition(
            enterprise=enterprise, hardware=hardware, topology=topology, traffic=traffic,
            capabilities=capabilities,
        )

    configuration = compile_enterprise_configuration(
        enterprise,
        topology,
        capabilities=capabilities,
        deployment_manifest=deployment_manifest,
        traffic_by_link=traffic.contributions_by_link,
        packet_tracer_version=packet_tracer_version or "",
    )
    if not configuration.is_valid or configuration.plan is None:
        return EnterpriseReferenceComposition(
            enterprise=enterprise, hardware=hardware, topology=topology, traffic=traffic,
            capabilities=capabilities,
            issues=[f"E5 configuration: {issue.message}" for issue in configuration.issues]
            or ["Configuration compilation produced no plan."],
        )

    if control_plane_intent is None:
        return EnterpriseReferenceComposition(
            enterprise=enterprise, hardware=hardware, topology=topology, traffic=traffic,
            capabilities=capabilities, configuration=configuration.plan,
        )

    control_plane = compile_enterprise_control_plane(
        control_plane_intent,
        topology,
        configuration.plan,
        traffic_flows=enterprise.traffic_flows,
    )
    if not control_plane.is_valid or control_plane.plan is None:
        return EnterpriseReferenceComposition(
            enterprise=enterprise, hardware=hardware, topology=topology, traffic=traffic,
            capabilities=capabilities, configuration=configuration.plan,
            issues=[f"E9 control plane: {issue.message}" for issue in control_plane.issues]
            or ["Control-plane compilation produced no plan."],
        )

    return EnterpriseReferenceComposition(
        enterprise=enterprise,
        hardware=hardware,
        topology=topology,
        traffic=traffic,
        capabilities=capabilities,
        configuration=configuration.plan,
        control_plane=control_plane.plan,
    )
