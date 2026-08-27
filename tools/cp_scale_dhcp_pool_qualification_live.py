"""Governed disposable LIVE for one closed DHCP-pool query candidate.

The caller selects only whether to execute and the evidence build label.  The
device model, typed pool action, read-only candidate, evidence destination and
cleanup scope are all closed constants owned by the qualification use case.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


GOVERNED_ROOT = Path(__file__).resolve().parents[1]
if str(GOVERNED_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(GOVERNED_ROOT / "src"))

import packet_tracer_mcp  # noqa: E402
from packet_tracer_mcp.application.use_cases.qualify_dhcp_pool_command import (  # noqa: E402
    DhcpPoolCommandQualifier,
    DhcpPoolCommandSupport,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (  # noqa: E402
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (  # noqa: E402
    ImportIsolationPreflight,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (  # noqa: E402
    ControlledIosExecutor,
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
    GOVERNED_ROOT / "data" / "cp-scale" /
    "dhcp-pool-command-qualification.json"
)
ROUTER_MODEL = "2811"


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=GOVERNED_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


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


def _ios_evidence(observation) -> dict[str, object] | None:
    if observation is None:
        return None
    return {
        "query_id": observation.query_id.value,
        "executed": observation.executed,
        "fresh_output_observed": observation.fresh_output_observed,
        "output_complete": observation.output_complete,
        "output": observation.output,
        "failure_reason": observation.failure_reason,
        "session_state": observation.session_state.value,
        "truncated_by_pager": observation.truncated_by_pager,
        "pager_pages_captured": observation.pager_pages_captured,
        "pager_continuation": observation.pager_continuation,
        "dispatch_attempts": observation.dispatch_attempts,
        "dispatch_classification": observation.dispatch_classification,
        "echo_observed": observation.echo_observed,
        "observed_device_name": observation.observed_device_name,
        "device_identity_provenance": (
            observation.device_identity_provenance
        ),
        "device_identity_evidence": observation.device_identity_evidence,
    }


def _result_evidence(result) -> dict[str, object]:
    return {
        "model": result.model,
        "device_name": result.device_name,
        "command_supported": result.command_support.value,
        "configuration_applied": result.configuration_applied,
        "observation": _ios_evidence(result.observation),
        "baseline": (
            result.baseline_inventory.compact_summary()
            if result.baseline_inventory is not None else None
        ),
        "final": (
            result.final_inventory.compact_summary()
            if result.final_inventory is not None else None
        ),
        "workspace_restored": result.workspace_restored,
        "realtime_before": result.realtime_before,
        "realtime_after": result.realtime_after,
        "realtime_restored": result.realtime_restored,
        "removed": list(result.removed),
        "errors": list(result.errors),
    }


def run(packet_tracer_version: str) -> int:
    head = _git("rev-parse", "HEAD")
    upstream = _git("rev-parse", "@{upstream}")
    status = _git("status", "--porcelain")
    evidence: dict[str, object] = {
        "packet_tracer_version": packet_tracer_version,
        "source_head": head,
        "upstream_head": upstream,
        "worktree_clean": not status,
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
        "isolated": isolation.isolated,
    }
    if status or head != upstream or not isolation.isolated:
        evidence["hard_stop"] = (
            "Qualification requires a clean pushed HEAD and one governed "
            "production import namespace."
        )
        _write_evidence(evidence)
        print(json.dumps({
            "event": "DHCP_POOL_COMMAND_QUALIFICATION_REFUSED",
            "hard_stop": evidence["hard_stop"],
        }))
        return 2

    transport = PacketTracerHttpTransport()
    if not transport.start(timeout_seconds=20.0):
        evidence["hard_stop"] = "The Packet Tracer bridge did not connect."
        _write_evidence(evidence)
        print(json.dumps({
            "event": "DHCP_POOL_COMMAND_QUALIFICATION_REFUSED",
            "hard_stop": evidence["hard_stop"],
        }))
        return 2

    try:
        physical = PacketTracerPhysicalTopologyRuntime(
            transport.send_and_wait,
            mutation_timeout_seconds=30.0,
            observation_timeout_seconds=12.0,
        )
        result = DhcpPoolCommandQualifier(
            physical,
            PacketTracerEnterpriseConfigurationRuntime(
                query_inventory=lambda: _inventory(physical),
                send=transport.send,
                send_and_wait=transport.send_and_wait,
                l3_timeout_seconds=20.0,
            ),
            ControlledIosExecutor(transport.send_and_wait),
            SimulationTraceRuntime(transport.send_and_wait),
        ).qualify(ROUTER_MODEL)
    finally:
        transport.stop()

    evidence["qualification"] = _result_evidence(result)
    _write_evidence(evidence)
    print(json.dumps({
        "event": "DHCP_POOL_COMMAND_QUALIFICATION_COMPLETE",
        "command_supported": result.command_support.value,
        "configuration_applied": result.configuration_applied,
        "workspace_restored": result.workspace_restored,
        "realtime_restored": result.realtime_restored,
        "errors": list(result.errors)[:5],
    }))
    return 0 if (
        result.command_support is not DhcpPoolCommandSupport.UNOBSERVABLE
        and result.workspace_restored
        and result.realtime_restored
    ) else 1


def _write_evidence(evidence: dict[str, object]) -> None:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Authorize the owned disposable mutation after all hard gates.",
    )
    parser.add_argument("--packet-tracer-version", required=True)
    args = parser.parse_args()
    if not args.execute:
        parser.error("refusing LIVE without --execute")
    return run(args.packet_tracer_version)


if __name__ == "__main__":
    raise SystemExit(main())
