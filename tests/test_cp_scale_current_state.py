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
    assert state["active_stage"] == "router0-branch"
    assert state["status"] == (
        "ROUTER0_LIVE_BLOCKER_FIXED_OFFLINE_PENDING_RERUN"
    )
    assert state["first_contradicted_boundary"] == (
        "FLOOR2_VOICE_SIGNAL_PVST_LEARNING_WINDOW"
    )
    assert state["next_active_step"] == "RERUN_ROUTER0_CANONICAL_LIVE"
    assert set(state["stages"]) == {"floor3", "router0-branch"}

    floor3 = state["stages"]["floor3"]
    assert floor3 == {
        "network": "VERIFIED",
        "voice": "VERIFIED_42_OF_42",
        "control_plane": "CAPABILITY_GAP_CLOSED_AFTER_PRIOR_PARTIAL_LIVE",
    }
    router0 = state["stages"]["router0-branch"]
    assert router0["result"] == "NOT_REACHED_AFTER_FLOOR2_NEGATIVE_LIVE"
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
            "canonical-cp-scale-voice-20260902T215118136599Z-"
            "aa94ce992c6b"
        ),
        "source_head": "aa94ce992c6bbcd45e44f4aca097f446b28e2ca4",
        "highest_verified_stage": "floor1",
        "failed_stage": "floor2",
        "failure_boundary": "VOICE_SIGNAL",
        "terminal_stp": {
            "switch": "Switch7",
            "voice_vlan_id": 20,
            "ports": 14,
            "state": "LRN",
            "wall_clock_elapsed_ms": 45563,
            "packet_tracer_simulation_elapsed_ms": 24361,
        },
        "fix": "ONE_PROTOCOL_BOUNDED_LRN_EXTENSION_OFFLINE_VERIFIED",
        "cleanup": {
            "workspace_restored_twice": True,
            "semantic_devices": 0,
            "links": 0,
            "realtime_restored": True,
        },
    }

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
