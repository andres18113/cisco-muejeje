"""Backend-neutral failure-domain contracts for resiliency analysis.

The domain deliberately records only facts supplied by a plan or by explicit
evidence.  In particular, power feeds, carrier identities and shared-risk
groups are never inferred from visual separation or device naming.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FailureDomainType(str, Enum):
    DEVICE = "device"
    LINK = "link"
    CHASSIS = "chassis"
    POWER = "power"
    SITE = "site"
    UPLINK_PROVIDER = "uplink_provider"
    SHARED_RISK = "shared_risk"


class FailureDomainProvenance(str, Enum):
    EXPLICIT = "explicit"
    DERIVED = "derived"


class FailureScenarioScope(str, Enum):
    LINK_FAULT = "link_fault"
    DEVICE_FAULT = "device_fault"
    CHASSIS_FAULT = "chassis_fault"
    POWER_FAULT = "power_fault"
    SITE_FAULT = "site_fault"
    UPLINK_PROVIDER_FAULT = "uplink_provider_fault"
    SHARED_RISK_FAULT = "shared_risk_fault"


class IndependenceStatus(str, Enum):
    INDEPENDENT = "independent"
    NOT_INDEPENDENT = "not_independent"
    UNKNOWN = "unknown"


class FailureDomain(BaseModel):
    """One declared or safely-derived blast radius."""

    id: str
    domain_type: FailureDomainType
    provenance: FailureDomainProvenance
    device_ids: list[str] = Field(default_factory=list)
    link_ids: list[str] = Field(default_factory=list)
    blocking: bool = True
    evidence_reference: str = ""
    description: str = ""


class FailureDomainCatalog(BaseModel):
    """Deterministic domain inventory bound to a physical topology."""

    source_topology_id: str = ""
    source_topology_hash: str = ""
    semantic_hash: str = ""
    domains: list[FailureDomain] = Field(default_factory=list)

    def domains_of_type(self, domain_type: FailureDomainType) -> list[FailureDomain]:
        return [item for item in self.domains if item.domain_type is domain_type]


class FailurePath(BaseModel):
    """Ordered physical resources used by one forwarding path."""

    id: str
    device_ids: list[str] = Field(default_factory=list)
    link_ids: list[str] = Field(default_factory=list)
    endpoint_device_ids: list[str] = Field(default_factory=list)

    @property
    def effective_endpoint_device_ids(self) -> list[str]:
        if self.endpoint_device_ids:
            return sorted(set(self.endpoint_device_ids))
        if not self.device_ids:
            return []
        return sorted({self.device_ids[0], self.device_ids[-1]})


class FailureScenario(BaseModel):
    """Two paths compared for one explicitly-scoped failure claim."""

    id: str
    scope: FailureScenarioScope
    primary_path: FailurePath
    surviving_path: FailurePath
    additional_relevant_domain_types: list[FailureDomainType] = Field(
        default_factory=list,
    )


class FailureDomainCoverageGap(BaseModel):
    domain_type: FailureDomainType
    primary_device_ids: list[str] = Field(default_factory=list)
    primary_link_ids: list[str] = Field(default_factory=list)
    surviving_device_ids: list[str] = Field(default_factory=list)
    surviving_link_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class FailureDomainIndependenceResult(BaseModel):
    scenario_id: str
    scope: FailureScenarioScope
    status: IndependenceStatus
    relevant_domain_types: list[FailureDomainType] = Field(default_factory=list)
    blocking_domain_ids: list[str] = Field(default_factory=list)
    ignored_common_endpoint_device_ids: list[str] = Field(default_factory=list)
    ignored_domain_ids: list[str] = Field(default_factory=list)
    missing_coverage: list[FailureDomainCoverageGap] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    def compact_summary(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "scope": self.scope.value,
            "status": self.status.value,
            "blocking_domain_ids": list(self.blocking_domain_ids),
            "ignored_common_endpoint_device_ids": list(
                self.ignored_common_endpoint_device_ids,
            ),
            "missing_coverage_types": sorted(
                {item.domain_type.value for item in self.missing_coverage},
            ),
        }
