"""The first successful Router3 closure is hash-pinned and fully verified."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "reference" / "cp-scale" / "router3_successful_run.json"
RUN_ID = "canonical-cp-scale-voice-20260914T184407060316Z-d2245d45d442"
HEAD = "d2245d45d442d32f5dfb107b1a715089f1cb8551"
PRECLEANUP_SHA = "bb863238acaf8d0662e2a67482183c14b9aa852447135730a723efa09fd46427"
CLEANUP_SHA = "91120f40ce7cf18c10410f8cf141ba2d160345fa834f6b90d58b888a5b29ee1f"
STAGES = [
    "routing-core",
    "router4-switch10",
    "floor1",
    "floor2",
    "floor3",
    "router0-branch",
    "router3-branch",
]


def _artifact(index: dict, phase: str) -> tuple[Path, dict]:
    record = next(item for item in index["artifacts"] if item["phase"] == phase)
    path = ROOT / record["path"]
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == record["sha256"]
    return path, json.loads(raw)


def _assert_unique_dispatch_delta(ping: dict, expected_source: str) -> None:
    assert ping["attempts"] == 1
    assert ping["reachable"] is True
    assert ping["fresh_output_observed"] is True
    assert ping["failure_reason"] == ""
    assert ping["observed_device_name"] == expected_source
    assert ping["device_identity_provenance"] == "confirmed_unique"
    assert ping["device_identity_evidence"] == "dispatch_transcript_delta"
    assert ping["device_identity_candidate_evidence"] == (
        "dispatch_transcript_delta"
    )
    assert ping["device_identity_candidate_names"] == [expected_source]
    assert ping["device_identity_refusal"] == "none"


def test_router3_success_index_pins_complete_product_evidence() -> None:
    index = json.loads(INDEX.read_text(encoding="utf-8"))

    assert index == {
        "schema": "cp-scale-router3-successful-run-v1",
        "classification": "VERIFIED",
        "successful_closure": True,
        "run_identity": RUN_ID,
        "executed_sha": HEAD,
        "requested_target": "router3-branch",
        "closure": "ROUTER3_BRANCH_VERIFIED_AND_CLEANED",
        "artifacts": [
            {
                "phase": "precleanup",
                "path": (
                    "docs/reference/cp-scale/canonical-live-evidence/"
                    f"{RUN_ID}-precleanup.json"
                ),
                "sha256": PRECLEANUP_SHA,
            },
            {
                "phase": "cleanup",
                "path": (
                    "docs/reference/cp-scale/canonical-live-evidence/"
                    f"{RUN_ID}-cleanup.json"
                ),
                "sha256": CLEANUP_SHA,
            },
        ],
        "verified": {
            "stages": STAGES,
            "cumulative_devices": 314,
            "cumulative_links": 219,
            "configuration": "ACCEPTED_UNDER_GOVERNED_CEILINGS",
            "control_plane": "VERIFIED",
            "voice": "CANONICAL_COMPLETE_69_OF_69",
            "router_to_workload": "VERIFIED_4_OF_4",
            "pc_to_pc": "VERIFIED_4_OF_4",
            "typed_ping_authority": (
                "DISPATCH_TRANSCRIPT_DELTA_CONFIRMED_UNIQUE_8_OF_8"
            ),
            "floor3_stp_learning_extension": (
                "VERIFIED_AFTER_ONE_QUALIFIED_SIMULATION_TIME_EXTENSION"
            ),
            "mutation_replay": "NO_MUTATION_REPLAY",
            "workspace_readback": "VERIFIED_TWICE",
        },
        "cleanup": {
            "deleted_devices": 314,
            "first_semantic_devices": 0,
            "first_links": 0,
            "second_semantic_devices": 0,
            "second_links": 0,
            "realtime_restored": True,
        },
        "evidence_authority": "ROUTER3_SUCCESS",
    }

    _, precleanup = _artifact(index, "precleanup")
    _, cleanup = _artifact(index, "cleanup")
    assert precleanup["run_identity"] == cleanup["run_identity"] == RUN_ID
    assert precleanup["repository"]["head"] == cleanup["source_head"] == HEAD
    authorization = precleanup["router3_live_authorization"]
    assert {
        authorization["authorized_sha"],
        authorization["expected_head"],
        authorization["repository_head"],
        authorization["upstream_head"],
    } == {HEAD}
    assert authorization["authorized_target"] == "router3-branch"
    assert precleanup["target_stage"] == cleanup["target_stage"] == (
        "router3-branch"
    )
    assert precleanup["closure"] == "ROUTER3_BRANCH_VERIFIED_PRECLEANUP"
    assert cleanup["closure"] == "ROUTER3_BRANCH_VERIFIED_AND_CLEANED"
    assert precleanup["presentation_retained"] is False
    assert precleanup["baseline"]["observed"] is True
    assert precleanup["baseline"]["semantic_device_count"] == 0
    assert precleanup["baseline"]["link_count"] == 0
    assert [item["stage"] for item in precleanup["stages"]] == STAGES
    assert all(item["verified"] is True for item in precleanup["stages"])

    router3 = precleanup["stages"][-1]
    voice = router3["canonical_voice_verification"]
    assert router3["configuration_acceptance_error"] == ""
    assert router3["control_plane"]["status"] == "verified"
    assert voice["complete"] is True
    assert {
        "expected": voice["expected_phone_count"],
        "fwd": voice["phone_access_fwd_verified"],
        "addressed": voice["addressed_count"],
        "bindings": voice["matching_binding_count"],
        "registered": voice["sccp_registered_count"],
    } == {
        "expected": 69,
        "fwd": 69,
        "addressed": 69,
        "bindings": 69,
        "registered": 69,
    }

    assert router3["site_forwarding_verified"] is True
    assert router3["user_forwarding_verified"] is True
    assert len(router3["site_forwarding"]) == 4
    assert len(router3["user_forwarding"]) == 4
    for observation in router3["site_forwarding"]:
        assert observation["verified"] is True
        _assert_unique_dispatch_delta(
            observation["result"],
            observation["check"]["source_device_name"],
        )
    for observation in router3["user_forwarding"]:
        assert observation["status"] == "verified"
        assert observation["verified"] is True
        assert observation["error"] == ""
        assert len(observation["attempts"]) == 1
        source = observation["source_binding"]["target"]["runtime_device_name"]
        _assert_unique_dispatch_delta(observation["attempts"][0], source)
        for binding in (
            observation["source_binding"],
            observation["destination_binding"],
        ):
            assert binding["fresh_evidence"] is True
            assert binding["target"]["runtime_link_identity_observed"] is True

    large_to_small = next(
        item for item in router3["user_forwarding"]
        if item["check"]["direction"] == "large-branch-pc-to-small-branch-pc"
    )
    _assert_unique_dispatch_delta(
        large_to_small["attempts"][0],
        "LARGE-BRANCH-CAMPUS-FLOOR-1-ZONE-A-PC-01",
    )

    floor3 = next(item for item in precleanup["stages"] if item["stage"] == "floor3")
    extension = next(
        item for item in floor3["control_plane"]["behavior_results"]
        if item["action_id"] == "cp/stp/2497111a0645b91e"
    )
    details = extension["convergence"]["details"]
    assert extension["status"] == "verified"
    assert extension["convergence"]["attempts"] == 24
    assert details["learning_extension_authorized"] is True
    assert details["learning_extension_clock"] == "packet_tracer_simulation_time"
    assert details["learning_extension_seconds"] == 20.0
    assert details["learning_extension_outcome"] == "converged"
    assert details["learning_extension_stop_reason"] == "converged"
    assert 0 < details["learning_extension_simulation_progress_ms"] <= 20_000

    assert precleanup["no_mutation_replay"] == cleanup["no_mutation_replay"]
    assert cleanup["no_mutation_replay"] == {
        "audited_stages": STAGES,
        "claim": "NO_MUTATION_REPLAY",
        "replayed_retained_ids": [],
        "stages_without_verified_audit": [],
        "verified": True,
    }
    assert router3["workspace_verified_twice"] is True
    assert cleanup["cleanup"]["verified"] is True
    assert len(cleanup["cleanup"]["mutations"]) == 314
    for observation in (cleanup["cleanup"]["first"], cleanup["cleanup"]["second"]):
        assert observation["observed"] is True
        assert observation["semantic_device_count"] == 0
        assert observation["link_count"] == 0
    assert cleanup["cleanup_realtime"]["verified"] is True
    assert cleanup["cleanup_realtime"]["state"]["simulation_mode"] is False
