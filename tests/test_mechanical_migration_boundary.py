"""Behavioral tests for the authorized mechanical migration quality boundary."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.mechanical_migration import (
    Classification,
    MechanicalMigrationError,
    Verdict,
    classify_bytes_change,
    classify_source_change,
    resolve_transformations,
)
from scripts.quality_gate import (
    QualityGateError,
    main,
    run_ruff,
    select_delivery_changes,
    select_worktree_changes,
)
from tests.mechanical_migration_fixtures import (
    AUTHORIZATION_RECORD,
    CANONICAL,
    HISTORICAL_MODULE,
    LEGACY,
    QUALITY_GATE,
    RENAMED_MODULE,
    REPOSITORY_ROOT,
    TARGET,
    write_authorization,
)
from tests.mechanical_migration_fixtures import (
    git as _git,
)
from tests.mechanical_migration_fixtures import (
    initialize_repository as _initialize_repository,
)

AUTHORIZED = resolve_transformations([CANONICAL])


def _classify(base: str, candidate: str) -> Verdict:
    """Classify a source-level delta with the canonical namespace authorized."""
    return classify_source_change(base, candidate, AUTHORIZED)


def _relative_names(paths: tuple[Path, ...], repository: Path) -> list[str]:
    """Return repository-relative POSIX names for stable assertions."""
    return sorted(path.relative_to(repository.resolve()).as_posix() for path in paths)


def test_from_import_rename_alone_is_mechanical_only() -> None:
    """Accept the from-import form of the authorized namespace rename."""
    base = "from src.packet_tracer_mcp.foo import Bar\n"
    candidate = "from packet_tracer_mcp.foo import Bar\n"

    verdict = _classify(base, candidate)

    assert verdict.classification is Classification.MECHANICAL_ONLY
    assert verdict.applied_sites == 1
    assert verdict.transformations == (CANONICAL,)
    assert verdict.is_exempt


def test_plain_import_rename_alone_is_mechanical_only() -> None:
    """Accept the plain import form of the authorized namespace rename."""
    verdict = _classify(
        "import src.packet_tracer_mcp.foo\n",
        "import packet_tracer_mcp.foo\n",
    )

    assert verdict.classification is Classification.MECHANICAL_ONLY


def test_bare_and_aliased_imports_are_mechanical_only() -> None:
    """Accept the bare package import and the aliased import form."""
    base = "import src.packet_tracer_mcp\nimport src.packet_tracer_mcp.foo as f\n"
    candidate = "import packet_tracer_mcp\nimport packet_tracer_mcp.foo as f\n"

    verdict = _classify(base, candidate)

    assert verdict.classification is Classification.MECHANICAL_ONLY
    assert verdict.applied_sites == 2


def test_many_authorized_imports_in_one_file_are_mechanical_only() -> None:
    """Accept a file whose every authorized reference is renamed together."""
    base = (
        '"""Module."""\n\n'
        "import src.packet_tracer_mcp.a\n"
        "from src.packet_tracer_mcp.b import Second\n"
        "from src.packet_tracer_mcp.c import Third\n"
    )

    verdict = _classify(base, base.replace(LEGACY, TARGET))

    assert verdict.classification is Classification.MECHANICAL_ONLY
    assert verdict.applied_sites == 3


@pytest.mark.parametrize(
    ("label", "base"),
    [
        (
            "dynamic import calls",
            '"""Module."""\n\n'
            "import importlib\n\n"
            'first = importlib.import_module("src.packet_tracer_mcp.foo")\n'
            'second = __import__("src.packet_tracer_mcp.bar")\n',
        ),
        (
            "patch and monkeypatch targets",
            '"""Module."""\n\n'
            "from unittest import mock\n\n\n"
            "def run(monkeypatch):\n"
            '    with mock.patch("src.packet_tracer_mcp.foo.Bar"):\n'
            '        monkeypatch.setattr("src.packet_tracer_mcp.foo.value", 1)\n',
        ),
        (
            "patch keyword target",
            '"""Module."""\n\n'
            "from unittest.mock import patch\n\n"
            'context = patch(target="src.packet_tracer_mcp.foo.Bar")\n',
        ),
    ],
    ids=["dynamic-imports", "patch-and-monkeypatch", "patch-keyword"],
)
def test_unaudited_dynamic_targets_are_authored(label: str, base: str) -> None:
    """Refuse dynamic string rewrites that no audited site registers.

    A recognizable callee name is not evidence of what the name is bound to, so
    these constructs are proven only at audited sites; see
    `test_mechanical_dynamic_site_authority.py`.
    """
    verdict = _classify(base, base.replace(LEGACY, TARGET))

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE, label
    assert not verdict.is_exempt


def test_untouched_comment_and_docstring_do_not_block_classification() -> None:
    """Accept a rename that leaves unauthorized namespace text exactly as it was."""
    base = (
        '"""Docstring naming src.packet_tracer_mcp on purpose."""\n\n'
        "# Historical note about src.packet_tracer_mcp.\n"
        "from src.packet_tracer_mcp.foo import Bar\n"
        'INERT = "src.packet_tracer_mcp"\n'
    )
    candidate = base.replace(f"from {LEGACY}.foo", f"from {TARGET}.foo")

    verdict = _classify(base, candidate)

    assert verdict.classification is Classification.MECHANICAL_ONLY
    assert verdict.applied_sites == 1


@pytest.mark.parametrize(
    ("label", "candidate"),
    [
        (
            "added statement",
            "from packet_tracer_mcp.foo import Bar\n\nx = 123\n",
        ),
        (
            "additional import",
            "import os\n\nfrom packet_tracer_mcp.foo import Bar\n",
        ),
        (
            "unnecessary requoting",
            "from packet_tracer_mcp.foo import Bar\n\nVALUE = 'text'\n",
        ),
        (
            "unnecessary blank line",
            'from packet_tracer_mcp.foo import Bar\n\n\nVALUE = "text"\n',
        ),
        (
            "removed trailing statement",
            "from packet_tracer_mcp.foo import Bar\n",
        ),
    ],
)
def test_any_additional_delta_is_authored(label: str, candidate: str) -> None:
    """Refuse the exemption whenever the delta exceeds the authorized rename."""
    base = 'from src.packet_tracer_mcp.foo import Bar\n\nVALUE = "text"\n'

    verdict = _classify(base, candidate)

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE, label
    assert not verdict.is_exempt


def test_functional_change_beside_a_rename_is_authored() -> None:
    """Refuse the exemption when behavior changes alongside the rename."""
    base = (
        "from src.packet_tracer_mcp.foo import Bar\n\n\n"
        "def run(authorized):\n"
        "    if authorized:\n"
        "        return Bar()\n"
        "    return None\n"
    )
    candidate = base.replace(LEGACY, TARGET).replace(
        "if authorized:", "if not authorized:"
    )

    verdict = _classify(base, candidate)

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE


def test_import_reordering_beside_a_rename_is_authored() -> None:
    """Refuse the exemption for an import reorder the transformation never makes."""
    base = "import os\n\nfrom src.packet_tracer_mcp.foo import Bar\n"
    candidate = "from packet_tracer_mcp.foo import Bar\n\nimport os\n"

    verdict = _classify(base, candidate)

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE


def test_rewritten_comment_is_authored() -> None:
    """Refuse the exemption when a comment mentioning the namespace is rewritten."""
    base = (
        "# Historical note about src.packet_tracer_mcp.\n"
        "from src.packet_tracer_mcp.foo import Bar\n"
    )

    verdict = _classify(base, base.replace(LEGACY, TARGET))

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE


def test_rewritten_docstring_is_authored() -> None:
    """Refuse the exemption when a docstring mentioning the namespace is rewritten."""
    base = (
        '"""Docstring naming src.packet_tracer_mcp."""\n\n'
        "from src.packet_tracer_mcp.foo import Bar\n"
    )

    verdict = _classify(base, base.replace(LEGACY, TARGET))

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE


def test_rewritten_inert_string_is_authored() -> None:
    """Refuse the exemption when an unauthorized string literal is rewritten."""
    base = (
        'from src.packet_tracer_mcp.foo import Bar\n\nINERT = "src.packet_tracer_mcp"\n'
    )

    verdict = _classify(base, base.replace(LEGACY, TARGET))

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE


def test_rewritten_unregistered_call_argument_is_authored() -> None:
    """Refuse the exemption for a string argument of an unregistered call."""
    base = (
        "from src.packet_tracer_mcp.foo import Bar\n\n"
        'record("src.packet_tracer_mcp.foo")\n'
    )

    verdict = _classify(base, base.replace(LEGACY, TARGET))

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE


def test_rewritten_format_string_is_authored() -> None:
    """Refuse the exemption for an f-string the transformation never rewrites."""
    base = (
        "from src.packet_tracer_mcp.foo import Bar\n\n"
        'LABEL = f"src.packet_tracer_mcp.{Bar.__name__}"\n'
    )

    verdict = _classify(base, base.replace(LEGACY, TARGET))

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE


def test_partially_authorized_delta_is_authored() -> None:
    """Refuse the exemption when only part of the delta is authorized."""
    base = (
        "from src.packet_tracer_mcp.foo import Bar\n"
        "# Historical note about src.packet_tracer_mcp.\n"
    )
    candidate = (
        "from packet_tracer_mcp.foo import Bar\n"
        "# Historical note about packet_tracer_mcp.\n"
    )

    verdict = _classify(base, candidate)

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE


def test_similar_prefix_is_not_an_authorized_reference() -> None:
    """Refuse the exemption for a package whose name merely starts alike."""
    base = "import src.packet_tracer_mcp_legacy\n"
    candidate = "import packet_tracer_mcp_legacy\n"

    verdict = _classify(base, candidate)

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE


def test_unparseable_candidate_is_authored() -> None:
    """Refuse the exemption when the candidate revision is not parseable Python."""
    verdict = _classify(
        "from src.packet_tracer_mcp.foo import Bar\n",
        "from packet_tracer_mcp.foo import (\n",
    )

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE


def test_unparseable_base_is_authored() -> None:
    """Refuse the exemption when the base revision cannot be analyzed."""
    verdict = _classify(
        "from src.packet_tracer_mcp.foo import (\n",
        "from packet_tracer_mcp.foo import Bar\n",
    )

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE


def test_absent_base_is_a_new_file() -> None:
    """Classify a file with no base revision as new, never as mechanical."""
    verdict = classify_source_change(None, RENAMED_MODULE, AUTHORIZED)

    assert verdict.classification is Classification.NEW_FILE
    assert not verdict.is_exempt


def test_identical_revisions_are_unchanged() -> None:
    """Classify an identical pair as unchanged rather than as a rename."""
    verdict = _classify(HISTORICAL_MODULE, HISTORICAL_MODULE)

    assert verdict.classification is Classification.UNCHANGED
    assert verdict.applied_sites == 0


def test_line_ending_change_beside_a_rename_is_authored() -> None:
    """Compare revisions exactly: the classifier never normalizes line endings.

    Checkout conversion is handled by the gate, which proves delivery over stored
    Git blobs; see `test_mechanical_delivery_blobs.py`.
    """
    base = HISTORICAL_MODULE.encode("utf-8")
    candidate = RENAMED_MODULE.replace("\n", "\r\n").encode("utf-8")

    verdict = classify_bytes_change(base, candidate, AUTHORIZED)

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE


def test_undecodable_base_is_unverifiable() -> None:
    """Report bytes that cannot be analyzed as unverifiable, never as mechanical."""
    verdict = classify_bytes_change(
        b"\xff\xfe\x00invalid",
        RENAMED_MODULE.encode("utf-8"),
        AUTHORIZED,
    )

    assert verdict.classification is Classification.UNVERIFIABLE
    assert not verdict.is_exempt


def test_no_authorized_transformation_never_exempts() -> None:
    """Keep the default gate unchanged when no transformation is authorized."""
    verdict = classify_source_change(HISTORICAL_MODULE, RENAMED_MODULE, ())

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE


def test_unknown_transformation_identifier_fails_closed() -> None:
    """Reject an unregistered transformation instead of authorizing nothing."""
    with pytest.raises(MechanicalMigrationError, match="UNREGISTERED"):
        resolve_transformations(["UNREGISTERED"])


def test_hidden_functional_change_cannot_ride_a_rename() -> None:
    """Prove a functional edit hidden in a renamed file loses the exemption."""
    base = (
        '"""Bridge."""\n\n'
        "from src.packet_tracer_mcp.foo import Bar\n\n\n"
        "def authorize(token, expected):\n"
        "    return token == expected\n"
    )
    candidate = base.replace(LEGACY, TARGET).replace(
        "return token == expected",
        "return True",
    )

    verdict = _classify(base, candidate)

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE
    assert not verdict.is_exempt


def test_inline_opt_in_marker_carries_no_authority() -> None:
    """Prove an in-file marker cannot declare a delta mechanical."""
    base = "from src.packet_tracer_mcp.foo import Bar\n"
    candidate = (
        "# quality-gate: mechanical-only\n"
        "from packet_tracer_mcp.foo import Bar\n"
        "SECRET = 1\n"
    )

    verdict = _classify(base, candidate)

    assert verdict.classification is Classification.SEMANTIC_OR_AUTHORED_CHANGE


def test_gate_exempts_only_files_proven_mechanical(tmp_path: Path) -> None:
    """Exempt a rename-only file while keeping every other delta under Ruff."""
    repository = tmp_path / "check out"
    baseline = _initialize_repository(repository)
    (repository / "smuggled.py").write_text(HISTORICAL_MODULE, encoding="utf-8")
    _git(repository, "add", "smuggled.py")
    _git(repository, "commit", "-m", "test: add second historical module")
    baseline = _git(repository, "rev-parse", "HEAD").stdout.strip()

    (repository / "historical.py").write_text(RENAMED_MODULE, encoding="utf-8")
    (repository / "smuggled.py").write_text(
        RENAMED_MODULE + "\n\ndef smuggled():\n    return 1\n",
        encoding="utf-8",
    )

    selection = select_worktree_changes(repository, baseline, AUTHORIZED)

    assert _relative_names(selection.exempt, repository) == ["historical.py"]
    assert _relative_names(selection.files, repository) == ["smuggled.py"]
    assert selection.unverifiable == ()
    assert run_ruff(selection.files) == 1


def test_gate_without_authorization_lints_every_changed_file(tmp_path: Path) -> None:
    """Keep the unchanged gate behavior when no migration is authorized."""
    repository = tmp_path / "checkout"
    baseline = _initialize_repository(repository)
    (repository / "historical.py").write_text(RENAMED_MODULE, encoding="utf-8")

    selection = select_worktree_changes(repository, baseline)

    assert selection.exempt == ()
    assert _relative_names(selection.files, repository) == ["historical.py"]
    assert run_ruff(selection.files) == 1


def test_delivery_selection_applies_the_same_boundary(tmp_path: Path) -> None:
    """Apply the mechanical boundary to delivery under a committed record."""
    repository = tmp_path / "checkout"
    baseline = _initialize_repository(repository)
    (repository / "historical.py").write_text(RENAMED_MODULE, encoding="utf-8")
    write_authorization(repository, AUTHORIZATION_RECORD, baseline)
    _git(repository, "add", "--all")
    _git(repository, "commit", "-m", "test: rename the namespace")
    delivery = _git(repository, "rev-parse", "HEAD").stdout.strip()

    selection = select_delivery_changes(
        repository,
        baseline,
        delivery,
        authorizations=[AUTHORIZATION_RECORD],
    )

    assert _relative_names(selection.exempt, repository) == ["historical.py"]
    assert selection.files == ()
    assert run_ruff(selection.files) == 0


def test_deleted_files_never_enter_the_boundary(tmp_path: Path) -> None:
    """Document that deletions are outside the selected set and its classifier."""
    repository = tmp_path / "checkout"
    baseline = _initialize_repository(repository)
    (repository / "historical.py").unlink()

    selection = select_worktree_changes(repository, baseline, AUTHORIZED)

    assert selection.files == ()
    assert selection.exempt == ()
    assert selection.classified == ()


def test_unverifiable_base_is_reported_and_never_exempt(tmp_path: Path) -> None:
    """Report an unanalyzable base and keep the file inside the Ruff set."""
    repository = tmp_path / "checkout"
    _initialize_repository(repository)
    (repository / "opaque.py").write_bytes(b"\xff\xfe\x00broken\n")
    _git(repository, "add", "opaque.py")
    _git(repository, "commit", "-m", "test: add an undecodable module")
    baseline = _git(repository, "rev-parse", "HEAD").stdout.strip()
    (repository / "opaque.py").write_text(RENAMED_MODULE, encoding="utf-8")

    selection = select_worktree_changes(repository, baseline, AUTHORIZED)

    assert _relative_names(selection.unverifiable, repository) == ["opaque.py"]
    assert _relative_names(selection.files, repository) == ["opaque.py"]
    assert selection.exempt == ()


def test_cli_rejects_an_unregistered_migration_identifier() -> None:
    """Fail closed when the command line names a transformation that is not registered."""
    result = subprocess.run(
        [
            sys.executable,
            str(QUALITY_GATE),
            "--base",
            "HEAD",
            "--mechanical-migration",
            "UNREGISTERED",
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "UNREGISTERED" in result.stderr


def test_cli_rejects_authorization_without_a_comparison_base() -> None:
    """Refuse a focused run that could not prove any mechanical equivalence."""
    result = subprocess.run(
        [
            sys.executable,
            str(QUALITY_GATE),
            "--files",
            str(QUALITY_GATE),
            "--mechanical-migration",
            CANONICAL,
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--mechanical-migration" in result.stderr


def test_gate_run_prints_every_exemption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Make each granted exemption visible in the gate's own audit output."""
    repository = tmp_path / "checkout"
    baseline = _initialize_repository(repository)
    (repository / "historical.py").write_text(RENAMED_MODULE, encoding="utf-8")
    monkeypatch.setattr("scripts.quality_gate.REPOSITORY_ROOT", repository)

    status = main(["--base", baseline, "--mechanical-migration", CANONICAL])
    output = capsys.readouterr().out

    assert status == 0
    assert f"Authorized mechanical migrations: {CANONICAL}" in output
    assert "historical.py" in output
    assert "MECHANICAL_ONLY" in output


def test_gate_run_fails_when_a_comparison_is_unverifiable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail the gate when a selected file's classification cannot be established."""
    repository = tmp_path / "checkout"
    _initialize_repository(repository)
    (repository / "opaque.py").write_bytes(b"\xff\xfe\x00broken\n")
    _git(repository, "add", "opaque.py")
    _git(repository, "commit", "-m", "test: add an undecodable module")
    baseline = _git(repository, "rev-parse", "HEAD").stdout.strip()
    (repository / "opaque.py").write_text(RENAMED_MODULE, encoding="utf-8")
    monkeypatch.setattr("scripts.quality_gate.REPOSITORY_ROOT", repository)

    status = main(["--base", baseline, "--mechanical-migration", CANONICAL])

    assert status != 0


def test_selection_rejects_an_unknown_base_before_classifying(tmp_path: Path) -> None:
    """Preserve the existing fail-closed base resolution with authorization present."""
    repository = tmp_path / "checkout"
    _initialize_repository(repository)

    with pytest.raises(QualityGateError, match="comparison base 'missing-ref'"):
        select_worktree_changes(repository, "missing-ref", AUTHORIZED)
