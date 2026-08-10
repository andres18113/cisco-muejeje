"""Consultas IOS registradas y lectura operacional sobre TerminalLine."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from time import monotonic
from collections.abc import Callable
from typing import Never

from ...domain.enterprise.models.discovery import DeviceInitializationResult
from .device_lifecycle import IosBootWaiter, StateConvergenceWaiter


class OperationalQueryId(str, Enum):
    SHOW_IP_INTERFACE_BRIEF = "show_ip_interface_brief"
    SHOW_INTERFACES_TRUNK = "show_interfaces_trunk"
    SHOW_EPHONE = "show_ephone"
    SHOW_ACCESS_LISTS = "show_access_lists"
    SHOW_IP_INTERFACE = "show_ip_interface"
    SHOW_IP_NAT_TRANSLATIONS = "show_ip_nat_translations"
    SHOW_IP_NAT_STATISTICS = "show_ip_nat_statistics"
    SHOW_PORT_SECURITY_INTERFACE = "show_port_security_interface"
    SHOW_IP_DHCP_SNOOPING = "show_ip_dhcp_snooping"
    SHOW_IP_ARP_INSPECTION = "show_ip_arp_inspection"
    SHOW_SPANNING_TREE = "show_spanning_tree"
    SHOW_ETHERCHANNEL_SUMMARY = "show_etherchannel_summary"
    SHOW_IP_OSPF_NEIGHBOR = "show_ip_ospf_neighbor"
    SHOW_IP_ROUTE_OSPF = "show_ip_route_ospf"
    SHOW_IP_EIGRP_NEIGHBORS = "show_ip_eigrp_neighbors"
    SHOW_IP_ROUTE_EIGRP = "show_ip_route_eigrp"


class TrunkQueryClassification(str, Enum):
    SUPPORTED_WITH_ROWS = "supported_with_rows"
    SUPPORTED_EMPTY = "supported_empty"
    INVALID_COMMAND = "invalid_command"
    UNIMPLEMENTED = "unimplemented"
    QUERY_TIMEOUT = "query_timeout"
    PARSER_UNAVAILABLE = "parser_unavailable"


class StpQueryClassification(str, Enum):
    SUPPORTED_WITH_INSTANCES = "supported_with_instances"
    SUPPORTED_EMPTY = "supported_empty"
    INVALID_COMMAND = "invalid_command"
    UNIMPLEMENTED = "unimplemented"
    QUERY_TIMEOUT = "query_timeout"
    PARSER_UNAVAILABLE = "parser_unavailable"


class EtherChannelQueryClassification(str, Enum):
    SUPPORTED_WITH_GROUPS = "supported_with_groups"
    QUERY_TIMEOUT = "query_timeout"
    PARSER_UNAVAILABLE = "parser_unavailable"


class OspfQueryClassification(str, Enum):
    SUPPORTED_WITH_ROWS = "supported_with_rows"
    QUERY_TIMEOUT = "query_timeout"
    PARSER_UNAVAILABLE = "parser_unavailable"


class EigrpQueryClassification(str, Enum):
    SUPPORTED_EMPTY = "supported_empty"
    PROCESS_MISMATCH = "process_mismatch"
    QUERY_TIMEOUT = "query_timeout"
    PARSER_UNAVAILABLE = "parser_unavailable"


class IosSessionState(str, Enum):
    WAITING_FOR_BOOT = "waiting_for_boot"
    BOOT_COMPLETE = "boot_complete"
    SETUP_DIALOG = "setup_dialog"
    SETUP_RESPONSE_SENT = "setup_response_sent"
    PRESS_RETURN = "press_return"
    RETURN_SENT = "return_sent"
    EXEC_PROMPT_READY = "exec_prompt_ready"
    TIMEOUT = "timeout"
    FAILED = "failed"


_COMMANDS = {
    OperationalQueryId.SHOW_IP_INTERFACE_BRIEF: "show ip interface brief",
    OperationalQueryId.SHOW_INTERFACES_TRUNK: "show interfaces trunk",
    OperationalQueryId.SHOW_EPHONE: "show ephone",
    OperationalQueryId.SHOW_ACCESS_LISTS: "show access-lists",
    OperationalQueryId.SHOW_IP_NAT_TRANSLATIONS: "show ip nat translations",
    OperationalQueryId.SHOW_IP_NAT_STATISTICS: "show ip nat statistics",
    OperationalQueryId.SHOW_IP_DHCP_SNOOPING: "show ip dhcp snooping",
    OperationalQueryId.SHOW_IP_ARP_INSPECTION: "show ip arp inspection",
    OperationalQueryId.SHOW_SPANNING_TREE: "show spanning-tree",
    OperationalQueryId.SHOW_ETHERCHANNEL_SUMMARY: "show etherchannel summary",
    OperationalQueryId.SHOW_IP_OSPF_NEIGHBOR: "show ip ospf neighbor",
    OperationalQueryId.SHOW_IP_ROUTE_OSPF: "show ip route ospf",
    OperationalQueryId.SHOW_IP_EIGRP_NEIGHBORS: "show ip eigrp neighbors",
    OperationalQueryId.SHOW_IP_ROUTE_EIGRP: "show ip route eigrp",
}
_INTERFACE_COMMANDS = {
    OperationalQueryId.SHOW_IP_INTERFACE: "show ip interface {interface}",
    OperationalQueryId.SHOW_PORT_SECURITY_INTERFACE:
        "show port-security interface {interface}",
}
_PRIVILEGED_QUERIES = {
    OperationalQueryId.SHOW_EPHONE,
    OperationalQueryId.SHOW_ACCESS_LISTS,
    OperationalQueryId.SHOW_IP_INTERFACE,
    OperationalQueryId.SHOW_IP_NAT_TRANSLATIONS,
    OperationalQueryId.SHOW_IP_NAT_STATISTICS,
    OperationalQueryId.SHOW_PORT_SECURITY_INTERFACE,
    OperationalQueryId.SHOW_IP_DHCP_SNOOPING,
    OperationalQueryId.SHOW_IP_ARP_INSPECTION,
}
_INTERFACE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9./:-]{0,79}$")
_SETUP_DIALOG = "would you like to enter the initial configuration dialog"
_PAGER_MARKER = "--More--"


@dataclass(frozen=True)
class IosCommandResult:
    device_name: str
    query_id: OperationalQueryId
    executed: bool
    output: str = ""
    failure_reason: str = ""
    duration_ms: int = 0
    session_state: IosSessionState = IosSessionState.FAILED
    fresh_output_observed: bool = False
    window_strategy: str = "none"
    truncated_by_pager: bool = False


@dataclass(frozen=True)
class InterfaceStatusRow:
    interface: str
    ip_address: str
    status: str
    protocol: str


@dataclass(frozen=True)
class EphoneStatusRow:
    index: int
    mac_address: str
    registered: bool
    ip_address: str
    extension: str
    line_state: str


@dataclass(frozen=True)
class TrunkStatusRow:
    interface: str
    mode: str
    encapsulation: str
    status: str
    native_vlan: str


@dataclass(frozen=True)
class StpPortStatusRow:
    interface: str
    role: str
    state: str
    cost: int
    priority_number: str
    link_type: str


@dataclass(frozen=True)
class StpInstanceStatus:
    vlan_id: int
    protocol: str
    root_priority: int
    root_address: str
    root_is_local: bool
    root_cost: int | None
    root_port: str
    bridge_priority: int
    bridge_base_priority: int | None
    bridge_address: str
    interfaces: tuple[StpPortStatusRow, ...]


@dataclass(frozen=True)
class EtherChannelMemberStatus:
    interface: str
    flag: str


@dataclass(frozen=True)
class EtherChannelGroupStatus:
    group_number: int
    port_channel: str
    port_channel_flags: str
    protocol: str
    members: tuple[EtherChannelMemberStatus, ...]


@dataclass(frozen=True)
class OspfNeighborStatusRow:
    neighbor_id: str
    priority: int
    state: str
    role: str
    dead_time: str
    address: str
    interface: str


@dataclass(frozen=True)
class OspfRouteStatusRow:
    code: str
    prefix: str
    prefix_length: int | None
    administrative_distance: int
    metric: int
    next_hop: str
    age: str
    interface: str


@dataclass(frozen=True)
class TerminalOutputWindow:
    output: str
    fresh: bool
    strategy: str
    query_echo_found: bool = False


def normalize_terminal_output(value: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", value).replace("\r\n", "\n").replace("\r", "\n")


def _has_active_pager(value: str) -> bool:
    return normalize_terminal_output(value).rstrip().endswith(_PAGER_MARKER)


def parse_show_ip_interface_brief(value: str) -> list[InterfaceStatusRow]:
    rows: list[InterfaceStatusRow] = []
    for line in normalize_terminal_output(value).splitlines():
        parts = line.split()
        if len(parts) < 6 or parts[0].casefold() == "interface":
            continue
        if not re.match(r"^[A-Za-z]+[A-Za-z0-9/.-]*$", parts[0]):
            continue
        rows.append(InterfaceStatusRow(parts[0], parts[1], " ".join(parts[4:-1]), parts[-1]))
    return rows


def parse_show_ephone(value: str) -> list[EphoneStatusRow]:
    """Extrae el estado vigente de cada bloque de ``show ephone`` de PT."""
    normalized = normalize_terminal_output(value)
    starts = list(re.finditer(
        r"(?m)^ephone-(?P<index>\d+)\s+Mac:(?P<mac>[0-9A-Fa-f.:-]+).*?"
        r"(?P<registration>UNREGISTERED|REGISTERED)(?:\s|$)",
        normalized,
    ))
    rows: list[EphoneStatusRow] = []
    for position, match in enumerate(starts):
        end = starts[position + 1].start() if position + 1 < len(starts) else len(normalized)
        block = normalized[match.start():end]
        ip_match = re.search(r"(?m)^IP:(?P<ip>\S+)", block)
        line_match = re.search(
            r"(?m)^\s*button\s+\d+:\s+dn\s+\d+\s+number\s+"
            r"(?P<extension>\d+)\s+CH\d+\s+(?P<state>\S+)",
            block,
            re.IGNORECASE,
        )
        if ip_match is None or line_match is None:
            continue
        rows.append(EphoneStatusRow(
            index=int(match.group("index")),
            mac_address=match.group("mac"),
            registered=match.group("registration").upper() == "REGISTERED",
            ip_address=ip_match.group("ip"),
            extension=line_match.group("extension"),
            line_state=line_match.group("state").upper(),
        ))
    return rows


def parse_show_interfaces_trunk(value: str) -> list[TrunkStatusRow]:
    """Parsea solamente filas de trunk del SHOW actual de Packet Tracer."""
    rows: list[TrunkStatusRow] = []
    for line in normalize_terminal_output(value).splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].casefold() in {"port", "switch>"}:
            continue
        if not re.match(r"^[A-Za-z]+[A-Za-z0-9/.-]*$", parts[0]):
            continue
        if parts[1].casefold() not in {"on", "desirable", "auto", "trunk"}:
            continue
        rows.append(TrunkStatusRow(parts[0], parts[1], parts[2], parts[3], parts[4]))
    return rows


def classify_show_interfaces_trunk(value: str, *, executed: bool = True) -> TrunkQueryClassification:
    if not executed:
        return TrunkQueryClassification.QUERY_TIMEOUT
    output = normalize_terminal_output(value).casefold()
    if "invalid input" in output or "% unknown command" in output:
        return TrunkQueryClassification.INVALID_COMMAND
    if "unimplemented" in output or "not supported" in output:
        return TrunkQueryClassification.UNIMPLEMENTED
    if parse_show_interfaces_trunk(value):
        return TrunkQueryClassification.SUPPORTED_WITH_ROWS
    if "show interfaces trunk" in output:
        return TrunkQueryClassification.SUPPORTED_EMPTY
    return TrunkQueryClassification.PARSER_UNAVAILABLE


def parse_show_spanning_tree(value: str) -> list[StpInstanceStatus]:
    """Parse the exact multi-instance layout emitted by PT 9.0.1.0858."""
    normalized = normalize_terminal_output(value)
    starts = list(re.finditer(r"(?m)^VLAN(?P<vlan>\d+)\s*$", normalized))
    instances: list[StpInstanceStatus] = []
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(normalized)
        block = normalized[start.start():end]
        protocol = re.search(
            r"(?m)^\s*Spanning tree enabled protocol\s+(?P<value>\S+)\s*$",
            block,
        )
        root = re.search(
            r"(?ms)^\s*Root ID\s+Priority\s+(?P<priority>\d+)\s*\n"
            r"\s*Address\s+(?P<address>[0-9A-Fa-f.:-]+)(?P<body>.*?)"
            r"^\s*Bridge ID\s+Priority",
            block,
        )
        bridge = re.search(
            r"(?m)^\s*Bridge ID\s+Priority\s+(?P<priority>\d+)"
            r"(?:\s+\(priority\s+(?P<base>\d+)\s+sys-id-ext\s+\d+\))?\s*\n"
            r"\s*Address\s+(?P<address>[0-9A-Fa-f.:-]+)",
            block,
        )
        if protocol is None or root is None or bridge is None:
            continue
        root_body = root.group("body")
        cost = re.search(r"(?m)^\s*Cost\s+(?P<value>\d+)\s*$", root_body)
        port = re.search(
            r"(?m)^\s*Port\s+\d+\((?P<value>[^)]+)\)\s*$",
            root_body,
        )
        rows: list[StpPortStatusRow] = []
        for line in block.splitlines():
            parts = line.split()
            if len(parts) < 6 or not re.fullmatch(
                r"[A-Za-z]+[A-Za-z0-9/.-]*", parts[0]
            ):
                continue
            if parts[1] not in {"Root", "Desg", "Altn", "Back", "Mstr"}:
                continue
            try:
                row_cost = int(parts[3])
            except ValueError:
                continue
            rows.append(StpPortStatusRow(
                interface=parts[0],
                role=parts[1],
                state=parts[2],
                cost=row_cost,
                priority_number=parts[4],
                link_type=" ".join(parts[5:]),
            ))
        instances.append(StpInstanceStatus(
            vlan_id=int(start.group("vlan")),
            protocol=protocol.group("value").casefold(),
            root_priority=int(root.group("priority")),
            root_address=root.group("address"),
            root_is_local="this bridge is the root" in root_body.casefold(),
            root_cost=int(cost.group("value")) if cost else None,
            root_port=port.group("value") if port else "",
            bridge_priority=int(bridge.group("priority")),
            bridge_base_priority=(
                int(bridge.group("base")) if bridge.group("base") else None
            ),
            bridge_address=bridge.group("address"),
            interfaces=tuple(rows),
        ))
    return instances


def classify_show_spanning_tree(
    value: str,
    *,
    executed: bool = True,
) -> StpQueryClassification:
    if not executed:
        return StpQueryClassification.QUERY_TIMEOUT
    output = normalize_terminal_output(value).casefold()
    if "invalid input" in output or "% unknown command" in output:
        return StpQueryClassification.INVALID_COMMAND
    if "unimplemented" in output or "not supported" in output:
        return StpQueryClassification.UNIMPLEMENTED
    if parse_show_spanning_tree(value):
        return StpQueryClassification.SUPPORTED_WITH_INSTANCES
    if "no spanning tree instance exists" in output:
        return StpQueryClassification.SUPPORTED_EMPTY
    if "show spanning-tree" in output:
        return StpQueryClassification.PARSER_UNAVAILABLE
    return StpQueryClassification.PARSER_UNAVAILABLE


def parse_show_etherchannel_summary(
    value: str,
) -> list[EtherChannelGroupStatus]:
    """Parse the group row observed in PT 9.0.1.0858."""
    groups: list[EtherChannelGroupStatus] = []
    group_row = re.compile(
        r"\s*(?P<group>\d+)\s+"
        r"(?P<port_channel>Po\d+)\((?P<flags>[A-Za-z]+)\)\s+"
        r"(?P<protocol>[A-Za-z0-9-]+)\s+"
        r"(?P<members>.+?)\s*"
    )
    member_value = re.compile(
        r"(?P<interface>[A-Za-z]+[A-Za-z0-9/.-]*)"
        r"\((?P<flag>[A-Za-z]+)\)"
    )
    for line in normalize_terminal_output(value).splitlines():
        match = group_row.fullmatch(line)
        if match is None:
            continue
        # LACP is the only protocol row backed by a captured PT 9.0.1.0858
        # fixture. PAgP and static/on stay unobservable until their real output
        # is captured instead of being accepted by a permissive regex.
        if match.group("protocol").casefold() != "lacp":
            continue
        members = tuple(
            EtherChannelMemberStatus(
                interface=item.group("interface"),
                flag=item.group("flag"),
            )
            for item in member_value.finditer(match.group("members"))
        )
        observed_members = " ".join(match.group("members").split())
        parsed_members = " ".join(
            f"{item.interface}({item.flag})" for item in members
        )
        if not members or parsed_members != observed_members:
            continue
        groups.append(EtherChannelGroupStatus(
            group_number=int(match.group("group")),
            port_channel=match.group("port_channel"),
            port_channel_flags=match.group("flags"),
            protocol=match.group("protocol"),
            members=members,
        ))
    return groups


def classify_show_etherchannel_summary(
    value: str,
    *,
    executed: bool = True,
) -> EtherChannelQueryClassification:
    if not executed:
        return EtherChannelQueryClassification.QUERY_TIMEOUT
    if parse_show_etherchannel_summary(value):
        return EtherChannelQueryClassification.SUPPORTED_WITH_GROUPS
    return EtherChannelQueryClassification.PARSER_UNAVAILABLE


def parse_show_ip_ospf_neighbor(value: str) -> list[OspfNeighborStatusRow]:
    """Parse only the FULL DR/BDR rows observed in PT 9.0.1.0858."""
    rows: list[OspfNeighborStatusRow] = []
    row_pattern = re.compile(
        r"\s*(?P<neighbor>\d{1,3}(?:\.\d{1,3}){3})\s+"
        r"(?P<priority>\d+)\s+"
        r"(?P<state>FULL)/(?P<role>DR|BDR)\s+"
        r"(?P<dead_time>\d{2}:\d{2}:\d{2})\s+"
        r"(?P<address>\d{1,3}(?:\.\d{1,3}){3})\s+"
        r"(?P<interface>GigabitEthernet\d+/\d+)\s*"
    )
    for line in normalize_terminal_output(value).splitlines():
        match = row_pattern.fullmatch(line)
        if match is None:
            continue
        rows.append(OspfNeighborStatusRow(
            neighbor_id=match.group("neighbor"),
            priority=int(match.group("priority")),
            state=match.group("state"),
            role=match.group("role"),
            dead_time=match.group("dead_time"),
            address=match.group("address"),
            interface=match.group("interface"),
        ))
    return rows


def classify_show_ip_ospf_neighbor(
    value: str,
    *,
    executed: bool = True,
) -> OspfQueryClassification:
    if not executed:
        return OspfQueryClassification.QUERY_TIMEOUT
    if parse_show_ip_ospf_neighbor(value):
        return OspfQueryClassification.SUPPORTED_WITH_ROWS
    return OspfQueryClassification.PARSER_UNAVAILABLE


def parse_show_ip_route_ospf(value: str) -> list[OspfRouteStatusRow]:
    """Parse only the OSPF route row observed in PT 9.0.1.0858."""
    rows: list[OspfRouteStatusRow] = []
    row_pattern = re.compile(
        r"\s*(?P<code>O)\s+"
        r"(?P<prefix>\d{1,3}(?:\.\d{1,3}){3})"
        r"(?:/(?P<prefix_length>\d{1,2}))?\s+"
        r"\[(?P<distance>\d+)/(?P<metric>\d+)\]\s+"
        r"via\s+(?P<next_hop>\d{1,3}(?:\.\d{1,3}){3}),\s+"
        r"(?P<age>\d{2}:\d{2}:\d{2}),\s+"
        r"(?P<interface>GigabitEthernet\d+/\d+)\s*"
    )
    for line in normalize_terminal_output(value).splitlines():
        match = row_pattern.fullmatch(line)
        if match is None:
            continue
        prefix_length = (
            int(match.group("prefix_length"))
            if match.group("prefix_length") is not None else None
        )
        if prefix_length is not None and prefix_length > 32:
            continue
        rows.append(OspfRouteStatusRow(
            code=match.group("code"),
            prefix=match.group("prefix"),
            prefix_length=prefix_length,
            administrative_distance=int(match.group("distance")),
            metric=int(match.group("metric")),
            next_hop=match.group("next_hop"),
            age=match.group("age"),
            interface=match.group("interface"),
        ))
    return rows


def classify_show_ip_route_ospf(
    value: str,
    *,
    executed: bool = True,
) -> OspfQueryClassification:
    if not executed:
        return OspfQueryClassification.QUERY_TIMEOUT
    if parse_show_ip_route_ospf(value):
        return OspfQueryClassification.SUPPORTED_WITH_ROWS
    return OspfQueryClassification.PARSER_UNAVAILABLE


def parse_show_ip_eigrp_neighbors(_value: str) -> list[Never]:
    """No EIGRP neighbor row was observed in PT 9.0.1.0858."""
    return []


def classify_show_ip_eigrp_neighbors(
    value: str,
    *,
    executed: bool = True,
    expected_as_number: int | None = None,
) -> EigrpQueryClassification:
    if not executed:
        return EigrpQueryClassification.QUERY_TIMEOUT
    lines = tuple(
        line.strip()
        for line in normalize_terminal_output(value).splitlines()
        if line.strip()
    )
    if len(lines) == 3 and lines[0] == "show ip eigrp neighbors":
        process = re.fullmatch(
            r"IP-EIGRP neighbors for process (?P<as_number>\d+)",
            lines[1],
        )
        if process is not None and re.fullmatch(r"\S+[>#]", lines[2]):
            observed_as = int(process.group("as_number"))
            if expected_as_number is not None and observed_as != expected_as_number:
                return EigrpQueryClassification.PROCESS_MISMATCH
            return EigrpQueryClassification.SUPPORTED_EMPTY
    return EigrpQueryClassification.PARSER_UNAVAILABLE


def parse_show_ip_route_eigrp(_value: str) -> list[Never]:
    """No EIGRP route row was observed in PT 9.0.1.0858."""
    return []


def classify_show_ip_route_eigrp(
    value: str,
    *,
    executed: bool = True,
) -> EigrpQueryClassification:
    if not executed:
        return EigrpQueryClassification.QUERY_TIMEOUT
    lines = tuple(
        line.strip()
        for line in normalize_terminal_output(value).splitlines()
        if line.strip()
    )
    if (
        len(lines) == 2
        and lines[0] == "show ip route eigrp"
        and re.fullmatch(r"\S+[>#]", lines[1])
    ):
        return EigrpQueryClassification.SUPPORTED_EMPTY
    return EigrpQueryClassification.PARSER_UNAVAILABLE


def extract_terminal_command_window(before: str, after: str, command: str) -> TerminalOutputWindow:
    """Aísla evidencia de la consulta actual sin confiar en historial IOS."""
    if after.startswith(before) and len(after) > len(before):
        return TerminalOutputWindow(after[len(before):], True, "prefix_delta", command.casefold() in after[len(before):].casefold())
    marker = command.casefold()
    index = after.casefold().rfind(marker)
    if index >= 0 and after[index:] != before[index:]:
        return TerminalOutputWindow(after[index:], True, "last_query_echo", True)
    return TerminalOutputWindow("", False, "no_fresh_window")


class ControlledIosExecutor:
    """Ejecuta exclusivamente consultas IOS registradas; nunca CLI del usuario."""

    def __init__(self, send_and_wait: Callable[[str, float], str | None]) -> None:
        self._send_and_wait = send_and_wait
        self._pager_quarantine: set[str] = set()

    def wait_until_ready(
        self,
        device_name: str,
        *,
        timeout_seconds: float = 90.0,
        interval_seconds: float = 0.25,
    ) -> DeviceInitializationResult:
        """Espera el boot IOS con el waiter compartido, separado del SHOW."""
        name = json.dumps(device_name)
        return IosBootWaiter(
            lambda: self._terminal_state(name),
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        ).wait()

    def execute(
        self,
        device_name: str,
        query_id: OperationalQueryId,
        *,
        interface: str = "",
    ) -> IosCommandResult:
        started = monotonic()
        try:
            command = self._registered_command(query_id, interface=interface)
        except ValueError as exc:
            return IosCommandResult(
                device_name,
                query_id,
                False,
                failure_reason=str(exc),
                duration_ms=int((monotonic() - started) * 1000),
            )
        name, command_json = json.dumps(device_name), json.dumps(command)
        session = self._prepare_session(name)
        if session is not IosSessionState.EXEC_PROMPT_READY:
            return IosCommandResult(device_name, query_id, False, failure_reason="IOS session state: " + session.value, duration_ms=int((monotonic() - started) * 1000), session_state=session)
        restore_user_mode = False
        if query_id in _PRIVILEGED_QUERIES:
            current = self._terminal_state(name)
            if str(current.get("prompt") or "").strip().endswith(">"):
                if not self._enter(name, "enable") or not self._wait_for(
                    name,
                    lambda state: str(state.get("prompt") or "").strip().endswith("#"),
                ):
                    return IosCommandResult(
                        device_name, query_id, False,
                        failure_reason="IOS privileged EXEC mode was unavailable.",
                        duration_ms=int((monotonic() - started) * 1000),
                        session_state=session,
                    )
                restore_user_mode = True

        def complete(result: IosCommandResult) -> IosCommandResult:
            if restore_user_mode:
                self._enter(name, "disable")
            return result

        js = "".join((
            "try{var d=ipc.network().getDevice(", name, ");var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;",
            "if(!t||typeof t.enterCommand!=='function'||typeof t.getOutput!=='function'){reportResult(JSON.stringify({ok:false,reason:'IOS terminal unavailable'}));}",
            "else{var before=String(t.getOutput());t.enterCommand(", command_json, ");",
            "reportResult(JSON.stringify({ok:true,before:before}));}}catch(e){reportResult('ERROR:'+e);}",
        ))
        raw = self._send_and_wait(js, 10.0)
        elapsed = int((monotonic() - started) * 1000)
        if raw is None:
            return complete(IosCommandResult(device_name, query_id, False, failure_reason="IOS command submission timed out.", duration_ms=elapsed, session_state=session))
        if raw.startswith("ERROR:"):
            return complete(IosCommandResult(device_name, query_id, False, failure_reason=raw, duration_ms=elapsed, session_state=session))
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            return complete(IosCommandResult(device_name, query_id, False, failure_reason="IOS terminal returned malformed JSON.", duration_ms=elapsed, session_state=session))
        if not state.get("ok"):
            return complete(IosCommandResult(device_name, query_id, False, failure_reason=str(state.get("reason") or "IOS terminal unavailable."), duration_ms=elapsed, session_state=session))
        baseline = str(state.get("before") or "")
        def observe() -> dict:
            read_js = "".join((
                "try{var d=ipc.network().getDevice(", name, ");var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;",
                "var o=t&&typeof t.getOutput==='function'?String(t.getOutput()):'';",
                "reportResult(JSON.stringify({found:!!d,configuration_channel:o!==", json.dumps(baseline), ",output:o}));}",
                "catch(e){reportResult('ERROR:'+e);}",
            ))
            observed = self._send_and_wait(read_js, 3.0)
            if observed is None or observed.startswith("ERROR:"):
                return {"found": False, "failure_reason": observed or "IOS output timed out."}
            try:
                return json.loads(observed)
            except json.JSONDecodeError:
                return {"found": False, "failure_reason": "IOS output was malformed."}
        convergence = StateConvergenceWaiter(observe, timeout_seconds=8.0).wait()
        elapsed = int((monotonic() - started) * 1000)
        output = str(observe().get("output") or "")
        window = extract_terminal_command_window(baseline, output, command)
        truncated_by_pager = _PAGER_MARKER in window.output
        if truncated_by_pager:
            # PT 9.0.1 rejects ``terminal length 0``. Cancel the documented
            # TerminalLine interaction so a paginated SHOW cannot poison the
            # next registered query. The captured first page remains evidence.
            pager_isolated = self._cancel_pager(name, output)
            if not pager_isolated:
                self._pager_quarantine.add(name)
                return IosCommandResult(
                    device_name,
                    query_id,
                    False,
                    output=normalize_terminal_output(window.output),
                    failure_reason=(
                        "IOS pager cancellation could not be confirmed; "
                        "the terminal session remains isolated from new queries."
                    ),
                    duration_ms=elapsed,
                    session_state=IosSessionState.FAILED,
                    fresh_output_observed=window.fresh,
                    window_strategy=window.strategy,
                    truncated_by_pager=True,
                )
        if not convergence.configuration_channel:
            return complete(IosCommandResult(device_name, query_id, False, output=normalize_terminal_output(window.output), failure_reason="IOS command output did not converge.", duration_ms=elapsed, session_state=session, fresh_output_observed=window.fresh, window_strategy=window.strategy, truncated_by_pager=truncated_by_pager))
        if not window.fresh:
            return complete(IosCommandResult(device_name, query_id, False, failure_reason="No fresh current-command output window was observed.", duration_ms=elapsed, session_state=session, window_strategy=window.strategy))
        return complete(IosCommandResult(device_name, query_id, True, output=normalize_terminal_output(window.output), duration_ms=elapsed, session_state=session, fresh_output_observed=True, window_strategy=window.strategy, truncated_by_pager=truncated_by_pager))

    @staticmethod
    def _registered_command(query_id: OperationalQueryId, *, interface: str) -> str:
        if query_id in _INTERFACE_COMMANDS:
            if not _INTERFACE_NAME.fullmatch(interface):
                raise ValueError("A registered interface query requires a valid interface name.")
            return _INTERFACE_COMMANDS[query_id].format(interface=interface)
        if interface:
            raise ValueError("This registered IOS query does not accept an interface.")
        return _COMMANDS[query_id]

    def _cancel_pager(self, name: str, paged_output: str) -> bool:
        js = "try{var d=ipc.network().getDevice(" + name + ");var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;if(!t||typeof t.enterCommand!=='function'){reportResult('{\"ok\":false}');}else{t.enterCommand(String.fromCharCode(3));reportResult('{\"ok\":true}');}}catch(e){reportResult('ERROR:'+e);}"
        if self._send_and_wait(js, 5.0) != '{"ok":true}':
            return False
        return self._wait_for(
            name,
            lambda state: (
                self._is_exec_prompt(state)
                and str(state.get("output") or "") != paged_output
                and not _has_active_pager(str(state.get("output") or ""))
            ),
        )

    def _prepare_session(self, name: str) -> IosSessionState:
        state = self._terminal_state(name)
        if not state.get("found") or not state.get("terminal"):
            return IosSessionState.FAILED
        if state.get("booting") is True:
            return IosSessionState.WAITING_FOR_BOOT
        if name in self._pager_quarantine or _has_active_pager(
            str(state.get("output") or ""),
        ):
            if not self._cancel_pager(name, str(state.get("output") or "")):
                self._pager_quarantine.add(name)
                return IosSessionState.FAILED
            self._pager_quarantine.discard(name)
            state = self._terminal_state(name)
            if _has_active_pager(str(state.get("output") or "")):
                self._pager_quarantine.add(name)
                return IosSessionState.FAILED
        content = (str(state.get("prompt") or "") + "\n" + str(state.get("output") or "")).casefold()
        if self._is_exec_prompt(state):
            return IosSessionState.EXEC_PROMPT_READY
        if _SETUP_DIALOG in content:
            if not self._enter(name, "no"):
                return IosSessionState.FAILED
            if not self._wait_for(name, lambda current: "press return to get started" in str(current.get("output") or "").casefold()):
                return IosSessionState.TIMEOUT
            if not self._enter(name, ""):
                return IosSessionState.FAILED
            return IosSessionState.EXEC_PROMPT_READY if self._wait_for(name, self._is_exec_prompt) else IosSessionState.TIMEOUT
        if "press return to get started" in content:
            if not self._enter(name, ""):
                return IosSessionState.FAILED
            return IosSessionState.EXEC_PROMPT_READY if self._wait_for(name, self._is_exec_prompt) else IosSessionState.TIMEOUT
        return IosSessionState.FAILED

    @staticmethod
    def _is_exec_prompt(state: dict) -> bool:
        prompt = str(state.get("prompt") or "").strip()
        # getOutput() conserva el transcript completo, incluso el setup dialog
        # ya terminado. El prompt actual es la señal operacional; reinterpretar
        # el histórico como estado presente impedía llegar a Router>/Router#.
        return bool(prompt and prompt.endswith((">", "#")) and _SETUP_DIALOG not in prompt.casefold())

    def _enter(self, name: str, command: str) -> bool:
        js = "try{var d=ipc.network().getDevice(" + name + ");var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;if(!t||typeof t.enterCommand!=='function'){reportResult('{\"ok\":false}');}else{t.enterCommand(" + json.dumps(command) + ");reportResult('{\"ok\":true}');}}catch(e){reportResult('ERROR:'+e);}"
        response = self._send_and_wait(js, 5.0)
        return response == '{"ok":true}'

    def _terminal_state(self, name: str) -> dict:
        js = "try{var d=ipc.network().getDevice(" + name + ");var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;reportResult(JSON.stringify({found:!!d,booting:d&&typeof d.isBooting==='function'?!!d.isBooting():null,terminal:!!t,terminal_available:!!t,terminal_kind:'ios_command_line',prompt:t&&typeof t.getPrompt==='function'?String(t.getPrompt()):'',output:t&&typeof t.getOutput==='function'?String(t.getOutput()):''}));}catch(e){reportResult('ERROR:'+e);}"
        raw = self._send_and_wait(js, 3.0)
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}

    def _wait_for(self, name: str, predicate: Callable[[dict], bool]) -> bool:
        def inspect() -> dict:
            current = self._terminal_state(name)
            current["configuration_channel"] = predicate(current)
            return current
        return StateConvergenceWaiter(inspect, timeout_seconds=8.0).wait().configuration_channel
