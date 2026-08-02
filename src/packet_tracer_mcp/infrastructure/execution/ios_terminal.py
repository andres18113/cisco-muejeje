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


_COMMANDS = {
    OperationalQueryId.SHOW_IP_INTERFACE_BRIEF: "show ip interface brief",
    OperationalQueryId.SHOW_INTERFACES_TRUNK: "show interfaces trunk",
}


@dataclass(frozen=True)
class IosCommandResult:
    device_name: str
    query_id: OperationalQueryId
    executed: bool
    output: str = ""
    failure_reason: str = ""
    duration_ms: int = 0


@dataclass(frozen=True)
class InterfaceStatusRow:
    interface: str
    ip_address: str
    status: str
    protocol: str


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


class ControlledIosExecutor:
    """Ejecuta exclusivamente consultas IOS registradas; nunca CLI del usuario."""

    def __init__(self, send_and_wait: Callable[[str, float], str | None]) -> None:
        self._send_and_wait = send_and_wait

    def execute(self, device_name: str, query_id: OperationalQueryId) -> IosCommandResult:
        started = monotonic()
        command = _COMMANDS[query_id]
        name, command_json = json.dumps(device_name), json.dumps(command)
        js = "".join((
            "try{var d=ipc.network().getDevice(", name, ");var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;",
            "if(!t||typeof t.enterCommand!=='function'||typeof t.getOutput!=='function'){reportResult(JSON.stringify({ok:false,reason:'IOS terminal unavailable'}));}",
            "else{var before=String(t.getOutput()).length;t.enterCommand(", command_json, ");",
            "reportResult(JSON.stringify({ok:true,before:before}));}}catch(e){reportResult('ERROR:'+e);}",
        ))
        raw = self._send_and_wait(js, 10.0)
        elapsed = int((monotonic() - started) * 1000)
        if raw is None:
            return IosCommandResult(device_name, query_id, False, failure_reason="IOS command submission timed out.", duration_ms=elapsed)
        if raw.startswith("ERROR:"):
            return IosCommandResult(device_name, query_id, False, failure_reason=raw, duration_ms=elapsed)
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            return IosCommandResult(device_name, query_id, False, failure_reason="IOS terminal returned malformed JSON.", duration_ms=elapsed)
        if not state.get("ok"):
            return IosCommandResult(device_name, query_id, False, failure_reason=str(state.get("reason") or "IOS terminal unavailable."), duration_ms=elapsed)
        baseline = int(state.get("before") or 0)
        def observe() -> dict:
            read_js = "".join((
                "try{var d=ipc.network().getDevice(", name, ");var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;",
                "var o=t&&typeof t.getOutput==='function'?String(t.getOutput()):'';",
                "reportResult(JSON.stringify({found:!!d,configuration_channel:o.length>", str(baseline), ",output:o}));}",
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
        if not convergence.configuration_channel:
            return IosCommandResult(device_name, query_id, False, output=normalize_terminal_output(output), failure_reason="IOS command output did not converge.", duration_ms=elapsed)
        return IosCommandResult(device_name, query_id, True, output=normalize_terminal_output(output), duration_ms=elapsed)
