"""La politica de rendimiento de enlace tiene que llegar al CLI de verdad.

Stage 3A3-C encontro el pipeline partido en dos sitios: nadie construia las
acciones de rendimiento de enlace, y el renderer descartaba en silencio
cualquier accion que no reconociera. Lo segundo era lo peligroso, porque un
plan sin una sola linea de CLI se parece mucho a un plan correcto.

Aqui se prueba la cadena productiva y su modo de fallo:

    compile_enterprise_configuration
    -> ConfigurationCompiler (resolver de capacidades inyectado)
    -> acciones tipadas
    -> PacketTracerIosRenderer
    -> payload IOS
"""

from __future__ import annotations

import typing
from typing import Literal

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    BaseConfigurationAction,
    ConfigurationAction,
    ConfigurationPhase,
    ConfigureEthernetLinkMode,
    ConfigureInterfaceBandwidth,
    ConfigureSerialClock,
    CreateVlan,
)
from src.packet_tracer_mcp.infrastructure.generator.configuration_renderer import (
    PacketTracerIosRenderer,
    UnrenderableConfigurationAction,
    renderer_coverage,
)


def _common(**overrides):
    base = dict(
        id="a1", phase=ConfigurationPhase.L2_INTERFACES,
        device_id="d1", device_name="SW1", site_id="hq",
    )
    base.update(overrides)
    return base


class _UnregisteredAction(BaseConfigurationAction):
    """Una accion tipada que ningun renderer conoce."""

    action_type: Literal["unregistered_probe"] = "unregistered_probe"
    interface: str = "GigabitEthernet0/1"


class TestTheRendererFailsClosed:
    def test_an_action_without_a_renderer_raises_instead_of_vanishing(self):
        with pytest.raises(UnrenderableConfigurationAction):
            PacketTracerIosRenderer().render_device_batches(
                "SW1", "2960-24TT", [_UnregisteredAction(**_common())],
            )

    def test_the_failure_names_the_action_it_could_not_render(self):
        with pytest.raises(UnrenderableConfigurationAction) as caught:
            PacketTracerIosRenderer().render_device_batches(
                "SW1", "2960-24TT", [_UnregisteredAction(**_common(id="orphan-1"))],
            )

        assert "_UnregisteredAction" in str(caught.value)
        assert "orphan-1" in str(caught.value)

    def test_one_unknown_action_does_not_let_the_others_through(self):
        """Un lote a medio renderizar seria peor que ninguno."""
        actions = [
            CreateVlan(**_common(id="vlan-1", phase=ConfigurationPhase.L2_DEFINITIONS),
                       vlan_id=10, name="Ventas"),
            _UnregisteredAction(**_common(id="orphan-2")),
        ]

        with pytest.raises(UnrenderableConfigurationAction):
            PacketTracerIosRenderer().render_device_batches("SW1", "2960-24TT", actions)

    def test_known_actions_still_render(self):
        batches = PacketTracerIosRenderer().render_device_batches(
            "SW1", "2960-24TT",
            [CreateVlan(**_common(id="vlan-1", phase=ConfigurationPhase.L2_DEFINITIONS),
                        vlan_id=10, name="Ventas")],
        )

        assert batches and "vlan 10" in batches[0].ios_payload

    @pytest.mark.parametrize("action, expected", [
        (ConfigureSerialClock(**_common(), interface="Serial0/0/0",
                              clock_rate_bps=2_000_000), " clock rate 2000000"),
        (ConfigureInterfaceBandwidth(**_common(), interface="Serial0/0/0",
                                     bandwidth_kbps=2000), " bandwidth 2000"),
        (ConfigureEthernetLinkMode(**_common(), interface="GigabitEthernet0/1",
                                   speed="auto", duplex="full"), " duplex full"),
    ], ids=["serial_clock", "interface_bandwidth", "ethernet_link_mode"])
    def test_every_link_performance_action_reaches_the_cli(self, action, expected):
        batches = PacketTracerIosRenderer().render_device_batches(
            "R1", "2911", [action],
        )

        assert batches, "the action produced no batch at all"
        assert expected in batches[0].ios_payload

    def test_endpoint_actions_are_delegated_not_dropped(self):
        """Delegar es una decision; ignorar es un descuido, y se parecen."""
        coverage = renderer_coverage()

        assert coverage.delegated
        assert all(
            coverage.handles(action_type)
            for action_type in coverage.delegated
        )


class TestEveryActionInTheUnionHasSomewhereToGo:
    def test_no_action_type_is_left_without_a_renderer_or_a_delegate(self):
        """Detecta una accion nueva que nadie conecto: el fallo original."""
        union = typing.get_args(typing.get_args(ConfigurationAction)[0])
        coverage = renderer_coverage()

        orphans = [item.__name__ for item in union if not coverage.handles(item)]

        assert orphans == [], f"Action types with no renderer: {orphans}"

    def test_the_union_is_not_empty(self):
        assert typing.get_args(typing.get_args(ConfigurationAction)[0])


class TestTheCompilerReachesLinkPerformance:
    @pytest.fixture(scope="class")
    def reference(self):
        from tests.test_e95_reference_regression import _compile_reference_chain

        return _compile_reference_chain()

    def test_the_reference_still_compiles_after_the_wiring(self, reference):
        assert reference.e5.is_valid
        assert reference.e5.plan is not None

    def test_the_reference_emits_no_forced_link_mode(self, reference):
        """AUTO/AUTO es la politica de la referencia: nada que escribir."""
        emitted = [
            action for action in reference.e5.plan.actions
            if isinstance(action, ConfigureEthernetLinkMode)
        ]

        assert emitted == []

    def test_the_reference_emits_no_bandwidth_on_switchports(self, reference):
        """Medido: un switchport de 2960 rechaza `bandwidth`."""
        emitted = [
            action for action in reference.e5.plan.actions
            if isinstance(action, ConfigureInterfaceBandwidth)
        ]

        assert emitted == []

    def test_the_whole_reference_plan_renders_without_orphans(self, reference):
        """Si algo quedara sin renderer, esto ya no pasaria en silencio.

        Antes la cadena de referencia se importaba por `packet_tracer_mcp` y
        este modulo por `src.packet_tracer_mcp`: dos identidades del mismo
        codigo. Los tests se normalizaron a un solo namespace, asi que un
        `isinstance` contra la cadena vuelve a significar lo que dice.
        """
        from src.packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
            _IOS_ACTIONS,
        )
        from src.packet_tracer_mcp.infrastructure.generator.configuration_renderer import (
            PacketTracerIosRenderer as ReferenceRenderer,
        )

        ios_names = {item.__name__ for item in _IOS_ACTIONS}
        renderer = ReferenceRenderer()
        by_device = {device.name: device.model for device in reference.e4.plan.devices}

        for device in reference.e5.plan.devices:
            renderer.render_device_batches(
                device.device_name,
                by_device.get(device.device_name, ""),
                [
                    action for action in reference.e5.plan.actions
                    if action.device_name == device.device_name
                    and type(action).__name__ in ios_names
                ],
            )

    def test_the_runtime_routes_every_planned_action_somewhere(self, reference):
        """El descarte mudo estaba tambien aqui, una capa por debajo."""
        from src.packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
            _ENDPOINT_ACTIONS,
            _IOS_ACTIONS,
        )

        routed = {
            item.__name__ for item in (*_IOS_ACTIONS, *_ENDPOINT_ACTIONS)
        }
        unrouted = sorted({
            type(action).__name__
            for action in reference.e5.plan.actions
            if type(action).__name__ not in routed
        })

        assert unrouted == [], f"Planned actions no runtime channel handles: {unrouted}"

    def test_the_link_performance_actions_are_routed_by_the_runtime(self):
        from src.packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
            _IOS_ACTIONS,
        )

        for action_type in (ConfigureSerialClock, ConfigureInterfaceBandwidth,
                            ConfigureEthernetLinkMode):
            assert issubclass(action_type, _IOS_ACTIONS)


class TestUnknownProfileNeverMutates:
    """UNKNOWN no es UNSUPPORTED, y tampoco es permiso para mutar.

    Se compila la topologia de referencia real con un resolver que no conoce
    ningun modelo, que es exactamente el caso de un backend sin perfil medido.
    """

    @pytest.fixture(scope="class")
    def reference(self):
        from tests.test_e95_reference_regression import _compile_reference_chain

        return _compile_reference_chain()

    @staticmethod
    def _compile(reference, resolver):
        from src.packet_tracer_mcp.domain.enterprise.services.configuration_compiler import (
            ConfigurationCompiler,
        )

        return ConfigurationCompiler(
            link_mode_capability_resolver=resolver,
        ).compile(reference.enterprise, reference.e4.plan)

    @staticmethod
    def _link_mode_actions(result):
        names = {"ConfigureEthernetLinkMode", "ConfigureInterfaceBandwidth",
                 "ConfigureSerialClock"}
        return [
            action for action in (result.plan.actions if result.plan else [])
            if type(action).__name__ in names
        ]

    def test_an_unknown_profile_produces_zero_link_mode_mutations(self, reference):
        result = self._compile(reference, lambda model, interface: None)

        assert self._link_mode_actions(result) == []

    def test_the_unknown_profile_is_reported_as_unverified_not_unsupported(self, reference):
        result = self._compile(reference, lambda model, interface: None)
        codes = {issue.code.value for issue in result.issues}

        assert "CAPABILITY_UNVERIFIED" in codes
        assert not any("UNSUPPORTED" in code for code in codes)

    def test_the_plan_still_compiles_without_any_profile(self, reference):
        """Sin perfil se sigue compilando; solo no se muta."""
        result = self._compile(reference, lambda model, interface: None)

        assert result.is_valid and result.plan is not None

    def test_the_measured_reference_needs_no_unverified_warning(self, reference):
        """Contraste: no emitir acciones no prueba por si solo que falte el perfil."""
        from src.packet_tracer_mcp.infrastructure.catalog.link_mode_capabilities import (
            link_mode_capability_for,
        )

        result = self._compile(reference, link_mode_capability_for)
        unverified = [
            issue for issue in result.issues
            if issue.code.value == "CAPABILITY_UNVERIFIED"
            and "link-mode profile" in issue.message
        ]

        assert unverified == []
        assert self._link_mode_actions(result) == []


class TestTheUseCaseInjectsTheBackendProfiles:
    def test_the_productive_use_case_wires_the_catalog_resolver(self):
        """Sin esto el compilador nunca veria un perfil y no decidiria nada."""
        import inspect

        from src.packet_tracer_mcp.application.use_cases import compile_configuration

        source = inspect.getsource(compile_configuration.compile_enterprise_configuration)

        assert "link_mode_capability_resolver" in source
