"""Shared sources and Git repositories for the mechanical migration boundary tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
QUALITY_GATE = REPOSITORY_ROOT / "scripts" / "quality_gate.py"
CANONICAL = "CANONICAL_PYTHON_NAMESPACE"
CANONICAL_AUTHORITY = "docs/engineering/change-briefs/namespace-migration.md"
AUTHORIZATION_SCHEMA = "cisco-mcp/mechanical-migration-authorization"
AUTHORIZATION_RECORD = "authorizations/canonical-python-namespace.json"
LEGACY = "src.packet_tracer_mcp"
TARGET = "packet_tracer_mcp"

# A historical module carrying pre-existing Ruff debt: the public function has no
# docstring (D103) and the imports are unsorted (I001). The migration never
# authors that debt, so a rename-only delta must not make the gate report it.
HISTORICAL_MODULE = '''"""Historical module."""

from src.packet_tracer_mcp.domain.models import Device
import os


def build(name):
    return Device(name, os.name)
'''

RENAMED_MODULE = HISTORICAL_MODULE.replace(LEGACY, TARGET)


def git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run Git in a repository and require success."""
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


def initialize_repository(repository: Path) -> str:
    """Create a repository holding the historical module and return its SHA."""
    repository.mkdir(parents=True, exist_ok=True)
    git(repository, "init", "--initial-branch=main")
    git(repository, "config", "user.email", "quality-gate@example.invalid")
    git(repository, "config", "user.name", "Quality Gate Test")
    (repository / "historical.py").write_text(HISTORICAL_MODULE, encoding="utf-8")
    git(repository, "add", "historical.py")
    git(repository, "commit", "-m", "test: create historical module")
    return head(repository)


def initialize_exact_repository(repository: Path) -> str:
    """Create a repository that stores exactly the bytes written to it.

    Line-ending conversion is disabled, so the stored blob of every file equals
    the bytes a test writes. The historical module is stored with LF endings.
    """
    repository.mkdir(parents=True, exist_ok=True)
    git(repository, "init", "--initial-branch=main")
    git(repository, "config", "core.autocrlf", "false")
    git(repository, "config", "user.email", "quality-gate@example.invalid")
    git(repository, "config", "user.name", "Quality Gate Test")
    (repository / "historical.py").write_bytes(HISTORICAL_MODULE.encode("utf-8"))
    return commit_all(repository, "test: create historical module")


def head(repository: Path) -> str:
    """Return the repository's current commit SHA."""
    return git(repository, "rev-parse", "HEAD").stdout.strip()


def commit_all(repository: Path, message: str) -> str:
    """Commit every current change and return the new commit SHA."""
    git(repository, "add", "--all")
    git(repository, "commit", "-m", message)
    return head(repository)


def stored_blob(repository: Path, commit: str, path: str) -> bytes:
    """Return the exact bytes Git stores for a path at a commit."""
    return subprocess.run(
        ["git", "cat-file", "blob", f"{commit}:{path}"],
        cwd=repository,
        check=True,
        capture_output=True,
    ).stdout


def authorization_record(
    base_commit: str,
    /,
    **overrides: object,
) -> dict[str, object]:
    """Return a well-formed authorization record, with optional field overrides."""
    record: dict[str, object] = {
        "schema": AUTHORIZATION_SCHEMA,
        "version": 1,
        "transformation": CANONICAL,
        "base_commit": base_commit,
        "authority": CANONICAL_AUTHORITY,
    }
    record.update(overrides)
    return record


def write_authorization(
    repository: Path,
    name: str,
    base_commit: str,
    /,
    **overrides: object,
) -> str:
    """Write an authorization record and its cited brief; return the record path."""
    brief = repository / CANONICAL_AUTHORITY
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_bytes(b"# Namespace migration\n")
    record = repository / name
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_bytes(
        json.dumps(authorization_record(base_commit, **overrides)).encode("utf-8")
    )
    return name
