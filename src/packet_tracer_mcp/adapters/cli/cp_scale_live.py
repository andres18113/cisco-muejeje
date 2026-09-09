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

from packet_tracer_mcp.application.cp_scale_live.errors import CanonicalLiveFailure
from packet_tracer_mcp.infrastructure.persistence.cp_scale_live import CPScaleLivePersistence
from packet_tracer_mcp.application.cp_scale_live.coordinator import CPScaleLiveCoordinator
from packet_tracer_mcp.application.cp_scale_live.backend import CPScaleBackendQualification
from packet_tracer_mcp.application.cp_scale_live.build_policy import CPScaleBuildPolicy
from packet_tracer_mcp.application.cp_scale_live.checkpoint import CPScaleCheckpoint, CPScaleCheckpointDecision, CPScaleCheckpointPrompt
from packet_tracer_mcp.application.cp_scale_live.cleanup import CPScaleCleanup
from packet_tracer_mcp.application.cp_scale_live.completion import CPScaleCompletion
from packet_tracer_mcp.application.cp_scale_live.session import CPScaleRuntimeResources
from packet_tracer_mcp.application.cp_scale_live.run_contracts import CPScaleRunOutcome
from packet_tracer_mcp.infrastructure.execution.cp_scale_live_session import PacketTracerCPScaleSession
from packet_tracer_mcp.infrastructure.execution.cp_scale_live_backend import CPScaleCapabilityAdapters, CPScaleCheckpointRepositoryReader
from packet_tracer_mcp.infrastructure.observation.cp_scale_live_run import CPScaleActiveProjection, PacketTracerCPScaleRunObservations

GOVERNED_ROOT = Path(packet_tracer_mcp.__file__).resolve().parents[2]
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

def _build_local_preflight(governed_root: Path = GOVERNED_ROOT) -> CPScaleLocalPreflight:
    """Compose local readers without granting any backend or product authority."""

    return CPScaleLocalPreflight(
        governed_root=governed_root,
        runtime_reader=PythonRuntimeEvidenceReader(),
        import_reader=PacketTracerImportIsolationReader(),
        repository_reader=GitCPScaleRepositoryReader(),
        process_reader=PowerShellPacketTracerProcessReader(),
        process_error_policy=packet_tracer_process_error,
        expected_branch=EXPECTED_BRANCH,
        expected_upstream=EXPECTED_UPSTREAM,
        target_resolver=canonical_cp_scale_target_contract,
    )

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

class CPScaleConsolePresentation:
    def __init__(self, evidence_path: Path) -> None:
        self.evidence_path = evidence_path

    def core_rematerialized(self) -> None:
        print(json.dumps({"event": "CORE_REMATERIALIZED", "devices": 3, "links": 3}), flush=True)

    def terminal(self, event: str, report) -> None:
        payload = {"event": event, "devices": report.live_devices, "links": report.live_links,
                   "evidence_path": str(self.evidence_path),
                   "canonical_archive": report.canonical_evidence_precleanup.model_dump(mode="json")}
        if event == "ROUTER0_BRANCH_VERIFIED_AND_CLEANED":
            payload["stage"] = CPScaleCanonicalStage.ROUTER0_BRANCH.value
        if report.cleanup_attestation is not None:
            payload["cleanup_attestation"] = report.cleanup_attestation.model_dump(mode="json")
        print(json.dumps(payload), flush=True)

    def finalization_incomplete(self, report) -> None:
        _emit_finalization_report({"event": "CP_SCALE_FINALIZATION_INCOMPLETE",
            "run_identity": report.run_identity, "primary_failure": report.failure,
            "hard_stop": report.hard_stop, "finalization_errors": list(report.finalization_errors)})


class CPScaleConsoleCheckpoint:
    def __init__(self, evidence_path: Path) -> None:
        self.evidence_path = evidence_path

    def decide(self, prompt: CPScaleCheckpointPrompt) -> CPScaleCheckpointDecision:
        print(json.dumps({"event": "CHECKPOINT_READY", "stage": prompt.stage,
            "evidence_path": str(self.evidence_path), "devices": prompt.devices,
            "links": prompt.links}), flush=True)
        command = input().strip().casefold()
        try:
            return CPScaleCheckpointDecision(command)
        except ValueError as exc:
            raise CanonicalLiveFailure(f"Checkpoint {prompt.stage!r} received operator command {command!r}; aborting.") from exc


def _build_coordinator(request: CPScaleLiveRequest, *, governed_root: Path = GOVERNED_ROOT) -> CPScaleLiveCoordinator:
    persistence = CPScaleLivePersistence(governed_root)
    presentation = CPScaleConsolePresentation(persistence.evidence_path)
    active = CPScaleActiveProjection()

    def runtimes(transport, physical) -> CPScaleRuntimeResources:
        observation = PacketTracerCPScaleRunObservations(transport, active)
        configuration = PacketTracerEnterpriseConfigurationRuntime(lambda: _inventory(physical),
            transport.send, transport.send_and_wait, l3_timeout_seconds=20.0,
            trunk_transition_observer=observation.trunk_transition)
        control = PacketTracerEnterpriseControlPlaneRuntime(lambda: _inventory(physical), transport.send, transport.send_and_wait)
        voice = PacketTracerEnterpriseVoiceRuntime(lambda: _inventory(physical), transport.send, transport.send_and_wait,
            registration_timeout_seconds=180.0, convergence_interval_seconds=5.0)
        return CPScaleRuntimeResources(configuration, control, voice)

    def session_factory() -> PacketTracerCPScaleSession:
        return PacketTracerCPScaleSession(transport_factory=PacketTracerHttpTransport,
            physical_factory=lambda transport: PacketTracerPhysicalTopologyRuntime(transport.send_and_wait,
                mutation_timeout_seconds=30.0, observation_timeout_seconds=12.0), runtime_factory=runtimes)

    def stage_factory(session, resources):
        return _build_stage_executor(physical=session.physical, configuration_runtime=resources.configuration,
            control_runtime=resources.control_plane, voice_runtime=resources.voice,
            transport=session.transport, packet_tracer_version=request.packet_tracer_version)

    capabilities = CPScaleCapabilityAdapters(governed_root)
    return CPScaleLiveCoordinator(preflight=_build_local_preflight(governed_root),
        session_factory=session_factory, stage_factory=stage_factory,
        observations_factory=lambda session: PacketTracerCPScaleRunObservations(session.transport, active),
        backend=CPScaleBackendQualification(compose=capabilities.compose, discovery_factory=capabilities.discovery,
            file_alive=lambda: FileBridge().pt_alive()),
        build=CPScaleBuildPolicy(capabilities=packet_tracer_control_plane_capabilities(request.packet_tracer_version)),
        persistence=persistence, presentation=presentation,
        checkpoint=CPScaleCheckpoint(repository=CPScaleCheckpointRepositoryReader(governed_root),
            console=CPScaleConsoleCheckpoint(persistence.evidence_path), persistence=persistence),
        completion=CPScaleCompletion(cleanup=CPScaleCleanup()))


def _write_evidence(evidence: dict[str, object]) -> None:
    CPScaleLivePersistence(GOVERNED_ROOT).write_evidence(evidence)


def _write_checkpoint_summary(stage: str, evidence: dict[str, object], *, destination: Path = CHECKPOINT_PATH) -> None:
    CPScaleLivePersistence(GOVERNED_ROOT).write_checkpoint_summary(stage, evidence, destination=destination)


def run(
    packet_tracer_version: str,
    *,
    expected_head: str,
    retain_on_full_verification: bool,
    target_stage: CPScaleCanonicalTarget | str = (
        CPScaleCanonicalTarget.FULL_QUALIFICATION
    ),
) -> int:
    request = CPScaleLiveRequest(packet_tracer_version, expected_head, retain_on_full_verification, target_stage)
    result = _build_coordinator(request).run(request)
    return {CPScaleRunOutcome.COMPLETED: 0, CPScaleRunOutcome.FAILED: 1, CPScaleRunOutcome.REJECTED: 2}[result.outcome]


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
