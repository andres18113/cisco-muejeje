"""Product composition for the governed canonical CP-SCALE topology.

The generic reference composer remains capacity-driven.  CP-SCALE has a
separate, document-governed physical design, so its exact hardware binding must
use ``ReferenceHardwarePlanner`` rather than silently falling back to capacity
allocation.  This module is the production seam shared by offline inspection
and bounded LIVE qualification.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.enterprise.models.capabilities import DeviceCapabilities
from ...domain.enterprise.models.configuration import (
    ConfigurationActionType,
    ConfigurationPlan,
)
from ...domain.enterprise.models.control_plane import (
    ControlPlaneCapabilityProfile,
    ControlPlanePlan,
    ControlPlaneVerificationKind,
)
from ...domain.enterprise.services.configuration_compiler import (
    configuration_plan_semantic_hash,
)
from ...domain.enterprise.services.control_plane_compiler import (
    control_plane_plan_semantic_hash,
)
from ...domain.enterprise.services.enterprise_designer import EnterpriseDesigner
from ...domain.enterprise.services.reference_hardware_planner import (
    ReferenceHardwarePlanner,
)
from ...domain.enterprise.services.topology_identity import stamp_topology_hashes
from ...domain.enterprise.services.traffic_attribution import (
    attribute_enterprise_traffic,
)
from ...domain.enterprise.scenarios.cp_scale import cp_scale_intent
from ...domain.enterprise.scenarios.cp_scale_physical import (
    cp_scale_canonical_control_plane_intent,
    cp_scale_physical_design,
)
from ...domain.models.plans import TopologyPlan
from ...infrastructure.catalog.control_plane_capabilities import (
    packet_tracer_control_plane_capabilities,
)
from ...infrastructure.catalog.enterprise_topology import (
    PacketTracerTopologyCatalogAdapter,
)
from ...infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)
from .compile_configuration import compile_enterprise_configuration
from .compile_control_plane import compile_enterprise_control_plane
from .compile_enterprise import compile_enterprise_topology
from .compose_enterprise_reference import EnterpriseReferenceComposition
from .plan_enterprise_hardware import (
    EnterpriseHardwareComposition,
    capability_catalog_for,
)


_CORE_ROUTER_NAMES = frozenset(("Router0", "Router3", "Router4"))
_CORE_CONFIGURATION_TYPES = frozenset((
    ConfigurationActionType.CONFIGURE_HOSTNAME,
    ConfigurationActionType.CONFIGURE_ROUTED_INTERFACE,
    ConfigurationActionType.CONFIGURE_SUBINTERFACE,
))


@dataclass(frozen=True)
class CPScaleRoutingCore:
    """Exact typed plans and forwarding probes for the serial routing core."""

    topology: TopologyPlan
    configuration: ConfigurationPlan
    control_plane: ControlPlanePlan
    forwarding_checks: dict[str, str]


def compose_cp_scale_canonical(
    *,
    packet_tracer_version: str,
    capability_store: CapabilitySnapshotStore | None = None,
    control_plane_capabilities: (
        dict[str, ControlPlaneCapabilityProfile] | None
    ) = None,
) -> EnterpriseReferenceComposition:
    """Compose the exact 314-device/219-link CP-SCALE product plans."""

    designed = EnterpriseDesigner().design(cp_scale_intent())
    if not designed.validation.is_valid or designed.plan is None:
        return EnterpriseReferenceComposition(issues=[
            f"E4 design: {item.message}" for item in designed.validation.errors
        ] or ["E4 design produced no plan."])
    enterprise = designed.plan

    capability_catalog = capability_catalog_for(
        packet_tracer_version, capability_store=capability_store,
    )
    switch_candidates = capability_catalog.hardware_candidates(
        "switch", packet_tracer_version,
    )
    router_candidates = capability_catalog.hardware_candidates(
        "router", packet_tracer_version,
    )
    hardware_plan = ReferenceHardwarePlanner().plan(
        enterprise,
        cp_scale_physical_design(),
        [*router_candidates, *switch_candidates],
    )
    hardware = EnterpriseHardwareComposition(
        plan=hardware_plan,
        switch_candidates=switch_candidates,
        router_candidates=router_candidates,
        packet_tracer_version=packet_tracer_version,
    )

    topology_catalog = PacketTracerTopologyCatalogAdapter()
    compiled = compile_enterprise_topology(
        enterprise,
        hardware_plan,
        topology_catalog.compilation_profile(),
        topology_catalog.cable_for,
    )
    if not compiled.is_valid or compiled.plan is None:
        return EnterpriseReferenceComposition(
            enterprise=enterprise,
            hardware=hardware,
            topology_summary=compiled.summary,
            issues=[f"E5 compile: {item.message}" for item in compiled.issues]
            or ["E5 compilation produced no topology."],
        )
    topology = compiled.plan
    capabilities = {
        model: (
            capability_catalog.capabilities_for(model, packet_tracer_version)
            or DeviceCapabilities(model=model)
        )
        for model in sorted({item.model for item in topology.devices})
    }

    traffic = attribute_enterprise_traffic(enterprise, topology)
    if not traffic.is_valid:
        return EnterpriseReferenceComposition(
            enterprise=enterprise,
            hardware=hardware,
            topology=topology,
            topology_summary=compiled.summary,
            traffic=traffic,
            capabilities=capabilities,
            issues=[f"traffic: {item.message}" for item in traffic.issues],
        )

    configuration = compile_enterprise_configuration(
        enterprise,
        topology,
        capabilities=capabilities,
        traffic_by_link=traffic.contributions_by_link,
        packet_tracer_version=packet_tracer_version,
    )
    if not configuration.is_valid or configuration.plan is None:
        return EnterpriseReferenceComposition(
            enterprise=enterprise,
            hardware=hardware,
            topology=topology,
            topology_summary=compiled.summary,
            traffic=traffic,
            capabilities=capabilities,
            issues=[
                f"E5 configuration: {item.message}" for item in configuration.issues
            ] or ["Configuration compilation produced no plan."],
        )

    control = compile_enterprise_control_plane(
        cp_scale_canonical_control_plane_intent(topology),
        topology,
        configuration.plan,
        capabilities=(
            control_plane_capabilities
            if control_plane_capabilities is not None
            else packet_tracer_control_plane_capabilities(packet_tracer_version)
        ),
        traffic_flows=enterprise.traffic_flows,
    )
    if not control.is_valid or control.plan is None:
        return EnterpriseReferenceComposition(
            enterprise=enterprise,
            hardware=hardware,
            topology=topology,
            topology_summary=compiled.summary,
            traffic=traffic,
            capabilities=capabilities,
            configuration=configuration.plan,
            issues=[f"E9 control plane: {item.message}" for item in control.issues]
            or ["Control-plane compilation produced no plan."],
        )

    return EnterpriseReferenceComposition(
        enterprise=enterprise,
        hardware=hardware,
        topology=topology,
        topology_summary=compiled.summary,
        traffic=traffic,
        capabilities=capabilities,
        configuration=configuration.plan,
        control_plane=control.plan,
    )


def project_cp_scale_routing_core(
    composition: EnterpriseReferenceComposition,
    *,
    control_plane_capabilities: (
        dict[str, ControlPlaneCapabilityProfile] | None
    ) = None,
) -> CPScaleRoutingCore:
    """Project the exact three-router LIVE slice from a canonical composition.

    The LAN subinterfaces remain in E5 so the RIP process retains the canonical
    classful site statements and passive-interface policy.  Learned-route
    expectations are narrowed to the three physically operational /30 transit
    foundations; the LAN trunks are intentionally outside this first slice.
    """

    if (
        not composition.valid
        or composition.enterprise is None
        or composition.topology is None
        or composition.configuration is None
    ):
        raise ValueError("A complete canonical composition is required.")

    full_topology = composition.topology
    router_ids = {
        item.id for item in full_topology.devices if item.name in _CORE_ROUTER_NAMES
    }
    if len(router_ids) != 3:
        raise ValueError("The canonical composition does not contain the routing core.")
    core_topology = full_topology.model_copy(deep=True)
    core_topology.id = "cp-scale-canonical-routing-core"
    core_topology.name = "CP-SCALE canonical routing core"
    core_topology.devices = [
        item for item in core_topology.devices if item.id in router_ids
    ]
    core_topology.modules = [
        item for item in core_topology.modules if item.device in _CORE_ROUTER_NAMES
    ]
    core_topology.links = [
        item for item in core_topology.links
        if item.device_a_id in router_ids and item.device_b_id in router_ids
    ]
    stamp_topology_hashes(core_topology)

    selected_actions = [
        item.model_copy(deep=True)
        for item in composition.configuration.actions
        if item.device_id in router_ids and item.action_type in _CORE_CONFIGURATION_TYPES
    ]
    selected_ids = {item.id for item in selected_actions}
    for action in selected_actions:
        action.depends_on = [
            item for item in action.depends_on if item in selected_ids
        ]
        action.apply_dependencies = list(action.depends_on)
    selected_expectations = [
        item.model_copy(deep=True)
        for item in composition.configuration.verification_expectations
        if item.action_id in selected_ids
    ]
    selected_devices = []
    for item in composition.configuration.devices:
        if item.device_id not in router_ids:
            continue
        action_ids = [identifier for identifier in item.action_ids if identifier in selected_ids]
        required = sorted({
            action.required_capability
            for action in selected_actions
            if action.device_id == item.device_id and action.required_capability
        })
        selected_devices.append(item.model_copy(update={
            "action_ids": action_ids,
            "required_capabilities": required,
        }))
    core_configuration = ConfigurationPlan(
        id="cfg_cp-scale-canonical-routing-core",
        source_topology_id=core_topology.id,
        source_topology_hash=core_topology.physical_identity_hash,
        source_topology_hash_schema="physical-topology-v2",
        actions=selected_actions,
        devices=selected_devices,
        verification_expectations=selected_expectations,
    )
    core_configuration.semantic_hash = configuration_plan_semantic_hash(
        core_configuration,
    )

    canonical_control = cp_scale_canonical_control_plane_intent(full_topology)
    routing_only = canonical_control.model_copy(update={"stp_domains": []})
    compiled_control = compile_enterprise_control_plane(
        routing_only,
        core_topology,
        core_configuration,
        capabilities=(
            control_plane_capabilities
            if control_plane_capabilities is not None
            else packet_tracer_control_plane_capabilities()
        ),
    )
    if not compiled_control.is_valid or compiled_control.plan is None:
        raise ValueError(
            "Canonical routing-core control plane did not compile: "
            + "; ".join(item.message for item in compiled_control.issues)
        )
    core_control = compiled_control.plan
    core_control.verification_expectations = [
        item for item in core_control.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTING_PROCESS
        or (
            item.kind is ControlPlaneVerificationKind.ROUTE_PRESENT
            and int(item.expected.get("prefix_length", -1)) == 30
            and str(item.expected.get("network", "")).startswith("10.0.0.")
        )
    ]
    core_control.verification_expectations.sort(key=lambda item: (
        0 if item.kind is ControlPlaneVerificationKind.ROUTING_PROCESS else 1,
        item.id,
    ))
    core_control.semantic_hash = control_plane_plan_semantic_hash(core_control)

    return CPScaleRoutingCore(
        topology=core_topology,
        configuration=core_configuration,
        control_plane=core_control,
        forwarding_checks={
            "Router4": "10.0.0.10",
            "Router0": "10.0.0.6",
            "Router3": "10.0.0.1",
        },
    )
