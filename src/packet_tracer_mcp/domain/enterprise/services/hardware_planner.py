"""E3: transforma capacidad agregada en un plan de hardware físico y compacto."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from ..models.capabilities import (
    CapabilityStatus,
    DeviceCandidateStatus,
    DeviceRequirement,
)
from ..models.enterprise_plan import EnterprisePlan, SitePlan
from ..models.hardware import (
    AccessBlockPlan,
    EndpointGroupSlice,
    HardwareCandidate,
    HardwareLinkRequirement,
    HardwarePlan,
    HardwarePlanStatus,
    HierarchyMode,
    LinkRole,
    ModuleInstallation,
    NetworkLayer,
    PlannedNetworkDevice,
    PortAssignmentRange,
    PortClass,
    PortDescriptor,
    ResiliencyLevel,
    SiteHardwarePlan,
)
from ..models.link_performance import LinkMedia
from ..models.roles import DeviceRole
from ..models.topology import TopologyPattern
from .device_selector import DeviceSelector
from .hierarchy_planner import iter_zone_plans


@dataclass(frozen=True)
class HierarchyPolicy:
    small_site_max_access_switches: int = 1
    collapsed_core_max_access_switches: int = 2
    max_access_switches_per_distribution: int = 8


@dataclass(frozen=True)
class HardwarePlanningPolicy:
    resiliency: ResiliencyLevel = ResiliencyLevel.BASIC
    homogeneous_access_models: bool = True
    hierarchy: HierarchyPolicy = HierarchyPolicy()


@dataclass(frozen=True)
class _SwitchChoice:
    candidate: HardwareCandidate
    count: int
    status: DeviceCandidateStatus
    warning: str = ""


@dataclass(frozen=True)
class _WanConnection:
    source_site_id: str
    target_site_id: str
    media: LinkMedia


@dataclass(frozen=True)
class _WanRouterResolution:
    device: PlannedNetworkDevice | None = None
    warning: str = ""


class SwitchCountPlanner:
    """Elige un conjunto homogéneo por capacidad física, sin reaplicar growth E2."""

    def choose(
        self,
        required_access_ports: int,
        required_poe_ports: int,
        required_uplinks: int,
        candidates: list[HardwareCandidate],
    ) -> _SwitchChoice | None:
        choices: list[_SwitchChoice] = []
        for candidate in candidates:
            access_ports = len(self._ports(candidate, PortClass.ACCESS_CAPABLE))
            uplinks = len(self._ports(candidate, PortClass.UPLINK_CAPABLE))
            if access_ports == 0 or uplinks < required_uplinks:
                continue
            poe_status = candidate.capabilities.supports_poe
            if required_poe_ports and poe_status is CapabilityStatus.UNSUPPORTED:
                continue
            access_count = ceil(required_access_ports / access_ports)
            if required_poe_ports and poe_status is CapabilityStatus.SUPPORTED:
                if not candidate.capabilities.poe_ports:
                    continue
                poe_count = ceil(required_poe_ports / candidate.capabilities.poe_ports)
            else:
                poe_count = 1
            count = max(access_count, poe_count)
            status = (
                DeviceCandidateStatus.NEEDS_VERIFICATION
                if required_poe_ports and poe_status is CapabilityStatus.UNKNOWN
                else DeviceCandidateStatus.COMPATIBLE
            )
            warning = (
                f"{candidate.model}: PoE requiere evidencia antes de selección definitiva."
                if status is DeviceCandidateStatus.NEEDS_VERIFICATION else ""
            )
            choices.append(_SwitchChoice(candidate, count, status, warning))
        if not choices:
            return None
        return min(
            choices,
            key=lambda item: (
                item.status is DeviceCandidateStatus.NEEDS_VERIFICATION,
                item.count,
                item.count * len(self._ports(item.candidate, PortClass.ACCESS_CAPABLE)) - required_access_ports,
                item.candidate.model.casefold(),
            ),
        )

    @staticmethod
    def _ports(candidate: HardwareCandidate, port_class: PortClass):
        return [port for port in candidate.ports if port_class in port.classes]


class ModulePlanner:
    """Planifica sólo módulos compatibles ya declarados por el catálogo."""

    def plan_serial(
        self,
        candidate: HardwareCandidate,
        required_serial_ports: int,
        options: list[ModuleInstallation],
        available_slots: int | None = None,
    ) -> list[ModuleInstallation] | None:
        existing = len([port for port in candidate.ports if PortClass.SERIAL in port.classes])
        if existing >= required_serial_ports:
            return []
        if candidate.capabilities.supports_modules is not CapabilityStatus.SUPPORTED:
            return None
        compatible = [option for option in options if option.module in candidate.capabilities.compatible_modules]
        compatible.sort(key=lambda item: (
            len(item.provided_ports), item.module.casefold(), item.slot or "",
        ))
        selected: list[ModuleInstallation] = []
        provided = existing
        for option in compatible:
            if available_slots is not None and len(selected) >= available_slots:
                return None
            selected.append(option)
            provided += len(option.provided_ports)
            if provided >= required_serial_ports:
                return selected
        return None


class HardwareHierarchyPlanner:
    """Decide Flat/Collapsed/Three-tier con threshold centralizado."""

    @staticmethod
    def choose(access_switches: int, policy: HierarchyPolicy) -> HierarchyMode:
        if access_switches <= policy.small_site_max_access_switches:
            return HierarchyMode.FLAT
        if access_switches <= policy.collapsed_core_max_access_switches:
            return HierarchyMode.COLLAPSED_CORE
        return HierarchyMode.THREE_TIER


class PortAssignmentPlanner:
    """Distribuye slices agregados por puertos físicos reales del candidato provisional."""

    def assign(
        self,
        block: AccessBlockPlan,
        devices: list[PlannedNetworkDevice],
    ) -> list[str]:
        warnings: list[str] = []
        availability = {
            device.id: [port.name for port in device.port_descriptors if PortClass.ACCESS_CAPABLE in port.classes]
            for device in devices
        }
        position = {device.id: 0 for device in devices}
        poe_position = {device.id: 0 for device in devices}
        for endpoint_slice in block.endpoint_slices:
            remaining = endpoint_slice.count
            start = endpoint_slice.start_index
            for device in devices:
                free = len(availability[device.id]) - position[device.id]
                if endpoint_slice.requires_poe and device.poe_capacity is not None:
                    free = min(free, device.poe_capacity - poe_position[device.id])
                if free <= 0 or remaining <= 0:
                    continue
                count = min(free, remaining)
                first_index = position[device.id]
                names = availability[device.id][first_index:first_index + count]
                block.port_assignments.append(PortAssignmentRange(
                    device_id=device.id,
                    source_group=endpoint_slice.group_id,
                    roles=endpoint_slice.roles,
                    start_index=start,
                    count=count,
                    first_port=names[0],
                    last_port=names[-1],
                    requires_poe=endpoint_slice.requires_poe,
                ))
                position[device.id] += count
                if endpoint_slice.requires_poe:
                    poe_position[device.id] += count
                remaining -= count
                start += count
            if remaining:
                warnings.append(f"{endpoint_slice.group_id}: {remaining} endpoint(s) sin puerto asignado.")
        return warnings


class RedundancyPlanner:
    """Representa enlaces físicos redundantes, sin configurar STP o EtherChannel."""

    def connect_access(
        self,
        access_devices: list[PlannedNetworkDevice],
        distribution_devices: list[PlannedNetworkDevice],
        resiliency: ResiliencyLevel,
    ) -> tuple[list[HardwareLinkRequirement], list[str]]:
        links: list[HardwareLinkRequirement] = []
        warnings: list[str] = []
        requested = 2 if resiliency is not ResiliencyLevel.NONE else 1
        for access in access_devices:
            parents = distribution_devices[:requested]
            if len(parents) < requested:
                warnings.append(f"{access.id}: redundancia de uplink no satisfecha; faltan distribution devices.")
            for index, parent in enumerate(parents, start=1):
                access_ports = [port.name for port in access.port_descriptors if PortClass.UPLINK_CAPABLE in port.classes]
                links.append(HardwareLinkRequirement(
                    source_device=access.id,
                    target_device=parent.id,
                    link_role=LinkRole.UPLINK,
                    source_port=access_ports[index - 1] if len(access_ports) >= index else None,
                    redundancy_group=f"uplink-{access.id}" if requested > 1 else None,
                ))
        return links, warnings

    @staticmethod
    def connect_layer(
        children: list[PlannedNetworkDevice],
        parents: list[PlannedNetworkDevice],
        role: LinkRole,
        resiliency: ResiliencyLevel,
    ) -> list[HardwareLinkRequirement]:
        if not children or not parents:
            return []
        parent_count = min(len(parents), 2 if resiliency is ResiliencyLevel.HIGH else 1)
        return [
            HardwareLinkRequirement(
                source_device=child.id,
                target_device=parent.id,
                link_role=role,
                redundancy_group=f"{role.value}-{child.id}" if parent_count > 1 else None,
            )
            for child in children
            for parent in parents[:parent_count]
        ]


class HardwarePlanner:
    """Orquestador E3 puro: consume EnterprisePlan y candidatos adaptados por infraestructura."""

    def plan(
        self,
        enterprise_plan: EnterprisePlan,
        switch_candidates: list[HardwareCandidate],
        router_candidates: list[HardwareCandidate] | None = None,
        policy: HardwarePlanningPolicy = HardwarePlanningPolicy(),
    ) -> HardwarePlan:
        wan_connections, wan_warnings = self._wan_connections(enterprise_plan)
        wan_demand = self._wan_demand(wan_connections)
        site_hardware = [
            self._plan_site(
                site,
                switch_candidates,
                router_candidates or [],
                policy,
                enterprise_plan.internet_required,
                *wan_demand.get(site.site_id, (0, 0)),
            )
            for site in sorted(enterprise_plan.sites, key=lambda item: item.site_id)
        ]
        self._connect_wan(site_hardware, wan_connections)
        warnings = [
            *wan_warnings,
            *(warning for site in site_hardware for warning in site.warnings),
        ]
        status = (
            HardwarePlanStatus.UNRESOLVED if not any(
                device.selected_model or device.provisional_model
                for site in site_hardware for device in site.devices
            )
            else HardwarePlanStatus.PARTIALLY_RESOLVED if warnings else HardwarePlanStatus.VALID
        )
        unsupported = [
            warning for warning in warnings
            if warning.startswith(("No existe candidato", "WAN inválida:"))
            or "sin puerto asignado" in warning
        ]
        return HardwarePlan(
            status=status,
            site_hardware=site_hardware,
            warnings=warnings,
            unsupported_requirements=unsupported,
        )

    def _plan_site(
        self,
        site: SitePlan,
        switch_candidates: list[HardwareCandidate],
        router_candidates: list[HardwareCandidate],
        policy: HardwarePlanningPolicy,
        internet_required: bool,
        required_serial_ports: int,
        required_wan_ethernet_ports: int,
    ) -> SiteHardwarePlan:
        access_blocks: list[AccessBlockPlan] = []
        devices: list[PlannedNetworkDevice] = []
        warnings: list[str] = []
        zones = {zone.zone_id: zone for zone in iter_zone_plans(site)}
        counter = 0
        count_planner = SwitchCountPlanner()
        for capacity in site.capacity_requirements:
            choice = count_planner.choose(
                capacity.required_access_ports, capacity.required_poe_ports,
                capacity.required_uplink_ports, switch_candidates,
            )
            block = AccessBlockPlan(
                site_id=site.site_id,
                zone_id=capacity.zone_id,
                block_id=f"access-{capacity.zone_id.rsplit('/', 1)[-1]}",
                required_access_ports=capacity.required_access_ports,
                required_poe_ports=capacity.required_poe_ports,
                required_uplinks=capacity.required_uplink_ports,
            )
            if choice is None:
                block.warnings.append("No existe candidato con puertos de acceso y uplinks físicos suficientes.")
                warnings.extend(block.warnings)
                access_blocks.append(block)
                continue
            if choice.warning:
                block.warnings.append(choice.warning)
                warnings.append(choice.warning)
            access_devices = []
            for index in range(1, choice.count + 1):
                counter += 1
                device = PlannedNetworkDevice(
                    id=f"sw-acc-{site.site_id}-{capacity.zone_id.rsplit('/', 1)[-1]}-{index:02d}",
                    site_id=site.site_id,
                    role=DeviceRole.ACCESS_SWITCH,
                    network_layer=NetworkLayer.ACCESS,
                    selection_status=choice.status,
                    selected_model=choice.candidate.model if choice.status is DeviceCandidateStatus.COMPATIBLE else None,
                    provisional_model=choice.candidate.model if choice.status is DeviceCandidateStatus.NEEDS_VERIFICATION else None,
                    candidate_models=[choice.candidate.model],
                    required_capabilities=DeviceRequirement(
                        role=DeviceRole.ACCESS_SWITCH,
                        min_access_ports=1,
                        min_uplinks=capacity.required_uplink_ports,
                        poe_ports=1 if capacity.required_poe_ports else 0,
                    ),
                    port_capacity=len([port for port in choice.candidate.ports if PortClass.ACCESS_CAPABLE in port.classes]),
                    poe_capacity=choice.candidate.capabilities.poe_ports,
                    port_descriptors=choice.candidate.ports,
                    parent_group=block.block_id,
                    warnings=[choice.warning] if choice.warning else [],
                )
                devices.append(device)
                access_devices.append(device)
                block.switches.append(device.id)
            block.endpoint_slices = self._slices(zones.get(capacity.zone_id), capacity.pc_phone_pairs)
            assignment_warnings = PortAssignmentPlanner().assign(block, access_devices)
            block.warnings.extend(assignment_warnings)
            warnings.extend(assignment_warnings)
            access_blocks.append(block)

        access_devices = [device for device in devices if device.role is DeviceRole.ACCESS_SWITCH]
        mode = HardwareHierarchyPlanner.choose(len(access_devices), policy.hierarchy)
        higher_devices = self._higher_layers(
            site, mode, len(access_devices), switch_candidates, router_candidates,
            policy, internet_required,
        )
        wan_resolution = self._wan_router_device(
            site,
            router_candidates,
            required_serial_ports,
            required_wan_ethernet_ports,
        )
        if wan_resolution.device is not None:
            higher_devices.append(wan_resolution.device)
        elif wan_resolution.warning:
            warnings.append(wan_resolution.warning)
        devices.extend(higher_devices)
        for device in higher_devices:
            if device.selection_status is not DeviceCandidateStatus.COMPATIBLE:
                warnings.append(f"{device.id}: selección provisional; falta evidencia de capacidades requeridas.")
        distributions = [device for device in higher_devices if device.role is DeviceRole.DISTRIBUTION_SWITCH]
        redundancy = RedundancyPlanner()
        uplinks, redundancy_warnings = redundancy.connect_access(access_devices, distributions, policy.resiliency)
        cores = [device for device in higher_devices if device.role is DeviceRole.CORE_SWITCH]
        edges = [device for device in higher_devices if device.role is DeviceRole.EDGE_ROUTER]
        uplinks.extend(redundancy.connect_layer(distributions, cores, LinkRole.CORE_LINK, policy.resiliency))
        uplinks.extend(redundancy.connect_layer(cores, edges, LinkRole.EDGE_LINK, policy.resiliency))
        warnings.extend(redundancy_warnings)
        pattern = site.topology.pattern if site.topology else TopologyPattern.STAR
        layers = site.topology.network_layers if site.topology else [NetworkLayer.ACCESS]
        return SiteHardwarePlan(
            site_id=site.site_id,
            topology_pattern=pattern,
            hierarchy_mode=mode,
            network_layers=layers,
            devices=devices,
            links=uplinks,
            access_blocks=access_blocks,
            resiliency=policy.resiliency,
            warnings=warnings,
        )

    @staticmethod
    def _wan_connections(
        enterprise_plan: EnterprisePlan,
    ) -> tuple[list[_WanConnection], list[str]]:
        known_sites = {site.site_id for site in enterprise_plan.sites}
        media_by_pair: dict[tuple[str, str], set[LinkMedia]] = {}
        warnings: list[str] = []
        for site in sorted(enterprise_plan.sites, key=lambda item: item.site_id):
            for requirement in sorted(
                site.uplinks,
                key=lambda item: (item.target_site_id, item.media.value),
            ):
                target = requirement.target_site_id
                if target not in known_sites:
                    warnings.append(
                        f"WAN inválida: {site.site_id} referencia el sitio inexistente {target}."
                    )
                    continue
                if target == site.site_id:
                    warnings.append(
                        f"WAN inválida: {site.site_id} no puede enlazarse consigo mismo."
                    )
                    continue
                if requirement.media is LinkMedia.UNKNOWN:
                    warnings.append(
                        f"WAN inválida: {site.site_id}->{target} requiere un medio conocido."
                    )
                    continue
                source, destination = sorted((site.site_id, target))
                media_by_pair.setdefault((source, destination), set()).add(
                    requirement.media,
                )
        connections: list[_WanConnection] = []
        for pair, media in sorted(media_by_pair.items()):
            if len(media) > 1:
                media_names = ", ".join(sorted(item.value for item in media))
                warnings.append(
                    f"WAN inválida: {pair[0]}<->{pair[1]} declara medios "
                    f"incompatibles: {media_names}."
                )
                continue
            connections.append(_WanConnection(
                source_site_id=pair[0],
                target_site_id=pair[1],
                media=next(iter(media)),
            ))
        return connections, sorted(set(warnings))

    @staticmethod
    def _wan_demand(
        connections: list[_WanConnection],
    ) -> dict[str, tuple[int, int]]:
        counts: dict[str, list[int]] = {}
        for connection in connections:
            index = 0 if connection.media is LinkMedia.SERIAL else 1
            for site_id in (connection.source_site_id, connection.target_site_id):
                demand = counts.setdefault(site_id, [0, 0])
                demand[index] += 1
        return {site_id: (demand[0], demand[1]) for site_id, demand in counts.items()}

    @staticmethod
    def _wan_router_device(
        site: SitePlan,
        router_candidates: list[HardwareCandidate],
        required_serial_ports: int,
        required_ethernet_ports: int,
    ) -> _WanRouterResolution:
        if required_serial_ports == 0 and required_ethernet_ports == 0:
            return _WanRouterResolution()
        viable: list[tuple[HardwareCandidate, list[ModuleInstallation], list[PortDescriptor]]] = []
        unknown_module_models: list[str] = []
        unsupported_reasons: list[str] = []
        module_planner = ModulePlanner()
        for candidate in sorted(router_candidates, key=lambda item: item.model.casefold()):
            ethernet_ports = [
                port for port in candidate.ports
                if PortClass.UPLINK_CAPABLE in port.classes
            ]
            if len(ethernet_ports) < required_ethernet_ports:
                unsupported_reasons.append(
                    f"{candidate.model} sólo tiene {len(ethernet_ports)} puerto(s) "
                    f"Ethernet WAN y se requiere(n) {required_ethernet_ports}"
                )
                continue
            existing_serial_ports = [
                port for port in candidate.ports
                if PortClass.SERIAL in port.classes
            ]
            needs_module = len(existing_serial_ports) < required_serial_ports
            if needs_module and candidate.capabilities.supports_modules is CapabilityStatus.UNKNOWN:
                unknown_module_models.append(candidate.model)
                continue
            if needs_module and candidate.capabilities.supports_modules is CapabilityStatus.UNSUPPORTED:
                unsupported_reasons.append(
                    f"{candidate.model} tiene supports_modules=UNSUPPORTED y se requiere(n) "
                    f"{required_serial_ports} puerto(s) serial"
                )
                continue
            module_plan = module_planner.plan_serial(
                candidate,
                required_serial_ports,
                candidate.module_options,
                available_slots=len(candidate.available_module_slots),
            )
            if module_plan is None:
                unsupported_reasons.append(
                    f"{candidate.model} no tiene un módulo serial compatible con "
                    f"{required_serial_ports} puerto(s) y los slots disponibles"
                )
                continue
            module_ports = [
                PortDescriptor(
                    name=port,
                    classes=list(dict.fromkeys([
                        PortClass.MODULE_PROVIDED,
                        PortClass.WAN,
                        *installation.provided_port_classes,
                    ])),
                    source="module_plan",
                    slot=installation.slot or "",
                    module=installation.module,
                )
                for installation in module_plan
                for port in installation.provided_ports
            ]
            viable.append((candidate, module_plan, [*candidate.ports, *module_ports]))
        if not viable:
            if unknown_module_models:
                models = ", ".join(sorted(unknown_module_models, key=str.casefold))
                return _WanRouterResolution(warning=(
                    f"WAN: {site.site_id} queda sin resolver: {models} tiene "
                    f"supports_modules=UNKNOWN; falta evidencia para instalar "
                    f"{required_serial_ports} puerto(s) serial."
                ))
            reasons = "; ".join(unsupported_reasons) or "no hay candidatos router"
            return _WanRouterResolution(warning=(
                f"No existe candidato WAN soportado para {site.site_id}: {reasons}."
            ))

        candidate, module_plan, port_descriptors = min(
            viable,
            key=lambda item: (
                len(item[1]),
                len(item[2]) - required_serial_ports - required_ethernet_ports,
                item[0].model.casefold(),
            ),
        )
        return _WanRouterResolution(device=PlannedNetworkDevice(
            id=f"r-wan-{site.site_id}-01",
            site_id=site.site_id,
            role=DeviceRole.WAN_ROUTER,
            network_layer=NetworkLayer.WAN,
            selection_status=DeviceCandidateStatus.COMPATIBLE,
            selected_model=candidate.model,
            candidate_models=sorted(
                (item[0].model for item in viable), key=str.casefold,
            ),
            required_capabilities=DeviceRequirement(
                role=DeviceRole.WAN_ROUTER,
                min_uplinks=required_ethernet_ports,
                requires_modules=bool(module_plan),
            ),
            port_capacity=len(port_descriptors),
            port_descriptors=port_descriptors,
            module_plan=module_plan,
        ))

    @staticmethod
    def _connect_wan(
        site_hardware: list[SiteHardwarePlan],
        connections: list[_WanConnection],
    ) -> None:
        sites = {site.site_id: site for site in site_hardware}
        routers = {
            site.site_id: next(
                (device for device in site.devices if device.role is DeviceRole.WAN_ROUTER),
                None,
            )
            for site in site_hardware
        }
        for connection in connections:
            source = routers.get(connection.source_site_id)
            target = routers.get(connection.target_site_id)
            if source is None or target is None:
                continue
            sites[connection.source_site_id].links.append(HardwareLinkRequirement(
                source_device=source.id,
                target_device=target.id,
                link_role=LinkRole.WAN_LINK,
                required_port_class=(
                    PortClass.SERIAL
                    if connection.media is LinkMedia.SERIAL
                    else PortClass.UPLINK_CAPABLE
                ),
                media=connection.media,
            ))

    def _higher_layers(
        self,
        site: SitePlan,
        mode: HierarchyMode,
        access_switch_count: int,
        switch_candidates: list[HardwareCandidate],
        router_candidates: list[HardwareCandidate],
        policy: HardwarePlanningPolicy,
        internet_required: bool,
    ) -> list[PlannedNetworkDevice]:
        devices: list[PlannedNetworkDevice] = []
        distribution_count = 0
        if mode is not HierarchyMode.FLAT:
            distribution_count = ceil(access_switch_count / policy.hierarchy.max_access_switches_per_distribution)
            distribution_count = max(1, distribution_count)
            if policy.resiliency is not ResiliencyLevel.NONE:
                distribution_count = max(2, distribution_count)
        core_count = (
            2 if mode is HierarchyMode.THREE_TIER and policy.resiliency is ResiliencyLevel.HIGH
            else 1 if mode is HierarchyMode.THREE_TIER else 0
        )
        devices.extend(self._layer_devices(site, DeviceRole.DISTRIBUTION_SWITCH, NetworkLayer.DISTRIBUTION, distribution_count, switch_candidates))
        devices.extend(self._layer_devices(site, DeviceRole.CORE_SWITCH, NetworkLayer.CORE, core_count, switch_candidates))
        if internet_required and router_candidates:
            devices.extend(self._layer_devices(site, DeviceRole.EDGE_ROUTER, NetworkLayer.EDGE, 1, router_candidates))
        return devices

    @staticmethod
    def _layer_devices(
        site: SitePlan,
        role: DeviceRole,
        layer: NetworkLayer,
        count: int,
        candidates: list[HardwareCandidate],
    ) -> list[PlannedNetworkDevice]:
        if not count:
            return []
        selector = DeviceSelector()
        requirement = DeviceRequirement(role=role, min_uplinks=1, requires_layer3=role is not DeviceRole.EDGE_ROUTER)
        selection = selector.select(requirement, [candidate.capabilities for candidate in candidates])
        candidate_map = {candidate.model: candidate for candidate in candidates}
        model = selection.selected_model or (selection.alternatives[0] if selection.alternatives else None)
        chosen = candidate_map.get(model) if model else None
        status = (
            DeviceCandidateStatus.COMPATIBLE if selection.selected_model
            else DeviceCandidateStatus.NEEDS_VERIFICATION if model else DeviceCandidateStatus.INCOMPATIBLE
        )
        prefix = {DeviceRole.DISTRIBUTION_SWITCH: "sw-dist", DeviceRole.CORE_SWITCH: "sw-core", DeviceRole.EDGE_ROUTER: "r-edge"}[role]
        return [
            PlannedNetworkDevice(
                id=f"{prefix}-{site.site_id}-{index:02d}",
                site_id=site.site_id,
                role=role,
                network_layer=layer,
                selection_status=status,
                selected_model=model if status is DeviceCandidateStatus.COMPATIBLE else None,
                provisional_model=model if status is DeviceCandidateStatus.NEEDS_VERIFICATION else None,
                candidate_models=selection.alternatives,
                required_capabilities=requirement,
                port_capacity=len([port for port in chosen.ports if PortClass.ACCESS_CAPABLE in port.classes]) if chosen else 0,
                port_descriptors=chosen.ports if chosen else [],
                warnings=selection.reasons if status is not DeviceCandidateStatus.COMPATIBLE else [],
            )
            for index in range(1, count + 1)
        ]

    @staticmethod
    def _slices(zone, pair_count: int) -> list[EndpointGroupSlice]:
        if zone is None:
            return []
        slices = []
        if pair_count:
            slices.append(EndpointGroupSlice(
                group_id=f"{zone.zone_id}:pc-phone", roles=[DeviceRole.USER_PC, DeviceRole.IP_PHONE],
                start_index=1, count=pair_count, requires_poe=True,
            ))
        remaining_pairs = pair_count
        direct_poe: list[EndpointGroupSlice] = []
        direct_other: list[EndpointGroupSlice] = []
        for group in zone.endpoint_groups:
            pcs = next((item.count for item in group.requirements if item.role is DeviceRole.USER_PC and item.wired and not item.wireless), 0)
            phones = next((item.count for item in group.requirements if item.role is DeviceRole.IP_PHONE and item.wired and not item.wireless), 0)
            paired_here = min(pcs, phones, remaining_pairs)
            remaining_pairs -= paired_here
            for requirement in group.requirements:
                if not requirement.wired or requirement.wireless or requirement.role in {
                    DeviceRole.ACCESS_SWITCH, DeviceRole.DISTRIBUTION_SWITCH, DeviceRole.CORE_SWITCH,
                    DeviceRole.WAN_ROUTER, DeviceRole.EDGE_ROUTER, DeviceRole.FIREWALL,
                }:
                    continue
                count = requirement.count
                if requirement.role in {DeviceRole.USER_PC, DeviceRole.IP_PHONE}:
                    count -= paired_here
                if count <= 0:
                    continue
                target = direct_poe if requirement.requires_poe else direct_other
                target.append(EndpointGroupSlice(
                    group_id=f"{zone.zone_id}:{group.name}:{requirement.role.value}",
                    roles=[requirement.role], start_index=paired_here + 1 if requirement.role in {DeviceRole.USER_PC, DeviceRole.IP_PHONE} else 1,
                    count=count, requires_poe=requirement.requires_poe,
                ))
        return slices + direct_poe + direct_other
