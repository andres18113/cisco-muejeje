"""Consultas IOS registradas y lectura operacional sobre TerminalLine."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from time import monotonic
from collections.abc import Callable

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


class TrunkQueryClassification(str, Enum):
    SUPPORTED_WITH_ROWS = "supported_with_rows"
    SUPPORTED_EMPTY = "supported_empty"
    INVALID_COMMAND = "invalid_command"
    UNIMPLEMENTED = "unimplemented"
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
class TerminalOutputWindow:
    output: str
    fresh: bool
    strategy: str
    query_echo_found: bool = False


def normalize_terminal_output(value: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", value).replace("\r\n", "\n").replace("\r", "\n")


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
        truncated_by_pager = "--More--" in window.output
        if truncated_by_pager:
            # PT 9.0.1 rejects ``terminal length 0``. Cancel the documented
            # TerminalLine interaction so a paginated SHOW cannot poison the
            # next registered query. The captured first page remains evidence.
            self._cancel_pager(name)
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

    def _cancel_pager(self, name: str) -> bool:
        js = "try{var d=ipc.network().getDevice(" + name + ");var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;if(!t||typeof t.enterCommand!=='function'){reportResult('{\"ok\":false}');}else{t.enterCommand(String.fromCharCode(3));reportResult('{\"ok\":true}');}}catch(e){reportResult('ERROR:'+e);}"
        return self._send_and_wait(js, 5.0) == '{"ok":true}'

    def _prepare_session(self, name: str) -> IosSessionState:
        state = self._terminal_state(name)
        if not state.get("found") or not state.get("terminal"):
            return IosSessionState.FAILED
        if state.get("booting") is True:
            return IosSessionState.WAITING_FOR_BOOT
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
