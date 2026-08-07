"""E5: EnterprisePlan + TopologyPlan E4 -> ConfigurationPlan puro."""

from __future__ import annotations

import hashlib
import ipaddress
import json
from collections import defaultdict

from ...models.plans import DevicePlan, LinkPlan, TopologyPlan
from ..models.addressing import SubnetAllocation
from ..models.capabilities import CapabilityStatus, DeviceCapabilities
from ..models.configuration import (
    AddressRange,
    ConfigurationAction,
    ConfigurationCompileResult,
    ConfigurationCompileSummary,
    ConfigurationIssue,
    ConfigurationIssueCode,
    ConfigurationIssueSeverity,
    ConfigurationPhase,
    ConfigurationPlan,
    ConfigurationPolicy,
    ConfigureAccessPort,
    ConfigureDhcpPool,
    ConfigureRoutedInterface,
    ConfigureSubinterface,
    ConfigureSvi,
    ConfigureTrunk,
    CreateVlan,
    DeviceConfigurationPlan,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
    VerificationExpectation,
    VerificationKind,
    action_type_counts,
)
from ..models.enterprise_plan import EnterprisePlan
from ..models.requirements import AddressingPreference, EndpointRequirement
from ..models.roles import DeviceRole
from ..models.segments import NetworkSegment, SegmentRole
from ..models.verification import PrerequisiteKind, VerificationPrerequisite
from .configuration_dependencies import ConfigurationDependencyError, order_configuration_actions
from .configuration_validator import validate_configuration_actions
from .segment_assignment import SegmentAssignmentPolicy


_RESERVED_VLANS = {1002, 1003, 1004, 1005}
_TRUNK_LINK_ROLES = {
    "access_uplink", "distribution_uplink", "core_link", "redundant_link", "edge_link",
}
_GATEWAY_ROLE_ORDER = {
    DeviceRole.EDGE_ROUTER.value: 0,
    DeviceRole.WAN_ROUTER.value: 1,
    DeviceRole.DISTRIBUTION_SWITCH.value: 2,
    DeviceRole.CORE_SWITCH.value: 3,
}


def _issue(
    severity: ConfigurationIssueSeverity,
    code: ConfigurationIssueCode,
    message: str,
    subject: str = "",
) -> ConfigurationIssue:
    return ConfigurationIssue(severity=severity, code=code, message=message, subject=subject)


def _error(code: ConfigurationIssueCode, message: str, subject: str = "") -> ConfigurationIssue:
    return _issue(ConfigurationIssueSeverity.ERROR, code, message, subject)


def _warning(code: ConfigurationIssueCode, message: str, subject: str = "") -> ConfigurationIssue:
    return _issue(ConfigurationIssueSeverity.WARNING, code, message, subject)


def _action_id(kind: str, *parts: object) -> str:
    semantic = "|".join((kind, *(str(part) for part in parts)))
    return f"cfg/{kind}/{hashlib.sha256(semantic.encode('utf-8')).hexdigest()[:16]}"


def _device_key(device: DevicePlan) -> str:
    return device.id or device.name


class ConfigurationCompiler:
    """Compila intención lógica sin bridge, IOS, TerminalLine ni MCP."""

    def compile(
        self,
        enterprise: EnterprisePlan,
        topology: TopologyPlan,
        policy: ConfigurationPolicy = ConfigurationPolicy(),
        capabilities: dict[str, DeviceCapabilities] | None = None,
    ) -> ConfigurationCompileResult:
        issues: list[ConfigurationIssue] = []
        actions: list[ConfigurationAction] = []
        if not topology.physical_identity_hash:
            issues.append(_error(
                ConfigurationIssueCode.SOURCE_TOPOLOGY_HASH_MISSING,
                "E5 requires the immutable semantic hash produced by E4.",
                topology.id,
            ))

        devices = {_device_key(device): device for device in topology.devices}
        names_to_ids = {device.name: _device_key(device) for device in topology.devices}
        links = [self._resolved_link(link, names_to_ids) for link in topology.links]
        site_segments, segment_vlans = self._segments(enterprise, policy, issues)
        allocations = {
            allocation.segment_id: allocation
            for allocation in (enterprise.addressing.allocations if enterprise.addressing else [])
        }

        endpoint_segments = self._endpoint_segments(
            topology, site_segments, issues,
        )
        pair_members = self._pair_members(topology.devices)
        access_actions, endpoint_access, switch_local_vlans = self._access_actions(
            topology, links, devices, endpoint_segments, segment_vlans, pair_members, issues,
        )
        actions.extend(access_actions)

        gateway_actions, gateway_action_by_segment, router_trunk_links, gateway_devices = (
            self._gateway_actions(
                devices, links, site_segments, segment_vlans,
                allocations, policy, issues,
            )
        )
        actions.extend(gateway_actions)

        trunk_actions, switch_trunk_vlans = self._trunk_actions(
            topology, devices, links, segment_vlans, switch_local_vlans,
            router_trunk_links, policy,
        )
        actions.extend(trunk_actions)

        participating_vlans: dict[str, set[int]] = defaultdict(set)
        for device_id, values in switch_local_vlans.items():
            participating_vlans[device_id].update(values)
        for device_id, values in switch_trunk_vlans.items():
            participating_vlans[device_id].update(values)
        for action in gateway_actions:
            if isinstance(action, ConfigureAccessPort):
                participating_vlans[action.device_id].add(action.data_vlan_id)
            elif isinstance(action, ConfigureSvi):
                participating_vlans[action.device_id].add(action.vlan_id)

        vlan_actions = self._vlan_actions(
            devices, participating_vlans, site_segments, segment_vlans,
        )
        actions.extend(vlan_actions)
        vlan_ids = {(action.device_id, action.vlan_id): action.id for action in vlan_actions}
        for action in actions:
            if isinstance(action, ConfigureAccessPort):
                required = [action.data_vlan_id]
                if action.voice_vlan_id is not None:
                    required.append(action.voice_vlan_id)
                action.depends_on = sorted({
                    vlan_ids[(action.device_id, vlan_id)] for vlan_id in required
                })
            elif isinstance(action, ConfigureTrunk):
                action.depends_on = sorted(
                    vlan_ids[(action.device_id, vlan_id)] for vlan_id in action.allowed_vlans
                )
            elif isinstance(action, ConfigureSvi):
                action.depends_on = [vlan_ids[(action.device_id, action.vlan_id)]]

        endpoint_actions, static_by_segment, pending_dhcp = self._endpoint_actions(
            topology, devices, links, endpoint_segments, allocations,
            endpoint_access, policy, issues,
        )
        actions.extend(endpoint_actions)
        pool_actions, pool_by_segment = self._dhcp_actions(
            devices, site_segments, allocations, pending_dhcp,
            static_by_segment, gateway_action_by_segment, gateway_devices, policy, issues,
        )
        actions.extend(pool_actions)
        for endpoint, segment, interface, access_dependency in pending_dhcp:
            pool = pool_by_segment.get(segment.name)
            if pool is None:
                continue
            allocation = allocations[segment.name]
            dependencies = [pool.id]
            if access_dependency:
                dependencies.append(access_dependency)
            actions.append(SetEndpointDhcp(
                id=_action_id("endpoint-dhcp", _device_key(endpoint), segment.name),
                phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
                device_id=_device_key(endpoint),
                device_name=endpoint.name,
                site_id=endpoint.site_id,
                interface=interface,
                segment_id=segment.name,
                network=allocation.network,
                prefix=allocation.prefix,
                netmask=allocation.netmask,
                gateway=allocation.gateway,
                dns_server=policy.dns_server,
                depends_on=sorted(set(dependencies)),
                required_capability="endpoint_dhcp",
            ))

        issues.extend(validate_configuration_actions(actions))
        if not any(issue.severity is ConfigurationIssueSeverity.ERROR for issue in issues):
            try:
                actions = order_configuration_actions(actions)
            except ConfigurationDependencyError as exc:
                code = (
                    ConfigurationIssueCode.DEPENDENCY_CYCLE
                    if "cycle" in str(exc).casefold()
                    else ConfigurationIssueCode.DEPENDENCY_MISSING
                )
                issues.append(_error(code, str(exc), ",".join(exc.action_ids)))

        if capabilities:
            issues.extend(self._capability_issues(actions, devices, capabilities))
        issues = self._deduplicate_issues(issues)
        if any(issue.severity is ConfigurationIssueSeverity.ERROR for issue in issues):
            return self._result(None, actions, topology, issues)

        expectations = self._expectations(actions)
        for action in actions:
            action.apply_dependencies = list(action.depends_on)
        for expectation in expectations:
            expectation.verification_prerequisites = [VerificationPrerequisite(
                kind=PrerequisiteKind.ACTION_APPLIED,
                reference_id=expectation.action_id,
            )]
        device_plans = self._device_plans(actions, devices)
        plan = ConfigurationPlan(
            id=f"cfg_{topology.id or topology.physical_identity_hash[:16]}",
            source_topology_id=topology.id,
            source_topology_hash=topology.physical_identity_hash,
            source_topology_hash_schema=(
                "physical-topology-v2"
                if topology.physical_topology_hash else "legacy-full-v1"
            ),
            actions=actions,
            devices=device_plans,
            verification_expectations=expectations,
        )
        plan.semantic_hash = self._semantic_hash(plan)
        return self._result(plan, actions, topology, issues)

    @staticmethod
    def _resolved_link(link: LinkPlan, names_to_ids: dict[str, str]) -> LinkPlan:
        result = link.model_copy(deep=True)
        result.device_a_id = result.device_a_id or names_to_ids.get(result.device_a, "")
        result.device_b_id = result.device_b_id or names_to_ids.get(result.device_b, "")
        return result

    @staticmethod
    def _segments(
        enterprise: EnterprisePlan,
        policy: ConfigurationPolicy,
        issues: list[ConfigurationIssue],
    ) -> tuple[dict[tuple[str, SegmentRole], NetworkSegment], dict[str, int]]:
        by_role: dict[tuple[str, SegmentRole], NetworkSegment] = {}
        vlan_by_segment: dict[str, int] = {}
        used: dict[tuple[str, int], str] = {}
        for site in sorted(enterprise.sites, key=lambda item: item.site_id):
            for segment in sorted(site.segments, key=lambda item: (item.role.value, item.name)):
                key = (site.site_id, segment.role)
                if key in by_role and by_role[key].name != segment.name:
                    issues.append(_error(
                        ConfigurationIssueCode.SEGMENT_MAPPING_MISSING,
                        f"Multiple {segment.role.value} segments in {site.site_id} need explicit endpoint mapping.",
                        site.site_id,
                    ))
                    continue
                by_role[key] = segment
                vlan_id = (
                    segment.vlan_id
                    if segment.vlan_id is not None
                    else policy.vlan_ids_by_role.get(segment.role)
                )
                if vlan_id is None:
                    issues.append(_error(
                        ConfigurationIssueCode.VLAN_INVALID_ID,
                        f"No VLAN policy exists for segment {segment.name}.", segment.name,
                    ))
                    continue
                if not 1 <= vlan_id <= 4094 or vlan_id in _RESERVED_VLANS:
                    issues.append(_error(
                        ConfigurationIssueCode.VLAN_INVALID_ID,
                        f"VLAN {vlan_id} is invalid or reserved for segment {segment.name}.",
                        segment.name,
                    ))
                    continue
                used_key = (site.site_id, vlan_id)
                if used_key in used and used[used_key] != segment.name:
                    issues.append(_error(
                        ConfigurationIssueCode.VLAN_ID_CONFLICT,
                        f"VLAN {vlan_id} maps both {used[used_key]} and {segment.name} in {site.site_id}.",
                        site.site_id,
                    ))
                    continue
                used[used_key] = segment.name
                vlan_by_segment[segment.name] = vlan_id
        return by_role, vlan_by_segment

    @staticmethod
    def _endpoint_segments(
        topology: TopologyPlan,
        segments: dict[tuple[str, SegmentRole], NetworkSegment],
        issues: list[ConfigurationIssue],
    ) -> dict[str, NetworkSegment]:
        result: dict[str, NetworkSegment] = {}
        assignment = SegmentAssignmentPolicy()
        for endpoint in sorted(
            (device for device in topology.devices if not device.network_layer),
            key=lambda item: _device_key(item),
        ):
            try:
                role = DeviceRole(endpoint.enterprise_role)
            except ValueError:
                issues.append(_warning(
                    ConfigurationIssueCode.SEGMENT_MAPPING_MISSING,
                    f"Endpoint {endpoint.name} has no recognized Enterprise role.",
                    _device_key(endpoint),
                ))
                continue
            segment_role = assignment.segment_for(EndpointRequirement(
                role=role, count=1, wireless=endpoint.wireless,
            ))
            segment = segments.get((endpoint.site_id, segment_role))
            if segment is None:
                issues.append(_warning(
                    ConfigurationIssueCode.SEGMENT_MAPPING_MISSING,
                    f"No {segment_role.value} segment exists for endpoint {endpoint.name}.",
                    _device_key(endpoint),
                ))
                continue
            result[_device_key(endpoint)] = segment
        return result

    @staticmethod
    def _pair_members(devices: list[DevicePlan]) -> dict[str, dict[str, DevicePlan]]:
        pairs: dict[str, dict[str, DevicePlan]] = defaultdict(dict)
        for device in devices:
            pair_id = device.metadata.get("pair_id", "")
            if pair_id:
                pairs[pair_id][device.enterprise_role] = device
        return pairs

    def _access_actions(
        self,
        topology: TopologyPlan,
        links: list[LinkPlan],
        devices: dict[str, DevicePlan],
        endpoint_segments: dict[str, NetworkSegment],
        segment_vlans: dict[str, int],
        pairs: dict[str, dict[str, DevicePlan]],
        issues: list[ConfigurationIssue],
    ) -> tuple[list[ConfigureAccessPort], dict[str, str], dict[str, set[int]]]:
        actions: list[ConfigureAccessPort] = []
        endpoint_access: dict[str, str] = {}
        switch_vlans: dict[str, set[int]] = defaultdict(set)
        for link in sorted(links, key=lambda item: item.id):
            if link.link_role not in {"endpoint_access", "server_access"}:
                continue
            sides = [
                (link.device_a_id, link.port_a, link.device_b_id, link.port_b),
                (link.device_b_id, link.port_b, link.device_a_id, link.port_a),
            ]
            switch_side = next(
                (side for side in sides if devices.get(side[0]) and devices[side[0]].category == "switch"),
                None,
            )
            if switch_side is None:
                issues.append(_error(
                    ConfigurationIssueCode.ACCESS_LINK_INVALID,
                    f"Access link {link.id} has no concrete switch endpoint.", link.id,
                ))
                continue
            switch_id, switch_port, endpoint_id, endpoint_port = switch_side
            endpoint = devices.get(endpoint_id)
            segment = endpoint_segments.get(endpoint_id)
            if endpoint is None or segment is None or segment.name not in segment_vlans:
                continue
            data_vlan = segment_vlans[segment.name]
            voice_vlan: int | None = None
            endpoint_ids = [endpoint_id]
            pair_id = endpoint.metadata.get("pair_id", "")
            if endpoint.enterprise_role == DeviceRole.IP_PHONE.value and pair_id in pairs:
                pc = pairs[pair_id].get(DeviceRole.USER_PC.value)
                voice_segment = endpoint_segments.get(endpoint_id)
                data_segment = endpoint_segments.get(_device_key(pc)) if pc else None
                if voice_segment and data_segment:
                    voice_vlan = segment_vlans.get(voice_segment.name)
                    paired_data_vlan = segment_vlans.get(data_segment.name)
                    if voice_vlan is None or paired_data_vlan is None:
                        continue
                    data_vlan = paired_data_vlan
                    endpoint_ids.append(_device_key(pc))
            action = ConfigureAccessPort(
                id=_action_id("access", switch_id, switch_port, data_vlan, voice_vlan or ""),
                phase=ConfigurationPhase.L2_INTERFACES,
                device_id=switch_id,
                device_name=devices[switch_id].name,
                site_id=devices[switch_id].site_id,
                interface=switch_port,
                data_vlan_id=data_vlan,
                voice_vlan_id=voice_vlan,
                endpoint_ids=sorted(endpoint_ids),
                required_capability="supports_vlan",
            )
            actions.append(action)
            switch_vlans[switch_id].add(data_vlan)
            if voice_vlan is not None:
                switch_vlans[switch_id].add(voice_vlan)
            endpoint_access[endpoint_id] = action.id
            endpoint_access[f"interface:{endpoint_id}"] = endpoint_port
            for member_id in endpoint_ids:
                endpoint_access[member_id] = action.id
        return actions, endpoint_access, switch_vlans

    def _gateway_actions(
        self,
        devices: dict[str, DevicePlan],
        links: list[LinkPlan],
        site_segments: dict[tuple[str, SegmentRole], NetworkSegment],
        segment_vlans: dict[str, int],
        allocations: dict[str, SubnetAllocation],
        policy: ConfigurationPolicy,
        issues: list[ConfigurationIssue],
    ) -> tuple[list[ConfigurationAction], dict[str, str], set[str], dict[str, DevicePlan]]:
        actions: list[ConfigurationAction] = []
        by_segment: dict[str, str] = {}
        router_trunks: set[str] = set()
        gateway_devices: dict[str, DevicePlan] = {}
        segments_by_site: dict[str, list[NetworkSegment]] = defaultdict(list)
        for (site_id, _), segment in site_segments.items():
            if segment.name in allocations and segment.name in segment_vlans:
                segments_by_site[site_id].append(segment)

        for site_id, segments in sorted(segments_by_site.items()):
            gateway = self._select_gateway(site_id, devices, policy)
            if gateway is None:
                issues.append(_warning(
                    ConfigurationIssueCode.GATEWAY_DEVICE_MISSING,
                    f"No gateway device was selected for addressed site {site_id}.", site_id,
                ))
                continue
            gateway_devices[site_id] = gateway
            if gateway.category == "switch":
                for segment in sorted(segments, key=lambda item: item.name):
                    allocation = allocations[segment.name]
                    if not self._valid_gateway(allocation):
                        issues.append(_error(
                            ConfigurationIssueCode.GATEWAY_INVALID,
                            f"Gateway {allocation.gateway} is not usable in {allocation.network}/{allocation.prefix}.",
                            segment.name,
                        ))
                        continue
                    action = ConfigureSvi(
                        id=_action_id("svi", _device_key(gateway), segment.name),
                        phase=ConfigurationPhase.L3_INTERFACES,
                        device_id=_device_key(gateway), device_name=gateway.name,
                        site_id=site_id, vlan_id=segment_vlans[segment.name],
                        ipv4=allocation.gateway, prefix=allocation.prefix,
                        netmask=allocation.netmask, segment_id=segment.name,
                        required_capability="supports_svi",
                    )
                    actions.append(action)
                    by_segment[segment.name] = action.id
                continue

            gateway_links = sorted(
                (
                    link for link in links
                    if _device_key(gateway) in {link.device_a_id, link.device_b_id}
                    and any(
                        devices.get(device_id) and devices[device_id].category == "switch"
                        for device_id in {link.device_a_id, link.device_b_id}
                    )
                ),
                key=lambda item: item.id,
            )
            if not gateway_links:
                issues.append(_error(
                    ConfigurationIssueCode.GATEWAY_INTERFACE_MISSING,
                    f"Gateway {gateway.name} has no E4 link to a switch.", _device_key(gateway),
                ))
                continue
            gateway_link = gateway_links[0]
            gateway_port = (
                gateway_link.port_a if gateway_link.device_a_id == _device_key(gateway)
                else gateway_link.port_b
            )
            if len(segments) == 1:
                segment = segments[0]
                allocation = allocations[segment.name]
                if not self._valid_gateway(allocation):
                    issues.append(_error(
                        ConfigurationIssueCode.GATEWAY_INVALID,
                        f"Gateway {allocation.gateway} is not usable in {allocation.network}/{allocation.prefix}.",
                        segment.name,
                    ))
                    continue
                action = ConfigureRoutedInterface(
                    id=_action_id("routed", _device_key(gateway), gateway_port, segment.name),
                    phase=ConfigurationPhase.L3_INTERFACES,
                    device_id=_device_key(gateway), device_name=gateway.name,
                    site_id=site_id, interface=gateway_port,
                    ipv4=allocation.gateway, prefix=allocation.prefix,
                    netmask=allocation.netmask, segment_id=segment.name,
                    required_capability="layer3",
                )
                actions.append(action)
                by_segment[segment.name] = action.id
                switch_id = (
                    gateway_link.device_b_id
                    if gateway_link.device_a_id == _device_key(gateway)
                    else gateway_link.device_a_id
                )
                switch_port = (
                    gateway_link.port_b
                    if gateway_link.device_a_id == _device_key(gateway)
                    else gateway_link.port_a
                )
                switch = devices[switch_id]
                actions.append(ConfigureAccessPort(
                    id=_action_id("gateway-access", switch_id, switch_port, segment.name),
                    phase=ConfigurationPhase.L2_INTERFACES,
                    device_id=switch_id, device_name=switch.name, site_id=site_id,
                    interface=switch_port, data_vlan_id=segment_vlans[segment.name],
                    endpoint_ids=[], required_capability="supports_vlan",
                ))
            else:
                router_trunks.add(gateway_link.id)
                for segment in sorted(segments, key=lambda item: item.name):
                    allocation = allocations[segment.name]
                    if not self._valid_gateway(allocation):
                        issues.append(_error(
                            ConfigurationIssueCode.GATEWAY_INVALID,
                            f"Gateway {allocation.gateway} is not usable in {allocation.network}/{allocation.prefix}.",
                            segment.name,
                        ))
                        continue
                    action = ConfigureSubinterface(
                        id=_action_id("subinterface", _device_key(gateway), gateway_port, segment.name),
                        phase=ConfigurationPhase.L3_INTERFACES,
                        device_id=_device_key(gateway), device_name=gateway.name,
                        site_id=site_id, parent_interface=gateway_port,
                        vlan_id=segment_vlans[segment.name], ipv4=allocation.gateway,
                        prefix=allocation.prefix, netmask=allocation.netmask,
                        segment_id=segment.name, required_capability="layer3",
                    )
                    actions.append(action)
                    by_segment[segment.name] = action.id
        return actions, by_segment, router_trunks, gateway_devices

    @staticmethod
    def _select_gateway(
        site_id: str, devices: dict[str, DevicePlan], policy: ConfigurationPolicy,
    ) -> DevicePlan | None:
        explicit = policy.gateway_device_ids.get(site_id)
        if explicit:
            return devices.get(explicit)
        candidates = [
            device for device in devices.values()
            if device.site_id == site_id and device.network_layer
            and (device.category == "router" or device.enterprise_role in _GATEWAY_ROLE_ORDER)
        ]
        return min(
            candidates,
            key=lambda item: (
                _GATEWAY_ROLE_ORDER.get(item.enterprise_role, 99), _device_key(item),
            ),
            default=None,
        )

    @staticmethod
    def _valid_gateway(allocation: SubnetAllocation) -> bool:
        network = ipaddress.ip_network(f"{allocation.network}/{allocation.prefix}")
        gateway = ipaddress.ip_address(allocation.gateway)
        return gateway in network and gateway not in {network.network_address, network.broadcast_address}

    def _trunk_actions(
        self,
        topology: TopologyPlan,
        devices: dict[str, DevicePlan],
        links: list[LinkPlan],
        segment_vlans: dict[str, int],
        local_vlans: dict[str, set[int]],
        router_trunk_links: set[str],
        policy: ConfigurationPolicy,
    ) -> tuple[list[ConfigureTrunk], dict[str, set[int]]]:
        actions: list[ConfigureTrunk] = []
        switch_vlans: dict[str, set[int]] = defaultdict(set)
        site_vlans: dict[str, set[int]] = defaultdict(set)
        for device in topology.devices:
            if device.site_id:
                site_vlans[device.site_id].update(
                    segment_vlans.values() if len({item.site_id for item in topology.devices}) == 1 else []
                )
        # For multiple sites, derive from segment names through the already-local sets;
        # upper-layer trunks conservatively carry the union required inside that site.
        for device_id, values in local_vlans.items():
            if device_id in devices:
                site_vlans[devices[device_id].site_id].update(values)

        for link in sorted(links, key=lambda item: item.id):
            endpoint_devices = [devices.get(link.device_a_id), devices.get(link.device_b_id)]
            switches = [device for device in endpoint_devices if device and device.category == "switch"]
            should_trunk = (
                len(switches) == 2 and link.link_role in _TRUNK_LINK_ROLES
            ) or link.id in router_trunk_links
            if not should_trunk:
                continue
            access_switch = next(
                (device for device in switches if device.network_layer == "access"), None,
            )
            allowed = sorted(
                local_vlans.get(_device_key(access_switch), set())
                if access_switch is not None
                else site_vlans.get(switches[0].site_id, set())
            )
            for switch in switches:
                switch_id = _device_key(switch)
                interface = link.port_a if link.device_a_id == switch_id else link.port_b
                peer = link.device_b_id if link.device_a_id == switch_id else link.device_a_id
                action = ConfigureTrunk(
                    id=_action_id("trunk", switch_id, interface, link.id),
                    phase=ConfigurationPhase.L2_INTERFACES,
                    device_id=switch_id, device_name=switch.name, site_id=switch.site_id,
                    interface=interface, allowed_vlans=allowed,
                    native_vlan_id=policy.native_vlan_id,
                    peer_device_id=peer, source_link_id=link.id,
                    required_capability="supports_trunk",
                )
                actions.append(action)
                switch_vlans[switch_id].update(allowed)
        return actions, switch_vlans

    def _vlan_actions(
        self,
        devices: dict[str, DevicePlan],
        participating: dict[str, set[int]],
        site_segments: dict[tuple[str, SegmentRole], NetworkSegment],
        segment_vlans: dict[str, int],
    ) -> list[CreateVlan]:
        names = {
            (segment.site, segment_vlans[segment.name]): segment
            for segment in site_segments.values()
            if segment.name in segment_vlans
        }
        actions: list[CreateVlan] = []
        for device_id, vlan_ids in sorted(participating.items()):
            device = devices[device_id]
            for vlan_id in sorted(vlan_ids):
                segment = names.get((device.site_id, vlan_id))
                actions.append(CreateVlan(
                    id=_action_id("vlan", device_id, vlan_id),
                    phase=ConfigurationPhase.L2_DEFINITIONS,
                    device_id=device_id, device_name=device.name, site_id=device.site_id,
                    vlan_id=vlan_id, name=segment.name if segment else f"VLAN_{vlan_id}",
                    segment_id=segment.name if segment else "",
                    required_capability="supports_vlan",
                ))
        return actions

    def _endpoint_actions(
        self,
        topology: TopologyPlan,
        devices: dict[str, DevicePlan],
        links: list[LinkPlan],
        endpoint_segments: dict[str, NetworkSegment],
        allocations: dict[str, SubnetAllocation],
        endpoint_access: dict[str, str],
        policy: ConfigurationPolicy,
        issues: list[ConfigurationIssue],
    ) -> tuple[
        list[SetEndpointStaticAddress], dict[str, list[str]],
        list[tuple[DevicePlan, NetworkSegment, str, str]],
    ]:
        actions: list[SetEndpointStaticAddress] = []
        static_by_segment: dict[str, list[str]] = defaultdict(list)
        pending_dhcp: list[tuple[DevicePlan, NetworkSegment, str, str]] = []
        endpoint_interfaces = self._endpoint_interfaces(links, devices)
        endpoints_by_segment: dict[str, list[DevicePlan]] = defaultdict(list)
        for endpoint_id, segment in endpoint_segments.items():
            endpoint = devices.get(endpoint_id)
            if endpoint and segment.name in allocations:
                endpoints_by_segment[segment.name].append(endpoint)
            elif endpoint:
                issues.append(_warning(
                    ConfigurationIssueCode.SEGMENT_ALLOCATION_MISSING,
                    f"No IPAM allocation exists for segment {segment.name}; L2 still compiles.",
                    segment.name,
                ))

        for segment_id, endpoints in sorted(endpoints_by_segment.items()):
            allocation = allocations[segment_id]
            network = ipaddress.ip_network(f"{allocation.network}/{allocation.prefix}")
            reserved = {ipaddress.ip_address(allocation.gateway)}
            next_hosts = (host for host in network.hosts() if host not in reserved)
            for endpoint in sorted(endpoints, key=_device_key):
                endpoint_id = _device_key(endpoint)
                segment = endpoint_segments[endpoint_id]
                interface = endpoint_interfaces.get(endpoint_id, "")
                preference = endpoint.metadata.get("addressing_preference", "unspecified")
                use_dhcp = preference == AddressingPreference.DHCP.value or (
                    preference == AddressingPreference.UNSPECIFIED.value and segment.dhcp
                )
                access_dependency = endpoint_access.get(endpoint_id, "")
                if use_dhcp:
                    pending_dhcp.append((endpoint, segment, interface, access_dependency))
                    continue
                explicit = endpoint.metadata.get("requirement.ipv4", "")
                if explicit:
                    try:
                        address = ipaddress.ip_address(explicit)
                    except ValueError:
                        issues.append(_error(
                            ConfigurationIssueCode.DUPLICATE_IPV4,
                            f"Endpoint {endpoint.name} carries invalid explicit IPv4 {explicit}.",
                            endpoint_id,
                        ))
                        continue
                    if address not in network or address in {
                        network.network_address, network.broadcast_address,
                    }:
                        issues.append(_error(
                            ConfigurationIssueCode.ADDRESS_SPACE_EXHAUSTED,
                            f"Explicit IPv4 {address} is outside usable segment {segment_id}.",
                            endpoint_id,
                        ))
                        continue
                else:
                    try:
                        address = next(next_hosts)
                    except StopIteration:
                        issues.append(_error(
                            ConfigurationIssueCode.ADDRESS_SPACE_EXHAUSTED,
                            f"Segment {segment_id} has no free static address for {endpoint.name}.",
                            segment_id,
                        ))
                        continue
                static_by_segment[segment_id].append(str(address))
                dependencies = [access_dependency] if access_dependency else []
                actions.append(SetEndpointStaticAddress(
                    id=_action_id("endpoint-static", endpoint_id, segment_id),
                    phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
                    device_id=endpoint_id, device_name=endpoint.name, site_id=endpoint.site_id,
                    interface=interface, ipv4=str(address), netmask=allocation.netmask,
                    gateway=allocation.gateway, dns_server=policy.dns_server,
                    segment_id=segment_id, depends_on=dependencies,
                    required_capability="endpoint_static_ipv4",
                ))
        return actions, static_by_segment, pending_dhcp

    @staticmethod
    def _endpoint_interfaces(
        links: list[LinkPlan], devices: dict[str, DevicePlan],
    ) -> dict[str, str]:
        interfaces: dict[str, str] = {}
        priorities = {"endpoint_access": 0, "server_access": 0, "phone_passthrough": 1}
        for link in sorted(links, key=lambda item: (priorities.get(item.link_role, 9), item.id)):
            for device_id, port in (
                (link.device_a_id, link.port_a), (link.device_b_id, link.port_b),
            ):
                device = devices.get(device_id)
                if device and not device.network_layer:
                    interface = (
                        "Vlan1"
                        if device.enterprise_role == DeviceRole.IP_PHONE.value
                        else port
                    )
                    interfaces.setdefault(device_id, interface)
        return interfaces

    def _dhcp_actions(
        self,
        devices: dict[str, DevicePlan],
        site_segments: dict[tuple[str, SegmentRole], NetworkSegment],
        allocations: dict[str, SubnetAllocation],
        pending: list[tuple[DevicePlan, NetworkSegment, str, str]],
        static_by_segment: dict[str, list[str]],
        gateway_actions: dict[str, str],
        gateway_devices: dict[str, DevicePlan],
        policy: ConfigurationPolicy,
        issues: list[ConfigurationIssue],
    ) -> tuple[list[ConfigureDhcpPool], dict[str, ConfigureDhcpPool]]:
        actions: list[ConfigureDhcpPool] = []
        by_segment: dict[str, ConfigureDhcpPool] = {}
        requested = {segment.name for _, segment, _, _ in pending}
        for segment in sorted(site_segments.values(), key=lambda item: item.name):
            if segment.name not in requested or segment.name not in allocations:
                continue
            server_id = policy.dhcp_server_device_ids.get(segment.site)
            server = devices.get(server_id) if server_id else gateway_devices.get(segment.site)
            if server is None:
                issues.append(_error(
                    ConfigurationIssueCode.DHCP_SERVER_MISSING,
                    f"No DHCP server device exists for segment {segment.name}.", segment.name,
                ))
                continue
            allocation = allocations[segment.name]
            network = ipaddress.ip_network(f"{allocation.network}/{allocation.prefix}")
            excluded_values = sorted({
                ipaddress.ip_address(allocation.gateway),
                *(ipaddress.ip_address(value) for value in static_by_segment.get(segment.name, [])),
            })
            excluded_ranges = self._collapse_ranges(excluded_values)
            dynamic = [
                host for host in network.hosts()
                if not any(
                    ipaddress.ip_address(item.start) <= host <= ipaddress.ip_address(item.end)
                    for item in excluded_ranges
                )
            ]
            if not dynamic:
                issues.append(_error(
                    ConfigurationIssueCode.ADDRESS_SPACE_EXHAUSTED,
                    f"DHCP segment {segment.name} has no dynamic address left.", segment.name,
                ))
                continue
            dependency = gateway_actions.get(segment.name, "")
            action = ConfigureDhcpPool(
                id=_action_id("dhcp", _device_key(server), segment.name),
                phase=ConfigurationPhase.SERVICES,
                device_id=_device_key(server), device_name=server.name, site_id=segment.site,
                pool_name=f"{segment.site}_{segment.role.value}".upper(),
                segment_id=segment.name, network=allocation.network,
                prefix=allocation.prefix, netmask=allocation.netmask,
                gateway=allocation.gateway, dns_server=policy.dns_server,
                excluded_ranges=excluded_ranges,
                lease_start=str(dynamic[0]), lease_end=str(dynamic[-1]),
                depends_on=[dependency] if dependency else [],
                required_capability="supports_dhcp_server",
            )
            actions.append(action)
            by_segment[segment.name] = action
        return actions, by_segment

    @staticmethod
    def _collapse_ranges(values: list[ipaddress.IPv4Address]) -> list[AddressRange]:
        if not values:
            return []
        ranges: list[AddressRange] = []
        start = previous = values[0]
        for value in values[1:]:
            if int(value) == int(previous) + 1:
                previous = value
                continue
            ranges.append(AddressRange(start=str(start), end=str(previous)))
            start = previous = value
        ranges.append(AddressRange(start=str(start), end=str(previous)))
        return ranges

    @staticmethod
    def _capability_issues(
        actions: list[ConfigurationAction],
        devices: dict[str, DevicePlan],
        capabilities: dict[str, DeviceCapabilities],
    ) -> list[ConfigurationIssue]:
        issues: list[ConfigurationIssue] = []
        reported: set[tuple[str, str]] = set()
        for action in actions:
            if not action.required_capability or action.required_capability.startswith("endpoint_"):
                continue
            device = devices.get(action.device_id)
            profile = capabilities.get(device.model) if device else None
            status = getattr(profile, action.required_capability, CapabilityStatus.UNKNOWN) if profile else CapabilityStatus.UNKNOWN
            key = (action.device_id, action.required_capability)
            if key in reported or status is CapabilityStatus.SUPPORTED:
                continue
            reported.add(key)
            code = (
                ConfigurationIssueCode.CAPABILITY_UNSUPPORTED
                if status is CapabilityStatus.UNSUPPORTED
                else ConfigurationIssueCode.CAPABILITY_UNVERIFIED
            )
            issues.append(_warning(
                code,
                f"{action.device_name}: runtime capability {action.required_capability} is {status.value}.",
                action.device_id,
            ))
        return issues

    @staticmethod
    def _expectations(actions: list[ConfigurationAction]) -> list[VerificationExpectation]:
        expectations: list[VerificationExpectation] = []
        for action in actions:
            kind: VerificationKind
            query = ""
            expected: dict[str, str | int | bool | list[int]] = {}
            if isinstance(action, CreateVlan):
                kind = VerificationKind.VLAN
                expected = {"vlan_id": action.vlan_id}
            elif isinstance(action, ConfigureAccessPort):
                kind = VerificationKind.ACCESS_PORT
                expected = {"interface": action.interface, "vlan_id": action.data_vlan_id}
            elif isinstance(action, ConfigureTrunk):
                kind = VerificationKind.TRUNK
                query = "show_interfaces_trunk"
                expected = {"interface": action.interface, "allowed_vlans": action.allowed_vlans}
            elif isinstance(action, (ConfigureRoutedInterface, ConfigureSvi, ConfigureSubinterface)):
                kind = VerificationKind.L3_INTERFACE
                query = "show_ip_interface_brief"
                interface = (
                    action.interface if isinstance(action, ConfigureRoutedInterface)
                    else f"Vlan{action.vlan_id}" if isinstance(action, ConfigureSvi)
                    else f"{action.parent_interface}.{action.vlan_id}"
                )
                expected = {
                    "interface": interface,
                    "ipv4": action.ipv4,
                    "administrative_up": getattr(action, "administrative_up", True),
                }
            elif isinstance(action, ConfigureDhcpPool):
                kind = VerificationKind.DHCP_POOL
                expected = {"network": action.network, "gateway": action.gateway}
            else:
                kind = VerificationKind.ENDPOINT_ADDRESSING
                expected = {"mode": "dhcp" if isinstance(action, SetEndpointDhcp) else "static"}
                if isinstance(action, SetEndpointDhcp):
                    expected.update({
                        "network": action.network,
                        "prefix": action.prefix,
                        "netmask": action.netmask,
                        "gateway": action.gateway,
                        "dns": action.dns_server or "",
                    })
                elif isinstance(action, SetEndpointStaticAddress):
                    expected.update({"ipv4": action.ipv4, "netmask": action.netmask})
            expectations.append(VerificationExpectation(
                id=_action_id("verify", action.id), action_id=action.id, kind=kind,
                device_id=action.device_id, device_name=action.device_name,
                expected=expected, required_query=query,
            ))
        return expectations

    @staticmethod
    def _device_plans(
        actions: list[ConfigurationAction], devices: dict[str, DevicePlan],
    ) -> list[DeviceConfigurationPlan]:
        grouped: dict[str, list[ConfigurationAction]] = defaultdict(list)
        for action in actions:
            grouped[action.device_id].append(action)
        return [
            DeviceConfigurationPlan(
                device_id=device_id,
                device_name=items[0].device_name,
                model=devices[device_id].model,
                site_id=items[0].site_id,
                action_ids=[item.id for item in items],
                required_capabilities=sorted({
                    item.required_capability for item in items if item.required_capability
                }),
            )
            for device_id, items in sorted(grouped.items())
        ]

    @staticmethod
    def _semantic_hash(plan: ConfigurationPlan) -> str:
        payload = plan.model_dump(mode="json")
        payload["semantic_hash"] = ""
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _deduplicate_issues(issues: list[ConfigurationIssue]) -> list[ConfigurationIssue]:
        unique = {
            (issue.severity.value, issue.code.value, issue.subject, issue.message): issue
            for issue in issues
        }
        return [unique[key] for key in sorted(unique)]

    @staticmethod
    def _result(
        plan: ConfigurationPlan | None,
        actions: list[ConfigurationAction],
        topology: TopologyPlan,
        issues: list[ConfigurationIssue],
    ) -> ConfigurationCompileResult:
        counts = action_type_counts(actions)
        summary = ConfigurationCompileSummary(
            config_plan_id=plan.id if plan else "",
            semantic_hash=plan.semantic_hash if plan else "",
            source_topology_hash=topology.physical_identity_hash,
            source_topology_hash_schema=(
                "physical-topology-v2"
                if topology.physical_topology_hash else "legacy-full-v1"
            ),
            devices=len({action.device_id for action in actions}),
            endpoint_devices=len({
                action.device_id for action in actions
                if isinstance(action, (SetEndpointStaticAddress, SetEndpointDhcp))
            }),
            action_count=len(actions),
            actions_by_type=counts,
            verification_expectations=len(plan.verification_expectations) if plan else 0,
            warnings=sum(issue.severity is ConfigurationIssueSeverity.WARNING for issue in issues),
            errors=sum(issue.severity is ConfigurationIssueSeverity.ERROR for issue in issues),
        )
        return ConfigurationCompileResult(
            plan=plan,
            semantic_hash=plan.semantic_hash if plan else "",
            summary=summary,
            issues=issues,
        )
