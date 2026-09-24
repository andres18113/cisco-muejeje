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


#: Title fragments that name a Packet Tracer document on disk.
_DOCUMENT_MARKERS = (".pkt", ".pka", ".pkz", ".pksz", "\\", "/")


def launched_blank(launch: Mapping[str, object]) -> bool:
    """Whether the launch record proves a new, unnamed document at start.

    It reads only what the CLI itself observed from the operating system when
    it recorded the launch (`observed_command_line`, `observed_main_window_
    title`), never what a capture claimed. The process must have been started
    with no argument besides its own executable, so the launch opened no
    document, and its main window title must be non-empty and name no file.
    """
    title = launch.get("observed_main_window_title")
    command = launch.get("observed_command_line")
    path = launch.get("process_path")
    if not (
        isinstance(title, str)
        and title
        and isinstance(command, str)
        and isinstance(path, str)
        and path
    ):
        return False
    if any(marker in title.casefold() for marker in _DOCUMENT_MARKERS):
        return False
    return command.strip() in {path, f'"{path}"'}


def observed_process_findings(
    launch: Mapping[str, object], observed: object
) -> tuple[str, ...]:
    """Compare one fresh OS observation of the owned PID with its launch.

    `observed` carries `process_id`, `present`, `process_path`,
    `process_incarnation`, `command_line`, `main_window_title` and `error`.
    Any difference, and any unreadable or absent process, is a finding: the
    caller then performs no close or termination on that reading.
    """
    if getattr(observed, "error", ""):
        return ("process_unobservable",)
    if getattr(observed, "present", False) is not True:
        return ("process_absent",)
    found: list[str] = []
    if (
        getattr(observed, "process_id", None),
        getattr(observed, "process_path", None),
        getattr(observed, "process_incarnation", None),
    ) != (
        launch.get("pid"),
        launch.get("process_path"),
        launch.get("process_incarnation"),
    ):
        found.append("process_identity_changed")
    if getattr(observed, "command_line", None) != launch.get("observed_command_line"):
        found.append("process_command_line_changed")
    if getattr(observed, "main_window_title", None) != launch.get(
        "observed_main_window_title"
    ):
        # Auxiliary: an unchanged title proves nothing alone, but a changed
        # one is conflicting document evidence and stops any force.
        found.append("process_document_title_changed")
    if not launched_blank(launch):
        found.append("launch_does_not_prove_blank_document")
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

    A force is admissible only as the retirement flow records it: the fresh
    OS reading taken just before it matched the launch's observed identity,
    command line and title (`observed_process_findings`), the launch proved a
    new unnamed document (`launched_blank`), and a durable ownership basis for
    the workspace was established from the campaign's own records. The title
    is auxiliary evidence; it never authorizes a force by itself.
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
            or not isinstance(forced.get("ownership_basis"), str)
            or not forced.get("ownership_basis")
            or not launched_blank(launch)
            or forced.get("rechecked_command_line")
            != launch.get("observed_command_line")
            or forced.get("rechecked_window_title")
            != launch.get("observed_main_window_title")
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
