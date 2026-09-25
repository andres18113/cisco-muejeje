"""Governed Server-PT commissioning phases for one disposable campaign.

`--campaign c31` (the default) is the delivery campaign exactly as before:
exact-SHA CI, a published HEAD and its two-attempt limit. `--campaign
fastloop` is the experimental campaign: a clean committed checkpoint and no CI
claim, bounded instead by its cumulative ledger. Every experimental phase
belongs to an episode opened before contact, and is admitted against that
episode's allocation before its mailbox is bound.

`--campaign dhcp-fastloop` is the S3/Q3 DHCP campaign. Its bridge work is a
governed qualification stage run by the qualification CLI, so here it may
only open, close and report its ledger episodes, record a launch and retire
it. It never forces a retirement: its charter does not authorize one.
"""

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
from itertools import pairwise
from pathlib import Path

from ...application.ports.service_qualification import OpenedTransport
from ...application.use_cases.accept_cold_http import (
    MEASURED_EXIT_CODE,
    ExperimentalSourceAuthority,
)
from ...application.use_cases.cleanup_server_pt_commissioning import (
    run_server_pt_cleanup,
)
from ...application.use_cases.deploy_enterprise_topology import (
    disposable_workspace_error,
)
from ...application.use_cases.prepare_server_pt_commissioning import (
    prepare_server_pt_commissioning,
)
from ...application.use_cases.prequalify_server_pt import prequalify_server_pt
from ...application.use_cases.seal_server_pt_acceptance import (
    seal_server_pt_acceptance,
)
from ...application.use_cases.server_pt_campaign import (
    C31_CAMPAIGN,
    DHCP_FASTLOOP_CAMPAIGN,
    FASTLOOP_CAMPAIGN,
    ServerPtCampaign,
    source_authority_findings,
)
from ...application.use_cases.server_pt_campaign_ledger import (
    allowance_for,
    closing_findings,
    episode_allowance_left,
    episode_name,
    ledger_record_findings,
    ledger_totals,
    opening_findings,
    qualification_admitted,
    qualification_settled,
    unsettled_phases,
)
from ...application.use_cases.server_pt_historical_exit import (
    FASTLOOP_EPISODE_1_EXIT_IMPORT,
    excerpt_lines,
    historical_exit_claim,
    historical_exit_import_findings,
)
from ...application.use_cases.server_pt_phase_budget import (
    E5_IOS_QUERY_MAX_CALLS,
    E5_IOS_QUERY_MAX_SECONDS,
    derive_phase_budget,
)
from ...application.use_cases.server_pt_phase_grant import (
    RECOVERY_PREQUALIFICATION_ATTEMPT,
    derive_server_pt_phase_grant,
)
from ...application.use_cases.server_pt_process_evidence import (
    exit_evidence_findings,
    exit_was_forced,
    force_window_findings,
    incarnation_ticks,
    launch_evidence_findings,
    launched_blank,
    lingering_process_findings,
    observed_process_findings,
    packet_tracer_process_role,
    select_document_window,
    window_signature_for_launch,
    window_signature_record,
)
from ...application.use_cases.server_pt_second_attempt import second_attempt_findings
from ...application.use_cases.setup_server_pt_commissioning import (
    run_server_pt_setup,
)
from ...domain.enterprise.models.cold_http_acceptance import publication_claim
from ...domain.enterprise.models.deployment import EnvironmentFingerprint
from ...domain.enterprise.models.scalable_http_acceptance import (
    EXPERIMENTAL_ENVELOPE_LIMITATION,
)
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
from ...infrastructure.execution.file_bridge import bridge_dir
from ...infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
    governed_root_from_env,
)
from ...infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
)
from ...infrastructure.execution.probe_runtime import PacketTracerBridgeProbeRuntime
from ...infrastructure.execution.product_channel import FixedChannelProductTransport
from ...infrastructure.execution.server_pt_campaign_authority import (
    read_exact_ci,
    read_source_ancestry,
)
from ...infrastructure.execution.server_pt_phase_channel import GovernedPhaseChannel
from ...infrastructure.execution.server_pt_process_control import (
    PowerShellOwnedProcessControl,
)
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
from .server_pt_campaign_archive import (
    archive_or_stop as _archive_or_stop,
)
from .server_pt_campaign_archive import (
    ledger_admit as _ledger_admit,
)
from .server_pt_campaign_archive import (
    ledger_result as _ledger_result,
)
from .server_pt_campaign_archive import (
    refresh_archive as _refresh_archive,
)
from .server_pt_live_phase import FEATURE_BRANCH, bind_live_phase, phase_preflight
from .service_qualification import repository_identity

_ATTEMPT = re.compile(r"[0-9a-f]{32}\Z")
_RECOVERY_FIRST_ATTEMPT = "979b4636d50290d199e8ea0f95eddab3"
_RECOVERY_FIRST_STATUS_SHA256 = (
    "c623ec5dbc62e108568cff6a41ab858d451de2e86c1ab426690dfdecae2e2829"
)
_CAMPAIGNS = {
    "c31": C31_CAMPAIGN,
    "fastloop": FASTLOOP_CAMPAIGN,
    "dhcp-fastloop": DHCP_FASTLOOP_CAMPAIGN,
}
#: The charter digest each campaign's LIVE modes require. Read at call time,
#: per campaign, so the C31 digest remains this module's one charter seam.
CHARTER_SHA256 = C31_CAMPAIGN.charter_sha256
FASTLOOP_CHARTER_SHA256 = FASTLOOP_CAMPAIGN.charter_sha256
DHCP_FASTLOOP_CHARTER_SHA256 = DHCP_FASTLOOP_CAMPAIGN.charter_sha256
#: One episode plan or closing is operator-written JSON; bound what it may be.
_LEDGER_INPUT_LIMIT = 16 * 1024
#: The OS helper that observes, closes and terminates one exact PID.
_PROCESS_CONTROL = PowerShellOwnedProcessControl
#: How long a graceful close may take before the owned process may be forced,
#: and how long the exit after a termination is awaited. Bounded both ways.
RETIREMENT_GRACE_SECONDS = 60.0
RETIREMENT_EXIT_WAIT_SECONDS = 30.0
#: After the owned process is gone, how long its own helper processes (such
#: as `--progress-bar-server`) are given to exit before the census is judged.
RETIREMENT_HELPER_WAIT_SECONDS = 30.0
_RETIREMENT_POLL_SECONDS = 1.0
#: How far wall and monotonic time may disagree between two readings before
#: the wall clock is taken to have stepped and no exit bound is claimed.
_CLOCK_TOLERANCE_SECONDS = 1.0
_retirement_sleep = time.sleep
#: The retiring process must itself be the isolated production process:
#: checkout interpreter and package, one namespace, no test runner.
_RETIREMENT_ISOLATION = ImportIsolationPreflight
#: The one historical exit an operator addendum authorizes importing, and
#: the read-only Git question that binds its episode to the recorder.
_EXIT_IMPORT_AUTHORITY = FASTLOOP_EPISODE_1_EXIT_IMPORT
_SOURCE_ANCESTRY = read_source_ancestry
_MAILBOX_DIR = bridge_dir
#: Byte budgets of the operator-written manifest, of one original artifact
#: and of the transcript whose lines an excerpt must reproduce.
_IMPORT_MANIFEST_LIMIT = 16 * 1024
_IMPORT_ARTIFACT_LIMIT = 1024 * 1024
_IMPORT_TRANSCRIPT_LIMIT = 64 * 1024 * 1024
_IMPORT_SUFFIXES = {
    "close_capture": ".json",
    "close_request_output": ".txt",
    "prelaunch_census": ".json",
    "transcript_excerpt": ".jsonl",
    "event_log_query": ".txt",
}
_IMPORT_LIMITATIONS = (
    "The exit instant and cause were not observed; the owned PID's absence was.",
    "A successful close request is not proof of exit; only the later "
    "absence readings and the zero census are.",
    "Transcript times are the lead session's clock, not the operating "
    "system's, and bound when an answer arrived, not when it was read.",
    "The retained command range shows what the lead ran; it cannot show "
    "what any other actor did to the process.",
    "The fresh census and mailbox inspection establish the state at archive time only.",
    "Only the index that preceded this import is preserved; earlier indexes "
    "of the episode were replaced in place and are not recoverable.",
)


def _charter_digest(campaign: ServerPtCampaign) -> str:
    """Return the digest this campaign's charter must have."""
    if campaign.campaign_id == DHCP_FASTLOOP_CAMPAIGN.campaign_id:
        return DHCP_FASTLOOP_CHARTER_SHA256
    return FASTLOOP_CHARTER_SHA256 if campaign.experimental else CHARTER_SHA256


#: What the DHCP campaign may do through this adapter. Its bridge work is a
#: qualification stage; every HTTP commissioning phase refuses for it.
_DHCP_CAMPAIGN_MODES = frozenset(
    {"open_episode", "close_episode", "ledger_status", "record_launch", "retire"}
)


def _dhcp_campaign_mode_refusal(campaign: ServerPtCampaign, args) -> str:
    """Name why this mode is not one the DHCP campaign may use, if so."""
    if campaign.campaign_id != DHCP_FASTLOOP_CAMPAIGN.campaign_id:
        return ""
    chosen = [
        name
        for name in (
            "prepare",
            "inspect",
            "qualify",
            "setup",
            "accept",
            "cleanup",
            "record_correction",
            "record_launch",
            "record_exit",
            "retire",
            "import_exit",
            "open_episode",
            "close_episode",
            "ledger_status",
        )
        if getattr(args, name, False)
    ]
    if any(name not in _DHCP_CAMPAIGN_MODES for name in chosen) or not chosen:
        return "mode_not_part_of_the_dhcp_campaign"
    return ""


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
    phase.add_argument("--retire", action="store_true")
    phase.add_argument("--import-exit", action="store_true")
    phase.add_argument("--open-episode", action="store_true")
    phase.add_argument("--close-episode", action="store_true")
    phase.add_argument("--ledger-status", action="store_true")
    parser.add_argument("--campaign", choices=sorted(_CAMPAIGNS), default="c31")
    parser.add_argument("--attempt", default="")
    parser.add_argument("--episode", type=int, default=0)
    parser.add_argument("--clients", type=int, default=30)
    parser.add_argument("--ci-run", type=int, default=0)
    parser.add_argument("--charter", default="")
    parser.add_argument("--first-attempt", default="")
    parser.add_argument("--correction-file", default="")
    parser.add_argument("--launch-evidence", default="")
    parser.add_argument("--close-evidence", default="")
    parser.add_argument("--episode-plan", default="")
    parser.add_argument("--episode-closing", default="")
    parser.add_argument("--addendum", default="")
    parser.add_argument("--import-manifest", default="")
    return parser


def _print(payload: Mapping[str, object]) -> None:
    print(json.dumps(payload, sort_keys=True), flush=True)


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
    campaign = _CAMPAIGNS[args.campaign]
    refusal = _dhcp_campaign_mode_refusal(campaign, args)
    if refusal:
        _print({"outcome": "refused", "reason": refusal})
        return 2
    if args.open_episode or args.close_episode or args.ledger_status:
        return _ledger_mode(root, campaign, args)
    if _ATTEMPT.fullmatch(args.attempt) is None:
        _print({"outcome": "refused", "reason": "invalid_attempt_id"})
        return 2
    if args.clients != 30:
        _print({"outcome": "refused", "reason": "charter_requires_30_clients"})
        return 2
    if args.record_correction:
        if campaign.experimental:
            # A causal correction binds C31's second attempt to its first.
            # An experimental episode states its question when it opens.
            _print({"outcome": "refused", "reason": "correction_is_a_c31_record"})
            return 2
        return _record_correction(
            root, args.attempt, args.first_attempt, args.correction_file
        )
    if args.import_exit:
        if not campaign.experimental:
            _print({"outcome": "refused", "reason": "import_exit_is_experimental_only"})
            return 2
        if args.ci_run:
            _print({"outcome": "refused", "reason": "experimental_ci_claim_refused"})
            return 2
        if not (args.charter and args.addendum and args.import_manifest):
            _print({"outcome": "refused", "reason": "import_exit_inputs_required"})
            return 2
        refusal = _charter_refusal(campaign, args.charter)
        if refusal:
            _print({"outcome": "refused", "reason": refusal})
            return 2
        return _import_exit(
            root, args.attempt, campaign, args.addendum, args.import_manifest
        )
    if (
        args.qualify
        or args.setup
        or args.accept
        or args.cleanup
        or args.record_launch
        or args.record_exit
        or args.retire
    ):
        if args.retire and not campaign.experimental:
            _print({"outcome": "refused", "reason": "retire_is_experimental_only"})
            return 2
        if campaign.experimental:
            if args.ci_run:
                _print(
                    {"outcome": "refused", "reason": "experimental_ci_claim_refused"}
                )
                return 2
            if not args.charter:
                _print({"outcome": "refused", "reason": "charter_required"})
                return 2
            if args.episode < 1 and not (
                args.record_launch or args.record_exit or args.retire
            ):
                _print({"outcome": "refused", "reason": "episode_required"})
                return 2
        elif not args.ci_run or not args.charter:
            _print({"outcome": "refused", "reason": "ci_run_and_charter_required"})
            return 2
        refusal = _charter_refusal(campaign, args.charter)
        if refusal:
            _print({"outcome": "refused", "reason": refusal})
            return 2
        if args.record_launch:
            if not args.launch_evidence:
                _print({"outcome": "refused", "reason": "launch_evidence_required"})
                return 2
            return _record_launch(
                root, args.attempt, args.ci_run, args.launch_evidence, campaign
            )
        if args.record_exit:
            if not args.close_evidence:
                _print({"outcome": "refused", "reason": "close_evidence_required"})
                return 2
            return _record_exit(
                root, args.attempt, args.ci_run, args.close_evidence, campaign
            )
        if args.retire:
            return _retire(root, args.attempt, campaign)
        if args.qualify:
            return _qualify(root, args.attempt, args.ci_run, campaign, args.episode)
        if args.setup:
            return _setup(root, args.attempt, args.ci_run, campaign, args.episode)
        if args.accept:
            return _accept(root, args.attempt, args.ci_run, campaign, args.episode)
        if args.cleanup:
            return _cleanup(root, args.attempt, args.ci_run, campaign, args.episode)
        _print({"outcome": "refused", "reason": "live_phase_not_bound"})
        return 2
    store = ServerPtCommissioningStore(root, campaign.campaign_id)
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


def _charter_refusal(campaign: ServerPtCampaign, charter: str) -> str:
    """Name why the offered charter does not authorize this campaign, if so."""
    try:
        charter_bytes = Path(charter).read_bytes()
    except OSError:
        return "charter_unreadable"
    if len(charter_bytes) > 1024 * 1024 or hashlib.sha256(
        charter_bytes
    ).hexdigest() != _charter_digest(campaign):
        return "charter_digest_mismatch"
    return ""


def _read_ledger_input(name: str) -> dict[str, object]:
    raw = Path(name).read_bytes()
    if len(raw) > _LEDGER_INPUT_LIMIT:
        raise ValueError("ledger input exceeds its budget")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("ledger input is not an object")
    return value


def _ledger_mode(root: Path, campaign: ServerPtCampaign, args) -> int:
    """Open, close or report one experimental episode; nothing contacts PT."""
    if not campaign.experimental:
        _print({"outcome": "refused", "reason": "ledger_is_experimental_only"})
        return 2
    refusal = _charter_refusal(campaign, args.charter) if args.charter else ""
    if not args.ledger_status and (not args.charter or refusal):
        _print({"outcome": "refused", "reason": refusal or "charter_required"})
        return 2
    store = ServerPtCommissioningStore(root, campaign.campaign_id)
    try:
        if _adopt_ledger_residue(store, campaign):
            raise ValueError("campaign archive is unverified")
        records = store.ledger_records()
        now = datetime.now(UTC)
        if args.ledger_status:
            totals = ledger_totals(records, allowance_for(campaign.campaign_id), now)
            _print({"outcome": "ready", "ledger": asdict(totals)})
            return 0
        if args.open_episode:
            plan = _read_ledger_input(args.episode_plan)
            source = repository_identity(root)
            if (
                source_authority_findings(campaign, source, None)
                or source.branch != FEATURE_BRANCH
            ):
                raise ValueError("episode source is not a clean committed checkpoint")
            episodes = [
                value
                for value in records.values()
                if value.get("kind") == "episode_opening"
            ]
            opening = {
                **plan,
                "kind": "episode_opening",
                "episode": len(episodes) + 1,
                "campaign_id": campaign.campaign_id,
                "charter_sha256": _charter_digest(campaign),
                "execution_purpose": campaign.purpose.value,
                "source_sha": source.head,
                "source_tree": source.tree,
                "source_upstream_head": source.upstream_head,
                "opened_at_utc": now.isoformat(),
            }
            findings = opening_findings(
                records, opening, allowance_for(campaign.campaign_id), now
            )
            if findings:
                _print({"outcome": "refused", "reasons": list(findings)})
                return 2
            name = episode_name(int(opening["episode"])) + "-opening"
            path = store.save_ledger_record(name, opening)
        else:
            closing_input = _read_ledger_input(args.episode_closing)
            findings = closing_findings(records, args.episode, now)
            if findings:
                _print({"outcome": "refused", "reasons": list(findings)})
                return 2
            closing = {
                **closing_input,
                "kind": "episode_closing",
                "episode": args.episode,
                "unsettled_phases": list(unsettled_phases(records, args.episode)),
                "closed_at_utc": now.isoformat(),
            }
            path = store.save_ledger_record(
                episode_name(args.episode) + "-closing", closing
            )
        store.refresh_index()
        if store.verify_index():
            raise ValueError("ledger archive is unverified")
        totals = ledger_totals(
            store.ledger_records(), allowance_for(campaign.campaign_id), now
        )
    except (OSError, ValueError) as exc:
        _print({"outcome": "refused", "reason": f"ledger:{type(exc).__name__}"})
        return 2
    _print(
        {
            "outcome": "recorded",
            "record_path": str(path),
            "record_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "ledger": asdict(totals),
        }
    )
    return 0


def _adopt_ledger_residue(
    store: ServerPtCommissioningStore, campaign: ServerPtCampaign
) -> tuple[str, ...]:
    """Index ledger records a hard stop left unindexed; nothing else."""
    if not campaign.experimental or not store.index_exists():
        return ()
    try:
        return store.adopt_ledger_residue(ledger_record_findings)
    except (OSError, ValueError) as exc:
        return (f"ledger_residue_unverified:{type(exc).__name__}",)


def _admit_phase(
    store: ServerPtCommissioningStore,
    campaign: ServerPtCampaign,
    episode: int,
    attempt_id: str,
    phase: str,
    preflight,
) -> tuple[str, ...]:
    """Admit a preliminary phase against its episode before any contact."""
    if not campaign.experimental:
        return ()
    try:
        planned = derive_server_pt_phase_grant(
            phase,
            attempt_id,
            preflight.source,
            preflight.process,
            preflight.ci,
            campaign=campaign,
        )
    except ValueError:
        return ("phase_grant_underivable",)
    return _ledger_admit(
        store,
        campaign,
        episode,
        attempt_id,
        phase,
        planned.max_operations,
        planned.max_seconds,
        source=preflight.source,
    )


def _settle_phase(
    store: ServerPtCommissioningStore,
    campaign: ServerPtCampaign,
    episode: int,
    attempt_id: str,
    phase: str,
    status: dict[str, object],
    active_seconds: float,
) -> None:
    """Record one experimental phase's use in the ledger and in its status."""
    if not campaign.experimental:
        return
    status["execution_purpose"] = campaign.purpose.value
    status["ledger_result"] = (
        _ledger_result(
            store,
            campaign,
            episode,
            attempt_id,
            phase,
            int(status.get("operations_used") or 0),
            active_seconds,
            str(status.get("outcome") or ""),
        )
        or "recorded"
    )


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
    root: Path,
    attempt_id: str,
    ci_run_id: int,
    evidence_file: str,
    campaign: ServerPtCampaign = C31_CAMPAIGN,
) -> int:
    """Pin a campaign-created disposable PT process before qualification."""
    store = ServerPtCommissioningStore(root, campaign.campaign_id)
    preflight = phase_preflight(root, ci_run_id=ci_run_id, campaign=campaign)
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
        observed: dict[str, object] = {}
        if campaign.experimental:
            # The command line and title that later bound a retirement are
            # read from the operating system here, never taken from the
            # capture; a capture that disagrees with them is refused.
            control = _PROCESS_CONTROL()
            reading = control.observe(preflight.process.process_id)
            if (
                reading.error
                or not reading.present
                or reading.process_path != preflight.process.process_path
                or reading.process_incarnation != preflight.process.process_incarnation
                or launch.get("command_line") != reading.command_line
                or launch.get("main_window_title") != reading.main_window_title
            ):
                raise ValueError("launch capture differs from the observed process")
            observed = {
                "observed_command_line": reading.command_line,
                "observed_main_window_title": reading.main_window_title,
                # The build the OS reported for this image; retirement
                # identifies the document window by this build's signature.
                "observed_product_version": preflight.process.product_version,
                "observed_file_version": preflight.process.file_version,
                # Auxiliary: the windows the process showed at launch. It
                # authorizes nothing; retirement takes its own census.
                "observed_window_census": _census_record(
                    control.windows(preflight.process.process_id)
                ),
            }
        document = {
            **launch,
            "capture_sha256": hashlib.sha256(raw).hexdigest(),
            "capture_text": raw.decode("utf-8"),
            "campaign_id": campaign.campaign_id,
            "charter_sha256": _charter_digest(campaign),
            "execution_purpose": campaign.purpose.value,
            "source_sha": preflight.source.head if preflight.source else "",
            "source_tree": preflight.source.tree if preflight.source else "",
            "ci_run_id": preflight.ci.run_id if preflight.ci else 0,
            **observed,
        }
        path = store.save_process_launch(attempt_id, document)
        status = {
            "phase": "launch",
            "outcome": "owned",
            "attempt_id": attempt_id,
            "process_id": preflight.process.process_id,
            "launch_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        if campaign.experimental:
            status["blank_document_proven"] = launched_blank(document)
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
    root: Path,
    attempt_id: str,
    ci_run_id: int,
    evidence_file: str,
    campaign: ServerPtCampaign = C31_CAMPAIGN,
) -> int:
    """Record the owned PT's close only after an OS census proves it exited.

    Delivery accepts only a graceful close. An experimental campaign also
    accepts a recorded exact-process termination after a bounded graceful
    attempt; it is kept as `_forced`, never relabelled graceful.
    """
    store = ServerPtCommissioningStore(root, campaign.campaign_id)
    try:
        try:
            store.require_archived_phase(attempt_id, "cleanup", "restored")
            disposition = "exited"
        except ValueError:
            if campaign.experimental and attempt_id not in store.setup_attempt_ids():
                # This attempt deployed no campus of its own. Whatever an
                # earlier preliminary phase left is in its own archived
                # record; the disposition claims nothing about the workspace.
                disposition = "exited_before_setup"
            else:
                store.require_archived_phase(attempt_id, "setup", "stopped")
                if store.cleanup_started(attempt_id):
                    raise ValueError(
                        "dirty retirement conflicts with cleanup"
                    ) from None
                disposition = "exited_dirty"
        launch = store.load_process_launch(attempt_id)
        # Delivery binds retirement to the setup grant, as before. An
        # experimental attempt may stop before any grant exists, so it binds
        # to the checkpoint its launch record pinned.
        source = repository_identity(root)
        if campaign.experimental:
            bound_source = (launch.get("source_sha"), launch.get("source_tree"))
            unusable = bool(source_authority_findings(campaign, source, None))
        else:
            setup_grant = store.load_phase_grant(attempt_id, "setup")
            bound_source = (setup_grant.source_sha, setup_grant.source_tree)
            unusable = bool(
                source.error
                or source.clean is not True
                or source.upstream_head != source.head
            )
        if unusable or (source.head, source.tree) != bound_source:
            raise ValueError("retirement source differs from setup")
        ci = None
        if not campaign.experimental:
            ci, findings = read_exact_ci(ci_run_id, source.head, checkout=root)
            if findings or ci is None:
                raise ValueError("retirement exact-SHA CI is unobservable")
        raw = Path(evidence_file).read_bytes()
        if len(raw) > 16 * 1024:
            raise ValueError("graceful close capture exceeds input budget")
        close = json.loads(raw)
        if not isinstance(close, dict):
            raise ValueError("graceful close capture is not an object")
        if close.get("method") == "WM_CLOSE":
            # Only `--retire` posts a targeted close, and it records its own
            # observed exit; a capture cannot claim one.
            raise ValueError("a targeted close is recorded only by --retire")
        observed = PowerShellPacketTracerProcessReader(timeout_seconds=10).read()
        if observed.error:
            raise ValueError("process exit census is unreadable")
        findings = exit_evidence_findings(
            launch,
            close,
            process_count=len(observed.processes),
            # A capture never carries a force; only `--retire` observes and
            # performs one, and it records its own evidence.
            allow_forced=False,
        )
        if findings:
            raise ValueError("graceful process exit is unverified")
        if exit_was_forced(close):
            disposition += "_forced"
        document = {
            **close,
            "disposition": disposition,
            "close_capture_sha256": hashlib.sha256(raw).hexdigest(),
            "close_capture_text": raw.decode("utf-8"),
            "observed_at_utc": datetime.now(UTC).isoformat(),
            "process_count": len(observed.processes),
            "source_sha": source.head,
            "source_tree": source.tree,
            "ci_run_id": ci.run_id if ci is not None else 0,
            "campaign_id": campaign.campaign_id,
            "charter_sha256": _charter_digest(campaign),
            "execution_purpose": campaign.purpose.value,
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


def _retirement_basis(
    store: ServerPtCommissioningStore, attempt_id: str
) -> tuple[str, str]:
    """Return the disposition and the durable workspace-ownership basis.

    Every basis rests on the campaign's own indexed records: a restored owned
    cleanup; an empty disposable baseline observed before any campaign
    effect; or, before setup, the blank launch with any preliminary phase
    archived. Anything else raises: ownership is then not established, and
    no force may follow. Retiring the process never proves restoration.
    """
    try:
        store.require_immutable_phase(attempt_id, "cleanup", "restored")
        return "exited", "owned_cleanup_restored"
    except (OSError, ValueError):
        pass
    qualification = _qualification_basis(store, attempt_id)
    if qualification is not None:
        return qualification
    if attempt_id not in store.setup_attempt_ids():
        try:
            status = store.load_phase_status(attempt_id, "prequalification")
        except (OSError, ValueError):
            if store.record_path_for(attempt_id, "prequalification-grant").exists():
                return "exited_before_setup", "blank_launch_interrupted_preliminary"
            return "exited_before_setup", "blank_launch_without_phase"
        store.require_immutable_phase(
            attempt_id, "prequalification", str(status.get("outcome"))
        )
        return "exited_before_setup", "blank_launch_archived_preliminary"
    if disposable_workspace_error(store.load_baseline(attempt_id)):
        raise ValueError("setup baseline is not an empty disposable workspace")
    try:
        setup = store.load_phase_status(attempt_id, "setup")
    except (OSError, ValueError):
        return "exited_interrupted", "empty_baseline_before_interrupted_setup"
    store.require_immutable_phase(attempt_id, "setup", str(setup.get("outcome")))
    return "exited_dirty", "empty_baseline_then_campaign_effects"


#: The outcomes a completed qualification use case archives.
_QUALIFICATION_OUTCOMES = frozenset({"completed", "stopped", "refused"})


def _qualification_basis(
    store: ServerPtCommissioningStore, attempt_id: str
) -> tuple[str, str] | None:
    """Return the basis an archived qualification run establishes, if any.

    A qualification attempt runs in a laboratory the campaign launched blank.
    Its own admission read an empty disposable workspace before its first
    effect, and its record says whether owned cleanup restored it. A ledger
    admission without an archived status means the run may have had effects
    whose state is unknown: the ownership still rests on the blank launch,
    and the disposition says the qualification was interrupted. `None` means
    this attempt never admitted a qualification, so the existing bases apply.
    """
    try:
        status = store.load_phase_status(attempt_id, "qualification")
    except (OSError, ValueError):
        records = store.ledger_records()
        if qualification_settled(records, attempt_id):
            # A recorded result with no archived status is a crash between
            # the two writes: the run was not interrupted, and nothing that
            # survived says its workspace stayed disposable.
            raise ValueError("settled qualification has no archived status") from None
        if qualification_admitted(records, attempt_id):
            return "exited_interrupted", "blank_launch_then_interrupted_qualification"
        return None
    store.require_immutable_phase(
        attempt_id, "qualification", str(status.get("outcome"))
    )
    outcome = status.get("outcome")
    effects = status.get("effects_dispatched")
    if outcome == "interrupted":
        # Effects of unknown state. The ownership still rests on the blank
        # launch, which `--retire` rechecks, and only if the ledger agrees
        # that no result was ever recorded for this qualification.
        records = store.ledger_records()
        if (
            effects is not None
            or status.get("restoration_proven") is not False
            or not qualification_admitted(records, attempt_id)
            or qualification_settled(records, attempt_id)
        ):
            raise ValueError("interrupted qualification status is incoherent")
        return "exited_interrupted", "blank_launch_then_interrupted_qualification"
    # Every other status is a completed use-case result: its outcome is one
    # the use case returns and each fact it carries is an actual boolean.
    # Anything else is not evidence of a disposable workspace.
    facts = (
        effects,
        status.get("workspace_baseline_observed"),
        status.get("workspace_baseline_empty"),
        status.get("restoration_proven"),
    )
    if outcome not in _QUALIFICATION_OUTCOMES or any(
        not isinstance(item, bool) for item in facts
    ):
        raise ValueError("qualification status is incoherent")
    if effects is False:
        # Nothing was dispatched, but a baseline this run observed must
        # still have been the empty disposable one: a blank launch that
        # later showed foreign devices is not the campaign's to close.
        if status.get("workspace_baseline_observed") is not False and (
            status.get("workspace_baseline_empty") is not True
        ):
            raise ValueError("qualification observed a non-disposable workspace")
        return "exited_before_setup", "blank_launch_without_qualification_effects"
    if status.get("workspace_baseline_empty") is not True:
        raise ValueError("qualification baseline was not an empty disposable workspace")
    if status.get("restoration_proven") is True:
        return "exited", "owned_qualification_restored"
    return "exited_dirty", "empty_baseline_then_qualification_effects"


def _instant() -> tuple[str, float]:
    """One UTC wall-clock instant and the monotonic reading taken with it."""
    return datetime.now(UTC).isoformat(), round(time.monotonic(), 6)


def _timed_reading(control, pid: int, readings: list[dict[str, object]]):
    """Observe one PID and keep the reading with its request and answer times."""
    started, started_monotonic = _instant()
    reading = control.observe(pid)
    answered, answered_monotonic = _instant()
    readings.append(
        {
            "started_at_utc": started,
            "answered_at_utc": answered,
            "started_monotonic_s": started_monotonic,
            "answered_monotonic_s": answered_monotonic,
            "present": None if reading.error else reading.present,
            "error": reading.error,
        }
    )
    return reading


def _await_absence(
    control, pid: int, seconds: float, readings: list[dict[str, object]]
) -> bool:
    """Poll one PID until the OS reports it absent, within a bounded wait.

    Every reading is appended to `readings`, so an exit is bounded by what
    was observed rather than by the limits of the wait.
    """
    deadline = time.monotonic() + seconds
    while True:
        reading = _timed_reading(control, pid, readings)
        if not reading.error and not reading.present:
            return True
        if time.monotonic() >= deadline:
            return False
        _retirement_sleep(_RETIREMENT_POLL_SECONDS)


def _wall_clock_continuous(instants: list[tuple[str, float]]) -> bool:
    """Whether wall time advanced like monotonic time between each instant."""
    for (wall_a, mono_a), (wall_b, mono_b) in pairwise(instants):
        wall = (
            datetime.fromisoformat(wall_b) - datetime.fromisoformat(wall_a)
        ).total_seconds()
        if abs(wall - (mono_b - mono_a)) > _CLOCK_TOLERANCE_SECONDS:
            return False
    return True


def _await_no_packet_tracer(
    control,
    launch: Mapping[str, object],
    start_ticks: int,
    seconds: float,
    readings: list[dict[str, object]],
) -> tuple[int | None, tuple[str, ...]]:
    """List Packet Tracer processes until none remains, within a bounded wait.

    Only the launched process and its own helpers are waited out. A process
    the campaign did not start stops the wait at once and is returned as a
    finding. Every census is appended to `readings` with its times and rows.
    Returns the last count (`None` if unreadable) and the findings.
    """
    deadline = time.monotonic() + seconds
    while True:
        started, started_monotonic = _instant()
        census = control.packet_tracer_processes()
        answered, answered_monotonic = _instant()
        count = None if census.error else len(census.processes)
        findings = (
            ()
            if census.error
            else lingering_process_findings(launch, start_ticks, census.processes)
        )
        readings.append(
            {
                "started_at_utc": started,
                "answered_at_utc": answered,
                "started_monotonic_s": started_monotonic,
                "answered_monotonic_s": answered_monotonic,
                "count": count,
                "error": census.error,
                "processes": [
                    {
                        "process_id": row.process_id,
                        "parent_process_id": row.parent_process_id,
                        "start_ticks": row.start_ticks,
                        "executable_path": row.executable_path,
                        "command_line": row.command_line,
                        "role": packet_tracer_process_role(launch, start_ticks, row),
                    }
                    for row in census.processes
                ],
                "findings": list(findings),
            }
        )
        if findings or count == 0 or time.monotonic() >= deadline:
            return count, findings
        _retirement_sleep(_RETIREMENT_POLL_SECONDS)


def _exit_bounds(
    alive: tuple[str, float], readings: list[dict[str, object]]
) -> dict[str, str]:
    """Bound an exit by raw readings, or return nothing if none saw it.

    The exit came after the start of the last reading that found the process
    present (or `alive`, when an effect's own recheck found it alive) and
    before the answer of the first reading that found it absent. If the wall
    clock stepped between those instants, no bound is claimed.
    """
    after = alive[0]
    instants = [alive]
    for reading in readings:
        instants += [
            (str(reading["started_at_utc"]), float(reading["started_monotonic_s"])),
            (str(reading["answered_at_utc"]), float(reading["answered_monotonic_s"])),
        ]
        if reading["present"] is True:
            after = str(reading["started_at_utc"])
        elif reading["present"] is False:
            if not _wall_clock_continuous(instants):
                return {"unavailable": "wall_clock_discontinuous"}
            return {"after_utc": after, "before_utc": str(reading["answered_at_utc"])}
    return {}


def _mailbox_state() -> dict[str, object]:
    """Count pending mailbox requests and responses without contacting PT."""
    try:
        directory = Path(_MAILBOX_DIR())
        pending = (
            sum(
                1
                for pattern in ("req_*", "res_*")
                for path in directory.glob(pattern)
                if path.is_file()
            )
            if directory.exists()
            else 0
        )
    except OSError as exc:
        return {
            "pending_count": None,
            "error": f"mailbox_unreadable:{type(exc).__name__}",
        }
    return {"pending_count": pending, "error": ""}


def _window_record(window: object) -> dict[str, object]:
    """One observed window as evidence; auxiliary, never an identity."""
    return {
        "handle": window.handle,
        "owner_pid": window.owner_pid,
        "class_name": window.class_name,
        "title": window.title,
        "visible": window.visible,
        "enabled": window.enabled,
        "owner_handle": window.owner_handle,
        "identity_digest": window.identity_digest,
    }


def _census_record(census: object) -> dict[str, object]:
    """One window census as evidence, including its completeness or error."""
    return {
        "process_id": census.process_id,
        "complete": census.complete,
        "error": census.error,
        "windows": [_window_record(window) for window in census.windows],
    }


def _record_retirement_attempt(
    store: ServerPtCommissioningStore,
    attempt_id: str,
    campaign: ServerPtCampaign,
    attempt: dict[str, object],
) -> int:
    """Keep one retirement that ended without an admitted exit, and refuse."""
    attempt = {
        **attempt,
        "campaign_id": campaign.campaign_id,
        "execution_purpose": campaign.purpose.value,
    }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    try:
        store.save_retirement_attempt(attempt_id, stamp, attempt)
        store.refresh_index()
    except (OSError, ValueError) as exc:
        attempt["attempt_unrecorded"] = type(exc).__name__
    _print({"outcome": "refused", **attempt})
    return 2


def _retire(root: Path, attempt_id: str, campaign: ServerPtCampaign) -> int:
    """Retire the campaign-launched disposable Packet Tracer of one attempt.

    The owned PID's identity (image, creation time, command line) is read
    fresh, its top-level windows are enumerated, and exactly one document
    window is selected by the signature of the build the launch observed
    (`select_document_window`); a dialog, an unclassified window or any other
    doubt sends nothing. After the identity is read again, one revalidated
    `WM_CLOSE` goes to that handle, never to the extension log window and
    never broadcast. Every absence reading is kept with its times. Only if
    the process is still present after the bounded wait, the identity still
    matches, a second complete census shows the same document window and
    nothing modal or unclassified, and the workspace-ownership basis is
    established from indexed records, is that exact PID terminated. An
    already absent process is neither closed nor killed. Every refusal is
    recorded as an attempt, with the signature and mailbox state it saw.
    """
    store = ServerPtCommissioningStore(root, campaign.campaign_id)
    if _adopt_ledger_residue(store, campaign):
        _print({"outcome": "refused", "reason": "prior_archive_unverified"})
        return 2
    try:
        launch = store.load_process_launch(attempt_id)
        if launch.get("execution_purpose") != campaign.purpose.value:
            raise ValueError("launch was not recorded by this campaign")
        disposition, basis = _retirement_basis(store, attempt_id)
        source = repository_identity(root)
        if source_authority_findings(campaign, source, None) or (
            source.head,
            source.tree,
        ) != (launch.get("source_sha"), launch.get("source_tree")):
            raise ValueError("retirement source differs from the launch")
        pid = launch["pid"]
        if isinstance(pid, bool) or not isinstance(pid, int):
            raise ValueError("launch PID is malformed")
        # Every census, close and termination is bound to this creation time.
        start_ticks = incarnation_ticks(launch.get("process_incarnation"))
        if start_ticks is None:
            raise ValueError("launch creation time is unreadable")
    except (OSError, ValueError, KeyError) as exc:
        _print(
            {
                "outcome": "refused",
                "reason": f"retirement_unestablished:{type(exc).__name__}",
            }
        )
        return 2
    isolation = _RETIREMENT_ISOLATION(root).ensure_isolated()
    if not isolation.isolated:
        # Nothing is observed or sent from a process that is not isolated.
        _print(
            {
                "outcome": "refused",
                "reason": "import_isolation_unverified:" + isolation.state.value,
            }
        )
        return 2
    # The document is identified by the launched build's signature. Without
    # one the census is still taken and kept, and nothing is selected.
    signature = window_signature_for_launch(launch)
    control = _PROCESS_CONTROL()
    identity = {
        "pid": pid,
        "process_path": launch.get("process_path"),
        "process_incarnation": launch.get("process_incarnation"),
        "ownership_basis": basis,
        "window_signature": (
            window_signature_record(signature) if signature is not None else None
        ),
    }
    reading = control.observe(pid)
    refusal = observed_process_findings(launch, reading)
    if refusal:
        # Already absent, unreadable or another process: nothing is sent.
        return _record_retirement_attempt(
            store,
            attempt_id,
            campaign,
            {
                **identity,
                "requested": False,
                "refusal": list(refusal),
                "observed_at_utc": datetime.now(UTC).isoformat(),
            },
        )
    before = control.windows(pid)
    target, refusal = select_document_window(
        pid, before, signature=signature, start_ticks=start_ticks
    )
    if not refusal:
        refusal = observed_process_findings(launch, control.observe(pid))
    mailbox_before = _mailbox_state()
    if refusal or target is None:
        return _record_retirement_attempt(
            store,
            attempt_id,
            campaign,
            {
                **identity,
                "requested": False,
                "refusal": list(refusal),
                "window_census_before": _census_record(before),
                "mailbox_before_close": mailbox_before,
                "observed_at_utc": datetime.now(UTC).isoformat(),
            },
        )
    readings: list[dict[str, object]] = []
    requested = _instant()
    requested_at = requested[0]
    # The helper posts only while the process and its visible windows are
    # still exactly what this census saw.
    sent = control.close_window(
        pid,
        target.handle,
        target.identity_digest,
        set_digest=before.visible_set_digest,
        start_ticks=before.process_start_ticks,
    )
    close: dict[str, object] = {
        **identity,
        "method": "WM_CLOSE",
        "close_target": _window_record(target),
        "requested": sent.sent,
        "requested_at_utc": requested_at,
        "close_refusal": sent.refusal,
        "close_error": sent.error,
        "window_census_before": _census_record(before),
        "mailbox_before_close": mailbox_before,
        "graceful_wait_seconds": RETIREMENT_GRACE_SECONDS,
        "absence_observations": readings,
    }
    if not sent.sent and not sent.error:
        # The helper refused before posting: nothing was sent, nothing forced.
        return _record_retirement_attempt(
            store,
            attempt_id,
            campaign,
            {
                **close,
                "refusal": [f"close_not_sent:{sent.refusal}"],
                "observed_at_utc": datetime.now(UTC).isoformat(),
            },
        )
    # A helper error leaves the close's outcome unknown: absence is still
    # observed, but an unknown request never authorizes a force.
    exited = _await_absence(control, pid, RETIREMENT_GRACE_SECONDS, readings)
    forced: dict[str, object] | None = None
    kill_readings: list[dict[str, object]] = []
    refusal = () if sent.sent else ("close_outcome_unknown",)
    if not exited and not refusal:
        again = _timed_reading(control, pid, readings)
        if not again.error and not again.present:
            exited = True
        elif not campaign.forced_retirement_authorized:
            # The charter never authorized a force: the laboratory stays open
            # and its ownership stays recorded as unresolved.
            refusal = ("forced_retirement_not_authorized_by_campaign",)
        else:
            refusal = observed_process_findings(launch, again)
            after = control.windows(pid) if not refusal else None
            if after is not None:
                close["window_census_after"] = _census_record(after)
                refusal = force_window_findings(
                    pid, target, after, signature=signature, start_ticks=start_ticks
                )
            if not refusal:
                forced = {
                    "method": "Process.Kill",
                    "pid": pid,
                    "rechecked_process_path": again.process_path,
                    "rechecked_process_incarnation": again.process_incarnation,
                    "rechecked_command_line": again.command_line,
                    "rechecked_document_window": _window_record(
                        next(
                            window
                            for window in after.windows
                            if window.handle == target.handle
                        )
                    ),
                    "window_census_complete": after.complete,
                    "modal_windows_visible": any(
                        window.visible and window.owner_handle
                        for window in after.windows
                    ),
                    "bound_process_start_ticks": after.process_start_ticks,
                    "bound_window_set_digest": after.visible_set_digest,
                    "disposable_workspace_rechecked": True,
                    "ownership_basis": basis,
                }
                kill_requested = _instant()
                forced["requested_at_utc"] = kill_requested[0]
                # The helper kills only the census's process, and only while
                # its visible windows are still the census's set.
                killed = control.terminate(
                    pid,
                    set_digest=after.visible_set_digest,
                    start_ticks=after.process_start_ticks,
                )
                forced["termination"] = {
                    "sent": killed.sent,
                    "refusal": killed.refusal,
                    "error": killed.error,
                }
                forced["absence_observations"] = kill_readings
                if killed.sent or killed.error:
                    # An unanswered helper may have acted: observe, never retry.
                    exited = _await_absence(
                        control, pid, RETIREMENT_EXIT_WAIT_SECONDS, kill_readings
                    )
                else:
                    refusal = (f"termination_not_sent:{killed.refusal}",)
    # The owned process's helpers may outlive it by seconds; they are given a
    # bounded wait, and only an exit of the owned process earns one.
    census_readings: list[dict[str, object]] = []
    count, foreign = _await_no_packet_tracer(
        control,
        launch,
        start_ticks,
        RETIREMENT_HELPER_WAIT_SECONDS if exited else 0.0,
        census_readings,
    )
    # A process the campaign did not start is never waited out or ignored.
    refusal = (*refusal, *foreign)
    close.update(
        {
            "actual_exit_observed": exited,
            "process_count": count,
            "process_census_readings": census_readings,
            "mailbox_after_exit": _mailbox_state(),
            "observed_at_utc": datetime.now(UTC).isoformat(),
        }
    )
    # Each effect's own recheck found the process alive when it was issued.
    if forced is not None and forced["termination"]["sent"]:
        close["exit_bounds"] = _exit_bounds(kill_requested, kill_readings)
    elif sent.sent:
        close["exit_bounds"] = _exit_bounds(requested, readings)
    if forced is not None:
        close["forced_termination"] = forced
        if not forced["termination"]["sent"]:
            # No confirmed kill: an observed exit is not a forced exit.
            refusal = (*refusal, "termination_unconfirmed")
    findings = exit_evidence_findings(
        launch, close, process_count=count, allow_forced=True
    )
    if refusal or findings:
        return _record_retirement_attempt(
            store,
            attempt_id,
            campaign,
            {**close, "refusal": list(refusal), "findings": list(findings)},
        )
    if forced is not None:
        disposition += "_forced"
    document = {
        **close,
        "disposition": disposition,
        "source_sha": source.head,
        "source_tree": source.tree,
        "ci_run_id": 0,
        "campaign_id": campaign.campaign_id,
        "charter_sha256": _charter_digest(campaign),
        "execution_purpose": campaign.purpose.value,
    }
    try:
        path = store.save_process_exit(attempt_id, document)
        status = {
            "phase": "retirement",
            "outcome": disposition,
            "attempt_id": attempt_id,
            "process_id": pid,
            "ownership_basis": basis,
            "exit_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        if _refresh_archive(store, status):
            raise ValueError("process exit archive is unverified")
    except (OSError, ValueError) as exc:
        _print({"outcome": "refused", "reason": f"process_exit:{type(exc).__name__}"})
        return 2
    _print(status)
    return 0


def _read_bounded(path: object, limit: int) -> bytes:
    """Read one named local file whole, refusing anything over its budget."""
    if not isinstance(path, str) or not path:
        raise ValueError("input path is missing")
    raw = Path(path).read_bytes()
    if len(raw) > limit:
        raise ValueError("input exceeds its byte budget")
    return raw


def _transcript_source(meta: Mapping[str, object], excerpt: bytes) -> dict[str, object]:
    """Prove each excerpt line equals the named line of its source file."""
    numbers = meta.get("source_lines")
    raw = _read_bounded(meta.get("source_path"), _IMPORT_TRANSCRIPT_LIMIT)
    source = raw.split(b"\n")
    lines = excerpt_lines(excerpt)
    if (
        not isinstance(numbers, list)
        or len(numbers) != len(lines)
        or any(
            isinstance(number, bool)
            or not isinstance(number, int)
            or not 1 <= number <= len(source)
            or source[number - 1] != line
            for number, line in zip(numbers, lines, strict=False)
        )
    ):
        raise ValueError("transcript excerpt differs from its source lines")
    return {
        "path": meta.get("source_path"),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "lines_verified": list(numbers),
    }


def _fresh_state(pid: int) -> dict[str, object]:
    """Census and mailbox now, without contacting Packet Tracer.

    Only the count of primary Packet Tracer processes (the reader validates
    and collapses each progress helper into its primary) and whether the
    owned PID is among them are kept; another process's path or command line
    is not.
    """
    observed = PowerShellPacketTracerProcessReader(timeout_seconds=10).read()
    if observed.error:
        raise ValueError("fresh process census is unreadable")
    mailbox = _mailbox_state()
    return {
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "packet_tracer_primary_process_count": len(observed.processes),
        "owned_pid_present": any(item.pid == pid for item in observed.processes),
        "mailbox_pending_count": mailbox["pending_count"] or 0,
        "mailbox_error": mailbox["error"],
        "packet_tracer_contacted": False,
    }


def _import_paths(campaign_id: str, attempt_id: str) -> tuple[str, dict[str, str]]:
    """Return the canonical archive paths of the addendum and each artifact."""
    base = f"data/commissioning/{campaign_id}"
    return f"{base}/authority/addendum-02.md", {
        role: f"{base}/{attempt_id}/exit-import-{role.replace('_', '-')}{suffix}"
        for role, suffix in _IMPORT_SUFFIXES.items()
    }


def _import_residue(
    store: ServerPtCommissioningStore, attempt_id: str
) -> frozenset[str]:
    """Name this import's own unindexed files; anything else is refused.

    An import stopped between its writes leaves files the index does not
    list. Only the files this import writes, with the snapshot of exactly the
    current index, may be tolerated; everything indexed must still verify.
    """
    residue = store.archive_residue()
    if residue is None:
        raise ValueError("campaign archive is unverified")
    base = f"data/commissioning/{store.campaign_id}"
    addendum, artifacts = _import_paths(store.campaign_id, attempt_id)
    own = {
        addendum,
        store.index_predecessor()["path"],
        f"{base}/{attempt_id}/exit-import.json",
        f"{base}/{attempt_id}/exit-import.sha256",
        f"{base}/{attempt_id}/exit-import-completion.json",
        f"{base}/{attempt_id}/exit-import-completion.sha256",
        *artifacts.values(),
    }
    if not set(residue) <= own:
        raise ValueError("archive residue is not this import's")
    return frozenset(residue)


def _import_document(
    *,
    campaign: ServerPtCampaign,
    attempt_id: str,
    manifest: Mapping[str, object],
    artifacts: Mapping[str, bytes],
    launch: Mapping[str, object],
    launch_sha256: str,
    cleanup_status_sha256: str,
    cleanup_result: Mapping[str, object],
    episode_tree: str,
    recorder: Mapping[str, object],
    transcript: Mapping[str, object],
    fresh: Mapping[str, object],
    predecessor: Mapping[str, object],
    archive_at: str,
) -> dict[str, object]:
    """Assemble the one record an admitted import writes, from its inputs.

    Both a first run and the completion of an interrupted one build the
    record here, so a stored record can be compared with its rebuild byte for
    byte.
    """
    authority = _EXIT_IMPORT_AUTHORITY
    addendum_path, artifact_paths = _import_paths(campaign.campaign_id, attempt_id)
    offered = manifest["artifacts"]
    return {
        "kind": "historical_exit_import",
        "campaign_id": campaign.campaign_id,
        "charter_sha256": _charter_digest(campaign),
        "execution_purpose": campaign.purpose.value,
        "attempt_id": attempt_id,
        "episode": authority.episode,
        "authority": {
            "addendum_sha256": authority.addendum_sha256,
            "addendum_path": addendum_path,
        },
        "episode_source": {
            "sha": authority.episode_source_sha,
            "tree": episode_tree,
            "ancestor_of_recorder": True,
        },
        "recorder_source": dict(recorder),
        "launch_sha256": launch_sha256,
        "cleanup_status_sha256": cleanup_status_sha256,
        "cleanup_outcome": "restored",
        "cleanup_recorded_at_utc": cleanup_result.get("recorded_at_utc"),
        "process": {
            "pid": launch.get("pid"),
            "process_path": launch.get("process_path"),
            "process_incarnation": launch.get("process_incarnation"),
        },
        "artifacts": [
            {
                "role": role,
                "file": artifact_paths[role],
                "sha256": hashlib.sha256(artifacts[role]).hexdigest(),
                "bytes": len(artifacts[role]),
                "original_path": offered[role]["path"],
                "origin": offered[role].get("origin", ""),
            }
            for role in sorted(artifacts)
        ],
        "transcript_source": dict(transcript),
        "capture_field_provenance": manifest.get("capture_field_provenance"),
        "time_bounds": manifest.get("time_bounds"),
        "retire_refusal": manifest.get("retire_refusal"),
        "close_request_command": manifest.get("close_request_command"),
        "absence_command": manifest.get("absence_command"),
        "retained_command_range": manifest.get("retained_command_range"),
        "lead_report": manifest.get("lead_report", ""),
        "fresh_state": dict(fresh),
        **historical_exit_claim(manifest),
        "index_predecessor": dict(predecessor),
        "archived_at_utc": archive_at,
        "limitations": list(_IMPORT_LIMITATIONS),
    }


_FRESH_STATE_KEYS = frozenset(
    {
        "observed_at_utc",
        "packet_tracer_primary_process_count",
        "owned_pid_present",
        "mailbox_pending_count",
        "mailbox_error",
        "packet_tracer_contacted",
    }
)


def _earlier_observations(
    root: Path, record: Mapping[str, object]
) -> tuple[dict[str, object], dict[str, object], str]:
    """Return what an interrupted run stated and cannot be derived again.

    Its recorder must have been a clean descendant of the episode source,
    and its archive time must not lie in the future. Its census must be
    well formed and taken between its archive time and now; it is carried
    as that run reported it, never as this run's observation, and the
    completion takes and records its own census. Everything else in the
    record is rebuilt and compared.
    """
    authority = _EXIT_IMPORT_AUTHORITY
    recorder = record.get("recorder_source")
    fresh = record.get("fresh_state")
    archive_at = record.get("archived_at_utc")
    now = datetime.now(UTC)

    def count(value: object) -> bool:
        return not isinstance(value, bool) and isinstance(value, int) and value >= 0

    if (
        not isinstance(recorder, dict)
        or recorder.get("clean") is not True
        or not isinstance(fresh, dict)
        or set(fresh) != _FRESH_STATE_KEYS
        or fresh.get("owned_pid_present") is not False
        or fresh.get("packet_tracer_contacted") is not False
        or not count(fresh.get("packet_tracer_primary_process_count"))
        or not count(fresh.get("mailbox_pending_count"))
        or not isinstance(fresh.get("mailbox_error"), str)
        or not isinstance(archive_at, str)
        or not isinstance(fresh.get("observed_at_utc"), str)
        or not (
            datetime.fromisoformat(archive_at)
            <= datetime.fromisoformat(fresh["observed_at_utc"])
            <= now
        )
    ):
        raise ValueError("interrupted import observations are unusable")
    ancestry = _SOURCE_ANCESTRY(
        root, authority.episode_source_sha, str(recorder.get("sha") or "")
    )
    if (
        ancestry.error
        or not ancestry.is_ancestor
        or ancestry.ancestor_tree != authority.episode_source_tree
    ):
        raise ValueError("interrupted import recorder did not descend")
    return recorder, fresh, archive_at


def _complete_import(
    store: ServerPtCommissioningStore,
    attempt_id: str,
    document: Mapping[str, object],
    written: bytes,
    addendum: bytes,
    artifacts: Mapping[str, bytes],
    tolerate: frozenset[str],
    census: Mapping[str, object],
    recorder: Mapping[str, object],
) -> int:
    """Index an interrupted import's record only if it is its validated rebuild.

    The caller revalidated every original, the manifest and the launch, and
    rebuilt the record from them with only the earlier run's stated values;
    the stored bytes must equal that rebuild, and every file it names must
    hold exactly the bytes it states. Only its derived digest may be missing.
    The earlier run's census cannot be observed again, so this completion
    records its own `census` beside it and marks the earlier one as only
    reported. A completion that was itself interrupted is refused for an
    operator decision rather than completed again.
    """
    record_path = store.record_path_for(attempt_id, "exit-import")
    sidecar = record_path.with_name("exit-import.sha256")
    completion = store.record_path_for(attempt_id, "exit-import-completion")
    addendum_path, artifact_paths = _import_paths(store.campaign_id, attempt_id)
    predecessor = document["index_predecessor"]
    try:
        if completion.exists():
            raise ValueError("an interrupted completion needs an operator decision")
        if store.mapping_bytes(document) != written:
            raise ValueError("import record differs from its validated rebuild")
        if (store.root / predecessor["path"]).read_bytes() != store.index_bytes():
            raise ValueError("preserved index differs from the current index")
        if (store.root / addendum_path).read_bytes() != addendum:
            raise ValueError("archived addendum differs")
        for role, raw in artifacts.items():
            if (store.root / artifact_paths[role]).read_bytes() != raw:
                raise ValueError("archived artifact differs from its original")
        named = {
            store.relative_path(record_path),
            store.relative_path(sidecar),
            predecessor["path"],
            addendum_path,
            *(artifact_paths[role] for role in artifacts),
        }
        if not tolerate <= named:
            raise ValueError("residue the import record does not name")
        store.save_exit_import_completion(
            attempt_id,
            {
                "kind": "historical_exit_import_completion",
                "campaign_id": store.campaign_id,
                "attempt_id": attempt_id,
                "record_sha256": hashlib.sha256(written).hexdigest(),
                "earlier_fresh_state": (
                    "reported_by_the_interrupted_run_not_reobserved"
                ),
                "fresh_state": dict(census),
                "recorder_source": dict(recorder),
                "completed_at_utc": datetime.now(UTC).isoformat(),
            },
        )
        store.seal_exit_import(attempt_id)
        store.refresh_index(predecessor=predecessor)
        if store.verify_index():
            raise ValueError("completed import archive is unverified")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        _print(
            {"outcome": "refused", "reason": f"import_completion:{type(exc).__name__}"}
        )
        return 2
    _print(
        {
            "phase": "exit-import",
            "outcome": document["disposition"],
            "attempt_id": attempt_id,
            "completed_interrupted_import": True,
            "retire_credited": False,
            "index_predecessor_sha256": predecessor["sha256"],
            "exit_import_sha256": hashlib.sha256(written).hexdigest(),
        }
    )
    return 0


def _import_exit(
    root: Path,
    attempt_id: str,
    campaign: ServerPtCampaign,
    addendum_file: str,
    manifest_file: str,
) -> int:
    """Import one historical exit under its operator addendum, append-only.

    Nothing is closed, terminated or configured, so the recorder may run at
    a clean committed descendant of the episode's source: it proves the
    ancestry and the episode's tree, and records its own source separately.
    Every original is validated and the current state observed before the
    first write; the prior index is preserved and named by the new one. No
    `process-exit` record is written, and nothing is credited to `--retire`.
    Every write accepts its own identical bytes, so a run stopped between
    writes is finished by its retry. A record written before the stop is
    indexed only if it equals the record rebuilt from revalidated originals
    (`_complete_import`); it is never rewritten.
    """
    authority = _EXIT_IMPORT_AUTHORITY
    store = ServerPtCommissioningStore(root, campaign.campaign_id)
    written: bytes | None = None
    try:
        if (campaign.campaign_id, attempt_id) != (
            authority.campaign_id,
            authority.attempt_id,
        ):
            raise PermissionError("import is not authorized for this attempt")
        addendum = _read_bounded(addendum_file, _IMPORT_ARTIFACT_LIMIT)
        if hashlib.sha256(addendum).hexdigest() != authority.addendum_sha256:
            raise PermissionError("addendum digest differs from the authority")
        source = repository_identity(root)
        if source_authority_findings(campaign, source, None):
            raise ValueError("recorder checkout is not a clean commit")
        ancestry = _SOURCE_ANCESTRY(root, authority.episode_source_sha, source.head)
        if (
            ancestry.error
            or not ancestry.is_ancestor
            or ancestry.ancestor_tree != authority.episode_source_tree
        ):
            raise ValueError("recorder does not descend from the episode source")
        tolerate = _import_residue(store, attempt_id)
        launch = store.load_process_launch(attempt_id)
        if (
            launch.get("campaign_id") != campaign.campaign_id
            or launch.get("execution_purpose") != campaign.purpose.value
        ):
            raise ValueError("launch was not recorded by this campaign")
        store.require_immutable_phase(
            attempt_id, "cleanup", "restored", tolerate=tolerate
        )
        if store.record_path_for(attempt_id, "process-exit").exists():
            raise ValueError("process-exit already exists")
        record_path = store.record_path_for(attempt_id, "exit-import")
        if record_path.exists():
            if store.relative_path(record_path) not in tolerate:
                raise ValueError("exit-import already exists")
            written = record_path.read_bytes()
            earlier = json.loads(written)
            if not isinstance(earlier, dict):
                raise ValueError("interrupted import record is not an object")
            recorder, fresh, archive_at = _earlier_observations(root, earlier)
        else:
            recorder = {
                "sha": source.head,
                "tree": source.tree,
                "branch": source.branch,
                "upstream": source.upstream,
                "upstream_head": source.upstream_head,
                "clean": source.clean,
            }
            archive_at = datetime.now(UTC).isoformat()
        result_name = f"episode-{authority.episode:04d}-{attempt_id}-cleanup-result"
        cleanup_result = store.ledger_records().get(result_name) or {}
        manifest = json.loads(_read_bounded(manifest_file, _IMPORT_MANIFEST_LIMIT))
        if not isinstance(manifest, dict) or not isinstance(
            manifest.get("artifacts"), dict
        ):
            raise ValueError("import manifest is not an object")
        artifacts = {
            role: _read_bounded(
                meta.get("path") if isinstance(meta, dict) else None,
                _IMPORT_ARTIFACT_LIMIT,
            )
            for role, meta in manifest["artifacts"].items()
        }
        findings = historical_exit_import_findings(
            authority=authority,
            manifest=manifest,
            launch=launch,
            cleanup_recorded_at_utc=str(cleanup_result.get("recorded_at_utc") or ""),
            artifacts=artifacts,
            archive_at_utc=archive_at,
        )
        if findings:
            _print({"outcome": "refused", "reasons": list(findings)})
            return 2
        transcript = _transcript_source(
            manifest["artifacts"]["transcript_excerpt"], artifacts["transcript_excerpt"]
        )
        # Every run observes the current state itself; a completion keeps
        # the interrupted run's census only as that run reported it.
        census = _fresh_state(launch["pid"])
        if census["owned_pid_present"]:
            raise ValueError("a process with the owned PID is present now")
        if written is None:
            fresh = census
        document = _import_document(
            campaign=campaign,
            attempt_id=attempt_id,
            manifest=manifest,
            artifacts=artifacts,
            launch=launch,
            launch_sha256=hashlib.sha256(
                store.record_path_for(attempt_id, "process-launch").read_bytes()
            ).hexdigest(),
            cleanup_status_sha256=hashlib.sha256(
                store.record_path_for(attempt_id, "cleanup-status").read_bytes()
            ).hexdigest(),
            cleanup_result=cleanup_result,
            episode_tree=authority.episode_source_tree,
            recorder=recorder,
            transcript=transcript,
            fresh=fresh,
            predecessor=store.index_predecessor(),
            archive_at=archive_at,
        )
    except PermissionError as exc:
        _print({"outcome": "refused", "reason": f"import_not_authorized:{exc}"})
        return 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        _print({"outcome": "refused", "reason": f"import_exit:{type(exc).__name__}"})
        return 2
    if written is not None:
        return _complete_import(
            store,
            attempt_id,
            document,
            written,
            addendum,
            artifacts,
            tolerate,
            census,
            {
                "sha": source.head,
                "tree": source.tree,
                "branch": source.branch,
                "upstream": source.upstream,
                "upstream_head": source.upstream_head,
                "clean": source.clean,
            },
        )
    try:
        if store.preserve_index() != document["index_predecessor"]:
            raise ValueError("preserved index differs from the validated one")
        store.save_authority_document("addendum-02.md", addendum)
        for role in sorted(artifacts):
            store.save_exit_import_artifact(
                attempt_id,
                role.replace("_", "-"),
                _IMPORT_SUFFIXES[role],
                artifacts[role],
            )
        path = store.save_exit_import(attempt_id, document)
        store.refresh_index(predecessor=document["index_predecessor"])
        if store.verify_index():
            raise ValueError("exit import archive is unverified")
    except (OSError, ValueError, KeyError) as exc:
        _print({"outcome": "refused", "reason": f"import_write:{type(exc).__name__}"})
        return 2
    _print(
        {
            "phase": "exit-import",
            "outcome": document["disposition"],
            "attempt_id": attempt_id,
            "process_id": launch.get("pid"),
            "exit_method": document["exit_method"],
            "completed_interrupted_import": False,
            "retire_credited": False,
            "recorder_source_sha": source.head,
            "episode_source_sha": authority.episode_source_sha,
            "index_predecessor_sha256": document["index_predecessor"]["sha256"],
            "exit_import_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    )
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


def _ready_prequalification(
    store: ServerPtCommissioningStore, attempt_ids: Sequence[str]
) -> str:
    """Return the campaign's archived ready preliminary attempt, if any."""
    for candidate in attempt_ids:
        try:
            store.require_immutable_phase(
                candidate, "prequalification", "ready_for_catalog_review"
            )
        except (OSError, ValueError):
            continue
        return candidate
    return ""


def _qualify(
    root: Path,
    attempt_id: str,
    ci_run_id: int,
    campaign: ServerPtCampaign = C31_CAMPAIGN,
    episode: int = 0,
) -> int:
    """Measure the two authorized prerequisites through one fixed file channel."""
    store = ServerPtCommissioningStore(root, campaign.campaign_id)
    if _adopt_ledger_residue(store, campaign):
        _print({"outcome": "refused", "reason": "prior_archive_unverified"})
        return 2
    try:
        already = store.prequalification_attempt_ids()
    except OSError:
        _print(
            {"outcome": "refused", "reason": "prequalification_inventory_unreadable"}
        )
        return 2
    if campaign.experimental:
        # One ready preliminary result serves the whole experimental campaign;
        # a new one is admitted only while none is ready, never on a used ID.
        if attempt_id in already or _ready_prequalification(store, already):
            _print(
                {"outcome": "refused", "reason": "prequalification_already_reserved"}
            )
            return 2
    elif attempt_id == RECOVERY_PREQUALIFICATION_ATTEMPT:
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
    preflight = phase_preflight(root, ci_run_id=ci_run_id, campaign=campaign)
    if preflight.findings:
        _print({"outcome": "refused", "reasons": list(preflight.findings)})
        return 2
    assert preflight.source is not None
    assert preflight.process is not None
    assert (preflight.ci is None) == campaign.experimental
    if not campaign.experimental and attempt_id == RECOVERY_PREQUALIFICATION_ATTEMPT:
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
    refusal = _admit_phase(
        store, campaign, episode, attempt_id, "prequalification", preflight
    )
    if refusal:
        _print({"outcome": "refused", "reasons": list(refusal)})
        return 2
    bound = None
    result = None
    path = None
    reason = ""
    interrupted = False
    phase_started = time.monotonic()
    try:
        grant = derive_server_pt_phase_grant(
            "prequalification",
            attempt_id,
            preflight.source,
            preflight.process,
            preflight.ci,
            campaign=campaign,
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
    _settle_phase(
        store,
        campaign,
        episode,
        attempt_id,
        "prequalification",
        status,
        time.monotonic() - phase_started,
    )
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


def _setup(
    root: Path,
    attempt_id: str,
    ci_run_id: int,
    campaign: ServerPtCampaign = C31_CAMPAIGN,
    episode: int = 0,
) -> int:
    """Deploy exact E4 and L2 E5 after preliminary evidence was pinned."""
    store = ServerPtCommissioningStore(root, campaign.campaign_id)
    if _adopt_ledger_residue(store, campaign):
        _print({"outcome": "refused", "reason": "prior_archive_unverified"})
        return 2
    used_attempts = store.setup_attempt_ids()
    if attempt_id in used_attempts:
        _print({"outcome": "refused", "reason": "setup_attempt_already_reserved"})
        return 2
    if (
        campaign.complete_attempt_limit is not None
        and len(used_attempts) >= campaign.complete_attempt_limit
    ):
        _print({"outcome": "refused", "reason": "campaign_attempt_allowance_exhausted"})
        return 2
    if campaign.experimental:
        try:
            qualification_id = _ready_prequalification(
                store, store.prequalification_attempt_ids()
            )
        except OSError:
            qualification_id = ""
        if not qualification_id:
            _print({"outcome": "refused", "reason": "prequalification_not_verified"})
            return 2
    else:
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
    preflight = phase_preflight(root, ci_run_id=ci_run_id, campaign=campaign)
    if preflight.findings:
        _print({"outcome": "refused", "reasons": list(preflight.findings)})
        return 2
    assert preflight.source is not None
    assert preflight.process is not None
    assert (preflight.ci is None) == campaign.experimental
    try:
        launch = store.load_process_launch(attempt_id)
        if launch_evidence_findings(launch, preflight.process):
            raise ValueError("setup receiver was not campaign launched")
    except (OSError, ValueError):
        _print({"outcome": "refused", "reason": "campaign_launch_unverified"})
        return 2
    if used_attempts and not campaign.experimental:
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
        campaign=campaign,
    )
    refusal = _ledger_admit(
        store,
        campaign,
        episode,
        attempt_id,
        "setup",
        grant.max_operations,
        grant.max_seconds,
        source=preflight.source,
    )
    if refusal:
        _print({"outcome": "refused", "reasons": list(refusal)})
        return 2
    bound = None
    result = None
    reason = ""
    interrupted = False
    phase_started = time.monotonic()
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
    _settle_phase(
        store,
        campaign,
        episode,
        attempt_id,
        "setup",
        status,
        time.monotonic() - phase_started,
    )
    try:
        store.save_phase_status(attempt_id, "setup", status)
    except (OSError, ValueError) as exc:
        status["outcome"] = "stopped"
        status["reason"] = f"setup_status_persistence_failed:{type(exc).__name__}"
    _archive_or_stop(store, status)
    _print(status)
    return 130 if interrupted else 0 if status["outcome"] == "ready" else 1


def _cleanup(
    root: Path,
    attempt_id: str,
    ci_run_id: int,
    campaign: ServerPtCampaign = C31_CAMPAIGN,
    episode: int = 0,
) -> int:
    """Remove only E4-owned objects with the original receiver still bound."""
    store = ServerPtCommissioningStore(root, campaign.campaign_id)
    if _adopt_ledger_residue(store, campaign):
        _print({"outcome": "refused", "reason": "prior_archive_unverified"})
        return 2
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
    preflight = phase_preflight(root, ci_run_id=ci_run_id, campaign=campaign)
    if preflight.findings:
        _print({"outcome": "refused", "reasons": list(preflight.findings)})
        return 2
    assert preflight.source is not None
    assert preflight.process is not None
    assert (preflight.ci is None) == campaign.experimental
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
        campaign=campaign,
    )
    refusal = _ledger_admit(
        store,
        campaign,
        episode,
        attempt_id,
        "cleanup",
        grant.max_operations,
        grant.max_seconds,
        source=preflight.source,
    )
    if refusal:
        _print({"outcome": "refused", "reasons": list(refusal)})
        return 2
    bound = None
    result = None
    reason = ""
    interrupted = False
    phase_started = time.monotonic()
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
    _settle_phase(
        store,
        campaign,
        episode,
        attempt_id,
        "cleanup",
        status,
        time.monotonic() - phase_started,
    )
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


def _accept(
    root: Path,
    attempt_id: str,
    ci_run_id: int,
    campaign: ServerPtCampaign = C31_CAMPAIGN,
    episode: int = 0,
) -> int:
    """Run the existing product coordinator with its sealed schema-2 grant.

    An experimental campaign reports a passing run as `measured`, never as
    `accepted`: its checkpoint had no delivery checks, and acceptance of the
    delivery belongs to an independent review.
    """
    store = ServerPtCommissioningStore(root, campaign.campaign_id)
    if _adopt_ledger_residue(store, campaign):
        _print({"outcome": "refused", "reason": "prior_archive_unverified"})
        return 2
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
    preflight = phase_preflight(root, ci_run_id=ci_run_id, campaign=campaign)
    if preflight.findings:
        _print({"outcome": "refused", "reasons": list(preflight.findings)})
        return 2
    assert preflight.source is not None
    assert preflight.process is not None
    assert (preflight.ci is None) == campaign.experimental
    try:
        sealed = seal_server_pt_acceptance(
            attempt_id,
            store=store,
            source=preflight.source,
            process=preflight.process,
            ci=preflight.ci,
            campaign=campaign,
            allocation=(
                episode_allowance_left(
                    store.ledger_records(), episode, datetime.now(UTC)
                )
                if campaign.experimental
                else None
            ),
        )
    except (OSError, ValueError) as exc:
        _print(
            {
                "outcome": "refused",
                "reason": f"acceptance_seal_failed:{type(exc).__name__}",
            }
        )
        return 2
    refusal = _ledger_admit(
        store,
        campaign,
        episode,
        attempt_id,
        "acceptance",
        int(sealed.grant["max_operations"]),
        float(sealed.grant["max_seconds"]),
        source=preflight.source,
    )
    if refusal:
        _print({"outcome": "refused", "reasons": list(refusal)})
        return 2
    raw_path = store.journal_path_for(attempt_id, "acceptance")
    recorded_channels: list[GovernedPhaseChannel] = []

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
            recorded_channels.append(recorded)
            return OpenedTransport(channel, recorded, opened.live, opened.detail)

        return replace(
            boundaries,
            open_channel=open_recorded,
            experimental_authority=authority,
        )

    # Validated above: the charter, the open episode, its exact checkpoint
    # (ledger admission), the fresh experimental preflight and the sealed
    # grant. A delivery campaign passes none, so publication stays required.
    authority = (
        ExperimentalSourceAuthority(
            campaign_id=campaign.campaign_id,
            episode=episode,
            attempt_id=attempt_id,
            authorization_id=str(sealed.grant["authorization_id"]),
            sha=preflight.source.head,
            tree=preflight.source.tree,
        )
        if campaign.experimental
        else None
    )

    output = StringIO()
    reason = ""
    interrupted = False
    summary: dict[str, object] = {}
    phase_started = time.monotonic()
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
        # The product's success code follows the grant's purpose; only the
        # one this campaign's purpose implies completes this phase.
        success = MEASURED_EXIT_CODE if campaign.experimental else 0
        if exit_code == success and envelope is None:
            raise ValueError("accepted attempt lacks an envelope")
        if raw_path.exists():
            if envelope is not None:
                raw_index = build_raw_answer_index(raw_path, envelope)
                store.save_acceptance_raw_index(attempt_id, raw_index)
        elif exit_code == success:
            raise ValueError("original acceptance answers were not retained")
        if exit_code == success:
            envelopes = ColdHttpAcceptanceStore(
                root / "data" / "acceptance" / "cold-http"
            )
            publication = envelopes.load_publication(attempt_id)
            if publication_claim(envelope, publication) != (True, ""):
                reason = "publication_claim_not_established"
            elif (
                EXPERIMENTAL_ENVELOPE_LIMITATION in envelope.limitations
            ) is not campaign.experimental:
                # An experimental envelope never completes a delivery phase,
                # and a delivery envelope never stands in for a measurement.
                reason = "envelope_purpose_differs_from_campaign"
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
    passed = (
        exit_code == (MEASURED_EXIT_CODE if campaign.experimental else 0) and not reason
    )
    status = {
        "phase": "acceptance",
        "outcome": (
            ("measured" if campaign.experimental else "accepted")
            if passed
            else "stopped"
        ),
        "reason": reason,
        "exit_code": exit_code,
        "attempt_id": attempt_id,
        "grant_path": sealed.grant_path,
        "seal_path": sealed.seal_path,
        "raw_path": str(raw_path) if raw_path.exists() else "",
        "product_summary": summary,
    }
    if campaign.experimental:
        status["execution_purpose"] = campaign.purpose.value
        status["ledger_result"] = (
            _ledger_result(
                store,
                campaign,
                episode,
                attempt_id,
                "acceptance",
                recorded_channels[-1].used_operations if recorded_channels else 0,
                time.monotonic() - phase_started,
                str(status["outcome"]),
            )
            or "recorded"
        )
    try:
        store.save_acceptance_status(attempt_id, status)
    except (OSError, ValueError) as exc:
        status["outcome"] = "stopped"
        status["reason"] = f"acceptance_status_persistence_failed:{type(exc).__name__}"
    _archive_or_stop(store, status)
    _print(status)
    return (
        130
        if interrupted
        else 0
        if status["outcome"] in {"accepted", "measured"}
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
