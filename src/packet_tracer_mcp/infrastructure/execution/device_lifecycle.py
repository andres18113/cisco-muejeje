"""Espera acotada del ciclo de vida de devices temporales de Packet Tracer."""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic, sleep

from ...domain.enterprise.models.discovery import DeviceInitializationResult, DeviceInitializationState


class DeviceReadinessWaiter:
    """Hace polling con presupuesto; no usa sleeps arbitrarios ni espera infinita."""

    def __init__(
        self,
        inspect: Callable[[], dict],
        *,
        timeout_seconds: float = 8.0,
        interval_seconds: float = 0.25,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._inspect = inspect
        self._timeout = timeout_seconds
        self._interval = interval_seconds
        self._clock = clock
        self._sleep = sleeper

    def wait(self) -> DeviceInitializationResult:
        started = self._clock()
        attempts = 0
        last: dict = {}
        while True:
            attempts += 1
            try:
                last = self._inspect()
            except Exception as exc:
                last = {"found": False, "failure_reason": str(exc)}
            if last.get("configuration_channel"):
                return self._result(DeviceInitializationState.CONFIGURATION_READY, started, attempts, last)
            if self._clock() - started >= self._timeout:
                state = DeviceInitializationState.TIMEOUT if last.get("found") else DeviceInitializationState.NOT_FOUND
                return self._result(state, started, attempts, last)
            self._sleep(self._interval)

    def _result(
        self, state: DeviceInitializationState, started: float, attempts: int, value: dict,
    ) -> DeviceInitializationResult:
        return DeviceInitializationResult(
            state=state,
            attempts=attempts,
            elapsed_ms=int((self._clock() - started) * 1000),
            power=value.get("power"),
            command_prompt=bool(value.get("command_prompt")),
            configuration_channel=bool(value.get("configuration_channel")),
            components_seen=list(value.get("components_seen") or []),
            failure_reason=str(value.get("failure_reason") or ""),
        )
