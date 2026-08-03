"""E6: EnterprisePlan + E4 + E5 -> ServicePlan puro y determinista."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections import defaultdict

from ...models.plans import DevicePlan, TopologyPlan
from ..models.capabilities import CapabilityStatus
from ..models.configuration import (
    ConfigurationIssue,
    ConfigurationIssueCode,
    ConfigurationIssueSeverity,
    ConfigurationPlan,
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
    AddDnsRecord,
    ConfigureNtpService,
    EnableDnsService,
    EnableHttpService,
    EnableHttpsService,
    EnableTftpService,
    FoundationalServiceRequirement,
    PublishTftpFile,
    ServiceAction,
    ServiceCapabilityProfile,
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
from .configuration_dependencies import (
    ConfigurationDependencyError,
    order_dependency_actions,
)


_HOSTNAME_RE = re.compile(
    r"(?=^.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
_SAFE_TFTP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,126}$")
_SAFE_HTTP_CONTENT = re.compile(r"^[\x20-\x7E\r\n\t]{0,4096}$")
_SERVICE_PROTOCOLS = {
    ServiceType.DNS: ("udp/tcp", [53]),
    ServiceType.HTTP: ("tcp", [80]),
    ServiceType.HTTPS: ("tcp", [443]),
    ServiceType.NTP: ("udp", [123]),
    ServiceType.TFTP: ("udp", [69]),
}
_SERVICE_HOST_ROLES = {
    ServiceType.DNS: (DeviceRole.DNS_SERVER.value, DeviceRole.SERVER.value),
    ServiceType.HTTP: (DeviceRole.WEB_SERVER.value, DeviceRole.SERVER.value),
    ServiceType.HTTPS: (DeviceRole.WEB_SERVER.value, DeviceRole.SERVER.value),
    ServiceType.NTP: (DeviceRole.NTP_SERVER.value, DeviceRole.SERVER.value),
    ServiceType.TFTP: (DeviceRole.TFTP_SERVER.value, DeviceRole.SERVER.value),
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
        issues: list[ConfigurationIssue] = []
        capabilities = capabilities or {}
        if not topology.semantic_hash:
            issues.append(_error(
                ConfigurationIssueCode.SOURCE_TOPOLOGY_HASH_MISSING,
                "E6 requires the immutable semantic hash produced by E4.",
                topology.id,
            ))
        if not configuration.semantic_hash:
            issues.append(_error(
                ConfigurationIssueCode.SOURCE_CONFIGURATION_HASH_MISSING,
                "E6 requires the immutable semantic hash produced by E5.",
                configuration.id,
            ))
        if configuration.source_topology_hash != topology.semantic_hash:
            issues.append(_error(
                ConfigurationIssueCode.SOURCE_CONFIGURATION_TOPOLOGY_MISMATCH,
                "The E5 ConfigurationPlan was compiled for a different E4 topology.",
                configuration.id,
            ))

        devices = {(item.id or item.name): item for item in topology.devices}
        foundations = {
            item.device_id: item
            for item in configuration.actions
            if isinstance(item, (SetEndpointStaticAddress, SetEndpointDhcp))
        }
        l3_foundations: dict[str, list[object]] = defaultdict(list)
        for item in configuration.actions:
            if isinstance(item, (ConfigureRoutedInterface, ConfigureSvi, ConfigureSubinterface)):
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
                issues.append(_error(
                    ConfigurationIssueCode.SERVICE_TYPE_INVALID,
                    f"{requirement.name!r} does not identify a supported E6 service type.",
                    service_id,
                ))
                continue
            host = self._host(requirement, service_type, site_id, devices)
            if host is None:
                issues.append(_error(
                    ConfigurationIssueCode.SERVICE_HOST_MISSING,
                    f"No existing E4 host can run {service_type.value} for {requirement.name}.",
                    service_id,
                ))
                continue
            host_id = host.id or host.name
            host_foundation = foundations.get(host_id)
            if not isinstance(host_foundation, SetEndpointStaticAddress):
                issues.append(_error(
                    ConfigurationIssueCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                    f"Service host {host.name} has no static E5 endpoint address action.",
                    host_id,
                ))
                continue
            address = requirement.address or host_foundation.ipv4
            try:
                address = str(ipaddress.ip_address(address))
            except ValueError:
                issues.append(_error(
                    ConfigurationIssueCode.SERVICE_ADDRESS_INVALID,
                    f"{address!r} is not a valid service address.",
                    service_id,
                ))
                continue
            if address != host_foundation.ipv4:
                issues.append(_error(
                    ConfigurationIssueCode.SERVICE_ADDRESS_MISMATCH,
                    f"Service address {address} does not belong to host {host.name} in E5.",
                    service_id,
                ))
            if requirement.segment_id and requirement.segment_id != host_foundation.segment_id:
                issues.append(_error(
                    ConfigurationIssueCode.SERVICE_SEGMENT_MISMATCH,
                    f"Service segment {requirement.segment_id} differs from E5 segment "
                    f"{host_foundation.segment_id}.",
                    service_id,
                ))

            client_ids = self._clients(
                requirement, site_id, host_id, devices, foundations, issues, service_id,
            )
            self._add_foundation(foundation_requirements, host, host_foundation)
            for client_id in client_ids:
                self._add_foundation(
                    foundation_requirements, devices[client_id], foundations[client_id],
                )
                client_foundation = foundations[client_id]
                if client_foundation.segment_id != host_foundation.segment_id:
                    for segment_id in sorted({
                        client_foundation.segment_id, host_foundation.segment_id,
                    }):
                        candidates = sorted(
                            l3_foundations.get(segment_id, []), key=lambda item: item.id,
                        )
                        if not candidates:
                            issues.append(_error(
                                ConfigurationIssueCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                                f"Cross-segment service path lacks an E5 L3 action for {segment_id!r}.",
                                f"{service_id}:{segment_id}",
                            ))
                            continue
                        gateway_action = candidates[0]
                        gateway_device = devices.get(gateway_action.device_id)
                        if gateway_device is None:
                            issues.append(_error(
                                ConfigurationIssueCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                                f"E5 L3 action {gateway_action.id} has no E4 device.",
                                gateway_action.id,
                            ))
                            continue
                        self._add_foundation(
                            foundation_requirements, gateway_device, gateway_action,
                        )

            profile = capabilities.get(f"{host.model}:{service_type.value}")
            if profile and profile.compile_support is CapabilityStatus.UNSUPPORTED:
                issues.append(_warning(
                    ConfigurationIssueCode.CAPABILITY_UNSUPPORTED,
                    f"Compilation support for {service_type.value} is unsupported.",
                    service_id,
                ))
            if profile is None or profile.application_support is CapabilityStatus.UNKNOWN:
                issues.append(_warning(
                    ConfigurationIssueCode.CAPABILITY_UNVERIFIED,
                    f"Runtime application support for {host.model}:{service_type.value} is unknown.",
                    service_id,
                ))
            elif profile.application_support is CapabilityStatus.UNSUPPORTED:
                issues.append(_warning(
                    ConfigurationIssueCode.CAPABILITY_UNSUPPORTED,
                    f"Runtime application support for {host.model}:{service_type.value} is unsupported.",
                    service_id,
                ))

            service_actions = self._actions(
                service_id, requirement, service_type, host, host_foundation, devices, issues,
            )
            if profile is not None:
                for action in service_actions:
                    action_support = profile.action_application_support.get(
                        action.action_type.value, profile.application_support,
                    )
                    if action_support is CapabilityStatus.UNKNOWN:
                        issues.append(_warning(
                            ConfigurationIssueCode.CAPABILITY_UNVERIFIED,
                            f"Runtime application support for {action.action_type.value} is unknown.",
                            action.id,
                        ))
                    elif action_support is CapabilityStatus.UNSUPPORTED:
                        issues.append(_warning(
                            ConfigurationIssueCode.CAPABILITY_UNSUPPORTED,
                            f"Runtime application support for {action.action_type.value} is unsupported.",
                            action.id,
                        ))
            actions.extend(service_actions)
            action_ids_by_service[service_id] = [item.id for item in service_actions]
            source_requirements[service_id] = requirement
            protocol, ports = _SERVICE_PROTOCOLS[service_type]
            services.append(ServiceDefinition(
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
            ))

        by_name = {item.name.casefold(): item for item in services}
        by_id = {item.id: item for item in services}
        for service in services:
            requirement = source_requirements[service.id]
            if not requirement.depends_on or not service.action_ids:
                continue
            first = next(item for item in actions if item.id == service.action_ids[0])
            for dependency_name in sorted(set(requirement.depends_on), key=str.casefold):
                dependency = by_name.get(dependency_name.casefold()) or by_id.get(dependency_name)
                if dependency is None or not dependency.action_ids:
                    issues.append(_error(
                        ConfigurationIssueCode.DEPENDENCY_MISSING,
                        f"Service dependency {dependency_name!r} does not exist.",
                        service.id,
                    ))
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

        errors = any(item.severity is ConfigurationIssueSeverity.ERROR for item in issues)
        if not errors:
            expectations = self._expectations(services, actions, source_requirements, devices)
            by_service_expectations: dict[str, list[str]] = defaultdict(list)
            for item in expectations:
                by_service_expectations[item.service_id].append(item.id)
            for service in services:
                service.verification_expectation_ids = by_service_expectations[service.id]

        issues = self._deduplicate_issues(issues)
        if any(item.severity is ConfigurationIssueSeverity.ERROR for item in issues):
            return self._result(None, actions, topology, configuration, services, expectations, issues)

        plan = ServicePlan(
            id=f"services_{topology.id or topology.semantic_hash[:16]}",
            source_topology_id=topology.id,
            source_topology_hash=topology.semantic_hash,
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
        return self._result(plan, actions, topology, configuration, services, expectations, issues)

    @staticmethod
    def _requirements(enterprise: EnterprisePlan) -> list[tuple[str, ServiceRequirement]]:
        values = [
            (site.site_id, requirement)
            for site in enterprise.sites
            for requirement in site.services
        ]
        values.extend((requirement.metadata.get("site_id", ""), requirement)
                      for requirement in enterprise.services)
        return sorted(values, key=lambda item: (
            item[0], item[1].service_type.value if item[1].service_type else "",
            item[1].name.casefold(),
        ))

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
            item for item in devices.values()
            if (not site_id or item.site_id == site_id)
            and item.enterprise_role in _SERVICE_HOST_ROLES[service_type]
        ]
        role_order = {role: index for index, role in enumerate(_SERVICE_HOST_ROLES[service_type])}
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
                device_id for device_id, device in devices.items()
                if device_id != host_id and (not site_id or device.site_id == site_id)
                and device_id in foundations
                and device.enterprise_role not in {
                    DeviceRole.SERVER.value, DeviceRole.DNS_SERVER.value,
                    DeviceRole.WEB_SERVER.value, DeviceRole.NTP_SERVER.value,
                    DeviceRole.TFTP_SERVER.value,
                }
            )
        valid: list[str] = []
        for client_id in requested:
            if client_id not in devices:
                issues.append(_error(
                    ConfigurationIssueCode.SERVICE_CLIENT_MISSING,
                    f"Service client {client_id!r} does not exist in E4.", service_id,
                ))
            elif client_id not in foundations:
                issues.append(_error(
                    ConfigurationIssueCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                    f"Service client {client_id!r} has no E5 endpoint addressing action.", service_id,
                ))
            else:
                valid.append(client_id)
        return valid

    @staticmethod
    def _add_foundation(target, device: DevicePlan, action) -> None:
        device_id = device.id or device.name
        target[action.id] = FoundationalServiceRequirement(
            id=_stable_id("foundation", device_id, action.id),
            device_id=device_id,
            device_name=device.name,
            model=device.model,
            ipv4=getattr(action, "ipv4", ""),
            segment_id=action.segment_id,
            configuration_action_id=action.id,
        )

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
                id=_stable_id("enable-dns", service_id), phase=ServicePhase.ENABLE, **common,
            )
            records: dict[tuple[str, str], object] = {}
            targets: dict[str, str] = {}
            for record in sorted(
                requirement.dns_records,
                key=lambda item: (item.hostname.casefold(), item.record_type, item.address),
            ):
                hostname = record.hostname.casefold()
                if record.target_device_id and record.target_device_id not in devices:
                    issues.append(_error(
                        ConfigurationIssueCode.SERVICE_HOST_MISSING,
                        f"DNS target device {record.target_device_id!r} does not exist in E4.",
                        service_id,
                    ))
                if not _HOSTNAME_RE.fullmatch(hostname):
                    issues.append(_error(
                        ConfigurationIssueCode.DNS_HOSTNAME_INVALID,
                        f"DNS hostname {record.hostname!r} is invalid.", service_id,
                    ))
                    continue
                try:
                    address = str(ipaddress.ip_address(record.address))
                except ValueError:
                    issues.append(_error(
                        ConfigurationIssueCode.SERVICE_ADDRESS_INVALID,
                        f"DNS target {record.address!r} is not a valid IPv4 address.", service_id,
                    ))
                    continue
                prior = targets.get(hostname)
                if prior is not None and prior != address:
                    issues.append(_error(
                        ConfigurationIssueCode.DNS_RECORD_CONFLICT,
                        f"DNS hostname {hostname} maps to both {prior} and {address}.", service_id,
                    ))
                    continue
                targets[hostname] = address
                records[(hostname, address)] = record
            return [enable, *[
                AddDnsRecord(
                    id=_stable_id("dns-a", service_id, hostname, address),
                    phase=ServicePhase.CONTENT,
                    depends_on=[enable.id],
                    hostname=hostname,
                    address=address,
                    **common,
                )
                for hostname, address in sorted(records)
            ]]
        if service_type is ServiceType.HTTP:
            enable = EnableHttpService(
                id=_stable_id("enable-http", service_id), phase=ServicePhase.ENABLE, **common,
            )
            content = requirement.http_content or f"MCP_E6_HTTP_OK_{_stable_id('http', service_id)[-8:]}"
            if not _SAFE_HTTP_CONTENT.fullmatch(content):
                issues.append(_error(
                    ConfigurationIssueCode.HTTP_CONTENT_UNSAFE,
                    "HTTP content must be bounded printable text.", service_id,
                ))
                return [enable]
            return [enable, SetHttpContent(
                id=_stable_id("http-content", service_id, content),
                phase=ServicePhase.CONTENT,
                depends_on=[enable.id],
                content=content,
                content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                **common,
            )]
        if service_type is ServiceType.HTTPS:
            return [EnableHttpsService(
                id=_stable_id("enable-https", service_id), phase=ServicePhase.ENABLE, **common,
            )]
        if service_type is ServiceType.NTP:
            return [ConfigureNtpService(
                id=_stable_id("configure-ntp", service_id), phase=ServicePhase.ENABLE,
                authoritative=requirement.ntp_authoritative, **common,
            )]
        enable = EnableTftpService(
            id=_stable_id("enable-tftp", service_id), phase=ServicePhase.ENABLE, **common,
        )
        files: dict[tuple[str, str], object] = {}
        for item in sorted(requirement.tftp_files, key=lambda value: (value.filename, value.content)):
            if not _SAFE_TFTP_NAME.fullmatch(item.filename) or ".." in item.filename:
                issues.append(_error(
                    ConfigurationIssueCode.TFTP_FILENAME_UNSAFE,
                    f"TFTP filename {item.filename!r} is not a safe server-local name.", service_id,
                ))
                continue
            digest = hashlib.sha256(item.content.encode("utf-8")).hexdigest()
            files[(item.filename, digest)] = item
        return [enable, *[
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
        ]]

    def _expectations(self, services, actions, requirements, devices):
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
            terminal = service_actions[-1]
            direct = ServiceVerificationExpectation(
                id=_stable_id("verify-direct", service.id),
                service_id=service.id,
                action_id=terminal.id,
                kind=ServiceVerificationKind.DIRECT_SERVICE_STATE,
                evidence_kind=ServiceEvidenceKind.DIRECT_STATE,
                host_device_id=service.host_device_id,
                host_device_name=service.host_device_name,
                expected={"enabled": True, "service_type": service.service_type.value},
            )
            if service.service_type is ServiceType.DNS:
                direct.expected["records_json"] = json.dumps(
                    {
                        item.hostname: item.address
                        for item in service_actions if isinstance(item, AddDnsRecord)
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            elif service.service_type in {ServiceType.HTTP, ServiceType.HTTPS}:
                direct.expected["marker"] = next(
                    (item.content for item in service_actions if isinstance(item, SetHttpContent)),
                    "",
                )
            expectations.append(direct)
            requirement = requirements[service.id]
            if not requirement.verification_required:
                continue
            for client_id in service.client_device_ids:
                client = devices[client_id]
                if service.service_type is ServiceType.DNS:
                    records = [item for item in service_actions if isinstance(item, AddDnsRecord)]
                    for record in records:
                        item = ServiceVerificationExpectation(
                            id=_stable_id("verify-dns", service.id, client_id, record.hostname),
                            service_id=service.id,
                            action_id=record.id,
                            kind=ServiceVerificationKind.DNS_RESOLUTION,
                            evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
                            host_device_id=service.host_device_id,
                            host_device_name=service.host_device_name,
                            client_device_id=client_id,
                            client_device_name=client.name,
                            expected={"hostname": record.hostname, "address": record.address},
                        )
                        dns_resolutions[(client_id, record.hostname)] = item.id
                        expectations.append(item)
                    negative_name = f"missing-{hashlib.sha256(service.id.encode()).hexdigest()[:8]}.example.local"
                    expectations.append(ServiceVerificationExpectation(
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
                    ))
                elif service.service_type in {ServiceType.HTTP, ServiceType.HTTPS}:
                    content = next(
                        (item.content for item in service_actions if isinstance(item, SetHttpContent)), "",
                    )
                    fetch = ServiceVerificationExpectation(
                        id=_stable_id("verify-http-ip", service.id, client_id),
                        service_id=service.id,
                        action_id=terminal.id,
                        kind=ServiceVerificationKind.HTTP_FETCH,
                        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
                        host_device_id=service.host_device_id,
                        host_device_name=service.host_device_name,
                        client_device_id=client_id,
                        client_device_name=client.name,
                        expected={"address": service.address, "marker": content},
                    )
                    http_fetches[(service.id, client_id)] = fetch.id
                    expectations.append(fetch)
                elif service.service_type is ServiceType.NTP:
                    expectations.append(ServiceVerificationExpectation(
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
                    ))
                elif service.service_type is ServiceType.TFTP:
                    for published in (
                        item for item in service_actions if isinstance(item, PublishTftpFile)
                    ):
                        expectations.append(ServiceVerificationExpectation(
                            id=_stable_id("verify-tftp", service.id, client_id, published.filename),
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
                        ))
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
                expectations.append(ServiceVerificationExpectation(
                    id=_stable_id("verify-http-name", service.id, client_id, hostname),
                    service_id=service.id,
                    action_id=by_service[service.id][-1].id,
                    kind=ServiceVerificationKind.HTTP_BY_HOSTNAME,
                    evidence_kind=ServiceEvidenceKind.COMPOSED_BEHAVIORAL,
                    host_device_id=service.host_device_id,
                    host_device_name=service.host_device_name,
                    client_device_id=client_id,
                    client_device_name=client.name,
                    depends_on=sorted([dns_id, fetch_id]),
                    expected={"hostname": hostname, "marker": next(
                        (item.content for item in by_service[service.id]
                         if isinstance(item, SetHttpContent)), "",
                    )},
                ))
        return sorted(expectations, key=lambda item: (
            1 if item.evidence_kind is ServiceEvidenceKind.COMPOSED_BEHAVIORAL else 0,
            item.service_id, item.kind.value, item.client_device_id, item.id,
        ))

    @staticmethod
    def _semantic_hash(plan: ServicePlan) -> str:
        payload = plan.model_dump(mode="json")
        payload["semantic_hash"] = ""
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
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
            source_topology_hash=topology.semantic_hash,
            source_configuration_hash=configuration.semantic_hash,
            service_count=len(services),
            action_count=len(actions),
            actions_by_type=service_action_type_counts(actions),
            dependencies=sum(len(item.depends_on) for item in actions),
            verification_expectations=len(expectations),
            warnings=sum(item.severity is ConfigurationIssueSeverity.WARNING for item in issues),
            errors=sum(item.severity is ConfigurationIssueSeverity.ERROR for item in issues),
        )
        return ServiceCompileResult(
            plan=plan,
            semantic_hash=plan.semantic_hash if plan else "",
            summary=summary,
            issues=issues,
        )
