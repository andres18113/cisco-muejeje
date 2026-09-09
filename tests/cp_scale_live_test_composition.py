"""Test-only explicit composition of Level A effects; no production imports."""
from __future__ import annotations


OFFLINE_COMPOSITION = r'''
import os
from datetime import datetime, timezone
from pathlib import Path
from packet_tracer_mcp.application.cp_scale_live.backend import CPScaleBackendQualification
from packet_tracer_mcp.application.cp_scale_live.build_policy import CPScaleBuildPolicy
from packet_tracer_mcp.application.cp_scale_live.checkpoint import CPScaleCheckpointDecision
from packet_tracer_mcp.application.cp_scale_live.checkpoint import CPScaleCheckpointPrepared, CPScaleCheckpointResumption
from packet_tracer_mcp.application.cp_scale_live.completion import CPScaleCompletion
from packet_tracer_mcp.application.cp_scale_live.coordinator import CPScaleLiveCoordinator
from packet_tracer_mcp.application.cp_scale_live.errors import CPScaleStageFailure
from packet_tracer_mcp.application.cp_scale_live.run_contracts import CPScaleCleanupResult, CPScaleCleanupRealtime
from packet_tracer_mcp.application.cp_scale_live.session import CPScaleRuntimeResources
from packet_tracer_mcp.infrastructure.execution.cp_scale_live_session import PacketTracerCPScaleSession
from packet_tracer_mcp.infrastructure.persistence.cp_scale_run_evidence import run_evidence, attestation_evidence
from packet_tracer_mcp.infrastructure.persistence.cp_scale_live import CPScaleLivePersistence
from packet_tracer_mcp.infrastructure.observation.cp_scale_live_run import PacketTracerCPScaleRunObservations, CPScaleActiveProjection, cleanup_realtime_state

test_persistence = CPScaleLivePersistence(Path(os.environ["PT_MCP_GOVERNED_ROOT"]))


class Evidence:
    def write_progress(self, report):
        seams._write_evidence(run_evidence(report))

    def checkpoint(self, stage, report, *, final=False):
        kwargs = {"destination": test_persistence.final_checkpoint_path} if final else {}
        seams._write_checkpoint_summary(stage, run_evidence(report), **kwargs)

    def archive(self, phase, payload, *, run_identity):
        serialized = run_evidence(payload) if hasattr(payload, "preflight") else attestation_evidence(payload)
        return seams.archive_cp_scale_canonical_evidence(serialized,
            base_dir=test_persistence.archive_dir, run_identity=run_identity, phase=phase)


class Checkpoint:
    def prepare(self, stage):
        return CPScaleCheckpointPrepared(stage, datetime.now(timezone.utc), None)

    def publish_and_prompt(self, prepared, publication):
        return CPScaleCheckpointDecision(seams._checkpoint(prepared.stage, run_evidence(publication),
            session_source_head=publication.preflight.identity.source_head))

    def resume(self, session_source_head):
        return CPScaleCheckpointResumption(None, "")

    def publish_resumed(self, resumed, publication):
        pass


class Cleanup:
    def restore(self, physical, topology, owned, baseline):
        try:
            value = seams._cleanup_owned(physical, topology, owned, baseline)
        except Exception as exc:
            return CPScaleCleanupResult(False, error=f"{type(exc).__name__}: {exc}")
        return CPScaleCleanupResult(value["verified"], value.get("restoration_error", ""), error=value.get("error", ""))


class Observations:
    def __init__(self, session):
        self.session = session

    def activate(self, projection):
        pass

    def before_delta(self, projection):
        from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleObservationRecord
        return CPScaleObservationRecord("network_state", projection.stage, "coordinator", "observed",
            seams._network_state_observation(None, projection, boundary="before_physical_delta"))

    def dhcp_target(self, projection):
        return seams._voice_dhcp_statistics_target(projection.configuration, projection.voice)

    def dhcp_baseline(self, target):
        return PacketTracerCPScaleRunObservations(self.session.transport, CPScaleActiveProjection()).dhcp_baseline(target)

    def cleanup_realtime(self):
        try:
            value = seams._voice_window_state(None)
            error = seams._realtime_boundary_error(value, "after cleanup")
            return CPScaleCleanupRealtime(not error, error, cleanup_realtime_state(value))
        except Exception as exc:
            return CPScaleCleanupRealtime(False, f"{type(exc).__name__}: {exc}")


coordinators = []
sessions = []
stage_requests = []


def offline_coordinator(request, **kwargs):
    persistence = Evidence()
    presentation = live.CPScaleConsolePresentation(test_persistence.evidence_path)

    def session_factory():
        session = PacketTracerCPScaleSession(transport_factory=seams.PacketTracerHttpTransport,
            physical_factory=lambda transport: seams.PacketTracerPhysicalTopologyRuntime(),
            runtime_factory=lambda transport, physical: CPScaleRuntimeResources(
                seams.PacketTracerEnterpriseConfigurationRuntime(), seams.PacketTracerEnterpriseControlPlaneRuntime(),
                seams.PacketTracerEnterpriseVoiceRuntime()))
        sessions.append(session)
        return session

    def stage_factory(session, resources):
        inner = seams._build_stage_executor()
        def execute(request):
            stage_requests.append(request)
            if seams._execute_stage is not None:
                return seams._execute_stage(request.projection, site_forwarding_checks=request.site_forwarding_checks)
            return inner.execute(request)
        return SimpleNamespace(execute=execute)

    build = CPScaleBuildPolicy(capabilities=(), project=seams.project_cp_scale_canonical_stage,
        delta=seams.project_cp_scale_canonical_delta, transition=seams.canonical_stage_transition_contract,
        deployer_factory=seams.EnterprisePhysicalTopologyDeployer,
        reconcile=seams.reconcile_canonical_stage_deployment,
        ownership_error=seams.canonical_delta_deployment_error, resume_error=seams.canonical_stage_resume_error)
    build.full_projection = seams._full_qualification_projection
    coordinator = CPScaleLiveCoordinator(preflight=seams._build_local_preflight(), session_factory=session_factory,
        stage_factory=stage_factory, observations_factory=Observations, build=build,
        backend=CPScaleBackendQualification(compose=seams.compose_cp_scale_canonical,
            discovery_factory=lambda session, version: object(), requirements=seams.canonical_required_capability_probes,
            restoration_error=seams.canonical_cleanup_restoration_error),
        checkpoint=Checkpoint(), persistence=persistence, presentation=presentation,
        completion=CPScaleCompletion(cleanup=Cleanup()),
        baseline_policy=seams.disposable_workspace_error)
    coordinators.append(coordinator)
    return coordinator


live.build_coordinator = offline_coordinator
'''
