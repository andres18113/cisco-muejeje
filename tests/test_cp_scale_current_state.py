"""Compact CP-SCALE state authority and legacy handoff compatibility."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from tests.handoff_state import parse_handoff_state


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "docs" / "reference" / "cp-scale" / "current_state.json"
HANDOFF_PATH = ROOT / "handoff.md"


def test_compact_current_state_is_bounded_and_matches_the_handoff_projection():
    raw = STATE_PATH.read_bytes()
    state = json.loads(raw)

    assert state["schema"] == "cp-scale-current-state-v1"
    assert len(raw) < 16_384
    assert datetime.fromisoformat(state["updated_at"].replace("Z", "+00:00"))
    assert re.fullmatch(r"[0-9a-f]{40}", state["source_head"])
    assert state["active_stage"] == "floor3"
    assert state["status"] == (
        "ROUTER0_NOT_REACHED_PVST_SIMULATION_TIME_CORRECTION_OFFLINE_VALIDATED"
    )
    assert state["first_contradicted_boundary"] == (
        "FLOOR3_VOICE_SIGNAL_SWITCH9_VLAN20_PVST_LRN_AFTER_SINGLE_EXTENSION"
    )
    assert state["next_active_step"] == (
        "RUN_ONE_GOVERNED_CANONICAL_ROUTER0_CP_LIVE_FROM_CLEAN_HEAD"
    )
    assert set(state["stages"]) == {"floor2", "floor3", "router0-branch"}

    floor2 = state["stages"]["floor2"]
    assert floor2 == {
        "network": "VERIFIED",
        "voice": "VERIFIED_35_OF_35",
        "switch7_voice_vlan20": "14_OF_14_FWD_AFTER_ONE_20S_EXTENSION",
    }

    floor3 = state["stages"]["floor3"]
    assert floor3 == {
        "network": "FOUNDATION_VERIFIED",
        "voice": "BLOCKED_AT_SIGNAL_SWITCH9_3_LRN",
        "control_plane": "NOT_REACHED_IN_LATEST_LIVE",
        "prior_voice_authority": "VERIFIED_42_OF_42_RUN21",
    }
    router0 = state["stages"]["router0-branch"]
    assert router0["result"] == "NOT_REACHED_AFTER_FLOOR3_NEGATIVE_LIVE"
    assert router0["expected_scope"] == {
        "cumulative_devices": 290,
        "cumulative_links": 202,
        "cumulative_phones": 62,
        "new_devices": 58,
        "new_links": 42,
        "configuration_mutations": 84,
        "control_plane_mutations": 40,
        "voice_mutations": 45,
    }
    assert state["latest_live_run"] == {
        "run_identity": (
            "canonical-cp-scale-voice-20260903T002846400677Z-"
            "6c6db5556689"
        ),
        "source_head": "6c6db55566890f1d9ca9cc06bfc13ae24505e793",
        "highest_verified_stage": "floor2",
        "failed_stage": "floor3",
        "failure_boundary": "VOICE_SIGNAL",
        "floor2_correction_result": {
            "switch": "Switch7",
            "voice_vlan_id": 20,
            "ports": 14,
            "initial_state": "LRN",
            "final_state": "FWD",
            "learning_extension_seconds": 20.0,
            "wall_clock_elapsed_ms": 45454,
            "terminal_authority": "AUTHORITATIVE",
        },
        "terminal_stp": {
            "switch": "Switch9",
            "voice_vlan_id": 20,
            "ports": 3,
            "state": "LRN",
            "wall_clock_elapsed_ms": 66404,
            "packet_tracer_simulation_elapsed_ms": 39355,
            "learning_extension_seconds": 20.0,
            "terminal_authority": "AUTHORITATIVE",
            "terminal_failure_dimension": "NON_FORWARDING",
        },
        "classification": {
            "product": "NOT_CONTRADICTED",
            "observer_harness": (
                "FAILED_WALL_CLOCK_BUDGET_FOR_SIMULATION_TIME_PROTOCOL"
            ),
            "capability": "VERIFIED_NOT_FAILURE",
            "convergence": "FAILED_NON_FORWARDING",
            "evidence": "AUTHORITATIVE_COMPLETE_FRESH_IDENTITY_BOUND",
        },
        "fix": "NONE_THIS_SESSION",
        "cleanup": {
            "workspace_restored_twice": True,
            "semantic_devices": 0,
            "links": 0,
            "realtime_restored": True,
        },
    }
    assert state["offline_correction"] == {
        "debt_id": "TD-PVST-WINDOW-001",
        "status": "OFFLINE_VALIDATED_LIVE_PENDING",
        "evidence_checkpoint": (
            "99bf4734f31c6dc7b22e49dd4cc46a3085c10036"
        ),
        "implementation_head": (
            "c45517972892b321fddb8a8032a31c4deb6bdf1a"
        ),
        "mechanism": "PACKET_TRACER_SIMULATION_TIME_PROGRESS",
        "forward_delay_source": (
            "FRESH_COMPLETE_IDENTITY_BOUND_SHOW_SPANNING_TREE"
        ),
        "qualified_forward_delay_seconds": 15.0,
        "simulation_progress_budget_seconds": 20.0,
        "wall_clock_safety_cap_seconds": 45.0,
        "wall_clock_cap_semantics": (
            "ADMISSION_BOUNDARY_NOT_EXECUTION_DEADLINE"
        ),
        "causal_outcome_projection": (
            "CONVERGED_NETWORK_MEASURED_OBSERVER_INCOMPLETE"
        ),
        "single_authority": True,
        "live_validation": "NOT_RUN_THIS_SESSION",
    }
    assert state["run_accounting"] == {
        "authority": "CURRENT_STATE_PLUS_HASH_PINNED_CLEANUP_ARCHIVES",
        "canonical_live_attempts": 23,
        "invalid_live_attempts": 2,
        "live_runs_consumed": 36,
        "curated_ledger": {
            "path": "docs/reference/cp-scale/canonical_voice_runs.json",
            "entry_count": 21,
            "role": "CURATED_GOVERNED_JUDGMENTS_NOT_EXHAUSTIVE",
            "exhaustive_through": (
                "canonical-cp-scale-voice-20260901T133350798961Z-"
                "5373539f0b1f"
            ),
        },
        "post_ledger_retained_runs": [
            {
                "run_identity": (
                    "canonical-cp-scale-voice-20260902T215118136599Z-"
                    "aa94ce992c6b"
                ),
                "cleanup_evidence_role": "router0_attempt1_cleanup",
                "invalid_live_attempt": False,
                "provenance": "HASH_PINNED_ARCHIVE_AND_GOVERNED_STATE",
            },
            {
                "run_identity": (
                    "canonical-cp-scale-voice-20260903T002846400677Z-"
                    "6c6db5556689"
                ),
                "cleanup_evidence_role": "router0_attempt2_cleanup",
                "invalid_live_attempt": False,
                "provenance": "HASH_PINNED_ARCHIVE_AND_GOVERNED_STATE",
            },
        ],
    }
    assert state["unresolved_debt"] == []

    handoff = parse_handoff_state(HANDOFF_PATH.read_text(encoding="utf-8"))
    assert state["handoff_compatibility"]
    for key, expected in state["handoff_compatibility"].items():
        assert handoff[key] == expected


def test_compact_current_state_evidence_paths_and_hashes_are_exact():
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    assert state["evidence"]
    for item in state["evidence"]:
        path = ROOT / item["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
