"""Pure ownership and process-exit evidence rules for Server-PT campaigns."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone

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
    `process_incarnation`, `command_line` and `error`. Any difference, and
    any unreadable or absent process, is a finding: the caller then performs
    no close or termination on that reading.

    The main window title is deliberately not compared. Packet Tracer with
    the extension shows two unowned top-level windows, and which one .NET
    calls "main" follows focus and enumeration order; document evidence comes
    from the window census (`select_document_window`) instead.
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
    if not launched_blank(launch):
        found.append("launch_does_not_prove_blank_document")
    return tuple(found)


#: The Script Engine extension's own window. On 9.0.1.0858 it is a second
#: visible, unowned top-level window of the Packet Tracer process (FASTLOOP
#: episode 1). It is never a close target and never evidence about a document.
EXTENSION_LOG_WINDOW_TITLE = "Logs - MCP BUILDER"


_INCARNATION = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,7}))?"
    r"(Z|[+-]\d{2}:\d{2})\Z"
)
_TICKS_EPOCH = datetime(1, 1, 1, tzinfo=UTC)


def incarnation_ticks(value: object) -> int | None:
    """Convert an ISO creation time to UTC .NET ticks, exactly, or `None`.

    Windows reports creation time in 100 ns units and the launch record keeps
    all seven fractional digits, which `datetime` would truncate; the
    fraction is therefore carried as an integer.
    """
    if not isinstance(value, str):
        return None
    match = _INCARNATION.fullmatch(value)
    if match is None:
        return None
    year, month, day, hour, minute, second = (int(item) for item in match.groups()[:6])
    fraction = int((match.group(7) or "").ljust(7, "0"))
    offset = match.group(8)
    if offset == "Z":
        zone = UTC
    else:
        sign = -1 if offset[0] == "-" else 1
        zone = timezone(
            sign * timedelta(hours=int(offset[1:3]), minutes=int(offset[4:]))
        )
    try:
        instant = datetime(year, month, day, hour, minute, second, tzinfo=zone)
    except ValueError:
        return None
    elapsed = instant - _TICKS_EPOCH
    return (elapsed.days * 86400 + elapsed.seconds) * 10_000_000 + fraction


def title_names_file(title: str) -> bool:
    """Whether a window title names a Packet Tracer document or a path."""
    return any(marker in title.casefold() for marker in _DOCUMENT_MARKERS)


def select_document_window(
    pid: int, census: object, *, start_ticks: int | None = None
) -> tuple[object | None, tuple[str, ...]]:
    """Select the one window a normal close may target, or name the doubt.

    `census` carries `process_id`, `windows`, `complete` and `error`; each
    window carries `handle`, `owner_pid`, `title`, `visible`, `enabled` and
    `owner_handle`. Only visible windows matter, whatever their order. The
    extension log window is set aside by its observed title. Exactly one
    other visible, unowned, enabled window whose title names no file may be
    selected. A visible owned window may be a modal prompt: it is reported,
    never filtered out, and withholds any close. The selection is auxiliary:
    it never proves that no user document exists. With `start_ticks`, the
    census must also have been taken of the process created at that instant.
    """
    if getattr(census, "error", ""):
        return None, ("window_census_unobservable",)
    if start_ticks is not None and getattr(census, "process_start_ticks", None) != (
        start_ticks
    ):
        return None, ("window_census_process_changed",)
    windows = tuple(getattr(census, "windows", ()) or ())
    if getattr(census, "process_id", None) != pid or any(
        getattr(window, "owner_pid", None) != pid for window in windows
    ):
        return None, ("window_attribution_mismatch",)
    if getattr(census, "complete", False) is not True:
        return None, ("window_census_incomplete",)
    visible = [window for window in windows if window.visible is True]
    found: list[str] = []
    if any(window.owner_handle for window in visible):
        found.append("modal_or_owned_window_visible")
    unowned = [window for window in visible if not window.owner_handle]
    if sum(window.title == EXTENSION_LOG_WINDOW_TITLE for window in unowned) > 1:
        found.append("extension_window_ambiguous")
    candidates = [
        window for window in unowned if window.title != EXTENSION_LOG_WINDOW_TITLE
    ]
    if not candidates:
        found.append("document_window_absent")
    elif len(candidates) > 1:
        found.append("document_window_ambiguous")
    else:
        document = candidates[0]
        if document.enabled is not True:
            found.append("document_window_disabled")
        if not document.title or title_names_file(document.title):
            found.append("document_window_names_file_or_nothing")
    if found:
        return None, tuple(found)
    return candidates[0], ()


def force_window_findings(
    pid: int, target: object, census: object, *, start_ticks: int | None = None
) -> tuple[str, ...]:
    """Name what, in the census after a failed close, withholds a force.

    The force needs the same document window the close targeted, with the
    same identity digest, and nothing modal or ambiguous beside it. A document
    window that closed while the process stays alive is recorded, not forced.
    """
    selected, found = select_document_window(pid, census, start_ticks=start_ticks)
    if found:
        return tuple(
            "document_window_closed_process_alive"
            if item == "document_window_absent"
            else item
            for item in found
        )
    if (
        getattr(selected, "handle", None),
        getattr(selected, "identity_digest", None),
    ) != (getattr(target, "handle", None), getattr(target, "identity_digest", None)):
        return ("document_window_changed",)
    return ()


#: The longest graceful wait a forced termination may follow. A capture that
#: claims a longer or no wait did not bound its graceful attempt.
FORCED_TERMINATION_MAX_GRACEFUL_WAIT_SECONDS = 120.0


def exit_was_forced(close: Mapping[str, object]) -> bool:
    """Whether a close capture records an exact-process termination."""
    return close.get("forced_termination") is not None


#: The graceful requests an exit record may name: the historical
#: `Process.CloseMainWindow` of a capture, and the retirement flow's
#: `WM_CLOSE` posted to one revalidated document window.
GRACEFUL_CLOSE_METHODS = ("CloseMainWindow", "WM_CLOSE")
_WINDOW_DIGEST_LENGTH = 64


def _document_target_proven(launch: Mapping[str, object], target: object) -> bool:
    """Whether a recorded close target is one owned, unnamed document window."""
    if not isinstance(target, Mapping):
        return False
    handle = target.get("handle")
    digest = target.get("identity_digest")
    title = target.get("title")
    return (
        not isinstance(handle, bool)
        and isinstance(handle, int)
        and handle > 0
        and target.get("owner_pid") == launch.get("pid")
        and isinstance(digest, str)
        and len(digest) == _WINDOW_DIGEST_LENGTH
        and isinstance(title, str)
        and bool(title)
        and title != EXTENSION_LOG_WINDOW_TITLE
        and not title_names_file(title)
    )


def _same_document_window(
    close: Mapping[str, object], forced: Mapping[str, object]
) -> bool:
    """Whether the force rechecked the very window the close targeted.

    The termination must also have been bound, in the helper call that
    issued it, to the census's process creation time and visible window set.
    """
    target = close.get("close_target")
    again = forced.get("rechecked_document_window")
    ticks = forced.get("bound_process_start_ticks")
    window_set = forced.get("bound_window_set_digest")
    return (
        close.get("method") == "WM_CLOSE"
        and isinstance(target, Mapping)
        and isinstance(again, Mapping)
        and again.get("handle") == target.get("handle")
        and again.get("identity_digest") == target.get("identity_digest")
        and forced.get("window_census_complete") is True
        and forced.get("modal_windows_visible") is False
        and not isinstance(ticks, bool)
        and isinstance(ticks, int)
        and ticks > 0
        and ticks == incarnation_ticks(forced.get("rechecked_process_incarnation"))
        and isinstance(window_set, str)
        and len(window_set) == _WINDOW_DIGEST_LENGTH
    )


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
    OS reading taken just before it matched the launch's observed identity
    and command line (`observed_process_findings`), the launch proved a new
    unnamed document (`launched_blank`), the window census after the failed
    close was complete, showed no modal window and still held the same
    document window it targeted (`force_window_findings`), and a durable
    ownership basis for the workspace was established from the campaign's
    own records. Windows and titles are auxiliary evidence; they never
    authorize a force by themselves.
    """
    found: list[str] = []
    forced = close.get("forced_termination")
    if forced is not None:
        wait = close.get("graceful_wait_seconds")
        if not allow_forced:
            found.append("forced_termination_not_permitted")
        elif (
            not isinstance(forced, Mapping)
            or forced.get("method") != "Process.Kill"
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
            or not _same_document_window(close, forced)
            or not isinstance(forced.get("requested_at_utc"), str)
            or isinstance(wait, bool)
            or not isinstance(wait, (int, float))
            or not 0 < wait <= FORCED_TERMINATION_MAX_GRACEFUL_WAIT_SECONDS
        ):
            found.append("forced_termination_identity_unproven")
    method = close.get("method")
    if (
        close.get("pid") != launch.get("pid")
        or close.get("process_path") != launch.get("process_path")
        or close.get("process_incarnation") != launch.get("process_incarnation")
        or method not in GRACEFUL_CLOSE_METHODS
        or (
            method == "WM_CLOSE"
            and not _document_target_proven(launch, close.get("close_target"))
        )
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
