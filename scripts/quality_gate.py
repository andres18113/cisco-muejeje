"""Run the repository's incremental Ruff lint and format gate."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# This module is both the documented `python scripts/quality_gate.py` entry point,
# where only `scripts/` is importable, and `scripts.quality_gate` under pytest,
# where only the repository root is. Import the sibling under whichever name the
# running interpreter can resolve; a process only ever resolves one of them.
try:
    from scripts import mechanical_migration
except ImportError:
    import mechanical_migration

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class QualityGateError(RuntimeError):
    """Report an input or repository state that makes the gate inconclusive."""


@dataclass(frozen=True)
class ClassifiedFile:
    """Pair one selected Python file with its mechanical-migration verdict."""

    path: Path
    relative: str
    verdict: mechanical_migration.Verdict


@dataclass(frozen=True)
class ChangeSelection:
    """Describe the exact Git comparison and Python files selected by the gate."""

    mode: Literal["worktree", "delivery"]
    files: tuple[Path, ...]
    base_ref: str
    base_sha: str
    merge_base_sha: str
    target_sha: str
    classified: tuple[ClassifiedFile, ...] = ()
    authorized: tuple[str, ...] = ()

    @property
    def exempt(self) -> tuple[Path, ...]:
        """Return the files a proven mechanical migration removed from the gate."""
        return tuple(item.path for item in self.classified if item.verdict.is_exempt)

    @property
    def unverifiable(self) -> tuple[Path, ...]:
        """Return the files whose classification could not be established."""
        unverifiable = mechanical_migration.Classification.UNVERIFIABLE
        return tuple(
            item.path
            for item in self.classified
            if item.verdict.classification is unverifiable
        )


def _run_git(repository: Path, *arguments: str) -> str:
    """Return Git output or fail with a diagnostic."""
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


def _run_git_bytes(repository: Path, *arguments: str) -> bytes:
    """Return raw Git output so stored bytes survive the comparison unchanged."""
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise QualityGateError("Git could not be executed.") from error
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise QualityGateError(detail or "Git returned no diagnostic.")
    return result.stdout


def _resolve_commit(repository: Path, reference: str, label: str) -> str:
    """Resolve a Git reference to one commit or fail with its purpose."""
    try:
        resolved = _run_git(
            repository,
            "rev-parse",
            "--verify",
            f"{reference}^{{commit}}",
        ).strip()
    except QualityGateError as error:
        raise QualityGateError(f"Unable to resolve {label} {reference!r}.") from error
    if not resolved:
        raise QualityGateError(f"Unable to resolve {label} {reference!r}.")
    return resolved


def _paths_from_git(repository: Path, *arguments: str) -> set[str]:
    """Return path names from a NUL-delimited Git command."""
    return {path for path in _run_git(repository, *arguments).split("\0") if path}


def _comparison(
    repository: Path,
    base: str,
    target: str,
) -> tuple[str, str, str]:
    """Resolve base, target, and their merge base to exact commit SHAs."""
    base_sha = _resolve_commit(repository, base, "comparison base")
    target_sha = _resolve_commit(repository, target, "comparison target")
    try:
        merge_base_sha = _run_git(
            repository,
            "merge-base",
            base_sha,
            target_sha,
        ).strip()
    except QualityGateError as error:
        raise QualityGateError(
            f"Unable to find a merge base for {base!r} and {target!r}."
        ) from error
    if not merge_base_sha:
        raise QualityGateError(
            f"Unable to find a merge base for {base!r} and {target!r}."
        )
    return base_sha, target_sha, merge_base_sha


def _existing_python_files(repository: Path, names: set[str]) -> tuple[Path, ...]:
    """Resolve selected Python paths and reject unavailable filesystem bytes."""
    selected: list[Path] = []
    for name in names:
        if Path(name).suffix != ".py":
            continue
        candidate = (repository / name).resolve()
        if not candidate.is_relative_to(repository):
            raise QualityGateError(f"Selected path escapes the repository: {name!r}.")
        if not candidate.is_file():
            raise QualityGateError(
                f"Selected Python path {name!r} is missing from the working tree."
            )
        selected.append(candidate)
    return tuple(
        sorted(selected, key=lambda path: path.relative_to(repository).as_posix())
    )


def _classify_selection(
    repository: Path,
    merge_base_sha: str,
    files: Sequence[Path],
    transformations: Sequence[mechanical_migration.MechanicalTransformation],
) -> tuple[ClassifiedFile, ...]:
    """Classify each selected file against the authorized mechanical migrations.

    Classification runs only when a migration is authorized, so the default gate
    performs exactly the work and the selection it performed before.
    """
    if not transformations or not files:
        return ()
    tracked = _paths_from_git(
        repository,
        "ls-tree",
        "-r",
        "--name-only",
        "-z",
        merge_base_sha,
    )
    classified: list[ClassifiedFile] = []
    for path in files:
        relative = path.relative_to(repository).as_posix()
        base_bytes = None
        if relative in tracked:
            base_bytes = _run_git_bytes(
                repository,
                "cat-file",
                "blob",
                f"{merge_base_sha}:{relative}",
            )
        try:
            candidate_bytes = path.read_bytes()
        except OSError as error:
            raise QualityGateError(
                f"Selected Python path {relative!r} could not be read."
            ) from error
        classified.append(
            ClassifiedFile(
                path=path,
                relative=relative,
                verdict=mechanical_migration.classify_bytes_change(
                    base_bytes,
                    candidate_bytes,
                    transformations,
                ),
            )
        )
    return tuple(classified)


def _gated_files(
    files: tuple[Path, ...],
    classified: tuple[ClassifiedFile, ...],
) -> tuple[Path, ...]:
    """Remove only the files a proven mechanical migration exempted."""
    if not classified:
        return files
    exempt = {item.path for item in classified if item.verdict.is_exempt}
    return tuple(path for path in files if path not in exempt)


def select_worktree_changes(
    repository: Path,
    base: str,
    transformations: Sequence[mechanical_migration.MechanicalTransformation] = (),
) -> ChangeSelection:
    """Select current files for provisional worktree validation."""
    repository = repository.resolve()
    base_sha, target_sha, merge_base_sha = _comparison(repository, base, "HEAD")
    names = _paths_from_git(
        repository,
        "diff",
        "--name-only",
        "--diff-filter=ACMRT",
        "-z",
        f"{merge_base_sha}...{target_sha}",
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
    selected = _existing_python_files(repository, names)
    classified = _classify_selection(
        repository,
        merge_base_sha,
        selected,
        transformations,
    )
    return ChangeSelection(
        mode="worktree",
        files=_gated_files(selected, classified),
        base_ref=base,
        base_sha=base_sha,
        merge_base_sha=merge_base_sha,
        target_sha=target_sha,
        classified=classified,
        authorized=tuple(item.identifier for item in transformations),
    )


def select_delivery_changes(
    repository: Path,
    base: str,
    delivery_commit: str,
    transformations: Sequence[mechanical_migration.MechanicalTransformation] = (),
) -> ChangeSelection:
    """Select files only when a clean tree matches an exact delivery commit."""
    repository = repository.resolve()
    requested_sha = _resolve_commit(repository, delivery_commit, "delivery commit")
    head_sha = _resolve_commit(repository, "HEAD", "HEAD")
    if head_sha != requested_sha:
        raise QualityGateError(
            f"HEAD {head_sha} does not match requested delivery {requested_sha}."
        )
    if _run_git(repository, "status", "--porcelain=v1", "--untracked-files=all"):
        raise QualityGateError(
            "Delivery validation requires a clean working tree and index."
        )

    base_sha, target_sha, merge_base_sha = _comparison(
        repository,
        base,
        requested_sha,
    )
    names = _paths_from_git(
        repository,
        "diff",
        "--name-only",
        "--diff-filter=ACMRT",
        "-z",
        f"{merge_base_sha}...{target_sha}",
    )
    selected = _existing_python_files(repository, names)
    classified = _classify_selection(
        repository,
        merge_base_sha,
        selected,
        transformations,
    )
    return ChangeSelection(
        mode="delivery",
        files=_gated_files(selected, classified),
        base_ref=base,
        base_sha=base_sha,
        merge_base_sha=merge_base_sha,
        target_sha=target_sha,
        classified=classified,
        authorized=tuple(item.identifier for item in transformations),
    )


def run_ruff(files: Sequence[Path], repository: Path = REPOSITORY_ROOT) -> int:
    """Run Ruff lint and format checks and return a combined exit status."""
    if not files:
        print("Ruff gate: no selected Python files.", flush=True)
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


def _explicit_files(paths: Sequence[Path]) -> tuple[Path, ...]:
    """Resolve focused input files and reject missing Python paths."""
    selected: list[Path] = []
    for path in paths:
        candidate = path.resolve()
        if candidate.suffix != ".py":
            raise QualityGateError(f"Focused path is not a Python file: {path!s}.")
        if not candidate.is_file():
            raise QualityGateError(f"Focused Python file is missing: {path!s}.")
        selected.append(candidate)
    return tuple(sorted(selected, key=lambda path: path.as_posix()))


def _print_selection(selection: ChangeSelection) -> None:
    """Print auditable comparison identity and validation semantics."""
    if selection.mode == "delivery":
        print(
            f"Delivery validation: clean tree at exact commit {selection.target_sha}.",
            flush=True,
        )
    else:
        print(
            "Provisional worktree validation; staged bytes are not "
            "validated independently.",
            flush=True,
        )
    print(
        f"Comparison base: {selection.base_ref} -> {selection.base_sha}",
        flush=True,
    )
    print(f"Merge base: {selection.merge_base_sha}", flush=True)
    print(f"Selected Python files: {len(selection.files)}", flush=True)
    _print_mechanical_boundary(selection)


def _print_mechanical_boundary(selection: ChangeSelection) -> None:
    """Print every granted exemption so no run can use one silently."""
    if not selection.authorized:
        return
    print(
        f"Authorized mechanical migrations: {', '.join(selection.authorized)}",
        flush=True,
    )
    for item in selection.classified:
        if not item.verdict.is_exempt:
            continue
        print(
            f"  {item.verdict.classification.value} {item.relative} "
            f"({item.verdict.applied_sites} authorized sites)",
            flush=True,
        )
    print(
        f"Files exempted from Ruff by a proven mechanical migration: "
        f"{len(selection.exempt)}",
        flush=True,
    )


def _report_unverifiable(selection: ChangeSelection) -> int:
    """Fail the gate for any file whose classification could not be established."""
    unverifiable = mechanical_migration.Classification.UNVERIFIABLE
    reported = 0
    for item in selection.classified:
        if item.verdict.classification is not unverifiable:
            continue
        reported += 1
        print(
            f"Unverifiable mechanical comparison for {item.relative}: "
            f"{item.verdict.reason}",
            file=sys.stderr,
            flush=True,
        )
    return int(reported > 0)


def _parse_arguments(arguments: Sequence[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        help="Required Git ref or SHA used as the full-gate comparison base.",
    )
    parser.add_argument(
        "--delivery-commit",
        help="Require a clean tree at this exact commit for delivery validation.",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        type=Path,
        help="Focused Python files; never constitutes full delivery validation.",
    )
    parser.add_argument(
        "--mechanical-migration",
        action="append",
        metavar="IDENTIFIER",
        help=(
            "Authorize one registered mechanical transformation for this "
            "comparison; repeatable. Registered: "
            f"{', '.join(mechanical_migration.registered_identifiers())}."
        ),
    )
    return parser.parse_args(arguments)


def _authorized_transformations(
    identifiers: Sequence[str] | None,
) -> tuple[mechanical_migration.MechanicalTransformation, ...]:
    """Resolve requested migrations, rejecting any identifier that is unregistered."""
    if not identifiers:
        return ()
    try:
        return mechanical_migration.resolve_transformations(identifiers)
    except mechanical_migration.MechanicalMigrationError as error:
        raise QualityGateError(str(error)) from error


def main(arguments: Sequence[str] | None = None) -> int:
    """Select files, run Ruff, and return a process exit status."""
    parsed = _parse_arguments(arguments)
    unverifiable_status = 0
    try:
        transformations = _authorized_transformations(parsed.mechanical_migration)
        if parsed.files is not None:
            if parsed.base is not None or parsed.delivery_commit is not None:
                raise QualityGateError(
                    "--files cannot be combined with --base or --delivery-commit."
                )
            if transformations:
                raise QualityGateError(
                    "--mechanical-migration needs a comparison base; a focused "
                    "check cannot prove mechanical equivalence."
                )
            files = _explicit_files(parsed.files)
            print(
                "Focused check only; this is not delivery validation.",
                flush=True,
            )
        else:
            if parsed.base is None:
                raise QualityGateError(
                    "A comparison base is required; pass --base <ref-or-sha>."
                )
            if parsed.delivery_commit is None:
                selection = select_worktree_changes(
                    REPOSITORY_ROOT,
                    parsed.base,
                    transformations,
                )
            else:
                selection = select_delivery_changes(
                    REPOSITORY_ROOT,
                    parsed.base,
                    parsed.delivery_commit,
                    transformations,
                )
            _print_selection(selection)
            unverifiable_status = _report_unverifiable(selection)
            files = selection.files
    except QualityGateError as error:
        print(f"Ruff gate inconclusive: {error}", file=sys.stderr, flush=True)
        return 2

    return max(run_ruff(files), unverifiable_status)


if __name__ == "__main__":
    raise SystemExit(main())
