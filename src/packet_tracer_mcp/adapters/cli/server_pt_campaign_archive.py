"""Campaign archive and ledger writes shared by the Server-PT campaign CLIs.

The commissioning CLI and the qualification CLI both record experimental
phases in one campaign store: a ledger admission before contact, a result
after it, and an indexed, hash-verified status. They share these helpers
rather than importing each other, which would make the two adapters one
import cycle.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from ...application.use_cases.server_pt_campaign import ServerPtCampaign
from ...application.use_cases.server_pt_campaign_ledger import (
    allowance_for,
    phase_admission_findings,
    phase_record_name,
)
from ...domain.enterprise.models.service_qualification import RepositoryIdentity
from ...infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)


def refresh_archive(
    store: ServerPtCommissioningStore, status: Mapping[str, object]
) -> tuple[str, ...]:
    """Update one current projection and verify the single hash index."""
    try:
        store.update_current_status(status)
        store.refresh_index()
        return store.verify_index()
    except (OSError, ValueError) as exc:
        return (f"archive_index_unavailable:{type(exc).__name__}",)


def archive_or_stop(
    store: ServerPtCommissioningStore, status: dict[str, object]
) -> None:
    """Never report phase success when its source-byte index is unverified."""
    findings = refresh_archive(store, status)
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


def ledger_admit(
    store: ServerPtCommissioningStore,
    campaign: ServerPtCampaign,
    episode: int,
    attempt_id: str,
    phase: str,
    operations: int,
    seconds: float,
    *,
    source: RepositoryIdentity,
) -> tuple[str, ...]:
    """Write one phase admission before contact, or name why there is none.

    `source` is the checkout this phase will execute, observed by its own
    preflight; it must be the checkpoint the episode declared when it opened.
    The ceilings are the campaign's own charter, never another campaign's.
    """
    if not campaign.experimental:
        return ()
    try:
        now = datetime.now(UTC)
        findings, protected = phase_admission_findings(
            store.ledger_records(),
            episode=episode,
            attempt_id=attempt_id,
            phase=phase,
            granted_operations=int(operations),
            granted_seconds=float(seconds),
            allowance=allowance_for(campaign.campaign_id),
            now=now,
            source_sha=source.head,
            source_tree=source.tree,
        )
        if findings:
            return findings
        store.save_ledger_record(
            phase_record_name(episode, attempt_id, phase, "admission"),
            {
                "kind": "phase_admission",
                "episode": episode,
                "attempt_id": attempt_id,
                "phase": phase,
                "granted_operations": int(operations),
                "granted_seconds": float(seconds),
                "draws_protected": protected,
                "source_sha": source.head,
                "source_tree": source.tree,
                "admitted_at_utc": now.isoformat(),
            },
        )
        store.refresh_index()
        return store.verify_index()
    except (OSError, ValueError) as exc:
        return (f"ledger_admission_unavailable:{type(exc).__name__}",)


def ledger_result(
    store: ServerPtCommissioningStore,
    campaign: ServerPtCampaign,
    episode: int,
    attempt_id: str,
    phase: str,
    used_operations: int,
    active_seconds: float,
    outcome: str,
) -> str:
    """Record what one admitted phase used; a failure is returned, not raised."""
    if not campaign.experimental:
        return ""
    try:
        store.save_ledger_record(
            phase_record_name(episode, attempt_id, phase, "result"),
            {
                "kind": "phase_result",
                "episode": episode,
                "attempt_id": attempt_id,
                "phase": phase,
                "used_operations": int(used_operations),
                "active_seconds": round(max(0.0, active_seconds), 3),
                "outcome": outcome,
                "recorded_at_utc": datetime.now(UTC).isoformat(),
            },
        )
    except (OSError, ValueError) as exc:
        return f"ledger_result_unrecorded:{type(exc).__name__}"
    return ""
