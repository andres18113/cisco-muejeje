"""Borde Cisco cerrado de E9: acciones de control plane tipadas a IOS."""

from __future__ import annotations

import ipaddress
import re

from pydantic import BaseModel

from ...domain.enterprise.models.control_plane import (
    BaseControlPlaneAction,
    ConfigureEigrpIpv4,
    ConfigureEtherChannel,
    ConfigureHsrp,
    ConfigureOspfv2,
    ConfigureRipv2,
    ConfigureSpanningTree,
    ConfigureStpEdgePort,
    ControlPlaneAction,
    ControlPlaneCapabilityDimension,
    EtherChannelProtocol,
    LinkFailureScenario,
    RipNetwork,
    RoutingNetwork,
    StpMode,
)
from ...domain.models.plans import EIGRPConfig, OSPFConfig, RIPConfig
from ...domain.models.switch_security import STPConfig
from ...infrastructure.catalog.cables import ALL_LINK_TYPES
from ...shared.utils import validate_ios_interface_name
from .switch_security_cli_generator import generate_stp_cli
from .vlan_cli_generator import switch_supports_encap


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
_SAFE_DEVICE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_PORT_CHANNEL = re.compile(r"^Port-channel(?P<group>[1-9][0-9]{0,2})$", re.IGNORECASE)
_ROOT_PRIMARY_PRIORITY = 24576
_ROOT_SECONDARY_PRIORITY = 28672


class RenderedControlPlaneMutation(BaseModel):
    action_id: str
    device_name: str
    ios_payload: str
    cleanup_payload: str


class RenderedControlPlaneFault(BaseModel):
    scenario_id: str
    device_name: str
    interface: str
    ios_payload: str
    cleanup_payload: str


def _wrap(lines: list[str]) -> str:
    return "\n".join(["enable", "configure terminal", *lines, "end", "write memory"])


def _fault_wrap(lines: list[str]) -> str:
    """Fault injection is deliberately ephemeral and never persisted."""
    return "\n".join(["enable", "configure terminal", *lines, "end"])


def _safe_reference(value: str, label: str) -> str:
    candidate = (value or "").strip()
    if candidate != value or not _SAFE_ID.fullmatch(candidate):
        raise ValueError(f"Invalid compiled {label}: {value!r}")
    return candidate


def _safe_device(value: str) -> str:
    candidate = (value or "").strip()
    if candidate != value or not _SAFE_DEVICE.fullmatch(candidate):
        raise ValueError(f"Invalid compiled device name: {value!r}")
    return candidate


def _bounded_int(value: int, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}.")
    return value


def _vlans(values: list[int], label: str) -> list[int]:
    result = [_bounded_int(value, 1, 4094, label) for value in values]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicate VLAN IDs.")
    return sorted(result)


def _ipv4(value: str, label: str) -> str:
    try:
        return str(ipaddress.IPv4Address(value))
    except ipaddress.AddressValueError as exc:
        raise ValueError(f"Invalid compiled {label}: {value!r}") from exc


def _exact_interface(value: str, label: str = "IOS interface") -> str:
    interface = validate_ios_interface_name(value)
    if interface != value:
        raise ValueError(f"Invalid exact IOS interface for {label}: {value!r}")
    return interface


def _network(value: RoutingNetwork, *, ospf: bool) -> dict[str, str | int]:
    network_address = _ipv4(value.network, "routing network")
    wildcard = _ipv4(value.wildcard, "routing wildcard")
    wildcard_value = int(ipaddress.IPv4Address(wildcard))
    netmask = ipaddress.IPv4Address(wildcard_value ^ 0xFFFFFFFF)
    try:
        network = ipaddress.IPv4Network(f"{network_address}/{netmask}", strict=True)
    except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError) as exc:
        raise ValueError(
            f"Routing network {network_address}/{wildcard} is not canonical."
        ) from exc
    interface = _exact_interface(value.interface, "routing network")
    _safe_reference(value.segment_id, "segment ID")
    _safe_reference(value.source_configuration_action_id, "configuration action ID")
    if ospf:
        if value.area is None:
            raise ValueError("An OSPF network requires a compiled area.")
        area = _bounded_int(value.area, 0, 0xFFFFFFFF, "OSPF area")
    else:
        if value.area is not None:
            raise ValueError("An EIGRP network cannot carry an OSPF area.")
        area = 0
    return {
        "network": str(network.network_address),
        "wildcard": wildcard,
        "area": area,
        "interface": interface,
    }


def _rip_network(value: RipNetwork) -> str:
    """La sentencia `network` de RIP: sólo una dirección classful.

    Rechaza cualquier dirección que no sea el inicio exacto de su clase, para
    que el renderer no pueda emitir una sentencia que IOS reinterpretaría.
    """
    address = _ipv4(value.network, "RIP network")
    first = int(ipaddress.IPv4Address(address)) >> 24
    length = 8 if 1 <= first <= 126 else 16 if 128 <= first <= 191 else (
        24 if 192 <= first <= 223 else None
    )
    if length is None:
        raise ValueError(f"RIP network {address} belongs to no routable class.")
    if int(ipaddress.IPv4Address(address)) & ((1 << (32 - length)) - 1):
        raise ValueError(f"RIP network {address} is not a classful network address.")
    for segment_id in value.source_segment_ids:
        _safe_reference(segment_id, "segment ID")
    for action_id in value.source_configuration_action_ids:
        _safe_reference(action_id, "configuration action ID")
    return address


def _validate_common(action: BaseControlPlaneAction) -> None:
    _safe_reference(action.id, "action ID")
    _safe_reference(action.device_id, "device ID")
    _safe_device(action.device_name)
    _safe_reference(action.model, "model")
    _safe_reference(action.site_id, "site ID")
    dependencies = [_safe_reference(item, "dependency ID") for item in action.depends_on]
    if len(dependencies) != len(set(dependencies)):
        raise ValueError("Compiled dependencies contain duplicates.")


def _require_capability(
    action: BaseControlPlaneAction,
    *allowed: ControlPlaneCapabilityDimension,
) -> None:
    if action.required_capability not in allowed:
        expected = ", ".join(item.value for item in allowed)
        raise ValueError(
            f"{type(action).__name__} requires one of these capability dimensions: {expected}."
        )


class PacketTracerControlPlaneRenderer:
    """Renderiza exclusivamente acciones producidas por el compilador E9."""

    def render_actions(
        self, actions: list[ControlPlaneAction],
    ) -> list[RenderedControlPlaneMutation]:
        return [
            self.render_action(action)
            for action in sorted(actions, key=lambda item: (item.phase, item.id))
        ]

    def render_action(self, action: ControlPlaneAction) -> RenderedControlPlaneMutation:
        _validate_common(action)
        if isinstance(action, ConfigureSpanningTree):
            _require_capability(action, {
                StpMode.PVST: ControlPlaneCapabilityDimension.STP_PVST_CONFIG,
                StpMode.RAPID_PVST:
                    ControlPlaneCapabilityDimension.STP_RAPID_PVST_CONFIG,
                StpMode.MST: ControlPlaneCapabilityDimension.STP_MST_CONFIG,
            }[action.mode])
            payload, cleanup = self._spanning_tree(action)
        elif isinstance(action, ConfigureStpEdgePort):
            _require_capability(
                action,
                ControlPlaneCapabilityDimension.STP_PVST_CONFIG,
                ControlPlaneCapabilityDimension.STP_RAPID_PVST_CONFIG,
                ControlPlaneCapabilityDimension.STP_MST_CONFIG,
            )
            payload, cleanup = self._stp_edge(action)
        elif isinstance(action, ConfigureEtherChannel):
            _require_capability(action, {
                EtherChannelProtocol.LACP:
                    ControlPlaneCapabilityDimension.ETHERCHANNEL_LACP_CONFIG,
                EtherChannelProtocol.PAGP:
                    ControlPlaneCapabilityDimension.ETHERCHANNEL_PAGP_CONFIG,
                EtherChannelProtocol.STATIC:
                    ControlPlaneCapabilityDimension.ETHERCHANNEL_STATIC_CONFIG,
            }[action.protocol])
            payload, cleanup = self._etherchannel(action)
        elif isinstance(action, ConfigureHsrp):
            _require_capability(action, ControlPlaneCapabilityDimension.HSRP_CONFIG)
            payload, cleanup = self._hsrp(action)
        elif isinstance(action, ConfigureOspfv2):
            _require_capability(action, ControlPlaneCapabilityDimension.OSPFV2_CONFIG)
            payload, cleanup = self._ospf(action)
        elif isinstance(action, ConfigureEigrpIpv4):
            _require_capability(
                action, ControlPlaneCapabilityDimension.EIGRP_IPV4_CONFIG
            )
            payload, cleanup = self._eigrp(action)
        elif isinstance(action, ConfigureRipv2):
            _require_capability(action, ControlPlaneCapabilityDimension.RIPV2_CONFIG)
            payload, cleanup = self._rip(action)
        else:
            raise ValueError(
                f"No Packet Tracer control-plane renderer for {type(action).__name__}."
            )
        if not payload.strip() or not cleanup.strip():
            raise ValueError("Every control-plane mutation requires payload and cleanup.")
        return RenderedControlPlaneMutation(
            action_id=action.id,
            device_name=action.device_name,
            ios_payload=payload,
            cleanup_payload=cleanup,
        )

    @staticmethod
    def _spanning_tree(action: ConfigureSpanningTree) -> tuple[str, str]:
        vlan_ids = _vlans(action.vlan_ids, "STP VLAN")
        primary = _vlans(action.root_primary_vlans, "STP primary-root VLAN")
        secondary = _vlans(action.root_secondary_vlans, "STP secondary-root VLAN")
        priorities = {
            _bounded_int(vlan, 1, 4094, "STP priority VLAN"):
            _bounded_int(priority, 0, 61440, "STP priority")
            for vlan, priority in action.priorities.items()
        }
        if any(priority % 4096 for priority in priorities.values()):
            raise ValueError("STP priorities must be multiples of 4096.")
        referenced = set(primary) | set(secondary) | set(priorities)
        if not referenced.issubset(vlan_ids):
            raise ValueError("STP root and priority VLANs must belong to vlan_ids.")
        if set(primary) & set(secondary):
            raise ValueError("A VLAN cannot be both STP primary and secondary root.")
        source_ids = [
            _safe_reference(item, "source VLAN action ID")
            for item in action.source_vlan_action_ids
        ]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("STP source VLAN action IDs contain duplicates.")

        if action.mode is not StpMode.MST:
            if action.mst_instances:
                raise ValueError("PVST modes cannot carry MST instance mappings.")
            for vlan in primary:
                if vlan in priorities and priorities[vlan] != _ROOT_PRIMARY_PRIORITY:
                    raise ValueError(
                        "An explicit PVST primary-root priority must be 24576."
                    )
            for vlan in secondary:
                if vlan in priorities and priorities[vlan] != _ROOT_SECONDARY_PRIORITY:
                    raise ValueError(
                        "An explicit PVST secondary-root priority must be 28672."
                    )
            config = STPConfig(
                switch=action.device_name,
                mode=action.mode.value,
                root_primary_vlans=[vlan for vlan in primary if vlan not in priorities],
                priority=priorities,
            )
            body = generate_stp_cli(config)
            body.extend(
                f"spanning-tree vlan {vlan} root secondary"
                for vlan in secondary
                if vlan not in priorities
            )
            reset_vlans = sorted(referenced)
            cleanup = [
                *(f"no spanning-tree vlan {vlan} priority" for vlan in reset_vlans),
                "spanning-tree mode pvst",
            ]
            return _wrap(body), _wrap(cleanup)

        instances: dict[int, list[int]] = {}
        vlan_to_instance: dict[int, int] = {}
        for raw_instance, raw_vlans in action.mst_instances.items():
            instance = _bounded_int(raw_instance, 1, 4094, "MST instance")
            mapped = _vlans(raw_vlans, f"MST instance {instance} VLAN")
            if not mapped:
                raise ValueError("An MST instance requires at least one VLAN.")
            for vlan in mapped:
                if vlan not in vlan_ids:
                    raise ValueError("MST instance VLANs must belong to vlan_ids.")
                if vlan in vlan_to_instance:
                    raise ValueError("A VLAN cannot belong to multiple MST instances.")
                vlan_to_instance[vlan] = instance
            instances[instance] = mapped
        if referenced - set(vlan_to_instance):
            raise ValueError("MST root and priority VLANs require an instance mapping.")

        instance_priorities: dict[int, int] = {}
        for vlan, priority in priorities.items():
            instance = vlan_to_instance[vlan]
            previous = instance_priorities.get(instance)
            if previous is not None and previous != priority:
                raise ValueError("One MST instance cannot carry conflicting priorities.")
            instance_priorities[instance] = priority
        primary_instances = sorted({vlan_to_instance[vlan] for vlan in primary})
        secondary_instances = sorted({vlan_to_instance[vlan] for vlan in secondary})
        if set(primary_instances) & set(secondary_instances):
            raise ValueError("An MST instance cannot be both primary and secondary root.")
        for instance in primary_instances:
            if (
                instance in instance_priorities
                and instance_priorities[instance] != _ROOT_PRIMARY_PRIORITY
            ):
                raise ValueError(
                    "An explicit MST primary-root priority must be 24576."
                )
        for instance in secondary_instances:
            if (
                instance in instance_priorities
                and instance_priorities[instance] != _ROOT_SECONDARY_PRIORITY
            ):
                raise ValueError(
                    "An explicit MST secondary-root priority must be 28672."
                )

        body = ["spanning-tree mode mst", "spanning-tree mst configuration"]
        for instance, mapped in sorted(instances.items()):
            body.append(f" instance {instance} vlan {','.join(str(vlan) for vlan in mapped)}")
        body.append(" exit")
        body.extend(
            f"spanning-tree mst {instance} root primary"
            for instance in primary_instances
            if instance not in instance_priorities
        )
        body.extend(
            f"spanning-tree mst {instance} root secondary"
            for instance in secondary_instances
            if instance not in instance_priorities
        )
        body.extend(
            f"spanning-tree mst {instance} priority {priority}"
            for instance, priority in sorted(instance_priorities.items())
        )
        reset_instances = sorted(
            set(primary_instances) | set(secondary_instances) | set(instance_priorities)
        )
        cleanup = [
            *(f"no spanning-tree mst {instance} priority" for instance in reset_instances),
            "spanning-tree mst configuration",
            *(f" no instance {instance}" for instance in sorted(instances)),
            " exit",
            "spanning-tree mode pvst",
        ]
        return _wrap(body), _wrap(cleanup)

    @staticmethod
    def _stp_edge(action: ConfigureStpEdgePort) -> tuple[str, str]:
        interface = _exact_interface(action.interface, "STP edge port")
        _safe_reference(action.source_access_action_id, "source access action ID")
        body = [f"interface {interface}"]
        cleanup = [f"interface {interface}"]
        body.append(" spanning-tree portfast" if action.portfast else " no spanning-tree portfast")
        cleanup.append(" no spanning-tree portfast" if action.portfast else " spanning-tree portfast")
        body.append(
            " spanning-tree bpduguard enable"
            if action.bpduguard else " no spanning-tree bpduguard enable"
        )
        cleanup.append(
            " no spanning-tree bpduguard enable"
            if action.bpduguard else " spanning-tree bpduguard enable"
        )
        body.append(" exit")
        cleanup.append(" exit")
        return _wrap(body), _wrap(cleanup)

    @staticmethod
    def _etherchannel(action: ConfigureEtherChannel) -> tuple[str, str]:
        _safe_reference(action.etherchannel_id, "EtherChannel ID")
        _safe_reference(action.peer_device_id, "peer device ID")
        source_links = [_safe_reference(item, "source link ID") for item in action.source_link_ids]
        source_trunks = [
            _safe_reference(item, "source trunk action ID")
            for item in action.source_trunk_action_ids
        ]
        if len(source_links) != len(set(source_links)) or len(source_trunks) != len(set(source_trunks)):
            raise ValueError("EtherChannel source IDs contain duplicates.")
        group = _bounded_int(action.channel_group, 1, 255, "EtherChannel group")
        port_channel = _exact_interface(
            action.port_channel_interface, "EtherChannel logical interface"
        )
        match = _PORT_CHANNEL.fullmatch(port_channel)
        if match is None or int(match.group("group")) != group:
            raise ValueError("Port-channel interface must match the compiled channel group.")
        members = [
            _exact_interface(item, "EtherChannel member")
            for item in action.member_interfaces
        ]
        if len(members) < 2 or len(members) != len(set(item.casefold() for item in members)):
            raise ValueError("EtherChannel requires at least two unique member interfaces.")
        if any(_PORT_CHANNEL.fullmatch(item) for item in members):
            raise ValueError("A Port-channel cannot be an EtherChannel member interface.")
        allowed = _vlans(action.allowed_vlans, "EtherChannel allowed VLAN")
        native = (
            _bounded_int(action.native_vlan_id, 1, 4094, "EtherChannel native VLAN")
            if action.native_vlan_id is not None else None
        )
        if native is not None and allowed and native not in allowed:
            raise ValueError("EtherChannel native VLAN must be present in allowed_vlans.")
        mode = {
            EtherChannelProtocol.LACP: "active",
            EtherChannelProtocol.PAGP: "desirable",
            EtherChannelProtocol.STATIC: "on",
        }[action.protocol]
        body: list[str] = []
        for interface in members:
            body.extend([
                f"interface {interface}",
                f" channel-group {group} mode {mode}",
                " exit",
            ])
        body.append(f"interface {port_channel}")
        if switch_supports_encap(action.model):
            body.append(" switchport trunk encapsulation dot1q")
        body.append(" switchport mode trunk")
        if allowed:
            body.append(f" switchport trunk allowed vlan {','.join(str(vlan) for vlan in allowed)}")
        if native is not None:
            body.append(f" switchport trunk native vlan {native}")
        body.append(" exit")

        cleanup: list[str] = []
        for interface in members:
            cleanup.extend([
                f"interface {interface}",
                f" no channel-group {group}",
                " exit",
            ])
        cleanup.append(f"no interface {port_channel}")
        return _wrap(body), _wrap(cleanup)

    @staticmethod
    def _hsrp(action: ConfigureHsrp) -> tuple[str, str]:
        _safe_reference(action.redundancy_id, "redundancy ID")
        _safe_reference(action.segment_id, "segment ID")
        _safe_reference(
            action.source_configuration_action_id, "source configuration action ID"
        )
        interface = _exact_interface(action.interface, "HSRP interface")
        group = _bounded_int(action.group_number, 0, 255, "HSRP group")
        priority = _bounded_int(action.priority, 0, 255, "HSRP priority")
        virtual = _ipv4(action.virtual_ipv4, "HSRP virtual IPv4")
        physical = _ipv4(action.physical_ipv4, "HSRP physical IPv4")
        if virtual == physical:
            raise ValueError("HSRP virtual and physical IPv4 addresses must differ.")
        body = [
            f"interface {interface}",
            f" standby {group} ip {virtual}",
            f" standby {group} priority {priority}",
            (
                f" standby {group} preempt"
                if action.preempt else f" no standby {group} preempt"
            ),
            " exit",
        ]
        cleanup = [f"interface {interface}", f" no standby {group}", " exit"]
        return _wrap(body), _wrap(cleanup)

    @staticmethod
    def _ospf(action: ConfigureOspfv2) -> tuple[str, str]:
        process_id = _bounded_int(action.process_id, 1, 65535, "OSPF process ID")
        router_id = _ipv4(action.router_id, "OSPF router ID")
        networks = [_network(item, ospf=True) for item in action.networks]
        keys = [(item["network"], item["wildcard"], item["area"]) for item in networks]
        if not networks or len(keys) != len(set(keys)):
            raise ValueError("OSPF requires unique compiled networks.")
        passive = [
            _exact_interface(item, "OSPF passive interface")
            for item in action.passive_interfaces
        ]
        if len(passive) != len(set(item.casefold() for item in passive)):
            raise ValueError("OSPF passive interfaces contain duplicates.")
        legacy = OSPFConfig(
            router=action.device_name,
            process_id=process_id,
            router_id=router_id,
            networks=[
                {"network": item["network"], "wildcard": item["wildcard"], "area": item["area"]}
                for item in networks
            ],
        )
        body = [f"router ospf {legacy.process_id}", f" router-id {legacy.router_id}"]
        body.extend(
            f" network {item['network']} {item['wildcard']} area {item['area']}"
            for item in legacy.networks
        )
        body.extend(f" passive-interface {interface}" for interface in passive)
        body.append(" exit")
        return _wrap(body), _wrap([f"no router ospf {process_id}"])

    @staticmethod
    def _eigrp(action: ConfigureEigrpIpv4) -> tuple[str, str]:
        as_number = _bounded_int(action.as_number, 1, 65535, "EIGRP AS number")
        router_id = _ipv4(action.router_id, "EIGRP router ID")
        networks = [_network(item, ospf=False) for item in action.networks]
        keys = [(item["network"], item["wildcard"]) for item in networks]
        if not networks or len(keys) != len(set(keys)):
            raise ValueError("EIGRP requires unique compiled networks.")
        passive = [
            _exact_interface(item, "EIGRP passive interface")
            for item in action.passive_interfaces
        ]
        if len(passive) != len(set(item.casefold() for item in passive)):
            raise ValueError("EIGRP passive interfaces contain duplicates.")
        legacy = EIGRPConfig(
            router=action.device_name,
            as_number=as_number,
            networks=[
                {"network": item["network"], "wildcard": item["wildcard"]}
                for item in networks
            ],
            no_auto_summary=action.no_auto_summary,
        )
        body = [f"router eigrp {legacy.as_number}", f" eigrp router-id {router_id}"]
        body.extend(
            f" network {item['network']} {item['wildcard']}" for item in legacy.networks
        )
        body.extend(f" passive-interface {interface}" for interface in passive)
        if legacy.no_auto_summary:
            body.append(" no auto-summary")
        body.append(" exit")
        return _wrap(body), _wrap([f"no router eigrp {as_number}"])

    @staticmethod
    def _rip(action: ConfigureRipv2) -> tuple[str, str]:
        networks = [_rip_network(item) for item in action.networks]
        if not networks or len(networks) != len(set(networks)):
            raise ValueError("RIPv2 requires unique compiled classful networks.")
        passive = [
            _exact_interface(item, "RIPv2 passive interface")
            for item in action.passive_interfaces
        ]
        if len(passive) != len(set(item.casefold() for item in passive)):
            raise ValueError("RIPv2 passive interfaces contain duplicates.")
        legacy = RIPConfig(
            router=action.device_name,
            version=action.version,
            networks=networks,
            no_auto_summary=action.no_auto_summary,
        )
        if legacy.version != 2:
            raise ValueError("Only RIP version 2 is a compiled product path.")
        # Este orden es el payload calificado en vivo durante R2-0.
        body = ["router rip", f" version {legacy.version}"]
        if legacy.no_auto_summary:
            body.append(" no auto-summary")
        body.extend(f" network {item}" for item in legacy.networks)
        body.extend(f" passive-interface {interface}" for interface in passive)
        body.append(" exit")
        return _wrap(body), _wrap(["no router rip"])


class PacketTracerControlPlaneFaultRenderer:
    """Renderiza sólo el target exacto resuelto por el escenario compilado."""

    def render_scenario(self, scenario: LinkFailureScenario) -> RenderedControlPlaneFault:
        scenario_id = _safe_reference(scenario.id, "failure scenario ID")
        _safe_reference(scenario.link_id, "failure link ID")
        device_a_id = _safe_reference(scenario.device_a_id, "failure device A ID")
        device_b_id = _safe_reference(scenario.device_b_id, "failure device B ID")
        target_device_id = _safe_reference(
            scenario.target_device_id, "fault target device ID"
        )
        device = _safe_device(scenario.target_device_name)
        port = _exact_interface(scenario.target_interface, "fault target")
        peer_device_id = _safe_reference(scenario.peer_device_id, "fault peer device ID")
        _safe_device(scenario.peer_device_name)
        _exact_interface(scenario.peer_interface, "fault peer")
        cable = _safe_reference(scenario.cable, "fault cable")
        if cable not in ALL_LINK_TYPES:
            raise ValueError(f"Unknown compiled Packet Tracer cable type: {cable!r}")
        _safe_reference(scenario.probe_source_device_id, "probe source device ID")
        _safe_device(scenario.probe_source_device_name)
        _safe_reference(
            scenario.probe_destination_device_id, "probe destination device ID"
        )
        _safe_device(scenario.probe_destination_device_name)
        _ipv4(scenario.probe_destination_ipv4, "probe destination IPv4")
        surviving = [
            _safe_reference(item, "surviving link ID")
            for item in scenario.expected_surviving_link_ids
        ]
        verifications = [
            _safe_reference(item, "verification expectation ID")
            for item in scenario.verification_expectation_ids
        ]
        if len(surviving) != len(set(surviving)):
            raise ValueError("Failure scenario surviving link IDs contain duplicates.")
        if len(verifications) != len(set(verifications)):
            raise ValueError("Failure scenario verification IDs contain duplicates.")
        if {target_device_id, peer_device_id} != {
            device_a_id, device_b_id,
        }:
            raise ValueError("Fault target and peer must be the compiled link endpoints.")
        if scenario.link_id in surviving:
            raise ValueError("The failed link cannot also be an expected surviving link.")
        if not scenario.restore_required:
            raise ValueError("Packet Tracer fault injection requires an inverse restore.")
        return RenderedControlPlaneFault(
            scenario_id=scenario_id,
            device_name=device,
            interface=port,
            ios_payload=_fault_wrap([f"interface {port}", " shutdown", " exit"]),
            cleanup_payload=_fault_wrap([f"interface {port}", " no shutdown", " exit"]),
        )
