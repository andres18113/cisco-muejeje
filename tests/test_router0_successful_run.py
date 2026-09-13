"""The first successful Router0 closure is hash-pinned and fully verified."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "reference" / "cp-scale" / "router0_successful_run.json"
STATE = ROOT / "docs" / "reference" / "cp-scale" / "current_state.json"
RUN_ID = "canonical-cp-scale-voice-20260913T142038552603Z-8980ada7ab99"
HEAD = "8980ada7ab993cbe5b5b915cefde24deb04b3e3f"
PRECLEANUP_SHA = "5c5e0478045144e3b35d500cf79d86af7f0f10853655003621c493046196fe05"
CLEANUP_SHA = "99f714f56a30decf547126300db28d7889c71e56fb0cea12720b74162e9f43f4"
STAGES = [
    "routing-core",
    "router4-switch10",
    "floor1",
    "floor2",
    "floor3",
    "router0-branch",
]


def _artifact(index: dict, phase: str) -> tuple[Path, dict]:
    record = next(item for item in index["artifacts"] if item["phase"] == phase)
    path = ROOT / record["path"]
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == record["sha256"]
    return path, json.loads(raw)


def test_router0_success_index_pins_complete_product_evidence() -> None:
    index = json.loads(INDEX.read_text(encoding="utf-8"))

    assert index == {
        "schema": "cp-scale-router0-successful-run-v1",
        "classification": "VERIFIED",
        "successful_closure": True,
        "run_identity": RUN_ID,
        "executed_sha": HEAD,
        "requested_target": "router0-branch",
        "closure": "ROUTER0_BRANCH_VERIFIED_AND_CLEANED",
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
            "cumulative_devices": 290,
            "cumulative_links": 202,
            "configuration": "ACCEPTED_UNDER_GOVERNED_CEILINGS",
            "control_plane": "VERIFIED",
            "voice": "CANONICAL_COMPLETE_62_OF_62",
            "router_to_workload": "VERIFIED_2_OF_2",
            "pc_to_pc": "VERIFIED_2_OF_2",
            "mutation_replay": "NO_MUTATION_REPLAY",
            "workspace_readback": "VERIFIED_TWICE",
        },
        "cleanup": {
            "deleted_devices": 290,
            "first_semantic_devices": 0,
            "first_links": 0,
            "second_semantic_devices": 0,
            "second_links": 0,
            "realtime_restored": True,
        },
        "evidence_authority": "ROUTER0_SUCCESS",
    }

    _, precleanup = _artifact(index, "precleanup")
    _, cleanup = _artifact(index, "cleanup")
    assert precleanup["run_identity"] == cleanup["run_identity"] == RUN_ID
    assert precleanup["repository"]["head"] == cleanup["source_head"] == HEAD
    assert precleanup["target_stage"] == cleanup["target_stage"] == "router0-branch"
    assert precleanup["closure"] == "ROUTER0_BRANCH_VERIFIED_PRECLEANUP"
    assert cleanup["closure"] == "ROUTER0_BRANCH_VERIFIED_AND_CLEANED"
    assert [item["stage"] for item in precleanup["stages"]] == STAGES
    assert all(item["verified"] is True for item in precleanup["stages"])

    router0 = precleanup["stages"][-1]
    voice = router0["canonical_voice_verification"]
    assert router0["configuration_acceptance_error"] == ""
    assert router0["control_plane"]["status"] == "verified"
    assert voice["complete"] is True
    assert {
        "expected": voice["expected_phone_count"],
        "fwd": voice["phone_access_fwd_verified"],
        "addressed": voice["addressed_count"],
        "bindings": voice["matching_binding_count"],
        "registered": voice["sccp_registered_count"],
    } == {"expected": 62, "fwd": 62, "addressed": 62, "bindings": 62, "registered": 62}

    assert router0["site_forwarding_verified"] is True
    assert router0["user_forwarding_verified"] is True
    assert len(router0["site_forwarding"]) == 2
    assert len(router0["user_forwarding"]) == 2
    for observation in router0["site_forwarding"]:
        assert observation["result"]["reachable"] is True
        assert observation["result"]["fresh_output_observed"] is True
        assert observation.get("error", "") == ""
    for observation in router0["user_forwarding"]:
        assert observation["status"] == "verified"
        assert observation["verified"] is True
        assert observation["error"] == ""
        assert len(observation["attempts"]) == 1
        assert observation["attempts"][0]["reachable"] is True
        assert observation["attempts"][0]["fresh_output_observed"] is True
        for binding in (
            observation["source_binding"],
            observation["destination_binding"],
        ):
            assert binding["fresh_evidence"] is True
            assert binding["target"]["runtime_link_identity_observed"] is True

    assert precleanup["no_mutation_replay"] == cleanup["no_mutation_replay"]
    assert cleanup["no_mutation_replay"] == {
        "audited_stages": STAGES,
        "claim": "NO_MUTATION_REPLAY",
        "replayed_retained_ids": [],
        "stages_without_verified_audit": [],
        "verified": True,
    }
    assert router0["workspace_verified_twice"] is True
    assert cleanup["cleanup"]["verified"] is True
    assert len(cleanup["cleanup"]["mutations"]) == 290
    for observation in (cleanup["cleanup"]["first"], cleanup["cleanup"]["second"]):
        assert observation["semantic_device_count"] == 0
        assert observation["link_count"] == 0
    assert cleanup["cleanup_realtime"]["verified"] is True
    assert cleanup["cleanup_realtime"]["state"]["simulation_mode"] is False


def test_current_state_points_to_the_router0_success_index() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    pointer = state["operational_state"]["router0"]["evidence"]
    raw = INDEX.read_bytes()

    assert pointer == {
        "path": "docs/reference/cp-scale/router0_successful_run.json",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "run_identity": RUN_ID,
        "executed_sha": HEAD,
        "classification": "VERIFIED",
        "successful_closure": True,
    }
