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
    HISTORICAL_FIXTURE_VERSIONS,
    LEVEL_A_SUBSTITUTED_SYMBOLS,
    POLICY_TRACE_DUPLICATE_DISPATCH_SOURCE,
    POLICY_TRACE_EXTRA_DISPATCH_SOURCE,
    POLICY_TRACE_SOURCE,
    POLICY_TRACE_WRONG_DESTINATION_SOURCE,
    PRODUCT_RULE_SYMBOLS,
    ROOT,
    SCENARIOS,
    candidate_provenance_issues,
    coordination_source,
    run_product_probe,
    trace_differences,
)


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "cp_live_m0"
FIXTURE = FIXTURE_DIR / "baseline-v3.json"
DIGEST = FIXTURE.with_suffix(".sha256")

# The commit whose corrected runner this reference characterizes. Re-pointing
# the reference at another commit is a decision that has to be taken here, in
# test code, and not by editing the artifact.
BASELINE_SOURCE_SHA = "b428129874f6e668e5074e1b29fa3d208c87df14"


@pytest.fixture(scope="module")
def baseline() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _assert_candidate_provenance(verdict: dict, *, substituted: frozenset):
    """The child's measured provenance, asserted apart from its trace.

    One namespace per process, files inside this tree, no dispatch attempted,
    the doubles installed and the rules left real -- judged by the same
    function the recorder uses before it writes a reference.
    """

    issues = candidate_provenance_issues(
        verdict["provenance"],
        interpreter=sys.executable,
        substituted_required=substituted,
        never_substituted=PRODUCT_RULE_SYMBOLS,
    )

    assert issues == [], {"issues": issues, "provenance": verdict["provenance"]}


def test_reference_artifact_has_pinned_source_and_external_digest(baseline):
    assert baseline["schema"] == "cp-live-m0-equivalence-baseline-v3"
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
    # The reference names the scope it was verified against, not just its
    # source commit.
    scope = baseline["provenance"]["executed_scope"]
    assert scope["verified_against_source_commit"] is True
    assert scope["repository_files"] > len(scope["recording_inputs"])
    assert sorted(scope["roots"]) == ["src", "tests", "tools"]
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


def test_every_superseded_reference_is_retained_and_still_verifiable(baseline):
    chain = baseline["supersedes"]

    assert [item["fixture_version"] for item in chain] == list(
        HISTORICAL_FIXTURE_VERSIONS
    )
    for superseded in chain:
        retained = ROOT / superseded["retained_as"]
        # Retained as history, not as an oracle: each still matches its own
        # digest, recorded here and in the file beside it.
        digest = hashlib.sha256(retained.read_bytes()).hexdigest()
        assert digest == superseded["sha256"], superseded["retained_as"]
        assert digest == (
            retained.with_suffix(".sha256")
            .read_text(encoding="ascii").strip().split()[0]
        ), superseded["retained_as"]
        # Every difference against it is named, not implied.
        assert superseded["justified_differences"], superseded["fixture_version"]
        for difference in superseded["justified_differences"]:
            assert difference["change"] and difference["why"]


@pytest.mark.parametrize(
    "scenario",
    tuple(item for item in SCENARIOS if item != "cleanup-failure"),
)
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
    _assert_candidate_provenance(
        verdict, substituted=LEVEL_A_SUBSTITUTED_SYMBOLS,
    )


def test_cleanup_retry_correction_is_an_explicit_delta_from_the_frozen_oracle(
    baseline,
    tmp_path,
):
    historical = baseline["coordination"]["cleanup-failure"]
    expected = copy.deepcopy(historical)
    cleanup_positions = [
        index for index, event in enumerate(expected["events"])
        if event.get("event") == "cleanup"
    ]
    assert len(cleanup_positions) == 2
    assert cleanup_positions[1] == cleanup_positions[0] + 1
    del expected["events"][cleanup_positions[1]]
    expected["final"]["failure"] = (
        "CanonicalLiveFailure: Router0 verification completed, but "
        "cleanup/restoration did not verify: RuntimeError: "
        "SYNTHETIC_CLEANUP_FAILURE"
    )

    verdict = run_product_probe(
        coordination_source("cleanup-failure"),
        tmp_path / "cleanup-failure-corrected",
    )

    assert trace_differences(expected, verdict["trace"]) == []
    assert sum(
        event.get("event") == "cleanup" for event in verdict["trace"]["events"]
    ) == 1
    _assert_candidate_provenance(
        verdict, substituted=LEVEL_A_SUBSTITUTED_SYMBOLS,
    )


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


def test_the_capture_keeps_every_dispatch_its_order_and_its_multiplicity(
    baseline,
    tmp_path,
):
    """An operation the runtime added must reach the trace, not fall off a zip."""

    recorded = baseline["policy_trace"]
    assert recorded["cardinality"] == {
        "planned_checks": 2,
        "dispatched_operations": 2,
        "evidence_records": 2,
        "unplanned_operations": [],
        "aligned": True,
    }

    verdict = run_product_probe(
        POLICY_TRACE_EXTRA_DISPATCH_SOURCE, tmp_path / "extra-dispatch",
    )
    observed = verdict["trace"]

    # Measured before any comparison: the extra dispatch is in the capture.
    assert len(observed["operations"]) == 3
    assert observed["cardinality"]["dispatched_operations"] == 3
    assert observed["cardinality"]["unplanned_operations"] == [2]
    assert observed["cardinality"]["aligned"] is False
    assert observed["operations"][1] == {
        "sequence": 2,
        "phase": "site-forwarding",
        "operation_id": "",
        "recipient": "Router4",
        "destination": "198.51.100.99",
        "authority": "",
        "declared_traffic_flow_id": "",
        "reverse_of_traffic_flow_id": "",
        "status": "",
        "planned": False,
        "attributed_evidence": False,
    }
    assert observed["operations"][2]["operation_id"] == (
        "forward/multilayer-to-large"
    )
    assert observed["operations"][2]["status"] == "VERIFIED"
    assert "198.51.100.99" in {
        item["destination"] for item in observed["operations"]
    }
    # And the oracle refuses it, naming the operations rather than a count.
    differences = trace_differences(recorded, observed)
    assert any("operations" in item for item in differences), differences
    assert any("cardinality" in item for item in differences), differences


def test_duplicate_dispatch_is_ambiguous_and_cannot_inherit_verified(
    baseline,
    tmp_path,
):
    verdict = run_product_probe(
        POLICY_TRACE_DUPLICATE_DISPATCH_SOURCE,
        tmp_path / "duplicate-dispatch",
    )
    observed = verdict["trace"]

    assert [item["destination"] for item in observed["operations"]] == [
        "192.0.2.20",
        "192.0.2.20",
        "192.0.2.10",
    ]
    assert observed["cardinality"]["unplanned_operations"] == [1, 2]
    assert observed["cardinality"]["aligned"] is False
    assert all(
        item["status"] != "VERIFIED" for item in observed["operations"][:2]
    )
    assert trace_differences(baseline["policy_trace"], observed)


def test_wrong_destination_is_observed_but_gets_no_planned_identity_or_evidence(
    baseline,
    tmp_path,
):
    verdict = run_product_probe(
        POLICY_TRACE_WRONG_DESTINATION_SOURCE,
        tmp_path / "wrong-destination",
    )
    observed = verdict["trace"]

    assert [item["destination"] for item in observed["operations"]] == [
        "198.51.100.99",
        "192.0.2.10",
    ]
    wrong = observed["operations"][0]
    assert wrong["planned"] is False
    assert wrong["attributed_evidence"] is False
    assert wrong["operation_id"] == ""
    assert wrong["status"] == ""
    assert observed["operations"][1]["operation_id"] == (
        "forward/multilayer-to-large"
    )
    assert observed["cardinality"]["unplanned_operations"] == [1]
    assert observed["cardinality"]["aligned"] is False
    assert trace_differences(baseline["policy_trace"], observed)


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
