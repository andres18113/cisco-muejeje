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
    document = json.loads(raw)

    assert document["schema"] == "cp-scale-current-state-v2"
    assert len(raw) < 16_384
    assert datetime.fromisoformat(document["updated_at"].replace("Z", "+00:00"))
    assert set(document) == {
        "schema",
        "updated_at",
        "last_live_state",
        "current_offline_operational_gate",
        "handoff_compatibility",
    }

    state = document["last_live_state"]
    gate = document["current_offline_operational_gate"]
    assert state != gate
    assert state["schema"] == "cp-scale-current-state-v1"
    assert state["updated_at"] == "2026-09-03T03:41:52.104318Z"
    assert gate == {
        "source_head": "961229ed80299d16ce6ebac0d8babbbf13723123",
        "source_head_role": "active_workspace_binding_gate_removed",
        "poe_delivery": "supported",
        "poe_ports": 1,
        "hardware_plan": "partially_resolved",
        "canonical_composition": "blocked_before_topology",
        "router0_authorized": False,
        "latest_poe_qualification": {
            "run_identity": "poe-7950198d050f",
            "packet_tracer_build": "9.0.1.0858",
            "decision": "A — DELIVERY VERIFIED",
            "observation_delivery": "DELIVERED_DURING_GOVERNED_OBSERVE",
            "session_reusable": True,
            "authorized_binding": "3560-24PS/FastEthernet0/1 + 7960/Switch",
            "comparison_model": "2960-24TT",
            "port_extrapolation_allowed": False,
            "artifact": {
                "path": (
                    "docs/reference/cp-scale/canonical-live-evidence/"
                    "poe-delivery-20260906T184155139196Z-"
                    "7950198d050f-verified.json"
                ),
                "sha256": (
                    "45ea94314228f1b0f49979f5fb815edd"
                    "d55d63c972429ad548f583b11c3d9a90"
                ),
            },
        },
        "observer_pipeline": {
            "finding": "OBSERVATION_DELIVERED_WITHIN_OBSERVE",
            "offline_status": "CORRECTED_AND_TESTED",
            "deadline_seconds": 300,
            "deadline_increased": False,
            "late_capture_accepted": False,
        },
        "reliability_finding": {
            "exception_code": "0xc0000005",
            "status": "CONFIRMED_NOT_ATTRIBUTED",
            "classification": "POST_BOUNDARY_RELIABILITY_INCIDENT",
            "invalidates_latest_qualification": False,
            "occurrences": 3,
            "identical_fault_offset": "0x00000000020e5204",
            "seconds_after_decision_persisted": 9.462,
            "dumps_retained": 3,
            "causal_attribution": (
                "NOT_ESTABLISHED_DUMP_RETAINED_NOT_YET_ANALYSED"
            ),
        },
        "pts_integrity": {
            "qualification_run_integrity": "VERIFIED",
            "canonical_file_identity_recorded": True,
            "pre_run_sha256": (
                "175f775560af7c17348c3d20cffc81ae"
                "5dc8d294d2486cc9e8409fbead8bc071"
            ),
            "post_run_sha256": (
                "175f775560af7c17348c3d20cffc81ae"
                "5dc8d294d2486cc9e8409fbead8bc071"
            ),
            "offline_containment": (
                "MANDATORY_PRE_PERSIST_GATE_DISPOSABLE_AND_CANONICAL_"
                "PRE_POST_SHA256_DUAL_RUNTIME_CRASH_BOUNDARY_SAMPLING_"
                "EXCLUSIVE_RESTORE_FAIL_CLOSED_TESTED"
            ),
        },
        "run_accounting": {
            "historical_live_runs_consumed_through_2026-09-03": 36,
            "direct_poe_runtime_sessions_after_historical_state": [
                "poe-e76063f692ec",
                "poe-d085610a5c94",
                "poe-e0da8048e559",
                "poe-29d64000dfb5",
                "poe-9d0d21961c1c",
                "poe-7950198d050f",
            ],
            "known_live_runs_consumed_lower_bound": 42,
            "current_total_exhaustive": False,
            "authority": "HISTORICAL_STATE_PLUS_DIRECT_RUNTIME_SNAPSHOTS",
        },
        "next_active_step": (
            "ATTRIBUTE_0XC0000005_POST_BOUNDARY_CRASH_"
            "BEFORE_ANY_ROUTER0_DECISION"
        ),
    }
    assert state["source_head"] == "6c6db55566890f1d9ca9cc06bfc13ae24505e793"
    assert re.fullmatch(r"[0-9a-f]{40}", state["source_head"])
    assert state["source_head_role"] == "latest_canonical_live_source"
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
    assert state["capabilities"] == {
        "stp_pvst": {
            "3560-24PS": "SUPPORTED",
            "2960-24TT": "SUPPORTED",
            "3650-24PS": "SUPPORTED",
        },
        "stp_edge": {
            "3560-24PS": "SUPPORTED",
            "2960-24TT": "UNKNOWN",
            "3650-24PS": "SUPPORTED",
        },
        "stp_state": {
            "3560-24PS": "SUPPORTED",
            "2960-24TT": "SUPPORTED",
            "3650-24PS": "SUPPORTED",
        },
        "stp_behavior": {
            "3560-24PS": "SUPPORTED",
            "2960-24TT": "SUPPORTED",
            "3650-24PS": "SUPPORTED",
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
    for key, expected in document["handoff_compatibility"].items():
        assert handoff[key] == expected

    assert document["handoff_compatibility"] == {
        "LIVE_RUNS_CONSUMED": (
            "AT_LEAST_42_NON_EXHAUSTIVE_AFTER_20260903"
        ),
        "CLEANUP": (
            "LATEST_POE_SEMANTIC_CLEANUP_4_OF_4 | "
            "PTS_INTEGRITY_VERIFIED | SESSION_REUSABLE"
        ),
        "WORKSPACE_RESTORED": (
            "SEMANTIC_INVENTORY_YES | PHYSICAL_PTS_VERIFIED"
        ),
        "NEXT_ACTIVE_STEP": (
            "ATTRIBUTE_0XC0000005_POST_BOUNDARY_CRASH_"
            "BEFORE_ANY_ROUTER0_DECISION"
        ),
        "CP_SCALE_STATUS": (
            "POE_DELIVERY_SUPPORTED_EXACT_BINDING_ONLY | "
            "LATEST_POE_EVIDENCE_VERIFIED | "
            "OBSERVER_PIPELINE_DELIVERED | "
            "PTS_GUARD_LIVE_VERIFIED | ROUTER0_NOT_AUTHORIZED"
        ),
    }
    assert "ROUTER0_CP_LIVE" not in document["handoff_compatibility"][
        "NEXT_ACTIVE_STEP"
    ]


def test_compact_current_state_evidence_paths_and_hashes_are_exact():
    document = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    state = document["last_live_state"]

    assert state["evidence"]
    for item in state["evidence"]:
        path = ROOT / item["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]

    poe = document["current_offline_operational_gate"][
        "latest_poe_qualification"
    ]
    artifact = poe["artifact"]
    path = ROOT / artifact["path"]
    assert path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
    evidence = json.loads(path.read_text(encoding="utf-8"))
    assert evidence["run_identity"] == "poe-7950198d050f"
    assert evidence["decision"] == "A — DELIVERY VERIFIED"
    assert evidence["claim_ceiling"] == {
        "supports_poe": "supported",
        "poe_ports": 1,
        "authorized_binding": {
            "candidate_model": "3560-24PS",
            "candidate_port": "FastEthernet0/1",
            "endpoint_model": "7960",
            "endpoint_port": "Switch",
        },
        "comparison_model": "2960-24TT",
        "port_extrapolation_allowed": False,
        "router0_authorized": False,
    }
    assert evidence["crash_finding"]["exception_code"] == "0xc0000005"
    assert evidence["crash_finding"]["poe_causation_claimed"] is False
    assert evidence["file_integrity"]["session_reusable"] is True

    # A crash proven after the governed boundary closed cannot retroactively
    # invalidate evidence that was already complete and persisted.
    boundary = evidence["temporal_boundary"]
    assert boundary["all_required_gates_closed_before_crash"] is True
    assert boundary["ordering_demonstrable"] is True
    crash = evidence["crash_finding"]
    assert crash["classification"] == "POST_BOUNDARY_RELIABILITY_INCIDENT"
    assert crash["invalidates_this_qualification"] is False

    # A dump exists for every occurrence, so attribution is open for want
    # of analysis, not for want of material.
    assert crash["dump"]["retained"] is True
    recurrence = crash["recurrence"]
    assert recurrence["occurrences"] == 3
    assert len(recurrence["correlated"]) == 3
    assert {item["run_identity"] for item in recurrence["correlated"]} == {
        "poe-29d64000dfb5", "poe-9d0d21961c1c", "poe-7950198d050f",
    }
    assert all(
        item["seconds_after_snapshot"] > 0
        for item in recurrence["correlated"]
    )
    assert recurrence["poe_causation_claimed"] is False
    persisted = next(
        item["at"] for item in boundary["sequence"]
        if item["gate"] == "decision_persisted"
    )
    assert persisted < crash["observed_at"]
