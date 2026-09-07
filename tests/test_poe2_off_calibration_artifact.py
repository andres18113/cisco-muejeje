"""Pins the committed, NON-PRODUCTIVE PSE off/zero calibration bundle.

These bytes calibrate one semantic question only: what `show power inline`
prints for FastEthernet0/13 when the powered device is physically absent. They
are not AP evidence and can never become AP evidence — the fixture endpoint is
a 7960 phone. The AP binding is decided by a separate, fresh LIVE run.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.poe2 import PoE2Capture
from src.packet_tracer_mcp.infrastructure.execution.poe2_evidence import (
    BINDING, BUILD, START_HEAD, capture_delivery, off_calibration_valid,
)
from src.packet_tracer_mcp.shared.utils import resolve_within, safe_name_component

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = "poe2-off-calibration-7bb812cdf106"
EVIDENCE_SHA256 = "34673ae29106fee49570233b05b72f778314d01b4e9d7af35dc5ad94cf3ea68b"
# One instant after the bundle closed; freshness is asserted, never assumed.
AFTER = "2026-09-07T17:02:00Z"


def _root() -> Path:
    return resolve_within(ROOT, "docs/reference/cp-scale/canonical-live-evidence",
                          safe_name_component(DIRECTORY))


def _reference() -> dict:
    body = resolve_within(_root(), "evidence.json").read_bytes()
    cal = json.loads(body)
    names = [c["raw_file"] for c in cal["captures"]] + [cal["restoration"]["capture"]["raw_file"]]
    texts = {name: resolve_within(_root(), safe_name_component(name)).read_bytes().decode()
             for name in names}
    return dict(evidence_raw=body.decode(), sha256=hashlib.sha256(body).hexdigest(), raw_files=texts)


def test_persisted_calibration_bytes_are_the_hashed_ones():
    assert _reference()["sha256"] == EVIDENCE_SHA256


def test_persisted_calibration_validates_as_prior_causal_evidence():
    assert off_calibration_valid(_reference(), before_utc=AFTER) is True


def test_persisted_calibration_is_not_prior_evidence_for_an_earlier_experiment():
    # A calibration that had not finished yet cannot calibrate anything.
    reference = _reference()
    completed = json.loads(reference["evidence_raw"])["completed_at_utc"]
    early = datetime.fromisoformat(completed.replace("Z", "+00:00")) - timedelta(seconds=1)
    assert off_calibration_valid(reference, before_utc=early.isoformat().replace("+00:00", "Z")) is False


def test_persisted_raw_captures_hash_to_their_declared_digests():
    reference = _reference()
    cal = json.loads(reference["evidence_raw"])
    for entry in cal["captures"] + [cal["restoration"]["capture"]]:
        raw = reference["raw_files"][entry["raw_file"]].encode()
        assert hashlib.sha256(raw).hexdigest() == entry["raw_sha256"], entry["raw_file"]


def test_persisted_raw_captures_agree_with_their_typed_readings():
    reference = _reference()
    cal = json.loads(reference["evidence_raw"])
    switch = cal["facts"]["fixture"]["switch"]["name"]
    states = [capture_delivery(PoE2Capture.model_validate(entry),
                               reference["raw_files"][entry["raw_file"]].encode(), switch)
              for entry in cal["captures"]]
    assert states == ["delivering", "not_delivering", "delivering"]


def test_persisted_calibration_declares_its_own_provenance():
    cal = json.loads(_reference()["evidence_raw"])
    assert cal["kind"] == "poe2-pse-off-calibration"
    assert cal["productive"] is False
    assert cal["START_HEAD"] == START_HEAD
    assert cal["packet_tracer_build"] == BUILD
    assert cal["problems"] == []


def test_persisted_calibration_never_speaks_for_the_access_point():
    # The powered device is a phone on the AP's port. No capture here observes
    # an AccessPoint-PT, so this bundle cannot be relabelled as an AP result.
    # The AP model appears once, in the baseline, as the binding still to be
    # measured — declaring a target is not observing it.
    reference = _reference()
    cal = json.loads(reference["evidence_raw"])
    fixture = cal["facts"]["fixture"]
    assert fixture["endpoint"]["model"] == "7960"
    assert fixture["endpoint"]["model"] != BINDING["endpoint_model"]
    assert fixture["link"]["first"]["port"] == BINDING["switch_port"]
    assert cal["baseline"]["derived_binding"]["endpoint_model"] == BINDING["endpoint_model"]
    observed = json.dumps([cal["captures"], cal["restoration"], cal["facts"]])
    assert BINDING["endpoint_model"] not in observed
    for raw in reference["raw_files"].values():
        assert BINDING["endpoint_model"] not in raw


@pytest.mark.parametrize("target", ["connected_1.txt", "pd_absent.txt", "connected_2.txt", "restore.txt"])
def test_tampering_persisted_raw_bytes_fails_closed(target):
    reference = _reference()
    reference["raw_files"][target] += "Fa0/13     auto   on     10.0    tampered           3     15.4\n"
    assert off_calibration_valid(reference, before_utc=AFTER) is False


def test_tampering_persisted_evidence_json_fails_closed():
    reference = _reference()
    cal = json.loads(reference["evidence_raw"])
    cal["facts"]["pd_absent"]["endpoint_absent"] = False
    reference["evidence_raw"] = json.dumps(cal)
    # The stale digest alone already refuses it; restate it to prove the causal gate.
    reference["sha256"] = hashlib.sha256(reference["evidence_raw"].encode()).hexdigest()
    assert off_calibration_valid(reference, before_utc=AFTER) is False
