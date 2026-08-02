"""Preflight acotado para operaciones que requieren el bridge de Packet Tracer."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar


class BridgePreflightState(str, Enum):
    READY = "READY"
    MCP_SERVER_NOT_READY = "MCP_SERVER_NOT_READY"
    BRIDGE_START_FAILED = "BRIDGE_START_FAILED"
    BRIDGE_START_TIMEOUT = "BRIDGE_START_TIMEOUT"
    BRIDGE_TOKEN_MISSING = "BRIDGE_TOKEN_MISSING"


@dataclass(frozen=True)
class BridgePreflightResult:
    state: BridgePreflightState
    attempts: int = 0

    @property
    def ready(self) -> bool:
        return self.state is BridgePreflightState.READY

    def render(self) -> str:
        messages = {
            BridgePreflightState.MCP_SERVER_NOT_READY:
                "El servidor MCP no está listo para iniciar el bridge.",
            BridgePreflightState.BRIDGE_START_FAILED:
                "No se pudo iniciar el bridge oficial de Packet Tracer.",
            BridgePreflightState.BRIDGE_START_TIMEOUT:
                "El bridge inició, pero Packet Tracer no se conectó dentro del tiempo de espera.",
            BridgePreflightState.BRIDGE_TOKEN_MISSING:
                "El bridge está disponible, pero MCP Control Center no tiene un token persistido válido.",
        }
        return f"{self.state.value}: {messages.get(self.state, 'Bridge listo.')}"


T = TypeVar("T")


class BridgeReadinessPreflight:
    """Reutiliza el bootstrap oficial y no crea tokens ni bridges alternativos."""

    def __init__(
        self,
        mcp_server_ready: Callable[[], bool],
        bridge_ready: Callable[[], bool],
        bootstrap_bridge: Callable[[], bool],
        token_ready: Callable[[], bool],
        *,
        timeout_s: float = 5.0,
        poll_interval_s: float = 0.2,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._mcp_server_ready = mcp_server_ready
        self._bridge_ready = bridge_ready
        self._bootstrap_bridge = bootstrap_bridge
        self._token_ready = token_ready
        self._timeout_s = max(0.0, timeout_s)
        self._poll_interval_s = max(0.01, poll_interval_s)
        self._monotonic = monotonic
        self._sleep = sleep

    def ensure_ready(self) -> BridgePreflightResult:
        if not self._mcp_server_ready():
            return BridgePreflightResult(BridgePreflightState.MCP_SERVER_NOT_READY)

        if self._bridge_ready():
            return self._result_for_token(attempts=0)

        # Esta callable debe ser _ensure_bridge() del registry: es el único
        # responsable de crear PTCommandBridge y de obtener su token.
        if not self._bootstrap_bridge():
            return BridgePreflightResult(BridgePreflightState.BRIDGE_START_FAILED)

        deadline = self._monotonic() + self._timeout_s
        attempts = 0
        while True:
            attempts += 1
            if self._bridge_ready():
                return self._result_for_token(attempts=attempts)
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                return BridgePreflightResult(BridgePreflightState.BRIDGE_START_TIMEOUT, attempts)
            self._sleep(min(self._poll_interval_s, remaining))

    def execute_if_ready(self, action: Callable[[], T]) -> tuple[BridgePreflightResult, T | None]:
        """Impide que una operación mutante alcance Packet Tracer sin readiness."""
        result = self.ensure_ready()
        return (result, action()) if result.ready else (result, None)

    def _result_for_token(self, attempts: int) -> BridgePreflightResult:
        state = BridgePreflightState.READY if self._token_ready() else BridgePreflightState.BRIDGE_TOKEN_MISSING
        return BridgePreflightResult(state, attempts)
