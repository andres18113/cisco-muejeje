"""Small cross-platform harness for Python subprocess regressions."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def checkout_venv_root(root: Path) -> Path:
    return root / ".venv"


def checkout_venv_python(root: Path) -> Path:
    relative = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    return checkout_venv_root(root) / relative


def foreign_python(root: Path) -> Path:
    name = "python.exe" if os.name == "nt" else "python"
    return root.parent / "foreign-python" / name


def run_isolated_python(
    code: str,
    *,
    cwd: Path,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run the current interpreter without inherited Python path injection."""
    environment = os.environ.copy()
    for variable in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP"):
        environment.pop(variable, None)
    return subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def subprocess_failure(completed: subprocess.CompletedProcess[str]) -> str:
    return (
        f"child return code: {completed.returncode}\n"
        f"child stdout:\n{completed.stdout}\n"
        f"child stderr:\n{completed.stderr}"
    )
