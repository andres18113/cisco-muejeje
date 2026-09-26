"""E6: EnterprisePlan + E4 + E5 -> ServicePlan puro y determinista."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import cast

from ...models.plans import DevicePlan, TopologyPlan
from ..models.capabilities import CapabilityStatus
from ..models.configuration import (
    AddressRange,
    ConfigurationIssue,
    ConfigurationIssueCode,
    ConfigurationIssueSeverity,
    ConfigurationPlan,
    ConfigureDhcpPool,
    ConfigureRoutedInterface,
    ConfigureSubinterface,
    ConfigureSvi,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
)
from ..models.enterprise_plan import EnterprisePlan
from ..models.requirements import ServiceRequirement
from ..models.roles import DeviceRole
from ..models.service_plan import (
    AcquireDhcpLease,
    AddDnsRecord,
    CapabilityProvenance,
    ClientOperationCapability,
    ConfigureEmailClient,
    ConfigureNtpService,
    ConfigureServerDhcpPool,
    EnableDnsService,
    EnableHttpService,
    EnableHttpsService,
    EnablePop3Service,
    EnableServerDhcp,
    EnableSmtpService,
    EnableTftpService,
    EnsureEmailAccount,
    FoundationalServiceRequirement,
    NativeDhcpClientPort,
    NativeDhcpPoolPolicy,
    PublishTftpFile,
    SendMailMessage,
    ServerDhcpPoolRequirement,
    ServiceAction,
    ServiceCapabilityProfile,
    ServiceCapabilityRecords,
    ServiceCompileResult,
    ServiceCompileSummary,
    ServiceDefinition,
    ServiceEvidenceKind,
    ServicePhase,
    ServicePlan,
    ServiceType,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
    SetHttpContent,
    service_action_type_counts,
)
from ..models.verification import PrerequisiteKind, VerificationPrerequisite
from .configuration_dependencies import (
    ConfigurationDependencyError,
    order_dependency_actions,
)
from .native_dhcp_policy import (
    MAX_NATIVE_CLIENTS,
    native_policy_network,
    native_policy_within_scope,
)
from .service_capability_resolution import resolve_action_capability

_HOSTNAME_RE = re.compile(
    r"(?=^.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
#: Where the shared page store stopped being an assumption. The Q1
#: ordinal-1 file run wrote the existing index page through each handle on
#: a Server-PT and read the other handle back changed. It is provenance for
#: the contract, not evidence that applying it works: application and
#: verification support stay UNKNOWN/UNMEASURED until a run measures them.
SHARED_PAGE_STORE_RECORD = "q1-2026-09-19T23-00-53Z-b17240ad"
_SAFE_TFTP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,126}$")
_SAFE_HTTP_CONTENT = re.compile(r"^[\x20-\x7E\r\n\t]{0,4096}$")
_MAIL_USER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_MAIL_DISPLAY = re.compile(r"^[\x20-\x7E]{0,64}$")
_SECRET_REF = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_SERVICE_PROTOCOLS = {
    ServiceType.DNS: ("udp/tcp", [53]),
    ServiceType.HTTP: ("tcp", [80]),
    ServiceType.HTTPS: ("tcp", [443]),
    ServiceType.NTP: ("udp", [123]),
    ServiceType.TFTP: ("udp", [69]),
    ServiceType.SMTP: ("tcp", [25]),
    ServiceType.POP3: ("tcp", [110]),
    ServiceType.DHCP: ("udp", [67, 68]),
}
_SERVICE_HOST_ROLES = {
    ServiceType.DNS: (DeviceRole.DNS_SERVER.value, DeviceRole.SERVER.value),
    ServiceType.HTTP: (DeviceRole.WEB_SERVER.value, DeviceRole.SERVER.value),
    ServiceType.HTTPS: (DeviceRole.WEB_SERVER.value, DeviceRole.SERVER.value),
    ServiceType.NTP: (DeviceRole.NTP_SERVER.value, DeviceRole.SERVER.value),
    ServiceType.TFTP: (DeviceRole.TFTP_SERVER.value, DeviceRole.SERVER.value),
    ServiceType.SMTP: (DeviceRole.SERVER.value,),
    ServiceType.POP3: (DeviceRole.SERVER.value,),
    ServiceType.DHCP: (DeviceRole.DHCP_SERVER.value, DeviceRole.SERVER.value),
}
#: The mail families select their clients from the requirement's own lists and
#: never by role, so a PC that is not an email client is never touched.
_MAIL_TYPES = frozenset({ServiceType.SMTP, ServiceType.POP3})
_SAFE_DHCP_POOL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
MAX_SERVER_DHCP_USERS = 4096


def _issue(
    severity: ConfigurationIssueSeverity,
    code: ConfigurationIssueCode,
    message: str,
    subject: str = "",
) -> ConfigurationIssue:
    return ConfigurationIssue(
        severity=severity, code=code, message=message, subject=subject
    )


def _error(
    code: ConfigurationIssueCode, message: str, subject: str = ""
) -> ConfigurationIssue:
    return _issue(ConfigurationIssueSeverity.ERROR, code, message, subject)


def _warning(
    code: ConfigurationIssueCode, message: str, subject: str = ""
) -> ConfigurationIssue:
    return _issue(ConfigurationIssueSeverity.WARNING, code, message, subject)


def _stable_id(kind: str, *parts: object) -> str:
    semantic = "|".join((kind, *(str(part) for part in parts)))
    return f"svc/{kind}/{hashlib.sha256(semantic.encode('utf-8')).hexdigest()[:16]}"


def _token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "service"


class ServiceCompiler:
    """Compila servicios sin bridge, JavaScript, CLI ni objetos Packet Tracer."""

    def compile(
        self,
        enterprise: EnterprisePlan,
        topology: TopologyPlan,
        configuration: ConfigurationPlan,
        *,
        capabilities: dict[str, ServiceCapabilityProfile] | None = None,
    ) -> ServiceCompileResult:
        """Compile services for one enterprise, topology and configuration."""
        issues: list[ConfigurationIssue] = []
        capabilities = capabilities or {}
        if not topology.physical_identity_hash:
            issues.append(
                _error(
                    ConfigurationIssueCode.SOURCE_TOPOLOGY_HASH_MISSING,
                    "E6 requires the immutable semantic hash produced by E4.",
                    topology.id,
                )
            )
        if not configuration.semantic_hash:
            issues.append(
                _error(
                    ConfigurationIssueCode.SOURCE_CONFIGURATION_HASH_MISSING,
                    "E6 requires the immutable semantic hash produced by E5.",
                    configuration.id,
                )
            )
        if configuration.source_topology_hash != topology.physical_identity_hash:
            issues.append(
                _error(
                    ConfigurationIssueCode.SOURCE_CONFIGURATION_TOPOLOGY_MISMATCH,
                    "The E5 ConfigurationPlan was compiled for a different E4 topology.",
                    configuration.id,
                )
            )

        devices = {(item.id or item.name): item for item in topology.devices}
        foundations = {
            item.device_id: item
            for item in configuration.actions
            if isinstance(item, (SetEndpointStaticAddress, SetEndpointDhcp))
        }
        dhcp_mode_action_ids = {
            item.action_id
            for item in configuration.verification_expectations
            if item.kind.value == ServiceVerificationKind.ENDPOINT_DHCP_MODE.value
        }
        ios_dhcp_segments = {
            item.segment_id
            for item in configuration.actions
            if isinstance(item, ConfigureDhcpPool)
        }
        l3_foundations: dict[str, list[object]] = defaultdict(list)
        for item in configuration.actions:
            if isinstance(
                item, (ConfigureRoutedInterface, ConfigureSvi, ConfigureSubinterface)
            ):
                l3_foundations[item.segment_id].append(item)
        requirements = self._requirements(enterprise)
        services: list[ServiceDefinition] = []
        actions: list[ServiceAction] = []
        expectations: list[ServiceVerificationExpectation] = []
        foundation_requirements: dict[str, FoundationalServiceRequirement] = {}
        source_requirements: dict[str, ServiceRequirement] = {}
        action_ids_by_service: dict[str, list[str]] = {}

        for site_id, requirement in requirements:
            service_type = self._service_type(requirement)
            service_id = f"service/{site_id or 'global'}/{_token(requirement.name)}"
            if service_type is None:
                issues.append(
                    _error(
                        ConfigurationIssueCode.SERVICE_TYPE_INVALID,
                        f"{requirement.name!r} does not identify a supported E6 service type.",
                        service_id,
                    )
                )
                continue
            host = self._host(requirement, service_type, site_id, devices)
            if host is None:
                issues.append(
                    _error(
                        ConfigurationIssueCode.SERVICE_HOST_MISSING,
                        f"No existing E4 host can run {service_type.value} for {requirement.name}.",
                        service_id,
                    )
                )
                continue
            host_id = host.id or host.name
            host_foundation = foundations.get(host_id)
            if not isinstance(host_foundation, SetEndpointStaticAddress):
                issues.append(
                    _error(
                        ConfigurationIssueCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                        f"Service host {host.name} has no static E5 endpoint address action.",
                        host_id,
                    )
                )
                continue
            address = requirement.address or host_foundation.ipv4
            try:
                address = str(ipaddress.ip_address(address))
            except ValueError:
                issues.append(
                    _error(
                        ConfigurationIssueCode.SERVICE_ADDRESS_INVALID,
                        f"{address!r} is not a valid service address.",
                        service_id,
                    )
                )
                continue
            if address != host_foundation.ipv4:
                issues.append(
                    _error(
                        ConfigurationIssueCode.SERVICE_ADDRESS_MISMATCH,
                        f"Service address {address} does not belong to host {host.name} in E5.",
                        service_id,
                    )
                )
            if (
                requirement.segment_id
                and requirement.segment_id != host_foundation.segment_id
            ):
                issues.append(
                    _error(
                        ConfigurationIssueCode.SERVICE_SEGMENT_MISMATCH,
                        f"Service segment {requirement.segment_id} differs from E5 segment "
                        f"{host_foundation.segment_id}.",
                        service_id,
                    )
                )

            if service_type in _MAIL_TYPES:
                client_ids = self._mail_clients(
                    requirement,
                    service_type,
                    devices,
                    foundations,
                    issues,
                    service_id,
                )
            elif service_type is ServiceType.DHCP:
                client_ids = self._dhcp_clients(
                    requirement,
                    host_id,
                    devices,
                    foundations,
                    dhcp_mode_action_ids,
                    issues,
                    service_id,
                )
                if requirement.segment_id in ios_dhcp_segments:
                    issues.append(
                        _error(
                            ConfigurationIssueCode.DHCP_AUTHORITY_CONFLICT,
                            f"Delegated segment {requirement.segment_id!r} still "
                            "contains an E5 IOS DHCP pool.",
                            service_id,
                        )
                    )
            else:
                client_ids = self._clients(
                    requirement,
                    site_id,
                    host_id,
                    devices,
                    foundations,
                    issues,
                    service_id,
                )
            self._add_foundation(
                foundation_requirements,
                host,
                host_foundation,
                dhcp_mode_action_ids=dhcp_mode_action_ids,
            )
            for client_id in client_ids:
                self._add_foundation(
                    foundation_requirements,
                    devices[client_id],
                    foundations[client_id],
                    dhcp_mode_action_ids=dhcp_mode_action_ids,
                )
                client_foundation = foundations[client_id]
                if client_foundation.segment_id != host_foundation.segment_id:
                    for segment_id in sorted(
                        {
                            client_foundation.segment_id,
                            host_foundation.segment_id,
                        }
                    ):
                        candidates = sorted(
                            l3_foundations.get(segment_id, []),
                            key=lambda item: item.id,
                        )
                        if not candidates:
                            issues.append(
                                _error(
                                    ConfigurationIssueCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                                    f"Cross-segment service path lacks an E5 L3 action for {segment_id!r}.",
                                    f"{service_id}:{segment_id}",
                                )
                            )
                            continue
                        gateway_action = candidates[0]
                        gateway_device = devices.get(gateway_action.device_id)
                        if gateway_device is None:
                            issues.append(
                                _error(
                                    ConfigurationIssueCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                                    f"E5 L3 action {gateway_action.id} has no E4 device.",
                                    gateway_action.id,
                                )
                            )
                            continue
                        self._add_foundation(
                            foundation_requirements,
                            gateway_device,
                            gateway_action,
                            dhcp_mode_action_ids=dhcp_mode_action_ids,
                        )

            profile = capabilities.get(f"{host.model}:{service_type.value}")
            if profile and profile.compile_support is CapabilityStatus.UNSUPPORTED:
                issues.append(
                    _warning(
                        ConfigurationIssueCode.CAPABILITY_UNSUPPORTED,
                        f"Compilation support for {service_type.value} is unsupported.",
                        service_id,
                    )
                )
            if (
                profile is None
                or profile.application_support is CapabilityStatus.UNKNOWN
            ):
                issues.append(
                    _warning(
                        ConfigurationIssueCode.CAPABILITY_UNVERIFIED,
                        f"Runtime application support for {host.model}:{service_type.value} is unknown.",
                        service_id,
                    )
                )
            elif profile.application_support is CapabilityStatus.UNSUPPORTED:
                issues.append(
                    _warning(
                        ConfigurationIssueCode.CAPABILITY_UNSUPPORTED,
                        f"Runtime application support for {host.model}:{service_type.value} is unsupported.",
                        service_id,
                    )
                )

            if service_type is ServiceType.SMTP:
                service_actions = self._mail_actions(
                    service_id,
                    requirement,
                    host,
                    address,
                    client_ids,
                    devices,
                    issues,
                )
            elif service_type is ServiceType.DHCP:
                service_actions = self._dhcp_actions(
                    service_id,
                    requirement,
                    host,
                    host_foundation,
                    client_ids,
                    foundations,
                    configuration,
                    topology,
                    devices,
                    capabilities,
                    issues,
                )
            else:
                service_actions = self._actions(
                    service_id,
                    requirement,
                    service_type,
                    host,
                    host_foundation,
                    devices,
                    issues,
                )
            if profile is not None:
                for action in service_actions:
                    # One resolution, the same one admission and execution use:
                    # the operation on the model that actually hosts it.
                    action_support = resolve_action_capability(
                        capabilities, action
                    ).support
                    if action_support is CapabilityStatus.UNKNOWN:
                        issues.append(
                            _warning(
                                ConfigurationIssueCode.CAPABILITY_UNVERIFIED,
                                f"Runtime application support for {action.action_type.value} is unknown.",
                                action.id,
                            )
                        )
                    elif action_support is CapabilityStatus.UNSUPPORTED:
                        issues.append(
                            _warning(
                                ConfigurationIssueCode.CAPABILITY_UNSUPPORTED,
                                f"Runtime application support for {action.action_type.value} is unsupported.",
                                action.id,
                            )
                        )
            actions.extend(service_actions)
            action_ids_by_service[service_id] = [item.id for item in service_actions]
            source_requirements[service_id] = requirement
            protocol, ports = _SERVICE_PROTOCOLS[service_type]
            services.append(
                ServiceDefinition(
                    id=service_id,
                    name=requirement.name,
                    service_type=service_type,
                    site_id=site_id or host.site_id,
                    host_device_id=host_id,
                    host_device_name=host.name,
                    host_model=host.model,
                    address=address,
                    segment_id=host_foundation.segment_id,
                    client_device_ids=client_ids,
                    action_ids=[item.id for item in service_actions],
                    protocol=protocol,
                    ports=ports,
                    required=requirement.required,
                    verification_required=requirement.verification_required,
                )
            )

        actions = self._bind_shared_web_content(
            services, actions, source_requirements, action_ids_by_service, issues
        )

        by_name = {item.name.casefold(): item for item in services}
        by_id = {item.id: item for item in services}
        for service in services:
            requirement = source_requirements[service.id]
            if not requirement.depends_on or not service.action_ids:
                continue
            first = next(item for item in actions if item.id == service.action_ids[0])
            for dependency_name in sorted(
                set(requirement.depends_on), key=str.casefold
            ):
                dependency = by_name.get(dependency_name.casefold()) or by_id.get(
                    dependency_name
                )
                if dependency is None or not dependency.action_ids:
                    issues.append(
                        _error(
                            ConfigurationIssueCode.DEPENDENCY_MISSING,
                            f"Service dependency {dependency_name!r} does not exist.",
                            service.id,
                        )
                    )
                    continue
                first.depends_on.append(dependency.action_ids[-1])
            first.depends_on = sorted(set(first.depends_on))

        try:
            actions = order_dependency_actions(actions)
        except ConfigurationDependencyError as exc:
            code = (
                ConfigurationIssueCode.DEPENDENCY_CYCLE
                if "cycle" in str(exc).casefold()
                else ConfigurationIssueCode.DEPENDENCY_MISSING
            )
            issues.append(_error(code, str(exc), ",".join(exc.action_ids)))

        errors = any(
            item.severity is ConfigurationIssueSeverity.ERROR for item in issues
        )
        if not errors:
            expectations = self._expectations(
                services,
                actions,
                source_requirements,
                devices,
                foundations,
            )
            lease_by_client = {
                item.client_device_id: item.id
                for item in expectations
                if item.kind is ServiceVerificationKind.DHCP_LEASE
                and item.client_device_id
            }
            server_state_by_service = {
                item.service_id: item.id
                for item in expectations
                if item.kind is ServiceVerificationKind.DHCP_SERVER_STATE
            }
            for action in actions:
                if isinstance(action, AcquireDhcpLease):
                    action.verification_dependencies = [
                        server_state_by_service[action.service_id]
                    ]
                elif (
                    action.service_type is not ServiceType.DHCP
                    and action.host_device_id in lease_by_client
                ):
                    action.verification_dependencies = [
                        lease_by_client[action.host_device_id]
                    ]
            for expectation in expectations:
                if (
                    expectation.kind
                    not in {
                        ServiceVerificationKind.DHCP_LEASE,
                        ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED,
                    }
                    and expectation.client_device_id in lease_by_client
                ):
                    expectation.depends_on = sorted(
                        {
                            *expectation.depends_on,
                            lease_by_client[expectation.client_device_id],
                        }
                    )
            for action in actions:
                action.apply_dependencies = list(action.depends_on)
            for expectation in expectations:
                expectation.verification_prerequisites = [
                    VerificationPrerequisite(
                        kind=PrerequisiteKind.ACTION_APPLIED,
                        reference_id=expectation.action_id,
                    ),
                    *[
                        VerificationPrerequisite(
                            kind=PrerequisiteKind.VERIFICATION_VERIFIED,
                            reference_id=identifier,
                        )
                        for identifier in sorted(set(expectation.depends_on))
                    ],
                ]
            by_service_expectations: dict[str, list[str]] = defaultdict(list)
            for item in expectations:
                by_service_expectations[item.service_id].append(item.id)
            for service in services:
                service.verification_expectation_ids = by_service_expectations[
                    service.id
                ]

        issues = self._deduplicate_issues(issues)
        if any(item.severity is ConfigurationIssueSeverity.ERROR for item in issues):
            return self._result(
                None, actions, topology, configuration, services, expectations, issues
            )

        plan = ServicePlan(
            id=f"services_{topology.id or topology.physical_identity_hash[:16]}",
            source_topology_id=topology.id,
            source_topology_hash=topology.physical_identity_hash,
            source_topology_hash_schema=(
                "physical-topology-v2"
                if topology.physical_topology_hash
                else "legacy-full-v1"
            ),
            source_configuration_id=configuration.id,
            source_configuration_hash=configuration.semantic_hash,
            services=sorted(services, key=lambda item: item.id),
            actions=actions,
            foundational_requirements=sorted(
                foundation_requirements.values(),
                key=lambda item: (item.device_id, item.configuration_action_id),
            ),
            verification_expectations=expectations,
        )
        plan.semantic_hash = self._semantic_hash(plan)
        return self._result(
            plan, actions, topology, configuration, services, expectations, issues
        )

    @staticmethod
    def _requirements(
        enterprise: EnterprisePlan,
    ) -> list[tuple[str, ServiceRequirement]]:
        values = [
            (site.site_id, requirement)
            for site in enterprise.sites
            for requirement in site.services
        ]
        values.extend(
            (requirement.metadata.get("site_id", ""), requirement)
            for requirement in enterprise.services
        )
        return sorted(
            values,
            key=lambda item: (
                item[0],
                item[1].service_type.value if item[1].service_type else "",
                item[1].name.casefold(),
            ),
        )

    @staticmethod
    def _service_type(requirement: ServiceRequirement) -> ServiceType | None:
        if requirement.service_type is not None:
            return requirement.service_type
        normalized = _token(requirement.name).replace("-", "_")
        aliases = {item.value: item for item in ServiceType}
        return aliases.get(normalized)

    @staticmethod
    def _host(
        requirement: ServiceRequirement,
        service_type: ServiceType,
        site_id: str,
        devices: dict[str, DevicePlan],
    ) -> DevicePlan | None:
        if requirement.host_device_id:
            return devices.get(requirement.host_device_id)
        candidates = [
            item
            for item in devices.values()
            if (not site_id or item.site_id == site_id)
            and item.enterprise_role in _SERVICE_HOST_ROLES[service_type]
        ]
        role_order = {
            role: index for index, role in enumerate(_SERVICE_HOST_ROLES[service_type])
        }
        return min(
            candidates,
            key=lambda item: (role_order[item.enterprise_role], item.id or item.name),
            default=None,
        )

    @staticmethod
    def _clients(
        requirement: ServiceRequirement,
        site_id: str,
        host_id: str,
        devices: dict[str, DevicePlan],
        foundations: dict[str, object],
        issues: list[ConfigurationIssue],
        service_id: str,
    ) -> list[str]:
        requested = sorted(set(requirement.client_device_ids))
        if not requested:
            requested = sorted(
                device_id
                for device_id, device in devices.items()
                if device_id != host_id
                and (not site_id or device.site_id == site_id)
                and device_id in foundations
                and device.enterprise_role
                not in {
                    DeviceRole.SERVER.value,
                    DeviceRole.DNS_SERVER.value,
                    DeviceRole.WEB_SERVER.value,
                    DeviceRole.NTP_SERVER.value,
                    DeviceRole.TFTP_SERVER.value,
                }
            )
        valid: list[str] = []
        for client_id in requested:
            if client_id not in devices:
                issues.append(
                    _error(
                        ConfigurationIssueCode.SERVICE_CLIENT_MISSING,
                        f"Service client {client_id!r} does not exist in E4.",
                        service_id,
                    )
                )
            elif client_id not in foundations:
                issues.append(
                    _error(
                        ConfigurationIssueCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                        f"Service client {client_id!r} has no E5 endpoint addressing action.",
                        service_id,
                    )
                )
            else:
                valid.append(client_id)
        return valid

    @staticmethod
    def _dhcp_clients(
        requirement: ServiceRequirement,
        host_id: str,
        devices: dict[str, DevicePlan],
        foundations: dict[str, object],
        dhcp_mode_action_ids: set[str],
        issues: list[ConfigurationIssue],
        service_id: str,
    ) -> list[str]:
        """Select only delegated DHCP clients with a mode-only E5 contract."""
        requested = sorted(set(requirement.client_device_ids))
        if not requested:
            requested = sorted(
                device_id
                for device_id, action in foundations.items()
                if device_id != host_id
                and isinstance(action, SetEndpointDhcp)
                and action.segment_id == requirement.segment_id
            )
        valid: list[str] = []
        for client_id in requested:
            action = foundations.get(client_id)
            if client_id not in devices:
                issues.append(
                    _error(
                        ConfigurationIssueCode.SERVICE_CLIENT_MISSING,
                        f"DHCP client {client_id!r} does not exist in E4.",
                        service_id,
                    )
                )
            elif not isinstance(action, SetEndpointDhcp):
                issues.append(
                    _error(
                        ConfigurationIssueCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                        f"DHCP client {client_id!r} has no E5 DHCP-mode action.",
                        service_id,
                    )
                )
            elif action.segment_id != requirement.segment_id:
                issues.append(
                    _error(
                        ConfigurationIssueCode.DHCP_RELAY_REQUIRED,
                        f"DHCP client {client_id!r} is on {action.segment_id!r}, not "
                        f"delegated segment {requirement.segment_id!r}.",
                        service_id,
                    )
                )
            elif action.id not in dhcp_mode_action_ids:
                issues.append(
                    _error(
                        ConfigurationIssueCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                        f"DHCP client {client_id!r} lacks the delegated mode reader.",
                        service_id,
                    )
                )
            else:
                valid.append(client_id)
        if not valid:
            issues.append(
                _error(
                    ConfigurationIssueCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                    "A delegated DHCP service needs at least one bound client.",
                    service_id,
                )
            )
        return valid

    @staticmethod
    def _mail_clients(
        requirement: ServiceRequirement,
        service_type: ServiceType,
        devices: dict[str, DevicePlan],
        foundations: dict[str, object],
        issues: list[ConfigurationIssue],
        service_id: str,
    ) -> list[str]:
        """Select exactly the requirement's email clients, never by role.

        An SMTP service selects the devices its `email_clients` name; a POP3
        service selects none, because every per-pair row belongs to the SMTP
        service so that no expectation depends across services. A separately
        listed `client_device_ids` that disagrees is refused rather than
        silently ignored.
        """
        if service_type is ServiceType.POP3:
            if requirement.client_device_ids:
                issues.append(
                    _error(
                        ConfigurationIssueCode.EMAIL_CLIENT_INVALID,
                        "A POP3 service selects no clients; its retrieval rows "
                        "belong to the SMTP service on the same host.",
                        service_id,
                    )
                )
            return []
        listed = [item.client_device_id for item in requirement.email_clients]
        duplicates = sorted({item for item in listed if listed.count(item) > 1})
        for device_id in duplicates:
            issues.append(
                _error(
                    ConfigurationIssueCode.EMAIL_CLIENT_INVALID,
                    f"Email client {device_id!r} is listed more than once.",
                    service_id,
                )
            )
        requested = sorted(set(listed))
        if (
            requirement.client_device_ids
            and sorted(set(requirement.client_device_ids)) != requested
        ):
            issues.append(
                _error(
                    ConfigurationIssueCode.EMAIL_CLIENT_INVALID,
                    "client_device_ids must equal the email clients of an SMTP "
                    "service.",
                    service_id,
                )
            )
        valid: list[str] = []
        for client_id in requested:
            if client_id not in devices:
                issues.append(
                    _error(
                        ConfigurationIssueCode.SERVICE_CLIENT_MISSING,
                        f"Service client {client_id!r} does not exist in E4.",
                        service_id,
                    )
                )
            elif client_id not in foundations:
                issues.append(
                    _error(
                        ConfigurationIssueCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                        f"Service client {client_id!r} has no E5 endpoint addressing action.",
                        service_id,
                    )
                )
            else:
                valid.append(client_id)
        return valid

    def _mail_actions(
        self,
        service_id: str,
        requirement: ServiceRequirement,
        host: DevicePlan,
        address: str,
        client_ids: list[str],
        devices: dict[str, DevicePlan],
        issues: list[ConfigurationIssue],
    ) -> list[ServiceAction]:
        """Compile the SMTP family: server, accounts, clients and messages.

        Pairs are explicit when the requirement lists them, else a ring over
        the sorted selected clients -- a self-send for one client -- and never
        all pairs. Each pair has one stable `message_ref`; its nonce is bound
        per run, outside the plan.
        """
        server = dict(
            service_id=service_id,
            service_type=ServiceType.SMTP,
            host_device_id=host.id or host.name,
            host_device_name=host.name,
            host_model=host.model,
            site_id=host.site_id,
            required_capability="service_smtp_application",
        )

        def on_client(client_id: str) -> dict[str, object]:
            device = devices[client_id]
            return {
                **server,
                "host_device_id": client_id,
                "host_device_name": device.name,
                "host_model": device.model,
                "site_id": device.site_id,
            }

        domain = requirement.domain_name.strip().casefold()
        if not domain or not _HOSTNAME_RE.fullmatch(domain):
            issues.append(
                _error(
                    ConfigurationIssueCode.EMAIL_DOMAIN_INVALID,
                    f"SMTP domain {requirement.domain_name!r} is not a valid domain.",
                    service_id,
                )
            )
            return []
        enable = EnableSmtpService(
            id=_stable_id("enable-smtp", service_id),
            phase=ServicePhase.ENABLE,
            domain_name=domain,
            **server,
        )
        accounts: dict[str, EnsureEmailAccount] = {}
        names: dict[str, str] = {}
        displays: dict[str, str] = {}
        for item in sorted(
            requirement.email_accounts, key=lambda value: value.username.casefold()
        ):
            key = item.username.casefold()
            if not _MAIL_USER.fullmatch(item.username) or key in accounts:
                issues.append(
                    _error(
                        ConfigurationIssueCode.EMAIL_ACCOUNT_INVALID,
                        f"Mail account {item.username!r} is invalid or repeated.",
                        service_id,
                    )
                )
                continue
            if not _MAIL_DISPLAY.fullmatch(item.display_name):
                issues.append(
                    _error(
                        ConfigurationIssueCode.EMAIL_ACCOUNT_INVALID,
                        f"Mail account {item.username!r} has an unsafe display name.",
                        service_id,
                    )
                )
                continue
            if not _SECRET_REF.fullmatch(item.secret_ref):
                issues.append(
                    _error(
                        ConfigurationIssueCode.SECRET_REF_INVALID,
                        f"Mail account {item.username!r} names an invalid secret "
                        "reference.",
                        service_id,
                    )
                )
                continue
            names[key] = item.username
            displays[key] = item.display_name or item.username
            accounts[key] = EnsureEmailAccount(
                id=_stable_id("email-account", service_id, key),
                phase=ServicePhase.CONTENT,
                depends_on=[enable.id],
                username=item.username,
                secret_ref=item.secret_ref,
                **server,
            )

        clients: dict[str, ConfigureEmailClient] = {}
        for item in sorted(
            requirement.email_clients, key=lambda value: value.client_device_id
        ):
            if item.client_device_id not in client_ids:
                continue
            account = accounts.get(item.username.casefold())
            if account is None:
                issues.append(
                    _error(
                        ConfigurationIssueCode.EMAIL_ACCOUNT_MISSING,
                        f"Email client {item.client_device_id!r} uses undeclared "
                        f"account {item.username!r}.",
                        service_id,
                    )
                )
                continue
            key = item.username.casefold()
            clients[item.client_device_id] = ConfigureEmailClient(
                id=_stable_id("email-client", service_id, item.client_device_id),
                phase=ServicePhase.CLIENT,
                depends_on=[account.id],
                username=names[key],
                mail_id=f"{names[key]}@{domain}",
                display_name=displays[key],
                smtp_server=address,
                pop3_server=address,
                secret_ref=account.secret_ref,
                **on_client(item.client_device_id),
            )

        pairs = self._mail_pairs(requirement, sorted(clients), issues, service_id)
        sends: list[SendMailMessage] = []
        for sender, recipient in pairs:
            if sender not in clients or recipient not in clients:
                continue
            source, target = clients[sender], clients[recipient]
            sends.append(
                SendMailMessage(
                    id=_stable_id("email-send", service_id, sender, recipient),
                    phase=ServicePhase.MESSAGE,
                    depends_on=sorted(
                        {source.id, accounts[target.username.casefold()].id}
                    ),
                    message_ref=_stable_id("message", service_id, sender, recipient),
                    sender_mail_id=source.mail_id,
                    recipient_mail_id=target.mail_id,
                    recipient_username=target.username,
                    smtp_server=address,
                    secret_ref=source.secret_ref,
                    **on_client(sender),
                )
            )
        return [
            enable,
            *(accounts[key] for key in sorted(accounts)),
            *(clients[key] for key in sorted(clients)),
            *sends,
        ]

    @staticmethod
    def _mail_pairs(
        requirement: ServiceRequirement,
        clients: list[str],
        issues: list[ConfigurationIssue],
        service_id: str,
    ) -> list[tuple[str, str]]:
        """Return the explicit pairs, or the default ring, in stable order."""
        if requirement.verification_mode == "configure_only":
            if requirement.email_pairs:
                issues.append(
                    _error(
                        ConfigurationIssueCode.EMAIL_PAIR_INVALID,
                        "A configure_only mail service sends no message, so it "
                        "cannot list message pairs.",
                        service_id,
                    )
                )
            return []
        if not requirement.email_pairs:
            if len(clients) == 1:
                return [(clients[0], clients[0])]
            return [
                (clients[index], clients[(index + 1) % len(clients)])
                for index in range(len(clients))
            ]
        pairs: list[tuple[str, str]] = []
        selected = set(clients)
        for item in requirement.email_pairs:
            pair = (item.sender_device_id, item.recipient_device_id)
            if pair in pairs or not {*pair} <= selected:
                issues.append(
                    _error(
                        ConfigurationIssueCode.EMAIL_PAIR_INVALID,
                        f"Message pair {pair!r} is repeated or names a device that "
                        "is not a selected email client.",
                        service_id,
                    )
                )
                continue
            pairs.append(pair)
        return sorted(pairs)

    @staticmethod
    def _add_foundation(
        target,
        device: DevicePlan,
        action,
        *,
        dhcp_mode_action_ids: set[str],
    ) -> None:
        device_id = device.id or device.name
        target[action.id] = FoundationalServiceRequirement(
            id=_stable_id("foundation", device_id, action.id),
            device_id=device_id,
            device_name=device.name,
            model=device.model,
            ipv4=getattr(action, "ipv4", ""),
            segment_id=action.segment_id,
            configuration_action_id=action.id,
            # Which E5 family this points at, recorded here because the
            # evidence derivation is given the E6 plan and the E5 RESULT, and
            # the result carries rows, not actions. Guessing the family from a
            # row is how an L3 interface could be promoted by the endpoint core
            # predicate, which only describes an endpoint.
            kind=(
                "endpoint_dhcp_mode"
                if action.id in dhcp_mode_action_ids
                else "endpoint_address"
                if isinstance(action, (SetEndpointStaticAddress, SetEndpointDhcp))
                else "l3_interface"
            ),
        )

    def _dhcp_actions(
        self,
        service_id: str,
        requirement: ServiceRequirement,
        host: DevicePlan,
        host_foundation: SetEndpointStaticAddress,
        client_ids: list[str],
        foundations: dict[str, object],
        configuration: ConfigurationPlan,
        topology: TopologyPlan,
        devices: dict[str, DevicePlan],
        capabilities: ServiceCapabilityRecords,
        issues: list[ConfigurationIssue],
    ) -> list[ServiceAction]:
        """Compile one validated same-segment Server-PT DHCP service."""
        requested = requirement.dhcp_pool or ServerDhcpPoolRequirement()
        host_id = host.id or host.name
        candidate_interfaces = {
            link.port_a if link.device_a_id == host_id else link.port_b
            for link in topology.links
            if host_id in {link.device_a_id, link.device_b_id}
        }
        interface = requested.interface.strip() or host_foundation.interface
        if (
            not interface
            or interface != host_foundation.interface
            or interface not in candidate_interfaces
            or (not requested.interface.strip() and len(candidate_interfaces) != 1)
        ):
            issues.append(
                _error(
                    ConfigurationIssueCode.DHCP_INTERFACE_MISSING,
                    f"DHCP interface {interface!r} does not equal the static "
                    f"server interface {host_foundation.interface!r}.",
                    service_id,
                )
            )
            return []
        if requested.start_offset < 0 or requested.max_users < 0:
            issues.append(
                _error(
                    ConfigurationIssueCode.DHCP_POOL_INVALID,
                    "DHCP start_offset and max_users must be non-negative.",
                    service_id,
                )
            )
            return []
        max_users = requested.max_users or len(client_ids)
        if not 0 < max_users <= MAX_SERVER_DHCP_USERS:
            issues.append(
                _error(
                    ConfigurationIssueCode.DHCP_POOL_INVALID,
                    f"DHCP max_users must be between 1 and {MAX_SERVER_DHCP_USERS}.",
                    service_id,
                )
            )
            return []
        native_record = capabilities.get("Server-PT:dhcp_native_default_binding")
        native_binding = (
            requirement.verification_mode == "state_only"
            and not requested.pool_name.strip()
            and isinstance(native_record, ClientOperationCapability)
            and native_record.support is CapabilityStatus.SUPPORTED
            and native_record.provenance is CapabilityProvenance.RECORDED_RUN
            and bool(native_record.build)
            and native_record.build == native_record.packet_tracer_version
            and bool(native_record.executed_sha)
            and native_record.transport == "file"
            and bool(native_record.run_id)
        )
        if (
            requirement.verification_mode == "state_only"
            and requested.pool_name.strip()
        ):
            issues.append(
                _error(
                    ConfigurationIssueCode.DHCP_POOL_INVALID,
                    "Native Server-PT binding requires an unnamed pool request.",
                    service_id,
                )
            )
            return []
        if native_binding and (
            requested.pool_name.strip()
            or requirement.verification_mode != "state_only"
            or host.model != "Server-PT"
            or interface != "FastEthernet0"
        ):
            issues.append(
                _error(
                    ConfigurationIssueCode.DHCP_POOL_INVALID,
                    "Native Server-PT binding requires an unnamed "
                    "state-only DHCP service on FastEthernet0.",
                    service_id,
                )
            )
            return []
        if requirement.verification_mode == "state_only" and not native_binding:
            issues.append(
                _error(
                    ConfigurationIssueCode.DHCP_POOL_INVALID,
                    "State-only DHCP requires an explicit effective-pool binding.",
                    service_id,
                )
            )
            return []
        client_actions = [foundations[client_id] for client_id in client_ids]
        first = cast(SetEndpointDhcp, client_actions[0])
        inactive_client_ids = (
            [
                device_id
                for device_id, item in foundations.items()
                if isinstance(item, SetEndpointDhcp)
                and item.segment_id == first.segment_id
                and device_id not in client_ids
            ]
            if native_binding
            else []
        )
        if native_binding and len(inactive_client_ids) > MAX_NATIVE_CLIENTS:
            issues.append(
                _error(
                    ConfigurationIssueCode.DHCP_POOL_INVALID,
                    "Native Server-PT binding exceeds its competing-client read bound.",
                    service_id,
                )
            )
            return []
        if any(
            not isinstance(item, SetEndpointDhcp)
            or (
                item.segment_id,
                item.network,
                item.prefix,
                item.netmask,
                item.gateway,
                item.dns_server or "",
            )
            != (
                first.segment_id,
                first.network,
                first.prefix,
                first.netmask,
                first.gateway,
                first.dns_server or "",
            )
            for item in client_actions
        ):
            issues.append(
                _error(
                    ConfigurationIssueCode.DHCP_POOL_INVALID,
                    "Delegated DHCP clients do not share one allocation.",
                    service_id,
                )
            )
            return []
        try:
            network = ipaddress.ip_network(f"{first.network}/{first.prefix}")
            server_address = ipaddress.ip_address(host_foundation.ipv4)
            gateway = ipaddress.ip_address(first.gateway)
        except ValueError:
            issues.append(
                _error(
                    ConfigurationIssueCode.DHCP_POOL_INVALID,
                    "The delegated DHCP allocation is not valid IPv4.",
                    service_id,
                )
            )
            return []
        if (
            server_address not in network
            or gateway not in network
            or str(network.netmask) != first.netmask
            or host_foundation.segment_id != first.segment_id
        ):
            issues.append(
                _error(
                    ConfigurationIssueCode.DHCP_POOL_INVALID,
                    "The DHCP server, gateway, network and mask are inconsistent.",
                    service_id,
                )
            )
            return []
        static = {
            ipaddress.ip_address(item.ipv4)
            for item in configuration.actions
            if isinstance(item, SetEndpointStaticAddress)
            and item.segment_id == first.segment_id
        }
        dns_server = requested.dns_server.strip() or first.dns_server or ""
        dns_address = None
        if dns_server:
            try:
                dns_address = ipaddress.ip_address(dns_server)
            except ValueError:
                issues.append(
                    _error(
                        ConfigurationIssueCode.DHCP_POOL_INVALID,
                        "The requested DHCP DNS server is not a valid IP address.",
                        service_id,
                    )
                )
                return []
            if dns_address.version != 4:
                issues.append(
                    _error(
                        ConfigurationIssueCode.DHCP_POOL_INVALID,
                        "The requested DHCP DNS server is not IPv4.",
                        service_id,
                    )
                )
                return []
        excluded = sorted(
            {
                server_address,
                gateway,
                *static,
                *(
                    (dns_address,)
                    if dns_address is not None and dns_address in network
                    else ()
                ),
            }
        )
        excluded_ranges = self._compact_address_ranges(excluded)
        window = self._lease_window(
            network,
            excluded_ranges,
            start_offset=requested.start_offset,
            max_users=max_users,
        )
        if window is None:
            issues.append(
                _error(
                    ConfigurationIssueCode.DHCP_POOL_INVALID,
                    "The delegated segment has no bounded usable DHCP range.",
                    service_id,
                )
            )
            return []
        lease_start, lease_end = window
        if (
            native_binding
            and native_policy_network(
                network=str(network.network_address),
                netmask=first.netmask,
                gateway=str(gateway),
                dns_server=dns_server,
                lease_start=lease_start,
                lease_end=lease_end,
                max_users=max_users,
                excluded_ranges=[(item.start, item.end) for item in excluded_ranges],
                selected_count=len(client_ids),
            )
            is None
        ):
            issues.append(
                _error(
                    ConfigurationIssueCode.DHCP_POOL_INVALID,
                    "Native Server-PT binding does not admit this derived "
                    "address policy.",
                    service_id,
                )
            )
            return []
        if native_binding and not native_policy_within_scope(
            native_record.native_policy_scope,
            network=str(network.network_address),
            netmask=first.netmask,
            server_address=str(server_address),
            gateway=str(gateway),
            dns_server=dns_server,
            lease_start=lease_start,
            lease_end=lease_end,
            max_users=max_users,
            excluded_ranges=[(item.start, item.end) for item in excluded_ranges],
        ):
            issues.append(
                _error(
                    ConfigurationIssueCode.DHCP_POOL_INVALID,
                    "Native Server-PT binding is outside its recorded policy scope.",
                    service_id,
                )
            )
            return []
        pool_name = requested.pool_name.strip() or re.sub(
            r"[^A-Za-z0-9]+", "_", first.segment_id.upper()
        ).strip("_")
        if not _SAFE_DHCP_POOL_NAME.fullmatch(pool_name):
            issues.append(
                _error(
                    ConfigurationIssueCode.DHCP_POOL_INVALID,
                    f"DHCP pool name {pool_name!r} is not safe.",
                    service_id,
                )
            )
            return []
        common = dict(
            service_id=service_id,
            service_type=ServiceType.DHCP,
            host_device_id=host.id or host.name,
            host_device_name=host.name,
            host_model=host.model,
            site_id=host.site_id,
            required_capability="service_dhcp_application",
        )
        enable = EnableServerDhcp(
            id=_stable_id("enable-server-dhcp", service_id, interface),
            phase=ServicePhase.ENABLE,
            depends_on=[],
            interface=interface,
            effective_pool_name="serverPool" if native_binding else "",
            **common,
        )
        pool = ConfigureServerDhcpPool(
            id=_stable_id("server-dhcp-pool", service_id, pool_name),
            phase=ServicePhase.CONTENT,
            depends_on=[] if native_binding else [enable.id],
            interface=interface,
            pool_name=pool_name,
            effective_pool_name="serverPool" if native_binding else "",
            pool_name_explicit=bool(requested.pool_name.strip()),
            segment_id=first.segment_id,
            network=str(network.network_address),
            prefix=network.prefixlen,
            netmask=str(network.netmask),
            gateway=str(gateway),
            dns_server=dns_server,
            lease_start=lease_start,
            lease_end=lease_end,
            max_users=max_users,
            excluded_ranges=excluded_ranges,
            **common,
        )
        if native_binding:
            enable.depends_on = [pool.id]
            enable.native_policy = NativeDhcpPoolPolicy(
                effective_pool_name="serverPool",
                network=pool.network,
                netmask=pool.netmask,
                gateway=pool.gateway,
                dns_server=pool.dns_server,
                lease_start=pool.lease_start,
                lease_end=pool.lease_end,
                max_users=pool.max_users,
                excluded_ranges=list(pool.excluded_ranges),
                selected_clients=[
                    NativeDhcpClientPort(
                        device_name=devices[client_id].name,
                        interface=cast(
                            SetEndpointDhcp, foundations[client_id]
                        ).interface,
                    )
                    for client_id in client_ids
                ],
                inactive_clients=sorted(
                    [
                        NativeDhcpClientPort(
                            device_name=devices[device_id].name,
                            interface=item.interface,
                        )
                        for device_id, item in foundations.items()
                        if device_id in inactive_client_ids
                    ],
                    key=lambda item: item.device_name,
                ),
            )
        actions: list[ServiceAction] = (
            [pool, enable] if native_binding else [enable, pool]
        )
        if requirement.verification_mode in {"configure_only", "state_only"}:
            return actions
        for client_id in client_ids:
            client_action = foundations[client_id]
            client_action = cast(SetEndpointDhcp, client_action)
            client = devices[client_id]
            actions.append(
                AcquireDhcpLease(
                    id=_stable_id("acquire-dhcp", service_id, client_id),
                    phase=ServicePhase.ACQUISITION,
                    service_id=service_id,
                    service_type=ServiceType.DHCP,
                    host_device_id=client_id,
                    host_device_name=client.name,
                    host_model=client.model,
                    site_id=client.site_id,
                    depends_on=[pool.id],
                    required_capability="client_dhcp_acquisition",
                    interface=client_action.interface,
                    segment_id=first.segment_id,
                    server_device_id=host.id or host.name,
                    server_device_name=host.name,
                    pool_name=pool_name,
                    network=str(network.network_address),
                    prefix=network.prefixlen,
                    netmask=str(network.netmask),
                    claim_ref=_stable_id("dhcp-claim", service_id, client_id),
                )
            )
        return actions

    @staticmethod
    def _compact_address_ranges(
        values: list[ipaddress.IPv4Address],
    ) -> list[AddressRange]:
        """Collapse exclusions without enumerating a subnet."""
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
    def _lease_window(
        network: ipaddress.IPv4Network,
        excluded_ranges: list[AddressRange],
        *,
        start_offset: int,
        max_users: int,
    ) -> tuple[str, str] | None:
        """Return the first bounded capacity window using compact intervals."""
        lower = int(network.network_address) + 1 + start_offset
        upper = int(network.broadcast_address) - 1
        if lower > upper:
            return None
        exclusions = sorted(
            (int(ipaddress.ip_address(item.start)), int(ipaddress.ip_address(item.end)))
            for item in excluded_ranges
        )
        cursor = lower
        remaining = max_users
        first: int | None = None
        last: int | None = None
        for excluded_start, excluded_end in [*exclusions, (upper + 1, upper + 1)]:
            if excluded_end < cursor:
                continue
            interval_end = min(upper, excluded_start - 1)
            if cursor <= interval_end:
                if first is None:
                    first = cursor
                available = interval_end - cursor + 1
                if available >= remaining:
                    last = cursor + remaining - 1
                    remaining = 0
                    break
                remaining -= available
                last = interval_end
            cursor = max(cursor, excluded_end + 1)
            if cursor > upper:
                break
        if remaining or first is None or last is None:
            return None
        return str(ipaddress.ip_address(first)), str(ipaddress.ip_address(last))

    def _actions(
        self,
        service_id: str,
        requirement: ServiceRequirement,
        service_type: ServiceType,
        host: DevicePlan,
        foundation: SetEndpointStaticAddress,
        devices: dict[str, DevicePlan],
        issues: list[ConfigurationIssue],
    ) -> list[ServiceAction]:
        common = dict(
            service_id=service_id,
            service_type=service_type,
            host_device_id=host.id or host.name,
            host_device_name=host.name,
            host_model=host.model,
            site_id=host.site_id,
            required_capability=f"service_{service_type.value}_application",
        )
        if service_type is ServiceType.DNS:
            enable = EnableDnsService(
                id=_stable_id("enable-dns", service_id),
                phase=ServicePhase.ENABLE,
                **common,
            )
            records: dict[tuple[str, str], object] = {}
            targets: dict[str, str] = {}
            for record in sorted(
                requirement.dns_records,
                key=lambda item: (
                    item.hostname.casefold(),
                    item.record_type,
                    item.address,
                ),
            ):
                hostname = record.hostname.casefold()
                if record.target_device_id and record.target_device_id not in devices:
                    issues.append(
                        _error(
                            ConfigurationIssueCode.SERVICE_HOST_MISSING,
                            f"DNS target device {record.target_device_id!r} does not exist in E4.",
                            service_id,
                        )
                    )
                if not _HOSTNAME_RE.fullmatch(hostname):
                    issues.append(
                        _error(
                            ConfigurationIssueCode.DNS_HOSTNAME_INVALID,
                            f"DNS hostname {record.hostname!r} is invalid.",
                            service_id,
                        )
                    )
                    continue
                try:
                    address = str(ipaddress.ip_address(record.address))
                except ValueError:
                    issues.append(
                        _error(
                            ConfigurationIssueCode.SERVICE_ADDRESS_INVALID,
                            f"DNS target {record.address!r} is not a valid IPv4 address.",
                            service_id,
                        )
                    )
                    continue
                prior = targets.get(hostname)
                if prior is not None and prior != address:
                    issues.append(
                        _error(
                            ConfigurationIssueCode.DNS_RECORD_CONFLICT,
                            f"DNS hostname {hostname} maps to both {prior} and {address}.",
                            service_id,
                        )
                    )
                    continue
                targets[hostname] = address
                records[(hostname, address)] = record
            return [
                enable,
                *[
                    AddDnsRecord(
                        id=_stable_id("dns-a", service_id, hostname, address),
                        phase=ServicePhase.CONTENT,
                        depends_on=[enable.id],
                        hostname=hostname,
                        address=address,
                        **common,
                    )
                    for hostname, address in sorted(records)
                ],
            ]
        if service_type in {ServiceType.HTTP, ServiceType.HTTPS}:
            enable: ServiceAction = (
                EnableHttpService(
                    id=_stable_id("enable-http", service_id),
                    phase=ServicePhase.ENABLE,
                    **common,
                )
                if service_type is ServiceType.HTTP
                else EnableHttpsService(
                    id=_stable_id("enable-https", service_id),
                    phase=ServicePhase.ENABLE,
                    **common,
                )
            )
            content = (
                requirement.http_content
                or f"MCP_E6_HTTP_OK_{_stable_id('http', service_id)[-8:]}"
            )
            if not _SAFE_HTTP_CONTENT.fullmatch(content):
                issues.append(
                    _error(
                        ConfigurationIssueCode.HTTP_CONTENT_UNSAFE,
                        "HTTP content must be bounded printable text.",
                        service_id,
                    )
                )
                return [enable]
            # Both protocols reach the same page store, so HTTPS compiles a
            # content action of its own here and `_bind_shared_web_content`
            # decides afterwards whether it survives as the shared one, is
            # merged into the HTTP-owned action, or refuses the plan.
            return [
                enable,
                SetHttpContent(
                    id=_stable_id("http-content", service_id, content),
                    phase=ServicePhase.CONTENT,
                    depends_on=[enable.id],
                    content=content,
                    content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    shared_service_ids=[service_id],
                    content_source_record=SHARED_PAGE_STORE_RECORD,
                    **common,
                ),
            ]
        if service_type is ServiceType.NTP:
            return [
                ConfigureNtpService(
                    id=_stable_id("configure-ntp", service_id),
                    phase=ServicePhase.ENABLE,
                    authoritative=requirement.ntp_authoritative,
                    **common,
                )
            ]
        if service_type is ServiceType.POP3:
            return [
                EnablePop3Service(
                    id=_stable_id("enable-pop3", service_id),
                    phase=ServicePhase.ENABLE,
                    **common,
                )
            ]
        enable = EnableTftpService(
            id=_stable_id("enable-tftp", service_id),
            phase=ServicePhase.ENABLE,
            **common,
        )
        files: dict[tuple[str, str], object] = {}
        for item in sorted(
            requirement.tftp_files, key=lambda value: (value.filename, value.content)
        ):
            if not _SAFE_TFTP_NAME.fullmatch(item.filename) or ".." in item.filename:
                issues.append(
                    _error(
                        ConfigurationIssueCode.TFTP_FILENAME_UNSAFE,
                        f"TFTP filename {item.filename!r} is not a safe server-local name.",
                        service_id,
                    )
                )
                continue
            digest = hashlib.sha256(item.content.encode("utf-8")).hexdigest()
            files[(item.filename, digest)] = item
        return [
            enable,
            *[
                PublishTftpFile(
                    id=_stable_id("tftp-file", service_id, filename, digest),
                    phase=ServicePhase.CONTENT,
                    depends_on=[enable.id],
                    filename=filename,
                    content=files[(filename, digest)].content,
                    content_sha256=digest,
                    **common,
                )
                for filename, digest in sorted(files)
            ],
        ]

    @staticmethod
    def _shared_content(
        service_id: str, actions: Sequence[ServiceAction]
    ) -> SetHttpContent | None:
        """Return the one content action that serves `service_id`, if any."""
        for item in actions:
            if isinstance(item, SetHttpContent) and (
                service_id in item.shared_service_ids or item.service_id == service_id
            ):
                return item
        return None

    @staticmethod
    def _bind_shared_web_content(
        services: Sequence[ServiceDefinition],
        actions: list[ServiceAction],
        requirements: Mapping[str, ServiceRequirement],
        action_ids_by_service: dict[str, list[str]],
        issues: list[ConfigurationIssue],
    ) -> list[ServiceAction]:
        """Collapse every host page to one content action, or refuse the plan.

        Packet Tracer serves HTTP and HTTPS from one page table, so two
        content actions on the same host page are two writes of one page, not
        two pages. When the requirements state different content for it there
        is no plan that satisfies both, and the conflict is an error before
        anything is applied rather than a last write that wins. A requirement
        that states nothing is not a competing intention: the stated one is
        used, and only stated contents can conflict.

        The surviving action is owned by the HTTP service when the host serves
        HTTP, so an HTTPS-only host never needs its HTTP listener enabled to
        publish a page. It depends on every merged service's enable, and it
        names all of them in `shared_service_ids`.
        """
        groups: dict[tuple[str, str], list[SetHttpContent]] = defaultdict(list)
        for item in actions:
            if isinstance(item, SetHttpContent):
                groups[(item.host_device_id, item.path)].append(item)
        removed: set[str] = set()
        replacements: dict[str, SetHttpContent] = {}
        for (host_device_id, path), group in sorted(groups.items()):
            if len(group) < 2:
                continue
            ordered = sorted(group, key=lambda item: item.service_id)
            stated = sorted(
                {
                    item.content
                    for item in ordered
                    if requirements[item.service_id].http_content
                }
            )
            if len(stated) > 1:
                issues.append(
                    _error(
                        ConfigurationIssueCode.WEB_CONTENT_CONFLICT,
                        f"Host {host_device_id} serves one page store, but "
                        f"{path} is required to hold "
                        + " and ".join(repr(item) for item in stated)
                        + ".",
                        ",".join(item.service_id for item in ordered),
                    )
                )
                continue
            owner = next(
                (item for item in ordered if item.service_type is ServiceType.HTTP),
                ordered[0],
            )
            content = stated[0] if stated else owner.content
            merged = owner.model_copy(
                update={
                    "id": _stable_id("http-content", owner.service_id, content),
                    "content": content,
                    "content_sha256": hashlib.sha256(
                        content.encode("utf-8")
                    ).hexdigest(),
                    "shared_service_ids": sorted(item.service_id for item in ordered),
                    "depends_on": sorted(
                        {
                            dependency
                            for item in ordered
                            for dependency in item.depends_on
                        }
                    ),
                },
                deep=True,
            )
            replacements[owner.id] = merged
            removed.update(item.id for item in ordered if item.id != owner.id)
        if not replacements and not removed:
            return actions
        kept = [
            replacements.get(item.id, item)
            for item in actions
            if item.id not in removed
        ]
        for service_id, identifiers in action_ids_by_service.items():
            action_ids_by_service[service_id] = [
                replacements[item].id if item in replacements else item
                for item in identifiers
                if item not in removed
            ]
        for service in services:
            service.action_ids = list(action_ids_by_service.get(service.id, []))
        # A warning about an action that no longer exists would name an
        # identity nothing in the plan carries.
        issues[:] = [item for item in issues if item.subject not in removed]
        return kept

    def _expectations(self, services, actions, requirements, devices, foundations):
        by_service: dict[str, list[ServiceAction]] = defaultdict(list)
        for action in actions:
            by_service[action.service_id].append(action)
        expectations: list[ServiceVerificationExpectation] = []
        dns_resolutions: dict[tuple[str, str], str] = {}
        http_fetches: dict[tuple[str, str], str] = {}
        for service in sorted(services, key=lambda item: item.id):
            service_actions = by_service[service.id]
            if not service_actions:
                continue
            # The server's own state is read after the last action that ran on
            # the server; client configuration and messages come later and are
            # observed by their own rows.
            terminal = [
                item
                for item in service_actions
                if item.host_device_id == service.host_device_id
            ][-1]
            direct = ServiceVerificationExpectation(
                id=_stable_id("verify-direct", service.id),
                service_id=service.id,
                action_id=terminal.id,
                kind=(
                    ServiceVerificationKind.DHCP_SERVER_STATE
                    if service.service_type is ServiceType.DHCP
                    else ServiceVerificationKind.DIRECT_SERVICE_STATE
                ),
                evidence_kind=ServiceEvidenceKind.DIRECT_STATE,
                host_device_id=service.host_device_id,
                host_device_name=service.host_device_name,
                expected={"enabled": True, "service_type": service.service_type.value},
            )
            if service.service_type is ServiceType.DNS:
                direct.expected["records_json"] = json.dumps(
                    {
                        item.hostname: item.address
                        for item in service_actions
                        if isinstance(item, AddDnsRecord)
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            elif service.service_type in {ServiceType.HTTP, ServiceType.HTTPS}:
                shared = self._shared_content(service.id, actions)
                direct.expected["marker"] = shared.content if shared else ""
            elif service.service_type is ServiceType.SMTP:
                direct.expected["domain_name"] = next(
                    item.domain_name
                    for item in service_actions
                    if isinstance(item, EnableSmtpService)
                )
                direct.expected["accounts_json"] = json.dumps(
                    [
                        item.username
                        for item in service_actions
                        if isinstance(item, EnsureEmailAccount)
                    ],
                    separators=(",", ":"),
                )
            elif service.service_type is ServiceType.DHCP:
                pool = next(
                    item
                    for item in service_actions
                    if isinstance(item, ConfigureServerDhcpPool)
                )
                enable = next(
                    item
                    for item in service_actions
                    if isinstance(item, EnableServerDhcp)
                )
                direct.expected.update(
                    {
                        "interface": pool.interface,
                        "pool_name": pool.pool_name,
                        "effective_pool_name": (
                            pool.effective_pool_name or pool.pool_name
                        ),
                        "network": pool.network,
                        "prefix": pool.prefix,
                        "netmask": pool.netmask,
                        "gateway": pool.gateway,
                        "dns_server": pool.dns_server,
                        "lease_start": pool.lease_start,
                        "lease_end": pool.lease_end,
                        "max_users": pool.max_users,
                        "excluded_ranges_json": json.dumps(
                            [
                                item.model_dump(mode="json")
                                for item in pool.excluded_ranges
                            ],
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    }
                )
            expectations.append(direct)
            if service.service_type is ServiceType.SMTP:
                expectations.extend(
                    self._mail_expectations(
                        service,
                        service_actions,
                        pop3_on_host=any(
                            item.service_type is ServiceType.POP3
                            and item.host_device_id == service.host_device_id
                            for item in services
                        ),
                        devices=devices,
                    )
                )
                continue
            requirement = requirements[service.id]
            if service.service_type is ServiceType.DHCP:
                pool = next(
                    item
                    for item in service_actions
                    if isinstance(item, ConfigureServerDhcpPool)
                )
                acquisitions = {
                    item.host_device_id: item
                    for item in service_actions
                    if isinstance(item, AcquireDhcpLease)
                }
                for client_id in service.client_device_ids:
                    client = devices[client_id]
                    foundation = cast(SetEndpointDhcp, foundations[client_id])
                    acquisition = acquisitions.get(client_id)
                    lease = ServiceVerificationExpectation(
                        id=_stable_id("verify-dhcp-lease", service.id, client_id),
                        service_id=service.id,
                        action_id=(
                            acquisition.id
                            if acquisition
                            else (
                                next(
                                    item.id
                                    for item in service_actions
                                    if isinstance(item, EnableServerDhcp)
                                )
                                if requirement.verification_mode == "state_only"
                                else pool.id
                            )
                        ),
                        kind=ServiceVerificationKind.DHCP_LEASE,
                        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
                        host_device_id=service.host_device_id,
                        host_device_name=service.host_device_name,
                        client_device_id=client_id,
                        client_device_name=client.name,
                        host_model=service.host_model,
                        client_model=client.model,
                        required=acquisition is not None
                        or requirement.verification_mode == "state_only",
                        expected={
                            "interface": foundation.interface,
                            "server_interface": pool.interface,
                            "network": pool.network,
                            "prefix": pool.prefix,
                            "netmask": pool.netmask,
                            "gateway": pool.gateway,
                            "dns_server": pool.dns_server,
                            "configure_only": (
                                requirement.verification_mode == "configure_only"
                            ),
                            "server_device_id": service.host_device_id,
                            "server_device_name": service.host_device_name,
                            "pool_name": pool.pool_name,
                            "effective_pool_name": (
                                pool.effective_pool_name or pool.pool_name
                            ),
                            "state_only": requirement.verification_mode == "state_only",
                            "native_inactive_clients_json": json.dumps(
                                [
                                    item.model_dump(mode="json")
                                    for item in (
                                        enable.native_policy.inactive_clients
                                        if enable.native_policy is not None
                                        else []
                                    )
                                ],
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            "max_users": pool.max_users,
                            "lease_start": pool.lease_start,
                            "lease_end": pool.lease_end,
                            "excluded_ranges_json": json.dumps(
                                [
                                    item.model_dump(mode="json")
                                    for item in pool.excluded_ranges
                                ],
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        },
                    )
                    expectations.append(lease)
                    if requirement.verification_mode != "state_only":
                        expectations.append(
                            ServiceVerificationExpectation(
                                id=_stable_id(
                                    "verify-dhcp-attribution", service.id, client_id
                                ),
                                service_id=service.id,
                                action_id=pool.id,
                                kind=ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED,
                                evidence_kind=ServiceEvidenceKind.DIRECT_STATE,
                                host_device_id=service.host_device_id,
                                host_device_name=service.host_device_name,
                                client_device_id=client_id,
                                client_device_name=client.name,
                                host_model=service.host_model,
                                client_model=client.model,
                                expected=dict(lease.expected),
                                required=False,
                            )
                        )
                continue
            # `verification_required=False` makes the expectations OPTIONAL, it
            # does not delete them. Compiling nothing would leave the selected
            # clients with no row at all, and R-COV-01 requires a row per
            # selected client per service, including the ones that never gate.
            for client_id in service.client_device_ids:
                client = devices[client_id]
                if service.service_type is ServiceType.DNS:
                    records = [
                        item
                        for item in service_actions
                        if isinstance(item, AddDnsRecord)
                    ]
                    for record in records:
                        item = ServiceVerificationExpectation(
                            id=_stable_id(
                                "verify-dns", service.id, client_id, record.hostname
                            ),
                            service_id=service.id,
                            action_id=record.id,
                            kind=ServiceVerificationKind.DNS_RESOLUTION,
                            evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
                            host_device_id=service.host_device_id,
                            host_device_name=service.host_device_name,
                            client_device_id=client_id,
                            client_device_name=client.name,
                            expected={
                                "hostname": record.hostname,
                                "address": record.address,
                            },
                        )
                        dns_resolutions[(client_id, record.hostname)] = item.id
                        expectations.append(item)
                    negative_name = f"missing-{hashlib.sha256(service.id.encode()).hexdigest()[:8]}.example.local"
                    expectations.append(
                        ServiceVerificationExpectation(
                            id=_stable_id("verify-dns-negative", service.id, client_id),
                            service_id=service.id,
                            action_id=terminal.id,
                            kind=ServiceVerificationKind.DNS_NEGATIVE_CONTROL,
                            evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
                            host_device_id=service.host_device_id,
                            host_device_name=service.host_device_name,
                            client_device_id=client_id,
                            client_device_name=client.name,
                            expected={"hostname": negative_name, "must_resolve": False},
                        )
                    )
                    # Advisory only (R-CAP-06). It reads the client's own
                    # resolver setting back, which is a different claim from
                    # resolving a name, and it has no evidence at all until
                    # M-DNS-3 records one. It is compiled so the operator can
                    # see it was not attempted; it never gates anything.
                    expectations.append(
                        ServiceVerificationExpectation(
                            id=_stable_id(
                                "verify-client-dns-server", service.id, client_id
                            ),
                            service_id=service.id,
                            action_id=terminal.id,
                            kind=ServiceVerificationKind.CLIENT_DNS_SERVER,
                            evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
                            host_device_id=service.host_device_id,
                            host_device_name=service.host_device_name,
                            client_device_id=client_id,
                            client_device_name=client.name,
                            required=False,
                            expected={"server_address": service.address},
                        )
                    )
                elif service.service_type in {ServiceType.HTTP, ServiceType.HTTPS}:
                    shared = self._shared_content(service.id, actions)
                    content = shared.content if shared else ""
                    fetch = ServiceVerificationExpectation(
                        id=_stable_id("verify-http-ip", service.id, client_id),
                        service_id=service.id,
                        action_id=terminal.id,
                        kind=(
                            ServiceVerificationKind.HTTPS_FETCH
                            if service.service_type is ServiceType.HTTPS
                            else ServiceVerificationKind.HTTP_FETCH
                        ),
                        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
                        host_device_id=service.host_device_id,
                        host_device_name=service.host_device_name,
                        client_device_id=client_id,
                        client_device_name=client.name,
                        expected={
                            "address": service.address,
                            "marker": content,
                            "scheme": service.service_type.value,
                        },
                    )
                    http_fetches[(service.id, client_id)] = fetch.id
                    expectations.append(fetch)
                elif service.service_type is ServiceType.NTP:
                    expectations.append(
                        ServiceVerificationExpectation(
                            id=_stable_id("verify-ntp", service.id, client_id),
                            service_id=service.id,
                            action_id=terminal.id,
                            kind=ServiceVerificationKind.NTP_SYNC,
                            evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
                            host_device_id=service.host_device_id,
                            host_device_name=service.host_device_name,
                            client_device_id=client_id,
                            client_device_name=client.name,
                            expected={"address": service.address},
                        )
                    )
                elif service.service_type is ServiceType.TFTP:
                    for published in (
                        item
                        for item in service_actions
                        if isinstance(item, PublishTftpFile)
                    ):
                        expectations.append(
                            ServiceVerificationExpectation(
                                id=_stable_id(
                                    "verify-tftp",
                                    service.id,
                                    client_id,
                                    published.filename,
                                ),
                                service_id=service.id,
                                action_id=published.id,
                                kind=ServiceVerificationKind.TFTP_RETRIEVE,
                                evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
                                host_device_id=service.host_device_id,
                                host_device_name=service.host_device_name,
                                client_device_id=client_id,
                                client_device_name=client.name,
                                expected={
                                    "address": service.address,
                                    "filename": published.filename,
                                    "content_sha256": published.content_sha256,
                                },
                            )
                        )
        for service in sorted(services, key=lambda item: item.id):
            requirement = requirements[service.id]
            if service.service_type is not ServiceType.HTTP or not requirement.hostname:
                continue
            hostname = requirement.hostname.casefold()
            if not _HOSTNAME_RE.fullmatch(hostname):
                continue
            for client_id in service.client_device_ids:
                dns_id = dns_resolutions.get((client_id, hostname))
                fetch_id = http_fetches.get((service.id, client_id))
                if not dns_id or not fetch_id:
                    continue
                client = devices[client_id]
                expectations.append(
                    ServiceVerificationExpectation(
                        id=_stable_id(
                            "verify-http-name", service.id, client_id, hostname
                        ),
                        service_id=service.id,
                        action_id=by_service[service.id][-1].id,
                        kind=ServiceVerificationKind.HTTP_BY_HOSTNAME,
                        evidence_kind=ServiceEvidenceKind.COMPOSED_BEHAVIORAL,
                        host_device_id=service.host_device_id,
                        host_device_name=service.host_device_name,
                        client_device_id=client_id,
                        client_device_name=client.name,
                        depends_on=sorted([dns_id, fetch_id]),
                        expected={
                            "hostname": hostname,
                            "marker": (
                                shared.content
                                if (shared := self._shared_content(service.id, actions))
                                else ""
                            ),
                        },
                    )
                )
        self._bind_expectation_targets(expectations, services, requirements, devices)
        return sorted(
            expectations,
            key=lambda item: (
                1
                if item.evidence_kind is ServiceEvidenceKind.COMPOSED_BEHAVIORAL
                else 0,
                item.service_id,
                item.kind.value,
                item.client_device_id,
                item.id,
            ),
        )

    @staticmethod
    def _mail_expectations(
        service: ServiceDefinition,
        service_actions: list[ServiceAction],
        *,
        pop3_on_host: bool,
        devices: dict[str, DevicePlan],
    ) -> list[ServiceVerificationExpectation]:
        """Compile the client read-backs and every pair's rows for one SMTP service.

        Every row belongs to the SMTP service, so no expectation depends on a
        service that admission might exclude. Under the R-EVT-05 fallback only
        mailbox presence gates the service: the send event, the retrieval and
        their composition compile optional and report a typed blocked result.
        """
        common = dict(
            service_id=service.id,
            host_device_id=service.host_device_id,
            host_device_name=service.host_device_name,
        )
        rows: list[ServiceVerificationExpectation] = []
        clients = {
            item.host_device_id: item
            for item in service_actions
            if isinstance(item, ConfigureEmailClient)
        }
        by_mail = {item.mail_id: device for device, item in clients.items()}
        for client_id, action in sorted(clients.items()):
            rows.append(
                ServiceVerificationExpectation(
                    id=_stable_id("verify-email-client", service.id, client_id),
                    action_id=action.id,
                    kind=ServiceVerificationKind.EMAIL_CLIENT_STATE,
                    evidence_kind=ServiceEvidenceKind.DIRECT_STATE,
                    client_device_id=client_id,
                    client_device_name=devices[client_id].name,
                    expected={
                        "name": action.display_name,
                        "user": action.username,
                        "mail_id": action.mail_id,
                        "smtp_server": action.smtp_server,
                        "pop3_server": action.pop3_server,
                    },
                    **common,
                )
            )
        for send in (
            item for item in service_actions if isinstance(item, SendMailMessage)
        ):
            sender = send.host_device_id
            recipient = by_mail[send.recipient_mail_id]
            pair = {
                "message_ref": send.message_ref,
                "sender_mail_id": send.sender_mail_id,
                "recipient_mail_id": send.recipient_mail_id,
            }
            smtp_send = ServiceVerificationExpectation(
                id=_stable_id("verify-smtp-send", service.id, send.id),
                action_id=send.id,
                kind=ServiceVerificationKind.SMTP_SEND,
                evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
                client_device_id=sender,
                client_device_name=devices[sender].name,
                required=False,
                expected=dict(pair),
                **common,
            )
            rows.append(smtp_send)
            rows.append(
                ServiceVerificationExpectation(
                    id=_stable_id("verify-smtp-delivered", service.id, send.id),
                    action_id=send.id,
                    kind=ServiceVerificationKind.SMTP_DELIVERED,
                    evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
                    client_device_id=recipient,
                    client_device_name=devices[recipient].name,
                    expected={**pair, "recipient_username": send.recipient_username},
                    **common,
                )
            )
            if not pop3_on_host:
                continue
            retrieve = ServiceVerificationExpectation(
                id=_stable_id("verify-pop3-retrieve", service.id, send.id),
                action_id=send.id,
                kind=ServiceVerificationKind.POP3_RETRIEVE,
                evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
                client_device_id=recipient,
                client_device_name=devices[recipient].name,
                depends_on=[smtp_send.id],
                required=False,
                expected=dict(pair),
                **common,
            )
            rows.append(retrieve)
            rows.append(
                ServiceVerificationExpectation(
                    id=_stable_id("verify-email-end-to-end", service.id, send.id),
                    action_id=send.id,
                    kind=ServiceVerificationKind.EMAIL_END_TO_END,
                    evidence_kind=ServiceEvidenceKind.COMPOSED_BEHAVIORAL,
                    client_device_id=recipient,
                    client_device_name=devices[recipient].name,
                    depends_on=sorted([smtp_send.id, retrieve.id]),
                    required=False,
                    expected=dict(pair),
                    **common,
                )
            )
        return rows

    @staticmethod
    def _bind_expectation_targets(
        expectations, services, requirements, devices
    ) -> None:
        """Record the model each expectation is observed on, and whether it gates.

        Capability is resolved on the model that performs the operation, so the
        model has to be part of the compiled expectation rather than something
        the applicator infers later from whichever device it happens to have.
        An expectation already marked optional at its construction site stays
        optional: a service whose verification is required cannot promote an
        advisory reader that has no evidence.
        """
        by_id = {item.id: item for item in services}
        for expectation in expectations:
            service = by_id.get(expectation.service_id)
            if service is None:
                continue
            expectation.host_model = service.host_model
            if expectation.client_device_id:
                client = devices.get(expectation.client_device_id)
                expectation.client_model = client.model if client is not None else ""
            requirement = requirements.get(expectation.service_id)
            if requirement is not None and not requirement.verification_required:
                expectation.required = False

    @staticmethod
    def _semantic_hash(plan: ServicePlan) -> str:
        payload = plan.model_dump(mode="json")
        payload["semantic_hash"] = ""
        # Additive scheduling metadata must not perturb legacy plan identities
        # when it is absent. Non-empty prerequisites remain hash-bound.
        for action in payload["actions"]:
            if not action.get("verification_dependencies"):
                action.pop("verification_dependencies", None)
            # Shared page ownership is semantic only once it binds more than
            # the action's own service: a content action that serves nobody
            # else is the plan it always was. The source record is provenance
            # for the contract, so two plans that differ only by which
            # measurement is cited are the same plan.
            action.pop("content_source_record", None)
            if action.get("shared_service_ids") in (
                None,
                [],
                [action.get("service_id")],
            ):
                action.pop("shared_service_ids", None)
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _deduplicate_issues(issues):
        unique = {
            (item.severity.value, item.code.value, item.subject, item.message): item
            for item in issues
        }
        return [unique[key] for key in sorted(unique)]

    @staticmethod
    def _result(plan, actions, topology, configuration, services, expectations, issues):
        summary = ServiceCompileSummary(
            service_plan_id=plan.id if plan else "",
            semantic_hash=plan.semantic_hash if plan else "",
            source_topology_hash=topology.physical_identity_hash,
            source_topology_hash_schema=(
                "physical-topology-v2"
                if topology.physical_topology_hash
                else "legacy-full-v1"
            ),
            source_configuration_hash=configuration.semantic_hash,
            service_count=len(services),
            action_count=len(actions),
            actions_by_type=service_action_type_counts(actions),
            dependencies=sum(len(item.depends_on) for item in actions),
            verification_expectations=len(expectations),
            warnings=sum(
                item.severity is ConfigurationIssueSeverity.WARNING for item in issues
            ),
            errors=sum(
                item.severity is ConfigurationIssueSeverity.ERROR for item in issues
            ),
        )
        return ServiceCompileResult(
            plan=plan,
            semantic_hash=plan.semantic_hash if plan else "",
            summary=summary,
            issues=issues,
        )
