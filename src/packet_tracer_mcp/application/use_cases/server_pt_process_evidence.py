"""Pure ownership and process-exit evidence rules for Server-PT campaigns."""

from __future__ import annotations

from collections.abc import Mapping

from ...domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
)
from .prepare_server_pt_commissioning import SERVER_PT_BUILD


def launch_evidence_findings(
    launch: Mapping[str, object], process: DiagnosticLifecycleObservation
) -> tuple[str, ...]:
    """Bind the campaign's owned launch to the fresh OS process reading."""
    found: list[str] = []
    if (
        process.error
        or not process.process_id
        or not process.process_path
        or not process.process_incarnation
        or launch.get("pid") != process.process_id
        or launch.get("process_path") != process.process_path
        or launch.get("process_incarnation") != process.process_incarnation
    ):
        found.append("foreign_launch_identity")
    if (
        launch.get("created_by_campaign") is not True
        or launch.get("workspace_kind") != "disposable_declared"
        or launch.get("launch_method") != "Start-Process"
    ):
        found.append("campaign_creation_unproven")
    if SERVER_PT_BUILD not in (process.product_version, process.file_version):
        found.append("process_build_mismatch")
    return tuple(found)


#: The longest graceful wait a forced termination may follow. A capture that
#: claims a longer or no wait did not bound its graceful attempt.
FORCED_TERMINATION_MAX_GRACEFUL_WAIT_SECONDS = 120.0


def exit_was_forced(close: Mapping[str, object]) -> bool:
    """Whether a close capture records an exact-process termination."""
    return close.get("forced_termination") is not None


def exit_evidence_findings(
    launch: Mapping[str, object],
    close: Mapping[str, object],
    *,
    process_count: int | None,
    allow_forced: bool = False,
) -> tuple[str, ...]:
    """Require graceful request and actual exit of exactly the owned process.

    A forced termination is admissible only where the caller's campaign
    allows it (`allow_forced`), and only as its own record: the graceful
    request still had to be made and bounded, the termination names the same
    PID, path and creation time as the launch after rechecking them, and the
    exit is still observed independently. It is never read as graceful.

    "No valuable user state" is rechecked, not assumed: the main window
    title at termination must equal the non-empty title the launch captured
    for its declared new blank document. Opening or saving any file changes
    that title, so a user document in the owned process refuses the force.
    """
    found: list[str] = []
    forced = close.get("forced_termination")
    if forced is not None:
        wait = close.get("graceful_wait_seconds")
        if not allow_forced:
            found.append("forced_termination_not_permitted")
        elif (
            not isinstance(forced, Mapping)
            or forced.get("method") != "Stop-Process"
            or forced.get("pid") != launch.get("pid")
            or forced.get("rechecked_process_path") != launch.get("process_path")
            or forced.get("rechecked_process_incarnation")
            != launch.get("process_incarnation")
            or forced.get("disposable_workspace_rechecked") is not True
            or not isinstance(launch.get("main_window_title"), str)
            or not launch.get("main_window_title")
            or forced.get("rechecked_window_title") != launch.get("main_window_title")
            or not isinstance(forced.get("requested_at_utc"), str)
            or isinstance(wait, bool)
            or not isinstance(wait, (int, float))
            or not 0 < wait <= FORCED_TERMINATION_MAX_GRACEFUL_WAIT_SECONDS
        ):
            found.append("forced_termination_identity_unproven")
    if (
        close.get("pid") != launch.get("pid")
        or close.get("process_path") != launch.get("process_path")
        or close.get("process_incarnation") != launch.get("process_incarnation")
        or close.get("method") != "CloseMainWindow"
        or close.get("requested") is not True
    ):
        found.append("graceful_close_identity_unproven")
    if (
        isinstance(process_count, bool)
        or process_count != 0
        or close.get("actual_exit_observed") is not True
    ):
        found.append("process_exit_unobserved")
    return tuple(found)
