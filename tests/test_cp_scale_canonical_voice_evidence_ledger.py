"""Terminal provenance for the one governed canonical CP-SCALE Voice LIVE."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    compose_cp_scale_canonical,
    project_cp_scale_canonical_stage,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigureAccessPort,
)
from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
)
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)


ROOT = Path(__file__).resolve().parents[1]
GITATTRIBUTES = ROOT / ".gitattributes"
LEDGER = (
    ROOT / "docs" / "reference" / "cp-scale"
    / "canonical_voice_runs.json"
)
HANDOFF = ROOT / "handoff.md"
SOURCE_HEAD = "f5e72f08a4e917410e917a8dc3fedac461c135e1"
BASE_HEAD = "528564493b855ce332f45fdab7b5867a065b1992"
RUN_IDENTITY = "canonical-cp-scale-voice-20260830T202000133616Z-f5e72f08a4e9"
LATEST_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T010136612890Z-2976329769f9"
)
STAGES = (
    CPScaleCanonicalStage.FLOOR1,
    CPScaleCanonicalStage.FLOOR2,
    CPScaleCanonicalStage.FLOOR3,
    CPScaleCanonicalStage.ROUTER0_BRANCH,
    CPScaleCanonicalStage.ROUTER3_BRANCH,
    CPScaleCanonicalStage.REMAINING,
)


@pytest.fixture(scope="module")
def ledger() -> dict:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def run(ledger: dict) -> dict:
    assert ledger["schema"] == "cp-scale-canonical-voice-evidence-v1"
    assert ledger["verification"] == "CANONICAL_CP_SCALE_VOICE"
    assert len(ledger["runs"]) == 2
    return ledger["runs"][0]


@pytest.fixture(scope="module")
def latest_run(ledger: dict) -> dict:
    return ledger["runs"][-1]


@pytest.fixture(scope="module")
def raw_artifacts(run: dict) -> dict[str, dict]:
    return {
        item["phase"]: json.loads(
            (ROOT / item["path"]).read_text(encoding="utf-8"),
        )
        for item in run["artifacts"]
    }


@pytest.fixture(scope="module")
def composition():
    result = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
        capability_store=CapabilitySnapshotStore(ROOT / "data" / "capabilities"),
    )
    assert result.valid, result.issues
    return result


def _canonical_phone_facts(composition) -> tuple[dict[str, dict], dict[tuple, list]]:
    introduced: dict[str, dict] = {}
    groups: dict[tuple[str, int], set[str]] = {}
    for stage in STAGES:
        projection = project_cp_scale_canonical_stage(composition, stage)
        assert projection.voice is not None
        actions = {
            item.id: item
            for item in projection.configuration.actions
            if isinstance(item, ConfigureAccessPort)
            and item.voice_vlan_id is not None
        }
        for assignment in projection.voice.phone_assignments:
            if assignment.phone_id in introduced:
                continue
            action = actions[assignment.access_configuration_action_id]
            introduced[assignment.phone_id] = {
                "phone": assignment.physical_device_name,
                "phone_id": assignment.phone_id,
                "site": assignment.site_id,
                "site_stage": stage.value,
                "floor": assignment.floor_id,
                "switch": action.device_name,
                "port": action.interface,
                "voice_vlan": assignment.voice_vlan_id,
            }
        for action in actions.values():
            groups.setdefault(
                (action.device_name, action.voice_vlan_id), set(),
            ).add(action.interface)
    return introduced, {
        key: sorted(value) for key, value in groups.items()
    }


def _state_block() -> dict[str, str]:
    text = HANDOFF.read_text(encoding="utf-8")
    match = re.search(
        r"<!-- CP_SCALE_STATE_BEGIN -->(.*?)<!-- CP_SCALE_STATE_END -->",
        text,
        re.DOTALL,
    )
    assert match is not None
    return {
        key.strip(): value.strip()
        for key, value in (
            line.split("=", 1)
            for line in match.group(1).splitlines()
            if "=" in line
        )
    }


def test_terminal_ledger_pins_the_exact_live_identity_and_contract(run: dict):
    assert run["run_identity"] == RUN_IDENTITY
    assert run["packet_tracer_version"] == "9.0.1.0858"
    assert run["heads"] == {
        "base_head": BASE_HEAD,
        "prelive_head": SOURCE_HEAD,
        "canonical_live_source_head": SOURCE_HEAD,
    }
    assert run["live_attempts"] == 1
    assert run["invalid_live_attempts"] == 0
    assert run["canonical_contract"] == {
        "phone_count": 69,
        "voice_access_action_count": 69,
        "stage_voice_counts": {
            "floor1": 21,
            "floor2": 35,
            "floor3": 51,
            "router0-branch": 62,
            "router3-branch": 69,
            "remaining": 69,
        },
        "topology_regeneration_required": False,
    }


def test_both_immutable_artifacts_still_hash_to_the_ledger(run: dict):
    artifacts = {item["phase"]: item for item in run["artifacts"]}
    assert set(artifacts) == {"failure-precleanup", "cleanup"}
    assert artifacts["failure-precleanup"]["sha256"] == (
        "d4b017332c1f0b7f12e5e6fef977a508c7b1fcdb72e1f605ad095143b54a60db"
    )
    assert artifacts["cleanup"]["sha256"] == (
        "a066f7efbedc23176871e2c0a75e3e2422426554dbb2aad3a9126e6e06e759db"
    )
    for item in artifacts.values():
        path = ROOT / item["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_latest_floor1_divergence_is_tied_to_both_immutable_artifacts(
    latest_run: dict,
):
    assert latest_run["run_identity"] == LATEST_RUN_IDENTITY
    assert latest_run["heads"]["canonical_live_source_head"] == (
        "2976329769f9747fa819935f851742b300f81333"
    )
    assert latest_run["live_attempts"] == 1
    assert latest_run["invalid_live_attempts"] == 1
    artifacts = {
        item["phase"]: item for item in latest_run["artifacts"]
    }
    assert artifacts["failure-precleanup"]["sha256"] == (
        "6662ffa03e405645882d4d61bcbcec3af60957e4dac64d881bebd9fa15590c03"
    )
    assert artifacts["cleanup"]["sha256"] == (
        "968face019bad5adb4f5890d4a6f15b3164d143d3eff609df40622bb4ce4ec7a"
    )
    for item in artifacts.values():
        path = ROOT / item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_latest_run_localizes_proven_addressing_from_unresolved_sccp(
    latest_run: dict,
):
    floor1 = latest_run["measured"]["floor1_voice"]
    assert floor1["phone_access_fwd_verified"] == 21
    assert floor1["endpoint_ipv4_count"] == 21
    assert floor1["matching_binding_count"] == 21
    assert floor1["sccp_registered_count"] == 19
    assert floor1["sccp_unobservable_count"] == 2
    assert floor1["raw_reported_first_boundary"] == "ENDPOINT_ADDRESS"
    assert floor1["corrected_first_boundary"] == "SCCP"
    assert floor1["missing_ephone_extensions"] == ["3001", "3007"]
    assert latest_run["measured"]["floor2"] == {
        "status": "NOT_REACHED",
        "causal_question_answered": False,
    }
    assert latest_run["conclusion"]["failure_classification"] == (
        "PRODUCT_OR_OBSERVER_UNRESOLVED"
    )
    assert latest_run["conclusion"]["next_live_authorized"] is True


def test_latest_run_cleanup_is_independently_verified(latest_run: dict):
    assert latest_run["cleanup"] == {
        "verified": True,
        "workspace_restored": True,
        "realtime_restored": True,
        "semantic_device_count": 0,
        "link_count": 0,
        "restoration_error": "",
        "realtime_error": "",
    }


def test_immutable_canonical_evidence_is_never_text_normalized():
    attributes = GITATTRIBUTES.read_text(encoding="utf-8").splitlines()

    assert (
        "docs/reference/cp-scale/canonical-live-evidence/*.json -text -diff"
        in attributes
    )


def test_floor1_retains_the_measured_causal_order_and_exact_success(run: dict):
    floor1 = run["measured"]["floor1_voice"]
    assert floor1["complete"] is True
    assert floor1["lifecycle_events"] == [
        "DATA_ONLY_ACCESS_APPLIED",
        "NETWORK_VERIFIED",
        "VOICE_BOOTSTRAP_STARTED",
        "VOICE_BOOTSTRAP_APPLIED",
        "DEFERRED_VOICE_COMPLETION_STARTED",
        "VOICE_SIGNAL_VERIFIED",
        "PHONE_ACCESS_FWD_VERIFIED",
        "DEFERRED_VOICE_COMPLETION_VERIFIED",
        "REGISTRATION_STARTED",
        "REGISTRATION_COMPLETED",
    ]
    assert floor1["registration_started_after_fwd_barrier"] is True
    assert floor1["phone_access_fwd_verified"] == 21
    assert floor1["voice_svi_present_count"] == 21
    assert floor1["dhcp_enabled_count"] == 21
    assert floor1["addressed_count"] == 21
    assert floor1["voice_dhcp_binding_count"] == 21
    assert floor1["matching_binding_count"] == 21
    assert floor1["sccp_registered_count"] == 21
    assert floor1["failed_phone_identities"] == []


def test_compact_floor1_measurement_is_exactly_the_archived_object(
    run: dict,
    raw_artifacts: dict[str, dict],
):
    floor1_raw = next(
        item
        for item in raw_artifacts["failure-precleanup"]["stages"]
        if item["stage"] == "floor1"
    )

    assert run["measured"]["floor1_voice"] == (
        floor1_raw["canonical_voice_verification"]
    )


def test_all_eight_groups_exist_but_only_floor1_was_reached(
    run: dict,
    composition,
):
    _, expected_groups = _canonical_phone_facts(composition)
    groups = run["phone_access_groups"]
    keyed = {(item["switch"], item["voice_vlan"]): item for item in groups}

    assert len(keyed) == 8
    assert set(keyed) == set(expected_groups)
    for key, expected_interfaces in expected_groups.items():
        assert keyed[key]["expected_interfaces"] == expected_interfaces
    verified = keyed[("Switch5", 20)]
    assert verified["status"] == "VERIFIED"
    assert verified["verified_fwd_interfaces"] == verified["expected_interfaces"]
    assert verified["missing_interfaces"] == []
    assert verified["non_fwd_interfaces"] == {}
    assert verified["sample_count"] == 82
    assert verified["elapsed_ms"] == 45500
    assert verified["terminal_authority"] == "AUTHORITATIVE"
    assert verified["terminal_failure_dimension"] == "NONE"
    for key, item in keyed.items():
        if key == ("Switch5", 20):
            continue
        assert item["status"] == "NOT_REACHED"
        assert item["verified_fwd_interfaces"] == []
        assert item["missing_interfaces"] == []
        assert item["non_fwd_interfaces"] == {}
        assert item["sample_count"] == 0
        assert item["elapsed_ms"] == 0
        assert item["terminal_authority"] == "NOT_REACHED"
        assert item["terminal_failure_dimension"] == "NOT_REACHED"


def test_exact_48_phone_complement_is_not_promoted_to_unobservable(
    run: dict,
    composition,
):
    introduced, _ = _canonical_phone_facts(composition)
    expected = {
        phone_id: facts
        for phone_id, facts in introduced.items()
        if facts["site_stage"] != "floor1"
    }
    retained = {
        item["phone_id"]: item
        for item in run["not_reached_phone_identities"]
    }

    assert len(expected) == len(retained) == 48
    assert set(retained) == set(expected)
    for phone_id, facts in expected.items():
        item = retained[phone_id]
        assert {key: item[key] for key in facts} == facts
        assert item["ipv4"] is None
        assert item["binding_state"] == "NOT_REACHED"
        assert item["sccp_state"] == "NOT_REACHED"
        assert item["first_contradicted_boundary"] == "NETWORK_FOUNDATION"


def test_first_contradiction_is_the_fresh_floor2_network_result(run: dict):
    failure = run["measured"]["floor2_failure"]
    assert failure["stage"] == "floor2"
    assert failure["first_contradicted_boundary"] == "NETWORK_FOUNDATION"
    assert failure["classification"] == "PRODUCT"
    assert failure["voice_lifecycle_events"] == []
    observations = {
        item["expectation_id"]: item
        for item in failure["failed_trunk_observations"]
    }
    assert set(observations) == {
        "cfg/verify/506997bfeb712df8",
        "cfg/verify/e3a93eaca47434b8",
        "cfg/verify/a5a13a7e12eb7f2e",
    }
    assert all(item["fresh_evidence"] for item in observations.values())
    assert observations["cfg/verify/506997bfeb712df8"]["message"] == (
        "Trunk convergence timed out."
    )
    for identifier in (
        "cfg/verify/e3a93eaca47434b8",
        "cfg/verify/a5a13a7e12eb7f2e",
    ):
        assert observations[identifier]["message"] == (
            "forwarding omitted 10,20,30"
        )


def test_floor2_and_cleanup_summaries_remain_tied_to_the_raw_attestations(
    run: dict,
    raw_artifacts: dict[str, dict],
):
    precleanup = raw_artifacts["failure-precleanup"]
    floor2_raw = next(
        item for item in precleanup["stages"] if item["stage"] == "floor2"
    )
    raw_failed = {
        item["expectation_id"]: item
        for item in floor2_raw["configuration_attempts"][0][
            "verification_results"
        ]
        if item["status"] == "failed"
    }
    retained_failed = {
        item["expectation_id"]: item
        for item in run["measured"]["floor2_failure"][
            "failed_trunk_observations"
        ]
    }
    for expectation_id, raw in raw_failed.items():
        retained = retained_failed[expectation_id]
        for key in (
            "action_id",
            "expectation_id",
            "status",
            "fresh_evidence",
            "evidence_method",
            "fields",
            "message",
        ):
            assert retained[key] == raw[key]
        assert retained["sample_count"] == raw["convergence"]["attempts"]
        assert retained["elapsed_ms"] == raw["convergence"]["elapsed_ms"]

    cleanup_raw = raw_artifacts["cleanup"]
    assert cleanup_raw["cleanup"]["verified"] is True
    assert cleanup_raw["cleanup"]["restoration_error"] == ""
    assert cleanup_raw["cleanup"]["first"]["semantic_device_count"] == 0
    assert cleanup_raw["cleanup"]["second"]["semantic_device_count"] == 0
    assert cleanup_raw["cleanup"]["first"]["link_count"] == 0
    assert cleanup_raw["cleanup"]["second"]["link_count"] == 0
    assert cleanup_raw["cleanup_realtime"] == {
        "error": "",
        "state": cleanup_raw["cleanup_realtime"]["state"],
        "verified": True,
    }


def test_terminal_conclusion_and_cleanup_fail_closed(run: dict):
    conclusion = run["conclusion"]
    assert conclusion == {
        "canonical_cp_scale_voice_verification": "FAIL",
        "root_cause_status": "CONFIRMED",
        "production_fix_status": "VERIFIED_RUN23_CANONICAL_NOT_VERIFIED",
        "cp_scale_status": (
            "VOICE_NOT_VERIFIED_CANONICAL_NETWORK_FOUNDATION_FAILED_FLOOR2"
        ),
        "first_contradicted_boundary": "NETWORK_FOUNDATION",
        "failure_classification": "PRODUCT",
        "second_live_authorized": False,
    }
    assert run["cleanup"] == {
        "verified": True,
        "workspace_restored": True,
        "realtime_restored": True,
        "semantic_device_count": 0,
        "link_count": 0,
        "restoration_error": "",
        "realtime_error": "",
    }


def test_handoff_preserves_terminal_ledger_and_records_offline_diagnosis():
    state = _state_block()
    assert state["CANONICAL_CP_SCALE_LIVE_RUN"] == "EXECUTED_TWICE"
    assert state["CANONICAL_CP_SCALE_LIVE_ATTEMPTS"] == "2"
    assert state["CANONICAL_CP_SCALE_INVALID_LIVE_ATTEMPTS"] == "1"
    assert state["CANONICAL_CP_SCALE_FLOOR1_CURRENT_BOUNDARY"] == "SCCP"
    assert state["CANONICAL_CP_SCALE_NOT_REACHED_PHONES"] == "48"
    assert state["CANONICAL_CP_SCALE_FIRST_CONTRADICTED_BOUNDARY"] == (
        "SCCP"
    )
    assert state["CANONICAL_CP_SCALE_FAILURE_CLASSIFICATION"] == (
        "PRODUCT_OR_OBSERVER_UNRESOLVED"
    )
    assert state["CANONICAL_CP_SCALE_VOICE_VERIFICATION"] == "FAIL"
    assert state["ROOT_CAUSE_STATUS"] == "CONFIRMED"
    assert state["PRODUCTION_FIX_STATUS"] == (
        "VERIFIED_RUN23_CANONICAL_PARTIAL_19_OF_21_SCCP"
    )
    assert state["CANONICAL_CP_SCALE_WORKSPACE_RESTORED"] == "YES"
    assert state["CANONICAL_CP_SCALE_REALTIME_RESTORED"] == "YES"
    assert state["CANONICAL_CP_SCALE_FLOOR2_PRIOR_STAGE_SEMANTICS"] == (
        "CUMULATIVE_REPLAY"
    )
    assert (
        state["CANONICAL_CP_SCALE_FLOOR1_ACTIONS_REAPPLIED_AT_FAILED_FLOOR2"]
        == "115_OF_115"
    )
    assert state["CANONICAL_CP_SCALE_FLOOR2_FAILED_RUN_TEMPORAL_EVIDENCE"] == (
        "INSUFFICIENT"
    )
    assert state["CANONICAL_CP_SCALE_FLOOR2_TIMEOUT_CLASSIFICATION"] == (
        "NOT_ESTABLISHED"
    )
    assert state["CANONICAL_CP_SCALE_FLOOR2_NETWORK_ROOT_CAUSE"] == (
        "STRONG_CANDIDATE"
    )
    assert state["CANONICAL_CP_SCALE_FLOOR2_PRODUCT_FIX"] == (
        "CANDIDATE_IMPLEMENTED_CAUSAL_LIVE_PENDING"
    )
    assert state["CANONICAL_CP_SCALE_FLOOR2_CAUSAL_LIVE"] == (
        "ATTEMPTED_BUT_NOT_REACHED_DUE_FLOOR1_SCCP"
    )
    assert state["CP_SCALE_STATUS"] == (
        "FLOOR1_SCCP_DIVERGENCE_BLOCKS_FLOOR2_CAUSAL_QUESTION"
    )
