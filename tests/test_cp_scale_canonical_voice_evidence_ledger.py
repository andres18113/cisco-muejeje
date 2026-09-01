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
DIAGNOSTIC_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T013000402201Z-144ebaa65c5f"
)
BATCH_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T015150996119Z-4802eb6de95b"
)
GATE_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T021410113093Z-6b7a9d37d81b"
)
ABSENCE_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T023109308451Z-f1cf32ad7391"
)
ORDER_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T025406307135Z-ea9b93f0da73"
)
MANAGED_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T031054739651Z-ba2b036561c7"
)
RECONCILE_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T032640436029Z-3e5b385cb8f2"
)
FRONTIER_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T034510704353Z-ab0a890a6229"
)
CAPACITY_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T040356110829Z-0b0f2def9748"
)
GOVERNED_CAPACITY_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T041940173800Z-b777036b925b"
)
TERMINAL_DIAGNOSTIC_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T043604861347Z-86603be911bf"
)
CHECKPOINT_EOF_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T051218175698Z-3c74547c50eb"
)
FLOOR1_CONTROL_OBSERVER_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T051758574307Z-ac6012f6a759"
)
FLOOR2_DELTA_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T055647792755Z-0ec4bdade3bb"
)
FLOOR2_NETWORK_VERIFIED_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T071703181436Z-fe725ac177d2"
)
FLOOR2_VOICE_DELTA_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T085436828856Z-b9da148c8b37"
)
FLOOR2_GROUPED_PAGER_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T095242336005Z-7ea42ee7d5db"
)
FLOOR2_SUCCESS_FLOOR3_CAPACITY_RUN_IDENTITY = (
    "canonical-cp-scale-voice-20260901T120836292077Z-2bf6876f0fd2"
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
    assert len(ledger["runs"]) == 20
    return ledger["runs"][0]


@pytest.fixture(scope="module")
def second_run(ledger: dict) -> dict:
    return ledger["runs"][1]


@pytest.fixture(scope="module")
def diagnostic_run(ledger: dict) -> dict:
    return ledger["runs"][2]


@pytest.fixture(scope="module")
def batch_run(ledger: dict) -> dict:
    return ledger["runs"][3]


@pytest.fixture(scope="module")
def gate_run(ledger: dict) -> dict:
    return ledger["runs"][4]


@pytest.fixture(scope="module")
def absence_run(ledger: dict) -> dict:
    return ledger["runs"][5]


@pytest.fixture(scope="module")
def order_run(ledger: dict) -> dict:
    return ledger["runs"][6]


@pytest.fixture(scope="module")
def managed_run(ledger: dict) -> dict:
    return ledger["runs"][7]


@pytest.fixture(scope="module")
def reconcile_run(ledger: dict) -> dict:
    return ledger["runs"][8]


@pytest.fixture(scope="module")
def frontier_run(ledger: dict) -> dict:
    return ledger["runs"][9]


@pytest.fixture(scope="module")
def capacity_run(ledger: dict) -> dict:
    return ledger["runs"][10]


@pytest.fixture(scope="module")
def latest_run(ledger: dict) -> dict:
    return ledger["runs"][11]


@pytest.fixture(scope="module")
def terminal_diagnostic_run(ledger: dict) -> dict:
    return ledger["runs"][12]


@pytest.fixture(scope="module")
def checkpoint_eof_run(ledger: dict) -> dict:
    return ledger["runs"][13]


@pytest.fixture(scope="module")
def floor1_control_observer_run(ledger: dict) -> dict:
    return ledger["runs"][14]


@pytest.fixture(scope="module")
def floor2_delta_run(ledger: dict) -> dict:
    return ledger["runs"][15]


@pytest.fixture(scope="module")
def floor2_network_verified_run(ledger: dict) -> dict:
    return ledger["runs"][16]


@pytest.fixture(scope="module")
def floor2_voice_delta_run(ledger: dict) -> dict:
    return ledger["runs"][17]


@pytest.fixture(scope="module")
def floor2_grouped_pager_run(ledger: dict) -> dict:
    return ledger["runs"][18]


@pytest.fixture(scope="module")
def floor2_success_floor3_capacity_run(ledger: dict) -> dict:
    return ledger["runs"][19]


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
    second_run: dict,
):
    assert second_run["run_identity"] == LATEST_RUN_IDENTITY
    assert second_run["heads"]["canonical_live_source_head"] == (
        "2976329769f9747fa819935f851742b300f81333"
    )
    assert second_run["live_attempts"] == 1
    assert second_run["invalid_live_attempts"] == 1
    artifacts = {
        item["phase"]: item for item in second_run["artifacts"]
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
    second_run: dict,
):
    floor1 = second_run["measured"]["floor1_voice"]
    assert floor1["phone_access_fwd_verified"] == 21
    assert floor1["endpoint_ipv4_count"] == 21
    assert floor1["matching_binding_count"] == 21
    assert floor1["sccp_registered_count"] == 19
    assert floor1["sccp_unobservable_count"] == 2
    assert floor1["raw_reported_first_boundary"] == "ENDPOINT_ADDRESS"
    assert floor1["corrected_first_boundary"] == "SCCP"
    assert floor1["missing_ephone_extensions"] == ["3001", "3007"]
    assert second_run["measured"]["floor2"] == {
        "status": "NOT_REACHED",
        "causal_question_answered": False,
    }
    assert second_run["conclusion"]["failure_classification"] == (
        "PRODUCT_OR_OBSERVER_UNRESOLVED"
    )
    assert second_run["conclusion"]["next_live_authorized"] is True


def test_latest_run_cleanup_is_independently_verified(second_run: dict):
    assert second_run["cleanup"] == {
        "verified": True,
        "workspace_restored": True,
        "realtime_restored": True,
        "semantic_device_count": 0,
        "link_count": 0,
        "restoration_error": "",
        "realtime_error": "",
    }


def test_diagnostic_run_separates_parser_and_product_divergences(
    diagnostic_run: dict,
):
    assert diagnostic_run["run_identity"] == DIAGNOSTIC_RUN_IDENTITY
    assert diagnostic_run["heads"]["canonical_live_source_head"] == (
        "144ebaa65c5fbc7f6cf268ee97d8cf5f13ad10cc"
    )
    observer = diagnostic_run["measured"]["observer_divergence"]
    assert observer == {
        "extension": "3007",
        "ephone_index": 7,
        "raw_table_present": True,
        "raw_sccp_registered": True,
        "raw_ipv4": "172.16.20.2",
        "parser_row_present": False,
        "cause": "LEADING_WHITESPACE_BEFORE_IP_LINE",
    }
    mutation = diagnostic_run["measured"]["product_mutation_divergence"]
    assert mutation["extension"] == "3001"
    assert mutation["phone_mac_unique_within_floor1"] is True
    assert mutation["rendered_ephone_block_present"] is True
    assert mutation["raw_table_present_in_any_sample"] is False
    assert mutation["raw_sample_count"] == 33
    assert diagnostic_run["conclusion"]["failure_classification"] == "PRODUCT"
    assert diagnostic_run["conclusion"]["next_live_authorized"] is True


def test_single_action_binding_batches_are_a_valid_negative(batch_run: dict):
    assert batch_run["run_identity"] == BATCH_RUN_IDENTITY
    assert batch_run["heads"]["canonical_live_source_head"] == (
        "4802eb6de95b333390324f989eb4ee5acf4043af"
    )
    experiment = batch_run["measured"]["binding_batch_experiment"]
    assert experiment["renderer_binding_batches"] == 21
    assert experiment["actions_per_binding_batch"] == 1
    assert experiment["ephone1_raw_table_present"] is False
    assert experiment["raw_registration_samples"] == 35
    assert experiment["result"] == "BATCH_SIZE_REFUTED_AS_SUFFICIENT"
    assert batch_run["conclusion"]["ephone1_batch_size_cause"] == (
        "REFUTED_AS_SUFFICIENT"
    )
    assert batch_run["conclusion"]["ephone1_mutation_completion_cause"] == (
        "STRONG_CANDIDATE"
    )
    assert batch_run["conclusion"]["next_live_authorized"] is True


def test_binding_gate_stops_on_observer_without_replaying(gate_run: dict):
    assert gate_run["run_identity"] == GATE_RUN_IDENTITY
    gate = gate_run["measured"]["binding_readback_gate"]
    assert gate["verified_bindings_before_stop"] == 11
    assert gate["mutation_dispatched"] is True
    assert gate["readback_executed"] is True
    assert gate["readback_fresh"] is True
    assert gate["readback_complete"] is False
    assert gate["readback_identity"] == "confirmed_unique"
    assert gate["later_bindings_dispatched"] is False
    assert gate["voice_signal_dispatched"] is False
    assert gate["registration_started"] is False
    assert gate_run["conclusion"]["failure_classification"] == "OBSERVER"
    assert gate_run["conclusion"]["next_live_authorized"] is True


def test_complete_ephone1_absence_is_not_retried(absence_run: dict):
    assert absence_run["run_identity"] == ABSENCE_RUN_IDENTITY
    gate = absence_run["measured"]["binding_readback_gate"]
    assert gate["verified_bindings_before_stop"] == 18
    assert gate["stopped_directory_index"] == 1
    assert gate["mutation_dispatched"] is True
    assert gate["readback_fresh"] is True
    assert gate["readback_complete"] is True
    assert gate["readback_pages"] == 5
    assert gate["readback_identity"] == "confirmed_unique"
    assert gate["row_present"] is False
    assert gate["retry_eligible"] is False
    assert gate["later_bindings_dispatched"] is False
    assert absence_run["conclusion"]["ephone1_complete_absence"] == "CONFIRMED"
    assert absence_run["conclusion"]["ephone1_hash_order_cause"] == (
        "STRONG_CANDIDATE"
    )


def test_semantic_order_proves_failure_follows_ordinal_nineteen(
    order_run: dict,
):
    assert order_run["run_identity"] == ORDER_RUN_IDENTITY
    experiment = order_run["measured"]["semantic_order_experiment"]
    assert experiment["binding_order"] == "DIRECTORY_INDEX_ASCENDING"
    assert experiment["first_binding_index"] == 1
    assert experiment["first_binding_verified"] is True
    assert experiment["verified_bindings_before_stop"] == 18
    assert experiment["stopped_ordinal"] == 19
    assert experiment["stopped_directory_index"] == 19
    assert experiment["row_present"] is False
    assert experiment["result"] == (
        "INDEX_ONE_CAUSE_REFUTED_FAILURE_FOLLOWS_ORDINAL_19"
    )
    assert order_run["conclusion"]["ephone_index_one_cause"] == "REFUTED"
    assert order_run["conclusion"]["ordinal_19_failure"] == "CONFIRMED"


def test_managed_cme_mode_refutes_auto_registration_cause(managed_run: dict):
    assert managed_run["run_identity"] == MANAGED_RUN_IDENTITY
    experiment = managed_run["measured"]["explicit_cme_mode_experiment"]
    assert experiment["call_control_mode"] == "NO_AUTO_REG_EPHONE"
    assert experiment["verified_bindings_before_stop"] == 18
    assert experiment["stopped_ordinal"] == 19
    assert experiment["row_present"] is False
    assert experiment["result"] == (
        "AUTO_REGISTRATION_REFUTED_FAILURE_FOLLOWS_ORDINAL_19"
    )
    assert managed_run["conclusion"]["auto_registration_interference_cause"] == (
        "REFUTED"
    )
    assert managed_run["conclusion"]["absence_driven_reconciliation_cause"] == (
        "AUTHORIZED_CAUSAL_EXPERIMENT"
    )


def test_immediate_reconciliation_is_a_valid_negative(reconcile_run: dict):
    assert reconcile_run["run_identity"] == RECONCILE_RUN_IDENTITY
    experiment = reconcile_run["measured"][
        "immediate_reconciliation_experiment"
    ]
    assert experiment["initial_absence_authoritative"] is True
    assert experiment["reconciliation_attempted"] is True
    assert experiment["reconciliation_accepted"] is True
    assert experiment["final_readback_authoritative"] is True
    assert experiment["final_row_present"] is False
    assert experiment["second_reconciliation_attempted"] is False
    assert experiment["result"] == "IMMEDIATE_RECONCILIATION_REFUTED"
    assert reconcile_run["conclusion"][
        "deferred_frontier_reconciliation_cause"
    ] == "AUTHORIZED_CAUSAL_EXPERIMENT"


def test_deferred_frontier_reconciliation_is_a_valid_negative(
    frontier_run: dict,
):
    assert frontier_run["run_identity"] == FRONTIER_RUN_IDENTITY
    experiment = frontier_run["measured"]["deferred_frontier_experiment"]
    assert experiment["initial_bindings_dispatched"] == 21
    assert experiment["initial_bindings_verified"] == 20
    assert experiment["later_siblings_20_and_21_verified"] is True
    assert experiment["deferred_reconciliation_attempted"] is True
    assert experiment["final_readback_complete"] is True
    assert len(experiment["final_readback_indices"]) == 20
    assert experiment["reconciled_row_present"] is False
    assert experiment["result"] == (
        "DEFERRED_FRONTIER_RECONCILIATION_REFUTED"
    )
    assert frontier_run["conclusion"]["stage_call_control_capacity_cause"] == (
        "STRONG_CANDIDATE"
    )


def test_capacity_51_is_refuted_against_governed_design(capacity_run: dict):
    assert capacity_run["run_identity"] == CAPACITY_RUN_IDENTITY
    experiment = capacity_run["measured"]["capacity_51_experiment"]
    assert experiment["rendered_max_ephones"] == 51
    assert experiment["binding_actions"] == 21
    assert experiment["initial_binding_rows_verified"] == 0
    assert experiment["final_table_rows"] == 0
    assert experiment["readback_complete"] is True
    assert experiment["result"] == "CAPACITY_51_INVALID_ON_PACKET_TRACER_2811"
    assert capacity_run["conclusion"]["capacity_51_cause"] == "REFUTED_INVALID"
    assert capacity_run["conclusion"]["declared_capacity_model"] == (
        "ROUTER4_42_ROUTER0_12_ROUTER3_7"
    )


def test_governed_capacity_is_refuted_for_ordinal_loss(latest_run: dict):
    assert latest_run["run_identity"] == GOVERNED_CAPACITY_RUN_IDENTITY
    experiment = latest_run["measured"]["capacity_42_experiment"]
    assert experiment["rendered_max_ephones"] == 42
    assert experiment["initial_bindings_verified"] == 20
    assert experiment["post_reconciliation_rows"] == 20
    assert experiment["raw_indices_equal_parsed_indices"] is True
    assert experiment["reconciled_row_present"] is False
    assert experiment["result"] == (
        "CAPACITY_REFUTED_FOR_ORDINAL_BINDING_LOSS"
    )
    assert latest_run["conclusion"]["stage_call_control_capacity_cause"] == (
        "REFUTED_FOR_ORDINAL_LOSS"
    )


def test_terminal_diagnostic_confirms_pager_header_parser_cause(
    terminal_diagnostic_run: dict,
):
    assert (
        terminal_diagnostic_run["run_identity"]
        == TERMINAL_DIAGNOSTIC_RUN_IDENTITY
    )
    experiment = terminal_diagnostic_run["measured"][
        "pager_boundary_parser_divergence"
    ]
    assert experiment["binding_ordinal"] == 19
    assert experiment["directory_index"] == 19
    assert experiment["initial_readback_complete"] is True
    assert experiment["raw_row_present"] is True
    assert experiment["raw_header_leading_spaces"] == 1
    assert experiment["parser_row_present"] is False
    assert experiment["later_raw_table_indices"] == list(range(1, 22))
    assert experiment["result"] == "EPHONE_HEADER_PARSER_CAUSE_CONFIRMED"
    assert (
        terminal_diagnostic_run["conclusion"]["failure_classification"]
        == "OBSERVER"
    )
    assert (
        terminal_diagnostic_run["conclusion"]["ordinal_19_product_loss"]
        == "REFUTED"
    )
    for artifact in terminal_diagnostic_run["artifacts"]:
        path = ROOT / artifact["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]


def test_checkpoint_eof_is_classified_as_harness_and_cleaned(
    checkpoint_eof_run: dict,
):
    assert checkpoint_eof_run["run_identity"] == CHECKPOINT_EOF_RUN_IDENTITY
    checkpoint = checkpoint_eof_run["measured"]["routing_core_checkpoint"]
    assert checkpoint == {
        "physical_status": "verified",
        "configuration_status": "verified",
        "control_plane_status": "verified",
        "core_forwarding_verified": True,
        "workspace_verified_twice": True,
        "semantic_devices": 3,
        "links": 3,
    }
    channel = checkpoint_eof_run["measured"]["checkpoint_command_channel"]
    assert channel["failure"] == "EOFError: EOF when reading a line"
    assert channel["operator_command_received"] is False
    assert channel["result"] == "HARNESS_STDIN_CLOSED"
    assert checkpoint_eof_run["conclusion"]["failure_classification"] == "HARNESS"
    assert checkpoint_eof_run["conclusion"]["next_live_authorized"] is True
    assert checkpoint_eof_run["cleanup"]["verified"] is True
    for artifact in checkpoint_eof_run["artifacts"]:
        path = ROOT / artifact["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]


def test_floor1_voice_closes_before_rip_process_observer_stop(
    floor1_control_observer_run: dict,
):
    assert (
        floor1_control_observer_run["run_identity"]
        == FLOOR1_CONTROL_OBSERVER_RUN_IDENTITY
    )
    voice = floor1_control_observer_run["measured"]["floor1_voice"]
    assert voice["complete"] is True
    assert voice["expected_phone_count"] == 21
    assert voice["voice_bootstrap_status"] == "applied"
    assert voice["phone_access_fwd_verified"] == 21
    assert voice["addressed_count"] == 21
    assert voice["matching_binding_count"] == 21
    assert voice["sccp_registered_count"] == 21
    assert voice["registration_started_after_fwd_barrier"] is True
    observer = floor1_control_observer_run["measured"][
        "rip_process_observer"
    ]
    assert observer["process_expectations_verified"] == ["Router4"]
    assert observer["process_expectations_unobservable"] == [
        "Router0",
        "Router3",
    ]
    assert observer["route_expectations_verified"] == 9
    assert observer["route_expectations_failed"] == 0
    assert observer["result"] == "RIP_PROCESS_PAGER_OBSERVER_BLOCKED_STAGE"
    conclusion = floor1_control_observer_run["conclusion"]
    assert conclusion["ephone_header_parser_correction"] == (
        "VERIFIED_CANONICAL_FLOOR1"
    )
    assert conclusion["failure_classification"] == "OBSERVER"
    assert conclusion["next_live_authorized"] is True
    for artifact in floor1_control_observer_run["artifacts"]:
        path = ROOT / artifact["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]


def test_floor2_delta_preserves_old_trunks_and_exposes_learning_boundary(
    floor2_delta_run: dict,
):
    assert floor2_delta_run["run_identity"] == FLOOR2_DELTA_RUN_IDENTITY
    assert floor2_delta_run["measured"]["floor1"][
        "checkpoint_advanced"
    ] is True
    delta = floor2_delta_run["measured"]["floor2_delta"]
    assert delta["configuration_mutation_actions"] == 76
    assert delta["configuration_retained_actions"] == 115
    assert delta["cumulative_verification_expectations"] == 191
    assert delta["physical_delta_new_devices"] == 58
    assert delta["physical_delta_links"] == 41
    convergence = floor2_delta_run["measured"]["floor2_trunk_convergence"]
    assert convergence["expectations"] == 9
    assert convergence["verified"] == 5
    assert convergence["failed"] == 4
    assert convergence["round_robin_samples"] == 35
    assert convergence["elapsed_ms"] == 45766
    assert len(convergence["preserved_floor1_interfaces"]) == 5
    assert len(convergence["new_non_forwarding_interfaces"]) == 4
    assert convergence["initial_new_port_state"] == "LIS"
    assert convergence["latest_retained_new_port_state"] == "LRN"
    assert convergence["latest_retained_pvst_rounds"] == [23, 31, 33]
    assert convergence["terminal_trunk_sample_round"] == 35
    assert convergence["pvst_sample_at_terminal_boundary"] is False
    assert convergence["observed_forward_delay_seconds"] == 15
    conclusion = floor2_delta_run["conclusion"]
    assert conclusion["cumulative_replay_sufficient_cause"] == "REFUTED"
    assert conclusion["floor2_root_cause_status"] == (
        "STRONGLY_SUPPORTED_BOUNDARY_SAMPLE_PENDING"
    )
    assert conclusion["state_authorized_learning_extension"] == (
        "CAUSAL_EXPERIMENT_READY_LIVE_PENDING"
    )
    for artifact in floor2_delta_run["artifacts"]:
        path = ROOT / artifact["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]


def test_floor2_network_closes_before_cumulative_voice_replay_stop(
    floor2_network_verified_run: dict,
):
    assert (
        floor2_network_verified_run["run_identity"]
        == FLOOR2_NETWORK_VERIFIED_RUN_IDENTITY
    )
    network = floor2_network_verified_run["measured"][
        "floor2_network_foundation"
    ]
    assert network["trunk_expectations"] == 9
    assert network["trunks_verified"] == 9
    assert network["boundary_switch6_states"] == {
        "GigabitEthernet0/1": "LRN",
        "GigabitEthernet0/2": "LRN",
    }
    assert network["boundary_switch10_fastethernet_0_2_state"] == "LRN"
    assert network["atomic_refresh_complete"] is True
    assert network["learning_extension_engaged"] is False
    assert network["result"] == (
        "VERIFIED_BY_FRESH_BOUNDARY_THEN_ATOMIC_TRUNK_REFRESH"
    )
    voice = floor2_network_verified_run["measured"][
        "floor2_voice_bootstrap"
    ]
    assert voice["cumulative_actions"] == 75
    assert voice["mutation_actions"] == 75
    assert voice["retained_actions"] == 0
    assert voice["first_binding_directory_index"] == 1
    assert voice["first_binding_belongs_to_floor1"] is True
    assert voice["readback_attempts"] == 2
    assert voice["attempts_complete"] == 0
    assert voice["new_floor2_binding_dispatched"] is False
    conclusion = floor2_network_verified_run["conclusion"]
    assert conclusion["floor2_network_correction"] == (
        "VERIFIED_BY_FRESH_BOUNDARY_ATOMIC_REFRESH"
    )
    assert conclusion["floor2_voice_delta"] == (
        "IMPLEMENTATION_READY_LIVE_PENDING"
    )
    for artifact in floor2_network_verified_run["artifacts"]:
        path = ROOT / artifact["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]


def test_floor2_voice_delta_reaches_first_new_binding_observer(
    floor2_voice_delta_run: dict,
):
    assert floor2_voice_delta_run["run_identity"] == (
        FLOOR2_VOICE_DELTA_RUN_IDENTITY
    )
    partitions = floor2_voice_delta_run["measured"][
        "floor2_mutation_partitions"
    ]
    assert partitions == {
        "configuration_mutation_actions": 76,
        "configuration_retained_actions": 115,
        "voice_mutation_actions": 29,
        "voice_retained_actions": 46,
        "control_plane_mutation_actions": 0,
        "control_plane_retained_actions": 3,
    }
    observer = floor2_voice_delta_run["measured"][
        "floor2_voice_binding_observer"
    ]
    assert observer["new_extensions_applied"] == 14
    assert observer["first_binding_directory_index"] == 22
    assert observer["first_binding_belongs_to_floor2"] is True
    assert observer["readback_attempts"] == 2
    assert observer["attempt_pages_captured"] == [3, 4]
    assert observer["attempts_complete"] == 0
    assert observer["authoritative_absence"] is False
    assert observer["reconciliation_attempted"] is False
    conclusion = floor2_voice_delta_run["conclusion"]
    assert conclusion["floor2_voice_replay_sufficient_cause"] == "REFUTED"
    assert conclusion["per_binding_global_paged_readback"] == (
        "CONFIRMED_OBSERVER_BOUNDARY"
    )
    assert conclusion["grouped_binding_frontier"] == (
        "IMPLEMENTATION_READY_LIVE_PENDING"
    )
    for artifact in floor2_voice_delta_run["artifacts"]:
        path = ROOT / artifact["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]


def test_grouped_frontier_localizes_combined_pager_rollover(
    floor2_grouped_pager_run: dict,
):
    assert floor2_grouped_pager_run["run_identity"] == (
        FLOOR2_GROUPED_PAGER_RUN_IDENTITY
    )
    frontier = floor2_grouped_pager_run["measured"][
        "floor2_grouped_binding_frontier"
    ]
    assert frontier["new_bindings_dispatched"] == 14
    assert frontier["binding_indices"] == list(range(22, 36))
    assert frontier["grouped_logical_reads"] == 1
    assert frontier["grouped_read_attempts"] == 2
    assert frontier["attempt_pages_captured"] == [3, 3]
    assert frontier["attempts_complete"] == 0
    assert frontier["frontier_authoritative"] is False
    assert frontier["reconciliation_action_ids"] == []
    assert frontier["later_voice_phases_dispatched"] is False
    conclusion = floor2_grouped_pager_run["conclusion"]
    assert conclusion["grouped_binding_frontier_sufficient_cause"] == "REFUTED"
    assert conclusion["pager_combined_head_roll_tail_rewrite"] == (
        "STRONGLY_SUPPORTED"
    )
    assert conclusion["pager_pre_marker_suffix_anchor"] == (
        "IMPLEMENTATION_READY_LIVE_PENDING"
    )
    for artifact in floor2_grouped_pager_run["artifacts"]:
        path = ROOT / artifact["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]


def test_pager_fix_closes_floor2_and_exposes_floor3_capacity_mismatch(
    floor2_success_floor3_capacity_run: dict,
):
    run = floor2_success_floor3_capacity_run
    assert run["run_identity"] == FLOOR2_SUCCESS_FLOOR3_CAPACITY_RUN_IDENTITY
    floor2 = run["measured"]["floor2"]
    assert floor2["checkpoint_advanced"] is True
    assert floor2["voice_complete"] is True
    assert floor2["expected_phone_count"] == 35
    assert floor2["phone_access_fwd_verified"] == 35
    assert floor2["addressed_count"] == 35
    assert floor2["matching_binding_count"] == 35
    assert floor2["sccp_registered_count"] == 35
    assert floor2["grouped_read_pages"] == 8
    assert floor2["grouped_read_continuation"] == "completed"
    capacity = run["measured"]["floor3_capacity_boundary"]
    assert capacity["declared_max_ephones"] == 42
    assert capacity["cumulative_phone_count"] == 51
    assert capacity["new_directory_indices"] == list(range(36, 52))
    assert capacity["initial_absent_new_bindings"] == 16
    assert capacity["reconciliations_attempted"] == 16
    assert capacity["reconciliations_accepted"] == 16
    assert capacity["final_table_indices_equal_initial"] is True
    assert capacity["final_absent_new_bindings"] == 16
    assert capacity["result"] == (
        "DOCUMENTED_51_PHONE_TO_42_EPHONE_MISMATCH_CONFIRMED_AT_FLOOR3"
    )
    conclusion = run["conclusion"]
    assert conclusion["pager_pre_marker_suffix_anchor"] == "VERIFIED_PRODUCTION"
    assert conclusion["router4_capacity_mismatch"] == "CONFIRMED"
    assert conclusion["capacity_correction"] == (
        "CME_MODEL_QUALIFICATION_REQUIRED"
    )
    for artifact in run["artifacts"]:
        path = ROOT / artifact["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]


def test_immutable_canonical_evidence_is_never_text_normalized():
    attributes = GITATTRIBUTES.read_text(encoding="utf-8").splitlines()

    assert (
        "docs/reference/cp-scale/canonical-live-evidence/*.json -text -diff"
        in attributes
    )


def test_2911_cme_probe_negative_and_cleanup_are_pinned():
    evidence_dir = (
        ROOT / "docs" / "reference" / "cp-scale"
        / "canonical-live-evidence"
    )
    wrapper = evidence_dir / (
        "cme-model-capability-20260901T124507166721Z-2410958d08f2.json"
    )
    snapshot = evidence_dir / (
        "cme-model-capability-20260901T124507166721Z-"
        "2410958d08f2-2911-snapshot.json"
    )
    cleanup = evidence_dir / (
        "cme-model-capability-20260901T124507166721Z-"
        "2410958d08f2-cleanup.json"
    )
    assert hashlib.sha256(wrapper.read_bytes()).hexdigest() == (
        "12a6efb47f7ac12bb98b15a6fd93ff7eb7f46acbfd529eb4bc14f57d3f71ffe1"
    )
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == (
        "7b2e1aa81552bead16678b95ce1c882b2e315cf4116e39edfddb976ba0793f83"
    )
    assert hashlib.sha256(cleanup.read_bytes()).hexdigest() == (
        "3dfb438e18aeb1cb77aad0ac7112ddc6f9a4e1989cb24064907ec131bd29689c"
    )
    snapshot_payload = json.loads(snapshot.read_text(encoding="utf-8"))
    result = next(
        item for item in snapshot_payload["session"]["results"]
        if item["capability"] == "supports_cme"
    )
    assert result["model"] == "2911"
    assert result["status"] == "unknown"
    assert result["execution_status"] == "verify_failed"
    assert result["verified"] is False
    assert snapshot_payload["inventory_restored"] is True
    assert snapshot_payload["session"]["cleanup_failed"] == []
    cleanup_payload = json.loads(cleanup.read_text(encoding="utf-8"))
    assert cleanup_payload["independent_post_cleanup"]["verified"] is True


def test_isr_cme_probe_negatives_and_cleanup_are_pinned():
    path = (
        ROOT / "docs" / "reference" / "cp-scale"
        / "canonical-live-evidence"
        / "cme-isr-capability-20260901T125208981243Z-f885b743dce2.json"
    )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "b32099fc9e2dfc88b3bc295c1361b730a2b4ab87f1312f6943642594e9f6823b"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload.get("failure", "") == ""
    for model in ("ISR4321", "ISR4331"):
        result = next(
            item for item in payload["models"][model]["results"]
            if item["capability"] == "supports_cme"
        )
        assert result["status"] == "unknown"
        assert result["execution_status"] == "verify_failed"
        assert result["verified"] is False
        assert payload["models"][model]["inventory_restored"] is True
        assert payload["models"][model]["cleanup_failed"] == []
    assert payload["cleanup"]["verified"] is True
    assert payload["cleanup"]["first"]["semantic_device_count"] == 0
    assert payload["cleanup"]["second"]["semantic_device_count"] == 0


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
    assert state["CANONICAL_CP_SCALE_LIVE_RUN"] == "EXECUTED_TWENTY_TIMES"
    assert state["CANONICAL_CP_SCALE_LIVE_ATTEMPTS"] == "20"
    assert state["CANONICAL_CP_SCALE_INVALID_LIVE_ATTEMPTS"] == "2"
    assert state["CANONICAL_CP_SCALE_FLOOR1_CURRENT_BOUNDARY"] == (
        "NONE_VERIFIED"
    )
    assert state["CANONICAL_CP_SCALE_NOT_REACHED_PHONES"] == "34"
    assert state["CANONICAL_CP_SCALE_FIRST_CONTRADICTED_BOUNDARY"] == (
        "FLOOR3_VOICE_BOOTSTRAP_CALL_CONTROL_CAPACITY"
    )
    assert state["CANONICAL_CP_SCALE_FAILURE_CLASSIFICATION"] == (
        "AUTHORITATIVE_DESIGN_MISMATCH"
    )
    assert state["CANONICAL_CP_SCALE_VOICE_VERIFICATION"] == "FAIL"
    assert state["ROOT_CAUSE_STATUS"] == "CONFIRMED"
    assert state["PRODUCTION_FIX_STATUS"] == (
        "EXISTING_2811_CME_PHONE_REBALANCE_IMPLEMENTATION_PENDING"
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
        "FRESH_BOUNDARY_LRN_THEN_ATOMIC_REFRESH_FWD"
    )
    assert state["CANONICAL_CP_SCALE_FLOOR2_TIMEOUT_CLASSIFICATION"] == (
        "CONFIRMED_FIXED_BOUNDARY_EXPIRED_DURING_PVST_CONVERGENCE"
    )
    assert state["CANONICAL_CP_SCALE_FLOOR2_NETWORK_ROOT_CAUSE"] == (
        "CONFIRMED"
    )
    assert state["CANONICAL_CP_SCALE_FLOOR2_PRODUCT_FIX"] == (
        "VERIFIED_DELTA_ONLY_PLUS_FRESH_PVST_BOUNDARY_ATOMIC_REFRESH"
    )
    assert state["CANONICAL_CP_SCALE_FLOOR2_CAUSAL_LIVE"] == (
        "VERIFIED_NETWORK_FOUNDATION | BOUNDARY_LRN | "
        "REFRESH_FWD_9_OF_9 | EXTENSION_NOT_ENGAGED"
    )
    assert state["CP_SCALE_STATUS"] == (
        "FLOOR2_VERIFIED_35_OF_35 | FLOOR3_CAPACITY_REBALANCE_REQUIRED"
    )
