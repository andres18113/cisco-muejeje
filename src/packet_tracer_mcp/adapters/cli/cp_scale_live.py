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
import json
import sys
from pathlib import Path

from packet_tracer_mcp.application.cp_scale_live import (
    CPScaleLiveRequest,
    CPScaleLocalPreflight,
)
from packet_tracer_mcp.application.cp_scale_live.backend import CPScaleBackendQualification
from packet_tracer_mcp.application.cp_scale_live.build_policy import CPScaleBuildPolicy
from packet_tracer_mcp.application.cp_scale_live.checkpoint import (
    CPScaleCheckpoint,
    CPScaleCheckpointDecision,
    CPScaleCheckpointPrompt,
)
from packet_tracer_mcp.application.cp_scale_live.cleanup import CPScaleCleanup
from packet_tracer_mcp.application.cp_scale_live.completion import CPScaleCompletion
from packet_tracer_mcp.application.cp_scale_live.configuration_stage import CPScaleConfigurationStage
from packet_tracer_mcp.application.cp_scale_live.control_plane_stage import CPScaleControlPlaneStage
from packet_tracer_mcp.application.cp_scale_live.coordinator import CPScaleLiveCoordinator
from packet_tracer_mcp.application.cp_scale_live.errors import CanonicalLiveFailure
from packet_tracer_mcp.application.cp_scale_live.forwarding_stage import CPScaleForwardingStage
from packet_tracer_mcp.application.cp_scale_live.reconciliation import CPScaleReconciliation
from packet_tracer_mcp.application.cp_scale_live.run_contracts import CPScaleRunOutcome
from packet_tracer_mcp.application.cp_scale_live.session import CPScaleRuntimeResources
from packet_tracer_mcp.application.cp_scale_live.stage_executor import CPScaleStageExecutor
from packet_tracer_mcp.application.cp_scale_live.voice_stage import CPScaleVoiceStage
from packet_tracer_mcp.application.use_cases.apply_configuration import ConfigurationApplicator
from packet_tracer_mcp.application.use_cases.apply_control_plane import ControlPlaneApplicator
from packet_tracer_mcp.application.use_cases.apply_voice import VoiceApplicator
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    CPScaleCanonicalTarget,
    canonical_cp_scale_target_contract,
)
from packet_tracer_mcp.application.use_cases.deploy_enterprise_topology import (
    disposable_workspace_error,
)
from packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    EXPECTED_BRANCH,
    EXPECTED_UPSTREAM,
)
from packet_tracer_mcp.infrastructure.catalog.control_plane_capabilities import (
    packet_tracer_control_plane_capabilities,
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
from packet_tracer_mcp.infrastructure.execution.cp_scale_live_backend import (
    CPScaleCapabilityAdapters,
    CPScaleCheckpointRepositoryReader,
)
from packet_tracer_mcp.infrastructure.execution.cp_scale_live_preflight import (
    GitCPScaleRepositoryReader,
    PacketTracerImportIsolationReader,
    PowerShellPacketTracerProcessReader,
    PythonRuntimeEvidenceReader,
)
from packet_tracer_mcp.infrastructure.execution.file_bridge import FileBridge
from packet_tracer_mcp.infrastructure.execution.factory_module_preparation import (
    PacketTracerFactoryModulePreparer,
)
from packet_tracer_mcp.infrastructure.execution.live_bridge import (
    PacketTracerHttpTransport,
)
from packet_tracer_mcp.infrastructure.execution.live_environment_preflight import (
    packet_tracer_process_error,
)
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    GOVERNED_ROOT_ENV_VAR,
    governed_root_from_env,
)
from packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
)
from packet_tracer_mcp.infrastructure.diagnostics.cp_scale_live import (
    PacketTracerCPScaleDiagnostics,
)
from packet_tracer_mcp.infrastructure.persistence.cp_scale_live import CPScaleLivePersistence
from packet_tracer_mcp.infrastructure.execution.cp_scale_live_session import PacketTracerCPScaleSession
from packet_tracer_mcp.infrastructure.observation.cp_scale_live import PacketTracerCPScaleObservations
from packet_tracer_mcp.infrastructure.observation.cp_scale_live_run import CPScaleActiveProjection, PacketTracerCPScaleRunObservations

def build_local_preflight(governed_root: Path) -> CPScaleLocalPreflight:
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


def build_stage_executor(
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


def build_coordinator(request: CPScaleLiveRequest, *, governed_root: Path) -> CPScaleLiveCoordinator:
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
                mutation_timeout_seconds=30.0, observation_timeout_seconds=12.0,
                factory_module_preparer=PacketTracerFactoryModulePreparer(
                    transport.send_and_wait, request.packet_tracer_version,
                )), runtime_factory=runtimes)

    def stage_factory(session, resources):
        return build_stage_executor(physical=session.physical, configuration_runtime=resources.configuration,
            control_runtime=resources.control_plane, voice_runtime=resources.voice,
            transport=session.transport, packet_tracer_version=request.packet_tracer_version)

    capabilities = CPScaleCapabilityAdapters(governed_root)
    return CPScaleLiveCoordinator(preflight=build_local_preflight(governed_root),
        session_factory=session_factory, stage_factory=stage_factory,
        observations_factory=lambda session: PacketTracerCPScaleRunObservations(session.transport, active),
        backend=CPScaleBackendQualification(compose=capabilities.compose, discovery_factory=capabilities.discovery,
            file_alive=lambda: FileBridge().pt_alive()),
        build=CPScaleBuildPolicy(capabilities=packet_tracer_control_plane_capabilities(request.packet_tracer_version)),
        persistence=persistence, presentation=presentation,
        checkpoint=CPScaleCheckpoint(repository=CPScaleCheckpointRepositoryReader(governed_root),
            console=CPScaleConsoleCheckpoint(persistence.evidence_path), persistence=persistence),
        completion=CPScaleCompletion(cleanup=CPScaleCleanup()))
def run(
    packet_tracer_version: str,
    *,
    expected_head: str,
    retain_on_full_verification: bool,
    target_stage: CPScaleCanonicalTarget | str = (
        CPScaleCanonicalTarget.FULL_QUALIFICATION
    ),
) -> int:
    governed_root = governed_root_from_env()
    if governed_root is None:
        print(json.dumps({
            "hard_stop": (
                f"{GOVERNED_ROOT_ENV_VAR} must declare the governed checkout; "
                "no Packet Tracer mutation occurred."
            ),
        }))
        return 2
    request = CPScaleLiveRequest(packet_tracer_version, expected_head, retain_on_full_verification, target_stage)
    result = build_coordinator(request, governed_root=governed_root).run(request)
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
