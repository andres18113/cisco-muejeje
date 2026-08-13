"""Typed E4 physical deployment observations and outcomes.

The domain records what a backend applied and what it independently observed.
It deliberately contains no Packet Tracer API or JavaScript details.
"""

from __future__ import annotations

from collections import Counter
from enum import Enum

from pydantic import BaseModel, Field

from .deployment import DeploymentManifest, EnvironmentFingerprint
from .evidence import (
    EvidenceFreshness,
    EvidenceRecord,
    ObservationStatus,
    SupportStatus,
)
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
    WORKSPACE_OBSERVATION_FAILED = "workspace_observation_failed"
    WORKSPACE_NOT_EMPTY = "workspace_not_empty"
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
    runtime_link_identifier: str = ""
    runtime_link_identity_observed: bool = False
    message: str = ""


class PhysicalModuleEffectCapability(BaseModel):
    """Backend support for proving one requested module by physical effect.

    Exact module identity is a separate axis.  In particular, a backend may
    support insertion and fresh port-effect read-back while being unable to
    name the installed card.
    """

    target_id: str
    operation_support: SupportStatus = SupportStatus.UNKNOWN
    effect_observation_support: SupportStatus = SupportStatus.UNKNOWN
    expected_ports: list[str] = Field(default_factory=list)
    expected_port_classes: list[str] = Field(default_factory=list)
    identity_observation_status: ObservationStatus = ObservationStatus.UNOBSERVABLE
    message: str = ""


class PhysicalModuleSlotObservation(BaseModel):
    """Direct fields exposed by one runtime module-tree entry.

    `observed_module_number` is deliberately not called `slot`: Packet Tracer
    reports values such as ``"0"`` while insertion requests use ``"0/0"`` and
    the repository has no evidence that those namespaces are interchangeable.
    """

    observed_module_number: str = ""
    slot_type_code: str = ""
    port_count: int | None = None
    observed_module_identity: str = ""
    identity_observable: bool = False


class PhysicalModuleObservation(BaseModel):
    """Before/after evidence for a requested module's physical effect.

    Requested identity and directly observed identity are never aliases.  A
    verified port effect can therefore coexist with an UNOBSERVABLE identity.
    """

    target_id: str
    observed: bool = True
    device_name: str
    requested_slot: str
    requested_module: str
    freshness: EvidenceFreshness = EvidenceFreshness.UNKNOWN
    port_inventory_observed: bool = False
    expected_ports: list[str] = Field(default_factory=list)
    expected_port_classes: list[str] = Field(default_factory=list)
    ports_before: list[str] = Field(default_factory=list)
    ports_after: list[str] = Field(default_factory=list)
    observed_expected_ports: list[str] = Field(default_factory=list)
    added_ports: list[str] = Field(default_factory=list)
    observed_port_classes: list[str] = Field(default_factory=list)
    slot_observations: list[PhysicalModuleSlotObservation] = Field(default_factory=list)
    slot_effect_observed: bool = False
    effect_observed: bool = False
    identity_observation_status: ObservationStatus = ObservationStatus.UNOBSERVABLE
    observed_module_identity: str = ""
    message: str = ""


class PhysicalWorkspaceDeviceObservation(BaseModel):
    """One device returned by a read-only workspace inventory."""

    name: str
    model: str
    ports: list[str] = Field(default_factory=list)
    backend_managed: bool = False

    def identity_key(self) -> tuple[str, str, tuple[str, ...]]:
        return self.name, self.model, tuple(sorted(set(self.ports), key=str.casefold))


class PhysicalWorkspaceLinkObservation(BaseModel):
    """One link returned by a read-only workspace inventory."""

    class_name: str = ""
    device_a: str = ""
    port_a: str = ""
    device_b: str = ""
    port_b: str = ""

    def identity_key(self) -> tuple[str, tuple[tuple[str, str], tuple[str, str]]]:
        endpoints = tuple(sorted(
            ((self.device_a, self.port_a), (self.device_b, self.port_b)),
        ))
        return self.class_name, endpoints


class PhysicalWorkspaceObservation(BaseModel):
    """Complete, read-only physical workspace inventory.

    A backend-managed power-distribution object may be retained, but semantic
    devices, any link, or an incomplete inventory make the workspace unsafe for
    the disposable Slice 2A qualification.
    """

    observed: bool = True
    devices: list[PhysicalWorkspaceDeviceObservation] = Field(default_factory=list)
    links: list[PhysicalWorkspaceLinkObservation] = Field(default_factory=list)
    message: str = ""

    @property
    def semantic_devices(self) -> list[PhysicalWorkspaceDeviceObservation]:
        return [item for item in self.devices if not item.backend_managed]

    @property
    def backend_managed_devices(self) -> list[PhysicalWorkspaceDeviceObservation]:
        return [item for item in self.devices if item.backend_managed]

    @property
    def safe_for_disposable_mutation(self) -> bool:
        return self.observed and not self.semantic_devices and not self.links

    def compact_summary(self) -> dict[str, object]:
        return {
            "observed": self.observed,
            "semantic_device_count": len(self.semantic_devices),
            "backend_managed_device_count": len(self.backend_managed_devices),
            "link_count": len(self.links),
            "devices": [
                item.model_dump(mode="json")
                for item in sorted(self.devices, key=lambda value: value.identity_key())
            ],
            "links": [
                item.model_dump(mode="json")
                for item in sorted(self.links, key=lambda value: value.identity_key())
            ],
            "message": self.message,
        }


def physical_workspace_restoration_matches(
    baseline: PhysicalWorkspaceObservation,
    observed: PhysicalWorkspaceObservation,
) -> bool:
    """Compare semantic inventory exactly while allowing new retained PDDs."""

    if not baseline.observed or not observed.observed:
        return False
    baseline_semantic = Counter(
        item.identity_key() for item in baseline.semantic_devices
    )
    observed_semantic = Counter(
        item.identity_key() for item in observed.semantic_devices
    )
    baseline_links = Counter(item.identity_key() for item in baseline.links)
    observed_links = Counter(item.identity_key() for item in observed.links)
    baseline_backend_managed = Counter(
        item.identity_key() for item in baseline.backend_managed_devices
    )
    observed_backend_managed = Counter(
        item.identity_key() for item in observed.backend_managed_devices
    )
    return (
        baseline_semantic == observed_semantic
        and baseline_links == observed_links
        and all(
            observed_backend_managed[key] >= count
            for key, count in baseline_backend_managed.items()
        )
    )


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
