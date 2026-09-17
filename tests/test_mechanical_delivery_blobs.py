"""Delivery validation proves mechanical equivalence over exact stored Git blobs.

The delivery proof reads the base blob at the merge base and the candidate blob at
the exact delivery commit. Checkout conversion and working-tree bytes take no part
in it, so no representation of a checkout can grant or withhold an exemption, and
no whitespace or line-ending change stored in Git can obtain one. Worktree mode
stays provisional: it reads filesystem bytes and normalizes line endings.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.mechanical_migration import Classification, resolve_transformations
from scripts.quality_gate import (
    ChangeSelection,
    select_delivery_changes,
    select_worktree_changes,
)
from tests.mechanical_migration_fixtures import (
    AUTHORIZATION_RECORD,
    CANONICAL,
    RENAMED_MODULE,
    commit_all,
    git,
    head,
    initialize_exact_repository,
    stored_blob,
    write_authorization,
)

AUTHORIZED = resolve_transformations([CANONICAL])
FUNCTIONAL_EDIT = RENAMED_MODULE.replace("os.name", "os.sep")


def _verdict(selection: ChangeSelection, relative: str) -> Classification:
    """Return the classification the selection recorded for one file."""
    verdicts = {
        item.relative: item.verdict.classification for item in selection.classified
    }
    return verdicts[relative]


def _commit_candidate(repository: Path, baseline: str, candidate: bytes) -> str:
    """Commit a candidate module with a record authorizing the migration at base."""
    (repository / "historical.py").write_bytes(candidate)
    write_authorization(repository, AUTHORIZATION_RECORD, baseline)
    return commit_all(repository, "test: commit an authorized candidate")


def _deliver(repository: Path, baseline: str) -> ChangeSelection:
    """Select the current clean commit for delivery under its committed record."""
    return select_delivery_changes(
        repository,
        baseline,
        head(repository),
        authorizations=[AUTHORIZATION_RECORD],
    )


def _checkout_through_filter(repository: Path, stored: str, checked_out: str) -> None:
    """Check out `historical.py` through a filter that swaps two tokens.

    Git applies the smudge command when writing the file and the clean command
    when reading it back, so the working bytes differ from the blob while
    `git status` reports a clean tree and no index flag is set.
    """
    git(repository, "config", "filter.swap.smudge", f"sed -e s/{stored}/{checked_out}/")
    git(repository, "config", "filter.swap.clean", f"sed -e s/{checked_out}/{stored}/")
    (repository / ".git" / "info").mkdir(exist_ok=True)
    (repository / ".git" / "info" / "attributes").write_bytes(
        b"historical.py filter=swap\n"
    )
    (repository / "historical.py").unlink()
    git(repository, "checkout", "--", "historical.py")
    assert git(repository, "status", "--porcelain").stdout == ""
    assert git(repository, "ls-files", "-v", "historical.py").stdout.startswith("H ")


def test_stored_lf_rename_is_mechanical_in_delivery(tmp_path: Path) -> None:
    """Accept an LF base and an LF renamed candidate as they are stored."""
    repository = tmp_path / "checkout"
    baseline = initialize_exact_repository(repository)
    delivery = _commit_candidate(repository, baseline, RENAMED_MODULE.encode("utf-8"))
    assert b"\r" not in stored_blob(repository, delivery, "historical.py")

    selection = _deliver(repository, baseline)

    assert _verdict(selection, "historical.py") is Classification.MECHANICAL_ONLY
    assert selection.files == ()


@pytest.mark.parametrize(
    ("label", "candidate"),
    [
        ("CRLF line endings", RENAMED_MODULE.replace("\n", "\r\n").encode("utf-8")),
        ("CR line endings", RENAMED_MODULE.replace("\n", "\r").encode("utf-8")),
        (
            "trailing whitespace",
            RENAMED_MODULE.replace("import os\n", "import os \n").encode("utf-8"),
        ),
        ("missing final newline", RENAMED_MODULE.rstrip("\n").encode("utf-8")),
    ],
    ids=["crlf", "cr", "trailing-whitespace", "missing-final-newline"],
)
def test_committed_whitespace_change_beside_rename_is_authored(
    tmp_path: Path,
    label: str,
    candidate: bytes,
) -> None:
    """Refuse the exemption for any stored whitespace or line-ending delta."""
    repository = tmp_path / "checkout"
    baseline = initialize_exact_repository(repository)
    delivery = _commit_candidate(repository, baseline, candidate)
    assert stored_blob(repository, delivery, "historical.py") == candidate

    selection = _deliver(repository, baseline)

    assert (
        _verdict(selection, "historical.py")
        is Classification.SEMANTIC_OR_AUTHORED_CHANGE
    ), label
    assert [path.name for path in selection.files] == ["historical.py"]


def test_windows_checkout_does_not_change_the_delivery_decision(
    tmp_path: Path,
) -> None:
    """Decide delivery identically when LF blobs are checked out as CRLF files."""
    repository = tmp_path / "checkout"
    baseline = initialize_exact_repository(repository)
    _commit_candidate(repository, baseline, RENAMED_MODULE.encode("utf-8"))
    lf_decision = _verdict(_deliver(repository, baseline), "historical.py")

    git(repository, "config", "core.autocrlf", "true")
    (repository / "historical.py").unlink()
    git(repository, "checkout", "--", "historical.py")
    assert b"\r\n" in (repository / "historical.py").read_bytes()
    assert git(repository, "status", "--porcelain").stdout == ""

    crlf_decision = _verdict(_deliver(repository, baseline), "historical.py")

    assert lf_decision is Classification.MECHANICAL_ONLY
    assert crlf_decision is lf_decision


def test_filesystem_rename_cannot_exempt_an_authored_commit(tmp_path: Path) -> None:
    """Decide delivery from the committed blob, never from divergent disk bytes."""
    repository = tmp_path / "checkout"
    baseline = initialize_exact_repository(repository)
    _commit_candidate(repository, baseline, FUNCTIONAL_EDIT.encode("utf-8"))
    _checkout_through_filter(repository, stored="os.sep", checked_out="os.name")
    assert (repository / "historical.py").read_bytes() == RENAMED_MODULE.encode()

    selection = _deliver(repository, baseline)

    assert (
        _verdict(selection, "historical.py")
        is Classification.SEMANTIC_OR_AUTHORED_CHANGE
    )
    assert [path.name for path in selection.files] == ["historical.py"]


def test_filesystem_edit_cannot_revoke_a_proven_commit(tmp_path: Path) -> None:
    """Keep the committed proof when disk bytes diverge in the other direction."""
    repository = tmp_path / "checkout"
    baseline = initialize_exact_repository(repository)
    _commit_candidate(repository, baseline, RENAMED_MODULE.encode("utf-8"))
    _checkout_through_filter(repository, stored="os.name", checked_out="os.sep")
    assert (repository / "historical.py").read_bytes() == FUNCTIONAL_EDIT.encode()

    selection = _deliver(repository, baseline)

    assert _verdict(selection, "historical.py") is Classification.MECHANICAL_ONLY


def test_worktree_mode_normalizes_line_endings_provisionally(tmp_path: Path) -> None:
    """Classify a CRLF working file provisionally, outside delivery evidence."""
    repository = tmp_path / "checkout"
    baseline = initialize_exact_repository(repository)
    assert b"\r" not in stored_blob(repository, baseline, "historical.py")
    (repository / "historical.py").write_bytes(
        RENAMED_MODULE.replace("\n", "\r\n").encode("utf-8")
    )

    selection = select_worktree_changes(repository, baseline, AUTHORIZED)

    assert selection.mode == "worktree"
    assert _verdict(selection, "historical.py") is Classification.MECHANICAL_ONLY


def test_worktree_mode_still_refuses_a_functional_edit(tmp_path: Path) -> None:
    """Keep provisional normalization limited to line terminators."""
    repository = tmp_path / "checkout"
    baseline = initialize_exact_repository(repository)
    (repository / "historical.py").write_bytes(
        FUNCTIONAL_EDIT.replace("\n", "\r\n").encode("utf-8")
    )

    selection = select_worktree_changes(repository, baseline, AUTHORIZED)

    assert FUNCTIONAL_EDIT != RENAMED_MODULE
    assert (
        _verdict(selection, "historical.py")
        is Classification.SEMANTIC_OR_AUTHORED_CHANGE
    )
