"""Committed mechanical authorizations are versioned and bound to one exact base.

An authorization record names a registered transformation, the exact commit it
was authorized against, and the brief that authorizes it. The gate evaluates the
transformation only while the comparison merge base equals that commit. Any other
merge base leaves the record inactive, and an inactive record grants nothing, so
the gate returns to ordinary Ruff behavior. Branch names never participate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.mechanical_migration import (
    MechanicalMigrationError,
    parse_authorization,
    resolve_transformations,
)
from scripts.quality_gate import (
    ChangeSelection,
    QualityGateError,
    main,
    run_ruff,
    select_delivery_changes,
    select_worktree_changes,
)
from tests.mechanical_migration_fixtures import (
    AUTHORIZATION_RECORD,
    CANONICAL,
    CANONICAL_AUTHORITY,
    HISTORICAL_MODULE,
    RENAMED_MODULE,
    authorization_record,
    commit_all,
    git,
    head,
    initialize_exact_repository,
    write_authorization,
)

RECORD = AUTHORIZATION_RECORD
EXAMPLE_BASE = "5330e0dd424bfa746007034ba0672e570cc4ff0f"
REQUIRED_FIELDS = ("schema", "version", "transformation", "base_commit", "authority")
SMUGGLED_EDIT = RENAMED_MODULE + "\n\ndef smuggled():\n    return 1\n"


def _record_bytes(record: dict[str, object]) -> bytes:
    """Serialize an authorization record as committed JSON."""
    return json.dumps(record).encode("utf-8")


def _migration(
    tmp_path: Path,
    *,
    stale: bool,
    smuggle: bool = False,
) -> tuple[Path, str, str]:
    """Commit a namespace migration branch that carries an authorization record.

    The comparison base is a main commit after the file history begins. A current
    record names that commit; a stale record names the earlier commit instead.
    Returns the repository, the comparison base, and the delivery commit.
    """
    repository = tmp_path / "checkout"
    earlier = initialize_exact_repository(repository)
    (repository / "smuggled.py").write_bytes(HISTORICAL_MODULE.encode("utf-8"))
    comparison = commit_all(repository, "test: add a second historical module")
    git(repository, "checkout", "-b", "feature/migration")
    (repository / "historical.py").write_bytes(RENAMED_MODULE.encode("utf-8"))
    if smuggle:
        (repository / "smuggled.py").write_bytes(SMUGGLED_EDIT.encode("utf-8"))
    write_authorization(repository, RECORD, earlier if stale else comparison)
    delivery = commit_all(repository, "test: migrate the namespace")
    return repository, comparison, delivery


def _names(paths: tuple[Path, ...]) -> list[str]:
    """Return sorted file names for stable assertions."""
    return sorted(path.name for path in paths)


def _outcome(selection: ChangeSelection) -> tuple[object, ...]:
    """Summarize every decision a selection makes, for invariance checks."""
    return (
        _names(selection.exempt),
        _names(selection.files),
        selection.authorized,
        tuple(item.source for item in selection.active_authorizations),
    )


def test_well_formed_authorization_names_a_registered_transformation() -> None:
    """Parse a complete record into its registered transformation and exact base."""
    authorization = parse_authorization(
        RECORD,
        _record_bytes(authorization_record(EXAMPLE_BASE)),
    )

    assert authorization.source == RECORD
    assert authorization.transformation.identifier == CANONICAL
    assert authorization.base_commit == EXAMPLE_BASE
    assert authorization.authority == CANONICAL_AUTHORITY
    assert authorization.is_active_for(EXAMPLE_BASE)
    assert not authorization.is_active_for("0" * 40)


@pytest.mark.parametrize(
    ("label", "data"),
    [
        ("empty", b""),
        ("truncated", b"{"),
        ("array", b"[]"),
        ("string", b'"CANONICAL_PYTHON_NAMESPACE"'),
        ("undecodable", b"\xff\xfe{}"),
        (
            "duplicate field",
            _record_bytes(authorization_record(EXAMPLE_BASE))[:-1]
            + b', "transformation": "CANONICAL_PYTHON_NAMESPACE"}',
        ),
    ],
)
def test_malformed_authorization_fails_closed(label: str, data: bytes) -> None:
    """Reject a record that is not one well-formed JSON object."""
    with pytest.raises(MechanicalMigrationError):
        parse_authorization(RECORD, data)


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_missing_required_field_fails_closed(field: str) -> None:
    """Reject a record that omits any required field."""
    record = authorization_record(EXAMPLE_BASE)
    del record[field]

    with pytest.raises(MechanicalMigrationError, match=field):
        parse_authorization(RECORD, _record_bytes(record))


def test_unknown_transformation_fails_closed() -> None:
    """Reject a record naming a transformation that is not registered."""
    record = authorization_record(EXAMPLE_BASE, transformation="UNREGISTERED")

    with pytest.raises(MechanicalMigrationError, match="UNREGISTERED"):
        parse_authorization(RECORD, _record_bytes(record))


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        ("transformation list", {"transformation": [CANONICAL, "ADDED"]}),
        ("extra transformations", {"transformations": ["ADDED"]}),
        ("extra paths", {"paths": ["historical.py"]}),
        ("extra audited sites", {"audited_sites": []}),
    ],
)
def test_authorization_cannot_add_to_the_registry(
    label: str,
    overrides: dict[str, object],
) -> None:
    """Reject any record that tries to extend what the registry defines."""
    record = authorization_record(EXAMPLE_BASE, **overrides)

    with pytest.raises(MechanicalMigrationError):
        parse_authorization(RECORD, _record_bytes(record))


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        ("other schema", {"schema": "other/authorization"}),
        ("future version", {"version": 2}),
        ("boolean version", {"version": True}),
        ("string version", {"version": "1"}),
        ("abbreviated base", {"base_commit": EXAMPLE_BASE[:7]}),
        ("symbolic base", {"base_commit": "main"}),
        ("uppercase base", {"base_commit": EXAMPLE_BASE.upper()}),
        ("other authority", {"authority": "docs/engineering/other.md"}),
    ],
)
def test_invalid_field_value_fails_closed(
    label: str,
    overrides: dict[str, object],
) -> None:
    """Reject a record whose schema, version, base, or authority is not exact."""
    record = authorization_record(EXAMPLE_BASE, **overrides)

    with pytest.raises(MechanicalMigrationError):
        parse_authorization(RECORD, _record_bytes(record))


def test_authorization_at_the_merge_base_exempts_a_proven_file(
    tmp_path: Path,
) -> None:
    """Evaluate the transformation when the record's base is the merge base."""
    repository, comparison, delivery = _migration(tmp_path, stale=False)

    selection = select_delivery_changes(
        repository,
        comparison,
        delivery,
        authorizations=[RECORD],
    )

    assert selection.merge_base_sha == comparison
    assert [item.source for item in selection.active_authorizations] == [RECORD]
    assert selection.authorized == (CANONICAL,)
    assert _names(selection.exempt) == ["historical.py"]
    assert selection.files == ()
    assert run_ruff(selection.files) == 0


def test_exact_authorization_keeps_an_unproven_file_under_ruff(
    tmp_path: Path,
) -> None:
    """Exempt only proven files even while the record is active."""
    repository, comparison, delivery = _migration(tmp_path, stale=False, smuggle=True)

    selection = select_delivery_changes(
        repository,
        comparison,
        delivery,
        authorizations=[RECORD],
    )

    assert _names(selection.exempt) == ["historical.py"]
    assert _names(selection.files) == ["smuggled.py"]
    assert run_ruff(selection.files) == 1


def test_stale_authorization_grants_zero_exemptions(tmp_path: Path) -> None:
    """Leave a record inactive once the merge base is not its authorized base."""
    repository, comparison, delivery = _migration(tmp_path, stale=True)

    selection = select_delivery_changes(
        repository,
        comparison,
        delivery,
        authorizations=[RECORD],
    )

    assert [item.source for item in selection.authorizations] == [RECORD]
    assert selection.active_authorizations == ()
    assert selection.authorized == ()
    assert selection.classified == ()
    assert selection.exempt == ()
    assert _names(selection.files) == ["historical.py"]
    assert run_ruff(selection.files) == 1


def test_stale_authorization_leaves_a_semantic_file_under_full_ruff(
    tmp_path: Path,
) -> None:
    """Keep every changed file, rename or not, under Ruff behind a stale record."""
    repository, comparison, delivery = _migration(tmp_path, stale=True, smuggle=True)

    selection = select_delivery_changes(
        repository,
        comparison,
        delivery,
        authorizations=[RECORD],
    )

    assert selection.exempt == ()
    assert _names(selection.files) == ["historical.py", "smuggled.py"]
    assert run_ruff(selection.files) == 1


@pytest.mark.parametrize("stale", [False, True], ids=["current", "stale"])
def test_branch_name_has_no_effect(tmp_path: Path, stale: bool) -> None:
    """Make the same decision under any branch name or a detached HEAD."""
    repository, comparison, delivery = _migration(tmp_path, stale=stale)

    def outcome() -> tuple[object, ...]:
        assert head(repository) == delivery
        return _outcome(
            select_delivery_changes(
                repository,
                comparison,
                delivery,
                authorizations=[RECORD],
            )
        )

    expected = outcome()
    git(repository, "branch", "-m", "feature/canonical-python-namespace")
    renamed = outcome()
    git(repository, "branch", "-m", "main", "previous-main")
    git(repository, "branch", "-m", "main")
    as_main = outcome()
    git(repository, "checkout", "--detach")
    detached = outcome()

    assert renamed == expected
    assert as_main == expected
    assert detached == expected
    assert bool(expected[0]) is not stale


def test_authorization_must_be_committed_at_the_delivery_commit(
    tmp_path: Path,
) -> None:
    """Refuse a record that exists only as ignored filesystem bytes."""
    repository = tmp_path / "checkout"
    baseline = initialize_exact_repository(repository)
    (repository / ".gitignore").write_bytes(b"authorizations/\n")
    (repository / "historical.py").write_bytes(RENAMED_MODULE.encode("utf-8"))
    write_authorization(repository, RECORD, baseline)
    delivery = commit_all(repository, "test: rename with an ignored record")
    assert (repository / RECORD).is_file()
    assert git(repository, "status", "--porcelain").stdout == ""

    with pytest.raises(QualityGateError, match="not committed"):
        select_delivery_changes(
            repository,
            baseline,
            delivery,
            authorizations=[RECORD],
        )


def test_authorization_cited_brief_must_exist_in_the_delivery_commit(
    tmp_path: Path,
) -> None:
    """Refuse a record whose authorizing brief is absent from the delivered tree."""
    repository = tmp_path / "checkout"
    baseline = initialize_exact_repository(repository)
    (repository / "historical.py").write_bytes(RENAMED_MODULE.encode("utf-8"))
    write_authorization(repository, RECORD, baseline)
    (repository / CANONICAL_AUTHORITY).unlink()
    delivery = commit_all(repository, "test: record without its brief")

    with pytest.raises(QualityGateError, match="authority"):
        select_delivery_changes(
            repository,
            baseline,
            delivery,
            authorizations=[RECORD],
        )


def test_authorization_cited_brief_must_be_a_committed_blob(tmp_path: Path) -> None:
    """Refuse a record whose authorizing brief path is a directory, not a file."""
    repository = tmp_path / "checkout"
    baseline = initialize_exact_repository(repository)
    (repository / "historical.py").write_bytes(RENAMED_MODULE.encode("utf-8"))
    write_authorization(repository, RECORD, baseline)
    brief = repository / CANONICAL_AUTHORITY
    brief.unlink()
    brief.mkdir()
    (brief / "README.md").write_bytes(b"# Not the brief\n")
    delivery = commit_all(repository, "test: record citing a directory")
    kind = git(repository, "cat-file", "-t", f"{delivery}:{CANONICAL_AUTHORITY}")
    assert kind.stdout.strip() == "tree"

    with pytest.raises(QualityGateError, match="authority"):
        select_delivery_changes(
            repository,
            baseline,
            delivery,
            authorizations=[RECORD],
        )


def test_delivery_selection_accepts_no_manual_transformation(tmp_path: Path) -> None:
    """Make a committed base-bound record the only delivery authority, in Python too.

    The migration branch carries a current record, but a direct caller that does
    not pass it cannot substitute a transformation of its own in any form.
    """
    repository, comparison, delivery = _migration(tmp_path, stale=False)
    manual = resolve_transformations([CANONICAL])

    with pytest.raises(TypeError):
        select_delivery_changes(repository, comparison, delivery, manual)
    with pytest.raises(TypeError):
        select_delivery_changes(
            repository,
            comparison,
            delivery,
            transformations=manual,
        )
    unauthorized = select_delivery_changes(repository, comparison, delivery)

    assert unauthorized.authorized == ()
    assert unauthorized.classified == ()
    assert unauthorized.exempt == ()
    assert _names(unauthorized.files) == ["historical.py"]


@pytest.mark.parametrize(
    ("label", "record_bytes"),
    [
        ("malformed", b"{"),
        (
            "missing field",
            _record_bytes(
                {
                    key: value
                    for key, value in authorization_record(EXAMPLE_BASE).items()
                    if key != "base_commit"
                }
            ),
        ),
        (
            "unknown transformation",
            _record_bytes(
                authorization_record(EXAMPLE_BASE, transformation="UNREGISTERED")
            ),
        ),
    ],
)
def test_invalid_committed_authorization_fails_the_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    label: str,
    record_bytes: bytes,
) -> None:
    """Exit inconclusive instead of ignoring a record that cannot be trusted."""
    repository = tmp_path / "checkout"
    baseline = initialize_exact_repository(repository)
    (repository / "historical.py").write_bytes(RENAMED_MODULE.encode("utf-8"))
    write_authorization(repository, RECORD, baseline)
    (repository / RECORD).write_bytes(record_bytes)
    delivery = commit_all(repository, "test: commit an invalid record")
    monkeypatch.setattr("scripts.quality_gate.REPOSITORY_ROOT", repository)

    status = main(
        [
            "--base",
            baseline,
            "--delivery-commit",
            delivery,
            "--mechanical-authorization",
            RECORD,
        ]
    )

    assert status == 2, label
    assert "Ruff gate inconclusive" in capsys.readouterr().err


@pytest.mark.parametrize("record", ["../outside.json", "/absolute/record.json"])
def test_authorization_path_must_be_repository_relative(
    tmp_path: Path,
    record: str,
) -> None:
    """Refuse a record path that could name bytes outside the repository."""
    repository = tmp_path / "checkout"
    baseline = initialize_exact_repository(repository)

    with pytest.raises(QualityGateError, match="repository-relative"):
        select_delivery_changes(
            repository,
            baseline,
            baseline,
            authorizations=[record],
        )


def test_gate_prints_active_and_inactive_authorizations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Show why a delivery run is or is not authorized, and what it exempted."""
    repository, comparison, delivery = _migration(tmp_path, stale=False)
    monkeypatch.setattr("scripts.quality_gate.REPOSITORY_ROOT", repository)
    arguments = [
        "--base",
        comparison,
        "--delivery-commit",
        delivery,
        "--mechanical-authorization",
        RECORD,
    ]

    active_status = main(arguments)
    active_output = capsys.readouterr().out
    stale_base = git(repository, "rev-list", "--max-parents=0", "HEAD").stdout.strip()
    (repository / RECORD).write_bytes(_record_bytes(authorization_record(stale_base)))
    arguments[3] = commit_all(repository, "test: bind the record to an old base")
    stale_status = main(arguments)
    stale_output = capsys.readouterr().out

    assert active_status == 0
    assert f"Mechanical authorization {RECORD}" in active_output
    assert ": ACTIVE" in active_output
    assert "INACTIVE" not in active_output
    assert "exact Git blobs" in active_output
    assert "MECHANICAL_ONLY historical.py" in active_output
    assert stale_status == 1
    assert "INACTIVE" in stale_output
    assert stale_base in stale_output
    assert "MECHANICAL_ONLY" not in stale_output


def test_cli_refuses_a_manual_migration_in_delivery_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Require a committed base-bound record for any delivery exemption."""
    repository = tmp_path / "checkout"
    baseline = initialize_exact_repository(repository)
    (repository / "historical.py").write_bytes(RENAMED_MODULE.encode("utf-8"))
    delivery = commit_all(repository, "test: rename the namespace")
    monkeypatch.setattr("scripts.quality_gate.REPOSITORY_ROOT", repository)

    status = main(
        [
            "--base",
            baseline,
            "--delivery-commit",
            delivery,
            "--mechanical-migration",
            CANONICAL,
        ]
    )

    assert status == 2
    assert "--mechanical-authorization" in capsys.readouterr().err


def test_cli_refuses_an_authorization_for_a_focused_check(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Refuse a record without a comparison base that could bind it."""
    status = main(
        [
            "--files",
            str(Path(__file__)),
            "--mechanical-authorization",
            RECORD,
        ]
    )

    assert status == 2
    assert "--mechanical-authorization" in capsys.readouterr().err


def test_worktree_mode_applies_the_same_base_binding(tmp_path: Path) -> None:
    """Bind provisional filesystem records to the merge base as well."""
    repository = tmp_path / "checkout"
    baseline = initialize_exact_repository(repository)
    (repository / "historical.py").write_bytes(RENAMED_MODULE.encode("utf-8"))
    write_authorization(repository, RECORD, baseline)

    current = select_worktree_changes(repository, baseline, authorizations=[RECORD])
    write_authorization(repository, RECORD, "0" * 40)
    stale = select_worktree_changes(repository, baseline, authorizations=[RECORD])

    assert current.mode == "worktree"
    assert _names(current.exempt) == ["historical.py"]
    assert stale.exempt == ()
    assert _names(stale.files) == ["historical.py"]
