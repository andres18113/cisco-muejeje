"""The first successful FULL qualification closure is hash-pinned and complete."""

from __future__ import annotations

import hashlib
import json
from functools import cache
from pathlib import Path

from src.packet_tracer_mcp.infrastructure.catalog.cp_scale_qualification_policy import (
    packet_tracer_cp_scale_qualification_policy,
)


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "reference" / "cp-scale" / "full_qualification_successful_run.json"
CHECKPOINT = ROOT / "docs" / "reference" / "cp-scale" / "live_canonical_checkpoint.json"
RUN_ID = "canonical-cp-scale-voice-20260915T193037865890Z-6a80b24626d4"
HEAD = "6a80b24626d40fb59bad5f0dc2e47d18a51f4a49"
STAGES = [
    "routing-core",
    "router4-switch10",
    "floor1",
    "floor2",
    "floor3",
    "router0-branch",
    "router3-branch",
    "remaining",
]


def _index() -> dict:
    return json.loads(INDEX.read_text(encoding="utf-8"))


@cache
def _artifact(phase: str) -> dict:
    record = next(item for item in _index()["artifacts"] if item["phase"] == phase)
    raw = (ROOT / record["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == record["sha256"]
    return json.loads(raw)


def _assert_unique_dispatch_delta(ping: dict, expected_source: str) -> None:
    assert ping["attempts"] == 1
    assert ping["reachable"] is True
    assert ping["fresh_output_observed"] is True
    assert ping["failure_reason"] == ""
    assert ping["observed_device_name"] == expected_source
    assert ping["device_identity_provenance"] == "confirmed_unique"
    assert ping["device_identity_evidence"] == "dispatch_transcript_delta"
    assert ping["device_identity_candidate_names"] == [expected_source]
    assert ping["device_identity_refusal"] == "none"


def test_full_success_index_identifies_one_attested_closure():
    index = _index()
    assert index["schema"] == "cp-scale-full-qualification-successful-run-v1"
    assert index["classification"] == "VERIFIED"
    assert index["successful_closure"] is True
    assert index["evidence_authority"] == "FULL_QUALIFICATION_SUCCESS"
    assert (index["run_identity"], index["executed_sha"]) == (RUN_ID, HEAD)
    assert [item["path"] for item in index["artifacts"]] == [
        f"docs/reference/cp-scale/canonical-live-evidence/{RUN_ID}-{phase}.json"
        for phase in ("precleanup", "cleanup")
    ]

    precleanup = _artifact("precleanup")
    cleanup = _artifact("cleanup")
    assert precleanup["run_identity"] == cleanup["run_identity"] == RUN_ID
    assert precleanup["repository"]["head"] == cleanup["source_head"] == HEAD
    authorization = precleanup["live_authorization"]
    assert authorization["authorized_target"] == index["requested_target"]
    assert {
        authorization["authorized_sha"],
        authorization["expected_head"],
        authorization["repository_head"],
        authorization["upstream_head"],
    } == {HEAD}
    assert precleanup["target_stage"] == cleanup["target_stage"] == (
        "full-qualification"
    )
    # The cleaned closure exists only after a valid precleanup closure.
    assert precleanup["closure"] == index["precleanup_closure"]
    assert cleanup["closure"] == index["closure"]
    assert cleanup["canonical_evidence_precleanup"]["sha256"] == (
        index["artifacts"][0]["sha256"]
    )
    assert precleanup["presentation_retained"] is False
    assert precleanup["baseline"]["observed"] is True
    assert precleanup["baseline"]["semantic_device_count"] == 0
    assert precleanup["baseline"]["link_count"] == 0
    assert precleanup["packet_tracer_version"] == index["packet_tracer_version"]
    policy = packet_tracer_cp_scale_qualification_policy(index["packet_tracer_version"])
    assert precleanup["qualification_policy"] == {
        "backend": policy.backend,
        "backend_version": policy.backend_version,
        **policy.dimensions(),
    }
    assert index["host_observations"]["session_process_id"] in {
        process["Id"] for process in precleanup["packet_tracer_processes"]
    }


def test_remaining_is_the_verified_terminal_authority_of_full():
    index = _index()
    verified = index["verified"]
    precleanup = _artifact("precleanup")
    assert [item["stage"] for item in precleanup["stages"]] == verified["stages"] == STAGES
    assert all(item["verified"] is True for item in precleanup["stages"])
    assert all(item["workspace_verified_twice"] is True for item in precleanup["stages"])
    remaining = precleanup["stages"][-1]

    transition = precleanup["remaining_transition_contract"]
    assert transition["previous_stage"] == verified["remaining_transition"]["previous_stage"]
    assert transition["current_stage"] == verified["terminal_stage"] == "remaining"
    assert transition["physical_delta_empty"] is True
    assert transition["mutation_scope_disjoint"] is True
    assert transition["previous_physical_topology_hash"] == (
        transition["current_physical_topology_hash"]
    )
    assert not any(
        transition[key] for key in (
            "new_device_ids", "new_link_ids", "anchor_device_ids",
            "replayed_configuration_ids", "replayed_control_plane_ids",
            "replayed_voice_ids",
        )
    )
    assert {
        "previous_stage": transition["previous_stage"],
        "physical_delta_empty": transition["physical_delta_empty"],
        "configuration_mutations": len(transition["configuration_mutation_ids"]),
        "configuration_retained": len(transition["configuration_retained_ids"]),
        "control_plane_mutations": len(transition["control_plane_mutation_ids"]),
        "control_plane_retained": len(transition["control_plane_retained_ids"]),
        "voice_mutations": len(transition["voice_mutation_ids"]),
        "voice_retained": len(transition["voice_retained_ids"]),
        "claim": transition["claim"],
    } == verified["remaining_transition"]
    reconciliation = remaining["physical"]
    assert reconciliation["status"] == "verified"
    assert reconciliation["deployment_id"] == "cp-scale-canonical/remaining/reconciliation"
    kinds = {"device": 0, "link": 0}
    for item in reconciliation["item_results"]:
        if item["target_kind"] in kinds:
            assert item["disposition"] == "no_op"
            kinds[item["target_kind"]] += 1
    assert kinds == {
        "device": verified["cumulative_devices"],
        "link": verified["cumulative_links"],
    }

    assert remaining["configuration_acceptance_error"] == ""
    assert remaining["control_plane"]["status"] == "verified"
    voice = remaining["canonical_voice_verification"]
    assert voice["complete"] is True
    assert voice["binding_evidence_complete"] is True
    assert voice["registration_identity_errors"] == []
    assert {
        "expected": voice["expected_phone_count"],
        "fwd": voice["phone_access_fwd_verified"],
        "addressed": voice["addressed_count"],
        "bindings": voice["matching_binding_count"],
        "registered": voice["sccp_registered_count"],
    } == dict.fromkeys(("expected", "fwd", "addressed", "bindings", "registered"), 69)
    assert remaining["voice"]["registration_evidence_method"] == {
        "fresh_privileged_show_ephone": 69,
    }
    # Calls stay UNQUALIFIED on this backend: counted, never promoted or failed.
    assert {
        "status": "UNQUALIFIED",
        "expected_calls": voice["expected_call_count"],
        "verified_calls": voice["call_verified_count"],
        "failed_calls": voice["call_failed_count"],
        "unobservable_calls": voice["call_unobservable_count"],
        "call_identity_errors": len(voice["call_identity_errors"]),
    } == index["unqualified"]["call_behavior"]
    assert voice["call_unobservable_count"] == voice["expected_call_count"] > 0

    assert remaining["site_forwarding_verified"] is True
    assert remaining["user_forwarding_verified"] is True
    assert len(remaining["site_forwarding"]) == len(remaining["user_forwarding"]) == 6
    for observation in remaining["site_forwarding"]:
        assert observation["verified"] is True
        _assert_unique_dispatch_delta(
            observation["result"], observation["check"]["source_device_name"],
        )
    for observation in remaining["user_forwarding"]:
        assert observation["status"] == "verified"
        assert observation["verified"] is True
        assert len(observation["attempts"]) == 1
        _assert_unique_dispatch_delta(
            observation["attempts"][0],
            observation["source_binding"]["target"]["runtime_device_name"],
        )
        for binding in (observation["source_binding"], observation["destination_binding"]):
            assert binding["fresh_evidence"] is True
            assert binding["target"]["runtime_link_identity_observed"] is True
    for readback in (remaining["workspace_first"], remaining["workspace_second"]):
        assert readback["observed"] is True
        assert readback["message"] == "fresh_complete_workspace_inventory"
        assert readback["semantic_device_count"] == verified["cumulative_devices"]


def test_full_cleanup_is_attested_after_the_precleanup_closure():
    index = _index()
    precleanup = _artifact("precleanup")
    cleanup = _artifact("cleanup")

    assert precleanup["no_mutation_replay"] == cleanup["no_mutation_replay"] == {
        "audited_stages": STAGES,
        "claim": "NO_MUTATION_REPLAY",
        "replayed_retained_ids": [],
        "stages_without_verified_audit": [],
        "verified": True,
    }
    removed = cleanup["cleanup"]
    assert removed["verified"] is True
    assert removed["restoration_error"] == ""
    assert len(removed["mutations"]) == index["cleanup"]["deleted_devices"] == 314
    assert all(
        item["applied"] is True and item["disposition"] == "changed"
        for item in removed["mutations"]
    )
    assert {
        "first_semantic_devices": removed["first"]["semantic_device_count"],
        "first_links": removed["first"]["link_count"],
        "second_semantic_devices": removed["second"]["semantic_device_count"],
        "second_links": removed["second"]["link_count"],
    } == {key: 0 for key in (
        "first_semantic_devices", "first_links",
        "second_semantic_devices", "second_links",
    )}
    assert cleanup["cleanup_realtime"]["verified"] is True
    assert cleanup["cleanup_realtime"]["state"]["simulation_mode"] is False
    assert cleanup["cleanup_completed_at"] > precleanup["completed_at"]

    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    assert index["final_checkpoint"]["path"] == "docs/reference/cp-scale/live_canonical_checkpoint.json"
    assert checkpoint["checkpoint"] == index["final_checkpoint"]["checkpoint"]
    assert checkpoint["raw_evidence_sha256"] == index["final_checkpoint"]["raw_progress_sha256"]
    assert (checkpoint["live_devices"], checkpoint["live_links"]) == (314, 219)
