"""Authoritative offline qualification for the canonical CP-SCALE intent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns

from pydantic import BaseModel

from ...domain.enterprise.models.capabilities import DeviceCapabilities
from ...domain.enterprise.models.compilation import EnterpriseCompileResult, LayoutProfile
from ...domain.enterprise.models.configuration import (
    ConfigurationActionType,
    ConfigurationCompileResult,
)
from ...domain.enterprise.models.configuration_runtime import RuntimeConfigurationTarget
from ...domain.enterprise.models.control_plane import (
    ControlPlaneCapabilityProfile,
    ControlPlaneCompileResult,
    ControlPlaneIntent,
    DynamicRoutingIntent,
    DynamicRoutingProtocol,
    StpIntent,
    StpMode,
)
from ...domain.enterprise.models.deployment import (
    DeploymentLinkBinding,
    DeploymentLinkEndpoint,
    DeploymentManifest,
    EnvironmentFingerprint,
    SerialEndpointOrientation,
    build_deployment_manifest,
)
from ...domain.enterprise.models.enterprise_plan import EnterprisePlan
from ...domain.enterprise.models.hardware import (
    HardwareCandidate,
    HardwarePlan,
    HardwarePlanStatus,
)
from ...domain.enterprise.models.intent import EnterpriseIntent
from ...domain.enterprise.models.link_performance import TrafficAttributionResult
from ...domain.enterprise.models.voice_plan import (
    ExtensionRange,
    VoiceCapabilityProfile,
    VoiceCompileResult,
    VoiceIntent,
)
from ...domain.enterprise.scenarios.cp_scale import cp_scale_intent
from ...domain.enterprise.services.enterprise_designer import EnterpriseDesigner
from ...domain.enterprise.services.hardware_planner import (
    HardwarePlanner,
    HardwarePlanningPolicy,
)
from ...domain.enterprise.services.traffic_attribution import attribute_enterprise_traffic
from ...domain.models.plans import TopologyPlan
from ...infrastructure.catalog.enterprise_topology import PacketTracerTopologyCatalogAdapter
from ...infrastructure.catalog.link_mode_capabilities import PT_2911_HWIC2T_SERIAL_CLOCK
from ...shared.utils import resolve_within, safe_name_component
from .compile_configuration import compile_enterprise_configuration
from .compile_control_plane import compile_enterprise_control_plane
from .compile_enterprise import compile_enterprise_topology
from .compile_voice import compile_enterprise_voice


class CPScaleStageMetric(BaseModel):
    stage: str
    duration_ms: float
    item_count: int = 0
    issue_count: int = 0


@dataclass
class CPScaleOfflineQualification:
    intent: EnterpriseIntent
    enterprise: EnterprisePlan | None = None
    hardware: HardwarePlan | None = None
    topology: EnterpriseCompileResult | None = None
    structural_manifest: DeploymentManifest | None = None
    traffic: TrafficAttributionResult | None = None
    configuration: ConfigurationCompileResult | None = None
    control_plane: ControlPlaneCompileResult | None = None
    voice: VoiceCompileResult | None = None
    stages: list[CPScaleStageMetric] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return (
            not self.blocking_issues
            and self.enterprise is not None
            and self.hardware is not None
            and self.hardware.status is HardwarePlanStatus.VALID
            and self.topology is not None
            and self.topology.is_valid
            and self.topology.plan is not None
            and self.traffic is not None
            and self.traffic.is_valid
            and self.configuration is not None
            and self.configuration.is_valid
            and self.configuration.plan is not None
            and self.control_plane is not None
            and self.control_plane.is_valid
            and self.voice is not None
            and self.voice.is_valid
        )

    def compact_summary(self) -> dict[str, object]:
        topology = self.topology
        configuration = self.configuration
        control_plane = self.control_plane
        voice = self.voice
        return {
            "valid": self.valid,
            "workload_endpoints": topology.summary.workload_endpoints if topology else 0,
            "access_points": topology.summary.access_points if topology else 0,
            "network_devices": topology.summary.network_devices if topology else 0,
            "devices": topology.summary.devices if topology else 0,
            "links": topology.summary.links if topology else 0,
            "hashes": {
                "physical": topology.physical_topology_hash if topology else "",
                "layout": topology.layout_hash if topology else "",
                "artifact": topology.artifact_hash if topology else "",
                "configuration": configuration.semantic_hash if configuration else "",
                "control_plane": control_plane.semantic_hash if control_plane else "",
                "voice": voice.semantic_hash if voice else "",
            },
            "actions": {
                "configuration": configuration.summary.action_count if configuration else 0,
                "control_plane": control_plane.summary.action_count if control_plane else 0,
                "voice": voice.summary.action_count if voice else 0,
            },
            "layout_metrics": (
                topology.layout_metrics.model_dump(mode="json") if topology else {}
            ),
            "substitutions": (
                [item.model_dump(mode="json") for item in topology.substitutions]
                if topology else []
            ),
            "stages": [item.model_dump(mode="json") for item in self.stages],
            "blocking_issues": list(self.blocking_issues),
        }


def qualify_cp_scale_offline(
    *,
    switch_candidates: list[HardwareCandidate],
    router_candidates: list[HardwareCandidate],
    layout_profile: LayoutProfile = LayoutProfile(),
    hardware_policy: HardwarePlanningPolicy = HardwarePlanningPolicy(),
    configuration_capabilities: dict[str, DeviceCapabilities] | None = None,
    control_plane_capabilities: dict[str, ControlPlaneCapabilityProfile] | None = None,
    voice_capabilities: dict[str, VoiceCapabilityProfile] | None = None,
) -> CPScaleOfflineQualification:
    """Compile every existing-scope typed plan; no bridge or runtime is touched."""
    result = CPScaleOfflineQualification(intent=cp_scale_intent())

    started = perf_counter_ns()
    designed = EnterpriseDesigner().design(result.intent)
    result.stages.append(_metric(
        "design", started,
        item_count=sum(len(site.segments) for site in designed.plan.sites) if designed.plan else 0,
        issue_count=len(designed.validation.errors) + len(designed.validation.warnings),
    ))
    if not designed.validation.is_valid or designed.plan is None:
        result.blocking_issues.extend(
            f"design: {item.message}" for item in designed.validation.errors
        )
        return result
    result.enterprise = designed.plan

    started = perf_counter_ns()
    result.hardware = HardwarePlanner().plan(
        result.enterprise,
        switch_candidates,
        router_candidates,
        hardware_policy,
    )
    result.stages.append(_metric(
        "hardware", started,
        item_count=sum(len(item.devices) for item in result.hardware.site_hardware),
        issue_count=len(result.hardware.warnings),
    ))
    if result.hardware.status is not HardwarePlanStatus.VALID:
        result.blocking_issues.extend(
            f"hardware: {item}" for item in result.hardware.warnings
        )
        return result

    started = perf_counter_ns()
    physical = PacketTracerTopologyCatalogAdapter()
    result.topology = compile_enterprise_topology(
        result.enterprise,
        result.hardware,
        physical.compilation_profile(),
        physical.cable_for,
        layout_profile,
    )
    result.stages.append(_metric(
        "topology", started,
        item_count=result.topology.summary.devices,
        issue_count=len(result.topology.issues),
    ))
    if not result.topology.is_valid or result.topology.plan is None:
        result.blocking_issues.extend(
            f"topology: {item.message}" for item in result.topology.issues
        )
        return result
    topology = result.topology.plan

    started = perf_counter_ns()
    result.structural_manifest = _structural_manifest(topology)
    result.stages.append(_metric(
        "structural_manifest", started,
        item_count=len(result.structural_manifest.bindings),
    ))

    started = perf_counter_ns()
    result.traffic = attribute_enterprise_traffic(result.enterprise, topology)
    result.stages.append(_metric(
        "traffic", started,
        item_count=len(result.traffic.paths_by_flow),
        issue_count=len(result.traffic.issues),
    ))
    if not result.traffic.is_valid:
        result.blocking_issues.extend(
            f"traffic: {item.message}" for item in result.traffic.issues
        )
        return result

    started = perf_counter_ns()
    result.configuration = compile_enterprise_configuration(
        result.enterprise,
        topology,
        capabilities=configuration_capabilities,
        deployment_manifest=result.structural_manifest,
        traffic_by_link=result.traffic.contributions_by_link,
        packet_tracer_version=PT_2911_HWIC2T_SERIAL_CLOCK.backend_version,
    )
    result.stages.append(_metric(
        "configuration", started,
        item_count=result.configuration.summary.action_count,
        issue_count=len(result.configuration.issues),
    ))
    if not result.configuration.is_valid or result.configuration.plan is None:
        result.blocking_issues.extend(
            f"configuration: {item.message}" for item in result.configuration.issues
        )
        return result
    configuration = result.configuration.plan

    started = perf_counter_ns()
    control_intent = cp_scale_control_plane_intent(
        result.enterprise, topology, configuration,
    )
    result.control_plane = compile_enterprise_control_plane(
        control_intent,
        topology,
        configuration,
        capabilities=control_plane_capabilities,
        traffic_flows=result.enterprise.traffic_flows,
    )
    result.stages.append(_metric(
        "control_plane", started,
        item_count=result.control_plane.summary.action_count,
        issue_count=len(result.control_plane.issues),
    ))
    if not result.control_plane.is_valid:
        result.blocking_issues.extend(
            f"control_plane: {item.message}" for item in result.control_plane.issues
        )
        return result

    started = perf_counter_ns()
    result.voice = compile_enterprise_voice(
        cp_scale_voice_intent(topology),
        result.enterprise,
        topology,
        configuration,
        capabilities=voice_capabilities,
    )
    result.stages.append(_metric(
        "voice", started,
        item_count=result.voice.summary.action_count,
        issue_count=len(result.voice.issues),
    ))
    if not result.voice.is_valid:
        result.blocking_issues.extend(
            f"voice: {item.message}" for item in result.voice.issues
        )
    return result


def write_cp_scale_offline_artifacts(
    qualification: CPScaleOfflineQualification,
    base_dir: Path,
    run_name: str = "offline",
) -> Path:
    """Persist full ignored evidence under a path-confined run directory."""
    run_dir = resolve_within(base_dir, safe_name_component(run_name, "offline"))
    run_dir.mkdir(parents=True, exist_ok=True)
    payloads: dict[str, object] = {
        "intent.json": qualification.intent,
        "enterprise.json": qualification.enterprise,
        "hardware.json": qualification.hardware,
        "topology.json": qualification.topology,
        "structural-manifest.json": qualification.structural_manifest,
        "traffic.json": qualification.traffic,
        "configuration.json": qualification.configuration,
        "control-plane.json": qualification.control_plane,
        "voice.json": qualification.voice,
        "summary.json": qualification.compact_summary(),
    }
    for filename, payload in payloads.items():
        if payload is None:
            continue
        target = resolve_within(run_dir, safe_name_component(filename, "artifact.json"))
        serialized = (
            payload.model_dump(mode="json")
            if isinstance(payload, BaseModel)
            else payload
        )
        target.write_text(
            json.dumps(serialized, indent=2, sort_keys=True, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    return run_dir


def _metric(
    stage: str,
    started_ns: int,
    *,
    item_count: int = 0,
    issue_count: int = 0,
) -> CPScaleStageMetric:
    return CPScaleStageMetric(
        stage=stage,
        duration_ms=round((perf_counter_ns() - started_ns) / 1_000_000, 3),
        item_count=item_count,
        issue_count=issue_count,
    )


def _structural_manifest(topology: TopologyPlan) -> DeploymentManifest:
    interfaces_by_device: dict[str, set[str]] = {
        item.id: set() for item in topology.devices
    }
    for link in topology.links:
        interfaces_by_device.setdefault(link.device_a_id, set()).add(link.port_a)
        interfaces_by_device.setdefault(link.device_b_id, set()).add(link.port_b)
    inventory = [
        RuntimeConfigurationTarget(
            device_name=item.name,
            model=item.model,
            interfaces=sorted(interfaces_by_device.get(item.id, set())),
        )
        for item in topology.devices
    ]
    link_bindings = [
        DeploymentLinkBinding(
            semantic_link_id=link.id,
            endpoint_a=DeploymentLinkEndpoint(
                semantic_device_id=link.device_a_id,
                interface=link.port_a,
                orientation=(
                    SerialEndpointOrientation.DCE
                    if link.cable == "serial" else SerialEndpointOrientation.UNRESOLVED
                ),
            ),
            endpoint_b=DeploymentLinkEndpoint(
                semantic_device_id=link.device_b_id,
                interface=link.port_b,
                orientation=(
                    SerialEndpointOrientation.DTE
                    if link.cable == "serial" else SerialEndpointOrientation.UNRESOLVED
                ),
            ),
        )
        for link in topology.links
    ]
    return build_deployment_manifest(
        topology,
        inventory,
        fingerprint=EnvironmentFingerprint(
            backend="packet_tracer",
            backend_version=PT_2911_HWIC2T_SERIAL_CLOCK.backend_version,
            bridge_transport="none",
            runtime_mode="offline_structural_only",
        ),
        deployment_id="cp-scale-offline-structural",
        link_bindings=link_bindings,
        created_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )


def cp_scale_control_plane_intent(
    enterprise: EnterprisePlan,
    topology: TopologyPlan,
    configuration=None,
) -> ControlPlaneIntent:
    vlan_ids_by_site: dict[str, set[int]] = {}
    if configuration is not None:
        for action in configuration.actions_of_type(ConfigurationActionType.CREATE_VLAN):
            vlan_ids_by_site.setdefault(action.site_id, set()).add(action.vlan_id)
    else:
        for site in enterprise.sites:
            vlan_ids_by_site[site.site_id] = {
                segment.vlan_id for segment in site.segments
                if segment.vlan_id is not None
            }

    layer_order = {"distribution": 0, "core": 1, "access": 2}
    stp_domains: list[StpIntent] = []
    for site in sorted(enterprise.sites, key=lambda item: item.site_id):
        switches = sorted(
            (
                item for item in topology.devices
                if item.site_id == site.site_id and item.category == "switch"
            ),
            key=lambda item: (layer_order.get(item.network_layer, 9), item.id),
        )
        vlan_ids = sorted(vlan_ids_by_site.get(site.site_id, set()))
        primary = {vlan_id: switches[0].id for vlan_id in vlan_ids}
        secondary = (
            {vlan_id: switches[1].id for vlan_id in vlan_ids}
            if len(switches) > 1 else {}
        )
        stp_domains.append(StpIntent(
            id=f"stp/{site.site_id}/pvst",
            site_id=site.site_id,
            mode=StpMode.PVST,
            vlan_ids=vlan_ids,
            root_primary_by_vlan=primary,
            root_secondary_by_vlan=secondary,
        ))

    routers = sorted(
        (item.id for item in topology.devices if item.category == "router"),
    )
    serial_links = sorted(
        item.id for item in topology.links if item.cable == "serial"
    )
    return ControlPlaneIntent(
        id="control-plane/cp-scale",
        stp_domains=stp_domains,
        routing=DynamicRoutingIntent(
            id="routing/cp-scale/ripv2",
            protocol=DynamicRoutingProtocol.RIPV2,
            device_ids=routers,
            transit_link_ids=serial_links,
        ),
    )


def cp_scale_voice_intent(topology: TopologyPlan) -> VoiceIntent:
    routers = {
        item.site_id: item.id
        for item in topology.devices
        if item.category == "router"
    }
    return VoiceIntent(
        id="voice/cp-scale",
        call_control_device_ids=dict(sorted(routers.items())),
        extension_ranges={
            "large-branch": ExtensionRange(start=3001, end=3999),
            "multilayer-branch": ExtensionRange(start=4001, end=4999),
            "small-branch": ExtensionRange(start=5001, end=5999),
        },
        intersite_calling=True,
    )
