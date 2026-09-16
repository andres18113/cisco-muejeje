"""Run the repository's incremental Ruff lint and format gate."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class QualityGateError(RuntimeError):
    """Report an input or repository state that makes the gate inconclusive."""


def _run_git(repository: Path, *arguments: str) -> str:
    """Return Git output or fail with a sanitized diagnostic."""
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise QualityGateError("Git could not be executed.") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or "Git returned no diagnostic."
        raise QualityGateError(detail)
    return result.stdout


def _paths_from_git(repository: Path, *arguments: str) -> set[str]:
    """Return path names from a NUL-delimited Git command."""
    return {path for path in _run_git(repository, *arguments).split("\0") if path}


def changed_python_files(repository: Path, base: str) -> list[Path]:
    """Return existing Python files changed since base or in the worktree."""
    repository = repository.resolve()
    try:
        merge_base = _run_git(repository, "merge-base", base, "HEAD").strip()
    except QualityGateError as error:
        raise QualityGateError(
            f"Unable to resolve comparison base {base!r}."
        ) from error
    if not merge_base:
        raise QualityGateError(f"Unable to resolve comparison base {base!r}.")

    names = _paths_from_git(
        repository,
        "diff",
        "--name-only",
        "--diff-filter=ACMRT",
        "-z",
        f"{merge_base}...HEAD",
    )
    names.update(
        _paths_from_git(
            repository,
            "diff",
            "--name-only",
            "--diff-filter=ACMRT",
            "-z",
        )
    )
    names.update(
        _paths_from_git(
            repository,
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACMRT",
            "-z",
        )
    )
    names.update(
        _paths_from_git(repository, "ls-files", "--others", "--exclude-standard", "-z")
    )

    selected: list[Path] = []
    for name in names:
        candidate = (repository / name).resolve()
        if (
            candidate.is_relative_to(repository)
            and candidate.suffix == ".py"
            and candidate.is_file()
        ):
            selected.append(candidate)
    return sorted(selected, key=lambda path: path.relative_to(repository).as_posix())


def run_ruff(files: Sequence[Path], repository: Path = REPOSITORY_ROOT) -> int:
    """Run Ruff lint and format checks and return a combined exit status."""
    if not files:
        print("Ruff gate: no changed Python files.")
        return 0

    config = repository / "pyproject.toml"
    common = ["--config", str(config), *(str(path) for path in files)]
    lint = subprocess.run(
        [sys.executable, "-m", "ruff", "check", *common],
        cwd=repository,
        check=False,
    )
    formatting = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", *common],
        cwd=repository,
        check=False,
    )
    return int(lint.returncode != 0 or formatting.returncode != 0)


def _parse_arguments(arguments: Sequence[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--base",
        default="origin/main",
        help="Git ref used as the merge-base comparison (default: origin/main).",
    )
    selection.add_argument(
        "--files",
        nargs="+",
        type=Path,
        help="Explicit Python files, primarily for focused checks and tests.",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    """Select files, run Ruff, and return a process exit status."""
    parsed = _parse_arguments(arguments)
    try:
        if parsed.files is None:
            files = changed_python_files(REPOSITORY_ROOT, parsed.base)
        else:
            files = sorted(
                (path.resolve() for path in parsed.files if path.suffix == ".py"),
                key=lambda path: path.as_posix(),
            )
    except QualityGateError as error:
        print(f"Ruff gate inconclusive: {error}", file=sys.stderr)
        return 2

    print(f"Ruff gate: checking {len(files)} Python file(s).")
    return run_ruff(files)


if __name__ == "__main__":
    raise SystemExit(main())
