"""E9 execution preserves the existing foundational hashes and prerequisites."""

from __future__ import annotations

from ..use_cases.apply_control_plane import ControlPlaneApplicator
from ..use_cases.foundational_evidence import derive_foundational_hashes
from ...domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult, ActionExecutionStatus, ConfigurationRuntimeContext,
)
from ...domain.enterprise.models.control_plane import ControlPlaneCapabilityProfile
from ...domain.enterprise.models.control_plane_runtime import ControlPlaneApplicationResult
from ...domain.enterprise.models.deployment import DeploymentManifest
from .contracts import CPScaleStageExecutionInput


class CPScaleControlPlaneStage:
    def __init__(
        self, applicator: ControlPlaneApplicator,
        capabilities: dict[str, ControlPlaneCapabilityProfile],
    ) -> None:
        self.applicator = applicator
        self.capabilities = capabilities

    def execute(
        self, request: CPScaleStageExecutionInput, manifest: DeploymentManifest,
        statuses: dict[str, ActionExecutionStatus], mutation_ids: tuple[str, ...],
        retained_results: tuple[ActionApplicationResult, ...],
    ) -> ControlPlaneApplicationResult:
        projection = request.projection
        return self.applicator.apply(
            projection.control_plane,
            actual_source_topology_hash=projection.topology.physical_identity_hash,
            actual_source_configuration_hash=projection.configuration.semantic_hash,
            foundational_statuses=statuses,
            foundational_hashes=derive_foundational_hashes(projection.control_plane),
            capabilities=self.capabilities,
            runtime_context=ConfigurationRuntimeContext(environment_fingerprint=request.fingerprint),
            deployment_manifest=manifest,
            mutation_action_ids=mutation_ids,
            retained_action_results=retained_results,
        )
