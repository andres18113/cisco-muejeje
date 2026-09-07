"""Pins the productive POE-2 AP result: 3560-24PS Fa0/13 -> AccessPoint-PT Port 0.

The experiment answered NEGATIVE. With the AP connected, `show power inline`
prints a table byte-identical to the one printed with no powered device at all
(the supplemental calibration's `pd_absent.txt`), while the same port, same
switch model and same runner delivered 10.0W to a 7960 phone. So the PSE sees
nothing on this binding, and that absence is causally calibrated rather than
inferred from an uncharacterised zero.

A negative is a result, not an absence of one — it has to survive the same
gates a positive would. These tests pin it against the bytes on disk: the
schema, every raw digest, raw against typed, all eight completeness gates,
freshness ordering, restoration, and the fact that the calibration alone can
never produce this classification.

Authority is untouched. The bundle records INTEGRATION_RESULT=NOT_ATTEMPTED,
and `_AUTHORIZED_OBSERVATION_METHODS` remains the manual contract's allowlist.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.poe2 import PoE2Capture, PoE2Evidence
from src.packet_tracer_mcp.domain.enterprise.services.poe_claims import (
    _AUTHORIZED_OBSERVATION_METHODS,
)
from src.packet_tracer_mcp.infrastructure.execution.poe2_evidence import (
    BINDING, BUILD, COMPLETENESS_KEYS, START_HEAD, capture_delivery, validate_poe2_evidence,
)
from src.packet_tracer_mcp.shared.utils import resolve_within, safe_name_component

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = "poe2-20260907T173336Z-b4d3459e"
EVIDENCE_SHA256 = "9355a78a25ba406785ecac083de9185df8f15a6819c5f6a7bc2b648c326eb834"
FROZEN_LIVE_SHA = "888178008b31734d61c7fc5d8c544e8049a983de"
# AUTO_1, AUTO_2 and the restore read-back are the same bytes as the
# calibration's powered-device-absent capture. That identity IS the finding.
PD_ABSENT_SHA256 = "d338b3213b4ca316a8132bd56540d13edf6e2dcfc5c61abbae425e46f6855e11"
RAW_FILES = ("auto_1.txt", "never.txt", "auto_2.txt", "restore.txt")


def _root() -> Path:
    return resolve_within(ROOT, "docs/reference/cp-scale/canonical-live-evidence",
                          safe_name_component(DIRECTORY))


def _raw() -> dict[str, bytes]:
    return {name: resolve_within(_root(), safe_name_component(name)).read_bytes()
            for name in RAW_FILES}


def _bundle() -> PoE2Evidence:
    return PoE2Evidence.model_validate_json(resolve_within(_root(), "evidence.json").read_bytes())


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_persisted_bundle_bytes_are_the_hashed_ones():
    body = resolve_within(_root(), "evidence.json").read_bytes()
    assert hashlib.sha256(body).hexdigest() == EVIDENCE_SHA256


def test_persisted_bundle_matches_the_typed_schema():
    bundle = _bundle()
    assert bundle.schema_version == 1
    assert bundle.experiment_id == DIRECTORY
    assert bundle.START_HEAD == START_HEAD
    assert bundle.frozen_live_sha == FROZEN_LIVE_SHA
    assert bundle.packet_tracer_build == BUILD
    assert [c.label for c in bundle.captures] == ["AUTO_1", "NEVER", "AUTO_2"]
    assert bundle.problems == []


def test_the_persisted_bundle_validates_over_the_bytes_on_disk():
    result = validate_poe2_evidence(_bundle(), _raw())
    assert result.is_valid, list(result.errors)
    assert not list(result.warnings)


def test_every_raw_capture_hashes_to_its_declared_digest():
    bundle, raw = _bundle(), _raw()
    entries = list(bundle.captures) + [PoE2Capture.model_validate(bundle.restoration["fresh_readback"])]
    for entry in entries:
        assert hashlib.sha256(raw[entry.raw_file]).hexdigest() == entry.raw_sha256, entry.raw_file


def test_raw_and_typed_readings_agree_on_every_capture():
    bundle, raw = _bundle(), _raw()
    switch = bundle.fixture["switch"]["name"]
    states = [capture_delivery(c, raw[c.raw_file], switch) for c in bundle.captures]
    assert states == ["not_delivering", "not_delivering", "not_delivering"]


def test_every_completeness_gate_holds_on_every_capture():
    """A negative built on an incomplete table would be an absence of evidence."""
    bundle = _bundle()
    entries = list(bundle.captures) + [PoE2Capture.model_validate(bundle.restoration["fresh_readback"])]
    for entry in entries:
        assert set(entry.table_completeness) == COMPLETENESS_KEYS, entry.label
        assert all(entry.table_completeness.values()), (entry.label, entry.table_completeness)
        assert entry.stable is True
        assert entry.expected_prompt == "Switch#"


def test_capture_times_are_ordered_inside_the_live_window():
    bundle = _bundle()
    previous = _moment(bundle.started_at_utc)
    for capture in bundle.captures:
        assert previous <= _moment(capture.started_at_utc) < _moment(capture.completed_at_utc)
        previous = _moment(capture.completed_at_utc)
    restore = PoE2Capture.model_validate(bundle.restoration["fresh_readback"])
    assert previous <= _moment(restore.started_at_utc) < _moment(restore.completed_at_utc)
    assert _moment(restore.completed_at_utc) <= _moment(bundle.completed_at_utc)


def test_the_result_is_an_exact_binding_with_no_extrapolation():
    bundle = _bundle()
    assert bundle.exact_binding == BINDING
    fixture = bundle.fixture
    assert fixture["switch"]["model"] == BINDING["switch_model"]
    assert fixture["endpoint"]["model"] == BINDING["endpoint_model"]
    assert fixture["link"]["first"]["port"] == BINDING["switch_port"]
    assert fixture["link"]["second"]["port"] == BINDING["endpoint_port"]
    # Exactly one port was observed. Twenty-three other rows were printed and
    # none of them is claimed.
    for capture in bundle.captures:
        ports = capture.observation["ports"]
        assert [p["port"] for p in ports] == [BINDING["switch_port"]]


def test_the_negative_is_the_calibrated_absence_not_an_uncharacterised_zero():
    """Strip the calibration and this classification stops being admissible."""
    bundle, raw = _bundle(), _raw()
    assert "off_semantics" in bundle.calibration_reference
    bundle.calibration_reference = dict(bundle.calibration_reference)
    bundle.calibration_reference.pop("off_semantics")
    result = validate_poe2_evidence(bundle, raw)
    assert not result.is_valid
    assert any("calibrated causal result" in error.message for error in result.errors)


def test_the_ap_table_is_indistinguishable_from_no_powered_device():
    """The finding itself: connecting the AP changes nothing the PSE can see."""
    raw = _raw()
    for name in ("auto_1.txt", "auto_2.txt", "restore.txt"):
        assert hashlib.sha256(raw[name]).hexdigest() == PD_ABSENT_SHA256, name
    # Under `never` the row disappears entirely, so the port really was driven.
    assert hashlib.sha256(raw["never.txt"]).hexdigest() != PD_ABSENT_SHA256
    assert b"Fa0/13" not in raw["never.txt"]
    assert b"Fa0/13" in raw["auto_1.txt"]


def test_the_experiment_restored_everything_it_touched():
    bundle = _bundle()
    restoration = bundle.restoration
    for key in ("power_inline_auto_proven", "endpoint_deleted", "switch_deleted",
                "inventory_restored", "fixture_removed", "realtime_restored"):
        assert restoration[key] is True, key
    assert (restoration["inventory_fingerprint_after"]
            == bundle.baseline["inventory_fingerprint"])
    safety = bundle.safety
    for key in ("clean", "mailbox_clean", "runtime_heartbeat_fresh",
                "same_pt_processes", "frozen_source_unchanged"):
        assert safety[key] is True, key
    assert safety["transport_problems"] == []
    assert safety["before_pt_pids"] == safety["after_pt_pids"]
    assert safety["external_power_condition"] == "as_created_unchanged"


def test_the_experiment_ran_from_an_exactly_green_frozen_source():
    baseline = _bundle().baseline
    assert baseline["local_head"] == baseline["remote_head"] == FROZEN_LIVE_SHA
    assert baseline["strict_e5"] is True
    jobs = baseline["jobs"]
    assert len(jobs) == 4
    assert all(job["conclusion"] == "success" and job["head_sha"] == FROZEN_LIVE_SHA
               for job in jobs)


def test_a_negative_claims_no_authority():
    bundle = _bundle()
    assert bundle.experimental_classification == "NEGATIVE"
    assert bundle.integration_result == "NOT_ATTEMPTED"
    assert bundle.authority_delta == "none; qualification only"
    assert _AUTHORIZED_OBSERVATION_METHODS == frozenset({"manual_visible_power_state"})


@pytest.mark.parametrize("target", RAW_FILES)
def test_tampering_a_persisted_raw_capture_fails_closed(target):
    bundle, raw = _bundle(), _raw()
    raw[target] += b"Fa0/13     auto   on     10.0    tampered           3     15.4\n"
    assert not validate_poe2_evidence(bundle, raw).is_valid


def test_a_result_dated_before_its_calibration_is_refused():
    """Freshness is ordered, not asserted: evidence cannot precede its basis."""
    bundle, raw = _bundle(), _raw()
    calibration = json.loads(bundle.calibration_reference["off_semantics"]["evidence_raw"])
    earlier = _moment(calibration["started_at_utc"]) - timedelta(minutes=1)
    bundle.started_at_utc = earlier.isoformat().replace("+00:00", "Z")
    assert not validate_poe2_evidence(bundle, raw).is_valid
