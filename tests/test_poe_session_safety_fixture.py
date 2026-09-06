"""Portability contract for synthetic governed PoE safety evidence."""

from __future__ import annotations

from pathlib import Path

from src.packet_tracer_mcp.domain.enterprise.rules.live_session_safety import (
    validate_live_session_positive_admission,
)
from tests.poe_session_safety import healthy_live_session_safety


def test_healthy_live_session_safety_uses_host_absolute_pts_identities() -> None:
    evidence = healthy_live_session_safety()

    canonical = Path(evidence.canonical_path or "")
    disposable = Path(evidence.disposable_path or "")

    assert canonical.is_absolute()
    assert disposable.is_absolute()
    assert canonical.suffix.casefold() == ".pts"
    assert disposable.suffix.casefold() == ".pts"
    assert canonical != disposable
    assert validate_live_session_positive_admission(evidence).is_valid
