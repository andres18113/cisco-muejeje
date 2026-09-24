"""Pure ownership and process-exit evidence rules for Server-PT campaigns."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
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
#: The title Packet Tracer 9.0.1.0858 gives its unnamed document window.
BLANK_DOCUMENT_TITLE = "Cisco Packet Tracer"


@dataclass(frozen=True)
class WindowRole:
    """One top-level window role: the classes it may have and its exact title."""

    class_names: frozenset[str]
    title: str

    def matches(self, window: object) -> bool:
        """Whether one observed window has this role's class and title."""
        return (
            getattr(window, "class_name", None) in self.class_names
            and getattr(window, "title", None) == self.title
        )


@dataclass(frozen=True)
class BuildWindowSignature:
    """The windows one Packet Tracer build is known to show, and why.

    A window is the document only when it matches `document`; a window that
    matches neither role is unclassified, and withholds every effect. The
    title is one conjunct among class, owner, visibility, enablement and the
    process, never a selection by itself.
    """

    build: str
    document: WindowRole
    extension_log: WindowRole
    basis: str


#: Win32's own dialog class. Such a window is never a document.
DIALOG_WINDOW_CLASSES = frozenset({"#32770"})

#: Qt 6.8.7, as installed with 9.0.1.0858, registers one of these two classes
#: for an ordinary top-level window with a system menu: `QWindowIcon`
#: (raster or Direct3D surface) or `QWindowOwnDCIcon` (OpenGL surface).
_QT_687_TOP_LEVEL_CLASSES = frozenset({"Qt687QWindowIcon", "Qt687QWindowOwnDCIcon"})

#: Only builds whose windows are known are listed. Another build selects
#: nothing until its own signature is established.
PT_WINDOW_SIGNATURES: Mapping[str, BuildWindowSignature] = {
    SERVER_PT_BUILD: BuildWindowSignature(
        build=SERVER_PT_BUILD,
        document=WindowRole(_QT_687_TOP_LEVEL_CLASSES, BLANK_DOCUMENT_TITLE),
        extension_log=WindowRole(_QT_687_TOP_LEVEL_CLASSES, EXTENSION_LOG_WINDOW_TITLE),
        basis=(
            "titles observed on 9.0.1.0858 (FASTLOOP episode 1 window listing; "
            "UIA inventory 2026-09-15: PtApp.CAppWindowBase, Qt class CAppWindow, "
            "named Cisco Packet Tracer); classes are the Qt 6.8.7 top-level "
            "window classes of the installed build's Qt, confirmed only by a "
            "laboratory census"
        ),
    ),
}


def window_signature_for_launch(
    launch: Mapping[str, object],
) -> BuildWindowSignature | None:
    """Return the signature of the build the launch record observed, or `None`.

    The build is what the operating system reported for the launched image
    (`observed_product_version`, `observed_file_version`). A launch without
    it, or with two readings naming different known builds, has none.
    """
    found = {
        PT_WINDOW_SIGNATURES[value]
        for value in (
            launch.get("observed_product_version"),
            launch.get("observed_file_version"),
        )
        if isinstance(value, str) and value in PT_WINDOW_SIGNATURES
    }
    return found.pop() if len(found) == 1 else None


def window_signature_record(signature: BuildWindowSignature) -> dict[str, object]:
    """One signature as evidence: how the document role was identified."""
    return {
        "build": signature.build,
        "document_classes": sorted(signature.document.class_names),
        "document_title": signature.document.title,
        "extension_log_classes": sorted(signature.extension_log.class_names),
        "extension_log_title": signature.extension_log.title,
        "dialog_classes": sorted(DIALOG_WINDOW_CLASSES),
        "basis": signature.basis,
    }


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


def _window_role(window: object, signature: BuildWindowSignature) -> str:
    """Classify one visible window; anything not positively known is doubt."""
    if getattr(window, "owner_handle", 0):
        return "owned"
    if getattr(window, "class_name", None) in DIALOG_WINDOW_CLASSES:
        return "dialog"
    if signature.document.matches(window):
        return "document"
    if signature.extension_log.matches(window):
        return "extension_log"
    return "unclassified"


def select_document_window(
    pid: int,
    census: object,
    *,
    signature: BuildWindowSignature | None,
    start_ticks: int | None = None,
) -> tuple[object | None, tuple[str, ...]]:
    """Select the one window a normal close may target, or name the doubt.

    `census` carries `process_id`, `windows`, `complete` and `error`; each
    window carries `handle`, `owner_pid`, `class_name`, `title`, `visible`,
    `enabled` and `owner_handle`. Only visible windows matter, whatever their
    order. Each one must be positively classified by the build's
    `signature`: exactly one enabled document window, at most one extension
    log window, and nothing else. A native dialog, an unclassified window or
    a visible owned window (possibly a modal prompt) is reported, never
    filtered out, and withholds any close. Without a signature nothing is
    selected. The selection is auxiliary: it never proves that no user
    document exists. With `start_ticks`, the census must also have been taken
    of the process created at that instant.
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
    if signature is None:
        return None, ("document_signature_unestablished",)
    visible = [window for window in windows if window.visible is True]
    roles = [(window, _window_role(window, signature)) for window in visible]
    found: list[str] = []
    if any(role == "owned" for _, role in roles):
        found.append("modal_or_owned_window_visible")
    if any(role == "dialog" for _, role in roles):
        found.append("dialog_window_visible")
    unclassified = [window for window, role in roles if role == "unclassified"]
    if unclassified:
        found.append("unclassified_window_visible")
    if any(
        window.class_name in signature.document.class_names
        and (not window.title or title_names_file(window.title))
        for window in unclassified
    ):
        found.append("document_window_names_file_or_nothing")
    if sum(role == "extension_log" for _, role in roles) > 1:
        found.append("extension_window_ambiguous")
    documents = [window for window, role in roles if role == "document"]
    if not documents:
        found.append("document_window_absent")
    elif len(documents) > 1:
        found.append("document_window_ambiguous")
    elif documents[0].enabled is not True:
        found.append("document_window_disabled")
    if found:
        return None, tuple(found)
    return documents[0], ()


#: Win32_Process reports creation to the microsecond (10 ticks); the launch
#: record keeps it to 100 ns, so the same instant may differ by up to 9.
_CENSUS_TICK_RESOLUTION = 10
_HELPER_ARGUMENT = re.compile(r"(?:^|\s)--progress-bar-server(?:\s|$)")


def packet_tracer_process_role(
    launch: Mapping[str, object], start_ticks: int, row: object
) -> str:
    """Name one listed Packet Tracer process relative to the owned launch.

    `owned` is the launched process itself (same PID and creation time).
    `owned_helper` is a `--progress-bar-server` process the launched process
    started: its parent is the owned PID, it was created no earlier than the
    launch, and its command line (and image, when the OS shows it) is the
    launched executable's. Anything else is `foreign`.
    """
    pid = launch.get("pid")
    path = launch.get("process_path")
    ticks = getattr(row, "start_ticks", None)
    if not isinstance(path, str) or not path or not isinstance(ticks, int):
        return "foreign"
    if (
        getattr(row, "process_id", None) == pid
        and abs(ticks - start_ticks) < _CENSUS_TICK_RESOLUTION
    ):
        return "owned"
    command = getattr(row, "command_line", "")
    image = getattr(row, "executable_path", "")
    if (
        getattr(row, "parent_process_id", None) == pid
        and ticks > start_ticks - _CENSUS_TICK_RESOLUTION
        and isinstance(command, str)
        and command.casefold().startswith(f'"{path}"'.casefold())
        and _HELPER_ARGUMENT.search(command) is not None
        and (not image or image.casefold() == path.casefold())
    ):
        return "owned_helper"
    return "foreign"


def lingering_process_findings(
    launch: Mapping[str, object], start_ticks: int, rows: object
) -> tuple[str, ...]:
    """Refuse when any listed Packet Tracer process is not the launch's own."""
    if any(
        packet_tracer_process_role(launch, start_ticks, row) == "foreign"
        for row in tuple(rows or ())
    ):
        return ("foreign_packet_tracer_process",)
    return ()


def force_window_findings(
    pid: int,
    target: object,
    census: object,
    *,
    signature: BuildWindowSignature | None,
    start_ticks: int | None = None,
) -> tuple[str, ...]:
    """Name what, in the census after a failed close, withholds a force.

    The force needs the same document window the close targeted, with the
    same identity digest, and nothing modal, unclassified or ambiguous beside
    it. A document window that closed while the process stays alive is
    recorded, not forced.
    """
    selected, found = select_document_window(
        pid, census, signature=signature, start_ticks=start_ticks
    )
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
    """Whether a recorded close target is one owned, unnamed document window.

    It must have been a visible, enabled top-level window with no owner, and
    its class and title must be the document role of the build the launch
    observed; a modal, a native dialog, the log or an unknown window is not
    a target.
    """
    if not isinstance(target, Mapping):
        return False
    handle = target.get("handle")
    digest = target.get("identity_digest")
    title = target.get("title")
    owner = target.get("owner_handle")
    signature = window_signature_for_launch(launch)
    return (
        not isinstance(handle, bool)
        and isinstance(handle, int)
        and handle > 0
        and not isinstance(owner, bool)
        and owner == 0
        and target.get("visible") is True
        and target.get("enabled") is True
        and target.get("owner_pid") == launch.get("pid")
        and isinstance(digest, str)
        and len(digest) == _WINDOW_DIGEST_LENGTH
        and isinstance(title, str)
        and bool(title)
        and title != EXTENSION_LOG_WINDOW_TITLE
        and not title_names_file(title)
        and signature is not None
        and target.get("class_name") not in DIALOG_WINDOW_CLASSES
        and target.get("class_name") in signature.document.class_names
        and title == signature.document.title
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
