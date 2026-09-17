"""The quality gate loads its classifier from one location chosen deterministically.

`scripts/quality_gate.py` runs both as a script and as `scripts.quality_gate`. In
either context it must load the sibling `mechanical_migration.py` and nothing
else: an import failure inside that module propagates, and a different module of
the same name elsewhere on the import path is never tried in its place.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.mechanical_migration_fixtures import CANONICAL, REPOSITORY_ROOT

DECOY_MARKER = "DECOY-MECHANICAL-MIGRATION-LOADED"


def _project(tmp_path: Path, *, broken: bool) -> Path:
    """Copy the gate into an isolated project with an optional failing classifier."""
    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(
        REPOSITORY_ROOT / "scripts" / "quality_gate.py",
        scripts / "quality_gate.py",
    )
    if broken:
        # The authoritative module exists but fails with its own ImportError.
        (scripts / "mechanical_migration.py").write_text(
            "import missing_dependency_of_the_classifier\n",
            encoding="utf-8",
        )
    else:
        shutil.copyfile(
            REPOSITORY_ROOT / "scripts" / "mechanical_migration.py",
            scripts / "mechanical_migration.py",
        )
    return project


def _environment(tmp_path: Path) -> dict[str, str]:
    """Return an environment whose import path offers a decoy classifier."""
    decoys = tmp_path / "decoys"
    decoys.mkdir()
    (decoys / "mechanical_migration.py").write_text(
        f"print({DECOY_MARKER!r})\n"
        "def registered_identifiers():\n"
        "    return ('DECOY',)\n",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment.pop("PYTHONSAFEPATH", None)
    environment["PYTHONPATH"] = str(decoys)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _run(
    arguments: list[str],
    project: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run the interpreter from the isolated project directory."""
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("flags", [[], ["-P"]], ids=["default", "safe-path"])
def test_script_loads_its_sibling_classifier(tmp_path: Path, flags: list[str]) -> None:
    """Use the sibling classifier when run as a script, even with a decoy present."""
    project = _project(tmp_path, broken=False)
    environment = _environment(tmp_path)

    result = _run(
        [*flags, str(project / "scripts" / "quality_gate.py"), "--help"],
        project,
        environment,
    )

    assert result.returncode == 0, result.stderr
    assert DECOY_MARKER not in result.stdout + result.stderr
    assert CANONICAL in result.stdout


@pytest.mark.parametrize("flags", [[], ["-P"]], ids=["default", "safe-path"])
def test_script_propagates_an_internal_classifier_import_error(
    tmp_path: Path,
    flags: list[str],
) -> None:
    """Fail the script with the classifier's own error instead of loading a decoy."""
    project = _project(tmp_path, broken=True)
    environment = _environment(tmp_path)

    result = _run(
        [*flags, str(project / "scripts" / "quality_gate.py"), "--help"],
        project,
        environment,
    )

    assert result.returncode != 0
    assert DECOY_MARKER not in result.stdout + result.stderr
    assert "missing_dependency_of_the_classifier" in result.stderr


def test_package_import_loads_the_package_classifier(tmp_path: Path) -> None:
    """Bind `scripts.quality_gate` to the classifier inside its own package."""
    project = _project(tmp_path, broken=False)
    environment = _environment(tmp_path)

    result = _run(
        [
            "-c",
            "import scripts.quality_gate as gate; "
            "print(gate.mechanical_migration.__name__); "
            "print(gate.mechanical_migration.__file__)",
        ],
        project,
        environment,
    )

    assert result.returncode == 0, result.stderr
    assert DECOY_MARKER not in result.stdout
    name, location = result.stdout.splitlines()
    assert name == "scripts.mechanical_migration"
    assert Path(location) == project / "scripts" / "mechanical_migration.py"


def test_package_import_propagates_an_internal_classifier_import_error(
    tmp_path: Path,
) -> None:
    """Fail `import scripts.quality_gate` instead of falling back to a decoy."""
    project = _project(tmp_path, broken=True)
    environment = _environment(tmp_path)

    result = _run(["-c", "import scripts.quality_gate"], project, environment)

    assert result.returncode != 0
    assert DECOY_MARKER not in result.stdout + result.stderr
    assert "missing_dependency_of_the_classifier" in result.stderr
