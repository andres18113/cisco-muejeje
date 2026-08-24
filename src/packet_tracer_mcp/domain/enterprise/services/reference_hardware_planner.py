"""Resolve a governed exact physical design into the ordinary E3 HardwarePlan."""

from __future__ import annotations

from collections import defaultdict

from ..models.capabilities import CapabilityStatus, DeviceCandidateStatus
from ..models.enterprise_plan import EnterprisePlan
from ..models.hardware import (
    HardwareCandidate,
    HardwarePlan,
    HardwarePlanStatus,
    PhysicalDesignSpec,
    PlannedNetworkDevice,
    PortClass,
    SiteHardwarePlan,
)
from .endpoint_expander import EndpointGroupExpander
from .naming import DeterministicNamingService


class ReferenceHardwarePlanner:
    """Bind exact reference devices only to candidates with exact port evidence.

    Powered ports are admitted the same way physical ports are: from exact
    evidence about the selected build, never from a model name and never from an
    aggregate nobody reconciled against the bindings. A powered endpoint is a
    demand on one named port of one selected switch, so that is the granularity
    the decision is made at:

    * UNSUPPORTED is a measured refusal, so the design is UNRESOLVED;
    * UNKNOWN is not permission -- the device drops to NEEDS_VERIFICATION and
      the plan to PARTIALLY_RESOLVED, which E5 already refuses to compile;
    * SUPPORTED still has to cover the exact demand, on ports the evidence
      actually reached.

    That last clause is not pedantry. The admitted powered-port count for a
    build is measured over its access ports, so counting a powered endpoint
    bound to an uplink would let a 24-port budget silently absorb a 25th
    powered attachment nobody ever observed delivering power.
    """

    def plan(
        self,
        enterprise: EnterprisePlan,
        design: PhysicalDesignSpec,
        candidates: list[HardwareCandidate],
    ) -> HardwarePlan:
        errors: list[str] = []
        unverified: list[str] = []
        enterprise_sites = {item.site_id for item in enterprise.sites}
        design_sites = {item.site_id for item in design.sites}
        if enterprise_sites != design_sites:
            missing = sorted(enterprise_sites - design_sites)
            extra = sorted(design_sites - enterprise_sites)
            if missing:
                errors.append(f"Physical design is missing enterprise sites: {missing}.")
            if extra:
                errors.append(f"Physical design has unknown sites: {extra}.")

        candidates_by_model = {item.model: item for item in candidates}
        design_devices = [device for site in design.sites for device in site.devices]
        by_id = {item.id: item for item in design_devices}
        if len(by_id) != len(design_devices):
            errors.append("Physical design contains duplicate network device IDs.")
        names = [item.semantic_name for item in design_devices]
        if len(set(names)) != len(names):
            errors.append("Physical design contains duplicate semantic device names.")

        required_ports: dict[str, set[str]] = defaultdict(set)
        for site in design.sites:
            for link in site.links:
                if link.source_port:
                    required_ports[link.source_device].add(link.source_port)
                if link.target_port:
                    required_ports[link.target_device].add(link.target_port)
            for binding in site.endpoint_bindings:
                required_ports[binding.device_id].add(binding.device_port)

        powered_ports = self._powered_ports_by_device(enterprise, design)
        for site in design.sites:
            for block in site.access_blocks:
                exact = sum(
                    len(powered_ports.get(switch, ())) for switch in block.switches
                )
                if exact != block.required_poe_ports:
                    errors.append(
                        f"{block.block_id}: required_poe_ports "
                        f"{block.required_poe_ports} does not reconcile with the "
                        f"{exact} powered endpoint binding(s) on its switches."
                    )

        resolved_by_id: dict[str, PlannedNetworkDevice] = {}
        for requested in design_devices:
            candidate = candidates_by_model.get(requested.model)
            if candidate is None:
                errors.append(
                    f"{requested.id}: no hardware candidate exists for {requested.model}."
                )
                continue
            if requested.site_id not in enterprise_sites:
                errors.append(
                    f"{requested.id}: site {requested.site_id!r} is not in EnterprisePlan."
                )

            selected_modules = []
            module_ports: set[str] = set()
            for module in requested.modules:
                option = next(
                    (
                        item for item in candidate.module_options
                        if item.module == module.module
                        and item.slot == module.slot
                        and set(module.provided_ports) <= set(item.provided_ports)
                    ),
                    None,
                )
                if option is None:
                    errors.append(
                        f"{requested.id}: {requested.model} has no exact-build evidence "
                        f"for {module.module}@{module.slot}."
                    )
                    continue
                selected_modules.append(module)
                module_ports.update(module.provided_ports)

            ports_by_name = {item.name: item for item in candidate.ports}
            for port in sorted(required_ports.get(requested.id, set())):
                if port in module_ports:
                    continue
                descriptor = ports_by_name.get(port)
                if descriptor is None:
                    errors.append(
                        f"{requested.id}: required port {port} is absent from "
                        f"the {requested.model} inventory."
                    )
                elif not descriptor.source.startswith("backend_verified:"):
                    errors.append(
                        f"{requested.id}: required port {port} is only "
                        f"{descriptor.source}, not exact-build evidence."
                    )

            access_ports = sum(
                PortClass.ACCESS_CAPABLE in item.classes for item in candidate.ports
            )
            poe_capacity = (
                candidate.capabilities.poe_ports
                if candidate.capabilities.supports_poe is CapabilityStatus.SUPPORTED
                else None
            )
            selection_status = DeviceCandidateStatus.COMPATIBLE
            demanded = sorted(powered_ports.get(requested.id, set()))
            if demanded:
                poe_capacity, selection_status = self._admit_powered_ports(
                    requested, candidate, demanded, ports_by_name, errors, unverified,
                )
            resolved_by_id[requested.id] = PlannedNetworkDevice(
                id=requested.id,
                site_id=requested.site_id,
                role=requested.role,
                additional_roles=list(requested.additional_roles),
                network_layer=requested.network_layer,
                selection_status=selection_status,
                semantic_name=requested.semantic_name,
                selected_model=requested.model,
                candidate_models=[requested.model],
                port_capacity=access_ports,
                poe_capacity=poe_capacity,
                port_descriptors=list(candidate.ports),
                module_plan=selected_modules,
                parent_group=requested.parent_group,
                redundancy_group=requested.redundancy_group,
            )

        site_hardware = [
            SiteHardwarePlan(
                site_id=site.site_id,
                topology_pattern=site.topology_pattern,
                hierarchy_mode=site.hierarchy_mode,
                network_layers=list(site.network_layers),
                devices=[
                    resolved_by_id[item.id]
                    for item in site.devices
                    if item.id in resolved_by_id
                ],
                links=list(site.links),
                access_blocks=list(site.access_blocks),
                endpoint_bindings=list(site.endpoint_bindings),
                resiliency=site.resiliency,
            )
            for site in design.sites
        ]
        return HardwarePlan(
            status=(
                HardwarePlanStatus.UNRESOLVED
                if errors
                else HardwarePlanStatus.PARTIALLY_RESOLVED
                if unverified
                else HardwarePlanStatus.VALID
            ),
            site_hardware=site_hardware,
            warnings=[*errors, *unverified],
        )

    @staticmethod
    def _powered_ports_by_device(
        enterprise: EnterprisePlan,
        design: PhysicalDesignSpec,
    ) -> dict[str, set[str]]:
        """Exact powered demand: expanded endpoint truth joined to the bindings.

        `endpoint_id` derives from zone, role and index alone, so the identity
        counted here is the identity E5 later binds against.
        """
        powered = {
            item.id
            for item in EndpointGroupExpander().expand(
                enterprise, DeterministicNamingService(),
            )
            if item.requires_poe
        }
        ports: dict[str, set[str]] = defaultdict(set)
        for site in design.sites:
            for binding in site.endpoint_bindings:
                if binding.endpoint_id in powered:
                    ports[binding.device_id].add(binding.device_port)
        return ports

    @staticmethod
    def _admit_powered_ports(
        requested,
        candidate: HardwareCandidate,
        demanded: list[str],
        ports_by_name: dict,
        errors: list[str],
        unverified: list[str],
    ) -> tuple[int | None, DeviceCandidateStatus]:
        """Decide one selected build against its own exact powered demand."""
        status = candidate.capabilities.supports_poe
        admitted = candidate.capabilities.poe_ports
        if status is CapabilityStatus.UNSUPPORTED:
            errors.append(
                f"{requested.id}: {requested.model} has exact-build evidence of no "
                f"PoE, but {len(demanded)} powered endpoint(s) are bound to it."
            )
            return None, DeviceCandidateStatus.INCOMPATIBLE
        if status is CapabilityStatus.UNKNOWN:
            unverified.append(
                f"{requested.id}: {requested.model} PoE capability is unknown, so "
                f"the {len(demanded)} powered endpoint(s) bound to it are not "
                "admitted."
            )
            return None, DeviceCandidateStatus.NEEDS_VERIFICATION
        if admitted is None:
            errors.append(
                f"{requested.id}: {requested.model} reports PoE support without an "
                f"admitted powered-port count for {len(demanded)} powered "
                "endpoint(s)."
            )
            return None, DeviceCandidateStatus.NEEDS_VERIFICATION
        if len(demanded) > admitted:
            errors.append(
                f"{requested.id}: {len(demanded)} powered endpoint(s) exceed the "
                f"{admitted} powered port(s) evidenced for {requested.model}."
            )
            return None, DeviceCandidateStatus.INCOMPATIBLE
        for port in demanded:
            descriptor = ports_by_name.get(port)
            if descriptor is None:
                continue
            if PortClass.ACCESS_CAPABLE not in descriptor.classes:
                errors.append(
                    f"{requested.id}: powered endpoint port {port} is outside the "
                    f"access ports the {requested.model} PoE evidence covers."
                )
        return admitted, DeviceCandidateStatus.COMPATIBLE
