"""Contratos backend-neutral de E7 para voz y telefonía empresarial."""

from __future__ import annotations

from collections import Counter
from enum import Enum, IntEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .configuration import ConfigurationIssue
from .execution import OperationSemantics
from .evidence import CapabilityReadiness
from .verification import VerificationPrerequisite


class VoiceCapabilityStatus(str, Enum):
    SUPPORTED = "supported"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    UNOBSERVABLE = "unobservable"
    SKIPPED = "skipped"


class VoiceCapabilityDimension(str, Enum):
    CALL_CONTROL_CONFIG = "call_control_config"
    PHONE_EXTENSION_CONFIG = "phone_extension_config"
    PHONE_REGISTRATION = "phone_registration"
    CALL_INITIATION = "call_initiation"
    CALL_STATE_READBACK = "call_state_readback"
    TFTP_PHONE_BOOTSTRAP = "tftp_phone_bootstrap"
    VOICE_DHCP_OPTIONS = "voice_dhcp_options"
    VOICE_NTP = "voice_ntp"
    INTERSITE_CALLING = "intersite_calling"


class VoiceCapabilityProfile(BaseModel):
    model: str
    dimensions: dict[VoiceCapabilityDimension, VoiceCapabilityStatus] = Field(
        default_factory=dict,
    )
    evidence_source: str = ""
    packet_tracer_version: str | None = None
    capability_readiness: dict[str, CapabilityReadiness] = Field(default_factory=dict)

    def status(self, dimension: VoiceCapabilityDimension) -> VoiceCapabilityStatus:
        return self.dimensions.get(dimension, VoiceCapabilityStatus.UNKNOWN)


class ExtensionRange(BaseModel):
    start: int
    end: int
    reserved: list[int] = Field(default_factory=list)


class VoicePolicy(BaseModel):
    default_extension_range: ExtensionRange = Field(
        default_factory=lambda: ExtensionRange(start=3001, end=3999),
    )
    signaling_port: int = 2000
    compile_negative_call_control: bool = True


class VoiceIntent(BaseModel):
    id: str
    call_control_device_ids: dict[str, str] = Field(default_factory=dict)
    central_call_control_device_id: str = ""
    phone_device_ids: list[str] = Field(default_factory=list)
    extension_ranges: dict[str, ExtensionRange] = Field(default_factory=dict)
    explicit_extensions: dict[str, str] = Field(default_factory=dict)
    service_dependency_ids: list[str] = Field(default_factory=list)
    registration_required: bool = True
    intersite_calling: bool = False
    policy: VoicePolicy = Field(default_factory=VoicePolicy)


class VoicePhase(IntEnum):
    CALL_CONTROL = 20
    EXTENSIONS = 30
    PHONE_BINDINGS = 40
    PHONE_BOOTSTRAP = 45
    DIAL_PLAN = 50


class VoiceActionType(str, Enum):
    ENABLE_CALL_CONTROL = "enable_call_control"
    CONFIGURE_CALL_CONTROL_SOURCE = "configure_call_control_source"
    CREATE_EXTENSION = "create_extension"
    BIND_PHONE_TO_EXTENSION = "bind_phone_to_extension"
    CONFIGURE_VOICE_DHCP_OPTION = "configure_voice_dhcp_option"
    GENERATE_PHONE_CONFIGURATION_FILES = "generate_phone_configuration_files"
    CONFIGURE_DIAL_RULE = "configure_dial_rule"


class BaseVoiceAction(BaseModel):
    id: str
    action_type: VoiceActionType
    phase: VoicePhase
    call_control_id: str
    host_device_id: str
    host_device_name: str
    host_model: str
    site_id: str
    depends_on: list[str] = Field(default_factory=list)
    apply_dependencies: list[str] = Field(default_factory=list)
    required_capability: VoiceCapabilityDimension
    critical: bool = True
    operation: OperationSemantics = OperationSemantics.SET_VALUE
    compensation_available: bool = False
    inverse_action_id: str = ""


class EnableCallControl(BaseVoiceAction):
    action_type: Literal[
        VoiceActionType.ENABLE_CALL_CONTROL
    ] = VoiceActionType.ENABLE_CALL_CONTROL
    max_phones: int
    max_extensions: int
    registration_required: bool = True


class ConfigureCallControlSource(BaseVoiceAction):
    action_type: Literal[
        VoiceActionType.CONFIGURE_CALL_CONTROL_SOURCE
    ] = VoiceActionType.CONFIGURE_CALL_CONTROL_SOURCE
    source_address: str
    signaling_port: int
    source_configuration_action_id: str


class CreateExtension(BaseVoiceAction):
    action_type: Literal[
        VoiceActionType.CREATE_EXTENSION
    ] = VoiceActionType.CREATE_EXTENSION
    operation: Literal[
        OperationSemantics.ENSURE_PRESENT
    ] = OperationSemantics.ENSURE_PRESENT
    extension: str
    directory_index: int


class BindPhoneToExtension(BaseVoiceAction):
    action_type: Literal[
        VoiceActionType.BIND_PHONE_TO_EXTENSION
    ] = VoiceActionType.BIND_PHONE_TO_EXTENSION
    phone_id: str
    physical_device_name: str
    phone_model: str
    extension: str
    directory_index: int
    registration_required: bool = True


class ConfigureVoiceDhcpOption(BaseVoiceAction):
    action_type: Literal[
        VoiceActionType.CONFIGURE_VOICE_DHCP_OPTION
    ] = VoiceActionType.CONFIGURE_VOICE_DHCP_OPTION
    pool_name: str
    tftp_address: str
    source_configuration_action_id: str


class GeneratePhoneConfigurationFiles(BaseVoiceAction):
    action_type: Literal[
        VoiceActionType.GENERATE_PHONE_CONFIGURATION_FILES
    ] = VoiceActionType.GENERATE_PHONE_CONFIGURATION_FILES
    operation: Literal[OperationSemantics.REPLACE] = OperationSemantics.REPLACE


class ConfigureDialRule(BaseVoiceAction):
    action_type: Literal[
        VoiceActionType.CONFIGURE_DIAL_RULE
    ] = VoiceActionType.CONFIGURE_DIAL_RULE
    operation: Literal[
        OperationSemantics.ENSURE_PRESENT
    ] = OperationSemantics.ENSURE_PRESENT
    source_site_id: str
    destination_site_id: str
    destination_prefix: str
    destination_call_control_id: str
    local: bool = True


VoiceAction = Annotated[
    EnableCallControl
    | ConfigureCallControlSource
    | CreateExtension
    | BindPhoneToExtension
    | ConfigureVoiceDhcpOption
    | GeneratePhoneConfigurationFiles
    | ConfigureDialRule,
    Field(discriminator="action_type"),
]


class CallControlInstance(BaseModel):
    id: str
    site_ids: list[str]
    host_device_id: str
    host_device_name: str
    host_model: str
    source_address: str
    source_configuration_action_id: str
    signaling_port: int
    phone_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)


class PhoneAssignment(BaseModel):
    phone_id: str
    physical_device_name: str
    model: str
    site_id: str
    floor_id: str = ""
    zone_id: str = ""
    extension: str
    call_control_id: str
    voice_vlan_id: int
    voice_segment_id: str
    access_configuration_action_id: str
    addressing_configuration_action_id: str
    binding_action_id: str
    metadata: dict[str, str] = Field(default_factory=dict)


class DialRule(BaseModel):
    id: str
    source_site_id: str
    destination_site_id: str
    destination_prefix: str
    destination_call_control_id: str
    local: bool = True
    action_id: str


class CallExpectationResult(str, Enum):
    ESTABLISHED = "established"
    NOT_CONNECTED = "not_connected"


class CallExpectation(BaseModel):
    id: str
    source_phone_id: str
    source_extension: str
    dialed_extension: str
    expected_target_phone_id: str = ""
    expected_result: CallExpectationResult
    site_id: str
    depends_on: list[str] = Field(default_factory=list)
    verification_prerequisites: list[VerificationPrerequisite] = Field(default_factory=list)
    operation: Literal[
        OperationSemantics.EXECUTE_ONCE
    ] = OperationSemantics.EXECUTE_ONCE


class VoiceVerificationKind(str, Enum):
    PHONE_REGISTRATION = "phone_registration"
    CALL_BEHAVIOR = "call_behavior"
    CALL_NEGATIVE_CONTROL = "call_negative_control"


class VoiceVerificationExpectation(BaseModel):
    id: str
    kind: VoiceVerificationKind
    phone_id: str
    extension: str
    call_control_id: str
    action_id: str
    call_expectation_id: str = ""
    depends_on: list[str] = Field(default_factory=list)
    verification_prerequisites: list[VerificationPrerequisite] = Field(default_factory=list)


class VoiceFoundationRequirement(BaseModel):
    id: str
    kind: Literal[
        "voice_vlan", "phone_addressing", "call_control_addressing",
        "voice_dhcp_pool", "service"
    ]
    source_id: str
    device_id: str = ""
    site_id: str = ""


class VoicePlan(BaseModel):
    id: str
    source_topology_id: str
    source_topology_hash: str
    source_topology_hash_schema: str = "legacy-full-v1"
    source_configuration_id: str
    source_configuration_hash: str
    source_service_id: str = ""
    source_service_hash: str = ""
    service_dependency_ids: list[str] = Field(default_factory=list)
    semantic_hash: str = ""
    call_controls: list[CallControlInstance] = Field(default_factory=list)
    phone_assignments: list[PhoneAssignment] = Field(default_factory=list)
    dial_rules: list[DialRule] = Field(default_factory=list)
    actions: list[VoiceAction] = Field(default_factory=list)
    foundational_requirements: list[VoiceFoundationRequirement] = Field(default_factory=list)
    verification_expectations: list[VoiceVerificationExpectation] = Field(default_factory=list)
    call_expectations: list[CallExpectation] = Field(default_factory=list)

    def actions_of_type(self, action_type: VoiceActionType) -> list[VoiceAction]:
        return [item for item in self.actions if item.action_type is action_type]

    def assignment_for_phone(self, phone_id: str) -> PhoneAssignment | None:
        return next((item for item in self.phone_assignments if item.phone_id == phone_id), None)

    def assignment_for_extension(self, extension: str) -> PhoneAssignment | None:
        return next((item for item in self.phone_assignments if item.extension == extension), None)


class VoiceCompileSummary(BaseModel):
    voice_plan_id: str = ""
    semantic_hash: str = ""
    source_topology_hash: str = ""
    source_topology_hash_schema: str = ""
    source_configuration_hash: str = ""
    source_service_hash: str = ""
    call_control_count: int = 0
    phone_count: int = 0
    extension_count: int = 0
    dial_rule_count: int = 0
    action_count: int = 0
    actions_by_type: dict[str, int] = Field(default_factory=dict)
    dependencies: int = 0
    verification_expectations: int = 0
    warnings: int = 0
    errors: int = 0


class VoiceCompileResult(BaseModel):
    plan: VoicePlan | None = None
    semantic_hash: str = ""
    summary: VoiceCompileSummary = Field(default_factory=VoiceCompileSummary)
    issues: list[ConfigurationIssue] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        from .configuration import ConfigurationIssueSeverity

        return self.plan is not None and not any(
            item.severity is ConfigurationIssueSeverity.ERROR for item in self.issues
        )

    def compact_summary(self) -> dict[str, object]:
        return {
            **self.summary.model_dump(mode="json"),
            "issues": [item.model_dump(mode="json") for item in self.issues],
        }


def voice_action_type_counts(actions: list[VoiceAction]) -> dict[str, int]:
    counts = Counter(item.action_type.value for item in actions)
    return dict(sorted(counts.items()))
