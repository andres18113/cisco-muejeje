"""Run the repository's incremental Ruff lint and format gate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath
from typing import Literal

# This module runs both as the documented `python scripts/quality_gate.py` script
# and as the `scripts.quality_gate` module. The execution context alone selects how
# the sibling classifier is loaded, and neither form searches the import path for a
# module of that name, so a failure inside the classifier propagates and no other
# module can stand in for it.
if __package__:
    from . import mechanical_migration
else:
    _CLASSIFIER = Path(__file__).resolve().with_name("mechanical_migration.py")
    _SPEC = importlib.util.spec_from_file_location("mechanical_migration", _CLASSIFIER)
    if _SPEC is None or _SPEC.loader is None:
        raise ImportError(f"Cannot load the mechanical classifier at {_CLASSIFIER}.")
    mechanical_migration = importlib.util.module_from_spec(_SPEC)
    sys.modules[_SPEC.name] = mechanical_migration
    try:
        _SPEC.loader.exec_module(mechanical_migration)
    except BaseException:
        del sys.modules[_SPEC.name]
        raise

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_RAW_EVIDENCE_ROOT = PurePosixPath(
    "docs/reference/server-pt/evidence/dhcp-autonomy-02/e1"
)
_RAW_EVIDENCE_MANIFEST_SHA256 = (
    "390772066149b6b0926566227a2bbdc518aac14d62d885e070b4906d302be623"
)
_RAW_EVIDENCE_PYTHON_SHA256 = {
    (_RAW_EVIDENCE_ROOT / "lead/launch_owned_lab.py").as_posix(): (
        "85b09d91b5e96077d05724fe2a9eb82dec92525cc0ba90171a1a654c85e4c2e5"
    ),
    (_RAW_EVIDENCE_ROOT / "lead/run_qualification.py").as_posix(): (
        "265c2e5e905f42c5885cadad38da851ad580577a42267ed9fbdaacdb5a078964"
    ),
}


class QualityGateError(RuntimeError):
    """Report an input or repository state that makes the gate inconclusive."""


def classify_immutable_evidence(
    files: Sequence[Path], repository: Path = REPOSITORY_ROOT
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    """Exempt only exact raw episode scripts under a fully verified archive."""
    root = repository.resolve()
    selected: list[tuple[Path, str]] = []
    for path in files:
        lexical = path.absolute()
        try:
            relative = lexical.relative_to(root).as_posix()
        except ValueError as exc:
            raise QualityGateError(
                f"Selected Python path escapes checkout: {path}."
            ) from exc
        if path.is_symlink() or path.resolve() != lexical:
            raise QualityGateError(
                f"Selected Python symlink or alias is refused: {path}."
            )
        selected.append((path, relative))
    archive_path = root / _RAW_EVIDENCE_ROOT
    if (
        not any(name in _RAW_EVIDENCE_PYTHON_SHA256 for _, name in selected)
        and not archive_path.exists()
    ):
        manifest_name = (_RAW_EVIDENCE_ROOT / "MANIFEST.sha256").as_posix()
        history = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", manifest_name],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        tracked = subprocess.run(
            [
                "git",
                "ls-files",
                "--error-unmatch",
                "--",
                manifest_name,
            ],
            cwd=root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if history.returncode != 0:
            raise QualityGateError("immutable evidence history is unobservable")
        if not history.stdout.strip() and tracked.returncode != 0:
            return tuple(files), ()

    archive = archive_path.resolve()
    if archive != archive_path.absolute() or not archive.is_relative_to(root):
        raise QualityGateError("immutable evidence archive is a symlink or alias")
    manifest = archive / "MANIFEST.sha256"
    try:
        raw = manifest.read_bytes()
        if hashlib.sha256(raw).hexdigest() != _RAW_EVIDENCE_MANIFEST_SHA256:
            raise ValueError("manifest digest mismatch")
        lines = raw.decode("utf-8").splitlines()
        declared: dict[str, str] = {}
        for line in lines:
            if not re.fullmatch(r"[0-9a-f]{64}  .+", line):
                raise ValueError("manifest row malformed")
            digest, name = line.split("  ", 1)
            relative = PurePosixPath(name)
            if (
                name in declared
                or relative.is_absolute()
                or ".." in relative.parts
                or relative.as_posix() != name
            ):
                raise ValueError("manifest path malformed or duplicated")
            candidate = (archive / relative).resolve()
            if not candidate.is_relative_to(archive) or not candidate.is_file():
                raise ValueError("manifest file unavailable or escaped")
            if hashlib.sha256(candidate.read_bytes()).hexdigest() != digest:
                raise ValueError("manifest file digest mismatch")
            declared[name] = digest
        actual = {
            path.relative_to(archive).as_posix()
            for path in archive.rglob("*")
            if path.is_file() and path != manifest
        }
        if actual != set(declared):
            raise ValueError("manifest inventory changed")
        for name, digest in _RAW_EVIDENCE_PYTHON_SHA256.items():
            member = PurePosixPath(name).relative_to(_RAW_EVIDENCE_ROOT).as_posix()
            if declared.get(member) != digest:
                raise ValueError("registered Python evidence differs from manifest")
    except (OSError, UnicodeError, ValueError) as exc:
        raise QualityGateError(f"immutable evidence is unverified: {exc}") from exc
    gated = tuple(
        path for path, name in selected if name not in _RAW_EVIDENCE_PYTHON_SHA256
    )
    exempt = tuple(
        Path(name) for _, name in selected if name in _RAW_EVIDENCE_PYTHON_SHA256
    )
    return gated, exempt


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
    authorizations: tuple[mechanical_migration.MechanicalAuthorization, ...] = ()

    @property
    def active_authorizations(
        self,
    ) -> tuple[mechanical_migration.MechanicalAuthorization, ...]:
        """Return the committed records bound to this comparison's merge base."""
        return tuple(
            record
            for record in self.authorizations
            if record.is_active_for(self.merge_base_sha)
        )

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
        candidate = (repository / name).absolute()
        if candidate.is_symlink() or candidate.resolve() != candidate:
            raise QualityGateError(
                f"Selected Python symlink or alias is refused: {name!r}."
            )
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


def _provisional_line_endings(data: bytes) -> bytes:
    """Normalize line terminators for provisional worktree classification only.

    Working-tree bytes carry the checkout's line-ending conversion. Worktree mode
    removes that difference so a local run stays useful; the result is not
    delivery evidence, which compares stored Git blobs exactly.
    """
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _classify_selection(
    repository: Path,
    merge_base_sha: str,
    files: Sequence[Path],
    transformations: Sequence[mechanical_migration.MechanicalTransformation],
    delivery_sha: str | None,
) -> tuple[ClassifiedFile, ...]:
    """Classify each selected file against the authorized mechanical migrations.

    With `delivery_sha`, both revisions are the exact stored blobs at the merge
    base and at that commit, so no checkout effect participates in the proof.
    Without it, the candidate is the working-tree file and both revisions have
    their line terminators normalized, which makes the verdict provisional.

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
        if delivery_sha is not None:
            candidate_bytes = _run_git_bytes(
                repository,
                "cat-file",
                "blob",
                f"{delivery_sha}:{relative}",
            )
        else:
            try:
                candidate_bytes = _provisional_line_endings(path.read_bytes())
            except OSError as error:
                raise QualityGateError(
                    f"Selected Python path {relative!r} could not be read."
                ) from error
            if base_bytes is not None:
                base_bytes = _provisional_line_endings(base_bytes)
        classified.append(
            ClassifiedFile(
                path=path,
                relative=relative,
                verdict=mechanical_migration.classify_bytes_change(
                    base_bytes,
                    candidate_bytes,
                    transformations,
                    relative,
                ),
            )
        )
    return tuple(classified)


def _authorization_path(name: str) -> str:
    """Return a record path as repository-relative POSIX text, or reject it."""
    candidate = PurePath(name)
    if not name or candidate.anchor or ".." in candidate.parts:
        raise QualityGateError(
            f"Mechanical authorization path {name!r} must be repository-relative."
        )
    return candidate.as_posix()


def _parse_authorization(
    source: str,
    data: bytes,
) -> mechanical_migration.MechanicalAuthorization:
    """Parse one record, reporting any defect as an inconclusive gate."""
    try:
        return mechanical_migration.parse_authorization(source, data)
    except mechanical_migration.MechanicalMigrationError as error:
        raise QualityGateError(str(error)) from error


def _require_committed_blob(
    repository: Path,
    commit: str,
    path: str,
    failure: str,
) -> None:
    """Fail with `failure` unless `path` is a blob, not a tree, at `commit`."""
    try:
        kind = _run_git(repository, "cat-file", "-t", f"{commit}:{path}")
    except QualityGateError as error:
        raise QualityGateError(failure) from error
    if kind.strip() != "blob":
        raise QualityGateError(failure)


def _committed_authorizations(
    repository: Path,
    delivery_sha: str,
    names: Sequence[str],
) -> tuple[mechanical_migration.MechanicalAuthorization, ...]:
    """Read authorization records and their cited briefs from the delivery commit.

    Both the record and the brief it cites must be committed blobs.
    """
    records: list[mechanical_migration.MechanicalAuthorization] = []
    for name in names:
        source = _authorization_path(name)
        _require_committed_blob(
            repository,
            delivery_sha,
            source,
            f"Mechanical authorization {source!r} is not committed at delivery "
            f"commit {delivery_sha}.",
        )
        record = _parse_authorization(
            source,
            _run_git_bytes(repository, "cat-file", "blob", f"{delivery_sha}:{source}"),
        )
        _require_committed_blob(
            repository,
            delivery_sha,
            record.authority,
            f"Mechanical authorization {source!r} cites authority "
            f"{record.authority!r}, which delivery commit {delivery_sha} does not "
            "hold as a file.",
        )
        records.append(record)
    return tuple(records)


def _worktree_authorizations(
    repository: Path,
    names: Sequence[str],
) -> tuple[mechanical_migration.MechanicalAuthorization, ...]:
    """Read authorization records and their cited briefs from the working tree."""
    records: list[mechanical_migration.MechanicalAuthorization] = []
    for name in names:
        source = _authorization_path(name)
        location = (repository / source).resolve()
        if not location.is_relative_to(repository) or not location.is_file():
            raise QualityGateError(
                f"Mechanical authorization {source!r} is missing from the working tree."
            )
        try:
            data = location.read_bytes()
        except OSError as error:
            raise QualityGateError(
                f"Mechanical authorization {source!r} could not be read."
            ) from error
        record = _parse_authorization(source, data)
        authority = (repository / record.authority).resolve()
        if not authority.is_relative_to(repository) or not authority.is_file():
            raise QualityGateError(
                f"Mechanical authorization {source!r} cites authority "
                f"{record.authority!r}, which the working tree lacks."
            )
        records.append(record)
    return tuple(records)


def _active_transformations(
    manual: Sequence[mechanical_migration.MechanicalTransformation],
    records: Sequence[mechanical_migration.MechanicalAuthorization],
    merge_base_sha: str,
) -> tuple[mechanical_migration.MechanicalTransformation, ...]:
    """Combine manual transformations with the records bound to this merge base.

    A record whose base commit is not the merge base contributes nothing.
    """
    identifiers = [item.identifier for item in manual]
    identifiers.extend(
        record.transformation.identifier
        for record in records
        if record.is_active_for(merge_base_sha)
    )
    try:
        return mechanical_migration.resolve_transformations(identifiers)
    except mechanical_migration.MechanicalMigrationError as error:
        raise QualityGateError(str(error)) from error


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
    *,
    authorizations: Sequence[str] = (),
) -> ChangeSelection:
    """Select current files for provisional worktree validation.

    `transformations` are authorized manually for this run. `authorizations` are
    repository-relative record paths read from the working tree; each contributes
    its transformation only while its base commit is the merge base.
    """
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
    records = _worktree_authorizations(repository, authorizations)
    active = _active_transformations(transformations, records, merge_base_sha)
    classified = _classify_selection(
        repository,
        merge_base_sha,
        selected,
        active,
        None,
    )
    return ChangeSelection(
        mode="worktree",
        files=_gated_files(selected, classified),
        base_ref=base,
        base_sha=base_sha,
        merge_base_sha=merge_base_sha,
        target_sha=target_sha,
        classified=classified,
        authorized=tuple(item.identifier for item in active),
        authorizations=records,
    )


def _hidden_index_paths(repository: Path) -> list[str]:
    """Describe every tracked path whose index flags hide it from `git status`.

    `git ls-files -v` tags a skip-worktree entry `S` and lowercases the tag of an
    assume-unchanged entry, so `s` marks a path carrying both flags.
    """
    hidden: list[str] = []
    for entry in _run_git(repository, "ls-files", "-v", "-z").split("\0"):
        if not entry:
            continue
        tag, path = entry[0], entry[2:]
        flags = []
        if tag in "Ss":
            flags.append("skip-worktree")
        if tag.islower():
            flags.append("assume-unchanged")
        if flags:
            hidden.append(f"{path!r} ({', '.join(flags)})")
    return hidden


def select_delivery_changes(
    repository: Path,
    base: str,
    delivery_commit: str,
    *,
    authorizations: Sequence[str] = (),
) -> ChangeSelection:
    """Select files only when a clean tree matches an exact delivery commit.

    Mechanical proofs compare the stored blobs at the merge base and at the
    delivery commit. `authorizations` are record paths read from the delivery
    commit; each contributes its transformation only while its base commit is the
    merge base. They are the only authority delivery accepts, so this function
    takes no transformation from its caller.

    Ruff reads the checkout, so delivery also refuses any tracked path flagged
    skip-worktree or assume-unchanged, whose working bytes `git status` would not
    compare. Raises `QualityGateError` for every refused state.
    """
    repository = repository.resolve()
    requested_sha = _resolve_commit(repository, delivery_commit, "delivery commit")
    head_sha = _resolve_commit(repository, "HEAD", "HEAD")
    if head_sha != requested_sha:
        raise QualityGateError(
            f"HEAD {head_sha} does not match requested delivery {requested_sha}."
        )
    hidden = _hidden_index_paths(repository)
    if hidden:
        raise QualityGateError(
            "Delivery validation refuses index flags that hide working-tree bytes "
            f"from the clean-tree check; clear them on: {'; '.join(hidden)}."
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
    records = _committed_authorizations(repository, target_sha, authorizations)
    active = _active_transformations((), records, merge_base_sha)
    classified = _classify_selection(
        repository,
        merge_base_sha,
        selected,
        active,
        target_sha,
    )
    return ChangeSelection(
        mode="delivery",
        files=_gated_files(selected, classified),
        base_ref=base,
        base_sha=base_sha,
        merge_base_sha=merge_base_sha,
        target_sha=target_sha,
        classified=classified,
        authorized=tuple(item.identifier for item in active),
        authorizations=records,
    )


def run_ruff(files: Sequence[Path], repository: Path = REPOSITORY_ROOT) -> int:
    """Run Ruff lint and format checks and return a combined exit status."""
    if not files:
        print("Ruff gate: no selected Python files.", flush=True)
        return 0

    config = repository / "pyproject.toml"
    # Windows CreateProcess has a command-line limit below the length of this
    # branch's full absolute-path selection. Ruff checks files independently;
    # partition only argv, never the selected set or the failure result.
    max_command_chars = 8_000
    longest_prefix = [
        sys.executable,
        "-m",
        "ruff",
        "format",
        "--check",
        "--config",
        str(config),
    ]
    batches: list[tuple[str, ...]] = []
    pending: list[str] = []
    for path in files:
        name = str(path)
        proposed = [*pending, name]
        if (
            len(subprocess.list2cmdline([*longest_prefix, *proposed]))
            > max_command_chars
        ):
            if not pending:
                raise QualityGateError(f"Ruff path exceeds command limit: {path!s}.")
            batches.append(tuple(pending))
            pending = [name]
            if (
                len(subprocess.list2cmdline([*longest_prefix, name]))
                > max_command_chars
            ):
                raise QualityGateError(f"Ruff path exceeds command limit: {path!s}.")
        else:
            pending = proposed
    if pending:
        batches.append(tuple(pending))
    failed = False
    for phase in (("check",), ("format", "--check")):
        for batch in batches:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    *phase,
                    "--config",
                    str(config),
                    *batch,
                ],
                cwd=repository,
                check=False,
            )
            failed |= result.returncode != 0
    return int(failed)


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


def _print_selection(
    selection: ChangeSelection, immutable_exempt: Sequence[Path] = ()
) -> None:
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
    exempt = len(selection.exempt)
    ruff_gated = len(selection.files) - len(immutable_exempt)
    print(f"Changed Python files: {exempt + len(selection.files)}", flush=True)
    print(f"Mechanical-only exempt: {exempt}", flush=True)
    if immutable_exempt:
        print(f"Immutable evidence exempt: {len(immutable_exempt)}", flush=True)
        for path in immutable_exempt:
            print(f"Immutable evidence: {path.as_posix()}", flush=True)
    print(f"Ruff-gated Python files: {ruff_gated}", flush=True)
    _print_mechanical_boundary(selection)


def _print_mechanical_boundary(selection: ChangeSelection) -> None:
    """Print every authorization and granted exemption so none is used silently."""
    for record in selection.authorizations:
        if record.is_active_for(selection.merge_base_sha):
            state = "ACTIVE"
        else:
            state = (
                f"INACTIVE: merge base is {selection.merge_base_sha}; "
                "no exemption granted"
            )
        print(
            f"Mechanical authorization {record.source}: "
            f"{record.transformation.identifier} bound to base {record.base_commit} "
            f"under {record.authority}: {state}",
            flush=True,
        )
    if not selection.authorized:
        return
    print(
        f"Authorized mechanical migrations: {', '.join(selection.authorized)}",
        flush=True,
    )
    if selection.mode == "delivery":
        print(
            "Mechanical proof: exact Git blobs at merge base "
            f"{selection.merge_base_sha} and delivery commit {selection.target_sha}.",
            flush=True,
        )
    else:
        print(
            "Mechanical proof: provisional, over working-tree bytes with "
            "normalized line endings; not delivery evidence.",
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
            "Authorize one registered mechanical transformation for a provisional "
            "worktree comparison; repeatable; refused with --delivery-commit. "
            f"Registered: {', '.join(mechanical_migration.registered_identifiers())}."
        ),
    )
    parser.add_argument(
        "--mechanical-authorization",
        action="append",
        metavar="PATH",
        help=(
            "Repository-relative committed authorization record; repeatable. It "
            "grants exemptions only while its base commit equals the merge base."
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
        authorizations = parsed.mechanical_authorization or ()
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
            if authorizations:
                raise QualityGateError(
                    "--mechanical-authorization needs a comparison base; a focused "
                    "check has no merge base to bind it to."
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
                    authorizations=authorizations,
                )
            else:
                if transformations:
                    raise QualityGateError(
                        "--mechanical-migration authorizes provisional worktree "
                        "runs only; a delivery exemption needs a committed "
                        "--mechanical-authorization bound to the merge base."
                    )
                selection = select_delivery_changes(
                    REPOSITORY_ROOT,
                    parsed.base,
                    parsed.delivery_commit,
                    authorizations=authorizations,
                )
            files, immutable_exempt = classify_immutable_evidence(
                selection.files, REPOSITORY_ROOT
            )
            _print_selection(selection, immutable_exempt)
            unverifiable_status = _report_unverifiable(selection)
    except QualityGateError as error:
        print(f"Ruff gate inconclusive: {error}", file=sys.stderr, flush=True)
        return 2

    return max(run_ruff(files), unverifiable_status)


if __name__ == "__main__":
    raise SystemExit(main())
