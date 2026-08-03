"""E8: E4 + E5 + E6/E7 semantics -> deterministic SecurityPlan."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections import defaultdict

from ...models.plans import DevicePlan, LinkPlan, TopologyPlan
from ..models.configuration import (
    ConfigurationIssue,
    ConfigurationIssueCode,
    ConfigurationIssueSeverity,
    ConfigurationPlan,
    ConfigureAccessPort,
    ConfigureDhcpPool,
    ConfigureRoutedInterface,
    ConfigureSubinterface,
    ConfigureSvi,
    CreateVlan,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
)
from ..models.security_plan import (
    AddSecurityAclRule,
    ApplyDeviceHardening,
    AttachSecurityAcl,
    ConfigureDhcpSnooping,
    ConfigureDynamicArpInspection,
    ConfigureEndpointPortSecurity,
    ConfigureSecurityNat,
    CompiledDynamicNatPool,
    CompiledStaticNatMapping,
    DhcpInspectionPolicyIntent,
    NatMode,
    SecurityAction,
    SecurityCapabilityDimension,
    SecurityCapabilityProfile,
    SecurityCapabilityStatus,
    SecurityCompileResult,
    SecurityCompileSummary,
    SecurityDecision,
    SecurityFoundationRequirement,
    SecurityIntent,
    SecurityPhase,
    SecurityPlan,
    SecurityPolicyIntent,
    SecurityProbeKind,
    SecurityVerificationExpectation,
    SecurityVerificationKind,
    security_action_type_counts,
    security_verification_capability,
)
from ..models.service_plan import ServiceDefinition, ServicePlan, ServiceType
from ..models.voice_plan import CallControlInstance, VoicePlan
from .configuration_dependencies import (
    ConfigurationDependencyError,
    order_dependency_actions,
)


_TOKEN_RE = re.compile(r"[^a-z0-9]+")
_TRUSTED_LINK_ROLES = ("uplink", "trunk", "core", "distribution")
_ACL_PROTOCOLS = {"ip", "icmp", "tcp", "udp", "udp/tcp"}
_SAFE_BANNER_RE = re.compile(r"^[\x20-\x7E]{0,256}$")


def _issue(
    severity: ConfigurationIssueSeverity,
    code: ConfigurationIssueCode,
    message: str,
    subject: str = "",
    **details: str | int | bool,
) -> ConfigurationIssue:
    return ConfigurationIssue(
        severity=severity,
        code=code,
        message=message,
        subject=subject,
        details=details,
    )


def _error(
    code: ConfigurationIssueCode,
    message: str,
    subject: str = "",
    **details: str | int | bool,
) -> ConfigurationIssue:
    return _issue(ConfigurationIssueSeverity.ERROR, code, message, subject, **details)


def _warning(
    code: ConfigurationIssueCode,
    message: str,
    subject: str = "",
    **details: str | int | bool,
) -> ConfigurationIssue:
    return _issue(ConfigurationIssueSeverity.WARNING, code, message, subject, **details)


def _stable_id(kind: str, *parts: object) -> str:
    semantic = "|".join((kind, *(str(part) for part in parts)))
    digest = hashlib.sha256(semantic.encode("utf-8")).hexdigest()[:16]
    return f"sec/{kind}/{digest}"


def _token(value: str) -> str:
    return _TOKEN_RE.sub("-", value.casefold()).strip("-") or "security"


def _device_id(device: DevicePlan) -> str:
    return device.id or device.name


def _interface_of(action: object) -> str:
    if isinstance(action, ConfigureSubinterface):
        return f"{action.parent_interface}.{action.vlan_id}"
    if isinstance(action, ConfigureSvi):
        return f"Vlan{action.vlan_id}"
    if isinstance(action, ConfigureRoutedInterface):
        return action.interface
    return ""


def _network_of(action: object) -> str:
    if isinstance(action, (ConfigureRoutedInterface, ConfigureSvi, ConfigureSubinterface)):
        return str(ipaddress.ip_interface(f"{action.ipv4}/{action.prefix}").network)
    if isinstance(action, ConfigureDhcpPool):
        return str(ipaddress.ip_network(f"{action.network}/{action.prefix}", strict=False))
    if isinstance(action, SetEndpointDhcp):
        return str(ipaddress.ip_network(f"{action.network}/{action.prefix}", strict=False))
    if isinstance(action, SetEndpointStaticAddress):
        return str(ipaddress.ip_interface(f"{action.ipv4}/{action.netmask}").network)
    return ""


class SecurityCompiler:
    """Compila seguridad sin CLI, JavaScript, UI ni objetos de Packet Tracer."""

    def compile(
        self,
        intent: SecurityIntent,
        topology: TopologyPlan,
        configuration: ConfigurationPlan,
        *,
        service_plan: ServicePlan | None = None,
        voice_plan: VoicePlan | None = None,
        capabilities: dict[str, SecurityCapabilityProfile] | None = None,
    ) -> SecurityCompileResult:
        issues: list[ConfigurationIssue] = []
        capabilities = capabilities or {}
        self._validate_sources(
            intent, topology, configuration, service_plan, voice_plan, issues,
        )
        self._validate_intent(intent, issues)

        devices = {_device_id(item): item for item in topology.devices}
        devices_by_name = {item.name: item for item in topology.devices}
        segment_l3, segment_networks = self._segment_l3(configuration)
        endpoints, endpoint_addresses = self._endpoints(configuration)
        vlans = self._vlans(configuration)
        services = {item.id: item for item in service_plan.services} if service_plan else {}
        call_controls = {
            item.id: item for item in voice_plan.call_controls
        } if voice_plan else {}

        self._analyze_policy_conflicts(intent.policies, issues)
        resolved = self._resolve_policies(
            intent.policies,
            services,
            call_controls,
            segment_l3,
            segment_networks,
            endpoints,
            endpoint_addresses,
            devices,
            issues,
        )

        actions: list[SecurityAction] = []
        expectations: list[SecurityVerificationExpectation] = []
        foundations: dict[str, SecurityFoundationRequirement] = {}
        acl_actions, acl_expectations = self._acl_actions(
            resolved, intent.default_decision, devices, foundations, issues,
        )
        actions.extend(acl_actions)
        expectations.extend(acl_expectations)

        nat_actions, nat_expectations = self._nat_actions(
            intent, topology, configuration, devices, segment_l3,
            segment_networks, endpoint_addresses, foundations, issues,
        )
        actions.extend(nat_actions)
        expectations.extend(nat_expectations)

        port_actions, port_expectations = self._port_security_actions(
            intent, topology, configuration, devices, devices_by_name,
            endpoint_addresses, foundations, issues,
        )
        actions.extend(port_actions)
        expectations.extend(port_expectations)

        inspection_actions, inspection_expectations = self._inspection_actions(
            intent.dhcp_inspection, topology, devices, devices_by_name,
            vlans, foundations, issues,
        )
        actions.extend(inspection_actions)
        expectations.extend(inspection_expectations)

        hardening_actions, hardening_expectations = self._hardening_actions(
            intent, devices, foundations, issues,
        )
        actions.extend(hardening_actions)
        expectations.extend(hardening_expectations)

        self._gate_capabilities(actions, expectations, capabilities, issues)
        try:
            actions = order_dependency_actions(actions)
        except ConfigurationDependencyError as exc:
            issues.append(_error(
                ConfigurationIssueCode.DEPENDENCY_CYCLE,
                str(exc),
                ",".join(exc.action_ids),
            ))

        issues = self._deduplicate_issues(issues)
        has_errors = any(
            item.severity is ConfigurationIssueSeverity.ERROR for item in issues
        )
        plan: SecurityPlan | None = None
        if not has_errors:
            service_consumed = any(item.destination_service_id for item in intent.policies)
            voice_consumed = any(
                item.destination_call_control_id for item in intent.policies
            )
            plan = SecurityPlan(
                id=f"security_{topology.id or topology.semantic_hash[:16]}",
                default_decision=intent.default_decision,
                source_topology_id=topology.id,
                source_topology_hash=topology.semantic_hash,
                source_configuration_id=configuration.id,
                source_configuration_hash=configuration.semantic_hash,
                source_service_id=service_plan.id if service_consumed and service_plan else "",
                source_service_hash=(
                    service_plan.semantic_hash if service_consumed and service_plan else ""
                ),
                source_voice_id=voice_plan.id if voice_consumed and voice_plan else "",
                source_voice_hash=(
                    voice_plan.semantic_hash if voice_consumed and voice_plan else ""
                ),
                actions=actions,
                foundational_requirements=sorted(
                    foundations.values(), key=lambda item: item.id,
                ),
                verification_expectations=sorted(
                    expectations,
                    key=lambda item: (item.kind.value, item.policy_id, item.id),
                ),
            )
            plan.semantic_hash = self._semantic_hash(plan)
        return self._result(plan, intent, actions, expectations, topology, configuration, issues)

    @staticmethod
    def _validate_intent(
        intent: SecurityIntent,
        issues: list[ConfigurationIssue],
    ) -> None:
        for policy in intent.policies:
            destinations = sum(bool(item) for item in (
                policy.destination_segment_id,
                policy.destination_service_id,
                policy.destination_call_control_id,
            ))
            if destinations > 1:
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_INTENT_INVALID,
                    "A policy must select exactly one semantic destination kind.",
                    policy.id,
                ))
            if policy.protocol.casefold() not in _ACL_PROTOCOLS:
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_INTENT_INVALID,
                    f"Protocol {policy.protocol!r} is not an allowed typed protocol.",
                    policy.id,
                ))
            if any(port < 1 or port > 65535 for port in (
                *policy.source_ports, *policy.destination_ports,
            )):
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_INTENT_INVALID,
                    "Security policy ports must be between 1 and 65535.",
                    policy.id,
                ))
            if (
                (policy.source_ports or policy.destination_ports)
                and policy.protocol.casefold() not in {"tcp", "udp", "udp/tcp"}
                and not policy.destination_service_id
                and not policy.destination_call_control_id
            ):
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_INTENT_INVALID,
                    "Port constraints require a typed TCP or UDP protocol.",
                    policy.id,
                ))
        for policy in intent.nat_policies:
            if policy.mode is NatMode.STATIC and not policy.static_mappings:
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_NAT_INVALID,
                    "Static NAT requires at least one typed endpoint mapping.",
                    policy.id,
                ))
            if policy.mode is NatMode.DYNAMIC and policy.dynamic_pool is None:
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_NAT_INVALID,
                    "Dynamic NAT requires an explicit typed address pool.",
                    policy.id,
                ))
            if policy.mode is NatMode.PAT and (
                policy.static_mappings or policy.dynamic_pool is not None
            ):
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_NAT_INVALID,
                    "Interface PAT cannot carry static mappings or a dynamic pool.",
                    policy.id,
                ))
        for policy in intent.port_security:
            if policy.max_macs < 1 or policy.max_macs > 132:
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_INTENT_INVALID,
                    "Port-security maximum must be between 1 and 132.",
                    policy.id,
                ))
        for policy in intent.hardening:
            if not _SAFE_BANNER_RE.fullmatch(policy.banner_motd) or "#" in policy.banner_motd:
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_INTENT_INVALID,
                    "Hardening banner contains an unsafe delimiter or control character.",
                    policy.id,
                ))

    @staticmethod
    def _validate_sources(
        intent: SecurityIntent,
        topology: TopologyPlan,
        configuration: ConfigurationPlan,
        service_plan: ServicePlan | None,
        voice_plan: VoicePlan | None,
        issues: list[ConfigurationIssue],
    ) -> None:
        if not topology.semantic_hash or not configuration.semantic_hash:
            issues.append(_error(
                ConfigurationIssueCode.SECURITY_SOURCE_HASH_MISSING,
                "E8 requires immutable E4 and E5 semantic hashes.",
                intent.id,
            ))
        if configuration.source_topology_hash != topology.semantic_hash:
            issues.append(_error(
                ConfigurationIssueCode.SECURITY_SOURCE_MISMATCH,
                "The E5 ConfigurationPlan was compiled for a different E4 topology.",
                configuration.id,
            ))
        needs_services = any(item.destination_service_id for item in intent.policies)
        if needs_services and service_plan is None:
            issues.append(_error(
                ConfigurationIssueCode.SECURITY_SERVICE_MISSING,
                "A semantic service policy requires its E6 ServicePlan.",
                intent.id,
            ))
        if service_plan and (
            service_plan.source_topology_hash != topology.semantic_hash
            or service_plan.source_configuration_hash != configuration.semantic_hash
            or not service_plan.semantic_hash
        ):
            issues.append(_error(
                ConfigurationIssueCode.SECURITY_SOURCE_MISMATCH,
                "The E6 ServicePlan does not match the E4/E5 sources.",
                service_plan.id,
            ))
        needs_voice = any(item.destination_call_control_id for item in intent.policies)
        if needs_voice and voice_plan is None:
            issues.append(_error(
                ConfigurationIssueCode.SECURITY_VOICE_DEPENDENCY_MISSING,
                "A semantic voice policy requires its E7 VoicePlan.",
                intent.id,
            ))
        if voice_plan and (
            voice_plan.source_topology_hash != topology.semantic_hash
            or voice_plan.source_configuration_hash != configuration.semantic_hash
            or not voice_plan.semantic_hash
        ):
            issues.append(_error(
                ConfigurationIssueCode.SECURITY_SOURCE_MISMATCH,
                "The E7 VoicePlan does not match the E4/E5 sources.",
                voice_plan.id,
            ))

    @staticmethod
    def _segment_l3(configuration: ConfigurationPlan):
        l3: dict[str, list[object]] = defaultdict(list)
        networks: dict[str, str] = {}
        for action in configuration.actions:
            if isinstance(action, (ConfigureRoutedInterface, ConfigureSvi, ConfigureSubinterface)):
                l3[action.segment_id].append(action)
                networks[action.segment_id] = _network_of(action)
            elif isinstance(action, (ConfigureDhcpPool, SetEndpointDhcp, SetEndpointStaticAddress)):
                networks.setdefault(action.segment_id, _network_of(action))
        return {
            key: sorted(value, key=lambda item: (item.device_id, item.id))
            for key, value in l3.items()
        }, networks

    @staticmethod
    def _endpoints(configuration: ConfigurationPlan):
        by_segment: dict[str, list[object]] = defaultdict(list)
        addresses: dict[str, object] = {}
        for action in configuration.actions:
            if isinstance(action, (SetEndpointDhcp, SetEndpointStaticAddress)):
                by_segment[action.segment_id].append(action)
                addresses[action.device_id] = action
        return {
            key: sorted(value, key=lambda item: (item.device_id, item.id))
            for key, value in by_segment.items()
        }, addresses

    @staticmethod
    def _vlans(configuration: ConfigurationPlan) -> dict[str, list[CreateVlan]]:
        result: dict[str, list[CreateVlan]] = defaultdict(list)
        for action in configuration.actions:
            if isinstance(action, CreateVlan):
                result[action.segment_id].append(action)
        return result

    @staticmethod
    def _analyze_policy_conflicts(
        policies: list[SecurityPolicyIntent],
        issues: list[ConfigurationIssue],
    ) -> None:
        exact: dict[tuple, SecurityPolicyIntent] = {}
        ordered = sorted(policies, key=lambda item: (item.priority, item.id))
        for policy in ordered:
            key = (
                policy.source_segment_id,
                policy.destination_segment_id,
                policy.destination_service_id,
                policy.destination_call_control_id,
                policy.protocol.casefold(),
                tuple(sorted(policy.source_ports)),
                tuple(sorted(policy.destination_ports)),
            )
            previous = exact.get(key)
            if previous and previous.decision is not policy.decision:
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_POLICY_CONFLICT,
                    f"Policies {previous.id!r} and {policy.id!r} contradict exactly.",
                    policy.id,
                ))
            elif previous:
                issues.append(_warning(
                    ConfigurationIssueCode.SECURITY_POLICY_SHADOWED,
                    f"Policy {policy.id!r} duplicates {previous.id!r}.",
                    policy.id,
                ))
            else:
                exact[key] = policy

        for index, policy in enumerate(ordered):
            if (
                policy.destination_segment_id
                or policy.destination_service_id
                or policy.destination_call_control_id
                or policy.protocol.casefold() != "ip"
            ):
                continue
            for later in ordered[index + 1:]:
                if later.source_segment_id == policy.source_segment_id:
                    issues.append(_warning(
                        ConfigurationIssueCode.SECURITY_POLICY_SHADOWED,
                        f"Broad policy {policy.id!r} may shadow {later.id!r}.",
                        later.id,
                    ))

    def _resolve_policies(
        self,
        policies: list[SecurityPolicyIntent],
        services: dict[str, ServiceDefinition],
        call_controls: dict[str, CallControlInstance],
        segment_l3: dict[str, list[object]],
        segment_networks: dict[str, str],
        endpoints: dict[str, list[object]],
        endpoint_addresses: dict[str, object],
        devices: dict[str, DevicePlan],
        issues: list[ConfigurationIssue],
    ) -> list[dict[str, object]]:
        resolved: list[dict[str, object]] = []
        for policy in sorted(policies, key=lambda item: (item.priority, item.id)):
            source_l3 = segment_l3.get(policy.source_segment_id, [])
            source_network = segment_networks.get(policy.source_segment_id, "")
            source_endpoint = next(iter(endpoints.get(policy.source_segment_id, [])), None)
            if not source_l3 or not source_network or source_endpoint is None:
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_PLACEMENT_FAILED,
                    f"Source segment {policy.source_segment_id!r} lacks E5 L3 or endpoint state.",
                    policy.id,
                ))
                continue
            placement_devices = [
                (placement, devices.get(placement.device_id))
                for placement in source_l3
            ]
            missing_placement = next((
                placement for placement, device in placement_devices
                if device is None
            ), None)
            if missing_placement is not None:
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_PLACEMENT_FAILED,
                    f"ACL placement device {missing_placement.device_id!r} "
                    "is absent from E4.",
                    policy.id,
                ))
                continue

            destination_cidr = "0.0.0.0/0"
            destination_device_id = ""
            destination_address = ""
            protocol = policy.protocol.casefold()
            source_ports = sorted(set(policy.source_ports))
            destination_ports = sorted(set(policy.destination_ports))
            probe_kind = (
                SecurityProbeKind.ICMP_REACHABILITY
                if protocol in {"ip", "icmp"}
                and not source_ports and not destination_ports
                else SecurityProbeKind.UNOBSERVABLE
            )
            source_action_id = source_endpoint.id
            destination_foundation_id = ""

            if policy.destination_service_id:
                service = services.get(policy.destination_service_id)
                if service is None:
                    issues.append(_error(
                        ConfigurationIssueCode.SECURITY_SERVICE_MISSING,
                        f"E6 service {policy.destination_service_id!r} does not exist.",
                        policy.id,
                    ))
                    continue
                destination_cidr = f"{service.address}/32"
                destination_address = service.address
                destination_device_id = service.host_device_id
                protocol = service.protocol.casefold()
                destination_ports = sorted(set(service.ports))
                probe_kind = self._service_probe(service.service_type)
                destination_foundation_id = service.id
            elif policy.destination_call_control_id:
                call_control = call_controls.get(policy.destination_call_control_id)
                if call_control is None:
                    issues.append(_error(
                        ConfigurationIssueCode.SECURITY_VOICE_DEPENDENCY_MISSING,
                        f"E7 call control {policy.destination_call_control_id!r} does not exist.",
                        policy.id,
                    ))
                    continue
                destination_cidr = f"{call_control.source_address}/32"
                destination_address = call_control.source_address
                destination_device_id = call_control.host_device_id
                protocol = "tcp"
                destination_ports = [call_control.signaling_port]
                probe_kind = SecurityProbeKind.VOICE_CALL
                destination_foundation_id = call_control.id
            elif policy.destination_segment_id:
                destination_cidr = segment_networks.get(policy.destination_segment_id, "")
                destination_endpoint = next(
                    iter(endpoints.get(policy.destination_segment_id, [])), None,
                )
                if not destination_cidr or destination_endpoint is None:
                    issues.append(_error(
                        ConfigurationIssueCode.SECURITY_SCOPE_MISSING,
                        f"Destination segment {policy.destination_segment_id!r} has no E5 scope.",
                        policy.id,
                    ))
                    continue
                destination_device_id = destination_endpoint.device_id
                destination_foundation_id = destination_endpoint.id
                if isinstance(destination_endpoint, SetEndpointStaticAddress):
                    destination_address = destination_endpoint.ipv4

            source_device = devices.get(source_endpoint.device_id)
            destination_device = devices.get(destination_device_id)
            for placement, device in placement_devices:
                resolved.append({
                    "policy": policy,
                    "placement": placement,
                    "placement_device": device,
                    "interface": _interface_of(placement),
                    "source_cidr": source_network,
                    "destination_cidr": destination_cidr,
                    "source_ports": source_ports,
                    "destination_ports": destination_ports,
                    "protocol": protocol,
                    "source_device_id": source_endpoint.device_id,
                    "source_device_name": source_device.name if source_device else "",
                    "destination_device_id": destination_device_id,
                    "destination_device_name": destination_device.name if destination_device else "",
                    "destination_address": destination_address,
                    "probe_kind": probe_kind,
                    "source_foundation_id": source_action_id,
                    "destination_foundation_id": destination_foundation_id,
                })
        return resolved

    @staticmethod
    def _service_probe(service_type: ServiceType) -> SecurityProbeKind:
        if service_type is ServiceType.DNS:
            return SecurityProbeKind.DNS_LOOKUP
        if service_type is ServiceType.HTTP:
            return SecurityProbeKind.HTTP_FETCH
        if service_type is ServiceType.HTTPS:
            return SecurityProbeKind.HTTPS_FETCH
        if service_type is ServiceType.NTP:
            return SecurityProbeKind.NTP_SYNC
        if service_type is ServiceType.TFTP:
            return SecurityProbeKind.TFTP_GET
        return SecurityProbeKind.UNOBSERVABLE

    def _acl_actions(
        self,
        resolved: list[dict[str, object]],
        default_decision: SecurityDecision,
        devices: dict[str, DevicePlan],
        foundations: dict[str, SecurityFoundationRequirement],
        issues: list[ConfigurationIssue],
    ) -> tuple[list[SecurityAction], list[SecurityVerificationExpectation]]:
        actions: list[SecurityAction] = []
        expectations: list[SecurityVerificationExpectation] = []
        groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
        for item in resolved:
            placement = item["placement"]
            groups[(placement.device_id, str(item["interface"]))].append(item)

        for group_index, ((device_id, interface), rules) in enumerate(sorted(groups.items())):
            device = devices[device_id]
            acl_number = self._extended_acl_number(group_index)
            if acl_number is None:
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_PLACEMENT_FAILED,
                    "The topology requires more numbered extended ACLs than IOS "
                    "ranges 100-199 and 2000-2699 can represent.",
                    f"{device_id}:{interface}",
                ))
                continue
            acl_name = str(acl_number)
            previous = ""
            sequence = 10
            for item in sorted(
                rules,
                key=lambda value: (value["policy"].priority, value["policy"].id),
            ):
                policy: SecurityPolicyIntent = item["policy"]
                rule_id = _stable_id("acl-rule", policy.id, device_id, interface)
                actions.append(AddSecurityAclRule(
                    id=rule_id,
                    phase=SecurityPhase.ENFORCEMENT,
                    device_id=device_id,
                    device_name=device.name,
                    model=device.model,
                    site_id=device.site_id,
                    depends_on=[previous] if previous else [],
                    required_capability=SecurityCapabilityDimension.ACL_CONFIG,
                    acl_name=acl_name,
                    sequence=sequence,
                    policy_id=policy.id,
                    decision=policy.decision,
                    protocol=str(item["protocol"]),
                    source_cidr=str(item["source_cidr"]),
                    destination_cidr=str(item["destination_cidr"]),
                    source_ports=list(item["source_ports"]),
                    destination_ports=list(item["destination_ports"]),
                    logging=policy.logging,
                ))
                previous = rule_id
                sequence += 10
                foundations[f"foundation/{item['source_foundation_id']}"] = (
                    SecurityFoundationRequirement(
                        id=f"foundation/{item['source_foundation_id']}",
                        kind="endpoint",
                        source_id=str(item["source_foundation_id"]),
                    )
                )
                destination_foundation_id = str(item["destination_foundation_id"])
                if destination_foundation_id:
                    kind = "voice" if policy.destination_call_control_id else (
                        "service" if policy.destination_service_id else "endpoint"
                    )
                    foundations[f"foundation/{destination_foundation_id}"] = (
                        SecurityFoundationRequirement(
                            id=f"foundation/{destination_foundation_id}",
                            kind=kind,
                            source_id=destination_foundation_id,
                        )
                    )
                expectations.append(SecurityVerificationExpectation(
                    id=_stable_id(
                        "verify-traffic", policy.id, device_id, interface,
                    ),
                    kind=SecurityVerificationKind.TRAFFIC_POLICY,
                    action_id=rule_id,
                    policy_id=policy.id,
                    probe_kind=item["probe_kind"],
                    expected_decision=policy.decision,
                    source_device_id=str(item["source_device_id"]),
                    source_device_name=str(item["source_device_name"]),
                    destination_device_id=str(item["destination_device_id"]),
                    destination_device_name=str(item["destination_device_name"]),
                    destination_address=str(item["destination_address"]),
                    protocol=str(item["protocol"]),
                    destination_ports=list(item["destination_ports"]),
                    baseline_required=policy.decision is SecurityDecision.DENY,
                    cleanup_recovery_required=policy.decision is SecurityDecision.DENY,
                    depends_on=[rule_id],
                ))

            if default_decision is SecurityDecision.ALLOW:
                default_id = _stable_id("acl-default", device_id, interface, "allow")
                actions.append(AddSecurityAclRule(
                    id=default_id,
                    phase=SecurityPhase.ENFORCEMENT,
                    device_id=device_id,
                    device_name=device.name,
                    model=device.model,
                    site_id=device.site_id,
                    depends_on=[previous],
                    required_capability=SecurityCapabilityDimension.ACL_CONFIG,
                    acl_name=acl_name,
                    sequence=sequence,
                    decision=SecurityDecision.ALLOW,
                    protocol="ip",
                    source_cidr="0.0.0.0/0",
                    destination_cidr="0.0.0.0/0",
                    default_rule=True,
                ))
                previous = default_id
            attach_id = _stable_id("acl-attach", device_id, interface, acl_name)
            actions.append(AttachSecurityAcl(
                id=attach_id,
                phase=SecurityPhase.ATTACHMENTS,
                device_id=device_id,
                device_name=device.name,
                model=device.model,
                site_id=device.site_id,
                depends_on=[previous],
                required_capability=SecurityCapabilityDimension.ACL_CONFIG,
                acl_name=acl_name,
                interface=interface,
                direction="in",
            ))
            rule_ids = {
                item.id for item in actions
                if isinstance(item, AddSecurityAclRule) and item.acl_name == acl_name
            }
            for expectation in expectations:
                if expectation.action_id in rule_ids:
                    expectation.action_id = attach_id
                    expectation.depends_on = [attach_id]
            foundations[f"foundation/l3/{device_id}/{interface}"] = (
                SecurityFoundationRequirement(
                    id=f"foundation/l3/{device_id}/{interface}",
                    kind="l3_interface",
                    source_id=str(rules[0]["placement"].id),
                )
            )
            expectations.append(SecurityVerificationExpectation(
                id=_stable_id("verify-acl", device_id, interface),
                kind=SecurityVerificationKind.ACL_DIRECT_STATE,
                action_id=attach_id,
                policy_id="",
                probe_kind=SecurityProbeKind.DIRECT_READBACK,
                required_query="show_access_lists",
                depends_on=[attach_id],
            ))
        return actions, expectations

    @staticmethod
    def _extended_acl_number(index: int) -> int | None:
        if 0 <= index < 100:
            return 100 + index
        if 100 <= index < 800:
            return 1900 + index
        return None

    def _nat_actions(
        self,
        intent: SecurityIntent,
        topology: TopologyPlan,
        configuration: ConfigurationPlan,
        devices: dict[str, DevicePlan],
        segment_l3: dict[str, list[object]],
        segment_networks: dict[str, str],
        endpoint_addresses: dict[str, object],
        foundations: dict[str, SecurityFoundationRequirement],
        issues: list[ConfigurationIssue],
    ) -> tuple[list[SecurityAction], list[SecurityVerificationExpectation]]:
        actions: list[SecurityAction] = []
        expectations: list[SecurityVerificationExpectation] = []
        allocated_standard_acls: set[int] = set()
        for policy in sorted(intent.nat_policies, key=lambda item: item.id):
            router = devices.get(policy.router_device_id)
            if router is None:
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_NAT_INVALID,
                    f"NAT router {policy.router_device_id!r} does not exist in E4.",
                    policy.id,
                ))
                continue
            inside_actions = []
            for segment_id in sorted(set(policy.inside_segment_ids)):
                candidate = next(
                    (item for item in segment_l3.get(segment_id, [])
                     if item.device_id == policy.router_device_id),
                    None,
                )
                if candidate is None or segment_id not in segment_networks:
                    issues.append(_error(
                        ConfigurationIssueCode.SECURITY_NAT_INVALID,
                        f"Inside segment {segment_id!r} has no E5 L3 interface on {router.name}.",
                        policy.id,
                    ))
                    continue
                inside_actions.append(candidate)
            outside = next(
                (item for item in segment_l3.get(policy.outside_segment_id, [])
                 if item.device_id == policy.router_device_id),
                None,
            )
            if outside is None or len(inside_actions) != len(set(policy.inside_segment_ids)):
                if outside is None:
                    issues.append(_error(
                        ConfigurationIssueCode.SECURITY_NAT_INVALID,
                        f"Outside segment {policy.outside_segment_id!r} has no E5 L3 interface on {router.name}.",
                        policy.id,
                    ))
                continue
            action_id = _stable_id("nat", policy.id, router.id)
            acl_number = 0
            if policy.mode in {NatMode.PAT, NatMode.DYNAMIC}:
                # The existing NAT renderer emits a standard source-network
                # ACE, so allocation must stay in IOS range 1-99.
                start = 1 + int(
                    hashlib.sha256(policy.id.encode()).hexdigest()[:4], 16,
                ) % 99
                acl_number = next((
                    1 + ((start - 1 + offset) % 99)
                    for offset in range(99)
                    if 1 + ((start - 1 + offset) % 99)
                    not in allocated_standard_acls
                ), 0)
                if not acl_number:
                    issues.append(_error(
                        ConfigurationIssueCode.SECURITY_NAT_INVALID,
                        "No standard numbered ACL remains for the compiled NAT policies.",
                        policy.id,
                    ))
                    continue
                allocated_standard_acls.add(acl_number)

            outside_network = ipaddress.ip_network(
                segment_networks[policy.outside_segment_id], strict=False,
            )
            static_mappings: list[CompiledStaticNatMapping] = []
            if policy.mode is NatMode.STATIC:
                for mapping in sorted(
                    policy.static_mappings,
                    key=lambda item: (
                        item.inside_endpoint_id, item.outside_global_address,
                    ),
                ):
                    endpoint = endpoint_addresses.get(mapping.inside_endpoint_id)
                    try:
                        global_address = ipaddress.ip_address(
                            mapping.outside_global_address,
                        )
                    except ValueError:
                        global_address = None
                    if not isinstance(endpoint, SetEndpointStaticAddress):
                        issues.append(_error(
                            ConfigurationIssueCode.SECURITY_NAT_INVALID,
                            f"Static NAT endpoint {mapping.inside_endpoint_id!r} "
                            "has no E5 static address.",
                            policy.id,
                        ))
                        continue
                    if endpoint.segment_id not in set(policy.inside_segment_ids):
                        issues.append(_error(
                            ConfigurationIssueCode.SECURITY_NAT_INVALID,
                            f"Static NAT endpoint {mapping.inside_endpoint_id!r} is not "
                            "inside the policy scope.",
                            policy.id,
                        ))
                        continue
                    if global_address is None or global_address not in outside_network:
                        issues.append(_error(
                            ConfigurationIssueCode.SECURITY_NAT_INVALID,
                            f"Static global address {mapping.outside_global_address!r} "
                            "is outside the compiled external segment.",
                            policy.id,
                        ))
                        continue
                    static_mappings.append(CompiledStaticNatMapping(
                        inside_endpoint_id=mapping.inside_endpoint_id,
                        inside_local_address=endpoint.ipv4,
                        outside_global_address=str(global_address),
                    ))
                    foundations[f"foundation/endpoint/{endpoint.id}"] = (
                        SecurityFoundationRequirement(
                            id=f"foundation/endpoint/{endpoint.id}",
                            kind="endpoint",
                            source_id=endpoint.id,
                        )
                    )
                if len(static_mappings) != len(policy.static_mappings):
                    continue

            dynamic_pool = None
            if policy.mode is NatMode.DYNAMIC and policy.dynamic_pool:
                pool = policy.dynamic_pool
                try:
                    start_address = ipaddress.ip_address(pool.start_address)
                    end_address = ipaddress.ip_address(pool.end_address)
                    pool_network = ipaddress.ip_network(
                        f"0.0.0.0/{pool.prefix}", strict=False,
                    )
                except ValueError:
                    start_address = end_address = None
                    pool_network = None
                if (
                    start_address is None or end_address is None
                    or int(start_address) > int(end_address)
                    or start_address not in outside_network
                    or end_address not in outside_network
                    or pool.prefix != outside_network.prefixlen
                ):
                    issues.append(_error(
                        ConfigurationIssueCode.SECURITY_NAT_INVALID,
                        "Dynamic NAT pool must be an ordered IPv4 range within "
                        "the compiled external segment and use its prefix.",
                        policy.id,
                    ))
                    continue
                dynamic_pool = CompiledDynamicNatPool(
                    name=("E8_" + _token(policy.id).upper())[:24],
                    start_address=str(start_address),
                    end_address=str(end_address),
                    netmask=str(pool_network.netmask),
                )
            action = ConfigureSecurityNat(
                id=action_id,
                phase=SecurityPhase.ENFORCEMENT,
                device_id=_device_id(router),
                device_name=router.name,
                model=router.model,
                site_id=router.site_id,
                required_capability={
                    NatMode.PAT: SecurityCapabilityDimension.NAT_PAT_CONFIG,
                    NatMode.STATIC: SecurityCapabilityDimension.NAT_STATIC_CONFIG,
                    NatMode.DYNAMIC: SecurityCapabilityDimension.NAT_DYNAMIC_CONFIG,
                }[policy.mode],
                policy_id=policy.id,
                mode=policy.mode,
                inside_interfaces=sorted(_interface_of(item) for item in inside_actions),
                outside_interface=_interface_of(outside),
                inside_networks=sorted(
                    segment_networks[item] for item in set(policy.inside_segment_ids)
                ),
                translation_acl_number=acl_number,
                probe_destination_device_id=policy.probe_destination_device_id,
                static_mappings=static_mappings,
                dynamic_pool=dynamic_pool,
            )
            actions.append(action)
            for foundation in [*inside_actions, outside]:
                foundation_id = f"foundation/l3/{foundation.id}"
                foundations[foundation_id] = SecurityFoundationRequirement(
                    id=foundation_id,
                    kind="l3_interface",
                    source_id=foundation.id,
                )
            destination = devices.get(policy.probe_destination_device_id)
            destination_address = endpoint_addresses.get(policy.probe_destination_device_id)
            preferred_source_id = (
                sorted(
                    policy.static_mappings,
                    key=lambda item: (
                        item.inside_endpoint_id, item.outside_global_address,
                    ),
                )[0].inside_endpoint_id
                if policy.mode is NatMode.STATIC and policy.static_mappings else ""
            )
            source_endpoint = (
                endpoint_addresses.get(preferred_source_id)
                if preferred_source_id else next((
                    item for item in sorted(
                        endpoint_addresses.values(), key=lambda value: value.id,
                    ) if item.segment_id in set(policy.inside_segment_ids)
                ), None)
            )
            source_device = devices.get(source_endpoint.device_id) if source_endpoint else None
            behavior_probe = (
                SecurityProbeKind.ICMP_REACHABILITY
                if source_device
                and destination
                and isinstance(destination_address, SetEndpointStaticAddress)
                else SecurityProbeKind.UNOBSERVABLE
            )
            expectations.append(SecurityVerificationExpectation(
                id=_stable_id("verify-nat-state", policy.id),
                kind=SecurityVerificationKind.NAT_DIRECT_STATE,
                action_id=action_id,
                policy_id=policy.id,
                probe_kind=SecurityProbeKind.DIRECT_READBACK,
                required_query="show_ip_nat_statistics",
                depends_on=[action_id],
            ))
            expectations.append(SecurityVerificationExpectation(
                id=_stable_id("verify-nat-translation", policy.id),
                kind=SecurityVerificationKind.NAT_TRANSLATION,
                action_id=action_id,
                policy_id=policy.id,
                probe_kind=behavior_probe,
                expected_decision=SecurityDecision.ALLOW,
                source_device_id=source_endpoint.device_id if source_endpoint else "",
                source_device_name=source_device.name if source_device else "",
                destination_device_id=policy.probe_destination_device_id,
                destination_device_name=destination.name if destination else "",
                destination_address=(
                    destination_address.ipv4
                    if isinstance(destination_address, SetEndpointStaticAddress) else ""
                ),
                required_query="show_ip_nat_translations",
                depends_on=[action_id],
            ))
            if source_endpoint:
                foundations[f"foundation/endpoint/{source_endpoint.id}"] = (
                    SecurityFoundationRequirement(
                        id=f"foundation/endpoint/{source_endpoint.id}",
                        kind="endpoint",
                        source_id=source_endpoint.id,
                    )
                )
        return actions, expectations

    def _port_security_actions(
        self,
        intent: SecurityIntent,
        topology: TopologyPlan,
        configuration: ConfigurationPlan,
        devices: dict[str, DevicePlan],
        devices_by_name: dict[str, DevicePlan],
        endpoint_addresses: dict[str, object],
        foundations: dict[str, SecurityFoundationRequirement],
        issues: list[ConfigurationIssue],
    ) -> tuple[list[SecurityAction], list[SecurityVerificationExpectation]]:
        actions: list[SecurityAction] = []
        expectations: list[SecurityVerificationExpectation] = []
        access_actions = [
            item for item in configuration.actions if isinstance(item, ConfigureAccessPort)
        ]
        for policy in sorted(intent.port_security, key=lambda item: item.id):
            for endpoint_id in sorted(set(policy.endpoint_ids)):
                binding = self._endpoint_switch_binding(
                    endpoint_id, topology.links, devices, devices_by_name,
                )
                if binding is None:
                    issues.append(_error(
                        ConfigurationIssueCode.SECURITY_PORT_BINDING_MISSING,
                        f"Endpoint {endpoint_id!r} has no exact E4 switch-port link.",
                        policy.id,
                    ))
                    continue
                switch, interface, link = binding
                access = next(
                    (item for item in access_actions
                     if item.device_id == _device_id(switch)
                     and item.interface == interface
                     and endpoint_id in item.endpoint_ids),
                    None,
                )
                if access is None:
                    issues.append(_error(
                        ConfigurationIssueCode.SECURITY_PORT_BINDING_MISSING,
                        f"E4 port {switch.name}:{interface} has no matching E5 access action.",
                        policy.id,
                    ))
                    continue
                action_id = _stable_id("port-security", policy.id, endpoint_id, link.id)
                actions.append(ConfigureEndpointPortSecurity(
                    id=action_id,
                    phase=SecurityPhase.ENFORCEMENT,
                    device_id=_device_id(switch),
                    device_name=switch.name,
                    model=switch.model,
                    site_id=switch.site_id,
                    required_capability=SecurityCapabilityDimension.PORT_SECURITY_CONFIG,
                    policy_id=policy.id,
                    switch_device_id=_device_id(switch),
                    interface=interface,
                    endpoint_ids=[endpoint_id],
                    max_macs=policy.max_macs,
                    violation=policy.violation,
                    sticky=policy.sticky,
                    access_configuration_action_id=access.id,
                ))
                foundations[f"foundation/access/{access.id}"] = SecurityFoundationRequirement(
                    id=f"foundation/access/{access.id}",
                    kind="access_port",
                    source_id=access.id,
                )
                endpoint_address = endpoint_addresses.get(endpoint_id)
                if endpoint_address:
                    foundations[f"foundation/endpoint/{endpoint_address.id}"] = (
                        SecurityFoundationRequirement(
                            id=f"foundation/endpoint/{endpoint_address.id}",
                            kind="endpoint",
                            source_id=endpoint_address.id,
                        )
                    )
                expectations.append(SecurityVerificationExpectation(
                    id=_stable_id("verify-port-security", action_id),
                    kind=SecurityVerificationKind.PORT_SECURITY_STATE,
                    action_id=action_id,
                    policy_id=policy.id,
                    probe_kind=SecurityProbeKind.DIRECT_READBACK,
                    required_query="show_port_security_interface",
                    depends_on=[action_id],
                ))
        return actions, expectations

    @staticmethod
    def _endpoint_switch_binding(
        endpoint_id: str,
        links: list[LinkPlan],
        devices: dict[str, DevicePlan],
        devices_by_name: dict[str, DevicePlan],
    ) -> tuple[DevicePlan, str, LinkPlan] | None:
        for link in sorted(links, key=lambda item: item.id):
            a_id = link.device_a_id or _device_id(devices_by_name[link.device_a])
            b_id = link.device_b_id or _device_id(devices_by_name[link.device_b])
            if a_id == endpoint_id:
                peer = devices.get(b_id)
                if peer and peer.category == "switch":
                    return peer, link.port_b, link
            if b_id == endpoint_id:
                peer = devices.get(a_id)
                if peer and peer.category == "switch":
                    return peer, link.port_a, link
        return None

    def _inspection_actions(
        self,
        policies: list[DhcpInspectionPolicyIntent],
        topology: TopologyPlan,
        devices: dict[str, DevicePlan],
        devices_by_name: dict[str, DevicePlan],
        vlans: dict[str, list[CreateVlan]],
        foundations: dict[str, SecurityFoundationRequirement],
        issues: list[ConfigurationIssue],
    ) -> tuple[list[SecurityAction], list[SecurityVerificationExpectation]]:
        actions: list[SecurityAction] = []
        expectations: list[SecurityVerificationExpectation] = []
        for policy in sorted(policies, key=lambda item: item.id):
            vlan_ids: list[int] = []
            for segment_id in sorted(set(policy.segment_ids)):
                candidates = vlans.get(segment_id, [])
                if not candidates:
                    issues.append(_error(
                        ConfigurationIssueCode.SECURITY_VLAN_MISSING,
                        f"Segment {segment_id!r} has no E5 VLAN definition.",
                        policy.id,
                    ))
                    continue
                vlan_ids.extend(item.vlan_id for item in candidates)
                for candidate in candidates:
                    foundations[f"foundation/vlan/{candidate.id}"] = (
                        SecurityFoundationRequirement(
                            id=f"foundation/vlan/{candidate.id}",
                            kind="vlan",
                            source_id=candidate.id,
                        )
                    )
            switches = sorted(
                (
                    item for item in topology.devices
                    if item.site_id == policy.site_id and item.category == "switch"
                ),
                key=lambda item: (_device_id(item), item.name),
            )
            if not switches:
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_SCOPE_MISSING,
                    f"Site {policy.site_id!r} has no E4 switch for inspection policy.",
                    policy.id,
                ))
                continue
            for switch in switches:
                trusted = self._trusted_interfaces(
                    switch, topology.links, devices, devices_by_name,
                )
                previous = ""
                if policy.enable_snooping:
                    snooping_id = _stable_id("dhcp-snooping", policy.id, _device_id(switch))
                    actions.append(ConfigureDhcpSnooping(
                        id=snooping_id,
                        phase=SecurityPhase.ENFORCEMENT,
                        device_id=_device_id(switch),
                        device_name=switch.name,
                        model=switch.model,
                        site_id=switch.site_id,
                        required_capability=SecurityCapabilityDimension.DHCP_SNOOPING_CONFIG,
                        policy_id=policy.id,
                        vlan_ids=sorted(set(vlan_ids)),
                        trusted_interfaces=trusted,
                    ))
                    previous = snooping_id
                    expectations.append(SecurityVerificationExpectation(
                        id=_stable_id("verify-dhcp-snooping", snooping_id),
                        kind=SecurityVerificationKind.DHCP_SNOOPING_STATE,
                        action_id=snooping_id,
                        policy_id=policy.id,
                        probe_kind=SecurityProbeKind.DIRECT_READBACK,
                        required_query="show_ip_dhcp_snooping",
                        depends_on=[snooping_id],
                    ))
                if policy.enable_dai:
                    dai_id = _stable_id("dai", policy.id, _device_id(switch))
                    actions.append(ConfigureDynamicArpInspection(
                        id=dai_id,
                        phase=SecurityPhase.ENFORCEMENT,
                        device_id=_device_id(switch),
                        device_name=switch.name,
                        model=switch.model,
                        site_id=switch.site_id,
                        depends_on=[previous] if previous else [],
                        required_capability=SecurityCapabilityDimension.DAI_CONFIG,
                        policy_id=policy.id,
                        vlan_ids=sorted(set(vlan_ids)),
                        trusted_interfaces=trusted,
                    ))
                    expectations.append(SecurityVerificationExpectation(
                        id=_stable_id("verify-dai", dai_id),
                        kind=SecurityVerificationKind.DAI_STATE,
                        action_id=dai_id,
                        policy_id=policy.id,
                        probe_kind=SecurityProbeKind.DIRECT_READBACK,
                        required_query="show_ip_arp_inspection",
                        depends_on=[dai_id],
                    ))
        return actions, expectations

    @staticmethod
    def _trusted_interfaces(
        switch: DevicePlan,
        links: list[LinkPlan],
        devices: dict[str, DevicePlan],
        devices_by_name: dict[str, DevicePlan],
    ) -> list[str]:
        switch_id = _device_id(switch)
        trusted: set[str] = set()
        for link in links:
            if not any(role in link.link_role.casefold() for role in _TRUSTED_LINK_ROLES):
                continue
            a_id = link.device_a_id or _device_id(devices_by_name[link.device_a])
            b_id = link.device_b_id or _device_id(devices_by_name[link.device_b])
            if a_id == switch_id and b_id in devices:
                trusted.add(link.port_a)
            elif b_id == switch_id and a_id in devices:
                trusted.add(link.port_b)
        return sorted(trusted)

    def _hardening_actions(
        self,
        intent: SecurityIntent,
        devices: dict[str, DevicePlan],
        foundations: dict[str, SecurityFoundationRequirement],
        issues: list[ConfigurationIssue],
    ) -> tuple[list[SecurityAction], list[SecurityVerificationExpectation]]:
        actions: list[SecurityAction] = []
        expectations: list[SecurityVerificationExpectation] = []
        for policy in sorted(intent.hardening, key=lambda item: item.id):
            for device_id in sorted(set(policy.device_ids)):
                device = devices.get(device_id)
                if device is None:
                    issues.append(_error(
                        ConfigurationIssueCode.SECURITY_SCOPE_MISSING,
                        f"Hardening device {device_id!r} does not exist in E4.",
                        policy.id,
                    ))
                    continue
                action_id = _stable_id("hardening", policy.id, device_id)
                actions.append(ApplyDeviceHardening(
                    id=action_id,
                    phase=SecurityPhase.HARDENING,
                    device_id=device_id,
                    device_name=device.name,
                    model=device.model,
                    site_id=device.site_id,
                    required_capability=SecurityCapabilityDimension.HARDENING_CONFIG,
                    policy_id=policy.id,
                    banner_motd=policy.banner_motd,
                    service_password_encryption=policy.service_password_encryption,
                ))
                expectations.append(SecurityVerificationExpectation(
                    id=_stable_id("verify-hardening", action_id),
                    kind=SecurityVerificationKind.HARDENING_STATE,
                    action_id=action_id,
                    policy_id=policy.id,
                    probe_kind=SecurityProbeKind.DIRECT_READBACK,
                    required_query="show_running_config_hardening",
                    depends_on=[action_id],
                ))
        return actions, expectations

    @staticmethod
    def _gate_capabilities(
        actions: list[SecurityAction],
        expectations: list[SecurityVerificationExpectation],
        capabilities: dict[str, SecurityCapabilityProfile],
        issues: list[ConfigurationIssue],
    ) -> None:
        for action in actions:
            profile = capabilities.get(action.model)
            status = (
                profile.status(action.required_capability)
                if profile else SecurityCapabilityStatus.UNKNOWN
            )
            if status is SecurityCapabilityStatus.UNKNOWN:
                issues.append(_warning(
                    ConfigurationIssueCode.SECURITY_CAPABILITY_UNKNOWN,
                    f"{action.model}:{action.required_capability.value} requires runtime evidence.",
                    action.id,
                    model=action.model,
                    capability=action.required_capability.value,
                ))
            elif status is SecurityCapabilityStatus.UNSUPPORTED:
                issues.append(_error(
                    ConfigurationIssueCode.SECURITY_CAPABILITY_UNSUPPORTED,
                    f"{action.model}:{action.required_capability.value} is unsupported.",
                    action.id,
                    model=action.model,
                    capability=action.required_capability.value,
                ))
        actions_by_id = {item.id: item for item in actions}
        for expectation in expectations:
            action = actions_by_id.get(expectation.action_id)
            if action is None:
                continue
            dimension = security_verification_capability(expectation)
            profile = capabilities.get(action.model)
            status = (
                profile.status(dimension)
                if profile else SecurityCapabilityStatus.UNKNOWN
            )
            if status is SecurityCapabilityStatus.SUPPORTED:
                continue
            code = {
                SecurityCapabilityStatus.UNKNOWN:
                    ConfigurationIssueCode.SECURITY_CAPABILITY_UNKNOWN,
                SecurityCapabilityStatus.PARTIAL:
                    ConfigurationIssueCode.SECURITY_CAPABILITY_PARTIAL,
                SecurityCapabilityStatus.UNOBSERVABLE:
                    ConfigurationIssueCode.SECURITY_CAPABILITY_UNOBSERVABLE,
                SecurityCapabilityStatus.UNSUPPORTED:
                    ConfigurationIssueCode.SECURITY_CAPABILITY_UNSUPPORTED,
                SecurityCapabilityStatus.SKIPPED:
                    ConfigurationIssueCode.SECURITY_CAPABILITY_UNKNOWN,
            }[status]
            issues.append(_warning(
                code,
                f"{action.model}:{dimension.value} verification is {status.value}.",
                expectation.id,
                model=action.model,
                capability=dimension.value,
            ))

    @staticmethod
    def _semantic_hash(plan: SecurityPlan) -> str:
        payload = plan.model_dump(mode="json")
        payload["semantic_hash"] = ""
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _deduplicate_issues(issues: list[ConfigurationIssue]) -> list[ConfigurationIssue]:
        unique = {
            (item.severity.value, item.code.value, item.subject, item.message): item
            for item in issues
        }
        return [unique[key] for key in sorted(unique)]

    @staticmethod
    def _result(
        plan: SecurityPlan | None,
        intent: SecurityIntent,
        actions: list[SecurityAction],
        expectations: list[SecurityVerificationExpectation],
        topology: TopologyPlan,
        configuration: ConfigurationPlan,
        issues: list[ConfigurationIssue],
    ) -> SecurityCompileResult:
        summary = SecurityCompileSummary(
            security_plan_id=plan.id if plan else "",
            semantic_hash=plan.semantic_hash if plan else "",
            source_topology_hash=topology.semantic_hash,
            source_configuration_hash=configuration.semantic_hash,
            source_service_hash=plan.source_service_hash if plan else "",
            source_voice_hash=plan.source_voice_hash if plan else "",
            policy_count=len(intent.policies),
            action_count=len(actions),
            actions_by_type=security_action_type_counts(actions),
            verification_count=len(expectations),
            warnings=sum(
                item.severity is ConfigurationIssueSeverity.WARNING for item in issues
            ),
            errors=sum(
                item.severity is ConfigurationIssueSeverity.ERROR for item in issues
            ),
        )
        return SecurityCompileResult(
            plan=plan,
            semantic_hash=plan.semantic_hash if plan else "",
            summary=summary,
            issues=issues,
        )
