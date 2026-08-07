"""Contratos backend-neutral de E8 para seguridad empresarial."""

from __future__ import annotations

from collections import Counter
from enum import Enum, IntEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .configuration import ConfigurationIssue
from .execution import OperationSemantics
from .evidence import CapabilityReadiness
from .verification import VerificationPrerequisite


class SecurityDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class SecurityCapabilityStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    UNOBSERVABLE = "unobservable"
    SKIPPED = "skipped"


class SecurityCapabilityDimension(str, Enum):
    ACL_CONFIG = "acl_config"
    ACL_READBACK = "acl_readback"
    ACL_BEHAVIORAL = "acl_behavioral"
    NAT_CONFIG = "nat_config"
    NAT_PAT_CONFIG = "nat_pat_config"
    NAT_STATIC_CONFIG = "nat_static_config"
    NAT_DYNAMIC_CONFIG = "nat_dynamic_config"
    NAT_TRANSLATION_READBACK = "nat_translation_readback"
    NAT_BEHAVIORAL = "nat_behavioral"
    PORT_SECURITY_CONFIG = "port_security_config"
    PORT_SECURITY_READBACK = "port_security_readback"
    PORT_SECURITY_BEHAVIORAL = "port_security_behavioral"
    DHCP_SNOOPING_CONFIG = "dhcp_snooping_config"
    DHCP_SNOOPING_READBACK = "dhcp_snooping_readback"
    DHCP_SNOOPING_BEHAVIORAL = "dhcp_snooping_behavioral"
    DAI_CONFIG = "dai_config"
    DAI_READBACK = "dai_readback"
    DAI_BEHAVIORAL = "dai_behavioral"
    HARDENING_CONFIG = "hardening_config"
    HARDENING_READBACK = "hardening_readback"


class SecurityCapabilityProfile(BaseModel):
    model: str
    dimensions: dict[SecurityCapabilityDimension, SecurityCapabilityStatus] = Field(
        default_factory=dict,
    )
    evidence_source: str = ""
    packet_tracer_version: str | None = None
    capability_readiness: dict[str, CapabilityReadiness] = Field(default_factory=dict)

    def status(self, dimension: SecurityCapabilityDimension) -> SecurityCapabilityStatus:
        return self.dimensions.get(dimension, SecurityCapabilityStatus.UNKNOWN)

    @classmethod
    def supported(cls, model: str) -> "SecurityCapabilityProfile":
        return cls(
            model=model,
            dimensions={
                dimension: SecurityCapabilityStatus.SUPPORTED
                for dimension in SecurityCapabilityDimension
            },
            evidence_source="test fixture",
        )


class NatMode(str, Enum):
    PAT = "pat"
    STATIC = "static"
    DYNAMIC = "dynamic"


class SecurityPolicyIntent(BaseModel):
    id: str
    source_segment_id: str
    destination_segment_id: str = ""
    destination_service_id: str = ""
    destination_call_control_id: str = ""
    protocol: str = "ip"
    source_ports: list[int] = Field(default_factory=list)
    destination_ports: list[int] = Field(default_factory=list)
    decision: SecurityDecision
    priority: int = 100
    logging: bool = False
    depends_on: list[str] = Field(default_factory=list)


class NatPolicyIntent(BaseModel):
    id: str
    router_device_id: str
    mode: NatMode
    inside_segment_ids: list[str]
    outside_segment_id: str
    probe_destination_device_id: str = ""
    static_mappings: list["StaticNatMappingIntent"] = Field(default_factory=list)
    dynamic_pool: "DynamicNatPoolIntent | None" = None
    depends_on: list[str] = Field(default_factory=list)


class StaticNatMappingIntent(BaseModel):
    inside_endpoint_id: str
    outside_global_address: str


class DynamicNatPoolIntent(BaseModel):
    start_address: str
    end_address: str
    prefix: int


class PortSecurityPolicyIntent(BaseModel):
    id: str
    endpoint_ids: list[str]
    max_macs: int = 1
    violation: Literal["protect", "restrict", "shutdown"] = "restrict"
    sticky: bool = True
    depends_on: list[str] = Field(default_factory=list)


class DhcpInspectionPolicyIntent(BaseModel):
    id: str
    site_id: str
    segment_ids: list[str]
    enable_snooping: bool = True
    enable_dai: bool = False
    depends_on: list[str] = Field(default_factory=list)


class DeviceHardeningIntent(BaseModel):
    id: str
    device_ids: list[str]
    banner_motd: str = ""
    service_password_encryption: bool = True
    depends_on: list[str] = Field(default_factory=list)


class SecurityIntent(BaseModel):
    id: str
    policies: list[SecurityPolicyIntent] = Field(default_factory=list)
    nat_policies: list[NatPolicyIntent] = Field(default_factory=list)
    port_security: list[PortSecurityPolicyIntent] = Field(default_factory=list)
    dhcp_inspection: list[DhcpInspectionPolicyIntent] = Field(default_factory=list)
    hardening: list[DeviceHardeningIntent] = Field(default_factory=list)
    default_decision: SecurityDecision = SecurityDecision.ALLOW


class SecurityPhase(IntEnum):
    DEFINITIONS = 20
    ENFORCEMENT = 30
    ATTACHMENTS = 40
    HARDENING = 50
    VERIFICATION = 60


class SecurityActionType(str, Enum):
    CREATE_ACL = "create_acl"
    ADD_ACL_RULE = "add_acl_rule"
    ATTACH_ACL = "attach_acl"
    CONFIGURE_NAT = "configure_nat"
    CONFIGURE_PORT_SECURITY = "configure_port_security"
    CONFIGURE_DHCP_SNOOPING = "configure_dhcp_snooping"
    CONFIGURE_DAI = "configure_dynamic_arp_inspection"
    APPLY_HARDENING = "apply_device_hardening"


class BaseSecurityAction(BaseModel):
    id: str
    action_type: SecurityActionType
    phase: SecurityPhase
    device_id: str
    device_name: str
    model: str
    site_id: str
    depends_on: list[str] = Field(default_factory=list)
    apply_dependencies: list[str] = Field(default_factory=list)
    required_capability: SecurityCapabilityDimension
    critical: bool = True
    operation: OperationSemantics = OperationSemantics.SET_VALUE
    compensation_available: bool = False
    inverse_action_id: str = ""


class CreateSecurityAcl(BaseSecurityAction):
    action_type: Literal[SecurityActionType.CREATE_ACL] = SecurityActionType.CREATE_ACL
    operation: Literal[
        OperationSemantics.ENSURE_PRESENT
    ] = OperationSemantics.ENSURE_PRESENT
    acl_name: str


class AddSecurityAclRule(BaseSecurityAction):
    action_type: Literal[SecurityActionType.ADD_ACL_RULE] = SecurityActionType.ADD_ACL_RULE
    operation: Literal[
        OperationSemantics.ENSURE_PRESENT
    ] = OperationSemantics.ENSURE_PRESENT
    acl_name: str
    sequence: int
    policy_id: str = ""
    decision: SecurityDecision
    protocol: str
    source_cidr: str
    destination_cidr: str
    source_ports: list[int] = Field(default_factory=list)
    destination_ports: list[int] = Field(default_factory=list)
    logging: bool = False
    default_rule: bool = False


class AttachSecurityAcl(BaseSecurityAction):
    action_type: Literal[SecurityActionType.ATTACH_ACL] = SecurityActionType.ATTACH_ACL
    acl_name: str
    interface: str
    direction: Literal["in", "out"]


class ConfigureSecurityNat(BaseSecurityAction):
    action_type: Literal[SecurityActionType.CONFIGURE_NAT] = SecurityActionType.CONFIGURE_NAT
    policy_id: str
    mode: NatMode
    inside_interfaces: list[str]
    outside_interface: str
    inside_networks: list[str]
    translation_acl_number: int
    probe_destination_device_id: str = ""
    static_mappings: list["CompiledStaticNatMapping"] = Field(default_factory=list)
    dynamic_pool: "CompiledDynamicNatPool | None" = None


class CompiledStaticNatMapping(BaseModel):
    inside_endpoint_id: str
    inside_local_address: str
    outside_global_address: str


class CompiledDynamicNatPool(BaseModel):
    name: str
    start_address: str
    end_address: str
    netmask: str


class ConfigureEndpointPortSecurity(BaseSecurityAction):
    action_type: Literal[
        SecurityActionType.CONFIGURE_PORT_SECURITY
    ] = SecurityActionType.CONFIGURE_PORT_SECURITY
    policy_id: str
    switch_device_id: str
    interface: str
    endpoint_ids: list[str]
    max_macs: int
    violation: Literal["protect", "restrict", "shutdown"]
    sticky: bool
    access_configuration_action_id: str


class ConfigureDhcpSnooping(BaseSecurityAction):
    action_type: Literal[
        SecurityActionType.CONFIGURE_DHCP_SNOOPING
    ] = SecurityActionType.CONFIGURE_DHCP_SNOOPING
    policy_id: str
    vlan_ids: list[int]
    trusted_interfaces: list[str]


class ConfigureDynamicArpInspection(BaseSecurityAction):
    action_type: Literal[SecurityActionType.CONFIGURE_DAI] = SecurityActionType.CONFIGURE_DAI
    policy_id: str
    vlan_ids: list[int]
    trusted_interfaces: list[str]


class ApplyDeviceHardening(BaseSecurityAction):
    action_type: Literal[
        SecurityActionType.APPLY_HARDENING
    ] = SecurityActionType.APPLY_HARDENING
    policy_id: str
    banner_motd: str
    service_password_encryption: bool


SecurityAction = Annotated[
    CreateSecurityAcl
    | AddSecurityAclRule
    | AttachSecurityAcl
    | ConfigureSecurityNat
    | ConfigureEndpointPortSecurity
    | ConfigureDhcpSnooping
    | ConfigureDynamicArpInspection
    | ApplyDeviceHardening,
    Field(discriminator="action_type"),
]


class SecurityVerificationKind(str, Enum):
    TRAFFIC_POLICY = "traffic_policy"
    ACL_DIRECT_STATE = "acl_direct_state"
    NAT_DIRECT_STATE = "nat_direct_state"
    NAT_TRANSLATION = "nat_translation"
    PORT_SECURITY_STATE = "port_security_state"
    DHCP_SNOOPING_STATE = "dhcp_snooping_state"
    DAI_STATE = "dai_state"
    HARDENING_STATE = "hardening_state"


class SecurityProbeKind(str, Enum):
    ICMP_REACHABILITY = "icmp_reachability"
    DNS_LOOKUP = "dns_lookup"
    HTTP_FETCH = "http_fetch"
    HTTPS_FETCH = "https_fetch"
    NTP_SYNC = "ntp_sync"
    TFTP_GET = "tftp_get"
    VOICE_CALL = "voice_call"
    DIRECT_READBACK = "direct_readback"
    UNOBSERVABLE = "unobservable"


class SecurityVerificationExpectation(BaseModel):
    id: str
    kind: SecurityVerificationKind
    action_id: str
    policy_id: str
    probe_kind: SecurityProbeKind
    expected_decision: SecurityDecision = SecurityDecision.ALLOW
    source_device_id: str = ""
    source_device_name: str = ""
    destination_device_id: str = ""
    destination_device_name: str = ""
    destination_address: str = ""
    protocol: str = "ip"
    destination_ports: list[int] = Field(default_factory=list)
    baseline_required: bool = False
    cleanup_recovery_required: bool = False
    required_query: str = ""
    depends_on: list[str] = Field(default_factory=list)
    verification_prerequisites: list[VerificationPrerequisite] = Field(default_factory=list)


def security_verification_capability(
    expectation: SecurityVerificationExpectation,
) -> SecurityCapabilityDimension:
    """Map an acceptance expectation to its independent capability gate."""
    if expectation.kind is SecurityVerificationKind.NAT_TRANSLATION:
        return SecurityCapabilityDimension.NAT_BEHAVIORAL
    if expectation.kind is SecurityVerificationKind.TRAFFIC_POLICY:
        return SecurityCapabilityDimension.ACL_BEHAVIORAL
    return {
        SecurityVerificationKind.ACL_DIRECT_STATE:
            SecurityCapabilityDimension.ACL_READBACK,
        SecurityVerificationKind.NAT_DIRECT_STATE:
            SecurityCapabilityDimension.NAT_TRANSLATION_READBACK,
        SecurityVerificationKind.PORT_SECURITY_STATE:
            SecurityCapabilityDimension.PORT_SECURITY_READBACK,
        SecurityVerificationKind.DHCP_SNOOPING_STATE:
            SecurityCapabilityDimension.DHCP_SNOOPING_READBACK,
        SecurityVerificationKind.DAI_STATE:
            SecurityCapabilityDimension.DAI_READBACK,
        SecurityVerificationKind.HARDENING_STATE:
            SecurityCapabilityDimension.HARDENING_READBACK,
    }[expectation.kind]


class SecurityFoundationRequirement(BaseModel):
    id: str
    kind: Literal[
        "l3_interface", "access_port", "service", "voice", "endpoint", "vlan"
    ]
    source_id: str
    source_hash: str = ""


class SecurityPlan(BaseModel):
    id: str
    default_decision: SecurityDecision = SecurityDecision.ALLOW
    source_topology_id: str
    source_topology_hash: str
    source_topology_hash_schema: str = "legacy-full-v1"
    source_configuration_id: str
    source_configuration_hash: str
    source_service_id: str = ""
    source_service_hash: str = ""
    source_voice_id: str = ""
    source_voice_hash: str = ""
    semantic_hash: str = ""
    actions: list[SecurityAction] = Field(default_factory=list)
    foundational_requirements: list[SecurityFoundationRequirement] = Field(
        default_factory=list,
    )
    verification_expectations: list[SecurityVerificationExpectation] = Field(
        default_factory=list,
    )

    def actions_of_type(self, action_type: SecurityActionType) -> list[SecurityAction]:
        return [item for item in self.actions if item.action_type is action_type]


class SecurityCompileSummary(BaseModel):
    security_plan_id: str = ""
    semantic_hash: str = ""
    source_topology_hash: str = ""
    source_topology_hash_schema: str = ""
    source_configuration_hash: str = ""
    source_service_hash: str = ""
    source_voice_hash: str = ""
    policy_count: int = 0
    action_count: int = 0
    actions_by_type: dict[str, int] = Field(default_factory=dict)
    verification_count: int = 0
    warnings: int = 0
    errors: int = 0


class SecurityCompileResult(BaseModel):
    plan: SecurityPlan | None = None
    semantic_hash: str = ""
    summary: SecurityCompileSummary = Field(default_factory=SecurityCompileSummary)
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


def security_action_type_counts(actions: list[SecurityAction]) -> dict[str, int]:
    counts = Counter(item.action_type.value for item in actions)
    return dict(sorted(counts.items()))
