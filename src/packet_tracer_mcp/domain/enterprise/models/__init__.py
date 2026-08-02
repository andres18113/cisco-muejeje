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
from .requirements import EndpointRequirement
from .roles import DeviceRole
from .segments import NetworkSegment, SegmentRequirement, SegmentRole
from .topology import NetworkLayer, TopologyDesign, TopologyPattern

__all__ = [
    "AccessBlockPlan", "AccessCapacityRequirement", "BuildingIntent", "CapabilityConflict",
    "CapabilityEvidence", "CapabilityProbeResult", "CapabilitySnapshot", "CapabilityStatus",
    "CapacityPlan", "CatalogCoverageReport", "CatalogGapReport", "CleanupStatus", "DetailLevel", "DeviceCandidate",
    "DeviceCandidateStatus", "DeviceCapabilities", "DeviceIdentity", "DeviceRequirement",
    "DeviceRole", "DeviceSelectionResult", "EndpointRequirement",
    "DiscoverySource", "E4ReadinessReport", "E4ReadinessState", "EndpointGroup", "EnterpriseIntent",
    "EnterprisePlan", "EvidenceSource", "FloorIntent",
    "HardwareCandidate", "HardwareLinkRequirement", "HardwarePlan", "HardwarePlanStatus",
    "HierarchyMode", "LinkRole", "ModelIdentityStatus", "ModuleInstallation", "NetworkLayer", "NormalizedPortSpeed",
    "NetworkSegment", "PlannedNetworkDevice", "PortAssignmentRange", "PortAttachmentPolicy",
    "PortClass", "PortDescriptor", "ProbeCost", "ProbeDefinition", "ProbeExecutionStatus",
    "ProbeLevel", "ProbeRequest", "ProbeSafety", "ProbeSession", "ProbeSessionResult",
    "ResiliencyLevel", "RuntimeDeviceDescriptor", "RuntimePortDescriptor", "SegmentRequirement", "SegmentRole",
    "SiteHardwarePlan", "SiteIntent", "SitePlan", "SiteType", "TopologyDesign",
    "SnapshotDiff", "TopologyPattern", "ZoneIntent",
]
