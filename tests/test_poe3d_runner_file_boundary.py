"""POE-3B runner authority: one bounded session, no raw transport bypass."""

from __future__ import annotations

import ast
from pathlib import Path


RUNNER = Path(__file__).resolve().parents[1] / "tools" / "poe3a_pse_live.py"
_FORBIDDEN_MODULES = {
    "importlib",
    "packet_tracer_mcp.infrastructure.execution.configuration_runtime",
    "packet_tracer_mcp.infrastructure.execution.file_bridge",
    "packet_tracer_mcp.infrastructure.execution.live_bridge",
    "packet_tracer_mcp.infrastructure.execution.poe_delivery_runtime",
    "packet_tracer_mcp.infrastructure.execution.poe_inline_observer",
    "packet_tracer_mcp.infrastructure.execution.pt_file_operations",
    "poe2_ap_live",
    "poe_inline_calibration_live",
}
_FORBIDDEN_NAMES = {
    "ControlledIosExecutor",
    "Experiment",
    "FileBridge",
    "GovernedPoEInlineObserver",
    "PTCommandBridge",
    "PacketTracerConfigurationRuntime",
    "PacketTracerFileOperationGuard",
    "PacketTracerFileOperationResult",
    "PacketTracerPoEDeliveryFixtureRuntime",
    "__import__",
    "getattr",
    "setattr",
    "vars",
}
_FORBIDDEN_ATTRIBUTES = {
    "_pending",
    "_transport",
    "__dict__",
    "bridge",
    "config",
    "executor",
    "fixture",
    "observer",
    "send",
    "send_and_wait",
}


def _boundary_violations(source: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module in _FORBIDDEN_MODULES:
                violations.append(f"forbidden import module: {node.module}")
            for alias in node.names:
                if alias.name in _FORBIDDEN_NAMES:
                    violations.append(f"forbidden import name: {alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _FORBIDDEN_MODULES:
                    violations.append(f"forbidden import module: {alias.name}")
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_ATTRIBUTES:
            violations.append(f"forbidden transport attribute: {node.attr}")
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            violations.append(f"forbidden transport name: {node.id}")
    return tuple(sorted(set(violations)))


def test_runner_has_no_raw_transport_or_component_route_around_session() -> None:
    assert _boundary_violations(RUNNER.read_text(encoding="utf-8")) == ()


def test_deliberate_file_transport_bypass_mutation_is_rejected() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    mutated = source + "\nFileBridge().send('synthetic bypass')\n"

    violations = _boundary_violations(mutated)

    assert "forbidden transport name: FileBridge" in violations
    assert "forbidden transport attribute: send" in violations

    private_bypass = source + "\nsession._transport.send('synthetic bypass')\n"
    private_violations = _boundary_violations(private_bypass)
    assert "forbidden transport attribute: _transport" in private_violations
    assert "forbidden transport attribute: send" in private_violations
