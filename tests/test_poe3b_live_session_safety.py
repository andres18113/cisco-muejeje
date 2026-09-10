"""Fail-closed contracts for the POE-3B ephemeral LIVE safety mode."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    EvidenceSource,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    CapabilityProbeResult,
    CapabilitySnapshot,
    EphemeralUntitledWorkspaceSafetyEvidence,
    LiveSessionSafetyEvidence,
    LiveSessionSafetyMode,
    ProbeExecutionStatus,
    ProbeSession,
    ProbeSessionResult,
)
from src.packet_tracer_mcp.domain.enterprise.rules.live_session_safety import (
    validate_live_session_positive_admission,
)
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
    CorruptCapabilitySnapshotError,
)
from tests.poe_session_safety import healthy_live_session_safety


def _healthy_ephemeral_safety() -> EphemeralUntitledWorkspaceSafetyEvidence:
    return EphemeralUntitledWorkspaceSafetyEvidence(
        initial_device_count=0,
        final_device_count=0,
        initial_link_count=0,
        final_link_count=0,
        initial_saved_filename="",
        final_saved_filename="",
        authorized_file_operations=(),
        attempted_file_operations=(),
        denied_file_operations=(),
        invoked_file_operations=(),
        completed_file_operations=(),
        indeterminate_file_operations=(),
        initial_inventory_fingerprint=(
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            "|backend-managed-device"
        ),
        final_inventory_fingerprint=(
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            "|backend-managed-device"
        ),
        fixture_removed=True,
        initial_realtime=True,
        final_realtime=True,
        packet_tracer_pids_before=(4242,),
        packet_tracer_pids_after=(4242,),
        bridge_healthy_before=True,
        bridge_healthy_after=True,
        mailbox_entries_before=(),
        mailbox_entries_after=(),
        source_branch_before="feature/runtime-ripv2",
        source_branch_after="feature/runtime-ripv2",
        source_head_before="e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43",
        source_head_after="e9e26b3f7cb967cad70d3c5585cafc2c3c46ef43",
        source_tree_before="f4bcd2aa798465ebc6f354746d22085375cbd8d8",
        source_tree_after="f4bcd2aa798465ebc6f354746d22085375cbd8d8",
        worktree_clean_before=True,
        worktree_clean_after=True,
        runtime_healthy=True,
        crash_detected=False,
        integrity_verified=True,
        session_reusable=True,
        positive_claim_allowed=True,
    )


def _snapshot_with_safety(
    safety: LiveSessionSafetyEvidence | EphemeralUntitledWorkspaceSafetyEvidence,
) -> CapabilitySnapshot:
    result = CapabilityProbeResult(
        probe_id="poe-delivery-qualification",
        model="3560-24PS",
        capability="supports_poe",
        execution_status=ProbeExecutionStatus.VERIFIED,
        evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME,
        context={
            "probe_id": "poe-delivery-qualification",
            "device_model": "3560-24PS",
            "live_session_safety": safety,
        },
    )
    return CapabilitySnapshot(
        session=ProbeSessionResult(
            session=ProbeSession(session_id="poe3b-round-trip"),
            results=[result],
        ),
    )


def test_guarded_evidence_keeps_legacy_serialized_shape_and_admission() -> None:
    evidence = healthy_live_session_safety()

    assert evidence.mode is LiveSessionSafetyMode.GUARDED_PTS_COPY
    assert set(evidence.model_dump(mode="json")) == {
        "path_identity_semantics",
        "canonical_path",
        "canonical_pre_run_sha256",
        "canonical_observed_post_run_sha256",
        "canonical_verified_sha256",
        "disposable_path",
        "disposable_pre_run_sha256",
        "disposable_post_run_sha256",
        "active_workspace_binding",
        "unexpected_canonical_modification",
        "disposable_modified",
        "restoration_attempted",
        "restoration_verified",
        "runtime_healthy",
        "crash_detected",
        "integrity_verified",
        "session_reusable",
        "positive_claim_allowed",
        "failure_reasons",
    }
    assert validate_live_session_positive_admission(evidence).is_valid


def test_complete_ephemeral_evidence_is_admitted() -> None:
    evidence = _healthy_ephemeral_safety()

    assert evidence.mode is LiveSessionSafetyMode.EPHEMERAL_UNTITLED_WORKSPACE
    assert validate_live_session_positive_admission(evidence).is_valid


@pytest.mark.parametrize(
    "malformed_update",
    [
        {"initial_device_count": False},
        {"final_link_count": "0"},
        {"initial_saved_filename": b""},
        {"authorized_file_operations": []},
        {"attempted_file_operations": []},
        {
            "initial_inventory_fingerprint": (
                b"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|"
            )
        },
        {"fixture_removed": 1},
        {"packet_tracer_pids_before": (True,)},
        {"mailbox_entries_before": []},
        {"source_branch_before": b"feature/runtime-ripv2"},
        {"failure_reasons": ()},
    ],
    ids=[
        "boolean-as-count",
        "string-as-count",
        "bytes-as-filename",
        "list-as-file-ledger",
        "list-as-attempt-ledger",
        "bytes-as-inventory",
        "integer-as-boolean",
        "boolean-as-pid",
        "list-as-mailbox",
        "bytes-as-branch",
        "tuple-as-failure-list",
    ],
)
def test_ephemeral_model_validate_rejects_coercible_values(
    malformed_update: dict[str, object],
) -> None:
    payload = _healthy_ephemeral_safety().model_dump(mode="python")
    payload.update(malformed_update)

    with pytest.raises(ValidationError):
        EphemeralUntitledWorkspaceSafetyEvidence.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "malformed_value"),
    [
        ("initial_device_count", False),
        ("fixture_removed", 1),
        ("packet_tracer_pids_before", [True]),
    ],
)
def test_capability_snapshot_json_rejects_coercible_ephemeral_values(
    field: str,
    malformed_value: object,
) -> None:
    snapshot = _snapshot_with_safety(_healthy_ephemeral_safety())
    payload = json.loads(snapshot.model_dump_json())
    safety = payload["session"]["results"][0]["context"]["live_session_safety"]
    safety[field] = malformed_value

    with pytest.raises(ValidationError):
        CapabilitySnapshot.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("mode", [[], {}], ids=["array", "object"])
def test_snapshot_json_refuses_unhashable_safety_mode(mode) -> None:
    payload = json.loads(
        _snapshot_with_safety(_healthy_ephemeral_safety()).model_dump_json(),
    )
    payload["session"]["results"][0]["context"]["live_session_safety"]["mode"] = mode

    with pytest.raises(ValidationError):
        CapabilitySnapshot.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("mode", [[], {}], ids=["array", "object"])
def test_store_reports_unhashable_safety_mode_as_snapshot_corruption(
    tmp_path, mode,
) -> None:
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    snapshot = _snapshot_with_safety(_healthy_ephemeral_safety())
    written = store.save_runtime(snapshot)
    payload = json.loads(written.read_text(encoding="utf-8"))
    payload["session"]["results"][0]["context"]["live_session_safety"]["mode"] = mode
    written.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CorruptCapabilitySnapshotError) as raised:
        store.list_runtime(snapshot.packet_tracer_version)
    assert raised.value.path == written


@pytest.mark.parametrize(
    "unsafe_update",
    [
        {
            "initial_inventory_fingerprint": "opaque-but-not-encoded",
            "final_inventory_fingerprint": "opaque-but-not-encoded",
        },
        {
            "initial_inventory_fingerprint": "a" * 64,
            "final_inventory_fingerprint": "a" * 64,
        },
        {
            "initial_inventory_fingerprint": f"{'A' * 64}|",
            "final_inventory_fingerprint": f"{'A' * 64}|",
        },
        {
            "initial_inventory_fingerprint": f"{'a' * 64}|z;a",
            "final_inventory_fingerprint": f"{'a' * 64}|z;a",
        },
        {
            "source_head_before": "same-arbitrary-head",
            "source_head_after": "same-arbitrary-head",
        },
        {
            "source_tree_before": "B" * 40,
            "source_tree_after": "B" * 40,
        },
    ],
    ids=[
        "unencoded-inventory",
        "legacy-inventory-without-separator",
        "uppercase-inventory-semantic-hash",
        "noncanonical-inventory-managed-order",
        "malformed-git-head",
        "uppercase-git-tree",
    ],
)
def test_ephemeral_evidence_rejects_malformed_equal_identities(
    unsafe_update: dict[str, object],
) -> None:
    evidence = _healthy_ephemeral_safety().model_copy(update=unsafe_update)

    assert not validate_live_session_positive_admission(evidence).is_valid


@pytest.mark.parametrize(
    "unsafe_update",
    [
        {"mode": LiveSessionSafetyMode.GUARDED_PTS_COPY},
        {"initial_device_count": None},
        {"final_device_count": 1},
        {"initial_link_count": 1},
        {"final_link_count": None},
        {"initial_saved_filename": None},
        {"final_saved_filename": "qualification.pts"},
        {"authorized_file_operations": None},
        {"authorized_file_operations": ("save",)},
        {"attempted_file_operations": None},
        {"attempted_file_operations": ("save",)},
        {"denied_file_operations": None},
        {"denied_file_operations": ("open",)},
        {"invoked_file_operations": None},
        {"invoked_file_operations": ("save_as",)},
        {"completed_file_operations": None},
        {"completed_file_operations": ("open",)},
        {"indeterminate_file_operations": None},
        {"indeterminate_file_operations": ("save",)},
        {"initial_inventory_fingerprint": ""},
        {"initial_inventory_fingerprint": "   "},
        {"final_inventory_fingerprint": "different-inventory"},
        {"fixture_removed": False},
        {"fixture_removed": 1},
        {"initial_realtime": None},
        {"final_realtime": False},
        {"packet_tracer_pids_before": None},
        {"packet_tracer_pids_before": ()},
        {"packet_tracer_pids_before": (0,)},
        {"packet_tracer_pids_before": (4242, 4243)},
        {"packet_tracer_pids_after": (4243,)},
        {"bridge_healthy_before": None},
        {"bridge_healthy_after": False},
        {"mailbox_entries_before": None},
        {"mailbox_entries_after": ("stale-response.json",)},
        {"source_branch_before": ""},
        {"source_branch_after": "other-branch"},
        {"source_head_before": ""},
        {"source_head_after": "different-head"},
        {"source_tree_before": ""},
        {"source_tree_after": "different-tree"},
        {"worktree_clean_before": None},
        {"worktree_clean_after": False},
        {"runtime_healthy": None},
        {"runtime_healthy": 1},
        {"crash_detected": None},
        {"crash_detected": True},
        {"integrity_verified": False},
        {"session_reusable": False},
        {"positive_claim_allowed": False},
        {"failure_reasons": ["post-run integrity failure"]},
    ],
    ids=[
        "contradictory-mode",
        "initial-device-count-missing",
        "final-device-count-nonzero",
        "initial-link-count-nonzero",
        "final-link-count-missing",
        "initial-saved-filename-missing",
        "final-saved-filename-nonempty",
        "authorized-file-ledger-missing",
        "authorized-file-operation-present",
        "attempted-file-ledger-missing",
        "attempted-file-operation-present",
        "denied-file-ledger-missing",
        "denied-file-operation-present",
        "invoked-file-ledger-missing",
        "invoked-file-operation-present",
        "completed-file-ledger-missing",
        "completed-file-operation-present",
        "indeterminate-file-ledger-missing",
        "indeterminate-file-operation-present",
        "initial-inventory-missing",
        "initial-inventory-blank",
        "inventory-changed",
        "fixture-not-removed",
        "fixture-merely-truthy",
        "initial-realtime-missing",
        "final-realtime-false",
        "initial-pid-missing",
        "initial-pid-empty",
        "initial-pid-nonpositive",
        "initial-pid-multiple",
        "pid-changed",
        "bridge-before-missing",
        "bridge-after-false",
        "mailbox-before-missing",
        "mailbox-after-nonempty",
        "branch-missing",
        "branch-changed",
        "head-missing",
        "head-changed",
        "tree-missing",
        "tree-changed",
        "worktree-before-missing",
        "worktree-after-dirty",
        "runtime-health-missing",
        "runtime-health-merely-truthy",
        "crash-status-missing",
        "crash-detected",
        "integrity-not-verified",
        "session-not-reusable",
        "claim-not-allowed",
        "failure-reported",
    ],
)
def test_ephemeral_evidence_fails_closed_for_incomplete_or_contradictory_facts(
    unsafe_update: dict[str, object],
) -> None:
    evidence = _healthy_ephemeral_safety().model_copy(update=unsafe_update)

    assert not validate_live_session_positive_admission(evidence).is_valid


@pytest.mark.parametrize(
    ("safety", "expected_type"),
    [
        (_healthy_ephemeral_safety(), EphemeralUntitledWorkspaceSafetyEvidence),
        (healthy_live_session_safety(), LiveSessionSafetyEvidence),
    ],
    ids=["ephemeral", "guarded"],
)
def test_safety_mode_survives_capability_snapshot_json_parsing(
    safety: LiveSessionSafetyEvidence | EphemeralUntitledWorkspaceSafetyEvidence,
    expected_type: type[
        LiveSessionSafetyEvidence | EphemeralUntitledWorkspaceSafetyEvidence
    ],
) -> None:
    snapshot = _snapshot_with_safety(safety)
    serialized = snapshot.model_dump_json()

    restored = CapabilitySnapshot.model_validate_json(serialized)

    context = restored.session.results[0].context
    assert context is not None
    assert isinstance(context.live_session_safety, expected_type)
    assert context.live_session_safety == safety
    assert restored.stable_hash() == snapshot.stable_hash()
