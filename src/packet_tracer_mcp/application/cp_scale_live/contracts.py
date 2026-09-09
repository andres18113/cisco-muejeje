"""Typed CP-SCALE LIVE preflight and bounded stage execution contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalTarget,
    CPScaleCanonicalTargetContract,
)
from .process_identity import packet_tracer_version_path_error

from ..use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage, CPScaleCanonicalStageProjection,
    CPScaleSiteForwardingCheck,
)
from ..use_cases.compose_enterprise_reference import EnterpriseReferenceComposition
from ..use_cases.observe_serial_orientation import SerialOrientationResult
from ..use_cases.qualify_cp_scale_live import CanonicalMutationReplayAudit, CPScaleCanonicalVoiceEvidence
from ...domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult, ConfigurationApplicationResult,
)
from ...domain.enterprise.models.configuration import ConfigurationPhase
from ...domain.enterprise.models.control_plane_runtime import ControlPlaneApplicationResult
from ...domain.enterprise.models.deployment import DeploymentManifest, EnvironmentFingerprint
from ...domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentResult, PhysicalWorkspaceObservation,
)
from ...domain.enterprise.models.voice_runtime import VoiceApplicationResult
from ...domain.models.plans import TopologyPlan
from ...domain.models.typed_ping import TypedPingResult


@dataclass(frozen=True)
class CPScaleStageContinuity:
    """Caller-owned replacement snapshot; no runtime or session ownership."""

    previous_projection: CPScaleCanonicalStageProjection | None = None
    previous_configuration: ConfigurationApplicationResult | None = None
    previous_voice_action_results: tuple[ActionApplicationResult, ...] = ()
    previous_control_plane_action_results: tuple[ActionApplicationResult, ...] = ()
    verified_serial_topology: TopologyPlan | None = None
    verified_serial_manifest: DeploymentManifest | None = None
    last_workspace: PhysicalWorkspaceObservation | None = None


@dataclass(frozen=True)
class CPScaleObservationRecord:
    """One bounded read with named provenance and its raw observation evidence."""

    kind: str
    stage: CPScaleCanonicalStage
    provenance: str
    status: str
    evidence: dict[str, object]
    error: str = ""


@dataclass(frozen=True)
class CPScaleStageSecondaryFailure:
    """One later observation failure; never an acceptance or first-cause claim."""

    operation: str
    error: str


@dataclass(frozen=True)
class CPScaleDiagnosticRequest:
    projection: CPScaleCanonicalStageProjection
    voice: CPScaleVoiceStageResult
    realtime_failure_established: bool


@dataclass(frozen=True)
class CPScaleDiagnosticRecord:
    """Diagnostic evidence has no acceptance or primary-failure field."""

    stage: CPScaleCanonicalStage
    evidence: dict[str, object]
    initial_mode: str = ""
    final_mode: str = ""
    attempted_mutations: tuple[str, ...] = ()
    restoration_verified: bool = False
    error: str = ""
    authority: str = field(default="DIAGNOSTIC_ONLY", init=False)


@dataclass(frozen=True)
class CPScaleDhcpStatisticsTarget:
    device_name: str
    interface: str = ""
    segment_id: str = ""
    control_interface: str = ""
    control_segment_id: str = ""


@dataclass(frozen=True)
class CPScaleStageExecutionInput:
    projection: CPScaleCanonicalStageProjection
    composition: EnterpriseReferenceComposition
    deployment: PhysicalDeploymentResult
    delta_deployment: PhysicalDeploymentResult | None
    fingerprint: EnvironmentFingerprint
    packet_tracer_version: str
    continuity: CPScaleStageContinuity = field(default_factory=CPScaleStageContinuity)
    dhcp_statistics_target: CPScaleDhcpStatisticsTarget | None = None
    dhcp_statistics_baseline: CPScaleObservationRecord | None = None
    network_boundaries: tuple[CPScaleObservationRecord, ...] = ()
    site_forwarding_checks: tuple[CPScaleSiteForwardingCheck, ...] = ()

    @property
    def configuration_attempt_limit(self) -> int:
        """Initial application, one zero-mutation reread, optional Voice signal."""
        return 2 + int(bool(self.projection.voice and self.projection.voice.actions))

    @property
    def diagnostic_attempt_limit(self) -> int:
        return int(bool(self.projection.voice and self.projection.voice.actions))

    @property
    def secondary_failure_limit(self) -> int:
        """One error each for bindings, statistics and correlation after Voice."""
        return 3 * self.diagnostic_attempt_limit

    @property
    def required_observation_limit(self) -> int:
        """Plan-derived cap, not a count inferred from the adapter's output.

        Before/after physical (2), serial (1), STP (2), bindings (1),
        one observation per declared L2 phase, and Voice mode pair/exchange (3).
        Rereads authorize no mutation-phase callbacks. Workspace's two reads
        and forwarding attempts have their own typed result slots.
        """
        phases = {action.phase for action in self.projection.configuration.actions}
        l2_count = sum(phase in phases for phase in (
            ConfigurationPhase.L2_DEFINITIONS, ConfigurationPhase.L2_INTERFACES,
        ))
        return 6 + l2_count + 3 * self.diagnostic_attempt_limit


@dataclass(frozen=True)
class CPScaleVoiceStageResult:
    result: VoiceApplicationResult | None
    staged: bool
    error: str = ""
    reason: str = ""
    runtime_diagnostics: CPScaleObservationRecord | None = None


@dataclass(frozen=True)
class CPScaleMutationScope:
    configuration: tuple[str, ...]
    retained_configuration: tuple[str, ...]
    control_plane: tuple[str, ...]
    retained_control_plane: tuple[str, ...]
    voice: tuple[str, ...]
    retained_voice: tuple[str, ...]


@dataclass(frozen=True)
class CPScaleRereadScope:
    verified: bool
    mutation_action_ids: tuple[str, ...] = ()
    retained_action_ids: tuple[str, ...] = ()
    retained_deferred_voice_action_ids: tuple[str, ...] = ()
    error: str = ""


@dataclass(frozen=True)
class CPScaleConfigurationReport:
    contradictions: tuple[str, ...] = ()
    serial_interfaces: CPScaleObservationRecord | None = None
    reread_scope: CPScaleRereadScope | None = None
    acceptance_error: str | None = None


@dataclass(frozen=True)
class CPScaleVoiceLifecycleEvent:
    event: str
    sequence: int
    monotonic_ns: int
    recorded_at: datetime


@dataclass(frozen=True)
class CPScaleRealtimeWindow:
    before: CPScaleObservationRecord
    after: CPScaleObservationRecord | None = None
    verified: bool = False
    failure_reason: str = ""


@dataclass(frozen=True)
class CPScaleCoreForwardingObservation:
    source_device_name: str
    destination_ipv4: str
    attempts: tuple[TypedPingResult, ...]
    verified: bool


@dataclass(frozen=True)
class CPScaleSiteForwardingObservation:
    check: CPScaleSiteForwardingCheck
    attempts: tuple[TypedPingResult, ...]
    verified: bool


@dataclass(frozen=True)
class CPScaleForwardingResult:
    core_verified: bool
    core: tuple[CPScaleCoreForwardingObservation, ...]
    site: tuple[CPScaleSiteForwardingObservation, ...] = ()
    site_verified: bool | None = None
    first_failure: str = ""
    error: str = ""

    @property
    def verified(self) -> bool:
        return self.core_verified and self.site_verified is not False


@dataclass(frozen=True)
class CPScaleStageReport:
    """Closed reporting facts, never a second copy of application journals."""

    scope: CPScaleMutationScope | None
    configuration: CPScaleConfigurationReport | None
    voice: CPScaleVoiceStageResult | None
    lifecycle: tuple[CPScaleVoiceLifecycleEvent, ...]
    realtime: CPScaleRealtimeWindow | None
    canonical_voice: CPScaleCanonicalVoiceEvidence | None
    canonical_voice_error: str
    forwarding: CPScaleForwardingResult | None
    workspace_first: PhysicalWorkspaceObservation | None
    workspace_second: PhysicalWorkspaceObservation | None
    workspace_verified: bool | None
    site_forwarding_checks: tuple[CPScaleSiteForwardingCheck, ...]


@dataclass(frozen=True)
class CPScaleLiveStageResult:
    """Typed authority survives failures; evidence is a compatibility view only.

    The executor owns this snapshot. It keeps each application attempt once;
    `configuration` refers to the last attempt, it is never reconstructed from
    the reporting view. Retry bounds remain owned by the existing applicators.
    """

    stage: CPScaleCanonicalStage
    outcome: str
    projection: CPScaleCanonicalStageProjection
    deployment: PhysicalDeploymentResult
    delta_deployment: PhysicalDeploymentResult | None
    manifest: DeploymentManifest | None
    workspace: PhysicalWorkspaceObservation | None
    configuration: ConfigurationApplicationResult | None
    configuration_accepted: bool
    configuration_attempts: tuple[ConfigurationApplicationResult, ...]
    control_plane: ControlPlaneApplicationResult | None
    voice: VoiceApplicationResult | None
    replay_audit: CanonicalMutationReplayAudit | None
    orientation: SerialOrientationResult | None
    required_observations: tuple[CPScaleObservationRecord, ...]
    diagnostics: tuple[CPScaleDiagnosticRecord, ...]
    first_failed_boundary: str | None
    failure: str
    continuity: CPScaleStageContinuity
    report: CPScaleStageReport
    secondary_failures: tuple[CPScaleStageSecondaryFailure, ...] = ()

    @property
    def forwarding(self) -> tuple[CPScaleSiteForwardingObservation, ...]:
        return self.report.forwarding.site if self.report.forwarding else ()


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
    return not packet_tracer_version_path_error(
        tuple(
            (
                item.product_version,
                item.file_version,
                item.executable_path,
            )
            for item in processes
        ),
        expected_version,
    )
