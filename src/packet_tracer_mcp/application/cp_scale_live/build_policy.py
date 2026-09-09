"""Narrow canonical projection/physical policies without shared run state."""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import CPScaleStageContinuity
from .errors import CanonicalLiveFailure
from .run_contracts import CPScaleResumeGate
from .session import CPScaleSessionPort
from ..use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage, project_cp_scale_canonical_stage, project_cp_scale_canonical_delta,
    canonical_stage_transition_contract, CPScaleCanonicalStageProjection,
)
from ..use_cases.compose_enterprise_reference import EnterpriseReferenceComposition
from ..use_cases.deploy_enterprise_topology import EnterprisePhysicalTopologyDeployer
from ..use_cases.qualify_cp_scale_live import canonical_stage_resume_error
from ..use_cases.reconcile_canonical_stage import canonical_delta_deployment_error, reconcile_canonical_stage_deployment
from ...domain.enterprise.models.physical_deployment import PhysicalDeploymentStatus, PhysicalDeploymentResult
from ...domain.models.plans import TopologyPlan
from ...domain.enterprise.models.deployment import EnvironmentFingerprint
from ...domain.enterprise.models.control_plane import ControlPlaneCapabilityProfile


@dataclass(frozen=True)
class CPScalePhysicalContinuity:
    owned: frozenset[str] = frozenset()
    core_topology: TopologyPlan | None = None
    core_deployment: PhysicalDeploymentResult | None = None


@dataclass(frozen=True)
class CPScaleResumeResult:
    gate: CPScaleResumeGate | None
    error: str


class CPScaleBuildPolicy:
    def __init__(self, *, capabilities: dict[str, ControlPlaneCapabilityProfile], project=project_cp_scale_canonical_stage,
                 delta=project_cp_scale_canonical_delta, transition=canonical_stage_transition_contract,
                 deployer_factory=EnterprisePhysicalTopologyDeployer,
                 reconcile=reconcile_canonical_stage_deployment,
                 ownership_error=canonical_delta_deployment_error, resume_error=canonical_stage_resume_error) -> None:
        self.capabilities = capabilities
        self.project = project
        self.delta = delta
        self.transition = transition
        self.deployer_factory = deployer_factory
        self.reconcile = reconcile
        self.ownership_error = ownership_error
        self.resume_error = resume_error

    def projection(self, composition: EnterpriseReferenceComposition, stage: CPScaleCanonicalStage) -> CPScaleCanonicalStageProjection:
        return self.project(composition, stage, control_plane_capabilities=self.capabilities)

    def statistics_projection(self, composition: EnterpriseReferenceComposition) -> CPScaleCanonicalStageProjection:
        return self.project(composition, CPScaleCanonicalStage.FLOOR1)

    def full_projection(self, composition: EnterpriseReferenceComposition) -> CPScaleCanonicalStageProjection:
        projection = self.project(composition, CPScaleCanonicalStage.REMAINING)
        return projection.__class__(stage=projection.stage, topology=composition.topology,
            configuration=composition.configuration, control_plane=composition.control_plane,
            forwarding_checks=projection.forwarding_checks, voice=composition.voice)

    def resume(self, *, session: CPScaleSessionPort, continuity: CPScaleStageContinuity,
               topology: TopologyPlan, stage: str, full: bool = False) -> CPScaleResumeResult:
        if not session.connected:
            suffix = "full qualification." if full else f"{stage!r}."
            return CPScaleResumeResult(None, "Packet Tracer bridge was not freshly connected before " + suffix)
        observations = (session.physical.observe_workspace(), session.physical.observe_workspace())
        errors = tuple(self.resume_error(continuity.last_workspace, item, topology) for item in observations)
        gate = CPScaleResumeGate(stage, session.status(), observations, errors)
        suffix = "full qualification: " if full else f"{stage!r}: "
        error = "Retained workspace drifted before " + suffix + next(item for item in errors if item) if any(errors) else ""
        return CPScaleResumeResult(gate, error)

    def remaining_projection(self, composition: EnterpriseReferenceComposition,
                             continuity: CPScaleStageContinuity) -> CPScaleCanonicalStageProjection:
        projection = self.projection(composition, CPScaleCanonicalStage.REMAINING)
        delta = self.delta(continuity.previous_projection.topology, projection.topology)
        if delta.devices or delta.modules or delta.links:
            raise CanonicalLiveFailure("The governed remaining-topology reconciliation was not zero-delta.")
        return projection


class CPScalePhysicalStages:
    """Session-bound effects; immutable ownership is supplied by the coordinator."""
    def __init__(self, policy: CPScaleBuildPolicy, session: CPScaleSessionPort,
                 fingerprint: EnvironmentFingerprint) -> None:
        self.policy = policy
        self.session = session
        self.fingerprint = fingerprint
        self.deployer = policy.deployer_factory(session.physical)

    def deploy(self, projection: CPScaleCanonicalStageProjection, delta_topology: TopologyPlan,
               *, first: bool) -> PhysicalDeploymentResult:
        return self.deployer.deploy(delta_topology, environment_fingerprint=self.fingerprint,
            deployment_id="cp-scale-canonical/routing-core" if first else f"cp-scale-canonical/{projection.stage.value}/delta",
            require_empty_workspace=first)

    def cumulative(self, projection: CPScaleCanonicalStageProjection, deployment_id: str,
                   continuity: CPScalePhysicalContinuity) -> PhysicalDeploymentResult:
        return self.policy.reconcile(projection.topology, self.session.physical,
            environment_fingerprint=self.fingerprint, verified_core_topology=continuity.core_topology,
            verified_core_deployment=continuity.core_deployment, deployment_id=deployment_id)

    def require_delta(self, previous: TopologyPlan | None, delta_topology: TopologyPlan,
                      delta: PhysicalDeploymentResult, stage: CPScaleCanonicalStage) -> None:
        error = self.policy.ownership_error(previous, delta_topology, delta)
        if error:
            prefix = "Routing-core ownership was not proven: " if previous is None else f"Physical delta {stage.value!r} lacked session ownership: "
            raise CanonicalLiveFailure(prefix + error)
        if previous is not None and (delta.status is not PhysicalDeploymentStatus.VERIFIED or delta.manifest is None):
            raise CanonicalLiveFailure(f"Physical delta {stage.value!r} was not VERIFIED: " + "; ".join(delta.errors))

    def require_cumulative(self, deployment: PhysicalDeploymentResult, stage: CPScaleCanonicalStage, *, remaining: bool = False) -> None:
        if deployment.status is not PhysicalDeploymentStatus.VERIFIED or deployment.manifest is None:
            prefix = "Remaining canonical topology reconciliation was not VERIFIED: " if remaining else f"Cumulative physical stage {stage.value!r} was not VERIFIED: "
            raise CanonicalLiveFailure(prefix + "; ".join(deployment.errors))
