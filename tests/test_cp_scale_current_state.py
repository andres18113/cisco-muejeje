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


def test_router0_poe_observer_failure_does_not_promote_or_consume_router0():
    document = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    acquisition = document["current_offline_operational_gate"]["router0_poe_acquisition"]
    artifact_path = ROOT / acquisition["prior_artifact"]["path"]
    raw = artifact_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == acquisition["prior_artifact"]["sha256"]
    artifact = json.loads(raw)
    result = artifact["result"]
    assert artifact["router0_attempts_consumed"] == 0
    assert artifact["physical_limitation_established"] is False
    assert result["observation"] is None
    assert result["capability_result"]["status"] == "unknown"
    assert result["capability_result"]["verified"] is False
    assert result["inventory_restored"] is True
    assert result["cleanup_status"] == "clean"
    assert len(result["attempted_identities"]) == len(result["deleted_identities"]) == 6
    assert result["cleanup_failed"] == []
    assert result["live_session_safety"]["integrity_verified"] is True
    assert result["live_session_safety"]["crash_detected"] is False
    assert artifact["closure"]["realtime"]["simulation_mode"] is False


def test_later_acquisitions_and_late_images_cannot_retroactively_promote_poe():
    document = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    gate = document["current_offline_operational_gate"]
    reference = gate["router0_poe_acquisition"]["artifact"]
    raw = (ROOT / reference["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == reference["sha256"]
    artifact = json.loads(raw)
    assert artifact["router0_attempts_consumed"] == 0
    assert artifact["router3_executed"] is False
    assert artifact["physical_incapability_established"] is False
    assert [item["run_id"] for item in artifact["episodes"]] == [
        "r0poe-mls4-6ffe810b", "r0poe-mls6-07e15945", "r0poe-mls6-df79fafe",
    ]
    for episode, count in zip(artifact["episodes"], (6, 4, 4), strict=True):
        result = episode["result"]
        assert result["observation"] is None
        assert result["observation_status"] == "unobservable"
        assert result["capability_result"]["status"] == "unknown"
        assert result["capability_result"]["verified"] is False
        assert result["cleanup_status"] == "clean"
        assert result["inventory_restored"] is True
        assert result["cleanup_failed"] == []
        assert len(result["attempted_identities"]) == count
        assert len(result["deleted_identities"]) == count
        assert result["live_session_safety"]["integrity_verified"] is True
        assert result["live_session_safety"]["crash_detected"] is False
        assert episode["closure"]["realtime"]["simulation_mode"] is False
        assert episode["closure"]["workspace"]["links"] == []
        assert episode["closure"]["product_admission"] is False
        assert "poe-" + episode["run_id"] in gate["run_accounting"][
            "direct_poe_runtime_sessions_after_historical_state"
        ]
        checks = episode["preflight"]["actions"]
        assert len(checks) == 4
        assert all(check["conclusion"] == "success" for check in checks)
        assert all(check["head_sha"] == episode["preflight"]["source_sha"] for check in checks)
        assert episode["preflight"]["namespaces"] == ["packet_tracer_mcp"]
    review = artifact["late_review"]
    assert review["governed_observation_delivered"] is False
    assert review["retroactive_poe_promotion_allowed"] is False
    assert review["physical_incapability_established"] is False
    assert review["operator_attestation"]["does_not_replace_in_boundary_receipt"] is True
    for image in review["images"]:
        image_path = ROOT / review["archived_image_directory"] / image["file"]
        assert hashlib.sha256(image_path.read_bytes()).hexdigest() == image["sha256"]
    assert len(review["images"]) == 6
    assert gate["poe_ports"] == 1
    assert gate["latest_verified_poe_qualification"]["run_identity"] == "poe-7950198d050f"


def test_compact_current_state_is_bounded_and_matches_the_handoff_projection():
    raw = STATE_PATH.read_bytes()
    document = json.loads(raw)

    assert document["schema"] == "cp-scale-current-state-v2"
    # One more governed decision -- the observed access-point differential --
    # earns its place here. The bound still exists so this stays an index of
    # decisions with hash-pinned artifacts, not a place to inline evidence.
    assert len(raw) < 20_480
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
        "source_head": "247294b619dfd7805a542a27019d3f78f94713c0",
        "source_head_role": "read_only_router0_product_admission_source",
        "poe_delivery": "supported",
        "poe_ports": 1,
        "hardware_plan": "unresolved",
        "canonical_composition": "blocked_before_topology",
        "router0_authorized": True,
        "router0_precondition": {
            "decision": "PRECONDITION_BLOCKED",
            "operator_authorization": "RUN_ONE_GOVERNED_ROUTER0_CP_LIVE_WITH_ASTRA",
            "attempts_authorized": 1,
            "attempts_consumed": 0,
            "product_admitted": False,
            "live_run_id": None,
            "packet_tracer_mutations": 0,
            "first_contradicted_boundary": "PRODUCT_HARDWARE_POE_ADMISSION_BEFORE_TOPOLOGY",
            "crash_attribution_prerequisite_superseded": True,
            "live_environment_checks": "NOT_REACHED_PRODUCT_ADMISSION_REFUSED",
            "artifact": {
                "path": (
                    "docs/reference/cp-scale/prelive-evidence/"
                    "router0-precondition-20260906T195307168481Z-247294b619df.json"
                ),
                "sha256": "6e2e46376debb1e0cdc5a63de8b501bb9ddcd85c8281ec6d36a53c2f8dd99fab",
            },
        },
        "router0_poe_acquisition": {
            "operator_authorization": "ACQUIRE_ROUTER0_POE_EVIDENCE_THEN_RUN_ROUTER0",
            "latest_attempt": "r0poe-mls6-df79fafe",
            "result": "OBSERVER_UNOBSERVABLE_NO_POE_PROMOTION",
            "physical_limitation_established": False,
            "cleanup": "4_OF_4_SEMANTIC_INVENTORY_AND_REALTIME_RESTORED",
            "file_runtime_safety": "VERIFIED_NO_CRASH",
            "artifact": {
                "path": "docs/reference/cp-scale/canonical-live-evidence/poe-acquisition-20260906T211432-df79fafe-diagnostic.json",
                "sha256": "4c757ed701c3f69ef01b6e2a774698da2b09415ae68a5af7bdd2aeaa1859fe87",
            },
            "prior_artifact": {
                "path": "docs/reference/cp-scale/canonical-live-evidence/poe-acquisition-20260906T202735-b4810d48-unobservable.json",
                "sha256": "f26cbe1ab1c2b254b5da73aba285086982b68aa8c7022a38443ad29b0e2640c8",
            },
            "continuation": "ACCESSPOINT_PT_HAS_NO_REMOVABLE_POWER_ADAPTER_SO_NO_WITHHOLDABLE_SUPPLY",
        },
        "accesspoint_differential": {
            "run_id": "r0poe-mls6-a1e7aa15",
            "source_head": "c4f909ca13e289fd91c6be243de5258c1a2f29d8",
            "decision": "OBSERVED_BOTH_ARMS_POWERED_NO_POE_PROMOTION",
            "observation_status": "observed",
            "verification_status": "failed",
            "capability_status": "unknown",
            "physical_incapability_established": False,
            "unqualifiable_accesspoint_bindings": 11,
            "inline_power_api_signal": "ABSENT_IN_9_0_1_IPCAPI_REFERENCE",
            "next_observable_candidate": (
                "SWITCH_SIDE_SHOW_POWER_INLINE_VIA_REGISTERED_IOS_QUERY_"
                "CALIBRATED_POE1"
            ),
            "artifact": {
                "path": (
                    "docs/reference/cp-scale/canonical-live-evidence/"
                    "poe-accesspoint-differential-20260907T024424Z-"
                    "c4f909ca13e2-observed.json"
                ),
                "sha256": (
                    "7f28f575aee4512bd41dc51b42e00fd0"
                    "9b06dbf6e80d96c1a9022fb40fc2812a"
                ),
            },
            "record": (
                "docs/reference/cp-scale/POE_ACCESSPOINT_DIFFERENTIAL_20260907.md"
            ),
        },
        "poe_inline_observable": {
            "run_id": "poe1-c4fae886",
            "source_head": "1d8b568",
            "packet_tracer_build": "9.0.1.0858",
            "decision": "OBSERVABLE_CALIBRATED_NO_CAPABILITY_PROMOTION",
            "execution_path": "REUSED_GOVERNED_IOS_QUALIFICATION_NO_RAW_CLI",
            "candidate_command": "show power inline",
            "calibration_binding": "3560-24PS/FastEthernet0/1 + 7960/Switch",
            "external_phone_power_adapter": False,
            "causal_signature": {
                "auto_1": (
                    "ROW_PRESENT_OPER_ON_POWER_10_0_DEVICE_IP_PHONE_7960_CLASS_3"
                ),
                "never": "ROW_ABSENT_FROM_COMPLETE_TABLE",
                "auto_2": "ROW_PRESENT_IDENTICAL_TO_AUTO_1",
                "reversible": True,
            },
            "contradicted_expectation": "NEVER_IS_ROW_ABSENCE_NOT_OPER_OFF",
            "summary_line_is_authority": False,
            "port_up_is_authority": False,
            "captures_attributable": 4,
            "pager_qualified": True,
            "claim_authority": {
                "authorized_observation_methods_unchanged": True,
                "promotes_candidate_to_product_registry": False,
                "poe_ports_extrapolated": False,
                "port_coverage_authorized": 0,
            },
            "restoration": {
                "power_inline_auto_restored": True,
                "restoration_proved_by_readback": True,
                "disposable_deleted": True,
                "session_residue_retired": ["Power Distribution Device1"],
                "inventory_restored": True,
                "realtime_restored": True,
                "problems": [],
            },
            "artifact": {
                "path": (
                    "docs/reference/cp-scale/canonical-live-evidence/"
                    "poe-inline-calibration-poe1-c4fae886.json"
                ),
                "sha256": (
                    "b13cad40901a94b957bc6738207e5a8b"
                    "9505258e96662d3e190b7b3b7e9be104"
                ),
            },
            "prior_attempt": {
                "run_id": "poe1-4d342a1a",
                "result": (
                    "RESTORATION_INCOMPLETE_SESSION_RESIDUE_NOT_RETIRED"
                ),
                "path": (
                    "docs/reference/cp-scale/canonical-live-evidence/"
                    "poe-inline-calibration-poe1-4d342a1a.json"
                ),
            },
            "productive_api": {
                "entry_point": (
                    "GovernedPoEInlineObserver.observe_poe_inline_status"
                ),
                "accepts": (
                    "EXACT_SWITCH_IDENTITY_AND_EXACT_EXPECTED_PORTS_ONLY"
                ),
                "accepts_ios_or_javascript": False,
                "end_to_end_run_id": "poe1-c5626851",
                "end_to_end_source_head": "1e145e8",
                "api_matched_raw_text_in_every_state": True,
                "refusals": 0,
                "interface_abbreviation_defect": (
                    "FOUND_AND_FIXED_PT_PRINTS_FA0_1_REPO_USES_"
                    "FASTETHERNET0_1"
                ),
                "artifact": {
                    "path": (
                        "docs/reference/cp-scale/canonical-live-evidence/"
                        "poe-inline-calibration-poe1-c5626851.json"
                    ),
                    "sha256": (
                        "f870b200d14e79c6a11bd656664f543f"
                        "a5b91da9c41ab6310cf1ff3cd4584dd8"
                    ),
                },
            },
            "record": (
                "docs/reference/cp-scale/POE_INLINE_CALIBRATION_20260907.md"
            ),
        },
        "factory_structure_survey": {
            "run_id": "factory-survey-9f967ef6",
            "source_head": "cf89481fa3eaf9efd46c2778cb33b789d2e1197d",
            "decision": "FACTORY_STRUCTURE_OBSERVED_NO_CAPABILITY_PROMOTION",
            "pt_mutations": 0,
            "capability_promotion": "NONE",
            "removable_power_adapter_supported": {
                "7960": True, "AccessPoint-PT": False,
            },
            "registered_device_type": {"3560-24PS": 16, "3650-24PS": 16},
            "physical_incapability_established": False,
            "artifact": {
                "path": (
                    "docs/reference/cp-scale/canonical-live-evidence/"
                    "factory-structure-20260907T003018Z-cf89481fa3ea-observed.json"
                ),
                "sha256": (
                    "fa5747e56dfa000d6cc3e2c2bdd57ebf"
                    "33e34b8cfddd109ed34299394220937a"
                ),
            },
            "access_point_family": {
                "run_id": "factory-survey-102006c6",
                "generic_ap_models_observed": 4,
                "adaptor_31_supported_by_any": False,
                "artifact": {
                    "path": (
                        "docs/reference/cp-scale/canonical-live-evidence/"
                        "factory-structure-20260907T005226Z-86c75f1c304c-"
                        "accesspoint-family.json"
                    ),
                    "sha256": (
                        "5549a9a30da2eda5aba4c8bae89279b4"
                        "13399073f9dcf396d5639cb41a7463c0"
                    ),
                },
            },
        },
        "latest_verified_poe_qualification": {
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
            "finding_run_identity": "poe-7950198d050f",
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
                "poe-r0poe-mls4-b4810d48",
                "poe-r0poe-mls4-6ffe810b",
                "poe-r0poe-mls6-07e15945",
                "poe-r0poe-mls6-df79fafe",
                "poe-r0poe-mls6-a1e7aa15",
            ],
            "known_live_runs_consumed_lower_bound": 47,
            "current_total_exhaustive": False,
            "authority": "HISTORICAL_STATE_PLUS_DIRECT_RUNTIME_SNAPSHOTS",
        },
        "next_active_step": (
            "POE2_ACCESSPOINT_PT_USING_THE_CALIBRATED_PSE_OBSERVABLE"
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
        "post_ledger_failed_run_bundles": {
            "path": "docs/reference/cp-scale/router0_failed_run_bundles.json",
            "sha256": (
                "e5f0ed8379708e050f68bd2be0d8888c"
                "526ca6f5bac2da1191b900ca3fdbe6f2"
            ),
            "run_count": 6,
            "classification": "FAILED",
            "successful_closure": False,
        },
    }
    assert state["unresolved_debt"] == []

    handoff = parse_handoff_state(HANDOFF_PATH.read_text(encoding="utf-8"))
    assert state["handoff_compatibility"]
    for key, expected in document["handoff_compatibility"].items():
        assert handoff[key] == expected

    assert document["handoff_compatibility"] == {
        "LIVE_RUNS_CONSUMED": (
            "AT_LEAST_46_NON_EXHAUSTIVE_AFTER_20260903"
        ),
        "CLEANUP": (
            "LATEST_POE_ACQUISITION_CLEANUP_4_OF_4 | "
            "PTS_INTEGRITY_VERIFIED | SESSION_REUSABLE"
        ),
        "WORKSPACE_RESTORED": (
            "SEMANTIC_INVENTORY_YES | PHYSICAL_PTS_VERIFIED"
        ),
        "NEXT_ACTIVE_STEP": (
            "POE2_ACCESSPOINT_PT_USING_THE_CALIBRATED_PSE_OBSERVABLE"
        ),
        # La proyeccion nombra el observable calibrado junto con las dos cosas
        # que la calibracion contradijo, para que nadie lea la firma de memoria.
        "POE_INLINE_OBSERVABLE": (
            "CALIBRATED_EXACT_BINDING_3560_24PS_FA0_1_7960_SWITCH | "
            "NEVER_IS_ROW_ABSENCE | SUMMARY_NOT_AUTHORITY | "
            "NO_PORT_EXTRAPOLATION"
        ),
        "CP_SCALE_STATUS": (
            "PRIOR_POE_EXACT_BINDING_VERIFIED | "
            "FACTORY_STRUCTURE_OBSERVED_NO_PROMOTION | "
            "ROUTER0_OPERATOR_AUTHORIZED_ONE_UNCONSUMED | "
            "PRODUCT_PRECONDITION_BLOCKED"
        ),
    }
    assert "ROUTER0_CP_LIVE" not in document["handoff_compatibility"][
        "NEXT_ACTIVE_STEP"
    ]


def test_router0_precondition_retains_product_refusal_without_consuming_live():
    document = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    gate = document["current_offline_operational_gate"]
    admission = gate["router0_precondition"]
    artifact = admission["artifact"]
    raw = (ROOT / artifact["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == artifact["sha256"]
    evidence = json.loads(raw)

    assert evidence["schema"] == "cp-scale-router0-precondition-v1"
    assert evidence["source_head"] == gate["source_head"]
    assert evidence["decision"] == admission["decision"] == "PRECONDITION_BLOCKED"
    assert evidence["live_run_id"] is None
    assert evidence["operator_authorization"]["attempts_authorized"] == 1
    assert evidence["operator_authorization"]["attempts_consumed"] == 0
    assert evidence["operator_authorization"]["router3_authorized"] is False
    assert all(value == 0 for value in evidence["mutation_delta"].values())

    product = evidence["product_admission"]
    assert product["valid"] is False
    assert product["hardware_plan"] == gate["hardware_plan"] == "unresolved"
    for key in (
        "topology_materialized", "configuration_materialized",
        "control_plane_materialized", "voice_materialized",
    ):
        assert product[key] is False
    assert product["router0_projection_error"] == (
        "A complete canonical composition is required."
    )
    assert product["documentary_router0_authorized_field_read_by_entrypoint"] is False
    assert "insufficient_evidence" in product["issues"][0]

    capabilities = evidence["effective_poe_capabilities"]
    assert capabilities["3560-24PS"] == {
        "supports_poe": "supported", "poe_ports": 1,
        "authorized_bindings": [{
            "switch_port": "FastEthernet0/1",
            "endpoint_model": "7960", "endpoint_port": "Switch",
        }],
    }
    assert capabilities["3650-24PS"] == {
        "supports_poe": "unknown", "poe_ports": None, "authorized_bindings": [],
    }
    contracts = {
        item["device_name"]: item for item in evidence["exact_missing_contracts"]
    }
    assert contracts["MLS3"]["required_simultaneous_ports"] == 12
    assert contracts["MLS4"]["required_simultaneous_ports"] == 2
    assert contracts["MLS5"]["required_simultaneous_ports"] == 8
    assert contracts["MLS6"]["missing_exact_bindings"] == [{
        "endpoint_model": "AccessPoint-PT", "endpoint_port": "Port 0",
        "switch_ports": ["FastEthernet0/13"],
    }]
    assert contracts["Switch3"]["router0_cumulative_scope"] is False
    assert evidence["router0_scope"]["compiled_topology_counts"] is None
    assert evidence["router0_scope"]["historical_counts_used_as_authority"] is False

    prelive = evidence["pre_live_state"]
    assert prelive["clean_worktree"] is True
    assert prelive["remote_head"] == evidence["source_head"]
    assert prelive["import_isolation"] == "ISOLATED"
    assert prelive["loaded_namespaces"] == ["packet_tracer_mcp"]
    assert len(prelive["github_actions"]) == 4
    assert all(
        check["head_sha"] == evidence["source_head"]
        and check["status"] == "completed" and check["conclusion"] == "success"
        for check in prelive["github_actions"]
    )
    assert evidence["prior_live_state"] == "UNCHANGED"
    # The artifact is sealed and hash-pinned, so it keeps the step that was
    # next when its boundary closed. Tying it to the live gate would have made
    # every later advance require rewriting evidence that must not change.
    assert evidence["next_active_step"] == (
        "OBTAIN_GOVERNED_EXACT_POE_BINDING_AND_"
        "SIMULTANEOUS_CAPACITY_EVIDENCE_BEFORE_ROUTER0"
    )
    assert gate["next_active_step"] == (
        "POE2_ACCESSPOINT_PT_USING_THE_CALIBRATED_PSE_OBSERVABLE"
    )


def test_compact_current_state_evidence_paths_and_hashes_are_exact():
    document = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    state = document["last_live_state"]

    assert state["evidence"]
    for item in state["evidence"]:
        path = ROOT / item["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]

    poe = document["current_offline_operational_gate"][
        "latest_verified_poe_qualification"
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


def test_factory_structure_evidence_observes_without_promoting_anything():
    """Reading Packet Tracer's own descriptors changes no capability."""
    document = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    gate = document["current_offline_operational_gate"]
    survey = gate["factory_structure_survey"]

    raw = (ROOT / survey["artifact"]["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == survey["artifact"]["sha256"]
    artifact = json.loads(raw)

    assert artifact["evidence_role"] == "FACTORY_STRUCTURE_ONLY_NOT_POWER_DELIVERY"
    assert artifact["pt_mutations"] == 0
    assert artifact["qualifications"] == 0
    assert artifact["router0_attempts_consumed"] == 0
    assert artifact["router3_executed"] is False
    assert artifact["physical_incapability_established"] is False
    assert artifact["capability_promotion"] == "NONE"
    assert artifact["poe_ports_changed"] is False

    # The read stayed inside a clean, CI-green boundary that touched nothing.
    assert artifact["source"]["head"] == survey["source_head"]
    assert artifact["source"]["status"] == ""
    assert artifact["source"]["branch"] == "feature/runtime-ripv2"
    assert artifact["canonical_pts"]["unchanged"] is True
    assert artifact["bridge_before"]["unauth_count"] == 0
    assert artifact["workspace_before"]["devices"] == []
    assert artifact["workspace_after"]["devices"] == []
    assert artifact["realtime_after"]["simulation_mode"] is False

    # The measured contrast: the endpoint model that already qualified has a
    # withholdable supply, and the access point has none of any documented type.
    observations = artifact["observations"]
    assert observations["7960#mt11#dtNone#d1"]["module_type_supported"] is True
    assert observations["7960#mt31#dtNone#d1"]["module_type_supported"] is False
    assert observations["AccessPoint-PT#mt31#dtNone#dNone"][
        "module_type_supported"
    ] is False
    assert observations["AccessPoint-PT#mt11#dtNone#d1"][
        "module_type_supported"
    ] is False

    # Both PoE switches answer only under eMultiLayerSwitch.
    for key in ("3560-24PS#mt4#dt16#d1", "3650-24PS#mt4#dt16#d1"):
        assert observations[key]["device_type"] == 16
    assert observations["3650-24PS#mt4#dt16#d1"]["module_type_supported"] is True
    assert observations["3560-24PS#mt4#dt16#d1"]["module_type_supported"] is False

    # Nothing here may move the authorized ceiling.
    assert gate["poe_ports"] == 1
    assert gate["hardware_plan"] == "unresolved"
    assert gate["router0_precondition"]["attempts_consumed"] == 0


def test_no_generic_access_point_model_accepts_the_power_adaptor():
    """The refusal is a property of the family, not of the bound model."""
    document = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    family = document["current_offline_operational_gate"][
        "factory_structure_survey"
    ]["access_point_family"]

    raw = (ROOT / family["artifact"]["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == family["artifact"]["sha256"]
    artifact = json.loads(raw)

    assert artifact["pt_mutations"] == 0
    assert artifact["router0_attempts_consumed"] == 0
    assert artifact["capability_promotion"] == "NONE"
    assert artifact["physical_incapability_established"] is False
    assert artifact["canonical_pts"]["unchanged"] is True
    assert artifact["source"]["status"] == ""

    supported = artifact["findings"]["adaptor_31_supported"]
    assert set(supported) == {
        "AccessPoint-PT", "AccessPoint-PT-A",
        "AccessPoint-PT-N", "AccessPoint-PT-AC",
    }
    assert not any(supported.values())
    assert len(supported) == family["generic_ap_models_observed"]
    for key, observation in artifact["observations"].items():
        assert observation["module_type_supported"] is False, key
        assert observation["queried_module_type"] == 31

    # A model the factory does not answer for is unobservable, never a
    # measured absence, and none of them is bound by the physical design.
    assert artifact["findings"]["no_descriptor_under_eaccesspoint"] == [
        "LAP-PT", "3702i", "802", "803",
    ]
    assert set(artifact["errors"]) == {
        "LAP-PT#mt31#dtNone#d1", "3702i#mt31#dtNone#d1",
        "802#mt31#dtNone#d1", "803#mt31#dtNone#d1",
    }


def test_observed_accesspoint_differential_cannot_promote_or_refuse_poe():
    # Both arms powered is a determinate reading, not a missing one, and it is
    # the reason the eleven AccessPoint-PT bindings stay uncovered. It must not
    # drift into a PoE positive, and it must not drift into UNSUPPORTED either:
    # an endpoint that is lit without inline power says nothing about whether
    # the switch delivers any.
    document = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    gate = document["current_offline_operational_gate"]
    record = gate["accesspoint_differential"]
    raw = (ROOT / record["artifact"]["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == record["artifact"]["sha256"]
    artifact = json.loads(raw)

    assert artifact["router0_attempts_consumed"] == 0
    assert artifact["router3_executed"] is False
    assert artifact["physical_incapability_established"] is False
    assert artifact["request"]["candidate_model"] == "3560-24PS"
    assert artifact["request"]["comparison_model"] == "2960-24TT"
    assert artifact["request"]["bindings"] == [{
        "candidate_port": "FastEthernet0/13",
        "comparison_port": "FastEthernet0/1",
        "endpoint_model": "AccessPoint-PT",
        "endpoint_port": "Port 0",
    }]

    observation = artifact["observation"]
    assert observation is not None
    assert observation["method"] == "manual_visible_power_state"
    assert observation["simultaneous"] is True
    assert observation["observer_id"].strip() == observation["observer_id"]
    assert len(observation["bindings"]) == 1
    arms = observation["bindings"][0]
    assert arms["candidate"]["state"] == "powered"
    assert arms["comparison"]["state"] == "powered"
    for arm in (arms["candidate"], arms["comparison"]):
        assert arm["state"] != "unobservable"
        assert arm["visible_indicator"].strip()
        assert arm["switch_ready"] and arm["link_ready"] and arm["endpoint_settled"]

    outcome = artifact["outcome"]
    assert outcome["observation_status"] == "observed"
    assert outcome["verification_status"] == "failed"
    assert outcome["capability_status"] == "unknown"
    assert outcome["capability_verified"] is False
    assert outcome["observed_value"] is None

    cleanup = artifact["cleanup"]
    assert cleanup["cleanup_status"] == "clean"
    assert cleanup["inventory_restored"] is True
    assert cleanup["cleanup_failed"] == []
    assert sorted(cleanup["attempted_identities"]) == sorted(cleanup["deleted_identities"])
    assert len(cleanup["attempted_identities"]) == 4
    safety = artifact["live_session_safety"]
    assert safety["integrity_verified"] is True
    assert safety["crash_detected"] is False
    assert safety["unexpected_canonical_modification"] is False
    assert artifact["closure"]["product_admission"] is False
    assert artifact["closure"]["realtime"]["simulation_mode"] is False

    assert gate["poe_ports"] == 1
    assert gate["poe_delivery"] == "supported"
    assert record["capability_status"] == "unknown"
    assert record["physical_incapability_established"] is False
    # POE-1 examined the switch-side candidate, so the field now says so. What
    # it must still NOT say is that calibrating it moved any PoE claim: the
    # AccessPoint reading stays `unknown` and the ceiling stays where it was.
    assert record["next_observable_candidate"].endswith("CALIBRATED_POE1")
    assert (ROOT / record["record"]).is_file()


def test_calibrating_the_inline_observable_promotes_no_capability():
    """Calibrar un observable no es autorizar un reclamo con el.

    La secuencia causal salio como se esperaba y aun asi nada sube: el metodo
    de observacion autorizado sigue siendo solo el visual, el candidato sigue
    fuera del registro de producto, y `poe_ports` sigue en 1 sin extrapolar.
    """
    document = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    gate = document["current_offline_operational_gate"]
    record = gate["poe_inline_observable"]

    raw = (ROOT / record["artifact"]["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == record["artifact"]["sha256"]
    artifact = json.loads(raw)

    assert artifact["problems"] == []
    assert artifact["binding"]["candidate_model"] == "3560-24PS"
    assert artifact["binding"]["switch_port"] == "FastEthernet0/1"
    assert artifact["binding"]["endpoint_model"] == "7960"
    assert artifact["binding"]["external_phone_power_adapter"] is False
    assert artifact["facts"]["inventory_restored"] is True
    assert artifact["facts"]["realtime_restored"] is True
    assert artifact["facts"]["environment_after"]["simulation_mode"] is False

    captures = {item["label"]: item for item in artifact["captures"]}
    assert set(captures) == {"as_created", "auto_1", "never", "auto_2"}
    for capture in captures.values():
        assert capture["attributable"] is True
        assert capture["stable"] is True
        assert capture["output_complete"] is True
        assert capture["device_identity_provenance"] == "confirmed_unique"

    powered_row = (
        "Fa0/1     auto   on         10.0    IP Phone 7960       3     15.4"
    )
    assert powered_row in captures["auto_1"]["output"]
    assert powered_row in captures["auto_2"]["output"]
    # La mitad negativa es una AUSENCIA, no una fila en `off`.
    assert "Fa0/1 " not in captures["never"]["output"]
    assert "off" in captures["never"]["output"]

    claim = artifact["claim_authority"]
    assert claim["authorized_observation_methods_unchanged"] is True
    assert claim["poe_ports_extrapolated"] is False
    assert claim["promotes_candidate_to_product_registry"] is False
    assert record["claim_authority"]["port_coverage_authorized"] == 0
    assert gate["poe_ports"] == 1
    assert gate["poe_delivery"] == "supported"
    assert (ROOT / record["record"]).is_file()


def test_the_productive_api_agreed_with_the_raw_text_in_every_live_state():
    """El observador corrio en vivo y no reinterpretó: coincidió.

    Su conclusion se guarda AL LADO del texto, no en su lugar, justamente para
    que una divergencia sea visible. Este test la buscaría.
    """
    document = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    api = document["current_offline_operational_gate"]["poe_inline_observable"][
        "productive_api"
    ]
    assert api["accepts_ios_or_javascript"] is False

    raw = (ROOT / api["artifact"]["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == api["artifact"]["sha256"]
    artifact = json.loads(raw)
    assert artifact["problems"] == []
    assert artifact["facts"]["inventory_restored"] is True
    assert artifact["facts"]["realtime_restored"] is True

    powered = "Fa0/1     auto   on         10.0    IP Phone 7960       3     15.4"
    for capture in artifact["captures"]:
        assert capture["observed_status"] == "observed"
        assert capture["observed_refusal_reason"] == ""
        assert capture["output_complete"] is True
        # Lo que dice la tabla, leido sin el parser, contra lo que concluyo la
        # API desde su propio despacho.
        row_present = powered in capture["output"]
        expected = "delivering" if row_present else "not_delivering"
        assert capture["observed_delivery"] == expected, capture["label"]

    by_label = {item["label"]: item for item in artifact["captures"]}
    assert by_label["auto_1"]["observed_delivery"] == "delivering"
    assert by_label["never"]["observed_delivery"] == "not_delivering"
    assert by_label["auto_2"]["observed_delivery"] == "delivering"
