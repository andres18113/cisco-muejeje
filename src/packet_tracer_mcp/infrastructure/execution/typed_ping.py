"""Ping tipado sobre el terminal correcto con evidencia de la consulta actual."""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic, sleep

from .ios_terminal import extract_terminal_command_window


_PACKET_COUNTS = re.compile(
    r"Packets:\s*Sent\s*=\s*(\d+),\s*Received\s*=\s*(\d+)",
    re.IGNORECASE,
)
_IOS_SUCCESS_RATE = re.compile(
    r"Success rate is\s+(\d+)\s+percent\s+\((\d+)/(\d+)\)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TypedPingResult:
    reachable: bool
    fresh_output_observed: bool
    window_strategy: str = "none"
    failure_reason: str = ""


class TypedPingExecutor:
    """Ejecuta solamente ``ping <ip-validada>``; nunca acepta comandos libres."""

    def __init__(
        self,
        send_and_wait: Callable[[str, float], str | None],
        *,
        timeout_seconds: float = 12.0,
        interval_seconds: float = 0.25,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds < 0
        ):
            raise ValueError("timeout_seconds must be non-negative.")
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or interval_seconds < 0
        ):
            raise ValueError("interval_seconds must be non-negative.")
        self._send_and_wait = send_and_wait
        self._timeout = timeout_seconds
        self._interval = interval_seconds
        self._clock = clock
        self._sleep = sleeper

    def ping(self, source_device: str, destination: str) -> TypedPingResult:
        if not self._valid_device_name(source_device):
            return TypedPingResult(False, False, failure_reason="invalid_source_device")
        try:
            target = str(ipaddress.ip_address(destination))
        except (TypeError, ValueError):
            return TypedPingResult(False, False, failure_reason="invalid_destination")

        source = json.dumps(source_device)
        command = "ping " + target
        started = self._json_result("".join((
            "try{var d=ipc.network().getDevice(", source, ");",
            "var t=null;var kind='';",
            "if(d&&typeof d.getCommandPrompt==='function'){",
            "t=d.getCommandPrompt();if(t){kind='command_prompt';}}",
            "if(!t&&d&&typeof d.getCommandLine==='function'){",
            "t=d.getCommandLine();if(t){kind='ios_command_line';}}",
            "var before=t&&typeof t.getOutput==='function'?String(t.getOutput()):'';",
            "var started=false;if(t&&typeof t.enterCommand==='function'){",
            "t.enterCommand(", json.dumps(command), ");started=true;}",
            "reportResult(JSON.stringify({started:started,before:before,",
            "terminal_kind:kind}));}",
            "catch(e){reportResult('ERROR:'+e);}",
        )), 5.0)
        if not started.get("started"):
            return TypedPingResult(False, False, failure_reason="command_prompt_unavailable")
        before = str(started.get("before") or "")

        def inspect() -> dict:
            return self._json_result("".join((
                "try{var d=ipc.network().getDevice(", source, ");",
                "var t=null;var kind='';",
                "if(d&&typeof d.getCommandPrompt==='function'){",
                "t=d.getCommandPrompt();if(t){kind='command_prompt';}}",
                "if(!t&&d&&typeof d.getCommandLine==='function'){",
                "t=d.getCommandLine();if(t){kind='ios_command_line';}}",
                "reportResult(JSON.stringify({found:!!t,terminal_kind:kind,",
                "output:t?String(t.getOutput()):''}));}",
                "catch(e){reportResult('ERROR:'+e);}",
            )), 3.0)

        deadline = self._clock() + self._timeout
        observed: dict = {}
        window = extract_terminal_command_window(before, "", command)
        while True:
            observed = inspect()
            window = extract_terminal_command_window(
                before, str(observed.get("output") or ""), command,
            )
            normalized = window.output.casefold()
            if (
                "packets: sent" in normalized
                or "success rate is" in normalized
                or self._clock() >= deadline
            ):
                break
            self._sleep(self._interval)

        if not window.fresh:
            return TypedPingResult(
                False,
                False,
                window_strategy=window.strategy,
                failure_reason="no_fresh_ping_result",
            )
        if not window.query_echo_found:
            return TypedPingResult(
                False,
                False,
                window_strategy=window.strategy,
                failure_reason="current_ping_echo_not_observed",
            )
        counts = _PACKET_COUNTS.search(window.output)
        if counts is not None:
            sent, received = int(counts.group(1)), int(counts.group(2))
            if sent > 0 and 0 <= received <= sent:
                return TypedPingResult(
                    reachable=received > 0,
                    fresh_output_observed=True,
                    window_strategy=window.strategy,
                )
        ios = _IOS_SUCCESS_RATE.search(window.output)
        if ios is not None:
            percent, received, sent = map(int, ios.groups())
            if 0 <= percent <= 100 and sent > 0 and 0 <= received <= sent:
                return TypedPingResult(
                    reachable=received > 0,
                    fresh_output_observed=True,
                    window_strategy=window.strategy,
                )
        return TypedPingResult(
            False,
            False,
            window_strategy=window.strategy,
            failure_reason="no_fresh_ping_result",
        )

    def _json_result(self, script: str, timeout: float) -> dict:
        raw = self._send_and_wait(script, timeout)
        if raw is None or raw.startswith(("ERROR:", "PT_ERROR:")):
            return {}
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _valid_device_name(value: str) -> bool:
        return bool(
            isinstance(value, str)
            and value
            and value == value.strip()
            and len(value) <= 128
            and not any(ord(character) < 32 or ord(character) == 127 for character in value)
        )
