"""POE-2 acceptance, deliberately independent from product claim authority.

The backend supplies its calibrated capture verifier and exact contract.
The domain decides freshness, causal classification and restoration acceptance.
"""
from __future__ import annotations

import re
from datetime import datetime
from collections.abc import Callable
from ...models.errors import ErrorCode, PlanError, ValidationResult
from ..models.poe2 import PoE2Capture, PoE2Evidence

def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Evidence time lacks timezone")
    return result


def validate_poe2_evidence(
    bundle: PoE2Evidence, raw_files: dict[str, bytes], *,
    expected_start_head: str, expected_build: str, expected_binding: dict[str, str],
    capture_verifier: Callable[[PoE2Capture, bytes, str], str],
) -> ValidationResult:
    errors = []
    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(PlanError(code=ErrorCode.CAPABILITY_PROBE_FAILED, message=message))
    require(bundle.START_HEAD == expected_start_head, "Wrong POE-2 START_HEAD")
    require(bundle.exact_binding == expected_binding, "POE-2 cannot extrapolate binding")
    require(bundle.packet_tracer_build == expected_build, "Wrong calibrated PT build")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", bundle.frozen_live_sha)), "Missing frozen source SHA")
    require(bundle.experiment_id.startswith("poe2-"), "Calibration is not POE-2 evidence")
    require(bundle.calibration_reference.get("productive") is False, "Calibration cannot be productive")
    require(bundle.integration_result == "NOT_ATTEMPTED", "Experimental evidence cannot self-authorize integration")
    labels = [item.label for item in bundle.captures]
    require(labels == ["AUTO_1", "NEVER", "AUTO_2"], "A full causal sequence is required")
    states = []
    try:
        start, end = _time(bundle.started_at_utc), _time(bundle.completed_at_utc)
        require(_time(bundle.start_head_committed_at_utc) <= start < end, "Pre-START_HEAD evidence is non-productive")
        previous = start
        switch_name = bundle.fixture["switch"]["name"]
        require(bundle.fixture["switch"]["model"] == expected_binding["switch_model"], "Wrong fixture switch")
        require(bundle.fixture["endpoint"]["model"] == expected_binding["endpoint_model"], "Wrong fixture endpoint")
        link = bundle.fixture["link"]
        require(link["first"] == {"device_name": switch_name, "device_model": expected_binding["switch_model"], "port": expected_binding["switch_port"]}, "Wrong switch link endpoint")
        require(link["second"] == {"device_name": bundle.fixture["endpoint"]["name"], "device_model": expected_binding["endpoint_model"], "port": expected_binding["endpoint_port"]}, "Wrong AP link endpoint")
        for capture in bundle.captures:
            a, b = _time(capture.started_at_utc), _time(capture.completed_at_utc)
            require(previous <= a < b <= end, "Capture is stale or out of sequence")
            previous = b
            require(capture.raw_file == capture.label.lower() + ".txt", "Unexpected raw file")
            states.append(capture_verifier(capture, raw_files[capture.raw_file], switch_name))
        if states == ["delivering", "not_delivering", "delivering"]:
            require(bundle.captures[1].observation["ports"][0]["row"] is None, "NEVER must match calibrated absence semantics")
            classification = "POSITIVE"
        elif states == ["not_delivering"] * 3 and all(c.observation["ports"][0]["row"] is None for c in bundle.captures):
            classification = "NEGATIVE"
        else:
            classification = "UNKNOWN"
        require(bundle.experimental_classification == classification, "Experimental classification disagrees with evidence")
        require(classification != "UNKNOWN", "No calibrated causal result")
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        require(False, str(exc))
    try:
        restored = PoE2Capture.model_validate(bundle.restoration["fresh_readback"])
        require(restored.label == "RESTORE" and restored.raw_file == "restore.txt", "Restoration identity missing")
        require(_time(bundle.captures[-1].completed_at_utc) <= _time(restored.started_at_utc) <
                _time(restored.completed_at_utc) <= _time(bundle.completed_at_utc), "Restoration readback is stale")
        capture_verifier(restored, raw_files[restored.raw_file], bundle.fixture["switch"]["name"])
        row = restored.observation["ports"][0]["row"]
        require(row is not None and row["admin"] == "auto", "Auto restoration raw readback missing")
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        require(False, "Restoration: " + str(exc))
    require(bundle.restoration.get("power_inline_auto_proven") is True, "Auto restoration not proven")
    require(bundle.restoration.get("fixture_removed") is True, "Fixture not removed")
    require(bundle.restoration.get("inventory_restored") is True, "Inventory not restored")
    require(bundle.restoration.get("realtime_restored") is True, "Realtime not restored")
    require(bundle.safety.get("clean") is True and not bundle.problems, "Safety is not clean")
    return ValidationResult(errors=errors)
