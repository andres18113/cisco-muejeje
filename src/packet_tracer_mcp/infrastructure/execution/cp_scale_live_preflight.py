"""Local environment readers for the CP-SCALE LIVE preflight."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

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
from .source_preflight import GitOutput, GitSourceReader


CommandRunner = Callable[..., Any]


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
        self._reader = GitSourceReader(git_output=git_output)

    def read(self, governed_root: Path) -> CPScaleRepositoryObservation:
        observed = self._reader.read(governed_root)
        return CPScaleRepositoryObservation(
            branch=observed.branch,
            upstream=observed.upstream,
            head=observed.head,
            upstream_head=observed.upstream_head,
            source_tree=observed.source_tree,
            dirty=observed.dirty,
            error=observed.error,
            dirty_error=observed.dirty_error,
            upstream_head_error=observed.upstream_head_error,
            source_tree_error=observed.source_tree_error,
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
