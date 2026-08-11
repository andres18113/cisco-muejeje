"""E9.5 cross-milestone regression for the representative enterprise chain.

These tests intentionally stop at compilation and pure reconciliation.  They
prove deterministic contracts and identity propagation without claiming that
Packet Tracer applied or behaviorally verified an UNKNOWN capability.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
import json

import pytest

from src.packet_tracer_mcp.application.use_cases.compile_configuration import (
    compile_enterprise_configuration,
)
from src.packet_tracer_mcp.application.use_cases.compile_control_plane import (
    compile_enterprise_control_plane,
)
from src.packet_tracer_mcp.application.use_cases.compile_enterprise import (
    compile_enterprise_topology,
)
from src.packet_tracer_mcp.application.use_cases.compile_security import (
    compile_enterprise_security,
)
from src.packet_tracer_mcp.application.use_cases.compile_services import (
    compile_enterprise_services,
)
from src.packet_tracer_mcp.application.use_cases.compile_voice import (
    compile_enterprise_voice,
)
from src.packet_tracer_mcp.domain.enterprise.models.compilation import (
    EnterpriseCompileResult,
    LayoutProfile,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationCompileResult,
    ConfigureSubinterface,
    CreateVlan,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ControlPlaneCompileResult,
    ControlPlaneIntent,
    StpIntent,
    StpMode,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    EnvironmentFingerprint,
    IdentityMethod,
    build_deployment_manifest,
)
from src.packet_tracer_mcp.domain.enterprise.models.enterprise_plan import EnterprisePlan
from src.packet_tracer_mcp.domain.enterprise.models.failure_domain import (
    FailurePath,
    FailureScenario,
    FailureScenarioScope,
    IndependenceStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.hardware import (
    HardwarePlan,
    ResiliencyLevel,
)
from src.packet_tracer_mcp.domain.enterprise.models.hierarchy import (
    BuildingIntent,
    EndpointGroup,
    FloorIntent,
    ZoneIntent,
)
from src.packet_tracer_mcp.domain.enterprise.models.intent import (
    EnterpriseIntent,
    SiteIntent,
    SiteType,
)
from src.packet_tracer_mcp.domain.enterprise.models.ipam_reconciliation import (
    AddressPurpose,
    AddressReconcileStatus,
    ExistingAddressBinding,
    InfrastructureAddressDemand,
)
from src.packet_tracer_mcp.domain.enterprise.models.requirements import (
    EndpointRequirement,
    ServiceRequirement,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.models.security_plan import (
    SecurityCompileResult,
    SecurityDecision,
    SecurityIntent,
    SecurityPolicyIntent,
)
from src.packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceCompileResult,
    ServiceType,
    TftpFileRequirement,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import (
    VoiceCompileResult,
    VoiceIntent,
)
from src.packet_tracer_mcp.domain.enterprise.services.address_reconciler import (
    AddressReconciler,
)
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import (
    EnterpriseDesigner,
)
from src.packet_tracer_mcp.domain.enterprise.services.failure_domain_analyzer import (
    FailureDomainAnalyzer,
    build_failure_domain_catalog,
)
from src.packet_tracer_mcp.domain.enterprise.services.hardware_planner import (
    HardwarePlanner,
    HardwarePlanningPolicy,
    HierarchyPolicy,
)
from src.packet_tracer_mcp.domain.enterprise.services.topology_identity import (
    compute_topology_hashes,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_topology import (
    PacketTracerTopologyCatalogAdapter,
)


@dataclass(frozen=True)
class _ReferenceChain:
    enterprise: EnterprisePlan
    hardware: HardwarePlan
    e4: EnterpriseCompileResult
    e5: ConfigurationCompileResult
    e6: ServiceCompileResult
    e7: VoiceCompileResult
    e8: SecurityCompileResult
    e9: ControlPlaneCompileResult


def _requirement(
    role: DeviceRole,
    count: int,
    *,
    poe: bool = False,
) -> EndpointRequirement:
    return EndpointRequirement(role=role, count=count, requires_poe=poe)


def _reference_intent() -> EnterpriseIntent:
    requirements = [
        _requirement(DeviceRole.USER_PC, 30),
        _requirement(DeviceRole.IP_PHONE, 30, poe=True),
        _requirement(DeviceRole.IP_CAMERA, 8, poe=True),
        _requirement(DeviceRole.PRINTER, 4),
        _requirement(DeviceRole.ACCESS_POINT, 3, poe=True),
        _requirement(DeviceRole.SERVER, 1),
    ]
    return EnterpriseIntent(
        name="E95 Reference",
        address_space="10.0.0.0/8",
        internet_required=True,
        default_growth_percent=0,
        sites=[SiteIntent(
            name="Matriz",
            type=SiteType.HQ,
            buildings=[BuildingIntent(
                name="A",
                floors=[FloorIntent(
                    name="1",
                    zones=[ZoneIntent(
                        name="Ventas",
                        endpoint_groups=[EndpointGroup(
                            name="Ventas",
                            requirements=requirements,
                        )],
                    )],
                )],
            )],
            services=[ServiceRequirement(
                name="intranet",
                service_type=ServiceType.HTTP,
                http_content="E95_REFERENCE_OK",
            ), ServiceRequirement(
                name="voice-bootstrap",
                service_type=ServiceType.TFTP,
                tftp_files=[TftpFileRequirement(
                    filename="SEPDEFAULT.cnf.xml",
                    content="E95_VOICE_BOOTSTRAP",
                )],
            )],
        )],
    )


def _compile_reference_chain() -> _ReferenceChain:
    designed = EnterpriseDesigner().design(_reference_intent())
    assert designed.validation.is_valid, designed.validation.error_messages()
    assert designed.plan is not None
    enterprise = designed.plan

    capability_catalog = EnterpriseCapabilityAdapter()
    switch = next(
        item for item in capability_catalog.hardware_candidates("switch")
        if item.model == "2960-24TT"
    )
    router = next(
        item for item in capability_catalog.hardware_candidates("router")
        if item.model == "2911"
    )
    # Force a complete physical chain.  A collapsed site has no core-to-edge
    # hop, so it is not a representative E4-E9 integration fixture.
    hardware = HardwarePlanner().plan(
        enterprise,
        [switch],
        [router],
        HardwarePlanningPolicy(
            resiliency=ResiliencyLevel.BASIC,
            hierarchy=HierarchyPolicy(
                small_site_max_access_switches=0,
                collapsed_core_max_access_switches=0,
            ),
        ),
    )
    topology_catalog = PacketTracerTopologyCatalogAdapter()
    e4 = compile_enterprise_topology(
        enterprise,
        hardware,
        topology_catalog.compilation_profile(),
        topology_catalog.cable_for,
    )
    assert e4.is_valid and e4.plan is not None

    e5 = compile_enterprise_configuration(enterprise, e4.plan)
    assert e5.is_valid and e5.plan is not None

    e6 = compile_enterprise_services(enterprise, e4.plan, e5.plan)
    assert e6.is_valid and e6.plan is not None and e6.plan.services

    edge = next(
        item for item in e4.plan.devices
        if item.enterprise_role == DeviceRole.EDGE_ROUTER.value
    )
    voice_bootstrap = next(
        item for item in e6.plan.services
        if item.service_type is ServiceType.TFTP
    )
    e7 = compile_enterprise_voice(
        VoiceIntent(
            id="voice/reference",
            call_control_device_ids={"matriz": edge.id},
            service_dependency_ids=[voice_bootstrap.id],
        ),
        enterprise,
        e4.plan,
        e5.plan,
        service_plan=e6.plan,
    )
    assert e7.is_valid and e7.plan is not None

    data_segment = next(
        item.name for item in enterprise.sites[0].segments
        if item.role.value == "data"
    )
    voice_segment = next(
        item.name for item in enterprise.sites[0].segments
        if item.role.value == "voice"
    )
    service = next(
        item for item in e6.plan.services
        if item.service_type is ServiceType.HTTP
    )
    call_control = e7.plan.call_controls[0]
    e8 = compile_enterprise_security(
        SecurityIntent(
            id="security/reference",
            policies=[
                SecurityPolicyIntent(
                    id="allow-data-http",
                    source_segment_id=data_segment,
                    destination_service_id=service.id,
                    decision=SecurityDecision.ALLOW,
                    priority=10,
                ),
                SecurityPolicyIntent(
                    id="allow-voice-signaling",
                    source_segment_id=voice_segment,
                    destination_call_control_id=call_control.id,
                    decision=SecurityDecision.ALLOW,
                    priority=20,
                ),
            ],
        ),
        e4.plan,
        e5.plan,
        service_plan=e6.plan,
        voice_plan=e7.plan,
    )
    assert e8.is_valid and e8.plan is not None

    vlan_ids = sorted({
        action.vlan_id for action in e5.plan.actions
        if isinstance(action, CreateVlan)
    })
    e9 = compile_enterprise_control_plane(
        ControlPlaneIntent(
            id="control-plane/reference",
            stp=StpIntent(
                id="stp/reference",
                site_id="matriz",
                mode=StpMode.PVST,
                vlan_ids=vlan_ids,
            ),
            security_policy_ids=["allow-data-http"],
        ),
        e4.plan,
        e5.plan,
        security_plan=e8.plan,
    )
    assert e9.is_valid and e9.plan is not None
    return _ReferenceChain(enterprise, hardware, e4, e5, e6, e7, e8, e9)


@pytest.fixture(scope="module")
def reference_chain() -> _ReferenceChain:
    return _compile_reference_chain()


def _deterministic_signature(chain: _ReferenceChain) -> tuple[str, ...]:
    return (
        chain.e4.physical_topology_hash,
        chain.e4.layout_hash,
        chain.e4.artifact_hash,
        chain.e5.semantic_hash,
        chain.e6.semantic_hash,
        chain.e7.semantic_hash,
        chain.e8.semantic_hash,
        chain.e9.semantic_hash,
    )


def test_reference_e4_to_e9_chain_is_deterministic_ten_of_ten(
    reference_chain: _ReferenceChain,
) -> None:
    signatures = [_deterministic_signature(reference_chain)]
    signatures.extend(
        _deterministic_signature(_compile_reference_chain()) for _ in range(9)
    )

    assert len(set(signatures)) == 1
    assert all(len(value) == 64 for value in signatures[0])


def test_reference_chain_binds_physical_identity_and_keeps_summaries_compact(
    reference_chain: _ReferenceChain,
) -> None:
    topology = reference_chain.e4.plan
    configuration = reference_chain.e5.plan
    services = reference_chain.e6.plan
    voice = reference_chain.e7.plan
    security = reference_chain.e8.plan
    control_plane = reference_chain.e9.plan
    assert all(
        item is not None
        for item in (topology, configuration, services, voice, security, control_plane)
    )
    physical_hash = topology.physical_topology_hash

    assert topology.hash_schema_version == "2"
    assert configuration.source_topology_hash == physical_hash
    assert services.source_topology_hash == physical_hash
    assert voice.source_topology_hash == physical_hash
    assert security.source_topology_hash == physical_hash
    assert control_plane.source_topology_hash == physical_hash
    assert services.source_configuration_hash == configuration.semantic_hash
    assert voice.source_configuration_hash == configuration.semantic_hash
    assert voice.source_service_hash == services.semantic_hash
    assert security.source_service_hash == services.semantic_hash
    assert security.source_voice_hash == voice.semantic_hash
    assert control_plane.source_security_hash == security.semantic_hash

    assert reference_chain.e4.summary.devices == len(topology.devices)
    assert reference_chain.e5.summary.action_count == len(configuration.actions)
    assert reference_chain.e6.summary.action_count == len(services.actions)
    assert reference_chain.e7.summary.action_count == len(voice.actions)
    assert reference_chain.e8.summary.action_count == len(security.actions)
    assert reference_chain.e9.summary.action_count == len(control_plane.actions)

    summaries = [
        reference_chain.e4.compact_summary(),
        reference_chain.e5.compact_summary(),
        reference_chain.e6.compact_summary(),
        reference_chain.e7.compact_summary(),
        reference_chain.e8.compact_summary(),
        reference_chain.e9.compact_summary(),
    ]
    forbidden_payloads = {
        "plan", "actions", "services", "assignments", "bindings",
        "failure_domain_catalog",
    }
    for summary in summaries:
        assert forbidden_payloads.isdisjoint(summary)
        if "verification_expectations" in summary:
            assert isinstance(summary["verification_expectations"], int)
        json.dumps(summary)

    # Catalog/runtime evidence is deliberately absent from this offline chain.
    # Compilation must retain that uncertainty instead of promoting support.
    assert "VOICE_CAPABILITY_UNKNOWN" in {
        item.code.value for item in reference_chain.e7.issues
    }
    assert "SECURITY_CAPABILITY_UNKNOWN" in {
        item.code.value for item in reference_chain.e8.issues
    }
    assert "CONTROL_PLANE_CAPABILITY_UNKNOWN" in {
        item.code.value for item in reference_chain.e9.issues
    }


def _runtime_inventory(reference_chain: _ReferenceChain) -> list[RuntimeConfigurationTarget]:
    topology = reference_chain.e4.plan
    assert topology is not None
    ports: dict[str, set[str]] = defaultdict(set)
    for link in topology.links:
        ports[link.device_a_id].add(link.port_a)
        ports[link.device_b_id].add(link.port_b)
    return [
        RuntimeConfigurationTarget(
            device_name=device.name,
            model=device.model,
            interfaces=sorted(ports[device.id]),
            runtime_identifier=f"runtime/{device.id}",
            runtime_identifier_stable=True,
            runtime_fingerprint=f"fingerprint/{device.id}",
        )
        for device in topology.devices
    ]


def test_layout_only_mutation_preserves_physical_manifest_bindings(
    reference_chain: _ReferenceChain,
) -> None:
    topology = reference_chain.e4.plan
    assert topology is not None
    original = compute_topology_hashes(
        topology,
        layout_regions=reference_chain.e4.layout_regions,
        layout_profile=LayoutProfile(),
    )
    moved = deepcopy(topology)
    moved.devices[0].x += 700
    moved.devices[-1].y += 400
    transformed = compute_topology_hashes(
        moved,
        layout_regions=reference_chain.e4.layout_regions,
        layout_profile=LayoutProfile(),
    )

    assert original.physical_topology_hash == transformed.physical_topology_hash
    assert original.layout_hash != transformed.layout_hash
    assert original.artifact_hash != transformed.artifact_hash

    inventory = _runtime_inventory(reference_chain)
    fingerprint = EnvironmentFingerprint(
        backend="packet_tracer",
        backend_version="9.0.1.0858",
        bridge_transport="file",
        extension_version="5",
        capability_snapshot_version="e9.5",
        runtime_mode="offline-regression",
    )
    manifest = build_deployment_manifest(
        topology,
        inventory,
        fingerprint=fingerprint,
        deployment_id="deployment/e95-reference",
    )
    reordered = build_deployment_manifest(
        topology,
        list(reversed(inventory)),
        fingerprint=fingerprint,
        deployment_id="deployment/e95-reference",
    )

    assert manifest.physical_topology_hash == original.physical_topology_hash
    assert manifest.semantic_hash == reordered.semantic_hash
    assert {item.semantic_device_id for item in manifest.bindings} == {
        item.id for item in topology.devices
    }
    assert all(
        item.identity_method is IdentityMethod.RUNTIME_ID
        for item in manifest.bindings
    )
    assert manifest.resolve_target(topology.devices[0].id, inventory).device_name == (
        topology.devices[0].name
    )
    compact = manifest.compact_summary()
    assert compact["binding_count"] == len(topology.devices)
    assert "bindings" not in compact


def test_reference_address_reconcile_preserves_existing_management_gateway(
    reference_chain: _ReferenceChain,
) -> None:
    topology = reference_chain.e4.plan
    configuration = reference_chain.e5.plan
    assert topology is not None and configuration is not None
    edge = next(
        item for item in topology.devices
        if item.enterprise_role == DeviceRole.EDGE_ROUTER.value
    )
    target_roles = {"management"}
    segment_names = {
        item.role.value: item.name
        for item in reference_chain.enterprise.sites[0].segments
        if item.role.value in target_roles
    }
    allocations = {
        item.segment_id: item
        for item in reference_chain.enterprise.addressing.allocations
    }
    gateway_actions = {
        action.segment_id: action
        for action in configuration.actions
        if isinstance(action, ConfigureSubinterface)
        and action.device_id == edge.id
        and action.segment_id in set(segment_names.values())
    }
    assert set(gateway_actions) == set(segment_names.values())

    demands: list[InfrastructureAddressDemand] = []
    existing: list[ExistingAddressBinding] = []
    for segment_id, action in sorted(gateway_actions.items()):
        allocation = allocations[segment_id]
        demand_id = f"gateway/{segment_id}"
        demands.append(InfrastructureAddressDemand(
            id=demand_id,
            purpose=AddressPurpose.MANAGEMENT,
            owner_id=edge.id,
            network=f"{allocation.network}/{allocation.prefix}",
            segment_id=segment_id,
            interface_prefix=action.prefix,
        ))
        existing.append(ExistingAddressBinding(
            id=f"existing/{segment_id}",
            demand_id=demand_id,
            purpose=AddressPurpose.MANAGEMENT,
            owner_id=edge.id,
            ipv4=action.ipv4,
            prefix=action.prefix,
            segment_id=segment_id,
        ))
    demands.append(InfrastructureAddressDemand(
        id="loopback/edge",
        purpose=AddressPurpose.LOOPBACK,
        owner_id=edge.id,
        network="10.255.255.0/24",
        interface_prefix=32,
    ))

    reconciler = AddressReconciler()
    first = reconciler.reconcile("10.0.0.0/8", demands, existing)
    reordered = reconciler.reconcile(
        "10.0.0.0/8", list(reversed(demands)), list(reversed(existing)),
    )

    assert first.status is AddressReconcileStatus.ALLOCATED_WITHOUT_RENUMBER
    assert first.plan is not None and reordered.plan is not None
    assert first.plan.semantic_hash == reordered.plan.semantic_hash
    for binding in existing:
        preserved = first.plan.binding_for_demand(binding.demand_id)
        assert preserved is not None
        assert preserved.preserved
        assert preserved.ipv4 == binding.ipv4
        assert preserved.source_binding_id == binding.id
    assert not first.plan.binding_for_demand("loopback/edge").preserved
    assert "plan" not in first.compact_summary()


def _link_between(reference_chain: _ReferenceChain, left: str, right: str):
    topology = reference_chain.e4.plan
    assert topology is not None
    return next(
        item for item in topology.links
        if {item.device_a_id, item.device_b_id} == {left, right}
    )


def test_reference_failure_domains_are_deterministic_and_paths_independent(
    reference_chain: _ReferenceChain,
) -> None:
    topology = reference_chain.e4.plan
    assert topology is not None
    access = sorted(
        (item for item in topology.devices if item.network_layer == "access"),
        key=lambda item: item.id,
    )[0]
    distributions = sorted(
        (item for item in topology.devices if item.network_layer == "distribution"),
        key=lambda item: item.id,
    )
    core = next(item for item in topology.devices if item.network_layer == "core")
    primary_links = [
        _link_between(reference_chain, access.id, distributions[0].id),
        _link_between(reference_chain, distributions[0].id, core.id),
    ]
    surviving_links = [
        _link_between(reference_chain, access.id, distributions[1].id),
        _link_between(reference_chain, distributions[1].id, core.id),
    ]

    hashes = {
        build_failure_domain_catalog(topology).semantic_hash for _ in range(10)
    }
    reordered_topology = deepcopy(topology)
    reordered_topology.devices.reverse()
    reordered_topology.links.reverse()
    catalog = build_failure_domain_catalog(topology)
    reordered_catalog = build_failure_domain_catalog(reordered_topology)

    assert len(hashes) == 1
    assert catalog.semantic_hash == reordered_catalog.semantic_hash
    assert catalog.source_topology_hash == topology.physical_topology_hash

    result = FailureDomainAnalyzer().analyze(
        FailureScenario(
            id="failure/reference-access-uplink",
            scope=FailureScenarioScope.LINK_FAULT,
            primary_path=FailurePath(
                id="path/primary",
                device_ids=[access.id, distributions[0].id, core.id],
                link_ids=[item.id for item in primary_links],
                endpoint_device_ids=[access.id, core.id],
            ),
            surviving_path=FailurePath(
                id="path/surviving",
                device_ids=[access.id, distributions[1].id, core.id],
                link_ids=[item.id for item in surviving_links],
                endpoint_device_ids=[access.id, core.id],
            ),
        ),
        catalog,
    )

    assert result.status is IndependenceStatus.INDEPENDENT
    assert result.blocking_domain_ids == []
    assert result.ignored_common_endpoint_device_ids == sorted([access.id, core.id])
    assert result.compact_summary() == FailureDomainAnalyzer().analyze(
        FailureScenario(
            id="failure/reference-access-uplink",
            scope=FailureScenarioScope.LINK_FAULT,
            primary_path=FailurePath(
                id="path/primary",
                device_ids=[access.id, distributions[0].id, core.id],
                link_ids=[item.id for item in primary_links],
                endpoint_device_ids=[access.id, core.id],
            ),
            surviving_path=FailurePath(
                id="path/surviving",
                device_ids=[access.id, distributions[1].id, core.id],
                link_ids=[item.id for item in surviving_links],
                endpoint_device_ids=[access.id, core.id],
            ),
        ),
        reordered_catalog,
    ).compact_summary()
