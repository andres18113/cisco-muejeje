"""Consultas IOS registradas y lectura operacional sobre TerminalLine."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from time import monotonic
from collections.abc import Callable

from .device_lifecycle import StateConvergenceWaiter


class OperationalQueryId(str, Enum):
    SHOW_IP_INTERFACE_BRIEF = "show_ip_interface_brief"
    SHOW_INTERFACES_TRUNK = "show_interfaces_trunk"


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
}
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


@dataclass(frozen=True)
class InterfaceStatusRow:
    interface: str
    ip_address: str
    status: str
    protocol: str


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

    def execute(self, device_name: str, query_id: OperationalQueryId) -> IosCommandResult:
        started = monotonic()
        command = _COMMANDS[query_id]
        name, command_json = json.dumps(device_name), json.dumps(command)
        session = self._prepare_session(name)
        if session is not IosSessionState.EXEC_PROMPT_READY:
            return IosCommandResult(device_name, query_id, False, failure_reason="IOS session state: " + session.value, duration_ms=int((monotonic() - started) * 1000), session_state=session)
        js = "".join((
            "try{var d=ipc.network().getDevice(", name, ");var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;",
            "if(!t||typeof t.enterCommand!=='function'||typeof t.getOutput!=='function'){reportResult(JSON.stringify({ok:false,reason:'IOS terminal unavailable'}));}",
            "else{var before=String(t.getOutput());t.enterCommand(", command_json, ");",
            "reportResult(JSON.stringify({ok:true,before:before}));}}catch(e){reportResult('ERROR:'+e);}",
        ))
        raw = self._send_and_wait(js, 10.0)
        elapsed = int((monotonic() - started) * 1000)
        if raw is None:
            return IosCommandResult(device_name, query_id, False, failure_reason="IOS command submission timed out.", duration_ms=elapsed, session_state=session)
        if raw.startswith("ERROR:"):
            return IosCommandResult(device_name, query_id, False, failure_reason=raw, duration_ms=elapsed, session_state=session)
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            return IosCommandResult(device_name, query_id, False, failure_reason="IOS terminal returned malformed JSON.", duration_ms=elapsed, session_state=session)
        if not state.get("ok"):
            return IosCommandResult(device_name, query_id, False, failure_reason=str(state.get("reason") or "IOS terminal unavailable."), duration_ms=elapsed, session_state=session)
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
        if not convergence.configuration_channel:
            return IosCommandResult(device_name, query_id, False, output=normalize_terminal_output(window.output), failure_reason="IOS command output did not converge.", duration_ms=elapsed, session_state=session, fresh_output_observed=window.fresh, window_strategy=window.strategy)
        if not window.fresh:
            return IosCommandResult(device_name, query_id, False, failure_reason="No fresh current-command output window was observed.", duration_ms=elapsed, session_state=session, window_strategy=window.strategy)
        return IosCommandResult(device_name, query_id, True, output=normalize_terminal_output(window.output), duration_ms=elapsed, session_state=session, fresh_output_observed=True, window_strategy=window.strategy)

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
        js = "try{var d=ipc.network().getDevice(" + name + ");var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;reportResult(JSON.stringify({found:!!d,booting:d&&typeof d.isBooting==='function'?!!d.isBooting():null,terminal:!!t,prompt:t&&typeof t.getPrompt==='function'?String(t.getPrompt()):'',output:t&&typeof t.getOutput==='function'?String(t.getOutput()):''}));}catch(e){reportResult('ERROR:'+e);}"
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
