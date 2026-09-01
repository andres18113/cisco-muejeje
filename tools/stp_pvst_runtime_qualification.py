"""Bounded exact-model PVST qualification for Packet Tracer.

The harness creates one disposable 3560-24PS and one disposable 2960-24TT,
builds a typed VLAN/trunk foundation, and exercises the same typed PVST
renderer, mutation runtime, and fresh observer used by the enterprise product.
It refuses a non-empty semantic workspace and restores both topology and
Realtime state in a finally-protected cleanup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import packet_tracer_mcp

from packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    read_git_repository_state,
)
from packet_tracer_mcp.application.use_cases.qualify_typed_runtime import (
    qualification_evidence_value,
    typed_runtime_batch_errors,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigureAccessPort,
    ConfigureHostname,
    ConfigureTrunk,
    CreateVlan,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureSpanningTree,
    ConfigureStpEdgePort,
    ControlPlaneCapabilityDimension,
    ControlPlanePhase,
    ControlPlaneVerificationExpectation,
    ControlPlaneVerificationKind,
    StpMode,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    MutationDisposition,
)
from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    physical_workspace_restoration_matches,
)
from packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_control_plane_runtime import (
    PacketTracerEnterpriseControlPlaneRuntime,
)
from packet_tracer_mcp.infrastructure.execution.file_bridge import FileBridge
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
    OperationalQueryId,
    parse_show_interfaces_trunk,
    parse_show_spanning_tree,
)
from packet_tracer_mcp.infrastructure.execution.live_environment_preflight import (
    packet_tracer_process_error,
)
from packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
)
from packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (
    SimulationTraceRuntime,
)
from packet_tracer_mcp.shared.utils import same_interface_name


GOVERNED_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = "feature/runtime-ripv2"
EXPECTED_UPSTREAM = "personal/feature/runtime-ripv2"
EVIDENCE_DIR = (
    GOVERNED_ROOT / "docs" / "reference" / "cp-scale"
    / "canonical-live-evidence"
)
PROBE_PREFIX = "MCP-PROBE-PVST"
VLAN_ID = 20
TRUNK_INTERFACE = "GigabitEthernet0/1"
EDGE_INTERFACE = "FastEthernet0/1"
PRIMARY_MODEL = "3560-24PS"
SECONDARY_MODEL = "2960-24TT"
TERTIARY_MODEL = "3650-24PS"
TERTIARY_TRUNK_INTERFACE = "GigabitEthernet1/0/1"
TERTIARY_EDGE_INTERFACE = "GigabitEthernet1/0/2"
QUALIFIED_MODELS = (PRIMARY_MODEL, SECONDARY_MODEL, TERTIARY_MODEL)
_TRUNK_INTERFACES = {
    PRIMARY_MODEL: ("GigabitEthernet0/1", "GigabitEthernet0/2"),
    SECONDARY_MODEL: (TRUNK_INTERFACE,),
    TERTIARY_MODEL: (TERTIARY_TRUNK_INTERFACE,),
}
_ROOT_PORTS = {
    SECONDARY_MODEL: TRUNK_INTERFACE,
    TERTIARY_MODEL: TERTIARY_TRUNK_INTERFACE,
}


def qualification_topology() -> TopologyPlan:
    devices = [
        DevicePlan(
            id="pvst-primary",
            name=f"{PROBE_PREFIX}-3560",
            model=PRIMARY_MODEL,
            category="switch",
            site_id="pvst",
            enterprise_role="access_switch",
            x=160,
            y=180,
        ),
        DevicePlan(
            id="pvst-secondary",
            name=f"{PROBE_PREFIX}-2960",
            model=SECONDARY_MODEL,
            category="switch",
            site_id="pvst",
            enterprise_role="access_switch",
            x=480,
            y=180,
        ),
        DevicePlan(
            id="pvst-tertiary",
            name=f"{PROBE_PREFIX}-3650",
            model=TERTIARY_MODEL,
            category="switch",
            site_id="pvst",
            enterprise_role="distribution_switch",
            x=480,
            y=360,
        ),
    ]
    links = [
        LinkPlan(
            id="pvst-trunk-secondary",
            device_a=devices[0].name,
            device_a_id=devices[0].id,
            port_a=TRUNK_INTERFACE,
            device_b=devices[1].name,
            device_b_id=devices[1].id,
            port_b=TRUNK_INTERFACE,
            cable="cross",
            link_role="trunk",
        ),
        LinkPlan(
            id="pvst-trunk-tertiary",
            device_a=devices[0].name,
            device_a_id=devices[0].id,
            port_a="GigabitEthernet0/2",
            device_b=devices[2].name,
            device_b_id=devices[2].id,
            port_b=TERTIARY_TRUNK_INTERFACE,
            cable="cross",
            link_role="trunk",
        ),
    ]
    return TopologyPlan(
        id="pvst-exact-model-qualification",
        semantic_hash="pvst-exact-model-qualification-v2",
        devices=devices,
        links=links,
    )


def foundation_actions(topology: TopologyPlan) -> list:
    primary, secondary, tertiary = topology.devices
    hostname_actions = [
        ConfigureHostname(
            id=f"pvst/hostname/{device.id}",
            phase=ConfigurationPhase.IDENTITY,
            device_id=device.id,
            device_name=device.name,
            site_id="pvst",
            hostname=device.name,
        )
        for device in topology.devices
    ]
    vlan_actions = [
        CreateVlan(
            id=f"pvst/vlan/{device.id}",
            phase=ConfigurationPhase.L2_DEFINITIONS,
            device_id=device.id,
            device_name=device.name,
            site_id="pvst",
            required_capability="supports_vlan",
            vlan_id=VLAN_ID,
            name="PVST_QUALIFICATION",
            segment_id="pvst-vlan20",
        )
        for device in topology.devices
    ]
    trunk_specs = (
        (
            primary, TRUNK_INTERFACE, secondary, "secondary",
            "pvst-trunk-secondary",
        ),
        (
            secondary, TRUNK_INTERFACE, primary, "primary",
            "pvst-trunk-secondary",
        ),
        (
            primary, "GigabitEthernet0/2", tertiary, "tertiary",
            "pvst-trunk-tertiary",
        ),
        (
            tertiary, TERTIARY_TRUNK_INTERFACE, primary, "primary",
            "pvst-trunk-tertiary",
        ),
    )
    trunk_actions = [
        ConfigureTrunk(
            id=f"pvst/trunk/{device.id}/to-{peer_role}",
            phase=ConfigurationPhase.L2_INTERFACES,
            device_id=device.id,
            device_name=device.name,
            site_id="pvst",
            depends_on=[f"pvst/vlan/{device.id}"],
            required_capability="supports_trunk",
            interface=interface,
            allowed_vlans=[VLAN_ID],
            peer_device_id=peer.id,
            source_link_id=link_id,
        )
        for device, interface, peer, peer_role, link_id in trunk_specs
    ]
    edge_actions = [
        ConfigureAccessPort(
            id=f"pvst/access/{device.id}",
            phase=ConfigurationPhase.L2_INTERFACES,
            device_id=device.id,
            device_name=device.name,
            site_id="pvst",
            depends_on=[f"pvst/vlan/{device.id}"],
            required_capability="supports_vlan",
            interface=interface,
            data_vlan_id=VLAN_ID,
        )
        for device, interface in (
            (primary, EDGE_INTERFACE),
            (tertiary, TERTIARY_EDGE_INTERFACE),
        )
    ]
    return [
        *hostname_actions, *vlan_actions, *trunk_actions, *edge_actions,
    ]


def stp_actions(topology: TopologyPlan) -> list:
    primary, secondary, tertiary = topology.devices
    global_actions = [
        ConfigureSpanningTree(
            id="pvst/stp/primary",
            phase=ControlPlanePhase.L2_FOUNDATION,
            device_id=primary.id,
            device_name=primary.name,
            model=primary.model,
            site_id="pvst",
            required_capability=ControlPlaneCapabilityDimension.STP_PVST_CONFIG,
            mode=StpMode.PVST,
            vlan_ids=[VLAN_ID],
            root_primary_vlans=[VLAN_ID],
            source_vlan_action_ids=[f"pvst/vlan/{primary.id}"],
        ),
        ConfigureSpanningTree(
            id="pvst/stp/secondary",
            phase=ControlPlanePhase.L2_FOUNDATION,
            device_id=secondary.id,
            device_name=secondary.name,
            model=secondary.model,
            site_id="pvst",
            required_capability=ControlPlaneCapabilityDimension.STP_PVST_CONFIG,
            mode=StpMode.PVST,
            vlan_ids=[VLAN_ID],
            root_secondary_vlans=[VLAN_ID],
            source_vlan_action_ids=[f"pvst/vlan/{secondary.id}"],
        ),
        ConfigureSpanningTree(
            id="pvst/stp/tertiary",
            phase=ControlPlanePhase.L2_FOUNDATION,
            device_id=tertiary.id,
            device_name=tertiary.name,
            model=tertiary.model,
            site_id="pvst",
            required_capability=ControlPlaneCapabilityDimension.STP_PVST_CONFIG,
            mode=StpMode.PVST,
            vlan_ids=[VLAN_ID],
            root_secondary_vlans=[VLAN_ID],
            source_vlan_action_ids=[f"pvst/vlan/{tertiary.id}"],
        ),
    ]
    edge_actions = [
        ConfigureStpEdgePort(
            id=f"pvst/stp/edge-{role}",
            phase=ControlPlanePhase.L2_RESILIENCY,
            device_id=device.id,
            device_name=device.name,
            model=device.model,
            site_id="pvst",
            depends_on=[f"pvst/stp/{role}"],
            required_capability=ControlPlaneCapabilityDimension.STP_PVST_CONFIG,
            interface=interface,
            portfast=True,
            bpduguard=True,
            source_access_action_id=f"pvst/access/{device.id}",
        )
        for role, device, interface in (
            ("primary", primary, EDGE_INTERFACE),
            ("tertiary", tertiary, TERTIARY_EDGE_INTERFACE),
        )
    ]
    return [*global_actions, *edge_actions]


def stp_expectations(topology: TopologyPlan) -> list:
    primary, secondary, tertiary = topology.devices
    state = [
        ControlPlaneVerificationExpectation(
            id=f"pvst/verify/{role}",
            kind=ControlPlaneVerificationKind.STP_STATE,
            action_id=f"pvst/stp/{role}",
            device_id=device.id,
            required_capability=ControlPlaneCapabilityDimension.STP_STATE,
            expected={
                "source_device_name": device.name,
                "mode": StpMode.PVST.value,
                "vlan_ids": [VLAN_ID],
                root_key: [VLAN_ID],
            },
            depends_on=[f"pvst/stp/{role}"],
        )
        for role, device, root_key in (
            ("primary", primary, "root_primary_vlans"),
            ("secondary", secondary, "root_secondary_vlans"),
            ("tertiary", tertiary, "root_secondary_vlans"),
        )
    ]
    behavior = [
        ControlPlaneVerificationExpectation(
            id=f"pvst/verify/{role}-behavior",
            kind=ControlPlaneVerificationKind.END_TO_END_REACHABILITY,
            action_id=f"pvst/stp/{role}",
            device_id=device.id,
            required_capability=ControlPlaneCapabilityDimension.STP_BEHAVIOR,
            expected={
                "source_device_name": device.name,
                "loop_free": True,
                "forwarding_converged": True,
            },
            depends_on=[f"pvst/stp/{role}"],
        )
        for role, device in (
            ("primary", primary),
            ("secondary", secondary),
            ("tertiary", tertiary),
        )
    ]
    return [*state, *behavior]


def stp_convergence_errors(instances_by_model: dict[str, list]) -> list[str]:
    errors: list[str] = []
    selected = {}
    for model in QUALIFIED_MODELS:
        instance = next(
            (
                item for item in instances_by_model.get(model, [])
                if item.vlan_id == VLAN_ID
            ),
            None,
        )
        if instance is None:
            errors.append(f"{model}: VLAN {VLAN_ID} STP instance is absent")
            continue
        selected[model] = instance
        if instance.protocol.casefold() != "ieee":
            errors.append(f"{model}: protocol is {instance.protocol!r}, not ieee")

    primary = selected.get(PRIMARY_MODEL)
    secondaries = {
        model: selected.get(model)
        for model in (SECONDARY_MODEL, TERTIARY_MODEL)
    }
    if primary is not None:
        if primary.bridge_base_priority != 24576:
            errors.append(
                f"{PRIMARY_MODEL}: bridge base priority is "
                f"{primary.bridge_base_priority!r}, not 24576"
            )
        if not primary.root_is_local:
            errors.append(f"{PRIMARY_MODEL}: the qualified primary is not root")
    for model, secondary in secondaries.items():
        if secondary is None:
            continue
        if secondary.bridge_base_priority != 28672:
            errors.append(
                f"{model}: bridge base priority is "
                f"{secondary.bridge_base_priority!r}, not 28672"
            )
        if secondary.root_is_local:
            errors.append(f"{model}: the qualified secondary is root")
        if not same_interface_name(secondary.root_port, _ROOT_PORTS[model]):
            errors.append(
                f"{model}: root port is {secondary.root_port!r}, "
                f"not {_ROOT_PORTS[model]}"
            )
        if primary is not None and (
            primary.bridge_address.casefold() != secondary.root_address.casefold()
        ):
            errors.append(
                f"{model}: root address does not match the primary bridge"
            )
    return errors


def _inventory(physical: PacketTracerPhysicalTopologyRuntime) -> list[dict]:
    observation = physical.observe_workspace()
    if not observation.observed:
        raise RuntimeError(
            "Live inventory became unobservable: " + observation.message
        )
    return [
        {"name": item.name, "model": item.model, "ports": list(item.ports)}
        for item in observation.semantic_devices
    ]


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


def _repository_errors(expected_head: str) -> list[str]:
    repository = read_git_repository_state(GOVERNED_ROOT)
    errors: list[str] = []
    if repository.branch != EXPECTED_BRANCH:
        errors.append(
            f"Expected branch {EXPECTED_BRANCH!r}; observed {repository.branch!r}."
        )
    if repository.upstream != EXPECTED_UPSTREAM:
        errors.append(
            f"Expected upstream {EXPECTED_UPSTREAM!r}; "
            f"observed {repository.upstream!r}."
        )
    if repository.head != expected_head:
        errors.append(
            f"Expected HEAD {expected_head!r}; observed {repository.head!r}."
        )
    if repository.error:
        errors.append(repository.error)
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=GOVERNED_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    upstream_head = subprocess.run(
        ["git", "rev-parse", "@{upstream}"],
        cwd=GOVERNED_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        errors.append("PVST qualification requires a clean initial worktree.")
    if repository.head != upstream_head:
        errors.append("PVST qualification requires HEAD equal to its upstream.")
    return errors


def _realtime_state(bridge: FileBridge) -> dict[str, object]:
    state = SimulationTraceRuntime(bridge.send_and_wait).read_simulation_state()
    return {
        "observed": state.observed,
        "simulation_mode": state.simulation_mode,
        "frames": state.frames,
        "sim_time": state.sim_time,
        "verified_realtime": state.observed and not state.simulation_mode,
    }


def _trunks_ready(
    ios: ControlledIosExecutor,
    topology: TopologyPlan,
    *,
    timeout_seconds: float = 60.0,
    interval_seconds: float = 2.0,
) -> tuple[bool, list[dict[str, object]]]:
    deadline = time.monotonic() + timeout_seconds
    attempts: list[dict[str, object]] = []
    while True:
        sample: dict[str, object] = {"devices": {}}
        ready = True
        for device in topology.devices:
            result = ios.execute(
                device.name, OperationalQueryId.SHOW_INTERFACES_TRUNK,
            )
            rows = parse_show_interfaces_trunk(result.output)
            expected_interfaces = _TRUNK_INTERFACES[device.model]
            selected_rows = [
                next(
                    (
                        item for item in rows
                        if same_interface_name(item.interface, interface)
                    ),
                    None,
                )
                for interface in expected_interfaces
            ]
            matched = bool(
                result.executed
                and result.fresh_output_observed
                and result.output_complete
                and result.observed_device_name == device.name
                and result.device_identity_provenance == "confirmed_unique"
                and all(
                    row is not None
                    and row.status.casefold() == "trunking"
                    and row.allowed_vlans is not None
                    and VLAN_ID in row.allowed_vlans
                    and row.active_vlans is not None
                    and VLAN_ID in row.active_vlans
                    and row.forwarding_vlans is not None
                    and VLAN_ID in row.forwarding_vlans
                    for row in selected_rows
                )
            )
            ready = ready and matched
            sample["devices"][device.model] = {
                "executed": result.executed,
                "fresh_output_observed": result.fresh_output_observed,
                "output_complete": result.output_complete,
                "observed_device_name": result.observed_device_name,
                "device_identity_provenance": result.device_identity_provenance,
                "failure_reason": result.failure_reason,
                "matched": matched,
                "rows": qualification_evidence_value(rows),
                "output": result.output,
            }
        attempts.append(sample)
        if ready:
            return True, attempts
        if time.monotonic() + interval_seconds >= deadline:
            return False, attempts
        time.sleep(interval_seconds)


def _observe_stp_until_converged(
    ios: ControlledIosExecutor,
    topology: TopologyPlan,
    *,
    timeout_seconds: float = 60.0,
    interval_seconds: float = 2.0,
) -> tuple[list[str], list[dict[str, object]]]:
    deadline = time.monotonic() + timeout_seconds
    attempts: list[dict[str, object]] = []
    errors = ["No STP sample was taken."]
    while True:
        instances_by_model: dict[str, list] = {}
        source_error = ""
        sample: dict[str, object] = {"devices": {}}
        for device in topology.devices:
            result = ios.execute(
                device.name, OperationalQueryId.SHOW_SPANNING_TREE,
            )
            attributed = bool(
                result.executed
                and result.fresh_output_observed
                and result.output_complete
                and result.observed_device_name == device.name
                and result.device_identity_provenance == "confirmed_unique"
            )
            instances = parse_show_spanning_tree(result.output) if attributed else []
            instances_by_model[device.model] = instances
            sample["devices"][device.model] = {
                "executed": result.executed,
                "fresh_output_observed": result.fresh_output_observed,
                "output_complete": result.output_complete,
                "observed_device_name": result.observed_device_name,
                "device_identity_provenance": result.device_identity_provenance,
                "failure_reason": result.failure_reason,
                "instances": qualification_evidence_value(instances),
                "output": result.output,
            }
            if not attributed:
                source_error = (
                    f"{device.model}: STP output was not fresh, complete, and "
                    "uniquely attributed."
                )
        errors = (
            [source_error]
            if source_error
            else stp_convergence_errors(instances_by_model)
        )
        sample["errors"] = errors
        attempts.append(sample)
        if not errors:
            return [], attempts
        if source_error or time.monotonic() + interval_seconds >= deadline:
            return errors, attempts
        time.sleep(interval_seconds)


def run(
    packet_tracer_version: str,
    *,
    expected_head: str,
) -> tuple[dict[str, object], int]:
    started_at = datetime.now(timezone.utc)
    run_identity = (
        "stp-pvst-capability-"
        f"{started_at.strftime('%Y%m%dT%H%M%S%fZ')}-{expected_head[:12]}"
    )
    evidence: dict[str, object] = {
        "schema": "stp-pvst-exact-model-qualification-v2",
        "run_identity": run_identity,
        "started_at": started_at.isoformat(),
        "packet_tracer_version": packet_tracer_version,
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
    repository_errors = _repository_errors(expected_head)
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

    bridge = FileBridge()
    evidence["file_bridge_alive"] = bridge.pt_alive()
    if not bridge.pt_alive():
        evidence["hard_stop"] = "Packet Tracer file bridge is not alive."
        return evidence, 2

    physical = PacketTracerPhysicalTopologyRuntime(
        bridge.send_and_wait,
        mutation_timeout_seconds=12.0,
        observation_timeout_seconds=12.0,
    )
    baseline = physical.observe_workspace()
    evidence["baseline"] = baseline.compact_summary()
    if not baseline.safe_for_disposable_mutation:
        evidence["hard_stop"] = (
            "Workspace contains semantic topology or inventory is incomplete."
        )
        return evidence, 2
    before_realtime = _realtime_state(bridge)
    evidence["realtime_before"] = before_realtime
    if not before_realtime["verified_realtime"]:
        evidence["hard_stop"] = "Packet Tracer was not observably in Realtime."
        return evidence, 2

    topology = qualification_topology()
    foundations = foundation_actions(topology)
    actions = stp_actions(topology)
    expectations = stp_expectations(topology)
    evidence["plan"] = {
        "topology": topology.model_dump(mode="json"),
        "foundation_actions": [
            item.model_dump(mode="json") for item in foundations
        ],
        "stp_actions": [item.model_dump(mode="json") for item in actions],
        "expectations": [
            item.model_dump(mode="json") for item in expectations
        ],
    }

    created: list[DevicePlan] = []
    qualification_error = ""
    exit_code = 1
    try:
        physical_results: list[dict[str, object]] = []
        for device in topology.devices:
            mutation = physical.ensure_device(device)
            physical_results.append(mutation.model_dump(mode="json"))
            if mutation.disposition not in {
                MutationDisposition.CHANGED,
                MutationDisposition.NO_OP,
            }:
                raise RuntimeError(
                    f"Device creation failed for {device.name}: {mutation.message}"
                )
            created.append(device)
            observed = physical.observe_device(device)
            if (
                not observed.observed
                or observed.deployed_name != device.name
                or observed.model.casefold() != device.model.casefold()
            ):
                raise RuntimeError(
                    f"Exact model read-back failed for {device.name}."
                )
        for link in topology.links:
            mutation = physical.ensure_link(link)
            physical_results.append(mutation.model_dump(mode="json"))
            if mutation.disposition not in {
                MutationDisposition.CHANGED,
                MutationDisposition.NO_OP,
            }:
                raise RuntimeError(
                    f"Link creation failed for {link.id}: {mutation.message}"
                )
            if not physical.observe_link(link).observed:
                raise RuntimeError(f"Link read-back failed for {link.id}.")
        evidence["physical_mutations"] = physical_results

        configuration_runtime = PacketTracerEnterpriseConfigurationRuntime(
            query_inventory=lambda: _inventory(physical),
            send=bridge.send,
            send_and_wait=bridge.send_and_wait,
        )
        foundation_results = configuration_runtime.apply_actions(foundations)
        evidence["foundation_application"] = [
            item.model_dump(mode="json") for item in foundation_results
        ]
        if (
            len(foundation_results) != len(foundations)
            or not all(item.applied for item in foundation_results)
        ):
            raise RuntimeError(
                "The typed VLAN/trunk/access foundation was not fully accepted."
            )

        ios = ControlledIosExecutor(bridge.send_and_wait)
        trunks_ready, trunk_attempts = _trunks_ready(ios, topology)
        evidence["foundation_trunk_convergence"] = {
            "verified": trunks_ready,
            "attempts": trunk_attempts,
        }
        if not trunks_ready:
            raise RuntimeError(
                "The exact VLAN 20 trunk did not converge to forwarding."
            )

        baseline_stp = {}
        for device in topology.devices:
            result = ios.execute(
                device.name, OperationalQueryId.SHOW_SPANNING_TREE,
            )
            baseline_stp[device.model] = {
                "executed": result.executed,
                "fresh_output_observed": result.fresh_output_observed,
                "output_complete": result.output_complete,
                "observed_device_name": result.observed_device_name,
                "device_identity_provenance": result.device_identity_provenance,
                "instances": qualification_evidence_value(
                    parse_show_spanning_tree(result.output)
                ),
                "output": result.output,
            }
        evidence["stp_before"] = baseline_stp

        control_runtime = PacketTracerEnterpriseControlPlaneRuntime(
            query_inventory=lambda: _inventory(physical),
            send=bridge.send,
            send_and_wait=bridge.send_and_wait,
        )
        mutations = control_runtime.apply_actions(actions)
        evidence["stp_application"] = [
            item.model_dump(mode="json") for item in mutations
        ]
        if len(mutations) != len(actions) or not all(
            item.applied for item in mutations
        ):
            raise RuntimeError(
                "The exact typed PVST action set was not fully accepted."
            )

        convergence_errors, convergence_attempts = _observe_stp_until_converged(
            ios, topology,
        )
        evidence["stp_convergence"] = {
            "verified": not convergence_errors,
            "errors": convergence_errors,
            "attempts": convergence_attempts,
        }
        if convergence_errors:
            raise RuntimeError(
                "PVST state did not converge: " + "; ".join(convergence_errors)
            )

        observations = control_runtime.verify(expectations)
        evidence["stp_verification"] = [
            item.model_dump(mode="json") for item in observations
        ]
        batch_errors = typed_runtime_batch_errors(
            action_ids=[item.id for item in actions],
            expectation_ids=[item.id for item in expectations],
            mutations=mutations,
            observations=observations,
        )
        evidence["qualification_errors"] = list(batch_errors)
        evidence["qualified_models"] = {
            model: {
                "stp_pvst_config": "supported",
                "stp_state": "supported",
                "stp_behavior": "supported",
            }
            for model in QUALIFIED_MODELS
        }
        evidence["edge_policy_qualification"] = {
            model: {
                "interface": interface,
                "portfast": True,
                "bpduguard": True,
                "mutation_status": next(
                    item for item in mutations
                    if item.action_id == action_id
                ).applied,
            }
            for model, interface, action_id in (
                (
                    PRIMARY_MODEL,
                    EDGE_INTERFACE,
                    "pvst/stp/edge-primary",
                ),
                (
                    TERTIARY_MODEL,
                    TERTIARY_EDGE_INTERFACE,
                    "pvst/stp/edge-tertiary",
                ),
            )
        }
        evidence["verified"] = not batch_errors and all(
            item.status is ActionExecutionStatus.VERIFIED
            for item in observations
        )
        if not evidence["verified"]:
            raise RuntimeError(
                "Typed PVST qualification was not VERIFIED: "
                + "; ".join(batch_errors)
            )
        exit_code = 0
    except Exception as exc:
        qualification_error = f"{type(exc).__name__}: {exc}"
        exit_code = 1
    finally:
        cleanup = []
        for device in reversed(created):
            cleanup.append(
                physical.remove_device(device).model_dump(mode="json")
            )
        bridge.collect_completed()
        final_first = physical.observe_workspace()
        final_second = physical.observe_workspace()
        after_realtime = _realtime_state(bridge)
        cleanup_verified = (
            physical_workspace_restoration_matches(baseline, final_first)
            and physical_workspace_restoration_matches(baseline, final_second)
        )
        evidence["cleanup"] = {
            "mutations": cleanup,
            "first": final_first.compact_summary(),
            "second": final_second.compact_summary(),
            "workspace_verified": cleanup_verified,
            "realtime": after_realtime,
            "verified": (
                cleanup_verified and after_realtime["verified_realtime"]
            ),
        }
        if not evidence["cleanup"]["verified"]:
            exit_code = 1
    if qualification_error:
        evidence["qualification_error"] = qualification_error
    evidence["completed_at"] = datetime.now(timezone.utc).isoformat()
    return evidence, exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Authorize the bounded disposable mutation after every hard gate.",
    )
    parser.add_argument("--packet-tracer-version", required=True)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({
            "hard_stop": "--execute is required; no Packet Tracer mutation occurred.",
        }))
        return 2

    evidence, exit_code = run(
        args.packet_tracer_version,
        expected_head=args.expected_head,
    )
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    output = EVIDENCE_DIR / f"{evidence['run_identity']}.json"
    payload = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    output.write_text(payload, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({
        "evidence_path": str(output),
        "sha256": digest,
        "verified": evidence.get("verified", False),
        "hard_stop": evidence.get("hard_stop", ""),
        "qualification_error": evidence.get("qualification_error", ""),
        "cleanup_verified": (
            evidence.get("cleanup", {}).get("verified", False)
            if isinstance(evidence.get("cleanup"), dict) else False
        ),
    }))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
