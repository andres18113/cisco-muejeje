"""Espera acotada del ciclo de vida de devices temporales de Packet Tracer."""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic, sleep

from ...domain.enterprise.models.discovery import (
    DeviceInitializationResult,
    DeviceInitializationState,
)


class DeviceReadinessWaiter:
    """Hace polling con presupuesto; no usa sleeps arbitrarios ni espera infinita.

    `timeout_seconds` is this waiter's own budget, measured once from its own
    start. `remaining_seconds` is the optional control a caller that owns a
    SHORTER budget injects, and it is re-read on every turn rather than
    snapshotted: a caller's allowance can be spent while this loop is running,
    and a snapshot taken before that happened keeps polling a channel that can
    no longer answer. When the control reports nothing left, the wait ends
    immediately and without sleeping -- waiting longer cannot change an answer
    that nothing is allowed to produce. A waiter with no control behaves
    exactly as it did before, which is what ordinary boot and ungated IOS
    waits rely on.
    """

    def __init__(
        self,
        inspect: Callable[[], dict],
        *,
        timeout_seconds: float = 8.0,
        interval_seconds: float = 0.25,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
        remaining_seconds: Callable[[], float] | None = None,
    ) -> None:
        """Bind one bounded poll to its clock, sleeper and optional control."""
        self._inspect = inspect
        self._timeout = timeout_seconds
        self._interval = interval_seconds
        self._clock = clock
        self._sleep = sleeper
        self._remaining_seconds = remaining_seconds

    def _control_allowance(self) -> float:
        """Return the caller's remaining allowance, or an unbounded one."""
        if self._remaining_seconds is None:
            return float("inf")
        try:
            return float(self._remaining_seconds())
        except Exception:
            # A control that cannot be read is not permission to keep polling.
            return 0.0

    def _expired(self, started: float, allowance: float) -> bool:
        """Return whether either this waiter's budget or the caller's is spent."""
        return self._clock() - started >= self._timeout or allowance <= 0

    def _rest(self, allowance: float) -> None:
        """Sleep one interval, never past the caller's remaining allowance."""
        self._sleep(min(self._interval, allowance))

    def wait(self) -> DeviceInitializationResult:
        """Poll until the configuration channel answers, or the budget ends."""
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
                return self._result(
                    DeviceInitializationState.CONFIGURATION_READY,
                    started,
                    attempts,
                    last,
                )
            allowance = self._control_allowance()
            if self._expired(started, allowance):
                state = (
                    DeviceInitializationState.TIMEOUT
                    if last.get("found")
                    else DeviceInitializationState.NOT_FOUND
                )
                return self._result(state, started, attempts, last)
            self._rest(allowance)

    def _result(
        self,
        state: DeviceInitializationState,
        started: float,
        attempts: int,
        value: dict,
    ) -> DeviceInitializationResult:
        return DeviceInitializationResult(
            state=state,
            attempts=attempts,
            elapsed_ms=int((self._clock() - started) * 1000),
            power=value.get("power"),
            command_prompt=bool(value.get("command_prompt")),
            terminal_available=bool(value.get("terminal_available")),
            terminal_kind=str(value.get("terminal_kind") or "unavailable"),
            booting=value.get("booting"),
            configuration_channel=bool(value.get("configuration_channel")),
            components_seen=list(value.get("components_seen") or []),
            failure_reason=str(value.get("failure_reason") or ""),
        )


class StateConvergenceWaiter:
    """Espera la lectura independiente de una mutacion ya enviada a PT."""

    def __init__(
        self,
        inspect: Callable[[], dict],
        *,
        timeout_seconds: float = 8.0,
        interval_seconds: float = 0.25,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
        remaining_seconds: Callable[[], float] | None = None,
    ) -> None:
        """Bind the same bounded poll to one already dispatched mutation."""
        self._readiness = DeviceReadinessWaiter(
            inspect,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
            clock=clock,
            sleeper=sleeper,
            remaining_seconds=remaining_seconds,
        )

    def wait(self) -> DeviceInitializationResult:
        """Return the bounded readiness reading of that mutation."""
        return self._readiness.wait()


class DeviceOperationalReadinessWaiter(DeviceReadinessWaiter):
    """Espera un terminal elegido por tipo y el fin de arranque de PT."""

    def wait(self) -> DeviceInitializationResult:
        """Poll until a terminal is available and boot ended, or time out."""
        started = self._clock()
        attempts = 0
        last: dict = {}
        while True:
            attempts += 1
            try:
                last = self._inspect()
            except Exception as exc:
                last = {"found": False, "failure_reason": str(exc)}
            if last.get("terminal_available") and last.get("booting") is not True:
                return self._result(
                    DeviceInitializationState.OPERATIONAL_READY, started, attempts, last
                )
            allowance = self._control_allowance()
            if self._expired(started, allowance):
                state = (
                    DeviceInitializationState.TIMEOUT
                    if last.get("found")
                    else DeviceInitializationState.NOT_FOUND
                )
                return self._result(state, started, attempts, last)
            self._rest(allowance)


class IosBootWaiter(DeviceOperationalReadinessWaiter):
    """Espera el boot IOS con presupuesto propio, separado de una query SHOW."""

    def __init__(
        self,
        inspect: Callable[[], dict],
        *,
        timeout_seconds: float = 90.0,
        **kwargs,
    ) -> None:
        """Bind the IOS boot wait to its own, longer default budget."""
        super().__init__(inspect, timeout_seconds=timeout_seconds, **kwargs)
