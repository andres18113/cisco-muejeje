"""The repository keeps no active use of the retired import namespace.

A "zero" is only worth something if the instrument that produced it can be
shown to react, so the acceptance assertion here is paired with controls: a
synthetic import and a synthetic dynamic-import target must both be reported,
a retained rejection reference must not be, and an unparsable file must fail
the inventory instead of quietly shrinking it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.namespace_inventory import (
    LEGACY_NAMESPACE,
    RETAINED_STRING_REFERENCES,
    exit_status,
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
    assert [usage.as_dict() for usage in inventory.unreviewed_strings] == []
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
    assert inventory.active_strings[0].kind == "dynamic-import"


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


RETAINED_FILE = next(iter(RETAINED_STRING_REFERENCES))

# Sources that load or register the retired namespace, written with a `{legacy}`
# placeholder so this test module never spells one itself. Each names the kind
# the inventory must report, whatever file it appears in.
EXECUTABLE_CONTEXTS = [
    (
        "find-spec",
        'import importlib.util\nimportlib.util.find_spec("{legacy}.domain")\n',
        "dynamic-import",
    ),
    ("builtin-import", '__import__("{legacy}")\n', "dynamic-import"),
    (
        "import-module-keyword",
        'import importlib\nimportlib.import_module(name="{legacy}")\n',
        "dynamic-import",
    ),
    (
        "mock-patch-target",
        'from unittest import mock\nwith mock.patch("{legacy}.domain.Thing"):\n'
        "    pass\n",
        "dynamic-import",
    ),
    (
        "monkeypatch-setattr-target",
        'def test(monkeypatch):\n    monkeypatch.setattr("{legacy}.domain.VALUE", 1)\n',
        "dynamic-import",
    ),
    (
        "sys-modules-assignment",
        'import sys\nimport types\nsys.modules["{legacy}"] = types.ModuleType("m")\n',
        "module-registry",
    ),
    (
        "sys-modules-setdefault",
        'import sys\nsys.modules.setdefault("{legacy}", object())\n',
        "module-registry",
    ),
    (
        "monkeypatch-setitem",
        "import sys\n\n\ndef test(monkeypatch):\n"
        '    monkeypatch.setitem(sys.modules, "{legacy}", object())\n',
        "module-registry",
    ),
    (
        "patch-dict",
        "import sys\nfrom unittest import mock\n"
        'with mock.patch.dict(sys.modules, {"{legacy}": object()}):\n    pass\n',
        "module-registry",
    ),
    (
        "child-source-inline",
        'import subprocess\nimport sys\nsubprocess.run([sys.executable, "-c", '
        '"import {legacy}"])\n',
        "executed-source",
    ),
    (
        "child-source-by-name",
        'import subprocess\nimport sys\nCHILD = "from {legacy}.domain import models\\n"\n'
        'subprocess.run([sys.executable, "-c", CHILD])\n',
        "executed-source",
    ),
    (
        "exec-source",
        'exec("import {legacy}.domain")\n',
        "executed-source",
    ),
    (
        "unparsable-child-source",
        'import subprocess\nimport sys\nsubprocess.run([sys.executable, "-c", '
        '"import {legacy} ("])\n',
        "executed-source",
    ),
]

# Sources that only name the retired namespace as data.
INERT_CONTEXTS = [
    ("guard-tuple", 'FORBIDDEN = ("packet_tracer_mcp", "{legacy}")\n'),
    ("membership-assertion", 'import sys\nassert "{legacy}" not in sys.modules\n'),
    ("registry-lookup", 'import sys\nloaded = sys.modules.get("{legacy}")\n'),
    (
        "child-source-that-only-inspects",
        'import subprocess\nimport sys\nsubprocess.run([sys.executable, "-c", '
        "\"import sys; print('{legacy}' in sys.modules)\"])\n",
    ),
    ("unrelated-call", 'record("{legacy}.domain")\n'),
    ("classifier-fixture", 'BASE = "from {legacy}.domain import models\\n"\n'),
]


def _source(template: str) -> str:
    """Fill a source template with the retired namespace."""
    return template.replace("{legacy}", LEGACY_NAMESPACE)


def test_importing_from_the_package_root_is_reported(tmp_path):
    """`from src import packet_tracer_mcp` loads the retired package root."""
    _write(tmp_path, "tests/test_from_root.py", "from src import packet_tracer_mcp\n")

    inventory = scan([tmp_path / "tests" / "test_from_root.py"], tmp_path)

    assert [usage.kind for usage in inventory.imports] == ["import"]


@pytest.mark.parametrize(
    ("label", "template", "kind"),
    EXECUTABLE_CONTEXTS,
    ids=[label for label, _, _ in EXECUTABLE_CONTEXTS],
)
@pytest.mark.parametrize(
    "relative",
    [RETAINED_FILE, "tests/test_unlisted.py"],
    ids=["allowlisted", "unlisted"],
)
def test_an_executable_reference_is_active_in_any_file(
    tmp_path, label, template, kind, relative
):
    """No allowlist entry can turn a load of the retired namespace into data."""
    _write(tmp_path, relative, _source(template))

    inventory = scan([tmp_path / relative], tmp_path)

    assert [usage.kind for usage in inventory.active] == [kind], label
    assert inventory.retained_strings == []
    assert inventory.unreviewed_strings == []
    assert exit_status(inventory) == 1


@pytest.mark.parametrize(
    ("label", "template"),
    INERT_CONTEXTS,
    ids=[label for label, _ in INERT_CONTEXTS],
)
def test_an_inert_mention_in_an_allowlisted_file_is_retained(tmp_path, label, template):
    """Naming the retired namespace as data is not a use of it."""
    _write(tmp_path, RETAINED_FILE, _source(template))

    inventory = scan([tmp_path / RETAINED_FILE], tmp_path)

    assert inventory.active == [], label
    assert [usage.kind for usage in inventory.retained_strings] == ["string"]
    assert exit_status(inventory) == 0


@pytest.mark.parametrize(
    ("label", "template"),
    INERT_CONTEXTS,
    ids=[label for label, _ in INERT_CONTEXTS],
)
def test_an_inert_mention_outside_the_allowlist_still_fails(tmp_path, label, template):
    """Every file that names the retired namespace is a reviewed decision."""
    _write(tmp_path, "tests/test_unlisted.py", _source(template))

    inventory = scan([tmp_path / "tests" / "test_unlisted.py"], tmp_path)

    assert inventory.active == [], label
    assert [usage.path for usage in inventory.unreviewed_strings] == [
        "tests/test_unlisted.py"
    ]
    assert exit_status(inventory) == 1


def test_every_allowlisted_file_still_needs_its_entry():
    """A stale entry is a place a future use could hide; none may remain."""
    inventory = scan(tracked_python_files(REPOSITORY_ROOT), REPOSITORY_ROOT)

    assert set(RETAINED_STRING_REFERENCES) == {
        usage.path for usage in inventory.retained_strings
    }
