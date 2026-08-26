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
import collections
import hashlib
import ipaddress
import json
import math
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
from packet_tracer_mcp.application.use_cases.apply_voice import VoiceApplicator
from packet_tracer_mcp.application.use_cases.capability_discovery import (
    CapabilityDiscoveryService,
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
    inherit_verified_serial_orientation,
)
from packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    canonical_capability_probe_error,
    canonical_bridge_polling_error,
    canonical_checkpoint_repository_error,
    canonical_cleanup_restoration_error,
    canonical_configuration_retryable_operational_unknown,
    canonical_required_capability_probes,
    canonical_stage_configuration_error,
    canonical_stage_resume_error,
    canonical_stage_workspace_error,
    read_git_repository_state,
)
from packet_tracer_mcp.application.use_cases.reconcile_canonical_stage import (
    canonical_delta_deployment_error,
    reconcile_canonical_stage_deployment,
)
from packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
    ConfigureAccessPort,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationRuntimeContext,
)
from packet_tracer_mcp.domain.enterprise.models.deployment import (
    EnvironmentFingerprint,
)
from packet_tracer_mcp.domain.enterprise.models.discovery import (
    ProbeLevel,
    ProbeRequest,
)
from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentItemStatus,
    PhysicalDeploymentStatus,
    PhysicalObjectKind,
)
from packet_tracer_mcp.infrastructure.catalog.control_plane_capabilities import (
    packet_tracer_control_plane_capabilities,
)
from packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_control_plane_runtime import (
    PacketTracerEnterpriseControlPlaneRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_voice_runtime import (
    PacketTracerEnterpriseVoiceRuntime,
)
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
)
from packet_tracer_mcp.infrastructure.execution.command_dispatch import (
    DispatchClassification,
    is_command_corrupted,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
    OperationalQueryId,
    PagerContinuation,
    classify_show_spanning_tree,
    ios_rejection_reason,
    parse_show_ip_dhcp_binding,
    parse_show_ip_dhcp_server_statistics,
    parse_show_ip_interface_brief,
    parse_show_spanning_tree,
)
from packet_tracer_mcp.infrastructure.execution.file_bridge import FileBridge
from packet_tracer_mcp.infrastructure.execution.frame_observer_probe import (
    PacketTracerFrameObserverProbe,
)
from packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (
    TRACE_LIMIT_MAX,
    SimulationTraceRuntime,
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
from packet_tracer_mcp.infrastructure.execution.probe_runtime import (
    PacketTracerBridgeProbeRuntime,
)
from packet_tracer_mcp.infrastructure.execution.serial_orientation_runtime import (
    PacketTracerSerialOrientationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.typed_ping import (
    TypedPingExecutor,
)
from packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)
from packet_tracer_mcp.shared.utils import (
    same_interface_name,
    serialize_typed_ping_evidence,
)


GOVERNED_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = "feature/runtime-ripv2"
EXPECTED_UPSTREAM = "personal/feature/runtime-ripv2"
EVIDENCE_PATH = GOVERNED_ROOT / "data" / "cp-scale" / "live-canonical-progress.json"
CHECKPOINT_PATH = EVIDENCE_PATH.parent / "live-canonical-checkpoint.json"
FINAL_CHECKPOINT_PATH = (
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
    """One governed stage failed after the session had acquired ownership.

    `stage_evidence` is whatever that stage had already journalled when it gave
    up. A stage that fails is exactly the stage whose read-backs are worth
    keeping, and they only exist inside `_execute_stage` until it returns.
    """

    def __init__(
        self,
        message: str,
        *,
        stage_evidence: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage_evidence = stage_evidence


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


def _write_checkpoint_summary(
    stage: str,
    evidence: dict[str, object],
    *,
    destination: Path = CHECKPOINT_PATH,
) -> None:
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
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    payload = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)


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


def _trunk_vlan_traversal_evidence(plan, result) -> list[dict[str, object]]:
    """Project typed trunk verification into human-auditable path evidence."""
    expectations = {
        item.id: item for item in plan.verification_expectations
        if item.kind is VerificationKind.TRUNK
    }
    evidence: list[dict[str, object]] = []
    for item in result.verification_results:
        expectation = expectations.get(item.expectation_id)
        if expectation is None:
            continue
        evidence.append({
            "expectation_id": item.expectation_id,
            "device_id": expectation.device_id,
            "device_name": expectation.device_name,
            "interface": str(expectation.expected.get("interface", "")),
            "expected_vlans": sorted({
                int(vlan)
                for vlan in expectation.expected.get("allowed_vlans", [])
            }),
            "status": item.status.value,
            "evidence_method": item.evidence_method,
            "fresh_evidence": item.fresh_evidence,
            "fields": {
                name: status.value for name, status in sorted(item.fields.items())
            },
            "message": item.message,
        })
    return evidence


def _record_configuration_attempt(
    evidence: dict[str, object], plan, result,
) -> None:
    """Persist the typed result and its named trunk projection before judging."""
    attempts = evidence.setdefault("configuration_attempts", [])
    assert isinstance(attempts, list)
    attempts.append(result.model_dump(mode="json"))

    traversal = _trunk_vlan_traversal_evidence(plan, result)
    traversal_attempts = evidence.setdefault("trunk_vlan_traversal_attempts", [])
    assert isinstance(traversal_attempts, list)
    traversal_attempts.append(traversal)
    # Convenience view of the latest attempt. It is intentionally written
    # before contradiction handling, so a failed stage cannot lose the names
    # behind opaque expectation identifiers.
    evidence["trunk_vlan_traversal"] = traversal


def _dhcp_server_binding_evidence(
    ios: ControlledIosExecutor,
    configuration_plan,
    voice_plan,
) -> list[dict[str, object]]:
    """Observe server lease effects without promoting DHCP_POOL read-back."""
    pools = [
        action for action in configuration_plan.actions
        if action.action_type is ConfigurationActionType.CONFIGURE_DHCP_POOL
    ]
    voice_segments = {
        assignment.voice_segment_id for assignment in voice_plan.phone_assignments
    } if voice_plan is not None else set()
    pools_by_device: dict[str, list[object]] = collections.defaultdict(list)
    for pool in pools:
        pools_by_device[pool.device_name].append(pool)

    evidence: list[dict[str, object]] = []
    for device_name, device_pools in sorted(pools_by_device.items()):
        show = ios.execute(
            device_name, OperationalQueryId.SHOW_IP_DHCP_BINDING,
        )
        rows = parse_show_ip_dhcp_binding(show.output) if show.executed else []
        rejection = ios_rejection_reason(show.output)
        identity_confirmed = bool(
            show.observed_device_name == device_name
            and show.device_identity_provenance == "confirmed_unique"
        )
        # A complete table with at least one typed row proves that the parser
        # can read this build's table. With no rows at all, an unfamiliar empty
        # rendering and a genuinely empty table stay deliberately indistinct.
        table_readable = bool(
            show.executed
            and show.fresh_output_observed
            and show.output_complete
            and not rejection
            and identity_confirmed
            and rows
        )
        addresses = sorted(
            {row.ip_address for row in rows},
            key=lambda value: int(ipaddress.ip_address(value)),
        )
        pool_evidence: list[dict[str, object]] = []
        for pool in sorted(device_pools, key=lambda item: item.segment_id):
            network = ipaddress.ip_network(
                f"{pool.network}/{pool.prefix}", strict=True,
            )
            matched = [
                address for address in addresses
                if ipaddress.ip_address(address) in network
            ]
            pool_evidence.append({
                "segment_id": pool.segment_id,
                "network": str(network),
                "voice": pool.segment_id in voice_segments,
                "binding_count": len(matched) if table_readable else None,
                "bindings": matched if table_readable else [],
            })
        evidence.append({
            "device_name": device_name,
            "query_id": OperationalQueryId.SHOW_IP_DHCP_BINDING.value,
            "executed": show.executed,
            "fresh_output_observed": show.fresh_output_observed,
            "output_complete": show.output_complete,
            "truncated_by_pager": show.truncated_by_pager,
            "pager_pages_captured": show.pager_pages_captured,
            "failure_reason": show.failure_reason,
            "ios_rejection": rejection or "",
            "observed_device_name": show.observed_device_name,
            "device_identity_provenance": show.device_identity_provenance,
            "device_identity_evidence": show.device_identity_evidence,
            "device_identity_confirmed": identity_confirmed,
            "table_readable": table_readable,
            "bindings": addresses if table_readable else [],
            "pools": pool_evidence,
            "output": show.output,
        })
    return evidence


def _scoped_dhcp_subinterface(
    configuration_plan, device_name: str, segment_id: str,
) -> str:
    """Render the one subinterface a segment owns on a device, or nothing."""
    subinterfaces = [
        action for action in configuration_plan.actions
        if action.action_type is ConfigurationActionType.CONFIGURE_SUBINTERFACE
        and action.device_name == device_name
        and action.segment_id == segment_id
    ]
    if len(subinterfaces) != 1:
        return ""
    return (
        f"{subinterfaces[0].parent_interface}.{subinterfaces[0].vlan_id}"
    )


def _voice_dhcp_statistics_target(
    configuration_plan,
    voice_plan,
) -> dict[str, str] | None:
    """Return one server/interface target only when voice scope is unique.

    The target carries a CONTROL scope beside the voice one, and is refused
    without it. Packet Tracer support for the interface-scoped form is UNKNOWN,
    and a build that accepted the interface token and answered with the GLOBAL
    table would be indistinguishable from a scoped answer -- while carrying the
    data clients that acquire inside this very window. A second pool-backed
    subinterface on the SAME server is what makes that difference observable.
    """
    if voice_plan is None:
        return None
    voice_segments = {
        assignment.voice_segment_id for assignment in voice_plan.phone_assignments
    }
    if len(voice_segments) != 1:
        return None
    segment_id = next(iter(voice_segments))
    pools = [
        action for action in configuration_plan.actions
        if action.action_type is ConfigurationActionType.CONFIGURE_DHCP_POOL
        and action.segment_id == segment_id
    ]
    if len(pools) != 1:
        return None
    device_name = pools[0].device_name
    interface = _scoped_dhcp_subinterface(
        configuration_plan, device_name, segment_id,
    )
    if not interface:
        return None
    control_segments = sorted(
        candidate for candidate in {
            action.segment_id for action in configuration_plan.actions
            if action.action_type is ConfigurationActionType.CONFIGURE_DHCP_POOL
            and action.device_name == device_name
            and action.segment_id != segment_id
        }
        if _scoped_dhcp_subinterface(configuration_plan, device_name, candidate)
    )
    if not control_segments:
        return None
    control_segment_id = control_segments[0]
    return {
        "device_name": device_name,
        "interface": interface,
        "segment_id": segment_id,
        "control_interface": _scoped_dhcp_subinterface(
            configuration_plan, device_name, control_segment_id,
        ),
        "control_segment_id": control_segment_id,
    }


def _dhcp_server_statistics_observation(
    ios: ControlledIosExecutor,
    target: dict[str, str],
) -> dict[str, object]:
    """Read one voice-scoped cumulative counter set, preserving every gate."""
    device_name = target.get("device_name", "")
    interface = target.get("interface", "")
    show = ios.execute(
        device_name,
        OperationalQueryId.SHOW_IP_DHCP_SERVER_STATISTICS_INTERFACE,
        interface=interface,
    )
    rejection = ios_rejection_reason(show.output)
    statistics = (
        parse_show_ip_dhcp_server_statistics(show.output)
        if show.executed else None
    )
    identity_confirmed = bool(
        show.observed_device_name == device_name
        and show.device_identity_provenance == "confirmed_unique"
    )
    usable = bool(
        show.executed
        and show.fresh_output_observed
        and show.output_complete
        and not rejection
        and identity_confirmed
        and statistics is not None
    )
    counters = (
        {
            "discover_received": statistics.discover_received,
            "offer_sent": statistics.offer_sent,
            "request_received": statistics.request_received,
            "ack_sent": statistics.ack_sent,
            "nak_sent": statistics.nak_sent,
        }
        if usable and statistics is not None else None
    )
    return {
        **target,
        "query_id": (
            OperationalQueryId
            .SHOW_IP_DHCP_SERVER_STATISTICS_INTERFACE.value
        ),
        "executed": show.executed,
        "fresh_output_observed": show.fresh_output_observed,
        "output_complete": show.output_complete,
        "truncated_by_pager": show.truncated_by_pager,
        "pager_pages_captured": show.pager_pages_captured,
        "failure_reason": show.failure_reason,
        "ios_rejection": rejection or "",
        "observed_device_name": show.observed_device_name,
        "device_identity_provenance": show.device_identity_provenance,
        "device_identity_evidence": show.device_identity_evidence,
        "device_identity_confirmed": identity_confirmed,
        "usable": usable,
        "counters": counters,
        "output": show.output,
    }


def _dhcp_server_statistics_point(
    ios: ControlledIosExecutor,
    target: dict[str, str],
) -> dict[str, object]:
    """Read BOTH scopes at one point, never the voice one alone.

    The pair is what carries the scope question through to the delta. Reading
    the voice subinterface by itself cannot say whether this build answered for
    that interface or for the whole server, and the two readings are only
    comparable when they are taken at the same governed point.
    """
    return {
        "voice": _dhcp_server_statistics_observation(ios, target),
        "control": _dhcp_server_statistics_observation(ios, {
            "device_name": target.get("device_name", ""),
            "interface": target.get("control_interface", ""),
            "segment_id": target.get("control_segment_id", ""),
        }),
    }


def _scope_observation(point: object, scope: str) -> dict[str, object]:
    """One scope of a paired point. A missing scope is unusable, not zero."""
    if isinstance(point, dict) and isinstance(point.get(scope), dict):
        return point[scope]
    return {}


_DHCP_STATISTIC_COUNTERS = (
    "discover_received",
    "offer_sent",
    "request_received",
    "ack_sent",
    "nak_sent",
)


def _dhcp_counter_delta(
    baseline: dict[str, object], post: dict[str, object],
) -> tuple[dict[str, int] | None, str]:
    """Subtract two observations of ONE scope, or refuse and say why.

    Every refusal returns None. No path here turns a missing, incompatible or
    decreasing observation into a zero delta: zero is what two real captures of
    the same scope produced, and nothing else may render it.
    """
    for field in ("device_name", "interface", "segment_id"):
        if baseline.get(field) != post.get(field):
            return None, "baseline and post observation target different scopes"
    if not baseline.get("usable") or not post.get("usable"):
        return None, "baseline or post observation was not usable"
    before, after = baseline.get("counters"), post.get("counters")
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None, "counters were not typed"
    if any(
        type(before.get(field)) is not int or type(after.get(field)) is not int
        for field in _DHCP_STATISTIC_COUNTERS
    ):
        return None, "counters were incomplete"
    delta = {
        field: int(after[field]) - int(before[field])
        for field in _DHCP_STATISTIC_COUNTERS
    }
    if any(value < 0 for value in delta.values()):
        # A cumulative counter that went down did not observe negative DHCP.
        # These two captures stopped being two points of one series.
        return None, "counters reset or wrapped inside the acquisition window"
    return delta, ""


def _dhcp_server_statistics_delta(
    baseline: dict[str, object],
    post: dict[str, object],
    *,
    voice_binding_count: int | None,
) -> dict[str, object]:
    """Classify one attributable voice-interface DORA counter delta.

    The classification is only reached once the interface argument is OBSERVED
    to scope. Packet Tracer support for the scoped form stays UNKNOWN until a
    live run says otherwise, and a build that answered every interface with the
    global table would hand this function the data clients that acquire inside
    the same window -- as if the voice subinterface had seen them.
    """
    evidence: dict[str, object] = {
        "baseline": baseline,
        "post": post,
        "voice_binding_count": voice_binding_count,
        "delta_readable": False,
        "counters": None,
        "control_counters": None,
        "scope_discriminated": False,
        "fork": "UNOBSERVABLE",
        "failure_reason": "",
    }
    delta, reason = _dhcp_counter_delta(
        _scope_observation(baseline, "voice"), _scope_observation(post, "voice"),
    )
    if delta is None:
        evidence["failure_reason"] = f"Voice-scoped DHCP statistics {reason}."
        return evidence
    control, control_reason = _dhcp_counter_delta(
        _scope_observation(baseline, "control"),
        _scope_observation(post, "control"),
    )
    if control is None:
        evidence["failure_reason"] = (
            f"The DHCP statistics control scope {control_reason}, so this "
            "build was never observed to scope the read to one interface."
        )
        return evidence
    evidence["control_counters"] = control
    # Two different subinterfaces that reported the SAME counters were not two
    # scopes. That is only harmless when the control scope observed nothing at
    # all: a global table could not have read zero across this window, and a
    # server with no traffic has nothing to confound the voice counters with.
    evidence["scope_discriminated"] = control != delta or not any(control.values())
    if not evidence["scope_discriminated"]:
        evidence["fork"] = "SCOPE_UNPROVEN"
        evidence["failure_reason"] = (
            "The voice and control subinterfaces reported identical non-zero "
            "counters, so the interface argument did not scope this read and "
            "the delta cannot be attributed to the voice exchange."
        )
        return evidence

    discover = delta["discover_received"]
    offer = delta["offer_sent"]
    request = delta["request_received"]
    ack = delta["ack_sent"]
    nak = delta["nak_sent"]
    if discover == 0:
        fork = (
            "A_NO_DISCOVER"
            if offer == request == ack == nak == 0
            else "UNCLASSIFIED_COUNTER_PATTERN"
        )
    elif offer == 0:
        fork = (
            "B_DISCOVER_WITHOUT_OFFER"
            if request == ack == nak == 0
            else "UNCLASSIFIED_COUNTER_PATTERN"
        )
    elif request == 0:
        fork = (
            "C_OFFER_WITHOUT_REQUEST"
            if ack == nak == 0
            else "UNCLASSIFIED_COUNTER_PATTERN"
        )
    elif ack == 0:
        fork = "D_REQUEST_WITHOUT_ACK"
    elif voice_binding_count is None:
        fork = "ACK_OBSERVED_BINDING_UNOBSERVABLE"
    elif voice_binding_count == 0:
        fork = "E_ACK_WITHOUT_BINDING"
    else:
        fork = "SERVER_EXCHANGE_AND_BINDING_OBSERVED"
    evidence.update({
        "delta_readable": True,
        "counters": delta,
        "fork": fork,
    })
    return evidence


def _voice_binding_count(
    binding_evidence: list[dict[str, object]],
    target: dict[str, str],
) -> int | None:
    matches = [
        pool.get("binding_count")
        for device in binding_evidence
        if device.get("device_name") == target.get("device_name")
        for pool in (
            device.get("pools")
            if isinstance(device.get("pools"), list) else []
        )
        if isinstance(pool, dict)
        and pool.get("segment_id") == target.get("segment_id")
        and pool.get("voice") is True
    ]
    return matches[0] if len(matches) == 1 and type(matches[0]) is int else None


# ----------------------------------------------------------------------
# POST_FAILURE_SIMULATION_DIAGNOSTIC
#
# Simulation mode changes EXECUTION SEMANTICS: packets stop progressing on
# their own and have to be stepped. That is why this runs only after the voice
# stage has already failed and been read back -- entering Simulation during the
# realtime acquisition window would not observe the tested condition, it would
# replace it.
#
# This slice classifies NOTHING. CP-SCALE does not yet know how this build
# represents DHCP, and a label invented here would be indistinguishable from an
# observation later. The product is the raw capture.
# ----------------------------------------------------------------------

#: Simulation time is the primary diagnostic bound.  The remaining ceilings
#: are independent fail-safes, not alternate ways to infer a negative result.
_SIMULATION_TARGET_TIME_SPAN = 60_000
_SIMULATION_STEP_BATCH_SIZE = 10
_SIMULATION_HARD_MAX_STEPS = 600
_SIMULATION_HARD_WALL_CLOCK_SECONDS = 120
_SIMULATION_GLOBAL_EVENT_LIST_CEILING = 2_500
_SIMULATION_STALL_BATCH_LIMIT = 3
_REPRESENTATIVE_PHONE_NAME = "LARGE-BRANCH-CAMPUS-FLOOR-1-ZONE-A-PHONE-02"
_REPRESENTATIVE_SWITCH_NAME = "Switch5"
_CONTROL_ENDPOINT_NAME = "LARGE-BRANCH-CAMPUS-FLOOR-1-ZONE-A-PC-01"
_VOICE_GATEWAY_NAME = "Router4"
#: Re-checked against THIS run before any capture is attributed to the phone.
_PHONE_PREREQUISITES = (
    ("endpoint_interface", "Vlan20"),
    ("endpoint_interface_present", True),
    ("endpoint_address_channel", True),
    ("endpoint_dhcp_enabled", True),
    ("endpoint_ipv4", ""),
)


def _endpoint_attachment(projection, device_name: str) -> dict[str, str] | None:
    """The one planned device with this name and the one link that attaches it."""
    devices = [
        item for item in projection.topology.devices if item.name == device_name
    ]
    if len(devices) != 1:
        return None
    device = devices[0]
    links = [
        item for item in projection.topology.links
        if device.id in (item.device_a_id, item.device_b_id)
    ]
    if len(links) != 1:
        return None
    link = links[0]
    near_is_a = link.device_a_id == device.id
    peer_id = link.device_b_id if near_is_a else link.device_a_id
    peers = [item for item in projection.topology.devices if item.id == peer_id]
    return {
        "device_name": device.name,
        "device_id": device.id,
        "model": getattr(device, "model", ""),
        "endpoint_port": link.port_a if near_is_a else link.port_b,
        "peer_id": peer_id,
        "peer_name": peers[0].name if len(peers) == 1 else "",
        "peer_port": link.port_b if near_is_a else link.port_a,
    }


def _representative_phone_evidence(
    projection, voice_evidence, device_name: str,
) -> dict[str, object]:
    """Re-establish the representative's prerequisites from THIS run.

    A phone that already holds an address, or whose channel could not be read,
    cannot carry a solicitation this window would be about. Failing any of them
    yields no trace at all -- never a quiet substitution of a different phone.
    """
    evidence: dict[str, object] = {
        "device_name": device_name,
        "attachment": None,
        "registration": None,
        "prerequisites_met": False,
        "failure_reason": "",
    }
    attachment = _endpoint_attachment(projection, device_name)
    evidence["attachment"] = attachment
    if attachment is None:
        evidence["failure_reason"] = (
            f"The representative endpoint {device_name!r} was not uniquely "
            "attributable to one planned device and one link."
        )
        return evidence
    result = voice_evidence.get("result")
    registrations = (
        result.get("registrations") if isinstance(result, dict) else None
    )
    rows = [
        item for item in (registrations if isinstance(registrations, list) else [])
        if isinstance(item, dict) and item.get("phone_id") == attachment["device_id"]
    ]
    if len(rows) != 1:
        evidence["failure_reason"] = (
            f"This run carried {len(rows)} registration row(s) for "
            f"{device_name!r}; exactly one is required to attribute a capture."
        )
        return evidence
    row = rows[0]
    evidence["registration"] = {
        field: row.get(field) for field in (
            "phone_id", "extension", "status", "evidence_method", "fresh_evidence",
            "endpoint_interface", "endpoint_interface_present",
            "endpoint_address_channel", "endpoint_dhcp_enabled", "endpoint_ipv4",
        )
    }
    unmet = [
        field for field, expected in _PHONE_PREREQUISITES
        if row.get(field) != expected
    ]
    if unmet:
        evidence["failure_reason"] = (
            f"{device_name!r} did not hold the representative prerequisites in "
            "this run: " + ", ".join(unmet)
        )
        return evidence
    evidence["prerequisites_met"] = True
    return evidence


def _simulation_state_dict(state) -> dict[str, object]:
    return {
        "observed": state.observed,
        "simulation_mode": state.simulation_mode,
        "frames": state.frames,
        "sim_time": state.sim_time,
        "current_index": state.current_index,
        "message": state.message,
    }


def _simulation_mode_dict(mode) -> dict[str, object]:
    return {
        "observed": mode.observed, "before": mode.before, "after": mode.after,
        "frames": mode.frames, "message": mode.message,
    }


def _simulation_step_dict(step) -> dict[str, object]:
    return {
        "observed": step.observed,
        "simulation_mode": step.simulation_mode,
        "frames_before": step.frames_before,
        "frames_after": step.frames_after,
        "sim_time": step.sim_time,
        "current_index": step.current_index,
        "message": step.message,
    }


def _progression_evidence(
    *,
    target_sim_time_span: int | float,
    step_batch_size: int,
    hard_max_steps: int,
    hard_wall_clock_seconds: int | float,
    global_event_list_ceiling: int,
    stall_batch_limit: int,
) -> dict[str, object]:
    """One conservative evidence shape for every bounded terminal path."""
    return {
        "limits": {
            "target_sim_time_span": target_sim_time_span,
            "step_batch_size": step_batch_size,
            "hard_max_steps": hard_max_steps,
            "hard_wall_clock_seconds": hard_wall_clock_seconds,
            "global_event_list_ceiling": global_event_list_ceiling,
            "stall_batch_limit": stall_batch_limit,
        },
        "monotonicity_policy": (
            "Each post-batch pure simulation-time read must be greater than or "
            "equal to the preceding read; a decrease terminates the window."
        ),
        "stall_policy": (
            f"Terminate after {stall_batch_limit} consecutive completed batches "
            "whose pure simulation-time read does not advance."
        ),
        "termination_reason": "",
        "start_state": None,
        "end_state": None,
        "simulation_time_start": None,
        "simulation_time_end": None,
        "simulation_time_span": None,
        "global_frames_start": None,
        "global_frames_end": None,
        "steps_completed": 0,
        "batches_completed": 0,
        "stall_batches": 0,
        "wall_clock_elapsed_seconds": 0.0,
        "progress": [],
        # Every terminal reason is a capture boundary, never evidence of absence.
        "negative_absence_interpretable": False,
    }


def _usable_simulation_progress_state(state) -> bool:
    return bool(
        state.observed
        and state.simulation_mode
        and type(state.frames) is int
        and state.frames >= 0
    )


def _usable_simulation_time(value) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def _bounded_simulation_progression(
    runtime,
    *,
    target_sim_time_span: int | float = _SIMULATION_TARGET_TIME_SPAN,
    step_batch_size: int = _SIMULATION_STEP_BATCH_SIZE,
    hard_max_steps: int = _SIMULATION_HARD_MAX_STEPS,
    hard_wall_clock_seconds: int | float = _SIMULATION_HARD_WALL_CLOCK_SECONDS,
    global_event_list_ceiling: int = _SIMULATION_GLOBAL_EVENT_LIST_CEILING,
    stall_batch_limit: int = _SIMULATION_STALL_BATCH_LIMIT,
    monotonic=time.monotonic,
) -> dict[str, object]:
    """Advance in fixed batches until simulation time or one hard ceiling wins.

    Each successful batch is followed by a PURE state read.  The complete step
    and state observations are retained even when that read fires a ceiling.
    No terminal reason makes a missing packet interpretable as a negative.
    """
    evidence = _progression_evidence(
        target_sim_time_span=target_sim_time_span,
        step_batch_size=step_batch_size,
        hard_max_steps=hard_max_steps,
        hard_wall_clock_seconds=hard_wall_clock_seconds,
        global_event_list_ceiling=global_event_list_ceiling,
        stall_batch_limit=stall_batch_limit,
    )
    started = monotonic()
    initial = runtime.read_simulation_state()
    initial_dict = _simulation_state_dict(initial)
    evidence["start_state"] = initial_dict
    evidence["end_state"] = initial_dict
    if not _usable_simulation_progress_state(initial):
        evidence["termination_reason"] = "SIMULATION_STATE_UNOBSERVABLE"
        evidence["wall_clock_elapsed_seconds"] = max(0.0, monotonic() - started)
        return evidence
    if not _usable_simulation_time(initial.sim_time):
        evidence["termination_reason"] = "SIM_TIME_UNOBSERVABLE"
        evidence["wall_clock_elapsed_seconds"] = max(0.0, monotonic() - started)
        return evidence

    start_sim_time = initial.sim_time
    previous_sim_time = initial.sim_time
    evidence.update({
        "simulation_time_start": start_sim_time,
        "simulation_time_end": start_sim_time,
        "simulation_time_span": 0,
        "global_frames_start": initial.frames,
        "global_frames_end": initial.frames,
    })
    if initial.frames >= global_event_list_ceiling:
        evidence["termination_reason"] = "EVENT_LIST_CEILING"
        evidence["wall_clock_elapsed_seconds"] = max(0.0, monotonic() - started)
        return evidence

    elapsed = 0.0
    while not evidence["termination_reason"]:
        completed = int(evidence["steps_completed"])
        if completed >= hard_max_steps:
            evidence["termination_reason"] = "HARD_MAX_STEPS_REACHED"
            break
        if elapsed >= hard_wall_clock_seconds:
            evidence["termination_reason"] = "HARD_WALL_CLOCK_REACHED"
            break

        requested = min(step_batch_size, hard_max_steps - completed)
        step = runtime.step("forward", times=requested)
        entry: dict[str, object] = {
            "batch": int(evidence["batches_completed"]) + 1,
            "steps_requested": requested,
            "cumulative_steps": completed,
            "step": _simulation_step_dict(step),
            "state": None,
        }
        progress = evidence["progress"]
        assert isinstance(progress, list)
        progress.append(entry)
        if not (step.observed and step.simulation_mode):
            evidence["termination_reason"] = "STEP_FAILED"
            elapsed = max(0.0, monotonic() - started)
            evidence["wall_clock_elapsed_seconds"] = elapsed
            entry["wall_clock_elapsed_seconds"] = elapsed
            break

        completed += requested
        evidence["steps_completed"] = completed
        evidence["batches_completed"] = int(evidence["batches_completed"]) + 1
        entry["cumulative_steps"] = completed

        state = runtime.read_simulation_state()
        state_dict = _simulation_state_dict(state)
        entry["state"] = state_dict
        evidence["end_state"] = state_dict
        elapsed = max(0.0, monotonic() - started)
        evidence["wall_clock_elapsed_seconds"] = elapsed
        entry["wall_clock_elapsed_seconds"] = elapsed
        if not _usable_simulation_progress_state(state):
            evidence["termination_reason"] = "SIMULATION_STATE_UNOBSERVABLE"
            break
        if not _usable_simulation_time(state.sim_time):
            evidence["termination_reason"] = "SIM_TIME_UNOBSERVABLE"
            break

        current_sim_time = state.sim_time
        evidence["simulation_time_end"] = current_sim_time
        evidence["simulation_time_span"] = current_sim_time - start_sim_time
        evidence["global_frames_end"] = state.frames
        entry["simulation_time_span"] = evidence["simulation_time_span"]

        if current_sim_time < previous_sim_time:
            evidence["termination_reason"] = "SIM_TIME_NON_MONOTONIC"
            break
        if current_sim_time == previous_sim_time:
            evidence["stall_batches"] = int(evidence["stall_batches"]) + 1
        else:
            evidence["stall_batches"] = 0
        entry["stall_batches"] = evidence["stall_batches"]
        previous_sim_time = current_sim_time

        if state.frames >= global_event_list_ceiling:
            evidence["termination_reason"] = "EVENT_LIST_CEILING"
        elif current_sim_time - start_sim_time >= target_sim_time_span:
            evidence["termination_reason"] = "TARGET_SIM_TIME_SPAN_REACHED"
        elif completed >= hard_max_steps:
            evidence["termination_reason"] = "HARD_MAX_STEPS_REACHED"
        elif elapsed >= hard_wall_clock_seconds:
            evidence["termination_reason"] = "HARD_WALL_CLOCK_REACHED"
        elif int(evidence["stall_batches"]) >= stall_batch_limit:
            evidence["termination_reason"] = "SIM_TIME_STALLED"

    return evidence


def _traced_hop_dict(hop) -> dict[str, object]:
    """Every measured field. A summary here would be evidence nobody can re-read."""
    return {
        "index": hop.index,
        "device": hop.device,
        "previous_device": hop.previous_device,
        "in_port": hop.in_port,
        "out_port": hop.out_port,
        "source": hop.source,
        "destination": hop.destination,
        "traffic_type_raw": hop.traffic_type_raw,
        "traffic_type": hop.traffic_type,
        "sim_time": hop.sim_time,
        "transit_time": hop.transit_time,
        "status": hop.status,
        "decisions": [
            {
                "layer": item.layer,
                "inbound": item.inbound,
                "description": item.description,
            }
            for item in hop.decisions
        ],
    }


def _packet_trace_dict(trace) -> dict[str, object]:
    return {
        "observed": trace.observed,
        "simulation_mode": trace.simulation_mode,
        # Global, never a filtered match count: it cannot support an absence.
        "total_in_event_list": trace.total_in_event_list,
        "requested_limit": trace.requested_limit,
        "effective_limit": trace.effective_limit,
        "limit_reached": trace.limit_reached,
        "hops_captured": len(trace.hops),
        "message": trace.message,
        "hops": [_traced_hop_dict(hop) for hop in trace.hops],
    }


# ----------------------------------------------------------------------
# VOICE_REALTIME_CONTINUITY
#
# The two windows are not interchangeable and must never be confused:
#
#   NORMAL_WINDOW  -- Realtime only. The authoritative voice acquisition and
#                     its verification. This is what 0/21 is a statement about.
#   POST_FAILURE_SIMULATION_DIAGNOSTIC -- Simulation, bounded stepping,
#                     diagnostic only, never configuration verification.
#
# In Simulation mode packets do not progress autonomously, so a 180-second
# convergence window that elapsed while it was active did not measure what the
# same wall clock measures in Realtime. Proving both edges of the authoritative
# window were Realtime is what makes its result attributable at all.
# ----------------------------------------------------------------------


def _voice_window_state(runtime) -> dict[str, object]:
    """One PURE boundary observation of the authoritative window."""
    return _simulation_state_dict(runtime.read_simulation_state())


def _realtime_boundary_error(state: dict[str, object] | None, edge: str) -> str:
    if not isinstance(state, dict) or not state.get("observed"):
        return (
            f"The simulation state {edge} the authoritative voice window was not "
            "observable, so the window cannot be attributed to REALTIME."
        )
    if state.get("simulation_mode"):
        return (
            f"Packet Tracer was in Simulation mode {edge} the authoritative voice "
            "window. Packets do not progress autonomously there, so the window "
            "is not a REALTIME acquisition."
        )
    return ""


#: Los dos únicos estados que la decisión distingue, exactamente como IOS los
#: imprime en la columna `Sts`. Cualquier otro estado REAL se conserva como
#: OTHER_OBSERVED con su token intacto: leer un `LRN` como FORWARDING o como
#: BLOCKING inventaría justo la mitad del experimento que falta medir.
_STP_FORWARDING_STATE = "fwd"
_STP_BLOCKING_STATE = "blk"


def _phone_edge_port_derivation(projection):
    """Los puertos con teléfono de esta etapa, y lo que quedó fuera de serlos.

    E7 ata cada teléfono a la acción de acceso tipada que lo sostiene, así que
    el conjunto SALE del plan: nombrar `Fa0/1-21` acá convertiría la evidencia
    en su propia hipótesis. Una asignación cuya acción no es un puerto de
    acceso tipado -- un trunk, o una acción que ya no existe -- no es un puerto
    de borde, y se registra como excluida en vez de desaparecer en silencio.
    """
    plan = getattr(projection, "voice", None)
    assignments = list(getattr(plan, "phone_assignments", []) or [])
    if not assignments:
        return [], []
    configuration = getattr(projection, "configuration", None)
    access_by_id = {
        action.id: action
        for action in getattr(configuration, "actions", []) or []
        if isinstance(action, ConfigureAccessPort)
    }
    ports: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for assignment in assignments:
        action_id = getattr(assignment, "access_configuration_action_id", None)
        if not isinstance(action_id, str):
            # Recolectar evidencia NUNCA puede ser el motivo por el que una
            # etapa gobernada se cae. Una asignación que no es del tipo del
            # plan no aporta un puerto y se dice, no revienta.
            excluded.append({
                "access_configuration_action_id": "",
                "reason": "NOT_A_TYPED_PHONE_ASSIGNMENT",
            })
            continue
        access = access_by_id.get(action_id)
        if access is None:
            excluded.append({
                "access_configuration_action_id": action_id,
                "reason": "NOT_A_TYPED_ACCESS_PORT",
            })
            continue
        key = (access.device_name, access.interface)
        if key in seen:
            continue
        seen.add(key)
        ports.append({
            "device_name": access.device_name,
            "interface": access.interface,
            "vlan_id": assignment.voice_vlan_id,
            "access_configuration_action_id": action_id,
        })
    ports.sort(key=lambda item: (item["device_name"], item["interface"]))
    excluded.sort(key=lambda item: item["access_configuration_action_id"])
    return ports, excluded


def _phone_edge_ports(projection) -> list[dict[str, object]]:
    """Cada puerto de acceso con teléfono que esta etapa realmente configuró."""
    return _phone_edge_port_derivation(projection)[0]


def _stp_source_error(show, rejection: str) -> str:
    """Por qué esta lectura no puede sostener NINGUNA afirmación de estado.

    El orden importa: una captura cortada por el pager también viene
    incompleta, y decir sólo `OUTPUT_INCOMPLETE` perdería exactamente el hecho
    que decide si esta consulta necesita cualificación.
    """
    if not show.executed:
        return "QUERY_NOT_EXECUTED"
    if not show.fresh_output_observed:
        return "OUTPUT_NOT_FRESH"
    if rejection:
        return "IOS_REJECTED"
    if show.truncated_by_pager:
        return "PAGER_TRUNCATED"
    if not show.output_complete:
        return "OUTPUT_INCOMPLETE"
    if (
        show.observed_device_name != show.device_name
        or show.device_identity_provenance != "confirmed_unique"
    ):
        return "DEVICE_IDENTITY_NOT_CONFIRMED"
    return ""


def _stp_port_observation(port, instances, source_error: str) -> dict[str, object]:
    """Un puerto, su estado tal como PT lo imprimió, o por qué no se sabe."""
    observation: dict[str, object] = {
        "device_name": port["device_name"],
        "interface": port["interface"],
        "vlan_id": port["vlan_id"],
        "protocol": "",
        "role": "",
        "state": "",
        "cost": None,
        "priority_number": "",
        "link_type": "",
        "classification": "UNOBSERVABLE",
        "failure_reason": source_error,
    }
    if source_error:
        return observation
    instance = next(
        (item for item in instances if item.vlan_id == port["vlan_id"]), None,
    )
    if instance is None:
        # Una instancia ausente NO es un puerto bloqueado. Es una tabla que no
        # dice nada sobre esta VLAN.
        observation["failure_reason"] = "VLAN_INSTANCE_ABSENT"
        return observation
    observation["protocol"] = instance.protocol
    row = next(
        (
            item for item in instance.interfaces
            if same_interface_name(item.interface, str(port["interface"]))
        ),
        None,
    )
    if row is None:
        observation["failure_reason"] = "INTERFACE_ROW_ABSENT"
        return observation
    state = (row.state or "").strip()
    observation.update({
        "role": row.role,
        "state": state,
        "cost": row.cost,
        "priority_number": row.priority_number,
        "link_type": row.link_type,
    })
    if not state:
        observation["failure_reason"] = "MALFORMED_PORT_STATE"
        return observation
    folded = state.casefold()
    observation["classification"] = (
        "FORWARDING" if folded == _STP_FORWARDING_STATE
        else "BLOCKING" if folded == _STP_BLOCKING_STATE
        else "OTHER_OBSERVED"
    )
    observation["failure_reason"] = ""
    return observation


#: Una observacion logica puede ejecutar como mucho dos consultas registradas.
#: No es un lazo hasta el exito: el segundo intento existe solo para UN fallo
#: transitorio de continuacion de pager, y no hay tercero.
_STP_MAX_LOGICAL_ATTEMPTS = 2


def _stp_attempt(show, device_name: str, index: int) -> dict[str, object]:
    """La calidad cruda de UNA ejecucion registrada, sin interpretarla."""
    rejection = ios_rejection_reason(show.output) or ""
    instances = parse_show_spanning_tree(show.output) if show.executed else []
    return {
        "attempt": index,
        "executed": show.executed,
        "fresh_output_observed": show.fresh_output_observed,
        "output_complete": show.output_complete,
        "truncated_by_pager": show.truncated_by_pager,
        "pager_pages_captured": show.pager_pages_captured,
        "pager_continuation": show.pager_continuation,
        "dispatch_classification": show.dispatch_classification,
        "failure_reason": show.failure_reason,
        "observed_device_name": show.observed_device_name,
        "device_identity_provenance": show.device_identity_provenance,
        "device_identity_confirmed": bool(
            show.observed_device_name == device_name
            and show.device_identity_provenance == "confirmed_unique"
        ),
        "ios_rejection": rejection,
        "classification": classify_show_spanning_tree(
            show.output, executed=show.executed,
        ).value,
        "source_error": _stp_source_error(show, rejection),
        "vlan_instances": sorted(item.vlan_id for item in instances),
        "output": show.output,
    }


def _stp_retry_refusal(show, device_name: str) -> str:
    """Vacio solo si ESTE resultado prueba que otra consulta fresca es segura.

    El discriminador es `executed`. Tras una captura cualificada incompleta el
    ejecutor cancela el pager, y el unico camino que llega a `executed=True` es
    el de una cancelacion CONFIRMADA: si no pudo confirmarla, pone el device en
    cuarentena y devuelve `executed=False`. Un resultado ejecutado, con la
    identidad del comando intacta y el device atribuido de forma unica, es
    entonces la prueba de que el terminal volvio a un prompt.

    Todo lo demas se niega. No se debilita nada del ejecutor para permitir el
    reintento: si el terminal sigue mal, su propia guarda atomica rechazara el
    despacho y el segundo intento sera otro `executed=False`, nunca una lectura
    mal atribuida.
    """
    if not show.executed:
        return "TERMINAL_NOT_CONFIRMED_SAFE"
    try:
        dispatch = DispatchClassification(show.dispatch_classification)
    except ValueError:
        # Una clasificacion que no es del enum no prueba que el comando llego
        # intacto, y no probarlo basta para no reintentar.
        return "DISPATCH_CORRUPTED"
    if is_command_corrupted(dispatch):
        return "DISPATCH_CORRUPTED"
    if (
        show.observed_device_name != device_name
        or show.device_identity_provenance != "confirmed_unique"
    ):
        return "DEVICE_IDENTITY_NOT_CONFIRMED"
    if ios_rejection_reason(show.output):
        return "IOS_REJECTED"
    if (
        show.pager_continuation != PagerContinuation.FAILED.value
        or not show.truncated_by_pager
        or show.output_complete
    ):
        # `not_qualified` es una politica, no un fallo transitorio: repetir la
        # consulta daria exactamente la misma primera pagina.
        return "NOT_A_QUALIFIED_PAGER_FAILURE"
    return ""


def _stp_logical_observation(ios, device_name: str):
    """UNA observacion logica del arbol de expansion: dos ejecuciones a lo sumo.

    Dos comandos son dos observaciones, no una tabla reconstruida: las paginas
    y las instancias parseadas nunca se mezclan entre ejecuciones. Se selecciona
    el PRIMER intento completo, fresco y atribuido de forma unica, y es el unico
    del que sale el estado afirmado; el intento fallido se conserva entero como
    su propia evidencia.
    """
    attempts: list[dict[str, object]] = []
    retry_eligible = False
    retry_reason = ""
    for index in range(1, _STP_MAX_LOGICAL_ATTEMPTS + 1):
        show = ios.execute(device_name, OperationalQueryId.SHOW_SPANNING_TREE)
        attempt = _stp_attempt(show, device_name, index)
        attempts.append(attempt)
        if not attempt["source_error"]:
            break
        if index == _STP_MAX_LOGICAL_ATTEMPTS:
            break
        refusal = _stp_retry_refusal(show, device_name)
        if refusal:
            retry_reason = refusal
            break
        retry_eligible = True
        retry_reason = "QUALIFIED_PAGER_CONTINUATION_FAILED"

    selected = next(
        (item for item in attempts if not item["source_error"]), None,
    )
    final = selected if selected is not None else attempts[-1]
    instances = (
        parse_show_spanning_tree(str(final["output"]))
        if selected is not None else []
    )
    device = {key: value for key, value in final.items() if key != "attempt"}
    device.update({
        "device_name": device_name,
        "query_id": OperationalQueryId.SHOW_SPANNING_TREE.value,
        "max_logical_attempts": _STP_MAX_LOGICAL_ATTEMPTS,
        "attempts": attempts,
        "selected_attempt": final["attempt"] if selected is not None else None,
        "retry_eligible": retry_eligible,
        "retry_reason": retry_reason,
    })
    return device, instances


def _stp_realtime_evidence(ios, projection, *, edge: str) -> dict[str, object]:
    """El estado de borde de los puertos con teléfono, medido en Realtime.

    Es la única lectura que puede decir qué hacía el puerto DURANTE la ventana
    autoritativa de voz. Es de sólo lectura y falla cerrada: FORWARDING y
    BLOCKING se afirman sólo desde una fila fresca, completa y atribuida; todo
    lo demás queda UNOBSERVABLE, que no es lo mismo que ausencia.
    """
    ports, excluded = _phone_edge_port_derivation(projection)
    by_device: dict[str, list[dict[str, object]]] = collections.defaultdict(list)
    for port in ports:
        by_device[str(port["device_name"])].append(port)

    devices: list[dict[str, object]] = []
    observations: list[dict[str, object]] = []
    for device_name, device_ports in sorted(by_device.items()):
        device, instances = _stp_logical_observation(ios, device_name)
        devices.append(device)
        source_error = str(device["source_error"])
        for port in device_ports:
            observations.append(
                _stp_port_observation(port, instances, source_error),
            )

    counts = {
        state: sum(
            1 for item in observations if item["classification"] == state
        )
        for state in ("FORWARDING", "BLOCKING", "OTHER_OBSERVED", "UNOBSERVABLE")
    }
    return {
        "edge": edge,
        "window": "NORMAL_WINDOW",
        "mode_required": "realtime",
        "proves": (
            "The phone-facing edge state PT printed at this boundary of the "
            "authoritative window. It does NOT prove the state held for the "
            "whole window, and it is never derived from DHCP behaviour."
        ),
        "phone_ports_total": len(ports),
        "devices": devices,
        "excluded": excluded,
        "ports": observations,
        "counts": counts,
    }


#: El texto EXACTO con el que PT identifica cada frame que hay que comparar. Un
#: frame se elige por lo que Packet Tracer dijo de el, jamas por su clase cruda
#: de trafico: ningun numero de clase nombra un protocolo en este repositorio, y
#: seguir tratandolos como sinonimos seria el clasificador que no existe.
_DHCP_DISCOVER_DECISION = "dhcp client constructs a discover packet"
_BPDU_DECISION = "stp process sends out a configuration bpdu"
_STP_DROP_DECISION = "is blocked by stp"


def _decision_match(hop: dict, needle: str) -> str:
    """La decision literal que identifica este frame, o cadena vacia."""
    for decision in hop.get("decisions") or ():
        description = str(decision.get("description") or "")
        if needle in description.casefold():
            return description
    return ""


def _frame_target(hop: dict, decision: str, role: str) -> dict[str, object]:
    """Lo que hay que conservar de un frame elegido, antes de enumerarlo."""
    return {
        "role": role,
        "index": hop.get("index"),
        "device": hop.get("device"),
        "previous_device": hop.get("previous_device"),
        "in_port": hop.get("in_port"),
        "out_port": hop.get("out_port"),
        "sim_time": hop.get("sim_time"),
        "traffic_type_raw": hop.get("traffic_type_raw"),
        "status": hop.get("status"),
        "identifying_decision": decision,
    }


def _frame_observer_discovery(
    transport,
    *,
    phone_name: str,
    switch_name: str,
    phone_trace,
    switch_trace,
) -> dict[str, object]:
    """Enumera los miembros de los dos frames que la pregunta compara.

    Uno es el DHCP Discover del telefono; el otro es una BPDU que el switch
    emite por un puerto de telefono. Mismo puerto fisico NO implica misma VLAN,
    y misma captura NO implica mismo instante: por eso cada objetivo conserva su
    propio `sim_time` y su propia decision identificadora, y nada aqui deriva
    una VLAN del tipo de trafico.
    """
    observation: dict[str, object] = {
        "diagnostic": "FRAME_OBSERVER_DISCOVERY",
        "observes": (
            "Which members a Simulation frameInstance exposes on this build. "
            "It reads NO discovered member: a name is evidence that something "
            "exists, never evidence of what it means."
        ),
        "targets": [],
        "attempted": False,
        "failure_reason": "",
    }
    phone_hops = (phone_trace or {}).get("hops") or []
    switch_hops = (switch_trace or {}).get("hops") or []

    targets: list[dict[str, object]] = []
    phone_hop = next(
        (
            hop for hop in phone_hops
            if hop.get("device") == phone_name
            and _decision_match(hop, _DHCP_DISCOVER_DECISION)
        ),
        None,
    )
    if phone_hop is not None:
        targets.append(_frame_target(
            phone_hop,
            _decision_match(phone_hop, _DHCP_DISCOVER_DECISION),
            "phone_dhcp",
        ))
        # El MISMO frame en el switch, probado por el camino y no por el reloj:
        # `previous_device` dice que vino de ESTE telefono. La caida de OTRO
        # telefono en el mismo instante no es este frame.
        switch_hop = next(
            (
                hop for hop in switch_hops
                if hop.get("device") == switch_name
                and hop.get("previous_device") == phone_name
                and hop.get("traffic_type_raw") == phone_hop.get("traffic_type_raw")
                and hop.get("sim_time") == phone_hop.get("sim_time")
            ),
            None,
        )
        if switch_hop is not None:
            drop_decision = _decision_match(switch_hop, _STP_DROP_DECISION)
            targets.append(_frame_target(
                switch_hop,
                drop_decision or "",
                "switch_dhcp",
            ))
            # La comparacion mas fuerte es en el MISMO device y el MISMO puerto
            # fisico: la BPDU tiene que salir por donde entro el DHCP.
            edge_port = switch_hop.get("in_port")
            bpdu_hop = next(
                (
                    hop for hop in switch_hops
                    if hop.get("device") == switch_name
                    and hop.get("out_port") == edge_port
                    and _decision_match(hop, _BPDU_DECISION)
                ),
                None,
            )
            if bpdu_hop is not None:
                targets.append(_frame_target(
                    bpdu_hop,
                    _decision_match(bpdu_hop, _BPDU_DECISION),
                    "switch_bpdu",
                ))

    times = {
        item.get("sim_time") for item in targets
        if item.get("sim_time") is not None
    }
    # Misma captura NO es mismo instante. Sin igualdad exacta de `sim_time` no
    # se afirma simultaneidad de ninguna forma.
    observation["same_capture"] = bool(targets)
    observation["same_instant"] = bool(targets) and len(times) == 1
    observation["targets"] = targets
    indices = [
        int(item["index"]) for item in targets
        if isinstance(item.get("index"), int)
    ]
    if not indices:
        observation["failure_reason"] = (
            "No frame carried the exact identifying decision text, so there was "
            "nothing whose members could be attributed."
        )
        return observation

    observation["attempted"] = True
    discovery = PacketTracerFrameObserverProbe(
        transport.send_and_wait,
    ).discover_frame_observers(indices)
    observation["discovery"] = {
        "observed": discovery.observed,
        "simulation_mode": discovery.simulation_mode,
        "frame_count": discovery.frame_count,
        "failure_reason": discovery.failure_reason,
        "frames": [
            {
                "index": frame.index,
                "in_bounds": frame.in_bounds,
                "frame_found": frame.frame_found,
                "observed_device": frame.observed_device,
                "observed_in_port": frame.observed_in_port,
                "observed_sim_time": frame.observed_sim_time,
                "observed_traffic_type": frame.observed_traffic_type,
                "truncated": frame.truncated,
                "members": list(frame.members),
                "observers": [
                    {
                        "name": item.name,
                        "type_name": item.type_name,
                        "is_callable": item.is_callable,
                        "arity": item.arity,
                        "read_only_name": item.read_only_name,
                    }
                    for item in frame.observers
                ],
            }
            for frame in discovery.frames
        ],
    }
    # La identidad del frame se vuelve a probar contra el objetivo elegido: un
    # indice sigue nombrando un frame solo mientras ese event list siga en pie.
    by_index = {frame.index: frame for frame in discovery.frames}
    for target in targets:
        frame = by_index.get(target.get("index"))
        target["identity_reconfirmed"] = bool(
            frame is not None
            and frame.matches(
                device=str(target.get("device") or ""),
                sim_time=target.get("sim_time"),
                traffic_type=target.get("traffic_type_raw"),
            )
        )
    return observation


def _post_failure_simulation_diagnostic(
    transport,
    projection,
    voice_evidence,
    *,
    realtime_failure_established: bool = True,
    phone_name: str = _REPRESENTATIVE_PHONE_NAME,
    control_name: str = _CONTROL_ENDPOINT_NAME,
    target_sim_time_span: int | float = _SIMULATION_TARGET_TIME_SPAN,
    step_batch_size: int = _SIMULATION_STEP_BATCH_SIZE,
    hard_max_steps: int = _SIMULATION_HARD_MAX_STEPS,
    hard_wall_clock_seconds: int | float = _SIMULATION_HARD_WALL_CLOCK_SECONDS,
    global_event_list_ceiling: int = _SIMULATION_GLOBAL_EVENT_LIST_CEILING,
    stall_batch_limit: int = _SIMULATION_STALL_BATCH_LIMIT,
    monotonic=time.monotonic,
) -> dict[str, object]:
    """Bounded raw capture after the voice failure. Never raises, always restores.

    Owns one explicit window: read the original mode purely, enter Simulation
    only if it was not already there, reset, advance in fixed batches until the
    simulation-time target or one independent hard ceiling, capture four raw
    device scopes, and give the mode back verifying with ANOTHER pure read. A
    restoration that cannot be verified is recorded on its own key -- it never
    becomes, hides or overwrites the Floor-1 failure this stage already carries.
    """
    evidence: dict[str, object] = {
        "diagnostic": "POST_FAILURE_SIMULATION_DIAGNOSTIC",
        "observes": (
            "Events generated or processed AFTER entering Simulation mode, "
            "following the already-established Floor-1 voice failure. Simulation "
            "mode changes execution semantics -- packets do not progress "
            "autonomously and must be stepped -- so this is NOT the original "
            "realtime voice acquisition window and may not be described as it."
        ),
        # This slice discovers a representation; it does not judge one. Both stay
        # UNOBSERVABLE until a live capture shows how this build renders DHCP.
        "dhcp_trace_identity": "UNOBSERVABLE",
        "control_dhcp_visibility": "UNOBSERVABLE",
        "positive_control_capability": "UNSAFE_OR_MUTATING",
        "positive_control_implemented": False,
        "dhcp_positive_control_observed": "UNOBSERVABLE",
        "control_semantics": (
            "Passive same-window visibility observation only. No acquisition is "
            "forced: the repository's governed DHCP acquisition paths mutate an "
            "endpoint or disposable probe topology/configuration. An empty PC-01 "
            "trace does not establish event-list eligibility and says nothing "
            "about the representative phone's own switching path."
        ),
        "phone": None,
        "control_name": control_name,
        "status": "ATTEMPTED",
        "captured": False,
        "restoration_verified": False,
        "failure_reason": "",
        "post_failure_simulation_state": {
            "phone_address_readback": "DEFERRED",
            "router4_voice_binding_readback": "DEFERRED",
            "reason": (
                "No cheap typed read-only post-restoration path is available in "
                "SimulationTraceRuntime; adding voice or IOS orchestration is deferred."
            ),
        },
    }
    if not realtime_failure_established:
        # There is no valid normal failure to diagnose. Opening a Simulation
        # window here would produce evidence about nothing, at the cost of a
        # real application-state transition.
        evidence["status"] = "NOT_APPLICABLE"
        evidence["failure_reason"] = (
            "No authoritative REALTIME voice failure was established, so there "
            "is nothing for this diagnostic to be about."
        )
        return evidence
    phone = _representative_phone_evidence(projection, voice_evidence, phone_name)
    evidence["phone"] = phone
    if not phone["prerequisites_met"]:
        evidence["failure_reason"] = str(phone["failure_reason"])
        return evidence
    attachment = phone["attachment"]
    assert isinstance(attachment, dict)
    switch_name = str(attachment["peer_name"])
    if switch_name != _REPRESENTATIVE_SWITCH_NAME:
        evidence["failure_reason"] = (
            f"The representative phone was attached to {switch_name!r}, not the "
            f"required attributable access scope {_REPRESENTATIVE_SWITCH_NAME!r}."
        )
        return evidence
    evidence["capture_scopes"] = {
        "phone": phone_name,
        "switch": switch_name,
        "router": _VOICE_GATEWAY_NAME,
        "control": control_name,
    }

    runtime = SimulationTraceRuntime(transport.send_and_wait)
    original = runtime.read_simulation_state()
    evidence["original_state"] = _simulation_state_dict(original)
    if not original.observed:
        # Nothing has been touched, and nothing may be: without an attributable
        # original there is no state to give back.
        evidence["failure_reason"] = (
            "The original simulation state was not attributable, so the mode was "
            "left untouched."
        )
        return evidence

    changed = False
    try:
        if not original.simulation_mode:
            evidence["mode_request"] = _simulation_mode_dict(
                runtime.set_simulation_mode(True),
            )
            changed = True
            entered = runtime.read_simulation_state()
            evidence["entered_state"] = _simulation_state_dict(entered)
            if not (entered.observed and entered.simulation_mode):
                evidence["failure_reason"] = (
                    "Simulation mode was requested and could not be verified."
                )
                return evidence
        evidence["window_before"] = _simulation_state_dict(
            runtime.read_simulation_state(),
        )
        reset = runtime.step("reset")
        evidence["reset"] = _simulation_step_dict(reset)
        if reset.observed and reset.simulation_mode:
            progression = _bounded_simulation_progression(
                runtime,
                target_sim_time_span=target_sim_time_span,
                step_batch_size=step_batch_size,
                hard_max_steps=hard_max_steps,
                hard_wall_clock_seconds=hard_wall_clock_seconds,
                global_event_list_ceiling=global_event_list_ceiling,
                stall_batch_limit=stall_batch_limit,
                monotonic=monotonic,
            )
        else:
            reset_state = runtime.read_simulation_state()
            progression = _progression_evidence(
                target_sim_time_span=target_sim_time_span,
                step_batch_size=step_batch_size,
                hard_max_steps=hard_max_steps,
                hard_wall_clock_seconds=hard_wall_clock_seconds,
                global_event_list_ceiling=global_event_list_ceiling,
                stall_batch_limit=stall_batch_limit,
            )
            reset_state_dict = _simulation_state_dict(reset_state)
            progression.update({
                "termination_reason": "STEP_FAILED",
                "start_state": reset_state_dict,
                "end_state": reset_state_dict,
                "progress": [{
                    "batch": 0,
                    "steps_requested": 0,
                    "cumulative_steps": 0,
                    "step": _simulation_step_dict(reset),
                    "state": reset_state_dict,
                }],
            })
        evidence["progression"] = progression
        evidence["reset_verification"] = progression["start_state"]
        evidence["window_after"] = _simulation_state_dict(
            runtime.read_simulation_state(),
        )
        traces = {
            "phone": runtime.read_trace(limit=TRACE_LIMIT_MAX, device=phone_name),
            "switch": runtime.read_trace(limit=TRACE_LIMIT_MAX, device=switch_name),
            "router": runtime.read_trace(
                limit=TRACE_LIMIT_MAX, device=_VOICE_GATEWAY_NAME,
            ),
            "control": runtime.read_trace(limit=TRACE_LIMIT_MAX, device=control_name),
        }
        for scope, trace in traces.items():
            evidence[f"{scope}_trace"] = _packet_trace_dict(trace)
        evidence["captured"] = all(trace.observed for trace in traces.values())
        if not evidence["captured"]:
            evidence["failure_reason"] = (
                "The bounded capture did not complete; what was observed is "
                "retained and no absence may be read from it."
            )
        # Still inside Simulation, on the SAME event list the traces came from:
        # a frame index only names a frame while that list stands. Nothing is
        # invoked here beyond the getters this repository already measured --
        # the question is which members exist, not what they return.
        evidence["frame_observer_discovery"] = _frame_observer_discovery(
            transport,
            phone_name=phone_name,
            switch_name=switch_name,
            phone_trace=evidence.get("phone_trace"),
            switch_trace=evidence.get("switch_trace"),
        )
    except Exception as exc:
        # The diagnostic may never be the reason a governed stage stops running
        # its own failure and cleanup.
        evidence["failure_reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        restoration: dict[str, object] = {"changed": changed}
        try:
            if changed:
                restoration["request"] = _simulation_mode_dict(
                    runtime.set_simulation_mode(original.simulation_mode),
                )
            verified = runtime.read_simulation_state()
            restoration["verification"] = _simulation_state_dict(verified)
            evidence["restoration_verified"] = bool(
                verified.observed
                and verified.simulation_mode == original.simulation_mode
            )
        except Exception as exc:
            restoration["error"] = f"{type(exc).__name__}: {exc}"
            evidence["restoration_verified"] = False
        if not evidence["restoration_verified"] and "error" not in restoration:
            restoration["error"] = (
                "Packet Tracer simulation mode could not be verified back to the "
                "observed original state."
            )
        evidence["restoration"] = restoration
    return evidence


def _stage_voice(
    projection,
    *,
    voice_runtime: PacketTracerEnterpriseVoiceRuntime,
    composition,
    configuration,
    statuses: dict,
    context: ConfigurationRuntimeContext,
    manifest,
) -> dict[str, object]:
    """Apply and judge E7 for one stage. Never claims what it did not observe.

    Three outcomes are acceptable and they are not the same thing:

      * no phone in this stage -- nothing to apply, nothing claimed;
      * applied, and every phone that E7 owns is addressed and registered;
      * applied, and the evidence is bounded -- a capability this build does
        not expose, or a phone whose state could not be read.

    Only a contradiction fails the stage: a phone observed to hold an address
    outside its voice segment, two channels disagreeing about one phone, or an
    action Packet Tracer refused. An absent observation is recorded as absent.
    """
    plan = getattr(projection, "voice", None)
    if plan is None or not plan.actions:
        return {"staged": False, "reason": "This stage carries no phone."}

    result = VoiceApplicator(voice_runtime).apply(
        plan,
        actual_source_topology_hash=projection.topology.physical_identity_hash,
        actual_source_configuration_hash=projection.configuration.semantic_hash,
        foundational_statuses=statuses,
        capabilities=composition.voice_capabilities,
        runtime_context=context,
        deployment_manifest=manifest,
    )
    evidence: dict[str, object] = {
        "staged": True,
        "result": result.model_dump(mode="json"),
        "phones": len(plan.phone_assignments),
        "actions": len(plan.actions),
    }

    refused = sorted(
        f"{item.action_id}: {item.message}" for item in result.action_results
        if item.status is ActionExecutionStatus.FAILED
    )
    if result.preflight_errors:
        evidence["error"] = "; ".join(result.preflight_errors)
        return evidence
    if refused:
        evidence["error"] = "Packet Tracer refused voice actions: " + "; ".join(refused)
        return evidence

    addressing = collections.Counter(
        item.addressing_status.value for item in result.registrations
    )
    registration = collections.Counter(
        item.status.value for item in result.registrations
    )
    evidence["addressing_by_status"] = dict(sorted(addressing.items()))
    evidence["registration_by_status"] = dict(sorted(registration.items()))
    # The voice path, one link at a time. A phone that never built its voice SVI
    # and one that built it and got no lease are different failures, and a
    # registration table that was truncated is not a statement about either.
    evidence["voice_interface_present"] = sum(
        1 for item in result.registrations if item.endpoint_interface_present
    )
    # Present is not the same as readable. A voice SVI that exposes no address
    # getter answers "" exactly like one that answered and holds no lease, and
    # only one of those is a statement about DHCP.
    evidence["voice_interface_address_channel"] = sum(
        1 for item in result.registrations if item.endpoint_address_channel
    )
    evidence["voice_interface_addressed"] = sum(
        1 for item in result.registrations
        if item.endpoint_address_channel and item.endpoint_ipv4
    )
    # And whether the phone was ever asked to acquire. A voice SVI with DHCP
    # off did not fail to lease; nothing solicited on it.
    # And the phone itself, which PT does not necessarily answer for in the
    # same place as its ports.
    evidence["voice_device_addressed"] = sorted(
        f"{item.phone_id}={item.device_ipv4}"
        for item in result.registrations if item.device_ipv4
    )
    evidence["voice_device_dhcp"] = dict(sorted(
        collections.Counter(
            "unreadable" if item.device_dhcp_enabled is None
            else ("enabled" if item.device_dhcp_enabled else "disabled")
            for item in result.registrations
        ).items()
    ))
    evidence["voice_interface_dhcp"] = dict(sorted(
        collections.Counter(
            "unreadable" if item.endpoint_dhcp_enabled is None
            else ("enabled" if item.endpoint_dhcp_enabled else "disabled")
            for item in result.registrations
        ).items()
    ))
    evidence["registration_evidence_method"] = dict(sorted(
        collections.Counter(
            item.evidence_method for item in result.registrations
        ).items()
    ))
    evidence["contradicted_addressing"] = sorted(
        f"{item.phone_id}: {item.addressing_message}"
        for item in result.registrations
        if item.addressing_status is ActionExecutionStatus.FAILED
    )
    evidence["addressed_phones"] = sorted(
        f"{item.phone_id}={item.call_control_ipv4 or item.endpoint_ipv4}"
        for item in result.registrations
        if item.addressing_status in {
            ActionExecutionStatus.VERIFIED, ActionExecutionStatus.PARTIAL,
        }
    )
    if evidence["contradicted_addressing"]:
        evidence["error"] = (
            "Observed phone addressing contradicted the plan: "
            + "; ".join(evidence["contradicted_addressing"])
        )
        return evidence
    # A registration this build cannot observe is bounded evidence, not a
    # failure; a registration it can observe and reports UNREGISTERED is a
    # contradiction of a claim the plan made.
    evidence["contradicted_registration"] = sorted(
        f"{item.phone_id}: {item.message}" for item in result.registrations
        if item.status is ActionExecutionStatus.FAILED
    )
    if evidence["contradicted_registration"]:
        evidence["error"] = (
            "Observed phone registration contradicted the plan: "
            + "; ".join(evidence["contradicted_registration"])
        )
        return evidence
    evidence["error"] = ""
    return evidence


def _execute_stage(
    projection,
    *,
    composition,
    deployment,
    delta_deployment,
    physical: PacketTracerPhysicalTopologyRuntime,
    configuration_runtime: PacketTracerEnterpriseConfigurationRuntime,
    control_runtime: PacketTracerEnterpriseControlPlaneRuntime,
    voice_runtime: PacketTracerEnterpriseVoiceRuntime,
    transport: PacketTracerHttpTransport,
    fingerprint: EnvironmentFingerprint,
    packet_tracer_version: str,
    dhcp_statistics_target: dict[str, str] | None = None,
    dhcp_statistics_baseline: dict[str, object] | None = None,
    verified_serial_topology=None,
    verified_serial_manifest=None,
) -> tuple[dict[str, object], object, object]:
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
            "voice_actions": (
                len(projection.voice.actions) if projection.voice is not None else 0
            ),
            "voice_phones": (
                len(projection.voice.phone_assignments)
                if projection.voice is not None else 0
            ),
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
    def _failed(message: str) -> CanonicalLiveFailure:
        """Fail with the journal this stage has so far, never without it."""
        return CanonicalLiveFailure(message, stage_evidence=evidence)

    if (
        deployment.status is not PhysicalDeploymentStatus.VERIFIED
        or deployment.manifest is None
    ):
        raise _failed(
            f"Physical stage {projection.stage.value!r} was not VERIFIED: "
            + "; ".join(deployment.errors)
        )

    if (verified_serial_topology is None) != (verified_serial_manifest is None):
        raise _failed(
            "Verified serial topology and manifest must be provided together."
        )
    if verified_serial_topology is None:
        orientation = SerialOrientationObserver(
            PacketTracerSerialOrientationRuntime(transport.send_and_wait),
        ).observe(projection.topology, deployment.manifest)
    else:
        orientation = inherit_verified_serial_orientation(
            projection.topology,
            deployment.manifest,
            verified_topology=verified_serial_topology,
            verified_manifest=verified_serial_manifest,
        )
    evidence["serial_orientation"] = orientation.model_dump(mode="json")
    if not orientation.verified or orientation.oriented_manifest is None:
        raise _failed(
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
    _record_configuration_attempt(
        evidence, projection.configuration, configuration,
    )
    contradiction = configuration_application_contradiction(configuration)
    evidence["configuration_contradictions"] = [contradiction]
    if contradiction:
        raise _failed(
            f"Configuration at {projection.stage.value!r} contradicted the plan: "
            + contradiction
        )

    ios = ControlledIosExecutor(transport.send_and_wait)
    serial_ready, serial_evidence = _wait_for_serial_interfaces(
        ios, _core_serial_addresses(projection),
    )
    evidence["serial_interfaces"] = serial_evidence
    if not serial_ready:
        raise _failed(
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
        _record_configuration_attempt(
            evidence, projection.configuration, configuration,
        )
        contradiction = configuration_application_contradiction(configuration)
        evidence["configuration_contradictions"].append(contradiction)
        if contradiction:
            raise _failed(
                f"Configuration re-read at {projection.stage.value!r} "
                "contradicted the plan: " + contradiction
            )
        configuration_error = canonical_stage_configuration_error(
            projection.configuration, configuration,
        )
    evidence["configuration"] = configuration.model_dump(mode="json")
    evidence["configuration_acceptance_error"] = configuration_error
    if configuration_error:
        raise _failed(
            f"Configuration at {projection.stage.value!r} exceeded its governed "
            "observability envelope: " + configuration_error
        )

    statuses = derive_foundational_statuses(
        configuration_result=configuration,
        physical_result=deployment,
    )

    # L2/VLAN/DHCP foundation is applied and verified above. Voice comes next,
    # before the control plane, because it is what turns a powered phone on a
    # voice VLAN into an addressed, registered one: option 150 on the pool the
    # foundation just created, a call control to answer, an extension per phone
    # and the configuration files they fetch. Only then is there anything to
    # verify about a phone at all.
    # The authoritative window opens here. Its first edge is observed with a
    # PURE read: a call that could change the mode would be attesting to its own
    # effect, and normalizing the mode silently would erase exactly the operator
    # state this gate exists to detect.
    voice_plan = getattr(projection, "voice", None)
    continuity: dict[str, object] | None = None
    if voice_plan is not None and voice_plan.actions:
        simulation = SimulationTraceRuntime(transport.send_and_wait)
        continuity = {
            "window": "NORMAL_WINDOW",
            "mode_required": "realtime",
            "proves": (
                "Both boundaries of the authoritative window were observed in "
                "Realtime. It does NOT prove the mode was never toggled between "
                "the two reads."
            ),
            "before": _voice_window_state(simulation),
            "after": None,
            "verified": False,
            "failure_reason": "",
        }
        evidence["voice_realtime_continuity"] = continuity
        before_error = _realtime_boundary_error(continuity["before"], "before")
        if before_error:
            continuity["failure_reason"] = before_error
            raise _failed(
                f"Voice at {projection.stage.value!r} was not attempted: "
                + before_error
            )
    # Inside the window, never around it. Simulation showed these ports
    # dropping every phone Discover on a blocked FastEthernet, but that trace
    # is taken after `resetSimulation()`; only a read taken here, bracketed by
    # the two boundary observations, can say what the port was doing while the
    # acquisition it is blamed for was actually running. Read-only: it observes
    # the condition, it does not relieve it.
    evidence["stp_realtime_before_voice"] = _stp_realtime_evidence(
        ios, projection, edge="before",
    )
    voice_evidence = _stage_voice(
        projection,
        voice_runtime=voice_runtime,
        composition=composition,
        configuration=configuration,
        statuses=statuses,
        context=context,
        manifest=manifest,
    )
    evidence["voice"] = voice_evidence
    # The second edge, still Realtime: taken before the closing boundary read
    # so the same two PURE observations that bracket the voice window bracket
    # this measurement too, and long before Simulation is entered at all.
    evidence["stp_realtime_after_voice"] = _stp_realtime_evidence(
        ios, projection, edge="after",
    )
    if continuity is not None:
        continuity["after"] = _voice_window_state(simulation)
        after_error = _realtime_boundary_error(continuity["after"], "after")
        continuity["verified"] = not after_error
        if after_error:
            # The acquisition already ran and its evidence is kept, but nothing
            # downstream may read 0/21 as an authoritative DHCP failure.
            continuity["failure_reason"] = after_error
            raise _failed(
                f"Voice at {projection.stage.value!r} is not interpretable: "
                + after_error
            )
    binding_evidence = (
        _dhcp_server_binding_evidence(
            ios, projection.configuration, projection.voice,
        )
        if voice_evidence.get("staged") else []
    )
    evidence["dhcp_server_bindings"] = binding_evidence
    if (
        voice_evidence.get("staged")
        and dhcp_statistics_target is not None
        and dhcp_statistics_baseline is not None
    ):
        statistics_post = _dhcp_server_statistics_point(
            ios, dhcp_statistics_target,
        )
        evidence["dhcp_voice_exchange"] = _dhcp_server_statistics_delta(
            dhcp_statistics_baseline,
            statistics_post,
            voice_binding_count=_voice_binding_count(
                binding_evidence, dhcp_statistics_target,
            ),
        )
    elif voice_evidence.get("staged"):
        evidence["dhcp_voice_exchange"] = {
            "baseline": dhcp_statistics_baseline,
            "post": None,
            "voice_binding_count": None,
            "delta_readable": False,
            "counters": None,
            "control_counters": None,
            "scope_discriminated": False,
            "fork": "UNOBSERVABLE",
            "failure_reason": (
                "A unique voice DHCP statistics target or baseline was "
                "unavailable at this stage."
            ),
        }
    if voice_evidence.get("error"):
        # POST-FAILURE ONLY. The tested condition has already been established
        # and read back, so entering Simulation now cannot alter it -- and it is
        # the last moment the devices still exist, because the raise below hands
        # this journal out and the governed cleanup follows.
        evidence["post_failure_simulation"] = _post_failure_simulation_diagnostic(
            transport, projection, voice_evidence,
            realtime_failure_established=bool(
                continuity is not None and continuity.get("verified")
            ),
        )
        raise _failed(
            f"Voice at {projection.stage.value!r} did not close: "
            + str(voice_evidence["error"])
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
        raise _failed(
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
        raise _failed(
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
        raise _failed(
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
        # The full plans, so the full voice plan: its source hashes bind the
        # whole topology and configuration, which is exactly what this stage
        # is applied against.
        voice=composition.voice,
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
            status = transport.status_dict()
            # Recorded beside it, never instead of it. The two channels are
            # independent and the file one is alive through every failure of
            # this one, which is exactly the confusion worth pre-empting in the
            # hard stop itself.
            try:
                status["file_bridge_alive"] = FileBridge().pt_alive()
            except Exception:
                pass
            evidence["http_bridge"] = status
            raise CanonicalLiveFailure(
                "Authenticated Packet Tracer HTTP bridge did not obtain fresh "
                "polling: " + canonical_bridge_polling_error(status)
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

        capability_store = CapabilitySnapshotStore(
            GOVERNED_ROOT / "data" / "capabilities",
        )
        composition = compose_cp_scale_canonical(
            packet_tracer_version=packet_tracer_version,
            capability_store=capability_store,
        )
        if not composition.valid:
            raise CanonicalLiveFailure(
                "Canonical composition failed: " + "; ".join(composition.issues),
            )
        assert composition.topology is not None
        assert composition.configuration is not None
        assert composition.control_plane is not None

        required_capabilities = canonical_required_capability_probes(composition)
        probe_runtime = PacketTracerBridgeProbeRuntime(
            transport.send_and_wait,
            packet_tracer_version=packet_tracer_version,
            send=transport.send,
            transport_channel=transport.bridge_transport,
        )
        capability_discovery = CapabilityDiscoveryService(
            runtime=probe_runtime,
            snapshots=capability_store,
            identity_for=EnterpriseCapabilityAdapter().identity_for,
            access_ports_for=EnterpriseCapabilityAdapter().access_ports_for,
        )
        capability_evidence = []
        for model, capabilities in required_capabilities.items():
            snapshot, cached = capability_discovery.run(ProbeRequest(
                models=[model],
                capabilities=capabilities,
                probe_level=ProbeLevel.LOGICAL,
                force=True,
                packet_tracer_version=packet_tracer_version,
            ))
            probe_error = canonical_capability_probe_error(
                snapshot,
                model=model,
                capabilities=capabilities,
                packet_tracer_version=packet_tracer_version,
            )
            capability_evidence.append({
                "model": model,
                "required": capabilities,
                "cached": cached,
                "summary": snapshot.compact_summary(),
                "results": [
                    item.model_dump(mode="json")
                    for item in snapshot.session.results
                    if item.capability in capabilities
                ],
                "error": probe_error,
            })
            if probe_error:
                evidence["capability_prequalification"] = capability_evidence
                raise CanonicalLiveFailure(probe_error)

        post_probe_first = physical.observe_workspace()
        post_probe_second = physical.observe_workspace()
        post_probe_error = canonical_cleanup_restoration_error(
            baseline, post_probe_first, post_probe_second,
        )
        evidence["capability_prequalification"] = {
            "requirements": required_capabilities,
            "sessions": capability_evidence,
            "workspace_first": post_probe_first.compact_summary(),
            "workspace_second": post_probe_second.compact_summary(),
            "restoration_error": post_probe_error,
        }
        if post_probe_error:
            raise CanonicalLiveFailure(post_probe_error)

        composition = compose_cp_scale_canonical(
            packet_tracer_version=packet_tracer_version,
            capability_store=capability_store,
        )
        if not composition.valid:
            raise CanonicalLiveFailure(
                "Canonical post-probe composition failed: "
                + "; ".join(composition.issues),
            )
        unresolved = sorted(
            f"{model}:{capability}"
            for model, capabilities in required_capabilities.items()
            for capability in capabilities
            if (
                composition.capabilities.get(model) is None
                or getattr(
                    composition.capabilities[model], capability,
                    CapabilityStatus.UNKNOWN,
                ) is not CapabilityStatus.SUPPORTED
            )
        )
        evidence["capability_prequalification"]["unresolved_after_composition"] = (
            unresolved
        )
        if unresolved:
            raise CanonicalLiveFailure(
                "Canonical composition did not consume VERIFIED capability evidence: "
                + ", ".join(unresolved)
            )

        floor1_statistics_projection = project_cp_scale_canonical_stage(
            composition, CPScaleCanonicalStage.FLOOR1,
        )
        dhcp_statistics_target = _voice_dhcp_statistics_target(
            floor1_statistics_projection.configuration,
            floor1_statistics_projection.voice,
        )

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
        # A phone that has just been given option 150 and a call control has to
        # solicit, lease, fetch its files and register. 30s is the applicator
        # default and it is a DHCP retry interval, not a provisioning cycle.
        voice_runtime = PacketTracerEnterpriseVoiceRuntime(
            lambda: _inventory(physical),
            transport.send,
            transport.send_and_wait,
            registration_timeout_seconds=180.0,
            convergence_interval_seconds=5.0,
        )

        previous_projection = None
        verified_core_deployment = None
        verified_core_topology = None
        verified_serial_manifest = None
        verified_serial_topology = None
        stage_snapshot = None
        dhcp_statistics_baseline = None
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
            stage_evidence, stage_manifest, stage_snapshot = _execute_stage(
                projection,
                composition=composition,
                deployment=deployment,
                delta_deployment=delta_deployment,
                physical=physical,
                configuration_runtime=configuration_runtime,
                control_runtime=control_runtime,
                voice_runtime=voice_runtime,
                transport=transport,
                fingerprint=fingerprint,
                packet_tracer_version=packet_tracer_version,
                dhcp_statistics_target=(
                    dhcp_statistics_target
                    if stage is CPScaleCanonicalStage.FLOOR1 else None
                ),
                dhcp_statistics_baseline=(
                    dhcp_statistics_baseline
                    if stage is CPScaleCanonicalStage.FLOOR1 else None
                ),
                verified_serial_topology=verified_serial_topology,
                verified_serial_manifest=verified_serial_manifest,
            )
            if stage is CPScaleCanonicalStage.ROUTER4_SWITCH10:
                if dhcp_statistics_target is None:
                    dhcp_statistics_baseline = {
                        "voice": None,
                        "control": None,
                        "failure_reason": (
                            "A unique Floor-1 voice DHCP statistics target "
                            "with a control scope was unavailable."
                        ),
                    }
                else:
                    dhcp_statistics_baseline = _dhcp_server_statistics_point(
                        ControlledIosExecutor(transport.send_and_wait),
                        dhcp_statistics_target,
                    )
                stage_evidence["dhcp_voice_statistics_baseline"] = (
                    dhcp_statistics_baseline
                )
            if stage is CPScaleCanonicalStage.ROUTING_CORE:
                verified_serial_topology = projection.topology
                verified_serial_manifest = stage_manifest
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
            voice_runtime=voice_runtime,
            transport=transport,
            fingerprint=fingerprint,
            packet_tracer_version=packet_tracer_version,
            verified_serial_topology=verified_serial_topology,
            verified_serial_manifest=verified_serial_manifest,
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
        # Only a terminal, fully verified run may update the tracked reference
        # summary. Intermediate progress remains durable under ignored data/
        # so its own repository gate never demands a progress commit.
        _write_checkpoint_summary(
            "full-qualification",
            evidence,
            destination=FINAL_CHECKPOINT_PATH,
        )
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
        partial = getattr(exc, "stage_evidence", None)
        if isinstance(partial, dict):
            # Durable, and marked for what it is: this stage did not pass.
            evidence.setdefault("stages", []).append({
                **partial, "stage_outcome": "failed",
            })
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
