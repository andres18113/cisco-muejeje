"""Governed persistent LIVE construction of the canonical CP-SCALE topology.

The process deliberately stays alive across every checkpoint because physical
cleanup ownership is runtime-instance-local.  It begins only from a completely
observed empty workspace, advances through the exact cumulative product stages,
and retains the presentation only after the full 314-device/219-link plans are
independently VERIFIED.  Any failure or operator abort cleans every device this
session attempted and requires two fresh empty-baseline observations.

No raw IOS, JavaScript, or bridge command is accepted from the operator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import packet_tracer_mcp

from packet_tracer_mcp.application.use_cases.apply_configuration import (
    ConfigurationApplicator,
)
from packet_tracer_mcp.application.use_cases.apply_control_plane import (
    ControlPlaneApplicator,
)
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    compose_cp_scale_canonical,
    project_cp_scale_canonical_delta,
    project_cp_scale_canonical_stage,
)
from packet_tracer_mcp.application.use_cases.deploy_enterprise_topology import (
    EnterprisePhysicalTopologyDeployer,
    disposable_workspace_error,
)
from packet_tracer_mcp.application.use_cases.foundational_evidence import (
    derive_foundational_hashes,
    derive_foundational_statuses,
)
from packet_tracer_mcp.application.use_cases.execute_enterprise_reference import (
    configuration_application_contradiction,
)
from packet_tracer_mcp.application.use_cases.observe_serial_orientation import (
    SerialOrientationObserver,
)
from packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    canonical_checkpoint_repository_error,
    canonical_cleanup_restoration_error,
    canonical_configuration_retryable_operational_unknown,
    canonical_stage_configuration_error,
    canonical_stage_resume_error,
    canonical_stage_workspace_error,
    read_git_repository_state,
)
from packet_tracer_mcp.application.use_cases.reconcile_canonical_stage import (
    canonical_delta_deployment_error,
    reconcile_canonical_stage_deployment,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ConfigurationApplicationStatus,
    ConfigurationRuntimeContext,
)
from packet_tracer_mcp.domain.enterprise.models.deployment import (
    EnvironmentFingerprint,
)
from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentItemStatus,
    PhysicalDeploymentStatus,
    PhysicalObjectKind,
)
from packet_tracer_mcp.infrastructure.catalog.control_plane_capabilities import (
    packet_tracer_control_plane_capabilities,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_control_plane_runtime import (
    PacketTracerEnterpriseControlPlaneRuntime,
)
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
    OperationalQueryId,
    parse_show_ip_interface_brief,
)
from packet_tracer_mcp.infrastructure.execution.live_bridge import (
    PacketTracerHttpTransport,
)
from packet_tracer_mcp.infrastructure.execution.live_environment_preflight import (
    packet_tracer_process_error,
)
from packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
)
from packet_tracer_mcp.infrastructure.execution.serial_orientation_runtime import (
    PacketTracerSerialOrientationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.typed_ping import (
    TypedPingExecutor,
)
from packet_tracer_mcp.shared.utils import (
    serialize_typed_ping_evidence,
)


GOVERNED_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = "feature/runtime-ripv2"
EXPECTED_UPSTREAM = "personal/feature/runtime-ripv2"
EVIDENCE_PATH = GOVERNED_ROOT / "data" / "cp-scale" / "live-canonical-progress.json"
CHECKPOINT_PATH = (
    GOVERNED_ROOT / "docs" / "reference" / "cp-scale"
    / "live_canonical_checkpoint.json"
)
_GOVERNED_SOURCE_PATHS = (
    "src",
    "tests",
    "tools/cp_scale_canonical_live.py",
    "docs/reference/cp-scale/diseno_logico_IMP.md",
    "docs/reference/cp-scale/topologia_completa_IMP.md",
)
_BUILD_STAGES = tuple(
    stage for stage in CPScaleCanonicalStage
    if stage is not CPScaleCanonicalStage.REMAINING
)


class CanonicalLiveFailure(RuntimeError):
    """One governed stage failed after the session had acquired ownership."""


def _packet_tracer_processes() -> list[dict[str, object]]:
    command = (
        "Get-Process | Where-Object { $_.ProcessName -like 'PacketTracer*' } | "
        "ForEach-Object { [PSCustomObject]@{ "
        "ProcessName=$_.ProcessName; Id=$_.Id; "
        "MainWindowHandle=$_.MainWindowHandle; "
        "ProductVersion=$_.MainModule.FileVersionInfo.ProductVersion; "
        "FileVersion=$_.MainModule.FileVersionInfo.FileVersion; "
        "Path=$_.MainModule.FileName } } | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        check=True,
        capture_output=True,
        text=True,
    )
    raw = completed.stdout.strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, list) else [parsed]


def _inventory(physical: PacketTracerPhysicalTopologyRuntime) -> list[dict]:
    observation = physical.observe_workspace()
    if not observation.observed:
        raise CanonicalLiveFailure(
            "Live inventory became unobservable: " + observation.message,
        )
    return [
        {"name": item.name, "model": item.model, "ports": list(item.ports)}
        for item in observation.semantic_devices
    ]


def _core_serial_addresses(projection) -> dict[str, dict[str, str]]:
    expected: dict[str, dict[str, str]] = {}
    for action in projection.configuration.actions:
        interface = getattr(action, "interface", "")
        if not interface.casefold().startswith("serial"):
            continue
        expected.setdefault(action.device_name, {})[interface] = action.ipv4
    return expected


def _wait_for_serial_interfaces(
    ios: ControlledIosExecutor,
    expected: dict[str, dict[str, str]],
    *,
    attempts: int = 10,
    interval_seconds: float = 2.0,
) -> tuple[bool, list[dict[str, object]]]:
    evidence: list[dict[str, object]] = []
    ready = False
    for attempt in range(attempts):
        ready = True
        evidence = []
        for device_name, interfaces in sorted(expected.items()):
            result = ios.execute(
                device_name, OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
            )
            rows = {
                item.interface.casefold(): item
                for item in parse_show_ip_interface_brief(result.output)
            }
            matched = all(
                (row := rows.get(interface.casefold())) is not None
                and row.ip_address == address
                and row.status.casefold() == "up"
                and row.protocol.casefold() == "up"
                for interface, address in interfaces.items()
            )
            ready = ready and result.fresh_output_observed and matched
            evidence.append({
                "device_name": device_name,
                "fresh_output_observed": result.fresh_output_observed,
                "output_complete": result.output_complete,
                "failure_reason": result.failure_reason,
                "expected_serial_up_up": matched,
                "output": result.output,
            })
        if ready or attempt + 1 == attempts:
            break
        time.sleep(interval_seconds)
    return ready, evidence


def _wait_for_core_forwarding(
    ping: TypedPingExecutor,
    checks: dict[str, str],
    *,
    attempts: int = 4,
    interval_seconds: float = 5.0,
) -> tuple[bool, dict[str, object]]:
    evidence: dict[str, object] = {}
    verified = True
    for source, destination in checks.items():
        result = ping.ping(source, destination)
        for attempt in range(attempts - 1):
            if result.fresh_output_observed and result.reachable is True:
                break
            time.sleep(interval_seconds)
            result = ping.ping(source, destination)
        evidence[source] = serialize_typed_ping_evidence(result)
        verified = (
            verified
            and result.fresh_output_observed
            and result.reachable is True
        )
    return verified, evidence


def _write_evidence(evidence: dict[str, object]) -> None:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    temporary = EVIDENCE_PATH.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, EVIDENCE_PATH)


def _write_checkpoint_summary(stage: str, evidence: dict[str, object]) -> None:
    stages = evidence.get("stages", [])
    latest = stages[-1] if isinstance(stages, list) and stages else {}
    if stage == "full-qualification":
        latest = evidence.get("full_qualification", latest)
    if not isinstance(latest, dict):
        latest = {}
    plan = latest.get("plan", {})
    physical = latest.get("physical", {})
    raw_digest = hashlib.sha256(EVIDENCE_PATH.read_bytes()).hexdigest()
    summary = {
        "schema": "cp-scale-live-checkpoint-v1",
        "checkpoint": stage,
        "checkpoint_at": evidence.get("checkpoint_at", ""),
        "packet_tracer_version": evidence.get("packet_tracer_version", ""),
        "live_devices": evidence.get("live_devices", 0),
        "live_links": evidence.get("live_links", 0),
        "physical_topology_hash": (
            plan.get("topology_hash", "")
            if isinstance(plan, dict) and plan.get("topology_hash")
            else physical.get("physical_topology_hash", "")
            if isinstance(physical, dict) else ""
        ),
        "configuration_status": (
            latest.get("configuration", {}).get("status", "")
            if isinstance(latest.get("configuration"), dict) else ""
        ),
        "control_plane_status": (
            latest.get("control_plane", {}).get("status", "")
            if isinstance(latest.get("control_plane"), dict) else ""
        ),
        "verification_scope": latest.get("verification_scope", ""),
        "workspace_verified_twice": latest.get("workspace_verified_twice", False),
        "raw_evidence_sha256": raw_digest,
    }
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CHECKPOINT_PATH.with_suffix(".json.tmp")
    payload = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, CHECKPOINT_PATH)


def _git_output(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=GOVERNED_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _governed_source_changed(session_source_head: str) -> bool:
    completed = subprocess.run(
        [
            "git", "diff", "--quiet", session_source_head, "--",
            *_GOVERNED_SOURCE_PATHS,
        ],
        cwd=GOVERNED_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode not in {0, 1}:
        raise CanonicalLiveFailure(
            "Governed source comparison failed: " + completed.stderr.strip(),
        )
    return completed.returncode == 1


def _checkpoint(
    stage: str,
    evidence: dict[str, object],
    *,
    session_source_head: str,
) -> str:
    evidence["checkpoint"] = stage
    evidence["checkpoint_at"] = datetime.now(timezone.utc).isoformat()
    repository = read_git_repository_state(GOVERNED_ROOT)
    evidence["checkpoint_repository"] = repository.model_dump(mode="json")
    _write_evidence(evidence)
    _write_checkpoint_summary(stage, evidence)
    print(json.dumps({
        "event": "CHECKPOINT_READY",
        "stage": stage,
        "evidence_path": str(EVIDENCE_PATH),
        "devices": evidence.get("live_devices", 0),
        "links": evidence.get("live_links", 0),
    }), flush=True)
    command = input().strip().casefold()
    if command not in {"continue", "retain"}:
        raise CanonicalLiveFailure(
            f"Checkpoint {stage!r} received operator command {command!r}; aborting.",
        )
    resumed_repository = read_git_repository_state(GOVERNED_ROOT)
    try:
        upstream_head = _git_output("rev-parse", "@{upstream}")
        dirty = bool(_git_output("status", "--porcelain"))
        source_changed = _governed_source_changed(session_source_head)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CanonicalLiveFailure(
            f"Checkpoint repository revalidation failed: {exc}",
        ) from exc
    repository_error = canonical_checkpoint_repository_error(
        branch=resumed_repository.branch,
        upstream=resumed_repository.upstream,
        head=resumed_repository.head,
        upstream_head=upstream_head,
        dirty=dirty,
        governed_source_changed=source_changed,
    )
    evidence["checkpoint_resume_repository"] = {
        **resumed_repository.model_dump(mode="json"),
        "upstream_head": upstream_head,
        "dirty": dirty,
        "governed_source_changed": source_changed,
    }
    _write_evidence(evidence)
    if resumed_repository.error or repository_error:
        raise CanonicalLiveFailure(
            "Checkpoint may not advance: "
            + (resumed_repository.error + " " if resumed_repository.error else "")
            + repository_error,
        )
    return command


def _cleanup_owned(
    physical: PacketTracerPhysicalTopologyRuntime,
    full_topology,
    owned_device_ids: set[str],
    baseline,
) -> dict[str, object]:
    cleanup = []
    for device in reversed(full_topology.devices):
        if device.id not in owned_device_ids:
            continue
        cleanup.append(physical.remove_device(device).model_dump(mode="json"))
    first = physical.observe_workspace()
    second = physical.observe_workspace()
    restoration_error = canonical_cleanup_restoration_error(
        baseline, first, second,
    )
    return {
        "mutations": cleanup,
        "first": first.compact_summary(),
        "second": second.compact_summary(),
        "restoration_error": restoration_error,
        "verified": not restoration_error,
    }


def _attempted_device_ids(deployment) -> set[str]:
    return {
        item.target_id
        for item in deployment.item_results
        if item.target_kind is PhysicalObjectKind.DEVICE
        and item.status is not PhysicalDeploymentItemStatus.NOT_ATTEMPTED
    }


def _execute_stage(
    projection,
    *,
    composition,
    deployment,
    delta_deployment,
    physical: PacketTracerPhysicalTopologyRuntime,
    configuration_runtime: PacketTracerEnterpriseConfigurationRuntime,
    control_runtime: PacketTracerEnterpriseControlPlaneRuntime,
    transport: PacketTracerHttpTransport,
    fingerprint: EnvironmentFingerprint,
    packet_tracer_version: str,
) -> tuple[dict[str, object], object]:
    evidence: dict[str, object] = {
        "stage": projection.stage.value,
        "plan": {
            "topology_hash": projection.topology.physical_identity_hash,
            "configuration_hash": projection.configuration.semantic_hash,
            "control_plane_hash": projection.control_plane.semantic_hash,
            "devices": len(projection.topology.devices),
            "modules": len(projection.topology.modules),
            "links": len(projection.topology.links),
            "configuration_actions": len(projection.configuration.actions),
            "control_plane_actions": len(projection.control_plane.actions),
            "verification_expectations": len(
                projection.control_plane.verification_expectations
            ),
        },
        "physical": deployment.model_dump(mode="json"),
        "physical_delta": (
            delta_deployment.model_dump(mode="json")
            if delta_deployment is not None else None
        ),
    }
    if (
        deployment.status is not PhysicalDeploymentStatus.VERIFIED
        or deployment.manifest is None
    ):
        raise CanonicalLiveFailure(
            f"Physical stage {projection.stage.value!r} was not VERIFIED: "
            + "; ".join(deployment.errors)
        )

    orientation = SerialOrientationObserver(
        PacketTracerSerialOrientationRuntime(transport.send_and_wait),
    ).observe(projection.topology, deployment.manifest)
    evidence["serial_orientation"] = orientation.model_dump(mode="json")
    if not orientation.verified or orientation.oriented_manifest is None:
        raise CanonicalLiveFailure(
            f"Serial orientation at {projection.stage.value!r} was not VERIFIED: "
            + "; ".join(orientation.errors)
        )
    manifest = orientation.oriented_manifest
    context = ConfigurationRuntimeContext(environment_fingerprint=fingerprint)
    configuration = ConfigurationApplicator(configuration_runtime).apply(
        projection.configuration,
        actual_source_topology_hash=projection.topology.physical_identity_hash,
        capabilities=composition.capabilities,
        runtime_context=context,
        deployment_manifest=manifest,
    )
    evidence["configuration_attempts"] = [configuration.model_dump(mode="json")]
    contradiction = configuration_application_contradiction(configuration)
    evidence["configuration_contradictions"] = [contradiction]
    if contradiction:
        raise CanonicalLiveFailure(
            f"Configuration at {projection.stage.value!r} contradicted the plan: "
            + contradiction
        )

    ios = ControlledIosExecutor(transport.send_and_wait)
    serial_ready, serial_evidence = _wait_for_serial_interfaces(
        ios, _core_serial_addresses(projection),
    )
    evidence["serial_interfaces"] = serial_evidence
    if not serial_ready:
        raise CanonicalLiveFailure(
            f"Serial interfaces lost up/up convergence at {projection.stage.value!r}."
        )

    configuration_error = canonical_stage_configuration_error(
        projection.configuration, configuration,
    )
    if (
        configuration_error
        and canonical_configuration_retryable_operational_unknown(
            projection.configuration, configuration,
        )
    ):
        configuration = ConfigurationApplicator(configuration_runtime).apply(
            projection.configuration,
            actual_source_topology_hash=projection.topology.physical_identity_hash,
            capabilities=composition.capabilities,
            runtime_context=context,
            deployment_manifest=manifest,
        )
        evidence["configuration_attempts"].append(
            configuration.model_dump(mode="json")
        )
        contradiction = configuration_application_contradiction(configuration)
        evidence["configuration_contradictions"].append(contradiction)
        if contradiction:
            raise CanonicalLiveFailure(
                f"Configuration re-read at {projection.stage.value!r} "
                "contradicted the plan: " + contradiction
            )
        configuration_error = canonical_stage_configuration_error(
            projection.configuration, configuration,
        )
    evidence["configuration"] = configuration.model_dump(mode="json")
    evidence["configuration_acceptance_error"] = configuration_error
    if configuration_error:
        raise CanonicalLiveFailure(
            f"Configuration at {projection.stage.value!r} exceeded its governed "
            "observability envelope: " + configuration_error
        )

    statuses = derive_foundational_statuses(
        configuration_result=configuration,
        physical_result=deployment,
    )
    control = ControlPlaneApplicator(control_runtime).apply(
        projection.control_plane,
        actual_source_topology_hash=projection.topology.physical_identity_hash,
        actual_source_configuration_hash=projection.configuration.semantic_hash,
        foundational_statuses=statuses,
        foundational_hashes=derive_foundational_hashes(projection.control_plane),
        capabilities=packet_tracer_control_plane_capabilities(packet_tracer_version),
        runtime_context=context,
        deployment_manifest=manifest,
    )
    evidence["control_plane"] = control.model_dump(mode="json")
    if control.status is not ConfigurationApplicationStatus.VERIFIED:
        raise CanonicalLiveFailure(
            f"Control plane at {projection.stage.value!r} was not VERIFIED: "
            f"{control.status.value}/{control.failure_code.value}"
        )

    forwarding_verified, forwarding = _wait_for_core_forwarding(
        TypedPingExecutor(
            transport.send_and_wait,
            timeout_seconds=30.0,
            measurement_attempts=3,
        ),
        projection.forwarding_checks,
    )
    evidence["core_forwarding"] = forwarding
    evidence["core_forwarding_verified"] = forwarding_verified
    if not forwarding_verified:
        raise CanonicalLiveFailure(
            f"Core forwarding regressed at {projection.stage.value!r}."
        )

    first = physical.observe_workspace()
    second = physical.observe_workspace()
    first_error = canonical_stage_workspace_error(first, projection.topology)
    second_error = canonical_stage_workspace_error(second, projection.topology)
    evidence["workspace_first"] = first.compact_summary()
    evidence["workspace_second"] = second.compact_summary()
    evidence["workspace_verified_twice"] = not first_error and not second_error
    if first_error or second_error:
        raise CanonicalLiveFailure(
            f"Canonical workspace reconciliation failed at "
            f"{projection.stage.value!r}: {first_error or second_error}"
        )
    evidence["verified"] = True
    evidence["verification_scope"] = "VERIFIED_BOUNDED_RETAINED"
    return evidence, manifest, second


def _full_qualification_projection(composition):
    projection = project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.REMAINING,
    )
    return projection.__class__(
        stage=projection.stage,
        topology=composition.topology,
        configuration=composition.configuration,
        control_plane=composition.control_plane,
        forwarding_checks=projection.forwarding_checks,
    )


def run(
    packet_tracer_version: str,
    *,
    expected_head: str,
    retain_on_full_verification: bool,
) -> int:
    evidence: dict[str, object] = {
        "packet_tracer_version": packet_tracer_version,
        "python_executable": sys.executable,
        "package_file": packet_tracer_mcp.__file__,
        "loaded_namespaces": [
            name for name in ("packet_tracer_mcp", "src.packet_tracer_mcp")
            if name in sys.modules
        ],
        "stages": [],
        "presentation_retained": False,
    }
    isolation = ImportIsolationPreflight(GOVERNED_ROOT).ensure_isolated()
    evidence["import_isolation"] = {
        "state": isolation.state.value,
        "detail": isolation.detail,
    }
    if not isolation.isolated:
        evidence["hard_stop"] = isolation.render()
        _write_evidence(evidence)
        return 2

    repository = read_git_repository_state(GOVERNED_ROOT)
    evidence["repository"] = repository.model_dump(mode="json")
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=GOVERNED_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    try:
        initial_upstream_head = _git_output("rev-parse", "@{upstream}")
    except (OSError, subprocess.CalledProcessError) as exc:
        initial_upstream_head = ""
        evidence["initial_upstream_error"] = str(exc)
    repository_errors = []
    if repository.branch != EXPECTED_BRANCH:
        repository_errors.append(
            f"Expected branch {EXPECTED_BRANCH!r}; observed {repository.branch!r}."
        )
    if repository.upstream != EXPECTED_UPSTREAM:
        repository_errors.append(
            f"Expected upstream {EXPECTED_UPSTREAM!r}; observed {repository.upstream!r}."
        )
    if expected_head and repository.head != expected_head:
        repository_errors.append(
            f"Expected HEAD {expected_head!r}; observed {repository.head!r}."
        )
    if repository.error:
        repository_errors.append(repository.error)
    if dirty:
        repository_errors.append("Live session requires a clean initial worktree.")
    if repository.head != initial_upstream_head:
        repository_errors.append(
            "Live session requires its exact initial HEAD pushed to upstream."
        )
    if repository_errors:
        evidence["hard_stop"] = " ".join(repository_errors)
        _write_evidence(evidence)
        return 2
    session_source_head = repository.head

    processes = _packet_tracer_processes()
    evidence["packet_tracer_processes"] = processes
    process_error = packet_tracer_process_error(processes, packet_tracer_version)
    if process_error:
        evidence["hard_stop"] = process_error
        _write_evidence(evidence)
        return 2

    transport = PacketTracerHttpTransport()
    physical = None
    baseline = None
    owned_device_ids: set[str] = set()
    retain_confirmed = False
    composition = None
    try:
        if not transport.start(timeout_seconds=10.0):
            evidence["http_bridge"] = transport.status_dict()
            raise CanonicalLiveFailure(
                "Authenticated Packet Tracer HTTP bridge did not obtain fresh polling."
            )
        evidence["http_bridge"] = transport.status_dict()
        physical = PacketTracerPhysicalTopologyRuntime(
            transport.send_and_wait,
            mutation_timeout_seconds=30.0,
            observation_timeout_seconds=12.0,
        )
        baseline = physical.observe_workspace()
        evidence["baseline"] = baseline.compact_summary()
        baseline_error = disposable_workspace_error(baseline)
        if baseline_error:
            evidence["hard_stop"] = baseline_error
            _write_evidence(evidence)
            return 2

        composition = compose_cp_scale_canonical(
            packet_tracer_version=packet_tracer_version,
        )
        if not composition.valid:
            raise CanonicalLiveFailure(
                "Canonical composition failed: " + "; ".join(composition.issues),
            )
        assert composition.topology is not None
        assert composition.configuration is not None
        assert composition.control_plane is not None

        fingerprint = EnvironmentFingerprint(
            backend="packet_tracer",
            backend_version=packet_tracer_version,
            bridge_transport=transport.bridge_transport,
            runtime_mode="live",
        )
        deployer = EnterprisePhysicalTopologyDeployer(physical)
        configuration_runtime = PacketTracerEnterpriseConfigurationRuntime(
            lambda: _inventory(physical),
            transport.send,
            transport.send_and_wait,
            l3_timeout_seconds=20.0,
        )
        control_runtime = PacketTracerEnterpriseControlPlaneRuntime(
            lambda: _inventory(physical),
            transport.send,
            transport.send_and_wait,
        )

        previous_projection = None
        verified_core_deployment = None
        verified_core_topology = None
        stage_snapshot = None
        for index, stage in enumerate(_BUILD_STAGES):
            projection = project_cp_scale_canonical_stage(
                composition,
                stage,
                control_plane_capabilities=(
                    packet_tracer_control_plane_capabilities(packet_tracer_version)
                ),
            )
            if index == 0:
                delta_deployment = deployer.deploy(
                    projection.topology,
                    environment_fingerprint=fingerprint,
                    deployment_id="cp-scale-canonical/routing-core",
                    require_empty_workspace=True,
                )
                owned_device_ids |= _attempted_device_ids(delta_deployment)
                ownership_error = canonical_delta_deployment_error(
                    None, projection.topology, delta_deployment,
                )
                if ownership_error:
                    raise CanonicalLiveFailure(
                        "Routing-core ownership was not proven: " + ownership_error
                    )
                deployment = delta_deployment
                verified_core_deployment = deployment
                verified_core_topology = projection.topology
            else:
                assert previous_projection is not None
                assert stage_snapshot is not None
                if not transport.is_connected:
                    raise CanonicalLiveFailure(
                        f"Packet Tracer bridge was not freshly connected before {stage.value!r}."
                    )
                resume_observations = [
                    physical.observe_workspace(),
                    physical.observe_workspace(),
                ]
                resume_errors = [
                    canonical_stage_resume_error(
                        stage_snapshot, observation, previous_projection.topology,
                    )
                    for observation in resume_observations
                ]
                evidence.setdefault("resume_gates", []).append({
                    "before_stage": stage.value,
                    "bridge": transport.status_dict(),
                    "observations": [
                        item.compact_summary() for item in resume_observations
                    ],
                    "errors": resume_errors,
                })
                if any(resume_errors):
                    raise CanonicalLiveFailure(
                        f"Retained workspace drifted before {stage.value!r}: "
                        + next(item for item in resume_errors if item)
                    )
                delta_topology = project_cp_scale_canonical_delta(
                    previous_projection.topology, projection.topology,
                )
                delta_deployment = deployer.deploy(
                    delta_topology,
                    environment_fingerprint=fingerprint,
                    deployment_id=f"cp-scale-canonical/{stage.value}/delta",
                    require_empty_workspace=False,
                )
                owned_device_ids |= _attempted_device_ids(delta_deployment)
                ownership_error = canonical_delta_deployment_error(
                    previous_projection.topology,
                    delta_topology,
                    delta_deployment,
                )
                if ownership_error:
                    raise CanonicalLiveFailure(
                        f"Physical delta {stage.value!r} lacked session ownership: "
                        + ownership_error
                    )
                if (
                    delta_deployment.status is not PhysicalDeploymentStatus.VERIFIED
                    or delta_deployment.manifest is None
                ):
                    raise CanonicalLiveFailure(
                        f"Physical delta {stage.value!r} was not VERIFIED: "
                        + "; ".join(delta_deployment.errors)
                    )
                deployment = reconcile_canonical_stage_deployment(
                    projection.topology,
                    physical,
                    environment_fingerprint=fingerprint,
                    verified_core_topology=verified_core_topology,
                    verified_core_deployment=verified_core_deployment,
                    deployment_id=f"cp-scale-canonical/{stage.value}/cumulative",
                )
            if (
                deployment.status is not PhysicalDeploymentStatus.VERIFIED
                or deployment.manifest is None
            ):
                raise CanonicalLiveFailure(
                    f"Cumulative physical stage {stage.value!r} was not VERIFIED: "
                    + "; ".join(deployment.errors)
                )
            stage_evidence, _, stage_snapshot = _execute_stage(
                projection,
                composition=composition,
                deployment=deployment,
                delta_deployment=delta_deployment,
                physical=physical,
                configuration_runtime=configuration_runtime,
                control_runtime=control_runtime,
                transport=transport,
                fingerprint=fingerprint,
                packet_tracer_version=packet_tracer_version,
            )
            evidence["stages"].append(stage_evidence)
            evidence["live_devices"] = len(projection.topology.devices)
            evidence["live_links"] = len(projection.topology.links)

            previous_projection = projection
            if stage is CPScaleCanonicalStage.ROUTING_CORE:
                print(json.dumps({
                    "event": "CORE_REMATERIALIZED",
                    "devices": 3,
                    "links": 3,
                }), flush=True)
            command = _checkpoint(
                stage.value,
                evidence,
                session_source_head=session_source_head,
            )
            if command == "retain":
                raise CanonicalLiveFailure(
                    "Retention is forbidden before full CP-SCALE qualification."
                )

        assert previous_projection is not None
        remaining_projection = project_cp_scale_canonical_stage(
            composition,
            CPScaleCanonicalStage.REMAINING,
            control_plane_capabilities=(
                packet_tracer_control_plane_capabilities(packet_tracer_version)
            ),
        )
        remaining_delta = project_cp_scale_canonical_delta(
            previous_projection.topology, remaining_projection.topology,
        )
        if remaining_delta.devices or remaining_delta.modules or remaining_delta.links:
            raise CanonicalLiveFailure(
                "The governed remaining-topology reconciliation was not zero-delta."
            )
        remaining_deployment = reconcile_canonical_stage_deployment(
            remaining_projection.topology,
            physical,
            environment_fingerprint=fingerprint,
            verified_core_topology=verified_core_topology,
            verified_core_deployment=verified_core_deployment,
            deployment_id="cp-scale-canonical/remaining/reconciliation",
        )
        if (
            remaining_deployment.status is not PhysicalDeploymentStatus.VERIFIED
            or remaining_deployment.manifest is None
        ):
            raise CanonicalLiveFailure(
                "Remaining canonical topology reconciliation was not VERIFIED: "
                + "; ".join(remaining_deployment.errors)
            )
        remaining_evidence = {
            "stage": CPScaleCanonicalStage.REMAINING.value,
            "physical_delta": {"devices": 0, "modules": 0, "links": 0},
            "physical": remaining_deployment.model_dump(mode="json"),
            "verified": True,
            "verification_scope": "ZERO_DELTA_RECONCILED",
        }
        evidence["stages"].append(remaining_evidence)
        command = _checkpoint(
            CPScaleCanonicalStage.REMAINING.value,
            evidence,
            session_source_head=session_source_head,
        )
        if command == "retain":
            raise CanonicalLiveFailure(
                "Retention is forbidden before full CP-SCALE qualification."
            )

        assert stage_snapshot is not None
        if not transport.is_connected:
            raise CanonicalLiveFailure(
                "Packet Tracer bridge was not freshly connected before full qualification."
            )
        full_resume_observations = [
            physical.observe_workspace(),
            physical.observe_workspace(),
        ]
        full_resume_errors = [
            canonical_stage_resume_error(
                stage_snapshot, observation, remaining_projection.topology,
            )
            for observation in full_resume_observations
        ]
        evidence.setdefault("resume_gates", []).append({
            "before_stage": "full-qualification",
            "bridge": transport.status_dict(),
            "observations": [
                item.compact_summary() for item in full_resume_observations
            ],
            "errors": full_resume_errors,
        })
        if any(full_resume_errors):
            raise CanonicalLiveFailure(
                "Retained workspace drifted before full qualification: "
                + next(item for item in full_resume_errors if item)
            )

        full_projection = _full_qualification_projection(composition)
        full_deployment = reconcile_canonical_stage_deployment(
            full_projection.topology,
            physical,
            environment_fingerprint=fingerprint,
            verified_core_topology=verified_core_topology,
            verified_core_deployment=verified_core_deployment,
            deployment_id="cp-scale-canonical/full-qualification",
        )
        full_evidence, _, stage_snapshot = _execute_stage(
            full_projection,
            composition=composition,
            deployment=full_deployment,
            delta_deployment=None,
            physical=physical,
            configuration_runtime=configuration_runtime,
            control_runtime=control_runtime,
            transport=transport,
            fingerprint=fingerprint,
            packet_tracer_version=packet_tracer_version,
        )
        full_evidence["stage"] = "full-qualification"
        evidence["full_qualification"] = full_evidence
        evidence["live_devices"] = len(composition.topology.devices)
        evidence["live_links"] = len(composition.topology.links)
        command = _checkpoint(
            "full-qualification",
            evidence,
            session_source_head=session_source_head,
        )
        if command != "retain" or not retain_on_full_verification:
            raise CanonicalLiveFailure(
                "Final presentation retention requires both the CLI authorization "
                "and the exact 'retain' checkpoint command."
            )
        evidence["presentation_retained"] = True
        evidence["closure"] = "CP_SCALE_GOVERNED_VERIFIED"
        _write_evidence(evidence)
        retain_confirmed = True
        print(json.dumps({
            "event": "PRESENTATION_RETAINED",
            "devices": evidence["live_devices"],
            "links": evidence["live_links"],
            "evidence_path": str(EVIDENCE_PATH),
        }), flush=True)
        return 0
    except Exception as exc:
        evidence["failure"] = f"{type(exc).__name__}: {exc}"
        return 1
    finally:
        if (
            physical is not None
            and baseline is not None
            and not retain_confirmed
            and composition is not None
        ):
            evidence["cleanup"] = _cleanup_owned(
                physical, composition.topology, owned_device_ids, baseline,
            )
        evidence["presentation_retained"] = retain_confirmed
        _write_evidence(evidence)
        transport.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Authorize the canonical typed mutations after every hard gate.",
    )
    parser.add_argument("--packet-tracer-version", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument(
        "--retain-on-full-verification",
        action="store_true",
        help="Permit final retention, but only after the final 'retain' command.",
    )
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({
            "hard_stop": "--execute is required; no Packet Tracer mutation occurred.",
        }))
        return 2
    return run(
        args.packet_tracer_version,
        expected_head=args.expected_head,
        retain_on_full_verification=args.retain_on_full_verification,
    )


if __name__ == "__main__":
    raise SystemExit(main())
