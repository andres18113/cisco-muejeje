"""Invariantes de integracion que ninguna capa suelta puede garantizar sola.

Cuatro cosas que se comprueban aqui porque solo se ven mirando el conjunto:

* el enrutado de acciones es una particion: cada tipo va a exactamente un
  canal, y ninguno se queda fuera;
* un lote con una accion desconocida se rechaza ENTERO, antes de tocar el
  primer dispositivo -- fallar a mitad deja la red en un estado que nadie
  pidio;
* `bandwidth` depende del tipo de interfaz, no del medio: un switchport nunca,
  un Gigabit enrutado si;
* produccion carga el paquete bajo una sola raiz de import.
"""

from __future__ import annotations

import ast
import pathlib
import typing
from typing import Literal

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    BaseConfigurationAction,
    ConfigurationAction,
    ConfigurationPhase,
    ConfigureInterfaceBandwidth,
    CreateVlan,
)
from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
    LinkMedia,
    LinkPerformanceDecision,
)
from src.packet_tracer_mcp.domain.enterprise.services.link_performance_integration import (
    LinkPerformanceIntegration,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    _ENDPOINT_ACTIONS,
    _IOS_ACTIONS,
    PacketTracerEnterpriseConfigurationRuntime,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = REPO / "src" / "packet_tracer_mcp"


def _action_union() -> tuple[type, ...]:
    return typing.get_args(typing.get_args(ConfigurationAction)[0])


class _UnroutableAction(BaseConfigurationAction):
    action_type: Literal["unroutable_probe"] = "unroutable_probe"
    interface: str = "GigabitEthernet0/1"


class TestActionRoutingIsAPartition:
    def test_the_two_channels_do_not_overlap(self):
        overlap = set(_IOS_ACTIONS) & set(_ENDPOINT_ACTIONS)

        assert overlap == set(), f"Action types claimed by both channels: {overlap}"

    def test_every_action_type_has_a_channel(self):
        orphans = set(_action_union()) - set(_IOS_ACTIONS) - set(_ENDPOINT_ACTIONS)

        assert orphans == set(), f"Action types with no channel: {orphans}"

    def test_no_channel_claims_a_type_outside_the_union(self):
        strays = (set(_IOS_ACTIONS) | set(_ENDPOINT_ACTIONS)) - set(_action_union())

        assert strays == set(), f"Routed types missing from the union: {strays}"

    def test_the_partition_covers_exactly_the_union(self):
        assert len(_IOS_ACTIONS) + len(_ENDPOINT_ACTIONS) == len(_action_union())


class _SpyRuntime:
    """Cuenta llamadas reales al bridge; el conteo es la prueba, no el mensaje."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def build(self) -> PacketTracerEnterpriseConfigurationRuntime:
        runtime = PacketTracerEnterpriseConfigurationRuntime(
            query_inventory=lambda: [
                {"name": "SW1", "model": "2960-24TT",
                 "interfaces": ["GigabitEthernet0/1", "FastEthernet0/1"]},
            ],
            send=self._send,
            send_and_wait=lambda js, timeout: None,
            ios_readiness=lambda device_name: True,
        )
        runtime.inventory()
        return runtime

    def _send(self, payload: str) -> bool:
        self.sent.append(payload)
        return True

    @property
    def configure_calls(self) -> list[str]:
        return [item for item in self.sent if "configureIosDevice" in item]

    @property
    def endpoint_calls(self) -> list[str]:
        return [item for item in self.sent if "configureIosDevice" not in item]


def _vlan(action_id: str = "vlan-1") -> CreateVlan:
    return CreateVlan(
        id=action_id, phase=ConfigurationPhase.L2_DEFINITIONS,
        device_id="d1", device_name="SW1", site_id="hq",
        vlan_id=10, name="Ventas",
    )


def _unroutable(action_id: str = "orphan-1") -> _UnroutableAction:
    return _UnroutableAction(
        id=action_id, phase=ConfigurationPhase.L2_INTERFACES,
        device_id="d1", device_name="SW1", site_id="hq",
    )


class TestAMixedBatchNeverMutatesPartially:
    def test_a_valid_action_alone_does_mutate(self):
        """Contraste imprescindible: si esto no mutara, el resto no probaria nada."""
        spy = _SpyRuntime()

        spy.build().apply_actions([_vlan()])

        assert len(spy.configure_calls) == 1

    def test_a_batch_with_an_unroutable_action_touches_nothing(self):
        spy = _SpyRuntime()

        results = spy.build().apply_actions([_vlan(), _unroutable()])

        assert spy.configure_calls == []
        assert spy.endpoint_calls == []
        assert all(not item.applied for item in results)

    def test_the_refusal_covers_every_action_in_the_batch(self):
        """El resultado no puede callar sobre las acciones que si eran validas."""
        spy = _SpyRuntime()

        results = spy.build().apply_actions([_vlan("v1"), _unroutable("o1")])

        assert {item.action_id for item in results} == {"v1", "o1"}

    def test_the_refusal_names_the_offending_type(self):
        spy = _SpyRuntime()

        results = spy.build().apply_actions([_vlan(), _unroutable()])

        assert any("_UnroutableAction" in item.message for item in results)

    def test_the_refusal_says_nothing_was_touched(self):
        spy = _SpyRuntime()

        results = spy.build().apply_actions([_vlan(), _unroutable()])

        assert all("before any device was touched" in item.message for item in results)


class TestBandwidthTargetFollowsTheInterfaceNotTheMedium:
    @staticmethod
    def _decision(media: LinkMedia) -> LinkPerformanceDecision:
        return LinkPerformanceDecision(
            link_id="l1", media=media, routing_bandwidth_kbps=2000,
        )

    def _emit(self, media: LinkMedia, *, routed: bool):
        return LinkPerformanceIntegration().actions_for(
            self._decision(media), device_id="d1", device_name="X",
            site_id="hq", interface="GigabitEthernet0/1",
            interface_is_routed=routed,
        )

    def test_an_ethernet_switchport_never_receives_bandwidth(self):
        """Medido: un switchport de 2960 responde "% Invalid input"."""
        emitted = self._emit(LinkMedia.ETHERNET, routed=False)

        assert not any(isinstance(item, ConfigureInterfaceBandwidth) for item in emitted)

    def test_a_routed_ethernet_interface_may_receive_bandwidth(self):
        """Prohibirlo en todo Ethernet era pasarse: un Gigabit enrutado lo acepta."""
        emitted = self._emit(LinkMedia.ETHERNET, routed=True)

        assert any(isinstance(item, ConfigureInterfaceBandwidth) for item in emitted)

    def test_serial_keeps_its_existing_semantics(self):
        for routed in (True, False):
            emitted = self._emit(LinkMedia.SERIAL, routed=routed)

            assert any(isinstance(item, ConfigureInterfaceBandwidth) for item in emitted)

    def test_the_seam_takes_interface_semantics_not_a_device_type(self):
        """El parametro es del puerto, no del dispositivo: eso es lo correcto."""
        import inspect

        signature = inspect.signature(LinkPerformanceIntegration.actions_for)

        assert "interface_is_routed" in signature.parameters
        assert "device_category" not in signature.parameters

    def test_the_compiler_derives_it_from_the_device_category(self):
        """DEUDA E9.5 acotada, y por eso INTERFACE_BANDWIDTH_TARGET_SAFETY = PARTIAL.

        El seam es correcto, pero quien lo alimenta usa `category == "router"`.
        Un puerto enrutado sobre un switch multicapa -- un 3560/3650 con `no
        switchport` o una SVI -- quedaria clasificado como conmutado y no
        recibiria `bandwidth` aunque lo aceptara.

        El error va en la direccion segura: se deja de emitir algo valido, no
        se emite algo que el backend rechace. Cerrarlo exige saber si el puerto
        esta enrutado, y esa evidencia es justo la que hoy no llega a la
        seleccion de hardware.
        """
        import inspect

        from src.packet_tracer_mcp.domain.enterprise.services import (
            configuration_compiler,
        )

        source = inspect.getsource(
            configuration_compiler.ConfigurationCompiler._link_performance_actions,
        )

        assert 'interface_is_routed=device.category == "router"' in source

    def test_no_routing_bandwidth_decided_means_no_action_anywhere(self):
        decision = LinkPerformanceDecision(link_id="l1", media=LinkMedia.SERIAL)

        emitted = LinkPerformanceIntegration().actions_for(
            decision, device_id="d1", device_name="X", site_id="hq",
            interface="Serial0/0/0", interface_is_routed=True,
        )

        assert not any(isinstance(item, ConfigureInterfaceBandwidth) for item in emitted)


class TestProductionHasOneImportRoot:
    """El harness cargo el paquete por dos rutas y roto `isinstance`.

    En produccion no puede pasar: si `src.` apareciera dentro de `src/`, dos
    modulos distintos representarian el mismo codigo y el enrutado por tipo
    dejaria de funcionar sin que nada fallara ruidosamente.
    """

    @staticmethod
    def _imported_roots(path: pathlib.Path) -> list[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        roots: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                roots.append(node.module.split(".")[0])
        return roots

    def test_no_production_module_imports_through_the_src_root(self):
        offenders = [
            path.relative_to(REPO).as_posix()
            for path in sorted(PACKAGE.rglob("*.py"))
            if "src" in self._imported_roots(path)
        ]

        assert offenders == [], f"Production modules importing via `src.`: {offenders}"

    def test_no_production_module_manipulates_sys_path(self):
        """Retocar sys.path es como aparecen las dobles identidades."""
        offenders = []
        for path in sorted(PACKAGE.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "sys.path" in text:
                offenders.append(path.relative_to(REPO).as_posix())

        assert offenders == [], f"Production modules touching sys.path: {offenders}"

    def test_production_dispatch_never_routes_by_type_name(self):
        """Comparar `type.__name__` taparia el problema en vez de resolverlo."""
        offenders = []
        for path in sorted(PACKAGE.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "type(action).__name__ ==" in text or "__name__ in _IOS" in text:
                offenders.append(path.relative_to(REPO).as_posix())

        assert offenders == [], f"Production dispatch by type name: {offenders}"
