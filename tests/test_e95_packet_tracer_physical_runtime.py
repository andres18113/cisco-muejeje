from __future__ import annotations

import json

from src.packet_tracer_mcp.application.use_cases.deploy_enterprise_topology import (
    EnterprisePhysicalTopologyDeployer,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import EnvironmentFingerprint
from src.packet_tracer_mcp.domain.enterprise.models.execution import MutationDisposition
from src.packet_tracer_mcp.domain.enterprise.models.execution import DirtyState
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentStatus,
)
from src.packet_tracer_mcp.domain.enterprise.services.topology_identity import stamp_topology_hashes
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan
from src.packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
)


def _double_port_inventory(topology):
    """La evidencia de puertos DEL DOBLE, que es el backend de estos tests.

    Estos casos ejercitan la MECANICA del desplegador contra un runtime falso,
    no la conformidad de Packet Tracer. El resolutor por defecto solo autoriza
    modelos realmente medidos, asi que dejarlo aqui haria que el doble tomara
    prestada evidencia tomada contra el backend real. Se declara la del doble,
    igual que ya se declaran sus observaciones.
    """
    from src.packet_tracer_mcp.domain.enterprise.models.port_inventory import (
        PortInventoryEvidenceTier,
        PortInventoryResolution,
    )

    by_model: dict[str, set[str]] = {item.model: set() for item in topology.devices}
    model_of = {item.name: item.model for item in topology.devices}
    for link in topology.links:
        for name, port in (
            (link.device_a, link.port_a), (link.device_b, link.port_b),
        ):
            if model_of.get(name):
                by_model.setdefault(model_of[name], set()).add(port)

    def _resolve(model, *, backend="packet_tracer", backend_version="", installed_modules=None):
        return PortInventoryResolution(
            model=model,
            backend=backend,
            backend_version=backend_version,
            installed_modules=sorted(installed_modules or []),
            tier=PortInventoryEvidenceTier.BACKEND_VERIFIED,
            ports=sorted(by_model.get(model, set()), key=str.casefold),
            reason="synthesised by the physical double in this test module",
        )

    return _resolve


class FakePacketTracerTransport:
    def __init__(self) -> None:
        self.devices = {
            "HQ-R1": {
                "model": "2911",
                "ports": ["GigabitEthernet0/0", "GigabitEthernet0/1"],
            },
            "HQ-SW1": {
                "model": "2960-24TT",
                "ports": ["FastEthernet0/1", "GigabitEthernet0/1"],
            },
        }
        self.link_mode = "exact"
        self.mutation_reply: str | None = json.dumps({"ack": True})
        self.calls: list[str] = []

    def __call__(self, script: str, _timeout: float) -> str | None:
        self.calls.append(script)
        if "lwAddDevice(" in script:
            self.devices["NEW-R1"] = {
                "model": "2911",
                "ports": ["GigabitEthernet0/0"],
            }
            return self.mutation_reply
        if "lwAddLink(" in script:
            self.link_mode = "exact"
            return self.mutation_reply
        if "var __o={" in script:
            if self.link_mode == "exact":
                endpoints = [
                    {"device": "HQ-R1", "port": "GigabitEthernet0/0"},
                    {"device": "HQ-SW1", "port": "GigabitEthernet0/1"},
                ]
                return json.dumps({
                    "exact": True,
                    "port_a_bound": True,
                    "port_b_bound": True,
                    "both_ports_bound": True,
                    "same_link": True,
                    "reason": "EXACT",
                    "observed_link_a": endpoints,
                    "observed_link_b": endpoints,
                })
            if self.link_mode == "one_bound":
                return json.dumps({
                    "exact": False,
                    "port_a_bound": True,
                    "port_b_bound": False,
                    "both_ports_bound": False,
                    "same_link": False,
                    "reason": "NO_LINK",
                    "observed_link_a": [],
                    "observed_link_b": [],
                })
            return json.dumps({
                "exact": False,
                "port_a_bound": False,
                "port_b_bound": False,
                "both_ports_bound": False,
                "same_link": False,
                "reason": "NO_LINK",
                "observed_link_a": [],
                "observed_link_b": [],
            })
        for name, details in self.devices.items():
            if json.dumps(name) in script:
                return json.dumps({
                    "found": True,
                    "name": name,
                    "model": details["model"],
                    "ports": details["ports"],
                })
        return json.dumps({"found": False})


def _topology() -> TopologyPlan:
    topology = TopologyPlan(
        id="e4/live-adapter",
        devices=[
            DevicePlan(
                id="r1", name="HQ-R1", model="2911", category="router",
            ),
            DevicePlan(
                id="sw1", name="HQ-SW1", model="2960-24TT", category="switch",
            ),
        ],
        links=[
            LinkPlan(
                id="link/r1-sw1",
                device_a_id="r1", device_a="HQ-R1", port_a="GigabitEthernet0/0",
                device_b_id="sw1", device_b="HQ-SW1", port_b="GigabitEthernet0/1",
                cable="straight",
            ),
        ],
    )
    stamp_topology_hashes(topology)
    return topology


def test_existing_exact_runtime_state_is_no_op_and_produces_manifest():
    transport = FakePacketTracerTransport()
    runtime = PacketTracerPhysicalTopologyRuntime(transport)

    topology = _topology()
    result = EnterprisePhysicalTopologyDeployer(
        runtime, port_inventory=_double_port_inventory(topology),
    ).deploy(
        topology,
        environment_fingerprint=EnvironmentFingerprint(
            backend="packet_tracer",
            backend_version="9.0.1.0858",
            bridge_transport="file",
        ),
    )

    assert result.status is PhysicalDeploymentStatus.VERIFIED
    assert result.manifest is not None
    assert result.manifest.compact_summary()["binding_count"] == 2
    assert all(
        item.disposition is MutationDisposition.NO_OP
        for item in result.item_results
    )
    assert not any("lwAddDevice(" in script for script in transport.calls)
    assert not any("lwAddLink(" in script for script in transport.calls)


def test_wrong_model_with_matching_name_is_rejected_before_mutation():
    transport = FakePacketTracerTransport()
    transport.devices["HQ-R1"]["model"] = "1841"
    runtime = PacketTracerPhysicalTopologyRuntime(transport)

    mutation = runtime.ensure_device(_topology().devices[0])

    assert mutation.disposition is MutationDisposition.FAILED
    assert "expected '2911'" in mutation.message
    assert not any("lwAddDevice(" in script for script in transport.calls)


def test_one_bound_link_endpoint_is_never_overwritten_or_reported_as_success():
    transport = FakePacketTracerTransport()
    transport.link_mode = "one_bound"
    runtime = PacketTracerPhysicalTopologyRuntime(transport)

    mutation = runtime.ensure_link(_topology().links[0])

    assert mutation.disposition is MutationDisposition.FAILED
    assert "already bound" in mutation.message
    assert not any("lwAddLink(" in script for script in transport.calls)


def test_absent_device_uses_trusted_mutation_then_requires_readback():
    transport = FakePacketTracerTransport()
    runtime = PacketTracerPhysicalTopologyRuntime(transport)
    device = DevicePlan(
        id="new-r1", name="NEW-R1", model="2911", category="router",
        x=10, y=20,
    )

    mutation = runtime.ensure_device(device)
    observation = runtime.observe_device(device)

    assert mutation.disposition is MutationDisposition.CHANGED
    assert mutation.applied
    assert observation.observed
    assert observation.model == "2911"
    assert observation.runtime_fingerprint
    assert any("lwAddDevice(" in script for script in transport.calls)


def test_lost_mutation_ack_is_unknown_dirty_and_never_replayed():
    transport = FakePacketTracerTransport()
    transport.devices.clear()
    transport.mutation_reply = None
    topology = TopologyPlan(
        id="e4/lost-ack",
        devices=[
            DevicePlan(
                id="new-r1", name="NEW-R1", model="2911", category="router",
            ),
        ],
    )
    stamp_topology_hashes(topology)

    result = EnterprisePhysicalTopologyDeployer(
        PacketTracerPhysicalTopologyRuntime(transport),
        port_inventory=_double_port_inventory(topology),
    ).deploy(
        topology,
        environment_fingerprint=EnvironmentFingerprint(
            backend="packet_tracer",
            backend_version="9.0.1.0858",
            bridge_transport="file",
        ),
    )

    assert result.manifest is None
    assert result.dirty_state is DirtyState.UNKNOWN
    assert result.execution_journal.entries[0].disposition is MutationDisposition.UNKNOWN
    assert result.item_results[0].disposition is MutationDisposition.UNKNOWN
    assert "ambiguous" in result.item_results[0].message
    assert sum("lwAddDevice(" in script for script in transport.calls) == 1
