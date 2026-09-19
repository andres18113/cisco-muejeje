"""The port through which an opaque credential reference becomes a value.

Plans, hashes, journals, records and responses carry `secret_ref` strings
only. A value exists in this process for one purpose -- building the script
that needs it -- and the type that carries it never shows it: `repr`, `str`
and formatting all render a placeholder, so a value that reaches a log line or
an exception by accident still says nothing.
"""

from __future__ import annotations

from typing import Protocol

_PLACEHOLDER = "SecretValue(<redacted>)"


class SecretUnavailable(LookupError):
    """Raised when a reference cannot be resolved; it never carries a value.

    `reason` is the typed category a caller acts on: `invalid_reference`,
    `not_set` or `too_short`. The message names the reference, which is an
    opaque identifier, and nothing else.
    """

    def __init__(self, reference: str, reason: str) -> None:
        """Record the reference and the category, never a value."""
        super().__init__(f"secret reference {reference!r} is unavailable: {reason}")
        self.reference = reference
        self.reason = reason


class SecretValue:
    """One resolved credential. Only `reveal()` returns the value."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        """Hold the value without exposing it through any representation."""
        self._value = value

    def reveal(self) -> str:
        """Return the value, for the one script that serializes it."""
        return self._value

    def __repr__(self) -> str:
        """Render a placeholder instead of the value."""
        return _PLACEHOLDER

    def __str__(self) -> str:
        """Render a placeholder instead of the value."""
        return _PLACEHOLDER

    def __format__(self, format_spec: str) -> str:
        """Render a placeholder instead of the value."""
        return _PLACEHOLDER


class SecretResolver(Protocol):
    """Resolve one opaque reference into its value, or refuse with a category."""

    def resolve(self, secret_ref: str) -> SecretValue:
        """Return the value, or raise `SecretUnavailable`."""
