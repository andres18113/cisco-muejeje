"""Governed LIVE qualification for the canonical CP-SCALE routing core.

The first run may explore the still-UNKNOWN 2811 RIPv2 capability through the
typed runtime directly.  It does not inject a fabricated SUPPORTED profile into
the product applicator.  Once fresh evidence is recorded and the catalogue is
promoted, ``--mode governed`` repeats the same slice through the ordinary E9
capability gate.

Every run starts from a completely observed empty semantic workspace, mutates
only the three canonical routers and their serial triangle, and restores the
baseline in a finally-protected cleanup.  No raw IOS or JavaScript is accepted
from the operator.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path

import packet_tracer_mcp

from packet_tracer_mcp.application.use_cases.apply_configuration import (
    ConfigurationApplicator,
)
from packet_tracer_mcp.application.use_cases.apply_control_plane import (
    ControlPlaneApplicator,
)
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    compose_cp_scale_canonical,
    project_cp_scale_routing_core,
)
from packet_tracer_mcp.application.use_cases.deploy_enterprise_topology import (
    EnterprisePhysicalTopologyDeployer,
    disposable_workspace_error,
)
from packet_tracer_mcp.application.use_cases.foundational_evidence import (
    derive_foundational_hashes,
    derive_foundational_statuses,
)
from packet_tracer_mcp.application.use_cases.observe_serial_orientation import (
    SerialOrientationObserver,
)
from packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    read_git_repository_state,
)
from packet_tracer_mcp.application.use_cases.qualify_typed_runtime import (
    qualification_evidence_value,
    typed_runtime_batch_errors,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ConfigurationApplicationStatus,
    ConfigurationRuntimeContext,
)
from packet_tracer_mcp.domain.enterprise.models.deployment import (
    EnvironmentFingerprint,
)
from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentStatus,
    physical_workspace_restoration_matches,
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
from packet_tracer_mcp.infrastructure.execution.live_bridge import (
    PacketTracerHttpTransport,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
    OperationalQueryId,
    parse_show_ip_interface_brief,
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
    TypedPingResult,
)
from packet_tracer_mcp.shared.utils import (
    serialize_typed_ping_evidence,
    typed_ping_behavior_transition_verified,
)


GOVERNED_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = "feature/runtime-ripv2"
EXPECTED_UPSTREAM = "personal/feature/runtime-ripv2"
EVIDENCE_PATH = GOVERNED_ROOT / "data" / "cp-scale" / "live-canonical-core.json"


class QualificationMode(str, Enum):
    QUALIFY_UNKNOWN = "qualify-unknown"
    GOVERNED = "governed"


def _jsonable(value):
    return qualification_evidence_value(value)


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
        raise RuntimeError("Live inventory became unobservable: " + observation.message)
    return [
        {"name": item.name, "model": item.model, "ports": list(item.ports)}
        for item in observation.semantic_devices
    ]


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
        evidence = []
        ready = True
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
                "executed": result.executed,
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


def _wait_for_ping(
    executor: TypedPingExecutor,
    source: str,
    destination: str,
    *,
    reachable: bool,
    attempts: int,
    interval_seconds: float,
) -> TypedPingResult:
    result = executor.ping(source, destination)
    for attempt in range(attempts - 1):
        if result.fresh_output_observed and result.reachable is reachable:
            break
        time.sleep(interval_seconds)
        result = executor.ping(source, destination)
    return result


def _core_serial_addresses(core) -> dict[str, dict[str, str]]:
    expected: dict[str, dict[str, str]] = {}
    for action in core.configuration.actions:
        interface = getattr(action, "interface", "")
        if not interface.casefold().startswith("serial"):
            continue
        expected.setdefault(action.device_name, {})[interface] = action.ipv4
    return expected


def run(
    packet_tracer_version: str,
    *,
    mode: QualificationMode,
    expected_head: str,
) -> tuple[dict[str, object], int]:
    evidence: dict[str, object] = {
        "packet_tracer_version": packet_tracer_version,
        "mode": mode.value,
        "python_executable": sys.executable,
        "package_file": packet_tracer_mcp.__file__,
        "loaded_namespaces": [
            name for name in ("packet_tracer_mcp", "src.packet_tracer_mcp")
            if name in sys.modules
        ],
    }

    isolation = ImportIsolationPreflight(GOVERNED_ROOT).ensure_isolated()
    evidence["import_isolation"] = {
        "state": isolation.state.value,
        "detail": isolation.detail,
    }
    if not isolation.isolated:
        evidence["hard_stop"] = isolation.render()
        return evidence, 2

    repository = read_git_repository_state(GOVERNED_ROOT)
    evidence["repository"] = repository.model_dump(mode="json")
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
    if repository_errors:
        evidence["hard_stop"] = " ".join(repository_errors)
        return evidence, 2

    processes = _packet_tracer_processes()
    evidence["packet_tracer_processes"] = processes
    process_error = packet_tracer_process_error(
        processes, packet_tracer_version,
    )
    if process_error:
        evidence["hard_stop"] = process_error
        return evidence, 2

    transport = PacketTracerHttpTransport()
    if not transport.start(timeout_seconds=10.0):
        evidence["http_bridge"] = transport.status_dict()
        transport.stop()
        evidence["hard_stop"] = (
            "Authenticated Packet Tracer HTTP bridge did not obtain fresh polling."
        )
        return evidence, 2
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
        transport.stop()
        evidence["hard_stop"] = baseline_error
        return evidence, 2

    composition = compose_cp_scale_canonical(
        packet_tracer_version=packet_tracer_version,
    )
    if not composition.valid:
        transport.stop()
        evidence["hard_stop"] = "Canonical composition failed: " + "; ".join(
            composition.issues,
        )
        return evidence, 2
    core = project_cp_scale_routing_core(composition)
    evidence["plan"] = {
        "topology_hash": core.topology.physical_identity_hash,
        "configuration_hash": core.configuration.semantic_hash,
        "control_plane_hash": core.control_plane.semantic_hash,
        "devices": len(core.topology.devices),
        "modules": len(core.topology.modules),
        "links": len(core.topology.links),
        "configuration_actions": len(core.configuration.actions),
        "control_plane_actions": len(core.control_plane.actions),
        "verification_expectations": len(
            core.control_plane.verification_expectations
        ),
    }

    fingerprint = EnvironmentFingerprint(
        backend="packet_tracer",
        backend_version=packet_tracer_version,
        bridge_transport=transport.bridge_transport,
        runtime_mode="live",
    )
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
    qualification_error = ""
    exit_code = 1
    mutation_started = False
    try:
        deployment = EnterprisePhysicalTopologyDeployer(physical).deploy(
            core.topology,
            environment_fingerprint=fingerprint,
            deployment_id="cp-scale-canonical-routing-core",
            require_empty_workspace=True,
        )
        mutation_started = True
        evidence["physical"] = deployment.model_dump(mode="json")
        if (
            deployment.status is not PhysicalDeploymentStatus.VERIFIED
            or deployment.manifest is None
        ):
            raise RuntimeError(
                "Physical core deployment was not independently VERIFIED: "
                + "; ".join(deployment.errors)
            )

        orientation = SerialOrientationObserver(
            PacketTracerSerialOrientationRuntime(transport.send_and_wait),
        ).observe(core.topology, deployment.manifest)
        evidence["serial_orientation"] = orientation.model_dump(mode="json")
        if not orientation.verified or orientation.oriented_manifest is None:
            raise RuntimeError(
                "Serial DCE/DTE orientation was not VERIFIED: "
                + "; ".join(orientation.errors)
            )
        manifest = orientation.oriented_manifest
        context = ConfigurationRuntimeContext(environment_fingerprint=fingerprint)

        if mode is QualificationMode.QUALIFY_UNKNOWN:
            configuration_mutations = configuration_runtime.apply_actions(
                core.configuration.actions,
            )
            configuration_observations = configuration_runtime.verify(
                core.configuration.verification_expectations,
            )
            evidence["configuration_application"] = _jsonable(
                configuration_mutations,
            )
            evidence["configuration_verification"] = _jsonable(
                configuration_observations,
            )
            configuration_errors = typed_runtime_batch_errors(
                action_ids=[item.id for item in core.configuration.actions],
                expectation_ids=[
                    item.id for item in core.configuration.verification_expectations
                ],
                mutations=configuration_mutations,
                observations=configuration_observations,
            )
            if configuration_errors:
                raise RuntimeError(
                    "Typed canonical core L3 qualification was not VERIFIED: "
                    + "; ".join(configuration_errors)
                )
            configuration = None
        else:
            configuration = ConfigurationApplicator(configuration_runtime).apply(
                core.configuration,
                actual_source_topology_hash=core.topology.physical_identity_hash,
                capabilities=composition.capabilities,
                runtime_context=context,
                deployment_manifest=manifest,
            )
            evidence["configuration"] = configuration.model_dump(mode="json")
            if configuration.status is not ConfigurationApplicationStatus.VERIFIED:
                raise RuntimeError(
                    "Canonical core L3 configuration was not VERIFIED: "
                    f"{configuration.status.value}/{configuration.failure_code.value}"
                )

        ios = ControlledIosExecutor(transport.send_and_wait)
        interfaces_ready, interface_evidence = _wait_for_serial_interfaces(
            ios, _core_serial_addresses(core),
        )
        evidence["serial_interfaces"] = interface_evidence
        if not interfaces_ready:
            raise RuntimeError(
                "Canonical serial interfaces did not converge to exact up/up state."
            )

        ping = TypedPingExecutor(
            transport.send_and_wait,
            timeout_seconds=30.0,
            measurement_attempts=3,
        )
        negative = {
            source: _wait_for_ping(
                ping, source, destination,
                reachable=False, attempts=2, interval_seconds=2.0,
            )
            for source, destination in core.forwarding_checks.items()
        }
        evidence["pre_rip_negative_controls"] = {
            key: serialize_typed_ping_evidence(value)
            for key, value in negative.items()
        }
        if not all(
            item.fresh_output_observed and not item.reachable
            for item in negative.values()
        ):
            raise RuntimeError(
                "Pre-RIP forwarding negative controls were not fresh and unreachable."
            )

        if mode is QualificationMode.QUALIFY_UNKNOWN:
            mutations = control_runtime.apply_actions(core.control_plane.actions)
            observations = control_runtime.verify(
                core.control_plane.verification_expectations,
            )
            evidence["ripv2_application"] = _jsonable(mutations)
            evidence["ripv2_verification"] = _jsonable(observations)
            ripv2_errors = typed_runtime_batch_errors(
                action_ids=[item.id for item in core.control_plane.actions],
                expectation_ids=[
                    item.id for item in core.control_plane.verification_expectations
                ],
                mutations=mutations,
                observations=observations,
            )
            if ripv2_errors:
                evidence["ripv2_diagnostics"] = {
                    device.name: {
                        query.value: _jsonable(ios.execute(device.name, query))
                        for query in (
                            OperationalQueryId.SHOW_IP_PROTOCOLS,
                            OperationalQueryId.SHOW_IP_ROUTE_RIP,
                            OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
                        )
                    }
                    for device in core.topology.devices
                }
                raise RuntimeError(
                    "Typed RIPv2 qualification was not VERIFIED: "
                    + "; ".join(ripv2_errors)
                )
        else:
            assert configuration is not None
            statuses = derive_foundational_statuses(
                configuration_result=configuration,
                physical_result=deployment,
            )
            control = ControlPlaneApplicator(control_runtime).apply(
                core.control_plane,
                actual_source_topology_hash=core.topology.physical_identity_hash,
                actual_source_configuration_hash=core.configuration.semantic_hash,
                foundational_statuses=statuses,
                foundational_hashes=derive_foundational_hashes(core.control_plane),
                capabilities=packet_tracer_control_plane_capabilities(
                    packet_tracer_version,
                ),
                runtime_context=context,
                deployment_manifest=manifest,
            )
            evidence["control_plane"] = control.model_dump(mode="json")
            if control.status is not ConfigurationApplicationStatus.VERIFIED:
                raise RuntimeError(
                    "Governed RIPv2 application was not VERIFIED: "
                    f"{control.status.value}/{control.failure_code.value}"
                )

        positive = {
            source: _wait_for_ping(
                ping, source, destination,
                reachable=True, attempts=4, interval_seconds=5.0,
            )
            for source, destination in core.forwarding_checks.items()
        }
        evidence["post_rip_forwarding"] = {
            key: serialize_typed_ping_evidence(value)
            for key, value in positive.items()
        }
        evidence["forwarding_transition_verified"] = (
            typed_ping_behavior_transition_verified(
                negative.values(), positive.values(),
            )
        )
        if not evidence["forwarding_transition_verified"]:
            raise RuntimeError(
                "Representative forwarding did not make a fresh false-to-true transition."
            )
        evidence["core_verified"] = True
        exit_code = 0
    except Exception as exc:
        qualification_error = f"{type(exc).__name__}: {exc}"
        exit_code = 1
    finally:
        cleanup = []
        if mutation_started:
            for device in reversed(core.topology.devices):
                cleanup.append(physical.remove_device(device).model_dump(mode="json"))
        final_first = physical.observe_workspace()
        final_second = physical.observe_workspace()
        evidence["cleanup"] = cleanup
        evidence["final_inventory_first"] = final_first.compact_summary()
        evidence["final_inventory_second"] = final_second.compact_summary()
        evidence["cleanup_verified"] = (
            physical_workspace_restoration_matches(baseline, final_first)
            and physical_workspace_restoration_matches(baseline, final_second)
        )
        if not evidence["cleanup_verified"]:
            exit_code = 1
        transport.stop()
    if qualification_error:
        evidence["qualification_error"] = qualification_error
    return evidence, exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Authorize the bounded canonical-core mutation after all hard gates.",
    )
    parser.add_argument(
        "--packet-tracer-version",
        required=True,
        help="Exact running Packet Tracer build expected by the qualification.",
    )
    parser.add_argument(
        "--mode",
        choices=[item.value for item in QualificationMode],
        default=QualificationMode.QUALIFY_UNKNOWN.value,
    )
    parser.add_argument(
        "--expected-head",
        default="",
        help="Optional exact repository HEAD required before mutation.",
    )
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({
            "hard_stop": "--execute is required; no Packet Tracer mutation occurred.",
        }))
        return 2
    evidence, exit_code = run(
        args.packet_tracer_version,
        mode=QualificationMode(args.mode),
        expected_head=args.expected_head,
    )
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "evidence_path": str(EVIDENCE_PATH),
        "mode": evidence.get("mode", ""),
        "hard_stop": evidence.get("hard_stop", ""),
        "qualification_error": evidence.get("qualification_error", ""),
        "core_verified": evidence.get("core_verified", False),
        "cleanup_verified": evidence.get("cleanup_verified", False),
        "exit_code": exit_code,
    }, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
