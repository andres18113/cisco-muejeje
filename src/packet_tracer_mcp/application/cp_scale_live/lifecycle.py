"""Terminal obligations and precedence, independent of topology policy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


class SessionClosePort(Protocol):
    def close(self) -> None: ...


@dataclass(frozen=True)
class FinalizationResult:
    errors: tuple[str, ...] = ()


def report_terminal_errors(errors: tuple[str, ...], report: Callable[[tuple[str, ...]], None]) -> tuple[str, ...]:
    """A failed report is a secondary; never a replacement exception."""
    try:
        report(errors)
    except Exception as exc:
        return (*errors, f"finalization_report: {type(exc).__name__}: {exc}")
    return errors


def finalize_session(
    *,
    prepare: Callable[[], None],
    write: Callable[[], None],
    session: SessionClosePort,
    report: Callable[[tuple[str, ...]], None],
    secondary_failures: Callable[[], tuple[str, ...]] = lambda: (),
    defer_report: bool = False,
) -> FinalizationResult:
    """Always attempt close; a cancellation remains an exception in flight.

    The owner of each obligation supplies its operation. This mechanism cannot
    decide cleanup, retention, or acceptance, and it never retries an operation.
    """
    errors: list[str] = []
    interrupted = False
    try:
        prepare()
        try:
            write()
        except Exception as exc:
            errors.append(f"final_evidence_write: {type(exc).__name__}: {exc}")
    except Exception as exc:
        errors.append(f"finalization: {type(exc).__name__}: {exc}")
    except BaseException:
        interrupted = True
        raise
    finally:
        try:
            try:
                session.close()
            except Exception as exc:
                errors.append(f"transport_stop: {type(exc).__name__}: {exc}")
            except BaseException:
                interrupted = True
                raise
        finally:
            errors = [*secondary_failures(), *errors]
            if errors and (not defer_report or interrupted):
                errors = list(report_terminal_errors(tuple(errors), report))
    return FinalizationResult(tuple(errors))
