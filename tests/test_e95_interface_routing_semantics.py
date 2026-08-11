"""Enrutado o conmutado es propiedad de la interfaz, no del dispositivo.

Hasta 3A3-F el compilador decidia con `device.category == "router"`. Eso no
puede representar el caso que importa: un switch multicapa con Gi0/1 como
switchport y Gi0/2 como puerto enrutado es la misma caja y dos respuestas
distintas.

La verdad sale de lo que el plan ya declaro para cada interfaz -- semantica de
configuracion tipada -- y no de la categoria, ni del modelo, ni del nombre del
puerto.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigurationPolicy,
    ConfigureAccessPort,
    ConfigureInterfaceBandwidth,
    ConfigureRoutedInterface,
    ConfigureSubinterface,
    ConfigureTrunk,
)
from src.packet_tracer_mcp.domain.enterprise.models.enterprise_plan import EnterprisePlan
from src.packet_tracer_mcp.domain.enterprise.services.configuration_compiler import (
    ConfigurationCompiler,
    InterfaceRoutingSemantics,
    interface_is_routed,
    interface_routing_semantics,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan
from src.packet_tracer_mcp.infrastructure.catalog.link_mode_capabilities import (
    link_mode_capability_for,
)

SWITCH = "sw-1"
L2_PORT, L3_PORT = "GigabitEthernet0/1", "GigabitEthernet0/2"


def _base(**overrides):
    common = dict(
        id="a", phase=ConfigurationPhase.L2_INTERFACES,
        device_id=SWITCH, device_name="SW1", site_id="hq",
    )
    common.update(overrides)
    return common


def _access(interface: str, action_id: str = "acc") -> ConfigureAccessPort:
    return ConfigureAccessPort(
        **_base(id=action_id), interface=interface, data_vlan_id=10,
    )


def _trunk(interface: str, action_id: str = "trk") -> ConfigureTrunk:
    return ConfigureTrunk(
        **_base(id=action_id), interface=interface, allowed_vlans=[10, 20],
    )


def _routed(interface: str, action_id: str = "rtd") -> ConfigureRoutedInterface:
    return ConfigureRoutedInterface(
        **_base(id=action_id, phase=ConfigurationPhase.L3_INTERFACES),
        interface=interface, segment_id="wan", ipv4="10.0.0.1", prefix=30,
        netmask="255.255.255.252",
    )


def _subinterface(parent: str, action_id: str = "sub") -> ConfigureSubinterface:
    return ConfigureSubinterface(
        **_base(id=action_id, phase=ConfigurationPhase.L3_INTERFACES),
        parent_interface=parent, vlan_id=10, segment_id="data", ipv4="10.0.0.1",
        prefix=24, netmask="255.255.255.0", encapsulation="dot1Q",
    )


class TestTheClassifierReadsTheInterfaceNotTheBox:
    def test_a_routed_interface_is_routed(self):
        assert interface_is_routed([_routed(L3_PORT)], SWITCH, L3_PORT)

    def test_an_access_port_is_not(self):
        assert not interface_is_routed([_access(L2_PORT)], SWITCH, L2_PORT)

    def test_a_trunk_is_not(self):
        assert not interface_is_routed([_trunk(L2_PORT)], SWITCH, L2_PORT)

    def test_the_parent_of_a_subinterface_is_routed(self):
        """Router-on-a-stick: el fisico sostiene subinterfaces y es enrutado."""
        assert interface_is_routed([_subinterface(L3_PORT)], SWITCH, L3_PORT)

    def test_the_same_device_answers_differently_per_interface(self):
        """El caso que la categoria del dispositivo no podia representar."""
        actions = [_access(L2_PORT, "acc"), _routed(L3_PORT, "rtd")]

        assert not interface_is_routed(actions, SWITCH, L2_PORT)
        assert interface_is_routed(actions, SWITCH, L3_PORT)

    def test_an_unconfigured_interface_is_unknown_not_switched(self):
        """No es lo mismo "nadie la configuro" que "esta conmutada"."""
        assert interface_routing_semantics([], SWITCH, L3_PORT) is (
            InterfaceRoutingSemantics.UNKNOWN
        )
        assert not interface_is_routed([], SWITCH, L3_PORT)

    def test_another_device_with_the_same_interface_name_does_not_leak(self):
        actions = [_routed(L3_PORT)]

        assert not interface_is_routed(actions, "other-device", L3_PORT)

    def test_a_contradictory_plan_is_a_conflict_not_a_switchport(self):
        """Llamarlo conmutado esconderia un error de compilacion."""
        actions = [_access(L3_PORT, "acc"), _routed(L3_PORT, "rtd")]

        assert interface_routing_semantics(actions, SWITCH, L3_PORT) is (
            InterfaceRoutingSemantics.CONFLICT
        )
        assert not interface_is_routed(actions, SWITCH, L3_PORT)

    def test_the_four_states_are_distinguishable(self):
        routed = [_routed(L3_PORT)]
        switched = [_access(L2_PORT)]

        assert interface_routing_semantics(routed, SWITCH, L3_PORT) is (
            InterfaceRoutingSemantics.ROUTED
        )
        assert interface_routing_semantics(switched, SWITCH, L2_PORT) is (
            InterfaceRoutingSemantics.SWITCHED
        )


def _topology(model: str = "2960-24TT") -> TopologyPlan:
    """Un switch con dos puertos y un vecino, para compilar de verdad."""
    return TopologyPlan(
        id="t-routing", physical_identity_hash="h" * 64,
        devices=[
            DevicePlan(id=SWITCH, name="SW1", model=model, category="switch",
                       site_id="hq", enterprise_role="distribution_switch"),
            DevicePlan(id="peer-l2", name="SW2", model=model, category="switch",
                       site_id="hq", enterprise_role="access_switch"),
            DevicePlan(id="peer-l3", name="SW3", model=model, category="switch",
                       site_id="hq", enterprise_role="core_switch"),
        ],
        links=[
            LinkPlan(id="l2-link", device_a="SW1", port_a=L2_PORT,
                     device_b="SW2", port_b=L2_PORT, cable="cross",
                     link_role="access_uplink"),
            LinkPlan(id="l3-link", device_a="SW1", port_a=L3_PORT,
                     device_b="SW3", port_b=L3_PORT, cable="cross",
                     link_role="core_link"),
        ],
    )


def _emit_with(decision, *, routed: bool):
    """El clasificador se prueba con una decision construida, no forzando
    al producto a producir una que bajo AUTO no existe."""
    from src.packet_tracer_mcp.domain.enterprise.services.link_performance_integration import (
        LinkPerformanceIntegration,
    )

    return LinkPerformanceIntegration().actions_for(
        decision, device_id=SWITCH, device_name="SW1", site_id="hq",
        interface=L3_PORT if routed else L2_PORT, interface_is_routed=routed,
    )


def _ethernet_decision_with_bandwidth():
    from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
        LinkMedia,
        LinkPerformanceDecision,
    )

    return LinkPerformanceDecision(
        link_id="l1", media=LinkMedia.ETHERNET, routing_bandwidth_kbps=1_000_000,
    )


def _compiler_semantics(planned, interface: str):
    topology = _topology()
    return interface_routing_semantics(planned, SWITCH, interface)


class TestSameDeviceTwoInterfacesTwoAnswers:
    """El caso que la categoria del dispositivo no podia representar."""

    @pytest.fixture()
    def planned(self):
        return [_access(L2_PORT, "acc"), _routed(L3_PORT, "rtd")]

    def test_the_two_interfaces_classify_differently(self, planned):
        assert _compiler_semantics(planned, L2_PORT) is (
            InterfaceRoutingSemantics.SWITCHED
        )
        assert _compiler_semantics(planned, L3_PORT) is (
            InterfaceRoutingSemantics.ROUTED
        )

    def test_the_switchport_gets_no_bandwidth(self):
        """Caso A."""
        emitted = _emit_with(_ethernet_decision_with_bandwidth(), routed=False)

        assert not any(
            isinstance(item, ConfigureInterfaceBandwidth) for item in emitted
        )

    def test_the_routed_port_on_the_same_switch_does(self):
        """Caso B: misma decision, misma caja, otra interfaz."""
        emitted = _emit_with(_ethernet_decision_with_bandwidth(), routed=True)

        assert len([
            item for item in emitted
            if isinstance(item, ConfigureInterfaceBandwidth)
        ]) == 1

    def test_an_unknown_interface_gets_no_bandwidth(self, planned):
        """Caso C: sin semantica declarada no se emite, y sigue siendo UNKNOWN."""
        assert _compiler_semantics(planned, "GigabitEthernet0/9") is (
            InterfaceRoutingSemantics.UNKNOWN
        )
        assert not interface_is_routed(planned, SWITCH, "GigabitEthernet0/9")

    def test_a_conflicting_interface_is_reported_not_silently_switched(self):
        """Caso D: el compilador lo bloquea con una incidencia estructurada."""
        planned = [_access(L3_PORT, "acc"), _routed(L3_PORT, "rtd")]
        compiler = ConfigurationCompiler(
            link_mode_capability_resolver=link_mode_capability_for,
        )
        topology = _topology()
        issues = []
        emitted = compiler._link_performance_actions(
            topology, {device.id: device for device in topology.devices},
            topology.links,
            {device.name: device.id for device in topology.devices},
            ConfigurationPolicy(sync_routing_bandwidth=True),
            planned,
            issues,
        )

        assert any("routed and switched" in issue.message for issue in issues)
        assert emitted == []


class TestAutoNeverSynthesisesAnEffectiveCapacity:
    """Caso E, y la razon por la que 3A3-G se revierte."""

    @staticmethod
    def _auto_decision(sync: bool):
        from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
            LinkMedia,
            LinkPerformanceIntent,
        )
        from src.packet_tracer_mcp.domain.enterprise.services.link_performance_planner import (
            LinkPerformancePlanner,
        )

        local = link_mode_capability_for("2960-24TT", "GigabitEthernet0/1")
        return LinkPerformancePlanner().plan(LinkPerformanceIntent(
            link_id="l1", media=LinkMedia.ETHERNET,
            local_port_capability=local, peer_port_capability=local,
            sync_routing_bandwidth_to_effective_capacity=sync,
        ))

    def test_the_auto_ceiling_is_known(self):
        assert self._auto_decision(True).auto_negotiable_ceiling_bps == 1_000_000_000

    def test_the_effective_capacity_is_not(self):
        """Un techo con evidencia no es un resultado."""
        assert self._auto_decision(True).effective_capacity_bps is None

    def test_syncing_does_not_substitute_the_ceiling(self):
        assert self._auto_decision(True).routing_bandwidth_kbps is None

    def test_the_two_are_never_conflated(self):
        decision = self._auto_decision(True)

        assert decision.auto_negotiable_ceiling_bps != decision.effective_capacity_bps

    def test_without_syncing_nothing_changes_either(self):
        assert self._auto_decision(False).routing_bandwidth_kbps is None


class TestSerialSyncStillWorks:
    """Caso F: donde la capacidad efectiva SI se conoce, sincronizar funciona."""

    @staticmethod
    def _serial_decision(sync: bool):
        from src.packet_tracer_mcp.domain.enterprise.models.compilation import (
            ConcreteLinkRole,
        )
        from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
            LinkMedia,
            LinkPerformanceIntent,
        )
        from src.packet_tracer_mcp.domain.enterprise.services.link_performance_planner import (
            LinkPerformancePlanner,
        )

        return LinkPerformancePlanner().plan(LinkPerformanceIntent(
            link_id="wan", media=LinkMedia.SERIAL, role=ConcreteLinkRole.WAN_LINK,
            dce_endpoint_device_id="hq", dte_endpoint_device_id="br",
            sync_routing_bandwidth_to_effective_capacity=sync,
        ))

    def test_the_serial_effective_capacity_is_known_before_deploying(self):
        assert self._serial_decision(False).effective_capacity_bps == 2_000_000

    def test_syncing_produces_the_matching_routing_bandwidth(self):
        assert self._serial_decision(True).routing_bandwidth_kbps == 2000

    def test_without_syncing_no_routing_bandwidth_is_decided(self):
        assert self._serial_decision(False).routing_bandwidth_kbps is None

    def test_the_clock_is_untouched_either_way(self):
        for sync in (True, False):
            assert self._serial_decision(sync).serial_clock_rate_bps == 2_000_000


class TestTheReferenceIsUnchanged:
    @pytest.fixture(scope="class")
    def reference(self):
        from tests.test_e95_reference_regression import _compile_reference_chain

        return _compile_reference_chain()

    def test_the_reference_still_emits_no_bandwidth_anywhere(self, reference):
        """La politica sigue apagada por defecto; nada cambia en la referencia."""
        emitted = [
            action for action in reference.e5.plan.actions
            if type(action).__name__ == "ConfigureInterfaceBandwidth"
        ]

        assert emitted == []

    def test_the_reference_still_compiles(self, reference):
        assert reference.e5.is_valid and reference.e5.plan is not None

    def test_the_default_policy_keeps_the_sync_off(self):
        assert ConfigurationPolicy().sync_routing_bandwidth is False


class TestSerialIsUntouched:
    def test_serial_bandwidth_does_not_depend_on_the_interface_classifier(self):
        from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
            LinkMedia,
            LinkPerformanceDecision,
        )
        from src.packet_tracer_mcp.domain.enterprise.services.link_performance_integration import (
            LinkPerformanceIntegration,
        )

        decision = LinkPerformanceDecision(
            link_id="wan", media=LinkMedia.SERIAL, routing_bandwidth_kbps=2000,
        )

        for routed in (True, False):
            emitted = LinkPerformanceIntegration().actions_for(
                decision, device_id="r1", device_name="R1", site_id="hq",
                interface="Serial0/0/0", interface_is_routed=routed,
            )

            assert any(
                isinstance(item, ConfigureInterfaceBandwidth) for item in emitted
            )

    def test_the_serial_clock_still_only_reaches_the_dce(self):
        from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
            LinkMedia,
            LinkPerformanceDecision,
        )
        from src.packet_tracer_mcp.domain.enterprise.services.link_performance_integration import (
            LinkPerformanceIntegration,
        )

        decision = LinkPerformanceDecision(
            link_id="wan", media=LinkMedia.SERIAL,
            serial_clock_rate_bps=2_000_000, dce_endpoint_device_id="r1",
        )
        integration = LinkPerformanceIntegration()

        dce = integration.actions_for(
            decision, device_id="r1", device_name="R1", site_id="hq",
            interface="Serial0/0/0")
        dte = integration.actions_for(
            decision, device_id="r2", device_name="R2", site_id="br",
            interface="Serial0/0/0")

        assert len(dce) == 1
        assert dte == []


class TestBandwidthObservabilityIsNotDestroyed:
    """Escribir `bandwidth` apaga la autonegociacion del valor.

    Medido sobre un 2911: `bandwidth 5000` deja `isBandwidthAutoNegotiate()`
    en False. Y esa autonegociacion es la unica evidencia indirecta de la tasa
    negociada, asi que sincronizar bajo AUTO no solo afirmaria lo que no se
    sabe: dejaria de poder averiguarlo.
    """

    @staticmethod
    def _observed(autonegotiated: bool, kbps: int = 1_000_000):
        from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
            ObservedLinkPerformance,
        )

        return ObservedLinkPerformance.from_runtime(
            "l1",
            capability=link_mode_capability_for("2960-24TT", "GigabitEthernet0/1"),
            routing_bandwidth_kbps=kbps,
            bandwidth_autonegotiated=autonegotiated,
            line_protocol_up=True,
        )

    def test_a_platform_tracked_bandwidth_still_infers_capacity(self):
        from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
            BandwidthProvenance,
        )

        observed = self._observed(True)

        assert observed.bandwidth_provenance is BandwidthProvenance.PLATFORM_TRACKED
        assert observed.effective_capacity_bps == 1_000_000_000

    def test_an_explicitly_configured_bandwidth_is_not_a_capacity(self):
        from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
            BandwidthProvenance,
        )

        observed = self._observed(False, kbps=5_000)

        assert observed.bandwidth_provenance is (
            BandwidthProvenance.EXPLICITLY_CONFIGURED
        )
        assert observed.effective_capacity_bps is None

    def test_the_auto_plan_leaves_the_channel_intact(self):
        """Al no emitir bandwidth bajo AUTO, la observacion sigue disponible."""
        from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
            LinkMedia,
            LinkPerformanceIntent,
        )
        from src.packet_tracer_mcp.domain.enterprise.services.link_performance_integration import (
            LinkPerformanceIntegration,
        )

        local = link_mode_capability_for("2960-24TT", "GigabitEthernet0/1")
        integration = LinkPerformanceIntegration()
        decision = integration.decide(LinkPerformanceIntent(
            link_id="l1", media=LinkMedia.ETHERNET,
            local_port_capability=local, peer_port_capability=local,
            sync_routing_bandwidth_to_effective_capacity=True,
        ))
        emitted = integration.actions_for(
            decision, device_id=SWITCH, device_name="SW1", site_id="hq",
            interface=L3_PORT, interface_is_routed=True,
        )

        assert not any(
            isinstance(item, ConfigureInterfaceBandwidth) for item in emitted
        )
        assert self._observed(True).effective_capacity_bps == 1_000_000_000

    def test_the_verifier_still_catches_a_shortfall_after_an_auto_plan(self):
        from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
            LinkMedia,
            LinkPerformanceDecision,
        )
        from src.packet_tracer_mcp.domain.enterprise.services.link_performance_planner import (
            LinkPerformancePlanner,
        )

        issues = LinkPerformancePlanner.verify_observed_capacity(
            LinkPerformanceDecision(link_id="l1", media=LinkMedia.ETHERNET),
            self._observed(True),
            minimum_capacity_bps=10_000_000_000,
        )

        assert [item.code.value for item in issues] == [
            "link_capacity_below_requirement",
        ]
