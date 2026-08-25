"""Progressive live qualification of the canonical CP-SCALE scenario.

This module only orchestrates the normal enterprise composition and execution
entry points. It does not own a second deployment, configuration, or cleanup
pipeline.
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from ...domain.enterprise.models.capabilities import CapabilityStatus
from ...domain.enterprise.models.configuration import ConfigurationPlan, VerificationKind
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
from ...domain.enterprise.models.voice_plan import VoiceCapabilityProfile, VoiceIntent
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

    expected_action_ids = Counter(item.id for item in plan.actions)
    observed_action_ids = Counter(item.action_id for item in result.action_results)
    if expected_action_ids != observed_action_ids:
        return "Configuration action result inventory did not match the typed plan."
    allowed_actions = {
        ActionExecutionStatus.APPLIED,
        ActionExecutionStatus.NO_OP,
        ActionExecutionStatus.REASSERTED,
    }
    invalid_actions = sorted(
        f"{item.action_id}:{item.status.value}"
        for item in result.action_results
        if item.status not in allowed_actions
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
            ceiling_present = True
            expected_fields = {
                "interface": FieldVerificationStatus.VERIFIED,
                "status": FieldVerificationStatus.VERIFIED,
                "allowed_vlans": FieldVerificationStatus.UNOBSERVABLE,
            }
            if (
                item.status is not ActionExecutionStatus.VERIFIED
                or not item.fresh_evidence
                or item.evidence_method != "fresh_show_interfaces_trunk"
                or item.fields != expected_fields
            ):
                return (
                    f"Trunk verification {item.expectation_id!r} departed "
                    "from the exact operational trunk VERIFIED and allowed "
                    "VLAN list UNOBSERVABLE ceiling."
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
    return found and canonical_stage_configuration_error(plan, candidate) == ""


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
