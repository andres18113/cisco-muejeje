"""Minimal disposable LIVE qualification for the existing E7 call path."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from ...domain.enterprise.models.configuration import (
    AddressRange,
    ConfigureAccessPort,
    ConfigureDhcpPool,
    ConfigureSubinterface,
    ConfigureTrunk,
    ConfigurationPhase,
    CreateVlan,
)
from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    RuntimeActionMutation,
)
from ...domain.enterprise.models.physical_deployment import (
    PhysicalMutationResult,
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...domain.enterprise.models.voice_plan import (
    BindPhoneToExtension,
    CallControlInstance,
    CallExpectation,
    CallExpectationResult,
    ConfigureCallControlSource,
    ConfigureVoiceDhcpOption,
    CreateExtension,
    EnableCallControl,
    GeneratePhoneConfigurationFiles,
    PhoneAssignment,
    VoiceCapabilityDimension,
    VoiceCapabilityProfile,
    VoiceCapabilityStatus,
    VoicePhase,
    VoicePlan,
    VoiceVerificationExpectation,
    VoiceVerificationKind,
)
from ...domain.enterprise.models.voice_runtime import (
    PhoneExecutionMethod,
    VoiceApplicationResult,
)
from ...domain.enterprise.services.configuration_dependencies import (
    order_dependency_actions,
)
from ...domain.models.plans import DevicePlan, LinkPlan
from .apply_voice import VoiceApplicator, call_observation_matches_expected_result


QUALIFICATION_SCOPE = "call-observability-qualification"
ROUTER_MODEL = "2811"
SWITCH_MODEL = "3560-24PS"
PHONE_MODEL = "7960"
VOICE_VLAN_ID = 930
VOICE_NETWORK = "198.18.250.0"
VOICE_PREFIX = 24
VOICE_NETMASK = "255.255.255.0"
VOICE_GATEWAY = "198.18.250.1"
VOICE_POOL = "MCP_CALL_QUAL_VOICE"
ROUTER_INTERFACE = "FastEthernet0/0"
SWITCH_UPLINK = "GigabitEthernet0/1"


class CallObservabilityQualificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNOBSERVABLE = "UNOBSERVABLE"
    BLOCKED = "BLOCKED"


class QualificationPhysicalRuntime(Protocol):
    def observe_workspace(self) -> PhysicalWorkspaceObservation: ...
    def ensure_device(self, device: DevicePlan) -> PhysicalMutationResult: ...
    def ensure_link(self, link: LinkPlan) -> PhysicalMutationResult: ...
    def remove_device(self, device: DevicePlan) -> PhysicalMutationResult: ...


class QualificationConfigurationRuntime(Protocol):
    def apply_actions(self, actions) -> list[RuntimeActionMutation]: ...


class QualificationModeRuntime(Protocol):
    def read_simulation_state(self): ...
    def set_simulation_mode(self, on: bool): ...


@dataclass(frozen=True)
class CallObservabilityQualificationResult:
    status: CallObservabilityQualificationStatus
    voice_plan: VoicePlan
    voice_result: VoiceApplicationResult | None
    baseline: PhysicalWorkspaceObservation | None
    cleanup_first: PhysicalWorkspaceObservation | None
    cleanup_second: PhysicalWorkspaceObservation | None
    created_devices: tuple[str, ...]
    created_links: tuple[str, ...]
    removed_devices: tuple[str, ...]
    initial_realtime: bool | None
    final_realtime: bool | None
    cleanup_verified: bool
    errors: tuple[str, ...]


class CallObservabilityQualification:
    """Build four governed objects and exercise calls only through VoiceApplicator."""

    def __init__(
        self,
        *,
        physical: QualificationPhysicalRuntime,
        configuration: QualificationConfigurationRuntime,
        voice: VoiceApplicator,
        mode: QualificationModeRuntime,
        token: str,
    ) -> None:
        if not token or token != token.strip():
            raise ValueError("Qualification token must be one exact nonblank value.")
        self._physical = physical
        self._configuration = configuration
        self._voice = voice
        self._mode = mode
        self._token = token

    def qualify(self) -> CallObservabilityQualificationResult:
        devices, links = self._fixture()
        voice_plan = self._voice_plan(devices)
        baseline = cleanup_first = cleanup_second = None
        voice_result = None
        initial_realtime = final_realtime = None
        created: list[DevicePlan] = []
        created_links: list[str] = []
        removed: list[str] = []
        errors: list[str] = []
        cleanup_mutations_ok = True
        eligible = True
        try:
            baseline = self._physical.observe_workspace()
            if not baseline.safe_for_disposable_mutation:
                errors.append(
                    "The call qualification requires an observed empty semantic baseline."
                )
                eligible = False
            if eligible:
                initial_mode = self._mode.read_simulation_state()
                initial_realtime = bool(
                    getattr(initial_mode, "observed", False)
                    and getattr(initial_mode, "simulation_mode", None) is False
                )
                if not initial_realtime:
                    errors.append("Realtime was not observed before fixture mutation.")
                    eligible = False
            if eligible:
                for device in devices:
                    mutation = self._physical.ensure_device(device)
                    if mutation.applied is not True:
                        errors.append(f"Device creation was not accepted: {device.name}.")
                        break
                    created.append(device)
            if eligible and len(created) == len(devices):
                for link in links:
                    mutation = self._physical.ensure_link(link)
                    if mutation.applied is not True:
                        errors.append(f"Link creation was not accepted: {link.id}.")
                        break
                    created_links.append(link.id)
            if not errors:
                configuration_actions = self._configuration_actions()
                configured = self._configuration.apply_actions(configuration_actions)
                if (
                    len(configured) != len(configuration_actions)
                    or any(item.applied is not True for item in configured)
                ):
                    errors.append(
                        "The typed minimum configuration batch was not fully accepted."
                    )
            if not errors:
                voice_result = self._voice.apply(
                    voice_plan,
                    actual_source_topology_hash=voice_plan.source_topology_hash,
                    actual_source_configuration_hash=(
                        voice_plan.source_configuration_hash
                    ),
                    foundational_statuses={},
                    capabilities=self._voice_capabilities(),
                    complete_voice_signal=self._complete_voice_signal,
                )
        except Exception as exc:
            errors.append(f"qualification_failed: {type(exc).__name__}: {exc}")
        finally:
            try:
                restored = self._mode.set_simulation_mode(False)
                final_mode = self._mode.read_simulation_state()
                final_realtime = bool(
                    getattr(restored, "observed", False)
                    and getattr(restored, "after", None) is False
                    and getattr(final_mode, "observed", False)
                    and getattr(final_mode, "simulation_mode", None) is False
                )
                if not final_realtime:
                    errors.append("Realtime restoration was not verified.")
            except Exception as exc:
                errors.append(f"realtime_restore_failed: {type(exc).__name__}: {exc}")
            for device in reversed(created):
                try:
                    mutation = self._physical.remove_device(device)
                    cleanup_mutations_ok = cleanup_mutations_ok and mutation.applied is True
                    if mutation.applied is True:
                        removed.append(device.name)
                    else:
                        errors.append(
                            f"Owned device removal was not accepted: {device.name}."
                        )
                except Exception as exc:
                    cleanup_mutations_ok = False
                    errors.append(
                        f"cleanup_failed:{device.name}: {type(exc).__name__}: {exc}"
                    )
            try:
                cleanup_first = self._physical.observe_workspace()
                cleanup_second = self._physical.observe_workspace()
            except Exception as exc:
                errors.append(f"cleanup_observation_failed: {type(exc).__name__}: {exc}")

        cleanup_verified = bool(
            baseline is not None
            and cleanup_first is not None
            and cleanup_second is not None
            and cleanup_mutations_ok
            and cleanup_first.safe_for_disposable_mutation
            and cleanup_second.safe_for_disposable_mutation
            and physical_workspace_restoration_matches(baseline, cleanup_first)
            and physical_workspace_restoration_matches(baseline, cleanup_second)
            and len(removed) == len(created)
        )
        if not cleanup_verified:
            errors.append(
                "Owned cleanup did not produce two exact empty workspace observations."
            )
        return self._result(
            voice_plan, voice_result, baseline, cleanup_first, cleanup_second,
            created, created_links, removed, initial_realtime, final_realtime,
            cleanup_verified, errors,
        )

    def _result(
        self,
        voice_plan,
        voice_result,
        baseline,
        cleanup_first,
        cleanup_second,
        created,
        created_links,
        removed,
        initial_realtime,
        final_realtime,
        cleanup_verified,
        errors,
    ) -> CallObservabilityQualificationResult:
        calls = tuple(voice_result.calls) if voice_result is not None else ()
        call_by_id = {item.call_expectation_id: item for item in calls}
        expected = tuple(voice_plan.call_expectations)
        calls_verified = bool(
            len(calls) == len(expected)
            and len(call_by_id) == len(expected)
            and len({item.call_attempt_id for item in calls}) == len(expected)
            and all(
                (
                    observation := call_by_id.get(expectation.id)
                ) is not None
                and observation.status is ActionExecutionStatus.VERIFIED
                and observation.source_phone_id == expectation.source_phone_id
                and observation.destination_phone_id
                == expectation.expected_target_phone_id
                and observation.dialed_extension == expectation.dialed_extension
                and observation.fresh_evidence is True
                and observation.execution_method
                is PhoneExecutionMethod.PACKET_TRACER_NATIVE_UI
                and observation.teardown_verified is True
                and bool(observation.evidence_method)
                and bool(observation.evidence_artifact_path)
                and len(observation.evidence_sha256) == 64
                and call_observation_matches_expected_result(
                    expectation.expected_result,
                    observation,
                )
                for expectation in expected
            )
        )
        verified = bool(
            calls_verified
            and voice_result is not None
            and voice_result.status is ActionExecutionStatus.VERIFIED
            and initial_realtime is True
            and final_realtime is True
            and cleanup_verified
            and not errors
        )
        if verified:
            status = CallObservabilityQualificationStatus.VERIFIED
        elif any(
            item.status is ActionExecutionStatus.UNOBSERVABLE for item in calls
        ):
            status = CallObservabilityQualificationStatus.UNOBSERVABLE
        else:
            status = CallObservabilityQualificationStatus.BLOCKED
        return CallObservabilityQualificationResult(
            status=status,
            voice_plan=voice_plan,
            voice_result=voice_result,
            baseline=baseline,
            cleanup_first=cleanup_first,
            cleanup_second=cleanup_second,
            created_devices=tuple(item.name for item in created),
            created_links=tuple(created_links),
            removed_devices=tuple(removed),
            initial_realtime=initial_realtime,
            final_realtime=final_realtime,
            cleanup_verified=cleanup_verified,
            errors=tuple(errors),
        )

    def _name(self, suffix: str) -> str:
        return f"__MCP_CALL_QUAL_{self._token}_{suffix}".upper()

    def _fixture(self) -> tuple[tuple[DevicePlan, ...], tuple[LinkPlan, ...]]:
        router = DevicePlan(
            id="callqual/router", name=self._name("R"), model=ROUTER_MODEL,
            category="router", x=9000, y=9000,
        )
        switch = DevicePlan(
            id="callqual/switch", name=self._name("SW"), model=SWITCH_MODEL,
            category="switch", x=9000, y=9400,
        )
        first = DevicePlan(
            id="callqual/phone/1", name=self._name("P1"), model=PHONE_MODEL,
            category="ip_phone", requires_poe=True, x=8850, y=9800,
        )
        second = DevicePlan(
            id="callqual/phone/2", name=self._name("P2"), model=PHONE_MODEL,
            category="ip_phone", requires_poe=True, x=9150, y=9800,
        )
        links = (
            LinkPlan(
                id="callqual/link/uplink",
                device_a=router.name,
                port_a=ROUTER_INTERFACE,
                device_b=switch.name,
                port_b=SWITCH_UPLINK,
                cable="straight",
            ),
            LinkPlan(
                id="callqual/link/phone/1",
                device_a=switch.name,
                port_a="FastEthernet0/1",
                device_b=first.name,
                port_b="Switch",
                cable="straight",
            ),
            LinkPlan(
                id="callqual/link/phone/2",
                device_a=switch.name,
                port_a="FastEthernet0/2",
                device_b=second.name,
                port_b="Switch",
                cable="straight",
            ),
        )
        return (router, switch, first, second), links

    def _configuration_actions(self):
        switch = self._name("SW")
        router = self._name("R")
        common_switch = {
            "device_id": "callqual/switch",
            "device_name": switch,
            "site_id": QUALIFICATION_SCOPE,
        }
        common_router = {
            "device_id": "callqual/router",
            "device_name": router,
            "site_id": QUALIFICATION_SCOPE,
        }
        return [
            CreateVlan(
                id="callqual/config/vlan",
                phase=ConfigurationPhase.L2_DEFINITIONS,
                vlan_id=VOICE_VLAN_ID,
                name="MCP_CALL_QUAL_VOICE",
                **common_switch,
            ),
            ConfigureTrunk(
                id="callqual/config/trunk",
                phase=ConfigurationPhase.L2_INTERFACES,
                interface=SWITCH_UPLINK,
                allowed_vlans=[VOICE_VLAN_ID],
                native_vlan_id=1,
                **common_switch,
            ),
            ConfigureAccessPort(
                id="callqual/config/access/1",
                phase=ConfigurationPhase.L2_INTERFACES,
                interface="FastEthernet0/1",
                data_vlan_id=VOICE_VLAN_ID,
                voice_vlan_id=None,
                endpoint_ids=["callqual/phone/1"],
                **common_switch,
            ),
            ConfigureAccessPort(
                id="callqual/config/access/2",
                phase=ConfigurationPhase.L2_INTERFACES,
                interface="FastEthernet0/2",
                data_vlan_id=VOICE_VLAN_ID,
                voice_vlan_id=None,
                endpoint_ids=["callqual/phone/2"],
                **common_switch,
            ),
            ConfigureSubinterface(
                id="callqual/config/subinterface",
                phase=ConfigurationPhase.L3_INTERFACES,
                parent_interface=ROUTER_INTERFACE,
                vlan_id=VOICE_VLAN_ID,
                ipv4=VOICE_GATEWAY,
                prefix=VOICE_PREFIX,
                netmask=VOICE_NETMASK,
                segment_id="callqual/voice",
                **common_router,
            ),
            ConfigureDhcpPool(
                id="callqual/config/dhcp",
                phase=ConfigurationPhase.SERVICES,
                pool_name=VOICE_POOL,
                segment_id="callqual/voice",
                network=VOICE_NETWORK,
                prefix=VOICE_PREFIX,
                netmask=VOICE_NETMASK,
                gateway=VOICE_GATEWAY,
                excluded_ranges=[AddressRange(start=VOICE_GATEWAY, end="198.18.250.9")],
                lease_start="198.18.250.10",
                lease_end="198.18.250.20",
                **common_router,
            ),
        ]

    def _complete_voice_signal(self) -> dict[str, ActionExecutionStatus]:
        common = {
            "phase": ConfigurationPhase.L2_INTERFACES,
            "device_id": "callqual/switch",
            "device_name": self._name("SW"),
            "site_id": QUALIFICATION_SCOPE,
            "data_vlan_id": VOICE_VLAN_ID,
            "voice_vlan_id": VOICE_VLAN_ID,
        }
        actions = [
            ConfigureAccessPort(
                id="callqual/config/access/voice/1",
                interface="FastEthernet0/1",
                endpoint_ids=["callqual/phone/1"],
                **common,
            ),
            ConfigureAccessPort(
                id="callqual/config/access/voice/2",
                interface="FastEthernet0/2",
                endpoint_ids=["callqual/phone/2"],
                **common,
            ),
        ]
        mutations = self._configuration.apply_actions(actions)
        if (
            len(mutations) != len(actions)
            or any(item.applied is not True for item in mutations)
        ):
            raise RuntimeError(
                "The post-bootstrap Voice signal batch was not fully accepted."
            )
        return {}

    def _voice_plan(self, devices: tuple[DevicePlan, ...]) -> VoicePlan:
        router, _switch, first, second = devices
        control_id = "callqual/call-control"
        common = {
            "call_control_id": control_id,
            "host_device_id": router.id,
            "host_device_name": router.name,
            "host_model": router.model,
            "site_id": QUALIFICATION_SCOPE,
        }
        actions = [
            ConfigureVoiceDhcpOption(
                id="callqual/voice/option150",
                phase=VoicePhase.CALL_CONTROL,
                required_capability=VoiceCapabilityDimension.VOICE_DHCP_OPTIONS,
                pool_name=VOICE_POOL,
                tftp_address=VOICE_GATEWAY,
                source_configuration_action_id="callqual/config/subinterface",
                **common,
            ),
            ConfigureCallControlSource(
                id="callqual/voice/source",
                phase=VoicePhase.CALL_CONTROL,
                required_capability=VoiceCapabilityDimension.CALL_CONTROL_CONFIG,
                source_address=VOICE_GATEWAY,
                signaling_port=2000,
                source_configuration_action_id="callqual/config/subinterface",
                **common,
            ),
            EnableCallControl(
                id="callqual/voice/enable",
                phase=VoicePhase.CALL_CONTROL,
                required_capability=VoiceCapabilityDimension.CALL_CONTROL_CONFIG,
                max_phones=2,
                max_extensions=2,
                **common,
            ),
        ]
        phones = ((first, "3001", 1), (second, "3002", 2))
        for _phone, extension, index in phones:
            actions.append(CreateExtension(
                id=f"callqual/voice/extension/{index}",
                phase=VoicePhase.EXTENSIONS,
                required_capability=VoiceCapabilityDimension.PHONE_EXTENSION_CONFIG,
                extension=extension,
                directory_index=index,
                **common,
            ))
        for phone, extension, index in phones:
            actions.append(BindPhoneToExtension(
                id=f"callqual/voice/binding/{index}",
                phase=VoicePhase.PHONE_BINDINGS,
                required_capability=VoiceCapabilityDimension.PHONE_EXTENSION_CONFIG,
                phone_id=phone.id,
                physical_device_name=phone.name,
                phone_model=phone.model,
                extension=extension,
                directory_index=index,
                **common,
            ))
        actions.append(GeneratePhoneConfigurationFiles(
            id="callqual/voice/cnf",
            phase=VoicePhase.PHONE_BOOTSTRAP,
            required_capability=VoiceCapabilityDimension.TFTP_PHONE_BOOTSTRAP,
            **common,
        ))
        actions = order_dependency_actions(actions)
        assignments = [
            PhoneAssignment(
                phone_id=phone.id,
                physical_device_name=phone.name,
                model=phone.model,
                site_id=QUALIFICATION_SCOPE,
                extension=extension,
                call_control_id=control_id,
                voice_vlan_id=VOICE_VLAN_ID,
                voice_segment_id="callqual/voice",
                access_configuration_action_id=f"callqual/config/access/{index}",
                addressing_configuration_action_id="",
                binding_action_id=f"callqual/voice/binding/{index}",
                addressing_interface=f"Vlan{VOICE_VLAN_ID}",
                voice_network=VOICE_NETWORK,
                voice_prefix=VOICE_PREFIX,
            )
            for phone, extension, index in phones
        ]
        registrations = [
            VoiceVerificationExpectation(
                id=f"callqual/voice/registration/{index}",
                kind=VoiceVerificationKind.PHONE_REGISTRATION,
                phone_id=phone.id,
                extension=extension,
                call_control_id=control_id,
                action_id=f"callqual/voice/binding/{index}",
                endpoint_device_name=phone.name,
                endpoint_interface=f"Vlan{VOICE_VLAN_ID}",
            )
            for phone, extension, index in phones
        ]
        calls = [
            CallExpectation(
                id="callqual/call/established",
                source_phone_id=first.id,
                source_extension="3001",
                dialed_extension="3002",
                expected_target_phone_id=second.id,
                expected_result=CallExpectationResult.ESTABLISHED,
                site_id=QUALIFICATION_SCOPE,
                depends_on=[item.id for item in registrations],
            ),
            CallExpectation(
                id="callqual/call/not-connected",
                source_phone_id=first.id,
                source_extension="3001",
                dialed_extension="3999",
                expected_result=CallExpectationResult.NOT_CONNECTED,
                site_id=QUALIFICATION_SCOPE,
                depends_on=[registrations[0].id],
            ),
        ]
        return VoicePlan(
            id="callqual/voice-plan",
            source_topology_id="callqual/topology",
            source_topology_hash="callqual/topology/hash",
            source_configuration_id="callqual/configuration",
            source_configuration_hash="callqual/configuration/hash",
            semantic_hash="callqual/voice/hash",
            call_controls=[CallControlInstance(
                id=control_id,
                site_ids=[QUALIFICATION_SCOPE],
                host_device_id=router.id,
                host_device_name=router.name,
                host_model=router.model,
                source_address=VOICE_GATEWAY,
                source_configuration_action_id="callqual/config/subinterface",
                signaling_port=2000,
                phone_ids=[first.id, second.id],
                action_ids=[item.id for item in actions],
            )],
            phone_assignments=assignments,
            actions=actions,
            verification_expectations=registrations,
            call_expectations=calls,
        )

    @staticmethod
    def _voice_capabilities() -> dict[str, VoiceCapabilityProfile]:
        dimensions = {
            dimension: VoiceCapabilityStatus.SUPPORTED
            for dimension in (
                VoiceCapabilityDimension.CALL_CONTROL_CONFIG,
                VoiceCapabilityDimension.PHONE_EXTENSION_CONFIG,
                VoiceCapabilityDimension.PHONE_REGISTRATION,
                VoiceCapabilityDimension.CALL_INITIATION,
                VoiceCapabilityDimension.CALL_STATE_READBACK,
                VoiceCapabilityDimension.TFTP_PHONE_BOOTSTRAP,
                VoiceCapabilityDimension.VOICE_DHCP_OPTIONS,
            )
        }
        return {ROUTER_MODEL: VoiceCapabilityProfile(
            model=ROUTER_MODEL,
            dimensions=dimensions,
            evidence_source="explicit_call_observability_qualification_probe",
            packet_tracer_version="9.0.1.0858",
            call_observability_phone_models=[PHONE_MODEL],
        )}
