from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.packet_tracer_mcp.application.cp_scale_live import CPScaleCheckState
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    DeviceCapabilities,
    EvidenceSource,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    BackendVersionProvenance,
    CapabilityBackend,
    CapabilityProbeResult,
    CapabilitySnapshot,
    CleanupStatus,
    EphemeralUntitledWorkspaceSafetyEvidence,
    ProbeContext,
    ProbeExecutionStatus,
    ProbeIsolationLevel,
    ProbeSession,
    ProbeSessionResult,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import (
    VoiceCapabilityDimension,
    VoiceCapabilityStatus,
)
from src.packet_tracer_mcp.infrastructure.catalog.voice_capabilities import (
    voice_capability_profile,
)
from src.packet_tracer_mcp.infrastructure.execution.call_observability_provider import (
    PacketTracerNativeUiPhoneControlProvider,
)
from src.packet_tracer_mcp.infrastructure.execution.phone_control import (
    PacketTracerNativeUiPhoneControlAdapter,
    UnavailablePhoneControl,
)
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)


BUILD = "9.0.1.0858"
EXECUTED_SHA = "a" * 40
TREE = "b" * 40
INVENTORY = "c" * 64 + "|"
RUN_ID = "call-observability-qualification/run-001"


def _safety(**changes):
    values = dict(
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
        initial_inventory_fingerprint=INVENTORY,
        final_inventory_fingerprint=INVENTORY,
        fixture_removed=True,
        initial_realtime=True,
        final_realtime=True,
        packet_tracer_pids_before=(123,),
        packet_tracer_pids_after=(123,),
        bridge_healthy_before=True,
        bridge_healthy_after=True,
        mailbox_entries_before=(),
        mailbox_entries_after=(),
        source_branch_before="feature/runtime-ripv2",
        source_branch_after="feature/runtime-ripv2",
        source_head_before=EXECUTED_SHA,
        source_head_after=EXECUTED_SHA,
        source_tree_before=TREE,
        source_tree_after=TREE,
        worktree_clean_before=True,
        worktree_clean_after=True,
        runtime_healthy=True,
        crash_detected=False,
        integrity_verified=True,
        session_reusable=True,
        positive_claim_allowed=True,
        failure_reasons=[],
    )
    values.update(changes)
    return EphemeralUntitledWorkspaceSafetyEvidence(**values)


def _snapshot(
    *,
    artifact_path,
    artifact_sha256,
    driver_sha256,
    dimensions=None,
    result_model="2811",
    packet_tracer_version=BUILD,
    safety=None,
):
    values = {
        "schema": "call-observability-qualification-v1",
        "provider_id": "packet-tracer-native-ui-mailbox-v1",
        "execution_method": "packet_tracer_native_ui",
        "driver_source_sha256": driver_sha256,
        "call_control_models": "2811",
        "phone_models": "7960",
        "expectation_results": "established,not_connected",
        "exact_identity": "true",
        "fresh_evidence": "true",
        "teardown_verified": "true",
        "cleanup_empty_observations": "2",
        "realtime_restored": "true",
        "evidence_path": artifact_path,
        "evidence_sha256": artifact_sha256,
        "executed_sha": EXECUTED_SHA,
        "run_identity": RUN_ID,
    }
    values.update(dimensions or {})
    live_safety = safety or _safety()
    result = CapabilityProbeResult(
        probe_id=RUN_ID,
        model=result_model,
        capability="supports_call_observability",
        status=CapabilityStatus.SUPPORTED,
        execution_status=ProbeExecutionStatus.VERIFIED,
        evidence_source=EvidenceSource.MANUAL_VERIFICATION,
        verified=True,
        raw_summary="Native UI ESTABLISHED and NOT_CONNECTED were observed.",
        packet_tracer_version=packet_tracer_version,
        dimensions=values,
        context=ProbeContext(
            probe_id=RUN_ID,
            probe_version="1",
            backend=CapabilityBackend.PACKET_TRACER,
            backend_version=packet_tracer_version,
            device_model=result_model,
            environment_fingerprint="environment/call-qualification",
            initial_inventory_hash=INVENTORY,
            final_inventory_hash=INVENTORY,
            inventory_restored=True,
            isolation_level=ProbeIsolationLevel.FRESH_SESSION_REQUIRED,
            mutations=["2811", "3560-24PS", "7960", "7960"],
            cleanup_status=CleanupStatus.CLEAN,
            result_status=CapabilityStatus.SUPPORTED,
            execution_status=ProbeExecutionStatus.VERIFIED,
            probe_fingerprint="d" * 64,
            live_session_safety=live_safety,
        ),
    )
    return CapabilitySnapshot(
        packet_tracer_version=packet_tracer_version,
        backend_version_provenance=BackendVersionProvenance.DIRECTLY_OBSERVED,
        backend=CapabilityBackend.PACKET_TRACER,
        environment_fingerprint="environment/call-qualification",
        initial_inventory_hash=INVENTORY,
        final_inventory_hash=INVENTORY,
        inventory_restored=True,
        session=ProbeSessionResult(
            session=ProbeSession(
                session_id=RUN_ID,
                started_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
                packet_tracer_version=packet_tracer_version,
                created_devices=["call-r", "call-sw", "call-p1", "call-p2"],
                mutations=["2811", "3560-24PS", "7960", "7960"],
                cleanup_status=CleanupStatus.CLEAN,
            ),
            results=[result],
            cleanup_deleted=["call-p2", "call-p1", "call-sw", "call-r"],
        ),
    )


def _provider(tmp_path, *, snapshot_changes=None, ready=True):
    artifact = tmp_path / "docs" / "reference" / "cp-scale" / "call.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"verification":"VERIFIED"}\n', encoding="utf-8")
    artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    driver = tmp_path / "native_ui_phone_driver.py"
    driver.write_text("# exact qualified driver\n", encoding="utf-8")
    driver_hash = hashlib.sha256(driver.read_bytes()).hexdigest()
    changes = snapshot_changes or {}
    snapshot = _snapshot(
        artifact_path=str(artifact.relative_to(tmp_path)).replace("\\", "/"),
        artifact_sha256=artifact_hash,
        driver_sha256=driver_hash,
        **changes,
    )
    store = CapabilitySnapshotStore(tmp_path / "data" / "capabilities")
    store.save_verified(snapshot)
    exchange = tmp_path / "exchange"
    exchange.mkdir()
    provider = PacketTracerNativeUiPhoneControlProvider(
        governed_root=tmp_path,
        store=store,
        exchange_dir=exchange,
        driver_source_path=driver,
        readiness_probe=lambda *_args: ready,
    )
    return provider, snapshot


def test_verified_capability_selects_the_concrete_native_ui_provider(tmp_path):
    provider, snapshot = _provider(tmp_path)

    evidence = provider.read(BUILD)

    assert evidence.state is CPScaleCheckState.PASSED
    assert evidence.passed_coherently is True
    assert evidence.provider_id == "packet-tracer-native-ui-mailbox-v1"
    assert evidence.call_control_models == ("2811",)
    assert evidence.phone_models == ("7960",)
    assert evidence.qualification_executed_sha == EXECUTED_SHA
    assert evidence.qualification_run_identity == RUN_ID
    assert isinstance(provider.phone_control, PacketTracerNativeUiPhoneControlAdapter)
    assert provider.capability_snapshot_hash == snapshot.stable_hash()


@pytest.mark.parametrize(
    "snapshot_changes",
    (
        {"result_model": "1941"},
        {"dimensions": {"phone_models": "7970"}},
        {"dimensions": {"driver_source_sha256": "e" * 64}},
        {"dimensions": {"evidence_sha256": "f" * 64}},
        {"dimensions": {"executed_sha": "9" * 40}},
        {"safety": _safety(final_device_count=1)},
    ),
)
def test_stale_foreign_or_incoherent_capability_never_selects_provider(
    tmp_path,
    snapshot_changes,
):
    provider, _snapshot_value = _provider(
        tmp_path,
        snapshot_changes=snapshot_changes,
    )

    evidence = provider.read(BUILD)

    assert evidence.state is CPScaleCheckState.FAILED
    assert "qualified" in evidence.error.casefold()
    assert isinstance(provider.phone_control, UnavailablePhoneControl)


def test_qualified_evidence_without_a_live_driver_is_unavailable_not_success(tmp_path):
    provider, _snapshot_value = _provider(tmp_path, ready=False)

    evidence = provider.read(BUILD)

    assert evidence.state is CPScaleCheckState.FAILED
    assert "not ready" in evidence.error.casefold()
    assert isinstance(provider.phone_control, UnavailablePhoneControl)


def test_voice_capability_consumes_the_same_validated_evidence():
    snapshot = _snapshot(
        artifact_path="docs/reference/cp-scale/call.json",
        artifact_sha256="e" * 64,
        driver_sha256="f" * 64,
    )
    evidence = snapshot.session.results[0].evidence()
    assert evidence is not None
    unreviewed = voice_capability_profile(DeviceCapabilities(
        model="2811",
        category="router",
        supports_cme=CapabilityStatus.SUPPORTED,
        supports_dhcp_server=CapabilityStatus.SUPPORTED,
        evidence=[evidence],
    ), packet_tracer_version=BUILD)

    assert unreviewed.status(
        VoiceCapabilityDimension.CALL_INITIATION
    ) is VoiceCapabilityStatus.UNOBSERVABLE
    reviewed = evidence.model_copy(update={
        "source_detail": "verified-store:" + evidence.source_detail,
    })
    profile = voice_capability_profile(DeviceCapabilities(
        model="2811",
        category="router",
        supports_cme=CapabilityStatus.SUPPORTED,
        supports_dhcp_server=CapabilityStatus.SUPPORTED,
        evidence=[reviewed],
    ), packet_tracer_version=BUILD)

    assert profile.status(
        VoiceCapabilityDimension.CALL_INITIATION
    ) is VoiceCapabilityStatus.SUPPORTED
    assert profile.status(
        VoiceCapabilityDimension.CALL_STATE_READBACK
    ) is VoiceCapabilityStatus.SUPPORTED
    assert profile.call_observability_phone_models == ["7960"]
