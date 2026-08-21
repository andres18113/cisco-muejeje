"""Bounded live qualification for typed EIGRP evidence on Packet Tracer.

This is an operator-only harness.  It refuses any workspace containing a
semantic device or link, applies only typed production actions to disposable
objects, and independently re-observes cleanup.  It never saves a ``.pkt`` and
does not accept raw IOS or JavaScript from the caller.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import packet_tracer_mcp

from packet_tracer_mcp.application.use_cases.compile_control_plane import (
    compile_enterprise_control_plane,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigurationPlan,
    ConfigureRoutedInterface,
    SetEndpointStaticAddress,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureEigrpIpv4,
    ControlPlaneIntent,
    ControlPlaneVerificationKind,
    DynamicRoutingIntent,
    DynamicRoutingProtocol,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    MutationDisposition,
)
from packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan
from packet_tracer_mcp.infrastructure.catalog.control_plane_capabilities import (
    packet_tracer_control_plane_capabilities,
)
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
    EigrpQueryClassification,
    IosCommandResult,
    OperationalQueryId,
    classify_show_ip_eigrp_neighbors,
    classify_show_ip_route_eigrp,
    parse_show_ip_interface_brief,
)
from packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
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
PROBE_PREFIX = "MCP-PROBE-EIGRP-CP3"
EVIDENCE_PATH = GOVERNED_ROOT / "data" / "eigrp-runtime-qualification.json"


def _devices() -> list[DevicePlan]:
    return [
        DevicePlan(
            id="r1", name=f"{PROBE_PREFIX}-R1", model="1941",
            category="router", site_id="cp3", enterprise_role="edge_router",
            x=160, y=120,
        ),
        DevicePlan(
            id="r2", name=f"{PROBE_PREFIX}-R2", model="1941",
            category="router", site_id="cp3", enterprise_role="edge_router",
            x=480, y=120,
        ),
        DevicePlan(
            id="pca", name=f"{PROBE_PREFIX}-PCA", model="PC-PT",
            category="pc", site_id="cp3", enterprise_role="user_pc",
            x=80, y=300,
        ),
        DevicePlan(
            id="pcb", name=f"{PROBE_PREFIX}-PCB", model="PC-PT",
            category="pc", site_id="cp3", enterprise_role="user_pc",
            x=560, y=300,
        ),
    ]


def _links(devices: list[DevicePlan]) -> list[LinkPlan]:
    by_id = {item.id: item for item in devices}

    def link(
        link_id: str,
        left: str,
        left_port: str,
        right: str,
        right_port: str,
        cable: str,
        role: str,
    ) -> LinkPlan:
        return LinkPlan(
            id=link_id,
            device_a=by_id[left].name,
            device_a_id=left,
            port_a=left_port,
            device_b=by_id[right].name,
            device_b_id=right,
            port_b=right_port,
            cable=cable,
            link_role=role,
        )

    return [
        link(
            "lan-a", "r1", "GigabitEthernet0/0", "pca", "FastEthernet0",
            "straight", "endpoint_access",
        ),
        link(
            "transit-r1-r2", "r1", "GigabitEthernet0/1",
            "r2", "GigabitEthernet0/1", "cross", "core_link",
        ),
        link(
            "lan-b", "r2", "GigabitEthernet0/0", "pcb", "FastEthernet0",
            "straight", "endpoint_access",
        ),
    ]


def _configuration(
    topology: TopologyPlan,
) -> ConfigurationPlan:
    by_id = {item.id: item for item in topology.devices}
    routed = (
        ("r1", "GigabitEthernet0/0", "198.18.210.1", 24, "lan-a"),
        ("r1", "GigabitEthernet0/1", "198.18.212.1", 30, "transit-r1-r2"),
        ("r2", "GigabitEthernet0/0", "198.18.211.1", 24, "lan-b"),
        ("r2", "GigabitEthernet0/1", "198.18.212.2", 30, "transit-r1-r2"),
    )
    actions = [
        ConfigureRoutedInterface(
            id=f"cfg/l3/{device_id}/{segment}",
            phase=ConfigurationPhase.L3_INTERFACES,
            device_id=device_id,
            device_name=by_id[device_id].name,
            site_id="cp3",
            interface=interface,
            ipv4=ipv4,
            prefix=prefix,
            netmask="255.255.255.252" if prefix == 30 else "255.255.255.0",
            segment_id=segment,
            required_capability="layer3",
        )
        for device_id, interface, ipv4, prefix, segment in routed
    ]
    actions.extend((
        SetEndpointStaticAddress(
            id="cfg/endpoint/pca",
            phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
            device_id="pca",
            device_name=by_id["pca"].name,
            site_id="cp3",
            interface="FastEthernet0",
            ipv4="198.18.210.10",
            netmask="255.255.255.0",
            gateway="198.18.210.1",
            segment_id="lan-a",
        ),
        SetEndpointStaticAddress(
            id="cfg/endpoint/pcb",
            phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
            device_id="pcb",
            device_name=by_id["pcb"].name,
            site_id="cp3",
            interface="FastEthernet0",
            ipv4="198.18.211.10",
            netmask="255.255.255.0",
            gateway="198.18.211.1",
            segment_id="lan-b",
        ),
    ))
    return ConfigurationPlan(
        id="cp3-eigrp-foundation",
        source_topology_id=topology.id,
        source_topology_hash=topology.semantic_hash,
        semantic_hash="cp3-eigrp-foundation-v1",
        actions=actions,
    )


def _control_plane(topology: TopologyPlan, configuration: ConfigurationPlan):
    intent = ControlPlaneIntent(
        id="cp3-eigrp-qualification",
        routing_domains=[DynamicRoutingIntent(
            id="routing/cp3-eigrp",
            site_id="cp3",
            protocol=DynamicRoutingProtocol.EIGRP,
            device_ids=["r1", "r2"],
            transit_link_ids=["transit-r1-r2"],
            eigrp_as_number=100,
        )],
    )
    return compile_enterprise_control_plane(
        intent,
        topology,
        configuration,
        capabilities=packet_tracer_control_plane_capabilities(),
    )


def _inventory(physical: PacketTracerPhysicalTopologyRuntime) -> list[dict]:
    observation = physical.observe_workspace()
    if not observation.observed:
        raise RuntimeError("Live inventory became unobservable: " + observation.message)
    return [
        {"name": item.name, "model": item.model, "ports": list(item.ports)}
        for item in observation.semantic_devices
    ]


def _physical_result(result) -> dict[str, object]:
    return {
        "target_id": result.target_id,
        "disposition": result.disposition.value,
        "applied": result.applied,
        "message": result.message,
    }


def _ios_result(result: IosCommandResult) -> dict[str, object]:
    return {
        "device_name": result.device_name,
        "query_id": result.query_id.value,
        "executed": result.executed,
        "fresh_output_observed": result.fresh_output_observed,
        "output_complete": result.output_complete,
        "truncated_by_pager": result.truncated_by_pager,
        "failure_reason": result.failure_reason,
        "window_strategy": result.window_strategy,
        "dispatch_attempts": result.dispatch_attempts,
        "output": result.output,
    }


def _wait_for_ping(
    executor: TypedPingExecutor,
    source: str,
    destination: str,
    *,
    attempts: int = 3,
    interval_seconds: float = 3.0,
) -> TypedPingResult:
    result = executor.ping(source, destination)
    for _ in range(attempts - 1):
        if result.fresh_output_observed and result.reachable:
            break
        time.sleep(interval_seconds)
        result = executor.ping(source, destination)
    return result


def _wait_for_eigrp_query(
    ios: ControlledIosExecutor,
    device_name: str,
    query_id: OperationalQueryId,
    *,
    expected_as_number: int = 100,
    attempts: int = 8,
    interval_seconds: float = 2.0,
) -> tuple[IosCommandResult, str]:
    result = ios.execute(device_name, query_id)
    classification = EigrpQueryClassification.QUERY_TIMEOUT
    for attempt in range(attempts):
        if query_id is OperationalQueryId.SHOW_IP_EIGRP_NEIGHBORS:
            classification = classify_show_ip_eigrp_neighbors(
                result.output,
                executed=result.executed and result.fresh_output_observed,
                expected_as_number=expected_as_number,
            )
        else:
            classification = classify_show_ip_route_eigrp(
                result.output,
                executed=result.executed and result.fresh_output_observed,
            )
        if classification not in {
            EigrpQueryClassification.SUPPORTED_EMPTY,
            EigrpQueryClassification.QUERY_TIMEOUT,
        }:
            break
        if attempt + 1 < attempts:
            time.sleep(interval_seconds)
            result = ios.execute(device_name, query_id)
    return result, classification.value


def _router_interfaces_ready(
    ios: ControlledIosExecutor,
    router_names: list[str],
) -> tuple[bool, list[dict[str, object]]]:
    expected = {
        router_names[0]: {
            "GigabitEthernet0/0": "198.18.210.1",
            "GigabitEthernet0/1": "198.18.212.1",
        },
        router_names[1]: {
            "GigabitEthernet0/0": "198.18.211.1",
            "GigabitEthernet0/1": "198.18.212.2",
        },
    }
    captured: list[dict[str, object]] = []
    ready = False
    for attempt in range(8):
        captured = []
        ready = True
        for name in router_names:
            result = ios.execute(name, OperationalQueryId.SHOW_IP_INTERFACE_BRIEF)
            rows = {item.interface: item for item in parse_show_ip_interface_brief(result.output)}
            matches = all(
                interface in rows
                and rows[interface].ip_address == address
                and rows[interface].status.casefold() == "up"
                and rows[interface].protocol.casefold() == "up"
                for interface, address in expected[name].items()
            )
            ready = ready and result.fresh_output_observed and matches
            captured.append({**_ios_result(result), "expected_up_up": matches})
        if ready or attempt == 7:
            break
        time.sleep(2.0)
    return ready, captured


def run(packet_tracer_version: str) -> tuple[dict[str, object], int]:
    evidence: dict[str, object] = {
        "packet_tracer_version": packet_tracer_version,
        "probe_prefix": PROBE_PREFIX,
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

    bridge = FileBridge()
    evidence["file_bridge_alive"] = bridge.pt_alive()
    if not bridge.pt_alive():
        evidence["hard_stop"] = "Packet Tracer file bridge is not alive."
        return evidence, 2

    physical = PacketTracerPhysicalTopologyRuntime(
        bridge.send_and_wait,
        mutation_timeout_seconds=8.0,
        observation_timeout_seconds=8.0,
    )
    baseline = physical.observe_workspace()
    evidence["baseline"] = baseline.compact_summary()
    if not baseline.safe_for_disposable_mutation:
        evidence["hard_stop"] = (
            "Workspace contains semantic topology or inventory is incomplete."
        )
        return evidence, 2

    devices = _devices()
    links = _links(devices)
    topology = TopologyPlan(
        id="cp3-eigrp-topology",
        semantic_hash="cp3-eigrp-topology-v1",
        devices=devices,
        links=links,
    )
    configuration = _configuration(topology)
    compiled = _control_plane(topology, configuration)
    evidence["compile"] = {
        "valid": compiled.is_valid,
        "issues": [item.model_dump(mode="json") for item in compiled.issues],
        "action_types": (
            [item.action_type.value for item in compiled.plan.actions]
            if compiled.plan else []
        ),
        "expectation_kinds": (
            [item.kind.value for item in compiled.plan.verification_expectations]
            if compiled.plan else []
        ),
    }
    if not compiled.is_valid or compiled.plan is None:
        evidence["hard_stop"] = "Current typed EIGRP plan did not compile."
        return evidence, 2

    qualification_error = ""
    exit_code = 1
    try:
        physical_results: list[dict[str, object]] = []
        for device in devices:
            mutation = physical.ensure_device(device)
            physical_results.append(_physical_result(mutation))
            if mutation.disposition not in {
                MutationDisposition.CHANGED,
                MutationDisposition.NO_OP,
            }:
                raise RuntimeError(
                    f"Device creation failed for {device.name}: {mutation.message}"
                )
            observed = physical.observe_device(device)
            if not observed.observed or observed.deployed_name != device.name:
                raise RuntimeError(f"Device read-back failed for {device.name}.")
        for link in links:
            mutation = physical.ensure_link(link)
            physical_results.append(_physical_result(mutation))
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
        applied_foundation = configuration_runtime.apply_actions(
            configuration.actions,
        )
        evidence["foundation_application"] = [
            item.model_dump(mode="json") for item in applied_foundation
        ]
        if not all(item.applied for item in applied_foundation):
            raise RuntimeError("A typed foundational configuration action failed.")

        ios = ControlledIosExecutor(bridge.send_and_wait)
        router_names = [devices[0].name, devices[1].name]
        interfaces_ready, interface_evidence = _router_interfaces_ready(
            ios, router_names,
        )
        evidence["foundation_router_readback"] = interface_evidence
        if not interfaces_ready:
            raise RuntimeError("Router interfaces did not reach fresh up/up read-back.")

        ping = TypedPingExecutor(
            bridge.send_and_wait,
            timeout_seconds=30.0,
            measurement_attempts=3,
        )
        baseline_pings = {
            "pca_to_gateway": _wait_for_ping(
                ping, devices[2].name, "198.18.210.1",
            ),
            "pcb_to_gateway": _wait_for_ping(
                ping, devices[3].name, "198.18.211.1",
            ),
            "r1_to_r2_transit": _wait_for_ping(
                ping, devices[0].name, "198.18.212.2",
            ),
        }
        evidence["pre_eigrp_baseline"] = {
            key: serialize_typed_ping_evidence(value)
            for key, value in baseline_pings.items()
        }
        if not all(
            item.fresh_output_observed and item.reachable
            for item in baseline_pings.values()
        ):
            raise RuntimeError("Connected-path baseline failed before EIGRP.")

        negative_controls = {
            "pca_to_pcb_without_eigrp": ping.ping(
                devices[2].name, "198.18.211.10",
            ),
            "pcb_to_pca_without_eigrp": ping.ping(
                devices[3].name, "198.18.210.10",
            ),
        }
        evidence["pre_eigrp_negative_controls"] = {
            key: serialize_typed_ping_evidence(value)
            for key, value in negative_controls.items()
        }
        if not all(
            item.fresh_output_observed and not item.reachable
            for item in negative_controls.values()
        ):
            raise RuntimeError(
                "The cross-LAN negative control was not fresh and unreachable "
                "before EIGRP application."
            )

        eigrp_actions = [
            item for item in compiled.plan.actions
            if isinstance(item, ConfigureEigrpIpv4)
        ]
        control_runtime = PacketTracerEnterpriseControlPlaneRuntime(
            query_inventory=lambda: _inventory(physical),
            send=bridge.send,
            send_and_wait=bridge.send_and_wait,
        )
        applied_eigrp = control_runtime.apply_actions(eigrp_actions)
        evidence["eigrp_application"] = [
            item.model_dump(mode="json") for item in applied_eigrp
        ]
        if len(applied_eigrp) != 2 or not all(item.applied for item in applied_eigrp):
            raise RuntimeError("Typed EIGRP application was not accepted on both routers.")

        process: dict[str, dict[str, object]] = {}
        neighbors: dict[str, dict[str, object]] = {}
        routes: dict[str, dict[str, object]] = {}
        for name in router_names:
            process[name] = _ios_result(
                ios.execute(name, OperationalQueryId.SHOW_IP_PROTOCOLS)
            )
            result, classification = _wait_for_eigrp_query(
                ios, name, OperationalQueryId.SHOW_IP_EIGRP_NEIGHBORS,
            )
            neighbors[name] = {
                **_ios_result(result), "classification": classification,
            }
            result, classification = _wait_for_eigrp_query(
                ios, name, OperationalQueryId.SHOW_IP_ROUTE_EIGRP,
            )
            routes[name] = {
                **_ios_result(result), "classification": classification,
            }
        evidence["eigrp_process"] = process
        evidence["eigrp_neighbors"] = neighbors
        evidence["eigrp_routes"] = routes

        typed_expectations = [
            item for item in compiled.plan.verification_expectations
            if item.expected.get("protocol") == DynamicRoutingProtocol.EIGRP.value
            and item.kind in {
                ControlPlaneVerificationKind.ROUTING_PROCESS,
                ControlPlaneVerificationKind.ROUTING_NEIGHBOR,
                ControlPlaneVerificationKind.ROUTE_PRESENT,
            }
        ]
        typed_observations = control_runtime.verify(typed_expectations)
        evidence["typed_eigrp_observations"] = [
            item.model_dump(mode="json") for item in typed_observations
        ]
        typed_observers_verified = (
            len(typed_observations) == 6
            and all(
                item.status is ActionExecutionStatus.VERIFIED
                for item in typed_observations
                if next(
                    expected for expected in typed_expectations
                    if expected.id == item.expectation_id
                ).kind in {
                    ControlPlaneVerificationKind.ROUTING_PROCESS,
                    ControlPlaneVerificationKind.ROUTING_NEIGHBOR,
                }
            )
            and all(
                item.status in {
                    ActionExecutionStatus.VERIFIED,
                    ActionExecutionStatus.PARTIAL,
                }
                and all(
                    item.fields.get(field) is FieldVerificationStatus.VERIFIED
                    for field in ("protocol", "network", "prefix_length")
                )
                for item in typed_observations
                if next(
                    expected for expected in typed_expectations
                    if expected.id == item.expectation_id
                ).kind is ControlPlaneVerificationKind.ROUTE_PRESENT
            )
        )
        if not typed_observers_verified:
            raise RuntimeError(
                "Current typed EIGRP observers did not verify every required core field."
            )

        forwarding = {
            "pca_to_pcb": _wait_for_ping(
                ping, devices[2].name, "198.18.211.10", attempts=4,
                interval_seconds=5.0,
            ),
            "pcb_to_pca": _wait_for_ping(
                ping, devices[3].name, "198.18.210.10", attempts=4,
                interval_seconds=5.0,
            ),
        }
        evidence["eigrp_forwarding"] = {
            key: serialize_typed_ping_evidence(value)
            for key, value in forwarding.items()
        }
        evidence["forwarding_transition_verified"] = (
            typed_ping_behavior_transition_verified(
                negative_controls.values(), forwarding.values(),
            )
        )
        exit_code = 0 if (
            typed_observers_verified
            and evidence["forwarding_transition_verified"]
        ) else 1
    except Exception as exc:  # cleanup still runs for every bounded failure
        qualification_error = str(exc)
        exit_code = 1
    finally:
        cleanup: list[dict[str, object]] = []
        for device in reversed(devices):
            cleanup.append(_physical_result(physical.remove_device(device)))
        bridge.collect_completed()
        final_first = physical.observe_workspace()
        final_second = physical.observe_workspace()
        evidence["cleanup"] = cleanup
        evidence["final_inventory_first"] = final_first.compact_summary()
        evidence["final_inventory_second"] = final_second.compact_summary()
        cleanup_verified = (
            final_first.safe_for_disposable_mutation
            and final_second.safe_for_disposable_mutation
        )
        evidence["cleanup_verified"] = cleanup_verified
        if not cleanup_verified:
            exit_code = 1
    if qualification_error:
        evidence["qualification_error"] = qualification_error
    return evidence, exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Authorize the bounded disposable mutation after all hard gates.",
    )
    parser.add_argument(
        "--packet-tracer-version",
        required=True,
        help="Fresh externally observed Packet Tracer build for evidence scope.",
    )
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({
            "hard_stop": "--execute is required; no Packet Tracer mutation occurred.",
        }))
        return 2
    evidence, exit_code = run(args.packet_tracer_version)
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "evidence_path": str(EVIDENCE_PATH),
        "packet_tracer_version": evidence.get("packet_tracer_version", ""),
        "hard_stop": evidence.get("hard_stop", ""),
        "qualification_error": evidence.get("qualification_error", ""),
        "cleanup_verified": evidence.get("cleanup_verified", False),
        "exit_code": exit_code,
    }, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
