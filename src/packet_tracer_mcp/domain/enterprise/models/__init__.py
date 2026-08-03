"""Modelos del dominio Enterprise."""

from .capabilities import (
    CapabilityEvidence,
    CapabilityStatus,
    DeviceCandidate,
    DeviceCandidateStatus,
    DeviceCapabilities,
    DeviceRequirement,
    DeviceSelectionResult,
    EvidenceSource,
)
from .capacity import AccessCapacityRequirement, CapacityPlan, PortAttachmentPolicy
from .compilation import (
    CompilationIssue, CompilationIssueCode, CompilationIssueSeverity, ConcreteLinkRole,
    EnterpriseCompileResult, EnterpriseCompileSummary, LayoutProfile, LayoutRegion,
    PhysicalCompilationProfile, PhysicalModelProfile,
)
from .configuration import (
    ConfigurationActionType, ConfigurationCompileResult, ConfigurationIssue,
    ConfigurationIssueCode, ConfigurationPhase, ConfigurationPlan, ConfigurationPolicy,
)
from .configuration_runtime import (
    ActionApplicationResult, ActionExecutionStatus, ConfigurationApplicationResult,
    ConfigurationApplicationStatus, ConfigurationFailureCode, ConvergenceReport,
    ConfigurationRuntimeContext, FieldVerificationStatus, RuntimeActionMutation, RuntimeConfigurationTarget,
    RuntimeVerification, VerificationResult,
)
from .enterprise_plan import EnterprisePlan, SitePlan
from .hierarchy import BuildingIntent, EndpointGroup, FloorIntent, ZoneIntent
from .discovery import (
    CapabilityConflict, CapabilityProbeResult, CapabilitySnapshot, CatalogGapReport,
    CleanupStatus, DetailLevel, DeviceIdentity, DiscoverySource, E4ReadinessReport,
    E4ReadinessState, ModelIdentityStatus, ProbeCost, ProbeDefinition, ProbeExecutionStatus,
    ProbeLevel, ProbeRequest, ProbeSafety, ProbeSession, ProbeSessionResult,
    RuntimeDeviceDescriptor, RuntimePortDescriptor, SnapshotDiff,
)
from .hardware import (
    AccessBlockPlan, CatalogCoverageReport, HardwareCandidate, HardwareLinkRequirement,
    HardwarePlan, HardwarePlanStatus, HierarchyMode, LinkRole, ModuleInstallation,
    NormalizedPortSpeed, PlannedNetworkDevice, PortAssignmentRange, PortClass,
    PortDescriptor, ResiliencyLevel, SiteHardwarePlan,
)
from .intent import EnterpriseIntent, SiteIntent, SiteType
from .requirements import EndpointRequirement, ServiceRequirement
from .service_plan import (
    DnsRecordRequirement, ServiceActionType, ServiceCapabilityProfile,
    ServiceCompileResult, ServiceEvidenceKind, ServicePlan, ServiceType,
    TftpFileRequirement,
)
from .service_runtime import ServiceApplicationResult, ServiceOutcome
from .voice_plan import (
    ExtensionRange, VoiceActionType, VoiceCapabilityDimension, VoiceCapabilityProfile,
    VoiceCapabilityStatus, VoiceCompileResult, VoiceIntent, VoicePlan, VoicePolicy,
)
from .voice_runtime import (
    CallState, CallVerificationResult, PhoneRegistrationResult, PhoneVoiceOutcome,
    RuntimeCallObservation, RuntimePhoneRegistration, VoiceApplicationResult,
)
from .roles import DeviceRole
from .segments import NetworkSegment, SegmentRequirement, SegmentRole
from .topology import NetworkLayer, TopologyDesign, TopologyPattern

__all__ = [
    "AccessBlockPlan", "AccessCapacityRequirement", "BuildingIntent", "CapabilityConflict",
    "CapabilityEvidence", "CapabilityProbeResult", "CapabilitySnapshot", "CapabilityStatus",
    "CapacityPlan", "CatalogCoverageReport", "CatalogGapReport", "CleanupStatus", "DetailLevel", "DeviceCandidate",
    "CompilationIssue", "CompilationIssueCode", "CompilationIssueSeverity", "ConcreteLinkRole",
    "ConfigurationActionType", "ConfigurationCompileResult", "ConfigurationIssue",
    "ConfigurationIssueCode", "ConfigurationPhase", "ConfigurationPlan", "ConfigurationPolicy",
    "ActionApplicationResult", "ActionExecutionStatus", "ConfigurationApplicationResult",
    "ConfigurationApplicationStatus", "ConfigurationFailureCode", "ConvergenceReport",
    "ConfigurationRuntimeContext", "FieldVerificationStatus", "RuntimeActionMutation", "RuntimeConfigurationTarget",
    "RuntimeVerification", "VerificationResult",
    "DeviceCandidateStatus", "DeviceCapabilities", "DeviceIdentity", "DeviceRequirement",
    "DeviceRole", "DeviceSelectionResult", "EndpointRequirement", "ServiceRequirement",
    "DiscoverySource", "E4ReadinessReport", "E4ReadinessState", "EndpointGroup", "EnterpriseIntent",
    "EnterprisePlan", "EvidenceSource", "FloorIntent",
    "EnterpriseCompileResult", "EnterpriseCompileSummary",
    "HardwareCandidate", "HardwareLinkRequirement", "HardwarePlan", "HardwarePlanStatus",
    "HierarchyMode", "LayoutProfile", "LayoutRegion", "LinkRole", "ModelIdentityStatus", "ModuleInstallation", "NetworkLayer", "NormalizedPortSpeed",
    "NetworkSegment", "PlannedNetworkDevice", "PortAssignmentRange", "PortAttachmentPolicy",
    "PhysicalCompilationProfile", "PhysicalModelProfile", "PortClass", "PortDescriptor", "ProbeCost", "ProbeDefinition", "ProbeExecutionStatus",
    "ProbeLevel", "ProbeRequest", "ProbeSafety", "ProbeSession", "ProbeSessionResult",
    "ResiliencyLevel", "RuntimeDeviceDescriptor", "RuntimePortDescriptor", "SegmentRequirement", "SegmentRole",
    "SiteHardwarePlan", "SiteIntent", "SitePlan", "SiteType", "TopologyDesign",
    "SnapshotDiff", "TopologyPattern", "ZoneIntent",
    "DnsRecordRequirement", "ServiceActionType", "ServiceApplicationResult",
    "ServiceCapabilityProfile", "ServiceCompileResult", "ServiceEvidenceKind",
    "ServiceOutcome", "ServicePlan", "ServiceType", "TftpFileRequirement",
    "ExtensionRange", "VoiceActionType", "VoiceCapabilityDimension",
    "VoiceCapabilityProfile", "VoiceCapabilityStatus", "VoiceCompileResult",
    "VoiceIntent", "VoicePlan", "VoicePolicy",
    "CallState", "CallVerificationResult", "PhoneRegistrationResult",
    "PhoneVoiceOutcome", "RuntimeCallObservation", "RuntimePhoneRegistration",
    "VoiceApplicationResult",
]
