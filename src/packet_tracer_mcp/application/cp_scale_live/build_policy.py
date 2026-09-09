"""Existing canonical projection/physical policies as a focused collaborator."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from .cleanup import attempted_device_ids
from .contracts import CPScaleStageContinuity, CPScaleObservationRecord
from .errors import CanonicalLiveFailure
from .run_contracts import CPScaleRunReport, CPScaleStageProgress, CPScaleResumeGate
from .run_ports import CPScaleEvidencePort
from .session import CPScaleSessionPort, CPScaleRunObservationPort
from ..use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage, CPScaleCanonicalTarget, project_cp_scale_canonical_stage,
    project_cp_scale_canonical_delta, canonical_stage_transition_contract,
    CPScaleCanonicalStageProjection,
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

    def resume(self, *, session: CPScaleSessionPort, report: CPScaleRunReport,
               continuity: CPScaleStageContinuity, topology: TopologyPlan, stage: str, full: bool = False) -> None:
        if not session.connected:
            suffix = "full qualification." if full else f"{stage!r}."
            raise CanonicalLiveFailure("Packet Tracer bridge was not freshly connected before " + suffix)
        observations = (session.physical.observe_workspace(), session.physical.observe_workspace())
        errors = tuple(self.resume_error(continuity.last_workspace, item, topology) for item in observations)
        report.resume_gates += (CPScaleResumeGate(stage, session.status(), observations, errors),)
        if any(errors):
            suffix = "full qualification: " if full else f"{stage!r}: "
            raise CanonicalLiveFailure("Retained workspace drifted before " + suffix + next(item for item in errors if item))


class CPScalePhysicalStages:
    """One build sequence owns its immutable physical continuity snapshots."""
    def __init__(self, policy: CPScaleBuildPolicy, session: CPScaleSessionPort,
                 evidence: CPScaleEvidencePort, observations: CPScaleRunObservationPort, fingerprint: EnvironmentFingerprint) -> None:
        self.policy = policy
        self.session = session
        self.evidence = evidence
        self.observations = observations
        self.fingerprint = fingerprint
        self.deployer = policy.deployer_factory(session.physical)
        self.state = CPScalePhysicalContinuity()

    def cumulative(self, projection: CPScaleCanonicalStageProjection, deployment_id: str) -> PhysicalDeploymentResult:
        return self.policy.reconcile(projection.topology, self.session.physical,
            environment_fingerprint=self.fingerprint, verified_core_topology=self.state.core_topology,
            verified_core_deployment=self.state.core_deployment, deployment_id=deployment_id)

    def prepare(self, projection: CPScaleCanonicalStageProjection, continuity: CPScaleStageContinuity,
                report: CPScaleRunReport) -> tuple[PhysicalDeploymentResult, PhysicalDeploymentResult, tuple[CPScaleObservationRecord, ...]]:
        stage = projection.stage
        first = continuity.previous_projection is None
        report.active_stage = CPScaleStageProgress(projection)
        self.observations.activate(projection)
        boundaries = ()
        if first:
            delta_topology = projection.topology
        else:
            previous = continuity.previous_projection
            self.policy.resume(session=self.session, report=report, continuity=continuity, topology=previous.topology, stage=stage.value)
            boundary = self.observations.before_delta(previous)
            boundaries = (boundary,)
            report.network_boundaries += ((stage.value, boundary),)
            delta_topology = self.policy.delta(previous.topology, projection.topology)
            if report.preflight.target.target is CPScaleCanonicalTarget.ROUTER0_BRANCH and stage is CPScaleCanonicalStage.ROUTER0_BRANCH:
                transition = self.policy.transition(previous, projection)
                report.active_stage = replace(report.active_stage, transition=transition)
                report.router0_transition = transition
                self.evidence.write_progress(report)
                if previous.stage is not CPScaleCanonicalStage.FLOOR3 or not transition.mutation_scope_disjoint:
                    raise CanonicalLiveFailure("Router0 target refused its incremental boundary: " + transition.claim)
        delta = self.deployer.deploy(delta_topology, environment_fingerprint=self.fingerprint,
            deployment_id="cp-scale-canonical/routing-core" if first else f"cp-scale-canonical/{stage.value}/delta",
            require_empty_workspace=first)
        report.active_stage = replace(report.active_stage, delta=delta)
        self.state = replace(self.state, owned=self.state.owned | attempted_device_ids(delta))
        self.evidence.write_progress(report)
        error = self.policy.ownership_error(None if first else continuity.previous_projection.topology, delta_topology, delta)
        if error:
            prefix = "Routing-core ownership was not proven: " if first else f"Physical delta {stage.value!r} lacked session ownership: "
            raise CanonicalLiveFailure(prefix + error)
        if first:
            deployment = delta
            self.state = replace(self.state, core_deployment=deployment, core_topology=projection.topology)
        else:
            if delta.status is not PhysicalDeploymentStatus.VERIFIED or delta.manifest is None:
                raise CanonicalLiveFailure(f"Physical delta {stage.value!r} was not VERIFIED: " + "; ".join(delta.errors))
            deployment = self.cumulative(projection, f"cp-scale-canonical/{stage.value}/cumulative")
        report.active_stage = replace(report.active_stage, deployment=deployment)
        self.evidence.write_progress(report)
        if deployment.status is not PhysicalDeploymentStatus.VERIFIED or deployment.manifest is None:
            raise CanonicalLiveFailure(f"Cumulative physical stage {stage.value!r} was not VERIFIED: " + "; ".join(deployment.errors))
        return deployment, delta, boundaries

    def remaining(self, composition: EnterpriseReferenceComposition, continuity: CPScaleStageContinuity,
                  report: CPScaleRunReport) -> CPScaleCanonicalStageProjection:
        projection = self.policy.projection(composition, CPScaleCanonicalStage.REMAINING)
        delta = self.policy.delta(continuity.previous_projection.topology, projection.topology)
        if delta.devices or delta.modules or delta.links:
            raise CanonicalLiveFailure("The governed remaining-topology reconciliation was not zero-delta.")
        deployment = self.cumulative(projection, "cp-scale-canonical/remaining/reconciliation")
        if deployment.status is not PhysicalDeploymentStatus.VERIFIED or deployment.manifest is None:
            raise CanonicalLiveFailure("Remaining canonical topology reconciliation was not VERIFIED: " + "; ".join(deployment.errors))
        report.stages += (CPScaleStageProgress(projection, deployment=deployment, remaining=True),)
        return projection
