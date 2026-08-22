"""Stage 3A4 Slice 2A: serial modules are proven by effect, not intent."""

from __future__ import annotations

from copy import deepcopy
import json
import shutil
import subprocess

import pytest

from src.packet_tracer_mcp.application.use_cases.deploy_enterprise_topology import (
    EnterprisePhysicalTopologyDeployer,
)
from src.packet_tracer_mcp.application.use_cases.qualify_serial_physical_slice import (
    SerialPhysicalSliceQualificationStatus,
    qualify_serial_physical_slice,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    DeploymentIdentityError,
    DeploymentLinkBinding,
    DeploymentLinkEndpoint,
    EnvironmentFingerprint,
    build_deployment_manifest,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.evidence import (
    EvidenceFreshness,
    ObservationStatus,
    SupportStatus,
    VerificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.execution import (
    MutationDisposition,
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
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceLinkObservation,
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from src.packet_tracer_mcp.domain.enterprise.services.topology_identity import (
    stamp_topology_hashes,
)
from src.packet_tracer_mcp.domain.models.plans import (
    DevicePlan,
    LinkPlan,
    ModulePlan,
    TopologyPlan,
)
from src.packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
)
from src.packet_tracer_mcp.infrastructure.generator.ptbuilder_generator import (
    generate_module_command,
    generate_ptbuilder_script,
)


SERIAL_PORTS = ["Serial0/0/0", "Serial0/0/1"]


def _topology() -> TopologyPlan:
    topology = TopologyPlan(
        id="stage-3a4/slice-2a",
        devices=[
            DevicePlan(id="r1", name="MCP-PROBE-S3A4-S2A-R1", model="2911", category="router"),
            DevicePlan(id="r2", name="MCP-PROBE-S3A4-S2A-R2", model="2911", category="router"),
        ],
        modules=[
            ModulePlan(device="MCP-PROBE-S3A4-S2A-R1", slot="0/0", module="HWIC-2T"),
            ModulePlan(device="MCP-PROBE-S3A4-S2A-R2", slot="0/0", module="HWIC-2T"),
        ],
        links=[
            LinkPlan(
                id="wan/r1-r2",
                device_a_id="r1",
                device_a="MCP-PROBE-S3A4-S2A-R1",
                port_a="Serial0/0/0",
                device_b_id="r2",
                device_b="MCP-PROBE-S3A4-S2A-R2",
                port_b="Serial0/0/0",
                cable="serial",
            ),
        ],
    )
    stamp_topology_hashes(topology)
    return topology


def _fingerprint() -> EnvironmentFingerprint:
    return EnvironmentFingerprint(
        backend="packet_tracer",
        backend_version="9.0.1.0858",
        bridge_transport="file",
        extension_version="5",
        runtime_mode="logical-workspace",
    )


class SerialEffectRuntime:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.operation_support = SupportStatus.SUPPORTED
        self.effect_support = SupportStatus.SUPPORTED
        self.observations = {
            name: self._module_observation(name)
            for name in ("MCP-PROBE-S3A4-S2A-R1", "MCP-PROBE-S3A4-S2A-R2")
        }
        self.workspace = PhysicalWorkspaceObservation(
            devices=[
                PhysicalWorkspaceDeviceObservation(
                    name="Power Distribution Device0",
                    model="Power Distribution Device",
                    backend_managed=True,
                ),
            ],
        )
        self.removed: list[str] = []

    @staticmethod
    def _module_id(module: ModulePlan) -> str:
        return f"{module.device}:{module.slot}:{module.module}"

    @staticmethod
    def _module_observation(name: str) -> PhysicalModuleObservation:
        return PhysicalModuleObservation(
            target_id=f"{name}:0/0:HWIC-2T",
            device_name=name,
            requested_slot="0/0",
            requested_module="HWIC-2T",
            freshness=EvidenceFreshness.FRESH,
            port_inventory_observed=True,
            expected_ports=SERIAL_PORTS,
            expected_port_classes=["serial"],
            ports_before=["GigabitEthernet0/0", "GigabitEthernet0/1"],
            ports_after=[
                "GigabitEthernet0/0", "GigabitEthernet0/1", *SERIAL_PORTS,
            ],
            observed_expected_ports=SERIAL_PORTS,
            added_ports=SERIAL_PORTS,
            observed_port_classes=["serial"],
            device_newly_owned=True,
            effect_observed=True,
            identity_observation_status=ObservationStatus.UNOBSERVABLE,
            observed_module_identity="",
            message="fresh module port-effect readback",
        )

    def module_effect_capability(
        self,
        module: ModulePlan,
        device: DevicePlan,
    ) -> PhysicalModuleEffectCapability:
        self.calls.append(f"capability:{self._module_id(module)}:{device.model}")
        return PhysicalModuleEffectCapability(
            target_id=self._module_id(module),
            operation_support=self.operation_support,
            effect_observation_support=self.effect_support,
            expected_ports=SERIAL_PORTS,
            expected_port_classes=["serial"],
            identity_observation_status=ObservationStatus.UNOBSERVABLE,
        )

    def observe_workspace(self) -> PhysicalWorkspaceObservation:
        self.calls.append("observe-workspace")
        return self.workspace

    def remove_device(self, device: DevicePlan) -> PhysicalMutationResult:
        self.calls.append(f"remove-device:{device.id}")
        self.removed.append(device.name)
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )

    def ensure_device(self, device: DevicePlan) -> PhysicalMutationResult:
        self.calls.append(f"ensure-device:{device.id}")
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )

    def ensure_module(self, module: ModulePlan) -> PhysicalMutationResult:
        target_id = self._module_id(module)
        self.calls.append(f"ensure-module:{target_id}")
        return PhysicalMutationResult(
            target_id=target_id,
            target_kind=PhysicalObjectKind.MODULE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )

    def observe_module_effect(self, module: ModulePlan) -> PhysicalModuleObservation:
        self.calls.append(f"observe-module-effect:{self._module_id(module)}")
        return self.observations[module.device]

    def observe_device(self, device: DevicePlan) -> PhysicalDeviceObservation:
        self.calls.append(f"observe-device:{device.id}")
        return PhysicalDeviceObservation(
            target_id=device.id,
            deployed_name=device.name,
            model=device.model,
            interfaces=["GigabitEthernet0/0", "GigabitEthernet0/1", *SERIAL_PORTS],
            runtime_fingerprint=f"fingerprint-{device.id}",
        )

    def ensure_link(self, link: LinkPlan) -> PhysicalMutationResult:
        self.calls.append(f"ensure-link:{link.id}")
        return PhysicalMutationResult(
            target_id=link.id,
            target_kind=PhysicalObjectKind.LINK,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )

    def observe_link(self, link: LinkPlan) -> PhysicalLinkObservation:
        self.calls.append(f"observe-link:{link.id}")
        return PhysicalLinkObservation(
            target_id=link.id,
            device_a=link.device_b,
            port_a=link.port_b,
            device_b=link.device_a,
            port_b=link.port_a,
            runtime_link_identifier="{slice-2a-link-uuid}",
            runtime_link_identity_observed=True,
            message="fresh exact two-ended readback",
        )


def _deploy(runtime: SerialEffectRuntime, *, require_empty_workspace: bool = False):
    return EnterprisePhysicalTopologyDeployer(runtime).deploy(
        _topology(),
        environment_fingerprint=_fingerprint(),
        deployment_id="deployment/stage-3a4-slice-2a",
        require_empty_workspace=require_empty_workspace,
    )


def test_unobservable_requested_identity_does_not_erase_verified_module_effect():
    result = _deploy(SerialEffectRuntime())

    assert result.status is PhysicalDeploymentStatus.VERIFIED
    assert result.manifest is not None
    assert all(
        item.observed
        for item in result.item_results
        if item.target_kind is PhysicalObjectKind.MODULE
    )

    effect_evidence = [
        item for item in result.evidence_records
        if item.id.startswith("e4/module-effect/")
    ]
    identity_evidence = [
        item for item in result.evidence_records
        if item.id.startswith("e4/module-identity/")
    ]
    assert len(effect_evidence) == 2
    assert all(item.verifies_claim for item in effect_evidence)
    assert len(identity_evidence) == 2
    assert all(
        item.observation_status is ObservationStatus.UNOBSERVABLE
        and item.verification_status is VerificationStatus.UNVERIFIED
        and not item.verifies_claim
        for item in identity_evidence
    )
    assert all(
        item.observed_value["requested_module"] == "HWIC-2T"
        and item.observed_value["observed_module_identity"] == ""
        for item in identity_evidence
    )

    placement_evidence = [
        item for item in result.evidence_records
        if item.id.startswith("e4/module-placement/")
    ]
    assert len(placement_evidence) == 2
    assert all(
        item.observation_status is ObservationStatus.UNOBSERVABLE
        and item.verification_status is VerificationStatus.UNVERIFIED
        and not item.verifies_claim
        and item.limitations
        for item in placement_evidence
    ), "un manifiesto callado sobre la ubicacion se leeria como si la afirmara"


def test_serial_manifest_binding_uses_fresh_two_ended_readback_and_runtime_identity():
    result = _deploy(SerialEffectRuntime())

    assert result.manifest is not None
    binding = result.manifest.link_binding_for("wan/r1-r2")
    assert binding.endpoint_for("r1").interface == "Serial0/0/0"
    assert binding.endpoint_for("r2").interface == "Serial0/0/0"
    assert binding.runtime_link_identifier == "{slice-2a-link-uuid}"
    assert binding.runtime_link_identity_observed
    assert result.manifest.compact_summary()["link_binding_count"] == 1


def test_manifest_refuses_observed_link_binding_on_wrong_existing_interfaces():
    topology = _topology()
    inventory = [
        RuntimeConfigurationTarget(
            device_name=device.name,
            model=device.model,
            interfaces=["Serial0/0/0", "Serial0/0/1"],
        )
        for device in topology.devices
    ]
    binding = DeploymentLinkBinding(
        semantic_link_id="wan/r1-r2",
        endpoint_a=DeploymentLinkEndpoint(
            semantic_device_id="r1",
            interface="Serial0/0/1",
        ),
        endpoint_b=DeploymentLinkEndpoint(
            semantic_device_id="r2",
            interface="Serial0/0/1",
        ),
    )

    with pytest.raises(DeploymentIdentityError, match="does not match the planned"):
        build_deployment_manifest(
            topology,
            inventory,
            fingerprint=_fingerprint(),
            link_bindings=[binding],
        )


@pytest.mark.parametrize("defect", ["no_effect", "partial", "wrong_slot", "stale"])
def test_incomplete_wrong_slot_or_stale_module_effect_never_produces_manifest(defect: str):
    runtime = SerialEffectRuntime()
    observation = deepcopy(runtime.observations["MCP-PROBE-S3A4-S2A-R1"])
    if defect == "no_effect":
        observation.ports_after = observation.ports_before
        observation.observed_expected_ports = []
        observation.added_ports = []
        observation.observed_port_classes = []
        observation.effect_observed = False
    elif defect == "partial":
        observation.ports_after = [*observation.ports_before, SERIAL_PORTS[0]]
        observation.observed_expected_ports = [SERIAL_PORTS[0]]
        observation.added_ports = [SERIAL_PORTS[0]]
        observation.effect_observed = False
    elif defect == "wrong_slot":
        wrong = ["Serial0/1/0", "Serial0/1/1"]
        observation.ports_after = [*observation.ports_before, *wrong]
        observation.observed_expected_ports = []
        observation.added_ports = wrong
        observation.effect_observed = False
    else:
        observation.freshness = EvidenceFreshness.STALE
    runtime.observations["MCP-PROBE-S3A4-S2A-R1"] = observation

    result = _deploy(runtime)

    assert result.manifest is None
    assert result.status is PhysicalDeploymentStatus.PARTIAL
    assert result.failure_code is PhysicalDeploymentFailureCode.MODULE_OBSERVATION_FAILED
    failed_effect = next(
        item for item in result.evidence_records
        if item.id == "e4/module-effect/MCP-PROBE-S3A4-S2A-R1:0/0:HWIC-2T"
    )
    assert not failed_effect.verifies_claim
    if defect == "stale":
        assert failed_effect.freshness is EvidenceFreshness.STALE
        assert failed_effect.verification_status is VerificationStatus.UNVERIFIED
    else:
        assert failed_effect.verification_status is VerificationStatus.FAILED


def test_explicitly_unsupported_module_operation_hard_stops_before_mutation():
    runtime = SerialEffectRuntime()
    runtime.operation_support = SupportStatus.UNSUPPORTED

    result = _deploy(runtime)

    assert result.status is PhysicalDeploymentStatus.FAILED
    assert result.manifest is None
    assert result.failure_code is PhysicalDeploymentFailureCode.MODULE_OBSERVATION_UNAVAILABLE
    assert all(call.startswith("capability:") for call in runtime.calls)
    support_evidence = [
        item for item in result.evidence_records
        if item.id.startswith("e4/module-capability/")
    ]
    assert support_evidence
    assert all(item.support_status is SupportStatus.UNSUPPORTED for item in support_evidence)


def test_unknown_module_capability_remains_unverified_and_stops_before_mutation():
    runtime = SerialEffectRuntime()
    runtime.operation_support = SupportStatus.UNKNOWN

    result = _deploy(runtime)

    assert result.failure_code is PhysicalDeploymentFailureCode.MODULE_OBSERVATION_UNAVAILABLE
    assert all(call.startswith("capability:") for call in runtime.calls)
    support_evidence = [
        item for item in result.evidence_records
        if item.id.startswith("e4/module-capability/")
    ]
    assert support_evidence
    assert all(
        item.support_status is SupportStatus.UNKNOWN
        and item.verification_status is VerificationStatus.UNVERIFIED
        for item in support_evidence
    )


def test_backend_managed_pdd_only_inventory_is_read_before_every_mutation():
    runtime = SerialEffectRuntime()

    result = _deploy(runtime, require_empty_workspace=True)

    assert result.status is PhysicalDeploymentStatus.VERIFIED
    assert runtime.calls[0] == "observe-workspace"
    workspace_evidence = next(
        item for item in result.evidence_records if item.id == "e4/workspace/pre-mutation"
    )
    assert workspace_evidence.verifies_claim
    assert workspace_evidence.observed_value["semantic_device_count"] == 0
    assert workspace_evidence.observed_value["backend_managed_device_count"] == 1


@pytest.mark.parametrize(
    "workspace",
    [
        PhysicalWorkspaceObservation(
            devices=[
                PhysicalWorkspaceDeviceObservation(
                    name="Student-R1",
                    model="2911",
                    ports=["GigabitEthernet0/0"],
                ),
            ],
        ),
        PhysicalWorkspaceObservation(
            links=[
                PhysicalWorkspaceLinkObservation(
                    class_name="Serial",
                    device_a="Student-R1",
                    port_a="Serial0/0/0",
                    device_b="Student-R2",
                    port_b="Serial0/0/0",
                ),
            ],
        ),
    ],
)
def test_user_or_graded_workspace_hard_stops_before_capability_or_mutation(
    workspace: PhysicalWorkspaceObservation,
):
    runtime = SerialEffectRuntime()
    runtime.workspace = workspace

    result = _deploy(runtime, require_empty_workspace=True)

    assert result.status is PhysicalDeploymentStatus.FAILED
    assert result.manifest is None
    assert result.failure_code is PhysicalDeploymentFailureCode.WORKSPACE_NOT_EMPTY
    assert runtime.calls == ["observe-workspace"]
    workspace_evidence = next(
        item for item in result.evidence_records if item.id == "e4/workspace/pre-mutation"
    )
    assert workspace_evidence.observation_status is ObservationStatus.OBSERVED
    assert workspace_evidence.verification_status is VerificationStatus.FAILED


def test_incomplete_workspace_inventory_hard_stops_as_unknown_not_empty_claim():
    runtime = SerialEffectRuntime()
    runtime.workspace = PhysicalWorkspaceObservation(
        observed=False,
        message="unreadable runtime link",
    )

    result = _deploy(runtime, require_empty_workspace=True)

    assert result.failure_code is PhysicalDeploymentFailureCode.WORKSPACE_OBSERVATION_FAILED
    assert runtime.calls == ["observe-workspace"]
    workspace_evidence = next(
        item for item in result.evidence_records if item.id == "e4/workspace/pre-mutation"
    )
    assert workspace_evidence.support_status is SupportStatus.UNKNOWN
    assert workspace_evidence.observation_status is ObservationStatus.PROBE_FAILED
    assert workspace_evidence.verification_status is VerificationStatus.UNVERIFIED


def test_workspace_restoration_preserves_semantics_and_preexisting_pdd_identity():
    baseline = PhysicalWorkspaceObservation(
        devices=[
            PhysicalWorkspaceDeviceObservation(
                name="Power Distribution Device0",
                model="Power Distribution Device",
                backend_managed=True,
            ),
        ],
    )
    restored = baseline.model_copy(deep=True)
    restored.devices.append(PhysicalWorkspaceDeviceObservation(
        name="Power Distribution Device1",
        model="Power Distribution Device",
        backend_managed=True,
    ))
    missing_preexisting = PhysicalWorkspaceObservation()

    assert physical_workspace_restoration_matches(baseline, restored)
    assert not physical_workspace_restoration_matches(baseline, missing_preexisting)
    duplicate_baseline = baseline.model_copy(deep=True)
    duplicate_baseline.devices.append(baseline.devices[0].model_copy(deep=True))
    assert not physical_workspace_restoration_matches(duplicate_baseline, baseline)


@pytest.mark.parametrize(
    ("payload", "observed", "safe"),
    [
        (
            {
                "items": [{
                    "kind": "device",
                    "name": "Power Distribution Device0",
                    "model": "Power Distribution Device",
                    "ports": [],
                }],
                "links": [],
            },
            True,
            True,
        ),
        (
            {
                "items": [{
                    "kind": "device",
                    "name": "Power Distribution Device0",
                    "model": "Power Distribution Device",
                    "ports": ["Port0"],
                }],
                "links": [],
            },
            True,
            False,
        ),
        (
            {
                "items": [],
                "links": [{"kind": "link", "index": 0, "unreadable": True}],
            },
            False,
            False,
        ),
    ],
)
def test_packet_tracer_workspace_inventory_is_strict_and_pdd_exception_is_exact(
    payload: dict[str, object],
    observed: bool,
    safe: bool,
):
    scripts: list[str] = []

    def transport(script: str, _timeout: float) -> str:
        scripts.append(script)
        return __import__("json").dumps(payload)

    inventory = PacketTracerPhysicalTopologyRuntime(transport).observe_workspace()

    assert inventory.observed is observed
    assert inventory.safe_for_disposable_mutation is safe
    assert len(scripts) == 1
    assert "getDeviceCount" in scripts[0]
    assert "addModule" not in scripts[0]
    assert "lwAddDevice" not in scripts[0]
    assert "removeDevice" not in scripts[0]


def test_packet_tracer_workspace_inventory_observes_one_ended_antenna_links():
    scripts: list[str] = []

    def transport(script: str, _timeout: float) -> str:
        scripts.append(script)
        if "__class==='Antenna'" not in script or ".getPort()" not in script:
            return __import__("json").dumps({
                "items": [],
                "links": [{"kind": "link", "index": 0, "unreadable": True}],
            })
        return __import__("json").dumps({
            "items": [],
            "links": [{
                "kind": "link",
                "class_name": "Antenna",
                "a_device": "AP1",
                "a_port": "Port 1",
                "b_device": "",
                "b_port": "",
            }],
        })

    inventory = PacketTracerPhysicalTopologyRuntime(transport).observe_workspace()

    assert inventory.observed
    assert len(inventory.links) == 1
    assert inventory.links[0].identity_key() == (
        "Antenna", (("", ""), ("AP1", "Port 1")),
    )
    assert not inventory.safe_for_disposable_mutation


def test_packet_tracer_workspace_inventory_rejects_one_ended_wired_links():
    payload = {
        "items": [],
        "links": [{
            "kind": "link",
            "class_name": "CopperStraightThrough",
            "a_device": "SW1",
            "a_port": "FastEthernet0/1",
            "b_device": "",
            "b_port": "",
        }],
    }

    inventory = PacketTracerPhysicalTopologyRuntime(
        lambda _script, _timeout: __import__("json").dumps(payload),
    ).observe_workspace()

    assert not inventory.observed
    assert inventory.message == "malformed_workspace_link"


class DeviceCleanupTransport:
    def __init__(self, *, model: str = "2911", mutation_reply: str | None = None) -> None:
        self.model = model
        self.mutation_reply = mutation_reply or '{"ack": true}'
        self.remove_mutations = 0

    def __call__(self, script: str, _timeout: float) -> str | None:
        if "removeDevice" in script:
            self.remove_mutations += 1
            return self.mutation_reply
        if "getPortCount" in script:
            return __import__("json").dumps({
                "found": True,
                "name": "MCP-PROBE-S3A4-S2A-R1",
                "model": self.model,
                "ports": ["GigabitEthernet0/0"],
            })
        raise AssertionError(f"unexpected script: {script}")


def test_packet_tracer_cleanup_deletes_only_exact_disposable_device_identity():
    transport = DeviceCleanupTransport()
    runtime = PacketTracerPhysicalTopologyRuntime(transport)

    mutation = runtime.remove_device(_device())

    assert mutation.disposition is MutationDisposition.CHANGED
    assert mutation.applied
    assert transport.remove_mutations == 1


def test_packet_tracer_cleanup_refuses_same_name_with_wrong_model():
    transport = DeviceCleanupTransport(model="3560-24PS")
    runtime = PacketTracerPhysicalTopologyRuntime(transport)

    mutation = runtime.remove_device(_device())

    assert mutation.disposition is MutationDisposition.FAILED
    assert "refusing" in mutation.message.casefold()
    assert transport.remove_mutations == 0


def test_disposable_qualification_always_cleans_exact_devices_and_restores_inventory():
    runtime = SerialEffectRuntime()
    baseline = runtime.workspace.model_copy(deep=True)
    observations = iter([
        baseline,
        PhysicalWorkspaceObservation(
            devices=[
                *baseline.devices,
                PhysicalWorkspaceDeviceObservation(
                    name="MCP-PROBE-S3A4-S2A-R1",
                    model="2911",
                ),
            ],
        ),
        baseline,
    ])

    def observe_workspace() -> PhysicalWorkspaceObservation:
        runtime.calls.append("observe-workspace")
        return next(observations)

    runtime.observe_workspace = observe_workspace  # type: ignore[method-assign]

    result = qualify_serial_physical_slice(
        runtime,
        _topology(),
        environment_fingerprint=_fingerprint(),
        deployment_id="deployment/stage-3a4-slice-2a",
        # Este test comprueba el camino de EXITO, no el vencimiento. Con 0.01 s
        # el deadline compite con las observaciones restantes y bajo carga de
        # suite completa llega a vencer antes de la tercera -- se observo fallar
        # asi una vez y pasar en aislamiento. Un presupuesto amplio no lo
        # debilita: el bucle corta en cuanto hay coincidencia, asi que el
        # timeout solo acota el camino de fallo. El vencimiento sigue cubierto
        # por los tests que pasan 0.0 y esperan False/None.
        restoration_timeout_seconds=5.0,
    )

    assert result.status is SerialPhysicalSliceQualificationStatus.VERIFIED_CLEAN
    assert result.deployment.status is PhysicalDeploymentStatus.VERIFIED
    assert result.inventory_restored is True
    assert runtime.removed == ["MCP-PROBE-S3A4-S2A-R2", "MCP-PROBE-S3A4-S2A-R1"]
    assert result.finished_at >= result.started_at


def test_disposable_qualification_cleanup_runs_when_deployment_fails_after_mutation():
    runtime = SerialEffectRuntime()
    broken = deepcopy(runtime.observations["MCP-PROBE-S3A4-S2A-R1"])
    broken.freshness = EvidenceFreshness.STALE
    runtime.observations["MCP-PROBE-S3A4-S2A-R1"] = broken
    baseline = runtime.workspace.model_copy(deep=True)
    runtime.observe_workspace = lambda: baseline  # type: ignore[method-assign]

    result = qualify_serial_physical_slice(
        runtime,
        _topology(),
        environment_fingerprint=_fingerprint(),
        restoration_timeout_seconds=0.01,
    )

    assert result.status is SerialPhysicalSliceQualificationStatus.FAILED_CLEAN
    assert result.deployment.manifest is None
    assert runtime.removed == ["MCP-PROBE-S3A4-S2A-R2", "MCP-PROBE-S3A4-S2A-R1"]
    assert result.inventory_restored is True


def test_cleanup_runs_after_a_module_port_effect_failure_and_spares_foreign_objects():
    """Filas 12 y 13 del contrato de TD-MODULE-SLOT-001, en su etapa propia.

    El modo de fallo elegido es el que la rama B agrega y la puerta anterior no
    veia: los puertos esperados YA estaban antes de la mutacion, asi que esta
    transaccion no puede afirmar haberlos causado. La limpieza tiene que correr
    igual, tocar exactamente los dispositivos planificados, y dejar intacto el
    objeto backend-managed que el workspace ya traia.
    """
    runtime = SerialEffectRuntime()
    not_caused = deepcopy(runtime.observations["MCP-PROBE-S3A4-S2A-R1"])
    not_caused.ports_before = list(not_caused.ports_after)
    runtime.observations["MCP-PROBE-S3A4-S2A-R1"] = not_caused
    baseline = runtime.workspace.model_copy(deep=True)
    runtime.observe_workspace = lambda: baseline  # type: ignore[method-assign]

    result = qualify_serial_physical_slice(
        runtime,
        _topology(),
        environment_fingerprint=_fingerprint(),
        restoration_timeout_seconds=0.01,
    )

    assert not_caused.effect_newly_caused is False
    assert not_caused.effect_verification_status is VerificationStatus.FAILED
    assert result.status is SerialPhysicalSliceQualificationStatus.FAILED_CLEAN
    assert result.deployment.manifest is None
    assert runtime.removed == ["MCP-PROBE-S3A4-S2A-R2", "MCP-PROBE-S3A4-S2A-R1"]
    assert "Power Distribution Device0" not in runtime.removed
    assert result.inventory_restored is True


def test_disposable_qualification_hard_stops_without_cleanup_on_foreign_workspace():
    runtime = SerialEffectRuntime()
    runtime.workspace = PhysicalWorkspaceObservation(devices=[
        PhysicalWorkspaceDeviceObservation(name="Graded-R1", model="2911"),
    ])

    result = qualify_serial_physical_slice(
        runtime,
        _topology(),
        environment_fingerprint=_fingerprint(),
    )

    assert result.status is SerialPhysicalSliceQualificationStatus.HARD_STOP
    assert result.deployment.failure_code is PhysicalDeploymentFailureCode.WORKSPACE_NOT_EMPTY
    assert runtime.removed == []
    assert all(call == "observe-workspace" for call in runtime.calls)


def test_disposable_qualification_cleanup_unknown_never_replays_and_marks_dirty():
    runtime = SerialEffectRuntime()
    baseline = runtime.workspace.model_copy(deep=True)
    runtime.observe_workspace = lambda: baseline  # type: ignore[method-assign]

    def unknown_remove(device: DevicePlan) -> PhysicalMutationResult:
        runtime.removed.append(device.name)
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.UNKNOWN,
        )

    runtime.remove_device = unknown_remove  # type: ignore[method-assign]

    result = qualify_serial_physical_slice(
        runtime,
        _topology(),
        environment_fingerprint=_fingerprint(),
        restoration_timeout_seconds=0.01,
    )

    assert result.status is SerialPhysicalSliceQualificationStatus.DIRTY_UNKNOWN
    assert runtime.removed == ["MCP-PROBE-S3A4-S2A-R2", "MCP-PROBE-S3A4-S2A-R1"]
    assert len(result.cleanup_results) == 2
    assert all(
        item.disposition is MutationDisposition.UNKNOWN
        for item in result.cleanup_results
    )


def test_unknown_device_creation_is_cleaned_once_but_remains_unknown():
    runtime = SerialEffectRuntime()
    baseline = runtime.workspace.model_copy(deep=True)
    runtime.observe_workspace = lambda: baseline  # type: ignore[method-assign]
    ensure_calls = 0

    def unknown_ensure(device: DevicePlan) -> PhysicalMutationResult:
        nonlocal ensure_calls
        ensure_calls += 1
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.UNKNOWN,
        )

    runtime.ensure_device = unknown_ensure  # type: ignore[method-assign]

    result = qualify_serial_physical_slice(
        runtime,
        _topology(),
        environment_fingerprint=_fingerprint(),
        restoration_timeout_seconds=0.01,
    )

    assert result.status is SerialPhysicalSliceQualificationStatus.UNKNOWN_CLEAN
    assert ensure_calls == 1
    assert runtime.removed == ["MCP-PROBE-S3A4-S2A-R1"]
    assert result.inventory_restored is True


def test_noop_device_race_is_never_deleted_and_final_inventory_is_dirty():
    runtime = SerialEffectRuntime()
    baseline = runtime.workspace.model_copy(deep=True)
    foreign = PhysicalWorkspaceObservation(devices=[
        PhysicalWorkspaceDeviceObservation(
            name="MCP-PROBE-S3A4-S2A-R1",
            model="2911",
        ),
    ])
    inventories = iter([baseline, foreign])
    runtime.observe_workspace = lambda: next(inventories)  # type: ignore[method-assign]
    runtime.ensure_device = lambda device: PhysicalMutationResult(  # type: ignore[method-assign]
        target_id=device.id,
        target_kind=PhysicalObjectKind.DEVICE,
        disposition=MutationDisposition.NO_OP,
    )

    result = qualify_serial_physical_slice(
        runtime,
        _topology(),
        environment_fingerprint=_fingerprint(),
        restoration_timeout_seconds=0.0,
    )

    assert result.status is SerialPhysicalSliceQualificationStatus.DIRTY_UNKNOWN
    assert runtime.removed == []
    assert result.inventory_restored is False
    assert result.deployment.failure_code is PhysicalDeploymentFailureCode.DEVICE_APPLICATION_FAILED


def test_exception_during_second_device_ensure_still_runs_cleanup_and_stays_unknown():
    runtime = SerialEffectRuntime()
    baseline = runtime.workspace.model_copy(deep=True)
    runtime.observe_workspace = lambda: baseline  # type: ignore[method-assign]
    calls = 0

    def ensure_then_raise(device: DevicePlan) -> PhysicalMutationResult:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("transport exploded")
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )

    runtime.ensure_device = ensure_then_raise  # type: ignore[method-assign]

    result = qualify_serial_physical_slice(
        runtime,
        _topology(),
        environment_fingerprint=_fingerprint(),
        restoration_timeout_seconds=0.01,
    )

    assert result.status is SerialPhysicalSliceQualificationStatus.UNKNOWN_CLEAN
    assert runtime.removed == ["MCP-PROBE-S3A4-S2A-R2", "MCP-PROBE-S3A4-S2A-R1"]


def test_incomplete_final_inventory_is_unknown_not_failed_restoration():
    runtime = SerialEffectRuntime()
    baseline = runtime.workspace.model_copy(deep=True)
    inventories = iter([
        baseline,
        PhysicalWorkspaceObservation(observed=False, message="readback timeout"),
    ])
    runtime.observe_workspace = lambda: next(inventories)  # type: ignore[method-assign]

    result = qualify_serial_physical_slice(
        runtime,
        _topology(),
        environment_fingerprint=_fingerprint(),
        restoration_timeout_seconds=0.0,
    )

    assert result.status is SerialPhysicalSliceQualificationStatus.DIRTY_UNKNOWN
    assert result.inventory_restored is None


def test_incomplete_pre_mutation_inventory_hard_stop_does_not_claim_restoration():
    runtime = SerialEffectRuntime()
    runtime.workspace = PhysicalWorkspaceObservation(
        observed=False,
        message="inventory unavailable",
    )

    result = qualify_serial_physical_slice(
        runtime,
        _topology(),
        environment_fingerprint=_fingerprint(),
    )

    assert result.status is SerialPhysicalSliceQualificationStatus.HARD_STOP
    assert result.inventory_restored is None
    assert runtime.removed == []


class ModuleEffectTransport:
    def __init__(self, *, ports: list[str] | None = None) -> None:
        self.ports = ports or ["GigabitEthernet0/0", "GigabitEthernet0/1"]
        self.calls: list[str] = []
        self.module_mutations = 0
        self.mutation_reply: str | None = (
            '{"ack":true,"changed":true,"outcome":"mutation_accepted",'
            '"identity_status":"unobservable"}'
        )

    def __call__(self, script: str, _timeout: float) -> str | None:
        self.calls.append(script)
        if "addModule(" in script:
            self.module_mutations += 1
            self.ports = sorted({*self.ports, *SERIAL_PORTS})
            return self.mutation_reply
        if "getRootModule" in script:
            return __import__("json").dumps({
                "found": True,
                "name": "MCP-PROBE-S3A4-S2A-R1",
                "model": "2911",
                "ports": self.ports,
                "modules_observed": True,
                "modules": [{
                    "observed_module_number": "0",
                    "slot_type_code": "18",
                    "port_count": 3 if set(SERIAL_PORTS) <= set(self.ports) else 0,
                    "observed_module_identity": "",
                    "identity_observable": False,
                }],
            })
        raise AssertionError(f"unexpected script: {script}")


def _module() -> ModulePlan:
    return ModulePlan(device="MCP-PROBE-S3A4-S2A-R1", slot="0/0", module="HWIC-2T")


def _device() -> DevicePlan:
    return DevicePlan(id="r1", name="MCP-PROBE-S3A4-S2A-R1", model="2911", category="router")


def _owned_runtime(transport: ModuleEffectTransport) -> PacketTracerPhysicalTopologyRuntime:
    runtime = PacketTracerPhysicalTopologyRuntime(transport)
    runtime._owned_new_devices.add(_module().device)
    return runtime


def test_packet_tracer_module_ensure_is_effect_idempotent_without_claiming_identity():
    transport = ModuleEffectTransport()
    runtime = _owned_runtime(transport)

    capability = runtime.module_effect_capability(_module(), _device())
    first = runtime.ensure_module(_module())
    first_observation = runtime.observe_module_effect(_module())
    second = runtime.ensure_module(_module())
    second_observation = runtime.observe_module_effect(_module())

    assert capability.operation_support is SupportStatus.SUPPORTED
    assert capability.effect_observation_support is SupportStatus.SUPPORTED
    assert capability.expected_ports == SERIAL_PORTS
    assert capability.identity_observation_status is ObservationStatus.UNOBSERVABLE
    assert first.disposition is MutationDisposition.CHANGED
    assert first.applied
    assert first_observation.effect_observed
    assert first_observation.added_ports == SERIAL_PORTS
    assert first_observation.identity_observation_status is ObservationStatus.UNOBSERVABLE
    assert first_observation.observed_module_identity == ""
    assert second.disposition is MutationDisposition.NO_OP
    assert second_observation.effect_observed
    assert second_observation.added_ports == []
    assert transport.module_mutations == 1


def test_expected_device_ports_without_module_tree_still_prove_the_port_effect():
    """Rama B de TD-MODULE-SLOT-001: el arbol de modulos no entra al veredicto.

    Este test antes exigia leer el arbol -- para correr sobre el una igualdad
    entre dos namespaces que nunca podia cumplirse. El efecto de puerto se
    prueba con el inventario de puertos antes/despues, que aqui esta completo,
    asi que exigir ademas el arbol seria pedir evidencia que nadie consulta. Lo
    que el arbol ausente deja UNOBSERVABLE es la UBICACION, y eso se afirma.
    """

    class NoModuleTreeTransport(ModuleEffectTransport):
        def __call__(self, script: str, timeout: float) -> str | None:
            raw = super().__call__(script, timeout)
            if "getRootModule" not in script or raw is None:
                return raw
            payload = __import__("json").loads(raw)
            payload["modules_observed"] = False
            payload["modules"] = []
            return __import__("json").dumps(payload)

    transport = NoModuleTreeTransport()
    runtime = _owned_runtime(transport)

    mutation = runtime.ensure_module(_module())
    observation = runtime.observe_module_effect(_module())

    assert mutation.disposition is MutationDisposition.CHANGED
    assert observation.effect_observed
    assert observation.module_tree_observed is False
    assert observation.effect_verification_status is VerificationStatus.VERIFIED
    assert observation.placement_observation_status is ObservationStatus.UNOBSERVABLE


def test_packet_tracer_module_ensure_fails_closed_on_partial_preexisting_effect():
    transport = ModuleEffectTransport(ports=[
        "GigabitEthernet0/0", "GigabitEthernet0/1", SERIAL_PORTS[0],
    ])
    runtime = _owned_runtime(transport)

    mutation = runtime.ensure_module(_module())

    assert mutation.disposition is MutationDisposition.FAILED
    assert "partial" in mutation.message.casefold()
    assert transport.module_mutations == 0


def test_packet_tracer_module_ensure_requires_owned_new_device_for_empty_slot():
    transport = ModuleEffectTransport()
    runtime = PacketTracerPhysicalTopologyRuntime(transport)

    mutation = runtime.ensure_module(_module())

    assert mutation.disposition is MutationDisposition.FAILED
    assert "emptiness" in mutation.message.casefold()
    assert transport.module_mutations == 0


def test_packet_tracer_module_ensure_rejects_foreign_same_slot_superset():
    transport = ModuleEffectTransport(ports=[
        "GigabitEthernet0/0", "GigabitEthernet0/1",
        *SERIAL_PORTS, "Serial0/0/2",
    ])
    runtime = _owned_runtime(transport)

    mutation = runtime.ensure_module(_module())

    assert mutation.disposition is MutationDisposition.FAILED
    assert "conflicting" in mutation.message.casefold()
    assert transport.module_mutations == 0


def test_packet_tracer_refuses_effect_claim_for_non_catalogued_slot_namespace():
    transport = ModuleEffectTransport()
    runtime = PacketTracerPhysicalTopologyRuntime(transport)
    module = ModulePlan(
        device="MCP-PROBE-S3A4-S2A-R1",
        slot="0/1",
        module="HWIC-2T",
    )

    capability = runtime.module_effect_capability(module, _device())
    mutation = runtime.ensure_module(module)

    assert capability.operation_support is SupportStatus.SUPPORTED
    assert capability.effect_observation_support is SupportStatus.UNSUPPORTED
    assert mutation.disposition is MutationDisposition.FAILED
    assert transport.module_mutations == 0
    assert transport.calls == []


def test_lost_module_ack_stays_unknown_and_is_never_replayed():
    transport = ModuleEffectTransport()
    transport.mutation_reply = None
    runtime = _owned_runtime(transport)

    first = runtime.ensure_module(_module())

    assert first.disposition is MutationDisposition.UNKNOWN
    assert not first.applied
    assert transport.module_mutations == 1


def test_module_renderer_serializes_every_caller_controlled_field():
    module = ModulePlan(
        device='R1";globalThis.pwned=true;//',
        slot='0/0";throw new Error("pwned")//',
        module='HWIC-2T";globalThis.pwned=true;//',
    )

    command = generate_module_command(module)

    assert __import__("json").dumps(module.device) in command
    assert __import__("json").dumps(module.slot) in command
    assert __import__("json").dumps(module.module) in command
    assert "globalThis.pwned=true" in command
    assert command.count("addModule(") == 1


# -- same-payload duplicate evaluation, measured in a real JS engine ---------
#
# El guard vive DENTRO del payload, asi que probarlo desde Python solo mediria
# el mock. Estas pruebas ejecutan el JS emitido en Node con un `addModule`
# instrumentado y cuentan invocaciones nativas reales.

_NATIVE_OUTCOMES = {
    # nombre -> (cuerpo JS de addModule, efecto que queda en el slot)
    "accepted": ('nativeCalls += 1; ports.push("Serial0/0/0", "Serial0/0/1"); '
                 'return true;', "complete"),
    "rejected": ('nativeCalls += 1; return false;', "absent"),
    "threw_without_effect": ('nativeCalls += 1; '
                             'throw new Error("ipc died mid-call");', "absent"),
    "threw_after_effect": ('nativeCalls += 1; '
                           'ports.push("Serial0/0/0", "Serial0/0/1"); '
                           'throw new Error("ipc died after mutating");', "complete"),
}


def _run_module_payload(tmp_path, evaluations: str, native_body: str, payloads: dict):
    """Evalua payloads de modulo en Node y devuelve el JSON observado."""
    harness = f"""
let ports = ["GigabitEthernet0/0", "GigabitEthernet0/1"];
let nativeCalls = 0;
global.GLOBAL = global;
const device = {{
  getPortCount: () => ports.length,
  getPortAt: (index) => ({{getName: () => ports[index]}})
}};
global.ipc = {{network: () => ({{getDevice: () => device}})}};
global.addModule = () => {{ {native_body} }};
const P = require(process.argv[2]);
function evaluate(source) {{
  try {{
    return (new Function(source + ';return __mcpModuleMutationReceipt;'))();
  }} catch (error) {{
    return {{ack:false, error:String(error)}};
  }}
}}
const out = {{}};
{evaluations}
out.nativeCalls = nativeCalls;
out.ports = ports;
out.storeSize = Object.keys(GLOBAL.__mcpModuleReceipts).length;
process.stdout.write(JSON.stringify(out));
"""
    script = tmp_path / "module_payload_harness.js"
    script.write_text(harness, encoding="utf-8")
    payload_file = tmp_path / "module_payloads.json"
    payload_file.write_text(json.dumps(payloads), encoding="utf-8")

    completed = subprocess.run(
        [shutil.which("node"), str(script), str(payload_file)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(completed.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is unavailable")
@pytest.mark.parametrize("outcome", sorted(_NATIVE_OUTCOMES))
def test_same_guarded_module_payload_never_invokes_native_add_twice(tmp_path, outcome):
    """Un mismo payload evaluado dos veces no puede insertar dos veces.

    Se cubren los tres post-estados que importan: insercion aceptada, rechazo
    nativo explicito, e incertidumbre por excepcion -- esta ultima tanto si el
    efecto alcanzo a quedar como si no. Lo que nunca puede pasar es que un
    intento se convierta en exito sin que una relectura fresca lo respalde.
    """
    native_body, effect = _NATIVE_OUTCOMES[outcome]
    command = generate_module_command(
        _module(), expected_ports=SERIAL_PORTS,
        operation_token="same-file-bridge-request", slot_empty_proven=True,
    )

    observed = _run_module_payload(
        tmp_path,
        "out.first = evaluate(P.original);\nout.second = evaluate(P.original);",
        native_body,
        {"original": command},
    )

    # La invariante central, identica en los cuatro post-estados.
    assert observed["nativeCalls"] == 1

    if effect == "complete":
        # El exito de la segunda evaluacion viene de releer el slot, no de
        # asumir que el intento previo funciono.
        assert observed["second"]["ack"] is True
        assert observed["second"]["replayed"] is True
        assert observed["second"]["outcome"] == "effect_present_after_prior_attempt"
        assert sorted(observed["ports"][-2:]) == sorted(SERIAL_PORTS)
    else:
        # Sin efecto no hay ascenso posible: el intento previo se mantiene
        # ambiguo y NO se degrada a NO_OP ni a exito.
        assert observed["first"]["ack"] is False
        assert observed["second"]["ack"] is False
        assert "already attempted" in observed["second"]["error"]

    if outcome == "rejected":
        assert "rejected module insertion" in observed["first"]["error"]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is unavailable")
def test_module_receipt_store_is_bounded_and_eviction_cannot_duplicate_an_effect(tmp_path):
    """El store global es acotado, y su desalojo no puede duplicar un efecto.

    Medido, no supuesto: el store se corta en 128 recibos, asi que no hay fuga
    de tokens. Tras desalojar el token original, la unica defensa que queda es
    la pre-lectura exacta del slot -- y basta, porque el efecto ya presente se
    reconoce sin invocar `addModule` otra vez.

    LIMITE CONOCIDO, declarado en vez de disimulado: si el intento previo NO
    dejo efecto (rechazo nativo), tras el desalojo un reenvio identico SI vuelve
    a invocar `addModule`. No promueve nada a exito -- el rechazo se repite --
    pero el recibo ya no lo contiene. El runtime tipado nunca reenvia
    (`ensure_module` falla cerrado ante REJECTED), asi que esto solo alcanzaria
    a un reenvio a nivel de transporte.
    """
    def command(token: str) -> str:
        return generate_module_command(
            _module(), expected_ports=SERIAL_PORTS,
            operation_token=token, slot_empty_proven=True,
        )

    payloads = {
        "original": command("tok-original"),
        "others": [command(f"tok-{index}") for index in range(130)],
    }
    evaluations = (
        "out.first = evaluate(P.original);\n"
        "for (const other of P.others) evaluate(other);\n"
        "const before = nativeCalls;\n"
        "out.afterEviction = evaluate(P.original);\n"
        "out.evictedDelta = nativeCalls - before;"
    )

    landed = _run_module_payload(
        tmp_path, evaluations, _NATIVE_OUTCOMES["accepted"][0], payloads,
    )
    absent = _run_module_payload(
        tmp_path, evaluations, _NATIVE_OUTCOMES["rejected"][0], payloads,
    )

    # Acotado: 130 operaciones extra no dejan 131 recibos vivos.
    assert landed["storeSize"] == 128
    assert absent["storeSize"] == 128

    # Efecto presente: el desalojo es irrelevante, la pre-lectura lo detiene.
    assert landed["evictedDelta"] == 0
    assert landed["afterEviction"]["ack"] is True
    assert landed["afterEviction"]["changed"] is False
    assert landed["afterEviction"]["outcome"] == "effect_already_present"

    # Efecto ausente: se repite el intento, pero jamas se promueve a exito.
    assert absent["evictedDelta"] == 1
    assert absent["afterEviction"]["ack"] is False


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is unavailable")
def test_guarded_module_payload_never_claims_exact_module_identity(tmp_path):
    """El efecto de puertos prueba efecto, nunca identidad HWIC/WIC exacta."""
    observed = _run_module_payload(
        tmp_path,
        "out.first = evaluate(P.original);\nout.second = evaluate(P.original);",
        _NATIVE_OUTCOMES["accepted"][0],
        {"original": generate_module_command(
            _module(), expected_ports=SERIAL_PORTS,
            operation_token="identity-check", slot_empty_proven=True,
        )},
    )

    for receipt in (observed["first"], observed["second"]):
        assert receipt["identity_status"] == "unobservable"
        assert "HWIC" not in json.dumps(receipt)


def test_batch_script_only_claims_slot_emptiness_for_devices_it_creates():
    """`slot_empty_proven` es una afirmacion, no un adorno del renderer.

    El script batch solo puede probar vacio de slot para un dispositivo que el
    mismo crea unas lineas antes. Sobre un dispositivo preexistente no tiene esa
    prueba, y el payload debe rechazar la insercion en vez de asumirla.
    """
    created = DevicePlan(id="r1", name="R-NEW", model="2911", category="router")
    plan = TopologyPlan(
        devices=[created],
        links=[],
        modules=[
            ModulePlan(device="R-NEW", slot="0/0", module="HWIC-2T"),
            ModulePlan(device="R-PREEXISTING", slot="0/0", module="HWIC-2T"),
        ],
    )

    script = generate_ptbuilder_script(plan)
    owned, foreign = [
        line for line in script.splitlines() if "__mcpModuleMutationReceipt" in line
    ]

    assert json.dumps("R-NEW") in owned
    assert "__emptyProven=true" in owned
    assert json.dumps("R-PREEXISTING") in foreign
    assert "__emptyProven=false" in foreign
