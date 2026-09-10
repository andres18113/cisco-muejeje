"""Governed PSE capacity qualification on an empty, untitled PT workspace.

Only model and qualification identity are caller supplied. The ordered binding
set comes from the Router0 capacity plan. Positive schema-3 runtime evidence is
persisted only after cleanup, ephemeral safety admission and schema decoding.
No Packet Tracer file operation is authorized or executed by this runner.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from secrets import token_hex, token_urlsafe
import sys
from types import SimpleNamespace

import packet_tracer_mcp
from packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus, EvidenceSource,
)
from packet_tracer_mcp.application.use_cases.plan_cp_scale_poe_capacity import (
    cp_scale_poe_capacity_qualification_plan,
)
from packet_tracer_mcp.domain.enterprise.models.poe_capacity import PoEModelQualificationPlan
from packet_tracer_mcp.domain.enterprise.models.discovery import (
    BackendVersionProvenance, CapabilityProbeResult, CapabilitySnapshot,
    CapabilityVerificationMethod, CleanupStatus, EphemeralUntitledWorkspaceSafetyEvidence,
    ProbeContext, ProbeExecutionStatus, ProbeIsolationLevel, ProbeSession, ProbeSessionResult,
    semantic_fingerprint,
)
from packet_tracer_mcp.domain.enterprise.rules.live_session_safety import (
    validate_live_session_positive_admission,
)
from packet_tracer_mcp.domain.enterprise.services.poe_claims import (
    _AUTHORIZED_OBSERVATION_METHODS,
)
from packet_tracer_mcp.domain.enterprise.services.poe_pse_multiport_claims import (
    PSE_MULTI_PORT_SCHEMA_VERSION, PoEPseBindingCapture, PoEPseMultiPortCapture,
    PoEPseMultiPortDeliveryScope, decode_poe_pse_multi_port_delivery_scope,
    encode_poe_pse_multi_port_dimensions,
)
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
)
from packet_tracer_mcp.infrastructure.execution.live_bridge import PTCommandBridge
from packet_tracer_mcp.infrastructure.execution.pt_file_operations import (
    PacketTracerFileOperationDenied,
    PacketTracerFileOperationGuard,
)
from packet_tracer_mcp.infrastructure.execution.poe2_evidence import (
    BUILD, START_HEAD, COMPLETENESS_KEYS, completeness,
)
from packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import CapabilitySnapshotStore
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    parse_show_power_inline, classify_poe_inline_delivery,
)
from packet_tracer_mcp.shared.utils import resolve_within, safe_name_component

from poe2_ap_live import (
    Experiment, authenticated_status, command, prove_processes, utc,
)
from poe_inline_calibration_live import PoEInlineMode

ROOT = Path(__file__).resolve().parents[1]
REPO = "andres18113/cisco-muejeje"
BRANCH = "feature/runtime-ripv2"
# 100-character path component budget: 6 prefix + 68 caller metadata +
# 1 separator + 16 UTC timestamp + 1 separator + 8 random hex characters.
QUALIFICATION_ID_MAX_LENGTH = 68


def source_baseline(plan: PoEModelQualificationPlan) -> dict:
    branch = command("git", "branch", "--show-current")
    if branch != BRANCH:
        raise RuntimeError("Wrong branch")
    if command("git", "status", "--porcelain"):
        raise RuntimeError("Worktree must be clean")
    sha = command("git", "rev-parse", "HEAD")
    command("git", "merge-base", "--is-ancestor", START_HEAD, sha)
    remote = json.loads(command(
        "gh", "api", "repos/" + REPO + "/git/ref/heads/" + BRANCH,
    ))["object"]["sha"]
    if sha != remote:
        raise RuntimeError("Local and remote SHA differ")
    runs = json.loads(command(
        "gh", "run", "list", "--repo", REPO, "--commit", sha,
        "--json", "databaseId,name,headSha,status,conclusion,url",
    ))
    run = next(r for r in runs if r["name"] == "tests" and r["headSha"] == sha)
    jobs = json.loads(command(
        "gh", "api",
        "repos/" + REPO + "/actions/runs/" + str(run["databaseId"]) + "/jobs",
    ))["jobs"]
    if len(jobs) != 4 or any(
        job["conclusion"] != "success" or job["head_sha"] != sha for job in jobs
    ):
        raise RuntimeError("Exact SHA Actions is not 4/4 green")
    if _AUTHORIZED_OBSERVATION_METHODS != frozenset({"manual_visible_power_state"}):
        raise RuntimeError("Strict E5 manual allowlist changed")
    return dict(
        verified_at_utc=utc(), local_head=sha, remote_head=remote, actions_run=run,
        jobs=[{k: job[k] for k in ("name", "conclusion", "head_sha", "html_url")}
              for job in jobs],
        strict_e5_manual_allowlist=True, qualification_plan=plan.model_dump(mode="json"),
        source_branch=branch, source_tree=command("git", "rev-parse", "HEAD^{tree}"),
        worktree_clean=True,
        initial_START_HEAD_verified=True,
    )


def governed_plan(model: str) -> PoEModelQualificationPlan:
    return cp_scale_poe_capacity_qualification_plan(BUILD).for_model(model)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--qualification-id", required=True, help="Exact safe ID, at most 68 characters.")
    args = parser.parse_args(argv)
    _validate_qualification_id(args.qualification_id)
    governed_plan(args.model)
    return args


def _validate_qualification_id(qualification_id: str) -> None:
    if (qualification_id != safe_name_component(qualification_id)
            or len(qualification_id) > QUALIFICATION_ID_MAX_LENGTH):
        raise ValueError("qualification-id must be an exact safe name component of at most 68 characters")


def qualification_run_id(qualification_id: str) -> str:
    """Preserve the full uniqueness suffix; never sanitize/truncate a run ID."""
    _validate_qualification_id(qualification_id)
    run_id = ("poe3b-" + qualification_id + "-"
              + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + token_hex(4))
    if run_id != safe_name_component(run_id):
        raise ValueError("Complete run identity does not fit one exact safe component")
    return run_id


@dataclass(frozen=True)
class ArtifactReservation:
    run_id: str
    directory: Path
    directory_identity: tuple[int, int]


def _artifact_directory(run_id: str) -> Path:
    if run_id != safe_name_component(run_id):
        raise ValueError("Artifact run identity must be exact and untruncated")
    return resolve_within(ROOT,
        Path("docs/reference/cp-scale/canonical-live-evidence") / safe_name_component(run_id))


def reserve_artifacts(qualification_id: str) -> ArtifactReservation:
    """Exclusively reserve the exact destination before any PT mutation.

    An empty directory does not dirty the frozen Git source. This is a local
    evidence-directory operation, never a Packet Tracer workspace operation.
    """
    run_id = qualification_run_id(qualification_id)
    directory = _artifact_directory(run_id)
    directory.mkdir(parents=True, exist_ok=False)
    identity = directory.stat()
    return ArtifactReservation(run_id, directory, (identity.st_dev, identity.st_ino))


def validate_artifact_reservation(artifacts: ArtifactReservation | None,
                                  expected_run_id: str | None = None) -> Path:
    """Require the same exclusively created directory before mutation or save."""
    if not isinstance(artifacts, ArtifactReservation):
        raise ValueError("Artifact destination has not been reserved")
    if expected_run_id is not None and artifacts.run_id != expected_run_id:
        raise ValueError("Artifact reservation belongs to a different run")
    if (artifacts.directory != _artifact_directory(artifacts.run_id)
            or artifacts.directory.is_symlink() or not artifacts.directory.is_dir()):
        raise ValueError("Artifact reservation path changed or disappeared")
    identity = artifacts.directory.stat()
    if (identity.st_dev, identity.st_ino) != artifacts.directory_identity:
        raise ValueError("Artifact reservation directory was replaced")
    return artifacts.directory


def create_fixture(exp: Experiment, plan: PoEModelQualificationPlan,
                   attempted: list[str], created: list[str], *,
                   artifacts: ArtifactReservation) -> dict:
    """Create exactly the governed scope, tracking attempts before each mutation."""
    validate_artifact_reservation(artifacts)
    attempted.append(exp.switch)
    switch = exp.fixture.create_device(plan.candidate_model, exp.switch,
        tuple(b.switch_port for b in plan.bindings), arm="candidate")
    created.append(exp.switch)
    if switch.model != plan.candidate_model:
        raise RuntimeError("Fixture switch model readback mismatch")
    endpoints, links = [], []
    for index, binding in enumerate(plan.bindings, start=1):
        name = exp.endpoint + "-" + str(index)
        attempted.append(name)
        phone = exp.fixture.create_device(binding.endpoint_model, name,
            (binding.endpoint_port,), arm="candidate")
        created.append(name)
        if phone.model != binding.endpoint_model:
            raise RuntimeError("Fixture endpoint model readback mismatch")
        link = exp.fixture.create_link(switch, binding.switch_port, phone, binding.endpoint_port)
        endpoints.append(phone.model_dump(mode="json"))
        links.append(link.model_dump(mode="json"))
    return dict(switch=switch.model_dump(mode="json"), endpoints=endpoints, links=links)


def cleanup_fixture(exp: Experiment, attempted: list[str], problems: list[str]) -> list[str]:
    deleted = []
    for name in reversed(attempted):
        try:
            if exp.fixture.delete_device(name):
                deleted.append(name)
            else:
                problems.append("Cleanup did not verify deletion: " + name)
        except Exception as exc:
            problems.append("Cleanup " + name + ": " + str(exc))
    return deleted


def pse_capture(plan: PoEModelQualificationPlan, label: str, capture,
                switch_name: str) -> PoEPseMultiPortCapture:
    """Check both complete captures before translating every ordered binding."""
    if (not capture.stable or capture.observation.get("raw_output") !=
            capture.repeat_observation.get("raw_output")):
        raise ValueError("Capture is not stable")
    translated = []
    for observation in (capture.observation, capture.repeat_observation):
        gates = completeness(observation, capture.expected_prompt, capture.stable, switch_name)
        if (set(gates) != COMPLETENESS_KEYS or not all(gates.values())
                or capture.table_completeness != gates
                or observation.get("status") != "observed" or observation.get("refusal_reason")):
            raise ValueError("Incomplete or refused governed capture")
        output = observation.get("raw_output", "")
        if (hashlib.sha256(output.encode()).hexdigest() != capture.raw_sha256
                or output != observation["command_result"].get("output")):
            raise ValueError("Capture raw output disagrees with dispatch")
        ports = observation.get("ports", [])
        if tuple(p.get("port") for p in ports) != tuple(b.switch_port for b in plan.bindings):
            raise ValueError("Capture does not cover the exact ordered plan")
        rows = []
        table = parse_show_power_inline(output)
        for binding, port in zip(plan.bindings, ports):
            row = port["row"]
            raw_row = table.row_for(binding.switch_port)
            if (row != (asdict(raw_row) if raw_row is not None else None)
                    or port["delivery"] != classify_poe_inline_delivery(
                        output, binding.switch_port, capture_complete=True).value):
                raise ValueError("Raw table and typed binding observation disagree")
            if row is not None and row["admin"] != _MODE_BY_LABEL[label]:
                raise ValueError("Capture admin mode disagrees with causal step")
            if port["delivery"] not in {"delivering", "not_delivering"}:
                raise ValueError("Unobservable delivery")
            rows.append(PoEPseBindingCapture(
                binding.switch_port, binding.endpoint_model, binding.endpoint_port,
                row["oper"] if row is not None else "absent",
                float(row["power_watts"]) if row is not None else 0.0,
                row is not None, port["delivery"] == "delivering"))
        translated.append(tuple(rows))
    if translated[0] != translated[1]:
        raise ValueError("Repeated binding observations disagree")
    return PoEPseMultiPortCapture(label, _MODE_BY_LABEL[label], translated[0])


_MODE_BY_LABEL = {"AUTO_1": "auto", "NEVER": "never", "AUTO_2": "auto"}


def ephemeral_file_operation_guard() -> PacketTracerFileOperationGuard:
    """Create the PT-file boundary used for one governed ephemeral session."""

    return PacketTracerFileOperationGuard.ephemeral()


def _crash_state_from_process_continuity(
    before: tuple[int, ...] | None,
    after: tuple[int, ...] | None,
) -> bool | None:
    """Separate observed process loss from composite runtime health."""

    if before is None or after is None or len(before) != 1:
        return None
    return False if before[0] in after else True


def pse_scope_for(
    *,
    plan: PoEModelQualificationPlan,
    run_id: str,
    observed_at: str,
    captures: tuple[PoEPseMultiPortCapture, ...],
    gates: tuple[str, ...],
) -> PoEPseMultiPortDeliveryScope:
    """Assemble the measured scope under whichever schema is in force.

    Kept separate from `main` so the producer can be exercised offline: a
    producer pinned to a literal version silently outlives its own contract.
    """
    return PoEPseMultiPortDeliveryScope(
        schema_version=PSE_MULTI_PORT_SCHEMA_VERSION,
        switch_model=plan.candidate_model, bindings=plan.bindings,
        packet_tracer_build=plan.packet_tracer_build,
        observer_id="GovernedPoEInlineObserver", experiment_id=run_id,
        observed_at=observed_at, captures=captures, gates=gates,
        simultaneous_active_ports=plan.simultaneous_active_ports, cleanup_status="clean",
        inventory_restoration="restored",
    )


def ephemeral_safety_for(
    baseline: dict,
    restoration: dict,
    safety: dict,
    problems: list[str],
    *,
    file_operations: PacketTracerFileOperationGuard,
) -> EphemeralUntitledWorkspaceSafetyEvidence:
    """Project acquired fields only; missing measurements stay unproven."""
    if not isinstance(file_operations, PacketTracerFileOperationGuard):
        raise ValueError("Observed Packet Tracer file-operation guard is required")
    file_ledger = file_operations.snapshot()
    initial, final = baseline.get("environment", {}), restoration.get("environment_after", {})
    def pids(facts):
        processes = facts.get("processes")
        return (tuple(sorted(p["ProcessId"] for p in processes if p["Name"] == "PacketTracer.exe"))
                if processes is not None else None)
    before, after = pids(baseline), pids(safety)
    healthy = (baseline.get("bridge_healthy") is True and safety.get("bridge_healthy") is True
               and before is not None and len(before) == 1 and before == after
               and safety.get("transport_problems") == [])
    crash_detected = _crash_state_from_process_continuity(before, after)
    # These summaries derive from the recorded checks, never substitute for them.
    clean = (healthy and not problems and restoration.get("fixture_removed") is True
             and restoration.get("inventory_restored") is True
             and initial == final and bool(initial)
             and baseline.get("mailbox_entries") == safety.get("mailbox_entries") == ()
             and baseline.get("worktree_clean") is True and safety.get("worktree_clean") is True
             and baseline.get("source_branch") == safety.get("source_branch")
             and baseline.get("local_head") == safety.get("source_head")
             and baseline.get("source_tree") == safety.get("source_tree")
             and file_ledger.ephemeral_safe)
    failure_reasons = list(problems) + list(safety.get("transport_problems") or [])
    if not file_ledger.ephemeral_safe:
        failure_reasons.append(
            "Packet Tracer file-operation ledger is not empty under EPHEMERAL policy."
        )
    if crash_detected is True:
        failure_reasons.append(
            "Packet Tracer process loss was observed during the governed session."
        )
    elif crash_detected is None:
        failure_reasons.append(
            "Packet Tracer crash status is indeterminate from process evidence."
        )
    return EphemeralUntitledWorkspaceSafetyEvidence(
        initial_device_count=initial.get("devices"), final_device_count=final.get("devices"),
        initial_link_count=initial.get("links"), final_link_count=final.get("links"),
        initial_saved_filename=initial.get("saved_filename"), final_saved_filename=final.get("saved_filename"),
        authorized_file_operations=file_ledger.authorized_operations,
        attempted_file_operations=file_ledger.attempted_operations,
        executed_file_operations=file_ledger.executed_operations,
        denied_file_operations=file_ledger.denied_operations,
        initial_inventory_fingerprint=baseline.get("inventory_fingerprint", ""),
        final_inventory_fingerprint=restoration.get("inventory_fingerprint_after", ""),
        fixture_removed=restoration.get("fixture_removed"),
        initial_realtime=initial.get("simulation_mode") is False,
        final_realtime=final.get("simulation_mode") is False,
        packet_tracer_pids_before=before, packet_tracer_pids_after=after,
        bridge_healthy_before=baseline.get("bridge_healthy"), bridge_healthy_after=safety.get("bridge_healthy"),
        mailbox_entries_before=baseline.get("mailbox_entries"), mailbox_entries_after=safety.get("mailbox_entries"),
        source_branch_before=baseline.get("source_branch", ""), source_branch_after=safety.get("source_branch", ""),
        source_head_before=baseline.get("local_head", ""), source_head_after=safety.get("source_head", ""),
        source_tree_before=baseline.get("source_tree", ""), source_tree_after=safety.get("source_tree", ""),
        worktree_clean_before=baseline.get("worktree_clean"), worktree_clean_after=safety.get("worktree_clean"),
        runtime_healthy=healthy, crash_detected=crash_detected,
        integrity_verified=clean, session_reusable=clean, positive_claim_allowed=clean,
        failure_reasons=failure_reasons,
    )


def persist_qualification(*, plan: PoEModelQualificationPlan,
                          scope: PoEPseMultiPortDeliveryScope, baseline: dict,
                          restoration: dict, safety: dict, problems: list[str],
                          file_operations: PacketTracerFileOperationGuard,
                          artifacts: ArtifactReservation,
                          store: CapabilitySnapshotStore) -> tuple[CapabilitySnapshot, Path]:
    """Release a controlled result only beyond cleanup, safety and schema gates."""
    validate_artifact_reservation(artifacts, scope.experiment_id)
    attempted = restoration.get("attempted", [])
    created = restoration.get("created", [])
    deleted = restoration.get("deleted", [])
    if (problems or restoration.get("inventory_restored") is not True
            or restoration.get("fixture_removed") is not True
            or restoration.get("power_inline_auto_proven") is not True
            or len(attempted) != len(plan.bindings) + 1
            or len(set(attempted)) != len(attempted)
            or created != attempted or len(deleted) != len(attempted)
            or set(deleted) != set(attempted)):
        raise ValueError("Qualification cleanup or fixture creation is incomplete")
    if (plan != governed_plan(plan.candidate_model) or scope.bindings != plan.bindings
            or scope.switch_model != plan.candidate_model
            or scope.packet_tracer_build != plan.packet_tracer_build
            or scope.simultaneous_active_ports != plan.simultaneous_active_ports):
        raise ValueError("Scope differs from governed qualification plan")
    if (baseline.get("environment", {}).get("pt_version") != plan.packet_tracer_build
            or restoration.get("environment_after", {}).get("pt_version") != plan.packet_tracer_build):
        raise ValueError("Acquired Packet Tracer build differs from qualification plan")
    evidence = ephemeral_safety_for(
        baseline,
        restoration,
        safety,
        problems,
        file_operations=file_operations,
    )
    validation = validate_live_session_positive_admission(evidence)
    if not validation.is_valid:
        raise ValueError("LIVE safety refused: " + "; ".join(validation.error_messages()))
    dimensions = encode_poe_pse_multi_port_dimensions(scope)
    # Decoder input is a structural contract candidate, not a released probe.
    candidate = SimpleNamespace(capability="supports_poe", status=CapabilityStatus.SUPPORTED,
        verified=True, observed_value=plan.simultaneous_active_ports, dimensions=dimensions,
        evidence_source=EvidenceSource.CONTROLLED_PROBE, packet_tracer_version=plan.packet_tracer_build)
    decoded = decode_poe_pse_multi_port_delivery_scope(candidate,
        expected_model=plan.candidate_model, expected_packet_tracer_version=plan.packet_tracer_build)
    if decoded is None:
        raise ValueError("Schema decoder refused qualification")
    probe_id = "poe-pse-capacity-qualification"
    mutations = ["temporary-device-attempt:" + name for name in attempted]
    context = ProbeContext(probe_id=probe_id, probe_version="3",
        backend_version=plan.packet_tracer_build, device_model=plan.candidate_model,
        environment_fingerprint=semantic_fingerprint(baseline["environment"]),
        initial_inventory_hash=evidence.initial_inventory_fingerprint,
        final_inventory_hash=evidence.final_inventory_fingerprint, inventory_restored=True,
        isolation_level=ProbeIsolationLevel.FRESH_SESSION_REQUIRED, mutations=mutations,
        cleanup_status=CleanupStatus.CLEAN, result_status=CapabilityStatus.SUPPORTED,
        execution_status=ProbeExecutionStatus.VERIFIED,
        probe_fingerprint=semantic_fingerprint(plan.model_dump(mode="json")), live_session_safety=evidence)
    result = CapabilityProbeResult(probe_id=probe_id, model=plan.candidate_model,
        capability="supports_poe", status=CapabilityStatus.SUPPORTED,
        execution_status=ProbeExecutionStatus.VERIFIED, evidence_source=EvidenceSource.CONTROLLED_PROBE,
        configured=True, verified=True, observed_value=plan.simultaneous_active_ports,
        packet_tracer_version=plan.packet_tracer_build,
        verification_method=CapabilityVerificationMethod.CLI_PLUS_READBACK,
        raw_summary="Governed simultaneous PSE AUTO/NEVER/AUTO qualification.",
        dimensions=dimensions, context=context)
    snapshot = CapabilitySnapshot(packet_tracer_version=plan.packet_tracer_build,
        backend_version_provenance=BackendVersionProvenance.DIRECTLY_OBSERVED,
        environment_fingerprint=context.environment_fingerprint,
        probe_fingerprints={probe_id: context.probe_fingerprint},
        initial_inventory_hash=evidence.initial_inventory_fingerprint,
        final_inventory_hash=evidence.final_inventory_fingerprint, inventory_restored=True,
        session=ProbeSessionResult(session=ProbeSession(session_id=scope.experiment_id,
            packet_tracer_version=plan.packet_tracer_build, created_devices=created,
            mutations=mutations, cleanup_status=CleanupStatus.CLEAN),
            results=[result], cleanup_deleted=deleted, cleanup_failed=[]))
    # This writes evidence JSON to the repository store, not a PT workspace.
    path = store.save_runtime(snapshot)
    return snapshot, path


def main() -> int:
    args = parse_args()
    isolation = ImportIsolationPreflight(ROOT).ensure_isolated()
    if not isolation.isolated:
        raise RuntimeError(isolation.render())
    plan = governed_plan(args.model)
    file_operations = ephemeral_file_operation_guard()
    baseline = source_baseline(plan)
    baseline["processes"] = prove_processes()
    baseline["import_isolation"] = dict(
        result=isolation.render(), executable=sys.executable,
        production_file=packet_tracer_mcp.__file__,
        loaded_namespaces=[n for n in ("packet_tracer_mcp", "src.packet_tracer_mcp")
                           if n in sys.modules],
    )
    artifacts = reserve_artifacts(args.qualification_id)
    run_id = artifacts.run_id
    started = utc()

    exp = Experiment(run_id, switch_ports=tuple(b.switch_port for b in plan.bindings), endpoint_role="PH")
    baseline["bridge_healthy"] = exp.bridge.pt_alive()
    if not baseline["bridge_healthy"]:
        raise RuntimeError("File bridge heartbeat stale")
    baseline["mailbox_entries"] = tuple(sorted(p.name for pattern in ("req_*.js", "res_*.txt")
        for p in exp.bridge.dir.glob(pattern)))
    if baseline["mailbox_entries"]:
        raise RuntimeError("Foreign mailbox residue")
    os.environ["PT_MCP_BRIDGE_TOKEN"] = token_urlsafe(32)
    http = PTCommandBridge(port=54321, token=os.environ["PT_MCP_BRIDGE_TOKEN"])
    http.start()

    captures, pse_captures, problems = [], [], []
    fixture, restoration, safety, raw_files = {}, {}, {}, {}
    attempted, created, deleted = [], [], []
    opening = preexisting = env = None
    creation_started = False
    try:
        baseline["fresh_authenticated_bridge"] = authenticated_status(http)
        env = exp.environment()
        if env.get("pt_version") != BUILD or env.get("simulation_mode") is not False:
            raise RuntimeError("Wrong PT build or mode")
        if env.get("devices") != 0 or env.get("links") != 0 or env.get("saved_filename") != "":
            raise RuntimeError("Requires an empty, untitled semantic baseline")
        baseline["environment"] = env
        opening = exp.fixture.inventory_fingerprint()
        preexisting = exp.names()
        baseline["inventory_fingerprint"] = opening
        baseline["devices"] = sorted(preexisting)
        prove_processes()
        print("LIVE OPEN " + run_id + " source=" + baseline["local_head"], flush=True)
        creation_started = True

        fixture = create_fixture(exp, plan, attempted, created, artifacts=artifacts)
        baseline["boot"] = exp.executor.wait_until_ready(
            exp.switch, timeout_seconds=150).model_dump(mode="json")

        for label, mode in (("AUTO_1", PoEInlineMode.AUTO),
                            ("NEVER", PoEInlineMode.NEVER),
                            ("AUTO_2", PoEInlineMode.AUTO)):
            prove_processes()
            if (command("git", "status", "--porcelain")
                    or command("git", "rev-parse", "HEAD") != baseline["local_head"]):
                raise RuntimeError("Frozen LIVE source changed")
            exp.apply(mode)
            capture = exp.capture(label)
            captures.append(capture)
            raw_files[capture.raw_file] = capture.observation["raw_output"].encode()
            if not all(capture.table_completeness.values()):
                raise RuntimeError(label + " did not satisfy every completeness gate")
            pse_captures.append(pse_capture(plan, label, capture, exp.switch))
            print(label + " captured; ports=" + str(capture.observation["ports"])
                  + "; completeness=True", flush=True)
    except Exception as exc:
        problems.append(type(exc).__name__ + ": " + str(exc))
    finally:
        if creation_started:
            try:
                exp.apply(PoEInlineMode.AUTO)
                restored = exp.capture("RESTORE")
                raw_files[restored.raw_file] = restored.observation["raw_output"].encode()
                restoration["fresh_readback"] = restored.model_dump(mode="json")
                # RESTORE uses the same complete multi-port readback checks.
                restore_capture = pse_capture(plan, "AUTO_2", restored, exp.switch)
                restoration["power_inline_auto_proven"] = all(
                    row.row_present for row in restore_capture.binding_captures)
            except Exception as exc:
                problems.append("Restoration readback: " + str(exc))
            deleted.extend(cleanup_fixture(exp, attempted, problems))
            try:
                restoration["residue_retired"] = list(
                    exp.fixture.retire_session_residue(preexisting))
                restoration["inventory_fingerprint_after"] = (
                    exp.fixture.wait_for_inventory_fingerprint(opening))
                restoration["inventory_restored"] = (
                    restoration["inventory_fingerprint_after"] == opening)
                restoration["fixture_removed"] = exp.names() == preexisting
                closing = exp.environment()
                restoration["environment_after"] = closing
                restoration["realtime_restored"] = closing.get("simulation_mode") is False
                exp.bridge.collect_completed()
                mailbox_entries = tuple(sorted(p.name for pattern in ("req_*.js", "res_*.txt")
                    for p in exp.bridge.dir.glob(pattern)))
                final_processes = prove_processes()
                safety = dict(
                    mailbox_entries=mailbox_entries, bridge_healthy=exp.bridge.pt_alive(),
                    processes=final_processes, transport_problems=list(exp.transport_problems),
                    source_branch=command("git", "branch", "--show-current"),
                    source_head=command("git", "rev-parse", "HEAD"),
                    source_tree=command("git", "rev-parse", "HEAD^{tree}"),
                    worktree_clean=not command("git", "status", "--porcelain"),
                )
            except Exception as exc:
                problems.append("Safety finalization: " + str(exc))
        http.stop()
    restoration.update(attempted=attempted, created=created, deleted=deleted)
    completed = utc()
    print("LIVE CLOSED; persisting after cleanup", flush=True)

    scope = dimensions = snapshot_path = None
    admitted_safety = None
    if len(pse_captures) == 3 and not problems:
        scope = pse_scope_for(
            plan=plan, run_id=run_id, observed_at=completed,
            captures=tuple(pse_captures),
            gates=tuple(sorted(captures[0].table_completeness)),
        )
        try:
            dimensions = encode_poe_pse_multi_port_dimensions(scope)
            snapshot, snapshot_path = persist_qualification(
                plan=plan, scope=scope, baseline=baseline, restoration=restoration,
                safety=safety, problems=problems, artifacts=artifacts,
                file_operations=file_operations,
                store=CapabilitySnapshotStore(resolve_within(ROOT, Path("data") / "capabilities")))
            admitted_safety = snapshot.session.results[0].context.live_session_safety
        except Exception as exc:
            problems.append("Qualification not persisted: " + str(exc))

    bundle = dict(
        schema_version=1, kind="poe3b-pse-capacity-qualification", experiment_id=run_id,
        started_at_utc=started, completed_at_utc=completed, START_HEAD=START_HEAD,
        frozen_live_sha=baseline["local_head"], packet_tracer_build=BUILD,
        qualification_id=args.qualification_id, qualification_plan=plan.model_dump(mode="json"),
        productive=snapshot_path is not None,
        integration_result="PERSISTED" if snapshot_path is not None else "NOT_ADMITTED",
        runtime_snapshot_path=str(snapshot_path) if snapshot_path is not None else None,
        live_session_safety=admitted_safety.model_dump(mode="json") if admitted_safety is not None else None,
        baseline=baseline, fixture=fixture,
        captures=[c.model_dump(mode="json") for c in captures],
        pse_scope=(asdict(scope) if scope is not None else None),
        pse_dimensions=dimensions, restoration=restoration, safety=safety,
        file_operation_ledger=asdict(file_operations.snapshot()),
        problems=problems,
    )

    directory = validate_artifact_reservation(artifacts, run_id)
    for name, content in raw_files.items():
        resolve_within(directory, safe_name_component(name)).write_bytes(content)
    path = resolve_within(directory, "evidence.json")
    path.write_bytes((json.dumps(bundle, indent=2, sort_keys=True) + "\n").encode())

    print(json.dumps(dict(
        bundle=str(directory), qualification_plan=plan.model_dump(mode="json"),
        measured=[asdict(c) for c in pse_captures],
        pse_contract_accepts_the_measurement=dimensions is not None,
        integration_result=bundle["integration_result"],
        restoration=restoration.get("inventory_restored"),
        safety=safety, problems=problems,
    ), indent=2))
    return 0 if not problems else 2


if __name__ == "__main__":
    raise SystemExit(main())
