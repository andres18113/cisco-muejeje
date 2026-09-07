"""Synthetic contract tests; these bytes never constitute productive LIVE evidence."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.poe2 import PoE2Capture, PoE2Evidence
from src.packet_tracer_mcp.infrastructure.execution.poe2_evidence import (
    BINDING, BUILD, START_HEAD, completeness, validate_poe2_evidence,
)
from src.packet_tracer_mcp.infrastructure.execution.poe_inline_observer import GovernedPoEInlineObserver
from tests.test_poe_inline_observer import _result, _StubExecutor, _SWITCH
from tests.test_poe_inline_parser import _MEASURED_AUTO


def bundle_fixture():
    # Move the measured phone row to a synthetic AP-port position, explicitly
    # for offline testing only. CLI Device text is not endpoint identity.
    rows = _MEASURED_AUTO.splitlines()
    one = next(i for i, line in enumerate(rows) if line.startswith("Fa0/1 "))
    thirteen = next(i for i, line in enumerate(rows) if line.startswith("Fa0/13 "))
    rows[one], rows[thirteen] = "Fa0/1".ljust(10) + rows[thirteen][10:], "Fa0/13".ljust(10) + rows[one][10:]
    auto = "\n".join(rows) + "\n"
    never = "\n".join(line for line in auto.splitlines() if not line.startswith("Fa0/13 ")) + "\n"
    captures, raw_files = [], {}
    for index, (label, output) in enumerate((("AUTO_1", auto), ("NEVER", never), ("AUTO_2", auto))):
        result = replace(_result(output), echo_observed="show power inline")
        observed = GovernedPoEInlineObserver(_StubExecutor(result)).observe_poe_inline_status(_SWITCH, (BINDING["switch_port"],))
        value = json.loads(json.dumps(asdict(observed)))
        raw = output.encode()
        capture = PoE2Capture(label=label, started_at_utc=f"2026-09-08T00:00:{index * 10 + 1:02d}Z",
            completed_at_utc=f"2026-09-08T00:00:{index * 10 + 5:02d}Z", expected_prompt="Switch#",
            observation=value, repeat_observation=deepcopy(value),
            table_completeness=completeness(value, "Switch#", True, _SWITCH), stable=True,
            raw_file=label.lower() + ".txt", raw_sha256=hashlib.sha256(raw).hexdigest())
        captures.append(capture)
        raw_files[capture.raw_file] = raw
    fixture = dict(switch=dict(name=_SWITCH, model=BINDING["switch_model"]),
                   endpoint=dict(name="synthetic-AP", model=BINDING["endpoint_model"]),
                   link=dict(first=dict(device_name=_SWITCH, device_model=BINDING["switch_model"], port=BINDING["switch_port"]),
                             second=dict(device_name="synthetic-AP", device_model=BINDING["endpoint_model"], port=BINDING["endpoint_port"])))
    bundle = PoE2Evidence(schema_version=1, experiment_id="poe2-synthetic-offline-only",
        started_at_utc="2026-09-08T00:00:00Z", completed_at_utc="2026-09-08T00:01:00Z",
        START_HEAD=START_HEAD, start_head_committed_at_utc="2026-09-07T13:30:53Z", frozen_live_sha="b" * 40,
        packet_tracer_build=BUILD, exact_binding=dict(BINDING), fixture=fixture,
        baseline={}, calibration_reference={"productive": False}, captures=captures,
        experimental_classification="POSITIVE", integration_result="NOT_ATTEMPTED", authority_delta="none",
        restoration=dict(power_inline_auto_proven=True, fixture_removed=True, inventory_restored=True, realtime_restored=True),
        safety={"clean": True}, problems=[])
    restore = captures[-1].model_copy(deep=True, update={"label": "RESTORE", "raw_file": "restore.txt",
        "started_at_utc": "2026-09-08T00:00:30Z", "completed_at_utc": "2026-09-08T00:00:35Z"})
    raw_files["restore.txt"] = raw_files["auto_2.txt"]
    bundle.restoration["fresh_readback"] = restore.model_dump(mode="json")
    return bundle, raw_files


def test_complete_causal_signature_is_an_experimental_positive_only():
    bundle, raw = bundle_fixture()
    assert validate_poe2_evidence(bundle, raw).is_valid
    assert bundle.integration_result == "NOT_ATTEMPTED"
    assert bundle.authority_delta == "none"


@pytest.mark.parametrize(("key", "value"), [
    ("switch_model", "other-switch"), ("switch_port", "FastEthernet0/14"),
    ("endpoint_model", "7960"), ("endpoint_port", "Port 1"),
])
def test_no_binding_port_or_endpoint_extrapolation(key, value):
    bundle, raw = bundle_fixture()
    bundle.exact_binding[key] = value
    assert not validate_poe2_evidence(bundle, raw).is_valid


@pytest.mark.parametrize("index", [0, 1, 2])
def test_any_incomplete_state_prevents_a_partial_positive(index):
    bundle, raw = bundle_fixture()
    bundle.captures[index].observation["command_result"]["pager_continuation"] = "failed"
    assert not validate_poe2_evidence(bundle, raw).is_valid


def test_incomplete_never_cannot_become_a_negative():
    bundle, raw = bundle_fixture()
    bundle.experimental_classification = "NEGATIVE"
    bundle.captures[1].observation["capture_complete"] = False
    assert not validate_poe2_evidence(bundle, raw).is_valid


@pytest.mark.parametrize("change", ["row", "delivery", "dispatch_output", "hash", "repeat"])
def test_raw_and_typed_disagreement_is_never_silent(change):
    bundle, raw = bundle_fixture()
    capture = bundle.captures[0]
    if change == "row":
        capture.observation["ports"][0]["row"]["power_watts"] = 99.0
    elif change == "delivery":
        capture.observation["ports"][0]["delivery"] = "not_delivering"
    elif change == "dispatch_output":
        capture.observation["command_result"]["output"] = "unrelated transcript"
    elif change == "hash":
        raw[capture.raw_file] += b"tamper"
    else:
        capture.repeat_observation["ports"][0]["delivery"] = "not_delivering"
    assert not validate_poe2_evidence(bundle, raw).is_valid


@pytest.mark.parametrize("change", ["calibration", "pre_start_head", "pre_experiment", "legacy"])
def test_nonproductive_or_stale_evidence_cannot_promote(change):
    bundle, raw = bundle_fixture()
    if change == "calibration":
        bundle.experiment_id = "poe1-c5626851"
    elif change == "pre_start_head":
        bundle.started_at_utc = "2026-09-07T12:00:00Z"
    elif change == "pre_experiment":
        bundle.captures[0].started_at_utc = "2026-09-07T14:00:00Z"
    else:
        bundle.captures[1].observation.pop("command_result")
    assert not validate_poe2_evidence(bundle, raw).is_valid


def test_summary_used_power_cannot_authorize_a_positive():
    bundle, raw = bundle_fixture()
    bundle.captures[0].observation["summary_used_watts"] = 999.0
    bundle.captures[0].observation["ports"][0]["delivery"] = "not_delivering"
    assert not validate_poe2_evidence(bundle, raw).is_valid


def test_restoration_and_safety_are_required_before_result_escapes():
    bundle, raw = bundle_fixture()
    bundle.restoration["inventory_restored"] = False
    assert not validate_poe2_evidence(bundle, raw).is_valid


def test_cli_device_text_does_not_supply_binding_identity():
    bundle, raw = bundle_fixture()
    assert bundle.captures[0].observation["ports"][0]["row"]["device"] == "IP Phone 7960"
    assert validate_poe2_evidence(bundle, raw).is_valid
    bundle.fixture["endpoint"]["model"] = "7960"
    assert not validate_poe2_evidence(bundle, raw).is_valid


def test_experimental_artifact_cannot_declare_integration_success():
    bundle, raw = bundle_fixture()
    bundle.integration_result = "PASS"
    assert not validate_poe2_evidence(bundle, raw).is_valid


def test_restore_summary_without_fresh_raw_readback_cannot_authorize():
    bundle, raw = bundle_fixture()
    bundle.restoration.pop("fresh_readback")
    assert not validate_poe2_evidence(bundle, raw).is_valid


def test_restoration_raw_hash_is_verified_too():
    bundle, raw = bundle_fixture()
    raw["restore.txt"] += b"tampered"
    assert not validate_poe2_evidence(bundle, raw).is_valid
