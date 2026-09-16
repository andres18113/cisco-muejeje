"""The repository keeps no active use of the retired import namespace.

A "zero" is only worth something if the instrument that produced it can be
shown to react, so the acceptance assertion here is paired with controls: a
synthetic import and a synthetic dynamic-import target must both be reported,
a retained rejection reference must not be, and an unparsable file must fail
the inventory instead of quietly shrinking it.
"""

from __future__ import annotations

from pathlib import Path

from scripts.namespace_inventory import (
    LEGACY_NAMESPACE,
    RETAINED_STRING_REFERENCES,
    main,
    scan,
    tracked_python_files,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, relative: str, source: str) -> Path:
    """Create a source file inside a synthetic repository root."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_the_repository_has_no_active_use_of_the_retired_namespace():
    """The migration's acceptance criterion, measured over tracked sources."""
    inventory = scan(tracked_python_files(REPOSITORY_ROOT), REPOSITORY_ROOT)

    assert [usage.as_dict() for usage in inventory.active] == []
    assert inventory.unparsed == []


def test_the_command_reports_success_for_the_current_tree():
    """The command-line form agrees with the scanned result."""
    assert main([]) == 0


def test_an_import_of_the_retired_namespace_is_reported(tmp_path):
    """Negative control: the instrument reacts to a real import."""
    _write(
        tmp_path,
        "tests/test_relapse.py",
        f"from {LEGACY_NAMESPACE}.domain import models\n",
    )

    inventory = scan([tmp_path / "tests" / "test_relapse.py"], tmp_path)

    assert len(inventory.imports) == 1
    assert inventory.imports[0].path == "tests/test_relapse.py"
    assert inventory.imports[0].kind == "import"


def test_importing_the_package_root_alone_is_reported(tmp_path):
    """`import src` is the same second identity, spelled shorter."""
    _write(tmp_path, "tests/test_root.py", "import src\n")

    inventory = scan([tmp_path / "tests" / "test_root.py"], tmp_path)

    assert [usage.text for usage in inventory.imports] == ["import src"]


def test_a_dynamic_import_target_is_reported(tmp_path):
    """A module path in a string still loads the package under a second name."""
    _write(
        tmp_path,
        "tests/test_dynamic.py",
        "import importlib\n"
        f'module = importlib.import_module("{LEGACY_NAMESPACE}.domain.models")\n',
    )

    inventory = scan([tmp_path / "tests" / "test_dynamic.py"], tmp_path)

    assert len(inventory.active_strings) == 1
    assert inventory.active_strings[0].kind == "string"


def test_prose_about_the_migration_is_not_an_active_use(tmp_path):
    """Docstrings and comments describe the migration; they do not perform it."""
    _write(
        tmp_path,
        "tests/test_prose.py",
        f'"""This module no longer imports {LEGACY_NAMESPACE}."""\n'
        f"# {LEGACY_NAMESPACE} is retired.\n",
    )

    inventory = scan([tmp_path / "tests" / "test_prose.py"], tmp_path)

    assert inventory.active == []
    assert len(inventory.prose) == 2


def test_a_retained_rejection_reference_is_not_counted_as_active(tmp_path):
    """A guard that names the retired namespace in order to refuse it."""
    relative = next(iter(RETAINED_STRING_REFERENCES))
    _write(tmp_path, relative, f'FORBIDDEN = "{LEGACY_NAMESPACE}"\n')

    inventory = scan([tmp_path / relative], tmp_path)

    assert inventory.active == []
    assert [usage.path for usage in inventory.retained_strings] == [relative]


def test_every_retained_file_declares_why_it_is_retained():
    """The allowlist is a set of decisions, not a place to park a real use."""
    assert all(reason.strip() for reason in RETAINED_STRING_REFERENCES.values())
    for relative in RETAINED_STRING_REFERENCES:
        assert (REPOSITORY_ROOT / relative).is_file(), relative


def test_a_retained_entry_never_licenses_an_import(tmp_path):
    """Being allowlisted covers strings only; an import is refused anywhere."""
    relative = next(iter(RETAINED_STRING_REFERENCES))
    _write(tmp_path, relative, f"import {LEGACY_NAMESPACE}\n")

    inventory = scan([tmp_path / relative], tmp_path)

    assert len(inventory.imports) == 1
    assert inventory.active != []


def test_an_unparsable_file_fails_the_inventory_rather_than_emptying_it(tmp_path):
    """An unresolved file is unknown, not clean."""
    _write(tmp_path, "tests/test_broken.py", "def broken(:\n")

    inventory = scan([tmp_path / "tests" / "test_broken.py"], tmp_path)

    assert len(inventory.unparsed) == 1
    assert inventory.unparsed[0].kind == "syntax-error"
