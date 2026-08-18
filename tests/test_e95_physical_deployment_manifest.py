from __future__ import annotations

from copy import deepcopy

import pytest

from src.packet_tracer_mcp.application.use_cases.deploy_enterprise_topology import (
    EnterprisePhysicalTopologyDeployer,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import EnvironmentFingerprint
from src.packet_tracer_mcp.domain.enterprise.models.execution import DirtyState, MutationDisposition
from src.packet_tracer_mcp.domain.enterprise.models.evidence import (
    EvidenceFreshness,
    ObservationStatus,
    SupportStatus,
    VerificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentFailureCode,
    PhysicalDeploymentStatus,
    PhysicalDeviceObservation,
    PhysicalLinkObservation,
    PhysicalModuleEffectCapability,
    PhysicalModuleObservation,
    PhysicalMutationResult,
    PhysicalObjectKind,
)
from src.packet_tracer_mcp.domain.enterprise.services.topology_identity import stamp_topology_hashes
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, ModulePlan, TopologyPlan


def _topology() -> TopologyPlan:
    topology = TopologyPlan(
        id="e4/physical-reference",
        devices=[
            DevicePlan(
                id="r1", name="HQ-R1", model="2911", category="router",
                x=100, y=100,
            ),
            DevicePlan(
                id="sw1", name="HQ-SW1", model="2960-24TT", category="switch",
                x=100, y=300,
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


def _fingerprint() -> EnvironmentFingerprint:
    return EnvironmentFingerprint(
        backend="packet_tracer",
        backend_version="9.0.1.0858",
        bridge_transport="http",
        extension_version="5",
        runtime_mode="logical-workspace",
    )


class FakePhysicalRuntime:
    def __init__(self) -> None:
        self.device_observations = {
            "r1": PhysicalDeviceObservation(
                target_id="r1", deployed_name="HQ-R1", model="2911",
                interfaces=[
                    "GigabitEthernet0/0", "GigabitEthernet0/1",
                    "Serial0/0/0", "Serial0/0/1",
                ],
                runtime_identifier="runtime-r1", runtime_identifier_stable=True,
                runtime_fingerprint="fp-r1",
            ),
            "sw1": PhysicalDeviceObservation(
                target_id="sw1", deployed_name="HQ-SW1", model="2960-24TT",
                interfaces=["GigabitEthernet0/1", "FastEthernet0/1"],
                runtime_identifier="runtime-sw1", runtime_identifier_stable=True,
                runtime_fingerprint="fp-sw1",
            ),
        }
        self.link_observations = {
            "link/r1-sw1": PhysicalLinkObservation(
                target_id="link/r1-sw1",
                device_a="HQ-R1", port_a="GigabitEthernet0/0",
                device_b="HQ-SW1", port_b="GigabitEthernet0/1",
                cable="straight", cable_observed=True,
            ),
        }
        self.fail_device = ""
        self.module_observation_supported = False
        self.calls: list[str] = []

    def module_effect_capability(
        self,
        module: ModulePlan,
        device: DevicePlan,
    ) -> PhysicalModuleEffectCapability:
        target_id = f"{module.device}:{module.slot}:{module.module}"
        return PhysicalModuleEffectCapability(
            target_id=target_id,
            operation_support=(
                SupportStatus.SUPPORTED
                if self.module_observation_supported else SupportStatus.UNKNOWN
            ),
            effect_observation_support=(
                SupportStatus.SUPPORTED
                if self.module_observation_supported else SupportStatus.UNKNOWN
            ),
            expected_ports=["Serial0/0/0", "Serial0/0/1"],
            expected_port_classes=["serial"],
            identity_observation_status=ObservationStatus.UNOBSERVABLE,
        )

    def ensure_device(self, device: DevicePlan) -> PhysicalMutationResult:
        self.calls.append(f"ensure-device:{device.id}")
        if device.id == self.fail_device:
            return PhysicalMutationResult(
                target_id=device.id,
                target_kind=PhysicalObjectKind.DEVICE,
                disposition=MutationDisposition.FAILED,
                message="controlled creation failure",
            )
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
            inverse_available=True,
            inverse_action_id=f"remove-device:{device.id}",
        )

    def observe_device(self, device: DevicePlan) -> PhysicalDeviceObservation:
        self.calls.append(f"observe-device:{device.id}")
        return self.device_observations[device.id]

    def ensure_module(self, module: ModulePlan) -> PhysicalMutationResult:
        target_id = f"{module.device}:{module.slot}:{module.module}"
        self.calls.append(f"ensure-module:{target_id}")
        return PhysicalMutationResult(
            target_id=target_id,
            target_kind=PhysicalObjectKind.MODULE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )

    def observe_module_effect(self, module: ModulePlan) -> PhysicalModuleObservation:
        target_id = f"{module.device}:{module.slot}:{module.module}"
        self.calls.append(f"observe-module-effect:{target_id}")
        return PhysicalModuleObservation(
            target_id=target_id,
            device_name=module.device,
            requested_slot=module.slot,
            requested_module=module.module,
            freshness=EvidenceFreshness.FRESH,
            port_inventory_observed=True,
            expected_ports=["Serial0/0/0", "Serial0/0/1"],
            expected_port_classes=["serial"],
            ports_before=["GigabitEthernet0/0", "GigabitEthernet0/1"],
            ports_after=[
                "GigabitEthernet0/0", "GigabitEthernet0/1",
                "Serial0/0/0", "Serial0/0/1",
            ],
            observed_expected_ports=["Serial0/0/0", "Serial0/0/1"],
            added_ports=["Serial0/0/0", "Serial0/0/1"],
            observed_port_classes=["serial"],
            device_newly_owned=True,
            effect_observed=True,
            identity_observation_status=ObservationStatus.UNOBSERVABLE,
        )

    def ensure_link(self, link: LinkPlan) -> PhysicalMutationResult:
        self.calls.append(f"ensure-link:{link.id}")
        return PhysicalMutationResult(
            target_id=link.id,
            target_kind=PhysicalObjectKind.LINK,
            disposition=MutationDisposition.CHANGED,
            applied=True,
            inverse_available=True,
            inverse_action_id=f"remove-link:{link.id}",
        )

    def observe_link(self, link: LinkPlan) -> PhysicalLinkObservation:
        self.calls.append(f"observe-link:{link.id}")
        return self.link_observations[link.id]


def test_verified_physical_deployment_produces_manifest_from_fresh_observations():
    topology = _topology()
    runtime = FakePhysicalRuntime()

    result = EnterprisePhysicalTopologyDeployer(runtime).deploy(
        topology,
        environment_fingerprint=_fingerprint(),
        deployment_id="deployment/live-reference",
    )

    assert result.status is PhysicalDeploymentStatus.VERIFIED
    assert result.manifest is not None
    assert result.manifest.physical_topology_hash == topology.physical_topology_hash
    assert result.manifest.environment_fingerprint == _fingerprint()
    assert result.manifest.binding_for("r1").runtime_identifier == "runtime-r1"
    assert result.manifest.binding_for("sw1").ports == [
        "FastEthernet0/1", "GigabitEthernet0/1",
    ]
    assert all(item.observed for item in result.item_results)
    assert all(item.verifies_claim for item in result.evidence_records)
    assert result.dirty_state is DirtyState.CLEAN
    assert runtime.calls == [
        "ensure-device:r1", "ensure-device:sw1",
        "observe-device:r1", "observe-device:sw1",
        "ensure-link:link/r1-sw1", "observe-link:link/r1-sw1",
    ]


@pytest.mark.parametrize(
    ("mutation", "failure_code"),
    [
        ("wrong_model", PhysicalDeploymentFailureCode.DEVICE_OBSERVATION_FAILED),
        ("missing_port", PhysicalDeploymentFailureCode.PORT_OBSERVATION_FAILED),
        ("missing_link", PhysicalDeploymentFailureCode.LINK_OBSERVATION_FAILED),
    ],
)
def test_missing_model_port_or_link_observation_blocks_manifest(mutation, failure_code):
    runtime = FakePhysicalRuntime()
    if mutation == "wrong_model":
        runtime.device_observations["r1"].model = "1841"
    elif mutation == "missing_port":
        runtime.device_observations["sw1"].interfaces = ["FastEthernet0/1"]
    else:
        runtime.link_observations["link/r1-sw1"].observed = False

    result = EnterprisePhysicalTopologyDeployer(runtime).deploy(
        _topology(), environment_fingerprint=_fingerprint(),
    )

    assert result.manifest is None
    assert result.status is PhysicalDeploymentStatus.PARTIAL
    assert result.failure_code is failure_code
    assert result.dirty_state is DirtyState.DIRTY_RECOVERABLE
    assert any(not item.verifies_claim for item in result.evidence_records)


def test_partial_application_failure_never_produces_manifest_and_marks_recoverable_dirty():
    runtime = FakePhysicalRuntime()
    runtime.fail_device = "sw1"

    result = EnterprisePhysicalTopologyDeployer(runtime).deploy(
        _topology(), environment_fingerprint=_fingerprint(),
    )

    assert result.status is PhysicalDeploymentStatus.PARTIAL
    assert result.failure_code is PhysicalDeploymentFailureCode.DEVICE_APPLICATION_FAILED
    assert result.manifest is None
    assert result.dirty_state is DirtyState.DIRTY_RECOVERABLE
    assert runtime.calls == ["ensure-device:r1", "ensure-device:sw1"]


def test_layout_transform_after_compilation_does_not_invalidate_physical_identity():
    topology = _topology()
    original_physical_hash = topology.physical_topology_hash
    transformed = deepcopy(topology)
    transformed.devices[0].x += 900
    transformed.devices[0].y += 450
    transformed.devices[1].x -= 300
    transformed.name = "Visual title changed"

    result = EnterprisePhysicalTopologyDeployer(FakePhysicalRuntime()).deploy(
        transformed, environment_fingerprint=_fingerprint(),
    )

    assert result.status is PhysicalDeploymentStatus.VERIFIED
    assert result.manifest is not None
    assert result.manifest.physical_topology_hash == original_physical_hash


def test_stale_or_missing_environment_identity_blocks_before_runtime_mutation():
    runtime = FakePhysicalRuntime()

    result = EnterprisePhysicalTopologyDeployer(runtime).deploy(
        _topology(),
        environment_fingerprint=EnvironmentFingerprint(
            backend="packet_tracer", backend_version="",
        ),
    )

    assert result.status is PhysicalDeploymentStatus.FAILED
    assert result.failure_code is PhysicalDeploymentFailureCode.ENVIRONMENT_FINGERPRINT_INVALID
    assert result.manifest is None
    assert result.dirty_state is DirtyState.CLEAN
    assert runtime.calls == []


def test_stale_physical_hash_blocks_before_runtime_mutation():
    topology = _topology()
    topology.devices[0].model = "1941"
    runtime = FakePhysicalRuntime()

    result = EnterprisePhysicalTopologyDeployer(runtime).deploy(
        topology, environment_fingerprint=_fingerprint(),
    )

    assert result.status is PhysicalDeploymentStatus.FAILED
    assert result.failure_code is PhysicalDeploymentFailureCode.PHYSICAL_HASH_MISMATCH
    assert result.manifest is None
    assert result.dirty_state is DirtyState.CLEAN
    assert runtime.calls == []


def test_crossed_semantic_id_and_deployed_name_blocks_before_mutation():
    topology = _topology()
    topology.devices.append(DevicePlan(
        id="sw2", name="HQ-SW2", model="2960-24TT", category="switch",
    ))
    topology.links[0].device_a = "HQ-SW2"
    stamp_topology_hashes(topology)
    runtime = FakePhysicalRuntime()

    result = EnterprisePhysicalTopologyDeployer(runtime).deploy(
        topology,
        environment_fingerprint=_fingerprint(),
    )

    assert result.manifest is None
    assert result.status is PhysicalDeploymentStatus.FAILED
    assert result.failure_code is PhysicalDeploymentFailureCode.INVALID_TOPOLOGY
    assert any("crosses semantic endpoint" in error for error in result.errors)
    assert runtime.calls == []


def test_unobservable_cable_identity_does_not_block_exact_endpoint_manifest():
    runtime = FakePhysicalRuntime()
    runtime.link_observations["link/r1-sw1"].cable_observed = False

    result = EnterprisePhysicalTopologyDeployer(runtime).deploy(
        _topology(), environment_fingerprint=_fingerprint(),
    )

    assert result.status is PhysicalDeploymentStatus.VERIFIED
    assert result.failure_code is PhysicalDeploymentFailureCode.NONE
    assert result.manifest is not None
    cable_evidence = next(
        item for item in result.evidence_records
        if item.id == "e4/link-cable/link/r1-sw1"
    )
    assert cable_evidence.observation_status is ObservationStatus.UNOBSERVABLE
    assert cable_evidence.verification_status is VerificationStatus.UNVERIFIED


def test_planned_module_without_independent_readback_blocks_manifest_before_mutation():
    topology = _topology()
    topology.modules = [
        ModulePlan(device="HQ-R1", slot="0/0", module="HWIC-2T"),
    ]
    stamp_topology_hashes(topology)
    runtime = FakePhysicalRuntime()

    result = EnterprisePhysicalTopologyDeployer(runtime).deploy(
        topology,
        environment_fingerprint=_fingerprint(),
    )

    assert result.manifest is None
    assert result.status is PhysicalDeploymentStatus.FAILED
    assert result.failure_code is PhysicalDeploymentFailureCode.MODULE_OBSERVATION_UNAVAILABLE
    assert runtime.calls == []


def test_planned_module_requires_exact_device_slot_and_model_readback():
    topology = _topology()
    topology.modules = [
        ModulePlan(device="HQ-R1", slot="0/0", module="HWIC-2T"),
    ]
    stamp_topology_hashes(topology)
    runtime = FakePhysicalRuntime()
    runtime.module_observation_supported = True

    result = EnterprisePhysicalTopologyDeployer(runtime).deploy(
        topology,
        environment_fingerprint=_fingerprint(),
    )

    assert result.status is PhysicalDeploymentStatus.VERIFIED
    assert result.manifest is not None
    module_item = next(
        item for item in result.item_results
        if item.target_kind is PhysicalObjectKind.MODULE
    )
    assert module_item.observed
    module_evidence = next(
        item for item in result.evidence_records
        if item.id == "e4/module-effect/HQ-R1:0/0:HWIC-2T"
    )
    assert module_evidence.verifies_claim
    identity_evidence = next(
        item for item in result.evidence_records
        if item.id == "e4/module-identity/HQ-R1:0/0:HWIC-2T"
    )
    assert identity_evidence.observation_status is ObservationStatus.UNOBSERVABLE
    assert identity_evidence.verification_status is VerificationStatus.UNVERIFIED
