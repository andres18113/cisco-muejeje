"""E7: compila telefonía sin CLI, bridge ni objetos Packet Tracer."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from os.path import commonprefix

from ...models.plans import DevicePlan, TopologyPlan
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
from ..models.enterprise_plan import EnterprisePlan
from ..models.roles import DeviceRole
from ..models.service_plan import ServicePlan
from ..models.voice_plan import (
    BindPhoneToExtension,
    CallControlInstance,
    CallExpectation,
    CallExpectationResult,
    ConfigureCallControlSource,
    ConfigureDialRule,
    ConfigureVoiceDhcpOption,
    CreateExtension,
    DialRule,
    EnableCallControl,
    ExtensionRange,
    GeneratePhoneConfigurationFiles,
    PhoneAssignment,
    VoiceAction,
    VoiceCapabilityDimension,
    VoiceCapabilityProfile,
    VoiceCapabilityStatus,
    VoiceCompileResult,
    VoiceCompileSummary,
    VoiceFoundationRequirement,
    VoiceIntent,
    VoicePhase,
    VoicePlan,
    VoiceVerificationExpectation,
    VoiceVerificationKind,
    voice_action_type_counts,
)
from ..models.verification import PrerequisiteKind, VerificationPrerequisite
from .configuration_dependencies import (
    ConfigurationDependencyError,
    order_dependency_actions,
)
from .extension_allocator import (
    ExtensionAllocationError,
    ExtensionAllocator,
    natural_identity_key,
)


_ADDRESSING_ACTIONS = (SetEndpointStaticAddress, SetEndpointDhcp)
_L3_ACTIONS = (ConfigureRoutedInterface, ConfigureSvi, ConfigureSubinterface)


def _stable_id(kind: str, *parts: object) -> str:
    semantic = "|".join((kind, *(str(part) for part in parts)))
    return f"voice/{kind}/{hashlib.sha256(semantic.encode('utf-8')).hexdigest()[:16]}"


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


class VoiceCompiler:
    """Transforma intención de voz y fundamentos E4/E5/E6 en acciones cerradas."""

    def __init__(self, allocator: ExtensionAllocator | None = None) -> None:
        self._allocator = allocator or ExtensionAllocator()

    def compile(
        self,
        intent: VoiceIntent,
        enterprise: EnterprisePlan,
        topology: TopologyPlan,
        configuration: ConfigurationPlan,
        *,
        service_plan: ServicePlan | None = None,
        capabilities: dict[str, VoiceCapabilityProfile] | None = None,
    ) -> VoiceCompileResult:
        del enterprise  # E7 consumes concrete E4 identities, not logical growth reserves.
        issues: list[ConfigurationIssue] = []
        capabilities = capabilities or {}
        self._validate_sources(intent, topology, configuration, service_plan, issues)

        devices = {item.id or item.name: item for item in topology.devices}
        all_phones = {
            device_id: device for device_id, device in devices.items()
            if device.enterprise_role == DeviceRole.IP_PHONE.value
        }
        requested_ids = sorted(
            set(intent.phone_device_ids) if intent.phone_device_ids else set(all_phones),
            key=natural_identity_key,
        )
        missing_phones = [item for item in requested_ids if item not in all_phones]
        for phone_id in missing_phones:
            issues.append(_error(
                ConfigurationIssueCode.PHONE_ENDPOINT_MISSING,
                f"Voice intent references phone {phone_id!r}, absent from E4.",
                phone_id,
            ))
        phones = [all_phones[item] for item in requested_ids if item in all_phones]

        access_by_phone: dict[str, list[ConfigureAccessPort]] = defaultdict(list)
        addressing_by_phone: dict[str, list[SetEndpointStaticAddress | SetEndpointDhcp]] = defaultdict(list)
        l3_by_device_segment: dict[tuple[str, str], list[object]] = defaultdict(list)
        dhcp_by_segment: dict[str, list[ConfigureDhcpPool]] = defaultdict(list)
        vlan_by_segment: dict[str, int] = {}
        for action in configuration.actions:
            if isinstance(action, CreateVlan):
                vlan_by_segment[action.segment_id] = action.vlan_id
            elif isinstance(action, ConfigureAccessPort):
                for endpoint_id in action.endpoint_ids:
                    access_by_phone[endpoint_id].append(action)
            elif isinstance(action, _ADDRESSING_ACTIONS):
                addressing_by_phone[action.device_id].append(action)
            elif isinstance(action, _L3_ACTIONS):
                l3_by_device_segment[(action.device_id, action.segment_id)].append(action)
            elif isinstance(action, ConfigureDhcpPool):
                dhcp_by_segment[action.segment_id].append(action)

        foundations: list[VoiceFoundationRequirement] = []
        usable: list[tuple[DevicePlan, ConfigureAccessPort, object]] = []
        for phone in phones:
            phone_id = phone.id or phone.name
            access = sorted(access_by_phone.get(phone_id, []), key=lambda item: item.id)
            addressing = sorted(addressing_by_phone.get(phone_id, []), key=lambda item: item.id)
            if not addressing:
                issues.append(_error(
                    ConfigurationIssueCode.PHONE_ADDRESSING_MISSING,
                    f"Phone {phone.name} has no E5 endpoint addressing action.",
                    phone_id,
                ))
                continue
            selected_addressing = addressing[0]
            expected_vlan = vlan_by_segment.get(selected_addressing.segment_id)
            voice_access = [
                item for item in access
                if item.voice_vlan_id is not None
                and (expected_vlan is None or item.voice_vlan_id == expected_vlan)
            ]
            if not voice_access:
                issues.append(_error(
                    ConfigurationIssueCode.FOUNDATIONAL_VOICE_VLAN_MISSING,
                    f"Phone {phone.name} has no E5 switch-facing voice VLAN action.",
                    phone_id,
                ))
                continue
            selected_access = voice_access[0]
            usable.append((phone, selected_access, selected_addressing))
            foundations.extend([
                VoiceFoundationRequirement(
                    id=_stable_id("foundation-vlan", phone_id, selected_access.id),
                    kind="voice_vlan", source_id=selected_access.id,
                    device_id=selected_access.device_id, site_id=phone.site_id,
                ),
                VoiceFoundationRequirement(
                    id=_stable_id("foundation-address", phone_id, selected_addressing.id),
                    kind="phone_addressing", source_id=selected_addressing.id,
                    device_id=phone_id, site_id=phone.site_id,
                ),
            ])

        phones_by_site: dict[str, list[str]] = defaultdict(list)
        usable_by_id = {}
        for item in usable:
            phone_id = item[0].id or item[0].name
            phones_by_site[item[0].site_id].append(phone_id)
            usable_by_id[phone_id] = item
        ranges = {
            site_id: intent.extension_ranges.get(site_id, intent.policy.default_extension_range)
            for site_id in phones_by_site
        }
        try:
            extensions = self._allocator.allocate(
                phones_by_site, ranges, intent.explicit_extensions,
            )
        except ExtensionAllocationError as exc:
            issues.append(_error(
                ConfigurationIssueCode(exc.code), str(exc), exc.subject,
            ))
            extensions = {}

        call_control_for_site: dict[str, str] = {}
        call_control_data: dict[str, tuple[DevicePlan, object, list[str]]] = {}
        for site_id in sorted(phones_by_site, key=natural_identity_key):
            host_id = (
                intent.call_control_device_ids.get(site_id)
                or intent.central_call_control_device_id
            )
            host = devices.get(host_id)
            if host is None:
                issues.append(_error(
                    ConfigurationIssueCode.CALL_CONTROL_HOST_MISSING,
                    f"Site {site_id!r} has no explicit existing E4 call-control target.",
                    site_id,
                ))
                continue
            segments = sorted({
                item[2].segment_id for item in usable if item[0].site_id == site_id
            })
            candidates = sorted(
                (
                    action for segment_id in segments
                    for action in l3_by_device_segment.get((host_id, segment_id), [])
                ),
                key=lambda item: item.id,
            )
            if not candidates:
                issues.append(_error(
                    ConfigurationIssueCode.CALL_CONTROL_ADDRESS_MISSING,
                    f"Call-control target {host.name} has no E5 address on the voice segment.",
                    host_id,
                ))
                continue
            call_control_id = f"call-control/{site_id}/{host_id}"
            call_control_for_site[site_id] = call_control_id
            existing = call_control_data.get(call_control_id)
            site_ids = sorted(set((existing[2] if existing else []) + [site_id]))
            call_control_data[call_control_id] = (host, candidates[0], site_ids)
            foundations.append(VoiceFoundationRequirement(
                id=_stable_id("foundation-call-control", call_control_id, candidates[0].id),
                kind="call_control_addressing", source_id=candidates[0].id,
                device_id=host_id, site_id=site_id,
            ))
            self._capability_issues(host, capabilities.get(host.model), issues)

        if intent.service_dependency_ids and service_plan is not None:
            for service_id in sorted(set(intent.service_dependency_ids)):
                if any(item.id == service_id for item in service_plan.services):
                    foundations.append(VoiceFoundationRequirement(
                        id=_stable_id("foundation-service", service_id),
                        kind="service", source_id=service_id,
                    ))

        if any(item.severity is ConfigurationIssueSeverity.ERROR for item in issues):
            return self._result(None, topology, configuration, [], [], [], issues, service_plan)

        actions: list[VoiceAction] = []
        call_controls: list[CallControlInstance] = []
        assignments: list[PhoneAssignment] = []
        dial_rules: list[DialRule] = []
        extension_action_by_phone: dict[str, str] = {}
        directory_index_by_phone: dict[str, int] = {}
        binding_action_by_phone: dict[str, str] = {}
        source_action_by_control: dict[str, str] = {}

        for call_control_id in sorted(call_control_data, key=natural_identity_key):
            host, source, site_ids = call_control_data[call_control_id]
            hosted_phone_ids = sorted(
                (
                    phone_id for site_id in site_ids
                    for phone_id in phones_by_site[site_id]
                ),
                key=natural_identity_key,
            )
            enable_id = _stable_id("enable", call_control_id)
            source_id = _stable_id("source", call_control_id, source.id)
            source_action_by_control[call_control_id] = source_id
            actions.extend([
                EnableCallControl(
                    id=enable_id, phase=VoicePhase.CALL_CONTROL,
                    call_control_id=call_control_id,
                    host_device_id=host.id or host.name, host_device_name=host.name,
                    host_model=host.model, site_id=site_ids[0],
                    required_capability=VoiceCapabilityDimension.CALL_CONTROL_CONFIG,
                    max_phones=len(hosted_phone_ids), max_extensions=len(hosted_phone_ids),
                    registration_required=intent.registration_required,
                ),
                ConfigureCallControlSource(
                    id=source_id, phase=VoicePhase.CALL_CONTROL,
                    call_control_id=call_control_id,
                    host_device_id=host.id or host.name, host_device_name=host.name,
                    host_model=host.model, site_id=site_ids[0], depends_on=[enable_id],
                    required_capability=VoiceCapabilityDimension.CALL_CONTROL_CONFIG,
                    source_address=source.ipv4, signaling_port=intent.policy.signaling_port,
                    source_configuration_action_id=source.id,
                ),
            ])
            for directory_index, phone_id in enumerate(hosted_phone_ids, 1):
                extension_id = _stable_id("extension", call_control_id, phone_id, extensions[phone_id])
                extension_action_by_phone[phone_id] = extension_id
                directory_index_by_phone[phone_id] = directory_index
                actions.append(CreateExtension(
                    id=extension_id, phase=VoicePhase.EXTENSIONS,
                    call_control_id=call_control_id,
                    host_device_id=host.id or host.name, host_device_name=host.name,
                    host_model=host.model, site_id=usable_by_id[phone_id][0].site_id,
                    depends_on=[source_id],
                    required_capability=VoiceCapabilityDimension.PHONE_EXTENSION_CONFIG,
                    extension=extensions[phone_id], directory_index=directory_index,
                ))

        for phone_id in sorted(usable_by_id, key=natural_identity_key):
            phone, access, addressing = usable_by_id[phone_id]
            call_control_id = call_control_for_site[phone.site_id]
            host = call_control_data[call_control_id][0]
            binding_id = _stable_id("binding", call_control_id, phone_id, extensions[phone_id])
            binding_action_by_phone[phone_id] = binding_id
            actions.append(BindPhoneToExtension(
                id=binding_id, phase=VoicePhase.PHONE_BINDINGS,
                call_control_id=call_control_id,
                host_device_id=host.id or host.name, host_device_name=host.name,
                host_model=host.model, site_id=phone.site_id,
                depends_on=[extension_action_by_phone[phone_id]],
                required_capability=VoiceCapabilityDimension.PHONE_EXTENSION_CONFIG,
                phone_id=phone_id, physical_device_name=phone.name,
                phone_model=phone.model,
                extension=extensions[phone_id], registration_required=intent.registration_required,
                directory_index=directory_index_by_phone[phone_id],
            ))
            assignments.append(PhoneAssignment(
                phone_id=phone_id, physical_device_name=phone.name, model=phone.model,
                site_id=phone.site_id, floor_id=phone.floor_id, zone_id=phone.zone_id,
                extension=extensions[phone_id], call_control_id=call_control_id,
                voice_vlan_id=int(
                    access.voice_vlan_id
                    if access.voice_vlan_id is not None else access.data_vlan_id
                ),
                voice_segment_id=addressing.segment_id,
                access_configuration_action_id=access.id,
                addressing_configuration_action_id=addressing.id,
                binding_action_id=binding_id,
                metadata=dict(sorted(phone.metadata.items())),
            ))

        for call_control_id in sorted(call_control_data, key=natural_identity_key):
            host, source, _ = call_control_data[call_control_id]
            hosted = [
                item for item in assignments if item.call_control_id == call_control_id
            ]
            option_ids: list[str] = []
            for segment_id in sorted({item.voice_segment_id for item in hosted}):
                pools = sorted(dhcp_by_segment.get(segment_id, []), key=lambda item: item.id)
                pool = next(
                    (item for item in pools if item.device_id == (host.id or host.name)),
                    None,
                )
                if pool is None:
                    continue
                option_id = _stable_id(
                    "voice-dhcp-option", call_control_id, pool.id, source.ipv4,
                )
                option_ids.append(option_id)
                foundations.append(VoiceFoundationRequirement(
                    id=_stable_id(
                        "foundation-voice-dhcp", call_control_id, pool.id,
                    ),
                    kind="voice_dhcp_pool", source_id=pool.id,
                    device_id=host.id or host.name, site_id=hosted[0].site_id,
                ))
                actions.append(ConfigureVoiceDhcpOption(
                    id=option_id, phase=VoicePhase.PHONE_BOOTSTRAP,
                    call_control_id=call_control_id,
                    host_device_id=host.id or host.name,
                    host_device_name=host.name, host_model=host.model,
                    site_id=hosted[0].site_id, depends_on=[source_action_by_control[call_control_id]],
                    required_capability=VoiceCapabilityDimension.VOICE_DHCP_OPTIONS,
                    pool_name=pool.pool_name, tftp_address=source.ipv4,
                    source_configuration_action_id=pool.id,
                ))
            binding_ids = sorted(
                (item.binding_action_id for item in hosted), key=natural_identity_key,
            )
            actions.append(GeneratePhoneConfigurationFiles(
                id=_stable_id("phone-files", call_control_id),
                phase=VoicePhase.PHONE_BOOTSTRAP,
                call_control_id=call_control_id,
                host_device_id=host.id or host.name,
                host_device_name=host.name, host_model=host.model,
                site_id=hosted[0].site_id,
                depends_on=sorted(binding_ids + option_ids, key=natural_identity_key),
                required_capability=VoiceCapabilityDimension.TFTP_PHONE_BOOTSTRAP,
            ))

        for site_id in sorted(phones_by_site, key=natural_identity_key):
            call_control_id = call_control_for_site[site_id]
            host = call_control_data[call_control_id][0]
            extension_range = ranges[site_id]
            prefix = commonprefix([str(extension_range.start), str(extension_range.end)])
            rule_id = f"dial-rule/{site_id}/local"
            action_id = _stable_id("dial-local", site_id, prefix)
            actions.append(ConfigureDialRule(
                id=action_id, phase=VoicePhase.DIAL_PLAN,
                call_control_id=call_control_id,
                host_device_id=host.id or host.name, host_device_name=host.name,
                host_model=host.model, site_id=site_id,
                depends_on=[source_action_by_control[call_control_id]],
                required_capability=VoiceCapabilityDimension.PHONE_EXTENSION_CONFIG,
                source_site_id=site_id, destination_site_id=site_id,
                destination_prefix=prefix, destination_call_control_id=call_control_id,
                local=True,
            ))
            dial_rules.append(DialRule(
                id=rule_id, source_site_id=site_id, destination_site_id=site_id,
                destination_prefix=prefix, destination_call_control_id=call_control_id,
                local=True, action_id=action_id,
            ))

        if intent.intersite_calling:
            for source_site in sorted(phones_by_site, key=natural_identity_key):
                for destination_site in sorted(phones_by_site, key=natural_identity_key):
                    if source_site == destination_site:
                        continue
                    source_control = call_control_for_site[source_site]
                    destination_control = call_control_for_site[destination_site]
                    host = call_control_data[source_control][0]
                    destination_range = ranges[destination_site]
                    prefix = commonprefix([
                        str(destination_range.start), str(destination_range.end),
                    ])
                    action_id = _stable_id("dial-intersite", source_site, destination_site, prefix)
                    actions.append(ConfigureDialRule(
                        id=action_id, phase=VoicePhase.DIAL_PLAN,
                        call_control_id=source_control,
                        host_device_id=host.id or host.name, host_device_name=host.name,
                        host_model=host.model, site_id=source_site,
                        depends_on=[source_action_by_control[source_control]],
                        required_capability=VoiceCapabilityDimension.INTERSITE_CALLING,
                        source_site_id=source_site, destination_site_id=destination_site,
                        destination_prefix=prefix,
                        destination_call_control_id=destination_control, local=False,
                    ))
                    dial_rules.append(DialRule(
                        id=f"dial-rule/{source_site}/{destination_site}",
                        source_site_id=source_site, destination_site_id=destination_site,
                        destination_prefix=prefix,
                        destination_call_control_id=destination_control,
                        local=False, action_id=action_id,
                    ))

        try:
            actions = order_dependency_actions(actions)
        except ConfigurationDependencyError as exc:
            issues.append(_error(
                ConfigurationIssueCode.DEPENDENCY_CYCLE, str(exc), ",".join(exc.action_ids),
            ))
            return self._result(None, topology, configuration, [], [], [], issues, service_plan)

        assignments.sort(key=lambda item: natural_identity_key(item.phone_id))
        dial_rules.sort(key=lambda item: (item.source_site_id, item.destination_site_id, item.id))
        expectations, verifications = self._expectations(
            assignments, ranges, binding_action_by_phone,
            intent.policy.compile_negative_call_control,
        )
        for action in actions:
            action.apply_dependencies = list(action.depends_on)
        for expectation in expectations:
            expectation.verification_prerequisites = [
                VerificationPrerequisite(
                    kind=PrerequisiteKind.PHONE_REGISTERED,
                    reference_id=identifier,
                )
                for identifier in sorted(set(expectation.depends_on))
            ]
        for verification in verifications:
            verification.verification_prerequisites = [
                VerificationPrerequisite(
                    kind=PrerequisiteKind.ACTION_APPLIED,
                    reference_id=verification.action_id,
                ),
                *[
                    VerificationPrerequisite(
                        kind=(
                            PrerequisiteKind.PHONE_REGISTERED
                            if verification.kind is not VoiceVerificationKind.PHONE_REGISTRATION
                            else PrerequisiteKind.VERIFICATION_VERIFIED
                        ),
                        reference_id=identifier,
                    )
                    for identifier in sorted(set(verification.depends_on))
                ],
            ]
        call_controls = self._call_controls(call_control_data, assignments, actions, intent)
        foundations = self._deduplicate_foundations(foundations)
        plan = VoicePlan(
            id=f"voice-plan/{intent.id}",
            source_topology_id=topology.id,
            source_topology_hash=topology.physical_identity_hash,
            source_topology_hash_schema=(
                "physical-topology-v2"
                if topology.physical_topology_hash else "legacy-full-v1"
            ),
            source_configuration_id=configuration.id,
            source_configuration_hash=configuration.semantic_hash,
            source_service_id=service_plan.id if intent.service_dependency_ids and service_plan else "",
            source_service_hash=(
                service_plan.semantic_hash if intent.service_dependency_ids and service_plan else ""
            ),
            service_dependency_ids=sorted(set(intent.service_dependency_ids)),
            call_controls=call_controls,
            phone_assignments=assignments,
            dial_rules=dial_rules,
            actions=actions,
            foundational_requirements=foundations,
            verification_expectations=verifications,
            call_expectations=expectations,
        )
        plan.semantic_hash = self._semantic_hash(plan)
        issues = self._deduplicate_issues(issues)
        return self._result(
            plan, topology, configuration, assignments, call_controls, actions,
            issues, service_plan,
        )

    @staticmethod
    def _validate_sources(intent, topology, configuration, service_plan, issues) -> None:
        if not topology.physical_identity_hash:
            issues.append(_error(
                ConfigurationIssueCode.SOURCE_TOPOLOGY_HASH_MISSING,
                "E7 requires the immutable semantic hash produced by E4.", topology.id,
            ))
        if not configuration.semantic_hash:
            issues.append(_error(
                ConfigurationIssueCode.SOURCE_CONFIGURATION_HASH_MISSING,
                "E7 requires the immutable semantic hash produced by E5.", configuration.id,
            ))
        if configuration.source_topology_hash != topology.physical_identity_hash:
            issues.append(_error(
                ConfigurationIssueCode.SOURCE_CONFIGURATION_TOPOLOGY_MISMATCH,
                "The E5 ConfigurationPlan belongs to a different E4 topology.", configuration.id,
            ))
        if not intent.service_dependency_ids:
            return
        if service_plan is None or not service_plan.semantic_hash:
            issues.append(_error(
                ConfigurationIssueCode.VOICE_SOURCE_SERVICE_MISMATCH,
                "Explicit E7 service dependencies require an immutable E6 ServicePlan.", intent.id,
            ))
            return
        if (
            service_plan.source_topology_hash != topology.physical_identity_hash
            or service_plan.source_configuration_hash != configuration.semantic_hash
        ):
            issues.append(_error(
                ConfigurationIssueCode.VOICE_SOURCE_SERVICE_MISMATCH,
                "The E6 ServicePlan does not belong to the supplied E4/E5 foundations.",
                service_plan.id,
            ))
        known = {item.id for item in service_plan.services}
        for service_id in sorted(set(intent.service_dependency_ids) - known):
            issues.append(_error(
                ConfigurationIssueCode.VOICE_SERVICE_DEPENDENCY_MISSING,
                f"Voice dependency {service_id!r} is absent from E6.", service_id,
            ))

    @staticmethod
    def _capability_issues(host, profile, issues) -> None:
        for dimension in (
            VoiceCapabilityDimension.CALL_CONTROL_CONFIG,
            VoiceCapabilityDimension.PHONE_EXTENSION_CONFIG,
        ):
            status = profile.status(dimension) if profile else VoiceCapabilityStatus.UNKNOWN
            if status is VoiceCapabilityStatus.UNSUPPORTED:
                issues.append(_error(
                    ConfigurationIssueCode.VOICE_CAPABILITY_UNSUPPORTED,
                    f"{host.model}:{dimension.value} is unsupported by evidence.",
                    host.id or host.name,
                ))
            elif status is not VoiceCapabilityStatus.SUPPORTED:
                issues.append(_warning(
                    ConfigurationIssueCode.VOICE_CAPABILITY_UNKNOWN,
                    f"{host.model}:{dimension.value} is {status.value}.",
                    host.id or host.name,
                ))

    @staticmethod
    def _expectations(assignments, ranges, bindings, include_negative):
        calls: list[CallExpectation] = []
        verification: list[VoiceVerificationExpectation] = []
        registration_ids = {}
        by_site: dict[str, list[PhoneAssignment]] = defaultdict(list)
        assigned = {item.extension for item in assignments}
        for assignment in assignments:
            by_site[assignment.site_id].append(assignment)
            expectation_id = _stable_id("verify-registration", assignment.phone_id)
            registration_ids[assignment.phone_id] = expectation_id
            verification.append(VoiceVerificationExpectation(
                id=expectation_id, kind=VoiceVerificationKind.PHONE_REGISTRATION,
                phone_id=assignment.phone_id, extension=assignment.extension,
                call_control_id=assignment.call_control_id,
                action_id=assignment.binding_action_id,
            ))
        for site_id in sorted(by_site, key=natural_identity_key):
            site_phones = sorted(by_site[site_id], key=lambda item: natural_identity_key(item.phone_id))
            if len(site_phones) >= 2:
                for source, target in ((site_phones[0], site_phones[1]),
                                       (site_phones[1], site_phones[0])):
                    call_id = _stable_id(
                        "call", source.phone_id, target.extension, target.phone_id,
                    )
                    dependencies = sorted([
                        registration_ids[source.phone_id], registration_ids[target.phone_id],
                    ])
                    calls.append(CallExpectation(
                        id=call_id, source_phone_id=source.phone_id,
                        source_extension=source.extension,
                        dialed_extension=target.extension,
                        expected_target_phone_id=target.phone_id,
                        expected_result=CallExpectationResult.ESTABLISHED,
                        site_id=site_id, depends_on=dependencies,
                    ))
                    verification.append(VoiceVerificationExpectation(
                        id=_stable_id("verify-call", call_id),
                        kind=VoiceVerificationKind.CALL_BEHAVIOR,
                        phone_id=source.phone_id, extension=source.extension,
                        call_control_id=source.call_control_id,
                        action_id=bindings[source.phone_id], call_expectation_id=call_id,
                        depends_on=dependencies,
                    ))
            if include_negative and site_phones:
                negative_number = ranges[site_id].end + 1
                while str(negative_number) in assigned:
                    negative_number += 1
                source = site_phones[0]
                call_id = _stable_id("call-negative", source.phone_id, negative_number)
                dependencies = [registration_ids[source.phone_id]]
                calls.append(CallExpectation(
                    id=call_id, source_phone_id=source.phone_id,
                    source_extension=source.extension,
                    dialed_extension=str(negative_number),
                    expected_result=CallExpectationResult.NOT_CONNECTED,
                    site_id=site_id, depends_on=dependencies,
                ))
                verification.append(VoiceVerificationExpectation(
                    id=_stable_id("verify-call-negative", call_id),
                    kind=VoiceVerificationKind.CALL_NEGATIVE_CONTROL,
                    phone_id=source.phone_id, extension=source.extension,
                    call_control_id=source.call_control_id,
                    action_id=bindings[source.phone_id], call_expectation_id=call_id,
                    depends_on=dependencies,
                ))
        calls.sort(key=lambda item: (
            natural_identity_key(item.source_phone_id), item.dialed_extension, item.id,
        ))
        verification.sort(key=lambda item: (item.kind.value, item.phone_id, item.id))
        return calls, verification

    @staticmethod
    def _call_controls(data, assignments, actions, intent):
        action_ids: dict[str, list[str]] = defaultdict(list)
        phones: dict[str, list[str]] = defaultdict(list)
        for action in actions:
            action_ids[action.call_control_id].append(action.id)
        for assignment in assignments:
            phones[assignment.call_control_id].append(assignment.phone_id)
        result = []
        for call_control_id in sorted(data, key=natural_identity_key):
            host, source, site_ids = data[call_control_id]
            result.append(CallControlInstance(
                id=call_control_id, site_ids=site_ids,
                host_device_id=host.id or host.name, host_device_name=host.name,
                host_model=host.model, source_address=source.ipv4,
                source_configuration_action_id=source.id,
                signaling_port=intent.policy.signaling_port,
                phone_ids=sorted(phones[call_control_id], key=natural_identity_key),
                action_ids=action_ids[call_control_id],
            ))
        return result

    @staticmethod
    def _deduplicate_foundations(foundations):
        unique = {item.id: item for item in foundations}
        return [unique[item] for item in sorted(unique)]

    @staticmethod
    def _deduplicate_issues(issues):
        unique = {
            (item.severity.value, item.code.value, item.subject, item.message): item
            for item in issues
        }
        return [unique[key] for key in sorted(unique)]

    @staticmethod
    def _semantic_hash(plan: VoicePlan) -> str:
        payload = plan.model_dump(mode="json")
        payload["semantic_hash"] = ""
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _result(plan, topology, configuration, assignments, controls, actions, issues, service_plan):
        issues = VoiceCompiler._deduplicate_issues(issues)
        summary = VoiceCompileSummary(
            voice_plan_id=plan.id if plan else "",
            semantic_hash=plan.semantic_hash if plan else "",
            source_topology_hash=topology.physical_identity_hash,
            source_topology_hash_schema=(
                "physical-topology-v2"
                if topology.physical_topology_hash else "legacy-full-v1"
            ),
            source_configuration_hash=configuration.semantic_hash,
            source_service_hash=(
                plan.source_service_hash if plan else
                service_plan.semantic_hash if service_plan else ""
            ),
            call_control_count=len(controls),
            phone_count=len(assignments),
            extension_count=len(assignments),
            dial_rule_count=len(plan.dial_rules) if plan else 0,
            action_count=len(actions),
            actions_by_type=voice_action_type_counts(actions),
            dependencies=sum(len(item.depends_on) for item in actions),
            verification_expectations=len(plan.verification_expectations) if plan else 0,
            warnings=sum(item.severity is ConfigurationIssueSeverity.WARNING for item in issues),
            errors=sum(item.severity is ConfigurationIssueSeverity.ERROR for item in issues),
        )
        return VoiceCompileResult(
            plan=plan, semantic_hash=plan.semantic_hash if plan else "",
            summary=summary, issues=issues,
        )
