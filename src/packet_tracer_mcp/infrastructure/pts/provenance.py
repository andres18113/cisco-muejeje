"""Source, hash and recipe identity for Muejeje build inputs.

This module answers exactly one question: *what were these bytes, and which
commit do they come from?* It measures; it never decides whether a build is
allowed. Deciding is `build_state`, validating shape is `manifest`, and naming
which paths matter is `inventory`.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 64 * 1024 * 1024
_GIT_TIMEOUT_S = 10


@dataclass(frozen=True)
class SourceIdentity:
    """What Git could say about the checkout, and nothing more."""

    commit: str
    tree: str
    clean: bool
    tracked: frozenset[str] = field(default=frozenset())

    def as_report(self) -> dict[str, Any]:
        return {"commit": self.commit, "tree": self.tree, "clean": self.clean}


def recipe_id(recipe: dict[str, Any]) -> str:
    """Return the SHA-256 of canonical, non-NaN JSON recipe bytes."""
    encoded = json.dumps(
        recipe, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def artifact_sha256(path: Path) -> str:
    """Measure an existing caller-selected artifact without qualifying it."""
    candidate = Path(path)
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return hash_file(candidate, max_bytes=None)


def hash_file(path: Path, *, max_bytes: int | None) -> str:
    size = path.stat().st_size
    if max_bytes is not None and size > max_bytes:
        raise ValueError(f"file exceeds {max_bytes} byte limit")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=root, text=True, encoding="utf-8",
            errors="replace", capture_output=True, check=False,
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Git source inspection failed: {exc}") from exc
    if completed.returncode:
        raise ValueError(f"Git source inspection failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def working_blob_matches_head(root: Path, logical: str) -> bool:
    """Compare the working bytes against HEAD, ignoring the index.

    `git status` honours `--assume-unchanged`, so a file flagged that way looks
    clean while its bytes differ. Hashing the working blob directly is what
    closes that hole.
    """
    try:
        head = git_output(root, "rev-parse", f"HEAD:{logical}")
        completed = subprocess.run(
            ["git", "hash-object", f"--path={logical}", "--", logical],
            cwd=root, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False, timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Git source inspection failed: {exc}") from exc
    if completed.returncode:
        raise ValueError(f"cannot hash working input: {logical}")
    return completed.stdout.strip() == head


def path_is_ignored(root: Path, logical: str) -> bool:
    """Whether Git ignores `logical`. Raises when Git cannot be asked."""
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", "--", logical], cwd=root,
            capture_output=True, check=False, timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Git ignore inspection failed for {logical}: {exc}") from exc
    return completed.returncode == 0


def inspect_source(root: Path) -> SourceIdentity:
    """Identify the checkout. Raises `ValueError` when Git cannot identify it."""
    git_top = Path(git_output(root, "rev-parse", "--show-toplevel")).resolve()
    if git_top != root:
        raise ValueError(
            "Git source inspection failed: root is not the repository top-level"
        )
    commit = git_output(root, "rev-parse", "HEAD")
    tree = git_output(root, "rev-parse", "HEAD^{tree}")
    tracked = frozenset(git_output(root, "ls-files").splitlines())
    dirty = git_output(
        root, "status", "--porcelain=v1", "--untracked-files=all",
    ).splitlines()
    return SourceIdentity(
        commit=commit, tree=tree, clean=not dirty, tracked=tracked,
    )
