"""Los negativos del manifest, contados en llamadas al bridge.

Los tests de `test_e95_manifest_application` ya cubren hash y fingerprint, pero
con un runtime falso que cuenta acciones. Aqui se atraviesa el runtime real
-- `PacketTracerEnterpriseConfigurationRuntime` -- y se cuentan las llamadas
que de verdad mutarian Packet Tracer. La diferencia importa: una accion puede
"no aplicarse" y aun asi haber tocado el dispositivo.

Se reutiliza la validacion existente; no se duplica ninguna comprobacion.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.apply_configuration import (
    ConfigurationApplicator,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    DeploymentIdentityError,
    DeploymentLinkBinding,
    DeploymentLinkEndpoint,
    EnvironmentFingerprint,
    SerialEndpointOrientation,
    build_deployment_manifest,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from test_configuration_application import _compiled, _supported_capabilities

FINGERPRINT = EnvironmentFingerprint(
    backend_version="9.0.1.0858", bridge_transport="file",
)


class _BridgeSpy:
    """Cuenta lo unico que importa: llamadas que tocarian el backend."""

    def __init__(self, topology, plan) -> None:
        self.sent: list[str] = []
        self._inventory = [
            RuntimeConfigurationTarget(
                device_name=device.name,
                model=device.model,
                interfaces=_interfaces_for(topology, plan, device.name),
            )
            for device in topology.devices
        ]

    @property
    def inventory_payload(self) -> list[RuntimeConfigurationTarget]:
        return list(self._inventory)

    @property
    def configure_calls(self) -> list[str]:
        return [item for item in self.sent if "configureIosDevice" in item]

    @property
    def endpoint_calls(self) -> list[str]:
        return [item for item in self.sent if "configureIosDevice" not in item]

    def runtime(self) -> PacketTracerEnterpriseConfigurationRuntime:
        return PacketTracerEnterpriseConfigurationRuntime(
            query_inventory=lambda: [
                {
                    "name": target.device_name,
                    "model": target.model,
                    "interfaces": list(target.interfaces),
                }
                for target in self._inventory
            ],
            send=self._send,
            send_and_wait=lambda js, timeout: None,
            ios_readiness=lambda device_name: True,
            # El spy no simula salida de `show`, asi que la verificacion
            # posterior no puede converger. Se acorta para que el proof mida
            # mutaciones y no espere a timeouts que ya sabemos que ocurren.
            vlan_timeout_seconds=0.01,
            endpoint_timeout_seconds=0.01,
            trunk_timeout_seconds=0.01,
            l3_timeout_seconds=0.01,
            convergence_interval_seconds=0.01,
        )

    def _send(self, payload: str) -> bool:
        self.sent.append(payload)
        return True


def _interfaces_for(topology, plan, device_name: str) -> list[str]:
    """Todo lo que el plan referencia en ese dispositivo, no solo sus enlaces."""
    ports = {
        port
        for link in topology.links
        for name, port in (
            (link.device_a, link.port_a), (link.device_b, link.port_b),
        )
        if name == device_name
    }
    for action in plan.actions:
        if action.device_name != device_name:
            continue
        for attribute in ("interface", "parent_interface"):
            value = getattr(action, attribute, "")
            if value:
                ports.add(value)
    return sorted(ports) or ["GigabitEthernet0/0"]


@pytest.fixture()
def scenario():
    topology, plan = _compiled()
    spy = _BridgeSpy(topology, plan)
    manifest = build_deployment_manifest(
        topology, spy.inventory_payload,
        fingerprint=FINGERPRINT, deployment_id="dep-proof",
    )
    return topology, plan, spy, manifest


def _apply(plan, spy, manifest, *, fingerprint=FINGERPRINT):
    return ConfigurationApplicator(spy.runtime()).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
        runtime_context=ConfigurationRuntimeContext(
            environment_fingerprint=fingerprint,
        ),
        deployment_manifest=manifest,
    )


class TestTheValidCaseActuallyReachesMutation:
    """Sin este contraste, los negativos no probarian nada."""

    def test_a_valid_manifest_lets_the_plan_reach_the_bridge(self, scenario):
        _topology, plan, spy, manifest = scenario

        _apply(plan, spy, manifest)

        assert spy.configure_calls, "the valid case never reached the bridge"

    def test_the_valid_case_passes_every_identity_preflight(self, scenario):
        """Llega a aplicar; lo que falle despues ya no es identidad."""
        _topology, plan, spy, manifest = scenario

        result = _apply(plan, spy, manifest)

        assert result.failure_code not in {
            ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH,
            ConfigurationFailureCode.INTERFACE_NOT_FOUND,
            ConfigurationFailureCode.TARGET_NOT_FOUND,
            ConfigurationFailureCode.ENVIRONMENT_FINGERPRINT_MISMATCH,
            ConfigurationFailureCode.DEPLOYMENT_MANIFEST_REQUIRED,
            ConfigurationFailureCode.SOURCE_TOPOLOGY_MISMATCH,
        }


class TestWrongIdentityNeverReachesTheBridge:
    def test_an_interface_the_runtime_does_not_expose_blocks_everything(self, scenario):
        topology, plan, spy, manifest = scenario
        # El runtime deja de exponer la interfaz que el plan necesita.
        for target in spy._inventory:
            target.interfaces = ["Loopback999"]

        result = _apply(plan, spy, manifest)

        assert result.failure_code is ConfigurationFailureCode.INTERFACE_NOT_FOUND
        assert spy.configure_calls == []
        assert spy.endpoint_calls == []

    def test_a_stale_environment_fingerprint_blocks_everything(self, scenario):
        _topology, plan, spy, manifest = scenario

        result = _apply(
            plan, spy, manifest,
            fingerprint=EnvironmentFingerprint(
                backend_version="8.0.0", bridge_transport="file",
            ),
        )

        assert result.failure_code is (
            ConfigurationFailureCode.ENVIRONMENT_FINGERPRINT_MISMATCH
        )
        assert spy.configure_calls == []
        assert spy.endpoint_calls == []

    def test_a_manifest_for_another_topology_blocks_everything(self, scenario):
        _topology, plan, spy, manifest = scenario
        manifest.physical_topology_hash = "0" * 64

        result = _apply(plan, spy, manifest)

        assert result.failure_code is ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
        assert spy.configure_calls == []
        assert spy.endpoint_calls == []

    def test_a_renamed_runtime_device_blocks_everything(self, scenario):
        """La identidad semantica manda; el nombre visible no la sustituye."""
        _topology, plan, spy, manifest = scenario
        for binding in manifest.bindings:
            binding.deployed_name = binding.deployed_name + "-GONE"

        result = _apply(plan, spy, manifest)

        assert result.failure_code is not ConfigurationFailureCode.NONE
        assert spy.configure_calls == []


class TestSerialClockNeverLandsOnTheWrongEnd:
    """El reloj es del DCE. Se resuelve antes de que exista mutacion alguna."""

    @staticmethod
    def _with_serial_link(manifest):
        manifest.link_bindings = [DeploymentLinkBinding(
            semantic_link_id="hq-br-wan",
            endpoint_a=DeploymentLinkEndpoint(
                semantic_device_id=manifest.bindings[0].semantic_device_id,
                interface="Serial0/0/0",
                orientation=SerialEndpointOrientation.DCE,
            ),
            endpoint_b=DeploymentLinkEndpoint(
                semantic_device_id=manifest.bindings[1].semantic_device_id,
                interface="Serial0/0/0",
                orientation=SerialEndpointOrientation.DTE,
            ),
            runtime_link_identifier="{proof}",
            runtime_link_identity_observed=True,
        )]
        return manifest

    def _inventory(self, spy):
        return [
            RuntimeConfigurationTarget(
                device_name=target.device_name, model=target.model,
                interfaces=[*target.interfaces, "Serial0/0/0", "Serial0/0/1"],
            )
            for target in spy.inventory_payload
        ]

    def test_the_dte_end_is_refused_before_any_bridge_call(self, scenario):
        _topology, _plan, spy, manifest = scenario
        manifest = self._with_serial_link(manifest)
        dte = manifest.bindings[1].semantic_device_id

        with pytest.raises(DeploymentIdentityError, match="clock belongs to the DCE"):
            manifest.resolve_serial_clock_target(
                "hq-br-wan", dte, self._inventory(spy),
            )

        assert spy.configure_calls == []

    def test_a_runtime_that_contradicts_the_binding_is_refused(self, scenario):
        _topology, _plan, spy, manifest = scenario
        manifest = self._with_serial_link(manifest)
        dce = manifest.bindings[0].semantic_device_id

        with pytest.raises(DeploymentIdentityError, match="refusing to swap"):
            manifest.resolve_serial_clock_target(
                "hq-br-wan", dce, self._inventory(spy),
                observed_orientation=SerialEndpointOrientation.DTE,
            )

        assert spy.configure_calls == []

    def test_the_wrong_interface_on_the_right_end_is_refused(self, scenario):
        """Existir en el dispositivo no prueba sostener este enlace."""
        _topology, _plan, spy, manifest = scenario
        manifest = self._with_serial_link(manifest)
        dce = manifest.bindings[0].semantic_device_id

        with pytest.raises(DeploymentIdentityError, match="was observed on"):
            manifest.resolve_serial_clock_target(
                "hq-br-wan", dce, self._inventory(spy),
                observed_orientation=SerialEndpointOrientation.DCE,
                observed_interface="Serial0/0/1",
            )

        assert spy.configure_calls == []

    def test_the_dce_end_does_resolve(self, scenario):
        _topology, _plan, spy, manifest = scenario
        manifest = self._with_serial_link(manifest)
        dce = manifest.bindings[0].semantic_device_id

        target, interface = manifest.resolve_serial_clock_target(
            "hq-br-wan", dce, self._inventory(spy),
            observed_orientation=SerialEndpointOrientation.DCE,
            observed_interface="Serial0/0/0",
        )

        assert interface == "Serial0/0/0"
        assert target.device_name


class TestPolicyVersionScope:
    """`POLICY_VERSION` versiona la decision, no el renderizado.

    Stage 3A3-E cambio a quien se le emite `bandwidth`, que es un paso
    posterior a la decision, y no la subio. Stage 3A3-G si cambio lo que el
    planner decide -- sincronizar bajo AUTO contra el techo negociable -- y
    por eso la subio a 5. La distincion es el contrato.
    """

    def test_the_decision_never_travels_into_the_configuration_plan(self):
        import typing

        from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
            ConfigurationAction,
        )

        union = typing.get_args(typing.get_args(ConfigurationAction)[0])
        carriers = [
            item.__name__ for item in union
            if "policy_version" in item.model_fields
        ]

        assert carriers == [], f"Actions carrying a policy version: {carriers}"

    def test_the_emitted_actions_do_not_depend_on_the_decision_version(self):
        from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
            LinkMedia,
            LinkPerformanceIntent,
        )
        from src.packet_tracer_mcp.domain.enterprise.services.link_performance_planner import (
            LinkPerformancePlanner,
        )

        intent = LinkPerformanceIntent(link_id="l1", media=LinkMedia.ETHERNET)
        default = LinkPerformancePlanner().plan(intent)
        relabelled = LinkPerformancePlanner(policy_version="99").plan(intent)

        assert default.policy_version != relabelled.policy_version
        assert default.effective_speed is relabelled.effective_speed
        assert default.routing_bandwidth_kbps == relabelled.routing_bandwidth_kbps

    def test_the_pinned_version_moved_with_the_planner_change(self):
        from src.packet_tracer_mcp.domain.enterprise.services.link_performance_planner import (
            LinkPerformancePlanner,
        )

        assert LinkPerformancePlanner.POLICY_VERSION == "5"
