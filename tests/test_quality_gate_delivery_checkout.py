"""Delivery validation refuses a checkout whose index hides working-tree bytes.

The mechanical proof reads Git blobs, but Ruff reads the checkout, so delivery
relies on a clean status meaning the checked-out files are the delivery commit.
`skip-worktree` and `assume-unchanged` make `git status` stop comparing a path, so
delivery refuses to run while any tracked path, Python or not, carries either flag.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.quality_gate import (
    QualityGateError,
    main,
    select_delivery_changes,
    select_worktree_changes,
)
from tests.mechanical_migration_fixtures import (
    commit_all,
    git,
    initialize_exact_repository,
)

FLAGS = {
    "skip-worktree": ("--skip-worktree",),
    "assume-unchanged": ("--assume-unchanged",),
    "both": ("--skip-worktree", "--assume-unchanged"),
}


def _delivery(tmp_path: Path) -> tuple[Path, str, str]:
    """Commit a clean delivery holding Python and non-Python tracked files."""
    repository = tmp_path / "checkout"
    baseline = initialize_exact_repository(repository)
    (repository / "docs").mkdir()
    (repository / "docs" / "notes.txt").write_bytes(b"Notes.\n")
    (repository / "docs" / "with space.txt").write_bytes(b"Spaced.\n")
    (repository / "delivered.py").write_bytes(b'"""Delivered module."""\n\nVALUE = 1\n')
    delivery = commit_all(repository, "test: commit a clean delivery")
    return repository, baseline, delivery


def _flag(repository: Path, path: str, flags: tuple[str, ...]) -> None:
    """Set index flags on one tracked path."""
    for flag in flags:
        git(repository, "update-index", flag, path)


@pytest.mark.parametrize("path", ["historical.py", "docs/notes.txt"])
@pytest.mark.parametrize("label", sorted(FLAGS))
def test_delivery_refuses_a_flagged_tracked_path(
    tmp_path: Path,
    label: str,
    path: str,
) -> None:
    """Refuse delivery and name the flagged path, even with unchanged bytes."""
    repository, baseline, delivery = _delivery(tmp_path)
    _flag(repository, path, FLAGS[label])
    assert git(repository, "status", "--porcelain").stdout == ""

    with pytest.raises(QualityGateError) as refusal:
        select_delivery_changes(repository, baseline, delivery)

    message = str(refusal.value)
    assert path in message
    for flag in FLAGS[label]:
        assert flag.removeprefix("--") in message


def test_delivery_refuses_bytes_hidden_behind_a_flag(tmp_path: Path) -> None:
    """Refuse delivery when a flag hides an edit that `git status` cannot see."""
    repository, baseline, delivery = _delivery(tmp_path)
    _flag(repository, "delivered.py", FLAGS["skip-worktree"])
    (repository / "delivered.py").write_bytes(b"import os\n")
    assert git(repository, "status", "--porcelain").stdout == ""

    with pytest.raises(QualityGateError, match=r"delivered\.py"):
        select_delivery_changes(repository, baseline, delivery)


def test_delivery_reports_every_flagged_path(tmp_path: Path) -> None:
    """Name each flagged path, including one whose name contains a space."""
    repository, baseline, delivery = _delivery(tmp_path)
    _flag(repository, "docs/with space.txt", FLAGS["assume-unchanged"])
    _flag(repository, "historical.py", FLAGS["skip-worktree"])

    with pytest.raises(QualityGateError) as refusal:
        select_delivery_changes(repository, baseline, delivery)

    message = str(refusal.value)
    assert "docs/with space.txt" in message
    assert "historical.py" in message


def test_delivery_accepts_the_checkout_once_flags_are_cleared(tmp_path: Path) -> None:
    """Keep the positive control: the same checkout without flags is delivered."""
    repository, baseline, delivery = _delivery(tmp_path)
    _flag(repository, "historical.py", FLAGS["both"])
    git(repository, "update-index", "--no-skip-worktree", "historical.py")
    git(repository, "update-index", "--no-assume-unchanged", "historical.py")

    selection = select_delivery_changes(repository, baseline, delivery)

    assert selection.mode == "delivery"
    assert [path.name for path in selection.files] == ["delivered.py"]


def test_cli_delivery_exits_inconclusive_for_a_flagged_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit 2 and report the flagged path through the command line."""
    repository, baseline, delivery = _delivery(tmp_path)
    _flag(repository, "docs/notes.txt", FLAGS["skip-worktree"])
    monkeypatch.setattr("scripts.quality_gate.REPOSITORY_ROOT", repository)

    status = main(["--base", baseline, "--delivery-commit", delivery])
    error = capsys.readouterr().err

    assert status == 2
    assert "Ruff gate inconclusive" in error
    assert "docs/notes.txt" in error


def test_worktree_mode_does_not_apply_the_delivery_check(tmp_path: Path) -> None:
    """Leave provisional worktree selection unchanged by delivery's index check."""
    repository, baseline, _ = _delivery(tmp_path)
    _flag(repository, "historical.py", FLAGS["skip-worktree"])

    selection = select_worktree_changes(repository, baseline)

    assert selection.mode == "worktree"
    assert [path.name for path in selection.files] == ["delivered.py"]
