"""FASTLOOP retirement by window observation, and the historical exit import.

Addendum 02 replaces the main-window-title guard of `--retire` with a bounded,
process-bound window census and one revalidated close, and authorizes one
append-only import of episode 1's exit. Every test drives the production rule,
helper, CLI or store that decides it, and every failure asserts that no close
was posted and no process terminated.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from importlib import import_module
from pathlib import Path

import pytest

from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
    prepare_server_pt_commissioning,
)
from packet_tracer_mcp.application.use_cases.server_pt_campaign import (
    FASTLOOP_CAMPAIGN,
)
from packet_tracer_mcp.application.use_cases.server_pt_historical_exit import (
    FASTLOOP_EPISODE_1_EXIT_IMPORT,
    HistoricalExitImportAuthority,
    historical_exit_import_findings,
)
from packet_tracer_mcp.application.use_cases.server_pt_phase_grant import (
    derive_server_pt_phase_grant,
)
from packet_tracer_mcp.application.use_cases.server_pt_process_evidence import (
    EXTENSION_LOG_WINDOW_TITLE,
    exit_evidence_findings,
    force_window_findings,
    incarnation_ticks,
    select_document_window,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
    RepositoryIdentity,
)
from packet_tracer_mcp.infrastructure.execution.server_pt_campaign_authority import (
    SourceAncestry,
)
from packet_tracer_mcp.infrastructure.execution.server_pt_process_control import (
    WINDOW_CENSUS_LIMIT,
    OwnedProcessObservation,
    OwnedWindow,
    OwnedWindowCensus,
    PowerShellOwnedProcessControl,
    TerminationResult,
    WindowCloseResult,
    visible_set_digest,
    window_identity_digest,
)
from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)

ATTEMPT = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
OTHER = "1f1e2d3c4b5a69788796a5b4c3d2e1f0"
HEAD = "a" * 40
TREE = "b" * 40
PID = 123
FOREIGN_PID = 999
PATH = "C:\\Program Files\\Cisco Packet Tracer 9.0.1\\bin\\PacketTracer.exe"
INCARNATION = "2026-09-24T07:00:00-05:00"
COMMAND_LINE = f'"{PATH}" '
START_TICKS = incarnation_ticks(INCARNATION)
QT_CLASS = "Qt663QWindowIcon"


def _window(
    handle: int,
    title: str,
    *,
    pid: int = PID,
    visible: bool = True,
    enabled: bool = True,
    owner: int = 0,
    class_name: str = QT_CLASS,
) -> OwnedWindow:
    return OwnedWindow(
        handle=handle,
        owner_pid=pid,
        class_name=class_name,
        title=title,
        visible=visible,
        enabled=enabled,
        owner_handle=owner,
        identity_digest=window_identity_digest(class_name, title),
    )


DOCUMENT = _window(4242, "Cisco Packet Tracer")
LOG = _window(4343, EXTENSION_LOG_WINDOW_TITLE)
HIDDEN = _window(4444, "QTrayIconMessageWindow", visible=False)


def _census(
    *windows: OwnedWindow,
    pid: int = PID,
    complete: bool = True,
    ticks: int | None = None,
):
    return OwnedWindowCensus(
        pid,
        windows=windows,
        complete=complete,
        process_start_ticks=START_TICKS if ticks is None else ticks,
        visible_set_digest=visible_set_digest(windows) if complete else "",
    )


# -- selection and force rules --------------------------------------------------------


@pytest.mark.parametrize(
    "windows",
    [
        (DOCUMENT, LOG),
        (LOG, DOCUMENT),
        (DOCUMENT,),
        (HIDDEN, LOG, DOCUMENT),
    ],
    ids=["document-first", "log-first", "log-gone", "hidden-ignored"],
)
def test_order_focus_and_the_log_window_select_the_same_document(windows):
    """Enumeration order and the log window's presence change nothing."""
    selected, found = select_document_window(PID, _census(*windows))

    assert found == ()
    assert selected == DOCUMENT


@pytest.mark.parametrize(
    ("census", "finding"),
    [
        (
            OwnedWindowCensus(PID, error="window_census_unobservable:TimeoutExpired"),
            "window_census_unobservable",
        ),
        (_census(DOCUMENT, LOG, complete=False), "window_census_incomplete"),
        (_census(DOCUMENT, pid=FOREIGN_PID), "window_attribution_mismatch"),
        (
            _census(replace(DOCUMENT, owner_pid=FOREIGN_PID), LOG),
            "window_attribution_mismatch",
        ),
        (
            _census(
                replace(DOCUMENT, enabled=False),
                _window(5555, "Cisco Packet Tracer", owner=4242),
                LOG,
            ),
            "modal_or_owned_window_visible",
        ),
        (_census(replace(DOCUMENT, enabled=False), LOG), "document_window_disabled"),
        (
            _census(DOCUMENT, _window(4545, "Cisco Packet Tracer"), LOG),
            "document_window_ambiguous",
        ),
        (_census(LOG), "document_window_absent"),
        (
            _census(_window(4242, "Cisco Packet Tracer - C:\\coursework.pkt"), LOG),
            "document_window_names_file_or_nothing",
        ),
        (_census(_window(4242, ""), LOG), "document_window_names_file_or_nothing"),
        (
            _census(DOCUMENT, LOG, _window(4646, EXTENSION_LOG_WINDOW_TITLE)),
            "extension_window_ambiguous",
        ),
    ],
)
def test_any_doubt_about_the_windows_selects_nothing(census, finding):
    """Incomplete, foreign, modal, changed or ambiguous: no close target."""
    selected, found = select_document_window(PID, census)

    assert selected is None
    assert finding in found


def test_a_census_of_another_incarnation_selects_nothing():
    """The same PID created at another instant is another process."""
    census = _census(DOCUMENT, LOG, ticks=START_TICKS + 1)

    assert select_document_window(PID, census, start_ticks=START_TICKS) == (
        None,
        ("window_census_process_changed",),
    )
    assert select_document_window(PID, _census(DOCUMENT, LOG), start_ticks=START_TICKS)[
        0
    ] == (DOCUMENT)


def test_the_creation_time_converts_exactly_to_windows_ticks():
    """Seven fractional digits survive; a malformed time is unusable."""
    assert incarnation_ticks("2026-09-24T07:29:09.8013309-05:00") == (
        639258497498013309
    )
    assert incarnation_ticks("2026-09-24T12:29:09.8013309Z") == 639258497498013309
    for value in ("", "2026-09-24T12:29:09", "2026-02-30T00:00:00Z", None, 5):
        assert incarnation_ticks(value) is None


def test_a_foreign_process_with_identical_titles_is_never_selected():
    """Titles equal to the owned ones prove nothing about another PID."""
    foreign = _census(
        _window(9001, "Cisco Packet Tracer", pid=FOREIGN_PID),
        _window(9002, EXTENSION_LOG_WINDOW_TITLE, pid=FOREIGN_PID),
        pid=FOREIGN_PID,
    )

    assert select_document_window(PID, foreign) == (
        None,
        ("window_attribution_mismatch",),
    )
    assert select_document_window(PID, _census(LOG))[1] == ("document_window_absent",)


@pytest.mark.parametrize(
    ("after", "finding"),
    [
        (_census(LOG, DOCUMENT), None),
        (_census(LOG), "document_window_closed_process_alive"),
        (_census(_window(7777, "Cisco Packet Tracer"), LOG), "document_window_changed"),
        (
            _census(_window(4242, "Cisco Packet Tracer - C:\\saved.pkt"), LOG),
            "document_window_names_file_or_nothing",
        ),
        (
            _census(
                replace(DOCUMENT, enabled=False), _window(5555, "Save?", owner=4242)
            ),
            "modal_or_owned_window_visible",
        ),
        (_census(DOCUMENT, complete=False), "window_census_incomplete"),
    ],
)
def test_a_force_needs_the_same_document_window_and_nothing_modal(after, finding):
    """After a failed close only the unchanged target may be forced."""
    found = force_window_findings(PID, DOCUMENT, after)

    assert (found == ()) if finding is None else (finding in found)


def _launch() -> dict[str, object]:
    return {
        "pid": PID,
        "process_path": PATH,
        "process_incarnation": INCARNATION,
        "observed_command_line": COMMAND_LINE,
        "observed_main_window_title": "Cisco Packet Tracer",
    }


def _target(window: OwnedWindow = DOCUMENT) -> dict[str, object]:
    return {
        "handle": window.handle,
        "owner_pid": window.owner_pid,
        "class_name": window.class_name,
        "title": window.title,
        "identity_digest": window.identity_digest,
    }


@pytest.mark.parametrize(
    "target",
    [
        None,
        _target(LOG),
        _target(_window(4242, "Cisco Packet Tracer - C:\\x.pkt")),
        {**_target(), "owner_pid": FOREIGN_PID},
        {**_target(), "handle": True},
    ],
    ids=["missing", "log-window", "named-file", "foreign", "bool-handle"],
)
def test_a_targeted_close_must_name_one_owned_unnamed_document(target):
    """A WM_CLOSE record without its proven target is not a graceful request."""
    close = {
        **_launch(),
        "method": "WM_CLOSE",
        "close_target": target,
        "requested": True,
        "actual_exit_observed": True,
    }

    assert "graceful_close_identity_unproven" in exit_evidence_findings(
        _launch(), close, process_count=0
    )
    assert (
        exit_evidence_findings(
            _launch(), {**close, "close_target": _target()}, process_count=0
        )
        == ()
    )


# -- the native helper's boundary -----------------------------------------------------


class _Runner:
    """Capture helper invocations and answer with a fixed stdout."""

    def __init__(self, stdout: str = "", error: Exception | None = None):
        self.stdout = stdout
        self.error = error
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        assert kwargs["timeout"] > 0
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(argv, 0, stdout=self.stdout, stderr="")

    def script(self) -> str:
        argv = self.calls[-1]
        assert argv[:4] == [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
        ]
        return base64.b64decode(argv[4]).decode("utf-16-le")


def _row(window: OwnedWindow) -> dict[str, object]:
    return {
        "handle": window.handle,
        "owner_pid": window.owner_pid,
        "class_name": window.class_name,
        "title": window.title,
        "visible": window.visible,
        "enabled": window.enabled,
        "owner_handle": window.owner_handle,
        "identity_digest": window.identity_digest,
    }


def _answer(*windows: OwnedWindow, **overrides) -> str:
    value = {
        "complete": True,
        "process_start_ticks": START_TICKS,
        "visible_set_digest": visible_set_digest(windows),
        "windows": [_row(window) for window in windows],
    }
    value.update(overrides)
    return json.dumps(value)


def test_the_census_command_names_only_the_validated_pid():
    """No external text reaches the helper; its answer becomes typed windows."""
    runner = _Runner(_answer(DOCUMENT, LOG))
    control = PowerShellOwnedProcessControl(run_command=runner)

    census = control.windows(PID)

    assert census == _census(DOCUMENT, LOG)
    assert runner.script().splitlines()[-1] == (
        f"[PtMcpOwnedWindows]::Census({PID}, {WINDOW_CENSUS_LIMIT})"
    )
    with pytest.raises(ValueError):
        control.windows(True)


def test_the_close_command_names_only_validated_integers_and_a_digest():
    """The handle and digest are checked before any helper runs."""
    runner = _Runner(json.dumps({"sent": True, "refusal": ""}))
    control = PowerShellOwnedProcessControl(run_command=runner)
    window_set = visible_set_digest((DOCUMENT, LOG))

    result = control.close_window(
        PID,
        DOCUMENT.handle,
        DOCUMENT.identity_digest,
        set_digest=window_set,
        start_ticks=START_TICKS,
    )

    assert result == WindowCloseResult(PID, DOCUMENT.handle, sent=True)
    assert runner.script().splitlines()[-1] == (
        f"[PtMcpOwnedWindows]::Close({PID}, {DOCUMENT.handle}, "
        f"'{DOCUMENT.identity_digest}', '{window_set}', {START_TICKS}, "
        f"{WINDOW_CENSUS_LIMIT})"
    )
    for handle, digest, bound_set, ticks in [
        (True, DOCUMENT.identity_digest, window_set, START_TICKS),
        (0, DOCUMENT.identity_digest, window_set, START_TICKS),
        (DOCUMENT.handle, "Cisco Packet Tracer", window_set, START_TICKS),
        (DOCUMENT.handle, "'); Stop-Process -Id 1; ('" + "0" * 40, window_set, 1),
        (DOCUMENT.handle, DOCUMENT.identity_digest, "", START_TICKS),
        (DOCUMENT.handle, DOCUMENT.identity_digest, window_set, 0),
        (DOCUMENT.handle, DOCUMENT.identity_digest, window_set, True),
    ]:
        with pytest.raises(ValueError):
            control.close_window(
                PID, handle, digest, set_digest=bound_set, start_ticks=ticks
            )
    assert len(runner.calls) == 1


def test_the_termination_names_only_the_bound_process_and_window_set():
    """No PID-only kill exists; the helper kills the checked process object."""
    runner = _Runner(json.dumps({"sent": False, "refusal": "window_set_changed"}))
    control = PowerShellOwnedProcessControl(run_command=runner)
    window_set = visible_set_digest((DOCUMENT, LOG))

    result = control.terminate(PID, set_digest=window_set, start_ticks=START_TICKS)

    assert result == TerminationResult(PID, refusal="window_set_changed")
    assert runner.script().splitlines()[-1] == (
        f"[PtMcpOwnedWindows]::Terminate({PID}, '{window_set}', {START_TICKS}, "
        f"{WINDOW_CENSUS_LIMIT})"
    )
    with pytest.raises(ValueError):
        control.terminate(PID, set_digest="x", start_ticks=START_TICKS)
    with pytest.raises(TypeError):
        control.terminate(PID)
    assert not hasattr(PowerShellOwnedProcessControl, "request_close")


@pytest.mark.parametrize(
    ("stdout", "error"),
    [
        ("not json", "window_census_malformed"),
        (_answer(DOCUMENT, windows=None), "window_census_malformed"),
        (_answer(DOCUMENT, DOCUMENT), "window_census_malformed"),
        (
            _answer(DOCUMENT, windows=[{**_row(DOCUMENT), "title": "changed"}]),
            "window_census_malformed",
        ),
        (
            _answer(DOCUMENT, windows=[{**_row(DOCUMENT), "visible": 1}]),
            "window_census_malformed",
        ),
        (
            _answer(replace(LOG, owner_pid=FOREIGN_PID)),
            "window_attribution_mismatch",
        ),
        (
            _answer(
                *(
                    _window(index + 1, f"w{index}")
                    for index in range(WINDOW_CENSUS_LIMIT + 1)
                )
            ),
            "window_census_malformed",
        ),
        (_answer(DOCUMENT, process_start_ticks=None), "window_census_malformed"),
        (_answer(DOCUMENT, process_start_ticks=-1), "window_census_process_unreadable"),
        (
            _answer(DOCUMENT, LOG, visible_set_digest=visible_set_digest((DOCUMENT,))),
            "window_census_malformed",
        ),
    ],
    ids=[
        "not-json",
        "no-windows",
        "duplicate-handle",
        "altered-title",
        "non-bool-flag",
        "foreign-row",
        "over-limit",
        "no-ticks",
        "process-unreadable",
        "set-digest-of-other-rows",
    ],
)
def test_a_doubtful_census_answer_is_an_error_not_an_empty_set(stdout, error):
    """Malformed, foreign-attributed or altered rows never become windows."""
    census = PowerShellOwnedProcessControl(run_command=_Runner(stdout)).windows(PID)

    assert census.error == error
    assert census.windows == ()


def test_a_census_or_close_that_times_out_is_unobservable():
    """A timed-out helper is an error; its close outcome is not known."""
    timeout = subprocess.TimeoutExpired("powershell.exe", 15)
    control = PowerShellOwnedProcessControl(run_command=_Runner(error=timeout))

    assert control.windows(PID).error == "window_census_unobservable:TimeoutExpired"
    bound = {"set_digest": visible_set_digest((DOCUMENT,)), "start_ticks": START_TICKS}
    result = control.close_window(
        PID, DOCUMENT.handle, DOCUMENT.identity_digest, **bound
    )
    assert result.sent is False
    assert result.error == "window_close_unobservable:TimeoutExpired"
    killed = control.terminate(PID, **bound)
    assert killed.sent is False
    assert killed.error == "termination_unobservable:TimeoutExpired"


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "nope",
        json.dumps({"sent": True, "refusal": "window_absent"}),
        json.dumps({"sent": False, "refusal": ""}),
    ],
    ids=["empty", "not-json", "sent-with-refusal", "unsent-without-refusal"],
)
def test_a_doubtful_close_answer_is_not_a_sent_close(stdout):
    """Only an explicit, consistent answer reports what the helper did."""
    result = PowerShellOwnedProcessControl(run_command=_Runner(stdout)).close_window(
        PID,
        DOCUMENT.handle,
        DOCUMENT.identity_digest,
        set_digest=visible_set_digest((DOCUMENT,)),
        start_ticks=START_TICKS,
    )

    assert result.sent is False
    assert result.error == "window_close_malformed"


# -- `--retire` through the CLI -------------------------------------------------------


class _FakeOS:
    """The OS as retirement sees it: the owned process, windows and effects."""

    def __init__(self):
        self.present = True
        self.incarnation = INCARNATION
        self.census_ticks = START_TICKS
        self.main_title = "Cisco Packet Tracer"
        self.windows_of: dict[int, list[OwnedWindow]] = {PID: [DOCUMENT, LOG]}
        self.census_complete = True
        self.census_error = ""
        self.on_close = "exit"
        self.close_refusal = ""
        self.close_error = ""
        self.calls: list[str] = []
        self.posted: list[int] = []
        # What changes in the world right after the n-th census (1-based).
        self.after_census: dict[int, object] = {}
        self.censuses = 0

    def __call__(self):
        return self

    def observe(self, pid):
        self.calls.append("observe")
        if not self.present:
            return OwnedProcessObservation(pid, present=False)
        return OwnedProcessObservation(
            pid,
            present=True,
            process_path=PATH,
            process_incarnation=self.incarnation,
            command_line=COMMAND_LINE,
            main_window_title=self.main_title,
        )

    def windows(self, pid):
        self.calls.append("windows")
        if self.census_error:
            return OwnedWindowCensus(pid, error=self.census_error)
        windows = tuple(self.windows_of.get(pid, ())) if self.present else ()
        census = OwnedWindowCensus(
            pid,
            windows=windows,
            complete=self.census_complete,
            process_start_ticks=self.census_ticks,
            visible_set_digest=visible_set_digest(windows),
        )
        self.censuses += 1
        change = self.after_census.pop(self.censuses, None)
        if change is not None:
            change(self)
        return census

    def _changed(self, pid, set_digest, start_ticks) -> str:
        """Recheck process and visible window set, as the helper does."""
        if start_ticks != self.census_ticks or not self.present:
            return "process_changed"
        if set_digest != visible_set_digest(tuple(self.windows_of.get(pid, ()))):
            return "window_set_changed"
        return ""

    def close_window(self, pid, handle, digest, *, set_digest, start_ticks):
        # The helper's own revalidation: the handle must still be that window.
        self.calls.append("close_helper")
        if self.close_error:
            self.posted.append(handle)
            return WindowCloseResult(pid, handle, error=self.close_error)
        if self.close_refusal:
            return WindowCloseResult(pid, handle, refusal=self.close_refusal)
        changed = self._changed(pid, set_digest, start_ticks)
        if changed:
            return WindowCloseResult(pid, handle, refusal=changed)
        owned = {window.handle: window for window in self.windows_of.get(pid, ())}
        if handle not in owned or owned[handle].identity_digest != digest:
            return WindowCloseResult(pid, handle, refusal="window_identity_changed")
        self.posted.append(handle)
        current = self.windows_of[pid]
        if self.on_close == "exit":
            self.present = False
        elif self.on_close == "modal":
            self.windows_of[pid] = [
                replace(window, enabled=False) if window.handle == handle else window
                for window in current
            ] + [_window(5555, "Cisco Packet Tracer", owner=handle)]
        elif self.on_close == "vanish":
            self.windows_of[pid] = [w for w in current if w.handle != handle]
        return WindowCloseResult(pid, handle, sent=True)

    def terminate(self, pid, *, set_digest, start_ticks):
        self.calls.append("terminate_helper")
        changed = self._changed(pid, set_digest, start_ticks)
        if changed:
            return TerminationResult(pid, refusal=changed)
        self.calls.append("terminate")
        self.present = False
        return TerminationResult(pid, sent=True)

    def census(self):
        return 0 if not self.present else 1


def _checkpoint() -> RepositoryIdentity:
    return RepositoryIdentity(
        branch="feature/server-pt-goal-foundations",
        head=HEAD,
        tree=TREE,
        clean=True,
        upstream_head="c" * 40,
    )


def _process() -> DiagnosticLifecycleObservation:
    return DiagnosticLifecycleObservation(
        process_id=PID,
        process_path=PATH,
        process_incarnation=INCARNATION,
        product_version="9.0.1.0858",
    )


def _run(cli, argv, env, capsys):
    code = cli.main(argv, environ=env)
    return code, json.loads(capsys.readouterr().out)


@pytest.fixture
def fastloop_cli(tmp_path: Path, monkeypatch):
    """Bind a test charter to the experimental campaign; forbid other reads."""
    cli = import_module("packet_tracer_mcp.adapters.cli.server_pt_commissioning")
    charter = tmp_path / "work-order.md"
    charter.write_text("experimental work order", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "FASTLOOP_CHARTER_SHA256",
        hashlib.sha256(charter.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(cli, "repository_identity", lambda _root: _checkpoint())

    def forbidden(*_args, **_kwargs):
        raise AssertionError("no process may be read by this refusal")

    monkeypatch.setattr(cli, "phase_preflight", forbidden)
    return cli, charter, {"PT_MCP_GOVERNED_ROOT": str(tmp_path)}


@pytest.fixture
def launched(fastloop_cli, tmp_path: Path, capsys, monkeypatch):
    """Record one experimental launch whose capture matches the OS reading."""
    from packet_tracer_mcp.adapters.cli.server_pt_live_phase import PhasePreflight

    cli, charter, env = fastloop_cli
    monkeypatch.setattr(
        cli,
        "phase_preflight",
        lambda *_args, **_kwargs: PhasePreflight(
            _checkpoint(), None, _process(), campaign=FASTLOOP_CAMPAIGN
        ),
    )
    monkeypatch.setattr(cli, "RETIREMENT_GRACE_SECONDS", 0.01)
    monkeypatch.setattr(cli, "RETIREMENT_EXIT_WAIT_SECONDS", 0.01)
    monkeypatch.setattr(cli, "_retirement_sleep", lambda _seconds: time.sleep(0.002))
    system = _FakeOS()
    # At launch the extension log window was the one .NET called "main".
    system.main_title = EXTENSION_LOG_WINDOW_TITLE
    system.windows_of[PID] = [LOG, DOCUMENT]
    monkeypatch.setattr(cli, "_PROCESS_CONTROL", system)
    capture = tmp_path / "launch.json"
    capture.write_text(
        json.dumps(
            {
                "pid": PID,
                "process_path": PATH,
                "process_incarnation": INCARNATION,
                "main_window_title": EXTENSION_LOG_WINDOW_TITLE,
                "command_line": COMMAND_LINE,
                "created_by_campaign": True,
                "workspace_kind": "disposable_declared",
                "launch_method": "Start-Process",
            }
        ),
        encoding="utf-8",
    )
    base = ["--campaign", "fastloop", "--attempt", ATTEMPT, "--charter", str(charter)]
    code, owned = _run(
        cli, ["--record-launch", *base, "--launch-evidence", str(capture)], env, capsys
    )
    assert code == 0, owned
    assert owned["blank_document_proven"] is True
    system.calls.clear()
    system.censuses = 0
    return cli, env, base, system


def _store(tmp_path: Path) -> ServerPtCommissioningStore:
    return ServerPtCommissioningStore(tmp_path, FASTLOOP_CAMPAIGN.campaign_id)


def _attempts(tmp_path: Path) -> list[dict[str, object]]:
    directory = tmp_path / "data" / "commissioning" / FASTLOOP_CAMPAIGN.campaign_id
    return [
        json.loads(path.read_bytes())
        for path in sorted((directory / ATTEMPT).glob("retirement-attempt-*.json"))
    ]


def test_the_launch_keeps_its_window_census_as_auxiliary_evidence(
    launched, tmp_path: Path
):
    """Both windows are retained with handle, owner, class, title and flags."""
    record = _store(tmp_path).load_process_launch(ATTEMPT)

    census = record["observed_window_census"]
    assert census["complete"] is True and census["error"] == ""
    assert [item["title"] for item in census["windows"]] == [
        EXTENSION_LOG_WINDOW_TITLE,
        "Cisco Packet Tracer",
    ]
    assert {"handle", "owner_pid", "class_name", "visible", "owner_handle"} <= set(
        census["windows"][0]
    )


@pytest.mark.parametrize(
    ("order", "main_title"),
    [
        ([DOCUMENT, LOG], "Cisco Packet Tracer"),
        ([LOG, DOCUMENT], EXTENSION_LOG_WINDOW_TITLE),
        ([DOCUMENT], "Cisco Packet Tracer"),
        ([HIDDEN, DOCUMENT, LOG], "PacketTracer"),
    ],
    ids=["document-first", "log-focused", "log-closed", "startup-title"],
)
def test_changing_focus_order_and_log_window_still_retire_gracefully(
    launched, capsys, tmp_path: Path, order, main_title
):
    """Episode 1's refusal is gone: one targeted close, no force."""
    cli, env, base, system = launched
    system.windows_of[PID] = list(order)
    system.main_title = main_title

    code, retired = _run(cli, ["--retire", *base], env, capsys)

    assert code == 0, retired
    assert retired["outcome"] == "exited_before_setup"
    assert system.posted == [DOCUMENT.handle]
    assert "terminate" not in system.calls
    record = _store(tmp_path).load_process_exit(ATTEMPT)
    assert record["method"] == "WM_CLOSE"
    assert record["close_target"]["handle"] == DOCUMENT.handle
    assert "forced_termination" not in record
    assert _store(tmp_path).verify_index() == ()


def _refused_without_effect(cli, env, base, system, capsys, tmp_path, finding):
    code, refused = _run(cli, ["--retire", *base], env, capsys)
    assert code == 2, refused
    assert system.posted == []
    assert "terminate" not in system.calls
    assert not _store(tmp_path).record_path_for(ATTEMPT, "process-exit").exists()
    attempts = _attempts(tmp_path)
    assert attempts and any(finding in str(item.get("refusal")) for item in attempts)
    return refused


def test_a_foreign_process_with_identical_titles_is_not_closed(
    launched, capsys, tmp_path: Path
):
    """The owned PID shows only its log; a foreign PID's document is not ours."""
    cli, env, base, system = launched
    system.windows_of = {
        PID: [LOG],
        FOREIGN_PID: [
            _window(9001, "Cisco Packet Tracer", pid=FOREIGN_PID),
            _window(9002, EXTENSION_LOG_WINDOW_TITLE, pid=FOREIGN_PID),
        ],
    }

    _refused_without_effect(
        cli, env, base, system, capsys, tmp_path, "document_window_absent"
    )


def test_a_row_attributed_to_another_process_sends_nothing(
    launched, capsys, tmp_path: Path
):
    """A census that mixes in another PID's window is not a census of ours."""
    cli, env, base, system = launched
    system.windows_of[PID] = [
        _window(9001, "Cisco Packet Tracer", pid=FOREIGN_PID),
        LOG,
    ]

    _refused_without_effect(
        cli, env, base, system, capsys, tmp_path, "window_attribution_mismatch"
    )


def test_a_census_of_another_incarnation_is_not_closed(launched, capsys, tmp_path):
    """Creation time is rechecked by the census itself, not only by observe."""
    cli, env, base, system = launched
    system.census_ticks = START_TICKS + 10_000_000

    _refused_without_effect(
        cli, env, base, system, capsys, tmp_path, "window_census_process_changed"
    )


def test_a_reused_pid_is_neither_enumerated_nor_closed(launched, capsys, tmp_path):
    """Another creation time under the same PID stops before the census."""
    cli, env, base, system = launched
    system.incarnation = "2026-09-24T09:00:00-05:00"

    _refused_without_effect(
        cli, env, base, system, capsys, tmp_path, "process_identity_changed"
    )
    assert "windows" not in system.calls


def test_a_handle_reused_before_the_close_is_refused_by_the_helper(
    launched, capsys, tmp_path: Path
):
    """The helper's same-call recheck refuses; nothing is posted or forced."""
    cli, env, base, system = launched
    system.close_refusal = "window_owner_changed"

    _refused_without_effect(
        cli, env, base, system, capsys, tmp_path, "close_not_sent:window_owner_changed"
    )
    assert system.present is True


@pytest.mark.parametrize(
    ("complete", "error", "finding"),
    [
        (False, "", "window_census_incomplete"),
        (
            True,
            "window_census_unobservable:TimeoutExpired",
            "window_census_unobservable",
        ),
    ],
)
def test_an_incomplete_enumeration_withholds_every_effect(
    launched, capsys, tmp_path: Path, complete, error, finding
):
    """No close is sent on a census that did not finish or answer."""
    cli, env, base, system = launched
    system.census_complete = complete
    system.census_error = error

    _refused_without_effect(cli, env, base, system, capsys, tmp_path, finding)


@pytest.mark.parametrize(
    ("windows", "finding"),
    [
        (
            [_window(4242, "Cisco Packet Tracer - C:\\coursework.pkt"), LOG],
            "document_window_names_file_or_nothing",
        ),
        (
            [DOCUMENT, _window(4545, "Cisco Packet Tracer"), LOG],
            "document_window_ambiguous",
        ),
        (
            [replace(DOCUMENT, enabled=False), _window(5555, "Save?", owner=4242)],
            "modal_or_owned_window_visible",
        ),
    ],
    ids=["changed-document", "ambiguous-document", "modal-before-close"],
)
def test_a_changed_ambiguous_or_modal_document_withholds_every_effect(
    launched, capsys, tmp_path: Path, windows, finding
):
    """Unknown document state is not permission to close or kill."""
    cli, env, base, system = launched
    system.windows_of[PID] = windows

    refused = _refused_without_effect(cli, env, base, system, capsys, tmp_path, finding)
    assert refused["window_census_before"]["windows"]


def _appear(window: OwnedWindow):
    def change(system: _FakeOS) -> None:
        system.windows_of[PID] = [*system.windows_of[PID], window]

    return change


@pytest.mark.parametrize(
    "window",
    [
        _window(4545, "Cisco Packet Tracer"),
        _window(5555, "Save changes?", owner=DOCUMENT.handle),
    ],
    ids=["second-document", "modal"],
)
def test_a_window_appearing_after_the_census_stops_the_close(
    launched, capsys, tmp_path: Path, window
):
    """The close rechecks the whole visible set, not only its target."""
    cli, env, base, system = launched
    system.after_census[1] = _appear(window)

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2, refused
    assert system.posted == []
    assert "terminate" not in system.calls
    assert not _store(tmp_path).record_path_for(ATTEMPT, "process-exit").exists()


def test_a_modal_appearing_after_the_second_census_stops_the_force(
    launched, capsys, tmp_path: Path
):
    """The termination rechecks the visible set the force was decided on."""
    cli, env, base, system = launched
    system.on_close = "stay"
    system.after_census[2] = _appear(
        _window(5555, "Save changes?", owner=DOCUMENT.handle)
    )

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2, refused
    assert system.posted == [DOCUMENT.handle]
    assert "terminate" not in system.calls
    assert system.present is True
    assert "termination_not_sent:window_set_changed" in refused["refusal"]


def test_a_modal_prompt_after_the_close_is_observed_not_answered(
    launched, capsys, tmp_path: Path
):
    """One close was posted; the prompt is recorded, never answered or forced."""
    cli, env, base, system = launched
    system.on_close = "modal"

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2
    assert system.posted == [DOCUMENT.handle]
    assert "terminate" not in system.calls
    assert "modal_or_owned_window_visible" in refused["refusal"]
    after = refused["window_census_after"]["windows"]
    assert any(item["owner_handle"] == DOCUMENT.handle for item in after)
    assert not _store(tmp_path).record_path_for(ATTEMPT, "process-exit").exists()


def test_a_close_that_does_not_exit_is_forced_only_on_the_same_document(
    launched, capsys, tmp_path: Path
):
    """Bounded close, identical process and window, exact PID, observed exit."""
    cli, env, base, system = launched
    system.on_close = "stay"

    code, retired = _run(cli, ["--retire", *base], env, capsys)

    assert code == 0, retired
    assert retired["outcome"] == "exited_before_setup_forced"
    assert system.posted == [DOCUMENT.handle]
    assert system.calls.index("close_helper") < system.calls.index("terminate")
    store = _store(tmp_path)
    forced = store.load_process_exit(ATTEMPT)["forced_termination"]
    assert forced["method"] == "Process.Kill"
    assert forced["rechecked_document_window"]["handle"] == DOCUMENT.handle
    assert forced["modal_windows_visible"] is False
    assert forced["bound_process_start_ticks"] == START_TICKS
    assert forced["bound_window_set_digest"] == visible_set_digest((DOCUMENT, LOG))
    assert forced["termination"] == {"sent": True, "refusal": "", "error": ""}
    assert forced["ownership_basis"] == "blank_launch_without_phase"
    assert store.verify_index() == ()


def test_a_document_that_closes_while_the_process_stays_is_not_forced(
    launched, capsys, tmp_path: Path
):
    """The fact is recorded; no kill follows an unexplained live process."""
    cli, env, base, system = launched
    system.on_close = "vanish"

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2
    assert system.posted == [DOCUMENT.handle]
    assert "terminate" not in system.calls
    assert "document_window_closed_process_alive" in refused["refusal"]


def test_an_already_absent_process_is_neither_closed_nor_killed(
    launched, capsys, tmp_path: Path
):
    """Absence before any request is recorded; nothing is sent."""
    cli, env, base, system = launched
    system.present = False

    _refused_without_effect(cli, env, base, system, capsys, tmp_path, "process_absent")
    assert system.calls == ["observe"]


@pytest.mark.parametrize("exits", [False, True])
def test_an_unknown_close_outcome_never_authorizes_a_force(
    launched, capsys, tmp_path: Path, exits
):
    """A helper that did not answer may have posted; nothing is forced."""
    cli, env, base, system = launched
    system.close_error = "window_close_unobservable:TimeoutExpired"
    system.present = True
    if exits:
        system.on_close = "exit"
        original = system.close_window

        def close_then_exit(pid, handle, digest, **bound):
            result = original(pid, handle, digest, **bound)
            system.present = False
            return result

        system.close_window = close_then_exit

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2
    assert "terminate" not in system.calls
    assert refused["requested"] is False
    assert not _store(tmp_path).record_path_for(ATTEMPT, "process-exit").exists()
    if not exits:
        assert "close_outcome_unknown" in refused["refusal"]


def test_a_launch_capture_that_disagrees_with_the_os_is_refused(
    fastloop_cli, tmp_path: Path, capsys, monkeypatch
):
    """The retirement evidence is observed at launch, never taken as claimed."""
    from packet_tracer_mcp.adapters.cli.server_pt_live_phase import PhasePreflight

    cli, charter, env = fastloop_cli
    monkeypatch.setattr(
        cli,
        "phase_preflight",
        lambda *_args, **_kwargs: PhasePreflight(
            _checkpoint(), None, _process(), campaign=FASTLOOP_CAMPAIGN
        ),
    )
    system = _FakeOS()
    system.main_title = "Cisco Packet Tracer - C:\\coursework.pkt"
    monkeypatch.setattr(cli, "_PROCESS_CONTROL", system)
    capture = tmp_path / "launch.json"
    capture.write_text(
        json.dumps(
            {
                "pid": PID,
                "process_path": PATH,
                "process_incarnation": INCARNATION,
                "main_window_title": "Cisco Packet Tracer",
                "command_line": COMMAND_LINE,
                "created_by_campaign": True,
                "workspace_kind": "disposable_declared",
                "launch_method": "Start-Process",
            }
        ),
        encoding="utf-8",
    )
    base = ["--campaign", "fastloop", "--attempt", ATTEMPT, "--charter", str(charter)]

    code, refused = _run(
        cli, ["--record-launch", *base, "--launch-evidence", str(capture)], env, capsys
    )

    assert code == 2
    assert refused["reason"] == "launch_evidence:ValueError"


def test_unestablished_workspace_ownership_prevents_any_retirement_effect(
    launched, capsys, tmp_path: Path
):
    """A setup grant without its empty baseline: no census, close or force."""
    cli, env, base, system = launched
    bundle = prepare_server_pt_commissioning(30, "COLD_HTTP_" + ATTEMPT)
    store = _store(tmp_path)
    store.save_phase_grant(
        ATTEMPT,
        derive_server_pt_phase_grant(
            "setup",
            ATTEMPT,
            _checkpoint(),
            _process(),
            None,
            bundle_sha256="c" * 64,
            prequalification_sha256="d" * 64,
            bundle=bundle,
            campaign=FASTLOOP_CAMPAIGN,
        ),
    )
    store.refresh_index()

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2
    assert refused["reason"].startswith("retirement_unestablished:")
    assert system.calls == []


def test_record_exit_never_admits_a_forced_capture(
    launched, capsys, tmp_path: Path, monkeypatch
):
    """A capture cannot carry a force; only the observed retirement can."""
    cli, env, base, _system = launched

    class _Census:
        def __init__(self, **_kwargs):
            pass

        def read(self):
            return type("Observed", (), {"error": "", "processes": ()})()

    monkeypatch.setattr(cli, "PowerShellPacketTracerProcessReader", _Census)
    close = tmp_path / "close.json"
    close.write_text(
        json.dumps(
            {
                **_launch(),
                "method": "WM_CLOSE",
                "close_target": _target(),
                "requested": True,
                "actual_exit_observed": True,
                "graceful_wait_seconds": 30.0,
                "forced_termination": {"method": "Stop-Process", "pid": PID},
            }
        ),
        encoding="utf-8",
    )

    code, refused = _run(
        cli, ["--record-exit", *base, "--close-evidence", str(close)], env, capsys
    )

    assert code == 2
    assert refused["reason"] == "process_exit:ValueError"


# -- the historical exit import --------------------------------------------------------

LAUNCHED_AT = "2026-09-24T03:43:18.7893781Z"
CLEANUP_AT = "2026-09-24T03:48:43.413036+00:00"
REQUESTED_AT = "2026-09-24T03:49:53.0758496Z"
PRESENCE_AT = "2026-09-24T03:50:13.930Z"
ABSENCE_AT = "2026-09-24T03:50:25.443Z"
CENSUS_AT = "2026-09-24T03:50:40.2114457Z"
REFUSAL = '{"outcome": "refused", "reasons": ["process_document_title_changed"]}'


def _request_command(guard: str = "", receiver: int | str = "$pidOwned") -> str:
    """Return the lead's request command form, with the lab's identity."""
    return (
        f"$pidOwned = {PID}; $p = Get-Process -Id {receiver}; "
        '$cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$pidOwned")'
        ".CommandLine; "
        f"if ($p.StartTime.ToString('o') -ne '{INCARNATION}' -or "
        f"$p.MainModule.FileName -ne '{PATH}' -or "
        f"$cmd.Trim() -ne '{COMMAND_LINE.strip()}') "
        "{ throw 'identity differs; nothing requested' }; "
        "$requestedAt = (Get-Date).ToUniversalTime().ToString('o'); "
        f"{guard}$requested = $p.CloseMainWindow(); "
        '"requested=$requested at=$requestedAt main_title_at_request=[x]"; '
        "$exited = $false; for ($i = 0; $i -lt 40; $i++) { Start-Sleep -Milliseconds "
        "500; if (-not (Get-Process -Id $pidOwned -ErrorAction SilentlyContinue)) "
        '{ $exited = $true; break } }; "exited=$exited"'
    )


def _absence_command() -> str:
    """Return the lead's later window listing, which reports absence."""
    return (
        'Add-Type @"\npublic static class W2 { }\n"@; '
        f"if (Get-Process -Id {PID} -ErrorAction SilentlyContinue) "
        f'{{ [W2]::Titles({PID}) | ForEach-Object {{ "window: $_" }} }} '
        f'else {{ "process {PID} exited" }}'
    )


def _transcript_lines() -> list[bytes]:
    """Return a small session transcript; 1-based lines 3-10 hold the exit."""

    def line(value: object) -> bytes:
        return json.dumps(value, separators=(",", ":")).encode("utf-8")

    def use(command: str) -> bytes:
        # A real transcript keeps the input twice: as sent and as recorded.
        return line(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "input": {"command": command}}]
                },
                "wireToolInputs": {"command": command},
            }
        )

    def answer(text: str, stamp: str) -> bytes:
        return line(
            {
                "type": "user",
                "timestamp": stamp,
                "message": {"content": [{"type": "tool_result", "content": text}]},
            }
        )

    return [
        line({"type": "note", "text": "earlier work"}),
        line({"type": "note", "text": "setup"}),
        use("python -m server_pt_commissioning --retire ..."),
        answer(f"Exit code 2\n{REFUSAL}\n2", "2026-09-24T03:48:55.333Z"),
        use(_request_command()),
        answer(
            f"requested=True at={REQUESTED_AT} main_title_at_request=[x]\nexited=False",
            PRESENCE_AT,
        ),
        use(_absence_command()),
        answer("process 123 exited", ABSENCE_AT),
        use("census; mailbox; write close-capture.json"),
        answer(
            "packet_tracer_processes=0\nmailbox_pending=0", "2026-09-24T03:50:40.506Z"
        ),
        line({"type": "note", "text": "later"}),
    ]


def _capture() -> dict[str, object]:
    return {
        "pid": PID,
        "process_path": PATH,
        "process_incarnation": INCARNATION,
        "method": "CloseMainWindow",
        "requested": True,
        "requested_at_utc": REQUESTED_AT,
        "actual_exit_observed": True,
        "observed_at_utc": CENSUS_AT,
        "process_count": 0,
        "completion_method": "graceful_close_request_only",
        "note": "lead narrative",
    }


def _provenance() -> dict[str, str]:
    return {
        "pid": "transcribed",
        "process_path": "transcribed",
        "process_incarnation": "transcribed",
        "method": "transcribed",
        "requested": "transcribed",
        "requested_at_utc": "transcribed",
        "actual_exit_observed": "observed",
        "observed_at_utc": "observed",
        "process_count": "observed",
        "completion_method": "lead_assertion",
        "note": "lead_assertion",
    }


class _ImportLab:
    """A temporary FASTLOOP archive with one restored attempt and its originals."""

    def __init__(self, root: Path):
        self.root = root
        self.lab = root / "lab"
        self.lab.mkdir()
        self.transcript = self.lab / "session.jsonl"
        self.transcript.write_bytes(b"\n".join(_transcript_lines()) + b"\n")
        self.files = {
            "close_capture": self.lab / "close-capture.json",
            "close_request_output": self.lab / "close-request.txt",
            "prelaunch_census": self.lab / "prelaunch-census.json",
            "transcript_excerpt": self.lab / "excerpt.jsonl",
            "event_log_query": self.lab / "event-log.txt",
        }
        self.write_capture(_capture())
        self.files["close_request_output"].write_bytes(
            f"requested=True requested_at_utc={REQUESTED_AT} "
            "exited_within_20s=False\r\n".encode("ascii")
        )
        self.files["prelaunch_census"].write_bytes(
            json.dumps(
                {
                    "attempt_id": ATTEMPT,
                    "source_sha": HEAD,
                    "observed_at_utc": "2026-09-24T03:43:18.7561037Z",
                    "process_count": 0,
                }
            ).encode()
        )
        self.lines = list(range(3, 11))
        self.write_excerpt()
        self.files["event_log_query"].write_bytes(b"matching_events=0\r\n")
        self.manifest = {
            "kind": "historical_exit_import",
            "attempt_id": ATTEMPT,
            "episode": 1,
            "artifacts": {
                role: {"path": str(path), "origin": "lead_command_output_file"}
                for role, path in self.files.items()
            },
            "capture_field_provenance": _provenance(),
            "time_bounds": {
                "close_requested_at_utc": {
                    "value": REQUESTED_AT,
                    "clock": "os",
                    "artifact": "close_request_output",
                },
                "presence_last_reported_by_utc": {
                    "value": PRESENCE_AT,
                    "clock": "session_transcript",
                    "artifact": "transcript_excerpt",
                    "line": 6,
                },
                "absence_first_reported_by_utc": {
                    "value": ABSENCE_AT,
                    "clock": "session_transcript",
                    "artifact": "transcript_excerpt",
                    "line": 8,
                },
                "zero_census_observed_at_utc": {
                    "value": CENSUS_AT,
                    "clock": "os",
                    "artifact": "close_capture",
                },
            },
            "retire_refusal": {"output": REFUSAL, "line": 4, "source_sha": HEAD},
            "close_request_command": {"line": 5, "answer_line": 6},
            "absence_command": {"line": 7, "answer_line": 8},
            "retained_command_range": {"first_line": 5, "last_line": 10},
            "lead_report": "The lead requested one graceful close.",
        }
        self.manifest["artifacts"]["transcript_excerpt"].update(
            {"source_path": str(self.transcript), "source_lines": self.lines}
        )

    def write_capture(self, capture: dict[str, object]) -> None:
        self.files["close_capture"].write_bytes(
            b"\xef\xbb\xbf"
            + json.dumps(capture, separators=(",", ":")).encode()
            + b"\r\n"
        )

    def write_excerpt(self) -> None:
        source = self.transcript.read_bytes().split(b"\n")
        self.files["transcript_excerpt"].write_bytes(
            b"".join(source[number - 1] + b"\n" for number in self.lines)
        )

    def launch(self) -> dict[str, object]:
        return {
            "pid": PID,
            "process_path": PATH,
            "process_incarnation": INCARNATION,
            "launched_at_utc": LAUNCHED_AT,
            "prelaunch_census_path": str(self.files["prelaunch_census"]),
            "source_sha": HEAD,
            "source_tree": TREE,
            "campaign_id": FASTLOOP_CAMPAIGN.campaign_id,
            "execution_purpose": "experimental",
            "observed_command_line": COMMAND_LINE,
            "observed_main_window_title": EXTENSION_LOG_WINDOW_TITLE,
        }

    def artifacts(self) -> dict[str, bytes]:
        return {role: path.read_bytes() for role, path in self.files.items()}

    def manifest_file(self) -> Path:
        path = self.lab / "manifest.json"
        path.write_text(json.dumps(self.manifest), encoding="utf-8")
        return path


def _authority(addendum: bytes) -> HistoricalExitImportAuthority:
    return HistoricalExitImportAuthority(
        addendum_sha256=hashlib.sha256(addendum).hexdigest(),
        campaign_id=FASTLOOP_CAMPAIGN.campaign_id,
        attempt_id=ATTEMPT,
        episode=1,
        episode_source_sha=HEAD,
        episode_source_tree=TREE,
    )


def _findings(lab: _ImportLab, **changes) -> tuple[str, ...]:
    return historical_exit_import_findings(
        authority=_authority(b"addendum"),
        manifest=changes.get("manifest", lab.manifest),
        launch=changes.get("launch", lab.launch()),
        cleanup_recorded_at_utc=changes.get("cleanup", CLEANUP_AT),
        artifacts=changes.get("artifacts", lab.artifacts()),
        archive_at_utc=changes.get("archive", "2026-09-24T12:00:00+00:00"),
    )


def test_the_retained_originals_support_the_import(tmp_path: Path):
    """The positive control of every rule below."""
    assert _findings(_ImportLab(tmp_path)) == ()


def _mutate(lab: _ImportLab, path: str, value: object) -> dict[str, object]:
    manifest = json.loads(json.dumps(lab.manifest))
    target = manifest
    keys = path.split(".")
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    return manifest


@pytest.mark.parametrize(
    ("path", "value", "finding"),
    [
        ("attempt_id", OTHER, "import_manifest_not_this_authority"),
        ("episode", 2, "import_manifest_not_this_authority"),
        (
            "capture_field_provenance.observed_at_utc",
            "lead_assertion",
            "exit_claim_not_supported_by_observation",
        ),
        (
            "capture_field_provenance.process_count",
            "transcribed",
            "exit_claim_not_supported_by_observation",
        ),
        (
            "capture_field_provenance.pid",
            "lead_assertion",
            "exit_claim_not_supported_by_observation",
        ),
        (
            "capture_field_provenance.note",
            "observed?",
            "capture_field_provenance_incomplete",
        ),
        (
            "time_bounds.presence_last_reported_by_utc.value",
            ABSENCE_AT,
            "time_bounds_out_of_order",
        ),
        (
            "time_bounds.close_requested_at_utc.value",
            "2026-09-24T03:49:54Z",
            "time_bounds_disagree_with_capture",
        ),
        (
            "time_bounds.absence_first_reported_by_utc.line",
            99,
            "time_bound_citation_invalid",
        ),
        (
            "time_bounds.zero_census_observed_at_utc.clock",
            "session_transcript",
            "time_bound_citation_invalid",
        ),
        ("retire_refusal.line", 6, "retire_refusal_not_retained"),
        ("retire_refusal.source_sha", "d" * 40, "retire_refusal_not_retained"),
        ("retained_command_range.last_line", 12, "retained_command_range_incomplete"),
        (
            "artifacts.prelaunch_census.path",
            "C:\\elsewhere.json",
            "prelaunch_census_does_not_bind_the_launch",
        ),
        (
            "artifacts.transcript_excerpt.source_lines",
            [3, 4],
            "transcript_excerpt_lines_malformed",
        ),
    ],
)
def test_each_manifest_claim_must_be_supported(tmp_path: Path, path, value, finding):
    """A citation, order, origin or binding that does not hold is refused."""
    lab = _ImportLab(tmp_path)

    assert finding in _findings(lab, manifest=_mutate(lab, path, value))


@pytest.mark.parametrize(
    ("change", "finding"),
    [
        ({"pid": 124}, "close_capture_does_not_bind_the_launch"),
        ({"process_count": 1}, "close_capture_does_not_bind_the_launch"),
        ({"actual_exit_observed": False}, "close_capture_does_not_bind_the_launch"),
        ({"process_incarnation": "other"}, "close_capture_does_not_bind_the_launch"),
        (
            {"forced_termination": {"method": "Stop-Process"}},
            "close_capture_does_not_bind_the_launch",
        ),
        (
            {"requested_at_utc": "2026-09-24T03:49:54Z"},
            "close_request_output_disagrees",
        ),
    ],
)
def test_a_capture_that_does_not_bind_the_launch_is_refused(
    tmp_path: Path, change, finding
):
    """The capture passes the existing exit rules against the launch, or not."""
    lab = _ImportLab(tmp_path)
    capture = {**_capture(), **change}
    lab.write_capture(capture)
    manifest = json.loads(json.dumps(lab.manifest))
    manifest["capture_field_provenance"] = {
        key: _provenance().get(key, "lead_assertion") for key in capture
    }

    assert finding in _findings(lab, manifest=manifest)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("close_request_command", None),
        ("close_request_command.line", 7),
        ("close_request_command.answer_line", 8),
    ],
    ids=["missing", "other-command", "other-answer"],
)
def test_the_retained_request_command_must_name_the_owned_process(
    tmp_path: Path, path, value
):
    """The capture's identity fields need the request's own command and answer."""
    lab = _ImportLab(tmp_path)

    found = _findings(lab, manifest=_mutate(lab, path, value))

    assert "close_request_not_bound_to_the_owned_process" in found


@pytest.mark.parametrize(
    "extra",
    [" pid=999", " method=Stop-Process", " requested=False"],
)
def test_a_request_output_that_contradicts_the_capture_is_refused(
    tmp_path: Path, extra
):
    """Contradictory fields in the request's own output are not ignored."""
    lab = _ImportLab(tmp_path)
    raw = lab.files["close_request_output"].read_bytes().rstrip(b"\r\n")
    lab.files["close_request_output"].write_bytes(raw + extra.encode() + b"\r\n")

    assert "close_request_output_disagrees" in _findings(lab)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (
            "time_bounds.absence_first_reported_by_utc.value",
            "2026-09-24T03:50:14Z",
        ),
        ("time_bounds.presence_last_reported_by_utc.line", 4),
        ("time_bounds.absence_first_reported_by_utc.line", 6),
    ],
    ids=["earlier-absence", "presence-from-refusal", "absence-from-presence"],
)
def test_a_transcript_bound_must_be_what_its_line_reports(tmp_path: Path, path, value):
    """The value is the cited answer's own time, and the answer shows the state."""
    lab = _ImportLab(tmp_path)

    assert "time_bound_not_supported_by_its_line" in _findings(
        lab, manifest=_mutate(lab, path, value)
    )


@pytest.mark.parametrize(
    "command",
    [
        # The identity appears, but only in a comment; $p is another process.
        f"$pidOwned = {PID}; $p = Get-Process -Id 999; # {INCARNATION} {PATH} "
        "$requested = $p.CloseMainWindow()",
        # The exact form, but $p is replaced after the guard.
        _request_command(guard="$p = Get-Process -Id 999; "),
        # The exact form, but the receiver is another PID from the start.
        _request_command(receiver=999),
    ],
    ids=["comment-only", "reassigned-after-guard", "other-receiver"],
)
def test_the_identity_must_guard_the_process_that_receives_the_close(
    tmp_path: Path, command
):
    """Only the exact supported command form binds the close to the owned PID."""
    lab = _ImportLab(tmp_path)
    lines = _transcript_lines()
    lines[4] = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "input": {"command": command}}]
            },
        },
        separators=(",", ":"),
    ).encode()
    lab.transcript.write_bytes(b"\n".join(lines) + b"\n")
    lab.write_excerpt()

    assert "close_request_not_bound_to_the_owned_process" in _findings(lab)


def test_a_retained_range_that_names_a_termination_is_refused(tmp_path: Path):
    """The claim that the lead issued no termination must hold in the record."""
    lab = _ImportLab(tmp_path)
    lines = _transcript_lines()
    lines[6] = lines[6].replace(b"ForEach-Object", b"Stop-Process -Id 123 -Force;")
    lab.transcript.write_bytes(b"\n".join(lines) + b"\n")
    lab.write_excerpt()

    assert "retained_record_names_a_termination" in _findings(lab)


def test_the_launch_must_be_the_authorized_episode_source(tmp_path: Path):
    """An episode source other than the addendum's is not importable."""
    lab = _ImportLab(tmp_path)

    found = _findings(lab, launch={**lab.launch(), "source_tree": "f" * 40})

    assert "launch_not_the_authorized_episode_source" in found


def test_the_cleanup_and_archive_bound_the_request(tmp_path: Path):
    """A request before the restored cleanup, or an archive before it, is refused."""
    lab = _ImportLab(tmp_path)

    assert "time_bounds_out_of_order" in _findings(
        lab, cleanup="2026-09-24T03:50:00+00:00"
    )
    assert "time_bounds_out_of_order" in _findings(
        lab, archive="2026-09-24T03:50:30+00:00"
    )


class _NoPacketTracer:
    processes: tuple = ()
    error = ""

    def __init__(self, **_kwargs):
        pass

    def read(self):
        return self


@pytest.fixture
def import_lab(fastloop_cli, tmp_path: Path, monkeypatch):
    """One restored attempt, its originals, and every non-local read faked."""
    cli, charter, env = fastloop_cli
    lab = _ImportLab(tmp_path)
    addendum = tmp_path / "addendum-02.md"
    addendum.write_bytes(b"# Addendum 02\r\n")
    monkeypatch.setattr(
        cli, "_EXIT_IMPORT_AUTHORITY", _authority(addendum.read_bytes())
    )
    recorder = replace(_checkpoint(), head="d" * 40, tree="e" * 40)
    monkeypatch.setattr(cli, "repository_identity", lambda _root: recorder)
    monkeypatch.setattr(
        cli,
        "_SOURCE_ANCESTRY",
        lambda _root, ancestor, descendant: SourceAncestry(
            ancestor, descendant, TREE, is_ancestor=True
        ),
    )
    monkeypatch.setattr(cli, "PowerShellPacketTracerProcessReader", _NoPacketTracer)
    mailbox = tmp_path / "mailbox"
    mailbox.mkdir()
    monkeypatch.setattr(cli, "_MAILBOX_DIR", lambda: mailbox)

    def no_effect():
        raise AssertionError("an import never observes, closes or terminates")

    monkeypatch.setattr(cli, "_PROCESS_CONTROL", no_effect)
    store = _store(tmp_path)
    store.save_process_launch(ATTEMPT, lab.launch())
    status = {"attempt_id": ATTEMPT, "outcome": "restored", "phase": "cleanup"}
    store.save_phase_status(ATTEMPT, "cleanup", status)
    store.save_archive_admission(ATTEMPT, "cleanup")
    store.save_ledger_record(
        f"episode-0001-{ATTEMPT}-cleanup-result",
        {"kind": "phase_result", "recorded_at_utc": CLEANUP_AT, "outcome": "restored"},
    )
    store.update_current_status(status)
    store.refresh_index()
    base = [
        "--import-exit",
        "--campaign",
        "fastloop",
        "--attempt",
        ATTEMPT,
        "--charter",
        str(charter),
        "--addendum",
        str(addendum),
    ]
    return cli, env, base, lab, addendum


def _archive_bytes(root: Path) -> dict[str, bytes]:
    directory = root / "data" / "commissioning"
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_the_import_is_additive_and_claims_no_more_than_absence(
    import_lab, capsys, tmp_path: Path
):
    """Byte-exact originals, a preserved index, no process-exit, no credit."""
    cli, env, base, lab, addendum = import_lab
    before = _archive_bytes(tmp_path)
    index_before = before[
        f"data/commissioning/{FASTLOOP_CAMPAIGN.campaign_id}/index.json"
    ]

    code, imported = _run(
        cli, [*base, "--import-manifest", str(lab.manifest_file())], env, capsys
    )

    assert code == 0, imported
    assert imported["outcome"] == "absence_observed_after_graceful_request"
    assert imported["retire_credited"] is False
    after = _archive_bytes(tmp_path)
    campaign = f"data/commissioning/{FASTLOOP_CAMPAIGN.campaign_id}"
    for name, raw in before.items():
        if name != f"{campaign}/index.json":
            assert after[name] == raw, name
    digest = hashlib.sha256(index_before).hexdigest()
    assert after[f"{campaign}/index-history/index-{digest}.json"] == index_before
    index = json.loads(after[f"{campaign}/index.json"])
    assert index["predecessor"]["sha256"] == digest
    assert after[f"{campaign}/authority/addendum-02.md"] == addendum.read_bytes()
    for role, path in lab.files.items():
        suffix = path.suffix
        stored = f"{campaign}/{ATTEMPT}/exit-import-{role.replace('_', '-')}{suffix}"
        assert after[stored] == path.read_bytes(), role
    store = _store(tmp_path)
    assert not store.record_path_for(ATTEMPT, "process-exit").exists()
    assert store.verify_index() == ()
    record = store.load_exit_import(ATTEMPT)
    assert record["exit_method"] == "unproven"
    assert record["retire_credited"] is False
    assert record["recorder_source"]["sha"] == "d" * 40
    assert record["episode_source"] == {
        "sha": HEAD,
        "tree": TREE,
        "ancestor_of_recorder": True,
    }
    assert record["lead_assertions_not_evidence"] == ["completion_method", "note"]
    assert record["fresh_state"]["packet_tracer_contacted"] is False
    assert record["fresh_state"]["owned_pid_present"] is False
    assert record["archived_at_utc"] > CENSUS_AT.replace("Z", "+00:00")
    assert record["transcript_source"]["lines_verified"] == lab.lines

    code, again = _run(
        cli, [*base, "--import-manifest", str(lab.manifest_file())], env, capsys
    )
    assert code == 2
    assert again["reason"] == "import_exit:ValueError"


def test_an_interrupted_import_is_completed_by_its_retry(
    import_lab, capsys, tmp_path: Path, monkeypatch
):
    """A stop between writes leaves residue that only this import completes."""
    cli, env, base, lab, _addendum = import_lab
    argv = [*base, "--import-manifest", str(lab.manifest_file())]
    original = ServerPtCommissioningStore.save_exit_import_artifact
    calls = {"count": 0}

    def interrupted(self, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 3:
            raise OSError("disk went away")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(
        ServerPtCommissioningStore, "save_exit_import_artifact", interrupted
    )
    code, stopped = _run(cli, argv, env, capsys)
    assert code == 2, stopped
    assert _store(tmp_path).verify_index() == ("archive_inventory_changed",)
    monkeypatch.setattr(
        ServerPtCommissioningStore, "save_exit_import_artifact", original
    )

    code, imported = _run(cli, argv, env, capsys)

    assert code == 0, imported
    store = _store(tmp_path)
    assert store.verify_index() == ()
    assert store.load_exit_import(ATTEMPT)["exit_method"] == "unproven"


def test_an_import_stopped_after_its_record_is_sealed_by_its_retry(
    import_lab, capsys, tmp_path: Path, monkeypatch
):
    """The already written record is indexed as written, never rewritten."""
    cli, env, base, lab, _addendum = import_lab
    argv = [*base, "--import-manifest", str(lab.manifest_file())]
    original = ServerPtCommissioningStore.refresh_index

    def refused(self, *args, **kwargs):
        if kwargs.get("predecessor") is not None:
            raise OSError("stopped before the index")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ServerPtCommissioningStore, "refresh_index", refused)
    code, stopped = _run(cli, argv, env, capsys)
    assert code == 2, stopped
    record = _store(tmp_path).record_path_for(ATTEMPT, "exit-import")
    written = record.read_bytes()
    monkeypatch.setattr(ServerPtCommissioningStore, "refresh_index", original)

    code, sealed = _run(cli, argv, env, capsys)

    assert code == 0, sealed
    assert sealed["completed_interrupted_import"] is True
    assert record.read_bytes() == written
    assert _store(tmp_path).verify_index() == ()


def _stop_before_the_index(import_lab, capsys, monkeypatch):
    """Run the import once, stopping after its record and before its index."""
    cli, env, base, lab, _addendum = import_lab
    argv = [*base, "--import-manifest", str(lab.manifest_file())]
    original = ServerPtCommissioningStore.refresh_index

    def refused(self, *args, **kwargs):
        if kwargs.get("predecessor") is not None:
            raise OSError("stopped before the index")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ServerPtCommissioningStore, "refresh_index", refused)
    code, _stopped = _run(cli, argv, env, capsys)
    assert code == 2
    monkeypatch.setattr(ServerPtCommissioningStore, "refresh_index", original)
    return cli, env, argv


def test_a_record_whose_named_bytes_changed_is_not_completed(
    import_lab, capsys, tmp_path: Path, monkeypatch
):
    """Completion indexes only what the record states, byte for byte."""
    cli, env, argv = _stop_before_the_index(import_lab, capsys, monkeypatch)
    campaign = tmp_path / "data" / "commissioning" / FASTLOOP_CAMPAIGN.campaign_id
    artifact = campaign / ATTEMPT / "exit-import-close-capture.json"
    artifact.write_bytes(artifact.read_bytes() + b" ")

    refused = _refuses_and_writes_nothing(cli, env, argv, capsys, tmp_path)

    assert refused["reason"] == "import_completion:ValueError"


def test_a_record_stopped_before_its_digest_is_completed_with_it(
    import_lab, capsys, tmp_path: Path, monkeypatch
):
    """The missing digest is derived from the record's own bytes, nothing more."""
    cli, env, argv = _stop_before_the_index(import_lab, capsys, monkeypatch)
    store = _store(tmp_path)
    record = store.record_path_for(ATTEMPT, "exit-import")
    record.with_name("exit-import.sha256").unlink()
    written = record.read_bytes()

    code, sealed = _run(cli, argv, env, capsys)

    assert code == 0, sealed
    assert sealed["completed_interrupted_import"] is True
    assert record.read_bytes() == written
    assert store.load_exit_import(ATTEMPT)["disposition"] == (
        "absence_observed_after_graceful_request"
    )
    assert store.verify_index() == ()
    code, again = _run(cli, argv, env, capsys)
    assert code == 2
    assert again["reason"] == "import_exit:ValueError"


@pytest.mark.parametrize("change", ["claim", "no-artifacts"])
def test_an_altered_or_planted_record_is_never_completed(
    import_lab, capsys, tmp_path: Path, monkeypatch, change
):
    """Completion revalidates everything; a self-consistent forgery refuses."""
    cli, env, argv = _stop_before_the_index(import_lab, capsys, monkeypatch)
    store = _store(tmp_path)
    record = store.record_path_for(ATTEMPT, "exit-import")
    value = json.loads(record.read_bytes())
    if change == "claim":
        value["exit_method"] = "graceful_close"
    else:
        for item in value["artifacts"]:
            (tmp_path / item["file"]).unlink()
        value["artifacts"] = []
    forged = (json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n").encode()
    record.write_bytes(forged)
    record.with_name("exit-import.sha256").write_bytes(
        (hashlib.sha256(forged).hexdigest() + "\n").encode()
    )

    refused = _refuses_and_writes_nothing(cli, env, argv, capsys, tmp_path)

    assert refused["reason"].startswith(("import_completion:", "import_exit:"))
    assert store.verify_index() == ("archive_inventory_changed",)


def test_residue_the_import_did_not_write_blocks_it(import_lab, capsys, tmp_path: Path):
    """Only this import's own files may be completed; anything else refuses."""
    cli, env, base, lab, _addendum = import_lab
    stray = (
        tmp_path
        / "data"
        / "commissioning"
        / FASTLOOP_CAMPAIGN.campaign_id
        / "stray.json"
    )
    stray.write_text("{}", encoding="utf-8")
    argv = [*base, "--import-manifest", str(lab.manifest_file())]

    refused = _refuses_and_writes_nothing(cli, env, argv, capsys, tmp_path)

    assert refused["reason"].startswith("import_exit:")


def _refuses_and_writes_nothing(cli, env, argv, capsys, tmp_path: Path):
    before = _archive_bytes(tmp_path)
    code, refused = _run(cli, argv, env, capsys)
    assert code == 2, refused
    assert _archive_bytes(tmp_path) == before
    return refused


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("other-attempt", "import_not_authorized:"),
        ("wrong-addendum", "import_not_authorized:"),
        ("not-descendant", "import_exit:ValueError"),
        ("other-episode-tree", "import_exit:ValueError"),
        ("dirty-recorder", "import_exit:ValueError"),
        ("excerpt-not-source", "import_exit:ValueError"),
        ("owned-pid-present", "import_exit:ValueError"),
        ("census-unreadable", "import_exit:ValueError"),
    ],
)
def test_an_unauthorized_or_unsupported_import_writes_nothing(
    import_lab, capsys, tmp_path: Path, monkeypatch, change, reason
):
    """Every refusal happens before the first write."""
    cli, env, base, lab, addendum = import_lab
    argv = [*base, "--import-manifest", str(lab.manifest_file())]
    if change == "other-attempt":
        argv[argv.index(ATTEMPT)] = OTHER
    elif change == "wrong-addendum":
        addendum.write_bytes(b"# Another addendum\r\n")
    elif change in {"not-descendant", "other-episode-tree"}:
        ancestor = change == "other-episode-tree"
        tree = "f" * 40 if ancestor else TREE
        monkeypatch.setattr(
            cli,
            "_SOURCE_ANCESTRY",
            lambda _r, a, d: SourceAncestry(a, d, tree, is_ancestor=ancestor),
        )
    elif change == "dirty-recorder":
        monkeypatch.setattr(
            cli,
            "repository_identity",
            lambda _root: replace(_checkpoint(), clean=False),
        )
    elif change == "excerpt-not-source":
        lines = _transcript_lines()
        lines[5] = lines[5].replace(b"exited=False", b"exited=True")
        lab.transcript.write_bytes(b"\n".join(lines) + b"\n")
    elif change in {"owned-pid-present", "census-unreadable"}:

        class _Census(_NoPacketTracer):
            error = "unreadable" if change == "census-unreadable" else ""
            processes = (type("Row", (), {"pid": PID})(),)

        monkeypatch.setattr(cli, "PowerShellPacketTracerProcessReader", _Census)

    refused = _refuses_and_writes_nothing(cli, env, argv, capsys, tmp_path)

    assert refused["reason"].startswith(reason)


def test_an_unsupported_manifest_is_refused_with_its_findings(
    import_lab, capsys, tmp_path: Path
):
    """The pure rule's findings reach the operator; nothing is written."""
    cli, env, base, lab, _addendum = import_lab
    lab.manifest["capture_field_provenance"]["observed_at_utc"] = "lead_assertion"
    argv = [*base, "--import-manifest", str(lab.manifest_file())]

    refused = _refuses_and_writes_nothing(cli, env, argv, capsys, tmp_path)

    assert refused["reasons"] == ["exit_claim_not_supported_by_observation"]


@pytest.mark.parametrize(
    ("argv_change", "reason"),
    [
        (["--campaign", "c31"], "import_exit_is_experimental_only"),
        (["--ci-run", "42"], "experimental_ci_claim_refused"),
    ],
)
def test_a_delivery_campaign_or_a_ci_claim_cannot_import(
    import_lab, capsys, tmp_path: Path, argv_change, reason
):
    """The exception is experimental and local; it borrows no delivery label."""
    cli, env, base, lab, _addendum = import_lab
    argv = [*base, "--import-manifest", str(lab.manifest_file())]
    if argv_change[0] == "--campaign":
        argv[argv.index("fastloop")] = "c31"
    else:
        argv += argv_change

    refused = _refuses_and_writes_nothing(cli, env, argv, capsys, tmp_path)

    assert refused == {"outcome": "refused", "reason": reason}


def test_a_new_index_names_only_a_preserved_predecessor(tmp_path: Path):
    """The prior index is kept byte for byte; a made-up predecessor is refused."""
    store = _store(tmp_path)
    store.save_ledger_record("episode-0001-opening", {"kind": "episode_opening"})
    store.refresh_index()
    prior = store.index_bytes()

    with pytest.raises(ValueError):
        store.refresh_index(
            predecessor={"path": "data/elsewhere.json", "sha256": "0" * 64}
        )
    predecessor = store.preserve_index()
    assert store.preserve_index() == predecessor
    store.refresh_index(predecessor=predecessor)

    assert json.loads(store.index_bytes())["predecessor"] == predecessor
    assert (tmp_path / str(predecessor["path"])).read_bytes() == prior
    assert predecessor["sha256"] == hashlib.sha256(prior).hexdigest()
    assert store.verify_index() == ()
    (tmp_path / str(predecessor["path"])).write_bytes(prior + b" ")
    assert store.verify_index() == ("archive_bytes_changed",)


def test_the_pinned_authority_is_the_operator_addendum():
    """The one importable exit is episode 1's PID 3248 under Addendum 02."""
    assert FASTLOOP_EPISODE_1_EXIT_IMPORT == HistoricalExitImportAuthority(
        addendum_sha256="684636f6436934029709d83e7bd651194aa6d3a7cd9e56da55d592b8660ea288",
        campaign_id="SERVER-PT-IOS-FASTLOOP-01",
        attempt_id="b118c84808bb06f3a8ede6cf124323b2",
        episode=1,
        episode_source_sha="1d086aad5ec473a29ddb3c631d6615ee8344d29d",
        episode_source_tree="1e709da5744ad8861239765bff9fa0a0e1c6a09f",
    )


# -- the real helper, against a window this test creates ------------------------------

_NATIVE = os.environ.get("PT_MCP_NATIVE_WINDOW_TESTS") == "1"
_FORMS = r"""
Add-Type -AssemblyName System.Windows.Forms
function New-ProbeForm([string]$title) {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = $title
    # Shown in the taskbar, a form has no owner window, like Packet Tracer's.
    $form.Opacity = 0
    $form.StartPosition = 'Manual'
    $form.Location = New-Object System.Drawing.Point(-32000, -32000)
    return $form
}
$log = New-ProbeForm 'Logs - MCP BUILDER'
$document = New-ProbeForm 'fastloop window probe'
$log.Show()
[System.Windows.Forms.Application]::Run($document)
"""


@pytest.mark.skipif(
    sys.platform != "win32" or not _NATIVE,
    reason="opt-in: set PT_MCP_NATIVE_WINDOW_TESTS=1 on Windows",
)
def test_the_native_helper_enumerates_selects_and_closes_one_window():
    """Real user32 calls: attribution, selection, a refused and a sent close."""
    encoded = base64.b64encode(_FORMS.encode("utf-16-le")).decode("ascii")
    probe = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]
    )
    try:
        control = PowerShellOwnedProcessControl()
        deadline = time.monotonic() + 30
        while True:
            census = control.windows(probe.pid)
            visible = [window for window in census.windows if window.visible]
            if len(visible) >= 2 or time.monotonic() > deadline:
                break
            time.sleep(0.5)
        assert census.complete is True and census.error == ""
        observed = control.observe(probe.pid)
        assert census.process_start_ticks == incarnation_ticks(
            observed.process_incarnation
        )
        assert all(window.owner_pid == probe.pid for window in census.windows)
        target, found = select_document_window(probe.pid, census)
        assert found == ()
        assert target.title == "fastloop window probe"
        bound = {
            "set_digest": census.visible_set_digest,
            "start_ticks": census.process_start_ticks,
        }
        refused = control.close_window(probe.pid, target.handle, "0" * 64, **bound)
        assert refused.sent is False
        assert refused.refusal == "window_identity_changed"
        stale = control.close_window(
            probe.pid,
            target.handle,
            target.identity_digest,
            set_digest="0" * 64,
            start_ticks=census.process_start_ticks,
        )
        assert stale.refusal == "window_set_changed"
        foreign = control.close_window(
            os.getpid(), target.handle, target.identity_digest, **bound
        )
        assert foreign.sent is False
        assert foreign.refusal == "process_changed"
        kept = control.terminate(
            probe.pid, set_digest="0" * 64, start_ticks=census.process_start_ticks
        )
        assert kept.refusal == "window_set_changed"
        assert probe.poll() is None
        sent = control.close_window(
            probe.pid, target.handle, target.identity_digest, **bound
        )
        assert sent.sent is True
        assert probe.wait(timeout=30) == 0
    finally:
        if probe.poll() is None:
            probe.kill()


@pytest.mark.skipif(
    sys.platform != "win32" or not _NATIVE,
    reason="opt-in: set PT_MCP_NATIVE_WINDOW_TESTS=1 on Windows",
)
def test_the_native_helper_terminates_only_the_bound_process():
    """Real handle: a stale binding refuses; the exact one terminates it."""
    encoded = base64.b64encode(_FORMS.encode("utf-16-le")).decode("ascii")
    probe = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]
    )
    try:
        control = PowerShellOwnedProcessControl()
        deadline = time.monotonic() + 30
        while True:
            census = control.windows(probe.pid)
            visible = [window for window in census.windows if window.visible]
            if len(visible) >= 2 or time.monotonic() > deadline:
                break
            time.sleep(0.5)
        assert census.complete is True and census.process_start_ticks > 0
        other = control.terminate(
            probe.pid,
            set_digest=census.visible_set_digest,
            start_ticks=census.process_start_ticks + 1,
        )
        assert other.refusal == "process_changed"
        assert probe.poll() is None
        killed = control.terminate(
            probe.pid,
            set_digest=census.visible_set_digest,
            start_ticks=census.process_start_ticks,
        )
        assert killed.sent is True
        assert probe.wait(timeout=30) == 1
    finally:
        if probe.poll() is None:
            probe.kill()
