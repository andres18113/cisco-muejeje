"""Governed Server-PT commissioning phases for the C31 disposable campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections.abc import Mapping, Sequence
from contextlib import redirect_stdout
from dataclasses import asdict, replace
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from ...application.ports.service_qualification import OpenedTransport
from ...application.use_cases.cleanup_server_pt_commissioning import (
    run_server_pt_cleanup,
)
from ...application.use_cases.prepare_server_pt_commissioning import (
    prepare_server_pt_commissioning,
)
from ...application.use_cases.prequalify_server_pt import prequalify_server_pt
from ...application.use_cases.seal_server_pt_acceptance import (
    seal_server_pt_acceptance,
)
from ...application.use_cases.server_pt_phase_budget import (
    E5_IOS_QUERY_MAX_CALLS,
    E5_IOS_QUERY_MAX_SECONDS,
    derive_phase_budget,
)
from ...application.use_cases.server_pt_phase_grant import (
    CHARTER_SHA256,
    RECOVERY_PREQUALIFICATION_ATTEMPT,
    derive_server_pt_phase_grant,
)
from ...application.use_cases.server_pt_process_evidence import (
    exit_evidence_findings,
    launch_evidence_findings,
)
from ...application.use_cases.server_pt_second_attempt import second_attempt_findings
from ...application.use_cases.setup_server_pt_commissioning import (
    run_server_pt_setup,
)
from ...domain.enterprise.models.cold_http_acceptance import publication_claim
from ...domain.enterprise.models.deployment import EnvironmentFingerprint
from ...domain.enterprise.models.service_qualification import (
    diagnostic_lifecycle_continuity,
)
from ...domain.models.plans import TopologyPlan
from ...infrastructure.catalog.server_pt_commissioning_evidence import (
    scoped_setup_evidence,
)
from ...infrastructure.execution.cp_scale_live_preflight import (
    PowerShellPacketTracerProcessReader,
)
from ...infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from ...infrastructure.execution.import_isolation_preflight import (
    governed_root_from_env,
)
from ...infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
)
from ...infrastructure.execution.probe_runtime import PacketTracerBridgeProbeRuntime
from ...infrastructure.execution.product_channel import FixedChannelProductTransport
from ...infrastructure.execution.server_pt_campaign_authority import read_exact_ci
from ...infrastructure.execution.server_pt_phase_channel import GovernedPhaseChannel
from ...infrastructure.execution.service_qualification_lifecycle import (
    PacketTracerDiagnosticLifecycleReader,
)
from ...infrastructure.persistence.cold_http_acceptance_store import (
    ColdHttpAcceptanceStore,
)
from ...infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)
from ...infrastructure.persistence.server_pt_raw_archive import build_raw_answer_index
from . import cold_http_acceptance as acceptance_cli
from .server_pt_live_phase import bind_live_phase, phase_preflight
from .service_qualification import repository_identity

_ATTEMPT = re.compile(r"[0-9a-f]{32}\Z")
_RECOVERY_FIRST_ATTEMPT = "979b4636d50290d199e8ea0f95eddab3"
_RECOVERY_FIRST_STATUS_SHA256 = (
    "c623ec5dbc62e108568cff6a41ab858d451de2e86c1ab426690dfdecae2e2829"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    phase = parser.add_mutually_exclusive_group(required=True)
    phase.add_argument("--prepare", action="store_true")
    phase.add_argument("--inspect", action="store_true")
    phase.add_argument("--qualify", action="store_true")
    phase.add_argument("--setup", action="store_true")
    phase.add_argument("--accept", action="store_true")
    phase.add_argument("--cleanup", action="store_true")
    phase.add_argument("--record-correction", action="store_true")
    phase.add_argument("--record-launch", action="store_true")
    phase.add_argument("--record-exit", action="store_true")
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--clients", type=int, default=30)
    parser.add_argument("--ci-run", type=int, default=0)
    parser.add_argument("--charter", default="")
    parser.add_argument("--first-attempt", default="")
    parser.add_argument("--correction-file", default="")
    parser.add_argument("--launch-evidence", default="")
    parser.add_argument("--close-evidence", default="")
    return parser


def _print(payload: Mapping[str, object]) -> None:
    print(json.dumps(payload, sort_keys=True), flush=True)


def _refresh_archive(
    store: ServerPtCommissioningStore, status: Mapping[str, object]
) -> tuple[str, ...]:
    """Update one current projection and verify the single hash index."""
    try:
        store.update_current_status(status)
        store.refresh_index()
        return store.verify_index()
    except (OSError, ValueError) as exc:
        return (f"archive_index_unavailable:{type(exc).__name__}",)


def _archive_or_stop(
    store: ServerPtCommissioningStore, status: dict[str, object]
) -> None:
    """Never report phase success when its source-byte index is unverified."""
    findings = _refresh_archive(store, status)
    if not findings:
        try:
            store.save_archive_admission(
                str(status["attempt_id"]), str(status["phase"])
            )
            store.refresh_index()
            findings = store.verify_index()
        except (OSError, ValueError, KeyError) as exc:
            findings = (f"archive_admission_unavailable:{type(exc).__name__}",)
        if not findings:
            return
    status["outcome"] = "stopped"
    status["archive_findings"] = list(findings)
    try:
        store.update_current_status(status)
        store.refresh_index()
    except (OSError, ValueError):
        pass


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Prepare exact full-plan bytes or inspect a sealed input without contact."""
    args = _parser().parse_args(argv)
    root = governed_root_from_env(environ)
    if root is None:
        _print({"outcome": "refused", "reason": "governed_root_not_declared"})
        return 2
    if _ATTEMPT.fullmatch(args.attempt) is None:
        _print({"outcome": "refused", "reason": "invalid_attempt_id"})
        return 2
    if args.clients != 30:
        _print({"outcome": "refused", "reason": "charter_requires_30_clients"})
        return 2
    if args.record_correction:
        return _record_correction(
            root, args.attempt, args.first_attempt, args.correction_file
        )
    if (
        args.qualify
        or args.setup
        or args.accept
        or args.cleanup
        or args.record_launch
        or args.record_exit
    ):
        if not args.ci_run or not args.charter:
            _print({"outcome": "refused", "reason": "ci_run_and_charter_required"})
            return 2
        try:
            charter_bytes = Path(args.charter).read_bytes()
        except OSError:
            _print({"outcome": "refused", "reason": "charter_unreadable"})
            return 2
        if (
            len(charter_bytes) > 1024 * 1024
            or hashlib.sha256(charter_bytes).hexdigest() != CHARTER_SHA256
        ):
            _print({"outcome": "refused", "reason": "charter_digest_mismatch"})
            return 2
        if args.record_launch:
            if not args.launch_evidence:
                _print({"outcome": "refused", "reason": "launch_evidence_required"})
                return 2
            return _record_launch(root, args.attempt, args.ci_run, args.launch_evidence)
        if args.record_exit:
            if not args.close_evidence:
                _print({"outcome": "refused", "reason": "close_evidence_required"})
                return 2
            return _record_exit(root, args.attempt, args.ci_run, args.close_evidence)
        if args.qualify:
            return _qualify(root, args.attempt, args.ci_run)
        if args.setup:
            return _setup(root, args.attempt, args.ci_run)
        if args.accept:
            return _accept(root, args.attempt, args.ci_run)
        if args.cleanup:
            return _cleanup(root, args.attempt, args.ci_run)
        _print({"outcome": "refused", "reason": "live_phase_not_bound"})
        return 2
    store = ServerPtCommissioningStore(root)
    try:
        if args.prepare:
            bundle = prepare_server_pt_commissioning(30, "COLD_HTTP_" + args.attempt)
            path = store.save_bundle(args.attempt, bundle)
            mode = "prepare"
        else:
            bundle = store.load_bundle(args.attempt)
            path = store.bundle_path_for(args.attempt)
            mode = "inspect"
        topology = TopologyPlan.model_validate_json(bundle.topology_json)
        payload = {
            "mode": mode,
            "outcome": "ready",
            "attempt_id": args.attempt,
            "bundle_path": str(path),
            "bundle_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "intent_sha256": bundle.intent_sha256,
            "topology_sha256": bundle.topology_sha256,
            "physical_topology_hash": bundle.physical_topology_hash,
            "configuration_semantic_hash": bundle.configuration_semantic_hash,
            "devices": len(topology.devices),
            "links": len(topology.links),
            "setup_action_types": bundle.setup_action_types,
            "phase_budget": asdict(derive_phase_budget(bundle)),
        }
        archive_findings = (
            _refresh_archive(store, payload) if args.prepare else store.verify_index()
        )
        if archive_findings:
            payload["outcome"] = "refused"
            payload["archive_findings"] = list(archive_findings)
        _print(payload)
    except (OSError, ValueError) as exc:
        _print(
            {
                "outcome": "refused",
                "reason": f"{mode if 'mode' in locals() else 'prepare'}:{type(exc).__name__}",
            }
        )
        return 2
    return 0 if payload["outcome"] == "ready" else 2


def _first_retirement(
    store: ServerPtCommissioningStore, attempt_id: str
) -> tuple[str, str]:
    """Return indexed safety evidence without adopting an uncertain E4 effect."""
    if store.verify_index():
        raise ValueError("first attempt archive is invalid")
    exit_record = store.load_process_exit(attempt_id)
    launch = store.load_process_launch(attempt_id)
    exit_path = store.record_path_for(attempt_id, "process-exit")
    if exit_evidence_findings(
        launch, exit_record, process_count=exit_record.get("process_count")
    ):
        raise ValueError("first owned process exit is unverified")
    disposition = exit_record.get("disposition")
    if disposition == "exited_dirty":
        store.require_immutable_phase(attempt_id, "setup", "stopped")
        if store.cleanup_started(attempt_id):
            raise ValueError("dirty retirement conflicts with cleanup")
        return "exited_dirty", hashlib.sha256(exit_path.read_bytes()).hexdigest()
    if disposition == "exited":
        store.require_immutable_phase(attempt_id, "cleanup", "restored")
        return "restored", hashlib.sha256(exit_path.read_bytes()).hexdigest()
    raise ValueError("first retirement disposition is unverified")


def _record_correction(
    root: Path, attempt_id: str, first_attempt_id: str, correction_file: str
) -> int:
    """Retain a first-result-bound cause and corrected source before attempt two."""
    store = ServerPtCommissioningStore(root)
    if first_attempt_id == attempt_id or _ATTEMPT.fullmatch(first_attempt_id) is None:
        _print({"outcome": "refused", "reason": "first_attempt_identity_invalid"})
        return 2
    try:
        if store.setup_attempt_ids() != (first_attempt_id,) or store.verify_index():
            raise ValueError("first campaign attempt is not a validated single result")
        first_status_name = (
            "acceptance-status"
            if store.record_path_for(first_attempt_id, "acceptance-status").exists()
            else "setup-status"
        )
        first_status = (
            store.load_acceptance_status(first_attempt_id)
            if first_status_name == "acceptance-status"
            else store.load_phase_status(first_attempt_id, "setup")
        )
        retirement_outcome, retirement_sha = _first_retirement(store, first_attempt_id)
        first_grant = store.load_phase_grant(first_attempt_id, "setup")
        source = repository_identity(root)
        if (
            source.error
            or source.clean is not True
            or source.upstream_head != source.head
        ):
            raise ValueError("corrected checkout is not clean and published")
        raw = Path(correction_file).read_bytes()
        if len(raw) > 16 * 1024:
            raise ValueError("causal correction exceeds input budget")
        correction = json.loads(raw)
        if not isinstance(correction, dict):
            raise ValueError("causal correction is not an object")
        first_result_sha = hashlib.sha256(
            store.record_path_for(first_attempt_id, first_status_name).read_bytes()
        ).hexdigest()
        findings = second_attempt_findings(
            first_attempt_id=first_attempt_id,
            first_process_incarnation=first_grant.process_incarnation,
            first_result_outcome=str(first_status.get("outcome") or ""),
            first_retirement_outcome=retirement_outcome,
            first_result_sha256=first_result_sha,
            first_retirement_sha256=retirement_sha,
            new_source_sha=source.head,
            new_process_incarnation="pending-fresh-process",
            correction=correction,
        )
        if findings:
            raise ValueError("causal correction does not bind the first result")
        path = store.save_causal_correction(attempt_id, correction)
        status = {
            "phase": "correction",
            "outcome": "recorded",
            "attempt_id": attempt_id,
            "first_attempt_id": first_attempt_id,
            "corrected_source_sha": source.head,
            "correction_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        findings = _refresh_archive(store, status)
        if findings:
            raise ValueError("causal correction archive is unverified")
    except (OSError, ValueError) as exc:
        _print(
            {"outcome": "refused", "reason": f"causal_correction:{type(exc).__name__}"}
        )
        return 2
    _print(status)
    return 0


def _record_launch(
    root: Path, attempt_id: str, ci_run_id: int, evidence_file: str
) -> int:
    """Pin a campaign-created disposable PT process before qualification."""
    store = ServerPtCommissioningStore(root)
    preflight = phase_preflight(root, ci_run_id=ci_run_id)
    if preflight.findings or preflight.process is None:
        _print({"outcome": "refused", "reasons": list(preflight.findings)})
        return 2
    try:
        raw = Path(evidence_file).read_bytes()
        if len(raw) > 16 * 1024:
            raise ValueError("launch capture exceeds input budget")
        launch = json.loads(raw)
        if not isinstance(launch, dict):
            raise ValueError("launch capture is not an object")
        findings = launch_evidence_findings(launch, preflight.process)
        if findings:
            raise ValueError("launch capture does not prove campaign ownership")
        document = {
            **launch,
            "capture_sha256": hashlib.sha256(raw).hexdigest(),
            "capture_text": raw.decode("utf-8"),
            "charter_sha256": CHARTER_SHA256,
            "source_sha": preflight.source.head if preflight.source else "",
            "source_tree": preflight.source.tree if preflight.source else "",
            "ci_run_id": preflight.ci.run_id if preflight.ci else 0,
        }
        path = store.save_process_launch(attempt_id, document)
        status = {
            "phase": "launch",
            "outcome": "owned",
            "attempt_id": attempt_id,
            "process_id": preflight.process.process_id,
            "launch_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        archive = _refresh_archive(store, status)
        if archive:
            raise ValueError("owned launch archive is unverified")
    except (OSError, ValueError) as exc:
        _print(
            {"outcome": "refused", "reason": f"launch_evidence:{type(exc).__name__}"}
        )
        return 2
    _print(status)
    return 0


def _record_exit(
    root: Path, attempt_id: str, ci_run_id: int, evidence_file: str
) -> int:
    """Record graceful close only after OS census proves the owned PT exited."""
    store = ServerPtCommissioningStore(root)
    try:
        try:
            store.require_archived_phase(attempt_id, "cleanup", "restored")
            disposition = "exited"
        except ValueError:
            store.require_archived_phase(attempt_id, "setup", "stopped")
            if store.cleanup_started(attempt_id):
                raise ValueError("dirty retirement conflicts with cleanup") from None
            disposition = "exited_dirty"
        launch = store.load_process_launch(attempt_id)
        setup_grant = store.load_phase_grant(attempt_id, "setup")
        source = repository_identity(root)
        if (
            source.error
            or source.clean is not True
            or source.upstream_head != source.head
            or source.head != setup_grant.source_sha
            or source.tree != setup_grant.source_tree
        ):
            raise ValueError("retirement source differs from setup")
        ci, findings = read_exact_ci(ci_run_id, source.head, checkout=root)
        if findings or ci is None:
            raise ValueError("retirement exact-SHA CI is unobservable")
        raw = Path(evidence_file).read_bytes()
        if len(raw) > 16 * 1024:
            raise ValueError("graceful close capture exceeds input budget")
        close = json.loads(raw)
        if not isinstance(close, dict):
            raise ValueError("graceful close capture is not an object")
        observed = PowerShellPacketTracerProcessReader(timeout_seconds=10).read()
        if observed.error:
            raise ValueError("process exit census is unreadable")
        findings = exit_evidence_findings(
            launch, close, process_count=len(observed.processes)
        )
        if findings:
            raise ValueError("graceful process exit is unverified")
        document = {
            **close,
            "disposition": disposition,
            "close_capture_sha256": hashlib.sha256(raw).hexdigest(),
            "close_capture_text": raw.decode("utf-8"),
            "observed_at_utc": datetime.now(UTC).isoformat(),
            "process_count": len(observed.processes),
            "source_sha": source.head,
            "source_tree": source.tree,
            "ci_run_id": ci.run_id,
            "charter_sha256": CHARTER_SHA256,
        }
        path = store.save_process_exit(attempt_id, document)
        status = {
            "phase": "retirement",
            "outcome": disposition,
            "attempt_id": attempt_id,
            "process_id": launch.get("pid"),
            "exit_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        archive = _refresh_archive(store, status)
        if archive:
            raise ValueError("process exit archive is unverified")
    except (OSError, ValueError) as exc:
        _print({"outcome": "refused", "reason": f"process_exit:{type(exc).__name__}"})
        return 2
    _print(status)
    return 0


def _prequalification_recovery_findings(
    store: ServerPtCommissioningStore,
    attempt_id: str,
    *,
    first_attempt_id: str,
    first_status_sha256: str,
    new_process_incarnation: str | None = None,
) -> tuple[str, ...]:
    """Admit only the operator's indexed, zero-contact preliminary replacement."""
    try:
        if (
            _ATTEMPT.fullmatch(attempt_id) is None
            or attempt_id == first_attempt_id
            or attempt_id != RECOVERY_PREQUALIFICATION_ATTEMPT
            or store.prequalification_attempt_ids() != (first_attempt_id,)
            or store.setup_attempt_ids()
            or not store.index_exists()
            or store.verify_index()
        ):
            return ("prequalification_recovery_inventory_invalid",)
        status = store.require_immutable_phase(
            first_attempt_id, "prequalification", "stopped"
        )
        status_path = store.record_path_for(first_attempt_id, "prequalification-status")
        first_grant = store.load_phase_grant(first_attempt_id, "prequalification")
        if (
            hashlib.sha256(status_path.read_bytes()).hexdigest() != first_status_sha256
            or status.get("operations_used") != 0
            or status.get("reason") != "prequalification_boundary:ValueError"
            or first_grant.attempt_id != first_attempt_id
            or store.record_path_for(first_attempt_id, "prequalification").exists()
            or store.journal_path_for(first_attempt_id, "prequalification").exists()
        ):
            return ("prequalification_recovery_first_result_invalid",)
        if new_process_incarnation is not None and (
            not new_process_incarnation
            or new_process_incarnation == first_grant.process_incarnation
        ):
            return ("prequalification_recovery_process_not_fresh",)
    except (OSError, ValueError):
        return ("prequalification_recovery_evidence_unverified",)
    return ()


def _qualify(root: Path, attempt_id: str, ci_run_id: int) -> int:
    """Measure the two authorized prerequisites through one fixed file channel."""
    store = ServerPtCommissioningStore(root)
    try:
        already = store.prequalification_attempt_ids()
    except OSError:
        _print(
            {"outcome": "refused", "reason": "prequalification_inventory_unreadable"}
        )
        return 2
    if attempt_id == RECOVERY_PREQUALIFICATION_ATTEMPT:
        recovery = _prequalification_recovery_findings(
            store,
            attempt_id,
            first_attempt_id=_RECOVERY_FIRST_ATTEMPT,
            first_status_sha256=_RECOVERY_FIRST_STATUS_SHA256,
        )
        if recovery:
            _print(
                {
                    "outcome": "refused",
                    "reason": "prequalification_recovery_unverified",
                    "recovery_findings": list(recovery),
                }
            )
            return 2
    elif already:
        _print({"outcome": "refused", "reason": "prequalification_already_reserved"})
        return 2
    if store.index_exists() and store.verify_index():
        _print({"outcome": "refused", "reason": "prior_archive_unverified"})
        return 2
    preflight = phase_preflight(root, ci_run_id=ci_run_id)
    if preflight.findings:
        _print({"outcome": "refused", "reasons": list(preflight.findings)})
        return 2
    assert preflight.source is not None
    assert preflight.process is not None
    assert preflight.ci is not None
    if attempt_id == RECOVERY_PREQUALIFICATION_ATTEMPT:
        recovery = _prequalification_recovery_findings(
            store,
            attempt_id,
            first_attempt_id=_RECOVERY_FIRST_ATTEMPT,
            first_status_sha256=_RECOVERY_FIRST_STATUS_SHA256,
            new_process_incarnation=preflight.process.process_incarnation,
        )
        if recovery:
            _print({"outcome": "refused", "recovery_findings": list(recovery)})
            return 2
    try:
        launch = store.load_process_launch(attempt_id)
        if launch_evidence_findings(launch, preflight.process):
            raise ValueError("qualified receiver was not campaign launched")
        if (
            launch.get("source_sha") != preflight.source.head
            or launch.get("source_tree") != preflight.source.tree
        ):
            raise ValueError("launch source differs from preliminary source")
    except (OSError, ValueError):
        _print({"outcome": "refused", "reason": "campaign_launch_unverified"})
        return 2
    bound = None
    result = None
    path = None
    reason = ""
    interrupted = False
    try:
        grant = derive_server_pt_phase_grant(
            "prequalification",
            attempt_id,
            preflight.source,
            preflight.process,
            preflight.ci,
        )
        with bind_live_phase(preflight, grant, store=store) as bound:
            fixed = FixedChannelProductTransport("file", bound.channel)

            def waited(script: str, timeout: float) -> str | None:
                return fixed.send_and_wait(script, timeout, "file")

            physical = PacketTracerPhysicalTopologyRuntime(waited)
            probe = PacketTracerBridgeProbeRuntime(
                waited,
                packet_tracer_version=grant.build,
                send=lambda script: fixed.send_payload(script, "file"),
                transport_channel="file",
                operational_readiness_seconds=30.0,
            )
            result = prequalify_server_pt(
                physical,
                probe,
                attempt_token=attempt_id[:8],
                cleanup_scope=bound.channel.cleanup_scope,
            )
            path = store.save_prequalification(attempt_id, result)
    except BaseException as exc:
        interrupted = isinstance(exc, KeyboardInterrupt)
        reason = f"prequalification_boundary:{type(exc).__name__}"
    release = bound.release_findings if bound else ()
    if bound and time.monotonic() - bound.channel.started > bound.channel.max_seconds:
        reason = reason or "prequalification_phase_time_exceeded"
    ready = bool(
        result and result.ready_for_catalog_review and not release and not reason
    )
    status = {
        "phase": "prequalification",
        "attempt_id": attempt_id,
        "outcome": "ready_for_catalog_review" if ready else "stopped",
        "reason": reason,
        "record_path": str(path) if path else "",
        "record_sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path else "",
        "grant_path": str(store.record_path_for(attempt_id, "prequalification-grant")),
        "raw_path": str(store.journal_path_for(attempt_id, "prequalification")),
        "operations_used": bound.channel.used_operations if bound else 0,
        "errors": [*(result.errors if result else []), *release],
    }
    try:
        store.save_phase_status(attempt_id, "prequalification", status)
    except (OSError, ValueError) as exc:
        status["outcome"] = "stopped"
        status["reason"] = (
            f"prequalification_status_persistence_failed:{type(exc).__name__}"
        )
    _archive_or_stop(store, status)
    _print(status)
    return (
        130
        if interrupted
        else 0
        if status["outcome"] == "ready_for_catalog_review"
        else 1
    )


def _setup(root: Path, attempt_id: str, ci_run_id: int) -> int:
    """Deploy exact E4 and L2 E5 after preliminary evidence was pinned."""
    store = ServerPtCommissioningStore(root)
    used_attempts = store.setup_attempt_ids()
    if attempt_id in used_attempts:
        _print({"outcome": "refused", "reason": "setup_attempt_already_reserved"})
        return 2
    if len(used_attempts) >= 2:
        _print({"outcome": "refused", "reason": "campaign_attempt_allowance_exhausted"})
        return 2
    qualification_id = used_attempts[0] if used_attempts else attempt_id
    try:
        preliminary = store.load_prequalification(qualification_id)
        bundle = store.load_bundle(attempt_id)
        prequal_path = store.record_path_for(qualification_id, "prequalification")
        bundle_path = store.bundle_path_for(attempt_id)
    except (OSError, ValueError) as exc:
        _print(
            {
                "outcome": "refused",
                "reason": f"setup_input_missing:{type(exc).__name__}",
            }
        )
        return 2
    if not preliminary.ready_for_catalog_review:
        _print({"outcome": "refused", "reason": "prequalification_not_verified"})
        return 2
    try:
        store.require_immutable_phase(
            qualification_id, "prequalification", "ready_for_catalog_review"
        )
    except ValueError:
        _print({"outcome": "refused", "reason": "prequalification_archive_unverified"})
        return 2
    try:
        capability_catalog, port_inventory = scoped_setup_evidence(preliminary)
    except ValueError:
        _print({"outcome": "refused", "reason": "prequalification_scope_invalid"})
        return 2
    preflight = phase_preflight(root, ci_run_id=ci_run_id)
    if preflight.findings:
        _print({"outcome": "refused", "reasons": list(preflight.findings)})
        return 2
    assert preflight.source is not None
    assert preflight.process is not None
    assert preflight.ci is not None
    try:
        launch = store.load_process_launch(attempt_id)
        if launch_evidence_findings(launch, preflight.process):
            raise ValueError("setup receiver was not campaign launched")
    except (OSError, ValueError):
        _print({"outcome": "refused", "reason": "campaign_launch_unverified"})
        return 2
    if used_attempts:
        first = used_attempts[0]
        try:
            correction = store.load_causal_correction(attempt_id)
            first_grant = store.load_phase_grant(first, "setup")
            first_result_phase = (
                "acceptance"
                if store.record_path_for(first, "acceptance-status").exists()
                else "setup"
            )
            first_result = (
                store.load_acceptance_status(first)
                if first_result_phase == "acceptance"
                else store.load_phase_status(first, "setup")
            )
            retirement_outcome, retirement_sha = _first_retirement(store, first)
            first_result_path = store.record_path_for(
                first, first_result_phase + "-status"
            )
            findings = second_attempt_findings(
                first_attempt_id=first,
                first_process_incarnation=first_grant.process_incarnation,
                first_result_outcome=str(first_result.get("outcome") or ""),
                first_retirement_outcome=retirement_outcome,
                first_result_sha256=hashlib.sha256(
                    first_result_path.read_bytes()
                ).hexdigest(),
                first_retirement_sha256=retirement_sha,
                new_source_sha=preflight.source.head,
                new_process_incarnation=preflight.process.process_incarnation,
                correction=correction,
            )
        except (OSError, ValueError) as exc:
            _print(
                {
                    "outcome": "refused",
                    "reason": f"second_attempt_evidence:{type(exc).__name__}",
                }
            )
            return 2
        if findings:
            _print({"outcome": "refused", "reasons": list(findings)})
            return 2
    grant = derive_server_pt_phase_grant(
        "setup",
        attempt_id,
        preflight.source,
        preflight.process,
        preflight.ci,
        bundle_sha256=hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
        prequalification_sha256=hashlib.sha256(prequal_path.read_bytes()).hexdigest(),
        prequalification_attempt_id=qualification_id,
        bundle=bundle,
    )
    bound = None
    result = None
    reason = ""
    interrupted = False
    try:
        with bind_live_phase(preflight, grant, store=store, bundle=bundle) as bound:
            fixed = FixedChannelProductTransport("file", bound.channel)

            def waited(script: str, timeout: float) -> str | None:
                return fixed.send_and_wait(script, timeout, "file")

            topology = TopologyPlan.model_validate_json(bundle.topology_json)
            names = [device.name for device in topology.devices]
            physical = PacketTracerPhysicalTopologyRuntime(
                waited, mutation_timeout_seconds=3.0, observation_timeout_seconds=3.0
            )
            configuration = PacketTracerEnterpriseConfigurationRuntime(
                query_inventory=lambda: fixed.query_inventory(names, "file"),
                send=lambda script: fixed.send_payload(script, "file"),
                send_and_wait=waited,
                trunk_timeout_seconds=5.0,
                ios_boot_timeout_seconds=45.0,
                ios_query_max_calls=E5_IOS_QUERY_MAX_CALLS,
                ios_query_max_seconds=E5_IOS_QUERY_MAX_SECONDS,
                wait_allowance=lambda: max(
                    0.0,
                    bound.channel.max_seconds
                    - (time.monotonic() - bound.channel.started),
                ),
            )
            result = run_server_pt_setup(
                attempt_id,
                deployment_id=grant.deployment_id,
                store=store,
                physical_runtime=physical,
                configuration_runtime=configuration,
                environment_fingerprint=EnvironmentFingerprint(
                    backend="packet_tracer",
                    backend_version=bundle.build,
                    bridge_transport="file",
                    runtime_mode="logical-workspace",
                ),
                admission=bound.channel.authority,
                port_inventory=port_inventory,
                capability_catalog=capability_catalog,
            )
        if bound.release_findings:
            reason = ",".join(bound.release_findings)
        elif result is None:
            reason = "setup_result_missing"
        elif not result.ready:
            reason = result.reason
        else:
            if (
                store.load_e4(attempt_id) != result.physical
                or store.load_e5(attempt_id) != result.configuration
            ):
                reason = "setup_result_reload_mismatch"
            postflight = PacketTracerDiagnosticLifecycleReader().read(
                time.monotonic() + 10.0
            )
            continuity = diagnostic_lifecycle_continuity(preflight.process, postflight)
            if continuity:
                reason = "setup_postflight:" + ",".join(continuity)
    except BaseException as exc:
        interrupted = isinstance(exc, KeyboardInterrupt)
        reason = f"setup_boundary:{type(exc).__name__}"
    if bound and time.monotonic() - bound.channel.started > bound.channel.max_seconds:
        reason = reason or "setup_phase_time_exceeded"
    if result is not None and result.manifest_path:
        try:
            store.register_external_source(
                attempt_id, "manifest", Path(result.manifest_path)
            )
        except (OSError, ValueError) as exc:
            reason = f"manifest_archive_failed:{type(exc).__name__}"
    status = {
        "phase": "setup",
        "outcome": "ready" if not reason else "stopped",
        "reason": reason,
        "attempt_id": attempt_id,
        "deployment_id": grant.deployment_id,
        "manifest_path": result.manifest_path if result else "",
        "operations_used": bound.channel.used_operations if bound else 0,
        "release_findings": list(bound.release_findings) if bound else [],
    }
    try:
        store.save_phase_status(attempt_id, "setup", status)
    except (OSError, ValueError) as exc:
        status["outcome"] = "stopped"
        status["reason"] = f"setup_status_persistence_failed:{type(exc).__name__}"
    _archive_or_stop(store, status)
    _print(status)
    return 130 if interrupted else 0 if status["outcome"] == "ready" else 1


def _cleanup(root: Path, attempt_id: str, ci_run_id: int) -> int:
    """Remove only E4-owned objects with the original receiver still bound."""
    store = ServerPtCommissioningStore(root)
    try:
        bundle = store.load_bundle(attempt_id)
        store.load_baseline(attempt_id)
        store.load_e4(attempt_id)
        setup_grant = store.load_phase_grant(attempt_id, "setup")
        prequal_path = store.record_path_for(
            setup_grant.prequalification_attempt_id, "prequalification"
        )
        bundle_path = store.bundle_path_for(attempt_id)
        prequal_sha = hashlib.sha256(prequal_path.read_bytes()).hexdigest()
        bundle_sha = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    except (OSError, ValueError) as exc:
        _print(
            {
                "outcome": "refused",
                "reason": f"cleanup_input_missing:{type(exc).__name__}",
            }
        )
        return 2
    if store.verify_index():
        _print({"outcome": "refused", "reason": "prior_archive_unverified"})
        return 2
    preflight = phase_preflight(root, ci_run_id=ci_run_id)
    if preflight.findings:
        _print({"outcome": "refused", "reasons": list(preflight.findings)})
        return 2
    assert preflight.source is not None
    assert preflight.process is not None
    assert preflight.ci is not None
    if (
        preflight.source.head != setup_grant.source_sha
        or preflight.source.tree != setup_grant.source_tree
        or preflight.process.process_id != setup_grant.process_id
        or preflight.process.process_path != setup_grant.process_path
        or preflight.process.process_incarnation != setup_grant.process_incarnation
    ):
        _print({"outcome": "refused", "reason": "cleanup_source_or_receiver_changed"})
        return 2
    grant = derive_server_pt_phase_grant(
        "cleanup",
        attempt_id,
        preflight.source,
        preflight.process,
        preflight.ci,
        bundle_sha256=bundle_sha,
        prequalification_sha256=prequal_sha,
        prequalification_attempt_id=setup_grant.prequalification_attempt_id,
        bundle=bundle,
    )
    bound = None
    result = None
    reason = ""
    interrupted = False
    try:
        with bind_live_phase(preflight, grant, store=store, bundle=bundle) as bound:
            fixed = FixedChannelProductTransport("file", bound.channel)
            physical = PacketTracerPhysicalTopologyRuntime(
                lambda script, timeout: fixed.send_and_wait(script, timeout, "file"),
                mutation_timeout_seconds=2.5,
                observation_timeout_seconds=2.5,
            )
            result = run_server_pt_cleanup(
                attempt_id,
                store=store,
                physical_runtime=physical,
                admission=bound.channel.authority,
            )
        if bound.release_findings:
            reason = ",".join(bound.release_findings)
        elif result is None:
            reason = "cleanup_result_missing"
        elif not result.restored:
            reason = ",".join(result.errors) or "cleanup_restoration_not_proven"
        else:
            if store.load_cleanup(attempt_id) != result:
                reason = "cleanup_result_reload_mismatch"
            postflight = PacketTracerDiagnosticLifecycleReader().read(
                time.monotonic() + 10.0
            )
            continuity = diagnostic_lifecycle_continuity(preflight.process, postflight)
            if continuity:
                reason = "cleanup_postflight:" + ",".join(continuity)
    except BaseException as exc:
        interrupted = isinstance(exc, KeyboardInterrupt)
        reason = f"cleanup_boundary:{type(exc).__name__}"
    if bound and time.monotonic() - bound.channel.started > bound.channel.max_seconds:
        reason = reason or "cleanup_phase_time_exceeded"
    status = {
        "phase": "cleanup",
        "outcome": "restored" if not reason else "stopped",
        "reason": reason,
        "attempt_id": attempt_id,
        "deployment_id": grant.deployment_id,
        "removed_devices": len(result.removals) if result else 0,
        "operations_used": bound.channel.used_operations if bound else 0,
        "release_findings": list(bound.release_findings) if bound else [],
    }
    try:
        store.save_phase_status(attempt_id, "cleanup", status)
    except (OSError, ValueError) as exc:
        status["outcome"] = "stopped"
        status["reason"] = f"cleanup_status_persistence_failed:{type(exc).__name__}"
    _archive_or_stop(store, status)
    _print(status)
    return 130 if interrupted else 0 if status["outcome"] == "restored" else 1


def _retain_acceptance_sources(store: ServerPtCommissioningStore, attempt_id: str):
    """Pin every product source that exists, including an interrupted attempt."""
    envelopes = ColdHttpAcceptanceStore(
        store.root / "data" / "acceptance" / "cold-http"
    )
    sources = (
        ("acceptance-begin", envelopes.path_for(attempt_id)),
        ("acceptance-terminal", envelopes.completed_path_for(attempt_id)),
        ("publication", envelopes.publication_path_for(attempt_id)),
    )
    for label, source in sources:
        if source.exists() and not store.external_source_registered(attempt_id, label):
            store.register_external_source(attempt_id, label, source)
    if not any(source.exists() for _, source in sources):
        return None
    envelope = envelopes.load(attempt_id)
    product_path = envelope.product.get("record_path")
    if (
        isinstance(product_path, str)
        and product_path
        and not store.external_source_registered(attempt_id, "product-record")
    ):
        store.register_external_source(attempt_id, "product-record", Path(product_path))
    return envelope


def _accept(root: Path, attempt_id: str, ci_run_id: int) -> int:
    """Run the existing product coordinator with its sealed schema-2 grant."""
    store = ServerPtCommissioningStore(root)
    try:
        store.load_bundle(attempt_id)
        store.load_phase_status(attempt_id, "setup")
        store.load_e4(attempt_id)
        store.load_e5(attempt_id)
    except (OSError, ValueError) as exc:
        _print(
            {
                "outcome": "refused",
                "reason": f"acceptance_input_missing:{type(exc).__name__}",
            }
        )
        return 2
    preflight = phase_preflight(root, ci_run_id=ci_run_id)
    if preflight.findings:
        _print({"outcome": "refused", "reasons": list(preflight.findings)})
        return 2
    assert preflight.source is not None
    assert preflight.process is not None
    assert preflight.ci is not None
    try:
        sealed = seal_server_pt_acceptance(
            attempt_id,
            store=store,
            source=preflight.source,
            process=preflight.process,
            ci=preflight.ci,
        )
    except (OSError, ValueError) as exc:
        _print(
            {
                "outcome": "refused",
                "reason": f"acceptance_seal_failed:{type(exc).__name__}",
            }
        )
        return 2
    raw_path = store.journal_path_for(attempt_id, "acceptance")

    def boundaries_factory(governed_root: Path):
        boundaries = acceptance_cli.production_boundaries(governed_root)

        def open_recorded(channel: str) -> OpenedTransport:
            opened = acceptance_cli.open_file_channel(channel)
            if opened.transport is None or not opened.live:
                return opened
            recorded = GovernedPhaseChannel(
                opened.transport,
                raw_path,
                phase="acceptance",
                max_operations=int(sealed.grant["max_operations"]),
                max_seconds=float(sealed.grant["max_seconds"]),
                authority=lambda: (),
            )
            return OpenedTransport(channel, recorded, opened.live, opened.detail)

        return replace(boundaries, open_channel=open_recorded)

    output = StringIO()
    reason = ""
    interrupted = False
    summary: dict[str, object] = {}
    try:
        with redirect_stdout(output):
            exit_code = acceptance_cli.main(
                [
                    "--execute",
                    "--grant",
                    sealed.grant_path,
                    "--intent",
                    str(store.intent_path_for(attempt_id)),
                ],
                environ={"PT_MCP_GOVERNED_ROOT": str(root)},
                boundaries_factory=boundaries_factory,
            )
        summary = json.loads(output.getvalue())
        envelope = _retain_acceptance_sources(store, attempt_id)
        if exit_code == 0 and envelope is None:
            raise ValueError("accepted attempt lacks an envelope")
        if raw_path.exists():
            if envelope is not None:
                raw_index = build_raw_answer_index(raw_path, envelope)
                store.save_acceptance_raw_index(attempt_id, raw_index)
        elif exit_code == 0:
            raise ValueError("original acceptance answers were not retained")
        if exit_code == 0:
            envelopes = ColdHttpAcceptanceStore(
                root / "data" / "acceptance" / "cold-http"
            )
            publication = envelopes.load_publication(attempt_id)
            if publication_claim(envelope, publication) != (True, ""):
                reason = "publication_claim_not_established"
            elif len(envelope.clients) != 30 or any(
                not item.accepted or item.release_outcome != "released"
                for item in envelope.clients
            ):
                reason = "thirty_client_ownership_not_accounted"
        else:
            reason = "product_acceptance_not_established"
    except BaseException as exc:
        interrupted = isinstance(exc, KeyboardInterrupt)
        exit_code = 1
        reason = f"acceptance_boundary:{type(exc).__name__}"
    try:
        _retain_acceptance_sources(store, attempt_id)
    except (OSError, ValueError) as exc:
        reason = (
            reason + ";" if reason else ""
        ) + f"source_archive:{type(exc).__name__}"
    status = {
        "phase": "acceptance",
        "outcome": "accepted" if exit_code == 0 and not reason else "stopped",
        "reason": reason,
        "exit_code": exit_code,
        "attempt_id": attempt_id,
        "grant_path": sealed.grant_path,
        "seal_path": sealed.seal_path,
        "raw_path": str(raw_path) if raw_path.exists() else "",
        "product_summary": summary,
    }
    try:
        store.save_acceptance_status(attempt_id, status)
    except (OSError, ValueError) as exc:
        status["outcome"] = "stopped"
        status["reason"] = f"acceptance_status_persistence_failed:{type(exc).__name__}"
    _archive_or_stop(store, status)
    _print(status)
    return 130 if interrupted else 0 if status["outcome"] == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
