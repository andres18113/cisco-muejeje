"""Explicit, test-only recorder for the CP-LIVE M0 equivalence reference.

Nothing regenerates the expected artifact during ``pytest``: this file is not a
test module, pytest never collects it, and it refuses to run inside a pytest
process.  Recording a reference is a decision, so it is taken here, by hand,
against a named commit:

    .venv/bin/python -m tests.cp_live_m0_record_baseline \\
        --record --source-sha <sha of the corrected code>

The recorder refuses unless every file the recording actually executed is byte
identical to that commit, so a reference can never be attributed to a SHA whose
executable dependencies differ.  That scope is measured, not assumed: each
probe reports the repository files it imported, and the union of those plus the
static recording inputs is what gets verified.  Probe provenance is checked
first, so a reference is never written for a run that loaded the wrong
namespace or attempted a dispatch.

It writes the JSON with the same byte contract as the previous reference
(sorted keys, two-space indent, LF, trailing newline) and the external digest
beside it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

from tests.cp_live_m0_harness import (
    BASELINE_V2_SOURCE_SHA,
    FIXTURE_VERSION,
    HARDENING_BASE_SHA,
    HISTORICAL_FIXTURE_VERSIONS,
    LEVEL_A_SUBSTITUTED_SYMBOLS,
    POLICY_TRACE_SOURCE,
    ROOT,
    SCENARIOS,
    candidate_provenance_issues,
    coordination_source,
    run_product_probe,
)


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "cp_live_m0"
FIXTURE = FIXTURE_DIR / "baseline-v3.json"
DIGEST = FIXTURE.with_suffix(".sha256")
SCHEMA = "cp-live-m0-equivalence-baseline-v3"

# The files that decide what is asked of the runner and what crosses back.
# They are the static half of the scope; the executed half is measured by the
# probes themselves and covers the real rules under src that they import.
RECORDING_INPUT_PATHS = (
    "tools/cp_scale_canonical_live.py",
    "tests/cp_live_m0_harness.py",
    "tests/test_cp_scale_router0_live_runner.py",
    "tests/cp_live_m0_record_baseline.py",
)

COMPARISON = {
    "candidate_provenance_is_asserted_not_compared": True,
    "omitted_nondeterministic_fields": {
        "absolute temporary paths": (
            "the harness intentionally relocates host state per probe"
        ),
        "run identity and archive filename digests": (
            "generated identifiers are not operation identities"
        ),
        "session timestamps": (
            "wall-clock values do not alter orchestration semantics"
        ),
    },
    "ordered_fields": [
        "coordination.*.events",
        "coordination.*.final.stages",
        "policy_trace.operations",
        "policy_trace.replay.surfaces.*.journaled_action_ids",
    ],
    "provenance_is_not_normalized": True,
    "security_fields_never_normalized": [
        "authority",
        "declared_traffic_flow_id",
        "reverse_of_traffic_flow_id",
        "recipient",
        "destination",
        "status",
        "verified",
        "canonically_accepted",
        "canonical_acceptance_error",
        "contradiction",
        "first_failed_boundary",
        "failure",
        "closure",
        "cleanup",
        "journaled_action_ids",
    ],
}

# Newest first. Every superseded reference stays in the tree, stays verifiable
# by its own digest, and names what changed against it.
SUPERSEDES = [
    {
        "fixture_version": HISTORICAL_FIXTURE_VERSIONS[0],
        "schema": "cp-live-m0-equivalence-baseline-v2",
        "source_commit": BASELINE_V2_SOURCE_SHA,
        "sha256": (
            "766bcbe6de16a320f9dcc5e3bb8d7c0ae4ad5ccf807bf14bd1814dd6a5f10cc9"
        ),
        "retained_as": "tests/fixtures/cp_live_m0/baseline-v2.json",
        "retained_reason": (
            "It is the record of the first corrected finalization and of the "
            "capture that a zip() could truncate; it stays verifiable and is "
            "no longer the oracle."
        ),
        "justified_differences": [
            {
                "change": (
                    "policy_trace.operations is built from every observed "
                    "dispatch and a policy_trace.cardinality block records "
                    "planned, dispatched and attributed counts."
                ),
                "why": (
                    "v2 zipped checks, calls and evidence together, so a "
                    "dispatch beyond the plan fell off the end of the shortest "
                    "sequence. Operations now keep their order and "
                    "multiplicity, each says whether it was planned and "
                    "attributed, and an extra-dispatch probe proves the "
                    "capture reacts to observed behaviour."
                ),
            },
            {
                "change": (
                    "provenance.executed_scope records the measured executed "
                    "scope this recording verified against its source commit."
                ),
                "why": (
                    "v2 verified four static files, so the real rules under "
                    "src that the probes execute were outside the check. The "
                    "scope is now measured by the probes themselves and every "
                    "file in it must match the named commit."
                ),
            },
            {
                "change": (
                    "The characterized source is the runner whose close is "
                    "protected through cleanup, archive and the re-read, and "
                    "whose report channel falls back and promises nothing."
                ),
                "why": (
                    "No coordination scenario in this reference fails a write, "
                    "a close or a report, so their frozen traces are "
                    "unchanged; only the policy trace and the provenance "
                    "differ from v2."
                ),
            },
        ],
    },
    {
        "fixture_version": HISTORICAL_FIXTURE_VERSIONS[1],
        "schema": "cp-live-m0-equivalence-baseline-v1",
        "source_commit": HARDENING_BASE_SHA,
        "sha256": (
            "99adcea78b0dbf861cfa4a32b49c50577ea6d0cca3f33725a136272273387634"
        ),
        "retained_as": "tests/fixtures/cp_live_m0/baseline-v1.json",
        "retained_reason": (
            "It is the historical record of the defective finalization and "
            "stays verifiable; it was superseded by v2."
        ),
        "justified_differences": [
            {
                "change": (
                    "Superseded by v2: verdicts split into trace and "
                    "provenance, and configuration acceptance came from "
                    "canonical_stage_configuration_error."
                ),
                "why": (
                    "v1 declared its isolation in the expected file and "
                    "derived acceptance from an absent contradiction. Both "
                    "are recorded in v2's own supersedes block."
                ),
            },
        ],
    },
]


def _git(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )


def _source_tree(source_sha: str) -> str:
    tree = _git("show", "-s", "--format=%T", source_sha)
    if tree.returncode != 0:
        raise SystemExit(
            f"Unknown source commit {source_sha}: "
            + tree.stderr.decode("utf-8", "replace").strip()
        )
    return tree.stdout.decode("ascii").strip()


def _committed_bytes(source_sha: str, relative: str) -> bytes | None:
    committed = _git("show", f"{source_sha}:{relative}")
    return committed.stdout if committed.returncode == 0 else None


def scope_mismatches(
    source_sha: str,
    paths,
    *,
    read_worktree=None,
    read_committed=None,
) -> list[str]:
    """Executed files whose bytes are not the ones committed at ``source_sha``.

    The readers are injectable so this rule can be exercised without touching
    the worktree: what it decides is whether a reference may claim that SHA.
    """

    if read_worktree is None:
        def read_worktree(relative):
            return (ROOT / relative).read_bytes()
    if read_committed is None:
        def read_committed(relative):
            return _committed_bytes(source_sha, relative)

    short = source_sha[:12]
    mismatched: list[str] = []
    for relative in sorted(paths):
        try:
            executed = read_worktree(relative)
        except OSError:
            mismatched.append(f"{relative}: absent from the worktree")
            continue
        committed = read_committed(relative)
        if committed is None:
            mismatched.append(f"{relative}: absent from {short}")
        elif committed != executed:
            mismatched.append(f"{relative}: differs from {short}")
    return mismatched


def executed_scope(verdicts) -> list[str]:
    """Every repository file the probes executed, plus the static inputs."""

    executed: set[str] = set(RECORDING_INPUT_PATHS)
    for verdict in verdicts:
        executed.update(verdict["provenance"]["executed_repository_files"])
    return sorted(executed)


def provenance_refusals(verdicts) -> list[str]:
    """Why these probes may not be recorded, before anything is written."""

    refusals: list[str] = []
    for name, verdict in verdicts.items():
        substituted = (
            frozenset() if name == "policy_trace" else LEVEL_A_SUBSTITUTED_SYMBOLS
        )
        for issue in candidate_provenance_issues(
            verdict["provenance"],
            interpreter=sys.executable,
            substituted_required=substituted,
        ):
            refusals.append(f"{name}: {issue}")
    return refusals


def record(source_sha: str) -> Path:
    source_tree = _source_tree(source_sha)
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        coordination = {
            scenario: run_product_probe(
                coordination_source(scenario), workspace / scenario,
            )
            for scenario in SCENARIOS
        }
        policy = run_product_probe(POLICY_TRACE_SOURCE, workspace / "policy")

    verdicts = {**coordination, "policy_trace": policy}
    refusals = provenance_refusals(verdicts)
    if refusals:
        raise SystemExit(
            "The probes' own provenance refuses this recording:\n  "
            + "\n  ".join(refusals)
        )
    scope = executed_scope(verdicts.values())
    mismatched = scope_mismatches(source_sha, scope)
    if mismatched:
        raise SystemExit(
            f"{len(mismatched)} executed file(s) differ from {source_sha[:12]}; "
            "commit the code this recording executes before attributing a "
            "reference to it:\n  " + "\n  ".join(mismatched[:20])
        )
    scope_digest = hashlib.sha256(
        "\n".join(scope).encode("utf-8"),
    ).hexdigest()

    baseline = {
        "schema": SCHEMA,
        "fixture_version": FIXTURE_VERSION,
        "provenance": {
            "dependencies": {
                name: version(name) for name in ("mcp", "pydantic", "pytest")
            },
            "generated_date": _git(
                "show", "-s", "--format=%cs", source_sha,
            ).stdout.decode("ascii").strip(),
            "interpreter": {
                "executable_contract": ".venv checkout-local interpreter",
                "implementation": platform.python_implementation(),
                "version": platform.python_version(),
            },
            "executed_scope": {
                "digest": scope_digest,
                "environment_files": max(
                    verdict["provenance"]["executed_environment_files"]
                    for verdict in verdicts.values()
                ),
                "recording_inputs": list(RECORDING_INPUT_PATHS),
                "repository_files": len(scope),
                "roots": sorted({item.split("/")[0] for item in scope}),
                "verified_against_source_commit": True,
            },
            "live_environment_contacted": False,
            "platform": platform.platform(),
            "reference_branch": branch.decode("utf-8").strip(),
            "repository": "andres18113/cisco-muejeje",
            "source_commit": source_sha,
            "source_tree": source_tree,
            "synthetic_test_capabilities": True,
        },
        "supersedes": SUPERSEDES,
        "comparison": COMPARISON,
        "coordination": {
            scenario: verdict["trace"]
            for scenario, verdict in coordination.items()
        },
        "policy_trace": policy["trace"],
    }
    payload = (json.dumps(baseline, indent=2, sort_keys=True) + "\n").encode(
        "utf-8",
    )
    FIXTURE.write_bytes(payload)
    DIGEST.write_bytes(
        f"{hashlib.sha256(payload).hexdigest()}  {FIXTURE.name}\n".encode(
            "ascii",
        ),
    )
    return FIXTURE


def main() -> int:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        raise SystemExit(
            "The reference is never regenerated from inside a test run.",
        )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--record",
        action="store_true",
        help="Authorize overwriting the reference and its digest.",
    )
    parser.add_argument(
        "--source-sha",
        required=True,
        help="Commit of the corrected code this reference characterizes.",
    )
    arguments = parser.parse_args()
    if not arguments.record:
        print("--record is required; no reference was written.")
        return 2
    written = record(arguments.source_sha)
    print(f"Recorded {written.relative_to(ROOT)} for {arguments.source_sha}")
    for superseded in SUPERSEDES:
        print(f"  {superseded['retained_as']} is retained unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
