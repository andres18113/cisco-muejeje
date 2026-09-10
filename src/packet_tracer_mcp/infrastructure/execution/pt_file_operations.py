"""Observed authority boundary for Packet Tracer workspace file operations."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from threading import Lock
from typing import Generic, TypeVar


_T = TypeVar("_T")


class PacketTracerFileOperationDenied(RuntimeError):
    """Raised before an unauthorized Packet Tracer file operation can run."""


@dataclass(frozen=True)
class PacketTracerFileOperationResult(Generic[_T]):
    """Callback value plus explicit observation of external completion."""

    value: _T
    completion_observed: bool

    def __post_init__(self) -> None:
        if type(self.completion_observed) is not bool:
            raise TypeError("completion_observed must be an exact boolean.")


@dataclass(frozen=True)
class PacketTracerFileOperationLedger:
    """Immutable observation of policy and calls crossing the PT-file boundary."""

    authorized_operations: tuple[str, ...]
    attempted_operations: tuple[str, ...]
    denied_operations: tuple[str, ...]
    invoked_operations: tuple[str, ...]
    completed_operations: tuple[str, ...]
    indeterminate_operations: tuple[str, ...]

    @property
    def ephemeral_safe(self) -> bool:
        """An ephemeral workspace authorizes and observes exactly no file calls."""

        return (
            self.authorized_operations == ()
            and self.attempted_operations == ()
            and self.denied_operations == ()
            and self.invoked_operations == ()
            and self.completed_operations == ()
            and self.indeterminate_operations == ()
        )


class PacketTracerFileOperationGuard:
    """Record every typed PT-file request before enforcing its authority policy.

    Governed callers must put the actual Packet Tracer operation in ``action``.
    The attempt is recorded before policy is checked, and an authorized dispatch
    is recorded before the callback starts. Completion requires an explicit
    receipt; an exception or untyped return records an indeterminate result
    because an external effect may already have occurred.
    """

    def __init__(self, *, authorized_operations: Iterable[str]) -> None:
        authorized = tuple(sorted(set(authorized_operations)))
        if any(not _exact_operation(operation) for operation in authorized):
            raise ValueError("Packet Tracer file-operation policy is malformed.")
        self._authorized_operations = authorized
        self._attempted_operations: list[str] = []
        self._denied_operations: list[str] = []
        self._invoked_operations: list[str] = []
        self._completed_operations: list[str] = []
        self._indeterminate_operations: list[str] = []
        self._lock = Lock()

    @classmethod
    def ephemeral(cls) -> PacketTracerFileOperationGuard:
        """Create the fail-closed empty policy for an untitled workspace."""

        return cls(authorized_operations=())

    def attempt(
        self,
        operation: str,
        action: Callable[[], PacketTracerFileOperationResult[_T]],
    ) -> _T:
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
            self._invoked_operations.append(operation)
        try:
            result = action()
        except BaseException:
            with self._lock:
                self._indeterminate_operations.append(operation)
            raise
        if not isinstance(result, PacketTracerFileOperationResult):
            with self._lock:
                self._indeterminate_operations.append(operation)
            raise TypeError(
                "Packet Tracer file callback returned no explicit completion receipt."
            )
        with self._lock:
            target = (
                self._completed_operations
                if result.completion_observed
                else self._indeterminate_operations
            )
            target.append(operation)
        return result.value

    def snapshot(self) -> PacketTracerFileOperationLedger:
        """Return one coherent immutable ledger observation."""

        with self._lock:
            return PacketTracerFileOperationLedger(
                authorized_operations=self._authorized_operations,
                attempted_operations=tuple(self._attempted_operations),
                denied_operations=tuple(self._denied_operations),
                invoked_operations=tuple(self._invoked_operations),
                completed_operations=tuple(self._completed_operations),
                indeterminate_operations=tuple(self._indeterminate_operations),
            )


def _exact_operation(operation: object) -> bool:
    return (
        type(operation) is str
        and bool(operation)
        and operation == operation.strip()
    )
