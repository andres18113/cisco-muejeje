"""Borde Cisco de E8: SecurityAction tipada -> payload IOS confiable."""

from __future__ import annotations

import ipaddress

from pydantic import BaseModel

from ...domain.enterprise.models.security_plan import (
    AddSecurityAclRule,
    ApplyDeviceHardening,
    AttachSecurityAcl,
    ConfigureDhcpSnooping,
    ConfigureDynamicArpInspection,
    ConfigureEndpointPortSecurity,
    ConfigureSecurityNat,
    CreateSecurityAcl,
    NatMode,
    SecurityAction,
    SecurityDecision,
)
from ...domain.models.acls import ACLBinding, ACLEntry, ACLPlan
from ...domain.models.hardening import HardeningConfig
from ...domain.models.nat import NATConfig, NATPool, NATStaticMapping
from ...domain.models.switch_security import PortSecurityConfig
from .acl_cli_generator import (
    build_configure_payload,
    build_remove_payload,
)
from .hardening_cli_generator import build_hardening_payload
from .nat_cli_generator import generate_nat_body_cli, generate_nat_interface_cli
from .switch_security_cli_generator import build_port_security_payload


class RenderedSecurityMutation(BaseModel):
    action_id: str
    device_name: str
    ios_payload: str
    cleanup_payload: str


def _wrap(lines: list[str]) -> str:
    return "\n".join(["enable", "configure terminal", *lines, "end", "write memory"])


def _ios_address(cidr: str) -> str:
    network = ipaddress.ip_network(cidr, strict=False)
    if network.prefixlen == 0:
        return "any"
    if network.prefixlen == 32:
        return f"host {network.network_address}"
    wildcard = ipaddress.IPv4Address(int(network.hostmask))
    return f"{network.network_address} {wildcard}"


class PacketTracerSecurityRenderer:
    """Adapta acciones compiladas; no acepta fragmentos IOS del usuario."""

    def render_actions(
        self, actions: list[SecurityAction],
    ) -> list[RenderedSecurityMutation]:
        return [self.render_action(item) for item in sorted(actions, key=lambda value: value.id)]

    def render_action(self, action: SecurityAction) -> RenderedSecurityMutation:
        if isinstance(action, CreateSecurityAcl):
            raise ValueError(
                "CreateSecurityAcl is declarative only; compile concrete typed rules first."
            )
        if isinstance(action, AddSecurityAclRule):
            payload, cleanup = self._acl_rule(action)
        elif isinstance(action, AttachSecurityAcl):
            payload, cleanup = self._acl_attachment(action)
        elif isinstance(action, ConfigureSecurityNat):
            payload, cleanup = self._nat(action)
        elif isinstance(action, ConfigureEndpointPortSecurity):
            payload, cleanup = self._port_security(action)
        elif isinstance(action, ConfigureDhcpSnooping):
            payload, cleanup = self._dhcp_snooping(action)
        elif isinstance(action, ConfigureDynamicArpInspection):
            payload, cleanup = self._dai(action)
        elif isinstance(action, ApplyDeviceHardening):
            payload, cleanup = self._hardening(action)
        else:
            raise ValueError(f"No Packet Tracer security renderer for {type(action).__name__}.")
        return RenderedSecurityMutation(
            action_id=action.id,
            device_name=action.device_name,
            ios_payload=payload,
            cleanup_payload=cleanup,
        )

    @staticmethod
    def _acl_rule(action: AddSecurityAclRule) -> tuple[str, str]:
        protocols = ["udp", "tcp"] if action.protocol == "udp/tcp" else [action.protocol]
        source_ports = action.source_ports or [None]
        destination_ports = action.destination_ports or [None]
        entries: list[ACLEntry] = []
        for protocol in protocols:
            for source_port in source_ports:
                for destination_port in destination_ports:
                    entries.append(ACLEntry(
                        action=(
                            "permit" if action.decision is SecurityDecision.ALLOW else "deny"
                        ),
                        protocol=protocol,
                        source=_ios_address(action.source_cidr),
                        destination=_ios_address(action.destination_cidr),
                        source_port_op="eq" if source_port is not None else None,
                        source_port=source_port,
                        dest_port_op="eq" if destination_port is not None else None,
                        dest_port=destination_port,
                        log=action.logging,
                    ))
        plan = ACLPlan(
            router=action.device_name,
            name_or_number=action.acl_name,
            acl_type="extended",
            entries=entries,
        )
        return (
            build_configure_payload(plan),
            build_remove_payload(action.device_name, action.acl_name),
        )

    @staticmethod
    def _acl_attachment(action: AttachSecurityAcl) -> tuple[str, str]:
        plan = ACLPlan(
            router=action.device_name,
            name_or_number=action.acl_name,
            acl_type="extended",
        )
        binding = ACLBinding(
            router=action.device_name,
            interface=action.interface,
            acl_id=action.acl_name,
            direction=action.direction,
        )
        return (
            build_configure_payload(plan, binding),
            build_remove_payload(
                action.device_name,
                action.acl_name,
                action.interface,
                action.direction,
            ),
        )

    @staticmethod
    def _nat(action: ConfigureSecurityNat) -> tuple[str, str]:
        if not action.inside_interfaces:
            raise ValueError("PAT requires at least one compiled inside interface.")
        inside_networks = [_ios_address(item) for item in action.inside_networks]
        config = NATConfig(
            router=action.device_name,
            mode=action.mode.value,
            inside_interface=action.inside_interfaces[0],
            outside_interface=action.outside_interface,
            acl_number=str(action.translation_acl_number),
            inside_networks=inside_networks,
            static_mappings=[NATStaticMapping(
                inside_local=item.inside_local_address,
                inside_global=item.outside_global_address,
            ) for item in action.static_mappings],
            pool=(NATPool(
                name=action.dynamic_pool.name,
                start_ip=action.dynamic_pool.start_address,
                end_ip=action.dynamic_pool.end_address,
                netmask=action.dynamic_pool.netmask,
            ) if action.dynamic_pool else None),
            use_interface_overload=action.mode is NatMode.PAT,
        )
        body = generate_nat_interface_cli(config)
        for interface in action.inside_interfaces[1:]:
            body.extend([f"interface {interface}", " ip nat inside", " exit"])
        body.extend(generate_nat_body_cli(config))
        cleanup: list[str] = []
        for interface in action.inside_interfaces:
            cleanup.extend([f"interface {interface}", " no ip nat inside", " exit"])
        cleanup.extend([
            f"interface {action.outside_interface}",
            " no ip nat outside",
            " exit",
        ])
        if action.mode is NatMode.STATIC:
            cleanup.extend(
                f"no ip nat inside source static {item.inside_local_address} "
                f"{item.outside_global_address}"
                for item in action.static_mappings
            )
        elif action.mode is NatMode.DYNAMIC and action.dynamic_pool:
            cleanup.extend([
                f"no ip nat inside source list {action.translation_acl_number} "
                f"pool {action.dynamic_pool.name}",
                f"no ip nat pool {action.dynamic_pool.name}",
                f"no access-list {action.translation_acl_number}",
            ])
        else:
            cleanup.extend([
                f"no ip nat inside source list {action.translation_acl_number} "
                f"interface {action.outside_interface} overload",
                f"no access-list {action.translation_acl_number}",
            ])
        return _wrap(body), _wrap(cleanup)

    @staticmethod
    def _port_security(action: ConfigureEndpointPortSecurity) -> tuple[str, str]:
        config = PortSecurityConfig(
            switch=action.device_name,
            port=action.interface,
            max_mac=action.max_macs,
            violation=action.violation,
            sticky=action.sticky,
        )
        cleanup = [
            f"interface {action.interface}",
            " no switchport port-security",
            " exit",
        ]
        return build_port_security_payload(config), _wrap(cleanup)

    @staticmethod
    def _dhcp_snooping(action: ConfigureDhcpSnooping) -> tuple[str, str]:
        vlans = ",".join(str(item) for item in action.vlan_ids)
        body = ["ip dhcp snooping", f"ip dhcp snooping vlan {vlans}"]
        cleanup: list[str] = []
        for interface in action.trusted_interfaces:
            body.extend([f"interface {interface}", " ip dhcp snooping trust", " exit"])
            cleanup.extend([
                f"interface {interface}", " no ip dhcp snooping trust", " exit",
            ])
        cleanup.extend([f"no ip dhcp snooping vlan {vlans}", "no ip dhcp snooping"])
        return _wrap(body), _wrap(cleanup)

    @staticmethod
    def _dai(action: ConfigureDynamicArpInspection) -> tuple[str, str]:
        vlans = ",".join(str(item) for item in action.vlan_ids)
        body = [f"ip arp inspection vlan {vlans}"]
        cleanup: list[str] = []
        for interface in action.trusted_interfaces:
            body.extend([f"interface {interface}", " ip arp inspection trust", " exit"])
            cleanup.extend([
                f"interface {interface}", " no ip arp inspection trust", " exit",
            ])
        cleanup.append(f"no ip arp inspection vlan {vlans}")
        return _wrap(body), _wrap(cleanup)

    @staticmethod
    def _hardening(action: ApplyDeviceHardening) -> tuple[str, str]:
        config = HardeningConfig(
            device=action.device_name,
            banner_motd=action.banner_motd,
            service_password_encryption=action.service_password_encryption,
            console_login_local=False,
            vty_ssh_only=False,
        )
        cleanup: list[str] = []
        if action.banner_motd:
            cleanup.append("no banner motd")
        if action.service_password_encryption:
            cleanup.append("no service password-encryption")
        return build_hardening_payload(config), _wrap(cleanup)
