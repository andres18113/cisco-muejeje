"""Frozen test-only oracle for the pre-extraction CP-LIVE behavior.

Two things are checked and they are kept apart on purpose:

* the **comparable trace** of each probe, compared field by field against the
  recorded reference, keeping destinations, authority, multiplicity, order and
  security decisions exactly as observed; and
* the **candidate's own provenance**, measured by the child process itself and
  asserted here -- never compared against the reference and never used to
  normalize the trace.

Nothing in this module recalculates an expectation.  The reference is recorded
by ``tests/cp_live_m0_record_baseline.py``, which is not a test module and
refuses to run inside pytest.
"""

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
    HISTORICAL_FIXTURE_VERSION,
    POLICY_TRACE_SOURCE,
    ROOT,
    SCENARIOS,
    coordination_source,
    run_product_probe,
    trace_differences,
)


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "cp_live_m0"
FIXTURE = FIXTURE_DIR / "baseline-v2.json"
DIGEST = FIXTURE.with_suffix(".sha256")
HISTORICAL_FIXTURE = FIXTURE_DIR / "baseline-v1.json"
HISTORICAL_DIGEST = HISTORICAL_FIXTURE.with_suffix(".sha256")

# The commit whose corrected runner this reference characterizes. Re-pointing
# the reference at another commit is a decision that has to be taken here, in
# test code, and not by editing the artifact.
BASELINE_SOURCE_SHA = "7a6c552dd570f683fe3f249c1037815192543ae7"

# What the Level A doubles must replace for a probe to be offline, and what has
# to stay real for the probe to be characterizing anything at all.
SUBSTITUTED_SYMBOLS = frozenset({
    "ImportIsolationPreflight",
    "read_git_repository_state",
    "_packet_tracer_processes",
    "PacketTracerHttpTransport",
    "PacketTracerPhysicalTopologyRuntime",
    "CapabilitySnapshotStore",
    "compose_cp_scale_canonical",
    "_execute_stage",
    "_checkpoint",
    "_cleanup_owned",
    "_write_evidence",
    "_write_checkpoint_summary",
    "archive_cp_scale_canonical_evidence",
})
REAL_SYMBOLS = frozenset({
    "run",
    "_complete_router0_target",
    "canonical_cp_scale_target_contract",
    "canonical_final_disposition",
    "canonical_checkpoint_repository_error",
    "canonical_stage_mutation_replay_audit",
    "_wait_for_site_forwarding",
})


@pytest.fixture(scope="module")
def baseline() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _assert_candidate_provenance(verdict: dict, *, substituted: frozenset):
    """The child's measured provenance, asserted apart from its trace."""

    provenance = verdict["provenance"]
    # One namespace per process is what makes enum and isinstance identity
    # meaningful; the production one is the only one a probe may load.
    assert provenance["loaded_namespaces"] == ["packet_tracer_mcp"], provenance
    assert provenance["package_file_inside_tree"] is True, provenance
    assert provenance["runner_file_inside_tree"] is True, provenance
    assert provenance["governed_root_inside_tree"] is True, provenance
    assert provenance["interpreter"] == sys.executable, provenance
    # Measured, not declared: no dispatch was even attempted, so no live
    # environment was contacted.
    assert provenance["transport_dispatch_attempts"] == [], provenance
    replaced = set(provenance["substituted_runner_symbols"])
    assert substituted <= replaced, sorted(substituted - replaced)
    assert not (REAL_SYMBOLS & replaced), sorted(REAL_SYMBOLS & replaced)


def test_reference_artifact_has_pinned_source_and_external_digest(baseline):
    assert baseline["schema"] == "cp-live-m0-equivalence-baseline-v2"
    assert baseline["fixture_version"] == FIXTURE_VERSION
    assert baseline["provenance"]["source_commit"] == BASELINE_SOURCE_SHA
    # A local object read, never a network call. CI checks out with
    # fetch-depth: 0 for exactly this dependency; on a shallow clone the
    # provenance cannot be verified, so this fails rather than skips.
    completed = subprocess.run(
        ["git", "show", "-s", "--format=%T", BASELINE_SOURCE_SHA],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, (
        f"The pinned source commit {BASELINE_SOURCE_SHA} is missing from this "
        "checkout, so the reference's provenance cannot be verified. A full "
        "history is required (CI: actions/checkout with fetch-depth: 0).\n"
        + completed.stderr
    )
    assert completed.stdout.strip() == baseline["provenance"]["source_tree"]
    assert baseline["provenance"]["live_environment_contacted"] is False
    assert baseline["provenance"]["synthetic_test_capabilities"] is True
    assert baseline["comparison"]["provenance_is_not_normalized"] is True
    assert baseline["comparison"][
        "candidate_provenance_is_asserted_not_compared"
    ] is True
    assert {
        "authority",
        "recipient",
        "destination",
        "journaled_action_ids",
        "canonically_accepted",
        "canonical_acceptance_error",
        "first_failed_boundary",
        "closure",
    } <= set(baseline["comparison"]["security_fields_never_normalized"])
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
        DIGEST.read_text(encoding="ascii").strip().split()[0]
    )


def test_the_superseded_reference_is_retained_and_still_verifiable(baseline):
    superseded = baseline["supersedes"]

    assert superseded["fixture_version"] == HISTORICAL_FIXTURE_VERSION
    assert superseded["source_commit"] == HARDENING_BASE_SHA
    assert superseded["retained_as"] == "tests/fixtures/cp_live_m0/baseline-v1.json"
    # Retained as history, not as an oracle: it still matches its own digest.
    assert hashlib.sha256(HISTORICAL_FIXTURE.read_bytes()).hexdigest() == (
        superseded["sha256"]
    )
    assert hashlib.sha256(HISTORICAL_FIXTURE.read_bytes()).hexdigest() == (
        HISTORICAL_DIGEST.read_text(encoding="ascii").strip().split()[0]
    )
    # Every difference against it is named, not implied.
    assert superseded["justified_differences"]
    for difference in superseded["justified_differences"]:
        assert difference["change"] and difference["why"]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_run_coordination_matches_the_frozen_ordered_trace(
    baseline,
    scenario,
    tmp_path,
):
    verdict = run_product_probe(
        coordination_source(scenario),
        tmp_path / scenario,
    )
    expected = baseline["coordination"][scenario]

    assert trace_differences(expected, verdict["trace"]) == []
    _assert_candidate_provenance(verdict, substituted=SUBSTITUTED_SYMBOLS)


def test_policy_and_authority_trace_matches_the_frozen_reference(
    baseline,
    tmp_path,
):
    verdict = run_product_probe(POLICY_TRACE_SOURCE, tmp_path / "policy")

    assert trace_differences(baseline["policy_trace"], verdict["trace"]) == []
    # Level C substitutes nothing at all: it feeds synthetic typed inputs to
    # the real rules, so every runner symbol is still the product one.
    _assert_candidate_provenance(verdict, substituted=frozenset())
    assert verdict["provenance"]["substituted_runner_symbols"] == []


def test_governed_acceptance_is_not_derived_from_an_absent_contradiction(
    baseline,
):
    configuration = baseline["policy_trace"]["configuration"]
    accepted = configuration["accepted_with_governed_ceiling"]
    rejected = configuration["rejected_promoted_ceiling"]

    # Accepted by the canonical rule, and still not a VERIFIED claim.
    assert accepted["canonical_acceptance_error"] == ""
    assert accepted["canonically_accepted"] is True
    assert accepted["aggregate_status"] == "partial"
    assert accepted["fully_verified"] is False
    # The rejection contradicts nothing and is refused anyway: an absent
    # contradiction is not canonical acceptance.
    assert rejected["contradiction"] == ""
    assert rejected["contradiction_free"] is True
    assert rejected["canonically_accepted"] is False
    assert rejected["canonical_acceptance_error"]
    assert rejected["fully_verified"] is False


@pytest.mark.parametrize(
    ("mutation", "needle"),
    [
        ("extra-operation", "operations"),
        ("changed-recipient", "recipient"),
        ("wrong-authority", "authority"),
        ("verified-promotion", "aggregate_status"),
        ("accepted-rejection", "canonically_accepted"),
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
        promoted = changed["configuration"]["accepted_with_governed_ceiling"]
        promoted["aggregate_status"] = "verified"
        promoted["fully_verified"] = True
    elif mutation == "accepted-rejection":
        refused = changed["configuration"]["rejected_promoted_ceiling"]
        refused["canonically_accepted"] = True
        refused["canonical_acceptance_error"] = ""

    differences = trace_differences(expected, changed)

    assert differences
    assert any(needle in item for item in differences)


def test_parent_pytest_process_never_loads_the_production_namespace():
    assert "packet_tracer_mcp" not in sys.modules
