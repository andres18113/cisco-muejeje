"""Correlated file exchange for one Packet Tracer native-UI phone call.

The UI controller is deliberately outside the application process.  This
driver publishes one immutable request, accepts one matching receipt, and
derives the typed call result from observed state samples.  It never retries a
call or accepts a receipt merely because a UI action ran.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ...domain.enterprise.models.configuration_runtime import ActionExecutionStatus
from ...domain.enterprise.models.voice_plan import CallExpectationResult, VoicePlan
from ...domain.enterprise.models.voice_runtime import CallState, RuntimeCallObservation
from ...shared.utils import resolve_within, safe_name_component


NATIVE_UI_CALL_SCHEMA = "packet-tracer-native-ui-call-v1"
NATIVE_UI_PROVIDER_ID = "packet-tracer-native-ui-mailbox-v1"
NATIVE_UI_EVIDENCE_METHOD = "packet_tracer_native_ui_correlated_state_capture_v1"
NATIVE_UI_READINESS_SCHEMA = "packet-tracer-native-ui-readiness-v1"


class NativeUiCallRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", populate_by_name=True)

    schema_id: str = Field(default=NATIVE_UI_CALL_SCHEMA, alias="schema")
    provider_id: str = NATIVE_UI_PROVIDER_ID
    request_fingerprint: str
    call_expectation_id: str
    call_attempt_id: str
    source_phone_id: str
    source_device_name: str
    destination_phone_id: str
    destination_device_name: str
    dialed_extension: str
    expected_result: CallExpectationResult
    started_ns: int
    deadline_ns: int


class NativeUiCallStateSample(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    phone_id: str
    device_name: str
    state: CallState
    observed_ns: int
    capture_sha256: str


class NativeUiCallReceipt(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", populate_by_name=True)

    schema_id: str = Field(alias="schema")
    provider_id: str
    request_fingerprint: str
    call_expectation_id: str
    call_attempt_id: str
    source_phone_id: str
    source_device_name: str
    destination_phone_id: str
    destination_device_name: str
    dialed_extension: str
    states: list[NativeUiCallStateSample] = Field(default_factory=list)
    evidence_method: str
    evidence_artifact_path: str
    evidence_sha256: str


class NativeUiReadinessRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", populate_by_name=True)

    schema_id: str = Field(default=NATIVE_UI_READINESS_SCHEMA, alias="schema")
    provider_id: str = NATIVE_UI_PROVIDER_ID
    request_id: str
    request_fingerprint: str
    packet_tracer_version: str
    driver_source_sha256: str
    requested_ns: int
    deadline_ns: int


class NativeUiReadinessReceipt(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", populate_by_name=True)

    schema_id: str = Field(alias="schema")
    provider_id: str
    request_id: str
    request_fingerprint: str
    packet_tracer_version: str
    driver_source_sha256: str
    observed_ns: int
    ready: bool


_ESTABLISHED_SOURCE = (
    CallState.IDLE,
    CallState.DIALING,
    CallState.RINGING,
    CallState.CONNECTED,
    CallState.DISCONNECTED,
    CallState.IDLE,
)
_ESTABLISHED_DESTINATION = (
    CallState.IDLE,
    CallState.RINGING,
    CallState.CONNECTED,
    CallState.DISCONNECTED,
    CallState.IDLE,
)
_NOT_CONNECTED_SOURCE = (
    CallState.IDLE,
    CallState.DIALING,
    CallState.FAILED,
    CallState.IDLE,
)


class PacketTracerNativeUiCallDriver:
    """Exchange one exact call request with the native-UI controller."""

    def __init__(
        self,
        *,
        exchange_dir: str | Path,
        physical_phone_names: dict[str, str],
        timeout_seconds: float,
        readiness_timeout_seconds: float = 2.0,
        monotonic_clock=time.monotonic,
        wall_clock_ns=time.time_ns,
        sleeper=time.sleep,
    ) -> None:
        self._exchange_dir = Path(exchange_dir)
        self._physical_phone_names = dict(physical_phone_names)
        self._timeout_seconds = float(timeout_seconds)
        self._readiness_timeout_seconds = float(readiness_timeout_seconds)
        self._monotonic_clock = monotonic_clock
        self._wall_clock_ns = wall_clock_ns
        self._sleeper = sleeper

    def bind_plan(self, plan: VoicePlan) -> None:
        """Bind semantic phone IDs to the plan's exact physical names."""

        names: dict[str, str] = {}
        for assignment in plan.phone_assignments:
            previous = names.get(assignment.phone_id)
            if previous is not None and previous != assignment.physical_device_name:
                raise ValueError(
                    f"Phone {assignment.phone_id!r} has contradictory physical names."
                )
            names[assignment.phone_id] = assignment.physical_device_name
        self._physical_phone_names = names

    def probe_readiness(
        self,
        packet_tracer_version: str,
        driver_source_sha256: str,
    ) -> bool:
        """Require one fresh response from the exact external UI controller."""

        if (
            not packet_tracer_version
            or not _is_sha256(driver_source_sha256)
            or self._readiness_timeout_seconds <= 0
        ):
            return False
        request_id = f"readiness-{uuid4().hex}"
        requested_ns = self._wall_clock_ns()
        values = {
            "schema": NATIVE_UI_READINESS_SCHEMA,
            "provider_id": NATIVE_UI_PROVIDER_ID,
            "request_id": request_id,
            "packet_tracer_version": packet_tracer_version,
            "driver_source_sha256": driver_source_sha256,
            "requested_ns": requested_ns,
            "deadline_ns": requested_ns
            + int(self._readiness_timeout_seconds * 1_000_000_000),
        }
        request = NativeUiReadinessRequest(
            request_fingerprint=_fingerprint(values),
            **values,
        )
        stem = safe_name_component(request_id, "readiness")
        try:
            self._exchange_dir.mkdir(parents=True, exist_ok=True)
            request_path = resolve_within(
                self._exchange_dir, f"{stem}.readiness.request.json",
            )
            receipt_path = resolve_within(
                self._exchange_dir, f"{stem}.readiness.receipt.json",
            )
            if request_path.exists() or receipt_path.exists():
                return False
            _write_atomic(
                request_path,
                request.model_dump_json(indent=2, by_alias=True),
            )
        except (OSError, ValueError):
            return False
        try:
            deadline = self._monotonic_clock() + self._readiness_timeout_seconds
            while self._monotonic_clock() <= deadline:
                if receipt_path.exists():
                    break
                self._sleeper(min(0.05, self._readiness_timeout_seconds))
            else:
                return False
            try:
                receipt = NativeUiReadinessReceipt.model_validate_json(
                    receipt_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError, ValidationError):
                return False
            return bool(
                receipt.schema_id == request.schema_id
                and receipt.provider_id == request.provider_id
                and receipt.request_id == request.request_id
                and receipt.request_fingerprint == request.request_fingerprint
                and receipt.packet_tracer_version == request.packet_tracer_version
                and receipt.driver_source_sha256 == request.driver_source_sha256
                and request.requested_ns <= receipt.observed_ns <= request.deadline_ns
                and receipt.ready is True
            )
        finally:
            if not _remove_owned_exchange_files(request_path, receipt_path):
                return False

    def __call__(self, expectation, call_attempt_id, started_ns):
        source_name = self._physical_phone_names.get(expectation.source_phone_id, "")
        destination_name = (
            self._physical_phone_names.get(expectation.expected_target_phone_id, "")
            if expectation.expected_target_phone_id else ""
        )
        if (
            not source_name
            or expectation.expected_target_phone_id and not destination_name
            or self._timeout_seconds <= 0
        ):
            return self._unobservable(
                expectation, call_attempt_id, started_ns,
                "The native-UI call target mapping or timeout is unavailable.",
            )

        timeout_ns = int(self._timeout_seconds * 1_000_000_000)
        request_values = {
            "schema": NATIVE_UI_CALL_SCHEMA,
            "provider_id": NATIVE_UI_PROVIDER_ID,
            "call_expectation_id": expectation.id,
            "call_attempt_id": call_attempt_id,
            "source_phone_id": expectation.source_phone_id,
            "source_device_name": source_name,
            "destination_phone_id": expectation.expected_target_phone_id,
            "destination_device_name": destination_name,
            "dialed_extension": expectation.dialed_extension,
            "expected_result": expectation.expected_result,
            "started_ns": started_ns,
            "deadline_ns": started_ns + timeout_ns,
        }
        fingerprint = _fingerprint(request_values)
        request = NativeUiCallRequest(
            request_fingerprint=fingerprint,
            **request_values,
        )
        stem = safe_name_component(
            hashlib.sha256(
                f"{expectation.id}\0{call_attempt_id}".encode("utf-8")
            ).hexdigest(),
            "call",
        )
        try:
            self._exchange_dir.mkdir(parents=True, exist_ok=True)
            request_path = resolve_within(
                self._exchange_dir, f"{stem}.request.json",
            )
            receipt_path = resolve_within(
                self._exchange_dir, f"{stem}.receipt.json",
            )
            if request_path.exists() or receipt_path.exists():
                return self._unobservable(
                    expectation, call_attempt_id, started_ns,
                    "The native-UI exchange already contains this call identity.",
                )
            _write_atomic(
                request_path,
                request.model_dump_json(indent=2, by_alias=True),
            )
        except (OSError, ValueError) as exc:
            return self._unobservable(
                expectation, call_attempt_id, started_ns,
                f"The native-UI request could not be published: {exc}",
            )

        try:
            deadline = self._monotonic_clock() + self._timeout_seconds
            while self._monotonic_clock() <= deadline:
                if receipt_path.exists():
                    break
                self._sleeper(min(0.05, self._timeout_seconds))
            else:
                return self._unobservable(
                    expectation, call_attempt_id, started_ns,
                    "The native-UI controller produced no correlated receipt before deadline.",
                )
            try:
                receipt = NativeUiCallReceipt.model_validate_json(
                    receipt_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError, ValidationError) as exc:
                return self._unobservable(
                    expectation, call_attempt_id, started_ns,
                    f"The native-UI receipt was unreadable or malformed: {exc}",
                )
            return self._observation(request, receipt)
        finally:
            if not _remove_owned_exchange_files(request_path, receipt_path):
                return self._unobservable(
                    expectation,
                    call_attempt_id,
                    started_ns,
                    "The native-UI exchange residue could not be removed.",
                )

    def _observation(
        self,
        request: NativeUiCallRequest,
        receipt: NativeUiCallReceipt,
    ) -> RuntimeCallObservation:
        expectation_identity = (
            request.schema_id,
            request.provider_id,
            request.request_fingerprint,
            request.call_expectation_id,
            request.call_attempt_id,
            request.source_phone_id,
            request.source_device_name,
            request.destination_phone_id,
            request.destination_device_name,
            request.dialed_extension,
        )
        receipt_identity = (
            receipt.schema_id,
            receipt.provider_id,
            receipt.request_fingerprint,
            receipt.call_expectation_id,
            receipt.call_attempt_id,
            receipt.source_phone_id,
            receipt.source_device_name,
            receipt.destination_phone_id,
            receipt.destination_device_name,
            receipt.dialed_extension,
        )
        samples = tuple(receipt.states)
        sample_times = tuple(item.observed_ns for item in samples)
        source = tuple(
            item.state for item in samples
            if (
                item.phone_id == request.source_phone_id
                and item.device_name == request.source_device_name
            )
        )
        destination = tuple(
            item.state for item in samples
            if (
                item.phone_id == request.destination_phone_id
                and item.device_name == request.destination_device_name
                and request.destination_phone_id
            )
        )
        samples_attributed = all(
            (
                item.phone_id == request.source_phone_id
                and item.device_name == request.source_device_name
            )
            or (
                bool(request.destination_phone_id)
                and item.phone_id == request.destination_phone_id
                and item.device_name == request.destination_device_name
            )
            for item in samples
        )
        hashes_valid = bool(
            _is_sha256(receipt.evidence_sha256)
            and all(_is_sha256(item.capture_sha256) for item in samples)
        )
        artifact_valid = False
        artifact_path = Path(receipt.evidence_artifact_path)
        if (
            receipt.evidence_artifact_path
            and artifact_path.is_absolute() is False
            and ".." not in artifact_path.parts
        ):
            try:
                resolved_artifact = resolve_within(
                    self._exchange_dir,
                    *artifact_path.parts,
                )
                artifact_valid = (
                    hashlib.sha256(resolved_artifact.read_bytes()).hexdigest()
                    == receipt.evidence_sha256
                )
            except (OSError, ValueError):
                artifact_valid = False
        time_valid = bool(
            sample_times
            and sample_times == tuple(sorted(sample_times))
            and sample_times[0] >= request.started_ns
            and sample_times[-1] <= request.deadline_ns
        )
        if request.expected_result is CallExpectationResult.ESTABLISHED:
            lifecycle_valid = bool(
                source == _ESTABLISHED_SOURCE
                and destination == _ESTABLISHED_DESTINATION
            )
        else:
            lifecycle_valid = bool(
                source == _NOT_CONNECTED_SOURCE
                and not request.destination_phone_id
                and not destination
            )
        valid = bool(
            expectation_identity == receipt_identity
            and receipt.evidence_method == NATIVE_UI_EVIDENCE_METHOD
            and samples_attributed
            and hashes_valid
            and artifact_valid
            and time_valid
            and lifecycle_valid
        )
        if not valid:
            return self._unobservable_from_request(
                request,
                "The native-UI receipt did not satisfy identity, freshness, "
                "artifact, or typed lifecycle requirements.",
            )
        return RuntimeCallObservation(
            call_expectation_id=request.call_expectation_id,
            call_attempt_id=request.call_attempt_id,
            source_phone_id=request.source_phone_id,
            destination_phone_id=request.destination_phone_id,
            dialed_extension=request.dialed_extension,
            status=ActionExecutionStatus.VERIFIED,
            states=list(source),
            connected=request.expected_result is CallExpectationResult.ESTABLISHED,
            teardown_verified=True,
            observed_after_ns=sample_times[-1],
            fresh_evidence=True,
            evidence_method=receipt.evidence_method,
            evidence_artifact_path=receipt.evidence_artifact_path,
            evidence_sha256=receipt.evidence_sha256,
        )

    @staticmethod
    def _unobservable(expectation, call_attempt_id, started_ns, message):
        return RuntimeCallObservation(
            call_expectation_id=expectation.id,
            call_attempt_id=call_attempt_id,
            source_phone_id=expectation.source_phone_id,
            destination_phone_id=expectation.expected_target_phone_id,
            dialed_extension=expectation.dialed_extension,
            status=ActionExecutionStatus.UNOBSERVABLE,
            observed_after_ns=started_ns,
            fresh_evidence=False,
            evidence_method="packet_tracer_native_ui_receipt_unobservable",
            message=message,
        )

    @classmethod
    def _unobservable_from_request(cls, request, message):
        class _Expectation:
            id = request.call_expectation_id
            source_phone_id = request.source_phone_id
            expected_target_phone_id = request.destination_phone_id
            dialed_extension = request.dialed_extension

        return cls._unobservable(
            _Expectation,
            request.call_attempt_id,
            request.started_ns,
            message,
        )


def _fingerprint(values: dict[str, object]) -> str:
    payload = json.dumps(
        values, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _write_atomic(target: Path, payload: str) -> None:
    handle, name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f"{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.write("\n")
        temporary.replace(target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _remove_owned_exchange_files(*paths: Path) -> bool:
    removed = True
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            removed = False
    return removed
