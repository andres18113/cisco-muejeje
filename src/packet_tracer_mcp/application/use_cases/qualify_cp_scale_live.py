"""Progressive live qualification of the canonical CP-SCALE scenario.

This module only orchestrates the normal enterprise composition and execution
entry points. It does not own a second deployment, configuration, or cleanup
pipeline.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from ...domain.enterprise.models.capabilities import CapabilityStatus
from ...domain.enterprise.models.configuration import (
    ConfigurationPlan,
    ConfigureAccessPort,
    VerificationKind,
)
from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
    FieldVerificationStatus,
)
from ...domain.enterprise.models.deployment import EnvironmentFingerprint
from ...domain.enterprise.models.discovery import (
    BackendVersionProvenance,
    CapabilitySnapshot,
    CleanupStatus,
    ModelIdentityStatus,
    ProbeExecutionStatus,
    inventory_restoration_matches,
)
from ...domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...domain.enterprise.models.intent import EnterpriseIntent
from ...domain.enterprise.models.voice_plan import (
    VoiceCapabilityProfile,
    VoiceIntent,
    VoicePlan,
)
from ...domain.enterprise.models.voice_runtime import VoiceApplicationResult
from ...domain.enterprise.models.control_plane import ControlPlaneIntent
from ...domain.enterprise.scenarios.cp_scale import CPScalePoint, cp_scale_intent_for
from ...domain.enterprise.services.hardware_planner import HardwarePlanningPolicy
from ...domain.models.plans import TopologyPlan
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


def canonical_required_capability_probes(
    composition: EnterpriseReferenceComposition,
) -> dict[str, list[str]]:
    """Derive the registered logical probes required by the canonical plan."""

    from .capability_discovery import CapabilityProbeRegistry

    if composition.topology is None or composition.configuration is None:
        raise ValueError(
            "Canonical capability prequalification requires complete product plans."
        )
    known = set(CapabilityProbeRegistry().known_capabilities)
    models_by_device = {
        item.id: item.model for item in composition.topology.devices
    }
    required: dict[str, set[str]] = {}
    for action in composition.configuration.actions:
        capability = action.required_capability
        if not capability or capability.startswith("endpoint_"):
            continue
        if capability not in known:
            raise ValueError(
                f"No registered typed capability probe exists for {capability!r}."
            )
        model = models_by_device.get(action.device_id)
        if not model:
            raise ValueError(
                f"Configuration target {action.device_id!r} has no topology model."
            )
        required.setdefault(model, set()).add(capability)
    # E7 gates every voice action on a model capability, and an unmeasured one
    # skips the action rather than attempting it. Prequalifying the call-control
    # hosts is what turns that fail-closed default into evidence -- otherwise a
    # stage would apply no voice at all and still look like it had.
    for control in getattr(composition.voice, "call_controls", None) or []:
        model = models_by_device.get(control.host_device_id)
        if not model:
            raise ValueError(
                f"Call-control host {control.host_device_id!r} has no topology model."
            )
        if "supports_cme" not in known:
            raise ValueError(
                "No registered typed capability probe exists for 'supports_cme'."
            )
        required.setdefault(model, set()).add("supports_cme")
    return {
        model: sorted(capabilities)
        for model, capabilities in sorted(required.items())
    }


def canonical_capability_probe_error(
    snapshot: CapabilitySnapshot,
    *,
    model: str,
    capabilities: list[str],
    packet_tracer_version: str,
) -> str:
    """Reject any capability session that is not exact, clean and VERIFIED."""

    if snapshot.packet_tracer_version != packet_tracer_version:
        return (
            "Capability probe Packet Tracer version mismatch: expected "
            f"{packet_tracer_version!r}, observed {snapshot.packet_tracer_version!r}."
        )
    if snapshot.backend_version_provenance is BackendVersionProvenance.UNKNOWN:
        return "Capability probe backend version provenance is UNKNOWN."
    if snapshot.session.session.cleanup_status is not CleanupStatus.CLEAN:
        return (
            "Capability probe cleanup is "
            f"{snapshot.session.session.cleanup_status.value}."
        )
    if snapshot.session.cleanup_failed:
        return "Capability probe cleanup retained failed disposable objects."
    if (
        snapshot.inventory_restored is not True
        or not inventory_restoration_matches(
            snapshot.initial_inventory_hash, snapshot.final_inventory_hash,
        )
        or not snapshot.reusable
    ):
        return "Capability probe did not prove exact inventory restoration."

    identities = [
        item for item in snapshot.session.devices
        if item.identity.canonical_id == model
        and item.identity.status is ModelIdentityStatus.CATALOG_MATCHED
        and item.observed
    ]
    if len(identities) != 1:
        return f"Capability probe did not bind one observed catalog identity for {model}."

    results_by_capability = {
        capability: [
            item for item in snapshot.session.results
            if item.model == model and item.capability == capability
        ]
        for capability in capabilities
    }
    for capability, results in results_by_capability.items():
        if len(results) != 1:
            return (
                f"Capability probe result inventory for {model}:{capability} "
                f"contained {len(results)} result(s)."
            )
        result = results[0]
        if result.status is not CapabilityStatus.SUPPORTED:
            return (
                f"Capability probe {model}:{capability} is "
                f"{result.status.value}."
            )
        if (
            result.execution_status is not ProbeExecutionStatus.VERIFIED
            or not result.verified
            or result.packet_tracer_version != packet_tracer_version
            or result.evidence() is None
        ):
            return (
                f"Capability probe {model}:{capability} lacks exact VERIFIED evidence."
            )
    return ""


class CPScalePointStatus(str, Enum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    NOT_RUN = "not_run"


class CPScaleFinalDisposition(str, Enum):
    """What a fully verified canonical workspace does at the final gate."""

    CLEANUP = "cleanup"
    RETAIN = "retain"


class CPScaleVoiceAccessGroupEvidence(BaseModel):
    switch: str
    voice_vlan_id: int
    expected_interfaces: list[str] = Field(default_factory=list)
    verified_fwd_interfaces: list[str] = Field(default_factory=list)
    missing_interfaces: list[str] = Field(default_factory=list)
    non_fwd_interfaces: dict[str, str] = Field(default_factory=dict)
    sample_count: int = 0
    elapsed_ms: int = 0
    terminal_authority: str = "UNOBSERVABLE"
    terminal_failure_dimension: str = "GROUP_EVIDENCE_MISSING"
    status: ActionExecutionStatus = ActionExecutionStatus.UNOBSERVABLE


class CPScaleFailedPhoneIdentity(BaseModel):
    phone_id: str
    phone_name: str = ""
    stage: str
    site_id: str = ""
    switch: str = ""
    port: str = ""
    voice_vlan_id: int = 0
    ipv4: str = ""
    binding_state: str = "UNOBSERVABLE"
    sccp_state: str = "UNOBSERVABLE"
    first_contradicted_boundary: str


class CPScaleCanonicalVoiceEvidence(BaseModel):
    stage: str
    expected_phone_count: int = 0
    network_foundation_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    voice_bootstrap_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    voice_signal_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    phone_access_group_count: int = 0
    phone_access_fwd_expected: int = 0
    phone_access_fwd_verified: int = 0
    phone_access_fwd_failed: int = 0
    phone_access_fwd_unobservable: int = 0
    phone_access_fwd_groups: list[CPScaleVoiceAccessGroupEvidence] = Field(
        default_factory=list,
    )
    phone_access_fwd_max_duration_ms: int = 0
    lifecycle_events: list[str] = Field(default_factory=list)
    registration_started_after_fwd_barrier: bool | None = None
    voice_svi_present_count: int = 0
    dhcp_enabled_count: int = 0
    addressed_count: int = 0
    registration_identity_errors: list[str] = Field(default_factory=list)
    binding_evidence_complete: bool = False
    voice_dhcp_binding_count: int = 0
    matching_binding_count: int = 0
    sccp_registered_count: int = 0
    sccp_failed_count: int = 0
    sccp_unobservable_count: int = 0
    failed_phone_identities: list[CPScaleFailedPhoneIdentity] = Field(
        default_factory=list,
    )
    first_contradicted_boundary: str = "NOT_ESTABLISHED"
    complete: bool = False


class CPScaleEvidenceArchive(BaseModel):
    run_identity: str
    phase: str
    path: Path
    sha256: str


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


def canonical_bridge_polling_error(status: dict) -> str:
    """Say WHICH authenticated-bridge failure this is, or "" if there is none.

    Three states reach the same hard stop and want three different actions, and
    one sentence that named none of them cost a diagnosis every time:

    * no request arrived at all -- the webview's command poll is dead. Its
      status interval keeps running, so Packet Tracer still looks healthy from
      the inside and waiting does not help.
    * requests arrived and were rejected -- a token mismatch, and the token id
      is the thing to compare across runs before touching anything.
    * requests arrived and then stopped -- a stall, which is not an absence and
      must not be reported as one.

    The file bridge is alive in every one of them. It runs in the Script Engine
    with no window at all, while this channel lives in the webview, so its
    health is not evidence about this channel and is stated as such wherever it
    is known.
    """
    if status.get("connected"):
        return ""
    last_poll = status.get("last_poll_ago")
    unauthorized = int(status.get("unauth_count") or 0)
    token_id = str(status.get("token_id") or "")
    if unauthorized > 0:
        paths = ", ".join(str(item) for item in (status.get("unauth_paths") or []))
        reason = (
            f"{unauthorized} request(s) were rejected as unauthorized"
            + (f" on {paths}" if paths else "")
            + f"; the bridge is serving token id {token_id!r}, so compare it "
            "against the one the extension read before changing either."
        )
    elif last_poll is None:
        reason = (
            "no request reached the bridge at all, so the extension is not "
            "polling: re-enable MCP BUILDER in Packet Tracer. Waiting does not "
            "help -- a dead command poll leaves the status poll running, so "
            "nothing looks wrong from inside Packet Tracer."
        )
    else:
        reason = (
            f"the extension last polled {last_poll}s ago and has gone quiet; "
            "this is a stalled poll, not an absent one."
        )
    if "file_bridge_alive" in status:
        reason += (
            " The file bridge is "
            + ("alive" if status.get("file_bridge_alive") else "down")
            + ", which says nothing about this channel: it runs in the Script "
            "Engine with no window, and this one lives in the webview."
        )
    return reason


def canonical_checkpoint_repository_error(
    *,
    branch: str,
    upstream: str,
    head: str,
    upstream_head: str,
    dirty: bool,
    governed_source_changed: bool,
) -> str:
    """Return why a retained LIVE checkpoint may not advance."""

    errors: list[str] = []
    if branch != EXPECTED_BRANCH:
        errors.append(f"Expected branch {EXPECTED_BRANCH!r}; observed {branch!r}.")
    if upstream != EXPECTED_UPSTREAM:
        errors.append(
            f"Expected upstream {EXPECTED_UPSTREAM!r}; observed {upstream!r}."
        )
    if dirty:
        errors.append("Checkpoint worktree is not clean.")
    if not head or head != upstream_head:
        errors.append("Checkpoint HEAD is not pushed to the configured upstream.")
    if governed_source_changed:
        errors.append("Governed source changed after the LIVE process started.")
    return " ".join(errors)


def canonical_cleanup_restoration_error(
    baseline: PhysicalWorkspaceObservation,
    first: PhysicalWorkspaceObservation,
    second: PhysicalWorkspaceObservation,
) -> str:
    """Require two fresh restorations of the exact pre-session workspace."""

    if not physical_workspace_restoration_matches(baseline, first):
        return "First cleanup observation did not restore the exact baseline."
    if not physical_workspace_restoration_matches(baseline, second):
        return "Second cleanup observation did not restore the exact baseline."
    return ""


def canonical_stage_resume_error(
    verified_snapshot: PhysicalWorkspaceObservation,
    current: PhysicalWorkspaceObservation,
    topology: TopologyPlan,
) -> str:
    """Refuse a post-checkpoint mutation when retained physical state drifted."""

    if not physical_workspace_restoration_matches(verified_snapshot, current):
        return (
            "Retained canonical workspace no longer matches the last VERIFIED "
            "snapshot."
        )
    return canonical_stage_workspace_error(current, topology)


def canonical_stage_configuration_error(
    plan: ConfigurationPlan,
    result: ConfigurationApplicationResult,
    *,
    allow_deferred_voice_signal: bool = False,
) -> str:
    """Accept only the exact measured CP-SCALE E5 read-back ceilings."""

    identity_errors: list[str] = []
    if result.config_plan_id != plan.id:
        identity_errors.append("configuration plan id")
    if result.config_semantic_hash != plan.semantic_hash:
        identity_errors.append("configuration semantic hash")
    if result.source_topology_hash != plan.source_topology_hash:
        identity_errors.append("source topology hash")
    if identity_errors:
        return "Configuration result mismatched " + ", ".join(identity_errors) + "."
    if result.preflight_errors:
        return "Configuration preflight reported: " + "; ".join(result.preflight_errors)

    pending_voice_ids: set[str] = set()
    if allow_deferred_voice_signal:
        barrier = result.voice_signal_barrier
        if (
            barrier is None
            or barrier.foundation_status is not ActionExecutionStatus.VERIFIED
            or barrier.signal_status is not ActionExecutionStatus.INTENDED
        ):
            return (
                "Configuration did not retain a VERIFIED network foundation "
                "with Voice signalling pending bootstrap."
            )
        pending_voice_ids = set(barrier.deferred_action_ids)

    expected_action_ids = Counter(item.id for item in plan.actions)
    observed_action_ids = Counter(item.action_id for item in result.action_results)
    if expected_action_ids != observed_action_ids:
        return "Configuration action result inventory did not match the typed plan."
    mutation_action_ids = Counter(result.mutation_action_ids)
    retained_action_ids = Counter(result.retained_action_ids)
    if (
        any(count != 1 for count in mutation_action_ids.values())
        or any(count != 1 for count in retained_action_ids.values())
        or mutation_action_ids & retained_action_ids
        or mutation_action_ids + retained_action_ids != expected_action_ids
    ):
        return (
            "Configuration mutation and retained action inventories did not "
            "partition the typed plan."
        )
    allowed_actions = {
        ActionExecutionStatus.APPLIED,
        ActionExecutionStatus.NO_OP,
        ActionExecutionStatus.REASSERTED,
    }
    invalid_actions = sorted(
        f"{item.action_id}:{item.status.value}"
        for item in result.action_results
        if (
            item.status not in allowed_actions
            and not (
                item.action_id in pending_voice_ids
                and item.status is ActionExecutionStatus.PARTIAL
            )
        )
    )
    if invalid_actions:
        return "Configuration action status is fail-closed: " + ", ".join(invalid_actions)

    expectations = {item.id: item for item in plan.verification_expectations}
    if len(expectations) != len(plan.verification_expectations):
        return "Configuration plan contains duplicate verification identifiers."
    if Counter(expectations.keys()) != Counter(
        item.expectation_id for item in result.verification_results
    ):
        return "Configuration verification inventory did not match the typed plan."

    ceiling_present = False
    for item in result.verification_results:
        expectation = expectations[item.expectation_id]
        if expectation.action_id in pending_voice_ids:
            ceiling_present = True
            if (
                item.status is not ActionExecutionStatus.PARTIAL
                or item.fresh_evidence
                or item.fields
                or "pending" not in item.message.casefold()
            ):
                return (
                    f"Deferred Voice verification {item.expectation_id!r} "
                    "did not remain explicitly PARTIAL and pending bootstrap."
                )
            continue
        invalid_fields = sorted(
            f"{name}:{status.value}"
            for name, status in item.fields.items()
            if status in {
                FieldVerificationStatus.UNKNOWN,
                FieldVerificationStatus.FAILED,
            }
        )
        if invalid_fields:
            return (
                f"Configuration verification {item.expectation_id!r} contains "
                "fail-closed UNKNOWN/FAILED field evidence: "
                + ", ".join(invalid_fields)
            )

        if expectation.kind is VerificationKind.DHCP_POOL:
            ceiling_present = True
            if (
                item.status is not ActionExecutionStatus.UNOBSERVABLE
                or item.fresh_evidence
                or item.evidence_method != "runtime_observability_limit"
                or set(item.fields) != set(expectation.expected)
                or set(item.fields.values()) != {FieldVerificationStatus.UNOBSERVABLE}
            ):
                return (
                    f"DHCP verification {item.expectation_id!r} exceeded or "
                    "departed from its exact UNOBSERVABLE getter ceiling."
                )
            continue

        if expectation.kind is VerificationKind.ENDPOINT_ADDRESSING:
            ceiling_present = True
            if item.evidence_method == "structured_endpoint_getters_absent":
                # Measured on build 9.0.1.0858: an AccessPoint-PT brings both
                # `Port 0` and `Port 1` up and powered and exposes no address
                # getter on either, nor at device level. It bridges rather than
                # hosts, so its designed management address can be applied and
                # can never be read back -- the same standing observability
                # limit the DHCP-pool ceiling already accepts, and admitted here
                # on the same terms: every field UNOBSERVABLE, nothing claimed.
                #
                # Keyed on this exact evidence method so that an interface which
                # was never found stays a failure rather than being absorbed.
                if (
                    item.status is not ActionExecutionStatus.UNOBSERVABLE
                    or item.fresh_evidence
                    or set(item.fields) != set(expectation.expected)
                    or set(item.fields.values()) != {
                        FieldVerificationStatus.UNOBSERVABLE
                    }
                ):
                    return (
                        f"Endpoint verification {item.expectation_id!r} claimed "
                        "an absent address channel without staying entirely "
                        "unobserved."
                    )
                continue
            expected_fields = {
                "ipv4": FieldVerificationStatus.VERIFIED,
                "netmask": FieldVerificationStatus.VERIFIED,
                "gateway": FieldVerificationStatus.UNOBSERVABLE,
                "dns": FieldVerificationStatus.UNOBSERVABLE,
            }
            if (
                item.status is not ActionExecutionStatus.PARTIAL
                or not item.fresh_evidence
                or item.evidence_method != "structured_endpoint_getters"
                or item.fields != expected_fields
            ):
                return (
                    f"Endpoint verification {item.expectation_id!r} departed "
                    "from the exact IP/mask VERIFIED and gateway/DNS "
                    "UNOBSERVABLE ceiling."
                )
            continue

        if expectation.kind is VerificationKind.TRUNK:
            expected_fields = {
                "interface": FieldVerificationStatus.VERIFIED,
                "status": FieldVerificationStatus.VERIFIED,
                "allowed_vlans": FieldVerificationStatus.VERIFIED,
                "active_vlans": FieldVerificationStatus.VERIFIED,
                "forwarding_vlans": FieldVerificationStatus.VERIFIED,
            }
            if (
                item.status is not ActionExecutionStatus.VERIFIED
                or not item.fresh_evidence
                or item.evidence_method != "fresh_show_interfaces_trunk"
                or item.fields != expected_fields
            ):
                return (
                    f"Trunk verification {item.expectation_id!r} departed "
                    "from the exact allowed, active, and forwarding VLAN "
                    "traversal proof."
                )
            continue

        if (
            item.status is not ActionExecutionStatus.VERIFIED
            or not item.fresh_evidence
            or any(
                status is not FieldVerificationStatus.VERIFIED
                for status in item.fields.values()
            )
        ):
            return (
                f"Configuration verification {item.expectation_id!r} is "
                f"{item.status.value}; only fresh VERIFIED evidence is allowed "
                "outside the governed ceilings."
            )

    expected_status = (
        ConfigurationApplicationStatus.PARTIAL
        if ceiling_present else ConfigurationApplicationStatus.VERIFIED
    )
    if result.status is not expected_status:
        return (
            f"Configuration aggregate is {result.status.value}; expected the "
            f"truthful {expected_status.value} state for this stage."
        )
    return ""


def canonical_configuration_retryable_operational_unknown(
    plan: ConfigurationPlan,
    result: ConfigurationApplicationResult,
    *,
    allow_deferred_voice_signal: bool = False,
) -> bool:
    """Whether one typed re-read can close only L3 carrier/protocol UNKNOWNs.

    The caller must first prove convergence independently and then invoke the
    normal typed applicator again.  This helper never promotes the original
    evidence; it only identifies the narrow transient shape worth re-reading.
    """

    expectations = {item.id: item for item in plan.verification_expectations}
    candidate = result.model_copy(deep=True)
    found = False
    for item in candidate.verification_results:
        expectation = expectations.get(item.expectation_id)
        unknown_fields = {
            name for name, status in item.fields.items()
            if status is FieldVerificationStatus.UNKNOWN
        }
        failed_fields = {
            name for name, status in item.fields.items()
            if status is FieldVerificationStatus.FAILED
        }
        if failed_fields:
            return False
        if not unknown_fields:
            continue
        if (
            expectation is None
            or expectation.kind is not VerificationKind.L3_INTERFACE
            or not unknown_fields <= {"status", "protocol"}
        ):
            return False
        found = True
        for name in unknown_fields:
            item.fields[name] = FieldVerificationStatus.VERIFIED
    return found and canonical_stage_configuration_error(
        plan,
        candidate,
        allow_deferred_voice_signal=allow_deferred_voice_signal,
    ) == ""


def canonical_stage_workspace_error(
    observation: PhysicalWorkspaceObservation,
    topology: TopologyPlan,
) -> str:
    """Fail closed unless a fresh inventory is exactly one canonical stage.

    This is the ownership gate for a persistent LIVE build.  Device names and
    models, link endpoint/port pairs, and every port used by the plan must all
    match before a later stage may call an idempotent mutator.  Backend-managed
    power objects remain subject to the same narrow classification as the
    disposable-workspace gate.
    """

    if not observation.observed:
        return (
            "Read-only canonical stage inventory was incomplete: "
            + (observation.message or "unknown observation failure")
        )
    invalid_backend_managed = [
        item
        for item in observation.backend_managed_devices
        if item.model.strip().casefold() != "power distribution device"
        or bool(item.ports)
    ]
    if invalid_backend_managed:
        return (
            "Canonical stage inventory used an invalid backend-managed device "
            "classification."
        )

    expected_devices = Counter((item.name, item.model) for item in topology.devices)
    observed_devices = Counter(
        (item.name, item.model) for item in observation.semantic_devices
    )
    if observed_devices != expected_devices:
        return (
            "Canonical stage device/model inventory mismatch: expected "
            f"{sum(expected_devices.values())}, observed "
            f"{sum(observed_devices.values())}."
        )

    def endpoints(device_a: str, port_a: str, device_b: str, port_b: str):
        return tuple(sorted(((device_a, port_a), (device_b, port_b))))

    antenna_devices = {
        item.name
        for item in topology.devices
        if item.wireless or item.model == "AccessPoint-PT"
    }
    antenna_links = [
        item for item in observation.links if item.class_name == "Antenna"
    ]
    antenna_owners = Counter(item.device_a for item in antenna_links)
    if antenna_owners != Counter(antenna_devices):
        return (
            "Canonical stage implicit antenna ownership mismatch: expected "
            f"{len(antenna_devices)}, observed {len(antenna_links)}."
        )
    ports_by_device = {
        item.name: {port.casefold() for port in item.ports}
        for item in observation.semantic_devices
    }
    invalid_antennas = sorted(
        f"{item.device_a}:{item.port_a}"
        for item in antenna_links
        if item.device_b
        or item.port_b
        or item.device_a not in antenna_devices
        or item.port_a.casefold() not in ports_by_device.get(item.device_a, set())
    )
    if invalid_antennas:
        return (
            "Canonical stage implicit antenna endpoint mismatch: "
            + ", ".join(invalid_antennas)
        )

    expected_links = Counter(
        endpoints(item.device_a, item.port_a, item.device_b, item.port_b)
        for item in topology.links
    )
    observed_links = Counter(
        endpoints(item.device_a, item.port_a, item.device_b, item.port_b)
        for item in observation.links if item.class_name != "Antenna"
    )
    if observed_links != expected_links:
        return (
            "Canonical stage link inventory mismatch: expected "
            f"{sum(expected_links.values())}, observed {sum(observed_links.values())}."
        )

    missing_ports = sorted({
        f"{device}:{port}"
        for link in topology.links
        for device, port in (
            (link.device_a, link.port_a),
            (link.device_b, link.port_b),
        )
        if port.casefold() not in ports_by_device.get(device, set())
    })
    if missing_ports:
        return (
            "Canonical stage required port inventory mismatch: "
            + ", ".join(missing_ports)
        )
    return ""


def canonical_final_disposition(
    command: str,
    *,
    retain_authorized: bool,
) -> CPScaleFinalDisposition:
    """Resolve the final checkpoint without turning cleanup into a failure."""

    normalized = command.strip().casefold()
    if normalized == "continue":
        return CPScaleFinalDisposition.CLEANUP
    if normalized == "retain":
        if not retain_authorized:
            raise ValueError("Final presentation retention was not authorized.")
        return CPScaleFinalDisposition.RETAIN
    raise ValueError(f"Unsupported final checkpoint command {command!r}.")


def _canonical_voice_access_groups(
    plan: ConfigurationPlan,
    result: ConfigurationApplicationResult,
) -> list[CPScaleVoiceAccessGroupEvidence]:
    voice_actions = {
        item.id: item
        for item in plan.actions
        if isinstance(item, ConfigureAccessPort)
        and item.voice_vlan_id is not None
    }
    expectation_by_action = {
        item.action_id: item
        for item in plan.verification_expectations
        if item.action_id in voice_actions
    }
    barrier = result.voice_signal_barrier
    observed = {
        item.expectation_id: item
        for item in (
            barrier.post_signal_convergence_results
            if barrier is not None else []
        )
    }
    grouped: dict[tuple[str, int], list[tuple[ConfigureAccessPort, object]]] = {}
    for action in voice_actions.values():
        expectation = expectation_by_action.get(action.id)
        if expectation is None:
            continue
        grouped.setdefault(
            (action.device_name, int(action.voice_vlan_id)), [],
        ).append((action, expectation))

    evidence: list[CPScaleVoiceAccessGroupEvidence] = []
    for (switch, voice_vlan), members in sorted(grouped.items()):
        expected_interfaces = sorted(action.interface for action, _ in members)
        results = [
            observed.get(expectation.id) for _, expectation in members
        ]
        structured = [
            item.convergence.details
            for item in results
            if item is not None
            and item.convergence is not None
            and item.convergence.details.get("kind")
            == "voice_access_forwarding_group"
        ]
        details = structured[0] if structured else {}
        detailed_verified = sorted(details.get("verified_fwd_interfaces", []))
        detailed_missing = sorted(details.get("missing_interfaces", []))
        detailed_non_fwd = {
            str(interface): str(state)
            for interface, state in sorted(
                dict(details.get("non_fwd_interfaces", {})).items()
            )
        }
        detailed_classification = (
            detailed_verified
            + detailed_missing
            + sorted(detailed_non_fwd)
        )
        structured_consistent = bool(
            len(structured) == len(results)
            and all(item == details for item in structured)
            and all(
                item is not None
                and item.expectation_id == expectation.id
                and item.fresh_evidence == (
                    details.get("terminal_authority") == "AUTHORITATIVE"
                )
                and (
                    action.interface in detailed_verified
                ) == (
                    item.status is ActionExecutionStatus.VERIFIED
                    and item.fields.get("voice_forwarding")
                    is FieldVerificationStatus.VERIFIED
                )
                for (action, expectation), item in zip(members, results)
            )
            and details.get("switch") == switch
            and details.get("voice_vlan_id") == voice_vlan
            and sorted(details.get("expected_interfaces", []))
            == expected_interfaces
            and sorted(detailed_classification) == expected_interfaces
            and len(set(detailed_classification)) == len(expected_interfaces)
        )
        if structured_consistent:
            verified = detailed_verified
            missing = detailed_missing
            non_fwd = detailed_non_fwd
            terminal_authority = str(
                details.get("terminal_authority") or "UNOBSERVABLE"
            )
            failure_dimension = str(
                details.get("terminal_failure_dimension")
                or "GROUP_EVIDENCE_MISSING"
            )
            sample_count = int(details.get("sample_count") or 0)
            elapsed_ms = int(details.get("elapsed_ms") or 0)
        else:
            verified = []
            missing = expected_interfaces
            non_fwd = {}
            terminal_authority = "UNOBSERVABLE"
            failure_dimension = "GROUP_EVIDENCE_MISSING"
            sample_count = max(
                (
                    item.convergence.attempts
                    for item in results
                    if item is not None and item.convergence is not None
                ),
                default=0,
            )
            elapsed_ms = max(
                (
                    item.convergence.elapsed_ms
                    for item in results
                    if item is not None and item.convergence is not None
                ),
                default=0,
            )
        if (
            terminal_authority == "AUTHORITATIVE"
            and verified == expected_interfaces
            and not missing
            and not non_fwd
            and failure_dimension == "NONE"
        ):
            status = ActionExecutionStatus.VERIFIED
        elif non_fwd:
            status = ActionExecutionStatus.FAILED
        else:
            status = ActionExecutionStatus.UNOBSERVABLE
        evidence.append(CPScaleVoiceAccessGroupEvidence(
            switch=switch,
            voice_vlan_id=voice_vlan,
            expected_interfaces=expected_interfaces,
            verified_fwd_interfaces=verified,
            missing_interfaces=missing,
            non_fwd_interfaces=non_fwd,
            sample_count=sample_count,
            elapsed_ms=elapsed_ms,
            terminal_authority=terminal_authority,
            terminal_failure_dimension=failure_dimension,
            status=status,
        ))
    return evidence


def _voice_binding_sets(
    voice_plan: VoicePlan,
    dhcp_server_bindings: Sequence[dict[str, object]],
) -> tuple[dict[str, set[str]], bool, int]:
    expected_segments = {
        item.voice_segment_id for item in voice_plan.phone_assignments
    }
    candidates: dict[str, list[tuple[set[str], int | None]]] = {
        segment: [] for segment in expected_segments
    }
    for device in dhcp_server_bindings:
        table_readable = device.get("table_readable") is True
        pools = device.get("pools")
        for pool in pools if isinstance(pools, list) else []:
            if not isinstance(pool, dict) or pool.get("voice") is not True:
                continue
            segment = str(pool.get("segment_id") or "")
            if segment not in candidates:
                continue
            addresses = {
                str(address) for address in (
                    pool.get("bindings")
                    if isinstance(pool.get("bindings"), list) else []
                )
            }
            count = pool.get("binding_count")
            candidates[segment].append((
                addresses,
                int(count) if type(count) is int and table_readable else None,
            ))

    complete = True
    total = 0
    binding_sets: dict[str, set[str]] = {}
    for segment in sorted(expected_segments):
        rows = candidates.get(segment, [])
        if len(rows) != 1:
            complete = False
            binding_sets[segment] = set()
            continue
        addresses, count = rows[0]
        binding_sets[segment] = addresses
        if count is None or count != len(addresses):
            complete = False
            continue
        total += count
    return binding_sets, complete, total


def canonical_cp_scale_voice_evidence(
    *,
    stage: str,
    configuration_plan: ConfigurationPlan,
    configuration_result: ConfigurationApplicationResult,
    voice_plan: VoicePlan,
    voice_result: VoiceApplicationResult,
    dhcp_server_bindings: Sequence[dict[str, object]],
    lifecycle_events: Sequence[str],
) -> CPScaleCanonicalVoiceEvidence:
    """Correlate the exact canonical phones across FWD, IP, lease, and SCCP."""

    assignments = list(voice_plan.phone_assignments)
    expected = len(assignments)
    barrier = configuration_result.voice_signal_barrier
    network_status = (
        barrier.foundation_status
        if barrier is not None else ActionExecutionStatus.UNKNOWN
    )
    signal_status = (
        barrier.signal_status
        if barrier is not None else ActionExecutionStatus.UNKNOWN
    )
    groups = _canonical_voice_access_groups(
        configuration_plan, configuration_result,
    )
    fwd_verified = sum(
        len(item.verified_fwd_interfaces) for item in groups
    )
    fwd_failed = sum(len(item.non_fwd_interfaces) for item in groups)
    fwd_unobservable = max(0, expected - fwd_verified - fwd_failed)

    event_names = list(lifecycle_events)
    signal_event = (
        event_names.index("VOICE_SIGNAL_VERIFIED")
        if "VOICE_SIGNAL_VERIFIED" in event_names else None
    )
    fwd_event = (
        event_names.index("PHONE_ACCESS_FWD_VERIFIED")
        if "PHONE_ACCESS_FWD_VERIFIED" in event_names else None
    )
    registration_event = (
        event_names.index("REGISTRATION_STARTED")
        if "REGISTRATION_STARTED" in event_names else None
    )
    registration_after_fwd = (
        None
        if registration_event is None
        else bool(
            signal_event is not None
            and fwd_event is not None
            and signal_event < fwd_event < registration_event
        )
    )

    registrations: dict[str, object] = {}
    duplicated_registrations: set[str] = set()
    expected_registration_ids = Counter(
        item.phone_id for item in assignments
    )
    observed_registration_ids = Counter(
        item.phone_id for item in voice_result.registrations
    )
    registration_identity_errors: list[str] = []
    for phone_id in sorted(
        set(expected_registration_ids) | set(observed_registration_ids)
    ):
        expected_count = expected_registration_ids[phone_id]
        observed_count = observed_registration_ids[phone_id]
        if expected_count == 0:
            registration_identity_errors.append(f"unexpected:{phone_id}")
        elif observed_count == 0:
            registration_identity_errors.append(f"missing:{phone_id}")
        elif expected_count != 1:
            registration_identity_errors.append(
                f"duplicate-plan:{phone_id}:{expected_count}",
            )
        elif observed_count != 1:
            registration_identity_errors.append(
                f"duplicate-observation:{phone_id}:{observed_count}",
            )
    for item in voice_result.registrations:
        if item.phone_id in registrations:
            duplicated_registrations.add(item.phone_id)
        registrations[item.phone_id] = item
    binding_sets, binding_complete, binding_count = _voice_binding_sets(
        voice_plan, dhcp_server_bindings,
    )
    access_actions = {
        item.id: item
        for item in configuration_plan.actions
        if isinstance(item, ConfigureAccessPort)
    }

    verified_ports = {
        (item.switch, item.voice_vlan_id, interface)
        for item in groups
        for interface in item.verified_fwd_interfaces
    }
    failed_ports = {
        (item.switch, item.voice_vlan_id, interface)
        for item in groups
        for interface in item.non_fwd_interfaces
    }
    unobservable_ports = {
        (item.switch, item.voice_vlan_id, interface)
        for item in groups
        for interface in item.missing_interfaces
    }

    svi_present = 0
    dhcp_enabled = 0
    addressed = 0
    matching_bindings = 0
    sccp_registered = 0
    sccp_failed = 0
    failed_phones: list[CPScaleFailedPhoneIdentity] = []

    early_boundary = ""
    if network_status is not ActionExecutionStatus.VERIFIED:
        early_boundary = "NETWORK_FOUNDATION"
    elif voice_result.application_status is not ActionExecutionStatus.APPLIED:
        early_boundary = "VOICE_BOOTSTRAP"
    elif signal_status is not ActionExecutionStatus.VERIFIED:
        early_boundary = "VOICE_SIGNAL"
    elif fwd_verified != expected:
        early_boundary = "PHONE_ACCESS_FORWARDING"
    elif registration_after_fwd is not True:
        early_boundary = "REGISTRATION_ORDER"

    for assignment in assignments:
        action = access_actions.get(assignment.access_configuration_action_id)
        switch = action.device_name if action is not None else ""
        port = action.interface if action is not None else ""
        voice_vlan = (
            int(action.voice_vlan_id)
            if action is not None and action.voice_vlan_id is not None
            else assignment.voice_vlan_id
        )
        port_key = (switch, voice_vlan, port)
        registration = registrations.get(assignment.phone_id)
        endpoint_ipv4 = (
            registration.endpoint_ipv4 if registration is not None else ""
        )
        if registration is not None and registration.endpoint_interface_present:
            svi_present += 1
        if registration is not None and registration.endpoint_dhcp_enabled is True:
            dhcp_enabled += 1
        endpoint_verified = bool(
            registration is not None
            and registration.addressing_status is ActionExecutionStatus.VERIFIED
            and registration.endpoint_interface_present
            and registration.endpoint_address_channel
            and registration.endpoint_dhcp_enabled is True
            and endpoint_ipv4
            and registration.call_control_ipv4 == endpoint_ipv4
        )
        if endpoint_verified:
            addressed += 1

        segment_bindings = binding_sets.get(assignment.voice_segment_id, set())
        if not binding_complete:
            binding_state = "UNOBSERVABLE"
        elif not endpoint_ipv4:
            binding_state = "NOT_CHECKED"
        elif endpoint_ipv4 in segment_bindings:
            binding_state = "MATCHED"
            matching_bindings += 1
        else:
            binding_state = "MISSING"

        if (
            registration is not None
            and registration.status is ActionExecutionStatus.VERIFIED
        ):
            sccp_state = "REGISTERED"
            sccp_registered += 1
        elif (
            registration is not None
            and registration.status is ActionExecutionStatus.FAILED
        ):
            sccp_state = "NOT_REGISTERED"
            sccp_failed += 1
        else:
            sccp_state = "UNOBSERVABLE"

        boundary = early_boundary
        if not boundary and port_key in failed_ports | unobservable_ports:
            boundary = "PHONE_ACCESS_FORWARDING"
        if not boundary and port_key not in verified_ports:
            boundary = "PHONE_ACCESS_FORWARDING"
        if not boundary and (
            registration is None
            or assignment.phone_id in duplicated_registrations
            or not endpoint_verified
        ):
            boundary = "ENDPOINT_ADDRESS"
        if not boundary and binding_state != "MATCHED":
            boundary = "DHCP_BINDING"
        if not boundary and sccp_state != "REGISTERED":
            boundary = "SCCP"
        if boundary:
            failed_phones.append(CPScaleFailedPhoneIdentity(
                phone_id=assignment.phone_id,
                phone_name=assignment.physical_device_name,
                stage=stage,
                site_id=assignment.site_id,
                switch=switch,
                port=port,
                voice_vlan_id=voice_vlan,
                ipv4=endpoint_ipv4,
                binding_state=binding_state,
                sccp_state=sccp_state,
                first_contradicted_boundary=boundary,
            ))

    sccp_unobservable = max(0, expected - sccp_registered - sccp_failed)
    if early_boundary:
        first_boundary = early_boundary
    elif registration_identity_errors:
        first_boundary = "ENDPOINT_ADDRESS"
    elif addressed != expected or svi_present != expected or dhcp_enabled != expected:
        first_boundary = "ENDPOINT_ADDRESS"
    elif (
        not binding_complete
        or binding_count != expected
        or matching_bindings != expected
    ):
        first_boundary = "DHCP_BINDING"
    elif sccp_registered != expected:
        first_boundary = "SCCP"
    else:
        first_boundary = "NONE"
    complete = bool(
        first_boundary == "NONE"
        and not failed_phones
        and expected > 0
    )
    return CPScaleCanonicalVoiceEvidence(
        stage=stage,
        expected_phone_count=expected,
        network_foundation_status=network_status,
        voice_bootstrap_status=voice_result.application_status,
        voice_signal_status=signal_status,
        phone_access_group_count=len(groups),
        phone_access_fwd_expected=expected,
        phone_access_fwd_verified=fwd_verified,
        phone_access_fwd_failed=fwd_failed,
        phone_access_fwd_unobservable=fwd_unobservable,
        phone_access_fwd_groups=groups,
        phone_access_fwd_max_duration_ms=max(
            (item.elapsed_ms for item in groups), default=0,
        ),
        lifecycle_events=event_names,
        registration_started_after_fwd_barrier=registration_after_fwd,
        voice_svi_present_count=svi_present,
        dhcp_enabled_count=dhcp_enabled,
        addressed_count=addressed,
        registration_identity_errors=registration_identity_errors,
        binding_evidence_complete=binding_complete,
        voice_dhcp_binding_count=binding_count,
        matching_binding_count=matching_bindings,
        sccp_registered_count=sccp_registered,
        sccp_failed_count=sccp_failed,
        sccp_unobservable_count=sccp_unobservable,
        failed_phone_identities=failed_phones,
        first_contradicted_boundary=first_boundary,
        complete=complete,
    )


def archive_cp_scale_canonical_evidence(
    evidence: object,
    *,
    base_dir: Path,
    run_identity: str,
    phase: str,
) -> CPScaleEvidenceArchive:
    """Write one immutable, path-confined canonical evidence artifact."""

    safe_run = safe_name_component(run_identity, "canonical-cp-scale")
    safe_phase = safe_name_component(phase, "evidence")
    target = resolve_within(base_dir, f"{safe_run}-{safe_phase}.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            _jsonable(evidence),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    with target.open("xb") as stream:
        stream.write(payload)
        stream.flush()
    return CPScaleEvidenceArchive(
        run_identity=run_identity,
        phase=phase,
        path=target,
        sha256=hashlib.sha256(payload).hexdigest(),
    )


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
