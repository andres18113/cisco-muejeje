"""Frozen test-only oracle for the pre-extraction CP-LIVE behavior."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys

import pytest

from tests.cp_live_m0_harness import (
    FIXTURE_VERSION,
    HARDENING_BASE_SHA,
    POLICY_TRACE_SOURCE,
    ROOT,
    coordination_source,
    run_product_probe,
    trace_differences,
)


FIXTURE = ROOT / "tests" / "fixtures" / "cp_live_m0" / "baseline-v1.json"
DIGEST = FIXTURE.with_suffix(".sha256")


@pytest.fixture(scope="module")
def baseline() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_reference_artifact_has_pinned_source_and_external_digest(baseline):
    assert baseline["schema"] == "cp-live-m0-equivalence-baseline-v1"
    assert baseline["fixture_version"] == FIXTURE_VERSION
    assert baseline["provenance"]["source_commit"] == HARDENING_BASE_SHA
    source_tree = subprocess.run(
        ["git", "show", "-s", "--format=%T", HARDENING_BASE_SHA],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert source_tree == baseline["provenance"]["source_tree"]
    assert baseline["provenance"]["live_environment_contacted"] is False
    assert baseline["provenance"]["synthetic_test_capabilities"] is True
    assert baseline["comparison"]["provenance_is_not_normalized"] is True
    assert {
        "authority",
        "recipient",
        "destination",
        "journaled_action_ids",
        "first_failed_boundary",
        "closure",
    } <= set(baseline["comparison"]["security_fields_never_normalized"])
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
        DIGEST.read_text(encoding="ascii").strip().split()[0]
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "router0-cleanup",
        "full-cleanup",
        "full-retain",
        "admission-rejected",
        "floor2-failure",
        "operator-abort",
        "precleanup-archive-failure",
        "cleanup-failure",
        "restoration-observation-failure",
    ],
)
def test_run_coordination_matches_the_frozen_ordered_trace(
    baseline,
    scenario,
    tmp_path,
):
    actual = run_product_probe(
        coordination_source(scenario),
        tmp_path / scenario,
    )
    expected = baseline["coordination"][scenario]

    assert trace_differences(expected, actual) == []


def test_policy_and_authority_trace_matches_the_frozen_reference(
    baseline,
    tmp_path,
):
    actual = run_product_probe(POLICY_TRACE_SOURCE, tmp_path / "policy")

    assert trace_differences(baseline["policy_trace"], actual) == []


@pytest.mark.parametrize(
    ("mutation", "needle"),
    [
        ("extra-operation", "operations"),
        ("changed-recipient", "recipient"),
        ("wrong-authority", "authority"),
        ("verified-promotion", "aggregate_status"),
    ],
)
def test_comparator_detects_deliberate_semantic_drift(
    baseline,
    mutation,
    needle,
):
    expected = baseline["policy_trace"]
    changed = copy.deepcopy(expected)
    if mutation == "extra-operation":
        changed["operations"].append(copy.deepcopy(changed["operations"][-1]))
    elif mutation == "changed-recipient":
        changed["operations"][0]["recipient"] = "WrongRouter"
    elif mutation == "wrong-authority":
        changed["operations"][0]["authority"] = (
            "reverse-path-of-declared-flow"
        )
    elif mutation == "verified-promotion":
        changed["configuration_acceptance"]["aggregate_status"] = "verified"
        changed["configuration_acceptance"]["fully_verified"] = True

    differences = trace_differences(expected, changed)

    assert differences
    assert any(needle in item for item in differences)


def test_parent_pytest_process_never_loads_the_production_namespace():
    assert "packet_tracer_mcp" not in sys.modules
