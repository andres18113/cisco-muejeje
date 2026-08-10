"""Explicit health and selection contracts for Packet Tracer transports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TransportName(str, Enum):
    HTTP = "http"
    FILE = "file"


class TransportHealthState(str, Enum):
    TRANSPORT_UP = "TRANSPORT_UP"
    POLLING = "POLLING"
    COMMAND_PATH_RESPONSIVE = "COMMAND_PATH_RESPONSIVE"
    DEGRADED = "DEGRADED"
    UNRESPONSIVE = "UNRESPONSIVE"


@dataclass(frozen=True)
class TransportHealth:
    """Layered evidence for one transport.

    ``transport_up`` only proves the local bridge/mailbox exists. ``polling``
    proves Packet Tracer is consuming that channel.  A matching command probe is
    the only evidence that the complete command/result path is responsive.
    """

    transport: TransportName
    transport_up: bool
    polling: bool
    command_path_responsive: bool
    command_probe_attempted: bool = True
    detail: str = ""

    @property
    def state(self) -> TransportHealthState:
        if self.command_path_responsive:
            return TransportHealthState.COMMAND_PATH_RESPONSIVE
        if self.polling:
            return (
                TransportHealthState.DEGRADED
                if self.command_probe_attempted
                else TransportHealthState.POLLING
            )
        if self.transport_up:
            return TransportHealthState.TRANSPORT_UP
        return TransportHealthState.UNRESPONSIVE

    @property
    def observed_states(self) -> tuple[TransportHealthState, ...]:
        states: list[TransportHealthState] = []
        if self.transport_up:
            states.append(TransportHealthState.TRANSPORT_UP)
        if self.polling:
            states.append(TransportHealthState.POLLING)
        if self.command_path_responsive:
            states.append(TransportHealthState.COMMAND_PATH_RESPONSIVE)
        elif self.polling and self.command_probe_attempted:
            states.append(TransportHealthState.DEGRADED)
        if not states:
            states.append(TransportHealthState.UNRESPONSIVE)
        return tuple(states)

    @property
    def selectable(self) -> bool:
        # During operation selection a command probe is deliberately not sent;
        # an active poll/heartbeat is the best non-mutating routing signal.  If
        # a probe was attempted, only its successful round-trip is selectable.
        if self.command_probe_attempted:
            return self.command_path_responsive
        return self.polling


@dataclass(frozen=True)
class TransportSelection:
    selected: TransportName | None
    fallback: TransportName | None
    reason: str
    pinned_for_operation: bool = True
    silent_replay_allowed: bool = False


def select_transport(
    http: TransportHealth,
    file: TransportHealth,
    *,
    preferred: TransportName = TransportName.HTTP,
) -> TransportSelection:
    """Choose once for an operation and disclose any viable fallback.

    The fallback is informational.  A caller must start a new operation after a
    failure; this result never authorizes replaying an ambiguous mutation.
    """

    by_name = {TransportName.HTTP: http, TransportName.FILE: file}
    other = TransportName.FILE if preferred is TransportName.HTTP else TransportName.HTTP
    preferred_health = by_name[preferred]
    other_health = by_name[other]
    if preferred_health.selectable:
        return TransportSelection(
            selected=preferred,
            fallback=other if other_health.selectable else None,
            reason="preferred transport is selectable",
        )
    if other_health.selectable:
        return TransportSelection(
            selected=other,
            fallback=None,
            reason=(
                preferred.value
                + " is "
                + preferred_health.state.value
                + "; selected explicit fallback"
            ),
        )
    return TransportSelection(
        selected=None,
        fallback=None,
        reason=(
            "no selectable command path: http="
            + http.state.value
            + ", file="
            + file.state.value
        ),
    )


def format_transport_health(health: TransportHealth) -> list[str]:
    trace = " -> ".join(state.value for state in health.observed_states)
    return [
        "state=" + health.state.value,
        "observed_states=" + trace,
        "transport_up=" + str(health.transport_up).lower(),
        "polling=" + str(health.polling).lower(),
        "command_path_responsive=" + str(health.command_path_responsive).lower(),
    ]
