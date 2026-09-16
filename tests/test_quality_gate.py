"""Behavioral tests for the incremental Ruff quality gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.quality_gate import QualityGateError, changed_python_files

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
QUALITY_GATE = REPOSITORY_ROOT / "scripts" / "quality_gate.py"


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run Git in a temporary repository and require success."""
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


def _initialize_repository(repository: Path) -> None:
    """Create a repository with one baseline commit."""
    _git(repository, "init", "--initial-branch=main")
    _git(repository, "config", "user.email", "quality-gate@example.invalid")
    _git(repository, "config", "user.name", "Quality Gate Test")
    (repository / "baseline.py").write_text("BASELINE = True\n", encoding="utf-8")
    _git(repository, "add", "baseline.py")
    _git(repository, "commit", "-m", "test: create baseline")


def test_changed_python_files_cover_committed_worktree_and_untracked_changes(
    tmp_path: Path,
) -> None:
    """Select all current Python changes while ignoring non-Python files."""
    _initialize_repository(tmp_path)
    baseline = _git(tmp_path, "rev-parse", "HEAD").stdout.strip()

    (tmp_path / "committed.py").write_text("COMMITTED = True\n", encoding="utf-8")
    _git(tmp_path, "add", "committed.py")
    _git(tmp_path, "commit", "-m", "test: add committed file")
    (tmp_path / "baseline.py").write_text("BASELINE = False\n", encoding="utf-8")
    (tmp_path / "untracked.py").write_text("UNTRACKED = True\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("Not Python.\n", encoding="utf-8")

    selected = changed_python_files(tmp_path, baseline)

    assert [path.name for path in selected] == [
        "baseline.py",
        "committed.py",
        "untracked.py",
    ]


def test_changed_python_files_fail_closed_for_unknown_base(tmp_path: Path) -> None:
    """Reject an invalid comparison base instead of silently checking nothing."""
    _initialize_repository(tmp_path)

    with pytest.raises(QualityGateError, match="comparison base"):
        changed_python_files(tmp_path, "missing-ref")


@pytest.mark.parametrize(
    ("source", "expected_return_code"),
    [
        ('"""Clean module."""\n\nVALUE = 1\n', 0),
        ('"""Invalid module."""\n\nimport os\n', 1),
    ],
)
def test_quality_gate_has_positive_and_negative_controls(
    tmp_path: Path,
    source: str,
    expected_return_code: int,
) -> None:
    """Accept clean code and reject a reproducible unused-import violation."""
    candidate = tmp_path / "candidate.py"
    candidate.write_text(source, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(QUALITY_GATE),
            "--files",
            str(candidate),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == expected_return_code, result.stdout + result.stderr
