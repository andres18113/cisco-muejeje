"""Coordinate the offline CP-SCALE LIVE preflight through explicit readers."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ..use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalTarget,
    CPScaleCanonicalTargetContract,
    canonical_cp_scale_target_contract,
)
from .contracts import (
    CPScaleCallObservabilityEvidence,
    CPScaleCheckState,
    CPScaleImportIsolationEvidence,
    CPScaleLiveAuthorizationEvidence,
    CPScaleLiveAuthorizationRequest,
    CPScaleLiveRequest,
    CPScaleLiveSessionIdentity,
    CPScalePreflightResult,
    CPScaleProcessEvidence,
    CPScaleProcessRecord,
    CPScaleRepositoryEvidence,
    CPScaleRuntimeEvidence,
)


@dataclass(frozen=True)
class CPScaleImportIsolationObservation:
    isolated: bool
    isolation_state: str
    detail: str = ""
    error: str = ""


@dataclass(frozen=True)
class CPScaleRepositoryObservation:
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


@dataclass(frozen=True)
class CPScaleProcessObservation:
    processes: tuple[CPScaleProcessRecord, ...] = ()
    error: str = ""


class CPScaleRuntimeReader(Protocol):
    def read(self) -> CPScaleRuntimeEvidence: ...


class CPScaleImportIsolationReader(Protocol):
    def read(self, governed_root: Path) -> CPScaleImportIsolationObservation: ...


class CPScaleRepositoryReader(Protocol):
    def read(self, governed_root: Path) -> CPScaleRepositoryObservation: ...


class CPScaleProcessReader(Protocol):
    def read(self) -> CPScaleProcessObservation: ...


class CPScaleCallObservabilityReader(Protocol):
    def read(
        self, packet_tracer_version: str,
    ) -> CPScaleCallObservabilityEvidence: ...


ProcessErrorPolicy = Callable[
    [Sequence[Mapping[str, object]], str],
    str,
]
TargetResolver = Callable[
    [CPScaleCanonicalTarget | str],
    CPScaleCanonicalTargetContract,
]


def process_record_mapping(record: CPScaleProcessRecord) -> dict[str, object]:
    """Retain every process field consumed or persisted by the current runner."""

    return {
        "ProcessName": record.name,
        "Id": record.pid,
        "MainWindowHandle": record.main_window_handle,
        "ProductVersion": record.product_version,
        "FileVersion": record.file_version,
        "Path": record.executable_path,
    }


class CPScaleLocalPreflight:
    """Apply CP-SCALE rules while keeping all local I/O behind narrow ports."""

    def __init__(
        self,
        *,
        governed_root: Path,
        runtime_reader: CPScaleRuntimeReader,
        import_reader: CPScaleImportIsolationReader,
        repository_reader: CPScaleRepositoryReader,
        process_reader: CPScaleProcessReader,
        call_observability_reader: CPScaleCallObservabilityReader,
        process_error_policy: ProcessErrorPolicy,
        expected_branch: str,
        expected_upstream: str,
        target_resolver: TargetResolver = canonical_cp_scale_target_contract,
    ) -> None:
        self._governed_root = governed_root
        self._runtime_reader = runtime_reader
        self._import_reader = import_reader
        self._repository_reader = repository_reader
        self._process_reader = process_reader
        self._call_observability_reader = call_observability_reader
        self._process_error_policy = process_error_policy
        self._expected_branch = expected_branch
        self._expected_upstream = expected_upstream
        self._target_resolver = target_resolver

    def inspect(
        self,
        request: CPScaleLiveRequest,
        *,
        run_identity: str,
        started_at: datetime,
    ) -> CPScalePreflightResult:
        target = self._target_resolver(request.target_stage)
        runtime = self._read_runtime()
        not_run_import = CPScaleImportIsolationEvidence(
            state=CPScaleCheckState.NOT_RUN,
        )
        not_run_repository = CPScaleRepositoryEvidence(
            state=CPScaleCheckState.NOT_RUN,
        )
        not_run_process = CPScaleProcessEvidence(
            state=CPScaleCheckState.NOT_RUN,
        )
        not_run_call_observability = CPScaleCallObservabilityEvidence(
            state=CPScaleCheckState.NOT_RUN,
        )

        request_error = _request_error(request, target)
        if request_error:
            return CPScalePreflightResult(
                target=target,
                runtime=runtime,
                import_isolation=not_run_import,
                repository=not_run_repository,
                process=not_run_process,
                identity=None,
                issues=(request_error,),
            )

        import_evidence = self._inspect_imports(runtime)
        if import_evidence.state is not CPScaleCheckState.PASSED:
            return CPScalePreflightResult(
                target=target,
                runtime=runtime,
                import_isolation=import_evidence,
                repository=not_run_repository,
                process=not_run_process,
                identity=None,
                issues=(import_evidence.error,),
            )

        repository = self._inspect_repository()
        authorization = _live_authorization_evidence(request, repository)
        repository_issues = _repository_issues(
            repository,
            expected_branch=self._expected_branch,
            expected_upstream=self._expected_upstream,
            expected_head=request.expected_head,
        )
        if repository_issues:
            repository = replace(repository, state=CPScaleCheckState.FAILED)
            return CPScalePreflightResult(
                target=target,
                runtime=runtime,
                import_isolation=import_evidence,
                repository=repository,
                process=not_run_process,
                identity=None,
                issues=repository_issues,
                live_authorization=authorization,
            )

        if (
            authorization is None
            or not authorization.passed_coherently
            or authorization.authorized_target is not target.target
        ):
            return CPScalePreflightResult(
                target=target,
                runtime=runtime,
                import_isolation=import_evidence,
                repository=repository,
                process=not_run_process,
                identity=None,
                issues=(
                    "LIVE authorization provenance is incomplete or "
                    "inconsistent after repository inspection.",
                ),
                live_authorization=authorization,
            )

        call_observability = not_run_call_observability
        if target.requires_call_observability:
            call_observability = self._inspect_call_observability(
                request.packet_tracer_version,
                target,
            )
            if call_observability.state is not CPScaleCheckState.PASSED:
                return CPScalePreflightResult(
                    target=target,
                    runtime=runtime,
                    import_isolation=import_evidence,
                    repository=repository,
                    process=not_run_process,
                    identity=None,
                    issues=(call_observability.error,),
                    live_authorization=authorization,
                    call_observability=call_observability,
                )

        identity = CPScaleLiveSessionIdentity(
            run_identity=run_identity,
            started_at=started_at,
            packet_tracer_version=request.packet_tracer_version,
            source_head=repository.head,
            source_tree=repository.source_tree,
            branch=repository.branch,
            upstream=repository.upstream,
            python_executable=runtime.python_executable,
            package_file=runtime.package_file,
            loaded_namespace=runtime.loaded_namespaces[0],
        )
        process = self._inspect_processes(request.packet_tracer_version)
        process_issues = (process.error,) if process.error else ()
        return CPScalePreflightResult(
            target=target,
            runtime=runtime,
            import_isolation=import_evidence,
            repository=repository,
            process=process,
            identity=identity,
            issues=process_issues,
            live_authorization=authorization,
            call_observability=call_observability,
        )

    def _inspect_call_observability(
        self,
        packet_tracer_version: str,
        target: CPScaleCanonicalTargetContract,
    ) -> CPScaleCallObservabilityEvidence:
        try:
            evidence = self._call_observability_reader.read(
                packet_tracer_version,
            )
        except Exception as exc:
            return CPScaleCallObservabilityEvidence(
                state=CPScaleCheckState.FAILED,
                required=True,
                packet_tracer_version=packet_tracer_version,
                error=(
                    "Call observability readiness failed: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
        mismatch = (
            not isinstance(evidence, CPScaleCallObservabilityEvidence)
            or not evidence.passed_coherently
            or evidence.packet_tracer_version != packet_tracer_version
            or evidence.expectation_results != target.call_expectation_results
            or evidence.provider_id != target.call_provider_id
            or evidence.call_control_models != target.call_control_models
            or evidence.phone_models != target.phone_models
        )
        if not mismatch:
            return evidence
        if (
            isinstance(evidence, CPScaleCallObservabilityEvidence)
            and evidence.state is CPScaleCheckState.FAILED
            and evidence.error
        ):
            return evidence
        detail = (
            evidence.error
            if isinstance(evidence, CPScaleCallObservabilityEvidence)
            else "reader returned an invalid evidence type"
        )
        message = (
            "FULL call observability evidence is unavailable, stale, "
            "foreign, or incoherent."
            + (f" {detail}" if detail else "")
        )
        if isinstance(evidence, CPScaleCallObservabilityEvidence):
            return replace(
                evidence,
                state=CPScaleCheckState.FAILED,
                error=message,
            )
        return CPScaleCallObservabilityEvidence(
            state=CPScaleCheckState.FAILED,
            required=True,
            packet_tracer_version=packet_tracer_version,
            error=message,
        )

    def _read_runtime(self) -> CPScaleRuntimeEvidence:
        try:
            return self._runtime_reader.read()
        except Exception as exc:
            return CPScaleRuntimeEvidence(
                error=f"Runtime provenance inspection failed: {type(exc).__name__}: {exc}",
            )

    def _inspect_imports(
        self,
        runtime: CPScaleRuntimeEvidence,
    ) -> CPScaleImportIsolationEvidence:
        if runtime.error:
            error = runtime.error
            return CPScaleImportIsolationEvidence(
                state=CPScaleCheckState.FAILED,
                isolation_state="INDETERMINATE",
                detail=error,
                error=error,
            )
        try:
            observation = self._import_reader.read(self._governed_root)
        except Exception as exc:
            error = f"Import isolation inspection failed: {type(exc).__name__}: {exc}"
            return CPScaleImportIsolationEvidence(
                state=CPScaleCheckState.FAILED,
                isolation_state="INDETERMINATE",
                detail=str(exc),
                error=error,
            )
        state = (
            CPScaleCheckState.PASSED
            if observation.isolated
            and observation.isolation_state == "ISOLATED"
            and observation.detail
            and not observation.error
            and runtime.coherent
            else CPScaleCheckState.FAILED
        )
        error = observation.error
        if state is CPScaleCheckState.FAILED and not error:
            error = (
                runtime.error
                or "Import isolation evidence is incomplete or inconsistent."
            )
        return CPScaleImportIsolationEvidence(
            state=state,
            isolation_state=observation.isolation_state,
            detail=observation.detail,
            error=error,
        )

    def _inspect_repository(self) -> CPScaleRepositoryEvidence:
        try:
            observation = self._repository_reader.read(self._governed_root)
        except Exception as exc:
            observation = CPScaleRepositoryObservation(
                error=f"Repository inspection failed: {type(exc).__name__}: {exc}",
            )
        return CPScaleRepositoryEvidence(
            state=CPScaleCheckState.PASSED,
            branch=observation.branch,
            upstream=observation.upstream,
            head=observation.head,
            upstream_head=observation.upstream_head,
            source_tree=observation.source_tree,
            dirty=observation.dirty,
            error=observation.error,
            dirty_error=observation.dirty_error,
            upstream_head_error=observation.upstream_head_error,
            source_tree_error=observation.source_tree_error,
        )

    def _inspect_processes(self, expected_version: str) -> CPScaleProcessEvidence:
        try:
            observation = self._process_reader.read()
        except Exception as exc:
            observation = CPScaleProcessObservation(
                error=f"Packet Tracer process inspection failed: {type(exc).__name__}: {exc}",
            )
        error = observation.error
        if not error:
            try:
                error = self._process_error_policy(
                    [process_record_mapping(item) for item in observation.processes],
                    expected_version,
                )
            except Exception as exc:
                error = (
                    "Packet Tracer process policy failed: "
                    f"{type(exc).__name__}: {exc}"
                )
        if not error and not all(item.coherent for item in observation.processes):
            error = "Packet Tracer process evidence is incomplete."
        return CPScaleProcessEvidence(
            state=(
                CPScaleCheckState.FAILED if error else CPScaleCheckState.PASSED
            ),
            processes=observation.processes,
            error=error,
        )


def _request_error(
    request: CPScaleLiveRequest,
    target: CPScaleCanonicalTargetContract,
) -> str:
    """Reject unauthorized target/retention combinations before readers."""

    authorization_error = _live_authorization_request_error(
        request,
        target,
    )
    if authorization_error:
        return authorization_error
    if (
        request.retain_on_full_verification
        and not target.allow_retention
    ):
        target_name = target.target.value.partition("-")[0].capitalize()
        return (
            f"{target_name} target cannot be combined with "
            "full-scale retention."
        )
    return ""


def _live_authorization_request_error(
    request: CPScaleLiveRequest,
    target: CPScaleCanonicalTargetContract,
) -> str:
    """Every canonical LIVE target needs its own explicit target and SHA."""

    authorization = request.live_authorization
    if authorization is None:
        return (
            f"LIVE target {target.target.value!r} requires an explicit "
            "target- and SHA-scoped authorization."
        )
    if not isinstance(authorization, CPScaleLiveAuthorizationRequest):
        return "LIVE authorization request has an invalid type."
    try:
        authorized_target = CPScaleCanonicalTarget(authorization.target)
    except (TypeError, ValueError):
        return (
            "LIVE authorization target is invalid; observed "
            f"{authorization.target!r}."
        )
    if target.target is not authorized_target:
        return (
            f"LIVE authorization for {authorized_target.value!r} does not "
            f"authorize requested target {target.target.value!r}."
        )
    authorized_sha = authorization.authorized_sha
    if not isinstance(authorized_sha, str) or not authorized_sha:
        return "LIVE authorization requires an explicit authorized SHA."
    if (
        len(authorized_sha) != 40
        or any(character not in "0123456789abcdef" for character in authorized_sha)
    ):
        return (
            "LIVE authorized SHA must be exactly 40 lowercase "
            "hexadecimal characters."
        )
    if authorized_sha != request.expected_head:
        return (
            f"LIVE authorized SHA {authorized_sha!r} does not match "
            f"request expected HEAD {request.expected_head!r}."
        )
    return ""


def _live_authorization_evidence(
    request: CPScaleLiveRequest,
    repository: CPScaleRepositoryEvidence,
) -> CPScaleLiveAuthorizationEvidence | None:
    authorization = request.live_authorization
    if not isinstance(authorization, CPScaleLiveAuthorizationRequest):
        return None
    return CPScaleLiveAuthorizationEvidence(
        authorized_target=CPScaleCanonicalTarget(authorization.target),
        authorized_sha=authorization.authorized_sha,
        expected_head=request.expected_head,
        repository_head=repository.head,
        upstream_head=repository.upstream_head,
        source_tree=repository.source_tree,
    )


def _repository_issues(
    evidence: CPScaleRepositoryEvidence,
    *,
    expected_branch: str,
    expected_upstream: str,
    expected_head: str,
) -> tuple[str, ...]:
    """Preserve the runner's repository gate ordering and multiplicity."""

    issues: list[str] = []
    if evidence.branch != expected_branch:
        issues.append(
            f"Expected branch {expected_branch!r}; observed {evidence.branch!r}.",
        )
    if evidence.upstream != expected_upstream:
        issues.append(
            f"Expected upstream {expected_upstream!r}; observed {evidence.upstream!r}.",
        )
    if expected_head and evidence.head != expected_head:
        issues.append(
            f"Expected HEAD {expected_head!r}; observed {evidence.head!r}.",
        )
    if evidence.error:
        issues.append(evidence.error)
    if evidence.dirty is True:
        issues.append("Live session requires a clean initial worktree.")
    elif evidence.dirty is None:
        issues.append(
            evidence.dirty_error or "Repository dirty state could not be proven.",
        )
    if evidence.head != evidence.upstream_head:
        issues.append(
            "Live session requires its exact initial HEAD pushed to upstream.",
        )
    if evidence.upstream_head and evidence.upstream_head_error:
        issues.append(evidence.upstream_head_error)
    if evidence.source_tree and evidence.source_tree_error:
        issues.append(evidence.source_tree_error)
    elif not evidence.source_tree:
        issues.append(
            evidence.source_tree_error or "Repository source tree could not be proven.",
        )
    return tuple(issues)
