"""Small cross-platform harness for Python subprocess regressions."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.cp_live_data_integrity import isolated_subprocess_environment


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
    governed_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run Python with no inherited package, token, mailbox or temp state."""
    return run_isolated_command(
        (sys.executable, "-I", "-"),
        cwd=cwd,
        timeout=timeout,
        governed_root=governed_root,
        stdin=code,
    )


def run_isolated_command(
    command: Sequence[str | Path],
    *,
    cwd: Path,
    timeout: int = 120,
    governed_root: Path | None = None,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run any child with fresh machine-local, token and temporary roots."""
    with TemporaryDirectory(prefix="cp-live-python-") as directory:
        environment = isolated_subprocess_environment(
            Path(directory),
            governed_root=governed_root,
        )
        return subprocess.run(
            [str(item) for item in command],
            cwd=cwd,
            env=environment,
            input=stdin,
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
