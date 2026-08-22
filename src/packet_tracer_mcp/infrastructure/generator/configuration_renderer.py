"""Renderer Packet Tracer para acciones E5 tipadas y validadas."""

from __future__ import annotations

import ipaddress
from collections import defaultdict
from dataclasses import dataclass

from ...domain.enterprise.models.configuration import (
    ConfigurationAction,
    ConfigurationPhase,
    ConfigureAccessPort,
    ConfigureDhcpPool,
    ConfigureEthernetLinkMode,
    ConfigureHostname,
    ConfigureInterfaceBandwidth,
    ConfigureRoutedInterface,
    ConfigureSerialClock,
    ConfigureSubinterface,
    ConfigureSvi,
    ConfigureTrunk,
    CreateVlan,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
)
from ...domain.models.vlans import (
    AccessPortConfig,
    SubinterfaceConfig,
    TrunkConfig,
    VLANConfig,
)
from ...shared.ios_config import build_configure_ios_call
from ...shared.utils import safe_ios_identifier, validate_ios_interface_name
from .link_performance_renderer import render_link_performance
from .vlan_cli_generator import (
    generate_router_subinterface_cli,
    generate_switch_vlan_cli,
    switch_supports_encap,
)


class UnrenderableConfigurationAction(ValueError):
    """Una accion tipada llego aqui y nadie sabe convertirla.

    Es un error y no un caso silencioso: durante E9.5 las acciones de
    rendimiento de enlace no estaban en la lista y compilaban, validaban y no
    producian una sola linea de CLI. Nadie se entero porque no fallaba nada.
    """

    def __init__(self, actions: list[ConfigurationAction]) -> None:
        self.actions = list(actions)
        detail = ", ".join(
            f"{type(action).__name__}({action.id})" for action in self.actions
        )
        super().__init__(
            "No renderer is registered for these configuration actions: " + detail
        )


# Acciones que este renderer convierte a CLI. La tupla es la definicion
# operativa de "renderizable".
_RENDERABLE = (
    ConfigureHostname, CreateVlan, ConfigureAccessPort, ConfigureTrunk,
    ConfigureRoutedInterface,
    ConfigureSvi, ConfigureSubinterface, ConfigureDhcpPool,
    ConfigureSerialClock, ConfigureInterfaceBandwidth, ConfigureEthernetLinkMode,
)

# Acciones que legitimamente pertenecen a otro renderer. Se enumeran a
# proposito: delegar es una decision, ignorar es un descuido, y desde fuera se
# parecen demasiado.
_DELEGATED = (
    SetEndpointStaticAddress, SetEndpointDhcp,
)


@dataclass(frozen=True)
class RendererCoverage:
    """Que sabe hacer este renderer, para poder auditarlo desde fuera."""

    rendered: tuple[type, ...]
    delegated: tuple[type, ...]

    def handles(self, action_type: type) -> bool:
        return issubclass(action_type, self.rendered) or issubclass(
            action_type, self.delegated,
        )


def renderer_coverage() -> RendererCoverage:
    return RendererCoverage(rendered=_RENDERABLE, delegated=_DELEGATED)


@dataclass(frozen=True)
class RenderedConfigurationBatch:
    device_name: str
    phase: ConfigurationPhase
    action_ids: list[str]
    ios_payload: str
    js_call: str


class PacketTracerIosRenderer:
    """Convierte sólo acciones cerradas; nunca acepta líneas IOS arbitrarias."""

    def render_device_batches(
        self,
        device_name: str,
        model: str,
        actions: list[ConfigurationAction],
    ) -> list[RenderedConfigurationBatch]:
        grouped: dict[ConfigurationPhase, list[ConfigurationAction]] = defaultdict(list)
        unhandled: list[ConfigurationAction] = []
        for action in actions:
            if isinstance(action, _RENDERABLE):
                grouped[action.phase].append(action)
            elif not isinstance(action, _DELEGATED):
                unhandled.append(action)
        if unhandled:
            # Fallar aqui es el punto: producir un plan vacio para una accion
            # que nadie sabe renderizar parece exito y no lo es.
            raise UnrenderableConfigurationAction(unhandled)

        batches: list[RenderedConfigurationBatch] = []
        for phase in sorted(grouped):
            phase_actions = sorted(grouped[phase], key=lambda item: item.id)
            body = self._render_body(model, phase_actions)
            if not body:
                continue
            payload = self._wrap(body)
            batches.append(RenderedConfigurationBatch(
                device_name=device_name,
                phase=phase,
                action_ids=[action.id for action in phase_actions],
                ios_payload=payload,
                js_call=build_configure_ios_call(device_name, payload),
            ))
        return batches

    def _render_body(self, model: str, actions: list[ConfigurationAction]) -> list[str]:
        lines: list[str] = []
        for action in actions:
            if isinstance(action, ConfigureHostname):
                hostname = safe_ios_identifier(action.hostname, max_length=63)
                if hostname != action.hostname:
                    raise ValueError(
                        f"Semantic hostname {action.hostname!r} is not an exact IOS hostname."
                    )
                lines.append(f"hostname {hostname}")

        vlans = [
            VLANConfig(vlan_id=action.vlan_id, name=action.name)
            for action in actions if isinstance(action, CreateVlan)
        ]
        access = [
            AccessPortConfig(
                switch=action.device_name,
                port=action.interface,
                vlan_id=action.data_vlan_id,
                voice_vlan_id=action.voice_vlan_id,
            )
            for action in actions if isinstance(action, ConfigureAccessPort)
        ]
        trunks = [
            TrunkConfig(
                switch=action.device_name,
                port=action.interface,
                allowed_vlans=action.allowed_vlans,
                native_vlan=action.native_vlan_id or 1,
            )
            for action in actions if isinstance(action, ConfigureTrunk)
        ]
        lines.extend(generate_switch_vlan_cli(
            vlans, access, trunks, supports_encap=switch_supports_encap(model),
        ))

        subinterfaces = [
            SubinterfaceConfig(
                router=action.device_name,
                parent_port=action.parent_interface,
                vlan_id=action.vlan_id,
                ip_cidr=f"{action.ipv4}/{action.prefix}",
                encapsulation=action.encapsulation,
            )
            for action in actions if isinstance(action, ConfigureSubinterface)
        ]
        lines.extend(generate_router_subinterface_cli(subinterfaces))

        for action in actions:
            if isinstance(action, (ConfigureSerialClock, ConfigureInterfaceBandwidth,
                                   ConfigureEthernetLinkMode)):
                # El CLI de rendimiento de enlace se construye en un solo sitio;
                # aqui sólo se despacha y se cierra el bloque de interfaz.
                rendered = render_link_performance(action)
                if rendered:
                    lines.extend([*rendered, " exit"])
            elif isinstance(action, ConfigureRoutedInterface):
                interface = validate_ios_interface_name(action.interface)
                address = str(ipaddress.ip_address(action.ipv4))
                lines.extend([
                    f"interface {interface}",
                    f" ip address {address} {action.netmask}",
                    " no shutdown" if action.administrative_up else " shutdown",
                    " exit",
                ])
            elif isinstance(action, ConfigureSvi):
                address = str(ipaddress.ip_address(action.ipv4))
                lines.extend([
                    f"interface Vlan{action.vlan_id}",
                    f" ip address {address} {action.netmask}",
                    " no shutdown" if action.administrative_up else " shutdown",
                    " exit",
                ])
            elif isinstance(action, ConfigureDhcpPool):
                pool_name = safe_ios_identifier(action.pool_name)
                for excluded in action.excluded_ranges:
                    start = str(ipaddress.ip_address(excluded.start))
                    end = str(ipaddress.ip_address(excluded.end))
                    line = f"ip dhcp excluded-address {start}"
                    if end != start:
                        line += f" {end}"
                    lines.append(line)
                lines.extend([
                    f"ip dhcp pool {pool_name}",
                    f" network {action.network} {action.netmask}",
                    f" default-router {action.gateway}",
                ])
                if action.dns_server:
                    lines.append(f" dns-server {ipaddress.ip_address(action.dns_server)}")
                lines.append(" exit")
        return lines

    @staticmethod
    def _wrap(lines: list[str]) -> str:
        return "\n".join(["enable", "configure terminal", *lines, "end", "write memory"])
