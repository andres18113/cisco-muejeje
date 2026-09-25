"""Behavioral tests for the incremental Ruff quality gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import quality_gate
from scripts.quality_gate import (
    QualityGateError,
    run_ruff,
    select_delivery_changes,
    select_worktree_changes,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
QUALITY_GATE = REPOSITORY_ROOT / "scripts" / "quality_gate.py"


def test_ruff_batches_every_long_windows_path_and_keeps_a_failure(
    tmp_path: Path, monkeypatch
) -> None:
    """Windows command length cannot silently drop any selected Python file."""
    files = tuple(
        tmp_path / ("nested_" * 20) / f"candidate_{index:03}.py" for index in range(220)
    )
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(
            argv,
            1 if argv[3] == "check" and len(calls) == 1 else 0,
        )

    monkeypatch.setattr(quality_gate.subprocess, "run", fake_run)
    assert run_ruff(files, repository=tmp_path) == 1
    for phase in ("check", "format"):
        phase_calls = [argv for argv in calls if argv[3] == phase]
        assert len(phase_calls) > 1
        observed = [
            Path(name)
            for argv in phase_calls
            for name in argv[argv.index("--config") + 2 :]
        ]
        assert sorted(observed) == sorted(files)
        assert all(len(subprocess.list2cmdline(argv)) <= 8_000 for argv in phase_calls)


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run Git in a temporary repository and require success."""
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


def _initialize_repository(repository: Path) -> str:
    """Create a repository with one baseline commit and return its SHA."""
    repository.mkdir(parents=True, exist_ok=True)
    _git(repository, "init", "--initial-branch=main")
    _git(repository, "config", "user.email", "quality-gate@example.invalid")
    _git(repository, "config", "user.name", "Quality Gate Test")
    (repository / "baseline.py").write_text("BASELINE = True\n", encoding="utf-8")
    _git(repository, "add", "baseline.py")
    _git(repository, "commit", "-m", "test: create baseline")
    return _git(repository, "rev-parse", "HEAD").stdout.strip()


def _selected_names(files: tuple[Path, ...]) -> list[str]:
    """Return stable file names for assertions."""
    return [path.name for path in files]


def test_worktree_selection_uses_cisco_and_covers_every_change_state(
    tmp_path: Path,
) -> None:
    """Resolve cisco/main without origin and select every current Git state."""
    remote = tmp_path / "authoritative.git"
    repository = tmp_path / "checkout"
    _git(tmp_path, "init", "--bare", str(remote))
    baseline = _initialize_repository(repository)
    _git(repository, "remote", "add", "cisco", str(remote))
    _git(repository, "push", "--set-upstream", "cisco", "main")

    (repository / "committed.py").write_text("COMMITTED = True\n", encoding="utf-8")
    _git(repository, "add", "committed.py")
    _git(repository, "commit", "-m", "test: add committed file")
    (repository / "staged.py").write_text("STAGED = True\n", encoding="utf-8")
    _git(repository, "add", "staged.py")
    (repository / "baseline.py").write_text("BASELINE = False\n", encoding="utf-8")
    (repository / "untracked.py").write_text("UNTRACKED = True\n", encoding="utf-8")
    (repository / "notes.md").write_text("Not Python.\n", encoding="utf-8")

    selection = select_worktree_changes(repository, "cisco/main")

    assert _git(repository, "remote").stdout.splitlines() == ["cisco"]
    assert selection.mode == "worktree"
    assert selection.base_sha == baseline
    assert selection.merge_base_sha == baseline
    assert _selected_names(selection.files) == [
        "baseline.py",
        "committed.py",
        "staged.py",
        "untracked.py",
    ]


def test_worktree_selection_fails_closed_for_unknown_base(tmp_path: Path) -> None:
    """Reject an invalid comparison base instead of checking nothing."""
    repository = tmp_path / "checkout"
    _initialize_repository(repository)

    with pytest.raises(QualityGateError, match="comparison base 'missing-ref'"):
        select_worktree_changes(repository, "missing-ref")


def test_full_gate_requires_an_explicit_base() -> None:
    """Reject a full-gate invocation that could otherwise guess a remote."""
    result = subprocess.run(
        [sys.executable, str(QUALITY_GATE)],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "A comparison base is required" in result.stderr


def test_staged_defect_with_clean_worktree_is_only_provisional(tmp_path: Path) -> None:
    """Never describe working-tree bytes as validation of divergent staged bytes."""
    repository = tmp_path / "checkout"
    baseline = _initialize_repository(repository)
    candidate = repository / "candidate.py"
    candidate.write_text(
        '"""Invalid staged module."""\n\nimport os\n', encoding="utf-8"
    )
    _git(repository, "add", "candidate.py")
    candidate.write_text('"""Clean working module."""\n\nVALUE = 1\n', encoding="utf-8")

    selection = select_worktree_changes(repository, baseline)

    assert selection.mode == "worktree"
    assert run_ruff(selection.files) == 0
    with pytest.raises(QualityGateError, match="clean working tree"):
        select_delivery_changes(repository, baseline, baseline)


def test_index_path_missing_from_worktree_fails_closed(tmp_path: Path) -> None:
    """Reject a selected staged path whose filesystem bytes cannot be checked."""
    repository = tmp_path / "checkout"
    baseline = _initialize_repository(repository)
    candidate = repository / "missing.py"
    candidate.write_text("VALUE = 1\n", encoding="utf-8")
    _git(repository, "add", "missing.py")
    candidate.unlink()

    with pytest.raises(QualityGateError, match="missing from the working tree"):
        select_worktree_changes(repository, baseline)


def test_delivery_selection_requires_exact_commit_and_clean_tree(
    tmp_path: Path,
) -> None:
    """Validate delivery files only when HEAD is the requested clean commit."""
    repository = tmp_path / "checkout"
    baseline = _initialize_repository(repository)
    candidate = repository / "delivery.py"
    candidate.write_text('"""Delivery module."""\n\nVALUE = 1\n', encoding="utf-8")
    _git(repository, "add", "delivery.py")
    _git(repository, "commit", "-m", "test: add delivery file")
    delivery = _git(repository, "rev-parse", "HEAD").stdout.strip()

    selection = select_delivery_changes(repository, baseline, delivery)

    assert selection.mode == "delivery"
    assert selection.target_sha == delivery
    assert _selected_names(selection.files) == ["delivery.py"]

    with pytest.raises(QualityGateError, match="does not match requested delivery"):
        select_delivery_changes(repository, baseline, baseline)

    (repository / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(QualityGateError, match="clean working tree"):
        select_delivery_changes(repository, baseline, delivery)


@pytest.mark.parametrize(
    ("source", "expected_return_code"),
    [
        ('"""Clean module."""\n\nVALUE = 1\n', 0),
        ('"""Lint violation."""\n\nimport os\n', 1),
        ('"""Format violation."""\n\nVALUES = [1,2,3]\n', 1),
    ],
)
def test_focused_gate_has_clean_lint_and_format_controls(
    tmp_path: Path,
    source: str,
    expected_return_code: int,
) -> None:
    """Accept clean code and reject independent lint and format defects."""
    candidate = tmp_path / "candidate.py"
    candidate.write_text(source, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(QUALITY_GATE), "--files", str(candidate)],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == expected_return_code, result.stdout + result.stderr
    assert "Focused check only; this is not delivery validation." in result.stdout
