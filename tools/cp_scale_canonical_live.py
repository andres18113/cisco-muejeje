"""Governed persistent LIVE construction of the canonical CP-SCALE topology.

The process deliberately stays alive across every checkpoint because physical
cleanup ownership is runtime-instance-local.  It begins only from a completely
observed empty workspace, advances through the exact cumulative product stages,
and archives the final evidence before verified cleanup. Explicitly authorized
presentation retention remains available after the full 314-device/219-link
plans are independently VERIFIED. Any failure or operator abort cleans every
device this session attempted and requires two fresh empty-baseline observations.

No raw IOS, JavaScript, or bridge command is accepted from the operator.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import ipaddress
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import packet_tracer_mcp

from packet_tracer_mcp.application.cp_scale_live import (
    CPScaleCheckState,
    CPScaleLiveRequest,
    CPScaleLocalPreflight,
    CPScalePreflightOutcome,
    process_record_mapping,
)
from packet_tracer_mcp.application.use_cases.apply_configuration import (
    ConfigurationApplicator,
)
from packet_tracer_mcp.application.use_cases.apply_control_plane import (
    ControlPlaneApplicator,
)
from packet_tracer_mcp.application.use_cases.apply_voice import VoiceApplicator
from packet_tracer_mcp.application.use_cases.capability_discovery import (
    CapabilityDiscoveryService,
)
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    CPScaleCanonicalTarget,
    canonical_cp_scale_target_contract,
    canonical_stage_configuration_mutation_ids,
    canonical_stage_control_plane_mutation_ids,
    canonical_stage_transition_contract,
    canonical_stage_voice_mutation_ids,
    compose_cp_scale_canonical,
    project_cp_scale_canonical_delta,
    project_cp_scale_canonical_stage,
)
from packet_tracer_mcp.application.use_cases.deploy_enterprise_topology import (
    EnterprisePhysicalTopologyDeployer,
    disposable_workspace_error,
)
from packet_tracer_mcp.application.use_cases.foundational_evidence import (
    derive_foundational_hashes,
    derive_foundational_statuses,
)
from packet_tracer_mcp.application.use_cases.execute_enterprise_reference import (
    configuration_application_contradiction,
)
from packet_tracer_mcp.application.use_cases.observe_serial_orientation import (
    SerialOrientationObserver,
    inherit_verified_serial_orientation,
)
from packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    CPScaleFinalDisposition,
    CanonicalMutationSurfaceObservation,
    EXPECTED_BRANCH,
    EXPECTED_UPSTREAM,
    archive_cp_scale_canonical_evidence,
    canonical_capability_probe_error,
    canonical_bridge_polling_error,
    canonical_cp_scale_voice_evidence,
    canonical_checkpoint_repository_error,
    canonical_cleanup_restoration_error,
    canonical_configuration_reread_scope,
    canonical_configuration_retryable_operational_unknown,
    canonical_final_disposition,
    canonical_required_capability_probes,
    canonical_stage_configuration_error,
    canonical_stage_mutation_replay_audit,
    canonical_stage_resume_error,
    canonical_stage_workspace_error,
    read_git_repository_state,
)
from packet_tracer_mcp.application.use_cases.reconcile_canonical_stage import (
    canonical_delta_deployment_error,
    reconcile_canonical_stage_deployment,
)
from packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
    ConfigurationPhase,
    ConfigureAccessPort,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
    ConfigurationRuntimeContext,
)
from packet_tracer_mcp.domain.enterprise.models.voice_runtime import (
    VoiceApplicationResult,
)
from packet_tracer_mcp.domain.enterprise.models.deployment import (
    EnvironmentFingerprint,
)
from packet_tracer_mcp.domain.enterprise.models.discovery import (
    ProbeLevel,
    ProbeRequest,
)
from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentItemStatus,
    PhysicalDeploymentStatus,
    PhysicalObjectKind,
)
from packet_tracer_mcp.infrastructure.catalog.control_plane_capabilities import (
    packet_tracer_control_plane_capabilities,
)
from packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_control_plane_runtime import (
    PacketTracerEnterpriseControlPlaneRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_voice_runtime import (
    PacketTracerEnterpriseVoiceRuntime,
)
from packet_tracer_mcp.infrastructure.execution.command_dispatch import (
    DispatchClassification,
    is_command_corrupted,
)
from packet_tracer_mcp.infrastructure.execution.cp_scale_live_preflight import (
    GitCPScaleRepositoryReader,
    PacketTracerImportIsolationReader,
    PowerShellPacketTracerProcessReader,
    PythonRuntimeEvidenceReader,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
    OperationalQueryId,
    PagerContinuation,
    classify_show_spanning_tree,
    ios_rejection_reason,
    parse_show_ip_dhcp_binding,
    parse_show_ip_dhcp_server_statistics,
    parse_show_ip_interface_brief,
    parse_show_interfaces_trunk,
    parse_show_spanning_tree,
)
from packet_tracer_mcp.infrastructure.execution.file_bridge import FileBridge
from packet_tracer_mcp.infrastructure.execution.frame_observer_probe import (
    CHILD_TAG_FIELDS,
    MAX_FRAME_TARGETS,
    MAX_VLAN_CONTROL_TARGETS,
    PacketTracerFrameObserverProbe,
)
from packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (
    TRACE_LIMIT_MAX,
    SimulationTraceRuntime,
)
from packet_tracer_mcp.infrastructure.execution.live_bridge import (
    PacketTracerHttpTransport,
)
from packet_tracer_mcp.infrastructure.execution.live_environment_preflight import (
    packet_tracer_process_error,
)
from packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
)
from packet_tracer_mcp.infrastructure.execution.probe_runtime import (
    PacketTracerBridgeProbeRuntime,
)
from packet_tracer_mcp.infrastructure.execution.serial_orientation_runtime import (
    PacketTracerSerialOrientationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.typed_ping import (
    TypedPingExecutor,
)
from packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)
from packet_tracer_mcp.shared.utils import (
    same_interface_name,
    serialize_typed_ping_evidence,
)


from packet_tracer_mcp.application.cp_scale_live.contracts import (
    CPScaleLiveStageResult, CPScaleStageExecutionInput, CPScaleStageContinuity, CPScaleObservationRecord,
    CPScaleDhcpStatisticsTarget,
)
from packet_tracer_mcp.application.cp_scale_live.configuration_stage import CPScaleConfigurationStage
from packet_tracer_mcp.application.cp_scale_live.voice_stage import CPScaleVoiceStage
from packet_tracer_mcp.application.cp_scale_live.control_plane_stage import CPScaleControlPlaneStage
from packet_tracer_mcp.application.cp_scale_live.forwarding_stage import CPScaleForwardingStage
from packet_tracer_mcp.application.cp_scale_live.reconciliation import CPScaleReconciliation
from packet_tracer_mcp.application.cp_scale_live.stage_executor import CPScaleStageExecutor
from packet_tracer_mcp.infrastructure.observation.cp_scale_live import (
    PacketTracerCPScaleObservations,
    _core_serial_addresses,
    _wait_for_serial_interfaces,
    _wait_for_core_forwarding,
    _wait_for_site_forwarding,
    _dhcp_server_binding_evidence,
    _scoped_dhcp_subinterface,
    _voice_dhcp_statistics_target,
    _dhcp_server_statistics_observation,
    _dhcp_server_statistics_point,
    _scope_observation,
    _DHCP_STATISTIC_COUNTERS,
    _dhcp_counter_delta,
    _dhcp_server_statistics_delta,
    _voice_binding_count,
    _simulation_state_dict,
    _simulation_mode_dict,
    _simulation_step_dict,
    _voice_window_state,
    _realtime_boundary_error,
    _STP_FORWARDING_STATE,
    _STP_BLOCKING_STATE,
    _phone_edge_port_derivation,
    _phone_edge_ports,
    _stp_source_error,
    _stp_port_observation,
    _STP_MAX_LOGICAL_ATTEMPTS,
    _stp_attempt,
    _stp_retry_refusal,
    _stp_logical_observation,
    _stp_realtime_evidence,
    _network_trunk_expectations,
    _stp_network_device_evidence,
    _network_state_observation,
)
from packet_tracer_mcp.infrastructure.diagnostics.cp_scale_live import (
    PacketTracerCPScaleDiagnostics,
    _SIMULATION_TARGET_TIME_SPAN,
    _SIMULATION_STEP_BATCH_SIZE,
    _SIMULATION_HARD_MAX_STEPS,
    _SIMULATION_HARD_WALL_CLOCK_SECONDS,
    _SIMULATION_GLOBAL_EVENT_LIST_CEILING,
    _SIMULATION_STALL_BATCH_LIMIT,
    _REPRESENTATIVE_PHONE_NAME,
    _REPRESENTATIVE_SWITCH_NAME,
    _CONTROL_ENDPOINT_NAME,
    _VOICE_GATEWAY_NAME,
    _PHONE_PREREQUISITES,
    _endpoint_attachment,
    _representative_phone_evidence,
    _progression_evidence,
    _usable_simulation_progress_state,
    _usable_simulation_time,
    _bounded_simulation_progression,
    _traced_hop_dict,
    _packet_trace_dict,
    _DHCP_DISCOVER_DECISION,
    _BPDU_DECISION,
    _STP_DROP_DECISION,
    _FRAME_VLAN_CANDIDATE_NEEDLES,
    _decision_match,
    _frame_target,
    _ROLE_TAG_GETTER,
    _CONTROL_VLAN_SOURCE,
    _CONTROL_TAG_GETTER,
    _tag_field_observation,
    _tag_value,
    _tag_link_comparison,
    _single_vlan_access_ports,
    _vlan_control_candidates,
    _frame_vlan_field_semantics,
    _frame_observer_discovery,
    _post_failure_simulation_diagnostic,
)
from packet_tracer_mcp.infrastructure.persistence.cp_scale_stage_evidence import (
    stage_result_evidence, voice_stage_evidence, _trunk_vlan_traversal_evidence,
)

GOVERNED_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = GOVERNED_ROOT / "data" / "cp-scale" / "live-canonical-progress.json"
CHECKPOINT_PATH = EVIDENCE_PATH.parent / "live-canonical-checkpoint.json"
FINAL_CHECKPOINT_PATH = (
    GOVERNED_ROOT / "docs" / "reference" / "cp-scale"
    / "live_canonical_checkpoint.json"
)
CANONICAL_EVIDENCE_DIR = (
    GOVERNED_ROOT / "docs" / "reference" / "cp-scale"
    / "canonical-live-evidence"
)
_GOVERNED_SOURCE_PATHS = (
    "src",
    "tests",
    "tools/cp_scale_canonical_live.py",
    "docs/reference/cp-scale/diseno_logico_IMP.md",
    "docs/reference/cp-scale/topologia_completa_IMP.md",
)
_BUILD_STAGES = tuple(
    stage for stage in CPScaleCanonicalStage
    if stage is not CPScaleCanonicalStage.REMAINING
)


def _build_local_preflight() -> CPScaleLocalPreflight:
    """Compose local readers without granting any backend or product authority."""

    return CPScaleLocalPreflight(
        governed_root=GOVERNED_ROOT,
        runtime_reader=PythonRuntimeEvidenceReader(),
        import_reader=PacketTracerImportIsolationReader(),
        repository_reader=GitCPScaleRepositoryReader(),
        process_reader=PowerShellPacketTracerProcessReader(),
        process_error_policy=packet_tracer_process_error,
        expected_branch=EXPECTED_BRANCH,
        expected_upstream=EXPECTED_UPSTREAM,
        target_resolver=canonical_cp_scale_target_contract,
    )


class CanonicalLiveFailure(RuntimeError):
    """One governed stage failed after the session had acquired ownership.

    `stage_evidence` is whatever that stage had already journalled when it gave
    up. A stage that fails is exactly the stage whose read-backs are worth
    keeping, and they only exist inside `_execute_stage` until it returns.
    """

    def __init__(
        self,
        message: str,
        *,
        stage_evidence: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage_evidence = stage_evidence


def _inventory(physical: PacketTracerPhysicalTopologyRuntime) -> list[dict]:
    observation = physical.observe_workspace()
    if not observation.observed:
        raise CanonicalLiveFailure(
            "Live inventory became unobservable: " + observation.message,
        )
    return [
        {"name": item.name, "model": item.model, "ports": list(item.ports)}
        for item in observation.semantic_devices
    ]


def _write_evidence(evidence: dict[str, object]) -> None:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    temporary = EVIDENCE_PATH.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, EVIDENCE_PATH)


def _emit_finalization_report(payload: dict[str, object]) -> None:
    """Say what finalization could not finish, on whatever channel still works.

    The durable channel may be exactly what just failed, so this one promises
    nothing: it tries each process channel in turn and, if every one of them
    refuses, it stays silent rather than raising over the cause it was called
    to preserve. The in-memory record and the exit code still carry it.
    """

    try:
        line = json.dumps(payload)
    except Exception:
        line = repr(payload)
    for stream in (sys.stdout, sys.stderr):
        try:
            print(line, file=stream, flush=True)
            return
        except Exception:
            continue


def _write_checkpoint_summary(
    stage: str,
    evidence: dict[str, object],
    *,
    destination: Path = CHECKPOINT_PATH,
) -> None:
    stages = evidence.get("stages", [])
    latest = stages[-1] if isinstance(stages, list) and stages else {}
    if stage == "full-qualification":
        latest = evidence.get("full_qualification", latest)
    if not isinstance(latest, dict):
        latest = {}
    plan = latest.get("plan", {})
    physical = latest.get("physical", {})
    raw_digest = hashlib.sha256(EVIDENCE_PATH.read_bytes()).hexdigest()
    summary = {
        "schema": "cp-scale-live-checkpoint-v1",
        "checkpoint": stage,
        "checkpoint_at": evidence.get("checkpoint_at", ""),
        "packet_tracer_version": evidence.get("packet_tracer_version", ""),
        "live_devices": evidence.get("live_devices", 0),
        "live_links": evidence.get("live_links", 0),
        "physical_topology_hash": (
            plan.get("topology_hash", "")
            if isinstance(plan, dict) and plan.get("topology_hash")
            else physical.get("physical_topology_hash", "")
            if isinstance(physical, dict) else ""
        ),
        "configuration_status": (
            latest.get("configuration", {}).get("status", "")
            if isinstance(latest.get("configuration"), dict) else ""
        ),
        "control_plane_status": (
            latest.get("control_plane", {}).get("status", "")
            if isinstance(latest.get("control_plane"), dict) else ""
        ),
        "verification_scope": latest.get("verification_scope", ""),
        "workspace_verified_twice": latest.get("workspace_verified_twice", False),
        "raw_evidence_sha256": raw_digest,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    payload = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)


def _git_output(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=GOVERNED_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _governed_source_changed(session_source_head: str) -> bool:
    completed = subprocess.run(
        [
            "git", "diff", "--quiet", session_source_head, "--",
            *_GOVERNED_SOURCE_PATHS,
        ],
        cwd=GOVERNED_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode not in {0, 1}:
        raise CanonicalLiveFailure(
            "Governed source comparison failed: " + completed.stderr.strip(),
        )
    return completed.returncode == 1


def _checkpoint(
    stage: str,
    evidence: dict[str, object],
    *,
    session_source_head: str,
) -> str:
    evidence["checkpoint"] = stage
    evidence["checkpoint_at"] = datetime.now(timezone.utc).isoformat()
    repository = read_git_repository_state(GOVERNED_ROOT)
    evidence["checkpoint_repository"] = repository.model_dump(mode="json")
    _write_evidence(evidence)
    _write_checkpoint_summary(stage, evidence)
    print(json.dumps({
        "event": "CHECKPOINT_READY",
        "stage": stage,
        "evidence_path": str(EVIDENCE_PATH),
        "devices": evidence.get("live_devices", 0),
        "links": evidence.get("live_links", 0),
    }), flush=True)
    command = input().strip().casefold()
    if command not in {"continue", "retain"}:
        raise CanonicalLiveFailure(
            f"Checkpoint {stage!r} received operator command {command!r}; aborting.",
        )
    resumed_repository = read_git_repository_state(GOVERNED_ROOT)
    try:
        upstream_head = _git_output("rev-parse", "@{upstream}")
        dirty = bool(_git_output("status", "--porcelain"))
        source_changed = _governed_source_changed(session_source_head)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CanonicalLiveFailure(
            f"Checkpoint repository revalidation failed: {exc}",
        ) from exc
    repository_error = canonical_checkpoint_repository_error(
        branch=resumed_repository.branch,
        upstream=resumed_repository.upstream,
        head=resumed_repository.head,
        upstream_head=upstream_head,
        dirty=dirty,
        governed_source_changed=source_changed,
    )
    evidence["checkpoint_resume_repository"] = {
        **resumed_repository.model_dump(mode="json"),
        "upstream_head": upstream_head,
        "dirty": dirty,
        "governed_source_changed": source_changed,
    }
    _write_evidence(evidence)
    if resumed_repository.error or repository_error:
        raise CanonicalLiveFailure(
            "Checkpoint may not advance: "
            + (resumed_repository.error + " " if resumed_repository.error else "")
            + repository_error,
        )
    return command


def _cleanup_owned(
    physical: PacketTracerPhysicalTopologyRuntime,
    full_topology,
    owned_device_ids: set[str],
    baseline,
) -> dict[str, object]:
    cleanup = []
    for device in reversed(full_topology.devices):
        if device.id not in owned_device_ids:
            continue
        cleanup.append(physical.remove_device(device).model_dump(mode="json"))
    first = physical.observe_workspace()
    second = physical.observe_workspace()
    restoration_error = canonical_cleanup_restoration_error(
        baseline, first, second,
    )
    return {
        "mutations": cleanup,
        "first": first.compact_summary(),
        "second": second.compact_summary(),
        "restoration_error": restoration_error,
        "verified": not restoration_error,
    }


def _complete_router0_target(
    *,
    evidence: dict[str, object],
    target_contract,
    physical: PacketTracerPhysicalTopologyRuntime,
    full_topology,
    owned_device_ids: set[str],
    baseline,
    observe_cleanup_realtime,
    archive,
    run_identity: str,
    session_source_head: str,
) -> dict[str, object]:
    """Publish Router0 success only after archive and full restoration."""

    stages = evidence.get("stages")
    latest = stages[-1] if isinstance(stages, list) and stages else None
    plan = latest.get("plan") if isinstance(latest, dict) else None
    planned_forwarding = (
        plan.get("branch_forwarding_checks")
        if isinstance(plan, dict) else None
    )
    observed_forwarding = (
        latest.get("site_forwarding") if isinstance(latest, dict) else None
    )
    planned_ids = {
        str(item.get("id") or "")
        for item in planned_forwarding
        if isinstance(item, dict)
    } if isinstance(planned_forwarding, list) else set()
    observed_ids = {
        str(item.get("check", {}).get("id") or "")
        for item in observed_forwarding
        if isinstance(item, dict) and isinstance(item.get("check"), dict)
    } if isinstance(observed_forwarding, list) else set()
    forwarding_coverage_verified = bool(
        isinstance(planned_forwarding, list)
        and isinstance(observed_forwarding, list)
        and len(planned_forwarding) == len(planned_ids)
        and len(observed_forwarding) == len(observed_ids)
        and planned_ids == observed_ids
        and all(
            item.get("verified") is True
            for item in observed_forwarding
            if isinstance(item, dict)
        )
    )
    if (
        target_contract.target is not CPScaleCanonicalTarget.ROUTER0_BRANCH
        or not isinstance(latest, dict)
        or latest.get("stage") != CPScaleCanonicalStage.ROUTER0_BRANCH.value
        or latest.get("verified") is not True
        or latest.get("site_forwarding_verified") is not True
        or latest.get("workspace_verified_twice") is not True
        or not planned_ids
        or not forwarding_coverage_verified
    ):
        raise CanonicalLiveFailure(
            "Router0 terminal closure lacks verified stage, forwarding, or "
            "double workspace evidence."
        )

    # NO_MUTATION_REPLAY is a claim about every stage this session built, not
    # about the last one. A retained action executed again at floor2 is still
    # a replay when Router0 asks to close, so the audit is read across the
    # whole run and any stage without a VERIFIED one refuses the closure.
    audits = [
        item.get("mutation_replay_audit") if isinstance(item, dict) else None
        for item in (stages if isinstance(stages, list) else [])
    ]
    replayed = sorted({
        identifier
        for audit in audits if isinstance(audit, dict)
        for surface in audit.get("surfaces", [])
        if isinstance(surface, dict)
        for identifier in surface.get("replayed_retained_ids", [])
    })
    unverified_stages = [
        str(stage.get("stage") or "")
        for stage, audit in zip(
            stages if isinstance(stages, list) else [], audits,
        )
        if not isinstance(audit, dict)
        or audit.get("verified") is not True
        or audit.get("claim") != "NO_MUTATION_REPLAY"
    ]
    evidence["no_mutation_replay"] = {
        "claim": (
            "NO_MUTATION_REPLAY" if not unverified_stages
            else "MUTATION_REPLAY_DETECTED"
        ),
        "verified": not unverified_stages,
        "audited_stages": [
            str(item.get("stage") or "")
            for item in (stages if isinstance(stages, list) else [])
            if isinstance(item, dict)
        ],
        "stages_without_verified_audit": unverified_stages,
        "replayed_retained_ids": replayed,
    }
    if unverified_stages:
        replay_detail = (
            "; replayed retained actions: " + ", ".join(replayed)
            if replayed else ""
        )
        raise CanonicalLiveFailure(
            "Router0 terminal closure cannot attest NO_MUTATION_REPLAY; "
            "stages without a verified runtime audit: "
            + ", ".join(unverified_stages)
            + replay_detail
        )

    evidence["final_disposition"] = CPScaleFinalDisposition.CLEANUP.value
    evidence["closure_scope"] = CPScaleCanonicalStage.ROUTER0_BRANCH.value
    evidence["closure"] = target_contract.precleanup_closure
    evidence["completed_at"] = datetime.now(timezone.utc).isoformat()
    _write_evidence(evidence)
    precleanup_archive = archive("precleanup", evidence)
    evidence["canonical_evidence_precleanup"] = precleanup_archive

    cleanup_result = _cleanup_owned(
        physical,
        full_topology,
        owned_device_ids,
        baseline,
    )
    cleanup_realtime = observe_cleanup_realtime()
    evidence["cleanup"] = cleanup_result
    evidence["cleanup_realtime"] = cleanup_realtime
    if not cleanup_result.get("verified") or not cleanup_realtime["verified"]:
        raise CanonicalLiveFailure(
            "Router0 verification completed, but cleanup/restoration did not "
            "verify: "
            + str(
                cleanup_result.get("restoration_error")
                or cleanup_realtime.get("error")
            )
        )

    cleanup_completed_at = datetime.now(timezone.utc).isoformat()
    cleanup_attestation = {
        "schema": "cp-scale-canonical-cleanup-attestation-v1",
        "run_identity": run_identity,
        "source_head": session_source_head,
        "target_stage": target_contract.target.value,
        "closure_scope": CPScaleCanonicalStage.ROUTER0_BRANCH.value,
        "canonical_evidence_precleanup": precleanup_archive,
        "no_mutation_replay": evidence["no_mutation_replay"],
        "cleanup": cleanup_result,
        "cleanup_realtime": cleanup_realtime,
        "closure": target_contract.cleaned_closure,
        "cleanup_completed_at": cleanup_completed_at,
    }
    archived_cleanup = archive("cleanup", cleanup_attestation)
    evidence["cleanup_attestation"] = archived_cleanup
    evidence["closure"] = target_contract.cleaned_closure
    evidence["cleanup_completed_at"] = cleanup_completed_at
    _write_evidence(evidence)
    _write_checkpoint_summary(CPScaleCanonicalStage.ROUTER0_BRANCH.value, evidence)
    print(json.dumps({
        "event": "ROUTER0_BRANCH_VERIFIED_AND_CLEANED",
        "stage": CPScaleCanonicalStage.ROUTER0_BRANCH.value,
        "devices": evidence.get("live_devices", 0),
        "links": evidence.get("live_links", 0),
        "evidence_path": str(EVIDENCE_PATH),
        "canonical_archive": precleanup_archive,
        "cleanup_attestation": evidence["cleanup_attestation"],
    }), flush=True)
    return {
        "precleanup_archive": precleanup_archive,
        "cleanup": cleanup_result,
        "cleanup_realtime": cleanup_realtime,
        "cleanup_attestation": evidence["cleanup_attestation"],
    }


def _attempted_device_ids(deployment) -> set[str]:
    return {
        item.target_id
        for item in deployment.item_results
        if item.target_kind is PhysicalObjectKind.DEVICE
        and item.status is not PhysicalDeploymentItemStatus.NOT_ATTEMPTED
    }


@dataclass(frozen=True)
class CPScaleStageAdapterResult:
    """Temporary publishing adapter; domain continuity stays on the typed result."""
    result: CPScaleLiveStageResult
    evidence: dict[str, object]

    def __iter__(self):
        yield self.evidence
        yield self.result.manifest
        yield self.result.workspace
        yield self.result.configuration


def _build_stage_executor(
    *, physical, configuration_runtime, control_runtime, voice_runtime,
    transport, packet_tracer_version,
) -> CPScaleStageExecutor:
    observations = PacketTracerCPScaleObservations(transport, physical)
    return CPScaleStageExecutor(
        configuration=CPScaleConfigurationStage(
            ConfigurationApplicator(configuration_runtime),
            serial_wait=observations.serial_interfaces,
        ),
        voice=CPScaleVoiceStage(VoiceApplicator(voice_runtime), voice_runtime),
        control_plane=CPScaleControlPlaneStage(
            ControlPlaneApplicator(control_runtime),
            packet_tracer_control_plane_capabilities(packet_tracer_version),
        ),
        forwarding=CPScaleForwardingStage(observations),
        reconciliation=CPScaleReconciliation(observations),
        observations=observations,
        diagnostics=PacketTracerCPScaleDiagnostics(transport),
    )


def _stage_voice(projection, *, voice_runtime, applicator=None, **kwargs) -> dict[str, object]:
    """Legacy publishing helper; the injected Voice stage owns the decision."""
    result = CPScaleVoiceStage(
        applicator if applicator is not None else VoiceApplicator(voice_runtime), voice_runtime,
    ).apply(projection, **kwargs)
    return voice_stage_evidence(projection, result)


def _execute_stage(
    projection,
    *,
    composition,
    deployment,
    delta_deployment,
    physical: PacketTracerPhysicalTopologyRuntime,
    configuration_runtime: PacketTracerEnterpriseConfigurationRuntime,
    control_runtime: PacketTracerEnterpriseControlPlaneRuntime,
    voice_runtime: PacketTracerEnterpriseVoiceRuntime,
    transport: PacketTracerHttpTransport,
    fingerprint: EnvironmentFingerprint,
    packet_tracer_version: str,
    dhcp_statistics_target: dict[str, str] | None = None,
    dhcp_statistics_baseline: dict[str, object] | None = None,
    verified_serial_topology=None,
    verified_serial_manifest=None,
    previous_projection=None,
    previous_configuration=None,
    previous_voice_action_results: tuple[
        ActionApplicationResult, ...
    ] = (),
    previous_control_plane_action_results: tuple[
        ActionApplicationResult, ...
    ] = (),
    network_boundaries: list[dict[str, object]] | None = None,
    site_forwarding_checks=(),
) -> CPScaleStageAdapterResult:
    request = CPScaleStageExecutionInput(
        projection=projection, composition=composition, deployment=deployment,
        delta_deployment=delta_deployment, fingerprint=fingerprint,
        packet_tracer_version=packet_tracer_version,
        continuity=CPScaleStageContinuity(
            previous_projection, previous_configuration, previous_voice_action_results,
            previous_control_plane_action_results, verified_serial_topology, verified_serial_manifest,
        ),
        dhcp_statistics_target=(CPScaleDhcpStatisticsTarget(**dhcp_statistics_target) if dhcp_statistics_target is not None else None),
        dhcp_statistics_baseline=(
            CPScaleObservationRecord("dhcp_baseline", projection.stage, "coordinator", "observed", dhcp_statistics_baseline)
            if dhcp_statistics_baseline is not None else None
        ),
        network_boundaries=tuple(
            CPScaleObservationRecord("network_state", projection.stage, "coordinator", "observed", item)
            for item in network_boundaries or ()
        ),
        site_forwarding_checks=tuple(site_forwarding_checks),
    )
    result = _build_stage_executor(
        physical=physical, configuration_runtime=configuration_runtime,
        control_runtime=control_runtime, voice_runtime=voice_runtime,
        transport=transport, packet_tracer_version=packet_tracer_version,
    ).execute(request)
    evidence = stage_result_evidence(result)
    if result.outcome == "failed":
        raise CanonicalLiveFailure(result.failure, stage_evidence=evidence)
    return CPScaleStageAdapterResult(result, evidence)


def _full_qualification_projection(composition):
    projection = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.REMAINING,
    )
    return projection.__class__(
        stage=projection.stage,
        topology=composition.topology,
        configuration=composition.configuration,
        control_plane=composition.control_plane,
        forwarding_checks=projection.forwarding_checks,
        # The full plans, so the full voice plan: its source hashes bind the
        # whole topology and configuration, which is exactly what this stage
        # is applied against.
        voice=composition.voice,
    )


def run(
    packet_tracer_version: str,
    *,
    expected_head: str,
    retain_on_full_verification: bool,
    target_stage: CPScaleCanonicalTarget | str = (
        CPScaleCanonicalTarget.FULL_QUALIFICATION
    ),
) -> int:
    request = CPScaleLiveRequest(
        packet_tracer_version=packet_tracer_version,
        expected_head=expected_head,
        retain_on_full_verification=retain_on_full_verification,
        target_stage=target_stage,
    )
    started_at = datetime.now(timezone.utc)
    run_identity = (
        "canonical-cp-scale-voice-"
        + started_at.strftime("%Y%m%dT%H%M%S%fZ")
        + "-"
        + (expected_head[:12] or "unknown-head")
    )
    preflight = _build_local_preflight().inspect(
        request,
        run_identity=run_identity,
        started_at=started_at,
    )
    target_contract = preflight.target
    evidence: dict[str, object] = {
        "schema": "cp-scale-canonical-voice-live-v1",
        "run_identity": run_identity,
        "started_at": started_at.isoformat(),
        "packet_tracer_version": packet_tracer_version,
        "python_executable": preflight.runtime.python_executable,
        "package_file": preflight.runtime.package_file,
        "loaded_namespaces": list(preflight.runtime.loaded_namespaces),
        "target_stage": target_contract.target.value,
        "target_contract": {
            "build_stages": [
                stage.value for stage in target_contract.build_stages
            ],
            "terminal_stage": target_contract.terminal_stage.value,
            "run_remaining_reconciliation": (
                target_contract.run_remaining_reconciliation
            ),
            "run_full_qualification": target_contract.run_full_qualification,
            "allow_retention": target_contract.allow_retention,
            "precleanup_closure": target_contract.precleanup_closure,
            "cleaned_closure": target_contract.cleaned_closure,
        },
        "stages": [],
        "presentation_retained": False,
    }
    if preflight.import_isolation.state is not CPScaleCheckState.NOT_RUN:
        evidence["import_isolation"] = {
            "state": preflight.import_isolation.isolation_state,
            "detail": preflight.import_isolation.detail,
        }
    if preflight.repository.state is not CPScaleCheckState.NOT_RUN:
        evidence["repository"] = {
            "branch": preflight.repository.branch,
            "upstream": preflight.repository.upstream,
            "head": preflight.repository.head,
            "error": preflight.repository.error,
        }
        if preflight.repository.upstream_head_error:
            evidence["initial_upstream_error"] = (
                preflight.repository.upstream_head_error
            )
    if preflight.process.state is not CPScaleCheckState.NOT_RUN:
        evidence["packet_tracer_processes"] = [
            process_record_mapping(item)
            for item in preflight.process.processes
        ]
    if preflight.outcome is CPScalePreflightOutcome.REJECTED:
        evidence["hard_stop"] = " ".join(preflight.issues) or (
            "Local preflight evidence is incomplete or inconsistent."
        )
        _write_evidence(evidence)
        return 2
    identity = preflight.identity
    if identity is None:  # Defensive: outcome already rejects absent identity.
        evidence["hard_stop"] = (
            "Local preflight did not produce a session identity."
        )
        _write_evidence(evidence)
        return 2
    session_source_head = identity.source_head

    transport = PacketTracerHttpTransport()
    physical = None
    baseline = None
    owned_device_ids: set[str] = set()
    retain_confirmed = False
    cleanup_attempted = False
    cleanup_attestation_archived = False
    terminal_cleanup_complete = False
    precleanup_archive: dict[str, object] | None = None
    composition = None
    pending_stage_evidence: dict[str, object] | None = None
    # The code this session settled on, or None while an exception is
    # still travelling: finalization may only downgrade a settled success,
    # never a failure it did not cause and never a cancellation.
    settled_outcome: int | None = None

    def _settled(code: int) -> int:
        """Record the outcome the session reached before finalization runs."""

        nonlocal settled_outcome
        settled_outcome = code
        return code

    def _finalize() -> list[str]:
        """Persist what happened, then close what this session acquired.

        Ownership, retention and the cleanup verdict are decided above and are
        never touched here: an attempted close is not a verified restoration.
        Everything this block cannot finish is secondary, and the report leaves
        before the function returns so a cancellation cannot take the
        secondaries with it.
        """

        nonlocal precleanup_archive, cleanup_attempted
        errors: list[str] = []
        try:
            if (
                physical is not None
                and baseline is not None
                and not retain_confirmed
                and not terminal_cleanup_complete
                and composition is not None
            ):
                if precleanup_archive is None:
                    try:
                        precleanup_archive = archive("failure-precleanup", evidence)
                        evidence["canonical_evidence_precleanup"] = precleanup_archive
                    except Exception as exc:
                        evidence["precleanup_archive_error"] = (
                            f"{type(exc).__name__}: {exc}"
                        )
                if not cleanup_attempted:
                    try:
                        evidence["cleanup"] = _cleanup_owned(
                            physical, composition.topology, owned_device_ids, baseline,
                        )
                        cleanup_attempted = True
                    except Exception as exc:
                        evidence["cleanup"] = {
                            "verified": False,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                evidence["cleanup_realtime"] = observe_cleanup_realtime()
                if not cleanup_attestation_archived:
                    try:
                        cleanup_attestation = {
                            "schema": "cp-scale-canonical-cleanup-attestation-v1",
                            "run_identity": run_identity,
                            "source_head": session_source_head,
                            "canonical_evidence_precleanup": precleanup_archive,
                            "failure": evidence.get("failure", ""),
                            "cleanup": evidence.get("cleanup"),
                            "cleanup_realtime": evidence["cleanup_realtime"],
                            "cleanup_completed_at": (
                                datetime.now(timezone.utc).isoformat()
                            ),
                        }
                        phase = (
                            "cleanup"
                            if (
                                isinstance(evidence.get("cleanup"), dict)
                                and evidence["cleanup"].get("verified")
                                and evidence["cleanup_realtime"].get("verified")
                            )
                            else "cleanup-incomplete"
                        )
                        evidence["cleanup_attestation"] = archive(
                            phase, cleanup_attestation,
                        )
                    except Exception as exc:
                        evidence["cleanup_archive_error"] = (
                            f"{type(exc).__name__}: {exc}"
                        )
            evidence["presentation_retained"] = retain_confirmed
            try:
                _write_evidence(evidence)
            except Exception as exc:
                errors.append(
                    f"final_evidence_write: {type(exc).__name__}: {exc}"
                )
        except Exception as exc:
            # Cleanup, archive or the re-read before the write: whatever this
            # block could not finish is still secondary to the session's cause.
            errors.append(f"finalization: {type(exc).__name__}: {exc}")
        finally:
            try:
                # Acquired, therefore closed. No failure and no cancellation
                # above may skip this, and closing attests nothing about
                # restoration.
                try:
                    transport.stop()
                except Exception as exc:
                    errors.append(
                        f"transport_stop: {type(exc).__name__}: {exc}"
                    )
            finally:
                if errors:
                    evidence["finalization_errors"] = list(errors)
                    _emit_finalization_report({
                        "event": "CP_SCALE_FINALIZATION_INCOMPLETE",
                        "run_identity": run_identity,
                        "primary_failure": str(evidence.get("failure") or ""),
                        "hard_stop": str(evidence.get("hard_stop") or ""),
                        "finalization_errors": list(errors),
                    })
        return errors

    def archive(phase: str, payload: object) -> dict[str, object]:
        archived = archive_cp_scale_canonical_evidence(
            payload,
            base_dir=CANONICAL_EVIDENCE_DIR,
            run_identity=run_identity,
            phase=phase,
        ).model_dump(mode="json")
        evidence.setdefault("archives", []).append(archived)
        return archived

    def observe_cleanup_realtime() -> dict[str, object]:
        try:
            state = _voice_window_state(
                SimulationTraceRuntime(transport.send_and_wait),
            )
            error = _realtime_boundary_error(state, "after cleanup")
            return {
                "state": state,
                "error": error,
                "verified": not error,
            }
        except Exception as exc:
            return {
                "state": None,
                "error": f"{type(exc).__name__}: {exc}",
                "verified": False,
            }

    try:
        if not transport.start(timeout_seconds=10.0):
            status = transport.status_dict()
            # Recorded beside it, never instead of it. The two channels are
            # independent and the file one is alive through every failure of
            # this one, which is exactly the confusion worth pre-empting in the
            # hard stop itself.
            try:
                status["file_bridge_alive"] = FileBridge().pt_alive()
            except Exception:
                pass
            evidence["http_bridge"] = status
            raise CanonicalLiveFailure(
                "Authenticated Packet Tracer HTTP bridge did not obtain fresh "
                "polling: " + canonical_bridge_polling_error(status)
            )
        evidence["http_bridge"] = transport.status_dict()
        physical = PacketTracerPhysicalTopologyRuntime(
            transport.send_and_wait,
            mutation_timeout_seconds=30.0,
            observation_timeout_seconds=12.0,
        )
        baseline = physical.observe_workspace()
        evidence["baseline"] = baseline.compact_summary()
        baseline_error = disposable_workspace_error(baseline)
        if baseline_error:
            evidence["hard_stop"] = baseline_error
            _write_evidence(evidence)
            return _settled(2)

        capability_store = CapabilitySnapshotStore(
            GOVERNED_ROOT / "data" / "capabilities",
        )
        composition = compose_cp_scale_canonical(
            packet_tracer_version=packet_tracer_version,
            capability_store=capability_store,
        )
        if not composition.valid:
            raise CanonicalLiveFailure(
                "Canonical composition failed: " + "; ".join(composition.issues),
            )
        assert composition.topology is not None
        assert composition.configuration is not None
        assert composition.control_plane is not None

        required_capabilities = canonical_required_capability_probes(composition)
        probe_runtime = PacketTracerBridgeProbeRuntime(
            transport.send_and_wait,
            packet_tracer_version=packet_tracer_version,
            send=transport.send,
            transport_channel=transport.bridge_transport,
        )
        capability_discovery = CapabilityDiscoveryService(
            runtime=probe_runtime,
            snapshots=capability_store,
            identity_for=EnterpriseCapabilityAdapter().identity_for,
            access_ports_for=EnterpriseCapabilityAdapter().access_ports_for,
        )
        capability_evidence = []
        for model, capabilities in required_capabilities.items():
            snapshot, cached = capability_discovery.run(ProbeRequest(
                models=[model],
                capabilities=capabilities,
                probe_level=ProbeLevel.LOGICAL,
                force=True,
                packet_tracer_version=packet_tracer_version,
            ))
            probe_error = canonical_capability_probe_error(
                snapshot,
                model=model,
                capabilities=capabilities,
                packet_tracer_version=packet_tracer_version,
            )
            capability_evidence.append({
                "model": model,
                "required": capabilities,
                "cached": cached,
                "summary": snapshot.compact_summary(),
                "results": [
                    item.model_dump(mode="json")
                    for item in snapshot.session.results
                    if item.capability in capabilities
                ],
                "error": probe_error,
            })
            if probe_error:
                evidence["capability_prequalification"] = capability_evidence
                raise CanonicalLiveFailure(probe_error)

        post_probe_first = physical.observe_workspace()
        post_probe_second = physical.observe_workspace()
        post_probe_error = canonical_cleanup_restoration_error(
            baseline, post_probe_first, post_probe_second,
        )
        evidence["capability_prequalification"] = {
            "requirements": required_capabilities,
            "sessions": capability_evidence,
            "workspace_first": post_probe_first.compact_summary(),
            "workspace_second": post_probe_second.compact_summary(),
            "restoration_error": post_probe_error,
        }
        if post_probe_error:
            raise CanonicalLiveFailure(post_probe_error)

        composition = compose_cp_scale_canonical(
            packet_tracer_version=packet_tracer_version,
            capability_store=capability_store,
        )
        if not composition.valid:
            raise CanonicalLiveFailure(
                "Canonical post-probe composition failed: "
                + "; ".join(composition.issues),
            )
        unresolved = sorted(
            f"{model}:{capability}"
            for model, capabilities in required_capabilities.items()
            for capability in capabilities
            if (
                composition.capabilities.get(model) is None
                or getattr(
                    composition.capabilities[model], capability,
                    CapabilityStatus.UNKNOWN,
                ) is not CapabilityStatus.SUPPORTED
            )
        )
        evidence["capability_prequalification"]["unresolved_after_composition"] = (
            unresolved
        )
        if unresolved:
            raise CanonicalLiveFailure(
                "Canonical composition did not consume VERIFIED capability evidence: "
                + ", ".join(unresolved)
            )

        floor1_statistics_projection = project_cp_scale_canonical_stage(
            composition, CPScaleCanonicalStage.FLOOR1,
        )
        dhcp_statistics_target = _voice_dhcp_statistics_target(
            floor1_statistics_projection.configuration,
            floor1_statistics_projection.voice,
        )

        fingerprint = EnvironmentFingerprint(
            backend="packet_tracer",
            backend_version=packet_tracer_version,
            bridge_transport=transport.bridge_transport,
            runtime_mode="live",
        )
        deployer = EnterprisePhysicalTopologyDeployer(physical)
        active_network_projection: dict[str, object] = {
            "projection": None,
        }
        transition_ios = ControlledIosExecutor(transport.send_and_wait)

        def observe_trunk_transition(
            device_name: str,
        ) -> dict[str, object]:
            active = active_network_projection["projection"]
            if active is None:
                return {
                    "device_name": device_name,
                    "authoritative": False,
                    "failure_reason": "NO_ACTIVE_CANONICAL_PROJECTION",
                }
            return _stp_network_device_evidence(
                transition_ios,
                active,
                device_name,
            )

        configuration_runtime = PacketTracerEnterpriseConfigurationRuntime(
            lambda: _inventory(physical),
            transport.send,
            transport.send_and_wait,
            l3_timeout_seconds=20.0,
            trunk_transition_observer=observe_trunk_transition,
        )
        control_runtime = PacketTracerEnterpriseControlPlaneRuntime(
            lambda: _inventory(physical),
            transport.send,
            transport.send_and_wait,
        )
        # A phone that has just been given option 150 and a call control has to
        # solicit, lease, fetch its files and register. 30s is the applicator
        # default and it is a DHCP retry interval, not a provisioning cycle.
        voice_runtime = PacketTracerEnterpriseVoiceRuntime(
            lambda: _inventory(physical),
            transport.send,
            transport.send_and_wait,
            registration_timeout_seconds=180.0,
            convergence_interval_seconds=5.0,
        )

        previous_projection = None
        previous_configuration = None
        previous_voice_action_results: tuple[
            ActionApplicationResult, ...
        ] = ()
        previous_control_plane_action_results: tuple[
            ActionApplicationResult, ...
        ] = ()
        verified_core_deployment = None
        verified_core_topology = None
        verified_serial_manifest = None
        verified_serial_topology = None
        stage_snapshot = None
        dhcp_statistics_baseline = None
        for index, stage in enumerate(target_contract.build_stages):
            projection = project_cp_scale_canonical_stage(
                composition,
                stage,
                control_plane_capabilities=(
                    packet_tracer_control_plane_capabilities(packet_tracer_version)
                ),
            )
            pending_stage_evidence = {
                "stage": stage.value,
                "plan": {
                    "topology_hash": projection.topology.physical_identity_hash,
                    "configuration_hash": projection.configuration.semantic_hash,
                    "control_plane_hash": projection.control_plane.semantic_hash,
                    "devices": len(projection.topology.devices),
                    "links": len(projection.topology.links),
                },
                "stage_outcome": "in_progress",
            }
            evidence["active_stage"] = pending_stage_evidence
            active_network_projection["projection"] = projection
            stage_network_boundaries: list[dict[str, object]] = []
            if index == 0:
                delta_deployment = deployer.deploy(
                    projection.topology,
                    environment_fingerprint=fingerprint,
                    deployment_id="cp-scale-canonical/routing-core",
                    require_empty_workspace=True,
                )
                pending_stage_evidence["physical_delta"] = (
                    delta_deployment.model_dump(mode="json")
                )
                _write_evidence(evidence)
                owned_device_ids |= _attempted_device_ids(delta_deployment)
                ownership_error = canonical_delta_deployment_error(
                    None, projection.topology, delta_deployment,
                )
                if ownership_error:
                    raise CanonicalLiveFailure(
                        "Routing-core ownership was not proven: " + ownership_error
                    )
                deployment = delta_deployment
                verified_core_deployment = deployment
                verified_core_topology = projection.topology
            else:
                assert previous_projection is not None
                assert stage_snapshot is not None
                if not transport.is_connected:
                    raise CanonicalLiveFailure(
                        f"Packet Tracer bridge was not freshly connected before {stage.value!r}."
                    )
                resume_observations = [
                    physical.observe_workspace(),
                    physical.observe_workspace(),
                ]
                resume_errors = [
                    canonical_stage_resume_error(
                        stage_snapshot, observation, previous_projection.topology,
                    )
                    for observation in resume_observations
                ]
                evidence.setdefault("resume_gates", []).append({
                    "before_stage": stage.value,
                    "bridge": transport.status_dict(),
                    "observations": [
                        item.compact_summary() for item in resume_observations
                    ],
                    "errors": resume_errors,
                })
                if any(resume_errors):
                    raise CanonicalLiveFailure(
                        f"Retained workspace drifted before {stage.value!r}: "
                        + next(item for item in resume_errors if item)
                    )
                before_physical_delta = _network_state_observation(
                    ControlledIosExecutor(transport.send_and_wait),
                    previous_projection,
                    boundary="before_physical_delta",
                )
                stage_network_boundaries.append(before_physical_delta)
                evidence.setdefault(
                    "network_state_boundaries", [],
                ).append({
                    "before_stage": stage.value,
                    **before_physical_delta,
                })
                delta_topology = project_cp_scale_canonical_delta(
                    previous_projection.topology, projection.topology,
                )
                if (
                    target_contract.target
                    is CPScaleCanonicalTarget.ROUTER0_BRANCH
                    and stage is CPScaleCanonicalStage.ROUTER0_BRANCH
                ):
                    transition = canonical_stage_transition_contract(
                        previous_projection,
                        projection,
                    )
                    transition_evidence = {
                        **asdict(transition),
                        "previous_stage": transition.previous_stage.value,
                        "current_stage": transition.current_stage.value,
                        "mutation_scope_disjoint": (
                            transition.mutation_scope_disjoint
                        ),
                        "claim": transition.claim,
                    }
                    pending_stage_evidence["transition_contract"] = (
                        transition_evidence
                    )
                    evidence["router0_transition_contract"] = (
                        transition_evidence
                    )
                    _write_evidence(evidence)
                    if (
                        previous_projection.stage
                        is not CPScaleCanonicalStage.FLOOR3
                        or not transition.mutation_scope_disjoint
                    ):
                        raise CanonicalLiveFailure(
                            "Router0 target refused its incremental boundary: "
                            + transition.claim,
                            stage_evidence=pending_stage_evidence,
                        )
                delta_deployment = deployer.deploy(
                    delta_topology,
                    environment_fingerprint=fingerprint,
                    deployment_id=f"cp-scale-canonical/{stage.value}/delta",
                    require_empty_workspace=False,
                )
                pending_stage_evidence["physical_delta"] = (
                    delta_deployment.model_dump(mode="json")
                )
                _write_evidence(evidence)
                owned_device_ids |= _attempted_device_ids(delta_deployment)
                ownership_error = canonical_delta_deployment_error(
                    previous_projection.topology,
                    delta_topology,
                    delta_deployment,
                )
                if ownership_error:
                    raise CanonicalLiveFailure(
                        f"Physical delta {stage.value!r} lacked session ownership: "
                        + ownership_error
                    )
                if (
                    delta_deployment.status is not PhysicalDeploymentStatus.VERIFIED
                    or delta_deployment.manifest is None
                ):
                    raise CanonicalLiveFailure(
                        f"Physical delta {stage.value!r} was not VERIFIED: "
                        + "; ".join(delta_deployment.errors)
                    )
                # Physical manifest assembly remains owned by the coordinator.
                # This is not the executor's terminal cumulative reconciliation:
                # that separate gate reads workspace twice after forwarding.
                deployment = reconcile_canonical_stage_deployment(
                    projection.topology,
                    physical,
                    environment_fingerprint=fingerprint,
                    verified_core_topology=verified_core_topology,
                    verified_core_deployment=verified_core_deployment,
                    deployment_id=f"cp-scale-canonical/{stage.value}/cumulative",
                )
            pending_stage_evidence["physical"] = deployment.model_dump(
                mode="json",
            )
            _write_evidence(evidence)
            if (
                deployment.status is not PhysicalDeploymentStatus.VERIFIED
                or deployment.manifest is None
            ):
                raise CanonicalLiveFailure(
                    f"Cumulative physical stage {stage.value!r} was not VERIFIED: "
                    + "; ".join(deployment.errors)
                )
            stage_output = _execute_stage(
                projection,
                composition=composition,
                deployment=deployment,
                delta_deployment=delta_deployment,
                physical=physical,
                configuration_runtime=configuration_runtime,
                control_runtime=control_runtime,
                voice_runtime=voice_runtime,
                transport=transport,
                fingerprint=fingerprint,
                packet_tracer_version=packet_tracer_version,
                dhcp_statistics_target=(
                    dhcp_statistics_target
                    if stage is CPScaleCanonicalStage.FLOOR1 else None
                ),
                dhcp_statistics_baseline=(
                    dhcp_statistics_baseline
                    if stage is CPScaleCanonicalStage.FLOOR1 else None
                ),
                verified_serial_topology=verified_serial_topology,
                verified_serial_manifest=verified_serial_manifest,
                previous_projection=previous_projection,
                previous_configuration=previous_configuration,
                previous_voice_action_results=previous_voice_action_results,
                previous_control_plane_action_results=(
                    previous_control_plane_action_results
                ),
                network_boundaries=stage_network_boundaries,
                site_forwarding_checks=(
                    projection.branch_forwarding_checks
                    if (
                        target_contract.target
                        is CPScaleCanonicalTarget.ROUTER0_BRANCH
                        and stage is CPScaleCanonicalStage.ROUTER0_BRANCH
                    )
                    else ()
                ),
            )
            stage_evidence, stage_manifest, stage_snapshot, configuration = stage_output
            if stage is CPScaleCanonicalStage.ROUTER4_SWITCH10:
                if dhcp_statistics_target is None:
                    dhcp_statistics_baseline = {
                        "voice": None,
                        "control": None,
                        "failure_reason": (
                            "A unique Floor-1 voice DHCP statistics target "
                            "with a control scope was unavailable."
                        ),
                    }
                else:
                    dhcp_statistics_baseline = _dhcp_server_statistics_point(
                        ControlledIosExecutor(transport.send_and_wait),
                        dhcp_statistics_target,
                    )
                stage_evidence["dhcp_voice_statistics_baseline"] = (
                    dhcp_statistics_baseline
                )
            if stage is CPScaleCanonicalStage.ROUTING_CORE:
                verified_serial_topology = projection.topology
                verified_serial_manifest = stage_manifest
            evidence["stages"].append(stage_evidence)
            pending_stage_evidence = None
            evidence.pop("active_stage", None)
            evidence["live_devices"] = len(projection.topology.devices)
            evidence["live_links"] = len(projection.topology.links)

            voice_result = stage_output.result.voice
            if voice_result is not None:
                previous_voice_action_results = tuple(voice_result.action_results)
            elif projection.voice is not None and projection.voice.actions:
                raise CanonicalLiveFailure(
                    f"Verified stage {stage.value!r} did not retain its Voice application results."
                )
            control_result = stage_output.result.control_plane
            if control_result is None:
                raise CanonicalLiveFailure(
                    f"Verified stage {stage.value!r} did not retain its control-plane result."
                )
            previous_control_plane_action_results = tuple(control_result.action_results)
            previous_projection = projection
            previous_configuration = configuration
            if stage is CPScaleCanonicalStage.ROUTING_CORE:
                print(json.dumps({
                    "event": "CORE_REMATERIALIZED",
                    "devices": 3,
                    "links": 3,
                }), flush=True)
            if (
                target_contract.target is CPScaleCanonicalTarget.ROUTER0_BRANCH
                and stage is target_contract.terminal_stage
            ):
                completion = _complete_router0_target(
                    evidence=evidence,
                    target_contract=target_contract,
                    physical=physical,
                    full_topology=composition.topology,
                    owned_device_ids=owned_device_ids,
                    baseline=baseline,
                    observe_cleanup_realtime=observe_cleanup_realtime,
                    archive=archive,
                    run_identity=run_identity,
                    session_source_head=session_source_head,
                )
                precleanup_archive = completion["precleanup_archive"]
                cleanup_attempted = True
                cleanup_attestation_archived = True
                terminal_cleanup_complete = True
                return _settled(0)
            command = _checkpoint(
                stage.value,
                evidence,
                session_source_head=session_source_head,
            )
            if command == "retain":
                raise CanonicalLiveFailure(
                    "Retention is forbidden before full CP-SCALE qualification."
                )

        assert target_contract.run_remaining_reconciliation
        assert target_contract.run_full_qualification
        assert previous_projection is not None
        remaining_projection = project_cp_scale_canonical_stage(
            composition,
            CPScaleCanonicalStage.REMAINING,
            control_plane_capabilities=(
                packet_tracer_control_plane_capabilities(packet_tracer_version)
            ),
        )
        remaining_delta = project_cp_scale_canonical_delta(
            previous_projection.topology, remaining_projection.topology,
        )
        if remaining_delta.devices or remaining_delta.modules or remaining_delta.links:
            raise CanonicalLiveFailure(
                "The governed remaining-topology reconciliation was not zero-delta."
            )
        remaining_deployment = reconcile_canonical_stage_deployment(
            remaining_projection.topology,
            physical,
            environment_fingerprint=fingerprint,
            verified_core_topology=verified_core_topology,
            verified_core_deployment=verified_core_deployment,
            deployment_id="cp-scale-canonical/remaining/reconciliation",
        )
        if (
            remaining_deployment.status is not PhysicalDeploymentStatus.VERIFIED
            or remaining_deployment.manifest is None
        ):
            raise CanonicalLiveFailure(
                "Remaining canonical topology reconciliation was not VERIFIED: "
                + "; ".join(remaining_deployment.errors)
            )
        remaining_evidence = {
            "stage": CPScaleCanonicalStage.REMAINING.value,
            "physical_delta": {"devices": 0, "modules": 0, "links": 0},
            "physical": remaining_deployment.model_dump(mode="json"),
            "verified": True,
            "verification_scope": "ZERO_DELTA_RECONCILED",
        }
        evidence["stages"].append(remaining_evidence)
        command = _checkpoint(
            CPScaleCanonicalStage.REMAINING.value,
            evidence,
            session_source_head=session_source_head,
        )
        if command == "retain":
            raise CanonicalLiveFailure(
                "Retention is forbidden before full CP-SCALE qualification."
            )

        assert stage_snapshot is not None
        if not transport.is_connected:
            raise CanonicalLiveFailure(
                "Packet Tracer bridge was not freshly connected before full qualification."
            )
        full_resume_observations = [
            physical.observe_workspace(),
            physical.observe_workspace(),
        ]
        full_resume_errors = [
            canonical_stage_resume_error(
                stage_snapshot, observation, remaining_projection.topology,
            )
            for observation in full_resume_observations
        ]
        evidence.setdefault("resume_gates", []).append({
            "before_stage": "full-qualification",
            "bridge": transport.status_dict(),
            "observations": [
                item.compact_summary() for item in full_resume_observations
            ],
            "errors": full_resume_errors,
        })
        if any(full_resume_errors):
            raise CanonicalLiveFailure(
                "Retained workspace drifted before full qualification: "
                + next(item for item in full_resume_errors if item)
            )

        full_projection = _full_qualification_projection(composition)
        active_network_projection["projection"] = full_projection
        full_deployment = reconcile_canonical_stage_deployment(
            full_projection.topology,
            physical,
            environment_fingerprint=fingerprint,
            verified_core_topology=verified_core_topology,
            verified_core_deployment=verified_core_deployment,
            deployment_id="cp-scale-canonical/full-qualification",
        )
        full_evidence, _, stage_snapshot, _ = _execute_stage(
            full_projection,
            composition=composition,
            deployment=full_deployment,
            delta_deployment=None,
            physical=physical,
            configuration_runtime=configuration_runtime,
            control_runtime=control_runtime,
            voice_runtime=voice_runtime,
            transport=transport,
            fingerprint=fingerprint,
            packet_tracer_version=packet_tracer_version,
            verified_serial_topology=verified_serial_topology,
            verified_serial_manifest=verified_serial_manifest,
            previous_projection=previous_projection,
            previous_configuration=configuration,
            previous_voice_action_results=previous_voice_action_results,
            previous_control_plane_action_results=(
                previous_control_plane_action_results
            ),
        )
        full_evidence["stage"] = "full-qualification"
        evidence["full_qualification"] = full_evidence
        evidence["live_devices"] = len(composition.topology.devices)
        evidence["live_links"] = len(composition.topology.links)
        command = _checkpoint(
            "full-qualification",
            evidence,
            session_source_head=session_source_head,
        )
        disposition = canonical_final_disposition(
            command,
            retain_authorized=retain_on_full_verification,
        )
        evidence["final_disposition"] = disposition.value
        evidence["closure"] = "CP_SCALE_GOVERNED_VOICE_VERIFIED_PRECLEANUP"
        evidence["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_evidence(evidence)
        precleanup_archive = archive("precleanup", evidence)
        evidence["canonical_evidence_precleanup"] = precleanup_archive

        if disposition is CPScaleFinalDisposition.RETAIN:
            evidence["presentation_retained"] = True
            evidence["closure"] = "CP_SCALE_GOVERNED_VOICE_VERIFIED_RETAINED"
            retain_confirmed = True
            _write_evidence(evidence)
            _write_checkpoint_summary(
                "full-qualification",
                evidence,
                destination=FINAL_CHECKPOINT_PATH,
            )
            print(json.dumps({
                "event": "PRESENTATION_RETAINED",
                "devices": evidence["live_devices"],
                "links": evidence["live_links"],
                "evidence_path": str(EVIDENCE_PATH),
                "canonical_archive": precleanup_archive,
            }), flush=True)
            return _settled(0)

        cleanup_result = _cleanup_owned(
            physical, composition.topology, owned_device_ids, baseline,
        )
        cleanup_attempted = True
        cleanup_realtime = observe_cleanup_realtime()
        evidence["cleanup"] = cleanup_result
        evidence["cleanup_realtime"] = cleanup_realtime
        if not cleanup_result.get("verified") or not cleanup_realtime["verified"]:
            raise CanonicalLiveFailure(
                "Canonical verification completed, but cleanup/restoration did "
                "not verify: "
                + str(
                    cleanup_result.get("restoration_error")
                    or cleanup_realtime.get("error")
                )
            )
        evidence["closure"] = "CP_SCALE_GOVERNED_VOICE_VERIFIED_AND_CLEANED"
        evidence["cleanup_completed_at"] = datetime.now(timezone.utc).isoformat()
        cleanup_attestation = {
            "schema": "cp-scale-canonical-cleanup-attestation-v1",
            "run_identity": run_identity,
            "source_head": session_source_head,
            "canonical_evidence_precleanup": precleanup_archive,
            "cleanup": cleanup_result,
            "cleanup_realtime": cleanup_realtime,
            "closure": evidence["closure"],
            "cleanup_completed_at": evidence["cleanup_completed_at"],
        }
        evidence["cleanup_attestation"] = archive(
            "cleanup", cleanup_attestation,
        )
        cleanup_attestation_archived = True
        _write_evidence(evidence)
        # Only a terminal, fully verified run may update the tracked reference
        # summary. Intermediate progress remains durable under ignored data/
        # so its own repository gate never demands a progress commit.
        _write_checkpoint_summary(
            "full-qualification",
            evidence,
            destination=FINAL_CHECKPOINT_PATH,
        )
        print(json.dumps({
            "event": "CANONICAL_VERIFIED_AND_CLEANED",
            "devices": evidence["live_devices"],
            "links": evidence["live_links"],
            "evidence_path": str(EVIDENCE_PATH),
            "canonical_archive": precleanup_archive,
            "cleanup_attestation": evidence["cleanup_attestation"],
        }), flush=True)
        return _settled(0)
    except Exception as exc:
        archived_precleanup = evidence.get("canonical_evidence_precleanup")
        if precleanup_archive is None and isinstance(archived_precleanup, dict):
            precleanup_archive = archived_precleanup
        cleanup_attempted = cleanup_attempted or isinstance(
            evidence.get("cleanup"), dict,
        )
        cleanup_attestation_archived = (
            cleanup_attestation_archived
            or isinstance(evidence.get("cleanup_attestation"), dict)
        )
        evidence["failure"] = f"{type(exc).__name__}: {exc}"
        partial = getattr(exc, "stage_evidence", None) or pending_stage_evidence
        if isinstance(partial, dict):
            # Durable, and marked for what it is: this stage did not pass.
            evidence.pop("active_stage", None)
            evidence.setdefault("stages", []).append({
                **partial, "stage_outcome": "failed",
            })
        return _settled(1)
    finally:
        # A cancellation travelling out of _finalize keeps travelling: it never
        # reaches this test and is never turned into a code.
        if _finalize() and settled_outcome == 0:
            # No primary cause to preserve, so the unfinished finalization is
            # itself the failure. Codes 1 and 2 already carry their own.
            return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Authorize the canonical typed mutations after every hard gate.",
    )
    parser.add_argument("--packet-tracer-version", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument(
        "--target-stage",
        choices=[item.value for item in CPScaleCanonicalTarget],
        default=CPScaleCanonicalTarget.FULL_QUALIFICATION.value,
        help="Stop with governed cleanup at Router0 or run full qualification.",
    )
    parser.add_argument(
        "--retain-on-full-verification",
        action="store_true",
        help="Permit final retention, but only after the final 'retain' command.",
    )
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({
            "hard_stop": "--execute is required; no Packet Tracer mutation occurred.",
        }))
        return 2
    return run(
        args.packet_tracer_version,
        expected_head=args.expected_head,
        retain_on_full_verification=args.retain_on_full_verification,
        target_stage=args.target_stage,
    )


if __name__ == "__main__":
    raise SystemExit(main())
