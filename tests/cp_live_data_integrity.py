"""Shared CP-LIVE test-state isolation and protected-path sentinels."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path


ISOLATED_TEST_TOKEN = "cp-live-tests-isolated-token-0123456789"


@dataclass(frozen=True)
class ProtectedPathEntry:
    path: str
    kind: str
    length: int | None = None
    sha256: str = ""


@dataclass(frozen=True)
class ProtectedPathsSnapshot:
    roots: tuple[Path, ...]
    entries: tuple[ProtectedPathEntry, ...]


def cp_live_workspace_protected_paths(root: Path) -> tuple[Path, ...]:
    root = Path(root).resolve()
    return (
        root / "data" / "cp-scale",
        root / "data" / "capabilities",
        root / "docs" / "reference" / "cp-scale" / "live_canonical_checkpoint.json",
        root / "docs" / "reference" / "cp-scale" / "canonical-live-evidence",
    )


def _file_entry(path: Path) -> ProtectedPathEntry:
    digest = hashlib.sha256()
    length = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            length += len(chunk)
            digest.update(chunk)
    return ProtectedPathEntry(str(path), "file", length, digest.hexdigest())


def capture_protected_paths(paths: Sequence[Path]) -> ProtectedPathsSnapshot:
    roots = tuple(Path(path).resolve() for path in paths)
    entries: list[ProtectedPathEntry] = []
    for root in roots:
        if not root.exists():
            entries.append(ProtectedPathEntry(str(root), "absent"))
            continue
        if root.is_file():
            entries.append(_file_entry(root))
            continue
        entries.append(ProtectedPathEntry(str(root), "directory"))
        for child in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
            if child.is_symlink():
                entries.append(ProtectedPathEntry(str(child), "symlink"))
            elif child.is_dir():
                entries.append(ProtectedPathEntry(str(child), "directory"))
            elif child.is_file():
                entries.append(_file_entry(child))
    return ProtectedPathsSnapshot(roots, tuple(entries))


def assert_protected_paths_unchanged(before: ProtectedPathsSnapshot) -> None:
    after = capture_protected_paths(before.roots)
    if after.entries == before.entries:
        return
    expected = {entry.path: entry for entry in before.entries}
    observed = {entry.path: entry for entry in after.entries}
    changed = [
        path
        for path in sorted(expected.keys() | observed.keys())
        if expected.get(path) != observed.get(path)
    ]
    raise AssertionError("Protected paths changed: " + ", ".join(changed))


def isolated_subprocess_environment(
    root: Path,
    *,
    governed_root: Path | None = None,
    inherited: Mapping[str, str] | None = None,
) -> dict[str, str]:
    root = Path(root).resolve()
    machine = root / "machine-state"
    temporary = root / "temporary"
    machine.mkdir(parents=True, exist_ok=True)
    temporary.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ if inherited is None else inherited)
    for name in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP"):
        environment.pop(name, None)
    environment.update({
        "LOCALAPPDATA": str(machine),
        "APPDATA": str(machine),
        "XDG_STATE_HOME": str(machine),
        "TEMP": str(temporary),
        "TMP": str(temporary),
        "TMPDIR": str(temporary),
        "PT_MCP_BRIDGE_TOKEN": ISOLATED_TEST_TOKEN,
        "PYTHONNOUSERSITE": "1",
    })
    if governed_root is None:
        environment.pop("PT_MCP_GOVERNED_ROOT", None)
    else:
        environment["PT_MCP_GOVERNED_ROOT"] = str(Path(governed_root).resolve())
    return environment
