"""E9: E4 + E5 (+ E8 when consumed) -> ControlPlanePlan determinista."""

from __future__ import annotations

import hashlib
import ipaddress
import json
from collections import defaultdict
from collections.abc import Iterable

from ...models.plans import DevicePlan, LinkPlan, TopologyPlan
from ..models.configuration import (
    ConfigureAccessPort,
    ConfigureDhcpPool,
    ConfigureRoutedInterface,
    ConfigureSubinterface,
    ConfigureSvi,
    ConfigureTrunk,
    ConfigurationIssue,
    ConfigurationIssueCode,
    ConfigurationIssueSeverity,
    ConfigurationPlan,
    CreateVlan,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
)
from ..models.control_plane import (
    ConfigureEigrpIpv4,
    ConfigureEtherChannel,
    ConfigureHsrp,
    ConfigureOspfv2,
    ConfigureRipv2,
    ConfigureSpanningTree,
    ConfigureStpEdgePort,
    ControlPlaneAction,
    ControlPlaneActionType,
    ControlPlaneCapabilityDimension,
    ControlPlaneCapabilityProfile,
    ControlPlaneCompileResult,
    ControlPlaneCompileSummary,
    ControlPlaneFoundationRequirement,
    ControlPlaneIntent,
    ControlPlanePhase,
    ControlPlanePlan,
    ControlPlaneVerificationExpectation,
    ControlPlaneVerificationKind,
    DynamicRoutingProtocol,
    EtherChannelProtocol,
    LinkFailureScenario,
    RipNetwork,
    RoutingNetwork,
    StpMode,
    control_plane_action_type_counts,
)
from ..models.security_plan import SecurityCapabilityStatus, SecurityPlan
from ..models.failure_domain import (
    FailureDomain,
    FailureDomainCatalog,
    FailurePath,
    FailureScenario,
    FailureScenarioScope,
    IndependenceStatus,
)
from ..models.verification import PrerequisiteKind, VerificationPrerequisite
from .configuration_dependencies import (
    ConfigurationDependencyError,
    order_dependency_actions,
)
from .failure_domain_analyzer import (
    FailureDomainAnalyzer,
    build_failure_domain_catalog,
)


_L3_ACTIONS = (ConfigureRoutedInterface, ConfigureSvi, ConfigureSubinterface)
_ENDPOINT_ACTIONS = (SetEndpointDhcp, SetEndpointStaticAddress)
_LAYER_RANK = {"core": 0, "distribution": 1, "access": 2, "edge": 3}


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
    return f"cp/{kind}/{digest}"


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


def _network_of(action: object) -> ipaddress.IPv4Network | None:
    if isinstance(action, _L3_ACTIONS):
        return ipaddress.ip_interface(f"{action.ipv4}/{action.prefix}").network
    return None


def _wildcard(network: ipaddress.IPv4Network) -> str:
    return str(ipaddress.IPv4Address(int(network.hostmask)))


def _prefix_length_from_wildcard(wildcard: str) -> int:
    return 32 - int(ipaddress.IPv4Address(wildcard)).bit_count()


def _classful_network(network: ipaddress.IPv4Network) -> str | None:
    """La red classful que IOS RIP espera detrás de `network`.

    RIP no lleva máscara en la sentencia: IOS la deduce de la clase. Varias
    subredes de la misma clase colapsan en una sola sentencia, que es la razón
    por la que 150.1.1.0/24 y 150.1.100.0/30 comparten `network 150.1.0.0`.
    Devuelve None cuando la dirección no pertenece a ninguna clase con
    sentencia RIP (loopback, multicast, reservadas).
    """
    first = int(network.network_address) >> 24
    if 1 <= first <= 126:
        length = 8
    elif 128 <= first <= 191:
        length = 16
    elif 192 <= first <= 223:
        length = 24
    else:
        return None
    return str(ipaddress.IPv4Network(
        (int(network.network_address) >> (32 - length) << (32 - length), length),
    ).network_address)


def _link_device_ids(
    link: LinkPlan, names_to_ids: dict[str, str],
) -> tuple[str, str]:
    return (
        link.device_a_id or names_to_ids.get(link.device_a, ""),
        link.device_b_id or names_to_ids.get(link.device_b, ""),
    )


def _links_connect(
    start: str,
    goal: str,
    link_ids: list[str],
    links: dict[str, LinkPlan],
    names_to_ids: dict[str, str],
) -> bool:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for link_id in sorted(set(link_ids)):
        link = links[link_id]
        left, right = _link_device_ids(link, names_to_ids)
        if not left or not right:
            continue
        adjacency[left].add(right)
        adjacency[right].add(left)
    pending = [start]
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current == goal:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(sorted(adjacency[current] - seen, reverse=True))
    return False


class ControlPlaneCompiler:
    """Compila control plane sin CLI, JavaScript ni objetos runtime de PT."""

    def compile(
        self,
        intent: ControlPlaneIntent,
        topology: TopologyPlan,
        configuration: ConfigurationPlan,
        *,
        security_plan: SecurityPlan | None = None,
        capabilities: dict[str, ControlPlaneCapabilityProfile] | None = None,
        failure_domains: Iterable[FailureDomain] = (),
    ) -> ControlPlaneCompileResult:
        issues: list[ConfigurationIssue] = []
        capabilities = capabilities or {}
        self._validate_sources(
            intent, topology, configuration, security_plan, issues,
        )
        self._validate_intent(intent, issues)

        devices = {_device_id(item): item for item in topology.devices}
        names_to_ids = {item.name: _device_id(item) for item in topology.devices}
        links = {item.id: item for item in topology.links if item.id}
        failure_domain_catalog = build_failure_domain_catalog(
            topology,
            explicit_domains=failure_domains,
        )
        foundations: dict[str, ControlPlaneFoundationRequirement] = {}
        actions: list[ControlPlaneAction] = []
        expectations: list[ControlPlaneVerificationExpectation] = []

        security_id = ""
        security_hash = ""
        if intent.security_policy_ids and security_plan is not None:
            security_id = security_plan.id
            security_hash = security_plan.semantic_hash
            requested = set(intent.security_policy_ids)
            for action in security_plan.actions:
                policy_id = getattr(action, "policy_id", "")
                if policy_id in requested:
                    self._foundation(
                        foundations, "security", action.id, security_plan.semantic_hash,
                    )

        stp_actions, stp_expectations, stp_by_device = self._compile_stp(
            intent, topology, configuration, devices, foundations, issues,
        )
        actions.extend(stp_actions)
        expectations.extend(stp_expectations)

        ether_actions, ether_expectations = self._compile_etherchannels(
            intent, topology, configuration, devices, names_to_ids, links,
            stp_by_device, foundations, issues,
        )
        actions.extend(ether_actions)
        expectations.extend(ether_expectations)

        hsrp_actions, hsrp_expectations = self._compile_hsrp(
            intent, configuration, devices, foundations, issues,
        )
        actions.extend(hsrp_actions)
        expectations.extend(hsrp_expectations)

        routing_actions, routing_expectations = self._compile_routing(
            intent, topology, configuration, devices, names_to_ids, links,
            foundations, issues,
        )
        actions.extend(routing_actions)
        expectations.extend(routing_expectations)

        scenarios, scenario_expectations = self._compile_failure_scenarios(
            intent, configuration, devices, names_to_ids, links, actions,
            foundations, failure_domain_catalog, issues,
        )
        expectations.extend(scenario_expectations)

        self._gate_capabilities(actions, expectations, capabilities, issues)
        try:
            actions = order_dependency_actions(actions)
        except ConfigurationDependencyError as exc:
            code = (
                ConfigurationIssueCode.DEPENDENCY_CYCLE
                if "cycle" in str(exc).casefold()
                else ConfigurationIssueCode.DEPENDENCY_MISSING
            )
            issues.append(_error(code, str(exc), ",".join(exc.action_ids)))

        issues = self._deduplicate_issues(issues)
        plan: ControlPlanePlan | None = None
        if not any(
            item.severity is ConfigurationIssueSeverity.ERROR for item in issues
        ):
            for action in actions:
                action.apply_dependencies = list(action.depends_on)
            for expectation in expectations:
                expectation.verification_prerequisites = [
                    VerificationPrerequisite(
                        kind=PrerequisiteKind.ACTION_APPLIED,
                        reference_id=identifier,
                    )
                    for identifier in sorted(set([
                        expectation.action_id, *expectation.depends_on,
                    ]))
                ]
            plan = ControlPlanePlan(
                id=f"control-plane_{topology.id or topology.physical_identity_hash[:16]}",
                source_topology_id=topology.id,
                source_topology_hash=topology.physical_identity_hash,
                source_topology_hash_schema=(
                    "physical-topology-v2"
                    if topology.physical_topology_hash else "legacy-full-v1"
                ),
                source_configuration_id=configuration.id,
                source_configuration_hash=configuration.semantic_hash,
                source_security_id=security_id,
                source_security_hash=security_hash,
                security_policy_ids=sorted(set(intent.security_policy_ids)),
                actions=actions,
                foundational_requirements=sorted(
                    foundations.values(), key=lambda item: item.id,
                ),
                verification_expectations=sorted(
                    expectations,
                    key=lambda item: (item.kind.value, item.device_id, item.id),
                ),
                failure_scenarios=sorted(scenarios, key=lambda item: item.id),
                failure_domain_catalog=failure_domain_catalog,
            )
            plan.semantic_hash = self._semantic_hash(plan)
        return self._result(
            plan, actions, expectations, scenarios, topology, configuration,
            security_hash, issues,
        )

    @staticmethod
    def _validate_sources(
        intent: ControlPlaneIntent,
        topology: TopologyPlan,
        configuration: ConfigurationPlan,
        security_plan: SecurityPlan | None,
        issues: list[ConfigurationIssue],
    ) -> None:
        if not topology.physical_identity_hash or not configuration.semantic_hash:
            issues.append(_error(
                ConfigurationIssueCode.CONTROL_PLANE_SOURCE_HASH_MISSING,
                "E9 requires immutable E4 and E5 semantic hashes.",
                intent.id,
            ))
        if configuration.source_topology_hash != topology.physical_identity_hash:
            issues.append(_error(
                ConfigurationIssueCode.CONTROL_PLANE_SOURCE_MISMATCH,
                "The E5 ConfigurationPlan was compiled for a different E4 topology.",
                configuration.id,
            ))
        if not intent.security_policy_ids:
            return
        if security_plan is None or not security_plan.semantic_hash:
            issues.append(_error(
                ConfigurationIssueCode.CONTROL_PLANE_SECURITY_MISSING,
                "Explicit security policy dependencies require an immutable E8 plan.",
                intent.id,
            ))
            return
        if (
            security_plan.source_topology_hash != topology.physical_identity_hash
            or security_plan.source_configuration_hash != configuration.semantic_hash
        ):
            issues.append(_error(
                ConfigurationIssueCode.CONTROL_PLANE_SOURCE_MISMATCH,
                "The E8 SecurityPlan does not match the supplied E4/E5 foundations.",
                security_plan.id,
            ))
        known = {
            getattr(action, "policy_id", "") for action in security_plan.actions
            if getattr(action, "policy_id", "")
        }
        for policy_id in sorted(set(intent.security_policy_ids) - known):
            issues.append(_error(
                ConfigurationIssueCode.CONTROL_PLANE_SECURITY_POLICY_MISSING,
                f"Security policy {policy_id!r} is absent from E8 actions.",
                policy_id,
            ))

    @staticmethod
    def _validate_intent(
        intent: ControlPlaneIntent, issues: list[ConfigurationIssue],
    ) -> None:
        seen: set[str] = set()
        for item in [
            *intent.stp_domains,
            *intent.etherchannels,
            *intent.first_hop_redundancy,
            *intent.routing_domains,
            *intent.failure_scenarios,
        ]:
            if item.id in seen:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_INTENT_INVALID,
                    f"Duplicate E9 intent id {item.id!r}.", item.id,
                ))
            seen.add(item.id)
        for item in intent.etherchannels:
            if item.channel_group is not None and not 1 <= item.channel_group <= 255:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_INTENT_INVALID,
                    "EtherChannel channel_group must be between 1 and 255.", item.id,
                ))
        for item in intent.first_hop_redundancy:
            if (
                item.group_number is not None and not 0 <= item.group_number <= 255
            ) or len(set(item.device_ids)) < 2:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_INTENT_INVALID,
                    "HSRP requires two distinct devices and a group in 0..255.", item.id,
                ))
            for device_id, priority in item.priority_by_device.items():
                if device_id not in set(item.device_ids):
                    issues.append(_error(
                        ConfigurationIssueCode.CONTROL_PLANE_INTENT_INVALID,
                        f"HSRP priority references non-member {device_id!r}.", item.id,
                    ))
                if not 0 <= priority <= 255:
                    issues.append(_error(
                        ConfigurationIssueCode.CONTROL_PLANE_INTENT_INVALID,
                        f"Invalid HSRP priority {priority} for {device_id}.", item.id,
                    ))
        routing_domains = [*intent.routing_domains]
        if intent.routing is not None:
            routing_domains.append(intent.routing)
        for routing in routing_domains:
            if routing.process_id < 1 or routing.eigrp_as_number < 1:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_INTENT_INVALID,
                    "Routing process and EIGRP AS numbers must be positive.", intent.id,
                ))

    def _compile_stp(
        self,
        intent: ControlPlaneIntent,
        topology: TopologyPlan,
        configuration: ConfigurationPlan,
        devices: dict[str, DevicePlan],
        foundations: dict[str, ControlPlaneFoundationRequirement],
        issues: list[ConfigurationIssue],
    ) -> tuple[
        list[ControlPlaneAction],
        list[ControlPlaneVerificationExpectation],
        dict[str, str],
    ]:
        policies = [*intent.stp_domains]
        if intent.stp is not None and intent.stp.id not in {item.id for item in policies}:
            policies.append(intent.stp)
        if not policies:
            return [], [], {}
        actions: list[ControlPlaneAction] = []
        expectations: list[ControlPlaneVerificationExpectation] = []
        global_by_device: dict[str, str] = {}
        etherchannel_member_ids = {
            link_id
            for channel in intent.etherchannels
            for link_id in channel.member_link_ids
        }
        for policy in sorted(policies, key=lambda item: item.id):
            domain_actions, domain_expectations, domain_globals = self._compile_stp_domain(
                policy,
                topology,
                configuration,
                devices,
                etherchannel_member_ids,
                foundations,
                issues,
            )
            actions.extend(domain_actions)
            expectations.extend(domain_expectations)
            for device_id, action_id in domain_globals.items():
                if device_id in global_by_device:
                    issues.append(_error(
                        ConfigurationIssueCode.CONTROL_PLANE_INTENT_INVALID,
                        f"STP domains overlap on device {device_id!r}.", policy.id,
                    ))
                global_by_device[device_id] = action_id
        return actions, expectations, global_by_device

    def _compile_stp_domain(
        self,
        policy,
        topology: TopologyPlan,
        configuration: ConfigurationPlan,
        devices: dict[str, DevicePlan],
        etherchannel_member_ids: set[str],
        foundations: dict[str, ControlPlaneFoundationRequirement],
        issues: list[ConfigurationIssue],
    ) -> tuple[
        list[ControlPlaneAction],
        list[ControlPlaneVerificationExpectation],
        dict[str, str],
    ]:
        names_to_ids = {
            item.name: _device_id(item)
            for item in topology.devices
        }
        physical_non_edge_ports: set[tuple[str, str]] = set()
        domain_l2_links: list[tuple[LinkPlan, str, str]] = []
        for link in sorted(
            topology.links,
            key=lambda item: (
                item.id,
                item.device_a_id or item.device_a,
                item.port_a,
                item.device_b_id or item.device_b,
                item.port_b,
            ),
        ):
            device_a_id, device_b_id = _link_device_ids(link, names_to_ids)
            device_a = devices.get(device_a_id)
            device_b = devices.get(device_b_id)
            if device_a is None or device_b is None:
                continue
            device_a_in_domain = not policy.site_id or device_a.site_id == policy.site_id
            device_b_in_domain = not policy.site_id or device_b.site_id == policy.site_id
            switch_link = (
                device_a.category == "switch" and device_b.category == "switch"
            )
            if switch_link and device_a_in_domain and device_b_in_domain:
                domain_l2_links.append((link, device_a_id, device_b_id))
            if switch_link or link.id in etherchannel_member_ids:
                if device_a_in_domain:
                    physical_non_edge_ports.add((device_a_id, link.port_a))
                if device_b_in_domain:
                    physical_non_edge_ports.add((device_b_id, link.port_b))
        vlan_actions: dict[int, list[CreateVlan]] = defaultdict(list)
        vlan_by_device: dict[str, list[CreateVlan]] = defaultdict(list)
        for action in configuration.actions:
            if isinstance(action, CreateVlan):
                device = devices.get(action.device_id)
                if policy.site_id and (device is None or device.site_id != policy.site_id):
                    continue
                vlan_actions[action.vlan_id].append(action)
                vlan_by_device[action.device_id].append(action)
        selected = sorted(set(policy.vlan_ids or vlan_actions))
        for vlan_id in selected:
            if vlan_id not in vlan_actions:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_STP_VLAN_MISSING,
                    f"VLAN {vlan_id} has no E5 definition.", str(vlan_id),
                ))

        mst_instances: dict[int, list[int]] = {}
        if policy.mode is StpMode.MST:
            mst_instances = (
                {key: sorted(set(value)) for key, value in sorted(policy.mst_instances.items())}
                if policy.mst_instances else {1: selected}
            )
            membership = [vlan for values in mst_instances.values() for vlan in values]
            if sorted(membership) != selected or len(membership) != len(set(membership)):
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_MST_MAPPING_INVALID,
                    "Every selected E5 VLAN must occur in exactly one MST instance.",
                    policy.id,
                ))

        roots_primary: dict[int, str] = {}
        roots_secondary: dict[int, str] = {}
        for vlan_id in selected:
            participants = sorted(
                {item.device_id for item in vlan_actions.get(vlan_id, [])},
                key=lambda device_id: self._stp_device_key(devices.get(device_id), device_id),
            )
            if not participants:
                continue
            primary = policy.root_primary_by_vlan.get(vlan_id, participants[0])
            secondary = policy.root_secondary_by_vlan.get(
                vlan_id, participants[1] if len(participants) > 1 else "",
            )
            if primary not in participants or (secondary and secondary not in participants):
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_STP_ROOT_INVALID,
                    f"STP roots for VLAN {vlan_id} must participate in that E5 VLAN.",
                    str(vlan_id),
                ))
                continue
            if secondary and secondary == primary:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_STP_ROOT_INVALID,
                    f"VLAN {vlan_id} primary and secondary roots must differ.",
                    str(vlan_id),
                ))
                continue
            roots_primary[vlan_id] = primary
            if secondary:
                roots_secondary[vlan_id] = secondary

        actions: list[ControlPlaneAction] = []
        expectations: list[ControlPlaneVerificationExpectation] = []
        global_by_device: dict[str, str] = {}
        capability = {
            StpMode.PVST: ControlPlaneCapabilityDimension.STP_PVST_CONFIG,
            StpMode.RAPID_PVST: ControlPlaneCapabilityDimension.STP_RAPID_PVST_CONFIG,
            StpMode.MST: ControlPlaneCapabilityDimension.STP_MST_CONFIG,
        }[policy.mode]
        for device_id in sorted(vlan_by_device):
            device = devices.get(device_id)
            if device is None or device.category != "switch":
                continue
            local = sorted(
                (item for item in vlan_by_device[device_id] if item.vlan_id in selected),
                key=lambda item: (item.vlan_id, item.id),
            )
            if not local:
                continue
            action_id = _stable_id("stp", policy.id, policy.mode.value, device_id)
            global_by_device[device_id] = action_id
            action = ConfigureSpanningTree(
                id=action_id,
                phase=ControlPlanePhase.L2_FOUNDATION,
                device_id=device_id,
                device_name=device.name,
                model=device.model,
                site_id=device.site_id,
                required_capability=capability,
                mode=policy.mode,
                vlan_ids=[item.vlan_id for item in local],
                root_primary_vlans=sorted(
                    vlan for vlan, root in roots_primary.items() if root == device_id
                ),
                root_secondary_vlans=sorted(
                    vlan for vlan, root in roots_secondary.items() if root == device_id
                ),
                priorities={
                    **{
                        vlan: 24576 for vlan, root in roots_primary.items()
                        if root == device_id
                    },
                    **{
                        vlan: 28672 for vlan, root in roots_secondary.items()
                        if root == device_id
                    },
                },
                mst_instances=mst_instances,
                source_vlan_action_ids=[item.id for item in local],
            )
            actions.append(action)
            for item in local:
                self._foundation(foundations, "vlan", item.id)
            expectations.append(ControlPlaneVerificationExpectation(
                id=_stable_id("verify-stp", action_id),
                kind=ControlPlaneVerificationKind.STP_STATE,
                action_id=action_id,
                device_id=device_id,
                required_capability=ControlPlaneCapabilityDimension.STP_STATE,
                expected={
                    "mode": policy.mode.value,
                    "vlan_ids": action.vlan_ids,
                    "root_primary_vlans": action.root_primary_vlans,
                },
                depends_on=[action_id],
            ))
            expectations.append(ControlPlaneVerificationExpectation(
                id=_stable_id("verify-stp-behavior", action_id),
                kind=ControlPlaneVerificationKind.END_TO_END_REACHABILITY,
                action_id=action_id,
                device_id=device_id,
                required_capability=ControlPlaneCapabilityDimension.STP_BEHAVIOR,
                expected={"loop_free": True, "forwarding_converged": True},
                depends_on=[action_id],
            ))

        participating_links = [
            (link, device_a_id, device_b_id)
            for link, device_a_id, device_b_id in domain_l2_links
            if device_a_id in global_by_device and device_b_id in global_by_device
        ]
        for link, device_a_id, device_b_id in participating_links:
            if link.id:
                self._foundation(foundations, "link", link.id)
            if not self._has_alternate_l2_path(
                device_a_id, device_b_id, link, participating_links,
            ):
                continue
            local_device_id, peer_device_id = sorted((device_a_id, device_b_id))
            dependency_ids = sorted({
                global_by_device[device_a_id],
                global_by_device[device_b_id],
            })
            expectations.append(ControlPlaneVerificationExpectation(
                id=_stable_id("verify-stp-failover", policy.id, link.id),
                kind=ControlPlaneVerificationKind.LINK_FAILURE_CONVERGENCE,
                action_id=global_by_device[local_device_id],
                device_id=local_device_id,
                peer_device_id=peer_device_id,
                source_link_id=link.id,
                required_capability=ControlPlaneCapabilityDimension.STP_FAILOVER,
                expected={"link_down": True, "alternate_path": True},
                depends_on=dependency_ids,
            ))

        trunk_ports = {
            (item.device_id, item.interface)
            for item in configuration.actions if isinstance(item, ConfigureTrunk)
        }
        access_actions = sorted(
            (
                item for item in configuration.actions
                if isinstance(item, ConfigureAccessPort)
            ),
            key=lambda item: (item.device_id, item.interface, item.id),
        )
        for access in access_actions:
            if access.device_id not in global_by_device:
                continue
            access_port = (access.device_id, access.interface)
            if access_port in trunk_ports or access_port in physical_non_edge_ports:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_PORTFAST_TRUNK_CONFLICT,
                    (
                        f"{access.device_id}:{access.interface} is marked as E5 access "
                        "but is a trunk, switch-to-switch, or EtherChannel member port."
                    ),
                    access.id,
                ))
                continue
            device = devices[access.device_id]
            edge_id = _stable_id("stp-edge", access.device_id, access.interface)
            actions.append(ConfigureStpEdgePort(
                id=edge_id,
                phase=ControlPlanePhase.L2_RESILIENCY,
                device_id=access.device_id,
                device_name=device.name,
                model=device.model,
                site_id=device.site_id,
                depends_on=[global_by_device[access.device_id]],
                required_capability=capability,
                interface=access.interface,
                portfast=policy.portfast_access_ports,
                bpduguard=policy.bpduguard_access_ports,
                source_access_action_id=access.id,
            ))
            self._foundation(foundations, "access_port", access.id)
        return actions, expectations, global_by_device

    @staticmethod
    def _has_alternate_l2_path(
        source_device_id: str,
        target_device_id: str,
        removed_link: LinkPlan,
        links: list[tuple[LinkPlan, str, str]],
    ) -> bool:
        adjacency: dict[str, set[str]] = defaultdict(set)
        for link, device_a_id, device_b_id in links:
            if link is removed_link:
                continue
            adjacency[device_a_id].add(device_b_id)
            adjacency[device_b_id].add(device_a_id)

        pending = [source_device_id]
        visited: set[str] = set()
        while pending:
            device_id = pending.pop()
            if device_id == target_device_id:
                return True
            if device_id in visited:
                continue
            visited.add(device_id)
            pending.extend(sorted(adjacency[device_id] - visited, reverse=True))
        return False

    @staticmethod
    def _stp_device_key(
        device: DevicePlan | None, device_id: str,
    ) -> tuple[int, str]:
        if device is None:
            return (99, device_id)
        layer = device.network_layer.casefold()
        rank = next((value for name, value in _LAYER_RANK.items() if name in layer), 50)
        return (rank, device_id)

    def _compile_etherchannels(
        self,
        intent: ControlPlaneIntent,
        topology: TopologyPlan,
        configuration: ConfigurationPlan,
        devices: dict[str, DevicePlan],
        names_to_ids: dict[str, str],
        links: dict[str, LinkPlan],
        stp_by_device: dict[str, str],
        foundations: dict[str, ControlPlaneFoundationRequirement],
        issues: list[ConfigurationIssue],
    ) -> tuple[list[ControlPlaneAction], list[ControlPlaneVerificationExpectation]]:
        del topology
        trunk_candidates: dict[tuple[str, str], list[ConfigureTrunk]] = defaultdict(list)
        for item in configuration.actions:
            if isinstance(item, ConfigureTrunk):
                trunk_candidates[(item.device_id, item.interface)].append(item)
        for (device_id, interface), candidates in sorted(trunk_candidates.items()):
            if len(candidates) > 1:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_ETHERCHANNEL_CONFLICT,
                    f"Physical port {device_id}:{interface} has multiple E5 trunk "
                    f"identities: {sorted(item.id for item in candidates)}.",
                    device_id,
                ))
        trunks = {
            key: sorted(values, key=lambda item: item.id)[0]
            for key, values in trunk_candidates.items()
        }
        access_ports = {
            (item.device_id, item.interface)
            for item in configuration.actions if isinstance(item, ConfigureAccessPort)
        }
        used_links: dict[str, str] = {}
        used_ports: dict[tuple[str, str], str] = {}
        actions: list[ControlPlaneAction] = []
        expectations: list[ControlPlaneVerificationExpectation] = []
        capability = {
            EtherChannelProtocol.LACP:
                ControlPlaneCapabilityDimension.ETHERCHANNEL_LACP_CONFIG,
            EtherChannelProtocol.PAGP:
                ControlPlaneCapabilityDimension.ETHERCHANNEL_PAGP_CONFIG,
            EtherChannelProtocol.STATIC:
                ControlPlaneCapabilityDimension.ETHERCHANNEL_STATIC_CONFIG,
        }
        channel_groups = self._allocated_numbers(
            [(item.id, item.channel_group) for item in intent.etherchannels], 1, 255,
            ConfigurationIssueCode.CONTROL_PLANE_ETHERCHANNEL_CONFLICT, issues,
        )
        for policy in sorted(intent.etherchannels, key=lambda item: item.id):
            if policy.id not in channel_groups:
                continue
            channel_group = channel_groups[policy.id]
            member_ids = sorted(set(policy.member_link_ids))
            if len(member_ids) < 2:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_ETHERCHANNEL_MEMBER_INVALID,
                    "EtherChannel requires at least two distinct E4 member links.",
                    policy.id,
                ))
                continue
            if any(link_id not in links for link_id in member_ids):
                missing = sorted(set(member_ids) - set(links))
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_LINK_MISSING,
                    f"Unknown E4 EtherChannel links: {missing}.", policy.id,
                ))
                continue
            link_roles = {
                (links[link_id].link_role.casefold(), links[link_id].network_layer.casefold())
                for link_id in member_ids
            }
            if len(link_roles) != 1:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_ETHERCHANNEL_MEMBER_INVALID,
                    "EtherChannel members must have identical E4 link-role semantics.",
                    policy.id,
                ))
                continue
            collision = next(
                (link_id for link_id in member_ids if link_id in used_links), None,
            )
            if collision:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_ETHERCHANNEL_CONFLICT,
                    f"E4 link {collision} already belongs to {used_links[collision]}.",
                    policy.id,
                ))
                continue
            pairs = {
                frozenset(_link_device_ids(links[link_id], names_to_ids))
                for link_id in member_ids
            }
            if len(pairs) != 1 or any("" in pair for pair in pairs):
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_ETHERCHANNEL_MEMBER_INVALID,
                    "All EtherChannel members must join the same two E4 devices.",
                    policy.id,
                ))
                continue
            pair = sorted(next(iter(pairs)))
            if len(pair) != 2 or any(device_id not in devices for device_id in pair):
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_ETHERCHANNEL_MEMBER_INVALID,
                    "EtherChannel member endpoints are not two known E4 devices.",
                    policy.id,
                ))
                continue
            member_ports: list[tuple[str, str]] = []
            local_port_owner: dict[tuple[str, str], str] = {}
            invalid_port = False
            for link_id in member_ids:
                link = links[link_id]
                a_id, b_id = _link_device_ids(link, names_to_ids)
                for port_key in ((a_id, link.port_a), (b_id, link.port_b)):
                    previous_link = local_port_owner.get(port_key)
                    if previous_link is not None:
                        issues.append(_error(
                            ConfigurationIssueCode.CONTROL_PLANE_ETHERCHANNEL_MEMBER_INVALID,
                            f"Physical port {port_key[0]}:{port_key[1]} is reused by "
                            f"{previous_link!r} and {link_id!r}.",
                            policy.id,
                        ))
                        invalid_port = True
                    previous_bundle = used_ports.get(port_key)
                    if previous_bundle is not None:
                        issues.append(_error(
                            ConfigurationIssueCode.CONTROL_PLANE_ETHERCHANNEL_CONFLICT,
                            f"Physical port {port_key[0]}:{port_key[1]} already belongs "
                            f"to {previous_bundle!r}.",
                            policy.id,
                        ))
                        invalid_port = True
                    local_port_owner[port_key] = link_id
                    member_ports.append(port_key)
            if invalid_port:
                continue
            local_data: dict[str, list[tuple[str, ConfigureTrunk]]] = defaultdict(list)
            invalid = False
            for link_id in member_ids:
                link = links[link_id]
                a_id, b_id = _link_device_ids(link, names_to_ids)
                for device_id, interface in ((a_id, link.port_a), (b_id, link.port_b)):
                    trunk = trunks.get((device_id, interface))
                    if trunk is None or trunk.source_link_id != link_id:
                        issues.append(_error(
                            ConfigurationIssueCode.CONTROL_PLANE_ETHERCHANNEL_TRUNK_MISSING,
                            f"{device_id}:{interface} lacks an E5 trunk bound to {link_id}.",
                            policy.id,
                        ))
                        invalid = True
                        continue
                    if (device_id, interface) in access_ports:
                        issues.append(_error(
                            ConfigurationIssueCode.CONTROL_PLANE_PORTFAST_TRUNK_CONFLICT,
                            f"EtherChannel member {device_id}:{interface} is an E5 access port.",
                            policy.id,
                        ))
                        invalid = True
                    local_data[device_id].append((interface, trunk))
            if invalid:
                continue
            signatures = {
                (tuple(item.allowed_vlans), item.native_vlan_id)
                for values in local_data.values() for _, item in values
            }
            if len(signatures) != 1:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_ETHERCHANNEL_CONFLICT,
                    "EtherChannel E5 member trunks must have identical VLAN semantics.",
                    policy.id,
                ))
                continue
            allowed, native = next(iter(signatures))
            for device_id in pair:
                device = devices[device_id]
                values = sorted(local_data[device_id], key=lambda item: item[0])
                action_id = _stable_id("etherchannel", policy.id, device_id)
                action = ConfigureEtherChannel(
                    id=action_id,
                    phase=ControlPlanePhase.L2_RESILIENCY,
                    device_id=device_id,
                    device_name=device.name,
                    model=device.model,
                    site_id=device.site_id,
                    depends_on=[stp_by_device[device_id]] if device_id in stp_by_device else [],
                    required_capability=capability[policy.protocol],
                    etherchannel_id=policy.id,
                    peer_device_id=pair[1] if pair[0] == device_id else pair[0],
                    protocol=policy.protocol,
                    channel_group=channel_group,
                    port_channel_interface=f"Port-channel{channel_group}",
                    member_interfaces=[interface for interface, _ in values],
                    allowed_vlans=list(allowed),
                    native_vlan_id=native,
                    source_link_ids=member_ids,
                    source_trunk_action_ids=[item.id for _, item in values],
                )
                actions.append(action)
                expectations.append(ControlPlaneVerificationExpectation(
                    id=_stable_id("verify-etherchannel", action_id),
                    kind=ControlPlaneVerificationKind.ETHERCHANNEL_STATE,
                    action_id=action_id,
                    device_id=device_id,
                    peer_device_id=action.peer_device_id,
                    required_capability=
                        ControlPlaneCapabilityDimension.ETHERCHANNEL_STATE,
                    expected={
                        "protocol": policy.protocol.value,
                        "member_interfaces": action.member_interfaces,
                        "port_channel_interface": action.port_channel_interface,
                    },
                    depends_on=[action_id],
                ))
                expectations.append(ControlPlaneVerificationExpectation(
                    id=_stable_id("verify-etherchannel-behavior", action_id),
                    kind=ControlPlaneVerificationKind.END_TO_END_REACHABILITY,
                    action_id=action_id,
                    device_id=device_id,
                    peer_device_id=action.peer_device_id,
                    required_capability=
                        ControlPlaneCapabilityDimension.ETHERCHANNEL_BEHAVIOR,
                    expected={"reachable": True, "bundled": True},
                    depends_on=[action_id],
                ))
                for _, trunk in values:
                    self._foundation(foundations, "trunk", trunk.id)
            for link_id in member_ids:
                used_links[link_id] = policy.id
                self._foundation(foundations, "link", link_id)
            for port_key in member_ports:
                used_ports[port_key] = policy.id
        return actions, expectations

    def _compile_hsrp(
        self,
        intent: ControlPlaneIntent,
        configuration: ConfigurationPlan,
        devices: dict[str, DevicePlan],
        foundations: dict[str, ControlPlaneFoundationRequirement],
        issues: list[ConfigurationIssue],
    ) -> tuple[list[ControlPlaneAction], list[ControlPlaneVerificationExpectation]]:
        l3_by_segment: dict[str, list[object]] = defaultdict(list)
        gateways: dict[str, set[str]] = defaultdict(set)
        endpoints_by_segment: dict[str, list[SetEndpointStaticAddress]] = defaultdict(list)
        assigned_ipv4: dict[str, str] = {}
        for action in configuration.actions:
            if isinstance(action, _L3_ACTIONS):
                l3_by_segment[action.segment_id].append(action)
                assigned_ipv4[action.ipv4] = action.id
            elif isinstance(action, ConfigureDhcpPool):
                gateways[action.segment_id].add(action.gateway)
            elif isinstance(action, SetEndpointStaticAddress):
                endpoints_by_segment[action.segment_id].append(action)
                assigned_ipv4[action.ipv4] = action.id
                if action.gateway:
                    gateways[action.segment_id].add(action.gateway)
            elif isinstance(action, SetEndpointDhcp) and action.gateway:
                gateways[action.segment_id].add(action.gateway)
        actions: list[ControlPlaneAction] = []
        expectations: list[ControlPlaneVerificationExpectation] = []
        virtual_ip_owners: dict[str, str] = {}
        group_numbers = self._allocated_numbers(
            [
                (item.id, item.group_number)
                for item in intent.first_hop_redundancy
            ],
            0,
            255,
            ConfigurationIssueCode.CONTROL_PLANE_INTENT_INVALID,
            issues,
        )
        for policy in sorted(intent.first_hop_redundancy, key=lambda item: item.id):
            if policy.id not in group_numbers:
                continue
            group_number = group_numbers[policy.id]
            candidates = {
                item.device_id: item for item in sorted(
                    l3_by_segment.get(policy.segment_id, []), key=lambda item: item.id,
                ) if item.device_id in set(policy.device_ids)
            }
            missing = sorted(set(policy.device_ids) - set(candidates))
            if missing:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_HSRP_FOUNDATION_MISSING,
                    f"HSRP devices lack E5 L3 identity for {policy.segment_id}: {missing}.",
                    policy.id,
                ))
                continue
            inferred = sorted(gateways.get(policy.segment_id, set()))
            if policy.virtual_ipv4:
                virtual = policy.virtual_ipv4
            elif len(inferred) == 1:
                virtual = inferred[0]
            else:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_HSRP_FOUNDATION_MISSING,
                    "HSRP requires an explicit VIP or one unambiguous E5 gateway.",
                    policy.id,
                ))
                continue
            try:
                vip = ipaddress.IPv4Address(virtual)
            except ipaddress.AddressValueError:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_HSRP_VIP_INVALID,
                    f"Invalid HSRP virtual IPv4 {virtual!r}.", policy.id,
                ))
                continue
            if str(vip) in assigned_ipv4:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_HSRP_VIP_COLLISION,
                    f"HSRP VIP {vip} collides with E5 address action "
                    f"{assigned_ipv4[str(vip)]!r}.",
                    policy.id,
                ))
                continue
            previous_owner = virtual_ip_owners.get(str(vip))
            if previous_owner is not None:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_HSRP_VIP_COLLISION,
                    f"HSRP VIP {vip} is shared by {previous_owner!r} and {policy.id!r}.",
                    policy.id,
                ))
                continue
            if any(vip not in _network_of(item) for item in candidates.values()):
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_HSRP_VIP_INVALID,
                    f"HSRP VIP {vip} is outside an E5 participant subnet.",
                    policy.id,
                ))
                continue
            virtual_ip_owners[str(vip)] = policy.id
            ordered_ids = sorted(set(policy.device_ids))
            priorities = {
                device_id: policy.priority_by_device.get(
                    device_id, 110 if index == 0 else 100,
                )
                for index, device_id in enumerate(ordered_ids)
            }
            role_order = sorted(
                ordered_ids,
                key=lambda device_id: (
                    priorities[device_id],
                    int(ipaddress.IPv4Address(candidates[device_id].ipv4)),
                    device_id,
                ),
                reverse=True,
            )
            preferred_active = role_order[0]
            expected_roles = {
                device_id: (
                    "active" if index == 0 else "standby" if index == 1 else "listen"
                )
                for index, device_id in enumerate(role_order)
            }
            group_action_ids: dict[str, str] = {}
            for index, device_id in enumerate(ordered_ids):
                device = devices.get(device_id)
                if device is None:
                    issues.append(_error(
                        ConfigurationIssueCode.CONTROL_PLANE_HSRP_FOUNDATION_MISSING,
                        f"HSRP device {device_id!r} is absent from E4.", policy.id,
                    ))
                    continue
                foundation = candidates[device_id]
                action_id = _stable_id("hsrp", policy.id, device_id)
                action = ConfigureHsrp(
                    id=action_id,
                    phase=ControlPlanePhase.L3_RESILIENCY,
                    device_id=device_id,
                    device_name=device.name,
                    model=device.model,
                    site_id=device.site_id,
                    required_capability=ControlPlaneCapabilityDimension.HSRP_CONFIG,
                    redundancy_id=policy.id,
                    interface=_interface_of(foundation),
                    segment_id=policy.segment_id,
                    group_number=group_number,
                    virtual_ipv4=str(vip),
                    physical_ipv4=foundation.ipv4,
                    priority=priorities[device_id],
                    preempt=policy.preempt,
                    source_configuration_action_id=foundation.id,
                )
                actions.append(action)
                group_action_ids[device_id] = action_id
                self._foundation(foundations, "l3_interface", foundation.id)
                expectations.append(ControlPlaneVerificationExpectation(
                    id=_stable_id("verify-hsrp", action_id),
                    kind=ControlPlaneVerificationKind.HSRP_STATE,
                    action_id=action_id,
                    device_id=device_id,
                    required_capability=ControlPlaneCapabilityDimension.HSRP_STATE,
                    expected={
                        "group": group_number,
                        "virtual_ipv4": str(vip),
                        "preempt": policy.preempt,
                        "expected_role": expected_roles[device_id],
                        "preferred_active_device_id": preferred_active,
                    },
                    depends_on=[action_id],
                ))
            endpoint = next(iter(sorted(
                endpoints_by_segment.get(policy.segment_id, []),
                key=lambda item: (item.device_id, item.id),
            )), None)
            if endpoint is not None and preferred_active in group_action_ids:
                anchor = group_action_ids[preferred_active]
                expectations.append(ControlPlaneVerificationExpectation(
                    id=_stable_id("verify-hsrp-behavior", policy.id, endpoint.device_id),
                    kind=ControlPlaneVerificationKind.END_TO_END_REACHABILITY,
                    action_id=anchor,
                    device_id=endpoint.device_id,
                    peer_device_id=preferred_active,
                    required_capability=ControlPlaneCapabilityDimension.HSRP_BEHAVIOR,
                    expected={
                        "destination_ipv4": str(vip),
                        "virtual_gateway_ipv4": str(vip),
                        "reachable": True,
                    },
                    depends_on=sorted(group_action_ids.values()),
                ))
        return actions, expectations

    def _compile_routing(
        self,
        intent: ControlPlaneIntent,
        topology: TopologyPlan,
        configuration: ConfigurationPlan,
        devices: dict[str, DevicePlan],
        names_to_ids: dict[str, str],
        links: dict[str, LinkPlan],
        foundations: dict[str, ControlPlaneFoundationRequirement],
        issues: list[ConfigurationIssue],
    ) -> tuple[list[ControlPlaneAction], list[ControlPlaneVerificationExpectation]]:
        policies = [*intent.routing_domains]
        if intent.routing is not None and intent.routing.id not in {item.id for item in policies}:
            policies.append(intent.routing)
        actions: list[ControlPlaneAction] = []
        expectations: list[ControlPlaneVerificationExpectation] = []
        used_devices: dict[str, str] = {}
        for policy in sorted(policies, key=lambda item: item.id):
            domain_actions, domain_expectations = self._compile_routing_domain(
                policy, topology, configuration, devices, names_to_ids, links,
                foundations, issues,
            )
            for action in domain_actions:
                if action.device_id in used_devices:
                    issues.append(_error(
                        ConfigurationIssueCode.CONTROL_PLANE_INTENT_INVALID,
                        f"Routing domains {used_devices[action.device_id]!r} and {policy.id!r} "
                        f"overlap on {action.device_id!r}; redistribution is outside E9.",
                        policy.id,
                    ))
                used_devices[action.device_id] = policy.id
            actions.extend(domain_actions)
            expectations.extend(domain_expectations)
        return actions, expectations

    def _compile_routing_domain(
        self,
        policy,
        topology: TopologyPlan,
        configuration: ConfigurationPlan,
        devices: dict[str, DevicePlan],
        names_to_ids: dict[str, str],
        links: dict[str, LinkPlan],
        foundations: dict[str, ControlPlaneFoundationRequirement],
        issues: list[ConfigurationIssue],
    ) -> tuple[list[ControlPlaneAction], list[ControlPlaneVerificationExpectation]]:
        del topology
        l3_by_device: dict[str, list[object]] = defaultdict(list)
        static_endpoints_by_segment: dict[str, list[SetEndpointStaticAddress]] = defaultdict(list)
        for action in configuration.actions:
            if isinstance(action, _L3_ACTIONS):
                device = devices.get(action.device_id)
                if policy.site_id and (device is None or device.site_id != policy.site_id):
                    continue
                l3_by_device[action.device_id].append(action)
            elif isinstance(action, SetEndpointStaticAddress):
                device = devices.get(action.device_id)
                if policy.site_id and (device is None or device.site_id != policy.site_id):
                    continue
                static_endpoints_by_segment[action.segment_id].append(action)
        selected = sorted(set(policy.device_ids or l3_by_device))
        for device_id in selected:
            if device_id not in devices or not l3_by_device.get(device_id):
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_ROUTING_FOUNDATION_MISSING,
                    f"Routing device {device_id!r} lacks E4/E5 L3 identity.", device_id,
                ))

        active_foundations: set[str] = set()
        transit: list[tuple[LinkPlan, object, object]] = []
        if len(selected) > 1 and not policy.transit_link_ids:
            issues.append(_error(
                ConfigurationIssueCode.CONTROL_PLANE_TRANSIT_L3_MISSING,
                "Multi-device dynamic routing requires explicit E4 transit_link_ids.",
                policy.id,
            ))
        for link_id in sorted(set(policy.transit_link_ids)):
            link = links.get(link_id)
            if link is None:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_LINK_MISSING,
                    f"Routing transit link {link_id!r} is absent from E4.", link_id,
                ))
                continue
            a_id, b_id = _link_device_ids(link, names_to_ids)
            a_action = self._l3_on_interface(l3_by_device.get(a_id, []), link.port_a)
            b_action = self._l3_on_interface(l3_by_device.get(b_id, []), link.port_b)
            if a_action is None or b_action is None:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_TRANSIT_L3_MISSING,
                    f"Transit {link_id} requires E5 L3 identities on both exact E4 ports.",
                    link_id,
                ))
                continue
            if _network_of(a_action) != _network_of(b_action):
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_TRANSIT_SUBNET_MISMATCH,
                    f"Transit {link_id} E5 endpoints are in different IPv4 networks.",
                    link_id,
                ))
                continue
            active_foundations.update((a_action.id, b_action.id))
            transit.append((link, a_action, b_action))
            self._foundation(foundations, "link", link.id)

        action_by_device: dict[str, ControlPlaneAction] = {}
        router_ids: dict[str, str] = {}
        for device_id in selected:
            device = devices.get(device_id)
            local = sorted(
                l3_by_device.get(device_id, []),
                key=lambda item: (_network_of(item).network_address, _interface_of(item), item.id),
            )
            if device is None or not local:
                continue
            passive = sorted({
                _interface_of(item) for item in local
                if item.id not in active_foundations
                or item.segment_id in set(policy.passive_segment_ids)
            })
            if policy.protocol is DynamicRoutingProtocol.RIPV2:
                # RIP no tiene router ID: no se calcula ni se comprueba una
                # colisión que el protocolo no puede sufrir.
                rip_action = self._rip_action(
                    policy, device, device_id, local, passive, foundations, issues,
                )
                if rip_action is not None:
                    action_by_device[device_id] = rip_action
                continue
            router_id = policy.router_ids.get(device_id, "")
            if not router_id:
                router_id = str(min(ipaddress.ip_address(item.ipv4) for item in local))
            try:
                router_id = str(ipaddress.IPv4Address(router_id))
            except ipaddress.AddressValueError:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_INTENT_INVALID,
                    f"Invalid router ID {router_id!r} for {device_id}.", device_id,
                ))
                continue
            router_ids[device_id] = router_id
            networks: list[RoutingNetwork] = []
            seen_networks: set[tuple[str, str, int | None]] = set()
            for foundation in local:
                network = _network_of(foundation)
                area = (
                    policy.area_by_segment.get(foundation.segment_id, 0)
                    if policy.protocol is DynamicRoutingProtocol.OSPFV2 else None
                )
                key = (str(network.network_address), _wildcard(network), area)
                if key in seen_networks:
                    continue
                seen_networks.add(key)
                networks.append(RoutingNetwork(
                    network=str(network.network_address),
                    wildcard=_wildcard(network),
                    area=area,
                    segment_id=foundation.segment_id,
                    interface=_interface_of(foundation),
                    source_configuration_action_id=foundation.id,
                ))
                self._foundation(foundations, "l3_interface", foundation.id)
            networks.sort(key=lambda item: (
                ipaddress.ip_address(item.network), item.wildcard,
                item.area if item.area is not None else -1, item.interface,
            ))
            if policy.protocol is DynamicRoutingProtocol.OSPFV2:
                action_id = _stable_id(
                    "ospfv2", policy.id, device_id, policy.process_id,
                )
                action: ControlPlaneAction = ConfigureOspfv2(
                    id=action_id,
                    phase=ControlPlanePhase.DYNAMIC_ROUTING,
                    device_id=device_id,
                    device_name=device.name,
                    model=device.model,
                    site_id=device.site_id,
                    required_capability=ControlPlaneCapabilityDimension.OSPFV2_CONFIG,
                    process_id=policy.process_id,
                    router_id=router_id,
                    networks=networks,
                    passive_interfaces=passive,
                )
            else:
                action_id = _stable_id(
                    "eigrp-ipv4", policy.id, device_id, policy.eigrp_as_number,
                )
                action = ConfigureEigrpIpv4(
                    id=action_id,
                    phase=ControlPlanePhase.DYNAMIC_ROUTING,
                    device_id=device_id,
                    device_name=device.name,
                    model=device.model,
                    site_id=device.site_id,
                    required_capability=ControlPlaneCapabilityDimension.EIGRP_IPV4_CONFIG,
                    as_number=policy.eigrp_as_number,
                    router_id=router_id,
                    networks=networks,
                    passive_interfaces=passive,
                )
            action_by_device[device_id] = action

        collisions: dict[str, list[str]] = defaultdict(list)
        for device_id, router_id in router_ids.items():
            collisions[router_id].append(device_id)
        for router_id, device_ids in sorted(collisions.items()):
            if len(device_ids) > 1:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_ROUTER_ID_COLLISION,
                    f"Router ID {router_id} is shared by {sorted(device_ids)}.", router_id,
                ))

        actions = [action_by_device[key] for key in sorted(action_by_device)]
        expectations: list[ControlPlaneVerificationExpectation] = []
        if policy.protocol is DynamicRoutingProtocol.RIPV2:
            # Verificación de CONFIGURACIÓN: el estado semántico intencionado
            # frente al leído. Vecindad, rutas aprendidas y alcance extremo a
            # extremo son comportamiento y no se compilan en esta etapa.
            for action in actions:
                expectations.append(ControlPlaneVerificationExpectation(
                    id=_stable_id("verify-rip-process", action.id),
                    kind=ControlPlaneVerificationKind.ROUTING_PROCESS,
                    action_id=action.id,
                    device_id=action.device_id,
                    required_capability=
                        ControlPlaneCapabilityDimension.ROUTING_PROCESS_STATE,
                    expected={
                        "protocol": DynamicRoutingProtocol.RIPV2.value,
                        "version_send": action.version,
                        "version_recv": action.version,
                        "auto_summary": not action.no_auto_summary,
                        "networks": [item.network for item in action.networks],
                        "passive_interfaces": list(action.passive_interfaces),
                    },
                    depends_on=[action.id],
                ))
            # Rutas APRENDIDAS. El prefijo esperado sale de las identidades L3
            # de E5, no de `RipNetwork`, que es classful y no sabe nada de la
            # /27 ni de la /28 reales. Un prefijo conectado localmente nunca
            # puede satisfacer esto: se descuenta antes de emitir nada.
            connected: dict[str, set] = {
                device_id: {
                    _network_of(item) for item in l3_by_device.get(device_id, [])
                }
                for device_id in action_by_device
            }
            for local_id, local_action in sorted(action_by_device.items()):
                for remote_id, remote_action in sorted(action_by_device.items()):
                    if local_id == remote_id:
                        continue
                    remote_only = sorted(
                        connected[remote_id] - connected[local_id],
                        key=lambda item: (item.network_address, item.prefixlen),
                    )
                    for network in remote_only:
                        expectations.append(ControlPlaneVerificationExpectation(
                            id=_stable_id(
                                "verify-rip-route", local_id,
                                str(network.network_address), network.prefixlen,
                            ),
                            kind=ControlPlaneVerificationKind.ROUTE_PRESENT,
                            action_id=local_action.id,
                            device_id=local_id,
                            peer_device_id=remote_id,
                            required_capability=
                                ControlPlaneCapabilityDimension.ROUTING_ROUTE_STATE,
                            expected={
                                "network": str(network.network_address),
                                "prefix_length": network.prefixlen,
                                "protocol": DynamicRoutingProtocol.RIPV2.value,
                            },
                            depends_on=sorted([local_action.id, remote_action.id]),
                        ))
            return actions, expectations
        for action in actions:
            expectations.append(ControlPlaneVerificationExpectation(
                id=_stable_id("verify-routing-process", action.id),
                kind=ControlPlaneVerificationKind.ROUTING_PROCESS,
                action_id=action.id,
                device_id=action.device_id,
                required_capability=
                    ControlPlaneCapabilityDimension.ROUTING_PROCESS_STATE,
                expected={
                    "protocol": policy.protocol.value,
                    "router_id": action.router_id,
                },
                depends_on=[action.id],
            ))
        for link, left, right in transit:
            for local, peer in ((left, right), (right, left)):
                action = action_by_device.get(local.device_id)
                if action is None:
                    continue
                expectations.append(ControlPlaneVerificationExpectation(
                    id=_stable_id("verify-neighbor", link.id, local.device_id),
                    kind=ControlPlaneVerificationKind.ROUTING_NEIGHBOR,
                    action_id=action.id,
                    device_id=local.device_id,
                    peer_device_id=peer.device_id,
                    source_link_id=link.id,
                    required_capability=
                        ControlPlaneCapabilityDimension.ROUTING_NEIGHBOR_STATE,
                    expected={
                        "peer_ipv4": peer.ipv4,
                        "peer_router_id": router_ids.get(peer.device_id, ""),
                        "protocol": policy.protocol.value,
                        "adjacent": True,
                    },
                    depends_on=[action.id],
                ))
        for local_id, local_action in sorted(action_by_device.items()):
            local_networks = {
                item.network for item in local_action.networks
            }
            for remote_id, remote_action in sorted(action_by_device.items()):
                if local_id == remote_id:
                    continue
                for remote in remote_action.networks:
                    if remote.network in local_networks:
                        continue
                    expectations.append(ControlPlaneVerificationExpectation(
                        id=_stable_id(
                            "verify-route", local_id, remote.network, remote.wildcard,
                        ),
                        kind=ControlPlaneVerificationKind.ROUTE_PRESENT,
                        action_id=local_action.id,
                        device_id=local_id,
                        peer_device_id=remote_id,
                        required_capability=
                            ControlPlaneCapabilityDimension.ROUTING_ROUTE_STATE,
                        expected={
                            "network": remote.network,
                            "wildcard": remote.wildcard,
                            "prefix_length": _prefix_length_from_wildcard(
                                remote.wildcard
                            ),
                            "segment_id": remote.segment_id,
                            "protocol": policy.protocol.value,
                        },
                        depends_on=[local_action.id, remote_action.id],
                    ))
                local_endpoints = sorted(
                    (
                        endpoint
                        for network in local_action.networks
                        for endpoint in static_endpoints_by_segment.get(
                            network.segment_id, []
                        )
                    ),
                    key=lambda item: (item.device_id, item.id),
                )
                remote_endpoints = sorted(
                    (
                        endpoint
                        for network in remote_action.networks
                        if network.network not in local_networks
                        for endpoint in static_endpoints_by_segment.get(
                            network.segment_id, []
                        )
                    ),
                    key=lambda item: (item.device_id, item.id),
                )
                source_device_id = local_id
                destination_device_id = remote_id
                if local_endpoints and remote_endpoints:
                    source_device_id = local_endpoints[0].device_id
                    destination_device_id = remote_endpoints[0].device_id
                    destination = remote_endpoints[0].ipv4
                else:
                    destination = next(
                        (item.ipv4 for item in sorted(
                            l3_by_device[remote_id], key=lambda candidate: candidate.id,
                        ) if item.id not in active_foundations),
                        sorted(
                            l3_by_device[remote_id], key=lambda candidate: candidate.id,
                        )[0].ipv4,
                    )
                expectations.append(ControlPlaneVerificationExpectation(
                    id=_stable_id(
                        "verify-reachability", source_device_id,
                        destination_device_id, destination,
                    ),
                    kind=ControlPlaneVerificationKind.END_TO_END_REACHABILITY,
                    action_id=local_action.id,
                    device_id=source_device_id,
                    peer_device_id=destination_device_id,
                    required_capability=
                        ControlPlaneCapabilityDimension.ROUTING_BEHAVIOR,
                    expected={
                        "destination_ipv4": destination,
                        "reachable": True,
                        "protocol": policy.protocol.value,
                    },
                    depends_on=sorted([local_action.id, remote_action.id]),
                ))
        return actions, expectations

    def _rip_action(
        self,
        policy,
        device: DevicePlan,
        device_id: str,
        local: list[object],
        passive: list[str],
        foundations: dict[str, ControlPlaneFoundationRequirement],
        issues: list[ConfigurationIssue],
    ) -> ConfigureRipv2 | None:
        """Colapsa las identidades L3 del dispositivo en sentencias classful."""
        segments: dict[str, set[str]] = defaultdict(set)
        sources: dict[str, set[str]] = defaultdict(set)
        contributing: list[object] = []
        for foundation in local:
            classful = _classful_network(_network_of(foundation))
            if classful is None:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_ROUTING_FOUNDATION_MISSING,
                    f"{_interface_of(foundation)} on {device_id} has no classful "
                    "RIP network statement.",
                    foundation.id,
                ))
                continue
            segments[classful].add(foundation.segment_id)
            sources[classful].add(foundation.id)
            contributing.append(foundation)
        if not segments:
            issues.append(_error(
                ConfigurationIssueCode.CONTROL_PLANE_ROUTING_FOUNDATION_MISSING,
                f"RIPv2 device {device_id!r} compiled no network statement.",
                device_id,
            ))
            return None
        for foundation in contributing:
            self._foundation(foundations, "l3_interface", foundation.id)
        networks = [
            RipNetwork(
                network=classful,
                source_segment_ids=sorted(segments[classful]),
                source_configuration_action_ids=sorted(sources[classful]),
            )
            for classful in sorted(segments, key=ipaddress.ip_address)
        ]
        return ConfigureRipv2(
            id=_stable_id("ripv2", policy.id, device_id),
            phase=ControlPlanePhase.DYNAMIC_ROUTING,
            device_id=device_id,
            device_name=device.name,
            model=device.model,
            site_id=device.site_id,
            required_capability=ControlPlaneCapabilityDimension.RIPV2_CONFIG,
            networks=networks,
            passive_interfaces=passive,
        )

    @staticmethod
    def _l3_on_interface(actions: list[object], interface: str):
        return next(
            (item for item in sorted(actions, key=lambda item: item.id)
             if _interface_of(item) == interface),
            None,
        )

    def _compile_failure_scenarios(
        self,
        intent: ControlPlaneIntent,
        configuration: ConfigurationPlan,
        devices: dict[str, DevicePlan],
        names_to_ids: dict[str, str],
        links: dict[str, LinkPlan],
        actions: list[ControlPlaneAction],
        foundations: dict[str, ControlPlaneFoundationRequirement],
        failure_domain_catalog: FailureDomainCatalog,
        issues: list[ConfigurationIssue],
    ) -> tuple[list[LinkFailureScenario], list[ControlPlaneVerificationExpectation]]:
        scenarios: list[LinkFailureScenario] = []
        expectations: list[ControlPlaneVerificationExpectation] = []
        address_actions = {
            item.device_id: item
            for item in sorted(configuration.actions, key=lambda item: item.id)
            if isinstance(item, (*_L3_ACTIONS, SetEndpointStaticAddress))
        }
        source_foundations = {
            item.device_id: item
            for item in sorted(configuration.actions, key=lambda item: item.id)
            if isinstance(item, _ENDPOINT_ACTIONS)
        }
        for policy in sorted(intent.failure_scenarios, key=lambda item: item.id):
            link = links.get(policy.link_id)
            if link is None:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_LINK_MISSING,
                    f"Failure link {policy.link_id!r} is absent from E4.", policy.id,
                ))
                continue
            if not policy.restore_required:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_FAILURE_RESTORE_REQUIRED,
                    "Every E9 link failure scenario must require typed restoration.",
                    policy.id,
                ))
                continue
            missing_survivors = sorted(
                set(policy.expected_surviving_link_ids) - set(links)
            )
            if missing_survivors:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_LINK_MISSING,
                    f"Unknown surviving E4 links: {missing_survivors}.", policy.id,
                ))
                continue
            if (
                policy.probe_source_device_id not in devices
                or policy.probe_destination_device_id not in devices
            ):
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_INTENT_INVALID,
                    "Failure probe endpoints must be existing E4 devices.", policy.id,
                ))
                continue
            destination_address = address_actions.get(
                policy.probe_destination_device_id
            )
            if destination_address is None:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_FAILURE_PROBE_MISSING,
                    "Failure behavior probe destination requires an immutable E5 "
                    "static or L3 IPv4 identity.",
                    policy.id,
                ))
                continue
            a_id, b_id = _link_device_ids(link, names_to_ids)
            if policy.link_id in set(policy.expected_surviving_link_ids):
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_INTENT_INVALID,
                    "A failed E4 link cannot also be declared as surviving.",
                    policy.id,
                ))
                continue
            if policy.expected_surviving_link_ids and not _links_connect(
                a_id,
                b_id,
                policy.expected_surviving_link_ids,
                links,
                names_to_ids,
            ):
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_INTENT_INVALID,
                    "Expected surviving E4 links do not form an alternate path "
                    f"between {a_id!r} and {b_id!r}.",
                    policy.id,
                ))
                continue
            surviving_devices = sorted({
                device_id
                for survivor_id in policy.expected_surviving_link_ids
                for device_id in _link_device_ids(links[survivor_id], names_to_ids)
                if device_id
            })
            domain_result = FailureDomainAnalyzer().analyze(
                FailureScenario(
                    id=policy.id,
                    scope=FailureScenarioScope.LINK_FAULT,
                    primary_path=FailurePath(
                        id=f"{policy.id}/primary",
                        device_ids=sorted({a_id, b_id}),
                        link_ids=[link.id],
                        endpoint_device_ids=sorted({a_id, b_id}),
                    ),
                    surviving_path=FailurePath(
                        id=f"{policy.id}/surviving",
                        device_ids=surviving_devices,
                        link_ids=sorted(set(policy.expected_surviving_link_ids)),
                        endpoint_device_ids=sorted({a_id, b_id}),
                    ),
                    additional_relevant_domain_types=sorted(
                        set(policy.required_independence_domains),
                        key=lambda item: item.value,
                    ),
                ),
                failure_domain_catalog,
            )
            if domain_result.status is IndependenceStatus.NOT_INDEPENDENT:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_FAILURE_DOMAIN_NOT_INDEPENDENT,
                    "Expected surviving path shares blocking failure domains: "
                    + ", ".join(domain_result.blocking_domain_ids),
                    policy.id,
                ))
                continue
            if domain_result.status is IndependenceStatus.UNKNOWN:
                issues.append(_warning(
                    ConfigurationIssueCode.CONTROL_PLANE_FAILURE_DOMAIN_UNKNOWN,
                    "Failure-domain independence remains UNKNOWN because required "
                    "coverage is incomplete.",
                    policy.id,
                ))
            affected = sorted(
                (
                    item for item in actions
                    if link.id in getattr(item, "source_link_ids", [])
                ),
                key=lambda item: item.id,
            )
            if affected:
                anchor = affected[0].id
                failover_capability = (
                    ControlPlaneCapabilityDimension.ETHERCHANNEL_FAILOVER
                    if policy.expected_surviving_link_ids
                    else ControlPlaneCapabilityDimension.LINK_FAILURE_CONTROL
                )
            else:
                routing = sorted(
                    (
                        item for item in actions
                        if item.device_id in {a_id, b_id}
                        and item.action_type in {
                            ControlPlaneActionType.CONFIGURE_OSPFV2,
                            ControlPlaneActionType.CONFIGURE_EIGRP_IPV4,
                        }
                    ),
                    key=lambda item: item.id,
                )
                hsrp = sorted(
                    (
                        item for item in actions
                        if item.device_id in {a_id, b_id}
                        and item.action_type is ControlPlaneActionType.CONFIGURE_HSRP
                    ),
                    key=lambda item: item.id,
                )
                stp = sorted(
                    (
                        item for item in actions
                        if item.device_id in {a_id, b_id}
                        and item.action_type is ControlPlaneActionType.CONFIGURE_STP
                    ),
                    key=lambda item: item.id,
                )
                selected = routing or hsrp or stp
                anchor = selected[0].id if selected else ""
                if not policy.expected_surviving_link_ids:
                    failover_capability = (
                        ControlPlaneCapabilityDimension.LINK_FAILURE_CONTROL
                    )
                elif routing:
                    failover_capability = ControlPlaneCapabilityDimension.ROUTING_FAILOVER
                elif hsrp:
                    failover_capability = ControlPlaneCapabilityDimension.HSRP_FAILOVER
                elif stp:
                    failover_capability = ControlPlaneCapabilityDimension.STP_FAILOVER
                else:
                    failover_capability = (
                        ControlPlaneCapabilityDimension.LINK_FAILURE_CONTROL
                    )
            failure_id = _stable_id("verify-link-failure", policy.id, link.id)
            restore_id = _stable_id("verify-link-restore", policy.id, link.id)
            dependencies = [anchor] if anchor else []
            expectations.extend([
                ControlPlaneVerificationExpectation(
                    id=failure_id,
                    kind=ControlPlaneVerificationKind.LINK_FAILURE_CONVERGENCE,
                    action_id=anchor,
                    device_id=policy.probe_source_device_id,
                    peer_device_id=policy.probe_destination_device_id,
                    source_link_id=link.id,
                    required_capability=failover_capability,
                    expected={
                        "link_down": True,
                        "reachable": bool(policy.expected_surviving_link_ids),
                        "surviving_link_ids": sorted(
                            set(policy.expected_surviving_link_ids)
                        ),
                        "failure_domain_status": domain_result.status.value,
                        "failure_domain_catalog_hash": failure_domain_catalog.semantic_hash,
                    },
                    depends_on=dependencies,
                ),
                ControlPlaneVerificationExpectation(
                    id=restore_id,
                    kind=ControlPlaneVerificationKind.RESTORE_RECOVERY,
                    action_id=anchor,
                    device_id=policy.probe_source_device_id,
                    peer_device_id=policy.probe_destination_device_id,
                    source_link_id=link.id,
                    required_capability=failover_capability,
                    expected={"link_restored": True, "reachable": True},
                    depends_on=[failure_id],
                ),
            ])
            scenarios.append(LinkFailureScenario(
                id=policy.id,
                link_id=link.id,
                device_a_id=a_id,
                device_b_id=b_id,
                target_device_id=a_id,
                target_device_name=link.device_a,
                target_interface=link.port_a,
                peer_device_id=b_id,
                peer_device_name=link.device_b,
                peer_interface=link.port_b,
                cable=link.cable,
                probe_source_device_id=policy.probe_source_device_id,
                probe_source_device_name=devices[
                    policy.probe_source_device_id
                ].name,
                probe_destination_device_id=policy.probe_destination_device_id,
                probe_destination_device_name=devices[
                    policy.probe_destination_device_id
                ].name,
                probe_destination_ipv4=destination_address.ipv4,
                expected_surviving_link_ids=sorted(
                    set(policy.expected_surviving_link_ids)
                ),
                failure_domain_result=domain_result,
                restore_required=True,
                verification_expectation_ids=[failure_id, restore_id],
            ))
            self._foundation(foundations, "link", link.id)
            destination_kind = (
                "endpoint_address"
                if isinstance(destination_address, SetEndpointStaticAddress)
                else "l3_interface"
            )
            self._foundation(
                foundations, destination_kind, destination_address.id,
            )
            source_foundation = source_foundations.get(
                policy.probe_source_device_id
            )
            if source_foundation is not None:
                self._foundation(
                    foundations, "endpoint_address", source_foundation.id,
                )
            for link_id in policy.expected_surviving_link_ids:
                self._foundation(foundations, "link", link_id)
        return scenarios, expectations

    @staticmethod
    def _allocated_numbers(
        requested: list[tuple[str, int | None]],
        minimum: int,
        maximum: int,
        conflict_code: ConfigurationIssueCode,
        issues: list[ConfigurationIssue],
    ) -> dict[str, int]:
        """Honor explicit numbers and allocate omitted values in stable ID order."""
        result: dict[str, int] = {}
        owners: dict[int, str] = {}
        for item_id, number in sorted(requested):
            if number is None:
                continue
            if number in owners:
                issues.append(_error(
                    conflict_code,
                    f"Numeric identifier {number} is shared by {owners[number]!r} and {item_id!r}.",
                    item_id,
                ))
                continue
            owners[number] = item_id
            result[item_id] = number
        available = (number for number in range(minimum, maximum + 1) if number not in owners)
        for item_id, number in sorted(requested):
            if number is not None:
                continue
            try:
                allocated = next(available)
            except StopIteration:
                issues.append(_error(
                    conflict_code,
                    "No deterministic numeric identifier remains available.", item_id,
                ))
                continue
            owners[allocated] = item_id
            result[item_id] = allocated
        return result

    @staticmethod
    def _gate_capabilities(
        actions: list[ControlPlaneAction],
        expectations: list[ControlPlaneVerificationExpectation],
        capabilities: dict[str, ControlPlaneCapabilityProfile],
        issues: list[ConfigurationIssue],
    ) -> None:
        reported: set[tuple[str, ControlPlaneCapabilityDimension]] = set()
        for action in actions:
            key = (action.model, action.required_capability)
            if key in reported:
                continue
            reported.add(key)
            profile = capabilities.get(action.model)
            status = (
                profile.status(action.required_capability)
                if profile else SecurityCapabilityStatus.UNKNOWN
            )
            if status is SecurityCapabilityStatus.SUPPORTED:
                continue
            if status is SecurityCapabilityStatus.UNSUPPORTED:
                issues.append(_error(
                    ConfigurationIssueCode.CONTROL_PLANE_CAPABILITY_UNSUPPORTED,
                    f"{action.model}:{action.required_capability.value} is unsupported.",
                    action.id,
                    model=action.model,
                    capability=action.required_capability.value,
                ))
            else:
                issues.append(_warning(
                    ConfigurationIssueCode.CONTROL_PLANE_CAPABILITY_UNKNOWN,
                    f"{action.model}:{action.required_capability.value} is {status.value}.",
                    action.id,
                    model=action.model,
                    capability=action.required_capability.value,
                ))
        actions_by_id = {item.id: item for item in actions}
        reported_expectations: set[tuple[str, ControlPlaneCapabilityDimension]] = set()
        for expectation in expectations:
            action = actions_by_id.get(expectation.action_id)
            if action is None:
                continue
            key = (action.model, expectation.required_capability)
            if key in reported_expectations:
                continue
            reported_expectations.add(key)
            profile = capabilities.get(action.model)
            status = (
                profile.status(expectation.required_capability)
                if profile else SecurityCapabilityStatus.UNKNOWN
            )
            if status is SecurityCapabilityStatus.SUPPORTED:
                continue
            code = (
                ConfigurationIssueCode.CONTROL_PLANE_CAPABILITY_UNSUPPORTED
                if status is SecurityCapabilityStatus.UNSUPPORTED
                else ConfigurationIssueCode.CONTROL_PLANE_CAPABILITY_UNKNOWN
            )
            issues.append(_warning(
                code,
                f"{action.model}:{expectation.required_capability.value} verification is {status.value}.",
                expectation.id,
                model=action.model,
                capability=expectation.required_capability.value,
            ))

    @staticmethod
    def _foundation(
        foundations: dict[str, ControlPlaneFoundationRequirement],
        kind: str,
        source_id: str,
        source_hash: str = "",
    ) -> None:
        foundation_id = f"foundation/{kind}/{source_id}"
        foundations[foundation_id] = ControlPlaneFoundationRequirement(
            id=foundation_id,
            kind=kind,
            source_id=source_id,
            source_hash=source_hash,
        )

    @staticmethod
    def _semantic_hash(plan: ControlPlanePlan) -> str:
        payload = plan.model_dump(mode="json")
        payload["semantic_hash"] = ""
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _deduplicate_issues(
        issues: list[ConfigurationIssue],
    ) -> list[ConfigurationIssue]:
        unique = {
            (item.severity.value, item.code.value, item.subject, item.message): item
            for item in issues
        }
        return [unique[key] for key in sorted(unique)]

    @staticmethod
    def _result(
        plan: ControlPlanePlan | None,
        actions: list[ControlPlaneAction],
        expectations: list[ControlPlaneVerificationExpectation],
        scenarios: list[LinkFailureScenario],
        topology: TopologyPlan,
        configuration: ConfigurationPlan,
        security_hash: str,
        issues: list[ConfigurationIssue],
    ) -> ControlPlaneCompileResult:
        summary = ControlPlaneCompileSummary(
            control_plane_plan_id=plan.id if plan else "",
            semantic_hash=plan.semantic_hash if plan else "",
            source_topology_hash=topology.physical_identity_hash,
            source_topology_hash_schema=(
                "physical-topology-v2"
                if topology.physical_topology_hash else "legacy-full-v1"
            ),
            source_configuration_hash=configuration.semantic_hash,
            source_security_hash=security_hash,
            action_count=len(actions),
            actions_by_type=control_plane_action_type_counts(actions),
            dependencies=sum(len(item.depends_on) for item in actions),
            verification_count=len(expectations),
            failure_scenario_count=len(scenarios),
            warnings=sum(
                item.severity is ConfigurationIssueSeverity.WARNING for item in issues
            ),
            errors=sum(
                item.severity is ConfigurationIssueSeverity.ERROR for item in issues
            ),
        )
        return ControlPlaneCompileResult(
            plan=plan,
            semantic_hash=plan.semantic_hash if plan else "",
            summary=summary,
            issues=issues,
        )
