"""Local environment readers for the CP-SCALE LIVE preflight."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from ...application.cp_scale_live.admission import (
    CPScaleImportIsolationObservation,
    CPScaleProcessObservation,
    CPScaleRepositoryObservation,
)
from ...application.cp_scale_live.contracts import (
    CPScaleProcessRecord,
    CPScaleRuntimeEvidence,
)
from .import_isolation_preflight import (
    PRODUCTION_NAMESPACE,
    TEST_NAMESPACE,
    ImportIsolationPreflight,
)


CommandRunner = Callable[..., Any]


class GitOutput(Protocol):
    def __call__(self, root: Path, *arguments: str) -> str: ...


class PythonRuntimeEvidenceReader:
    """Read only the already-loaded process identity; never import a namespace."""

    def __init__(
        self,
        *,
        executable: Callable[[], str] = lambda: sys.executable,
        modules: Callable[[], Mapping[str, object]] = lambda: sys.modules,
    ) -> None:
        self._executable = executable
        self._modules = modules

    def read(self) -> CPScaleRuntimeEvidence:
        modules = self._modules()
        loaded = tuple(
            name
            for name in (PRODUCTION_NAMESPACE, TEST_NAMESPACE)
            if name in modules
        )
        production = modules.get(PRODUCTION_NAMESPACE)
        package_file = getattr(production, "__file__", "") if production else ""
        return CPScaleRuntimeEvidence(
            python_executable=str(self._executable() or ""),
            package_file=str(package_file or ""),
            loaded_namespaces=loaded,
        )


class PacketTracerImportIsolationReader:
    def __init__(
        self,
        *,
        factory: Callable[[Path], ImportIsolationPreflight] = ImportIsolationPreflight,
    ) -> None:
        self._factory = factory

    def read(self, governed_root: Path) -> CPScaleImportIsolationObservation:
        result = self._factory(governed_root).ensure_isolated()
        return CPScaleImportIsolationObservation(
            isolated=result.isolated,
            isolation_state=result.state.value,
            detail=result.detail,
            error="" if result.isolated else result.render(),
        )


class GitCPScaleRepositoryReader:
    """Read branch, cleanliness, pushed HEAD and source tree without mutation."""

    def __init__(self, *, git_output: GitOutput | None = None) -> None:
        self._git_output = git_output or _git_output

    def read(self, governed_root: Path) -> CPScaleRepositoryObservation:
        branch = ""
        upstream = ""
        head = ""
        error = ""
        try:
            branch = self._git_output(governed_root, "branch", "--show-current")
            upstream = self._git_output(
                governed_root,
                "rev-parse",
                "--abbrev-ref",
                "@{upstream}",
            )
            head = self._git_output(governed_root, "rev-parse", "HEAD")
        except (OSError, subprocess.CalledProcessError) as exc:
            branch = ""
            upstream = ""
            head = ""
            error = str(exc)

        dirty: bool | None
        dirty_error = ""
        try:
            dirty = bool(self._git_output(governed_root, "status", "--porcelain"))
        except (OSError, subprocess.CalledProcessError) as exc:
            dirty = None
            dirty_error = str(exc)

        upstream_head = ""
        upstream_head_error = ""
        try:
            upstream_head = self._git_output(
                governed_root,
                "rev-parse",
                "@{upstream}",
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            upstream_head_error = str(exc)

        source_tree = ""
        source_tree_error = ""
        if head:
            try:
                source_tree = self._git_output(
                    governed_root,
                    "rev-parse",
                    f"{head}^{{tree}}",
                )
            except (OSError, subprocess.CalledProcessError) as exc:
                source_tree_error = str(exc)
        else:
            source_tree_error = "Repository HEAD was unavailable for tree capture."

        if head:
            try:
                final_head = self._git_output(
                    governed_root,
                    "rev-parse",
                    "HEAD",
                )
                if final_head != head:
                    source_tree_error = (
                        "HEAD changed during repository inspection: "
                        f"captured {head!r}; observed {final_head!r}."
                    )
            except (OSError, subprocess.CalledProcessError) as exc:
                source_tree_error = (
                    "Repository HEAD could not be revalidated: " + str(exc)
                )

        if upstream_head:
            try:
                final_upstream_head = self._git_output(
                    governed_root,
                    "rev-parse",
                    "@{upstream}",
                )
                if final_upstream_head != upstream_head:
                    upstream_head_error = (
                        "upstream changed during repository inspection: "
                        f"captured {upstream_head!r}; "
                        f"observed {final_upstream_head!r}."
                    )
            except (OSError, subprocess.CalledProcessError) as exc:
                upstream_head_error = (
                    "Repository upstream could not be revalidated: " + str(exc)
                )

        return CPScaleRepositoryObservation(
            branch=branch,
            upstream=upstream,
            head=head,
            upstream_head=upstream_head,
            source_tree=source_tree,
            dirty=dirty,
            error=error,
            dirty_error=dirty_error,
            upstream_head_error=upstream_head_error,
            source_tree_error=source_tree_error,
        )


class PowerShellPacketTracerProcessReader:
    """Enumerate Packet Tracer processes and retain exact version/path evidence."""

    _COMMAND = (
        "Get-Process | Where-Object { $_.ProcessName -like 'PacketTracer*' } | "
        "ForEach-Object { [PSCustomObject]@{ "
        "ProcessName=$_.ProcessName; Id=$_.Id; "
        "MainWindowHandle=$_.MainWindowHandle; "
        "ProductVersion=$_.MainModule.FileVersionInfo.ProductVersion; "
        "FileVersion=$_.MainModule.FileVersionInfo.FileVersion; "
        "Path=$_.MainModule.FileName } } | ConvertTo-Json -Compress"
    )

    def __init__(self, *, run_command: CommandRunner = subprocess.run) -> None:
        self._run_command = run_command

    def read(self) -> CPScaleProcessObservation:
        try:
            completed = self._run_command(
                ["powershell.exe", "-NoProfile", "-Command", self._COMMAND],
                check=True,
                capture_output=True,
                text=True,
            )
            raw = completed.stdout.strip()
            if not raw:
                return CPScaleProcessObservation()
            parsed = json.loads(raw)
            rows = parsed if isinstance(parsed, list) else [parsed]
            if not all(isinstance(item, dict) for item in rows):
                raise ValueError("Packet Tracer process output is not an object list.")
            return CPScaleProcessObservation(
                processes=tuple(_process_record(item) for item in rows),
            )
        except Exception as exc:
            return CPScaleProcessObservation(
                error=(
                    "Packet Tracer process inspection failed: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )


def _git_output(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _process_record(row: Mapping[str, object]) -> CPScaleProcessRecord:
    return CPScaleProcessRecord(
        pid=_required_int(row.get("Id"), "Id"),
        name=_required_string(row.get("ProcessName"), "ProcessName"),
        main_window_handle=_required_int(
            row.get("MainWindowHandle"),
            "MainWindowHandle",
        ),
        product_version=_optional_string(
            row.get("ProductVersion"),
            "ProductVersion",
        ),
        file_version=_optional_string(row.get("FileVersion"), "FileVersion"),
        executable_path=_required_string(row.get("Path"), "Path"),
    )


def _required_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer; got {value!r}.")
    return value


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string; got {value!r}.")
    return value


def _optional_string(value: object, field: str) -> str:
    if value is None:
        return ""
    return _required_string(value, field)
