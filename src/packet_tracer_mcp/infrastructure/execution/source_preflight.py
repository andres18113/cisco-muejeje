"""Coherent Git source observations for governed live runners."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class GitOutput(Protocol):
    def __call__(self, root: Path, *arguments: str) -> str: ...


@dataclass(frozen=True)
class GitSourceObservation:
    """One source snapshot, including failures that make it inadmissible."""

    branch: str = ""
    upstream: str = ""
    head: str = ""
    upstream_head: str = ""
    source_tree: str = ""
    dirty: bool | None = None
    error: str = ""
    dirty_error: str = ""
    upstream_head_error: str = ""
    source_tree_error: str = ""

    @property
    def complete(self) -> bool:
        return bool(
            self.branch
            and self.upstream
            and self.head
            and self.upstream_head
            and self.source_tree
            and self.dirty is not None
            and not self.error
            and not self.dirty_error
            and not self.upstream_head_error
            and not self.source_tree_error
        )

    def require_complete(self) -> GitSourceObservation:
        problems = tuple(
            problem
            for problem in (
                self.error,
                self.dirty_error,
                self.upstream_head_error,
                self.source_tree_error,
            )
            if problem
        )
        if not self.complete:
            detail = "; ".join(problems) or "repository evidence is incomplete"
            raise RuntimeError("Git source inspection failed: " + detail)
        return self

    def live_state(self) -> dict[str, str | bool]:
        self.require_complete()
        return {
            "source_branch": self.branch,
            "source_head": self.head,
            "source_tree": self.source_tree,
            "upstream": self.upstream,
            "upstream_head": self.upstream_head,
            "worktree_clean": self.dirty is False,
        }


class GitSourceReader:
    """Capture tree from an immutable SHA, then revalidate both references."""

    def __init__(self, *, git_output: GitOutput | None = None) -> None:
        self._git_output = git_output or _git_output

    def read(self, governed_root: Path) -> GitSourceObservation:
        branch = ""
        upstream = ""
        head = ""
        error = ""
        try:
            branch = self._git_output(governed_root, "branch", "--show-current")
            upstream = self._git_output(
                governed_root,
                "rev-parse",
                "--abbrev-ref",
                "@{upstream}",
            )
            head = self._git_output(governed_root, "rev-parse", "HEAD")
        except (OSError, subprocess.CalledProcessError) as exc:
            branch = ""
            upstream = ""
            head = ""
            error = str(exc)

        dirty: bool | None
        dirty_error = ""
        try:
            dirty = bool(
                self._git_output(governed_root, "status", "--porcelain")
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            dirty = None
            dirty_error = str(exc)

        upstream_head = ""
        upstream_head_error = ""
        try:
            upstream_head = self._git_output(
                governed_root,
                "rev-parse",
                "@{upstream}",
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            upstream_head_error = str(exc)

        source_tree = ""
        source_tree_error = ""
        if head:
            try:
                source_tree = self._git_output(
                    governed_root,
                    "rev-parse",
                    f"{head}^{{tree}}",
                )
            except (OSError, subprocess.CalledProcessError) as exc:
                source_tree_error = str(exc)
        else:
            source_tree_error = (
                "Repository HEAD was unavailable for tree capture."
            )

        if head:
            try:
                final_head = self._git_output(
                    governed_root,
                    "rev-parse",
                    "HEAD",
                )
                if final_head != head:
                    source_tree_error = (
                        "HEAD changed during repository inspection: "
                        f"captured {head!r}; observed {final_head!r}."
                    )
            except (OSError, subprocess.CalledProcessError) as exc:
                source_tree_error = (
                    "Repository HEAD could not be revalidated: " + str(exc)
                )

        if upstream_head:
            try:
                final_upstream_head = self._git_output(
                    governed_root,
                    "rev-parse",
                    "@{upstream}",
                )
                if final_upstream_head != upstream_head:
                    upstream_head_error = (
                        "upstream changed during repository inspection: "
                        f"captured {upstream_head!r}; "
                        f"observed {final_upstream_head!r}."
                    )
            except (OSError, subprocess.CalledProcessError) as exc:
                upstream_head_error = (
                    "Repository upstream could not be revalidated: "
                    + str(exc)
                )

        return GitSourceObservation(
            branch=branch,
            upstream=upstream,
            head=head,
            upstream_head=upstream_head,
            source_tree=source_tree,
            dirty=dirty,
            error=error,
            dirty_error=dirty_error,
            upstream_head_error=upstream_head_error,
            source_tree_error=source_tree_error,
        )


def _git_output(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()
