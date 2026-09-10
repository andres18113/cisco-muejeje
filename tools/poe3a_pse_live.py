"""Governed PSE capacity qualification on an empty, untitled PT workspace.

Only model and qualification identity are caller supplied. The ordered binding
set comes from the Router0 capacity plan. Positive schema-3 runtime evidence is
persisted only after cleanup, ephemeral safety admission and schema decoding.
All Packet Tracer access crosses one bounded session; its workspace-file policy
is empty and its observed ledger must remain empty.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from secrets import token_hex
import subprocess
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
from packet_tracer_mcp.infrastructure.execution.poe3b_session import (
    PacketTracerFileOperationLedger,
    PacketTracerPoE3BSession,
    PoE3BSessionOperation,
    PoEInlineMode,
)
from packet_tracer_mcp.infrastructure.execution.poe2_evidence import (
    BUILD, START_HEAD, COMPLETENESS_KEYS, completeness,
)
from packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import CapabilitySnapshotStore
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    parse_show_power_inline, classify_poe_inline_delivery,
)
from packet_tracer_mcp.shared.utils import resolve_within, safe_name_component

ROOT = Path(__file__).resolve().parents[1]
REPO = "andres18113/cisco-muejeje"
BRANCH = "feature/runtime-ripv2"
UPSTREAM = "cisco/feature/runtime-ripv2"
# 100-character path component budget: 6 prefix + 68 caller metadata +
# 1 separator + 16 UTC timestamp + 1 separator + 8 random hex characters.
QUALIFICATION_ID_MAX_LENGTH = 68
_PACKET_TRACER_HELPER_ARGUMENT = re.compile(
    r"(?:^|\s)--progress-bar-server(?:\s|$)",
)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def command(*args: str) -> str:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()


def processes() -> list[dict]:
    script = (
        "Get-CimInstance Win32_Process | Where-Object { $_.Name -match "
        "'^(python|pythonw|pytest|PacketTracer)\\.exe$' } | Select-Object "
        "ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine | "
        "ConvertTo-Json -Compress"
    )
    raw = command("powershell.exe", "-NoProfile", "-Command", script)
    result = json.loads(raw) if raw else []
    return result if isinstance(result, list) else [result]


def prove_processes() -> list[dict]:
    result = processes()
    allowed = {os.getpid(), os.getppid()}
    foreign = [
        process for process in result
        if process["Name"].lower() != "packettracer.exe"
        and process["ProcessId"] not in allowed
    ]
    if foreign:
        raise RuntimeError("Foreign Python/test process: " + json.dumps(foreign))
    try:
        packet_tracer_primary_pids(result)
    except ValueError as exc:
        raise RuntimeError(
            "Packet Tracer process cohort is invalid: " + str(exc)
        ) from exc
    return result


def packet_tracer_primary_pids(processes: list[dict]) -> tuple[int, ...]:
    """Identify one PT instance while retaining its exact helper in raw evidence."""

    packet_tracer = [
        process for process in processes
        if process.get("Name") == "PacketTracer.exe"
    ]
    if not packet_tracer:
        raise ValueError("Packet Tracer is absent")
    if any(
        type(process.get("ProcessId")) is not int
        or process["ProcessId"] <= 0
        or type(process.get("ParentProcessId")) is not int
        or type(process.get("ExecutablePath")) is not str
        or not process["ExecutablePath"]
        or type(process.get("CommandLine")) is not str
        for process in packet_tracer
    ):
        raise ValueError("process identity evidence is incomplete")
    if len({process["ProcessId"] for process in packet_tracer}) != len(
        packet_tracer
    ):
        raise ValueError("process IDs are duplicated")

    helpers = [
        process for process in packet_tracer
        if _PACKET_TRACER_HELPER_ARGUMENT.search(process["CommandLine"])
    ]
    primary = [process for process in packet_tracer if process not in helpers]
    if len(primary) != 1 or len(helpers) > 1:
        raise ValueError("exactly one primary and at most one helper are allowed")
    owner = primary[0]
    for helper in helpers:
        if (
            helper["ParentProcessId"] != owner["ProcessId"]
            or os.path.normcase(os.path.normpath(helper["ExecutablePath"]))
            != os.path.normcase(os.path.normpath(owner["ExecutablePath"]))
        ):
            raise ValueError("progress helper is not owned by the primary process")
    return (owner["ProcessId"],)


def source_baseline(plan: PoEModelQualificationPlan) -> dict:
    branch = command("git", "branch", "--show-current")
    if branch != BRANCH:
        raise RuntimeError("Wrong branch")
    if command("git", "status", "--porcelain"):
        raise RuntimeError("Worktree must be clean")
    sha = command("git", "rev-parse", "HEAD")
    upstream = command(
        "git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}",
    )
    upstream_sha = command("git", "rev-parse", "@{upstream}")
    if upstream != UPSTREAM or upstream_sha != sha:
        raise RuntimeError("HEAD and the authorized upstream differ")
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
    run = next(
        record for record in runs
        if record["name"] == "tests"
        and record["headSha"] == sha
        and record["status"] == "completed"
        and record["conclusion"] == "success"
    )
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
        upstream=upstream, upstream_head=upstream_sha, worktree_clean=True,
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
    file_operation_ledger: PacketTracerFileOperationLedger,
) -> EphemeralUntitledWorkspaceSafetyEvidence:
    """Project acquired fields only; missing measurements stay unproven."""
    if not isinstance(file_operation_ledger, PacketTracerFileOperationLedger):
        raise ValueError("Observed Packet Tracer file-operation ledger is required")
    file_ledger = file_operation_ledger
    initial, final = baseline.get("environment", {}), restoration.get("environment_after", {})
    def pids(facts):
        processes = facts.get("processes")
        if processes is None:
            return None
        if (
            isinstance(processes, list)
            and not any(
                isinstance(process, dict)
                and process.get("Name") == "PacketTracer.exe"
                for process in processes
            )
        ):
            return ()
        try:
            return packet_tracer_primary_pids(processes)
        except (AttributeError, TypeError, ValueError):
            return None
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
        denied_file_operations=file_ledger.denied_operations,
        invoked_file_operations=file_ledger.invoked_operations,
        completed_file_operations=file_ledger.completed_operations,
        indeterminate_file_operations=file_ledger.indeterminate_operations,
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
                          file_operation_ledger: PacketTracerFileOperationLedger,
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
        file_operation_ledger=file_operation_ledger,
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


@dataclass
class GovernedQualificationExecution:
    fixture_evidence: dict
    captures: list
    pse_captures: list[PoEPseMultiPortCapture]
    problems: list[str]
    restoration: dict
    safety: dict
    raw_files: dict[str, bytes]
    completed_at_utc: str
    file_operation_ledger: PacketTracerFileOperationLedger
    scope: PoEPseMultiPortDeliveryScope | None = None
    dimensions: dict[str, str] | None = None
    snapshot: CapabilitySnapshot | None = None
    snapshot_path: Path | None = None


def current_source_state() -> dict:
    return {
        "source_branch": command("git", "branch", "--show-current"),
        "source_head": command("git", "rev-parse", "HEAD"),
        "source_tree": command("git", "rev-parse", "HEAD^{tree}"),
        "worktree_clean": not command("git", "status", "--porcelain"),
    }


def _require_frozen_source(baseline: dict, observed: dict) -> None:
    if (
        observed.get("source_branch") != baseline.get("source_branch")
        or observed.get("source_head") != baseline.get("local_head")
        or observed.get("source_tree") != baseline.get("source_tree")
        or observed.get("worktree_clean") is not True
    ):
        raise RuntimeError("Frozen LIVE source changed")


def execute_governed_qualification(
    *,
    session: PacketTracerPoE3BSession,
    plan: PoEModelQualificationPlan,
    baseline: dict,
    artifacts: ArtifactReservation,
    store,
    process_probe: Callable[[], list[dict]] = prove_processes,
    source_state_probe: Callable[[], dict] = current_source_state,
) -> GovernedQualificationExecution:
    """Run one bounded qualification; never retry a failed or ambiguous run."""

    validate_artifact_reservation(artifacts)
    if tuple(binding.switch_port for binding in plan.bindings) != session.switch_ports:
        raise ValueError("Session ports differ from the governed qualification plan")
    if (
        session.dispatches
        or session.attempted_device_names
        or session.created_device_names
    ):
        raise ValueError("The governed Packet Tracer session is not fresh")
    if not session.file_operation_ledger().ephemeral_safe:
        raise ValueError("EPHEMERAL file-operation boundary was not initially clean")

    captures = []
    pse_captures: list[PoEPseMultiPortCapture] = []
    problems: list[str] = []
    fixture: dict = {}
    restoration: dict = {}
    safety: dict = {}
    raw_files: dict[str, bytes] = {}
    deleted: list[str] = []
    opening: str | None = None
    preexisting: frozenset[str] | None = None
    creation_started = False
    try:
        baseline["bridge_healthy"] = session.bridge_healthy()
        baseline["mailbox_entries"] = session.mailbox_entries()
        if baseline["bridge_healthy"] is not True:
            raise RuntimeError("File bridge heartbeat stale")
        if baseline["mailbox_entries"] != ():
            raise RuntimeError("Foreign mailbox residue")
        baseline["fresh_authenticated_bridge"] = session.start_control_bridge()
        environment = session.environment()
        if (
            environment.get("pt_version") != plan.packet_tracer_build
            or environment.get("simulation_mode") is not False
        ):
            raise RuntimeError("Wrong Packet Tracer build or mode")
        if (
            environment.get("devices") != 0
            or environment.get("links") != 0
            or environment.get("saved_filename") != ""
        ):
            raise RuntimeError("Requires an empty, untitled semantic baseline")
        baseline["environment"] = environment
        opening = session.inventory_fingerprint()
        preexisting = session.device_names()
        baseline["inventory_fingerprint"] = opening
        baseline["devices"] = sorted(preexisting)
        process_probe()
        print(
            "LIVE OPEN " + artifacts.run_id + " source=" + baseline["local_head"],
            flush=True,
        )
        creation_started = True
        fixture = session.create_fixture(plan.candidate_model, plan.bindings)
        baseline["boot"] = session.wait_until_ready(
            timeout_seconds=150,
        ).model_dump(mode="json")

        for label, mode in (
            ("AUTO_1", PoEInlineMode.AUTO),
            ("NEVER", PoEInlineMode.NEVER),
            ("AUTO_2", PoEInlineMode.AUTO),
        ):
            process_probe()
            _require_frozen_source(baseline, source_state_probe())
            session.apply_inline_mode(mode)
            capture = session.capture_inline_status(label)
            captures.append(capture)
            raw_files[capture.raw_file] = capture.observation["raw_output"].encode()
            if not all(capture.table_completeness.values()):
                raise RuntimeError(
                    label + " did not satisfy every completeness gate"
                )
            pse_captures.append(
                pse_capture(plan, label, capture, session.switch_name)
            )
            print(
                label + " captured; ports=" + str(capture.observation["ports"])
                + "; completeness=True",
                flush=True,
            )
    except Exception as exc:
        problems.append(type(exc).__name__ + ": " + str(exc))
    finally:
        if creation_started:
            try:
                session.apply_inline_mode(PoEInlineMode.AUTO)
                restored = session.capture_inline_status("RESTORE")
                raw_files[restored.raw_file] = restored.observation[
                    "raw_output"
                ].encode()
                restoration["fresh_readback"] = restored.model_dump(mode="json")
                restore_capture = pse_capture(
                    plan, "AUTO_2", restored, session.switch_name,
                )
                restoration["power_inline_auto_proven"] = all(
                    row.row_present for row in restore_capture.binding_captures
                )
            except Exception as exc:
                problems.append("Restoration readback: " + str(exc))

            cleanup = session.cleanup_fixture()
            deleted.extend(cleanup.deleted)
            problems.extend(cleanup.problems)
            try:
                assert opening is not None and preexisting is not None
                restoration["residue_retired"] = list(
                    session.retire_session_residue(preexisting)
                )
                restoration["inventory_fingerprint_after"] = (
                    session.wait_for_inventory_fingerprint(opening)
                )
                restoration["inventory_restored"] = (
                    restoration["inventory_fingerprint_after"] == opening
                )
                restoration["fixture_removed"] = (
                    session.device_names() == preexisting
                )
                closing = session.environment()
                restoration["environment_after"] = closing
                restoration["realtime_restored"] = (
                    closing.get("simulation_mode") is False
                )
                session.collect_completed()
                final_processes = process_probe()
                source_state = source_state_probe()
                safety = {
                    "mailbox_entries": session.mailbox_entries(),
                    "bridge_healthy": session.bridge_healthy(),
                    "processes": final_processes,
                    "transport_problems": list(session.transport_problems()),
                    **source_state,
                }
            except Exception as exc:
                problems.append("Safety finalization: " + str(exc))
        try:
            session.stop_control_bridge()
        except Exception as exc:
            problems.append("Control bridge shutdown: " + str(exc))

    restoration.update(
        attempted=list(session.attempted_device_names),
        created=list(session.created_device_names),
        deleted=deleted,
    )
    completed = utc()
    print("LIVE CLOSED; persisting after cleanup", flush=True)
    execution = GovernedQualificationExecution(
        fixture_evidence=fixture,
        captures=captures,
        pse_captures=pse_captures,
        problems=problems,
        restoration=restoration,
        safety=safety,
        raw_files=raw_files,
        completed_at_utc=completed,
        file_operation_ledger=session.file_operation_ledger(),
    )
    if len(pse_captures) == 3 and not problems:
        execution.scope = pse_scope_for(
            plan=plan,
            run_id=artifacts.run_id,
            observed_at=completed,
            captures=tuple(pse_captures),
            gates=tuple(sorted(captures[0].table_completeness)),
        )
        try:
            execution.dimensions = encode_poe_pse_multi_port_dimensions(
                execution.scope,
            )
            execution.snapshot, execution.snapshot_path = persist_qualification(
                plan=plan,
                scope=execution.scope,
                baseline=baseline,
                restoration=restoration,
                safety=safety,
                problems=problems,
                artifacts=artifacts,
                file_operation_ledger=execution.file_operation_ledger,
                store=store,
            )
        except Exception as exc:
            problems.append("Qualification not persisted: " + str(exc))
    return execution


def main() -> int:
    args = parse_args()
    isolation = ImportIsolationPreflight(ROOT).ensure_isolated()
    if not isolation.isolated:
        raise RuntimeError(isolation.render())
    plan = governed_plan(args.model)
    baseline = source_baseline(plan)
    baseline["processes"] = prove_processes()
    baseline["import_isolation"] = {
        "result": isolation.render(),
        "executable": sys.executable,
        "production_file": packet_tracer_mcp.__file__,
        "loaded_namespaces": [
            name for name in ("packet_tracer_mcp", "src.packet_tracer_mcp")
            if name in sys.modules
        ],
    }
    artifacts = reserve_artifacts(args.qualification_id)
    started = utc()
    session = PacketTracerPoE3BSession(
        artifacts.run_id,
        switch_ports=tuple(binding.switch_port for binding in plan.bindings),
        endpoint_role="PH",
    )
    execution = execute_governed_qualification(
        session=session,
        plan=plan,
        baseline=baseline,
        artifacts=artifacts,
        store=CapabilitySnapshotStore(
            resolve_within(ROOT, Path("data") / "capabilities"),
        ),
    )
    admitted_safety = (
        execution.snapshot.session.results[0].context.live_session_safety
        if execution.snapshot is not None
        else None
    )
    bundle = {
        "schema_version": 1,
        "kind": "poe3b-pse-capacity-qualification",
        "experiment_id": artifacts.run_id,
        "started_at_utc": started,
        "completed_at_utc": execution.completed_at_utc,
        "START_HEAD": START_HEAD,
        "frozen_live_sha": baseline["local_head"],
        "packet_tracer_build": BUILD,
        "qualification_id": args.qualification_id,
        "qualification_plan": plan.model_dump(mode="json"),
        "productive": execution.snapshot_path is not None,
        "integration_result": (
            "PERSISTED" if execution.snapshot_path is not None else "NOT_ADMITTED"
        ),
        "runtime_snapshot_path": (
            str(execution.snapshot_path)
            if execution.snapshot_path is not None
            else None
        ),
        "live_session_safety": (
            admitted_safety.model_dump(mode="json")
            if admitted_safety is not None
            else None
        ),
        "baseline": baseline,
        "fixture": execution.fixture_evidence,
        "captures": [capture.model_dump(mode="json") for capture in execution.captures],
        "pse_scope": asdict(execution.scope) if execution.scope is not None else None,
        "pse_dimensions": execution.dimensions,
        "restoration": execution.restoration,
        "safety": execution.safety,
        "file_operation_ledger": asdict(execution.file_operation_ledger),
        "session_dispatches": [asdict(record) for record in session.dispatches],
        "problems": execution.problems,
    }
    directory = validate_artifact_reservation(artifacts, artifacts.run_id)
    for name, content in execution.raw_files.items():
        resolve_within(directory, safe_name_component(name)).write_bytes(content)
    evidence_path = resolve_within(directory, "evidence.json")
    evidence_path.write_bytes(
        (json.dumps(bundle, indent=2, sort_keys=True) + "\n").encode()
    )
    print(json.dumps({
        "bundle": str(directory),
        "qualification_plan": plan.model_dump(mode="json"),
        "measured": [asdict(capture) for capture in execution.pse_captures],
        "pse_contract_accepts_the_measurement": execution.dimensions is not None,
        "integration_result": bundle["integration_result"],
        "restoration": execution.restoration.get("inventory_restored"),
        "safety": execution.safety,
        "problems": execution.problems,
    }, indent=2))
    return 0 if not execution.problems else 2


if __name__ == "__main__":
    raise SystemExit(main())
