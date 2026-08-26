"""Driver LIVE de la calibración de `child.vlanId` sobre un desechable propio.

No decide nada: arma los runtimes gobernados que este repositorio ya usa, corre
`FrameVlanCalibrationQualifier` y escribe lo observado. La lógica -- qué frame
puede calibrar y qué no -- vive en el caso de uso y está cubierta contra fakes,
así que este archivo es cableado y nada más.

La composición de tráfico es la MEDIDA, no la conveniente: el cliente DHCP se
arma en Realtime y sus reintentos entran al switch por el puerto de acceso y
aparecen en el event list al avanzar Simulación. Un ping tipado NO se usa: su
ejecutor espera una ventana fresca de terminal que en Simulación no puede llegar
sin avanzar el reloj, y esa composición no está medida en este repositorio.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GOVERNED_ROOT = Path(__file__).resolve().parents[1]
if str(GOVERNED_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(GOVERNED_ROOT / "src"))

from packet_tracer_mcp.application.use_cases.qualify_frame_vlan_calibration import (  # noqa: E402
    CONTROL_VLAN_IDS,
    FrameVlanCalibrationQualifier,
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

EVIDENCE_PATH = GOVERNED_ROOT / "data" / "cp-scale" / "vlan-calibration.json"
#: Modelos ya cualificados sobre PT 9.0.1.0858 por las corridas de CP-SCALE.
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
        "diagnostic": "FRAME_VLAN_CALIBRATION",
        "model": result.model,
        "switch_name": result.switch_name,
        "control_vlan_ids": list(CONTROL_VLAN_IDS),
        "frame_vlan_field_semantics": result.semantics,
        "controls": [
            {
                "vlan_id": item.vlan_id,
                "switch_interface": item.switch_interface,
                "endpoint_name": item.endpoint_name,
                "access_vlan_verified": item.access_vlan_verified,
                "expected_vlan_qualified": item.expected_vlan_qualified,
                "frame_index": item.frame_index,
                "frame_observed_in_port": item.frame_observed_in_port,
                "frame_previous_device": item.frame_previous_device,
                "identity_reconfirmed": item.identity_reconfirmed,
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
        "workspace_restored": result.restored,
        "realtime_restored": result.realtime_restored,
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
        result = FrameVlanCalibrationQualifier(
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
        encoding="utf-8", newline="\n",
    )
    print(json.dumps({
        "event": "VLAN_CALIBRATION_COMPLETE",
        "semantics": evidence["frame_vlan_field_semantics"],
        "controls": [
            {k: item[k] for k in ("vlan_id", "switch_interface", "frame_index",
                                  "observed_vlan", "match")}
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
        "--execute", action="store_true",
        help="Authorize the disposable mutations after the empty-baseline gate.",
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
