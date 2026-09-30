"""Contract tests for correlated native-UI phone-control receipts."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import pytest

from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.voice_plan import (
    CallExpectation,
    CallExpectationResult,
)
from packet_tracer_mcp.domain.enterprise.models.voice_runtime import (
    CallState,
    PhoneExecutionMethod,
)
from packet_tracer_mcp.infrastructure.execution.native_ui_phone_driver import (
    PacketTracerNativeUiCallDriver,
)
from packet_tracer_mcp.infrastructure.execution.phone_control import (
    PacketTracerNativeUiPhoneControlAdapter,
)


def _write_receipt_atomic(path: Path, payload: dict[str, object]) -> None:
    """Publish a complete fake-provider receipt at the observable path."""
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _await_provider_request(root: Path, pattern: str) -> tuple[Path, dict]:
    """Wait within the existing bound for complete readable request bytes."""
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        for request_path in root.glob(pattern):
            try:
                request = json.loads(request_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(request, dict):
                return request_path, request
        time.sleep(0.005)
    raise AssertionError("No complete provider request arrived within the deadline.")


def _expectation(expected_result=CallExpectationResult.ESTABLISHED):
    return CallExpectation(
        id="call/qualification/established",
        source_phone_id="phone/qualification/1",
        source_extension="3001",
        dialed_extension=(
            "3002" if expected_result is CallExpectationResult.ESTABLISHED else "3999"
        ),
        expected_target_phone_id=(
            "phone/qualification/2"
            if expected_result is CallExpectationResult.ESTABLISHED
            else ""
        ),
        expected_result=expected_result,
        site_id="call-observability-qualification",
    )


def _serve_one_receipt(root: Path, *, mutate=None):
    def worker():
        request_path, request = _await_provider_request(root, "*.request.json")
        positive = bool(request["destination_phone_id"])
        source_states = (
            ["idle", "dialing", "ringing", "connected", "disconnected", "idle"]
            if positive
            else ["idle", "dialing", "failed", "idle"]
        )
        samples = [
            {
                "phone_id": request["source_phone_id"],
                "device_name": request["source_device_name"],
                "state": state,
                "observed_ns": request["started_ns"] + index + 1,
                "capture_sha256": f"{index + 1:064x}",
            }
            for index, state in enumerate(source_states)
        ]
        if positive:
            samples.extend(
                {
                    "phone_id": request["destination_phone_id"],
                    "device_name": request["destination_device_name"],
                    "state": state,
                    "observed_ns": request["started_ns"] + index + 20,
                    "capture_sha256": f"{index + 20:064x}",
                }
                for index, state in enumerate(
                    ["idle", "ringing", "connected", "disconnected", "idle"]
                )
            )
        artifact = root / "captures" / "call-qualification.json"
        artifact.parent.mkdir(exist_ok=True)
        artifact.write_text(json.dumps({"states": samples}), encoding="utf-8")
        artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
        receipt = {
            "schema": request["schema"],
            "provider_id": request["provider_id"],
            "request_fingerprint": request["request_fingerprint"],
            "call_expectation_id": request["call_expectation_id"],
            "call_attempt_id": request["call_attempt_id"],
            "source_phone_id": request["source_phone_id"],
            "source_device_name": request["source_device_name"],
            "destination_phone_id": request["destination_phone_id"],
            "destination_device_name": request["destination_device_name"],
            "dialed_extension": request["dialed_extension"],
            "states": samples,
            "evidence_method": "packet_tracer_native_ui_correlated_state_capture_v1",
            "evidence_artifact_path": "captures/call-qualification.json",
            "evidence_sha256": artifact_hash,
        }
        if mutate is not None:
            mutate(receipt, request)
        receipt_path = Path(str(request_path).replace(".request.json", ".receipt.json"))
        _write_receipt_atomic(receipt_path, receipt)

    thread = threading.Thread(target=worker)
    thread.start()
    return thread


def _serve_readiness(root: Path, *, mutate=None):
    def worker():
        request_path, request = _await_provider_request(
            root, "*.readiness.request.json"
        )
        receipt = {
            "schema": request["schema"],
            "provider_id": request["provider_id"],
            "request_id": request["request_id"],
            "request_fingerprint": request["request_fingerprint"],
            "packet_tracer_version": request["packet_tracer_version"],
            "driver_source_sha256": request["driver_source_sha256"],
            "observed_ns": request["requested_ns"] + 1,
            "ready": True,
        }
        if mutate is not None:
            mutate(receipt, request)
        receipt_path = Path(
            str(request_path).replace(
                ".readiness.request.json",
                ".readiness.receipt.json",
            )
        )
        _write_receipt_atomic(receipt_path, receipt)

    thread = threading.Thread(target=worker)
    thread.start()
    return thread


@pytest.mark.parametrize(
    ("expected_result", "connected", "source_states"),
    (
        (
            CallExpectationResult.ESTABLISHED,
            True,
            [
                CallState.IDLE,
                CallState.DIALING,
                CallState.RINGING,
                CallState.CONNECTED,
                CallState.DISCONNECTED,
                CallState.IDLE,
            ],
        ),
        (
            CallExpectationResult.NOT_CONNECTED,
            False,
            [CallState.IDLE, CallState.DIALING, CallState.FAILED, CallState.IDLE],
        ),
    ),
)
def test_native_ui_driver_returns_exact_fresh_typed_call_lifecycle(
    tmp_path,
    expected_result,
    connected,
    source_states,
):
    """A complete correlated receipt produces the exact typed lifecycle."""
    expectation = _expectation(expected_result)
    thread = _serve_one_receipt(tmp_path)
    driver = PacketTracerNativeUiCallDriver(
        exchange_dir=tmp_path,
        physical_phone_names={
            "phone/qualification/1": "__MCP_CALL_QUAL_P1",
            "phone/qualification/2": "__MCP_CALL_QUAL_P2",
        },
        timeout_seconds=2,
    )
    control = PacketTracerNativeUiPhoneControlAdapter(driver)

    observed = control.execute_call(expectation, "attempt/exact-001", 10_000)
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert observed.call_expectation_id == expectation.id
    assert observed.call_attempt_id == "attempt/exact-001"
    assert observed.source_phone_id == expectation.source_phone_id
    assert observed.destination_phone_id == expectation.expected_target_phone_id
    assert observed.dialed_extension == expectation.dialed_extension
    assert observed.status is ActionExecutionStatus.VERIFIED
    assert observed.states == source_states
    assert observed.connected is connected
    assert observed.teardown_verified is True
    assert observed.observed_after_ns > 10_000
    assert observed.fresh_evidence is True
    assert observed.evidence_method == (
        "packet_tracer_native_ui_correlated_state_capture_v1"
    )
    assert observed.execution_method is PhoneExecutionMethod.PACKET_TRACER_NATIVE_UI
    assert observed.evidence_artifact_path == "captures/call-qualification.json"
    artifact = tmp_path / observed.evidence_artifact_path
    assert observed.evidence_sha256 == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert list(tmp_path.glob("*.request.json")) == []
    assert list(tmp_path.glob("*.receipt.json")) == []


@pytest.mark.parametrize(
    "defect",
    (
        "foreign-attempt",
        "foreign-source",
        "foreign-destination",
        "foreign-extension",
        "stale",
        "bad-artifact-hash",
        "missing-teardown",
    ),
)
def test_native_ui_driver_rejects_foreign_stale_or_incomplete_receipts(
    tmp_path,
    defect,
):
    """Identity, freshness, artifact, and teardown defects fail closed."""
    expectation = _expectation()

    def mutate(receipt, request):
        if defect == "foreign-attempt":
            receipt["call_attempt_id"] = "attempt/foreign"
        elif defect == "foreign-source":
            receipt["source_phone_id"] = "phone/foreign"
        elif defect == "foreign-destination":
            receipt["destination_phone_id"] = "phone/foreign"
        elif defect == "foreign-extension":
            receipt["dialed_extension"] = "7777"
        elif defect == "stale":
            receipt["states"][0]["observed_ns"] = request["started_ns"] - 1
        elif defect == "bad-artifact-hash":
            receipt["evidence_sha256"] = "not-a-sha"
        else:
            receipt["states"] = [
                item
                for item in receipt["states"]
                if item["state"] not in {"disconnected", "idle"}
            ]

    thread = _serve_one_receipt(tmp_path, mutate=mutate)
    driver = PacketTracerNativeUiCallDriver(
        exchange_dir=tmp_path,
        physical_phone_names={
            "phone/qualification/1": "__MCP_CALL_QUAL_P1",
            "phone/qualification/2": "__MCP_CALL_QUAL_P2",
        },
        timeout_seconds=2,
    )
    observed = PacketTracerNativeUiPhoneControlAdapter(driver).execute_call(
        expectation,
        "attempt/exact-001",
        10_000,
    )
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert observed.status is ActionExecutionStatus.UNOBSERVABLE
    assert observed.call_expectation_id == expectation.id
    assert observed.call_attempt_id == "attempt/exact-001"
    assert observed.source_phone_id == expectation.source_phone_id
    assert observed.destination_phone_id == expectation.expected_target_phone_id
    assert observed.dialed_extension == expectation.dialed_extension
    assert observed.fresh_evidence is False
    assert observed.connected is False
    assert observed.teardown_verified is False
    assert observed.execution_method is PhoneExecutionMethod.PACKET_TRACER_NATIVE_UI
    assert list(tmp_path.glob("*.request.json")) == []
    assert list(tmp_path.glob("*.receipt.json")) == []


@pytest.mark.parametrize("defect", ("", "foreign", "stale", "not-ready"))
def test_native_ui_driver_readiness_is_a_fresh_correlated_handshake(
    tmp_path,
    defect,
):
    """Readiness requires the exact current provider receipt."""

    def mutate(receipt, request):
        if defect == "foreign":
            receipt["request_id"] = "readiness/foreign"
        elif defect == "stale":
            receipt["observed_ns"] = request["requested_ns"] - 1
        elif defect == "not-ready":
            receipt["ready"] = False

    thread = _serve_readiness(tmp_path, mutate=mutate)
    driver = PacketTracerNativeUiCallDriver(
        exchange_dir=tmp_path,
        physical_phone_names={},
        timeout_seconds=2,
    )

    ready = driver.probe_readiness("9.0.1.0858", "b" * 64)
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert ready is (not defect)
    assert list(tmp_path.glob("*.readiness.request.json")) == []
    assert list(tmp_path.glob("*.readiness.receipt.json")) == []


@pytest.mark.parametrize("transient", ["permission", "partial_json"])
def test_simulated_readiness_provider_waits_for_complete_readable_request(
    tmp_path, monkeypatch, transient
):
    """A published path can still be locked or have incomplete request bytes."""
    original_read = Path.read_text
    reads = 0

    def read_after_publication(path, *args, **kwargs):
        nonlocal reads
        if path.parent == tmp_path and path.name.endswith(".readiness.request.json"):
            reads += 1
            if reads == 1:
                if transient == "permission":
                    raise PermissionError("writer still holds the request")
                raise json.JSONDecodeError("request bytes incomplete", "", 0)
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_after_publication)
    thread = _serve_readiness(tmp_path)
    driver = PacketTracerNativeUiCallDriver(
        exchange_dir=tmp_path,
        physical_phone_names={},
        timeout_seconds=2,
    )
    ready = driver.probe_readiness("9.0.1.0858", "b" * 64)
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert ready is True
    assert reads >= 2
