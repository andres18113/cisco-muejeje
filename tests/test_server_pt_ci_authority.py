"""Exact delivery SHA and all CI jobs bind every LIVE phase."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def _jobs():
    return [
        {"name": f"pytest ({os}, {python})", "conclusion": "success"}
        for os in ("windows-latest", "ubuntu-latest")
        for python in ("3.11", "3.13")
    ] + [
        {"name": "quality", "conclusion": "success"},
        {"name": "docs", "conclusion": "success"},
    ]


def test_exact_sha_ci_requires_the_whole_green_matrix():
    """A green run for another SHA or one missing job cannot seal a phase."""
    from packet_tracer_mcp.infrastructure.execution.server_pt_campaign_authority import (
        exact_ci_findings,
    )

    sha = "a" * 40
    run = {
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success",
        "name": "tests",
        "event": "push",
    }

    assert exact_ci_findings(run, _jobs(), sha) == ()
    assert "ci_head_mismatch" in exact_ci_findings(run, _jobs(), "b" * 40)
    assert "ci_matrix_incomplete" in exact_ci_findings(run, _jobs()[:-1], sha)
    failed = _jobs()
    failed[0]["conclusion"] = "failure"
    assert "ci_job_not_green" in exact_ci_findings(run, failed, sha)


def test_ci_reader_checks_the_exact_run_and_all_jobs(tmp_path: Path):
    """The effecting process fetches GitHub's run and complete job page."""
    from packet_tracer_mcp.infrastructure.execution.server_pt_campaign_authority import (
        read_exact_ci,
    )

    calls = []

    def command(argv, **_kwargs):
        calls.append(argv)
        body = (
            {
                "head_sha": "a" * 40,
                "status": "completed",
                "conclusion": "success",
                "name": "tests",
                "event": "push",
                "html_url": "https://example.test/run/42",
            }
            if len(calls) == 1
            else {"total_count": 6, "jobs": _jobs()}
        )
        return SimpleNamespace(stdout=json.dumps(body))

    evidence, findings = read_exact_ci(
        42, "a" * 40, checkout=tmp_path, run_command=command
    )

    assert findings == ()
    assert evidence is not None
    assert evidence.run_id == 42
    assert len(evidence.jobs) == 6
    assert len(calls) == 2
    assert calls[0][0:2] == ["gh", "api"]
