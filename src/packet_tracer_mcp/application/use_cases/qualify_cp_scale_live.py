"""Progressive live qualification of the canonical CP-SCALE scenario.

This module only orchestrates the normal enterprise composition and execution
entry points. It does not own a second deployment, configuration, or cleanup
pipeline.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from ...domain.enterprise.models.deployment import EnvironmentFingerprint
from ...domain.enterprise.models.intent import EnterpriseIntent
from ...domain.enterprise.models.voice_plan import VoiceCapabilityProfile, VoiceIntent
from ...domain.enterprise.models.control_plane import ControlPlaneIntent
from ...domain.enterprise.scenarios.cp_scale import CPScalePoint, cp_scale_intent_for
from ...domain.enterprise.services.hardware_planner import HardwarePlanningPolicy
from ...infrastructure.execution.import_isolation_preflight import ImportIsolationPreflight
from ...infrastructure.persistence.capability_snapshot_store import CapabilitySnapshotStore
from ...shared.utils import resolve_within, safe_name_component
from .compose_enterprise_reference import (
    EnterpriseReferenceComposition,
    compose_enterprise_reference,
)
from .execute_enterprise_reference import (
    EnterpriseExecutionResult,
    EnterpriseExecutionStatus,
    EnterpriseRuntimes,
    execute_enterprise_reference,
)
from .qualify_cp_scale_offline import (
    cp_scale_control_plane_intent,
    cp_scale_voice_intent,
)


EXPECTED_BRANCH = "feature/runtime-ripv2"
EXPECTED_UPSTREAM = "personal/feature/runtime-ripv2"
_POINT_COUNTS = {
    CPScalePoint.A: (65, 3),
    CPScalePoint.B: (118, 6),
    CPScalePoint.C: (217, 12),
    CPScalePoint.D: (279, 17),
}


class CPScalePointStatus(str, Enum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    NOT_RUN = "not_run"


class CPScaleDimensionMetric(BaseModel):
    status: str
    count: int = 0
    message: str = ""


class CPScaleRepositoryState(BaseModel):
    branch: str = ""
    upstream: str = ""
    head: str = ""
    error: str = ""


@dataclass(frozen=True)
class CPScalePreparedPoint:
    intent: EnterpriseIntent
    composition: EnterpriseReferenceComposition
    control_plane_intent: ControlPlaneIntent | None = None
    voice_intent: VoiceIntent | None = None


@dataclass(frozen=True)
class CPScaleLivePointResult:
    point: CPScalePoint
    expected_workload_endpoints: int
    expected_access_points: int
    status: CPScalePointStatus
    repository_state: CPScaleRepositoryState | None = None
    observed_fingerprint: EnvironmentFingerprint | None = None
    prepared: CPScalePreparedPoint | None = None
    execution: EnterpriseExecutionResult | None = None
    dimensions: dict[str, CPScaleDimensionMetric] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def compact_summary(self) -> dict[str, object]:
        composition = self.prepared.composition if self.prepared else None
        return {
            "point": self.point.value,
            "status": self.status.value,
            "expected_workload_endpoints": self.expected_workload_endpoints,
            "expected_access_points": self.expected_access_points,
            "devices": len(composition.topology.devices) if composition and composition.topology else 0,
            "links": len(composition.topology.links) if composition and composition.topology else 0,
            "physical_topology_hash": (
                composition.topology.physical_identity_hash
                if composition and composition.topology else ""
            ),
            "execution": self.execution.compact_summary() if self.execution else None,
            "dimensions": {
                key: value.model_dump(mode="json")
                for key, value in sorted(self.dimensions.items())
            },
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class CPScaleLiveQualification:
    points: list[CPScaleLivePointResult]
    reliable_workload_envelope: int
    closure: str

    @property
    def full_scale_executed(self) -> bool:
        return any(
            item.point is CPScalePoint.D and item.status is CPScalePointStatus.COMPLETED
            for item in self.points
        )

    def compact_summary(self) -> dict[str, object]:
        return {
            "closure": self.closure,
            "reliable_workload_envelope": self.reliable_workload_envelope,
            "full_scale_executed": self.full_scale_executed,
            "points": [item.compact_summary() for item in self.points],
        }


PointPreparer = Callable[[CPScalePoint, EnterpriseIntent], CPScalePreparedPoint]
ExecutionUseCase = Callable[..., EnterpriseExecutionResult]


def qualify_cp_scale_progressive(
    runtimes: EnterpriseRuntimes,
    *,
    environment_fingerprint: EnvironmentFingerprint,
    environment_probe: Callable[[], EnvironmentFingerprint],
    repository_state_provider: Callable[[], CPScaleRepositoryState],
    import_preflight: ImportIsolationPreflight,
    packet_tracer_version: str,
    capability_store: CapabilitySnapshotStore | None = None,
    voice_capabilities: dict[str, VoiceCapabilityProfile] | None = None,
    policy: HardwarePlanningPolicy | None = None,
    expected_branch: str = EXPECTED_BRANCH,
    expected_upstream: str = EXPECTED_UPSTREAM,
    point_preparer: PointPreparer | None = None,
    execution_use_case: ExecutionUseCase = execute_enterprise_reference,
) -> CPScaleLiveQualification:
    """Run A→D, stopping at the first unproven gate or failed scale point."""
    prepare = point_preparer or _default_preparer(
        packet_tracer_version=packet_tracer_version,
        capability_store=capability_store,
        policy=policy,
        voice_capabilities=voice_capabilities,
    )
    results: list[CPScaleLivePointResult] = []
    reliable_envelope = 0
    stopped = False

    for point in CPScalePoint:
        workload_count, access_points = _POINT_COUNTS[point]
        if stopped:
            results.append(_not_run(point, workload_count, access_points))
            continue

        repository_state = repository_state_provider()
        gate_errors = _repository_gate_errors(
            repository_state, expected_branch, expected_upstream,
        )
        try:
            observed_fingerprint = environment_probe()
        except Exception as exc:
            observed_fingerprint = None
            gate_errors.append(f"Environment fingerprint probe failed: {exc}")
        if (
            observed_fingerprint is not None
            and observed_fingerprint.semantic_hash != environment_fingerprint.semantic_hash
        ):
            gate_errors.append(
                "Current backend fingerprint does not match the fingerprint supplied "
                "to the mutating enterprise execution."
            )
        if gate_errors:
            results.append(CPScaleLivePointResult(
                point=point,
                expected_workload_endpoints=workload_count,
                expected_access_points=access_points,
                status=CPScalePointStatus.BLOCKED,
                repository_state=repository_state,
                observed_fingerprint=observed_fingerprint,
                dimensions=_not_run_dimensions("pre-mutation gate blocked"),
                errors=gate_errors,
            ))
            stopped = True
            continue

        intent = cp_scale_intent_for(point)
        prepared = prepare(point, intent)
        preparation_errors = list(prepared.composition.issues)
        topology_summary = prepared.composition.topology_summary
        if topology_summary is None:
            preparation_errors.append("Typed topology compile summary is unavailable.")
        else:
            if topology_summary.workload_endpoints != workload_count:
                preparation_errors.append(
                    f"Scale point {point.value} compiled "
                    f"{topology_summary.workload_endpoints} workloads; expected "
                    f"{workload_count}."
                )
            if topology_summary.access_points != access_points:
                preparation_errors.append(
                    f"Scale point {point.value} compiled "
                    f"{topology_summary.access_points} access points; expected "
                    f"{access_points}."
                )
        if (
            not prepared.composition.valid
            or prepared.composition.enterprise is None
            or prepared.composition.topology is None
            or prepared.control_plane_intent is None
            or prepared.voice_intent is None
            or preparation_errors
        ):
            preparation_errors = preparation_errors or [
                "Typed structural composition did not produce topology, control-plane, "
                "and voice intents."
            ]
            results.append(CPScaleLivePointResult(
                point=point,
                expected_workload_endpoints=workload_count,
                expected_access_points=access_points,
                status=CPScalePointStatus.BLOCKED,
                repository_state=repository_state,
                observed_fingerprint=observed_fingerprint,
                prepared=prepared,
                dimensions=_not_run_dimensions("typed preparation blocked"),
                errors=preparation_errors,
            ))
            stopped = True
            continue

        execution = execution_use_case(
            intent,
            runtimes,
            prepared.control_plane_intent,
            environment_fingerprint=environment_fingerprint,
            import_preflight=import_preflight,
            packet_tracer_version=packet_tracer_version,
            capability_store=capability_store,
            voice_intent=prepared.voice_intent,
            voice_capabilities=voice_capabilities,
            deployment_id=f"cp-scale-{point.value.casefold()}",
            require_empty_workspace=True,
            policy=policy,
        )
        completed = (
            execution.status is EnterpriseExecutionStatus.COMPLETED
            and execution.cleanup_confirmed_twice is True
        )
        status = CPScalePointStatus.COMPLETED if completed else CPScalePointStatus.FAILED
        results.append(CPScaleLivePointResult(
            point=point,
            expected_workload_endpoints=workload_count,
            expected_access_points=access_points,
            status=status,
            repository_state=repository_state,
            observed_fingerprint=observed_fingerprint,
            prepared=prepared,
            execution=execution,
            dimensions=_execution_dimensions(execution),
            errors=list(execution.errors),
        ))
        if completed:
            reliable_envelope = workload_count
        else:
            stopped = True

    # Wireless association and IoT function remain deliberately unqualified,
    # so exact catalog identity alone cannot emit FULL_TARGET_VERIFIED.
    return CPScaleLiveQualification(
        points=results,
        reliable_workload_envelope=reliable_envelope,
        closure="MECHANICALLY_VERIFIED_ENVELOPE",
    )


def read_git_repository_state(root: Path) -> CPScaleRepositoryState:
    """Read the exact branch/upstream/HEAD without mutating repository state."""
    try:
        branch = _git(root, "branch", "--show-current")
        upstream = _git(root, "rev-parse", "--abbrev-ref", "@{upstream}")
        head = _git(root, "rev-parse", "HEAD")
        return CPScaleRepositoryState(branch=branch, upstream=upstream, head=head)
    except (OSError, subprocess.CalledProcessError) as exc:
        return CPScaleRepositoryState(error=str(exc))


def write_cp_scale_live_artifacts(
    qualification: CPScaleLiveQualification,
    base_dir: Path,
    run_name: str,
) -> Path:
    """Write full typed live results beneath a path-confined evidence directory."""
    run_dir = resolve_within(base_dir, safe_name_component(run_name, "live"))
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = resolve_within(run_dir, "summary.json")
    summary.write_text(
        json.dumps(qualification.compact_summary(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    for point in qualification.points:
        target = resolve_within(run_dir, f"point-{point.point.value.casefold()}.json")
        target.write_text(
            json.dumps(_jsonable(point), indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
    return run_dir


def _default_preparer(
    *,
    packet_tracer_version: str,
    capability_store: CapabilitySnapshotStore | None,
    policy: HardwarePlanningPolicy | None,
    voice_capabilities: dict[str, VoiceCapabilityProfile] | None,
) -> PointPreparer:
    def prepare(point: CPScalePoint, intent: EnterpriseIntent) -> CPScalePreparedPoint:
        composition = compose_enterprise_reference(
            intent,
            packet_tracer_version=packet_tracer_version,
            capability_store=capability_store,
            policy=policy,
        )
        if composition.enterprise is None or composition.topology is None:
            return CPScalePreparedPoint(intent=intent, composition=composition)
        return CPScalePreparedPoint(
            intent=intent,
            composition=composition,
            control_plane_intent=cp_scale_control_plane_intent(
                composition.enterprise, composition.topology,
            ),
            voice_intent=cp_scale_voice_intent(composition.topology),
        )

    return prepare


def _repository_gate_errors(
    state: CPScaleRepositoryState,
    expected_branch: str,
    expected_upstream: str,
) -> list[str]:
    errors = [state.error] if state.error else []
    if state.branch != expected_branch:
        errors.append(f"Expected branch {expected_branch!r}; observed {state.branch!r}.")
    if state.upstream != expected_upstream:
        errors.append(f"Expected upstream {expected_upstream!r}; observed {state.upstream!r}.")
    if not state.head:
        errors.append("Repository HEAD could not be proven.")
    return errors


def _execution_dimensions(
    execution: EnterpriseExecutionResult,
) -> dict[str, CPScaleDimensionMetric]:
    return {
        "physical": CPScaleDimensionMetric(
            status="executed" if execution.deployment is not None else "not_run",
            count=len(execution.deployment.item_results) if execution.deployment else 0,
        ),
        "configuration": CPScaleDimensionMetric(
            status=(
                execution.configuration_result.status.value
                if execution.configuration_result else "not_run"
            ),
            count=(
                len(execution.configuration_result.action_results)
                if execution.configuration_result else 0
            ),
        ),
        "voice": CPScaleDimensionMetric(
            status=execution.voice_result.status.value if execution.voice_result else "not_run",
            count=len(execution.voice_result.action_results) if execution.voice_result else 0,
        ),
        "control_plane": CPScaleDimensionMetric(
            status=(
                execution.control_plane_result.status.value
                if execution.control_plane_result else "not_run"
            ),
            count=(
                len(execution.control_plane_result.action_results)
                if execution.control_plane_result else 0
            ),
        ),
        "cleanup": CPScaleDimensionMetric(
            status="verified" if execution.cleanup_confirmed_twice is True else "failed",
            count=2 if execution.cleanup_confirmed_twice is True else 0,
        ),
        "wireless_association": CPScaleDimensionMetric(
            status="not_run", count=0,
            message="No registered governed association primitive is claimed.",
        ),
        "iot_function": CPScaleDimensionMetric(
            status="not_run", count=0,
            message=(
                "Exact catalog model identity is structural; IoT function "
                "remains unqualified."
            ),
        ),
    }


def _not_run_dimensions(message: str) -> dict[str, CPScaleDimensionMetric]:
    return {
        name: CPScaleDimensionMetric(status="not_run", count=0, message=message)
        for name in (
            "physical", "configuration", "voice", "control_plane", "cleanup",
            "wireless_association", "iot_function",
        )
    }


def _not_run(
    point: CPScalePoint,
    workload_count: int,
    access_points: int,
) -> CPScaleLivePointResult:
    return CPScaleLivePointResult(
        point=point,
        expected_workload_endpoints=workload_count,
        expected_access_points=access_points,
        status=CPScalePointStatus.NOT_RUN,
        dimensions=_not_run_dimensions("an earlier progressive scale point stopped"),
    )


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _jsonable(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {
            item.name: _jsonable(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
