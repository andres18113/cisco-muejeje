"""A second C31 attempt requires a preserved failure, correction and new PT."""

from __future__ import annotations

import pytest


def _correction():
    return {
        "first_attempt_id": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
        "first_result_sha256": "a" * 64,
        "first_retirement_sha256": "b" * 64,
        "corrected_source_sha": "c" * 40,
        "classification": "transport",
        "causal_explanation": "The retained response showed a dropped file-channel result.",
        "corrective_action": "The owning bridge result reader was corrected and regressed.",
    }


def test_second_attempt_requires_fresh_process_and_causal_record():
    """A new nonce or same process cannot authorize a blind repeat."""
    from packet_tracer_mcp.application.use_cases.server_pt_second_attempt import (
        second_attempt_findings,
    )

    kwargs = {
        "first_attempt_id": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
        "first_process_incarnation": "first-process",
        "first_result_outcome": "stopped",
        "first_retirement_outcome": "restored",
        "first_result_sha256": "a" * 64,
        "first_retirement_sha256": "b" * 64,
        "new_source_sha": "c" * 40,
        "new_process_incarnation": "fresh-process",
        "correction": _correction(),
    }

    assert second_attempt_findings(**kwargs) == ()
    assert "causal_correction_missing" in second_attempt_findings(
        **{**kwargs, "correction": None}
    )
    assert "process_not_fresh" in second_attempt_findings(
        **{**kwargs, "new_process_incarnation": "first-process"}
    )
    assert (
        second_attempt_findings(
            **{**kwargs, "first_retirement_outcome": "exited_dirty"}
        )
        == ()
    )
    assert "first_retirement_not_safe" in second_attempt_findings(
        **{**kwargs, "first_retirement_outcome": "stopped"}
    )


def test_partial_e4_allows_only_indexed_dirty_process_retirement(tmp_path):
    """Uncertain objects stay untouched while owned-process exit is preserved."""
    from packet_tracer_mcp.adapters.cli.server_pt_commissioning import (
        _first_retirement,
    )
    from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
        ServerPtCommissioningStore,
    )

    attempt = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
    store = ServerPtCommissioningStore(tmp_path)
    store.save_phase_status(attempt, "setup", {"outcome": "stopped"})
    store.refresh_index()
    store.save_archive_admission(attempt, "setup")
    identity = {
        "pid": 123,
        "process_path": "C:/PacketTracer.exe",
        "process_incarnation": "owned-first-process",
    }
    store.save_process_launch(attempt, identity)
    store.save_process_exit(
        attempt,
        {
            **identity,
            "method": "CloseMainWindow",
            "requested": True,
            "disposition": "exited_dirty",
            "actual_exit_observed": True,
            "process_count": 0,
        },
    )
    store.refresh_index()

    outcome, digest = _first_retirement(store, attempt)
    assert outcome == "exited_dirty"
    assert len(digest) == 64

    # The archived row must carry the original graceful-close proof too.
    bad = "1f1e2d3c4b5a69788796a5b4c3d2e1f0"
    store.save_phase_status(bad, "setup", {"outcome": "stopped"})
    store.save_archive_admission(bad, "setup")
    store.save_process_launch(bad, identity)
    store.save_process_exit(
        bad,
        {
            **identity,
            "disposition": "exited_dirty",
            "actual_exit_observed": True,
            "process_count": 0,
        },
    )
    store.refresh_index()
    with pytest.raises(ValueError, match="exit is unverified"):
        _first_retirement(store, bad)

    from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
        PhysicalWorkspaceObservation,
    )

    store.save_precleanup(attempt, PhysicalWorkspaceObservation())
    store.refresh_index()
    with pytest.raises(ValueError, match="conflicts with cleanup"):
        _first_retirement(store, attempt)
