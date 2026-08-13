"""E4: EnterprisePlan + HardwarePlan -> TopologyPlan físico concreto."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from ...models.plans import DevicePlan, LinkPlan, ModulePlan, TopologyPlan
from ...rules.enterprise_compilation_rules import validate_concrete_topology
from ....shared.enums import DeviceRole as TopologyDeviceRole
from ..models.compilation import (
    CompilationIssue,
    CompilationIssueCode,
    CompilationIssueSeverity,
    ConcreteLinkRole,
    EnterpriseCompileResult,
    EnterpriseCompileSummary,
    LayoutProfile,
    LayoutRegion,
    PhysicalCompilationProfile,
    PhysicalModelProfile,
)
from ..models.enterprise_plan import EnterprisePlan
from ..models.hardware import (
    HardwareLinkRequirement,
    HardwarePlan,
    HardwarePlanStatus,
    LinkRole,
    PlannedNetworkDevice,
    PortClass,
    PortDescriptor,
)
from ..models.link_performance import LinkMedia
from ..models.roles import DeviceRole
from .endpoint_expander import EndpointGroupExpander, ExpandedEndpoint, iter_zone_contexts
from .layout_planner import LayoutPlanner
from .naming import DeterministicNamingService
from .physical_ports import is_logical_interface, natural_interface_key, physical_ports
from .topology_identity import stamp_topology_hashes


CableResolver = Callable[[str, str], str]


_SERVER_ROLES = {
    DeviceRole.SERVER,
    DeviceRole.WEB_SERVER,
    DeviceRole.DNS_SERVER,
    DeviceRole.DHCP_SERVER,
    DeviceRole.NTP_SERVER,
    DeviceRole.TFTP_SERVER,
    DeviceRole.NVR,
}


@dataclass
class _CompiledEndpoint:
    expanded: ExpandedEndpoint
    device: DevicePlan
    profile: PhysicalModelProfile


class _PortAllocator:
    def __init__(
        self,
        inventories: dict[str, list[PortDescriptor]],
        issues: list[CompilationIssue],
    ) -> None:
        self._inventories = {
            device_id: physical_ports(ports) for device_id, ports in inventories.items()
        }
        self._issues = issues
        self._used: dict[tuple[str, str], str] = {}

    def allocate(
        self,
        device_id: str,
        reservation: str,
        required_class: PortClass,
        explicit_port: str | None = None,
        *,
        allow_class_fallback: bool,
    ) -> str | None:
        inventory = self._inventories.get(device_id, [])
        if explicit_port:
            return self._reserve_explicit(device_id, explicit_port, reservation, inventory)
        free = [port for port in inventory if (device_id, port.name) not in self._used]
        preferred = [port for port in free if required_class in port.classes]
        candidates = preferred
        if not candidates and allow_class_fallback and free:
            candidates = free
            self._issues.append(_warning(
                CompilationIssueCode.PORT_CLASS_FALLBACK,
                f"{device_id}: no hay puerto libre de clase {required_class.value}; "
                f"se usará inventario físico sin afirmar esa capability.",
                device_id,
                required_class=required_class.value,
            ))
        if not candidates:
            self._issues.append(_error(
                CompilationIssueCode.INSUFFICIENT_PHYSICAL_PORT_CAPACITY,
                f"{device_id}: no queda un puerto físico libre para {required_class.value}.",
                device_id,
                required_class=required_class.value,
            ))
            return None
        port = sorted(candidates, key=lambda item: natural_interface_key(item.name))[0]
        self._used[(device_id, port.name)] = reservation
        return port.name

    def release(self, device_id: str, port: str, reservation: str) -> None:
        if self._used.get((device_id, port)) == reservation:
            del self._used[(device_id, port)]

    def _reserve_explicit(
        self,
        device_id: str,
        port_name: str,
        reservation: str,
        inventory: list[PortDescriptor],
    ) -> str | None:
        if is_logical_interface(port_name):
            self._issues.append(_error(
                CompilationIssueCode.LOGICAL_PORT_SELECTED,
                f"{device_id}: {port_name} es una interfaz lógica.", device_id,
            ))
            return None
        if port_name not in {port.name for port in inventory}:
            self._issues.append(_error(
                CompilationIssueCode.PHYSICAL_PORT_MISSING,
                f"{device_id}: {port_name} no existe en el inventario físico.", device_id,
            ))
            return None
        key = (device_id, port_name)
        if key in self._used:
            self._issues.append(_error(
                CompilationIssueCode.PORT_ALREADY_ASSIGNED,
                f"{device_id}:{port_name} ya fue reservado por {self._used[key]}.", device_id,
            ))
            return None
        self._used[key] = reservation
        return port_name


class EnterpriseCompiler:
    """Compilador puro: no importa bridge, MCP, TerminalLine ni APIs de Packet Tracer."""

    def compile(
        self,
        enterprise: EnterprisePlan,
        hardware: HardwarePlan,
        physical_profile: PhysicalCompilationProfile,
        layout_profile: LayoutProfile = LayoutProfile(),
        cable_resolver: CableResolver | None = None,
    ) -> EnterpriseCompileResult:
        issues: list[CompilationIssue] = []
        naming = DeterministicNamingService(
            physical_profile.max_device_name_length,
            physical_profile.device_name_prefix,
        )
        topology = TopologyPlan(
            id=f"compiled/{enterprise.id}",
            name=enterprise.name,
            metadata={
                "enterprise_plan_id": enterprise.id,
                "compiler_milestone": "E4",
                "configuration_deferred_to": "E5",
            },
        )
        if hardware.status is HardwarePlanStatus.UNRESOLVED:
            cause = (
                "unsupported"
                if hardware.unsupported_requirements
                else "insufficient_evidence"
            )
            reasons = hardware.unsupported_requirements or hardware.warnings
            issues.append(_error(
                CompilationIssueCode.HARDWARE_PLAN_UNRESOLVED,
                "HardwarePlan no está resuelto; E4 no puede inventar la topología física. "
                + (" ".join(reasons) if reasons else "No se seleccionó hardware físico."),
                resolution_cause=cause,
                warning_count=len(hardware.warnings),
                unsupported_count=len(hardware.unsupported_requirements),
            ))
            return self._result(topology, enterprise, issues, [], valid=False)
        enterprise_sites = {site.site_id: site for site in enterprise.sites}
        hardware_sites = {site.site_id: site for site in hardware.site_hardware}
        for site_id in sorted(enterprise_sites):
            if site_id not in hardware_sites:
                issues.append(_error(
                    CompilationIssueCode.HARDWARE_SITE_MISSING,
                    f"No existe SiteHardwarePlan para {site_id}.", site_id,
                ))
        for site_id in sorted(hardware_sites):
            if site_id not in enterprise_sites:
                issues.append(_error(
                    CompilationIssueCode.HIERARCHY_REFERENCE_MISSING,
                    f"El hardware del sitio {site_id} no existe en EnterprisePlan.", site_id,
                ))

        network_devices, hardware_by_id, inventories = self._compile_network_devices(
            hardware, enterprise_sites, physical_profile, naming, issues,
        )
        topology.devices.extend(network_devices.values())
        expanded = EndpointGroupExpander().expand(enterprise, naming)
        compiled_endpoints = self._compile_endpoints(expanded, physical_profile, issues)
        topology.devices.extend(item.device for item in compiled_endpoints.values())

        name_by_id = {device.id: device.name for device in topology.devices}
        topology.modules.extend(self._compile_modules(hardware_by_id, name_by_id, issues))
        endpoint_inventories = {
            endpoint.device.id: [PortDescriptor(name=port) for port in endpoint.profile.physical_ports]
            for endpoint in compiled_endpoints.values()
        }
        all_inventories = {**inventories, **endpoint_inventories}
        allocator = _PortAllocator(inventories, issues)

        infrastructure_links = self._compile_infrastructure_links(
            hardware, hardware_by_id, network_devices, allocator,
            physical_profile, cable_resolver, issues,
        )
        topology.links.extend(infrastructure_links)
        endpoint_links = self._compile_endpoint_links(
            hardware, compiled_endpoints, network_devices, allocator,
            physical_profile, cable_resolver, issues,
        )
        topology.links.extend(endpoint_links)
        topology.devices = sorted(topology.devices, key=lambda item: item.id)
        topology.modules = sorted(topology.modules, key=lambda item: (item.device, item.slot, item.module))
        topology.links = sorted(
            topology.links,
            key=lambda item: (
                item.link_role, item.device_a_id, natural_interface_key(item.port_a),
                item.device_b_id, natural_interface_key(item.port_b), item.id,
            ),
        )

        if any(issue.severity is CompilationIssueSeverity.ERROR for issue in issues):
            return self._result(topology, enterprise, issues, [], valid=False)

        topology, regions = LayoutPlanner().plan(topology, layout_profile)
        issues.extend(validate_concrete_topology(
            topology,
            {
                device_id: {port.name for port in physical_ports(ports)}
                for device_id, ports in all_inventories.items()
            },
        ))
        issues.extend(self._capability_warnings(hardware, compiled_endpoints))
        issues.append(_warning(
            CompilationIssueCode.LAYOUT_COORDINATE_READBACK_PARTIAL,
            "Packet Tracer relee coordenadas transformadas que no equivalen exactamente a los valores "
            "enviados a moveToLocation; la aplicación está verificada y la igualdad exacta sigue parcial.",
        ))
        issues = _deduplicate_issues(issues)
        if any(issue.severity is CompilationIssueSeverity.ERROR for issue in issues):
            return self._result(topology, enterprise, issues, regions, valid=False)

        topology.warnings = [issue.message for issue in issues if issue.severity is CompilationIssueSeverity.WARNING]
        topology.errors = []
        stamp_topology_hashes(
            topology,
            layout_regions=regions,
            layout_profile=layout_profile,
        )
        return self._result(topology, enterprise, issues, regions, valid=True)

    @staticmethod
    def _compile_network_devices(
        hardware: HardwarePlan,
        enterprise_sites: dict[str, object],
        physical_profile: PhysicalCompilationProfile,
        naming: DeterministicNamingService,
        issues: list[CompilationIssue],
    ) -> tuple[dict[str, DevicePlan], dict[str, PlannedNetworkDevice], dict[str, list[PortDescriptor]]]:
        compiled: dict[str, DevicePlan] = {}
        planned: dict[str, PlannedNetworkDevice] = {}
        inventories: dict[str, list[PortDescriptor]] = {}
        zone_by_switch: dict[str, str] = {
            switch_id: block.zone_id
            for site in hardware.site_hardware
            for block in site.access_blocks
            for switch_id in block.switches
        }
        counters: dict[tuple[str, DeviceRole], int] = defaultdict(int)
        for site in sorted(hardware.site_hardware, key=lambda item: item.site_id):
            for device in sorted(site.devices, key=lambda item: item.id):
                if device.id in planned:
                    issues.append(_error(
                        CompilationIssueCode.DUPLICATE_DEVICE_ID,
                        f"HardwarePlan contiene el ID duplicado {device.id!r}.", device.id,
                    ))
                    continue
                model = device.selected_model or device.provisional_model
                if not model:
                    issues.append(_error(
                        CompilationIssueCode.MODEL_SELECTION_UNRESOLVED,
                        f"{device.id}: HardwarePlan no resolvió un modelo físico.", device.id,
                    ))
                    continue
                model_profile = physical_profile.model_by_name(model)
                if model_profile is None:
                    issues.append(_error(
                        CompilationIssueCode.MODEL_SELECTION_UNRESOLVED,
                        f"{device.id}: el adapter no proporcionó metadata física para {model}.", device.id,
                    ))
                    continue
                if device.provisional_model and not device.selected_model:
                    issues.append(_warning(
                        CompilationIssueCode.MODEL_SELECTION_PROVISIONAL,
                        f"{device.id}: se conserva el modelo provisional {model}; E4 no promueve capabilities.",
                        device.id,
                    ))
                counters[(site.site_id, device.role)] += 1
                index = counters[(site.site_id, device.role)]
                zone_id = zone_by_switch.get(device.id, "")
                site_plan = enterprise_sites.get(site.site_id)
                building_id, floor_id = _hierarchy_for_zone(site_plan, zone_id)
                metadata = {
                    "selection_status": device.selection_status.value,
                    "parent_group": device.parent_group,
                    "redundancy_group": device.redundancy_group or "",
                    "port_capacity": str(device.port_capacity),
                    "poe_capacity": "unknown" if device.poe_capacity is None else str(device.poe_capacity),
                }
                if device.additional_roles:
                    metadata["additional_roles"] = ",".join(
                        role.value for role in sorted(
                            device.additional_roles, key=lambda item: item.value,
                        )
                    )
                compiled_device = DevicePlan(
                    id=device.id,
                    name=naming.network_name(site.site_id, device.role, index, zone_id),
                    model=model,
                    category=model_profile.category,
                    role=_topology_role(device.role),
                    enterprise_role=device.role.value,
                    site_id=site.site_id,
                    building_id=building_id,
                    floor_id=floor_id,
                    zone_id=zone_id,
                    network_layer=device.network_layer.value,
                    metadata=metadata,
                )
                compiled[device.id] = compiled_device
                planned[device.id] = device
                existing_ports = {port.name for port in device.port_descriptors}
                module_ports = [
                    PortDescriptor(
                        name=port,
                        classes=list(dict.fromkeys([
                            PortClass.MODULE_PROVIDED,
                            PortClass.WAN,
                            *module.provided_port_classes,
                        ])),
                        source="module_plan",
                        slot=module.slot or "",
                        module=module.module,
                    )
                    for module in device.module_plan
                    for port in module.provided_ports
                    if port not in existing_ports
                ]
                inventories[device.id] = list(device.port_descriptors) + module_ports
        return compiled, planned, inventories

    @staticmethod
    def _compile_endpoints(
        expanded: list[ExpandedEndpoint],
        physical_profile: PhysicalCompilationProfile,
        issues: list[CompilationIssue],
    ) -> dict[str, _CompiledEndpoint]:
        compiled: dict[str, _CompiledEndpoint] = {}
        generic_roles_reported: set[tuple[DeviceRole, str]] = set()
        for endpoint in expanded:
            model_name = physical_profile.endpoint_role_models.get(endpoint.role)
            model_profile = physical_profile.model_by_name(model_name) if model_name else None
            if model_profile is None:
                issues.append(_error(
                    CompilationIssueCode.ENDPOINT_MODEL_UNRESOLVED,
                    f"No existe resolución física para el rol {endpoint.role.value}.", endpoint.id,
                ))
                continue
            generic_key = (endpoint.role, model_profile.model)
            if model_profile.generic and generic_key not in generic_roles_reported:
                issues.append(_warning(
                    CompilationIssueCode.ENDPOINT_MODEL_GENERIC,
                    f"El rol {endpoint.role.value} usa el modelo físico genérico {model_profile.model}.",
                    endpoint.role.value,
                ))
                generic_roles_reported.add(generic_key)
            if endpoint.wired and not endpoint.wireless and not model_profile.network_port:
                issues.append(_error(
                    CompilationIssueCode.PHYSICAL_PORT_MISSING,
                    f"{endpoint.id}: el perfil {model_profile.model} no define puerto de red.", endpoint.id,
                ))
            metadata = {
                "source_group": endpoint.source_group,
                "source_index": str(endpoint.source_index),
                "pair_id": endpoint.pair_id,
                "addressing_preference": endpoint.addressing_preference.value,
                "actual_endpoint": "true",
                "growth_reserve": "false",
            }
            metadata.update({f"requirement.{key}": value for key, value in endpoint.requirement_metadata.items()})
            device = DevicePlan(
                id=endpoint.id,
                name=endpoint.name,
                model=model_profile.model,
                category=model_profile.category,
                role=_topology_role(endpoint.role),
                enterprise_role=endpoint.role.value,
                site_id=endpoint.site_id,
                building_id=endpoint.building_id,
                floor_id=endpoint.floor_id,
                zone_id=endpoint.zone_id,
                requires_poe=endpoint.requires_poe,
                wireless=endpoint.wireless,
                metadata=metadata,
            )
            compiled[endpoint.id] = _CompiledEndpoint(endpoint, device, model_profile)
        return compiled

    @staticmethod
    def _compile_modules(
        hardware_by_id: dict[str, PlannedNetworkDevice],
        name_by_id: dict[str, str],
        issues: list[CompilationIssue],
    ) -> list[ModulePlan]:
        modules: list[ModulePlan] = []
        for device_id in sorted(hardware_by_id):
            for installation in sorted(
                hardware_by_id[device_id].module_plan,
                key=lambda item: (item.slot or "", item.module),
            ):
                if installation.slot is None:
                    issues.append(_warning(
                        CompilationIssueCode.MODULE_SLOT_UNRESOLVED,
                        f"{device_id}: el módulo {installation.module} no tiene slot concreto; no se emite instalación.",
                        device_id,
                    ))
                    continue
                modules.append(ModulePlan(
                    device=name_by_id[device_id], slot=installation.slot, module=installation.module,
                ))
        return modules

    def _compile_infrastructure_links(
        self,
        hardware: HardwarePlan,
        hardware_by_id: dict[str, PlannedNetworkDevice],
        network_devices: dict[str, DevicePlan],
        allocator: _PortAllocator,
        physical_profile: PhysicalCompilationProfile,
        cable_resolver: CableResolver | None,
        issues: list[CompilationIssue],
    ) -> list[LinkPlan]:
        links: list[LinkPlan] = []
        requirements = sorted(
            (link for site in hardware.site_hardware for link in site.links),
            key=lambda item: (
                item.source_device, item.target_device, item.link_role.value,
                item.media.value, item.source_port or "", item.target_port or "",
                item.redundancy_group or "",
            ),
        )
        for index, requirement in enumerate(requirements, start=1):
            if requirement.media is LinkMedia.UNKNOWN:
                issues.append(_error(
                    CompilationIssueCode.LINK_MEDIA_UNRESOLVED,
                    f"El enlace {requirement.source_device}->{requirement.target_device} no define un medio conocido.",
                ))
                continue
            if requirement.source_device not in hardware_by_id or requirement.target_device not in hardware_by_id:
                issues.append(_error(
                    CompilationIssueCode.LINK_ENDPOINT_MISSING,
                    f"El enlace {requirement.source_device}->{requirement.target_device} referencia hardware inexistente.",
                ))
                continue
            reservation = f"infra:{index:04d}"
            source_port = allocator.allocate(
                requirement.source_device, reservation, requirement.required_port_class,
                requirement.source_port,
                allow_class_fallback=requirement.media is not LinkMedia.SERIAL,
            )
            target_port = allocator.allocate(
                requirement.target_device, reservation, requirement.required_port_class,
                requirement.target_port,
                allow_class_fallback=requirement.media is not LinkMedia.SERIAL,
            )
            if not source_port or not target_port:
                if source_port:
                    allocator.release(requirement.source_device, source_port, reservation)
                if target_port:
                    allocator.release(requirement.target_device, target_port, reservation)
                continue
            source = network_devices[requirement.source_device]
            target = network_devices[requirement.target_device]
            role = _concrete_hardware_link_role(requirement)
            links.append(_link_plan(
                source, source_port, target, target_port, role,
                source.network_layer, requirement.redundancy_group or "",
                physical_profile, cable_resolver, media=requirement.media,
            ))
        return links

    def _compile_endpoint_links(
        self,
        hardware: HardwarePlan,
        endpoints: dict[str, _CompiledEndpoint],
        network_devices: dict[str, DevicePlan],
        allocator: _PortAllocator,
        physical_profile: PhysicalCompilationProfile,
        cable_resolver: CableResolver | None,
        issues: list[CompilationIssue],
    ) -> list[LinkPlan]:
        links: list[LinkPlan] = []
        attachable: dict[str, list[_CompiledEndpoint]] = defaultdict(list)
        attached: set[str] = set()
        for endpoint in endpoints.values():
            item = endpoint.expanded
            if item.wireless or not item.wired:
                continue
            if item.role is DeviceRole.USER_PC and item.pair_id:
                continue
            attachable[item.source_group].append(endpoint)
        for items in attachable.values():
            items.sort(key=lambda item: (item.expanded.source_index, item.expanded.id))

        assignments = sorted(
            (
                assignment
                for site in hardware.site_hardware
                for block in site.access_blocks
                for assignment in block.port_assignments
            ),
            key=lambda item: (item.device_id, item.source_group, item.start_index, item.count),
        )
        for assignment in assignments:
            if assignment.device_id not in network_devices:
                issues.append(_error(
                    CompilationIssueCode.LINK_ENDPOINT_MISSING,
                    f"La asignación referencia el switch inexistente {assignment.device_id}.", assignment.device_id,
                ))
                continue
            candidates = [
                item for item in attachable.get(assignment.source_group, [])
                if assignment.start_index <= item.expanded.source_index < assignment.start_index + assignment.count
                and item.expanded.id not in attached
            ]
            if len(candidates) != assignment.count:
                issues.append(_error(
                    CompilationIssueCode.ENDPOINT_ASSIGNMENT_MISSING,
                    f"{assignment.source_group}: se esperaban {assignment.count} endpoints y se hallaron {len(candidates)}.",
                    assignment.source_group,
                ))
                continue
            switch = network_devices[assignment.device_id]
            for endpoint in candidates:
                reservation = f"endpoint:{endpoint.expanded.id}"
                switch_port = allocator.allocate(
                    assignment.device_id, reservation, PortClass.ACCESS_CAPABLE,
                    allow_class_fallback=False,
                )
                if not switch_port:
                    continue
                role = (
                    ConcreteLinkRole.SERVER_ACCESS
                    if endpoint.expanded.role in _SERVER_ROLES
                    else ConcreteLinkRole.ENDPOINT_ACCESS
                )
                links.append(_link_plan(
                    switch, switch_port, endpoint.device, endpoint.profile.network_port,
                    role, "access", "", physical_profile, cable_resolver,
                ))
                attached.add(endpoint.expanded.id)

        pairs: dict[str, dict[DeviceRole, _CompiledEndpoint]] = defaultdict(dict)
        for endpoint in endpoints.values():
            if endpoint.expanded.pair_id:
                pairs[endpoint.expanded.pair_id][endpoint.expanded.role] = endpoint
        for pair_id in sorted(pairs):
            pair = pairs[pair_id]
            phone = pair.get(DeviceRole.IP_PHONE)
            pc = pair.get(DeviceRole.USER_PC)
            if phone is None or pc is None or phone.expanded.id not in attached:
                issues.append(_error(
                    CompilationIssueCode.ENDPOINT_ASSIGNMENT_MISSING,
                    f"{pair_id}: el par PC/teléfono no quedó completamente conectado.", pair_id,
                ))
                continue
            if not phone.profile.passthrough_port:
                issues.append(_error(
                    CompilationIssueCode.PHYSICAL_PORT_MISSING,
                    f"{phone.profile.model} no define el puerto downstream del teléfono.", phone.expanded.id,
                ))
                continue
            links.append(_link_plan(
                phone.device, phone.profile.passthrough_port,
                pc.device, pc.profile.network_port,
                ConcreteLinkRole.PHONE_PASSTHROUGH, "access", "",
                physical_profile, cable_resolver,
            ))
            attached.add(pc.expanded.id)

        expected = {
            endpoint.expanded.id for endpoint in endpoints.values()
            if endpoint.expanded.wired and not endpoint.expanded.wireless
        }
        missing = sorted(expected - attached)
        for endpoint_id in missing:
            issues.append(_error(
                CompilationIssueCode.ENDPOINT_ASSIGNMENT_MISSING,
                f"El endpoint cableado {endpoint_id} no obtuvo enlace físico.", endpoint_id,
            ))
        return links

    @staticmethod
    def _capability_warnings(
        hardware: HardwarePlan, endpoints: dict[str, _CompiledEndpoint],
    ) -> list[CompilationIssue]:
        warnings: list[CompilationIssue] = []
        if any(item.expanded.requires_poe for item in endpoints.values()):
            unknown = sorted(
                device.id
                for site in hardware.site_hardware
                for device in site.devices
                if device.role is DeviceRole.ACCESS_SWITCH and device.poe_capacity is None
            )
            if unknown:
                warnings.append(_warning(
                    CompilationIssueCode.POE_CAPABILITY_UNKNOWN,
                    "La topología propaga requires_poe, pero la operación PoE sigue sin evidencia runtime.",
                    details_count=len(unknown),
                ))
        return warnings

    @staticmethod
    def _result(
        topology: TopologyPlan,
        enterprise: EnterprisePlan,
        issues: list[CompilationIssue],
        regions: list[LayoutRegion],
        *,
        valid: bool,
    ) -> EnterpriseCompileResult:
        ordered_issues = sorted(
            _deduplicate_issues(issues),
            key=lambda item: (item.severity.value, item.code.value, item.subject, item.message),
        )
        role_counts = Counter(
            device.enterprise_role for device in topology.devices if not device.network_layer
        )
        bounds = [region for region in regions if region.kind == "site"]
        width = max((region.x + region.width for region in bounds), default=0) - min(
            (region.x for region in bounds), default=0,
        )
        height = max((region.y + region.height for region in bounds), default=0) - min(
            (region.y for region in bounds), default=0,
        )
        summary = EnterpriseCompileSummary(
            plan_id=topology.id,
            semantic_hash=topology.semantic_hash if valid else "",
            physical_topology_hash=topology.physical_topology_hash if valid else "",
            layout_hash=topology.layout_hash if valid else "",
            artifact_hash=topology.artifact_hash if valid else "",
            sites=len(enterprise.sites),
            network_devices=sum(bool(device.network_layer) for device in topology.devices),
            endpoints=sum(not device.network_layer for device in topology.devices),
            endpoints_by_role=dict(sorted(role_counts.items())),
            devices=len(topology.devices),
            links=len(topology.links),
            endpoint_access_links=sum(
                link.link_role in {ConcreteLinkRole.ENDPOINT_ACCESS.value, ConcreteLinkRole.SERVER_ACCESS.value}
                for link in topology.links
            ),
            phone_passthrough_links=sum(
                link.link_role == ConcreteLinkRole.PHONE_PASSTHROUGH.value for link in topology.links
            ),
            infrastructure_links=sum(
                link.link_role not in {
                    ConcreteLinkRole.ENDPOINT_ACCESS.value,
                    ConcreteLinkRole.SERVER_ACCESS.value,
                    ConcreteLinkRole.PHONE_PASSTHROUGH.value,
                }
                for link in topology.links
            ),
            warnings=sum(issue.severity is CompilationIssueSeverity.WARNING for issue in ordered_issues),
            errors=sum(issue.severity is CompilationIssueSeverity.ERROR for issue in ordered_issues),
            layout_width=width,
            layout_height=height,
        )
        return EnterpriseCompileResult(
            plan=topology if valid else None,
            semantic_hash=topology.semantic_hash if valid else "",
            physical_topology_hash=topology.physical_topology_hash if valid else "",
            layout_hash=topology.layout_hash if valid else "",
            artifact_hash=topology.artifact_hash if valid else "",
            summary=summary,
            issues=ordered_issues,
            layout_regions=regions if valid else [],
        )


def _hierarchy_for_zone(site: object | None, zone_id: str) -> tuple[str, str]:
    if site is None or not zone_id:
        return "", ""
    for context in iter_zone_contexts(site):
        if context.zone.zone_id == zone_id:
            return context.building_id, context.floor_id
    return "", ""


def _topology_role(role: DeviceRole) -> TopologyDeviceRole:
    if role is DeviceRole.ACCESS_SWITCH:
        return TopologyDeviceRole.ACCESS_SWITCH
    if role in {DeviceRole.DISTRIBUTION_SWITCH, DeviceRole.CORE_SWITCH}:
        return TopologyDeviceRole.DISTRIBUTION_SWITCH
    if role is DeviceRole.EDGE_ROUTER:
        return TopologyDeviceRole.EDGE_ROUTER
    if role is DeviceRole.WAN_ROUTER:
        return TopologyDeviceRole.CORE_ROUTER
    if role in _SERVER_ROLES:
        return TopologyDeviceRole.SERVER_HOST
    return TopologyDeviceRole.END_HOST


def _concrete_hardware_link_role(requirement: HardwareLinkRequirement) -> ConcreteLinkRole:
    if requirement.redundancy_group and requirement.link_role is LinkRole.REDUNDANT_LINK:
        return ConcreteLinkRole.REDUNDANT_LINK
    return {
        LinkRole.ACCESS_LINK: ConcreteLinkRole.ACCESS_UPLINK,
        LinkRole.UPLINK: ConcreteLinkRole.ACCESS_UPLINK,
        LinkRole.DISTRIBUTION_LINK: ConcreteLinkRole.DISTRIBUTION_UPLINK,
        LinkRole.CORE_LINK: ConcreteLinkRole.CORE_LINK,
        LinkRole.EDGE_LINK: ConcreteLinkRole.EDGE_LINK,
        LinkRole.WAN_LINK: ConcreteLinkRole.WAN_LINK,
        LinkRole.REDUNDANT_LINK: ConcreteLinkRole.REDUNDANT_LINK,
    }[requirement.link_role]


def _link_plan(
    source: DevicePlan,
    source_port: str,
    target: DevicePlan,
    target_port: str,
    role: ConcreteLinkRole,
    network_layer: str,
    redundancy_group: str,
    physical_profile: PhysicalCompilationProfile,
    cable_resolver: CableResolver | None,
    media: LinkMedia = LinkMedia.ETHERNET,
) -> LinkPlan:
    semantic_parts = [role.value, source.id, source_port, target.id, target_port]
    if media is not LinkMedia.ETHERNET:
        semantic_parts.insert(1, media.value)
    semantic = "|".join(semantic_parts)
    link_id = f"link/{role.value}/{hashlib.sha256(semantic.encode('utf-8')).hexdigest()[:12]}"
    cable = (
        LinkMedia.SERIAL.value
        if media is LinkMedia.SERIAL
        else cable_resolver(source.category, target.category)
        if cable_resolver is not None
        else physical_profile.default_cable
    )
    return LinkPlan(
        id=link_id,
        device_a=source.name,
        port_a=source_port,
        device_b=target.name,
        port_b=target_port,
        cable=cable,
        device_a_id=source.id,
        device_b_id=target.id,
        link_role=role.value,
        network_layer=network_layer,
        redundancy_group=redundancy_group,
    )


def _error(
    code: CompilationIssueCode,
    message: str,
    subject: str = "",
    **details: str | int | bool,
) -> CompilationIssue:
    return CompilationIssue(
        severity=CompilationIssueSeverity.ERROR,
        code=code,
        message=message,
        subject=subject,
        details=details,
    )


def _warning(
    code: CompilationIssueCode,
    message: str,
    subject: str = "",
    **details: str | int | bool,
) -> CompilationIssue:
    return CompilationIssue(
        severity=CompilationIssueSeverity.WARNING,
        code=code,
        message=message,
        subject=subject,
        details=details,
    )


def _deduplicate_issues(issues: list[CompilationIssue]) -> list[CompilationIssue]:
    unique: dict[tuple[str, str, str, str], CompilationIssue] = {}
    for issue in issues:
        key = (issue.severity.value, issue.code.value, issue.subject, issue.message)
        unique[key] = issue
    return list(unique.values())
