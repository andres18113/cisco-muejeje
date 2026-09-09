"""Compatibility views of typed run facts. No orchestration or acceptance."""
from __future__ import annotations

from dataclasses import asdict

from ...application.cp_scale_live import CPScaleCheckState, process_record_mapping
from ...application.cp_scale_live.run_contracts import (
    CPScaleCleanupAttestation, CPScaleCleanupResult, CPScaleCleanupRealtime,
    CPScaleRunReport, CPScaleRunReplayAudit, CPScaleStageProgress,
    CPScaleBridgeStatus,
)
from .cp_scale_stage_evidence import realtime_state_evidence, stage_result_evidence


def transition_evidence(transition):
    return {**asdict(transition), "previous_stage": transition.previous_stage.value,
            "current_stage": transition.current_stage.value,
            "mutation_scope_disjoint": transition.mutation_scope_disjoint, "claim": transition.claim}


def bridge_evidence(status: CPScaleBridgeStatus) -> dict[str, object]:
    value: dict[str, object] = {"connected": status.connected}
    if status.last_poll_reported:
        value["last_poll_ago"] = status.last_poll_ago
    for name in ("unauth_recent", "unauth_count", "token_id", "file_bridge_alive"):
        if getattr(status, name) is not None:
            value[name] = getattr(status, name)
    if status.unauth_paths is not None:
        value["unauth_paths"] = list(status.unauth_paths)
    if status.client_headers is not None:
        value["client_headers"] = dict(status.client_headers)
    return value


def cleanup_evidence(result: CPScaleCleanupResult) -> dict[str, object]:
    value: dict[str, object] = {"verified": result.verified}
    if result.error:
        value["error"] = result.error
    if result.restoration_error or not result.error:
        value["restoration_error"] = result.restoration_error
    if result.mutations is not None:
        value["mutations"] = [item.model_dump(mode="json") for item in result.mutations]
    if result.first is not None:
        value["first"] = result.first.compact_summary()
    if result.second is not None:
        value["second"] = result.second.compact_summary()
    return value


def realtime_evidence(result: CPScaleCleanupRealtime) -> dict[str, object]:
    return {"state": realtime_state_evidence(result.state), "error": result.error, "verified": result.verified}


def replay_evidence(result: CPScaleRunReplayAudit) -> dict[str, object]:
    return {"claim": "NO_MUTATION_REPLAY" if result.verified else "MUTATION_REPLAY_DETECTED",
            "verified": result.verified, "audited_stages": list(result.audited_stages),
            "stages_without_verified_audit": list(result.stages_without_verified_audit),
            "replayed_retained_ids": list(result.replayed_retained_ids)}


def stage_progress_evidence(progress: CPScaleStageProgress) -> dict[str, object]:
    projection = progress.projection
    if progress.failure_details is not None:
        failure = progress.failure_details
        return {"stage": failure.stage, "first_failed_boundary": failure.first_failed_boundary,
                "stage_outcome": "failed"}
    if progress.remaining:
        return {"stage": projection.stage.value, "physical_delta": {"devices": 0, "modules": 0, "links": 0},
                "physical": progress.deployment.model_dump(mode="json"), "verified": True,
                "verification_scope": "ZERO_DELTA_RECONCILED"}
    if progress.result is not None:
        value = stage_result_evidence(progress.result)
    else:
        value = {"stage": projection.stage.value, "plan": {
            "topology_hash": projection.topology.physical_identity_hash,
            "configuration_hash": projection.configuration.semantic_hash,
            "control_plane_hash": projection.control_plane.semantic_hash,
            "devices": len(projection.topology.devices), "links": len(projection.topology.links),
        }, "stage_outcome": "in_progress"}
        if progress.delta is not None:
            value["physical_delta"] = progress.delta.model_dump(mode="json")
        if progress.deployment is not None:
            value["physical"] = progress.deployment.model_dump(mode="json")
        if progress.transition is not None:
            value["transition_contract"] = transition_evidence(progress.transition)
    if progress.dhcp_baseline is not None:
        value["dhcp_voice_statistics_baseline"] = progress.dhcp_baseline.evidence
    if progress.failed:
        value["stage_outcome"] = "failed"
    return value


def run_evidence(report: CPScaleRunReport) -> dict[str, object]:
    preflight = report.preflight
    target = preflight.target
    value: dict[str, object] = {
        "schema": "cp-scale-canonical-voice-live-v1", "run_identity": report.run_identity,
        "started_at": report.started_at.isoformat(), "packet_tracer_version": report.packet_tracer_version,
        "python_executable": preflight.runtime.python_executable, "package_file": preflight.runtime.package_file,
        "loaded_namespaces": list(preflight.runtime.loaded_namespaces), "target_stage": target.target.value,
        "target_contract": {"build_stages": [stage.value for stage in target.build_stages],
            "terminal_stage": target.terminal_stage.value,
            "run_remaining_reconciliation": target.run_remaining_reconciliation,
            "run_full_qualification": target.run_full_qualification, "allow_retention": target.allow_retention,
            "precleanup_closure": target.precleanup_closure, "cleaned_closure": target.cleaned_closure},
        "stages": [stage_progress_evidence(stage) for stage in report.stages],
        "presentation_retained": report.presentation_retained,
    }
    if preflight.import_isolation.state is not CPScaleCheckState.NOT_RUN:
        value["import_isolation"] = {"state": preflight.import_isolation.isolation_state, "detail": preflight.import_isolation.detail}
    if preflight.repository.state is not CPScaleCheckState.NOT_RUN:
        value["repository"] = {"branch": preflight.repository.branch, "upstream": preflight.repository.upstream,
                               "head": preflight.repository.head, "error": preflight.repository.error}
        if preflight.repository.upstream_head_error:
            value["initial_upstream_error"] = preflight.repository.upstream_head_error
    if preflight.process.state is not CPScaleCheckState.NOT_RUN:
        value["packet_tracer_processes"] = [process_record_mapping(item) for item in preflight.process.processes]
    for name in ("hard_stop", "failure", "closure_scope", "closure",
                 "precleanup_archive_error", "cleanup_archive_error", "checkpoint"):
        if getattr(report, name):
            value[name] = getattr(report, name)
    if report.final_disposition is not None:
        value["final_disposition"] = report.final_disposition.value
    if report.http_bridge is not None:
        value["http_bridge"] = bridge_evidence(report.http_bridge)
    for name in ("live_devices", "live_links"):
        if getattr(report, name) is not None:
            value[name] = getattr(report, name)
    if report.capability_prequalification is not None:
        qualification = report.capability_prequalification
        sessions = [{"model": probe.model, "required": list(probe.required), "cached": probe.cached,
            "summary": probe.snapshot.compact_summary(), "results": [item.model_dump(mode="json")
                for item in probe.snapshot.session.results if item.capability in probe.required],
            "error": probe.error} for probe in qualification.sessions]
        structured = (
            qualification.first is not None
            or qualification.second is not None
            or qualification.unresolved is not None
            or bool(qualification.restoration_error)
        )
        if not structured:
            value["capability_prequalification"] = sessions
        else:
            value["capability_prequalification"] = {
                "requirements": {model: list(capabilities) for model, capabilities in qualification.requirements},
                "sessions": sessions,
                "workspace_first": qualification.first.compact_summary() if qualification.first is not None else None,
                "workspace_second": qualification.second.compact_summary() if qualification.second is not None else None,
                "restoration_error": qualification.restoration_error,
            }
            if qualification.unresolved is not None:
                value["capability_prequalification"]["unresolved_after_composition"] = list(qualification.unresolved)
    if report.checkpoint_repository is not None:
        value["checkpoint_repository"] = report.checkpoint_repository.model_dump(mode="json")
    if report.checkpoint_resume_repository is not None:
        resumed = report.checkpoint_resume_repository
        value["checkpoint_resume_repository"] = {**resumed.repository.model_dump(mode="json"),
            "upstream_head": resumed.upstream_head, "dirty": resumed.dirty,
            "governed_source_changed": resumed.governed_source_changed}
    for name in ("completed_at", "cleanup_completed_at", "checkpoint_at"):
        if getattr(report, name) is not None:
            value[name] = getattr(report, name).isoformat()
    if report.baseline is not None:
        value["baseline"] = report.baseline.compact_summary()
    if report.active_stage is not None:
        value["active_stage"] = stage_progress_evidence(report.active_stage)
    if report.router0_transition is not None:
        value["router0_transition_contract"] = transition_evidence(report.router0_transition)
    if report.full_qualification is not None:
        value["full_qualification"] = {**stage_result_evidence(report.full_qualification), "stage": "full-qualification"}
    if report.resume_gates:
        value["resume_gates"] = [{"before_stage": gate.before_stage, "bridge": bridge_evidence(gate.bridge),
            "observations": [item.compact_summary() for item in gate.observations], "errors": list(gate.errors)} for gate in report.resume_gates]
    if report.network_boundaries:
        value["network_state_boundaries"] = [{"before_stage": stage, **item.evidence} for stage, item in report.network_boundaries]
    if report.no_mutation_replay is not None:
        value["no_mutation_replay"] = replay_evidence(report.no_mutation_replay)
    if report.cleanup is not None:
        value["cleanup"] = cleanup_evidence(report.cleanup)
    if report.cleanup_realtime is not None:
        value["cleanup_realtime"] = realtime_evidence(report.cleanup_realtime)
    for name in ("canonical_evidence_precleanup", "cleanup_attestation"):
        if getattr(report, name) is not None:
            value[name] = getattr(report, name).model_dump(mode="json")
    if report.archives:
        value["archives"] = [item.model_dump(mode="json") for item in report.archives]
    if report.finalization_errors:
        value["finalization_errors"] = list(report.finalization_errors)
    return value


def attestation_evidence(attestation: CPScaleCleanupAttestation) -> dict[str, object]:
    value = {"schema": "cp-scale-canonical-cleanup-attestation-v1", "run_identity": attestation.run_identity,
             "source_head": attestation.source_head,
             "canonical_evidence_precleanup": attestation.precleanup.model_dump(mode="json") if attestation.precleanup else None,
             "cleanup": cleanup_evidence(attestation.cleanup) if attestation.cleanup else None,
             "cleanup_realtime": realtime_evidence(attestation.realtime), "cleanup_completed_at": attestation.completed_at.isoformat()}
    if attestation.failure is not None:
        value["failure"] = attestation.failure
    for name in ("closure", "target_stage", "closure_scope"):
        if getattr(attestation, name):
            value[name] = getattr(attestation, name)
    if attestation.replay is not None:
        value["no_mutation_replay"] = replay_evidence(attestation.replay)
    return value
