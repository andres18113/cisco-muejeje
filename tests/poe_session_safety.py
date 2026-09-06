"""Portable synthetic LIVE-session safety evidence for offline tests."""

from __future__ import annotations

from pathlib import Path

from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    LiveSessionSafetyEvidence,
)


def healthy_live_session_safety() -> LiveSessionSafetyEvidence:
    """Return internally coherent safety evidence with host-native identities."""

    fixture_root = Path(__file__).resolve().parent / ".poe-session-safety-fixture"
    stable_sha256 = "a" * 64
    return LiveSessionSafetyEvidence(
        canonical_path=str(fixture_root / "canonical.pts"),
        canonical_pre_run_sha256=stable_sha256,
        canonical_observed_post_run_sha256=stable_sha256,
        canonical_verified_sha256=stable_sha256,
        disposable_path=str(fixture_root / "disposable.pts"),
        disposable_pre_run_sha256=stable_sha256,
        disposable_post_run_sha256=stable_sha256,
        unexpected_canonical_modification=False,
        disposable_modified=False,
        runtime_healthy=True,
        crash_detected=False,
        integrity_verified=True,
        session_reusable=True,
        positive_claim_allowed=True,
    )
