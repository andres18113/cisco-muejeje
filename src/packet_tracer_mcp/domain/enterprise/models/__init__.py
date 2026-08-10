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
from .deployment import (
    DeploymentBinding, DeploymentIdentityError, DeploymentManifest,
    EnvironmentFingerprint, IdentityMethod, build_deployment_manifest,
    resolve_manifest_targets, runtime_target_fingerprint,
)
from .physical_deployment import (
    PhysicalDeploymentFailureCode, PhysicalDeploymentItemResult,
    PhysicalDeploymentItemStatus, PhysicalDeploymentResult,
    PhysicalDeploymentStatus, PhysicalDeviceObservation,
    PhysicalLinkObservation, PhysicalModuleObservation, PhysicalMutationResult,
    PhysicalObjectKind,
)
from .evidence import (
    CapabilityReadiness, EvidenceFreshness, EvidenceRecord, EvidenceStrength,
    ObservationStatus, ReadinessStatus, SupportStatus, VerificationMethod,
    VerificationStatus, evidence_from_legacy_result,
)
from .execution import (
    ApplicationExecutionJournal, CompensationStatus, DirtyState,
    ExecutionJournalEntry, MutationDisposition, OperationSemantics,
    disposition_from_status, journal_from_action_results,
    satisfies_apply_dependency,
)
from .failure_domain import (
    FailureDomain, FailureDomainCatalog, FailureDomainCoverageGap,
    FailureDomainIndependenceResult, FailureDomainProvenance, FailureDomainType,
    FailurePath, FailureScenario, FailureScenarioScope, IndependenceStatus,
)
from .enterprise_plan import EnterprisePlan, SitePlan
from .hierarchy import BuildingIntent, EndpointGroup, FloorIntent, ZoneIntent
from .ipam_reconciliation import (
    AddressPurpose, AddressReconcileIssue, AddressReconcileIssueCode,
    AddressReconcileResult, AddressReconcileStatus, AddressRenumbering,
    ExistingAddressBinding, FinalAddressBinding, FinalAddressPlan,
    InfrastructureAddressDemand, ReconciliationStatus,
)
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
    CallState, CallVerificationResult, PhoneExecutionMethod, PhoneRegistrationResult, PhoneVoiceOutcome,
    RuntimeCallObservation, RuntimePhoneRegistration, VoiceApplicationResult,
)
from .security_plan import (
    DeviceHardeningIntent, DhcpInspectionPolicyIntent, DynamicNatPoolIntent,
    NatMode, NatPolicyIntent,
    PortSecurityPolicyIntent, SecurityActionType, SecurityCapabilityDimension,
    SecurityCapabilityProfile, SecurityCapabilityStatus, SecurityCompileResult,
    SecurityDecision, SecurityIntent, SecurityPlan, SecurityPolicyIntent, SecurityProbeKind,
    SecurityVerificationExpectation, SecurityVerificationKind,
    StaticNatMappingIntent,
)
from .security_runtime import (
    RuntimeSecurityVerification, SecurityApplicationResult,
    SecurityVerificationResult, SecurityVerificationStage,
)
from .control_plane import (
    ConfigureEigrpIpv4, ConfigureEtherChannel, ConfigureHsrp, ConfigureOspfv2,
    ConfigureSpanningTree, ConfigureStpEdgePort, ControlPlaneActionType,
    ControlPlaneCapabilityDimension, ControlPlaneCapabilityProfile,
    ControlPlaneCompileResult, ControlPlaneIntent, ControlPlanePlan,
    ControlPlaneVerificationExpectation, ControlPlaneVerificationKind,
    DynamicRoutingIntent, DynamicRoutingProtocol, EtherChannelIntent,
    EtherChannelProtocol, FirstHopRedundancyIntent, LinkFailureScenario,
    LinkFailureScenarioIntent, StpIntent, StpMode,
)
from .control_plane_runtime import (
    ControlPlaneApplicationResult, ControlPlaneExecutionStage,
    ControlPlaneVerificationResult, FailureScenarioResult,
    FailureScenarioTransition, FailureTransitionPhase,
    RuntimeControlPlaneVerification, RuntimeFailureScenarioResult,
)
from .roles import DeviceRole
from .segments import NetworkSegment, SegmentRequirement, SegmentRole
from .topology import NetworkLayer, TopologyDesign, TopologyPattern
from .verification import (
    PrerequisiteKind, VerificationDependencyError, VerificationPrerequisite,
    legacy_action_prerequisites, order_verification_expectations,
    prerequisites_satisfied,
)

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
    "CallState", "CallVerificationResult", "PhoneExecutionMethod", "PhoneRegistrationResult",
    "PhoneVoiceOutcome", "RuntimeCallObservation", "RuntimePhoneRegistration",
    "VoiceApplicationResult",
    "DeviceHardeningIntent", "DhcpInspectionPolicyIntent", "DynamicNatPoolIntent",
    "NatMode", "NatPolicyIntent",
    "PortSecurityPolicyIntent", "SecurityActionType", "SecurityCapabilityDimension",
    "SecurityCapabilityProfile", "SecurityCapabilityStatus", "SecurityCompileResult",
    "SecurityDecision", "SecurityIntent", "SecurityPlan", "SecurityPolicyIntent", "SecurityProbeKind",
    "SecurityVerificationExpectation", "SecurityVerificationKind",
    "StaticNatMappingIntent",
    "RuntimeSecurityVerification", "SecurityApplicationResult",
    "SecurityVerificationResult", "SecurityVerificationStage",
    "ConfigureEigrpIpv4", "ConfigureEtherChannel", "ConfigureHsrp",
    "ConfigureOspfv2", "ConfigureSpanningTree", "ConfigureStpEdgePort",
    "ControlPlaneActionType", "ControlPlaneCapabilityDimension",
    "ControlPlaneCapabilityProfile", "ControlPlaneCompileResult",
    "ControlPlaneIntent", "ControlPlanePlan", "ControlPlaneVerificationExpectation",
    "ControlPlaneVerificationKind", "DynamicRoutingIntent",
    "DynamicRoutingProtocol", "EtherChannelIntent", "EtherChannelProtocol",
    "FirstHopRedundancyIntent", "LinkFailureScenario",
    "LinkFailureScenarioIntent", "StpIntent", "StpMode",
    "ControlPlaneApplicationResult", "ControlPlaneExecutionStage",
    "ControlPlaneVerificationResult", "FailureScenarioResult",
    "FailureScenarioTransition", "FailureTransitionPhase",
    "RuntimeControlPlaneVerification", "RuntimeFailureScenarioResult",
    "DeploymentBinding", "DeploymentIdentityError", "DeploymentManifest",
    "EnvironmentFingerprint", "IdentityMethod", "build_deployment_manifest",
    "resolve_manifest_targets", "runtime_target_fingerprint",
    "PhysicalDeploymentFailureCode", "PhysicalDeploymentItemResult",
    "PhysicalDeploymentItemStatus", "PhysicalDeploymentResult",
    "PhysicalDeploymentStatus", "PhysicalDeviceObservation",
    "PhysicalLinkObservation", "PhysicalModuleObservation",
    "PhysicalMutationResult", "PhysicalObjectKind",
    "CapabilityReadiness", "EvidenceFreshness", "EvidenceRecord", "EvidenceStrength",
    "ObservationStatus", "ReadinessStatus", "SupportStatus", "VerificationMethod",
    "VerificationStatus", "evidence_from_legacy_result",
    "ApplicationExecutionJournal", "CompensationStatus",
    "DirtyState", "ExecutionJournalEntry", "MutationDisposition", "OperationSemantics",
    "disposition_from_status", "journal_from_action_results", "satisfies_apply_dependency",
    "AddressPurpose", "AddressReconcileIssue", "AddressReconcileIssueCode",
    "AddressReconcileResult", "AddressReconcileStatus", "AddressRenumbering",
    "ExistingAddressBinding", "FinalAddressBinding", "FinalAddressPlan",
    "InfrastructureAddressDemand", "ReconciliationStatus",
    "FailureDomain", "FailureDomainCatalog", "FailureDomainCoverageGap",
    "FailureDomainIndependenceResult", "FailureDomainProvenance", "FailureDomainType",
    "FailurePath", "FailureScenario", "FailureScenarioScope", "IndependenceStatus",
    "PrerequisiteKind", "VerificationDependencyError", "VerificationPrerequisite",
    "legacy_action_prerequisites", "order_verification_expectations",
    "prerequisites_satisfied",
]
