"""Read exact-SHA CI evidence before a C31 Packet Tracer phase can contact."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CI_REPOSITORY = "andres18113/cisco-muejeje"
_EXPECTED_JOBS = frozenset(
    {
        "pytest (windows-latest, 3.11)",
        "pytest (windows-latest, 3.13)",
        "pytest (ubuntu-latest, 3.11)",
        "pytest (ubuntu-latest, 3.13)",
        "quality",
        "docs",
    }
)


@dataclass(frozen=True)
class ExactCiEvidence:
    """The exact successful workflow and six checked jobs."""

    run_id: int
    head_sha: str
    url: str
    jobs: tuple[str, ...]


def exact_ci_findings(
    run: Mapping[str, Any], jobs: Sequence[Mapping[str, Any]], expected_sha: str
) -> tuple[str, ...]:
    """Refuse a green label without the exact push SHA and complete matrix."""
    found: list[str] = []
    if run.get("head_sha") != expected_sha:
        found.append("ci_head_mismatch")
    if (
        run.get("name") != "tests"
        or run.get("event") != "push"
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
    ):
        found.append("ci_workflow_not_green")
    names = [item.get("name") for item in jobs]
    if not _EXPECTED_JOBS <= set(names):
        found.append("ci_matrix_incomplete")
    if len(names) != len(set(names)) or any(
        item.get("conclusion") != "success" for item in jobs
    ):
        found.append("ci_job_not_green")
    return tuple(found)


def read_exact_ci(
    run_id: int,
    expected_sha: str,
    *,
    checkout: Path,
    run_command: Callable[..., Any] = subprocess.run,
) -> tuple[ExactCiEvidence | None, tuple[str, ...]]:
    """Ask GitHub for this run and its jobs in the effecting Python process."""
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
        return None, ("ci_run_id_invalid",)
    base = f"repos/{CI_REPOSITORY}/actions/runs/{run_id}"

    def query(path: str) -> Mapping[str, Any]:
        completed = run_command(
            ["gh", "api", path],
            cwd=checkout,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        data = json.loads(completed.stdout)
        if not isinstance(data, dict):
            raise ValueError("GitHub returned no JSON object")
        return data

    try:
        run = query(base)
        page = query(base + "/jobs?per_page=100")
        jobs = page.get("jobs")
        if not isinstance(jobs, list) or page.get("total_count") != len(jobs):
            return None, ("ci_jobs_unobservable",)
        findings = exact_ci_findings(run, jobs, expected_sha)
        if findings:
            return None, findings
        url = run.get("html_url")
        if not isinstance(url, str) or not url:
            return None, ("ci_run_url_unobservable",)
        return (
            ExactCiEvidence(
                run_id=run_id,
                head_sha=expected_sha,
                url=url,
                jobs=tuple(sorted(item["name"] for item in jobs)),
            ),
            (),
        )
    except (OSError, ValueError, subprocess.SubprocessError, KeyError) as exc:
        return None, (f"ci_unobservable:{type(exc).__name__}",)


_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class SourceAncestry:
    """Whether one commit is an ancestor of another, and its tree."""

    ancestor_sha: str
    descendant_sha: str
    ancestor_tree: str = ""
    is_ancestor: bool = False
    error: str = ""


def read_source_ancestry(
    checkout: Path,
    ancestor_sha: str,
    descendant_sha: str,
    *,
    run_command: Callable[..., Any] = subprocess.run,
) -> SourceAncestry:
    """Ask Git, read-only, for the ancestor's tree and the ancestry relation.

    Both arguments must be full lowercase SHAs, so no other text reaches Git.
    An unanswered question is an error, never a negative answer.
    """
    if not (
        isinstance(ancestor_sha, str)
        and isinstance(descendant_sha, str)
        and _COMMIT.fullmatch(ancestor_sha)
        and _COMMIT.fullmatch(descendant_sha)
    ):
        return SourceAncestry(
            str(ancestor_sha), str(descendant_sha), error="source_sha_invalid"
        )

    def git(*arguments: str) -> subprocess.CompletedProcess:
        return run_command(
            ["git", *arguments],
            cwd=checkout,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    try:
        tree = git("rev-parse", "--verify", f"{ancestor_sha}^{{tree}}")
        relation = git("merge-base", "--is-ancestor", ancestor_sha, descendant_sha)
    except (OSError, subprocess.SubprocessError) as exc:
        return SourceAncestry(
            ancestor_sha, descendant_sha, error=f"git_unobservable:{type(exc).__name__}"
        )
    value = str(tree.stdout or "").strip()
    if tree.returncode != 0 or _COMMIT.fullmatch(value) is None:
        return SourceAncestry(
            ancestor_sha, descendant_sha, error="ancestor_tree_unread"
        )
    if relation.returncode not in (0, 1):
        return SourceAncestry(
            ancestor_sha, descendant_sha, value, error="ancestry_unobservable"
        )
    return SourceAncestry(
        ancestor_sha, descendant_sha, value, is_ancestor=relation.returncode == 0
    )
