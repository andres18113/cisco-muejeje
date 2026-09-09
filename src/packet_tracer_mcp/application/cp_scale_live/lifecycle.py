"""Terminal obligations and precedence, independent of topology policy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


class SessionClosePort(Protocol):
    def close(self) -> None: ...


@dataclass(frozen=True)
class FinalizationResult:
    errors: tuple[str, ...] = ()

def finalize_session(
    *,
    prepare: Callable[[], None],
    write: Callable[[], None],
    session: SessionClosePort,
    report: Callable[[tuple[str, ...]], None],
) -> FinalizationResult:
    """Always attempt close; a cancellation remains an exception in flight.

    The owner of each obligation supplies its operation. This mechanism cannot
    decide cleanup, retention, or acceptance, and it never retries an operation.
    """
    errors: list[str] = []
    try:
        prepare()
        try:
            write()
        except Exception as exc:
            errors.append(f"final_evidence_write: {type(exc).__name__}: {exc}")
    except Exception as exc:
        errors.append(f"finalization: {type(exc).__name__}: {exc}")
    finally:
        try:
            try:
                session.close()
            except Exception as exc:
                errors.append(f"transport_stop: {type(exc).__name__}: {exc}")
        finally:
            if errors:
                report(tuple(errors))
    return FinalizationResult(tuple(errors))
