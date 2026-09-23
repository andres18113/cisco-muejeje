"""Cleanup can recover only the exact devices a verified E4 result owns."""

from __future__ import annotations

import json
import re

import pytest
from test_e95_physical_deployment_manifest import _double_port_inventory
from test_server_pt_commissioning import _EmptyCampusPhysical

from packet_tracer_mcp.application.use_cases.deploy_enterprise_topology import (
    EnterprisePhysicalTopologyDeployer,
)
from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
    prepare_server_pt_commissioning,
)
from packet_tracer_mcp.domain.enterprise.models.deployment import EnvironmentFingerprint
from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentFailureCode,
    PhysicalDeploymentItemStatus,
    PhysicalDeploymentStatus,
    PhysicalObjectKind,
)
from packet_tracer_mcp.domain.models.plans import TopologyPlan
from packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
)


def _verified_e4():
    bundle = prepare_server_pt_commissioning(
        30, "COLD_HTTP_0f1e2d3c4b5a69788796a5b4c3d2e1f0"
    )
    topology = TopologyPlan.model_validate_json(bundle.topology_json)
    result = EnterprisePhysicalTopologyDeployer(
        _EmptyCampusPhysical(topology), port_inventory=_double_port_inventory(topology)
    ).deploy(
        topology,
        environment_fingerprint=EnvironmentFingerprint(
            backend="packet_tracer",
            backend_version="9.0.1.0858",
            bridge_transport="file",
            runtime_mode="logical-workspace",
        ),
        deployment_id="deploy-c31-01",
        require_empty_workspace=True,
    )
    assert result.status is PhysicalDeploymentStatus.VERIFIED
    return topology, result


def test_new_runtime_removes_only_a_device_owned_by_verified_e4():
    """A separate cleanup process restores ownership from immutable E4 rows."""
    topology, e4 = _verified_e4()
    device = topology.devices[0]
    state = {item.name: item.model for item in topology.devices}

    def send_and_wait(script: str, _timeout: float) -> str:
        match = re.search(r'getDevice\(("(?:\\.|[^"\\])*")\)', script)
        if "removeDevice" in script:
            state.pop(device.name)
            return '{"ack":true}'
        name = json.loads(match.group(1)) if match else ""
        return json.dumps(
            {
                "found": name in state,
                "name": name,
                "model": state.get(name, ""),
                "ports": [],
            }
        )

    runtime = PacketTracerPhysicalTopologyRuntime(send_and_wait)
    assert runtime.remove_device(device).applied is False

    owned = runtime.adopt_verified_deployment_for_cleanup(topology, e4)
    removed = runtime.remove_device(device)

    assert len(owned) == 35
    assert removed.applied is True
    assert device.name not in state


def test_partial_e4_cannot_grant_cleanup_ownership():
    """An unknown physical result never authorizes a later process to remove."""
    topology, e4 = _verified_e4()
    runtime = PacketTracerPhysicalTopologyRuntime(lambda _script, _timeout: None)

    with pytest.raises(ValueError, match="verified E4"):
        runtime.adopt_verified_deployment_for_cleanup(
            topology, e4.model_copy(update={"status": PhysicalDeploymentStatus.PARTIAL})
        )


def test_historical_physical_enum_string_contract_remains_stable():
    """Scoped Ruff cleanup cannot change external enum rendering."""
    assert str(PhysicalObjectKind.DEVICE) == "PhysicalObjectKind.DEVICE"
    assert str(PhysicalDeploymentStatus.VERIFIED) == "PhysicalDeploymentStatus.VERIFIED"
    assert (
        str(PhysicalDeploymentItemStatus.OBSERVED)
        == "PhysicalDeploymentItemStatus.OBSERVED"
    )
    assert (
        str(PhysicalDeploymentFailureCode.NONE) == "PhysicalDeploymentFailureCode.NONE"
    )
