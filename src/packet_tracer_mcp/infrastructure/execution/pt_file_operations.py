"""Observed authority boundary for Packet Tracer workspace file operations."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from threading import Lock
from typing import TypeVar


_T = TypeVar("_T")


class PacketTracerFileOperationDenied(RuntimeError):
    """Raised before an unauthorized Packet Tracer file operation can run."""


@dataclass(frozen=True)
class PacketTracerFileOperationLedger:
    """Immutable observation of policy and calls crossing the PT-file boundary."""

    authorized_operations: tuple[str, ...]
    attempted_operations: tuple[str, ...]
    executed_operations: tuple[str, ...]
    denied_operations: tuple[str, ...]

    @property
    def ephemeral_safe(self) -> bool:
        """An ephemeral workspace authorizes and observes exactly no file calls."""

        return (
            self.authorized_operations == ()
            and self.attempted_operations == ()
            and self.executed_operations == ()
            and self.denied_operations == ()
        )


class PacketTracerFileOperationGuard:
    """Record every typed PT-file request before enforcing its authority policy.

    Governed callers must put the actual Packet Tracer operation in ``action``.
    The attempt is recorded before policy is checked, and an authorized dispatch
    is recorded before the callback starts because the callback may fail after a
    partial external side effect.
    """

    def __init__(self, *, authorized_operations: Iterable[str]) -> None:
        authorized = tuple(sorted(set(authorized_operations)))
        if any(not _exact_operation(operation) for operation in authorized):
            raise ValueError("Packet Tracer file-operation policy is malformed.")
        self._authorized_operations = authorized
        self._attempted_operations: list[str] = []
        self._executed_operations: list[str] = []
        self._denied_operations: list[str] = []
        self._lock = Lock()

    @classmethod
    def ephemeral(cls) -> PacketTracerFileOperationGuard:
        """Create the fail-closed empty policy for an untitled workspace."""

        return cls(authorized_operations=())

    def attempt(self, operation: str, action: Callable[[], _T]) -> _T:
        """Observe one request and execute it only when policy authorizes it."""

        if not _exact_operation(operation):
            raise ValueError("Packet Tracer file-operation identity is malformed.")
        if not callable(action):
            raise TypeError("Packet Tracer file-operation action must be callable.")
        with self._lock:
            self._attempted_operations.append(operation)
            if operation not in self._authorized_operations:
                self._denied_operations.append(operation)
                raise PacketTracerFileOperationDenied(
                    f"Packet Tracer file operation denied by policy: {operation}"
                )
            self._executed_operations.append(operation)
        return action()

    def snapshot(self) -> PacketTracerFileOperationLedger:
        """Return one coherent immutable ledger observation."""

        with self._lock:
            return PacketTracerFileOperationLedger(
                authorized_operations=self._authorized_operations,
                attempted_operations=tuple(self._attempted_operations),
                executed_operations=tuple(self._executed_operations),
                denied_operations=tuple(self._denied_operations),
            )


def _exact_operation(operation: object) -> bool:
    return (
        type(operation) is str
        and bool(operation)
        and operation == operation.strip()
    )
