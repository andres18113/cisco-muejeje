"""Governed LIVE for the singleton non-native trunk-ingress VLAN controls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GOVERNED_ROOT = Path(__file__).resolve().parents[1]
if str(GOVERNED_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(GOVERNED_ROOT / "src"))

from packet_tracer_mcp.application.use_cases.qualify_trunk_frame_vlan_calibration import (  # noqa: E402
    CONTROL_VLAN_IDS,
    TrunkFrameVlanCalibrationQualifier,
)
from packet_tracer_mcp.infrastructure.execution.configuration_runtime import (  # noqa: E402
    PacketTracerConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (  # noqa: E402
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.frame_observer_probe import (  # noqa: E402
    PacketTracerFrameObserverProbe,
)
from packet_tracer_mcp.infrastructure.execution.live_bridge import (  # noqa: E402
    PacketTracerHttpTransport,
)
from packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime import (  # noqa: E402
    PacketTracerPhysicalTopologyRuntime,
)
from packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (  # noqa: E402
    SimulationTraceRuntime,
)


EVIDENCE_PATH = (
    GOVERNED_ROOT / "data" / "cp-scale" / "trunk-vlan-calibration.json"
)
SWITCH_MODEL = "3560-24PS"
ENDPOINT_MODEL = "PC-PT"


def _inventory(physical) -> list[dict]:
    observation = physical.observe_workspace()
    if not observation.observed:
        raise RuntimeError("Live inventory became unobservable: " + observation.message)
    return [
        {"name": item.name, "model": item.model, "ports": list(item.ports)}
        for item in observation.semantic_devices
    ]


def _serialize(result) -> dict:
    return {
        "diagnostic": "TRUNK_FRAME_VLAN_CALIBRATION",
        "model": result.model,
        "source_switch_name": result.source_switch_name,
        "target_switch_name": result.target_switch_name,
        "control_vlan_ids": list(CONTROL_VLAN_IDS),
        "frame_vlan_field_semantics": result.semantics,
        "parallel_trunk_control_independence_established": (
            result.parallel_trunk_control_independence_established
        ),
        "controls": [
            {
                "target_vlan_id": item.target_vlan_id,
                "expected_vlan": item.expected_vlan,
                "switch_interface": item.switch_interface,
                "source_switch_name": item.source_switch_name,
                "convergence_verified": item.convergence_verified,
                "readback_fresh": item.readback_fresh,
                "readback_complete": item.readback_complete,
                "trunk_status": item.trunk_status,
                "allowed_vlans": (
                    list(item.allowed_vlans)
                    if item.allowed_vlans is not None else None
                ),
                "active_vlans": (
                    list(item.active_vlans)
                    if item.active_vlans is not None else None
                ),
                "forwarding_vlans": (
                    list(item.forwarding_vlans)
                    if item.forwarding_vlans is not None else None
                ),
                "native_vlan": item.native_vlan,
                "endpoint_armed": item.endpoint_armed,
                "frame_entered_policy_qualified_trunk": (
                    item.frame_entered_policy_qualified_trunk
                ),
                "single_allowed_non_native_trunk_policy_proven": (
                    item.single_allowed_non_native_trunk_policy_proven
                ),
                "frame_admitted_for_target_vlan": (
                    item.frame_admitted_for_target_vlan
                ),
                "frame_index": item.frame_index,
                "frame_observed_in_port": item.frame_observed_in_port,
                "frame_previous_device": item.frame_previous_device,
                "source_to_target_hop_identity_reconfirmed": (
                    item.source_to_target_hop_identity_reconfirmed
                ),
                "selected_frame_end_to_end_dhcp_identity_established": (
                    item.selected_frame_end_to_end_dhcp_identity_established
                ),
                "child_returned": item.child_returned,
                "child_members": list(item.child_members),
                "tag_fields_present": list(item.tag_fields_present),
                "observed_vlan": item.observed_vlan,
                "match": item.match,
                "failure_reason": item.failure_reason,
            }
            for item in result.controls
        ],
        "baseline": (
            result.baseline_inventory.compact_summary()
            if result.baseline_inventory is not None else None
        ),
        "final": (
            result.final_inventory.compact_summary()
            if result.final_inventory is not None else None
        ),
        "workspace_restored": result.workspace_restored,
        "realtime_restored": result.realtime_restored,
        "owned_links": list(result.owned_links),
        "removed": list(result.removed),
        "errors": list(result.errors),
    }


def run(packet_tracer_version: str) -> int:
    transport = PacketTracerHttpTransport()
    if not transport.start(timeout_seconds=20.0):
        print(json.dumps({"hard_stop": "The Packet Tracer bridge did not connect."}))
        return 2
    try:
        physical = PacketTracerPhysicalTopologyRuntime(
            transport.send_and_wait,
            mutation_timeout_seconds=30.0,
            observation_timeout_seconds=12.0,
        )
        result = TrunkFrameVlanCalibrationQualifier(
            physical,
            PacketTracerEnterpriseConfigurationRuntime(
                lambda: _inventory(physical),
                transport.send,
                transport.send_and_wait,
                l3_timeout_seconds=20.0,
            ),
            PacketTracerConfigurationRuntime(transport.send),
            SimulationTraceRuntime(transport.send_and_wait),
            PacketTracerFrameObserverProbe(transport.send_and_wait),
        ).qualify(SWITCH_MODEL, ENDPOINT_MODEL)
    finally:
        transport.stop()

    evidence = _serialize(result)
    evidence["packet_tracer_version"] = packet_tracer_version
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "event": "TRUNK_VLAN_CALIBRATION_COMPLETE",
        "semantics": evidence["frame_vlan_field_semantics"],
        "controls": [
            {
                key: item[key]
                for key in (
                    "target_vlan_id", "expected_vlan", "switch_interface",
                    "allowed_vlans", "active_vlans", "forwarding_vlans",
                    "native_vlan", "frame_index", "observed_vlan", "match",
                )
            }
            for item in evidence["controls"]
        ],
        "workspace_restored": evidence["workspace_restored"],
        "realtime_restored": evidence["realtime_restored"],
        "removed": len(evidence["removed"]),
        "errors": evidence["errors"][:3],
        "evidence_path": str(EVIDENCE_PATH),
    }, ensure_ascii=False))
    return 0 if not result.errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Authorize disposable mutations after the empty-baseline gate.",
    )
    parser.add_argument("--packet-tracer-version", required=True)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({
            "hard_stop": "--execute is required; no Packet Tracer mutation occurred.",
        }))
        return 2
    return run(args.packet_tracer_version)


if __name__ == "__main__":
    raise SystemExit(main())
