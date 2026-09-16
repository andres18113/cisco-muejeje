"""A clean worktree must test its own source, under one name.

Why this file exists
--------------------
A shared `.venv` carries an editable install that records one absolute tree. A
newly created worktree inherits that `.pth`, so a bare `import
packet_tracer_mcp` resolved to the main checkout while the operator was editing
the worktree. Measured during Runtime Safety R1: 18 test files were validating
code that was not the code being changed, and the failure was silent -- the
tests passed, they simply tested something else.

The suite's historical containment for that defect was to import the package as
`src.packet_tracer_mcp`, which pinned resolution to the repository root. It
worked, but it bought isolation with a second identity of the same files, and
two identities make every cross-namespace `isinstance` and enum comparison
silently false.

The canonical namespace migration removed the second name. Isolation is now
established by the thing that was wrong in the first place -- the environment
and its editable install -- and proved here:

* `tests.namespace_preflight` decides identity and origin, and the suite
  already refuses to collect without it. This module asserts the same rule
  holds, so the guarantee is visible as a test and not only as a side effect
  of collection.
* The runtime entrypoints are exercised **from the repository root**. The
  superseded version ran them with `cwd=src`, where Python puts the current
  directory first on `sys.path`; that made the checks pass whatever the
  editable install pointed at, which is precisely the fault they existed to
  detect. Running from the root has no such fallback: it resolves through the
  environment, so a foreign or missing install fails here instead of hiding.

What this module does not own: proving that no source still imports the retired
namespace. `tests/test_namespace_inventory.py` measures that across every
tracked file, and duplicating it here with a narrower glob would only create a
second, weaker answer.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import packet_tracer_mcp as package_under_test
from tests.namespace_preflight import (
    LEGACY_NAMESPACE,
    PRODUCTION_NAMESPACE,
    NamespacePreflight,
    NamespacePreflightState,
)

REPO = Path(__file__).resolve().parents[1]
EXPECTED_PACKAGE_FILE = REPO / "src" / PRODUCTION_NAMESPACE / "__init__.py"


def test_the_package_under_test_belongs_to_this_worktree():
    """The source being tested is the source in this tree."""
    resolved = Path(package_under_test.__file__).resolve()

    assert REPO in resolved.parents, (
        "The tests are importing the package from outside this worktree: "
        f"{resolved}. Check this checkout's editable install before trusting "
        "any result."
    )


def test_the_package_resolves_under_the_src_layout_of_this_repo():
    """And it resolves at the exact path this checkout's layout declares."""
    assert Path(package_under_test.__file__).resolve() == EXPECTED_PACKAGE_FILE


def test_this_process_satisfies_the_namespace_preflight():
    """The gate that guards collection is asserted, not merely assumed."""
    result = NamespacePreflight(REPO).evaluate()

    assert result.state is NamespacePreflightState.ISOLATED, result.render(REPO)


def test_a_bare_import_from_the_repository_root_resolves_to_this_worktree():
    """The real editable-install check, with no directory trick to soften it.

    From the root there is no `src` on `sys.path`, so this name can only come
    from the environment. If the environment belongs to another checkout, this
    is where it shows.
    """
    completed = subprocess.run(
        [sys.executable, "-c", "import packet_tracer_mcp as m; print(m.__file__)"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    resolved = Path(completed.stdout.strip()).resolve()
    assert resolved == EXPECTED_PACKAGE_FILE, (
        f"The runtime loaded the package from {resolved}, outside this worktree."
    )


def test_the_module_entrypoint_starts_from_the_repository_root():
    """Non-mutating startup: `--help` proves the executable module is the local one."""
    completed = subprocess.run(
        [sys.executable, "-m", PRODUCTION_NAMESPACE, "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "pt-mcp" in completed.stdout


def test_the_console_entrypoint_starts_from_the_repository_root():
    """The installed `pt-mcp` script is the shipped entrypoint; it is tested too."""
    script = Path(sys.executable).parent / (
        "pt-mcp.exe" if sys.platform == "win32" else "pt-mcp"
    )

    assert script.is_file(), (
        f"The console entrypoint is missing from this environment: {script}. "
        "Install this checkout in editable mode."
    )

    completed = subprocess.run(
        [str(script), "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "pt-mcp" in completed.stdout


def test_only_one_identity_of_the_package_is_loaded_in_a_process():
    """Two identities made a cross-namespace `isinstance` always false."""
    code = (
        "import sys\n"
        "import packet_tracer_mcp\n"
        "print(sorted(n for n in sys.modules "
        f"if n in ({PRODUCTION_NAMESPACE!r}, {LEGACY_NAMESPACE!r})))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == f"['{PRODUCTION_NAMESPACE}']"


def test_the_retired_namespace_is_not_loaded_by_the_running_suite():
    """`src/` is where the package lives, not a name the suite may import."""
    assert LEGACY_NAMESPACE not in sys.modules
    assert "src" not in sys.modules
