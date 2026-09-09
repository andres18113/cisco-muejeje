"""Typed contracts for the local, offline CP-SCALE LIVE preflight."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ..use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalTarget,
    CPScaleCanonicalTargetContract,
)


class CPScaleCheckState(str, Enum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"


class CPScalePreflightOutcome(str, Enum):
    """A local continuation decision, never product admission."""

    ADMITTED = "admitted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class CPScaleLiveRequest:
    packet_tracer_version: str
    expected_head: str
    retain_on_full_verification: bool
    target_stage: CPScaleCanonicalTarget | str = (
        CPScaleCanonicalTarget.FULL_QUALIFICATION
    )


@dataclass(frozen=True)
class CPScaleRuntimeEvidence:
    python_executable: str = ""
    package_file: str = ""
    loaded_namespaces: tuple[str, ...] = ()
    error: str = ""

    @property
    def coherent(self) -> bool:
        return bool(
            not self.error
            and isinstance(self.python_executable, str)
            and self.python_executable
            and isinstance(self.package_file, str)
            and self.package_file
            and isinstance(self.loaded_namespaces, tuple)
            and self.loaded_namespaces == ("packet_tracer_mcp",)
        )


@dataclass(frozen=True)
class CPScaleImportIsolationEvidence:
    state: CPScaleCheckState
    isolation_state: str = ""
    detail: str = ""
    error: str = ""

    @property
    def passed_coherently(self) -> bool:
        return bool(
            self.state is CPScaleCheckState.PASSED
            and isinstance(self.isolation_state, str)
            and self.isolation_state == "ISOLATED"
            and isinstance(self.detail, str)
            and self.detail
            and not self.error
        )


@dataclass(frozen=True)
class CPScaleRepositoryEvidence:
    state: CPScaleCheckState
    branch: str = ""
    upstream: str = ""
    head: str = ""
    upstream_head: str = ""
    source_tree: str = ""
    dirty: bool | None = None
    error: str = ""
    dirty_error: str = ""
    upstream_head_error: str = ""
    source_tree_error: str = ""

    @property
    def passed_coherently(self) -> bool:
        return bool(
            self.state is CPScaleCheckState.PASSED
            and isinstance(self.branch, str)
            and self.branch
            and isinstance(self.upstream, str)
            and self.upstream
            and isinstance(self.head, str)
            and self.head
            and isinstance(self.upstream_head, str)
            and self.upstream_head == self.head
            and isinstance(self.source_tree, str)
            and self.source_tree
            and self.dirty is False
            and not self.error
            and not self.dirty_error
            and not self.upstream_head_error
            and not self.source_tree_error
        )


@dataclass(frozen=True)
class CPScaleProcessRecord:
    pid: int
    name: str
    main_window_handle: int
    product_version: str
    file_version: str
    executable_path: str

    @property
    def coherent(self) -> bool:
        return bool(
            isinstance(self.pid, int)
            and not isinstance(self.pid, bool)
            and self.pid > 0
            and isinstance(self.name, str)
            and self.name
            and isinstance(self.main_window_handle, int)
            and not isinstance(self.main_window_handle, bool)
            and isinstance(self.product_version, str)
            and isinstance(self.file_version, str)
            and (self.product_version or self.file_version)
            and isinstance(self.executable_path, str)
            and self.executable_path
        )


@dataclass(frozen=True)
class CPScaleProcessEvidence:
    state: CPScaleCheckState
    processes: tuple[CPScaleProcessRecord, ...] = ()
    error: str = ""

    @property
    def passed_coherently(self) -> bool:
        return bool(
            self.state is CPScaleCheckState.PASSED
            and isinstance(self.processes, tuple)
            and self.processes
            and all(
                isinstance(item, CPScaleProcessRecord) and item.coherent
                for item in self.processes
            )
            and not self.error
        )


@dataclass(frozen=True)
class CPScaleLiveSessionIdentity:
    """Only provenance available before any backend contact."""

    run_identity: str
    started_at: datetime
    packet_tracer_version: str
    source_head: str
    source_tree: str
    branch: str
    upstream: str
    python_executable: str
    package_file: str
    loaded_namespace: str

    @property
    def coherent(self) -> bool:
        return bool(
            isinstance(self.run_identity, str)
            and self.run_identity
            and isinstance(self.started_at, datetime)
            and self.started_at.tzinfo is not None
            and isinstance(self.packet_tracer_version, str)
            and self.packet_tracer_version
            and isinstance(self.source_head, str)
            and self.source_head
            and isinstance(self.source_tree, str)
            and self.source_tree
            and isinstance(self.branch, str)
            and self.branch
            and isinstance(self.upstream, str)
            and self.upstream
            and isinstance(self.python_executable, str)
            and self.python_executable
            and isinstance(self.package_file, str)
            and self.package_file
            and self.loaded_namespace == "packet_tracer_mcp"
        )


@dataclass(frozen=True)
class CPScalePreflightResult:
    target: CPScaleCanonicalTargetContract
    runtime: CPScaleRuntimeEvidence
    import_isolation: CPScaleImportIsolationEvidence
    repository: CPScaleRepositoryEvidence
    process: CPScaleProcessEvidence
    identity: CPScaleLiveSessionIdentity | None
    issues: tuple[str, ...]

    @property
    def evidence_coherent(self) -> bool:
        identity = self.identity
        if not (
            isinstance(self.runtime, CPScaleRuntimeEvidence)
            and isinstance(
                self.import_isolation, CPScaleImportIsolationEvidence,
            )
            and isinstance(self.repository, CPScaleRepositoryEvidence)
            and isinstance(self.process, CPScaleProcessEvidence)
            and isinstance(identity, CPScaleLiveSessionIdentity)
            and isinstance(self.target, CPScaleCanonicalTargetContract)
        ):
            return False
        return bool(
            self.runtime.coherent
            and self.import_isolation.passed_coherently
            and self.repository.passed_coherently
            and self.process.passed_coherently
            and identity.coherent
            and identity.source_head == self.repository.head
            and identity.source_tree == self.repository.source_tree
            and identity.branch == self.repository.branch
            and identity.upstream == self.repository.upstream
            and identity.python_executable == self.runtime.python_executable
            and identity.package_file == self.runtime.package_file
            and identity.loaded_namespace == self.runtime.loaded_namespaces[0]
            and _processes_match_version_and_path(
                self.process.processes,
                identity.packet_tracer_version,
            )
        )

    @property
    def outcome(self) -> CPScalePreflightOutcome:
        checks = (
            self.import_isolation,
            self.repository,
            self.process,
        )
        all_passed = all(
            getattr(item, "state", None) is CPScaleCheckState.PASSED
            for item in checks
        )
        issues_are_typed = isinstance(self.issues, tuple) and all(
            isinstance(item, str) for item in self.issues
        )
        return (
            CPScalePreflightOutcome.ADMITTED
            if (
                issues_are_typed
                and not self.issues
                and all_passed
                and self.evidence_coherent
            )
            else CPScalePreflightOutcome.REJECTED
        )


def _processes_match_version_and_path(
    processes: tuple[CPScaleProcessRecord, ...],
    expected_version: str,
) -> bool:
    versions = {
        item.product_version or item.file_version
        for item in processes
    }
    paths = {item.executable_path for item in processes}
    return bool(
        expected_version
        and len(versions) == 1
        and all(value.startswith(expected_version) for value in versions)
        and len(paths) == 1
        and next(iter(paths), "")
    )
