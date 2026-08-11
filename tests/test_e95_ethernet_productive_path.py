"""El camino productivo de Ethernet, del LinkPlan al comando renderizado.

Verificado en vivo sobre PT 9.0.1.0858 con 2911 Gig0/0 <-> 3560-24PS Fa0/1, la
unica pareja cuyos DOS extremos tienen `speed 100` + `duplex full` con efecto
observado:

    AUTO/AUTO   -> ninguna accion emitida; el enlace queda arriba negociando,
                   con duplex_autonegotiated=True en ambos extremos
    100/FULL    -> `interface X` / ` speed 100` / ` duplex full` en ambos,
                   aceptado, y duplex_autonegotiated=False releido en ambos

El binding de enlace es el generico que cerro Serial. No hay manifest de
Ethernet.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigureEthernetLinkMode,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    DeploymentBinding,
    DeploymentIdentityError,
    DeploymentLinkBinding,
    DeploymentLinkEndpoint,
    DeploymentManifest,
    EnvironmentFingerprint,
    validate_manifest_environment,
)
from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
    DuplexMode,
    LinkSpeedMode,
)
from src.packet_tracer_mcp.domain.enterprise.services.link_performance_integration import (
    LinkPerformanceIntegration,
)
from src.packet_tracer_mcp.domain.models.plans import LinkPlan
from src.packet_tracer_mcp.infrastructure.catalog.link_mode_capabilities import (
    link_mode_capability_for,
)
from src.packet_tracer_mcp.infrastructure.generator.link_performance_renderer import (
    render_ethernet_link_mode,
)

SEM_R, SEM_SW, SEM_LINK = "hq-r1", "hq-sw1", "hq-access-uplink"
R_IF, S_IF = "GigabitEthernet0/0", "FastEthernet0/1"
RUNTIME_R, RUNTIME_SW = "HQ-R1-deployed", "HQ-SW1-deployed"
UUID = "{dd7ac7a9-528c-a177-14b2-f9ed6601500e}"
ENV = EnvironmentFingerprint(backend_version="9.0.1.0858", bridge_transport="file")
MODELS = {SEM_R: "2911", SEM_SW: "3560-24PS"}

INVENTORY = [
    RuntimeConfigurationTarget(
        device_name=RUNTIME_R, model="2911",
        interfaces=[R_IF, "GigabitEthernet0/1", "GigabitEthernet0/2"],
    ),
    RuntimeConfigurationTarget(
        device_name=RUNTIME_SW, model="3560-24PS",
        interfaces=[S_IF, "FastEthernet0/2", "GigabitEthernet0/1"],
    ),
]


def _plan() -> LinkPlan:
    return LinkPlan(
        id=SEM_LINK, device_a=SEM_R, port_a=R_IF, device_b=SEM_SW, port_b=S_IF,
        cable="straight", link_role="access_uplink",
    )


def _manifest(*, interface_a=R_IF) -> DeploymentManifest:
    return DeploymentManifest(
        deployment_id="dep-eth-1", physical_topology_hash="ph-eth",
        backend_version="9.0.1.0858", environment_fingerprint=ENV,
        bindings=[
            DeploymentBinding(
                semantic_device_id=SEM_R, deployed_name=RUNTIME_R, model="2911"),
            DeploymentBinding(
                semantic_device_id=SEM_SW, deployed_name=RUNTIME_SW, model="3560-24PS"),
        ],
        link_bindings=[DeploymentLinkBinding(
            semantic_link_id=SEM_LINK,
            endpoint_a=DeploymentLinkEndpoint(
                semantic_device_id=SEM_R, interface=interface_a),
            endpoint_b=DeploymentLinkEndpoint(
                semantic_device_id=SEM_SW, interface=S_IF),
            runtime_link_identifier=UUID, runtime_link_identity_observed=True,
        )],
    )


def _integration() -> LinkPerformanceIntegration:
    return LinkPerformanceIntegration(capability_resolver=link_mode_capability_for)


def _actions(decision):
    integration = _integration()
    emitted = []
    for device_id, interface in ((SEM_R, R_IF), (SEM_SW, S_IF)):
        emitted.extend(integration.actions_for(
            decision, device_id=device_id, device_name=device_id,
            site_id="hq", interface=interface,
        ))
    return emitted


class TestTheCapabilityResolverIsInjected:
    def test_without_a_resolver_no_endpoint_carries_a_profile(self):
        """El dominio no sabe resolver un modelo: se lo dan o no lo tiene."""
        intent = LinkPerformanceIntegration().intent_for_link(
            _plan(), endpoint_models=MODELS,
        )

        assert intent.local_port_capability is None
        assert intent.peer_port_capability is None

    def test_with_the_catalog_resolver_both_endpoints_resolve(self):
        intent = _integration().intent_for_link(_plan(), endpoint_models=MODELS)

        assert intent.local_port_capability.port_kind == "GigabitEthernet"
        assert intent.peer_port_capability.port_kind == "FastEthernet"

    def test_the_ports_come_from_the_link_plan_field_names(self):
        """`port_a`/`port_b`: con otro nombre el perfil quedaria siempre vacio."""
        intent = _integration().intent_for_link(_plan(), endpoint_models=MODELS)

        assert intent.local_port_capability.nominal_capacity_bps == 1_000_000_000
        assert intent.peer_port_capability.nominal_capacity_bps == 100_000_000


class TestAutoNegotiationEmitsNothing:
    def test_auto_auto_is_applicable(self):
        decision = _integration().decide(
            _integration().intent_for_link(_plan(), endpoint_models=MODELS),
        )

        assert decision.applicable
        assert decision.effective_speed is LinkSpeedMode.AUTO
        assert decision.effective_duplex is DuplexMode.AUTO

    def test_auto_auto_emits_no_action_at_all(self):
        decision = _integration().decide(
            _integration().intent_for_link(_plan(), endpoint_models=MODELS),
        )

        assert _actions(decision) == []

    def test_auto_auto_emits_no_routing_bandwidth(self):
        decision = _integration().decide(
            _integration().intent_for_link(_plan(), endpoint_models=MODELS),
        )

        assert decision.routing_bandwidth_kbps is None


class TestExplicitHundredFullReachesTheRenderer:
    def _decision(self):
        integration = _integration()
        return integration.decide(integration.intent_for_link(
            _plan(), endpoint_models=MODELS,
            requested_speed=LinkSpeedMode.SPEED_100M,
            requested_duplex=DuplexMode.FULL,
        ))

    def test_the_pair_is_applicable_because_both_ends_were_measured(self):
        assert self._decision().applicable

    def test_an_action_is_emitted_for_each_endpoint(self):
        emitted = _actions(self._decision())

        assert len(emitted) == 2
        assert all(isinstance(item, ConfigureEthernetLinkMode) for item in emitted)

    def test_a_speed_that_was_not_forced_is_never_written(self):
        """El enlace ya negocia 100 Mbps; escribir `speed` sugeriria un control
        que no existe. Medido: `speed 100` se acepta y no mueve nada."""
        decision = self._decision()
        emitted = _actions(decision)

        assert decision.speed_forced is False
        assert render_ethernet_link_mode(emitted[0]) == [
            f"interface {R_IF}", " duplex full",
        ]

    def test_the_renderer_emits_speed_before_duplex_when_it_is_forced(self):
        """El orden es el que se aplico en vivo y el backend acepto."""
        forced = ConfigureEthernetLinkMode(
            id="x", phase=ConfigurationPhase.L2_INTERFACES,
            device_id="d", device_name="d", site_id="hq",
            interface=R_IF, speed="100m", duplex="full",
        )

        assert render_ethernet_link_mode(forced) == [
            f"interface {R_IF}", " speed 100", " duplex full",
        ]

    def test_the_far_end_renders_against_its_own_interface(self):
        emitted = _actions(self._decision())

        assert render_ethernet_link_mode(emitted[1])[0] == f"interface {S_IF}"

    def test_the_decision_differs_from_autonegotiation(self):
        integration = _integration()
        auto = integration.decide(
            integration.intent_for_link(_plan(), endpoint_models=MODELS))

        assert self._decision().explain() != auto.explain()


class TestTheGenericLinkBindingIsReused:
    def test_both_endpoints_resolve_to_their_runtime_target(self):
        manifest = _manifest()

        target_a, interface_a = manifest.resolve_link_endpoint_target(
            SEM_LINK, SEM_R, INVENTORY, observed_interface=R_IF)
        target_b, interface_b = manifest.resolve_link_endpoint_target(
            SEM_LINK, SEM_SW, INVENTORY, observed_interface=S_IF)

        assert (target_a.device_name, interface_a) == (RUNTIME_R, R_IF)
        assert (target_b.device_name, interface_b) == (RUNTIME_SW, S_IF)

    def test_an_ethernet_endpoint_needs_no_serial_orientation(self):
        """El binding es del enlace; DCE/DTE solo le importa a un reloj."""
        target, _ = _manifest().resolve_link_endpoint_target(
            SEM_LINK, SEM_SW, INVENTORY)

        assert target.device_name == RUNTIME_SW

    def test_a_wrong_interface_is_refused(self):
        with pytest.raises(DeploymentIdentityError, match="was observed on"):
            _manifest().resolve_link_endpoint_target(
                SEM_LINK, SEM_SW, INVENTORY, observed_interface="FastEthernet0/2")

    def test_an_interface_absent_from_the_runtime_target_is_refused(self):
        with pytest.raises(DeploymentIdentityError, match="not present"):
            _manifest(interface_a="GigabitEthernet9/9").resolve_link_endpoint_target(
                SEM_LINK, SEM_R, INVENTORY)

    def test_a_device_outside_the_link_is_refused(self):
        with pytest.raises(DeploymentIdentityError, match="no endpoint"):
            _manifest().resolve_link_endpoint_target(SEM_LINK, "not-in-link", INVENTORY)

    def test_a_stale_environment_fingerprint_is_refused(self):
        with pytest.raises(DeploymentIdentityError, match="EnvironmentFingerprint"):
            validate_manifest_environment(
                _manifest(), EnvironmentFingerprint(backend_version="8.0.0"))

    def test_the_serial_path_still_goes_through_its_own_orientation_check(self):
        """Reutilizar el resolvedor no puede dejar pasar un reloj al DTE."""
        with pytest.raises(DeploymentIdentityError, match="clock belongs to the DCE"):
            _manifest().resolve_serial_clock_target(SEM_LINK, SEM_R, INVENTORY)


class TestRuntimeIdentityStaysOutOfTheDecision:
    def test_the_runtime_link_uuid_never_reaches_the_decision(self):
        integration = _integration()
        decision = integration.decide(
            integration.intent_for_link(_plan(), endpoint_models=MODELS))

        assert UUID not in str(decision.explain())

    def test_the_uuid_lives_only_in_the_manifest(self):
        binding = _manifest().link_binding_for(SEM_LINK)

        assert binding.runtime_link_identifier == UUID
        assert binding.runtime_link_identity_observed
