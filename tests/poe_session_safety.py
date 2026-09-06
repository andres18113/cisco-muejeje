"""Portable synthetic LIVE-session safety evidence for offline tests."""

from __future__ import annotations

import os
from pathlib import Path

from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    ActiveWorkspaceBindingEvidence,
    ActiveWorkspaceIdentityMethod,
    LivePathIdentitySemantics,
    LiveSessionSafetyEvidence,
)


def healthy_live_session_safety() -> LiveSessionSafetyEvidence:
    """Return internally coherent safety evidence with host-native identities."""

    fixture_root = Path(__file__).resolve().parent / ".poe-session-safety-fixture"
    canonical_path = str(fixture_root / "canonical.pts")
    disposable_path = str(fixture_root / "disposable.pts")
    stable_sha256 = "a" * 64
    return LiveSessionSafetyEvidence(
        path_identity_semantics=(
            LivePathIdentitySemantics.WINDOWS
            if os.name == "nt"
            else LivePathIdentitySemantics.POSIX
        ),
        canonical_path=canonical_path,
        canonical_pre_run_sha256=stable_sha256,
        canonical_observed_post_run_sha256=stable_sha256,
        canonical_verified_sha256=stable_sha256,
        disposable_path=disposable_path,
        disposable_pre_run_sha256=stable_sha256,
        disposable_post_run_sha256=stable_sha256,
        active_workspace_binding=ActiveWorkspaceBindingEvidence(
            method=ActiveWorkspaceIdentityMethod.SCRIPT_MODULE_SELF_COMMAND_LINE,
            pre_qualification_path=disposable_path,
            post_integrity_path=disposable_path,
            pre_qualification_instance_id="synthetic-fixture-instance",
            post_integrity_instance_id="synthetic-fixture-instance",
            pre_qualification_module_id="synthetic-fixture-module",
            post_integrity_module_id="synthetic-fixture-module",
            pre_qualification_module_name="Synthetic Packet Tracer MCP module",
            post_integrity_module_name="Synthetic Packet Tracer MCP module",
        ),
        unexpected_canonical_modification=False,
        disposable_modified=False,
        runtime_healthy=True,
        crash_detected=False,
        integrity_verified=True,
        session_reusable=True,
        positive_claim_allowed=True,
    )
