from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from packet_tracer_mcp.infrastructure.execution.call_observability_provider import (
    PacketTracerNativeUiPhoneControlProvider,
)
from packet_tracer_mcp.infrastructure.persistence.call_observability_evidence import (
    promote_verified_call_observability,
)
from packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)


BUILD = "9.0.1.0858"
HEAD = "a" * 40
TREE = "b" * 40
RUN_ID = "call-observability-qualification-live-001"


def _capture(exchange: Path, name: str, states: list[str]):
    path = exchange / "captures" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"states": states}) + "\n", encoding="utf-8")
    return path.relative_to(exchange).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()


def _call(
    *,
    identifier,
    attempt,
    source,
    destination,
    extension,
    expected,
    states,
    connected,
    artifact,
    sha256,
):
    return {
        "call_expectation_id": identifier,
        "call_attempt_id": attempt,
        "source_phone_id": source,
        "destination_phone_id": destination,
        "dialed_extension": extension,
        "expected_result": expected,
        "status": "verified",
        "states": states,
        "connected": connected,
        "teardown_verified": True,
        "observed_after_ns": 100,
        "fresh_evidence": True,
        "evidence_method": "packet_tracer_native_ui_correlated_state_capture_v1",
        "execution_method": "packet_tracer_native_ui",
        "evidence_artifact_path": artifact,
        "evidence_sha256": sha256,
        "failure_code": "none",
        "message": "",
    }


def _raw(
    tmp_path,
    *,
    status="VERIFIED",
    driver_hash=None,
    backend_managed=False,
):
    driver = (
        tmp_path / "src" / "packet_tracer_mcp" / "infrastructure"
        / "execution" / "native_ui_phone_driver.py"
    )
    driver.parent.mkdir(parents=True)
    driver.write_text("# qualified exact driver\n", encoding="utf-8")
    actual_driver_hash = hashlib.sha256(driver.read_bytes()).hexdigest()
    exchange = tmp_path / "exchange"
    established_path, established_hash = _capture(
        exchange,
        "established.json",
        ["idle", "dialing", "ringing", "connected", "disconnected", "idle"],
    )
    negative_path, negative_hash = _capture(
        exchange,
        "not-connected.json",
        ["idle", "dialing", "failed", "idle"],
    )
    backend_devices = ([{
        "name": "Power Distribution Device0",
        "model": "Power Distribution Device",
        "ports": [],
        "backend_managed": True,
    }] if backend_managed else [])
    environment = {
        "found": True,
        "saved_filename": "",
        "pt_version": BUILD,
        "simulation_mode": False,
        "devices": len(backend_devices),
        "links": 0,
    }
    process = {
        "ProcessName": "PacketTracer",
        "Id": 123,
        "MainWindowHandle": 1,
        "ProductVersion": BUILD,
        "FileVersion": BUILD,
        "Path": r"C:\PacketTracer.exe",
    }
    repository = {
        "branch": "feature/runtime-ripv2",
        "upstream": "cisco/feature/runtime-ripv2",
        "head": HEAD,
        "upstream_head": HEAD,
        "source_tree": TREE,
        "dirty": False,
        "error": "",
        "dirty_error": "",
        "upstream_head_error": "",
        "source_tree_error": "",
    }
    empty = {
        "observed": True,
        "semantic_device_count": 0,
        "backend_managed_device_count": 0,
        "link_count": 0,
        "devices": backend_devices,
        "links": [],
        "message": "",
    }
    raw = {
        "schema": "call-observability-live-v1",
        "scope": "call-observability-qualification",
        "run_identity": RUN_ID,
        "executed_sha": HEAD,
        "source_tree": TREE,
        "packet_tracer_version": BUILD,
        "provider": {
            "provider_id": "packet-tracer-native-ui-mailbox-v1",
            "execution_method": "packet_tracer_native_ui",
            "driver_source": "src/packet_tracer_mcp/infrastructure/execution/native_ui_phone_driver.py",
            "driver_source_sha256": driver_hash or actual_driver_hash,
        },
        "ci": {
            "head": HEAD,
            "run_id": "ci-run-1",
            "successful_check_runs": ["1", "2", "3", "4"],
        },
        "preflight": {
            "exchange_dir": str(exchange),
            "mailbox_entries_before": [],
            "packet_tracer_environment": environment,
            "bridge": {"connected": True},
            "repository": repository,
            "packet_tracer_processes": [process],
        },
        "qualification": {
            "status": status,
            "fixture_models": ["2811", "3560-24PS", "7960", "7960"],
            "voice_plan_id": "callqual/voice-plan",
            "voice_plan_hash": "callqual/voice/hash",
            "calls": [
                _call(
                    identifier="callqual/call/established",
                    attempt="attempt-1",
                    source="callqual/phone/1",
                    destination="callqual/phone/2",
                    extension="3002",
                    expected="established",
                    states=["idle", "dialing", "ringing", "connected", "disconnected", "idle"],
                    connected=True,
                    artifact=established_path,
                    sha256=established_hash,
                ),
                _call(
                    identifier="callqual/call/not-connected",
                    attempt="attempt-2",
                    source="callqual/phone/1",
                    destination="",
                    extension="3999",
                    expected="not_connected",
                    states=["idle", "dialing", "failed", "idle"],
                    connected=False,
                    artifact=negative_path,
                    sha256=negative_hash,
                ),
            ],
            "created_devices": ["r", "sw", "p1", "p2"],
            "created_links": ["uplink", "p1", "p2"],
            "removed_devices": ["p2", "p1", "sw", "r"],
            "baseline": empty,
            "cleanup_first": empty,
            "cleanup_second": empty,
            "cleanup_verified": True,
            "initial_realtime": True,
            "final_realtime": True,
            "errors": [],
        },
        "postflight": {
            "packet_tracer_processes": [process],
            "primary_pid_before": 123,
            "primary_pid_after": 123,
            "bridge": {"connected": True},
            "packet_tracer_environment": environment,
            "mailbox_entries_after": [],
            "repository": repository,
            "errors": [],
        },
    }
    raw_path = tmp_path / "data" / "call-observability.json"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return raw_path, driver, exchange


def test_promotion_writes_hash_pinned_compact_evidence_and_standard_snapshot(tmp_path):
    raw_path, driver, exchange = _raw(tmp_path)

    receipt = promote_verified_call_observability(
        raw_path,
        governed_root=tmp_path,
    )

    compact = json.loads(receipt.evidence_path.read_text(encoding="utf-8"))
    assert receipt.evidence_sha256 == hashlib.sha256(
        receipt.evidence_path.read_bytes()
    ).hexdigest()
    assert compact["classification"] == "VERIFIED"
    assert compact["executed_sha"] == HEAD
    assert compact["run_identity"] == RUN_ID
    assert [item["expected_result"] for item in compact["calls"]] == [
        "established", "not_connected",
    ]
    assert all(
        hashlib.sha256((tmp_path / item["path"]).read_bytes()).hexdigest()
        == item["sha256"]
        for item in compact["captures"]
    )
    store = CapabilitySnapshotStore(
        tmp_path / "docs" / "reference" / "cp-scale" / "call-capabilities"
    )
    snapshots = store.list_verified(BUILD)
    assert len(snapshots) == 1
    assert receipt.capability_snapshot_hash == snapshots[0].stable_hash()

    provider = PacketTracerNativeUiPhoneControlProvider(
        governed_root=tmp_path,
        store=store,
        exchange_dir=exchange,
        driver_source_path=driver,
        readiness_probe=lambda *_args: True,
    )
    assert provider.read(BUILD).passed_coherently is True


def test_promotion_accepts_unchanged_backend_managed_power_device(tmp_path):
    raw_path, _driver, _exchange = _raw(tmp_path, backend_managed=True)

    receipt = promote_verified_call_observability(
        raw_path,
        governed_root=tmp_path,
    )

    assert receipt.evidence_path.is_file()


@pytest.mark.parametrize(
    ("change", "expected"),
    (
        ("status", "VERIFIED"),
        ("driver", "driver"),
    ),
)
def test_promotion_rejects_unverified_or_foreign_driver_without_writing(
    tmp_path,
    change,
    expected,
):
    raw_path, _driver, _exchange = _raw(
        tmp_path,
        status="UNOBSERVABLE" if change == "status" else "VERIFIED",
        driver_hash="f" * 64 if change == "driver" else None,
    )

    with pytest.raises(ValueError, match=expected):
        promote_verified_call_observability(raw_path, governed_root=tmp_path)

    output = tmp_path / "docs" / "reference" / "cp-scale"
    assert not (output / "call-observability-evidence").exists()
    assert not (output / "call-capabilities").exists()
