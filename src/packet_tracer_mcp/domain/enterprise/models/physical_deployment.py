"""Typed E4 physical deployment observations and outcomes.

The domain records what a backend applied and what it independently observed.
It deliberately contains no Packet Tracer API or JavaScript details.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .deployment import DeploymentManifest, EnvironmentFingerprint
from .evidence import EvidenceRecord
from .execution import (
    ApplicationExecutionJournal,
    DirtyState,
    MutationDisposition,
)


class PhysicalObjectKind(str, Enum):
    DEVICE = "device"
    MODULE = "module"
    LINK = "link"


class PhysicalDeploymentStatus(str, Enum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    FAILED = "failed"


class PhysicalDeploymentItemStatus(str, Enum):
    NOT_ATTEMPTED = "not_attempted"
    APPLIED = "applied"
    SATISFIED = "satisfied"
    OBSERVED = "observed"
    FAILED = "failed"


class PhysicalDeploymentFailureCode(str, Enum):
    NONE = "none"
    INVALID_TOPOLOGY = "invalid_topology"
    PHYSICAL_HASH_MISMATCH = "physical_hash_mismatch"
    ENVIRONMENT_FINGERPRINT_INVALID = "environment_fingerprint_invalid"
    DEVICE_APPLICATION_FAILED = "device_application_failed"
    DEVICE_OBSERVATION_FAILED = "device_observation_failed"
    PORT_OBSERVATION_FAILED = "port_observation_failed"
    MODULE_APPLICATION_FAILED = "module_application_failed"
    MODULE_OBSERVATION_UNAVAILABLE = "module_observation_unavailable"
    MODULE_OBSERVATION_FAILED = "module_observation_failed"
    LINK_APPLICATION_FAILED = "link_application_failed"
    LINK_OBSERVATION_FAILED = "link_observation_failed"
    MANIFEST_CREATION_FAILED = "manifest_creation_failed"


class PhysicalMutationResult(BaseModel):
    """Result returned by a backend for one typed ensure operation."""

    target_id: str
    target_kind: PhysicalObjectKind
    disposition: MutationDisposition = MutationDisposition.UNKNOWN
    applied: bool = False
    inverse_available: bool = False
    inverse_action_id: str = ""
    message: str = ""


class PhysicalDeviceObservation(BaseModel):
    """Fresh structured observation of one runtime device."""

    target_id: str
    observed: bool = True
    deployed_name: str
    model: str
    interfaces: list[str] = Field(default_factory=list)
    interfaces_observed: bool = True
    runtime_identifier: str = ""
    runtime_identifier_stable: bool = False
    runtime_fingerprint: str = ""
    message: str = ""


class PhysicalLinkObservation(BaseModel):
    """Fresh structured observation of the exact peers of one runtime link."""

    target_id: str
    observed: bool = True
    device_a: str
    port_a: str
    device_b: str
    port_b: str
    cable: str = ""
    cable_observed: bool = False
    message: str = ""


class PhysicalModuleObservation(BaseModel):
    """Fresh observation of one exact module identity in one device slot."""

    target_id: str
    observed: bool = True
    device_name: str
    slot: str
    module: str
    message: str = ""


class PhysicalDeploymentItemResult(BaseModel):
    target_id: str
    target_kind: PhysicalObjectKind
    status: PhysicalDeploymentItemStatus = PhysicalDeploymentItemStatus.NOT_ATTEMPTED
    disposition: MutationDisposition = MutationDisposition.UNKNOWN
    applied: bool = False
    observed: bool = False
    message: str = ""


class PhysicalDeploymentResult(BaseModel):
    topology_id: str
    physical_topology_hash: str
    deployment_id: str
    environment_fingerprint: EnvironmentFingerprint
    status: PhysicalDeploymentStatus
    failure_code: PhysicalDeploymentFailureCode = PhysicalDeploymentFailureCode.NONE
    item_results: list[PhysicalDeploymentItemResult] = Field(default_factory=list)
    manifest: DeploymentManifest | None = None
    execution_journal: ApplicationExecutionJournal
    dirty_state: DirtyState = DirtyState.CLEAN
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    def compact_summary(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for item in self.item_results:
            counts[item.status.value] = counts.get(item.status.value, 0) + 1
        return {
            "topology_id": self.topology_id,
            "physical_topology_hash": self.physical_topology_hash,
            "deployment_id": self.deployment_id,
            "environment_fingerprint": self.environment_fingerprint.semantic_hash,
            "status": self.status.value,
            "failure_code": self.failure_code.value,
            "items": dict(sorted(counts.items())),
            "manifest": self.manifest.compact_summary() if self.manifest else None,
            "dirty_state": self.dirty_state.value,
            "execution_journal": self.execution_journal.compact_summary(),
            "evidence_records": [item.compact_summary() for item in self.evidence_records],
            "errors": list(self.errors),
        }
