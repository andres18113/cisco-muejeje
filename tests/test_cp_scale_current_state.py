"""Compact CP-SCALE state authority and legacy handoff compatibility."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

from tests.cp_scale_historical_state import load_historical_pre_router0
from tests.handoff_state import parse_handoff_state


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "docs" / "reference" / "cp-scale" / "current_state.json"
HANDOFF_PATH = ROOT / "handoff.md"


def _historical_live_state(document: dict) -> dict:
    return load_historical_pre_router0(document)["live_state"]


def _historical_gate(document: dict) -> dict:
    return load_historical_pre_router0(document)["offline_operational_gate"]


def test_router0_poe_observer_failure_does_not_promote_or_consume_router0():
    document = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    acquisition = _historical_gate(document)["router0_poe_acquisition"]
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
    gate = _historical_gate(document)
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


def test_current_state_separates_operational_authority_from_history():
    raw = STATE_PATH.read_bytes()
    document = json.loads(raw)

    assert document["schema"] == "cp-scale-current-state-v5"
    assert len(raw) < 16_384
    assert datetime.fromisoformat(document["updated_at"].replace("Z", "+00:00"))
    assert set(document) == {
        "schema",
        "updated_at",
        "operational_state",
        "historical_pre_router0",
    }
    assert "last_live_state" not in document
    assert "current_offline_operational_gate" not in document
    assert "handoff_compatibility" not in document

    operational = document["operational_state"]
    router0 = operational["router0"]
    authority = router0["evidence"]
    authority_path = ROOT / authority["path"]
    authority_raw = authority_path.read_bytes()
    index = json.loads(authority_raw)

    assert operational["authority"] == (
        "HASH_PINNED_ROUTER0_AND_ROUTER3_SUCCESS_INDEXES"
    )
    assert authority_path == (
        ROOT / "docs/reference/cp-scale/router0_successful_run.json"
    )
    assert hashlib.sha256(authority_raw).hexdigest() == authority["sha256"]
    assert authority["run_identity"] == index["run_identity"]
    assert authority["executed_sha"] == index["executed_sha"]
    assert authority["classification"] == index["classification"] == "VERIFIED"
    assert authority["successful_closure"] is index["successful_closure"] is True
    assert router0["executed"] is True
    assert router0["status"] == "VERIFIED_AND_CLEANED"
    assert router0["closure"] == index["closure"]
    assert router0["closure"] == "ROUTER0_BRANCH_VERIFIED_AND_CLEANED"
    assert router0["closure_requires_cleanup"] is True
    assert router0["reexecution_authorized"] is False
    assert index["cleanup"]["first_semantic_devices"] == 0
    assert index["cleanup"]["first_links"] == 0
    assert index["cleanup"]["second_semantic_devices"] == 0
    assert index["cleanup"]["second_links"] == 0
    assert index["cleanup"]["realtime_restored"] is True

    router3 = operational["router3"]
    router3_authority = router3["evidence"]
    router3_raw = (ROOT / router3_authority["path"]).read_bytes()
    router3_index = json.loads(router3_raw)
    assert hashlib.sha256(router3_raw).hexdigest() == router3_authority["sha256"]
    assert router3_authority["run_identity"] == router3_index["run_identity"]
    assert router3_authority["executed_sha"] == router3_index["executed_sha"]
    assert router3_authority["classification"] == "VERIFIED"
    assert router3_authority["successful_closure"] is True
    assert router3["executed"] is True
    assert router3["status"] == "VERIFIED_AND_CLEANED"
    assert router3["verification"] == "VERIFIED"
    assert router3["closure"] == "ROUTER3_BRANCH_VERIFIED_AND_CLEANED"
    assert router3["closure"] == router3_index["closure"]
    assert router3["closure_requires_cleanup"] is True
    assert router3["reexecution_authorized"] is False
    assert router3["live_evidence"] == "HASH_PINNED"
    assert router3["live_evidence_acquired"] is True
    assert router3["live_execution_authorized"] is False
    reconciliation = router3["reconciliation"]
    assert reconciliation == {
        "executed_sha": "d2245d45d442d32f5dfb107b1a715089f1cb8551",
        "evidence_promotion_sha": "f9f419ad76ea06cf6272b5e99726d241ec29efd9",
        "reconciliation_sha_role": "GIT_COMMIT_CONTAINING_THIS_DOCUMENT",
        "executed_sha_is_reconciliation_sha": False,
    }
    assert operational["live_execution_authorized"] is False
    assert operational["next_active_step"] == (
        "READY_FOR_EXPLICIT_FULL_QUALIFICATION_LIVE_AUTHORIZATION"
    )

    history_reference = document["historical_pre_router0"]
    assert set(history_reference) == {
        "classification",
        "governs_current_operation",
        "authorization_effect",
        "artifact",
    }
    assert history_reference["classification"] == (
        "HISTORICAL_PRE_ROUTER0_NON_GOVERNING"
    )
    assert history_reference["governs_current_operation"] is False
    assert history_reference["authorization_effect"] == "NONE"
    assert history_reference["artifact"] == {
        "path": "docs/reference/cp-scale/history/pre_router0.json",
        "sha256": "ce10cbf93737daa5c1a2320b980d00e6d0013802980a7450dc48766f62d176ff",
        "schema": "cp-scale-historical-pre-router0-v1",
    }

    history = load_historical_pre_router0(document)
    historical_gate = history["offline_operational_gate"]
    assert historical_gate["router0_authorized"] is True
    assert historical_gate["router0_precondition"]["attempts_authorized"] == 1
    assert historical_gate["router0_precondition"]["attempts_consumed"] == 0
    assert historical_gate["next_active_step"] == (
        "POE2_ACCESSPOINT_PT_USING_THE_CALIBRATED_PSE_OBSERVABLE"
    )
    assert historical_gate["next_active_step"] != operational["next_active_step"]

    handoff = parse_handoff_state(HANDOFF_PATH.read_text(encoding="utf-8"))
    historical_handoff = history["handoff_compatibility"]
    assert historical_handoff
    for key, expected in historical_handoff.items():
        assert handoff[key] == expected


def test_closed_history_cannot_return_as_an_inline_current_state_payload():
    document = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    reference = document["historical_pre_router0"]

    assert set(reference) == {
        "classification",
        "governs_current_operation",
        "authorization_effect",
        "artifact",
    }
    assert not {
        "live_state",
        "offline_operational_gate",
        "handoff_compatibility",
        "runs",
        "evidence",
        "snapshots",
    }.intersection(reference)


@pytest.mark.parametrize(
    ("defect", "error", "message"),
    (
        ("outside_repository", ValueError, "within repository"),
        ("missing", FileNotFoundError, "does not exist"),
        ("sha256", ValueError, "SHA-256"),
        ("schema", ValueError, "schema reference"),
        ("classification", ValueError, "non-governing"),
    ),
)
def test_historical_loader_fails_closed_on_invalid_references(
    defect,
    error,
    message,
):
    document = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    defective = deepcopy(document)
    reference = defective["historical_pre_router0"]

    if defect == "outside_repository":
        reference["artifact"]["path"] = "../outside.json"
    elif defect == "missing":
        reference["artifact"]["path"] = "docs/reference/cp-scale/history/missing.json"
    elif defect == "sha256":
        reference["artifact"]["sha256"] = "0" * 64
    elif defect == "schema":
        reference["artifact"]["schema"] = "wrong-schema"
    else:
        reference["classification"] = "GOVERNING"

    with pytest.raises(error, match=message):
        load_historical_pre_router0(defective)


def test_router0_precondition_retains_product_refusal_without_consuming_live():
    document = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    gate = _historical_gate(document)
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
    state = _historical_live_state(document)

    assert state["evidence"]
    for item in state["evidence"]:
        path = ROOT / item["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]

    poe = _historical_gate(document)[
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
    gate = _historical_gate(document)
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
    family = _historical_gate(document)[
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
    gate = _historical_gate(document)
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
    gate = _historical_gate(document)
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
    api = _historical_gate(document)["poe_inline_observable"][
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
