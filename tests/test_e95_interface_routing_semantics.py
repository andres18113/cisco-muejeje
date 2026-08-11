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
    interface_is_routed,
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

    def test_an_unconfigured_interface_is_not_assumed_routed(self):
        assert not interface_is_routed([], SWITCH, L3_PORT)

    def test_another_device_with_the_same_interface_name_does_not_leak(self):
        actions = [_routed(L3_PORT)]

        assert not interface_is_routed(actions, "other-device", L3_PORT)

    def test_a_contradictory_plan_resolves_to_switched(self):
        """Ante un plan incoherente se elige lo que no emite nada."""
        actions = [_access(L3_PORT, "acc"), _routed(L3_PORT, "rtd")]

        assert not interface_is_routed(actions, SWITCH, L3_PORT)


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


def _bandwidth_actions(planned, device_id: str, interface: str):
    compiler = ConfigurationCompiler(
        link_mode_capability_resolver=link_mode_capability_for,
    )
    emitted = compiler._link_performance_actions(
        _topology(), {device.id: device for device in _topology().devices},
        _topology().links,
        {device.name: device.id for device in _topology().devices},
        ConfigurationPolicy(sync_routing_bandwidth=True),
        planned,
        [],
    )
    return [
        action for action in emitted
        if isinstance(action, ConfigureInterfaceBandwidth)
        and action.device_id == device_id and action.interface == interface
    ]


class TestSameDeviceTwoInterfacesTwoAnswers:
    """La regresion obligatoria: falla con `device.category == "router"`.

    Con la regla vieja SW1 es un switch, asi que sus DOS puertos quedaban
    clasificados como conmutados y ninguno recibia `bandwidth`. El puerto
    enrutado lo recibe ahora, y el switchport sigue sin recibirlo.
    """

    @pytest.fixture()
    def planned(self):
        return [_access(L2_PORT, "acc"), _routed(L3_PORT, "rtd")]

    def test_the_switchport_gets_no_bandwidth(self, planned):
        assert _bandwidth_actions(planned, SWITCH, L2_PORT) == []

    def test_the_routed_port_on_the_same_switch_does(self, planned):
        assert len(_bandwidth_actions(planned, SWITCH, L3_PORT)) == 1

    def test_the_emitted_bandwidth_carries_the_link_capacity(self, planned):
        [action] = _bandwidth_actions(planned, SWITCH, L3_PORT)

        assert action.bandwidth_kbps > 0

    def test_without_the_policy_neither_interface_gets_bandwidth(self, planned):
        """`sync_routing_bandwidth` apagado: no es un efecto secundario."""
        compiler = ConfigurationCompiler(
            link_mode_capability_resolver=link_mode_capability_for,
        )
        topology = _topology()
        emitted = compiler._link_performance_actions(
            topology, {device.id: device for device in topology.devices},
            topology.links,
            {device.name: device.id for device in topology.devices},
            ConfigurationPolicy(),
            planned,
            [],
        )

        assert [
            action for action in emitted
            if isinstance(action, ConfigureInterfaceBandwidth)
        ] == []


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
