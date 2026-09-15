"""Review and promote one verified call-observability LIVE artifact."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ...domain.enterprise.models.capabilities import CapabilityStatus, EvidenceSource
from ...domain.enterprise.models.discovery import (
    BackendVersionProvenance,
    CapabilityBackend,
    CapabilityProbeResult,
    CapabilitySnapshot,
    CleanupStatus,
    EphemeralUntitledWorkspaceSafetyEvidence,
    ProbeContext,
    ProbeExecutionStatus,
    ProbeIsolationLevel,
    ProbeSession,
    ProbeSessionResult,
    encode_inventory_observation,
    semantic_fingerprint,
    semantic_inventory_fingerprint,
)
from ...domain.enterprise.services.call_observability import (
    CALL_OBSERVABILITY_CALL_CONTROL_MODELS,
    CALL_OBSERVABILITY_CAPABILITY,
    CALL_OBSERVABILITY_EXPECTATION_RESULTS,
    CALL_OBSERVABILITY_PHONE_MODELS,
    CALL_OBSERVABILITY_PROVIDER_ID,
    CALL_OBSERVABILITY_SCHEMA,
)
from ...shared.utils import resolve_within, safe_name_component
from .capability_snapshot_store import CapabilitySnapshotStore


@dataclass(frozen=True)
class CallObservabilityPromotionReceipt:
    evidence_path: Path
    evidence_sha256: str
    capability_snapshot_path: Path
    capability_snapshot_hash: str
    executed_sha: str
    run_identity: str


def promote_verified_call_observability(
    raw_path: str | Path,
    *,
    governed_root: str | Path,
) -> CallObservabilityPromotionReceipt:
    """Promote only complete LIVE evidence; never relabel a partial result."""

    root = Path(governed_root).resolve()
    raw_file = Path(raw_path).resolve()
    if raw_file != root and not raw_file.is_relative_to(root):
        raise ValueError("Raw call evidence must be within the governed repository.")
    raw_bytes = raw_file.read_bytes()
    raw = json.loads(raw_bytes)
    if not isinstance(raw, dict):
        raise ValueError("Raw call evidence must be a JSON object.")
    _validate_raw(raw, root)

    run_identity = raw["run_identity"]
    executed_sha = raw["executed_sha"]
    packet_tracer_version = raw["packet_tracer_version"]
    provider = raw["provider"]
    qualification = raw["qualification"]
    preflight = raw["preflight"]
    postflight = raw["postflight"]
    exchange = Path(preflight["exchange_dir"]).resolve()
    capture_root = resolve_within(
        root,
        "docs",
        "reference",
        "cp-scale",
        "call-observability-evidence",
        safe_name_component(run_identity, "call-observability"),
    )
    captured: list[tuple[Path, bytes, str, str]] = []
    compact_captures: list[dict[str, str]] = []
    for index, call in enumerate(qualification["calls"], start=1):
        source = resolve_within(
            exchange,
            *Path(call["evidence_artifact_path"]).parts,
        )
        content = source.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != call["evidence_sha256"]:
            raise ValueError("Call capture SHA-256 does not match the receipt.")
        target = resolve_within(
            capture_root,
            f"call-{index}-{safe_name_component(source.name, 'capture.json')}",
        )
        relative = target.relative_to(root).as_posix()
        captured.append((target, content, digest, call["expected_result"]))
        compact_captures.append({
            "expected_result": call["expected_result"],
            "path": relative,
            "sha256": digest,
        })

    compact = {
        "schema": "call-observability-verified-v1",
        "classification": "VERIFIED",
        "scope": raw["scope"],
        "run_identity": run_identity,
        "executed_sha": executed_sha,
        "source_tree": raw["source_tree"],
        "packet_tracer_version": packet_tracer_version,
        "provider": provider,
        "ci": raw["ci"],
        "fixture_models": qualification["fixture_models"],
        "calls": [{
            key: call[key] for key in (
                "call_expectation_id",
                "call_attempt_id",
                "source_phone_id",
                "destination_phone_id",
                "dialed_extension",
                "expected_result",
                "status",
                "states",
                "connected",
                "teardown_verified",
                "fresh_evidence",
                "evidence_method",
                "execution_method",
            )
        } for call in qualification["calls"]],
        "captures": compact_captures,
        "cleanup": {
            "first_semantic_devices": qualification["cleanup_first"][
                "semantic_device_count"
            ],
            "first_links": qualification["cleanup_first"]["link_count"],
            "second_semantic_devices": qualification["cleanup_second"][
                "semantic_device_count"
            ],
            "second_links": qualification["cleanup_second"]["link_count"],
            "realtime_restored": qualification["final_realtime"],
            "mailbox_entries_after": postflight["mailbox_entries_after"],
        },
        "raw_source": {
            "path": raw_file.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "tracked": False,
        },
    }
    evidence_root = resolve_within(
        root,
        "docs",
        "reference",
        "cp-scale",
        "call-observability-evidence",
    )
    evidence_path = resolve_within(
        evidence_root,
        safe_name_component(run_identity, "call-observability") + ".json",
    )
    compact_bytes = (
        json.dumps(compact, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    compact_hash = hashlib.sha256(compact_bytes).hexdigest()
    evidence_relative = evidence_path.relative_to(root).as_posix()

    repository = preflight["repository"]
    environment = preflight["packet_tracer_environment"]
    primary_pid = postflight["primary_pid_before"]
    inventory = encode_inventory_observation(
        semantic_inventory_fingerprint([]),
        [],
    )
    safety = EphemeralUntitledWorkspaceSafetyEvidence(
        initial_device_count=environment["devices"],
        final_device_count=postflight["packet_tracer_environment"]["devices"],
        initial_link_count=environment["links"],
        final_link_count=postflight["packet_tracer_environment"]["links"],
        initial_saved_filename=environment["saved_filename"],
        final_saved_filename=postflight["packet_tracer_environment"][
            "saved_filename"
        ],
        authorized_file_operations=(),
        attempted_file_operations=(),
        denied_file_operations=(),
        invoked_file_operations=(),
        completed_file_operations=(),
        indeterminate_file_operations=(),
        initial_inventory_fingerprint=inventory,
        final_inventory_fingerprint=inventory,
        fixture_removed=True,
        initial_realtime=qualification["initial_realtime"],
        final_realtime=qualification["final_realtime"],
        packet_tracer_pids_before=(primary_pid,),
        packet_tracer_pids_after=(postflight["primary_pid_after"],),
        bridge_healthy_before=preflight["bridge"]["connected"],
        bridge_healthy_after=postflight["bridge"]["connected"],
        mailbox_entries_before=tuple(preflight["mailbox_entries_before"]),
        mailbox_entries_after=tuple(postflight["mailbox_entries_after"]),
        source_branch_before=repository["branch"],
        source_branch_after=postflight["repository"]["branch"],
        source_head_before=repository["head"],
        source_head_after=postflight["repository"]["head"],
        source_tree_before=repository["source_tree"],
        source_tree_after=postflight["repository"]["source_tree"],
        worktree_clean_before=repository["dirty"] is False,
        worktree_clean_after=postflight["repository"]["dirty"] is False,
        runtime_healthy=True,
        crash_detected=False,
        integrity_verified=True,
        session_reusable=True,
        positive_claim_allowed=True,
        failure_reasons=[],
    )
    dimensions = {
        "schema": CALL_OBSERVABILITY_SCHEMA,
        "provider_id": CALL_OBSERVABILITY_PROVIDER_ID,
        "execution_method": provider["execution_method"],
        "driver_source_sha256": provider["driver_source_sha256"],
        "call_control_models": ",".join(
            CALL_OBSERVABILITY_CALL_CONTROL_MODELS
        ),
        "phone_models": ",".join(CALL_OBSERVABILITY_PHONE_MODELS),
        "expectation_results": ",".join(
            CALL_OBSERVABILITY_EXPECTATION_RESULTS
        ),
        "exact_identity": "true",
        "fresh_evidence": "true",
        "teardown_verified": "true",
        "cleanup_empty_observations": "2",
        "realtime_restored": "true",
        "evidence_path": evidence_relative,
        "evidence_sha256": compact_hash,
        "executed_sha": executed_sha,
        "run_identity": run_identity,
    }
    fingerprint = semantic_fingerprint({
        "provider": provider,
        "packet_tracer_version": packet_tracer_version,
        "fixture_models": qualification["fixture_models"],
    })
    result = CapabilityProbeResult(
        probe_id=run_identity,
        model=CALL_OBSERVABILITY_CALL_CONTROL_MODELS[0],
        capability=CALL_OBSERVABILITY_CAPABILITY,
        status=CapabilityStatus.SUPPORTED,
        execution_status=ProbeExecutionStatus.VERIFIED,
        evidence_source=EvidenceSource.MANUAL_VERIFICATION,
        configured=True,
        verified=True,
        raw_summary=(
            "Packet Tracer native UI produced correlated ESTABLISHED and "
            "NOT_CONNECTED call lifecycles with verified teardown."
        ),
        packet_tracer_version=packet_tracer_version,
        dimensions=dimensions,
        context=ProbeContext(
            probe_id=run_identity,
            probe_version="1",
            backend=CapabilityBackend.PACKET_TRACER,
            backend_version=packet_tracer_version,
            device_model=CALL_OBSERVABILITY_CALL_CONTROL_MODELS[0],
            environment_fingerprint=fingerprint,
            initial_inventory_hash=inventory,
            final_inventory_hash=inventory,
            inventory_restored=True,
            isolation_level=ProbeIsolationLevel.FRESH_SESSION_REQUIRED,
            mutations=[
                *qualification["created_devices"],
                *qualification["created_links"],
            ],
            cleanup_status=CleanupStatus.CLEAN,
            result_status=CapabilityStatus.SUPPORTED,
            execution_status=ProbeExecutionStatus.VERIFIED,
            probe_fingerprint=fingerprint,
            live_session_safety=safety,
        ),
    )
    snapshot = CapabilitySnapshot(
        packet_tracer_version=packet_tracer_version,
        backend_version_provenance=BackendVersionProvenance.DIRECTLY_OBSERVED,
        backend=CapabilityBackend.PACKET_TRACER,
        environment_fingerprint=fingerprint,
        probe_fingerprints={CALL_OBSERVABILITY_CAPABILITY: fingerprint},
        initial_inventory_hash=inventory,
        final_inventory_hash=inventory,
        inventory_restored=True,
        session=ProbeSessionResult(
            session=ProbeSession(
                session_id=run_identity,
                started_at=datetime.now(timezone.utc),
                packet_tracer_version=packet_tracer_version,
                created_devices=list(qualification["created_devices"]),
                mutations=[
                    *qualification["created_devices"],
                    *qualification["created_links"],
                ],
                cleanup_status=CleanupStatus.CLEAN,
            ),
            results=[result],
            cleanup_deleted=list(qualification["removed_devices"]),
        ),
    )
    store = CapabilitySnapshotStore(
        resolve_within(
            root,
            "docs",
            "reference",
            "cp-scale",
            "call-capabilities",
        )
    )

    targets = [target for target, *_rest in captured]
    targets.append(evidence_path)
    if any(target.exists() for target in targets):
        raise ValueError("Promotion target already exists; evidence is immutable.")
    created: list[Path] = []
    try:
        for target, content, _digest, _result in captured:
            _write_atomic(target, content)
            created.append(target)
        _write_atomic(evidence_path, compact_bytes)
        created.append(evidence_path)
        snapshot_path = store.save_verified(snapshot)
        created.append(snapshot_path)
    except BaseException:
        for target in reversed(created):
            target.unlink(missing_ok=True)
        raise
    return CallObservabilityPromotionReceipt(
        evidence_path=evidence_path,
        evidence_sha256=compact_hash,
        capability_snapshot_path=snapshot_path,
        capability_snapshot_hash=snapshot.stable_hash(),
        executed_sha=executed_sha,
        run_identity=run_identity,
    )


def _validate_raw(raw: dict[str, object], root: Path) -> None:
    if raw.get("schema") != "call-observability-live-v1":
        raise ValueError("Raw call evidence schema is not supported.")
    if raw.get("scope") != "call-observability-qualification":
        raise ValueError("Raw call evidence has a foreign scope.")
    if not _is_git_sha(raw.get("executed_sha")):
        raise ValueError("Raw call evidence executed SHA is malformed.")
    if not _is_git_sha(raw.get("source_tree")):
        raise ValueError("Raw call evidence source tree is malformed.")
    if raw.get("packet_tracer_version") != "9.0.1.0858":
        raise ValueError("Raw call evidence belongs to a foreign Packet Tracer build.")
    if not _exact_text(raw.get("run_identity")):
        raise ValueError("Raw call evidence run identity is missing.")
    provider = raw.get("provider")
    if not isinstance(provider, dict):
        raise ValueError("Raw call evidence provider is missing.")
    if (
        provider.get("provider_id") != CALL_OBSERVABILITY_PROVIDER_ID
        or provider.get("execution_method") != "packet_tracer_native_ui"
        or not _is_sha256(provider.get("driver_source_sha256"))
    ):
        raise ValueError("Raw call evidence provider is foreign or malformed.")
    driver_path = provider.get("driver_source")
    if not isinstance(driver_path, str):
        raise ValueError("Raw call evidence driver path is missing.")
    driver = resolve_within(root, *Path(driver_path).parts)
    if hashlib.sha256(driver.read_bytes()).hexdigest() != provider[
        "driver_source_sha256"
    ]:
        raise ValueError("Qualified driver source hash does not match the current driver.")
    ci = raw.get("ci")
    if not isinstance(ci, dict) or (
        ci.get("head") != raw["executed_sha"]
        or not _exact_text(ci.get("run_id"))
        or not isinstance(ci.get("successful_check_runs"), list)
        or len(ci["successful_check_runs"]) != 4
        or len(set(ci["successful_check_runs"])) != 4
    ):
        raise ValueError("Raw call evidence does not pin CI 4/4 to executed SHA.")
    preflight = raw.get("preflight")
    postflight = raw.get("postflight")
    qualification = raw.get("qualification")
    if not all(isinstance(item, dict) for item in (
        preflight, postflight, qualification,
    )):
        raise ValueError("Raw call evidence boundaries are incomplete.")
    if qualification.get("status") != "VERIFIED":
        raise ValueError("Only a VERIFIED call qualification can be promoted.")
    if qualification.get("fixture_models") != [
        "2811", "3560-24PS", "7960", "7960",
    ]:
        raise ValueError("Call qualification used foreign fixture models.")
    if (
        len(qualification.get("created_devices", [])) != 4
        or len(qualification.get("created_links", [])) != 3
        or len(qualification.get("removed_devices", [])) != 4
        or qualification.get("cleanup_verified") is not True
        or qualification.get("initial_realtime") is not True
        or qualification.get("final_realtime") is not True
        or qualification.get("errors") != []
    ):
        raise ValueError("Call qualification lifecycle or cleanup is incomplete.")
    for name in ("baseline", "cleanup_first", "cleanup_second"):
        observation = qualification.get(name)
        if not isinstance(observation, dict) or (
            observation.get("observed") is not True
            or observation.get("semantic_device_count") != 0
            or observation.get("link_count") != 0
        ):
            raise ValueError("Call qualification lacks two exact empty cleanup observations.")
    calls = qualification.get("calls")
    if not isinstance(calls, list) or len(calls) != 2:
        raise ValueError("Call qualification does not contain the exact E7 pair.")
    expected = (
        (
            "established",
            "callqual/phone/1",
            "callqual/phone/2",
            "3002",
            ["idle", "dialing", "ringing", "connected", "disconnected", "idle"],
            True,
        ),
        (
            "not_connected",
            "callqual/phone/1",
            "",
            "3999",
            ["idle", "dialing", "failed", "idle"],
            False,
        ),
    )
    attempt_ids: list[str] = []
    for call, contract in zip(calls, expected):
        result, source, destination, extension, states, connected = contract
        if not isinstance(call, dict) or (
            call.get("expected_result") != result
            or call.get("source_phone_id") != source
            or call.get("destination_phone_id") != destination
            or call.get("dialed_extension") != extension
            or call.get("status") != "verified"
            or call.get("states") != states
            or call.get("connected") is not connected
            or call.get("teardown_verified") is not True
            or call.get("fresh_evidence") is not True
            or call.get("evidence_method")
            != "packet_tracer_native_ui_correlated_state_capture_v1"
            or call.get("execution_method") != "packet_tracer_native_ui"
            or call.get("failure_code") != "none"
            or not _exact_text(call.get("call_attempt_id"))
            or not _exact_text(call.get("call_expectation_id"))
            or not _exact_text(call.get("evidence_artifact_path"))
            or not _is_sha256(call.get("evidence_sha256"))
        ):
            raise ValueError("Call qualification observation violates the typed E7 contract.")
        attempt_ids.append(call["call_attempt_id"])
    if len(set(attempt_ids)) != 2:
        raise ValueError("Call qualification attempt IDs are not unique.")
    repository = preflight.get("repository")
    repository_after = postflight.get("repository")
    if not isinstance(repository, dict) or not isinstance(repository_after, dict):
        raise ValueError("Call qualification repository evidence is missing.")
    for item in (repository, repository_after):
        if (
            item.get("branch") != "feature/runtime-ripv2"
            or item.get("upstream") != "cisco/feature/runtime-ripv2"
            or item.get("head") != raw["executed_sha"]
            or item.get("upstream_head") != raw["executed_sha"]
            or item.get("source_tree") != raw["source_tree"]
            or item.get("dirty") is not False
        ):
            raise ValueError("Call qualification repository evidence is foreign or dirty.")
    before_environment = preflight.get("packet_tracer_environment")
    after_environment = postflight.get("packet_tracer_environment")
    expected_environment = {
        "found": True,
        "saved_filename": "",
        "pt_version": raw["packet_tracer_version"],
        "simulation_mode": False,
        "devices": 0,
        "links": 0,
    }
    if before_environment != expected_environment or after_environment != expected_environment:
        raise ValueError("Call qualification environment was not restored exactly.")
    if (
        preflight.get("mailbox_entries_before") != []
        or postflight.get("mailbox_entries_after") != []
        or postflight.get("errors") != []
        or postflight.get("primary_pid_before") != postflight.get("primary_pid_after")
        or not isinstance(postflight.get("primary_pid_before"), int)
        or preflight.get("bridge", {}).get("connected") is not True
        or postflight.get("bridge", {}).get("connected") is not True
    ):
        raise ValueError("Call qualification postflight or mailbox evidence is incomplete.")


def _write_atomic(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f"{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
        temporary.replace(target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _exact_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _is_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_git_sha(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )
