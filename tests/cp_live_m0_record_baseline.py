"""Explicit, test-only recorder for the CP-LIVE M0 equivalence reference.

Nothing regenerates the expected artifact during ``pytest``: this file is not a
test module, pytest never collects it, and it refuses to run inside a pytest
process.  Recording a reference is a decision, so it is taken here, by hand,
against a named commit:

    .venv/bin/python -m tests.cp_live_m0_record_baseline \\
        --record --source-sha <sha of the corrected code>

The recorder refuses unless every characterized file in the worktree is byte
identical to that commit, so a reference can never describe code that was never
committed.  It writes the JSON with the same byte contract as the previous
reference (sorted keys, two-space indent, LF, trailing newline) and the
external digest beside it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import tempfile
from importlib.metadata import version
from pathlib import Path

from tests.cp_live_m0_harness import (
    FIXTURE_VERSION,
    HARDENING_BASE_SHA,
    HISTORICAL_FIXTURE_VERSION,
    POLICY_TRACE_SOURCE,
    ROOT,
    SCENARIOS,
    coordination_source,
    run_product_probe,
)


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "cp_live_m0"
FIXTURE = FIXTURE_DIR / "baseline-v2.json"
DIGEST = FIXTURE.with_suffix(".sha256")
HISTORICAL_FIXTURE = FIXTURE_DIR / "baseline-v1.json"
SCHEMA = "cp-live-m0-equivalence-baseline-v2"

# Every file whose content decides what the reference records. The runner is the
# characterized code; the harness and the Router0 doubles decide what is asked
# of it and what crosses back.
CHARACTERIZED_PATHS = (
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

SUPERSEDES = {
    "fixture_version": HISTORICAL_FIXTURE_VERSION,
    "schema": "cp-live-m0-equivalence-baseline-v1",
    "source_commit": HARDENING_BASE_SHA,
    "sha256": (
        "99adcea78b0dbf861cfa4a32b49c50577ea6d0cca3f33725a136272273387634"
    ),
    "retained_as": "tests/fixtures/cp_live_m0/baseline-v1.json",
    "retained_reason": (
        "It is the historical record of the defective finalization and stays "
        "verifiable; it is no longer the oracle."
    ),
    "justified_differences": [
        {
            "change": (
                "Every probe verdict is split into 'trace' and 'provenance'."
            ),
            "why": (
                "v1 compared one flat dict and declared its isolation in the "
                "expected file. The candidate now measures its own provenance "
                "and it is asserted, never compared and never used to "
                "normalize the trace."
            ),
        },
        {
            "change": (
                "policy_trace.configuration_acceptance is replaced by "
                "policy_trace.configuration with an accepted and a rejected "
                "decision."
            ),
            "why": (
                "v1 derived acceptance from configuration_application_"
                "contradiction alone, so an absent contradiction read as "
                "canonical acceptance. The reference now records "
                "canonical_stage_configuration_error over a coherent plan and "
                "read-back, including a promoted-ceiling rejection that is "
                "contradiction free and still refused."
            ),
        },
        {
            "change": (
                "The recorded source is the corrected runner, not "
                + HARDENING_BASE_SHA[:12]
                + "."
            ),
            "why": (
                "Finalization no longer skips transport.stop() after a failed "
                "final write and no longer lets a write or close failure "
                "replace the primary cause. No coordination scenario in this "
                "reference exercises a failing write or close, so their frozen "
                "traces are unchanged by the correction."
            ),
        },
    ],
}


def _git(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )


def _require_characterized_source(source_sha: str) -> str:
    """Refuse to record a reference for code that is not exactly committed."""

    tree = _git("show", "-s", "--format=%T", source_sha)
    if tree.returncode != 0:
        raise SystemExit(
            f"Unknown source commit {source_sha}: "
            + tree.stderr.decode("utf-8", "replace").strip()
        )
    for relative in CHARACTERIZED_PATHS:
        committed = _git("show", f"{source_sha}:{relative}")
        if committed.returncode != 0:
            raise SystemExit(f"{relative} is absent from {source_sha}.")
        if committed.stdout != (ROOT / relative).read_bytes():
            raise SystemExit(
                f"{relative} in the worktree differs from {source_sha}; commit "
                "the characterized code before recording a reference."
            )
    return tree.stdout.decode("ascii").strip()


def record(source_sha: str) -> Path:
    source_tree = _require_characterized_source(source_sha)
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
    print(f"  {HISTORICAL_FIXTURE.relative_to(ROOT)} is retained unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
