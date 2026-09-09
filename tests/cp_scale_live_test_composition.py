"""Test-only explicit composition of Level A effects; no production imports."""
from __future__ import annotations


OFFLINE_COMPOSITION = r'''
from packet_tracer_mcp.application.cp_scale_live.backend import CPScaleBackendQualification
from packet_tracer_mcp.application.cp_scale_live.build_policy import CPScaleBuildPolicy
from packet_tracer_mcp.application.cp_scale_live.checkpoint import CPScaleCheckpointDecision
from packet_tracer_mcp.application.cp_scale_live.completion import CPScaleCompletion
from packet_tracer_mcp.application.cp_scale_live.coordinator import CPScaleLiveCoordinator
from packet_tracer_mcp.application.cp_scale_live.errors import CPScaleStageFailure
from packet_tracer_mcp.application.cp_scale_live.run_contracts import CPScaleCleanupResult, CPScaleCleanupRealtime
from packet_tracer_mcp.application.cp_scale_live.session import CPScaleRuntimeResources
from packet_tracer_mcp.infrastructure.execution.cp_scale_live_session import PacketTracerCPScaleSession
from packet_tracer_mcp.infrastructure.persistence.cp_scale_run_evidence import run_evidence, attestation_evidence
from packet_tracer_mcp.infrastructure.observation.cp_scale_live_run import PacketTracerCPScaleRunObservations, CPScaleActiveProjection


class Evidence:
    def write_progress(self, report):
        seams._write_evidence(run_evidence(report))

    def checkpoint(self, stage, report, *, final=False):
        kwargs = {"destination": live.FINAL_CHECKPOINT_PATH} if final else {}
        seams._write_checkpoint_summary(stage, run_evidence(report), **kwargs)

    def archive(self, phase, payload, *, run_identity):
        serialized = run_evidence(payload) if hasattr(payload, "preflight") else attestation_evidence(payload)
        return seams.archive_cp_scale_canonical_evidence(serialized,
            base_dir=live.CANONICAL_EVIDENCE_DIR, run_identity=run_identity, phase=phase)


class Checkpoint:
    def decide(self, stage, report, *, session_source_head):
        return CPScaleCheckpointDecision(seams._checkpoint(stage, run_evidence(report), session_source_head=session_source_head))


class Cleanup:
    def restore(self, physical, topology, owned, baseline):
        value = seams._cleanup_owned(physical, topology, owned, baseline)
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
            return CPScaleCleanupRealtime(not error, error, value)
        except Exception as exc:
            return CPScaleCleanupRealtime(False, f"{type(exc).__name__}: {exc}")


coordinators = []
sessions = []
stage_requests = []


def offline_coordinator(request, **kwargs):
    persistence = Evidence()
    presentation = live.CPScaleConsolePresentation(live.EVIDENCE_PATH)

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
        completion=CPScaleCompletion(evidence=persistence, presentation=presentation, cleanup=Cleanup()),
        baseline_policy=seams.disposable_workspace_error)
    coordinators.append(coordinator)
    return coordinator


live._build_coordinator = offline_coordinator
'''


TERMINAL_FIXTURE = r'''
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from packet_tracer_mcp.application.cp_scale_live.completion import CPScaleCompletion
from packet_tracer_mcp.application.cp_scale_live.run_contracts import (
    CPScaleRunReport, CPScaleFinalizationState, CPScaleStageProgress,
    CPScaleCleanupResult, CPScaleCleanupRealtime,
)
from packet_tracer_mcp.infrastructure.persistence.cp_scale_run_evidence import cleanup_evidence, realtime_evidence, replay_evidence


def _complete_router0_target(*, evidence, target_contract, physical, full_topology,
                             owned_device_ids, baseline, observe_cleanup_realtime,
                             archive, run_identity, session_source_head):
    # Fixture translation only. The real typed completion owns every decision
    # and side-effect sequence; no product function is replaced by this helper.
    stages = []
    for item in evidence.get("stages", []):
        checks = tuple(SimpleNamespace(**check) for check in item["plan"]["branch_forwarding_checks"])
        by_id = {check.id: check for check in checks}
        site = tuple(SimpleNamespace(check=by_id.get(row["check"]["id"]), verified=row["verified"])
                     for row in item["site_forwarding"])
        audit = item.get("mutation_replay_audit")
        typed_audit = None if audit is None else SimpleNamespace(
            verified=audit["verified"], claim=audit["claim"], surfaces=tuple(
                SimpleNamespace(replayed_retained_ids=row.get("replayed_retained_ids", ()))
                for row in audit.get("surfaces", [])))
        stage = live.CPScaleCanonicalStage(item["stage"])
        projection = SimpleNamespace(stage=stage)
        result = SimpleNamespace(stage=stage, outcome="verified" if item["verified"] else "failed",
            replay_audit=typed_audit, report=SimpleNamespace(
                forwarding=SimpleNamespace(site_verified=item["site_forwarding_verified"], site=site),
                site_forwarding_checks=checks, workspace_verified=item["workspace_verified_twice"]))
        stages.append(CPScaleStageProgress(projection, result=result))
    report = CPScaleRunReport(SimpleNamespace(target=target_contract, identity=SimpleNamespace(source_head=session_source_head)),
        run_identity, datetime.now(timezone.utc), "9.0.1.0858", stages=tuple(stages),
        live_devices=evidence.get("live_devices"), live_links=evidence.get("live_links"), baseline=baseline)

    class Persistence:
        def write_progress(self, report):
            seams._write_evidence(evidence)
        def checkpoint(self, stage, report, **kwargs):
            seams._write_checkpoint_summary(stage, evidence)
        def archive(self, phase, payload, **kwargs):
            value = archive(phase, payload)
            return SimpleNamespace(model_dump=lambda mode: value)

    class Cleanup:
        def restore(self, *args):
            value = seams._cleanup_owned(*args)
            return CPScaleCleanupResult(value["verified"], value.get("restoration_error", ""),
                first=SimpleNamespace(compact_summary=lambda: value["first"]) if "first" in value else None,
                second=SimpleNamespace(compact_summary=lambda: value["second"]) if "second" in value else None)

    class Observations:
        def cleanup_realtime(self):
            value = observe_cleanup_realtime()
            return CPScaleCleanupRealtime(value["verified"], value.get("error", ""), value.get("state"))

    completion = CPScaleCompletion(evidence=Persistence(), cleanup=Cleanup(),
        presentation=live.CPScaleConsolePresentation(live.EVIDENCE_PATH))
    try:
        completion.complete(report=report, state=CPScaleFinalizationState(),
            session=SimpleNamespace(physical=physical), composition=SimpleNamespace(topology=full_topology),
            owned=owned_device_ids, observations=Observations(), router0=True)
    finally:
        evidence["closure"] = report.closure
        evidence["closure_scope"] = report.closure_scope
        if report.no_mutation_replay is not None:
            evidence["no_mutation_replay"] = replay_evidence(report.no_mutation_replay)
    return {"precleanup_archive": report.canonical_evidence_precleanup.model_dump(mode="json"),
        "cleanup": cleanup_evidence(report.cleanup), "cleanup_realtime": realtime_evidence(report.cleanup_realtime),
        "cleanup_attestation": report.cleanup_attestation.model_dump(mode="json")}
'''
