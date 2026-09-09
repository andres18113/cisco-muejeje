"""What must hold before a reference may claim a source commit.

The recorder is not a test module and never runs inside pytest.  Its decisions
are, so they live in pure functions: which files the recording actually
executed, whether those bytes are the ones committed at the named SHA, and
whether each probe's own provenance allows recording at all.  Nothing here
writes a reference, reaches the network, or regenerates an expectation.
"""

from __future__ import annotations

import pytest

from tests import cp_live_m0_record_baseline as recorder
from tests.cp_live_m0_harness import (
    LEVEL_A_SUBSTITUTED_SYMBOLS,
    coordination_source,
    run_product_probe,
)


# A rule the probes import and execute, and that no static list ever named.
IMPORTED_RULE = (
    "src/packet_tracer_mcp/application/use_cases/qualify_cp_scale_live.py"
)
SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"


def _readers(contents: dict[str, bytes]):
    def read(relative):
        try:
            return contents[relative]
        except KeyError:
            raise OSError(f"missing {relative}")

    return read


def test_the_executed_scope_covers_the_rules_the_probes_import(tmp_path):
    verdict = run_product_probe(
        coordination_source("router0-cleanup"), tmp_path / "scope",
    )

    executed = verdict["provenance"]["executed_repository_files"]
    scope = recorder.executed_scope([verdict])

    # The hole this closes: the static inputs never named the rules under src,
    # so a reference could be attributed to a commit whose executable
    # dependencies had moved underneath it.
    assert IMPORTED_RULE not in recorder.RECORDING_INPUT_PATHS
    assert IMPORTED_RULE in executed, executed[:10]
    assert "tools/cp_scale_canonical_live.py" in executed
    assert set(recorder.RECORDING_INPUT_PATHS) <= set(scope)
    assert IMPORTED_RULE in scope
    # Only repository sources are in scope; the checkout-local environment is
    # counted and named separately, never silently dropped.
    assert {item.split("/")[0] for item in scope} <= {"src", "tests", "tools"}
    assert verdict["provenance"]["executed_environment_files"] > 0


def test_a_modified_imported_rule_refuses_the_recording():
    committed = {IMPORTED_RULE: b"rule", "tools/runner.py": b"runner"}
    worktree = dict(committed)
    worktree[IMPORTED_RULE] = b"rule\n# drifted after the commit\n"

    mismatched = recorder.scope_mismatches(
        SOURCE_SHA,
        sorted(committed),
        read_worktree=_readers(worktree),
        read_committed=lambda relative: committed.get(relative),
    )

    assert mismatched == [f"{IMPORTED_RULE}: differs from {SOURCE_SHA[:12]}"]


def test_an_unchanged_scope_is_accepted():
    committed = {IMPORTED_RULE: b"rule", "tools/runner.py": b"runner"}

    assert recorder.scope_mismatches(
        SOURCE_SHA,
        sorted(committed),
        read_worktree=_readers(committed),
        read_committed=lambda relative: committed.get(relative),
    ) == []


@pytest.mark.parametrize(
    ("absent_from", "expected"),
    [
        ("commit", f"{IMPORTED_RULE}: absent from {SOURCE_SHA[:12]}"),
        ("worktree", f"{IMPORTED_RULE}: absent from the worktree"),
    ],
)
def test_a_file_missing_from_either_side_refuses_the_recording(
    absent_from,
    expected,
):
    committed = {IMPORTED_RULE: b"rule"}
    worktree = dict(committed)
    if absent_from == "commit":
        committed = {}
    else:
        worktree = {}

    mismatched = recorder.scope_mismatches(
        SOURCE_SHA,
        [IMPORTED_RULE],
        read_worktree=_readers(worktree),
        read_committed=lambda relative: committed.get(relative),
    )

    assert mismatched == [expected]


def test_probe_provenance_is_refused_before_anything_is_written():
    healthy = {
        "interpreter": recorder.sys.executable,
        "loaded_namespaces": ["packet_tracer_mcp"],
        "package_file_inside_tree": True,
        "runner_file_inside_tree": True,
        "governed_root_inside_tree": True,
        "transport_dispatch_attempts": [],
        "substituted_runner_symbols": sorted(LEVEL_A_SUBSTITUTED_SYMBOLS),
        "executed_repository_files": [IMPORTED_RULE],
    }
    dispatched = {**healthy, "transport_dispatch_attempts": ["send_and_wait"]}
    foreign = {**healthy, "loaded_namespaces": ["src.packet_tracer_mcp"]}
    undoubled = {
        **healthy,
        "substituted_runner_symbols": sorted(
            LEVEL_A_SUBSTITUTED_SYMBOLS - {"_build_coordinator"},
        ),
    }

    assert recorder.provenance_refusals({"router0-cleanup": {
        "provenance": healthy,
    }}) == []
    assert recorder.provenance_refusals({"router0-cleanup": {
        "provenance": dispatched,
    }}) == [
        "router0-cleanup: transport dispatch was attempted: ['send_and_wait']",
    ]
    assert recorder.provenance_refusals({"floor2-failure": {
        "provenance": foreign,
    }}) == [
        "floor2-failure: loaded namespaces are ['src.packet_tracer_mcp']",
    ]
    assert recorder.provenance_refusals({"full-cleanup": {
        "provenance": undoubled,
    }}) == [
        "full-cleanup: not substituted: _build_coordinator",
    ]
    # The policy trace substitutes nothing, so the same provenance without the
    # doubles is exactly what it should report.
    assert recorder.provenance_refusals({"policy_trace": {
        "provenance": {**healthy, "substituted_runner_symbols": []},
    }}) == []


@pytest.mark.parametrize(
    "invalid_attempts",
    [pytest.param(None, id="none"), pytest.param("", id="wrong-type")],
)
def test_probe_provenance_requires_typed_dispatch_attempt_metrics(
    invalid_attempts,
):
    healthy = {
        "interpreter": recorder.sys.executable,
        "loaded_namespaces": ["packet_tracer_mcp"],
        "package_file_inside_tree": True,
        "runner_file_inside_tree": True,
        "governed_root_inside_tree": True,
        "transport_dispatch_attempts": [],
        "substituted_runner_symbols": sorted(LEVEL_A_SUBSTITUTED_SYMBOLS),
        "executed_repository_files": [IMPORTED_RULE],
    }
    provenance = {
        **healthy,
        "transport_dispatch_attempts": invalid_attempts,
    }

    refusals = recorder.provenance_refusals({"router0-cleanup": {
        "provenance": provenance,
    }})

    assert len(refusals) == 1
    assert "transport_dispatch_attempts" in refusals[0]
    assert "must be a list of strings" in refusals[0]


def test_probe_provenance_requires_dispatch_attempt_metric_to_be_present():
    provenance = {
        "interpreter": recorder.sys.executable,
        "loaded_namespaces": ["packet_tracer_mcp"],
        "package_file_inside_tree": True,
        "runner_file_inside_tree": True,
        "governed_root_inside_tree": True,
        "substituted_runner_symbols": sorted(LEVEL_A_SUBSTITUTED_SYMBOLS),
        "executed_repository_files": [IMPORTED_RULE],
    }

    refusals = recorder.provenance_refusals({"router0-cleanup": {
        "provenance": provenance,
    }})

    assert len(refusals) == 1
    assert "transport_dispatch_attempts" in refusals[0]
    assert "must be a list of strings" in refusals[0]


def test_an_unknown_source_commit_is_refused_before_any_probe_runs():
    with pytest.raises(SystemExit) as refusal:
        recorder.record("f" * 40)

    assert "Unknown source commit" in str(refusal.value)
