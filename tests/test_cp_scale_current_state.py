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
        "ROUTER0_NOT_REACHED_FLOOR3_VOICE_SIGNAL_CONVERGENCE_BLOCKED"
    )
    assert state["first_contradicted_boundary"] == (
        "FLOOR3_VOICE_SIGNAL_SWITCH9_VLAN20_PVST_LRN_AFTER_SINGLE_EXTENSION"
    )
    assert state["next_active_step"] == (
        "FIX_PVST_SIMULATION_TIME_BUDGET_BEFORE_ANY_LIVE"
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
    assert state["unresolved_debt"] == [
        {
            "id": "TD-PVST-WINDOW-001",
            "status": "BLOCKING",
            "resolve_before": "ANY_FURTHER_CANONICAL_CP_SCALE_LIVE",
        },
        {
            "id": "TD-CP-SCALE-LEDGER-001",
            "status": "BLOCKING",
            "resolve_before": "ANY_FURTHER_CANONICAL_CP_SCALE_LIVE",
        },
    ]

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
